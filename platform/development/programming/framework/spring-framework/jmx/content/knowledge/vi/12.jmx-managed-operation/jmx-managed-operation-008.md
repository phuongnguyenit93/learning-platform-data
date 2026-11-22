# Phân biệt operation điều khiển với endpoint nghiệp vụ trong Spring Framework JMX

## 1. Mục tiêu bài học

Trong Spring Framework JMX, annotation `@ManagedOperation` cho phép công bố một phương thức của Spring bean như **operation quản trị** trên MBean. Một operation có thể khởi động lại bộ đếm, bật chế độ chẩn đoán, làm mới cache hoặc yêu cầu một công việc vận hành được kiểm soát.

Trong khi đó, **endpoint nghiệp vụ** — thường là HTTP REST endpoint, GraphQL resolver, gRPC method hoặc message handler — giải quyết yêu cầu của người dùng và quy trình kinh doanh như tạo đơn hàng, thanh toán, truy vấn sản phẩm hay đổi thông tin tài khoản. Cả hai loại interface đều có thể gọi Java method và thay đổi trạng thái ứng dụng, nhưng **mục đích, người gọi, hợp đồng, bảo mật, vòng đời và mức độ phơi bày** khác nhau.

Bài học giúp bạn:

- Phân biệt `@ManagedOperation` với `@RestController`/`@PostMapping` và các giao diện nghiệp vụ khác.
- Hiểu khi nào nên công bố một hành động qua JMX thay vì HTTP API.
- Thiết kế các thao tác quản trị có kiểm soát, an toàn khi thực hiện lại và có kết quả quan sát được.
- Dùng Spring `MBeanExporter` và metadata để xuất operation.
- Gọi operation bằng `MBeanServer.invoke(...)` với ObjectName và chữ ký tham số phù hợp.
- Tránh biến JMX thành API nghiệp vụ ngầm hoặc tạo backdoor vượt qua phân quyền.

## 2. Hai loại giao diện giải quyết hai vấn đề

### 2.1. Operation điều khiển (management operation)

Operation quản trị phục vụ **vận hành và quản trị hệ thống**, chẳng hạn:

- `clearCache()`: làm rỗng cache khi dữ liệu bị stale.
- `resetCounters()`: đặt lại số liệu thống kê phục vụ chẩn đoán.
- `enableDiagnostics(boolean)`: bật/tắt mức thu thập thông tin chẩn đoán.
- `reloadConfiguration()`: yêu cầu nạp lại cấu hình động đã được phê duyệt.
- `pauseScheduler()` / `resumeScheduler()`: kiểm soát xử lý nền.
- `dumpPoolStatus()`: lấy thông tin trạng thái một pool ở thời điểm kiểm tra.

JMX operation là một phần của **giao diện quản trị MBean**, được gọi bằng một `ObjectName` và tên operation. Nó không tự cung cấp URL HTTP.

### 2.2. Endpoint nghiệp vụ (business endpoint)

Endpoint nghiệp vụ phục vụ use case của người dùng hoặc hệ thống đối tác:

- `POST /orders`: tạo đơn hàng theo quy tắc nghiệp vụ.
- `POST /payments`: xử lý thanh toán.
- `GET /catalog/products`: truy vấn danh mục.
- `PATCH /customers/{id}`: cập nhật hồ sơ khách hàng.
- `POST /subscriptions/{id}/cancel`: hủy đăng ký theo quyền của tài khoản.

Những endpoint này thường có request/response schema, cơ chế nhận diện người gọi, quyền nghiệp vụ, validation và semantics giao thức HTTP/gRPC/message. Chúng thường cần API versioning, rate limiting và audit theo đối tượng kinh doanh.

### 2.3. So sánh nhanh

