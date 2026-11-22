# 7.1 MBeanServer, ObjectName, attribute, operation và notification

Khi điều tra một tiến trình Java đang chạy, đôi khi chỉ biết “JVM còn sống” vẫn chưa đủ. Người vận hành muốn hỏi **heap đang dùng bao nhiêu**, **thread count hiện tại là gì**, **queue nội bộ có đang nghẽn**, hoặc muốn nhận một tín hiệu khi một ngưỡng quan trọng bị vượt. **Java Management Extensions (JMX)** cung cấp mô hình quản trị cho các câu hỏi đó: các đối tượng quản lý (MBean) được đăng ký vào **MBeanServer** bằng **ObjectName**; người quan sát có thể đọc/ghi **attribute**, gọi **operation** và đăng ký nghe **notification** nếu đối tượng hỗ trợ.

JMX không phải một công cụ đo mọi thứ tự động. Một MBean có thể chỉ chứa số tích lũy, một attribute có thể đắt để tính, một operation có thể thay đổi trạng thái sản xuất và một notification không phải hàng đợi sự kiện bền vững. Hiểu đúng năm khái niệm trên giúp đọc số liệu runtime mà không vô tình gây tác động lên ứng dụng hoặc suy diễn quá mức.

Bài này tập trung vào **lớp mô hình JMX**: cách quản lý một MBean, cách đặt tên và tìm kiếm, cách phân biệt property/operation/event, đọc metadata, đăng ký notification, xử lý lỗi và giới hạn truy cập. Ví dụ Java 17+ chạy hoàn chỉnh trên một JVM, không cần thư viện ngoài; nó dựng một MBean mô phỏng độ sâu hàng đợi, kiểm chứng attribute, operation và notification bằng stdout ổn định.

## 1. Bản đồ kiến trúc JMX

Một sơ đồ tư duy:

```text
  Ứng dụng Java / JVM
  +------------------------------------------------------------+
  |  MBean: QueueMetrics            Platform MXBeans           |
  |  - QueueDepth [attribute]       - MemoryMXBean              |
  |  - Status [attribute]           - ThreadMXBean              |
  |  - reset() [operation]          - GarbageCollectorMXBean   |
  |  - threshold [notification]     - ...                       |
  |           \                         /                       |
  |            \                       /                        |
  |             MBeanServer (registry + dispatch)               |
  |                       |                                     |
  +-----------------------|-------------------------------------+
                          |
                MBeanServerConnection
                  /                \
           local Java client       JMX connector (nếu được bật
                                   và phân quyền an toàn)
                          |
               JConsole / JMC / giám sát
```

Các thành phần có vai trò khác nhau:

| Thành phần | Định nghĩa ngắn | Câu hỏi trả lời |
| --- | --- | --- |
| **MBean** | Java object cung cấp giao diện quản lý hợp lệ theo JMX | Đối tượng nào đang được quan sát/điều khiển? |
| **MBeanServer** | Registry và cổng truy cập các MBean theo tên | MBean nào đã đăng ký, đọc/gọi chúng thế nào? |
| **ObjectName** | Định danh có cấu trúc của MBean **trong một MBeanServer** | Đối tượng cần hỏi có tên gì? |
| **Attribute** | Giá trị có thể đọc và/hoặc ghi theo contract của MBean | Trạng thái hiện tại hoặc cấu hình là gì? |
| **Operation** | Hành động/phương thức management được công bố | Có thể yêu cầu đối tượng làm gì? |
| **Notification** | Sự kiện do MBean phát khi được thiết kế để phát | Điều gì vừa xảy ra hoặc ngưỡng nào vừa vượt? |
| **MBeanInfo** | Metadata mô tả attributes, operations, notifications, constructors | Client biết cách tương tác một cách kiểm chứng ra sao? |

**Luồng phổ biến**: lấy `MBeanServer` → xác định `ObjectName` → kiểm tra MBean đã đăng ký và metadata → đọc attribute hoặc gọi operation cần thiết → nếu có support, thêm `NotificationListener` rồi xử lý và tháo listener khi xong.

MBeanServer không nhất thiết tạo một process hoặc thread độc lập. MBean tồn tại **trong JVM**, có thể được đọc cục bộ; remote JMX là một lớp connector và cơ chế bảo mật riêng. Có MBean trong process **không đồng nghĩa cổng JMX remote đang mở**.

## 2. MBeanServer: đăng ký, tìm kiếm và điều phối truy cập

### 2.1 Lấy platform MBeanServer của JVM hiện tại

Trong ứng dụng Java:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
```

Đây là **đoạn API minh họa** cần đặt bên trong method/class. `getPlatformMBeanServer()` trả MBeanServer nền tảng của JVM hiện tại, nơi có các platform management beans và có thể đăng ký MBean ứng dụng. Đối tượng được chia sẻ trong process; không gọi method đó để truy cập PID khác.

`MBeanServer` mở rộng `MBeanServerConnection`: các phương thức đọc/gọi/nhận metadata của hai interface có nhiều điểm chung; `MBeanServer` còn có đăng ký/hủy đăng ký MBean cục bộ. Với remote client, thường thao tác qua `MBeanServerConnection` lấy từ `JMXConnector`, **không có quyền trực tiếp gọi mọi thao tác nội bộ chỉ vì cùng API**.

### 2.2 MBeanServer không tự chứa logic nghiệp vụ

Ví dụ một lớp `QueueMetrics` lưu độ sâu hàng đợi, biết khi nào vượt ngưỡng. MBeanServer **không tự đo độ sâu**, chỉ giúp:

- Gán tên duy nhất cho MBean đã được đăng ký.
- Truy vấn tên/metadata và chuyển lời gọi đọc/ghi attribute đến đối tượng.
- Chuyển `invoke` đến operation được công bố.
- Đăng ký/tháo listener để nhận notification khi MBean phát.
- Ghi nhận hoạt động register/unregister thông qua notification của MBeanServerDelegate.

Nếu MBean trả số sai, collector/time window sai hoặc getter block, MBeanServer không tự sửa semantics. **Chất lượng diagnostic phụ thuộc cả implementation của MBean và phương pháp thu mẫu**.

### 2.3 Các API quản lý thường gặp

| API | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `registerMBean(bean, name)` | Đăng ký một MBean đã tạo | Phải tuân thủ quy tắc MBean; tên đang dùng gây `InstanceAlreadyExistsException` |
| `unregisterMBean(name)` | Hủy đăng ký MBean | Không đồng nghĩa destroy toàn bộ Java object |
| `isRegistered(name)` | Kiểm tra có tên tại một thời điểm | Có race với register/unregister khác |
| `getMBeanCount()` | Số MBean đã đăng ký | Không phải số thread/process/JVM |
| `queryNames(pattern, query)` | Trả tập ObjectName khớp | Tập kết quả là snapshot; không mặc định thứ tự |
| `queryMBeans(pattern, query)` | Trả ObjectInstance tương ứng | Metadata/object class không thay thế attribute value |
| `getMBeanInfo(name)` | Trả mô tả attribute/operation/notification | Không bảo đảm một attribute có thể đọc bởi mọi caller |
| `getAttribute(name, attr)` | Đọc một attribute | Getter có thể tính toán/lock/throw |
| `setAttribute(name, attr)` | Ghi một attribute | Có thể thay đổi trạng thái thực |
| `invoke(name, operation, params, signature)` | Gọi operation | Có thể có tác động đáng kể |
| `addNotificationListener(...)` | Nhận event khi MBean phát | Không hỗ trợ cho mọi MBean |

Một số code mẫu dễ nhầm `createMBean` và `registerMBean`. `createMBean` nhờ MBeanServer khởi tạo và đăng ký theo tên class/loader; `registerMBean` đưa **object đã tạo** vào registry. Với ứng dụng có dependency injection, phương án đăng ký object sẵn có thường dễ quản lý vòng đời hơn. Khi tạo/hủy phải chú ý ownership của MBean để không register trùng sau redeploy.

### 2.4 Có nhiều MBeanServer được không?

JMX cũng có `MBeanServerFactory.createMBeanServer(...)` và `newMBeanServer(...)`. Một process có thể có server riêng ngoài platform server. Vì vậy việc tìm một MBean trong platform server mà không thấy **không đủ** để kết luận process không có MBean ở server khác. Ngược lại, nhiều công cụ chỉ kết nối platform server mặc định. Cần thống nhất nơi đăng ký MBean và endpoint client thực sự truy cập.

Dùng platform server là lựa chọn điển hình cho runtime diagnostics, nhưng việc đăng ký một application MBean không tự cho phép bất kỳ người dùng nào trên mạng gọi nó.

## 3. ObjectName: định danh có domain và key properties

Một `ObjectName` điển hình:

```text
learning.jmx:type=QueueMetrics,name=Orders
  domain   :   key=value, key=value
