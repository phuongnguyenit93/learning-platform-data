# Tùy biến exporter khi có nhiều ApplicationContext trong Spring Framework JMX

## 1. Mục tiêu và tình huống

Một ứng dụng Spring có thể có **nhiều \`ApplicationContext\`**: root context, context của từng module, context con cho web, context sinh động cho plugin, hoặc context độc lập phục vụ integration test. Nếu nhiều context cùng bật JMX export, chúng có thể cùng đăng ký MBean lên một \`MBeanServer\`, sử dụng ObjectName trùng nhau hoặc không quản lý đúng vòng đời unregister.

Với cấu hình dựa trên annotation, Spring có \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\`, \`@EnableMBeanExport\` và các thành phần export như \`AnnotationMBeanExporter\` / \`MBeanExporter\`. Khi có nhiều context, câu hỏi quan trọng không còn là “làm sao bật JMX?” mà là:

- Context nào sở hữu exporter?
- Exporter nào nhìn thấy những bean nào?
- Các exporter có dùng cùng \`MBeanServer\` không?
- ObjectName có phân biệt rõ module/context/instance không?
- Context đóng thì ai unregister những MBean đã đăng ký?
- Làm sao giữ được một hợp đồng quản trị ổn định cho client?

Bài học giúp thiết kế và kiểm thử cấu hình JMX khi ứng dụng có nhiều Spring context, tránh vừa trùng registration vừa mất khả năng quan sát.

## 2. Bản đồ khái niệm

\`\`\`text
                   Một tiến trình JVM
                           |
              Platform MBeanServer (chung)
                           |
          +----------------+----------------+
          |                |                |
       Root Context    Module A Context  Module B Context
          |                |                |
       Exporter R      Exporter A       Exporter B
          |                |                |
     root:* MBeans   module=A,*        module=B,*
\`\`\`

Đây là một cách tổ chức. Không phải cứ có nhiều context thì phải tạo nhiều exporter hoặc nhiều MBeanServer. Có thể dùng **một exporter tập trung**, một exporter mỗi context hoặc server riêng cho nhóm context, tùy yêu cầu. Sự khác biệt nằm ở *ownership* và phạm vi phát hiện bean.

| Thành phần | Phạm vi ý nghĩa |
|---|---|
| \`ApplicationContext\` | Container chứa bean definitions/instances và lifecycle của Spring |
| \`BeanFactory\` | Nơi exporter tra cứu bean hoặc autodetect ứng viên |
| \`MBeanExporter\` | Đăng ký các object được chọn vào một MBeanServer |
| \`AnnotationMBeanExporter\` | Hỗ trợ xuất bean dựa trên annotation quản trị của Spring |
| \`MBeanServer\` | Registry JMX, có thể được nhiều context dùng chung |
| \`ObjectName\` | Định danh MBean duy nhất trong một MBeanServer |
| \`RegistrationPolicy\` | Hành vi của exporter khi đã có MBean cùng tên |
| \`@EnableMBeanExport\` | Kích hoạt hỗ trợ export JMX bằng Java configuration |

**Nguyên tắc nền tảng:** tính duy nhất của ObjectName được xét trong **MBeanServer**, không theo ranh giới ApplicationContext. Hai bean cùng tên trong hai context khác nhau vẫn có thể đụng nhau nếu exporter đưa chúng vào cùng server.

## 3. Các kiến trúc nhiều context thường gặp

### 3.1. Một root context và các child context

Ví dụ ứng dụng web có root context lưu services chung và một child context cho MVC.

\`\`\`text
RootApplicationContext
  - commonCacheMonitor
  - commonExporter

  └── WebApplicationContext
        - requestMonitor
        - optionalWebExporter
\`\`\`

Child context có thể nhìn bean cha khi lookup, nhưng parent không tự nhìn bean con. Đồng thời, việc autodetect candidate của exporter phụ thuộc cơ chế exporter và BeanFactory được cấu hình. Không nên suy luận đơn giản rằng “exporter ở root sẽ tự đăng ký tất cả bean của child” hoặc “exporter ở child chỉ thấy mọi bean cha mà không có rủi ro trùng”.

Cần chọn rõ ai chịu trách nhiệm export từng resource và kiểm thử từ MBeanServer.

### 3.2. Các module context độc lập

Ví dụ một ứng dụng nạp module A và B bằng hai \`AnnotationConfigApplicationContext\` tách biệt.

\`\`\`text
Module A context --> Exporter A --+
                                  +--> MBeanServer chung
Module B context --> Exporter B --+
\`\`\`

Với trường hợp này, mỗi exporter chỉ biết module của mình, nhưng ObjectName phải có namespace rõ ràng, ví dụ:

\`\`\`text
com.example.app:type=Worker,module=inventory,name=Primary
com.example.app:type=Worker,module=billing,name=Primary
\`\`\`

Giữ \`type/name\` mà bỏ \`module\` trong cả hai context sẽ gây collision.

### 3.3. Plugin context có vòng đời động

Một plugin được bật/tắt có thể tạo/đóng ApplicationContext. JMX resource của plugin cũng nên xuất hiện và biến mất tương ứng:

\`\`\`text
Plugin enabled  -> context created -> exporter registers MBeans
Plugin disabled -> context closed  -> exporter unregisters owned MBeans
\`\`\`

Nếu context không được đóng, hoặc MBean đăng ký thủ công mà không được cleanup, JMX registry sẽ chứa object cũ và có thể giữ tham chiếu đến classloader của plugin.

### 3.4. Integration tests chạy song song

Nhiều test contexts trong một JVM có thể cùng dùng platform MBeanServer. Test tạo \`ObjectName\` cố định và không cleanup dễ khiến test khác gặp \`InstanceAlreadyExistsException\`. Một cách giảm nhiễu là cấp MBeanServer riêng cho từng fixture/context hoặc đặt tên riêng, đồng thời đóng context sau test.

## 4. Vì sao AnnotationMBeanExporter có thể gây trùng đăng ký?

Với Spring annotation export, các object có metadata JMX có thể được autodetect rồi register khi context khởi tạo exporter. Khi nhiều context có cấu hình tương tự, các nguồn trùng lặp có thể là:

1. Cùng một class/bean bị tạo lại trong hai context nhưng đều dùng \`@ManagedResource(objectName = "...")\` cố định.
2. Một shared bean từ parent được export ở root và lại bị exporter của child đăng ký.
3. Một configuration class bật \`@EnableMBeanExport\` được import ở nhiều context.
4. Vừa có exporter từ annotation config, vừa khai báo thêm \`MBeanExporter\` tường minh cho cùng object.
5. Plugin reload trong khi registration cũ chưa unregister.
6. Một naming strategy tạo tên không có phân biệt module/instance.

Ví dụ:

\`\`\`java
@ManagedResource(objectName = "example.jmx:type=Worker,name=Primary")
public class WorkerMonitor {
    // ...
}
\`\`\`

Nếu module A và B cùng export object này lên một MBeanServer, tên sẽ trùng bất kể chúng nằm ở hai \`ApplicationContext\` độc lập.

**Phân biệt rõ:** việc có annotation trên một bean không tự đảm bảo nó đã được export. Cần exporter được khởi tạo và cấu hình thích hợp. Lỗi trùng thường phát sinh khi có hơn một registration thực sự, không đơn thuần vì metadata giống nhau.

## 5. Ba lựa chọn chiến lược export

| Chiến lược | Thiết kế | Khi phù hợp | Điểm phải kiểm soát |
|---|---|---|---|
| Một exporter tập trung | Một context quản lý registration cho toàn ứng dụng | Hệ thống module ổn định, quản trị tập trung | Tập bean có thể truy cập và lifecycle |
| Mỗi context một exporter | Module tự export MBean của nó | Plugin hoặc module độc lập | ObjectName namespace và cleanup |
| Server riêng theo context | Mỗi context có server và exporter riêng | Test isolation hoặc tách quản trị có chủ đích | Client kết nối đúng server và connector |

Một exporter tập trung không tự động thu thập bean từ mọi child context. Nếu module được nạp động, cần cơ chế truyền/đăng ký resource rõ ràng hoặc sử dụng exporter/module-local.

Một server riêng cũng không tự có endpoint remote; vẫn cần connector nếu client ở JVM khác phải truy cập.

## 6. Ví dụ: hai context dùng chung MBeanServer, mỗi context sở hữu exporter

Ví dụ dưới đây dùng explicit registration để thấy rõ thành phần nào chịu trách nhiệm. Có thể mở rộng sang annotation exporter sau khi hiểu kiến trúc.

### 6.1. Contract MBean

\`\`\`java
// ModuleMonitorMBean.java
public interface ModuleMonitorMBean {
    String getModule();
    int getCompletedTasks();
}
\`\`\`

\`\`\`java
// ModuleMonitor.java
import java.util.concurrent.atomic.AtomicInteger;

public final class ModuleMonitor implements ModuleMonitorMBean {
    private final String module;
    private final AtomicInteger completed = new AtomicInteger();

    public ModuleMonitor(String module) {
        this.module = module;
    }

    @Override
    public String getModule() {
        return module;
    }

    @Override
    public int getCompletedTasks() {
        return completed.get();
    }

    public void recordCompletion() {
        completed.incrementAndGet();
    }
}
\`\`\`

### 6.2. Cấp một MBeanServer chung

Trong ví dụ Java configuration, dùng platform server hoặc server được tạo một lần bên ngoài các context. Mỗi context sẽ được cung cấp cùng instance:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

MBeanServer sharedServer =
    ManagementFactory.getPlatformMBeanServer();
\`\`\`

Không cần mỗi module gọi \`MBeanServerFactory.newMBeanServer()\` nếu yêu cầu là tất cả module xuất hiện dưới cùng JMX endpoint.

### 6.3. Configuration riêng cho từng module

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

import javax.management.MBeanServer;
import java.util.Map;

@Configuration(proxyBeanMethods = false)
public class ModuleJmxConfiguration {
    private final MBeanServer server;
    private final String moduleName;

    public ModuleJmxConfiguration(
            MBeanServer server, String moduleName) {
        this.server = server;
        this.moduleName = moduleName;
    }

    @Bean
    public ModuleMonitor moduleMonitor() {
        return new ModuleMonitor(moduleName);
    }

    @Bean
    public MBeanExporter moduleExporter(ModuleMonitor monitor) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(server);
        exporter.setBeans(Map.of(
            "example.jmx:type=ModuleMonitor,module=" + moduleName,
            monitor
        ));
        exporter.setRegistrationPolicy(
            RegistrationPolicy.FAIL_ON_EXISTING);
        return exporter;
    }
}
\`\`\`

Khởi tạo các context riêng:

\`\`\`java
import org.springframework.context.annotation
    .AnnotationConfigApplicationContext;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class MultipleContextsDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            java.lang.management.ManagementFactory
                .getPlatformMBeanServer();

        try (var inventory =
                 new AnnotationConfigApplicationContext();
             var billing =
                 new AnnotationConfigApplicationContext()) {

            inventory.registerBean(
                ModuleJmxConfiguration.class,
                () -> new ModuleJmxConfiguration(
                    server, "inventory"));
            inventory.refresh();

            billing.registerBean(
                ModuleJmxConfiguration.class,
                () -> new ModuleJmxConfiguration(
                    server, "billing"));
            billing.refresh();

            ObjectName a = new ObjectName(
                "example.jmx:type=ModuleMonitor,module=inventory");
            ObjectName b = new ObjectName(
                "example.jmx:type=ModuleMonitor,module=billing");

            System.out.println(server.isRegistered(a)); // true
            System.out.println(server.isRegistered(b)); // true
        }
    }
}
\`\`\`

Ví dụ sử dụng Spring Context với các bean definitions được đăng ký trước \`refresh()\`. Cả hai exporter cùng dùng một server, nhưng mỗi context tự quản lý registration khác nhau. Khi các context đóng, Spring gọi lifecycle cleanup của exporter tương ứng để unregister các MBean do nó đăng ký theo chính sách của exporter.

**Lưu ý thiết kế:** nếu \`moduleName\` lấy từ plugin hoặc cấu hình bên ngoài, cần validate và/hoặc escape đúng cú pháp \`ObjectName\`. Không nối trực tiếp dữ liệu không tin cậy có thể chứa ký tự \`:,=*?\` vào ObjectName.

## 7. Thêm annotation export vào mô hình nhiều context

Một Spring-managed bean có thể dùng:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "example.jmx:type=Service,module=inventory,name=Primary")
public class InventoryStatus {
    private volatile boolean healthy = true;

    @ManagedAttribute
    public boolean isHealthy() {
        return healthy;
    }
}
\`\`\`

Để exporter phát hiện metadata annotation, cần cấu hình \`AnnotationMBeanExporter\` hoặc \`MBeanExporter\` với annotation metadata assembler tương ứng. Một lựa chọn là \`@EnableMBeanExport\` trên đúng context cần export.

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
class InventoryJmxConfig {
}
\`\`\`

Cấu hình này là ví dụ cách bật annotation export. Trong ứng dụng dùng MBeanServer chung, cần kết nối exporter do annotation configuration tạo với server mong muốn theo API và phiên bản Spring đang dùng. Tránh bật cùng một cấu hình ở cả parent và child nếu không có quy hoạch ownership.

### 7.1. Đặt ObjectName từ annotation hay naming strategy?

Với ít bean ổn định, \`@ManagedResource(objectName = "...")\` là tường minh. Nhưng khi cùng một class được dùng ở nhiều module/context, một ObjectName hard-coded dễ trùng.

Các cách tiếp cận:

- Khai báo class khác nhau với ObjectName riêng khi domain rõ và số lượng nhỏ.
- Sử dụng naming strategy trên exporter để đưa \`module/context\` vào tên.
- Tạo cấu hình export tường minh cho từng bean với ObjectName được tính từ module identifier đã validate.
- Để metadata annotation mô tả management interface, còn tên instance do exporter/naming strategy quyết định nếu cách kết hợp đó được cấu hình hỗ trợ.

Không phụ thuộc vào một tên bean trong Spring container để tự tạo ObjectName duy nhất nếu chưa xác minh naming strategy thực tế.

## 8. Chọn quy ước đặt tên cho nhiều context

Ví dụ quy ước:

\`\`\`text
<domain>:type=<type>,context=<context>,name=<resource>
\`\`\`

Ví dụ:

\`\`\`text
com.example.platform:type=Cache,context=root,name=ProductCache
com.example.platform:type=Worker,context=inventory,name=Primary
com.example.platform:type=Worker,context=billing,name=Primary
\`\`\`

Với nhiều instance của cùng module:

\`\`\`text
com.example.platform:type=Worker,context=inventory,instance=node-1
com.example.platform:type=Worker,context=inventory,instance=node-2
\`\`\`

Hãy chọn các key ổn định, không nhúng dữ liệu nhạy cảm, không dùng thông tin thay đổi liên tục như current queue size. Nếu một tiến trình chỉ có một instance của module, không cần tạo key giả để làm phức tạp tên.

### 8.1. Canonical name và collision

Hai ObjectName có cùng domain và cùng tập key/value vẫn tương đương dù thứ tự key khác nhau:

\`\`\`text
demo:type=Worker,module=billing
demo:module=billing,type=Worker
\`\`\`

Đừng cố giải quyết collision bằng cách đảo thứ tự key. Chỉ đổi namespace hoặc identity mới tạo được ObjectName khác.

### 8.2. Query theo module/context

\`\`\`java
import javax.management.ObjectName;

ObjectName inventoryPattern = new ObjectName(
    "com.example.platform:context=inventory,*");
\`\`\`

Dấu \`,*\` cho phép những key khác như \`type\` và \`name\`. Thiếu \`,*\`, mẫu có thể yêu cầu tập key chỉ gồm \`context\`, khiến query rỗng dù nhiều resource đang tồn tại.

## 9. Parent–child context: quyền quan sát bean và lifecycle

Parent/child contexts có quan hệ lookup không đối xứng:

\`\`\`text
Parent can see its own beans.
Child may resolve beans from parent.
Parent does not automatically enumerate child beans.
\`\`\`

Nếu root context có exporter autodetect, đừng giả định nó tự phát hiện bean chỉ được khai báo ở child. Nếu child có exporter riêng, phải xác minh phạm vi scan và registration để tránh export lại bean quản trị vốn do parent sở hữu.

Một cách phân chia trách nhiệm rõ ràng:

- Root exporter sở hữu MBean của dịch vụ chung trong root.
- Child exporter chỉ đăng ký MBean riêng của child.
- ObjectNames phân biệt root/child.
- Mỗi exporter chỉ unregister những MBean do nó quản lý.
- Context child được đóng trước khi parent đóng nếu lifecycle của ứng dụng phụ thuộc parent.

Với một Spring application phức tạp, test nên so sánh \`queryNames\` trên cùng server trước/sau khi tạo và đóng child context để xác nhận ownership chính xác.

## 10. RegistrationPolicy không thay thế thiết kế namespace

Spring cung cấp chính sách khi exporter gặp ObjectName đã tồn tại:

| Policy | Hành vi | Tác động trong nhiều context |
|---|---|---|
| \`FAIL_ON_EXISTING\` | Fail khi có tên trùng | Phát hiện collision nhanh |
| \`IGNORE_EXISTING\` | Bỏ qua registration mới | Có thể ẩn việc context mới không được export |
| \`REPLACE_EXISTING\` | Thay MBean cùng tên | Có thể thay resource của context khác, gây khó cleanup |

\`FAIL_ON_EXISTING\` là lựa chọn minh họa tốt vì lỗi có ngữ nghĩa rõ. \`IGNORE_EXISTING\` không giải quyết việc context khác muốn công khai MBean của chính nó. \`REPLACE_EXISTING\` cần cực kỳ thận trọng nếu các context có lifecycle độc lập; một context đóng sau khi đã thay registration của context khác có thể dẫn tới kết quả khó dự đoán.

Nếu module A và B đều cần MBean, hãy cấp ObjectName duy nhất theo module, thay vì phụ thuộc policy để quyết định ai thắng.

## 11. Vòng đời exporter và cleanup

Với MBeanExporter, Spring lifecycle thường bao gồm:

\`\`\`text
Context refresh
    |
    v
Exporter initialized
    |
    v
Register owned MBeans
    |
    v
Context running
    |
    v
Context closes
    |
    v
Exporter unregisters owned MBeans
\`\`\`

Một số tình huống thực tế có thể làm lifecycle phức tạp:

- Một exporter đăng ký đối tượng trên MBeanServer được nhiều context dùng chung.
- Plugin bị bỏ tham chiếu nhưng context vẫn chưa đóng.
- Một đối tượng được đăng ký bằng code thủ công ngoài exporter.
- MBean đã tồn tại trước khi exporter khởi tạo.
- Context khởi tạo lỗi giữa chừng và registration chỉ hoàn tất một phần.
- Có chính sách replace registration của exporter khác.

Vì vậy nên kiểm tra thực tế qua \`MBeanServer.isRegistered\` và \`queryNames\` sau mỗi mốc tạo/đóng context. Không tự hủy đăng ký mọi tên có chung domain khi một module dừng, vì tên đó có thể thuộc context khác.

## 12. Tách MBeanServer theo context: khi nào cần?

Không phải nhiều context là lý do bắt buộc tạo nhiều \`MBeanServer\`. Tuy nhiên server riêng có ích trong một số trường hợp:

### 12.1. Kiểm thử độc lập

Một server riêng tránh collision với platform MBeanServer:

\`\`\`java
MBeanServer isolated =
    javax.management.MBeanServerFactory.newMBeanServer();
\`\`\`

Inject server này vào exporter của test. Khi test kết thúc, đóng context và giải phóng fixture.

### 12.2. Quản trị module bị cô lập

Một hệ thống plugin có thể cấp mỗi plugin một server riêng, nhưng cần giải quyết cách client tìm các server ấy và có cần connector riêng không. JConsole attach vào platform MBeanServer không tự duyệt các server khác.

### 12.3. Một management endpoint thống nhất

Nếu yêu cầu vận hành là một nơi xem toàn bộ MBean, dùng server chung thường đơn giản hơn. Tách server sẽ làm việc vận hành/monitoring phức tạp, vì phải gắn hoặc aggregate nhiều nguồn.

Cân nhắc tính quan sát, quyền truy cập và vòng đời trước khi lựa chọn.

## 13. Kiểm thử integration cho nhiều ApplicationContext

Mục tiêu là kiểm thử **kết quả đăng ký trong MBeanServer**, không chỉ xác minh ApplicationContext có bean.

Ví dụ test ý tưởng:

\`\`\`java
import org.junit.jupiter.api.Test;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.lang.management.ManagementFactory;

import static org.junit.jupiter.api.Assertions.*;

class MultiContextJmxTest {
    @Test
    void eachModuleOwnsItsRegistration() throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName inventoryName = new ObjectName(
            "example.jmx:type=ModuleMonitor,module=inventory");
        ObjectName billingName = new ObjectName(
            "example.jmx:type=ModuleMonitor,module=billing");

        // Tạo context theo MultipleContextsDemo, giữ references.
        // Sau khi cả hai context refresh:
        assertTrue(server.isRegistered(inventoryName));
        assertTrue(server.isRegistered(billingName));

        // Sau khi đóng inventory context:
        // assertFalse(server.isRegistered(inventoryName));
        // assertTrue(server.isRegistered(billingName));

        // Sau khi đóng billing context:
        // assertFalse(server.isRegistered(billingName));
    }
}
\`\`\`

Đoạn này trình bày assertions trọng tâm; cần nối setup/teardown context thực tế từ ví dụ trên để trở thành test runnable. Khi cần test song song, nên dùng \`MBeanServer\` riêng thay platform server; tránh việc hai test cùng ghi registry global.

Các case nên có:

1. Hai context khởi động thành công với ObjectName khác nhau.
2. Query theo module trả đúng tập MBean.
3. Đóng context A chỉ xóa MBean của A.
4. Context B tiếp tục đọc attribute bình thường.
5. Khởi động lại A không báo duplicate.
6. Cố tình trùng tên và quan sát lỗi \`FAIL_ON_EXISTING\`.
7. Nếu bật annotation exporter ở parent/child, kiểm tra các bean chung không bị export lặp.
8. Nếu dùng server riêng, client phải kết nối đúng server mới nhìn thấy object.

## 14. Chẩn đoán sự cố có nhiều ApplicationContext

| Triệu chứng | Nguyên nhân điển hình | Hướng kiểm tra |
|---|---|---|
| \`InstanceAlreadyExistsException\` | Nhiều exporter dùng cùng ObjectName | Kiểm tra exporter, naming strategy, server |
| MBean xuất hiện một lần nhưng module B thiếu | \`IGNORE_EXISTING\` che collision | So tên và policy, sửa namespace |
| Root MBean có, child MBean không | Exporter root không thấy child bean | Kiểm tra phạm vi BeanFactory và exporter của child |
| Child đóng nhưng MBean còn | Context chưa close hoặc registration thủ công | Kiểm tra exporter ownership/unregister |
| Đóng A làm B mất MBean | Dùng chung tên và replace policy | Tránh replace chéo; đặt tên tách biệt |
| MBean có trong server riêng nhưng JConsole không thấy | Client kết nối platform server | Kiểm tra MBeanServer được exporter chọn |
| Cùng MBean xuất hiện hai lần với tên khác | Hai exporter cùng export một resource | Xác định owner duy nhất |
| Remote JMX không thấy bean | Connector gắn server khác hoặc lỗi transport | Kiểm tra connector và server reference |
| Context reload lỗi | MBean cũ chưa cleanup hoặc tên không thay đổi | Theo dõi lifecycle và registration policy |

Khi debug, thu thập bằng chứng theo thứ tự:

\`\`\`text
1. Bao nhiêu ApplicationContext đang hoạt động?
2. Mỗi context định nghĩa exporter nào?
3. Exporter nào dùng MBeanServer nào?
4. Mỗi exporter đăng ký ObjectName nào?
5. Bean nào thuộc context nào?
6. Sau khi close/reload, tên nào còn đăng ký?
7. Client đang kết nối đến đúng server chứ?
\`\`\`

Không thay đổi \`RegistrationPolicy\` ngay khi gặp lỗi trùng nếu chưa xác định owner thực sự.

## 15. Ranh giới bảo mật và remote connector

Nhiều context không tự tạo ranh giới bảo mật JMX. Nếu tất cả exporter cùng dùng MBeanServer và remote connector, một client kết nối tới server đó có thể thấy nhiều module, tùy cơ chế bảo mật và access control.

- Namespace trong ObjectName hỗ trợ tổ chức và tìm kiếm; nó **không tự phân quyền**.
- \`RegistrationPolicy\` không cấp quyền truy cập.
- Tạo server riêng chỉ tạo ranh giới registry; vẫn phải thiết kế kết nối và authorization nếu expose remote.
- Operation quản trị có tác dụng phụ nên hạn chế quyền và có audit phù hợp.
- Không đưa secret hoặc dữ liệu nhạy cảm vào ObjectName/attributes.
- Remote JMX phải dùng mạng quản trị riêng, xác thực và mã hóa theo chính sách vận hành.

Nếu các module có mức độ tin cậy rất khác nhau, cần thiết kế kiểm soát truy cập ở tầng connector hoặc cơ chế quản trị phù hợp; không dựa vào việc module có ApplicationContext riêng để coi như đã cô lập quyền.

## 16. Bài tập thực hành

### Bài tập A — Hai context, một server

Tạo module A và B cùng dùng platform MBeanServer. Mỗi module có \`ModuleMonitor\` và \`MBeanExporter\`. Đăng ký:

\`\`\`text
training.multictx:type=Module,name=A
training.multictx:type=Module,name=B
\`\`\`

Kiểm tra hai MBean cùng tồn tại và có thể đọc thuộc tính. Đóng A rồi kiểm tra B vẫn hoạt động.

### Bài tập B — Cố tình tạo collision

Đổi ObjectName của A và B thành giống nhau. Dùng \`FAIL_ON_EXISTING\` rồi ghi nhận lỗi; thử \`IGNORE_EXISTING\` trong môi trường lab và giải thích vì sao B không được xuất như mong muốn.

### Bài tập C — Parent/child contexts

Tạo parent chứa một shared service và child chứa một module service. Bật annotation export ở từng context theo phương án của bạn. Kiểm tra \`queryNames\` để xác định mỗi MBean được đăng ký một lần và ai sở hữu cleanup.

### Bài tập D — Plugin reload

Tạo và đóng một plugin context ba lần. Dùng cùng ObjectName giữa các lần nhưng không đồng thời. Sau mỗi lần đóng, kiểm tra \`isRegistered=false\`. Nếu thất bại, truy vết cleanup thay vì dùng \`REPLACE_EXISTING\` để che lỗi.

### Bài tập E — Test isolation

Chạy hai integration tests sử dụng cùng tên ObjectName nhưng mỗi test inject một \`MBeanServerFactory.newMBeanServer()\` riêng. Giải thích vì sao không collision và vì sao JConsole mặc định không nhìn thấy các registry test này.

## 17. Câu hỏi tự kiểm tra

1. Vì sao ObjectName có thể trùng dù hai bean thuộc hai ApplicationContext khác nhau?
2. Root exporter có tự thấy toàn bộ bean trong child context không?
3. Khi nào nên dùng một exporter tập trung?
4. \`IGNORE_EXISTING\` có giải quyết thiếu namespace không?
5. Vì sao \`REPLACE_EXISTING\` nguy hiểm khi các context có vòng đời độc lập?
6. Context đóng có tự hủy một MBean đã đăng ký thủ công ngoài exporter không?
7. MBeanServer riêng có làm client platform JMX nhìn thấy bean của nó không?
8. Naming strategy giúp giải quyết bài toán gì khi cùng class được tái sử dụng?
9. Trong Spring, exporter nào chịu trách nhiệm unregister MBean khi plugin dừng?
10. Tách context có đồng nghĩa tách quyền truy cập remote JMX không?

## 18. Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — \`AnnotationMBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/AnnotationMBeanExporter.html
- Spring Framework API — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework API — \`@EnableMBeanExport\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/EnableMBeanExport.html
- Java SE 21 API — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 API — \`ObjectName\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html

**Ghi nhớ:** trong nhiều ApplicationContext, mỗi exporter cần có ownership rõ ràng, kết nối đúng MBeanServer, tạo ObjectName duy nhất và cleanup theo lifecycle của context. Khi thiết kế đúng các ranh giới này, annotation export trở thành một cơ chế quản trị ổn định cho toàn ứng dụng.
