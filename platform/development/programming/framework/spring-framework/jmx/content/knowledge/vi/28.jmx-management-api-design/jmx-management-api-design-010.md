# Rà soát management surface trước khi phát hành — Spring Framework JMX

## 1. Mục đích của bài học

Khi ứng dụng Spring Framework đưa bean lên Java Management Extensions (JMX), nó tạo thêm một **management surface**: tập hợp các MBean, attribute, operation, notification và đường kết nối mà công cụ quản trị có thể truy cập. Một thay đổi tưởng như nhỏ — ví dụ thêm `@ManagedOperation` để xóa cache hoặc cho phép ghi một `@ManagedAttribute` — có thể mở ra khả năng thay đổi trạng thái runtime nằm ngoài API nghiệp vụ thông thường.

Vì vậy, trước khi phát hành, nhóm phát triển và vận hành cần **rà soát management surface** cũng như rà soát REST API, cấu hình bảo mật hoặc migration database. Không chỉ hỏi “JMX đã chạy chưa?”, cần hỏi “JMX đang công bố gì, ai truy cập được, tác động đến đâu và có kế hoạch vận hành/thu hồi hay không?”.

Mục tiêu:

- Xác định các thành phần tạo nên management surface của Spring JMX.
- Lập danh mục ObjectName, attribute, operation, notification, connector.
- Phân loại mức độ nhạy cảm và tác dụng phụ của API quản trị.
- Kiểm tra naming, metadata, bảo mật, quyền truy cập và vòng đời MBean.
- Kiểm tra hợp đồng và khả năng tương thích với công cụ giám sát.
- Đưa ra checklist release gate và kế hoạch xác minh sau triển khai.
- Phân biệt rà soát management API với kiểm thử API nghiệp vụ hoặc việc bật Actuator endpoint.

## 2. Management surface gồm những gì?

```text
Ứng dụng Spring Framework
  |
  +-- Bean nghiệp vụ hoặc bean vận hành
  |    +-- @ManagedResource
  |    +-- @ManagedAttribute
  |    +-- @ManagedOperation
  |
  +-- MBeanExporter
  |    +-- ObjectNamingStrategy
  |    +-- MetadataMBeanInfoAssembler
  |    +-- RegistrationPolicy
  |
  +-- MBeanServer
       +-- ObjectName / MBeanInfo
       +-- Attributes (read-only hoặc writable)
       +-- Operations (có thể có side effect)
       +-- Notifications và listeners
       |
       +-- JMXConnectorServer / management agent
            +-- local access
            +-- remote JMX / authentication / TLS / network
```

Management surface có ít nhất hai chiều:

1. **Bề mặt chức năng**: những tên MBean và khả năng thực sự được công bố.
2. **Bề mặt tiếp cận**: client nào có thể kết nối, đọc, ghi hoặc gọi operation.

Một MBean chỉ chứa chỉ số đọc khác về rủi ro với MBean có operation thay đổi config, xóa cache hoặc tạm dừng luồng xử lý. Cùng một MBean cũng khác mức rủi ro nếu chỉ dùng local trong JVM so với được expose qua JMX Remote trong mạng rộng.

## 3. Inventory trước khi phát hành

Đầu tiên, ghi nhận các MBean mà ứng dụng có chủ đích sở hữu. Ví dụ:

| ObjectName | Attribute | Operation | Mục đích |
| --- | --- | --- | --- |
| `com.example.ops:type=QueueMonitor,name=Main` | `ActiveJobs`, `QueuedJobs` | Không | Theo dõi queue |
| `com.example.ops:type=CacheControl,name=Products` | `EntryCount` | `evictKey` | Bảo trì cache |
| `com.example.ops:type=WorkerControl,name=Primary` | `AcceptingJobs` | `pause`, `resume` | Kiểm soát worker |
| `com.example.ops:type=ConfigMonitor,name=Main` | `ConfigVersion` | `reload` | Quản trị cấu hình |

Inventory nên ghi thêm owner, môi trường xuất hiện, server đích, client tiêu thụ, quyền đọc/ghi, side effect, tần suất gọi và cách phục hồi.

