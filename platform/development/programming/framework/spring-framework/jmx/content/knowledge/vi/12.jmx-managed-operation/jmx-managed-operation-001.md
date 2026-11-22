# @ManagedOperation và cách phơi bày phương thức qua Spring JMX

## Mục tiêu

Sau bài học, bạn có thể hiểu cách `@ManagedOperation` công bố một phương thức Java thành **JMX operation**, cấu hình exporter trong Spring, lựa chọn phương thức được phép quản trị, mô tả tham số và giá trị trả về, gọi operation qua `MBeanServerConnection`, phân biệt operation với attribute, và xử lý các vấn đề về metadata, proxy, phiên bản phương thức, quyền truy cập và hiệu năng.

## 1. Phơi bày phương thức là gì?

Một Spring bean có thể chứa hàng chục phương thức phục vụ nghiệp vụ. Không phải mọi phương thức đều nên được gọi từ bên ngoài qua JMX.

Ví dụ service:

```java
public class JobService {
    public void enqueue(Job job) { /* nghiệp vụ */ }
    public int calculatePriority(Job job) { /* ... */ return 0; }
    public void pauseIntake() { /* ... */ }
    public void resumeIntake() { /* ... */ }
}
```

Các hàm `enqueue` và `calculatePriority` thường thuộc API nghiệp vụ nội bộ. Ngược lại, `pauseIntake` hoặc `resumeIntake` có thể là thao tác quản trị có ý nghĩa khi xử lý sự cố.

`@ManagedOperation` thuộc gói:

```java
org.springframework.jmx.export.annotation.ManagedOperation
```

Annotation này đánh dấu method mà hạ tầng Spring JMX có thể xuất thành operation trong MBean. Người vận hành hoặc chương trình JMX client sau đó có thể gọi operation qua `MBeanServer.invoke` hoặc `MBeanServerConnection.invoke`, nếu MBean đã đăng ký thành công và client được phép truy cập.

Ví dụ:

```java
@ManagedOperation(description = "Pauses intake of new jobs")
public void pauseIntake() {
    intakePaused = true;
}
```

**Điểm quan trọng:** annotation không tự mở cổng JMX, không tạo MBeanServer mới và không bảo vệ lời gọi. Cần có một Spring JMX exporter hoạt động, đăng ký bean và hạ tầng kết nối JMX phù hợp.

## 2. Quan hệ giữa @ManagedResource và @ManagedOperation

Trong mô hình annotation-driven của Spring:

- `@ManagedResource` đánh dấu **bean/class** như một resource quản trị và cung cấp metadata như `objectName`, `description`.
- `@ManagedAttribute` đánh dấu getter/setter được công bố dưới dạng JMX attribute.
- `@ManagedOperation` đánh dấu method được công bố dưới dạng JMX operation.
- `@ManagedOperationParameter` / `@ManagedOperationParameters` bổ sung tên và mô tả cho tham số operation.

Ví dụ:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.jobs:type=Queue,name=Billing",
    description = "Billing job queue administration"
)
public class BillingQueueAdmin {
    private volatile boolean paused;

    @ManagedAttribute(description = "Whether intake is paused")
    public boolean isPaused() {
        return paused;
    }

    @ManagedOperation(description = "Stops accepting new billing jobs")
    public void pause() {
        paused = true;
    }

    @ManagedOperation(description = "Allows new billing jobs again")
    public void resume() {
        paused = false;
    }
}
```

Với exporter và metadata assembler phù hợp, client có thể thấy:

```text
ObjectName: com.example.jobs:type=Queue,name=Billing

Attributes:
  Paused  boolean  read-only

Operations:
  pause()   void
  resume()  void
```

`isPaused()` là attribute vì được gắn `@ManagedAttribute`; `pause()` và `resume()` là operations vì được gắn `@ManagedOperation`.

Cách phân loại này giúp client hiểu đâu là trạng thái để quan sát, đâu là hành động để thực thi.

## 3. Bật cơ chế export annotation trong Spring

Trong Spring Framework dùng Java configuration:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
```

