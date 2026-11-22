# Exporter listener theo dõi đăng ký và hủy đăng ký MBean trong Spring

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích cách **MBeanExporter** trong Spring quản lý vòng đời đăng ký MBean với một **MBeanServer**.
- Hiểu vai trò của **MBeanExporterListener** và hai callback \`mbeanRegistered(ObjectName)\`, \`mbeanUnregistered(ObjectName)\`.
- Phân biệt callback của exporter với **JMX notification** từ \`MBeanServerDelegate\` và với event của Spring \`ApplicationContext\`.
- Cấu hình một hoặc nhiều exporter listener, thu nhận \`ObjectName\` được đăng ký/hủy đăng ký, và ghi log hoặc metrics với chi phí hợp lý.
- Nhận biết các giới hạn của callback trong trường hợp đăng ký thất bại, đối tượng do thành phần khác đăng ký, sự cố dừng JVM và chính sách đăng ký trùng tên.
- Thiết kế việc quan sát vòng đời MBean mà không làm thay đổi hành vi kinh doanh, tránh side effect lớn và tránh rò dữ liệu quản trị.
- Kiểm tra trình tự đăng ký/hủy đăng ký bằng cách khởi động và đóng Spring context.

## 2. Bối cảnh: exporter quản lý MBean như thế nào?

Trong Java Management Extensions (JMX), một MBean cần được đăng ký với \`MBeanServer\` dưới một \`ObjectName\` cụ thể để công cụ quản trị như JConsole có thể khám phá và truy cập.

Ở Spring Framework, **\`org.springframework.jmx.export.MBeanExporter\`** giúp biến các đối tượng được cấu hình thành MBean hoặc adapter JMX, đăng ký chúng vào một MBeanServer, rồi quản lý cleanup tương ứng theo vòng đời của exporter.

\`\`\`text
Spring ApplicationContext
          |
          | khởi tạo bean và MBeanExporter
          v
MBeanExporter
          |
          +----> chuẩn bị ObjectName / JMX adapter
          |
          +----> MBeanServer.registerMBean(...)
          |                  |
          |                  v
          |          MBean đã đăng ký
          |                  |
          +----> MBeanExporterListener.mbeanRegistered(name)
          |
      Spring context đang hoạt động
          |
          v
      Context shutdown
          |
          +----> MBeanServer.unregisterMBean(...)
          |
          +----> MBeanExporterListener.mbeanUnregistered(name)
\`\`\`

Listener của exporter là một **hook vòng đời**: nó nhận thông báo sau khi exporter đăng ký hoặc hủy đăng ký MBean thuộc phạm vi nó quản lý. Listener phù hợp để ghi nhận hoạt động vận hành, đồng bộ trạng thái local, đo số lượng MBean do exporter xuất hoặc hỗ trợ chẩn đoán.

**Giới hạn quan trọng:** một exporter listener không tự động giám sát mọi MBean trên toàn bộ MBeanServer. MBean được thư viện khác hoặc code thủ công đăng ký trực tiếp có thể không phát callback của exporter đang theo dõi.

## 3. Ba thành phần và trách nhiệm

| Thành phần | Trách nhiệm |
| --- | --- |
| \`MBeanServer\` | Registry thực tế của JMX: giữ \`ObjectName\`, cung cấp \`registerMBean\`, \`unregisterMBean\`, \`isRegistered\`, \`queryNames\` và các thao tác quản trị. |
| \`MBeanExporter\` | Cầu nối Spring và JMX: chọn bean, tạo/nhận metadata quản trị, đăng ký MBean, xử lý chính sách trùng tên và cleanup khi dừng. |
| \`MBeanExporterListener\` | Nhận callback về những lần exporter đăng ký hoặc hủy đăng ký thành công, kèm \`ObjectName\` tương ứng. |

Một **Spring bean** trong \`ApplicationContext\` không mặc nhiên là MBean. Ngược lại, một MBean được đăng ký trực tiếp qua JMX API cũng không tự động trở thành Spring bean.

Ví dụ tên JMX:

\`\`\`text
com.example.orders:type=Cache,name=ProductReadCache
com.example.orders:type=Worker,name=ImportWorker
com.example.orders:type=Queue,name=RetryQueue
\`\`\`

Một callback nhận \`ObjectName\` để xác định MBean nào vừa thay đổi vòng đời; listener không cần và không nên tự giải mã dữ liệu bí mật từ bean nghiệp vụ.

## 4. Giao diện MBeanExporterListener

Trong Spring Framework, interface listener nằm trong package:

\`\`\`java
import org.springframework.jmx.export.MBeanExporterListener;
\`\`\`

Giao diện gồm hai callback:

\`\`\`java
void mbeanRegistered(javax.management.ObjectName objectName);

void mbeanUnregistered(javax.management.ObjectName objectName);
\`\`\`

Ý nghĩa:

- **\`mbeanRegistered(name)\`**: exporter đã thực hiện đăng ký MBean với tên đó thành công và thông báo cho listener.
- **\`mbeanUnregistered(name)\`**: exporter đã thực hiện hủy đăng ký MBean thuộc quyền quản lý và thông báo cho listener.
- Tham số **\`ObjectName\`** chính là định danh JMX, ví dụ \`com.example.orders:type=Worker,name=ImportWorker\`.

Hai callback không nhận class Java, Spring bean name, event payload hay nguyên nhân hủy đăng ký. Nếu muốn ánh xạ \`ObjectName\` sang thành phần nghiệp vụ, phải xây dựng quy ước namespace hoặc bảng mapping riêng do ứng dụng quản lý.

Listener có thể dùng để ghi log, cập nhật bộ đếm hoặc kích hoạt kiểm tra nhẹ nhàng; nó không phải điểm phù hợp để làm công việc blocking kéo dài.

## 5. Ví dụ đơn giản: log khi đăng ký và hủy đăng ký

Tạo implementation cụ thể:

\`\`\`java
package example.springjmx;

import javax.management.ObjectName;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jmx.export.MBeanExporterListener;

public final class LoggingMBeanExporterListener
        implements MBeanExporterListener {

    private static final Logger log =
        LoggerFactory.getLogger(LoggingMBeanExporterListener.class);

    @Override
    public void mbeanRegistered(ObjectName objectName) {
        log.info("JMX MBean registered: {}", objectName);
    }

    @Override
    public void mbeanUnregistered(ObjectName objectName) {
        log.info("JMX MBean unregistered: {}", objectName);
    }
}
\`\`\`

Đây là implementation stateless, dễ áp dụng. Log tên MBean giúp truy vết các lần exporter đăng ký và cleanup theo vòng đời Spring context.

Ví dụ output minh họa:

\`\`\`text
INFO  JMX MBean registered: com.example.orders:type=Worker,name=ImportWorker
INFO  JMX MBean unregistered: com.example.orders:type=Worker,name=ImportWorker
\`\`\`

**Lưu ý riêng tư:** \`ObjectName\` có thể vô tình chứa dữ liệu nhạy cảm nếu thiết kế tên không tốt. Nên dùng domain/key value ổn định, không đưa token, email cá nhân hoặc secret vào tên MBean và hạn chế thông tin đưa vào log.

## 6. Ví dụ hoàn chỉnh với Spring Java Configuration

Để nhìn rõ luồng, ví dụ này khai báo một **Standard MBean**, một **MBeanExporter** và một listener được gắn tường minh.

### 6.1. Định nghĩa Standard MBean

\`\`\`java
package example.springjmx;

public interface WorkerMonitorMBean {
    int getActiveWorkers();
    boolean isRunning();
}
\`\`\`

\`\`\`java
package example.springjmx;

public final class WorkerMonitor implements WorkerMonitorMBean {

    private volatile int activeWorkers = 3;
    private volatile boolean running = true;

    @Override
    public int getActiveWorkers() {
        return activeWorkers;
    }

    @Override
    public boolean isRunning() {
        return running;
    }
}
\`\`\`

Spring exporter sẽ đưa \`WorkerMonitor\` lên JMX theo cấu hình, không cần tự gọi \`MBeanServer.registerMBean\` trong class này.

### 6.2. Cấu hình exporter và listener

\`\`\`java
package example.springjmx;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxExportConfiguration {

    @Bean
    public WorkerMonitor workerMonitor() {
        return new WorkerMonitor();
    }

    @Bean
    public LoggingMBeanExporterListener loggingMBeanExporterListener() {
        return new LoggingMBeanExporterListener();
    }

    @Bean
    public MBeanExporter workerExporter(
            WorkerMonitor workerMonitor,
            LoggingMBeanExporterListener listener) {

        MBeanExporter exporter = new MBeanExporter();

        exporter.setBeans(Map.of(
            "com.example.orders:type=Worker,name=ImportWorker",
            workerMonitor
        ));

        exporter.setListeners(listener);

        return exporter;
    }
}
\`\`\`

Ở đây:

1. \`WorkerMonitor\` là đối tượng quản trị.
2. \`MBeanExporter\` dùng \`setBeans\` để chọn chính xác bean và tên \`ObjectName\` sẽ đăng ký.
3. \`setListeners(listener)\` gắn listener sẽ nhận các callback do exporter phát.
4. Khi exporter hoàn tất đăng ký, \`mbeanRegistered\` được gọi.
5. Khi exporter hủy đăng ký trong quá trình đóng context, \`mbeanUnregistered\` được gọi.

Các cấu hình tự động của Spring Boot có thể tạo exporter khác. Nếu ứng dụng đã có Spring Boot JMX auto-configuration, cần tránh export cùng MBean hai lần; chỉ nên chọn một chủ thể quản lý mỗi \`ObjectName\`.

### 6.3. Chạy context và xác minh đăng ký

\`\`\`java
package example.springjmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public final class ExporterLifecycleDemo {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.orders:type=Worker,name=ImportWorker"
        );

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                    JmxExportConfiguration.class)) {

            System.out.println(
                "Registered: " + server.isRegistered(name)
            );

            System.out.println(
                "ActiveWorkers: " +
                server.getAttribute(name, "ActiveWorkers")
            );
        }

        System.out.println(
            "Registered after close: " + server.isRegistered(name)
        );
    }
}
\`\`\`

Với exporter dùng platform MBeanServer và môi trường không có xung đột tên, kết quả dự kiến:

\`\`\`text
INFO  JMX MBean registered: com.example.orders:type=Worker,name=ImportWorker
Registered: true
ActiveWorkers: 3
INFO  JMX MBean unregistered: com.example.orders:type=Worker,name=ImportWorker
Registered after close: false
\`\`\`

Đây là một ví dụ vòng đời có thể chạy trong ứng dụng Spring Framework với JDK/JMX và dependency Spring Context phù hợp. Khi chạy trong Spring Boot hoặc một container khác, có thể có exporter mặc định hoặc custom \`MBeanServer\`; cần điều chỉnh cấu hình để kiểm tra đúng registry.

## 7. Một MBeanExporter có thể có nhiều listener

Một exporter có thể gọi nhiều listener đã cấu hình:

\`\`\`java
exporter.setListeners(
    new LoggingMBeanExporterListener(),
    new MetricsMBeanExporterListener()
);
\`\`\`

Một listener ghi log; listener khác đo số sự kiện. Tuy nhiên hai listener đều chạy trong luồng xử lý đăng ký/hủy đăng ký do exporter điều phối; không nên để bất kỳ listener nào chặn lâu hoặc ném exception không kiểm soát.

Ví dụ một listener đo số lượt callback:

\`\`\`java
package example.springjmx;

import java.util.concurrent.atomic.LongAdder;
import javax.management.ObjectName;
import org.springframework.jmx.export.MBeanExporterListener;

public final class MetricsMBeanExporterListener
        implements MBeanExporterListener {

    private final LongAdder registrations = new LongAdder();
    private final LongAdder unregistrations = new LongAdder();

    @Override
    public void mbeanRegistered(ObjectName objectName) {
        registrations.increment();
    }

    @Override
    public void mbeanUnregistered(ObjectName objectName) {
        unregistrations.increment();
    }

    public long getRegistrations() {
        return registrations.sum();
    }

    public long getUnregistrations() {
        return unregistrations.sum();
    }
}
\`\`\`

Hai bộ đếm này thể hiện **số callback đã nhận**, không nhất thiết là số MBean hiện có trong MBeanServer vì:

- MBean do thành phần khác đăng ký không phát callback tới listener này.
- Có thể có nhiều chu kỳ đăng ký/hủy đăng ký cùng một tên.
- Các MBean hệ thống JDK thường không thuộc quyền quản lý của Spring exporter.
- Shutdown đột ngột có thể không thực hiện cleanup thông thường.
- Một số lỗi giữa các bước có thể làm bộ đếm callback khác trạng thái registry nếu listener hoặc hệ thống gặp sự cố.

Nếu cần số MBean đang tồn tại trong registry, dùng \`MBeanServer.queryNames\` hoặc \`getMBeanCount\` theo phạm vi cụ thể thay vì lấy \`registrations - unregistrations\` làm nguồn sự thật duy nhất.

## 8. Thời điểm callback được gọi

### 8.1. Đăng ký

Trong đường xử lý thông thường:

\`\`\`text
Spring khởi tạo MBeanExporter
   -> xác định bean sẽ export
   -> tìm/tạo ObjectName
   -> gọi MBeanServer.registerMBean(...)
   -> xử lý kết quả thành công
   -> thông báo listener: mbeanRegistered(name)
\`\`\`

Sự kiện đăng ký được thông báo **sau khi** exporter đăng ký thành công. Nếu đăng ký bị lỗi trước bước này, không thể mặc định listener sẽ nhận \`mbeanRegistered\`. Cơ chế thông báo không thay thế log exception hoặc xử lý lỗi xuất MBean.

### 8.2. Hủy đăng ký

Vòng đời thông thường khi Spring context đóng:

\`\`\`text
ApplicationContext.close()
   -> lifecycle destroy của MBeanExporter
   -> MBeanServer.unregisterMBean(name)
   -> thông báo listener: mbeanUnregistered(name)
\`\`\`

Thời điểm cụ thể có thể phụ thuộc lifecycle callback của exporter và bản Spring Framework. Không nên dựa vào thứ tự callback giữa các bean khác nhau để thực thi business workflow.

### 8.3. Không có bảo đảm phát khi JVM chết đột ngột

Nếu JVM bị kill cứng, host mất điện, container bị chấm dứt không qua shutdown hook hoặc quá trình exit bất thường, code cleanup có thể không chạy. Khi đó không có bảo đảm nhận \`mbeanUnregistered\`.

Vì vậy không dùng callback unregistration như tín hiệu đáng tin cậy duy nhất để xóa trạng thái trên hệ thống phân tán. Với hệ thống cần phát hiện instance chết, nên dùng health check, lease, heartbeat hoặc infrastructure lifecycle tương ứng.

## 9. Chính sách trùng tên MBean ảnh hưởng thế nào?

\`MBeanExporter\` có cấu hình xử lý tình huống \`ObjectName\` đã tồn tại, thường qua registration policy. Các giá trị chính gồm:

- **FAIL_ON_EXISTING:** từ chối/ghi nhận lỗi khi tên đã được đăng ký.
- **IGNORE_EXISTING:** bỏ qua đăng ký của exporter nếu tên đã tồn tại.
- **REPLACE_EXISTING:** cho phép thay thế MBean hiện có theo chính sách exporter.

Cần kiểm tra phiên bản Spring và API chính xác khi cấu hình; ví dụ:

\`\`\`java
import org.springframework.jmx.support.RegistrationPolicy;

exporter.setRegistrationPolicy(
    RegistrationPolicy.FAIL_ON_EXISTING
);
\`\`\`

Đối với listener:

- Nếu exporter **bỏ qua** một MBean đã tồn tại, không nên suy ra callback registered cho một MBean mới do exporter quản lý.
- Nếu một MBean **bị thay thế**, callback/ownership phải được diễn giải theo hành vi thực tế của registration support và policy đã cấu hình.
- Nếu đăng ký **thất bại**, cần chẩn đoán exception/log, không đợi registered callback như tín hiệu lỗi.

Trong hệ thống có nhiều exporter hoặc cả đăng ký thủ công, hãy áp dụng ownership rõ ràng và tránh dùng \`REPLACE_EXISTING\` chỉ để che lỗi cấu hình.

## 10. Listener của exporter khác JMX notification như thế nào?

Đây là điểm quan trọng nhất khi thiết kế cơ chế quan sát MBean.

### 10.1. MBeanExporterListener: theo dõi exporter

\`MBeanExporterListener\` nhận callback trực tiếp từ Spring exporter. Nó chỉ phản ánh những hành động mà exporter thông báo trong phạm vi của mình.

\`\`\`java
exporter.setListeners(loggingListener);
\`\`\`

Nó phù hợp để log những MBean thuộc một module Spring đã được export hay unexport trong vòng đời Spring.

### 10.2. MBeanServerDelegate: notification toàn registry tương ứng

JMX có một MBean delegate chuẩn mang tên:

\`\`\`text
JMImplementation:type=MBeanServerDelegate
\`\`\`

Delegate có thể phát \`MBeanServerNotification\` khi MBean được đăng ký/hủy đăng ký trên **chính MBeanServer đó**, bất kể thao tác do Spring exporter hay thành phần khác thực hiện.

Ví dụ:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.MBeanServerNotification;
import javax.management.NotificationListener;
import javax.management.ObjectName;

ObjectName delegateName = new ObjectName(
    "JMImplementation:type=MBeanServerDelegate"
);

NotificationListener listener = (notification, handback) -> {
    if (notification instanceof MBeanServerNotification event) {
        System.out.printf(
            "JMX registry event: type=%s, object=%s%n",
            event.getType(),
            event.getMBeanName()
        );
    }
};

server.addNotificationListener(
    delegateName,
    listener,
    null,
    null
);

try {
    // Đăng ký/hủy đăng ký MBean để quan sát.
} finally {
    server.removeNotificationListener(
        delegateName,
        listener
    );
}
\`\`\`

**Sự khác nhau về nguồn sự kiện:**

| Thuộc tính | MBeanExporterListener | MBeanServerDelegate notification |
| --- | --- | --- |
| Nguồn phát | Spring \`MBeanExporter\` | JMX \`MBeanServerDelegate\` |
| Phạm vi | Những thay đổi exporter thông báo | Registry của một MBeanServer |
| Cách đăng ký | \`MBeanExporter.setListeners(...)\` | \`MBeanServer.addNotificationListener(...)\` |
| Dữ liệu | \`ObjectName\` | Notification type + \`ObjectName\` + metadata notification |
| Dùng cho | Quan sát lifecycle exporter | Quan sát các sự kiện register/unregister toàn registry |
| Khi MBean do bên khác đăng ký | Không bảo đảm callback | Có thể nhận notification từ delegate cùng server |
| Phụ thuộc vòng đời listener | Spring exporter | Listener JMX được đăng ký với server |

Nếu mục tiêu là *mọi* đăng ký và hủy đăng ký trong một MBeanServer, delegate notification phù hợp hơn. Nếu mục tiêu là *các MBean do exporter của module Spring quản lý*, listener của exporter phù hợp hơn.

### 10.3. Spring ApplicationEvent khác hai cơ chế trên

\`ContextRefreshedEvent\` và \`ContextClosedEvent\` là sự kiện Spring ApplicationContext, mô tả vòng đời context. Chúng không mang danh sách từng MBean vừa đăng ký hoặc hủy đăng ký. Có thể kết hợp event Spring với listener exporter để chẩn đoán, nhưng không nên nhầm hai loại thông báo.

## 11. Thiết kế listener chịu lỗi

Một listener tốt thường có các đặc điểm:

1. **Nhanh:** không gọi HTTP, database, filesystem nặng hoặc block lâu trong callback.
2. **Idempotent khi cần:** cập nhật state theo \`ObjectName\` an toàn trước duplicate hoặc thay đổi thứ tự xử lý.
3. **Không gây lỗi dây chuyền:** xử lý exception của logic phụ trợ để tránh làm gián đoạn lifecycle exporter.
4. **Không làm lộ dữ liệu:** log ObjectName đã được thiết kế và chỉ những metadata cần thiết.
5. **Thread-safe:** nếu state được đọc/ghi qua nhiều luồng, dùng cấu trúc đồng bộ thích hợp.
6. **Không suy luận toàn registry:** hiểu rõ listener chỉ theo dõi exporter.
7. **Không làm thay business lifecycle:** listener phục vụ observability, không gánh logic nghiệp vụ cần transaction.

Ví dụ listener theo dõi tập những tên đã nhận registered callback:

\`\`\`java
package example.springjmx;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import javax.management.ObjectName;
import org.springframework.jmx.export.MBeanExporterListener;

public final class TrackingMBeanExporterListener
        implements MBeanExporterListener {

    private final Set<ObjectName> observed =
        ConcurrentHashMap.newKeySet();

    @Override
    public void mbeanRegistered(ObjectName objectName) {
        observed.add(objectName);
    }

    @Override
    public void mbeanUnregistered(ObjectName objectName) {
        observed.remove(objectName);
    }

    public Set<ObjectName> observedNamesSnapshot() {
        return Set.copyOf(observed);
    }
}
\`\`\`

Tập \`observed\` là trạng thái nội bộ của listener, không phải phép kiểm kê JMX chính thức. Nếu ứng dụng thật cần trạng thái chính xác, kết hợp kiểm tra \`server.isRegistered(name)\` hoặc \`queryNames\` vào đúng thời điểm và chấp nhận khả năng thay đổi đồng thời.

## 12. Khi callback phát sinh exception thì sao?

\`MBeanExporterListener\` không yêu cầu checked exception trong chữ ký callback, nhưng code bên trong có thể ném runtime exception. Nếu listener ném lỗi trong luồng exporter đang đăng ký/hủy đăng ký, hậu quả phụ thuộc implementation và thời điểm phát callback; không nên giả định exception sẽ được bỏ qua.

Một listener chuyên log thường không cần ném lỗi. Nếu gửi metrics thất bại, có thể xử lý nội bộ:

\`\`\`java
@Override
public void mbeanRegistered(ObjectName objectName) {
    try {
        metricsRecorder.recordRegistered(objectName);
    } catch (RuntimeException ex) {
        log.warn(
            "Could not record JMX registration for {}",
            objectName,
            ex
        );
    }
}
\`\`\`

Trong ví dụ, \`metricsRecorder\` là collaborator do ứng dụng cung cấp, không phải API có sẵn của Spring. Logging cần tránh chi phí quá lớn hoặc tiết lộ secret trong exception.

Nếu yêu cầu nghiệp vụ là “mọi registration phải ghi bền vào DB”, listener exporter không phải lựa chọn duy nhất đáng tin cậy. Cần cơ chế transaction, retry và reconciliation riêng, vì callback có thể không chạy khi JVM kết thúc bất thường.

## 13. Quan hệ giữa listener và vòng đời Spring

\`MBeanExporter\` quản lý các MBean nó đăng ký theo lifecycle của Spring. Điều này thường liên quan đến:

- Khởi tạo bean và cấu hình exporter.
- Hoàn tất đăng ký MBean khi exporter khởi tạo.
- MBean hoạt động trong suốt vòng đời context.
- Hủy đăng ký MBean khi exporter bị destroy hoặc context đóng.

Trong code sử dụng \`AnnotationConfigApplicationContext\`, \`try-with-resources\` giúp gọi \`close()\` và đưa các singleton bean qua quá trình hủy. Nhờ đó ví dụ ở phần 6 có thể quan sát được unregistered callback.

Tuy nhiên có những yếu tố ảnh hưởng:

- Bean singleton bị thay đổi thủ công không đồng nghĩa MBean được exporter đăng ký lại ngay.
- Một exporter có thể không đăng ký MBean bị trùng tên tùy policy.
- MBean được đăng ký bởi code ngoài exporter có thể tồn tại sau khi Spring context đóng.
- Nếu sử dụng custom \`MBeanServer\`, kiểm tra đúng instance khi gọi \`isRegistered\`.
- Trong ứng dụng có nhiều Spring contexts, mỗi exporter có vòng đời riêng và có nguy cơ tranh chấp ObjectName.

## 14. Minh họa integration test về lifecycle

Một test đơn giản có thể dùng listener thu thập event mà không cần JConsole hoặc remote connector.

\`\`\`java
package example.springjmx;

import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.List;
import javax.management.ObjectName;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.MBeanExporterListener;

public final class ExporterLifecycleCheck {

    static final class EventRecorder
            implements MBeanExporterListener {

        final List<String> events = new ArrayList<>();

        @Override
        public void mbeanRegistered(ObjectName objectName) {
            events.add("REGISTER " + objectName.getCanonicalName());
        }

        @Override
        public void mbeanUnregistered(ObjectName objectName) {
            events.add("UNREGISTER " + objectName.getCanonicalName());
        }
    }

    public static void main(String[] args) throws Exception {
        EventRecorder recorder = new EventRecorder();
        ObjectName name = new ObjectName(
            "com.example.orders:type=Worker,name=LifecycleCheck"
        );

        AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext();

        context.registerBean(
            "worker",
            WorkerMonitor.class,
            WorkerMonitor::new
        );

        context.registerBean(
            "exporter",
            MBeanExporter.class,
            () -> {
                MBeanExporter exporter = new MBeanExporter();
                exporter.setBeans(java.util.Map.of(
                    name.toString(),
                    context.getBean("worker")
                ));
                exporter.setListeners(recorder);
                return exporter;
            }
        );

        context.refresh();

        boolean registered =
            ManagementFactory.getPlatformMBeanServer()
                .isRegistered(name);

        context.close();

        boolean stillRegistered =
            ManagementFactory.getPlatformMBeanServer()
                .isRegistered(name);

        System.out.println("registered=" + registered);
        System.out.println("afterClose=" + stillRegistered);
        System.out.println(recorder.events);
    }
}
\`\`\`

Ví dụ minh họa lifecycle; khi xây dựng integration test chính thức cần cô lập ObjectName, xử lý cleanup ngay cả khi assertion lỗi và tránh phụ thuộc trạng thái MBeanServer dùng chung của các test khác. Trong kiểm tra tự động, có thể thay test thủ công bằng JUnit và assert callback event.

Mục tiêu kiểm chứng là sự kiện REGISTER khi exporter đăng ký MBean và UNREGISTER khi context cleanup, không phải kiểm tra nội dung nghiệp vụ của bean.

## 15. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Không thấy registered callback | Listener chưa được gắn đúng exporter; MBean không nằm trong danh sách xuất; đăng ký thất bại. | Kiểm tra \`setListeners\`, \`setBeans\`, log exporter và \`isRegistered\`. |
| MBean xuất hiện trong JConsole nhưng listener không nhận | MBean do thành phần khác đăng ký hoặc dùng exporter khác. | Xác minh chủ thể đăng ký và MBeanServer. |
| Có registered nhưng không thấy unregistered | JVM kết thúc bất thường; context không đóng; MBean được quản lý ngoài exporter. | Kiểm tra lifecycle shutdown và ownership. |
| Bị \`InstanceAlreadyExistsException\` | Trùng ObjectName trong cùng MBeanServer. | Kiểm tra registration policy và exporter khác. |
| Unregistered xảy ra lúc refresh/redeploy | Context/exporter bị destroy/recreate. | Ghi nhận lifecycle của từng context. |
| Đếm callback không bằng tổng số MBean | Phạm vi listener chỉ là exporter; MBean hệ thống do JVM tạo. | Dùng \`queryNames\` cho số lượng registry thực. |
| Listener chặn lâu khiến startup chậm | Logic đồng bộ nặng trong callback. | Dùng ghi log nhẹ hoặc handoff bất đồng bộ có giới hạn. |
| Listener ném runtime exception | Lỗi xử lý metrics/log/hạ tầng phụ trợ. | Xử lý exception trong listener; tách trách nhiệm quan sát. |
| Sai tên MBean trong event | Cấu hình \`ObjectName\`/naming strategy khác dự kiến. | Log canonical name, kiểm tra metadata và mapping. |

## 16. Các nhầm lẫn cần tránh

### 16.1. “Listener giám sát mọi MBean trong JVM”

Không đúng. Listener gắn với một \`MBeanExporter\`, nên chỉ nhận callback do exporter đó phát. Muốn quan sát registry toàn server phải cân nhắc delegate notification.

### 16.2. “Nếu không thấy unregistered callback thì MBean chắc chắn còn tồn tại”

Không đúng. JVM có thể đã dừng hoặc MBean bị thành phần khác gỡ. Trạng thái callback không phải nguồn sự thật toàn cục.

### 16.3. “MBeanExporterListener là NotificationListener của JMX”

Không đúng. Hai interface và cơ chế khác nhau: một thuộc Spring export lifecycle, một thuộc JMX Notification API.

### 16.4. “Đăng ký trùng tên thì listener sẽ được gọi cho tên đã có”

Không thể suy ra như vậy. Callback phụ thuộc việc exporter thực hiện thành công thao tác tương ứng và registration policy được áp dụng.

### 16.5. “Có listener thì không cần kiểm tra MBeanServer”

Không đúng. \`MBeanServer.isRegistered\` và \`queryNames\` vẫn là API trực tiếp để kiểm tra registry trong một thời điểm.

### 16.6. “Phải thực hiện network request trong callback để đảm bảo đồng bộ”

Không nên mặc định. Callback đồng bộ, việc phụ thuộc network có thể làm chậm hoặc gây lỗi lifecycle. Nếu cần gửi event ra hệ thống khác, thiết kế hàng đợi, batch hoặc cơ chế retry phù hợp.

## 17. Bài tập thực hành

### Bài tập 1 — Log một MBean

Tạo \`WorkerMonitorMBean\`, \`WorkerMonitor\`, \`LoggingMBeanExporterListener\` và \`MBeanExporter\` theo phần 6. Chạy context, quan sát log registered; đóng context, quan sát log unregistered.

**Mục tiêu:** hiểu callback gắn với vòng đời exporter.

### Bài tập 2 — Hai listener cùng một exporter

Gắn một logging listener và một metrics listener. Khởi động một exporter đăng ký hai MBean; xem hai listener đều nhận callback tương ứng.

**Mục tiêu:** hiểu \`setListeners\` và sự khác nhau giữa event count và registry size.

### Bài tập 3 — Đăng ký MBean ngoài exporter

Dùng \`ManagementFactory.getPlatformMBeanServer().registerMBean(...)\` để đăng ký trực tiếp một MBean khác. Quan sát exporter listener không phát callback cho đối tượng đó, nhưng \`server.queryNames\` vẫn tìm thấy nó.

**Mục tiêu:** phân biệt exporter lifecycle với toàn JMX registry.

### Bài tập 4 — MBeanServerDelegate

Đăng ký một JMX \`NotificationListener\` với \`JMImplementation:type=MBeanServerDelegate\`. Thử đăng ký/hủy đăng ký bằng cả Spring exporter và API JMX trực tiếp.

**Mục tiêu:** phân biệt loại event và phạm vi quan sát.

### Bài tập 5 — Trùng tên

Trong môi trường thử nghiệm cô lập, tạo hai exporter cùng dùng một ObjectName. Thử \`FAIL_ON_EXISTING\` và \`IGNORE_EXISTING\`, ghi nhận cách ứng dụng khởi động và listener nhận callback.

**Mục tiêu:** hiểu chính sách ownership và không suy đoán callback từ tên đã tồn tại.

### Bài tập 6 — Dừng ứng dụng bất thường

Ở môi trường lab, so sánh \`context.close()\` bình thường với việc chấm dứt JVM đột ngột. Quan sát sự khác nhau về cleanup và callback.

**Mục tiêu:** hiểu callback không phải một giao thức reliable distributed event.

## 18. Câu hỏi ôn tập

**1. MBeanExporterListener nhận thông tin gì?** Hai callback \`mbeanRegistered\` và \`mbeanUnregistered\`, mỗi callback nhận \`ObjectName\` của MBean liên quan.

**2. Listener có giám sát tất cả MBean của JVM không?** Không. Nó chỉ nhận thông báo do exporter được gắn phát ra.

**3. Khi nào callback registered thường được gọi?** Sau thao tác đăng ký MBean thành công qua exporter.

**4. Khi nào callback unregistered thường được gọi?** Sau khi exporter hủy đăng ký MBean thuộc quyền quản lý, thường trong quá trình cleanup/shutdown.

**5. JVM bị kill cứng có bảo đảm callback unregistered không?** Không. Shutdown lifecycle bình thường có thể không được thực hiện.

**6. Nếu muốn nghe toàn bộ sự kiện registry trong một MBeanServer nên xem API nào?** Notification từ \`JMImplementation:type=MBeanServerDelegate\`, đăng ký qua \`MBeanServer.addNotificationListener\`.

**7. Listener có nên thực hiện tác vụ network dài không?** Không. Nên giữ callback nhanh, xử lý lỗi và nếu cần thì chuyển giao sang cơ chế bất đồng bộ phù hợp.

**8. Đếm registered trừ unregistered có luôn bằng MBeanServer.getMBeanCount không?** Không. Listener chỉ quan sát một phạm vi exporter và callback không nhất thiết đại diện tất cả MBean.

**9. Vì sao nên kiểm tra \`ObjectName\`?** Vì đây là định danh mà JMX registry sử dụng để phân biệt MBean, điều tra xung đột và tra cứu trạng thái.

**10. Có thể dùng listener để thực thi business transaction bắt buộc không?** Không nên coi callback này là kênh event bền vững; các nghiệp vụ có ràng buộc đảm bảo riêng cần cơ chế transaction hoặc event delivery phù hợp.

## 19. Tổng kết

\`MBeanExporterListener\` là cơ chế theo dõi **vòng đời xuất MBean của Spring**. Khi \`MBeanExporter\` đăng ký hoặc hủy đăng ký những MBean nó quản lý, listener nhận callback cùng \`ObjectName\`. Nhờ đó ứng dụng có thể ghi log, đo sự kiện hoặc quan sát thay đổi ở lớp tích hợp Spring–JMX mà không phải polling toàn bộ registry.

Để hiểu đúng phạm vi, cần phân biệt listener này với **\`MBeanServerDelegate\` notification** theo dõi sự kiện registry rộng hơn và với **Spring ApplicationContext events**. Listener nên nhẹ, an toàn khi có lỗi, tránh dữ liệu nhạy cảm và không được xem là bằng chứng duy nhất của trạng thái hệ thống khi có shutdown bất thường.

## Tài liệu tham khảo

- Spring Framework Javadoc — \`MBeanExporterListener\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporterListener.html
- Spring Framework Javadoc — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Java SE 21 — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 — \`MBeanServerNotification\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerNotification.html
- Java SE 21 — \`MBeanServerDelegate\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerDelegate.html