# Proxy động và giới hạn của kiểu trả về trong Spring JMX

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích **proxy động cho MBean local** là gì, vì sao code Java có thể gọi một interface trong khi lời gọi thực chất đi qua `MBeanServerConnection`.
- Phân biệt JDK dynamic proxy do JMX tạo, proxy của Spring `MBeanProxyFactoryBean`/`MBeanClientInterceptor`, và AOP proxy thường dùng cho service nghiệp vụ.
- Mô tả cách một method trên proxy được chuyển thành thao tác **đọc attribute**, **ghi attribute**, hoặc **invoke operation** lên MBean.
- Hiểu giới hạn của **return type**: kiểu nguyên thủy, `String`, `ObjectName`, mảng, custom DTO, `CompositeData`, `TabularData`, Java records, generic collections và MXBean open-type mapping.
- Phân biệt hành vi local MBeanServer với remote JMX connector, nhất là **class loading** và **serialization**.
- Xử lý lỗi như `ClassCastException`, `InvalidAttributeValueException`, `ReflectionException`, `MBeanException`, `UndeclaredThrowableException` hoặc lỗi mapping/không tương thích chữ ký.
- Thiết kế interface quản trị ổn định, dễ gọi qua proxy và dễ chuyển thành contract cho monitoring.

## 2. Bối cảnh: vì sao cần proxy thay vì gọi MBeanServer thủ công?

JMX (Java Management Extensions) cho phép một ứng dụng đăng ký các đối tượng quản lý (MBeans) với `MBeanServer`, dưới một `ObjectName`.

Ví dụ:

```text
com.example.shop.orders:type=QueueMonitor,name=outbox
```

Một client thuần JMX có thể đọc attribute:

```java
Object value = connection.getAttribute(name, "PendingCount");
int pending = (Integer) value;
```

hoặc gọi operation:

```java
Object result = connection.invoke(
        name,
        "resetStatistics",
        new Object[0],
        new String[0]);
```

Cách này hoạt động nhưng khi ứng dụng gọi nhiều attributes và operations, code cần tự xử lý tên, kiểu dữ liệu, signatures và checked exceptions.

**MBean proxy** cung cấp một interface Java để client viết code tự nhiên hơn:

```java
int pending = monitor.getPendingCount();
monitor.resetStatistics();
```

Đằng sau lời gọi, proxy chuyển method sang JMX access tương ứng. Proxy không làm mất ranh giới JMX; nó chỉ **đóng gói các lời gọi đến MBeanServerConnection**.

## 3. “Local MBean proxy” chính xác là gì?

Một MBean proxy được gọi là **local** khi nó giao tiếp với MBeanServer trong cùng process/JVM, thường bằng cách lấy platform MBeanServer:

```java
MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();
```

`MBeanServer` cũng cung cấp các thao tác của `MBeanServerConnection`, vì vậy proxy có thể dùng server này mà không cần network connector.

Luồng:

```text
Application code
       |
       v
QueueMonitorMBean proxy (Java interface)
       |
       v
Dynamic proxy / interceptor
       |
       v
MBeanServerConnection
       |
       v
Local MBeanServer
       |
       v
Registered MBean: com.example.shop.orders:type=QueueMonitor,name=outbox
```

Đặc điểm:

- Không cần socket/network để truy cập trong cùng JVM.
- Vẫn phụ thuộc ObjectName, metadata của MBean, interface và sự tồn tại của registration.
- Lời gọi có thể thất bại nếu MBean chưa đăng ký, đã unregister, hoặc signature không phù hợp.
- Không tự tạo cache cho mọi getter.
- Không mặc nhiên giúp một method chậm trở nên nhanh.

Trong Spring, bạn thường gặp `MBeanProxyFactoryBean` và `MBeanClientInterceptor`. Trong Java chuẩn có `javax.management.JMX.newMBeanProxy(...)` hoặc `newMXBeanProxy(...)`.

## 4. Phân biệt ba loại proxy dễ bị nhầm

| Loại proxy | Mục đích | Ví dụ |
|---|---|---|
| **Spring AOP proxy** | Chèn transaction, security, caching, retry hoặc advice quanh service method | Bean có `@Transactional` |
| **JMX MBean proxy** | Biểu diễn JMX attributes/operations bằng Java interface và gửi lời gọi tới `MBeanServerConnection` | `JMX.newMBeanProxy(...)` |
| **Spring JMX client proxy** | Dùng Spring factory/interceptor để tạo proxy giao tiếp với một MBean | `MBeanProxyFactoryBean` |

Một Spring JMX client proxy có thể trông giống service bean khi inject qua interface, nhưng **implementation thực** là lệnh JMX tới ObjectName. Nó không đồng nghĩa với một Spring AOP proxy trực tiếp bao target service.

Sự khác biệt quan trọng khi debug:

