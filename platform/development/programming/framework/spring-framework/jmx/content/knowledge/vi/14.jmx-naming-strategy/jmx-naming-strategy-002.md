# KeyNamingStrategy: dùng key của map bean làm ObjectName trong Spring JMX

## 1. Mục tiêu

Khi xuất Spring bean qua JMX, mỗi MBean cần một `javax.management.ObjectName` duy nhất trong `MBeanServer`. Spring Framework cung cấp `MBeanExporter` và các chiến lược đặt tên (`ObjectNamingStrategy`) để chuyển một bean cùng khóa cấu hình thành tên JMX.

`KeyNamingStrategy` phù hợp khi ứng dụng khai báo map các bean cần export và **muốn chính key trong map biểu diễn tên MBean**. Thay vì buộc mỗi class có `@ManagedResource(objectName=...)`, cấu hình bên ngoài class định nghĩa danh tính quản trị.

Điểm cần nhớ:

- Key của map `MBeanExporter.setBeans(...)` không phải chỉ là một nhãn tùy ý trong trường hợp dùng `KeyNamingStrategy`: nó là đầu vào để xây dựng `ObjectName`.
- Bean instance là **giá trị** của entry; key là cơ sở xác định **tên đăng ký**.
- Tên JMX có ngữ pháp riêng: `domain:key=value[,key=value...]`.
- `KeyNamingStrategy` giải quyết việc đặt tên, không quyết định attribute/operation nào được xuất. Việc xây dựng `MBeanInfo` thuộc assembler hoặc contract MBean chuẩn.
- Một object name hợp lệ phải không đụng một MBean khác trong cùng server, trừ khi có chính sách registration được cấu hình rõ.

## 2. Từ map bean đến MBeanServer

Luồng cấu hình:

```text
MBeanExporter
  setBeans(Map<String, Object>)
    |
    +-- key: "com.example.jobs:type=Worker,name=Primary"
    +-- value: workerManagementBean
            |
            v
    KeyNamingStrategy.getObjectName(bean, key)
            |
            v
    ObjectName("com.example.jobs:type=Worker,name=Primary")
            |
            v
    MBeanServer.registerMBean(...)
```

`MBeanExporter` đưa cho naming strategy hai dữ liệu: bean cần export và key liên quan tới cấu hình export. Với `KeyNamingStrategy`, key là nguồn đặt tên chính. Tên của Java class hoặc Spring bean ID không tự thay thế key khi bạn đã chỉ định một key JMX tường minh trong map.

Sự phân tách này hữu ích khi một implementation được dùng ở nhiều deployment khác nhau nhưng mỗi deployment có `ObjectName` khác nhau. Cũng vì thế, quản lý key của map phải được coi là quản lý API vận hành.

## 3. Ví dụ một MBean chuẩn

Tạo interface theo quy ước Standard MBean:

```java
package com.example.jobs;

public interface WorkerMonitorMBean {
    int getQueueDepth();
    boolean isPaused();
    void requestPause();
}
```

Implementation:

```java
package com.example.jobs;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class WorkerMonitor implements WorkerMonitorMBean {
    private final AtomicInteger queued = new AtomicInteger();
    private final AtomicBoolean paused = new AtomicBoolean();

    @Override
    public int getQueueDepth() {
        return queued.get();
    }

    @Override
    public boolean isPaused() {
        return paused.get();
    }

    @Override
    public void requestPause() {
        paused.set(true);
    }
}
```

`WorkerMonitor` có contract JMX riêng, không cần import các annotation của Spring. Trong một ứng dụng thật, số lượng queued được cập nhật từ worker/queue chính xác và lệnh pause phải tuân theo quy tắc quản trị, không chỉ sửa một biến mà worker không sử dụng.

## 4. Java configuration với KeyNamingStrategy

Khai báo `MBeanExporter` và map các bean:

```java
package com.example.jobs.config;

import com.example.jobs.WorkerMonitor;
import java.lang.management.ManagementFactory;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.naming.KeyNamingStrategy;

@Configuration
public class JmxExportConfig {

    @Bean
    public WorkerMonitor workerMonitor() {
        return new WorkerMonitor();
    }

    @Bean
    public MBeanExporter mbeanExporter(WorkerMonitor workerMonitor) {
        Map<String, Object> exported = new LinkedHashMap<>();

        exported.put(
            "com.example.jobs:type=Worker,name=Primary",
            workerMonitor
        );

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(ManagementFactory.getPlatformMBeanServer());
        exporter.setNamingStrategy(new KeyNamingStrategy());
        exporter.setBeans(exported);
        return exporter;
    }
}
```

