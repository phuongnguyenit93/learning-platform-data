# Định danh endpoint JMX và domain mặc định trong Spring Boot

## 1. Mục tiêu

Spring Boot có thể đưa thông tin quản trị ứng dụng ra **JMX** thông qua các MBean. Khi kết hợp Spring Boot Actuator và Spring Framework JMX, người vận hành thường thấy nhiều ObjectName trong JConsole hoặc VisualVM: một số thuộc domain của JVM, một số thuộc domain do Spring Boot quản lý và một số là MBean tùy chỉnh của ứng dụng.

Một lỗi phổ biến là nhầm lẫn:

- **Actuator endpoint ID**, chẳng hạn `health`, `info`, `metrics`.
- **JMX ObjectName**, tên mà `MBeanServer` dùng để định danh một MBean.
- **JMX domain**, thành phần đứng trước dấu `:` trong ObjectName.
- **HTTP actuator path**, ví dụ `/actuator/health`, vốn là một phương thức truy cập khác.
- **Spring bean name**, tên bean trong `ApplicationContext`, không nhất thiết là tên trên JMX.

Bài này giải thích cách định danh endpoint JMX trong Spring Boot, cách kiểm soát domain mặc định và phạm vi ảnh hưởng của các cấu hình liên quan. Mục tiêu thực hành là nhìn vào một ObjectName và biết nó đến từ đâu, tránh va chạm giữa những application context chạy trong cùng JVM và kiểm thử được hợp đồng định danh.

## 2. JMX ObjectName là gì?

ObjectName của JMX có cú pháp tổng quát:

```text
domain:key=value[,key=value...]
```

Ví dụ:

```text
java.lang:type=Memory
org.springframework.boot:type=Endpoint,name=Health
com.example.billing:type=Cache,name=Primary
```

Trong đó:

- `domain`: nhóm tên logic, không tự đại diện cho network domain.
- `type`, `name`: các **key properties** dùng xác định đối tượng.
- Một ObjectName được so sánh theo domain và tập property keys/values; thứ tự các key-property không quyết định tính đồng nhất của tên.
- Những giá trị chứa dấu phẩy, ký tự đặc biệt hoặc wildcard phải được xây dựng đúng cú pháp JMX, thường với `ObjectName.quote`.

Một `MBeanServer` chỉ có thể đăng ký một MBean cho một ObjectName cụ thể tại một thời điểm. Hai component cùng chọn tên đó có thể gây `InstanceAlreadyExistsException`, trừ khi exporter được cấu hình registration policy đặc biệt.

**JMX domain không có quan hệ bắt buộc với tên package Java, Maven groupId hay HTTP host.** Đó là namespace có thể được công cụ quản trị sử dụng để nhóm và truy vấn MBean.

## 3. Domain mặc định cho Spring Boot Actuator JMX

Spring Boot Actuator có hỗ trợ các endpoint qua JMX khi được bật và có thành phần cần thiết trên classpath. Trong nhiều phiên bản Boot, namespace mặc định cho các endpoint Actuator JMX là:

```text
org.springframework.boot
```

Một ObjectName thường gặp cho endpoint Health:

```text
org.springframework.boot:type=Endpoint,name=Health
```

Với Metrics:

```text
org.springframework.boot:type=Endpoint,name=Metrics
```

Tên endpoint ở biểu diễn JMX có thể được chuẩn hóa về dạng phù hợp với ObjectName, ví dụ ID `health` thành giá trị `Health`. Không nên hard-code một quy tắc đổi chữ hoa tùy đoán cho mọi version/extension; hãy xác minh các MBean thực sự đăng ký trong phiên bản Spring Boot đang triển khai.

Các endpoint `health`, `info`, `metrics` là các **Actuator endpoint ID**. Chúng không đồng nghĩa Java class của MBean và không phải tên của HTTP endpoint; một endpoint ID có thể được expose qua nhiều technology khác nhau tùy cấu hình.

## 4. Cấu hình domain JMX tùy chỉnh

Spring Boot cung cấp property chuyên dành cho domain Actuator JMX:

```properties
management.endpoints.jmx.domain=com.example.billing.management
```

Sau khi cấu hình, các endpoint được expose qua JMX sẽ thuộc namespace này, ví dụ:

```text
com.example.billing.management:type=Endpoint,name=Health
com.example.billing.management:type=Endpoint,name=Info
```

Trong YAML:

```yaml
management:
  endpoints:
    jmx:
      domain: com.example.billing.management
```

