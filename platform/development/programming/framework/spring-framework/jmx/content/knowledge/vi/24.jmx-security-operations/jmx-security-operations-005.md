# Không phơi bày bí mật, token hoặc dữ liệu cá nhân qua Spring Framework JMX

## 1. Vì sao JMX là một bề mặt dữ liệu nhạy cảm?

Java Management Extensions (JMX) cho phép công cụ vận hành quan sát và điều khiển JVM hoặc ứng dụng. Với Spring Framework, `MBeanExporter`, `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation` và notification publisher giúp xuất bản thông tin quản trị dễ dàng. Sự tiện lợi này tạo ra rủi ro: dữ liệu nội bộ có thể bị công bố tới một JMX client không nên biết dữ liệu đó.

Không nên xem JMX là một kênh riêng tư chỉ vì nó dùng trong hệ thống nội bộ. Một remote JMX connector, tài khoản vận hành có quyền quá rộng, công cụ monitoring, debugger, log hoặc một shared MBeanServer đều có thể tạo đường truy cập tới dữ liệu nhạy cảm.

**Nguyên tắc quan trọng nhất:** chỉ công bố những gì phục vụ vận hành; không đưa password, API key, access token, refresh token, cookie, session identifier, khóa mật mã, thông tin xác thực database, dữ liệu cá nhân (PII), thông tin tài chính hoặc business payload thô vào JMX management contract.

Đặc biệt, **read-only không có nghĩa là an toàn**. Một attribute chỉ đọc vẫn có thể làm lộ secrets. Quyền truy cập JMX không thay thế được việc phân loại và giảm thiểu dữ liệu ngay từ lúc thiết kế MBean.

## 2. Những con đường có thể làm lộ dữ liệu

JMX không chỉ có attribute. Bề mặt tiếp xúc gồm:

| Bề mặt | Ví dụ lộ dữ liệu | Thiết kế an toàn hơn |
| --- | --- | --- |
| `@ManagedAttribute` getter | `getDatabasePassword()`, `getAccessToken()` | Trạng thái kết nối, TTL hoặc cờ configured thay vì giá trị thật |
| `@ManagedOperation` return value | Operation `dumpConfig()` trả raw `Properties` | Chỉ trả summary hoặc kết quả đã sanitize |
| JMX operation parameters | Token hoặc ID cá nhân truyền trong operation | Tránh truyền credentials/PII; dùng tham số không nhạy cảm |
| `Notification.message` | Exception message chứa JDBC URL có user/password | Gửi error category/code an toàn |
| `Notification.userData` | DTO có email, user profile, customer payload | Chỉ gửi enum/counter/identifier không nhạy cảm |
| `ObjectName` domain/keys | `tenantEmail`, `accessKey`, `userId` | App/component/instance ID đã kiểm soát |
| MBean description/metadata | Chuỗi chứa secret trong mô tả | Mô tả contract, không chứa dữ liệu runtime |
| JMX tooling/logging | In `MBeanInfo`, attributes hoặc stack traces | Redaction và kiểm soát access/log retention |

Điểm chung là một khi dữ liệu đã được trả qua MBeanServer hoặc đính kèm notification, dữ liệu đó có thể được đọc, lưu, truyền hoặc hiển thị bởi các client downstream. Việc ẩn cột trong dashboard **không ngăn** client khác dùng JMX API đọc attribute gốc.

## 3. Phân biệt field nội bộ với management attribute

Java field `private` không tự động thành JMX attribute. Tuy nhiên một getter public được export có thể trả về chính field private:

```java
public class ConnectionSettings {
    private final String password;

    public ConnectionSettings(String password) {
        this.password = password;
    }

    public String getPassword() {
        return password;
    }
}
```

Nếu service bị export bằng assembler phản chiếu rộng (ví dụ `SimpleReflectiveMBeanInfoAssembler`), public getter này có thể trở thành JMX attribute `Password`. Nếu getter được đánh dấu `@ManagedAttribute` và annotation-based exporter hoạt động, rủi ro cũng xuất hiện.

