# Tránh hai ứng dụng cùng chiếm một ObjectName trong Spring Framework JMX

## 1. Vì sao ObjectName có thể bị trùng?

Trong Java Management Extensions (JMX), một `MBeanServer` duy trì registry ánh xạ **mỗi `ObjectName` tới một MBean đang được đăng ký**. Trong phạm vi một MBeanServer, hai MBean không thể đồng thời chiếm cùng một ObjectName. Điều này giống một khóa duy nhất trong registry, không phải địa chỉ có thể tự chia sẻ giữa hai đối tượng độc lập.

Vấn đề thường xuất hiện khi **hai ứng dụng Spring, hai ApplicationContext, hai module hoặc hai MBeanExporter** cùng sử dụng một MBeanServer và cùng cố đăng ký, chẳng hạn:

```text
com.example.app:type=CacheMonitor,name=Primary
```

Ứng dụng A đã đăng ký MBean dưới tên này; ứng dụng B khởi động sau và cũng muốn dùng đúng tên. Nếu exporter không có chính sách cho trường hợp trùng, quá trình đăng ký thường thất bại. Nếu dùng chính sách thay thế mà không kiểm soát ownership, ứng dụng B có thể vô tình thay MBean của A và làm sai dữ liệu monitoring.

**Nguyên tắc:** `ObjectName` phải duy nhất trong **từng MBeanServer**, và ứng dụng cần định nghĩa rõ **ai sở hữu tên, đăng ký, cập nhật và hủy đăng ký**. Tránh phụ thuộc vào thứ tự khởi động để quyết định ai “giành” được tên.

## 2. Phạm vi duy nhất: cùng MBeanServer, không phải toàn hệ thống

Cần phân biệt những tình huống:

| Tình huống | Có xung đột JMX không? |
| --- | --- |
| Hai Spring ApplicationContext trong cùng JVM, cùng platform MBeanServer, cùng ObjectName | **Có** nếu cả hai đều đăng ký |
| Hai WAR trong cùng application server dùng một MBeanServer chung | **Có thể có**, tùy cấu hình container |
| Hai MBeanExporter của cùng context đăng ký cùng tên | **Có** |
| Hai JVM độc lập, mỗi JVM có MBeanServer riêng, cùng ObjectName | **Không xung đột trực tiếp** giữa hai server |
| Một JVM có hai MBeanServer riêng, mỗi server có cùng ObjectName | **Không xung đột registry**, nhưng client phải chọn đúng server |
| Hai MBean có cùng Java class nhưng ObjectName khác nhau | **Không** vì định danh khác |

JMX client định vị tài nguyên bằng **kết nối đến server** cộng với **ObjectName trong server đó**. ObjectName không phải global UUID trên mọi JVM. Hai replica của ứng dụng ở các JVM khác nhau có thể dùng tên giống nhau và vẫn đúng nếu client giám sát từng JVM theo kết nối riêng.

## 3. Mô hình hai ứng dụng cùng chiếm một tên

```text
                 Shared MBeanServer
                       |
         ObjectName: demo:type=Cache,name=Main
                       ^
                       |
Application A           |             Application B
Spring Context A        |             Spring Context B
   MBeanExporter A -----+             MBeanExporter B
                         \           /
                          \----?----/
                   cùng muốn register
```

MBeanServer không biết bean đó thuộc về “ứng dụng” nào theo nghĩa Spring. Nó kiểm tra ObjectName đã tồn tại chưa và áp dụng hành vi đăng ký của JMX. Spring `MBeanExporter` bổ sung `RegistrationPolicy` để xử lý tình huống tên đã có, nhưng policy không tự biến một tên chung thành hợp đồng sở hữu an toàn.

Có ba ý quan trọng:

1. **Naming:** đặt tên có đủ thông tin phân biệt khi hai endpoint thật sự khác nhau.
2. **Registration policy:** xác định điều gì xảy ra nếu tên đã có.
3. **Lifecycle/ownership:** chỉ hủy đăng ký đối tượng mà thành phần quản lý thực sự sở hữu; tránh context này phá registry của context khác.

## 4. RegistrationPolicy trong Spring Framework

`org.springframework.jmx.support.RegistrationPolicy` có các lựa chọn chính sau:

| Chính sách | Ý nghĩa khi ObjectName đã có | Khi nào cân nhắc |
| --- | --- | --- |
| `FAIL_ON_EXISTING` | Không thay thế; báo lỗi khi tên đã đăng ký | Mặc định an toàn để phát hiện trùng tên bất ngờ |
| `IGNORE_EXISTING` | Giữ MBean đã có và bỏ qua việc đăng ký MBean mới tại tên đó | Khi chấp nhận dùng MBean hiện hữu và hiểu rõ sở hữu |
| `REPLACE_EXISTING` | Thay MBean đang đăng ký bằng đối tượng mới | Chỉ khi có quyền sở hữu và kế hoạch thay thế rõ ràng |

Ví dụ Java config:

```java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

@Configuration
public class JmxExportConfig {
    @Bean
    public MBeanExporter mbeanExporter(CacheManagement cache) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
            "com.example.cache:type=CacheManagement,name=Main",
            cache
        ));
        exporter.setRegistrationPolicy(
            RegistrationPolicy.FAIL_ON_EXISTING
        );
        return exporter;
    }
}
```

`CacheManagement` là management adapter của ứng dụng. Map chỉ ra bean được export, còn policy chỉ xử lý xung đột tại thời điểm đăng ký. Đoạn code giả định có bean `CacheManagement` được cấu hình và một `MBeanServer` phù hợp.

### Vì sao thường ưu tiên FAIL_ON_EXISTING?

Nếu tên trùng ngoài dự kiến, lỗi ngay lúc startup giúp phát hiện bug cấu hình. Nó không để ứng dụng mới âm thầm thay endpoint của ứng dụng khác. Trong hệ thống nhiều module, việc một MBean không xuất hiện có thể nghiêm trọng hơn việc startup báo lỗi rõ ràng, bởi dashboard sẽ đọc sai đối tượng.

### Vì sao IGNORE_EXISTING không phải cách sửa tuyệt đối?

`IGNORE_EXISTING` có thể làm startup không thất bại, nhưng bean của ứng dụng B **không được quản trị qua ObjectName dự kiến**. Công cụ vận hành có thể vẫn nhìn thấy MBean của A và tưởng đang đọc B. Nếu B cần endpoint riêng, phải đặt tên riêng, không chỉ bỏ qua xung đột.

### Vì sao REPLACE_EXISTING nguy hiểm?

`REPLACE_EXISTING` có thể thay một MBean do ứng dụng A đăng ký. Client đang giữ ObjectName có thể thấy thông tin đột ngột đổi nguồn. Khi A hoặc B shutdown, logic unregister/lifecycle có thể khiến endpoint biến mất ngoài kỳ vọng. Chính sách này chỉ phù hợp khi việc thay thế thực sự là chủ ý và có cơ chế sở hữu rõ ràng, không dùng để giải quyết naming collision bằng cách “ai khởi động sau thì thắng”.

## 5. Đặt ObjectName duy nhất bằng domain và key properties

ObjectName có cú pháp:

```text
domain:key1=value1,key2=value2,...
```

Ví dụ thiếu thông tin:

```text
demo:type=Cache,name=Main
```

Nếu hai ứng dụng chia sẻ server, tên `demo` quá chung chung. Một cách thiết kế tốt hơn:

```text
com.example.billing:type=Cache,name=Main
com.example.shipping:type=Cache,name=Main
```

Hoặc dùng property phân biệt ứng dụng:

```text
com.example.services:application=billing,type=Cache,name=Main
com.example.services:application=shipping,type=Cache,name=Main
```

Domain/keys được chọn nên **ổn định, có ý nghĩa vận hành và không chứa bí mật**. Những key phổ biến gồm `application`, `component`, `type`, `name`, `tenant` (chỉ nếu tenant identifier không nhạy cảm), `instance` hoặc `context`.

Với nhiều instance của cùng một ứng dụng cùng đăng ký vào một MBeanServer:

```text
com.example.jobs:application=worker,type=Queue,name=Main,instance=alpha
com.example.jobs:application=worker,type=Queue,name=Main,instance=beta
```

