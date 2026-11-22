# Kiểm tra ObjectName, quyền, vòng đời và registration policy

> **Chủ đề:** Spring Framework JMX  
> **Nhóm kiến thức:** Đánh giá thiết kế  
> **Bài học:** Kiểm tra ObjectName, quyền, vòng đời và registration policy

## 1. Mục tiêu

Trong Spring Framework JMX, một MBean không chỉ cần xuất hiện trong JConsole. Thiết kế quản trị còn phải đảm bảo định danh ổn định, quyền truy cập có giới hạn, vòng đời rõ ràng và chính sách xử lý đăng ký trùng có chủ đích.

Sau bài học, bạn có thể:

- Đánh giá ObjectName về cú pháp, tính duy nhất và độ ổn định của hợp đồng.
- Phân biệt quyền kết nối JMX với quyền đọc attribute, ghi attribute và gọi operation.
- Xác định exporter, ApplicationContext và MBeanServer chịu trách nhiệm đăng ký/hủy đăng ký.
- So sánh FAIL_ON_EXISTING, IGNORE_EXISTING và REPLACE_EXISTING.
- Nhận diện các rủi ro khi nhiều context hoặc nhiều exporter chia sẻ MBeanServer.
- Viết integration test kiểm tra metadata, quyền, đăng ký, shutdown và xung đột.
- Tạo checklist review và runbook chẩn đoán vận hành.

## 2. Mô hình đánh giá

Một hệ thống có thể gồm:

```text
Spring ApplicationContext
       |
       +-- Business bean
       +-- Management facade
       +-- MBeanExporter
                |
                | ObjectName + RegistrationPolicy
                v
            MBeanServer
                |
       +--------+----------+
       |                   |
   Local client       Remote connector
                           |
                     JMX client
```

Bốn trục thiết kế cần được đánh giá cùng nhau:

| Trục | Câu hỏi chính | Dấu hiệu bất thường |
|---|---|---|
| ObjectName | Client có định danh MBean ổn định không? | Tên theo proxy class, trùng tên, đổi sau restart |
| Quyền | Ai có thể đọc/ghi/gọi operation? | Tài khoản monitoring gọi được thao tác nguy hiểm |
| Vòng đời | Khi nào MBean được đăng ký/hủy? | MBean stale hoặc bị unregister nhầm |
| Registration policy | Xử lý xung đột có chủ đích không? | IGNORE che bean cũ; REPLACE đè MBean của module khác |

Không chỉ đọc annotation trong source: hãy kiểm tra registry và metadata thật từ MBeanServer mà client sử dụng.

## 3. Bắt đầu bằng inventory

Trước review, lập danh sách:

1. Tên Spring ApplicationContext và module sở hữu.
2. Bean implementation hay management facade được export.
3. Exporter nào thực hiện đăng ký.
4. MBeanServer nào nhận đăng ký.
5. ObjectName cuối cùng.
6. Attributes, operations và notifications được công bố.
7. Clients sử dụng, bao gồm dashboard, JConsole, agent hoặc automation.
8. Vòng đời, policy và quy trình thay đổi hợp đồng.
9. Đường truy cập local/remote, phương án authentication và authorization.
10. Độ nhạy dữ liệu và các tác dụng phụ.

Ví dụ:

| MBean | Owner | ObjectName | Quyền kỳ vọng |
|---|---|---|---|
| Orders queue | Orders module | app.management:type=Queue,name=orders | Đọc depth; operator được pause |
| Product cache | Catalog module | app.management:type=Cache,name=products | Đọc hit ratio; refresh có kiểm soát |
| Worker pool | Worker module | app.management:type=WorkerPool,name=main | Đọc active count; giới hạn resize |

Inventory phải ghi đúng server. Hai JVM hoặc hai MBeanServer khác nhau có thể cùng dùng một ObjectName mà không xung đột.

## 4. ObjectName là hợp đồng quản trị

JMX ObjectName gồm domain và key properties:

```text
app.management:type=Cache,name=products
```

Trong đó domain là app.management; type mô tả tài nguyên; name phân biệt logical instance.