```

- **Domain** đứng trước dấu `:`, thường là namespace logic của sản phẩm, library hoặc JVM.
- **Key properties** là các cặp `key=value` sau dấu hai chấm, ngăn cách bằng dấu phẩy. Ví dụ `type`, `name`, `service`, `instance`.
- Trong một MBeanServer, tên ObjectName hợp lệ phải xác định một đăng ký duy nhất. Hai MBeans không thể đăng ký đồng thời với **cùng một ObjectName**.
- Java platform MBeans thường có domain `java.lang`, chẳng hạn `java.lang:type=Memory`. Không dùng lại namespace JDK đó cho đối tượng nghiệp vụ tùy tiện.

ObjectName là một **định danh quản lý**, không mặc định là URL, địa chỉ IP, class Java, PID hoặc tên file. Một application có thể có `QueueMetrics` Java class nhưng đăng ký dưới `learning.jmx:type=QueueMetrics,name=Orders`.

### 3.1 Tạo ObjectName bằng Java

```java
import javax.management.ObjectName;

ObjectName name =
        new ObjectName("learning.jmx:type=QueueMetrics,name=Orders");
```

Đây là đoạn minh họa cần đặt trong method với handling `MalformedObjectNameException`; ví dụ Java độc lập đầy đủ ở phần 8 khai báo `throws Exception` cho mục đích học.

Nếu tên đến từ cấu hình/user input hoặc chứa dấu cách, dấu phẩy, dấu bằng, dấu hai chấm, ký tự `*`/`?`, nên dùng **`ObjectName.quote(value)`** cho phần giá trị thay vì nối chuỗi tùy tiện:

```java
String serviceName = "Order API";
ObjectName quoted = new ObjectName(
        "learning.jmx:type=QueueMetrics,name="
        + ObjectName.quote(serviceName));
```

Kết quả biểu diễn name có dấu nháy phù hợp với cú pháp JMX. Không cần tự escape riêng từng ký tự bằng giải pháp ad hoc; dùng các API JMX sẵn có.

### 3.2 ObjectName matching và pattern

`ObjectName` còn được dùng để truy vấn nhiều MBean:

```java
ObjectName pattern =
        new ObjectName("learning.jmx:type=QueueMetrics,*");
