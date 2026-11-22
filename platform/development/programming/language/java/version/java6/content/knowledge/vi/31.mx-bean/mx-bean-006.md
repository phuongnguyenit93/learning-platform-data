# JMX.newMXBeanProxy và gọi MXBean qua proxy trong Java

## 1. Vì sao cần MXBean proxy?

Trong JMX (Java Management Extensions), một **MXBean** là giao diện quản trị cho phép giám sát và điều khiển thành phần của ứng dụng/JVM bằng **Open Types**. Một công cụ theo dõi có thể đọc thông tin hiệu năng từ một MBean server mà không cần tải tất cả các class Java nội bộ của đối tượng được giám sát.

Ở phía ứng dụng, bạn có hai cách tương tác với MBean đã đăng ký:

- **Dùng API cấp thấp** `MBeanServerConnection.getAttribute(...)`, `setAttribute(...)` và `invoke(...)` với tên thuộc tính, operation và `ObjectName` dạng chuỗi.
- **Dùng typed proxy** tạo bởi `JMX.newMXBeanProxy(...)`, sau đó gọi như một Java interface thông thường: `proxy.getSize()`, `proxy.setMode("active")`, `proxy.reset()`.

`JMX.newMXBeanProxy` thuộc package `javax.management`, module `java.management`, và **vẫn là API hiện hành trên Java 17+**. Nó không khởi động một server JMX, không kết nối mạng nếu bạn đưa vào local MBeanServer và không tự cấp quyền truy cập. Nhiệm vụ chính là tạo **Java dynamic proxy** biết chuyển đổi Java types ↔ JMX Open Types rồi chuyển lời gọi qua `MBeanServerConnection`.

Mục tiêu bài học:

1. Hiểu chữ ký hai overloads của `JMX.newMXBeanProxy` và bốn input cốt lõi.
2. Tạo MXBean, đăng ký vào MBeanServer, tạo proxy, đọc/ghi attributes và gọi operations.
3. Quan sát ánh xạ `List<String> ↔ String[]`, `Map<String,Integer> ↔ TabularData` và `MemoryUsage ↔ CompositeData`.
4. Hiểu `MBeanServerInvocationHandler`, `Proxy`, semantics `equals/hashCode/toString`.
5. Đăng ký và hủy lắng nghe notification qua `notificationEmitter=true`.
6. Phân biệt proxy creation với sự tồn tại/quyền truy cập MBean đích.
7. Biết khi nào chọn `newMXBeanProxy`, `newMBeanProxy` và `ManagementFactory.newPlatformMXBeanProxy`.
8. Quản lý lỗi, kết nối remote, authorization và lifecycle tài nguyên.

> **Nhớ:** Typed proxy là một **client-side adapter** cho API JMX; nó **không biến** một MBean bất kỳ thành MXBean, không tạo server và không bảo đảm kết nối/operation sẽ thành công.

## 2. Ba thực thể khác nhau: interface, MBean instance và proxy

Giả sử bạn muốn theo dõi trạng thái cache.

~~~java
public interface CacheMXBean {
    int getSize();
    void clear();
}
~~~

Interface này mô tả hợp đồng quản trị. Một object `Cache` implements nó chứa trạng thái thật. Đối tượng được đăng ký vào một `MBeanServer` với `ObjectName`, ví dụ `demo.cache:type=Cache`. Cuối cùng, một client tạo **proxy** từ connection + ObjectName + interface class:

~~~java
CacheMXBean proxy = JMX.newMXBeanProxy(
        connection,
        new ObjectName("demo.cache:type=Cache"),
        CacheMXBean.class);

int current = proxy.getSize();
proxy.clear();
~~~

Đây là snippet, `connection` phải là `MBeanServerConnection` trỏ đến server chứa Cache MBean; `CacheMXBean` và implementation cần được khai báo hợp lệ. Chưa có chúng, code riêng lẻ chưa phải một chương trình chạy đầy đủ. Chương trình hoàn chỉnh ở mục 11 cung cấp tất cả definitions và môi trường nội bộ.

### 2.1. Luồng gọi qua proxy

~~~text
Java client code                         MBeanServer
----------------                         -----------
CacheMXBean proxy
       |
       | proxy.getSize()
       v
java.lang.reflect.Proxy
       |
       v
MBeanServerInvocationHandler
       |
       | getAttribute(ObjectName, "Size")
       +------------------------------------> registered Cache MXBean
       |                                         |
       | <---------------------------------------+
       |         OpenData / primitive value
       v
OpenType -> Java type conversion
       |
       v
int size returned to caller
~~~

Khi operation có tham số kiểu phức tạp, proxy còn **chuyển Java argument thành OpenData** trước khi gửi, rồi chuyển kết quả OpenData trở lại kiểu khai báo trong MXBean interface.

### 2.2. Không nhầm ObjectName và Java class name

| Thành phần | Chức năng | Ví dụ |
| --- | --- | --- |
| `CacheMXBean.class` | Management interface contract | Public Java interface |
| `new Cache()` | Implementation object có state | In-memory cache |
| `MBeanServer` | Registry/dispatcher của MBeans | Local server do app tạo |
| `ObjectName` | Tên instance trong registry | `demo.cache:type=Cache` |
| `MBeanServerConnection` | Đường gọi local hoặc remote đến registry | `MBeanServer` cũng là một connection |
| `CacheMXBean proxy` | Client adapter forwarding calls | JDK dynamic proxy object |

Nhiều MBean instances có thể cùng Java interface nhưng khác ObjectName; một proxy trỏ tới **một connection và một ObjectName cụ thể**. Việc đổi instance ở phía server hoặc unregister sẽ ảnh hưởng đến các lời gọi tiếp theo; proxy không tự sở hữu hay khóa vòng đời đối tượng.

## 3. API JMX.newMXBeanProxy hiện hành

Hai overloads:

~~~java
public static <T> T newMXBeanProxy(
        MBeanServerConnection connection,
        ObjectName objectName,
        Class<T> interfaceClass);

public static <T> T newMXBeanProxy(
        MBeanServerConnection connection,
        ObjectName objectName,
        Class<T> interfaceClass,
        boolean notificationEmitter);
~~~

Đây là chữ ký minh họa đã đối chiếu Java SE 26. Overload ba tham số tương đương gọi overload bốn tham số với `notificationEmitter=false`.

| Tham số | Ý nghĩa | Điểm cần validate |
| --- | --- | --- |
| `connection` | MBeanServerConnection để forward operations | Local/remote nào, đang mở, auth/permissions gì |
| `objectName` | Instance được target trong server | Name đúng domain/properties và được phép truy cập |
| `interfaceClass` | Java interface dùng làm hợp đồng proxy | Mappable theo MXBean rules, khớp contract server |
| `notificationEmitter` | Khi true, proxy còn implements `NotificationEmitter` | MBean phía server thực sự phát notifications |

Kiểu trả về `T` để caller giữ typed reference: `CacheMXBean proxy`. Nội bộ nó là object do `java.lang.reflect.Proxy` tạo, với handler `MBeanServerInvocationHandler`.

**Không có tham số hostname/port** trong `newMXBeanProxy`. Nếu làm remote JMX, bước kết nối/định danh server nằm ở `JMXConnectorFactory` và `MBeanServerConnection` **trước đó**.

### 3.1. Phép kiểm interface và lỗi tuân thủ

`JMX.newMXBeanProxy` có thể ném `IllegalArgumentException` nếu `interfaceClass` không phải management interface thích hợp/không có MXBean type mapping hợp lệ. **Điều đó không đồng nghĩa method sẽ từ chối mọi interface thiếu hậu tố MXBean**. Thí nghiệm Java17/JDK24 cho thấy một public interface `PlainView` chỉ khai báo `String getMode()`, dù `JMX.isMXBeanInterface(PlainView.class) == false`, vẫn tạo được typed proxy và đọc attribute `Mode` từ một MXBean phù hợp.

Phân biệt:

- `JMX.isMXBeanInterface(type)`: **quy tắc nhận diện interface để export tự động** theo public, suffix `MXBean` hoặc `@MXBean`.
- `JMX.newMXBeanProxy(..., type)`: **khả năng tạo client proxy** với management method signatures mappable.
- `MBeanServer.isRegistered(name)` và descriptor `mxbean`: **thực thể đã đăng ký** trên server.
- Thực tế lời gọi `proxy.getX()`: **một lần JMX I/O/dispatch và chuyển đổi dữ liệu**, có thể thất bại vì target, type, quyền, mạng hoặc server-side operation.

