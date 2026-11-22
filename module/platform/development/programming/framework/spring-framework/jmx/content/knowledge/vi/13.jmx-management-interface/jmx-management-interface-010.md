# So sánh MBeanInfoAssembler với @ManagedAttribute và @ManagedOperation trong Spring Framework JMX

## 1. Vấn đề cần hiểu

Trong Spring Framework JMX, một Spring bean có thể được đưa vào `MBeanServer` để công cụ quản trị đọc trạng thái hoặc gọi thao tác. Tuy nhiên, **không phải mọi phương thức Java đều nên xuất hiện trên giao diện quản trị**.

Có hai khái niệm dễ bị đặt đối lập:

- **`MBeanInfoAssembler`**: thành phần của Spring tạo metadata `MBeanInfo` cho MBean từ class, interface, danh sách phương thức hoặc metadata.
- **`@ManagedAttribute` và `@ManagedOperation`**: các annotation khai báo một getter/setter hay một operation nên trở thành thành phần của giao diện quản trị.

Điểm mấu chốt: **assembler và annotation không phải hai cơ chế loại trừ nhau**. Annotation là **nguồn metadata**, còn một assembler phù hợp, thường là `MetadataMBeanInfoAssembler` kết hợp `AnnotationJmxAttributeSource`, đọc metadata đó để xây dựng `MBeanInfo`.

Một số assembler khác có thể công bố phương thức **không cần annotation**. Chẳng hạn `SimpleReflectiveMBeanInfoAssembler` dựa trên reflection, `MethodNameBasedMBeanInfoAssembler` dựa vào danh sách tên phương thức, và `InterfaceBasedMBeanInfoAssembler` dựa vào management interface được cấu hình.

## 2. Chuỗi xử lý từ Spring bean tới JMX client

```text
                        Spring bean
                            |
                  MBeanExporter chọn bean
                            |
                  MBeanInfoAssembler
                            |
          +-----------------+------------------+
          |                 |                  |
      Reflection       Method names        Metadata
          |                 |                  |
    Public methods       Allowlist       @ManagedResource
                                          @ManagedAttribute
                                          @ManagedOperation
          |                 |                  |
          +-----------------+------------------+
                            |
                   MBeanInfo metadata
             attributes / operations / info
                            |
                  ModelMBean + ObjectName
                            |
                        MBeanServer
                            |
                  JConsole / VisualVM / API
```

`MBeanExporter` chịu trách nhiệm export bean. `MBeanInfoAssembler` quyết định metadata của MBean được thích ứng. `ObjectNamingStrategy` quyết định `ObjectName`. Các thành phần này có nhiệm vụ khác nhau, dù có thể được cấu hình cùng nhau.

Spring sử dụng annotation-based export thuận tiện qua `@EnableMBeanExport`; cấu hình này thiết lập hạ tầng đọc metadata annotation và export bean phù hợp, nên ứng dụng thường không cần tự khai báo assembler. Nhưng `@ManagedAttribute` đứng độc lập trên method **không tự đăng ký** bean vào MBeanServer.

## 3. Phân biệt attribute và operation trước khi so sánh

Trong JMX:

- **Attribute** diễn tả trạng thái hoặc cấu hình. Client đọc bằng `getAttribute(ObjectName, "ActiveJobs")`, và chỉ ghi bằng `setAttribute` nếu attribute writable.
- **Operation** diễn tả hành động quản trị. Client gọi bằng `invoke(ObjectName, operationName, arguments, signature)`.
- **MBeanInfo** là metadata mô tả các attribute, operation, notification và thông tin kiểu dữ liệu.

Một Java method không trở thành attribute chỉ vì nó đọc field nội bộ. Theo quy ước JavaBean, `getActiveJobs()` hoặc `isEnabled()` có thể là accessor của attribute `ActiveJobs` hoặc `Enabled`. Một method `requestRefresh()` thường được xem là operation.

Ví dụ:

```java
public class WorkerService {
    private volatile boolean enabled = true;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public int getActiveJobs() {
        return 3;
    }

    public void requestRefresh() {
        // Gọi service cần thiết
    }

    public void deleteAllHistory() {
        // API nghiệp vụ nội bộ, không nên công bố mặc định
    }
}
```