- Nếu lỗi xảy ra trong business advice, điều tra Spring AOP invocation chain.
- Nếu lỗi là `InstanceNotFoundException` hoặc không đọc được JMX attribute, điều tra ObjectName/MBeanServer/management metadata.
- Nếu lỗi là `ClassCastException` sau khi proxy trả giá trị, điều tra return type và JMX type mapping.

## 5. Ví dụ hoàn chỉnh với Standard MBean

Ta tạo một MBean đơn giản cho queue.

### 5.1. Management interface

**`QueueMonitorMBean.java`**

```java
public interface QueueMonitorMBean {
    int getPendingCount();
    boolean isPaused();
    void pause();
    void resume();
}
```

Theo convention Standard MBean, interface `QueueMonitorMBean` xác định management attributes và operations.

- `getPendingCount()` → attribute `PendingCount` có kiểu `int`.
- `isPaused()` → boolean attribute `Paused`.
- `pause()`, `resume()` → JMX operations.

### 5.2. Implementation

**`QueueMonitor.java`**

```java
import java.util.concurrent.atomic.AtomicInteger;

public class QueueMonitor implements QueueMonitorMBean {

    private final AtomicInteger pending = new AtomicInteger(5);
    private volatile boolean paused;

    @Override
    public int getPendingCount() {
        return pending.get();
    }

    @Override
    public boolean isPaused() {
        return paused;
    }

    @Override
    public void pause() {
        paused = true;
    }

    @Override
    public void resume() {
        paused = false;
    }
}
```

Ví dụ dùng `AtomicInteger` và `volatile` để đơn giản hóa việc đọc trạng thái trong RAM; production phải thiết kế lifecycle của worker/queue tương ứng.

### 5.3. Đăng ký và tạo JMX dynamic proxy

**`LocalProxyDemo.java`**

```java
import java.lang.management.ManagementFactory;
import javax.management.JMX;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class LocalProxyDemo {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
                "com.example.shop.orders:type=QueueMonitor,name=outbox");

        server.registerMBean(new QueueMonitor(), name);

        try {
            QueueMonitorMBean proxy = JMX.newMBeanProxy(
                    server,
                    name,
                    QueueMonitorMBean.class);

            System.out.println("Pending: " + proxy.getPendingCount());
            System.out.println("Paused: " + proxy.isPaused());

            proxy.pause();
            System.out.println("Paused after pause(): " + proxy.isPaused());

            proxy.resume();
        } finally {
            server.unregisterMBean(name);
        }
    }
}
```

Mã chỉ yêu cầu Java/JMX chuẩn. Khi chạy, `JMX.newMBeanProxy` trả về một Java proxy hiện thực interface `QueueMonitorMBean`. Nó không trực tiếp trả reference của đối tượng `QueueMonitor` đã đăng ký.

### 5.4. Điều gì xảy ra khi gọi proxy?

```text
proxy.getPendingCount()
    |
    v
connection.getAttribute(objectName, "PendingCount")
    |
    v
QueueMonitor.getPendingCount()

proxy.pause()
    |
    v
connection.invoke(objectName, "pause", [], [])
    |
    v
QueueMonitor.pause()
```

JMX introspection hiểu getter/setter theo management contract và chuẩn đặt tên. Nếu interface proxy khai báo method không tồn tại trong metadata MBean, lời gọi sẽ không thành công chỉ vì Java compile được.

## 6. Spring MBeanProxyFactoryBean hoạt động thế nào?

Spring Framework hỗ trợ tạo JMX client proxy thông qua `MBeanProxyFactoryBean` (sử dụng interception để ánh xạ method sang JMX).

Ví dụ Java configuration:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

@Configuration
public class JmxClientConfig {

    @Bean
    MBeanProxyFactoryBean queueMonitorProxy(MBeanServer mbeanServer)
            throws Exception {

        MBeanProxyFactoryBean factory = new MBeanProxyFactoryBean();
        factory.setServer(mbeanServer);
        factory.setObjectName(new ObjectName(
                "com.example.shop.orders:type=QueueMonitor,name=outbox"));
        factory.setProxyInterface(QueueMonitorMBean.class);

        return factory;
    }
}
```

Ví dụ giả định Spring context có bean `MBeanServer` phù hợp và MBean đã được đăng ký theo ObjectName trên. Vì `MBeanProxyFactoryBean` là một `FactoryBean`, consumer thường lấy **product proxy** qua bean name, còn việc lấy chính factory (nếu cần) sử dụng cách truy cập FactoryBean của Spring.

Một client được inject qua management interface:

```java
import org.springframework.stereotype.Component;

@Component
public class QueueOperations {

    private final QueueMonitorMBean monitor;

    public QueueOperations(QueueMonitorMBean monitor) {
        this.monitor = monitor;
    }

