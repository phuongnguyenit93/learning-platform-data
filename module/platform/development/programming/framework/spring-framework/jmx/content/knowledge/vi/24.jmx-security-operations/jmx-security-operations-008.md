# Đặt tên để phân biệt production, staging và local trong Spring JMX

## 1. Bối cảnh

Trong hệ thống Spring Framework JMX, các môi trường production, staging và local thường triển khai cùng một mã ứng dụng, cùng loại MBean và thậm chí cùng ObjectName. Điều này không sai nếu MBeans nằm trên các MBeanServers khác nhau. Tuy nhiên, người vận hành có thể trộn số liệu, gắn nhãn sai hoặc gọi nhầm operation có tác động lên production.

Quy ước đặt tên JMX nên cung cấp định danh dễ hiểu cho **application, environment, resource type, logical resource, instance**. Nhưng ObjectName chỉ duy nhất trong phạm vi một MBeanServer; nó không tự xác thực hoặc phân quyền và không đủ để chứng minh client đang nối đúng JVM.

Bài này trình bày quy tắc thiết kế, các phương án đặt tên, lập trình Spring JMX, validation, an toàn vận hành và bài tập kiểm thử.

## 2. ObjectName và identity

JMX ObjectName có cú pháp:

    domain:key1=value1,key2=value2,...

Ví dụ:

    com.example.orders:env=prod,type=Queue,name=Payments,instance=node01
    com.example.orders:env=staging,type=Queue,name=Payments,instance=node01
    com.example.orders:env=local,type=Queue,name=Payments,instance=laptop

Trong ví dụ:
- Domain là namespace ứng dụng.
- env xác định môi trường triển khai.
- type là loại đối tượng quản trị.
- name là logical resource.
- instance dùng khi cần phân biệt nhiều MBeans cùng loại.

Mỗi MBeanServer chỉ cho đăng ký một MBean với mỗi ObjectName cụ thể. Hai JVM độc lập có thể đăng ký cùng tên mà không có xung đột. Vì vậy identity đầy đủ trong hệ thống quan sát phải xét cả **connector/server target** lẫn ObjectName.

## 3. Vì sao cần environment naming?

**Giám sát:** metrics của QueueMonitor trên staging không nên bị gộp với production.

**Vận hành:** operator mở JConsole hoặc công cụ JMX remote cần nhận ra target trước khi gọi reset, clear, reload hoặc thao tác nguy hiểm.

**Khám phá:** query theo key env giúp tìm các MBeans của một môi trường trong server đang kết nối.

**Nhiều contexts:** nếu các Spring contexts chạy cùng một JVM, app/module/instance keys giúp tránh collision. Riêng env không đủ giải quyết trường hợp tất cả cùng là prod.

**Tương thích:** ObjectName là một phần của management API. Đổi key properties có thể làm scripts/alerts cũ ngừng tìm thấy MBean.

## 4. Các chiến lược đặt tên

### 4.1 Environment là key property

    com.example.orders:env=prod,type=Cache,name=Products
    com.example.orders:env=staging,type=Cache,name=Products

Cách này giữ domain ổn định, dễ lọc bằng key và phù hợp với một schema thống nhất. Nhược điểm là mỗi thay đổi về env sẽ đổi ObjectName; third-party MBeans có thể không tuân cùng quy tắc.

### 4.2 Environment là thành phần của domain

    com.example.orders.prod:type=Cache,name=Products
    com.example.orders.staging:type=Cache,name=Products

Một số công cụ hiển thị domain rất rõ, nhưng scripts phải biết domain khác nhau và việc viết wildcard xuyên nhiều environments có thể kém thuận tiện.

### 4.3 Environment thuộc connector target

    prod-jmx.example.net -> com.example.orders:type=Cache,name=Products
    staging-jmx.example.net -> com.example.orders:type=Cache,name=Products

ObjectName không thay đổi giữa environments, phù hợp với các collector có identity ở tầng target. Tuy nhiên JMX tree không tự chỉ ra environment. Nếu collector làm mất nhãn target, số liệu dễ bị trộn.

### 4.4 Nên chọn cách nào?

Một hệ thống custom JMX MBeans có thể chọn env key property để tăng tính rõ ràng, đồng thời giữ environment/cluster labels ở connector target. Không coi env key là bằng chứng bảo mật hay source of truth duy nhất.

## 5. Chuẩn hóa environment values

Nên dùng các giá trị có quy ước:

| Value | Ý nghĩa |
|---|---|
| prod | Production |
| staging | Môi trường kiểm thử trước production |
| local | Máy phát triển |
| dev | Development shared environment |
| test hoặc ci | Automated test |