var names = server.queryNames(pattern, null);
```

`pattern` khớp các tên trong domain `learning.jmx` có property `type=QueueMetrics` cùng những key properties bổ sung phù hợp. `queryNames` trả một `Set<ObjectName>`, **không có thứ tự được bảo đảm**. Khi cần xuất báo cáo ổn định, sắp xếp tên một cách tường minh.

Ví dụ pattern khác:

| ObjectName | Ý nghĩa minh họa |
| --- | --- |
| `java.lang:type=Memory` | Tên xác định của platform Memory MXBean |
| `java.lang:type=GarbageCollector,*` | Mẫu tìm các garbage collector MBeans |
| `learning.jmx:type=QueueMetrics,name=Orders` | MBean đích xác định |
| `learning.jmx:type=QueueMetrics,*` | Pattern tìm cùng type, bất kể key khác |
| `learning.jmx:*` | Mọi key-property lists trong domain đó |
| `*:type=QueueMetrics,*` | Tìm type tương ứng ở nhiều domains (rộng; cần cẩn thận) |

Phân biệt **tên xác định để `registerMBean`** và **pattern để `queryNames`**. Không đăng ký MBean dưới tên chứa wildcard pattern; thiết kế tên thật cụ thể. Dùng `ObjectName.isPattern()` để phát hiện tên có pattern khi cần validate input.

### 3.3 canonical name, thứ tự key và danh tính

Hai ObjectName có key properties giống nhau nhưng thứ tự chuỗi khác nhau được JMX hiểu như cùng tên về mặt identity:

```text
learning.jmx:type=QueueMetrics,name=Orders
learning.jmx:name=Orders,type=QueueMetrics
```

`getCanonicalName()` đưa ra biểu diễn canonical để so sánh/lưu. **Không so sánh tên bằng phép so chuỗi raw tùy ý** nếu caller có thể thay thứ tự key. Dùng chính `ObjectName.equals` hoặc canonical name.

### 3.4 Thiết kế namespace để tránh trùng và rò rỉ dữ liệu

Quy tắc thực tế:

1. Dùng domain của ứng dụng/tổ chức, tránh ghi đè `java.lang`.
2. Dùng các key ổn định như `type` và `name`, thống nhất quy ước chữ hoa/thường.
3. Không đưa access token, password, email người dùng, customer ID hoặc request ID bí mật vào ObjectName. **Tên MBean có thể hiện trong danh sách query**.
4. Tránh mỗi request tạo một MBean: cardinality quá cao gây phình registry và metrics labels.
5. Trên redeploy/hot reload, hủy đăng ký đúng bean mình sở hữu để tránh `InstanceAlreadyExistsException` hoặc giữ tham chiếu class loader không mong muốn.
6. Mỗi JVM có registry riêng; ObjectName trùng ở **hai JVM khác nhau** là bình thường. Remote monitoring cần thêm JVM instance/host/container identity.

## 4. MBean là gì? Standard MBean, MXBean và DynamicMBean

### 4.1 Standard MBean

Một **Standard MBean** tuân theo quy ước tên interface: class `QueueMetrics` công bố management interface `QueueMetricsMBean`, với getter/setter và các method làm operation.

```java
public interface QueueMetricsMBean {
    int getQueueDepth();
    void setQueueDepth(int newDepth);
    String getStatus();
    void reset();
}
```

Trong ví dụ độc lập, đây là toàn bộ nội dung tệp `QueueMetricsMBean.java`. JMX tự nhận biết:

- `getQueueDepth()` và `setQueueDepth(int)` tạo attribute `QueueDepth` đọc/ghi.
- `getStatus()` tạo attribute `Status` chỉ đọc.
- `reset()` là một **operation**, không phải attribute.
- Những phương thức nội bộ khác của class triển khai **không tự công bố** nếu không nằm trong management interface.

Method boolean dạng `isEnabled()` cũng có thể được nhận diện là getter của attribute `Enabled` theo quy tắc JavaBeans/JMX. Đừng lẫn tên method `getQueueDepth` với tên attribute **`QueueDepth`** khi gọi `getAttribute`.

Standard MBean không phải tự động công bố **mọi** public method của object; contract là interface đáp ứng quy ước và các quy tắc của JMX.

### 4.2 MXBean

**MXBean** là một biến thể cung cấp quy ước ánh xạ kiểu dữ liệu quản lý (open types) để client từ xa có thể hiểu mà không cần cùng các class domain tùy biến. Những platform beans như `MemoryMXBean`, `ThreadMXBean` và `GarbageCollectorMXBean` là ví dụ thường gặp. Trong MBeanServer, các giá trị phức tạp của MXBean có thể được trình bày theo `CompositeData`/`TabularData` khi truy cập qua JMX.

Đọc Java API trong cùng process và đọc qua một JMX connector **không luôn có cùng kiểu object bên ngoài**; không cast bừa tất cả attribute remote thành Java bean gốc. `MBeanInfo` và MXBean type mapping là nguồn để biết dữ liệu nào được công bố.

### 4.3 Dynamic MBean

`DynamicMBean` cho phép một object tự mô tả attributes/operations bằng `getMBeanInfo()` và tự xử lý `getAttribute`/`setAttribute`/`invoke`. Hữu ích khi management contract cần dựng động, nhưng dễ phức tạp và lỗi hơn so Standard MBean với interface rõ ràng.

### 4.4 Chọn mô hình nào?

| Tình huống | Lựa chọn thường hợp lý | Vì sao |
| --- | --- | --- |
| Quản trị một service Java đơn giản | Standard MBean | Interface rõ, dễ test |
| API giám sát cần kiểu dữ liệu portable | MXBean | Open-type mapping phù hợp JMX |
| Contract thay đổi động theo runtime | DynamicMBean | Tự định nghĩa metadata/xử lý |
| Chỉ cần xem heap/thread/GC JVM | Platform MXBeans có sẵn | Không cần xây bean mới |
| Cần histogram latency có labels/cardinality | Metrics framework/exporter có schema thích hợp | JMX alone không tự sinh histogram/rate |
| Cần chuỗi events có lưu trữ, replay | Messaging/event store hoặc logs/JFR | Notification JMX không phải durable event bus |

## 5. Attribute: giá trị có thể đọc và/hoặc thay đổi

### 5.1 Getter và setter tạo attribute

Với management interface ở trên, `QueueDepth` là attribute **read/write**, `Status` là attribute **read-only**. Qua server:

```java
Object value = server.getAttribute(name, "QueueDepth");
server.setAttribute(name, new Attribute("QueueDepth", 5));
Object status = server.getAttribute(name, "Status");
```

Đoạn này minh họa API, giả sử `server` và `name` đã được tạo và MBean đã đăng ký. `getAttribute` trả `Object`: client cần biết kiểu được mô tả bởi metadata. Dữ liệu bất hợp lệ hoặc tên sai có thể gây `AttributeNotFoundException`; lỗi trong getter/setter có thể được bao trong exception của JMX.

**Đọc attribute không luôn miễn phí**: getter có thể đi vào lock, tính toán, gọi API chậm hoặc query hệ thống. Thiết kế MBean tốt nên giữ getter nhẹ, bounded và không vô tình làm network I/O trên request path. Một attribute thay đổi liên tục cũng chỉ là **ảnh chụp** khi gọi, không tự cung cấp lịch sử.

### 5.2 Đọc nhiều attributes: getAttributes

`MBeanServer.getAttributes(name, new String[]{"QueueDepth","Status"})` trả `AttributeList`. Có tình huống một hoặc nhiều field không lấy được; **API có thể bỏ field đó khỏi kết quả**, chứ không bảo đảm danh sách trả về đủ số lượng theo yêu cầu. Cần kiểm tra danh sách nhận và phân biệt các trường missing.

Không lấy số phần tử trả về ít hơn rồi tự gán value theo vị trí của mảng yêu cầu nếu chưa kiểm tra tên từng `Attribute`. Khi cần biết lỗi cụ thể của một trường, dùng `getAttribute` riêng để bắt exception.

### 5.3 Readable, writable và isIs

`MBeanAttributeInfo` (trong `MBeanInfo`) có metadata:

- `isReadable()`: caller về mặt interface có thể đọc; quyền vẫn có thể giới hạn.
- `isWritable()`: có setter/ghi theo contract; **không có nghĩa nên ghi trong production**.
- `isIs()`: attribute dùng dạng boolean `isXxx`.
- `getType()` và `getDescription()`: kiểu, mô tả nếu được định nghĩa.

Không dựa vào việc JConsole vẽ một trường thành textbox để suy ra hành động vô hại. Nếu setter cập nhật queue limit, feature switch hoặc GC configuration, việc ghi là **hành động thay đổi runtime** cần quyền và quy trình.

### 5.4 Thao tác xem khác thao tác thay đổi

| Tác vụ | Ví dụ | Tính chất |
| --- | --- | --- |
| Đọc | `getAttribute(name,"QueueDepth")` | Quan sát; getter vẫn có thể tốn chi phí |
| Ghi | `setAttribute(name,new Attribute("QueueDepth",5))` | Mutating; có thể kích hoạt logic ứng dụng |
| Đọc metadata | `getMBeanInfo(name)` | Kiểm tra khả năng được công bố |
| Truy vấn registry | `queryNames(pattern,null)` | Discover MBeans, không nhất thiết đọc values |
| Gọi operation | `invoke(name,"reset",...)` | Có thể là read-only hoặc mutating, phải xem contract |
| Subscribe | `addNotificationListener(...)` | Đăng ký nhận event, cần tháo đúng vòng đời |

**Attribute không phải luôn là metric counter.** Có attribute là số hiện tại (gauge), có attribute là cấu hình, có attribute là counter tích lũy. Muốn tính rate từ counter phải lấy hai mẫu cùng instance và xử lý reset; không lấy một snapshot làm percentile hay latency history.

## 6. Operation: hành động do MBean công bố

Một method quản lý không theo mẫu getter/setter thường là **operation**. Ví dụ `QueueMetricsMBean.reset()` sẽ đặt queue depth về 0 trong bài thực hành. Qua MBeanServer:

```java
server.invoke(name, "reset", new Object[0], new String[0]);
```

Tham số:

1. `name`: ObjectName của bean đã đăng ký.
2. `"reset"`: tên operation được công bố.
3. `params`: đối số thực, trong trường hợp này mảng rỗng.
4. `signature`: tên các kiểu Java của tham số theo đúng thứ tự; trong trường hợp này mảng rỗng.

Khi operation có tham số `int count`, signature có thể chứa `"int"`, **không phải** `"java.lang.Integer"` nếu management interface khai báo primitive int. Sự khác biệt signature rất quan trọng khi overload. Với remote MXBeans, còn phải xét mapping kiểu dữ liệu và class compatibility.

### 6.1 Không đồng nhất operation với phép đọc

Một số operations chỉ trả thông tin, nhưng số khác có thể:

- Reset counter hoặc clear cache.
- Thay cấu hình runtime, bật/tắt tính năng.
- Bắt đầu/kết thúc một recording hoặc công việc nền.
- Chạy health/diagnostic command có chi phí cao.
- Flush, reload, reconnect, close resource.
- Gây tạm dừng hoặc thay đổi chất lượng dịch vụ.

Do đó, một dashboard/operator cần **liệt kê và phân quyền operation** riêng với read-only attributes. Gọi `invoke` thành công không chứng minh an toàn hay kết quả nghiệp vụ đã hoàn tất nếu operation kích hoạt việc bất đồng bộ.

### 6.2 Xác định operation qua metadata

`MBeanOperationInfo` cho biết tên, mô tả, signature và impact metadata như `INFO`, `ACTION`, `ACTION_INFO`, `UNKNOWN` khi MBean triển khai metadata đó. Thông tin impact là mô tả về intent, **không thay thế đánh giá side effect của code**.

Với Standard MBean, nếu muốn mô tả metadata phong phú có thể dùng `@DescriptorKey`, StandardMBean customizer hoặc các cơ chế mô tả JMX khác; không giả định mặc định mọi method đều có description rõ ràng.

### 6.3 Vì sao signature quan trọng

Hai operations giả định:

```java
void clear();
void clear(String scope);
```

Qua `invoke`, cần phân biệt `clear()` với `clear(java.lang.String)`. Chỉ dùng tên `clear` mà signature sai có thể gây `ReflectionException` hoặc lỗi khi invoke. Đọc `MBeanInfo.getOperations()` để xác nhận tên/parameter types thực tế trước khi gọi, nhất là khi công cụ client hiển thị nhiều overloads.

## 7. Notification: sự kiện, listener và những giới hạn

### 7.1 Notification khác polling một attribute

Polling `getAttribute("QueueDepth")` mỗi 10 giây cho bạn các **mẫu trạng thái**. Nếu queue tăng nhanh qua ngưỡng rồi giảm giữa hai lần poll, bạn có thể không nhìn thấy peak. Một MBean được thiết kế để phát notification có thể chủ động gửi event **khi vượt ngưỡng**.

JMX có các kiểu:

- `Notification`: object chứa `type`, `source`, `sequenceNumber`, `timeStamp`, message và `userData` tùy trường hợp.
- `NotificationListener`: callback `handleNotification(notification,handback)`.
- `NotificationBroadcaster` / `NotificationEmitter`: contract cho MBean phát event.
- `NotificationBroadcasterSupport`: helper triển khai listener registration và `sendNotification(...)`.
- `MBeanNotificationInfo`: metadata cho client biết những notification types bean có thể phát.

**Chỉ vì một MBean có attribute không có nghĩa nó tự phát notification khi attribute đổi.** Code của MBean phải chủ động phát hoặc sử dụng implementation đã hỗ trợ. Ví dụ demo có điều kiện “depth từ dưới 5 lên ít nhất 5”; những lần đổi depth khác không phát event.

### 7.2 Kết nối listener qua MBeanServer

```java
NotificationListener listener = (notification, handback) -> {
    System.out.println(notification.getType());
};
server.addNotificationListener(name, listener, null, null);
```

Ở đây `null` filter nghĩa là không lọc notification trước khi chuyển cho listener; `null` handback là không kèm context. Trong chương trình thực tế có thể dùng `NotificationFilter` để chỉ xử lý type cụ thể, và handback để phân biệt registration.

Sau khi xong:

```java
server.removeNotificationListener(name, listener);
```

Nhớ tháo listener đúng vòng đời. Đăng ký chồng nhiều listener hoặc quên remove có thể gây giữ tham chiếu, callback lặp, lỗi class loader sau redeploy hoặc tăng chi phí dispatch.

### 7.3 Có những notification nào?

Một số MBeans phát notification theo sự kiện runtime cụ thể (ví dụ memory threshold khi được JVM hỗ trợ và được cấu hình). MBeanServer còn có **MBeanServerDelegate**, phát sự kiện registration/unregistration kiểu `MBeanServerNotification`. Nghe các sự kiện registry thông qua ObjectName `JMImplementation:type=MBeanServerDelegate` — không nhầm với event do MBean ứng dụng phát.

Ví dụ:

| Nguồn | Event | Điều cần nhớ |
| --- | --- | --- |
| Custom `QueueMetrics` | `learning.queue.threshold` | Chỉ phát khi logic của bean gọi `sendNotification` |
| Memory MXBean (khi hỗ trợ/cấu hình) | Memory threshold | Phụ thuộc pool/threshold support, không tự phát mọi thay đổi heap |
| MBeanServerDelegate | Register/unregister MBean | Event về registry, không phải GC/queue event |
| GC notification extension (nếu hỗ trợ) | GC completion information | Phụ thuộc implementation, cần hiểu memory/duration semantics |

### 7.4 Thông tin sự kiện không đảm bảo là dữ liệu lịch sử bền vững

Với `NotificationBroadcasterSupport`, **dispatch mặc định là đồng bộ**: gọi `sendNotification` có thể chạy callback trong luồng gọi, trừ khi cấu hình Executor khác hoặc subclass thay đổi hành vi. Listener chậm có thể làm chậm đường phát event; listener tự ghi log/đụng shared lock có thể gây tác động phụ.

Thông báo JMX cũng không phải message queue có đảm bảo lưu trữ và replay. Khi một client kết nối sau sự kiện, không nên mong sẽ nhận các event đã qua. Với remote connector, mất mạng, reconnect, lag, filtering và thời gian sống client có thể ảnh hưởng việc nhận event. Nếu cần **audit toàn vẹn, persistence, ordering liên dịch vụ, dead-letter/replay**, hãy dùng event store/log hoặc hệ thống messaging phù hợp.

`sequenceNumber` có ích để theo dõi thứ tự theo **nguồn phát**, nhưng không phải global sequence cho cả cluster. Cùng sequence ở hai JVM không biểu thị cùng event. Timestamp và source cũng phải gắn với instance/timezone khi phân tích.

### 7.5 Notification và quyền riêng tư

`userData` và `message` có thể chứa chi tiết nội bộ hoặc dữ liệu người dùng nếu developer đặt vào. Không đưa token, password, request body, email/customer ID vào notification phát cho client không kiểm soát. Nên gửi type, severity, alias/ID vô hại và metric cần thiết; bảo vệ remote JMX như các kênh xuất dữ liệu khác.

## 8. Ví dụ Java 17+ hoàn chỉnh: MBeanServer, ObjectName, attribute, operation và notification

Ví dụ gồm **ba tệp trong cùng một thư mục**, dùng JDK 17 trở lên, chỉ cần module tiêu chuẩn `java.management`. Nó không mở network port và không thao tác hệ thống bên ngoài. Dữ liệu hoàn toàn mô phỏng trong bộ nhớ; stdout do code tạo có thứ tự xác định.

### 8.1 Tệp QueueMetricsMBean.java

```java
public interface QueueMetricsMBean {
    int getQueueDepth();
    void setQueueDepth(int newDepth);
    String getStatus();
    void reset();
}
```

Interface public định nghĩa contract Standard MBean; tên **`QueueMetricsMBean`** khớp class triển khai **`QueueMetrics`**. `QueueDepth` sẽ là read/write attribute, `Status` là read-only attribute, `reset` là operation.

### 8.2 Tệp QueueMetrics.java

```java
import javax.management.MBeanNotificationInfo;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class QueueMetrics extends NotificationBroadcasterSupport
        implements QueueMetricsMBean {

    private int queueDepth;
    private long nextSequence;

    @Override
    public synchronized int getQueueDepth() {
        return queueDepth;
    }

    @Override
    public synchronized void setQueueDepth(int newDepth) {
        if (newDepth < 0) {
            throw new IllegalArgumentException("negative depth");
        }
        int previous = queueDepth;
        queueDepth = newDepth;

        if (previous < 5 && newDepth >= 5) {
            Notification event = new Notification(
                    "learning.queue.threshold",
                    this,
                    ++nextSequence,
                    "queue depth crossed threshold");
            sendNotification(event);
        }
    }

    @Override
    public synchronized String getStatus() {
        return queueDepth >= 5 ? "BUSY" : "NORMAL";
    }

    @Override
    public synchronized void reset() {
        setQueueDepth(0);
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        String[] types = {"learning.queue.threshold"};
        return new MBeanNotificationInfo[] {
                new MBeanNotificationInfo(
                        types,
                        Notification.class.getName(),
                        "Emitted when queue depth crosses 5")
        };
    }
}
```

Cần phân biệt rõ:

- `queueDepth` và `nextSequence` là trạng thái của **ứng dụng mô phỏng**, không đọc được độ sâu của hàng đợi sản xuất.
- Khi depth thay đổi từ **dưới 5** lên **từ 5 trở lên**, setter chủ động phát một notification. Nếu depth vẫn trên ngưỡng và tiếp tục tăng, code **không** phát lại.
- `reset()` gọi setter với 0, không phát notification threshold vì không phải crossing theo hướng đi lên.
- `NotificationBroadcasterSupport` cung cấp dispatch; `getNotificationInfo()` mô tả type mà bean có thể phát. Nếu bỏ logic `sendNotification`, metadata **không tự tạo event**.
- Phần triển khai đơn giản giữ synchronized lock khi phát notification; điều đó chấp nhận trong demo một luồng, **không phải mẫu hot-path tối ưu cho production**. Với workload thật nên cập nhật trạng thái dưới lock, phát event bên ngoài critical section hoặc dùng cơ chế async có giới hạn hàng đợi, đo callback latency và quản lý backpressure.

### 8.3 Tệp JmxConceptDemo.java

```java
import java.lang.management.ManagementFactory;
import javax.management.Attribute;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.NotificationListener;
import javax.management.ObjectName;