Với những thư viện tự đăng ký MBean, phân biệt MBean **do ứng dụng sở hữu** với MBean **do JVM/container/thư viện sở hữu**. Không được tự unregister hoặc thay thế MBean của thành phần khác chỉ để “làm sạch” danh sách.

### 3.1. Không xem tên bean Spring là tên JMX

Spring bean có thể tên `cacheControl`, nhưng JMX ObjectName là:

```text
com.example.ops:type=CacheControl,name=Products
```

Tên cuối cùng có thể đến từ `@ManagedResource(objectName=...)`, key trong `MBeanExporter.setBeans(...)` hoặc naming strategy. Inventory phải dùng **ObjectName thực tế**, không suy từ tên class hoặc tên Spring bean.

## 4. Khám phá surface bằng MBeanServer

Một cách rà soát chính xác là truy vấn registry JMX ở môi trường tương ứng.

```java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

Set<ObjectName> names = server.queryNames(
    new ObjectName("com.example.ops:*"),
    null
);

for (ObjectName name : names) {
    System.out.println(name.getCanonicalName());
}
```

Nếu ứng dụng dùng `MBeanServerFactoryBean` tạo server riêng, phải query trên **đúng server mà `MBeanExporter` đăng ký vào**. Platform server không tự chứa mọi MBeanServer khác trong cùng JVM.

