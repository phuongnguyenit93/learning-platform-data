# Giữ tài liệu và kiểm thử hợp đồng JMX sau nâng cấp Spring Framework

## 1. Mục tiêu

JMX (Java Management Extensions) là một management API của ứng dụng Java. Khi Spring Framework export bean thành MBean, những thành phần như `ObjectName`, attributes, operations, notification types, signatures và kiểu dữ liệu trở thành một **hợp đồng quản trị** mà JConsole, VisualVM, monitoring agents, automation scripts hoặc ứng dụng Java khác có thể phụ thuộc.

Nâng cấp Spring Framework, JDK, Spring Boot, thư viện monitoring hoặc cấu hình exporter có thể làm thay đổi hợp đồng này theo cách không hiển nhiên. Ví dụ một naming strategy mới tạo ObjectName khác, assembler công bố thêm/bớt method, kiểu trả về thay đổi, notification type bị đổi tên hoặc một MBean không còn được autodetect. Ứng dụng có thể vẫn khởi động và hoạt động nghiệp vụ bình thường nhưng monitoring và vận hành đã bị gián đoạn.

**Nguyên tắc:** xem API JMX như một hợp đồng có người tiêu thụ thực sự. Trước khi nâng cấp, lưu baseline có thể kiểm chứng; sau nâng cấp, so sánh hợp đồng một cách tự động và cập nhật tài liệu/runbook đúng với hành vi thực tế. Không chỉ dựa vào việc application startup thành công.

## 2. Hợp đồng JMX gồm những gì?

Một hợp đồng management có nhiều phần:

| Thành phần | Ý nghĩa | Tác động khi thay đổi |
| --- | --- | --- |
| `ObjectName` | Định danh MBean trong MBeanServer | Client không tìm được MBean cũ hoặc gọi sai resource |
| Attribute name | Tên thuộc tính như `QueueDepth` | Collector hoặc dashboard mất metric |
| Attribute type | Kiểu dữ liệu như `int`, `long`, `String`, Open Types | Lỗi cast/deserialize hoặc alert sai |
| Readable/writable | Quyền đọc/ghi ở metadata | Một attribute chỉ đọc có thể vô tình thành writable |
| Operation name | Tên lệnh quản trị | Automation gọi `invoke` thất bại |
| Operation signature | Số lượng/thứ tự/kiểu tham số | Client proxy không còn khớp API |
| Operation return type | Kiểu trả về và dữ liệu | Parser hoặc client bị lỗi |
| Notification types | Định danh sự kiện | Listener filter không còn nhận event |
| Notification payload | Schema/ý nghĩa của message, userData | Consumer xử lý sai hoặc mất tương thích |
| Semantics | Ý nghĩa, side effects, giới hạn và quyền | Có thể thay đổi behavior dù tên API không đổi |
| Lifecycle/registration | Khi nào MBean xuất hiện/biến mất | Monitoring báo missing MBean hoặc duplicate |

Không nên chỉ lưu danh sách tên. Hai phiên bản có thể có cùng ObjectName và operation name nhưng khác signature, hoặc giữ nguyên type mà đổi ý nghĩa. Một contract test tốt kiểm tra cả **cấu trúc** lẫn **ngữ nghĩa quan trọng**.

## 3. Các đường thay đổi hợp đồng khi nâng cấp

Trong Spring Framework JMX, các yếu tố có thể ảnh hưởng metadata đăng ký:

- `MBeanExporter`: danh sách bean trong map explicit hoặc autodetection.
- `@ManagedResource`: ObjectName, description và metadata tài nguyên.
- `@ManagedAttribute`/`@ManagedOperation`: các member được công bố.
- `@ManagedOperationParameters`: mô tả/tên tham số.
- `@ManagedNotifications`/`@ManagedNotification`: notification metadata.
- `ObjectNamingStrategy`: tên ObjectName khi không hard-code tên.
- `MBeanInfoAssembler`: thuật toán chọn getter, setter, operation và mô tả.
- Interface JMX chuẩn như `ExampleMBean` hoặc `ExampleMXBean`.
- Proxy Spring AOP và loại proxy JDK/CGLIB có thể ảnh hưởng metadata/call path.
- Version JDK và Open MBean type mappings.
- Cấu hình MBeanServer và `RegistrationPolicy`.