**Không khắc phục bằng cách đổi field thành `private` hoặc `final`**: getter vẫn trả giá trị. Cần loại getter khỏi JMX contract hoặc thay bằng một management view không chứa secret.

## 4. Anti-pattern: expose credential qua attribute

Ví dụ cần tránh:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.db:type=DatabaseConfig,name=Primary"
)
public class DatabaseConfigManagement {
    private final DatabaseSettings settings;

    public DatabaseConfigManagement(DatabaseSettings settings) {
        this.settings = settings;
    }

    @ManagedAttribute
    public String getPassword() {
        return settings.password();
    }

    @ManagedAttribute
    public String getJdbcUrl() {
        return settings.jdbcUrl();
    }
}
```

Password lộ trực tiếp. JDBC URL cũng có thể chứa username, password hoặc thông tin hạ tầng cần giới hạn. Một JMX client có quyền đọc có thể gọi:

```java
Object password = connection.getAttribute(
    objectName,
    "Password"
);
```

Không nên viện lý do “chỉ JConsole nội bộ mới dùng”. Remote connector có thể được bật sau này, công cụ tự động có thể poll và lưu giá trị, hoặc một operator có quyền rộng hơn nhu cầu.

## 5. Thiết kế management view chỉ trả thông tin cần thiết

Thay vì công bố toàn bộ config, export một adapter nhỏ:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.db:type=DatabaseHealth,name=Primary",
    description = "Thông tin trạng thái database an toàn"
)
public class DatabaseHealthManagement {
    private final DatabaseHealthProbe probe;
    private final DatabaseSettings settings;

    public DatabaseHealthManagement(
            DatabaseHealthProbe probe,
            DatabaseSettings settings) {
        this.probe = probe;
        this.settings = settings;
    }

    @ManagedAttribute(description = "Kết nối database sẵn sàng?")
    public boolean isReady() {
        return probe.isReady();
    }

    @ManagedAttribute(description = "Credential đã được cấu hình?")
    public boolean isCredentialConfigured() {
        return settings.hasCredential();
    }

    @ManagedAttribute(description = "Số kết nối đang hoạt động")
    public int getActiveConnections() {
        return probe.activeConnections();
    }
}
```

`DatabaseSettings` và `DatabaseHealthProbe` là abstractions ứng dụng cần định nghĩa. Management adapter không trả `password`, không trả token, không trả raw connection string. Nó trả trạng thái cần để quyết định điều hành.

Ngay cả boolean `CredentialConfigured` cũng có thể là thông tin nhạy cảm trong hệ thống cụ thể; chỉ expose nếu nó cần thiết. Không nên thay secret bằng hash hoặc vài ký tự cuối của token một cách máy móc: token fingerprint cũng có thể tạo khả năng correlation không mong muốn.

## 6. Dùng annotation-based export để chọn rõ API quản trị

Với Spring Framework, có thể bật:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {}
```

Đồng thời chỉ annotate các getter/operation cần công bố qua `@ManagedAttribute` và `@ManagedOperation`. Tuy nhiên phải bảo đảm exporter thực tế dùng metadata assembler phù hợp; nếu một exporter thủ công sử dụng reflection assembler rộng, các method public không annotate vẫn có thể được expose.

Mẫu thiết kế an toàn:

```text
BusinessService (nhiều field/methods nội bộ)
     |
     +-- credentials, tokens, customer records
     +-- database handles, caches, internal state
     |
     v
ManagementAdapter (API nhỏ, sanitized)
     |
     +-- getQueueDepth()
     +-- getErrorCount()
     +-- getConnectionState()
     v
MBeanExporter + MetadataMBeanInfoAssembler
     v