Đảm bảo class `BillingQueueAdmin` được quản lý bởi cùng ApplicationContext, chẳng hạn bằng `@Component` và component scanning, hoặc bằng `@Bean`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class AdminBeans {
    @Bean
    public BillingQueueAdmin billingQueueAdmin() {
        return new BillingQueueAdmin();
    }
}
```

Trong cấu hình XML, có thể kích hoạt exporter bằng:

```xml
<context:mbean-export/>
```

với Spring `context` namespace được khai báo hợp lệ.

`@EnableMBeanExport` và `<context:mbean-export/>` là những cách cấu hình hạ tầng annotation-driven export; `AnnotationMBeanExporter` cung cấp cơ chế nhận diện metadata từ annotation.

Không bật nhiều exporter độc lập cùng đăng ký một `ObjectName` nếu chưa có chiến lược ownership rõ ràng. Xung đột trong một `MBeanServer` có thể gây `InstanceAlreadyExistsException`.

## 4. Một ví dụ có tham số và giá trị trả về

Operation thường cần tham số, ví dụ retry tối đa một số job lỗi.

```java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.jobs:type=RetryAdmin,name=Billing",
    description = "Limited retry controls for failed billing jobs"
)
public class RetryAdmin {
    @ManagedOperation(
        description = "Retries up to maxCount failed billing jobs"
    )
    @ManagedOperationParameters({
        @ManagedOperationParameter(
            name = "maxCount",
            description = "Maximum jobs to retry (1..100)"
        )
    })
    public int retryFailed(int maxCount) {
        if (maxCount < 1 || maxCount > 100) {
            throw new IllegalArgumentException("maxCount must be 1..100");
        }

        // Trong thực tế: gọi service retry và trả số job được nhận xử lý.
        return Math.min(maxCount, 3);
    }
}
```

Điều một JMX client cần biết:

| Thành phần | Metadata thường gặp |
| --- | --- |
| Tên operation | `retryFailed` |
| Số lượng tham số | 1 |
| Kiểu tham số | `int` |
| Tên tham số | `maxCount`, nếu exporter công bố metadata này |
| Kiểu trả về | `int` |
| Mô tả | Retry tối đa `maxCount` job lỗi |
| Ràng buộc | `1..100`, cần kiểm tra trong implementation |

Annotation mô tả tham số **không thực thi validation**. Phải validate trong code, ví dụ kiểm tra `maxCount`, đặc biệt với operation có side effect.

### Đọc và gọi qua MBeanServer

Giả sử bean đã được đăng ký trong platform MBeanServer:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "com.example.jobs:type=RetryAdmin,name=Billing"
);

Object result = server.invoke(
    name,
    "retryFailed",
    new Object[] { 5 },
    new String[] { "int" }
);

System.out.println("Accepted jobs: " + result);
```

Mảng cuối truyền **chữ ký kiểu tham số**, không phải tên tham số. Với primitive `int`, chữ ký là `"int"`, không phải `"java.lang.Integer"`. Nếu operation không có tham số, có thể dùng mảng rỗng cho parameters và signature.

Khi sử dụng `MBeanServerConnection` ở client từ xa, cú pháp `invoke` tương tự, nhưng thêm các vấn đề kết nối, xác thực, serialization và khả năng tương thích kiểu dữ liệu.

## 5. Operation khác attribute như thế nào?

JMX cung cấp hai mô hình truy cập chính:

**Attribute** biểu diễn trạng thái mà client đọc/ghi:

```java
@ManagedAttribute(description = "Current pending job count")
public int getPendingCount() {
    return pendingCount;
}
```

**Operation** biểu diễn hành động hoặc truy vấn có chủ đích:

```java
@ManagedOperation(description = "Rebuilds the local queue index")
public void rebuildIndex() {
    // ...
}
```

Client đọc attribute bằng:

```java
server.getAttribute(name, "PendingCount");
```

Client gọi operation bằng:

```java
server.invoke(name, "rebuildIndex", new Object[0], new String[0]);
```