| Tiêu chí | JMX management operation | Endpoint nghiệp vụ |
| --- | --- | --- |
| Mục đích | Vận hành, chẩn đoán, điều khiển runtime | Thực hiện use case kinh doanh |
| Người gọi | Operator, hệ thống monitoring/automation được ủy quyền | Người dùng, frontend, dịch vụ/đối tác |
| Đường vào | `MBeanServer.invoke(...)`, JConsole, JMX client | HTTP, gRPC, message, GraphQL... |
| Định danh | `ObjectName` + operation name/signature | Route/method, service/method hoặc message type |
| Contract | `MBeanInfo`, `MBeanOperationInfo` | OpenAPI/IDL/schema/domain contract |
| Bảo mật | JMX connector/agent, network, role/quyền quản trị | Authentication/authorization cấp người dùng và tài nguyên |
| Hệ quả | Thường tác động hạ tầng hoặc cấu hình runtime | Tạo/thay đổi/truy vấn dữ liệu nghiệp vụ |
| Khả năng công khai | Thường giới hạn nội bộ và đặc quyền cao | Có thể public hoặc internal theo thiết kế |

Sự khác biệt không phải “method có tham số hay không”, “có thay đổi dữ liệu hay không” hoặc “có chạy trong Spring hay không”. Khác biệt nằm ở **vai trò của hành động trong mô hình hệ thống**.

## 3. @ManagedOperation không phải @RequestMapping

Ví dụ Spring JMX:

```java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.ops:type=CacheControl,name=Primary",
    description = "Administrative cache controls"
)
public class CacheControl {

    @ManagedOperation(
        description = "Clear the application cache"
    )
    public void clearCache() {
        // Thao tác quản trị
    }
}
```

Client JMX có thể yêu cầu:

```java
server.invoke(
    objectName,
    "clearCache",
    new Object[0],
    new String[0]
);
```

Còn ví dụ endpoint HTTP:

```java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public ResponseEntity<OrderResult> createOrder(
            CreateOrderRequest request) {
        OrderResult result = orderService.createOrder(request);
        return ResponseEntity.ok(result);
    }
}
```

Đoạn controller minh họa ngữ nghĩa nghiệp vụ; trong ứng dụng thật cần `@RequestBody`, DTO, validation và xử lý lỗi phù hợp. `@PostMapping` được ánh xạ sang HTTP route thông qua Spring MVC, còn `@ManagedOperation` được Spring JMX assembler diễn giải để xây dựng MBean operation metadata.

**Không thể dùng URL HTTP để gọi một JMX operation nếu không xây thêm lớp chuyển đổi riêng.** Tương tự, gắn `@ManagedOperation` lên một method không tự tạo REST endpoint.

## 4. Vị trí của @ManagedOperation trong mô hình JMX

```text
Spring ApplicationContext
        |
        +-- Bean @ManagedResource
        |      +-- @ManagedAttribute: trạng thái quản trị
        |      +-- @ManagedOperation: hành động quản trị
        |
        +-- AnnotationJmxAttributeSource
        +-- MetadataMBeanInfoAssembler
        +-- MBeanExporter
                   |
                   v
               MBeanServer
                   |
                 ObjectName
                   |
                   v
       MBeanOperationInfo / invoke(...)
```

Một `@ManagedResource` mô tả bean quản trị. `@ManagedOperation` đánh dấu phương thức được export thành operation; `@ManagedAttribute` mô tả getter/setter xuất thành attribute. Spring `MBeanExporter` đưa bean vào `MBeanServer`, với metadata assembler hoặc cấu hình annotation-driven phù hợp.

Chỉ đặt annotation trên một class không đồng nghĩa method được công bố: instance phải có trong Spring context, exporter phải chạy, assembler phải sử dụng metadata annotation và ObjectName phải hợp lệ.

## 5. Khi nào một thao tác nên là JMX operation?

Một phép thử thiết kế hữu ích:

1. **Ai là người được phép thực hiện?** Nếu chỉ operator hoặc automation vận hành được ủy quyền, JMX là một lựa chọn.
2. **Đối tượng chịu tác động là runtime hay tài nguyên nghiệp vụ?** Điều khiển cache, thread pool, scheduler thường là vận hành. Tạo đơn hàng hoặc hủy thanh toán là nghiệp vụ.
3. **Có cần API contract công khai, API versioning hay client đa nền tảng không?** Nếu có, API nghiệp vụ thường hợp lý hơn.
4. **Có yêu cầu audit nghiệp vụ, idempotency key hoặc kiểm soát quyền theo tài khoản không?** Khi có, nên đi qua application service và business API thiết kế đúng.
5. **Thao tác có thể làm giảm tính sẵn sàng hoặc bảo mật?** Nếu có, phải giảm phạm vi quản trị, phân quyền và hạn chế phơi bày.
6. **Kết quả có thể được quan sát sau khi chạy không?** JMX operation nên có trạng thái/attribute hỗ trợ kiểm tra kết quả, đặc biệt khi thao tác bất đồng bộ.

