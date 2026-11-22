# Tự đánh giá bằng bằng chứng từ MBeanInfo, tool và test trong Spring Framework JMX

## 1. Mục tiêu bài học

Trong nhóm **Đánh giá thiết kế** của Spring Framework JMX, việc một ứng dụng khởi động thành công chưa đủ chứng minh JMX đã được thiết kế đúng. Cũng vậy, việc nhìn thấy một tên MBean trên JConsole không chứng minh mọi attribute và operation đều chính xác, đang trỏ đến đúng Spring bean, hay an toàn để vận hành.

Bài học hướng dẫn một phương pháp tự đánh giá bằng ba loại bằng chứng bổ trợ:

- **MBeanInfo:** hợp đồng JMX đã được công bố thực tế trong MBeanServer.
- **Tool:** khả năng quan sát và thao tác trên MBean trong một JVM đang chạy.
- **Test:** các kiểm chứng tự động về registration, metadata, hành vi, lỗi và vòng đời.

Sau khi hoàn thành, người học có thể xác định yêu cầu kiểm chứng, thu thập bằng chứng phù hợp, đọc các cấu trúc metadata của JMX, viết integration tests và trình bày kết luận có thể truy vết. Việc đánh giá phải phân biệt rõ những gì đã kiểm chứng, những gì chưa kiểm chứng và những rủi ro còn lại.

## 2. Khung đánh giá theo yêu cầu và bằng chứng

Mỗi kết luận nên đi theo một chuỗi minh bạch:

~~~text
Yêu cầu thiết kế
       |
       v
Bằng chứng dự kiến
       |
       v
Quan sát hoặc assertion thực tế
       |
       v
Đối chiếu yêu cầu
       |
       v
Kết luận và hành động tiếp theo
~~~

Ví dụ, yêu cầu “MBean chỉ công bố QueueDepth để đọc” cần bằng chứng từ MBeanAttributeInfo về tên, type, readable/writable, và một phép đọc getAttribute trong test. Chỉ nhìn method getQueueDepth() trong source code chưa chứng minh cấu hình exporter đã đăng ký đúng MBean.

Tương tự, yêu cầu “operation resetStatistics có thể gọi” cần kiểm tra metadata về chữ ký và phép invoke trên một fixture an toàn. Việc MBeanInfo liệt kê operation chưa chứng minh thực thi không ném lỗi, không treo hoặc không phá trạng thái nghiệp vụ.

Các trạng thái đánh giá hữu ích:

| Trạng thái | Diễn giải |
| --- | --- |
| VERIFIED | Bằng chứng phù hợp cho thấy yêu cầu đã được thỏa mãn |
| PARTIALLY_VERIFIED | Mới chứng minh một phần đường đi hoặc tình huống |
| NOT_VERIFIED | Chưa có phép kiểm tra đủ để kết luận |
| FAILED | Có bằng chứng cụ thể về việc không đạt yêu cầu |
| NOT_APPLICABLE | Yêu cầu không áp dụng cho đối tượng này |

Không được biến “chưa có bằng chứng” thành “đã đạt” hoặc “thất bại” nếu chưa có kiểm tra.

## 3. Các tầng trong pipeline Spring JMX

~~~text
Spring ApplicationContext
        |
        +-- Spring bean / AOP proxy
        |
        +-- MBeanExporter
                |
                +-- naming strategy
                +-- MBeanInfoAssembler
                +-- registration policy
                |
                v
            MBeanServer
                |
                +-- ObjectName -> registered MBean
                |
                +-- local JMX API
                |
                +-- JMXConnectorServer
                           |
                           v
                    JMX remote client
~~~

Các phép đánh giá theo tầng:

| Tầng | Câu hỏi | Bằng chứng |
| --- | --- | --- |
| Spring bean | Bean nào đang được quản lý? | ApplicationContext và state của bean |
| Exporter | Bean nào được export và tên nào được chọn? | Configuration và registration logs |
| MBeanServer | Registry có ObjectName đúng? | isRegistered, queryNames |
| Metadata | API quản trị được công bố gồm những gì? | MBeanInfo |
| Local behavior | Attribute và operation hoạt động không? | getAttribute, setAttribute, invoke |
| Runtime tool | Operator có tìm thấy đúng JVM/MBean không? | JConsole hoặc công cụ tương đương |
| Remote connector | Client có truy cập đúng MBean từ xa? | JMXConnector integration test |
| Lifecycle | MBean được unregister đúng khi context đóng? | Test đóng context và đọc lại registry |
| Security | Bề mặt API và quyền truy cập có hợp lý? | Metadata, test authorization và chính sách kết nối |

