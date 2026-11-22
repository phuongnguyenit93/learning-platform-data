# Thay đổi domain khi tách mô-đun trong Spring Framework JMX

## 1. Bối cảnh

Trong JMX, mỗi MBean được định danh bằng một \`javax.management.ObjectName\` có cấu trúc:

\`\`\`text
domain:key1=value1,key2=value2,...
\`\`\`

Khi một ứng dụng Spring Framework được tách từ monolith thành các mô-đun hoặc dịch vụ độc lập, đội phát triển thường muốn tách cả **JMX domain** để phản ánh ownership rõ hơn. Ví dụ, trước đây tất cả MBeans nằm trong domain \`com.example.application\`, còn sau khi tách thành các phần \`orders\`, \`payments\` và \`inventory\`, có thể muốn sử dụng:

\`\`\`text
com.example.orders:type=Queue,name=Import
com.example.payments:type=Processor,name=Settlement
com.example.inventory:type=Cache,name=Catalog
\`\`\`

Thay đổi này tưởng như chỉ là đổi tên, nhưng thực tế là **thay đổi hợp đồng quản trị**: monitoring scripts, dashboards, cảnh báo, JMX notifications, automation tools và runbooks có thể đang phụ thuộc vào ObjectNames cũ. Nếu đổi domain thiếu kế hoạch, các client có thể tưởng MBean biến mất, không thu thập metrics hoặc gọi nhầm MBean.

Bài học tập trung vào cách thiết kế và triển khai domain migration an toàn khi chia tách ứng dụng.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt JMX domain, Spring module, Java package, Spring bean name và runtime process.
2. Xác định tác động của việc đổi domain đối với ObjectName và JMX client.
3. Lập kế hoạch migration từ domain monolith sang domain mô-đun.
4. Chọn chiến lược cutover trực tiếp, hỗ trợ tên cũ có thời hạn hoặc compatibility facade.
5. Cấu hình domain trong Spring JMX bằng \`@ManagedResource\`, \`MBeanExporter\` và naming strategy.
6. Kiểm soát tình huống hai MBeans cũ/mới đại diện cùng một tài nguyên.
7. Kiểm thử ObjectName, attributes, operations, registration lifecycle và client compatibility.
8. Thiết kế kế hoạch rollback, cảnh báo và truyền thông khi thay đổi management API.

## 2. Domain là gì, và không phải là gì?

ObjectName:

\`\`\`text
com.example.application:type=Queue,name=Import
\`\`\`

gồm:
- Domain: \`com.example.application\`.
- Key properties: \`type=Queue,name=Import\`.

JMX domain là một chuỗi định danh trong MBeanServer; nó **không tự tạo Java package, Spring ApplicationContext, network boundary hoặc security boundary**.

So sánh:

| Khái niệm | Mục đích | Có tự thay đổi khi đổi JMX domain? |
|---|---|---|
| Java package | Tổ chức source code | Không |
| Maven/Gradle module | Đơn vị build/dependency | Không |
| Spring bean name | Định danh bean trong ApplicationContext | Không |
| Spring ApplicationContext | Container quản lý Spring beans | Không |
| JMX domain | Thành phần của ObjectName | Có |
| JMX ObjectName | Định danh MBean trong MBeanServer | Có |
| JMX connector URL | Địa chỉ kết nối đến JMX server | Không bắt buộc |
| MBeanServer | Registry JMX | Không bắt buộc |
| Monitoring target | Endpoint mà collector truy vấn | Có thể cần cập nhật |

Ví dụ đổi:

\`\`\`text
com.example.application:type=Queue,name=Import
\`\`\`

thành:

\`\`\`text
com.example.orders:type=Queue,name=Import
\`\`\`

làm thay đổi **identity** của MBean ngay cả khi class Java, Java methods và dữ liệu bên trong không đổi.

## 3. Vì sao tách mô-đun thường dẫn đến đổi domain?

Trước khi tách:

\`\`\`text
Monolith JVM
  |
  +-- Orders module
  +-- Payments module
  +-- Inventory module
  |
  +-- Platform MBeanServer
        |
        +-- com.example.application:type=Queue,name=Import
        +-- com.example.application:type=Processor,name=Settlement
        +-- com.example.application:type=Cache,name=Catalog
\`\`\`

Sau khi tách:

\`\`\`text
Orders JVM                  Payments JVM                 Inventory JVM
  |                             |                             |
  +-- Orders MBeans             +-- Payments MBeans          +-- Inventory MBeans
  |                             |                             |
  +-- com.example.orders:*      +-- com.example.payments:*   +-- com.example.inventory:*
\`\`\`

Lợi ích của domain theo mô-đun:
- Phân biệt nhóm chịu trách nhiệm quản trị.
- Giúp client query đúng bộ MBeans.
- Tránh namespace mơ hồ khi có nhiều mô-đun trong cùng JVM.
- Dễ định nghĩa tài liệu quản trị cho mỗi domain.
- Có thể đồng bộ quy tắc đặt tên với application/team ownership.
- Giảm khả năng các modules vô tình dùng cùng ObjectName trong một MBeanServer.

Tuy nhiên không phải mọi lần tách module đều phải đổi domain. Nếu các client đang ổn định và domain cũ được công bố như một public contract, giữ domain cũ có thể ít rủi ro hơn. Tách code và đổi management API là hai thay đổi độc lập.

## 4. Tác động của việc đổi domain

Giả sử monitoring query cũ:

\`\`\`java
ObjectName oldPattern = new ObjectName(
    "com.example.application:*"
);

Set<ObjectName> names =
    connection.queryNames(oldPattern, null);
\`\`\`

Khi MBeans chuyển hết sang \`com.example.orders:*\`, truy vấn này không tìm ra các MBeans mới. Điều đó có thể dẫn đến:
- Metrics “biến mất” khỏi dashboard.
- Alert \`missing metrics\` hoặc \`service down\` giả.
- Scripts gọi \`isRegistered(oldName)\` trả false.
- Automation gọi \`getAttribute(oldName, ...)\` gặp \`InstanceNotFoundException\`.
- JConsole tree hiển thị domain khác.
- Event listeners đang gắn với ObjectName cũ không còn nhận notifications của MBean mới.
- Runbook và tài liệu vận hành không đúng.
- Historical timeseries bị chia làm hai khi monitoring labels chứa ObjectName.

**Đổi domain không phải thay đổi cosmetic.** Các client trực tiếp hoặc gián tiếp phụ thuộc ObjectName có thể bị ảnh hưởng.

## 5. Ba kịch bản tách mô-đun cần phân biệt

### Kịch bản A: Chỉ tách source code, vẫn cùng JVM

Các Maven modules được tách nhưng ứng dụng vẫn triển khai chung:

\`\`\`text
Monolith process
  |
  +-- orders.jar
  +-- payments.jar
  +-- inventory.jar
  |
  +-- one MBeanServer
\`\`\`

Khi này thay đổi domain giúp phân chia ownership và tránh collision, nhưng không phải điều kiện bắt buộc. MBeans và JMX connector có thể vẫn nằm ở cùng JVM.

### Kịch bản B: Tách thành các JVM/services riêng

Mỗi service có MBeanServer riêng. Khi đó cần xem cả:
- Domain/ObjectName mới.
- JMX connector URL mới.
- Firewall/credentials/network rules riêng.
- Collector discovery/configuration.
- Metrics labels và instance identity.

Một monitoring client dùng đúng domain mới nhưng vẫn kết nối đến JVM cũ cũng không thấy MBean. Domain migration và connector migration phải được phối hợp.

### Kịch bản C: Giai đoạn chuyển tiếp hybrid

Một số MBeans vẫn nằm trong monolith, một số đã chuyển sang service mới. Có thể tồn tại cùng lúc:
- Old domain trên monolith.
- New domain trên services.
- Cùng một logical resource được quan sát qua hai MBeans trong quá trình cutover.

Đây là kịch bản cần kiểm soát double-count metrics và duplicate administrative operations.

## 6. Lập inventory trước khi thay đổi

Trước migration, lập danh sách các MBeans hiện tại:

| Old ObjectName | Owner | Client phụ thuộc | Thao tác nhạy cảm | Proposed New ObjectName |
|---|---|---|---|---|
| \`com.example.application:type=Queue,name=Import\` | Orders | JConsole, collector | pause/resume | \`com.example.orders:type=Queue,name=Import\` |
| \`com.example.application:type=Processor,name=Settlement\` | Payments | Alerting, script | retrySettlement | \`com.example.payments:type=Processor,name=Settlement\` |
| \`com.example.application:type=Cache,name=Catalog\` | Inventory | Dashboard | clearCache | \`com.example.inventory:type=Cache,name=Catalog\` |

Với mỗi ObjectName:
1. Xác nhận MBean owner.
2. Liệt kê attributes và descriptions.
3. Liệt kê operations, parameters và side effects.
4. Liệt kê notification types và listeners.
5. Xác định current MBeanServer/connector endpoint.
6. Tìm tất cả monitoring clients và automation references.
7. Chọn new domain có cấu trúc ổn định.
8. Ghi lại deadline bỏ hỗ trợ tên cũ nếu cần.

Không chỉ grep source code: monitoring configuration, scripts, dashboard queries và runbooks có thể nằm ngoài repository ứng dụng.

## 7. Thiết kế domain mới

Một quy tắc có thể là:

\`\`\`text
<organization>.<application-or-module>:type=<Type>,name=<Name>[,instance=<Instance>]
\`\`\`

Ví dụ:

\`\`\`text
com.example.orders:type=Queue,name=Import
com.example.orders:type=Worker,name=Fulfillment
com.example.payments:type=Processor,name=Settlement
com.example.inventory:type=Cache,name=Catalog
\`\`\`

Nên tránh:
- Domain tùy tiện phụ thuộc class name được refactor.
- Domain chứa hostname động không có lý do.
- Domain thay đổi theo deployment ID khi client cần tên ổn định.
- Domain chứa customer ID hoặc thông tin bí mật.
- Domain có giá trị không được validate từ user input.
- Tạo quá nhiều domains khiến JConsole khó khám phá.

Nếu cần phân biệt môi trường, có thể dùng \`env=prod\` key hoặc collector target label. Domain mới không tự giải quyết việc phân biệt prod/staging/local.

### Domain là tên hợp đồng, không chỉ tên package

Package có thể đổi từ \`com.example.orders.impl\` sang \`com.example.orders.core\` mà management domain nên giữ \`com.example.orders\`. Điều đó giúp JMX clients không bị ảnh hưởng bởi refactor implementation.

## 8. Cách 1: Đổi @ManagedResource.objectName

Spring Framework JMX hỗ trợ:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedAttribute;

@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=Import",
    description = "Orders import queue monitoring"
)
public class ImportQueueMonitor {

    @ManagedAttribute(description = "Pending imports")
    public int getPendingCount() {
        return 42;
    }
}
\`\`\`

Ưu điểm:
- Tên rõ ngay trong source.
- MetadataNamingStrategy có thể dùng metadata được khai báo.
- Dễ hiểu cho MBean có một ObjectName cố định.

Hạn chế:
- Đây là Java annotation constant.
- Một class có thể được dùng ở nhiều môi trường hoặc nhiều instances.
- Đổi domain trong annotation cần deploy binary mới.
- Các scripts phụ thuộc tên cũ sẽ không tự được cập nhật.

**Cần nhớ:** Annotation không tự đăng ký MBean. Phải có Spring JMX exporter/annotation-driven configuration phù hợp, ví dụ \`@EnableMBeanExport\` hoặc XML \`<context:mbean-export/>\`.

## 9. Cách 2: Explicit MBeanExporter mapping

Với một Standard MBean:

\`\`\`java
public interface ImportQueueMonitorMBean {
    int getPendingCount();
}
\`\`\`

\`\`\`java
public class ImportQueueMonitor implements ImportQueueMonitorMBean {
    @Override
    public int getPendingCount() {
        return 42;
    }
}
\`\`\`

Có thể cấu hình:

\`\`\`java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxConfiguration {

    @Bean
    public MBeanExporter mBeanExporter(
            ImportQueueMonitor monitor) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
            "com.example.orders:type=Queue,name=Import",
            monitor
        ));
        exporter.setAutodetectMode(
            MBeanExporter.AUTODETECT_NONE
        );
        return exporter;
    }
}
\`\`\`

Khi migration, map trở thành nơi quản lý naming contract. Với annotation-based POJO phải bổ sung assembler/metadata source phù hợp; \`setBeans\` không tự chuyển mọi POJO thành annotated MBean có metadata đúng.

Khi ứng dụng Spring Boot đã có JMX auto-configuration, cần tránh vô tình tạo hai exporters cùng đăng ký một MBean dưới cùng ObjectName.

## 10. Cách 3: ObjectNamingStrategy tập trung

Khi các mô-đun có cùng convention nhưng domain riêng, một custom naming strategy có thể giúp thống nhất quy tắc.

\`\`\`java
import java.util.Map;
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;
import org.springframework.jmx.export.naming.ObjectNamingStrategy;

public final class ModuleNamingStrategy
        implements ObjectNamingStrategy {

    private final Map<String, String> domainsByBeanKey;

    public ModuleNamingStrategy(
            Map<String, String> domainsByBeanKey) {
        this.domainsByBeanKey = Map.copyOf(domainsByBeanKey);
    }

    @Override
    public ObjectName getObjectName(
            Object managedBean,
            String beanKey) throws MalformedObjectNameException {

        String domain = domainsByBeanKey.get(beanKey);
        if (domain == null) {
            throw new IllegalArgumentException(
                "No JMX domain mapping for " + beanKey
            );
        }

        return new ObjectName(
            domain + ":type=Queue,name=" + ObjectName.quote(beanKey)
        );
    }
}
\`\`\`

Ví dụ này minh họa dùng config mapping thay vì suy luận domain từ package/class runtime. Với hệ thống thực tế, cần mapping cả \`type\` và \`name\` theo business contract, không hardcode mọi MBean là Queue.

Không nên dựa vào \`managedBean.getClass().getPackageName()\` như nguồn duy nhất cho domain vì Spring AOP proxies và refactor implementation có thể làm thay đổi class runtime hoặc package.

## 11. Cutover trực tiếp

Phương án đơn giản nhất:
1. Đổi domain trong ứng dụng.
2. Cập nhật mọi monitoring clients/scripts.
3. Deploy theo kế hoạch.
4. Xác minh MBeans ở domain mới.
5. Ngừng dùng ObjectNames cũ.

Ưu điểm:
- Không có giai đoạn tên cũ và mới cùng tồn tại lâu.
- Ít phức tạp trong code.
- Giảm nguy cơ duplicate operations.

Nhược điểm:
- Các clients cũ có thể mất kết nối trong thời gian migration.
- Cần phối hợp deployment chặt.
- Một consumer bị bỏ sót có thể ngừng hoạt động.

Phù hợp khi:
- Số clients ít.
- Có quyền kiểm soát toàn bộ deployment.
- Có maintenance window và rollback rõ.
- Đã tìm đủ external dependencies.

## 12. Tương thích hai tên: có nên đăng ký alias?

Một ý tưởng phổ biến là export cùng tài nguyên dưới cả tên cũ và tên mới:

\`\`\`text
com.example.application:type=Queue,name=Import
com.example.orders:type=Queue,name=Import
\`\`\`

Về JMX, hai tên có thể cùng tồn tại trong một MBeanServer nếu đăng ký hợp lệ. Tuy nhiên phải đánh giá rủi ro:

- Metrics collector có thể thu hai series cho cùng logical resource.
- Operation như pause/resume có thể bị gọi từ cả hai endpoint.
- Notifications có thể bị quan sát lặp.
- Registration/unregistration lifecycle phức tạp hơn.
- Một exporter hoặc MBean implementation có thể không hỗ trợ đơn giản việc đăng ký cùng object instance dưới hai names theo cách giả định.
- Clients có thể không biết tên nào được khuyến nghị.

**Không mặc định “thêm alias là xong”.** Nếu cần compatibility, thiết kế một facade MBean riêng cho tên cũ, delegate có kiểm soát đến service mới, đồng thời công bố thời hạn deprecation.

### Compatibility facade

\`\`\`text
Old ObjectName
      |
      v
Deprecated compatibility MBean
      |
      v
Shared management service
      ^
      |
New MBean
      ^
      |
New ObjectName
\`\`\`

Để an toàn, có thể:
- Giữ attributes read-only trên alias.
- Hạn chế operations nhạy cảm ở alias.
- Đánh dấu description deprecated.
- Ghi log/audit các lần sử dụng alias.
- Có ngày ngừng hỗ trợ được thông báo.
- Chống double-count trong collectors.

Nếu yêu cầu compatibility chỉ là metrics, đôi khi cập nhật collector mapping tốt hơn đăng ký thêm một MBean alias.

## 13. Registry chính xác và MBeanServer lifecycle

Một MBean được đăng ký vào một MBeanServer cụ thể. Khi tách module:
- Monolith có thể dùng platform MBeanServer.
- Service mới có MBeanServer riêng.
- Mỗi process có connector URL khác.
- ObjectName cũ trên JVM cũ có thể tiếp tục tồn tại trong giai đoạn hybrid.

Một client truy vấn đúng new ObjectName trên old server vẫn có thể nhận \`InstanceNotFoundException\`.

Phải kiểm tra cả:
1. **Connection target**.
2. **MBeanServer identity**.
3. **ObjectName**.
4. **Registration status**.
5. **Management interface contract**.

Khi đóng Spring ApplicationContext, exporter cần unregister MBeans mà nó sở hữu theo lifecycle/configuration. Không để compatibility MBean còn tồn tại mà delegate đến service đã đóng.

## 14. Migration của notification listeners

Nếu một client đăng ký listener vào:

\`\`\`text
com.example.application:type=Queue,name=Import
\`\`\`

sau khi MBean chuyển sang:

\`\`\`text
com.example.orders:type=Queue,name=Import
\`\`\`

listener ở tên cũ không tự chuyển qua tên mới. Client cần:
- Kết nối đến đúng server mới.
- Tìm ObjectName mới.
- Đăng ký lại listener.
- Quản lý cleanup của listener cũ.
- Đọc snapshot trạng thái sau cutover.
- Không giả định notifications bị bỏ lỡ trong lúc chuyển được replay đầy đủ.

Nếu alias và MBean mới cùng phát notification cho cùng event, client cần phân biệt logical event ID hoặc tránh subscribe cả hai mà không kiểm soát duplicate processing.

## 15. Migration của operations có tác động

Các operations như:
- \`clearCache()\`.
- \`pauseWorker()\`.
- \`resumeWorker()\`.
- \`resetStatistics()\`.
- \`reloadConfiguration()\`.

có thể được gọi qua cả old/new naming trong giai đoạn migration. Cần quyết định:
- Endpoint nào là canonical?
- Có tắt write operations trên old alias không?
- Nếu remote timeout, client có retry sang tên mới không?
- Có idempotency key hoặc state check để tránh chạy hai lần không?
- Có audit và quyền tách biệt không?

Không được retry một operation có side effect trên domain mới chỉ vì gọi domain cũ timeout: server cũ có thể đã thực hiện operation nhưng response bị mất.

Đối với critical operations, việc chỉ cho phép thao tác ở new canonical MBean và giữ old name read-only có thể giảm rủi ro.

## 16. Migration của monitoring và metrics

Nếu metric identity bao gồm ObjectName, đổi domain có thể tạo time series mới.

Trước:
\`\`\`text
jmx_queue_pending{object_name="com.example.application:type=Queue,name=Import"} 12
\`\`\`

Sau:
\`\`\`text
jmx_queue_pending{object_name="com.example.orders:type=Queue,name=Import"} 12
\`\`\`

Mặc dù đây là cùng loại chỉ số, metrics backend có thể coi là hai series khác nhau.

Một số giải pháp:
- Dùng stable metric name và labels app/module/resource độc lập với raw ObjectName.
- Cập nhật collector mapping tại cutover.
- Đối chiếu thresholds/alerts trước và sau deploy.
- Tránh double-count khi cùng metric được scrape qua old/new alias.
- Ghi rõ thời điểm thay đổi để phân tích dashboards.
- Đảm bảo dashboards hiển thị dữ liệu lịch sử đúng ngữ nghĩa.

Khi module chuyển sang JVM khác, còn phải cập nhật target identity, instance labels và service discovery. Không giải quyết mọi thay đổi bằng cách chỉ sửa ObjectName domain.

## 17. Kiểm thử trước migration

### 17.1. Unit test mapping

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;

class ModuleDomainNamingTest {

    @Test
    void ordersUsesOrdersDomain() throws Exception {
        ObjectName name = new ObjectName(
            "com.example.orders:type=Queue,name=Import"
        );
        assertEquals("com.example.orders", name.getDomain());
        assertEquals("Queue", name.getKeyProperty("type"));
        assertEquals("Import", name.getKeyProperty("name"));
        assertFalse(name.isPattern());
    }
}
\`\`\`

### 17.2. Integration test registration

\`\`\`java
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = /* MBeanServer used by Spring exporter */ null;

ObjectName newName = new ObjectName(
    "com.example.orders:type=Queue,name=Import"
);

if (!server.isRegistered(newName)) {
    throw new AssertionError("New MBean name is missing");
}
\`\`\`

Trong test thật, thay placeholder bằng MBeanServer lấy từ ApplicationContext hoặc server được cấu hình cho exporter. Không suy đoán platform server nếu Spring dùng custom MBeanServer.

### 17.3. Kiểm tra MBeanInfo

\`\`\`java
var info = server.getMBeanInfo(newName);
for (var attr : info.getAttributes()) {
    System.out.println(attr.getName() + ": " + attr.getType());
}
for (var op : info.getOperations()) {
    System.out.println(op.getName());
}
\`\`\`

Đối chiếu management interface cũ/mới:
- Attributes cần thiết có được giữ?
- Read/write flags có thay đổi không?
- Operations có chữ ký và semantics phù hợp không?
- Notifications và descriptions có bị mất không?
- Những thay đổi khác có được intentional/documented không?

## 18. Contract test cho clients

Một test hữu ích hơn chỉ \`isRegistered()\` là thực hiện quy trình client:

1. Kết nối với đúng JVM/service.
2. Query new ObjectName.
3. Đọc một read-only attribute quan trọng.
4. Kiểm tra MBeanInfo.
5. Thử subscription notification nếu ứng dụng có.
6. Xác nhận client automation không còn dùng old domain.
7. Với alias, xác nhận old name chỉ cung cấp những khả năng được phép.
8. Xác minh reconnect khi endpoint/service mới restart.

Đối với operation làm thay đổi trạng thái, chỉ test trên môi trường staging/test. Không thực hiện operations phá dữ liệu thật chỉ để xác minh migration.

## 19. Quan sát domain cũ còn được sử dụng hay không

Nếu có giai đoạn tương thích, nên đo việc sử dụng old name để biết đã có thể xóa.

Những nguồn quan sát:
- Monitoring collector configuration.
- Logs từ compatibility facade.
- Audit của admin operations.
- Inventory của scripts/clients.
- Dashboard/alert query references.
- Số lần subscription listener trên old endpoint nếu hệ thống đo được.

Không phải JMX server nào cũng có sẵn số liệu “client nào gọi MBean cũ” ở mức chi tiết. Muốn ghi nhận có thể cần facade riêng hoặc instrumentation ở connector/application layer.

Một chính sách deprecation có thể là:
- Công bố ngày bắt đầu và kết thúc hỗ trợ.
- Đánh dấu MBean cũ deprecated trong description.
- Theo dõi usage trong giai đoạn chuyển tiếp.
- Cập nhật runbooks và client libraries.
- Xóa alias khi các consumer đã được chuyển đổi.

## 20. Rollback khi migration lỗi

Cần phân biệt:
- **Rollback naming:** trở lại domain cũ.
- **Rollback service split:** chuyển module về monolith.
- **Rollback collector:** đưa monitoring query về tên cũ.

Không phải ba việc luôn cần rollback cùng lúc.

Một kế hoạch thực dụng:
1. Giữ bản cấu hình mapping cũ và mới.
2. Có release/version cho naming contract.
3. Có smoke test JMX để phát hiện thiếu MBeans ngay sau deploy.
4. Có cách đưa collector quay về domain cũ khi cần.
5. Không hủy old compatibility path trước khi xác minh clients.
6. Kiểm tra dữ liệu duplicate hoặc missing trong monitoring.
7. Cân nhắc downtime cần thiết với operations không thể chạy song song.

Nếu rolling deployment khiến một số instances dùng domain cũ và một số dùng domain mới, collectors có thể cần hỗ trợ song song có kiểm soát trong thời gian ngắn.

## 21. Security khi đổi domain

Domain không phải cơ chế authentication/authorization. Khi module chuyển sang service mới, bề mặt remote JMX có thể thay đổi:
- Một connector mới mở thêm network endpoint.
- Credentials và access roles mới.
- MBeanServer chứa tập MBeans khác.
- Một operation từng chỉ có local access nay được remote exposure.
- Alias cũ có thể trở thành đường truy cập ít được review.

Vì vậy cần xem migration như thay đổi **security topology**, không chỉ naming:
- Bảo vệ connector.
- Giới hạn interface mạng.
- Kiểm tra TLS/credentials và quyền.
- Review operations nhạy cảm.
- Không expose secrets trong attributes.
- Tách quyền monitoring read-only với admin invoke.
- Ghi audit cho thao tác production khi phù hợp.

Việc domain có chữ \`payments\` không ngăn caller truy cập MBean nếu connector security cho phép.

## 22. Những sai lầm thường gặp

**Sai lầm 1: “Đổi Java package đồng nghĩa phải đổi JMX domain.”**  
Không. Domain là management contract độc lập và nên ổn định.

**Sai lầm 2: “Đổi domain không ảnh hưởng behavior.”**  
Management clients dùng ObjectName cũ có thể không hoạt động.

**Sai lầm 3: “Một ObjectName mới tự xuất hiện ở client kết nối JVM cũ.”**  
Không. Connection target và server registry cũng phải đúng.

**Sai lầm 4: “Giữ cả hai tên luôn an toàn.”**  
Có thể double-count metrics, duplicate notifications và gọi operations hai lần.

**Sai lầm 5: “Chỉ cần sửa exporter, không cần sửa dashboards.”**  
Monitoring clients, alert rules và runbooks có thể phụ thuộc domain cũ.

**Sai lầm 6: “Có thể dùng REPLACE_EXISTING để chuyển domain.”**  
RegistrationPolicy xử lý collision trong cùng ObjectName, không chuyển client từ tên cũ sang tên mới.

**Sai lầm 7: “Cứ dùng getClass().getPackageName() là naming ổn định.”**  
Refactor, proxy hoặc thay đổi package làm management contract biến động.

**Sai lầm 8: “Notification listeners tự chuyển sang new ObjectName.”**  
Không. Client cần re-register listener và refresh state.

**Sai lầm 9: “Đổi domain là đủ khi tách service.”**  
Còn connector, network, credentials, target discovery, lifecycle và metrics mapping.

**Sai lầm 10: “Domain mới bảo mật hơn vì tên riêng.”**  
Tên không phải security boundary; quyền do connector/application policy kiểm soát.

## 23. Kế hoạch migration theo bước

### Bước 1 — Inventory

- Liệt kê tất cả old ObjectNames.
- Xác nhận owners.
- Xác định clients, dashboards, scripts, alerts và notifications.
- Đánh giá operations nguy hiểm.

### Bước 2 — Thiết kế domain mới

- Chọn domain theo ownership logic.
- Giữ key properties ổn định nếu có thể.
- Xác định naming cho instance/environment.
- Đặt version/deprecation policy nếu cần.

### Bước 3 — Chọn chiến lược compatibility

- Cutover trực tiếp nếu consumer nhỏ và kiểm soát được.
- Compatibility facade khi phải hỗ trợ client cũ.
- Collector mapping nếu chỉ cần giữ metrics continuity.
- Không tự đăng ký aliases cho mọi MBean mà không review.

### Bước 4 — Triển khai code/config

- Cập nhật annotation, exporter mapping hoặc naming strategy.
- Kiểm tra đúng MBeanServer.
- Tránh exporter duplication.
- Bảo đảm management interface và lifecycle không thay đổi ngoài ý muốn.

### Bước 5 — Kiểm thử

- Unit test ObjectName.
- Integration test MBean registration.
- Contract test attributes/operations/notifications.
- End-to-end test collector hoặc JMX client.
- Kiểm tra access controls.

### Bước 6 — Cutover và giám sát

- Deploy theo thứ tự có kiểm soát.
- Xác minh MBeans new domain tồn tại.
- Theo dõi gaps/double-count trong metrics.
- Theo dõi usage old alias.
- Cập nhật runbooks.

### Bước 7 — Dọn dẹp có kế hoạch

- Chỉ gỡ old domain/alias sau khi clients đã chuyển.
- Ghi rõ thay đổi trong release notes.
- Loại bỏ compatibility code khi không còn cần.
- Tiếp tục kiểm tra ObjectNames trong smoke tests.

## 24. Ví dụ runbook

\`\`\`text
Migration: com.example.application -> com.example.orders

Before:
  1. Confirm inventory for orders MBeans.
  2. Verify monitoring queries support new domain.
  3. Check access to new JMX connector.
  4. Freeze changes to JMX operations during migration.

Deploy:
  1. Deploy orders module/service.
  2. Query com.example.orders:* on correct server.
  3. Read PendingCount on Queue Import.
  4. Inspect MBeanInfo.
  5. Verify collector sees expected metrics.

After:
  1. Check alerting and dashboard continuity.
  2. Confirm no duplicate metric ingestion.
  3. Validate only intended old aliases remain.
  4. Record outcome and deprecation deadline.

Rollback:
  1. Restore prior connector/collector mapping if needed.
  2. Roll back application naming configuration when appropriate.
  3. Confirm old ObjectNames are registered.
  4. Re-run safe read-only smoke tests.
\`\`\`

## 25. Bài tập thực hành

### Bài A: Inventory và mapping

1. Cho ba MBeans trong \`com.example.application\`.
2. Phân loại owner orders/payments/inventory.
3. Đề xuất ba domain mới.
4. Ghi đầy đủ old/new ObjectNames.
5. Liệt kê ba nhóm clients cần cập nhật.

### Bài B: Spring JMX code migration

1. Tạo \`@ManagedResource\` trong domain cũ.
2. Đổi ObjectName sang domain orders.
3. Bật annotation JMX export.
4. Khởi động Spring context.
5. \`queryNames()\` và \`isRegistered()\` xác minh domain mới.

### Bài C: Client compatibility

1. Viết client query domain cũ.
2. Đổi MBean domain.
3. Quan sát \`InstanceNotFoundException\` hoặc empty query result.
4. Sửa client sang domain mới.
5. Thử migration bằng compatibility facade nếu cần.

### Bài D: Duplicate metric

1. Export hai MBeans cũ/mới cho một logical resource trong môi trường test.
2. Cấu hình collector thu cả hai.
3. Quan sát series trùng hoặc double-count.
4. Thiết kế collector mapping tránh trùng.
5. Quy định thời hạn gỡ alias.

### Bài E: Remote service split

1. Chuyển MBean sang JVM thử nghiệm khác.
2. Thay JMXServiceURL trong client.
3. Dùng domain mới.
4. Đọc attributes qua \`MBeanServerConnection\`.
5. Xác minh security và listener registration.

## 26. Câu hỏi tự kiểm tra

**Câu 1.** Đổi JMX domain có đồng nghĩa đổi Java package không?  
**Trả lời:** Không. Hai khái niệm độc lập.

**Câu 2.** Tại sao đổi domain có thể làm monitoring mất dữ liệu?  
**Trả lời:** Collectors/scripts có thể query ObjectNames cũ.

**Câu 3.** Domain mới có giúp bảo mật MBeans không?  
**Trả lời:** Không trực tiếp. Bảo mật phụ thuộc connector và quyền truy cập.

**Câu 4.** Có nên luôn đăng ký old/new aliases cùng lúc?  
**Trả lời:** Không. Cần đánh giá double-count, duplicate notifications, side effects và lifecycle.

**Câu 5.** Khi module chuyển sang JVM khác, đổi domain đã đủ chưa?  
**Trả lời:** Chưa. Phải cập nhật connector URL, network/security và target discovery.

**Câu 6.** Listener đăng ký old ObjectName có tự nhận notification của new ObjectName không?  
**Trả lời:** Không. Client cần đăng ký lại theo tên/server mới.

**Câu 7.** Vì sao nên dùng management facade cho compatibility?  
**Trả lời:** Để giữ hợp đồng cũ có kiểm soát, giảm rủi ro expose trùng operations và có thể ghi nhận deprecation.

**Câu 8.** Khi nào nên gỡ old domain?  
**Trả lời:** Sau khi xác nhận các clients đã chuyển, monitoring ổn định và deprecation policy được đáp ứng.

## 27. Ghi nhớ

- JMX domain là một thành phần của ObjectName và của management API contract.
- Tách source module **không buộc** đổi domain, nhưng có thể là cơ hội chuẩn hóa ownership.
- Đổi domain ảnh hưởng JMX clients, scripts, alerts, dashboards và notification listeners.
- Với service split, phải xử lý cả connector target và security topology, không chỉ ObjectName.
- Chọn cutover trực tiếp hoặc compatibility facade theo số lượng clients và mức rủi ro.
- Không mặc định alias kép là an toàn; có thể double-count metrics hoặc duplicate operations.
- Cần kiểm thử MBeanInfo, ObjectName, registration lifecycle và client contract.
- Ghi kế hoạch rollback và deprecation deadline trước khi triển khai.
- Domain mới là tên, không phải security boundary.
- Duy trì ObjectName ổn định sau migration để các client vận hành không phụ thuộc refactor nội bộ.

### Tài liệu tham khảo

- Spring Framework Reference — JMX Exporting: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Javadoc — \`MetadataNamingStrategy\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/naming/MetadataNamingStrategy.html
- Java SE 21 API — \`ObjectName\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
- Java SE 21 API — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
