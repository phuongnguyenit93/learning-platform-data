# Getter và setter tạo attribute đọc–ghi trong Spring JMX `@ManagedAttribute`

## 1. Attribute trong JMX là gì?

Trong Java Management Extensions (**JMX**), **attribute** là một giá trị trạng thái mà công cụ quản trị có thể đọc, ghi hoặc vừa đọc vừa ghi thông qua MBean. Khi tích hợp Spring Framework JMX, `@ManagedAttribute` giúp khai báo một phương thức getter hoặc setter của Spring bean là thành phần thuộc giao diện quản trị.

Ví dụ một bean có trạng thái:

```java
private volatile boolean enabled = true;
```

Ta có thể công bố trạng thái đó cho JConsole dưới tên attribute **Enabled**, có thể đọc và chỉnh sửa nếu đồng thời xuất cả getter lẫn setter phù hợp:

```java
@ManagedAttribute
public boolean isEnabled() {
    return enabled;
}

@ManagedAttribute
public void setEnabled(boolean enabled) {
    this.enabled = enabled;
}
```

Trong JMX, **getter** cung cấp khả năng đọc; **setter** cung cấp khả năng ghi. Nếu hai phương thức tạo thành một cặp hợp lệ cùng tên property và kiểu dữ liệu, công cụ quản trị thường thấy **một attribute read/write**, không phải hai attribute khác nhau.

Điều quan trọng là phải phân biệt:

- **Java property**: cặp phương thức `getXxx()`/`setXxx(...)` hoặc `isXxx()`/`setXxx(...)` của bean.
- **JMX attribute**: tên, kiểu, quyền đọc/ghi và metadata được MBean công bố.
- **Spring `@ManagedAttribute`**: annotation giúp Spring xây metadata JMX từ method của bean.
- **MBeanServer**: nơi công cụ quản trị thực hiện `getAttribute` và `setAttribute` trên một `ObjectName` đã đăng ký.

## 2. Cơ chế ánh xạ getter/setter thành attribute

Với bean:

```java
public class WorkerSettings {
    private int maxWorkers = 8;

    public int getMaxWorkers() {
        return maxWorkers;
    }

    public void setMaxWorkers(int maxWorkers) {
        this.maxWorkers = maxWorkers;
    }
}
```

Theo quy ước JavaBeans, property tên `maxWorkers` có getter và setter. Trong giao diện JMX, tên attribute thường được công bố với chữ cái đầu viết hoa: **MaxWorkers**.

Nếu dùng exporter dựa trên annotation:

```java
@ManagedAttribute
public int getMaxWorkers() { /* ... */ }

@ManagedAttribute
public void setMaxWorkers(int maxWorkers) { /* ... */ }
```

thì Spring có thể xây metadata như sau:

```text
ObjectName: com.example.jobs:type=WorkerSettings,name=background

Attribute: MaxWorkers
Type:      int
Readable:  true
Writable:  true
Is-is:     false
```

### Quy ước tên thường gặp

| Java method | Thuộc tính JMX | Ý nghĩa |
| --- | --- | --- |
| `getMaxWorkers()` | `MaxWorkers` | Getter cho phép đọc |
| `setMaxWorkers(int)` | `MaxWorkers` | Setter cho phép ghi |
| `isEnabled()` | `Enabled` | Boolean getter kiểu `is` |
| `setEnabled(boolean)` | `Enabled` | Boolean setter |
| `getActiveCount()` | `ActiveCount` | Getter không có setter, thường read-only |
| `setMaintenanceMode(boolean)` | `MaintenanceMode` | Setter không có getter, có thể write-only |

Cách Spring ánh xạ method thành JMX metadata còn phụ thuộc loại exporter và assembler đang dùng. Chỉ có method trong class không bảo đảm nó được xuất; với cơ chế annotation cần đánh dấu đúng method và kích hoạt exporter thích hợp.

## 3. Ví dụ hoàn chỉnh: một attribute đọc–ghi

