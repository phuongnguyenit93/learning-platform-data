# MXBean: MXBean tùy biến và dữ liệu quản trị không phụ thuộc lớp phía khách

## Mục tiêu học tập

Trong ứng dụng Java, một bộ phận quản trị có thể cần xem **số yêu cầu đã xử lý, độ dài hàng đợi, trạng thái service, kết quả thống kê** và thực hiện một số **operation được phép** mà không chạy cùng codebase với service. Nếu server chỉ xuất ra một đối tượng Java riêng của ứng dụng, khách quản trị bình thường sẽ phải có đúng lớp đó trong classpath, đúng phiên bản package, cùng điều kiện serialization/class loading. Điều này gây khó khăn khi phát triển dashboard, công cụ giám sát hoặc kết nối nhiều JVM khác nhau.

**MXBean**, thuộc Java Management Extensions (**JMX**), giải quyết một phần quan trọng: interface ở phía server có thể sử dụng những kiểu Java có quy tắc ánh xạ phù hợp; khi truy cập qua **`MBeanServer`/`MBeanServerConnection`**, chúng được chuyển thành các **Open Types** chuẩn của Java, ví dụ **`String`**, **`String[]`**, **`CompositeData`**, **`TabularData`**. Vì vậy **một client động không cần các lớp dữ liệu quản trị tự định nghĩa của server** vẫn có thể đọc metadata và values của MXBean.

Bài này tập trung chính xác vào **“MXBean tùy biến và dữ liệu quản trị không phụ thuộc lớp phía khách”**, bao gồm cơ chế mapping, cách xây custom MXBean, cách viết **generic JMX client chỉ dùng JDK classes**, giới hạn tương thích, bảo mật và kiểm thử thực tế. Sau bài bạn có thể:

1. Phân biệt **MBean thông thường (Standard MBean)** và **MXBean**; biết vì sao MXBean giúp giảm classpath dependency của client.
2. Tạo **public MXBean interface** theo quy ước hậu tố `MXBean` hoặc annotation **`@javax.management.MXBean`**.
3. Đăng ký implementation qua **`MBeanServer.registerMBean`** với **`ObjectName`** cụ thể.
4. Hiểu **getter → attribute**, **setter → writable attribute**, phương thức khác → **operation**, và tên thuộc tính **`getSnapshot` → `Snapshot`**.
5. Trả dữ liệu quản trị bằng **record/bean DTO**, **List**, **Map**, **enum** và các kiểu được hỗ trợ; quan sát chuyển đổi sang **CompositeData, array, TabularData, String**.
6. Dùng **`MBeanServerConnection.getMBeanInfo`** để khám phá schema, operations và thông tin OpenType thay vì phải biết server implementation.
7. Viết **generic client** chỉ import các kiểu `javax.management` và `javax.management.openmbean`, truy cập `getAttribute`/`invoke` mà không import DTO hoặc interface của service.
8. Phân biệt đường đọc **raw Open Data** và đường **typed proxy `JMX.newMXBeanProxy`**: proxy cần các kiểu interface/DTO đã biết, dù dữ liệu truyền qua server vẫn là Open Data.
9. Hiểu ranh giới **record mapping**, `@ConstructorProperties`/`@ConstructorParameters`, yêu cầu **reconstructible types**, và những kiểu/collection không thể dùng tùy tiện.
10. Tách **định dạng dữ liệu quản trị ổn định** khỏi object graph nội bộ có reference, lock, credential, connection hoặc dữ liệu lớn.
11. Chạy **hai file Java 17+**, biên dịch client hoàn toàn độc lập trước server, chứng minh `CompositeData`/`TabularData`/`String[]`/enum và operation thực sự hoạt động.
12. Xây tests cho **MBeanInfo, OpenType metadata, schema evolution, security, concurrency, registration/unregistration, gọi operation đúng quyền**.

**Tính hiện hành:** Các API `javax.management`, `javax.management.openmbean`, `java.lang.management` thuộc **module `java.management`** vẫn có trong Java 17 và Java 26. Java record là tính năng chuẩn từ Java 16. Ví dụ đã được kiểm thử thực tế trên **OpenJDK 24.0.2**, biên dịch bằng `javac --release 17`, không dùng cơ chế legacy để giao tiếp hay deserialize các lớp riêng của server.

---

## 1. Vì sao client thường phụ thuộc lớp quản trị của server?

### 1.1. Vấn đề với Java object riêng của ứng dụng

Giả sử một service tạo `QueueSnapshot`:

~~~java
// MẢNH MINH HỌA, chỉ diễn tả DTO phía service.
public final class QueueSnapshot {
    private final long processed;
    private final int waiting;
    // Constructors, getters...
}
~~~

Nếu một giao thức quản trị bắt client deserialize trực tiếp `com.example.QueueSnapshot`, client có thể cần:

- Có file class tương ứng trong classpath/module path.
- Biết package name, signatures và constructors/serialization details.
- Thỏa điều kiện version/compatibility giữa server và client.
- Xử lý rủi ro khi dữ liệu serializable tùy ý và các dependency lồng nhau.
- Update mỗi dashboard/client khi server refactor DTO.

Đối với tool quan sát linh hoạt hoặc sản phẩm cần nhiều phiên bản server, cách đó rất bất tiện. **MXBean không xuất Java object riêng dưới dạng bắt buộc client phải nhận chính class đó**; nó dùng quy tắc chuyển dữ liệu sang **Open Data**.

### 1.2. Hai lối truy cập cùng một MXBean

~~~text
                         Service JVM
                   Custom QueueView MXBean
             getSnapshot() returns Snapshot record
                │                     │
                ▼                     ▼
        MXBean mapping            Typed Java API
        Snapshot →                 QueueView proxy
        CompositeData                 (nếu client có
                │                      interface/DTO)
                ▼
              MBeanServer
                │
                ▼
        MBeanServerConnection
                │
      ┌─────────┴───────────────────┐
      │                             │
      ▼                             ▼
Generic client                 Typed client
getAttribute()                 JMX.newMXBeanProxy()
→ CompositeData                → Snapshot record
→ TabularData                   → Map<String,Integer>
→ String[]                      → List<String>
→ String                        → enum
      │                             │
   Chỉ cần JDK              Cần shared interface/DTO
~~~

**“Không phụ thuộc lớp phía khách”** ở đây nghĩa là **khách quản trị không cần có những application-specific model classes của server để đọc Open Data**. Không có nghĩa client không cần biết **ObjectName, attribute names, loại dữ liệu/schema** hoặc không cần thông tin xác thực. Các semantics như `processed` là số lượng requests vẫn phải được tài liệu hóa.

### 1.3. Các khái niệm cần nhớ

| Khái niệm | Vai trò |
| --- | --- |
| **JMX** | Hạ tầng Java để quan sát/điều khiển các resources |
| **MBean** | Managed Bean có attributes, operations, notifications |
| **MXBean** | MBean được giới hạn và ánh xạ dữ liệu theo Open Types |
| **OpenType** | Mô tả type chuẩn để các clients tương tác không cần model class riêng |
| **CompositeData** | Dữ liệu dạng bản ghi gồm nhiều key/value có schema `CompositeType` |
| **TabularData** | Tập dữ liệu dạng bảng/map có `TabularType` |
| **MBeanServer** | Registry và dispatcher JMX attributes/operations |
| **MBeanServerConnection** | Interface client dùng để đọc/ghi/gọi operations, có thể local hoặc remote |
| **ObjectName** | Định danh MBean trong một server |
| **MBeanInfo** | Runtime metadata: attributes, operations, constructors, notifications, descriptors |
| **JMX.newMXBeanProxy** | Tạo proxy typed khi client có MXBean interface tương ứng |
| **ManagementFactory** | Truy cập platform MXBeans và platform MBeanServer của JVM |

---

## 2. Tạo MXBean tùy biến trong Java hiện hành

### 2.1. Hai cách nhận diện MXBean interface

**Theo tên public interface có hậu tố `MXBean`:**

~~~java
// MẢNH MINH HỌA
public interface OrdersMXBean {
    int getQueueSize();
    long getProcessedCount();
}
~~~

**Hoặc đánh dấu public interface bằng `@MXBean`:**

~~~java
import javax.management.MXBean;