Mục tiêu quản trị có thể chỉ là `Enabled` (read-only), `ActiveJobs` (read-only) và `requestRefresh()`. Cách lựa chọn assembler và annotation quyết định client thực sự nhìn thấy những gì.

## 4. MBeanInfoAssembler là chiến lược tạo metadata

Giao diện `org.springframework.jmx.export.assembler.MBeanInfoAssembler` định nghĩa vai trò tạo `ModelMBeanInfo` cho bean được export. Spring có những implementation phục vụ các cách công bố khác nhau.

| Cách chọn | Thành phần điển hình | Nguyên tắc |
| --- | --- | --- |
| Reflection | `SimpleReflectiveMBeanInfoAssembler` | Phản chiếu những public getter/setter và public methods theo quy tắc assembler |
| Danh sách tên | `MethodNameBasedMBeanInfoAssembler` | Chọn các phương thức có tên trong danh sách cấu hình |
| Loại trừ tên | `MethodExclusionMBeanInfoAssembler` | Phản chiếu nhưng loại phương thức được liệt kê |
| Interface quản trị | `InterfaceBasedMBeanInfoAssembler` | Chỉ expose method theo interface đã chọn |
| Annotation/metadata | `MetadataMBeanInfoAssembler` | Đọc metadata từ `JmxAttributeSource`, thường là `AnnotationJmxAttributeSource` |

Một assembler có thể chọn getter/setter để tạo attribute và method khác để tạo operation. Các assembler có chính sách khác nhau về method nào được đưa ra. Chúng không phải một cơ chế phân quyền runtime: **assembler quyết định bề mặt được công bố**, còn connector/MBeanServer quyết định client có quyền sử dụng bề mặt đó hay không.

### 4.1. SimpleReflectiveMBeanInfoAssembler

Thuận tiện khi class là một management adapter nhỏ với public API đúng mục tiêu. Tuy nhiên, class nghiệp vụ có nhiều public methods sẽ dễ công bố nhiều hơn dự định.

```java
MBeanExporter exporter = new MBeanExporter();
exporter.setAssembler(
    new SimpleReflectiveMBeanInfoAssembler()
);
```

Với `WorkerService` ở trên, không nên mặc định `deleteAllHistory()` được ẩn chỉ vì không có `@ManagedOperation`. Reflection assembler không sử dụng annotation làm danh sách cho phép.

### 4.2. MethodNameBasedMBeanInfoAssembler

Chọn những method có tên được nêu trong cấu hình. Đây là cách dùng allowlist ngoài class, hữu ích khi không muốn sửa source code bean.

```java
MethodNameBasedMBeanInfoAssembler assembler =
    new MethodNameBasedMBeanInfoAssembler();
assembler.setManagedMethods(
    "getActiveJobs",
    "requestRefresh"
);
```

Lưu ý tên được dùng là **tên Java method**, không phải tên JMX attribute. Khi cần phân biệt các overload, phải đọc semantics của assembler phiên bản đang dùng và kiểm tra `MBeanInfo` thực tế; không nên xem tên method là mô hình phân quyền tới từng signature.

### 4.3. InterfaceBasedMBeanInfoAssembler

Một management interface có thể tách hợp đồng quản trị ra khỏi toàn bộ public API của implementation.

```java
public interface WorkerManagement {
    int getActiveJobs();
    void requestRefresh();
}
```

Assembler được cấu hình chọn interface này, nhờ đó thêm method nghiệp vụ vào implementation không đương nhiên mở rộng JMX contract.

### 4.4. MetadataMBeanInfoAssembler

`MetadataMBeanInfoAssembler` dùng `JmxAttributeSource` để đọc metadata. Khi kết hợp `AnnotationJmxAttributeSource`, các annotation quản trị trở thành nguồn chọn method và mô tả.

```text
@ManagedAttribute / @ManagedOperation
                  |
          AnnotationJmxAttributeSource
                  |
          MetadataMBeanInfoAssembler
                  |
                 MBeanInfo
```

Nếu ứng dụng đã dùng `@EnableMBeanExport`, Spring cấu hình phần lớn chuỗi này. Không cần tạo thêm assembler thủ công chỉ để bật annotation export.

## 5. @ManagedAttribute là cách khai báo attribute

Annotation `org.springframework.jmx.export.annotation.ManagedAttribute` thường đặt trên getter hoặc setter được muốn công bố.