Khi context khởi động, exporter đăng ký `workerMonitor` dưới tên:

```text
com.example.jobs:type=Worker,name=Primary
```

Trong ví dụ này, `WorkerMonitor` là Standard MBean. Nếu giá trị của map là POJO thường, có thể phải dùng `MBeanInfoAssembler` phù hợp để Spring tạo ModelMBean; `KeyNamingStrategy` không biến một POJO bất kỳ thành MBean Java chuẩn bằng chính nó.

Cũng cần chú ý cấu hình Spring Boot: nếu Boot đã tự tạo exporter, thêm một exporter thủ công có thể dẫn tới hai lần đăng ký cùng ObjectName hoặc hai vùng tên khác nhau. Cần quản lý một chiến lược export nhất quán.

## 5. Key trong map không phải key property của ObjectName

Có hai chữ *key* thường gây nhầm:

1. **Map key:** chuỗi ở vế trái của `exported.put(key, bean)`; `KeyNamingStrategy` nhận chuỗi này.
2. **ObjectName key property:** phần như `type`, `name`, `instance` nằm *bên trong* cú pháp ObjectName.

Ví dụ:

```java
String mapKey = "com.example:type=Cache,name=Catalog";
exported.put(mapKey, catalogMonitor);
```

Toàn bộ `mapKey` là một JMX ObjectName, còn `type` và `name` là hai property keys của ObjectName. `KeyNamingStrategy` không tự suy luận domain và properties từ cụm chữ “catalogMonitor” trong key tùy ý của `Map` nếu bạn chưa thiết kế hoặc cấu hình cách chuyển đổi phù hợp.

Khi không có mapping tùy chỉnh, nên dùng key mang cú pháp ObjectName đầy đủ, dễ đối chiếu và ổn định.

## 6. KeyNamingStrategy và Properties mappings

`KeyNamingStrategy` còn hỗ trợ một bảng ánh xạ key sang ObjectName thông qua `Properties`. Nhờ đó, key trong map có thể là alias ngắn, còn tên JMX thật được cấu hình tập trung.

Ví dụ định nghĩa mappings:

```java
import java.util.Properties;
import org.springframework.jmx.export.naming.KeyNamingStrategy;

Properties mappings = new Properties();
mappings.setProperty(
    "primaryWorker",
    "com.example.jobs:type=Worker,name=Primary"
);
mappings.setProperty(
    "secondaryWorker",
    "com.example.jobs:type=Worker,name=Secondary"
);

KeyNamingStrategy naming = new KeyNamingStrategy();
naming.setMappings(mappings);
```

Khi khai báo map:

```java
Map<String, Object> exported = Map.of(
    "primaryWorker", primaryWorker,
    "secondaryWorker", secondaryWorker
);

MBeanExporter exporter = new MBeanExporter();
exporter.setNamingStrategy(naming);
exporter.setBeans(exported);
```

Ý nghĩa: key trong map đóng vai trò alias nội bộ, `Properties` cung cấp tên đăng ký. Nếu không có mapping cho một key, chiến lược có thể dùng key đó làm ObjectName đầu vào; vì vậy key thiếu mapping phải là tên hợp lệ hoặc việc đăng ký sẽ gặp lỗi. Nên kiểm thử và quản lý mappings như một phần của cấu hình ứng dụng.

Lưu ý: các mapping không phải bản ghi đăng ký MBean; chúng chỉ xác định tên sẽ được sử dụng khi exporter làm công việc đăng ký.

## 7. MBeanInfoAssembler quyết định bề mặt quản trị

Bên cạnh `ObjectNamingStrategy`, exporter có thể sử dụng `MBeanInfoAssembler` để xác định các thuộc tính và thao tác của bean.

Ví dụ:

```java
MBeanExporter exporter = new MBeanExporter();
exporter.setNamingStrategy(new KeyNamingStrategy());
exporter.setBeans(exported);
// exporter.setAssembler(assembler); // Nếu xuất POJO bằng ModelMBean
```