Không trộn prod, production, prd, live trong các ứng dụng khác nhau nếu cùng một tổ chức muốn quản lý tập trung.

Không tự suy luận môi trường từ Spring active profiles. Một JVM có thể dùng đồng thời prod, cloud và observability profiles. Profiles biểu diễn cách kích hoạt cấu hình, không nhất thiết một nhãn deployment duy nhất.

Cấu hình riêng:

    app.environment=prod
    app.instance-id=orders-node01

Nếu biến thiếu ở production, nên fail startup rõ ràng thay vì âm thầm dùng local.

## 6. Schema và semantics của key properties

Một schema thường hữu ích:

    com.example.orders:env=prod,type=Queue,name=Payments,instance=orders01

Domain nên thuộc ứng dụng hoặc tổ chức. Các key phải mang ý nghĩa ổn định:
- env: deployment.
- type: Queue, Cache, Worker, Scheduler...
- name: tên logical resource.
- instance: định danh cụ thể nếu cùng server có nhiều instance.
- region: chỉ khi thực sự cần phân biệt vùng.
- module: khi một ứng dụng chứa nhiều subsystems.
- tenant: chỉ dùng khi có nhu cầu rõ và không gây lộ thông tin hoặc bùng nổ MBeans.

Không đưa token, password, email cá nhân, request ID hay session ID vào ObjectName. Các giá trị này có thể xuất hiện trong logging, JConsole, collectors và dashboards.

## 7. API ObjectName

```java
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.orders:env=prod,type=Queue,name=Payments,instance=node01"
);

System.out.println(name.getDomain());
System.out.println(name.getKeyProperty("env"));
System.out.println(name.getKeyProperty("instance"));
System.out.println(name.getCanonicalName());
System.out.println(name.isPattern());
```

Với tên cụ thể, isPattern() nên false. ObjectName patterns như "com.example.orders:env=prod,*" phù hợp với queryNames(), không phải registration của một MBean cụ thể.

Hai ObjectNames có thứ tự key khác nhau vẫn có thể bằng nhau:

```java
ObjectName a = new ObjectName(
    "com.example.orders:env=prod,type=Queue,name=Payments"
);
ObjectName b = new ObjectName(
    "com.example.orders:name=Payments,type=Queue,env=prod"
);
System.out.println(a.equals(b)); // true
```

Để so định danh, dùng equals() hoặc getCanonicalName(), không so raw strings dựa trên key order.

## 8. Tạo tên từ giá trị động an toàn

Giả sử instance nhận từ deployment là "worker,region=west". Nếu nối vào chuỗi JMX mà không quote, dấu phẩy có thể bị hiểu như dấu ngăn cách properties.

```java
import java.util.Hashtable;
import javax.management.ObjectName;

String instance = "worker,region=west";
Hashtable<String, String> props = new Hashtable<>();
props.put("env", "prod");
props.put("type", "Worker");
props.put("name", "Import");
props.put("instance", ObjectName.quote(instance));

ObjectName name = new ObjectName("com.example.orders", props);
```

ObjectName.quote() được dùng cho **giá trị property**, không phải toàn bộ ObjectName. Key và domain cần được validate riêng. Dữ liệu từ người dùng không nên trực tiếp điều khiển toàn bộ tên MBean mà không có giới hạn.

## 9. @ManagedResource và giới hạn tên tĩnh

Spring JMX annotation:

```java
@ManagedResource(
    objectName = "com.example.orders:env=prod,type=Queue,name=Payments"
)
public class PaymentsQueueMonitor {
}
```

Là metadata tĩnh. Nếu cùng binary được deploy lên staging/local, hardcode env=prod tạo tên không đúng thực tế.

Annotation attribute không chấp nhận biến runtime:

```java
// Không hợp lệ nếu environmentName là biến runtime:
@ManagedResource(
    objectName = "com.example.orders:env=" + environmentName
)
```

Các giải pháp có chủ đích:
- Explicit MBeanExporter mapping.
- Custom ObjectNamingStrategy.
- Configuration-based naming với property resolution được hỗ trợ.
- Programmatic registration khi lifecycle nhiều instances thay đổi.

Nếu dự án dùng metadata assembler và annotation naming, cần bảo đảm chiến lược naming được chọn thực sự có hiệu lực, không bị một thành phần auto-configuration khác thay thế.

