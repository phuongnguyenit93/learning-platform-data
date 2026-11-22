# Đọc cây domain, thuộc tính và operation trong công cụ JMX

## 1. Mục tiêu

Trong Java Management Extensions (**JMX**), công cụ quản trị như **JConsole** hoặc **VisualVM** giúp quan sát các MBean mà ứng dụng Java công bố. Thay vì đọc mã nguồn để tìm một đối tượng quản trị, người vận hành có thể duyệt **cây domain**, chọn từng MBean theo **ObjectName**, xem **attributes**, gọi **operations** và quan sát **notifications** nếu MBean hỗ trợ.

Sau bài học này, bạn có thể:

- Đọc đúng cấu trúc cây JMX theo domain và các key của `ObjectName`.
- Phân biệt metadata của attribute với giá trị runtime hiện tại.
- Xác định attribute nào chỉ đọc, attribute nào được phép ghi.
- Hiểu chữ ký operation, tham số, kiểu trả về và tác động khi gọi.
- Dùng JConsole hoặc công cụ JMX tương đương để kiểm tra MBean do Spring Framework export.
- Xử lý các lỗi hay gặp: không thấy MBean, giá trị không cập nhật, operation không gọi được hoặc tên hiển thị khác kỳ vọng.

Phạm vi tập trung vào **khả năng đọc và diễn giải giao diện quản trị**. Khi gọi operation làm thay đổi trạng thái, cần hiểu rõ tác động của operation và quyền truy cập của môi trường đang vận hành.

## 2. Công cụ JMX thấy những gì?

Cấu trúc cơ bản:

```text
Java application / JVM
    |
    +-- MBeanServer
          |
          +-- ObjectName: java.lang:type=Memory
          +-- ObjectName: java.lang:type=Threading
          +-- ObjectName: com.example.cache:type=Cache,name=products
          +-- ObjectName: com.example.cache:type=Cache,name=prices
                    |
                    +-- Attributes
                    +-- Operations
                    +-- Notifications
                    +-- Metadata
```

Trong JMX, mỗi MBean được định danh bằng `ObjectName` dạng:

```text
domain:key1=value1,key2=value2,...
```

Ví dụ:

```text
com.example.cache:type=Cache,name=products
```

Các phần có ý nghĩa:

| Phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Domain | `com.example.cache` | Namespace của nhóm MBean |
| `type` | `Cache` | Nhóm hoặc loại tài nguyên |
| `name` | `products` | Tên một tài nguyên cụ thể |
| Attribute | `EntryCount` | Trạng thái có thể đọc hoặc ghi |
| Operation | `clear()` | Hành động có thể được gọi |
| Notification | `cache.threshold.exceeded` | Loại sự kiện MBean có thể phát |

**Cây hiển thị trong JConsole là cách công cụ nhóm và trình bày các ObjectName.** Cây không nhất thiết phản ánh cây package Java, Spring bean hierarchy hoặc quan hệ cha/con thực của các đối tượng. Cấu trúc cây thay đổi theo công cụ và cách MBean được đặt tên.

## 3. Chuẩn bị để xem cây JMX

### 3.1. Chạy ứng dụng có MBean được đăng ký

Để có nội dung trong tab MBeans, JVM phải có `MBeanServer` và các MBean đăng ký thành công.

JVM thường có sẵn các **platform MXBean** trong domain `java.lang`, chẳng hạn:

- `java.lang:type=Memory`: bộ nhớ heap và non-heap.
- `java.lang:type=Threading`: thông tin thread.
- `java.lang:type=ClassLoading`: số lớp đã nạp, đã gỡ và tổng số lớp nạp.
- `java.lang:type=Runtime`: uptime và thông tin runtime.
- `java.lang:type=OperatingSystem`: thông tin hệ điều hành theo API hỗ trợ.
- `java.lang:type=GarbageCollector,name=...`: dữ liệu của garbage collector được JVM cung cấp.

Các domain khác xuất hiện khi ứng dụng, framework, thư viện hoặc JVM cụ thể đăng ký thêm MBean.

### 3.2. Mở JConsole

Nếu JDK cài đặt có công cụ `jconsole`, có thể chạy:

```bash
jconsole
```

Sau đó chọn một tiến trình Java đang chạy mà bạn có quyền truy cập. JConsole thường hiển thị các tab như **Overview**, **Memory**, **Threads**, **Classes**, **VM Summary** và **MBeans**.

Chọn **MBeans** để duyệt cây domain. Với kết nối tới JVM ở máy khác, cần cấu hình JMX remote phù hợp (authentication, TLS, địa chỉ/port và quyền truy cập mạng); không nên mở endpoint quản trị công khai chỉ để thuận tiện xem thử.

### 3.3. VisualVM và công cụ khác

VisualVM có các tính năng quan sát JVM. Phần hiển thị MBeans/JMX có thể cần plugin hoặc cấu hình tương ứng, tùy bản VisualVM. Các ứng dụng giám sát và JMX client khác có thể hiển thị cùng dữ liệu dưới dạng bảng, cây hoặc API.

Cách đọc vẫn dựa trên cùng bộ khái niệm: **ObjectName → MBeanInfo → attributes/operations/notifications**.

## 4. Đọc cây domain từng bước

Giả sử JConsole hiển thị:

```text
MBeans
├── java.lang
│   ├── ClassLoading
│   ├── Memory
│   ├── Runtime
│   └── Threading
├── com.example.cache
│   └── Cache
│       ├── name=products
│       └── name=prices
└── org.springframework...
    └── ...
```

Đây là **sơ đồ minh họa**; tên node và cách nhóm phụ thuộc cách công cụ sắp xếp các key của ObjectName.

Để hiểu một node:

1. **Chọn domain**. Domain giúp khoanh vùng MBean theo namespace.
2. **Mở nhóm hoặc key property**. Các key như `type`, `name`, `application` giúp phân biệt tài nguyên.
3. **Chọn MBean cuối cùng**. Xác định ObjectName đầy đủ, ví dụ `com.example.cache:type=Cache,name=products`.
4. **Mở phần Attributes/Operations** trong giao diện công cụ.
5. **Đối chiếu metadata và giá trị**. Tên, loại dữ liệu và quyền của attribute đến từ metadata; giá trị phải được đọc từ MBean thực tại thời điểm công cụ truy vấn.

### Domain không phải package Java

`com.example.cache` nhìn giống Java package, nhưng đây chỉ là chuỗi domain của JMX. Một MBean viết trong package `com.example.app.monitoring` vẫn có thể được đăng ký dưới domain `com.example.cache`.

### Trật tự key không quyết định danh tính

Hai chuỗi sau biểu diễn cùng một ObjectName:

```text
com.example.cache:type=Cache,name=products
com.example.cache:name=products,type=Cache
```

Vì vậy, không dùng vị trí key trên cây UI để suy ra rằng thứ tự văn bản là một phần của danh tính. Khi debug có thể dùng `ObjectName.getCanonicalName()` để có dạng chuẩn hóa.

### Query pattern là công cụ tìm kiếm, không phải tên một MBean

Ví dụ:

```text
com.example.cache:type=Cache,*
```

Đây là pattern có thể dùng để tìm nhiều ObjectName. Nó không phải ObjectName cụ thể để đăng ký một bean.

## 5. Đọc Attributes: tên, kiểu, quyền và giá trị

Một MBean minh họa có thể công bố:

```text
Attributes
  EntryCount    int      412
  Enabled       boolean  true
  HitRate       double   0.96
  LastRefresh   long     1720000000000
```

Cần phân biệt:

- **Attribute name**: tên dùng trong JMX API, ví dụ `EntryCount`.
- **Attribute type**: kiểu dữ liệu được mô tả trong `MBeanAttributeInfo`, ví dụ `int`, `boolean`, `java.lang.String`.
- **Readable**: client có thể gọi `getAttribute` nếu quyền và implementation cho phép.
- **Writable**: client có thể gọi `setAttribute` nếu quyền và implementation cho phép.
- **Runtime value**: giá trị được MBean trả về tại lần đọc hiện tại.
- **Description**: mô tả metadata, có thể được client hiển thị.

Ví dụ Java:

```java
public interface CacheMonitorMBean {
    int getEntryCount();
    boolean isEnabled();
    void setEnabled(boolean enabled);
}
```

JMX suy ra:

| Java method | MBean attribute | Trạng thái |
| --- | --- | --- |
| `getEntryCount()` | `EntryCount` | Chỉ đọc |
| `isEnabled()` | `Enabled` | Có getter |
| `setEnabled(boolean)` | `Enabled` | Có setter, có thể ghi |

Với ví dụ này, `EntryCount` là read-only; `Enabled` là read/write. Một setter có tồn tại trong Java không đồng nghĩa mọi client đều được phép sử dụng: quyền truy cập JMX và kiểm tra nghiệp vụ vẫn có thể ngăn thao tác ghi.

### 5.1. Giá trị snapshot và chu kỳ refresh

JConsole thường cập nhật số liệu theo một chu kỳ. Nếu attribute `EntryCount` thay đổi từ 412 sang 413, giao diện có thể hiển thị độ trễ cho đến lần polling tiếp theo.

Một số Model MBean có chính sách cache attribute thông qua metadata như `currencyTimeLimit`. Vì vậy dữ liệu nhìn thấy có thể là snapshot từ lần lấy trước. Nếu số liệu không thay đổi, kiểm tra cả chu kỳ refresh, cách MBean tính giá trị và cache metadata.

### 5.2. Dữ liệu phức tạp

Attribute không phải lúc nào cũng là số nguyên hoặc chuỗi. Ví dụ:

- `java.lang:type=Memory` công bố `HeapMemoryUsage`, một kiểu cấu trúc được công cụ JMX trình bày qua `CompositeData` theo cơ chế MXBean.
- Một `TabularData` có thể đại diện cho dữ liệu dạng bảng.
- Một số kiểu object tùy chỉnh có thể không hiển thị đầy đủ hoặc không giải mã được ở client nếu thiếu class tương ứng.

Không suy ra lỗi chỉ từ việc công cụ không thể trình bày một object tùy chỉnh. Cần kiểm tra kiểu trả về, MXBean/open-type mapping, serialization và khả năng hỗ trợ của client.

### 5.3. Đơn vị đo

Giá trị `HeapMemoryUsage.used` thường tính bằng **bytes**. Một metric custom như `RequestLatency` cần mô tả rõ đơn vị (milliseconds, seconds hay microseconds). JMX không tự áp đặt một đơn vị cho mọi attribute do ứng dụng định nghĩa.

Nếu metadata không nói rõ, phải đối chiếu hợp đồng của MBean trước khi diễn giải số liệu.

## 6. Đọc Operations: tên, tham số, kiểu trả về và ý nghĩa

Một operation là hành động mà client có thể gọi thông qua MBeanServer. Ví dụ:

```text
Operations
  clearCache() : void
  resetStatistics() : void
  setMaxEntries(int maxEntries) : void
  reloadConfiguration() : boolean
```

Thông tin chính gồm:

| Trường metadata | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Name | `setMaxEntries` | Tên operation |
| Parameters | `int maxEntries` | Tên và kiểu từng tham số |
| Return type | `void` | Kiểu kết quả trả về |
| Description | `Change cache capacity` | Ý nghĩa quản trị |
| Impact | `ACTION`, `INFO`, `ACTION_INFO`, `UNKNOWN` | Phân loại tác động theo metadata |

**Impact là khai báo mô tả**, không phải chính sách quyền thực thi. Operation có impact `INFO` vẫn cần được đánh giá theo implementation thực; không coi nhãn metadata là bằng chứng operation tuyệt đối vô hại.

### 6.1. Cách đọc chữ ký

```text
resetStatistics()
```

Nghĩa là operation không nhận tham số.

```text
resizePool(int newSize)
```

Nghĩa là cần một tham số kiểu `int` tên `newSize`.

```text
lookupTask(java.lang.String id)
```

Nghĩa là cần một chuỗi định danh task.

Khi có operation overload, ví dụ `resizePool(int)` và `resizePool(java.lang.String)`, JMX phân biệt bằng **signature**, tức danh sách kiểu tham số. Công cụ quản trị cần gọi đúng phiên bản.