Tốt nhất, public API nên dùng **đúng MXBean interface contract** mà server công bố, thay vì dựa vào một interface gần giống chỉ tình cờ có methods tương thích.

## 4. Điều kiện trước khi tạo proxy

Một quy trình đáng tin cho ứng dụng:

1. Xác định interface quản trị được server công bố (ví dụ `MetricsMXBean`).
2. Xác định chính xác `ObjectName` đã đăng ký.
3. Chuẩn bị `MBeanServerConnection`: local server hoặc authenticated/authorized remote connector.
4. Nếu cần fail fast, kiểm `isRegistered(name)` và `getMBeanInfo(name)`, đặc biệt descriptor MXBean.
5. Gọi `JMX.newMXBeanProxy(connection, name, MetricsMXBean.class)`.
6. Thực hiện getter/setter/operations theo contract.
7. Bắt và xử lý lỗi tại **mỗi lời gọi**, không chỉ ở bước tạo proxy.
8. Khi dùng notifications, đăng ký listener, tháo listener trong `finally` và đóng connector do caller sở hữu.

### 4.1. Kiểm target đã đăng ký

~~~java
if (!connection.isRegistered(objectName)) {
    throw new IllegalStateException("Required MXBean not registered");
}
~~~

Đây là snippet, `connection` và `objectName` đã được tạo. `isRegistered` là một lời gọi có thể liên quan tới remote I/O; giữa phép kiểm và lời gọi tiếp theo, MXBean vẫn có thể bị unregister hoặc connection mất. Đây là **preflight hữu ích**, không phải giao dịch nguyên tử chặn race.

### 4.2. Kiểm metadata của instance, không chỉ suffix Java

~~~java
MBeanInfo info = connection.getMBeanInfo(objectName);
Object rawFlag = info.getDescriptor()
        .getFieldValue(JMX.MXBEAN_FIELD);

boolean isMxBean = Boolean.parseBoolean(
        String.valueOf(rawFlag));
~~~

JMX descriptor field `mxbean` giúp xác định instance đã được đăng ký với MXBean semantics. Đừng coi ObjectName có `type=MXBean` là bằng chứng: đó chỉ là phần text trong tên instance.

Nếu MXBean do provider bên thứ ba triển khai, hãy kiểm metadata và OpenType definitions theo contract, xử lý trường vắng mặt hoặc lỗi một cách có kiểm soát.

### 4.3. Tạo proxy không đòi hỏi MBean đích đang tồn tại

Đây là một đặc điểm quan trọng đã kiểm chứng:

~~~java
ObjectName missing =
        new ObjectName("demo.metrics:type=Missing");

MetricsMXBean proxy = JMX.newMXBeanProxy(
        connection, missing, MetricsMXBean.class);
~~~

Proxy có thể được **tạo thành công** mặc dù `connection.isRegistered(missing)==false`. Nhưng `proxy.getMode()` sẽ thất bại khi invocation thực sự được forward tới server. Đừng viết health check chỉ bằng:

~~~java
boolean healthy = proxy != null;
~~~

Nó chỉ chứng minh object proxy được tạo, **không chứng minh** server tồn tại, kết nối đang hoạt động, user được cấp quyền hoặc dữ liệu trả về hợp lệ.

## 5. Getter và setter đi qua MBeanServerConnection ra sao?

Một MXBean interface thường dùng JavaBeans-like conventions:

~~~java
public interface MetricsMXBean {
    String getMode();
    void setMode(String value);
    boolean isEnabled();
    void reset();
}
~~~

Chữ ký thông thường:

- `getMode()` → đọc attribute `"Mode"`.
- `setMode(value)` → cập nhật attribute `"Mode"`.
- `isEnabled()` → đọc boolean attribute `"Enabled"`.
- `reset()` → gọi JMX operation `"reset"`.

Khi dùng typed proxy:

~~~java
String original = proxy.getMode();
proxy.setMode("active");
String updated = proxy.getMode();
proxy.reset();
~~~

Đây là snippet; `proxy` là `MetricsMXBean` đã khởi tạo. Bên dưới, handler thường dùng:

~~~java
connection.getAttribute(name, "Mode");

connection.setAttribute(
        name,
        new Attribute("Mode", "active"));

connection.invoke(name, "reset", new Object[0], new String[0]);
~~~

Đây là **diễn giải tương đương về cơ chế**, không nhất thiết là call sequence/implementation detail tuyệt đối của mọi JDK/provider; `name` là ObjectName. Proxy che bớt chuỗi tên attribute, `Attribute` wrapper và operation signatures.

### 5.1. Lợi ích type-safe và giới hạn

Ưu điểm:

- Java compiler kiểm tên method và kiểu arguments/return từ interface.
- Không phải tự viết `getAttribute("...")` và ép kiểu OpenData ở mọi điểm.
- Có thể tái sử dụng chung interface giữa MXBean producer và client khi classpath phù hợp.

Giới hạn:

- Type-safe **tại compile time** không đảm bảo server-side MBean vẫn có đúng attribute/operation.
- Một method có thể ném lỗi do remote I/O, security, mapping hoặc business logic.
- Đồng thời giữa hai lời gọi getter và setter, state có thể thay đổi; proxy không tạo transaction.
- Một proxy không tự retry, không tự thay đổi ObjectName khi service restart và không tự khóa consistency.

### 5.2. Không biến getter thành công việc nặng

MXBean getter có thể được gọi liên tục bởi monitoring agents. Cân nhắc trả metric snapshot nhỏ, không làm database scan, network call hoặc blocking operation vô hạn. Một typed proxy giúp code dễ đọc nhưng không giới hạn thời gian/memory của server-side method.

## 6. Gọi operations và xử lý tham số

Giả sử interface có:

~~~java
public interface MetricsMXBean {
    int add(int left, int right);
    List<String> reverse(List<String> values);
    void reset();
}
~~~

Typed proxy:

~~~java
int sum = proxy.add(2, 5);

List<String> mirrored = proxy.reverse(
        List.of("a", "b", "c"));

proxy.reset();
~~~

Kết quả mong đợi trong demo:

~~~text
sum = 7
mirrored = [c, b, a]
~~~

Đây là kết quả của implementation minh họa, **không phải method tiêu chuẩn của Java JMX**. Ở mức JMX server, `add` và `reverse` là operations; proxy chuyển arguments sang Open Types, gọi `MBeanServerConnection.invoke(...)`, sau đó chuyển kết quả.

### 6.1. Generic types và reconstruction

`List<String>` không được truyền nguyên trạng như một `java.util.List` khi đi qua MXBean mapping chuẩn. MXBean mapping chuyển nó thành `String[]`, có thể dùng được với công cụ JMX generic. Khi proxy nhận `String[]`, handler tái tạo kiểu danh sách theo contract.

Điều này khác với Standard MBean có thể làm lộ Java-specific types. Vì vậy `JMX.newMXBeanProxy` **không đơn giản là một cái tên khác** của `JMX.newMBeanProxy`.

### 6.2. Không gọi operations tùy ý từ input

Nếu client có thể truyền tên operation do user nhập vào và bạn tự gọi `connection.invoke(...)` thì cần allowlist và authorization. Typed interface giảm bề mặt gọi nhầm, nhưng **không thay security policy**: nếu operation `reset()` có ảnh hưởng production, access tới management connection cũng phải được kiểm soát.

## 7. OpenType mapping: List, Map, CompositeData

MXBean được thiết kế để chuyển một tập Java types sang JMX Open Data. Đó là điểm quan trọng nhất khi gọi qua proxy.

| Java type trong MXBean interface | Raw JMX OpenType phổ biến | Giá trị khi qua typed proxy |
| --- | --- | --- |
| `int` / `long` / `boolean` | Primitive/wrapper tương ứng | Kiểu đã khai báo |
| `String` | `String` | `String` |
| `List<String>` | `String[]` qua `ArrayType` | `List<String>` |
| `Map<String,Integer>` | `TabularData` | `Map<String,Integer>` |
| `MemoryUsage` | `CompositeData` | `MemoryUsage` |
| Java enum đủ điều kiện | `String` biểu diễn enum name | Enum value |
| `ObjectName` | `ObjectName` | `ObjectName` |
| MXBean reference đủ điều kiện | `ObjectName` | MXBean proxy/reference phù hợp |
| `Object` tùy ý | **Không có mapping tổng quát** | Không tự hợp lệ |

**Không suy đoán tất cả Java classes đều chuyển được.** Các type có thể cần `@ConstructorProperties`, `from(CompositeData)` hoặc những quy tắc reconstruction khác, tùy loại và API. Tập hợp/map nested có điều kiện mapping riêng.

