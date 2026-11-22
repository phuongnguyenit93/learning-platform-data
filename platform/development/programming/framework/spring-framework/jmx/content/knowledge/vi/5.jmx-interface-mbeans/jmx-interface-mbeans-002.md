# Thuộc tính chỉ đọc, chỉ ghi và đọc–ghi trong giao diện MBean

## 1. Vì sao MBean cần phân biệt quyền đọc và ghi?

Một MBean (Managed Bean) là đối tượng cung cấp giao diện quản trị cho tài nguyên Java đang chạy. Qua JMX, người vận hành hoặc công cụ như JConsole có thể xem trạng thái hiện tại và, khi được cho phép, thay đổi một phần cấu hình runtime.

Nhưng không phải thông tin nào cũng được phép thay đổi. Chẳng hạn:

- Số yêu cầu đã xử lý là **thông tin quan sát**; việc đọc có ý nghĩa, còn tự ý ghi số đếm thường không hợp lý.
- Một lệnh nạp giá trị cấu hình một chiều có thể cần **nhận giá trị mới** nhưng không công bố giá trị đang giữ vì mục đích bảo mật hoặc vì dữ liệu không có getter thích hợp.
- Ngưỡng cảnh báo có thể cần **đọc để kiểm tra** và **ghi để điều chỉnh** trong quá trình vận hành.

JMX giải quyết sự khác biệt đó bằng khái niệm **attribute** với hai khả năng độc lập: `isReadable` và `isWritable`. Từ hai cờ này ta có ba tổ hợp attribute hợp lệ trong thực tế: chỉ đọc, chỉ ghi và đọc–ghi.

```text
                    Giao diện quản trị MBean
                              |
                         Attribute
                              |
                  +-----------+-----------+
                  |                       |
              Đọc được?                Ghi được?
                  |                       |
           getAttribute(...)        setAttribute(...)
                  |                       |
           Trả trạng thái          Thay đổi trạng thái
                  +-----------+-----------+
                              |
                         MBeanServer
                              |
                   Đối tượng ứng dụng
```

**Mấu chốt:** quyền đọc/ghi ở đây là **khả năng của thuộc tính theo hợp đồng JMX**, chưa phải cơ chế xác thực và phân quyền theo từng người dùng. Nếu một thuộc tính có `isWritable=true`, JMX cho phép thực hiện lệnh ghi về mặt giao diện; bảo vệ kết nối và quyền người gọi vẫn cần được cấu hình riêng.

## 2. Cách JMX nhận ra attribute từ một Standard MBean

Với **Standard MBean**, Java dùng một interface quản trị theo quy ước `TênLớpMBean`. Ví dụ class `ServiceMonitor` triển khai `ServiceMonitorMBean`.

Trong interface, JMX sử dụng những mẫu phương thức JavaBean để nhận diện thuộc tính:

| Khai báo trong interface | Diễn giải trong JMX | Tên attribute |
|---|---|---|
| `T getX()` | Getter, hỗ trợ đọc | `X` |
| `boolean isX()` | Getter boolean, hỗ trợ đọc | `X` |
| `void setX(T value)` | Setter, hỗ trợ ghi | `X` |
| `getX()` và `setX(T)` tương thích | Đọc–ghi cùng một attribute | `X` |
| Method không theo mẫu getter/setter | Thường là operation | Theo tên method |

Đối với dạng `isX()`, kiểu trả về phải là `boolean` nguyên thủy theo quy tắc nhận dạng thuộc tính Standard MBean. Getter có dạng `getX()` không nhận tham số và có kết quả; setter có một tham số kiểu phù hợp và trả `void`.

Ví dụ:

```java
public interface ServiceMonitorMBean {
    long getRequestCount();             // read-only attribute: RequestCount
    void setMaintenanceMessage(String message); // write-only: MaintenanceMessage
    int getWarningThreshold();          // getter: WarningThreshold
    void setWarningThreshold(int value); // setter: WarningThreshold
    boolean isMaintenanceMode();        // read-only: MaintenanceMode
}
```

Nếu cặp getter/setter cùng tên nhưng không có kiểu tương thích, JMX không thể tùy ý suy đoán rằng chúng là một attribute hợp lệ. Hãy thiết kế chữ ký đơn nghĩa, thống nhất giữa interface và implementation.

