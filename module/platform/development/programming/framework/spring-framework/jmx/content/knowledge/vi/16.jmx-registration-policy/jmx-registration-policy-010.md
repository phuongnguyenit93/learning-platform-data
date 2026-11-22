# Chọn chính sách đăng ký MBean theo môi trường và mức an toàn

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **registration policy** trong Spring Framework JMX và tại sao `ObjectName` trùng nhau có thể làm quá trình export MBean thất bại.
- Phân biệt ba lựa chọn `FAIL_ON_EXISTING`, `IGNORE_EXISTING` và `REPLACE_EXISTING` của `RegistrationPolicy`.
- Đánh giá từng policy theo **môi trường** (local, test, staging, production) và **mức an toàn** (tránh chiếm dụng tên của MBean khác, ổn định lifecycle, giữ nguyên management contract).
- Hiểu rằng registration policy chỉ chi phối **xử lý xung đột khi đăng ký**, không phải cơ chế authentication, authorization hay transaction rollback.
- Thiết kế quy ước ownership của `ObjectName`, exporter, MBeanServer và vòng đời unregister.
- Viết cấu hình Spring và integration test để phát hiện conflict thay vì che lỗi.
- Lập kế hoạch thay thế MBean có kiểm soát khi cần nâng cấp implementation hoặc metadata.

## 2. Bối cảnh: vì sao MBean registration có thể xung đột?

Trong Java Management Extensions (JMX), một MBean được đăng ký với `MBeanServer` dưới một `ObjectName` cụ thể:

```text
com.example.shop.orders:type=Queue,name=outbox
```

Trong **một MBeanServer**, không thể có hai MBean đồng thời giữ cùng một ObjectName cụ thể. Nếu bean đã tồn tại và có code đăng ký một bean khác cùng tên, JMX thông thường báo `InstanceAlreadyExistsException`.

Trong Spring, `MBeanExporter` giúp đưa Spring beans ra MBeanServer. Khi có xung đột, exporter có thể áp dụng một **registration policy** để quyết định báo lỗi, bỏ qua bean mới hoặc thay thế bean đang đăng ký.

Ví dụ sơ đồ:

```text
Spring ApplicationContext
    |
    +-- Exporter A --> QueueMonitor A
    |                    |
    |                    v
    |       com.example.shop.orders:type=Queue,name=outbox
    |
    +-- Exporter B --> QueueMonitor B
                         |
                         v
              cùng ObjectName, cùng MBeanServer
                         |
                         v
                  REGISTRATION CONFLICT
```

Xung đột có thể đến từ hai exporter, hai bean được đánh dấu `@ManagedResource` cùng tên, auto-configuration cộng với mapping thủ công, hoặc một instance MBean tồn tại sẵn trong MBeanServer.

**Vấn đề quyết định:** Khi phát hiện xung đột, ứng dụng nên **dừng và báo cấu hình sai**, **giữ MBean đang có**, hay **thay thế MBean cũ**?

## 3. Ba registration policy trong Spring

Spring cung cấp enum `org.springframework.jmx.support.RegistrationPolicy`, với ba policy phổ biến:

| Policy | Khi ObjectName chưa được đăng ký | Khi ObjectName đã tồn tại | Ý nghĩa vận hành |
|---|---|---|---|
| `FAIL_ON_EXISTING` | Đăng ký bean mới | Báo lỗi registration | Phát hiện cấu hình trùng; ưu tiên tính rõ ràng |
| `IGNORE_EXISTING` | Đăng ký bean mới | Giữ MBean hiện có, bỏ qua đăng ký mới | Không làm gián đoạn MBean đang tồn tại |
| `REPLACE_EXISTING` | Đăng ký bean mới | Cố gắng thay MBean hiện có bằng MBean mới | Chủ đích chuyển quyền sở hữu ObjectName |

Đây là mô tả ngữ nghĩa của policy khi Spring exporter xử lý tình huống ObjectName đã bị chiếm. Chi tiết ngoại lệ và lifecycle vẫn phụ thuộc MBeanServer, loại MBean, cấu hình exporter và phiên bản Spring.

### 3.1. FAIL_ON_EXISTING

Đây là hướng **fail fast**: xung đột được hiển thị thay vì che giấu.

```text
ObjectName chưa tồn tại -> register
ObjectName đã tồn tại   -> fail
```

Nó phù hợp khi một ObjectName cần một owner duy nhất và việc trùng tên là lỗi cấu hình phải sửa. Trong test, staging hoặc production có yêu cầu chặt chẽ về management contract, fail fast giúp tránh trường hợp dashboard kết nối nhầm MBean.

