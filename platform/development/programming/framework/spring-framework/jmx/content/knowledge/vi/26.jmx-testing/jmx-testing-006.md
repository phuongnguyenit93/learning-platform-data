# Kiểm thử exporter start và stop trong Spring Framework JMX

## 1. Mục tiêu

Trong Spring Framework JMX, `MBeanExporter` chịu trách nhiệm đăng ký các Spring bean thành MBean trong `MBeanServer`. Khi Spring `ApplicationContext` khởi động, exporter thường thực hiện đăng ký; khi context đóng, exporter phải dọn dẹp những registration thuộc quyền quản lý của nó.

Kiểm thử **exporter start và stop** cần xác nhận **vòng đời đăng ký/hủy đăng ký**, không chỉ việc class có annotation hay một getter trả đúng dữ liệu.

Các câu hỏi cần trả lời:

1. Trước khi khởi tạo exporter, ObjectName chưa được đăng ký?
2. Sau khi exporter khởi tạo, MBean xuất hiện đúng `ObjectName`?
3. Attribute và operation của MBean có thể truy cập?
4. Khi đóng `ApplicationContext`, MBean do exporter quản lý có được hủy đăng ký?
5. Nếu startup thất bại hoặc trùng ObjectName, exporter báo và xử lý ra sao?
6. Có vô tình hủy đăng ký MBean thuộc chủ sở hữu khác?
7. Nếu context được tạo lại, có thể đăng ký lại cùng tên mà không bị leak?
8. Những listener, connection và tài nguyên phụ thuộc có được giải phóng phù hợp?

Bài học phân biệt **start/stop của exporter**, **start/stop của application context** và **start/stop của tài nguyên nghiệp vụ**. Các vòng đời này liên quan nhưng không luôn đồng nghĩa.

## 2. Luồng lifecycle của MBeanExporter

Một vòng đời điển hình:

~~~text
ApplicationContext chưa tạo
        |
        v
Spring tạo bean nghiệp vụ
        |
        v
Spring tạo MBeanExporter
        |
        v
Exporter đăng ký MBean vào MBeanServer
        |
        v
MBeanServer.isRegistered(ObjectName) = true
        |
        | Các client đọc attributes/gọi operations
        |
        v
ApplicationContext.close()
        |
        v
Exporter unregister những MBean thuộc phạm vi quản lý
        |
        v
MBeanServer.isRegistered(ObjectName) = false
~~~

**Không giả định MBeanExporter là `SmartLifecycle` với các phương thức `start()` và `stop()` trong mọi phiên bản.** Với cách sử dụng thường gặp, exporter là Spring bean tham gia lifecycle khởi tạo/hủy bean; việc gọi `afterPropertiesSet()` và `destroy()` hoặc đóng context là những điểm kiểm thử chính.

Nói “kiểm thử exporter start/stop” trong bài này là kiểm tra việc exporter **được khởi tạo/đăng ký** và **được hủy/deregister**, không nhất thiết là API `Lifecycle.start()`/`stop()`.

## 3. Thành phần cần có trong bài test

| Thành phần | Vai trò |
| --- | --- |
| `MBeanServer` cô lập | Registry riêng cho test, không đụng platform MBeans của JVM |
| `MBeanExporter` | Thành phần cần kiểm thử lifecycle |
| Bean quản trị | MBean sẽ được exporter đăng ký |
| `ObjectName` | Định danh cần xác nhận trước/sau |
| `ApplicationContext` | Quản lý việc tạo/hủy exporter |
| Assertion | Kiểm tra trạng thái registry và hợp đồng MBean |
| Cleanup | Đóng context, release MBeanServer |

Cách an toàn là tạo MBeanServer riêng bằng `MBeanServerFactory.newMBeanServer()`. Phương thức này tạo một MBeanServer mới không đăng ký vào danh sách tìm kiếm của factory, giảm nguy cơ tác động test khác. Trong ví dụ, chọn cách này để không can thiệp vào platform MBeanServer mà JConsole hoặc thư viện khác đang dùng.

Nếu code ứng dụng cần `MBeanServerFactory.createMBeanServer()`, phải quản lý release theo contract của factory. Không tự ý release platform server.

## 4. Ví dụ MBean dùng trong kiểm thử