Nhưng nếu các replica nằm ở các JVM độc lập, mỗi JVM có server riêng, **không cần tự động thêm `instance` chỉ để tránh xung đột vốn không tồn tại**. Thêm ID biến động như PID, timestamp hoặc UUID ngẫu nhiên có thể làm dashboard khó tìm tên ổn định sau restart.

## 6. Tên chuẩn hóa và thứ tự key properties

Trong JMX, hai chuỗi sau mô tả cùng một ObjectName:

```text
com.example.cache:type=Cache,name=Main
com.example.cache:name=Main,type=Cache
```

Thứ tự các key property không quyết định danh tính. Do đó đổi thứ tự chuỗi **không tránh được xung đột**.

```java
import javax.management.ObjectName;

ObjectName first = new ObjectName(
    "com.example.cache:type=Cache,name=Main"
);
ObjectName second = new ObjectName(
    "com.example.cache:name=Main,type=Cache"
);

System.out.println(first.equals(second)); // true
System.out.println(first.getCanonicalName());
// com.example.cache:name=Main,type=Cache
```

Tương tự, Spring bean name khác nhau, chẳng hạn `billingCacheMonitor` và `shippingCacheMonitor`, **không đảm bảo ObjectName khác nhau** nếu exporter/naming strategy vẫn sinh cùng một giá trị.

## 7. @ManagedResource và MetadataNamingStrategy

Trong annotation-based export, `@ManagedResource` có thể khai báo ObjectName:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.billing:type=CacheMonitor,name=Main"
)
public class BillingCacheMonitor {
    @ManagedAttribute
    public int getEntryCount() {
        return 100;
    }
}
```

Đối với ứng dụng thứ hai:

```java
@Component
@ManagedResource(
    objectName = "com.example.shipping:type=CacheMonitor,name=Main"
)
public class ShippingCacheMonitor {
    @ManagedAttribute
    public int getEntryCount() {
        return 50;
    }
}
```

Khi dùng `@EnableMBeanExport` hoặc `MBeanExporter` với `MetadataNamingStrategy`/metadata assembler được cấu hình phù hợp, hai bean được đăng ký dưới ObjectName khác nhau. Metadata chỉ là dữ liệu cấu hình: tên cuối cùng vẫn phải hợp lệ và không trùng trong đúng MBeanServer.

**Lưu ý:** `@ManagedResource` không tự tạo namespace ứng dụng. Nếu copy-paste class nhưng giữ nguyên `objectName`, hai application context cùng server vẫn có thể trùng. Review annotation ObjectName như một API công khai.

## 8. Tách biệt exporter của hai context

Giả sử hai ApplicationContext A và B cùng JVM:

```text
ApplicationContext A:
  @ManagedResource("com.example:type=Health,name=Main")

ApplicationContext B:
  @ManagedResource("com.example:type=Health,name=Main")

Shared PlatformMBeanServer:
  ObjectName bị trùng.
```

Có thể chọn các hướng:

1. **Đặt tên khác nhau trong cùng server**: dùng `application`, `module`, `context` hoặc domain khác; cách đơn giản và dễ giám sát nhất khi muốn dùng chung JMX endpoint.
2. **Chỉ một context export MBean tổng hợp**: context A hoặc một parent context giữ management adapter, đọc trạng thái của A/B qua service abstraction.
3. **Dùng MBeanServer riêng biệt khi thực sự cần cô lập registry**: cần bảo đảm công cụ JMX kết nối đúng server và connector được vận hành rõ ràng; không mặc định JConsole platform connection sẽ tự liệt kê MBean ở mọi server.
4. **Không export một số bean không cần quản trị**: giới hạn autodetection hoặc map explicit để tránh hai exporter cùng đăng ký một endpoint.

Không nên tạo MBeanServer riêng chỉ để che một lỗi đặt tên. Việc tách server có thể làm tăng độ phức tạp của kết nối, bảo mật, quyền và tooling.

## 9. Lựa chọn một chủ sở hữu duy nhất cho MBean

Vấn đề không chỉ là tên. Khi một MBean được đăng ký, cần biết ai có trách nhiệm:

- Tạo và đăng ký MBean.
- Duy trì trạng thái được quản trị.
- Thay thế MBean khi deployment hoặc reload.
- Hủy đăng ký đúng lúc khi context dừng.
- Không xóa MBean do hệ thống khác đăng ký cùng tên.

Mô hình ownership rõ ràng:

```text
Spring Context A
    |
    +-- owns com.example.billing:type=Cache,name=Main
    |      -> register
    |      -> manage
    |      -> unregister on shutdown