Những nguyên tắc thường hữu ích:

- Dùng attribute cho trạng thái cần quan sát thường xuyên.
- Dùng operation cho action có side effect, truy vấn cần tham số hoặc xử lý có chủ đích.
- Getter attribute nên nhanh, ít side effect, vì công cụ giám sát có thể poll định kỳ.
- Operation có thể tốn thời gian hơn, nhưng nên có giới hạn và phản hồi minh bạch.
- Không biến mọi method public thành operation; chỉ xuất API quản trị thật sự cần thiết.

Một method `getStatus()` có thể được gắn `@ManagedOperation` nếu dự án muốn nó là một action truy vấn; nhưng nếu nó trả trạng thái đơn giản và được dùng thường xuyên, `@ManagedAttribute` thường trực quan hơn.

## 6. Đọc metadata MBeanOperationInfo

Spring chuyển thông tin annotation thành metadata JMX. Sau khi đăng ký MBean, có thể kiểm tra bằng `MBeanInfo`:

```java
import javax.management.*;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println("Name: " + operation.getName());
    System.out.println("Description: " + operation.getDescription());
    System.out.println("Return: " + operation.getReturnType());
    System.out.println("Impact: " + operation.getImpact());

    for (MBeanParameterInfo p : operation.getSignature()) {
        System.out.printf("  %s : %s (%s)%n",
                p.getName(),
                p.getType(),
                p.getDescription());
    }
}
```

`MBeanOperationInfo` chứa:

- `name`: tên operation.
- `description`: mô tả.
- `returnType`: kiểu trả về ở mức JMX metadata.
- `signature`: danh sách tham số với tên, kiểu và mô tả.
- `impact`: một trong các giá trị `INFO`, `ACTION`, `ACTION_INFO`, `UNKNOWN`.

Trường `impact` chỉ mô tả mục đích dự kiến. Nó **không tự giới hạn quyền** hoặc ngăn client gọi operation. Một operation được mô tả là thông tin vẫn có thể thực hiện side effect nếu code triển khai như vậy.

JConsole và JMC có thể hiển thị operation dựa trên metadata này; giao diện và mức hỗ trợ nhập tham số phụ thuộc phiên bản công cụ.

## 7. Overloading: hai method cùng tên

Java cho phép overload:

```java
@ManagedOperation
public void retry(int maxCount) { /* ... */ }

@ManagedOperation
public void retry(String jobId) { /* ... */ }
```

Trong JMX, tên `retry` thôi chưa đủ để chọn operation. Khi gọi `invoke`, cần truyền đúng **signature**:

```java
server.invoke(
    name, "retry",
    new Object[] { 10 },
    new String[] { "int" }
);

server.invoke(
    name, "retry",
    new Object[] { "job-42" },
    new String[] { "java.lang.String" }
);
```

Một số client UI có thể hiển thị nhiều operation cùng tên và phân biệt bằng kiểu tham số. Với hợp đồng vận hành cần dễ sử dụng, nên cân nhắc tên cụ thể hơn như `retryUpTo` và `retryById` thay vì overload phức tạp.

Tránh overload dùng những kiểu gần nhau như `int`, `Integer`, `long` nếu người dùng chủ yếu thao tác qua JConsole/JMC. Chữ ký sai dẫn đến `ReflectionException` hoặc lỗi invocation tương ứng tùy MBean/exporter.

## 8. Kiểu dữ liệu nào phù hợp với JMX operation?

Một operation có thể nhận và trả primitive, wrapper, String, ObjectName và các kiểu phức tạp tùy hợp đồng MBean. Nhưng đối với remote JMX client, kiểu domain tùy ý có thể gây khó khăn:

```java
@ManagedOperation
public Result submit(InternalRequest request) { /* ... */ }
```

Vấn đề có thể là client không có class `InternalRequest`, object không serialization được hoặc công cụ không biết tạo instance làm tham số.

Ưu tiên API quản trị nhỏ:

```java
@ManagedOperation(description = "Cancels a pending job by its ID")
public boolean cancelJob(String jobId) { /* ... */ return false; }
```