Để tập trung vào lifecycle, dùng một Standard MBean theo quy ước Java JMX:

~~~java
package com.example.testjmx;

public interface CounterAdminMBean {
    long getCount();
    void reset();
}
~~~

~~~java
package com.example.testjmx;

import java.util.concurrent.atomic.AtomicLong;

public class CounterAdmin implements CounterAdminMBean {

    private final AtomicLong count = new AtomicLong(5);

    @Override
    public long getCount() {
        return count.get();
    }

    @Override
    public void reset() {
        count.set(0);
    }
}
~~~

`CounterAdmin` không cần annotation Spring; nó là Standard MBean khi được đăng ký với interface `CounterAdminMBean`. Tên và cấu trúc interface giúp JMX nhận diện attributes và operations.

Đây là một resource test đơn giản, không truy cập network, database hoặc tài nguyên thật. Vì vậy test có thể chạy nhiều lần mà không tạo side effect ngoài MBeanServer.

## 5. Cấu hình Spring với MBeanServer riêng

Có thể tạo một Spring configuration quản lý exporter và server:

~~~java
package com.example.testjmx;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

import java.util.Map;

@Configuration
public class JmxTestConfiguration {

    public static final String OBJECT_NAME =
        "com.example.test:type=Counter,name=primary";

    @Bean
    MBeanServer testMBeanServer() {
        return MBeanServerFactory.newMBeanServer();
    }

    @Bean
    CounterAdmin counterAdmin() {
        return new CounterAdmin();
    }

    @Bean
    MBeanExporter counterExporter(
            MBeanServer testMBeanServer,
            CounterAdmin counterAdmin
    ) {
        MBeanExporter exporter = new MBeanExporter();

        exporter.setServer(testMBeanServer);
        exporter.setBeans(Map.of(
            OBJECT_NAME,
            counterAdmin
        ));

        return exporter;
    }
}
~~~

**Lưu ý:** annotation `@Configuration` chỉ thể hiện cách tổ chức bean; exporter vẫn phải thực sự được Spring tạo trong context. Khi context đóng, Spring gọi lifecycle destruction của các bean liên quan, gồm exporter.

Trong một số cấu hình project, có thể có exporter tự động khác. Đối với unit/integration test này, dùng context cô lập và chỉ import `JmxTestConfiguration` nhằm tránh trùng registration.

## 6. Integration test: context khởi động thì MBean xuất hiện

JUnit 5 có thể dùng `AnnotationConfigApplicationContext` để chủ động điều khiển lifecycle context.

~~~java
package com.example.testjmx;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

public class MBeanExporterLifecycleTest {

    @Test
    void registersAndUnregistersMBean() throws Exception {
        AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext();

        context.register(JmxTestConfiguration.class);

        ObjectName name = new ObjectName(
            JmxTestConfiguration.OBJECT_NAME
        );

        // Chưa refresh, exporter chưa khởi tạo/đăng ký.
        context.refresh();

        MBeanServer server =
            context.getBean(MBeanServer.class);

        assertTrue(server.isRegistered(name));

        Object value = server.getAttribute(name, "Count");
        assertEquals(5L, value);

        context.close();

        assertFalse(server.isRegistered(name));
    }
}
~~~

Test minh họa luồng refresh → registered → close → unregistered. Nhưng đoạn test trên chưa quan sát `isRegistered=false` **trước khi refresh**, vì MBeanServer được tạo bởi context trong lúc refresh.

Muốn kiểm tra chặt cả precondition, hãy tạo MBeanServer bên ngoài context và inject hoặc đăng ký nó vào context trước khi refresh; cách đó được trình bày ở phần tiếp theo.

### Lưu ý khi assertion trên Java value

`MBeanServer.getAttribute` trả `Object`. Với attribute kiểu primitive `long`, kết quả thường được boxing thành `Long`; assertion `assertEquals(5L, value)` phù hợp với tình huống này.

## 7. Integration test đầy đủ: before, during, after

Một cách test độc lập hơn là tạo MBeanServer trước, rồi truyền nó cho Spring context:

~~~java
package com.example.testjmx;

import java.util.Map;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.jmx.export.MBeanExporter;

import static org.junit.jupiter.api.Assertions.*;