// MẢNH MINH HỌA: tên QueueView không có hậu tố MXBean nhưng vẫn là MXBean.
@MXBean
public interface QueueView {
    long getProcessed();
    void markProcessed(int delta);
}
~~~

Cả hai đều là cách chuẩn còn áp dụng trong Java SE 26. `@MXBean(false)` còn có thể đánh dấu một interface **không** thuộc loại MXBean dù tên tương tự hậu tố.

Trong ví dụ runnable, interface được đặt **public** và có annotation **`@MXBean`**, minh họa rõ ràng cách nhận diện không phụ thuộc tên hậu tố.

### 2.2. Implementation không nhất thiết cùng tên interface

~~~java
// MẢNH MINH HỌA:
@MXBean
public interface QueueView {
    long getProcessed();
}

public final class QueueService implements QueueView {
    public long getProcessed() {
        return 7L;
    }
}
~~~

MXBean implementation cần implement đúng interface và đáp ứng các yêu cầu JMX-compliant. Không cần gọi class `Queue` chỉ vì interface tên `QueueView` hoặc `QueueViewMXBean`.

`@MXBean` nằm trên **interface**. Không phải cứ annotation một class domain tùy ý là mọi public method của class trở thành managed operations. Chỉ những methods được phơi bày qua management interface mới tạo API quản trị, giảm surface area.

### 2.3. Getter, setter và operation

~~~java
// MẢNH MINH HỌA
@MXBean
public interface WorkerView {
    long getProcessed();        // attribute "Processed", read-only
    boolean isActive();         // attribute "Active", read-only
    int getLimit();             // attribute "Limit"
    void setLimit(int value);   // writable attribute "Limit"
    void reset();               // JMX operation "reset"
}
~~~

Phân biệt **attribute** và **operation**:

- `getProcessed()` → attribute tên `Processed`, kiểu `long` ở Java.
- `isActive()` → attribute tên `Active`, kiểu `boolean`.
- `getLimit` và `setLimit` kết hợp thành writable attribute.
- `reset()` → operation, **không phải getter attribute**.
- `markProcessed(int delta)` → operation với tham số kiểu nguyên thủy `int`, JMX signature cần đúng `"int"` khi gọi raw.

Những operation có side effects cần chính sách quyền chặt chẽ. Không tạo operation vô tình cho phép shutdown, dump secrets, clear queue hoặc nâng quyền chỉ vì nó tiện để test.

### 2.4. Đăng ký đúng `ObjectName`

~~~java
// MẢNH MINH HỌA: server và service đã tạo.
ObjectName name = new ObjectName(
        "demo.management:type=Queue,name=primary");

server.registerMBean(service, name);
~~~

Cấu trúc `ObjectName` gồm **domain** và các **key properties**. Hãy có naming convention ổn định, không cho dữ liệu client tùy ý đi vào ObjectName không kiểm soát.

- `registerMBean` với ObjectName đã được dùng có thể gây **InstanceAlreadyExistsException**.
- Một class không tuân thủ quy ước/JMX interface có thể gây **NotCompliantMBeanException**.
- `unregisterMBean` khi bean không tồn tại có thể gây **InstanceNotFoundException**.
- MBeanServer là registry, không phải database lưu lịch sử metrics.
- Nếu mbean chỉ nên sống trong thời gian component hoạt động, hãy đăng ký/unregister theo lifecycle để không để lại stale endpoints.

### 2.5. `ManagementFactory` và isolated MBeanServer

Khi ứng dụng muốn một bảng quản trị chung với JVM platform beans:

~~~java
// MẢNH MINH HỌA:
javax.management.MBeanServer server =
        java.lang.management.ManagementFactory.getPlatformMBeanServer();
~~~

`getPlatformMBeanServer` cung cấp shared platform MBeanServer của JVM, trong đó có JVM platform MXBeans. Custom MXBean có thể được đăng ký thêm theo ObjectName phù hợp.

Trong **demo**, chương trình dùng **`MBeanServerFactory.newMBeanServer("example")`** để tạo một MBeanServer độc lập, không động chạm global/platform registry và **không bật remote connector**. Điều này tạo test cô lập, dễ dọn dẹp, không cần cổng mạng.

---

## 3. Cơ chế ánh xạ dữ liệu qua Open Types

**Khái niệm cốt lõi:** Bên trong implementation có thể dùng các Java types phong phú hơn. Khi gọi qua `MBeanServerConnection`, MXBean framework chuyển values sang một tập **Open Data types** mà khách chỉ dùng Java standard management API vẫn hiểu được.

### 3.1. Bảng ánh xạ thường gặp

| Type ở MXBean interface | Open type/data khi truy cập qua MBeanServer |
| --- | --- |
| `boolean`, `int`, `long`, ... | Tương ứng boxed `Boolean`, `Integer`, `Long` |
| `String` | `String` |
| `ObjectName` | `ObjectName` |
| `int[]`, `long[]` | Arrays nguyên thủy phù hợp |
| `String[]` | `String[]` |
| `List<String>` | `String[]` |
| `Set<String>` | Array của phần tử được hỗ trợ |
| `enum State {ACTIVE,...}` | `String` |
| `Map<String,Integer>` | `TabularData` |
| Một record có các components hợp lệ | `CompositeData` |
| JavaBean DTO có public getters hợp lệ | `CompositeData` nếu thỏa quy tắc |
| Một MXBean interface tham chiếu MXBean khác | `ObjectName` |

Các quy tắc đầy đủ nằm trong **Java SE 26 `javax.management.MXBean` specification**; **không phải Java type nào cũng tự chuyển được**. Với arrays/collections/maps, từng type parameter/item cũng phải convertible; với maps và sets có các ràng buộc bổ sung.

### 3.2. Record → CompositeData

Ví dụ record server:

~~~java
public record Snapshot(long processed, int waiting, String state) {}
~~~

Khi MXBean interface trả `Snapshot`, một client động gọi:

~~~java
// MẢNH MINH HỌA: name và connection đã xác định.
CompositeData snapshot = (CompositeData)
        connection.getAttribute(name, "Snapshot");

long processed = (Long) snapshot.get("processed");
int waiting = (Integer) snapshot.get("waiting");
String state = (String) snapshot.get("state");
~~~

`CompositeData` chứa các **item names** `processed`, `waiting`, `state`; không cần client biết Java class `Snapshot`.

**Java record mapping hiện hành:** các components được ánh xạ sang CompositeType khi tất cả components convertible; record được reconstruct qua **canonical constructor**, không cần gắn `@ConstructorProperties` để dùng trong typed proxy. Một record không có components không được MXBean mapping thành CompositeType theo quy tắc hiện hành.

### 3.3. Tại sao names khác nhau giữa MXBean attribute và DTO property?

Đây là hai lớp naming:

~~~text
MXBean method getSnapshot()    → JMX attribute "Snapshot"
Record component processed()   → CompositeData item "processed"
Record component waiting()     → CompositeData item "waiting"
Record component state()       → CompositeData item "state"
~~~

Trong MXBean interface, `getSnapshot()` tạo attribute `Snapshot` **viết hoa S**. Trong CompositeData, property của record `processed` **viết thường p**. Viết `getAttribute(name,"snapshot")` sai case có thể gây `AttributeNotFoundException`.

Với JavaBean DTO, getter `getProcessed()` cũng trở thành composite item `processed`; tên field property của DTO không đồng nhất với JMX attribute name của interface.

### 3.4. Map → TabularData

~~~java
// Phía server:
Map<String, Integer> getCounters();
~~~

Ở phía client động:

~~~java
// MẢNH MINH HỌA:
TabularData table = (TabularData)
        connection.getAttribute(name, "Counters");

CompositeData row = table.get(new Object[] {"success"});
Integer value = (Integer) row.get("value");
~~~

`Map<K,V>` được ánh xạ thành `TabularType` với **hai columns** `key` và `value`, **index** là `key`. Tất cả keys/values phải chuyển được sang Open Types.

`TabularData.get(new Object[]{"success"})` trả đúng hàng có key `"success"` hoặc null; không gọi `row.get("value")` trước khi kiểm tra null nếu input không chắc chắn.

**Map thường không bảo đảm một thứ tự iteration có ý nghĩa nghiệp vụ.** Nếu muốn biểu đồ có sorting hoặc stable display order, hãy sắp xếp ở client thay vì giả định TabularData giữ thứ tự Map.of.