### 7.1. `List<String>`

Server exposes getter:

~~~java
public List<String> getTags() {
    return List.of("alpha", "beta");
}
~~~

Nếu đã đăng ký thành MXBean:

~~~java
Object raw = server.getAttribute(name, "Tags");
boolean openArray = raw instanceof String[];

List<String> typed = proxy.getTags();
~~~

Trong demo, `openArray==true` và `typed.equals(List.of("alpha","beta"))==true`. Không nhầm raw OpenData response với return type của proxy.

### 7.2. `Map<String,Integer>`

Server:

~~~java
public Map<String, Integer> getCounts() {
    return Map.of("accepted", 3, "rejected", 1);
}
~~~

Raw JMX:

~~~java
Object raw = server.getAttribute(name, "Counts");
boolean table = raw instanceof TabularData;
~~~

Proxy:

~~~java
Map<String, Integer> counts = proxy.getCounts();
int accepted = counts.get("accepted");
~~~

Test xác nhận raw data là `TabularData` nhưng proxy trả `Map<String,Integer>`. **Không dựa vào iteration order** của Map sau OpenData reconstruction trừ khi contract riêng có yêu cầu và được test.

### 7.3. `MemoryUsage` và `CompositeData`

`java.lang.management.MemoryUsage` là loại MXBean-friendly được JDK dùng rộng rãi. Trong demo:

~~~java
MemoryUsage usage = new MemoryUsage(1L, 2L, 3L, 4L);
~~~

Các trường `init`, `used`, `committed` và `max` trong ví dụ lần lượt là 1,2,3,4. Khi đọc raw attribute `UsageSnapshot` từ MBeanServer, giá trị là `CompositeData`; typed proxy có thể tái tạo `MemoryUsage`.

~~~java
Object rawUsage = server.getAttribute(
        name, "UsageSnapshot");

MemoryUsage typedUsage = proxy.getUsageSnapshot();
~~~

Chương trình xác nhận `rawUsage instanceof CompositeData` và bốn giá trị trong `typedUsage`. Không cần người viết client tự bóc `CompositeData.get("used")` rồi dựng MemoryUsage cho trường hợp thông thường.

### 7.4. Vì sao không nên dùng `Object` làm return type tùy ý?

~~~java
public interface InvalidMXBean {
    Object getUnsupported();
}
~~~

`Object` không có ánh xạ OpenType tổng quát để bảo đảm client bên kia hiểu/reconstruct được. Trong kiểm thử, `JMX.newMXBeanProxy(..., InvalidMXBean.class)` bị từ chối bằng `IllegalArgumentException`. Nên thiết kế management contract bằng những types/DTO được JMX mapping hỗ trợ, thay vì trả object domain nội bộ không kiểm soát.

## 8. Dynamic proxy, InvocationHandler và Object methods

`JMX.newMXBeanProxy` trả object thuộc `java.lang.reflect.Proxy`, với invocation handler kiểu `javax.management.MBeanServerInvocationHandler`.

~~~java
MetricsMXBean proxy = JMX.newMXBeanProxy(
        server, name, MetricsMXBean.class);

boolean dynamic = Proxy.isProxyClass(proxy.getClass());

MBeanServerInvocationHandler handler =
        (MBeanServerInvocationHandler)
        Proxy.getInvocationHandler(proxy);
~~~

`dynamic` là true trong test. Handler cung cấp:

~~~java
boolean mx = handler.isMXBean();

MBeanServerConnection connection =
        handler.getMBeanServerConnection();

ObjectName objectName =
        handler.getObjectName();
~~~

Cả ba giá trị giúp xác nhận proxy forward bằng **MXBean conversion** qua đúng server và đúng ObjectName. Chúng **không** thay thế authorization hoặc health check: handler chỉ chứa metadata phía client.

### 8.1. `equals`, `hashCode` và `toString` không phải remote business calls thông thường

Theo JavaDoc `MBeanServerInvocationHandler`:

- `toString()` thường trả string mô tả proxy.
- `hashCode()` thường dựa trên identity của connection/ObjectName/interface.
- `equals(Object)` so sánh proxy class cùng invocation handler phù hợp với connection, ObjectName và interface class.

Nếu management interface **tự khai báo** một method tương ứng, behavior có thể khác và method có thể được forward. Vì vậy đừng nhầm:

~~~java
proxy.equals(otherProxy)
~~~

với so sánh trạng thái cache phía server. Trong demo, hai proxies được tạo bằng cùng `MBeanServerConnection`, `ObjectName` và `MetricsMXBean.class` được xác nhận `equals==true` và hashCode giống nhau.

Không dùng `proxy.toString()` làm nguồn business data hoặc identity bảo mật; đó là biểu diễn client proxy, không phải chứng thư của remote server.

### 8.2. Cùng ObjectName nhưng khác connection không chắc bằng nhau

Hai proxies cùng trỏ tới tên `demo.metrics:type=Service` trên hai server/connector khác nhau có thể không bằng nhau. `ObjectName` chỉ duy nhất **trong một MBean server**, không phải định danh toàn cầu của mọi JVM. Khi cache proxies, nên gắn lifecycle của cache với connection/target JVM cụ thể.

## 9. Tham số `notificationEmitter=true` và NotificationEmitter

Overload bốn tham số:

~~~java
MetricsMXBean proxy = JMX.newMXBeanProxy(
        connection,
        objectName,
        MetricsMXBean.class,
        true);
~~~

Khi flag `true`, proxy còn triển khai `javax.management.NotificationEmitter`; lời gọi `addNotificationListener/removeNotificationListener` được forward qua `MBeanServerConnection`.

~~~java
NotificationEmitter emitter =
        (NotificationEmitter) proxy;

NotificationListener listener =
        (notification, handback) -> {
            if ("demo.metrics.reset".equals(notification.getType())) {
                System.out.println("Metrics reset event");
            }
        };

emitter.addNotificationListener(listener, null, null);
try {
    proxy.reset();
} finally {
    emitter.removeNotificationListener(listener);
}
~~~

Đây là snippet; chỉ hoạt động đúng nếu target thực sự là `NotificationBroadcaster/NotificationEmitter` được server expose và đã được phép subscribe. Gọi overload bốn tham số với `false` không tự thêm interface NotificationEmitter vào proxy.

### 9.1. Flag true không làm target tự phát notification

`notificationEmitter=true` chỉ yêu cầu client-side proxy forwarding. Actual MBean phải hỗ trợ phát notification. Trong chương trình:

- Implementation `Metrics` extends `NotificationBroadcasterSupport`.
- `reset()` gọi `sendNotification(new Notification(...))`.
- Listener đếm đúng **một** notification sau một lần reset.
- Listener được gỡ trong `finally`.
- Lần reset tiếp theo không còn gọi listener đã tháo.

Đừng tạo `notificationEmitter=true` cho mọi MBean chỉ vì mong có events. Nếu server không support, listener operations sẽ gặp lỗi JMX tương ứng.

### 9.2. Listener lifecycle và memory leak

Một listener đăng ký vào remote/local MBeanServer có thể giữ tham chiếu đến object client hoặc làm connection tiếp tục tiêu thụ tài nguyên. Luôn:

1. Đăng ký listener một cách có kiểm soát.
2. Xác định NotificationFilter và handback nếu cần.
3. Tháo listener khi subscription dừng.
4. Khi dùng remote connector, đóng connector lúc hoàn tất.
5. Xử lý reconnection/re-subscribe theo policy, không giả định subscription sống qua mất kết nối.

Notification events có thể tới bất đồng bộ, không nên dựng logic core business đòi exactly-once delivery chỉ dựa vào JMX notifications.

## 10. Lỗi: proxy được tạo thành công vẫn có thể gọi thất bại

Những trường hợp tiêu biểu:

| Giai đoạn | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| Tạo ObjectName | Syntax sai | Bắt `MalformedObjectNameException`, validate config |
| Tạo proxy | Interface không compliant, OpenType mapping sai | `IllegalArgumentException`, sửa contract |
| Kiểm isRegistered | Server không có MBean, remote I/O lỗi | Fail fast, retry bounded theo policy |
| Getter | Attribute không tồn tại hoặc không được đọc | Kiểm `MBeanInfo`/server version |
| Setter | Attribute read-only hoặc giá trị bị từ chối | Đọc metadata, validate allowed values |
| Operation | Method/signature không khớp | So interface/server contract |
| OpenType conversion | Kiểu raw không đúng hoặc reconstruction thất bại | Kiểm mapping, provider/versions |
| Remote connector | Mất mạng, timeout, authorization lỗi | Limit time, reconnect có kiểm soát |
| Notification subscribe | Target không phát notifications/quyền thiếu | Chỉ subscribe nếu supported |
| Sau unregister | ObjectName biến mất | Refresh discovery/re-register theo lifecycle |
| Proxy equals/toString | Hiểu nhầm là server call | Không dùng làm health check |