Để đọc interface quản trị:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = server.getMBeanInfo(objectName);

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.printf(
        "ATTRIBUTE %s type=%s read=%s write=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable()
    );
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.printf(
        "OPERATION %s returns=%s impact=%d%n",
        op.getName(),
        op.getReturnType(),
        op.getImpact()
    );
}
```

`MBeanInfo` trả metadata của API JMX mà client nhìn thấy. Chỉ xem annotation trong source code có thể bỏ sót trường hợp exporter sử dụng assembler khác hoặc một MBean được đăng ký thủ công.

## 5. Phân loại attribute trước release

Attribute JMX có thể là chỉ đọc, chỉ ghi hoặc đọc/ghi tùy metadata. Một checklist thực dụng:

| Thuộc tính | Câu hỏi |
| --- | --- |
| Tên và type | Client đang dựa vào `int`, `long`, `String` hay kiểu khác? |
| Readable | Getter có tiết lộ dữ liệu nhạy cảm không? |
| Writable | Ai được phép thay đổi? Có validation không? |
| Giá trị runtime | Getter có tốn tài nguyên hoặc blocking không? |
| Metadata | Description và unit có rõ ràng không? |
| Compatibility | Đổi tên/kiểu có phá monitoring script không? |

Ví dụ:

```java
@ManagedAttribute(
    description = "Number of currently active background jobs"
)
public int getActiveJobs() {
    return activeJobs.get();
}
```

Đây là một attribute đọc phục vụ quan sát. Ngược lại:

```java
@ManagedAttribute(
    description = "Enable or disable intake of new jobs"
)
public void setAcceptingJobs(boolean enabled) {
    controlService.setAcceptingJobs(enabled);
}
```

là một entry point thay đổi trạng thái. Dù setter trông giống JavaBean thông thường, qua JMX nó có thể được gọi bởi operator hoặc client được quyền kết nối. Vì vậy phải có phân quyền, điều kiện tiền đề và kết quả quan sát được.

### 5.1. Không công bố secrets hoặc dữ liệu cá nhân

Một getter như `getDatabasePassword()` hoặc `getAccessToken()` không nên trở thành JMX attribute. Điều tương tự áp dụng với connection string chứa credentials, dữ liệu khách hàng, session token và nội dung request nhạy cảm.

Nếu cần hiển thị thông tin cấu hình, ưu tiên trạng thái phi nhạy cảm:

```text
databaseConnected = true
credentialSource = "vault"
lastCredentialRotationEpoch = ...
```

Thay vì giá trị bí mật thực tế. JMX client và tooling có thể lưu hoặc log attribute, nên dữ liệu quản trị cần được thiết kế như một contract có thể được thu thập bởi hệ thống vận hành.

## 6. Phân loại operation theo side effect

Operation JMX có thể chỉ đọc hoặc thay đổi trạng thái. Metadata `MBeanOperationInfo.getImpact()` có thể mô tả đặc điểm informational/action, nhưng đây **không phải cơ chế authorization** và không tự bảo đảm method không có side effect.

Trước release, mỗi operation cần trả lời:

- Có thể gây mất dữ liệu, xóa cache hoặc thay đổi luồng xử lý không?
- Có ảnh hưởng toàn JVM hay chỉ một module/instance?
- Có thay đổi persisted configuration không hay chỉ state trong memory?
- Gọi lặp có an toàn không?
- Operation chạy đồng bộ, bất đồng bộ hay kích hoạt job dài hạn?
- Nếu timeout, làm sao xác minh đã thực thi chưa?
- Có rollback, cancel hoặc recovery procedure không?
- Có được audit theo actor và target không?

Ví dụ operation có side effect:

```java
@ManagedOperation(
    description = "Evict one product cache key"
)
public void evictProduct(String productId) {
    if (productId == null || productId.isBlank()) {
        throw new IllegalArgumentException("productId is required");
    }
    cacheMaintenance.evictProduct(productId);
}
```

Ngay cả operation giới hạn một key cũng cần cân nhắc cache miss, tải backend và nguồn dữ liệu. Một `evictAll()` có blast radius lớn hơn và cần điều kiện vận hành nghiêm ngặt hơn.

## 7. Tách operation điều khiển khỏi business API

Các hành động nghiệp vụ như thanh toán, cấp quyền người dùng, điều chỉnh giá hoặc xóa dữ liệu khách hàng thường có contract và authorization riêng trong HTTP/gRPC/message API.

Không nên export trực tiếp:

```java
@ManagedOperation
public void approvePayment(String paymentId) {
    paymentService.approve(paymentId);
}
```

chỉ vì thao tác tiện trong JConsole. Điều này có thể tạo đường vòng ngoài kiểm soát authentication, authorization theo tài khoản, approval workflow, idempotency key và audit của business API.

Nếu muốn quản trị một job nghiệp vụ, nên thiết kế control plane chuyên biệt. JMX có thể công bố **trạng thái** hoặc một operation hẹp đã được phê duyệt, không biến thành business API bí mật.

Một nguyên tắc thiết kế: **MBean adapter nên mỏng, chỉ delegate vào service chịu trách nhiệm validation và invariant**. Điều này giúp cùng logic được sử dụng đúng cách mà không nhân đôi các quy tắc trong annotation.

## 8. Đánh giá remote connector và network exposure

Có `MBeanServer` không đồng nghĩa có remote connector. Ngược lại, khi JMX Remote được bật, đây là một kênh quản trị cần xem xét như control plane.

Rà soát:

1. JMX endpoint đang bind trên interface nào?
2. Connector có thể truy cập từ subnet hoặc Internet nào?
3. Có yêu cầu authentication không?
4. TLS hoặc kênh mã hóa phù hợp đã bật chưa?
5. Có cơ chế authorization đọc/ghi/gọi operation không?
6. Cấu hình RMI registry và RMI server port có rõ không?
7. Hostname trong RMI stub có reachable đúng mạng quản trị không?
8. Credentials có được quản lý qua secrets system không?
9. Có log audit hoặc giới hạn truy cập theo môi trường không?
10. Quy trình thu hồi endpoint khi không cần đã xác định chưa?

Không nên mở public JMX port chỉ để phục vụ JConsole. Nếu có nhu cầu vận hành từ xa, ưu tiên VPN, bastion, tunnel hoặc network path có kiểm soát và tuân theo security policy.

### 8.1. Nhiều server trong một JVM

Ứng dụng có thể có platform MBeanServer và private MBeanServer. Phải biết connector nào trỏ vào server nào. Khi JConsole thấy JVM MXBeans nhưng không thấy một managed bean Spring, nguyên nhân có thể là exporter đăng ký vào server khác chứ không phải annotation sai.

### 8.2. Domain không phải security boundary

Hai ObjectName:

```text
com.example.orders:type=WorkerControl,name=Main
com.example.payments:type=WorkerControl,name=Main
```

có domain khác nhau nhưng vẫn có thể được cùng một client nhìn thấy nếu cùng server và quyền truy cập cho phép. Domain giúp naming/namespace, không tạo isolation bảo mật.

## 9. Registration policy và quyền sở hữu ObjectName

Spring `MBeanExporter` có cơ chế xử lý đăng ký trùng ObjectName, ví dụ các chính sách fail, ignore hoặc replace existing.

Trước release, kiểm tra:

- Mỗi ObjectName có owner rõ ràng.
- Không có hai exporter cùng export một bean hoặc hai bean cùng tên.
- Không vô tình bật annotation exporter và exporter thủ công cho cùng resource.
- Không dùng replace để ghi đè MBean của container/thư viện.
- Không dùng ignore để che một MBean sai đã tồn tại.
- Có quy tắc namespace ổn định theo app, module và instance.
- Nếu chạy nhiều Spring contexts trong cùng JVM, các context không tranh chấp cùng ObjectName.

Mặc định fail khi trùng tên thường là lựa chọn an toàn để lộ cấu hình sai. Thay đổi policy chỉ nên được chấp thuận khi hiểu ownership, client impact và lifecycle.

## 10. Metadata và compatibility contract

JMX client có thể phụ thuộc vào:

- `ObjectName` đầy đủ.
- Attribute name, type, readable/writable.
- Operation name và parameter signature.
- Return type và lỗi đã định nghĩa.
- Notification type và metadata.
- MBean descriptor fields hoặc description nếu tooling có đọc.

Đổi:

```text
com.example.ops:type=QueueMonitor,name=Main
```

thành:

```text
com.example.monitoring:type=QueueMonitor,name=Main
```

không chỉ đổi nhãn: đó là đổi identity của MBean.

Tương tự, đổi getter:

```java
public int getActiveJobs()
```

thành:

```java
public long getActiveJobs()
```

thay type từ `int` sang `long`. Client đang cast `Integer` có thể hỏng. Những thay đổi này nên được xử lý như thay đổi API contract: cập nhật client, dashboard, alert, automation và tài liệu.

### 10.1. Description và default metadata

Description giúp operator hiểu attribute/operation. Giá trị `defaultValue` trong Spring metadata, nếu được dùng, là mô tả mặc định và không tự khởi tạo state của bean. Trong release review, cần kiểm tra metadata không làm người vận hành hiểu sai “default” thành “current”.

## 11. Notification, listener và tài nguyên dài hạn

Một MBean có thể phát notification để thông báo thay đổi trạng thái. Trước release, xác minh:

- Notification type có tên và semantics rõ.
- Listener được đăng ký ở đâu, do ai sở hữu.
- Listener có được gỡ khi context/connector đóng không.
- Notification không chứa secrets hoặc dữ liệu cá nhân.
- Tốc độ phát notification có thể gây quá tải không.
- Client có xử lý mất kết nối/reconnect và missed event không.
- Nếu cần độ tin cậy cao, có cơ chế durable event khác hay không.

JMX notification thường là kênh quản trị **không nên mặc định dùng làm event bus nghiệp vụ bền vững**. Client mất kết nối có thể bỏ lỡ sự kiện nếu không có cơ chế bổ sung.

Trong application server hoặc môi trường redeploy, broadcaster/listener giữ tham chiếu tới bean cũ có thể dẫn đến classloader leak. Lifecycle phải được review đồng thời với notification.

## 12. Hiệu năng và độ bền của management API

Không phải getter JMX nào cũng rẻ. Ví dụ:

```java
@ManagedAttribute
public List<String> getAllSessionIds() {
    return sessionRepository.findEverySessionId();
}
```

Một getter như vậy có thể tiêu thụ bộ nhớ, tăng tải database và lộ dữ liệu nếu được polling thường xuyên. Các công cụ giám sát có thể gọi attribute mỗi vài giây, biến một phép đọc tưởng như vô hại thành tải nền liên tục.

Một management API phù hợp nên:

- Ưu tiên giá trị tổng hợp, số đếm hoặc snapshot nhỏ.
- Tránh truy vấn toàn bộ dữ liệu và thao tác blocking dài.
- Có timeout/caching phù hợp cho phép đo đắt.
- Không giữ lock rộng khi JMX client đọc trạng thái.
- Tránh trả object graph hoặc collection khổng lồ.
- Dùng kiểu dữ liệu quản trị đơn giản và ổn định.

Nếu cần dump dữ liệu lớn, cân nhắc job có kiểm soát và trả reference đến artifact được quản lý bảo mật, thay vì đổ toàn bộ dữ liệu ra một JMX attribute.

## 13. Concurrency và tính nhất quán runtime

JMX operation có thể được gọi đồng thời với HTTP request, scheduler và các JMX client khác.

Ví dụ, operator gọi `pauseProcessing()` trong khi một thread đang nhận job mới. Chỉ có một `volatile boolean` có thể không đảm bảo quy tắc mạnh “không nhận thêm job nào sau khi pause trả về” nếu phần kiểm tra và phần nhận job không được đồng bộ theo contract.

Rà soát:

1. State transition có hợp lệ và atomic không?
2. Getter hiển thị trạng thái hiện tại có nhất quán với operation không?
3. Có race giữa pause/resume/stop không?
4. Operation có thể được gọi lặp lại không?
5. Nếu timeout sau khi gửi lệnh, client xác minh kết quả bằng cách nào?
6. Có cần expected version hoặc compare-and-set để tránh lost update không?
7. Những thao tác dài có làm nghẽn JMX connector/thread khác không?

Với tác vụ kéo dài, nên cân nhắc operation chỉ **nhận yêu cầu**, trả request ID, rồi công bố `Running`, `LastOutcome`, `ErrorCount` hoặc notification để theo dõi.

## 14. Vòng đời Spring ApplicationContext và redeploy

`MBeanExporter` thường tham gia vòng đời Spring để đăng ký/hủy những MBean do nó quản lý. Khi context đóng, cần xác nhận:

- MBean của ứng dụng đã unregister.
- Listener và connector do ứng dụng tạo đã được dọn.
- Không còn thread/executor giữ bean cũ.
- Không còn ObjectName từ deployment trước làm deployment mới fail.
- Không có registration policy replace/ignore che vấn đề ownership.

Trong một JVM chứa nhiều ứng dụng, platform MBeanServer có vòng đời dài hơn một web application. MBean cũ còn đăng ký có thể giữ tham chiếu tới classloader cũ và gây memory leak.

Không nên tự quét và unregister toàn bộ MBean cùng domain nếu có thành phần khác cũng sở hữu resource. Quy trình cleanup phải dựa vào danh mục ownership.

## 15. Kiểm thử management surface trước khi release

Thay vì chỉ kiểm tra Spring context chạy được, viết test dựa trên `MBeanInfo`.

Ví dụ:

```java
import java.util.Arrays;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.ops:type=QueueMonitor,name=Main"
);