### 3.5. List và Set → arrays

~~~java
// Phía server:
List<String> getLabels();
~~~

Qua raw MBeanServerConnection:

~~~java
String[] labels = (String[]) connection.getAttribute(name, "Labels");
~~~

MXBean mapping chuyển `List<String>` thành mảng `String[]` khi đi qua Open Data. Không cast raw attribute sang `List<String>` nếu đọc bằng `getAttribute` (khác với typed MXBean proxy).

Đối với Set/SortedSet, mapping cũng theo array tương ứng nhưng còn các ràng buộc reconstructible/comparable/comparator theo spec. Đừng dùng các collection tùy ý như `Queue<OpaqueObject>` rồi mong MXBean tự serialize được.

### 3.6. Enum → String

~~~java
public enum State { ACTIVE, PAUSED }

// MXBean interface:
State getState();
~~~

Raw client nhận:

~~~java
String state = (String) connection.getAttribute(name, "State");
~~~

`enum` được ánh xạ sang **String tên constant**, không phải client-side `State` enum class. Khi dựng typed proxy cùng interface, framework có thể chuyển String trở lại enum tương ứng.

**Versioning:** nếu đổi tên/xóa constant, typed proxies cũ có thể không reconstruct được. Generic clients cũng cần logic đối phó state mới, chẳng hạn hiển thị `UNKNOWN` thay vì crash khi nhận giá trị chưa biết.

### 3.7. OpenType metadata nằm ở đâu?

Mỗi MXBean có thể được inspect qua:

~~~java
MBeanInfo info = connection.getMBeanInfo(name);
MBeanAttributeInfo attr = ...; // Tìm attribute tên "Snapshot".
Object type = attr.getDescriptor().getFieldValue(JMX.OPEN_TYPE_FIELD);
boolean composite = type instanceof CompositeType;
~~~

Trường descriptor **`JMX.OPEN_TYPE_FIELD`** tương ứng **`openType`**, mô tả OpenType dùng cho attribute. Những trường như **`originalType`** và **`mxbean`** cũng có thể xuất hiện theo metadata. Hãy dựa trên MBeanInfo/descriptor và kiểm tra null/kiểu, không tự đoán schema chỉ từ tên.

**Metadata không tương đương quyền truy cập.** Một MBean có operation hay attribute được công bố vẫn cần JMX connector security/authorization riêng nếu cho kết nối từ xa.

---

## 4. Ví dụ Java 17+: Server có DTO riêng, client chỉ cần Open Data

Ví dụ dưới đây được chia làm **hai file nguồn thật sự**, biên dịch riêng để chứng minh client **không phải import class ứng dụng**. Các source codes dùng JDK chuẩn và một MBeanServer **local, isolated, không mở mạng**.

### 4.1. Ý tưởng kiểm chứng

**Server:**
- Khai báo `@MXBean public interface QueueView` dù tên không kết thúc bằng `MXBean`.
- Trả một **record `Snapshot`** từ `getSnapshot()`.
- Trả `Map<String,Integer>` từ `getCounters()`.
- Trả `List<String>` từ `getLabels()`.
- Trả enum `State` từ `getState()`.
- Có operation `markProcessed(int delta)` với validation.
- Register service dưới `ObjectName("demo.management:type=Queue,name=primary")`.
- Dùng `JMX.newMXBeanProxy` ở cùng module để cho thấy typed mapping có thể reconstruct record.
- Unregister bean ở `finally`.

**Generic client:**
- Không import `QueueView`, `Snapshot`, `QueueService`, `State` hay bất kỳ model class của service.
- Chỉ cần `MBeanServerConnection` và `ObjectName` từ caller.
- Dùng `getMBeanInfo` + descriptor `openType` khám phá schema.
- Dùng `getAttribute` nhận `CompositeData`, `TabularData`, `String[]`, String/Long.
- Dùng `invoke` với method name và signature chuẩn.
- Được **biên dịch trước** khi server source được biên dịch.

**Giới hạn có chủ đích:** Đây là minh họa JMX local API; **không tạo RMI connector, không mở port/remote JMX hoặc cho truy cập từ xa**. `markProcessed` là operation demo sửa counter in-memory, không tác động database/queue thật.

### 4.2. File 1 — `client/GenericMxClient.java`

~~~java
import java.util.Arrays;
import javax.management.Attribute;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.JMX;
import javax.management.openmbean.CompositeData;
import javax.management.openmbean.CompositeType;
import javax.management.openmbean.TabularData;

public final class GenericMxClient {
    // This file compiles with JDK classes only.
    // It does not import or know the server's MXBean interface or DTO.
    private GenericMxClient() {}

    public static void readWithoutApplicationClasses(
            MBeanServerConnection connection, ObjectName name)
            throws Exception {
        MBeanInfo info = connection.getMBeanInfo(name);
        MBeanAttributeInfo snapshotAttribute = Arrays.stream(info.getAttributes())
                .filter(a -> a.getName().equals("Snapshot"))
                .findFirst().orElseThrow();
        Object openType = snapshotAttribute.getDescriptor()
                .getFieldValue(JMX.OPEN_TYPE_FIELD);
        System.out.println("snapshotSchemaIsComposite="
                + (openType instanceof CompositeType));

        CompositeData snapshot = (CompositeData) connection.getAttribute(
                name, "Snapshot");
        System.out.println("snapshot=processed=" + snapshot.get("processed")
                + ",waiting=" + snapshot.get("waiting")
                + ",state=" + snapshot.get("state"));

        TabularData counters = (TabularData) connection.getAttribute(
                name, "Counters");
        System.out.println("counterRows=" + counters.size());
        CompositeData success = counters.get(new Object[] {"success"});
        System.out.println("counterSuccess=" + success.get("value"));

        String[] labels = (String[]) connection.getAttribute(name, "Labels");
        System.out.println("labels=" + Arrays.toString(labels));

        String state = (String) connection.getAttribute(name, "State");
        System.out.println("stateOpenTypeString=" + state);

        boolean operationPresent = Arrays.stream(info.getOperations())
                .anyMatch(a -> a.getName().equals("markProcessed"));
        System.out.println("operationAvailable=" + operationPresent);

        connection.invoke(name, "markProcessed", new Object[] {3},
                new String[] {"int"});
        long after = (Long) connection.getAttribute(name, "Processed");
        System.out.println("processedAfterInvocation=" + after);

        CompositeData afterSnapshot = (CompositeData) connection.getAttribute(
                name, "Snapshot");
        System.out.println("snapshotAfter=" + afterSnapshot.get("processed"));
    }
}
~~~

**Giải thích:** File client **không có compile-time dependency vào server model**. `CompositeData` và `TabularData` đến từ `javax.management.openmbean`; `MBeanServerConnection`/`MBeanInfo` đến từ Java JMX API. Client vẫn đang biết **contract name** `Snapshot`, `Counters`, `Labels`, `State`, `Processed` và operation `markProcessed`: “không cần class” không phải “không cần schema”.

`import javax.management.Attribute` trong file không được sử dụng; nó không ảnh hưởng kết quả. Trong project thực, nên xóa unused imports bằng formatter/linter theo convention.

### 4.3. File 2 — `server/MxBeanIndependentDemo.java`

~~~java
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;
import javax.management.JMX;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.MXBean;
import javax.management.ObjectName;

public final class MxBeanIndependentDemo {
    public enum State { ACTIVE, PAUSED }

    public record Snapshot(long processed, int waiting, String state) {}

    // Annotation enables MXBean semantics even without the name suffix.
    @MXBean
    public interface QueueView {
        Snapshot getSnapshot();
        List<String> getLabels();
        Map<String, Integer> getCounters();
        State getState();
        long getProcessed();
        void markProcessed(int delta);
    }

    public static final class QueueService implements QueueView {
        private final AtomicLong processed = new AtomicLong(7);

        @Override
        public Snapshot getSnapshot() {
            return new Snapshot(processed.get(), 2, State.ACTIVE.name());
        }

        @Override
        public List<String> getLabels() {
            return List.of("region=local", "service=queue");
        }

        @Override
        public Map<String, Integer> getCounters() {
            return Map.of("success", (int) processed.get(), "failure", 1);
        }

        @Override
        public State getState() {
            return State.ACTIVE;
        }