### 6.2. Nhấn Invoke không tương đương đọc attribute

Đọc attribute thường là truy vấn trạng thái (nhưng vẫn có thể chạy logic getter). Operation có thể thực hiện thay đổi thật như clear cache, reset counter, reload config, pause worker hay shutdown service.

Trước khi gọi operation, cần hiểu:

1. MBean thuộc ứng dụng/JVM nào.
2. Operation có làm thay đổi dữ liệu hoặc ngắt dịch vụ không.
3. Operation có idempotent không.
4. Tham số truyền vào có hợp lệ không.
5. Có phương án kiểm chứng kết quả từ attribute hoặc log không.

Trong môi trường thực tế, dùng tài khoản có quyền tối thiểu cần thiết và chỉ gọi operation tác động trạng thái khi đã được cho phép.

## 7. Ví dụ hoàn chỉnh: tạo MBean để thực hành đọc cây

### 7.1. Standard MBean interface

```java
package com.example.jmx;

public interface CacheAdminMBean {
    int getEntryCount();
    boolean isEnabled();
    void setEnabled(boolean enabled);
    void clear();
}
```

### 7.2. Implementation

```java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

public class CacheAdmin implements CacheAdminMBean {
    private final AtomicInteger entryCount =
            new AtomicInteger(3);
    private volatile boolean enabled = true;

    @Override
    public int getEntryCount() {
        return entryCount.get();
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    @Override
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @Override
    public void clear() {
        entryCount.set(0);
    }
}
```

### 7.3. Đăng ký vào MBeanServer

```java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class JmxDemoApp {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
                "com.example.demo:type=Cache,name=primary"
        );

        server.registerMBean(new CacheAdmin(), name);

        System.out.println("MBean registered: " + name);
        System.out.println("PID/JVM is ready for JConsole");

        Thread.sleep(10 * 60 * 1000L);
    }
}
```

Đoạn mã giữ JVM hoạt động trong khoảng 10 phút để có thời gian kết nối bằng JConsole. Đây là ví dụ dành cho môi trường học tập; ứng dụng production có lifecycle riêng.

### 7.4. Những gì dự kiến xuất hiện

Trong tab **MBeans**, tìm domain:

```text
com.example.demo
```

Bên trong domain, chọn MBean có ObjectName:

```text
com.example.demo:type=Cache,name=primary
```

Các mục cần thấy:

```text
Attributes
  EntryCount = 3   [readable]
  Enabled    = true [readable, writable]

Operations
  clear()
```

Nếu công cụ cho phép, gọi `clear()` sẽ thay đổi bộ đếm trong ví dụ thành 0. Sau đó refresh/read lại `EntryCount` để quan sát giá trị mới. Có thể chỉnh `Enabled` qua attribute writable; logic ví dụ chỉ lưu cờ và không điều khiển cache thật.

### 7.5. Cách phân biệt metadata với giá trị thực tế

Khi gọi `clear()`, metadata của `EntryCount` vẫn là `int`, `readable=true`; chỉ giá trị runtime từ 3 thành 0. Metadata định nghĩa **hình dạng giao diện**, còn attribute value phản ánh **trạng thái hiện tại**.

## 8. Liên hệ Spring Framework JMX

Spring Framework cung cấp `MBeanExporter` và các annotation giúp đưa Spring bean vào MBeanServer.

Ví dụ:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.spring:type=JobQueue,name=background",
    description = "Background job queue management"
)
public class JobQueueManagement {
    private volatile int pendingJobs = 5;

    @ManagedAttribute(
        description = "Number of pending jobs"
    )
    public int getPendingJobs() {
        return pendingJobs;
    }

    @ManagedOperation(
        description = "Reset queue statistics"
    )
    public void resetStatistics() {
        pendingJobs = 0;
    }
}
```

Để xuất bean này, Spring cần một cấu hình JMX exporter phù hợp, ví dụ `AnnotationMBeanExporter` hoặc cơ chế tương đương. Chỉ thêm `@ManagedResource` chưa bảo đảm bean tự xuất ra JMX nếu exporter chưa hoạt động.

Khi được đăng ký thành công, công cụ sẽ thấy:

```text
com.example.spring:type=JobQueue,name=background