**Quan trọng:** thành viên công khai trên class triển khai nhưng không xuất hiện trong interface Standard MBean sẽ không tự được công bố như một attribute của hợp đồng đó.

## 3. Thuộc tính chỉ đọc (read-only)

Thuộc tính **chỉ đọc** có getter và không có setter được export trong giao diện MBean.

```java
public interface RequestStatsMBean {
    long getTotalRequests();
    boolean isHealthy();
}
```

Khi đăng ký MBean, metadata của `TotalRequests` và `Healthy` cho biết chúng đọc được nhưng không ghi được:

```text
TotalRequests:
  readable = true
  writable = false

Healthy:
  readable = true
  writable = false
```

Client dùng:

```java
Object total = connection.getAttribute(objectName, "TotalRequests");
Object healthy = connection.getAttribute(objectName, "Healthy");
```

Trong đó `connection` là `MBeanServerConnection`, còn `objectName` định danh MBean đã được đăng ký. Không có setter tương ứng nên gọi `setAttribute(..., new Attribute("TotalRequests", ...))` sẽ bị từ chối theo khả năng ghi của thuộc tính.

**Trường hợp sử dụng:**

- Các số đo runtime: số thread, số yêu cầu, số tác vụ lỗi.
- Trạng thái sức khỏe, kết nối, phiên bản hoặc thời gian uptime.
- Giá trị cấu hình mà người vận hành chỉ cần tham khảo, không được tùy ý sửa tại runtime.

Một getter chỉ đọc vẫn có thể trả dữ liệu biến đổi theo thời gian. `read-only` **không có nghĩa immutable** và **không đảm bảo giá trị không thay đổi giữa hai lần đọc**. Nó chỉ có nghĩa JMX client không thể ghi trực tiếp qua attribute đó.

Nếu ứng dụng có operation `resetTotalRequests()`, giá trị `TotalRequests` vẫn có thể thay đổi do operation; thuộc tính vẫn là chỉ đọc vì không có setter được công bố.

### 3.1. Getter nên có đặc tính gì?

Getter được công cụ quản trị gọi mỗi khi cần hiển thị hoặc thu thập dữ liệu. Vì vậy nên:

- Trả về nhanh, tránh quét toàn bộ database hoặc gọi mạng chậm.
- Không tự tạo tác dụng phụ như xóa cache, ghi dữ liệu hay đổi cấu hình.
- Có kiểu trả về và đơn vị đo rõ ràng, ví dụ milliseconds, bytes, count.
- Tránh ném exception vì trạng thái phổ biến của hệ thống; nếu dữ liệu không sẵn sàng, cần biểu diễn điều đó bằng hợp đồng rõ ràng.
- Tránh tiết lộ mật khẩu, token hoặc dữ liệu cá nhân qua JMX.

## 4. Thuộc tính chỉ ghi (write-only)

Thuộc tính **chỉ ghi** chỉ có setter được công bố trong interface:

```java
public interface RuntimeSettingsMBean {
    void setMaintenanceMessage(String message);
}
```

Metadata tương ứng:

```text
MaintenanceMessage:
  readable = false
  writable = true
```

Client có thể ghi:

```java
connection.setAttribute(
    objectName,
    new javax.management.Attribute(
        "MaintenanceMessage",
        "Bảo trì theo lịch lúc 23:00"
    )
);
```

Nhưng đọc sẽ thất bại:

```java
connection.getAttribute(objectName, "MaintenanceMessage");
```

Phương thức `getAttribute` ném một lỗi JMX thích hợp, thường là `AttributeNotFoundException` khi thuộc tính không có khả năng đọc. Hành vi hiển thị trên JConsole cũng phụ thuộc công cụ: giao diện có thể không hiển thị giá trị hiện tại hoặc không cung cấp ô đọc cho attribute đó.

### 4.1. Khi nào nên dùng write-only?

Dùng khi người vận hành cần gửi một giá trị hoặc yêu cầu cập nhật nhưng không có lý do phù hợp để trả lại cùng giá trị qua giao diện quản trị. Ví dụ đặt một chuỗi thông báo vận hành hoặc nhận một giá trị thay thế cần xử lý nội bộ.

