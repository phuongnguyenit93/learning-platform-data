# Standard MBean và quy ước tên giao diện quản lý

## Mục tiêu

Hiểu cách Standard MBean dùng giao diện Java có hậu tố `MBean` để công bố thuộc tính và thao tác quản trị qua JMX. Biết phân biệt quy ước tên interface, tên lớp triển khai và `ObjectName`; thực hành đăng ký MBean trên `MBeanServer` và tích hợp với Spring Framework.

## 1. Standard MBean trong JMX

Java Management Extensions (JMX) là API quản trị và giám sát ứng dụng Java tại thời điểm chạy. Managed Bean (MBean) là đối tượng công bố thông tin và thao tác quản lý cho JMX client như JConsole. Ví dụ, người vận hành có thể đọc bộ đếm xử lý, bật tắt một chế độ hoặc gọi thao tác reset.

Standard MBean dựa vào **giao diện Java tuân theo quy ước tên** để xác định những gì được công bố. Nếu đối tượng được quản lý thuộc lớp `JobMonitor`, giao diện quản lý theo quy ước là `JobMonitorMBean`. Lớp triển khai phải thực hiện giao diện này. Chỉ các phương thức nằm trong hợp đồng quản lý được JMX nhìn thấy; một phương thức `public` bổ sung trong implementation không mặc nhiên thành thao tác JMX.

Standard MBean là khái niệm của Java JMX, không phụ thuộc Spring. Spring Framework cung cấp cách đăng ký, xuất đối tượng quản lý qua `MBeanExporter`, đồng thời hỗ trợ mô hình metadata dựa trên annotation.

## 2. Ví dụ interface và implementation

Tạo hai file trong package `com.example.monitoring`.

**JobMonitorMBean.java**

```java
package com.example.monitoring;

public interface JobMonitorMBean {
    int getProcessedCount();
    boolean isEnabled();
    void setEnabled(boolean enabled);
    void reset();
}
```

**JobMonitor.java**

```java
package com.example.monitoring;

import java.util.concurrent.atomic.AtomicInteger;

public class JobMonitor implements JobMonitorMBean {
    private final AtomicInteger processedCount = new AtomicInteger();
    private volatile boolean enabled = true;

    public void recordCompletedJob() {
        if (enabled) {
            processedCount.incrementAndGet();
        }
    }

    @Override
    public int getProcessedCount() {
        return processedCount.get();
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
    public void reset() {
        processedCount.set(0);
    }
}
```

Các thành phần JMX nhận được từ interface:

| Khai báo | Phần tử JMX | Truy cập |
| --- | --- | --- |
| `getProcessedCount()` | Thuộc tính `ProcessedCount` | Đọc |
| `isEnabled()`, `setEnabled(boolean)` | Thuộc tính `Enabled` | Đọc/ghi |
| `reset()` | Operation `reset` | Gọi |
| `recordCompletedJob()` chỉ có trong lớp triển khai | Không xuất qua Standard MBean | Nội bộ |

Tên attribute được suy ra theo quy tắc getter/setter, khác tên method. Ví dụ, `getProcessedCount()` tương ứng `ProcessedCount`, còn `reset()` là operation. Khi viết API quản trị, các getter/setter cần cùng kiểu dữ liệu, đúng chữ hoa chữ thường và tuân thủ JavaBeans/JMX conventions.

## 3. Tên giao diện quản lý: quy tắc chính xác

Với Standard MBean trực tiếp theo convention:

- Lớp `JobMonitor` → interface `JobMonitorMBean`.
- Lớp `CacheMonitor` → interface `CacheMonitorMBean`.
- Lớp `ThreadPoolManager` → interface `ThreadPoolManagerMBean`.

Tên interface **có ý nghĩa đối với JMX introspection**; không thể tùy tiện đổi thành `MonitorApi` rồi mong hệ thống suy ra đây là hợp đồng Standard MBean của `JobMonitor`. Interface cần là kiểu công khai có thể dùng được, lớp quản lý thực sự implement interface đó.

