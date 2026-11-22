# Không tạo exporter trùng trong cùng ApplicationContext — Spring Framework JMX

## Mục tiêu

Spring Framework JMX dùng MBeanExporter và AnnotationMBeanExporter để đăng ký các bean quản trị vào MBeanServer. Khi một ApplicationContext có đồng thời @EnableMBeanExport, XML context:mbean-export, @Bean MBeanExporter, hoặc Spring Boot JMX auto-configuration, có thể có nhiều exporter cố đăng ký cùng ObjectName vào cùng MBeanServer. Kết quả có thể là InstanceAlreadyExistsException, lỗi startup, thay thế registration không chủ đích và lỗi cleanup khi context đóng.

Bài học giúp phân biệt exporter với MBeanServer, xác định đường cấu hình tạo exporter, thiết kế một owner cho mỗi registration, giới hạn autodetection, xác minh ObjectName và xử lý startup/shutdown an toàn.

## 1. Phân biệt các thành phần

| Thành phần | Trách nhiệm |
|---|---|
| Spring bean | Đối tượng ứng dụng có thể được công bố |
| MBeanExporter | Đăng ký và quản lý vòng đời MBean |
| AnnotationMBeanExporter | Đọc metadata @ManagedResource và các annotation liên quan |
| MBeanServer | Registry JMX, chứa các ObjectName và MBean |
| ObjectName | Khóa duy nhất trong một MBeanServer |
| JMXConnectorServer | Mở kết nối tới MBeanServer cho client từ xa |

Cùng ObjectName trên hai MBeanServer khác nhau không xung đột ở registry; cùng ObjectName trên một MBeanServer thì không thể tồn tại thành hai registration độc lập tại cùng thời điểm. Hai exporter khác tên Spring bean vẫn có thể cùng đăng ký cùng ObjectName.

~~~text
ApplicationContext
  ├── CatalogCacheMonitor
  ├── Exporter A ── register com.example:type=Cache,name=Catalog ──┐
  └── Exporter B ── register com.example:type=Cache,name=Catalog ──┤ MBeanServer
                                                               └─ collision
~~~

## 2. Những nguồn tạo exporter trùng

Một ứng dụng có thể bật annotation export bằng @EnableMBeanExport, dùng namespace XML context:mbean-export, tạo AnnotationMBeanExporter hoặc MBeanExporter thủ công, hoặc dựa vào auto-configuration của Spring Boot. Các starter nội bộ và cấu hình test cũng có thể tạo thêm exporter. Mỗi cơ chế không nhất thiết tạo duplicate trong mọi phiên bản: Spring có điều kiện tạo bean và hạ tầng bảo vệ tên bean. Phải kiểm tra ApplicationContext thực tế thay vì suy đoán chỉ từ code.

Nguy cơ còn xuất hiện giữa parent/child context và các module dùng chung platform MBeanServer. Một context có thể shutdown trong khi context khác vẫn chạy; nếu exporter thay thế registration của nhau, cleanup sẽ khó an toàn.

## 3. Nguyên tắc một registration, một owner

Với mỗi MBean cần biết: ObjectName đầy đủ; MBeanServer đích; exporter hoặc code đã register; ApplicationContext sở hữu exporter; thời điểm unregister; client đang dùng tên nào. Nếu hai exporter có trách nhiệm chồng lấn, hãy sửa phạm vi đăng ký chứ không mặc định cho phép replace.

Ví dụ sở hữu rõ:

~~~text
Exporter Web:   com.example.web:type=Health,name=Api
Exporter Batch: com.example.batch:type=Worker,name=Import
Exporter Core:  com.example.shared:type=Cache,name=Catalog
~~~

Cả ba có thể dùng chung platform MBeanServer khi các ObjectName khác nhau và mỗi exporter chỉ quản lý registration của mình. Không unregister tất cả theo domain khi một context đóng vì domain không chứng minh ownership.

## 4. Chọn một chiến lược export chính

### 4.1 Annotation-driven

~~~java
@Configuration
@EnableMBeanExport(defaultDomain = "com.example.ops")
class JmxConfiguration { }

@Component
@ManagedResource(objectName = "com.example.ops:type=Worker,name=Import")
class ImportWorkerMonitor {
    @ManagedAttribute
    public long getCompletedCount() { return 0L; }
}
~~~