```java
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "app.management:type=Cache,name=products"
);

System.out.println(name.getDomain());
System.out.println(name.getCanonicalName());
```

Tên bền vững nên:

- Có ý nghĩa đối với người vận hành.
- Phân biệt instance thực sự cần phân biệt.
- Không phụ thuộc tên class, package hoặc AOP-generated proxy.
- Không chứa secret, token, email hay dữ liệu cá nhân.
- Không đổi tùy tiện khi refactor implementation.
- Không gắn request ID hoặc timestamp tạo cardinality vô hạn.
- Có quy ước domain, type, name nhất quán trong tổ chức.

Tên chưa tốt:

```text
com.example.internal:type=RedisProductCacheServiceImpl
```

Tên theo logical resource:

```text
app.management:type=Cache,name=products
```

Đổi implementation Redis sang Caffeine không nhất thiết khiến client phải đổi ObjectName nếu management contract vẫn được giữ.

## 5. Phạm vi tính duy nhất

Mỗi MBeanServer chỉ cho phép một registration dưới một ObjectName tại một thời điểm.

```text
Server A:
  app.management:type=Queue,name=orders -> Queue A

Server B:
  app.management:type=Queue,name=orders -> Queue B
```

Hai registration này hợp lệ vì khác server.

Nhưng trong cùng Server A, hai bean đồng thời giành tên app.management:type=Queue,name=orders sẽ tạo xung đột.

Hai cách sắp xếp key sau mô tả cùng ObjectName:

```text
app.management:type=Queue,name=orders
app.management:name=orders,type=Queue
```

Có thể so:

```java
ObjectName first = new ObjectName(
    "app.management:type=Queue,name=orders"
);
ObjectName second = new ObjectName(
    "app.management:name=orders,type=Queue"
);

System.out.println(first.equals(second)); // true
```

Không xác định tính duy nhất bằng so chuỗi thủ công. Dùng ObjectName.equals hoặc canonical name.

## 6. Đặt tên trong ứng dụng nhiều module

Hai module cùng dùng type=Queue nên có key phân biệt:

```text
app.management:type=Queue,name=orders
app.management:type=Queue,name=payments
```

Nếu nhiều Spring contexts cùng quản lý một logical queue, cần quyết định rõ một context là owner duy nhất, hay mỗi instance phải có ObjectName riêng.

Có thể dùng thêm context hoặc instance key khi thật sự cần:

```text
app.management:type=Queue,name=orders,context=primary
```

Đừng tự động gắn PID hay UUID vào mọi tên để né xung đột. Điều đó có thể làm client phải khám phá lại ObjectName sau mỗi lần restart. Chỉ dùng instance identity khi hệ thống vận hành cần quản lý từng instance độc lập.

## 7. Kiểm chứng ObjectName thực tế

Với MBeanServerConnection trỏ đúng registry:

```java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import java.util.Set;

Set<ObjectName> names = connection.queryNames(
    new ObjectName("app.management:*"),
    null
);

for (ObjectName actual : names) {
    System.out.println(actual.getCanonicalName());
}
```

Khi không thấy MBean, kiểm tra:

- Bean đã được Spring tạo chưa?
- Exporter đã được bật chưa?
- Tên được khai báo trong ManagedResource hay setBeans có giống tên đang tìm không?
- ObjectNamingStrategy có tạo tên khác không?
- Exporter có dùng custom MBeanServer không?
- Có lỗi registration bị che bởi policy không?
- Client có kết nối đúng JVM không?

Không vội chỉnh annotation khi nguyên nhân là sai server hoặc URL remote connector.

## 8. MBeanInfo là bề mặt được công bố

Một bean có nhiều public methods không có nghĩa mọi method nên nằm trong JMX.

```java
import javax.management.MBeanInfo;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = connection.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "%s %s read=%s write=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println(operation.getName());
}
```

Review đầy đủ còn cần so parameter signatures và return types. Ví dụ resize(int) và resize(long) không phải cùng JMX operation signature.

Một allowlist hợp đồng minh họa:

```text
Attributes:
  PendingCount : int  read-only
  ActiveCount  : int  read-only
  MaxWorkers   : int  read-write

Operations:
  pause()  : void
  resume() : void
```

Bất cứ attribute/operation không nằm trong allowlist cần được giải thích và phê duyệt theo quy trình thiết kế.

## 9. Đánh giá quyền truy cập

Quyền được xem xét theo nhiều lớp:

```text
Network:
  Client có thể tới JMX endpoint?

Authentication:
  Client đã chứng minh danh tính gì?

Authorization:
  Danh tính được đọc, ghi, invoke những gì?

Business validation:
  Input và tác dụng phụ có nằm trong giới hạn?
```

Spring Security HTTP filter không tự bảo vệ remote JMX/RMI. Một client trong cùng JVM có thể gọi MBeanServer trực tiếp mà không đi qua remote connector.

Vì vậy không nên đặt toàn bộ kiểm soát ở port JMX. Những bất biến quan trọng như số worker tối đa, không xóa dữ liệu nhạy cảm và kiểm soát thao tác nghiệp vụ cần được thực thi ở service/facade phù hợp.

## 10. Phân vai và nguyên tắc ít quyền

| Vai trò | Read | Write | Invoke |
|---|---|---|---|
| Monitoring reader | Attribute an toàn theo allowlist | Không | Không, trừ thao tác chỉ đọc được duyệt |
| Operator | Dữ liệu vận hành | Một số setting có giới hạn | Pause/resume/reload phù hợp |
| Automation account | Chỉ số theo mục tiêu | Hạn chế | Lệnh cụ thể, có rate limit và audit |
| Administrator | Theo policy | Theo policy | Theo policy |
| Unknown caller | Không | Không | Không |

JDK management agent có thể hỗ trợ access-control file với quyền read-only/read-write tùy phiên bản, nhưng mức này không bảo đảm phân quyền tới từng operation. Khi cần role và policy chi tiết, dùng authorization layer hoặc gateway có kiểm soát, kết hợp allowlist và validation server-side.

Không mặc định mọi tài khoản kết nối được đến JMX đều có quyền gọi toàn bộ operation.

## 11. Kiểm tra attribute nhạy cảm

Ví dụ không nên expose:

```java
@ManagedAttribute
public String getDatabasePassword() {
    return password;
}
```

Hoặc:

```java
@ManagedOperation
public String dumpAllEnvironmentVariables() {
    // ...
}
```

Ngay cả attribute chỉ đọc cũng có thể làm lộ secret, metadata người dùng hoặc cấu hình nhạy cảm.

Nên ưu tiên dữ liệu tổng hợp:

```java
@ManagedAttribute
public boolean isDatabaseHealthy() {
    return healthProbe.isHealthy();
}
```

Đối với diagnostics, chỉ trả thông tin cần thiết, có redaction và giới hạn quyền phù hợp. Không lấy lý do “mạng nội bộ” làm cơ sở để bỏ qua security.

## 12. Writable attribute và operation cần validation

Ví dụ setter có giới hạn:

```java
@ManagedAttribute
public void setMaxWorkers(int requested) {
    if (requested < 1 || requested > 64) {
        throw new IllegalArgumentException(
            "requested must be between 1 and 64"
        );
    }

    workerCoordinator.setMaxWorkers(requested);
}
```

Giới hạn 1..64 chỉ là ví dụ, phải hiệu chỉnh theo hệ thống thật.

Một review cần trả lời:

1. Ai được phép thay đổi?
2. Khoảng giá trị hợp lệ là gì?
3. Operation có idempotent không?
4. Có thể đảo ngược thao tác không?
5. Nếu mất kết nối sau khi server thực thi thì client biết kết quả bằng cách nào?
6. Có audit không?
7. Có giới hạn concurrency/rate không?

JMX không tự giải quyết retry/idempotency cho các thao tác có tác dụng phụ.

## 13. Remote JMX connector không tự sinh từ exporter

Spring annotation-based export chỉ đăng ký MBean vào server thích hợp.