Attributes
  PendingJobs

Operations
  resetStatistics()
```

Description từ annotation có thể xuất hiện trong metadata nếu công cụ hỗ trợ hiển thị. Các công cụ khác nhau có thể nhóm node hoặc trình bày description khác nhau.

### Những điều nên kiểm tra khi không thấy Spring bean

- `MBeanExporter` hoặc `AnnotationMBeanExporter` đã được tạo/khởi động chưa.
- Bean có thuộc phạm vi exporter được quản lý không.
- `ObjectName` có hợp lệ và không xung đột không.
- Exporter dùng đúng MBeanServer mà công cụ đang kết nối không.
- Bean có proxy hoặc metadata khiến exporter không nhận dạng như kỳ vọng không.
- Nếu dùng Spring Boot, cấu hình kích hoạt JMX và exporter có phù hợp phiên bản/dependency không.

## 9. Cách xem metadata bằng Java mà không phụ thuộc giao diện công cụ

Giao diện JConsole giúp học nhanh, nhưng khi cần đối chiếu chính xác thì JMX API cung cấp metadata trực tiếp.

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class InspectJmxApi {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
                "java.lang:type=Memory"
        );

        MBeanInfo info = server.getMBeanInfo(name);
        System.out.println("MBean: " + name);
        System.out.println("Class: " + info.getClassName());

        for (MBeanAttributeInfo attr : info.getAttributes()) {
            System.out.printf(
                "ATTRIBUTE %s : %s, read=%s, write=%s%n",
                attr.getName(),
                attr.getType(),
                attr.isReadable(),
                attr.isWritable()
            );
        }

        for (MBeanOperationInfo op : info.getOperations()) {
            StringBuilder signature = new StringBuilder();

            for (MBeanParameterInfo p : op.getSignature()) {
                if (signature.length() > 0) {
                    signature.append(", ");
                }
                signature.append(p.getType())
                         .append(" ")
                         .append(p.getName());
            }

            System.out.printf(
                "OPERATION %s(%s) : %s%n",
                op.getName(),
                signature,
                op.getReturnType()
            );
        }
    }
}
```

Đoạn mã lấy metadata từ MBean `java.lang:type=Memory` vốn thường có trên JVM hỗ trợ platform MXBeans. Khi muốn inspect MBean custom, thay ObjectName bằng tên đúng và bảo đảm MBean đã được đăng ký trong **cùng MBeanServer/JVM**.

### Đọc giá trị attribute thực tế

```java
Object heapUsage = server.getAttribute(
    new ObjectName("java.lang:type=Memory"),
    "HeapMemoryUsage"
);

System.out.println(heapUsage);
```

`getMBeanInfo` trả metadata; `getAttribute` trả giá trị runtime. Đây là hai thao tác khác nhau.

### Đọc qua kết nối remote

Khi client ở tiến trình khác, dùng `MBeanServerConnection` lấy từ JMX connector. API cho metadata và attributes tương tự:

```java
MBeanInfo info = connection.getMBeanInfo(name);
Object value = connection.getAttribute(name, "EntryCount");
```

Kết nối remote cần được cấu hình đúng và có quyền phù hợp. Không thể lấy `ManagementFactory.getPlatformMBeanServer()` ở tiến trình client rồi mong nhìn thấy MBeanServer của JVM server khác.

## 10. Notifications trong cây JMX

Ngoài attributes và operations, một MBean có thể công bố **notifications**.

Ví dụ các loại event:

```text
com.example.queue.threshold.exceeded
com.example.cache.invalidated
jmx.attribute.change
```

Metadata cho biết MBean công bố loại notification nào; công cụ JMX phù hợp có thể đăng ký listener để theo dõi event.

Cần phân biệt:

- **Notification metadata**: mô tả loại sự kiện MBean có khả năng phát.
- **Notification thực tế**: một sự kiện được phát tại runtime.
- **Listener**: client đăng ký nhận event, có thể dùng filter.