    public int pending() {
        return monitor.getPendingCount();
    }
}
```

Cần bảo đảm dependency injection không mơ hồ nếu application có cả target MBean và proxy cùng triển khai `QueueMonitorMBean`. Có thể dùng bean name/qualifier hoặc tách interface client theo cấu hình phù hợp. Không giả định ví dụ injection này tự resolve duy nhất nếu có nhiều candidates.

**Lưu ý phiên bản:** Kiểm tra Javadoc Spring đang dùng về setters, khởi tạo FactoryBean và khả năng autodetect metadata. Với Spring JMX exporter, server và client có thể dùng cùng một `MBeanServer`, nhưng không nên tạo thêm server mới chỉ để proxy truy cập tên đang đăng ký ở server khác.

## 7. Proxy không xóa bỏ ranh giới JMX

Một dynamic proxy có thể tạo ảo giác đối tượng bình thường:

```java
QueueMonitorMBean monitor = ...;
int value = monitor.getPendingCount();
```

Nhưng lời gọi đi qua MBeanServer và có các đặc tính khác method call trực tiếp:

1. **ObjectName là định danh đích**, không phải Java object reference tới target.
2. MBean có thể không tồn tại tại thời điểm gọi.
3. Getter có thể ném lỗi do MBeanServer, metadata hoặc logic implementation.
4. Operation có thể bị giới hạn bởi MBean contract và security policy.
5. Kiểu dữ liệu đi qua JMX API phải khớp với kiểu mà proxy kỳ vọng.
6. Không nên giả định một lời gọi local luôn nhẹ: target getter có thể gọi DB/HTTP.
7. Client có thể gặp thay đổi metadata nếu MBean được unregister/re-register dưới cùng tên.

Do đó, interface proxy là **client-side contract**, không phải bằng chứng rằng MBean thực sự cung cấp mọi method và type tương ứng.

## 8. Return type: kiểu nào đơn giản nhất?

Với các Standard MBeans trong cùng JVM, các kiểu trả về thông dụng thường dễ dùng:

| Kiểu | Ví dụ method | Ghi chú |
|---|---|---|
| Primitive | `int getPendingCount()` | Rõ ràng, không nhận null |
| Boxed primitive | `Integer getPendingCount()` | Có thể null theo contract, cần xử lý |
| `boolean` / `Boolean` | `isPaused()` | Attribute boolean hoặc boxed |
| `String` | `String getState()` | Đơn giản, dễ hiểu |
| `ObjectName` | `ObjectName getRelatedMBean()` | Định danh tham chiếu MBean khác |
| Mảng kiểu đơn giản | `String[] getActiveQueues()` | Kích thước và snapshot semantics cần kiểm soát |
| `CompositeData` | `CompositeData getSnapshot()` | Dữ liệu open type, client cần hiểu field |
| `TabularData` | `TabularData getWorkers()` | Bảng open-data với schema rõ |
| Custom DTO | `QueueSnapshot getSnapshot()` | Phụ thuộc Standard/MXBean mapping và local/remote class loading |
| Collections/generics | `List<QueueSnapshot> listSnapshots()` | Dễ gặp giới hạn mapping, interface, serialization |

**Không có một quy tắc “local proxy nhận mọi return type mà Java chấp nhận”.** Return type hợp lệ còn phụ thuộc **kiểu MBean**, **MBeanInfo**, **mechanism mapping** và **transport**.

## 9. Standard MBean và MXBean: giới hạn kiểu khác nhau

Đây là phân biệt quan trọng nhất khi thiết kế API có dữ liệu phức tạp.

### 9.1. Standard MBean

Standard MBean tạo management contract từ interface có tên phù hợp, ví dụ:

```java
public interface QueueMonitorMBean {
    int getPendingCount();
    QueueSnapshot getSnapshot();
}
```

Một `QueueSnapshot` tùy chỉnh có thể được dùng trong Standard MBean, nhưng:

- Client phải hiểu đúng class/kiểu runtime khi nhận giá trị.
- Nếu remote, Java serialization/class loading có thể là rào cản quan trọng.
- Spring proxy phải có method signature tương thích với metadata JMX.
- Nếu MBean exporter hoặc assembler chuyển đổi type theo cơ chế khác, client có thể nhận một kiểu không giống DTO dự đoán.

Với **local** Standard MBean trong cùng JVM, client thường có cùng classpath và classloader tương thích hơn remote client. Nhưng local **không xóa được** rủi ro interface sai type, `ClassCastException`, hoặc trả một object mutable dùng chung mà client thay đổi ngoài ý muốn.

### 9.2. MXBean

MXBean có quy tắc ánh xạ nhiều Java types sang **Open MBean types**. Client thường làm việc với các representation tiêu chuẩn như `CompositeData` và `TabularData` trên JMX wire/API layer. `JMX.newMXBeanProxy(...)` có thể áp dụng MXBean mapping để client nhìn thấy Java types theo interface MXBean của nó.

Ví dụ:

```java
public interface QueueStatsMXBean {
    int getPendingCount();
    QueueSnapshot getSnapshot();
}
```

Nếu `QueueSnapshot` phù hợp với quy tắc MXBean mapping, API sẽ có cách chuyển đổi tương ứng. Nếu không, registration hoặc access có thể thất bại vì kiểu dữ liệu không thể chuyển sang OpenType.

**Không mặc định:** Một Java record hoặc một arbitrary custom class luôn tự map thành `CompositeData` trong mọi phiên bản JDK và cấu hình MXBean. Cần xác minh mapping theo quy tắc MXBean và kiểu cụ thể.

## 10. Ví dụ an toàn: DTO dưới dạng các thuộc tính đơn giản

Nếu mục tiêu là monitoring với JMX client đa dạng, thay vì trả DTO tùy ý:

```java
public interface QueueMonitorMBean {
    int getPendingCount();
    long getProcessedCount();
    String getState();
}
```

Ưu điểm:

- Ít phụ thuộc Java class phía client.
- Dễ đọc qua JConsole và scripts.
- Dễ ánh xạ sang metrics exporter.
- Tránh schema phức tạp với serialization hoặc mapping.

Đánh đổi:

- Client đọc ba attributes có thể lấy ở ba thời điểm khác nhau, **không đảm bảo atomic snapshot của cả ba**.
- Nếu cần consistency nghiêm ngặt, nên thiết kế compound attribute hoặc snapshot có metadata/version và mapping phù hợp.
- Không nên chia một cấu trúc thành hàng trăm attributes chỉ để né kiểu phức tạp.

## 11. Ví dụ return type phức tạp: CompositeData

JMX Open MBean API cung cấp `CompositeData`, đại diện một record gồm các trường có kiểu đã được khai báo.

Ví dụ method:

```java
import javax.management.openmbean.CompositeData;