```java
@Configuration
@EnableMBeanExport
public class JmxConfig {
}
```

Nó không mặc định mở cổng RMI từ xa.

Một remote JMX connector sử dụng cấu hình riêng, ví dụ JDK management agent hoặc JMXConnectorServer do ứng dụng quản lý. Cần kiểm tra:

- Registry port và RMI connector endpoint port.
- Hostname được quảng bá bởi RMI.
- Firewall/security group/NetworkPolicy.
- Authentication và authorization.
- TLS/truststore/keystore nếu cần.
- MBeanServer thực sự được connector expose.

Không mở port JMX trên Internet công khai để khắc phục lỗi truy cập JConsole. Ưu tiên private management network và quyền tối thiểu.

## 14. Audit hành động quản trị

Một thao tác như pauseWorkers() có thể ảnh hưởng dịch vụ đang chạy.

Audit event nên chứa:

```json
{
  "event": "jmx.operation",
  "objectName": "app.management:type=WorkerPool,name=orders",
  "operation": "pause",
  "actor": "verified-operator-id",
  "actorSource": "authenticated-connector",
  "outcome": "SUCCESS",
  "requestId": "ops-124"
}
```

Đây là schema minh họa do ứng dụng tự xây dựng, không phải cấu trúc Spring JMX tạo sẵn.

Không coi OS user, IP hoặc tham số requestedBy do client truyền vào là bằng chứng danh tính người thao tác. Nếu dùng shared JMX credentials, audit có thể chỉ biết service account.

Cần ghi nhận cả hành động bị từ chối ở security layer, thao tác thất bại trong business code và operation bất đồng bộ chỉ mới được chấp nhận.

## 15. Vòng đời đăng ký và hủy đăng ký

Một vòng đời đơn giản:

```text
Spring context refresh
        |
        v
Managed bean initialized
        |
        v
MBeanExporter registers MBean
        |
        v
MBeanServer serves clients
        |
        v
Context shutdown
        |
        v
Exporter unregisters owned MBeans
```

Thứ tự chi tiết phụ thuộc exporter, lifecycle hooks, BeanPostProcessors và phiên bản Spring.

Review cần nêu rõ ai sở hữu MBean, khi nào nó bắt đầu sẵn sàng và khi nào nó bị hủy. Không giả định một MBean được tạo từ một context sẽ tự động được quản lý bởi mọi context khác cùng JVM.

## 16. Vấn đề startup

Các lỗi khởi động có thể gồm:

- Bean chưa được scan/khởi tạo.
- Exporter không bật hoặc trỏ sai MBeanServer.
- MBean đăng ký trước khi dependency sẵn sàng.
- Multiple exporters đăng ký cùng ObjectName.
- Proxy interface che method cần export.
- Metadata assembler không nhận diện annotation.
- Registration policy cho phép bỏ qua bean mới.

Một probe kỹ thuật:

```java
ObjectName name = new ObjectName(
    "app.management:type=Queue,name=orders"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException(
        "MBean not registered: " + name
    );
}
```

Sau đó đọc MBeanInfo và một attribute chỉ đọc an toàn. isRegistered=true không đủ để khẳng định đúng implementation hoặc hợp đồng.

## 17. Vấn đề shutdown

Khi context dừng, exporter thường hủy những registration thuộc quyền quản lý của nó.

Những tình huống cần kiểm thử:

- Context đóng rồi MBean có biến mất không?
- Một MBean thuộc module khác có bị hủy nhầm không?
- NotificationListener có được dỡ bỏ không?
- MBean bị replace có làm cleanup của exporter cũ ảnh hưởng exporter mới không?
- Client giữ proxy tới ObjectName cũ sẽ xử lý InstanceNotFoundException thế nào?
- Sau restart có còn stale registration hay không?

Một MBean chỉ đổi object bên trong không bảo đảm listener, state hoặc identity cũ tự được chuyển sang object mới.

## 18. RegistrationPolicy của Spring

Các policy:

```java
import org.springframework.jmx.support.RegistrationPolicy;
```

