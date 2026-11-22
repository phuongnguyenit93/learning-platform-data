# Phân biệt bean được phát hiện tự động và bean được khai báo trong map của MBeanExporter

## 1. Mục tiêu

Trong Spring Framework JMX, `MBeanExporter` là thành phần đưa các Spring-managed bean ra `MBeanServer`. Exporter có thể nhận bean theo hai nguồn khác nhau: **danh sách tường minh trong map `beans`** và **các bean được tìm thấy bằng cơ chế autodetection**. Hai nguồn cùng có thể dẫn tới đăng ký MBean nhưng không có cùng ý nghĩa về lựa chọn, tên đăng ký và tính dự đoán của cấu hình.

Đề bài cần giải quyết là: một bean được exporter phát hiện khác một bean được liệt kê trong map ở điểm nào, khi nào nên chọn từng cách và cần tránh nhầm lẫn gì khi hai cách được dùng cùng lúc?

**Kết luận ngắn:** Map `beans` là danh sách export **chủ động, tường minh** do người cấu hình cung cấp; autodetection là quá trình exporter **tìm ứng viên theo quy tắc phát hiện** trong Spring `ApplicationContext`. Việc phát hiện không đồng nghĩa mọi bean sẽ được export, và việc có trong map không đồng nghĩa bean đó được phát hiện qua annotation.

## 2. Vị trí hai cơ chế trong kiến trúc JMX

```text
Spring ApplicationContext
  |
  +-- Explicit registration
  |      MBeanExporter.setBeans(Map<String, Object>)
  |      key -> ObjectName / định danh nguồn
  |      value -> bean instance hoặc bean name
  |
  +-- Autodetection
         MBeanExporter.setAutodetect(true)
         / autodetectMode
         -> tìm bean ứng viên trong context
         -> quy tắc nhận biết MBean / @ManagedResource
  |
  v
MBeanExporter
  |-- ObjectNamingStrategy: xác định ObjectName
  |-- MBeanInfoAssembler: mô tả attributes/operations
  |-- RegistrationPolicy: xử lý ObjectName trùng
  v
MBeanServer
  |-- domain:type=...,name=...
  v
JConsole / VisualVM / JMX client
```

Đừng nhầm **bean discovery** với **MBean registration**: discovery tạo danh sách ứng viên, trong khi registration đưa MBean thực vào `MBeanServer` dưới `ObjectName` cụ thể. Một bean có thể tồn tại trong Spring context nhưng không thuộc danh sách ứng viên; hoặc là ứng viên nhưng không được đăng ký do lỗi tên, xung đột, quyền và cấu hình exporter.

## 3. Cách 1: khai báo tường minh qua map `beans`

`MBeanExporter` có thuộc tính `beans`, thường được cấu hình bằng `setBeans(Map<String, ?>)`. Map mô tả các đối tượng ứng dụng **muốn export**. Key có thể là một ObjectName dùng để đăng ký hoặc là đầu vào cho naming strategy; value có thể là object hoặc tham chiếu theo cách cấu hình exporter hỗ trợ.

Ví dụ Java configuration chỉ định chính xác một bean:

```java
package com.example.config;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class ExplicitJmxConfiguration {
    @Bean
    public CacheManagement cacheManagement(CacheService service) {
        return new CacheManagement(service);
    }

    @Bean
    public MBeanExporter mbeanExporter(
            CacheManagement cacheManagement) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
            "com.example.cache:type=CacheManagement,name=Primary",
            cacheManagement
        ));
        return exporter;
    }
}
```

Ở đây `CacheManagement` là một management adapter của ứng dụng, còn `CacheService` là service nghiệp vụ được inject; ví dụ giả định các class này đã được định nghĩa. Chỉ một bean được truyền vào map. Exporter không cần quét toàn context để xác định ứng viên khác.

**Ưu điểm của map:**

- Danh sách MBean được chọn có chủ đích và dễ đối chiếu với yêu cầu vận hành.
- Có thể export một bean không có `@ManagedResource`, nếu assembler và các điều kiện JMX phù hợp.
- Có thể kiểm soát ObjectName hoặc map key rõ ràng.
- Dễ dùng cho adapter quản trị nhỏ; giảm nguy cơ một bean ngoài dự kiến bị export khi ứng dụng thêm component mới.
- Phù hợp khi cần chỉ export một tập giới hạn trong context có hàng trăm service.

**Điểm cần chú ý:** map không tự định nghĩa cách mọi public method được expose. Điều đó phụ thuộc MBean chuẩn JMX hoặc `MBeanInfoAssembler` được exporter sử dụng. Một bean được chỉ định tường minh vẫn có thể expose quá nhiều operation nếu dùng reflection assembler trên một service lớn.

