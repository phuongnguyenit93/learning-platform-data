# Đọc và ghi attribute qua MBeanServer trong Spring Framework JMX

## 1. Mục tiêu và vị trí của MBeanServer

Một trong những thao tác quản trị phổ biến nhất với JMX là **đọc hoặc thay đổi giá trị của attribute** trên MBean. Java Management Extensions (JMX) chuẩn hóa cách trình bày trạng thái quản trị của ứng dụng dưới dạng attribute, operation và notification. `MBeanServer` là thành phần nhận các yêu cầu của client, định vị MBean bằng `ObjectName`, kiểm tra hợp đồng quản trị mà MBean công bố và thực hiện truy cập tương ứng.

Trong ứng dụng Spring Framework, một bean có thể được xuất thành MBean thông qua `MBeanExporter` hoặc cơ chế đăng ký JMX khác. Sau khi đăng ký thành công, đoạn mã quản trị có thể dùng trực tiếp `javax.management.MBeanServer` để làm việc với nó. API này thuộc JMX của Java; Spring hỗ trợ cấu hình và vòng đời của các đối tượng xung quanh, còn quy tắc đọc/ghi attribute do JMX xác định.

Bài này tập trung vào các thao tác:

- Định vị một MBean thông qua `ObjectName`.
- Đọc một attribute với `getAttribute` hoặc nhiều attribute với `getAttributes`.
- Ghi một attribute bằng `setAttribute` hoặc nhiều attribute với `setAttributes`.
- Hiểu quyền đọc/ghi, kiểu dữ liệu, lỗi và giới hạn của các lệnh.
- Kết hợp cấu hình Spring với thao tác JMX và xác nhận kết quả bằng cách đọc lại.

```text
Ứng dụng Spring
  ├── Spring bean quản trị
  │      └── MBeanExporter / đăng ký MBean
  │               │
  │               ▼
  └── MBeanServer ── ObjectName ── MBean
          ▲                        ├── Attribute chỉ đọc
          │                        ├── Attribute ghi được
          │                        └── Operation / Notification
          │
     Mã quản trị Java
       getAttribute()
       setAttribute()
       getAttributes()
       setAttributes()
```

Điểm phân biệt cần nhớ: **attribute không phải là một trường Java có thể truy cập tùy ý**. Nó là một phần của giao diện quản trị mà MBean đã công bố. Một MBean có thể chứa hàng chục trường nội bộ nhưng chỉ xuất một vài attribute cho JMX client.

## 2. Chuẩn bị một MBean để đọc và ghi

### 2.1. Hợp đồng Standard MBean

Một cách cơ bản để có MBean là dùng **Standard MBean** theo quy ước đặt tên của JMX: giao diện có tên `<TênLớp>MBean`, lớp triển khai giao diện đó. Thuộc tính được suy ra từ phương thức getter và setter theo JavaBeans.

Giao diện sau định nghĩa `ActiveSessions` chỉ đọc và `Enabled` đọc/ghi:

```java
package com.example.monitoring;

public interface TrafficMonitorMBean {
    int getActiveSessions();

    boolean isEnabled();

    void setEnabled(boolean enabled);
}
```

Lớp triển khai:

```java
package com.example.monitoring;

import java.util.concurrent.atomic.AtomicInteger;

public class TrafficMonitor implements TrafficMonitorMBean {
    private final AtomicInteger activeSessions = new AtomicInteger();
    private volatile boolean enabled = true;

    @Override
    public int getActiveSessions() {
        return activeSessions.get();
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    @Override
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    // Phương thức ứng dụng; không nằm trong TrafficMonitorMBean.
    public void sessionStarted() {
        activeSessions.incrementAndGet();
    }

    public void sessionFinished() {
        activeSessions.decrementAndGet();
    }
}
```

JMX thấy hai attribute:

| Attribute | Kiểu JMX | Đọc | Ghi | Cơ sở |
| --- | --- | --- | --- | --- |
| `ActiveSessions` | `int` | Có | Không | `getActiveSessions()` |
| `Enabled` | `boolean` | Có | Có | `isEnabled()` và `setEnabled(boolean)` |

Không có `setActiveSessions(int)` trong interface MBean nên JMX không cho phép ghi `ActiveSessions`. Mặt khác, một field private không tự trở thành attribute nếu không có hợp đồng quản trị tương ứng.

### 2.2. Đăng ký vào MBeanServer

