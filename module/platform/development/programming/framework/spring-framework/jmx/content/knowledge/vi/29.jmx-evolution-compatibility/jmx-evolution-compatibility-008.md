# Spring Framework JMX — Đồng bộ cấu hình giữa Spring Framework và Spring Boot

## 1. Bối cảnh và mục tiêu

Spring Framework cung cấp các thành phần JMX nền tảng như `MBeanExporter`, `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation`, `ObjectNamingStrategy`, `MBeanInfoAssembler` và `MBeanServer`. Spring Boot xây dựng trên nền Spring Framework, bổ sung cơ chế auto-configuration, properties và tích hợp với application lifecycle. Trong quá trình nâng cấp hoặc chuyển ứng dụng Spring Framework thuần sang Spring Boot, nếu giữ nguyên cấu hình JMX cũ và đồng thời bật auto-configuration mới, ứng dụng có thể gặp **đăng ký trùng MBean, dùng sai MBeanServer, đổi ObjectName ngoài ý muốn hoặc export các bean khác dự kiến**.

Bài học hướng dẫn cách đồng bộ hai lớp cấu hình để JMX management API có giao diện ổn định, không tạo double exporter và không làm hỏng dashboards, scripts, monitoring hoặc quyền vận hành.

```text
Spring Framework JMX primitives
   MBeanServer / MBeanExporter
   MetadataMBeanInfoAssembler
   ObjectNamingStrategy / annotations
                  ^
                  |
Spring Boot JMX auto-configuration
   spring.jmx.enabled
   naming domain / unique names / MBeanServer
                  |
                  v
One effective runtime JMX configuration
   -> stable ObjectName
   -> correct server
   -> intended attributes / operations
```

### Sau bài học, bạn có thể

1. Phân biệt cấu hình JMX thủ công của Spring Framework với cấu hình JMX tự động của Spring Boot.
2. Chọn **một nguồn sở hữu việc export** để tránh hai exporter đăng ký cùng MBean.
3. Duy trì `ObjectName`, domain và `MBeanServer` ổn định qua chuyển đổi/nâng cấp.
4. Kiểm soát `spring.jmx.enabled` và các properties liên quan theo Spring Boot version thực tế.
5. Tách JMX export của Spring beans khỏi Actuator endpoint exposure.
6. Viết test kiểm chứng tương thích ở runtime và kế hoạch migration an toàn.

## 2. Spring Framework JMX cung cấp gì?

Spring Framework hỗ trợ export bean Java thành MBeans thông qua `org.springframework.jmx.export.MBeanExporter`. Bean có thể:

- Là Standard MBean hoặc DynamicMBean theo JMX contract.
- Là POJO được chuyển thành ModelMBean với assembler phù hợp.
- Dùng Spring annotations: `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation` và metadata liên quan.

Ví dụ cấu hình annotation-driven:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
```

Ví dụ bean:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.app:type=WorkerPool,name=primary",
    description = "Manage the primary worker pool"
)
public class WorkerPoolControl {
    private int maxWorkers = 8;

    @ManagedAttribute
    public synchronized int getMaxWorkers() {
        return maxWorkers;
    }

    @ManagedAttribute
    public synchronized void setMaxWorkers(int requested) {
        if (requested < 1 || requested > 64) {
            throw new IllegalArgumentException("Expected 1..64");
        }
        maxWorkers = requested;
    }

    @ManagedOperation(description = "Pause new jobs")
    public void pauseIntake() {
        // Thực hiện thao tác quản trị.
    }
}
```

`@EnableMBeanExport` kích hoạt infrastructure xuất các bean được đánh dấu phù hợp. Nếu ứng dụng tự khai báo `MBeanExporter`, cần kiểm tra có thêm exporter từ annotation-driven infrastructure hay không. Không nên bật cả hai chỉ vì mỗi cách xuất hiện ở một module.

## 3. Spring Boot bổ sung điều gì?

Spring Boot có cơ chế auto-configuration để tích hợp JMX khi được bật theo cấu hình. Một property thường gặp:

```properties
spring.jmx.enabled=true
```

Trong những dòng Spring Boot hiện đại, JMX export thường không được bật mặc định cho tất cả ứng dụng; phải dựa vào reference documentation của **đúng phiên bản Boot đang chạy** để xác định default và các điều kiện auto-configuration. Không nên suy luận một property mặc định trên phiên bản mới từ dự án dùng phiên bản cũ.

Spring Boot có thể tạo hoặc tìm `MBeanServer`, thiết lập exporter và cung cấp các quy ước đặt tên. Các lựa chọn thường liên quan:

```properties
spring.jmx.enabled=true
spring.jmx.default-domain=com.example.app
spring.jmx.unique-names=true
```

`default-domain` giúp điều chỉnh domain mặc định cho tên được sinh, còn `unique-names` nhằm giảm nguy cơ trùng ObjectName trong những tình huống có nhiều context hoặc bean. Cách các giá trị này được áp dụng phụ thuộc phiên bản Boot và loại MBean. Tên tường minh từ `@ManagedResource(objectName=...)` có thể không bị thay đổi như các tên tự sinh; cần xác minh ở registry thật.

**Điểm quan trọng:** Spring Boot không thay thế JMX API của Spring Framework. Nó quyết định lúc nào tạo cấu hình và wiring mặc định; phía dưới vẫn là `MBeanServer`, exporter, assembler và naming strategy. Khi cần customization, phải biết auto-configuration nào đang hoạt động để tránh vô tình tạo đường export thứ hai.

## 4. Ba mô hình cấu hình cần phân biệt

### 4.1. Spring Framework thuần, cấu hình tường minh

```java
@Configuration
@EnableMBeanExport
public class LegacyJmxConfiguration {
}
```

Hoặc tạo một `MBeanExporter` duy nhất và cấu hình `setBeans`, `setServer`, `setAssembler`, `setNamingStrategy`.

Đặc điểm: người phát triển kiểm soát exporter và lifecycle trực tiếp; nếu muốn đổi server hoặc tên, phải điều chỉnh cấu hình thủ công.

### 4.2. Spring Boot auto-configuration

```properties
spring.jmx.enabled=true
```

Đặc điểm: Boot có thể cung cấp infrastructure theo điều kiện, giảm cấu hình thủ công. Nên dựa trên properties và customizer/bean override được hỗ trợ trong phiên bản đang dùng, thay vì khai báo thêm một exporter giống hệt.

### 4.3. Kết hợp Boot và custom exporter

Trường hợp này có thể cần thiết khi một nhóm MBeans đặc biệt phải export với naming policy riêng. Nhưng phải **tách phạm vi bean**, ObjectName và ownership giữa exporters. Nếu cùng một Spring bean được export theo annotation-driven route và explicit route, có nguy cơ `InstanceAlreadyExistsException` hoặc policy replace/ignore che đi xung đột.

## 5. Rủi ro lớn nhất: duplicate exporter

Giả sử một ứng dụng cũ dùng:

```java
@Configuration
@EnableMBeanExport
class OldJmxConfig {
}
```

Sau khi chuyển sang Spring Boot, application properties lại bật:

```properties
spring.jmx.enabled=true
```

Nếu hai cơ chế cùng tạo exporter và cùng nhận diện bean, chúng có thể cùng cố đăng ký:

```text
com.example.app:type=WorkerPool,name=primary
```

Hậu quả phổ biến:

- Startup thất bại với nguyên nhân `InstanceAlreadyExistsException`.
- Exporter A đăng ký thành công còn exporter B bị từ chối.
- Một registration policy dạng ignore/replace làm application start nhưng MBean ownership khó đoán.
- Khi context dừng hoặc restart, MBean có thể bị unregister bởi exporter không đúng owner.

Không nên xem `IGNORE_EXISTING` hoặc `REPLACE_EXISTING` là giải pháp mặc định. Chúng có thể che lỗi kiến trúc và tạo hành vi lifecycle khó kiểm soát.

**Quy tắc:** chọn một exporter chính cho các MBeans của ứng dụng. Nếu phải dùng nhiều exporter, định nghĩa rõ danh sách bean, MBeanServer và ObjectName cho từng exporter; kiểm thử chúng không đè lên nhau.

## 6. Chọn một nguồn sự thật khi chuyển đổi

Một kế hoạch migration an toàn:

1. Liệt kê các MBeans hiện có từ server chạy phiên bản cũ.
2. Ghi lại ObjectName, attributes, operations, notification types và hành vi authorization.
3. Xác định cấu hình cũ thuộc `@EnableMBeanExport`, `MBeanExporter` tường minh hay cả hai.
4. Quyết định dùng Boot auto-configuration hay tiếp tục exporter thủ công.
5. Nếu chuyển sang Boot, bỏ hoặc cô lập cấu hình export cũ để tránh duplicate.
6. Giữ lại tên tường minh quan trọng, đặc biệt các ObjectName đã được monitoring scripts sử dụng.
7. Chạy integration test so metadata/registry và thử các operations không gây side effects.
8. Chỉ rollout sau khi xác nhận server registry đúng và không có registration collisions.

Đừng xóa annotation quản trị chỉ vì đã bật `spring.jmx.enabled`; bean vẫn cần hợp đồng JMX phù hợp để được export đúng member.