class ExporterRegistrationTest {

    @Test
    void exporterRegistrationFollowsContextLifecycle()
            throws Exception {

        MBeanServer server = MBeanServerFactory.newMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.test:type=Counter,name=primary"
        );

        assertFalse(server.isRegistered(name));

        AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext();

        // Đưa MBeanServer hiện có vào context.
        context.getBeanFactory().registerSingleton(
            "testMBeanServer", server
        );

        context.registerBean(
            "counterAdmin", CounterAdmin.class
        );

        context.registerBean(
            "counterExporter",
            MBeanExporter.class,
            () -> {
                MBeanExporter exporter = new MBeanExporter();
                exporter.setServer(server);
                exporter.setBeans(Map.of(
                    name.toString(),
                    context.getBean("counterAdmin")
                ));
                return exporter;
            }
        );

        try {
            context.refresh();

            assertTrue(server.isRegistered(name));
            assertEquals(5L, server.getAttribute(name, "Count"));

        } finally {
            context.close();
        }

        assertFalse(server.isRegistered(name));
    }
}
~~~

Ở đoạn trên, `context.registerBean` là API dành cho Spring Framework hiện đại; trong project dùng Spring bản cũ có thể thay bằng configuration class hoặc register bean definition tương ứng.

Mục tiêu test là ba mốc:

~~~text
Before: MBean chưa đăng ký
During: MBean đã đăng ký và truy vấn được
After:  MBean đã được hủy đăng ký
~~~

Nếu test sử dụng một MBeanServer riêng, kết quả không bị ảnh hưởng bởi MBean cùng tên trong platform MBeanServer của ứng dụng khác.

## 8. Kiểm tra operations ngoài trạng thái đăng ký

MBean xuất hiện trong registry chưa chắc có metadata đúng. Có thể kiểm tra thêm operation:

~~~java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = server.getMBeanInfo(name);

boolean hasReset = false;

for (MBeanOperationInfo operation : info.getOperations()) {
    if ("reset".equals(operation.getName())) {
        hasReset = true;
        break;
    }
}

assertTrue(hasReset, "Expected reset operation");

server.invoke(
    name,
    "reset",
    new Object[0],
    new String[0]
);

assertEquals(0L, server.getAttribute(name, "Count"));
~~~

Việc kiểm tra operation hữu ích vì một exporter có thể đăng ký MBean thành công nhưng mapping metadata/assembler không đúng hợp đồng. Trong test lifecycle, dùng operation vô hại như reset counter để tránh ảnh hưởng tài nguyên thật.

## 9. Khi dùng annotation exporter

Spring JMX cho phép khai báo management metadata bằng:

- `@ManagedResource`
- `@ManagedAttribute`
- `@ManagedOperation`
- `@ManagedNotification`

Ví dụ:

~~~java
package com.example.testjmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.test:type=Worker,name=primary"
)
public class WorkerManagement {
    private volatile boolean paused;

    @ManagedAttribute
    public boolean isPaused() {
        return paused;
    }

    @ManagedOperation
    public void pause() {
        paused = true;
    }
}
~~~

Muốn Spring phát hiện và export bean này, context phải có một annotation-capable exporter như `AnnotationMBeanExporter` hoặc cấu hình tương đương.

Một test riêng cho annotation export nên xác nhận:

1. Bean được tạo trong đúng context.
2. Exporter đọc được `@ManagedResource`.
3. MBean được đăng ký theo ObjectName trong annotation hoặc naming strategy.
4. Attribute `Paused` và operation `pause()` có trong `MBeanInfo`.
5. Khi context close, MBean được unregister.

Không được suy ra một class được gắn `@ManagedResource` là MBean ngay lập tức; annotation không tự đăng ký class chưa được Spring quản lý.

## 10. Kiểm tra shutdown trong trường hợp exception

Một rủi ro khi viết test là assertion thất bại giữa chừng làm context không được đóng. Điều này có thể để MBean còn đăng ký và gây lỗi cho test kế tiếp.

Nên dùng `try/finally`:

~~~java
AnnotationConfigApplicationContext context =
    new AnnotationConfigApplicationContext();

try {
    context.register(JmxTestConfiguration.class);
    context.refresh();

    // Assertions here.
} finally {
    context.close();
}
~~~