Một lỗi ở tầng trên không tự có nghĩa tầng dưới lỗi. Ví dụ đọc qua MBeanServer cục bộ thành công nhưng remote connector lỗi thường cần điều tra network, credentials hoặc advertised RMI endpoint trước khi thay đổi assembler.

## 4. Mẫu Standard MBean để thực hành

Tạo một MBean nhỏ với các đặc tính rõ ràng.

**QueueMonitorMBean.java**

~~~java
package com.example.jmx;

public interface QueueMonitorMBean {
    int getQueueDepth();
    boolean isPollingEnabled();
    void setPollingEnabled(boolean enabled);
    void resetStatistics();
}
~~~

**QueueMonitor.java**

~~~java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

public class QueueMonitor implements QueueMonitorMBean {
    private final AtomicInteger queueDepth = new AtomicInteger();
    private final AtomicInteger resetCount = new AtomicInteger();
    private volatile boolean pollingEnabled = true;

    public void enqueue() {
        queueDepth.incrementAndGet();
    }

    public int getResetCountForTest() {
        return resetCount.get();
    }

    @Override
    public int getQueueDepth() {
        return queueDepth.get();
    }

    @Override
    public boolean isPollingEnabled() {
        return pollingEnabled;
    }

    @Override
    public void setPollingEnabled(boolean enabled) {
        pollingEnabled = enabled;
    }

    @Override
    public void resetStatistics() {
        resetCount.incrementAndGet();
    }
}
~~~

Vì QueueMonitor implement QueueMonitorMBean, đây là Standard MBean hợp lệ theo convention JMX. Những phương thức chỉ nằm trên implementation như enqueue() và getResetCountForTest() không tự xuất qua management interface; chúng phục vụ ứng dụng và kiểm thử.

Hợp đồng mong đợi:

| Tên | Loại | Type | Access |
| --- | --- | --- | --- |
| QueueDepth | Attribute | int | Read |
| PollingEnabled | Attribute | boolean | Read/Write |
| resetStatistics | Operation | void, không tham số | Invoke |

ResetCountForTest chỉ dùng để xác minh operation thực sự gây một side effect có thể quan sát được; không nên công bố nó nếu management contract không yêu cầu.

## 5. Cấu hình Spring JMX

~~~java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class QueueJmxConfiguration {

    @Bean
    public QueueMonitor queueMonitor() {
        return new QueueMonitor();
    }

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter queueExporter(
            QueueMonitor queueMonitor,
            MBeanServer platformMBeanServer) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(platformMBeanServer);
        exporter.setBeans(Map.of(
                "com.example.orders:type=QueueMonitor,name=primary",
                queueMonitor));
        return exporter;
    }
}
~~~

Từ đoạn cấu hình có thể kết luận exporter **được định hướng** đăng ký bean dưới tên xác định, nhưng chưa đủ chứng minh registration đã thành công. Phải đọc registry runtime.

Nếu dự án dùng Spring Boot auto-configuration hoặc một exporter thứ hai, có thể xảy ra trùng ObjectName. Nếu exporter dùng custom MBeanServer, việc kiểm tra platform server sẽ không phản ánh đúng registry đó.

## 6. Đọc MBeanInfo từ đúng server

JMX API cung cấp MBeanInfo chứa metadata cuối cùng của MBean đã đăng ký.

~~~java
import javax.management.MBeanServer;
import javax.management.MBeanInfo;
import javax.management.ObjectName;

MBeanServer server = context.getBean(MBeanServer.class);
ObjectName name = new ObjectName(
        "com.example.orders:type=QueueMonitor,name=primary");

if (!server.isRegistered(name)) {
    throw new IllegalStateException(
            "Expected MBean is missing: " + name);
}

MBeanInfo info = server.getMBeanInfo(name);

System.out.println("className=" + info.getClassName());
System.out.println("description=" + info.getDescription());