**Lưu ý:** Một lỗi đăng ký JMX có thể làm startup của Spring context thất bại tùy cách exporter/bean lifecycle xử lý exception. Điều này là tradeoff cần hiểu nếu JMX không phải thành phần tối quan trọng cho nghiệp vụ.

### 3.2. IGNORE_EXISTING

Nếu tên đã tồn tại, exporter có thể bỏ qua bean mới và để MBean cũ tiếp tục được đăng ký:

```text
ObjectName chưa tồn tại -> register
ObjectName đã tồn tại   -> giữ MBean cũ
```

Điều này có thể hữu ích khi một MBean được cung cấp sẵn bởi container hoặc thư viện và ứng dụng không muốn chiếm tên. Tuy nhiên, consumer JMX sẽ thấy **implementation/metadata của MBean đã tồn tại**, không nhất thiết là bean bạn vừa cấu hình.

Nguy cơ:

- Cấu hình mới có `@ManagedAttribute` nhưng client vẫn đọc metadata cũ.
- Một lỗi naming hoặc export trùng bị che giấu.
- Môi trường A register trước MBean X, môi trường B register trước MBean Y; cả hai cùng tên nhưng kết quả khác.
- Team tưởng bean vừa viết đã export thành công vì context không lỗi.

Vì vậy `IGNORE_EXISTING` không nên được dùng như cách chữa mọi `InstanceAlreadyExistsException`.

### 3.3. REPLACE_EXISTING

Policy này yêu cầu exporter thay MBean đang giữ tên bằng bean mới. Một luồng khái niệm:

```text
ObjectName đã tồn tại
     |
     v
unregister MBean hiện có
     |
     v
register MBean mới
```

Hậu quả có thể gồm:

- Client JMX đang dùng MBean cũ có thể thấy khoảng trống hoặc lỗi ngắn khi thay thế.
- MBean cũ có thể nhận callbacks/lifecycle effects khi unregister.
- Metadata attributes/operations thay đổi đột ngột, làm hỏng monitoring.
- Nếu MBean mới đăng ký thất bại sau khi unregister, tên có thể không còn MBean hợp lệ.
- Hai exporter cạnh tranh có thể tạo hành vi phụ thuộc thứ tự startup.

**Điểm đặc biệt quan trọng:** `REPLACE_EXISTING` không phải một phép migration nguyên tử, không có rollback tự động và không tự chứng minh bạn có quyền thay MBean của component khác.

## 4. Registration policy không đồng nghĩa với bảo mật JMX

Các từ `FAIL`, `IGNORE`, `REPLACE` mô tả cách xử lý **name collision**, không mô tả cấp quyền cho JMX client.

Registration policy không tự cung cấp:

- Authentication cho client JMX remote.
- TLS hoặc mã hóa network.
- Authorization theo role của từng operation.
- Audit log cho action quản trị.
- Validation payload/parameters của management operation.
- Quyền sở hữu pháp lý/organizational của ObjectName.
- Bảo đảm transaction hoặc rollback khi thay MBean.

Một ứng dụng dùng `FAIL_ON_EXISTING` vẫn có thể expose operation nhạy cảm nếu connector JMX không được bảo vệ. Và một ứng dụng dùng `IGNORE_EXISTING` vẫn có thể gặp vấn đề bảo mật nếu MBean cũ có API nguy hiểm.

**Mức an toàn** khi chọn policy cần được hiểu theo ít nhất hai tầng: an toàn của *registry/metadata* và an toàn của *đường truy cập/operation*.

## 5. Hiểu đúng phạm vi ObjectName

Một ObjectName có dạng:

```text
domain:key=value,key2=value2
```

Ví dụ:

```text
com.example.shop.orders:type=Queue,name=outbox
```

Tính duy nhất khi đăng ký được xét trong **MBeanServer**, không trên toàn cluster. Hai JVM ở hai pod khác nhau có thể đăng ký cùng ObjectName trong hai platform MBeanServers độc lập mà không gây conflict.

Vì vậy, trước khi đổi policy do nghĩ “production có nhiều replicas”, hãy hỏi:

1. Các replicas có thực sự dùng **cùng một MBeanServer** không?
2. Hay mỗi JVM có platform MBeanServer riêng?
3. Có exporter nào trong cùng JVM cố đăng ký trùng không?
4. Có MBean của container, thư viện hoặc Actuator dùng cùng ObjectName không?
5. Có hai ApplicationContexts/child contexts export cùng bean vào một server không?

Đừng đưa pod name/instance ID ngẫu nhiên vào ObjectName chỉ để chữa xung đột giữa JVM độc lập. Tên động có thể phá vỡ dashboard và alert rules.