| Policy | Khi ObjectName tồn tại | Mục đích |
|---|---|---|
| FAIL_ON_EXISTING | Báo xung đột registration | Phát hiện lỗi naming/ownership |
| IGNORE_EXISTING | Bỏ qua đăng ký mới | Giữ MBean cũ có chủ đích |
| REPLACE_EXISTING | Thay registration cũ | Replacement có kiểm soát |

Ví dụ:

```java
MBeanExporter exporter = new MBeanExporter();

exporter.setRegistrationPolicy(
    RegistrationPolicy.FAIL_ON_EXISTING
);
```

Đoạn code chưa phải exporter hoàn chỉnh; phải gán server/bean mappings và để Spring xử lý lifecycle.

RegistrationPolicy chỉ xử lý conflict ở lúc đăng ký; nó không tự cung cấp transaction, ownership transfer, compatibility hoặc high availability.

## 19. Vì sao FAIL_ON_EXISTING thường có ích?

Một ObjectName conflict có thể tiết lộ:

- Hai module cùng dùng một logical name.
- Spring Boot auto-configuration và exporter thủ công bị chồng.
- Hai ApplicationContexts cùng export một bean.
- Naming strategy quá rộng.
- MBean cũ chưa được cleanup.
- Một thư viện khác đã chiếm tên.

Nếu xung đột là lỗi, FAIL_ON_EXISTING giúp phát hiện sớm thay vì âm thầm bỏ qua hoặc thay MBean cũ.

Không dùng IGNORE/REPLACE chỉ để làm startup hết lỗi khi chưa rõ chủ sở hữu hợp lệ.

## 20. IGNORE_EXISTING có thể giữ bản cũ

Ví dụ:

```text
Old MBean:
  ObjectName X -> version=1

New exporter:
  ObjectName X -> version=2
  policy=IGNORE_EXISTING
```

Nếu MBean cũ còn, exporter mới không thay registration. Client vẫn có thể thấy version=1.

Vì vậy ngoài việc kiểm tra server.isRegistered(name), nên đọc một attribute nhận diện hoặc metadata để xác minh registration đúng version/instance:

```java
Object version = server.getAttribute(
    name,
    "Version"
);
```

Trường Version là attribute minh họa và phải được MBean thực tế công bố; không giả định mọi MBean đều có.

## 21. REPLACE_EXISTING có rủi ro gì?

Kịch bản:

```text
Context A registers MBean A
           |
Context B replaces with MBean B
           |
Context A closes
```

Những rủi ro:

- Client gặp khoảng thời gian ObjectName chưa đăng ký.
- Notification listener gắn với MBean cũ không tự chuyển.
- MBean mới có metadata khác; client cũ có thể lỗi.
- State của MBean cũ không tự chuyển sang MBean mới.
- Cleanup của exporter cũ có thể tác động registration đang sống tùy ownership/lifecycle.
- Một exporter ngoài ý muốn có thể đè MBean quan trọng.

REPLACE_EXISTING không phải hot swap nguyên tử hoặc công cụ failover. Dùng khi có thiết kế replacement rõ ràng và integration test cho trường hợp nhiều context.

## 22. Bài thực hành với hai bean cùng ObjectName

Tạo Standard MBean:

```java
public interface CounterMBean {
    int getValue();
}

public class Counter implements CounterMBean {
    private final int value;

    public Counter(int value) {
        this.value = value;
    }

    @Override
    public int getValue() {
        return value;
    }
}
```

Server test riêng:

```java
MBeanServer server =
    MBeanServerFactory.newMBeanServer("review.test");

ObjectName name = new ObjectName(
    "app.management:type=Counter,name=shared"
);
```

Đăng ký Counter(10) trước, sau đó để Spring MBeanExporter cố đăng ký Counter(20) cùng ObjectName. Mỗi policy chạy trong một test độc lập:

| Policy | Kết quả kỳ vọng |
|---|---|
| FAIL_ON_EXISTING | Lỗi, giá trị cũ là 10 nếu không có cleanup khác |
| IGNORE_EXISTING | Giữ 10 |
| REPLACE_EXISTING | Thay thành 20 nếu đăng ký mới thành công |