Nếu test có nhiều resource, quản lý lifecycle đầy đủ:

~~~text
Create MBeanServer
Create ApplicationContext
Refresh/export
Assert
Close ApplicationContext
Verify unregister
Release test-only resources
~~~

Nếu dùng `MBeanServerFactory.createMBeanServer()`, có thể cần `MBeanServerFactory.releaseMBeanServer(server)` sau test theo contract của factory. Với `newMBeanServer()`, không có yêu cầu release tương tự trong registry của factory.

## 11. Test đóng rồi mở lại context

Một lỗi phổ biến là lần chạy đầu thành công, lần thứ hai thất bại do ObjectName còn tồn tại. Thực hiện test hai vòng:

~~~java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

MBeanServer server = MBeanServerFactory.newMBeanServer();

ObjectName name = new ObjectName(
    "com.example.test:type=Counter,name=primary"
);

for (int attempt = 0; attempt < 2; attempt++) {
    AnnotationConfigApplicationContext context =
        createContextWithExporter(server);

    try {
        assertTrue(server.isRegistered(name));
    } finally {
        context.close();
    }

    assertFalse(
        server.isRegistered(name),
        "MBean leaked after context close"
    );
}
~~~

`createContextWithExporter(server)` là helper minh họa cần định nghĩa trong fixture.

Điều kiện mong đợi:

~~~text
Attempt 1: register -> unregister
Attempt 2: register -> unregister
~~~

Nếu lần hai gặp `InstanceAlreadyExistsException`, exporter hoặc một thành phần khác có thể đã giữ lại registration cũ.

Không chữa lỗi test bằng cách bật `REPLACE_EXISTING` một cách mặc định; làm vậy có thể che dấu leak và lỗi ownership.

## 12. Test registration policy

Spring cung cấp `RegistrationPolicy` cho tình huống ObjectName đã được dùng.

### FAIL_ON_EXISTING

Đây là hành vi phù hợp khi cần phát hiện trùng tên:

~~~text
Existing MBean at ObjectName X
New exporter tries to register X
    -> fail with registration error
~~~

Test nên xác nhận exporter báo lỗi và **MBean cũ không bị thay thế**.

### IGNORE_EXISTING

Exporter bỏ qua registration mới khi tên đã tồn tại:

~~~text
Existing MBean X
New exporter wants X
    -> existing MBean retained
~~~

Test cần xác minh bean mới không được đăng ký thay, MBean cũ vẫn hoạt động và context shutdown không vô tình unregister tài nguyên thuộc owner khác.

### REPLACE_EXISTING

Exporter thay MBean đã có dưới cùng ObjectName. Test cần xem:

- MBean mới thực sự được đăng ký.
- Metadata và trạng thái thể hiện implementation mới.
- MBean cũ có side effect/lifecycle gì còn tiếp tục không.
- Khi context đóng, tên bị unregister theo ownership của exporter.
- Client đọc/gọi trong khoảng replace có thể gặp gián đoạn.

**Thay MBean đang dùng không phải thao tác nguyên tử đảm bảo không gián đoạn.** Với hệ thống production, cần test lifecycle và concurrency riêng.

## 13. Test owner: không unregister MBean của bên khác

Giả sử một test đăng ký MBean A thủ công, sau đó tạo exporter B có mapping tới ObjectName A.

Với policy `IGNORE_EXISTING`, sau khi đóng exporter B, MBean A nên vẫn còn. Đây là một invariant quan trọng:

~~~text
MBean owned by A
    |
Exporter B sees same ObjectName
    |
B skips registration
    |
B stops
    |
MBean A should remain
~~~

Với `REPLACE_EXISTING`, ownership khó hơn vì B đã unregister A rồi đăng ký B. Cần quyết định rõ ai sở hữu tên sau khi thay.

Trong test đơn giản, dùng `FAIL_ON_EXISTING` để phát hiện xung đột sớm. Không dựa vào `REPLACE_EXISTING` như cách tự động giải quyết mọi xung đột ObjectName.

## 14. Kiểm thử listener registration và cleanup

Nếu exporter cấu hình `NotificationListenerBean`, kiểm thử lifecycle không chỉ có MBean registration mà còn có listener binding.