Không phải mọi bản nâng cấp sẽ làm thay đổi các thành phần này. Tuy nhiên **thay đổi nhỏ trong cấu hình hoặc code cũng có thể phá hợp đồng quản trị**, nên kiểm tra sau upgrade phải nhắm tới MBean thực tế được đăng ký, không chỉ file cấu hình.

## 4. Tài liệu hợp đồng nên lưu những gì?

Mỗi management API quan trọng nên có một tài liệu mô tả:

```text
MBean: com.example.jobs:type=QueueDiagnostics,name=Main
Owner: jobs-service
Purpose: read-only monitoring for worker queue
Since: 1.0
Status: supported

Attributes:
  QueueDepth: int, readable=true, writable=false
  CompletedCount: long, readable=true, writable=false
  HealthSummary: java.lang.String, readable=true, writable=false

Operations:
  requestRefresh(): void
    Effect: schedules refresh; may change runtime state
    Permission: privileged operator only
    Retry: not unconditional; check status first

Notifications:
  com.example.jobs.queue.threshold
    Meaning: backlog crossed warning threshold
    Payload: safe integer depth, best-effort

Compatibility:
  Name stable across deployments
  QueueDepth semantics: current pending jobs
  No secrets/PII
```

Đoạn trên là mẫu tài liệu, không phải một schema JMX tiêu chuẩn. Nó bổ sung những thông tin mà `MBeanInfo` không luôn mô tả đầy đủ, như ownership, side effects, retry policy, security và ý nghĩa nghiệp vụ.

**Tài liệu nên có version và owner**, lưu cùng repository hoặc tài liệu vận hành được kiểm soát. Không đặt token, password hoặc dữ liệu cá nhân vào ví dụ ObjectName, notification payload hay output mẫu.

## 5. Baseline phải lấy từ MBeanServer thật

Không nên xây baseline chỉ bằng cách tìm annotation trong source code. Một bean mang `@ManagedResource` có thể không được export do context scan, exporter config, conditional bean, profile hoặc lỗi đăng ký. Tên cuối cùng có thể khác annotation do naming strategy; một assembler khác có thể chọn methods khác.

Một baseline đáng tin cậy phải đọc `MBeanInfo` từ **MBeanServer đã khởi động thực tế**, trên đúng Spring profile và cấu hình deployment đại diện.

```text
ApplicationContext + Spring exporter
            |
            v
         MBeanServer
            |
            v
        queryNames
            |
            v
      getMBeanInfo(name)
            |
            v
     Versioned contract snapshot
```

Snapshot nên được chuẩn hóa thứ tự để tránh diff vô nghĩa. Đặc biệt, ObjectName key properties không có thứ tự ngữ nghĩa; dùng `getCanonicalName()` thay vì so sánh chuỗi gốc.

## 6. Truy xuất ObjectName và MBeanInfo

Ví dụ JMX thuần:

```java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName domainPattern = new ObjectName(
    "com.example.jobs:*") ;

Set<ObjectName> names = server.queryNames(domainPattern, null);

for (ObjectName name : names) {
    MBeanInfo info = server.getMBeanInfo(name);
    System.out.println(name.getCanonicalName());
    System.out.println("class=" + info.getClassName());
    System.out.println("attrs=" + info.getAttributes().length);
    System.out.println("ops=" + info.getOperations().length);
}
```

Ví dụ giả định MBeans được đăng ký vào platform MBeanServer. Nếu Spring dùng server riêng, phải truy cập đúng server hoặc `MBeanServerConnection`. Chỉ query một domain thuộc ứng dụng để tránh đưa các MBeans do JVM hoặc module khác sở hữu vào contract riêng.