Tạo Spring bean với `@ManagedResource` và hai `@ManagedAttribute`:

```java
package com.example.jobs.management;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=WorkerSettings,name=background",
    description = "Settings for background workers"
)
public class WorkerSettingsManagement {

    private volatile int maxWorkers = 8;

    @ManagedAttribute(
        description = "Maximum allowed worker count"
    )
    public int getMaxWorkers() {
        return maxWorkers;
    }

    @ManagedAttribute(
        description = "Update maximum allowed worker count"
    )
    public void setMaxWorkers(int maxWorkers) {
        if (maxWorkers < 1 || maxWorkers > 128) {
            throw new IllegalArgumentException(
                "maxWorkers must be between 1 and 128"
            );
        }
        this.maxWorkers = maxWorkers;
    }
}
```

Bean này có một thuộc tính JMX tên `MaxWorkers`:

- Khi client đọc, MBean gọi getter và trả lại giá trị hiện tại.
- Khi client ghi, MBean chuyển giá trị mới vào setter.
- Setter kiểm tra miền giá trị từ 1 đến 128.
- Trường `volatile` giúp các thread nhìn thấy giá trị `int` mới nhất theo ngữ nghĩa Java Memory Model.

**Lưu ý kiến trúc:** ví dụ chỉ thay đổi biến cấu hình. Trong hệ thống thực, thay `maxWorkers` phải đi kèm logic áp dụng tới executor hoặc scheduler thực tế; thay biến mà không áp dụng xuống tài nguyên có thể khiến giao diện JMX hiển thị cấu hình mới nhưng hành vi ứng dụng chưa đổi.

### Cấu hình exporter

Annotation chỉ tạo metadata khi có exporter tương ứng:

```java
package com.example.jobs.management;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.annotation.AnnotationMBeanExporter;

@Configuration
public class JmxManagementConfiguration {

    @Bean
    static AnnotationMBeanExporter annotationMBeanExporter() {
        return new AnnotationMBeanExporter();
    }
}
```

Trong ứng dụng Spring Boot, cơ chế JMX có thể được cấu hình hoặc auto-configure riêng tùy phiên bản và properties. Nếu exporter đã tồn tại, tránh tạo thêm exporter trùng chức năng cùng đăng ký ObjectName.

Trong ví dụ, `@Component` bảo đảm bean được Spring phát hiện nếu package nằm trong phạm vi component scan. `@ManagedResource` cung cấp metadata quản trị. `AnnotationMBeanExporter` đảm nhiệm việc xuất bean tới MBeanServer.

## 4. Đọc và ghi attribute qua MBeanServer

Có thể tương tác bằng Java API:

```java
import java.lang.management.ManagementFactory;
import javax.management.Attribute;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class WorkerSettingsClient {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
                "com.example.jobs:type=WorkerSettings,name=background"
        );

        Object before = server.getAttribute(
                name,
                "MaxWorkers"
        );
        System.out.println("Before: " + before);

        server.setAttribute(
                name,
                new Attribute("MaxWorkers", 16)
        );

        Object after = server.getAttribute(
                name,
                "MaxWorkers"
        );
        System.out.println("After: " + after);
    }
}
```

Đoạn client giả định bean đã được exporter đăng ký trong **cùng MBeanServer/JVM**. Nếu chạy chương trình Java độc lập khác, `getPlatformMBeanServer()` của chương trình đó sẽ không tự truy cập MBean trong JVM ứng dụng. Khi truy cập từ xa, cần một `MBeanServerConnection` qua JMX connector phù hợp.

Kết quả dự kiến khi giá trị ban đầu là 8:

```text
Before: 8
After: 16
```

`getAttribute` nhận **tên JMX attribute**, không phải tên Java method. Vì vậy dùng `MaxWorkers`, không dùng `getMaxWorkers`. `setAttribute` nhận một đối tượng `javax.management.Attribute` chứa tên và giá trị được ghi.

