# Kiểu property được JMX hỗ trợ trong Spring @ManagedAttribute

## 1. Vì sao cần hiểu kiểu dữ liệu của JMX attribute?

Trong Spring Framework JMX, \`@ManagedAttribute\` đánh dấu getter hoặc setter cần xuất hiện như một **JMX attribute** của MBean. Nhưng có annotation không có nghĩa mọi kiểu Java đều có thể được mọi JMX client đọc, ghi hoặc hiển thị theo cùng cách.

Có ba câu hỏi cần tách riêng:

1. **Spring có nhận diện property làm managed attribute không?** Đây là vai trò của \`@ManagedAttribute\`, \`MBeanInfoAssembler\` và \`MBeanExporter\`.
2. **MBeanServer có thể biểu diễn kiểu của attribute không?** Với Standard MBean, Dynamic MBean và Model MBean, metadata thường phản ánh tên kiểu Java; với MXBean, Java Management API quy định ánh xạ sang *Open Types*.
3. **Client JMX có tiêu thụ giá trị được không?** Việc truyền dữ liệu qua JMX remote phụ thuộc serialization, class availability, security filter và khả năng hiển thị của client. Một kiểu hợp lệ tại server chưa chắc phù hợp với monitoring client bên ngoài JVM.

Bài học giúp bạn chọn kiểu property an toàn, ổn định và dễ quan sát, đồng thời tránh nhầm lẫn giữa **Spring managed attribute**, **JMX attribute** và **MXBean OpenType**.

### Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt property getter/setter với JMX attribute thực tế.
- Nắm các kiểu scalar, mảng, enum, Java object và cấu trúc OpenType.
- Giải thích khác biệt giữa Standard MBean/Model MBean và MXBean.
- Chọn kiểu dữ liệu phù hợp cho JMX management API.
- Kiểm tra \`MBeanAttributeInfo\`, \`MBeanInfo\` và \`OpenMBeanAttributeInfo\`.
- Thiết kế các managed attributes có read/write semantics rõ ràng, tránh phụ thuộc vào Java class nội bộ.

## 2. Từ Java property đến JMX attribute

Ví dụ một Spring bean:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.monitoring:type=Queue,name=Orders"
)
public class OrderQueueMonitor {
    private volatile int pendingCount;

    @ManagedAttribute(description = "Number of pending orders")
    public int getPendingCount() {
        return pendingCount;
    }

    @ManagedAttribute(description = "Adjust pending count")
    public void setPendingCount(int pendingCount) {
        this.pendingCount = pendingCount;
    }
}
\`\`\`

Property \`pendingCount\` theo JavaBeans convention có getter và setter. Khi Spring JMX annotation metadata được xử lý bằng exporter/assembler phù hợp, nó có thể xuất thành **một JMX attribute** tên \`PendingCount\`, kiểu \`int\`, đọc và ghi được.

\`\`\`text
Java methods
    getPendingCount() : int
    setPendingCount(int) : void
           |
           v
Spring JMX attribute metadata
           |
           v
JMX MBeanInfo
    name = "PendingCount"
    type = "int"
    readable = true
    writable = true
           |
           v
MBeanServer.getAttribute/setAttribute
\`\`\`

Cần chú ý:

- Annotation chỉ cung cấp metadata. Ứng dụng phải bật JMX export.
- Getter và setter phải nhất quán về property name và kiểu.
- Có getter mà không có setter được expose thì attribute chỉ đọc.
- Có setter nhưng không có getter được expose thì attribute chỉ ghi nếu implementation hỗ trợ.
- Việc setter chấp nhận một giá trị **không đồng nghĩa** người gọi được phép thay đổi state. Cần kiểm soát quyền JMX.

## 3. JMX hỗ trợ kiểu theo những tầng nào?

Các khái niệm chính:

| Thành phần | Định nghĩa | Ý nghĩa đối với kiểu |
|---|---|---|
| **Standard MBean** | Interface theo convention \`XxxMBean\` | Java methods trong interface quy định kiểu của attribute/operation |
| **Dynamic MBean** | Implement \`DynamicMBean\` và trả \`MBeanInfo\` | Tự định nghĩa kiểu metadata và cách xử lý giá trị |
| **Model MBean** | Dạng Dynamic MBean có descriptor quản trị | Spring có thể dùng để expose bean với metadata annotation |
| **MXBean** | MBean tuân thủ quy tắc ánh xạ kiểu của MXBean | Thông số và giá trị được ánh xạ sang **Open Types** chuẩn JMX |

**Quy tắc quan trọng:** Không nên nói “JMX chỉ hỗ trợ primitive và String”. MBean thông thường có thể dùng nhiều loại Java serializable; tuy nhiên mức độ tương thích qua mạng và giữa các client sẽ giảm khi expose các kiểu ứng dụng tùy biến.

Ngược lại, không nên nói “đã là Java object thì JMX remote sẽ hoạt động”. Không phải object nào cũng serializable; remote client có thể thiếu class hoặc bị từ chối deserialize.

MXBean giúp giải quyết vấn đề này bằng một tập Open Types có quy tắc chuyển đổi.

## 4. Những kiểu property cơ bản thường phù hợp

Với các managed attribute dùng cho monitoring và vận hành, nên ưu tiên các kiểu đơn giản:

| Java type | Giá trị thường gặp | Dùng cho |
|---|---|---|
| \`boolean\`/\`Boolean\` | \`true\`, \`false\` | Bật/tắt tính năng hoặc trạng thái |
| \`byte\`/\`Byte\` | Số nguyên nhỏ | Trường hợp có biên xác định |
| \`short\`/\`Short\` | Số nguyên nhỏ | Số liệu đơn giản |
| \`int\`/\`Integer\` | \`12\` | Số worker, số connection |
| \`long\`/\`Long\` | \`120000L\` | Tổng số tác vụ, thời gian dạng số |
| \`float\`/\`Float\` | \`0.5f\` | Giá trị đo cần phần thập phân |
| \`double\`/\`Double\` | \`98.6\` | Tỷ lệ, số liệu dạng số thực |
| \`char\`/\`Character\` | \`'A'\` | Ký tự điều khiển đơn lẻ |
| \`String\` | \`"RUNNING"\` | Trạng thái, hostname, phiên bản |

Ví dụ:

\`\`\`java
@ManagedAttribute
public boolean isHealthy() {
    return healthy;
}

@ManagedAttribute
public long getProcessedCount() {
    return processedCount.get();
}

@ManagedAttribute
public String getStatus() {
    return "RUNNING";
}

@ManagedAttribute
public double getLoadRatio() {
    return loadRatio;
}
\`\`\`

Ưu điểm: metadata dễ đọc, client hiển thị thuận tiện, ít phụ thuộc vào class ứng dụng. Tuy nhiên \`null\` với wrapper, \`NaN\`/\`Infinity\` với floating-point và giá trị ngoài miền mong đợi vẫn cần được xử lý theo hợp đồng.

### Dùng kiểu nào cho trạng thái?

Nếu trạng thái thuộc tập giá trị nhỏ, có thể dùng \`String\` có hợp đồng rõ ràng:

\`\`\`java
@ManagedAttribute(description = "IDLE, RUNNING, FAILED or COMPLETED")
public String getState() {
    return currentState.name();
}
\`\`\`

Đây là lựa chọn thân thiện với client JMX không biết enum của ứng dụng. Nếu dùng trực tiếp enum, cần kiểm tra khả năng tương thích của loại MBean và remote client.

## 5. Kiểu String và giới hạn của cách biểu diễn

\`String\` thường là lựa chọn tốt cho:

- Trạng thái máy chủ.
- Build version.
- Tên cấu hình không nhạy cảm.
- Định danh instance.
- Mô tả ngắn cho operator.

Nhưng một chuỗi không có cấu trúc có giới hạn:

\`\`\`java
@ManagedAttribute
public String getQueueState() {
    return "pending=14,active=3,failed=1";
}
\`\`\`

Client phải parse lại chuỗi tự chế, dễ lỗi khi format thay đổi. Với ba giá trị độc lập, thường tốt hơn khi expose ba scalar attributes (\`PendingCount\`, \`ActiveCount\`, \`FailedCount\`) hoặc dùng OpenType có cấu trúc.

Không nên nhét JSON khối lượng lớn vào một \`String\` rồi coi nó là API typed. Nếu cần biểu diễn cấu trúc, cân nhắc \`CompositeData\` hoặc \`TabularData\` với hợp đồng ổn định.

Ngoài ra, không expose password, token, key hay dữ liệu cá nhân qua managed attributes, kể cả khi giá trị là String “chỉ để debug”.

## 6. Arrays và collections

### 6.1. Mảng

JMX có thể biểu diễn mảng trong nhiều loại MBean; với MXBean/OpenType, \`ArrayType\` mô tả mảng các kiểu OpenType hợp lệ.

Ví dụ:

\`\`\`java
@ManagedAttribute(description = "Configured cluster nodes")
public String[] getNodeNames() {
    return new String[] {"node-a", "node-b"};
}
\`\`\`

Mảng String là kiểu tương đối dễ tiêu thụ trong client. Nên trả bản sao hoặc giá trị snapshot nếu dữ liệu nội bộ có thể bị thay đổi đồng thời.

\`\`\`java
@ManagedAttribute
public int[] getQueueDepthHistory() {
    return history.clone();
}
\`\`\`

Cần tránh trả trực tiếp mảng mutable nội bộ khi code local có thể sửa nó. Với remote client, serialization có thể tạo bản sao, nhưng không nên dựa vào hành vi remote để bảo vệ state local.

### 6.2. List, Set, Map

\`List<String>\`, \`Map<String, Integer>\` hoặc collection tùy biến không đồng nghĩa với một OpenType JMX tương ứng trong mọi trường hợp.

Trong Standard/Model MBean, bạn có thể gặp việc truyền object Java đã serialize. Khi đó client phải tương thích với kiểu và class liên quan. Với **MXBean**, framework có quy tắc mapping các kiểu khai báo thích hợp sang dữ liệu OpenType; điều kiện và cấu trúc mapping cần thỏa JMX specification.

Vì thế:

- Không mặc định collection là unsupported.
- Không mặc định mọi collection đều được client remote tiêu thụ như dữ liệu độc lập với class.
- Nếu thiết kế management API cho hệ thống khác JVM, cân nhắc xuất thành scalar, String array, \`CompositeData\` hoặc \`TabularData\` rõ ràng.
- Tránh collection quá lớn hoặc cập nhật liên tục, vì mỗi lần \`getAttribute()\` có thể tốn CPU, bộ nhớ và mạng.

## 7. Enum, Date, ObjectName và những kiểu đặc biệt

### Enum

\`\`\`java
public enum WorkerState {
    IDLE, RUNNING, FAILED
}
\`\`\`

Một Standard MBean có thể expose enum như Java type khi đường truyền và client hỗ trợ; MXBean có quy tắc mapping enum sang dạng mở phù hợp, thường là String name.

Để API quản trị dễ tương thích với client đơn giản:

\`\`\`java
@ManagedAttribute
public String getWorkerState() {
    return state.name();
}
\`\`\`

Việc lựa chọn enum trực tiếp hay String cần căn cứ vào phạm vi tích hợp và dạng MBean, không chỉ khả năng compile của Java.

### Date và thời gian

\`java.util.Date\` là một Java object có thể dùng trong một số MBean, nhưng không thuộc nhóm SimpleType phổ biến của Open MBean. MXBean mapping cho kiểu thời gian phụ thuộc quy tắc type mapping cụ thể.

Nếu client cần giá trị ổn định, dễ so sánh:

\`\`\`java
@ManagedAttribute(description = "Last successful run, epoch millis")
public long getLastSuccessfulRunEpochMillis() {
    return lastSuccessMillis;
}
\`\`\`

Nêu rõ đơn vị \`milliseconds since Unix epoch\`. Đừng đưa thời điểm dạng \`String\` mơ hồ thiếu timezone/format specification.

### ObjectName

\`javax.management.ObjectName\` còn có thể xuất hiện trong hệ thống metadata/quản trị để tham chiếu MBean khác. Trong Open MBean, \`ObjectName\` thuộc tập SimpleType được hỗ trợ.

Ví dụ thuộc tính tham chiếu:

\`\`\`java
@ManagedAttribute
public ObjectName getSchedulerMBean() {
    return schedulerName;
}
\`\`\`

Sử dụng khi client thật sự cần danh tính JMX của một đối tượng liên quan. Không dùng ObjectName làm thay thế cho mọi ID nghiệp vụ.

### BigDecimal, BigInteger và các kiểu số mở

\`java.math.BigDecimal\` và \`java.math.BigInteger\` là các kiểu đơn giản được OpenType hỗ trợ. Chúng phù hợp với giá trị cần độ chính xác cụ thể, nhưng hãy kiểm tra client hiển thị/tính toán đúng và tránh dùng kiểu số lớn nếu một \`long\` có đơn vị rõ ràng đã đủ.

## 8. Open MBean và tập Open Types chuẩn

JMX Open MBean định nghĩa các kiểu có thể mô tả được bằng metadata chuẩn, giúp client không phải biết class nghiệp vụ tùy biến.

Các lớp trong \`javax.management.openmbean\`:

| OpenType | Biểu diễn |
|---|---|
| \`SimpleType\` | Kiểu scalar chuẩn như String, Boolean, Integer, Long, Double, BigDecimal, BigInteger, ObjectName... |
| \`ArrayType\` | Mảng phần tử có kiểu OpenType |
| \`CompositeType\` | Schema của một record/đối tượng gồm nhiều thuộc tính được đặt tên |
| \`TabularType\` | Schema của một bảng các record CompositeType, có chỉ mục |
| \`OpenType\` | Lớp cơ sở mô tả hệ kiểu Open MBean |

Giá trị thực tế:

| OpenType schema | Value object |
|---|---|
| \`SimpleType\` | Object thuộc kiểu simple tương ứng |
| \`ArrayType\` | Mảng có element type thích hợp |
| \`CompositeType\` | \`CompositeData\` |
| \`TabularType\` | \`TabularData\` |

**Phân biệt:** \`CompositeType\` mô tả **schema**, còn \`CompositeData\` chứa **dữ liệu**. Tương tự \`TabularType\` là schema và \`TabularData\` là giá trị dạng bảng.

### Vì sao Open Types hữu ích?

Một class như \`com.example.internal.QueueSnapshot\` có thể không có trong classpath của JConsole hoặc remote monitoring service. Nếu server gửi trực tiếp object đó, client có thể không giải mã được.

Khi dữ liệu được trình bày bằng \`CompositeData\`, client chỉ cần biết JMX Open MBean API và schema, giảm phụ thuộc vào thư viện nghiệp vụ bên server.

## 9. Ví dụ CompositeData: một trạng thái nhiều trường

Giả sử cần xuất snapshot hàng đợi gồm \`pending\`, \`active\`, \`status\`. Có thể tạo \`CompositeDataSupport\`:

\`\`\`java
import javax.management.openmbean.CompositeData;
import javax.management.openmbean.CompositeDataSupport;
import javax.management.openmbean.CompositeType;
import javax.management.openmbean.OpenType;
import javax.management.openmbean.SimpleType;

public final class QueueOpenData {

    private static final CompositeType TYPE;

    static {
        try {
            TYPE = new CompositeType(
                "QueueSnapshot",
                "Current queue status",
                new String[] {"pending", "active", "status"},
                new String[] {
                    "Pending jobs",
                    "Active jobs",
                    "State"
                },
                new OpenType<?>[] {
                    SimpleType.INTEGER,
                    SimpleType.INTEGER,
                    SimpleType.STRING
                }
            );
        } catch (Exception ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    private QueueOpenData() {}

    public static CompositeData snapshot(
            int pending,
            int active,
            String status) throws Exception {

        return new CompositeDataSupport(
            TYPE,
            new String[] {"pending", "active", "status"},
            new Object[] {pending, active, status}
        );
    }
}
\`\`\`

Một getter có thể trả \`CompositeData\`:

\`\`\`java
@ManagedAttribute(description = "Queue snapshot")
public CompositeData getQueueSnapshot() throws Exception {
    return QueueOpenData.snapshot(
        pendingCount.get(),
        activeCount.get(),
        state.get()
    );
}
\`\`\`

Ở client:

\`\`\`java
CompositeData snapshot = (CompositeData) server.getAttribute(
    objectName, "QueueSnapshot"
);

int pending = (Integer) snapshot.get("pending");
String state = (String) snapshot.get("status");
\`\`\`

Lợi ích: client biết các trường qua OpenType schema. Hạn chế: xây dựng dữ liệu và quản lý schema phức tạp hơn scalar getters. Nếu chỉ cần một hoặc hai phép đo, scalar attributes thường dễ đọc và bảo trì hơn.

### Khi nào dùng TabularData?

Khi cần expose một tập bản ghi có schema cố định, ví dụ danh sách cache region với \`name\`, \`size\`, \`hitCount\`, \`TabularData\` có thể phù hợp.

Không dùng \`TabularData\` cho bảng rất lớn hoặc dữ liệu liên tục streaming nếu việc đọc toàn bộ snapshot gây tải đáng kể. JMX attribute thường phục vụ quản trị, không phải query engine cho dữ liệu nghiệp vụ khối lượng lớn.

## 10. MXBean và tự động mapping Java types

MXBean giúp biểu diễn Java interface quản trị qua Open Types.

Ví dụ:

\`\`\`java
public interface WorkerHealthMXBean {
    String getState();
    long getProcessedCount();
}
\`\`\`

\`\`\`java
public class WorkerHealth implements WorkerHealthMXBean {
    @Override
    public String getState() {
        return "RUNNING";
    }

    @Override
    public long getProcessedCount() {
        return 1200L;
    }
}
\`\`\`

MXBean có quy ước ánh xạ Java types sang Open Types. Với các kiểu phức tạp, rules cụ thể quyết định chúng có thể chuyển thành \`CompositeData\` hay \`TabularData\` không. Nếu một Java type không có mapping hợp lệ, MBean registration hoặc invocation có thể thất bại.

Đừng mặc định annotation \`@ManagedResource\` **biến một bean thành MXBean**. Spring annotation-driven export thông thường có thể tạo Model MBean/metadata-based exposure; cơ chế MXBean có hợp đồng và quy tắc type mapping riêng.

Khi mục tiêu là remote interoperability và typed management interface, có thể cân nhắc MXBean rõ ràng hoặc expose OpenType từ MBean. Khi cần metadata annotation thuận tiện, sử dụng \`@ManagedAttribute\` với các kiểu client có thể tiêu thụ và kiểm chứng trên đường kết nối thực tế.

## 11. Những kiểu nên hạn chế expose trực tiếp

### 11.1. Entity/JPA hoặc domain object

\`\`\`java
@ManagedAttribute
public CustomerEntity getLatestCustomer() {
    return repository.findLatest();
}
\`\`\`

Thiết kế này không phù hợp trong đa số bối cảnh:
- Có thể làm lộ dữ liệu khách hàng.
- Phụ thuộc class/schema nghiệp vụ.
- Có thể kích hoạt lazy loading ngoài ý muốn.
- Remote serialization có thể thất bại.
- Có thể khiến getter tốn thời gian truy vấn.

Thay bằng các dữ liệu quản trị phù hợp:

\`\`\`java
@ManagedAttribute
public long getCustomerRecordsProcessed() {
    return processedCount.get();
}
\`\`\`

### 11.2. Spring beans và infrastructure object

Tránh trả trực tiếp \`ApplicationContext\`, \`DataSource\`, \`EntityManager\`, \`Thread\`, \`ExecutorService\`, \`HttpServletRequest\` hay những object có vòng đời/tài nguyên phức tạp. Client không cần giữ tham chiếu vào toàn bộ đối tượng đó để hiểu trạng thái.

Thay bằng scalar, String và snapshot phù hợp:

\`\`\`java
@ManagedAttribute
public int getActiveThreads() {
    return executor.getActiveCount();
}
\`\`\`

### 11.3. Stream, file, socket, callback

Các đối tượng như \`InputStream\`, \`Socket\`, \`Runnable\` không nên là thuộc tính JMX để client lấy qua mạng. Chúng không đại diện cho snapshot dữ liệu quản trị ổn định và thường không có serialization contract thích hợp.

### 11.4. Generic Object

\`\`\`java
@ManagedAttribute
public Object getState() {
    return someInternalObject;
}
\`\`\`

Metadata \`java.lang.Object\` quá mơ hồ; client không biết kiểu thực tế và có thể thất bại khi deserialize. Tránh kiểu \`Object\` nếu có thể định nghĩa type contract cụ thể.

## 12. Read-only, writable và kiểu setter

Một attribute có thể có các thuộc tính truy cập:

- **Readable:** có getter được expose.
- **Writable:** có setter được expose.
- **Is:** getter boolean theo quy ước \`isEnabled()\`.

Ví dụ read-only:

\`\`\`java
@ManagedAttribute(description = "Current queue depth")
public int getQueueDepth() {
    return queueDepth.get();
}
\`\`\`

Ví dụ writable:

\`\`\`java
private volatile boolean paused;

@ManagedAttribute
public boolean isPaused() {
    return paused;
}

@ManagedAttribute
public void setPaused(boolean paused) {
    this.paused = paused;
}
\`\`\`

Nếu quản trị viên muốn chỉnh một cấu hình quan trọng, cần kiểm tra giá trị:

\`\`\`java
private volatile int maxConcurrentJobs = 8;

@ManagedAttribute
public int getMaxConcurrentJobs() {
    return maxConcurrentJobs;
}

@ManagedAttribute
public void setMaxConcurrentJobs(int count) {
    if (count < 1 || count > 128) {
        throw new IllegalArgumentException(
            "maxConcurrentJobs must be between 1 and 128"
        );
    }
    maxConcurrentJobs = count;
}
\`\`\`

JMX metadata chỉ nói type là \`int\`; nó **không tự bảo đảm** giá trị thuộc miền nghiệp vụ \`1..128\`. Setter phải validate và cơ chế quản trị phải bảo vệ quyền truy cập.

Không nên expose setter chỉ vì Java property có setter nội bộ. Mỗi writable attribute mở thêm bề mặt thay đổi trạng thái runtime.

## 13. Kiểm tra kiểu thuộc tính qua MBeanInfo

Sau khi export MBean, có thể kiểm tra metadata:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.monitoring:type=Queue,name=Orders"
);

if (server.isRegistered(name)) {
    MBeanInfo info = server.getMBeanInfo(name);

    for (MBeanAttributeInfo attribute : info.getAttributes()) {
        System.out.printf(
            "%s | type=%s | readable=%s | writable=%s%n",
            attribute.getName(),
            attribute.getType(),
            attribute.isReadable(),
            attribute.isWritable()
        );
    }
}
\`\`\`

\`MBeanAttributeInfo.getType()\` cho biết tên kiểu khai báo trong metadata, ví dụ \`int\`, \`java.lang.String\` hoặc tên class khác. Nó không đủ để kết luận remote client chắc chắn nhận được một object phức tạp.

Nếu attribute có Open MBean metadata:

\`\`\`java
import javax.management.openmbean.OpenMBeanAttributeInfo;

for (MBeanAttributeInfo attr : info.getAttributes()) {
    if (attr instanceof OpenMBeanAttributeInfo openAttr) {
        System.out.println(openAttr.getOpenType());
    }
}
\`\`\`

Lưu ý \`MBeanAttributeInfo\` và \`OpenMBeanAttributeInfo\` là những kiểu API khác nhau; không phải mọi MBeanAttributeInfo đều triển khai interface Open MBean. Một số implementation có thể công bố thông tin OpenType qua descriptor. Khi viết tooling chung, phải xử lý các khả năng metadata thực tế được trả về.

### Kiểm tra giá trị thực tế

\`\`\`java
Object value = server.getAttribute(name, "PendingCount");
System.out.println(value);
\`\`\`

Khi gọi \`getAttribute\`, cần xử lý các exception như \`AttributeNotFoundException\`, \`MBeanException\`, \`ReflectionException\` hoặc lỗi truyền thông trong remote scenario. Một getter có thể thất bại dù kiểu của nó đã hiện trong metadata.

Với \`setAttribute\`, sử dụng \`javax.management.Attribute\`:

\`\`\`java
import javax.management.Attribute;

server.setAttribute(
    name,
    new Attribute("MaxConcurrentJobs", 16)
);
\`\`\`

Giá trị phải đúng kiểu và đáp ứng validation; một client gửi String \`"16"\` không đương nhiên tương đương với Integer \`16\`.

## 14. Kiểm tra interoperability với remote JMX

Một MBean có thể chạy hoàn hảo trong cùng JVM nhưng lỗi khi truy cập từ xa. Nguyên nhân thường gặp:

- Class application không có ở client.
- Object không serializable.
- \`serialVersionUID\` hoặc phiên bản class không tương thích.
- Serialization filter từ chối class.
- Collection chứa phần tử thuộc kiểu không tương thích.
- Object graph quá lớn, cycle phức tạp hoặc truyền dữ liệu quá nhiều.
- Remote client chỉ biết hiển thị scalar/OpenType chuẩn.

Chiến lược giảm rủi ro:

1. Dùng kiểu scalar đơn giản cho attribute phổ biến.
2. Dùng String hoặc mã trạng thái cho enum khi client độc lập với ứng dụng.
3. Với cấu trúc, ưu tiên OpenType hoặc MXBean có schema ổn định.
4. Cung cấp đơn vị đo và ý nghĩa rõ ràng trong description.
5. Tránh object có side effect, lazy-loading hoặc phụ thuộc tài nguyên nội bộ.
6. Chạy kiểm thử với một client **không chứa toàn bộ classpath server** để xác minh hợp đồng remote.
7. Không mở JMX remote ra Internet nếu không có bảo vệ thích hợp.

## 15. Kiểu property và chi phí giám sát

Getter \`@ManagedAttribute\` có thể được gọi nhiều lần bởi công cụ quản trị. Một kiểu dữ liệu dễ serialize vẫn có thể gây tải lớn nếu getter:

- Query database mỗi lần gọi.
- Duyệt toàn bộ hàng triệu bản ghi.
- Chụp một collection có hàng trăm nghìn phần tử.
- Chờ I/O hoặc lock.
- Tạo các object có kích thước lớn.

Ví dụ tránh:

\`\`\`java
@ManagedAttribute
public List<Order> getAllOrders() {
    return repository.findAll();
}
\`\`\`

Thiết kế phù hợp hơn:

\`\`\`java
@ManagedAttribute(description = "Current active order count")
public long getActiveOrderCount() {
    return activeOrderCounter.get();
}
\`\`\`

Nếu cần snapshot chi tiết, hãy giới hạn kích thước, dùng endpoint quản trị có phân trang hoặc cơ chế diagnostics được bảo vệ thay vì nhét cả dữ liệu nghiệp vụ vào một JMX attribute.

Một nguyên tắc tốt là **managed attribute nên mô tả trạng thái nhanh, ổn định, giới hạn kích thước và an toàn khi đọc**.

## 16. Phân biệt JMX attribute với Micrometer metric

Ví dụ:

\`\`\`java
@ManagedAttribute
public int getQueueDepth() {
    return queueDepth.get();
}
\`\`\`

Đây là JMX attribute. Nếu cùng số liệu được đăng ký vào Micrometer \`Gauge\`, đó còn là một metric. Hai cơ chế có thể phản ánh cùng nguồn trạng thái nhưng khác nhau:

| JMX attribute | Metric |
|---|---|
| Đọc theo yêu cầu bằng \`getAttribute\` | Được scrape/ghi nhận theo hệ thống metrics |
| Có thể read-only hoặc writable | Thường mô tả phép đo, không phải API thay đổi cấu hình |
| Có thể trả Java object/OpenType | Có meter type, name, tags và giá trị số |
| Phù hợp chẩn đoán/quản trị JVM | Phù hợp dashboard và cảnh báo theo thời gian |

Một thuộc tính có type \`long\` không tự động là counter metric; ngữ nghĩa đo đạc phải được xác định riêng.

## 17. Các sai lầm thường gặp

**Sai lầm 1: “Có \`@ManagedAttribute\` thì kiểu nào cũng truy cập được từ JConsole.”**  
Không đúng. Exporter/assembler phải đăng ký attribute, và client có thể không hỗ trợ serialized custom object.

**Sai lầm 2: “JMX chỉ hỗ trợ số và chuỗi.”**  
Không đúng. JMX hỗ trợ nhiều Java types ở các loại MBean khác nhau; Open MBean cung cấp hệ kiểu có cấu trúc như CompositeData/TabularData.

**Sai lầm 3: “\`List<CustomObject>\` chắc chắn hoạt động qua remote.”**  
Không thể suy ra. Cần xem loại MBean, mapping/serialization và classpath client.

**Sai lầm 4: “\`Object\` là kiểu linh hoạt nên luôn an toàn.”**  
Ngược lại, nó làm hợp đồng API mơ hồ và có thể khiến remote client gặp lỗi deserialize.

**Sai lầm 5: “JMX metadata tự validate miền giá trị.”**  
Metadata thể hiện kiểu, không tự ràng buộc khoảng số hay quy tắc nghiệp vụ. Cần validate trong setter.

**Sai lầm 6: “MXBean và \`@ManagedResource\` là một.”**  
Không đúng. MXBean tuân thủ mapping chuẩn sang Open Types; \`@ManagedResource\` là metadata cho Spring JMX export.

**Sai lầm 7: “Getter chỉ đọc nên không ảnh hưởng hiệu năng.”**  
Không đúng. Getter có thể query dữ liệu, lock hoặc serialize object lớn. Phải giới hạn chi phí đọc.

**Sai lầm 8: “Kiểu \`Date\` hoặc object Java nào cũng có cùng mapping OpenType.”**  
Không đúng. Cần theo quy tắc JMX type mapping của loại MBean đang dùng, và xem implementation cụ thể.

## 18. Bài tập thực hành

### Bài tập A: Scalar types

Tạo class \`QueueMonitor\` với các managed attributes:
- \`getQueueDepth(): int\`
- \`isPaused(): boolean\`
- \`getStatus(): String\`
- \`getProcessedCount(): long\`

Bật JMX export; kiểm tra \`MBeanInfo.getAttributes()\`, xác nhận tên và type.

### Bài tập B: Read/write type safety

Thêm \`getMaxConcurrentJobs()\` và \`setMaxConcurrentJobs(int)\`, giới hạn miền \`1..128\`. Thử \`setAttribute\` với Integer hợp lệ, giá trị ngoài miền và String không đúng type. Quan sát những exception hoặc lỗi được wrapping ở JMX layer.

### Bài tập C: OpenType

Expose \`CompositeData\` có \`pending\`, \`active\` và \`state\`. Dùng \`getAttribute()\` đọc lại và trích xuất từng field. So sánh với ba scalar getters riêng biệt về sự đơn giản và khả năng mở rộng.

### Bài tập D: Remote compatibility

Tạo một custom DTO và một CompositeData có cùng nội dung. Truy cập chúng từ một remote client không có class DTO. So sánh kết quả và giải thích vì sao OpenType dễ trao đổi giữa ứng dụng độc lập.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** \`@ManagedAttribute\` tự tạo MBean và remote connector chưa?  
**Trả lời:** Không. Annotation cần Spring JMX export; remote connector là cơ chế riêng.

**Câu 2.** \`String\` và \`int\` có phù hợp với đa số JMX management properties không?  
**Trả lời:** Có, vì đơn giản và dễ tiêu thụ, nhưng vẫn phải kiểm tra miền giá trị, chi phí getter và bảo mật.

**Câu 3.** \`CompositeType\` khác \`CompositeData\` ở đâu?  
**Trả lời:** CompositeType là schema, CompositeData là giá trị thỏa schema.

**Câu 4.** Một Spring \`@ManagedResource\` với getter kiểu custom DTO có tự thành MXBean không?  
**Trả lời:** Không. MXBean có hợp đồng chuyển đổi riêng; Spring annotation metadata không tự chuyển loại MBean.

**Câu 5.** Tại sao \`getAttribute()\` trả một custom Java object có thể chạy local nhưng lỗi remote?  
**Trả lời:** Client có thể thiếu class, serialization không hợp lệ hoặc bị security filter từ chối.

**Câu 6.** Metadata \`getType()\` trả \`java.lang.Object\`. Có đủ để client hiểu dữ liệu không?  
**Trả lời:** Không. Cần hợp đồng type cụ thể hoặc OpenType schema.

**Câu 7.** Setter \`setMaxConcurrentJobs(int)\` có cần kiểm tra số âm không?  
**Trả lời:** Có, vì kiểu int cho phép số âm; ràng buộc nghiệp vụ phải được thực thi riêng.

## 20. Ghi nhớ

- \`@ManagedAttribute\` mô tả getter/setter để Spring export thành JMX attribute; nó không định nghĩa lại hệ kiểu Java.
- **Kiểu Java hợp lệ tại server** khác với **kiểu dễ tương tác qua JMX remote**.
- Scalar như \`boolean\`, \`int\`, \`long\`, \`double\`, \`String\` thường là lựa chọn tốt.
- Arrays, enums, collections và custom objects cần xem loại MBean, type mapping và khả năng remote serialization.
- MXBean ánh xạ Java types sang Open Types; Open MBean cung cấp \`SimpleType\`, \`ArrayType\`, \`CompositeType\`, \`TabularType\`.
- \`CompositeData\` và \`TabularData\` là các cấu trúc dữ liệu quản trị có schema, hữu ích khi cần client độc lập với class nội bộ.
- Dùng \`MBeanInfo\` để kiểm tra metadata thực tế; dùng client thực tế để xác nhận interoperability.
- Writable attribute cần validation và authorization; getter cần nhanh, có kích thước dữ liệu hữu hạn và tránh side effects.

### Tài liệu tham khảo

- Spring Framework Reference — JMX Exporting: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Spring Framework Javadoc — \`ManagedAttribute\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedAttribute.html
- Java SE 21 API — \`MBeanAttributeInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanAttributeInfo.html
- Java SE 21 API — Open MBean package: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/openmbean/package-summary.html
- Java SE 21 API — \`CompositeData\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/openmbean/CompositeData.html
- Java SE 21 API — \`MXBean\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MXBean.html
- Oracle JMX Tutorial — MXBeans: https://docs.oracle.com/javase/tutorial/jmx/mbeans/mxbeans.html