Spring Context B
    |
    +-- owns com.example.shipping:type=Cache,name=Main
           -> register
           -> manage
           -> unregister on shutdown
```

Không để A dọn registry của B chỉ vì chúng cùng biết một ObjectName. Trong các hệ thống plugin, hot reload hoặc nhiều WAR, cần đặc biệt chú ý classloader và vòng đời: nếu MBeanServer còn giữ reference đến MBean của ứng dụng đã undeploy, có thể gây leak và lỗi redeployment.

## 10. Race condition khi hai ứng dụng đăng ký đồng thời

Thử kiểm tra `isRegistered()` trước khi `registerMBean()` không loại bỏ race:

```java
if (!server.isRegistered(name)) {
    server.registerMBean(bean, name);
}
```

Hai thread hoặc hai exporter có thể cùng nhìn thấy `false`; một bên đăng ký thành công, bên còn lại nhận `InstanceAlreadyExistsException`. Vì vậy không nên xem check-then-register là mutex.

Ưu tiên:

- Thiết kế ObjectName duy nhất ngay từ đầu.
- Để JMX registry báo lỗi trùng tên theo thao tác đăng ký thực tế.
- Với tài nguyên thực sự cần singleton trên server, có một lifecycle owner điều phối việc đăng ký.
- Khi cần coordination giữa ứng dụng, dùng cơ chế điều phối ở cấp deployment/application phù hợp thay vì cho nhiều owner cạnh tranh cùng tên.

Ngay cả khi `isRegistered(name)` trả true, điều đó chỉ chứng minh có một MBean tại thời điểm kiểm tra, không chứng minh nó thuộc ứng dụng đang chạy. Đừng dùng `isRegistered` như giấy phép để unregister hoặc replace một MBean không thuộc sở hữu của mình.

## 11. Đăng ký qua MBeanServer trực tiếp

JMX chuẩn có thể đăng ký MBean theo ObjectName:

```java
import java.lang.management.ManagementFactory;
import javax.management.InstanceAlreadyExistsException;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.billing:type=Cache,name=Main"
);

try {
    server.registerMBean(cacheMonitorMBean, name);
} catch (InstanceAlreadyExistsException collision) {
    throw new IllegalStateException(
        "ObjectName already owned by another MBean: " + name,
        collision
    );
}
```

`cacheMonitorMBean` ở ví dụ cần là instance Standard MBean/MXBean hoặc DynamicMBean hợp lệ. Với Spring exporter, không cần đăng ký thủ công cùng đối tượng một lần nữa: tránh tạo hai chủ sở hữu đăng ký.

Quy trình xử lý xung đột thực tế không nên tự động unregister rồi retry mù. Đầu tiên phải xác định vì sao tên đã có, có phải exporter cũ chưa cleanup hay ứng dụng khác đang sở hữu, rồi quyết định sửa naming hoặc lifecycle.

## 12. Khám phá ObjectName đang tồn tại

Trước khi kết luận hai ứng dụng trùng tên, cần nhìn registry đúng MBeanServer:

```java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName pattern =
    new ObjectName("com.example.*:*");

Set<ObjectName> names = server.queryNames(pattern, null);

names.stream()
    .map(ObjectName::getCanonicalName)
    .sorted()
    .forEach(System.out::println);
```

Nếu ứng dụng export vào server khác, cần dùng `MBeanServerConnection` của đúng server đó. Pattern có wildcard chỉ áp dụng với tên khớp, không đại diện cho toàn bộ hệ thống.

Kiểm tra tên cụ thể:

```java
ObjectName exact = new ObjectName(
    "com.example.billing:type=Cache,name=Main"
);

