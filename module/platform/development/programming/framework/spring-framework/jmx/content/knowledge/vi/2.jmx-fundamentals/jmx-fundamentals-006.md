# MXBean và cách ánh xạ kiểu dữ liệu mở rộng

## 1. MXBean giải quyết vấn đề gì?

JMX (Java Management Extensions) cho phép công cụ vận hành đọc thuộc tính, gọi thao tác và nhận thông báo từ ứng dụng Java thông qua `MBeanServer`. Với **Standard MBean**, một interface có tên theo quy ước `SomethingMBean` mô tả các thuộc tính và thao tác quản trị. Trong một JVM, phía client có thể làm việc với các kiểu Java mà hai bên cùng biết. Nhưng một giao diện quản trị cần hữu ích cả khi:

- Client ở **tiến trình khác**, dùng JConsole, JMC hoặc thư viện JMX.
- Client không có JAR chứa mọi lớp domain/DTO của ứng dụng.
- Công cụ muốn hiển thị một đối tượng nhiều trường hoặc một bảng dữ liệu mà không cần deserialization lớp riêng.
- Nhiều JVM và công cụ khác nhau cần trao đổi trạng thái quản trị theo định dạng có cấu trúc, được JMX hiểu chung.

**MXBean** là biến thể của MBean có quy tắc ánh xạ các kiểu Java trong giao diện quản trị sang một tập **Open Types** đã được JMX định nghĩa. Nhờ vậy, phía client có thể đọc dữ liệu cấu trúc dưới dạng `CompositeData`, `TabularData`, mảng và kiểu đơn giản mà không cần mang theo lớp DTO phía server.

Sơ đồ tư duy:

```text
              Bên server (ứng dụng Java)
  CatalogMXBean: CatalogStatus getStatus()
                         |
            MXBean type mapping
                         v
           OpenType / OpenData của JMX
                         |
               MBeanServer / connector
                         |
                Công cụ / remote client
                         |
       CompositeData(status), TabularData(...)
                         |
           (nếu có interface tương thích)
          JMX.newMXBeanProxy(...) -> DTO Java
```

Điểm cần ghi nhớ: **MXBean là hợp đồng quản trị dựa trên kiểu mở**, không phải công nghệ truyền tải riêng. JMX connector vẫn phụ trách kết nối; `MBeanServer` vẫn quản lý đăng ký và truy cập MBean.

## 2. Phân biệt MBean, MXBean và Open MBean

| Khía cạnh | Standard MBean | MXBean | Open MBean |
|---|---|---|---|
| Hợp đồng | Interface quản trị theo quy ước `*MBean` | Interface `*MXBean` hoặc được đánh dấu `@MXBean` | Metadata và kiểu dữ liệu mở được khai báo theo Open MBean API |
| Kiểu dữ liệu trên giao diện | Có thể dùng kiểu Java tùy ý | Kiểu Java thuộc tập ánh xạ được sang Open Types | Khai báo trực tiếp bằng `OpenType` |
| Client đọc DTO custom | Thường cần lớp tương thích | Có thể đọc dạng `CompositeData` mà không cần DTO | Có thể làm việc trực tiếp với OpenData |
| Độ tiện lợi khi lập trình | Đơn giản | Giữ API Java nhưng xuất dữ liệu mở | Kiểm soát mô tả OpenType chặt chẽ hơn |
| Trường hợp tiêu biểu | Quản trị nội bộ có sẵn class | Giám sát cấu trúc, JVM platform MXBeans | Giao diện quản trị cần metadata động hoặc OpenData chuyên biệt |

MXBean **không phải** “MBean mạnh hơn về mọi mặt”. Nó phù hợp khi muốn một hợp đồng Java dễ viết nhưng dữ liệu đi qua JMX có cấu trúc được chuẩn hóa. Với đối tượng không ánh xạ được, MXBean sẽ cần thiết kế lại hợp đồng hoặc chuyển sang kiểu có thể ánh xạ; không thể tùy ý xuất bất kỳ object graph nào.

Các platform MXBean như `MemoryMXBean`, `ThreadMXBean` và `GarbageCollectorMXBean` là các ví dụ quen thuộc mà JVM cung cấp sẵn.

