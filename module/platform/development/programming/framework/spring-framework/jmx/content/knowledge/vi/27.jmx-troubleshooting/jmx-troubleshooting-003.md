# Chẩn đoán trùng ObjectName khi khởi động hoặc redeploy trong Spring Framework JMX

## 1. Hiện tượng và mục tiêu

Trong Spring Framework JMX, `MBeanExporter` đăng ký Spring-managed bean vào `MBeanServer` dưới một `ObjectName`. Khi một tên đã có MBean chiếm giữ, việc đăng ký thêm MBean khác với cùng tên sẽ không thành công theo chính sách đăng ký đang áp dụng. Tình huống này thường xuất hiện lúc startup, restart context, hot reload hoặc redeploy ứng dụng trong cùng JVM.

Thông điệp liên quan có thể chứa `javax.management.InstanceAlreadyExistsException`, `UnableToRegisterMBeanException`, tên `ObjectName` trùng và stack trace từ Spring `MBeanExporter`/`MBeanRegistrationSupport`. Một số hệ thống không báo lỗi khởi động nhưng MBean mới lại không xuất hiện vì `RegistrationPolicy.IGNORE_EXISTING` bỏ qua registration; đây cũng là dấu hiệu cần chẩn đoán.

Bài này hướng dẫn:

- Hiểu ranh giới duy nhất của ObjectName trong từng MBeanServer.
- Phân biệt trùng tên do **hai exporter đang sống**, do **MBean cũ còn sau redeploy** và do **tên sinh sai**.
- Kiểm tra ObjectName thật trong registry thay vì suy đoán từ tên Spring bean.
- Xử lý an toàn bằng naming convention, ownership và lifecycle cleanup.
- Lựa chọn `RegistrationPolicy` mà không che lỗi hoặc vô tình thay MBean của ứng dụng khác.
- Đề phòng memory leak, classloader leak, và sai dữ liệu giám sát sau khi redeploy.

**Nguyên tắc xử lý:** không gọi `unregisterMBean` hoặc bật `REPLACE_EXISTING` một cách mù quáng chỉ để startup qua. Trước tiên phải xác định MBean hiện hữu do ai sở hữu và vì sao nó chưa được dọn dẹp.

## 2. ObjectName phải duy nhất trong một MBeanServer

Cú pháp ObjectName:

```text
domain:key1=value1,key2=value2,...
```

Ví dụ:

```text
com.example.jobs:type=WorkerPool,name=Main
```

Trong **một** MBeanServer, chỉ có một MBean đang đăng ký với tên này. Nhưng ở hai JVM hoặc hai MBeanServer khác nhau, cùng tên vẫn có thể tồn tại mà không gây xung đột registry.

| Trường hợp | Có thể trùng registry? |
| --- | --- |
| Hai MBeanExporter trong cùng Spring context, cùng server, cùng ObjectName | Có |
| Parent và child ApplicationContext cùng đăng ký một MBean vào platform MBeanServer | Có |
| Hai WAR trong cùng app server dùng chung MBeanServer | Có |
| Phiên bản cũ chưa unregister rồi phiên bản mới đăng ký cùng tên | Có |
| Hai JVM độc lập cùng tên nhưng dùng MBeanServer riêng | Không xung đột trực tiếp |
| Hai MBeanServer khác nhau trong cùng JVM | Không trùng ở cùng registry, nhưng có thể gây nhầm client |

Không lấy tên bean trong Spring, ví dụ `workerPool`, để suy ra xung đột. Quyết định nằm ở ObjectName cuối cùng: hai bean Spring khác tên vẫn có thể được export dưới một ObjectName duy nhất.

## 3. Luồng lỗi phổ biến khi redeploy

```text
First deployment
  ApplicationContext A
       |
       +-- MBeanExporter -> register ObjectName X
       |                         |
       |                         v
       |                      MBeanServer
       |
       +-- shutdown/redeploy
              |
              +-- expected: unregister X
              +-- bug: X still registered

Second deployment
  ApplicationContext B
       |
       +-- MBeanExporter -> register ObjectName X
                                  |
                                  v
                     InstanceAlreadyExistsException
```