MBeanInfo info = server.getMBeanInfo(name);

Map<String, MBeanAttributeInfo> attrs =
    Arrays.stream(info.getAttributes())
        .collect(Collectors.toMap(
            MBeanAttributeInfo::getName,
            Function.identity()
        ));

MBeanAttributeInfo active = attrs.get("ActiveJobs");

if (active == null || !active.isReadable() ||
        active.isWritable() || !"int".equals(active.getType())) {
    throw new AssertionError("Unexpected ActiveJobs JMX contract");
}
```

Kiểm thử có thể xác nhận:

- ObjectName tồn tại trên đúng MBeanServer.
- Attribute cần thiết có mặt và đúng type/readability/writability.
- Getter nhạy cảm không bị export.
- Operation cần thiết có signature hợp lệ.
- Operation nguy hiểm hoặc method nội bộ không xuất hiện.
- Notification type đúng như contract.
- Hủy Spring context làm sạch đăng ký do exporter sở hữu.

Dùng test MBeanServer riêng để tránh xung đột ObjectName trên platform server. Khi kiểm thử operation có side effect, chỉ dùng môi trường và fixture cô lập.

## 16. Test danh sách operation, tránh expose nhầm

Ví dụ assert một method nội bộ không xuất hiện trong JMX metadata:

```java
import java.util.Arrays;
import javax.management.MBeanOperationInfo;