## 3. Open Types: ngôn ngữ dữ liệu chung của MXBean

JMX Open MBean API định nghĩa các đối tượng ở package `javax.management.openmbean`. Các kiểu quan trọng:

- **`SimpleType`**: kiểu giá trị đơn giản như `String`, `Integer`, `Long`, `Boolean`, `Double`, `Date`, `ObjectName` và một số kiểu số/chuỗi khác.
- **`ArrayType`**: mảng có kiểu phần tử đã biết; dùng để biểu diễn mảng và nhiều collection có thứ tự.
- **`CompositeType`**: schema của một bản ghi gồm các trường có tên, mô tả và kiểu.
- **`CompositeData`**: một giá trị thực tế phù hợp `CompositeType`, ví dụ một snapshot bộ nhớ có các trường `used`, `committed`, `max`.
- **`TabularType`**: schema của bảng gồm nhiều hàng kiểu `CompositeType` và một hoặc nhiều cột dùng làm khóa.
- **`TabularData`**: dữ liệu thực tế của bảng theo `TabularType`.

**Phân biệt schema và dữ liệu:** `CompositeType` mô tả một bản ghi có những trường nào; `CompositeData` giữ giá trị cụ thể tại một thời điểm. Tương tự, `TabularType` mô tả bảng còn `TabularData` là nội dung bảng.

Ví dụ biểu diễn một trạng thái:

```text
Java object phía server:
  CatalogStatus(name="products", activeItems=128, healthy=true)

Qua MXBean:
  CompositeData {
      name        -> "products"   (SimpleType.STRING)
      activeItems -> 128          (SimpleType.INTEGER)
      healthy     -> true         (SimpleType.BOOLEAN)
  }
```

Client có thể tìm tên trường và giá trị mà không cần class `CatalogStatus`. Với client Java có cùng interface và DTO tương thích, MXBean proxy còn có thể thực hiện ánh xạ ngược.

## 4. Các quy tắc ánh xạ cần thuộc

Bảng sau mô tả ý tưởng ánh xạ trong giao diện MXBean; kết quả cụ thể phụ thuộc vào kiểu được khai báo và quy tắc MXBean hợp lệ của JDK.

| Kiểu Java trong MXBean | Dạng mở thường thấy | Ý nghĩa |
|---|---|---|
| `int`, `long`, `boolean`, `double`, wrapper tương ứng | `SimpleType` phù hợp | Số, cờ |
| `String`, `BigInteger`, `BigDecimal`, `Date`, `ObjectName` | `SimpleType` phù hợp | Giá trị đơn giản |
| `enum` | `SimpleType.STRING` | Tên hằng enum |
| `T[]` với `T` ánh xạ được | `ArrayType` | Danh sách giá trị kiểu đồng nhất |
| `List<T>`, `Set<T>` với `T` ánh xạ được | `ArrayType` | Collection được chuyển thành mảng mở |
| `Map<K,V>` với khóa và giá trị ánh xạ được | `TabularType` / `TabularData` | Bảng các cặp key/value |
| JavaBean DTO có các property ánh xạ được | `CompositeType` / `CompositeData` | Bản ghi có tên trường |
| `CompositeData`, `TabularData` | Bản thân OpenData tương ứng | Dữ liệu mở được sử dụng trực tiếp |

Ví dụ:

```java
public interface CatalogMXBean {
    int getActiveCount();                 // số nguyên đơn giản
    CatalogMode getMode();                // enum -> String ở OpenData
    String[] getKnownRegions();           // mảng các String
    java.util.List<String> getTags();     // mảng mở
    java.util.Map<String, Integer> getCountsByRegion(); // bảng
    CatalogStatus getStatus();            // composite record
}
```

Khi gọi `MBeanServerConnection.getAttribute(name, "Mode")` trực tiếp, client nhận biểu diễn kiểu mở (ví dụ chuỗi `"ACTIVE"`). Khi gọi qua proxy MXBean có đủ class/interface tương thích, Java có thể chuyển biểu diễn đó về `CatalogMode.ACTIVE`.

**Các ranh giới cần nhớ:**