        @Override
        public long getProcessed() {
            return processed.get();
        }

        @Override
        public void markProcessed(int delta) {
            if (delta <= 0 || delta > 1000) {
                throw new IllegalArgumentException("delta out of range");
            }
            processed.addAndGet(delta);
        }
    }

    public static void main(String[] args) throws Exception {
        MBeanServer server = MBeanServerFactory.newMBeanServer("example");
        ObjectName name = new ObjectName(
                "demo.management:type=Queue,name=primary");
        QueueService service = new QueueService();
        server.registerMBean(service, name);
        try {
            System.out.println("registered=" + server.isRegistered(name));
            System.out.println("mxbeanInterface=" +
                    JMX.isMXBeanInterface(QueueView.class));
            GenericMxClient.readWithoutApplicationClasses(server, name);
            QueueView typed = JMX.newMXBeanProxy(server, name, QueueView.class);
            System.out.println("typedProxyProcessed="
                    + typed.getSnapshot().processed());
        } finally {
            server.unregisterMBean(name);
        }
        System.out.println("removed=" + !server.isRegistered(name));
    }
}
~~~

**Lưu ý:** `QueueService` giữ `AtomicLong` vì cùng một MXBean có thể bị nhiều management callers truy cập. `getSnapshot()` tạo một record giá trị tại thời điểm gọi và không trả reference tới internal mutable queue. Các fields `waiting=2` và `State.ACTIVE` là dữ liệu giả. Phép ép `(int)processed.get()` của demo chỉ an toàn vì counter nhỏ; production phải tránh **narrowing overflow** hoặc dùng `Map<String,Long>`.

### 4.4. Biên dịch client trước, không có server classes

Tạo đúng thư mục:

~~~text
mxbean-example/
├── client/
│   └── GenericMxClient.java
└── server/
    └── MxBeanIndependentDemo.java
~~~

**Linux/macOS (bash, `:` là dấu ngăn cách classpath):**

~~~bash
mkdir -p client server

# Biên dịch hoàn toàn riêng GenericMxClient, chỉ có JDK APIs.
javac -encoding UTF-8 --release 17 \
      -d client client/GenericMxClient.java

# Sau đó mới biên dịch server, server có thể gọi client demo.
javac -encoding UTF-8 --release 17 \
      -cp client -d server server/MxBeanIndependentDemo.java

java -cp "server:client" MxBeanIndependentDemo
~~~

**Windows PowerShell (`;` là dấu ngăn cách classpath):**

~~~powershell
New-Item -ItemType Directory -Force client,server | Out-Null
javac -encoding UTF-8 --release 17 -d client client/GenericMxClient.java
javac -encoding UTF-8 --release 17 -cp client -d server server/MxBeanIndependentDemo.java
java -cp "server;client" MxBeanIndependentDemo
~~~

Trong code thật, **generic client nên chạy trong một process riêng** và dùng JMX connector được bảo vệ để lấy `MBeanServerConnection`. Demo ghép hai file vào cùng process **chỉ để chứng minh Open Data mapping mà không cần cấu hình mạng**. Việc compile client thành công trước server chứng minh chiều phụ thuộc source code: client không cần domain classes.

### 4.5. Stdout chính xác đã kiểm chứng (13 dòng)

~~~text
registered=true
mxbeanInterface=true
snapshotSchemaIsComposite=true
snapshot=processed=7,waiting=2,state=ACTIVE
counterRows=2
counterSuccess=7
labels=[region=local, service=queue]
stateOpenTypeString=ACTIVE
operationAvailable=true
processedAfterInvocation=10
snapshotAfter=10
typedProxyProcessed=10
removed=true
~~~

**Đã kiểm thử thực tế:** `javac 24.0.2`, biên dịch mỗi file bằng `--release 17`, client compile thành công **không có classes của server**, sau đó chạy chương trình và so khớp chính xác **13 dòng stdout**. Không bật cổng JMX từ xa, không yêu cầu database hay dependency ngoài JDK.

### 4.6. Giải thích kết quả

- **`registered=true`**: service đã được đăng ký dưới ObjectName theo yêu cầu.
- **`mxbeanInterface=true`**: annotation `@MXBean` biến `QueueView` thành management interface dù không có suffix.
- **`snapshotSchemaIsComposite=true`**: descriptor `openType` cho attribute Snapshot là CompositeType.
- **`snapshot=processed=7,waiting=2,state=ACTIVE`**: generic client nhận `CompositeData` và đọc properties mà không có `Snapshot` class.
- **`counterRows=2`, `counterSuccess=7`**: Map server chuyển thành TabularData gồm key/value rows.
- **`labels=[region=local, service=queue]`**: List server chuyển thành String[] khi lấy bằng raw getAttribute.
- **`stateOpenTypeString=ACTIVE`**: enum server chuyển thành String.
- **`operationAvailable=true`**: `MBeanInfo.getOperations()` công bố markProcessed.
- **`processedAfterInvocation=10`**: client JDK-only gọi operation với tham số nguyên `3`, counter đổi từ 7 thành 10.
- **`snapshotAfter=10`**: snapshot kế tiếp phản ánh giá trị mới.
- **`typedProxyProcessed=10`**: nếu client có interface/DTO, `JMX.newMXBeanProxy` có thể reconstruct record và truy cập typed.
- **`removed=true`**: unregister hoàn tất; không để lại MBean trong isolated registry.

**Đừng diễn giải `generic client can invoke` thành “an toàn cho mọi caller”.** Demo không bật remote connector. Production phải phân quyền và giới hạn những operations có side effects.

---

## 5. Generic client độc lập như thế nào?

### 5.1. Không import service model

Một client động cần biết:

- Nơi lấy `MBeanServerConnection`: local hoặc connector đã xác thực.
- `ObjectName` của MXBean hoặc query pattern được phép.
- Những attributes/operations cần khám phá và đọc.
- Các OpenType contracts, item names và units/semantics.

Nó **không cần**:

- Có class `MxBeanIndependentDemo$Snapshot` để cast.
- Import `QueueService` hay khởi tạo server implementation.
- Import `QueueView` nếu chỉ dùng `getAttribute`/`invoke`.
- Deserialize tùy ý một Java object graph từ server.

**Lưu ý:** Sự độc lập classpath chỉ giải quyết kiểu dữ liệu khi trao đổi qua JMX. Nếu client viết code `snapshot.get("processed")`, nó vẫn phụ thuộc **semantic schema** có tên `processed`. Đổi field name hay units có thể phá client dù không thay Java class.

### 5.2. Khám phá ObjectName an toàn

~~~java
// MẢNH MINH HỌA, connection là MBeanServerConnection đã có.
javax.management.ObjectName query =
        new javax.management.ObjectName(
                "demo.management:type=Queue,*");

java.util.Set<javax.management.ObjectName> names =
        connection.queryNames(query, null);
~~~

Một management tool có thể liệt kê các MBeans phù hợp pattern. Nhưng kết quả không cố định; tùy ObjectNames đăng ký và permissions của connector. Không dùng `queryNames(null,null)` trên server lớn nếu không cần vì có thể trả nhiều MBeans và gây overhead.

### 5.3. Đọc schema trước khi cast

~~~java
// MẢNH MINH HỌA:
MBeanInfo info = connection.getMBeanInfo(name);
for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.println(attr.getName() + ":" + attr.getType());
}
~~~

Với MXBean, `getType()` có thể phản ánh Open Data class name; descriptors cung cấp `openType` và `originalType` giúp kiểm tra schema. Không cast trùm mọi attribute sang CompositeData: một String vẫn là String, List có thể là array, Map có thể là TabularData.

Một generic client thật nên **dispatch theo runtime type**:

~~~text
Simple value → String / Long / Integer / Boolean...
Array       → Object array hoặc primitive array tương ứng
Composite   → CompositeData.getCompositeType().keySet()
Tabular     → TabularData.getTabularType(), key/index columns
ObjectName  → tham chiếu tới MXBean khác, cần lookup có kiểm soát
~~~

Khi nhận field type bất ngờ, client cần báo **SCHEMA_MISMATCH** hoặc hiển thị an toàn, không silently cast thành một kiểu sai.

### 5.4. `JMX.newMXBeanProxy` không phải class-free client

~~~java
// MẢNH MINH HỌA:
QueueView proxy =
        JMX.newMXBeanProxy(connection, name, QueueView.class);