public interface QueueDiagnosticsMBean {
    CompositeData getSnapshot();
}
```

Client có thể đọc:

```java
CompositeData snapshot = proxy.getSnapshot();
Object pending = snapshot.get("pendingCount");
Object state = snapshot.get("state");
```

Tên field `pendingCount`/`state` phải khớp với `CompositeType` mà MBean thực sự công bố.

### Dựng CompositeData

```java
import javax.management.openmbean.CompositeData;
import javax.management.openmbean.CompositeDataSupport;
import javax.management.openmbean.CompositeType;
import javax.management.openmbean.OpenType;
import javax.management.openmbean.SimpleType;

public static CompositeData createSnapshot(
        int pending, String state) throws Exception {

    String[] names = {"pendingCount", "state"};
    OpenType<?>[] types = {
            SimpleType.INTEGER,
            SimpleType.STRING
    };

    CompositeType type = new CompositeType(
            "QueueSnapshot",
            "Queue monitoring snapshot",
            names,
            new String[] {"Pending count", "Queue state"},
            types);

    return new CompositeDataSupport(
            type,
            names,
            new Object[] {pending, state});
}
```

Kiểu `CompositeData` phù hợp cho client không muốn phụ thuộc DTO Java riêng. Nhưng cần quản lý schema: đổi field name hoặc type có thể khiến client cũ lỗi. `CompositeData.get("missing")` có thể ném `InvalidKeyException`, nên không coi schema là tự thương lượng được.

## 12. Ví dụ TabularData cho danh sách trạng thái

`TabularData` là một cấu trúc open-data cho dữ liệu dạng bảng với row `CompositeData` và key/index hợp lệ.

Có thể dùng để công bố tình trạng nhiều worker:

```text
workerId   state     processed
w-01       RUNNING   120
w-02       IDLE      105
w-03       PAUSED    90
```

Interface:

```java
import javax.management.openmbean.TabularData;

public interface WorkerStatusMBean {
    TabularData getWorkers();
}
```

Lưu ý khi thiết kế:

- Schema `TabularType` và `CompositeType` phải thống nhất.
- Một hoặc nhiều field cần làm key để định danh row.
- Kích thước danh sách phải được giới hạn; không nên trả một bảng hàng trăm nghìn bản ghi trong mỗi lần JMX polling.
- Với dữ liệu thay đổi liên tục, cần xác định snapshot semantics.
- Nếu mục tiêu là metrics aggregation, nhiều scalar gauges/counters hoặc một endpoint metrics chuyên dụng có thể phù hợp hơn.

## 13. Custom Java DTO: tại sao local chạy mà remote có thể lỗi?

Giả sử:

```java
public final class QueueSnapshot implements java.io.Serializable {
    private static final long serialVersionUID = 1L;

    private final int pending;
    private final String state;

    public QueueSnapshot(int pending, String state) {
        this.pending = pending;
        this.state = state;
    }

    public int getPending() {
        return pending;
    }

