# Không phơi bày nhầm service nội bộ qua annotation

> **Chủ đề:** Spring Framework JMX  
> **Nhóm kiến thức:** ManagedResource  
> **Bài học:** Không phơi bày nhầm service nội bộ qua annotation

## 1. Mục tiêu bài học

Sau bài học, bạn có thể:

- Giải thích vì sao một Spring service nội bộ có thể vô tình trở thành bề mặt quản trị khi gắn \`@ManagedResource\`.
- Phân biệt việc bean tồn tại trong Spring \`ApplicationContext\` với việc bean được đăng ký trong JMX \`MBeanServer\`.
- Nhận diện những attribute, operation và notification không nên công bố cho JMX client.
- Thiết kế một **management facade** riêng để chỉ công bố dữ liệu và thao tác quản trị có chủ đích.
- Sử dụng \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\` và \`@EnableMBeanExport\` có kiểm soát.
- Kiểm tra bề mặt MBean thực tế bằng \`MBeanInfo\` trước khi đưa ứng dụng vào môi trường có công cụ quản trị.
- Hiểu rằng không bật remote connector vẫn cần quản lý quyền truy cập local JMX và tránh đưa dữ liệu bí mật vào MBean.

## 2. Vấn đề: annotation quản trị có thể mở thêm một giao diện của ứng dụng

Một Spring service thường được thiết kế để phục vụ logic nội bộ. Ví dụ \`PaymentService\` có thể chứa dependency, cấu hình giao dịch, khóa truy cập nhà cung cấp và các method thay đổi trạng thái.

Khi một class được gắn \`@ManagedResource\`, và ứng dụng bật annotation-based JMX export, Spring có thể đăng ký bean này dưới dạng MBean trong \`MBeanServer\`.

\`\`\`text
               Spring ApplicationContext
                           |
               +-----------+------------+
               |                        |
         PaymentService             CacheService
         nghiệp vụ nội bộ           nghiệp vụ nội bộ
               |
               | @ManagedResource
               | @ManagedAttribute
               | @ManagedOperation
               v
           MBeanExporter
               |
               v
           MBeanServer
               |
               v
       JConsole / JMX client
       đọc attribute, gọi operation
\`\`\`

Chỉ có Spring bean không đồng nghĩa có MBean. Nhưng khi annotation và exporter hoạt động cùng nhau, những thành phần quản trị đã công bố có thể trở thành điểm tương tác ngoài luồng gọi nghiệp vụ thông thường.

**Bề mặt JMX là một API quản trị.** Nó cần được thiết kế giống một API có tác dụng thật: có hợp đồng, phạm vi cho phép, kiểm tra đầu vào, quyền truy cập và cách kiểm chứng.

## 3. Các annotation liên quan

| Annotation | Ý nghĩa | Rủi ro khi dùng thiếu kiểm soát |
|---|---|---|
| \`@ManagedResource\` | Đánh dấu bean là tài nguyên JMX và có thể khai báo \`ObjectName\`. | Dễ biến một service nghiệp vụ thành đối tượng có thể được công cụ JMX tìm thấy. |
| \`@ManagedAttribute\` | Công bố getter/setter thành JMX attribute. | Getter có thể làm lộ dữ liệu; setter có thể sửa cấu hình hoặc trạng thái. |
| \`@ManagedOperation\` | Công bố method thành JMX operation. | Operation có thể xóa dữ liệu, reload cấu hình, thay đổi tài nguyên hoặc kích hoạt xử lý tốn kém. |
| \`@ManagedOperationParameters\` | Mô tả tham số operation. | Làm giao diện dễ gọi hơn; phải bảo đảm operation thực sự được phép expose. |
| \`@ManagedNotifications\` / \`@ManagedNotification\` | Công bố loại JMX notification. | Notification payload có thể chứa dữ liệu nội bộ hoặc phát quá nhiều sự kiện. |
| \`@EnableMBeanExport\` | Bật annotation-based MBean export trong Java configuration. | Có thể kích hoạt export các bean đã được gắn annotation mà nhóm phát triển chưa kiểm kê. |

\`@ManagedResource\` không có nghĩa mọi public method tự động xuất hiện như operation khi sử dụng Spring annotation metadata theo cấu hình thông thường. Nhưng điều này **không phải lý do để gắn annotation tùy tiện**: bề mặt JMX có thể thay đổi khi bổ sung \`@ManagedAttribute\`, \`@ManagedOperation\`, thay assembler hoặc thay cơ chế export.

## 4. Phân biệt bean nghiệp vụ và MBean quản trị

Một Spring bean có thể phục vụ nhiều luồng xử lý:

\`\`\`text
HTTP request / scheduled job / message consumer
                 |
                 v
             Service bean
                 |
                 v
         Repository / database
\`\`\`

Nếu service được export trực tiếp, có thêm luồng:

\`\`\`text
JMX client
    |
    v
MBeanServer
    |
    v
Service bean được export
    |
    v
Method và trạng thái nghiệp vụ
\`\`\`

Luồng thứ hai có thể vượt qua những kiểm soát chỉ được thiết kế ở HTTP controller, chẳng hạn validation, authorization hoặc audit gắn ở tầng web. Việc Spring Security bảo vệ REST endpoint **không tự động chứng minh** cùng một operation được bảo vệ khi gọi bằng JMX.

Do đó, đừng xem JMX là một “cửa sổ debug vô hại”. Một setter hoặc operation JMX có thể thực thi logic trên server thật, thậm chí ảnh hưởng database và hệ thống bên ngoài.

## 5. Ví dụ không nên làm: export trực tiếp một service nhạy cảm

Giả sử một service chứa cấu hình và method vận hành:

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Service;

@Service
@ManagedResource(
    objectName = "app.security:type=PaymentService,name=main"
)
public class PaymentService {

    private String providerApiKey = "example-secret";

    @ManagedAttribute
    public String getProviderApiKey() {
        return providerApiKey;
    }

    @ManagedOperation
    public void disableFraudChecks() {
        // Thay đổi hành vi kiểm tra rủi ro.
    }

    public void chargeCustomer(String customerId) {
        // Logic thanh toán nội bộ.
    }
}
\`\`\`

Đây là **ví dụ phản diện để nhận diện lỗi thiết kế**, không phải mã nên dùng trong ứng dụng thật. Hai vấn đề rõ ràng:

1. \`getProviderApiKey()\` có thể đưa giá trị bí mật vào JMX attribute.
2. \`disableFraudChecks()\` tạo operation cho phép thay đổi một kiểm soát quan trọng ngoài kênh quản trị được thiết kế riêng.

Trong một JMX client có quyền truy cập, người dùng có thể đọc attribute hoặc gọi operation đã được exporter công bố. Truy cập này không nhất thiết đi qua controller, REST authorization hoặc filter bảo mật của ứng dụng web.

Việc credential được đặt cứng trong source ở ví dụ là để minh họa điều không nên làm; trong sản phẩm thực tế không được hardcode secret. Ngay cả khi secret được lấy từ môi trường hoặc secret manager, expose qua JMX vẫn làm rò rỉ giá trị đó.

## 6. Nguyên tắc: chỉ export management facade có chủ đích

Một cách thiết kế rõ ràng là giữ service nghiệp vụ độc lập với annotation quản trị và tạo bean quản trị riêng.

\`\`\`text
           Spring ApplicationContext
              |                 |
              v                 v
       PaymentService      PaymentMetricsMBean
       nghiệp vụ thật      management facade
              ^                 |
              |                 | đọc chỉ số an toàn
              +-----------------+
                                |
                                | @ManagedResource
                                v
                          MBeanExporter
                                |
                                v
                           MBeanServer
                                |
                                v
                             JConsole
\`\`\`

Facade có trách nhiệm **chọn** những gì cần expose. Nó không cần sao chép toàn bộ API của service. Tốt nhất bắt đầu từ những thuộc tính chỉ đọc được định nghĩa rõ: số yêu cầu, số lỗi, thời điểm xử lý cuối, trạng thái hoạt động đã được tổng hợp.

### 6.1. Service không có annotation JMX

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    private final AtomicLong processedCount =
        new AtomicLong();

    private final AtomicLong failureCount =
        new AtomicLong();

    public void recordSuccess() {
        processedCount.incrementAndGet();
    }

    public void recordFailure() {
        failureCount.incrementAndGet();
    }

    public long processedCount() {
        return processedCount.get();
    }

    public long failureCount() {
        return failureCount.get();
    }

    // Các method nghiệp vụ và dependency nhạy cảm
    // không được export trực tiếp qua JMX.
}
\`\`\`

Service chỉ cung cấp một phần thông tin tổng hợp cần thiết cho facade. Ở ứng dụng thực, hãy cung cấp dữ liệu quan sát thông qua service hoặc metrics component rõ trách nhiệm, tránh tạo quyền truy cập lan rộng vào internals.

### 6.2. Facade chỉ đọc

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "app.monitoring:type=PaymentMetrics,name=main",
    description = "Non-sensitive payment counters"
)
public class PaymentMetricsMBean {

    private final PaymentService paymentService;

    public PaymentMetricsMBean(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    @ManagedAttribute(
        description = "Successful payment processing count"
    )
    public long getProcessedCount() {
        return paymentService.processedCount();
    }

    @ManagedAttribute(
        description = "Failed payment processing count"
    )
    public long getFailureCount() {
        return paymentService.failureCount();
    }
}
\`\`\`

Ở đây, facade chỉ công bố hai attribute read-only. Không có setter hay operation thay đổi trạng thái trong giao diện quản trị. \`PaymentService\` vẫn là service bình thường và không bị \`@ManagedResource\` gắn trực tiếp.

Tên class \`PaymentMetricsMBean\` trong ví dụ là tên mô tả vai trò facade; Spring annotation exporter sử dụng \`@ManagedResource\` và metadata liên quan. Không cần coi class này là Standard MBean interface kiểu \`PaymentMetricsMBean\` theo quy tắc JMX chuẩn.

### 6.3. Bật exporter trong Java configuration

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@ComponentScan(basePackageClasses = PaymentService.class)
@EnableMBeanExport
public class JmxConfiguration {
}
\`\`\`

Với component scan phù hợp, Spring tạo \`PaymentService\` và \`PaymentMetricsMBean\`. Annotation exporter đăng ký facade có \`@ManagedResource\`, còn service nghiệp vụ không được đưa vào MBeanServer chỉ vì nó là \`@Service\`.

Một hệ thống có thể dùng Spring Boot JMX auto-configuration thay vì khai báo \`@EnableMBeanExport\`; cần kiểm tra các exporter thực tế để tránh đăng ký trùng ObjectName. Dù bật bằng cơ chế nào, nguyên tắc **chọn facade có chủ đích** vẫn giữ nguyên.

## 7. Khi cần operation quản trị, giới hạn trách nhiệm và kiểm tra đầu vào

Đôi khi operator cần một thao tác như làm mới cache, reset counter hoặc thay đổi mức logging. Operation kiểu này vẫn có tác dụng phụ nên phải có hợp đồng rõ ràng.

Ví dụ một facade quản lý cache:

\`\`\`java
@Component
@ManagedResource(
    objectName = "app.monitoring:type=CacheControl,name=primary"
)
public class CacheControlMBean {

    private final CacheMaintenanceService maintenance;

    public CacheControlMBean(
            CacheMaintenanceService maintenance
    ) {
        this.maintenance = maintenance;
    }

    @ManagedOperation(
        description = "Refresh a permitted cache by name"
    )
    public String refreshCache(String cacheName) {
        if (!"catalog".equals(cacheName)
                && !"configuration".equals(cacheName)) {
            throw new IllegalArgumentException(
                "Unsupported cacheName"
            );
        }

        maintenance.refresh(cacheName);
        return "Refresh requested for " + cacheName;
    }
}
\`\`\`

\`CacheMaintenanceService\` là dependency minh họa có API \`refresh(String)\`, không phải một Spring class có sẵn. Trong ứng dụng thực, hãy triển khai service phù hợp và bảo đảm cách gọi qua JMX tuân thủ cùng các kiểm soát nghiệp vụ cần thiết.

Điểm thiết kế quan trọng:

- Facade expose **một thao tác hẹp** thay vì toàn bộ cache service.
- Tên cache được giới hạn bằng allowlist, không nhận bất kỳ chuỗi nào.
- Không expose operation nguy hiểm như “delete all data”.
- Kết quả trả về phân biệt việc gửi yêu cầu với việc hoàn tất công việc nếu backend xử lý bất đồng bộ.
- Khi môi trường yêu cầu audit, ghi nhận thao tác quản trị ở service hoặc lớp hạ tầng phù hợp.
- Quyền gọi remote JMX phải được giới hạn riêng, không dựa vào bảo vệ REST endpoint.

Ngay cả operation có vẻ nhỏ cũng có thể gây tải lớn nếu bị gọi nhiều lần. Hãy cân nhắc rate limiting tại tầng quản trị, idempotency và giới hạn tài nguyên cho thao tác tốn kém.

## 8. Không đánh đồng “internal” với “an toàn”

Có nhiều cách một client có thể truy cập JMX:

\`\`\`text
Cùng JVM:
  Code -> MBeanServer

Local process:
  JConsole / JMX client -> cơ chế attach phù hợp -> MBeanServer

Remote:
  JMXConnector -> MBeanServerConnection -> MBeanServer
\`\`\`

\`@EnableMBeanExport\` chỉ làm MBean xuất hiện trong registry; nó **không tự mở cổng remote**. Nhưng điều đó không đủ để kết luận MBean không thể bị truy cập: local JVM management, monitoring agent, công cụ trên máy chủ hoặc client đã được cấp quyền kết nối vẫn có thể tương tác.

Do đó cần phân biệt:

- **Kiểm soát phơi bày:** những attribute và operation nào tồn tại trong MBeanInfo.
- **Kiểm soát kết nối:** ai có thể mở kết nối JMX local/remote.
- **Kiểm soát quyền:** client nào được đọc hay gọi thao tác quản trị.
- **Kiểm soát dữ liệu:** giá trị trả về/notification không chứa secret hoặc thông tin nhạy cảm.

Một lỗi thiết kế ở tầng expose không nhất thiết được sửa chỉ bằng cách chặn cổng remote, vì các thành phần nội bộ vẫn có thể truy cập registry.

## 9. Quy tắc đặt ObjectName có chủ đích

Tên MBean nên mô tả chức năng quản trị thay vì expose cấu trúc nội bộ quá chi tiết.

Ví dụ nên dùng:

\`\`\`text
app.monitoring:type=PaymentMetrics,name=main
app.monitoring:type=CacheControl,name=primary
\`\`\`

Tên cần tránh khi không cần thiết:

\`\`\`text
app.internal:type=DatabaseCredentials,name=production
app.internal:type=PaymentSecretProvider,name=primary
\`\`\`

ObjectName không tự chứa secret nếu chỉ là tên. Tuy nhiên đặt tên tài nguyên quá chi tiết có thể làm lộ kiến trúc, công nghệ hoặc mục đích của hệ thống khi client duyệt registry.

Nếu có nhiều instance, bổ sung property có quy ước rõ ràng:

\`\`\`text
app.monitoring:type=WorkerPool,name=primary,node=one
app.monitoring:type=WorkerPool,name=primary,node=two
\`\`\`

Mỗi ObjectName phải duy nhất trong một MBeanServer. Tránh đưa dữ liệu người dùng chưa escape trực tiếp vào key property; với giá trị chứa ký tự đặc biệt, dùng \`ObjectName.quote(value)\` hoặc API tạo ObjectName phù hợp.

## 10. Kiểm tra nội dung JMX thực sự được expose

Không dừng ở việc đọc annotation trong source. Một \`MBeanInfo\` từ server đang chạy cho biết bề mặt quản trị đã đăng ký.

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "app.monitoring:type=PaymentMetrics,name=main"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException(
        "MBean missing: " + name
    );
}

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "Attribute: %s, readable=%s, writable=%s%n",
        attribute.getName(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println(
        "Operation: " + operation.getName()
    );
}
\`\`\`

Khi ví dụ facade được export bằng annotation metadata phù hợp, mong muốn thấy \`ProcessedCount\` và \`FailureCount\` ở dạng read-only, không có operation từ \`PaymentService\`.

**Chú ý:** \`ManagementFactory.getPlatformMBeanServer()\` chỉ cho thấy MBean trên platform server. Nếu Spring exporter dùng MBeanServer riêng, phải kiểm tra đúng server ấy; việc không tìm thấy trong platform server chưa chứng minh bean không được export.

### Kiểm tra bằng queryNames

\`\`\`java
ObjectName pattern = new ObjectName(
    "app.monitoring:type=*,*"
);

for (ObjectName objectName :
        server.queryNames(pattern, null)) {
    System.out.println(objectName);
}
\`\`\`

Query giúp kiểm kê MBean thuộc domain đã chọn. Khi rà soát toàn bộ bề mặt quản trị, có thể truy vấn phạm vi rộng hơn bằng client có quyền và kiểm tra từng MBeanInfo, tránh giả định domain này là nơi duy nhất ứng dụng export MBean.

## 11. Một bài test bảo đảm service nhạy cảm không xuất hiện

Có thể tạo bài kiểm chứng cấu hình khi chạy integration test trong một context đã bật JMX export:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;

import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(JmxConfiguration.class)
class JmxExposureTest {

    @Autowired
    MBeanServer server;

    @Test
    void onlyManagementFacadeIsRegistered() throws Exception {
        ObjectName facade = new ObjectName(
            "app.monitoring:type=PaymentMetrics,name=main"
        );
        ObjectName internal = new ObjectName(
            "app.security:type=PaymentService,name=main"
        );

        assertTrue(server.isRegistered(facade));
        assertFalse(server.isRegistered(internal));
    }
}
\`\`\`

Đoạn test giả định trong Spring context có bean \`MBeanServer\` được đăng ký cho phép injection và exporter dùng chính bean đó. Nếu context không expose \`MBeanServer\` như một Spring bean, cần tạo hoặc inject server bằng cấu hình phù hợp; không mặc định \`@Autowired MBeanServer\` luôn thành công.

Một cấu hình đơn giản để dùng platform server là:

\`\`\`java
@Configuration
@EnableMBeanExport(server = "jmxServer")
public class JmxServerConfig {

    @Bean
    public MBeanServer jmxServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }
}
\`\`\`

Trong test thực tế, hãy bảo đảm context test import đúng cấu hình này, tránh trùng tên khi nhiều test cùng chia sẻ platform MBeanServer và đóng context để exporter cleanup.

Cũng cần hiểu giới hạn của test tên cụ thể: nó chỉ chứng minh **một ObjectName** không xuất hiện. Nếu mục tiêu là bảo đảm không có bất kỳ service nhạy cảm nào bị expose, cần kiểm kê tất cả ObjectName và MBeanInfo thuộc phạm vi ứng dụng theo danh sách cho phép (allowlist).

## 12. Mẫu allowlist kiểm kê MBean

Một cách tiếp cận là khai báo tập ObjectName ứng dụng được phép export:

\`\`\`java
Set<String> allowed = Set.of(
    "app.monitoring:type=PaymentMetrics,name=main",
    "app.monitoring:type=CacheControl,name=primary"
);
\`\`\`

Sau đó đối chiếu với MBean đăng ký trong domain ứng dụng:

\`\`\`java
ObjectName applicationPattern =
    new ObjectName("app.monitoring:*");

Set<ObjectName> actual =
    server.queryNames(applicationPattern, null);

for (ObjectName objectName : actual) {
    if (!allowed.contains(
            objectName.getCanonicalName())) {
        throw new IllegalStateException(
            "Unexpected MBean: " + objectName
        );
    }
}
\`\`\`

Vì \`ObjectName.getCanonicalName()\` có thể sắp xếp lại thứ tự key properties, hãy đưa allowlist về dạng canonical tương ứng thay vì so sánh chuỗi nhập bất kỳ.

Ví dụ xây canonical allowlist:

\`\`\`java
Set<String> allowedCanonical = Set.of(
    new ObjectName(
        "app.monitoring:type=PaymentMetrics,name=main"
    ).getCanonicalName(),
    new ObjectName(
        "app.monitoring:type=CacheControl,name=primary"
    ).getCanonicalName()
);
\`\`\`

Khi quản trị nhiều domain, hãy kiểm kê từng domain mà ứng dụng có thể export. Nếu có exporter bên thứ ba hoặc agent runtime, danh sách MBean hợp lệ cần được quản lý rõ để tránh chặn nhầm MBean hệ thống.

**Allowlist tên là bước đầu, không phải toàn bộ bảo đảm.** Một MBean vẫn có thể expose thêm attribute hay operation nguy hiểm mà giữ nguyên ObjectName. Vì vậy kiểm tra thêm \`MBeanInfo\` và so sánh hợp đồng quản trị dự kiến.

## 13. Đánh giá attribute: thông tin nào nên/không nên công bố?

| Dữ liệu | Đánh giá | Lý do |
|---|---|---|
| Số request xử lý | Thường phù hợp | Chỉ số tổng hợp, ít nhạy cảm nếu không chứa thông tin người dùng. |
| Số lỗi theo loại | Có thể phù hợp | Hữu ích vận hành; tránh label chứa dữ liệu nhạy cảm. |
| Trạng thái service \`UP/DOWN\` | Thường phù hợp | Phục vụ chẩn đoán. |
| Độ dài hàng đợi | Thường phù hợp | Trạng thái tài nguyên. |
| Mật khẩu/token/API key | Không nên | Có thể bị đọc bởi client quản trị. |
| Connection string chứa credential | Không nên | Có thể làm lộ tài khoản hoặc endpoint nội bộ. |
| Danh sách email, tên khách hàng | Không nên xuất trực tiếp | Thông tin cá nhân không cần thiết cho quản trị tổng hợp. |
| SQL đầy đủ kèm tham số | Rủi ro cao | Có thể lộ dữ liệu và cấu trúc hệ thống. |
| Stack trace chứa secret | Không nên expose nguyên vẹn | Error detail đôi khi chứa giá trị nội bộ. |
| Cấu hình feature flag nhạy cảm | Cần cân nhắc | Có thể làm lộ cơ chế kiểm soát hoặc thay đổi hành vi. |

Một attribute read-only **không đồng nghĩa không có rủi ro**. Nó vẫn có thể làm lộ dữ liệu khi bị đọc. Một attribute writable còn mở thêm khả năng thay đổi trạng thái.

## 14. Kiểm tra operation: quyền gọi và tác dụng phụ

Trước khi gắn \`@ManagedOperation\` vào một method, trả lời:

1. Operation có mục đích vận hành rõ không?
2. Có cần hiển thị cho mọi client có quyền JMX hay chỉ một nhóm operator?
3. Có thể gọi lặp an toàn không?
4. Tham số có được kiểm tra và giới hạn giá trị không?
5. Operation có thể gây mất dữ liệu, gián đoạn dịch vụ hoặc ảnh hưởng security không?
6. Có cần audit ai gọi, khi nào, kết quả thế nào không?
7. Khi thất bại, exception có làm lộ chi tiết nhạy cảm không?
8. Nếu chạy lâu, có timeout, cơ chế trả trạng thái hoặc cancel không?

Đừng export trực tiếp method có quyền rộng chỉ vì tiện debug. Nếu cần một thao tác quản trị, hãy tạo facade gọi một service có kiểm tra đầu vào, trạng thái và quyền tương ứng.

### Vì sao có thể bỏ qua security của HTTP?

\`\`\`text
HTTP Request
  -> Spring Security Filter Chain
  -> Controller
  -> Service

JMX invoke
  -> JMXConnector / MBeanServer
  -> Exposed MBean operation
  -> Service
\`\`\`

Hai đường đi có thể không chia sẻ lớp authorization. Nếu logic bảo vệ chỉ nằm ở HTTP filter/controller, JMX invocation sẽ không tự thực thi những kiểm soát đó. Nơi phù hợp cho điều kiện nghiệp vụ quan trọng là service/hạ tầng chung; còn phân quyền thao tác quản trị cần được thiết kế ở tầng JMX connector và/hoặc facade phù hợp.

## 15. Notification cũng là bề mặt phơi bày dữ liệu

Một JMX notification có thể chứa:

- \`type\`, \`source\`, \`timeStamp\`, \`message\`.
- \`sequenceNumber\`.
- \`userData\` (payload do implementation gắn).

Ví dụ không nên:

\`\`\`java
Notification event = new Notification(
    "app.payment.failed",
    this,
    sequence.incrementAndGet(),
    System.currentTimeMillis(),
    "Payment failed for " + customerEmail
);
event.setUserData(rawPaymentRequest);
publisher.sendNotification(event);
\`\`\`

Message có thể chứa email khách hàng, \`userData\` có thể chứa dữ liệu giao dịch. Đây là thông tin mà client JMX có quyền nghe notification có thể nhận được.

Thay thế bằng thông tin tổng hợp:

\`\`\`java
Notification event = new Notification(
    "app.payment.failure.rate.high",
    this,
    sequence.incrementAndGet(),
    System.currentTimeMillis(),
    "Payment failure rate crossed threshold"
);
event.setUserData("severity=warning");
publisher.sendNotification(event);
\`\`\`

Nếu cần liên kết với sự kiện chi tiết, có thể dùng mã tương quan không nhạy cảm và kiểm tra chính sách dữ liệu của hệ thống trước khi phát.

## 16. Bảo vệ kết nối remote JMX

Đối với môi trường dùng remote connector, cần cấu hình các lớp kiểm soát:

- Xác thực người dùng hoặc cơ chế identity thích hợp.
- Phân quyền đọc/ghi/gọi operation.
- Mã hóa vận chuyển (TLS) khi cần.
- Giới hạn host, network segment, firewall và truy cập qua VPN/bastion.
- Chỉ bật endpoint khi có nhu cầu quản trị thật.
- Theo dõi và ghi log các thao tác quản trị quan trọng ở tầng phù hợp.

Spring \`@EnableMBeanExport\` hoặc \`@ManagedResource\` **không tự cấu hình** những lớp bảo vệ này. Một MBean không nên phụ thuộc vào giả định “không ai biết URL JMX” như một biện pháp an toàn.

Với local JMX, cần kiểm soát quyền trên host, người dùng hệ điều hành, agent và công cụ có khả năng attach vào JVM.

## 17. Sự cố thường gặp

### 17.1. Service bất ngờ xuất hiện trong JConsole

Kiểm tra:

- Bean có \`@ManagedResource\` không?
- Context có \`@EnableMBeanExport\` hoặc exporter tương đương không?
- Có \`MBeanExporter\` khai báo thủ công hoặc auto-configuration khác không?
- ObjectName thực tế là gì?
- Có naming strategy hay annotation metadata từ class/interface khác không?
- MBeanInfo hiện expose attribute/operation nào?

Đừng chỉ xóa \`@ManagedResource\` rồi cho rằng toàn bộ đường export biến mất, vì MBean có thể còn được đăng ký theo cấu hình explicit hoặc một exporter khác. Xác định cơ chế đăng ký thật trong context.

### 17.2. Service không có @ManagedResource nhưng vẫn bị export

Điều này có thể xảy ra nếu cấu hình \`MBeanExporter\` sử dụng danh sách bean tường minh hoặc cơ chế autodetection khác với annotation-based export. Kiểm tra exporter và các naming/assembler đang áp dụng, thay vì chỉ rà annotation trong class.

### 17.3. Chỉ muốn đọc metrics nhưng thấy setter/operation nguy hiểm

Kiểm tra \`MBeanInfo\` của MBean đã đăng ký. Nếu bề mặt rộng hơn mong muốn, xem assembler, method annotations, Standard MBean interface và cấu hình exporter. Chuyển sang facade chỉ expose hợp đồng nhỏ, hoặc thu hẹp annotation/assembler theo thiết kế.

### 17.4. Bỏ annotation rồi nhưng MBean cũ vẫn xuất hiện

Kiểm tra ứng dụng đã restart/reload đúng context chưa, exporter có cleanup MBean cũ không, có server khác cùng đăng ký tên không, và client có đang xem dữ liệu từ JVM cũ hay không. Không unregister MBean ngoài phạm vi sở hữu chỉ để “dọn cho sạch”.

### 17.5. Khóa/cấu hình không nằm trong attribute nhưng lộ qua exception

Một operation JMX có thể ném exception với message chứa cấu hình nội bộ. Đừng coi việc ẩn getter là đủ. Phải xử lý error logging và nội dung lỗi trả về cho client quản trị có chủ đích.

## 18. Tình huống thực hành

**Tình huống:** ứng dụng có \`InventoryService\` với các method:

\`\`\`java
public int getAvailableStock();
public String getSupplierApiToken();
public void rebuildIndex();
public void deleteAllInventory();
public void setReservationLimit(int limit);
\`\`\`

Một developer muốn thêm \`@ManagedResource\` và \`@ManagedOperation\` lên service để xem trạng thái qua JConsole.

Hãy thiết kế một facade thay thế.

**Gợi ý hợp đồng JMX:**

\`\`\`java
@Component
@ManagedResource(
    objectName = "app.monitoring:type=InventoryMetrics,name=main"
)
public class InventoryMetricsMBean {

    private final InventoryService service;

    public InventoryMetricsMBean(InventoryService service) {
        this.service = service;
    }

    @ManagedAttribute
    public int getAvailableStock() {
        return service.getAvailableStock();
    }
}
\`\`\`

Ở giai đoạn đầu chỉ công bố \`AvailableStock\`, không công bố \`getSupplierApiToken\` hoặc \`deleteAllInventory\`. \`rebuildIndex\` có thể được cân nhắc riêng như một operation bảo trì, cần điều kiện vận hành, audit và giới hạn quyền rõ ràng. \`setReservationLimit\` là thao tác thay đổi chính sách nghiệp vụ, không nên expose nếu chưa có kiểm soát thích hợp.

**Câu hỏi:** Nếu client JMX có quyền đọc MBean nhưng không được phép thay đổi hệ thống, nên có getter/setter nào? Vì sao?

**Gợi ý trả lời:** chỉ expose thông tin tổng hợp cần thiết qua getter read-only. Không expose setter/operation làm thay đổi trạng thái; đồng thời kiểm soát quyền đọc JMX để ngăn lộ thông tin không phù hợp.

## 19. Checklist thiết kế trước khi đưa MBean vào môi trường chạy

- [ ] Có lý do vận hành cụ thể để export MBean này.
- [ ] \`@ManagedResource\` chỉ xuất hiện trên bean/facade được duyệt.
- [ ] ObjectName thuộc domain quản trị có quy ước và không chứa dữ liệu nhạy cảm.
- [ ] Attribute được công bố theo allowlist; setter chỉ tồn tại khi thật sự cần.
- [ ] Operation có trách nhiệm hẹp, kiểm tra input và được giới hạn quyền.
- [ ] \`MBeanInfo\` đã được đối chiếu với hợp đồng mong muốn.
- [ ] Notification type/message/userData không làm lộ dữ liệu người dùng hoặc secret.
- [ ] Các exporter trong context không đăng ký thừa bean, trùng ObjectName hoặc mở rộng bề mặt ngoài dự kiến.
- [ ] Remote JMX connector (nếu bật) có xác thực, phân quyền và bảo vệ network.
- [ ] MBean lifecycle và cleanup khi context đóng được hiểu rõ.
- [ ] Có cách kiểm tra hồi quy khi thay đổi annotation hoặc cấu hình exporter.

Đây là những điểm kiểm tra thiết kế dành cho người triển khai MBean, không phải một cơ chế tự động được Spring áp dụng cho mọi service.

## 20. Câu hỏi tự kiểm tra

1. \`@ManagedResource\` khác \`@Service\` ở đâu?
2. Tại sao một service được Spring quản lý không nên mặc nhiên trở thành MBean?
3. \`@ManagedAttribute\` trên getter trả API key tạo rủi ro gì?
4. Vì sao không thể dựa vào Spring Security web filter để bảo vệ operation JMX?
5. Management facade giúp thu hẹp bề mặt quản trị như thế nào?
6. Đọc \`MBeanInfo\` có ích gì hơn chỉ xem annotation trong source?
7. Nếu \`@ManagedResource\` bị xóa nhưng MBean vẫn tồn tại, có thể còn cơ chế export nào?
8. Vì sao remote JMX bị tắt không có nghĩa mọi dữ liệu trong MBean an toàn?
9. Một notification \`userData\` chứa raw payment request gây vấn đề gì?
10. Làm sao bảo đảm thêm method mới vào service không vô tình mở rộng JMX API?

## 21. Ghi nhớ

\`\`\`text
Spring @Service
   = đối tượng phục vụ nghiệp vụ

@ManagedResource
   = chỉ dấu tài nguyên quản trị JMX

@EnableMBeanExport + MBeanExporter
   = hạ tầng đăng ký MBean vào MBeanServer

@ManagedAttribute / @ManagedOperation
   = hợp đồng công bố cho JMX client

Management facade
   = lớp chọn lọc những gì thực sự cần expose
\`\`\`

**Nguyên tắc trọng tâm:** chỉ công bố qua JMX những dữ liệu và thao tác có mục đích quản trị rõ ràng. Giữ service nội bộ không bị export trực tiếp khi có thể, dùng facade nhỏ và đọc \`MBeanInfo\` để xác nhận bề mặt thực tế. Annotation giúp cấu hình thuận tiện, nhưng quyền truy cập và hậu quả của từng operation vẫn là trách nhiệm thiết kế của ứng dụng.