Ví dụ một MBean hỗ trợ notification:

~~~java
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;
import java.util.concurrent.atomic.AtomicLong;

public class EventMonitor extends NotificationBroadcasterSupport
        implements EventMonitorMBean {

    private final AtomicLong sequence = new AtomicLong();

    @Override
    public void fireEvent() {
        sendNotification(new Notification(
            "com.example.test.event",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Test event"
        ));
    }
}
~~~

`EventMonitorMBean` là interface cần được định nghĩa với `void fireEvent()`.

Các bước test:

1. Context refresh và exporter đăng ký MBean.
2. Listener nhận event khi MBean phát.
3. Context close.
4. ObjectName không còn đăng ký.
5. Listener không tiếp tục nhận event do exporter cũ phát trong test mới.
6. Nếu có listener registration ngoài exporter, test phải tự cleanup để không làm rò tham chiếu.

Notification lifecycle có thể khác tùy broadcaster và cấu hình. Không nên suy ra chỉ kiểm tra `isRegistered(false)` là chứng minh mọi listener đã được giải phóng.

## 15. Test lỗi startup: invalid ObjectName

Ví dụ ObjectName sai cú pháp:

~~~text
com.example.test:type=Cache,name=foo,bar
~~~

Có thể dẫn đến `MalformedObjectNameException` hoặc exception được Spring wrap ở thời điểm cấu hình/đăng ký.

Một test có thể cố ý truyền ObjectName không hợp lệ để xác nhận:

- ApplicationContext báo lỗi có thể hiểu.
- MBean không được đăng ký một phần theo tên lỗi.
- Các MBean đã đăng ký trước đó có được cleanup đúng khi startup thất bại.
- Không để môi trường test bị ô nhiễm giữa các case.

Nếu exporter đăng ký nhiều MBean và một cái thất bại ở giữa, không nên mặc định toàn bộ registration là transaction atomic. Cần kiểm tra chính sách rollback và cleanup thực tế của phiên bản Spring đang dùng.

## 16. Test sự cố khi đóng context

Một MBean có thể có resource bên dưới như executor, cache hoặc connection pool. Hủy đăng ký MBean không tự bảo đảm resource đã được dừng.

Phân biệt:

~~~text
MBeanExporter.destroy()
    -> unregister JMX MBean

Business bean destroy()/close()
    -> stop worker / close resource / release connections
~~~

Những bước này có thể diễn ra trong cùng quá trình đóng context nhưng thuộc trách nhiệm khác nhau. Một integration test tốt sẽ xác nhận cả:

- MBean không còn trong registry.
- Tài nguyên nghiệp vụ đã release theo lifecycle riêng.

Ví dụ kiểm tra một worker service:

~~~java
assertFalse(server.isRegistered(name));
assertTrue(workerService.isStopped());
~~~

Các kiểu `workerService` ở đây là minh họa. Không nên cho rằng `MBeanExporter` tự dừng executor khi unregister MBean.

## 17. Parallel test và ObjectName collisions

Khi test chạy song song, hai test có thể dùng cùng platform MBeanServer và cùng ObjectName, tạo lỗi không ổn định.

Cách giảm rủi ro:

- Tạo MBeanServer cô lập cho mỗi test.
- Dùng ObjectName riêng khi cần.
- Không dùng static shared exporter mutable giữa test.
- Đảm bảo context được close ngay cả khi assertion thất bại.
- Không đăng ký MBean test vào platform server nếu không cần.
- Không dùng random suffix để che bug tên nếu test kiểm tra naming stability.

### Khi bắt buộc dùng platform MBeanServer

Nếu cần kiểm tra tích hợp với platform MBeans/JVM management, có thể dùng platform server nhưng phải đảm bảo ObjectName không xung đột và cleanup cẩn thận. Những test này nên được cách ly khỏi unit tests chạy song song.

## 18. Kiểm thử MBeanInfo trong vòng đời

Một MBean có mặt chưa đủ; metadata có thể sai nếu assembler hoặc proxy khác mong đợi.

~~~java
import javax.management.MBeanInfo;
import javax.management.MBeanAttributeInfo;

MBeanInfo info = server.getMBeanInfo(name);

boolean hasCount = false;

