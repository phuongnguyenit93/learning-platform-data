# Phân biệt lỗi Spring context với lỗi JMX runtime

## 1. Mục tiêu

Khi một ứng dụng Spring Framework sử dụng JMX, cùng một triệu chứng “không nhìn thấy MBean”, “không đọc được attribute” hoặc “ứng dụng không khởi động” có thể bắt nguồn từ những tầng hoàn toàn khác nhau. Một lỗi có thể xảy ra khi Spring tạo ApplicationContext, khi MBeanExporter đăng ký bean, khi MBeanServer xử lý lời gọi, hoặc khi client từ xa kết nối qua JMX connector.

Việc chẩn đoán hiệu quả bắt đầu bằng câu hỏi: **Lỗi xảy ra ở thời điểm nào, tại tầng nào, và thành phần nào thực sự ném exception?** Nếu không phân biệt đúng tầng, người vận hành dễ sửa sai: tăng timeout của client trong khi bean Spring chưa được tạo, bật registration replacement để che xung đột ObjectName, hoặc tắt TLS chỉ vì JConsole không kết nối được.

Bài học này tập trung vào:
- Phân biệt lỗi Spring context, lỗi JMX export/registration, lỗi JMX runtime và lỗi remote connector.
- Nhận diện các exception và thời điểm phát sinh.
- Lần theo chuỗi nguyên nhân của \`BeanCreationException\` để tìm lỗi gốc.
- Kiểm tra MBeanExporter, MBeanServer và ObjectName thay vì chỉ nhìn JConsole.
- Sử dụng \`MBeanInfo\`, \`isRegistered\`, \`queryNames\` và log để khoanh vùng sự cố.
- Phân biệt lỗi do bean, AOP proxy, annotation, operation, serialization, quyền và kết nối.
- Thiết kế runbook có thể dùng cho development, CI và production.

## 2. Mô hình bốn tầng

\`\`\`text
TẦNG A — SPRING CONTEXT
  @Configuration / component scan / bean conditions
    |
    +-- BeanDefinition / Dependency Injection
    +-- BeanFactory / BeanPostProcessor
    +-- AOP proxies
    +-- Context refresh / destroy
    |
    v
TẦNG B — JMX EXPORT
  MBeanExporter / AnnotationMBeanExporter
    |
    +-- chọn bean
    +-- đọc metadata / MBeanInfoAssembler
    +-- tạo ObjectName
    +-- registerMBean
    |
    v
TẦNG C — JMX RUNTIME
  MBeanServer
    |
    +-- registry ObjectName -> MBean
    +-- getAttribute / setAttribute
    +-- invoke / queryNames
    +-- notification listener
    |
    v
TẦNG D — REMOTE CONNECTOR / CLIENT
  JMXConnectorServer <-> JMXConnector
    |
    +-- Service URL / DNS / firewall / RMI stub
    +-- authentication / TLS
    +-- connection loss / timeout
    +-- remote serialization / callback
\`\`\`

Một số exception đi xuyên nhiều tầng dưới dạng wrapper. Chẳng hạn, khi \`MBeanExporter\` đăng ký MBean trong quá trình Spring refresh và \`MBeanServer\` báo \`InstanceAlreadyExistsException\`, Spring có thể bọc lỗi đó trong \`MBeanExportException\` và cuối cùng \`BeanCreationException\`. Nhìn exception ở dòng đầu không đủ để kết luận gốc lỗi thuộc Spring dependency injection.

Điểm quan trọng: **tầng phát hiện lỗi và tầng gây lỗi không phải lúc nào giống nhau**.

## 3. Bảng phân biệt nhanh

| Hiện tượng | Tầng đáng nghi | Kiểm tra đầu tiên |
|---|---|---|
| Context refresh thất bại, bean thiếu dependency | Spring context | Root cause của \`BeanCreationException\` |
| Context chạy nhưng không có bean monitor | Spring context | \`containsBean\`, profiles, conditions |
| Bean tồn tại nhưng không được export | JMX export | Exporter, autodetection, annotation/assembler |
| \`InstanceAlreadyExistsException\` | JMX registration | ObjectName trùng trong cùng server |
| \`NotCompliantMBeanException\` | JMX contract/export | Interface MBean, MXBean, proxy, assembler |
| \`MalformedObjectNameException\` | JMX naming | Cú pháp domain/key properties |
| MBean đăng ký nhưng attribute không thấy | JMX metadata | \`MBeanInfo.getAttributes()\` |
| \`AttributeNotFoundException\` | JMX runtime contract | Tên attribute và read/write flags |
| \`ReflectionException\` khi invoke | JMX operation dispatch | Name, signature, overload |
| \`MBeanException\` khi invoke | Implementation | Cause bên trong managed operation |
| JConsole không kết nối | Remote connector | Service URL, network, auth/TLS |
| Registry port mở nhưng lời gọi timeout | RMI transport | Host/port thực trong stub |
| Client đã kết nối nhưng không thấy app MBean | Sai server/endpoint/naming | Connector trỏ MBeanServer nào? |
| Notification không đến | Listener/filter/runtime/remote | Registration, filter, lifecycle |
| MBean biến mất sau redeploy | Lifecycle | Exporter owner, unregister, context close |

Đây là gợi ý để ưu tiên kiểm tra chứ không phải ánh xạ tuyệt đối. Ví dụ một \`InstanceNotFoundException\` có thể do ObjectName sai, MBean chưa được đăng ký, hoặc MBean vừa bị unregister khi context đóng.

## 4. Tầng A: lỗi Spring ApplicationContext

Spring context chịu trách nhiệm đọc configuration, tạo bean, inject dependencies và áp dụng BeanPostProcessor. Những lỗi phổ biến:

### 4.1 Bean không được tạo

Ví dụ:

\`\`\`java
@Configuration
public class MonitoringConfig {
    @Bean
    public QueueMonitor queueMonitor(QueueRepository repository) {
        return new QueueMonitor(repository);
    }
}
\`\`\`

Nếu \`QueueRepository\` không có bean phù hợp, context có thể báo \`UnsatisfiedDependencyException\` hoặc \`NoSuchBeanDefinitionException\`. JMX hoàn toàn chưa có cơ hội đăng ký monitor.

Checklist:
1. Bean definition có được load không?
2. Profile và condition có bật không?
3. Component scanning có bao gồm package không?
4. Dependency có tồn tại và đủ điều kiện autowire không?
5. Factory method/constructor có ném exception không?
6. AOP hoặc BeanPostProcessor có lỗi khi tạo proxy không?

Cần xử lý tầng Spring trước khi điều tra JConsole.

### 4.2 Bean có mặt nhưng JMX không có

\`\`\`java
boolean hasBean = context.containsBean("queueMonitor");
Object bean = context.getBean("queueMonitor");
System.out.println(bean.getClass().getName());
\`\`\`

Nếu \`hasBean=true\`, chưa thể nói exporter hoạt động. Phải kiểm tra \`@EnableMBeanExport\` hoặc \`MBeanExporter\`, bean mapping, annotation metadata và MBeanServer.

Nếu bean bị \`@Lazy\`, lifecycle và timing khởi tạo có thể khác dự kiến. Không cố ép khởi tạo mọi bean chỉ để chẩn đoán một MBean trong production.

### 4.3 Exception xuất hiện trong context refresh nhưng do JMX

Spring exporter có thể đăng ký MBean trong quá trình khởi tạo. Khi registration thất bại, context refresh cũng có thể fail. Stack trace thường có nhiều lớp:

\`\`\`text
BeanCreationException: Error creating bean 'mbeanExporter'
  caused by MBeanExportException
    caused by InstanceAlreadyExistsException:
      com.example.ops:type=Worker,name=Import
\`\`\`

Lỗi được báo ở Spring lifecycle, nhưng nguyên nhân gốc là ObjectName đã có trong MBeanServer. Cần đọc phần \`Caused by\` sâu nhất và kiểm tra registration thực tế.

## 5. Tầng B: lỗi chọn bean và export

\`MBeanExporter\` có thể xuất bean bằng explicit mappings, Standard MBean autodetection hoặc assembler-based autodetection. \`AnnotationMBeanExporter\` chọn bean theo metadata annotation trong cấu hình tương ứng.

Có ba bước nên tách:

\`\`\`text
Bean tồn tại trong context?
         |
         v
Exporter có chọn bean làm ứng viên?
         |
         v
MBeanInfo / ObjectName hợp lệ?
         |
         v
registerMBean thành công?
\`\`\`

Nếu bean bị bỏ qua ở bước lựa chọn, registry không có MBean và có thể không xuất hiện exception rõ ràng. Nếu bean được chọn nhưng metadata không hợp lệ, có thể thấy \`NotCompliantMBeanException\`, naming error hoặc \`MBeanExportException\`.

### 5.1 Annotation thiếu hoặc đặt sai chỗ

\`\`\`java
@Component
public class CacheMonitor {
    @ManagedAttribute
    public long getHitCount() {
        return 0L;
    }
}
\`\`\`

Nếu cấu hình annotation-driven yêu cầu metadata \`@ManagedResource\` cho class mà class không có, nó có thể không được tự phát hiện. Không nên giải quyết bằng cách bật autodetection rộng toàn context vì điều đó có thể export nhầm bean khác.

Cấu hình có chủ đích:

\`\`\`java
@Component
@ManagedResource(objectName = "com.example.ops:type=Cache,name=Catalog")
public class CacheMonitor {
    @ManagedAttribute
    public long getHitCount() {
        return 0L;
    }
}
\`\`\`

Cần một annotation exporter tương ứng được kích hoạt, và phải kiểm tra metadata thực sự ở \`MBeanInfo\`.

### 5.2 AOP proxy làm thay đổi cách nhận diện

Khi bật \`@Transactional\` hoặc AOP auto-proxy, bean thực tế có thể là JDK dynamic proxy hoặc class-based proxy. Interface MBean hoặc annotation trên target class có thể được assembler nhìn thấy khác nhau tùy cơ chế export.

\`\`\`java
Object bean = context.getBean("cacheMonitor");
System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.getTargetClass(bean));
\`\`\`

Nếu JDK proxy không expose management interface, Standard MBean detection có thể không nhận như trước. Một management adapter riêng thường giúp tách bề mặt JMX khỏi domain service bị AOP proxy.

Không dùng việc unwrap target để sửa lỗi một cách mù quáng: lời gọi trực tiếp vào target có thể bỏ qua transaction, security hoặc audit advice mà proxy cung cấp.

### 5.3 Trùng exporter hoặc trùng ObjectName

Một context có thể đồng thời bật \`@EnableMBeanExport\`, XML export và \`@Bean MBeanExporter\`. Nếu hai exporter đăng ký cùng ObjectName, một lần registration sẽ xung đột. Phải phân định một owner cho mỗi registration, tránh tùy tiện dùng chính sách replace.

Cách dò exporter:

\`\`\`java
String[] exporters = context.getBeanNamesForType(
    MBeanExporter.class, true, false);
System.out.println(Arrays.toString(exporters));
\`\`\`

Hai exporter không tự động là lỗi nếu tập MBean rời nhau. Ngược lại, một exporter vẫn có thể lỗi nếu hai bean có ObjectName trùng.

## 6. Tầng C: lỗi JMX runtime

Khi MBean đã được đăng ký, JMX runtime quyết định attribute và operation nào khả dụng. Một Java method có thể tồn tại nhưng không thuộc management interface hoặc không được metadata assembler công bố.

### 6.1 Kiểm tra đúng MBeanServer

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "com.example.ops:type=Worker,name=Import");

System.out.println(server.isRegistered(name));
\`\`\`

Đây là kiểm tra platform MBeanServer. Nếu Spring exporter dùng custom server, phải truyền server đó; không dùng platform server rồi kết luận MBean thiếu.

### 6.2 ObjectName đúng nhưng member không đúng

\`\`\`java
MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo a : info.getAttributes()) {
    System.out.println(a.getName() + " read=" + a.isReadable()
        + " write=" + a.isWritable());
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println(op.getName());
}
\`\`\`

\`MBeanInfo\` là nguồn xác minh thực tế cho contract đang được MBeanServer công bố. Nếu \`getAttribute(name, "QueueDepth")\` gặp \`AttributeNotFoundException\`, kiểm tra attribute name đúng chính tả/case và có nằm trong \`MBeanInfo\` không.

### 6.3 Method tồn tại trong Java nhưng không được công bố

Standard MBean chỉ công bố thành viên thuộc management interface tương ứng. Annotation-driven export phụ thuộc metadata. Vì vậy việc gọi:

\`\`\`java
connection.invoke(name, "deleteInternalState",
    new Object[0], new String[0]);
\`\`\`

có thể thất bại nếu \`deleteInternalState\` là public Java method nhưng không nằm trong JMX contract. Đây có thể là hành vi đúng của thiết kế bảo mật, không phải lỗi Spring context.

### 6.4 Operation signature sai

\`\`\`java
connection.invoke(
    name,
    "setThreshold",
    new Object[]{Integer.valueOf(10)},
    new String[]{"int"}
);
\`\`\`

Trong \`invoke\`, signature mô tả **kiểu tham số khai báo của operation**, không phải kiểu runtime của object wrapper trong \`Object[]\`. Nếu operation nhận primitive \`int\`, signature thường là \`"int"\`, không phải \`"java.lang.Integer"\`. Với overload, phải lấy signature từ \`MBeanOperationInfo\`.

Một lời gọi không khớp có thể dẫn tới \`ReflectionException\` hoặc exception liên quan dispatch. Không nên sửa Java method nếu sai chỉ nằm ở client signature.

## 7. Khi managed method tự ném exception

Giả sử:

\`\`\`java
@ManagedOperation
public void requestRefresh() {
    if (refreshRunning) {
        throw new IllegalStateException("Refresh already running");
    }
    startRefresh();
}
\`\`\`

Nếu JMX invocation vào đúng MBean và đúng operation nhưng implementation ném exception, client có thể nhận \`MBeanException\` hoặc \`RuntimeMBeanException\` tùy loại exception và đường xử lý. Cần đọc nguyên nhân, không gán thành lỗi connector.

Phân biệt:
- **JMX dispatch không tìm thấy method:** sửa operation name/signature hoặc export contract.
- **Method được gọi nhưng logic từ chối:** kiểm tra precondition/state và exception của ứng dụng.
- **Method chạy rồi client timeout:** không biết chắc side effect đã hoàn tất hay chưa.
- **Operation bất đồng bộ trả ID:** phải đọc trạng thái tác vụ thay vì dựa hoàn toàn vào response ban đầu.

Đối với thao tác điều khiển production, không retry mù sau timeout: có thể request đã được thực thi nhưng response bị mất.

## 8. Attribute lỗi vì getter truy cập I/O nặng

Getter trong JMX không phải property tĩnh; nó có thể chạy code Java tùy ý:

\`\`\`java
@ManagedAttribute
public long getPendingOrders() {
    return repository.countPending();
}
\`\`\`

Nếu database chậm, \`getAttribute\` bị chậm hoặc lỗi. Điều này khác với MBean không đăng ký. Khi \`server.isRegistered(name)=true\` nhưng đọc attribute bị treo, hãy điều tra logic getter, DB timeout, lock contention và polling rate.

Giải pháp thường dùng là cached snapshot hoặc counter đã được cập nhật sẵn, còn tính toán nặng chuyển sang background refresh có timeout. Tránh tăng JMX client timeout mà bỏ qua việc getter tiếp tục giữ DB connection hoặc thread server.

## 9. Tầng D: connector, client và transport

Một MBean có thể hoạt động hoàn toàn bình thường khi gọi local qua MBeanServer nhưng không truy cập được từ xa.

\`\`\`text
Local JMX call: OK
       |
       v
JMXConnectorServer
       |
       +-- RMI registry / stub
       +-- DNS / firewall
       +-- authentication / TLS
       +-- connector lifecycle
       |
       v
Remote JMX client: FAILED
\`\`\`

Các nguyên nhân thường gặp:

| Triệu chứng remote | Nguyên nhân có thể |
|---|---|
| Connection refused | Sai host/port, connector chưa start |
| Registry lookup OK nhưng invoke lỗi | RMI stub công bố endpoint không tới được |
| Authentication failed | Sai credential hoặc server policy |
| SSLHandshakeException | Truststore, certificate, TLS mismatch |
| MalformedURLException | JMXServiceURL sai cú pháp |
| IOException sau thời gian hoạt động | Network/server restart hoặc connector bị đóng |
| Client thấy JVM metrics nhưng thiếu app MBean | Exporter dùng server khác hoặc ObjectName sai |

Trong JMX RMI, registry lookup và connector endpoint có thể sử dụng host/port khác nhau. Mở được registry port không đủ để chứng minh đường remote JMX thông suốt.

### 9.1 Đừng sửa lỗi bằng cách tắt bảo mật

Khi thấy authentication/TLS failure, không nên tắt:

\`\`\`text
com.sun.management.jmxremote.authenticate=false
com.sun.management.jmxremote.ssl=false
\`\`\`

trên endpoint có thể truy cập từ mạng không đáng tin cậy. Cần sửa credential, certificate trust, hostname và chính sách mạng. Spring \`@ManagedResource\` không tự bảo vệ connector.

## 10. Cây quyết định chẩn đoán

\`\`\`text
Ứng dụng có khởi động thành công?
 ├── KHÔNG
 │    |
 │    +── Root cause là dependency/bean/profile?
 │    |      └── SPRING CONTEXT ERROR
 │    |
 │    +── Root cause là MBeanExportException/JMException?
 │           └── JMX EXPORT / REGISTRATION ERROR
 │
 └── CÓ
      |
      +── Bean quản trị có trong ApplicationContext?
      |      ├── KHÔNG -> Bean scan/condition/definition
      |      └── CÓ
      |           |
      |           +── MBeanServer đúng có đăng ký ObjectName?
      |                  ├── KHÔNG -> Exporter/naming/registration
      |                  └── CÓ
      |                       |
      |                       +── Local getAttribute/invoke OK?
      |                              ├── KHÔNG -> Runtime contract/logic
      |                              └── CÓ
      |                                   |
      |                                   +── Remote connector OK?
      |                                          ├── KHÔNG -> URL/network/TLS/auth
      |                                          └── CÓ -> Client ObjectName,
      |                                                   signature, rights,
      |                                                   timing/lifecycle
\`\`\`

Cây này giúp tránh nhảy thẳng sang lỗi network khi context thậm chí không có MBean.

## 11. Ví dụ thực tế: context refresh thất bại vì trùng ObjectName

Cấu hình:

\`\`\`java
@Configuration
@EnableMBeanExport
public class JmxConfig {
    @Bean
    public AnnotationMBeanExporter anotherExporter() {
        return new AnnotationMBeanExporter();
    }
}
\`\`\`

Tùy registration của infrastructure bean và phiên bản Spring, cấu hình có thể tạo đường export chồng lấn. Nếu hai exporter đăng ký cùng MBean dưới cùng ObjectName, xảy ra collision.

Một stack trace có thể gồm:

\`\`\`text
BeanCreationException
  └── MBeanExportException
       └── InstanceAlreadyExistsException
\`\`\`

Phân loại: lỗi xuất hiện trong **Spring context refresh**, nhưng root cause thuộc **JMX registration**. Giải pháp là chọn một đường annotation export chính, hoặc phân tách phạm vi exporter rõ ràng; không mặc định dùng registration replacement.

## 12. Ví dụ thực tế: MBean biến mất sau khi bật @Transactional

Trước thay đổi, target class implement \`WorkerStatusMBean\` và exporter nhận diện Standard MBean. Sau khi thêm transaction advice, bean có thể được JDK dynamic proxy hóa và không expose đúng management interface theo cấu hình.

Triệu chứng:
- Spring \`containsBean("workerStatus")=true\`.
- \`AopUtils.isAopProxy(bean)=true\`.
- \`server.isRegistered(name)=false\`.
- Log exporter có thể cho thấy bean không đủ điều kiện hoặc đăng ký lỗi.

Chẩn đoán:
1. Xác định proxy interfaces.
2. Kiểm tra exporter/assembler được dùng.
3. Xác nhận interface quản trị có được proxy expose không.
4. Nếu cần, dùng management adapter riêng gọi Spring service qua proxy.
5. Kiểm chứng MBeanInfo sau thay đổi.

Không bypass proxy bằng cách đăng ký raw target tùy tiện: transaction/security advice có thể bị bỏ qua khi JMX gọi target trực tiếp.

## 13. Ví dụ thực tế: local OK, remote không thấy MBean

Giả sử:

\`\`\`java
MBeanServer customServer = MBeanServerFactory.createMBeanServer(
    "com.example.private");
exporter.setServer(customServer);
\`\`\`

Trong khi JMX connector lại phục vụ platform MBeanServer. Local code dùng \`customServer.isRegistered(name)\` trả true, nhưng JConsole trên connector platform không thấy bean.

Đây không phải lỗi Spring bean hay metadata. Vấn đề là exporter và connector trỏ **hai MBeanServer khác nhau**.

Cách sửa:
- Dùng cùng server reference nếu muốn công bố bean qua connector đó.
- Hoặc tạo connector riêng cho custom server với network/security phù hợp.
- Không sao chép MBean bừa bãi sang registry khác chỉ để “hiện trên JConsole”.

## 14. Ví dụ thực tế: attribute tồn tại nhưng luôn timeout

\`MBeanInfo\` cho thấy attribute \`PendingJobs\` đã được công bố. Client có thể query MBean, nhưng \`getAttribute\` bị timeout.

Tình huống này thường thuộc runtime getter:
- Getter chờ SQL query.
- Getter lấy lock đang bị giữ bởi worker thread.
- Getter gọi HTTP health endpoint đang lỗi.
- Getter serialize dữ liệu quá lớn.
- Monitoring agents poll đồng thời gây stampede.

Kiểm tra local call latency, dependency metrics, thread dump và timeout server-side. Nếu remote client timeout, không mặc định server đã ngừng chạy getter.

## 15. Dùng MBeanInfo để xác minh hợp đồng

Sau khi xác định đúng MBeanServer và ObjectName:

\`\`\`java
import javax.management.*;

MBeanInfo info = server.getMBeanInfo(name);

System.out.println(info.getClassName());

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.println("attribute=" + attribute.getName()
        + ", readable=" + attribute.isReadable()
        + ", writable=" + attribute.isWritable());
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println("operation=" + operation.getName());
}
\`\`\`

Không suy đoán rằng tên Java getter \`getQueueDepth()\` chắc chắn hiển thị y nguyên thành một operation: trong JMX nó thường là attribute \`QueueDepth\`. Nếu management interface/assembler khác nhau, member set cũng khác. MBeanInfo phản ánh chính xác runtime contract được công bố lúc đó.

Kiểm tra luôn các member **không** được xuất. Một operation nhạy cảm xuất nhầm là vấn đề bảo mật, không chỉ là lỗi chẩn đoán.

## 16. Notification: phân biệt lỗi filter với lỗi emitter

Notification listener có thể không nhận event vì:
- MBean không phát notification.
- Listener đăng ký sai ObjectName.
- Filter loại event.
- Handback bị nhầm với userData.
- Listener bị remove khi context đóng.
- Remote connection bị ngắt.
- Callback bất đồng bộ chưa chạy xong.

Cách chẩn đoán:
1. Kiểm tra \`MBeanInfo.getNotifications()\` để xem metadata.
2. Test emitter local bằng listener không filter.
3. Thêm filter và kiểm tra positive/negative events.
4. Dùng \`CountDownLatch\` hoặc controlled executor thay vì sleep tùy tiện.
5. Nếu local OK nhưng remote fail, chuyển sang connector/transport.
6. Khi reconnect, đọc lại current state vì notification không mặc định được lưu và replay.

Không xem notification metadata là bằng chứng callback đã diễn ra; hai thứ cần được kiểm thử riêng.

## 17. Logging theo tầng

Khi cần điều tra ở development/test, có thể bật logging phù hợp:

\`\`\`properties
logging.level.org.springframework.beans=DEBUG
logging.level.org.springframework.jmx=DEBUG
logging.level.org.springframework.aop=DEBUG
\`\`\`

Đây là property style của Spring Boot; với Spring Framework thuần, cấu hình logging framework tương ứng theo dự án. Không bật toàn bộ DEBUG lâu dài trong production nếu log quá nhiều hoặc có nguy cơ chứa dữ liệu nhạy cảm.

Các thông tin hữu ích:
- Spring context nào đang refresh?
- Bean nào không tạo được?
- Exporter nào đăng ký ObjectName?
- MBeanServer nào được chọn?
- Exception cause chain là gì?
- Connector server đang phục vụ registry nào?
- Client kết nối bằng Service URL nào?
- Thời điểm shutdown hoặc redeploy?

Không ghi password, access token, keystore secret hay raw payload nhạy cảm vào log.

## 18. Đối chiếu exception và hướng xử lý

| Exception hoặc trạng thái | Tầng gốc thường gặp | Cách xử lý |
|---|---|---|
| \`NoSuchBeanDefinitionException\` | Spring bean lookup | Kiểm tra scan/condition/definition |
| \`UnsatisfiedDependencyException\` | Spring injection | Kiểm tra dependency, qualifiers |
| \`BeanCreationException\` | Wrapper khi khởi tạo | Xem cause sâu nhất |
| \`MBeanExportException\` | Spring JMX exporter | Xem nested JMException |
| \`NotCompliantMBeanException\` | JMX contract | Sửa MBean interface/metadata/proxy |
| \`InstanceAlreadyExistsException\` | Registry | Phân định ObjectName/owner |
| \`MalformedObjectNameException\` | Naming | Sửa domain/key property syntax |
| \`InstanceNotFoundException\` | Registry/runtime | Xác minh đúng ObjectName/server/lifecycle |
| \`AttributeNotFoundException\` | MBean contract | Đọc MBeanInfo |
| \`ReflectionException\` | Operation dispatch | Kiểm tra name/signature |
| \`MBeanException\` | Implementation checked exception | Đọc target exception |
| \`RuntimeMBeanException\` | Implementation runtime exception | Đọc target exception |
| \`IOException\` | Remote transport hoặc I/O khác | Xác định tầng và trạng thái lời gọi |
| \`SecurityException\` | Auth/authorization | Kiểm tra quyền và connector |
| \`SSLHandshakeException\` | TLS handshake | Kiểm tra cert/trust/protocol/hostname |

Một class exception không đủ để chứng minh toàn bộ nguyên nhân. Thời điểm, call path, cause chain và server đích mới quyết định hướng sửa.

## 19. Runbook xử lý sự cố

### Bước 1 — Khoanh phạm vi

- Xác nhận JVM, node/instance, ApplicationContext và môi trường.
- Xác nhận triệu chứng xuất hiện khi startup, thao tác local hay remote.
- Thu thập exception cause chain và thời điểm.
- Không đổi security settings hoặc retry destructive operations trong lúc chưa rõ nguyên nhân.

### Bước 2 — Xác minh Spring context

- Context có refresh thành công không?
- Bean quản trị có tồn tại không?
- Bean có bị proxy không, proxy expose interface nào?
- Exporter có được tạo không và export mode là gì?

### Bước 3 — Xác minh JMX registration

- MBeanServer nào được exporter sử dụng?
- ObjectName được tạo là gì?
- \`isRegistered(name)\` có đúng không?
- Có duplicate registration hoặc stale entry?
- MBeanInfo có đúng attributes, operations và notifications?

### Bước 4 — Xác minh runtime behavior

- Local \`getAttribute\` hoặc \`invoke\` có thành công?
- Getter có I/O/lock nặng?
- Operation có ném exception hoặc trạng thái từ chối?
- Listener/filter có đúng và callback đã hoàn tất?

### Bước 5 — Xác minh connector

- Remote Service URL, registry host và RMI endpoint?
- Auth/TLS/truststore/hostname có hợp lệ?
- Firewall/DNS/NAT có cho phép đủ cổng?
- Connector trỏ đúng MBeanServer?
- Remote client đang gọi đúng ObjectName và signature?

### Bước 6 — Xác nhận sau sửa

- Spring context startup thành công.
- MBean tồn tại trên đúng server.
- MBeanInfo phản ánh contract dự kiến.
- Attribute read-only hoạt động với latency hợp lý.
- Operation điều khiển được thử trong môi trường an toàn.
- Context shutdown không để lại MBean stale hay gỡ nhầm registration.

## 20. Integration test phân tầng

Một fixture hữu ích có thể khởi tạo Spring context với MBeanServer test riêng rồi kiểm tra:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class JmxLayeringTest {

    @Test
    void beanAndMBeanAreBothPresent() throws Exception {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(
                     MonitoringTestConfiguration.class)) {

            assertTrue(context.containsBean("workerMonitor"));

            MBeanServer server = context.getBean(MBeanServer.class);
            ObjectName name = new ObjectName(
                "com.example.test:type=Worker,name=Import");

            assertTrue(server.isRegistered(name));
            assertNotNull(server.getMBeanInfo(name));
        }
    }
}
\`\`\`

\`MonitoringTestConfiguration\` trong ví dụ là fixture cần được dự án định nghĩa để cung cấp bean, exporter và MBeanServer đúng. Test trên không có remote connector; nó chứng minh tầng Spring và registration local. Muốn kiểm tra remote, viết integration test riêng start connector test có authentication/TLS phù hợp.

### 20.1 Negative contract test

Ngoài assert MBean cần thiết có mặt, nên xác nhận MBean không nên xuất cũng vắng mặt:

\`\`\`java
ObjectName forbidden = new ObjectName(
    "com.example.test:type=InternalService,name=Payment");

assertFalse(server.isRegistered(forbidden));
\`\`\`

Điều này giúp phát hiện exporter autodetection bị mở rộng nhầm, đặc biệt sau khi thêm một starter hoặc configuration module mới.

### 20.2 Lifecycle test

Tạo context, assert registration; đóng context; assert registration được gỡ do exporter sở hữu. Nếu dùng platform server chung với test khác, không dùng domain wildcard để unregister hàng loạt. Một context không được xóa MBean mà nó không đăng ký.

## 21. Những nhầm lẫn thường gặp

**“BeanCreationException luôn là lỗi Spring DI.”** Không. Nó có thể bọc lỗi JMX registration xảy ra trong context refresh.

**“Bean tồn tại thì JMX phải thấy.”** Không. Cần exporter, selection, metadata, naming và registration.

**“MBean thấy trên JConsole thì Spring context chắc chắn khỏe.”** Không. MBean có thể là registration cũ hoặc chỉ phản ánh một phần ứng dụng.

**“Local JMX OK thì remote JMX chắc chắn OK.”** Không. Remote còn connector, TLS, auth, network, serialization.

**“JConsole không thấy bean tức là lỗi annotation.”** Không. Có thể sai MBeanServer hoặc ObjectName.

**“AttributeNotFoundException nghĩa là Java getter không có.”** Không. Getter có thể tồn tại nhưng không thuộc JMX management contract.

**“Timeout nghĩa là operation chưa chạy.”** Không. Side effect có thể đã xảy ra.

**“Đổi registration policy sang replace là sửa lỗi.”** Có thể che xung đột owner và gây lỗi lifecycle.

**“MBeanInfo có notification type là đã phát event.”** Không. Metadata không chứng minh delivery.

## 22. Bài tập vận dụng

**Bài 1 — Wrapped exception.** Context startup fail với \`BeanCreationException -> MBeanExportException -> InstanceAlreadyExistsException\`. Xác định tầng gốc và sửa ownership/ObjectName như thế nào?

**Bài 2 — Bean có nhưng MBean không.** \`containsBean=true\`, \`isRegistered=false\`. Liệt kê các bước kiểm tra exporter, autodetection, proxy, metadata và naming.

**Bài 3 — Remote mất MBean.** Local \`customServer.isRegistered(name)=true\`, JConsole không thấy. Chứng minh connector trỏ server khác và đề xuất cách sửa.

**Bài 4 — Attribute lỗi.** \`MBeanInfo\` có attribute \`PendingJobs\` nhưng \`getAttribute\` timeout. Giải thích vì sao đây không đơn thuần là lỗi Spring context và cách đo getter/dependency.

**Bài 5 — Operation signature.** Method nhận primitive \`int\` nhưng client dùng signature \`java.lang.Integer\`. Hãy sửa và kiểm tra metadata.

**Bài 6 — Notification.** Listener không nhận event; hãy phân biệt emitter không phát, filter loại, listener chưa đăng ký và remote disconnect.

**Bài 7 — AOP.** Sau khi bật \`@Transactional\`, MBean mất nhưng bean Spring vẫn có. Đề xuất kiểm tra proxy interface và management adapter.

## Tổng kết

Phân biệt lỗi Spring context với lỗi JMX runtime là phân biệt **thời điểm và tầng phát sinh sự cố**. Spring context tạo bean và áp dụng proxy; exporter chọn bean, tạo metadata và đăng ký; MBeanServer thực thi management contract; connector phục vụ client từ xa. Một exception Spring ở bề mặt có thể bọc lỗi JMX sâu bên trong, nên luôn đọc root cause. Quy trình chẩn đoán hiệu quả là kiểm tra lần lượt **context → exporter → MBeanServer → local runtime → remote connector**, dùng \`MBeanInfo\` và kiểm tra ObjectName để tránh suy đoán. Khi đã xác định đúng tầng, việc sửa sẽ nhỏ, an toàn và không cần các biện pháp rủi ro như tắt bảo mật hay thay thế MBean của thành phần khác.