Không phải mọi trường hợp tên trùng đều do unregister thất bại. Cũng có thể bản triển khai mới tạo **hai exporter** cùng startup, hoặc cùng một exporter nhận hai bean với naming strategy trùng nhau. Vì vậy phải phân biệt **trùng ngay lần start đầu** với **trùng chỉ sau restart/redeploy**.

## 4. Triệu chứng giúp khoanh vùng

| Triệu chứng | Nghi vấn ưu tiên |
| --- | --- |
| Startup lần đầu đã lỗi | Hai exporter/bean cùng ObjectName, hoặc MBean nền tảng đã chiếm tên |
| Start đầu thành công, redeploy lần hai lỗi | Cleanup/unregister không chạy hoặc registry còn MBean cũ |
| Chỉ xảy ra khi bật `@EnableMBeanExport` | Annotation-based exporter trùng exporter thủ công/XML |
| Chỉ xảy ra với một profile | Cấu hình naming/domain hoặc bean definitions khác giữa profile |
| Không báo exception nhưng MBean hiển thị dữ liệu cũ | `IGNORE_EXISTING` giữ MBean cũ |
| Lúc nào cũng thấy MBean của phiên bản mới, nhưng ứng dụng khác mất MBean | Có thể đang `REPLACE_EXISTING` |
| Hai môi trường chạy hai JVM khác nhau đều dùng cùng tên | Không phải collision trực tiếp nếu server riêng |
| JConsole thấy MBean nhưng code `isRegistered` trả false | Kết nối tới MBeanServer khác hoặc ObjectName sai |

## 5. Đọc đúng nguyên nhân từ log

Ví dụ stack trace minh họa:

```text
org.springframework.jmx.export.UnableToRegisterMBeanException:
  Unable to register MBean [workerPoolManagement]
  with key 'com.example.jobs:type=WorkerPool,name=Main'
Caused by: javax.management.InstanceAlreadyExistsException:
  com.example.jobs:type=WorkerPool,name=Main
```

Cần ghi lại ba thông tin: **ObjectName bị trùng**, **exporter/context đang đăng ký** và **MBeanServer đích**. Không nên chỉ thấy `InstanceAlreadyExistsException` rồi lập tức xóa tên. Nên tìm xem error xảy ra trên lần đăng ký đầu, sau reload hay khi nhiều module khởi tạo cùng lúc.

Trong log, thông điệp chính xác có thể khác theo Spring Framework/JDK version. Điều quan trọng là exception chain, ObjectName và giai đoạn lifecycle.

## 6. Tìm MBean hiện hữu bằng API JMX

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.jobs:type=WorkerPool,name=Main"
);

System.out.println("registered=" + server.isRegistered(name));

if (server.isRegistered(name)) {
    MBeanInfo info = server.getMBeanInfo(name);
    System.out.println("class=" + info.getClassName());
    System.out.println("attributes=" + info.getAttributes().length);
    System.out.println("operations=" + info.getOperations().length);
}
```

Đoạn code giả định exporter dùng platform MBeanServer. Nếu ứng dụng có dedicated MBeanServer, phải dùng đúng instance hoặc `MBeanServerConnection` tương ứng. MBeanInfo cho biết contract đang đăng ký nhưng không luôn chỉ ra chính xác application/classloader owner, nhất là với ModelMBean hoặc AOP proxy.

Có thể query theo domain:

```java
import java.util.Set;