## 6. Chọn policy theo mục tiêu vận hành

| Mục tiêu | Hướng thường phù hợp | Giải thích |
|---|---|---|
| Muốn phát hiện cấu hình export trùng | `FAIL_ON_EXISTING` | Lỗi được hiển thị ngay |
| MBean được quản lý bởi một owner duy nhất | `FAIL_ON_EXISTING` | Tránh thay hoặc bỏ qua bean bất ngờ |
| Tích hợp môi trường có MBean có sẵn và muốn ưu tiên owner cũ | `IGNORE_EXISTING` có kiểm soát | Không ghi đè owner hiện hành |
| Chủ đích thay thế MBean cũ của chính mình | `REPLACE_EXISTING` có quy trình | Cần kế hoạch lifecycle/metadata |
| Không rõ nguồn xung đột | Không dùng replace để che lỗi | Điều tra object name/owner trước |
| Production quan trọng, cần contract có thể dự đoán | Thường ưu tiên fail fast hoặc export owner rõ | Tránh kết quả phụ thuộc thứ tự startup |
| Cần chạy song song hai phiên bản management API | ObjectName/version khác nhau hoặc migration rõ ràng | Không đè cùng tên tình cờ |

Bảng này là hướng dẫn thực hành, không phải luật bắt buộc của Spring. Nếu hệ thống yêu cầu application không được ngừng khởi động chỉ vì JMX conflict, có thể chọn chính sách khác với **giám sát và kiểm chứng** tương ứng.

## 7. Khuyến nghị theo môi trường

### 7.1. Local development

Mục tiêu là phản hồi nhanh, dễ phát hiện nguyên nhân.

Một lựa chọn tốt thường là **`FAIL_ON_EXISTING`**:

- Developer thấy ngay exporter hoặc bean nào đăng ký trùng.
- Không âm thầm sử dụng MBean của lần chạy/config khác.
- Có động lực sửa ObjectName và ownership rõ ràng.

Trong một môi trường local thử nghiệm hot reload hoặc embedded container đặc biệt, có thể có registration tồn dư. Đừng tự động chuyển sang replace vĩnh viễn mà chưa hiểu vì sao lifecycle không unregister đúng.

### 7.2. Automated test / CI

Thường nên dùng **`FAIL_ON_EXISTING`** để kiểm chứng:

- Chỉ một exporter sở hữu mỗi ObjectName.
- Test context cleanup đúng.
- Không bị xung đột giữa suites chạy cùng JVM/MBeanServer.
- ObjectName và contract ổn định.

Nếu nhiều tests dùng chung platform MBeanServer, hãy thiết kế test isolation (MBeanServer riêng, unique ObjectName test hoặc cleanup đầy đủ). Dùng `REPLACE_EXISTING` trong tests có thể che lỗi rò rỉ MBean giữa test cases.

### 7.3. Staging

Staging nên phản ánh **chính sách production dự kiến** và giúp kiểm tra deployment/migration. Nếu production dùng fail fast, staging cũng nên phát hiện trùng tên. Nếu production có logic replacement được thiết kế, staging cần thử lỗi giữa chừng, client đang kết nối và dashboard tương thích.

Dùng staging để xác nhận:

- Có bao nhiêu exporters hoạt động sau auto-configuration.
- MBeanServer nào được sử dụng.
- ObjectName đầy đủ của mỗi MBean.
- `MBeanInfo` có đúng attributes/operations.
- Logs/metrics thể hiện registration conflict thế nào.
- Rollback deployment có khôi phục management endpoints không.

### 7.4. Production

Production cần ưu tiên **tính dự đoán được** và giảm tác động ngoài ý muốn.

Trong đa số hệ thống có owner rõ ràng, `FAIL_ON_EXISTING` là điểm xuất phát dễ kiểm toán vì không tự lấy hoặc bỏ qua một ObjectName đã được component khác dùng. Nhưng nếu lỗi JMX làm application startup thất bại và business availability là ưu tiên cao, cần thiết kế cách xử lý phù hợp với availability objective: ví dụ đảm bảo cấu hình trùng đã bị chặn ở CI/staging, tách management component hoặc có policy ignore kèm cảnh báo và xác minh rõ nguồn existing MBean.

Không dùng `REPLACE_EXISTING` làm mặc định chỉ vì “đỡ lỗi khi deploy”. Nó có thể thay MBean không thuộc quyền quản lý của exporter và gây đứt quãng monitoring.

## 8. Spring configuration: khai báo registrationPolicy