MBeanServer / JMX client
```

Management interface chỉ có method an toàn là một lớp giảm rủi ro. Vẫn cần security riêng cho JMX connector.

## 7. Không để reflection assembler công bố quá rộng

`SimpleReflectiveMBeanInfoAssembler` dựa trên public methods/getters. Nếu export trực tiếp service có `getConfiguration()`, `getUserSessions()` hoặc `getAuthTokens()`, dữ liệu nhạy cảm có thể nằm trong JMX contract dù không cố ý.

Ví dụ:

```java
public class AccountService {
    public int getActiveSessionCount() { return 10; }
    public List<SessionRecord> getSessions() { /* ... */ return List.of(); }
    public String getServiceToken() { /* ... */ return "secret"; }
}
```

Việc `getSessions()` trả nhiều object còn gây rủi ro serialization/classpath và tài nguyên. Với một service như vậy, không dùng reflection assembler để export trực tiếp. Hãy dùng:

- `MetadataMBeanInfoAssembler` với annotation chọn lọc.
- `InterfaceBasedMBeanInfoAssembler` với management interface riêng.
- `MethodNameBasedMBeanInfoAssembler` với allowlist rõ ràng.
- Management adapter chỉ chứa getters/operations phù hợp.

Đừng mặc định method không có annotation được ẩn nếu exporter dùng một assembler khác. Quyết định cuối cùng phải xem từ `MBeanInfo` thực tế.

## 8. ObjectName cũng có thể làm lộ dữ liệu

ObjectName dễ bị bỏ qua vì nó là tên, không phải value:

```text
com.example.users:type=Session,userEmail=alice@example.com
com.example.payments:type=Account,cardNumber=4111111111111111
com.example.auth:type=Token,accessToken=eyJ...
```

Đây là anti-pattern: `MBeanServer.queryNames` và JConsole thường cho phép liệt kê tên MBean. Tên có thể xuất hiện trong error logs, dashboards hoặc metrics collection.

Nên dùng tên không nhạy cảm, có chủ sở hữu và ổn định:

```text
com.example.auth:type=TokenService,name=Primary
com.example.payments:type=PaymentProcessor,name=Main
com.example.sessions:type=SessionMetrics,name=Global
```

Nếu buộc phải phân biệt nhiều instance, dùng opaque instance ID được thiết kế không mang PII và không có tính chất credential. Không đưa secret vào domain, key name hoặc key value.

Với value động có dấu phẩy/ký tự đặc biệt, `ObjectName.quote` chỉ xử lý **cú pháp**, không biến nội dung nhạy cảm thành an toàn.

## 9. Không đưa dữ liệu nhạy cảm vào JMX notifications

JMX notifications có type, source, sequence, timestamp, message và `userData`. Cả message và userData có thể được chuyển tới nhiều listener.

Anti-pattern:

```java
Notification event = new Notification(
    "com.example.auth.login.failed",
    this,
    sequence.incrementAndGet(),
    System.currentTimeMillis(),
    "Login failed for " + email + " token=" + token
);
event.setUserData(rawCustomerRecord);
publisher.sendNotification(event);
```

Thiết kế tốt hơn là phát event tổng hợp:

```java
Notification event = new Notification(
    "com.example.auth.login.failure.spike",
    this,
    sequence.incrementAndGet(),
    System.currentTimeMillis(),
    "Authentication failures exceeded threshold"
);
event.setUserData(Integer.valueOf(failureCount));
publisher.sendNotification(event);
```

JMX notification là một kênh quản trị, không phải kênh audit bảo mật được đảm bảo durable và có quy tắc masking mặc định. Nếu cần chi tiết để điều tra sự cố, sử dụng hệ thống audit/logging bảo mật theo chính sách lưu trữ và truy cập riêng.

## 10. Operation không nên nhận hoặc trả secret

Operation quản trị có thể không có attribute getter nhưng vẫn làm lộ dữ liệu qua tham số, return value hoặc exception message.

Ví dụ nên tránh:

```java
@ManagedOperation
public String rotateApiKey(String currentApiKey) {
    return tokenService.rotate(currentApiKey); // Trả token mới qua JMX.
}
```

Việc gửi token qua operation có thể bị log bởi instrumentation, command history hoặc JMX client. Tốt hơn là dùng một luồng rotation có kiểm soát qua secret manager hoặc dịch vụ bảo mật chuyên dụng. JMX có thể expose **trạng thái** của hoạt động này, không expose giá trị credential.

```java
@ManagedAttribute(description = "Thời điểm rotation gần nhất, epoch ms")
public long getLastRotationEpochMillis() {
    return tokenRotationState.lastRotationEpochMillis();
}
```

Nếu vẫn cần operation kích hoạt một hành động, thiết kế method không nhận secret và không trả secret, có authorization, audit và idempotency phù hợp. Thao tác nhạy cảm phải được kiểm soát tại nhiều lớp, không chỉ dựa vào tên khó đoán.

## 11. Không trả raw exception hoặc stack trace

Exceptions có thể chứa đường dẫn, username, JDBC URL, thông số xác thực, request payload hoặc thông tin hệ thống nhạy cảm. Một getter `getLastError()` trả `Throwable.toString()` hoặc một operation `dumpStackTrace()` có thể lộ dữ liệu qua JMX.

Thay bằng error category và mã lỗi có nghĩa:

```java
@ManagedAttribute(description = "Nhóm lỗi gần nhất")
public String getLastErrorCategory() {
    return errorState.getLastSafeCategory();
}