Phân công rõ:

| Thành phần | Trách nhiệm |
| --- | --- |
| `MBeanExporter.setBeans` | Chọn bean nào được export và khóa gắn với từng bean |
| `KeyNamingStrategy` | Biến key thành ObjectName |
| `MBeanInfoAssembler` | Quyết định metadata, attribute và operation khi export POJO theo ModelMBean |
| `MBeanServer` | Đăng ký và phục vụ truy vấn MBean |
| JMX client | Kết nối, tìm ObjectName và tương tác theo MBeanInfo |

Nếu một MBean xuất hiện đúng tên nhưng thiếu operation, sửa `KeyNamingStrategy` thường không có tác dụng. Phải xem interface MBean hoặc assembler. Nếu operation đúng nhưng tên xuất hiện sai domain, nên xem key map và mapping.

## 8. Quy tắc đặt ObjectName an toàn

Một tên JMX hợp lệ có dạng:

```text
domain:key=value[,key=value...]
```

Ví dụ:

```text
com.example.jobs:type=Worker,name=Primary
com.example.jobs:type=Worker,name=Secondary,region=apac
```

Các vấn đề thường gặp:

- Domain không phù hợp hoặc chứa ký tự pattern ngoài ý muốn.
- Thiếu dấu `:` hoặc cặp `key=value`.
- Lặp property key trong cùng một tên.
- Hai map entries giải quyết về cùng ObjectName.
- Value động chứa dấu phẩy, bằng, dấu nháy kép hoặc wildcard không xử lý đúng.

Ví dụ từ giá trị động:

```java
import javax.management.ObjectName;

String rawInstanceName = "worker,apac*";

String objectNameText =
    "com.example.jobs:type=Worker,name=" +
    ObjectName.quote(rawInstanceName);

ObjectName objectName = new ObjectName(objectNameText);
System.out.println(objectName.isPattern()); // false

exported.put(objectName.getCanonicalName(), workerMonitor);
```

`ObjectName.quote` nên áp dụng lên **property value**, không áp dụng lên toàn bộ ObjectName. Đây là cách tránh key của map bị parse thành pattern hoặc nhiều cặp property không mong muốn.

Với names được xây từ configuration không đáng tin cậy, xác thực cả domain và property key. Dùng `ObjectName` để kiểm tra cấu trúc trước khi khởi động exporter là một biện pháp tốt.

## 9. Khác biệt giữa key map và Spring bean name

Spring bean có thể tên `workerMonitor`:

```java
@Bean("workerMonitor")
WorkerMonitor monitor() {
    return new WorkerMonitor();
}
```

Nhưng cấu hình explicit map vẫn có key:

```java
exported.put(
    "com.example.jobs:type=Worker,name=Primary",
    workerMonitor
);
```

Khi `KeyNamingStrategy` nhận key này, tên MBean là `com.example.jobs:type=Worker,name=Primary` chứ không phải `workerMonitor`. Đổi Spring bean name không nhất thiết đổi ObjectName nếu map key vẫn giữ nguyên.

Ngược lại, nếu cấu hình xuất bean qua tên reference và sử dụng key là một bean name đơn giản, cần đảm bảo naming strategy hoặc mapping có thể chuyển được key ấy thành ObjectName hợp lệ. Cách an toàn và dễ hiểu nhất trong giáo trình là đặt explicit key đầy đủ.

## 10. KeyNamingStrategy so với MetadataNamingStrategy và IdentityNamingStrategy

Ba chiến lược thường được nhắc tới trong Spring JMX:

| Strategy | Nguồn đặt tên | Trường hợp dùng |
| --- | --- | --- |
| `KeyNamingStrategy` | Key export map, có thể qua Properties mappings | Cấu hình định danh tập trung, không cần annotation objectName trên class |
| `MetadataNamingStrategy` | Metadata như `@ManagedResource(objectName=...)` | Annotation-driven export |
| `IdentityNamingStrategy` | Đặc điểm định danh runtime của object | Các đối tượng cần tên khác nhau theo instance, không nhằm tạo tên vận hành ổn định |

Với MBean dùng cho automation và dashboard, tên cần ổn định qua restart để client không phải khám phá lại bằng một định danh ngẫu nhiên. `KeyNamingStrategy` thích hợp khi bạn chủ động quản lý `ObjectName` trong cấu hình.