Tuy nhiên, **write-only không tự làm dữ liệu trở nên bí mật**. Giá trị có thể bị lộ qua kết nối không an toàn, audit log, ứng dụng hoặc các kênh khác. Không dùng setter JMX để truyền secret nếu chưa thiết kế đầy đủ bảo mật.

Nếu hành động vốn là một mệnh lệnh (ví dụ `clearCache()`, `rotateKey()`, `reloadRules()`), **operation** thường diễn đạt rõ hơn write-only attribute. Setter nên có ý nghĩa “thiết lập giá trị của thuộc tính X”, còn operation phù hợp với “thực hiện một hành động Y”.

### 4.2. Một điểm khác biệt quan trọng

Với setter không có getter, client không thể lấy lại giá trị trước/sau để đối chiếu bằng cùng attribute. Nếu cần xác nhận trạng thái hiện tại, hãy cân nhắc thêm thuộc tính chỉ đọc riêng như `getMaintenanceStatus()` hoặc một operation có kết quả thích hợp. Tránh thiết kế giao diện khiến người vận hành không biết yêu cầu cập nhật đã được áp dụng hay chưa.

## 5. Thuộc tính đọc–ghi (read-write)

Một attribute **đọc–ghi** có getter và setter được công bố đồng thời với cùng tên và kiểu tương thích:

```java
public interface AlertConfigMBean {
    int getWarningThreshold();
    void setWarningThreshold(int threshold);
}
```

Metadata:

```text
WarningThreshold:
  readable = true
  writable = true
```

Client xem và thay đổi:

```java
int oldValue = (Integer) connection.getAttribute(
    objectName, "WarningThreshold"
);

connection.setAttribute(
    objectName,
    new javax.management.Attribute("WarningThreshold", 75)
);

int newValue = (Integer) connection.getAttribute(
    objectName, "WarningThreshold"
);
```

Việc đọc lại giúp xác nhận giá trị thực tế đã được MBean trả về. Nó không tự đảm bảo rằng thay đổi đã được lưu bền vững sau khi ứng dụng restart, hoặc rằng không có tác nhân khác vừa cập nhật cùng attribute.

**Trường hợp sử dụng:**

- Ngưỡng cảnh báo, giới hạn hoặc hệ số điều chỉnh được phép thay đổi runtime.
- Chế độ maintenance/debug được vận hành bật/tắt có kiểm soát.
- Tùy chọn cấu hình có validation, đơn vị đo và phạm vi rõ ràng.

Setter phải tự kiểm tra tính hợp lệ của giá trị. Ví dụ, `WarningThreshold = -10` có thể vô nghĩa trong bài toán cụ thể; JMX không biết quy tắc nghiệp vụ nếu implementation không thực thi.

## 6. Ví dụ Java hoàn chỉnh: cả ba loại thuộc tính

Ví dụ dưới đây dùng Java SE và platform MBeanServer, có thể chạy độc lập với Spring. Mục tiêu là quan sát trực tiếp ba kiểu attribute và phản ứng khi đọc/ghi.

### 6.1. Interface quản trị

```java
// RuntimeControlMBean.java
public interface RuntimeControlMBean {
    // READ-ONLY: chỉ cung cấp getter.
    long getProcessedRequests();

    // WRITE-ONLY: chỉ cung cấp setter.
    void setMaintenanceMessage(String message);

    // READ-WRITE: getter và setter.
    int getWarningThreshold();
    void setWarningThreshold(int threshold);

    // READ-ONLY boolean theo mẫu isX().
    boolean isMaintenanceMode();

    // Operation độc lập với thuộc tính.
    void resetRequestCounter();
}
```

### 6.2. Implementation

```java
// RuntimeControl.java
import java.util.Objects;
import java.util.concurrent.atomic.AtomicLong;

public class RuntimeControl implements RuntimeControlMBean {
    private final AtomicLong processedRequests = new AtomicLong();
    private volatile String maintenanceMessage = "";
    private volatile int warningThreshold = 80;
    private volatile boolean maintenanceMode;

    public void recordRequest() {
        processedRequests.incrementAndGet();
    }

    @Override
    public long getProcessedRequests() {
        return processedRequests.get();
    }

    @Override
    public void setMaintenanceMessage(String message) {
        String normalized = Objects.requireNonNull(message, "message").trim();
        if (normalized.length() > 200) {
            throw new IllegalArgumentException(
                "Maintenance message is too long"
            );
        }
        maintenanceMessage = normalized;
        maintenanceMode = !normalized.isEmpty();
    }

    @Override
    public int getWarningThreshold() {
        return warningThreshold;
    }

    @Override
    public void setWarningThreshold(int threshold) {
        if (threshold < 1 || threshold > 100) {
            throw new IllegalArgumentException(
                "WarningThreshold must be between 1 and 100"
            );
        }
        warningThreshold = threshold;
    }

    @Override
    public boolean isMaintenanceMode() {
        return maintenanceMode;
    }

    @Override
    public void resetRequestCounter() {
        processedRequests.set(0);
    }
}
```