Có thể đăng ký đối tượng bằng JMX thuần:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import com.example.monitoring.TrafficMonitor;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.monitoring:type=TrafficMonitor,name=Main");

if (!server.isRegistered(name)) {
    server.registerMBean(new TrafficMonitor(), name);
}
```

Ví dụ này đăng ký một Standard MBean vào platform MBeanServer. Với ứng dụng Spring, thường nên để cấu hình Spring sở hữu bean và việc xuất MBean, để vòng đời khởi tạo/hủy được quản lý rõ ràng; ví dụ trực tiếp trên minh họa API JMX cốt lõi.

Một cấu hình Spring cơ bản:

```java
package com.example.monitoring;

import java.lang.management.ManagementFactory;
import java.util.Map;

import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class MonitoringJmxConfig {

    @Bean
    public TrafficMonitor trafficMonitor() {
        return new TrafficMonitor();
    }

    @Bean
    public MBeanServer mBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter trafficMonitorExporter(
            TrafficMonitor trafficMonitor,
            MBeanServer mBeanServer) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mBeanServer);
        exporter.setBeans(Map.of(
            "com.example.monitoring:type=TrafficMonitor,name=Main",
            trafficMonitor));
        return exporter;
    }
}
```

Ở đây `MBeanExporter` nhận bean và `ObjectName` cụ thể, sau đó xuất đối tượng vào MBeanServer được cấu hình. Cần tránh đăng ký thủ công đối tượng cùng tên nếu Spring đã xuất nó: hai lần đăng ký có thể gây `InstanceAlreadyExistsException` hoặc phụ thuộc chính sách registration của exporter.

### 2.3. ObjectName là khóa truy cập

`ObjectName` sử dụng cú pháp **domain:key=value,...**:

```text
com.example.monitoring:type=TrafficMonitor,name=Main
```

Khi truy cập attribute, client phải chỉ rõ cả ObjectName lẫn tên attribute. `type` và `name` chỉ là các property định danh, không nhất thiết là attribute JMX. Do đó lời gọi `getAttribute(name, "Enabled")` đọc trạng thái do MBean xuất, còn `getAttribute(name, "name")` sẽ lỗi nếu MBean không công bố một attribute có tên `name`.

Hãy dùng tên nhất quán giữa bước đăng ký và bước truy cập. Đối với nhiều instance, định danh cần đủ thông tin tránh xung đột.

## 3. Đọc một attribute bằng getAttribute

### 3.1. Chữ ký và giá trị trả về

`MBeanServer` cung cấp phương thức:

```java
Object getAttribute(ObjectName name, String attribute)
    throws MBeanException,
           AttributeNotFoundException,
           InstanceNotFoundException,
           ReflectionException;
```

Ví dụ:

```java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.monitoring:type=TrafficMonitor,name=Main");

Object raw = server.getAttribute(name, "ActiveSessions");
int activeSessions = (Integer) raw;

System.out.println("Active sessions: " + activeSessions);
```

Tham số thứ nhất là định danh MBean; tham số thứ hai là tên attribute **phân biệt chữ hoa/chữ thường** theo metadata JMX. Giá trị trả về có kiểu `Object`, vì API có thể phục vụ nhiều MBean khác nhau. Với attribute `int`, kiểu trả về thực tế thường là `Integer`; với `boolean`, thường là `Boolean`.

```java
boolean enabled = (Boolean) server.getAttribute(name, "Enabled");
```

Không nên ép kiểu khi chưa biết hợp đồng MBean. Nếu công cụ quản trị đọc MBean không do mình kiểm soát, hãy khám phá metadata trước và xử lý các kiểu có thể gặp như `String`, kiểu số, `ObjectName`, array, `CompositeData` hoặc `TabularData`.

### 3.2. Những điều kiện để đọc thành công

Đọc attribute yêu cầu:

1. MBean đã đăng ký dưới ObjectName chính xác trong server được gọi.
2. MBean công bố attribute đúng tên.
3. Attribute được khai báo **readable**.
4. Phần cài đặt getter hoạt động và trả về giá trị hợp lệ.
5. Nếu truy cập từ xa, kết nối và quyền truy cập cho phép đọc.

Attribute có thể có tên tương tự property JavaBeans nhưng không phải mọi phương thức `getX()` trên một Spring bean đều mặc nhiên thành JMX attribute. Điều này còn phụ thuộc vào loại MBean hoặc metadata/assembler mà Spring sử dụng.

### 3.3. Đọc nhiều attribute một lần

Với một MBean và nhiều tên thuộc tính, dùng:

```java
import javax.management.Attribute;
import javax.management.AttributeList;