Snapshot snapshot = proxy.getSnapshot();
~~~

Dạng proxy này cần interface `QueueView` cùng các kiểu Java liên quan, có thể bao gồm `Snapshot`, nằm trên classpath **của client typed**. MXBean framework chuyển Open Data trở lại Java model types theo mapping rule.

**So sánh:**

| Cách gọi | Client cần server-specific classes? | Giá trị nhận |
| --- | --- | --- |
| Raw `getAttribute(...,"Snapshot")` | **Không** | `CompositeData` |
| Raw `getAttribute(...,"Counters")` | **Không** | `TabularData` |
| Raw `getAttribute(...,"Labels")` | **Không** | `String[]` |
| Raw `getAttribute(...,"State")` | **Không** | `String` |
| Raw `invoke(...,"markProcessed",...)` | **Không**, nhưng biết signature/schema | Open Data return value |
| `JMX.newMXBeanProxy(...,QueueView.class)` | **Có interface và DTO thích hợp** | `Snapshot`, Map, List, enum typed |

Không dùng `JMX.newMBeanProxy` thay cho `newMXBeanProxy` khi cần chuyển đổi typed giữa Open Data và Java model classes; hai factory methods phục vụ interfaces khác nhau.

### 5.5. Có phải mọi Java object đều trở thành Open Data?

**Không.** MXBean specification có quy tắc hạn chế:

- Một Java type phải có cách ánh xạ thành OpenType hợp lệ.
- Một phương thức **nhận tham số** cần type có thể **reconstruct** từ Open Data.
- Khi typed proxy chuyển **return value** trở lại Java type, return type cũng cần reconstructible.
- Record phải có các components convertible và canonical constructor phù hợp.
- JavaBean DTO cần public getters có kiểu convertible và quy tắc khởi tạo phù hợp nếu cần reconstruct.
- `List<E>`, `Set<E>`, `Map<K,V>` cần nested types convertible, một số collection contracts có điều kiện Comparable/comparator.
- Không expose raw `Object`, runtime-specific stream, connection/socket, arbitrary graph hay domain entity với cycles chỉ vì code compile được.
- Các generic types khó hoặc không reconstructible có thể gây `NotCompliantMBeanException` khi đăng ký hoặc conversion errors khi gọi.

**Thiết kế contract Open Data trước, rồi chọn Java model phù hợp**, không đảo ngược bằng cách expose toàn bộ domain aggregate.

---

## 6. Record và JavaBean DTO: reconstructibility

### 6.1. Record thích hợp cho snapshot

~~~java
// MẢNH MINH HỌA Java 17+:
public record HealthSnapshot(
        long timestampEpochMillis,
        int activeWorkers,
        String phase) {}
~~~

Ưu điểm:

- Bất biến theo component values (nhưng tránh nested mutable references).
- Tên field/components thể hiện schema rõ.
- MXBean mapping records tạo **CompositeData** và typed proxy có thể dùng **canonical constructor**.
- Không cần `@ConstructorProperties` cho record như JavaBean DTO.
- Tránh đẩy entity có kết nối/database/session internal ra khách quản trị.

**Không phải tất cả records đều convertible**: nếu component là một kiểu không thể mapping, cả record có thể không map được. DTO fields nên tối giản và có units rõ.

### 6.2. JavaBean DTO còn được hỗ trợ

~~~java
// MẢNH MINH HỌA DTO theo getter:
public final class QueueHealth {
    private final long processed;
    private final String phase;

    @java.beans.ConstructorProperties({"processed", "phase"})
    public QueueHealth(long processed, String phase) {
        this.processed = processed;
        this.phase = phase;
    }

    public long getProcessed() { return processed; }
    public String getPhase() { return phase; }
}
~~~

Framework có thể map từ `getProcessed()/getPhase()` thành CompositeData items `processed` và `phase`. `@ConstructorProperties` hoặc `@javax.management.ConstructorParameters` là một trong các cách reconstruct đối tượng Java khi typed proxy cần nó.

**Lưu ý:** Không đưa một class DTO chỉ có private fields, không public getters hoặc unsupported getters rồi kỳ vọng MXBean nhìn thấy schema. Không coi `Serializable` là điều kiện bắt buộc của MXBean model types; Open Data mapping là cơ chế riêng.

### 6.3. Vì sao getter nên cung cấp snapshot nhất quán?

Giả sử service có hai counters `processed` và `waiting` thay đổi cùng lúc. Nếu client gọi hai attributes riêng biệt, nó có thể đọc:

~~~text
T1: Processed=10
T2: service tiếp nhận job mới
T3: Waiting=12
~~~

Hai con số đến từ hai thời điểm khác nhau. Một `getSnapshot()` duy nhất có thể tạo **coherent point-in-time view** bằng lock/snapshot mechanism phù hợp.

**Nhưng một record không tự tạo tính nhất quán giữa hai biến mutable khác nhau.** `new Snapshot(a.get(), b.get(),...)` vẫn có thể đọc chúng tại hai thời điểm. Nếu cần invariant chặt chẽ, phải có synchronization/immutable state snapshot hoặc cơ chế atomic publication thực sự.

Demo có một counter `AtomicLong` và `waiting=2` cố định nên không gặp vấn đề cross-counter consistency.

---

## 7. Versioning: client không có class vẫn cần một schema ổn định

### 7.1. Tách backward compatibility khỏi Java class names

Một generic client có thể đọc mọi CompositeData có item names hợp lệ, nhưng nếu server đổi:

~~~text
Trước:
  Snapshot.processed = Long (count)
  Snapshot.waiting = Integer (count)

Sau:
  Snapshot.completed = Long (count)
  Snapshot.waiting = String ("many")
~~~

Code cũ `snapshot.get("processed")` hoặc cast `Integer waiting` sẽ thất bại. Vì vậy **MXBean không tự giải quyết schema evolution**.

Nên đặt chính sách:

- Giữ tên attributes và CompositeData item names ổn định.
- Không đổi type/units âm thầm; ví dụ milliseconds → seconds sẽ phá logic dù vẫn là `long`.
- Tránh xóa/đổi tên enum constants mà typed clients cũ đang dùng.
- Nếu thêm fields, cho generic clients **ignore unknown fields** nếu phù hợp.
- Với typed proxy DTO, kiểm thử reconstructibility qua phiên bản khác.
- Nếu thay đổi không tương thích, dùng **ObjectName/versioned interface** có chủ đích hoặc quá trình migration.
- Giữ bảng attributes, units, semantics, nullability, update frequency và permission docs.
- Có integration tests giữa client cũ và server mới.

### 7.2. Units và timestamps

Management counters nên dùng các đơn vị rõ:

~~~text
ProcessedCount       → events (long)
QueueDepth           → items (int)
LastUpdateEpochMillis → milliseconds since Unix epoch (long)
DurationNanos        → elapsed nanoseconds (long)
Phase                → enum/state as String open data
~~~

Tránh trả `java.time.Instant`/custom timezone objects tùy ý mà không xác minh mapping; các kiểu nguyên thủy hoặc record với units rõ dễ tương thích với generic client và monitoring collectors.

**Không dùng ngày giờ của server như bằng chứng thời gian tuyệt đối không thể sai**; clocks giữa JVMs có thể lệch. Để đo duration trong cùng JVM, `System.nanoTime()` phù hợp hơn wall-clock epoch.

### 7.3. `CompositeData` có schema runtime

Một client có thể tự kiểm tra:

~~~java
// MẢNH MINH HỌA:
CompositeType type = snapshot.getCompositeType();
for (String key : type.keySet()) {
    Object value = snapshot.get(key);
    // Ghi/hiển thị theo policy, không dump secrets.
}
~~~

Nhờ đó client biết những item names hiện có mà không phải compile DTO. Khi cần hình thành dashboard cố định, hãy giữ contract có version để các charts/alerts không thay đổi nghĩa tùy server.

---

## 8. Quản trị dữ liệu không đồng nghĩa quản trị quyền truy cập

### 8.1. Expose ít nhất cần thiết

MXBean attributes thường được gọi bởi diagnostics/monitoring clients; đó là một bề mặt quản trị có thể rất nhạy cảm. Không expose:

- Raw API keys, passwords, tokens, cookies, database connection strings.
- Full HTTP headers, session objects, user identities nếu không có privacy policy.
- Toàn bộ queue payload/PII/transaction IDs tùy ý.
- Paths/secrets/SSL private-key material.
- File handles, open sockets, arbitrary object references.
- Một operation như `setAdminRole`, `downloadAllCustomers` chỉ vì nó là Java method của service.

`getSnapshot` nên trả **counters và state đã được tổng hợp/sanitized**; không trả domain entities chưa được kiểm tra.

### 8.2. Raw MBeanServerConnection có quyền gọi operation

Trong demo, generic client không biết class của service nhưng vẫn gọi:

~~~java
connection.invoke(name, "markProcessed",
        new Object[]{3},
        new String[]{"int"});
~~~

Điều này chứng minh **không cần Java class không đồng nghĩa chỉ được read-only**. Nếu connector cấp quyền gọi operation, client có thể thay đổi state.

**Production:** phân biệt quyền **read monitoring** với quyền **invoke management operations**. JMX remote connector phải có authentication, authorization, TLS/network restrictions theo môi trường. Không mở JMX remote port công khai, không tắt auth/SSL cho tiện.

### 8.3. Demo không sử dụng remote JMX

Mã chạy:

~~~java
MBeanServer server = MBeanServerFactory.newMBeanServer("example");
~~~

MBeanServer là registry nội bộ, không tự mở TCP port. Nếu muốn kết nối remote qua **JMXConnector**, cần chủ động cấu hình connector và bảo mật, trong đó có credential transport, access control và firewall. **Không sao chép các flags vô hiệu hóa authentication/SSL từ bài hướng dẫn cũ vào production.**

Một generic client dùng `MBeanServerConnection` trên remote hoặc local theo API giống nhau về mặt đọc/ghi, nhưng transport/error conditions khác nhau: timeout, authentication, network failure, reconnect và ObjectName lifecycle.

### 8.4. Phân quyền theo action

| Operation/attribute | Ai thường cần | Chính sách |
| --- | --- | --- |
| Read queue depth | Metrics collector, operator | Read-only, rate-limited |
| Read aggregate counts | Dashboard | No PII, low overhead |
| Read status | Health monitoring | Stable schema |
| Change limit | Operator đã cấp quyền | Audit, bounds validation |
| Pause service | Administrator | Authz, change control |
| Clear queue/retry tasks | Administrator rất hạn chế | Idempotency/impact guard |
| Expose secrets | Không nên có | Không xuất qua MXBean |

Nếu hệ thống quan sát cần gọi raw `getAttribute`, nó không phải lý do cấp quyền `invoke` trên toàn bộ MBeanServer.

### 8.5. Operation cần validate inputs

`markProcessed(int delta)` trong demo có:

~~~java
if (delta <= 0 || delta > 1000) {
    throw new IllegalArgumentException("delta out of range");
}
processed.addAndGet(delta);
~~~

Input `3` là giả để thấy counter đổi 7→10. Với production, management operation phải kiểm tra bounds, identity, policy, conflict/idempotency, không được block vô hạn hoặc tạo resource leak.

---

## 9. Hiệu năng, concurrency và observability

### 9.1. `getAttribute` có thể chạy code của bạn

Khi một monitoring collector gọi `getAttribute(name,"Snapshot")`, JMX introspection có thể gọi method `getSnapshot()` do bạn viết. Đó **không phải một phép đọc field miễn phí**. Nếu getter gọi database lớn, network, lock lâu hoặc duyệt hàng triệu queue items, collector có thể làm ảnh hưởng service.

**Nguyên tắc:**
- Getter nhẹ và không làm side effects.
- Trả cached/aggregated snapshots nếu tính toán tốn kém.
- Không trả unbounded `List`/Map; có quotas.
- Không khóa tài nguyên nóng quá lâu.
- Giới hạn call frequency/parallelism theo cấu hình quản trị.
- Metrics có timestamp/quality flag nếu data cache bị stale.

### 9.2. Thread safety

Một MXBean có thể bị gọi đồng thời bởi nhiều threads/callers. Dùng `AtomicLong` cho các counters đơn giản như demo. Với state phức tạp, sử dụng immutable state snapshots, locks được thiết kế tốt hoặc event counters phù hợp.

**Không trả trực tiếp mutable collections** chứa state nội bộ. Java MXBean mapping có thể chuyển đổi data, nhưng getters vẫn phải lấy một snapshot hợp lệ trong môi trường đồng thời.

### 9.3. Snapshot consistency

Nếu muốn báo `processed`, `failed`, `inFlight`, `queueDepth` và timestamp nhất quán, nên tạo một record được cập nhật/đọc **trong cùng một critical section hoặc immutable publication boundary**. Nhiều `getAttribute` độc lập sẽ không đảm bảo các values thuộc một thời điểm.

Bản thân việc CompositeData gộp fields **không bảo đảm tính nguyên tử** nếu getter lấy thông tin từ nhiều mutable objects không đồng bộ.

### 9.4. Kiểu dữ liệu quá lớn

Một `Map<String, List<Record>>` có thể convert thành TabularData/CompositeData lồng nhau, nhưng nếu chứa hàng trăm nghìn entries, nó sẽ làm tăng allocations, CPU/JMX payload và timeout. Với dữ liệu quản trị:

- Dùng aggregates (counts/histograms) thay vì raw payload.
- Có limit/maxRows rõ.
- Dùng String codes thay vì objects khó convert.
- Có pagination khi dùng một API thích hợp; MXBean có thể không phải chỗ tốt cho data dumps lớn.
- Tránh long-running operation trên management thread.

### 9.5. `MBeanInfo` và versioned schema cache

Client có thể cache metadata để giảm lookup, nhưng phải refresh khi MBean bị unregister/re-register hoặc schema thay đổi. Một ObjectName có thể được dùng lại bởi bean phiên bản mới; **ObjectName giống nhau không đồng nghĩa schema hoàn toàn giống nhau**.

---

## 10. Những lỗi thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Viết Standard MBean trả DTO tùy ý rồi mong generic client không cần class | Standard MBean không tự đảm bảo MXBean open mapping | Dùng MXBean interface |
| Gắn `@MXBean` lên class thay vì public interface | Không tạo interface contract như mong đợi | Annotate public interface |
| Đặt interface không public/không đúng convention | JMX có thể không nhận là MXBean | Public interface hoặc @MXBean |
| Dùng `Object`/domain aggregate arbitrary | Không có conversion/reconstructibility chắc chắn | DTO/OpenType-compatible types |
| Trả DTO có getters không convertible | Mapping thất bại | Giữ fields đơn giản |
| Đổi item name mà không version | Generic clients cũ fail | Stable schema/compat tests |
| Đổi enum constant không migration | Typed proxy/client cũ không hiểu | Versioned/state fallback |
| Bắt buộc client import Snapshot để đọc | Mất lợi ích generic interoperability | MBeanServerConnection + CompositeData |
| Cast getAttribute("Snapshot") sang Snapshot | Runtime trả CompositeData | Cast CompositeData |
| Cast List getter sang List | Raw MXBean mapping trả array | Cast String[]/appropriate array |
| Cast Map getter sang Map | Raw MXBean mapping trả TabularData | Cast TabularData |
| Cast enum getter sang enum | Raw mapping trả String | Cast String |
| Nhầm Snapshot với snapshot | Case-sensitive attribute names | Đọc MBeanInfo |
| Sai method signature khi invoke | ReflectionException/operation lookup fail | Dùng `"int"` cho int |
| Tưởng MBeanInfo metadata bảo đảm truy cập | Connector policy có thể từ chối | Authn/authz rõ |
| Đăng ký trùng ObjectName | InstanceAlreadyExistsException | Naming/lifecycle đúng |
| Không unregister MXBean | Stale registry/leak | Cleanup |
| Getter trả mutable internal list | Race/lộ state | Immutable/defensive snapshots |
| Dùng nhiều getter để lấy atomic snapshot | Dữ liệu khác thời điểm | Composite snapshot được đồng bộ |
| Getter query database nặng | Ảnh hưởng service latency | Cached metrics/limits |
| Mở JMX remote không auth/TLS | Rủi ro nghiêm trọng | Secure JMX |
| Cho generic client invoke operation nguy hiểm | Thiếu authorization | Least privilege |
| Log secrets qua JMX attrs | Lộ dữ liệu nội bộ | Redaction/minimal exposure |
| Không test client-server version mismatch | Break schema | Compatibility matrix |
| Diễn giải “class-free” là “schema-free” | Client vẫn cần item names/units | Document OpenData contract |