## 4. Cách 2: tự phát hiện bean bằng autodetection

Autodetection cho phép exporter rà soát các bean trong ApplicationContext và xác định những đối tượng phù hợp để đăng ký MBean theo quy tắc phát hiện. Các quy tắc có thể dựa vào việc bean đã tuân thủ JMX MBean convention hoặc mang metadata quản trị, tùy mode và cấu hình.

Ví dụ một POJO được Spring đánh dấu quản trị:

```java
package com.example.management;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=QueueMonitor,name=Main",
    description = "Trạng thái queue xử lý job"
)
public class QueueMonitor {
    private final QueueService service;

    public QueueMonitor(QueueService service) {
        this.service = service;
    }

    @ManagedAttribute
    public int getDepth() {
        return service.pendingJobCount();
    }
}
```

Cấu hình ngắn gọn cho annotation-based export:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
```

`@EnableMBeanExport` cấu hình hạ tầng cần thiết để tìm và export các bean phù hợp với annotation quản trị. Đây là đường đi thông dụng khi ứng dụng sở hữu source code, dùng nhiều bean có `@ManagedResource` và muốn quản lý metadata ngay trên class/method.

Nếu cấu hình `MBeanExporter` thủ công, có thể bật autodetection trực tiếp:

```java
@Bean
public MBeanExporter detectingExporter() {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setAutodetect(true);
    return exporter;
}
```

**Quan trọng:** autodetection mode, naming strategy và MBeanInfoAssembler cần phù hợp với loại bean được phát hiện. Chỉ bật `setAutodetect(true)` không bảo đảm mọi `@ManagedResource` POJO đều được công bố đúng metadata trong mọi cấu hình thủ công. Với annotation-based export, ưu tiên `@EnableMBeanExport` hoặc cấu hình đầy đủ `AnnotationJmxAttributeSource`, `MetadataMBeanInfoAssembler` và `MetadataNamingStrategy`.

## 5. Phân biệt theo nguồn danh sách và danh tính

| Tiêu chí | Bean trong map `beans` | Bean do autodetection phát hiện |
| --- | --- | --- |
| Nguồn chọn | Người cấu hình đưa vào `setBeans` | Exporter khám phá ứng viên trong ApplicationContext |
| Mức tường minh | Cao: từng entry có thể được review | Dựa vào marker/quy tắc phát hiện trên tập bean |
| Cần `@ManagedResource`? | Không bắt buộc trong mọi cách export | Cần metadata/loại MBean phù hợp với detection mode |
| ObjectName | Có thể từ key map hoặc naming strategy | Thường từ naming strategy, annotation metadata hoặc quy tắc của MBean |
| Thêm Spring bean mới | Không tự làm map rộng hơn | Có thể tạo thêm MBean nếu bean mới khớp tiêu chí |
| Quản lý contract | Vẫn cần assembler/interface/metadata | Vẫn cần assembler/interface/metadata |
| Rủi ro chính | Quên thêm bean mong muốn, sai key, cấu hình thủ công lặp lại | Vô tình phát hiện nhiều MBean, trùng ObjectName, thay đổi khi scan mở rộng |
| Phù hợp với | Endpoint chọn lọc, security-sensitive, cấu hình tập trung | Nhiều component quản trị có annotation nhất quán |

Hai nhóm không tạo hai loại MBean khác nhau về bản chất. Sau khi đăng ký, JMX client chỉ thấy ObjectName và metadata của MBean. Client không biết bean được chọn vì map hay autodetection, trừ khi ứng dụng có metadata riêng thể hiện điều đó.

## 6. Map key, Spring bean name và JMX ObjectName

Cần phân biệt ba loại tên:

1. **Spring bean name**: định danh bean definition trong ApplicationContext, ví dụ `queueMonitor`.
2. **Map key của `MBeanExporter.beans`**: khóa dùng khi khai báo đối tượng export; có thể là chuỗi ObjectName hoặc được xử lý bởi naming strategy.
3. **JMX ObjectName**: định danh MBean đã đăng ký, ví dụ `com.example.jobs:type=QueueMonitor,name=Main`.

Chúng có thể liên quan nhưng không phải cùng một khái niệm. Ví dụ:

```java
Map<String, Object> managementBeans = Map.of(
    "com.example.jobs:type=QueueMonitor,name=Main",
    queueMonitor
);
exporter.setBeans(managementBeans);
```

Ở đây key map đã là biểu diễn ObjectName. Nếu naming strategy dựa vào metadata annotation, nó có thể lấy ObjectName từ `@ManagedResource`. Nếu tên bị sinh khác với mong muốn, client sẽ không tìm thấy tên đã dự đoán. Khi gặp vấn đề, hãy đọc danh sách MBean thực tế bằng `MBeanServer.queryNames` và kiểm tra `ObjectName.getCanonicalName()`.

## 7. Ví dụ cấu hình autodetect và explicit cùng exporter

Về mặt khái niệm, `MBeanExporter` có thể nhận cả map explicit và lựa chọn autodetection. Khi bật cả hai, cần dự đoán trường hợp một bean được chỉ định trong map cũng thuộc nhóm tự phát hiện.

```java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class MixedExportConfiguration {
    @Bean
    public MBeanExporter mbeanExporter(
            CacheManagement cacheManagement) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
            "com.example.cache:type=CacheManagement,name=Primary",
            cacheManagement
        ));
        exporter.setAutodetect(true);
        return exporter;
    }
}
```

Ví dụ trên **chỉ minh họa hai nguồn ứng viên**, chưa phải một cấu hình annotation export hoàn chỉnh. Để export annotated POJO đúng ý cần assembler/naming strategy phù hợp. Không nên mặc định exporter sẽ đăng ký hai bản MBean độc lập cho cùng bean. Tùy quy tắc phát hiện, xử lý entry và danh tính, bean có thể chỉ được xử lý một lần hoặc xảy ra trùng ObjectName với các ứng viên khác.

Để giảm bất ngờ, nên ưu tiên **một nguồn lựa chọn chủ đạo** cho một nhóm MBean. Nếu sử dụng đồng thời, quy hoạch ObjectName và phân chia rõ trách nhiệm; kiểm tra danh sách đăng ký sau startup.

## 8. Chọn assembler cho từng nguồn

Map và autodetection trả lời câu hỏi **export bean nào**. Assembler trả lời câu hỏi **expose gì từ bean đó**.

Ví dụ một bean được đưa vào map nhưng dùng `SimpleReflectiveMBeanInfoAssembler`:

```java
public class MaintenanceService {
    public int getPendingTasks() { return 10; }
    public void refreshIndex() { /* ... */ }
    public void deleteAllData() { /* ... */ }
}
```

Nếu export theo reflection, cả những public methods không dành cho quản trị có thể nằm trong `MBeanInfo`. Việc bean được chọn tường minh không có nghĩa interface quản trị được giới hạn.

Trong annotation-based export, một adapter riêng có thể chỉ chọn:

```java
@ManagedResource(
    objectName = "com.example.jobs:type=Maintenance,name=Main"
)
public class MaintenanceManagement {
    private final MaintenanceService delegate;