Một số điểm thiết kế trong implementation:

- `AtomicLong` giúp tăng số đếm an toàn trong tình huống nhiều thread cùng gọi `recordRequest()`.
- `volatile` giúp cập nhật các trường đơn lẻ được nhìn thấy giữa các thread; nó không biến nhiều lệnh cập nhật trên các trường khác nhau thành một giao dịch nguyên tử.
- Setter của `WarningThreshold` kiểm tra giá trị trước khi chấp nhận.
- `maintenanceMessage` không có getter JMX công khai; ứng dụng nội bộ vẫn có thể sử dụng giá trị của trường đó khi triển khai logic phù hợp.
- `resetRequestCounter()` được công bố như operation có tác dụng thay đổi số đếm, dù `ProcessedRequests` là read-only attribute.

### 6.3. Đăng ký và kiểm tra qua MBeanServer

```java
// Main.java
import java.lang.management.ManagementFactory;
import javax.management.Attribute;
import javax.management.AttributeNotFoundException;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class Main {
    public static void main(String[] args) throws Exception {
        RuntimeControl control = new RuntimeControl();
        control.recordRequest();
        control.recordRequest();

        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
            "demo.runtime:type=RuntimeControl,name=main"
        );
        server.registerMBean(control, name);

        // Đọc metadata chính thức từ JMX.
        MBeanInfo info = server.getMBeanInfo(name);
        for (MBeanAttributeInfo attribute : info.getAttributes()) {
            System.out.printf(
                "%s: readable=%s, writable=%s, is=%s%n",
                attribute.getName(),
                attribute.isReadable(),
                attribute.isWritable(),
                attribute.isIs()
            );
        }

        // READ-ONLY: đọc được, ghi sẽ bị từ chối.
        System.out.println(
            "ProcessedRequests = " +
                server.getAttribute(name, "ProcessedRequests")
        );

        // WRITE-ONLY: ghi được, đọc sẽ bị từ chối.
        server.setAttribute(
            name,
            new Attribute("MaintenanceMessage", "Đang bảo trì")
        );
        try {
            server.getAttribute(name, "MaintenanceMessage");
        } catch (AttributeNotFoundException expected) {
            System.out.println("MaintenanceMessage is not readable");
        }

        // READ-WRITE: đọc, ghi, đọc lại.
        System.out.println(
            "Old threshold = " +
                server.getAttribute(name, "WarningThreshold")
        );
        server.setAttribute(
            name,
            new Attribute("WarningThreshold", 65)
        );
        System.out.println(
            "New threshold = " +
                server.getAttribute(name, "WarningThreshold")
        );

        // Method resetRequestCounter là operation.
        server.invoke(
            name,
            "resetRequestCounter",
            new Object[0],
            new String[0]
        );
        System.out.println(
            "After reset = " +
                server.getAttribute(name, "ProcessedRequests")
        );

        Thread.sleep(120_000L); // Đủ thời gian quan sát bằng JConsole.
    }
}
```

Lưu ba `public` type trong các file cùng tên và chạy với JDK. Ví dụ là Standard MBean bởi class `RuntimeControl` triển khai `RuntimeControlMBean` theo đúng convention.

Kết quả metadata cần thấy về mặt ý nghĩa:

| Attribute | Readable | Writable | Cách sinh ra |
|---|---|---|---|
| `ProcessedRequests` | true | false | Chỉ có `getProcessedRequests()` |
| `MaintenanceMessage` | false | true | Chỉ có `setMaintenanceMessage(String)` |
| `WarningThreshold` | true | true | Có cả getter và setter |
| `MaintenanceMode` | true | false | Chỉ có `isMaintenanceMode()` |