### 10.1. `NotCompliantMBeanException` khi đăng ký

Nguyên nhân phổ biến:

- Không có public management interface hợp lệ.
- Interface không được nhận dạng là MXBean hoặc Standard MBean.
- Type trong interface không convertible.
- Method parameters không reconstructible.
- Getter/setter names clash hoặc generic/type mapping không hợp lệ.
- Implementation không đúng interface.

Hướng xử lý: kiểm tra `@MXBean`/suffix, public visibility, signatures, type mapping và `MBeanServer.registerMBean` trong unit test trước khi deploy. Không dùng catch rồi bỏ và “giả định MXBean đã chạy”.

### 10.2. `AttributeNotFoundException`

Có thể do:

~~~java
// Sai: "snapshot" viết thường.
connection.getAttribute(name, "snapshot");

// Đúng cho getSnapshot().
connection.getAttribute(name, "Snapshot");
~~~

Tránh hardcode đoán tên theo camelCase; dùng `getMBeanInfo` và contract/version.

### 10.3. `ClassCastException` tại generic client

Nếu client cast `getAttribute("Counters")` sang `Map`, trong khi Open Data là `TabularData`, sẽ lỗi. Tương tự cast `Snapshot` sang server record hoặc `Labels` sang List. Dùng MXBean mapping table và metadata.

### 10.4. `ReflectionException` hoặc `MBeanException` khi invoke

Raw `invoke` dùng method name, arguments và signature; nếu sai `"int"` thành `"java.lang.Integer"`, có thể không tìm đúng operation. Nếu implementation ném exception, JMX có thể wrap theo API. Client cần phân biệt request invalid, permissions và internal error; không dump secrets/stack trace ra public logs.

---

## 11. Kiểm thử mà không cần server domain classes ở client

### 11.1. Unit test server mapping

- Đăng ký MBean dưới ObjectName test.
- Dùng `getMBeanInfo` kiểm tra attributes/operations.
- Kiểm tra descriptor `openType` cho Snapshot là CompositeType.
- `getAttribute("Snapshot")` trả CompositeData và `processed/waiting/state` đúng.
- `getAttribute("Counters")` trả TabularData, có rows key/value đúng.
- `getAttribute("Labels")` trả `String[]`.
- `getAttribute("State")` trả String.
- Raw `invoke(..., "markProcessed", int)` cập nhật state.
- Typed proxy cùng interface có thể reconstruct record.
- Unregister sau test, no leaked ObjectName.

### 11.2. Unit test khách độc lập

**Biên dịch GenericMxClient trước server** như trong ví dụ. Một CI job có thể giữ GenericMxClient như artifact riêng, build chỉ với JDK/management API mà **không có JAR của server**. Test đảm bảo client không compile-time import DTO.

Ở runtime, dùng `MBeanServerConnection`/fake fixture hoặc một JMX service test. Assertions tập trung vào **Open Data** thay vì Java record type của service.

### 11.3. Negative tests không phụ thuộc network

| Test | Input | Expected |
| --- | --- | --- |
| Attribute tên sai | `"snapshot"` thay `"Snapshot"` | AttributeNotFoundException |
| Bean chưa đăng ký | ObjectName không tồn tại | InstanceNotFoundException |
| Invoke sai signature | `"java.lang.Integer"` thay `"int"` | Operation lookup failure |
| `getAttribute` sai cast | Cast CompositeData thành Snapshot | ClassCastException |
| Server DTO có unsupported component | Registration/conversion failure | Không nhận như MXBean hợp lệ |
| Duplicate ObjectName | Register bean thứ hai cùng name | InstanceAlreadyExistsException |
| Read after unregister | gọi lại ObjectName | InstanceNotFoundException |
| Invalid delta | markProcessed(0) | Implementation reject; JMX exception wrapping |
| No OpenType descriptor | Client thấy metadata không phù hợp | Fail schema validation |
| New CompositeData item | Server thêm property | Generic client cần tolerate nếu phù hợp |
| Removed/renamed item | Client cũ đọc name đã mất | Schema mismatch |
| Changed enum state | Server có constant mới | Generic client phải xử lý unknown |
| Concurrent invokes | Nhiều threads cập nhật counter | Counter/thread safety đúng |
| Getter throws | Service unavailable | Error response, không crash collector |
| Payload quá lớn | Map/record nhiều items | Quota/time limits |
| Remote connector refused | không authenticated | Từ chối, không fallback insecure |

Một số tests là **kế hoạch mở rộng**, không được mô tả như đã chạy trong demo 13 dòng.

### 11.4. Integration tests đa JDK

Dùng Java 17 và runtime production hiện hành để chạy mapping tests. Nếu hỗ trợ khách Java 17 kết nối server Java 26 hoặc ngược lại, thử **cross-version communication qua JMX connector được cấu hình an toàn** trong test environment.

Test:

- Open Type name/type/CompositeData keys.
- Reconstruct record khi typed proxy.
- Nullability của getter.
- List/Map conversion và các generic types.
- Enum state name changes.
- MBeanInfo descriptor fields.
- Remote errors, timeout/reconnect/authn/authz.
- Unregister/re-register ObjectName.
- Backwards-compatible schema additions.

### 11.5. Tránh so sánh `MBeanInfo.toString()` tuyệt đối

Metadata có thể mang descriptions/order/descriptors thay đổi giữa implementations/JDKs. Test nên **assert những fields có contract quan trọng** (attribute name/type, descriptor OpenType, operation signatures) thay vì so toàn bộ dump string không cần thiết.

### 11.6. Kiểm thử hiệu năng và security

- Getters có latency tối đa không ảnh hưởng service.
- Map/list sizes có quota.
- High-frequency polling không tạo GC pressure lớn.
- Unauthorized principals không thể invoke write operations.
- Schema không lộ credentials/PII.
- JMX remote connector chỉ tiếp cận từ mạng/quyền được phép.
- Server startup/shutdown/unregister không tạo stale MBeans.

---

## 12. Nâng cấp ví dụ cho ứng dụng thực

### 12.1. Sử dụng platform MBeanServer

Nếu muốn JConsole/JMC/management client nhận biết custom MXBean trong cùng JVM:

~~~java
// MẢNH MINH HỌA:
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
        "com.example.service:type=QueueMetrics,name=primary");
server.registerMBean(queueMetricsService, name);
~~~

Đoạn này không phải file runnable độc lập vì `queueMetricsService` cần implementation do ứng dụng cung cấp. Điều cần nhớ: **MBeanServer giữ các beans do bạn đăng ký**; việc cấp remote access vẫn là một bước bảo mật riêng.

### 12.2. Gói DTO và MXBean interface theo version

Nếu có typed clients, tạo một **management API module** gồm interface/DTO record versioned và kiểm thử compatibility. Nếu có generic clients, công bố Open Data contract theo `ObjectName`, attribute names, CompositeData item names, types, units, permissions.

Đừng bắt generic clients tải toàn bộ business JAR chỉ để giải mã thống kê.

### 12.3. Lưu ý JPMS

Trong ứng dụng modular, server/client cần module **`java.management`**:

~~~java
// MẢNH MINH HỌA cho module-info.java khi dùng JMX API:
module com.example.management {
    requires java.management;
}
~~~

Nếu code dùng `ManagementFactory` cũng nằm trong `java.management`, không phải mở một module mới. Đối với Java records/DTO qua reflection/JMX, kiểm tra **visibility/exports** cho public management interface/DTO theo JPMS ở module path; không suy tự động rằng mọi private package đều có thể expose ra JMX.

Trong demo chạy **classpath unnamed module**, nên không cần module-info.java; phần biên dịch Java 17 vẫn là cách chứng minh tính độc lập của client.

### 12.4. Notifications và event streams

JMX hỗ trợ **notifications** nếu implementation áp dụng NotificationBroadcaster/NotificationEmitter; có thể hữu ích khi trạng thái thay đổi. Nhưng notifications không tự tương đương một durable event queue, không đảm bảo mọi client nhận đủ events qua network failure nếu không có cơ chế riêng.