Ví dụ `clearCache()` thường là operation vận hành, còn `purchaseItem(customerId, itemId)` là use case nghiệp vụ. Không nên export `purchaseItem` chỉ vì “JConsole gọi được rất tiện”.

## 6. Thiết kế cấu trúc lớp tách biệt

Một thiết kế rõ ràng đặt logic dùng chung trong service, còn lớp JMX và HTTP chỉ là adapter với quyền riêng.

```text
             +------------------+
             |   CacheService   |
             | clear / metrics  |
             +------------------+
                    ^      ^
                    |      |
          +---------+      +------------------+
          |                                |
  JMX CacheControl                  Business API adapter
  @ManagedResource                  @RestController
  @ManagedOperation                 route nghiệp vụ
  dùng cho operator                 dùng cho client
```

Ví dụ service:

```java
package com.example.cache;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Service;

@Service
public class CacheService {

    private final AtomicLong clearCount = new AtomicLong();

    public void clear() {
        // Gọi lớp cache thật để xóa dữ liệu cache.
        clearCount.incrementAndGet();
    }

    public long getClearCount() {
        return clearCount.get();
    }
}
```

JMX adapter:

```java
package com.example.cache;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.cache:type=CacheControl,name=Primary",
    description = "Operational control of the primary cache"
)
public class CacheControl {

    private final CacheService cacheService;

    public CacheControl(CacheService cacheService) {
        this.cacheService = cacheService;
    }

    @ManagedOperation(description = "Evict all cached entries")
    public void clearCache() {
        cacheService.clear();
    }

    @ManagedAttribute(description = "Number of cache clear requests")
    public long getClearCount() {
        return cacheService.getClearCount();
    }
}
```

Cách này giúp lớp quản trị chỉ có hai khả năng được chủ động công bố: một operation thay đổi cache và một attribute đọc thống kê. Các phương thức nghiệp vụ của service khác vẫn có thể dùng `CacheService`, nhưng không bị export tràn lan qua JMX.

Nguyên tắc: **không nên cho controller HTTP gọi thẳng JMX chỉ để tái sử dụng một operation**. Nếu cùng logic được nhiều adapter dùng, đưa logic vào application/service layer, còn adapter chỉ chuyển yêu cầu theo contract và quyền phù hợp.

## 7. Export operation bằng Spring

Cấu hình annotation-driven thường sử dụng `@EnableMBeanExport`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxExportConfiguration {
}
```

Khi hạ tầng này được bật trong context chứa bean `CacheControl`, Spring có thể xuất các managed resource được đánh dấu bằng annotation. Môi trường thực tế phải cấu hình `MBeanServer` thích hợp và lưu ý registration policy, ObjectName, quyền truy cập.

Có thể cấu hình thủ công để thấy rõ assembler:

```java
import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.metadata.AnnotationJmxAttributeSource;

@Configuration
public class ExplicitJmxConfiguration {

    @Bean
    MBeanServer jmxServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    AnnotationJmxAttributeSource jmxAttributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    MetadataMBeanInfoAssembler jmxAssembler(
            AnnotationJmxAttributeSource source) {
        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);
        return assembler;
    }

    @Bean
    MBeanExporter cacheExporter(
            CacheControl control,
            MetadataMBeanInfoAssembler assembler,
            MBeanServer jmxServer) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(jmxServer);
        exporter.setAssembler(assembler);
        exporter.setBeans(Map.of(
            "com.example.cache:type=CacheControl,name=Primary",
            control
        ));
        return exporter;
    }
}
```

Đây là **hai lựa chọn** cấu hình, không phải hai cơ chế cần bật đồng thời cho cùng MBean. Nếu vừa dùng `@EnableMBeanExport` vừa tạo exporter thủ công cùng ObjectName, có thể gặp đăng ký trùng.

## 8. Gọi operation bằng MBeanServer.invoke

JMX client gọi operation không qua HTTP verb hay route, mà qua:

```java
Object invoke(
    ObjectName name,
    String operationName,
    Object[] params,
    String[] signature
);
```

Ví dụ:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.cache:type=CacheControl,name=Primary"
);

server.invoke(
    name,
    "clearCache",
    new Object[0],
    new String[0]
);
```

