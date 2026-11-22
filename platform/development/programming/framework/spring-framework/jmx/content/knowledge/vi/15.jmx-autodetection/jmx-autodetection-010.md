# Chọn autodetection hay đăng ký tường minh theo rủi ro trong Spring JMX

## 1. Vấn đề cần giải quyết

Trong Spring Framework JMX, \`MBeanExporter\` có thể đưa Spring beans vào \`MBeanServer\` theo hai cách phổ biến:

- **Autodetection:** exporter dò các bean phù hợp trong \`ApplicationContext\` theo chế độ phát hiện đã cấu hình.
- **Đăng ký tường minh:** cấu hình cụ thể tập bean được export, thường với \`MBeanExporter.setBeans(...)\` và các \`ObjectName\` có chủ đích.

Cả hai đều có giá trị. Autodetection giảm cấu hình lặp lại khi có nhiều management beans. Đăng ký tường minh giúp giới hạn bề mặt JMX một cách dễ kiểm kê. Quyết định đúng phụ thuộc rủi ro của môi trường, mức độ nhạy cảm của operation/attribute, số lượng bean, thay đổi code theo thời gian và yêu cầu kiểm soát vận hành.

**Câu hỏi trung tâm:** Khi một bean mới được thêm vào ứng dụng hoặc khi metadata JMX thay đổi, hệ thống có nên tự đưa bean đó vào \`MBeanServer\` hay phải được chủ động bổ sung vào danh sách export?

Sau bài này, bạn có thể:

1. Giải thích cơ chế autodetection và explicit registration trong \`MBeanExporter\`.
2. Phân biệt các autodetect modes và vai trò của \`MBeanInfoAssembler\`.
3. Xác định những rủi ro cần xét trước khi tự động expose một bean.
4. Chọn chế độ phù hợp cho development, test, production hoặc hệ thống nhạy cảm.
5. Thiết kế quy trình kiểm chứng \`ObjectName\`, \`MBeanInfo\` và ownership của exporter.
6. Tránh các lỗi phổ biến như MBean trùng, expose nhầm operation nguy hiểm và trông chờ annotation tự đăng ký.

## 2. Mô hình tư duy

\`\`\`text
                   Spring ApplicationContext
                      /               \
                     /                 \
             AUTODETECTION        EXPLICIT REGISTRATION
                   |                      |
       Quét bean theo chế độ       Danh sách được chỉ định
       (MBean/assembler/...)       (setBeans map)
                   |                      |
                   +----------+-----------+
                              |
                         MBeanExporter
                       +------+------+
                       |             |
               ObjectNamingStrategy  MBeanInfoAssembler
                       |             |
                       +------+------+
                              |
                         MBeanServer
                              |
                     JConsole/JMX client
\`\`\`

Cần phân biệt:

- **Bean được Spring container quản lý** không đồng nghĩa tự động là MBean.
- **Bean được exporter chọn** chưa chắc đăng ký thành công, vì có thể lỗi \`ObjectName\`, metadata hoặc xung đột.
- **MBean đăng ký thành công** chưa chắc được truy cập từ xa; JMX remote connector và quyền mạng được cấu hình riêng.
- **Autodetection** chọn ứng viên; \`MBeanInfoAssembler\` quyết định giao diện quản trị và \`ObjectNamingStrategy\` quyết định tên.

Đừng nhầm autodetection của JMX với Spring component scanning. Component scanning tìm class để tạo Spring beans; JMX autodetection tìm các bean đã có trong container để xem bean nào thích hợp export.

## 3. Các chế độ autodetection

\`MBeanExporter\` cung cấp các chế độ phát hiện chính:

| Chế độ | Ý nghĩa | Kết quả theo mục đích |
|---|---|---|
| \`AUTODETECT_NONE\` | Không tự dò các bean | Chỉ các đối tượng được cấu hình tường minh được xét để export |
| \`AUTODETECT_MBEAN\` | Dò bean phù hợp JMX MBean convention/interface | Tự export các bean có management interface theo JMX |
| \`AUTODETECT_ASSEMBLER\` | Dò dựa trên \`MBeanInfoAssembler\` hỗ trợ autodetect | Phù hợp với metadata-driven JMX và annotation assembler |
| \`AUTODETECT_ALL\` | Kết hợp phát hiện theo MBean và assembler | Phạm vi có thể rộng nhất trong các chế độ nói trên |

Những giá trị này điều khiển **phát hiện ứng viên**, không phải chính sách bảo mật hay authorization.

### 3.1. AUTODETECT_NONE

Đây là chế độ dễ kiểm soát khi mỗi bean được export cần có một quyết định rõ ràng. Nếu dùng \`setBeans(...)\`, exporter biết chính xác tập bean được khai báo.

Ưu điểm: thay đổi ở một bean khác trong container không tự mở rộng tập MBean vì cơ chế scan.

Hạn chế: khi thêm MBean mới, phải cập nhật cấu hình; có thể bỏ sót một thành phần cần vận hành nếu quy trình không theo kịp.

### 3.2. AUTODETECT_MBEAN

Chế độ này nhắm vào các bean đã tuân thủ JMX MBean convention hoặc hợp đồng MBean phù hợp.

Ví dụ Standard MBean:

\`\`\`java
public interface QueueMonitorMBean {
    int getPendingCount();
    void resetStatistics();
}

public class QueueMonitor implements QueueMonitorMBean {
    @Override
    public int getPendingCount() {
        return 42;
    }

    @Override
    public void resetStatistics() {
        // Chỉ minh họa operation quản trị.
    }
}
\`\`\`

Khi bean được Spring tạo và exporter phát hiện là MBean phù hợp, nó có thể được export. Tuy nhiên cách đặt tên vẫn cần phù hợp naming strategy.

**Rủi ro:** Một class mới tình cờ tuân theo convention MBean có thể trở thành ứng viên nếu autodetection được bật. Cần kiểm soát các module được quét và MBean được công bố thực tế.

### 3.3. AUTODETECT_ASSEMBLER

Chế độ này dựa vào assembler, ví dụ \`MetadataMBeanInfoAssembler\` với \`AnnotationJmxAttributeSource\`.

\`\`\`java
@ManagedResource(
    objectName = "com.example.monitoring:type=Queue,name=Orders"
)
public class QueueMonitor {
    @ManagedAttribute
    public int getPendingCount() {
        return 42;
    }
}
\`\`\`

Bean có metadata phù hợp có thể được chọn thông qua assembler. Nhưng \`@ManagedResource\` **chỉ là metadata**; cần source, assembler và exporter được cấu hình đúng.

**Rủi ro:** Developer thêm \`@ManagedResource\` vì muốn debug, nhưng do cơ chế autodetection đang bật, bean mới có thể xuất hiện trong JMX management surface của môi trường production.

### 3.4. AUTODETECT_ALL

Chế độ này bao quát cả việc phát hiện bean tuân thủ MBean contract lẫn bean được assembler nhận diện.

Nó giảm việc khai báo từng bean nhưng làm phạm vi export thay đổi theo source code, các dependency và Spring context.

Không nên mặc định rằng \`AUTODETECT_ALL\` là tốt nhất chỉ vì tên có chữ “ALL”. Nó phù hợp khi có mục tiêu khám phá rõ ràng và kiểm soát thay đổi đủ tốt; ở hệ thống có yêu cầu bảo mật hoặc tenant isolation, phạm vi rộng có thể khó kiểm kê hơn.

## 4. Đăng ký tường minh với setBeans

Ví dụ hai bean được chọn cụ thể:

\`\`\`java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxConfiguration {
    @Bean
    public MBeanExporter mBeanExporter(
            QueueMonitor queueMonitor,
            CacheMonitor cacheMonitor) {

        Map<String, Object> exports = new LinkedHashMap<>();
        exports.put(
            "com.example.monitoring:type=Queue,name=Orders",
            queueMonitor
        );
        exports.put(
            "com.example.monitoring:type=Cache,name=Products",
            cacheMonitor
        );

        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(exports);
        exporter.setAutodetectMode(
            MBeanExporter.AUTODETECT_NONE
        );
        return exporter;
    }
}
\`\`\`

Trong ví dụ:

- Hai object được truyền trực tiếp vào export map.
- Mỗi entry chỉ định ObjectName có chủ đích.
- Autodetection bị tắt nhằm tránh mở rộng tập export ngoài danh sách.
- Khi muốn thêm MBean thứ ba, cấu hình phải được cập nhật.

Các class \`QueueMonitor\` và \`CacheMonitor\` cần là MBean hợp lệ hoặc được exporter hỗ trợ adaptation với assembler thích hợp. Nếu là POJO và chỉ dùng annotation, phải cấu hình annotation metadata assembler; việc \`setBeans\` không tự tạo metadata quản trị có chủ đích.

**Lưu ý về key:** \`setBeans\` dùng các key/tên trong cấu hình export; cách tên cuối cùng được xác định có thể tương tác với \`ObjectNamingStrategy\`. Khi cần kiểm soát chính xác, kiểm tra \`ObjectName\` được đăng ký thực tế và không suy đoán toàn bộ hành vi từ một chuỗi key.

## 5. Autodetection theo annotation

Ví dụ dùng \`@ManagedResource\` với annotation-driven exporter.

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.monitoring:type=Queue,name=Orders",
    description = "Order queue monitoring"
)
public class QueueMonitor {
    @ManagedAttribute(description = "Current queue depth")
    public int getPendingCount() {
        return 42;
    }
}
\`\`\`

Spring Framework cho phép dùng:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
\`\`\`

Với cấu hình annotation export phù hợp, Spring có thể tìm các managed beans dựa trên metadata. Đây là cách gọn cho dự án có quy ước annotation rõ ràng.

Điều cần quản lý là **annotation mới có thể làm tăng tập MBean được export** nếu cơ chế tự phát hiện đang bật. Vì thế, code review cần xem \`@ManagedResource\` và member annotations như một thay đổi API quản trị, không chỉ là chú thích vô hại.

### Khác với Spring Boot

Nếu ứng dụng dùng Spring Boot, cần xem auto-configuration và property như \`spring.jmx.enabled\` trong phiên bản đang sử dụng. Đừng đặt thêm \`@EnableMBeanExport\` hay \`MBeanExporter\` thủ công nếu Boot đã cấu hình cùng chức năng, vì nhiều exporter có thể cố đăng ký cùng ObjectName.

Autodetection của exporter và việc expose Spring Boot Actuator endpoints qua HTTP/JMX là những vấn đề liên quan nhưng không đồng nhất. Cần quản lý cấu hình tương ứng theo đúng mục tiêu.

## 6. Đánh giá rủi ro trước khi chọn chế độ

Đề bài không có một câu trả lời đúng cho mọi ứng dụng. Có thể đánh giá theo các chiều sau:

| Yếu tố | Dấu hiệu ưu tiên explicit registration | Dấu hiệu có thể chọn autodetection |
|---|---|---|
| Mức độ nhạy cảm | MBean có operation thay đổi trạng thái quan trọng | MBean chủ yếu chỉ đọc, dữ liệu không nhạy cảm |
| Quy mô | Ít MBean, tập tên ổn định | Nhiều loại monitor, bổ sung thường xuyên |
| Quyền truy cập | Nhiều tenant/nhóm quyền, cần allowlist nghiêm | Môi trường vận hành nội bộ có kiểm soát |
| Nguồn code | Nhiều team, plugin/dependency có thể thêm beans | Các bean quản trị được kiểm soát tập trung |
| Thay đổi | Muốn mọi MBean mới được review riêng | Muốn thêm managed bean bằng annotation |
| Debug | Cần đảm bảo không mở thêm MBean ngoài danh sách | Cần khám phá nhanh các MBean quan sát |
| Môi trường | Production nhạy cảm hoặc regulated | Test/dev hoặc production có governance tốt |
| Ownership | Nhiều context/exporter cùng MBeanServer | Một context có quy ước tên và quyền rõ ràng |

**Không đánh đồng explicit với “an toàn tuyệt đối”.** Một MBean được đăng ký tường minh nhưng có operation nguy hiểm và JMX remote mở sai cách vẫn có rủi ro cao.

Ngược lại, autodetection có thể phù hợp trong production khi tập annotation được kiểm soát, bề mặt quản trị được kiểm thử và JMX access bị giới hạn đúng cách.

## 7. Ma trận lựa chọn theo mức rủi ro

Một gợi ý ra quyết định:

| Mức độ | Ví dụ | Chiến lược thường phù hợp | Điều kiện bổ sung |
|---|---|---|---|
| **Thấp** | Counter/health attributes chỉ đọc, môi trường dev | Autodetection theo assembler hoặc MBean | Kiểm tra metadata và tránh dữ liệu nhạy cảm |
| **Trung bình** | Cache monitor, refresh nhẹ, staging | Autodetection có review hoặc explicit | Giới hạn access và kiểm soát operation |
| **Cao** | Reset production state, thay đổi cấu hình runtime | Explicit registration/allowlist | Authentication, authorization, audit, validation |
| **Rất cao** | MBean có tác động tài chính, dữ liệu nhạy cảm, multi-tenant | Tối thiểu hóa export, thường explicit | Có thể không expose trực tiếp operation qua JMX |

Bảng này là khung tư duy, không phải chính sách bảo mật có hiệu lực tự động. Quyết định thực tế cần xét mức tác động, mô hình truy cập và cách triển khai.

### Đặt câu hỏi trước khi bật autodetection

1. Ai có thể kết nối đến MBeanServer này?
2. MBean có writable attributes hoặc operations thay đổi trạng thái không?
3. Cơ chế export có quét bean trong dependency/module bên ngoài kiểm soát không?
4. Tên ObjectName có thể trùng khi nhiều context chạy cùng JVM không?
5. Có công cụ giám sát phụ thuộc vào MBean names hiện tại không?
6. Mỗi thay đổi annotation có được review như thay đổi API quản trị không?
7. Có thể kiểm kê chính xác MBeans sau khởi động không?

Nếu không trả lời được các câu hỏi về quyền và phạm vi export, nên thu hẹp tập MBean trước khi mở rộng cơ chế tự dò.

## 8. Các loại rủi ro kỹ thuật của autodetection

### 8.1. Vô tình mở rộng bề mặt quản trị

Developer thêm:

\`\`\`java
@ManagedResource(
    objectName = "com.example.monitoring:type=Maintenance,name=System"
)
public class MaintenanceMonitor {
    @ManagedOperation
    public void clearAllCaches() {
        // Có tác động lớn.
    }
}
\`\`\`

Nếu \`AUTODETECT_ASSEMBLER\` đang bật, bean này có thể được export mà không cần chỉnh một allowlist riêng. Nếu MBeanServer được truy cập bởi nhóm operator rộng hơn dự kiến, rủi ro tăng.

Giải pháp: review annotations, kiểm tra tập MBean xuất bản thực tế, phân quyền JMX và tránh đặt method nhạy cảm lên interface quản trị chung.

### 8.2. Thay đổi không dự kiến khi nâng cấp dependency

Một thư viện hoặc module mới có thể thêm compliant MBeans hoặc bean có metadata JMX. Trong context có autodetection rộng, tập MBean thay đổi mà file cấu hình export không đổi.

Giải pháp: kiểm kê ObjectNames trong integration test và so sánh với danh sách MBean được dự kiến. Cân nhắc \`AUTODETECT_ASSEMBLER\` thay vì \`AUTODETECT_ALL\` nếu muốn chỉ chọn annotation-based managed resources.

### 8.3. Tên trùng

Hai bean có thể cùng khai báo:

\`\`\`text
com.example.monitoring:type=Worker,name=Import
\`\`\`

trên cùng MBeanServer. Khi autodetection phát hiện cả hai, exporter có thể gặp \`InstanceAlreadyExistsException\` hoặc xử lý theo registration policy.

Giải pháp: định nghĩa domain/type/name/instance naming convention; tránh nhiều exporter cố đăng ký một đối tượng cùng tên.

### 8.4. Metadata và proxy

Spring AOP hoặc proxy có thể khiến một bean runtime khác với target class. Annotation source/assembler cần tìm được metadata đúng và operation được expose phải gọi được trên object thực tế.

Giải pháp: test tích hợp đối với bean có \`@Transactional\`, \`@Async\` hoặc proxy đặc biệt. Nếu cần, tách management facade bean riêng.

### 8.5. Khác biệt giữa các môi trường

Dev có thể bật JMX/exporter, production lại tắt, hoặc ngược lại. Một operator có thể kết luận sai rằng bean bị lỗi nếu chỉ nhìn JConsole.

Giải pháp: xác minh cấu hình exporter, target MBeanServer và remote connector cho từng môi trường. Đừng nhầm việc client không kết nối được với việc bean không được đăng ký.

## 9. Rủi ro của explicit registration

Đăng ký tường minh cũng có chi phí và lỗi:

### 9.1. Bỏ sót MBean mới

Developer tạo monitor bean đúng nhưng quên thêm vào export map. Bean vẫn hoạt động trong Spring nhưng JMX client không thấy.

Cách xử lý: quản lý danh sách MBean dự kiến như một contract và có kiểm thử xác minh các ObjectNames quan trọng.

### 9.2. Configuration drift

Tên ObjectName hoặc bean reference thay đổi, nhưng map export chưa cập nhật. Có thể dẫn đến fail khi startup hoặc xuất nhầm đối tượng.

Cách xử lý: cấu hình tập trung; dùng constant/factory cho ObjectName khi thích hợp, và kiểm tra registration.

### 9.3. Map cấu hình quá lớn

Với hàng trăm MBeans, một \`setBeans\` map dài khó đọc, nhất là khi mỗi thành phần liên tục thêm monitor riêng.

Cách xử lý: chia cấu hình theo module, hoặc dùng autodetection có kiểm soát với naming convention và kiểm kê sau khởi động.

### 9.4. Cảm giác an toàn giả

Danh sách explicit vẫn có thể chứa một MBean expose dữ liệu nhạy cảm hoặc operation nguy hiểm.

Cách xử lý: review \`MBeanInfo\`, attributes/operations thực tế, quyền JMX remote và cách truy cập; không dựa vào sự hiện diện của allowlist là đủ.

## 10. Chính sách đăng ký và xung đột

\`MBeanExporter\` hỗ trợ \`RegistrationPolicy\` để xử lý ObjectName đã tồn tại:

\`\`\`java
import org.springframework.jmx.support.RegistrationPolicy;

exporter.setRegistrationPolicy(
    RegistrationPolicy.FAIL_ON_EXISTING
);
\`\`\`

Các policy:

| Policy | Ý nghĩa | Rủi ro cần xét |
|---|---|---|
| \`FAIL_ON_EXISTING\` | Báo lỗi khi tên đã có | Có thể làm ứng dụng startup fail, nhưng lộ lỗi cấu hình sớm |
| \`IGNORE_EXISTING\` | Không thay đăng ký hiện hữu | Có thể giữ MBean khác với đối tượng bạn kỳ vọng |
| \`REPLACE_EXISTING\` | Thay đăng ký hiện hữu | Có thể ảnh hưởng MBean thuộc context/library khác |

Registration policy không thay thế quyết định autodetection/explicit. Nó xử lý **khi đã có collision**, không tự xác định đúng tập bean được phép công bố.

Trong production nhạy cảm, fail fast đối với tên trùng thường giúp phát hiện cấu hình sai; nhưng cần xét tác động của việc startup fail đối với hệ thống.

## 11. Kiểm chứng tập MBean được export

Một cách tốt để kiểm soát cả hai chiến lược là **kiểm kê thực tế trên MBeanServer** sau khi Spring context khởi động.

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.util.Set;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName pattern = new ObjectName(
    "com.example.monitoring:*"
);

Set<ObjectName> names =
    server.queryNames(pattern, null);

for (ObjectName name : names) {
    System.out.println(name.getCanonicalName());
}
\`\`\`

**Lưu ý:** \`ManagementFactory.getPlatformMBeanServer()\` trả về platform MBeanServer của JVM hiện tại. Nếu exporter chọn server khác, phải truy vấn đúng server đó. Nếu client ở JVM khác, dùng \`JMXConnector\` và \`MBeanServerConnection\`.

Tập \`queryNames()\` cho biết tên tồn tại, nhưng chưa đủ để xác định độ an toàn. Đọc tiếp \`MBeanInfo\`:

\`\`\`java
for (ObjectName name : names) {
    var info = server.getMBeanInfo(name);

    System.out.println("MBean: " + name.getCanonicalName());

    for (var attribute : info.getAttributes()) {
        System.out.printf(
            "  attribute=%s readable=%s writable=%s%n",
            attribute.getName(),
            attribute.isReadable(),
            attribute.isWritable()
        );
    }

    for (var operation : info.getOperations()) {
        System.out.printf(
            "  operation=%s%n",
            operation.getName()
        );
    }
}
\`\`\`

Đây là cách phát hiện một attribute bỗng thành writable hoặc operation mới được expose sau thay đổi code.

### Kiểm thử tập tên mong đợi

Trong integration test, có thể so sánh danh sách ObjectName theo domain ứng dụng với allowlist hoặc tập tên đã được chấp thuận.

Ví dụ logic:

\`\`\`java
Set<String> actual = names.stream()
    .map(ObjectName::getCanonicalName)
    .collect(java.util.stream.Collectors.toSet());

Set<String> expected = Set.of(
    new ObjectName(
        "com.example.monitoring:type=Queue,name=Orders"
    ).getCanonicalName(),
    new ObjectName(
        "com.example.monitoring:type=Cache,name=Products"
    ).getCanonicalName()
);

if (!actual.equals(expected)) {
    throw new AssertionError(
        "Unexpected JMX exposure: " + actual
    );
}
\`\`\`

Trong môi trường có thêm MBeans do hạ tầng tạo trong cùng domain, phạm vi so sánh cần được định nghĩa rõ. Không so toàn bộ \`java.lang\` hoặc những domain hệ thống như thể mọi tên đều do ứng dụng sở hữu.

## 12. Một thiết kế kết hợp

Autodetection và explicit không nhất thiết áp dụng một kiểu cho mọi phần của hệ thống. Có thể chia các nhóm quản trị theo mức rủi ro.

Ví dụ:

- **Monitoring read-only:** dùng autodetection có review trong domain chỉ dành cho quan sát.
- **Operations nhạy cảm:** dùng exporter explicit, giới hạn tập bean, tách domain/quyền nếu kiến trúc hỗ trợ.
- **MBeans của thư viện:** để library quản lý hoặc xác định ownership cụ thể, tránh export trùng.
- **Dynamic instances:** dùng registration programmatic có kiểm soát lifecycle/naming thay vì cùng annotation name cho mọi instance.

Điều cần chú ý là **nhiều exporter trong cùng context/JVM có thể trùng tập bean hoặc ObjectName**. Khi dùng mô hình kết hợp, phải đảm bảo mỗi MBean có một chủ sở hữu đăng ký rõ ràng.

Một cách tổ chức đơn giản hơn là giữ một exporter với tập explicit ở production, và chỉ bật autodetection trong profile thử nghiệm nếu nhu cầu thật sự đòi hỏi. Tuy nhiên profile môi trường không được trở thành lý do để khác biệt hành vi quản trị không được kiểm thử.

## 13. Bảo mật và phạm vi truy cập

Cần tách ba lớp:

1. **Selection:** exporter chọn bean nào.
2. **Management interface:** bean expose attributes/operations nào.
3. **Access control:** ai được đọc/ghi/gọi qua JMX.

Autodetection/explicit xử lý chủ yếu lớp **selection**. Chúng không tự thực thi đầy đủ lớp thứ ba.

Một triển khai an toàn cần xét:

- JMX remote có được mở hay không và trên interface mạng nào.
- Authentication, authorization, TLS hoặc bảo vệ kênh khi cần.
- Người dùng nào được gọi \`invoke\`, \`setAttribute\`.
- Operation có tác động đến dữ liệu, cache, worker hay hệ thống bên ngoài.
- Attribute có lộ secret, token, đường dẫn hệ thống hoặc thông tin cá nhân không.
- Có audit cho thao tác quản trị nhạy cảm hay không.

Một MBean “read-only” cũng cần review vì dữ liệu chẩn đoán có thể nhạy cảm. Ngược lại, một MBean explicit với operation làm thay đổi trạng thái vẫn cần bảo vệ.

## 14. Cấu hình theo rủi ro: hai ví dụ

### 14.1. Hệ thống nội bộ chỉ có monitoring

Giả sử ứng dụng có khoảng vài chục monitor chỉ đọc, được duy trì bởi một nhóm code owner. Autodetection theo assembler có thể giảm việc lặp map và tạo cơ chế mở rộng nhất quán.

\`\`\`java
MBeanExporter exporter = new MBeanExporter();
exporter.setAssembler(assembler);
exporter.setNamingStrategy(namingStrategy);
exporter.setAutodetectMode(
    MBeanExporter.AUTODETECT_ASSEMBLER
);
\`\`\`

Điều kiện phù hợp:
- Chỉ class được đánh dấu annotation JMX được xét.
- Operation nhạy cảm không có trong cùng policy.
- ObjectName được kiểm tra qua integration test.
- Remote access bị giới hạn.
- Mọi thay đổi \`@ManagedResource\` được review.

### 14.2. Hệ thống production có operation quản trị quan trọng

Giả sử hệ thống có \`flushQueue\`, \`reloadCredentials\`, \`resetState\`. Việc một annotation mới vô tình mở operation có thể gây hậu quả.

Một danh sách explicit:

\`\`\`java
MBeanExporter exporter = new MBeanExporter();
exporter.setAutodetectMode(
    MBeanExporter.AUTODETECT_NONE
);
exporter.setBeans(Map.of(
    "com.example.admin:type=Cache,name=SafeCache",
    safeCacheMonitor
));
\`\`\`

Cách này khiến phạm vi export rõ ràng. Vẫn cần kiểm tra nội dung interface và access control. Nếu \`safeCacheMonitor\` là POJO annotation-based, bổ sung metadata assembler phù hợp.

**Không có một ngưỡng cố định** về số lượng bean hay mức rủi ro để lựa chọn. Đó là đánh giá kỹ thuật dựa trên tác động và mức kiểm soát cần thiết.

## 15. Các lỗi và hiểu lầm thường gặp

**Nhầm 1: “Autodetection nghĩa là tất cả @Component thành MBean.”**  
Không đúng. Exporter phát hiện theo mode và hợp đồng JMX/assembler, không tự động lấy toàn bộ Spring beans bất kể metadata.

**Nhầm 2: “@ManagedResource tự đăng ký vào MBeanServer.”**  
Không. Annotation cung cấp metadata; cần cơ chế export hoạt động.

**Nhầm 3: “AUTODETECT_ALL là mode an toàn nhất.”**  
Không. Nó là phạm vi phát hiện rộng, không phải security mode.

**Nhầm 4: “Explicit registration thì không cần kiểm tra quyền.”**  
Không đúng. Danh sách explicit không hạn chế ai có thể gọi JMX nếu access control chưa được cấu hình.

**Nhầm 5: “Đăng ký MBean thành công là remote client tự truy cập được.”**  
Không. Remote connector, mạng và bảo mật được cấu hình riêng.

**Nhầm 6: “RegistrationPolicy.REPLACE_EXISTING giải quyết triệt để tên trùng.”**  
Không. Nó có thể che conflict và thay MBean khác, gây lỗi ownership/lifecycle.

**Nhầm 7: “Đã chạy đúng trên dev thì production có cùng tập MBeans.”**  
Không chắc. Profile, dependencies, auto-configuration và những bean được tạo ở mỗi môi trường có thể khác nhau.

**Nhầm 8: “Kiểm tra ObjectName là đủ để review exposure.”**  
Không. Cần thêm \`MBeanInfo\`, đặc biệt writable attributes và operations.

## 16. Quy trình ra quyết định thực dụng

Có thể dùng trình tự sau trong một thiết kế mới:

1. **Liệt kê nhu cầu quản trị:** health/counter, diagnostics, cấu hình runtime, operation thay đổi state.
2. **Phân loại tác động:** chỉ đọc, ghi cấu hình, vận hành nhạy cảm, dữ liệu bí mật.
3. **Xác định đối tượng có thể kết nối:** local tool, nội bộ production, hay remote systems.
4. **Chọn phạm vi export:** explicit khi cần allowlist rõ; autodetect khi tập metadata được governance tốt và chi phí cấu hình explicit cao.
5. **Chọn naming policy:** domain, type, name, instance để tránh trùng.
6. **Kiểm soát interface:** annotations hoặc Standard MBean interface chỉ expose những gì cần.
7. **Kiểm tra runtime:** xuất MBeans trong test context, query ObjectNames và \`MBeanInfo\`.
8. **Kiểm tra access control:** remote network, credentials, quyền invoke/set.
9. **Kiểm tra vòng đời:** startup, shutdown, restart, multi-context và collision.
10. **Ghi nhận quy ước:** để người thêm bean mới biết khi nào phải cập nhật allowlist hoặc annotations.

Nếu thay đổi exporter mode sau khi đã deploy, nên coi đó là thay đổi bề mặt quản trị: MBean nào xuất hiện/biến mất, client nào bị ảnh hưởng, quyền nào cần cập nhật.

## 17. Bài tập thực hành

### Bài tập A — So sánh hai chiến lược

1. Tạo hai monitor beans \`QueueMonitor\` và \`CacheMonitor\`.
2. Gắn \`@ManagedResource\` cho cả hai.
3. Dùng \`AUTODETECT_ASSEMBLER\`; kiểm tra cả hai được export khi có assembler/metadata source phù hợp.
4. Chuyển sang \`AUTODETECT_NONE\` và \`setBeans\` chỉ chứa \`QueueMonitor\`.
5. Kiểm tra \`CacheMonitor\` không còn được đăng ký bởi exporter.
6. Đối chiếu ObjectNames và MBeanInfo giữa hai lần chạy.

### Bài tập B — Thêm một operation

1. Dùng một MBean chỉ có getter read-only.
2. Thêm \`@ManagedOperation\` lên một method thay đổi state trong môi trường thử nghiệm.
3. Đọc lại \`MBeanInfo.getOperations()\`.
4. Giải thích vì sao đây là thay đổi management API dù cấu hình exporter không đổi.

### Bài tập C — Xung đột ObjectName

1. Tạo hai bean có \`@ManagedResource.objectName\` giống nhau.
2. Bật autodetection trên cùng MBeanServer.
3. Quan sát lỗi/policy.
4. Đặt tên riêng hoặc chỉ export một bean.
5. Xác minh kết quả bằng \`queryNames()\`.

### Bài tập D — Kiểm tra production allowlist

1. Liệt kê ObjectNames được phép trong domain ứng dụng.
2. Khởi động context.
3. \`queryNames()\` để lấy danh sách thực tế.
4. \`getMBeanInfo()\` để kiểm tra writable attributes và operations.
5. Fail kiểm thử nếu có MBean hoặc operation ngoài hợp đồng đã duyệt.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** \`AUTODETECT_NONE\` có ý nghĩa gì?  
**Trả lời:** Không tự dò bean; tập export được xác định từ cấu hình tường minh.

**Câu 2.** Khi nào \`AUTODETECT_ASSEMBLER\` phù hợp?  
**Trả lời:** Khi dùng assembler có thể nhận diện các bean được khai báo bằng metadata như Spring JMX annotations.

**Câu 3.** Vì sao autodetection có thể tăng rủi ro dù không thay đổi file cấu hình?  
**Trả lời:** Một bean hoặc annotation mới có thể làm tập MBean được export mở rộng tự động.

**Câu 4.** Explicit registration có thay thế JMX authentication/authorization không?  
**Trả lời:** Không. Nó giới hạn tập bean được chọn, không tự quyết định ai có quyền thao tác.

**Câu 5.** Vì sao phải đọc \`MBeanInfo\` sau khi đăng ký?  
**Trả lời:** Để xác minh các attribute/operation thực tế được expose, kể cả writable flags.

**Câu 6.** Chọn \`REPLACE_EXISTING\` có phải cách sửa tốt nhất khi trùng tên?  
**Trả lời:** Không. Cần xác định ownership, sửa naming hoặc export scope; policy replace có thể gây tác động ngoài ý muốn.

**Câu 7.** Một hệ thống nhiều plugin/contexts và có MBeans nhạy cảm thường cần ưu tiên gì?  
**Trả lời:** Phạm vi export có thể kiểm kê rõ, quyền được kiểm soát và quy tắc naming tránh trùng; explicit registration thường là lựa chọn dễ quản lý hơn.

## 19. Ghi nhớ

- Autodetection và explicit registration là **hai chiến lược lựa chọn bean**, không phải hai cơ chế bảo mật.
- \`AUTODETECT_NONE\` giữ tập export tường minh; \`AUTODETECT_MBEAN\` dò compliant MBeans; \`AUTODETECT_ASSEMBLER\` dựa vào assembler; \`AUTODETECT_ALL\` kết hợp các nguồn phát hiện.
- Autodetection tiện khi quản lý annotations nhất quán và cần mở rộng nhanh, nhưng có thể làm tăng tập MBeans khi code/dependencies thay đổi.
- Explicit registration giúp tạo allowlist rõ ràng cho những hệ thống nhạy cảm, nhưng có chi phí bảo trì cấu hình.
- Dù chọn cách nào, phải review ObjectName, MBeanInfo, operation tác động trạng thái, authentication/authorization và lifecycle.
- Không dùng registration policy như cách che xung đột naming.
- Kiểm chứng thực tế bằng \`MBeanServer.queryNames()\` và \`getMBeanInfo()\` trên đúng server.

### Tài liệu tham khảo

- Spring Framework Reference — JMX Exporting: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Spring Framework Javadoc — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Javadoc — \`MetadataMBeanInfoAssembler\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/assembler/MetadataMBeanInfoAssembler.html
- Spring Framework Javadoc — \`RegistrationPolicy\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/support/RegistrationPolicy.html
- Spring Framework Javadoc — \`@EnableMBeanExport\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/EnableMBeanExport.html
- Java SE 21 API — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