@ManagedAttribute(description = "Số lần lỗi trong cửa sổ gần nhất")
public long getRecentFailureCount() {
    return metrics.recentFailureCount();
}
```

Ví dụ category có thể là `TIMEOUT`, `AUTHENTICATION_FAILED`, `DEPENDENCY_UNAVAILABLE`. Chỉ công bố những gì operator cần để quyết định bước xử lý; chi tiết sự cố đầy đủ phải nằm trong kênh điều tra có quyền truy cập riêng.

## 12. Kiểu dữ liệu và serialization

JMX remote client có thể chạy ở JVM khác. Trả DTO domain tùy biến không chỉ có rủi ro lộ trường nhạy cảm mà còn có thể gây lỗi deserialize nếu client thiếu class. Đặc biệt tránh xuất bản:

- `User`, `Customer`, `Payment`, `Session`, `Token` object thô.
- `Map<String, Object>` chứa toàn bộ runtime configuration.
- `Properties` có database secrets hoặc cloud credentials.
- Collections không giới hạn kích thước.
- Debug DTO chứa stack traces, raw HTTP headers, cookies.

Ưu tiên số liệu tổng hợp, primitive, String an toàn hoặc JMX Open Types khi cần schema nhiều trường.

```java
@ManagedAttribute
public long getActiveSessionCount() {
    return sessionMetrics.activeCount();
}

@ManagedAttribute
public double getAuthenticationFailureRate() {
    return authMetrics.failureRate();
}
```

Ngay cả một String nhỏ cũng có thể lộ dữ liệu nếu được ghép từ exception message hoặc config mà không lọc.

## 13. Phân quyền và bảo mật JMX connector

Việc thu hẹp MBean API là bước đầu tiên. Remote connector cần các lớp bảo vệ khác:

1. **Network segmentation:** không mở JMX port ra Internet; giới hạn theo private network, VPN hoặc management plane.
2. **Authentication:** mỗi client/operator cần danh tính xác thực phù hợp; tránh tài khoản shared với quyền rộng.
3. **Authorization:** phân biệt quyền đọc metrics, nhận notification và quyền invoke operation có tác động.
4. **Encryption:** bảo vệ kênh truyền (ví dụ TLS/giải pháp transport được phê duyệt) để tránh credentials và thông tin quản trị lộ trên mạng.
5. **Audit:** ghi nhận hành động quản trị quan trọng mà không ghi giá trị secret trong log.
6. **Least privilege:** monitoring accounts nên chỉ có quyền đủ để đọc trạng thái cần thiết.

Spring Security cho HTTP endpoints không mặc định áp dụng chính sách giống hệt lên JMX/RMI connector. Khi vận hành Spring Boot Actuator và JMX song song, cần đánh giá riêng cả hai bề mặt.

Không đưa username/password thật vào file README, log, system property hiển thị cho nhiều người hoặc source control. Cấu hình credentials nên đến từ secret-management mechanism được phê duyệt.

## 14. Spring Boot Actuator và custom Spring MBeans

Spring Boot Actuator có thể expose những endpoint như `health`, `info`, `metrics`, `env`, `configprops`, `beans` qua HTTP hoặc JMX theo cấu hình/version.

Ví dụ cấu hình production với allowlist nhỏ:

```yaml
management:
  endpoints:
    jmx:
      exposure:
        include: health,info,metrics
    web:
      exposure:
        include: health,info