Ví dụ một exporter quản lý một Standard MBean:

```java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

@Configuration
public class JmxConfiguration {

    @Bean
    MBeanExporter queueExporter(QueueMonitorMBean queueMonitor) {
        MBeanExporter exporter = new MBeanExporter();

        exporter.setBeans(Map.of(
                "com.example.shop.orders:type=Queue,name=outbox",
                queueMonitor));

        exporter.setRegistrationPolicy(
                RegistrationPolicy.FAIL_ON_EXISTING);

        return exporter;
    }
}
```

Giả định `QueueMonitorMBean` là management interface hợp lệ, có implementation phù hợp và là Spring bean. Mapping có một ObjectName tường minh, exporter duy nhất.

Nếu bean được Spring proxy, cần kiểm tra JMX compliance/metadata và method exposure. Chỉ đặt `setRegistrationPolicy` không giải quyết proxy hoặc annotation lookup.

### Bản Standard MBean tối giản

```java
public interface QueueMonitorMBean {
    int getPendingCount();
}

public class QueueMonitor implements QueueMonitorMBean {
    @Override
    public int getPendingCount() {
        return 5;
    }
}
```

Đây là cặp interface/implementation theo convention Standard MBean. Nếu triển khai qua Spring, cần khai báo `QueueMonitor` là bean và gắn exporter phù hợp.

### Dùng environment property

Có thể lấy chính sách từ Spring `Environment`/configuration thay vì hardcode:

```java
import org.springframework.core.env.Environment;
import org.springframework.jmx.support.RegistrationPolicy;

RegistrationPolicy policy = RegistrationPolicy.valueOf(
        environment.getRequiredProperty(
                "app.jmx.registration-policy"));
```

Ví dụ file cấu hình:

```yaml
app:
  jmx:
    registration-policy: FAIL_ON_EXISTING
```

Cách này yêu cầu validation và xử lý lỗi cấu hình từ startup. Không nên cho ứng dụng production tự chuyển fallback sang `REPLACE_EXISTING` khi giá trị property không hợp lệ.

Trong dự án dùng Spring Boot, kiểm tra exporter auto-configuration hiện có trước khi tự tạo `MBeanExporter`. Có thể không cần tạo exporter thủ công nếu framework đã quản lý bean export.

## 9. Chọn chính sách với annotation-driven export

Giả sử có Spring bean:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.shop.catalog:type=Cache,name=products",
    description = "Product cache")
public class ProductCacheManagement {

    @ManagedAttribute
    public int getEntryCount() {
        return 42;
    }
}
```

Với annotation-driven JMX, exporter/assembler phát hiện managed resource và đăng ký `ObjectName`. Registration policy vẫn liên quan **sự trùng ObjectName**, không liên quan nội dung attribute.

Nếu hai bean cùng khai báo:

```text
com.example.shop.catalog:type=Cache,name=products
```

thì:

- `FAIL_ON_EXISTING` báo conflict.
- `IGNORE_EXISTING` có thể giữ MBean đã đăng ký trước.
- `REPLACE_EXISTING` có thể thay MBean hiện có bằng bean được export sau.

Chúng không có phép hợp nhất annotation/metadata. Nếu MBean mới có `getHitRate()` mà MBean cũ không có, chọn ignore không làm attribute đó xuất hiện.

## 10. Khi nào IGNORE_EXISTING là lựa chọn có chủ đích?

Một trường hợp tương đối hợp lý: ứng dụng chạy trong container đã đăng ký một MBean hạ tầng và bạn muốn bảo toàn MBean đó, trong khi exporter có mapping trùng do convention.

Quy trình:

1. Xác định **owner hiện tại** của ObjectName.
2. Đọc `MBeanInfo` để biết attributes/operations được công bố.
3. Xác nhận bean mới có thể được bỏ qua mà **không mất chức năng giám sát cần thiết**.
4. Đặt `IGNORE_EXISTING` như một policy rõ ràng, có tài liệu.
5. Ghi log/metric về tình huống đã bỏ qua để vận hành nhận biết.
6. Test các môi trường khởi động khác nhau để tránh behavior phụ thuộc thứ tự.

Không nên chỉ viết:

```java
exporter.setRegistrationPolicy(
        RegistrationPolicy.IGNORE_EXISTING);