- `Map<K,V>` không tự đồng nghĩa với JSON object: OpenData mô tả bảng có cấu trúc, trong đó key/value có quy tắc kiểu và khóa; không nên thiết kế phụ thuộc vào thứ tự hàng của map.
- `List` có thứ tự theo contract; `Set` không đảm bảo thứ tự có ý nghĩa nếu kiểu set không bảo đảm. Client không nên diễn giải thứ tự của set như dữ liệu nghiệp vụ.
- Kiểu generic phải đủ rõ để MXBean xác định kiểu phần tử. Raw collection và những cấu trúc generic không hỗ trợ có thể làm lỗi ánh xạ.
- Tập kiểu được hỗ trợ có giới hạn; không nên suy luận rằng mọi `Serializable`, mọi `Object` hay mọi class bất kỳ sẽ thành `CompositeData`.
- JavaBean dùng property công khai và các quy tắc mapping của JMX. Một class chứa field private nhưng không có property thích hợp không đương nhiên được xuất thành composite record.
- Cấu trúc lồng nhau có thể ánh xạ đệ quy nếu từng thành phần hợp lệ; object graph có chu trình và kiểu mơ hồ không phải mô hình dữ liệu tốt cho MXBean.

## 5. Ví dụ hoàn chỉnh: một MXBean có DTO, enum và Map

Ví dụ sau dùng Java SE, không cần Spring; mục tiêu là thấy rõ **Java type → OpenData** ngay khi đi qua MBeanServer.

```java
// CatalogMode.java
public enum CatalogMode {
    ACTIVE, PAUSED
}
```

```java
// CatalogStatus.java
public class CatalogStatus {
    private final String name;
    private final int activeItems;
    private final boolean healthy;

    public CatalogStatus(String name, int activeItems, boolean healthy) {
        this.name = name;
        this.activeItems = activeItems;
        this.healthy = healthy;
    }

    public String getName() {
        return name;
    }

    public int getActiveItems() {
        return activeItems;
    }

    public boolean isHealthy() {
        return healthy;
    }
}
```

```java
// CatalogMXBean.java
import java.util.Map;

public interface CatalogMXBean {
    CatalogStatus getStatus();
    CatalogMode getMode();
    Map<String, Integer> getItemsByRegion();
    void resetStatistics();
}
```

```java
// Catalog.java
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

public class Catalog implements CatalogMXBean {
    private final AtomicInteger processed = new AtomicInteger();

    @Override
    public CatalogStatus getStatus() {
        return new CatalogStatus("products", 128, true);
    }

    @Override
    public CatalogMode getMode() {
        return CatalogMode.ACTIVE;
    }

    @Override
    public Map<String, Integer> getItemsByRegion() {
        return Map.of("apac", 80, "eu", 48);
    }

    public void recordProcessed() {
        processed.incrementAndGet();
    }

    @Override
    public void resetStatistics() {
        processed.set(0);
    }
}
```

```java
// Demo.java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;
import javax.management.openmbean.TabularData;

public class Demo {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name =
            new ObjectName("demo.catalog:type=Catalog,name=products");

        server.registerMBean(new Catalog(), name);

        Object rawStatus = server.getAttribute(name, "Status");
        CompositeData status = (CompositeData) rawStatus;

        System.out.println(status.get("name"));        // products
        System.out.println(status.get("activeItems")); // 128
        System.out.println(status.get("healthy"));     // true

        Object rawMap = server.getAttribute(name, "ItemsByRegion");
        TabularData regions = (TabularData) rawMap;
        System.out.println(regions.size());            // 2

        Object rawMode = server.getAttribute(name, "Mode");
        System.out.println(rawMode);                   // ACTIVE

        Thread.sleep(120_000L); // Giữ JVM sống để quan sát bằng JConsole
    }
}
```

Để chạy, đặt mỗi `public` class/interface/enum trong file `.java` cùng tên, biên dịch và thực thi trên một JDK có JMX. Interface `CatalogMXBean` tuân theo quy ước tên `MXBean`, nên JMX nhận ra đây là MXBean khi đăng ký đối tượng implement giao diện đó.

Một số chi tiết của ví dụ:

- `getStatus()` không trở thành thuộc tính chứa instance `CatalogStatus` theo serialization Java thông thường. JMX ánh xạ giá trị thành `CompositeData`.
- `getItemsByRegion()` trở thành `TabularData`; client xem hàng qua metadata của bảng, không giả định `Map` đã trở thành `HashMap` bên nhận.
- `getMode()` là enum trong Java nhưng hiện thành chuỗi ở mức OpenData.
- `resetStatistics()` là **operation**, không phải attribute. Việc gọi nó có thể thay đổi runtime và cần kiểm soát quyền thực thi.
- Giá trị `activeItems=128` ở đây được cố định để minh họa; trong ứng dụng thật, nó cần được lấy từ state hoặc phép đo có ý nghĩa.

Nếu nối client Java qua `JMX.newMXBeanProxy(connection, name, CatalogMXBean.class)`, proxy trả về kiểu Java được khai báo trong interface khi ánh xạ ngược khả thi. Đối với custom composite DTO, khả năng tái dựng từ `CompositeData` còn phụ thuộc quy tắc dựng đối tượng phía client; xem phần kế tiếp.

## 6. Tại sao chiều Java → OpenData dễ hơn chiều OpenData → Java?

Khi MXBean trả dữ liệu, JMX có một instance Java thật và có thể truy xuất các property được phép. Tuy nhiên, ở phía client, muốn chuyển `CompositeData` ngược về `CatalogStatus` thì runtime phải biết **cách tạo object** từ những trường nhận được.

Đối với DTO bất biến (immutable), có thể khai báo constructor được gắn `@ConstructorProperties` để xác định property tương ứng:

```java
import java.beans.ConstructorProperties;

public class CatalogStatus {
    private final String name;
    private final int activeItems;
    private final boolean healthy;

    @ConstructorProperties({"name", "activeItems", "healthy"})
    public CatalogStatus(String name, int activeItems, boolean healthy) {
        this.name = name;
        this.activeItems = activeItems;
        this.healthy = healthy;
    }

    public String getName() { return name; }
    public int getActiveItems() { return activeItems; }
    public boolean isHealthy() { return healthy; }
}
```

Khi dùng phiên bản DTO này ở phía client, MXBean proxy có cơ sở để dựng object từ các trường composite theo contract tương thích. Một phương án khác cho kiểu phù hợp là cung cấp method chuyển đổi tĩnh `from(CompositeData)` theo quy tắc MXBean; hoặc sử dụng kiểu JavaBean có constructor/property đáp ứng yêu cầu mapping của JMX.

Tuy nhiên, **không phải client nào cũng phải dựng DTO**. JConsole hoặc tool dùng `MBeanServerConnection` có thể xem trực tiếp `CompositeData`, chính là lý do OpenData hữu ích. Hãy cân nhắc tách hai mục tiêu:

1. Công cụ vận hành đa nền tảng chỉ cần đọc và hiển thị dữ liệu qua schema mở.
2. Một Java client muốn API kiểu mạnh và gọi typed method qua MXBean proxy.

Thiết kế DTO nên ưu tiên thuộc tính nhỏ, ổn định, đặt tên rõ ràng. Đổi tên property, kiểu property hoặc cấu trúc nested type có thể làm client cũ xử lý sai hoặc không ánh xạ được, dù JMX connector vẫn kết nối thành công.

## 7. MXBean proxy và truy cập OpenData trực tiếp

Hai cách đọc cùng một thuộc tính:

```java
// Cách A: kết nối mức thấp, nhận OpenData.
Object raw = connection.getAttribute(name, "Status");
CompositeData status = (CompositeData) raw;
String value = (String) status.get("name");
```

```java
// Cách B: typed MXBean proxy; client cần các lớp liên quan.
CatalogMXBean proxy =
    javax.management.JMX.newMXBeanProxy(
        connection, name, CatalogMXBean.class);
CatalogStatus status = proxy.getStatus();
```

`connection` là một `MBeanServerConnection` trỏ đến MBeanServer chứa ObjectName đã đăng ký. Ở server local, `MBeanServer` cũng triển khai giao diện kết nối này. Với remote JMX, connector tạo kết nối tương ứng; việc thiết lập địa chỉ, TLS và xác thực là bước riêng.