Trường `is` trong `MBeanAttributeInfo` cho biết attribute sử dụng mẫu getter `isX()` dành cho boolean; không phải cờ diễn đạt attribute có “tồn tại” hay không.

## 7. Đọc và ghi thuộc tính qua JMX API

Công cụ quản trị có thể làm việc qua `MBeanServerConnection`. Những phương thức cơ bản:

```java
Object value = connection.getAttribute(name, "WarningThreshold");

connection.setAttribute(
    name,
    new Attribute("WarningThreshold", 90)
);
```

Để đọc/ghi nhiều attribute, JMX cung cấp:

```java
AttributeList readValues = connection.getAttributes(
    name,
    new String[]{"ProcessedRequests", "WarningThreshold"}
);

AttributeList valuesToWrite = new AttributeList();
valuesToWrite.add(new Attribute("WarningThreshold", 70));

AttributeList written = connection.setAttributes(
    name,
    valuesToWrite
);
```

`getAttributes` và `setAttributes` trả kết quả theo những attribute xử lý thành công; kết quả có thể không bao gồm tất cả attribute đã yêu cầu. Cần kiểm tra danh sách trả về thay vì giả định toàn bộ batch đã hoàn tất.

**Batch attribute không mặc nhiên là transaction.** Ví dụ, đặt hai giá trị cấu hình bằng `setAttributes` không đảm bảo cả hai thay đổi đồng thời hoặc tự rollback nếu một giá trị thất bại. Với thay đổi nhiều trường đòi hỏi bất biến chung, thiết kế operation nguyên tử hoặc một cấu hình tổng hợp được validation toàn bộ trước khi áp dụng.

Các lỗi phổ biến gồm:

- `AttributeNotFoundException`: thuộc tính không có hoặc không hỗ trợ chiều truy cập được yêu cầu.
- `InvalidAttributeValueException`: kiểu/giá trị ghi không phù hợp theo JMX hoặc cách implementation xử lý.
- `MBeanException` / `RuntimeMBeanException`: getter/setter phía MBean phát sinh exception được JMX bọc tương ứng.
- `InstanceNotFoundException`: ObjectName không trỏ tới MBean đang đăng ký.
- `ReflectionException`: lỗi liên quan gọi method qua cơ chế introspection/reflection của MBean.

Đừng dùng những exception trên như phương pháp đoán xem attribute có writable hay không. Trước khi thao tác, đọc metadata để biết khả năng được công bố.

## 8. Đọc metadata: nguồn sự thật của client

JMX cho phép client tìm hiểu trước một MBean hỗ trợ gì:

```java
MBeanInfo info = connection.getMBeanInfo(name);

for (MBeanAttributeInfo attr : info.getAttributes()) {
    String access;
    if (attr.isReadable() && attr.isWritable()) {
        access = "read-write";
    } else if (attr.isReadable()) {
        access = "read-only";
    } else if (attr.isWritable()) {
        access = "write-only";
    } else {
        access = "neither"; // Không phải attribute hữu dụng để thao tác.
    }

    System.out.println(
        attr.getName() + " (" + attr.getType() + "): " + access
    );
}
```

Metadata giúp công cụ tạo UI phù hợp:

```text
Readable + !Writable  -> hiển thị giá trị, không cho sửa
!Readable + Writable  -> cho nhập giá trị, không hiển thị current value
Readable + Writable   -> hiển thị + điều khiển nhập giá trị mới
```

Metadata cũng chứa kiểu, mô tả và cờ getter `isX()`. Đối với Dynamic MBean, metadata được cung cấp trực tiếp bởi implementation; với Standard MBean, JMX thường tạo metadata từ interface quản trị.

Hãy nhớ rằng **metadata có thể xác nhận hình thức API, không thể tự xác nhận logic an toàn của setter**. Dù `WarningThreshold` có `isWritable=true`, việc ghi `999` có thể bị validation từ chối; một setter được công bố cũng có thể không áp dụng thay đổi do trạng thái runtime.

## 9. Phân biệt “writable” và “được phép ghi”

Hai câu hỏi cần trả lời độc lập:

1. **MBean có công bố khả năng ghi không?** `MBeanAttributeInfo.isWritable()`.
2. **Caller này có quyền gọi lệnh ghi không?** Phụ thuộc vào connector, cấu hình xác thực/phân quyền, network access và các lớp bảo vệ bổ sung.

