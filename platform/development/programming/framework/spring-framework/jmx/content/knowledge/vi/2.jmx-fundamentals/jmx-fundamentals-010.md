# Phân biệt management interface với lớp cài đặt trong JMX

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của **management interface** và **lớp cài đặt** trong Java Management Extensions (JMX).
- Nhận biết quy ước Standard MBean: interface \`<ClassName>MBean\` và lớp \`ClassName\` triển khai interface đó.
- Xác định phương thức nào trở thành JMX **attribute**, phương thức nào trở thành **operation**, và phương thức nào hoàn toàn không được công khai.
- Hiểu lý do management contract nên giới hạn ở chức năng quan sát và quản trị, thay vì đưa toàn bộ API nghiệp vụ lên JMX.
- Phân biệt Standard MBean, MXBean và trường hợp dùng \`StandardMBean\` để gắn management interface một cách tường minh.
- Liên hệ nguyên lý interface–implementation với cơ chế export MBean trong Spring Framework.

## 2. Bức tranh tổng quan

Trong JMX, một MBean đại diện cho tài nguyên có thể được giám sát hoặc quản trị lúc JVM đang chạy. MBeanServer đăng ký một đối tượng với \`ObjectName\`, rồi công cụ quản lý như JConsole truy cập **các thuộc tính và thao tác quản trị được công bố**.

Tài nguyên thực tế có thể có nhiều hành vi nội bộ. Ví dụ \`OrderQueue\` chịu trách nhiệm thêm đơn hàng, lấy đơn hàng, kiểm tra lỗi, điều phối worker và ghi thống kê. Người vận hành có thể chỉ cần xem số đơn chờ và tạm dừng/tiếp tục xử lý.

Vì vậy cần phân biệt rõ hai khái niệm:

| Thành phần | Trách nhiệm | Đối tượng sử dụng |
|---|---|---|
| **Management interface** | Xác định những thuộc tính và thao tác có thể quan sát/điều khiển qua JMX | MBeanServer và công cụ quản trị |
| **Lớp cài đặt** | Chứa trạng thái và logic thực thi các hành vi quản trị, có thể có thêm API nội bộ | Ứng dụng và MBeanServer |
| **ObjectName** | Định danh MBean khi đăng ký vào một MBeanServer | Bộ đăng ký/tra cứu JMX |

Management interface là **hợp đồng công khai đối với JMX**. Lớp cài đặt là **đối tượng thực hiện hợp đồng đó**. Management interface không phải bản sao của mọi method trên lớp và không đồng nghĩa với Java interface nghiệp vụ.

Ví dụ tổng quát:

\`\`\`text
Ứng dụng nghiệp vụ                       Công cụ JMX
        |                                   |
        v                                   v
   OrderQueue -----------------------> MBeanServer
   (lớp cài đặt)             đăng ký       |
       |                                    |
       +-- OrderQueueMBean <----------------+
           (management contract)
\`\`\`

Sơ đồ thể hiện quan hệ logic: MBeanServer quản lý instance được đăng ký và công bố management metadata dựa trên interface tương ứng. Client JMX không cần thấy API Java nội bộ của instance.

## 3. Quy ước Standard MBean

Với **Standard MBean**, JMX nhận diện interface quản trị theo quy ước:

\`\`\`text
Lớp cài đặt:       CacheMonitor
Management interface: CacheMonitorMBean
\`\`\`

Interface phải được lớp cài đặt triển khai, và tên interface theo quy tắc tên lớp + hậu tố \`MBean\`. Các method của interface quy định bề mặt quản lý; các method public khác trên lớp cài đặt không tự động trở thành JMX operations.

Ví dụ:

**\`CacheMonitorMBean.java\`**

\`\`\`java
public interface CacheMonitorMBean {
    int getEntryCount();
    boolean isEnabled();
    void clear();
    void setEnabled(boolean enabled);
}
\`\`\`

**\`CacheMonitor.java\`**

\`\`\`java
public class CacheMonitor implements CacheMonitorMBean {
    private int entryCount = 42;
    private boolean enabled = true;

    @Override
    public int getEntryCount() {
        return entryCount;
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    @Override
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @Override
    public void clear() {
        entryCount = 0;
    }

    // API Java nội bộ, không nằm trong management interface.
    public void loadEntriesFromDatabase() {
        // Thực thi nghiệp vụ thực tế ở đây.
    }
}
\`\`\`

Ở đây, \`CacheMonitorMBean\` quyết định người quản trị thấy những gì. JMX không công bố \`loadEntriesFromDatabase()\` chỉ vì method này được khai báo public trên \`CacheMonitor\`.

Lưu ý: Interface trong ví dụ là public và các method interface là public theo ngữ nghĩa Java. Nếu interface bị lỗi quy ước tên hoặc lớp không triển khai phù hợp, JMX có thể ném \`NotCompliantMBeanException\` khi đăng ký.

## 4. Mapping method thành attribute và operation

Các method trên **management interface** được JMX diễn giải theo quy ước JavaBeans.

| Khai báo trong interface | Metadata JMX được công bố | Ghi chú |
|---|---|---|
| \`int getEntryCount()\` | Attribute \`EntryCount\`, chỉ đọc | Getter trả về giá trị |
| \`boolean isEnabled()\` | Attribute \`Enabled\` | Dạng \`isXxx\` dành cho boolean |
| \`void setEnabled(boolean value)\` | Attribute \`Enabled\`, có thể ghi nếu kết hợp getter phù hợp | Setter cập nhật trạng thái |
| \`void clear()\` | Operation \`clear\` | Thao tác quản trị |
| \`void resetCounter(int baseline)\` | Operation \`resetCounter\` | Có tham số |

Các method \`getXxx()\`, \`isXxx()\` và \`setXxx(...)\` được diễn giải thành attributes khi tuân thủ chữ ký hợp lệ. Không phải mọi method có chữ \`get\` đều là attribute; ví dụ \`getById(String id)\` không có dạng getter zero-argument và thường là operation.

Khi dùng \`MBeanServer.getAttribute(name, "EntryCount")\`, client yêu cầu attribute \`EntryCount\`. Client không gọi trực tiếp \`getEntryCount\` qua Java reflection. Khi dùng \`MBeanServer.invoke(name, "clear", ...)\`, client yêu cầu operation \`clear\`.

Điểm quan trọng là **khả năng truy cập JMX dựa vào management metadata**, không dựa vào visibility \`public\` của toàn bộ class.

## 5. Ví dụ đầy đủ: đăng ký và gọi qua MBeanServer

Sử dụng hai file \`CacheMonitorMBean.java\` và \`CacheMonitor.java\` ở trên cùng một package, sau đó tạo file sau:

**\`StandardMBeanDemo.java\`**

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class StandardMBeanDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
                "com.example.shop:type=CacheMonitor,name=products");

        CacheMonitor monitor = new CacheMonitor();
        server.registerMBean(monitor, name);

        try {
            // JMX attribute được khai báo bằng getEntryCount().
            System.out.println(server.getAttribute(name, "EntryCount"));
            // 42

            // JMX attribute ghi được vì có setEnabled(boolean).
            server.setAttribute(name,
                    new javax.management.Attribute("Enabled", false));
            System.out.println(server.getAttribute(name, "Enabled"));
            // false

            // Operation thuộc management interface.
            server.invoke(name, "clear",
                    new Object[0], new String[0]);
            System.out.println(server.getAttribute(name, "EntryCount"));
            // 0

            // Liệt kê operations thực tế được công bố.
            MBeanInfo info = server.getMBeanInfo(name);
            for (MBeanOperationInfo operation : info.getOperations()) {
                System.out.println(operation.getName());
            }
        } finally {
            server.unregisterMBean(name);
        }
    }
}
\`\`\`

Với ví dụ này, metadata quản trị sẽ gồm thuộc tính \`EntryCount\`, \`Enabled\` và operation \`clear\`. \`loadEntriesFromDatabase\` không thuộc management metadata. Việc gọi tên đó bằng \`server.invoke\` không được cung cấp như một operation trên Standard MBean.

### Các bước chạy

1. Lưu ba file cùng package/thư mục; bảo đảm tên interface chính xác là \`CacheMonitorMBean\`.
2. Biên dịch bằng JDK: \`javac CacheMonitorMBean.java CacheMonitor.java StandardMBeanDemo.java\`.
3. Chạy: \`java StandardMBeanDemo\`.
4. Quan sát attribute được đọc/ghi qua MBeanServer và operation \`clear\` được gọi.
5. Kiểm tra \`getMBeanInfo()\` để xác nhận bề mặt quản trị thực tế thay vì suy đoán từ tất cả public methods.

Đoạn demo hủy đăng ký ngay khi xong. Nếu muốn dùng JConsole quan sát thủ công, cần giữ JVM chạy trong lúc MBean vẫn được đăng ký, ví dụ thêm đoạn chờ nhập bàn phím trước \`unregisterMBean\`.

**Lưu ý về quản lý vòng đời:** Trong ví dụ, mã dùng \`finally\` để hủy đăng ký khi chương trình hoàn thành. Trong ứng dụng server dài hạn, registration/unregistration nên đi cùng vòng đời component và xử lý xung đột tên \`InstanceAlreadyExistsException\`.

## 6. Vì sao không đưa toàn bộ implementation lên JMX?

Một lớp nghiệp vụ có thể chứa các API nhạy cảm, thay đổi thường xuyên hoặc đòi hỏi transaction và input validation. Công bố tất cả method sẽ khiến việc giám sát trở thành một đường thao tác ngoài ý muốn.

Ví dụ, một dịch vụ thanh toán có thể có:

\`\`\`java
public class PaymentProcessor {
    public void charge(String cardToken, long amount) { /* ... */ }
    public void retryFailedPayments() { /* ... */ }
    public int pendingCount() { return 0; }
}
\`\`\`

Thông thường, management interface chỉ nên công bố điều thực sự hữu ích và an toàn để vận hành, chẳng hạn:

\`\`\`java
public interface PaymentMonitorMBean {
    int getPendingCount();
}
\`\`\`

Ví dụ trên chỉ minh họa phạm vi management contract; để là Standard MBean đúng quy ước, một lớp cài đặt tên \`PaymentMonitor\` cần triển khai \`PaymentMonitorMBean\`, hoặc dùng \`StandardMBean\` để chỉ định interface rõ ràng.

Thiết kế contract tách biệt đem lại các lợi ích:

- **Kiểm soát bề mặt quản trị:** chỉ công bố thông tin và thao tác cần thiết.
- **Giữ API nghiệp vụ độc lập:** thay đổi method nội bộ không bắt dashboard JMX thay đổi.
- **Dễ kiểm thử:** có thể so sánh metadata JMX với interface quản trị dự kiến.
- **Dễ phân quyền:** số lượng thao tác cần bảo vệ được giới hạn và mô tả rõ ràng.

Tuy nhiên, management interface không tự cung cấp authentication/authorization. Nếu có kết nối JMX từ xa, cấu hình transport, xác thực, TLS và quyền quản trị phải được kiểm soát riêng. Một operation dù được định nghĩa trong interface vẫn phải được xem xét kỹ trước khi công bố.

## 7. Management interface khác Java interface nghiệp vụ

Java interface nói chung mô tả một hợp đồng cho các đối tượng Java, ví dụ \`OrderRepository\`, \`PaymentGateway\` hay \`CacheService\`. Một **management interface** trong Standard MBean là Java interface tuân theo quy ước JMX và được dùng để tạo JMX management metadata.

So sánh:

| Tiêu chí | Interface nghiệp vụ | Standard MBean management interface |
|---|---|---|
| Mục tiêu | Dùng trong gọi hàm ứng dụng | Quan sát và quản lý qua JMX |
| Ví dụ | \`CacheService\` | \`CacheMonitorMBean\` |
| Quy ước tên JMX | Không cần | Thường là \`ClassNameMBean\` |
| Cách gọi | Java method call, DI | \`MBeanServer\`, JMX client |
| Bề mặt công khai | API cho code ứng dụng | Attribute/operation cho công cụ quản trị |
| Vòng đời | Theo object/component | Cần đăng ký/hủy đăng ký vào MBeanServer |

Có thể dùng cùng một class để thực thi logic nghiệp vụ và contract quản trị, nhưng với component phức tạp nên cân nhắc một **monitor adapter** riêng, chỉ gọi các API đọc trạng thái hoặc operation đã phê duyệt.

\`\`\`text
CacheService  <-- dùng bởi -->  CacheMonitor implements CacheMonitorMBean
                                |
                                +-- expose EntryCount, Enabled, clear
\`\`\`

Adapter tạo ranh giới rõ giữa interface phục vụ ứng dụng và interface dành cho người vận hành.

## 8. Khi quy ước tên không phù hợp: StandardMBean

Đôi khi interface quản trị có tên khác quy ước, ví dụ \`HealthView\`, hoặc một lớp cần công bố interface JMX tách biệt khỏi tên class thực tế. \`javax.management.StandardMBean\` cho phép khai báo tường minh management interface.

**\`HealthView.java\`**

\`\`\`java
public interface HealthView {
    boolean isHealthy();
}
\`\`\`

**\`HealthComponent.java\`**

\`\`\`java
public class HealthComponent implements HealthView {
    @Override
    public boolean isHealthy() {
        return true;
    }

    public void performInternalRecovery() {
        // Không công bố qua HealthView.
    }
}
\`\`\`

**Đăng ký bằng StandardMBean:**

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.StandardMBean;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
HealthComponent component = new HealthComponent();

StandardMBean wrapper =
        new StandardMBean(component, HealthView.class);

ObjectName name = new ObjectName(
        "com.example.shop:type=HealthComponent,name=primary");

server.registerMBean(wrapper, name);
try {
    System.out.println(server.getAttribute(name, "Healthy"));
} finally {
    server.unregisterMBean(name);
}
\`\`\`

\`StandardMBean\` là wrapper JMX công bố management interface được chỉ định. \`HealthView\` không cần mang hậu tố \`MBean\` trong trường hợp này. Phần business implementation vẫn ở \`HealthComponent\`.

Không dùng \`StandardMBean\` chỉ để che giấu lỗi thiết kế; nếu quy ước Standard MBean đáp ứng yêu cầu, cách khai báo \`CacheMonitorMBean\` đơn giản và rõ ràng hơn.

## 9. MXBean: management interface có quy ước và kiểu dữ liệu riêng

Một **MXBean** cũng phân tách management interface với lớp cài đặt, nhưng tập trung vào khả năng ánh xạ kiểu dữ liệu sang các kiểu phù hợp cho công cụ JMX, đặc biệt khi quản lý JVM từ xa.

Một interface thường được nhận diện là MXBean khi tên kết thúc bằng \`MXBean\` hoặc có \`@MXBean\` thích hợp. Ví dụ:

\`\`\`java
public interface QueueMetricsMXBean {
    int getPendingCount();
    String getQueueName();
}

public class QueueMetrics implements QueueMetricsMXBean {
    @Override
    public int getPendingCount() {
        return 7;
    }

    @Override
    public String getQueueName() {
        return "orders";
    }
}
\`\`\`

So sánh trọng tâm:

- **Standard MBean:** interface theo quy ước \`SomethingMBean\`; mô hình management attribute/operation trực tiếp.
- **MXBean:** interface \`SomethingMXBean\` hoặc annotation tương ứng; bổ sung quy tắc ánh xạ từ kiểu Java sang **open types** trong JMX, giúp client ở process khác không nhất thiết phải chia sẻ toàn bộ kiểu class nghiệp vụ.
- **Dynamic MBean:** không cần một management interface Java theo quy ước; class tự cung cấp metadata và hành vi qua \`DynamicMBean\`.

Với ví dụ đơn giản dùng \`int\` và \`String\`, Standard MBean và MXBean có thể trông rất giống nhau trong client. Khác biệt trở nên quan trọng khi quản lý kiểu dữ liệu phức tạp và truy cập từ xa.

## 10. Spring Framework: annotation là cách khai báo contract quản trị

Spring Framework cung cấp annotation JMX để mô tả các attribute/operation của bean mà không cần bắt buộc tạo interface \`SomethingMBean\` thủ công. Khi cấu hình exporter và annotation assembler phù hợp, Spring dùng annotation để tạo management metadata.

Ví dụ:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.shop:type=Cache,name=products",
    description = "Product cache monitor")
public class ProductCacheManagement {

    private volatile int entryCount = 3;

    @ManagedAttribute(description = "Entries in cache")
    public int getEntryCount() {
        return entryCount;
    }

    @ManagedOperation(description = "Clear the cache")
    public void clear() {
        entryCount = 0;
    }

    public void refreshFromStorage() {
        // Method không được đánh dấu là management operation.
    }
}
\`\`\`

Ở mô hình annotation, nhóm \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\` đóng vai trò mô tả bề mặt quản trị. Đối với \`@ManagedAttribute\` ở getter, tên attribute thường được suy ra từ tên property JavaBeans; với \`@ManagedOperation\`, method được mô tả như operation.

Điều kiện quan trọng: class phải nằm trong phạm vi Spring quản lý/export và exporter phải dùng assembler có hỗ trợ annotation; chỉ đặt annotation lên một class bất kỳ không tự bảo đảm xuất hiện MBean. Cách cấu hình có thể khác giữa Spring Framework thuần và Spring Boot.

**Khác với Standard MBean interface truyền thống:** Spring annotation có thể mô tả contract ngay trên class, vì vậy không nhất thiết có một file interface riêng. Dù vậy, nguyên tắc thiết kế không đổi: công bố một bộ chức năng quản trị nhỏ và có chủ đích.

### Spring MBeanExporter và interface

Spring cũng có thể export bean triển khai Standard MBean interface theo quy ước, sử dụng \`MBeanExporter\`. Khi dựa vào interface/assembler, hãy xác định rõ exporter nào tạo metadata để tránh giả định rằng tất cả public methods đều tự trở thành operations.

Trong một hệ thống, có thể gặp ba tên khác nhau:

\`\`\`text
Spring bean name:          productCacheManagement
Java implementation type:  ProductCacheManagement
JMX ObjectName:            com.example.shop:type=Cache,name=products
\`\`\`

Chúng phục vụ ba chức năng khác nhau. Tên bean Spring dùng cho dependency injection; tên class dùng cho kiểu triển khai; \`ObjectName\` dùng đăng ký và tra cứu trong MBeanServer.

## 11. Kiểm tra metadata thay vì nhìn vào class

Cách đáng tin để xác định một MBean thật sự công bố gì là đọc \`MBeanInfo\`:

\`\`\`java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf("ATTRIBUTE %s read=%s write=%s%n",
            attribute.getName(),
            attribute.isReadable(),
            attribute.isWritable());
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println("OPERATION " + operation.getName());
}
\`\`\`

Thực hành này hữu ích khi:

- Một class có nhiều public methods nhưng client JMX chỉ thấy một phần.
- Bạn dùng Spring annotation assembler hoặc MXBean.
- Client báo \`AttributeNotFoundException\` hoặc \`ReflectionException\`.
- Bạn cần xác nhận bộ management operations trước khi cho phép truy cập từ xa.

Khi kiểm tra, đừng chỉ nhìn vào \`ObjectName\`: tên đúng cho biết đã tìm đúng MBean, nhưng metadata mới cho biết attribute/operation nào đang khả dụng.

## 12. Những lỗi dễ gặp

| Tình huống | Điều cần kiểm tra |
|---|---|
| \`NotCompliantMBeanException\` khi đăng ký | Interface tên \`ClassNameMBean\` có tồn tại, public và được implementation thực thi không? Có cần wrapper \`StandardMBean\`? |
| Public method không xuất hiện trong JConsole | Method đó có nằm trong management interface hoặc có annotation/export phù hợp không? |
| Attribute hiển thị chỉ đọc | Có setter hợp lệ trong management interface hoặc metadata tương ứng không? |
| Gọi \`invoke("getEntryCount")\` không được | \`getEntryCount()\` được công bố thành attribute \`EntryCount\`; hãy dùng \`getAttribute\`. |
| Thay tên Java class rồi export lỗi | Interface Standard MBean có còn tuân thủ tên class + \`MBean\` không? |
| MXBean không xử lý được kiểu trả về | Kiểu Java có thể ánh xạ sang open types theo quy tắc MXBean không? |
| Spring annotation không có hiệu lực | Bean có được export và assembler có nhận diện annotation không? |
| Nhầm JMX với Java visibility | \`public\` trong Java chưa đồng nghĩa với operation JMX. |

Không phải mọi lỗi khi gọi một method qua JMX đều là lỗi interface. Có thể còn vấn đề kết nối, quyền truy cập, chữ ký tham số, instance chưa đăng ký hoặc exception trong logic implementation.

## 13. Bài tập thực hành

### Bài tập 1 — Chọn management contract

Giả sử lớp sau có các method:

\`\`\`java
public class InvoiceService {
    public int pendingInvoices() { return 5; }
    public void issueInvoice(String customerId) { /* ... */ }
    public void retryDispatch() { /* ... */ }
    public void resetMetrics() { /* ... */ }
}
\`\`\`

Yêu cầu người vận hành chỉ xem được số invoice đang chờ và reset thống kê. Hãy thiết kế một \`InvoiceMonitorMBean\` chỉ gồm \`getPendingCount()\` và \`resetMetrics()\`, cùng một lớp \`InvoiceMonitor\` cài đặt contract và ủy quyền an toàn sang service cần thiết.

**Gợi ý:** Không đưa \`issueInvoice\` vào management interface; một lời gọi quản trị không nên vô tình thực thi nghiệp vụ phát hành invoice.

### Bài tập 2 — Dự đoán metadata

Cho:

\`\`\`java
public interface WorkerMonitorMBean {
    int getActiveThreads();
    boolean isPaused();
    void setPaused(boolean paused);
    void restart();
}
\`\`\`

Hãy xác định:

- Attribute \`ActiveThreads\`: chỉ đọc.
- Attribute \`Paused\`: có thể đọc và ghi.
- Operation \`restart\`: có thể gọi qua JMX.

Sau đó tự tạo class \`WorkerMonitor\`, đăng ký và so sánh kết quả dự đoán với \`getMBeanInfo()\`.

### Bài tập 3 — Tìm API vô tình bị công bố

Tạo một Standard MBean có implementation gồm thêm public method \`deleteAllData()\`, nhưng không đặt method này trong interface \`SomethingMBean\`. Quan sát metadata để xác nhận method đó không nằm trong JMX operations.

Đây chỉ là bài tập về **phạm vi công bố API**; không cần tạo logic xóa dữ liệu thật.

### Bài tập 4 — So sánh hai phương thức export

Thử một mô hình Standard MBean interface và một mô hình Spring \`@ManagedResource\` + \`@ManagedAttribute\`. So sánh file/interface Java cần khai báo, metadata công bố, cách đặt ObjectName và cách cấu hình exporter.

## 14. Câu hỏi tự kiểm tra

**1. Nếu \`CacheMonitor\` có một public method không nằm trong \`CacheMonitorMBean\`, method đó có tự thành JMX operation không?**

Không, trong mô hình Standard MBean thông thường, bề mặt quản trị dựa vào management interface.

**2. Vì sao \`getEntryCount()\` không nhất thiết xuất hiện dưới danh sách Operations?**

Vì phương thức getter hợp lệ được ánh xạ thành JMX attribute \`EntryCount\`.

**3. Đổi tên implementation từ \`CacheMonitor\` sang \`CacheAgent\` nhưng vẫn giữ \`CacheMonitorMBean\` có vấn đề gì?**

Standard MBean convention có thể không còn khớp tên. Có thể đổi contract cho phù hợp hoặc dùng \`StandardMBean\` để cung cấp interface tường minh.

**4. Có management interface rồi thì JMX từ xa tự an toàn không?**

Không. Interface giới hạn các hành vi có thể công bố nhưng không tự cung cấp xác thực, mã hóa hay phân quyền kết nối.

**5. Trong Spring, management contract có nhất thiết phải ở interface \`*MBean\` không?**

Không. Spring hỗ trợ mô tả management metadata qua annotation/assembler hoặc cơ chế export khác, nhưng phải có cấu hình exporter thích hợp.

## 15. Tổng kết

- **Management interface** trả lời câu hỏi: *JMX client được phép nhìn thấy và gọi những gì trên MBean?*
- **Lớp cài đặt** trả lời câu hỏi: *Hành vi và trạng thái ấy được thực thi bằng logic Java nào?*
- Với **Standard MBean**, interface \`ClassNameMBean\` là management contract theo quy ước; chỉ bề mặt này trở thành management metadata.
- Getter/setter hợp lệ biến thành attributes, các method khác trong contract có thể trở thành operations.
- \`StandardMBean\` cho phép chỉ định interface tường minh khi muốn tách tên contract khỏi tên implementation.
- MXBean cũng có management interface, đồng thời có quy tắc ánh xạ kiểu dữ liệu phục vụ JMX interoperability.
- Spring hỗ trợ export qua annotation hoặc interface, nhưng nguyên tắc công bố có chọn lọc vẫn cần được giữ.
- Khi cần xác nhận hành vi thật, tra cứu \`MBeanInfo\` từ MBeanServer.

## 16. Tài liệu tham khảo

- Oracle Java SE 21 — \`javax.management.StandardMBean\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/StandardMBean.html
- Oracle Java SE 21 — \`javax.management.MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Oracle JMX Tutorial — Standard MBeans: https://docs.oracle.com/javase/tutorial/jmx/mbeans/standard.html
- Oracle JMX Tutorial — MXBeans: https://docs.oracle.com/javase/tutorial/jmx/mbeans/mxbeans.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