Các `MBeanServerConnection` methods có checked exceptions như `IOException`, `InstanceNotFoundException`, `AttributeNotFoundException`, `MBeanException`, `ReflectionException`, `JMRuntimeException` tùy operation. Khi gọi qua typed proxy, checked exception **không khai báo trên interface** có thể đi qua dynamic proxy dưới dạng `UndeclaredThrowableException`; cũng có thể gặp các runtime exceptions khác. Hãy xem **cause chain** và phân loại lỗi thay vì catch `Exception` rồi biến thành "0 metrics".

### 10.1. Target chưa đăng ký: lỗi phát sinh lúc invocation

Demo kiểm:

~~~java
ObjectName missing =
        new ObjectName("demo.metrics:type=Missing");

MetricsMXBean lazy = JMX.newMXBeanProxy(
        server, missing, MetricsMXBean.class);

// lazy được tạo, nhưng target không có.
lazy.getMode(); // Gây lỗi tại thời điểm dispatch.
~~~

Đừng chủ quan rằng constructor proxy đã kiểm remote target hoặc authentication. Để kiểm ready/health, dùng `isRegistered` và một getter không có side effects nếu contract định nghĩa; vẫn cần timeouts/circuit breaker với remote JMX.

### 10.2. Khi OpenType không match

Nếu server đổi `getCounts()` từ `Map<String,Integer>` sang kiểu khác, client interface cũ vẫn compile nhưng invocation có thể fail ở runtime hoặc reconstruction. Quản lý compatibility:

- Ưu tiên giữ contract ổn định.
- Có versioning rõ ràng cho management interfaces/ObjectNames khi đổi semantics.
- Không serialize Java implementation classes qua JMX mong clients không có classpath vẫn dùng được.
- Kiểm `MBeanInfo` và `OpenType` trong integration tests.
- Triển khai rollout/reconnect có kiểm soát.

### 10.3. Không retry operation thay đổi state tùy ý

Một call `reset()` hoặc `clear()` có thể **đã thực thi trên server** nhưng client mất kết nối trước khi nhận response. Retry mù có thể tạo side effects trùng lặp. Với operation nhạy cảm, thiết kế idempotency, confirmation hoặc status query theo protocol của ứng dụng; đừng giả định transport tự biết request đã được xử lý hay chưa.

## 11. Ví dụ #1 hoàn chỉnh: typed proxy, OpenData, notification

### 11.1. Mục đích và giới hạn

Chương trình `MxBeanProxyDemo.java` là Java 17+ độc lập, không cần Maven, credentials, port hay JVM khác. Nó:

- Tạo một `MBeanServer` tạm **trong JVM hiện tại** bằng `MBeanServerFactory.createMBeanServer`.
- Đăng ký `Metrics` implements `MetricsMXBean` dưới ObjectName cụ thể.
- Đọc metadata và xác minh descriptor `mxbean=true`.
- Tạo `JMX.newMXBeanProxy(...)` và xác minh JDK Proxy/handler.
- Gọi getters, setters và operations.
- Kiểm raw OpenData `String[]`, `TabularData`, `CompositeData` và typed results.
- Kiểm `equals/hashCode/toString` cho hai proxies cùng connection/name/interface.
- Thử một **plain interface không có suffix** nhưng method signature phù hợp với attribute có sẵn.
- Thử interface trả `Object` không mappable, xác nhận proxy creation bị từ chối.
- Tạo `notificationEmitter=true` proxy, thêm listener, gọi reset, tháo listener và xác minh.
- Chứng minh proxy có thể tạo khi ObjectName không đăng ký, nhưng invocation thất bại.
- `finally` unregister và release MBeanServer tạm.
- Không khởi động JMX remote connector, không mở TCP socket.

Toàn bộ test chạy trên JDK24 qua `javac --release 17`. Các số liệu là dữ liệu giả lập trong memory, không phải metrics thực tế của máy.

### 11.2. Source `MxBeanProxyDemo.java`

~~~java
import java.lang.management.MemoryUsage;
import java.lang.reflect.Proxy;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import javax.management.JMX;
import javax.management.MBeanNotificationInfo;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.MBeanServerInvocationHandler;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;
import javax.management.NotificationEmitter;
import javax.management.NotificationListener;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;
import javax.management.openmbean.TabularData;

public final class MxBeanProxyDemo {
    public interface MetricsMXBean {
        String getMode();
        void setMode(String value);
        List<String> getTags();
        Map<String, Integer> getCounts();
        MemoryUsage getUsageSnapshot();
        List<String> reverse(List<String> values);
        int add(int left, int right);
        void reset();
    }

    public interface PlainView {
        String getMode();
    }

    public interface InvalidMXBean {
        Object getUnsupported();
    }

    public static final class Metrics
            extends NotificationBroadcasterSupport
            implements MetricsMXBean {
        private String mode = "idle";
        private int count = 3;
        private long sequence;

        @Override
        public synchronized String getMode() {
            return mode;
        }

        @Override
        public synchronized void setMode(String value) {
            if (!List.of("idle", "active").contains(value)) {
                throw new IllegalArgumentException("Invalid mode");
            }
            mode = value;
        }

        @Override
        public List<String> getTags() {
            return List.of("alpha", "beta");
        }

        @Override
        public synchronized Map<String, Integer> getCounts() {
            Map<String, Integer> counts = new LinkedHashMap<>();
            counts.put("accepted", count);
            counts.put("rejected", 1);
            return counts;
        }

        @Override
        public MemoryUsage getUsageSnapshot() {
            return new MemoryUsage(1L, 2L, 3L, 4L);
        }

        @Override
        public List<String> reverse(List<String> values) {
            List<String> copy = new ArrayList<>(values);
            Collections.reverse(copy);
            return copy;
        }

        @Override
        public int add(int left, int right) {
            return Math.addExact(left, right);
        }

        @Override
        public synchronized void reset() {
            count = 0;
            sendNotification(new Notification(
                    "demo.metrics.reset", this, ++sequence, "reset"));
        }

        @Override
        public MBeanNotificationInfo[] getNotificationInfo() {
            return new MBeanNotificationInfo[] {
                new MBeanNotificationInfo(
                    new String[] {"demo.metrics.reset"},
                    Notification.class.getName(), "Metrics reset")
            };
        }
    }