Với cách này, không tạo thêm một AnnotationMBeanExporter thủ công cùng quét tập @ManagedResource. Nếu chạy Spring Boot và JMX auto-configuration đã đáp ứng nhu cầu, xác định điều kiện tạo exporter trước khi thêm @EnableMBeanExport.

### 4.2 Explicit MBeanExporter

~~~java
@Configuration
class ExplicitJmxConfiguration {
    @Bean
    MBeanExporter exporter(WorkerStatus worker, CacheStatus cache) {
        MBeanExporter result = new MBeanExporter();
        result.setServer(ManagementFactory.getPlatformMBeanServer());
        result.setBeans(Map.of(
            "com.example.ops:type=Worker,name=Import", worker,
            "com.example.ops:type=Cache,name=Catalog", cache));
        result.setAutodetect(false);
        return result;
    }
}
~~~

Ở đây WorkerStatus và CacheStatus phải là MBean hợp lệ hoặc có assembler thích hợp. Tắt autodetection giúp tập đăng ký ổn định, không mở rộng chỉ vì một developer thêm Spring bean. Với quản trị production cần API ổn định, explicit mapping dễ kiểm toán.

### 4.3 Spring Boot auto-configuration

Property spring.jmx.enabled=true được dùng trong nhiều phiên bản Spring Boot để bật hạ tầng JMX theo điều kiện. Không được suy ra chắc chắn một bean exporter nào được tạo nếu chưa xem phiên bản Boot và condition report. Nếu một starter cung cấp exporter thủ công, điều kiện auto-configuration có thể back off, hoặc hệ thống vẫn có hai đường export ở phạm vi khác nhau. Hãy chọn owner chính và kiểm chứng thực tế.

## 5. Phân biệt trùng exporter với trùng ObjectName

Trùng exporter nghĩa là có nhiều exporter cùng hoặc có thể chồng trách nhiệm. Trùng ObjectName nghĩa là có ít nhất hai yêu cầu đăng ký tên giống nhau vào cùng server. Có thể có một exporter nhưng hai bean cùng ObjectName, vẫn lỗi. Có thể có hai exporter nhưng tập ObjectName rời nhau, không lỗi. Số exporter tự nó không phải kết luận đủ.

### Ví dụ trùng ObjectName do metadata

~~~java
@Component
@ManagedResource(objectName = "com.example.ops:type=Status,name=Main")
class BillingStatus { }

@Component
@ManagedResource(objectName = "com.example.ops:type=Status,name=Main")
class InventoryStatus { }
~~~

Ngay cả với một AnnotationMBeanExporter, hai bean vẫn yêu cầu cùng tên. Đổi defaultDomain của exporter không đổi ObjectName đã được chỉ định đầy đủ. Giải pháp là chọn tên tường minh khác nhau hoặc chỉ giữ một owner được phép công bố.

## 6. Vì sao registration policy không phải giải pháp mặc định?

Exporter có thể được cấu hình xử lý tên đã tồn tại bằng cách thất bại, bỏ qua hoặc thay thế tùy API/phiên bản. Khi dùng IGNORE_EXISTING, một bean mong đợi có thể không được đăng ký. Với REPLACE_EXISTING, exporter B có thể thay MBean của A, khiến vòng đời A/B xung đột. Policy xử lý kết quả collision, không chữa nguyên nhân: hai đường cấu hình hoặc hai bean đang yêu cầu một ObjectName.

Nếu hệ thống đang gặp InstanceAlreadyExistsException, tìm ObjectName, MBeanServer và đường register gây lỗi trước khi sửa. Không xóa toàn bộ domain và không tùy tiện thay registry của module khác.

## 7. XML và JavaConfig chồng lấn

Cấu hình XML sau:

~~~xml
<context:mbean-export />
~~~

có thể tồn tại cùng JavaConfig:

~~~java
@Configuration
@EnableMBeanExport
class AnotherJmxConfig { }
~~~

Điều cần xem là bean definition thực tế được tạo từ hai đường, có cùng đăng ký @ManagedResource không và có lỗi tên Spring bean hay ObjectName JMX không. BeanDefinitionOverrideException thuộc Spring container, khác InstanceAlreadyExistsException thuộc MBeanServer. Khi chuyển đổi XML sang JavaConfig, chọn một nguồn cấu hình exporter chủ đạo và loại bỏ đường thừa bằng thay đổi source có kiểm soát.