    public String getState() {
        return state;
    }
}
```

Một Standard MBean có thể trả object này khi cả hai phía tương thích. Local client dùng cùng classloader có thể cast trực tiếp:

```java
QueueSnapshot snapshot = monitor.getSnapshot();
```

Nhưng khi chuyển sang remote JMX/RMI, điều kiện thay đổi:

- DTO cần phù hợp với cơ chế serialization đang dùng.
- Client cần class `QueueSnapshot` và các dependencies liên quan.
- `serialVersionUID`, thay đổi field, phiên bản class hoặc package có thể gây lỗi deserialization.
- Java serialization có rủi ro bảo mật nếu đối tượng không tin cậy; phải cấu hình kết nối đáng tin cậy và serialization filtering/allowlisting khi phù hợp.
- Việc class có `Serializable` không tự đảm bảo mọi thành viên lồng bên trong cũng có thể được serialize.

Vì vậy thiết kế được cho local MBean proxy không mặc nhiên là contract tốt cho remote client. MXBean open types hoặc các scalar attributes thường giúp giảm sự phụ thuộc vào class riêng.

## 14. Vì sao không nên tùy tiện trả JPA Entity?

Một getter JMX như sau dễ gây vấn đề:

```java
public interface OrderMonitorMBean {
    OrderEntity getLastOrder();
}
```

Đây thường là thiết kế không phù hợp cho management API vì:

1. JPA entity có thể chứa nhiều field và dữ liệu nhạy cảm.
2. Lazy associations có thể kích hoạt SQL khi client/serializer truy cập.
3. Object graph có thể lớn hoặc có vòng tham chiếu.
4. Có thể gặp `LazyInitializationException` khi persistence context đã đóng.
5. Client phải biết class `OrderEntity`.
6. Schema entity thay đổi theo nghiệp vụ, khiến management contract không ổn định.
7. Nếu trả mutable object trong local JVM, code client có thể nhận reference có side effect ngoài ý muốn tùy implementation.

Nên công bố **DTO quản trị tối thiểu** hoặc attributes như:

```text
LastProcessedOrderId
LastProcessedEpochMillis
PendingCount
ProcessingState
```

Vẫn cần bảo đảm ID được công bố không mang thông tin cá nhân hoặc bí mật. JMX interface là một **API vận hành**, không phải API trả entity nghiệp vụ.

## 15. Hạn chế của generic return types

Xét:

```java
List<QueueSnapshot> getSnapshots();
Map<String, QueueSnapshot> getQueues();
Optional<QueueSnapshot> getLatestSnapshot();
```

Điều cần cân nhắc:

- Generics trong Java chủ yếu được áp dụng tại compile time; runtime reflection có cả raw type và metadata generic, nhưng khả năng mapping phụ thuộc cơ chế.
- Standard MBean không tự định nghĩa schema OpenType cho mọi generic collection.
- MXBean có những quy tắc mapping cho collection/map hợp lệ, nhưng không phải mọi tổ hợp đều tương thích.
- `Optional<T>` không phải kiểu dữ liệu JMX đơn giản mặc định; cần xác minh trong mapping cụ thể thay vì giả định.
- Client remote có thể không có DTO class hoặc deserializer tương ứng.
- Trả collection lớn qua JMX có thể khiến management endpoint chậm và cấp phát nhiều bộ nhớ.

Nếu cần danh sách trạng thái đa nền tảng, cân nhắc `TabularData` hoặc MXBean interface với kiểu được mapping chính thức. Nếu chỉ phục vụ dashboard, hãy ưu tiên các metric/attribute hữu ích thay vì export toàn bộ object graph.

## 16. Method signatures và overloaded operations

Proxy dịch lời gọi operation sang tên và signature trên MBeanServer:

```java
connection.invoke(
        objectName,
        "resize",
        new Object[] {16},
        new String[] {"int"});
