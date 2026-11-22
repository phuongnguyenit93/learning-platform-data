# Kiểm tra registry bằng JConsole hoặc công cụ JMX tương đương

## Mục tiêu

Sau bài học, bạn có thể xác định `MBeanServer` đang chạy trong JVM, mở registry JMX bằng JConsole hoặc công cụ tương đương, kiểm tra `ObjectName`, attribute, operation và metadata của một MBean, đồng thời phân biệt lỗi đăng ký MBean với lỗi kết nối, xác thực hoặc hiển thị của client. Ví dụ tập trung vào Spring Framework JMX nhưng dùng các khái niệm và API chuẩn Java Management Extensions (JMX).

## 1. Registry JMX là gì?

`MBeanServer` là nơi đăng ký và tra cứu các Managed Bean (MBean) của một JVM. Mỗi MBean đã đăng ký được định danh bằng `ObjectName` duy nhất trong **cùng một** `MBeanServer`, chẳng hạn:

```text
com.example.monitoring:type=JobMonitor,name=primary
```

Một `ObjectName` có dạng tổng quát `domain:key=value,key=value`; `domain` thường thể hiện namespace của ứng dụng, còn các key property phân biệt loại và instance. Thứ tự trình bày các property có thể được công cụ chuẩn hóa, vì vậy nên đối chiếu `ObjectName` theo ý nghĩa của domain và các key thay vì chỉ nhìn thứ tự chuỗi.

Khi mở tab **MBeans** trong JConsole, cây bên trái thể hiện các domain và MBean đã đăng ký. Việc nhìn thấy tiến trình Java ở danh sách kết nối **không** tự chứng minh rằng MBean ứng dụng đã được đăng ký. Phải tìm đúng tên trong registry và xác minh metadata có sẵn.

Trong Spring Framework, một bean tồn tại trong `ApplicationContext` cũng chưa chắc xuất hiện ở JMX. Nó cần được đăng ký với `MBeanServer` trực tiếp, hoặc được exporter như `MBeanExporter` / `AnnotationMBeanExporter` xuất ra. Nếu hệ thống có nhiều `MBeanServer` hoặc nhiều JVM, cần chắc chắn công cụ đang kết nối tới server chứa MBean mong muốn.

## 2. Chuẩn bị một MBean để quan sát