Với dữ liệu có cấu trúc, cân nhắc MXBean/Open Types hoặc một API chuyên dụng (REST, messaging) nếu người dùng cần gửi payload phức tạp. `@ManagedOperation` trên một method của class Spring không tự chuyển mọi kiểu domain thành `CompositeData`.

Nguyên tắc thiết kế:

1. Giữ tham số dễ nhập từ công cụ JMX.
2. Dùng tên và đơn vị rõ ràng: `timeoutMillis`, `maxItems`.
3. Trả kết quả có thể giải thích được, ví dụ `boolean`, `int`, `String`.
4. Không trả dữ liệu cá nhân hoặc secret.
5. Hạn chế các cấu trúc lớn vì chi phí serialization, bộ nhớ và mạng.

## 9. Visibility và proxy: phương thức nào thực sự được phơi bày?

Spring bean có thể được bọc bằng JDK dynamic proxy hoặc CGLIB/class-based proxy do AOP, transaction, security hoặc tracing.

```text
JMX client
    |
    v
Exported MBean metadata
    |
    v
Spring proxy (nếu được export)
    |
    v
Target method
```

Nếu annotation nằm trên target nhưng JDK proxy chỉ triển khai interface không chứa method quản trị, exporter có thể không thể gọi method hoặc metadata không phản ánh đúng kỳ vọng. Ngược lại, nếu exporter đăng ký trực tiếp target để tránh proxy thì lời gọi JMX có thể bỏ qua transaction/security advice.

Cách tiếp cận bền vững là tạo adapter quản trị:

```java
public interface BillingService {
    void pauseProcessing();
}

@ManagedResource(
    objectName = "com.example.billing:type=Admin",
    description = "Billing processing controls"
)
public class BillingAdmin {
    private final BillingService service;

    public BillingAdmin(BillingService service) {
        this.service = service;
    }

    @ManagedOperation(
        description = "Pauses the billing service through its normal proxy"
    )
    public void pause() {
        service.pauseProcessing();
    }
}
```

Nếu `BillingService` được Spring inject dưới dạng proxy, adapter gọi qua interface đó và giữ được cơ chế advice có hiệu lực. Export adapter thay vì trực tiếp xuất toàn bộ service nghiệp vụ.

**Lưu ý:** Method `private`, `protected` hoặc `final` không nên được giả định có thể export/call qua JMX giống method public. Mô hình metadata và proxy khác nhau có giới hạn khác nhau; interface quản trị nên có các method public với chữ ký đơn giản.

## 10. Tác động vận hành và bảo mật

Một operation JMX là một điểm điều khiển có thể tác động trực tiếp đến application. Ví dụ nguy hiểm:

```java
@ManagedOperation
public void purgeQueue() {
    // Xóa dữ liệu queue
}
```

Nếu không giới hạn quyền và không có cơ chế xác nhận phù hợp, người có kết nối JMX có thể gọi thao tác này.

Quy tắc an toàn:

- Chỉ công bố những thao tác thật sự cần vận hành.
- Áp dụng authentication, authorization và TLS cho remote JMX theo môi trường.
- Giới hạn truy cập cổng JMX trong mạng tin cậy, không mở Internet công khai.
- Kiểm tra tham số và hạn mức thực thi ngay trong implementation.
- Ghi log/audit những thao tác quan trọng, phù hợp với chính sách hệ thống.
- Không đặt operation `deleteAll`, `shutdown`, `resetDatabase` vào interface chung nếu không có nhu cầu và bảo vệ rõ ràng.
- Phân biệt operation quan sát (query) với operation thay đổi trạng thái (action).
- Không dựa vào `description`, `impact` hay tên method như cơ chế phân quyền.

Nếu code có Spring Security method advice, xác nhận đường gọi JMX đi qua proxy bảo mật hoặc có lớp authorization độc lập ở ranh giới JMX.

## 11. Operation chạy lâu: thiết kế bất đồng bộ