for (var attribute : info.getAttributes()) {
    System.out.printf(
        "attribute=%s type=%s read=%s write=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable());
}

for (var operation : info.getOperations()) {
    System.out.printf(
        "operation=%s returnType=%s impact=%s%n",
        operation.getName(),
        operation.getReturnType(),
        operation.getImpact());

    for (var parameter : operation.getSignature()) {
        System.out.printf(
            "parameter=%s type=%s%n",
            parameter.getName(),
            parameter.getType());
    }
}

for (var notification : info.getNotifications()) {
    System.out.println(
        java.util.Arrays.toString(notification.getNotifTypes()));
}
~~~

MBeanInfo là bằng chứng về API JMX được công bố **trên server hiện tại**. Nó không bảo đảm mọi lời gọi thực thi thành công, cũng không tự chứng minh remote access được bảo vệ.

Nếu thấy className là một adapter hoặc ModelMBean thay vì implementation, có thể do Spring MBeanInfoAssembler. Đánh giá cần dựa trên contract mong đợi và kiểu MBean đang dùng, không kết luận chỉ từ className.

## 7. Đánh giá attribute qua MBeanAttributeInfo

Đối với mỗi attribute, kiểm tra tên, kiểu, quyền đọc, quyền ghi và ngữ nghĩa của getter/setter.

Ví dụ kỳ vọng:

~~~text
QueueDepth: int, readable=true, writable=false
PollingEnabled: boolean, readable=true, writable=true
~~~

Một vài rủi ro:
- QueueDepth vô tình thành String, khiến client cũ không xử lý được.
- PollingEnabled trở thành read-only làm operator mất khả năng điều chỉnh.
- Một setter không nên xuất lại xuất dưới JMX.
- Bean được exporter trỏ tới không phải instance nghiệp vụ đang cập nhật.
- Attribute có tên trùng nhưng kiểu/ý nghĩa khác.

Việc một getter tồn tại trong Java class không có nghĩa JMX sẽ xuất nó. Standard MBean dựa vào interface; Spring ModelMBean có thể dựa vào assembler và annotation metadata.

Nếu một attribute có giá trị được cập nhật bất đồng bộ, cần đọc trạng thái ở thời điểm thích hợp và cân nhắc dữ liệu có thể thay đổi giữa các lần đọc. MBeanInfo không cung cấp bảo đảm atomic snapshot.

## 8. Đánh giá operation qua MBeanOperationInfo

Một operation có các thành phần:
- Tên method.
- Kiểu trả về.
- Chữ ký và thứ tự tham số.
- Impact metadata.
- Description/descriptor tùy loại MBean.

Ví dụ client:

~~~java
server.invoke(
        name,
        "resetStatistics",
        new Object[0],
        new String[0]);
~~~

Với operation có tham số, signature trong JMX invoke phải đúng kiểu method thực. Một method nhận primitive int thường có signature "int", trong khi Integer là "java.lang.Integer". Luôn tham khảo MBeanOperationInfo thay vì đoán.

Impact INFO, ACTION hoặc ACTION_INFO là metadata mô tả, không phải hệ thống kiểm soát quyền. Một operation được đánh dấu INFO nhưng xóa dữ liệu vẫn là thao tác nguy hiểm. Cần xem implementation và có functional test an toàn.

## 9. Đánh giá notification

Khi MBean phát notifications, đọc MBeanNotificationInfo:

~~~java
for (var notification : info.getNotifications()) {
    for (String type : notification.getNotifTypes()) {
        System.out.println("notificationType=" + type);
    }
}
~~~

Những gì metadata chứng minh:
- MBean tuyên bố hỗ trợ những notification types nào.
- Mô tả notification được công bố.

Những gì metadata chưa chứng minh:
- Sự kiện có thật sự được phát khi điều kiện xảy ra.
- Listener có nhận được callback.
- Payload, sequence number và source chính xác.
- Listener được tháo khi context/client đóng.
- Remote reconnect có đăng ký lại listener đúng cách.

Khi cần kiểm tra notification, dùng fixture có broadcaster và listener rõ ràng, CountDownLatch với timeout hữu hạn và teardown trong finally. Không dùng Thread.sleep làm bằng chứng duy nhất.

## 10. Quan sát thực tế bằng JConsole

Quy trình:

1. Chạy ứng dụng và xác định PID/JVM instance.
2. Mở JConsole từ JDK được hỗ trợ.
3. Kết nối tới đúng local JVM hoặc remote endpoint của môi trường thử nghiệm.
4. Mở tab MBeans, tìm domain com.example.orders.
5. Chọn ObjectName type=QueueMonitor,name=primary.
6. Xem QueueDepth và PollingEnabled.
7. Kiểm tra metadata của operation resetStatistics.
8. Nếu cần, thay đổi PollingEnabled trong fixture an toàn rồi kiểm tra trạng thái bean.
9. Không gọi operation nguy hiểm trên production chỉ vì mục tiêu chứng minh công cụ hoạt động.
10. Ghi lại JVM identity, endpoint, thời điểm và tình trạng công cụ.

Một ảnh chụp JConsole là bằng chứng runtime hữu ích, nhưng không thể thay thế integration test hay security test. Với custom MBeanServer, JConsole có thể kết nối đến server khác mà không thấy object cần tìm.

## 11. Chứng minh JMX trỏ đúng Spring bean

Một exporter có thể đăng ký MBean hợp lệ nhưng sai instance:

~~~java
exporter.setBeans(Map.of(
        "com.example.orders:type=QueueMonitor,name=primary",
        new QueueMonitor()));
~~~

Nếu service nghiệp vụ đang dùng một QueueMonitor bean khác, số liệu JMX sẽ đứng yên. Để chứng minh đúng instance:

1. Lấy bean từ ApplicationContext.
2. Thực hiện thay đổi trạng thái an toàn trên bean đó.
3. Đọc attribute tương ứng qua MBeanServer.
4. So sánh kết quả và lặp lại khi có hai instances cùng type.
5. Bổ sung InstanceId nếu môi trường có nhiều JVM/contexts.

Không sử dụng biểu thức so sánh identity giữa client proxy và bean để khẳng định cùng target; JMX proxy và bean là hai references khác nhau. Hãy kiểm chứng qua trạng thái và cấu hình registration.

## 12. Integration test registration và state

~~~java
package com.example.jmx;

import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class QueueJmxTest {

    @Test
    void registersMBeanAndReadsBeanState() throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                QueueJmxConfiguration.class)) {

            MBeanServer server = context.getBean(MBeanServer.class);
            ObjectName name = new ObjectName(
                "com.example.orders:type=QueueMonitor,name=primary");

            assertTrue(server.isRegistered(name));

            QueueMonitor monitor = context.getBean(QueueMonitor.class);
            monitor.enqueue();

            assertEquals(1,
                    server.getAttribute(name, "QueueDepth"));
        }
    }
}
~~~