**Trade-off:** truy cập `CompositeData` trực tiếp không cần DTO application nhưng client phải đọc tên cột/trường. Proxy cho code Java dễ đọc và kiểm tra kiểu tốt hơn, đổi lại client cần interface, enum, DTO tương thích với hợp đồng phía server.

Ví dụ kiểm tra metadata mà không ép kiểu mù:

```java
if (raw instanceof CompositeData data) {
    System.out.println(data.getCompositeType().keySet());
    for (String key : data.getCompositeType().keySet()) {
        System.out.println(key + " = " + data.get(key));
    }
}
```

Với `TabularData`, có thể xem schema bằng `getTabularType()`, các cột hàng bằng `getTabularType().getRowType()`, và duyệt `values()`. Không nên hard-code index của bảng khi chưa đọc `TabularType.getIndexNames()`.

## 8. Dùng @MXBean khi không muốn đặt tên interface theo hậu tố

JMX có thể nhận diện MXBean qua convention `*MXBean`, hoặc qua annotation:

```java
import javax.management.MXBean;

@MXBean
public interface HealthView {
    boolean isHealthy();
    String getSummary();
}
```

Lớp implement `HealthView` có thể được đăng ký như một MXBean trong cấu hình phù hợp dù interface không kết thúc bằng `MXBean`. Khi naming convention không rõ, có thể bọc object bằng `StandardMBean` với chế độ MXBean:

```java
import javax.management.StandardMBean;

HealthView target = new HealthViewImpl();
StandardMBean wrapper =
    new StandardMBean(target, HealthView.class, true); // true = MXBean
server.registerMBean(wrapper,
    new ObjectName("demo.health:type=HealthView"));
```

Đây là hai cách biểu diễn cùng ý tưởng: **một interface quản trị được đánh dấu là MXBean**, để JMX áp dụng các quy tắc kiểu mở. Không nên triển khai cả hai cách cùng lúc cho cùng ObjectName; một ObjectName chỉ định danh một MBean trong MBeanServer.

## 9. MXBean với Spring Framework: hiểu ranh giới trách nhiệm

Spring Framework hỗ trợ JMX thông qua `MBeanExporter`, annotation quản trị và cơ chế đặt tên/metadata. Những công cụ này giúp đăng ký Spring bean dưới dạng MBean và chọn thuộc tính/thao tác cần công bố.

Nhưng cần tách rõ:

- **Java JMX/MXBean** quyết định OpenType mapping, `CompositeData`, `TabularData`, `MBeanServer`, ObjectName và proxy.
- **Spring Framework** hỗ trợ quản lý lifecycle, chọn bean, cấu hình exporter và khai báo thông tin quản trị.
- **Spring Boot** (nếu sử dụng) có cấu hình riêng liên quan JMX và endpoint; không đồng nhất với Spring Framework core.

Một ứng dụng Spring có thể tạo bean implement interface MXBean chuẩn rồi đăng ký qua JMX exporter phù hợp. Ví dụ:

```java
public interface QueueStatsMXBean {
    int getPendingMessages();
    java.util.Map<String, Integer> getPendingByTopic();
}

public class QueueStats implements QueueStatsMXBean {
    @Override
    public int getPendingMessages() {
        return 12;
    }

    @Override
    public java.util.Map<String, Integer> getPendingByTopic() {
        return java.util.Map.of("orders", 8, "notifications", 4);
    }
}
```

Khi đối tượng được đăng ký đúng là MXBean, `getPendingByTopic()` được công bố qua OpenData theo quy tắc Map → tabular. Đừng hiểu rằng gắn `@Component` cho `QueueStats` là đủ để tự đăng ký MXBean: còn cần exporter/registration tương ứng.

Tùy cơ chế export đã chọn, Spring annotation như `@ManagedResource` có thể tạo một giao diện MBean theo metadata của Spring. **Không được giả định mọi bean có `@ManagedResource` đều mặc nhiên được xem là MXBean với cùng quy tắc type mapping**. Nếu mục tiêu bài toán là MXBean, hãy xác minh chính kiểu MBean được đăng ký và giá trị `MBeanInfo`/attribute thực tế qua client JMX.

