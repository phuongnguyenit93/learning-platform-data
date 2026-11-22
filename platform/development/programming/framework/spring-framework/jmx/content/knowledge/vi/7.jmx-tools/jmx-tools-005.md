# Gọi operation có tác dụng phụ từ công cụ quản trị

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao thao tác **invoke operation** qua JMX có thể làm thay đổi trạng thái của ứng dụng, thay vì chỉ quan sát thông tin.
- Phân biệt thao tác đọc attribute, ghi attribute và gọi operation qua JConsole hoặc một JMX client khác.
- Thiết kế operation quản trị rõ hợp đồng, có giới hạn tác động và trạng thái lỗi minh bạch.
- Gọi operation từ JConsole và từ Java JMX API với tên, tham số và chữ ký chính xác.
- Nhận diện các vấn đề như gọi lặp, đồng thời, timeout, thiếu quyền truy cập, khởi động lại hệ thống và tác động trên môi trường production.
- Áp dụng kiến thức trong ứng dụng Spring Framework có MBean được đăng ký bằng \`MBeanExporter\` hoặc cơ chế JMX tương đương.

## 1. Vì sao operation JMX có thể có tác dụng phụ?

JMX (Java Management Extensions) cung cấp một giao diện quản lý cho tiến trình Java đang chạy. Bên trong \`MBeanServer\`, một MBean có thể công bố:

- **Attribute đọc**: cho phép client xem số kết nối, số tác vụ, trạng thái hoặc cấu hình hiện tại.
- **Attribute ghi**: cho phép client chỉnh một giá trị cấu hình quản trị, chẳng hạn \`Enabled=true/false\`.
- **Operation**: cho phép client gọi một phương thức quản lý như \`resetStatistics()\`, \`clearCache()\`, \`pauseScheduler()\`, \`reloadRules()\` hoặc \`triggerMaintenance()\`.

Operation có thể chỉ đọc dữ liệu, nhưng nhiều operation gây **side effect**: thay đổi trạng thái bộ nhớ, xóa dữ liệu cache, dừng công việc, tải lại cấu hình hoặc kích hoạt xử lý bổ sung. Vì thế, việc một công cụ JMX hiển thị nút để gọi operation không có nghĩa rằng thao tác đó vô hại.

Ví dụ, \`getQueueDepth()\` chỉ trả về số lượng phần tử đang chờ. Trong khi đó, \`clearQueue()\` có thể loại bỏ các phần tử chưa được xử lý. Cả hai đều có thể xuất hiện qua JMX tùy hợp đồng MBean, nhưng rủi ro vận hành hoàn toàn khác nhau.

### Minh họa chuỗi tác động

\`\`\`text
JConsole / JMX client
       |
       | invoke("clearCache", ...)
       v
MBeanServer
       |
       | resolve ObjectName + operation + signature
       v
MBean đã đăng ký
       |
       | gọi phương thức quản lý
       v
Trạng thái ứng dụng thay đổi
       |
       +--> dữ liệu cache bị xóa
       +--> request tiếp theo phải nạp lại dữ liệu
       +--> metrics/log có thể phản ánh thay đổi
\`\`\`

JMX là **đường điều khiển runtime**, không chỉ là công cụ vẽ biểu đồ. Thiết kế và sử dụng nó cần xem xét quyền truy cập và hệ quả của các thay đổi.

## 2. Phân biệt read, write và invoke

| Thao tác của client | API JMX tương ứng | Ví dụ | Tác động điển hình |
| --- | --- | --- | --- |
| Đọc attribute | \`getAttribute\` | Đọc \`CacheSize\` | Thường dùng để quan sát; getter vẫn có thể có logic riêng |
| Ghi attribute | \`setAttribute\` | Đặt \`RefreshEnabled=false\` | Thay đổi cấu hình hoặc trạng thái |
| Gọi operation | \`invoke\` | \`resetStatistics()\` | Thực hiện logic quản trị; có thể thay đổi dữ liệu |
| Xem metadata | \`getMBeanInfo\` | Kiểm tra tên, tham số, kiểu kết quả | Giúp xác định hợp đồng được công bố |

Cần phân biệt **mục đích của API** với **mức độ an toàn**. Một getter được viết kém có thể gây side effect; một operation như \`getDetailedStatus()\` có thể chỉ đọc. Không thể xác định tính an toàn chỉ từ việc phần tử đó xuất hiện trong tab \`Attributes\` hay \`Operations\`.

## 3. Xây dựng Standard MBean có operation quản trị

Giả sử hệ thống có bộ nhớ cache đơn giản. Ta muốn JMX cho phép quan sát kích thước cache và gọi \`clearCache()\` để loại bỏ tất cả entry.

**CacheControlMBean.java**

\`\`\`java
package com.example.jmx;

public interface CacheControlMBean {
    int getCacheSize();
    boolean isMaintenanceEnabled();
    void setMaintenanceEnabled(boolean enabled);
    int clearCache();
}
\`\`\`

Tên interface \`CacheControlMBean\` tuân thủ quy ước Standard MBean đối với lớp triển khai \`CacheControl\`. Method \`clearCache()\` được khai báo trong interface quản lý, vì vậy được công bố là operation.

**CacheControl.java**

\`\`\`java
package com.example.jmx;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

public class CacheControl implements CacheControlMBean {
    private final ConcurrentMap<String, String> entries =
            new ConcurrentHashMap<>();

    private volatile boolean maintenanceEnabled;

    public void put(String key, String value) {
        entries.put(key, value);
    }

    @Override
    public int getCacheSize() {
        return entries.size();
    }

    @Override
    public boolean isMaintenanceEnabled() {
        return maintenanceEnabled;
    }

    @Override
    public void setMaintenanceEnabled(boolean enabled) {
        this.maintenanceEnabled = enabled;
    }

    @Override
    public int clearCache() {
        if (!maintenanceEnabled) {
            throw new IllegalStateException(
                    "Enable maintenance mode before clearing cache");
        }

        int approximateRemovedCount = entries.size();
        entries.clear();
        return approximateRemovedCount;
    }
}
\`\`\`

Ở đây, \`clearCache()\` có **side effect** rõ ràng: xóa các entry đang tồn tại. Operation chỉ cho chạy khi \`maintenanceEnabled\` là \`true\`; đây là chốt logic minh họa, không phải cơ chế xác thực hoặc phân quyền. Nếu các thread khác vẫn ghi vào cache, số phần tử trả về chỉ mang tính xấp xỉ, vì \`size()\` và \`clear()\` không phải một transaction nguyên tử với những hoạt động đồng thời.

Các method thông thường \`put()\` không nằm trong interface MBean nên không được Standard MBean mặc định xuất thành operation JMX.

### Hợp đồng vận hành cần được mô tả rõ

Một operation quản trị nên cho biết:

1. **Điều kiện trước khi gọi**: chẳng hạn cần bật maintenance mode hoặc bảo đảm không còn tác vụ đang xử lý.
2. **Tác động**: trạng thái nào bị thay đổi, có ảnh hưởng request đang chạy hay không.
3. **Kết quả**: giá trị trả về biểu thị điều gì, có chính xác khi concurrent hay không.
4. **Lỗi có thể xảy ra**: operation bị từ chối, timeout, lỗi hạ tầng hoặc runtime exception.
5. **Khả năng gọi lặp**: gọi lần hai có gây thêm tác động không.
6. **Khả năng phục hồi**: có thể nạp lại cache, bật lại scheduler hoặc khôi phục cấu hình không.

Với thao tác xóa cache, lần gọi đầu có thể xóa nhiều entry, lần tiếp theo có thể không xóa gì nếu cache chưa được nạp lại. Đó là hành vi gần với idempotent ở mức trạng thái cache, nhưng không được tự suy diễn rằng mọi operation gọi lặp đều an toàn.

## 4. Đăng ký MBean để công cụ quản trị nhìn thấy

Để JConsole hoặc client JMX khác tìm thấy operation, đối tượng phải được đăng ký trong \`MBeanServer\` dưới một \`ObjectName\`.

\`\`\`java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class JmxOperationDemo {
    public static void main(String[] args) throws Exception {
        CacheControl cache = new CacheControl();
        cache.put("product:1", "Book");
        cache.put("product:2", "Keyboard");

        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName objectName = new ObjectName(
                "com.example.jmx:type=CacheControl,name=primary");

        server.registerMBean(cache, objectName);

        System.out.println("PID: " + ProcessHandle.current().pid());
        System.out.println("Registered: " + objectName);

        // Giữ JVM chạy để JConsole có thể kết nối và thử operation.
        Thread.currentThread().join();
    }
}
\`\`\`

Ví dụ đăng ký MBean vào **platform MBeanServer** của JVM hiện tại. \`ObjectName\` dùng domain \`com.example.jmx\`, \`type=CacheControl\` và \`name=primary\`.

Câu lệnh \`Thread.currentThread().join()\` làm luồng chính chờ chính nó để giữ JVM tồn tại, chỉ phù hợp với demo; ứng dụng Spring thật có vòng đời runtime riêng. Bạn có thể dừng tiến trình demo sau khi hoàn thành thao tác thử nghiệm.

Nếu đăng ký trùng \`ObjectName\`, JMX ném \`InstanceAlreadyExistsException\`; nếu class/interface không hợp lệ theo MBean convention, có thể gặp \`NotCompliantMBeanException\`.

## 5. Gọi operation bằng JConsole

Khi chương trình demo đang chạy:

1. Mở \`jconsole\` bằng JDK phù hợp.
2. Chọn đúng JVM theo tên hoặc PID vừa in ra.
3. Vào tab **MBeans**.
4. Mở domain \`com.example.jmx\`, tìm \`type=CacheControl,name=primary\`.
5. Trong mục **Attributes**, đọc \`CacheSize\` (ban đầu dự kiến là 2) và \`MaintenanceEnabled\` (ban đầu \`false\`).
6. Chuyển sang mục **Operations**, tìm \`clearCache\`.
7. Nếu gọi ngay khi maintenance mode đang tắt, operation ném \`IllegalStateException\`; JMX client có thể hiển thị exception đã được wrapper bởi tầng quản lý.
8. Trở lại **Attributes**, đặt \`MaintenanceEnabled=true\`.
9. Gọi \`clearCache\`, kiểm tra kết quả và đọc lại \`CacheSize\`, lúc này dự kiến bằng 0 nếu không có thread khác thêm entry.
10. Đặt \`MaintenanceEnabled=false\` sau bài thử.

Nhãn nút, hình thức nhập tham số và cách hiển thị lỗi có thể khác theo phiên bản JConsole. Có công cụ cần refresh hoặc chọn lại node trước khi hiển thị giá trị mới.

**Không sử dụng bài thử xóa cache này trên production** nếu chưa xác định tác động nghiệp vụ. Thao tác quản trị tương tự có thể làm mất dữ liệu tạm thời hoặc tạo lưu lượng tải lại đột biến.

## 6. Gọi operation bằng Java MBeanServer.invoke

Nếu ứng dụng hoặc một diagnostic tool đang chạy trong **cùng JVM** với MBean đã đăng ký, có thể gọi trực tiếp qua \`MBeanServer\`:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.Attribute;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
        "com.example.jmx:type=CacheControl,name=primary");

server.setAttribute(name, new Attribute("MaintenanceEnabled", true));

Object result = server.invoke(
        name,
        "clearCache",
        new Object[0],
        new String[0]
);

System.out.println("Removed (approximate): " + result);
System.out.println("Current cache size: "
        + server.getAttribute(name, "CacheSize"));
\`\`\`

Các tham số của \`invoke\` gồm:

\`\`\`java
Object invoke(
        ObjectName name,
        String operationName,
        Object[] params,
        String[] signature
)
\`\`\`

- \`name\`: định danh MBean đã được đăng ký.
- \`operationName\`: đúng tên operation được công bố.
- \`params\`: danh sách tham số thực tế.
- \`signature\`: danh sách tên kiểu Java tương ứng từng tham số, cùng thứ tự.
- Kết quả trả về: giá trị mà operation trả về thông qua JMX (hoặc \`null\` với thao tác \`void\`).

Với \`clearCache()\`, không có tham số nên cả \`params\` và \`signature\` đều là mảng rỗng. Không truyền chuỗi rỗng \`""\` thay cho một kiểu tham số; chữ ký không đúng có thể khiến operation không tìm được.

### Operation có tham số

Giả sử \`CacheControlMBean\` bổ sung:

\`\`\`java
boolean evictEntry(String key);
\`\`\`

Khi implementation hỗ trợ method đó, cách gọi bằng JMX API là:

\`\`\`java
Object removed = server.invoke(
        name,
        "evictEntry",
        new Object[]{"product:1"},
        new String[]{"java.lang.String"}
);
\`\`\`

Chữ ký dùng tên Java type, chẳng hạn \`java.lang.String\` hoặc \`int\` đối với primitive \`int\`, và phải khớp với signature của operation thực sự được công bố. Đặc biệt khi overload nhiều method cùng tên, client cần chọn đúng danh sách kiểu tham số.

### Kết nối từ tiến trình khác

\`ManagementFactory.getPlatformMBeanServer()\` trả về server của **JVM đang chạy mã**. Một chương trình JMX client riêng không thể dùng lời gọi đó để truy cập registry trong JVM ứng dụng. Client ở tiến trình khác cần kết nối thông qua một \`JMXConnector\` đã được cấu hình, nhận \`MBeanServerConnection\`, rồi gọi \`invoke\` trên connection đó. Truy cập remote phụ thuộc quyền xác thực, cấu hình mạng và transport JMX.

## 7. Metadata và ảnh hưởng của MBeanOperationInfo

Trước khi gọi, JMX client có thể đọc metadata từ \`MBeanInfo\`:

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println("Operation: " + operation.getName());
    System.out.println("Return type: " + operation.getReturnType());
    System.out.println("Impact hint: " + operation.getImpact());

    for (var param : operation.getSignature()) {
        System.out.println(
                "Parameter: " + param.getName() + " / " + param.getType());
    }
}
\`\`\`

JMX cung cấp các mức độ mô tả tác động của operation:

| Hằng số JMX | Ý nghĩa theo metadata |
| --- | --- |
| \`MBeanOperationInfo.INFO\` | Operation được mô tả là cung cấp thông tin |
| \`MBeanOperationInfo.ACTION\` | Operation được mô tả là thực hiện hành động |
| \`MBeanOperationInfo.ACTION_INFO\` | Vừa thực hiện hành động vừa trả thông tin |
| \`MBeanOperationInfo.UNKNOWN\` | Chưa xác định hoặc không biết loại tác động |

**Đây là metadata/hint, không phải cơ chế bảo vệ.** Không nên dựa hoàn toàn vào \`INFO\` để quyết định có được phép gọi hay không. Mức impact có thể do cơ chế introspection hoặc tác giả MBean cung cấp, không tự chứng minh operation không gây tác dụng phụ.

Ở Standard MBean dùng convention, tên operation và signature được lấy từ interface quản lý; metadata impact không phải lúc nào cũng diễn đạt đầy đủ rủi ro kinh doanh. Đối với thao tác quan trọng, cần tài liệu vận hành cụ thể hơn tên phương thức và return type.

## 8. Tích hợp operation quản trị với Spring Framework

Trong Spring, bạn có thể giữ class và interface quản lý thuần Java, sau đó đăng ký bean với \`MBeanExporter\`:

\`\`\`java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxConfiguration {

    @Bean
    public CacheControl cacheControl() {
        return new CacheControl();
    }

    @Bean
    public MBeanServer mBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter mBeanExporter(
            CacheControl cacheControl, MBeanServer mBeanServer) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mBeanServer);
        exporter.setBeans(Map.of(
                "com.example.jmx:type=CacheControl,name=primary",
                cacheControl));
        return exporter;
    }
}
\`\`\`

Khi Spring context khởi tạo exporter, nó đưa \`cacheControl\` vào JMX registry. JConsole kết nối đúng JVM sẽ tìm thấy các attribute và operation do \`CacheControlMBean\` công bố.

Trong Spring Boot, JMX auto-configuration có thể đã quản lý server hoặc exporter; hãy kiểm tra cấu hình thực tế để tránh tạo MBean trùng tên. Đừng đăng ký cùng một \`ObjectName\` bằng cả \`MBeanServer.registerMBean\` thủ công lẫn Spring exporter.

### Spring annotation-based JMX

Spring còn hỗ trợ khai báo operation với \`@ManagedOperation\`:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(objectName =
        "com.example.jmx:type=CacheControl,name=annotated")
public class AnnotatedCacheControl {
    @ManagedOperation(description =
            "Clear cached entries; changes application state")
    public void clearCache() {
        // Đưa logic quản trị có kiểm soát vào đây.
    }
}
\`\`\`

Annotation cần được exporter hỗ trợ annotation xử lý, chẳng hạn \`AnnotationMBeanExporter\`; chỉ đặt \`@ManagedResource\` trên class không bảo đảm ứng dụng tự xuất MBean khi chưa cấu hình cơ chế thích hợp.

Vì annotation dễ khiến operation được xuất qua JMX mà không cần interface \`*MBean\`, cần đặc biệt cân nhắc phạm vi method được đánh dấu. Operation có thể gọi từ JConsole cũng như bất kỳ client JMX nào có kết nối và quyền phù hợp.

## 9. Rủi ro thực tế khi gọi operation có side effect

### 9.1. Tác động lâu dài và tính không thể hoàn tác

Một lệnh \`clearCache()\` có thể khiến hệ thống phải nạp lại dữ liệu, nhưng vẫn có khả năng phục hồi từ nguồn. Ngược lại, \`deletePendingJobs()\` có thể xóa thông tin chưa được lưu ở nơi khác. Khả năng hoàn tác không được JMX tự cung cấp; tùy logic thực thi của từng operation.

Với hành động quan trọng, giao diện quản lý nên mô tả rõ phạm vi và điều kiện, và chỉ công bố những thao tác thực sự cần thiết cho người vận hành.

### 9.2. Gọi lặp, retry và kết quả mơ hồ

Giả sử client gửi lệnh \`triggerBatch()\` rồi mất kết nối trước khi nhận phản hồi. Bạn không thể kết luận chắc rằng batch chưa chạy: operation có thể đã hoàn thành, đang chạy hoặc chưa được thực hiện. Retry mù có thể khiến batch chạy hai lần.

Đối với tác vụ không idempotent, có thể thiết kế operation sử dụng request ID, cơ chế từ chối trùng, hay API tra cứu trạng thái. Đối với tác vụ dài, mô hình \`startJob()\` trả mã công việc và \`getJobStatus(id)\` thường dễ vận hành hơn việc giữ một lời gọi invoke chờ vô hạn.

### 9.3. Thread safety và cạnh tranh với luồng nghiệp vụ

Operation JMX được gọi trong bối cảnh runtime của ứng dụng. Trong khi client gọi \`clearCache()\`, một luồng khác có thể đang ghi hoặc đọc cache. Nếu cần thao tác nguyên tử hoặc bảo toàn invariant, code phải dùng đồng bộ, khóa, transaction hoặc cơ chế điều phối thích hợp. \`ConcurrentHashMap\` giúp thread-safe cho từng thao tác, không tạo transaction cho toàn bộ quy trình quản trị.

### 9.4. Phân quyền và bảo vệ endpoint

Remote JMX có thể mở ra một đường điều khiển ứng dụng. Xác thực, phân quyền, mã hóa kết nối và giới hạn mạng phải được thiết kế theo môi trường. Một cờ \`MaintenanceEnabled\` trong MBean chỉ là kiểm tra trạng thái nghiệp vụ; nó không thay cho bảo mật của transport và người gọi. Không đặt mật khẩu, token hay thông tin nhạy cảm trong attribute công khai.

### 9.5. Thời gian thực hiện và trải nghiệm client

Operation xử lý lâu có thể làm JConsole bị chờ hoặc lỗi kết nối. Điều này không đồng nghĩa operation chắc chắn thất bại. Với tác vụ dài, nên tách khởi tạo và theo dõi trạng thái, đồng thời ghi log hoặc metrics đủ để xác định kết quả. Không nên chạy công việc nặng trên luồng quản trị mà không có chiến lược giới hạn và hủy hợp lý.

## 10. Xử lý lỗi khi gọi operation

Các lỗi phổ biến từ JMX API:

| Tình huống | Ngoại lệ hoặc biểu hiện thường gặp | Cách xác minh |
| --- | --- | --- |
| Không tồn tại MBean theo \`ObjectName\` | \`InstanceNotFoundException\` | Tra \`isRegistered(name)\` và danh sách \`queryNames\` |
| Tên operation hoặc chữ ký không đúng | \`ReflectionException\` hoặc lỗi invoke tương ứng | Xem \`MBeanInfo.getOperations()\` và signature |
| Implementation ném runtime exception | \`RuntimeMBeanException\` | Kiểm tra cause và log phía server |
| Implementation ném checked exception | \`MBeanException\` | Kiểm tra target exception và ngữ cảnh |
| Không thể truy cập JMX endpoint | Lỗi kết nối/I/O hoặc xác thực | Xác minh JMX service URL, network và quyền |
| Client timeout/mất kết nối sau invoke | Kết quả thực thi có thể chưa rõ | Tra log/trạng thái trước khi quyết định retry |

Ví dụ trong \`CacheControl.clearCache()\`, khi chưa bật maintenance mode, implementation ném \`IllegalStateException\`. Tầng JMX có thể bọc ngoại lệ runtime trong \`RuntimeMBeanException\`. JConsole thường hiển thị thông báo lỗi, nhưng cách thể hiện tùy công cụ; cần kiểm tra nguyên nhân gốc ở server.

Không diễn giải lỗi UI của công cụ quản trị thành kết luận về trạng thái dữ liệu. Khi kết quả mơ hồ, hãy kiểm tra metric/trạng thái trong JVM và log có correlation phù hợp.

## 11. Quy trình gọi operation an toàn trong môi trường thử nghiệm

Trước khi invoke:

1. Xác định đúng JVM, \`MBeanServer\` và \`ObjectName\`, đặc biệt khi có nhiều instance tương tự.
2. Đọc \`MBeanInfo\` để biết tên operation, loại tham số, return type và thông tin impact.
3. Đọc thuộc tính hiện tại và các điều kiện trước khi gọi, chẳng hạn \`MaintenanceEnabled\`.
4. Hiểu rõ tác động trên đối tượng được quản lý; chọn dữ liệu thử nghiệm nếu có thể.
5. Chỉ gọi một lần, ghi nhận thời điểm, tham số và kết quả.
6. Đọc lại attribute và log để xác nhận trạng thái thực tế.
7. Khôi phục các trạng thái cấu hình tạm như maintenance mode nếu phù hợp.
8. Nếu thao tác lỗi hoặc trả kết quả mơ hồ, xác minh hậu quả trước khi gọi lại.

Quy trình này là cách tiếp cận thực hành cho môi trường học tập và vận hành có kiểm soát. Nó không đảm bảo một operation tùy ý là an toàn: mức rủi ro phụ thuộc logic nghiệp vụ và môi trường thực tế.

## 12. Bài tập thực hành

**Bài 1 — Thao tác có side effect.** Tạo \`CounterControlMBean\` có \`getCount()\`, \`incrementBy(int amount)\` và \`reset()\`. Đăng ký với \`ObjectName\` \`com.example.jmx:type=CounterControl,name=demo\`. Dùng JConsole gọi \`incrementBy(5)\` và \`reset()\`, đọc lại attribute sau từng bước.

**Bài 2 — Kiểm tra signature.** Gọi \`incrementBy\` qua \`MBeanServer.invoke\` với \`new Object[]{5}\` và \`new String[]{"int"}\`. Sau đó cố tình dùng \`"java.lang.String"\` làm signature, quan sát lỗi rồi đối chiếu với metadata trả về từ \`getMBeanInfo\`.

**Bài 3 — Retry.** Thiết kế operation \`triggerCleanup(String requestId)\` chỉ thực hiện cleanup một lần cho mỗi ID. Mô tả cách phát hiện ID trùng, cách lưu trạng thái và hậu quả khi client mất kết nối trước khi nhận kết quả. Không cần chạy cleanup thật trên dữ liệu sản xuất.

**Bài 4 — Spring Framework.** Tạo bean có operation \`reloadRules()\`, export qua \`MBeanExporter\`, rồi dùng JConsole kiểm tra metadata và gọi trên dữ liệu cấu hình thử nghiệm. Xác nhận JMX không tự yêu cầu HTTP endpoint và operation chạy trong cùng JVM ứng dụng.

## Kết luận

Gọi operation thông qua JConsole hoặc JMX client là hành động trực tiếp trên đối tượng quản trị của JVM. Với những method như \`clearCache\`, \`resetStatistics\`, \`pauseScheduler\` hoặc \`triggerMaintenance\`, lời gọi có thể thay đổi trạng thái ứng dụng và ảnh hưởng đến hoạt động nghiệp vụ. Cần hiểu đúng \`ObjectName\`, operation signature, điều kiện trước khi gọi, tính đồng thời, rủi ro retry và phương án xác minh kết quả. Spring Framework hỗ trợ xuất MBean ra JMX, còn tác dụng phụ thực tế của operation vẫn do implementation quyết định.