```java
@ManagedAttribute(description = "Số job đang chạy")
public int getActiveJobs() {
    return workerService.getActiveJobCount();
}
```

Đây là khai báo rằng property `ActiveJobs` phục vụ quản trị. Method có thể tính toán trực tiếp, đọc atomic counter hoặc delegate sang service. Nó không cần ánh xạ 1:1 với field Java.

Với boolean:

```java
@ManagedAttribute(description = "Đang cho phép nhận job?")
public boolean isEnabled() {
    return workerService.isEnabled();
}
```

Nếu muốn cho phép ghi, có thể công bố setter:

```java
@ManagedAttribute(description = "Bật/tắt nhận job")
public void setEnabled(boolean enabled) {
    workerService.setEnabled(enabled);
}
```

Khi getter/setter tương ứng được export, attribute `Enabled` có thể trở thành writable. Đây là thay đổi khả năng điều khiển, không chỉ thay đổi cách hiển thị: client JMX có quyền ghi có thể thay đổi runtime. Chỉ expose setter khi thực sự cần, đồng thời bảo vệ invariant, validation, authorization và audit ở mức thích hợp.

**`@ManagedAttribute` khác Java field:** field `private int activeJobs` không tự động được expose; accessor được chọn mới tạo JMX attribute. Getter có thể trả một metric tổng hợp và không chứa field cùng tên.

## 6. @ManagedOperation là cách khai báo thao tác quản trị

Annotation `org.springframework.jmx.export.annotation.ManagedOperation` đánh dấu method được đưa vào danh sách operation.

```java
@ManagedOperation(description = "Yêu cầu làm mới cấu hình worker")
public void requestRefresh() {
    workerService.requestRefresh();
}
```

Operation có thể có tham số:

```java
@ManagedOperation(description = "Đặt giới hạn worker")
@ManagedOperationParameters({
    @ManagedOperationParameter(
        name = "limit",
        description = "Số worker, từ 1 đến 64"
    )
})
public void updateWorkerLimit(int limit) {
    if (limit < 1 || limit > 64) {
        throw new IllegalArgumentException(
            "limit must be in [1, 64]"
        );
    }
    workerService.updateWorkerLimit(limit);
}
```

Để biên dịch ví dụ này, import `ManagedOperation`, `ManagedOperationParameter`, `ManagedOperationParameters` từ package `org.springframework.jmx.export.annotation`.

Các metadata annotation có thể cung cấp mô tả cho JMX tooling, nhưng không tự cung cấp kiểm soát bảo mật. Client có quyền gọi operation vẫn có thể gây thay đổi dữ liệu hoặc hiệu năng nếu implementation không có ràng buộc.

Không nên gán `@ManagedOperation` lên mọi public method để “xem cho tiện”: đó là mở rộng bề mặt quản trị từ xa khi JMX connector được bật.

## 7. Ví dụ đầy đủ: annotation-based export

Ứng dụng muốn expose một management adapter cho worker pool, không expose các method nghiệp vụ.

**Bean quản trị:**

```java
package com.example.management;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=WorkerPool,name=Main",
    description = "Trạng thái và thao tác quản trị worker pool"
)
public class WorkerPoolManagement {
    private final WorkerPoolService service;

    public WorkerPoolManagement(WorkerPoolService service) {
        this.service = service;
    }

    @ManagedAttribute(description = "Số worker đang hoạt động")
    public int getActiveWorkers() {
        return service.getActiveWorkerCount();
    }

    @ManagedAttribute(description = "Số tác vụ đang chờ")
    public long getPendingTasks() {
        return service.getPendingTaskCount();
    }

    @ManagedOperation(description = "Yêu cầu refresh worker pool")
    public void requestRefresh() {
        service.requestRefresh();
    }

    // Public method này không được chủ động expose bằng annotation.
    public String internalDescription() {
        return "implementation detail";
    }
}
```

`WorkerPoolService` là service nghiệp vụ của ứng dụng, cung cấp ba method được delegate trong ví dụ; hãy định nghĩa hoặc inject service thực tế phù hợp với project.

**Cấu hình:**

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
```

Trong mô hình annotation-based do Spring cấu hình, client dự kiến thấy:

```text
ObjectName:
  com.example.jobs:type=WorkerPool,name=Main