public class JmxConceptDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
                "learning.jmx:type=QueueMetrics,name=Orders");

        QueueMetrics bean = new QueueMetrics();
        server.registerMBean(bean, name);

        NotificationListener listener = (event, handback) ->
                System.out.println("NOTIFICATION=" + event.getType());

        try {
            server.addNotificationListener(name, listener, null, null);

            System.out.println("REGISTERED=" + server.isRegistered(name));

            ObjectName pattern = new ObjectName(
                    "learning.jmx:type=QueueMetrics,*");
            System.out.println("DISCOVERED="
                    + server.queryNames(pattern, null).contains(name));

            MBeanInfo info = server.getMBeanInfo(name);
            System.out.println("METADATA_PRESENT=" + (info != null));

            System.out.println("ATTRIBUTE_INITIAL="
                    + server.getAttribute(name, "QueueDepth"));

            server.setAttribute(name, new Attribute("QueueDepth", 5));
            System.out.println("ATTRIBUTE_UPDATED="
                    + server.getAttribute(name, "QueueDepth"));
            System.out.println("STATUS="
                    + server.getAttribute(name, "Status"));

            server.invoke(name, "reset", new Object[0], new String[0]);
            System.out.println("AFTER_RESET="
                    + server.getAttribute(name, "QueueDepth"));
        } finally {
            try {
                server.removeNotificationListener(name, listener);
            } finally {
                server.unregisterMBean(name);
            }
        }

        System.out.println("UNREGISTERED=" + !server.isRegistered(name));
    }
}
```

Biên dịch và chạy từ thư mục chứa đủ ba file:

```bash
javac QueueMetricsMBean.java QueueMetrics.java JmxConceptDemo.java
java JmxConceptDemo
```

Stdout **chính xác do chương trình phát ra** trên JVM tương thích trong điều kiện bình thường:

```text
REGISTERED=true
DISCOVERED=true
METADATA_PRESENT=true
ATTRIBUTE_INITIAL=0
NOTIFICATION=learning.queue.threshold
ATTRIBUTE_UPDATED=5
STATUS=BUSY
AFTER_RESET=0
UNREGISTERED=true
```

**Vì sao thứ tự này hợp lý?**

1. `registerMBean` đưa MBean vào platform registry, nên `isRegistered` trả `true`.
2. Pattern `learning.jmx:type=QueueMetrics,*` bao gồm ObjectName xác định, nên `queryNames(...).contains(name)` là `true`.
3. `getMBeanInfo` trả metadata của bean đã đăng ký, không trả `null` trong trường hợp bình thường.
4. `getAttribute("QueueDepth")` gọi getter trả giá trị khởi tạo `0`.
5. `setAttribute` gọi setter với 5. Setter phát notification khi vượt ngưỡng. `NotificationBroadcasterSupport` mặc định dispatch đồng bộ, nên listener in dòng `NOTIFICATION=...` **trước khi** lệnh `setAttribute` trả về.
6. Đọc lại `QueueDepth` được 5 và `Status` là `BUSY`.
7. `invoke("reset", [], [])` gọi operation, depth thành 0.
8. `finally` tháo listener và hủy đăng ký; kiểm tra cuối nhận `UNREGISTERED=true`.

Code cố tình chỉ in loại notification, không in timestamp, process ID hoặc tên MBean tự sinh để stdout có thể kiểm chứng. Trong môi trường thật, callback order giữa nhiều threads/event sources **không được suy từ ví dụ đơn luồng**.

### 8.4 Nếu biên dịch hoặc đăng ký thất bại?

- Đảm bảo tên file public class/interface đúng: `QueueMetricsMBean.java`, `QueueMetrics.java` và `JmxConceptDemo.java`.
- Các file cùng default package cho mục đích học; với dự án thực nên dùng package rõ ràng, bố trí source tree tương ứng.
- Dùng Java 17+ và JDK có `javac`, không dùng chỉ JRE tối giản.
- `QueueMetrics` phải implement **đúng tên interface** `QueueMetricsMBean` và có public methods cần thiết.
- Nếu đã có bean cùng ObjectName trong **cùng MBeanServer**, `registerMBean` ném `InstanceAlreadyExistsException`; demo chạy một JVM mới cho mỗi lệnh nên không có đăng ký cũ từ lần trước.
- Nếu không có interface hợp lệ, `NotCompliantMBeanException` có thể xuất hiện. Không sửa bằng cách tự ý đăng ký một object bất kỳ rồi bỏ qua contract.
- Nếu notification không xuất hiện, kiểm tra bean có thực sự phát `sendNotification`, listener đã được add **trước** khi setter đổi state và type/filter được cấu hình đúng.

## 9. Tự khám phá contract bằng MBeanInfo trước khi đọc/gọi

Một client không nên đoán rằng mọi bean có attribute tên `Value` hoặc operation `reset`. `MBeanInfo` cho phép xác minh metadata.

Ví dụ **đoạn code bổ sung** (không phải lớp độc lập):

```java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanNotificationInfo;