Ví dụ một attribute được thiết kế đọc–ghi nhưng tài khoản monitoring chỉ được đọc. Metadata có thể vẫn mô tả attribute là writable vì đó là hợp đồng của MBean; bảo mật thực tế hạn chế người dùng monitoring. Ngược lại, một administrator được xác thực cũng không thể dùng `setAttribute` để ghi thuộc tính vốn là read-only theo hợp đồng.

Không nên “bảo vệ” một giá trị bằng cách bỏ getter nhưng vẫn cho phép ghi tùy ý qua connector công khai. Write-only đơn thuần chỉ loại bỏ chiều đọc trên giao diện, không kiểm soát người ghi.

Các thao tác thay đổi trạng thái nên có nhật ký audit thích hợp, quyền tối thiểu và cơ chế khôi phục khi cần. Đặc biệt thận trọng với remote JMX/RMI và thiết lập mạng, TLS, authentication; tránh mở kết nối quản trị ra Internet.

## 10. Spring Framework: xuất thuộc tính có phân quyền đọc/ghi

Spring hỗ trợ JMX export bằng `MBeanExporter` và bộ annotation trong `org.springframework.jmx.export.annotation`. Khi dùng annotation-based export với cấu hình thích hợp, `@ManagedAttribute` đánh dấu accessor được phơi bày cho giao diện quản trị.

Ví dụ đơn giản:

```java
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(objectName = "demo.spring:type=RuntimeSettings")
public class RuntimeSettings {
    private final AtomicLong processedRequests = new AtomicLong();
    private volatile int warningThreshold = 80;
    private volatile String maintenanceMessage = "";

    public void recordRequest() {
        processedRequests.incrementAndGet();
    }

    @ManagedAttribute(description = "Number of processed requests")
    public long getProcessedRequests() {
        return processedRequests.get();
    }

    @ManagedAttribute(description = "Runtime warning threshold")
    public int getWarningThreshold() {
        return warningThreshold;
    }

    @ManagedAttribute(description = "Runtime warning threshold")
    public void setWarningThreshold(int warningThreshold) {
        if (warningThreshold < 1 || warningThreshold > 100) {
            throw new IllegalArgumentException("Range: 1..100");
        }
        this.warningThreshold = warningThreshold;
    }

    @ManagedAttribute(description = "Maintenance notice")
    public void setMaintenanceMessage(String maintenanceMessage) {
        this.maintenanceMessage = maintenanceMessage;
    }

    @ManagedOperation(description = "Reset request counter")
    public void resetRequestCounter() {
        processedRequests.set(0);
    }
}
```

Đoạn code khai báo:

- `ProcessedRequests`: chỉ đọc vì getter được đánh dấu.
- `WarningThreshold`: đọc–ghi vì cả getter và setter đều được đánh dấu.
- `MaintenanceMessage`: chỉ ghi vì chỉ setter được đánh dấu.
- `resetRequestCounter`: operation vì dùng `@ManagedOperation`.

**Điều kiện:** các annotation phải được xử lý bởi cấu hình JMX exporter phù hợp. Trong Spring Framework thuần có thể bật cơ chế export qua `@EnableMBeanExport` trong cấu hình Java:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfig {
}
```

Ứng dụng cần có Spring Context và các dependency phù hợp. Tùy phiên bản Spring Boot, JMX auto-configuration và thuộc tính `spring.jmx.enabled` có thể quyết định việc export. Hãy kiểm tra metadata của MBean thực tế để xác nhận mức độ read/write thay vì suy luận từ tên method hay trạng thái `@Component`.

### 10.1. Sự khác biệt giữa Spring annotation và Standard MBean

Standard MBean rút hợp đồng từ **interface** kiểu `SomethingMBean`. Spring annotation-based export có thể chọn accessor từ **bean** và metadata annotation, tùy assembler/exporter được cấu hình. Không đồng nhất hai cơ chế:

```text
Standard MBean:
  Management interface -> JMX introspection -> MBeanInfo

Spring annotation export:
  Bean + @ManagedResource/@ManagedAttribute
       -> exporter/assembler -> MBeanInfo