## 8. Module và starter: nên cung cấp management bean, không âm thầm export toàn context

Thiết kế nhiều module thường tốt hơn khi application bootstrap sở hữu exporter và MBeanServer. Các module inventory, billing, worker cung cấp management adapter hoặc annotation metadata; application xác định tập cần export. Nếu mỗi starter tạo exporter tự động, tập được quét dễ chồng lấn, nhất là khi dùng autodetection trong cùng context.

Với module cần exporter riêng, phải ghi rõ điều kiện enable, danh sách explicit MBean, ObjectName namespace, lifecycle và test không chồng lấn. Sự hiện diện của nhiều exporter phải là quyết định kiến trúc, không phải hệ quả ngẫu nhiên của import configuration.

## 9. MBeanServer và defaultDomain

### Server

~~~java
@Bean
MBeanServer managementServer() {
    return ManagementFactory.getPlatformMBeanServer();
}
~~~

Với exporter trực tiếp, truyền object bằng exporter.setServer(managementServer). Với @EnableMBeanExport, thuộc tính server là tên bean kiểu MBeanServer, ví dụ server = "managementServer". Nó không phải host, port hay Service URL.

### Domain

defaultDomain phục vụ naming strategy khi sinh ObjectName theo cấu hình. Nếu bean đã có @ManagedResource(objectName = "com.example.ops:type=Cache,name=Catalog"), đổi defaultDomain không tự ghi đè tên này. Cùng defaultDomain cũng không có nghĩa cùng server; server và namespace là hai lựa chọn độc lập.

## 10. Kiểm kê exporter đang hoạt động

~~~java
String[] exporters = context.getBeanNamesForType(
    MBeanExporter.class, true, false);
System.out.println(Arrays.toString(exporters));
~~~

Phép tra cứu áp dụng cho context được hỏi; parent/child hierarchy phải được kiểm tra có chủ đích. allowEagerInit=false giúp tránh một số khởi tạo không cần thiết khi chỉ muốn kiểm kê type. Đọc configuration class của từng exporter, server đích, autodetect flag, explicit bean mappings, assembler và naming strategy.

Không dựa duy nhất vào số lượng exporter: hai exporter độc lập có thể là thiết kế đúng; một exporter cũng có thể đăng ký nhiều bean trùng ObjectName do tên sinh sai.

## 11. Kiểm tra registry thực tế

~~~java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
Set<ObjectName> names = server.queryNames(
    new ObjectName("com.example.ops:*"), null);
names.forEach(n -> System.out.println(n.getCanonicalName()));
~~~

Chỉ suy luận về server đang được truy vấn. Nếu exporter dùng custom MBeanServer khác connector hoặc platform server, một MBean đăng ký thành công có thể không xuất hiện ở đây. MBeanServer.queryNames không tự cho biết exporter owner; phải kết hợp log và bean definitions.

Để xem member được công bố:

~~~java
MBeanInfo info = server.getMBeanInfo(
    new ObjectName("com.example.ops:type=Worker,name=Import"));
for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println(operation.getName());
}
~~~

Kiểm tra operation có tác dụng phụ, readable/writable attributes và dữ liệu nhạy cảm. Trùng exporter không chỉ có rủi ro collision mà còn có thể vô tình mở rộng bề mặt quản trị.

## 12. Startup log và các lỗi điển hình

| Dấu hiệu | Giải thích có thể |
|---|---|
| InstanceAlreadyExistsException | ObjectName đã tồn tại trong server |
| NotCompliantMBeanException | Bean không đúng hợp đồng MBean/assembler |
| BeanDefinitionOverrideException | Spring bean definition trùng hoặc overriding bị chặn |
| MBean có rồi biến mất | Exporter khác thay/gỡ registration, lifecycle chưa rõ |
| MBean không thấy trong JConsole | Connector trỏ server khác hoặc ObjectName sai |
| Sau reload có duplicate | Context cũ chưa unregister hoặc context mới export lặp |