Hai mảng rỗng vì `clearCache()` không nhận tham số. Client phải kết nối đúng `MBeanServer` đã nhận đăng ký MBean; một ObjectName giống nhau trong server khác không chỉ cùng đối tượng.

### 8.1. Operation có tham số

Một operation có thể cho phép đặt chế độ chẩn đoán:

```java
@ManagedOperation(
    description = "Set diagnostic collection mode"
)
public void setDiagnostics(boolean enabled) {
    diagnosticService.setEnabled(enabled);
}
```

JMX client gọi:

```java
server.invoke(
    name,
    "setDiagnostics",
    new Object[] { Boolean.TRUE },
    new String[] { "boolean" }
);
```

Giá trị trong `signature` là tên kiểu Java của tham số được khai báo, không phải tên hiển thị hay tên field trong JSON. Với overload, signature giúp phân biệt đúng phương thức. Cần đảm bảo operation đã được export với chữ ký tương ứng.

### 8.2. Operation trả kết quả

```java
@ManagedOperation(
    description = "Return current diagnostic status"
)
public String diagnosticStatus() {
    return diagnosticService.status();
}
```

```java
Object raw = server.invoke(
    name,
    "diagnosticStatus",
    new Object[0],
    new String[0]
);

String status = (String) raw;
```

Khi thiết kế return type, cân nhắc khả năng biểu diễn dữ liệu qua JMX connector, đặc biệt khi client ở JVM khác. Nhiều lớp domain phức tạp có thể gây khó khăn khi serialization hoặc khi client thiếu class tương ứng. Với contract quản trị, thường ưu tiên kiểu đơn giản hoặc Open MBean types thích hợp.

## 9. Khám phá operation metadata

`MBeanServer.getMBeanInfo(...)` cho phép liệt kê operation đã export:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.printf(
        "Operation: %s, return=%s, impact=%d%n",
        op.getName(),
        op.getReturnType(),
        op.getImpact()
    );

    for (MBeanParameterInfo param : op.getSignature()) {
        System.out.printf(
            "  param=%s type=%s description=%s%n",
            param.getName(),
            param.getType(),
            param.getDescription()
        );
    }
}
```

`MBeanOperationInfo` mô tả name, return type, signature, description và impact classification. Spring annotation metadata có thể đóng góp các mô tả và thông tin impact, tùy assembler được sử dụng.

Impact classification trong JMX là metadata giúp mô tả bản chất operation, chẳng hạn action, info hoặc action/info; **không phải** hệ thống phân quyền thực thi. Một operation được gắn là informational vẫn phải được đánh giá bảo mật và side effect thực tế.

Một operation không có trong `MBeanInfo.getOperations()` thì client không thể giả định nó callable qua JMX chỉ vì phương thức đó tồn tại trên class Java.

## 10. Bảo mật: không dùng JMX làm đường vòng nghiệp vụ

Một lỗi kiến trúc nguy hiểm là xuất operation cho phép làm nghiệp vụ với đặc quyền cao chỉ vì JMX dễ gọi trong JConsole.

Ví dụ không nên:

```java
@ManagedOperation
public void transferMoney(
        String sourceAccount,
        String destinationAccount,
        long amount) {
    paymentService.transfer(sourceAccount, destinationAccount, amount);
}
```

Nếu được export, operation này có thể bỏ qua một phần contract HTTP: user identity, anti-fraud check, authorization theo tài khoản, idempotency key, audit, validation và gateway policy. Dù service bên dưới có bảo vệ một số quy tắc, việc mở thêm một lối gọi quản trị vẫn mở rộng bề mặt tấn công và khả năng thao tác sai.

Nguyên tắc:

- Không export method chỉ vì nó hữu ích cho debugging.
- Chỉ công bố thao tác vận hành thực sự cần thiết.
- Bảo vệ remote JMX với xác thực, mã hóa và giới hạn mạng phù hợp.
- Thiết kế quyền quản trị riêng, không giả định chỉ cần “ở mạng nội bộ” là an toàn.
- Cân nhắc audit theo operator, mục tiêu, thời gian, tham số phi nhạy cảm và kết quả.
- Không ghi token, mật khẩu hoặc dữ liệu khách hàng vào notification, error message hoặc JMX attribute.
- Đối với thao tác có tác động lớn, cân nhắc dùng workflow phê duyệt thay vì cho phép gọi trực tiếp.

Có những tác vụ “nghiệp vụ” vẫn do hệ thống nội bộ thực hiện, và có những tác vụ vận hành được expose qua HTTP admin API. **Tên giao thức không tự quyết định bản chất**, nhưng nên giữ ranh giới trách nhiệm và quyền truy cập rõ ràng.

## 11. Idempotency, retry và side effect

Một management operation có thể được gọi lại vì operator không nhìn thấy kết quả, mạng bị ngắt hoặc automation retry. Thiết kế nên xác định rõ:

- Gọi hai lần có an toàn không?
- Nếu lần đầu đang chạy, lần thứ hai trả gì?
- Operation chạy đồng bộ hay chỉ tạo yêu cầu bất đồng bộ?
- Thời gian chờ và trạng thái tiến trình được quan sát ra sao?
- Có cơ chế khóa hoặc từ chối khi hệ thống không ở trạng thái phù hợp không?

Ví dụ `clearCache()` thường có thể gọi lặp lại mà không làm hỏng dữ liệu (dù tốn tài nguyên). Nhưng `rebuildIndex()` có thể tiêu thụ nhiều CPU và I/O, cần tránh khởi chạy trùng.

Mẫu trạng thái quản trị:

```java
@ManagedAttribute(description = "Whether a rebuild is running")
public boolean isRebuildRunning() {
    return rebuildRunning.get();
}