```

Trong cả hai trường hợp, client đều dùng `MBeanServerConnection` và `MBeanAttributeInfo` để kiểm tra giao diện cuối cùng.

## 11. Read/write không phải immutable, atomic hay persistent

Có ba nhầm lẫn phổ biến khi thiết kế attribute:

**Read-only ≠ immutable.** Bộ đếm `ProcessedRequests` tiếp tục thay đổi bởi thread nghiệp vụ. Người gọi JMX không thể set số đếm qua attribute, nhưng trạng thái không bất biến.

**Read-write ≠ thao tác nguyên tử giữa nhiều attribute.** Một getter có thể trả về giá trị trước khi thread khác cập nhật. Hai lần gọi set có thể bị xen kẽ. Nếu nhiều thuộc tính phải thay đổi đồng bộ, thiết kế logic đồng bộ và operation quản trị phù hợp.

**Writable ≠ persistent.** Thay đổi `WarningThreshold` trong RAM có thể mất khi ứng dụng restart. Nếu cấu hình cần được giữ, phải có cơ chế lưu vào nguồn cấu hình và xử lý hiệu lực giữa runtime/cấu hình bền vững, đồng thời ghi rõ điều này cho người vận hành.

Thêm một điểm: setter có thể nhận giá trị nhưng chuẩn hóa trước khi lưu (ví dụ trim string, clamp threshold) hoặc từ chối dữ liệu không hợp lệ. Client nên đọc lại thuộc tính đọc–ghi để quan sát giá trị hiện tại; với write-only thì cần một kênh xác nhận riêng.

## 12. Chọn attribute hay operation

Hai cơ chế thường bị nhầm lẫn:

| Ý định | Nên chọn | Lý do |
|---|---|---|
| Xem số kết nối đang mở | Read-only attribute | Giá trị trạng thái |
| Xem/chỉnh ngưỡng cảnh báo | Read-write attribute | Một tham số cấu hình có giá trị hiện hành |
| Đặt một thông báo chỉ cần nhận | Write-only attribute nếu có ý nghĩa | Không công bố getter |
| Xóa cache | Operation | Một hành động tác động đến hệ thống |
| Nạp lại file cấu hình | Operation | Tác vụ có kết quả/lỗi riêng |
| Khởi động job hoặc dừng consumer | Operation | Hành động có điều kiện, side effect đáng kể |
| Reset bộ đếm | Operation | Thay đổi trạng thái qua mệnh lệnh có chủ đích |

Một operation có thể nhận nhiều tham số và trả kết quả, trong khi setter của attribute thường nhận một giá trị tương ứng một thuộc tính. Hãy ưu tiên một hợp đồng dễ hiểu và dễ kiểm soát: quản trị viên nhìn vào metadata có thể đoán được tác động của việc đọc hoặc ghi.

## 13. Những tình huống dễ gây lỗi

### 13.1. Getter/setter tên không khớp

```java
int getWarningThreshold();
void setThreshold(int value);
```

JMX nhìn thấy hai tên property khác nhau (`WarningThreshold` và `Threshold`). Nó không tự ghép chúng thành một read-write attribute. Đổi setter thành `setWarningThreshold` nếu muốn cùng một thuộc tính.

### 13.2. Getter/setter khác kiểu

```java
int getWarningThreshold();
void setWarningThreshold(String threshold);
```

Không có hợp đồng type-safe thống nhất cho một read-write attribute. Giữ cùng kiểu Java cho cả hai hướng hoặc tách thành operation có ý nghĩa chuyển đổi riêng.

### 13.3. Tưởng setter chỉ tồn tại trong implementation là đủ

```java
public interface RuntimeControlMBean {
    int getWarningThreshold();
}

