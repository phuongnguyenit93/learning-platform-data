# Giám sát log khi đăng ký MBean thất bại trong Spring JMX

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Hiểu quá trình **Spring MBeanExporter** đăng ký MBean vào **MBeanServer** và những tình huống làm đăng ký thất bại.
- Phân biệt lỗi đăng ký thực sự với trường hợp bean bị **bỏ qua theo registration policy** hoặc JMX exporter chưa chạy.
- Biết vai trò của **FAIL_ON_EXISTING**, **IGNORE_EXISTING**, **REPLACE_EXISTING** trong quá trình xử lý \`ObjectName\` trùng.
- Đọc log và chuỗi nguyên nhân của exception để xác định nhóm lỗi: trùng tên, sai metadata, sai kiểu MBean, quyền truy cập hoặc lifecycle.
- Cấu hình logging cho Spring JMX exporter và tạo thông tin chẩn đoán an toàn, không phơi bày secrets.
- Kiểm tra registry thực tế bằng \`MBeanServer.isRegistered\`, \`queryNames\` và \`getMBeanInfo\` sau khi khởi động.
- Phân biệt listener thông báo đăng ký thành công với cơ chế phát hiện, ghi nhận và cảnh báo **đăng ký thất bại**.
- Xây dựng quy trình kiểm tra lỗi và quan sát có thể lặp lại trong môi trường Spring Framework, Spring Boot và Java Management Extensions (JMX).

## 2. Bối cảnh: một MBean được đăng ký như thế nào?

Trong ứng dụng Spring Framework, \`MBeanExporter\` có thể nhận danh sách bean được cấu hình tường minh hoặc tự phát hiện. Exporter chọn \`ObjectName\`, tạo/thu thập metadata quản trị phù hợp rồi đăng ký MBean thông qua \`MBeanServer\`.

\`\`\`text
ApplicationContext khởi tạo
           |
           v
      MBeanExporter
           |
           +--> Chọn bean cần export
           |
           +--> Tạo ObjectName
           |
           +--> Chuẩn bị JMX metadata / adapter
           |
           v
 MBeanServer.registerMBean(...)
           |
      +----+------+
      |           |
   thành công    thất bại
      |           |
      v           +--> exception / log / startup failure
 MBean hiện có    +--> xử lý theo registration policy
      |
      v
 JConsole / JMX client
\`\`\`

Lỗi có thể xảy ra tại nhiều bước, không chỉ ở lệnh \`registerMBean\`: Spring không tìm thấy bean, naming strategy tạo tên không hợp lệ, hai exporter cùng dùng một tên, MBean không tuân hợp đồng JMX, Model MBean metadata không hợp lệ hoặc JVM/MBeanServer có chính sách từ chối.

Nếu chỉ xem log \`INFO\` của ứng dụng rồi thấy không có MBean trên JConsole, chưa thể kết luận lỗi do registration. Có thể exporter chưa bật, bean không được chọn để export, kết nối nhầm JVM, hoặc policy cố ý bỏ qua đối tượng đã tồn tại.

## 3. Registration policy và ảnh hưởng đến log

Spring cung cấp các chính sách xử lý khi một \`ObjectName\` đã tồn tại trong cùng \`MBeanServer\`, thường được cấu hình bằng \`RegistrationPolicy\`.

| Policy | Ý nghĩa | Điều cần quan sát |
| --- | --- | --- |
| \`FAIL_ON_EXISTING\` | Coi việc tên đã tồn tại là lỗi đăng ký. | Exception liên quan duplicate name; tùy đường khởi tạo có thể khiến Spring context khởi động thất bại. |
| \`IGNORE_EXISTING\` | Bỏ qua đăng ký mới nếu tên đã tồn tại. | Không nhất thiết có lỗi; MBean đang tồn tại có thể thuộc chủ thể khác. |
| \`REPLACE_EXISTING\` | Thực hiện thay thế đối tượng đã đăng ký theo cơ chế của exporter. | Cần biết MBean nào bị thay, ai sở hữu lifecycle và có gián đoạn hay không. |

Ví dụ cấu hình tường minh:

\`\`\`java
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

MBeanExporter exporter = new MBeanExporter();

exporter.setRegistrationPolicy(
    RegistrationPolicy.FAIL_ON_EXISTING
);
\`\`\`

Việc chọn policy phải phản ánh yêu cầu quản lý MBean, không phải chỉ để loại bỏ lỗi trong log.

**Khuyến nghị:** với hệ thống cần bảo đảm MBean xuất đúng bean đã định nghĩa, policy \`FAIL_ON_EXISTING\` thường giúp phát hiện cấu hình trùng tên sớm. Dùng \`IGNORE_EXISTING\` có thể hợp lý khi chia sẻ namespace có chủ đích, nhưng cần tránh tình huống hệ thống tiếp tục chạy với MBean cũ không đúng phiên bản. Dùng \`REPLACE_EXISTING\` phải có ownership rõ ràng, vì thay thế MBean của thành phần khác có thể gây ảnh hưởng vận hành.

## 4. Các nhóm lỗi thường gặp khi export

### 4.1. InstanceAlreadyExistsException: ObjectName trùng

Một MBeanServer không cho phép hai MBean cùng chiếm một \`ObjectName\` tại cùng thời điểm.

Ví dụ:

\`\`\`text
javax.management.InstanceAlreadyExistsException:
com.example:type=Worker,name=Importer
\`\`\`

Nguyên nhân thường gặp:

- Hai \`MBeanExporter\` cùng export một bean hoặc hai bean dùng chung tên.
- Spring Boot đã có exporter, ứng dụng lại tạo exporter thủ công.
- Bean được đăng ký bằng JMX API trực tiếp trước khi exporter chạy.
- Hai Spring ApplicationContext cùng chia sẻ platform MBeanServer.
- Context cũ chưa cleanup trong môi trường test hoặc redeploy.
- Naming strategy tạo tên giống nhau cho các bean khác nhau.

Chẩn đoán nên bắt đầu bằng **ObjectName chính xác** xuất hiện trong lỗi và tìm thành phần đang sở hữu tên đó. Không xóa MBean hiện tại chỉ để tiếp tục startup nếu chưa xác định nó thuộc exporter nào.

### 4.2. NotCompliantMBeanException: hợp đồng JMX không hợp lệ

Ví dụ:

\`\`\`text
javax.management.NotCompliantMBeanException:
MBean class does not implement DynamicMBean,
and neither follows the Standard MBean conventions
nor the MXBean conventions
\`\`\`

Nguyên nhân có thể là một POJO được đăng ký trực tiếp mà không có adapter hoặc metadata exporter phù hợp; Standard MBean interface không đúng tên/quy ước; hoặc exporter dùng strategy không đúng với loại bean.

Cách xử lý:

1. Kiểm tra bean thuộc Standard MBean, MXBean, DynamicMBean hay POJO cần Model MBean adapter.
2. Kiểm tra \`MBeanInfoAssembler\` đang dùng.
3. Nếu dùng annotation Spring, xác nhận \`@ManagedResource\` được đọc bởi metadata assembler phù hợp.
4. Không sửa bằng cách công bố toàn bộ public methods của service nội bộ.

### 4.3. MalformedObjectNameException: ObjectName không hợp lệ

Ví dụ:

\`\`\`text
javax.management.MalformedObjectNameException:
Invalid character in value
\`\`\`

Tên JMX có cấu trúc:

\`\`\`text
domain:key=value,key2=value2
\`\`\`

Các ký tự đặc biệt trong giá trị cần được quote theo quy tắc \`ObjectName\`. Tránh đưa dữ liệu người dùng hoặc chuỗi tùy ý vào domain/key property. Nên dùng naming strategy ổn định và kiểm tra \`ObjectName\` trước khi export.

\`\`\`java
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example:type=Cache,name=Products"
);
\`\`\`

Nếu cần giá trị động chứa ký tự đặc biệt:

\`\`\`java
String quoted = ObjectName.quote(rawValue);
ObjectName name = new ObjectName(
    "com.example:type=Cache,name=" + quoted
);
\`\`\`

Không dùng giá trị chứa token, email khách hàng hoặc thông tin bí mật làm tên MBean, vì \`ObjectName\` có thể xuất hiện trong log và các công cụ giám sát.

### 4.4. InstanceNotFoundException và lỗi lifecycle

Một exporter hoặc thao tác cleanup có thể gặp lỗi liên quan MBean không còn ở registry. Nguyên nhân có thể là:

- Thành phần khác đã unregister trước.
- Context bị đóng hai lần hoặc ownership không rõ.
- Registration thất bại nhưng cleanup vẫn dựa trên trạng thái cũ.
- Có race khi nhiều thành phần thay đổi cùng ObjectName.

Đây có thể là lỗi lúc hủy đăng ký, khác với lỗi lúc đăng ký. Phải đọc stack trace và phương thức phát sinh thay vì gộp tất cả lỗi JMX vào một nhóm.

### 4.5. Runtime exception từ constructor hoặc initialization

Một bean có thể throw exception trước khi exporter đăng ký: thiếu dependency, sai cấu hình, lỗi kết nối bên ngoài hoặc logic constructor. Log có thể có các lớp exception Spring như \`BeanCreationException\`.

Khi đọc log, đi theo chuỗi \`Caused by\` đến nguyên nhân gần gốc. \`BeanCreationException\` chỉ nói quá trình tạo Spring bean thất bại, không mặc định chứng minh lỗi \`MBeanServer.registerMBean\`.

## 5. Mức log nên quan sát

Spring dùng logging abstraction; ứng dụng thường triển khai qua SLF4J/Logback hoặc một backend logging khác. Những logger có giá trị khi điều tra Spring JMX gồm các package liên quan:

\`\`\`text
org.springframework.jmx
org.springframework.jmx.export
org.springframework.jmx.support
\`\`\`

Trong Spring Boot, có thể tăng log level cục bộ cho môi trường thử nghiệm:

\`\`\`properties
logging.level.org.springframework.jmx=DEBUG
logging.level.org.springframework.jmx.export=DEBUG
\`\`\`

Nếu cần phân tích quá trình cấu hình phức tạp, có thể thử \`TRACE\` tạm thời với thời gian và phạm vi giới hạn, sau đó khôi phục mức log phù hợp.

**Lưu ý:** không có bảo đảm mọi phiên bản Spring phát một thông điệp log cụ thể hoặc một dòng \`DEBUG\` nhất định. Cấu trúc log phụ thuộc phiên bản/framework/backend; quan sát exception và trạng thái registry mới là bằng chứng chính.

### 5.1. INFO, WARN, ERROR, DEBUG trong bối cảnh đăng ký

| Mức | Khi nào hữu ích | Ghi chú |
| --- | --- | --- |
| \`INFO\` | Ghi lifecycle hoặc quyết định cấu hình quan trọng. | Không nên log quá nhiều MBean khi ứng dụng có hàng nghìn bean. |
| \`WARN\` | Trường hợp có thể tiếp tục nhưng cần chú ý, ví dụ skip/trùng theo chính sách. | Không giả định exporter luôn dùng WARN cho từng trường hợp. |
| \`ERROR\` | Lỗi làm export thất bại hoặc ảnh hưởng khởi tạo. | Cần chứa lỗi gốc và ObjectName an toàn. |
| \`DEBUG\` | Điều tra chọn bean, naming và đăng ký. | Bật có chủ đích, tránh tràn log. |
| \`TRACE\` | Điều tra chi tiết ngắn hạn. | Có thể tốn tài nguyên, tăng nguy cơ lộ metadata. |

Chính sách vận hành tốt thường có mức log mặc định vừa phải và khả năng tăng chi tiết trong môi trường được kiểm soát.

## 6. Ví dụ ứng dụng Spring có MBeanExporter

### 6.1. Standard MBean

\`\`\`java
package example.springjmx;

public interface WorkerMonitorMBean {
    long getProcessedCount();
    boolean isRunning();
}
\`\`\`

\`\`\`java
package example.springjmx;

public final class WorkerMonitor implements WorkerMonitorMBean {

    @Override
    public long getProcessedCount() {
        return 123L;
    }

    @Override
    public boolean isRunning() {
        return true;
    }
}
\`\`\`

### 6.2. Cấu hình exporter và policy

\`\`\`java
package example.springjmx;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

@Configuration
public class JmxConfiguration {

    @Bean
    public WorkerMonitor workerMonitor() {
        return new WorkerMonitor();
    }

    @Bean
    public MBeanExporter workerMBeanExporter(WorkerMonitor monitor) {
        MBeanExporter exporter = new MBeanExporter();

        exporter.setBeans(Map.of(
            "com.example:type=Worker,name=Importer",
            monitor
        ));

        exporter.setRegistrationPolicy(
            RegistrationPolicy.FAIL_ON_EXISTING
        );

        return exporter;
    }
}
\`\`\`

Cấu hình này định nghĩa một exporter đăng ký đúng một MBean theo ObjectName chỉ định. Khi không có xung đột, exporter đăng ký thành công lúc Spring context khởi tạo.

### 6.3. Chạy context để quan sát trạng thái

\`\`\`java
package example.springjmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public final class JmxRegistrationDemo {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example:type=Worker,name=Importer"
        );

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                    JmxConfiguration.class)) {

            System.out.println(
                "Registered: " + server.isRegistered(name)
            );

            System.out.println(
                "ProcessedCount: "
                    + server.getAttribute(name, "ProcessedCount")
            );
        }

        System.out.println(
            "Registered after shutdown: "
                + server.isRegistered(name)
        );
    }
}
\`\`\`

Với platform MBeanServer mặc định và cấu hình không xung đột, kết quả mong đợi:

\`\`\`text
Registered: true
ProcessedCount: 123
Registered after shutdown: false
\`\`\`

Nếu exporter được cấu hình để dùng custom \`MBeanServer\`, cần lấy đúng instance để kiểm tra. Đừng lấy kết quả \`false\` từ platform server làm bằng chứng tuyệt đối rằng exporter không đăng ký ở bất kỳ server nào.

## 7. Tái hiện lỗi trùng ObjectName trong lab

Để hiểu log, có thể chủ động tạo xung đột trong môi trường thử nghiệm.

### 7.1. Tạo MBean chiếm tên trước

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example:type=Worker,name=Importer"
);

// Chỉ trong lab cô lập:
server.registerMBean(new WorkerMonitor(), name);
\`\`\`

Sau đó khởi tạo \`ApplicationContext\` dùng \`JmxConfiguration\`, exporter lại cố đăng ký cùng tên.

Với \`FAIL_ON_EXISTING\`, Spring có thể ném exception liên quan việc tên đã tồn tại; tùy vị trí lỗi, stack trace có thể được bọc trong \`BeanCreationException\` hoặc \`MBeanExportException\`.

Ví dụ log minh họa (không phải template bảo đảm cho mọi phiên bản):

\`\`\`text
ERROR Failed to create bean 'workerMBeanExporter'
org.springframework.beans.factory.BeanCreationException:
  Error creating bean with name 'workerMBeanExporter'
Caused by: org.springframework.jmx.export.MBeanExportException:
  Unable to register MBean
Caused by: javax.management.InstanceAlreadyExistsException:
  com.example:type=Worker,name=Importer
\`\`\`

Đọc **nguyên nhân cuối** \`InstanceAlreadyExistsException\` để xác định lỗi trùng tên thực sự. Sau đó tìm nguồn đăng ký trước thay vì chỉ đổi policy.

### 7.2. Không tự động đổi sang REPLACE_EXISTING để “sửa”

Đổi policy thành \`REPLACE_EXISTING\` có thể khiến lỗi biến mất nhưng thay thế một MBean đang được thành phần khác quản lý. Nếu exporter sau đó destroy, trạng thái registry có thể khác dự kiến.

Trước khi chọn replace, xác định:

- Ai sở hữu \`ObjectName\`?
- MBean đang tồn tại có phải phiên bản cũ cần thay không?
- Có client nào đang sử dụng MBean trong lúc thay thế?
- Nếu export mới thất bại, đối tượng cũ có còn phục hồi được không?
- Ai sẽ chịu trách nhiệm unregister khi đóng context?

Một hệ thống có nhiều module nên quy định một owner quản trị cho mỗi namespace/ObjectName hoặc dùng naming scheme tránh xung đột.

## 8. Ghi log lỗi có cấu trúc

Khi dự án xây dựng wrapper hoặc logic export tùy chỉnh, log nên có đủ thông tin để tìm nguyên nhân:

\`\`\`text
event=JMX_REGISTRATION_FAILURE
mbean=com.example:type=Worker,name=Importer
phase=register
policy=FAIL_ON_EXISTING
exception=InstanceAlreadyExistsException
application=import-service
environment=staging
\`\`\`

Cần tránh ghi credential, nội dung \`ObjectName\` không được lọc, dữ liệu khách hàng hoặc configuration secret. Nếu domain/name được tạo từ dữ liệu động, nên sanitize hoặc chuyển thành định danh được cấp phép trước khi đưa vào log.

Một cách phân loại log tối thiểu:

- \`JMX_EXPORT_START\`: bắt đầu export trong context/module.
- \`JMX_REGISTERED\`: đăng ký MBean thành công.
- \`JMX_REGISTRATION_FAILURE\`: đăng ký thất bại.
- \`JMX_IGNORED_EXISTING\`: bỏ qua vì policy.
- \`JMX_UNREGISTERED\`: hủy đăng ký thành công.
- \`JMX_UNREGISTRATION_FAILURE\`: hủy đăng ký thất bại.

Đây là **quy ước sự kiện do ứng dụng tự định nghĩa**, không phải danh sách event name chuẩn được Spring tự động phát. Chỉ ghi những sự kiện có nguồn xác thực tương ứng.

### 8.1. Tránh log exception nhiều tầng lặp lại

Với Spring, một exception có thể được log ở tầng exporter, tầng ApplicationContext và tầng main process. Nếu tự log thêm tại mỗi tầng mà không có context mới, kết quả dễ trùng lặp nhiều stack trace.

Một phương án là ghi structured diagnostic ở một điểm phù hợp, sau đó để framework xử lý/propagate exception; hệ thống thu thập log dùng correlation ID hoặc service instance để nhóm các thông điệp liên quan.

## 9. MBeanExporterListener không báo đầy đủ lỗi đăng ký

Spring cung cấp \`MBeanExporterListener\` với callback:

\`\`\`java
void mbeanRegistered(ObjectName name);
void mbeanUnregistered(ObjectName name);
\`\`\`

Ví dụ:

\`\`\`java
import javax.management.ObjectName;
import org.springframework.jmx.export.MBeanExporterListener;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class LoggingExporterListener
        implements MBeanExporterListener {

    private static final Logger log =
        LoggerFactory.getLogger(LoggingExporterListener.class);

    @Override
    public void mbeanRegistered(ObjectName name) {
        log.info("JMX registration succeeded: {}", name);
    }

    @Override
    public void mbeanUnregistered(ObjectName name) {
        log.info("JMX unregistration succeeded: {}", name);
    }
}
\`\`\`

Gắn với exporter:

\`\`\`java
exporter.setListeners(new LoggingExporterListener());
\`\`\`

Điểm quan trọng: listener này được thiết kế để theo dõi **đăng ký/hủy đăng ký đã xảy ra**, không cung cấp callback chuẩn như \`mbeanRegistrationFailed(Exception)\`. Nếu register thất bại, bạn không thể chỉ dựa vào listener để biết lỗi.

Một chiến lược hợp lý:

1. Ghi log lifecycle thành công qua listener nếu cần.
2. Thu stack trace của lỗi exporter qua logging và error handling của Spring.
3. Sau startup, xác minh MBean dự kiến có trong registry.
4. Nếu ứng dụng cần monitoring production, phát cảnh báo khi MBean quan trọng không tồn tại hoặc exporter initialization thất bại.

## 10. MBeanServerDelegate notifications cũng không thay thế failure logging

JMX \`MBeanServerDelegate\` có thể phát notification cho các lần MBean được đăng ký/hủy đăng ký trong một \`MBeanServer\`. Ví dụ:

\`\`\`java
ObjectName delegate = new ObjectName(
    "JMImplementation:type=MBeanServerDelegate"
);
\`\`\`

Client đăng ký \`NotificationListener\` với delegate để theo dõi \`MBeanServerNotification\` từ registry.

Tuy nhiên **registration failure** không phải một loại notification success registration mặc định. Delegate hữu ích để giám sát biến động registry; muốn biết vì sao register thất bại vẫn cần exception/log của exporter hoặc logic đăng ký.

Do đó:

\`\`\`text
Exporter listener        -> success lifecycle của exporter
MBeanServerDelegate      -> registry notifications
Spring exception/log     -> nguyên nhân lỗi đăng ký
MBeanServer.isRegistered -> trạng thái registry hiện tại
\`\`\`

Không trộn chúng thành một “nguồn sự thật duy nhất” vì mỗi công cụ có phạm vi khác nhau.

## 11. Kiểm tra trạng thái registry sau startup

Một phép kiểm tra đơn giản:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName expected = new ObjectName(
    "com.example:type=Worker,name=Importer"
);

boolean exists = server.isRegistered(expected);

if (!exists) {
    System.err.println(
        "Expected JMX MBean is missing: " + expected
    );
}
\`\`\`

Lưu ý: \`exists=true\` chỉ nghĩa có MBean ở tên đó, không chứng minh **đúng MBean** được exporter vừa đăng ký. Với \`IGNORE_EXISTING\`, có thể là MBean từ một component khác.

Khi cần chắc chắn, đọc thêm \`MBeanInfo\`:

\`\`\`java
if (server.isRegistered(expected)) {
    var info = server.getMBeanInfo(expected);

    System.out.println("Class: " + info.getClassName());

    for (var attr : info.getAttributes()) {
        System.out.println("Attribute: " + attr.getName());
    }

    for (var op : info.getOperations()) {
        System.out.println("Operation: " + op.getName());
    }
}
\`\`\`

Nếu class/signature không đúng kỳ vọng, cần điều tra ownership, registration policy và exporter thay vì ghi nhận là đã hoàn tất.

## 12. Test tự động phân biệt success và failure

### 12.1. Success case

Trong integration test:

1. Khởi tạo Spring context chứa exporter.
2. Khẳng định \`MBeanServer.isRegistered(name)\` trả \`true\`.
3. Đọc \`MBeanInfo\`, kiểm tra attribute/operation cần thiết.
4. Đóng context.
5. Khẳng định MBean đã được unregister, nếu exporter là owner.

### 12.2. Duplicate failure case

Dùng platform MBeanServer của một môi trường test cô lập:

\`\`\`java
MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example:type=Worker,name=DuplicateCase"
);

server.registerMBean(new WorkerMonitor(), name);

try {
    // Khởi tạo một Spring exporter cấu hình
    // FAIL_ON_EXISTING cho cùng ObjectName.
    // Assert quá trình tạo context hoặc exporter thất bại
    // với nguyên nhân duplicate phù hợp.
} finally {
    if (server.isRegistered(name)) {
        server.unregisterMBean(name);
    }
}
\`\`\`

Không cần ghi log thật ra production. Test nên dùng tên duy nhất và cleanup chắc chắn để không làm nhiễm registry dùng chung.

### 12.3. Kiểm tra bằng exception cause chain

Spring có thể wrap lỗi trong nhiều lớp exception. Với Java, có thể duyệt cause chain:

\`\`\`java
static boolean hasCause(
        Throwable failure,
        Class<? extends Throwable> type) {

    for (Throwable current = failure;
            current != null;
            current = current.getCause()) {

        if (type.isInstance(current)) {
            return true;
        }
    }
    return false;
}
\`\`\`

Trong test:

\`\`\`java
if (!hasCause(
        failure,
        javax.management.InstanceAlreadyExistsException.class)) {
    throw new AssertionError(
        "Expected duplicate ObjectName cause",
        failure
    );
}
\`\`\`

Không nên so sánh tuyệt đối toàn bộ exception message vì text có thể khác giữa phiên bản Spring/JDK. Loại exception và ObjectName liên quan thường bền vững hơn.

## 13. Theo dõi bằng metrics và cảnh báo

Log giúp truy vết sự cố, nhưng một MBean quan trọng không được đăng ký có thể khiến monitoring mất dữ liệu mà không có người đọc log ngay. Một hệ thống vận hành có thể bổ sung:

- **Counter** số lần export thất bại theo loại nguyên nhân.
- **Gauge** số MBean quan trọng đang tồn tại so với số mong đợi.
- **Startup health check** hoặc kiểm tra tự động cho JMX surface bắt buộc.
- **Alert** khi mất MBean phục vụ monitoring hoặc khi exporter startup thất bại.
- **Release comparison** để phát hiện sau triển khai MBean/attribute/operation bị mất.

Ví dụ metric tự định nghĩa:

\`\`\`text
jmx_export_failure_total{
  service="import-service",
  reason="duplicate_object_name"
} 1
\`\`\`

Đây là một ví dụ tên metric; Spring Framework không mặc định tạo metric này chỉ vì MBeanExporter lỗi. Để có metric thật, ứng dụng cần integration thích hợp với Micrometer/collector và điểm ghi nhận lỗi đáng tin cậy.

### 13.1. Tránh high-cardinality

Không dùng \`ObjectName\` đầy đủ có ID động làm metric label nếu tạo ra rất nhiều giá trị. Nên group theo \`reason\`, module hoặc loại MBean có số lượng hữu hạn.

Giữ ObjectName chi tiết trong log có bảo vệ, còn metrics thường dùng nhãn tổng hợp để tránh tăng chi phí giám sát.

## 14. Chẩn đoán theo thứ tự

Khi không thấy MBean trong JConsole, đi theo luồng:

\`\`\`text
Không thấy MBean
      |
      v
1. Đúng JVM/MBeanServer?
      |
      v
2. Spring exporter đã khởi tạo?
      |
      v
3. Bean được chọn để export?
      |
      v
4. ObjectName có đúng?
      |
      v
5. Có exception trong startup logs?
      |
      +--> InstanceAlreadyExistsException
      |       -> trùng ObjectName / policy
      |
      +--> NotCompliantMBeanException
      |       -> sai hợp đồng MBean / adapter
      |
      +--> MalformedObjectNameException
      |       -> sai naming
      |
      +--> BeanCreationException / khác
      |       -> xem nguyên nhân gốc
      |
      v
6. Policy IGNORE_EXISTING?
      |
      v
7. isRegistered và getMBeanInfo có khớp?
      |
      v
8. Kiểm tra quyền và kết nối JMX client
\`\`\`

Một lỗi “không thấy MBean trên JConsole” cũng có thể do client kết nối nhầm process/endpoint, không liên quan đăng ký. Phân biệt lỗi client-side và server-side trước khi sửa logging hoặc policy.

## 15. Cấu hình logging trong Spring Boot

Một ứng dụng Spring Boot sử dụng Logback hoặc cấu hình logging tương đương có thể bật mức chi tiết ở package JMX:

\`\`\`yaml
logging:
  level:
    org.springframework.jmx: DEBUG
    org.springframework.jmx.export: DEBUG
\`\`\`

Trong môi trường production, có thể giữ mức INFO/WARN theo chính sách vận hành và chỉ bật DEBUG ngắn hạn khi cần chẩn đoán.

Nếu startup bị lỗi trước khi backend logging được thiết lập đầy đủ, thông báo có thể xuất hiện trên stderr hoặc hệ thống log của container/service manager. Vì vậy khi điều tra, xem cả:

- Log ứng dụng.
- Stack trace khởi động Spring.
- Stderr/stdout của JVM.
- Kubernetes pod logs hoặc systemd service logs nếu có.
- Log của custom MBeanServer/connector nếu triển khai.
- Log từ deployment pipeline hoặc test integration.

**Không** tự động lưu credential hoặc full environment variables vào log để chẩn đoán JMX.

## 16. Phân biệt JMX registration failure với remote JMX connection failure

Đăng ký MBean và kết nối JMX từ xa là hai tầng khác nhau:

\`\`\`text
Ứng dụng
  MBeanExporter -> MBeanServer [registration]
                         |
                 JMXConnectorServer
                         |
                    Network/TLS
                         |
                      JConsole
\`\`\`

Nếu MBean đã đăng ký thành công nhưng remote JConsole không kết nối, lỗi có thể nằm ở:

- JVM remote JMX agent chưa bật.
- Sai cổng registry hoặc RMI server port.
- \`java.rmi.server.hostname\` không thể truy cập từ client.
- Firewall/NAT/container networking.
- Authentication hoặc TLS mismatch.
- JConsole kết nối nhầm JVM.

Đừng thay \`RegistrationPolicy\` để sửa network timeout. Ngược lại, việc mở remote JMX port không sửa được \`InstanceAlreadyExistsException\`.

## 17. Bảo mật trong quá trình giám sát log

Metadata JMX có thể tiết lộ topology ứng dụng hoặc tên thành phần nội bộ. Cần tránh:

1. In toàn bộ Java system properties hoặc environment để tìm lỗi MBean.
2. Log mật khẩu, token hoặc cấu hình remote JMX authentication.
3. Đưa thông tin cá nhân vào \`ObjectName\`.
4. Bật DEBUG/TRACE trên toàn bộ ứng dụng trong thời gian dài chỉ để thấy một lỗi nhỏ.
5. Ghi stack trace với dữ liệu nhạy cảm lên hệ thống log không giới hạn truy cập.
6. Dùng \`REPLACE_EXISTING\` không rõ ownership, có thể thay MBean quan trọng.
7. Mở JMX connector không có authentication/TLS ra mạng ngoài để tiện kiểm tra.
8. Truy vấn \`getAttribute\` nhạy cảm hoặc invoke operation chỉ để chứng minh registration.

Log và metadata có thể giúp điều tra, nhưng cũng phải tuân thủ chính sách phân quyền, retention và dữ liệu nhạy cảm của tổ chức.

## 18. Quy trình vận hành khi có lỗi

### Bước 1 — Ghi nhận sự cố

Lấy thời điểm, service instance, môi trường, lỗi Spring/JMX, và \`ObjectName\` liên quan nếu an toàn. Ghi lại policy hiện tại.

### Bước 2 — Xác định nơi lỗi phát sinh

Xem stack trace: tên class Spring, phương thức exporter, lớp cause thấp nhất. Phân biệt MBean registration với bean initialization và remote connection.

### Bước 3 — Kiểm tra registry

Trên đúng MBeanServer, dùng \`isRegistered(name)\`, sau đó \`getMBeanInfo(name)\` nếu tồn tại. Nếu có MBean ở cùng tên nhưng class/metadata khác, nghi ngờ ownership hoặc policy bỏ qua/thay thế.

### Bước 4 — Đối chiếu cấu hình

Xem danh sách bean exporter, naming strategy, assembler, autodetect mode, registration policy và những exporter khác cùng context. Trong Spring Boot xem auto-configuration có tạo thêm exporter không.

### Bước 5 — Khắc phục nguyên nhân

Ví dụ đặt ObjectName duy nhất, loại exporter trùng, sửa interface/metadata MBean hoặc giới hạn autodetection. Không chỉ tắt log hay đổi policy để làm mất thông báo lỗi.

### Bước 6 — Xác minh trong môi trường kiểm thử

Khởi tạo context, kiểm tra registry và MBeanInfo, sau đó kiểm tra cleanup khi shutdown. Nếu lỗi từng xuất hiện sau deploy/restart, thực hiện test vòng đời lặp.

### Bước 7 — Bổ sung cảnh báo phù hợp

Nếu MBean là bắt buộc, thêm startup check hoặc health signal; metrics báo nguyên nhân tổng hợp và log chi tiết được bảo vệ.

## 19. Bài tập thực hành

### Bài tập 1 — Đăng ký MBean thành công

Tạo \`WorkerMonitorMBean\` và \`MBeanExporter\` với \`FAIL_ON_EXISTING\`. Khởi tạo Spring context, xác minh \`isRegistered(name)\` và đọc \`ProcessedCount\`.

**Mục tiêu:** xác lập dấu hiệu của một lần export thành công.

### Bài tập 2 — Trùng ObjectName

Đăng ký trước một MBean ở cùng tên trong platform server của lab, rồi khởi chạy exporter cũng dùng tên đó. Đọc cause chain, xác định \`InstanceAlreadyExistsException\`.

**Mục tiêu:** truy nguyên lỗi đăng ký thay vì chỉ đọc exception wrapper.

### Bài tập 3 — So sánh policy

Trong ba test context cô lập, thử \`FAIL_ON_EXISTING\`, \`IGNORE_EXISTING\` và \`REPLACE_EXISTING\` với một ObjectName đang tồn tại. Kiểm tra trạng thái registry và metadata của MBean trước/sau.

**Mục tiêu:** hiểu chính sách đăng ký ảnh hưởng đến hành vi và log, đồng thời nhìn thấy rủi ro ownership.

### Bài tập 4 — Lỗi metadata

Đăng ký một POJO trực tiếp qua MBeanServer không tuân Standard/Dynamic/MXBean convention. Quan sát \`NotCompliantMBeanException\`. Sau đó tạo interface MBean hợp lệ.

**Mục tiêu:** phân biệt lỗi hợp đồng JMX với lỗi duplicate name.

### Bài tập 5 — Listener và lỗi

Gắn \`LoggingExporterListener\`, thử đăng ký thành công và thất bại. Quan sát listener không cung cấp callback lỗi đăng ký có exception; dùng log/cause chain để xem failure.

**Mục tiêu:** hiểu phạm vi của success lifecycle listener.

### Bài tập 6 — Chẩn đoán một deploy

Giả sử sau deploy, JConsole vẫn thấy \`com.example:type=Worker,name=Importer\`, nhưng \`ProcessedCount\` là metadata của phiên bản cũ. Kiểm tra registration policy, exporter trùng và MBeanInfo để tìm root cause.

**Mục tiêu:** hiểu \`isRegistered=true\` không đảm bảo đúng object mới.

## 20. Câu hỏi ôn tập

**1. \`FAIL_ON_EXISTING\` có tác dụng gì?** Phát hiện và báo lỗi nếu ObjectName đã được đăng ký.

**2. \`IGNORE_EXISTING\` có chắc là đăng ký mới thành công không?** Không. Nó có thể chỉ bỏ qua bean mới vì tên đã tồn tại.

**3. Lỗi \`InstanceAlreadyExistsException\` nói lên điều gì?** Một ObjectName bị chiếm trong MBeanServer đang được dùng.

**4. Lỗi \`NotCompliantMBeanException\` thường liên quan vấn đề nào?** Hợp đồng MBean/metadata hoặc adapter không hợp lệ với JMX.

**5. \`MBeanExporterListener\` có callback lỗi đăng ký chuẩn không?** Không. Các callback chính là registered và unregistered.

**6. Khi thấy \`BeanCreationException\`, nên làm gì?** Xem cause chain để tìm lỗi gốc, không dừng ở wrapper.

**7. Làm sao xác nhận MBean mới thực sự có hợp đồng mong đợi?** Đọc \`getMBeanInfo\` và so sánh class/attributes/operations.

**8. Tại sao không dùng ObjectName đầy đủ với ID động làm metric label?** Vì dễ gây high cardinality, tăng chi phí và có thể lộ thông tin.

**9. Remote JConsole timeout có nghĩa registration thất bại không?** Không. Lỗi mạng/connector và lỗi đăng ký là hai tầng riêng.

**10. Khi nào nên bật DEBUG logging?** Khi cần chẩn đoán có chủ đích, với phạm vi và thời gian giới hạn.

## 21. Tổng kết

**Giám sát log đăng ký thất bại** cần kết hợp ba nguồn: exception và cause chain của Spring/JMX để biết nguyên nhân, registration policy để hiểu hành vi khi trùng tên, và MBeanServer registry để xác minh trạng thái thực tế. \`MBeanExporterListener\` hữu ích cho thành công và cleanup, nhưng không thay thế failure logging.

Khi xử lý sự cố, hãy xem đúng \`ObjectName\`, \`MBeanServer\`, exporter, assembler và policy; không vội đổi sang \`IGNORE_EXISTING\` hoặc \`REPLACE_EXISTING\` để che lỗi. Với hệ thống quan trọng, bổ sung integration tests, kiểm tra MBeanInfo, metrics tổng hợp và cảnh báo phù hợp.

## Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Javadoc — \`RegistrationPolicy\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/support/RegistrationPolicy.html
- Spring Framework Javadoc — \`MBeanExporterListener\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporterListener.html
- Java SE 21 — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 — \`InstanceAlreadyExistsException\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/InstanceAlreadyExistsException.html
- Java SE 21 — \`NotCompliantMBeanException\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/NotCompliantMBeanException.html