# Phiên bản hóa management interface trong Spring Framework JMX

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **management interface** trong JMX là một hợp đồng (contract) dành cho công cụ vận hành, không chỉ là một interface Java nội bộ.
- Phân biệt các mức tương thích: Java source/binary compatibility, JMX metadata compatibility, client compatibility, semantic compatibility và operational compatibility.
- Nhận diện breaking changes khi đổi \`ObjectName\`, attribute name/type/access, operation name/signature, notification type, return type, description và semantics.
- Thiết kế chiến lược **versioning management interface** theo từng MBean, bằng cách giữ contract cũ, thêm contract mới, hoặc đưa version vào ObjectName khi cần.
- Lập kế hoạch migration giữa phiên bản v1 và v2 trong Spring Framework JMX mà không làm dashboard, alert rules, JConsole scripts hay JMX exporters ngừng hoạt động ngoài ý muốn.
- Sử dụng Standard MBean, MXBean hoặc annotation-driven management adapters với ranh giới version rõ ràng.
- Kiểm tra tương thích bằng \`MBeanServer.getMBeanInfo()\`, \`getAttribute()\`, \`invoke()\` và integration tests tự động.
- Hiểu khi nào không nên tạo phiên bản mới và khi nào cần thông báo deprecation, hỗ trợ song song rồi loại bỏ API cũ.

## 2. Management interface là public API cho vận hành

JMX (Java Management Extensions) cho phép application hoặc JVM công bố một tập **attributes, operations và notifications** trong \`MBeanServer\`. Những thành phần đó được xác định bằng \`ObjectName\` và metadata \`MBeanInfo\`.

Ví dụ:

~~~text
ObjectName:
com.example.shop.orders:type=QueueMonitor,name=outbox

Attributes:
PendingCount : int (read-only)
Paused       : boolean (read-only)

Operations:
pause()
resume()
resetStatistics()

Notifications:
com.example.shop.queue.threshold.exceeded
~~~

Nếu một JMX exporter, dashboard, monitoring rule hoặc script đã sử dụng contract đó, việc đổi tên \`PendingCount\` thành \`QueueDepth\` có thể khiến script lỗi, dù bản Java service mới vẫn compile và hoạt động.

**Nguyên tắc:** Một management interface đã được client dùng phải được quản lý như **API có phiên bản và vòng đời tương thích**.

Không nên cho rằng các phương thức quản trị “chỉ dành cho nội bộ” thì có thể đổi tùy ý. Trong production, các consumers có thể là:
- JConsole/JMC và công cụ hỗ trợ sự cố.
- JMX exporter hoặc metric collectors.
- Alert rules và dashboards dựa trên tên thuộc tính.
- Automation scripts sử dụng \`getAttribute()\`/\`invoke()\`.
- Client Java sử dụng \`JMX.newMBeanProxy()\` hoặc Spring \`MBeanProxyFactoryBean\`.
- Các công cụ quản lý application server hoặc thư viện.

Một thay đổi không ảnh hưởng Java compiler vẫn có thể phá client JMX.

## 3. “Phiên bản hóa” gồm những lớp nào?

| Lớp | Đối tượng thay đổi | Rủi ro |
|---|---|---|
| Java source API | Tên interface, method, tham số | Code client không compile |
| Java binary API | Method descriptor và class signature | \`NoSuchMethodError\` hoặc lỗi linkage |
| JMX ObjectName | Domain/key properties | Client không tìm thấy MBean |
| JMX attribute metadata | Name/type/readable/writable | \`AttributeNotFoundException\` hoặc cast lỗi |
| JMX operation metadata | Name/parameter signature/return | \`ReflectionException\` hoặc invoke sai |
| JMX value representation | Scalar, CompositeData, MXBean mapping | Client không parse/cast được |
| Semantics | Ý nghĩa, đơn vị, mức độ nhất quán | Dashboard vẫn chạy nhưng diễn giải sai |
| Security/authorization | Ai được phép đọc hoặc invoke | Automation bị từ chối hoặc quyền tăng ngoài ý muốn |
| Lifecycle | Thời điểm register/unregister | Client mất endpoint khi deploy |
| Observability mapping | Exporter rules, labels, dashboards | Time series bị gián đoạn hoặc đổi tên |

Phiên bản hóa đúng phải tính cả **hình thức** lẫn **ngữ nghĩa**. Ví dụ, giữ attribute \`Timeout\` cùng tên và kiểu \`long\` nhưng đổi đơn vị từ milliseconds sang seconds là breaking semantic change dù Java/JMX metadata không thay đổi.

## 4. Ví dụ contract v1

Giả sử ứng dụng ban đầu có Standard MBean:

~~~java
public interface QueueMonitorMBean {
    int getPendingCount();
    boolean isPaused();
    void pause();
    void resume();
}
~~~

~~~java
public class QueueMonitor implements QueueMonitorMBean {
    private volatile boolean paused;

    @Override
    public int getPendingCount() {
        return 42;
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
~~~

Registration:

~~~java
ObjectName name = new ObjectName(
    "com.example.shop.orders:type=QueueMonitor,name=outbox");

server.registerMBean(new QueueMonitor(), name);
~~~

Một client JMX đọc:

~~~java
int count = (Integer) server.getAttribute(
        name, "PendingCount");
~~~

và gọi operation:

~~~java
server.invoke(
        name, "pause", new Object[0], new String[0]);
~~~

Tất cả đều ổn nếu MBean được đăng ký và hợp đồng khớp. Vấn đề xuất hiện khi nâng cấp server mà client chưa được nâng cấp đồng thời.

## 5. Thay đổi nào có thể giữ tương thích?

### 5.1. Thêm attribute mới

Từ v1:

~~~text
PendingCount : int
Paused       : boolean
~~~

sang v2:

~~~text
PendingCount : int
Paused       : boolean
OldestPendingAgeMillis : long
~~~

Nếu thuộc tính cũ giữ nguyên tên, kiểu, quyền đọc và semantics, nhiều client cũ vẫn hoạt động. Đây thường là **additive change**.

Tuy nhiên không có bảo đảm tuyệt đối: một client viết theo schema cứng hoặc dựa vào đúng số lượng attributes có thể không chấp nhận field mới. Vì vậy vẫn cần contract tests.

### 5.2. Thêm operation mới

Thêm \`refreshSnapshot()\` thường không phá client cũ chỉ đọc các operations trước đó. Nhưng nó mở rộng bề mặt quản trị, có thể tạo rủi ro bảo mật hoặc audit. “Backward compatible” không đồng nghĩa “safe to expose”.

### 5.3. Thêm description/documentation

Cập nhật mô tả \`PendingCount\` để rõ hơn thường không phá method signatures. Tuy nhiên exporter hoặc automation có thể đọc metadata description theo quy tắc riêng; tránh nhúng thông tin máy móc có tính bắt buộc vào description mà không tài liệu hóa.

### 5.4. Tối ưu implementation

Đổi getter từ query DB sang cached snapshot mà vẫn giữ cùng contract có thể không phá cú pháp, nhưng cần công bố thay đổi về **freshness** nếu client trước đây giả định mỗi lần đọc là giá trị truy vấn tức thời.

### 5.5. Thêm metadata phụ trợ

Thêm \`CapturedAtEpochMillis\`, \`SnapshotHealthy\` hoặc \`Generation\` có thể hỗ trợ tương thích và minh bạch, miễn client cũ vẫn nhận các thuộc tính cũ với ngữ nghĩa thích hợp.

## 6. Các thay đổi breaking phổ biến

| Thay đổi | Ví dụ | Tác động |
|---|---|---|
| Đổi ObjectName | \`type=QueueMonitor\` → \`type=QueueStats\` | Client \`isRegistered\` sai; exporter không tìm MBean |
| Đổi attribute name | \`PendingCount\` → \`QueueDepth\` | \`AttributeNotFoundException\` |
| Đổi attribute type | \`int\` → \`long\` | Proxy/cast kỳ vọng \`Integer\` có thể lỗi |
| Đổi quyền | readable → không readable | Client không đọc được |
| Đổi operation name | \`pause\` → \`suspend\` | \`invoke\` không tìm operation |
| Đổi tham số | \`resize(int)\` → \`resize(long)\` | Signature JMX không khớp |
| Đổi return structure | scalar → CompositeData | Deserializer/cast/schema cũ lỗi |
| Đổi units | milliseconds → seconds | Metrics/alerts hiểu sai |
| Đổi behavior | \`resetStatistics\` reset thêm business state | Side effects ngoài dự kiến |
| Đổi notification type | tên event bị thay | Listener lọc theo type bị bỏ lỡ |
| Đổi naming version | v1 MBean bị gỡ trước migration | Clients cũ mất endpoint |
| Đổi remote access | connector/port/auth đổi | Clients không kết nối được |

Một thay đổi có thể phá nhiều lớp. Ví dụ đổi từ Standard MBean sang MXBean có thể làm \`MBeanInfo\` và value mapping khác, kể cả khi interface Java trông gần giống.

## 7. Đổi kiểu int sang long: vì sao phải cẩn thận?

Ví dụ v1:

~~~java
public interface QueueMonitorMBean {
    int getPendingCount();
}
~~~

v2:

~~~java
public interface QueueMonitorMBean {
    long getPendingCount();
}
~~~

Java developer có thể thấy đây là cách mở rộng phạm vi số nguyên. Nhưng JMX client v1 có thể cast:

~~~java
Integer value = (Integer) connection.getAttribute(
        name, "PendingCount");
~~~

Trong v2, runtime JMX value có thể là \`Long\`, gây \`ClassCastException\`. JMX dynamic proxy sử dụng interface v1 cũng có thể không khớp return type thực tế.

Giải pháp chuyển đổi mềm:

- Giữ \`getPendingCount()\` cũ trong một giai đoạn nếu giá trị còn biểu diễn chính xác; không được âm thầm truncate.
- Thêm \`getPendingCountLong()\` hoặc một attribute tên mới mô tả kiểu rõ.
- Nếu vượt miền \`int\`, xác định policy cho v1 (ví dụ deprecate và signal overflow) thay vì trả sai số.
- Công bố v2 MBean với contract mới dưới ObjectName riêng nếu client cần nâng cấp đồng bộ.
- Đo phiên bản client thực tế trước khi xóa v1.

Không nên thay đổi kiểu trực tiếp trong production mà không có compatibility test.

## 8. Đổi đơn vị cũng có thể là breaking change

Giả sử v1 có:

~~~text
AverageProcessingTime = 2500
Unit = milliseconds
~~~

Nếu v2 trả \`2.5\` giây dưới cùng tên, client cũ sẽ vẽ metric thấp hơn 1000 lần hoặc kích hoạt cảnh báo sai.

Hai cách rõ hơn:

1. Giữ \`AverageProcessingTimeMillis\` và thêm \`AverageProcessingTimeSeconds\`.
2. Tạo v2 contract tường minh với tên/description mới, chuyển consumers có kế hoạch.

Nếu dùng \`@ManagedMetric\` hoặc descriptor có units, metadata cũng phải cập nhật nhất quán. Đừng hy vọng client tự suy ra việc đổi đơn vị từ một đoạn description.

## 9. Chiến lược A — Giữ một ObjectName và phát triển cộng dồn

Nếu thay đổi chủ yếu là thêm attributes/operations không phá cũ, có thể giữ:

~~~text
com.example.shop.orders:type=QueueMonitor,name=outbox
~~~

và mở rộng management interface:

~~~java
public interface QueueMonitorMBean {
    int getPendingCount();
    boolean isPaused();
    void pause();
    void resume();

    long getProcessedCount();
    long getLastRefreshEpochMillis();
}
~~~

Ưu điểm:
- Clients cũ vẫn dùng ObjectName cũ.
- Monitoring rules không cần đổi domain/key.
- Thường dễ vận hành khi chỉ thêm dữ liệu.

Nhược điểm:
- Contract có thể phình to nếu tích lũy nhiều legacy attributes.
- Khó xử lý thay đổi không tương thích về type/semantics.
- Các operations mới cần được review bảo mật.

**Quy tắc:** Chỉ thêm cái mới khi có thể giữ ý nghĩa của cái cũ. Nếu không thể, dùng chiến lược song song hoặc versioned ObjectName.

## 10. Chiến lược B — Tạo versioned ObjectName

Khi v2 phá contract v1, có thể đăng ký hai MBeans độc lập:

~~~text
com.example.shop.orders:type=QueueMonitor,name=outbox,version=v1
com.example.shop.orders:type=QueueMonitor,name=outbox,version=v2
~~~

Mỗi ObjectName có management contract riêng.

Ưu điểm:
- Clients có thể chọn phiên bản rõ ràng.
- Cho phép migration từng bước.
- Dễ kiểm chứng v1 và v2 song song.
- Không cần đổi behavior âm thầm dưới cùng một ObjectName.

Nhược điểm:
- Cần vận hành hai adapters/MBeans trong giai đoạn chuyển tiếp.
- Có thể trùng số liệu/metric nếu collectors scrape cả hai.
- Nếu v1 và v2 tính toán độc lập, có thể tăng tải.
- Clients/dashboards phải biết version key.

Lưu ý: nếu v1 trước đây dùng tên **không có** key \`version\`, chỉ thêm MBean \`version=v1\` vẫn làm clients cũ tìm sai. Trong migration cần **giữ nguyên ObjectName lịch sử** cho v1 và chỉ dùng version key cho v2, hoặc có alias MBean tương thích:

~~~text
Legacy v1: com.example.shop.orders:type=QueueMonitor,name=outbox
New v2:    com.example.shop.orders:type=QueueMonitor,name=outbox,version=v2
~~~

Không sửa tên v1 chỉ để tên hai phiên bản đẹp và đồng nhất.

## 11. Chiến lược C — Management facade có phiên bản nội bộ

Một lựa chọn khác là giữ ObjectName ổn định nhưng đặt một facade/adapter làm nguồn contract:

~~~text
JMX client
    |
    v
QueueManagementFacade (stable ObjectName)
    |
    +-- adapter v1 semantics
    +-- adapter v2 implementation
    |
    v
Queue service + snapshot data
~~~

Facade giúp che implementation details và tránh export trực tiếp business bean. Tuy nhiên nếu một method v1 phải trả kiểu \`int\` trong khi v2 cần \`long\`, facade không thể thay type dưới cùng attribute mà vẫn giữ binary/JMX compatibility. Khi đó thêm attribute mới hoặc versioned MBean vẫn cần thiết.

Facade không phải phép màu tự chuyển mọi contract. Nó chỉ giúp quản lý version logic ở một nơi.

## 12. Ví dụ Standard MBean v1 và v2 song song

Hai interfaces:

~~~java
public interface QueueMonitorV1MBean {
    int getPendingCount();
}

public interface QueueMonitorV2MBean {
    long getPendingCount();
    long getProcessedCount();
    long getSnapshotEpochMillis();
}
~~~

Hai implementations có thể cùng đọc từ một \`QueueStatistics\` service:

~~~java
public final class QueueMonitorV1 implements QueueMonitorV1MBean {
    private final QueueStatistics stats;

    public QueueMonitorV1(QueueStatistics stats) {
        this.stats = stats;
    }

    @Override
    public int getPendingCount() {
        long value = stats.pendingCount();
        if (value > Integer.MAX_VALUE || value < Integer.MIN_VALUE) {
            throw new IllegalStateException(
                    "Legacy PendingCount is out of int range");
        }
        return (int) value;
    }
}
~~~

~~~java
public final class QueueMonitorV2 implements QueueMonitorV2MBean {
    private final QueueStatistics stats;

    public QueueMonitorV2(QueueStatistics stats) {
        this.stats = stats;
    }

    @Override
    public long getPendingCount() {
        return stats.pendingCount();
    }

    @Override
    public long getProcessedCount() {
        return stats.processedCount();
    }

    @Override
    public long getSnapshotEpochMillis() {
        return stats.snapshotEpochMillis();
    }
}
~~~

Vì Standard MBean naming convention phụ thuộc tên class/interface, hai classes và interfaces ở đây có cặp tên tương ứng. Nếu cần tách class/interface naming khác, có thể sử dụng \`StandardMBean\` wrapper theo API Java JMX.

Ví dụ explicit registration:

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName legacyName = new ObjectName(
    "com.example.shop.orders:type=QueueMonitor,name=outbox");
ObjectName v2Name = new ObjectName(
    "com.example.shop.orders:type=QueueMonitor,name=outbox,version=v2");

server.registerMBean(new QueueMonitorV1(stats), legacyName);
server.registerMBean(new QueueMonitorV2(stats), v2Name);
~~~

Ví dụ giả định \`stats\` đã tồn tại, đáp ứng service interface riêng và không trùng names. Trong Spring application, nên dùng bean/exporter owner phù hợp thay vì tự register nếu dự án đang quản lý lifecycle qua Spring.

**Cẩn thận:** Không để v1 overflow được “giải quyết” bằng cast trực tiếp mà âm thầm làm số âm/sai. Nếu legacy type không còn biểu diễn đúng số liệu, cần chính sách thông báo lỗi hoặc migration có kế hoạch.

## 13. Spring annotation-driven versioning

Một kiến trúc khác dùng hai Spring management adapters có metadata riêng.

~~~java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.shop.orders:type=Queue,name=outbox",
    description = "Legacy queue management v1")
public class QueueManagementV1 {
    private final QueueStatistics stats;

    public QueueManagementV1(QueueStatistics stats) {
        this.stats = stats;
    }

    @ManagedAttribute
    public int getPendingCount() {
        long count = stats.pendingCount();
        if (count > Integer.MAX_VALUE) {
            throw new IllegalStateException("Count exceeds v1 range");
        }
        return (int) count;
    }
}
~~~

~~~java
@Component
@ManagedResource(
    objectName = "com.example.shop.orders:type=Queue,name=outbox,version=v2",
    description = "Queue management v2")
public class QueueManagementV2 {
    private final QueueStatistics stats;

    public QueueManagementV2(QueueStatistics stats) {
        this.stats = stats;
    }

    @ManagedAttribute
    public long getPendingCount() {
        return stats.pendingCount();
    }

    @ManagedAttribute
    public long getProcessedCount() {
        return stats.processedCount();
    }
}
~~~

Yêu cầu:
- \`QueueStatistics\` là Spring bean hoặc contract được inject đúng.
- Một annotation-aware exporter có thể chọn và đăng ký hai adapters.
- Naming strategy nhận đúng \`objectName\` của mỗi resource.
- Không có exporter khác đăng ký trùng.
- Cả hai adapters dựa trên dữ liệu chung để tránh đo lường lệch.
- Mỗi ObjectName có một registration owner và lifecycle rõ.

Nếu dùng Spring AOP proxies, phải kiểm tra method exposure và annotation discovery. Một management adapter riêng thường dễ duy trì hơn việc annotate trực tiếp một business service có nhiều transaction/security advice.

## 14. Vì sao không được dùng REPLACE_EXISTING như versioning?

Spring JMX hỗ trợ \`RegistrationPolicy\`:

| Policy | Khi ObjectName đã tồn tại |
|---|---|
| \`FAIL_ON_EXISTING\` | Báo conflict |
| \`IGNORE_EXISTING\` | Giữ MBean cũ |
| \`REPLACE_EXISTING\` | Thay MBean cũ |

Đây là **chính sách xử lý trùng đăng ký**, không phải cơ chế quản lý phiên bản API. Dùng \`REPLACE_EXISTING\` để đưa v2 lên cùng tên v1 có thể khiến clients v1 nhận metadata khác và lỗi.

Một chiến lược versioning cần tính tới:
- Clients đang dùng tên nào.
- Contract nào được công bố.
- Khi nào client được chuyển sang v2.
- Khi nào v1 bị deprecate và gỡ bỏ.
- Làm sao rollback.
- Ai chịu trách nhiệm ObjectName.

Nếu muốn thay implementation dưới cùng ObjectName, cần đảm bảo contract vẫn tương thích. Nếu không, versioned ObjectName hoặc compatibility adapter mới là giải pháp rõ ràng.

## 15. MBeanInfo là nguồn chân lý runtime

Source code là contract dự định; \`MBeanInfo\` là thứ JMX client nhìn thấy thực tế.

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class ContractInspector {
    public static void inspect(String objectName) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        MBeanInfo info = server.getMBeanInfo(
                new ObjectName(objectName));

        System.out.println("MBean: " + objectName);
        System.out.println("Implementation: " + info.getClassName());

        for (MBeanAttributeInfo a : info.getAttributes()) {
            System.out.printf(
                "ATTR %s type=%s readable=%s writable=%s%n",
                a.getName(),
                a.getType(),
                a.isReadable(),
                a.isWritable());
        }

        for (MBeanOperationInfo op : info.getOperations()) {
            System.out.printf(
                "OP %s returns %s%n",
                op.getName(),
                op.getReturnType());
        }
    }
}
~~~

Nếu Spring exporter dùng một custom MBeanServer, phải sử dụng đúng server thay vì platform server. Các giá trị từ metadata là bằng chứng về surface API; để xác minh semantics, cần thêm tests gọi thật và kiểm tra kết quả.

Với overloaded operations, không chỉ so sánh tên mà còn phải so sánh parameter types và signature. JMX \`invoke(name, "resize", args, signature)\` phân biệt \`int\` với \`long\` và những kiểu khác.

## 16. Thiết kế contract test cho v1 và v2

Trong Spring integration test:
1. Khởi động ApplicationContext với exporter/assembler thực tế.
2. Dùng MBeanServer test riêng nếu có thể.
3. Xác nhận ObjectName v1 vẫn đăng ký.
4. Xác nhận ObjectName v2 được đăng ký.
5. Kiểm tra v1 \`PendingCount\` có type \`int\` và readable.
6. Kiểm tra v2 \`PendingCount\` có type \`long\`.
7. Gọi \`getAttribute()\` và xác minh runtime values.
8. Kiểm tra operations cũ và mới (kể cả signatures).
9. Kiểm tra các operations nội bộ không bị expose.
10. Đóng context và xác minh cleanup đúng registration owner.

Pseudocode assertion:

~~~java
ObjectName v1 = new ObjectName(
    "com.example.shop.orders:type=Queue,name=outbox");

ObjectName v2 = new ObjectName(
    "com.example.shop.orders:type=Queue,name=outbox,version=v2");

assertTrue(server.isRegistered(v1));
assertTrue(server.isRegistered(v2));

MBeanInfo oldInfo = server.getMBeanInfo(v1);
MBeanInfo newInfo = server.getMBeanInfo(v2);

assertTrue(
    java.util.Arrays.stream(oldInfo.getAttributes())
        .anyMatch(a -> a.getName().equals("PendingCount")
                    && a.getType().equals("int")));

assertTrue(
    java.util.Arrays.stream(newInfo.getAttributes())
        .anyMatch(a -> a.getName().equals("PendingCount")
                    && a.getType().equals("long")));
~~~

Đoạn assertion giả định JUnit assertions được import và server đã khởi động/đăng ký hai MBeans. Đây là logic minh họa, không phải một test standalone đầy đủ.

Đừng chỉ kiểm tra \`isRegistered\`; một MBean khác có thể chiếm cùng tên nếu registration policy \`IGNORE_EXISTING\` được cấu hình.

## 17. Snapshot test cho metadata, có giới hạn

Một cách quản lý contract là lưu mô tả có cấu trúc về MBeanInfo:

~~~json
{
  "objectName": "com.example.shop.orders:type=Queue,name=outbox",
  "attributes": [
    {"name": "PendingCount", "type": "int", "readable": true},
    {"name": "Paused", "type": "boolean", "readable": true}
  ],
  "operations": [
    {"name": "pause", "signature": []},
    {"name": "resume", "signature": []}
  ]
}
~~~

Sau mỗi build, integration test so sánh metadata runtime với hợp đồng mong đợi. Nếu có diff, developer xem đó là thay đổi API quản trị cần giải thích.

Hạn chế:
- Một số metadata descriptions hoặc ordering có thể không ổn định theo assembler/version.
- Không nên phụ thuộc thứ tự attributes nếu không có ý nghĩa hợp đồng.
- Việc giữ snapshot quá cứng có thể khiến additive changes hợp lệ làm test fail.
- Chỉ so sánh metadata không bắt được semantic changes như đổi đơn vị hoặc timeout behavior.

Nên phân loại test thành **required legacy contract** và **new v2 contract**, đồng thời kiểm tra key semantics bằng integration assertions.

## 18. Versioning với CompositeData và MXBean

Một MBean có thể trả \`CompositeData\` hoặc một MXBean mapped type thay vì scalar attributes.

Ví dụ v1 schema:

~~~text
QueueSnapshot {
  pendingCount: int
  paused: boolean
}
~~~

v2 schema:

~~~text
QueueSnapshot {
  pendingCount: long
  processedCount: long
  paused: boolean
  capturedAtEpochMillis: long
}
~~~

Thay \`pendingCount\` từ int sang long hoặc đổi field names là breaking change cho client đọc schema cũ.

Một số thay đổi thêm field có thể tương thích với consumer chỉ chọn field bằng tên, nhưng client so sánh toàn bộ CompositeType hoặc deserialize theo class cứng vẫn có thể lỗi.

Chiến lược:
- Giữ v1 \`CompositeData\` schema trên ObjectName cũ.
- Công bố v2 dưới versioned ObjectName hoặc attribute mới có schema rõ.
- Ghi generation/timestamp và type metadata tường minh.
- Tránh trả DTO/JPA entity trực tiếp nếu remote clients không có cùng Java classes.
- Xác minh các type MXBean sử dụng thực sự hỗ trợ open-type mapping theo JDK.
- Giữ schema nhỏ, không trả collection không giới hạn qua JMX.

Không mặc định mọi Java record/generic type tự tương thích với MXBean mapping trong mọi version.

## 19. Versioning JMX notifications

Một số MBeans phát notifications và client có thể filter theo notification type.

Ví dụ:
~~~text
com.example.shop.queue.threshold.exceeded
~~~

Nếu v2 đổi tên thành:
~~~text
com.example.shop.queue.backlog.high
~~~

listener cũ lọc theo type v1 có thể bỏ lỡ sự kiện, dù MBean vẫn tồn tại. Những thay đổi cần được xem xét gồm:
- Notification type.
- Message format và userData schema.
- Ý nghĩa threshold.
- Sequence semantics.
- Frequency và guarantees khi reconnect.
- Attribute-change notification metadata nếu sử dụng.

Trong giai đoạn chuyển đổi, có thể giữ notification type cũ hoặc phát hai loại có chủ đích. Tuy nhiên việc phát gấp đôi events có thể làm automation chạy hai lần nếu clients subscribe rộng. Cần tài liệu và tests.

JMX notification không mặc định là durable queue có replay, nên migration không thể chỉ dựa vào listener nhận đủ mọi sự kiện.

## 20. Versioning của operations có side effects

Operations mang rủi ro lớn hơn getters khi thay đổi behavior.

Ví dụ v1:
~~~java
void resetStatistics();
~~~

v2 vẫn giữ tên nhưng mở rộng behavior để reset cả trạng thái worker hoặc xóa pending jobs. Đây là breaking semantic change nguy hiểm dù signature không đổi.

Phương án rõ:
- Giữ \`resetStatistics()\` chỉ reset monitoring counters như v1.
- Thêm operation mới \`resetQueueState()\` nếu thực sự cần.
- Đặt description và authorization policy rõ.
- Audit các operations có tác động.
- Tránh đưa destructive operations ra JMX nếu không có use case chính đáng.

Không đưa operation mới vào v2 rồi cấp quyền readwrite chung cho mọi monitoring client mà không kiểm tra least privilege.

## 21. Nâng cấp Spring Framework và Java JDK

Management contract có thể thay đổi ngoài ý muốn khi nâng version framework/runtime:

- Assembler hoặc metadata discovery thay đổi.
- Proxy mode hoặc target class resolution khác.
- Type mapping của MXBean/CompositeData khác.
- Naming strategy hoặc auto-configuration chọn ObjectName khác.
- Spring Boot Actuator JMX exposure defaults/properties thay đổi.
- JVM platform MBeans bổ sung attributes hoặc metadata.

Vì vậy kiểm thử phiên bản hóa không chỉ chạy lúc đổi code quản trị; nên chạy trong CI khi nâng Spring, Spring Boot, JDK hoặc thư viện cung cấp MBeans.

Trước khi nâng cấp:
1. Ghi nhận MBeanInfo của các contracts được người dùng phụ thuộc.
2. Chạy tests trên runtime mới.
3. So sánh danh sách ObjectNames và signatures quan trọng.
4. Kiểm tra collector/exporter rules.
5. Kiểm tra Java client proxies và remote serialization.
6. Kiểm tra authentication/access nếu connector được nâng cấp.

Không tự động coi mọi metadata diff là bug, nhưng phải biết thay đổi nào ảnh hưởng consumers.

## 22. Kế hoạch migration hai giai đoạn

Một quy trình có thể áp dụng:

### Giai đoạn A — Chuẩn bị v2

- Xác định mục tiêu business/operational của thay đổi.
- Phân loại additive hoặc breaking.
- Chọn ObjectName v2 và schema mới nếu breaking.
- Viết compatibility adapter v1 tiếp tục đọc cùng nguồn state.
- Kiểm tra getter costs và side effects.
- Tạo contract tests cho cả v1 và v2.
- Cập nhật tài liệu deprecation.

### Giai đoạn B — Triển khai song song

- Deploy v1 và v2 cùng JVM/MBeanServer với tên khác nhau.
- Đảm bảo một registration owner cho mỗi tên.
- Chạy JMX exporter hoặc dashboard shadow reading v2.
- So sánh giá trị trên cùng dữ liệu nguồn, chú ý differences về freshness.
- Di chuyển consumers sang v2 theo từng nhóm.
- Theo dõi lỗi AttributeNotFound/ReflectionException hoặc missing MBeans.

### Giai đoạn C — Ngừng sử dụng v1

- Kiểm kê được consumers còn dùng v1, kể cả scripts ít chạy.
- Thông báo lịch ngừng hỗ trợ và rollback plan.
- Loại bỏ MBean v1 trong phiên bản major hoặc cửa sổ bảo trì phù hợp.
- Cập nhật alerts/metrics để tránh false positives.
- Giữ giám sát về client errors sau deployment.

Nếu không có cách xác định mọi client (đặc biệt JConsole/scripts thủ công), cần thận trọng khi gỡ bỏ v1. Có thể duy trì alias lâu hơn nếu chi phí thấp và dữ liệu không nhạy cảm.

## 23. Giữ tương thích với metrics exporters và dashboards

Một JMX exporter có thể có rule dựa trên ObjectName và attribute:

~~~text
com.example.shop.orders:type=QueueMonitor,name=outbox
  attribute: PendingCount
  metric: shop_orders_pending
~~~

Nếu ObjectName đổi hoặc type chuyển từ number sang CompositeData, exporter rule có thể không tìm thấy dữ liệu hoặc phải đổi mapping.

Chọn chiến lược:
- Giữ metric name \`shop_orders_pending\` nếu semantics không thay đổi.
- Nếu đơn vị/semantics đổi, cân nhắc metric name mới và migration alerts.
- Không thêm version label tăng liên tục gây cardinality.
- Khi expose cả v1 và v2, tránh scrape đúp rồi cộng dữ liệu hai lần.
- Theo dõi gaps trong time series và cảnh báo về missing metrics.

JMX API version và metric name version là hai lớp riêng. Có thể giữ một metric ổn định khi thay implementation phía MBean nếu mapping và semantics không đổi.

## 24. Compatibility matrix mẫu

| Consumer | v1 | v2 | Migration |
|---|---|---|---|
| JConsole manual | ObjectName cũ | ObjectName v2 | Thông báo và hướng dẫn |
| JMX exporter | PendingCount int | PendingCount long | Cập nhật rules/kiểu |
| Java proxy client | QueueMonitorV1MBean | QueueMonitorV2MBean | Deploy client mới |
| Alert rules | shop_orders_pending | Metric map tương ứng | Shadow test trước khi switch |
| Automation pause | pause() | pause() hoặc operation mới | Kiểm tra signature/security |
| Support scripts | Hardcoded ObjectName | Versioned ObjectName | Phát hành script v2 |

Ma trận cần dựa trên hệ thống thật, không đoán rằng mọi consumers đều được nâng cấp cùng một lúc.

## 25. Rollback và registration lifecycle

Nếu v2 có lỗi sau deployment, rollback phải trả lời:
- V1 ObjectName còn tồn tại không?
- V1 có dùng cùng state source hay có cache riêng?
- Có operations v2 nào gây thay đổi state không tương thích ngược?
- Collector có còn scrape v1 không?
- Spring context shutdown unregister chính xác các MBeans thuộc quyền quản lý không?
- Có two exporters cạnh tranh và dùng \`IGNORE_EXISTING\`/\`REPLACE_EXISTING\` không?

Một migration tốt nên tránh sử dụng registration policy làm versioning. \`REPLACE_EXISTING\` không phải cơ chế transaction rollback cho MBeans.

Nếu v1 được giữ song song, rollback consumer thường đơn giản hơn: chuyển client về ObjectName cũ. Nhưng điều đó không đảm bảo dữ liệu nghiệp vụ đã thay đổi bởi v2 operations có thể rollback; phải xem behavior của từng operation.

## 26. Quy tắc versioning thực dụng

Một đội dự án có thể áp dụng:

1. **Không phá v1 vô tình.** Mọi thay đổi management contract cần được ghi nhận.
2. **Thêm được thì thêm.** Ưu tiên additive changes khi semantics cũ vẫn hợp lệ.
3. **Đổi semantics thì đổi tên/version.** Đặc biệt units và operation behavior.
4. **Giữ ObjectName v1 lịch sử.** Không “đẹp hóa” tên cũ trong migration.
5. **Không trộn source metadata.** Một MBean có management contract rõ: interface, MXBean hoặc annotations.
6. **Một owner mỗi registration.** Tránh duplicate exporters.
7. **Test contract runtime.** So sánh MBeanInfo, values và operation signatures.
8. **Theo dõi consumers.** Exporters, scripts, dashboards, alerts, local/remote clients.
9. **Dùng deprecation window.** Không xóa legacy endpoint trước khi consumer migration.
10. **An toàn vận hành trên hết.** Operations có side effects và JMX remote access cần review riêng.

## 27. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Client báo AttributeNotFoundException | Attribute đổi tên | Giữ alias hoặc migrate client |
| Client cast Integer thành Long lỗi | Return type thay đổi | V2 contract và conversion rõ |
| JConsole không thấy MBean | ObjectName v1 bị đổi | Giữ legacy name, thêm v2 name |
| Exporter mất metric | Rule dựa vào type/name cũ | Cập nhật mapping và shadow test |
| Dashboard vẽ sai 1000 lần | Đổi milliseconds sang seconds | Tên/units mới và migration |
| Operation invoke lỗi | Parameter signature khác | Version operation/client |
| Notification listener không chạy | Type/schema đổi | Giữ compatibility hoặc subscription migration |
| MXBean client không decode | OpenType schema thay đổi | Test mapping và version schema |
| Hai MBeans gây double count | V1/v2 cùng bị scrape | Loại trừ một nguồn hoặc gắn rules rõ |
| Rollback thất bại | V1 bị xóa trước, v2 thay state | Duy trì compatibility window |
| Spring upgrade thay metadata | Assembler/naming/proxy khác | Contract tests trên runtime mới |
| Operation cũ làm tác động mới | Semantic change không được version | Giữ old behavior, thêm new operation |

## 28. Bài tập thực hành

### Bài 1 — Phân loại thay đổi

Đánh giá các trường hợp: thêm \`ProcessedCount\`; đổi \`PendingCount\` từ int sang long; đổi \`getTimeoutMillis()\` thành \`getTimeoutSeconds()\`; thêm operation \`clearCache()\`; sửa description. Phân loại additive, breaking hoặc cần security review.

### Bài 2 — Thiết kế v1/v2 ObjectName

V1 hiện có \`com.example.shop.orders:type=QueueMonitor,name=outbox\`. Hãy tạo ObjectName v2 mà không làm thay tên v1. Viết JMX client có thể đọc cả hai trong migration window.

### Bài 3 — Contract test metadata

Tạo JUnit integration test kiểm tra v1 attribute \`PendingCount\` là \`int\`, v2 là \`long\`; đảm bảo operations cũ vẫn có mặt trên v1 và không có operation nội bộ bị công bố.

### Bài 4 — Migration metrics exporter

Một exporter rule dùng ObjectName cũ và PendingCount. Hãy đề xuất rule cho v2, cách tránh duplicate scraping và kế hoạch chuyển alert.

### Bài 5 — Notification compatibility

Một listener filter type \`queue.threshold.exceeded\`. Đề xuất migration khi v2 muốn type \`queue.backlog.high\`. Nêu nguy cơ phát hai notifications và gây action trùng.

### Bài 6 — Rollback

Giả lập v2 getter lỗi mapping. Hãy mô tả cách client chuyển về v1, cần giữ ObjectName nào, các tests nào chạy trước và sau rollback.

## 29. Tự kiểm tra

**1. Đổi tên attribute mà Java service vẫn compile có phải breaking change JMX không?** Có, client đọc tên cũ có thể gặp AttributeNotFoundException.

**2. Thêm attribute mới luôn hoàn toàn tương thích không?** Thường là additive, nhưng client schema cứng có thể không chấp nhận; cần kiểm chứng.

**3. Vì sao đổi int thành long cần versioning?** JMX runtime type thay đổi, Java proxy/cast và exporter mappings có thể không khớp.

**4. Có thể đặt version=v1 lên ObjectName cũ ngay lập tức không?** Không nếu clients đang hardcode tên không có version key; phải giữ alias/legacy name.

**5. REPLACE_EXISTING có phải cơ chế versioning an toàn không?** Không. Nó chỉ xử lý registration conflict và có thể làm mất contract cũ.

**6. MBeanInfo có đủ để đảm bảo tương thích semantics không?** Không. Cần tests về giá trị, units, side effects và thời điểm dữ liệu.

**7. MXBean có làm mọi custom DTO tự portable không?** Không. Type phải phù hợp open-type mapping và schema.

**8. Có cần version notification type không?** Có thể cần nếu đổi event/schema; listener cũ có thể bị bỏ lỡ.

## 30. Ghi nhớ

- **Management interface là API vận hành có consumers thật.**
- Backward compatibility gồm tên, kiểu, signatures, ObjectName, units, semantics, security và lifecycle.
- Thay đổi cộng dồn thường dễ giữ tương thích hơn thay đổi phá vỡ.
- Với breaking change, giữ v1 và công bố v2 ở ObjectName khác là chiến lược dễ kiểm soát.
- Không đổi ObjectName lịch sử chỉ để bổ sung version key.
- Không dùng registration policy thay cho migration plan.
- Kiểm tra MBeanInfo và gọi attributes/operations thật trong tests.
- Theo dõi JMX exporters, dashboards, alert rules và scripts khi đổi contract.
- Có kế hoạch deprecation, migration, rollback và cuối cùng mới retire v1.
- Đối với operation có side effects, thay đổi ngữ nghĩa có thể nguy hiểm hơn đổi signature.

## 31. Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — MBeanExporter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Java SE 21 — MBeanInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
- Java SE 21 — MBeanServer: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 — StandardMBean: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/StandardMBean.html
- Java SE 21 — MXBean: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MXBean.html