Trường hợp đặc biệt: JMX cung cấp lớp `javax.management.StandardMBean` để chỉ định tường minh interface quản lý và bọc một implementation. Với lựa chọn này, có thể tách tên interface khỏi quy ước thông thường; không nên kết luận hậu tố `ClassNameMBean` là quy tắc tuyệt đối cho mọi cách đăng ký JMX.

## 4. Đăng ký MBean và ObjectName

Để JMX client tìm thấy đối tượng, đăng ký nó vào `MBeanServer` với một `ObjectName` duy nhất trong server.

```java
package com.example.monitoring;

import java.lang.management.ManagementFactory;
import javax.management.Attribute;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class JmxDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        JobMonitor monitor = new JobMonitor();

        ObjectName name = new ObjectName(
                "com.example.monitoring:type=JobMonitor,name=primary"
        );

        server.registerMBean(monitor, name);

        monitor.recordCompletedJob();
        Object count = server.getAttribute(name, "ProcessedCount");
        System.out.println("ProcessedCount = " + count);

        server.setAttribute(name, new Attribute("Enabled", false));
        server.invoke(name, "reset", new Object[0], new String[0]);
    }
}
```

Các API JMX liên quan:

- `registerMBean(object, objectName)`: đăng ký đối tượng.
- `getAttribute(name, attribute)`: đọc thuộc tính.
- `setAttribute(name, attribute)`: ghi thuộc tính có setter.
- `invoke(name, operation, args, signature)`: gọi operation.
- `getMBeanInfo(name)`: đọc metadata công bố.
- `unregisterMBean(name)`: gỡ đăng ký khi cần.

Lỗi `NotCompliantMBeanException` thường gợi ý interface/class không đáp ứng contract MBean. `InstanceAlreadyExistsException` cho biết `ObjectName` đã tồn tại trong server.

## 5. Phân biệt hai quy ước tên

Có hai cơ chế thường bị nhầm lẫn:

**Tên giao diện Java**: `JobMonitorMBean` là hợp đồng quản lý của lớp `JobMonitor`. Quy tắc dựa trên tên lớp và interface Java.

**JMX ObjectName**: `com.example.monitoring:type=JobMonitor,name=primary` là định danh runtime của một instance trong `MBeanServer`. Cú pháp thường là `domain:key=value,key=value` và không bị bắt buộc phải trùng package hoặc class name; cần chọn domain và các key nhất quán cho vận hành.

| Thành phần | Ví dụ | Chức năng |
| --- | --- | --- |
| Implementation | `JobMonitor` | Chứa trạng thái và logic |
| Standard MBean interface | `JobMonitorMBean` | Quy định API JMX |
| JMX ObjectName | `com.example.monitoring:type=JobMonitor,name=primary` | Định danh đăng ký |
| Spring bean name | `jobMonitor` | Định danh bean trong IoC container |

Hai instance của cùng loại có thể đăng ký khác `ObjectName`: `name=primary` và `name=secondary`. Nhưng hai MBean không được trùng hoàn toàn `ObjectName` trên cùng một server. Khi giá trị property chứa ký tự đặc biệt, áp dụng cú pháp quote/escape của `ObjectName` thay vì ghép chuỗi tùy tiện.

## 6. Dùng với Spring Framework

Trong Spring, `MBeanExporter` đăng ký các bean được chỉ định vào `MBeanServer`. Ví dụ cấu hình Java sau dùng sẵn platform MBean server:

```java
package com.example.monitoring;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxConfiguration {
    @Bean
    public JobMonitor jobMonitor() {
        return new JobMonitor();
    }

    @Bean
    public MBeanServer mBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter mBeanExporter(
            JobMonitor monitor, MBeanServer mBeanServer) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mBeanServer);
        exporter.setBeans(Map.of(
                "com.example.monitoring:type=JobMonitor,name=primary",
                monitor
        ));
        return exporter;
    }
}
```

Cấu hình trên minh họa **Spring Framework thuần**: đối tượng `JobMonitor` được quản lý bởi Spring IoC, còn `MBeanExporter` đưa nó vào registry JMX. Trong ứng dụng Spring Boot có auto-configuration JMX, kiểm tra cấu hình đang hoạt động trước khi bổ sung exporter/server để tránh đăng ký trùng. Một đối tượng là Spring bean không tự động đồng nghĩa với việc nó đã được xuất thành MBean.