@ManagedOperation(description = "Request a rebuild")
public String requestRebuild() {
    if (!rebuildRunning.compareAndSet(false, true)) {
        return "ALREADY_RUNNING";
    }
    rebuildExecutor.submit(() -> {
        try {
            rebuildIndex();
        } finally {
            rebuildRunning.set(false);
        }
    });
    return "STARTED";
}
```

Đây là ví dụ logic minh họa, giả định các field `rebuildRunning` và `rebuildExecutor` đã được cấu hình. Trong hệ thống thật, cần xử lý trường hợp `submit` thất bại để không giữ cờ `running` vĩnh viễn và cung cấp kết quả cuối cùng của công việc.

Đối với operation chạy lâu, đừng buộc client giữ kết nối chờ vô hạn. Có thể trả request ID, công bố trạng thái qua attribute hoặc cung cấp notification khi hoàn tất. Khi cần workflow quan trọng với durability và recovery, thường phải dùng hàng đợi và job orchestration thích hợp thay vì chỉ dựa vào lời gọi JMX.

## 12. Validation và hợp đồng tham số

Đừng mặc định rằng dùng JMX thì có thể bỏ validation. Trên đường gọi `MBeanServer.invoke`, tham số đến từ client quản trị và có thể sai kiểu hoặc vượt giới hạn nghiệp vụ kỹ thuật.

Ví dụ điều chỉnh số worker:

```java
@ManagedOperation(
    description = "Resize the worker pool within approved limits"
)
public void resizeWorkers(int requested) {
    if (requested < 1 || requested > 64) {
        throw new IllegalArgumentException(
            "Worker count must be between 1 and 64"
        );
    }
    workerPool.resize(requested);
}
```

Validation đặt trong lớp điều khiển hoặc service vẫn cần thiết. Annotation metadata có thể mô tả tham số, nhưng không tự đảm bảo toàn bộ giới hạn được thực thi.

Đối với endpoint nghiệp vụ, validation còn bao gồm quyền theo tenant/user, dữ liệu domain, workflow state và consistency transaction. Không nên chuyển phần logic đó sang JMX adapter để “giảm code”.

## 13. Quan sát kết quả của operation

JMX operation không chỉ cần khả năng khởi chạy. Client vận hành còn cần biết hành động có thành công không và trạng thái hiện tại thế nào.

Các cách thường dùng:

1. **Giá trị trả về:** thích hợp cho hành động nhanh, trả một kết quả rõ ràng.
2. **ManagedAttribute:** cung cấp `Running`, `LastRunTime`, `LastOutcome`, `ErrorCount`.
3. **Notification:** phát khi hành động bắt đầu/hoàn tất/thất bại, nếu MBean hỗ trợ broadcaster/publisher.
4. **Log và tracing:** dùng correlation ID và thông tin vận hành phi nhạy cảm.
5. **Hệ thống job riêng:** cho tác vụ lâu dài, có retry/persistence/approval.

Ví dụ phần trạng thái:

```java
@ManagedAttribute(description = "Last reload result")
public String getLastReloadOutcome() {
    return lastReloadOutcome;
}