for (MBeanAttributeInfo attr : info.getAttributes()) {
    if ("Count".equals(attr.getName())) {
        hasCount = attr.isReadable();
    }
}

assertTrue(hasCount);
~~~

Đối với annotation exporter, kiểm tra các method được `@ManagedAttribute` và `@ManagedOperation` có mặt. Nếu class được Spring AOP proxy, có thể cần xem cách exporter khám phá metadata gốc và method của proxy.

Khi context đóng, mọi lệnh `getMBeanInfo` qua ObjectName đã unregister nên thất bại theo contract, trừ khi có một owner khác đã đăng ký lại cùng tên.

## 19. Test hủy đăng ký bằng MBeanServerDelegate

JMX cung cấp MBean `JMImplementation:type=MBeanServerDelegate` phát event đăng ký/hủy đăng ký.

Có thể theo dõi:

~~~text
JMX.mbean.registered
JMX.mbean.unregistered
~~~

Tên type thực tế được định nghĩa bằng các hằng `MBeanServerNotification.REGISTRATION_NOTIFICATION` và `UNREGISTRATION_NOTIFICATION`.

Ví dụ:

~~~java
import javax.management.MBeanServerNotification;
import javax.management.NotificationListener;
import javax.management.ObjectName;
import java.util.concurrent.CopyOnWriteArrayList;

ObjectName delegate = new ObjectName(
    "JMImplementation:type=MBeanServerDelegate"
);

CopyOnWriteArrayList<MBeanServerNotification> events =
    new CopyOnWriteArrayList<>();

NotificationListener listener = (notification, handback) -> {
    if (notification instanceof MBeanServerNotification event) {
        events.add(event);
    }
};

server.addNotificationListener(
    delegate, listener, null, null
);
~~~

Sau khi exporter start/stop, filter events theo `event.getMBeanName().equals(name)`. Khi kết thúc test, remove listener khỏi delegate.

**Lưu ý:** event delivery phụ thuộc cơ chế notification; với test bất đồng bộ phải chờ bounded. Việc đọc `server.isRegistered(name)` vẫn là assertion đơn giản nhất để xác định trạng thái registry ở từng mốc.

## 20. Các lỗi phổ biến khi kiểm thử exporter

| Hiện tượng | Nguyên nhân | Hướng khắc phục |
| --- | --- | --- |
| MBean không xuất hiện sau refresh | Exporter không tạo hoặc server không đúng | Kiểm tra Spring config và MBeanServer |
| MBean xuất hiện nhưng operation thiếu | Assembler/annotation metadata sai | Xem `MBeanInfo` |
| Context close nhưng MBean còn | Exporter không sở hữu registration hoặc lifecycle lỗi | Kiểm tra owner và destroy |
| Test thứ hai gặp `InstanceAlreadyExistsException` | Test trước chưa cleanup hoặc cùng ObjectName | Cô lập server và close context |
| Test chạy độc lập được nhưng parallel fail | Dùng platform MBeanServer chung | newMBeanServer riêng cho test |
| Annotation có nhưng không export | Bean không ở context hoặc thiếu annotation exporter | Component registration và exporter |
| `REPLACE_EXISTING` khiến test qua sai | Che giấu xung đột/leak | Dùng fail policy để phát hiện bug |
| Context startup lỗi để lại MBean | Partial registration hoặc cleanup thiếu | Test failure path và finally |
| Stop exporter nhưng resource vẫn chạy | Unregister không tương đương business stop | Kiểm tra lifecycle service riêng |
| Listener nhận trùng notification | Listener đăng ký nhiều lần | Cleanup/re-subscribe đúng |
| Wrong MBeanServer | Test đọc platform server thay server được cấu hình | Inject same server |
| Assertion ngẫu nhiên thất bại | Race trong startup/shutdown hoặc test async | Dùng latch/state observation |

## 21. Bài tập thực hành

**Mục tiêu:** xây test xác nhận lifecycle `MBeanExporter` với một Standard MBean và một annotation MBean.

### Phần A — Standard MBean