var info = server.getMBeanInfo(name);

for (MBeanAttributeInfo a : info.getAttributes()) {
    System.out.println(a.getName()
            + " type=" + a.getType()
            + " read=" + a.isReadable()
            + " write=" + a.isWritable());
}

for (MBeanOperationInfo o : info.getOperations()) {
    System.out.println("op=" + o.getName()
            + " params=" + o.getSignature().length);
}

for (MBeanNotificationInfo n : info.getNotifications()) {
    System.out.println("notification-types="
            + String.join(",", n.getNotifTypes()));
}
```

Các `import`/biến `server`/`name` cần đặt trong file/method phù hợp. Metadata order **không được dùng** làm một output cụ thể nếu chưa sắp xếp; ví dụ độc lập không in danh sách để tránh khẳng định thứ tự/đếm mà implementation có thể trình bày khác.

### 9.1 Vì sao metadata vẫn chưa phải mọi sự thật?

- `isWritable()` nói contract có thể ghi, **không bảo đảm caller có quyền** hoặc giá trị mới hợp lệ.
- `getNotifications()` cho biết loại event bean khai báo, **không bảo đảm** event sẽ phát, listener sẽ nhận hoặc dữ liệu có tính bền vững.
- `getOperations()` cho biết operation có trong contract, **không nói chắc** thời gian thực hiện, tính idempotent hoặc side effect.
- `getClassName()` là thông tin metadata về class, không phải sự chứng minh quy trình nghiệp vụ đang khỏe.
- Một MBean có thể biến mất giữa `queryNames` và `getMBeanInfo`; caller phải xử lý `InstanceNotFoundException`.

Nếu thực hiện nhiều `getAttribute` nối tiếp, dữ liệu có thể phản ánh **những thời điểm khác nhau**. JMX không tự tạo atomic snapshot toàn bộ JVM. Khi làm latency/GC/rate, phải lưu window/timestamp/instance identity.

## 10. JMX local và JMX remote: cùng mô hình, khác ranh giới tin cậy

### 10.1 Local JMX không đòi mở port cho mọi người

Ví dụ `ManagementFactory.getPlatformMBeanServer()` diễn ra trong **chính JVM**. JConsole/JMC có thể attach cục bộ tùy công cụ, implementation, quyền và chính sách runtime. Một service có MBeanServer không đồng nghĩa remote management đã bật.

### 10.2 Remote client dùng MBeanServerConnection

Một JMX connector được cấu hình/hạn chế quyền có thể cấp đối tượng `MBeanServerConnection` để client gọi `queryNames`, `getAttribute` hoặc `invoke` theo permissions của endpoint. Các bước liên quan tới transport, discovery, authentication, TLS, network/firewall và lifecycle của connector **nằm ngoài phần mô hình cơ bản**, nhưng cần nhớ:

- JMX remote **không tự an toàn** vì nằm trên mạng nội bộ.
- Không bật endpoint không xác thực hoặc TLS yếu trên production để tiện xem một metric.
- Một operation có thể restart/reconfigure ứng dụng; **read-only và write privileges phải phân tách**.
- Remote JMX dựa trên kết nối có thể timeout/đứt, object có thể biến mất, attribute có thể không serialize/marshal được theo kiểu mong đợi.
- Các cổng/địa chỉ do connector/RMI công bố có thể liên quan NAT, containers, firewalls; lỗi kết nối không chứng minh MBean không tồn tại.
- Nếu kết nối qua JConsole/JMC, kiểm tra chính xác process/service, user, quyền, môi trường, Java version và kết nối được tin cậy.

Đối với mục tiêu học cú pháp, **không cần triển khai JMX remote**. Chương trình `JmxConceptDemo` hoàn toàn cục bộ, giảm rủi ro cấp quyền quá rộng.

### 10.3 ObjectName không định danh JVM từ xa

Hai JVM khác nhau đều có thể đăng ký `learning.jmx:type=QueueMetrics,name=Orders`. Nếu hệ thống giám sát tổng hợp từ nhiều JVM, key hoàn chỉnh cần cả **endpoint/JVM instance identity + ObjectName + timestamp**. Nếu không, time series dễ nhập nhằng hoặc ghi đè lẫn nhau.

PID chỉ hữu ích ở một phạm vi host/namespace và có thể tái sử dụng sau restart. Một monitor đáng tin ghi thêm process start time, container/pod identity, service/version và môi trường; tránh gắn giá trị bí mật vào labels.

## 11. So sánh attribute, operation và notification trong tình huống chẩn đoán

| Câu hỏi vận hành | Chọn khả năng JMX nào? | Giới hạn |
| --- | --- | --- |
| “Queue depth hiện tại bằng bao nhiêu?” | Đọc attribute `QueueDepth` | Snapshot, không cho biết peak giữa hai samples |
| “Trạng thái BUSY hay NORMAL?” | Đọc attribute `Status` | Contract của ứng dụng, không phải health check toàn diện |
| “Đặt ngưỡng queue mới?” | Ghi attribute có setter tương ứng **nếu được thiết kế và được phép** | Mutating, cần validate/rate-limit/audit |
| “Xóa/reset queue statistics?” | Gọi operation `reset` **khi có phê duyệt** | Có thể làm mất số liệu chẩn đoán |
| “Báo ngay khi depth vượt 5?” | Subscribe notification từ bean hỗ trợ | Không bền vững; callback có thể chậm/mất |
| “Có những khả năng nào?” | `getMBeanInfo` | Metadata không phải lịch sử dữ liệu |
| “MBean nào được đăng ký?” | `queryNames`, `isRegistered` | Snapshot; tên có thể đổi sau redeploy |
| “GC pause p99 là bao nhiêu?” | Không suy từ một attribute counter đơn lẻ | Cần event-level/GC logs/JFR/histogram |

Các khả năng có thể kết hợp. Ví dụ giám sát queue có thể dùng attribute cho **gauge**, notification cho **thời điểm vượt ngưỡng** và operation để **điều khiển có kiểm soát**. Tuy nhiên, nếu cần lưu lịch sử và alert có bảo đảm, nên đưa dữ liệu từ JMX vào pipeline metrics/events đúng semantics.

## 12. Các lỗi JMX thường gặp và nguyên nhân

### 12.1 InstanceAlreadyExistsException

**Tình huống:** cùng một ObjectName đã được đăng ký. Nguyên nhân thường là register hai lần, component khởi tạo lại, class loader/redeploy không unregister hoặc đặt tên thiếu instance-specific key.

**Khắc phục:** quản lý lifecycle rõ, xác định owner; `isRegistered` có thể giúp kiểm tra trước nhưng không loại bỏ race. Với concurrent registration, xử lý exception; không tự hủy MBean không thuộc mình chỉ để lấy tên.

### 12.2 NotCompliantMBeanException

**Tình huống:** object không đáp ứng Standard MBean/MXBean/DynamicMBean contract. Có thể interface không tên đúng, không public, method signature không hợp lệ hoặc kiểu không được ánh xạ theo MXBean rules.

**Khắc phục:** kiểm tra compliance bằng interface `YourClassMBean` public; dùng `StandardMBean` wrapper khi muốn định nghĩa interface khác tên theo contract hợp lệ; với MXBean kiểm tra open-type mapping. Không tự coi mọi POJO là một MBean có thể đăng ký.

### 12.3 MalformedObjectNameException

**Tình huống:** tên ObjectName sai cú pháp do thiếu domain/key, dấu phẩy/colon trong value, wildcard dùng sai vị trí hoặc giá trị không được quote đúng.

**Khắc phục:** tách domain/key rõ ràng, dùng `ObjectName.quote` cho value động, kiểm tra `isPattern()` khi phân biệt registration và discovery. Không nối trực tiếp input từ user vào ObjectName dùng làm quyền truy cập.

### 12.4 InstanceNotFoundException

**Tình huống:** MBean không được đăng ký trong server được kết nối, hoặc đã unregister giữa lúc query và đọc.

**Khắc phục:** xác minh endpoint, JVM instance và ObjectName canonical; kiểm tra lại `isRegistered` và lifecycle. **Không suy ra JVM process đã chết** từ một MBean biến mất: bean có thể được unregister trong process còn sống.

### 12.5 AttributeNotFoundException / InvalidAttributeValueException

**Tình huống:** attribute sai tên/chữ hoa-thường, không readable/writable theo metadata, value sai kiểu/range hoặc setter từ chối.

**Khắc phục:** xem `MBeanInfo.getAttributes()` và contract thực tế; phân biệt tên `getQueueDepth` của method với attribute `QueueDepth`. Với thay đổi giá trị, xác minh quyền và điều kiện nghiệp vụ trước khi retry.

### 12.6 ReflectionException / MBeanException

**Tình huống:** gọi operation không khớp tên/signature hoặc code của method được gọi phát sinh exception. JMX có thể bọc lỗi ở lớp reflection/management exception.

**Khắc phục:** xem chính xác `getOperations()`, parameter type strings và root cause, phân biệt lỗi client invocation với lỗi logic của bean. Đừng retry operation gây side effect mà không biết nó đã chạy một phần hay chưa.

### 12.7 “Notification không đến”

**Giả thuyết cần kiểm tra:**

- Bean có thực sự implement broadcaster/emitter và **gọi `sendNotification`** không?
- Listener đã được add trước event chưa; có bị remove/disconnect/GC/class loader cleanup?
- Type có bị filter chặn không; client có subscribe đúng ObjectName/JVM instance?
- Sự kiện phát trước lúc subscribe? Không có history/replay mặc định.
- Callback xử lý chậm, ném lỗi hoặc remote connection bị gián đoạn?
- Nếu nhìn thấy event từ MBeanServerDelegate, có đang nhầm với event của bean ứng dụng không?

Không giải quyết bằng cách tăng polling vô hạn mà không biết notification contract.

### 12.8 Remote JMX timeout / lỗi kết nối

Có thể do mạng, authentication, certificate/TLS, RMI endpoint/port/NAT, JMX connector chưa bật, quyền user, firewall hoặc JVM/collector bận. Một timeout **không đủ** kết luận “MBean bị hỏng”. Kiểm tra layer kết nối trước, sau đó mới kiểm tra ObjectName và metadata; không bypass bảo mật chỉ để xác minh.

## 13. Thiết kế JMX MBean an toàn cho production

### 13.1 Giới hạn quyền và diện tích thao tác

Một MBean công bố operation `shutdown` hoặc setter thay cấu hình có thể trở thành bề mặt điều khiển nhạy cảm khi qua remote JMX. Nguyên tắc thiết kế:

1. Chỉ công bố những attributes/operations thực sự có nhu cầu vận hành.
2. Tách **read-only telemetry** khỏi **mutating control** khi có thể.
3. Kiểm soát authorization của connector và operation; không chỉ dựa vào khó đoán ObjectName.
4. Ghi audit cho thay đổi có tác động, không log credential.
5. Kiểm tra input/range, timeout, idempotency và khả năng gọi lặp.
6. Không cho phép một getter/do operation thực hiện công việc vô hạn hoặc block request threads.
7. Không công bố secret qua attribute, notification message/userData hoặc ObjectName.

### 13.2 Getter và notification phải có chi phí kiểm soát

Nếu `getQueueDepth()` cần scan một hàng đợi khổng lồ hoặc gọi DB, scraper tần suất cao có thể tự gây nghẽn. Nên dùng cache/snapshot cheap hoặc counter/gauge được cập nhật trong đường vận hành với synchronization phù hợp. Getter phải có semantics rõ về thời điểm và tính nhất quán; không giả định các attributes đọc lần lượt là atomic.

Với notification, không thực hiện I/O lâu hoặc logic nặng ngay trong `handleNotification`. `NotificationBroadcasterSupport` mặc định dispatch synchronous: một listener chậm có thể làm sender chậm. Nếu cấu hình Executor async, phải thiết kế giới hạn queue, xử lý backpressure/drop và thứ tự khi nhiều worker chạy; không tự hứa “async = không mất event”.

### 13.3 Metadata và labels không nên quá nhiều

Nếu đăng ký một MBean cho mỗi customer/session/request, số lượng beans, ObjectNames và metric labels có thể tăng cực lớn. Cần chọn đối tượng aggregate có vòng đời rõ; dữ liệu per-request nên đi qua traces/logs hoặc event pipeline được kiểm soát, không qua registry JMX tùy tiện.

### 13.4 Vòng đời và tài nguyên

- Register khi component sẵn sàng quản trị, unregister khi component kết thúc/undeploy.
- Tháo listener khi subscriber dừng, nhất là sau reconnect.
- Dùng tên ổn định theo component nhưng đủ phân biệt nhiều instance trong **cùng JVM**.
- Tránh giữ class loader cũ khi hot reload vì MBeanServer còn tham chiếu bean/listener.
- Với event/metric mang thời gian, ghi JVM start time/instance để tránh nối nhầm sau restart.
- Dành quyền truy cập raw management data cho vai trò cần thiết; số liệu nội bộ không tự động là public.

## 14. Ba tình huống thực tế để ứng dụng

### 14.1 Chẩn đoán thread pool bị nghẽn

**Đề bài:** API latency p95 tăng; ứng dụng expose custom MBean về thread pool.

Quy trình:

1. Tìm ObjectName đúng bằng `queryNames` dưới domain của service đã xác minh.
2. Đọc `MBeanInfo` để xem có `ActiveThreads`, `QueueDepth`, `CompletedTaskCount` hay không.
3. Lấy mẫu attribute cùng timestamp/instance và đối chiếu HTTP rate, CPU, GC và application metrics.
4. Nếu MBean phát `threadpool.saturation` notification, subscribe để có dấu mốc crossing, nhưng không dùng nó thay histogram latency.
5. **Không gọi operation `reset` hay `shutdown`** chỉ để “xem thử” khi chưa xác minh side effect.

Kết luận cần dựa vào cả queue metrics, number of threads và traces; một QueueDepth lớn ở một snapshot không nhất thiết là nguyên nhân duy nhất của latency.

### 14.2 Memory threshold

Platform `MemoryMXBean` có thể phát memory notifications trong các điều kiện được JVM hỗ trợ và cấu hình. Nhưng threshold support phụ thuộc `MemoryPoolMXBean` cụ thể; không phải mọi pool có usage threshold, và bật threshold ở pool khác có thể làm số liệu khác.

Phân biệt:

- Attribute `HeapMemoryUsage` là snapshot/usage, không phải event log.
- Threshold notification là event logic riêng, không nhất thiết xuất ở mọi GC.
- Heap high không tự động là OOM; container memory pressure/RSS còn nhiều nguồn ngoài Java heap.
- Nếu cần lịch sử memory pressure, cần metrics time series và logs/JFR.

### 14.3 Operation vận hành: clear cache

Một MBean có `CacheSize` attribute và `clearCache()` operation. Xem cache size có thể ít rủi ro; gọi clear có thể gây cache miss storm, tăng tải database và làm chậm request. Dùng `getMBeanInfo` để nhận diện operation, đọc runbook của service, xác định quyền và thời điểm; không tự thử trên production. Sự phân biệt attribute và operation là phân biệt **quan sát** với **can thiệp**, không chỉ cú pháp.

## 15. Checklist kiểm tra contract trước khi dùng JMX

- [ ] Đã xác nhận JVM/instance và MBeanServer/connector đang truy cập.
- [ ] Biết ObjectName xác định; nếu dùng pattern, hiểu phạm vi query và không giả định thứ tự `Set`.
- [ ] ObjectName không chứa credential/định danh nhạy cảm; tên động được quote/validate đúng.
- [ ] Đã kiểm tra `MBeanInfo` trước khi đọc/ghi/gọi operation chưa biết.
- [ ] Attribute có readable/writable metadata đúng và giá trị/đơn vị/semantics được hiểu.
- [ ] Ghi attribute hoặc gọi operation chỉ khi có quyền và đã xác minh side effect.
- [ ] `invoke` dùng đúng operation name, param types và signature.
- [ ] MBean có support notifications thật; listener được đăng ký trước event và được gỡ lúc cleanup.
- [ ] Không coi notification là sự kiện bền vững hay bảo đảm replay.
- [ ] Gắn timestamp/instance vào snapshots; không suy rate/p99 từ một getter duy nhất.
- [ ] Đã giới hạn chi phí getters, event callbacks và số MBeans/labels.
- [ ] Remote JMX có authentication/TLS/authorization và network boundaries phù hợp; không mở endpoint công khai chỉ để debug.
- [ ] Có cách xử lý mất kết nối, InstanceNotFound, counter reset, redeploy và listener lifecycle.
- [ ] Bằng chứng JMX được đối chiếu với logs, GC/JFR/CPU và application telemetry khi cần kết luận nguyên nhân.
- [ ] Chỉ chia sẻ metadata/attribute/notifications sau khi đánh giá dữ liệu nhạy cảm.

## 16. Bài tập tự kiểm tra

**Bài 1 — Phân biệt tên với đối tượng.** Trong một MBeanServer có đăng ký `learning.jmx:type=QueueMetrics,name=Orders`. Client query `learning.jmx:type=QueueMetrics,*` được bao nhiêu MBean?

**Đáp án:** Pattern có thể khớp bean này và các bean khác cùng domain/type; không thể suy số lượng chỉ từ một ví dụ. Cần chạy `queryNames`. ObjectName cũng không chỉ định PID/JVM ở nơi khác.

**Bài 2 — Getter và setter.** Interface có `int getQueueDepth()` và `void setQueueDepth(int)`. JMX attribute tên gì, có thể đọc/ghi thế nào?

**Đáp án:** Attribute là `QueueDepth`, có getter/setter. Đọc `getAttribute(name,"QueueDepth")` và ghi `setAttribute(name,new Attribute("QueueDepth",n))` nếu được phép; setter có thể thay đổi trạng thái.

**Bài 3 — Operation không tham số.** `reset()` trên Standard MBean được gọi thế nào?

**Đáp án:** `server.invoke(name,"reset",new Object[0],new String[0])`. Nó là operation mutating trong ví dụ, không phải một read-only attribute.

**Bài 4 — Thời điểm notification.** Demo có QueueDepth từ 0 lên 5 trước khi listener được add. Sau khi add listener, có nhận event cũ không?

**Đáp án:** Không được bảo đảm và với bean demo sẽ không nhận, vì notification được phát tại lúc setter chạy; `NotificationBroadcasterSupport` không lưu replay history theo mặc định.

**Bài 5 — Vì sao JMX query thấy bean nhưng đọc attribute thất bại?**

**Đáp án:** Có thể tên attribute sai, attribute không readable, bean bị unregister giữa hai bước, getter ném exception hoặc caller thiếu quyền. `queryNames` chỉ chứng minh bean được liệt kê ở lúc query.

**Bài 6 — MXBean khác Standard MBean ở điểm gì?**

**Đáp án:** MXBean có quy ước open-type mapping cho dữ liệu phù hợp client JMX, trong khi Standard MBean dùng contract Java interface theo quy tắc đặt tên. Khi đọc từ xa, object phức tạp có thể được biểu diễn dưới dạng `CompositeData` thay vì class ứng dụng gốc.

**Bài 7 — Một listener chậm có thể ảnh hưởng service không?**

**Đáp án:** Có. `NotificationBroadcasterSupport` mặc định phát đồng bộ trong thread gọi `sendNotification`; một callback chậm có thể gây delay. Nếu dùng dispatch async, vẫn phải kiểm soát queue/ordering/drop.

**Bài 8 — Có nên in `MBeanInfo` rồi thử invoke tất cả operations?**

**Đáp án:** Không. Metadata giúp phát hiện contract nhưng operations có thể mutate/restart/flush và mang chi phí cao. Chỉ gọi operation phù hợp mục đích, quyền và runbook đã được phê duyệt.

## Tài liệu tham khảo

- [Java SE 21 — MBeanServer](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html): registration, access, invocation, query, listener và lỗi.
- [Java SE 21 — ObjectName](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html): domain, key properties, pattern, quoting và canonical name.
- [Java SE 21 — javax.management package](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/package-summary.html): MBean types, Standard MBean convention và access methods.
- [Java SE 21 — MBeanInfo](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html): metadata về attributes/operations/notifications.
- [Java SE 21 — NotificationBroadcasterSupport](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/NotificationBroadcasterSupport.html): dispatcher mặc định đồng bộ, filters/listeners và executor.
- [Java SE 21 — ManagementFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html): lấy platform MBeanServer và platform MXBeans.
- [Oracle JMX Technology Tutorial](https://docs.oracle.com/javase/tutorial/jmx/index.html): ví dụ Standard MBeans, operations, notifications và clients (tài liệu tutorial của Java SE 8; đọc kèm Javadoc release đang dùng).

**Ghi nhớ:** `MBeanServer` là registry/đầu mối thao tác; `ObjectName` chỉ đúng MBean trong một server; `attribute` là trạng thái/cấu hình được công bố; `operation` là hành động có thể gây tác động; `notification` là sự kiện được bean thiết kế phát, không phải log bền vững. Khi làm runtime diagnostics, **khám phá bằng metadata, đọc đúng trường, kiểm soát lệnh thay đổi, quản lý listener và bảo mật kết nối**, rồi ghép dữ liệu JMX với logs, metrics và events theo thời gian để kết luận.