Quy trình chẩn đoán nên đi từ ObjectName trong exception tới exporter đang register, server đích, bean ứng viên, đường cấu hình và lịch sử lifecycle. Không sửa bằng cách mở toàn bộ JMX endpoint ra Internet hay tắt authentication.

## 13. Kiểm thử configuration

~~~java
@Test
void onlyOneExporterOwnsExpectedMBean() throws Exception {
    MBeanServer server = ManagementFactory.getPlatformMBeanServer();
    ObjectName expected = new ObjectName(
        "com.example.ops:type=Worker,name=Import");

    try (AnnotationConfigApplicationContext context =
             new AnnotationConfigApplicationContext(
                 JmxConfiguration.class, ImportWorkerMonitor.class)) {
        String[] exporters =
            context.getBeanNamesForType(MBeanExporter.class);
        assertEquals(1, exporters.length);
        assertTrue(server.isRegistered(expected));
    }

    assertFalse(server.isRegistered(expected));
}
~~~

Fixture cần tránh trùng ObjectName với test khác. Nếu test chạy song song, sử dụng server riêng hoặc namespace test không đụng nhau. Không unregister một MBean không được test sở hữu. Assert có đúng một exporter chỉ phù hợp khi kiến trúc của fixture thực sự chủ định một exporter; không áp dụng nó như một quy luật phổ quát.

Negative contract test cũng hữu ích: assert không có InternalService MBean, không có operation nguy hiểm ngoài kế hoạch và context đóng không gỡ MBean của parent/child khác.

## 14. Parent/child context

Parent, Web child và Batch child có thể cùng chia sẻ MBeanServer. Nếu từng context sở hữu exporter riêng, namespace và tập MBean phải tách biệt. Đóng Web context không được unregister MBean thuộc Batch hoặc Parent. Không dùng wildcard domain làm bằng chứng ownership; chỉ gỡ các registration mà exporter của context ấy đã tạo thành công.

Nếu hai context cùng dùng một ObjectName tường minh, phải sửa tên hoặc điều phối handoff khi redeploy. REPLACE_EXISTING có thể che collision mà làm shutdown không an toàn.

## 15. Runbook trước và sau thay đổi JMX

Trước khi triển khai: kiểm kê exporter, xác định auto-configuration và XML/Java config, liệt kê MBean cần xuất, quyết định owner, đặt ObjectName ổn định, thiết lập server/connector phù hợp, thêm test startup và shutdown.

Khi gặp lỗi: lấy ObjectName và MBeanServer đích, lần theo exporter đang register, tìm bean/cấu hình trùng, không bật replacement mù, thu hẹp phạm vi hoặc bỏ một đường export, chạy lại test.

Khi nâng cấp Spring hoặc Boot: đọc thay đổi auto-configuration, xác minh condition report, bean definitions, tập ObjectName và cleanup sau context refresh. Không giả định hành vi bean overriding hoặc JMX default giữ nguyên qua mọi phiên bản.

## 16. Bài tập vận dụng

1. Ứng dụng có @EnableMBeanExport và @Bean AnnotationMBeanExporter. Nêu nguy cơ và cách chọn một đường export.
2. Spring Boot đã bật JMX, một starter thêm exporter thủ công. Bạn sẽ kiểm tra bean conditions và ObjectName thế nào?
3. Hai exporter quản lý hai domain khác nhau cùng platform MBeanServer. Khi nào chúng hợp lệ?
4. Vì sao REPLACE_EXISTING không phải cách chữa collision trong context có vòng đời độc lập?
5. Thiết kế integration test xác minh MBean expected có mặt, forbidden MBean vắng mặt và registration được gỡ sau context.close().
6. Parent/child context dùng chung server: hãy mô tả cách phân định owner để đóng child không xóa MBean của parent.

## Tổng kết

Để không tạo exporter trùng trong cùng ApplicationContext, hãy kiểm soát các đường cấu hình annotation, XML, manual exporter và Spring Boot auto-configuration. Một cơ chế export chính thường dễ bảo trì nhất cho cùng nhóm bean; nhiều exporter chỉ nên tồn tại khi tập MBean không chồng lấn và lifecycle có owner rõ. Đừng dùng registration policy hay đổi defaultDomain để che lỗi. Kiểm chứng bằng exporter bean inspection, MBeanServer registry, MBeanInfo và integration test startup/shutdown.
