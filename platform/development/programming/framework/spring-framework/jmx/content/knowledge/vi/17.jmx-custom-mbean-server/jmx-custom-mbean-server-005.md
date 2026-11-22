# Chia sẻ MBeanServer giữa nhiều Spring ApplicationContext

## Mục tiêu học tập

Trong Java Management Extensions (JMX), một **MBeanServer** là registry và điểm truy cập quản trị: các MBean được đăng ký bằng \`ObjectName\`, rồi được client truy vấn, đọc attribute, gọi operation hoặc nhận notification. Trong Spring Framework, mỗi \`ApplicationContext\` có thể tạo \`MBeanExporter\` riêng. Một JVM đồng thời có thể chứa nhiều context: parent/child context, web và batch context, nhiều module, integration test, application nhúng hoặc các context được tạo/đóng động.

Khi các context cần chia sẻ **cùng một MBeanServer**, bài toán không đơn thuần là inject chung một object. Cần xác định quyền sở hữu server, miền tên JMX, registration ownership, thứ tự khởi tạo và shutdown, hành vi khi một context restart, cùng ranh giới bảo mật và vận hành.

Sau bài học, bạn có thể:

- Phân biệt chia sẻ MBeanServer với chia sẻ Spring bean và chia sẻ JMX connector.
- Cấu hình nhiều ApplicationContext sử dụng cùng platform MBeanServer hoặc server tùy biến.
- Quy định namespace \`ObjectName\` cho các context để tránh collision.
- Tách vòng đời server khỏi vòng đời exporter và từng MBean registration.
- Hiểu giới hạn của parent/child context, bean visibility và độc lập giữa các sibling context.
- Xử lý \`InstanceAlreadyExistsException\`, hot reload, context refresh và test song song.
- Kiểm chứng MBean nằm trong đúng server và chỉ bị gỡ bởi context sở hữu.
- Thiết kế topology phù hợp khi cần isolation thay vì chia sẻ.

## 1. Mô hình tư duy: ba vòng đời khác nhau

Một MBeanServer có thể được dùng bởi nhiều context nhưng thường **không thuộc riêng một context con nào**.

\`\`\`text
JVM
│
├── Shared MBeanServer
│   ├── java.lang:type=Memory
│   ├── com.example.web:type=Health,name=Api
│   ├── com.example.batch:type=Worker,name=Import
│   └── com.example.shared:type=Cache,name=Catalog
│
├── Parent ApplicationContext
│   ├── Bean MBeanServer (reference tới shared server)
│   └── Shared infrastructure
│
├── Web ApplicationContext
│   ├── WebMonitor
│   └── MBeanExporter(web) ── register/unregister WebMonitor
│
└── Batch ApplicationContext
    ├── BatchMonitor
    └── MBeanExporter(batch) ── register/unregister BatchMonitor
\`\`\`

Khi Web context đóng, exporter của nó cần gỡ những MBean mà nó thực sự sở hữu. **MBeanServer vẫn tiếp tục sống**, và MBean của Batch context vẫn phải còn. Khi Batch context restart, nó có thể đăng ký lại những ObjectName của chính mình sau khi registration cũ đã được dọn.

Phân biệt:

| Đối tượng | Chức năng | Chủ sở hữu vòng đời |
|---|---|---|
| \`MBeanServer\` | Registry chung | JVM hoặc hạ tầng/shared owner |
| Spring \`ApplicationContext\` | Container bean của module | Module/runtime quản lý context |
| \`MBeanExporter\` | Đăng ký các MBean được chọn | Context tạo exporter |
| Registration \`ObjectName -> MBean\` | Một entry quản trị | Exporter hoặc component đã register |
| \`JMXConnectorServer\` | Cho phép client kết nối từ xa | Hạ tầng khởi động connector |

Cùng dùng một server không có nghĩa các context cùng sở hữu mọi MBean trên đó. Một exporter không được gỡ tên chỉ vì tên có cùng domain nếu registration đó thuộc thành phần khác.

## 2. Khi nào nên chia sẻ server?

Một shared MBeanServer phù hợp khi:

1. Các module chạy **trong cùng một JVM** và cần được quan sát từ một JMX connector.
2. Bộ công cụ vận hành muốn thấy JVM MXBean và MBean của nhiều module cùng một nơi.
3. Namespace quản trị đủ rõ để phân biệt các module/instance.
4. Các context có vòng đời độc lập nhưng có thể quản lý đăng ký đối xứng.
5. Không có yêu cầu cách ly bảo mật cứng buộc các module phải dùng endpoint hoặc process riêng.

Các trường hợp đáng cân nhắc **server riêng**:

- Một plugin/tenant phải cô lập bề mặt quản trị theo mô hình truy cập và lifecycle được thiết kế rõ.
- Có runtime/container quản lý nhiều registry và connector khác nhau.
- Một module cần test hoặc thực nghiệm mà không tác động registry của phần còn lại.
- Có khả năng xung đột contract JMX không thể giải quyết chỉ bằng namespace.

Dù dùng server riêng, server vẫn nằm trong **cùng JVM**; điều đó tự nó không tạo sandbox hay quyền bảo mật tương đương process isolation. Connector và policy truy cập phải được cấu hình riêng.

## 3. Chọn server chung: platform hay tùy biến?

### 3.1 Platform MBeanServer

Java cung cấp:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

MBeanServer shared = ManagementFactory.getPlatformMBeanServer();
\`\`\`

Platform server là lựa chọn phổ biến khi ứng dụng muốn thống nhất với các MXBean chuẩn của JVM. Nhiều context có thể giữ reference tới object này. Gọi \`getPlatformMBeanServer()\` từ nhiều context trong cùng JVM không tạo các server platform độc lập cho từng context.

Điều cần nhớ: platform MBeanServer thuộc phạm vi JVM; đừng release nó khi một Spring context con đóng.

### 3.2 Server tùy biến tạo một lần

Nếu cần server riêng được dùng chung:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer shared =
    MBeanServerFactory.createMBeanServer("com.example.runtime");
\`\`\`

Server này cần được tạo **một lần** bởi shared owner và chuyển reference đến các context sử dụng. Nếu mỗi context tự gọi \`createMBeanServer\`, bạn đã tạo nhiều registry khác nhau, không còn “chia sẻ server”.

\`MBeanServerFactory.createMBeanServer\` tạo server được factory theo dõi. Shared owner có thể release nó khi toàn bộ consumers và connectors đã dừng:

\`\`\`java
MBeanServerFactory.releaseMBeanServer(shared);
\`\`\`

Lời gọi release không tự đóng mọi thread, connector, bean hoặc các resource khác. Các component sở hữu chúng phải cleanup riêng. Không gọi release trên server không thuộc quyền quản lý của owner, và không xem \`releaseMBeanServer\` là lệnh xóa mọi MBean an toàn.

## 4. Cấu hình parent/child context: một bean server tại parent

Nếu các context con có chung parent, hãy để parent cung cấp server:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ParentJmxConfiguration {

    @Bean
    public MBeanServer sharedMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }
}
\`\`\`

Web context và Batch context dùng bean \`sharedMBeanServer\` từ parent, nếu bean visibility và injection được thiết kế phù hợp. Trong mô hình Spring context hierarchy, child có thể tra cứu bean từ parent; parent không tự nhìn thấy toàn bộ bean riêng ở child, và hai sibling context không tự trao đổi bean với nhau.

Ví dụ exporter của Web context:

\`\`\`java
import java.util.Map;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class WebJmxConfiguration {

    @Bean
    public MBeanExporter webExporter(
            MBeanServer sharedMBeanServer,
            WebHealthMBeanAdapter webHealth) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(sharedMBeanServer);
        exporter.setBeans(Map.of(
            "com.example.web:type=Health,name=Api", webHealth
        ));
        exporter.setAutodetect(false);
        return exporter;
    }
}
\`\`\`

Exporter của Batch context:

\`\`\`java
@Configuration
public class BatchJmxConfiguration {

    @Bean
    public MBeanExporter batchExporter(
            MBeanServer sharedMBeanServer,
            BatchWorkerMBeanAdapter batchWorker) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(sharedMBeanServer);
        exporter.setBeans(Map.of(
            "com.example.batch:type=Worker,name=Import", batchWorker
        ));
        exporter.setAutodetect(false);
        return exporter;
    }
}
\`\`\`

Các adapter trong ví dụ là management beans hợp lệ: Standard MBean/MXBean hoặc bean được exporter xử lý bằng assembler phù hợp. Để các đoạn mã chạy trong dự án, phải khai báo đầy đủ adapter và interface quản trị tương ứng. Cấu hình chọn explicit \`setBeans\` và tắt autodetection để giữ tập MBean của từng module rõ ràng.

**Điểm chính:** cả hai exporter nhận cùng reference \`sharedMBeanServer\`, nhưng mỗi exporter chỉ đăng ký một danh sách ObjectName thuộc module của mình.

## 5. Không có parent chung: đưa reference vào mỗi context

Hai sibling context hoặc hai \`ApplicationContext\` độc lập không tự động chia sẻ bean qua dependency injection. Có thể:

- Tạo server ở bootstrap/root owner rồi truyền reference cho từng context.
- Đăng ký một reference cùng object vào mỗi context trước khi refresh.
- Dùng platform MBeanServer làm điểm hội tụ nếu phù hợp.
- Có một shared configuration/factory được bootstrap cấp cùng server thay vì mỗi nơi tự tạo.

Một skeleton với Spring \`AnnotationConfigApplicationContext\`:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

MBeanServer shared = ManagementFactory.getPlatformMBeanServer();

AnnotationConfigApplicationContext web =
    new AnnotationConfigApplicationContext();

AnnotationConfigApplicationContext batch =
    new AnnotationConfigApplicationContext();

web.getBeanFactory().registerSingleton("sharedMBeanServer", shared);
batch.getBeanFactory().registerSingleton("sharedMBeanServer", shared);

web.register(WebJmxConfiguration.class);
batch.register(BatchJmxConfiguration.class);

web.refresh();
batch.refresh();
\`\`\`

Trong ứng dụng thật, mỗi context còn cần cấu hình các adapter, service và dependency phù hợp. Bootstrap owner phải đóng context khi shutdown; chỉ đăng ký cùng reference chưa tự định nghĩa cleanup registration hay server release.

Đặc biệt tránh:

\`\`\`java
@Bean
public MBeanServer sharedMBeanServer() {
    return MBeanServerFactory.createMBeanServer();
}
\`\`\`

trong **nhiều** context độc lập nếu mong muốn dùng một server; mỗi lần gọi factory sẽ tạo một server khác. Nếu dùng platform server, \`ManagementFactory.getPlatformMBeanServer()\` có thể gọi từ nhiều context nhưng vẫn phải bảo đảm exporter thực sự được cấu hình dùng platform server đó.

## 6. Server bean và exporter server là hai cấu hình riêng

Chỉ tạo một Spring bean kiểu \`MBeanServer\` không bảo đảm mọi exporter tự dùng nó nếu có nhiều candidate hoặc exporter đã được cấu hình tự chọn một server khác. Thiết kế nên chỉ định rõ:

\`\`\`java
exporter.setServer(sharedMBeanServer);
\`\`\`

Hoặc với annotation-driven export:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport(
    server = "sharedMBeanServer",
    defaultDomain = "com.example.web"
)
public class WebAnnotationExportConfiguration {
}
\`\`\`

Trong \`@EnableMBeanExport\`, giá trị \`server\` là **tên Spring bean** kiểu \`MBeanServer\`, không phải hostname hay port kết nối remote. Với \`MBeanExporter.setServer\`, tham số là reference tới object \`MBeanServer\`.

Phải bảo đảm các exporter annotation ở nhiều context không cùng export một bean hoặc cùng ObjectName. Dùng \`@ManagedResource(objectName = "...")\` tường minh khi cần hợp đồng tên ổn định.

### 6.1 defaultDomain không thay MBeanServer

Hai exporter cùng dùng server nhưng có \`defaultDomain\` khác nhau vẫn là chia sẻ registry. \`defaultDomain\` ảnh hưởng cách naming strategy tạo ObjectName khi không có domain tường minh; nó không di chuyển registration sang server mới.

Nếu hai bean đều khai báo:

\`\`\`java
@ManagedResource(
    objectName = "com.example.shared:type=Worker,name=Import")
\`\`\`

thì đổi \`defaultDomain\` ở một exporter sẽ không giải quyết xung đột cùng ObjectName. Cần sửa tên công bố hoặc phân định một owner.

## 7. ObjectName là khóa duy nhất trong mỗi server

MBeanServer dùng \`ObjectName\` như registry key. Hai context cùng đăng ký:

\`\`\`text
com.example:type=Worker,name=Main
\`\`\`

vào cùng server sẽ tạo collision. Lỗi có thể thể hiện qua \`InstanceAlreadyExistsException\` hoặc chính sách registration đã cấu hình. Không nên áp dụng “replace” mặc định vì exporter A có thể thay MBean của B và sau đó context A shutdown lại dọn entry B đang cần.

Thiết kế tên có định danh phạm vi:

\`\`\`text
com.example.web:type=Health,name=Api
com.example.batch:type=Worker,name=Import
com.example.shared:type=Cache,name=Catalog
\`\`\`

Nếu có hai instance giống nhau **trong cùng JVM**, có thể thêm key \`instance\` hoặc \`context\`:

\`\`\`text
com.example.batch:type=Worker,name=Import,instance=primary
com.example.batch:type=Worker,name=Import,instance=secondary
\`\`\`

Khi nhiều JVM khác nhau dùng cùng ObjectName, không xung đột vì registry tách biệt; monitoring có thể cần gắn thêm identity của JVM/node ở tầng thu thập.

Các key property phải được encode theo cú pháp \`ObjectName\`. Tránh đưa token, user ID hoặc dữ liệu nhạy cảm vào tên MBean.

## 8. Một registration, một owner

Mấu chốt khi chia sẻ server là **ownership**:

| Thành phần | Quyền cần có |
|---|---|
| Server owner | Tạo, cấu hình, quản lý connector và release server riêng khi không còn consumer |
| Web exporter | Đăng ký/gỡ MBean thuộc Web context |
| Batch exporter | Đăng ký/gỡ MBean thuộc Batch context |
| Shared infrastructure exporter | Đăng ký/gỡ MBean dùng chung thuộc shared owner |
| Monitoring client | Đọc/gọi theo quyền; không sở hữu server |

Không dùng \`queryNames("com.example:*")\` rồi unregister tất cả khi một context dừng. Domain là namespace logic, không phải bằng chứng ownership. Một context chỉ nên dọn danh sách đăng ký **chính nó đã tạo thành công** hoặc exporter của nó quản lý.

Nếu dùng Spring \`MBeanExporter\`, exporter thường gỡ những đăng ký của nó khi bị destroy. Với code register thủ công bằng \`MBeanServer.registerMBean\`, component sở hữu cần ghi nhận thành công rồi gỡ khi đóng.

Ví dụ:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.JMException;

public final class OwnedRegistration implements AutoCloseable {

    private final MBeanServer server;
    private final ObjectName name;
    private boolean registered;

    public OwnedRegistration(MBeanServer server, ObjectName name, Object mbean)
            throws JMException {
        this.server = server;
        this.name = name;
        server.registerMBean(mbean, name);
        registered = true;
    }

    @Override
    public void close() throws JMException {
        if (registered) {
            server.unregisterMBean(name);
            registered = false;
        }
    }
}
\`\`\`

Đây là minh họa single-owner, không phải implementation concurrency hoàn chỉnh. Trong production, nếu có nhiều luồng hoặc khả năng thay registration giữa các thao tác, cần đồng bộ/lifecycle policy đủ mạnh. Không để component khác overwrite mục sau khi owner đã register rồi vẫn cố gỡ theo tên khi shutdown.

## 9. Startup nhiều context và trật tự phụ thuộc

Một bootstrap nhiều context có thể gồm:

\`\`\`text
1. Tạo MBeanServer shared (hoặc lấy platform server)
2. Tạo shared context hoặc cung cấp reference
3. Tạo Web context + exporter riêng
4. Tạo Batch context + exporter riêng
5. Khởi động JMX connector nếu cần
6. Kiểm tra các ObjectName dự kiến trên đúng server
\`\`\`

Không bắt buộc mọi hệ thống theo đúng một thứ tự trên, nhưng phải bảo đảm **server tồn tại trước exporter cần nó** và **connector không được coi là điều kiện duy nhất để MBeanServer hoạt động**.

Nếu một context fail khi startup:

- Đảm bảo những registration đã thành công được dọn bởi owner của chúng.
- Không release shared server chỉ vì một module thất bại.
- Các context khác tiếp tục sử dụng registry nếu hợp đồng runtime cho phép.
- Lỗi \`InstanceAlreadyExistsException\` cần chẩn đoán ObjectName và exporter, không được xử lý bằng xóa toàn domain.

### 9.1 Readiness của MBean khác readiness của service

Một MBean được register có thể xuất hiện trên JConsole trước khi module phục vụ nghiệp vụ sẵn sàng. Vì thế nên công bố \`LifecycleState\`, \`RequestedState\`, \`EffectiveState\` hoặc readiness summary khi cần, thay vì dùng \`server.isRegistered(name)\` làm tín hiệu service healthy.

Getter JMX nên có chi phí thấp. Không để một thao tác chẩn đoán nặng trong getter làm trì hoãn bootstrap hoặc tuyến xử lý quan trọng.

## 10. Shutdown và restart độc lập

Giả sử Web context được redeploy, Batch context vẫn đang chạy:

\`\`\`text
Shared MBeanServer: sống
Web Context A:      RUNNING → CLOSED → new Web Context A'
Batch Context B:    RUNNING → RUNNING
\`\`\`

Hành vi mong muốn:

1. Web exporter A unregister \`com.example.web:...\` do A sở hữu.
2. Batch MBean và shared MBean vẫn tồn tại.
3. Web context A' đăng ký lại đúng tên khi sẵn sàng.
4. Shared MBeanServer không bị release trong quá trình redeploy.
5. Client quản trị có thể thấy Web MBean tạm thời biến mất và xuất hiện lại; đây có thể là lifecycle hợp lệ.

Nếu Web context mới startup khi Web context cũ chưa unregister, collision có thể xảy ra. Giải pháp là đồng bộ handoff hoặc dùng namespace theo instance/generation có chủ đích, thay vì tự động thay thế MBean của context cũ mà chưa rõ quyền sở hữu.

Với một server tùy biến, chỉ shared owner mới nên release sau khi các context/connector thực sự ngừng sử dụng. Nếu server được tạo bởi \`MBeanServerFactory.createMBeanServer\`, cần phân biệt release factory tracking với cleanup resource của các component.

## 11. JMX connector có vòng đời độc lập

Một \`MBeanServer\` không tự mở cổng remote. \`JMXConnectorServer\` có thể cung cấp endpoint tới một server cụ thể.

\`\`\`text
JMX client ── network ── JMXConnectorServer
                               |
                               v
                        Shared MBeanServer
                         /             \
                  Web MBeans         Batch MBeans
\`\`\`

Chỉ cần **một connector** nếu kiến trúc và quyền phù hợp cho mọi MBean trong shared server. Không nên để mỗi context tự start connector trên cùng port; có thể gây lỗi bind hoặc tạo các endpoint không nhất quán.

Nếu quyền của các nhóm người dùng khác nhau, phải kiểm tra authentication/authorization của connector. Tách ObjectName domain không tự áp dụng phân quyền; người có quyền JMX phù hợp có thể truy cập MBean thuộc nhiều domain. Một server riêng cũng không thay thế access control hay network isolation.

Không để JMX endpoint không được bảo vệ mở ra Internet. Các operation điều khiển trên MBean có thể tác động trực tiếp tới trạng thái ứng dụng.

## 12. Các loại topology context thường gặp

### 12.1 Parent/child context

\`\`\`text
Parent
  ├── sharedMBeanServer
  ├── sharedMonitor
  └── Child Web / Child Batch
\`\`\`

Child có thể nhìn thấy bean từ parent. Hãy chú ý nếu \`MBeanExporter\` ở parent đang autodetect bean; phạm vi cụ thể phụ thuộc BeanFactory/exporter. Không nên giả định parent exporter có thể quản lý mọi bean ở child, hoặc hai child exporter tự chia sẻ registration ownership.

Cách đơn giản là exporter riêng cho module với explicit beans, server bean ở parent.

### 12.2 Các context độc lập

Không có parent chung, nhưng cùng nhận server qua bootstrap hoặc dùng platform server. Các context không tự chia sẻ Spring bean; chỉ **reference tới MBeanServer** là dùng chung. Không cố inject bean module A trực tiếp vào B chỉ vì MBean của A xuất hiện trong registry.

### 12.3 Application nhiều module cùng một context

Nếu mọi module trong một ApplicationContext, có thể dùng một exporter có danh sách explicit hoặc nhiều exporter phân quyền theo nhóm. Nhiều exporter tăng độ phức tạp collision/lifecycle; ưu tiên thiết kế đơn giản khi không có nhu cầu phân định owner riêng.

### 12.4 Integration test dùng chung JVM

Nhiều test có thể tạo và đóng context liên tục, đặc biệt khi test chạy parallel. Platform MBeanServer được chia sẻ nên một \`ObjectName\` cố định có thể xung đột giữa test. Có thể dùng server riêng mỗi test hoặc namespace test duy nhất, cleanup trong finally và tránh xóa những MBean không thuộc test.

## 13. Chẩn đoán MBean không xuất hiện trong JConsole

Các nguyên nhân phổ biến:

| Hiện tượng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| Web MBean thấy, Batch MBean không | Batch exporter dùng server khác | So sánh server reference |
| MBean đăng ký thành công nhưng JConsole không thấy | Connector đang trỏ sang registry khác | Kiểm tra connector/server |
| Startup một context lỗi collision | Hai exporter dùng cùng ObjectName | Kiểm tra tên, owner, policy |
| Web shutdown làm Batch MBean mất | Có component unregister nhầm/replace registration | Kiểm tra code cleanup và ownership |
| Context reload rồi MBean không quay lại | Exporter mới chưa chạy hoặc context cũ chưa cleanup | Kiểm tra lifecycle và log |
| JConsole có MBean nhưng operation lỗi | Service chưa ready, signature sai hoặc quyền không đủ | Kiểm tra MBeanInfo/effective state |
| Hai module hiện cùng domain | Naming strategy/defaultDomain quá chung | Thiết kế lại namespace |

Đừng sửa lỗi “mất MBean” bằng cách tạo thêm một \`MBeanServer\` bừa bãi. Trước tiên hãy xác định MBean đã đăng ký vào **server nào** và JMX client kết nối qua connector nào.

## 14. Kiểm tra registry và metadata trên đúng server

Ví dụ:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.MBeanInfo;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

Set<ObjectName> webNames = server.queryNames(
    new ObjectName("com.example.web:*"), null);

Set<ObjectName> batchNames = server.queryNames(
    new ObjectName("com.example.batch:*"), null);

System.out.println("Web MBeans = " + webNames);
System.out.println("Batch MBeans = " + batchNames);

for (ObjectName objectName : batchNames) {
    MBeanInfo info = server.getMBeanInfo(objectName);
    System.out.println(objectName + " -> " + info.getClassName());
}
\`\`\`

Đây là truy vấn platform server; nếu chia sẻ một server tùy biến, truyền reference server đó thay vì gọi \`getPlatformMBeanServer()\`. Kết quả \`queryNames\` là snapshot tại thời điểm đọc, không phải bảo đảm trạng thái không thay đổi khi context đang restart.

Một kiểm tra sau khi Web context đóng:

\`\`\`java
assertTrue(server.queryNames(
    new ObjectName("com.example.web:*"), null).isEmpty());

assertFalse(server.queryNames(
    new ObjectName("com.example.batch:*"), null).isEmpty());
\`\`\`

Hai assertion trên chỉ phù hợp khi fixture test thực sự chỉ có Web MBean thuộc Web context và Batch MBean thuộc Batch context trong các domain tương ứng. Trong production có thể có MBean khác thuộc các domain đó; nên assert đúng những ObjectName do fixture sở hữu.

## 15. Integration test: đóng một context không làm mất MBean của context khác

Một fixture cần tạo server chung rồi khởi động hai context khác nhau, xác minh registration và shutdown:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class SharedMBeanServerTest {

    @Test
    void closingWebContextKeepsBatchMBean() throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();

        ObjectName webName = new ObjectName(
            "com.example.web:type=Health,name=Api");
        ObjectName batchName = new ObjectName(
            "com.example.batch:type=Worker,name=Import");

        AnnotationConfigApplicationContext web =
            new AnnotationConfigApplicationContext();
        AnnotationConfigApplicationContext batch =
            new AnnotationConfigApplicationContext();

        try {
            web.getBeanFactory().registerSingleton(
                "sharedMBeanServer", server);
            batch.getBeanFactory().registerSingleton(
                "sharedMBeanServer", server);

            web.register(WebJmxConfiguration.class);
            batch.register(BatchJmxConfiguration.class);

            web.refresh();
            batch.refresh();

            assertTrue(server.isRegistered(webName));
            assertTrue(server.isRegistered(batchName));

            web.close();

            assertFalse(server.isRegistered(webName));
            assertTrue(server.isRegistered(batchName));
        } finally {
            web.close();
            batch.close();
        }
    }
}
\`\`\`

Để chạy, cần có các \`WebHealthMBeanAdapter\` và \`BatchWorkerMBeanAdapter\` hợp lệ, được đăng ký trong context tương ứng. Các tên phải không xung đột với test chạy song song. Mục tiêu của test là xác minh **lifecycle ownership**, không phải tạo một fixture đầy đủ cho mọi module ứng dụng.

Trong hệ thống có nhiều context phức tạp, nên test thêm:
- Restart một context trong khi context khác còn chạy.
- Hai exporter cố tình đăng ký trùng ObjectName và startup bị từ chối rõ ràng.
- Không có duplicate MBean sau refresh.
- Connector (nếu có) vẫn sống khi một consumer context đóng.
- Server tùy biến chỉ release khi shared owner kết thúc.

## 16. Các sai lầm cần tránh

### 16.1 Mỗi context tạo một server mới nhưng nghĩ rằng đang chia sẻ

\`\`\`java
@Bean
MBeanServer server() {
    return MBeanServerFactory.createMBeanServer();
}
\`\`\`

Nếu config được khởi tạo độc lập ở nhiều context, mỗi context có registry khác nhau. Giải pháp: platform server hoặc một bootstrap owner tạo rồi inject cùng reference.

### 16.2 Cùng domain là cùng owner

Hai MBean \`com.example:type=Worker,name=A\` và \`com.example:type=Worker,name=B\` có thể thuộc hai context. Không được unregister tất cả theo domain khi một context shutdown.

### 16.3 Dùng registration policy replace để chữa collision

Có thể che lỗi namespace hoặc làm context này thay MBean của context kia. Hãy sửa ownership, ObjectName và thứ tự lifecycle.

### 16.4 Gắn connector lifecycle vào từng module context

Một module dừng có thể vô tình làm mọi JMX client mất kết nối, dù MBeanServer và các module khác vẫn sống. Connector chung nên có owner với vòng đời đủ dài.

### 16.5 Chỉ định defaultDomain rồi coi server tự chia sẻ

Default domain là naming concern; lựa chọn server là một quyết định khác. Hai exporter có domain giống nhau nhưng server khác nhau vẫn không chia sẻ registry.

### 16.6 Đăng ký MBean thủ công nhưng không unregister

Một context có thể đóng nhưng MBean entry vẫn giữ reference tới bean cũ, gây rò rỉ và collision khi khởi động lại. Cần cleanup đối xứng theo ownership.

### 16.7 Cho mọi MBean vào chung server mà không kiểm soát quyền

JMX là bề mặt quản trị mạnh. Chia sẻ server khiến nhiều MBean xuất hiện tại một nơi, nên authentication, authorization, TLS, mạng quản trị và audit càng quan trọng.

## 17. Runbook thiết kế và vận hành

### Trước khi triển khai

1. Chọn rõ **platform server** hay **shared custom server**.
2. Xác định **shared owner** của server và connector.
3. Ghi lại mỗi context/exporter quản lý nhóm MBean nào.
4. Đặt namespace \`ObjectName\` có định danh module/instance khi cần.
5. Bật export explicit hoặc annotation có chọn lọc, tránh tự động xuất cùng bean bởi nhiều exporter.
6. Bảo vệ JMX endpoint và phân loại operation có side effect.
7. Viết integration test cho startup, shutdown và restart độc lập.

### Khi startup

1. Đảm bảo server reference sẵn sàng trước exporter.
2. Quan sát exception đăng ký, đặc biệt \`InstanceAlreadyExistsException\`.
3. Đọc \`MBeanServer.queryNames\` trên đúng server.
4. Kiểm tra các ObjectName được công bố và MBeanInfo.
5. Kiểm tra connector trỏ đúng server nếu dùng remote JMX.

### Khi shutdown

1. Đóng context theo dependency thực tế.
2. Mỗi exporter unregister những MBean mình đã đăng ký.
3. Không release server khi context khác còn sử dụng.
4. Shared owner dừng connector, cleanup và release custom server nếu có quyền và cần thiết.
5. Xác minh không còn registration stale và không gỡ nhầm MBean của module khác.

## 18. Bài tập vận dụng

**Bài 1 — Parent/child.** Parent context cung cấp platform MBeanServer. Web child và Batch child mỗi nơi có MBeanExporter. Hãy mô tả cách inject cùng server và chọn namespace sao cho Web shutdown không ảnh hưởng Batch.

**Bài 2 — Custom server.** Hai context độc lập mỗi nơi gọi \`MBeanServerFactory.createMBeanServer()\`. Vì sao JConsole chỉ thấy một phần MBean khi kết nối tới một connector? Cần tạo server một lần rồi truyền reference đến cả hai.

**Bài 3 — Collision.** Hai exporter cùng đăng ký \`com.example:type=Worker,name=Main\` vào platform server. Hãy đề xuất ObjectName mới và giải thích vì sao chính sách replace không phải lời giải mặc định.

**Bài 4 — Ownership.** Khi Web context đóng, code gọi \`queryNames("com.example:*")\` rồi unregister tất cả. Chỉ ra rủi ro và thay bằng cleanup những registration thuộc Web exporter.

**Bài 5 — Testing.** Viết integration test tạo hai context dùng cùng server, assert cả hai MBean tồn tại, đóng một context rồi assert MBean còn lại vẫn sống.

**Bài 6 — Remote connector.** Nêu ba lý do một MBean đăng ký thành công nhưng remote JMX client không thấy: connector trỏ server khác, client kết nối sai JVM, ObjectName thực tế khác kỳ vọng.

## Tổng kết

**Chia sẻ MBeanServer giữa nhiều Spring ApplicationContext** là việc để các exporter của nhiều context đăng ký vào **cùng một registry JMX**, chứ không phải hợp nhất Spring bean graph hay đồng nhất vòng đời của các context. Thiết kế đúng cần một owner cho server chung, exporter/registration owner cho từng module, ObjectName duy nhất trong registry, cleanup đối xứng và connector có vòng đời độc lập. Platform MBeanServer giúp chia sẻ đơn giản trong một JVM; server tùy biến chỉ nên tạo một lần và release bởi shared owner sau khi mọi consumer kết thúc. Với cơ chế này, nhiều context có thể được quan sát chung mà vẫn khởi động, dừng và redeploy độc lập, không xóa nhầm MBean của nhau.