    public MaintenanceManagement(MaintenanceService delegate) {
        this.delegate = delegate;
    }

    @ManagedAttribute
    public int getPendingTasks() {
        return delegate.getPendingTasks();
    }

    @ManagedOperation
    public void requestRefreshIndex() {
        delegate.refreshIndex();
    }
}
```

`deleteAllData` không xuất hiện trong adapter và không phải operation được công bố. Điều này giảm bề mặt quản trị khi client có quyền invoke. Tuy nhiên annotation không tự tạo authorization; connector phải được bảo vệ riêng.

## 9. Phân biệt autodetection với component scanning

Đây là ba bước khác nhau:

```text
@ComponentScan
     |
     v
Spring tìm class -> đăng ký bean definitions trong context
     |
     v
MBeanExporter autodetect
     |
     v
Tìm ứng viên JMX trong các bean của context
     |
     v
MBeanExporter register MBean theo ObjectName
```

`@ComponentScan` chỉ là cách đưa các component vào Spring context. Nó không tự làm mọi `@Component` trở thành MBean. Ngược lại, một bean được tạo bằng `@Bean` và có metadata JMX phù hợp cũng có thể là ứng viên autodetection.

Một `@ManagedResource` nằm trên class mà không có bean instance trong context không đương nhiên được Spring exporter tìm thấy. Để được tự phát hiện, đối tượng cần tham gia cơ chế quản lý/đăng ký mà exporter thực sự sử dụng.

Trong ứng dụng có nhiều ApplicationContext hoặc parent-child contexts, phạm vi nhìn thấy của exporter có thể ảnh hưởng tập bean được phát hiện. Đừng giả định exporter trong context con sẽ quản lý mọi bean của các context không liên quan.

## 10. Singleton, prototype và thời điểm phát hiện

JMX đăng ký một MBean dưới một ObjectName tại một thời điểm, còn Spring scope quyết định tạo instance.

- **Singleton:** thường phù hợp với MBean quản trị ổn định, vì một bean instance được dùng chung trong context.
- **Prototype:** mỗi lần lấy bean có thể tạo instance mới; không nên suy diễn autodetection tạo một ObjectName cho tất cả instance prototype được phát sinh sau startup.
- **FactoryBean và scoped proxy:** kiểu bean và instance thực có thể được xác định qua factory/proxy; cần kiểm tra cách exporter nhận diện và đăng ký trong cấu hình thực tế.
- **Bean động:** instance không nằm trong registry Spring tại thời điểm autodetection sẽ không tự động trở thành MBean chỉ vì được tạo trong code nghiệp vụ sau đó.

Nếu cần quản trị một nhóm prototype ngắn hạn, thiết kế singleton management adapter tổng hợp thường ổn định hơn việc đăng ký từng instance. Nếu cần từng MBean động, xây lifecycle manager chủ động register/unregister và đặt ObjectName riêng.

## 11. ObjectName trùng và RegistrationPolicy

MBeanServer yêu cầu mỗi ObjectName chỉ định tối đa một MBean đang đăng ký. Va chạm có thể xảy ra khi:

- Hai entry trong map dùng cùng ObjectName.
- Một bean explicit trùng ObjectName với bean được autodetect.
- Hai exporter chạy trong cùng ApplicationContext hoặc hai context dùng chung MBeanServer.
- Một MBean đã được subsystem khác đăng ký trước khi exporter chạy.
- Nhiều instance được cấu hình bằng một tên cố định.

Spring cung cấp `RegistrationPolicy` để kiểm soát phản ứng khi tên đã tồn tại:

| Policy | Hành vi tổng quát | Lưu ý |
| --- | --- | --- |
| `FAIL_ON_EXISTING` | Báo lỗi trùng đăng ký | Thường tốt để phát hiện cấu hình bất ngờ |
| `IGNORE_EXISTING` | Giữ MBean đang tồn tại | Bean mới không nhất thiết được expose |
| `REPLACE_EXISTING` | Thay MBean đang tồn tại | Có thể thay một endpoint do context khác sở hữu |

Ví dụ:

```java
import org.springframework.jmx.support.RegistrationPolicy;