Nếu mục tiêu là mỗi deployment có tên riêng, đặt `instance`/environment key property rõ ràng thay vì dựa vào identity runtime không ổn định.

## 11. Khi nào key map bị trùng?

Ví dụ có hai bean:

```java
exported.put(
    "com.example:type=Cache,name=Primary",
    cacheA
);
exported.put(
    "com.example:type=Cache,name=Primary",
    cacheB
);
```

Trong Java `Map`, lần `put` thứ hai cùng key **thay giá trị trước**, nên exporter chỉ thấy một entry; không tự báo lỗi duplicate MBean ở trường hợp cụ thể này. Đây là nguyên nhân khó phát hiện vì một bean đơn giản “biến mất” khỏi cấu hình export.

Trường hợp khác:

```java
exported.put(
    "com.example:type=Cache,name=Primary",
    cacheA
);
exported.put(
    "com.example:name=Primary,type=Cache",
    cacheB
);
```

Hai chuỗi key khác nhau nên cùng nằm trong `Map`, nhưng hai `ObjectName` tương đương về canonical identity. Khi cả hai đăng ký vào cùng server, thao tác đăng ký thứ hai có thể ném `InstanceAlreadyExistsException`, tùy registration policy.

Nên validate toàn bộ key như `ObjectName`, chuyển về `getCanonicalName()` và kiểm tra uniqueness trước khi gửi cho exporter.

## 12. Tạo mapping có kiểm tra trùng canonical name

Ví dụ một builder nhỏ để phát hiện trùng định danh JMX:

```java
import java.util.LinkedHashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;

public final class ExportedMBeans {
    private final Map<String, Object> values = new LinkedHashMap<>();
    private final Set<String> canonicalNames = new HashSet<>();

    public void add(String name, Object bean)
            throws MalformedObjectNameException {
        ObjectName objectName = new ObjectName(name);
        if (objectName.isPattern()) {
            throw new IllegalArgumentException(
                "A registration name cannot be a JMX pattern: " + name
            );
        }
        String canonical = objectName.getCanonicalName();
        if (!canonicalNames.add(canonical)) {
            throw new IllegalArgumentException(
                "Duplicate MBean ObjectName: " + canonical
            );
        }
        values.put(canonical, bean);
    }

    public Map<String, Object> asMap() {
        return Map.copyOf(values);
    }
}
```

Công cụ này giúp phát hiện trùng canonical `ObjectName` **trong bản cấu hình của bạn**; nó không thay thế việc kiểm tra MBean đã được component khác đăng ký trong `MBeanServer`. `Map.copyOf` tạo map bất biến nhưng không bảo đảm thứ tự iteration; nếu cần thứ tự hiển thị hoặc khởi tạo ổn định, có thể trả một bản copy `LinkedHashMap` không sửa được theo cách thích hợp.

## 13. Đọc và chẩn đoán lỗi lúc khởi động

Khi exporter không đăng ký được MBean, xem nested cause:

| Lỗi / triệu chứng | Ý nghĩa thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `MalformedObjectNameException` | Key/mapping tạo tên không đúng ngữ pháp | In key và canonical parsing trong test |
| `InstanceAlreadyExistsException` | Tên đã có trong cùng server | So sánh canonical name, kiểm tra exporter khác |
| `NotCompliantMBeanException` | Bean chưa phải MBean hợp lệ và assembler không xử lý | Kiểm tra Standard MBean/MXBean/assembler |
| Đăng ký thành công nhưng sai tên | Map key hoặc Properties mappings không như dự kiến | Kiểm tra resolved ObjectName |
| MBean không xuất hiện | Map không chứa entry, bean chưa tạo hoặc exporter không chạy | Kiểm tra bean context và configuration |
| MBean có nhưng thiếu method | Contract MBean/assembler không xuất method | Kiểm tra `MBeanInfo` |

Có thể thực hiện probe bên trong cùng JVM:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName expected = new ObjectName(
    "com.example.jobs:type=Worker,name=Primary"
);

System.out.println(server.isRegistered(expected));