@ManagedOperation(description = "Reload operational settings")
public String reloadConfiguration() {
    try {
        configurationService.reload();
        lastReloadOutcome = "SUCCESS";
        return "SUCCESS";
    } catch (RuntimeException ex) {
        lastReloadOutcome = "FAILED";
        throw ex;
    }
}
```

Với hệ thống thật, nên bảo vệ truy cập đồng thời tới `lastReloadOutcome` và tránh trả chi tiết lỗi nhạy cảm. Trạng thái `SUCCESS` cũng cần được định nghĩa rõ: đã nhận yêu cầu, đã áp dụng cấu hình, hay tất cả downstream đã nhận?

## 14. Tình huống thiết kế

### 14.1. Xóa cache có nên dùng JMX?

Có thể, nếu chỉ operator được phép xóa cache và hành động tác động trạng thái runtime. Nếu business workflow cần invalidation cache theo một sự kiện domain, logic nên gọi service/cache abstraction từ luồng nghiệp vụ, không “đi vòng” qua JMX.

### 14.2. Reconcile đơn hàng có nên là JMX operation?

Nếu reconcile là công việc nghiệp vụ quan trọng cần audit theo đối tượng, kết quả theo batch, retry và kiểm soát dữ liệu, nên thiết kế như một job/workflow nghiệp vụ có hợp đồng nội bộ rõ ràng. JMX có thể cung cấp **thông tin sức khỏe** hoặc **yêu cầu vận hành hẹp** liên quan, nhưng không nên biến `reconcileOrder(orderId)` thành API nghiệp vụ bí mật.

### 14.3. Bật chế độ debug có nên là JMX operation?

Có thể hợp lý trong môi trường cho phép quản trị viên bật debug tạm thời. Tuy nhiên cần cân nhắc thời hạn tự tắt, chi phí thu thập, rò rỉ dữ liệu trong log và audit của thao tác.

### 14.4. Thay đổi giá bán có nên dùng JMX?

Không phải lựa chọn thông thường. Đó là một thay đổi nghiệp vụ cần quy trình phê duyệt, quyền theo vai trò, event, lịch sử thay đổi và consistency. Đặt nó trong business API/workflow phù hợp sẽ dễ quản trị hơn.

## 15. Các lỗi thường gặp khi export và gọi operation

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy MBean | Sai ObjectName/server, exporter chưa chạy | Kiểm tra `isRegistered`, lifecycle và `setServer` |
| Operation không có trong JConsole | Thiếu `@ManagedOperation` hoặc assembler không đọc metadata | Kiểm tra `MBeanInfo.getOperations()` |
| `ReflectionException` | Chữ ký/tham số không tương ứng operation được công bố | So sánh method name, signature types |
| `MBeanException` | Method quản trị phát sinh lỗi được JMX bao bọc | Kiểm tra nguyên nhân gốc, validation, side effect |
| Không thấy thay đổi sau khi gọi | Operation bất đồng bộ, xử lý nền hoặc sai instance | Đọc attribute trạng thái và xác nhận target |
| Client remote không gọi được | Connector, authentication hoặc authorization | Kiểm tra JMX Remote và cấu hình security |
| Xung đột ObjectName | Hai exporters cùng đăng ký một tên trong server | Đặt tên duy nhất, tránh duplicate exporter |
| Business API bị bypass | Đã export domain service method trực tiếp | Thu hẹp JMX adapter và bảo vệ invariant tại service |

`MBeanInfo` là công cụ khám phá interface quản trị thực tế, tránh suy đoán rằng mọi method public trên Java bean đều gọi được.

## 16. Bài tập thực hành

Tạo `CacheService` và `CacheControl` như phần 6, export qua `@EnableMBeanExport` hoặc `MBeanExporter` có metadata assembler.

Thực hiện theo thứ tự:

1. Khởi chạy Spring context chứa bean quản trị.
2. Xác nhận ObjectName `com.example.cache:type=CacheControl,name=Primary` có trong MBeanServer mong muốn.
3. Dùng `getMBeanInfo` liệt kê các operation và attribute.
4. Gọi `getAttribute(name, "ClearCount")` để đọc số lần clear.
5. Gọi `invoke(name, "clearCache", new Object[0], new String[0])`.
6. Đọc lại `ClearCount` và giải thích tại sao số lần clear tăng.
7. Thử gọi tên operation không được công bố, ví dụ `"deleteOrders"`, để quan sát lỗi.
8. Tạo endpoint nghiệp vụ `POST /orders` ở một controller riêng, gọi một `OrderService` theo hợp đồng nghiệp vụ; không export method này qua JMX.
9. Ghi lại các điểm khác biệt về quyền, validation, monitoring và consumer.

Mẫu kiểm tra ObjectName:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.cache:type=CacheControl,name=Primary"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException("MBean not registered: " + name);
}
```