Đây là integration test đơn giản cho Spring bean → MBeanExporter → MBeanServer. Test cần đóng context để exporter cleanup.

Trong suite chạy song song, nên dùng server riêng hoặc tên JMX riêng để tránh xung đột khi các tests sử dụng platform MBeanServer chung.

## 13. Assertion cho MBeanInfo

~~~java
import java.util.Arrays;
import javax.management.MBeanInfo;

MBeanInfo info = server.getMBeanInfo(name);

assertTrue(Arrays.stream(info.getAttributes()).anyMatch(a ->
        "QueueDepth".equals(a.getName())
        && "int".equals(a.getType())
        && a.isReadable()
        && !a.isWritable()));

assertTrue(Arrays.stream(info.getAttributes()).anyMatch(a ->
        "PollingEnabled".equals(a.getName())
        && "boolean".equals(a.getType())
        && a.isReadable()
        && a.isWritable()));

assertTrue(Arrays.stream(info.getOperations()).anyMatch(op ->
        "resetStatistics".equals(op.getName())
        && op.getSignature().length == 0));
~~~

Các assertions này bảo vệ contract khi refactor code, thay assembler, đổi Spring version hoặc migrate Standard MBean sang annotation-based exporting.

Trong một số ModelMBean configurations, getter/setter metadata có thể được biểu diễn khác với Standard MBean. Khi kiểm tra migration, xác định rõ contract bắt buộc và những khác biệt metadata được chấp nhận có chủ đích.

## 14. Kiểm chứng operation thực thi thực sự

Chỉ assert operation nằm trong metadata là chưa đủ. Với demo, có thể dùng counter nội bộ để đo side effect:

~~~java
QueueMonitor monitor = context.getBean(QueueMonitor.class);

int before = monitor.getResetCountForTest();

server.invoke(
        name,
        "resetStatistics",
        new Object[0],
        new String[0]);

assertEquals(before + 1, monitor.getResetCountForTest());
~~~