Không đọc mọi attribute value để lập baseline; getter có thể tốn tài nguyên hoặc trả secrets. Phần lớn kiểm thử cấu trúc chỉ cần metadata từ `MBeanInfo`.

## 7. Snapshot attributes chính xác hơn

```java
import javax.management.MBeanAttributeInfo;

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.printf(
        "attribute=%s type=%s readable=%s writable=%s is=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable(),
        attr.isIs()
    );
}
```

Các thuộc tính cần lưu: name, Java type, readable, writable và boolean getter convention (`isIs` nếu cần). Description có thể giữ trong tài liệu, nhưng một số description do framework tạo có thể thay đổi ngôn từ qua version; nên phân biệt **diff phá hợp đồng** với **diff chỉ mô tả**.

Ví dụ thay đổi phá hợp đồng:

```text
Before: QueueDepth, int, readable=true, writable=false
After:  PendingJobs, long, readable=true, writable=false
```

Client đọc `QueueDepth` sẽ nhận `AttributeNotFoundException`; dù đổi sang long là mở rộng kiểu Java theo một số ngữ cảnh, JMX client cũ kỳ vọng int vẫn có thể lỗi cast.

Ví dụ thay đổi nguy hiểm về quyền:

```text
Before: Enabled, boolean, readable=true, writable=false
After:  Enabled, boolean, readable=true, writable=true
```

Đây là mở thêm bề mặt điều khiển, cần review về quyền và semantics, không chỉ coi là một tính năng tương thích.

## 8. Snapshot operations và signatures

MBean operation được nhận diện bằng tên và danh sách tham số. Cần ghi lại thứ tự, kiểu, return type và impact metadata.

```java
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println(
        "operation=" + op.getName() +
        " return=" + op.getReturnType() +
        " impact=" + op.getImpact()
    );
    for (MBeanParameterInfo p : op.getSignature()) {
        System.out.println(
            "  parameter=" + p.getName() + " type=" + p.getType()
        );
    }
}
```

Ví dụ contract ban đầu:

```text
requestScaleUp(int desiredWorkers): void
```

Thay bằng:

```text
requestScaleUp(long desiredWorkers): void
```

là một thay đổi signature có thể phá `MBeanServerConnection.invoke` và JMX proxy cũ dù tên operation không đổi. Nếu cần mở rộng API, cân nhắc thêm overload hoặc operation mới với lộ trình deprecation, và kiểm thử client cũ với version mới.

Với operation có side effect, contract test không được vô tình invoke ở production chỉ để xác minh nó tồn tại. Có thể kiểm tra MBeanInfo cho sự hiện diện/signature; behavior tests dùng môi trường cô lập và dữ liệu thử.

## 9. Notification types cũng là hợp đồng

Notification listener có thể subscribe theo type bằng `NotificationFilterSupport`. Nếu đổi type, listener cũ sẽ không nhận event:

```text
Before: com.example.jobs.queue.threshold
After:  com.example.jobs.queue.warning
```

Lấy metadata:

```java
import javax.management.MBeanNotificationInfo;

for (MBeanNotificationInfo n : info.getNotifications()) {
    for (String type : n.getNotifTypes()) {
        System.out.println("notificationType=" + type);
    }
}
```

Metadata chưa đủ chứng minh sự kiện được phát đúng. Trong môi trường test có thể kích hoạt một state transition an toàn, đăng ký listener và kiểm tra type, sequence, message/userData schema và ý nghĩa. Không dùng notification như một message broker durable, vì client có thể bỏ lỡ sự kiện.

Payload cần tài liệu rõ ràng và bảo đảm không chứa password/token/PII; nếu thay kiểu userData giữa các bản, remote client có thể lỗi deserialize hoặc cast.