```

Một MBean có thể có overloaded methods:

```java
void resize(int size);
void resize(String preset);
```

Chúng có cùng tên nhưng khác signature. Nếu interface proxy khai báo kiểu khác với metadata server, operation có thể không tìm được.

Ví dụ Java interface dùng:

```java
void resize(Integer size);
```

nhưng MBean metadata chỉ có operation `resize(int)`, khi đó signatures `java.lang.Integer` và `int` khác nhau. Một proxy không bắt buộc tự chuyển chúng như compiler thường làm với autoboxing trong local method call.

**Quy tắc:** Interface phía client phải khớp **tên, kiểu tham số và return type** theo management contract thực tế; đừng xem proxy như một “adapter tự hiểu” mọi overload.

## 17. Null và primitive return types

Java primitive không thể biểu diễn `null`.

Nếu MBean trả `null` nhưng interface proxy khai báo:

```java
int getPendingCount();
```

thì việc unboxing có thể gây lỗi như `NullPointerException` hoặc lỗi chuyển kiểu tùy đường gọi.

Khi giá trị có thể vắng mặt, có thể:

- Trả `Integer` thay vì `int` và tài liệu hóa `null`.
- Trả một trạng thái riêng `boolean isInitialized()`.
- Dùng sentinel có ý nghĩa rõ, chẳng hạn `-1`, chỉ nếu không xung đột với miền giá trị.
- Công bố `LastRefreshEpochMillis` hoặc `Healthy` để biết freshness.

Trong MXBean/open type mapping, cần hiểu quy tắc nullable của kiểu được dùng. Không phải mọi client sẽ xử lý `null` giống nhau khi chuyển thành metrics.

## 18. Checked exceptions và exception wrapping

MBeanServer có các loại ngoại lệ từ registration, reflection, attribute access, invocation và lỗi implementation. Proxy client có thể chuyển hoặc bọc ngoại lệ theo cơ chế proxy/interceptor.

Các loại thường gặp:

| Exception | Tình huống |
|---|---|
| `InstanceNotFoundException` | ObjectName không có MBean |
| `AttributeNotFoundException` | Getter map tới attribute không tồn tại |
| `InvalidAttributeValueException` | Giá trị set không phù hợp |
| `MBeanException` | Exception từ logic MBean được gói lại |
| `ReflectionException` | Không tìm được method hoặc signature phù hợp |
| `ClassCastException` | Kiểu runtime không tương thích với kiểu client kỳ vọng |
| `UndeclaredThrowableException` | JDK proxy có checked exception không được interface khai báo và không được chuyển đổi phù hợp |
| `IOException` | Có thể gặp ở remote MBeanServerConnection |

Không nên dựa vào một exception type duy nhất để suy ra root cause. Đọc **cause chain**, metadata qua `getMBeanInfo` và log phía server. Đối với JMX local, lỗi network ít liên quan nhưng lỗi compliance/mapping, object lifecycle và logic implementation vẫn tồn tại.

Một interface proxy có thể thêm `throws` theo contract, nhưng Spring/JMX proxy không nhất thiết truyền đúng exception như method Java trực tiếp. Cần integration test để xác nhận lỗi được expose thế nào trong framework version cụ thể.

## 19. Đọc MBeanInfo để xác thực kiểu trả về

Trước khi tin vào interface proxy, hãy hỏi MBeanServer metadata thực sự cung cấp điều gì.

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class MBeanContractInspector {

    public static void inspect() throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
                "com.example.shop.orders:type=QueueMonitor,name=outbox");

        MBeanInfo info = server.getMBeanInfo(name);

        for (MBeanAttributeInfo attr : info.getAttributes()) {
            System.out.printf(
                    "ATTRIBUTE %s : %s readable=%s writable=%s%n",
                    attr.getName(),
                    attr.getType(),
                    attr.isReadable(),
                    attr.isWritable());
        }

        for (MBeanOperationInfo op : info.getOperations()) {
            System.out.printf(
                    "OPERATION %s -> %s%n",
                    op.getName(),
                    op.getReturnType());
        }
    }
}
```

Kết quả trả về từ `MBeanInfo` là thông tin client thật sự được expose; kiểm tra tên attribute, kiểu dữ liệu, operations và chữ ký tham số.

**Chú ý:** `MBeanInfo` mô tả kiểu theo metadata JMX, nhưng một custom DTO vẫn có thể gây vấn đề runtime serialization/classloader khi gọi thực sự. Metadata inspection phải đi cùng integration test gọi proxy và kiểm tra giá trị nhận được.

## 20. Khi local proxy cũng có rủi ro classloader

Cùng một JVM không đồng nghĩa mọi class đều dùng một classloader. Ứng dụng có thể có:

- Application classloader.
- Plugin module classloader.
- Container classloader.
- Classloader riêng của framework hoặc module.

Nếu hai classloaders khác nhau nạp hai class cùng tên `com.example.shop.QueueSnapshot`, JVM coi chúng là **hai kiểu khác nhau**. Một object do classloader A tạo có thể không cast được sang class do classloader B nạp, dù tên class giống hệt.

Biểu hiện:

```text
ClassCastException: com.example.shop.QueueSnapshot
cannot be cast to com.example.shop.QueueSnapshot
```

Thông điệp kiểu này có thể gây khó hiểu; root cause là classloader identity. Cách giảm rủi ro:

- Dùng interface và DTO contract được chia sẻ trong một module/classloader phù hợp.
- Trả scalar hoặc OpenType khi cần tương tác giữa plugin/classloader.
- Tránh expose implementation classes nội bộ qua management API.
- Test trong môi trường container/plugin thật, không chỉ chạy unit test cùng classpath.

## 21. Dynamic proxy không tự tạo cache hoặc backpressure

Vì method call trông giống gọi Java object, developer có thể quên đây là lệnh truy cập management server. Một exporter có thể poll proxy liên tục:

```java
int pending = proxy.getPendingCount();
```

Nhưng getter thật có thể truy vấn database hoặc tính toán nặng. Local proxy chỉ loại bỏ network hop, không loại bỏ:

- CPU cost của getter.
- Lock contention.
- JDBC/HTTP I/O phía target.
- Chi phí tạo `CompositeData`/`TabularData`.
- Tần suất của nhiều consumers.
- Nguy cơ operation có side effects.