JMX invocation về bản chất là lời gọi có thể đồng bộ và chặn client cho đến khi method hoàn tất. Nếu `reindexAll()` mất nhiều phút, JMX client có thể timeout hoặc người dùng không biết công việc đang tiến triển.

Một mẫu tốt hơn:

```java
@ManagedResource(
    objectName = "com.example.search:type=ReindexAdmin",
    description = "Controls background search reindexing"
)
public class ReindexAdmin {
    private volatile String state = "IDLE";

    @ManagedAttribute(description = "IDLE, RUNNING or FAILED")
    public String getState() {
        return state;
    }

    @ManagedOperation(description = "Starts a background reindex job")
    public String startReindex() {
        // Demo: triển khai thật cần executor/job manager và khóa chống chạy trùng.
        state = "RUNNING";
        return "job-accepted";
    }
}
```

Đây chỉ là skeleton cho API quản trị. Bản triển khai production cần thật sự giao việc cho executor/job system và cập nhật `state` theo lifecycle; không được coi việc đổi biến sang `RUNNING` là đã chạy task.

Mẫu thực tế:

1. Operation `startReindex()` kiểm tra quyền, tính hợp lệ và trạng thái hiện tại.
2. Operation trả về nhanh cùng job ID hoặc mã trạng thái.
3. Job chạy ở background worker/executor.
4. Attribute `State`, `ProgressPercent`, `LastError` cung cấp trạng thái.
5. Nếu cần, MBean phát notification khi job kết thúc.
6. Có quy trình dừng/hủy và tránh tạo nhiều job trùng.

Nếu operation chặn lâu, tài nguyên thread JMX connector và công cụ quản trị có thể bị ảnh hưởng.

## 12. Kiểm tra trực tiếp qua Spring integration test

Có thể khởi tạo context với `@EnableMBeanExport`, sau đó xác minh operation xuất hiện và gọi được:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.lang.management.ManagementFactory;
import javax.management.*;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class RetryAdminJmxTest {
    @Test
    void exportsAndInvokesOperation() throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
            "com.example.jobs:type=RetryAdmin,name=Billing"
        );

        try (var context = new AnnotationConfigApplicationContext(
                JmxConfiguration.class, RetryAdminConfig.class)) {

            assertTrue(server.isRegistered(name));

            Object value = server.invoke(
                name,
                "retryFailed",
                new Object[] { 5 },
                new String[] { "int" }
            );

            assertEquals(3, value);
        }
    }
}
```

Cấu hình bean được đưa vào context:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RetryAdminConfig {
    @Bean
    public RetryAdmin retryAdmin() {
        return new RetryAdmin();
    }
}
```

Test giả định exporter thực sự đăng ký vào platform `MBeanServer`; nếu dùng server khác, hãy inject server đó. Test không nên chạy song song với context khác đăng ký cùng ObjectName vì có thể gây `InstanceAlreadyExistsException`.

Một test tốt cũng có thể kiểm tra tên, parameter signature và description trong `MBeanInfo`, rồi xác nhận MBean được unregister khi context đóng.

## 13. Xử lý lỗi phổ biến

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| JConsole không thấy method | Chưa gắn `@ManagedOperation`, exporter chưa bật hoặc metadata assembler khác | Kiểm tra annotation, exporter, `MBeanInfo` |
| MBean không xuất hiện | `@ManagedResource` thiếu/không được phát hiện; ObjectName sai; server khác | Kiểm tra context, JMX server và log |
| `InstanceAlreadyExistsException` | Hai exporter đăng ký trùng ObjectName | Chọn một cơ chế đăng ký có owner |
| `NotCompliantMBeanException` | Hợp đồng MBean không phù hợp hoặc proxy bị ảnh hưởng | Dùng annotation exporter/adapter/StandardMBean theo đúng trường hợp |
| `ReflectionException` khi invoke | Tên operation hoặc chữ ký tham số không khớp | Lấy signature từ `MBeanOperationInfo` |
| `MBeanException` khi invoke | Method thực thi đã ném exception | Kiểm tra root cause và validation |
| `SecurityException` hoặc từ chối quyền | Client không đủ quyền hoặc bảo mật JMX chặn | Xem cấu hình authorization/authentication |
| Operation không chạy qua aspect | Target bị đăng ký thay vì proxy | Export adapter hoặc đảm bảo delegate là proxy |
| UI không nhập được tham số | Kiểu phức tạp hoặc client không hỗ trợ | Giản lược signature, cân nhắc Open Types |
| Operation timeout | Thực thi lâu/chặn thread | Trả nhanh và dùng job bất đồng bộ |