## 10. Phân biệt breaking change và thay đổi tương thích

| Loại thay đổi | Đánh giá sơ bộ |
| --- | --- |
| Đổi domain hoặc `ObjectName` | Thường breaking với client hard-code tên |
| Xóa attribute | Breaking |
| Đổi kiểu attribute | Có thể breaking dù kiểu được “mở rộng” |
| Read-only thành writable | Mở thêm quyền tác động, cần security review |
| Xóa/đổi tên operation | Breaking |
| Đổi signature hoặc return type | Thường breaking |
| Thêm attribute/operation read-only | Thường additive nhưng cần xét bề mặt bảo mật |
| Thêm operation điều khiển | Additive về cấu trúc, nhưng có rủi ro security lớn |
| Đổi notification type | Breaking với listener lọc type |
| Thêm notification type | Additive; cần document semantics |
| Đổi mô tả text | Thường non-breaking về API, nhưng có thể ảnh hưởng tooling đặc biệt |
| Đổi semantics getter/operation | Có thể breaking dù metadata không đổi |

Đừng chỉ so sánh danh sách methods có tồn tại hay không. `getQueueDepth()` vẫn trả int nhưng bây giờ đếm cả delayed jobs là thay đổi semantics; dashboard alert thresholds có thể phải sửa.

## 11. Chuẩn hóa snapshot để diff ổn định

Để tránh snapshot thay đổi không có ý nghĩa:

1. Chuẩn hóa ObjectName bằng `getCanonicalName()`.
2. Sắp xếp MBeans theo ObjectName.
3. Sắp xếp attributes theo name/type.
4. Sắp xếp operations theo name + danh sách parameter types + return type.
5. Sắp xếp notification types.
6. Không đưa timestamp runtime, PID ngẫu nhiên hoặc giá trị đo tức thời vào structural baseline.
7. Chỉ snapshot domain/beans thuộc ứng dụng mình quản lý.
8. Có thể lưu descriptions riêng để không khiến thay đổi mô tả phá CI nếu policy không coi đó là compatibility contract.

Một baseline nên dễ đọc và dễ review trong pull request, ví dụ JSON hoặc Markdown. Không trộn structural diff với metric values động như `QueueDepth=17` vì chúng sẽ làm test không ổn định.

## 12. Ví dụ contract test bằng JUnit 5

Giả sử bài test khởi tạo Spring context chứa MBean exporter, sau đó đọc MBeanServer đã dùng để đăng ký. Một số contract quan trọng có thể được assert trực tiếp:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Arrays;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(JmxTestConfiguration.class)
class QueueJmxContractTest {
    @Autowired
    MBeanServer server;

    @Test
    void shouldPreserveQueueDiagnosticsContract() throws Exception {
        ObjectName name = new ObjectName(
            "com.example.jobs:type=QueueDiagnostics,name=Main"
        );

        assertTrue(server.isRegistered(name));
        MBeanInfo info = server.getMBeanInfo(name);

        assertTrue(Arrays.stream(info.getAttributes())
            .anyMatch(a -> a.getName().equals("QueueDepth")
                && a.getType().equals("int")
                && a.isReadable()
                && !a.isWritable()));

        assertTrue(Arrays.stream(info.getAttributes())
            .anyMatch(a -> a.getName().equals("CompletedCount")
                && a.getType().equals("long")
                && a.isReadable()
                && !a.isWritable()));
    }
}
```

`JmxTestConfiguration` là Spring test configuration do dự án định nghĩa; nó cần tạo management bean, exporter và MBeanServer phù hợp. Trong test chạy song song, nên cân nhắc MBeanServer riêng hoặc namespace test để tránh ObjectName collision giữa các test contexts.

Ví dụ trên là contract test cấu trúc, không gọi method làm thay đổi state. Có thể bổ sung assert operation signatures/notification types và verify không có attributes nhạy cảm.

## 13. Kiểm thử operation signature và tính tương thích

```java
import java.util.Arrays;
import javax.management.MBeanOperationInfo;