exporter.setRegistrationPolicy(
    RegistrationPolicy.FAIL_ON_EXISTING
);
```

Không dùng `REPLACE_EXISTING` như biện pháp chữa xung đột mặc định. Thay vào đó hãy xác định rõ ai sở hữu ObjectName, vì việc hủy context hoặc unregister có thể tác động đến MBean không phải của exporter đang xử lý.

## 12. Kiểm tra MBean thực tế đã đăng ký

Không thể phân biệt nguồn export chỉ bằng một lời gọi JMX query. Nhưng có thể xác nhận bộ ObjectName và hợp đồng quản trị sau khi application khởi chạy.

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.util.Set;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName pattern =
    new ObjectName("com.example.*:*");

Set<ObjectName> names = server.queryNames(pattern, null);

for (ObjectName name : names) {
    System.out.println(name.getCanonicalName());
    MBeanInfo info = server.getMBeanInfo(name);
    System.out.println("  attributes=" + info.getAttributes().length);
    System.out.println("  operations=" + info.getOperations().length);
}
```

Đoạn code giả định exporter đăng ký vào platform MBeanServer. Nếu exporter dùng server riêng, cần kết nối đúng server đó. Pattern `com.example.*:*` chỉ khớp domain theo wildcard tương ứng; trong hệ thống có domain khác, đổi pattern cho phù hợp.

Bạn cũng có thể kiểm tra một MBean xác định:

```java
ObjectName exact =
    new ObjectName("com.example.cache:type=CacheManagement,name=Primary");

boolean registered = server.isRegistered(exact);
System.out.println("registered=" + registered);
```

Nếu một MBean không xuất hiện, hãy phân tích theo thứ tự: bean có nằm trong context không, map có entry hoặc autodetection có chọn không, assembler có phù hợp không, naming strategy tạo tên nào, registration có bị trùng hoặc lỗi không, và client có kết nối đúng MBeanServer không.

## 13. Khi nào nên chọn map và khi nào nên chọn autodetection?

### Chọn map explicit khi:

1. Cần danh sách MBean cố định, nhỏ và được duyệt cẩn thận.
2. Không muốn phụ thuộc vào annotation hay marker trên class nguồn.
3. Sử dụng một management adapter chuyên dụng cho một số service quan trọng.
4. Muốn bảo đảm thêm bean mới vào context không tự xuất hiện trên JMX.
5. Cần kiểm soát tên đăng ký cụ thể và phạm vi module được export.