Operation có thể nhận input không hợp lệ, ném business exception hoặc bị chặn bởi dependency ngoài. Trong hệ thống thật, nên có tests cho:
- Input hợp lệ.
- Input sai được từ chối rõ ràng.
- Operation không leak secret.
- Thời gian thực thi bị chặn bởi budget/deadline phù hợp.
- Kết quả sau timeout không bị suy diễn là thất bại chắc chắn.
- Retry không tạo side effect lặp nếu operation không idempotent.

Không thực thi các operation có tác động production trong một phép kiểm chứng đơn giản.

## 15. Đánh giá lifecycle của MBeanExporter

Một điểm quan trọng là registration có được dọn đúng khi Spring ApplicationContext đóng hay không.

~~~java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
        "com.example.orders:type=QueueMonitor,name=primary");

var context = new AnnotationConfigApplicationContext(
        QueueJmxConfiguration.class);

try {
    assertTrue(server.isRegistered(name));
} finally {
    context.close();
}

assertFalse(server.isRegistered(name));
~~~

Test giả định fixture thực sự sở hữu registration đó. Trong môi trường có nhiều exporters, registration policies IGNORE_EXISTING/REPLACE_EXISTING, kết quả shutdown có thể khác. Cần quản lý ownership chính xác.

Việc đóng Spring context không xóa platform MBeanServer của JVM. Nếu có custom MBeanServer, owner của server chịu trách nhiệm release sau khi exporter đã dọn registrations.

## 16. Kiểm thử naming strategy và nhiều instances

Khi hai beans cùng kiểu cần được quản trị, sử dụng hai tên rõ:

~~~text
com.example.orders:type=QueueMonitor,name=primary
com.example.orders:type=QueueMonitor,name=secondary
~~~

Các assertions nên bao phủ:
- Cả hai tên cùng đăng ký.
- Hai ObjectNames trỏ tới đúng instances khác nhau.
- Dữ liệu primary không bị ghi đè bởi secondary ngoài shared state đã định nghĩa.
- Context này đóng không tự ý unregister MBean do context khác sở hữu.
- Naming strategy không đổi tên ngoài dự kiến khi refactor.

RegistrationPolicy.FAIL_ON_EXISTING giúp phát hiện tên trùng. IGNORE_EXISTING có thể giữ MBean cũ khiến số liệu của bean mới không được công bố; REPLACE_EXISTING cần xác định ownership và lifecycle. Policy không thay thế naming strategy.

## 17. Kiểm chứng qua remote connector

Một local JMX API test không kiểm tra remote connector. Với client từ JVM khác, cần có JMXConnectorServer thích hợp và kết nối qua JMXConnector.

Ví dụ client (giả định endpoint fixture đã sẵn sàng):

~~~java
JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://127.0.0.1:9010/jmxrmi");

try (JMXConnector connector =
        JMXConnectorFactory.connect(url)) {

    MBeanServerConnection connection =
            connector.getMBeanServerConnection();

    assertTrue(connection.isRegistered(name));

    assertEquals(1,
            connection.getAttribute(name, "QueueDepth"));
}
~~~

Test remote nên chạy trong môi trường cô lập, có network/ports được quản lý, timeout hữu hạn và teardown đầy đủ.

Nếu production yêu cầu TLS/authentication, phải có test security riêng. Một kết nối JMX loopback không xác thực chỉ chứng minh transport của fixture, không chứng minh policy production.

## 18. Đánh giá bảo mật và bề mặt công bố

Bản kiểm kê của MBean cần phân loại các attributes/operations theo rủi ro:

| Thành phần | Rủi ro | Đánh giá |
| --- | --- | --- |
| QueueDepth read-only | Quan sát số liệu | Thường phù hợp |
| PollingEnabled writable | Thay đổi xử lý | Chỉ nên cho operator có quyền |
| resetStatistics | Thay đổi counters | Cần audit/side-effect test |
| getSecret() | Tiết lộ thông tin | Không công bố |
| deleteAllData() | Hủy dữ liệu | Không công bố theo mặc định |
| restartService() | Gián đoạn hệ thống | Cần policy riêng |

MBeanInfo cho bằng chứng rằng một method được công bố, nhưng không chứng minh authorization của connector. Phải kiểm tra đúng security policy và user roles tại runtime nếu có remote JMX.