private static boolean hasOperation(
        MBeanInfo info, String name, String... parameterTypes) {
    return Arrays.stream(info.getOperations()).anyMatch(op ->
        op.getName().equals(name)
        && Arrays.equals(
            Arrays.stream(op.getSignature())
                .map(p -> p.getType())
                .toArray(String[]::new),
            parameterTypes
        )
    );
}
```

Trong test:

```java
assertTrue(hasOperation(info, "requestRefresh"));
assertTrue(hasOperation(info, "setWorkerLimit", "int"));
```

Nếu cần kiểm tra return type và impact, bổ sung so sánh `op.getReturnType()` và `op.getImpact()`. Với methods overload, chỉ so tên operation là chưa đủ để xác định hợp đồng.

## 14. Kiểm thử hành vi an toàn

Structural contract test không phát hiện mọi thay đổi semantics. Với một số API quan trọng, cần behavior tests:

- Getter quản trị không thay đổi business state.
- Getter trả dữ liệu an toàn, không có secrets/PII.
- Operation thay đổi trạng thái kiểm tra input range.
- Operation có idempotency hoặc concurrency policy như tài liệu.
- Notification type phát đúng khi có chuyển trạng thái trong môi trường test.
- Metric attribute có đơn vị và định nghĩa không đổi.
- Management API không tạo side effect đáng kể khi bị polling thường xuyên.

Behavior tests nên chạy với service giả/môi trường cô lập. Không gọi operation `clearCache`, `shutdown` hoặc `resetDatabase` trên production để kiểm tra “tương thích”.

## 15. Kiểm thử tương thích JMX proxy

Spring `MBeanProxyFactoryBean` giúp client gọi MBean qua interface. Nếu contract thay đổi, proxy cũ có thể không còn tương thích.

Ví dụ phía client:

```java
public interface QueueManagementClient {
    int getQueueDepth();
    void requestRefresh();
}
```

Sau nâng cấp, contract test có thể tạo proxy từ interface **của phiên bản client đang được hỗ trợ** và gọi những method read-only an toàn, hoặc kiểm tra signature từ MBeanInfo.

```text
Old client interface + new MBean server
               |
               v
     Compatibility test suite
               |
        +------+-------+
        |              |
      PASS           BREAKING
```

Nếu client và server được nâng cấp độc lập, nên có matrix compatibility thay vì chỉ build toàn bộ trên cùng dependency version mới. Một test dùng interface vừa được sửa có thể bỏ sót việc client cũ thực tế vẫn đang chạy ở phiên bản trước.

## 16. Tác động từ Spring AOP và proxy target-class

Spring bean đã được AOP proxied có thể thay đổi public surface khi chuyển giữa JDK dynamic proxy và class-based proxy. `MBeanExporter`, assembler hoặc metadata detection có thể nhìn thấy interface/method khác tùy cấu hình.

Nếu nâng cấp Spring làm thay đổi proxy behavior hoặc ứng dụng chuyển `proxyTargetClass`, cần xác nhận:

- Bean quản trị vẫn được đăng ký đúng ObjectName.
- Getter/operation dự kiến vẫn có mặt trong MBeanInfo.
- Annotation metadata vẫn được exporter đọc đúng.
- Call path qua proxy vẫn duy trì transaction/security advice khi cần.
- Không vô tình expose thêm methods chỉ có trên concrete class.

Chỉ dựa vào unit tests của business service là chưa đủ; contract test nên chạy với Spring context và exporter thực tế.

## 17. Spring Boot Actuator là một bề mặt khác

Trong ứng dụng Spring Boot, Actuator endpoints có thể được expose qua JMX bên cạnh các custom MBeans của Spring Framework. Cấu hình các endpoint này phụ thuộc Boot version và properties exposure/access.

Ví dụ:

```properties
management.endpoints.jmx.exposure.include=health,info,metrics
```

Không xem property này là filter tự động cho mọi custom MBean do `MBeanExporter` thủ công export. Sau nâng cấp, cần kiểm tra cả hai nhóm: Actuator JMX endpoints và custom application MBeans, đặc biệt nếu thay đổi naming domain, endpoint IDs hoặc tập endpoint được include.

Cấu hình `management.endpoints.web.exposure.include` độc lập với JMX exposure. Một endpoint vẫn có thể xuất hiện ở JMX dù không được public qua HTTP, hoặc ngược lại.

## 18. Security cũng là hợp đồng

Thêm một writable attribute hoặc operation có side effect không chỉ là thay đổi cấu trúc. Nó có thể mở ra khả năng điều khiển không có trong bản cũ.

Ví dụ:

```text
Before:
  CacheSize: int, readable=true, writable=false