```

rồi coi mọi conflict đã được xử lý đúng. Một exporter khởi động trước có thể chiếm tên; exporter khác khởi động sau bị bỏ qua. Kết quả có thể khác giữa local và production.

## 11. Khi nào REPLACE_EXISTING có thể được cân nhắc?

Một tình huống có chủ đích: cùng một owner quản lý một MBean đã đăng ký và cần thay bằng implementation mới trong một runtime có lifecycle đặc biệt.

Điều kiện nên có:

- Ownership của ObjectName được xác nhận.
- Không có thành phần bên thứ ba giữ tên.
- MBean cũ có thể unregister an toàn.
- Client chịu được một khoảng không có MBean hoặc thay đổi metadata.
- MBean mới đã được kiểm tra bằng test và môi trường staging.
- Có quy trình recovery nếu register mới thất bại.
- Cảnh báo/giám sát có thể phát hiện mất MBean sau replacement.
- Không có hai exporter liên tục tranh quyền đăng ký.

Nếu không thể thỏa các điều kiện này, hãy ưu tiên thiết kế **ObjectName versioned** hoặc migration hai pha.

### Rủi ro rollback

Một số người lầm tưởng REPLACE_EXISTING “đăng ký mới thất bại thì MBean cũ trở lại”. Đây không phải bảo đảm chung. Vì vậy trước migration cần có bản kế hoạch có thể tái đăng ký/khôi phục component cũ, và nên test thất bại giữa chừng.

## 12. Một nguồn đăng ký: phòng ngừa tốt hơn policy

Registration policy chỉ giải quyết khi conflict **đã xảy ra**. Thiết kế tốt hơn là phòng ngừa conflict.

Một convention nên quy định:

- Mỗi ObjectName có một **registration owner**.
- Mỗi MBean có một nguồn management metadata chính: interface, MXBean hoặc annotation assembler.
- Domain phản ánh sản phẩm/module, key property phản ánh type/name.
- Chỉ một exporter hoặc một điểm `MBeanServer.registerMBean` được phép sở hữu ObjectName.
- Các exporter auto và manual không cùng export một bean mà không có chủ đích.
- Unregister gắn với lifecycle component.
- Các integration tests kiểm tra tập ObjectNames được đăng ký và contract.

Ví dụ:

```text
ObjectName:
com.example.shop.orders:type=Queue,name=outbox

Contract owner:
OrderQueueManagement

Export owner:
Spring JMX exporter (annotation-driven)

Registration policy:
FAIL_ON_EXISTING

Consumer:
JConsole + exporter metrics
```

Đây là dữ liệu kiến trúc có thể ghi vào tài liệu dự án; không nhất thiết cần một file registry quản lý phức tạp, nhưng quy tắc ownership phải rõ.

## 13. Kiểm tra conflict trực tiếp qua MBeanServer

Một đoạn Java có thể kiểm tra ObjectName đã tồn tại:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class RegistrationInspection {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
                "com.example.shop.orders:type=Queue,name=outbox");

        System.out.println("Registered: "
                + server.isRegistered(name));
    }
}
```

Kết quả `true` cho biết đã có MBean ở tên đó trong server được hỏi. Nó không tự xác định owner hoặc implementation Java cụ thể.

Đọc metadata:

```java
import javax.management.MBeanInfo;

MBeanInfo info = server.getMBeanInfo(name);

System.out.println(info.getClassName());
System.out.println(info.getDescription());
```

`MBeanInfo` giúp quan sát contract được công bố, nhưng class name hoặc description chưa đủ để xác thực ownership. Nếu muốn xác định nguồn registration, phải đối chiếu cấu hình exporter, logs startup và lifecycle.

**Race condition:** `isRegistered(name)` trước `registerMBean` không tạo atomic check-and-register. Một thread/exporter khác vẫn có thể đăng ký sau lần check. Registration policy và thiết kế owner mới quyết định hành vi khi conflict thực sự diễn ra.

## 14. Integration test: FAIL_ON_EXISTING

Mục tiêu: tạo một MBeanServer cô lập, đăng ký MBean đầu tiên rồi thử đăng ký lần nữa dưới cùng ObjectName.

Ví dụ Java thuần:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

public class DuplicateRegistrationDemo {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
                MBeanServerFactory.createMBeanServer("test");

        ObjectName name = new ObjectName(
                "com.example.test:type=QueueMonitor,name=main");

        server.registerMBean(new QueueMonitor(), name);

