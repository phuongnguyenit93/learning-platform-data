# AutodetectCapableMBeanInfoAssembler và cơ chế vote trong Spring JMX

## 1. Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích **autodetection** trong Spring JMX: exporter tự tìm những Spring bean phù hợp để đăng ký thành JMX MBean thay vì chỉ nhận danh sách tường minh.
- Hiểu vai trò của giao diện **\`AutodetectCapableMBeanInfoAssembler\`** và phương thức **\`includeBean(Class<?> beanClass, String beanName)\`** như một phép đánh giá đủ điều kiện (*vote*) khi \`MBeanExporter\` quét các bean.
- Phân biệt việc **một bean được chọn để export** với việc **những attribute/operation nào của bean được công bố**.
- Xác định quan hệ giữa \`MBeanExporter\`, \`MBeanInfoAssembler\`, \`MetadataMBeanInfoAssembler\`, \`AnnotationJmxAttributeSource\` và các cơ chế phát hiện MBean chuẩn/MXBean.
- Cấu hình autodetect có kiểm soát, biết khi nào cần chọn bean bằng danh sách tường minh thay vì quét toàn bộ \`ApplicationContext\`.
- Viết ví dụ cấu hình và phép kiểm tra runtime cho sự lựa chọn bean, \`ObjectName\`, \`MBeanInfo\` và phần API được phép lộ.
- Nhận diện bẫy do proxy, tên bean, interface quản trị, phạm vi quét, đăng ký trùng tên và ranh giới bảo mật.
- Biết cách giới hạn và chẩn đoán phép vote để JMX exporter không vô tình công bố bean nội bộ.

## 2. Autodetection là gì trong Spring JMX?

Một ứng dụng Spring có thể chứa hàng trăm bean: service, repository, listener, scheduler, HTTP controller, cache và adapter quản trị. Việc đăng ký tất cả bean thành MBean là không cần thiết và có thể tạo rủi ro. Spring \`MBeanExporter\` hỗ trợ một số cách xác định bean nào sẽ được export:

1. **Khai báo tường minh** các bean cần export bằng map, danh sách hoặc cấu hình thích hợp.
2. **Tự phát hiện (autodetect)** các bean đủ điều kiện theo cơ chế exporter và/hoặc thông tin từ metadata assembler.
3. **Kết hợp** cấu hình tường minh và các bean được exporter phát hiện theo policy phù hợp.

Điểm cốt lõi của autodetection: exporter cần quyết định **bean nào là đối tượng quản trị** trước khi dựng metadata JMX và đăng ký với \`MBeanServer\`.

\`\`\`text
Spring ApplicationContext
  |-- paymentService
  |-- orderRepository
  |-- importWorker
  |-- cacheManagement
  |-- healthController
            |
            v
       MBeanExporter
            |
            | Danh sách tường minh?
            | Chế độ autodetect?
            | Assembler có khả năng "vote"?
            v
    Candidate selection
       /          \
     YES           NO
      |             |
      v             +--> Không xuất bean này
MBeanInfoAssembler
      |
      v
Naming strategy -> ObjectName
      |
      v
MBeanServer.registerMBean(...)
      |
      v
JConsole / JMX client
\`\`\`

Không được hiểu “autodetect” là mọi bean đều có thể được JMX client truy cập. Một bean chỉ xuất hiện sau khi exporter chọn, tạo metadata/hợp đồng phù hợp và đăng ký thành công.

## 3. AutodetectCapableMBeanInfoAssembler là gì?

Giao diện Spring:

\`\`\`java
org.springframework.jmx.export.assembler.AutodetectCapableMBeanInfoAssembler
\`\`\`

mở rộng ý tưởng của \`MBeanInfoAssembler\`: ngoài việc dựng thông tin quản trị cho bean, assembler có thể **đưa ra ý kiến** một bean có nên được chọn trong luồng autodetection hay không.

Phương thức quan trọng:

\`\`\`java
boolean includeBean(Class<?> beanClass, String beanName);
\`\`\`

- **\`beanClass\`**: kiểu class mà quá trình đánh giá đang xét.
- **\`beanName\`**: tên bean trong Spring container.
- **\`true\`**: assembler chấp nhận bean này như một candidate có thể autodetect.
- **\`false\`**: assembler không chọn bean này trong quá trình vote tương ứng.

Ví dụ một bộ lọc theo class/name:

\`\`\`java
import org.springframework.jmx.export.assembler.AutodetectCapableMBeanInfoAssembler;

boolean eligible = assembler.includeBean(
    CacheManagement.class,
    "cacheManagement"
);
\`\`\`

Đây chỉ là cách minh họa phương thức. Việc gọi \`includeBean\` thủ công không đăng ký bean; exporter phải chạy quá trình phát hiện và thực hiện \`registerMBean\`.

**Quan trọng:** giá trị \`true\` thể hiện một *vote về eligibility*, không phải bảo đảm \`ObjectName\` sẽ đăng ký thành công. Các điều kiện khác như trùng tên, naming strategy, MBeanServer hoặc vòng đời context vẫn có thể khiến export thất bại hay bị bỏ qua.

## 4. Vì sao gọi là vote?

Trong ngữ cảnh này, “vote” có nghĩa assembler có khả năng quyết định một candidate có phù hợp với **chiến lược xây dựng metadata quản trị** mà nó áp dụng hay không. Một assembler dựa vào annotation có thể chọn bean có marker quản trị; một assembler khác có thể không cung cấp khả năng autodetect hoặc có quy tắc riêng.

Đây không phải bỏ phiếu theo số đông của nhiều service, không phải hệ thống phân quyền của Java SecurityManager và cũng không phải thuật toán scheduler. Thường chỉ có **một assembler được MBeanExporter cấu hình** đang quyết định sự phù hợp của bean theo luồng đã chọn.

\`\`\`text
Candidate bean
     |
     v
AutodetectCapableMBeanInfoAssembler?
     |
    YES
     |
     v
includeBean(beanClass, beanName)
     |
  +--+---+
  |      |
 true   false
  |      |
  v      v
chấp    bỏ qua
nhận    candidate
  |
  v
chuẩn bị metadata & ObjectName
  |
  v
thử đăng ký
\`\`\`

Trong thực tế, \`MBeanExporter\` còn có cơ chế autodetection đối với MBean tuân thủ chuẩn Java/JMX. Vì vậy không nên mô tả mọi candidate đều phải đi qua một phép vote của assembler. Hãy phân biệt **autodetect các MBean chuẩn** với **autodetect dựa trên assembler**.

## 5. Hai nhóm cơ chế phát hiện cần phân biệt

### 5.1. MBean theo quy tắc JMX sẵn có

Một class thực thi interface \`CacheMonitorMBean\` theo convention Standard MBean hoặc interface MXBean có thể được nhận diện là JMX-compliant bean theo logic phát hiện của exporter, tùy mode. Trong trường hợp này, metadata của MBean có thể đi theo hợp đồng interface quản trị chuẩn, không phụ thuộc annotation \`@ManagedResource\`.

Ví dụ:

\`\`\`java
public interface QueueMonitorMBean {
    long getDepth();
}

public final class QueueMonitor implements QueueMonitorMBean {
    @Override
    public long getDepth() {
        return 12L;
    }
}
\`\`\`

Nếu được chọn và đăng ký, MBean công bố \`Depth\`, không tự động công bố toàn bộ public method của implementation.

### 5.2. Bean được chọn dựa vào assembler metadata

Một bean có annotation Spring:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example:type=Queue,name=Orders"
)
public final class QueueManagement {
    @ManagedAttribute
    public long getDepth() {
        return 12L;
    }
}
\`\`\`

Nếu exporter dùng \`MetadataMBeanInfoAssembler\` kết hợp \`AnnotationJmxAttributeSource\`, assembler có khả năng đánh giá annotation để lựa chọn bean khi chế độ autodetect phù hợp được bật. Sau khi chọn, nó sử dụng metadata đó để dựng MBean interface.

Một class có \`@ManagedResource\` nhưng không nằm trong phạm vi exporter quét, hoặc exporter không sử dụng metadata assembler phù hợp, có thể **không** được đăng ký.

## 6. MBeanExporter, assembler và naming strategy: ba vai trò tách biệt

| Thành phần | Câu hỏi trả lời |
| --- | --- |
| \`MBeanExporter\` | Bean nào sẽ được đưa vào JMX, khi nào đăng ký và hủy đăng ký? |
| \`AutodetectCapableMBeanInfoAssembler\` | Bean này có đủ điều kiện cho chiến lược autodetect theo assembler không? |
| \`MBeanInfoAssembler\` | Nếu đã chọn bean, những attributes/operations/metadata nào được công bố? |
| \`JmxAttributeSource\` | Metadata nguồn của bean/method là gì, ví dụ annotation Spring? |
| \`ObjectNamingStrategy\` | \`ObjectName\` của bean sẽ là gì? |
| \`MBeanServer\` | Registry nào thực sự nhận MBean và phục vụ JMX clients? |

Những bước này có liên quan nhưng không thay thế nhau:

- Vote true **không** bảo đảm tên MBean hợp lệ.
- Tên MBean hợp lệ **không** bảo đảm registration thành công nếu đã bị sử dụng.
- Registration thành công **không** bảo đảm thuộc tính/operation khớp ý định nếu assembler sai.
- Cấu hình đúng assembler **không** thay thế bảo vệ remote JMX connector và authorization.

### 6.1. Tại sao phải kiểm tra MBeanInfo sau export?

Metadata runtime là thứ client nhìn thấy. Khi đã đăng ký:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(objectName);
\`\`\`

Hãy so sánh danh sách attributes/operations với hợp đồng được phép, đặc biệt những method nội bộ phải không bị công bố. Đây là phép kiểm tra hiệu lực của cấu hình, không phải tác động của một vote riêng lẻ.

## 7. Các chế độ autodetect của MBeanExporter

Spring \`MBeanExporter\` hỗ trợ các hằng số mode liên quan autodetection (tên có thể được dùng qua \`setAutodetectMode\` hoặc \`setAutodetectModeName\` tùy API phiên bản):

| Mode | Ý nghĩa tổng quát |
| --- | --- |
| \`AUTODETECT_NONE\` | Không chạy autodetection; chỉ dùng những bean được cấu hình tường minh. |
| \`AUTODETECT_MBEAN\` | Phát hiện bean có hợp đồng JMX-compliant MBean theo cơ chế exporter. |
| \`AUTODETECT_ASSEMBLER\` | Phát hiện candidate dựa trên khả năng vote của assembler. |
| \`AUTODETECT_ALL\` | Kết hợp những nhóm autodetection được hỗ trợ. |

Ví dụ:

\`\`\`java
MBeanExporter exporter = new MBeanExporter();
exporter.setAutodetectMode(
    MBeanExporter.AUTODETECT_ASSEMBLER
);
\`\`\`

Khi chọn \`AUTODETECT_ASSEMBLER\`, cần cấu hình một assembler thực sự implements \`AutodetectCapableMBeanInfoAssembler\`. Nếu không, cơ chế autodetect theo assembler không thể quyết định candidate như dự kiến.

Các mode có thể có mặc định khác nhau tùy Spring version/configuration. Không nên giả định Spring Boot tự bật mọi mode cho mọi bean; luôn xem cấu hình exporter đang sử dụng.

## 8. MetadataMBeanInfoAssembler và AnnotationJmxAttributeSource

Spring có hỗ trợ metadata annotation để xác định bề mặt JMX:

- \`@ManagedResource\`: đánh dấu class như một JMX-managed resource.
- \`@ManagedAttribute\`: mô tả getter/setter được công bố.
- \`@ManagedOperation\`: mô tả operation.
- \`@ManagedOperationParameter\`: mô tả tham số operation.

\`AnnotationJmxAttributeSource\` đọc metadata từ các annotation này. \`MetadataMBeanInfoAssembler\` dùng nguồn metadata để dựng MBeanInfo và có khả năng vote cho autodetection.

\`\`\`text
@ManagedResource class
        |
        v
AnnotationJmxAttributeSource
        |
        v
MetadataMBeanInfoAssembler
        |
        +--> includeBean(...) (eligibility)
        |
        +--> metadata attributes/operations
        |
        v
MBeanExporter + naming strategy
        |
        v
MBeanServer.registerMBean
\`\`\`

Điều quan trọng là **lớp annotation được đọc bởi đúng attribute source**. Nếu cấu hình assembler không gắn source, hoặc sử dụng source khác, kết quả vote và metadata có thể không khớp với annotation trên class.

## 9. Ví dụ Spring Java configuration: autodetect bằng assembler

### 9.1. Bean có annotation quản trị

\`\`\`java
package example.springjmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example:type=Cache,name=Products",
    description = "Product cache management"
)
public class ProductCacheManagement {

    @ManagedAttribute(description = "Number of cache entries")
    public long getEntryCount() {
        return 100L;
    }

    @ManagedOperation(description = "Request safe cache refresh")
    public void requestRefresh() {
        // Chuyển yêu cầu tới service quản lý cache.
    }

    // Không có @ManagedOperation:
    public void deleteAllInternalCacheFiles() {
        // Không nên xuất method nội bộ.
    }
}
\`\`\`

### 9.2. Bean thông thường không có annotation

\`\`\`java
package example.springjmx;

import org.springframework.stereotype.Service;

@Service
public class BillingService {
    public void createInvoice() {
        // Logic nghiệp vụ, không cần công bố qua JMX.
    }
}
\`\`\`

### 9.3. Cấu hình MBeanExporter

\`\`\`java
package example.springjmx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxAutodetectConfiguration {

    @Bean
    public MBeanExporter jmxExporter() {
        AnnotationJmxAttributeSource source =
            new AnnotationJmxAttributeSource();

        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);

        MetadataNamingStrategy naming =
            new MetadataNamingStrategy();
        naming.setAttributeSource(source);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        exporter.setAutodetectMode(
            MBeanExporter.AUTODETECT_ASSEMBLER
        );

        return exporter;
    }
}
\`\`\`

Nếu \`ProductCacheManagement\` được Spring container tạo và nằm trong phạm vi exporter quét, assembler có thể vote cho bean theo metadata \`@ManagedResource\`. \`BillingService\` không có marker quản trị nên không nên được chọn theo cơ chế annotation-based metadata.

**Quan trọng về Spring version:** cách phát hiện, tên hằng số và các property cụ thể cần khớp Javadoc của phiên bản đang triển khai. Trong Spring Boot, auto-configured JMX exporter có thể tồn tại; không tạo thêm exporter đè/đăng ký trùng \`ObjectName\` nếu chưa kiểm soát cấu hình.

## 10. Cơ chế vote qua includeBean

Trong Java, kiểu một assembler có khả năng autodetect được xét qua giao diện \`AutodetectCapableMBeanInfoAssembler\`:

\`\`\`java
import org.springframework.jmx.export.assembler.AutodetectCapableMBeanInfoAssembler;

public void inspectVote(
        AutodetectCapableMBeanInfoAssembler assembler,
        Class<?> type,
        String beanName) {

    boolean included = assembler.includeBean(type, beanName);

    System.out.printf(
        "JMX autodetect vote: bean=%s, type=%s, include=%s%n",
        beanName, type.getName(), included
    );
}
\`\`\`

Đoạn trên chỉ là tiện ích chẩn đoán, không thay đổi registry. Trong quá trình exporter thực tế, bean class có thể chịu ảnh hưởng proxy, factory bean và cách Spring xác định target type. Vì thế một phép gọi \`includeBean\` bằng class tưởng tượng không chắc tái hiện chính xác toàn bộ quá trình exporter chạy.

### 10.1. Điều kiện vote true/false cần hiểu

Với metadata assembler:

- Nếu class mang metadata quản trị thích hợp từ \`JmxAttributeSource\`, assembler có cơ sở để chọn.
- Nếu bean không mang metadata tương ứng, assembler có thể không chọn.
- Nếu annotation nằm trên interface hoặc target class nhưng bean là proxy, khả năng phát hiện còn phụ thuộc cơ chế introspection và phiên bản Spring.
- Nếu bean name không hợp lệ theo naming strategy, vote vẫn chưa phải bước đăng ký.

Không dùng vote làm hệ thống authorization. Một bean được chọn bởi metadata vẫn cần kiểm tra xem những method thực sự được công bố có an toàn hay không.

## 11. Ví dụ custom assembler có khả năng vote

Để minh họa cách một assembler triển khai bộ lọc, có thể mở rộng một assembler sẵn có và tùy biến lựa chọn candidate theo prefix bean name. Cần biết rõ rằng đây là chính sách phát hiện **ứng dụng tự chọn**, không phải mặc định của Spring.

\`\`\`java
package example.springjmx;

import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;

public class RestrictedMetadataAssembler
        extends MetadataMBeanInfoAssembler {

    @Override
    public boolean includeBean(Class<?> beanClass, String beanName) {
        return beanName.startsWith("management")
            && super.includeBean(beanClass, beanName);
    }
}
\`\`\`

Cấu hình:

\`\`\`java
RestrictedMetadataAssembler assembler =
    new RestrictedMetadataAssembler();
assembler.setAttributeSource(source);

exporter.setAssembler(assembler);
exporter.setAutodetectMode(
    MBeanExporter.AUTODETECT_ASSEMBLER
);
\`\`\`

Ví dụ yêu cầu cả hai điều kiện: tên bean bắt đầu bằng \`management\`, đồng thời metadata assembler gốc chấp nhận class. Điều này hữu ích khi team muốn chỉ export những bean trong namespace quản trị.

Tuy nhiên không nên xem tiền tố bean name là ranh giới bảo mật mạnh. Tên bean có thể đổi do refactor; quyền truy cập JMX connector và thiết kế interface tối thiểu mới là các lớp bảo vệ thiết yếu.

## 12. Sự khác biệt giữa vote và assembler output

Một bean có thể vượt qua \`includeBean\` nhưng interface quản trị cuối cùng vẫn phụ thuộc \`MBeanInfoAssembler\`.

Ví dụ:

\`\`\`java
@ManagedResource(objectName = "com.example:type=Worker,name=Importer")
public class ImportWorkerManagement {

    @ManagedAttribute
    public long getProcessedCount() {
        return 100L;
    }

    public String getSecretToken() {
        return "sensitive";
    }
}
\`\`\`

Nếu metadata assembler chỉ xuất những method được annotate, bạn mong đợi attribute \`ProcessedCount\` chứ không phải \`SecretToken\`. Nhưng kết quả chỉ được khẳng định khi đọc \`MBeanInfo\` thực tế sau export.

Hãy phân biệt:

\`\`\`text
includeBean(...) == true
    -> Candidate đủ điều kiện để thử export.

getMBeanInfo(...) sau register
    -> Bề mặt quản trị thực sự mà JMX client nhìn thấy.
\`\`\`

Một thiết kế an toàn kiểm soát **cả hai**: chọn đúng bean và chọn đúng API được công bố.

## 13. Kiểm tra các MBean được export

Sau khi Spring context khởi động:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName cacheName = new ObjectName(
    "com.example:type=Cache,name=Products"
);

System.out.println(
    "Cache management registered: "
        + server.isRegistered(cacheName)
);

if (server.isRegistered(cacheName)) {
    MBeanInfo info = server.getMBeanInfo(cacheName);

    System.out.println("MBean: " + info.getClassName());
    for (var attr : info.getAttributes()) {
        System.out.println("attribute: " + attr.getName());
    }
    for (var op : info.getOperations()) {
        System.out.println("operation: " + op.getName());
    }
}
\`\`\`

Kỳ vọng của ví dụ:

- \`ProductCacheManagement\` được đăng ký tại \`com.example:type=Cache,name=Products\` khi exporter và assembler cấu hình đúng.
- \`EntryCount\` xuất hiện như thuộc tính.
- \`requestRefresh\` xuất hiện như operation.
- \`deleteAllInternalCacheFiles\` không nên xuất hiện.
- \`BillingService\` không có ObjectName quản trị tương ứng do assembler vote không chọn.

Nếu \`isRegistered\` trả false, cần kiểm tra exporter đang dùng MBeanServer nào. Một exporter có thể được cấu hình với server riêng thay vì platform server.

## 14. Kiểm tra vote bằng unit test

Có thể kiểm tra logic \`includeBean\` của metadata assembler mà không khởi chạy một JMX connector remote.

Ví dụ kiểm tra class có và không có \`@ManagedResource\`:

\`\`\`java
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;

public class VoteDemo {

    public static void main(String[] args) {
        AnnotationJmxAttributeSource source =
            new AnnotationJmxAttributeSource();

        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);

        boolean management = assembler.includeBean(
            ProductCacheManagement.class,
            "productCacheManagement"
        );

        boolean service = assembler.includeBean(
            BillingService.class,
            "billingService"
        );

        System.out.println(
            "Management eligible: " + management
        );
        System.out.println(
            "Business service eligible: " + service
        );
    }
}
\`\`\`

Đây là minh họa unit-level của vote. Kết quả mong đợi với metadata source phù hợp là bean có \`@ManagedResource\` được chấp nhận, bean thường không được chấp nhận. Khi đưa vào test dự án, dùng assertion theo semantics của Spring version thực tế.

**Không đánh đồng unit vote test với integration test exporter**: unit test chỉ kiểm tra quyết định eligibility của assembler, không chứng minh \`ObjectName\`, MBeanServer, registration policy hoặc exposed API.

## 15. Kiểm tra integration: exporter và MBeanServer

Một phép kiểm tra end-to-end cần khởi tạo \`ApplicationContext\` chứa bean và exporter, rồi đọc JMX registry.

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class AutodetectIntegrationDemo {

    public static void main(String[] args) throws Exception {
        ObjectName name = new ObjectName(
            "com.example:type=Cache,name=Products"
        );

        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        try (AnnotationConfigApplicationContext ctx =
                new AnnotationConfigApplicationContext()) {

            ctx.register(JmxAutodetectConfiguration.class);
            ctx.register(ProductCacheManagement.class);
            ctx.register(BillingService.class);
            ctx.refresh();

            if (!server.isRegistered(name)) {
                throw new AssertionError(
                    "Expected management MBean was not autodetected"
                );
            }

            MBeanInfo info = server.getMBeanInfo(name);
            boolean hasExpectedAttribute = false;

            for (var attribute : info.getAttributes()) {
                if ("EntryCount".equals(attribute.getName())) {
                    hasExpectedAttribute = true;
                }
                if ("SecretToken".equals(attribute.getName())) {
                    throw new AssertionError(
                        "Sensitive attribute unexpectedly exported"
                    );
                }
            }

            if (!hasExpectedAttribute) {
                throw new AssertionError(
                    "Missing expected EntryCount attribute"
                );
            }
        }
    }
}
\`\`\`

Trong integration test, có thể thêm negative assertion cho \`deleteAllInternalCacheFiles\`. Khi Spring context đóng bình thường, exporter thường hủy đăng ký những MBean do nó quản lý.

Lưu ý: khi đăng ký class bằng \`ctx.register(...)\`, Spring cần nhận diện annotation/configuration theo bản Spring đang chạy; trong ứng dụng lớn cũng cần loại bỏ exporter mặc định trùng để test có ownership rõ ràng. Kiểm tra trong môi trường cô lập, không làm thay đổi MBean production.

## 16. Trường hợp proxy và target class

Một số bean Spring được proxy bởi AOP hoặc transaction interceptor. Khi đó:

\`\`\`text
Bean name: productCacheManagement
Declared class: ProductCacheManagement
Runtime object: proxy class
Target class: ProductCacheManagement
\`\`\`

Annotation có thể nằm trên target class, trong khi class mà exporter hoặc assembler xét đến lại là proxy. Điều này ảnh hưởng cách phản xạ tìm \`@ManagedResource\` và các metadata phương thức.

Các hướng xử lý:

1. Xác định exporter đang đánh giá target class hay proxy class.
2. Tránh phụ thuộc vào tên class proxy được tạo động để đặt ObjectName.
3. Sử dụng Spring/JMX metadata source hiểu target class và annotation theo cơ chế hỗ trợ.
4. Nếu phát hiện không ổn định, xuất một **management adapter riêng** không bị AOP proxy hoặc đăng ký tường minh.
5. Xác minh \`includeBean\` bằng kiểu thực tế mà exporter dùng, rồi kiểm tra runtime \`MBeanInfo\`.

Không khẳng định rằng cứ dùng \`@ManagedResource\` trên class gốc thì mọi cấu hình proxy đều tự động vote true. Cần kiểm chứng theo phiên bản và kiểu proxy đang dùng.

## 17. Registration policy và vòng đời

Một candidate được chọn còn cần đăng ký với \`ObjectName\` chưa bị chiếm, hoặc tuân thủ chính sách đăng ký trùng của exporter.

Một số policy phổ biến:

- \`FAIL_ON_EXISTING\`: từ chối khi đã có MBean cùng ObjectName.
- \`IGNORE_EXISTING\`: bỏ qua candidate nếu tên đã tồn tại.
- \`REPLACE_EXISTING\`: thay thế theo chính sách nếu được cấu hình.

Ví dụ:

\`\`\`java
import org.springframework.jmx.support.RegistrationPolicy;

exporter.setRegistrationPolicy(
    RegistrationPolicy.FAIL_ON_EXISTING
);
\`\`\`

Nếu vote true nhưng ObjectName đã tồn tại, việc export có thể thất bại hoặc bị bỏ qua theo policy. Không được suy ra rằng MBean xuất hiện trong JConsole là object mới vừa được exporter đăng ký.

Khi Spring context đóng, exporter thường hủy các MBean mà nó sở hữu. Nếu bean được đăng ký thủ công bởi thành phần khác, lifecycle của nó có thể khác.

## 18. Rủi ro khi autodetect quá rộng

Autodetection có thể tiết kiệm cấu hình, nhưng đồng thời tạo nguy cơ mở rộng bề mặt quản trị không mong muốn.

Ví dụ:

- Một bean mới được annotate nhầm \`@ManagedResource\`, tự động được exporter chọn.
- Một class kế thừa annotation hoặc metadata không chủ định dẫn tới vote true.
- Bean có phương thức quản trị quá mạnh được assembler công bố.
- Một package được scan rộng chứa service/debug adapter không dành cho production.
- Hai module xuất MBean với cùng ObjectName gây conflict.
- Người dùng JMX có quyền \`readwrite\` gọi operation nguy hiểm.

Khuyến nghị thực tế:

1. **Chỉ xuất những bean thật sự phục vụ vận hành.**
2. Khi số MBean ít, ưu tiên map tường minh để dễ review.
3. Với autodetect, dùng marker annotation và assembler đúng cơ chế.
4. Dùng \`ObjectName\` ổn định, namespace rõ ràng, không chứa PII/secret.
5. Kiểm tra allowlist của MBeanInfo sau export.
6. Đặt negative test cho những attribute/operation không được phép công bố.
7. Bảo vệ remote JMX connector bằng authentication, TLS và giới hạn mạng.
8. Không coi \`includeBean\` là authorization.

## 19. Chẩn đoán khi vote hoặc export không như mong đợi

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Bean \`@ManagedResource\` không xuất hiện | Autodetect mode không dùng assembler hoặc thiếu assembler phù hợp. | Kiểm tra \`setAutodetectMode\`, \`setAssembler\`, \`AnnotationJmxAttributeSource\`. |
| \`includeBean\` trả false | Annotation không được source nhận diện, class proxy hoặc class không có metadata. | Kiểm tra class thực tế và attribute source. |
| \`includeBean\` trả true nhưng MBean không đăng ký | Naming strategy, MBeanServer hoặc registration policy. | Kiểm tra ObjectName, log exporter, \`isRegistered\`. |
| Bean thường cũng xuất hiện | Autodetect mode kết hợp MBean JMX compliant hoặc exporter cấu hình rộng. | Kiểm tra mode, phạm vi và các interface MBean. |
| MBean có attribute/operation thừa | Assembler introspect quá rộng. | Dùng metadata hoặc interface allowlist; kiểm tra MBeanInfo. |
| MBean được xuất nhưng tên sai | Naming strategy, bean name, ObjectName không tường minh. | Kiểm tra \`ObjectName\` trong registry. |
| Xuất trùng tên | Nhiều exporter hoặc module cùng ObjectName. | Quy định ownership, xem registration policy. |
| App startup chậm | Quét nhiều bean, introspection nặng hoặc logic không phù hợp. | Giới hạn candidate hoặc xuất tường minh. |
| Spring Boot có lỗi trùng MBean | Auto-configured exporter và exporter riêng cùng xuất. | Chỉ giữ cấu hình phù hợp, tránh hai chủ thể đăng ký. |
| Chỉ lỗi khi bật AOP | Metadata không được tìm đúng qua proxy. | Xác minh target class/metadata, dùng adapter hoặc explicit mapping. |

## 20. Khi nào dùng autodetect, khi nào export tường minh?

| Hoàn cảnh | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Ứng dụng nhỏ có 2–3 MBean | \`setBeans(...)\` tường minh | Dễ kiểm soát, rõ ownership. |
| Nhiều module có marker annotation ổn định | \`AUTODETECT_ASSEMBLER\` | Giảm cấu hình lặp, dùng cùng metadata policy. |
| Chỉ có Standard MBean/MXBean có interface rõ | \`AUTODETECT_MBEAN\` nếu dự án mong muốn | Phát hiện theo hợp đồng JMX tuân chuẩn. |
| Ứng dụng có nguy cơ phơi bày API nội bộ | Export tường minh và contract tests | Giảm khả năng mở rộng surface ngoài chủ định. |
| Có AOP proxy phức tạp | Adapter quản trị hoặc đăng ký tường minh | Tránh phụ thuộc kiểu runtime/proxy name. |
| Nhiều Spring contexts/expor­ter | Quy định một owner cho ObjectName | Giảm xung đột và cleanup sai. |

Không có mode nào tự động bảo đảm bảo mật. Bề mặt công bố và quyền remote connector phải được kiểm soát riêng.

## 21. Bài tập thực hành

### Bài tập 1 — Kiểm tra vote trực tiếp

Tạo một class có \`@ManagedResource\` và một class không có annotation. Khởi tạo \`MetadataMBeanInfoAssembler\` cùng \`AnnotationJmxAttributeSource\`, gọi \`includeBean\` cho cả hai.

**Mục tiêu:** hiểu quyết định eligibility của assembler.

### Bài tập 2 — Chạy exporter ở chế độ assembler

Cấu hình \`AUTODETECT_ASSEMBLER\` và một bean quản trị có \`ObjectName\` rõ. Khởi động Spring context, kiểm tra \`MBeanServer.isRegistered(name)\`.

**Mục tiêu:** nối vote tới quá trình export thực tế.

### Bài tập 3 — So sánh mode

Dùng một Standard MBean, một bean \`@ManagedResource\` và một bean service thường. Thử \`AUTODETECT_MBEAN\`, \`AUTODETECT_ASSEMBLER\` và \`AUTODETECT_ALL\` trong các context cô lập.

**Mục tiêu:** nhận biết mode thay đổi tập candidate nào.

### Bài tập 4 — Bảo vệ bề mặt công bố

Thêm public method \`deleteAllInternalCacheFiles()\` không annotate. Viết phép kiểm tra rằng method không xuất hiện trong \`MBeanInfo.getOperations()\`.

**Mục tiêu:** phân biệt eligible bean với eligible API.

### Bài tập 5 — Proxy

Bọc bean bằng AOP proxy trong một ứng dụng lab. So sánh kết quả autodetect và metadata với/không proxy. Nếu không ổn định, thử adapter hoặc export tường minh.

**Mục tiêu:** hiểu tác động của runtime type và target class.

### Bài tập 6 — Registration conflict

Tạo hai exporter cố đăng ký cùng \`ObjectName\`; thử policy \`FAIL_ON_EXISTING\` và \`IGNORE_EXISTING\`. Quan sát callback, lỗi và kết quả \`isRegistered\`.

**Mục tiêu:** phân biệt vote true và đăng ký thành công.

## 22. Câu hỏi ôn tập

**1. \`AutodetectCapableMBeanInfoAssembler\` giải quyết vấn đề gì?** Nó cho phép metadata assembler đóng góp quyết định xem một bean có nên được autodetect để xuất JMX hay không.

**2. Phương thức vote là gì?** \`includeBean(Class<?> beanClass, String beanName)\`.

**3. Vote true có nghĩa MBean đã được đăng ký chưa?** Chưa. Exporter còn phải đặt tên, chuẩn bị metadata và gọi register.

**4. Vote true có nghĩa mọi public method được công bố không?** Không. Bề mặt API phụ thuộc assembler và hợp đồng MBean.

**5. \`AUTODETECT_ASSEMBLER\` khác \`AUTODETECT_MBEAN\` ra sao?** Một cơ chế dựa trên vote của assembler, cơ chế còn lại phát hiện các MBean phù hợp hợp đồng JMX.

**6. Metadata annotation có tác dụng gì?** Cung cấp thông tin quản trị để assembler lựa chọn bean và dựng attributes/operations.

**7. Vì sao proxy gây khó khăn?** Exporter có thể thấy class proxy khác target class chứa annotation, tùy cơ chế introspection.

**8. Vì sao \`includeBean\` không phải ranh giới bảo mật?** Nó chỉ chọn candidate; quyền truy cập và operation được công bố phải được kiểm soát riêng.

**9. Làm sao kiểm tra export đã đúng?** Xác minh \`ObjectName\`, \`isRegistered\` và \`MBeanInfo\` sau khi Spring context khởi tạo.

**10. Khi nào nên chọn export tường minh?** Khi số lượng MBean nhỏ, API nhạy cảm, có proxy phức tạp hoặc cần kiểm soát chính xác từng bean.

## 23. Tổng kết

**AutodetectCapableMBeanInfoAssembler** là cơ chế để Spring JMX exporter hỏi metadata assembler liệu một Spring bean có nên được chọn khi **autodetection** hay không. Phương thức \`includeBean(beanClass, beanName)\` đóng vai trò phép vote, thường dùng với assembler dựa trên metadata như \`MetadataMBeanInfoAssembler\`.

Vote chỉ quyết định **ứng viên có đủ điều kiện**, không tự đăng ký MBean và không cấp quyền cho JMX client. Để triển khai an toàn, cần phối hợp đúng autodetect mode, assembler, annotation source, naming strategy và registration policy; sau cùng kiểm tra MBeanInfo runtime để bảo đảm chỉ công bố những attribute/operation cần thiết.

## Tài liệu tham khảo

- Spring Framework Javadoc — \`AutodetectCapableMBeanInfoAssembler\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/assembler/AutodetectCapableMBeanInfoAssembler.html
- Spring Framework Javadoc — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Javadoc — \`MetadataMBeanInfoAssembler\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/assembler/MetadataMBeanInfoAssembler.html
- Spring Framework Javadoc — \`AnnotationJmxAttributeSource\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/AnnotationJmxAttributeSource.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Java SE 21 — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html