Không chạy thí nghiệm replace trên platform MBeanServer có dữ liệu vận hành thật.

## 23. Kiểm tra vòng đời bằng Spring test

Ví dụ ý tưởng:

```java
MBeanServer server =
    MBeanServerFactory.newMBeanServer("lifecycle.test");

ObjectName name = new ObjectName(
    "app.management:type=WorkerPool,name=main"
);

// Spring context được cấu hình exporter với server ở trên.
AnnotationConfigApplicationContext context =
    new AnnotationConfigApplicationContext();

context.register(TestJmxConfiguration.class);
context.refresh();

assertTrue(server.isRegistered(name));

context.close();

assertFalse(server.isRegistered(name));
```

Đoạn code là khung cần TestJmxConfiguration và dependency injection phù hợp. Phải bảo đảm configuration thực sự dùng biến server đã tạo. Nếu server được tạo riêng trong context thì test cần lấy đúng MBeanServer bean sau refresh.

Không áp dụng assert unregister đơn giản cho MBean do thành phần khác sở hữu hoặc bị exporter khác replace. Ownership phải được đưa vào kỳ vọng test.

## 24. Quản lý notification listener lifecycle

Nếu MBean phát notification:

- Khi nào listener được đăng ký?
- Listener có gắn đúng ObjectName không?
- Khi MBean bị unregister, listener có được cleanup không?
- Khi MBean bị replace, listener có được đăng ký lại không?
- Có mất event trong khoảng downtime không?
- Có xử lý duplicate notifications không?

Notification không mặc định có lưu trữ/replay. Không dùng listener làm audit trail duy nhất cho hành động quan trọng.

## 25. Proxy và metadata

Spring AOP có thể khiến bean được export là JDK dynamic proxy hoặc class-based proxy.

```java
Object bean = context.getBean("workerManagement");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.getTargetClass(bean));
```

JDK proxy có thể chỉ expose methods trên interface. Annotation đặt ở implementation có thể được metadata assembler xử lý theo quy tắc phiên bản/cấu hình, nhưng không nên mặc định mọi method implementation đều gọi được qua proxy.

Review cần kiểm tra cả MBeanInfo và invocation thực tế, không chỉ sự tồn tại của annotation.

Management facade riêng thường giảm rủi ro expose nhầm service methods và giữ ObjectName độc lập khỏi implementation.

## 26. Bộ kiểm tra nhanh

```java
ObjectName name = new ObjectName(
    "app.management:type=WorkerPool,name=main"
);

if (!connection.isRegistered(name)) {
    throw new IllegalStateException("Missing MBean");
}

MBeanInfo info = connection.getMBeanInfo(name);

for (MBeanAttributeInfo a : info.getAttributes()) {
    System.out.println(
        a.getName() +
        " readable=" + a.isReadable() +
        " writable=" + a.isWritable()
    );
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println(
        "operation=" + op.getName()
    );
}
```

Cần xác minh connection trỏ đúng server exporter sử dụng. Đây là kiểm tra hợp đồng kỹ thuật, không thay thế kiểm thử security với account thực tế.

## 27. Ma trận thiết kế

| Phát hiện | Mức quan tâm | Hướng xử lý |
|---|---|---|
| Tên MBean theo class proxy | Cao | Dùng tên logical |
| Hai module dùng cùng ObjectName | Cao | Sửa naming/ownership |
| Monitoring account gọi operation thay đổi state | Cao | Giới hạn quyền |
| Read-only attribute trả secret | Cao | Không expose/masking |
| IGNORE che MBean cũ | Trung bình–cao | Đánh giá owner và deployment |
| REPLACE thiếu test lifecycle | Cao | Thêm integration test |
| MBean tồn tại nhưng thiếu operation | Trung bình | Kiểm tra assembler/proxy |
| Client kết nối sai MBeanServer | Trung bình | Đồng bộ exporter/connector |
| Listener không cleanup | Trung bình–cao | Quản lý lifecycle |
| Không có audit cho lệnh nguy hiểm | Cao | Bổ sung audit tại boundary |