boolean unsafeExposed =
    Arrays.stream(info.getOperations())
        .map(MBeanOperationInfo::getName)
        .anyMatch("deleteAllOrders"::equals);

if (unsafeExposed) {
    throw new AssertionError(
        "Unsafe business method exposed via JMX"
    );
}
```

Với operation được cho phép, test signature và return type nếu đó là hợp đồng quan trọng. Không nên gọi chính operation nguy hiểm để kiểm tra nó có tồn tại; chỉ đọc `MBeanInfo` đã đủ cho kiểm thử metadata.

### 16.1. Positive và negative contract

Có hai loại assertion:

- **Positive contract:** các attribute/operation mong đợi phải xuất hiện.
- **Negative contract:** các method/attribute nhạy cảm không được xuất hiện.

Một kiểm thử release tốt có thể có cả hai. Chỉ test những gì “phải có” sẽ không phát hiện trường hợp exporter vô tình công bố tất cả public methods, bao gồm những method không được phép.

## 17. Kiểm tra remote accessibility mà không hạ bảo mật

Khi release thực sự có JMX Remote, cần kiểm thử từ vị trí mạng được phép:

1. Client được phép có thể kết nối và đọc MBean cần thiết.
2. Client không được phép bị từ chối phù hợp.
3. TLS/authentication vận hành đúng.
4. Policy phân biệt quyền đọc và quyền gọi operation nếu hệ thống có cơ chế đó.
5. Hostname/port trong RMI stub reachable từ vị trí operator.
6. Remote connector trỏ đúng MBeanServer.
7. Không có endpoint JMX công khai ngoài ý muốn.

Không nên dùng giải pháp “tắt auth/SSL tạm” rồi quên bật lại. Cũng không nên mở JMX RMI tới Internet chỉ để hoàn thành kiểm thử từ máy cá nhân.

Nếu tổ chức dùng VPN/bastion/tunnel, phải kiểm tra RMI registry và server endpoint qua chính đường kết nối đó.

## 18. Release checklist theo từng lớp

### Lớp A — Registry và naming

- [ ] Đã xác định MBeanServer và ownership của mọi resource.
- [ ] ObjectName duy nhất, ổn định, có namespace ứng dụng.
- [ ] Không có duplicate exporter hoặc cấu hình registration policy mơ hồ.
- [ ] Không có MBean cũ giữ lại sau redeploy.

### Lớp B — Metadata và contract

- [ ] Đã liệt kê mọi attribute, operation, notification dự kiến.
- [ ] Attribute có type, read/write và description đúng.
- [ ] Không có attribute/operation nhạy cảm bị công bố ngoài ý muốn.
- [ ] Naming/return/signature thay đổi có migration plan cho client.
- [ ] Notification listener/metadata được kiểm tra khi cần.

### Lớp C — Quyền và bảo mật

- [ ] Connector chỉ accessible từ vùng mạng được phép.
- [ ] Authentication và mã hóa phù hợp đã cấu hình.
- [ ] Có policy cho read/write/invoke theo quyền.
- [ ] Credentials không hard-code hoặc bị đưa vào log.
- [ ] Có audit phù hợp với operation có side effect.

### Lớp D — An toàn vận hành

- [ ] Operation thay đổi trạng thái có validation và giới hạn phạm vi.
- [ ] Cơ chế retry/idempotency/timeout được mô tả.
- [ ] Tác vụ lâu có trạng thái theo dõi.
- [ ] Có rollback/recovery hoặc phương án giảm thiểu rủi ro.
- [ ] Getter/operation không gây tải không kiểm soát.

### Lớp E — Kiểm thử và phát hành

- [ ] Test MBeanInfo xác nhận positive và negative contracts.
- [ ] Test lifecycle unregister sau khi context đóng.
- [ ] Kiểm thử JMX Remote trên môi trường có security tương đương.
- [ ] Có runbook cho kết nối, lỗi và thay đổi trạng thái.
- [ ] Có bước post-deploy verification trên đúng MBeanServer.

## 19. Review matrix có chủ sở hữu

Một bảng review giúp tránh việc “đã review” nhưng không ai chịu trách nhiệm các rủi ro cụ thể.

| Mục rà soát | Người chịu trách nhiệm gợi ý | Bằng chứng cần có |
| --- | --- | --- |
| ObjectName và compatibility | Dev/maintainer | Snapshot MBeanInfo, changelog |
| Operation có side effect | Dev + SRE | Runbook, test giới hạn, rollback |
| Network/TLS/auth | Platform/Security | Cấu hình endpoint, access review |
| Monitoring/alert | SRE/Observability | Dashboard/alert integration test |
| Lifecycle và cleanup | Dev + Platform | Redeploy/integration test |
| Documentation | Maintainer | README hoặc runbook cập nhật |

Vai trò có thể thay đổi theo tổ chức. Điểm quan trọng là **mỗi mục có owner và evidence rõ**, không chỉ một chữ ký phê duyệt chung.

## 20. Quy trình trước và sau phát hành

### 20.1. Trước phát hành

1. Chốt phiên bản JMX contract và liệt kê thay đổi.
2. Dựng ứng dụng trong test/staging với cấu hình MBeanServer và exporter gần production.
3. Truy vấn `MBeanInfo` và lưu snapshot những thông tin cần kiểm tra.
4. Chạy test negative surface để tìm method/attribute ngoài ý muốn.
5. Kiểm tra auth/TLS/network từ client được phép.
6. Đánh giá operation side effect, validation, retry và rollback.
7. Xác nhận lifecycle cleanup sau restart/redeploy.
8. Thống nhất runbook, quyền thao tác và điều kiện mở endpoint quản trị.
9. Phê duyệt release với evidence cụ thể.

### 20.2. Sau phát hành

1. Kiểm tra JVM/instance được quản trị là bản phát hành mong muốn.
2. Dùng client được phép kết nối đúng connector.
3. Xác nhận ObjectName quan trọng có mặt.
4. Đọc attribute an toàn và kiểm tra trạng thái.
5. Xác nhận không có MBean lạ hoặc MBean cũ thuộc ứng dụng.
6. Giám sát error rate, memory, thread và kết nối quản trị.
7. Tránh gọi operation phá trạng thái chỉ để “smoke test”.
8. Nếu phát hiện management surface khác kế hoạch, quyết định rollback hoặc khóa kênh quản trị theo quy trình.

Không nên thực hiện test tác động mạnh trực tiếp trên production khi không có yêu cầu vận hành và phê duyệt phù hợp.

## 21. Tình huống điển hình

### 21.1. Thêm operation `clearAllCaches()`

Tác động có thể bao gồm tăng cache miss và tải backend. Trước release, cân nhắc operation giới hạn theo cache/key, permission riêng và telemetry để biết hậu quả.

### 21.2. Đổi getter `getQueueSize()` từ int sang long

Metadata type thay đổi. Client đang ép kiểu `Integer` có thể fail. Cần xem đây là thay đổi contract, cập nhật test và consumer.

### 21.3. Mở JMX Remote để hỗ trợ vận hành

Đây là thay đổi bề mặt truy cập, không chỉ thay đổi cấu hình monitoring. Cần security review về bind address, RMI port, TLS, credentials và network.

### 21.4. Spring context đóng nhưng MBean vẫn còn

Có thể một thành phần đăng ký thủ công hoặc listener/connector giữ reference. Cần xác minh ownership và cleanup; không dùng lệnh unregister hàng loạt khi chưa rõ nguồn gốc.

### 21.5. Một instance mới xuất hiện với ObjectName trùng

Nếu dùng chung MBeanServer, có thể gặp lỗi `InstanceAlreadyExistsException`. Nên sửa naming hoặc duplicate exporter; không bật `REPLACE_EXISTING` chỉ để startup thành công.

## 22. Bài tập thực hành

Tạo một managed bean chứa:

- Attribute đọc `ActiveJobs`.
- Attribute đọc/ghi `AcceptingJobs`.
- Operation `pauseProcessing()`.
- Một method nội bộ `deleteAllOrders()` **không được export**.

Sau đó:

1. Export bean qua Spring `MBeanExporter` với metadata assembler đọc annotation.
2. Tạo isolated `MBeanServer` cho test.
3. Dùng `getMBeanInfo` liệt kê attributes và operations.
4. Assert `ActiveJobs` chỉ đọc và `AcceptingJobs` đọc/ghi.
5. Assert `pauseProcessing` được export với signature đúng.
6. Assert `deleteAllOrders` không xuất hiện.
7. Đọc description và xác nhận không chứa thông tin nhạy cảm.
8. Đóng Spring context, xác nhận MBean được unregister.
9. Viết release checklist cho việc mở remote connector trên một mạng lab có xác thực/TLS.
10. Tạo runbook ngắn mô tả cách xác nhận trạng thái sau khi operator gọi `pauseProcessing()`.

**Kết quả cần đạt:** không chỉ chứng minh JMX hoạt động, mà chứng minh chính xác API quản trị nào được mở, điều gì được phép thực hiện và cách xác minh/thu hồi.

## 23. Câu hỏi tự kiểm tra

**1. Management surface gồm những gì?** MBean, ObjectName, attribute, operation, notification và đường truy cập/connector.

**2. Có `@ManagedResource` là đã mở JMX Remote chưa?** Không; export và connector là hai tầng riêng.

**3. Vì sao cần test cả attribute không được phép xuất hiện?** Để phát hiện bề mặt quản trị ngoài ý muốn.

**4. Domain trong ObjectName có tự tạo quyền riêng không?** Không. Domain là namespace, không phải security boundary.

**5. `MBeanInfo` giúp release review như thế nào?** Cho biết metadata giao diện mà JMX client thực sự nhìn thấy.

**6. Vì sao `clearCache()` cần đánh giá tác động?** Có thể làm tăng cache miss và tải backend sau khi gọi.

**7. Đổi type attribute có ảnh hưởng client không?** Có thể. Script/monitoring có thể phụ thuộc kiểu cũ.

**8. `REPLACE_EXISTING` có nên bật để giải quyết mọi trùng ObjectName?** Không. Nó có thể thay MBean của thành phần khác.

**9. Vì sao getter chậm là rủi ro?** Monitoring polling thường xuyên có thể tạo tải và làm nghẽn tài nguyên.

**10. Kiểm thử endpoint JMX từ xa có nên bỏ qua TLS/authentication cho tiện không?** Không. Cần thử trong cấu hình bảo mật tương đương thực tế.

**11. Post-deploy verification nên kiểm tra gì?** Đúng JVM/server, ObjectName, metadata và những giá trị trạng thái an toàn.

**12. Nếu operation có side effect lớn, smoke test production nên làm gì?** Không gọi operation phá trạng thái tùy tiện; dùng metadata/read-only test và quy trình được phê duyệt.

## 24. Ghi nhớ

- **Management surface là API quản trị có khả năng đọc và thay đổi trạng thái runtime**, không chỉ là tập metrics.
- Trước release, kiểm kê **ObjectName, attribute, operation, notification và connector** trên đúng MBeanServer.
- Dùng **MBeanInfo** để xác minh contract thực tế, không chỉ nhìn annotation.
- Kiểm tra cả những khả năng **phải có** và những khả năng **không được xuất hiện**.
- Attribute writable và operation thay đổi trạng thái cần authorization, validation, audit và giới hạn blast radius.
- JMX Remote là control plane đặc quyền; domain ObjectName không thay thế cơ chế bảo mật.
- Tên/kiểu/signature JMX là contract có thể ảnh hưởng dashboard và automation khi thay đổi.
- Quản lý ownership, duplicate registration, listener và lifecycle để tránh MBean cũ sau redeploy.
- Không dùng operation nguy hiểm làm smoke test production.
- Một release gate tốt cần **owner, evidence, runbook và post-deploy verification**.

Rà soát management surface trước khi phát hành giúp Spring Framework JMX trở thành công cụ vận hành có kiểm soát thay vì một cổng điều khiển bị bỏ quên. Mục tiêu cuối cùng là bảo đảm những gì JMX công bố **đúng với thiết kế, có thể kiểm thử, có thể vận hành và không vượt quá quyền cần thiết**.