## 10. Lấy environment từ cấu hình Spring

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class DeploymentIdentity {
    private final String environment;
    private final String instanceId;

    public DeploymentIdentity(
            @Value("${app.environment}") String environment,
            @Value("${app.instance-id}") String instanceId) {

        if (!"prod".equals(environment)
                && !"staging".equals(environment)
                && !"local".equals(environment)) {
            throw new IllegalArgumentException("Invalid environment");
        }
        if (instanceId == null || instanceId.isBlank()) {
            throw new IllegalArgumentException("Invalid instance ID");
        }
        this.environment = environment;
        this.instanceId = instanceId;
    }

    public String environment() { return environment; }
    public String instanceId() { return instanceId; }
}
```

Một ứng dụng có thêm dev/ci nên cập nhật tập giá trị hợp lệ theo chính sách chung. Không dùng hostname làm environment mà chưa có mapping đáng tin cậy.

## 11. Custom ObjectNamingStrategy

```java
import java.util.Hashtable;
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;
import org.springframework.jmx.export.naming.ObjectNamingStrategy;

public class EnvironmentNamingStrategy
        implements ObjectNamingStrategy {

    private final DeploymentIdentity identity;

    public EnvironmentNamingStrategy(DeploymentIdentity identity) {
        this.identity = identity;
    }

    @Override
    public ObjectName getObjectName(Object managedBean, String beanKey)
            throws MalformedObjectNameException {

        Hashtable<String, String> properties = new Hashtable<>();
        properties.put("env", ObjectName.quote(identity.environment()));
        properties.put("type", "Monitor");
        properties.put("name", ObjectName.quote(beanKey));
        properties.put("instance", ObjectName.quote(identity.instanceId()));

        return new ObjectName("com.example.orders", properties);
    }
}
```

Đây là ví dụ naming tập trung. Trong production có thể dùng explicit mapping từ beanKey sang logical type/name để tránh lệ thuộc bean key thay đổi sau refactor.

Không nên lấy managedBean.getClass().getSimpleName() làm public JMX type nếu Spring AOP có thể tạo JDK dynamic proxy hoặc class-based proxy: runtime class name có thể không ổn định.

## 12. Cấu hình MBeanExporter

```java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxConfiguration {
    @Bean
    public MBeanExporter mBeanExporter(
            PaymentsQueueMonitor monitor,
            DeploymentIdentity identity) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of("PaymentsQueue", monitor));
        exporter.setNamingStrategy(
            new EnvironmentNamingStrategy(identity)
        );
        exporter.setAutodetectMode(MBeanExporter.AUTODETECT_NONE);
        return exporter;
    }
}
```

Mẫu này trình bày naming dynamic. Nếu PaymentsQueueMonitor chỉ là POJO với @ManagedResource, còn cần metadata assembler phù hợp hoặc cơ chế adaptation tương đương; setBeans riêng không tự công bố mọi getter và operation theo annotations. Nếu bean là Standard MBean hợp lệ, management interface có thể được suy ra từ interface quy ước.

Trong Spring Boot, kiểm tra JMX auto-configuration trước khi khai báo exporter thủ công. Hai exporters cùng đăng ký một ObjectName trên cùng server có thể xung đột.

## 13. Phân biệt target và ObjectName

Một JMX connector URL:

    service:jmx:rmi:///jndi/rmi://prod-jmx.example.net:9010/jmxrmi

khác với ObjectName:

    com.example.orders:env=prod,type=Queue,name=Payments

URL định vị connector và MBeanServer đích. ObjectName định danh một MBean trong server đó. Cùng một ObjectName có thể tồn tại trên staging. Vì vậy, một script dùng đúng ObjectName nhưng kết nối sai URL vẫn có thể thao tác trên MBean của staging.

Identity cho monitoring thường nên gồm:
- Environment/cluster được xác minh ở tầng target.
- Host/process hoặc stable instance ID.
- ObjectName canonical.
- Attribute/operation/notification type khi cần.

## 14. Xác nhận trước khi gọi production operation

Với operation làm thay đổi trạng thái:
1. Đọc và xác nhận connector URL từ inventory đáng tin.
2. Đối chiếu environment label của target.
3. Kiểm tra ObjectName env key.
4. Đọc một runtime identity attribute nếu được hệ thống hỗ trợ.
5. Kiểm tra quyền và xác nhận phạm vi tác động.
6. Ghi audit và giới hạn thao tác theo chính sách.
7. Không retry remote invoke có side effect khi timeout nếu chưa biết request trước đã chạy chưa.

Ví dụ:

```java
ObjectName target = new ObjectName(
    "com.example.orders:env=prod,type=Queue,name=Payments,instance=node01"
);