Attributes:
  ActiveWorkers   (read-only)
  PendingTasks    (read-only)

Operations:
  requestRefresh()
```

Method `internalDescription()` không có annotation quản trị và không được dự kiến xuất hiện trong contract annotation-selected. Cần phân biệt với trường hợp cấu hình một `SimpleReflectiveMBeanInfoAssembler` riêng: lúc đó public method có thể được expose ngay cả khi không gắn annotation.

## 8. Cấu hình MBeanExporter thủ công với MetadataMBeanInfoAssembler

Khi cần tự kiểm soát một `MBeanExporter`, có thể lắp metadata assembler và naming strategy thay vì dùng `@EnableMBeanExport`:

```java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class ExplicitJmxExportConfiguration {
    @Bean
    AnnotationJmxAttributeSource attributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    MetadataMBeanInfoAssembler mbeanInfoAssembler(
            AnnotationJmxAttributeSource source) {
        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);
        return assembler;
    }

    @Bean
    MetadataNamingStrategy objectNamingStrategy(
            AnnotationJmxAttributeSource source) {
        MetadataNamingStrategy naming =
            new MetadataNamingStrategy();
        naming.setAttributeSource(source);
        return naming;
    }

    @Bean
    MBeanExporter mbeanExporter(
            WorkerPoolManagement management,
            MetadataMBeanInfoAssembler assembler,
            MetadataNamingStrategy naming) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of("workerPool", management));
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        return exporter;
    }
}
```

`@ManagedResource.objectName` trên bean được naming strategy dùng để quyết định tên MBean. Nếu không khai báo tên theo metadata hoặc naming strategy khác, tên có thể được sinh theo quy tắc khác; client phải biết ObjectName thực tế.

Đây là **phương án thay thế**, không phải cấu hình cần chạy đồng thời với `@EnableMBeanExport`. Nếu hai exporter cố đăng ký cùng ObjectName, có thể gặp `InstanceAlreadyExistsException` hoặc hành vi phụ thuộc registration policy.

## 9. So sánh trực tiếp: assembler và annotation

| Tiêu chí | Assembler dựa trên reflection/allowlist/interface | Annotation `@ManagedAttribute` / `@ManagedOperation` |
| --- | --- | --- |
| Bản chất | Chiến lược build `MBeanInfo` | Metadata đặt trên các accessor/operation |
| Vị trí cấu hình | Java config / XML / bean exporter | Gần source code method |
| Chọn method | Reflection, tên method hoặc management interface | Annotation được đọc qua `AnnotationJmxAttributeSource` + `MetadataMBeanInfoAssembler` |
| Cần sửa class? | Không nhất thiết | Thường có nếu annotate trực tiếp |
| Nguy cơ expose nhầm | Cao hơn với simple reflection trên service lớn | Thấp hơn khi chọn method tường minh và cấu hình đúng |
| Metadata mô tả | Tùy chiến lược và cấu hình | Có description và metadata annotation |
| Tách contract khỏi implementation | Rõ với interface-based assembler | Có thể đạt được bằng management adapter |
| Phụ thuộc Spring | Tích hợp trong Spring JMX exporter | Các annotation Spring JMX |
| Tính linh hoạt | Cấu hình thay đổi mà không sửa code | Thuận tiện và trực quan khi code thuộc quyền quản lý |
| Quyền JMX connector | Không tự kiểm soát | Không tự kiểm soát |

Không thể nói “assembler cũ, annotation mới” theo cách tuyệt đối: **annotation-based export cũng cần assembler** để chuyển thông tin annotation thành MBeanInfo. Khác biệt thực tế nằm ở việc **metadata được suy ra tự động, liệt kê bên ngoài hay khai báo rõ trên code**.

## 10. Khi nào chọn mỗi hướng?

### 10.1. Chọn reflection khi class đã là management adapter nhỏ

Một class chuyên dụng chỉ có public methods dành cho quản trị, ví dụ `getHealth()`, `getActiveCount()`, `requestReload()`, có thể phù hợp với `SimpleReflectiveMBeanInfoAssembler`. Đổi lại, cần hiểu rằng thêm một public method về sau có thể vô tình mở rộng contract JMX.

### 10.2. Chọn method-name allowlist khi không thể sửa source

Nếu bean thuộc thư viện bên ngoài hoặc không muốn thêm dependency Spring JMX vào domain, `MethodNameBasedMBeanInfoAssembler` cho phép chọn phương thức qua cấu hình. Tuy nhiên, nếu API có overload phức tạp, cần kiểm tra metadata thực tế của các signature được expose.

### 10.3. Chọn interface-based khi cần contract rõ ràng

`InterfaceBasedMBeanInfoAssembler` thích hợp khi quản trị là một hợp đồng dài hạn và client Java cần sự ổn định. Việc đổi implementation ít làm thay đổi MBean contract nếu interface không đổi.

### 10.4. Chọn annotation-based khi ứng dụng Spring sở hữu code

Với Spring application, annotation-based export thường dễ đọc, dễ bảo trì: đặt `@ManagedResource` trên adapter hoặc bean, `@ManagedAttribute` trên getter/setter và `@ManagedOperation` trên hành động. `@EnableMBeanExport` giảm cấu hình boilerplate.

Đối với production, một management adapter nhỏ kết hợp annotation chọn lọc là lựa chọn dễ kiểm soát hơn so với reflection trên một business service lớn.

## 11. Một method có thể thay đổi vai trò tùy assembler

Giả sử:

```java
public class InventoryService {
    public int getStockCount() { return 120; }
    public void refreshStock() { /* ... */ }
    public void purgeAll() { /* ... */ }
}
```

Nếu exporter dùng simple reflection, các method public có thể được đưa vào metadata. Nếu dùng `MethodNameBasedMBeanInfoAssembler` với `getStockCount`, `refreshStock`, chỉ những tên được chọn mới là mục tiêu export. Nếu dùng metadata assembler, class cần annotation tương ứng và các method không annotate không trở thành bề mặt quản trị dự định.

Ví dụ annotate có kiểm soát:

```java
@ManagedResource(
    objectName = "com.example.inventory:type=InventoryManagement"
)
public class InventoryManagement {
    private final InventoryService inventory;