Chọn domain có nghĩa và tương đối ổn định để công cụ giám sát có thể truy vấn theo pattern:

```java
ObjectName pattern = new ObjectName(
    "com.example.billing.management:*"
);
```

**Phạm vi quan trọng:** `management.endpoints.jmx.domain` áp dụng cho các endpoint Actuator xuất qua JMX, không phải lệnh đổi domain toàn bộ MBean do ứng dụng, JVM hoặc thư viện khác đăng ký. Một MBean tùy chỉnh `@ManagedResource(objectName="com.example.cache:type=Cache,name=Primary")` vẫn dùng tên riêng của nó nếu exporter nhận metadata đó.

## 5. Bật JMX và bật exposure của Actuator là hai việc khác nhau

Các dự án có thể sử dụng `spring.jmx.enabled` để bật khả năng đăng ký bean qua cơ chế Spring JMX:

```properties
spring.jmx.enabled=true
```

Đối với Actuator, phạm vi endpoint xuất qua JMX còn chịu ảnh hưởng của cấu hình exposure:

```properties
management.endpoints.jmx.exposure.include=health,info,metrics
```

Hoặc:

```yaml
management:
  endpoints:
    jmx:
      exposure:
        include: health, info, metrics
```

Những property này phục vụ hai mục đích khác nhau:

| Property | Mục đích |
| --- | --- |
| `spring.jmx.enabled` | Điều khiển khả năng Spring JMX/bean export theo auto-configuration của Boot |
| `management.endpoints.jmx.domain` | Chọn JMX domain cho endpoint Actuator |
| `management.endpoints.jmx.exposure.include` | Chọn Actuator endpoint IDs được expose qua JMX |
| `management.endpoints.jmx.exposure.exclude` | Loại Actuator endpoint khỏi JMX exposure |
| `management.endpoints.web.exposure.include` | Chọn endpoint xuất qua HTTP, không quyết định JMX |

Hành vi mặc định và điều kiện auto-configuration thay đổi giữa các dòng Spring Boot. Vì vậy, khi chẩn đoán thiếu endpoint, hãy xem **effective configuration** và phiên bản thực tế của ứng dụng. Đừng giả định bật HTTP endpoint là JMX endpoint sẽ tự xuất hiện, hoặc ngược lại.

## 6. Endpoint ID, JMX ObjectName và HTTP path

Ví dụ với endpoint health:

```text
Logical Actuator endpoint ID:
    health

Potential HTTP endpoint:
    /actuator/health

Potential JMX ObjectName:
    org.springframework.boot:type=Endpoint,name=Health
```

Một endpoint có thể được cấu hình để truy cập qua HTTP nhưng không qua JMX. Ngược lại, khi JMX exposure bật, endpoint có thể xuất trong registry JMX mà không có web endpoint tương ứng do web exposure bị giới hạn.

**HTTP path và JMX ObjectName không nhất thiết đổi cùng nhau.** Thay đổi `management.endpoints.web.base-path` hoặc HTTP path-mapping không tự điều chỉnh `management.endpoints.jmx.domain`.

Các quy tắc security cũng khác nhau: HTTP endpoint thường đi qua Spring Security và servlet/reactive stack, còn JMX connector sử dụng security của giao thức/quản trị JMX. Không coi security rule của `/actuator/**` là biện pháp bảo vệ remote JMX.

## 7. Cách Spring Boot nhận diện endpoint Actuator

Actuator có khái niệm endpoint cùng các operation read/write/delete phù hợp với mô hình quản trị. Định nghĩa endpoint tùy chỉnh:

```java
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "queueStatus")
public class QueueStatusEndpoint {
    @ReadOperation
    public QueueSnapshot read() {
        return new QueueSnapshot(12, 3, false);
    }

    public record QueueSnapshot(
        int queued,
        int active,
        boolean paused
    ) {}
}
```

Ví dụ nhằm minh họa endpoint ID `queueStatus`, không bảo đảm kiểu return record được mọi phiên bản/công cụ JMX mapping cùng một cách. Với JMX, data model phải có khả năng chuyển đổi phù hợp với JMX/OpenType hoặc cơ chế actuator hỗ trợ; hãy kiểm thử thực tế.

Khi endpoint được expose qua JMX, infrastructure Actuator tạo MBean tương ứng và gắn dưới domain đã cấu hình. Không nên tự đăng ký thêm một Standard MBean trùng ObjectName với Actuator endpoint.