Với MBean getter quan trọng, nên đọc cached snapshot hoặc counter nhẹ. Nếu cần truy vấn nặng, refresh theo lịch riêng hoặc công bố operation có chủ đích thay vì làm mỗi lần proxy đọc.

## 22. Kiểm chứng Spring proxy local bằng integration test

Một test có thể xác định cả hai yếu tố:

1. MBean đăng ký dưới ObjectName mong đợi.
2. Client proxy đọc được đúng attribute và gọi operation đúng semantics.

Ý tưởng:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;
import javax.management.JMX;

public class ProxyContractCheck {

    public static void verify() throws Exception {
        MBeanServer server =
                MBeanServerFactory.createMBeanServer("test");

        ObjectName name =
                new ObjectName("com.example.test:type=QueueMonitor");

        server.registerMBean(new QueueMonitor(), name);
        try {
            QueueMonitorMBean proxy = JMX.newMBeanProxy(
                    server, name, QueueMonitorMBean.class);

            if (proxy.getPendingCount() != 5) {
                throw new AssertionError("Wrong pending count");
            }

            proxy.pause();

            if (!proxy.isPaused()) {
                throw new AssertionError("Pause failed");
            }
        } finally {
            server.unregisterMBean(name);
        }
    }
}
```

Ví dụ dùng server test riêng để không làm ô nhiễm platform MBeanServer. Để test `MBeanProxyFactoryBean` thật, khởi động Spring context với factory, MBeanServer test và bean đã đăng ký, rồi kiểm tra proxy product từ Spring.

Không chỉ test `proxy != null`; proxy có thể được tạo trước khi MBean server chứa object đích (tùy cơ chế khởi tạo). Gọi method thật mới kiểm tra đường JMX end-to-end.

## 23. Chọn kiểu trả về phù hợp theo yêu cầu

| Nhu cầu | Return type/cách thiết kế thường phù hợp | Vì sao |
|---|---|---|
| Số lượng job, số thread | `int`, `long` | Đơn giản, dễ query và chuyển metric |
| Trạng thái enum | `String` hoặc enum với hợp đồng rõ | Hạn chế class dependency |
| Thời điểm cập nhật | `long` epoch millis | Dễ sử dụng nhiều client |
| Liên kết MBean khác | `ObjectName` | Chuẩn JMX |
| Snapshot nhiều field có schema rõ | `CompositeData` hoặc MXBean mapping hợp lệ | Open types hỗ trợ interoperability |
| Danh sách/bảng giới hạn | `TabularData` hoặc MXBean type hợp lệ | Có schema quản trị |
| DTO Java custom trong cùng module | Standard MBean với DTO đã kiểm soát | Chỉ khi client/classloader tương thích |
| Dữ liệu nghiệp vụ nhiều cấp hoặc rất lớn | Không trả thẳng qua JMX; thiết kế API khác | Tránh tải, leak và schema rối |
| Streaming/logs/traces | Dùng kênh tương ứng | JMX attribute không phù hợp dữ liệu dòng lớn |

Không có một return type “tốt nhất” cho mọi MBean. Chọn dựa trên **người tiêu thụ**, **mục đích**, **transport** và **độ ổn định contract**.

## 24. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `ClassCastException` khi nhận DTO | Return type khác metadata hoặc classloader khác | Kiểm tra interface, runtime type, classloader |
| `AttributeNotFoundException` | Proxy gọi getter không tương ứng attribute | Đọc `MBeanInfo`, sửa contract |
| `ReflectionException` khi invoke | Tên method/parameter signature sai | So sánh metadata method signatures |
| `InstanceNotFoundException` | ObjectName sai, chưa register hoặc đã unregister | Kiểm tra `isRegistered` và lifecycle |
| Local hoạt động, remote lỗi | Serialization hoặc client thiếu class | Dùng open types/MXBean hoặc shared DTO phù hợp |
| `CompositeData.get()` lỗi | Field name/schema thay đổi | Version và kiểm tra CompositeType |
| Trả danh sách rất lớn làm JConsole chậm | Attribute tạo snapshot nặng | Giới hạn dữ liệu, tách API |
| `null` trả về primitive | Không thể unbox | Dùng boxed type hoặc trạng thái phụ |
| Proxy chạy nhưng dữ liệu cũ | Getter target đọc cached snapshot | Công bố freshness/timestamp |
| Lỗi sau thay đổi `*MBean` interface | Proxy contract không khớp registered MBean | Tăng kiểm thử MBeanInfo và migration |

## 25. Bài tập thực hành

### Bài tập A — Chuyển lời gọi Java thành JMX

Với interface:

```java
public interface CacheMonitorMBean {
    int getEntryCount();
    boolean isEnabled();
    void clear();
}
```

Hãy viết lời gọi tương ứng bằng `MBeanServerConnection`.

Đáp án gợi ý:

```java
int count = (Integer) connection.getAttribute(name, "EntryCount");
boolean enabled =
        (Boolean) connection.getAttribute(name, "Enabled");