## 10. Ví dụ platform MXBean: MemoryUsage

JDK cung cấp `java.lang.management.MemoryMXBean` với thuộc tính kiểu `MemoryUsage`. Một giá trị memory usage chứa:

- `init`: kích thước bộ nhớ ban đầu theo ngữ nghĩa của pool/JVM, hoặc `-1` nếu không xác định.
- `used`: bộ nhớ đang dùng.
- `committed`: dung lượng được JVM cam kết có thể dùng.
- `max`: giới hạn tối đa, hoặc `-1` nếu không xác định.

Qua OpenData, giá trị thường xuất hiện dưới dạng `CompositeData` chứa các trường tương ứng. Ví dụ truy cập bằng JMX API:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName memory = new ObjectName("java.lang:type=Memory");

CompositeData heap =
    (CompositeData) server.getAttribute(memory, "HeapMemoryUsage");

long used = (Long) heap.get("used");
long committed = (Long) heap.get("committed");

System.out.println("heap used = " + used);
System.out.println("heap committed = " + committed);
```

Khi dùng typed platform interface, `ManagementFactory.getMemoryMXBean().getHeapMemoryUsage()` trả về `MemoryUsage` trong Java. Hai góc nhìn khác nhau trên **cùng hợp đồng quản trị**: typed Java API thuận tiện cho code, còn OpenData giúp công cụ bên ngoài khám phá cấu trúc.

`used`, `committed` và `max` không đồng nghĩa với nhau. Không mặc định `used / max` có nghĩa khi `max = -1`; cũng không thể kết luận memory leak chỉ bằng một lần đọc.

## 11. Thiết kế DTO và schema MXBean bền vững

Một MXBean được nhiều client sử dụng nên được xem như API có hợp đồng ổn định.

### Chọn dữ liệu để xuất

Nên công bố dữ liệu có ý nghĩa vận hành: số kết nối đang bận, độ sâu hàng đợi, bộ đếm lỗi, trạng thái pool, snapshot cấu hình an toàn. Tránh export toàn bộ entity nghiệp vụ, Hibernate proxy, object graph có vòng tham chiếu hoặc tài nguyên chứa secret.

Ưu tiên một DTO snapshot nhỏ:

```text
ConnectionPoolStatus
  activeConnections: int
  idleConnections: int
  waitingThreads: int
  healthy: boolean