1. Tạo `CounterAdminMBean` và `CounterAdmin`.
2. Tạo `MBeanServerFactory.newMBeanServer()`.
3. Tạo `AnnotationConfigApplicationContext`.
4. Đăng ký `MBeanExporter` ánh xạ CounterAdmin tới ObjectName.
5. Trước refresh, xác nhận `isRegistered=false`.
6. Sau refresh, xác nhận `isRegistered=true`.
7. Đọc attribute `Count`.
8. Gọi `reset()` và kiểm tra `Count=0`.
9. Đóng context trong `finally`.
10. Xác nhận `isRegistered=false`.

### Phần B — Annotation MBean

1. Tạo `WorkerManagement` với `@ManagedResource`.
2. Bật `AnnotationMBeanExporter` trong context cô lập.
3. Xác nhận ObjectName đã đăng ký.
4. Đọc `Paused`.
5. Gọi `pause()`.
6. Kiểm tra `Paused=true`.
7. Đóng context.
8. Xác nhận ObjectName không còn.

### Phần C — Failure paths

1. Đăng ký sẵn một MBean cùng ObjectName.
2. Chạy exporter với `FAIL_ON_EXISTING`.
3. Xác nhận startup báo lỗi và MBean cũ còn nguyên.
4. Chạy trường hợp `IGNORE_EXISTING` với owner rõ.
5. Test context close không hủy đăng ký nhầm MBean thuộc owner khác.
6. Test restart context hai lần.
7. Chạy test song song với MBeanServer riêng để tránh va chạm.

## 22. Câu hỏi tự kiểm tra

**1. Khi nào MBeanExporter đăng ký MBean?**

Thông thường trong lifecycle khởi tạo của Spring bean/exporter sau khi các dependency đã sẵn sàng, dưới sự điều khiển của ApplicationContext.

**2. Có thể kiểm tra exporter stop bằng `Lifecycle.stop()` không?**

Không nên mặc định. Với MBeanExporter thường kiểm tra `destroy()` hoặc context close và registry sau shutdown.

**3. Vì sao cần MBeanServer riêng?**

Để test độc lập, tránh xung đột với platform MBeans và không làm ô nhiễm các test khác.

**4. `isRegistered(false)` sau context close chứng minh điều gì?**

Chứng minh ObjectName không còn đăng ký trong server đã kiểm tra. Nó không tự chứng minh mọi resource hoặc listener đã cleanup hoàn toàn.

**5. Vì sao không nên bật `REPLACE_EXISTING` để test luôn chạy qua?**

Vì policy này có thể che giấu ObjectName leak hoặc ownership bug.

**6. Test cần kiểm tra thuộc tính/operation không?**

Có. Registry có MBean không bảo đảm metadata của nó đúng hợp đồng mong đợi.

**7. Nếu exporter fail giữa lúc đăng ký nhiều MBean thì sao?**

Không được giả định atomic rollback. Cần kiểm tra failure path, cleanup và trạng thái registry thực tế.

**8. Test context khởi động lại hữu ích thế nào?**

Nó giúp phát hiện stale registration hoặc listener leak khiến lần chạy thứ hai thất bại hoặc nhận event trùng.

## 23. Tổng kết

Kiểm thử exporter start/stop trong Spring Framework JMX là kiểm thử **vòng đời đăng ký MBean**:

~~~text
Before refresh: not registered
After refresh:  registered
After close:    not registered
~~~

Để có kết quả đáng tin cậy:

- Dùng MBeanServer riêng.
- Kiểm tra ObjectName trước/sau và metadata khi đang chạy.
- Đóng ApplicationContext trong `finally`.
- Kiểm tra nhiều vòng start/stop và các trường hợp xung đột.
- Tách việc unregister MBean khỏi việc dừng resource nghiệp vụ.
- Kiểm tra notification listener cleanup khi exporter quản lý listener.
- Xác định owner của từng MBean để tránh unregister nhầm.

**MBeanExporter vận hành đúng khi MBean cần quản trị được đăng ký trong lifecycle của context và được dọn dẹp đúng lúc, không để lại registration hoặc listener ngoài quyền sở hữu.**

### Tài liệu tham khảo

- Spring Framework Reference — JMX Exporting: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Spring Framework API — MBeanExporter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework API — AnnotationMBeanExporter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/AnnotationMBeanExporter.html
- Java SE API — MBeanServer: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE API — MBeanServerFactory: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerFactory.html