## 5. Phân biệt read-only, write-only và read/write

Quyền đọc và ghi là một phần của metadata MBean.

### 5.1. Attribute chỉ đọc

```java
@ManagedAttribute
public long getProcessedCount() {
    return processedCount;
}
```

Không công bố setter tương ứng. MBean thường thể hiện:

```text
ProcessedCount: readable=true, writable=false
```

Đây là lựa chọn phù hợp cho counters, uptime, số thread hoặc trạng thái chỉ nên quan sát.

### 5.2. Attribute chỉ ghi

```java
@ManagedAttribute
public void setMaintenanceMode(boolean mode) {
    this.maintenanceMode = mode;
}
```

Nếu cơ chế metadata hỗ trợ setter-only property và không công bố getter, attribute có thể write-only:

```text
MaintenanceMode: readable=false, writable=true
```

Tuy nhiên, write-only attributes thường khó vận hành vì client không biết trạng thái hiện tại. Khi cần thay đổi trạng thái mà không cung cấp giá trị đọc, hãy cân nhắc một **operation** rõ nghĩa, ví dụ `enableMaintenance()`, thay vì một setter khó kiểm chứng.

### 5.3. Attribute đọc–ghi

```java
@ManagedAttribute
public boolean isEnabled() {
    return enabled;
}

@ManagedAttribute
public void setEnabled(boolean enabled) {
    this.enabled = enabled;
}
```

Metadata mong đợi:

```text
Enabled: readable=true, writable=true
```

Dùng kiểu này khi người vận hành cần vừa xem vừa điều chỉnh trạng thái, chẳng hạn bật/tắt một chức năng đã được thiết kế để có thể thay đổi tại runtime.

### Bảng lựa chọn

| Nhu cầu | Getter | Setter | Gợi ý |
| --- | --- | --- | --- |
| Chỉ quan sát metric | Có | Không | Read-only attribute |
| Điều chỉnh cấu hình runtime | Có | Có | Read/write attribute |
| Gửi lệnh không cần đọc giá trị | Không bắt buộc | Không bắt buộc | Thường dùng operation |
| Thao tác thay đổi trạng thái lớn | Không áp dụng | Không áp dụng | `@ManagedOperation` |
| Cấu hình nhạy cảm | Tùy yêu cầu | Tùy yêu cầu | Giới hạn quyền, cân nhắc không export |

## 6. Getter boolean: getXxx và isXxx

Theo quy ước JavaBeans và JMX, boolean thường dùng getter dạng `isXxx()`:

```java
private boolean enabled;

@ManagedAttribute
public boolean isEnabled() {
    return enabled;
}

@ManagedAttribute
public void setEnabled(boolean enabled) {
    this.enabled = enabled;
}
```

JMX có thể đánh dấu `MBeanAttributeInfo.isIs() == true` cho boolean getter dạng `isXxx`.

Có thể dùng `getEnabled()` cho property boolean trong nhiều ngữ cảnh, nhưng cần nhất quán giữa getter, setter và quy tắc introspection. Với wrapper `Boolean`, nên dùng `getEnabled()` thay vì tự giả định `isEnabled()` được mọi cơ chế nhận diện giống primitive `boolean`.

### Các lỗi thường gặp

```java
public boolean isEnabled() { ... }
public void setIsEnabled(boolean value) { ... }
```

Hai method này có thể được diễn giải thành các property khác nhau (`Enabled` và `IsEnabled`), khiến người viết tưởng đã tạo một attribute đọc–ghi nhưng metadata không ghép cặp như mong đợi.

Nên dùng đúng:

```java
public boolean isEnabled() { ... }
public void setEnabled(boolean value) { ... }
```

## 7. Kiểu tham số của setter phải phù hợp getter

Một attribute đọc–ghi hợp lệ cần kiểu dữ liệu nhất quán:

```java
@ManagedAttribute
public int getPoolSize() {
    return poolSize;
}

@ManagedAttribute
public void setPoolSize(int poolSize) {
    this.poolSize = poolSize;
}
```

Không nên ghép một getter `int` với setter `String`:

```java
public int getPoolSize() { ... }
public void setPoolSize(String value) { ... }
```

Hai phương thức có kiểu không tương thích có thể làm JavaBeans introspection hoặc JMX metadata không xác định được một property read/write như dự kiến.

Khi client ghi bằng `MBeanServerConnection.setAttribute`, kiểu giá trị phải tương thích với loại được khai báo. Ví dụ `MaxWorkers` là `int`, client Java nên truyền `Integer`. Việc ghi chuỗi `"16"` không nên được giả định sẽ tự chuyển thành số nguyên trong mọi JMX client.

## 8. MBeanInfo cho biết attribute có thực sự đọc–ghi không

Thay vì suy luận từ source code, client có thể đọc metadata thực tế đã đăng ký:

```java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public final class AttributeInspector {

    public static void inspect(
            MBeanServerConnection connection,
            ObjectName name
    ) throws Exception {
        MBeanInfo info = connection.getMBeanInfo(name);

        for (MBeanAttributeInfo attribute : info.getAttributes()) {
            System.out.printf(
                "%s: type=%s, readable=%s, writable=%s, isIs=%s%n",
                attribute.getName(),
                attribute.getType(),
                attribute.isReadable(),
                attribute.isWritable(),
                attribute.isIs()
            );
        }
    }
}
```

Một attribute có:

```text
MaxWorkers: type=int, readable=true, writable=true, isIs=false
```

nghĩa là metadata cho phép client đọc và ghi. Nhưng **metadata không bảo đảm mọi lần ghi đều thành công**: setter có thể từ chối giá trị, business logic có thể lỗi hoặc người dùng có thể thiếu quyền.

Ngược lại, khi attribute là read-only, các công cụ thường không cung cấp ô chỉnh sửa hoặc thao tác ghi sẽ bị từ chối.

### Tại sao cần kiểm tra runtime metadata?

Source code có thể có cả getter và setter nhưng:

- Setter chưa được đánh dấu `@ManagedAttribute`.
- Exporter không sử dụng annotation metadata như kỳ vọng.
- Bean được export qua một interface chỉ chứa getter.
- Class thực tế là proxy hoặc một bean khác.
- Metadata assembler giới hạn một tập method.
- ObjectName đang chỉ tới MBean được đăng ký bởi exporter khác.

`MBeanInfo` là nguồn xác nhận giao diện JMX thực tế mà client nhìn thấy.

## 9. Demo Spring với nhiều kiểu attribute

```java
package com.example.management;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example:type=JobProcessor,name=default",
    description = "Runtime job processor management"
)
public class JobProcessorManagement {

    private final AtomicLong processed = new AtomicLong();
    private volatile boolean enabled = true;
    private volatile int maxParallelism = 4;

    @ManagedAttribute(
        description = "Total number of completed jobs"
    )
    public long getProcessedCount() {
        return processed.get();
    }

    @ManagedAttribute(
        description = "Whether job processing is enabled"
    )
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @ManagedAttribute(
        description = "Maximum parallel workers"
    )
    public int getMaxParallelism() {
        return maxParallelism;
    }

    @ManagedAttribute
    public void setMaxParallelism(int value) {
        if (value < 1 || value > 32) {
            throw new IllegalArgumentException(
                "maxParallelism must be in range 1..32"
            );
        }
        maxParallelism = value;
    }

    // Ordinary business/internal method.
    public void recordCompletion() {
        processed.incrementAndGet();
    }
}
```

Kỳ vọng ở JConsole:

| JMX attribute | Type | Read | Write |
| --- | --- | --- | --- |
| `ProcessedCount` | `long` | Có | Không |
| `Enabled` | `boolean` | Có | Có |
| `MaxParallelism` | `int` | Có | Có |