Đối với API có tham số nhạy cảm hoặc operation có tác động, cần authorization và audit riêng; việc định danh endpoint không phải security policy.

## 8. Nhiều application context trong cùng JVM

Một JVM có thể chạy nhiều Spring `ApplicationContext`:

```text
JVM / platform MBeanServer
  |
  +-- ApplicationContext A
  |      org.springframework.boot:type=Endpoint,name=Health
  |
  +-- ApplicationContext B
         org.springframework.boot:type=Endpoint,name=Health
```

Nếu cả hai context đăng ký cùng ObjectName vào cùng server, xảy ra collision. Đây là trường hợp thường gặp với:

- Nhiều application Spring Boot trong cùng application server.
- Parent/child context có Actuator riêng.
- Spring Boot DevTools restart context.
- Test integration khởi tạo nhiều context và chia sẻ platform server.
- Hot deploy/redeploy khi context cũ chưa cleanup xong.

Spring Boot có thể cung cấp cấu hình tạo các tên JMX duy nhất cho endpoint:

```properties
spring.jmx.unique-names=true
management.endpoints.jmx.unique-names=true
```

Phạm vi và khả dụng của các property này cần kiểm tra theo phiên bản Boot. `management.endpoints.jmx.unique-names` nhắm tới endpoint Actuator, còn `spring.jmx.unique-names` liên quan đăng ký MBean ở tầng Spring. Khi cấu hình hỗ trợ tạo unique names, ObjectName có thể thêm key định danh context/bean để phân biệt các đăng ký.

Không nên bật unique-name một cách mù quáng nếu automation đang phụ thuộc ObjectName ổn định. Xác nhận actual names trước và sau thay đổi, rồi cập nhật dashboard/client queries cho phù hợp.

## 9. Chọn domain riêng cho từng ứng dụng

Khi nhiều ứng dụng cùng chia sẻ JVM nhưng có ranh giới riêng, cách dễ theo dõi là đặt domain cụ thể cho ứng dụng:

```properties
management.endpoints.jmx.domain=com.example.payments.management
```

Ứng dụng khác:

```properties
management.endpoints.jmx.domain=com.example.inventory.management
```

Kết quả:

```text
com.example.payments.management:type=Endpoint,name=Health
com.example.inventory.management:type=Endpoint,name=Health
```

Cách này giúp giảm va chạm và rõ namespace. Tuy nhiên, nếu hai instance của **cùng một ứng dụng** sống đồng thời trong cùng JVM, cùng domain vẫn có thể trùng tên. Khi đó cần thêm định danh instance/context hoặc thiết kế lại ownership.

Không nhét dữ liệu bí mật, tenant identifier nhạy cảm hoặc đường dẫn filesystem vào domain hoặc ObjectName. Metadata MBean có thể được hiển thị bởi nhiều công cụ quản trị.

## 10. Domain mặc định của MBeanServer không đồng nghĩa domain Actuator

Mỗi `MBeanServer` có thể có `defaultDomain`:

```java
MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

System.out.println(server.getDefaultDomain());
```

Với platform server, giá trị mặc định thường là `DefaultDomain`. Nhưng `getDefaultDomain()` không phải `management.endpoints.jmx.domain` của Spring Boot.

Một MBean dùng ObjectName có **domain rõ ràng**:

```text
org.springframework.boot:type=Endpoint,name=Health
```

sẽ không tự đổi theo defaultDomain của server. DefaultDomain chỉ có vai trò nhất định khi ObjectName thiếu phần domain hoặc khi cơ chế đăng ký sử dụng domain mặc định.

Đừng giải quyết yêu cầu đổi namespace endpoint Actuator bằng cách tùy tiện tạo một `MBeanServer` khác chỉ để có defaultDomain khác. Điều đó có thể tách biệt MBean ứng dụng và connector ngoài ý muốn.

## 11. MBean tùy chỉnh và endpoint Actuator là hai đường export

Ví dụ Standard MBean do ứng dụng tạo:

```java
public interface CacheAdminMBean {
    long getSize();
    void clearExpired();
}

public final class CacheAdmin implements CacheAdminMBean {
    public long getSize() { return 42; }
    public void clearExpired() {}
}
```

Đăng ký:

```java
MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.cache:type=Cache,name=Primary"
);

server.registerMBean(new CacheAdmin(), name);
```