if (!"prod".equals(target.getKeyProperty("env"))) {
    throw new IllegalArgumentException("Unexpected environment");
}

if (!connection.isRegistered(target)) {
    throw new IllegalStateException("Target not registered");
}
```

Đây chỉ là client-side validation. Một staging server có thể vô tình công bố env=prod nếu cấu hình sai; vì vậy vẫn cần kiểm tra connector identity và phân quyền server-side.

## 15. Security và network isolation

Naming không thay thế:
- Authentication.
- Authorization cho invoke()/setAttribute().
- TLS hoặc bảo vệ đường truyền.
- Firewall và network segmentation.
- Audit.
- Quy trình approval khi thay đổi production state.

Production JMX remote cần được giới hạn truy cập. Không dùng chung credentials prod/staging chỉ để tiện tooling. Một MBean có env=prod không ngăn client trái quyền gọi được operations nếu connector security được cấu hình sai.

## 16. Multi-context collision

Trong cùng JVM có thể chạy:
- orders application context.
- reporting context.
- admin context.

Nếu cả ba export:

    com.example:type=Cache,name=Default

thì ObjectName collision có thể xảy ra. Sửa bằng domain/module/instance:

    com.example.orders:env=prod,type=Cache,name=Default,instance=orders01
    com.example.reporting:env=prod,type=Cache,name=Default,instance=report01
    com.example.admin:env=prod,type=Cache,name=Default,instance=admin01

Registration policies như FAIL_ON_EXISTING, IGNORE_EXISTING hoặc REPLACE_EXISTING không thay thế thiết kế naming. REPLACE_EXISTING có thể tác động tới MBean do component khác sở hữu.

## 17. Truy vấn runtime

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName query = new ObjectName("com.example.orders:*");

for (ObjectName name : server.queryNames(query, null)) {
    System.out.println(name.getCanonicalName());
    System.out.println(name.getKeyProperty("env"));
}
```

Sử dụng platform server chỉ khi exporter thực sự đăng ký vào platform server. Nếu ứng dụng có custom MBeanServer, phải truy vấn đúng instance đó.

Query theo environment:

```java
ObjectName prod = new ObjectName(
    "com.example.orders:env=prod,*"
);
for (ObjectName name : server.queryNames(prod, null)) {
    System.out.println(name);
}
```

Query vẫn chỉ chạy trong server đang kết nối, không tự tìm tất cả JVM production.

## 18. Kiểm thử naming

Các trường hợp quan trọng:

| Test input | Kỳ vọng |
|---|---|
| environment=prod | env=prod |
| environment=staging | env=staging |
| environment=local | env=local |
| Environment bị thiếu | Fail rõ ràng |
| Instance có dấu phẩy | Value được quote phù hợp |
| Hai instances cùng JVM | ObjectNames khác nhau |
| Hai JVM khác nhau cùng ObjectName | Hợp lệ nhưng target phải rõ |
| Key order khác nhau | ObjectName equality giữ nguyên |
| Wildcard ngoài ý muốn | Không dùng pattern để register |
| Proxy class thay đổi | Tên logical vẫn ổn định |

Ví dụ JUnit:

```java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;

class ObjectNameTest {
    @Test
    void environmentChangesIdentity() throws Exception {
        ObjectName prod = new ObjectName(
            "com.example.orders:env=prod,type=Queue,name=Payments"
        );
        ObjectName stage = new ObjectName(
            "com.example.orders:env=staging,type=Queue,name=Payments"
        );
        assertNotEquals(prod, stage);
        assertEquals("prod", prod.getKeyProperty("env"));
        assertFalse(prod.isPattern());
    }
}
```

Unit test kiểm tra định danh, integration test cần khởi động Spring MBeanExporter và xác nhận isRegistered() trên đúng MBeanServer.

## 19. Thay đổi ObjectName và migration

Nếu đổi từ:

    com.example.orders:type=Queue,name=Payments

sang:

    com.example.orders:env=prod,type=Queue,name=Payments

thì script JMX client dùng tên cũ có thể mất kết nối tới MBean mong muốn mặc dù server vẫn chạy.

Nên:
1. Kiểm kê monitoring queries, scripts và alerts.
2. Cập nhật patterns trong clients.
3. Triển khai và kiểm tra trên staging.
4. Lập migration plan nếu có nhiều consumers.
5. Tránh tạo hai MBeans không đồng bộ cùng đại diện một resource.
6. Xác minh ObjectNames sau deploy.

## 20. High cardinality