`recordCompletion()` là một Java method thông thường không được khai báo là management operation. Với annotation exporter, không nên tự động công bố nó chỉ vì method là public.

**Ứng dụng thực tế:** nếu `setMaxParallelism()` cần cập nhật một executor thực, setter phải gọi API cập nhật thích hợp. Demo chỉ giữ cờ và bộ đếm để làm rõ việc mapping attribute.

## 10. Thực hành trong JConsole

Giả sử ứng dụng đã chạy, exporter đã đăng ký:

```text
com.example:type=JobProcessor,name=default
```

Các bước:

1. Mở `jconsole` từ JDK, kết nối đúng JVM.
2. Chọn tab **MBeans**.
3. Mở domain `com.example` và chọn MBean có ObjectName nói trên.
4. Vào phần **Attributes**.
5. Xem `ProcessedCount`: chỉ đọc.
6. Xem `Enabled`: có thể đổi giữa `true` và `false` nếu client/quyền cho phép.
7. Xem `MaxParallelism`: thử một giá trị hợp lệ trên môi trường thực hành.
8. Đọc lại attribute để xác nhận trạng thái đã được cập nhật.
9. Khi nhập giá trị ngoài khoảng hợp lệ, kiểm tra lỗi setter được chuyển về client như thế nào.

Trước khi thay đổi attribute trên hệ thống thật, cần chắc chắn đó là thuộc tính được thiết kế cho quản trị runtime. Một setter có thể làm thay đổi hành vi dịch vụ ngay lập tức.

### JConsole hiển thị kiểu dữ liệu

Tùy client, attribute có thể được trình bày dạng bảng và hỗ trợ chỉnh sửa trực tiếp nếu metadata cho phép. Không phải mọi kiểu phức tạp đều có editor tương ứng. Đối với kiểu `int`, `boolean`, `String`, thao tác thường đơn giản hơn.

## 11. Kiểm tra write bằng JMX API

Đọc và ghi theo `ObjectName`:

```java
import javax.management.Attribute;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public final class JmxAttributeWriter {

    public static void updateMaxParallelism(
            MBeanServerConnection connection
    ) throws Exception {
        ObjectName name = new ObjectName(
            "com.example:type=JobProcessor,name=default"
        );

        Object before = connection.getAttribute(
                name,
                "MaxParallelism"
        );

        connection.setAttribute(
                name,
                new Attribute("MaxParallelism", 6)
        );

        Object after = connection.getAttribute(
                name,
                "MaxParallelism"
        );

        System.out.println(
                "MaxParallelism: " + before + " -> " + after
        );
    }
}
```

Đây là một API chuẩn chung cho cả kết nối tại chỗ và từ xa. `MBeanServer` kế thừa `MBeanServerConnection`. Với remote, ứng dụng nhận connection từ `JMXConnector` sau khi kết nối.

Khi setter trả lỗi, `setAttribute` có thể ném exception tương ứng. Đừng giả định mỗi write đều thành công chỉ vì attribute có metadata `writable=true`.

## 12. Validation: setter vẫn là ranh giới bảo vệ

Một getter/setter được công bố qua JMX có thể trở thành đầu vào từ một client quản trị khác process. Vì vậy setter cần kiểm tra dữ liệu và điều kiện nghiệp vụ tương tự public API khác.

Ví dụ:

```java
@ManagedAttribute
public void setMaxPoolSize(int size) {
    if (size < 1 || size > 64) {
        throw new IllegalArgumentException(
            "Pool size must be in range 1..64"
        );
    }

    // Apply to a real managed executor here.
    executor.setMaximumPoolSize(size);
}
```

Cần hiểu rằng `ThreadPoolExecutor` có quan hệ giữa core pool size và maximum pool size; thay đổi ngưỡng không đúng thứ tự có thể ném `IllegalArgumentException`. Mẫu trên chỉ minh họa validation của setter, không phải logic đầy đủ để đổi kích thước mọi executor.