        try {
            server.registerMBean(new QueueMonitor(), name);
            throw new AssertionError("Expected duplicate registration failure");
        } catch (javax.management.InstanceAlreadyExistsException expected) {
            System.out.println("Duplicate ObjectName rejected");
        } finally {
            server.unregisterMBean(name);
        }
    }
}
```

Ví dụ này minh họa hành vi cơ sở của `MBeanServer`, chưa gọi `MBeanExporter`. Để test policy Spring, cần khởi động Spring exporter dùng cùng MBeanServer và set policy phù hợp, sau đó xác định bean nào thực sự được đăng ký.

Với `FAIL_ON_EXISTING`, kỳ vọng conflict không bị che. Test nên xác minh exception/cấu hình theo Spring version, không gắn cứng vào một stack trace cụ thể.

## 15. Integration test: IGNORE_EXISTING

Một integration test Spring nên:

1. Tạo MBeanServer riêng.
2. Đăng ký `MonitorA` dưới tên `com.example.test:type=Monitor,name=main`.
3. Cấu hình `MBeanExporter` để xuất `MonitorB` dưới cùng tên với `IGNORE_EXISTING`.
4. Khởi động exporter.
5. Đọc một attribute định danh contract của MonitorA để xác nhận bean cũ vẫn được giữ.
6. Cleanup context và unregister có kiểm soát.

Điểm cần assert:

```text
Before:
  ObjectName exists -> MonitorA

After IGNORE_EXISTING:
  ObjectName still exists -> MonitorA
  MonitorB was not installed under that name
