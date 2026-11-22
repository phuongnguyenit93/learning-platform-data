# Lộ trình học từ JMX nền tảng đến cấu hình Spring và truy cập từ xa

## 1. Mục tiêu và bức tranh tổng thể

Java Management Extensions (JMX) là chuẩn Java dùng để quan sát và quản lý một ứng dụng JVM trong lúc nó đang chạy. Khi học JMX trong Spring Framework, nên đi từ mô hình quản trị đối tượng Java, thử nghiệm MBean thuần Java, đến cơ chế Spring đăng ký bean lên MBeanServer, rồi mới mở quyền truy cập từ xa. Cách học này giúp hiểu rõ *cái gì được công khai*, *ai công khai*, *client nhìn thấy như thế nào*, và *tại sao cần bảo vệ kết nối*.

Sau bài này, người học có thể:
- Phân biệt resource, MBean, MBeanServer, ObjectName, attribute, operation, notification và JMX client.
- Viết và đăng ký một Standard MBean Java; kiểm tra qua JConsole.
- Giải thích cách Spring dùng @ManagedResource, @ManagedAttribute, @ManagedOperation và MBeanExporter.
- Phân biệt việc đăng ký MBean với việc mở cổng JMX từ xa.
- Thử kết nối bằng công cụ JDK, hiểu RMI/JMX URL và các vấn đề firewall/NAT.
- Xây dựng lộ trình vận hành an toàn, không tùy tiện tắt xác thực hoặc TLS ở môi trường thật.

### Sơ đồ tư duy