AttributeList attributes = server.getAttributes(
    name,
    new String[] { "ActiveSessions", "Enabled" });

for (Object item : attributes) {
    Attribute attribute = (Attribute) item;
    System.out.printf("%s = %s%n",
        attribute.getName(),
        attribute.getValue());
}
```

`getAttributes` trả về `AttributeList`, mỗi phần tử là một cặp tên/giá trị. Danh sách kết quả **có thể chỉ chứa những thuộc tính đọc được thành công**; không nên suy ra mọi tên yêu cầu đều có mặt hoặc dựa máy móc vào vị trí trả về. Hãy lập bản đồ theo `attribute.getName()` và kiểm tra các tên bị thiếu.

```java
import java.util.HashMap;
import java.util.Map;

Map<String, Object> values = new HashMap<>();
for (Object item : attributes) {
    Attribute attribute = (Attribute) item;
    values.put(attribute.getName(), attribute.getValue());
}

if (!values.containsKey("Enabled")) {
    throw new IllegalStateException(
        "JMX attribute Enabled was not returned");
}
```

Đọc nhiều attribute qua một lần gọi API có thể giảm số lượt trao đổi với client từ xa, nhưng kết quả không đương nhiên là một snapshot nguyên tử của toàn bộ MBean: dữ liệu vẫn có thể thay đổi giữa các lần getter được thực thi.

## 4. Ghi một attribute bằng setAttribute

### 4.1. Chữ ký và cách truyền giá trị

`setAttribute` nhận một đối tượng `Attribute` chứa tên và giá trị:

```java
void setAttribute(ObjectName name, Attribute attribute)
    throws InstanceNotFoundException,
           AttributeNotFoundException,
           InvalidAttributeValueException,
           MBeanException,
           ReflectionException;
```

Ví dụ tắt thu thập trạng thái theo hợp đồng quản trị:

```java
import javax.management.Attribute;

server.setAttribute(
    name,
    new Attribute("Enabled", Boolean.FALSE));
```

`Enabled` là tên JMX attribute; `Boolean.FALSE` là giá trị mới có kiểu tương thích với `boolean`. MBeanServer định tuyến yêu cầu đến logic setter do MBean triển khai. Setter có thể kiểm tra, chuẩn hóa hoặc từ chối giá trị tùy quy tắc nghiệp vụ.

**Ghi thành công không có nghĩa mọi thành phần liên quan cập nhật tức thì.** Nếu setter chỉ thay đổi cấu hình và một worker khác đọc theo chu kỳ, hiệu ứng quan sát có thể đến sau; điều này là đặc điểm ứng dụng, không phải quy tắc tự động của JMX.

### 4.2. Đọc lại để xác nhận trạng thái

```java
server.setAttribute(
    name,
    new Attribute("Enabled", Boolean.FALSE));

boolean actual = (Boolean) server.getAttribute(name, "Enabled");
if (actual) {
    throw new IllegalStateException(
        "Enabled remained true after write");
}
```

Readback ở đây xác nhận giá trị mà getter JMX công bố sau khi ghi. Nếu có nhiều bên thay đổi cùng attribute, giá trị có thể tiếp tục thay đổi ngay sau đó. Vì vậy đọc lại là một phép quan sát tại thời điểm gọi, không thay thế các cơ chế đồng bộ hoặc quản lý phiên bản khi cần đảm bảo cạnh tranh.

### 4.3. Ghi nhiều attribute bằng setAttributes

`MBeanServer` cung cấp:

```java
AttributeList setAttributes(
    ObjectName name,
    AttributeList attributes);
```

Ví dụ MBean có cả `Enabled` và một thuộc tính ghi được khác tên `Threshold`:

```java
import javax.management.Attribute;
import javax.management.AttributeList;

AttributeList updates = new AttributeList();
updates.add(new Attribute("Enabled", Boolean.TRUE));
updates.add(new Attribute("Threshold", Integer.valueOf(100)));

AttributeList applied = server.setAttributes(name, updates);