Các bước thiết kế setter tốt:

- Xác định miền giá trị hợp lệ.
- Kiểm tra tương quan với cấu hình khác.
- Áp dụng thay đổi lên tài nguyên thật theo trình tự an toàn.
- Nếu thất bại, tránh để metadata hoặc trạng thái ghi nhận không khớp runtime.
- Ghi log/audit thao tác quan trọng theo yêu cầu.
- Không thực hiện tác vụ rất lâu dưới một lời gọi JMX đồng bộ nếu có thể tránh.

Getter nên phản ánh **trạng thái đang được áp dụng** hoặc nói rõ đó là giá trị **được yêu cầu**; tránh một thuộc tính `MaxWorkers` mà client tưởng đã áp dụng nhưng executor vẫn chạy với giới hạn cũ.

## 13. Thread safety và tính nhất quán

JMX không tự bảo vệ trạng thái của bean khỏi truy cập đồng thời.

Ví dụ:

```java
private volatile boolean enabled;
```

phù hợp với cờ boolean đơn giản vì việc đọc/ghi thấy được giá trị mới theo Java Memory Model. Nhưng với cấu hình nhiều trường liên quan:

```java
private int minWorkers;
private int maxWorkers;
```

nếu cập nhật riêng từng field, một thread có thể nhìn thấy trạng thái trung gian không hợp lệ.

Cách giải quyết tùy nghiệp vụ:

- Dùng một đối tượng cấu hình bất biến và tham chiếu `volatile`/atomic để thay thế đồng thời.
- Dùng synchronized/lock phù hợp khi thay đổi nhiều trường.
- Gói thay đổi liên quan thành một management operation nhận đầy đủ tham số.
- Tránh công bố setter độc lập cho mỗi giá trị nếu chúng không được phép thay đổi độc lập.

Đối với bộ đếm, dùng `AtomicLong`, `LongAdder` hoặc snapshot theo nhu cầu. Tách rạch ròi property đọc–ghi với operation có hành vi nghiệp vụ phức tạp.

## 14. Getter và setter có nên dùng cùng description?

`@ManagedAttribute` có thể chứa metadata mô tả ở method. Khi một attribute có cả getter và setter, Spring assembler cần tổng hợp metadata thành một `MBeanAttributeInfo` hoặc `ModelMBeanAttributeInfo`.

Nên mô tả theo nghĩa của **attribute**, không theo thao tác Java riêng lẻ:

```java
@ManagedAttribute(
    description = "Maximum number of concurrent workers"
)
public int getMaxWorkers() {
    return maxWorkers;
}

@ManagedAttribute
public void setMaxWorkers(int value) {
    this.maxWorkers = value;
}
```

Thực tế exporter/assembler quyết định descriptor được tổng hợp như thế nào. Nếu metadata của getter và setter xung đột, hãy kiểm tra `MBeanInfo` thực tế thay vì dựa vào giả định thứ tự ưu tiên.

Có thể tổ chức thông tin vận hành khác như đơn vị, mức giá trị hợp lệ và tác động thay đổi trong description hoặc tài liệu quản trị đi kèm.

## 15. Spring bean và JMX attribute là hai hợp đồng riêng

Một class:

```java
public class QueueService {
    public long getPendingCount() { ... }
    public void setProcessingEnabled(boolean enabled) { ... }
    public void submitJob(Job job) { ... }
}
```

có thể được dùng bởi nhiều phần khác nhau của ứng dụng. Nếu xuất trực tiếp toàn bộ class, ranh giới giữa business API và JMX API có thể bị mờ.

Một cách thiết kế sạch hơn là adapter:

```java
@ManagedResource(
    objectName = "com.example:type=QueueControl,name=orders"
)
public class QueueControl {
    private final QueueService service;

    public QueueControl(QueueService service) {
        this.service = service;
    }

    @ManagedAttribute
    public long getPendingCount() {
        return service.getPendingCount();
    }

    @ManagedAttribute
    public boolean isProcessingEnabled() {
        return service.isProcessingEnabled();
    }

    @ManagedAttribute
    public void setProcessingEnabled(boolean enabled) {
        service.setProcessingEnabled(enabled);
    }
}
```

`QueueService` và `Job` trong ví dụ là các kiểu nghiệp vụ minh họa. Adapter giới hạn chính xác những property được xuất. Chỉ thêm setter quản trị khi thực sự muốn client JMX có khả năng thay đổi trạng thái.

## 16. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Không thấy attribute | Bean chưa export, thiếu annotation hoặc sai ObjectName | Exporter, `@ManagedResource`, MBeanServer |
| Attribute chỉ đọc dù có setter | Setter không được công bố trong metadata | Annotation, assembler, `MBeanInfo.isWritable()` |
| Getter/setter thành hai property khác nhau | Đặt tên không cùng quy ước | `getXxx/isXxx` và `setXxx` |
| Lỗi type khi ghi | Giá trị không phù hợp kiểu metadata | `MBeanAttributeInfo.getType()` |
| `AttributeNotFoundException` | Sai tên JMX attribute | Dùng tên trong `MBeanInfo` |
| `InvalidAttributeValueException` | Giá trị không hợp lệ hoặc không tương thích | Validation và kiểu dữ liệu |
| `MBeanException` | Lỗi từ code getter/setter hoặc resource | Exception cause và business logic |
| Ghi thành công nhưng hành vi không đổi | Setter chỉ đổi biến cấu hình mà chưa cập nhật resource | Kiểm tra logic áp dụng runtime |
| Giá trị đọc cũ | Cache metadata, polling, đồng bộ dữ liệu | Currency time limit và thread safety |
| Không có editor trong công cụ | Client không hỗ trợ loại dữ liệu hoặc quyền ghi | Metadata/khả năng client |
| Bean khác có cùng ObjectName | Exporter đăng ký trùng | Naming và registration policy |

### Phân biệt lỗi setter với metadata

Metadata `writable=true` chỉ nói attribute có lối ghi. Setter vẫn có thể từ chối giá trị mới khi không hợp lệ. Nếu write bị lỗi, cần xem exception từ client và log ứng dụng để biết liệu lỗi do type conversion, validation hay logic nội bộ.

## 17. Các trường hợp đặc biệt

### 17.1. Setter không có getter

Một MBean có thể công bố một attribute write-only nếu cơ chế exporter/assembler hỗ trợ. Tuy nhiên, việc không đọc lại được trạng thái khiến vận hành khó kiểm chứng. Cân nhắc operation nếu hành động giống “gửi lệnh” hơn là “đặt giá trị property”.

### 17.2. Getter tốn chi phí

Một getter JMX có thể bị gọi định kỳ bởi công cụ giám sát. Tránh những getter thực hiện truy vấn database lớn, mạng hoặc khóa lâu. Nếu đo lường tốn chi phí, dùng snapshot/cache có chủ đích và ghi rõ độ trễ dữ liệu.

### 17.3. Có nhiều setter overload

Ví dụ:

```java
void setLimit(int value);
void setLimit(String value);
```

Introspection có thể trở nên mơ hồ. Với JMX, nên giữ một kiểu rõ ràng cho mỗi attribute và dùng operation riêng khi cần nhiều cách biểu diễn đầu vào.

### 17.4. Thay đổi type

Nếu client hiện đọc `MaxWorkers` kiểu `int`, thay nó thành `long` có thể ảnh hưởng dashboard hoặc client Java. Tên attribute, kiểu và quyền read/write là một phần của hợp đồng quản trị cần ổn định.

### 17.5. Quản trị từ xa