Set<ObjectName> names = server.queryNames(
    new ObjectName("com.example.jobs:*") ,
    null
);
for (ObjectName item : names) {
    System.out.println(item.getCanonicalName());
}
```

Không đọc toàn bộ attribute values để chẩn đoán tên: một số getter có thể trả secrets/PII hoặc làm công việc nặng. Metadata và tên canonical thường đủ cho bước đầu.

## 7. Kiểm tra tên canonical để tránh nhầm thứ tự key

```text
com.example.jobs:type=WorkerPool,name=Main
com.example.jobs:name=Main,type=WorkerPool
```

Hai chuỗi trên mô tả cùng một ObjectName. Thứ tự key property không làm thay đổi định danh JMX.

```java
ObjectName a = new ObjectName(
    "com.example.jobs:type=WorkerPool,name=Main"
);
ObjectName b = new ObjectName(
    "com.example.jobs:name=Main,type=WorkerPool"
);
System.out.println(a.equals(b)); // true
System.out.println(a.getCanonicalName());
```

Nếu naming strategy sinh hai chuỗi khác thứ tự nhưng cùng key/value, vẫn trùng. Cũng cần kiểm tra khác biệt chữ hoa/thường và những giá trị đã được quote bằng `ObjectName.quote`.

## 8. Kiểm tra các nguồn MBeanExporter

Spring application có thể có nhiều hạ tầng JMX:

- `@EnableMBeanExport` tạo annotation-based exporter.
- Java `@Bean` tự tạo `MBeanExporter` và `setBeans(...)`.
- XML `<context:mbean-export/>` hoặc `<bean class="org.springframework.jmx.export.MBeanExporter">`.
- Framework/module khác hoặc application server đăng ký MBean riêng.
- Spring Boot Actuator có JMX endpoint exporter ngoài các custom MBeans.

Chạy nhiều cơ chế không tự động là lỗi; lỗi xảy ra khi chúng đăng ký **cùng ObjectName trên cùng MBeanServer**. Cần thiết kế ownership: mỗi MBean có một exporter chịu trách nhiệm.

Ví dụ anti-pattern: cùng context vừa dùng `@EnableMBeanExport` vừa cấu hình exporter thủ công để xuất cùng adapter dưới tên giống nhau. Khi đó một hạ tầng có thể đã đăng ký target trước khi hạ tầng kia thực hiện registration.

Không nên tắt tất cả JMX export để né lỗi nếu hệ thống vẫn cần monitoring. Hãy loại duplicate registration hoặc tách ObjectName rõ ràng.

## 9. RegistrationPolicy: hành vi khi tên đã tồn tại

Spring hỗ trợ `org.springframework.jmx.support.RegistrationPolicy`:

| Policy | Khi MBean cùng ObjectName đã đăng ký | Điều cần lưu ý |
| --- | --- | --- |
| `FAIL_ON_EXISTING` | Báo lỗi thay vì thay thế | Giúp phát hiện collision ngoài dự kiến |
| `IGNORE_EXISTING` | Giữ MBean cũ, bỏ qua registration mới | Ứng dụng mới có thể không có MBean riêng, data có thể cũ |
| `REPLACE_EXISTING` | Thay MBean đang đăng ký bằng MBean mới | Có nguy cơ chiếm endpoint của ứng dụng khác |

Ví dụ:

```java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

