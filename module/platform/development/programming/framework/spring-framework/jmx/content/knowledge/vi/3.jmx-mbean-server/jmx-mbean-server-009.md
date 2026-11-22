# Quản lý vòng đời MBeanServer trong ứng dụng Spring Framework

## Mục tiêu học tập

\`MBeanServer\` là trung tâm của một **JMX agent** trong JVM: nơi đăng ký, tra cứu và gọi các MBean quản trị. Với Spring Framework, khó khăn không chỉ là “lấy được một \`MBeanServer\`” mà còn là xác định **ai tạo**, **ai sở hữu**, **ai đăng ký MBean**, **ai dọn dẹp khi dừng**, và điều gì xảy ra khi ứng dụng được khởi động lại trong cùng JVM.

Sau bài này, bạn có thể:

- Phân biệt vòng đời của \`MBeanServer\`, Spring \`ApplicationContext\`, MBean được export và JMX connector từ xa.
- Quyết định khi nào nên dùng platform \`MBeanServer\`, tìm server đã có hoặc tạo server riêng.
- Giải thích vai trò của Spring \`MBeanServerFactoryBean\`, \`MBeanExporter\` và các cơ chế hủy đăng ký.
- Thiết kế cách đăng ký, gỡ đăng ký và kiểm tra \`ObjectName\` để tránh trùng lặp và rò rỉ tài nguyên.
- Xử lý startup/shutdown, context refresh, triển khai nhiều context, test suite và ứng dụng nhúng.
- Phân biệt trạng thái vòng đời được xác nhận với kỳ vọng dựa trên một lệnh gọi hoặc cấu hình.

## 1. Mô hình tư duy: MBeanServer là registry có vòng đời JVM, không mặc định trùng với vòng đời Spring

Trong JMX, một \`MBeanServer\` quản lý bảng ánh xạ giữa \`ObjectName\` và đối tượng MBean được đăng ký. Client quản trị dùng \`MBeanServerConnection\` để truy vấn metadata, đọc attribute, gọi operation và nhận notification theo khả năng của MBean.

Mô hình đơn giản:

\`\`\`text
JVM
├── Platform MBeanServer (có thể dùng chung)
│   ├── java.lang:type=Memory
│   ├── java.lang:type=Threading
│   ├── domain.application:type=Cache,name=ProductCache
│   └── domain.application:type=Worker,name=ImportWorker
│
├── Spring ApplicationContext A
│   ├── Spring bean: CacheMonitor
│   └── MBeanExporter A ── đăng ký/gỡ MBean của A
│
├── Spring ApplicationContext B
│   ├── Spring bean: WorkerMonitor
│   └── MBeanExporter B ── đăng ký/gỡ MBean của B
│
└── JMX Connector (tùy chọn)
    └── Cung cấp truy cập từ xa tới một MBeanServer
\`\`\`

Các vòng đời liên quan nhưng **không đồng nhất**:

| Thành phần | Thường được tạo khi nào? | Ai chịu trách nhiệm dọn dẹp? |
|---|---|---|
| Platform \`MBeanServer\` | Qua \`ManagementFactory.getPlatformMBeanServer()\` hoặc được runtime khởi tạo khi cần | JVM/runtime; application context thường không hủy server này |
| \`MBeanServer\` riêng | Khi ứng dụng/khung quản trị chủ động tạo | Thành phần sở hữu server; có thể release qua \`MBeanServerFactory\` nếu được factory quản lý |
| Spring \`ApplicationContext\` | Khi bootstrap ứng dụng | Cơ chế đóng context; gọi destroy/disposable callbacks |
| \`MBeanExporter\` | Khi context tạo bean export | Exporter thường dọn các đăng ký do nó quản lý khi bị destroy |
| MBean | Khi được đăng ký dưới một \`ObjectName\` | Thành phần đã đăng ký/nhận quyền sở hữu đăng ký |
| JMX connector | Khi endpoint quản trị được khởi động | Thành phần khởi động connector phải stop/close connector đúng cách |

Hãy luôn hỏi: **“Tài nguyên này thuộc JVM, Spring context, exporter hay dịch vụ hạ tầng nào?”** Không trả lời được câu này thường dẫn đến hai lỗi ngược nhau: không dọn registry khi đóng context hoặc vô tình hủy một server dùng chung.

## 2. Các con đường lấy MBeanServer và ý nghĩa vòng đời

### 2.1 Dùng platform MBeanServer

Đây là lựa chọn tự nhiên khi cần dùng chung nơi JVM công bố các MXBean nền tảng về memory, threads, garbage collection, class loading và runtime:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
\`\`\`

Đặc điểm quan trọng:

- Gọi lại \`getPlatformMBeanServer()\` cho phép truy cập platform server của cùng JVM; đừng xem mỗi lần gọi là một server mới thuộc người gọi.
- Có thể đăng ký MBean ứng dụng vào server này bằng \`ObjectName\` riêng.
- Khi một \`ApplicationContext\` dừng, không được tự ý release server dùng chung chỉ để xóa MBean ứng dụng.
- Nhiều Spring context và thư viện có thể cùng đăng ký MBean trên một platform server. Namespace và ownership là điều kiện tiên quyết.

Ví dụ tên phù hợp:

\`\`\`text
com.example.orders:type=Worker,name=ImportWorker,instance=node-01
\`\`\`

Tên thực tế cần ổn định, đủ duy nhất trong phạm vi \`MBeanServer\` và không chứa dữ liệu nhạy cảm hoặc giá trị ngẫu nhiên thay đổi vô cớ. \`ObjectName\` có cú pháp riêng; sử dụng \`new ObjectName(...)\` để kiểm tra tên, không tự giả định mọi chuỗi đều hợp lệ.

### 2.2 Tạo MBeanServer riêng

JMX cung cấp factory cho server:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer isolated = MBeanServerFactory.createMBeanServer("com.example.isolated");
try {
    // Đăng ký và quản lý các MBean thuộc phạm vi này.
} finally {
    MBeanServerFactory.releaseMBeanServer(isolated);
}
\`\`\`

\`createMBeanServer\` đưa server mới vào danh sách do \`MBeanServerFactory\` theo dõi; \`releaseMBeanServer\` giải phóng server khỏi danh sách đó. Đây **không phải lời hứa** rằng mọi MBean, callback, JMX connector hoặc tài nguyên thread đều tự đóng. Phần mềm sở hữu các thành phần đó vẫn phải dọn chúng và ngừng cung cấp kết nối trước khi release.

Ngoài ra, \`newMBeanServer\` tạo server mà factory không giữ trong danh sách được tra cứu theo cùng cách; không được mặc định gọi \`releaseMBeanServer\` trên server được tạo bằng con đường khác.

Tạo server riêng hữu ích khi cần cách ly registry hoặc kiểm thử thành phần độc lập. Tuy nhiên, việc tạo nhiều server làm tăng nhu cầu định tuyến đúng \`MBeanServerConnection\`; MBean trên server A không tự xuất hiện ở server B.

### 2.3 Tìm server đang tồn tại

Ứng dụng tích hợp có thể muốn tìm server JMX sẵn có của runtime/container. \`MBeanServerFactory.findMBeanServer(null)\` liệt kê các server được factory theo dõi, còn \`ManagementFactory.getPlatformMBeanServer()\` truy cập platform server.

Không nên lấy “phần tử đầu tiên” của danh sách tìm được mà coi đó là lựa chọn đúng. Trong một JVM có thể có nhiều server, với các domain và đối tượng khác nhau. Cần xác định hợp đồng cấu hình: chọn platform server hay một server được runtime/container chỉ định.

## 3. Spring MBeanServerFactoryBean: cấu hình tìm hoặc tạo server

Spring hỗ trợ \`org.springframework.jmx.support.MBeanServerFactoryBean\` để đưa một \`MBeanServer\` vào bean graph. Bean factory có thể tìm server hiện có hoặc tạo server theo cấu hình. Đây là một cách tường minh để quản lý dependency JMX tại tầng Spring.

Ví dụ cấu hình dùng platform server như một dependency:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JmxServerConfiguration {

    @Bean
    public MBeanServer mbeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }
}
\`\`\`

Ưu điểm của cách trên là ý định sử dụng platform server rất rõ. Bean \`mbeanServer\` chỉ là **reference** đến tài nguyên JVM; không được mặc định coi Spring là chủ sở hữu có quyền release tài nguyên đó. Nếu quản lý server riêng bằng \`MBeanServerFactoryBean\`, cấu hình cần xác định mục đích tìm/tạo và vòng đời đóng cho đúng phiên bản Spring đang dùng.

Một cấu hình khai báo factory:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.support.MBeanServerFactoryBean;

@Configuration
public class IsolatedJmxConfiguration {

    @Bean
    public MBeanServerFactoryBean applicationMBeanServerFactory() {
        MBeanServerFactoryBean factory = new MBeanServerFactoryBean();
        factory.setDefaultDomain("com.example.application");
        // Với thiết kế thực tế, chọn rõ chế độ tìm server đã có
        // hoặc tạo server mới theo hợp đồng runtime.
        return factory;
    }
}
\`\`\`

\`setDefaultDomain\` đặt domain mặc định cho server được tạo, **không thay thế** namespace \`ObjectName\` của từng MBean và không tự đảm bảo không trùng tên. Cần kiểm tra các thuộc tính lựa chọn server của \`MBeanServerFactoryBean\` theo version Spring Framework được triển khai. Khi không cần cô lập, cấu hình platform server thường đơn giản hơn.

## 4. Vòng đời đăng ký MBean: create → register → expose → unregister

Dù server đã tồn tại, một MBean chỉ xuất hiện khi có bước **register** với \`ObjectName\`. Có hai cách phổ biến:

1. Đăng ký trực tiếp bằng \`MBeanServer.registerMBean\` và tự chịu trách nhiệm \`unregisterMBean\`.
2. Để Spring \`MBeanExporter\` đăng ký các bean và thực hiện cleanup cho những đăng ký mà exporter sở hữu.

### 4.1 Đăng ký thủ công: owner phải có hành động đối xứng

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.*;
import java.util.concurrent.atomic.AtomicLong;

public interface QueueStatsMBean {
    long getCompleted();
}

public final class QueueStats implements QueueStatsMBean {
    private final AtomicLong completed = new AtomicLong();
    @Override public long getCompleted() {
        return completed.get();
    }
    public void recordCompleted() {
        completed.incrementAndGet();
    }
}

public final class ManualRegistration implements AutoCloseable {
    private final MBeanServer server;
    private final ObjectName objectName;
    private boolean registered;

    public ManualRegistration() throws Exception {
        this.server = ManagementFactory.getPlatformMBeanServer();
        this.objectName = new ObjectName(
            "com.example.app:type=QueueStats,name=ImportQueue");
        server.registerMBean(new QueueStats(), objectName);
        registered = true;
    }

    @Override
    public void close() throws JMException {
        if (registered) {
            server.unregisterMBean(objectName);
            registered = false;
        }
    }
}
\`\`\`

Ví dụ trên minh họa tài nguyên đăng ký, không phải một tiện ích concurrency production-ready. Nếu nhiều luồng có thể gọi \`close\` hoặc quản lý \`register\`, cần đồng bộ hóa và kiểm tra ownership. Quan trọng hơn, không viết logic “nếu tên tồn tại thì unregister” một cách mù quáng: tên đó có thể thuộc thành phần khác. Chỉ dọn các MBean được instance của bạn đăng ký thành công.

Nếu \`registerMBean\` ném \`InstanceAlreadyExistsException\`, nguyên nhân có thể là trùng \`ObjectName\`, context cũ chưa cleanup hoặc ứng dụng khác đang dùng cùng tên. Đây là dấu hiệu cần xác định owner, **không** phải lý do tự xóa mục có sẵn.

### 4.2 Để Spring MBeanExporter quản lý

Spring \`MBeanExporter\` giúp ánh xạ Spring beans thành MBean trực tiếp hoặc thông qua annotation metadata. Khái niệm:

\`\`\`text
ApplicationContext khởi động
  ↓
Tạo bean nghiệp vụ
  ↓
MBeanExporter lấy bean + ObjectName
  ↓
Đăng ký vào MBeanServer được cấu hình
  ↓
JMX client quan sát/thao tác
  ↓
ApplicationContext đóng
  ↓
Exporter dọn đăng ký do nó quản lý
\`\`\`

Ví dụ dùng annotation:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.app:type=QueueStats,name=ImportQueue",
    description = "Read-only queue statistics")
public class QueueMetrics {
    private volatile long completed;

    @ManagedAttribute
    public long getCompleted() {
        return completed;
    }
}
\`\`\`

Kích hoạt annotation-driven JMX export khi phù hợp:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxExportConfiguration {
}
\`\`\`

Trong Spring Boot, hãy kiểm tra cấu hình JMX auto-configuration thực tế để tránh tạo đồng thời nhiều exporter đăng ký cùng MBean. \`@ManagedResource\` chỉ mô tả MBean, không tự đảm bảo đã được đăng ký nếu cơ chế export chưa hoạt động. Các application context con/cha cũng có thể cùng quét hoặc export những bean khác nhau; thiết kế cần phân định owner cho từng \`ObjectName\`.

### 4.3 Chính sách khi trùng ObjectName

Spring \`MBeanExporter\` hỗ trợ chính sách đăng ký cho tình huống tên đã tồn tại (ví dụ: bỏ qua mục hiện có, thay thế hoặc từ chối, tùy cấu hình/API phiên bản). Dùng chính sách đúng phải bắt đầu từ ownership:

| Tình huống | Hành vi mong muốn |
|---|---|
| Cùng một context đăng ký cùng tên hai lần do lỗi cấu hình | Phát hiện và sửa cấu hình |
| Context A và B cùng dùng server nhưng thuộc hai instance khác nhau | Đặt tên duy nhất và ổn định cho mỗi instance |
| MBean của runtime/container đã tồn tại | Không overwrite để “giải quyết” xung đột |
| Hot reload tạo context mới khi context cũ chưa đóng | Đồng bộ trình tự shutdown/startup; kiểm tra owner |
| Tái đăng ký có chủ đích khi thay phiên bản component | Thiết kế handoff, thời điểm unregister/register và xử lý client |

Chính sách “replace” có thể có hiệu ứng đến MBean thuộc bên khác; không nên chọn chỉ để làm hết lỗi startup.

## 5. Một máy trạng thái vòng đời đơn giản

Có thể hình dung trạng thái đăng ký của một MBean như sau:

\`\`\`text
NEW
 └── tạo bean thành công → READY
                           ├── register thành công → REGISTERED
                           │                           ├── dùng qua JMX
                           │                           └── unregister → REMOVED
                           └── register thất bại → FAILED
\`\`\`

\`REGISTERED\` nghĩa là registry có một entry tại tên đã chọn; nó không đảm bảo mọi operation đều hoạt động khỏe, connector từ xa đang mở, hoặc dependency nghiệp vụ sẵn sàng. Tương tự, \`REMOVED\` nghĩa là entry đã bị gỡ khỏi server, không có nghĩa object Java đã bị GC ngay lập tức hay thread do object tạo đã dừng.

Đối với \`MBeanServer\` riêng:

\`\`\`text
SERVER_CREATED → MBEANS_REGISTERED → CONNECTOR_STARTED
                         ↓                    ↓
                 UNREGISTER_OWNED ← CONNECTOR_STOPPED
                         ↓
                  SERVER_RELEASED
\`\`\`

Trình tự cụ thể phụ thuộc runtime, nhưng điểm bất biến là **ngừng cung cấp truy cập quản trị rồi dọn những gì mình sở hữu trước khi giải phóng server**. Nếu chỉ dùng platform server, bước \`SERVER_RELEASED\` không thuộc trách nhiệm ứng dụng.

## 6. Khởi động: dependency, thứ tự và khả năng quan sát

Một startup có thể gồm:

1. Chọn/lấy \`MBeanServer\` mục tiêu.
2. Khởi tạo bean nghiệp vụ có dữ liệu quản trị.
3. Đăng ký MBean bằng exporter hoặc cơ chế tự quản.
4. Khởi động connector nếu thực sự cần truy cập từ xa và cấu hình cho phép.
5. Kiểm tra trạng thái đã đăng ký và readiness của chức năng quản trị.

Nếu một MBean được đăng ký trước khi bean nghiệp vụ hoàn toàn sẵn sàng, một JMX client có thể đọc được MBean nhưng operation lại thất bại. Điều này cần được nêu trong hợp đồng: \`registered\` khác \`ready\`.

Đừng dùng một getter JMX để “lười khởi tạo” những dependency nặng trong lần đọc đầu; việc quan sát khi ứng dụng vừa khởi động có thể vô tình kích hoạt công việc nặng. Nếu muốn lộ trạng thái khởi động, nên cung cấp attribute read-only như \`LifecycleState\` và \`LastStartupError\` có chi phí đọc thấp.

Khi startup fail giữa chừng, cần đảm bảo cleanup đối xứng. Ví dụ exporter đăng ký được MBean A nhưng thất bại ở MBean B do trùng tên, hệ thống cần biết những registration nào đã hoàn tất và phải dọn trong luồng phá hủy context. Không tự suy luận rằng exception startup tự động xóa mọi entry của thư viện ngoài do code tự register.

## 7. Shutdown: đóng context không có nghĩa dừng JVM

Các ứng dụng trong cùng JVM có thể có nhiều context, test context hoặc cơ chế redeploy. Khi một context đóng, cần phân biệt:

- **MBean do context đăng ký**: phải được gỡ khi component sở hữu kết thúc vòng đời.
- **MBean của context khác**: phải giữ nguyên.
- **Platform MXBean**: tiếp tục tồn tại theo JVM.
- **Connector được chia sẻ**: chỉ component thực sự sở hữu mới được stop.
- **MBeanServer riêng do context tạo**: có thể được giải phóng sau khi ngừng connector và cleanup phù hợp.
- **Thread, executor, timer, scheduled task của MBean**: cần shutdown riêng theo hợp đồng của resource; unregister không tự thay thế destroy.

Một bean Spring tự đăng ký MBean có thể dùng \`@PostConstruct\` / \`@PreDestroy\` hoặc các cơ chế \`InitializingBean\` / \`DisposableBean\`. Với Spring Framework 6 và Jakarta EE, các annotation lifecycle tương ứng thuộc \`jakarta.annotation\`, không phải \`javax.annotation\`.

Ví dụ owner của một registration:

\`\`\`java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import javax.management.*;
import java.lang.management.ManagementFactory;
import org.springframework.stereotype.Component;

@Component
public class OwnedQueueMBeanRegistration {
    private final MBeanServer server = ManagementFactory.getPlatformMBeanServer();
    private final ObjectName name;
    private boolean registered;

    public OwnedQueueMBeanRegistration() throws MalformedObjectNameException {
        name = new ObjectName("com.example.app:type=Queue,name=LocalQueue");
    }

    @PostConstruct
    public void register() throws JMException {
        server.registerMBean(new LocalQueueStats(), name);
        registered = true;
    }

    @PreDestroy
    public void unregister() throws JMException {
        if (registered) {
            server.unregisterMBean(name);
            registered = false;
        }
    }
}
\`\`\`

Ở đây \`LocalQueueStats\` là một MBean hợp lệ do ứng dụng định nghĩa riêng, với interface theo quy ước Standard MBean hoặc hình thức JMX tương ứng. Không được đăng ký trùng chính object này qua \`MBeanExporter\` nữa. Nếu startup lỗi trước khi \`registered\` được đặt thành true, cần xử lý tình huống lỗi giữa đăng ký và cập nhật cờ nếu có logic bổ sung, thay vì gỡ tên của thành phần khác.

Với shutdown hooks, tránh tự đăng ký nhiều hook gây gọi cleanup trùng. Phần lớn ứng dụng Spring Boot đã có cơ chế shutdown context; cấu hình riêng phải hiểu rõ lifecycle đang có.

## 8. JMX connector: một vòng đời độc lập

\`MBeanServer\` là registry trong JVM; kết nối từ xa không tự tồn tại chỉ vì server được tạo. Một JMX connector server có thể được khởi động riêng, ví dụ qua \`JMXConnectorServerFactory\`, hoặc do JVM/container cung cấp. Quản lý connector gồm endpoint, xác thực, mã hóa, mạng, port và cleanup.

\`\`\`text
MBeanServer (registry)
    ↑
JMXConnectorServer (remote endpoint)
    ↑
JMXConnector/JMX client
\`\`\`

Nếu connector đang chạy nhưng application context đã gỡ các MBean của nó, client có thể vẫn kết nối được đến server và chỉ nhìn thấy các MBean còn lại. Nếu connector dừng nhưng registry vẫn sống, các client in-process vẫn có thể truy cập server trực tiếp. Hai trạng thái này khác nhau.

Khi tự quản connector, owner phải gọi \`stop()\` khi shutdown và đảm bảo client không còn dựa vào endpoint đã đóng. Không nhầm việc release \`MBeanServer\` với đóng socket/connector; một connector có thể giữ tài nguyên của riêng nó.

Về an toàn, không công khai cổng JMX trên Internet. Phải cấu hình xác thực, phân quyền, TLS/mạng bảo vệ và kiểm tra endpoint thực tế. Lệnh JMX có thể tác động sâu vào JVM, không chỉ đọc metric.

## 9. Nhiều context trong cùng JVM: ai sở hữu tên?

Một máy chủ ứng dụng có thể có parent/child context; các test integration có thể tái dùng JVM; hệ thống module có thể load/unload context động. Nếu hai context đăng ký:

\`\`\`text
com.example.app:type=Cache,name=Catalog
\`\`\`

vào cùng server, tên sẽ xung đột trừ khi cấu hình chủ động xử lý. Cần có quy tắc tên dựa trên logic deployment:

\`\`\`text
com.example.app:type=Cache,name=Catalog,context=publicApi
com.example.app:type=Cache,name=Catalog,context=batchWorker
\`\`\`

Nếu JVM chạy nhiều instance tương tự, thêm \`instance\` ổn định trong vòng đời process khi thật sự cần. Nếu chạy trên nhiều JVM riêng, mỗi server có namespace độc lập; không bắt buộc đưa hostname vào mọi \`ObjectName\`, nhưng nó có thể giúp định danh khi tập hợp kết quả quản trị.

Quy tắc ownership tối thiểu:

- Component đăng ký thành công thì có quyền và trách nhiệm gỡ mục đó.
- Component không đăng ký mục nào không được xóa theo tên chỉ vì nó trông “cũ”.
- Mọi tên đều có kế hoạch xử lý khi hot reload hoặc context restart.
- Server dùng chung có lifetime dài hơn context; cleanup không được xóa các registration khác.

## 10. Kiểm tra vòng đời bằng API JMX

Các API hữu ích:

\`\`\`java
boolean registered = server.isRegistered(objectName);
ObjectInstance instance = server.getObjectInstance(objectName);
Set<ObjectName> names = server.queryNames(
    new ObjectName("com.example.app:*"), null);
\`\`\`

Dùng \`isRegistered\` hoặc \`queryNames\` để quan sát registry, nhưng nhớ rằng đây là snapshot: kết quả có thể đổi ngay sau khi đọc. Trong hoạt động concurrent, không viết code kiểu “đọc thấy chưa đăng ký rồi chắc chắn register thành công”; lời gọi \`registerMBean\` vẫn có thể gặp race và ném exception.

Khi kiểm tra sau shutdown:

1. Các \`ObjectName\` do context sở hữu không còn trong registry.
2. MBean của context khác và platform MXBean vẫn còn nếu server tiếp tục sống.
3. Connector của context nếu có đã dừng.
4. Không còn worker thread hoặc executor thuộc resource đã dừng.
5. Context mới có thể đăng ký lại cùng tên mà không cần xóa mục “ma” bằng tay.

Đối với automated test, dùng namespace độc lập hoặc \`MBeanServer\` riêng khi phù hợp, đóng context sau test và assert trạng thái registration. Nếu phải test với platform server, tránh dùng tên cố định trùng với test khác chạy song song.

### 10.1 Ví dụ kiểm tra đơn giản

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class JmxRegistrationLifecycleTest {

    @Test
    void registrationIsRemovedWhenContextCloses() throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name =
            new ObjectName("com.example.app:type=QueueStats,name=ImportQueue");

        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(JmxExportConfiguration.class)) {
            // Cần cấu hình thực tế có QueueMetrics bean và MBeanExporter.
            assertTrue(server.isRegistered(name));
        }

        assertFalse(server.isRegistered(name));
    }
}
\`\`\`

Đây là mẫu thử ý tưởng; để chạy độc lập cần tạo context chứa đúng bean \`QueueMetrics\`, config JMX và bảo đảm exporter sử dụng cùng platform server. Nếu dùng Spring test context caching, test sẽ không thực sự đóng context ở cuối từng test trừ khi có cấu hình vòng đời tương ứng. Khi cần kiểm tra cleanup, tạo và đóng context tường minh là cách rõ ràng.

## 11. Những lỗi vòng đời phổ biến

### 11.1 \`InstanceAlreadyExistsException\` khi restart context

**Biểu hiện:** lượt startup mới không thể register MBean với \`ObjectName\` cũ.

**Nguyên nhân thường gặp:** context cũ chưa đóng, đăng ký thủ công không có unregister, hoặc hai exporter cùng quản lý cùng tên.

**Cách xử lý:** xác định owner và nguồn đăng ký, sửa cleanup hoặc namespace. Không dùng “unregister all” trên shared server.

### 11.2 MBean biến mất sau khi một context dừng

**Biểu hiện:** context B vẫn hoạt động nhưng MBean mà B kỳ vọng không còn.

**Nguyên nhân:** context A thay thế hoặc hủy một \`ObjectName\` dùng chung mà không làm rõ ownership.

**Cách xử lý:** tách namespace và policy đăng ký; chỉ component đăng ký chính thức mới có quyền dọn mục của mình.

### 11.3 \`MBeanServer\` tồn tại nhưng không thấy MBean

**Biểu hiện:** JConsole kết nối nhưng không thấy các bean ứng dụng.

**Nguyên nhân khả dĩ:** exporter chưa bật, bean không thuộc context cần export, server đích khác server mà client kết nối, annotation không được exporter xử lý, hoặc registration failed.

**Cách xử lý:** kiểm tra server instance, exporter config, \`ObjectName\`, startup logs và \`queryNames\` trên đúng server.

### 11.4 Chạy test nhiều lần làm JVM giữ lại MBean

**Biểu hiện:** test sau fail vì registration còn sót, dù test trước đã kết thúc.

**Nguyên nhân:** đăng ký thủ công hoặc context test cache kéo dài hơn tưởng tượng.

**Cách xử lý:** fixture có close/unregister, tách tên hoặc server, tránh test song song cùng tên.

### 11.5 Release server không đóng tài nguyên

**Biểu hiện:** server bị release khỏi factory nhưng còn thread, socket hoặc reference.

**Nguyên nhân:** nhầm release registry với dispose mọi object.

**Cách xử lý:** stop connector, shutdown tài nguyên ứng dụng, unregister owner-managed MBeans, rồi mới release server được sở hữu.

## 12. Runbook khởi động, vận hành và dừng

### Startup

- Ghi rõ lựa chọn server: platform/shared/isolated.
- Có một con đường export rõ ràng cho mỗi MBean.
- \`ObjectName\` hợp lệ, xác định và tránh trùng giữa các context.
- Chỉ công bố operation an toàn theo trạng thái readiness.
- Nếu bật remote connector, xác thực và network exposure phải được cấu hình chủ động.

### Runtime

- Quan sát MBean registration và trạng thái thực sự của component riêng biệt.
- Duy trì log/audit các operation thay đổi trạng thái.
- Không dùng snapshot \`isRegistered\` làm khóa đồng bộ.
- Phân biệt “MBean có mặt trong registry” với “service đang healthy”.

### Shutdown

- Dừng nhận các yêu cầu quản trị mới nếu connector thuộc sở hữu context.
- Dọn MBean được context/exporter đăng ký.
- Đóng thread, executor và tài nguyên do MBean/component tạo.
- Chỉ release server riêng khi application thực sự sở hữu nó.
- Kiểm tra absence của các tên thuộc context trong registry còn sống.

## 13. Bài tập vận dụng

**Bài 1 — Hai Spring context dùng chung platform MBeanServer.** Context A export \`com.demo:type=Metrics,name=Scheduler\`. Context B cũng export đúng tên đó. Hãy nêu kết quả có thể xảy ra khi B startup, cách đặt tên và lý do không nên luôn bật chính sách replace. Gợi ý: xung đột \`ObjectName\` là vấn đề ownership; thêm định danh context hoặc thống nhất chỉ một exporter.

**Bài 2 — Tạo server riêng cho một plugin.** Plugin được load/unload nhiều lần trong cùng JVM. Thiết kế thứ tự tạo server, đăng ký MBean, start connector tùy chọn, stop connector, gỡ đăng ký và release. Nêu cách bảo vệ thao tác cleanup khi startup thất bại giữa chừng. Gợi ý: tài nguyên nào tạo thành công thì phải được ghi nhận để dispose đối xứng; server không được release nếu không thuộc owner đó.

**Bài 3 — Đánh giá một implementation.** Một \`@PreDestroy\` method gọi \`MBeanServerFactory.releaseMBeanServer(ManagementFactory.getPlatformMBeanServer())\`. Phân tích sai ở đâu và viết lại trách nhiệm: context chỉ gỡ MBean mà nó sở hữu, platform server thuộc JVM.

**Bài 4 — Kiểm tra vòng đời.** Viết integration test tạo rồi đóng \`AnnotationConfigApplicationContext\`, assert MBean của context xuất hiện khi đang mở và biến mất khi đóng. Đảm bảo tên không xung đột test song song; không mặc định rằng một assertion \`isRegistered\` kiểm chứng mọi tài nguyên đã cleanup.

## Tóm tắt

Quản lý vòng đời \`MBeanServer\` trong Spring Framework là bài toán **ownership và ranh giới tài nguyên**. \`MBeanServer\` có thể sống lâu hơn một \`ApplicationContext\`; exporter chỉ sở hữu những registration mà nó thực hiện; JMX connector có vòng đời riêng; và một \`ObjectName\` phải có owner rõ ràng. Cách thiết kế bền vững là chọn server có chủ đích, đăng ký với namespace xác định, dọn đúng đối tượng khi context đóng và kiểm tra kết quả trên registry thực tế. Điều này tránh cả rò rỉ MBean lẫn việc xóa nhầm tài nguyên quản trị của thành phần khác.