Không phải lúc nào khai báo notification cũng đồng nghĩa hiện đang có sự kiện. Không phải việc thay đổi mọi attribute đều tự phát notification; logic MBean hoặc cơ chế framework phải thực sự phát event.

Khi dùng JConsole, phần Notifications nếu có hỗ trợ thường cho phép đăng ký nhận sự kiện của MBean được chọn.

## 11. Cách dùng cây JMX để chẩn đoán một tình huống thật

Giả sử đội vận hành nhận báo cáo: “Hàng đợi xử lý đơn tăng cao.”

Ứng dụng công bố:

```text
com.example.orders:type=Queue,name=payment
com.example.orders:type=Queue,name=shipping
```

Với payment queue:

```text
Attributes:
  PendingCount      long     1200
  ActiveWorkers     int      8
  MaxWorkers        int      16
  ProcessingEnabled boolean  true

Operations:
  pause()
  resume()
  resetStatistics()
```

Cách phân tích:

1. **Xác nhận đúng MBean**: domain là `com.example.orders`, type là `Queue`, name là `payment`.
2. **Đọc attributes**: pending cao cho biết backlog tại thời điểm đo; kiểm tra active workers, max workers và trạng thái processing.
3. **Quan sát theo thời gian**: đọc nhiều lần để biết backlog tăng, giảm hay giữ nguyên.
4. **Đối chiếu metadata**: `PendingCount` là kiểu `long`, đọc được; `ProcessingEnabled` có thể read-only hoặc writable tùy interface thực tế.
5. **Hiểu operations**: `pause()` và `resume()` có thể tác động luồng xử lý; không gọi khi chỉ cần chẩn đoán.
6. **Kết hợp log/metrics khác**: JMX cho biết trạng thái được công bố, không tự giải thích toàn bộ nguyên nhân của backlog.

Nhờ cây domain và ObjectName, có thể phân biệt queue payment với shipping mà không cần truy cập trực tiếp lớp Java nội bộ.

## 12. Các lỗi thường gặp khi đọc JMX

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Tab MBeans không có domain ứng dụng | Bean chưa export, đang xem sai JVM hoặc sai MBeanServer | Kiểm tra exporter, ObjectName và PID/JVM |
| Không thấy một bean cụ thể | Tên không đúng hoặc đăng ký thất bại | Kiểm tra exception, log registration và query ObjectName |
| Cây hiển thị khác tài liệu | Tool nhóm key properties khác hoặc naming strategy đã đổi | Đối chiếu full ObjectName |
| Attribute chỉ đọc dù có setter trong class | Setter không thuộc MBean interface/metadata | Kiểm tra `MBeanAttributeInfo.isWritable()` |
| Attribute hiển thị giá trị cũ | Polling interval, cache, getter hoặc nguồn metric chưa cập nhật | Đọc lại trực tiếp và xem policy cache |
| Operation không hiện | Chưa được công bố hoặc exporter không nhận metadata | Xem `MBeanInfo.getOperations()` |
| Gọi operation lỗi | Sai tham số/signature, exception từ resource hoặc thiếu quyền | Xem lỗi JMX trả về, chữ ký và quyền |
| Attribute kiểu phức tạp khó đọc | Client không hỗ trợ kiểu dữ liệu, serialization hoặc open types | Xem kiểu metadata và tài liệu MXBean |
| Không nhận notification | Chưa subscribe hoặc MBean không phát sự kiện | Kiểm tra listener, filter và emitter |
| Remote JMX không kết nối được | Sai host/port, RMI endpoint, firewall, authentication/TLS | Kiểm tra cấu hình remote và mạng |

### Những exception có thể gặp

- `InstanceNotFoundException`: ObjectName không còn đăng ký trong MBeanServer.
- `AttributeNotFoundException`: attribute không tồn tại theo hợp đồng MBean.
- `InvalidAttributeValueException`: giá trị ghi không hợp lệ.
- `ReflectionException`: không gọi được operation do lỗi phản chiếu/chữ ký.
- `MBeanException`: exception do MBean tạo ra khi thực thi thao tác.
- `SecurityException` hoặc lỗi kết nối: quyền và cấu hình endpoint không đáp ứng yêu cầu.