public class RuntimeControl implements RuntimeControlMBean {
    public int getWarningThreshold() { return 80; }
    public void setWarningThreshold(int value) { /* ... */ }
}
```

Ở Standard MBean, hợp đồng JMX dựa trên interface nên `WarningThreshold` vẫn là read-only. Muốn công bố quyền ghi, thêm setter vào interface và triển khai đúng chữ ký.

### 13.4. Đọc attribute write-only để xác nhận

```java
connection.setAttribute(name, new Attribute("MaintenanceMessage", "Test"));
connection.getAttribute(name, "MaintenanceMessage"); // không hỗ trợ
```

Thiết kế write-only chủ động không cho đọc. Nếu cần xác nhận, sử dụng operation trả trạng thái hoặc một attribute chỉ đọc riêng (không nhất thiết tiết lộ giá trị nhạy cảm).

### 13.5. Dùng writable attribute cho thao tác nguy hiểm

```java
void setDeleteAllData(boolean enabled);
```

API này vừa khó đoán tác động, vừa dễ bị công cụ tự động hóa thao tác sai. Một hành động phá hủy hoặc có điều kiện cần hợp đồng operation và kiểm soát bổ sung, thay vì được ngụy trang thành việc set boolean.

### 13.6. Giả định mọi UI JMX hỗ trợ write-only giống nhau

Các công cụ JMX khác nhau có thể chọn cách hiển thị attribute write-only khác nhau. Căn cứ chính xác là `MBeanInfo` và API, không chỉ nhìn một screenshot công cụ.

## 14. Bài tập thực hành

**Bài 1 — Phân loại interface.** Cho:

```java
public interface CacheControlMBean {
    int getCurrentSize();
    int getMaxSize();
    void setMaxSize(int maxSize);
    void setLoadingProfile(String profile);
    boolean isEnabled();
    void clear();
}
```

Hãy xác định: `CurrentSize` read-only; `MaxSize` read-write; `LoadingProfile` write-only; `Enabled` read-only; `clear()` là operation. Sau đó giải thích điều gì xảy ra khi client cố ghi `CurrentSize`.

**Bài 2 — Quan sát metadata.** Đăng ký một Standard MBean, gọi `getMBeanInfo()` rồi in `getName()`, `getType()`, `isReadable()`, `isWritable()`, `isIs()` cho từng attribute. So sánh với các method trong interface và kiểm tra lại sau khi sửa interface/khởi động lại ứng dụng.

**Bài 3 — Validation.** Viết setter cho `MaxConnections` với miền hợp lệ 1..500. Thử ghi `0`, `200`, `501` qua JMX. Mô tả giá trị nào được chấp nhận, giá trị nào bị từ chối, và cách client xử lý exception.

**Bài 4 — Phân biệt cấu hình runtime và cấu hình bền vững.** Tạo `getWarningThreshold()`/`setWarningThreshold()`, thay đổi thành 65, restart JVM, quan sát giá trị. Sau đó đề xuất cách lưu cấu hình bền vững nếu vận hành cần giữ giá trị qua restart.

**Bài 5 — Chuyển sang Spring.** Tạo một Spring bean có `@ManagedResource`; đánh dấu một getter read-only, một setter write-only, một cặp getter/setter read-write. Bật JMX export trong cấu hình thích hợp và xem metadata qua JConsole.

## 15. Câu hỏi tự kiểm tra

1. `isReadable()` và `isWritable()` trong `MBeanAttributeInfo` mô tả điều gì?
2. Vì sao `getX()` và `setX()` cần thống nhất tên/kiểu nếu muốn tạo một thuộc tính đọc–ghi?
3. Sự khác nhau giữa read-only attribute và đối tượng thực sự bất biến là gì?
4. Client phải dùng API nào để ghi một attribute, và API nào để gọi operation?
5. Vì sao quyền ghi của attribute không thay thế authentication/authorization của remote JMX?
6. Khi nào write-only attribute hợp lý và khi nào nên dùng operation?
7. `setAttributes()` có đảm bảo transaction giữa nhiều thuộc tính không?
8. Vì sao cần đọc metadata của MBean thực tế khi sử dụng Spring export?

## 16. Kết luận

Trong JMX, **read-only** là thuộc tính chỉ có hướng đọc, **write-only** chỉ có hướng ghi, còn **read-write** cho phép cả hai. Standard MBean thể hiện các khả năng này qua chữ ký getter/setter trong interface quản trị; Spring Framework có thể công bố các accessor tương ứng qua cơ chế annotation export.

Luôn kiểm tra `MBeanAttributeInfo.isReadable()` và `isWritable()` trên MBean đã đăng ký để biết hợp đồng thực tế. Thiết kế getter nhẹ, setter có validation, phân biệt attribute với operation và bảo vệ quyền truy cập JMX sẽ giúp giao diện quản trị rõ ràng, dự đoán được và an toàn khi vận hành.