Tên của MBean này do code đăng ký xác định, không phụ thuộc domain Actuator. Khi dùng Spring `MBeanExporter` cùng `@ManagedResource`, tên có thể lấy từ annotation hoặc naming strategy.

Một ứng dụng có thể có đồng thời:

```text
java.lang:type=Memory
org.springframework.boot:type=Endpoint,name=Health
com.example.cache:type=Cache,name=Primary
```

Đây là ba nguồn MBean khác nhau, mặc dù đều nằm trong một `MBeanServer`.

## 12. Xem tên thực bằng MBeanServer

Cách xác minh thay vì phỏng đoán ObjectName:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

for (ObjectName name : server.queryNames(null, null)) {
    if (name.getDomain().contains("springframework") ||
        name.getDomain().contains("example")) {
        System.out.println(name.getCanonicalName());
    }
}
```

Đoạn probe phải chạy **trong cùng JVM** và trên **đúng MBeanServer** mà exporter sử dụng. Nếu Spring Boot hoặc ứng dụng cấu hình custom server, cần inject đúng instance.

Truy vấn theo domain:

```java
ObjectName pattern = new ObjectName(
    "com.example.payments.management:*"
);

for (ObjectName name : server.queryNames(pattern, null)) {
    System.out.println(name.getCanonicalName());
}
```

Với MBean đã biết:

```java
ObjectName expected = new ObjectName(
    "com.example.payments.management:type=Endpoint,name=Health"
);

boolean registered = server.isRegistered(expected);
System.out.println("Registered = " + registered);
```

Nếu `isRegistered` false, hãy thử `queryNames` trước khi kết luận endpoint bị tắt: có thể ObjectName khác do custom domain, unique-name hoặc quy tắc naming theo phiên bản Boot.

## 13. Dùng MBeanInfo để xác minh hợp đồng

Sau khi tìm được tên chính xác:

```java
var info = server.getMBeanInfo(expected);