Khi chẩn đoán, nên bắt đầu từ ba câu hỏi: **MBean đã được đăng ký chưa? Operation có trong metadata không? Chữ ký invocation có khớp không?**

## 14. Checklist thiết kế @ManagedOperation

Trước khi xuất method thành JMX operation, cân nhắc:

1. **Mục đích:** operation có phục vụ observability hoặc quản trị thực sự không?
2. **Phạm vi:** tác động tới một resource, một JVM hay cả cluster?
3. **Tên:** có rõ động từ và đối tượng không (ví dụ `pauseProcessing` thay vì `action1`)?
4. **Tham số:** có giới hạn kiểu, số lượng và miền giá trị không?
5. **Kết quả:** client biết operation thành công/thất bại như thế nào?
6. **Tác động:** có ảnh hưởng dữ liệu, lưu lượng hoặc khả dụng của dịch vụ không?
7. **Quyền:** ai được phép gọi, có audit phù hợp không?
8. **Độ trễ:** method có nhanh hoặc dùng job bất đồng bộ nếu chạy lâu không?
9. **Phiên bản:** đổi tên/kiểu tham số có làm hỏng client tự động không?
10. **Metadata:** mô tả được hiển thị hữu ích trong JConsole/JMC không?

## 15. Bài tập thực hành

1. Tạo `@ManagedResource` tên `com.example:type=Worker,name=Background`, thêm attribute `ActiveWorkers` và operation `pause()`/`resume()`.
2. Tạo operation `retryFailed(int maxCount)`, mô tả tham số bằng `@ManagedOperationParameters`, rồi gọi qua `MBeanServer.invoke`.
3. Thử gọi operation với signature `"java.lang.Integer"` thay vì `"int"` và quan sát lỗi do chữ ký không khớp.
4. Overload `retry(int)` và `retry(String)`; dùng metadata để lấy hai signature và gọi từng operation.
5. Thử công bố operation nhận một domain DTO phức tạp; so sánh khả năng dùng từ JConsole/JMC với operation chỉ nhận String/int.
6. Tạo một adapter MBean gọi qua Spring AOP proxy; xác nhận advice hoạt động khi operation được gọi từ JMX.
7. Viết test kiểm tra operation xuất hiện trong `MBeanInfo`, gọi thành công, và MBean được hủy đăng ký sau khi context đóng.

## 16. Câu hỏi tự kiểm tra

- `@ManagedOperation` khác `@ManagedAttribute` như thế nào?
- Vì sao class có `@ManagedResource` vẫn cần exporter hoạt động?
- Tại sao `MBeanServer.invoke` cần cả tên operation lẫn signature?
- `@ManagedOperationParameter` có tự thực thi giới hạn tham số không?
- Khi nào nên dùng operation bất đồng bộ thay vì xử lý lâu ngay trong lời gọi JMX?
- Proxy AOP có thể ảnh hưởng đường gọi của operation thế nào?
- Vì sao một method có `@ManagedOperation` chưa chắc an toàn để mở cho mọi JMX client?

**Ghi nhớ:** `@ManagedOperation` là cách Spring đánh dấu method được xuất thành JMX operation thông qua exporter có cấu hình annotation phù hợp. Hãy xuất có chọn lọc, mô tả rõ tác động, dùng chữ ký và kiểu dữ liệu tương thích với client, validate tham số, áp dụng bảo mật riêng cho JMX, và xác minh metadata cùng khả năng gọi thực tế qua `MBeanServer`.