```

thay vì export một object pool nội bộ có hàng chục dependency. Snapshot nên có các thuộc tính đọc nhanh và nhất quán vừa đủ với mục đích quan sát. Nếu các trường được lấy ở thời điểm khác nhau, tài liệu nên nói rõ đó là ảnh chụp gần đúng.

### Tránh breaking change

Các thay đổi có thể ảnh hưởng client gồm:

- Đổi ObjectName hoặc tên thuộc tính (`Status` thành `State`).
- Đổi kiểu số (`Integer` sang `Long`) khi client hard-code kiểu.
- Đổi tên property trong composite (`activeItems` thành `activeCount`).
- Thay đổi tên enum hoặc ý nghĩa giá trị.
- Thay danh sách thành map hoặc đổi khóa của map.
- Đưa một custom type mới không ánh xạ được vào interface đã xuất.

Nếu cần mở rộng, cân nhắc thêm thuộc tính mới hoặc phiên bản hợp đồng; cung cấp ý nghĩa/đơn vị đo và tính tương thích. Trường hợp client dùng `CompositeData` nên kiểm tra field tồn tại trước khi truy cập; client proxy cần DTO/interface đúng phiên bản.

### Cân nhắc chi phí và quyền truy cập

Đọc một attribute có thể gọi code thật trong ứng dụng. Một getter quét hàng triệu bản ghi hoặc giữ lock dài sẽ làm client quản trị chậm và có thể ảnh hưởng workload. Những thao tác thay đổi state như `resetStatistics`, `clearCache` hoặc `reloadConfiguration` cần quyền quản trị, đánh giá tác động và audit.

MXBean không tự mang đến RBAC, TLS hay audit. Với remote JMX, phải bảo vệ kết nối và giới hạn endpoint theo môi trường. Không để schema mở trở thành kênh tiết lộ token, dữ liệu người dùng hoặc thông tin nhạy cảm.

## 12. Lỗi thường gặp và cách suy luận

**Lỗi: interface tên `*MXBean` nhưng đăng ký thất bại.** Kiểm tra interface có được implement đúng, đối tượng có thỏa quy tắc JMX compliance, có nhiều interface gây mơ hồ và mọi method/property trong hợp đồng có kiểu ánh xạ hợp lệ không. Đọc exception gốc thay vì chỉ bắt `Exception`.

**Lỗi: `ClassCastException` khi cast raw attribute sang DTO.** Truy cập mức thấp của MXBean thường trả giá trị OpenData. Nếu `Status` là một DTO được ánh xạ, hãy đọc `CompositeData` hoặc dùng typed MXBean proxy, không ép `CompositeData` thành `CatalogStatus`.

**Lỗi: proxy không dựng được DTO.** Kiểm tra mapping chiều ngược: JavaBean properties, constructor và `@ConstructorProperties`, hoặc cơ chế `from(CompositeData)` phù hợp; kiểm tra các tên và kiểu field giữa server/client.

**Lỗi: map trở thành bảng thay vì `Map`.** Đây là hành vi mong đợi ở OpenData. Hãy duyệt `TabularData` theo row type/index names, hoặc sử dụng proxy đã biết `Map<K,V>`.

**Lỗi: không thấy MBean trong JConsole.** Kiểm tra tiến trình đã đăng ký đúng ObjectName, kết nối tới đúng JVM, exporter đã chạy, quyền attach/remote JMX và không có xung đột tên. Annotation hoặc interface chỉ khai báo hợp đồng; đăng ký vào MBeanServer vẫn phải xảy ra.

**Lỗi: getter chạy nhưng chậm hoặc gây lỗi.** Attribute getter được gọi mỗi lần client đọc. Đưa công việc nặng sang luồng thu thập/cập nhật snapshot, để getter trả dữ liệu đã chuẩn bị khi phù hợp; không chuyển logic nghiệp vụ nặng vào giao diện quan sát.

## 13. Bài tập tự luyện

1. Với `Map<String, Long> getErrorCountByType()`, loại OpenData nào phù hợp và vì sao không phải một Java `HashMap` được truyền nguyên dạng?
2. So sánh `CatalogStatus getStatus()` và `CompositeData` phía JMX client. Vì sao hai bên không nhất thiết cần chung JAR DTO?
3. Tại sao client dùng `JMX.newMXBeanProxy` có thể nhận lại một DTO nhưng `getAttribute` trực tiếp trả `CompositeData`?
4. Với enum `CatalogMode`, giá trị được ánh xạ thành loại mở nào? Điều gì xảy ra nếu client không biết tên enum mới khi ánh xạ ngược?
5. Hãy thiết kế `ConnectionPoolMXBean` chỉ có `getActiveConnections()`, `getIdleConnections()`, `getStatus()` và `resetStatistics()`. Phân loại attribute/operation và DTO composite.
6. Nếu một DTO có `getConnections()` trả `List<Socket>`, tại sao cần xem xét thay đổi hợp đồng thay vì mặc định JMX sẽ serialize được?
7. Làm thế nào xác minh một Spring bean được đăng ký **thực sự** là MXBean và client đang nhận OpenData mong đợi?

## 14. Ghi nhớ cốt lõi

**MXBean = giao diện quản trị Java có hợp đồng ánh xạ sang Open Types.** Từ phía server, Java type được chuyển sang các biểu diễn JMX hiểu chung: `SimpleType` cho giá trị đơn, `CompositeData` cho bản ghi, `TabularData` cho bảng và `ArrayType` cho nhiều cấu trúc dạng mảng. Client có thể đọc OpenData trực tiếp hoặc dùng typed MXBean proxy khi có lớp phù hợp.

Nắm chắc ranh giới **type mapping**, **chiều chuyển đổi ngược**, **MBeanServer/ObjectName** và **lifecycle export trong Spring** giúp thiết kế giao diện giám sát rõ ràng, dễ dùng trên nhiều công cụ và an toàn hơn cho hệ thống Java đang chạy.
