# MXBean và quy tắc chuyển đổi kiểu dữ liệu

## Mục tiêu học tập

Sau bài này, bạn có thể giải thích MXBean trong Java Management Extensions (JMX), phân biệt MXBean với Standard MBean, hiểu cơ chế ánh xạ từ kiểu Java sang **open types** để JMX client có thể đọc dữ liệu mà không cần mang theo lớp Java riêng của ứng dụng, xây dựng MXBean cho một đối tượng quản lý trong Spring Framework và kiểm tra dữ liệu qua `MBeanServer` hoặc JConsole.

## 1. MXBean là gì và tại sao cần?

JMX cho phép ứng dụng Java công bố các thuộc tính và thao tác quản trị thông qua MBean. Với **Standard MBean**, giao diện thường có tên `ClassNameMBean`, ví dụ `JobMonitorMBean`. Nhưng một thuộc tính Java sử dụng class tùy biến có thể gây khó khăn cho JMX client từ xa: phía client cần biết kiểu Java đó để giải mã hoặc gọi method.

**MXBean** giải quyết nhu cầu trao đổi dữ liệu quản trị bằng cách ánh xạ các kiểu Java ở giao diện quản lý sang tập **Open MBean types** chuẩn của JMX. Client có thể nhận các dạng dữ liệu quen thuộc như `String`, số, `CompositeData`, `TabularData` và mảng mà không cần có class DTO của ứng dụng trên classpath. MXBean vẫn là một MBean, được đăng ký trong `MBeanServer` và có `ObjectName` như các loại MBean khác.

Ví dụ một API quản trị trả `CacheSnapshot` (class do ứng dụng định nghĩa). Khi khai báo trong MXBean, JMX có thể trình bày snapshot dưới dạng `CompositeData` gồm các trường `size`, `hits`, `misses`. Đó là giá trị **wire/management view**, không phải đối tượng `CacheSnapshot` truyền trực tiếp đến client.

Trong Spring Framework, MXBean là tính năng của Java JMX; Spring `MBeanExporter` có thể xuất đối tượng MXBean vào JMX registry. Annotation quản lý riêng của Spring là cơ chế khác và không tự biến mọi phương thức Java thành MXBean.

## 2. Cách nhận diện giao diện MXBean

Có hai cách nhận diện thường dùng.

**Cách 1: Hậu tố `MXBean`**

```java
package com.example.monitoring;

public interface CacheMonitorMXBean {
    int getEntryCount();
    boolean isRefreshEnabled();
    void setRefreshEnabled(boolean enabled);
    void clear();
}
```

Một lớp `CacheMonitor` implement `CacheMonitorMXBean`. Quy ước hậu tố `MXBean` giúp JMX tự nhận diện giao diện này là MXBean.

**Cách 2: Annotation `@MXBean`**

```java
package com.example.monitoring;

import javax.management.MXBean;

@MXBean
public interface CacheManagement {
    int getEntryCount();
    void clear();
}
```

Có thể dùng `@MXBean(true)` để khai báo tường minh. `@MXBean(false)` có thể phủ định việc interface được xem là MXBean khi áp dụng quy tắc nhận diện; khi thiết kế API quản lý, nên dùng tên/annotation rõ ràng để tránh mơ hồ.

Đừng nhầm `@MXBean` của `javax.management` với các annotation `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation` của Spring JMX.

## 3. Open types và quy tắc ánh xạ dữ liệu

JMX định nghĩa các kiểu dữ liệu mở như `SimpleType`, `ArrayType`, `CompositeType`, `TabularType`. Giá trị tương ứng được biểu diễn qua dữ liệu chuẩn, ví dụ `CompositeData` hoặc `TabularData`.

Bảng sau minh họa các quy tắc MXBean thường gặp; tên lớp Java và hình dạng thực tế là thông tin quan trọng đối với tool quản trị.