Ví dụ sau tạo Standard MBean với hai attribute và một operation. Tạo hai file Java cùng package.

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
    private final AtomicInteger processed = new AtomicInteger();
    private volatile boolean enabled = true;

    public void recordProcessedJob() {
        if (enabled) {
            processed.incrementAndGet();
        }
    }

    @Override
    public int getProcessedCount() {
        return processed.get();
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
        processed.set(0);
    }
}
```

Interface `JobMonitorMBean` quy định hợp đồng JMX: `ProcessedCount` có getter nên chỉ đọc, `Enabled` có getter và setter nên đọc/ghi, `reset` là operation. Method `recordProcessedJob` chỉ phục vụ nội bộ; nó không hiện như operation quản trị vì không được khai báo trong interface Standard MBean.

Đăng ký bằng Java JMX API với server nền tảng của JVM:

```java
package com.example.monitoring;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class JmxRegistryDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
                "com.example.monitoring:type=JobMonitor,name=primary");

        JobMonitor monitor = new JobMonitor();
        server.registerMBean(monitor, name);

        System.out.println("PID JVM: " + ProcessHandle.current().pid());
        System.out.println("Registered: " + server.isRegistered(name));

        while (true) {
            monitor.recordProcessedJob();
            Thread.sleep(1000);
        }
    }
}
```

Chạy chương trình bằng JDK, giữ tiến trình hoạt động để JConsole có thể kết nối. Vòng lặp ở đây chỉ để duy trì ví dụ và tạo số đếm dễ quan sát; trong ứng dụng thật, số liệu nên phản ánh hoạt động nghiệp vụ thực. `registerMBean` có thể ném `NotCompliantMBeanException` nếu class không tuân thủ contract Standard MBean hoặc `InstanceAlreadyExistsException` nếu tên đã đăng ký trùng.

## 3. Kết nối bằng JConsole

JConsole là công cụ giám sát JMX đi kèm nhiều bản phân phối JDK. Nếu có sẵn JDK và tiện ích này, khởi động qua lệnh:

```bash
jconsole
```

Trong màn hình kết nối:

1. Chọn **Local Process** và tiến trình JVM đang chạy ví dụ. Đối chiếu PID in trên stdout nếu có nhiều tiến trình Java.
2. Chọn **Connect**. Tùy nền tảng và cấu hình, công cụ có thể yêu cầu xác nhận kết nối không an toàn hoặc quyền truy cập tiến trình.
3. Mở tab **MBeans**.
4. Trong cây bên trái, mở domain `com.example.monitoring`.
5. Chọn MBean có property `type=JobMonitor`, `name=primary` (cách phân nhóm và thứ tự node có thể khác giữa các JMX client).
6. Kiểm tra khu vực **Attributes**, **Operations**, **Info** hoặc các phần tương ứng của giao diện.

Dấu hiệu đăng ký thành công: cây MBeans có đúng entry mong muốn; khu vực metadata cho thấy các attribute và operation được interface công bố. Một số màn hình cần bấm **Refresh** hoặc chọn lại node để thấy dữ liệu cập nhật.

Nếu không có tiện ích `jconsole` trong PATH, kiểm tra `JAVA_HOME/bin/jconsole` và gói JDK đang dùng. Runtime image tối giản hoặc môi trường container có thể không kèm giao diện đồ họa; khi đó dùng client JMX hỗ trợ kết nối phù hợp hoặc kiểm tra bằng API ở mục tiếp theo.

## 4. Kiểm tra attributes, operations và metadata

Với MBean ở ví dụ, JConsole thường hiển thị các phần tử:

| Nhóm | Tên | Ý nghĩa | Cách kiểm tra |
| --- | --- | --- | --- |
| Attribute | `ProcessedCount` | Số tác vụ đã ghi nhận | Đọc lần lượt; giá trị tăng theo vòng lặp |
| Attribute | `Enabled` | Cờ cho phép ghi nhận tác vụ | Đổi thành `false`; đếm không tăng |
| Operation | `reset` | Đặt số đếm về 0 | Invoke và đọc lại bộ đếm |
| Metadata | Tên, kiểu và quyền truy cập | Hợp đồng quản lý đã được introspect | Kiểm tra kiểu `int`, `boolean`, khả năng read/write |

Khi `Enabled=false`, tiến trình vẫn chạy nhưng `recordProcessedJob` không tăng bộ đếm. Sau khi `reset`, `ProcessedCount` trở về 0 và sẽ tiếp tục tăng nếu `Enabled=true`. Thứ tự click và các nút invoke thay đổi theo phiên bản JConsole.

Phải phân biệt **attribute** và **operation**. JMX attribute có thể xuất phát từ getter/setter; operation là method có thể invoke theo signature. Ví dụ `reset()` không phải getter và sẽ nằm ở phần operations. Việc một method tồn tại trong lớp Java không đủ để xuất hiện nếu không có trong hợp đồng MBean.

Không thử thay đổi attribute hoặc gọi operation trên JVM sản xuất nếu chưa hiểu tác động. Một số operation có thể làm thay đổi trạng thái thật, reset thống kê hoặc ảnh hưởng đến dịch vụ.

## 5. Kiểm tra registry bằng JMX API

Khi không thể dùng giao diện đồ họa, bạn có thể đọc registry trong JVM qua `MBeanServer`:

```java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class InspectJmx {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
                "com.example.monitoring:type=JobMonitor,name=primary");

        System.out.println("Registered? " + server.isRegistered(name));

        Set<ObjectName> names = server.queryNames(
                new ObjectName("com.example.monitoring:*"), null);
        for (ObjectName item : names) {
            System.out.println(item.getCanonicalName());
        }

        if (server.isRegistered(name)) {
            MBeanInfo info = server.getMBeanInfo(name);
            for (MBeanAttributeInfo a : info.getAttributes()) {
                System.out.printf(
                        "Attribute: %s type=%s readable=%s writable=%s%n",
                        a.getName(), a.getType(), a.isReadable(), a.isWritable());
            }
            for (MBeanOperationInfo operation : info.getOperations()) {
                System.out.println("Operation: " + operation.getName());
            }
            System.out.println(
                    "Count = " + server.getAttribute(name, "ProcessedCount"));
        }
    }
}
```

**Phạm vi quan trọng:** mã trên dùng `getPlatformMBeanServer()` của chính tiến trình thực thi. Nếu chạy `InspectJmx` như **một JVM thứ hai**, nó không thể tự động thấy MBean đã đăng ký trong JVM chạy `JmxRegistryDemo`. Để kiểm tra đúng, chạy logic này **bên trong cùng JVM** (ví dụ tại một endpoint debug an toàn, diagnostic action hoặc đoạn mã gọi trong ứng dụng), hoặc dùng `JMXConnector` để kết nối tới JMX server từ xa nếu endpoint đã được cấu hình.

Để tìm toàn bộ tên có domain ứng dụng, `queryNames(new ObjectName("com.example.monitoring:*"), null)` trả về tập tên đáp ứng pattern. `isRegistered(name)` giúp kiểm tra cụ thể tên có tồn tại. `getMBeanInfo` trả metadata theo hợp đồng JMX. Việc attribute/operation có mặt trong metadata chứng minh MBean server đang công bố API đó, nhưng không chứng minh mọi thao tác sẽ thành công trong mọi trạng thái runtime.

## 6. Công cụ JMX tương đương

Ngoài JConsole, có thể dùng **VisualVM** cùng khả năng MBeans/JMX phù hợp với phiên bản và plugin đang cài, hoặc client quản lý JMX khác có chức năng duyệt MBean registry. Những công cụ này thường cung cấp danh sách tiến trình hay kết nối JMX, cây `ObjectName`, thuộc tính và operation.

Khi sử dụng công cụ thay thế, giữ cùng một quy trình xác minh:

1. Xác định đúng JVM hoặc JMX service URL, không chỉ cùng tên service.
2. Tìm chính xác domain và key properties trong `ObjectName`.
3. Đọc metadata, đối chiếu tên và kiểu attribute/operation.
4. Đọc một thuộc tính không gây side effect, đối chiếu với trạng thái ứng dụng.
5. Chỉ gọi một operation an toàn trong môi trường thử nghiệm để xác nhận request đến đúng MBean.

Spring Framework không buộc dùng một trình xem JMX cụ thể. Phần giao tiếp quản lý tuân theo hợp đồng Java JMX, nên JConsole và client tương thích có thể truy cập cùng registry nếu có cùng kết nối và quyền.

## 7. Spring Framework: làm sao biết exporter đã đăng ký?

Đối với Spring bean được cấu hình để xuất ra JMX:

- Kiểm tra ứng dụng có cấu hình `MBeanExporter`, `AnnotationMBeanExporter` hoặc cơ chế tương đương.
- Đối chiếu tên bean và `ObjectName` được exporter dùng; tên trong Spring container không tự quyết định domain/key của JMX.
- Bảo đảm exporter nhắm đến đúng `MBeanServer`. Ứng dụng dùng platform server sẽ thuận tiện cho JConsole truy cập theo tiến trình.
- Kiểm tra quá trình khởi động có báo lỗi registration, trùng tên hoặc MBean không hợp lệ hay không.
- Với Spring Boot, tính năng JMX và auto-export chịu ảnh hưởng cấu hình Boot; kiểm tra thiết lập đang dùng trước khi thêm exporter thủ công để tránh đăng ký trùng.

Ví dụ cấu hình Spring Framework đăng ký Standard MBean:

```java
package com.example.monitoring;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class MonitoringJmxConfiguration {
    @Bean
    public JobMonitor jobMonitor() {
        return new JobMonitor();
    }

    @Bean
    public MBeanServer mBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter monitorExporter(
            JobMonitor jobMonitor, MBeanServer mBeanServer) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mBeanServer);
        exporter.setBeans(Map.of(
                "com.example.monitoring:type=JobMonitor,name=primary",
                jobMonitor));
        return exporter;
    }
}
```

Spring sẽ quản lý vòng đời exporter; đừng đồng thời đăng ký cùng instance/`ObjectName` bằng `registerMBean` thủ công và exporter trong cùng ứng dụng. Nếu sử dụng cấu hình này, chỉ chạy một cơ chế đăng ký để tránh lỗi trùng.

## 8. Chẩn đoán khi không thấy MBean

| Triệu chứng | Khả năng cần kiểm tra | Hành động |
| --- | --- | --- |
| Không thấy tiến trình Java | Khác user OS, quyền attach, container/host hoặc JVM đã dừng | Kiểm tra PID, tài khoản, môi trường chạy và chính sách attach |
| Kết nối được nhưng thiếu domain ứng dụng | MBean chưa đăng ký, sai `MBeanServer`, sai JVM | Xem log exporter, gọi `isRegistered` ngay trong JVM đúng |
| Có domain nhưng thiếu `ObjectName` | Tên đã đặt khác hoặc đăng ký thất bại | Dùng `queryNames`, so khớp domain/key |
| Có MBean nhưng thiếu attribute/operation | Interface/metadata không công bố method hoặc đặt sai quy ước | Kiểm tra `*MBean`, getter/setter, annotation metadata |
| `NotCompliantMBeanException` | MBean không đáp ứng contract | Kiểm tra interface public, tên class/interface và kiểu exposed |
| `InstanceAlreadyExistsException` | Trùng `ObjectName` trong server | Thay instance name có chủ đích hoặc sửa vòng đời exporter |
| Attribute không ghi được | Không có setter hoặc chỉ đọc | Dùng metadata `isWritable()`, kiểm tra đúng loại dữ liệu |
| Invoke thất bại | Sai signature, quyền truy cập hoặc operation ném lỗi | Đọc `MBeanOperationInfo`, kiểm tra log và nguyên nhân |
| Remote connection từ chối | Chưa bật endpoint, firewall, xác thực hoặc cấu hình RMI/port | Xác nhận JMX service URL và cấu hình mạng/bảo mật |

JMX local và remote có những điều kiện kết nối khác nhau. Một kết nối local thành công không chứng minh truy cập từ máy khác sẽ hoạt động. Với remote JMX, cần cấu hình xác thực, mã hóa và hạn chế network phù hợp; tránh mở endpoint quản trị công khai chỉ để dùng JConsole.

## 9. Quy trình xác minh lặp lại được

Để có bằng chứng rõ ràng cho một MBean trong ứng dụng Spring, ghi lại:

1. PID/tên tiến trình Java và công cụ client đang dùng.
2. `ObjectName` đầy đủ (domain và các key properties).
3. Kết quả `isRegistered` hoặc vị trí tương ứng trong cây registry.
4. Danh sách attribute, kiểu dữ liệu, khả năng đọc/ghi và operation.
5. Một giá trị thuộc tính thực tế trước/sau thay đổi trạng thái thử nghiệm an toàn.
6. Thời điểm và môi trường chạy, vì MBean có thể được đăng ký/gỡ trong vòng đời ứng dụng.

Không nên suy luận chỉ từ việc JConsole mở được ứng dụng. Cần xác minh cả danh tính MBean và hợp đồng quản lý đúng với API dự kiến.

## 10. Bài tập thực hành

Tạo hai instance `JobMonitor` dưới các tên:

```text
com.example.monitoring:type=JobMonitor,name=primary
com.example.monitoring:type=JobMonitor,name=secondary
```

Mở JConsole và chứng minh cả hai entry tồn tại độc lập. Thay `Enabled=false` của `primary` rồi quan sát `secondary` vẫn xử lý theo trạng thái riêng. Ghi lại danh sách attributes/operations và gọi `reset` cho một instance. Tiếp đó, cố đăng ký MBean thứ ba với `ObjectName` đã có và giải thích lỗi. Cuối cùng, chạy `queryNames` ngay trong JVM ứng dụng và đối chiếu kết quả với cây JConsole.

**Ghi nhớ:** Kiểm tra registry JMX nghĩa là xác minh đúng JVM, đúng `MBeanServer`, đúng `ObjectName` và đúng metadata/giá trị của MBean. JConsole là giao diện thuận tiện, còn JMX API cho phép tự động hóa các bước kiểm chứng tương đương.