@Bean
public MBeanExporter exporter(WorkerPoolManagement management) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setBeans(Map.of(
        "com.example.jobs:type=WorkerPool,name=Main",
        management
    ));
    exporter.setRegistrationPolicy(
        RegistrationPolicy.FAIL_ON_EXISTING
    );
    return exporter;
}
```

`FAIL_ON_EXISTING` là lựa chọn tốt để phát hiện sự cố thay vì che xung đột. Với `IGNORE_EXISTING`, cần chắc chắn MBean hiện có chính là MBean mà client được phép dùng. Với `REPLACE_EXISTING`, cần có ownership và kế hoạch thay thế rõ ràng; không chọn chỉ vì “redeploy sẽ không lỗi nữa”.

## 10. Phân biệt tên trùng do naming và do leak

### 10.1. Naming collision

Hai service khác nhau vô tình dùng một tên chung:

```text
com.example:type=Cache,name=Main
```

Khắc phục bằng namespace phân biệt:

```text
com.example.billing:type=Cache,name=Main
com.example.shipping:type=Cache,name=Main
```

Hoặc thêm key:

```text
com.example.services:application=billing,type=Cache,name=Main
com.example.services:application=shipping,type=Cache,name=Main
```

### 10.2. Lifecycle leak sau redeploy

Ứng dụng cũ đã dừng nhưng MBean cũ còn trong server chung. Cần sửa unregister/cleanup của owner cũ. Nếu MBean còn giữ reference đến class của WAR cũ, nó có thể ngăn garbage collection của classloader.

### 10.3. Double registration

Cùng một target được export qua hai `MBeanExporter`, hoặc đăng ký bằng JMX API trực tiếp và qua Spring. Cần chọn một owner, không đăng ký kép.

### 10.4. Sai MBeanServer

Exporter A dùng platform server, exporter B dùng dedicated server. Hai server có ObjectName giống nhau không xung đột; nếu log/quản trị tool nhìn sang server khác, có thể chẩn đoán nhầm “đã tồn tại” hoặc “không tồn tại”.

## 11. Cleanup khi Spring context đóng

`MBeanExporter` quản lý lifecycle của những MBean nó export và thông thường unregister khi Spring context đóng đúng cách. Nhưng sự cố có thể xuất hiện nếu:

- Context không được đóng khi redeploy/hot reload.
- Một MBean được đăng ký thủ công nhưng không có matching unregister.
- Bean bị tạo trong context phụ rồi context owner không dừng đúng cách.
- Nhiều exporter làm mờ ownership của cùng ObjectName.
- MBeanServer dùng chung còn giữ MBean của application cũ.
- Process bị terminate bất thường: với JVM chết hoàn toàn, registry trong JVM đó cũng mất; vấn đề “MBean cũ còn” chỉ áp dụng nếu JVM/server tiếp tục sống.

Đối với container có nhiều WAR chạy trên cùng JVM, cần quan sát lifecycle của riêng WAR, không nhầm với việc toàn bộ JVM restart.

## 12. Quản lý MBean thủ công phải unregister tương ứng

Ví dụ JMX thuần:

```java
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class RegistrationOwner implements AutoCloseable {
    private final MBeanServer server;
    private final ObjectName name;
    private boolean owned;

    public RegistrationOwner(
            MBeanServer server, ObjectName name) {
        this.server = server;
        this.name = name;
    }

    public synchronized void register(Object mbean) throws Exception {
        if (owned) {
            throw new IllegalStateException("Already registered by owner");
        }
        server.registerMBean(mbean, name);
        owned = true;
    }

    @Override
    public synchronized void close() throws Exception {
        if (owned) {
            server.unregisterMBean(name);
            owned = false;
        }
    }
}
```

Đoạn code minh họa ownership cho một lifecycle owner. MBean phải là Standard MBean/MXBean/DynamicMBean phù hợp. Nếu một thành phần khác có thể replace tên giữa lúc register và close, chỉ theo dõi boolean `owned` chưa đủ để chứng minh object hiện tại vẫn thuộc owner; trong hệ thống shared server cần ngăn replacement trái phép hoặc phối hợp ownership rõ hơn.

Không sử dụng ví dụ này để unregister MBean đã có sẵn khi owner chưa từng đăng ký thành công.

## 13. Check-then-register không loại được race condition

Anti-pattern:

```java
if (!server.isRegistered(name)) {
    server.registerMBean(bean, name);
}
```

Hai thread hoặc hai exporter có thể cùng thấy `false`, sau đó chỉ một bên đăng ký thành công. `isRegistered` là phép kiểm tra snapshot, không khóa registry để dành tên.

Do đó:

- Để thao tác `registerMBean` quyết định trùng tên và xử lý exception cụ thể.
- Thiết kế naming duy nhất ngay từ đầu.
- Điều phối ownership khi một MBean phải là singleton trong shared server.
- Tránh retry register/unregister liên tục để “giành tên”.

Nếu MBean cũ vẫn đang thực sự được phục vụ, xóa nó để tạo chỗ cho MBean mới có thể gây sai dữ liệu và phá client đang dùng endpoint cũ.

## 14. Thứ tự startup và shutdown

Một số lỗi chỉ xảy ra khi modules chạy song song:

```text
Module A start ------ register X ------ OK
Module B start ------ register X ------ collision
```

Với redeploy:

```text
Old module stop ------ unregister X (expected)
New module start ----- register X
```

Nếu bước unregister chưa xong hoặc không xảy ra, có thể lỗi. Không nên chỉ thêm sleep hoặc tăng timeout để che vấn đề. Cần xác định sequence lifecycle của server/container và đảm bảo owner dừng trước khi owner mới đăng ký cùng tên.

Khi dùng Spring `@DependsOn`, có thể kiểm soát thứ tự khởi tạo bean trong **một** context, nhưng không biến nó thành cơ chế phối hợp ownership giữa hai context hoặc hai WAR độc lập.

## 15. MBeanInfo và classloader leak

Một MBean cũ tồn tại sau redeploy có thể giữ object reference tới implementation, annotation metadata, listener hoặc classloader của ứng dụng cũ. Triệu chứng bao gồm:

- JConsole vẫn thấy ObjectName dù WAR cũ đã undeploy.
- MBeanInfo cho thấy description/class cũ hoặc dữ liệu cũ.
- Memory usage tăng sau nhiều lần redeploy.
- Lỗi class loading/serialization từ JMX client.
- Listener cũ tiếp tục nhận notification hoặc gọi vào resource đã dừng.

Để tránh leak:

1. Dùng exporter/lifecycle owner được quản lý bởi Spring.
2. Bảo đảm `ApplicationContext.close()`/shutdown hook hoặc container lifecycle được thực thi.
3. Remove notification listeners do ứng dụng tự đăng ký.
4. Shutdown executors hoặc background tasks liên quan MBean.
5. Không giữ static references tới application objects trên server/global registries.

Không dựa vào GC để tự unregister MBean. MBeanServer giữ reference mạnh tới các đối tượng đăng ký cho tới khi chúng được unregister hoặc server bị hủy.

## 16. Chẩn đoán nếu thấy MBean cũ nhưng không biết owner

Quy trình điều tra có kiểm soát:

1. Xác nhận đúng JVM/MBeanServer từ log và tooling.
2. Lấy canonical ObjectName đang tồn tại.
3. Đọc MBeanInfo an toàn; không dump tất cả attribute values.
4. Tìm nơi trong cấu hình app khai báo exporter/naming của tên đó.
5. Xác định context/application/version đã đăng ký trong lifecycle.
6. Xem có duplicate exporter hoặc manual `registerMBean` hay không.
7. Kiểm tra shutdown hooks/undeploy logs để xác định unregister đã chạy chưa.
8. Chỉ khi xác minh ownership mới quyết định unregister/redeploy hoặc sửa naming.

Có thể thêm attribute quản trị không nhạy cảm như `ApplicationId`, `DeploymentVersion` hoặc `InstanceId` vào management adapter để chẩn đoán, nhưng không bắt buộc và không nên lộ credentials hay dữ liệu cá nhân.

## 17. Lựa chọn tên ổn định cho nhiều ứng dụng

ObjectName nên phân biệt:

- `application`: ứng dụng/microservice khi cùng server.
- `type`: loại MBean.
- `name`: vai trò hoặc component.
- `instance`: chỉ khi nhiều instance cùng server cần tên riêng.

Ví dụ:

```text
com.example.services:application=billing,type=Queue,name=Main
com.example.services:application=shipping,type=Queue,name=Main
```

Không nhất thiết thêm PID, timestamp hoặc UUID ngẫu nhiên vào tên trong mỗi deployment; client và dashboard thường cần ObjectName ổn định. Nếu replica chạy ở các JVM riêng, cùng ObjectName có thể được dùng ở mỗi server mà không có xung đột.

## 18. Tránh làm hỏng monitoring khi sửa tên

Khi đổi ObjectName để sửa collision, những client sau có thể bị ảnh hưởng:

- `MBeanProxyFactoryBean` đang dùng `setObjectName(...)`.
- JMX collectors đang query theo domain/key cụ thể.
- JConsole bookmarks hoặc scripts `getAttribute/invoke`.
- Alert rules và dashboards.
- Notification listener registrations.

Vì vậy naming fix là thay đổi management API. Cần đồng bộ config client/server và có kế hoạch migration phù hợp. Không đổi domain tùy tiện cho mỗi lần start chỉ để loại lỗi trùng nếu có thể sửa ownership/lifecycle gốc.

## 19. Những sai lầm cần tránh

| Sai lầm | Vì sao nguy hiểm |
| --- | --- |
| Chuyển mọi exporter sang `IGNORE_EXISTING` | App mới có thể không được export, monitoring vẫn đọc dữ liệu cũ |
| Dùng `REPLACE_EXISTING` ở production mặc định | Có thể chiếm endpoint của app khác và phá lifecycle |
| `unregisterMBean` mọi tên trùng khi startup | Xóa MBean không thuộc quyền sở hữu |
| Đổi thứ tự key properties | Hai ObjectName vẫn bằng nhau |
| Thêm `Thread.sleep` trước register | Che race, không giải quyết ownership |
| Xem bean name là ObjectName | Naming strategy có thể sinh tên khác |
| Chỉ test cold start | Không phát hiện leak/hot reload issue |
| Dump toàn bộ attributes trong log | Có thể lộ secrets và trigger getter nặng |
| Chỉ nhìn một JMX connection | Có thể đang kiểm tra sai server/JVM |

## 20. Checklist vận hành

- [ ] Xác định MBeanServer đích của exporter.
- [ ] Xác định canonical ObjectName bị trùng.
- [ ] Phân biệt lỗi cold start với lỗi chỉ sau redeploy.
- [ ] Tìm tất cả exporter/manual registration của ObjectName.
- [ ] Kiểm tra parent-child context, WAR/modules và Boot Actuator nếu có.
- [ ] Xác nhận MBean hiện hữu thuộc owner nào trước khi unregister.
- [ ] Dùng `FAIL_ON_EXISTING` trong các trường hợp cần phát hiện conflict.
- [ ] Thiết kế namespace application/type/name/instance hợp lý.
- [ ] Bảo đảm context shutdown và exporter unregister đúng lifecycle.
- [ ] Remove listeners, stop executors và dọn references sau redeploy.
- [ ] Cập nhật client JMX nếu tên thay đổi.
- [ ] Kiểm tra cold start và repeated redeploy ở môi trường thử nghiệm.

## 21. Mô hình xử lý nhanh

```text
Startup / redeploy throws InstanceAlreadyExistsException
                    |
                    v
            Confirm MBeanServer
                    |
                    v
             Canonical ObjectName
                    |
                    v
           Query registered MBean
                    |
          +---------+----------+
          |                    |
   Existing active owner    Old stale registration
          |                    |
   Fix naming / one owner   Fix shutdown / unregister
          |                    |
          +---------+----------+
                    |
          Verify stable registration
                    |
              Update clients if renamed
```

**Kết luận:** lỗi trùng tên lúc startup hoặc redeploy cần được xử lý như một vấn đề **ObjectName identity + MBeanServer scope + lifecycle ownership**. Hãy xác nhận MBean hiện hữu trên đúng server, phân biệt duplicate exporter với stale registration, sửa naming hoặc cleanup gốc, và chỉ unregister/replace khi đã xác minh quyền sở hữu. `RegistrationPolicy` là cách điều khiển hành vi lúc đăng ký, không phải cách thay thế thiết kế namespace và quản lý vòng đời.