for (Object item : applied) {
    Attribute result = (Attribute) item;
    System.out.printf("Applied %s = %s%n",
        result.getName(),
        result.getValue());
}
```

`Threshold` trong đoạn này là một **attribute giả định** của MBean có hỗ trợ; `TrafficMonitorMBean` ở phần 2 chưa khai báo nó. Nếu dùng nguyên lớp `TrafficMonitor` để chạy, chỉ nên ghi `Enabled`.

Kết quả `setAttributes` là danh sách các attribute được xử lý thành công. Không được giả định mọi yêu cầu đều thành công. Cũng không được coi lời gọi nhóm là **transaction**: nếu cập nhật thứ nhất thành công và cập nhật thứ hai thất bại, JMX không tự đảm bảo rollback trạng thái trước đó.

Đối với cập nhật phụ thuộc nhau, cân nhắc cung cấp một operation quản trị duy nhất có kiểm tra và xử lý nhất quán trong MBean thay vì gọi nhiều setter rời rạc.

## 5. Kiểm tra attribute nào có thể đọc hoặc ghi

### 5.1. Khám phá bằng MBeanInfo

Trước khi tương tác với một MBean chưa biết, dùng `getMBeanInfo`:

```java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.printf(
        "name=%s type=%s readable=%s writable=%s is=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable(),
        attr.isIs());
}
```

`MBeanAttributeInfo` cung cấp:

| API | Ý nghĩa |
| --- | --- |
| `getName()` | Tên attribute được công bố |
| `getType()` | Tên kiểu dữ liệu Java theo metadata |
| `isReadable()` | Cho phép đọc qua JMX |
| `isWritable()` | Cho phép ghi qua JMX |
| `isIs()` | Attribute boolean sử dụng mẫu getter `isX()` |
| `getDescription()` | Mô tả dành cho công cụ vận hành |

Ví dụ trên mang tính khám phá: ở MBean động (`DynamicMBean`), metadata được cung cấp theo chương trình; ở bean do Spring xuất, metadata cũng có thể do assembler tạo ra. Đừng dự đoán quyền chỉ dựa vào tên getter/setter trong một lớp Java ngẫu nhiên.

### 5.2. Ví dụ utility an toàn theo metadata

```java
import javax.management.Attribute;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public final class JmxAttributeHelper {

    private JmxAttributeHelper() {}

    public static Object read(
            MBeanServerConnection connection,
            ObjectName name,
            String attribute) throws Exception {

        MBeanAttributeInfo attr = find(
            connection.getMBeanInfo(name), attribute);

        if (!attr.isReadable()) {
            throw new IllegalArgumentException(
                "Attribute is not readable: " + attribute);
        }
        return connection.getAttribute(name, attribute);
    }

    public static void write(
            MBeanServerConnection connection,
            ObjectName name,
            String attribute,
            Object value) throws Exception {

        MBeanAttributeInfo attr = find(
            connection.getMBeanInfo(name), attribute);

        if (!attr.isWritable()) {
            throw new IllegalArgumentException(
                "Attribute is not writable: " + attribute);
        }
        connection.setAttribute(name, new Attribute(attribute, value));
    }

    private static MBeanAttributeInfo find(
            MBeanInfo info,
            String attribute) {

        for (MBeanAttributeInfo candidate : info.getAttributes()) {
            if (candidate.getName().equals(attribute)) {
                return candidate;
            }
        }
        throw new IllegalArgumentException(
            "Unknown JMX attribute: " + attribute);
    }
}
```

Utility này kiểm tra tên và quyền theo metadata trước thao tác. Nó **không thực hiện chuyển đổi kiểu tự động**, không đảm bảo giá trị ghi hợp lệ, và không thay thế xử lý ngoại lệ cụ thể của JMX. Trạng thái hoặc metadata còn có thể thay đổi giữa lúc kiểm tra và thao tác; server vẫn là nơi quyết định kết quả cuối cùng.

Giao diện `MBeanServerConnection` được dùng để utility có thể hoạt động với kết nối nội bộ hoặc từ xa. `MBeanServer` mở rộng khả năng tương tác tương tự cho JVM cục bộ và hỗ trợ thêm quản lý đăng ký đối tượng.

## 6. Các lỗi cần phân biệt

Lời gọi đọc và ghi có nhiều nguyên nhân thất bại khác nhau. Đừng gộp mọi lỗi thành “JMX không hoạt động”.

| Lỗi | Khi nào thường xảy ra | Cách xử lý |
| --- | --- | --- |
| `MalformedObjectNameException` | Chuỗi tạo ObjectName sai cú pháp | Sửa domain/key/value, dùng `ObjectName` hợp lệ |
| `InstanceNotFoundException` | Chưa đăng ký MBean hoặc dùng sai server/name | Kiểm tra `isRegistered(name)`, exporter và vòng đời |
| `AttributeNotFoundException` | Sai tên hoặc attribute không cho phép thao tác yêu cầu | Kiểm tra `MBeanInfo`, chữ hoa/thường và readable/writable |
| `InvalidAttributeValueException` | Giá trị ghi không tương thích hoặc bị từ chối | Dùng đúng kiểu, kiểm tra ràng buộc |
| `MBeanException` | Method quản trị do MBean triển khai phát sinh ngoại lệ được JMX bao bọc | Xem nguyên nhân gốc, phân biệt lỗi nghiệp vụ với kết nối |
| `ReflectionException` | Lỗi phản chiếu khi thực hiện access | Kiểm tra interface, chữ ký getter/setter và cấu hình MBean |
| `SecurityException` hoặc lỗi xác thực/quyền tương ứng | Chủ thể không được phép truy cập | Kiểm tra policy/role và cấu hình bảo mật |
| `IOException` khi dùng `MBeanServerConnection` từ xa | Mất kết nối, timeout, lỗi transport | Kiểm tra connector, mạng và chiến lược retry phù hợp |

Một số lỗi là unchecked exception; các hành vi cụ thể còn tùy loại MBean và connector. `getAttributes`/`setAttributes` có thể bỏ qua từng attribute không thành công thay vì ném một lỗi cho toàn bộ danh sách, vì vậy phải đối chiếu kết quả trả về.

Ví dụ xử lý lỗi đọc cụ thể:

```java
import javax.management.AttributeNotFoundException;
import javax.management.InstanceNotFoundException;
import javax.management.MBeanException;
import javax.management.ReflectionException;