connection.invoke(name, "clear", new Object[0], new String[0]);
```

### Bài tập B — Chọn return type

Một MBean cần công bố `QueueState` với `pendingCount`, `paused`, `lastUpdatedMillis`. Hãy chọn giữa:

1. Ba scalar attributes.
2. Một `CompositeData`.
3. Custom DTO `QueueState`.

Giải thích sự đánh đổi giữa consistency, ease of use, open-type support và classloader/remote compatibility.

### Bài tập C — Interface không khớp

Client proxy khai báo:

```java
long getPendingCount();
```

nhưng MBean thật công bố:

```java
int getPendingCount();
```

Hãy đoán các rủi ro khi proxy nhận `Integer` nhưng caller mong `long`. Đề xuất kiểm tra `MBeanAttributeInfo.getType()` và sửa interface client để khớp contract, thay vì dựa vào ép kiểu tự động.

### Bài tập D — Chạy local và remote

Tạo Standard MBean trả về một custom `QueueSnapshot`. Chạy local qua platform MBeanServer, sau đó thử kết nối qua remote connector với một client không có DTO class.

Giải thích vì sao remote có thể lỗi deserialize/class loading và vì sao dùng `CompositeData` hoặc MXBean mapping hợp lệ giúp tương tác tốt hơn.

### Bài tập E — Spring MBeanProxyFactoryBean

Tạo một Spring context có `QueueMonitorMBean` local đã đăng ký và `MBeanProxyFactoryBean` dùng `setServer`, `setObjectName`, `setProxyInterface`. Lấy proxy từ context và gọi `getPendingCount()`.

Kiểm tra bằng `MBeanInfo` khi một method bị đổi tên hoặc kiểu trả về để nhìn thấy contract mismatch.

## 26. Câu hỏi tự kiểm tra

**1. Proxy local có trực tiếp gọi method trên target MBean instance không?**

Không theo nghĩa Java reference thông thường. Nó chuyển method call qua JMX connection/MBeanServer và ObjectName.

**2. Vì sao return type ở client cần khớp metadata MBean?**

Vì JMX trả kiểu theo contract server; proxy không tự biết cách chuyển mọi Object sang kiểu Java mong muốn.

**3. Local proxy có tránh được mọi lỗi class loading không?**

Không. Hai classloaders khác nhau trong cùng JVM có thể nạp hai type khác nhau dù tên trùng.

**4. Standard MBean và MXBean có cùng quy tắc xử lý DTO không?**

Không. MXBean có open-type mapping, Standard MBean có thể công bố Java type tùy chỉnh với các yêu cầu tương thích phù hợp.

**5. `MBeanProxyFactoryBean` có phải server-side MBeanExporter không?**

Không. Factory này giúp tạo client proxy gọi MBean đã đăng ký; `MBeanExporter` là cơ chế phía server để export Spring beans.

**6. `List<CustomDto>` có luôn là lựa chọn JMX portable không?**

Không. Generic type, mapping, serialization và classloader cần được xem xét.

**7. Một local MBean getter có thể chậm không?**

Có. Dù không có network, getter vẫn có thể thực hiện SQL, HTTP hoặc giữ lock lâu.

## 27. Ghi nhớ

- **MBean proxy** là lớp client giúp gọi JMX như gọi Java interface; lời gọi thực đi qua `MBeanServerConnection`.
- Local proxy không cần network nhưng vẫn chịu ràng buộc **ObjectName**, **MBeanInfo**, method signatures, lifecycle và type compatibility.
- `JMX.newMBeanProxy` dùng cho Standard MBean; `JMX.newMXBeanProxy` dùng cho MXBean với mapping tương ứng.
- Spring `MBeanProxyFactoryBean` tạo client proxy; khác với `MBeanExporter` dùng để export MBean từ Spring context.
- Return types đơn giản (`int`, `long`, `boolean`, `String`) dễ duy trì. Với cấu trúc phức tạp, cân nhắc `CompositeData`, `TabularData` hoặc MXBean mapping đã được xác minh.
- Custom DTO có thể chạy local nhưng fail remote do serialization/class loading; local cũng có thể fail do classloader khác nhau.
- Interface proxy phải khớp MBean attributes/operations, kể cả parameter signatures và return types.
- Đọc `MBeanInfo` và gọi method thật trong integration test để phát hiện mismatch.
- Tránh trả entity nghiệp vụ, object graph lớn, secrets hoặc collection không giới hạn qua JMX.

## 28. Tài liệu tham khảo

- Java SE 21 — `javax.management.JMX`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/JMX.html
- Java SE 21 — `MBeanServerConnection`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE 21 — `CompositeData`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/openmbean/CompositeData.html
- Java SE 21 — `TabularData`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/openmbean/TabularData.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — `MBeanProxyFactoryBean`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/access/MBeanProxyFactoryBean.html
- Spring Framework Javadoc — `MBeanClientInterceptor`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/access/MBeanClientInterceptor.html