```

Nếu chỉ assert `isRegistered(name) == true`, test chưa đủ; nó không phân biệt MonitorA và MonitorB. Có thể dùng attribute `Version` với hai giá trị khác nhau hoặc kiểm tra một operation/metadata có riêng ở mỗi contract.

## 16. Integration test: REPLACE_EXISTING

Với policy replace, test cần xác nhận:

1. Trước export, MBean là MonitorA.
2. Sau export, MBean phản ánh MonitorB.
3. Client nhìn thấy metadata mong đợi.
4. Lifecycle callbacks của MBean cũ/mới được xử lý.
5. Nếu registration mới lỗi, hệ thống có cơ chế recovery đã được thiết kế.
6. Các dashboard hoặc consumers có khả năng reconnect/requery.

Sơ đồ:

```text
T0: ObjectName -> MonitorA
T1: exporter REPLACE_EXISTING
T2: ObjectName -> MonitorB
```

Đừng xem replacement test thành công là chứng cứ cho phép dùng policy này trong mọi môi trường. Nó chỉ cho thấy một đường thay thế đã hoạt động trong điều kiện test.

### Chú ý về service availability

MBean replacement có thể làm quản trị/giám sát gián đoạn; tùy client, việc mất MBean làm polling thất bại trong một khoảng ngắn. Nếu ứng dụng cần không gián đoạn cho observability, hãy cân nhắc phiên bản ObjectName mới, hoặc một management facade giữ ObjectName ổn định trong khi thay implementation bên dưới.

## 17. Spring Boot và auto-configuration

Trong ứng dụng Spring Boot, có thể có nhiều cấu hình liên quan JMX:

- JVM platform MBeans.
- Spring `@ManagedResource` beans.
- Actuator endpoints được expose qua JMX tùy configuration.
- MBeanExporter do ứng dụng tự tạo.
- MBeans do thư viện/database pool đăng ký trực tiếp.

Không nên giả định rằng chỉ có một exporter hoặc một MBeanServer. Khi thêm custom exporter, kiểm tra effective configuration và tránh conflict với auto-configuration.

Đặc biệt nếu một thư viện đã đăng ký MBean quản trị connection pool, việc tự đăng ký thêm cùng ObjectName để “thêm attribute” sẽ không tự hợp nhất metadata. Dùng `IGNORE_EXISTING` chỉ giữ lại bản cũ; dùng `REPLACE_EXISTING` có thể làm mất khả năng quản lý của thư viện.

Nên giữ namespace riêng cho custom MBeans:

```text
com.example.shop.orders:type=Queue,name=outbox
com.example.shop.payments:type=PoolMonitor,name=primary
```

Thay vì cố chiếm ObjectName của platform hoặc thư viện.

## 18. Hướng dẫn quyết định chính sách bằng câu hỏi

Trước khi lựa chọn policy, tự trả lời:

**Câu 1. Ai sở hữu ObjectName?**

- Nếu tên thuộc chính module, nên bảo đảm chỉ một owner.
- Nếu tên thuộc thư viện/container, không thay trừ khi API hỗ trợ và được thiết kế rõ.

**Câu 2. Trùng tên có phải một lỗi cấu hình không?**

- Nếu có, `FAIL_ON_EXISTING` giúp phát hiện.
- Nếu không, cần giải thích vì sao bỏ qua hoặc thay thế là đúng.

**Câu 3. MBean mới khác MBean cũ thế nào?**

- Có attributes/operations mới không?
- Có thay đổi kiểu dữ liệu, description, permission hoặc semantics không?
- Dashboard phụ thuộc những field nào?

**Câu 4. Nếu MBean mất trong 1–2 chu kỳ polling, điều gì xảy ra?**

- Collector chỉ log missing data?
- Alert có phát false positive?
- Có operation điều khiển đang chạy hay không?

**Câu 5. Nếu registration mới thất bại, cách khôi phục là gì?**

- Có thể đăng ký lại MBean cũ?
- Có thể rollback deployment?
- Có cần versioned ObjectName?

**Câu 6. Policy đang áp dụng cho những environments nào?**

- CI/test có phát hiện conflict không?
- Staging mô phỏng production không?
- Production có monitoring để phát hiện MBean bị skip hoặc replace không?

Một quyết định policy có chất lượng cần dựa vào các câu trả lời, không chỉ dựa vào “ứng dụng khởi động được”.

## 19. Ví dụ bảng policy nội bộ

Một nhóm có thể ghi bảng quy tắc:

| ObjectName hoặc nhóm MBean | Owner | Environment | Policy | Lý do |
|---|---|---|---|---|
| `com.example.shop.orders:*` | Orders service | test/staging/prod | `FAIL_ON_EXISTING` | Một owner, contract ổn định |
| `com.example.shop.legacy:*` | Legacy adapter | staging/prod | `IGNORE_EXISTING` có kiểm tra | Tôn trọng MBean đã có và cảnh báo skip |
| `com.example.shop.migration:*` | Migration component | staging có kiểm soát | `REPLACE_EXISTING` | Thử chuyển MBean chủ đích |
| JVM platform `java.lang:*` | JVM | mọi môi trường | Không tự export đè | Dùng MBeans chuẩn của platform |

Đây là **ví dụ chính sách nội bộ**, không phải cấu hình mặc định Spring. Trong nhiều dự án, bạn chỉ cần `FAIL_ON_EXISTING` và loại bỏ mọi trường hợp export trùng.

## 20. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách khắc phục |
|---|---|---|
| Startup thất bại với duplicate MBean | Hai exporter/beans cùng ObjectName | Xác định owner, sửa naming, giữ fail fast |
| JConsole thấy metadata cũ | `IGNORE_EXISTING` giữ MBean đã tồn tại | Kiểm tra MBeanInfo và thứ tự registration |
| Dashboard mất attribute sau deploy | `REPLACE_EXISTING` thay contract | Version/migration và compatibility test |
| ObjectName được đăng ký từ thư viện khác | Namespace trùng, custom exporter chiếm tên | Chọn domain của sản phẩm/module |
| Test lúc pass lúc fail | Test contexts chia sẻ platform server | MBeanServer riêng và cleanup đúng |
| Chạy nhiều replicas tưởng bị conflict | Nhầm phạm vi mỗi MBeanServer | Không thêm instance key nếu JVM độc lập |
| MBean mất sau replace lỗi | Không có rollback tự động | Recovery plan, tránh replace vô kiểm soát |
| App startup chậm do JMX | Registration callbacks hoặc exporter chờ | Kiểm tra lifecycle và dependencies |
| Bật ignore để “sửa” lỗi cấu hình | Bỏ qua MBean mới ngoài ý muốn | Cảnh báo skip, giải quyết conflict gốc |
| Có policy đúng nhưng operation vẫn nguy hiểm | Registration policy không là authorization | Cấu hình security và hạn chế operations |

## 21. Bài tập thực hành

### Bài tập 1 — Chọn policy theo tình huống

Bạn có bốn tình huống:

1. Hai team vô tình dùng cùng ObjectName trong một JVM.
2. Container đã sở hữu MBean hệ thống, ứng dụng được yêu cầu giữ nguyên MBean đó.
3. Nhóm platform muốn thay management implementation của chính mình trong thời gian bảo trì có kế hoạch.
4. Test suite có các contexts không dọn registration sau khi test xong.

Hãy chọn policy/giải pháp:

- (1) `FAIL_ON_EXISTING`, sửa ownership/naming.
- (2) `IGNORE_EXISTING` có điều kiện hoặc đổi tên custom MBean để khỏi conflict.
- (3) `REPLACE_EXISTING` có kiểm soát, test migration/lifecycle.
- (4) Tách MBeanServer test và cleanup; không dùng replace để che leak.

### Bài tập 2 — Dự đoán MBeanInfo

Một MBean cũ có attribute `State`. MBean mới có attributes `State`, `QueueDepth`. Nếu ObjectName đã tồn tại:

- `FAIL_ON_EXISTING`: export mới báo lỗi.
- `IGNORE_EXISTING`: client tiếp tục thấy metadata MBean cũ, nên không tự có `QueueDepth`.
- `REPLACE_EXISTING`: client có thể thấy `QueueDepth` sau replacement thành công.

Hãy dùng `MBeanInfo.getAttributes()` để xác minh thay vì chỉ đọc `isRegistered`.

### Bài tập 3 — Thiết kế integration test

Tạo một MBeanServer riêng và hai MBeans có attribute `Version` lần lượt là `"A"` và `"B"`. Lần lượt chạy exporter với mỗi policy trong test context riêng. Assert kết quả và thực hiện cleanup đầy đủ.

### Bài tập 4 — Đánh giá production risk

Một nhóm đề xuất đặt `REPLACE_EXISTING` cho mọi MBeans ở production để tránh startup fail. Hãy liệt kê ít nhất bốn rủi ro và đề xuất alternative:

- Chiếm tên MBean của owner khác.
- Mất metadata/operations cũ.
- Monitoring gián đoạn.
- Không có rollback tự động.
- Hành vi phụ thuộc thứ tự registration.

Alternative: một owner/naming contract, fail fast trong test/staging, migration có kế hoạch hoặc dùng versioned ObjectName.

### Bài tập 5 — Kiểm tra nhiều JVM

Hai pods `orders-1` và `orders-2` cùng đăng ký:

```text
com.example.shop.orders:type=Queue,name=outbox
```

Mỗi pod là một JVM độc lập. Giải thích vì sao không có conflict giữa hai MBeanServers, và tại sao monitoring aggregator vẫn cần phân biệt instance qua target labels.

## 22. Câu hỏi tự kiểm tra

**1. `FAIL_ON_EXISTING` làm gì khi ObjectName đã được đăng ký?**

Nó báo conflict thay vì âm thầm bỏ qua hoặc thay MBean đang có.

**2. `IGNORE_EXISTING` có tạo MBean mới với metadata hợp nhất không?**

Không. Nó giữ MBean đã đăng ký; các attributes/operations mới không được tự hợp nhất.

**3. `REPLACE_EXISTING` có đảm bảo rollback nguyên tử nếu đăng ký mới thất bại không?**

Không có bảo đảm chung như vậy.

**4. Registration policy có bảo vệ operation nhạy cảm khỏi JMX client không?**

Không. Đó là trách nhiệm của security configuration và quyền quản trị riêng.

**5. Hai JVM có cùng ObjectName có tự gây `InstanceAlreadyExistsException` không?**

Không, nếu hai MBeanServers độc lập.

**6. Vì sao `IGNORE_EXISTING` có thể làm lỗi khó phát hiện?**

Vì context có thể không báo lỗi, nhưng bean mới không được export và client tiếp tục thấy MBean cũ.

**7. Trong production, tiêu chí quan trọng hơn “không có startup error” là gì?**

Tính đúng đắn, ổn định, quyền sở hữu MBean, tương thích monitoring và kế hoạch phục hồi.

## 23. Ghi nhớ

- Spring JMX registration policy xác định cách `MBeanExporter` xử lý khi **ObjectName đã tồn tại** trong cùng MBeanServer.
- `FAIL_ON_EXISTING` giúp phát hiện conflict; `IGNORE_EXISTING` giữ MBean cũ; `REPLACE_EXISTING` thay MBean cũ bằng MBean mới theo cơ chế đăng ký.
- Policy không hợp nhất metadata, không làm thay đổi ngữ nghĩa JMX contract và không phải cơ chế security.
- Trong development/CI/staging, fail fast giúp phát hiện configuration và lifecycle mistakes.
- Production cần policy dựa trên ownership, availability objectives và ảnh hưởng khi mất/thay management endpoints, không phải chỉ dựa trên startup success.
- `IGNORE_EXISTING` phù hợp khi cố ý ưu tiên MBean hiện tại và có kiểm chứng/cảnh báo; `REPLACE_EXISTING` chỉ nên dùng khi migration có owner và recovery rõ.
- Mỗi ObjectName cần một registration owner và một management contract nhất quán.
- Kiểm tra `MBeanServer.isRegistered`, `getMBeanInfo` và log export thực tế để xác minh bean nào đang hiện diện.
- Replicas chạy JVM độc lập không xung đột chỉ vì cùng ObjectName; phạm vi duy nhất là từng MBeanServer.

## 24. Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — `RegistrationPolicy`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/support/RegistrationPolicy.html
- Spring Framework Javadoc — `MBeanExporter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Reference — Controlling MBean Registration Behavior: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Java SE 21 — `MBeanServer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