\`\`\`text
Ứng dụng Java / Spring
        |
        v
Resource có trạng thái và hành vi cần quản trị
        |
        v
MBean: attributes + operations (+ notifications)
        |
        v
MBeanServer: kho đăng ký MBean theo ObjectName
        |
        +---- JConsole/JVisualVM cục bộ
        |
        +---- JMXConnectorServer (ví dụ RMI) ---- client từ xa
                          |
                     xác thực / TLS /
                     mạng riêng / firewall
\`\`\`

**Phân biệt vai trò:** JMX là giao diện quản trị ở cấp JVM; Spring là lớp tích hợp giúp xuất các Spring bean dưới dạng MBean; RMI connector là một cơ chế truyền thông để client khác tiến trình truy cập. Không có quan hệ “bật Spring JMX thì tự động an toàn để mở Internet”.

## 2. Chặng 1 — Hiểu JMX nền tảng bằng một ví dụ thuần Java

### 2.1. Các khái niệm tối thiểu

| Thuật ngữ | Ý nghĩa | Câu hỏi tự kiểm tra |
|---|---|---|
| Managed resource | Đối tượng/dịch vụ muốn giám sát, quản lý | Ta cần nhìn hoặc đổi trạng thái nào? |
| MBean | Giao diện quản trị của resource | Công khai attribute/operation nào? |
| Attribute | Giá trị đọc và/hoặc ghi | Dữ liệu đó chỉ đọc hay có thể sửa? |
| Operation | Hành động gọi qua JMX | Gọi có gây tác dụng phụ không? |
| Notification | Sự kiện MBean có thể phát | Client có cần nhận thông báo không? |
| MBeanServer | Nơi MBean được đăng ký và truy vấn | MBean đăng ký ở server nào? |
| ObjectName | Tên định danh dạng domain:key=value | Có tránh trùng tên không? |
| Connector | Cầu nối giữa client và MBeanServer | Kết nối nội bộ hay từ xa? |

Ví dụ ObjectName: \`demo.monitoring:type=Queue,name=Orders\`. Phần trước dấu hai chấm là domain, sau đó là các cặp thuộc tính khóa. ObjectName nên ổn định, đủ cụ thể và tránh nhét dữ liệu nhạy cảm vào tên.

### 2.2. Standard MBean đầu tiên

Tên interface phải theo quy ước \`<TênLớp>MBean\` khi dùng Standard MBean.

\`\`\`java
// QueueMonitorMBean.java
public interface QueueMonitorMBean {
    int getPendingJobs();
    void resetCounter();
}

// QueueMonitor.java
public class QueueMonitor implements QueueMonitorMBean {
    private final java.util.concurrent.atomic.AtomicInteger pendingJobs =
            new java.util.concurrent.atomic.AtomicInteger();

    @Override
    public int getPendingJobs() {
        return pendingJobs.get();
    }

    @Override
    public void resetCounter() {
        pendingJobs.set(0);
    }

    public void jobSubmitted() {
        pendingJobs.incrementAndGet();
    }
}
\`\`\`

Đăng ký MBean vào platform MBeanServer:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class DemoApplication {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        QueueMonitor monitor = new QueueMonitor();

        ObjectName name =
                new ObjectName("demo.monitoring:type=Queue,name=Orders");
        server.registerMBean(monitor, name);

        monitor.jobSubmitted();
        System.out.println("JMX demo is running; PID=" +
                ProcessHandle.current().pid());
        Thread.sleep(300_000);
    }
}
\`\`\`

Chạy chương trình bằng JDK phù hợp, sau đó chạy \`jconsole\`, chọn tiến trình Java cục bộ, mở tab **MBeans** và tìm \`demo.monitoring → Queue → Orders\` (cấu trúc hiển thị có thể khác đôi chút giữa các công cụ). Kiểm tra \`PendingJobs\` là attribute đọc được và \`resetCounter()\` là operation gọi được.

**Điểm cần hiểu:** \`registerMBean\` làm đối tượng xuất hiện trong MBeanServer; một client địa phương có thể truy cập qua cơ chế attach của JDK. Bước này chưa đồng nghĩa với việc đã cấu hình cổng truy cập từ xa.

### 2.3. Các biến thể nên biết

- **Standard MBean:** interface đặt tên theo quy ước, phù hợp để học đầu tiên.
- **MXBean:** ánh xạ kiểu dữ liệu qua Open Types, thường thuận tiện cho client trung lập và đối tượng quản trị phức tạp hơn.
- **Dynamic MBean:** metadata và cách truy cập động, hữu ích khi cấu trúc quản trị không cố định.
- **NotificationBroadcaster:** mở rộng để phát sự kiện, ví dụ thay đổi trạng thái hoặc vượt ngưỡng.

Không cần triển khai tất cả ngay. Chỉ chuyển bước khi có thể giải thích attribute/operation được xác định từ interface và MBeanServer xử lý ObjectName như thế nào.

## 3. Chặng 2 — Tích hợp Spring Framework với JMX

Spring JMX hỗ trợ đưa đối tượng do Spring IoC container quản lý lên JMX. Cần phân biệt **Spring Framework JMX** (cơ chế export MBean và metadata annotation) với tính năng **Spring Boot Actuator**; đây là các tầng tích hợp khác nhau.

### 3.1. Export bằng annotation

Một bean Spring đơn giản:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

import java.util.concurrent.atomic.AtomicInteger;

@Component
@ManagedResource(
    objectName = "training.spring:type=Worker,name=Example",
    description = "Example Spring-managed worker"
)
public class WorkerMonitor {
    private final AtomicInteger activeTasks = new AtomicInteger();

    @ManagedAttribute(description = "Current number of active tasks")
    public int getActiveTasks() {
        return activeTasks.get();
    }

    @ManagedOperation(description = "Clear the active task counter")
    public void clearActiveTasks() {
        activeTasks.set(0);
    }

    public void taskStarted() {
        activeTasks.incrementAndGet();
    }
}
\`\`\`

Trong ứng dụng Spring Framework dùng Java configuration, bật exporter và annotation metadata:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.support.RegistrationPolicy;

@Configuration
public class JmxConfiguration {
    @Bean
    public AnnotationJmxAttributeSource jmxAttributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    public MetadataMBeanInfoAssembler jmxAssembler(
            AnnotationJmxAttributeSource jmxAttributeSource) {
        MetadataMBeanInfoAssembler assembler =
                new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(jmxAttributeSource);
        return assembler;
    }

    @Bean
    public MBeanExporter mbeanExporter(
            WorkerMonitor workerMonitor,
            MetadataMBeanInfoAssembler jmxAssembler) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(jmxAssembler);
        exporter.setBeans(java.util.Map.of(
                "training.spring:type=Worker,name=Example",
                workerMonitor
        ));
        exporter.setRegistrationPolicy(RegistrationPolicy.FAIL_ON_EXISTING);
        return exporter;
    }
}
\`\`\`

Ví dụ trên cố ý thiết lập exporter và assembler rõ ràng để thấy từng thành phần. Trong dự án thực tế có thể dùng \`@EnableMBeanExport\` cho cấu hình annotation ngắn gọn, hoặc cấu hình exporter bằng các cơ chế Spring sẵn có. Không đồng thời đăng ký một object dưới cùng ObjectName từ nhiều exporter trừ khi có chủ đích xử lý trùng tên.

**Lưu ý khi chạy:** cần \`spring-context\` và các thư viện liên quan của phiên bản Spring Framework đang sử dụng; ví dụ này giả định ứng dụng đã bật component scanning cho \`WorkerMonitor\` và nạp \`JmxConfiguration\`. Dùng project Java/Spring hiện có với dependency đồng bộ phiên bản thay vì trộn tùy ý các JAR.

### 3.2. Vai trò của từng thành phần Spring

| Thành phần | Vai trò |
|---|---|
| \`@ManagedResource\` | Khai báo bean là resource có thể export, đặt ObjectName/description |
| \`@ManagedAttribute\` | Chọn getter/setter được công khai qua JMX |
| \`@ManagedOperation\` | Chọn method có thể gọi từ JMX client |
| \`AnnotationJmxAttributeSource\` | Đọc annotation quản trị |
| \`MetadataMBeanInfoAssembler\` | Biến metadata thành thông tin MBean |
| \`MBeanExporter\` | Đăng ký đối tượng vào MBeanServer |
| \`MBeanServer\` | Registry/runtime JMX, không thuộc riêng Spring |
| \`@EnableMBeanExport\` | Cơ chế kích hoạt hỗ trợ export dựa trên annotation |

Một getter bình thường không tự trở thành attribute được export theo metadata annotation chỉ vì lớp có \`@Component\`. Quy tắc exposure phụ thuộc assembler và cấu hình export, vì vậy phải nhìn vào MBean thực tế sau khi khởi động.

### 3.3. Các lỗi cần tự trải nghiệm

1. **Không thấy MBean:** kiểm tra bean có được tạo bởi Spring, exporter có được khởi tạo, annotation metadata có được đọc, và ObjectName có đúng hay không.
2. **Đăng ký trùng ObjectName:** hai đối tượng cùng tên hoặc exporter lặp lại. Đặt tên nhất quán; chỉ chọn chính sách replace/ignore khi hiểu hậu quả.
3. **Thấy MBean nhưng không thấy operation:** chưa thêm \`@ManagedOperation\`, assembler chưa cấu hình đúng, hoặc method có kiểu tham số khó biểu diễn.
4. **Attribute không ghi được:** getter không có setter phù hợp hoặc không export setter.
5. **Lẫn lộn dữ liệu Spring và dữ liệu JVM:** platform MBean như Memory/Threading tồn tại từ JDK; các MBean nghiệp vụ cần được export riêng.

## 4. Chặng 3 — Quan sát và thử nghiệm tại máy cục bộ

Lộ trình thực hành:

1. Khởi động ứng dụng và giữ tiến trình chạy.
2. Chạy \`jconsole\` từ JDK, kết nối local process.
3. Mở **MBeans**, xác định đúng domain/ObjectName.
4. Đọc attribute của MBean mẫu; gọi operation không nguy hiểm trong môi trường thử nghiệm.
5. Quan sát thay đổi từ chính ứng dụng và qua JConsole; kiểm tra đối chiếu hai chiều.
6. Thử tình huống tên trùng và cấu hình exporter sai để biết đọc lỗi lúc startup.

Đừng dùng method như xóa cache, shutdown hoặc reset dữ liệu sản xuất làm operation thử nghiệm. MBean chỉ nên xuất những hành động có phạm vi, kiểm soát quyền và khả năng audit phù hợp.

### Cách xác định đã hiểu

Có thể giải thích đường đi đầy đủ: đối tượng \`WorkerMonitor\` → Spring exporter → platform MBeanServer → \`ObjectName\` → JConsole → attribute/operation → phương thức Java thực thi. Nếu bỏ Spring khỏi chuỗi, Standard MBean vẫn được JMX quản trị; nếu bỏ connector từ xa, JMX cục bộ vẫn có thể vận hành.

## 5. Chặng 4 — Kết nối JMX từ xa và bảo mật

### 5.1. Trước khi mở kết nối

JMX remote cho phép client điều khiển những operation đã expose. Một endpoint JMX bị lộ có thể tạo rủi ro lớn nếu có MBean nguy hiểm hoặc quyền quản trị rộng. Vì vậy môi trường sản xuất nên ưu tiên kết nối qua mạng quản trị riêng hoặc tunnel được quản lý, xác thực mạnh, mã hóa, quyền tối thiểu và giới hạn máy được phép kết nối.

Không dùng cấu hình \`authenticate=false\`, \`ssl=false\` như một công thức triển khai trên máy có mạng công cộng. Nếu cần thử trong máy lab cô lập, phải hiểu rõ đây chỉ là cấu hình thử nghiệm có giới hạn.

### 5.2. Vai trò của RMI registry và RMI server

JMX RMI thường liên quan đến hai chỗ kết nối: RMI registry và endpoint RMI server. Nếu để endpoint chọn cổng ngẫu nhiên, client có thể kết nối cổng registry nhưng thất bại ở bước tiếp theo do firewall/NAT. Cấu hình \`com.sun.management.jmxremote.port\` và \`com.sun.management.jmxremote.rmi.port\` giúp cố định hai cổng (có thể cùng một số trong cấu hình phù hợp). \`java.rmi.server.hostname\` quyết định hostname/IP mà stub quảng bá cho client; nó phải là địa chỉ client thực sự truy cập được.

Ví dụ minh họa endpoint trong mạng thử nghiệm **chỉ để giải thích cấu trúc**:

\`\`\`text
Service URL:
service:jmx:rmi:///jndi/rmi://jmx.internal.example:9010/jmxrmi

Registry endpoint : 9010
RMI server endpoint: cổng cố định đã cấu hình
Advertised hostname: jmx.internal.example
\`\`\`

Trong vận hành thật, thiết lập đồng bộ DNS/hostname, cổng registry và RMI server, TLS, credentials và firewall theo hướng dẫn JDK phù hợp. Có thể chọn kiểu tunnel/mạng quản trị riêng tùy hạ tầng. Tránh mặc định suy ra rằng một URL có nghĩa chỉ có một kết nối TCP.

### 5.3. Các bước kiểm tra kết nối có kiểm soát

1. Trên máy chủ, xác nhận tiến trình Java hoạt động và MBean có mặt khi kiểm tra local.
2. Xác nhận cơ chế remote JMX connector thực sự được khởi tạo; việc có \`MBeanExporter\` chưa đủ.
3. Xác nhận địa chỉ/cổng được publish đúng, đặc biệt hostname trong RMI stub.
4. Kiểm tra ACL/firewall chỉ cho phép nguồn quản trị dự kiến; xác thực và mã hóa đã bật.
5. Kết nối bằng JConsole theo service URL, cung cấp thông tin đăng nhập hợp lệ.
6. Đọc một attribute vô hại trước; ghi nhận lỗi chính xác nếu client không kết nối được.
7. Khi hoàn tất thử nghiệm, đóng quyền truy cập thử nghiệm và thu hồi thông tin đăng nhập tạm nếu có.

Phân biệt lỗi:
- **Connection refused:** connector không lắng nghe đúng cổng hoặc mạng từ chối.
- **Timeout:** firewall, routing, hostname trong stub hoặc endpoint thứ hai không tới được.
- **Authentication failed:** credentials, chính sách xác thực hoặc quyền truy cập không khớp.
- **SSL handshake:** certificate/truststore, TLS policy hoặc hostname verification không hợp lệ.
- **MBean not found:** kết nối đã thành công nhưng ObjectName hoặc quá trình export không đúng.

Không mở firewall bừa để “sửa” timeout. Trước hết xác định từng endpoint và hướng kết nối thực tế.

## 6. Chặng 5 — Phân biệt JMX với monitoring ứng dụng hiện đại

JMX cung cấp mô hình quản trị trạng thái/hành vi. Metrics pipeline (ví dụ ứng dụng xuất chỉ số cho hệ thống quan sát) có mục tiêu tổng hợp dữ liệu thời gian, cảnh báo và dashboard. Hai hướng có thể bổ sung cho nhau, nhưng không thay thế trực tiếp:

| Tình huống | JMX thích hợp? | Lựa chọn/bổ sung |
|---|---|---|
| Kiểm tra một MBean của JVM đang chạy | Có | JConsole hoặc client JMX |
| Gọi operation quản trị có kiểm soát | Có, cần phân quyền | Admin API với audit nếu phù hợp |
| Theo dõi heap, thread, GC khi debug | Có | Metrics/observability |
| Lưu lịch sử CPU, latency và dashboard dài hạn | JMX là nguồn dữ liệu, chưa đủ hệ thống lưu trữ | Metrics collector + time-series database |
| Mở public endpoint phục vụ người dùng cuối | Thường không phù hợp | API có kiểm soát quyền phù hợp |

Khi ứng dụng dùng Spring Boot, tìm hiểu thêm cách Spring Boot expose JMX/Actuator và hành vi mặc định theo **phiên bản Boot cụ thể**; tránh suy luận thiết lập của Boot từ cấu hình Spring Framework thuần.

## 7. Kế hoạch học thực hành theo buổi

| Buổi | Trọng tâm | Bài tập | Tiêu chí hoàn thành |
|---|---|---|---|
| 1 | Khái niệm JMX | Vẽ sơ đồ resource → MBean → server → client | Giải thích vai trò 7 thuật ngữ cốt lõi |
| 2 | Standard MBean Java | Tạo QueueMonitor và đăng ký platform server | JConsole thấy attribute và operation |
| 3 | Spring JMX export | Tạo @ManagedResource và MBeanExporter | ObjectName Spring xuất hiện đúng |
| 4 | Chẩn đoán | Cố ý gây trùng tên và thiếu annotation | Chỉ ra được nguyên nhân lỗi |
| 5 | Remote JMX trong lab cô lập | Lập sơ đồ RMI endpoint và kết nối qua mạng quản trị | Xác nhận kết nối qua các cổng dự kiến, có bảo vệ |
| 6 | Vận hành và lựa chọn công cụ | So sánh JMX và hệ metrics | Viết checklist bảo mật/giám sát phù hợp |

**Bài tập cuối:** tạo một Spring bean mô phỏng bộ xử lý tác vụ, export hai read-only attributes (\`activeTasks\`, \`completedTasks\`) và một operation có kiểm soát (\`resetDemoCounters\`). Chứng minh từ JConsole rằng số liệu thay đổi khi chương trình chạy; diễn giải cách truy cập remote qua connector và những biện pháp bắt buộc trước khi triển khai ngoài lab.

## 8. Tự kiểm tra kiến thức

1. Tại sao \`MBeanServer\` và \`MBeanExporter\` không phải cùng một thành phần?
2. ObjectName xác định điều gì và tại sao cần tránh trùng?
3. Phương thức nào trở thành JMX operation khi dùng annotation assembler?
4. Vì sao đăng ký MBean không tự động tạo endpoint mạng từ xa?
5. Vì sao JMX RMI có thể “kết nối được registry nhưng không đọc được MBean”?
6. Nêu cách hạn chế rủi ro khi expose operation quản trị.
7. Khi cần dashboard lịch sử và cảnh báo, cần bổ sung những thành phần nào ngoài JMX?
8. Làm sao phân biệt lỗi export MBean với lỗi mạng remote JMX?

## 9. Những nguyên tắc cần ghi nhớ

- Học JMX thuần Java trước để hiểu hợp đồng MBean và registry; Spring chủ yếu đơn giản hóa export và metadata.
- Thử trên local trước rồi mới đi đến connector từ xa.
- Chỉ công khai attribute và operation thực sự cần, ưu tiên read-only, không lộ thông tin nhạy cảm.
- Remote JMX phải được đối xử như kênh quản trị đặc quyền: mạng riêng, xác thực, mã hóa, giới hạn truy cập, kiểm toán.
- Khi chẩn đoán RMI, luôn nhớ địa chỉ/cổng được công bố trong stub và đường đi tới endpoint thứ hai.
- Kiểm tra hành vi cụ thể theo phiên bản JDK/Spring đang dùng, vì công cụ và mặc định bảo mật có thể thay đổi.

## 10. Tài liệu tham khảo để học sâu hơn

- Oracle Java Management Extensions (JMX) Technology: https://docs.oracle.com/javase/8/docs/technotes/guides/jmx/
- Java \`javax.management\` API (MBeanServer, ObjectName, Standard MBean): https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/package-summary.html
- Java Monitoring and Management Guide: https://docs.oracle.com/en/java/javase/21/management/
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring \`MBeanExporter\` API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html

Người học nên hoàn thành ví dụ local và tự giải thích kiến trúc trước khi thử bất kỳ kịch bản remote nào. Giá trị cốt lõi của JMX là một hợp đồng quản trị tường minh, có thể quan sát và kiểm soát được trong vòng đời ứng dụng JVM.