Nên đọc toàn bộ cause của exception và xác minh client đang thao tác với đúng ObjectName, đúng JVM.

## 13. Quy tắc đặt tên để cây domain dễ đọc

Cây JMX có ích nhất khi các ứng dụng dùng quy ước ObjectName thống nhất.

Một cách đặt tên:

```text
com.example.<subsystem>:type=<ResourceType>,application=<AppId>,name=<ResourceName>
```

Ví dụ:

```text
com.example.cache:type=Cache,application=storefront,name=products
com.example.cache:type=Cache,application=storefront,name=prices
com.example.jobs:type=Scheduler,application=storefront,name=background
```

Lợi ích:

- Dễ tìm theo domain và type.
- Dễ phân biệt nhiều MBean cùng loại.
- Hỗ trợ query pattern như `com.example.cache:type=Cache,*`.
- Tránh tên mặc định quá chung.
- Giúp dashboard, script và tài liệu vận hành cùng tham chiếu một hợp đồng.

Đừng đưa dữ liệu biến động như user ID hay request ID vào ObjectName của MBean liên tục được tạo/hủy; điều đó có thể làm cây phình to và gây khó quản trị.

## 14. Checklist thực hành trên công cụ JMX

Khi được yêu cầu “đọc cây domain, thuộc tính và operation”, có thể thực hiện theo trình tự:

1. Xác định JVM/PID và cách kết nối JMX.
2. Chọn tab hoặc màn hình MBeans.
3. Mở domain phù hợp; đọc ObjectName đầy đủ của MBean.
4. Xem Attributes: tên, kiểu, quyền read/write, đơn vị và giá trị.
5. Xem Operations: tên, signature, kiểu trả về, description và impact.
6. Chỉ thực thi operation khi hiểu tác động và có quyền thực hiện.
7. Nếu cần notification, xác nhận MBean có hỗ trợ và đăng ký listener.
8. Đối chiếu giá trị với log, metrics hoặc trạng thái ứng dụng khi chẩn đoán.
9. Ghi lại ObjectName và thời điểm đọc khi lập báo cáo vận hành.

### Câu hỏi tự kiểm tra

**1. Domain có phải package Java không?** Không. Domain là namespace trong ObjectName.

**2. Attributes và Operations khác nhau thế nào?** Attribute là giá trị trạng thái có thể đọc/ghi; operation là lời gọi hành động với signature.

**3. Metadata khác runtime value thế nào?** Metadata mô tả giao diện MBean, còn runtime value là dữ liệu nhận ở một thời điểm.

**4. Tại sao hai key property viết khác thứ tự vẫn là cùng MBean?** ObjectName xem tập key property là danh tính, không phụ thuộc thứ tự nhập.

**5. Vì sao không nên thử bấm mọi operation trong JConsole?** Operation có thể thay đổi trạng thái hoặc gây gián đoạn thực tế.

**6. Vì sao cây không thấy Spring bean?** Bean có thể chưa được export, export thất bại hoặc công cụ đang kết nối tới JVM/MBeanServer khác.

**7. Có thể inspect MBean mà không dùng JConsole không?** Có. Dùng `MBeanServerConnection`, `getMBeanInfo`, `getAttribute` và `invoke`.

## 15. Tổng kết

Đọc công cụ JMX theo thứ tự **domain → ObjectName → attributes/operations/notifications** giúp hiểu đúng tài nguyên mà ứng dụng công bố. Domain và các key property giúp định danh; metadata cho biết giao diện quản trị; attribute value phản ánh trạng thái; operation cho phép thực thi hành động.

Trong Spring Framework, các MBean được xuất qua `MBeanExporter` hoặc cơ chế dựa trên annotation vẫn được đọc theo cùng mô hình JMX. Khi quan sát và xử lý sự cố, luôn xác nhận **đúng JVM, đúng ObjectName, đúng quyền truy cập và đúng ý nghĩa của các số liệu/thao tác**.

### Tài liệu tham khảo

- Oracle Java Tutorials — Monitoring and Management Using JMX Technology: https://docs.oracle.com/javase/tutorial/jmx/
- Java SE API — `ObjectName`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
- Java SE API — `MBeanServerConnection`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