Không nên đưa:
- request ID.
- session ID.
- customer email.
- authorization token.
- unrestricted tenant/user ID.

vào ObjectName nếu không có nhu cầu thực sự. Chúng có thể gây bùng nổ số MBeans, tăng metric cardinality khi collector chuyển key properties thành labels và làm lộ dữ liệu.

Giữ app/env/type/name/instance ổn định và bounded. Nếu cần xử lý nhiều đối tượng động, dùng một management MBean tổng hợp với query/snapshot có giới hạn thay vì một MBean cho từng request.

## 21. Bài tập thực hành

### Bài A: ObjectName theo ba môi trường
1. Thiết kế domain com.example.orders.
2. Tạo tên prod, staging, local theo cùng schema.
3. Parse bằng ObjectName.
4. Kiểm tra getKeyProperty("env").
5. So sánh equality và canonical names.

### Bài B: Runtime config
1. Cấu hình app.environment và app.instance-id.
2. Tạo EnvironmentNamingStrategy.
3. Export một monitor bằng MBeanExporter.
4. Chạy cùng artifact với ba bộ cấu hình.
5. Xác minh tên được đăng ký thực tế.

### Bài C: Ký tự đặc biệt
1. Dùng instance value "worker,region=west".
2. Thử nối chuỗi thủ công.
3. Sửa bằng ObjectName.quote().
4. Kiểm tra các key properties và isPattern().
5. Giải thích vì sao quote chỉ dành cho property value.

### Bài D: Multi-context
1. Tạo hai Spring contexts dùng chung platform MBeanServer.
2. Export cùng ObjectName để quan sát collision.
3. Sửa domain/module/instance.
4. Kiểm tra cả hai được đăng ký.
5. Đóng context và xác minh lifecycle.

### Bài E: Tránh thao tác nhầm production
1. Chuẩn bị một MBean có operation thay đổi state.
2. Viết client xác nhận target identity.
3. Thử đưa URL staging nhưng ObjectName prod.
4. Đảm bảo client từ chối khi identity mismatch.
5. Giải thích tại sao server-side authorization vẫn bắt buộc.

## 22. Câu hỏi tự kiểm tra

**Câu 1.** ObjectName có duy nhất trên mọi JVM không?  
**Trả lời:** Không, chỉ trong từng MBeanServer.

**Câu 2.** Vì sao thêm env key?  
**Trả lời:** Giúp phân loại và nhận diện môi trường trong MBean tree và monitoring.

**Câu 3.** env=prod có bảo vệ operation không?  
**Trả lời:** Không, cần quyền, network controls và xác nhận target.

**Câu 4.** Spring active profiles có luôn là tên môi trường không?  
**Trả lời:** Không, profile có thể rỗng hoặc bao gồm nhiều feature/config profiles.

**Câu 5.** Vì sao không hardcode env trong annotation khi dùng cùng artifact?  
**Trả lời:** Annotation value là hằng tại compile time; runtime environment có thể khác.

**Câu 6.** Giá trị instance động có dấu phẩy xử lý thế nào?  
**Trả lời:** Dùng ObjectName.quote() cho value.

**Câu 7.** Vì sao đổi ObjectName cần kế hoạch migration?  
**Trả lời:** Monitoring scripts và JMX clients có thể đang phụ thuộc tên cũ.

**Câu 8.** Một identifier đủ an toàn cho JMX production cần gì?  
**Trả lời:** Target/server identity được xác minh, ObjectName rõ ràng và access controls thực thi riêng.

## 23. Ghi nhớ

- JMX ObjectName có phạm vi duy nhất trong một MBeanServer.
- Chọn quy ước tên nhất quán cho prod, staging, local.
- env trong ObjectName là nhãn nhận diện, không phải bảo mật.
- Không nhầm Spring profiles với deployment environment.
- Dùng runtime naming nếu ứng dụng deploy cùng artifact lên nhiều môi trường.
- Quote property values động; validate key/domain và giới hạn độ dài.
- Tránh collision giữa contexts và instances cùng server.
- Không đưa bí mật hoặc dữ liệu cardinality cao vào ObjectName.
- Đổi tên làm thay đổi management API, cần cập nhật client.
- Trước khi thao tác nhạy cảm, xác nhận cả connector target và MBean identity.

### Tài liệu tham khảo

- Spring Framework Reference — JMX Exporting: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Spring Framework Javadoc — MBeanExporter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Javadoc — ObjectNamingStrategy: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/naming/ObjectNamingStrategy.html
- Java SE 21 API — ObjectName: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
- Java SE 21 API — MBeanServer: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