| Kiểu trong interface MXBean | Kiểu hiển thị/trao đổi thường gặp | Diễn giải |
| --- | --- | --- |
| `int`, `long`, `boolean`, `double` và các wrapper tương ứng | `SimpleType.INTEGER`, `LONG`, `BOOLEAN`, `DOUBLE` | Giá trị đơn giản |
| `String` | `SimpleType.STRING` | Chuỗi |
| `BigDecimal`, `BigInteger`, `Date`, `ObjectName` | SimpleType tương ứng | Các kiểu chuẩn được OpenType hỗ trợ |
| `enum` | `String` | Tên hằng enum |
| Mảng hoặc collection được MXBean mapping hỗ trợ | `ArrayType` | Các phần tử được ánh xạ từng phần |
| JavaBean/DTO phù hợp quy tắc ánh xạ | `CompositeData` / `CompositeType` | Thuộc tính của DTO được trình bày thành các mục dữ liệu |
| `Map<K,V>` có cặp kiểu ánh xạ được | `TabularData` / `TabularType` | Dạng bảng các cặp khóa/giá trị |

Đây là **ánh xạ theo quy tắc MXBean của JMX**, không phải mọi kiểu Java đều tự động được chấp nhận. Kiểu tham số, kiểu trả về, nested type, generic parameter và class DTO phải thỏa điều kiện chuyển đổi. Ví dụ một kiểu `Object` tổng quát hoặc cấu trúc không xác định có thể không có mapping hợp lệ. Nếu không thể mapping, quá trình đăng ký hoặc kiểm tra tính hợp lệ của MXBean có thể thất bại.

### Các kiểu đơn giản

```java
public interface WorkerPoolMXBean {
    int getActiveCount();         // Integer OpenType
    long getCompletedCount();     // Long OpenType
    boolean isPaused();           // Boolean OpenType
    String getState();            // String OpenType
}
```

Ở giao diện quản lý, Java giữ kiểu dữ liệu quen thuộc. Khi JMX client dùng API chuẩn, metadata attribute cho biết kiểu dữ liệu được công bố và OpenType tương ứng. Với MXBean, đôi khi metadata còn chứa thông tin kiểu Java gốc trong descriptor để client MXBean proxy khôi phục kiểu dữ liệu.

### Enum thành String

```java
public enum CacheState {
    ACTIVE, PAUSED, STOPPED
}

public interface CacheStatusMXBean {
    CacheState getState();
}
```

Giá trị `CacheState.ACTIVE` được trao đổi theo tên `"ACTIVE"`. Khi dùng MXBean proxy ở phía Java client, JMX có thể chuyển chuỗi trở lại enum tương ứng nếu interface và class enum có sẵn trên client. Một JMX client tổng quát vẫn có thể hiển thị chuỗi.

### Mảng và collection

```java
public interface PoolMetricsMXBean {
    String[] getWorkerNames();
    java.util.List<String> getActiveWorkerNames();
}
```

MXBean mapping chuyển các phần tử hợp lệ sang array of open values. Với danh sách, client JMX mức thấp có thể nhận cấu trúc mảng tương ứng thay vì một `List<String>` Java trực tiếp. Không giả định mọi collection cụ thể, generic hoang dã hoặc cấu trúc tham số hóa đều hỗ trợ như nhau; cần kiểm thử theo API JMX và JDK thực tế.

### Map thành TabularData

```java
public interface CacheMetricsMXBean {
    java.util.Map<String, Long> getHitsByRegion();
}
```

Map thường được biểu diễn như `TabularData`: mỗi hàng gồm khóa và giá trị đã được chuyển thành open type. Điều này giúp client đọc bảng thống kê mà không cần class Map implementation. Khóa và giá trị phải thuộc các kiểu có thể ánh xạ; cấu trúc generic phức tạp cần được thiết kế và thử nghiệm cẩn thận.

## 4. DTO quản trị và CompositeData

Một ưu điểm quan trọng của MXBean là trả về đối tượng dữ liệu có cấu trúc rõ ràng. Xây dựng DTO chỉ đọc bằng các getter JavaBean:

```java
package com.example.monitoring;

public class CacheSnapshot {
    private final int entryCount;
    private final long hitCount;
    private final long missCount;

    public CacheSnapshot(int entryCount, long hitCount, long missCount) {
        this.entryCount = entryCount;
        this.hitCount = hitCount;
        this.missCount = missCount;
    }

    public int getEntryCount() {
        return entryCount;
    }

    public long getHitCount() {
        return hitCount;
    }

    public long getMissCount() {
        return missCount;
    }
}
```

Dùng DTO này làm kết quả của MXBean:

```java
package com.example.monitoring;

public interface CacheMonitorMXBean {
    CacheSnapshot getSnapshot();
    void resetStatistics();
}
```

Khi gọi `getSnapshot()` qua `MBeanServer.getAttribute(name, "Snapshot")`, JMX client mức thấp nhận giá trị tương thích `CompositeData`, chứa ba item như `entryCount`, `hitCount`, `missCount`. Client không phải nạp `CacheSnapshot.class` để đọc tên trường và giá trị.

Lưu ý về **đường chuyển ngược**: Một class với getters có thể phù hợp để hiển thị giá trị từ MXBean, nhưng để nhận tham số hoặc nhận giá trị trả về thông qua MXBean proxy và tái tạo đúng class, JMX phải có cách dựng object từ CompositeData. Có thể cần public constructor phù hợp với `@ConstructorProperties`, factory như `from(CompositeData)`, hoặc JavaBean constructor/setter theo những quy tắc JMX hỗ trợ. Vì DTO chỉ đọc bên trên dùng constructor ba tham số mà không khai báo metadata dựng ngược, nó **không nên được giả định** có thể phục hồi đầy đủ ở mọi đường truyền proxy.

Nếu mục tiêu là làm ví dụ dễ dùng cả hai chiều, thêm chú thích constructor:

```java
import java.beans.ConstructorProperties;

// Bên trong class CacheSnapshot
@ConstructorProperties({"entryCount", "hitCount", "missCount"})
public CacheSnapshot(int entryCount, long hitCount, long missCount) {
    this.entryCount = entryCount;
    this.hitCount = hitCount;
    this.missCount = missCount;
}
```

Giữ tên property trong `@ConstructorProperties` đúng với tên getter tương ứng. Khi tạo DTO quản trị, ưu tiên dữ liệu bất biến và đơn giản, hạn chế đệ quy/vòng tham chiếu, type generic mơ hồ và object chứa tài nguyên hạ tầng.

## 5. Ví dụ MXBean hoàn chỉnh và đăng ký vào MBeanServer

Ví dụ này dùng `CacheSnapshot` và `CacheMonitorMXBean` ở trên.

**CacheMonitor.java**

```java
package com.example.monitoring;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public class CacheMonitor implements CacheMonitorMXBean {
    private final AtomicInteger entryCount = new AtomicInteger(5);
    private final AtomicLong hitCount = new AtomicLong(15);
    private final AtomicLong missCount = new AtomicLong(2);

    @Override
    public CacheSnapshot getSnapshot() {
        return new CacheSnapshot(
                entryCount.get(), hitCount.get(), missCount.get());
    }

    @Override
    public void resetStatistics() {
        hitCount.set(0);
        missCount.set(0);
    }
}
```

**JmxMxBeanDemo.java**

```java
package com.example.monitoring;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;

public class JmxMxBeanDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
                "com.example.monitoring:type=CacheMonitor,name=primary");

        server.registerMBean(new CacheMonitor(), name);

        Object value = server.getAttribute(name, "Snapshot");
        if (value instanceof CompositeData data) {
            System.out.println("Entries: " + data.get("entryCount"));
            System.out.println("Hits: " + data.get("hitCount"));
            System.out.println("Misses: " + data.get("missCount"));
        }

        server.invoke(
                name, "resetStatistics", new Object[0], new String[0]);
    }
}
```

Ví dụ trên minh họa hai lớp API:

1. **API Java trong MXBean** giữ kiểu `CacheSnapshot`, giúp implementation có mô hình rõ ràng.
2. **API của `MBeanServer`** trao đổi theo open type, nên attribute `Snapshot` xuất hiện dưới dạng `CompositeData` cho client thấp tầng.

Để xem trực quan bằng JConsole, cần giữ tiến trình Java hoạt động sau đăng ký (chẳng hạn chờ trong ứng dụng demo hoặc chạy Spring service), vì ví dụ `main` thoát ngay sau khi thực hiện thao tác.

## 6. MXBean proxy: nhận lại kiểu Java ở client

JMX hỗ trợ proxy MXBean, hữu ích khi client Java có interface và DTO tương thích:

```java
import java.lang.management.ManagementFactory;
import javax.management.JMX;
import javax.management.MBeanServer;
import javax.management.ObjectName;

// Ví dụ cùng JVM; client từ xa dùng MBeanServerConnection.
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
        "com.example.monitoring:type=CacheMonitor,name=primary");

CacheMonitorMXBean proxy = JMX.newMXBeanProxy(
        server, name, CacheMonitorMXBean.class);

CacheSnapshot snapshot = proxy.getSnapshot();
System.out.println(snapshot.getEntryCount());
```

Khi proxy tái tạo đối tượng `CacheSnapshot`, nó phải biết cách chuyển ngược từ `CompositeData` sang Java class. Đó là lý do constructor hoặc cơ chế dựng lại object theo chuẩn MXBean rất quan trọng. Một client chỉ cần hiển thị dữ liệu quản trị thường có thể dùng `CompositeData` và không cần proxy.

`JMX.newMXBeanProxy` không tự mở kết nối mạng; tham số đầu vào là một `MBeanServerConnection` đã có. Nếu kết nối remote, client cần endpoint JMX, quyền truy cập và cấu hình mạng phù hợp.

## 7. MXBean trong Spring Framework

Spring quản lý vòng đời bean và có thể xuất bean thành MXBean thông qua `MBeanExporter`. Ví dụ cấu hình cụ thể:

```java
package com.example.monitoring;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class MxBeanJmxConfiguration {
    @Bean
    public CacheMonitor cacheMonitor() {
        return new CacheMonitor();
    }

    @Bean
    public MBeanServer mBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter mBeanExporter(
            CacheMonitor cacheMonitor, MBeanServer mBeanServer) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mBeanServer);
        exporter.setBeans(Map.of(
                "com.example.monitoring:type=CacheMonitor,name=primary",
                cacheMonitor));
        return exporter;
    }
}
```

Khi cấu hình được nạp trong Spring `ApplicationContext`, exporter sẽ đăng ký đối tượng với server. Cơ chế nhận diện hợp đồng `CacheMonitorMXBean` vẫn là của JMX. Mỗi `ObjectName` cần duy nhất trong `MBeanServer`; không đăng ký cùng tên song song bằng code Java thuần và exporter.

Với ứng dụng Spring Boot, xem trạng thái JMX auto-configuration và các exporter đã được tạo trước khi bổ sung cấu hình tùy chỉnh. Đừng suy ra tất cả Spring beans đều tự động được xuất ra JMX; những bean được xuất phụ thuộc cấu hình và cơ chế đăng ký.

## 8. Kiểm tra open type bằng MBeanInfo

Sau khi đăng ký, có thể xem metadata thuộc tính `Snapshot` và OpenType:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.openmbean.OpenMBeanAttributeInfo;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
        "com.example.monitoring:type=CacheMonitor,name=primary");

