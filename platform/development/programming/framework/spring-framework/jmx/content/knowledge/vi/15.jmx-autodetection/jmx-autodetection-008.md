# Giới hạn phạm vi autodetection trong context lớn — Spring Framework JMX

## Mục tiêu

Trong Spring Framework JMX, **autodetection** là cơ chế để \`MBeanExporter\` tự tìm những bean đủ điều kiện rồi đăng ký chúng thành MBean. Cơ chế này thuận tiện cho ứng dụng nhỏ: không cần liệt kê thủ công từng bean trong cấu hình export. Tuy nhiên, một \`ApplicationContext\` lớn có thể chứa hàng trăm hoặc hàng nghìn bean, nhiều module, proxy AOP, Spring infrastructure, bean khởi tạo lười, context cha/con và các thư viện tích hợp. Khi bật autodetection quá rộng, rủi ro không chỉ là chậm startup: có thể xuất nhầm bean, xung đột ObjectName, tăng bề mặt quản trị, làm thay đổi vòng đời bean và khó xác định exporter nào sở hữu registration.

Bài học này giải thích cách xác định và thu hẹp tập bean được phát hiện để JMX chỉ công bố những thành phần quản trị đã được lựa chọn có chủ đích.

Sau bài này, bạn có thể:

- Phân biệt \`MBeanExporter\` tự phát hiện bean, export bằng danh sách explicit và \`AnnotationMBeanExporter\` dùng metadata annotation.
- Hiểu vai trò của \`autodetect\`, \`autodetectMode\` và các chế độ \`AUTODETECT_NONE\`, \`AUTODETECT_MBEAN\`, \`AUTODETECT_ASSEMBLER\`, \`AUTODETECT_ALL\` trong những phiên bản Spring API có hỗ trợ.
- Nhận diện ảnh hưởng của BeanFactory, bean names, proxy, parent/child context và lazy initialization.
- Lựa chọn giữa đăng ký tường minh, management adapter, metadata naming strategy, assembler có giới hạn và chia phạm vi context.
- Quản lý \`ObjectName\`, registration policy, lifecycle và quyền truy cập JMX.
- Kiểm chứng chính xác những MBean thực sự được xuất bằng \`MBeanServer.queryNames\` và \`MBeanInfo\`.
- Xây dựng một chiến lược export có thể dự đoán cho ứng dụng Spring lớn.

## 1. Autodetection là gì và tại sao phải đặt giới hạn?

Một exporter thông thường có thể hoạt động theo hai hướng:

\`\`\`text
Cách A: Khai báo tường minh
  MBeanExporter
    ├── workerStatus  → com.example:type=Worker,name=Import
    └── cacheStatus   → com.example:type=Cache,name=Catalog

Cách B: Tự phát hiện
  ApplicationContext / BeanFactory
    ├── workerService
    ├── cacheService
    ├── paymentService
    ├── dataSource
    ├── taskExecutor
    ├── metricsRegistry
    ├── workerStatus
    └── ...
          |
          v
    MBeanExporter autodetection
          |
          v
    Chọn bean theo tiêu chí exporter / assembler / metadata
          |
          v
    MBeanServer
\`\`\`

**Autodetection không nhất thiết đồng nghĩa export mọi Spring bean.** Nó có nghĩa exporter tự đánh giá một tập ứng viên từ BeanFactory theo các tiêu chí đã cấu hình. Tập nào được công bố phụ thuộc loại exporter, kiểu MBean, \`MBeanInfoAssembler\`, naming strategy và chế độ autodetect.

Với context lớn, vấn đề chính là hai tập:

- **Tập bean tồn tại trong Spring context**: phục vụ đầy đủ nhu cầu ứng dụng.
- **Tập bean phải được quản lý qua JMX**: chỉ là một phần nhỏ, được chọn vì nhu cầu vận hành.

Mục tiêu là bảo đảm tập thứ hai không tự phình to theo mọi thay đổi của tập thứ nhất.

## 2. Bốn dạng phạm vi cần phân biệt

### 2.1 Phạm vi BeanFactory/ApplicationContext

Exporter được tạo trong một Spring context và có thể tìm bean trong BeanFactory tương ứng theo cơ chế của nó. Trong hệ thống có parent/child context, không nên mặc định rằng exporter chỉ nhìn những bean bạn trực tiếp viết tại một package.

Một context lớn có thể gom nhiều configuration class và import module. Khi nhiều exporter được tạo tại các context có liên quan, một bean có thể bị xem xét để export nhiều lần nếu phạm vi và naming không được tổ chức rõ.

### 2.2 Phạm vi ứng viên MBean

Không phải bean nào cũng là Standard MBean, MXBean hoặc có metadata annotation. Chế độ autodetect quyết định tập ứng viên được xem xét là loại nào. Đây là lớp giới hạn đầu tiên: chỉ những bean phù hợp contract quản trị mới nên nằm trong tập ứng viên.

### 2.3 Phạm vi tên JMX

Mỗi ứng viên được xuất cần có \`ObjectName\` duy nhất trong **MBeanServer đích**. \`ObjectName\` gồm domain và key properties:

\`\`\`text
com.example.operations:type=Worker,name=Import,instance=node01
\`\`\`

Hai bean khác nhau có thể bị gán cùng tên nếu naming strategy không phân biệt instance. Đổi \`defaultDomain\` không tự làm bean names trở nên duy nhất nếu key properties vẫn trùng.

### 2.4 Phạm vi quyền điều khiển

Một bean có method thay đổi trạng thái, nếu bị export, có thể tạo thêm operation điều khiển qua JMX. Ngay cả khi phạm vi autodetection đã thu hẹp, vẫn cần quyết định attribute/operation nào được phép công bố và role nào có quyền gọi. Giới hạn phát hiện bean là bước giảm bề mặt, **không phải** toàn bộ cơ chế bảo mật.

## 3. Cơ chế MBeanExporter và chế độ autodetection

Spring \`org.springframework.jmx.export.MBeanExporter\` là thành phần đăng ký bean vào một \`MBeanServer\`. Bên cạnh ánh xạ \`beans\` tường minh, Spring JMX cung cấp lựa chọn tự phát hiện phù hợp với từng thế hệ API.

Các hằng số chế độ được biết đến trong \`MBeanExporter\`:

| Chế độ | Ý tưởng |
|---|---|
| \`AUTODETECT_NONE\` | Không tự quét tìm bean để export |
| \`AUTODETECT_MBEAN\` | Tập trung các bean đã đáp ứng hình thức MBean tiêu chuẩn, như Standard MBean/MXBean phù hợp |
| \`AUTODETECT_ASSEMBLER\` | Dùng \`MBeanInfoAssembler\` để xác định những bean có thể được xuất |
| \`AUTODETECT_ALL\` | Kết hợp các con đường tự phát hiện tương ứng |

Cách kích hoạt cụ thể và các setter/hằng số khả dụng cần phù hợp phiên bản Spring Framework bạn đang chạy. Trong cấu hình dùng \`AnnotationMBeanExporter\`, việc lựa chọn bean được định hướng bởi metadata \`@ManagedResource\` và assembler tương ứng, không đơn thuần do một tên chế độ.

Mô hình quyết định:

\`\`\`text
Bean candidate
    |
    +--> Có là MBean theo quy ước JMX không?
    |       |
    |       +--> Có thể thuộc autodetect MBEAN
    |
    +--> Assembler có hỗ trợ bean này không?
            |
            +--> Có thể thuộc autodetect ASSEMBLER
\`\`\`

**Đừng bật \`AUTODETECT_ALL\` chỉ để “cho chắc”.** Trong một context lớn, điều này có thể làm rộng danh sách MBean ngoài kế hoạch. Hãy bắt đầu từ nhu cầu quản trị cần xuất và chọn mode nhỏ nhất đáp ứng yêu cầu.

## 4. Export tường minh: ranh giới rõ ràng nhất

Khi JMX được coi là API vận hành có chủ đích, cách chắc chắn nhất là khai báo từng bean quản trị:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxExportConfiguration {

    @Bean
    public MBeanExporter mbeanExporter(
            WorkerStatus workerStatus,
            CacheStatus cacheStatus) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(ManagementFactory.getPlatformMBeanServer());

        exporter.setBeans(Map.of(
            "com.example.ops:type=Worker,name=Import", workerStatus,
            "com.example.ops:type=Cache,name=Catalog", cacheStatus
        ));

        exporter.setAutodetect(false);
        return exporter;
    }
}
\`\`\`

Trong đó \`WorkerStatus\` và \`CacheStatus\` là các management adapter hoặc bean tuân theo hợp đồng MBean phù hợp. Ví dụ sử dụng \`setAutodetect(false)\` để thể hiện rằng chỉ danh sách \`setBeans(...)\` mới thuộc phạm vi export. Cần kiểm tra API và cấu hình đã sử dụng trong phiên bản Spring; nếu các bean chỉ là POJO thông thường thì exporter cần \`MBeanInfoAssembler\` phù hợp hoặc interface JMX tương ứng để đăng ký hợp lệ.

Lợi ích:

- Code review nhìn thấy chính xác từng \`ObjectName\`.
- Thêm một Spring bean mới không tự làm tăng số MBean.
- Có thể tách management adapter khỏi service nghiệp vụ.
- Dễ xác định owner của registration khi context đóng.
- Có thể kiểm thử danh sách tên dự kiến thay vì chỉ đếm số lượng.

Nhược điểm: thêm hoặc xóa MBean phải cập nhật cấu hình. Đây thường là chi phí chấp nhận được nếu bề mặt JMX cần ổn định và được vận hành bởi nhiều công cụ.

## 5. Cách dùng annotation có chọn lọc

Trong ứng dụng đã thống nhất dùng annotation-based JMX, một cách hạn chế phạm vi là **chỉ gắn \`@ManagedResource\` cho bean thực sự dùng để quản trị**, thay vì đánh dấu rộng mọi service.

Ví dụ:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.ops:type=Worker,name=Import",
    description = "Read-only import worker monitoring")
public class ImportWorkerMonitor {

    private final ImportWorkerService worker;

    public ImportWorkerMonitor(ImportWorkerService worker) {
        this.worker = worker;
    }

    @ManagedAttribute
    public long getCompletedCount() {
        return worker.completedCount();
    }

    @ManagedAttribute
    public String getEffectiveState() {
        return worker.effectiveState();
    }
}
\`\`\`

\`ImportWorkerService\` là service xử lý nghiệp vụ, không nhất thiết có metadata JMX. Adapter \`ImportWorkerMonitor\` là đối tượng nhỏ chuyên đọc trạng thái và chỉ export những attribute cần thiết.

Kích hoạt export:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport(
    server = "jmxServer",
    defaultDomain = "com.example.ops"
)
public class JmxAnnotationsConfiguration {
}
\`\`\`

Với cấu hình này, cần có Spring bean tên \`jmxServer\` kiểu \`MBeanServer\` và đảm bảo không tồn tại exporter khác cùng đăng ký \`ImportWorkerMonitor\` dưới cùng \`ObjectName\`. \`defaultDomain\` hỗ trợ đặt domain cho tên được sinh theo naming strategy; nó không ghi đè một ObjectName đầy đủ đã được khai báo trong \`@ManagedResource\`.

**Lưu ý quan trọng:** annotation-driven export giúp chọn bean theo metadata, nhưng vẫn cần giới hạn số bean được annotate, phạm vi context nơi exporter hoạt động và các cơ chế autoconfiguration khác. Đặt annotation lên hàng trăm service vẫn có thể tạo một bề mặt quản trị lớn.

## 6. Giới hạn dựa trên naming/assembler

Một \`MBeanInfoAssembler\` quyết định metadata attribute và operation cho bean được export. Trong một số cấu hình, khả năng \`includeBean\` của assembler được sử dụng để chọn bean đủ điều kiện autodetection.

Có thể xây dựng chiến lược mà chỉ bean thuộc một nhóm quản trị được phép đi qua assembler. Ví dụ về ý tưởng:

\`\`\`text
ApplicationContext
  ├── domain.*        → không export
  ├── repositories.*  → không export
  ├── integrations.*  → không export
  └── management.*    → được đánh giá để export
\`\`\`

Tuy nhiên, đừng mặc định **component scan của Spring** và **JMX autodetection** dùng cùng filter package. \`@ComponentScan\` quyết định bean nào được đăng ký vào ApplicationContext, không phải danh sách bean nào exporter cho phép. Nếu loại \`domain.*\` khỏi Spring component scan chỉ để hạn chế JMX, bạn có thể vô tình làm mất bean nghiệp vụ và khiến ứng dụng không chạy.

Thay vào đó, hãy kiểm soát qua:

1. Danh sách export tường minh.
2. Management adapter có annotation rõ ràng.
3. \`MBeanInfoAssembler\` hoặc \`AutodetectCapableMBeanInfoAssembler\` phù hợp, có tiêu chí inclusion cụ thể.
4. Cấu hình exporter theo module hoặc context chuyên dụng.
5. Bài test xác minh \`ObjectName\` và operation được đăng ký thực tế.

### 6.1 Vì sao không nên chọn theo package bằng reflection đơn giản?

Một Spring bean có thể được JDK proxy, CGLIB proxy hoặc factory tạo ra. \`bean.getClass().getPackageName()\` có thể trả về package của proxy, không phản ánh package của target service. Khi chọn bean bằng tên, type metadata hoặc annotation, phải hiểu cách Spring xử lý proxy/target class và factory beans.

Với tổ chức lớn, một tag hoặc interface quản trị riêng thường đáng tin cậy hơn so với logic heuristic phức tạp trên class name. Nếu dùng custom assembler/filter, nên test với bean thường, proxied bean và lazy bean.

## 7. Nhiều ApplicationContext: ranh giới quét và trách nhiệm

Một ứng dụng có thể có:

\`\`\`text
JVM
├── Parent ApplicationContext
│    ├── common metrics
│    └── shared services
├── Web ApplicationContext
│    ├── controllers
│    └── web monitors
└── Batch ApplicationContext
     ├── workers
     └── batch monitors
\`\`\`

Nếu mỗi context có một exporter tự động, một số bean hoặc tên có thể được công bố nhiều lần tùy khả năng nhìn thấy bean và cách cấu hình. Xung đột phổ biến:

\`\`\`text
Parent exporter:
  com.example:type=Worker,name=Import

Batch exporter:
  com.example:type=Worker,name=Import
\`\`\`

Vì cả hai đăng ký vào cùng platform MBeanServer, \`ObjectName\` bị trùng. Chính sách thay thế đăng ký không nên dùng làm giải pháp mặc định vì có thể làm một context unregister registration của context khác lúc shutdown.

Một cấu trúc an toàn hơn:

- MBean của shared infrastructure do parent context sở hữu.
- MBean của web module do web context sở hữu với namespace riêng.
- MBean của batch module do batch context sở hữu với namespace riêng.
- Mỗi registration có đúng một exporter/owner.
- Khi một context dừng, chỉ các MBean do context đó quản lý bị gỡ.

Không cần tạo MBeanServer mới cho từng module chỉ để tách namespace; nhiều domain/key properties có thể cùng tồn tại trên một server. Nhưng khi thật sự cần isolation, một server riêng cũng cần connector/lifecycle được quản lý đúng.

## 8. Lazy initialization và side effect của autodetection

Trong context lớn, nhiều bean được cấu hình lazy để giảm thời gian startup và tài nguyên ban đầu. Một quá trình quét hoặc tạo MBean wrapper có thể làm phát sinh bean sớm hơn dự kiến, tùy cách exporter tra cứu ứng viên và khởi tạo instance.

Ví dụ:

\`\`\`java
@Lazy
@Component
public class ExpensiveDiagnosticService {
    public ExpensiveDiagnosticService() {
        // Khởi tạo kết nối, warm-up cache hoặc cấu trúc lớn.
    }
}
\`\`\`

Nếu exporter autodetect và tạo bean này trong startup, lợi ích lazy initialization có thể bị mất. Ngoài ra, một MBean getter thực hiện I/O ở lần gọi đầu cũng có thể làm phát sinh tài nguyên mà operator không ngờ.

Để tránh:

- Không export service nặng chỉ để có một hoặc hai metric.
- Dùng adapter nhẹ lấy số liệu từ nguồn đã tồn tại.
- Xác định rõ có cần eagerly register MBean hay không.
- Tránh getter JMX tạo đối tượng lớn hoặc trigger network call.
- Quan sát thời gian bootstrap, số bean được khởi tạo và CPU/heap sau khi bật JMX.

Không nên khẳng định rằng mọi chế độ autodetection đều luôn khởi tạo toàn bộ lazy bean; hành vi cụ thể phụ thuộc BeanFactory, exporter, assembler và phiên bản framework. Nhưng trong thiết kế production, đây là một rủi ro cần có phép đo và kiểm thử.

## 9. MBeanExporter, AnnotationMBeanExporter và Boot auto-configuration

Một vấn đề phổ biến là nhiều cơ chế cùng hoạt động:

\`\`\`text
@SpringBootApplication
  |
  +-- Boot JMX auto-configuration (nếu bật)
  |
  +-- @EnableMBeanExport do dự án khai báo
  |
  +-- @Bean MBeanExporter do module khai báo
\`\`\`

Nếu không phân định phạm vi, cùng một bean có thể bị đánh giá để export bởi nhiều exporter. Khi cả hai cùng đăng ký một ObjectName trên cùng server, có thể phát sinh \`InstanceAlreadyExistsException\`, hoặc nếu chính sách cho phép thay thế sẽ gây vấn đề ownership.

Trước khi thêm exporter mới vào context lớn, cần biết:

- Cơ chế export nào đang được bật?
- MBeanServer được mỗi exporter sử dụng là server nào?
- Mỗi exporter quản lý những ObjectName nào?
- Có bean nào bị export trùng không?
- Những MBean của Spring Boot/Actuator hoặc thư viện được quản lý bởi ai?

Spring Boot có các property liên quan đến JMX tùy phiên bản, nhưng không nên copy một property từ ví dụ cũ mà không kiểm tra behavior thực tế. Đặc biệt, \`spring.jmx.enabled\` ảnh hưởng đến khả năng export JMX qua auto-configuration trong các phiên bản Boot hỗ trợ; đó không phải thay thế cho thiết kế namespace/authorization.

## 10. Lựa chọn nào phù hợp với mức độ lớn của context?

| Bối cảnh | Lựa chọn đề xuất | Lý do |
|---|---|---|
| Ứng dụng nhỏ, ít MBean có hợp đồng rõ | Annotation-based autodetection có chọn lọc | Đơn giản, ít khai báo |
| Ứng dụng nhiều module, hàng trăm bean | Explicit \`setBeans\` hoặc tập adapter riêng | Phạm vi dễ kiểm chứng |
| Library cung cấp Standard MBean/MXBean | Autodetect MBEAN có giới hạn hoặc explicit registration | Phù hợp hợp đồng đã định nghĩa |
| Nhiều context chia sẻ platform server | Namespace + exporter ownership riêng | Tránh collision và cleanup nhầm |
| Service có nhiều operation nghiệp vụ nhạy cảm | Adapter read-only / interface nhỏ | Giảm bề mặt điều khiển |
| Có lazy bean nặng | Adapter nhẹ, đo bootstrap và tránh quét quá rộng | Giữ kiểm soát chi phí khởi tạo |
| Có yêu cầu bảo mật chặt | Export whitelist + connector access control | Autodetection không phải security boundary |
| Nhiều client phụ thuộc ObjectName ổn định | Explicit names và contract tests | Tránh tên tự sinh thay đổi không chủ đích |

Một câu hỏi định hướng hữu ích: **“Nếu tuần sau nhóm khác thêm 50 Spring bean, có hợp lý không khi số MBean tăng theo?”** Nếu không, cấu hình autodetection nên được thu hẹp cho đến khi việc thêm bean bình thường không tự làm thay đổi API JMX.

## 11. Đặt ObjectName rõ ràng để tránh rủi ro khi quét rộng

Khi exporter sinh tên, tên thường phụ thuộc vào bean name, naming strategy, default domain và metadata. Với nhiều module, tên ngắn dễ trùng:

\`\`\`text
workerMonitor
cacheMonitor
status
health
\`\`\`

Những tên này không đủ phân biệt nếu nhiều context dùng cùng một server. ObjectName theo domain và key properties rõ ràng hơn:

\`\`\`text
com.example.inventory:type=Worker,name=Import,context=batch
com.example.orders:type=Worker,name=Fulfillment,context=web
com.example.shared:type=Cache,name=Catalog,context=parent
\`\`\`

Không bắt buộc mọi hệ thống đều phải có \`context\` key; hãy chọn key có ngữ nghĩa ổn định và phân biệt những instance thật sự cùng tồn tại trong một server. Nếu ứng dụng có nhiều JVM riêng, một ObjectName giống nhau ở hai JVM không xung đột, nhưng monitoring có thể cần host/instance metadata để phân biệt nguồn.

Một số lỗi khi đặt tên:

- Default domain bị hiểu nhầm là domain của mọi bean kể cả bean có ObjectName tường minh.
- Tên có ký tự đặc biệt nhưng không dùng quy tắc \`ObjectName.quote\`/constructor phù hợp.
- Đưa user ID, token, tham số request hoặc dữ liệu cá nhân vào ObjectName.
- Dùng random UUID mỗi startup làm dashboard không theo dõi được MBean ổn định.
- Hai exporter sinh cùng \`type/name\` trong cùng domain và MBeanServer.

## 12. Giảm phạm vi thao tác, không chỉ phạm vi bean

Một exporter có thể chỉ chọn đúng ba bean, nhưng một trong ba bean lại công bố operation \`purgeAllData()\`. Vì vậy, hai chiều kiểm soát cần độc lập:

\`\`\`text
Dimension 1 — Bean selection
   Có cho bean này trở thành MBean không?

Dimension 2 — Member selection
   Nếu có, attribute/operation nào được công bố?
\`\`\`

Standard MBean/MXBean interface giúp giới hạn thành viên theo contract. Spring annotation giúp chỉ định method qua \`@ManagedAttribute\`, \`@ManagedOperation\` khi dùng đúng metadata assembler. Với các bean dùng assembler khác, hãy xem chính sách member inclusion.

Ngay cả sau khi thu hẹp tập MBean, không nên công bố getter tiết lộ secrets hoặc operation thay đổi trạng thái không có quyền, input validation và audit. Tách management adapter read-only hoặc control adapter khi cần, nhưng việc tách MBean không tự đảm bảo phân quyền nếu client vẫn có quyền invoke trên cùng connector.

## 13. Kiểm chứng phạm vi thực tế trên MBeanServer

Cách tốt nhất để biết exporter đã đăng ký gì là truy vấn đúng server:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

Set<ObjectName> names = server.queryNames(
    new ObjectName("com.example.ops:*"),
    null
);

for (ObjectName name : names) {
    System.out.println(name.getCanonicalName());
}
\`\`\`

Kết quả này chỉ phản ánh MBean trong **platform server** được truy vấn tại thời điểm đó. Nếu exporter dùng server riêng, phải truy vấn đúng server riêng. \`queryNames\` là snapshot: có thể khác khi context đang startup hoặc shutdown.

Để kiểm tra member:

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;

for (ObjectName name : names) {
    MBeanInfo info = server.getMBeanInfo(name);
    System.out.println("MBean: " + name.getCanonicalName());
    for (MBeanOperationInfo op : info.getOperations()) {
        System.out.println("  operation: " + op.getName());
    }
}
\`\`\`

Nếu dự kiến chỉ có hai operation nhưng xuất hiện nhiều hơn, đây có thể là dấu hiệu assembler/export path khác với hợp đồng. Tránh chỉ đếm tổng MBean của JVM vì server còn có platform MXBeans của Java và các thư viện khác.

## 14. Integration test để khóa phạm vi export

Trong một application context lớn, test nên kiểm tra tập ObjectName mong muốn theo domain riêng thay vì chỉ assert exporter bean tồn tại.

Ví dụ skeleton:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class JmxScopeIntegrationTest {

    @Test
    void onlyExpectedOperationsMBeansAreVisible() throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                    JmxExportConfiguration.class,
                    WorkerStatus.class,
                    CacheStatus.class)) {

            Set<ObjectName> actual = server.queryNames(
                new ObjectName("com.example.ops:*"), null);

            Set<ObjectName> expected = Set.of(
                new ObjectName(
                    "com.example.ops:type=Worker,name=Import"),
                new ObjectName(
                    "com.example.ops:type=Cache,name=Catalog")
            );

            assertEquals(expected, actual);
        }
    }
}
\`\`\`

Đây là mẫu kiểm thử về ý tưởng: các class \`WorkerStatus\`, \`CacheStatus\` cần được định nghĩa và phải là MBean hợp lệ; context fixture phải tránh đăng ký bean hai lần; namespace \`com.example.ops\` phải không chứa MBean của test khác. Với test song song, nên tạo MBeanServer riêng hoặc cấp namespace độc lập. Test không nên xóa tất cả ObjectName có cùng domain khi cleanup vì có thể gỡ MBean không thuộc quyền sở hữu.

Mở rộng test:
- Assert thiếu những MBean không được phép xuất.
- Assert danh sách operation/attribute theo \`MBeanInfo\`.
- Đóng context và xác nhận những registration của exporter đã được gỡ.
- Assert platform MBeanServer vẫn còn hoạt động; đừng release server dùng chung.
- Nếu có proxy/lazy bean, kiểm tra behavior startup bằng fixture chuyên biệt.

## 15. Theo dõi hiệu năng khi thay đổi autodetection

Một thay đổi cấu hình JMX nên có ít nhất một số quan sát:

| Tín hiệu | Ý nghĩa |
|---|---|
| Số MBean ứng dụng đã đăng ký | Phát hiện bề mặt quản trị tăng bất thường |
| Thời gian startup của context | Xác định chi phí autodetection/registration |
| Số bean lazy bị khởi tạo khi boot | Phát hiện side effect của scanning |
| Exception đăng ký MBean | Phát hiện ObjectName collision và config lỗi |
| CPU/heap allocation lúc export | Nhận diện introspection hoặc wrapper nặng |
| Số exporter active | Phát hiện double-export do auto-configuration |
| Số operation quản trị có side effect | Kiểm soát bề mặt điều khiển |

Những con số này cần được đo theo baseline ứng dụng thực tế, không có một ngưỡng chung như “hơn 100 MBean là quá nhiều”. Một hệ thống nhiều module có thể chủ đích công bố hàng trăm MBean, nhưng điều đó phải xuất phát từ contract rõ ràng chứ không phải từ quét ngẫu nhiên.

## 16. Các lỗi phổ biến

### 16.1 Bật autodetect rồi dựa vào mặc định

**Vấn đề:** exporter có thể phát hiện nhiều bean hơn người viết tưởng, đặc biệt khi thêm các thư viện hoặc module mới.

**Cách xử lý:** xác định mode thực tế, dùng \`AUTODETECT_NONE\`/tắt autodetect khi cần và khai báo danh sách tường minh hoặc annotation có chọn lọc.

### 16.2 Dùng @ComponentScan exclude để “ẩn khỏi JMX”

**Vấn đề:** những bean bị loại khỏi Spring context có thể là dependency nghiệp vụ cần thiết.

**Cách xử lý:** giới hạn exporter hoặc assembler, không làm thay đổi Spring bean registration chỉ để thu hẹp JMX.

### 16.3 Tin rằng @ManagedResource trên một bean không gây overhead

**Vấn đề:** quá nhiều bean quản trị, đặc biệt bean nặng/lazy, có thể tăng chi phí bootstrap và metadata.

**Cách xử lý:** management adapter nhẹ, annotation có chủ đích và đo hiệu năng.

### 16.4 Nhiều exporter cùng phát hiện một bean

**Vấn đề:** collision hoặc shutdown context này vô tình gỡ registration của context khác.

**Cách xử lý:** một owner cho mỗi registration, namespace và exporter scope rõ ràng.

### 16.5 Chỉ kiểm tra ObjectName mà quên operations

**Vấn đề:** MBean đúng tên nhưng có những operation không nên công bố.

**Cách xử lý:** kiểm tra \`MBeanInfo.getOperations()\`, writable attributes và negative contract tests.

### 16.6 Tưởng rằng domain là ranh giới bảo mật

**Vấn đề:** mọi MBean trong cùng server có thể được client có đủ quyền nhìn thấy bất kể domain.

**Cách xử lý:** authentication, authorization, TLS, network isolation và phân tách server/connector khi thực sự cần.

### 16.7 Xóa tất cả MBean trùng domain khi startup lỗi

**Vấn đề:** có thể xóa MBean của context, thư viện hoặc ứng dụng khác.

**Cách xử lý:** chỉ unregister những ObjectName mà exporter/component đã đăng ký thành công và sở hữu.

## 17. Runbook giới hạn phạm vi autodetection

### Trước khi triển khai

1. Liệt kê đúng các capability quản trị cần thiết, không xuất phát từ toàn bộ bean list.
2. Chọn export mode: explicit, annotation-based hoặc autodetect MBean có giới hạn.
3. Quy định domain/ObjectName, owner, MBeanServer và connector mà client sử dụng.
4. Phân loại các operation có tác dụng phụ, loại bỏ những method không nên export.
5. Kiểm tra các context liên quan và auto-configuration đang bật.
6. Có integration test cho ObjectName expected/forbidden và metadata.

### Khi startup

1. Theo dõi lỗi \`NotCompliantMBeanException\`, \`InstanceAlreadyExistsException\` hoặc lỗi naming.
2. Kiểm tra MBean thực tế trên đúng server bằng \`queryNames\`.
3. So sánh tập tên với hợp đồng expected, không chỉ đếm tổng registry.
4. Kiểm tra thời gian startup/lazy bean initialization nếu thay đổi exporter.

### Khi shutdown và redeploy

1. Đóng context/exporter của module.
2. Đảm bảo registration được sở hữu bởi context ấy đã bị gỡ.
3. Giữ nguyên platform MXBeans và MBean của các context khác.
4. Tái khởi động để xác minh không có collision và không có MBean stale.

## 18. Bài tập vận dụng

**Bài 1 — Context lớn.** Một context có 800 bean, nhưng chỉ 6 bean có nhu cầu quản trị. Bạn chọn autodetect rộng hay explicit export? Giải thích chi phí bảo trì và khả năng test hợp đồng ObjectName.

**Bài 2 — Hai exporter.** Spring Boot auto-configuration đã bật JMX, module mới lại khai báo \`@EnableMBeanExport\`. Kết quả có thể là gì? Hãy thiết kế cách xác định exporter nào chịu trách nhiệm, tránh trùng MBean và kiểm tra \`ObjectName\`.

**Bài 3 — Lazy bean.** Một diagnostic service đánh dấu \`@Lazy\` nhưng bắt đầu khởi tạo ở startup sau khi bật autodetection. Hãy đề xuất cách đo và thay thế bằng management adapter nhẹ.

**Bài 4 — Negative contract.** Viết test chứng minh domain \`com.example.ops\` chỉ chứa 2 ObjectName được phép và không có operation \`deleteAllData\`. Nêu vì sao test vắng mặt quan trọng.

**Bài 5 — Parent/child context.** Parent context có shared metrics, child context chứa batch workers. Hãy thiết kế namespace, owner và cleanup sao cho child shutdown không làm biến mất MBean của parent.

**Bài 6 — MBeanInfoAssembler.** Một custom assembler có thể export nhiều public method trên bean. Hãy giải thích vì sao chọn đúng bean chưa đủ để bảo vệ management API và cách kiểm tra metadata để nhận biết rủi ro.

## Tổng kết

Trong Spring Framework JMX, autodetection hữu ích để giảm cấu hình nhưng không nên biến toàn bộ \`ApplicationContext\` lớn thành bề mặt quản trị không kiểm soát. Giới hạn phạm vi bằng **export explicit, annotation có chọn lọc, management adapter, assembler phù hợp và ownership rõ ràng**. Song song, tách vấn đề chọn bean khỏi chọn attribute/operation, xác định ObjectName ổn định, kiểm tra tác động lên lazy bean/proxy và xác minh registry thực tế bằng \`MBeanServer\`. Thiết kế đạt yêu cầu khi việc thêm bean nghiệp vụ mới không vô tình tạo thêm MBean hoặc operation quản trị mới và khi mỗi registration có một owner chịu trách nhiệm suốt vòng đời.