Spring còn có `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation` kết hợp exporter hỗ trợ annotation. Đây là cách Spring tạo metadata JMX theo annotation; nó khác với quy ước tên interface của Standard MBean. Nếu muốn API quản lý tường minh, dễ dùng ngoài Spring, Standard MBean có lợi thế vì chỉ dùng JMX chuẩn.

## 7. Kiểm tra với JConsole

Dùng JDK có `jconsole`, khởi chạy ứng dụng, mở JConsole, kết nối đến tiến trình đang chạy và chuyển sang tab **MBeans**. Tìm domain `com.example.monitoring`, sau đó tìm `type=JobMonitor,name=primary` theo cây hiển thị.

Thực hiện từng bước:

1. Đọc `ProcessedCount`, gọi `recordCompletedJob()` qua luồng ứng dụng và quan sát bộ đếm tăng.
2. Đặt `Enabled=false`; xử lý thêm một job và xác minh bộ đếm không tăng.
3. Bật `Enabled=true`, xử lý job và xác minh bộ đếm tiếp tục tăng.
4. Gọi operation `reset`; kiểm tra `ProcessedCount` trở về 0.
5. Quan sát `recordCompletedJob()` không có trong danh sách operations, vì nó không được khai báo trong interface quản lý.

Nếu không thấy MBean, kiểm tra tiến trình JVM đang kết nối, trạng thái exporter và `ObjectName` thực tế. Nếu có `NotCompliantMBeanException`, rà lại class/interface chuẩn, phương thức public và kiểu dữ liệu. Nếu tên đã tồn tại, xử lý việc đăng ký trùng hoặc vòng đời context.

## 8. So sánh với MXBean và Dynamic MBean

| Loại | Cơ chế | Trường hợp dùng |
| --- | --- | --- |
| Standard MBean | Interface `ClassNameMBean` theo convention | Quản trị đơn giản, contract tường minh |
| MXBean | Interface hậu tố `MXBean` hoặc được đánh dấu `@MXBean`; mapping sang open types | Dữ liệu thuận tiện cho client JMX |
| Dynamic MBean | Tự implement `DynamicMBean`, cung cấp metadata từ `getMBeanInfo()` | Metadata và operations cần thiết lập động |

## 9. Lưu ý khi thiết kế hợp đồng quản lý

Coi MBean là API vận hành. Chỉ công bố các thuộc tính và thao tác cần thiết, tránh lộ mật khẩu/token hoặc operation nghiệp vụ nguy hiểm. JMX client có thể gọi đồng thời với các thread ứng dụng nên phải dùng cơ chế đồng bộ thích hợp. Ví dụ `AtomicInteger` và `volatile` hỗ trợ trường hợp đơn giản; với nhiều trạng thái liên quan, cần bảo vệ nhất quán bằng cơ chế mạnh hơn.

Một `ObjectName` có domain và thuộc tính rõ ràng giúp phân biệt instance khi chạy nhiều service. Quản lý unregister/lifecycle khi khởi động lại context. Nếu bật remote JMX, cấu hình authentication, mã hóa kết nối và giới hạn network theo môi trường; ví dụ local ở trên chưa tạo remote endpoint.

## 10. Bài tập

Tạo `CacheMonitorMBean` và `CacheMonitor` có thuộc tính `CacheSize` chỉ đọc, thuộc tính `RefreshEnabled` đọc/ghi, operation `clearCache()`. Đăng ký ở `com.example.monitoring:type=CacheMonitor,name=local`. Dùng JConsole kiểm tra interface công bố đúng ba thành phần. Tạo instance thứ hai với `name=secondary`, sau đó thử đăng ký trùng `name=local` để giải thích lỗi.

**Ghi nhớ:** Quy ước `ClassNameMBean` xác định interface quản lý của Standard MBean; `ObjectName` phân biệt đối tượng đã đăng ký trong JMX; Spring `MBeanExporter` hỗ trợ tích hợp bean vào `MBeanServer`.