for (var attribute : info.getAttributes()) {
    System.out.printf(
        "%s: type=%s readable=%s writable=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}

for (var operation : info.getOperations()) {
    System.out.println(operation.getName());
}
```

`MBeanInfo` cho biết MBean thực sự công bố những attribute và operation nào. Một tên đúng không bảo đảm method đang được expose đúng; đối với Actuator endpoint, cách mapping `@ReadOperation`, `@WriteOperation` và kiểu dữ liệu cần được kiểm chứng riêng.

Trong nhiều phiên bản Actuator, endpoint JMX công bố operation theo mô hình Actuator thay vì tất cả method Java của endpoint bean. Không suy ra tên operation chỉ bằng cách xem tên method implementation.

## 14. Kiểm thử đổi domain bằng Spring Boot Test

Một integration test có thể chạy với các property định danh:

```java
@SpringBootTest(properties = {
    "spring.jmx.enabled=true",
    "management.endpoints.jmx.domain=com.example.test.management",
    "management.endpoints.jmx.exposure.include=health,info"
})
class JmxNamingIntegrationTest {
    // Inject đúng MBeanServer rồi queryNames theo domain.
}
```

Một phép kiểm thử tập trung vào domain, thay vì giả định mọi ObjectName value:

```java
ObjectName pattern = new ObjectName(
    "com.example.test.management:*"
);

Set<ObjectName> names = server.queryNames(pattern, null);

assertFalse(names.isEmpty());
assertTrue(names.stream().allMatch(
    name -> name.getDomain().equals(
        "com.example.test.management"
    )
));
```

Nếu muốn assert chính xác Health endpoint name, dùng tên được xác định cho phiên bản Boot đang chạy và bảo đảm health endpoint thực sự được expose. Nhiều test trong cùng JVM nên dùng domain khác nhau để tránh collision với test khác.

Test cũng nên đóng Spring context đúng lifecycle. Nếu một context bị bỏ lại, MBean có thể tiếp tục tồn tại và ảnh hưởng test sau.

## 15. Tên duy nhất và độ ổn định của automation

Một ObjectName ổn định giúp:

- Script quản trị gọi được endpoint sau restart.
- JConsole/VisualVM dễ tìm cùng vị trí.
- Monitoring agent dùng query pattern nhất quán.
- Alerting truy xuất đúng MBean.

Nhưng tên quá chung dễ collision nếu nhiều context cùng server. Có hai chiến lược:

1. **Ổn định theo application**: domain cố định và một logical endpoint name, phù hợp khi chỉ một instance dùng server.
2. **Duy nhất theo instance/context**: bổ sung property hoặc namespace thích hợp, phù hợp khi nhiều instance cùng JVM.

Nếu dùng unique names tạo từ runtime identity, automation phải truy vấn theo pattern hoặc khám phá instance mới. Không nên hard-code ObjectName chứa identity động trong dashboard như một contract bất biến.

Một naming strategy cần được tài liệu hóa: domain, type, name, instance, môi trường, cách quote và tính ổn định qua redeploy.

## 16. Chẩn đoán các lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| Không thấy `org.springframework.boot` | Domain đã custom hoặc JMX exposure tắt | Effective properties và `queryNames` |
| Chỉ thấy `java.lang` | Actuator JMX chưa bật/exposed hoặc sai server | Auto-configuration, domain, MBeanServer |
| Health qua HTTP hoạt động nhưng JMX thiếu | Web và JMX exposure khác nhau | `management.endpoints.jmx.exposure.*` |
| Có hai context và startup lỗi | Trùng ObjectName | Domain, unique-names, registration policy |
| Tên endpoint khác dự kiến | Quy tắc naming/unique-name của phiên bản | In canonical ObjectNames |
| Dashboard mất số liệu sau đổi domain | Query pattern đang dùng domain cũ | Cập nhật mapping/monitoring config |
| Custom MBean không theo domain Actuator | MBean xuất qua exporter hoặc registration riêng | Kiểm tra annotation/ObjectNamingStrategy |
| Remote client không nhìn thấy endpoint | Connector trỏ server khác hoặc kết nối sai JVM | So sánh MBeanServer, JMX URL |
| Endpoint có tên đúng nhưng operation lỗi | Contract, signature hoặc security | `getMBeanInfo`, nested exception |

Để phân biệt lỗi naming với lỗi network, trước tiên kiểm tra registry **trong process ứng dụng**. Nếu MBean có ở đó nhưng client remote không thấy, chẩn đoán connector và MBeanServer binding.

## 17. Bảo mật: JMX name không phải access control

Một ObjectName dễ đoán như:

```text
org.springframework.boot:type=Endpoint,name=Health
```

không có nghĩa endpoint tự động public. Ngược lại, đặt domain khó đoán không tạo bảo mật cho endpoint.

Remote JMX cần authentication, TLS và network isolation phù hợp. Spring Security rule cho `/actuator/**` chỉ quản lý web traffic theo cấu hình; nó không tự bảo vệ remote RMI connector.

Không export endpoint quản trị có tác động mạnh nếu chưa xác định quyền gọi, auditing và tính idempotent của operation. Tránh để ObjectName chứa dữ liệu nhạy cảm vì danh sách MBean có thể bị client quản trị truy vấn.

## 18. Checklist cấu hình

- [ ] Xác định phiên bản Spring Boot và Actuator đang sử dụng.
- [ ] Biết `spring.jmx.enabled` đang có hiệu lực như thế nào.
- [ ] Biết endpoint IDs nào được expose qua `management.endpoints.jmx.exposure.*`.
- [ ] Xác định `management.endpoints.jmx.domain` và mặc định của môi trường.
- [ ] Không nhầm JMX domain với MBeanServer defaultDomain.
- [ ] Không nhầm endpoint ID với HTTP path hoặc Spring bean name.
- [ ] Nếu nhiều context/JVM instance, có chiến lược unique ObjectName.
- [ ] Custom MBean có ObjectName và naming strategy độc lập, rõ owner.
- [ ] Integration test kiểm tra actual canonical names và `MBeanInfo`.
- [ ] Remote JMX connector được bảo vệ và gắn đúng MBeanServer.
- [ ] Monitoring/dashboard được cập nhật nếu đổi domain/unique-name.
- [ ] Shutdown/redeploy không giữ MBean cũ hoặc va chạm tên mới.

## 19. Ghi nhớ

**Spring Boot Actuator endpoint ID là định danh logic của endpoint; JMX ObjectName là định danh MBean trong MBeanServer.** Một endpoint JMX thường nằm dưới domain mặc định `org.springframework.boot`, và property `management.endpoints.jmx.domain` cho phép thay đổi namespace Actuator. Domain này không tự đổi tên mọi MBean tùy chỉnh hoặc defaultDomain của server. Muốn tránh xung đột và giữ công cụ quản trị ổn định, hãy quản lý domain/unique names theo bối cảnh nhiều context, xác minh bằng `queryNames` và coi ObjectName như một hợp đồng vận hành.