    static void require(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws Exception {
        MBeanServer server =
                MBeanServerFactory.createMBeanServer("demo");
        ObjectName name =
                new ObjectName("demo.metrics:type=Service,name=Main");

        try {
            require(JMX.isMXBeanInterface(MetricsMXBean.class),
                    "not MXBean interface");
            server.registerMBean(new Metrics(), name);
            Object metadata = server.getMBeanInfo(name)
                    .getDescriptor()
                    .getFieldValue(JMX.MXBEAN_FIELD);
            require(Boolean.parseBoolean(String.valueOf(metadata)),
                    "not registered MXBean");
            System.out.println("Registered MXBean descriptor: true");

            MetricsMXBean proxy = JMX.newMXBeanProxy(
                    server, name, MetricsMXBean.class);
            require(Proxy.isProxyClass(proxy.getClass()),
                    "not Proxy");
            MBeanServerInvocationHandler handler =
                    (MBeanServerInvocationHandler)
                    Proxy.getInvocationHandler(proxy);
            require(handler.isMXBean()
                    && handler.getObjectName().equals(name)
                    && handler.getMBeanServerConnection() == server,
                    "wrong invocation handler");
            System.out.println("Typed dynamic proxy handler: true");

            require("idle".equals(proxy.getMode()), "get");
            proxy.setMode("active");
            require("active".equals(proxy.getMode())
                    && "active".equals(
                            server.getAttribute(name, "Mode")),
                    "set/get");
            System.out.println("Getter and setter forwarded: true");

            require(proxy.add(2, 5) == 7, "operation");
            require(proxy.reverse(List.of("a", "b", "c"))
                    .equals(List.of("c", "b", "a")),
                    "list arguments");
            System.out.println(
                    "Operations and List round-trip: true");

            require(server.getAttribute(name, "Tags") instanceof String[],
                    "List raw open");
            require(proxy.getTags().equals(
                    List.of("alpha", "beta")),
                    "List reconstruct");
            System.out.println(
                    "List raw String[] mapped to List: true");

            require(server.getAttribute(name, "Counts")
                    instanceof TabularData, "Map raw open");
            Map<String, Integer> counts = proxy.getCounts();
            require(counts.get("accepted") == 3
                    && counts.get("rejected") == 1,
                    "Map reconstruct");
            System.out.println(
                    "Map raw TabularData mapped to Map: true");

            require(server.getAttribute(name, "UsageSnapshot")
                    instanceof CompositeData,
                    "usage raw composite");
            MemoryUsage usage = proxy.getUsageSnapshot();
            require(usage.getInit() == 1
                    && usage.getUsed() == 2
                    && usage.getCommitted() == 3
                    && usage.getMax() == 4,
                    "usage reconstruct");
            System.out.println(
                    "MemoryUsage raw CompositeData mapped: true");

            MetricsMXBean equalProxy = JMX.newMXBeanProxy(
                    server, name, MetricsMXBean.class);
            require(proxy.equals(equalProxy)
                    && proxy.hashCode() == equalProxy.hashCode()
                    && !proxy.toString().isBlank(),
                    "identity methods");
            System.out.println(
                    "Proxy equals/hashCode/toString handled: true");

            require(!JMX.isMXBeanInterface(PlainView.class),
                    "Plain should fail auto-detection");
            PlainView plain = JMX.newMXBeanProxy(
                    server, name, PlainView.class);
            require("active".equals(plain.getMode()),
                    "plain compatible view failed");
            System.out.println(
                    "Compatible no-suffix proxy view works: true");

            boolean invalidRejected = false;
            try {
                JMX.newMXBeanProxy(
                        server, name, InvalidMXBean.class);
            } catch (IllegalArgumentException expected) {
                invalidRejected = true;
            }
            require(invalidRejected, "Invalid OpenType accepted");
            System.out.println(
                    "Unmappable MXBean interface rejected: true");

            MetricsMXBean notifying = JMX.newMXBeanProxy(
                    server, name, MetricsMXBean.class, true);
            require(notifying instanceof NotificationEmitter,
                    "not emitter");

            NotificationEmitter emitter =
                    (NotificationEmitter) notifying;
            AtomicInteger received = new AtomicInteger();
            NotificationListener listener = (n, handback) -> {
                if ("demo.metrics.reset".equals(n.getType())) {
                    received.incrementAndGet();
                }
            };
            emitter.addNotificationListener(
                    listener, null, null);
            try {
                notifying.reset();
                require(received.get() == 1,
                        "notification missing");
                require(proxy.getCounts().get("accepted") == 0,
                        "reset not applied");
            } finally {
                emitter.removeNotificationListener(listener);
            }
            notifying.reset();
            require(received.get() == 1,
                    "listener not removed");
            System.out.println(
                    "Notifications received and removed: true");
            System.out.println(
                    "Reset operation changed backing state: true");

            ObjectName missing =
                    new ObjectName("demo.metrics:type=Missing");
            MetricsMXBean lazy = JMX.newMXBeanProxy(
                    server, missing, MetricsMXBean.class);
            require(lazy != null && !server.isRegistered(missing),
                    "proxy construction validated existence");
            System.out.println(
                    "Proxy creation does not require registered target: true");

            boolean failed = false;
            try {
                lazy.getMode();
            } catch (RuntimeException expected) {
                failed = true;
            }
            require(failed,
                    "missing target call unexpectedly succeeded");
            System.out.println(
                    "Missing target fails at method invocation: true");
        } finally {
            if (server.isRegistered(name)) {
                server.unregisterMBean(name);
            }
            MBeanServerFactory.releaseMBeanServer(server);
        }
        System.out.println("Local MBeanServer cleaned: true");
        System.out.println(
                "No remote JMX connector created: true");
    }
}
~~~

### 11.3. Biên dịch và chạy

Lưu file đúng tên `MxBeanProxyDemo.java`:

~~~sh
javac --release 17 MxBeanProxyDemo.java
java MxBeanProxyDemo
~~~

Không có dependencies ngoài JDK. Do dùng module `java.management` thuộc hệ thống modules chuẩn, không cần flags đặc biệt với cấu hình Java 17 thông thường.

**Đầu ra chính xác đã kiểm thử trên JDK24 — 16 dòng:**

~~~text
Registered MXBean descriptor: true
Typed dynamic proxy handler: true
Getter and setter forwarded: true
Operations and List round-trip: true
List raw String[] mapped to List: true
Map raw TabularData mapped to Map: true
MemoryUsage raw CompositeData mapped: true
Proxy equals/hashCode/toString handled: true
Compatible no-suffix proxy view works: true
Unmappable MXBean interface rejected: true
Notifications received and removed: true
Reset operation changed backing state: true
Proxy creation does not require registered target: true
Missing target fails at method invocation: true
Local MBeanServer cleaned: true
No remote JMX connector created: true
~~~

### 11.4. Kết quả quan trọng nhất

**Proxy là JDK dynamic proxy:** `Proxy.isProxyClass` và `MBeanServerInvocationHandler.isMXBean` đều xác nhận. Điều này giải thích vì sao method calls chuyển sang `MBeanServerConnection` chứ không trực tiếp gọi instance backing từ phía client.

**Getter/setter/operation:** `proxy.setMode("active")` cập nhật state thực, đọc qua MBeanServer cũng thấy `active`; `add(2,5)` trả 7, `reverse([a,b,c])` trả `[c,b,a]`.

**OpenData mapping:** Raw MBeanServer returns `String[]`, `TabularData` và `CompositeData` cho các getter đã nêu; proxy tái tạo `List`, `Map` và `MemoryUsage`.

**Plain interface nuance:** Interface `PlainView` không đủ điều kiện auto-recognition, nhưng proxy dùng nó để gọi `getMode()` vẫn hoạt động với MBean đã đăng ký; điều này không cấp quyền xuất một MBean mới và không phải lời khuyên thay đổi public contract.

**Notification:** Listener nhận reset event một lần; khi removed, lần reset kế tiếp không tăng counter. Trong local test, NotificationBroadcasterSupport thực thi listener trực tiếp; remote transport có thể khác timing và delivery.

**Proxy được tạo trước target:** `lazy` object tồn tại nhưng `lazy.getMode()` thất bại; proxy object non-null không chứng minh target healthy.

**Cleanup:** MBeanServer tạo riêng trong process test, unregister rồi release. Không mở JMXConnectorServer, port hoặc kết nối remote.

### 11.5. Giới hạn của bản demo

- Không benchmark latency hoặc throughput của MXBean proxies.
- Không gọi remote JMX server, không cần credential/JMX service URL.
- Không thử JMX notifications qua mạng, reconnect, serialization cross-version.
- Chưa xây distributed authorization policy cho operations.
- Không thử schema evolution hoặc certificate/TLS handshake.
- Không phơi state JVM thật ngoài dữ liệu minh họa; `MemoryUsage` là object được tạo bằng giá trị cố định.
- Chương trình chỉ dùng port-less local MBeanServer; điều này **không đồng nghĩa** rằng tất cả ứng dụng production có platform MBeanServer đều mặc định an toàn nếu remote management được bật.

## 12. Ví dụ #2: proxy cho platform MXBeans sẵn có trong JVM

JDK cũng cung cấp các MXBeans quản lý JVM như `RuntimeMXBean`, `MemoryMXBean`, `ThreadMXBean`. Bạn có thể dùng `ManagementFactory` để lấy platform MBeanServer và tạo typed proxies mà không cần tự viết implementation.

### 12.1. Mục tiêu

File `PlatformMxBeanProxyDemo.java`:

- Tạo `MBeanServerConnection` từ `ManagementFactory.getPlatformMBeanServer()`.
- Tạo `RuntimeMXBean` proxy với `ManagementFactory.RUNTIME_MXBEAN_NAME`.
- Đọc VM name, startTime và uptime; không in data nhạy cảm.
- Kiểm raw `InputArguments` trả `String[]`, còn proxy trả `List<String>`.
- Tạo `MemoryMXBean` proxy với `ManagementFactory.MEMORY_MXBEAN_NAME`.
- Kiểm raw heap memory là `CompositeData`, typed proxy là `MemoryUsage`.
- Xác nhận ObjectName từ platform MXBean trùng tên được `ManagementFactory` công bố.
- Không mở JMX network connector; chỉ đọc platform registry trong JVM.

Đừng in `RuntimeMXBean.getInputArguments()` trực tiếp vào public logs: JVM startup arguments có thể chứa file paths, system properties hoặc cấu hình nhạy cảm. Ví dụ chỉ kiểm đúng kiểu.

### 12.2. Source `PlatformMxBeanProxyDemo.java`

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import java.lang.management.RuntimeMXBean;
import java.util.List;
import javax.management.JMX;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;

public final class PlatformMxBeanProxyDemo {
    static void require(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws Exception {
        MBeanServerConnection server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName runtimeName =
                new ObjectName(ManagementFactory.RUNTIME_MXBEAN_NAME);

        RuntimeMXBean runtime = JMX.newMXBeanProxy(
                server, runtimeName, RuntimeMXBean.class);

        require(server.isRegistered(runtimeName),
                "RuntimeMXBean missing");
        require(!runtime.getVmName().isBlank(),
                "Runtime VM name");
        require(runtime.getStartTime() > 0
                && runtime.getUptime() >= 0,
                "Runtime clocks invalid");
        System.out.println(
                "Platform RuntimeMXBean proxy reads VM data: true");

        Object rawArgs = server.getAttribute(
                runtimeName, "InputArguments");
        require(rawArgs instanceof String[],
                "InputArguments raw OpenType");
        List<String> typedArgs = runtime.getInputArguments();
        require(typedArgs != null,
                "typed List missing");
        System.out.println(
                "RuntimeMXBean String[] to List conversion: true");

        MemoryMXBean memory = JMX.newMXBeanProxy(
                server,
                new ObjectName(
                        ManagementFactory.MEMORY_MXBEAN_NAME),
                MemoryMXBean.class);

        MemoryUsage heap = memory.getHeapMemoryUsage();
        require(heap.getUsed() >= 0,
                "used heap negative");

        Object rawHeap = server.getAttribute(
                new ObjectName(
                        ManagementFactory.MEMORY_MXBEAN_NAME),
                "HeapMemoryUsage");
        require(rawHeap instanceof CompositeData,
                "raw heap OpenType");
        System.out.println(
                "MemoryMXBean CompositeData to MemoryUsage: true");

        require(runtimeName.equals(
                ManagementFactory.getRuntimeMXBean()
                        .getObjectName()),
                "Platform ObjectName mismatch");
        System.out.println(
                "Platform RuntimeMXBean ObjectName matches: true");

        System.out.println(
                "No connector or network access required: true");
    }
}
~~~

### 12.3. Biên dịch và output

~~~sh
javac --release 17 PlatformMxBeanProxyDemo.java
java PlatformMxBeanProxyDemo
~~~

**Stdout chính xác đã chạy trên JDK24 — 5 dòng:**

~~~text
Platform RuntimeMXBean proxy reads VM data: true
RuntimeMXBean String[] to List conversion: true
MemoryMXBean CompositeData to MemoryUsage: true
Platform RuntimeMXBean ObjectName matches: true
No connector or network access required: true
~~~

Ở đây dữ liệu VM đang chạy biến đổi theo OS/JVM, nên ví dụ không in start time, uptime, heap bytes hoặc startup arguments thành các giá trị cố định. Nó chỉ assert các thuộc tính API mang tính ổn định.

### 12.4. Có API platform MXBean chuyên dụng khác

Với các MXBeans chuẩn JDK, `ManagementFactory` có những factory methods dành riêng:

~~~java
RuntimeMXBean runtime =
        ManagementFactory.getRuntimeMXBean();

MemoryMXBean memory =
        ManagementFactory.getMemoryMXBean();
~~~

Đây là cách lấy platform MXBean **trực tiếp trong cùng JVM**. Nếu bạn cần typed proxy trên một `MBeanServerConnection` (đặc biệt remote), có thể dùng `ManagementFactory.newPlatformMXBeanProxy(...)` hoặc những overload `getPlatformMXBean(connection, interface)` tùy loại/điều kiện hỗ trợ. `JMX.newMXBeanProxy` là giải pháp tổng quát cho MXBean interfaces, không chỉ platform MXBeans.

### 12.5. Local platform MBeanServer không phải phép thử từ xa

`ManagementFactory.getPlatformMBeanServer()` trả registry trong JVM hiện hành. Nó không mở RMI/TCP connector hoặc cấu hình TLS. Để kiểm remote MXBeans của **JVM khác**, cần có một `MBeanServerConnection` từ JMX connector được xác thực/bảo vệ; `ObjectName` vẫn là tên MBean trên server mục tiêu, không phải URL kết nối.

## 13. Từ local sang remote JMX: nguyên tắc cấu hình

Ở phía remote, bạn có thể dùng connector được tổ chức vận hành cung cấp:

~~~java
JMXServiceURL approvedUrl = /* trusted configuration */;
Map<String, ?> environment = /* secure credentials and TLS options */;

try (JMXConnector connector =
        JMXConnectorFactory.connect(approvedUrl, environment)) {
    MBeanServerConnection connection =
            connector.getMBeanServerConnection();

    ObjectName name =
            new ObjectName("demo.metrics:type=Service,name=Main");

    MetricsMXBean proxy = JMX.newMXBeanProxy(
            connection, name, MetricsMXBean.class);

    String mode = proxy.getMode();
}
~~~

Đây là **snippet kiến trúc**, không phải file chạy độc lập: `approvedUrl`, `environment` và `MetricsMXBean` cần do hệ thống cung cấp/kiểm soát. Cần imports `javax.management.remote.JMXServiceURL`, `JMXConnector`, `JMXConnectorFactory` và `javax.management.*`, `java.util.Map`. Đoạn này **không phải hướng dẫn bật một JMX port không bảo mật**.

### 13.1. Những điểm bắt buộc với remote connector

- **URL từ trusted config**, không dùng arbitrary JMX URL do request ngoài cung cấp.
- **Authentication** cho quản trị; credentials quản lý bằng secret manager.
- **TLS** và xác minh danh tính endpoint, không tắt certificate/hostname validation.
- **Authorization** theo ObjectName/attribute/operation; không cho reader gọi destructive operations nếu không có quyền.
- Network ACL/firewall, không phơi remote JMX port công khai.
- Timeouts, rate limits và network error handling theo connector/provider.
- `try-with-resources` hoặc `finally` để đóng `JMXConnector`; typed proxy **không tự đóng** connector.
- Nếu dùng notifications, remove listener và cleanup ngay cả khi operation thất bại.
- Không log password, raw remote exceptions chứa secret data, hoặc toàn bộ sensitive MXBean attributes.

### 13.2. Proxy lifecycle gắn với connection

Một proxy được tạo từ `connection`. Nếu connector bị đóng:

- Proxy Java object có thể vẫn tồn tại.
- Những method calls sau đó có thể fail vì underlying connection không còn hoạt động.
- Không mong proxy tự reconnect.
- Khi reconnect, lấy connection mới và thường tạo **proxy mới** với đúng ObjectName/interface.

Không cache proxy giữa các deployment/JVM khác nhau chỉ vì ObjectName trùng. Gắn cache key với target identity và connection lifecycle.

### 13.3. Không coi JMX là một public REST API

JMX dành cho management/monitoring. Một remote connector mở ra quyền đọc/điều khiển state JVM; đôi khi có thông tin rất nhạy cảm. Nếu cần expose metrics tới người dùng/third-party, nên có một service/exporter với allowlist và validation, thay vì cấp quyền remote JMX rộng rãi.

## 14. Security: typed proxy không thêm authorization

Những thuộc tính có thể chứa dữ liệu nhạy cảm:

- JVM input arguments / system properties.
- Tên host, đường dẫn file, thread names và stack traces.
- Heap/memory usage và tên pools; một số runtime details.
- Trạng thái cache nội bộ/feature flags/connection pools.
- Các operations như `reset`, `clear` hoặc thay logging level.

Dù gọi qua typed interface, một getter vẫn truy cập dữ liệu thật và một operation có thể tác động production.

**Policy đề xuất:**

1. Cấp quyền **tối thiểu** cho connector/service account.
2. Cho phép chỉ những ObjectNames/attributes/operations cần thiết.
3. Tách tài khoản read-only monitoring khỏi tài khoản vận hành có quyền thay state.
4. Không để mỗi HTTP request tự chọn ObjectName rồi dùng privileged JMX connection.
5. Thêm audit log cho operations có side effect, nhưng mask thông tin nhạy cảm.
6. Không chuyển trực tiếp JMX exceptions chứa thông tin nội bộ tới API clients.
7. Đánh giá input validation ở server-side MXBean, ngay cả khi client dùng typed proxy.
8. Với remote access, ràng buộc TLS/identity/credentials và giới hạn network.
9. Tôn trọng user data privacy khi export thread names, args hoặc cấu hình JVM.
10. Không để một MXBean getter thực hiện tính toán nặng gây DoS trên monitoring path.

### 14.1. Một interface Java có thể đẹp nhưng vẫn xuất quá nhiều quyền

~~~java
public interface MaintenanceMXBean {
    boolean isHealthy();
    void deleteAllCachedEntries();
}
~~~

Đây là snippet **minh họa rủi ro**. Nếu cùng một remote principal được gọi cả hai methods, việc bạn gọi `proxy.isHealthy()` từ dashboard **không ngăn** principal đó gọi `proxy.deleteAllCachedEntries()`. Security boundary phải nằm tại server/connector authorization và thiết kế management contract.

### 14.2. Notification content cũng cần kiểm soát

JMX `Notification` có `message`, `userData`, `source`, timestamp, sequenceNumber. Nếu server đặt bí mật vào `userData`, subscribers có quyền có thể đọc được. Thiết kế notification payload tối thiểu và không coi userData là channel truyền secret.

## 15. So sánh ba kiểu proxy JMX dễ nhầm

| API | Khi dùng | Chuyển OpenTypes tự động? |
| --- | --- | --- |
| `JMX.newMXBeanProxy(conn,name,MXInterface.class)` | MXBean tự viết hoặc platform MXBean với đúng interface | **Có**, theo MXBean mapping |
| `JMX.newMBeanProxy(conn,name,StandardInterface.class)` | Standard MBean | **Không theo MXBean mapping** |
| `ManagementFactory.newPlatformMXBeanProxy(conn,name,PlatformInterface.class)` | Platform MXBeans chuẩn JDK trên connection | **Có**, theo platform MXBean contract |

Đừng mặc định `newMBeanProxy` và `newMXBeanProxy` luôn hoán đổi được chỉ vì getter trả `String`. Sự khác biệt thấy rõ với `List`, `Map`, custom composite types hoặc MXBean references.

### 15.1. Khi nào không dùng proxy?

Dùng `MBeanServerConnection.getMBeanInfo/getAttribute/invoke` trực tiếp khi:

- Bạn xây công cụ JMX generic không có compile-time interface class.
- Bạn muốn khám phá MBeans động theo descriptor/OpenType.
- Version của interface server/client không đồng bộ, cần xử lý schema runtime.
- Bạn muốn export OpenData thành JSON/metrics theo controlled mapping.
- Bạn cần thực hiện query/aggregation hoặc kiểm toàn bộ attributes trước khi gọi.

Proxy phù hợp khi **contract đã biết và ổn định**, không phải thay thế cho mọi JMX discovery tooling.

## 16. Test matrix cho MXBean proxy

| Tình huống | Kỳ vọng |
| --- | --- |
| Interface hợp lệ + registered MXBean | Tạo proxy, đọc getter |
| Interface thiếu suffix nhưng phương thức mappable tương thích | Proxy có thể tạo/gọi theo kiểm thử, không thay auto-recognition |
| Interface có `Object` return không mappable | `IllegalArgumentException` lúc tạo proxy |
| Đúng ObjectName nhưng server đã unregister | Gọi method fail |
| Proxy được tạo với ObjectName không tồn tại | Có thể tạo, invocation fail |
| Getter read-only | Đọc được qua proxy |
| Setter writable | State server cập nhật |
| Setter bị cấm/bad value | Propagate lỗi, không giả thành công |
| Operation có primitive args | `add(2,5)==7` |
| Operation có List args/result | `List<String> ↔ String[]` |
| Getter trả `List<String>` | Raw `String[]`, typed List |
| Getter trả `Map<String,Integer>` | Raw `TabularData`, typed Map |
| Getter trả `MemoryUsage` | Raw `CompositeData`, typed MemoryUsage |
| Proxy handler inspection | `MBeanServerInvocationHandler.isMXBean()==true` |
| Hai proxies cùng connection/name/interface | `equals/hashCode` phù hợp |
| `toString()` trên proxy | Không dùng làm server health |
| `notificationEmitter=false` | Không yêu cầu support emitter |
| `notificationEmitter=true` với broadcaster | Add/remove listener hoạt động |
| `notificationEmitter=true` với target không hỗ trợ | Subscribe có thể fail theo JMX |
| Listener removal | Không nhận event sau khi tháo |
| JMX remote connection closed | Proxy calls fail, không tự reconnect |
| Malformed ObjectName | Bắt lỗi cấu hình |
| Missing attribute/operation | Handle runtime/checked cause chain |
| MXBean type schema change | Compatibility/integration test fail rõ ràng |
| Remote authorization denied | Không fallback privileged hoặc trust-all |
| Network timeout | Bounded retry/backoff/circuit breaker |
| JMX platform proxy | Runtime/Memory MXBean hoạt động cục bộ |
| Java17 compatibility | `javac --release 17` cả hai chương trình |
| Cleanup | Unregister/release local server, close remote connector |
| Sensitive args | Không in JVM args vào logs |
| No remote connector in unit demo | Không mở port/test network |

### 16.1. Test concurrency

Nếu nhiều threads gọi `proxy.setMode` và `getMode` cùng lúc:

- Bản thân proxy không đảm bảo transaction hoặc global ordering.
- MXBean implementation phải bảo đảm thread-safety cho state được chia sẻ.
- Remote calls có latency và có thể được xử lý xen kẽ.
- Không khẳng định getter ngay sau setter từ **thread khác** sẽ luôn thấy state mong muốn nếu implementation không đồng bộ đúng.

Trong demo, `Metrics.getMode/setMode` được `synchronized` để bảo vệ state; `getCounts/reset` cũng đồng bộ. Đây là lựa chọn của implementation demo, **không phải tính năng tự thêm của JMX.newMXBeanProxy**.

### 16.2. Test remote behavior

Trên môi trường được phép, tạo JMX connector với TLS/auth, test:

- Credential đúng/sai.
- Allowed ObjectName và disallowed ObjectName.
- Read-only vs privileged operations.
- Disconnect trong khi getter chạy.
- Reconnect và proxy mới.
- Notification subscription removal.
- Unregister/re-register same ObjectName.
- MXBean interface version mismatch.
- Timeout/slow provider và loại lỗi mà client nhận.

Không kiểm thử bằng cách mở public JMX port hoặc dùng credentials thật trong source code/CI logs.

## 17. Troubleshooting theo triệu chứng

### 17.1. `JMX.newMXBeanProxy` tạo được nhưng `getMode()` lỗi

Kiểm connection, ObjectName, target registered state, MBeanInfo attributes, MXBean descriptor, quyền truy cập và server-side exception. Một proxy có thể tồn tại mà target không tồn tại.

### 17.2. Nhận `ClassCastException` hoặc lỗi mapping

So Java interface return/argument types với MBeanInfo OpenTypes thực tế. Nếu server trả raw `CompositeData` nhưng client tưởng `String`, interface contract đã lệch. Không cast `CompositeData` thẳng thành một Java domain object khi không có conversion.

### 17.3. `List<String>` bị lộ là `String[]`

Nếu bạn gọi trực tiếp `getAttribute`, đó là **đúng** raw OpenType mapping. Dùng `JMX.newMXBeanProxy` nếu muốn khai báo và nhận kiểu `List<String>`.

### 17.4. `Map<K,V>` đọc thành TabularData

Cũng là OpenType mapping. Nếu làm công cụ generic, đọc `TabularData` theo schema; nếu là typed client contract, dùng MXBean proxy.

### 17.5. Không nhận được notifications

Kiểm MBean thực sự hỗ trợ NotificationEmitter, type/filter, đăng ký listener trước sự kiện, `notificationEmitter=true`, thời gian sống connector và server-side `sendNotification`.

### 17.6. Notification nhận quá nhiều lần

Có thể listener được đăng ký trùng hoặc reconnect tạo subscriptions mới mà không gỡ cái cũ. Quản lý subscription state, idempotent re-registration và cleanup trong `finally`.

### 17.7. `equals` của proxies trả false

Kiểm cùng `MBeanServerConnection` instance, cùng ObjectName, cùng interfaceClass/proxy class. Một connection mới đến cùng remote JVM có thể khiến equality khác; không coi equals là phép so underlying MBean state.

### 17.8. RuntimeMXBean proxy không có một thuộc tính mong đợi

Kiểm JDK version, ObjectName, platform MXBean interface, server version và metadata. Không giả định mọi property của platform management interface được phép truy cập qua mọi connector hoặc mọi security context.

### 17.9. Remote client không đóng hoặc JVM chưa thoát

Nếu bạn tạo `JMXConnector` hoặc listeners, hãy đóng/unsubscribe. Chương trình demo sử dụng local server tạm và release trong finally, không tạo socket. Remote connectors có threads/resources riêng.

### 17.10. `UndeclaredThrowableException`

Dynamic proxy có thể bọc một checked exception từ JMX/remote call vì interface getter không khai báo nó. Kiểm `getUndeclaredThrowable()` hoặc `getCause()`, phân loại dựa trên root cause và giữ context của failing ObjectName/method ở logs an toàn.

## 18. Câu hỏi tự kiểm tra

**1. `JMX.newMXBeanProxy` trả về object loại gì?**

Trả về typed Java dynamic proxy, thường do `java.lang.reflect.Proxy` tạo với `MBeanServerInvocationHandler`.

**2. Proxy có trực tiếp chứa implementation MXBean không?**

Không. Nó giữ connection, ObjectName và interface; lời gọi được forward tới MBeanServer.

**3. Có phải tạo JMX remote connector mới dùng được proxy không?**

Không. Local `MBeanServer` cũng là `MBeanServerConnection`; hai demo chạy không cần mạng.

**4. Proxy creation thành công có chứng minh ObjectName đang đăng ký?**

Không. Có thể tạo proxy cho ObjectName không tồn tại; call sau đó mới thất bại.

**5. Vì sao phải dùng `ObjectName` chính xác?**

Nó xác định instance cụ thể trong một MBean server. Cùng interface có thể được nhiều objects export.

**6. `proxy.getMode()` ánh xạ đến JMX API nào về nguyên tắc?**

Thường là đọc attribute `"Mode"` bằng `MBeanServerConnection.getAttribute`.

**7. `proxy.setMode(...)` có bảo đảm quyền sửa state không?**

Không. Server/connector authorization và implementation validation quyết định được phép hay không.

**8. `List<String>` ở raw JMX thường được nhìn dưới dạng gì?**

`String[]` theo MXBean OpenType mapping; proxy tái tạo `List<String>` cho typed client.

**9. `Map<String,Integer>` raw dùng kiểu nào?**

`TabularData`; typed MXBean proxy chuyển lại Map khi mapping hợp lệ.

**10. `MemoryUsage` raw thường là gì?**

`CompositeData`; proxy có thể chuyển thành `MemoryUsage`.

**11. Dùng `JMX.newMBeanProxy` thay newMXBeanProxy có luôn đúng không?**

Không. Standard MBean proxy không áp MXBean OpenType conversions theo cùng cách.

**12. Khi nào `notificationEmitter=true` có tác dụng?**

Khi target hỗ trợ JMX notifications và bạn muốn proxy triển khai `NotificationEmitter` để add/remove listeners.

**13. Flag `true` có tạo notification source không?**

Không. Server MBean phải thực sự hỗ trợ và phát notifications.

**14. Khi listener không còn cần, phải làm gì?**

Gỡ bằng `removeNotificationListener`, thường trong `finally`, và đóng remote connector khi xong.

**15. Có nên cache proxy đã tạo qua nhiều lần reconnect không?**

Không. Proxy gắn với connection cũ; tạo proxy mới với connection mới và kiểm lại target.

**16. `equals` hai proxies có kiểm business data equality không?**

Không. Nó so client-side proxy identity dựa trên connection/ObjectName/interface theo JDK handler.

**17. Vì sao một interface không có suffix MXBean vẫn có thể dùng để tạo proxy?**

`isMXBeanInterface` là quy tắc auto-export nhận diện, còn proxy constructor kiểm interface/mapping theo cách khác. Đừng coi điều này thay việc dùng contract chuẩn.

**18. Nếu interface có `Object getUnsupported()` thì sao?**

Không có mapping tổng quát cho tùy ý Java Object; demo xác nhận tạo proxy bị từ chối.

**19. Một RuntimeMXBean proxy có cần mở JMX network connector?**

Không nếu sử dụng platform MBeanServer của JVM hiện tại; remote JVM mới cần kết nối tương ứng.

**20. `getInputArguments()` của RuntimeMXBean có nên log thẳng không?**

Không. Input args có thể chứa sensitive config hoặc paths. Chỉ thu thập những fields được phê duyệt.

**21. Có thể dùng MXBean proxy làm một REST endpoint mà không thêm security checks không?**

Không. Management operations có thể thay đổi state và lộ dữ liệu; cần authentication/authorization, allowlist và privacy controls.

**22. Nếu JMX invocation mất mạng ngay sau khi reset, có retry ngay không?**

Không tự động. Operation có thể đã chạy server-side, nên cần kiểm trạng thái/idempotency để tránh side effects lặp.

**23. Vì sao cần kiểm MBeanInfo descriptor?**

Để biết instance thực tế được đăng ký với MXBean semantics; interface name một mình không xác nhận.

**24. Bài tự kiểm thử hoàn chỉnh xác minh gì?**

Typed method forwarding, OpenType round-trip, notification listener lifecycle, dynamic proxy identity, invalid mapping, missing target behavior, platform MXBeans và cleanup — **không** xác nhận remote TLS/auth vì không mở kết nối ngoài.

## 19. Checklist dùng thực tế

- [ ] Interface quản trị public, OpenType-mappable, được quản lý phiên bản.
- [ ] MBean implementation đăng ký đúng `ObjectName` và MXBean descriptor.
- [ ] Caller dùng đúng `MBeanServerConnection` và quyền truy cập tối thiểu.
- [ ] Proxy tạo bằng `JMX.newMXBeanProxy(..., Interface.class)`.
- [ ] Method calls được bao bằng timeout/error policy khi remote.
- [ ] Getter, setter, operation và OpenType conversions đã có integration tests.
- [ ] Không dùng `proxy != null` làm health check.
- [ ] Không dùng `equals/toString` làm dữ liệu từ server.
- [ ] Không dùng untrusted ObjectName/operation name để invoke quyền cao.
- [ ] NotificationEmitter flag chỉ bật khi target hỗ trợ.
- [ ] Listener được gỡ và connector được đóng theo lifecycle.
- [ ] Không log JVM input arguments, credentials, raw exception sensitive data.
- [ ] Không retry operations có side effects khi chưa xác định kết quả.
- [ ] Có kiểm compatibility sau nâng cấp JDK/provider hoặc MXBean interface.
- [ ] Remote JMX được bảo vệ bằng TLS, identity, ACL, auth và authorization.

**Ghi nhớ:** `JMX.newMXBeanProxy(connection, objectName, MXBeanInterface.class)` tạo typed **client proxy** forward getter/setter/operations đến MBeanServer và chuyển đổi dữ liệu giữa Java types và JMX Open Types. `List<String>` ↔ `String[]`, `Map` ↔ `TabularData`, `MemoryUsage` ↔ `CompositeData` là những ví dụ quan trọng. Overload `notificationEmitter=true` thêm khả năng subscribe notifications nhưng không làm target tự phát event. **Tạo proxy không xác nhận target tồn tại hoặc có quyền truy cập**; remote JMX vẫn cần authentication, authorization, TLS, timeout và resource cleanup.

### Tài liệu chính thức còn hiệu lực

- [Oracle Java SE 26 — JMX](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/JMX.html): `newMXBeanProxy` overloads, type mapping, notificationEmitter, `newMBeanProxy`.
- [Oracle Java SE 26 — MBeanServerInvocationHandler](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/MBeanServerInvocationHandler.html): dynamic proxy, forwarding, equals/hashCode/toString, MXBean conversions.
- [Oracle Java SE 26 — MXBean annotation và mapping specification](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/MXBean.html): MXBean types, OpenData mapping, interface conventions.
- [Oracle Java SE 26 — MBeanServerConnection](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/MBeanServerConnection.html): `getAttribute`, `setAttribute`, `invoke`, `isRegistered`, notifications và exceptions.
- [Oracle Java SE 26 — NotificationEmitter](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/NotificationEmitter.html): notification listener API.
- [Oracle Java SE 26 — NotificationBroadcasterSupport](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/NotificationBroadcasterSupport.html): emitter helper và notification lifecycle.
- [Oracle Java SE 26 — ManagementFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ManagementFactory.html): platform MXBeans và typed proxy access.
- [Oracle Java SE 26 — MemoryUsage](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/MemoryUsage.html): composite mapping cho JVM memory metrics.
- [Oracle Java SE 26 — OpenType](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/openmbean/OpenType.html): Java/OpenData representation.
- [Oracle Java SE 26 — JMXConnector](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/remote/JMXConnector.html): remote connection lifecycle/close.
- [Oracle Java SE 17 — JMX](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/JMX.html): đối chiếu tương thích Java 17.
