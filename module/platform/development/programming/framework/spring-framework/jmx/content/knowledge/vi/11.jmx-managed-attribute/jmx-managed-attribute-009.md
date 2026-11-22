# Phân biệt attribute quản trị với field nội bộ trong Spring Framework JMX

## 1. Mục tiêu

Trong một Spring bean, **field nội bộ** dùng để lưu trạng thái và phục vụ implementation; **management attribute** là một phần của hợp đồng quản trị JMX mà client bên ngoài có thể đọc hoặc ghi thông qua MBeanServer. Hai khái niệm có thể liên quan đến cùng một giá trị nhưng không đồng nhất.

Ví dụ một service lưu field \`private int activeJobs\`; điều đó không có nghĩa JMX client được đọc nó. Chỉ khi MBean công bố một attribute tương ứng, chẳng hạn \`ActiveJobs\`, client mới có thể dùng \`MBeanServerConnection.getAttribute(objectName, "ActiveJobs")\`. Trong Spring, \`@ManagedAttribute\` giúp lựa chọn getter/setter nào trở thành attribute khi bean được export theo metadata.

Mục tiêu của bài:

- Phân biệt Java field, JavaBean property và JMX management attribute.
- Hiểu cách \`@ManagedAttribute\` biến phương thức truy cập thành giao diện quản trị.
- Kiểm soát read-only/read-write, tên, kiểu, đơn vị và ngữ nghĩa của attribute.
- Tránh vô tình tiết lộ state, secrets hoặc chi tiết implementation.
- Thiết kế management contract ổn định ngay cả khi cấu trúc field bên trong thay đổi.

## 2. Ba lớp khái niệm: field, property và JMX attribute

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| Java field | \`private int activeJobs;\` | Lưu state của object; visibility do Java access modifier quyết định |
| JavaBean property | \`getActiveJobs()\` | Giao diện truy cập logic theo quy ước getter/setter |
| JMX management attribute | \`ActiveJobs\` | Tên và metadata mà MBean công bố cho JMX client |
| Spring \`@ManagedAttribute\` | Annotation trên getter/setter | Chỉ dẫn cho metadata assembler chọn property để export qua JMX |

Một field có thể không có getter, hoặc getter có thể tính giá trị mà không dựa vào field tương ứng. Một JMX attribute cũng không nhất thiết là bản sao trực tiếp của field.

Ví dụ:

\`\`\`java
private final AtomicInteger running = new AtomicInteger();
private final AtomicInteger waiting = new AtomicInteger();

public int getTotalJobs() {
    return running.get() + waiting.get();
}
\`\`\`

Không có field \`totalJobs\`, nhưng \`getTotalJobs()\` vẫn là JavaBean property và có thể được expose thành JMX attribute \`TotalJobs\`. Ngược lại, có field \`password\` không có lý do để tạo một management attribute tên \`Password\`.

**Quy tắc quan trọng:** \`private\` chỉ ngăn truy cập field trực tiếp theo luật Java. Nếu một public getter trả về nội dung của field và được export qua JMX, client được cấp quyền vẫn có thể nhận giá trị đó.

## 3. Attribute trong JMX được đọc như thế nào?

JMX xác định MBean bằng \`ObjectName\`. Client dùng API:

\`\`\`java
Object value = connection.getAttribute(objectName, "ActiveJobs");
\`\`\`

Ở đây:

- \`connection\` là \`MBeanServerConnection\` hoặc \`MBeanServer\`.
- \`objectName\` xác định MBean đã đăng ký.
- \`"ActiveJobs"\` là tên **JMX attribute**, phân biệt chữ hoa/chữ thường.
- Giá trị do MBean tính toán/trả về khi phương thức quản lý tương ứng được gọi.

Nếu attribute cho phép ghi, client dùng:

\`\`\`java
connection.setAttribute(
    objectName,
    new javax.management.Attribute("Enabled", false)
);
\`\`\`

Client không trực tiếp đọc/ghi một Java field. MBean/adapter chịu trách nhiệm ánh xạ thao tác JMX vào getter/setter và logic ứng dụng; Spring có thể sinh metadata và adapter từ annotation.

Một JMX attribute có metadata như tên, kiểu, mô tả, khả năng đọc và ghi. \`MBeanInfo\` cho phép công cụ như JConsole khám phá contract, không cần biết class Java nội bộ.

## 4. Ví dụ Spring: field nội bộ và attribute quản trị

Xét một cache service:

\`\`\`java
package com.example.cache;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Service;

@Service
public class CacheService {
    private final AtomicLong hits = new AtomicLong();
    private final AtomicLong misses = new AtomicLong();
    private final String accessToken = "never-expose-this-value";

    public void recordHit() {
        hits.incrementAndGet();
    }

    public void recordMiss() {
        misses.incrementAndGet();
    }

    public long getHitCount() {
        return hits.get();
    }

    public long getMissCount() {
        return misses.get();
    }

    public double getHitRatio() {
        long hit = hits.get();
        long miss = misses.get();
        long total = hit + miss;
        return total == 0 ? 0.0 : (double) hit / total;
    }
}
\`\`\`

Ở đây \`hits\`, \`misses\`, \`accessToken\` là field nội bộ; phương thức \`getHitRatio()\` tính một thông số tổng hợp. Service được dùng trong nghiệp vụ và không nhất thiết phải trực tiếp chứa annotation JMX.

Ta có thể tạo management adapter riêng:

\`\`\`java
package com.example.management;

import com.example.cache.CacheService;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.cache:type=CacheMonitor,name=Primary",
    description = "Các chỉ số quản trị của cache"
)
public class CacheMonitor {
    private final CacheService service;

    public CacheMonitor(CacheService service) {
        this.service = service;
    }

    @ManagedAttribute(description = "Số lần cache hit")
    public long getHitCount() {
        return service.getHitCount();
    }

    @ManagedAttribute(description = "Số lần cache miss")
    public long getMissCount() {
        return service.getMissCount();
    }

    @ManagedAttribute(description = "Tỷ lệ hit trong khoảng 0.0 đến 1.0")
    public double getHitRatio() {
        return service.getHitRatio();
    }
}
\`\`\`

Bật annotation export:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
\`\`\`

MBean \`com.example.cache:type=CacheMonitor,name=Primary\` công bố các attribute \`HitCount\`, \`MissCount\`, \`HitRatio\`. Field \`accessToken\` không được export. Các getter trả trạng thái tổng hợp hoặc số liệu quan sát mà công cụ vận hành cần, còn chi tiết lưu state được giữ trong service.

Điểm đáng chú ý: adapter không cần field \`hitCount\` hoặc \`hitRatio\`; các attribute JMX là contract của phương thức, không phải ánh xạ 1:1 tới field.

## 5. Vì sao nên dùng management adapter?

Có thể đặt \`@ManagedResource\` trực tiếp lên service, nhưng adapter thường giúp ranh giới API quản trị rõ ràng hơn:

\`\`\`text
JMX client
    |
    v
ObjectName: com.example.cache:type=CacheMonitor,name=Primary
    |
    v
CacheMonitor (management adapter)
    |-- HitCount
    |-- MissCount
    |-- HitRatio
    |
    v
CacheService (business implementation)
    |-- hits field
    |-- misses field
    |-- cache storage
    |-- credentials/configuration
    |-- internal algorithms
\`\`\`

Ưu điểm:

1. Service có thể thay đổi tên field hoặc thuật toán mà attribute \`HitRatio\` vẫn tồn tại.
2. Adapter chỉ expose dữ liệu cần quản trị, không làm lộ toàn bộ public method của service.
3. Phần kiểm soát đơn vị, mô tả và snapshot có nơi triển khai riêng.
4. Có thể giữ Spring/JMX annotations ra khỏi module domain hoặc service cần tái sử dụng độc lập.
5. Bề mặt quản trị dễ được review như một API public, nhất là khi remote JMX được bật.

Không nhất thiết mỗi service phải có adapter riêng. Với service đơn giản, annotation trực tiếp có thể hợp lý; điều cần bảo đảm là **phạm vi phương thức được export** được xác định rõ và không vô tình mở rộng.

## 6. @ManagedAttribute chọn getter/setter, không “đánh dấu field”

Trong Spring JMX, \`@ManagedAttribute\` thường được đặt trên accessor method:

\`\`\`java
@ManagedAttribute(description = "Số job đang chạy")
public int getActiveJobs() {
    return scheduler.activeJobCount();
}
\`\`\`

Annotation này hướng dẫn Spring metadata assembler tạo JMX attribute có tên \`ActiveJobs\` theo quy ước JavaBean. Đặt annotation lên một private field rồi mong Spring xuất bản trực tiếp field đó không phải cách dùng tiêu chuẩn của \`@ManagedAttribute\`.

Với boolean property:

\`\`\`java
@ManagedAttribute
public boolean isEnabled() {
    return enabled;
}
\`\`\`

Tên JMX attribute thường là \`Enabled\`. Với getter có tiền tố \`get\`, ví dụ \`getQueueDepth()\`, attribute thường mang tên \`QueueDepth\`. Khi cần biết tên và quyền thực tế đã export, đọc \`MBeanInfo\` từ MBeanServer thay vì suy đoán từ field.

Method công bố attribute cần có chữ ký getter/setter hợp lệ và kiểu dữ liệu có thể biểu diễn qua JMX theo MBean model được dùng.

## 7. Read-only và read-write: khác biệt lớn

Một attribute chỉ đọc công bố thông tin, còn writable attribute cho phép client tác động lên ứng dụng.

### 7.1. Read-only attribute

\`\`\`java
@ManagedAttribute(description = "Số lượng tác vụ đang chờ")
public int getPendingTasks() {
    return taskQueue.pendingCount();
}
\`\`\`

Nếu không công bố setter tương ứng, JMX attribute \`PendingTasks\` chỉ đọc. Monitoring account thường chỉ cần những attribute kiểu này.

### 7.2. Writable attribute

\`\`\`java
private volatile boolean paused;

@ManagedAttribute(description = "Trạng thái tạm dừng")
public boolean isPaused() {
    return paused;
}

@ManagedAttribute(description = "Bật hoặc tắt trạng thái tạm dừng")
public void setPaused(boolean paused) {
    this.paused = paused;
}
\`\`\`

Khi getter/setter được export thành một JMX attribute thống nhất, client có thể dùng \`setAttribute\` để thay đổi giá trị. Setter không chỉ “ghi field”; nó là lời gọi quản trị từ bên ngoài nên có thể cần validation, audit, kiểm tra trạng thái và xử lý concurrency.

Ví dụ giới hạn runtime:

\`\`\`java
@ManagedAttribute
public int getMaxWorkers() {
    return workerPool.getMaxWorkers();
}

@ManagedAttribute
public void setMaxWorkers(int value) {
    if (value < 1 || value > 128) {
        throw new IllegalArgumentException(
            "maxWorkers must be in [1, 128]"
        );
    }
    workerPool.setMaxWorkers(value);
}
\`\`\`

Mọi client có quyền ghi attribute có thể gọi setter này. \`@ManagedAttribute\` không tự tạo RBAC; phân quyền phụ thuộc connector/MBeanServer/security layer, còn logic setter vẫn cần tự bảo vệ các invariant của ứng dụng.

## 8. Attribute quản trị không đồng nghĩa dữ liệu lưu trữ

Các loại management attribute thường gặp:

| Loại | Ví dụ | Nguồn dữ liệu |
| --- | --- | --- |
| Snapshot trạng thái | \`Health\`, \`Paused\`, \`QueueDepth\` | State hiện tại từ service |
| Counter | \`FailedJobs\`, \`CacheHits\` | Atomic counter/metrics |
| Derived value | \`HitRatio\`, \`UtilizationPercent\` | Tính từ các số liệu nền |
| Configuration view | \`MaxWorkers\`, \`TimeoutMillis\` | Cấu hình hiệu lực |
| Timestamp | \`LastRefreshEpochMillis\` | Event state hoặc clock |
| Summary | \`LastFailureCategory\` | Chuỗi an toàn đã tổng hợp |

Một management attribute có thể được tính tại thời điểm đọc; có thể là snapshot được cập nhật trước đó; hoặc có thể delegate sang hệ thống monitoring. Không có yêu cầu phải tồn tại field cùng tên.

Một attribute tốt nên rõ **đơn vị** và ngữ nghĩa. Ví dụ:

\`\`\`java
@ManagedAttribute(description = "Thời gian hoạt động tính theo mili giây")
public long getUptimeMillis() {
    return uptimeService.uptimeMillis();
}
\`\`\`

Nếu method trả \`-1\` khi dữ liệu không khả dụng, điều đó cần được mô tả như một phần contract; nếu không, client có thể xem \`-1\` là giá trị hợp lệ.

## 9. Tránh expose chi tiết implementation

Các field nội bộ có thể chứa:

- Password, token, API key, credential hoặc secret đã giải mã.
- Connection pool object, HTTP client, database handle, thread reference.
- Collection/cache lớn, bản ghi nghiệp vụ hoặc dữ liệu cá nhân.
- State trung gian khi thực hiện transaction.
- Đối tượng có vòng đời ngắn hoặc reference dễ mất hiệu lực.
- Thông tin có thể gây lộ cấu trúc bảo mật khi kết hợp với ObjectName và metadata.

Không nên viết:

\`\`\`java
@ManagedAttribute
public String getDatabasePassword() {
    return config.getDatabasePassword();
}
\`\`\`

Cũng không nên trả một object tổng hợp chứa secrets rồi tin rằng công cụ JMX chỉ hiển thị vài field. Khi cần vận hành, hãy trả dữ liệu đã sanitize:

\`\`\`java
@ManagedAttribute(description = "Trạng thái kết nối database")
public String getDatabaseConnectionState() {
    return dataSourceHealth.isReady() ? "READY" : "UNAVAILABLE";
}
\`\`\`

**Read-only không đồng nghĩa an toàn tuyệt đối.** Một JMX connector cấp quyền chỉ đọc vẫn có thể expose thông tin nhạy cảm qua attribute. Cần bảo vệ dữ liệu ngay từ contract và bảo vệ kết nối JMX bằng quyền truy cập phù hợp.

## 10. Attribute phải phù hợp với polling

JConsole và các hệ thống monitoring có thể gọi \`getAttribute\` lặp lại theo chu kỳ. Vì vậy getter quản trị nên:

- Hoàn tất nhanh và có giới hạn tài nguyên.
- Không có side effect như reset counter, xóa cache hoặc trigger job mới.
- Tránh truy vấn database lớn ở mỗi lần đọc.
- Không giữ lock quan trọng quá lâu.
- Trả snapshot nhất quán hoặc mô tả rõ khi số liệu chỉ mang tính xấp xỉ.
- Giới hạn độ dài chuỗi, tập dữ liệu hoặc số phần tử được expose.

Anti-pattern:

\`\`\`java
@ManagedAttribute
public long getProcessedCount() {
    return database.scanAllProcessedJobs(); // Có thể cực kỳ tốn kém.
}
\`\`\`

Hướng thiết kế tốt hơn:

\`\`\`java
@ManagedAttribute
public long getProcessedCount() {
    return metrics.getProcessedCount(); // Snapshot/counter đã duy trì.
}
\`\`\`

Nếu cần thao tác tốn thời gian, hãy cung cấp operation được mô tả rõ, ví dụ \`requestRecalculation()\`, còn attribute đọc kết quả gần nhất. Getter không nên biến thành một operation ẩn.

## 11. Thread safety khi expose field qua getter

Một private field có thể được nhiều thread nghiệp vụ cập nhật đồng thời, trong khi JMX client đọc từ thread khác. Java access modifier \`private\` không giải quyết memory visibility.

Ví dụ an toàn cho counter:

\`\`\`java
private final java.util.concurrent.atomic.AtomicLong failedJobs =
    new java.util.concurrent.atomic.AtomicLong();

public void recordFailure() {
    failedJobs.incrementAndGet();
}

@ManagedAttribute
public long getFailedJobs() {
    return failedJobs.get();
}
\`\`\`

Với cờ đơn giản:

\`\`\`java
private volatile boolean enabled = true;

@ManagedAttribute
public boolean isEnabled() {
    return enabled;
}
\`\`\`

Với nhiều field có quan hệ, có thể cần snapshot immutable, lock hoặc cơ chế đồng bộ khác để client không đọc một tổ hợp trạng thái không nhất quán:

\`\`\`java
record QueueSnapshot(long pending, long active, long completed) {}

private volatile QueueSnapshot latest =
    new QueueSnapshot(0, 0, 0);

@ManagedAttribute
public long getPending() {
    return latest.pending();
}
\`\`\`

Tuy nhiên, nếu JMX client gọi \`getPending\` và \`getActive\` ở hai thời điểm khác nhau, không bảo đảm hai giá trị đến từ cùng snapshot. Nếu cần một snapshot nguyên tử qua một lần đọc, cân nhắc expose một cấu trúc \`CompositeData\` hoặc MXBean-compatible value thay vì nhiều attribute rời.

## 12. Kiểu dữ liệu và khả năng truy cập từ xa

Với remote JMX, công cụ quản trị có thể chạy ở JVM khác, không có classpath của ứng dụng. Vì vậy nên ưu tiên primitive, \`String\`, kiểu JMX Open Types hoặc MXBean-compatible mapping.

Ví dụ không nên expose một object domain tùy biến trực tiếp:

\`\`\`java
@ManagedAttribute
public CustomerAggregate getCustomerAggregate() {
    return customerService.loadAggregate();
}
\`\`\`

Ngoài nguy cơ lộ dữ liệu, client có thể thiếu class \`CustomerAggregate\` hoặc gặp lỗi serialization.

Thay bằng các attribute tổng hợp:

\`\`\`java
@ManagedAttribute
public long getActiveCustomerCount() {
    return customerMetrics.activeCount();
}

@ManagedAttribute
public long getFailedSyncCount() {
    return customerMetrics.failedSyncCount();
}
\`\`\`

Nếu cần nhiều trường có quan hệ, \`CompositeData\` hoặc MXBean là lựa chọn tốt hơn để công bố schema mang tính quản trị. Cần chú ý giới hạn kích thước và tương thích schema khi phát triển API.

## 13. Tính ổn định: field có thể đổi, contract nên giữ

Giả sử phiên bản đầu dùng:

\`\`\`java
private long lastUpdateMillis;
\`\`\`

Sau một thời gian, implementation đổi sang \`Instant\`, database hoặc cache phân tán. Client vẫn có thể phụ thuộc vào attribute:

\`\`\`text
LastUpdateEpochMillis : long
\`\`\`

Ta giữ getter:

\`\`\`java
@ManagedAttribute(description = "Thời điểm cập nhật gần nhất, epoch millis")
public long getLastUpdateEpochMillis() {
    return stateStore.lastUpdate().toEpochMilli();
}
\`\`\`

Đây là lợi ích của tách biệt field nội bộ và attribute quản trị.

Các thay đổi dễ làm hỏng client:

| Thay đổi nội bộ hoặc contract | Tác động |
| --- | --- |
| Đổi tên field \`lastUpdateMillis\` | Không ảnh hưởng JMX nếu getter giữ nguyên |
| Đổi cách tính \`getHitRatio()\` nhưng giữ ý nghĩa | Có thể tương thích, cần thống nhất semantics |
| Đổi \`getHitRatio()\` thành \`getCacheEfficiency()\` | JMX attribute có thể đổi từ \`HitRatio\` sang \`CacheEfficiency\` |
| Đổi kiểu \`long\` thành \`String\` | Client ép kiểu có thể thất bại |
| Đổi đơn vị milliseconds thành seconds, giữ cùng tên | Sai lệch diễn giải dữ liệu |
| Thêm setter cho attribute chỉ đọc | Mở rộng quyền điều khiển runtime |
| Xóa một attribute đang được monitoring sử dụng | Dashboard/script có thể thất bại |

Hãy coi các attribute JMX là giao diện public đối với công cụ vận hành: tên, kiểu, đơn vị, tính writable và semantics nên được quản lý tương thích qua các release.

## 14. Xem MBeanInfo để biết cái gì thật sự được export

Không nên đoán JMX attribute từ danh sách field của class. Có thể hỏi MBeanServer:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name =
    new ObjectName("com.example.cache:type=CacheMonitor,name=Primary");

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.printf(
        "%s : %s, readable=%s, writable=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable()
    );
}
\`\`\`

Đoạn code giả định exporter đã đăng ký MBean vào chính platform MBeanServer. Nếu ứng dụng dùng server khác, cần truy cập đúng server đã đăng ký.

Output có thể có dạng:

\`\`\`text
HitCount : long, readable=true, writable=false
MissCount : long, readable=true, writable=false
HitRatio : double, readable=true, writable=false
\`\`\`

Tên kiểu và biểu diễn phụ thuộc MBean model, nhưng ý nghĩa là metadata cho biết contract thực tế. Nếu một field không xuất hiện trong \`MBeanInfo\`, client không thể đọc nó như một attribute của MBean đó chỉ nhờ biết tên field.

## 15. Attribute và operation là hai loại giao diện khác nhau

Attribute trả về hoặc nhận một trạng thái; operation diễn tả một hành động quản trị.

\`\`\`java
@ManagedAttribute
public int getQueueDepth() {
    return queue.depth();
}

@ManagedOperation(description = "Yêu cầu chạy lại các job thất bại")
public void requestRetryFailures() {
    retryService.requestRetries();
}
\`\`\`

Một action có tác động phụ lớn không nên được giấu trong getter:

\`\`\`java
// Không nên:
@ManagedAttribute
public int getQueueDepth() {
    retryService.retryFailedJobs();
    return queue.depth();
}
\`\`\`

Việc công cụ liên tục đọc \`QueueDepth\` có thể vô tình kích hoạt retry nhiều lần. Thao tác nên được expose qua operation với tên, validation và quyền rõ ràng.

Tương tự, setter writable attribute phù hợp với thay đổi state/configuration có nghĩa rõ ràng; các hành động phức tạp nhiều bước thường dễ quản lý hơn dưới operation được thiết kế chuyên dụng.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Field có giá trị nhưng JConsole không thấy | Field chưa được expose qua metadata JMX | Tạo getter hợp lệ, \`@ManagedAttribute\`, kiểm tra exporter |
| Getter public nhưng không có trong MBeanInfo | Annotation/assembler không chọn getter | Xem \`@ManagedAttribute\` và cấu hình export |
| Client gọi \`getAttribute(..., "activeJobs")\` bị lỗi | Tên JMX là \`ActiveJobs\`, phân biệt hoa/thường | Đọc tên thực tế trong \`MBeanInfo\` |
| Attribute chỉ đọc dù class có setter | Setter không được export hoặc metadata không ghép thành writable | Kiểm tra getter/setter và \`MBeanInfo\` |
| Setter bị gọi nhưng state không cập nhật đúng | Concurrency hoặc logic validation | Dùng đồng bộ phù hợp, kiểm tra invariant |
| Monitoring chậm hoặc gây tải | Getter làm việc nặng | Trả counter/snapshot, giới hạn kích thước |
| Remote client không đọc được object tùy biến | Kiểu không tương thích/classpath hoặc serialization | Ưu tiên primitive/Open Types/MXBean |
| Dữ liệu nhạy cảm lộ dù field private | Getter quản trị trả field đó | Loại bỏ hoặc sanitize attribute |
| MBean không tìm thấy | Sai ObjectName/MBeanServer hoặc exporter chưa chạy | Kiểm tra đăng ký, naming và đúng server |

## 17. Mô hình tư duy

\`\`\`text
Spring bean implementation
    |
    +-- private fields
    |      - counters
    |      - connections
    |      - credentials
    |      - caches
    |      - runtime state
    |
    +-- public getters/setters / computed values
               |
               +-- lựa chọn bằng @ManagedAttribute
               |
               v
       Spring JMX MBeanExporter
               |
               v
         JMX MBeanInfo
               |
        +------+------+
        |             |
    attributes     operations
        |
        v
JConsole / VisualVM / JMX client
\`\`\`

**Ghi nhớ:** **Field nội bộ là chi tiết implementation; management attribute là hợp đồng công khai của MBean.** \`@ManagedAttribute\` chọn accessor được công bố, không làm field tự động trở thành tài nguyên JMX. Hãy expose số liệu quản trị cần thiết, ưu tiên read-only, giữ getter nhanh và an toàn, dùng kiểu dữ liệu tương thích và duy trì tên/đơn vị/semantics ổn định qua các phiên bản Spring application.