Nếu ứng dụng dùng MBeanServer khác platform server, phải lấy đúng server được cấu hình cho exporter.

## 17. Câu hỏi tự kiểm tra

**1. `@ManagedOperation` tạo HTTP endpoint không?** Không. Nó mô tả operation được Spring JMX export vào MBean.

**2. `MBeanServer.invoke` định vị method như thế nào?** Bằng ObjectName, operation name, mảng tham số và signature.

**3. Có nên export `createOrder` làm JMX operation cho tiện test không?** Không nên; đây là use case nghiệp vụ cần contract và kiểm soát quyền riêng.

**4. Operation điều khiển có thể thay đổi state không?** Có. Ví dụ reset counter, clear cache hoặc điều chỉnh cấu hình runtime.

**5. Tại sao một method public có thể không xuất hiện trong JMX?** Assembler/metadata quyết định giao diện quản trị được công bố, không tự động xuất mọi method.

**6. Impact metadata có thay cho quyền thực thi không?** Không. Nó mô tả bản chất operation, không cấp phép hoặc từ chối lời gọi.

**7. Khi operation xử lý bất đồng bộ, client cần gì?** Trạng thái, ID công việc, kết quả cuối hoặc notification để theo dõi.

**8. Nếu JMX client gọi được một method, có nghĩa các kiểm soát HTTP vẫn áp dụng không?** Không. JMX có entry point và security riêng; invariant quan trọng phải được bảo vệ ở tầng service/domain thích hợp.

**9. Làm sao biết operation nào thực sự được export?** Đọc `MBeanInfo.getOperations()` từ server và ObjectName chính xác.

**10. Vì sao không dùng JMX làm API nghiệp vụ phụ?** Vì tạo thêm bề mặt gọi và nguy cơ bypass contract, phân quyền, audit, validation, vận hành và quản lý phiên bản.

## 18. Ghi nhớ

- **JMX operation** là giao diện **quản trị runtime**; **business endpoint** là giao diện thực hiện **use case nghiệp vụ**.
- `@ManagedOperation` công bố method qua Spring JMX; `@PostMapping` hay contract tương đương phục vụ HTTP/API nghiệp vụ.
- Cả hai có thể gọi chung một **service** khi thật sự phù hợp, nhưng phải giữ adapter và quyền truy cập tách biệt.
- Đừng export domain service method trực tiếp chỉ vì nó có thể giúp thao tác thủ công.
- Thiết kế JMX operation với validation, phạm vi hạn chế, audit, idempotency và kết quả quan sát được.
- `MBeanServer.invoke` cần đúng `ObjectName`, tên operation và signature; `MBeanInfo` cho biết interface thật sự được công bố.
- JMX Remote phải được bảo vệ như một kênh quản trị đặc quyền, không phải một API công khai thay thế business API.

Phân biệt rõ operation điều khiển với endpoint nghiệp vụ giúp Spring Framework JMX giữ đúng vai trò quản trị, đồng thời giúp các luồng nghiệp vụ tiếp tục tuân thủ hợp đồng, phân quyền và kiểm soát thay đổi cần thiết của hệ thống.