Với dữ liệu metrics liên tục, đôi khi một exporter/pull endpoint theo tiêu chuẩn monitoring phù hợp hơn việc mỗi client polling MXBean nặng. Chọn công cụ theo yêu cầu vận hành.

### 12.5. Khi nào không nên dùng MXBean?

- Truyền bulk domain records hoặc raw user data.
- Thực hiện REST/public API cho khách bên ngoài không có JMX tooling.
- Đẩy async jobs lớn/streaming messages.
- Chứa secrets hoặc remote management operations chưa phân quyền.
- Yêu cầu schema phức tạp/version negotiation tốt hơn một giao thức chuyên dụng.
- Tăng số lượng attributes/maps quá lớn hoặc dynamic ObjectNames không kiểm soát.

MXBean đặc biệt hợp cho **trạng thái JVM/component, counters, configuration readouts và vài operations quản trị đã kiểm soát**.

---

## 13. Bài tập tự luyện

1. Chạy hai file theo đúng thứ tự biên dịch client trước server; chỉ ra vì sao GenericMxClient không import service class.
2. Đổi name `QueueView` thành `QueueViewMXBean` và bỏ `@MXBean`, kiểm tra interface detection.
3. Đổi field `waiting` trong Snapshot thành `pending` và kiểm tra điều gì xảy ra ở generic client cũ.
4. Thêm `timestampEpochMillis` vào Snapshot; cập nhật mapping/documentation và test.
5. Thêm attribute `getWorkerNames()` trả `List<String>`, kiểm tra raw getAttribute có `String[]`.
6. Thêm Map<String,Long> stats, đọc qua TabularData.
7. Thử enum State thêm `DRAINING`, kiểm tra generic client đọc String và typed client nhận enum mới.
8. Viết một generic inspector lặp `MBeanInfo.getAttributes` và hiển thị OpenType metadata, không import domain DTO.
9. Viết generic `CompositeData` renderer lặp keys và sanitize values.
10. Viết renderer cho `TabularData`, tách key/value và không giả định row iteration order.
11. Thử `JMX.newMXBeanProxy` với interface có sẵn ở client, so sánh với raw getAttribute.
12. Thử `JMX.newMBeanProxy` trên cùng MXBean complex data, giải thích vì sao không phù hợp typed mapping.
13. Đổi method `markProcessed(int)` thành `markProcessed(long)` và quan sát raw invoke cần signature `"long"`.
14. Thử invalid delta=0, xác định exception contract/side effects.
15. Đăng ký hai MBeans cùng ObjectName và bắt InstanceAlreadyExistsException.
16. Unregister rồi gọi getAttribute lại, kiểm tra InstanceNotFoundException.
17. Trả DTO JavaBean có @ConstructorProperties thay record và kiểm tra typed proxy.
18. Tạo một DTO record chứa unsupported type, xác nhận registration/conversion failure.
19. Dùng một snapshot với hai counters mutable khác nhau, viết test race và thêm atomic publication.
20. Thêm staleSnapshotTimestamp và định nghĩa sampling period.
21. Thêm rate limiting cho read/invoke trên management boundary.
22. Thiết kế permissions READ vs INVOKE đối với JMX remote connector.
23. Tạo một mô hình DTO không chứa credentials/PII; kiểm thử redaction.
24. Dùng `ManagementFactory.getPlatformMBeanServer()` trong test process cô lập, đăng ký rồi unregister custom MXBean.
25. Chạy trên Java 17 và 26, đối chiếu Open Types của record/list/map/enum.
26. Viết integration test client JDK-only chạy ở một JVM khác qua connector **đã xác thực**.
27. Xây schema contract versioning và test client cũ khi server thêm field mới.
28. Thử queryNames có pattern giới hạn và kiểm tra không lộ beans không được phép.
29. Đặt quotas để không trả Map hàng triệu entries.
30. So sánh MXBean với một metrics exporter, xác định khi nào chỉ cần counters, khi nào cần API chuyên dụng.

---

## 14. Checklist đưa MXBean tùy biến vào production

- [ ] Có public interface đúng chuẩn MXBean hoặc `@MXBean`.
- [ ] Interface phơi bày **chỉ** attributes/operations cần quản trị.
- [ ] Mọi parameter và return type theo MXBean OpenType mapping rules.
- [ ] DTO record/bean fields có names, units, nullability và types rõ.
- [ ] Dữ liệu dynamic raw client đọc được qua CompositeData/TabularData/arrays.
- [ ] Không bắt generic client import domain classes của server.
- [ ] Không nhầm `JMX.newMXBeanProxy` typed client với class-free generic client.
- [ ] Đọc MBeanInfo và OpenType descriptor để validate schema.
- [ ] Tránh thay field names/types/units âm thầm; có schema evolution plan.
- [ ] Không expose arbitrary domain objects, sockets, locks, threads hoặc secrets.
- [ ] Các getter nhẹ, có size limits, không block/network không kiểm soát.
- [ ] Snapshot data nhất quán theo concurrency guarantees đã công bố.
- [ ] Dùng AtomicLong/immutable snapshots hoặc synchronization đúng nơi.
- [ ] Operation có bounds validation, authorization và audit.
- [ ] ObjectName ổn định và không duplicate trong cùng MBeanServer.
- [ ] Register khi startup, unregister khi component shutdown.
- [ ] Generic client xử lý AttributeNotFound/InstanceNotFound/schema mismatch.
- [ ] Raw invoke dùng đúng Java/JMX method signature.
- [ ] Không vô hiệu hóa TLS/auth cho remote management connector.
- [ ] Giới hạn mạng, credentials, quyền READ và INVOKE riêng.
- [ ] Không dump MBean attrs chứa dữ liệu nhạy cảm vào public logs.
- [ ] Có tests cho record→CompositeData, Map→TabularData, List→array, enum→String.
- [ ] Có test client compile mà không phụ thuộc service-specific DTO/JAR.
- [ ] Có test typed proxy reconstruct record (nếu typed clients cần).
- [ ] Có tests cho concurrent polling và operation invocation.
- [ ] Có compatibility tests giữa JDK/client/server versions đang hỗ trợ.
- [ ] Không dùng một MBean để thay REST/database/event stream khi use case không phù hợp.

## Kết luận

**MXBean tùy biến** cho phép service định nghĩa một management API thuận tiện bằng Java interface/DTO nhưng vẫn trao đổi **Open Data chuẩn** khi đi qua `MBeanServerConnection`. Một generic client **không cần lớp `Snapshot`, `QueueService` hay `QueueView` phía server** vẫn đọc được dữ liệu, vì record được ánh xạ thành `CompositeData`, Map thành `TabularData`, List thành array và enum thành String. `JMX.newMXBeanProxy` vẫn có vai trò khi client muốn một **typed API**, nhưng lúc đó client cần management interface/model tương ứng.

Cách thiết kế đúng là **management contract nhỏ, có Open Types ổn định, schema/units rõ ràng, data snapshots an toàn**, kèm xác thực/phân quyền cho các operations, thread safety, limits và register/unregister lifecycle. **“Không phụ thuộc class” không đồng nghĩa “không phụ thuộc schema” hoặc “mặc nhiên an toàn khi mở JMX remote”.**

Ví dụ Java 17+ đã chứng minh điều này bằng **hai lần biên dịch độc lập và 13 dòng stdout được kiểm chứng**. Chỉ dùng dữ liệu giả, local MBeanServer, không mở remote connector và không để lại MBean trong registry sau khi chạy.

**Tài liệu chính thức hiện hành:**

- [MXBean specification — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/MXBean.html)
- [MXBean specification — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/MXBean.html)
- [JMX.newMXBeanProxy — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/JMX.html)
- [MBeanServer — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/MBeanServer.html)
- [MBeanServerConnection — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/MBeanServerConnection.html)
- [MBeanInfo — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/MBeanInfo.html)
- [ObjectName — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/ObjectName.html)
- [CompositeData — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/openmbean/CompositeData.html)
- [TabularData — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/openmbean/TabularData.html)
- [OpenType — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/openmbean/OpenType.html)
- [ManagementFactory — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ManagementFactory.html)
- [Java Management Extensions Guide — Java SE 26](https://docs.oracle.com/en/java/javase/26/jmx/java-management-extensions-guide.pdf)