try {
    Object value = server.getAttribute(name, "ActiveSessions");
    System.out.println(value);
} catch (InstanceNotFoundException ex) {
    System.err.println("MBean chưa được đăng ký: " + name);
} catch (AttributeNotFoundException ex) {
    System.err.println("Không có attribute được đọc: ActiveSessions");
} catch (MBeanException | ReflectionException ex) {
    System.err.println("Lỗi thực thi getter JMX: " + ex.getMessage());
}
```

Không nên bắt `Exception` rồi âm thầm trả về `null`, vì người vận hành cần phân biệt “giá trị thật sự null” với “đọc thất bại”.

## 7. Liên hệ với Spring Framework JMX

### 7.1. Bean Spring không tự động là một JMX attribute

Spring quản lý bean trong `ApplicationContext`. MBeanServer quản lý các MBean bằng `ObjectName`. Hai registry có định danh và hợp đồng khác nhau.

Ví dụ Spring `MBeanExporter` xuất `TrafficMonitor` dưới tên:

```text
com.example.monitoring:type=TrafficMonitor,name=Main
```

Khi đó code dùng:

```java
server.getAttribute(name, "ActiveSessions");
server.setAttribute(name, new Attribute("Enabled", true));
```

mà không cần gọi thẳng `trafficMonitor.getActiveSessions()` hay `trafficMonitor.setEnabled(...)`. Đây là truy cập qua contract quản trị JMX, có thể phục vụ công cụ ngoài Spring.

### 7.2. Annotation và assembler thay đổi giao diện được xuất

Nếu Spring xuất bean theo annotation metadata, `@ManagedAttribute` trên getter/setter và `MetadataMBeanInfoAssembler` quyết định thuộc tính nào được công khai. Ví dụ:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.monitoring:type=TrafficMonitor,name=Main")
public class AnnotatedTrafficMonitor {

    private volatile boolean enabled = true;

    @ManagedAttribute(description = "Whether monitoring is enabled")
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute(description = "Enable or disable monitoring")
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
```

Bean annotation-based phải được đưa vào exporter có cấu hình assembler đọc annotation (hoặc cơ chế annotation-driven tương ứng) thì metadata mới phát huy tác dụng. Không thể chỉ nhìn annotation rồi mặc định mọi application context đều đăng ký MBean. Tương tự, việc có setter Java không tự bảo đảm JMX ghi được nếu assembler chọn không xuất setter đó.

### 7.3. Phân biệt trực tiếp MBeanServer và proxy

Hai cách truy cập phổ biến:

```java
Object raw = connection.getAttribute(name, "ActiveSessions");
connection.setAttribute(name, new Attribute("Enabled", true));
```

và thông qua một proxy Spring:

```java
public interface TrafficMonitorClient {
    int getActiveSessions();
    boolean isEnabled();
    void setEnabled(boolean enabled);
}
```

`MBeanProxyFactoryBean` có thể ánh xạ lời gọi interface này sang JMX trên `MBeanServerConnection`. Proxy giúp code client ít phụ thuộc vào tên String, nhưng vẫn sử dụng cùng attribute đã công bố và vẫn chịu lỗi JMX/transport. Khi học cách đọc và ghi attribute, API `MBeanServer` giúp nhìn rõ cơ chế nền tảng.

## 8. Tình huống vận hành thực tế

### 8.1. Quan sát mà không thay đổi trạng thái

Một dashboard chỉ cần đọc `ActiveSessions` theo chu kỳ. Attribute chỉ đọc phù hợp vì không cần quyền ghi và không gây side effect quản trị. Người vận hành vẫn cần cân nhắc chi phí getter: một getter JMX được gọi nhiều lần có thể gây tải nếu nó thực hiện truy vấn nặng hoặc khóa lâu.

### 8.2. Thay đổi cờ cấu hình

Khi cần bật/tắt một tính năng runtime, có thể công bố `Enabled` đọc/ghi. Trước khi thay đổi cần biết semantics: cờ ảnh hưởng request mới hay cả request đang xử lý? Có được phép cập nhật trong mọi trạng thái không? Setter là nơi kiểm soát invariant và có thể từ chối thao tác không phù hợp.

Luồng vận hành đề xuất:

```text
Định vị ObjectName
      ↓
getMBeanInfo: xác nhận Enabled đọc/ghi
      ↓
getAttribute("Enabled"): đọc trạng thái ban đầu
      ↓
setAttribute("Enabled", false): yêu cầu thay đổi
      ↓
getAttribute("Enabled"): kiểm tra giá trị quan sát được
      ↓
Ghi nhận thời điểm, người thực hiện và kết quả ở hệ thống vận hành
```

Không gửi mật khẩu, secret hay dữ liệu nhạy cảm qua attribute cho mục đích tiện quan sát. Nếu mở remote JMX, phải bảo vệ connector bằng kiểm soát mạng, xác thực và mã hóa phù hợp; khả năng `setAttribute` là quyền có thể tác động tới ứng dụng đang chạy.

### 8.3. Nhiều attribute và tính nhất quán

Giả sử MBean có `MinimumThreads` và `MaximumThreads`. Ghi hai attribute rời rạc có thể tạo ra trạng thái tạm thời không hợp lệ. API `setAttributes` cũng không đảm bảo transaction. Thiết kế tốt hơn là:

- Quy định setter kiểm tra invariant độc lập; hoặc
- Công bố một operation duy nhất, ví dụ `configureThreadPool(min, max)`, có validation và thay đổi nguyên tử trong logic ứng dụng.

Với tình huống nhiều người điều khiển đồng thời, có thể phải dùng versioning, lock hoặc cơ chế command có điều kiện ở tầng ứng dụng. `MBeanServer.setAttribute` không tự cung cấp compare-and-swap.

## 9. Bài thực hành đề xuất

Mục tiêu: tạo một Spring application có MBean `TrafficMonitor`, đọc thuộc tính và thay đổi trạng thái.

1. Tạo interface `TrafficMonitorMBean` và lớp `TrafficMonitor` như phần 2.
2. Cấu hình `MBeanExporter` để đăng ký bean vào platform `MBeanServer` dưới `com.example.monitoring:type=TrafficMonitor,name=Main`.
3. Sau khi context khởi tạo, lấy `MBeanServer` và tạo `ObjectName` tương ứng.
4. Gọi `getMBeanInfo`, xác nhận `ActiveSessions` chỉ đọc và `Enabled` đọc/ghi.
5. Gọi `getAttribute(name, "Enabled")` để xem giá trị đầu.
6. Gọi `setAttribute(name, new Attribute("Enabled", false))`; sau đó đọc lại `Enabled`.
7. Thử `setAttribute(name, new Attribute("ActiveSessions", 42))` và quan sát lỗi ghi thuộc tính chỉ đọc.
8. Thử đọc `MissingAttribute` để thấy hành vi khi tên không có.
9. Nếu có JConsole/JMX client, tìm ObjectName và quan sát thay đổi trạng thái qua giao diện quản trị.