Một negative metadata assertion bảo đảm không có method nguy hiểm hữu ích không kém việc kiểm tra có đầy đủ method hợp lệ.

## 19. Đánh giá notifications

Nếu MBean có NotificationBroadcaster, test bao gồm:
1. MBeanInfo liệt kê notification type kỳ vọng.
2. Listener đăng ký thành công qua MBeanServer.
3. Một event thử nghiệm được phát.
4. Listener nhận type, sequence và payload phù hợp.
5. Listener được remove.
6. Sau khi đóng context, không còn listener đăng ký sai owner.

Code khái niệm:

~~~java
CountDownLatch latch = new CountDownLatch(1);
NotificationListener listener = (notification, handback) -> {
    if ("com.example.queue.threshold".equals(notification.getType())) {
        latch.countDown();
    }
};

server.addNotificationListener(name, listener, null, null);

try {
    triggerSafeTestNotification();
    assertTrue(latch.await(2, TimeUnit.SECONDS));
} finally {
    server.removeNotificationListener(name, listener);
}
~~~

Ví dụ này giả định fixture thật sự hỗ trợ notification type được chọn và có phương thức trigger an toàn. Test cần có deadline để không treo khi callback không tới.

## 20. Đánh giá freshness và identity

MBean vẫn có thể được đăng ký với contract đúng nhưng trỏ đến bean cũ. Để đánh giá khả năng quan sát, nên bổ sung:
- InstanceId và build version.
- LastUpdatedEpochMillis.
- HeartbeatEpochMillis.
- SnapshotVersion hoặc sequence.
- LastSuccessfulPoll ở client.
- Trạng thái FRESH/STALE/UNAVAILABLE.

Một metric nghiệp vụ không đổi không tự chứng minh dữ liệu cũ: một queue có thể trống nhiều giờ. Heartbeat và thời gian poll là bằng chứng phù hợp hơn khi đánh giá tính cập nhật.

Nếu nhiều JVM dùng chung ObjectName, client phải định danh cả endpoint hoặc JVM instance để tránh gộp dữ liệu sai.

## 21. Mẫu bảng bằng chứng thiết kế

| Yêu cầu | Bằng chứng | Kết luận có thể rút ra |
| --- | --- | --- |
| ObjectName chính xác | isRegistered và queryNames | Registry hiện có tên mong đợi |
| Bean đúng | Thay trạng thái bean rồi đọc JMX | JMX phản ánh instance nghiệp vụ |
| Attribute read-only | MBeanAttributeInfo | Client không được công bố setter qua contract |
| Operation đúng signature | MBeanOperationInfo | API gọi có tên/tham số phù hợp |
| Operation side effect đúng | invoke + state assertion | Có tác động đúng trong fixture |
| Method nhạy cảm không xuất | Negative MBeanInfo assertion | Bề mặt JMX không có method đó |
| Lifecycle sạch | close + registry check | Exporter unregister theo ownership |
| Remote access | JMXConnector test | Connector fixture hoạt động |
| Authorization | Test user/role với connector bảo vệ | Quyền thực tế phù hợp policy |
| Notifications | Metadata + listener test | Event được công bố và phát |
| Freshness | Timestamp/heartbeat/poll logs | Giá trị có thể phân biệt cũ và mới |

Không đặt tất cả yêu cầu thành bắt buộc cho mọi MBean. Một MBean read-only không cần có operations hoặc notifications nếu use case không yêu cầu.

## 22. Snapshot contract để ngăn regression

Có thể chuẩn hóa metadata:

~~~text
ObjectName=com.example.orders:type=QueueMonitor,name=primary

ATTR:
  PollingEnabled|boolean|READ|WRITE
  QueueDepth|int|READ|-

OP:
  resetStatistics|void|()
~~~

Từ MBeanInfo, sort attributes và operations theo tên/chữ ký, rồi so sánh với contract đã phê duyệt. Nếu operation overload, tên method không đủ để xác định một signature.

Khi migrate từ Standard MBean sang annotation-based ModelMBean, metadata có thể khác về descriptors, description hoặc cách biểu diễn getter/setter. Đánh giá tương thích cần xác định trường nào client thực sự phụ thuộc.

Không chỉ so sánh output console nguyên văn nếu thứ tự hoặc metadata phụ không ổn định qua phiên bản framework.

## 23. Các lỗi phổ biến khi tự đánh giá