After:
  CacheSize: int, readable=true, writable=true
```

Người dùng JMX có quyền write/invoke rộng có thể thay đổi runtime. Vì vậy quy trình nâng cấp cần kiểm tra:

- Có attribute mới trả secrets, token hoặc PII không?
- Có writable attribute mới ngoài dự kiến không?
- Có operation mới cho phép shutdown/reset/delete không?
- Connector có authentication, authorization, TLS và network policy tương ứng không?
- Monitoring user có chỉ cần đọc hay được phép invoke?
- Có endpoint nào được expose do wildcard/config default thay đổi không?

Đừng dựa vào tên `diagnostics` để kết luận an toàn. Semantics và quyền thực tế mới quyết định rủi ro.

## 19. Quản lý phiên bản và deprecation

Khi muốn thay đổi một API JMX đã có client, có thể áp dụng lộ trình:

1. **Additive first:** thêm attribute/operation mới bên cạnh contract cũ nếu có thể.
2. **Document:** ghi rõ API mới, API cũ, thời điểm deprecate và hướng di chuyển.
3. **Dual support:** hỗ trợ tạm thời cả tên cũ và mới khi hợp lý, chú ý tránh hai MBean cùng thao tác gây hiệu ứng kép.
4. **Client migration:** cập nhật collectors, dashboards, JMX proxy và scripts.
5. **Observe usage:** ghi nhận client còn dùng API cũ bằng cơ chế an toàn, không thu thập secrets.
6. **Removal window:** chỉ gỡ API cũ sau khi consumer đã được migrate và test.

Không phải lúc nào cũng có thể đăng ký song song hai ObjectName cho cùng resource. Nếu làm vậy, phải có ownership, lifecycle và duplicate notification/operation semantics rõ ràng.

Đối với thay đổi đơn vị đo, ví dụ từ milliseconds sang seconds, tốt hơn nên tạo attribute mới có tên và đơn vị rõ ràng rồi deprecate attribute cũ, thay vì đổi semantics âm thầm.

## 20. Checklist trước và sau nâng cấp

### Trước nâng cấp

- [ ] Liệt kê các MBeans được hỗ trợ và owner của từng ObjectName.
- [ ] Snapshot MBeanInfo cho attributes, operations, notifications.
- [ ] Lưu schema, semantics, units, security và side effects trong tài liệu.
- [ ] Liệt kê client phụ thuộc: dashboards, collectors, JMX proxy, scripts.
- [ ] Ghi nhận version Spring/JDK/Boot và active profiles.
- [ ] Có bài test contract chạy trên bản hiện tại để làm baseline.

### Sau nâng cấp

- [ ] Chạy lại test với context/exporter thật.
- [ ] So diff normalized ObjectName và metadata, không chỉ test startup.
- [ ] Xác nhận getter cũ vẫn đọc được theo kiểu cũ.
- [ ] Xác nhận operation signatures và notification types không thay đổi ngoài kế hoạch.
- [ ] Kiểm tra attributes mới không trả secrets và không thành writable ngoài dự kiến.
- [ ] Kiểm thử JMX proxy của những client version còn được hỗ trợ.
- [ ] Kiểm tra registration policy, duplicate ObjectName và cleanup/redeploy.
- [ ] Kiểm tra JMX exposure/access config của Actuator nếu dùng Spring Boot.
- [ ] Cập nhật runbook, monitoring, dashboards, security docs và release notes.

## 21. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Service startup bình thường, dashboard mất metric | Attribute/ObjectName đã đổi | So sánh baseline và runtime MBeanInfo |
| JMX proxy báo AttributeNotFoundException | Getter hoặc naming khác bản cũ | Giữ alias/compatibility hoặc cập nhật client |
| invoke bị ReflectionException | Operation signature thay đổi | Contract test theo type và thứ tự tham số |
| Listener không thấy notification | Notification type bị đổi hoặc registration khác | Giữ type cũ hoặc migrate subscription có kế hoạch |
| Test chỉ chạy trên client mới nên vẫn PASS | Chưa test old-client compatibility | Chạy matrix với interface/client được hỗ trợ |
| MBean bị trùng sau upgrade/redeploy | Exporter/lifecycle/naming thay đổi | Xác định owner và RegistrationPolicy |
| Endpoint mới lộ ra ngoài ý muốn | Auto-detection hoặc wildcard exposure | Dùng allowlist và kiểm tra registry thực tế |
| Diff test báo quá nhiều thay đổi vô nghĩa | Snapshot thiếu canonicalization/sorting | Chuẩn hóa metadata trước diff |
| API vẫn tồn tại nhưng semantics đã đổi | Chỉ kiểm tra metadata, không có behavior tests | Bổ sung tests ngữ nghĩa và tài liệu |

## 22. Quy trình tích hợp vào CI/CD

```text
Build new version
       |
       v