System.out.println(server.isRegistered(exact));
```

Sau đó có thể dùng `getMBeanInfo(exact)` để kiểm tra class name và attribute/operation của MBean đang đăng ký. **Metadata không luôn xác định chính xác Spring context owner**; một JMX ModelMBean có thể che class implementation. Nếu cần biết owner, ứng dụng nên công bố một attribute an toàn như `ApplicationId` hoặc duy trì registry nội bộ có ownership rõ ràng.

## 13. Đặt tên khi nhiều instance và nhiều tenant

Đối với hệ thống nhiều ứng dụng hoặc tenant, không thể chỉ nối một chuỗi tùy ý vào ObjectName. Value có thể chứa dấu phẩy, dấu bằng, dấu hai chấm hoặc wildcard. Hãy tạo value an toàn:

```java
import javax.management.ObjectName;

String applicationId = "billing,blue";
ObjectName name = new ObjectName(
    "com.example.services:application=" +
    ObjectName.quote(applicationId) +
    ",type=Cache,name=Main"
);
```

`ObjectName.quote` dùng để biểu diễn value literal theo cú pháp JMX, tránh tách nhầm key properties hoặc tạo wildcard pattern ngoài ý muốn. Không đưa secret, token hoặc thông tin nhạy cảm vào ObjectName, vì tên MBean thường hiển thị trong công cụ và log.

Với nhiều tenant, hãy cân nhắc liệu mỗi tenant có thật sự cần một MBean riêng không. Hàng nghìn MBean có thể khiến query, registration và lifecycle nặng hơn. Một MBean tổng hợp cùng cơ chế truy vấn có kiểm soát có thể phù hợp hơn khi số tenant rất lớn.

## 14. Kiểm soát số lượng exporter và autodetection

Một ứng dụng có thể có:

- Một `MBeanExporter` khai báo map `beans`.
- Một exporter được cấu hình bởi `@EnableMBeanExport`.
- Một exporter khác được cấu hình qua XML `<context:mbean-export/>`.
- Các MBean do Spring Boot Actuator hoặc thư viện nền tảng đăng ký.

Nếu nhiều cơ chế cùng export một bean hoặc cùng đặt một ObjectName, có thể xảy ra trùng. Không nên bật hai chiến lược export đồng thời mà không biết chúng đăng ký những đối tượng nào.

Autodetection cũng có thể mở rộng tập MBean khi thêm bean/annotation mới. Đối với môi trường nhạy cảm, dùng management adapter và map explicit/annotation chọn lọc để kiểm soát bề mặt export.

Mỗi exporter cần naming strategy và registration policy phù hợp. Dù cùng class Java, nếu hai exporter dùng naming strategy khác nhau, chúng có thể tạo hai ObjectName khác nhau (dẫn đến hai MBean quản trị cùng nguồn); đây không phải xung đột tên nhưng có thể gây trùng số liệu hoặc thao tác.

## 15. Kịch bản triển khai và hướng xử lý

### Kịch bản A: hai Spring Boot service ở hai JVM

Service billing chạy port JMX riêng, service shipping ở JVM khác. Cả hai dùng `com.example:type=Health,name=Main`. Về mặt registry, không có conflict trực tiếp vì MBeanServer khác nhau. Tooling phân biệt theo service URL/connection. Có thể giữ tên chung để dashboard tái sử dụng nếu quy ước endpoint đồng nhất.

### Kịch bản B: hai WAR trong cùng Tomcat, cùng MBeanServer

Hai WAR đều export `com.example:type=Cache,name=Main`. Conflict thật sự xảy ra. Nên gắn `application=billing` và `application=shipping`, hoặc dùng domain riêng. Chỉ dùng `IGNORE_EXISTING` nếu cố ý để một WAR không đăng ký endpoint của nó.

### Kịch bản C: redeploy trong cùng JVM

Ứng dụng cũ bị undeploy nhưng MBean chưa được unregister; phiên bản mới đăng ký cùng ObjectName rồi lỗi. Nên sửa lifecycle cleanup, bảo đảm owner unregister đúng các MBean đã đăng ký. Không giải quyết bằng `REPLACE_EXISTING` vô điều kiện vì có thể che leak hoặc xóa MBean còn đang được dùng.

### Kịch bản D: hai module cùng muốn điều khiển một scheduler

Thay vì mỗi module export `com.example:type=Scheduler,name=Main`, có thể tạo một management adapter singleton do module scheduler sở hữu. Các module khác đọc thông tin từ adapter hoặc dùng service API nội bộ. Cách này có một nguồn sự thật và một lifecycle owner.

## 16. Những lỗi và hiểu nhầm phổ biến

| Triệu chứng | Nguyên nhân có thể | Hướng giải quyết |
| --- | --- | --- |
| `InstanceAlreadyExistsException` khi startup | ObjectName đã có | Đọc registry, xác định owner, đổi tên hoặc sửa vòng đời |
| App B khởi động bình thường nhưng không có MBean riêng | Dùng `IGNORE_EXISTING` và tên bị A chiếm | Dùng tên độc lập thay vì dựa vào bỏ qua đăng ký |
| Dashboard trỏ ObjectName đúng nhưng số liệu sai ứng dụng | `REPLACE_EXISTING` hoặc monitoring không phân biệt server | Kiểm tra connector và ownership, tránh replace không chủ đích |
| MBean mất khi một context shutdown | Xung đột ownership hoặc lifecycle cleanup | Chỉ một owner cho mỗi đăng ký, tránh chia sẻ tên |
| Trùng sau khi đổi thứ tự `type` và `name` | Hai ObjectName vẫn bằng nhau | Thay đổi domain hoặc giá trị property thật sự |
| Trùng khi bật thêm `@EnableMBeanExport` | Có nhiều exporter cùng đăng ký | Chọn một chiến lược export hoặc tách rõ phạm vi |
| MBean chỉ xuất hiện ở một JVM | Tool kết nối server khác | Kiểm tra service URL và MBeanServer đích |
| MBean cũ còn sau redeploy | Unregister không đầy đủ | Sửa lifecycle, tránh giữ reference/classloader cũ |

## 17. Quy tắc thiết kế thực tế

1. **Thiết kế namespace trước**: chọn domain và bộ key properties đủ phân biệt những MBean cùng xuất hiện trong một server.
2. **Một ObjectName, một owner**: chỉ một thành phần chịu trách nhiệm đăng ký và hủy đăng ký.
3. **Ưu tiên báo lỗi khi tên trùng ngoài dự kiến**: dùng `FAIL_ON_EXISTING` thay cho replace âm thầm.
4. **Không dùng `IGNORE_EXISTING` để che lỗi thiết kế**: nó có thể làm ứng dụng mất endpoint quản trị riêng.
5. **Không tự thay thế MBean của ứng dụng khác**: `REPLACE_EXISTING` phải là quyết định có chủ ý và được kiểm soát.
6. **Phân biệt server với tên**: cùng ObjectName trên hai JVM riêng thường không xung đột.
7. **Giữ ObjectName ổn định**: client JMX thường phụ thuộc vào tên để polling và gọi operation.
8. **Kiểm soát exporter trùng**: Spring XML, Java config, annotation-based export và thư viện có thể cùng đăng ký.
9. **Đăng ký và cleanup nhất quán**: đặc biệt quan trọng với plugin, hot reload và nhiều ApplicationContext.
10. **Bảo vệ JMX connector**: naming độc lập với authentication/authorization; một tên duy nhất không tự bảo vệ operation nhạy cảm.

## 18. Mô hình tư duy tổng kết

```text
Hai ứng dụng muốn export MBean
              |
              v
      Chúng có chung MBeanServer?
          /              \
        Không             Có
         |                 |
  Tên giống nhau       So ObjectName canonical
  thường không         và ownership
  gây collision            |
                       +---+---+
                       |       |
                    Khác tên  Trùng tên
                       |       |
                    đăng ký   sửa namespace/
                    riêng     chọn owner
                                 |
                         RegistrationPolicy
                         FAIL / IGNORE / REPLACE
                         chỉ là hành vi đăng ký
```

**Ghi nhớ:** Tránh hai ứng dụng cùng chiếm một ObjectName bằng cách **thiết kế naming rõ ràng, phân biệt đúng phạm vi MBeanServer, kiểm soát exporter và chỉ định một lifecycle owner cho mỗi MBean**. `RegistrationPolicy` xử lý xung đột lúc đăng ký, nhưng không thay thế kiến trúc naming/ownership. Trong production, đừng để `REPLACE_EXISTING` âm thầm biến MBean của ứng dụng A thành endpoint của ứng dụng B.