**Chỉ xem JConsole:** có thể bỏ sót vấn đề vòng đời, security, stale data hoặc remote connector.

**Chỉ kiểm tra isRegistered:** có thể registry chứa MBean của exporter khác, nhất là khi IGNORE_EXISTING được dùng.

**Chỉ đọc source:** code có đúng annotation/interface cũng chưa chứng minh exporter chọn bean và assembler như mong đợi.

**Chỉ kiểm tra operation hiện diện:** không phát hiện exception hoặc side effect sai.

**Chỉ chạy happy-path test:** không phát hiện ObjectName trùng, sai type, thiếu quyền, timeout hoặc thiếu cleanup.

**Dùng client remote để kiểm tra sai server:** connector có thể gắn với custom MBeanServer, trong khi test lại so với platform server.

**Không phân biệt AOP proxy và management interface:** có thể kiểm tra metadata của proxy chứ không phải target class; phải hiểu exporter đang nhận object nào.

**Không ghi bằng chứng cụ thể:** kết luận “ổn” không cho biết JVM, ObjectName, phiên bản Spring, test case hoặc thời điểm quan sát.

## 24. Quy trình đánh giá bảy bước

1. **Xác định mục đích.** MBean hỗ trợ observability, operation quản trị hay notifications?
2. **Ghi contract.** ObjectName, attribute types/permissions, operation signatures, expected behavior và lifecycle.
3. **Đọc MBeanInfo.** Kiểm tra metadata trên chính server mà exporter dùng.
4. **Quan sát runtime.** Dùng JConsole hoặc tool tương đương ở đúng JVM.
5. **Chạy tests.** Bao phủ registration, behavior, negative cases, lifecycle và remote/security nếu cần.
6. **Đối chiếu từng yêu cầu.** Đánh dấu VERIFIED, PARTIALLY_VERIFIED hoặc NOT_VERIFIED theo bằng chứng.
7. **Ưu tiên cải thiện.** Tập trung vào lỗi bảo mật, side effects, sai instance, data freshness và compatibility trước những thay đổi chỉ mang tính thẩm mỹ.

Khi cần refactor, chạy lại cùng bộ contract tests trước và sau để phát hiện API quản trị thay đổi ngoài ý muốn.

## 25. Bài tập thực hành

**Bài 1.** Tạo một CacheMonitorMBean có CacheSize và resetStatistics, ghi snapshot MBeanInfo bao gồm type/access/signature.

**Bài 2.** Thêm method deleteAllData trên implementation nhưng không thêm vào management interface. Viết negative assertion xác minh method không nằm trong metadata.

**Bài 3.** Export sai một instance QueueMonitor khác với bean đang được service cập nhật. Viết test chứng minh sự khác biệt rồi sửa bằng dependency injection.

**Bài 4.** Tạo primary và secondary MBeans cùng class dưới hai ObjectNames, dùng test xác minh hai instances được tách biệt.

**Bài 5.** Kiểm tra registration trước và sau ApplicationContext.close(), phân biệt unregister MBean và vòng đời platform server.

**Bài 6.** Tạo remote connector trong fixture loopback cô lập, kết nối bằng JMXConnector rồi đọc một attribute qua MBeanServerConnection.

**Bài 7.** Thêm notification type và kiểm tra MBeanInfo, listener callback, sequence và cleanup.

**Bài 8.** Chuyển Standard MBean sang Spring annotation metadata, so sánh snapshot trước/sau để phát hiện khác biệt.

**Bài 9.** Lập báo cáo đánh giá gồm requirement, evidence, result và improvement cho một MBean thật của dự án thử nghiệm.

## Kết luận

Tự đánh giá thiết kế Spring Framework JMX phải dựa trên **bằng chứng từ MBeanInfo, tool và test**, không chỉ cảm nhận về cấu hình. MBeanInfo cho thấy management contract thực sự đã được công bố; công cụ như JConsole giúp xác minh trải nghiệm vận hành; các integration tests kiểm chứng được registration, behavior, lifecycle, security và khả năng tương thích một cách lặp lại. Mỗi nhận định cần được nối với ObjectName, đúng MBeanServer, đúng managed instance và kết quả có thể quan sát. Những yêu cầu chưa được kiểm tra phải được ghi rõ là chưa xác minh, còn các khác biệt giữa kỳ vọng và thực tế cần được xử lý theo mức độ rủi ro.