Start isolated Spring test context
       |
       v
Export MBeans to controlled MBeanServer
       |
       v
Collect canonical MBeanInfo snapshot
       |
       v
Compare with approved baseline
       |
       +--> Compatible: continue integration tests
       |
       +--> Breaking: require explicit migration review
       |
       v
Run safe behavior/security tests
       |
       v
Update contract docs + release notes
       |
       v
Deploy / monitor consumer compatibility
```

Trong test chạy song song, tránh nhiều contexts đăng ký cùng ObjectName trong platform MBeanServer chung. Có thể tạo dedicated MBeanServer, namespace riêng hoặc chạy test JVM tách biệt. Đừng đổi ObjectName production chỉ để làm test không trùng.

Test suite không nên thực hiện đầy đủ mọi operation có side effect. Dùng metadata tests cho sự tồn tại/signature và chỉ thực thi những operation được thiết kế an toàn trong môi trường cô lập.

## 23. Mô hình tư duy

```text
JMX API contract
  |
  +-- ObjectNames
  +-- Attributes (name/type/access)
  +-- Operations (name/signature/return/semantics)
  +-- Notifications (type/payload)
  +-- Security and lifecycle
  |
  v
Versioned baseline + documentation
  |
  v
Spring/JDK/Boot upgrade
  |
  v
Runtime MBeanInfo snapshot
  |
  v
Compatibility diff + safe behavior tests
  |
  +-- compatible -> update docs and deploy
  +-- breaking -> migration, deprecation, client changes
```

**Kết luận:** sau nâng cấp Spring Framework, JDK hoặc Spring Boot, cần **giữ tài liệu và kiểm thử hợp đồng JMX** như một phần của quá trình phát hành. Baseline được lấy từ MBeanServer thực tế, chuẩn hóa ObjectName/metadata, so sánh attributes/operations/notifications và bổ sung tests cho semantics, security, lifecycle và client compatibility. Tài liệu và tests giúp ngăn ứng dụng “chạy vẫn bình thường” nhưng JMX monitoring và công cụ vận hành đã bị phá vỡ.