## 7. ObjectName và default domain

ObjectName gồm domain và key properties:

```text
com.example.app:type=WorkerPool,name=primary
```

Trong migration, thay `com.example.app` bằng domain mặc định mới có thể phá vỡ client:

```java
ObjectName expected = new ObjectName(
    "com.example.app:type=WorkerPool,name=primary"
);
```

Nếu tên thay đổi, script gọi `getAttribute` hoặc `invoke` sẽ gặp `InstanceNotFoundException` mặc dù MBean có thể đã đăng ký dưới tên khác.

Ưu tiên giữ ObjectName ổn định như một **public management API**. Không tự động thêm random ID hoặc suffix phiên bản vào những ObjectName mà client đã phụ thuộc. Với nhiều instances trong cùng MBeanServer, dùng key logic ổn định như `name`, `service`, `context`, `tenant` nếu có nhu cầu thực.

### So sánh tên đã đăng ký

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName pattern = new ObjectName("com.example.app:*");

for (ObjectName name : server.queryNames(pattern, null)) {
    System.out.println(name.getCanonicalName());
}
```

Nếu exporter cấu hình `MBeanServer` khác platform server, phải truy vấn đúng server đó. ObjectName giống nhau ở hai MBeanServers khác nhau không cùng một registration.

## 8. Đúng MBeanServer quan trọng hơn tên của bean Spring

Trong Spring Framework, có thể cấu hình:

```java
@Bean
public MBeanExporter exporter(
        MBeanServer targetServer,
        WorkerPoolControl control) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(targetServer);
    exporter.setBeans(Map.of(
        "com.example.app:type=WorkerPool,name=primary", control
    ));
    return exporter;
}
```

Nếu một host/container đã cung cấp MBeanServer, cần inject đúng reference. Nếu Boot tự tìm server khác, có thể khiến MBeans xuất hiện tại registry mà JConsole hoặc monitoring connector không quan sát.

Với annotation-driven cấu hình có tham chiếu server bean:

```java
@Configuration
@EnableMBeanExport(server = "applicationMBeanServer")
public class JmxConfig {
    @Bean("applicationMBeanServer")
    MBeanServer applicationMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }
}
```

Ví dụ trên chỉ minh họa cách gắn exporter với bean MBeanServer được đặt tên. Trong Boot application có auto-config đang chạy, cần chọn một cấu hình sở hữu exporter để không vô tình tạo hai bean exporter.

## 9. Spring Boot Actuator JMX là lớp khác

Spring Boot Actuator có thể expose management endpoints qua JMX khi có dependency và cấu hình phù hợp. Điều này **khác với** export một bean nghiệp vụ có `@ManagedResource`. Những property liên quan Actuator thường có dạng:

```properties
management.endpoints.jmx.exposure.include=health,info
management.endpoints.jmx.domain=org.springframework.boot
```

Property cụ thể và defaults cần kiểm tra theo Spring Boot version. `management.endpoints.jmx.exposure.*` điều khiển những endpoint Actuator nào được expose qua JMX; nó không thay thế `@ManagedOperation` của một bean nghiệp vụ. Domain dành cho Actuator cũng có thể khác domain cho application MBeans.

Đừng mặc định tắt `spring.jmx.enabled` sẽ chỉ tắt Actuator mà không ảnh hưởng Spring MBeans, hoặc bật Actuator HTTP endpoints đồng nghĩa đã bật JMX management. Các lớp cấu hình này cần được xác minh riêng.

## 10. Tách trách nhiệm annotation và auto-configuration

Spring annotations mô tả **những thành phần nào của bean có thể được quản trị**:

```java
@ManagedResource(objectName = "com.example.app:type=Cache,name=products")
class ProductCacheControl {
    @ManagedAttribute
    public int getEntryCount() { return 0; }

    @ManagedOperation
    public void clearCache() { /* ... */ }
}
```

Spring Boot properties điều khiển **hạ tầng nào được khởi tạo và cách đặt tên mặc định**.

Vì vậy:

- Annotation không tự bảo đảm exporter tồn tại.
- Boot auto-config không tự biến mọi public method của bean thành management operation.
- Có metadata mà không có registration vẫn không thấy MBean.
- Có registration nhưng assembler sai có thể thiếu attribute/operation.
- Có đúng member nhưng ObjectName đổi vẫn làm client cũ thất bại.

## 11. Kiểm thử tích hợp qua runtime MBeanInfo

Phép kiểm chứng migration nên đọc metadata thực tế:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public void verifyJmxContract(MBeanServer server) throws Exception {
    ObjectName name = new ObjectName(
        "com.example.app:type=WorkerPool,name=primary"
    );

    if (!server.isRegistered(name)) {
        throw new AssertionError("Expected MBean missing: " + name);
    }

    MBeanInfo info = server.getMBeanInfo(name);

    boolean hasMaxWorkers = java.util.Arrays.stream(
        info.getAttributes()
    ).anyMatch(a -> a.getName().equals("MaxWorkers"));

    boolean hasPause = java.util.Arrays.stream(
        info.getOperations()
    ).anyMatch(op -> op.getName().equals("pauseIntake"));

    if (!hasMaxWorkers || !hasPause) {
        throw new AssertionError("JMX contract changed unexpectedly");
    }
}
```