Các mức quan tâm mang tính định hướng; tổ chức cần điều chỉnh theo rủi ro và mức độ ảnh hưởng thực tế.

## 28. Tình huống review

Ứng dụng có module orders và payments, đều tạo một QueueMonitor dưới ObjectName:

```text
app.management:type=Queue
```

Startup lỗi trùng tên; developer đổi policy sang REPLACE_EXISTING để hết lỗi.

Đánh giá:

1. Hai queue có phải hai tài nguyên khác nhau không?
2. Chúng có cần ObjectName riêng không?
3. Cùng MBeanServer hay khác server?
4. Có dashboard đang đọc tên cũ không?
5. Ai sở hữu MBean và vòng đời registration?
6. Account nào được pause/resume từng queue?
7. Nếu context payments đóng, MBean orders có bị ảnh hưởng không?
8. REPLACE có mục tiêu hợp lệ không?

Nếu hai queue cần tồn tại đồng thời, nên đổi sang:

```text
app.management:type=Queue,name=orders
app.management:type=Queue,name=payments
```

thay vì cho hai exporter tranh một ObjectName. Khi tên không còn xung đột, registration policy không phải cơ chế sửa naming nữa.

## 29. Checklist bàn giao

- [ ] Có inventory MBean, exporter, server, owner và client.
- [ ] ObjectName hợp lệ, logic, ổn định và duy nhất theo server.
- [ ] Không có token/PII trong ObjectName.
- [ ] MBeanInfo khớp hợp đồng đã duyệt.
- [ ] Chỉ expose attribute và operation cần thiết.
- [ ] Writable attributes có validation.
- [ ] Remote JMX connector được giới hạn mạng, authentication và TLS.
- [ ] Authorization phân biệt read/write/operation theo nhu cầu.
- [ ] Có audit cho thao tác có tác dụng phụ.
- [ ] Startup không xuất hiện registration conflict ngoài ý muốn.
- [ ] Context shutdown cleanup đúng registration thuộc quyền sở hữu.
- [ ] Nhiều exporter/context không đè tên nhau thiếu chủ đích.
- [ ] IGNORE/REPLACE được tài liệu hóa rõ mục đích.
- [ ] Có test cho trường hợp trùng ObjectName.
- [ ] Notification listener được quản lý vòng đời.
- [ ] Có runbook điều tra khi client không thấy MBean.

## 30. Câu hỏi tự kiểm tra

1. ObjectName unique theo JVM hay theo MBeanServer?
2. Vì sao tên dựa trên implementation class dễ tạo breaking change?
3. Read-only attribute có đồng nghĩa an toàn không?
4. Spring Security HTTP filter có bảo vệ JMX RMI mặc định không?
5. IGNORE_EXISTING giữ MBean nào khi tên trùng?
6. REPLACE_EXISTING có tự chuyển state/notification listener không?
7. Khi đóng context cũ sau replacement, rủi ro là gì?
8. isRegistered=true có đủ chứng minh đúng implementation không?
9. Làm sao xác định exporter và connector dùng cùng server?
10. Vì sao cần integration test cho cả registration lẫn shutdown?

## 31. Ghi nhớ

```text
ObjectName:
  logical + stable + unique + non-sensitive

Quyền:
  least privilege + network isolation
  + authentication + authorization + audit

Vòng đời:
  register đúng lúc
  unregister đúng owner
  tránh stale và duplicate registration

RegistrationPolicy:
  FAIL   -> phát hiện xung đột
  IGNORE -> giữ MBean cũ
  REPLACE -> thay MBean cũ, phải quản lý rủi ro
```

**Kết luận:** Một thiết kế Spring JMX đáng tin cậy phải trả lời rõ bốn câu hỏi: MBean có tên gì, ai được truy cập, ai quản lý vòng đời và điều gì xảy ra khi ObjectName đã tồn tại. Đừng dùng registration policy để che naming lỗi hoặc bỏ qua security. Kiểm chứng bằng metadata thực tế, quyền truy cập, integration test và kế hoạch vận hành.