```

Đừng để production expose wildcard `*` vô điều kiện. Những endpoint như `env`, `configprops`, `beans`, `heapdump` hoặc `threaddump` có thể chứa thông tin cấu hình/nội bộ và cần giới hạn đặc biệt. Cấu hình redaction/sanitization của Actuator phụ thuộc phiên bản và endpoint; không nên giả định tất cả dữ liệu nhạy cảm đều được mask ở mọi đường truy cập.

**Quan trọng:** `management.endpoints.jmx.exposure.include` chỉ kiểm soát **Actuator endpoints** tương ứng; nó không tự lọc mọi custom `@ManagedResource` đã được `MBeanExporter` khác export. Cần đánh giá cả MBean do Spring Framework thủ công tạo.

## 15. Các lỗ hổng thiết kế thường gặp

| Thiết kế sai | Rủi ro | Cách thay |
| --- | --- | --- |
| Expose trực tiếp `DataSourceProperties` | URL/user/password bị lộ | `DatabaseHealthManagement` chỉ trả ready/counts |
| Getter `getSecretMasked()` trả 4 ký tự cuối token | Fingerprint/correlation không mong muốn | Trả boolean configured hoặc status |
| Notification chứa email/userId | Lộ PII tới listener và logs | Trả aggregate count/category |
| ObjectName có tenantEmail | Dễ liệt kê tenant danh tính | Dùng opaque non-sensitive ID hoặc aggregate MBean |
| Operation trả token mới | Credential nằm trong JMX response | Secret manager + status attribute |
| Reflection assembler trên service lớn | Public getter ngoài dự định thành attribute | Allowlist/interface/annotation metadata |
| Bật JMX remote không xác thực | Truy cập trái phép và command execution qua operation | Bật auth/TLS/network policy phù hợp |
| Log tất cả attribute values để debug | Secrets đi vào log retention/backups | Chỉ log safe keys/types và redact |
| Chỉ cấm HTTP Actuator mà bỏ JMX | Dữ liệu vẫn có đường JMX | Đánh giá exposure riêng từng transport |

## 16. Cách kiểm tra MBeanInfo mà không đọc secret

Có thể liệt kê **metadata** để xem những attribute/operation nào được expose mà không gọi getter lấy giá trị nhạy cảm:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.db:type=DatabaseHealth,name=Primary"
);

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.println(
        attr.getName() + " : " + attr.getType()
    );
}

for (var operation : info.getOperations()) {
    System.out.println("Operation " + operation.getName());
}
```

Ví dụ giả định MBean được export vào platform server. Nếu exporter dùng server khác, phải truy cập đúng server đó. `MBeanInfo` cho biết contract hiện hữu nhưng không chứng minh mọi getter đều vô hại hoặc mọi payload đã được sanitize.

**Không dùng công cụ kiểm tra tự động đọc mọi attribute values rồi ghi ra log** khi chưa review từng attribute. Việc QA bảo mật phải tránh tạo một bản sao của secret trong log, terminal hoặc báo cáo.

## 17. Kiểm soát dữ liệu khi vận hành và giám sát

Monitoring agent có thể poll attributes rồi chuyển dữ liệu qua nhiều hệ thống khác. Cần xem toàn bộ data path:

```text
Spring MBean
    |
    v
JMX connector / collector
    |
    v
Metrics/logs pipeline
    |
    v
Storage, dashboard, alerts, exports
```

Một secret bị expose ở MBean có thể tiếp tục nằm trong logs, traces, index và backup ngay cả sau khi getter được sửa. Vì vậy nên ngăn tại nguồn thay vì chỉ tìm cách xóa ở dashboard.

Giới hạn labels/tags trong metrics: không dùng email, account number, session ID hay token làm label. Vừa gây rủi ro riêng tư, vừa tạo cardinality cao. Dữ liệu tổng hợp như `active_sessions`, `failed_logins_total` và `queue_depth` thường phù hợp hơn.

## 18. Khi phát hiện lộ secret qua JMX

Nếu một MBean đã expose credential hoặc PII, coi đây là sự cố dữ liệu và phối hợp xử lý theo quy trình bảo mật:

1. Hạn chế đường truy cập JMX không cần thiết và thu hẹp quyền client.
2. Sửa hoặc gỡ management attribute/operation/notification bị lộ.
3. Xác định phạm vi dữ liệu đã có thể được truy cập hoặc thu thập.
4. Nếu là credential, xem xét rotate/revoke theo chính sách và đánh giá ảnh hưởng hệ thống.
5. Kiểm tra bản sao downstream: collector, log, dashboard, audit/export và retention.
6. Đánh giá nghĩa vụ thông báo liên quan dữ liệu cá nhân theo chính sách và quy định áp dụng.
7. Ngăn tái diễn bằng allowlist JMX contract, review và cấu hình connector quyền tối thiểu.

Không đưa giá trị secret thật vào ticket, chat hay bản ghi chẩn đoán. Sử dụng secret reference hoặc thông tin được redacted để phối hợp.

## 19. Checklist dành cho developer và operator

- [ ] MBean chỉ expose các trạng thái/operation thực sự cần quản trị.
- [ ] Không có getter trả password, token, cookie, API key hoặc credentials.
- [ ] Không có ObjectName/domain/key chứa PII hay secret.
- [ ] Notification type/message/userData không chứa raw business data.
- [ ] Operation không nhận/trả secret qua JMX và có validation phù hợp.
- [ ] Không export trực tiếp business service bằng reflection khi chứa public getter nhạy cảm.
- [ ] Không đưa secrets vào exception messages/stack traces được expose.
- [ ] JMX client/collector chỉ đọc danh sách được phép; không log mọi attribute values.
- [ ] Remote connector có authentication, authorization, TLS/network segmentation đúng yêu cầu.
- [ ] Các Actuator HTTP/JMX exposure và custom MBeanExporter được cấu hình riêng.
- [ ] Contract được kiểm tra bằng metadata mà không vô tình copy sensitive values.
- [ ] Có quy trình rotate/revoke và điều tra khi phát hiện lộ secret.

## 20. Mô hình tư duy

```text
Business service
  |-- credentials
  |-- tokens
  |-- personal data
  |-- internal objects
  |
  +--> management adapter / safe aggregate
             |
             +-- operational status
             +-- counters
             +-- sanitized categories
             +-- constrained operations
             |
             v
       MBeanExporter / MBeanServer
             |
             v
        authenticated JMX clients
             |
             v
        controlled monitoring pipeline
```

**Kết luận:** Spring Framework JMX phải được xem là một management API có bề mặt dữ liệu và quyền điều khiển riêng. Tránh phơi bày bí mật, token hoặc dữ liệu cá nhân bằng cách **không đưa chúng vào contract ngay từ đầu**: dùng management adapter chọn lọc, dữ liệu tổng hợp/sanitized, ObjectName an toàn, notification payload tối thiểu và operation không trao đổi secrets. Sau đó mới bổ sung bảo vệ connector, kiểm soát quyền và quản trị pipeline giám sát. Read-only, nội bộ hoặc có annotation không đồng nghĩa an toàn nếu dữ liệu được công bố sai.