    public InventoryManagement(InventoryService inventory) {
        this.inventory = inventory;
    }

    @ManagedAttribute
    public int getStockCount() {
        return inventory.getStockCount();
    }

    @ManagedOperation
    public void requestRefresh() {
        inventory.refreshStock();
    }
}
```

Không đặt `purgeAll()` trên adapter chỉ để debug. Client JMX chỉ có thể gọi operation được công bố, nhưng nếu một operation nguy hiểm được công bố thì việc tên method ít người biết không tạo thành bảo vệ.

## 12. Cách kiểm tra bề mặt thực sự được công bố

Sau khi bean được export, đọc `MBeanInfo` từ đúng MBeanServer:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name =
    new ObjectName("com.example.jobs:type=WorkerPool,name=Main");

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "Attribute: %s, type=%s, readable=%s, writable=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.printf(
        "Operation: %s, params=%d%n",
        operation.getName(),
        operation.getSignature().length
    );
}
```

Ví dụ giả định exporter dùng platform MBeanServer; nếu cấu hình server khác, phải dùng kết nối tới đúng server. Việc inspect MBeanInfo giúp phân biệt ý định thiết kế và contract cuối cùng. Đặc biệt nên xác nhận attribute nào writable và không có operation thay đổi state ngoài dự kiến.

Không cần đọc private fields của bean để biết JMX contract: JMX client nhìn thấy metadata được export, không nhìn trực tiếp field Java.

## 13. Các lỗi và hiểu nhầm phổ biến

| Hiện tượng | Nguyên nhân thường gặp | Cách tiếp cận |
| --- | --- | --- |
| Có `@ManagedAttribute` nhưng JConsole không thấy | Exporter chưa bật, bean không nằm trong context, hoặc assembler đang dùng không đọc annotation | Kiểm tra `@EnableMBeanExport`/assembler và đăng ký MBean |
| Public method không có annotation vẫn là operation | Exporter dùng simple reflection | Dùng metadata assembler hoặc allowlist |
| Getter được export nhưng là read-only | Chưa công bố setter tương ứng | Chỉ thêm setter khi thực sự cho phép ghi |
| Client gọi sai tên attribute | JMX attribute thường là `ActiveWorkers`, không phải `getActiveWorkers` | Xem `MBeanInfo` và dùng đúng tên |
| Operation có nhiều tham số không gọi được | Sai signature hoặc kiểu tham số | Xem `MBeanOperationInfo.getSignature()` |
| MBean không tồn tại | Sai ObjectName, chưa export hoặc sai MBeanServer | Dùng `isRegistered`, kiểm tra naming và lifecycle |
| Trùng ObjectName | Nhiều exporter/bean cùng đăng ký tên | Dùng naming policy rõ ràng và tránh duplicate exporter |
| Method được export quá rộng | Dùng reflection trên business service | Export một adapter có API nhỏ hoặc dùng allowlist |
| Read-only client gọi operation bị từ chối | Authorization ở connector chặn invoke | Không nhầm với lỗi metadata; kiểm tra policy |