MBeanInfo info = server.getMBeanInfo(name);
for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.println(attribute.getName() + ": " + attribute.getType());
    if (attribute instanceof OpenMBeanAttributeInfo openInfo) {
        System.out.println("OpenType: " + openInfo.getOpenType());
    }
}
```

JMX MXBean metadata có thể biểu diễn OpenType trong descriptor của MBeanInfo; việc `MBeanAttributeInfo` có implement trực tiếp `OpenMBeanAttributeInfo` hay không phụ thuộc cách metadata được cung cấp. Để kiểm tra ổn định, có thể đọc descriptor field `openType`:

```java
Object openType = attribute.getDescriptor().getFieldValue("openType");
System.out.println("OpenType descriptor: " + openType);
```

Với `Snapshot`, open type mong đợi là `CompositeType`; dữ liệu đọc bằng `getAttribute` có thể inspect qua `CompositeData.getCompositeType()` và `get("entryCount")`.

Trong JConsole, chọn domain và `ObjectName` tương ứng, xem phần `Attributes`, mở `Snapshot` để quan sát dữ liệu phân cấp. JConsole hoặc client tương đương có thể trình bày `CompositeData` khác nhau tùy phiên bản. Giá trị open type và metadata là bằng chứng kỹ thuật đáng tin cậy hơn giao diện hiển thị cụ thể.

## 9. Phân biệt MXBean, Standard MBean và Dynamic MBean

| Tiêu chí | Standard MBean | MXBean | Dynamic MBean |
| --- | --- | --- | --- |
| Định nghĩa hợp đồng | Interface `ClassNameMBean` | Interface `*MXBean` hoặc `@MXBean` | Implementation tự cung cấp metadata bằng `DynamicMBean` |
| Ánh xạ dữ liệu | Dùng kiểu khai báo của MBean interface; client có thể cần class riêng | Ánh xạ sang JMX OpenType | Do implementation quyết định |
| DTO tùy biến | Có thể khó thao tác từ client không có class DTO | Thường trao đổi qua `CompositeData` | Tùy metadata và dữ liệu triển khai |
| Mức độ tự động | Dựa vào naming convention | Naming/annotation + quy tắc mapping | Cần tự cài đặt nhiều hơn |
| Tình huống dùng | API quản trị đơn giản, client biết kiểu | Quan sát và quản trị qua công cụ tổng quát, remote client | Hợp đồng quản lý cần biến đổi động |

Không có lựa chọn nào làm thay quyền quản trị JMX trở nên an toàn mặc định. Operation có thể thay đổi trạng thái của ứng dụng; remote JMX cần kiểm soát xác thực, mã hóa và phạm vi truy cập.

## 10. Lỗi thường gặp và cách xử lý

**Không đăng ký được MXBean:** xem chi tiết `NotCompliantMBeanException` và nguyên nhân lồng bên trong; kiểm tra class implement interface, hậu tố `MXBean` hoặc annotation `@MXBean`, kiểu trả về/tham số có mapping hợp lệ và cấu trúc DTO.

**CompositeData thiếu hoặc khác tên trường mong đợi:** kiểm tra quy tắc property của getter JavaBean, chữ hoa chữ thường và kiểu dữ liệu. `getEntryCount()` thường ánh xạ key `entryCount`; dùng metadata `CompositeType.keySet()` để xem key thực tế.

**Proxy không tái tạo được DTO:** kiểm tra constructor thích hợp, tên trong `@ConstructorProperties` và các getter; phía client cần interface/class tương thích. Có thể dùng `CompositeData` trực tiếp nếu không cần object Java.

**Dùng kiểu generic không rõ ràng:** tránh `Object`, collection raw, wildcard phức tạp hoặc object graph có tham chiếu vòng mà không có hợp đồng chuyển đổi xác định; chọn DTO đơn giản và khai báo generic cụ thể.

**Không tìm thấy MBean trong JConsole:** xác minh JVM đang kết nối, tên `ObjectName`, trạng thái `MBeanExporter` và server được dùng. Một MXBean vẫn cần đăng ký vào registry như Standard MBean.

**Dữ liệu đo không nhất quán:** MXBean mapping không thay thế đồng bộ luồng. Nếu snapshot cần tính nhất quán giữa nhiều bộ đếm, implementation phải có chiến lược snapshot thích hợp.

## 11. Bài tập thực hành

1. Tạo interface `WorkerPoolMXBean` có `getState()` trả enum, `getMetrics()` trả DTO chứa `activeWorkers` và `completedTasks`, cùng `getActiveWorkerNames()` trả `List<String>`.
2. Implement và đăng ký trong platform `MBeanServer` dưới `com.example.monitoring:type=WorkerPool,name=demo`.
3. Dùng JConsole hoặc `MBeanServer.getAttribute` xác nhận enum được hiển thị qua chuỗi, DTO qua `CompositeData`, collection theo array open value.
4. Đọc `getMBeanInfo` và descriptor `openType` để kiểm tra kiểu mà server công bố.
5. Thử `JMX.newMXBeanProxy` trong JVM thử nghiệm để truy cập interface bằng kiểu Java; bổ sung constructor metadata thích hợp nếu DTO không thể chuyển ngược.
6. So sánh với một Standard MBean trả về kiểu đơn giản và giải thích vì sao MXBean hữu ích cho các công cụ JMX độc lập với ứng dụng.

**Ghi nhớ:** MXBean là hợp đồng quản trị JMX mà các kiểu Java được ánh xạ sang OpenType chuẩn. Cách này đặc biệt hữu ích khi dữ liệu quản lý chứa enum, DTO, collection hoặc map và được quan sát bởi JMX client không biết các lớp Java riêng của ứng dụng. Spring Framework có thể xuất MXBean qua `MBeanExporter`, nhưng quy tắc chuyển đổi dữ liệu do JMX định nghĩa.
