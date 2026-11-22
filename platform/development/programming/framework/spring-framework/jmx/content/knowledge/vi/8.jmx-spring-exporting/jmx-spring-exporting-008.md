# Vòng đời export và unexport khi Spring context khởi động, dừng

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Mô tả thời điểm Spring Framework đăng ký (export) một bean thành JMX MBean khi ApplicationContext khởi động.
- Giải thích vì sao phải hủy đăng ký (unexport) MBean khi context đóng và trường hợp nào cần tự quản lý vòng đời.
- Phân biệt vòng đời của đối tượng Spring bean, MBeanExporter, MBeanServer và MBean registration.
- Hiểu cách ObjectName, RegistrationPolicy và ApplicationContext lifecycle ảnh hưởng đến lỗi đăng ký trùng tên.
- Viết cấu hình Java cho MBeanExporter và quan sát việc đăng ký/hủy đăng ký bằng MBeanServer.
- Tránh rò rỉ MBean hoặc thao tác nhầm instance khi ứng dụng restart, chạy nhiều context, hoặc dùng MBeanServer chia sẻ.

## 1. Export/unexport thực chất là gì?

Trong Spring Framework, **JMX export** là quá trình đăng ký một Spring-managed bean hoặc một đối tượng quản trị được tạo từ bean đó vào **MBeanServer**. Sau khi export thành công, công cụ JMX có thể tìm MBean theo ObjectName, đọc attributes hoặc gọi operations được công bố.

**Unexport** là hủy đăng ký MBean khỏi MBeanServer. Điều này loại bỏ tên quản trị khỏi registry; nó không nhất thiết có nghĩa là Java object bị hủy ngay lập tức, JVM kết thúc, hoặc toàn bộ connector JMX đóng lại.

Sơ đồ:

\`\`\`text
Spring ApplicationContext
        |
        | khởi tạo bean + MBeanExporter
        v
MBeanExporter
        |
        | register vào MBeanServer
        v
MBeanServer
        |
        | ObjectName -> MBean được công bố
        v
JConsole / JMX client
        |
        | ApplicationContext đóng
        v
MBeanExporter unregister
        |
        v
ObjectName không còn trong registry
\`\`\`

Hai câu hỏi cần tách:

1. **Object Java còn tồn tại hay không?** Phụ thuộc vòng đời bean, reference, garbage collection và JVM.
2. **JMX client còn tìm thấy MBean theo ObjectName hay không?** Phụ thuộc việc đăng ký/hủy đăng ký với MBeanServer.

Unexport tác động trực tiếp đến câu hỏi thứ hai.

## 2. Các đối tượng và vòng đời liên quan

| Thành phần | Trách nhiệm | Vòng đời thường gặp |
|---|---|---|
| ApplicationContext | Tạo và quản lý bean, xử lý đóng context | Từ refresh đến close |
| Spring-managed bean | Chứa logic/trạng thái được quản trị | Theo scope và cấu hình Spring |
| MBeanExporter | Chọn bean, tạo/đăng ký giao diện quản trị, theo dõi đăng ký để dọn dẹp | Bean hạ tầng trong context |
| MBeanServer | Registry và API JMX | Thường sống cùng JVM, có thể được nhiều context dùng chung |
| ObjectName | Định danh MBean trong một MBeanServer | Có hiệu lực khi đăng ký còn tồn tại |
| JMX connector/client | Cho phép công cụ truy cập MBeanServer | Có vòng đời kết nối riêng, không đồng nhất với exporter |

Trong ứng dụng Java thông thường, platform MBeanServer được lấy qua:

\`\`\`java
MBeanServer platformServer =
        ManagementFactory.getPlatformMBeanServer();
\`\`\`

Platform MBeanServer thường tồn tại cùng JVM. Khi một Spring context đóng, platform MBeanServer vẫn có thể tồn tại, và các platform MBean của JVM vẫn hiện diện. Chỉ các đăng ký do exporter tương ứng quản lý mới thuộc phạm vi cleanup của exporter đó.

## 3. Khi context khởi động, export diễn ra lúc nào?

Trong cách cấu hình phổ biến, MBeanExporter là một Spring bean hạ tầng. Nó tham gia quá trình khởi tạo ApplicationContext và đăng ký các MBean khi các bean liên quan đã sẵn sàng.

Luồng khái niệm:

1. Ứng dụng tạo hoặc refresh ApplicationContext.
2. Spring phân tích cấu hình, tạo các bean cần thiết.
3. Spring khởi tạo MBeanExporter và cung cấp MBeanServer, map các đối tượng cần export, assembler và naming strategy nếu có.
4. MBeanExporter thực hiện đăng ký các đối tượng được chọn theo ObjectName.
5. ApplicationContext trở nên sẵn sàng để ứng dụng và JMX client tương tác với các MBean đã đăng ký.

Không nên nhầm việc một bean được **khởi tạo** với việc MBean đó đã được **export**. Một ứng dụng có thể tạo bean thành công nhưng export thất bại vì ObjectName trùng, MBeanServer không phù hợp, hoặc contract JMX không hợp lệ.

### Bean được tạo trước hay sau export?

Một đối tượng cần tồn tại để được đăng ký, nhưng thứ tự chính xác giữa các bean khác nhau còn phụ thuộc dependency graph, lazy initialization, exporter configuration và cơ chế proxy. Nếu code muốn dùng MBean từ một bước startup khác, cần xác định rõ thứ tự phụ thuộc hoặc kiểm tra đăng ký thay vì mặc định mọi MBean đã sẵn sàng từ đầu quá trình refresh.

### Sự khác biệt giữa container đã chạy và MBean đã sẵn sàng

Một log “Spring context initialized” hoặc “web server started” chưa đủ chứng minh tất cả các MBean mong muốn đã được đăng ký. Cách kiểm chứng trực tiếp là gọi:

\`\`\`java
server.isRegistered(objectName)
\`\`\`

trên đúng MBeanServer mà exporter đang dùng.

## 4. Ví dụ cấu hình Spring Framework với MBeanExporter

Ta xây một Standard MBean, đăng ký nó qua MBeanExporter, rồi quan sát trạng thái đăng ký.

### 4.1. Interface quản trị

Tệp CacheMonitorMBean.java:

\`\`\`java
package example.jmx;

public interface CacheMonitorMBean {
    int getEntryCount();
    void clear();
}
\`\`\`

### 4.2. Implementation

Tệp CacheMonitor.java:

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

public class CacheMonitor implements CacheMonitorMBean {
    private final AtomicInteger entryCount =
            new AtomicInteger(10);

    @Override
    public int getEntryCount() {
        return entryCount.get();
    }

    @Override
    public void clear() {
        entryCount.set(0);
    }
}
\`\`\`

Ở đây MBean interface công bố thuộc tính EntryCount và operation clear(). Đây chỉ là mô hình minh họa. Trong hệ thống thực, thao tác xóa cache phải gắn vào cache thật và có kiểm soát quyền.

### 4.3. Cấu hình exporter

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

@Configuration
public class JmxExportConfig {

    @Bean
    public CacheMonitor cacheMonitor() {
        return new CacheMonitor();
    }

    @Bean
    public MBeanExporter cacheMBeanExporter(CacheMonitor monitor) {
        MBeanExporter exporter = new MBeanExporter();

        exporter.setServer(
                ManagementFactory.getPlatformMBeanServer()
        );

        exporter.setBeans(Map.of(
                "learning.jmx:type=CacheMonitor,name=Primary",
                monitor
        ));

        exporter.setRegistrationPolicy(
                RegistrationPolicy.FAIL_ON_EXISTING
        );

        return exporter;
    }
}
\`\`\`

Chú ý:

- setServer() chọn rõ platform MBeanServer.
- setBeans() ánh xạ một ObjectName tới bean cần export.
- CacheMonitor và CacheMonitorMBean tuân theo Standard MBean convention.
- FAIL_ON_EXISTING xác định hành vi khi tên đã được dùng.

Đăng ký được quản lý bởi exporter. Không cần đồng thời gọi registerMBean() thủ công cho cùng tên, vì như vậy dễ gây đăng ký trùng.

### 4.4. Tạo và đóng ApplicationContext

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class JmxLifecycleDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
                "learning.jmx:type=CacheMonitor,name=Primary"
        );

        System.out.println(
                "Before context: " + server.isRegistered(name)
        );

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        JmxExportConfig.class)) {

            System.out.println(
                    "After refresh: " + server.isRegistered(name)
            );
        }

        System.out.println(
                "After close: " + server.isRegistered(name)
        );
    }
}
\`\`\`

Khi không có đăng ký trùng từ bên ngoài và exporter hoạt động bình thường, kết quả mong đợi là:

\`\`\`text
Before context: false
After refresh: true
After close: false
\`\`\`

Đây là **kết quả dự kiến trong môi trường thử nghiệm riêng**. Nếu JVM đã có MBean tại ObjectName đó, dòng đầu có thể là true và policy FAIL_ON_EXISTING có thể khiến refresh thất bại.

Ví dụ đặt context trong try-with-resources nên close() được gọi cả khi có lỗi sau khi context tạo xong.

## 5. Khi context đóng, unexport diễn ra như thế nào?

Spring Framework cung cấp các callback dọn dẹp cho bean quản lý vòng đời. MBeanExporter thực hiện cleanup khi bản thân exporter bị destroy, bao gồm việc hủy đăng ký những MBean thuộc phạm vi nó theo dõi.

Luồng điển hình:

\`\`\`text
context.close()
    |
    v
Spring thực hiện shutdown callbacks
    |
    v
MBeanExporter cleanup
    |
    v
unregister MBeans do exporter quản lý
    |
    v
MBeanServer.isRegistered(name) -> false
\`\`\`

Hủy đăng ký cho phép:

- Giải phóng ObjectName để một context mới có thể đăng ký.
- Ngăn client tiếp tục thao tác trên MBean thuộc context đã đóng.
- Tránh giữ những tham chiếu không cần thiết trong registry.
- Làm rõ instance nào đang sở hữu giao diện quản trị.

Tuy nhiên, việc unexport không tự động bảo đảm **mọi thread, socket, tài nguyên hoặc tác vụ** của bean nghiệp vụ đã dừng. Vòng đời tài nguyên đó do chính bean, container, executor hoặc thành phần tương ứng quản lý.

### close khác với process shutdown

Nếu ApplicationContext đóng nhưng JVM còn chạy, việc unregister rất quan trọng. Khi toàn JVM kết thúc, MBeanServer của process cũng mất theo, nhưng vẫn nên để Spring cleanup đúng khi có thể. Quy trình ứng dụng có thể tạo lại context mà không khởi động lại JVM; lúc đó đăng ký cũ tồn tại sẽ gây xung đột nếu cleanup không diễn ra.

### Đóng bất thường

Nếu JVM bị kill ngay lập tức, mất điện hoặc process crash, callback destroy không được bảo đảm sẽ chạy. MBeanServer biến mất cùng process, nên registry trong heap của JVM không cần một thao tác unregister sau crash. Tuy vậy các tài nguyên hoặc đăng ký **bên ngoài JVM** có thể cần cơ chế cleanup riêng; MBeanExporter không thay thế các cơ chế đó.

## 6. RegistrationPolicy và xử lý tên trùng

Khi MBeanExporter cố đăng ký một ObjectName đã tồn tại trong cùng MBeanServer, hành vi phụ thuộc RegistrationPolicy.

Ba chính sách quan trọng:

| Policy | Ý nghĩa | Tình huống |
|---|---|---|
| FAIL_ON_EXISTING | Báo lỗi khi tên đã tồn tại | Muốn phát hiện cấu hình trùng/sai ownership |
| IGNORE_EXISTING | Bỏ qua đăng ký mới nếu tên đã tồn tại | Muốn giữ MBean hiện có mà không thay thế |
| REPLACE_EXISTING | Thay thế MBean hiện có bằng đăng ký mới | Chỉ dùng khi quyền sở hữu và tác động được xác định rõ |

**FAIL_ON_EXISTING** thường hữu ích khi học về vòng đời vì giúp phát hiện ngay rò rỉ đăng ký. Nếu một context mới không thể refresh do InstanceAlreadyExistsException, cần xác định MBean nào còn giữ ObjectName.

**IGNORE_EXISTING** không có nghĩa là MBean mới đã được export thành công. Nếu tên đã được giữ bởi một context khác, client tiếp tục tương tác với MBean đang tồn tại.

**REPLACE_EXISTING** có thể gây ảnh hưởng đến MBean thuộc component/context khác nếu cả hai dùng chung MBeanServer. Không sử dụng nó như cách mặc định để che lỗi trùng tên.

Một lưu ý quan trọng: khi exporter bỏ qua một đăng ký đã tồn tại, không nên giả định nó sở hữu hoặc có quyền hủy MBean bị bỏ qua. Phạm vi cleanup cần được xem theo registry và hành vi exporter thực tế.

## 7. ObjectName và quản lý nhiều ApplicationContext

Một JVM có thể chứa nhiều ApplicationContext, ví dụ:

- Parent context và child web context.
- Nhiều context được tạo bởi chương trình thử nghiệm.
- Một host Java chứa nhiều application module.
- Context mới được refresh trong cùng JVM mà context cũ chưa đóng.

Nếu các context dùng chung platform MBeanServer và cùng export:

\`\`\`text
learning.jmx:type=CacheMonitor,name=Primary
\`\`\`

thì chúng sẽ xung đột về ObjectName.

Cách thiết kế:

1. Xác định context nào thực sự sở hữu management interface.
2. Export MBean tại một cấp context nhất quán.
3. Tránh exporter quét trùng bean ở parent/child context.
4. Đặt ObjectName đủ phân biệt theo service, module hoặc instance khi thực sự cần nhiều instance cùng tồn tại.
5. Đóng context đúng vòng đời trước khi mở context mới dùng cùng tên.
6. Nếu dùng nhiều MBeanServer, biết rõ client đang kết nối server nào.

Ví dụ hai tên khác nhau:

\`\`\`text
learning.jmx:type=CacheMonitor,application=Billing,name=Primary
learning.jmx:type=CacheMonitor,application=Shipping,name=Primary
\`\`\`

Tên được chọn phải duy nhất trong MBeanServer và có cấu trúc rõ ràng. Không cần thêm một ID ngẫu nhiên cho mỗi lần khởi động nếu điều đó gây khó khăn khi tooling tìm lại MBean; hãy chọn naming scheme gắn với cấu trúc triển khai.

## 8. Vòng đời của MBeanExporter khác với MBeanServer

Một MBeanExporter là **đối tượng hạ tầng Spring**. Nó dùng MBeanServer hiện có hoặc một MBeanServer được tìm/tạo theo cấu hình. Nhưng khi exporter bị hủy, điều đó không có nghĩa toàn bộ MBeanServer bị hủy.

Ví dụ:

\`\`\`java
MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();
\`\`\`

Đây là platform server của JVM. Các MBean nền tảng như memory, threads hoặc class loading vẫn có thể tồn tại dù một Spring context đóng.

Khi xác minh cleanup, không kiểm tra rằng số lượng MBean trên server phải bằng 0. Hãy kiểm tra đúng **ObjectName do context của bạn quản lý**.

\`\`\`java
boolean registered = server.isRegistered(
    new ObjectName("learning.jmx:type=CacheMonitor,name=Primary")
);
\`\`\`

Số lượng MBean toàn server có thể thay đổi vì nhiều thành phần khác và không phản ánh chính xác lifecycle của một bean.

## 9. Export và Spring bean lifecycle

Spring có nhiều callback vòng đời như constructor, dependency injection, BeanPostProcessor, init callbacks, ApplicationContext refresh, ContextClosedEvent và destroy callbacks.

Không nên mặc định rằng thứ tự của mọi callback trong hệ thống sẽ luôn phù hợp với một đoạn code độc lập đang truy cập JMX. Cách an toàn khi thiết kế là mô tả rõ dependency và thời điểm consumer bắt đầu cần MBean.

### Điều gì xảy ra nếu bean là lazy?

Một bean lazy có thể chưa được tạo cho đến khi có nhu cầu. Nếu MBeanExporter được cấu hình ánh xạ trực tiếp tới đối tượng/bean, quá trình export có thể ảnh hưởng thời điểm khởi tạo. Hành vi cụ thể phụ thuộc cách cấu hình exporter và kiểu tham chiếu; không nên suy ra rằng mọi lazy bean đều chắc chắn được export sau khi context refresh.

Khi mục tiêu là export MBean ngay lúc startup, hãy cấu hình dependency và exporter phù hợp, rồi kiểm chứng bằng isRegistered().

### Điều gì xảy ra với prototype bean?

Prototype bean không có cùng semantics destroy callback tự động như singleton. Nếu bạn tự đăng ký một prototype object vào MBeanServer, phải bảo đảm ai sở hữu và hủy đăng ký object đó. Không dựa hoàn toàn vào lifecycle của prototype để unregister.

MBeanExporter với một tập managed resources xác định có thể quản lý đăng ký của chúng; tuy nhiên nếu ứng dụng chủ động đăng ký prototype/new instance ngoài exporter, trách nhiệm cleanup vẫn thuộc code đã đăng ký.

### Bean bị thay đổi reference?

MBeanServer có thể giữ tham chiếu tới đối tượng được đăng ký. Nếu một component nội bộ được thay bằng instance khác, ObjectName không tự động trỏ tới instance mới trừ khi có cơ chế re-registration hoặc wrapper/proxy có hành vi phù hợp.

Cần phân biệt cập nhật state bên trong MBean và thay thế chính object MBean.

## 10. Đăng ký thủ công khác export do Spring quản lý

### 10.1. Đăng ký thủ công

\`\`\`java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName("learning.jmx:type=Manual,name=One");

server.registerMBean(manualBean, name);
\`\`\`

Khi dùng cách này, **code của bạn** chịu trách nhiệm unregister:

\`\`\`java
server.unregisterMBean(name);
\`\`\`

Nếu một Spring bean tự đăng ký MBean trong init callback nhưng không unregister khi destroy, có nguy cơ để lại đăng ký khi context đóng mà JVM vẫn còn.

### 10.2. MBeanExporter của Spring

\`\`\`java
exporter.setBeans(Map.of(
        "learning.jmx:type=CacheMonitor,name=Primary",
        cacheMonitor
));
\`\`\`

Exporter theo dõi phần registration mà nó quản lý và thực hiện cleanup tương ứng khi destroy. Đây thường là lựa chọn rõ trách nhiệm hơn khi MBean thuộc về Spring ApplicationContext.

### 10.3. Tránh đăng ký hai lần

Đừng vừa cấu hình MBeanExporter cho cùng một ObjectName, vừa gọi registerMBean() thủ công ở @PostConstruct cho chính object đó, trừ khi có lý do và cơ chế điều phối rõ ràng.

Trùng đăng ký có thể dẫn đến:

- InstanceAlreadyExistsException.
- Exporter startup thất bại.
- MBean bị thay thế ngoài ý muốn khi dùng REPLACE_EXISTING.
- Unregister nhầm tên khi một bên không biết bên kia đã thay đăng ký.

Nguyên tắc đơn giản: **một ObjectName trong một MBeanServer nên có một chủ thể quản lý vòng đời rõ ràng**.

## 11. Ví dụ tự quản lý unregister với lifecycle callback

Nếu bài toán bắt buộc gọi registerMBean() trực tiếp, hãy ghép đăng ký và hủy đăng ký trong cùng một Spring-managed component.

Ví dụ:

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.InitializingBean;

public class ManualJmxRegistration
        implements InitializingBean, DisposableBean {

    private final MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

    private final ObjectName name;
    private boolean registered;

    public ManualJmxRegistration() throws Exception {
        this.name = new ObjectName(
                "learning.jmx:type=CacheMonitor,name=Manual"
        );
    }

    @Override
    public void afterPropertiesSet() throws Exception {
        server.registerMBean(new CacheMonitor(), name);
        registered = true;
    }

    @Override
    public void destroy() throws Exception {
        if (registered && server.isRegistered(name)) {
            server.unregisterMBean(name);
            registered = false;
        }
    }
}
\`\`\`

Ví dụ này minh họa tương ứng giữa init và destroy callbacks. Trong hệ thống thực, cần xử lý thất bại partial registration, ownership, thread safety và trường hợp MBean tại tên đó bị thay thế bởi thành phần khác.

Nếu có thể sử dụng MBeanExporter, thường không cần tự viết toàn bộ lifecycle management như trên.

## 12. Export khi context refresh và vấn đề đăng ký lại

Một ApplicationContext có thể được refresh trong những bối cảnh cho phép, hoặc ứng dụng có thể tạo context mới nhiều lần. Khi một exporter mới bắt đầu đăng ký MBean trong MBeanServer còn sống:

- Nếu context trước đã unregister đầy đủ, tên có thể được tái sử dụng.
- Nếu context trước vẫn chạy, đăng ký trùng có thể xảy ra.
- Nếu context trước đóng bất thường mà JVM vẫn chạy nhưng cleanup không được gọi, registry có thể còn MBean cũ.
- Nếu một MBean khác đã chiếm tên, cần xác định ownership trước khi dùng policy thay thế.

Không chọn REPLACE_EXISTING chỉ để giúp một bài test pass nếu thật ra có hai context đang đăng ký cùng tên. Hãy điều tra vòng đời các context và tên đăng ký.

### Test bằng ApplicationContext độc lập

Bạn có thể viết một kiểm tra integration (khi cần) gồm:

1. Đọc isRegistered(name) trước khi tạo context.
2. Tạo AnnotationConfigApplicationContext.
3. Xác nhận isRegistered(name) là true.
4. Đóng context.
5. Xác nhận isRegistered(name) trở lại false.
6. Tạo context mới và xác nhận export thành công lần nữa.

Khi test chạy song song, dùng MBeanServer độc lập hoặc ObjectName được phân vùng phù hợp để không xung đột với những test khác. Đừng cố xóa mọi MBean trên platform server vì nó có thể thuộc về các phần khác của JVM.

## 13. Lắng nghe registration và unregistration event

MBeanServer cũng có thể phát notification về việc một MBean được đăng ký hoặc hủy đăng ký. Trong JMX, MBeanServerDelegate là nguồn cung cấp notification quản trị liên quan registry.

Các type tiêu biểu do MBeanServerNotification định nghĩa:

\`\`\`java
MBeanServerNotification.REGISTRATION_NOTIFICATION
MBeanServerNotification.UNREGISTRATION_NOTIFICATION
\`\`\`

Cần phân biệt:

- **MBeanServer registration notification:** cho biết một ObjectName được đăng ký/hủy khỏi registry.
- **Notification nghiệp vụ do MBean phát:** ví dụ cache cleared, queue overloaded; đây là contract riêng của MBean đó.

Hai loại notification không tương đương.

Để theo dõi lifecycle, có thể đăng ký listener với MBeanServerDelegate theo ObjectName hệ thống, hoặc đơn giản kiểm tra isRegistered() tại các thời điểm cần thiết. Cần tránh để listener quản trị tồn tại lâu hơn vòng đời component sở hữu nó.

## 14. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không thấy MBean sau startup | Exporter chưa chạy, không có bean trong map, sai MBeanServer hoặc lỗi đăng ký | Kiểm tra cấu hình, log export và isRegistered() trên đúng server |
| InstanceAlreadyExistsException | ObjectName trùng | Xác định context/bean sở hữu tên và RegistrationPolicy |
| MBean còn sau context.close() | Đăng ký thủ công, exporter không sở hữu tên, destroy callback không chạy hoặc context chưa thật sự đóng | Truy tìm nơi register/unregister và trạng thái context |
| MBean biến mất sau restart | JVM cũ đã dừng hoặc context mới chưa export | Kết nối đúng JVM mới và kiểm tra startup |
| JConsole vẫn thấy tên cũ | Client chưa refresh, kết nối nhầm JVM hoặc còn registration thật | Refresh và xác nhận qua server.isRegistered() |
| MBean hoạt động nhưng target bean đã dừng | Registry giữ object/proxy ngoài lifecycle | Kiểm tra ownership, destroy và unexport |
| Hai context đè MBean của nhau | Cùng server, cùng ObjectName, REPLACE_EXISTING | Dùng naming scheme và chính sách sở hữu rõ |
| Số lượng MBean toàn server không về 0 | Platform MBeans và đăng ký khác vẫn tồn tại | Kiểm tra ObjectName cụ thể |
| Không thể export Standard MBean | Interface naming/metadata không đúng | Kiểm tra Standard MBean contract, assembler và NotCompliantMBeanException |
| Context refresh fail nhưng tên vẫn tồn tại | Có đăng ký trùng hoặc một registration còn từ bối cảnh khác | Đọc exception và xác định owner trước khi sửa |

## 15. Chẩn đoán theo vòng đời

Khi có lỗi, điều tra lần lượt:

**A. Trước startup**

- MBeanServer nào sẽ được dùng?
- ObjectName nào dự kiến đăng ký?
- Có MBean nào đang dùng tên đó không?
- Context nào được quyền quản lý registration?

**B. Sau context refresh**

- MBeanExporter đã khởi tạo chưa?
- Có exception liên quan register/assembler/ObjectName không?
- server.isRegistered(name) trả về true không?
- JMX client đang kết nối đúng JVM/server không?

**C. Khi context đóng**

- context.close() thực sự được gọi chưa?
- Destroy callbacks có chạy không?
- Exporter có sở hữu MBean mà bạn đang kiểm tra không?
- server.isRegistered(name) sau đóng còn true không?

**D. Khi khởi động lại**

- JVM/process có đổi không?
- Tên MBean cũ còn tồn tại trong cùng server không?
- Có parent/child context hoặc một instance khác đang export trùng tên không?
- RegistrationPolicy đang làm gì khi tên đã có?

Câu hỏi trọng tâm là: **ai đã đăng ký ObjectName và ai chịu trách nhiệm unregister nó?**

## 16. Tình huống thực tế

### Tình huống 1: Spring application khởi động bình thường

Ứng dụng chỉ có một context và một MBeanExporter. Khi context refresh hoàn tất, MBean được đăng ký; khi close, exporter hủy đăng ký. Đây là vòng đời mong muốn.

### Tình huống 2: Ứng dụng có parent và child context

Một bean bị export hai lần cùng ObjectName. Context thứ hai có thể gặp InstanceAlreadyExistsException. Cần xác định một nơi duy nhất chịu trách nhiệm export hoặc dùng tên riêng cho các instance thật sự khác nhau.

### Tình huống 3: Test chạy lại trong cùng JVM

Test đầu tạo context nhưng không close. Test tiếp theo tạo context mới cùng ObjectName và thất bại. Sửa bằng cách đóng context đúng vòng đời, dùng resource management phù hợp hoặc tách biệt MBeanServer/ObjectName trong test.

### Tình huống 4: MBean được đăng ký trực tiếp

Một @PostConstruct gọi registerMBean(), nhưng không có @PreDestroy hay DisposableBean unregister. Context đóng mà JVM vẫn chạy khiến MBean có thể còn trong registry. Cần ghép callback cleanup hoặc chuyển sang MBeanExporter.

### Tình huống 5: Service chạy trong container

JVM restart sẽ tạo MBeanServer mới. Một JMX client giữ kết nối tới process cũ không tự động chuyển sang process mới. Cần kết nối lại, kiểm tra ObjectName và bảo mật của endpoint mới, đồng thời hiểu rằng registration mới chỉ xuất hiện sau startup.

## 17. Bài tập thực hành

**Bài tập A — Quan sát lifecycle**

Tạo ba class CacheMonitorMBean, CacheMonitor và JmxExportConfig như ví dụ. Chạy JmxLifecycleDemo và xác nhận:

\`\`\`text
Before context: false
After refresh: true
After close: false
\`\`\`

Hãy giải thích tại sao server vẫn tồn tại sau context.close() nhưng ObjectName đã biến mất.

**Bài tập B — Mô phỏng trùng tên**

Giữ context A đang chạy rồi thử tạo context B với cùng JmxExportConfig, cùng platform MBeanServer và ObjectName. Dự đoán hành vi với FAIL_ON_EXISTING. Sau đó đóng A trước khi tạo B và quan sát khác biệt.

**Bài tập C — Tìm MBean rò rỉ**

Tạo một Spring bean tự register trong callback khởi tạo nhưng không unregister. Đóng context và dùng isRegistered(name) kiểm tra. Bổ sung destroy callback phù hợp, chạy lại và so sánh.

**Bài tập D — Đánh giá policy**

Một hệ thống có hai module cùng muốn export ObjectName learning.jmx:type=CacheMonitor,name=Primary. Hãy giải thích rủi ro của IGNORE_EXISTING và REPLACE_EXISTING, sau đó đề xuất ObjectName hoặc ownership phù hợp.

## 18. Ghi nhớ

- **Export** là đăng ký MBean vào một MBeanServer; **unexport** là hủy đăng ký khỏi registry.
- Khi MBeanExporter là Spring-managed bean, quá trình đăng ký và cleanup thường gắn với khởi tạo và destroy của ApplicationContext.
- **Unexport không đồng nghĩa hủy JVM**, xóa toàn bộ MBeanServer hay dừng mọi tài nguyên khác của bean.
- Chỉ kiểm tra đúng ObjectName trên đúng MBeanServer, không dùng tổng số MBean làm điều kiện lifecycle.
- Đăng ký thủ công yêu cầu cơ chế unregister thủ công hoặc lifecycle callback tương ứng.
- **RegistrationPolicy** ảnh hưởng cách xử lý ObjectName trùng; nó không thay thế thiết kế ownership.
- Với nhiều context hoặc test trong cùng JVM, phải bảo đảm tên duy nhất hoặc thống nhất một chủ thể quản lý.
- Khi xảy ra lỗi, truy ngược hành trình: **context startup → exporter registration → MBeanServer → context close → exporter cleanup**.

## Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — MBeanExporter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework API — RegistrationPolicy: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/support/RegistrationPolicy.html
- Java SE 21 API — MBeanServer: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 API — MBeanServerNotification: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerNotification.html