Trong integration tests, có thể kết hợp test context cho cấu hình Spring thuần và Spring Boot với fixture MBean giống nhau. Đừng chỉ assert application context start thành công; cần kiểm tra registry, `MBeanInfo`, tên và loại members. Nếu operations có side effects, test bằng fake service/test MBean hoặc state fixture cô lập.

## 12. So sánh cấu hình trước và sau nâng cấp

Trước khi đổi phiên bản Spring hoặc Boot, lưu snapshot contract (không chứa secrets):

```text
ObjectName: com.example.app:type=WorkerPool,name=primary
Attributes:
  MaxWorkers type=int readable=true writable=true
Operations:
  pauseIntake()
Notifications:
  jmx.attribute.change
```

Ở phiên bản mới, đọc lại `MBeanInfo` và so:

1. Những ObjectName cũ vẫn tồn tại?
2. Domain và key properties có giữ nguyên không?
3. Getter/setter tạo đúng read/write flags không?
4. Operation signature có đổi do kiểu primitive/wrapper hoặc overload không?
5. Notification types còn được expose không?
6. JMX connector quyền đọc/ghi/gọi có giữ policy không?
7. Có thêm MBeans không mong muốn từ auto-config/Actuator không?
8. Có duplicate-registration warning/error không?

Các khác biệt có chủ đích phải có migration plan cho dashboards/scripts. Các khác biệt vô tình nên xử lý trước rollout.

## 13. Profiles và môi trường triển khai

Không phải môi trường nào cũng cần remote JMX. Ví dụ:

```properties
# application-dev.properties
spring.jmx.enabled=true
```

```properties
# application-prod.properties
spring.jmx.enabled=true
```

Chỉ bật khi có nhu cầu và connector remote được bảo vệ. `spring.jmx.enabled` không tự cấu hình authentication/TLS cho một JMX remote endpoint. Đây là hai trách nhiệm khác nhau: export beans và remote transport security.

Với môi trường container/Kubernetes:

- Ưu tiên ObjectName logic ổn định, không phụ thuộc pod UID nếu không cần.
- Dùng monitoring target labels để phân biệt JVM replicas.
- Không mở cổng remote JMX công khai không bảo vệ.
- Kiểm tra RMI registry/server ports và advertised hostname nếu dùng remote RMI.
- Tách cấu hình JMX export khỏi secrets/connector credentials.

## 14. Quản lý nhiều ApplicationContexts

Một ứng dụng có thể có parent/child contexts, test contexts hoặc nhiều modules khởi tạo exporter. Các contexts dùng chung MBeanServer có thể tạo collision:

```text
Context A -> com.example.app:type=Cache,name=primary
Context B -> com.example.app:type=Cache,name=primary
```

Để tránh:

- Quy định rõ context nào sở hữu registration.
- Tách Bean/ObjectName theo context nếu thật sự là hai tài nguyên khác nhau.
- Nếu là một tài nguyên chung, chỉ một exporter đăng ký.
- Không dùng registration policy ignore/replace để che thiết kế sai.
- Kiểm tra unregister sau khi dừng một context: MBeans của context còn lại phải tồn tại.

Trong Spring Boot tests, nhiều application contexts có thể tồn tại theo test runner. Khi JMX bật, có thể cần domain/unique naming riêng cho test fixtures để tránh collision, nhưng không nên dùng random naming trong production nếu client phụ thuộc tên ổn định.

## 15. Chính sách về phiên bản và tính tương thích

Spring Framework và Spring Boot cần dùng **bộ phiên bản được quản lý tương thích**. Với dự án Boot, thường nên để dependency management của Boot quyết định Spring Framework modules, tránh ép version Framework riêng tùy tiện.

Khi nâng cấp:

1. Đọc release notes và migration guide của Boot version dự kiến.
2. Kiểm tra dependency tree để biết Spring Framework thực tế.
3. Kiểm tra những properties JMX đã đổi tên, thay default hoặc deprecated.
4. Kiểm tra conditional auto-configuration và custom bean overrides.
5. Chạy regression tests cho ObjectName/MBeanInfo/registration.
6. Tổ chức rollout theo môi trường, quan sát metrics và lỗi connector.

Không dựa vào một cấu hình JMX được copy từ dự án Boot khác mà không biết version. Một property hợp lệ có thể có semantics hoặc defaults khác ở những dòng phiên bản khác nhau.

## 16. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| `InstanceAlreadyExistsException` khi startup | Hai exporters hoặc contexts đăng ký cùng ObjectName | Tìm cấu hình annotation-driven và Boot auto-config trùng |
| Application chạy nhưng không thấy MBean | JMX chưa bật, sai server hoặc thiếu annotation/assembler | Xác nhận exporter, server, `queryNames` |
| ObjectName đổi sau migration | Default domain/naming strategy/unique names thay đổi | So registry trước/sau |
| Chỉ một số operations xuất hiện | Metadata assembler/Standard MBean contract khác | Kiểm tra `MBeanInfo` |
| MBeans Actuator xuất hiện ngoài dự kiến | Actuator JMX exposure được bật | Kiểm tra `management.endpoints.jmx.exposure.*` |
| MBean mất khi một context dừng | Registration ownership trùng hoặc lifecycle overlap | Xem exporter ownership và unregister |
| JConsole kết nối nhưng không thấy custom MBean | Export vào server khác connector công bố | So MBeanServer reference/endpoint |
| Tests pass riêng lẻ nhưng fail khi chạy suite | Context/JMX registry bị chia sẻ và tên trùng | Cô lập contexts hoặc names trong test |
| Remote JMX có lỗi auth/TLS | Connector security riêng với bean export | Kiểm tra server-side connector properties |

## 17. Bài thực hành

### Bài 1: Hai cơ chế export

Ứng dụng có `@EnableMBeanExport` và `spring.jmx.enabled=true`. Hãy giải thích nguy cơ nếu cả hai export cùng bean và đề xuất chọn một nguồn sở hữu registration.

### Bài 2: Đổi domain

Trước migration: `com.example.app:type=WorkerPool,name=primary`. Sau migration: `org.springframework:type=WorkerPool,name=primary`. Phân tích ảnh hưởng tới script dùng `ObjectName` cố định và cách giữ compatibility.

### Bài 3: Kiểm tra runtime

Viết test dùng `MBeanServer.getMBeanInfo` xác nhận MBean `WorkerPool` có `MaxWorkers` writable và `pauseIntake()` được expose.

### Bài 4: Actuator và application MBean

Giải thích vì sao `management.endpoints.jmx.exposure.include=health` không thay thế `@ManagedResource` để export một business POJO thành JMX MBean.

### Bài 5: Parent và child contexts

Hai contexts cùng dùng platform MBeanServer và đăng ký cùng ObjectName. Đề xuất chiến lược ownership/namespace và kiểm tra cleanup khi một context dừng.

### Bài 6: Production security

Vì sao `spring.jmx.enabled=true` chưa đủ để expose remote JMX an toàn? Trả lời: property liên quan export, còn remote connector cần authentication, authorization, TLS và network controls riêng.

## 18. Checklist migration

- Xác định phiên bản Spring Boot/Framework và auto-configuration hiệu lực.
- Chọn một cơ chế export chính; không để exporter trùng.
- Giữ ObjectName và domain ổn định cho client hiện có.
- Xác định đúng MBeanServer được JMX connector công bố.
- Kiểm tra assembler, annotations và interface MBean.
- Phân biệt Actuator JMX endpoints với application MBeans.
- Kiểm tra unique naming khi có nhiều contexts/instances.
- Regression-test attributes/operations/notifications và quyền.
- Bảo vệ remote connector bằng auth/TLS/network isolation.
- Rollout có kiểm soát, theo dõi log registration và JMX health.

## 19. Tổng kết

Đồng bộ cấu hình JMX giữa Spring Framework và Spring Boot là quá trình xác định một **nguồn sự thật cho MBean export**, giữ management API ổn định và tránh auto-configuration trùng với cấu hình thủ công. Spring Framework cung cấp primitives và annotations; Boot cung cấp wiring/properties có điều kiện. Khi nâng cấp hoặc chuyển đổi, phải xác minh exporter, MBeanServer, ObjectName, metadata và Actuator exposure theo phiên bản thực tế. Một bài kiểm thử runtime với `MBeanInfo` và registry giúp đảm bảo client quản trị không bị phá vỡ bởi những thay đổi cấu hình không chủ ý.