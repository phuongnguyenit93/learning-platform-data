# SimpleReflectiveMBeanInfoAssembler trong Spring Framework JMX

## 1. Mục tiêu

Khi một Spring bean được xuất bản thành MBean qua JMX, MBeanServer cần biết bean đó công bố những **attribute** nào và những **operation** nào. Thông tin này được biểu diễn bằng \`MBeanInfo\`, gồm danh sách thuộc tính, thao tác, constructor, notification và các descriptor liên quan.

Spring Framework có giao diện \`MBeanInfoAssembler\` và nhiều implementation để quyết định **bề mặt quản trị** được công bố. \`SimpleReflectiveMBeanInfoAssembler\` là assembler dựa trên reflection, dùng các phương thức Java public của bean để xây metadata quản trị theo quy tắc mặc định thay vì yêu cầu metadata annotation hay một danh sách method được chỉ định trước.

Sự thuận tiện của nó cũng là giới hạn quan trọng: nếu bean có nhiều public method, assembler phản chiếu đơn giản có thể công bố những method vốn chỉ dành cho implementation nội bộ. Vì thế cần hiểu rõ hành vi, phạm vi sử dụng và ranh giới bảo mật trước khi dùng.

## 2. Assembler đóng vai trò gì?

\`MBeanExporter\` là thành phần của Spring giúp đăng ký Spring bean vào \`MBeanServer\`. Khi bean chưa phải một MBean phù hợp theo chuẩn JMX, exporter có thể thích ứng bean thành \`ModelMBean\`. \`MBeanInfoAssembler\` xác định metadata sẽ xuất hiện trong MBeanInfo của đối tượng được thích ứng.

Luồng xử lý khái quát:

\`\`\`text
Spring-managed bean
      |
      v
MBeanExporter
      |
      +--> MBeanInfoAssembler
      |         |
      |         +--> tìm getter/setter -> JMX attributes
      |         +--> tìm phương thức  -> JMX operations
      |
      +--> ObjectNamingStrategy -> ObjectName
      |
      v
JMX ModelMBean / MBeanServer
      |
      v
JConsole / VisualVM / JMX client
\`\`\`

Một assembler không tự mở remote connector, không đăng ký tất cả bean trong context, và không phân quyền cho client. Nó quyết định **metadata quản trị của bean được chọn để export**, còn việc đăng ký, naming và connector thuộc các thành phần khác.

## 3. SimpleReflectiveMBeanInfoAssembler là gì?

Lớp nằm trong package:

\`\`\`java
org.springframework.jmx.export.assembler.SimpleReflectiveMBeanInfoAssembler
\`\`\`

Nó thuộc nhóm assembler dựa trên reflection của Spring JMX. Với các quy tắc mặc định của loại assembler này:

- Các JavaBean getter/setter public có thể được công bố thành JMX attributes.
- Các public methods có thể được công bố thành JMX operations theo cơ chế phản chiếu.
- Không cần khai báo \`@ManagedAttribute\` hoặc \`@ManagedOperation\` để chọn từng method.
- Các phương thức được kế thừa và các phương thức framework/public utility cần được xem xét khi chọn loại assembler này.

Vì thế, tên “SimpleReflective” mô tả **cách tạo metadata từ hình dạng class**, không có nghĩa đây là lớp bảo mật đơn giản hoặc chỉ đọc.

Ví dụ một service:

\`\`\`java
public class CacheService {
    private int entryCount;

    public int getEntryCount() {
        return entryCount;
    }

    public void clearCache() {
        entryCount = 0;
    }

    public void reloadConfiguration() {
        // Nạp lại cấu hình
    }
}
\`\`\`

Nếu được export bằng reflection assembler, JMX client có thể thấy \`EntryCount\` như attribute và các public operations như \`clearCache\`, \`reloadConfiguration\` tùy metadata thực tế. Điều này khác với việc chỉ định thủ công “chỉ công bố getEntryCount”.

**Quan điểm thiết kế:** Public đối với Java caller không đồng nghĩa phù hợp để công bố cho JMX operator. Một method public có thể phục vụ API nội bộ, không được thiết kế cho invocation từ một công cụ quản trị có quyền truy cập.

## 4. Phân biệt getter/setter với operation

JMX có khái niệm thuộc tính và operation:

- **Attribute** biểu diễn trạng thái có thể đọc hoặc ghi, thường được ánh xạ từ JavaBean getter/setter.
- **Operation** biểu diễn hành động, thường ánh xạ từ method Java được công bố trong \`MBeanOperationInfo\`.
- **MBeanInfo** mô tả contract mà JMX client thấy, không nhất thiết phản ánh mọi chi tiết class.

Ví dụ:

\`\`\`java
public class WorkerPool {
    private volatile boolean enabled = true;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public int getActiveWorkers() {
        return 4;
    }

    public void requestRefresh() {
        // Yêu cầu refresh
    }
}
\`\`\`

Một MBeanInfo phù hợp có thể cung cấp:

\`\`\`text
Attributes
  Enabled        boolean  readable=true  writable=true
  ActiveWorkers  int      readable=true  writable=false

Operations
  requestRefresh()
\`\`\`

Nhưng điều cần kiểm tra là output thực tế của assembler trên class tương ứng. Không nên đoán toàn bộ tập operations được công bố chỉ từ bảng trên vì quy tắc loại trừ getter/setter khỏi operation và xử lý method kế thừa có thể ảnh hưởng metadata.

Khi chỉ muốn \`ActiveWorkers\` và \`requestRefresh\`, cần chọn assembler/cấu hình cho phép kiểm soát chính xác những method đó.

## 5. Ví dụ cấu hình bằng MBeanExporter

Ví dụ cấu hình Spring Java-based tạo một bean quản trị và dùng \`SimpleReflectiveMBeanInfoAssembler\`:

\`\`\`java
package com.example.config;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.SimpleReflectiveMBeanInfoAssembler;

@Configuration
public class JmxConfiguration {

    @Bean
    public WorkerPoolControl workerPoolControl() {
        return new WorkerPoolControl();
    }

    @Bean
    public MBeanExporter mbeanExporter(
            WorkerPoolControl workerPoolControl) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
            "com.example.jobs:type=WorkerPool,name=Main",
            workerPoolControl
        ));
        exporter.setAssembler(
            new SimpleReflectiveMBeanInfoAssembler()
        );

        return exporter;
    }
}
\`\`\`

Bean được export:

\`\`\`java
package com.example.config;

public class WorkerPoolControl {
    private volatile boolean enabled = true;
    private volatile int activeWorkers = 2;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public int getActiveWorkers() {
        return activeWorkers;
    }

    public void requestRefresh() {
        // Một thao tác quản trị minh họa.
    }
}
\`\`\`

\`setBeans\` chỉ định rõ bean và key được sử dụng làm ObjectName. Key ở ví dụ là chuỗi ObjectName hợp lệ. Trong triển khai này, \`MBeanExporter\` thích ứng đối tượng thông qua assembler rồi đăng ký vào MBeanServer được cấu hình hoặc server mà exporter tìm được.

Không bật thêm một exporter khác đăng ký cùng ObjectName mà không có chủ đích; nếu một context cấu hình \`@EnableMBeanExport\` đồng thời với exporter thủ công, cần kiểm tra khả năng đăng ký trùng.

### Điểm quan trọng về cấu hình

\`SimpleReflectiveMBeanInfoAssembler\` chỉ là cách chọn metadata. Nếu trong ứng dụng có một bean vốn đã là JMX-compliant MBean hoặc cấu hình exporter sử dụng một đường thích ứng khác, metadata thực tế có thể đi theo quy tắc của MBean tương ứng. Vì vậy cần xem \`MBeanInfo\` sau khi đăng ký, thay vì giả định mọi đối tượng đều phản chiếu theo một đường duy nhất.

## 6. Ví dụ chạy và khám phá MBeanInfo

Có thể kiểm tra những attribute/operation đã được export bằng API JMX tiêu chuẩn:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class InspectMBean {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.jobs:type=WorkerPool,name=Main"
        );

        if (!server.isRegistered(name)) {
            throw new IllegalStateException(
                "MBean is not registered: " + name
            );
        }

        MBeanInfo info = server.getMBeanInfo(name);

        for (MBeanAttributeInfo attr : info.getAttributes()) {
            System.out.printf(
                "Attribute %s type=%s read=%s write=%s%n",
                attr.getName(),
                attr.getType(),
                attr.isReadable(),
                attr.isWritable()
            );
        }

        for (MBeanOperationInfo operation : info.getOperations()) {
            System.out.println(
                "Operation " + operation.getName()
            );
        }
    }
}
\`\`\`

Đoạn mã giả định MBean đã được export vào platform MBeanServer. Nếu exporter dùng MBeanServer khác, phải lấy đúng kết nối hoặc server đó.

Việc kiểm tra \`MBeanInfo\` hữu ích vì nó cho biết contract JMX cuối cùng chứ không chỉ các method bạn dự định expose trong Java.

## 7. So sánh với các MBeanInfoAssembler khác

Spring cung cấp nhiều chiến lược chọn bề mặt quản trị:

| Assembler | Nguyên tắc | Trường hợp thích hợp |
| --- | --- | --- |
| \`SimpleReflectiveMBeanInfoAssembler\` | Reflection đơn giản, công bố rộng các public members theo quy tắc assembler | Prototype, ứng dụng nội bộ được kiểm soát, class chuyên quản trị có API nhỏ |
| \`MethodNameBasedMBeanInfoAssembler\` | Chọn method theo danh sách tên được cấu hình | Khi muốn allowlist một vài operation/accessor |
| \`MethodExclusionMBeanInfoAssembler\` | Reflection nhưng loại trừ các method được liệt kê | Khi chỉ cần loại một vài method khỏi một bề mặt được kiểm soát |
| \`InterfaceBasedMBeanInfoAssembler\` | Chọn method dựa trên interface chỉ định | Khi có management interface rõ ràng |
| \`MetadataMBeanInfoAssembler\` | Chọn theo metadata/annotation thông qua \`JmxAttributeSource\` | Khi muốn annotation-based JMX export chọn lọc |

Sự khác biệt nằm ở **ai quyết định danh sách method được công bố**:

\`\`\`text
SimpleReflective -> nhìn vào public methods của class
MethodNameBased  -> lấy các method nằm trong allowlist
MethodExclusion  -> phản chiếu nhưng loại các method chỉ định
InterfaceBased   -> lấy từ management interface
Metadata         -> lấy từ annotation/metadata
\`\`\`

Nếu class chỉ chứa đúng API quản trị đã được thiết kế, simple reflection có thể giảm cấu hình. Nếu class là một service nghiệp vụ với nhiều public methods, nên ưu tiên allowlist, management interface hoặc annotation để ngăn việc expose ngoài ý muốn.

## 8. So sánh với @ManagedAttribute và @ManagedOperation

Cấu hình annotation-based JMX:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.jobs:type=WorkerPool,name=Main"
)
public class WorkerPoolControl {
    @ManagedAttribute
    public int getActiveWorkers() {
        return 2;
    }

    @ManagedOperation
    public void requestRefresh() {
        // Logic refresh
    }

    public void deleteAllRecords() {
        // API nội bộ, không định công bố qua JMX.
    }
}
\`\`\`

Với annotation-based export được cấu hình bằng \`@EnableMBeanExport\` hoặc \`MetadataMBeanInfoAssembler\`, metadata \`@ManagedAttribute\` và \`@ManagedOperation\` được dùng để quyết định phạm vi export.

Với \`SimpleReflectiveMBeanInfoAssembler\`, các annotation đó không phải bộ lọc mặc định của assembler. Public method \`deleteAllRecords\` có thể được đưa ra dưới dạng JMX operation dù không gắn \`@ManagedOperation\`.

**Không thể chỉ thêm annotation rồi giả định các public method khác được ẩn nếu exporter vẫn dùng simple reflection.** Phải chọn đúng assembler và kiểm tra \`MBeanInfo\` đã xuất bản.

## 9. Bảo mật: reflection không phải là allowlist quyền

Một số hiểu nhầm nguy hiểm:

> “Method không có annotation nên JMX không gọi được.”

Điều này chỉ đúng khi annotation/metadata assembler chọn lọc được dùng theo cấu hình phù hợp. Với reflection assembler, phương thức public có thể được export theo quy tắc phản chiếu ngay cả khi không có annotation.

> “Method private nên an toàn; các public method đều có thể expose.”

Java \`public\` chỉ mô tả khả năng gọi trong Java API, không có nghĩa method phù hợp để vận hành qua mạng. JMX client có thể được cấp quyền gọi \`invoke\`, và một public method \`resetDatabase()\` hoặc \`shutdown()\` có thể gây ảnh hưởng lớn nếu vô tình export.

> “Chỉ dùng JConsole nội bộ nên không cần giới hạn.”

Công cụ JMX local cũng có quyền quản trị và có thể bị sử dụng nhầm. Remote connector còn có rủi ro network, credentials và authorization. Giới hạn bề mặt MBean là một lớp phòng vệ bổ sung.

Những API không nên vô tình expose:

- \`getPassword()\`, \`getAccessToken()\` hoặc getter trả cấu hình chứa secret.
- \`deleteAll()\`, \`shutdown()\`, \`execute(String command)\`, các hàm quản trị có tác động lớn.
- Getter trả collection lớn, object chứa dữ liệu người dùng hoặc internal graph.
- Method thao tác database/network tốn tài nguyên và không có giới hạn.
- Method debug thay đổi trạng thái mà không có audit hoặc validation.

Một nguyên tắc thực tế: **trong production, không dùng simple reflection trực tiếp trên service nghiệp vụ lớn chỉ để khỏi viết annotation**. Nếu cần dùng, hãy export một adapter chuyên biệt chỉ có những public method phục vụ quản trị.

## 10. Tách management adapter khi muốn dùng simple reflection

Giả sử một service nghiệp vụ có API rộng:

\`\`\`java
public class OrderService {
    public int getPendingCount() { /* ... */ return 0; }
    public void submitOrder(String payload) { /* ... */ }
    public void cancelOrder(String id) { /* ... */ }
    public void purgeFailedOrders() { /* ... */ }
}
\`\`\`

Nếu export trực tiếp service bằng simple reflection, nhiều public operations có thể xuất hiện ngoài mong muốn. Thay bằng management adapter nhỏ:

\`\`\`java
public class OrderManagementView {
    private final OrderService service;

    public OrderManagementView(OrderService service) {
        this.service = service;
    }

    public int getPendingCount() {
        return service.getPendingCount();
    }

    public String getStatus() {
        return "RUNNING";
    }
}
\`\`\`

Chỉ đăng ký \`OrderManagementView\` qua \`MBeanExporter\`. Trong trường hợp này, bề mặt public của adapter có ít method và mang ngữ nghĩa quản trị rõ ràng. Nhưng vẫn cần kiểm tra \`MBeanInfo\`: các public methods được kế thừa hoặc thêm trong tương lai cũng có thể thay đổi contract được phản chiếu.

Nếu cần kiểm soát chặt tuyệt đối, nên ưu tiên \`InterfaceBasedMBeanInfoAssembler\`, \`MethodNameBasedMBeanInfoAssembler\` hoặc annotation-based assembler cho phép chọn đúng danh sách.

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| JConsole thấy nhiều operations ngoài dự định | Simple reflection lấy public methods | Chuyển sang metadata/interface/allowlist assembler |
| Method không có annotation vẫn xuất hiện | Annotation không phải bộ lọc của simple reflection | Chọn \`MetadataMBeanInfoAssembler\` |
| Getter xuất hiện như writable attribute | Setter public tương ứng cũng được expose | Xóa setter khỏi contract hoặc dùng assembler chọn lọc |
| Metadata description nghèo nàn | Reflection không cung cấp mô tả chuyên biệt như annotation | Dùng metadata annotation hoặc assembler hỗ trợ mô tả |
| Không thấy MBean | Exporter chưa đăng ký, sai ObjectName/server | Kiểm tra cấu hình MBeanExporter, tên, MBeanServer |
| \`InstanceAlreadyExistsException\` | Trùng ObjectName trong MBeanServer | Dùng ObjectName duy nhất, tránh exporter đăng ký lặp |
| Remote client lỗi khi đọc attribute | Kiểu không thể deserialize hoặc không có class ở client | Dùng primitive/Open Types/MXBean-compatible data |
| Getter monitoring làm chậm hệ thống | Getter tính toán nặng, bị polling liên tục | Trả snapshot/counter và giới hạn tài nguyên |

### Điều cần biết khi refactor

Nếu trước đây một public method không bị expose nhưng sau một lần refactor lại được mở public, simple reflection có thể đưa nó vào MBeanInfo. Như vậy việc refactor code nội bộ vô tình trở thành **thay đổi API quản trị**. Mỗi lần thêm public method vào class được export bằng reflection, cần xem xét tác động JMX.

Ngược lại, khi đổi tên method hoặc đổi signature, dashboard/script đang gọi attribute/operation cũ có thể bị phá vỡ. Do đó nên xem management contract là một API có yêu cầu tương thích phiên bản.

## 12. Performance và concurrency

Assembler thường xây dựng metadata trong quá trình export, nhưng **getter/operation của MBean được gọi khi client yêu cầu**, có thể nhiều lần và đồng thời.

- Getter công bố thành attribute nên nhanh, không có side effect.
- Không để getter mỗi lần bị polling lại quét cả database hoặc tạo object quá lớn.
- Tránh operation làm thay đổi state nếu client có thể gọi nhiều lần mà thiếu xác thực/validation.
- State do nhiều thread ghi cần thread-safe; reflection không bổ sung locking.
- Các attribute chứa số liệu nên có đơn vị, ngữ nghĩa và quy ước khi unavailable rõ ràng.
- Khi cần nhiều metrics nhất quán, cân nhắc snapshot thay vì đọc rời rạc trong khoảng thời gian dài.

Một class có phương thức \`public String getStatus()\` không tự động là an toàn. Nếu bên trong \`getStatus()\` tạo kết nối mạng hoặc giữ lock lâu, JMX monitoring vẫn có thể làm chậm ứng dụng.

## 13. Tình huống chọn assembler

### Tình huống A: Ứng dụng demo hoặc công cụ nội bộ

Một class nhỏ chỉ có \`getActiveCount\`, \`isEnabled\`, \`requestRefresh\`; người quản lý muốn xem ngay qua JConsole. \`SimpleReflectiveMBeanInfoAssembler\` có thể giúp giảm cấu hình metadata.

### Tình huống B: Service nghiệp vụ production có API rộng

Service có nhiều method public, bao gồm thay đổi dữ liệu. Không nên export trực tiếp bằng simple reflection. Hãy dùng management adapter chọn lọc và metadata/interface-based assembler.

### Tình huống C: API quản trị cần ổn định qua nhiều phiên bản

Một management interface riêng với \`InterfaceBasedMBeanInfoAssembler\` hoặc annotation contract có thể giúp phát hiện dễ hơn khi thay đổi attribute/operation. Tránh cho reflection tự động mở rộng contract mỗi lần thêm public method nội bộ.

### Tình huống D: Cần tên/description trong công cụ JMX

\`MetadataMBeanInfoAssembler\` kết hợp \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\` thường cung cấp khả năng khai báo metadata chính xác hơn simple reflection.

## 14. Mô hình tư duy

\`\`\`text
                     Spring bean
                         |
             +-----------+-----------+
             |                       |
      SimpleReflective          Metadata/Interface
             |                       |
       Public methods          Selected methods
       Getter / setter         Annotation/interface
             |                       |
             +----------+------------+
                        |
                   MBeanInfo
                        |
                  MBeanExporter
                        |
                  MBeanServer
                        |
                JMX management client
\`\`\`

**Ghi nhớ:** \`SimpleReflectiveMBeanInfoAssembler\` tạo giao diện quản trị bằng cách phản chiếu public methods của bean, nhờ đó cấu hình nhanh nhưng dễ công bố rộng hơn ý định. Nó không dựa vào \`@ManagedAttribute\`/\`@ManagedOperation\` làm allowlist. Với Spring JMX trong ứng dụng thực, hãy ưu tiên API quản trị nhỏ, metadata được chọn rõ ràng, kiểm tra MBeanInfo và giới hạn quyền truy cập connector. Reflection là kỹ thuật tạo metadata, không phải một chính sách bảo mật.