### Chọn autodetection khi:

1. Có nhiều Spring-managed bean được thiết kế rõ cho quản trị.
2. Dùng annotation-based export nhất quán với `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation`.
3. Muốn mở rộng tập MBean bằng cách thêm metadata vào class mà không cập nhật một map trung tâm.
4. Có naming convention và chiến lược quản lý trùng ObjectName nhất quán.
5. Đã kiểm soát vùng component scan/context để tránh mở rộng bề mặt quản trị ngoài ý muốn.

### Kết hợp hai cơ chế:

Có thể phù hợp khi một nhóm bean là JMX-compliant và một nhóm adapter được khai báo tường minh. Tuy vậy, cần mô tả rõ trách nhiệm của từng nhóm, không duplicate exporter và không xem autodetection là cơ chế “quét hết mọi thứ rồi tự xử lý xung đột”.

## 14. Các hiểu nhầm phổ biến

| Hiểu nhầm | Điều đúng hơn |
| --- | --- |
| `@Component` sẽ tự thành MBean | Component scanning và MBean autodetection là hai bước riêng |
| Bean không có `@ManagedResource` không thể export | Map explicit có thể export bean phù hợp qua assembler/MBean adapter |
| Map explicit nghĩa là chỉ getter được expose | Danh sách methods phụ thuộc MBean contract và assembler |
| `setAutodetect(true)` công bố mọi bean | Chỉ những ứng viên khớp quy tắc autodetect được xét |
| `@ManagedResource` tự mở JMX remote | Export MBean và bật remote connector là cấu hình khác nhau |
| Thêm bean mới không ảnh hưởng JMX | Với autodetection, bean mới có thể trở thành MBean nếu khớp điều kiện |
| Trùng ObjectName có thể bỏ qua hoàn toàn | Cần xác định ownership, registration policy và sự nhất quán client |
| JMX client biết bean đến từ map hay autodetection | Client thường chỉ thấy ObjectName/MBeanInfo, không thấy nguồn cấu hình Spring |

## 15. Bảo mật và vận hành

Autodetection giúp giảm công việc cấu hình nhưng làm danh sách MBean có thể thay đổi theo tập bean hoặc annotation. Với production, thay đổi này cần được xem như thay đổi bề mặt quản trị. Những lưu ý quan trọng:

- Không annotate/export getter chứa credentials, token, dữ liệu cá nhân hay cấu hình nhạy cảm.
- Không expose operation phá dữ liệu chỉ vì muốn debug nhanh.
- Getter phục vụ monitoring phải nhẹ, ít side effects và giới hạn kích thước dữ liệu trả về.
- Bảo vệ JMX connector bằng network policy, authentication, TLS và authorization phù hợp.
- Giữ `ObjectName`, tên attribute, kiểu và operation signature ổn định để dashboard/script không bị phá vỡ.
- Đảm bảo cùng một MBeanServer không có exporter khác chiếm cùng ObjectName một cách tình cờ.
- Khi cần nhiều instance, thiết kế tên có định danh hợp lý hoặc phân biệt theo kết nối MBeanServer; không mặc định dùng PID ngẫu nhiên cho endpoint mà dashboard cần truy cập ổn định.

**Tính tường minh của map không phải lớp bảo mật đầy đủ**, còn annotation-based autodetection cũng không tự động làm MBean an toàn. Cả hai cần contract quản trị tối thiểu và một JMX connector có chính sách quyền thích hợp.

## 16. Mô hình tư duy

```text
Spring bean được tạo trong context
             |
      +------+-------+
      |              |
  explicit map    autodetection
      |              |
  entry do dev    quy tắc phát hiện
  chỉ định        MBean / metadata
      |              |
      +------+-------+
             |
         MBeanExporter
             |
       ObjectName + MBeanInfo
             |
      RegistrationPolicy
             |
         MBeanServer
             |
       JMX management tool
```

**Ghi nhớ:** `beans` map trả lời **“tôi chọn chính xác bean nào để export”**; autodetection trả lời **“theo cấu hình này, bean nào trong context đủ điều kiện được tìm thấy”**. Cả hai đều phải qua đăng ký MBean và tạo metadata; cả hai đều cần quản lý ObjectName, lifecycle và bảo mật. Trong ứng dụng có management contract cần kiểm soát chặt, map explicit hoặc annotation-based adapter chọn lọc thường dễ dự đoán hơn việc quét rộng không có quy hoạch.