**Phân biệt lỗi metadata với lỗi quyền:** một operation có thể hiện trong `MBeanInfo` nhưng client không có quyền invoke. Ngược lại, công cụ có quyền cao cũng không gọi được method không được công bố qua MBean contract chỉ bằng cách biết method Java nội bộ.

## 14. Bảo mật và tính ổn định của management contract

Dù dùng assembler nào, MBean expose có thể được truy cập bởi client local hoặc remote theo cấu hình connector. Vì vậy:

- Chỉ công bố attributes/operations cần thiết cho monitoring và vận hành.
- Tránh `getPassword()`, `getToken()`, raw customer data, stack trace chứa thông tin nhạy cảm.
- Getter nên nhẹ, giới hạn tài nguyên và không có side effect vì client có thể polling liên tục.
- Operation như `stop()`, `clear()`, `purge()` phải có ngữ nghĩa rõ, validation, audit và quyền thực thi phù hợp.
- Không xem annotation là security policy; authentication, TLS và authorization của JMX connector là lớp riêng.
- Giữ `ObjectName`, tên attribute, kiểu, đơn vị và operation signature ổn định khi refactor class.
- Nếu chọn reflection, việc thêm public method có thể thay đổi contract một cách ngoài ý muốn.
- Nếu dùng annotation, việc xóa/đổi tên annotation hoặc getter có thể phá dashboard đang dùng thuộc tính cũ.

**Read-only attribute không đồng nghĩa dữ liệu công khai**: chỉ đọc vẫn có thể làm lộ cấu hình và thông tin hệ thống. Quyết định expose dữ liệu phải bắt đầu từ phân loại thông tin, không chỉ từ quyền ghi.

## 15. Sơ đồ lựa chọn nhanh

```text
Cần expose Spring bean qua JMX?
       |
       +-- Có quyền sửa code và muốn chọn method rõ ràng?
       |       |
       |       +-- Có -> @ManagedResource
       |                  @ManagedAttribute / @ManagedOperation
       |                  @EnableMBeanExport
       |
       +-- Không muốn sửa class?
       |       |
       |       +-- Có management interface?
       |       |       |
       |       |       +-- Có -> InterfaceBasedMBeanInfoAssembler
       |       |
       |       +-- Chỉ vài method -> MethodNameBasedMBeanInfoAssembler
       |
       +-- Class chỉ gồm API quản trị, nhỏ và kiểm soát?
               |
               +-- Có thể dùng SimpleReflectiveMBeanInfoAssembler,
                   nhưng cần xem bề mặt public và MBeanInfo
```

## 16. Kết luận

**`MBeanInfoAssembler` là cơ chế chọn và tạo metadata, còn `@ManagedAttribute` và `@ManagedOperation` là cách khai báo metadata trên method.** Hai khái niệm bổ sung cho nhau khi sử dụng `MetadataMBeanInfoAssembler` với `AnnotationJmxAttributeSource`.

Chọn đúng chiến lược dựa trên yêu cầu hợp đồng quản trị:

- Reflection nhanh nhưng có nguy cơ expose thêm public methods khi class thay đổi.
- Allowlist hoặc interface giúp tách management contract khỏi implementation.
- Annotation rõ ràng và dễ bảo trì trong Spring application, đặc biệt khi kết hợp management adapter nhỏ.

Trong mọi cách, kiểm tra MBeanInfo thực tế để biết chính xác attributes/operations đã công bố; bảo vệ connector, hạn chế thao tác có side effect và giữ contract ổn định cho các công cụ JMX.