for (ObjectName name : server.queryNames(
        new ObjectName("com.example.jobs:*"), null)) {
    System.out.println(name.getCanonicalName());
}
```

Nếu exporter trỏ tới custom `MBeanServer`, phải probe chính server đó. Khi client JConsole/VisualVM không thấy MBean dù probe thấy, tiếp tục kiểm tra JMX connector và đúng JVM thay vì thay đổi map key vô cớ.

## 14. Kiểm thử KeyNamingStrategy

Một phép thử đơn vị nên xác nhận key được biến thành tên mong đợi:

```java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.jmx.export.naming.KeyNamingStrategy;

class KeyNamingStrategyTest {
    @Test
    void usesMapKeyAsObjectName() throws Exception {
        KeyNamingStrategy naming = new KeyNamingStrategy();

        ObjectName actual = naming.getObjectName(
            new WorkerMonitor(),
            "com.example.jobs:name=Primary,type=Worker"
        );

        ObjectName expected = new ObjectName(
            "com.example.jobs:type=Worker,name=Primary"
        );

        assertEquals(expected, actual);
        assertFalse(actual.isPattern());
    }
}
```

Integration test nên khởi tạo Spring context với một exporter trỏ tới test server riêng hoặc một ObjectName có namespace duy nhất, sau đó xác nhận:

```java
assertTrue(mBeanServer.isRegistered(
    new ObjectName("com.example.jobs:type=Worker,name=Primary")
));
```

Cuối test cần đóng context hoặc unregister những MBean thuộc test. Nếu dùng platform server trong các test song song, tránh dùng cùng một ObjectName tĩnh. Với `Properties mappings`, nên có test xác nhận từng alias resolve về tên chính xác, không bị sót mapping.

## 15. Vòng đời và quyền truy cập

`MBeanExporter` thông thường quản lý việc đăng ký và unregister các MBean mà nó sở hữu theo vòng đời context. Nhưng không nên mặc định exporter có thể xóa những MBean do ứng dụng khác đăng ký. Khi bật registration policy thay thế MBean đã tồn tại, phải hiểu chủ sở hữu và tác động tới client.

`KeyNamingStrategy` không cung cấp authentication, authorization hay TLS. Nó chỉ định danh MBean. Quyền kết nối JMX và quyền gọi operation vẫn do connector, security policy và application layer quyết định.

Trong production:

- Giữ `ObjectName` ổn định và tránh nhét secret hoặc dữ liệu cá nhân vào key.
- Tránh export thao tác nguy hiểm chỉ vì nó là method public.
- Giới hạn quyền truy cập remote JMX.
- Quản lý alias/mapping theo cấu hình versioned.
- Kiểm tra trùng tên khi khởi động và log thông tin đủ để chẩn đoán nhưng không lộ dữ liệu nhạy cảm.

## 16. Khi nào nên dùng KeyNamingStrategy?

Chọn `KeyNamingStrategy` khi:

1. Muốn quản lý tên JMX tập trung ở config, tách khỏi class.
2. Một bean implementation được triển khai ở nhiều instance với ObjectName khác nhau.
3. Cần map alias nội bộ sang tên JMX ổn định.
4. Muốn export các MBean chuẩn mà không cần thêm `@ManagedResource(objectName=...)` lên từng class.
5. Muốn kiểm soát naming theo module/deployment và dùng test bảo vệ contract.

Nếu nhóm muốn class tự khai báo tên và metadata quản trị, `MetadataNamingStrategy` cùng các annotation có thể phù hợp hơn. Hai phương án nên được lựa chọn nhất quán, không kết hợp tùy tiện khiến một bean có nhiều nguồn định danh cạnh tranh.

## 17. Ghi nhớ

**KeyNamingStrategy xem key của map export là nguồn xác định ObjectName.** Khi key chứa tên JMX đầy đủ, exporter có thể đăng ký bean theo đúng tên đó; khi cấu hình mappings, key đóng vai trò alias được đổi sang ObjectName. Naming strategy chỉ phụ trách **đặt tên**: bề mặt attribute/operation vẫn được quyết định bởi contract MBean hoặc assembler, còn an toàn truy cập phải được quản lý riêng. Muốn tránh lỗi khó tìm, hãy validate ObjectName, kiểm tra trùng canonical names, giữ tên ổn định và đối chiếu kết quả bằng `MBeanServer.isRegistered` hoặc `queryNames`.
