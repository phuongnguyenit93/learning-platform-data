# Thuộc tính currencyTimeLimit và persistence metadata ở đâu còn phù hợp trong Spring JMX ManagedResource

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích ý nghĩa của **\`currencyTimeLimit\`** trong metadata JMX và phân biệt metadata “độ mới” với cơ chế cache thực sự.
- Nhận biết các trường **\`persistPolicy\`**, **\`persistPeriod\`**, **\`persistName\`** và **\`persistLocation\`** trong mô hình descriptor liên quan đến persistence của Model MBean.
- Xác định khi nào annotation \`@ManagedResource\` của Spring Framework có thể cung cấp các giá trị này cho **ModelMBeanInfo** và **Descriptor**.
- Hiểu rằng khai báo metadata không đồng nghĩa Spring hoặc JVM tự động cung cấp cơ chế cache, snapshot, storage và durability phù hợp với mọi ứng dụng.
- Phân biệt giá trị metadata ở **resource**, **attribute** và **operation**; kiểm tra metadata được xuất thực tế bằng \`MBeanServer.getMBeanInfo\`.
- Quyết định khi nào nên dùng metadata legacy JMX, khi nào nên tự triển khai caching/persistence trong service hoặc dùng hệ thống metrics và cấu hình hiện đại.
- Tránh lỗi vận hành do hiểu sai \`currencyTimeLimit\`, chính sách lưu trạng thái và vòng đời MBean trong ứng dụng Spring.

## 2. Bối cảnh: ManagedResource và Model MBean

Trong Spring Framework, \`@ManagedResource\` đánh dấu một bean là tài nguyên có thể xuất qua JMX khi ứng dụng cấu hình **\`MBeanExporter\`** cùng cơ chế đọc annotation phù hợp. Cùng với \`@ManagedAttribute\` và \`@ManagedOperation\`, Spring có thể xây dựng metadata quản trị cho bean.

Ví dụ:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example:type=Cache,name=Products",
    description = "Cache management resource"
)
public class CacheManagement {
    // ...
}
\`\`\`

Một số thuộc tính của \`@ManagedResource\` có tên mang tính lịch sử như \`currencyTimeLimit\`, \`persistPolicy\`, \`persistPeriod\`, \`persistName\`, \`persistLocation\`. Chúng xuất phát từ mô hình **JMX Model MBean metadata**, đặc biệt là các descriptor field mô tả cách quản trị, caching hoặc persistence có thể được xử lý.

Cần tách ba tầng:

\`\`\`text
Spring bean / application service
          |
          | @ManagedResource, @ManagedAttribute,
          | @ManagedOperation
          v
Spring JMX exporter + metadata assembler
          |
          | chuyển thông tin thành MBeanInfo,
          | ModelMBeanInfo / Descriptor
          v
MBeanServer / Model MBean
          |
          | JMX client truy vấn metadata
          v
JConsole, custom JMX client, management tool
\`\`\`

Các annotation là **đầu vào mô tả**. Hành vi quan sát thực tế phụ thuộc Spring exporter, assembler, kiểu ModelMBean, phiên bản JMX, cấu hình và cách client sử dụng metadata.

**Không nên suy luận rằng cứ thêm một annotation là cache/persistence nghiệp vụ của ứng dụng được thiết lập hoàn chỉnh.**

## 3. currencyTimeLimit là gì?

\`currencyTimeLimit\` là một descriptor field chuẩn trong JMX Model MBean, liên quan đến thời gian một giá trị được xem là còn đủ mới để sử dụng. Trường này thường được biểu diễn bằng **số giây** và có thể xuất hiện ở descriptor của thuộc tính, operation hoặc MBean.

Trong mô hình Model MBean, \`currencyTimeLimit\` ảnh hưởng đến chính sách dùng lại giá trị đã có hoặc gọi lại nguồn lấy dữ liệu, theo semantics của JMX Model MBean implementation.

Một cách hình dung:

\`\`\`text
Client gọi getAttribute("CacheSize")
                 |
                 v
      Model MBean xem descriptor
                 |
           currencyTimeLimit
                 |
           +-----+------+
           |            |
     cached value   cần cập nhật
     còn hợp lệ?    hoặc không cache
           |            |
           v            v
    trả giá trị cũ    gọi getter nguồn
                         |
                         v
                    cập nhật giá trị
                         |
                         v
                      trả client
\`\`\`

Không nên mặc định mọi **Standard MBean**, **MXBean** hoặc getter Java đều dùng field này. Nó có ý nghĩa đặc biệt khi chạy qua Model MBean hoặc một implementation thực sự diễn giải descriptor. Nếu MBean được xuất theo cơ chế khác, descriptor có thể chỉ là metadata hoặc không hiện diện.

### 3.1. Giá trị thường gặp

Trong JMX Model MBean semantics, các giá trị hay gặp:

| Giá trị | Ý nghĩa thông dụng |
| --- | --- |
| \`-1\` | Không cache: lấy giá trị mới khi cần. |
| \`0\` | Có thể giữ giá trị trong cache mà không hết hạn theo thời gian. |
| Số dương \`N\` | Giá trị cache được xem là hợp lệ trong khoảng \`N\` giây. |

Đây là quy ước Model MBean; hãy đối chiếu descriptor thực tế và implementation được dùng. Đặc biệt, \`0\` không có nghĩa “cập nhật mỗi 0 giây”; trong mô hình này nó biểu diễn chính sách cache vô hạn, có thể tạo giá trị cũ kéo dài nếu không có cơ chế invalidation.

### 3.2. Ví dụ đọc trạng thái thay đổi

Giả sử bean có getter:

\`\`\`java
public long getQueueDepth() {
    return queue.size();
}
\`\`\`

Nếu một Model MBean áp dụng \`currencyTimeLimit=15\` ở attribute, các lần đọc gần nhau có thể nhận cùng giá trị được cache dù queue đã thay đổi. Điều này có thể phù hợp với chỉ số vận hành biến đổi vừa phải, nhưng không phù hợp cho số liệu đòi hỏi độ mới ngay lập tức.

Trong một dashboard liên tục polling:

\`\`\`text
12:00:00   queue depth thực = 20 -> JMX đọc 20
12:00:05   queue depth thực = 50 -> JMX có thể vẫn trả 20
12:00:16   queue depth thực = 12 -> JMX lấy lại và trả 12
\`\`\`

Đây là minh họa về chính sách cache, không phải bảo đảm thời điểm cập nhật tuyệt đối: thời điểm lấy lại dữ liệu còn phụ thuộc thời điểm đọc, descriptor và implementation.

### 3.3. Những điều currencyTimeLimit không làm

- Không bật cache HTTP, Spring Cache hoặc cache dữ liệu nghiệp vụ.
- Không bảo đảm tất cả JMX clients đồng bộ refresh theo một lịch cố định.
- Không tự động biến getter tốn tài nguyên thành một hệ đo lường có backpressure.
- Không quyết định TTL của Redis, Caffeine, Ehcache hay cache bên ngoài.
- Không đảm bảo thread safety hoặc snapshot consistency của code getter.
- Không thay thế việc thiết kế dữ liệu metrics có timestamp hoặc freshness rõ ràng.

Do đó khi tối ưu getter JMX, cần xem cả nguồn dữ liệu, chi phí tính toán, phạm vi cache và yêu cầu độ mới của người vận hành.

## 4. Metadata của resource, attribute và operation

Spring JMX annotation có nhiều cấp độ. Phạm vi đặt metadata quyết định đối tượng quản trị nhận descriptor field.

**Resource-level** dùng \`@ManagedResource\`, mô tả MBean nói chung:

\`\`\`java
@ManagedResource(
    objectName = "com.example:type=Cache,name=Products",
    currencyTimeLimit = 10
)
public class CacheManagement {
    // ...
}
\`\`\`

**Attribute-level** dùng \`@ManagedAttribute\`, mô tả thuộc tính cụ thể:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;

@ManagedAttribute(
    description = "Number of cache entries",
    currencyTimeLimit = 5
)
public int getEntryCount() {
    return cache.size();
}
\`\`\`

**Operation-level** dùng \`@ManagedOperation\` để mô tả lệnh; các thuộc tính metadata được Spring hỗ trợ tùy loại annotation và phiên bản. Với Model MBean, currencyTimeLimit cũng có thể thuộc operation descriptor do JMX Model MBean công bố.

Điểm cần phân biệt:

| Cấp độ | Ví dụ sử dụng | Ý nghĩa cần kiểm tra |
| --- | --- | --- |
| MBean/resource | \`@ManagedResource.currencyTimeLimit\` | Metadata chung cho tài nguyên. |
| Attribute | \`@ManagedAttribute.currencyTimeLimit\` | Metadata áp dụng riêng cho một thuộc tính. |
| Operation | Descriptor của operation | Có thể ảnh hưởng chiến lược cache kết quả operation nếu Model MBean hỗ trợ. |

Khi đặt cả resource-level và attribute-level, không nên tự suy đoán quy tắc precedence. Hãy kiểm tra \`ModelMBeanInfo\` và descriptor được tạo trong phiên bản Spring/JMX đang chạy, rồi thử hành vi đọc thuộc tính.

## 5. persistence metadata là gì?

Các descriptor field persistence trong Model MBean mô tả **chính sách và vị trí lưu trạng thái** mà implementation có thể dùng. Đây là khái niệm khác với transaction, database persistence hoặc cấu hình Spring Data.

Những field thường gặp:

| Field | Ý nghĩa khái quát |
| --- | --- |
| \`persistPolicy\` | Chính sách thời điểm hoặc điều kiện persist. |
| \`persistPeriod\` | Chu kỳ liên quan persistence, thường theo giây khi policy yêu cầu chu kỳ. |
| \`persistName\` | Tên gợi ý cho đối tượng/file lưu trữ. |
| \`persistLocation\` | Vị trí gợi ý cho lưu trữ. |

Đối với Model MBean theo JMX specification, \`persistPolicy\` có thể nhận những giá trị biểu thị cách kích hoạt lưu trữ, ví dụ \`Never\`, \`OnUpdate\`, \`OnTimer\`, \`NoMoreOftenThan\`, \`Always\` hoặc chính sách được implementation hỗ trợ.

Tuy nhiên **khả năng persistence thực tế phụ thuộc ModelMBean implementation**, các hook lưu/khôi phục, file permission, cơ chế storage và lifecycle. Không có bảo đảm một descriptor được điền sẽ tạo file hay database record đúng mong đợi.

### 5.1. persistPolicy

\`persistPolicy\` mô tả *khi nào nên lưu* giá trị hoặc trạng thái:

- \`Never\`: không yêu cầu persist theo chính sách này.
- \`OnUpdate\`: gắn việc lưu với cập nhật.
- \`OnTimer\`: chính sách liên quan thời gian/chu kỳ.
- \`NoMoreOftenThan\`: hạn chế tần suất persist.
- \`Always\`: mô tả chính sách persist thường xuyên theo semantics implementation.

Tên policy không thay thế việc kiểm tra code và tài liệu của Model MBean thực sự được sử dụng.

### 5.2. persistPeriod

\`persistPeriod\` cung cấp tham số thời gian cho các policy có tính chu kỳ, thường đơn vị giây trong mô hình Model MBean descriptor. Nếu persistPolicy không sử dụng chu kỳ, field này có thể không tạo tác dụng đáng kể.

Ví dụ về ý định cấu hình:

\`\`\`text
persistPolicy = OnTimer
persistPeriod = 60
\`\`\`

Hãy hiểu đây là **metadata yêu cầu/lựa chọn chính sách**, không phải lịch chạy task Spring \`@Scheduled(fixedRate=...)\` và không bảo đảm đã có background timer ghi file.

### 5.3. persistName và persistLocation

Hai field có thể dùng để mô tả tên và vị trí lưu trạng thái. Tuy nhiên việc dùng chúng để xây dựng đường dẫn file và tạo tài nguyên lưu là trách nhiệm của implementation.

Ví dụ ý định metadata:

\`\`\`text
persistName     = cache-management.snapshot
persistLocation = /var/lib/app/jmx
\`\`\`

Đây chỉ là ví dụ về tên/đường dẫn trên một host Unix-like. Không nên đặt secret hoặc dữ liệu nhạy cảm trực tiếp vào descriptor. Trên Windows, container hoặc hệ cloud không có disk ổn định, đường dẫn phải được xác định theo môi trường triển khai.

## 6. Annotation @ManagedResource có những giá trị nào?

Khi làm việc với Spring JMX, \`@ManagedResource\` cung cấp các thuộc tính định danh/mô tả như \`objectName\`, \`description\` và một số field liên quan Model MBean descriptor như \`currencyTimeLimit\`, \`persistPolicy\`, \`persistPeriod\`, \`persistName\`, \`persistLocation\` tùy API phiên bản.

Ví dụ mô tả:

\`\`\`java
package example.springjmx;

import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example:type=Maintenance,name=Cache",
    description = "Cache maintenance resource",
    currencyTimeLimit = 5,
    persistPolicy = "Never"
)
public class CacheMaintenanceAdmin {

    // Những thuộc tính/operation được export cần
    // @ManagedAttribute/@ManagedOperation hoặc
    // assembler và cấu hình tương ứng.
}
\`\`\`

**Lưu ý khi dùng Spring 6.x:** API có thể thay đổi theo minor version; khi áp dụng vào code, tham khảo Javadoc của phiên bản Spring đang chạy để xác định đúng tên thuộc tính và giá trị mặc định. Những field này có nguồn gốc từ JMX Model MBean metadata; không nên xem chúng như Spring Cache abstraction.

Một annotation trên class cũng không tự đảm bảo export. Cần có MBeanExporter (hoặc auto-configuration phù hợp) đang chọn class đó và một assembler hỗ trợ metadata annotation.

## 7. Cấu hình exporter và metadata assembler

Muốn \`@ManagedResource\` và \`@ManagedAttribute\` được diễn giải, Spring thường dùng \`AnnotationJmxAttributeSource\` cùng \`MetadataMBeanInfoAssembler\`.

Ví dụ cấu hình:

\`\`\`java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxConfiguration {

    @Bean
    public MBeanExporter exporter(CacheManagementBean bean) {
        AnnotationJmxAttributeSource attributeSource =
            new AnnotationJmxAttributeSource();

        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(attributeSource);

        MetadataNamingStrategy namingStrategy =
            new MetadataNamingStrategy();
        namingStrategy.setAttributeSource(attributeSource);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(namingStrategy);
        exporter.setBeans(Map.of("cacheManagementBean", bean));
        return exporter;
    }
}
\`\`\`

Đây là cấu hình minh họa để metadata có đường đi từ annotation tới MBeanInfo. Trong ứng dụng đã dùng Spring Boot JMX auto-configuration, tránh tạo thêm exporter cùng \`ObjectName\` mà chưa hiểu ownership; có thể xảy ra \`InstanceAlreadyExistsException\`.

\`CacheManagementBean\` trong ví dụ là bean do ứng dụng cung cấp; cần khai báo implementation và annotation thực tế. Trong một ứng dụng Spring, có thể ưu tiên dùng \`@EnableMBeanExport\` hoặc cấu hình Spring tương ứng khi phù hợp với dự án.

## 8. Kiểm tra metadata runtime thay vì đoán

Nguồn sự thật tốt nhất về những gì client JMX có thể thấy là \`MBeanInfo\` từ MBeanServer đang chạy.

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.Descriptor;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example:type=Maintenance,name=Cache"
);

MBeanInfo info = server.getMBeanInfo(name);

Descriptor descriptor = info.getDescriptor();
System.out.println(
    "MBean currencyTimeLimit = "
        + descriptor.getFieldValue("currencyTimeLimit")
);
System.out.println(
    "MBean persistPolicy = "
        + descriptor.getFieldValue("persistPolicy")
);
\`\`\`

Đoạn trên đọc descriptor ở cấp MBean. Một số field có thể được đặt ở descriptor của attribute hoặc operation thay vì MBean descriptor. Vì vậy chỉ kiểm tra \`info.getDescriptor()\` có thể chưa đủ.

### 8.1. Đọc descriptor của từng attribute

\`\`\`java
import javax.management.MBeanAttributeInfo;

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    Descriptor d = attribute.getDescriptor();

    System.out.printf(
        "%s: currencyTimeLimit=%s, persistPolicy=%s%n",
        attribute.getName(),
        d.getFieldValue("currencyTimeLimit"),
        d.getFieldValue("persistPolicy")
    );
}
\`\`\`

### 8.2. Đọc descriptor của operation

\`\`\`java
import javax.management.MBeanOperationInfo;

for (MBeanOperationInfo operation : info.getOperations()) {
    Descriptor d = operation.getDescriptor();

    System.out.printf(
        "%s: currencyTimeLimit=%s%n",
        operation.getName(),
        d.getFieldValue("currencyTimeLimit")
    );
}
\`\`\`

Nếu field nhận \`null\`, có thể là field không được đặt, descriptor không có dữ liệu đó, hoặc cơ chế export không tạo Model MBean metadata như kỳ vọng. Không nên kết luận rằng Spring đã tự bật hoặc tắt một cache thực tế chỉ từ một \`null\` này.

### 8.3. Kiểm tra loại MBean info

\`\`\`java
import javax.management.modelmbean.ModelMBeanInfo;

System.out.println(
    "Is ModelMBeanInfo = " + (info instanceof ModelMBeanInfo)
);
\`\`\`

Nếu \`true\`, bạn có thể kiểm tra thêm descriptor theo semantics Model MBean. Nếu \`false\`, không nên áp dụng mọi quy tắc Model MBean cho MBean đó.

## 9. Ví dụ thực tế: chọn currencyTimeLimit cho metrics

Giả sử có một Spring service nhận số liệu từ queue:

\`\`\`java
public interface QueueStatsService {
    long pendingMessages();
    long processedMessages();
    boolean isHealthy();
}
\`\`\`

Một JMX adapter có getter nhẹ:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example:type=Queue,name=Orders",
    description = "Order queue monitoring"
)
public class OrderQueueManagement {

    private final QueueStatsService stats;

    public OrderQueueManagement(QueueStatsService stats) {
        this.stats = stats;
    }

    @ManagedAttribute(
        description = "Current pending messages",
        currencyTimeLimit = 5
    )
    public long getPendingMessages() {
        return stats.pendingMessages();
    }

    @ManagedAttribute(
        description = "Total processed messages",
        currencyTimeLimit = -1
    )
    public long getProcessedMessages() {
        return stats.processedMessages();
    }

    @ManagedAttribute(
        description = "Whether the queue is healthy",
        currencyTimeLimit = -1
    )
    public boolean isHealthy() {
        return stats.isHealthy();
    }
}
\`\`\`

Ở đây giá trị \`5\` trên thuộc tính PendingMessages thể hiện ý định chấp nhận dữ liệu cache trong khoảng 5 giây nếu Model MBean implementation áp dụng descriptor. Với các giá trị \`-1\`, ý định là không lưu cache ở lớp Model MBean.

**Cần xác minh**:
1. Spring exporter có thật sự dùng Model MBean và metadata assembler đọc annotation không?
2. Descriptor của từng attribute có chứa currencyTimeLimit mong đợi không?
3. Giá trị đọc qua MBeanServer trong các khoảng ngắn có phản ánh chính sách cache như mong muốn không?
4. Có nên để cache ở service/collector thay cho JMX không, để có timestamp, thống nhất hành vi và dễ kiểm thử?

Một hệ monitoring hiện đại thường ưu tiên để nguồn metrics xuất ra snapshot rõ ràng; JMX getter chỉ đọc giá trị hiện tại từ đó. \`currencyTimeLimit\` vẫn hữu ích khi cần tương thích hoặc khai thác behavior của Model MBean theo thiết kế đã kiểm chứng.

## 10. Ví dụ metadata persistence và giới hạn

Xét một đối tượng quản trị trạng thái một job:

\`\`\`java
@ManagedResource(
    objectName = "com.example:type=Job,name=Importer",
    persistPolicy = "OnUpdate",
    persistName = "importer-state",
    persistLocation = "/var/lib/app/jmx"
)
public class ImportJobManagement {
    // ...
}
\`\`\`

Ý định metadata là hỗ trợ một chính sách persist liên quan cập nhật và vị trí lưu trạng thái. Tuy nhiên:

- Một \`MBeanExporter\` đơn lẻ không thay thế database hoặc storage service.
- Không có bảo đảm Model MBean tiêu chuẩn đang dùng sẽ ghi ra file này chỉ vì descriptor có đường dẫn.
- Nếu Model MBean implementation không hỗ trợ persistence, khai báo có thể không tạo lưu trữ nào.
- Persistence của trạng thái nghiệp vụ thường cần transaction, schema migration, concurrency, durability và recovery; những thứ đó không thể giải quyết chỉ bằng metadata JMX.
- Với container/cloud, đường dẫn local có thể mất sau restart nếu không có volume được quản lý.

Do đó nếu bài toán là **lưu checkpoint của job**, hãy triển khai trong service/database phù hợp. Persistence metadata của JMX chủ yếu dành cho những Model MBean hoặc framework quản trị thực sự có engine persistence tương ứng.

## 11. Lịch sử thiết kế và lý do những field này còn tồn tại

JMX Model MBean được xây dựng để mô tả các managed resources qua metadata chuẩn, nhằm cho phép công cụ và agent quản trị sử dụng descriptor để điều khiển caching, persistence và thông tin quản trị theo cùng một hợp đồng.

Trong Spring JMX, \`@ManagedResource\` và \`ManagedResource\` metadata giữ những trường này để hỗ trợ ModelMBean semantics và tương thích với hệ thống quản trị Java truyền thống.

Những field này **còn phù hợp** trong các trường hợp:

- Ứng dụng dùng Model MBean hoặc một JMX agent diễn giải descriptor theo đúng JMX semantics.
- Cần tương thích với công cụ quản trị enterprise cũ đang đọc currencyTimeLimit/persistPolicy.
- Có yêu cầu cụ thể để giới hạn số lần gọi getter của Model MBean và đã kiểm thử cache behavior.
- Một implementation Model MBean có persistence engine hỗ trợ descriptor và ứng dụng cần dùng theo hợp đồng đó.
- Muốn mô tả/công bố metadata cho client JMX tiêu chuẩn, ngay cả khi không dùng mọi feature.

Chúng **ít phù hợp** khi:

- Dùng Standard MBean/MXBean đơn giản với getter trực tiếp không áp dụng Model MBean cache.
- Ứng dụng chỉ muốn metrics được collector thu thập để đưa vào Prometheus/OpenTelemetry.
- Cần cache nghiệp vụ, Redis TTL hoặc Spring Cache abstraction.
- Cần lưu trạng thái job, giao dịch, checkpoint hoặc dữ liệu quan trọng với cơ chế durability nghiêm ngặt.
- Hệ thống dùng container ephemeral, không có persistence backend tương thích.
- Không có client hay implementation nào đọc hoặc diễn giải các descriptor field này.

Việc một annotation vẫn tồn tại trong API không có nghĩa nó là giải pháp tốt nhất cho mọi bài toán hiện đại.

## 12. So sánh với Spring Cache và metrics systems

| Nhu cầu | Công cụ phù hợp | Vì sao |
| --- | --- | --- |
| Hạn chế đọc lại attribute qua Model MBean | \`currencyTimeLimit\` nếu implementation hỗ trợ | Metadata JMX chuẩn, hành vi phụ thuộc Model MBean. |
| Cache dữ liệu service/DAO | Spring Cache, Caffeine, Redis | Quản lý key/TTL/invalidation trong tầng nghiệp vụ. |
| Thu thập chỉ số thời gian thực/gần thực | Micrometer, OpenTelemetry, metrics collector | Metrics có nhãn, timestamp, aggregation và pipeline. |
| Lưu checkpoint của batch job | Database hoặc storage bền vững | Có transaction, recovery và schema rõ ràng. |
| Lưu state Model MBean legacy | \`persistPolicy\` + implementation hỗ trợ | Tương thích engine quản trị có semantics persistence tương ứng. |
| Tham khảo cấu hình MBean | JMX \`MBeanInfo\` / \`Descriptor\` | Đọc metadata quản trị runtime. |

Một thuộc tính JMX đọc \`getCacheHitRate()\` vẫn có thể lấy dữ liệu từ Caffeine/Redis thông qua service riêng; JMX metadata không chi phối TTL của cache đó.

## 13. Rủi ro khi lạm dụng currencyTimeLimit

### 13.1. Dữ liệu cũ gây quyết định sai

Nếu \`currencyTimeLimit=0\` dẫn tới cache không hết hạn, một trạng thái \`Healthy=true\` có thể giữ nguyên sau khi hệ thống đã gặp lỗi, tùy Model MBean behavior. Do đó status phục vụ điều khiển hoặc incident response thường phải có freshness được kiểm soát chặt.

### 13.2. Phụ thuộc vào cache nhưng không ghi timestamp

Một client JMX có thể thấy giá trị nhưng không biết thời điểm nó được tính. Hãy xem xét công bố thêm \`LastSampleEpochMillis\` hoặc \`LastUpdatedAt\` để phân biệt dữ liệu cũ với dữ liệu mới.

### 13.3. Cache ở nhiều tầng

Có thể tồn tại cache trong service, trong Model MBean và trong collector. TTL cộng dồn có thể làm dashboard trễ hơn mong đợi. Không nên tối ưu bằng cách thêm \`currencyTimeLimit\` mà không kiểm tra toàn bộ đường dữ liệu.

### 13.4. Khi getter có side effect

Getter JMX cần hạn chế side effect. Nếu getter có tác dụng làm mới dữ liệu hoặc thay đổi state, việc Model MBean cache kết quả có thể thay đổi tần suất thực hiện code, gây hành vi khó đoán.

## 14. Rủi ro khi lạm dụng persistence metadata

- **Nhầm lẫn về durability:** metadata không bảo đảm đã có file hoặc transaction.
- **Tác động tài nguyên:** một engine persistence thực sự có thể gây I/O, lock hoặc tăng số lần ghi.
- **Đường dẫn không portable:** \`persistLocation\` phụ thuộc OS, container image và volume mapping.
- **Quyền filesystem:** nếu có cơ chế ghi thật, phải bảo vệ file và tài khoản tiến trình.
- **Lộ dữ liệu:** không persist secret hoặc dữ liệu người dùng qua một cơ chế JMX chưa được kiểm soát.
- **Recovery không rõ:** khả năng đọc lại state sau restart phải được kiểm thử độc lập, không chỉ xem field descriptor.
- **Tính nhất quán:** persistence của state liên quan nhiều thành phần cần có ranh giới transaction cụ thể.

Một điểm thực hành: nếu không có chủ thể thực sự xử lý \`persistPolicy\`, thêm field này có thể gây hiểu lầm cho người đọc và công cụ vận hành hơn là mang lại lợi ích.

## 15. Kiểm tra cache semantics bằng thử nghiệm có kiểm soát

Có thể tạo một bean có bộ đếm số lần getter được gọi:

\`\`\`java
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example:type=Counter,name=GetterProbe"
)
public class GetterProbe {

    private final AtomicInteger invocations =
        new AtomicInteger();

    @ManagedAttribute(currencyTimeLimit = 5)
    public int getValue() {
        return invocations.incrementAndGet();
    }
}
\`\`\`

Sau khi exporter đăng ký MBean, client đọc qua \`MBeanServer\`:

\`\`\`java
ObjectName name = new ObjectName(
    "com.example:type=Counter,name=GetterProbe"
);

Object first = server.getAttribute(name, "Value");
Object second = server.getAttribute(name, "Value");

System.out.println(first);
System.out.println(second);
\`\`\`

Nếu Model MBean thực thi caching theo descriptor, hai giá trị đọc sát nhau có thể giống nhau. Nếu mỗi lần getter đều được gọi, các giá trị có thể khác. Khi làm thí nghiệm nên:

1. Đọc descriptor của attribute \`Value\` để biết metadata thật.
2. Đọc hai lần trong khoảng ngắn hơn TTL.
3. Chờ qua TTL rồi đọc lại.
4. Quan sát số lần getter thực thi và thời điểm cập nhật.
5. Đảm bảo không có tầng cache khác ảnh hưởng phép đo.

Đây là thí nghiệm xác minh behavior của môi trường đang dùng, không thay thế Javadoc/đặc tả Model MBean.

## 16. Hướng dẫn quyết định thực tế

Khi gặp \`currencyTimeLimit\` hoặc \`persistPolicy\` trong một dự án Spring Framework, hãy hỏi:

1. **MBean là loại nào?** Standard MBean, MXBean, Dynamic MBean hay Model MBean?
2. **Metadata đến từ đâu?** Annotation Spring, XML, custom assembler hay mã tự tạo \`Descriptor\`?
3. **Implementation nào tiêu thụ metadata?** Model MBean implementation của JVM, Spring exporter hay một custom agent?
4. **Mục tiêu thực tế?** Giảm tải getter, truyền thông tin về độ mới, hay lưu trạng thái?
5. **Client nào quan tâm?** JConsole, JMX collector, custom JMX client hoặc tool enterprise?
6. **Đã kiểm tra hành vi chưa?** Đọc MBeanInfo/descriptor, thử cache hoặc persistence trong môi trường lab.
7. **Có giải pháp rõ ràng hơn?** Cache service, metrics collector, configuration management hay database.
8. **Có nguy cơ mất dữ liệu hoặc trễ thông tin không?** Xác định SLA cho freshness và durability.

Nếu metadata không có bên tiêu thụ, tốt hơn nên giữ cấu hình tối giản và mô tả trực tiếp chính sách cache/persistence ở lớp thực sự triển khai.

## 17. Bài tập thực hành

### Bài tập 1 — Kiểm tra resource descriptor

Tạo bean \`@ManagedResource(currencyTimeLimit=5)\`, export qua \`MBeanExporter\` với \`MetadataMBeanInfoAssembler\`, đọc \`MBeanInfo.getDescriptor()\` và tìm field \`currencyTimeLimit\`.

**Mục tiêu:** nhận biết vị trí metadata được tạo.

### Bài tập 2 — Attribute-level TTL

Tạo getter \`getValue()\` tăng bộ đếm, đặt \`@ManagedAttribute(currencyTimeLimit=5)\`. Đọc qua MBeanServer nhiều lần trong 5 giây và sau 5 giây. Ghi nhận behavior của implementation thực tế.

**Mục tiêu:** hiểu rằng annotation và runtime behavior cần kiểm chứng cùng nhau.

### Bài tập 3 — So sánh Standard MBean và Model MBean

Tạo một Standard MBean với getter có cùng ý nghĩa, không dùng metadata assembler của Spring; so sánh \`MBeanInfo\` và số lần getter chạy khi client gọi lặp lại.

**Mục tiêu:** không áp dụng \`currencyTimeLimit\` cho mọi loại MBean một cách mặc định.

### Bài tập 4 — Persistence metadata

Khai báo \`persistPolicy\`, \`persistPeriod\`, \`persistName\` và \`persistLocation\` trong môi trường phù hợp. Đọc descriptor rồi kiểm tra có file hoặc storage thật được tạo không. Nếu không, xác định implementation nào cần có để persistence diễn ra.

**Mục tiêu:** phân biệt metadata với engine lưu trữ.

### Bài tập 5 — Thiết kế ứng dụng thực tế

Một ứng dụng có các chỉ số \`QueueDepth\`, \`LastErrorAt\`, \`DatabaseHealthy\` và checkpoint nhập dữ liệu. Hãy chọn nơi áp dụng cache/TTL, nơi lưu checkpoint và cách xuất qua JMX.

**Gợi ý:** chỉ số và trạng thái cần freshness rõ ràng; checkpoint phải lưu bằng storage bền vững; JMX có thể chỉ là cổng đọc.

## 18. Câu hỏi ôn tập

**1. \`currencyTimeLimit\` có đơn vị gì trong Model MBean descriptor?** Thường là giây, theo semantics Model MBean.

**2. \`currencyTimeLimit=0\` có nghĩa gì?** Trong Model MBean semantics thông dụng, giá trị cache có thể được giữ vô hạn theo thời gian.

**3. \`currencyTimeLimit=-1\` có nghĩa gì?** Chỉ định không cache giá trị theo quy tắc Model MBean.

**4. Annotation này có tự cấu hình Spring Cache không?** Không. Nó thuộc mô hình metadata JMX.

**5. \`persistPolicy\` tương đương \`@Transactional\` không?** Không. Đây là metadata về chính sách persistence của Model MBean, không phải transaction nghiệp vụ.

**6. \`persistPeriod\` tự tạo task \`@Scheduled\` không?** Không. Việc có hành vi timer phụ thuộc Model MBean implementation.

**7. Làm thế nào biết metadata thực sự được xuất?** Đọc \`MBeanInfo\`, \`ModelMBeanInfo\` và các descriptor của resource/attribute/operation trên MBeanServer.

**8. Khi nào nên dùng persistence metadata?** Khi ứng dụng có một Model MBean hoặc management framework thực sự hỗ trợ và tiêu thụ nó.

**9. Khi nào dùng database thay vì JMX persistence?** Khi cần durability, recovery, transaction hoặc dữ liệu nghiệp vụ quan trọng.

**10. Nếu JConsole hiển thị attribute nhưng giá trị chậm cập nhật, cần kiểm tra gì?** Nguồn dữ liệu, cache ở service, Model MBean currencyTimeLimit, collector/client polling và timestamp của snapshot.

## 19. Tổng kết

\`currencyTimeLimit\` và persistence metadata trong \`@ManagedResource\` là những dấu vết có chủ đích của **JMX Model MBean descriptor model**. \`currencyTimeLimit\` mô tả chính sách độ mới/cache trong ngữ cảnh Model MBean; \`persistPolicy\`, \`persistPeriod\`, \`persistName\` và \`persistLocation\` mô tả ý định lưu trữ trạng thái khi implementation hỗ trợ.

Chúng vẫn có giá trị trong các hệ thống JMX/Model MBean cần metadata chuẩn hoặc tương thích legacy. Với ứng dụng Spring hiện đại, cần kiểm chứng runtime descriptor và hành vi trước khi phụ thuộc vào các field này; caching nghiệp vụ, observability và lưu trạng thái bền vững thường do những cơ chế chuyên trách đảm nhiệm.

## Tài liệu tham khảo

- Spring Framework Javadoc — \`ManagedResource\` annotation: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedResource.html
- Spring Framework Javadoc — \`ManagedAttribute\` annotation: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedAttribute.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Java SE 21 — \`ModelMBeanInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/modelmbean/ModelMBeanInfo.html
- Java SE 21 — \`Descriptor\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/Descriptor.html
- Java SE 21 — \`RequiredModelMBean\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/modelmbean/RequiredModelMBean.html