Một client ở JVM khác dùng JMX remote sẽ tương tác qua `MBeanServerConnection`; không nên giả định mọi object tùy chỉnh có thể truyền qua ranh giới JVM dễ dàng. Với dữ liệu phức tạp, cân nhắc MXBean và Open Types. Bảo vệ kết nối JMX remote bằng authentication, TLS và kiểm soát mạng phù hợp.

## 18. Khi nào dùng @ManagedOperation thay vì setter?

Getter/setter phù hợp khi trạng thái là một property có ý nghĩa và có thể đặt lại bằng một giá trị hợp lệ:

```text
Enabled = true/false
MaxWorkers = 8/16
LoggingLevel = INFO/DEBUG
```

Với hành động như:

```text
clearCache()
reloadConfiguration()
rebuildIndex()
rotateCredentials()
```

nên công bố dưới dạng operation, ví dụ:

```java
@ManagedOperation(
    description = "Reload application configuration"
)
public void reloadConfiguration() {
    // Deliberate management operation.
}
```

Không nên tạo một setter giả như `setReload(true)` chỉ để kích hoạt side effect, trừ khi đây thực sự là trạng thái có hợp đồng rõ ràng. Operation truyền đạt ý nghĩa “thực thi hành động” tốt hơn.

## 19. Câu hỏi tự kiểm tra

**1. Điều kiện để getter và setter tạo một attribute đọc–ghi là gì?**

Phải cùng property name theo quy ước, kiểu dữ liệu tương thích và cả hai được công bố trong metadata JMX.

**2. Getter `isEnabled()` kết hợp với setter nào?**

`setEnabled(boolean enabled)`, không phải `setIsEnabled(...)`.

**3. Có getter và setter trong class nhưng `MBeanInfo` báo read-only, vì sao?**

Có thể setter chưa được `@ManagedAttribute` hoặc bị interface/assembler loại khỏi hợp đồng export.

**4. `writable=true` có bảo đảm ghi giá trị nào cũng được không?**

Không. Setter có thể kiểm tra giới hạn, runtime có thể không cho phép hoặc client có thể thiếu quyền.

**5. Có cần dùng `@ManagedOperation` cho setter không?**

Không. Setter được công bố bằng `@ManagedAttribute` để tạo lối ghi của attribute; `@ManagedOperation` dùng cho hành động quản trị độc lập.

**6. Vì sao getter cần nhanh?**

Công cụ giám sát có thể đọc định kỳ; getter chậm làm tăng tải và có thể ảnh hưởng hiệu năng ứng dụng.

**7. Việc cập nhật một biến trong setter có bảo đảm tài nguyên đang dùng giá trị mới không?**

Không. Logic ứng dụng phải thực sự áp dụng cấu hình vào tài nguyên runtime.

## 20. Tổng kết

Với Spring JMX, **`@ManagedAttribute` trên getter tạo quyền đọc**, còn **`@ManagedAttribute` trên setter tương ứng tạo quyền ghi**. Khi hai method cùng mô tả một Java property hợp lệ, Spring exporter có thể công bố **một JMX attribute read/write**.

Điểm cần xác nhận cuối cùng luôn là metadata thực tế:

```text
MBeanInfo
  Attribute: MaxWorkers
  Type: int
  Readable: true
  Writable: true
```

Tuy nhiên, quyền ghi trong metadata khác với quyền truy cập và khả năng nghiệp vụ chấp nhận một giá trị. Setter quản trị phải kiểm tra đầu vào, xử lý đồng thời, cập nhật tài nguyên thật và bảo đảm thao tác an toàn. Khi hành vi giống một lệnh thay vì điều chỉnh property, hãy chọn `@ManagedOperation`.

### Tài liệu tham khảo

- Spring Framework Reference — JMX Exporting: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Spring Framework API — `ManagedAttribute`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedAttribute.html
- Spring Framework API — `AnnotationMBeanExporter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/AnnotationMBeanExporter.html
- Java SE API — `MBeanAttributeInfo`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanAttributeInfo.html
- Java SE API — `MBeanServerConnection`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