Ví dụ một hàm chạy từ mã ứng dụng (khi MBean đã được đăng ký):

```java
package com.example.monitoring;

import java.lang.management.ManagementFactory;

import javax.management.Attribute;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class TrafficMonitorDemo {

    private TrafficMonitorDemo() {}

    public static void run() throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
            "com.example.monitoring:type=TrafficMonitor,name=Main");

        if (!server.isRegistered(name)) {
            throw new IllegalStateException("MBean not registered: " + name);
        }

        MBeanInfo info = server.getMBeanInfo(name);
        for (MBeanAttributeInfo attr : info.getAttributes()) {
            System.out.printf("%s: readable=%s writable=%s%n",
                attr.getName(), attr.isReadable(), attr.isWritable());
        }

        boolean before = (Boolean) server.getAttribute(name, "Enabled");
        server.setAttribute(name, new Attribute("Enabled", false));
        boolean after = (Boolean) server.getAttribute(name, "Enabled");

        System.out.printf("Enabled: %s -> %s%n", before, after);
        System.out.println(
            "ActiveSessions: " + server.getAttribute(name, "ActiveSessions"));
    }
}
```

Hàm `run()` được gọi **sau khi** Spring khởi tạo exporter. Nếu gọi trước khi MBean đăng ký, lỗi `MBean not registered` phản ánh đúng vấn đề vòng đời và không có nghĩa API `getAttribute` sai.

Kết quả mong đợi: tên `Enabled` xuất hiện là readable/writable, `ActiveSessions` readable nhưng không writable; thao tác ghi `Enabled` đổi giá trị được đọc lại thành `false`.

## 10. Câu hỏi tự kiểm tra

**1. `getAttribute` nhận những tham số nào?** Một `ObjectName` xác định MBean và một `String` là tên attribute, trả về `Object`.

**2. Tại sao `getAttribute` trả về `Object`?** Vì giao diện JMX có thể phục vụ nhiều kiểu attribute; client cần hiểu metadata để ép kiểu hoặc diễn giải đúng.

**3. Nếu `getActiveSessions()` tồn tại nhưng không có setter, có thể `setAttribute(..., "ActiveSessions")` không?** Không, khi metadata của MBean công bố nó là chỉ đọc.

**4. `getAttributes` có luôn trả đủ số lượng tên được yêu cầu không?** Không. Cần kiểm tra từng tên thực sự có trong `AttributeList`.

**5. `setAttributes` có tự rollback nếu một attribute thất bại không?** Không có bảo đảm transaction hay rollback cho cả nhóm.

**6. Nếu đọc thất bại với `InstanceNotFoundException`, nên kiểm tra gì?** ObjectName, MBeanServer được sử dụng, thời điểm đăng ký và vòng đời MBean.

**7. `MBeanInfo` hữu ích ở đâu?** Cho biết tên, kiểu và cờ readable/writable để client biết hợp đồng JMX thực tế.

**8. Có thể dùng `MBeanServerConnection` thay `MBeanServer` để đọc/ghi không?** Có, các phương thức tương ứng được công bố trong `MBeanServerConnection`, phù hợp cả kết nối nội bộ và từ xa.

## 11. Ghi nhớ

- **`MBeanServer` + `ObjectName`** xác định nơi và đối tượng quản trị.
- **`getAttribute`** đọc giá trị một attribute; **`getAttributes`** đọc nhiều attribute và cần kiểm tra danh sách trả về.
- **`setAttribute`** ghi một attribute thông qua `Attribute(name, value)`; **`setAttributes`** ghi một nhóm nhưng không mang tính transaction.
- **`MBeanInfo`** là nguồn để khám phá attribute nào readable/writable và kiểu dữ liệu đã công bố.
- **Spring `MBeanExporter`** giúp đăng ký bean vào JMX; quyền đọc/ghi vẫn dựa trên giao diện MBean thực sự được xuất.
- Sau khi ghi, **đọc lại và kiểm tra kết quả**, đồng thời xử lý rõ ràng lỗi tên, kiểu, quyền và vòng đời.

Khả năng đọc và ghi attribute qua MBeanServer là nền tảng của quản trị JMX: nó cho phép quan sát và điều khiển một phần trạng thái runtime qua hợp đồng quản trị rõ ràng, độc lập với việc caller có giữ reference trực tiếp tới Spring bean hay không.