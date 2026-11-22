# ObjectName khác với tên dự kiến trong Spring Framework JMX

## 1. Mục tiêu bài học

Trong Spring Framework JMX, bạn có thể cấu hình một Spring bean tên `paymentQueue`, đặt annotation `@ManagedResource(objectName = "...")`, hoặc khai báo `MBeanExporter`, nhưng khi mở JConsole/JMC lại thấy MBean dưới một `ObjectName` khác dự kiến. Điều này có thể khiến dashboard không tìm được attribute, script gọi operation thất bại hoặc hai ứng dụng vô tình dùng chung tên quản trị.

Bài học thuộc **Spring Framework JMX → Chẩn đoán sự cố**, tập trung vào nguyên nhân và cách xử lý khi ObjectName thực tế khác ObjectName kỳ vọng.

Sau bài này, bạn có thể:

- Phân biệt **Spring bean name**, **Java class name**, **JMX domain** và **ObjectName**.
- Xác định chính xác MBean đã được đăng ký dưới tên nào bằng `MBeanServer.queryNames`.
- Phân biệt khác biệt **chuỗi hiển thị** với khác biệt **danh tính ObjectName**.
- Truy nguyên cấu hình `MBeanExporter`, `ObjectNamingStrategy`, `MetadataNamingStrategy`, `@ManagedResource` và bean key.
- Nhận biết các tình huống JDK/CGLIB proxy và nhiều exporter làm thay đổi tên nhìn thấy.
- Kiểm tra đúng `MBeanServer`/remote connector trước khi kết luận tên bị đặt sai.
- Viết integration test để ngăn ObjectName thay đổi ngoài dự kiến sau refactor hoặc redeploy.

## 2. Trước tiên: ObjectName là gì?

JMX định danh MBean bằng `javax.management.ObjectName`:

```text
domain:key1=value1,key2=value2,...
```

Ví dụ:

```text
com.example.billing:type=Queue,name=Payment
```

Trong một `MBeanServer`, ObjectName này xác định một registration duy nhất. Spring bean có thể tên `paymentQueueMonitor`, class Java tên `PaymentQueueMonitor`, nhưng tên JMX vẫn có thể là `com.example.billing:type=Queue,name=Payment`.

Bốn tên thường bị nhầm:

| Khái niệm | Ví dụ | Dùng để |
| --- | --- | --- |
| Spring bean name | `paymentQueueMonitor` | Tìm/inject bean trong ApplicationContext |
| Java class | `com.example.billing.PaymentQueueMonitor` | Định nghĩa kiểu và implementation |
| JMX domain | `com.example.billing` | Nhóm MBean trong một registry |
| JMX ObjectName | `com.example.billing:type=Queue,name=Payment` | Định danh MBean trong MBeanServer |

**Không có quy tắc bắt buộc ObjectName phải trùng tên Spring bean hoặc class Java.** Nếu muốn hợp đồng tên ổn định, phải cấu hình và kiểm thử rõ ràng.

## 3. Triệu chứng thường gặp

Một số biểu hiện:

1. JConsole thấy `com.example.billing:name=Payment,type=Queue` thay vì `com.example.billing:type=Queue,name=Payment`.
2. Spring bean tên `paymentQueue`, nhưng MBean được export theo tên class hoặc domain khác.
3. `@ManagedResource(objectName = "...")` khai báo một tên, nhưng exporter thực tế không dùng annotation metadata như dự kiến.
4. JMX client truy vấn tên cố định trả `InstanceNotFoundException`.
5. Một dashboard không tìm ra MBean sau khi bật Spring AOP hoặc đổi naming strategy.
6. MBean xuất hiện ở một JVM/connector khác, khiến người vận hành tưởng tên bị thay đổi.
7. Có hai exporters, một exporter sử dụng mapping explicit còn exporter khác autodetect, dẫn đến kết quả không như kỳ vọng hoặc lỗi trùng tên.

Cần chia nhỏ chẩn đoán thành **so sánh tên**, **xác định registry**, **đường sinh tên** và **vòng đời export**.

## 4. Khác thứ tự key không phải khác ObjectName

Hai chuỗi:

```text
com.example.billing:type=Queue,name=Payment
com.example.billing:name=Payment,type=Queue
```

biểu diễn **cùng một ObjectName**. JMX không dựa vào thứ tự key properties để xác định danh tính.

```java
import javax.management.ObjectName;

ObjectName expected = new ObjectName(
    "com.example.billing:type=Queue,name=Payment"
);

ObjectName actual = new ObjectName(
    "com.example.billing:name=Payment,type=Queue"
);

System.out.println(expected.equals(actual)); // true
System.out.println(expected.getCanonicalName());
System.out.println(actual.getCanonicalName());
```

Vì vậy:

- Nếu `ObjectName.equals` là `true`, không cần sửa naming chỉ vì JConsole hiển thị thứ tự key khác.
- `getCanonicalName()` hữu ích để log và so sánh tên chuẩn.
- Không dùng `String.equals` trên hai chuỗi raw để kết luận registration khác nhau.

Đây là bước đầu tiên giúp tránh sửa một cấu hình vốn đã đúng.

## 5. Xác định ObjectName đã đăng ký thực tế

Đừng đoán tên MBean từ annotation hoặc Spring bean name. Truy vấn trực tiếp server:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.util.Set;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName pattern = new ObjectName(
    "com.example.billing:*"
);

Set<ObjectName> names = server.queryNames(pattern, null);

for (ObjectName item : names) {
    System.out.println(item.getCanonicalName());
}
```

Nếu không thấy tên:

- Có thể MBean chưa đăng ký.
- Có thể domain thực tế khác `com.example.billing`.
- Có thể exporter dùng một `MBeanServer` tùy biến.
- Có thể client đang kết nối sai JVM hoặc endpoint.
- Có thể bean đã unregister do context đóng.

Nếu chưa biết domain, **trong môi trường test/diagnostic có kiểm soát** có thể liệt kê các domain qua `getDomains()` hoặc tìm trên một server đã được định danh. Tránh scan quá rộng một hệ thống production nhiều MBean nếu không cần.

### Kiểm tra một tên cụ thể

```java
ObjectName expected = new ObjectName(
    "com.example.billing:type=Queue,name=Payment"
);

System.out.println(
    "Expected name registered = " + server.isRegistered(expected)
);
```

`isRegistered == false` chỉ chứng minh **server đang hỏi** không có tên đó, không chứng minh tên bị Spring đổi. Kiểm tra server đích trước khi sửa config.

## 6. Phân biệt sai ObjectName với sai MBeanServer

Một JVM có thể có nhiều MBeanServer:

```text
JVM
  |
  +-- Platform MBeanServer
  |     +-- java.lang:type=Memory
  |
  +-- Custom MBeanServer
        +-- com.example.billing:type=Queue,name=Payment
```

Nếu exporter dùng:

```java
exporter.setServer(customServer);
```

mà code chẩn đoán dùng:

```java
ManagementFactory.getPlatformMBeanServer();
```

thì `isRegistered(expected)` trả `false` dù tên thực tế hoàn toàn đúng.

Kiểm tra:

- Exporter được inject server bean nào?
- Có dùng `MBeanServerFactoryBean` hay `MBeanServerFactory` tạo custom server không?
- Client JConsole/JMC đang kết nối tới registry nào?
- Nếu remote connector, connector phục vụ platform server hay custom server?
- Có nhiều JVM hoặc replica dùng cùng ObjectName không?

**Danh tính toàn hệ thống cần cả server/endpoint lẫn ObjectName.** Hai JVM có thể dùng cùng tên mà không xung đột.

## 7. Các nguồn tạo ObjectName trong Spring

Spring có nhiều cách xác định tên khi export MBean.

### Cách 1: map explicit beans

```java
import java.util.Map;
import org.springframework.jmx.export.MBeanExporter;

MBeanExporter exporter = new MBeanExporter();

exporter.setBeans(Map.of(
    "com.example.billing:type=Queue,name=Payment",
    paymentQueueMonitor
));
```

Ở cấu hình này, key map cung cấp tên JMX đầy đủ. Nếu key hợp lệ như ObjectName, nó có thể được dùng trực tiếp cho registration tùy đường cấu hình.

### Cách 2: annotation-based metadata

```java
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.billing:type=Queue,name=Payment"
)
public class PaymentQueueAdmin {
    // @ManagedAttribute / @ManagedOperation ...
}
```

Khi dùng annotation exporter và metadata naming strategy phù hợp, thông tin `objectName` trong `@ManagedResource` có thể được dùng để xác định tên.

### Cách 3: ObjectNamingStrategy

Exporter có thể sử dụng một `ObjectNamingStrategy` như `KeyNamingStrategy`, `MetadataNamingStrategy`, `IdentityNamingStrategy` hoặc strategy tùy chỉnh.

```text
Spring bean / bean key
       |
       v
ObjectNamingStrategy
       |
       v
javax.management.ObjectName
       |
       v
MBeanServer.registerMBean(...)
```

Nếu tên khác dự kiến, hãy tìm xem **đường cấu hình nào đang thực sự hoạt động**. Một annotation trên class không nhất thiết được ưu tiên nếu exporter đang dùng key explicit hoặc strategy khác.

## 8. MetadataNamingStrategy và @ManagedResource

Với annotation-driven JMX, Spring thường kết hợp:

```text
AnnotationJmxAttributeSource
        |
        v
MetadataNamingStrategy
        |
        v
@ManagedResource(objectName = ...)
        |
        v
ObjectName
```

Nếu annotation được phát hiện và tên được cung cấp phù hợp, strategy có thể dùng tên đã khai báo.

Nhưng nếu bạn tạo `MBeanExporter` thủ công mà chỉ gọi:

```java
exporter.setBeans(Map.of("paymentQueue", bean));
```

mà không cài metadata naming/assembler thích hợp, đừng mặc định exporter tự lấy `@ManagedResource(objectName=...)` theo cơ chế annotation-driven.

Để kiểm tra, hãy xác định:

1. Exporter nào đang dùng.
2. Naming strategy của exporter đó.
3. Metadata source/assembler có được cấu hình không.
4. Bean thực tế exporter nhận là target hay proxy.
5. ObjectName trong `MBeanServer` có trùng metadata kỳ vọng không.

## 9. KeyNamingStrategy và sự khác biệt của bean key

Giả sử:

```java
exporter.setBeans(Map.of(
    "paymentQueue",
    paymentQueueMonitor
));
```

Key `paymentQueue` có thể là khóa logic cho naming strategy, không phải một ObjectName đầy đủ. Khi đó strategy quyết định tên cuối:

```text
paymentQueue -> com.example.billing:type=Queue,name=Payment
```

Nếu key bị đổi trong cấu hình nhưng naming strategy dùng key để tạo tên, ObjectName có thể thay đổi theo. Ngược lại, nếu mapping explicit dùng ObjectName đầy đủ, đổi Spring bean name chưa chắc tác động tới tên JMX.

Vì vậy, trước khi refactor bean IDs, cần biết **key nào là một phần hợp đồng quản trị**. Đừng sử dụng một tên không ổn định chỉ vì nó thuận tiện cho dependency injection.

## 10. IdentityNamingStrategy và tên runtime

Một nguyên nhân gây bất ngờ là naming dựa trên identity/class.

Khi strategy sử dụng danh tính runtime, ObjectName có thể chứa dấu vết của implementation class hoặc object identity. Tên như vậy không phù hợp khi dashboard kỳ vọng một tên logic cố định.

Ví dụ kỳ vọng:

```text
com.example.billing:type=Queue,name=Payment
```

nhưng thực tế lại xuất tên chứa thông tin class hoặc instance-specific suffix.

Giải pháp thường là dùng:

- Explicit ObjectName cho resource có định danh ổn định.
- Metadata naming với `@ManagedResource(objectName=...)`.
- Custom naming strategy ánh xạ bean key logic sang tên ổn định.

Không chỉ “cắt suffix” ở client để chữa cháy. Nếu tên có thể thay đổi theo restart, cần sửa tại **nguồn tạo tên** và có integration test.

## 11. Spring AOP proxy ảnh hưởng naming

Một Spring bean có thể được bọc bởi:

- JDK dynamic proxy.
- CGLIB/class-based proxy.

Nếu naming strategy dùng trực tiếp:

```java
managedBean.getClass().getName()
```

thì tên class runtime có thể không giống target class:

```text
jdk.proxy2.$Proxy...
OrderQueueService$$SpringCGLIB$$...
```

Đây là nguồn tạo tên thiếu ổn định. Với annotation-based JMX, metadata source cần tìm annotation trên class/method phù hợp; kiểu proxy cũng có thể ảnh hưởng khả năng introspection.

Có thể chẩn đoán:

```java
import org.springframework.aop.framework.AopProxyUtils;
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("paymentQueueMonitor");

System.out.println("Runtime class: " + bean.getClass());
System.out.println("AOP proxy: " + AopUtils.isAopProxy(bean));
System.out.println(
    "Target class: " + AopProxyUtils.ultimateTargetClass(bean)
);
```

**Không tự lấy target object ra khỏi proxy để export** khi chưa xem xét transaction/security advice; làm vậy có thể khiến operation JMX bỏ qua logic AOP cần thiết. Nếu service proxy phức tạp, cân nhắc JMX adapter riêng.

## 12. MBeanExporter và nhiều exporter trùng nhau

Một ứng dụng có thể vô tình có:

```java
@EnableMBeanExport
```

và một bean `MBeanExporter` khai báo thủ công. Nếu hai exporter cùng phát hiện một resource:

- Chúng có thể cố đăng ký cùng ObjectName và gây `InstanceAlreadyExistsException`.
- Chúng có thể dùng hai cách naming khác nhau, khiến cùng một bean xuất hiện nhiều lần dưới hai ObjectName.
- Với `RegistrationPolicy.IGNORE_EXISTING`, một registration mới có thể bị bỏ qua, khiến người vận hành nhìn thấy MBean cũ.
- Với `REPLACE_EXISTING`, resource hiện tại có thể bị thay thế theo ownership/configuration.

Khi ObjectName khác dự kiến, kiểm tra tất cả exporter thực sự hoạt động trong ApplicationContext, không chỉ exporter mà bạn đang xem source.

Không sửa bằng cách xóa ngẫu nhiên MBean trên server: đó có thể là MBean thuộc một module khác.

## 13. Cấu hình Java với ObjectName explicit ổn định

Một ví dụ cấu hình dễ kiểm thử:

```java
package com.example.billing.config;

import com.example.billing.jmx.PaymentQueueMonitor;
import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

@Configuration
public class BillingJmxConfiguration {

    public static final String PAYMENT_QUEUE_OBJECT_NAME =
        "com.example.billing:type=Queue,name=Payment";

    @Bean
    public PaymentQueueMonitor paymentQueueMonitor() {
        return new PaymentQueueMonitor();
    }

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter billingMBeanExporter(
            PaymentQueueMonitor paymentQueueMonitor,
            MBeanServer platformMBeanServer) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(platformMBeanServer);
        exporter.setBeans(Map.of(
            PAYMENT_QUEUE_OBJECT_NAME,
            paymentQueueMonitor
        ));
        exporter.setRegistrationPolicy(
            RegistrationPolicy.FAIL_ON_EXISTING
        );
        return exporter;
    }
}
```

Ở ví dụ này, `PaymentQueueMonitor` phải là MBean hợp lệ theo cách export đã chọn (Standard MBean interface hoặc ModelMBean metadata tương ứng). Điều quan trọng là định danh nằm trong một constant được quản lý có chủ đích và được test.

Nếu ứng dụng có nhiều MBean, có thể tạo helper riêng để tạo ObjectName bằng API của `ObjectName` thay vì nối chuỗi tùy tiện.

## 14. Kiểm thử ObjectName kỳ vọng với MBeanServer

Một integration test nên khởi tạo context thực và kiểm tra exact ObjectName:

```java
import static org.junit.jupiter.api.Assertions.*;

import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class BillingJmxNamingTest {

    @Test
    void registersWithStableObjectName() throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                BillingJmxConfiguration.class)) {

            MBeanServer server = context.getBean(MBeanServer.class);

            ObjectName expected = new ObjectName(
                BillingJmxConfiguration.PAYMENT_QUEUE_OBJECT_NAME
            );

            assertTrue(
                server.isRegistered(expected),
                "MBean missing: " + expected.getCanonicalName()
            );

            assertFalse(expected.isPattern());
        }
    }
}
```

Với test chạy song song, nên thay platform server bằng một `MBeanServer` riêng trong test configuration để tránh conflict với production beans/test khác.

Đọc `MBeanInfo` nếu muốn xác minh thêm contract:

```java
var info = server.getMBeanInfo(expected);

System.out.println("MBean class = " + info.getClassName());
System.out.println("Attribute count = " + info.getAttributes().length);
```

**Đừng dùng `MBeanInfo.getClassName()` một mình để xác định owner:** Spring ModelMBean có thể có metadata/class khác kỳ vọng.

## 15. Kiểm tra tên thực tế bằng queryNames

Nếu không thấy exact name, dùng query theo domain hoặc một key ổn định:

```java
ObjectName pattern = new ObjectName(
    "com.example.billing:type=Queue,*"
);

var candidates = server.queryNames(pattern, null);

for (ObjectName candidate : candidates) {
    System.out.println(candidate.getCanonicalName());
}
```

Nếu thấy:

```text
com.example.billing:name=Payment,type=Queue
```

hãy so sánh bằng `equals`. Nếu thấy:

```text
com.example.billing:name=PaymentQueue,type=Queue
```

thì key property khác thật, cần truy naming strategy hoặc cấu hình.

Nếu không thấy candidate nào, hãy xác minh server. Đừng tự đổi tên dự kiến cho khớp một resource ngẫu nhiên khác có thể có trong namespace.

## 16. Những lỗi liên quan đến domain, key và quoting

Một vài trường hợp:

### Domain khác

```text
expected: com.example.billing:type=Queue,name=Payment
actual:   com.example.payment:type=Queue,name=Payment
```

Đây là ObjectName khác. Kiểm tra naming convention hoặc metadata.

### Key khác

```text
expected: com.example.billing:type=Queue,name=Payment
actual:   com.example.billing:type=Queue,id=Payment
```

Đây cũng là ObjectName khác. `name` và `id` không tương đương.

### Value khác chữ hoa/thường

```text
expected: com.example.billing:type=Queue,name=Payment
actual:   com.example.billing:type=Queue,name=payment
```

Key property values của ObjectName có phân biệt chữ hoa/thường. Hai tên này không tương đương.

### Ký tự đặc biệt

Nếu tên logic chứa `,`, `=`, `:`, `*`, `?`, cần xử lý theo cú pháp ObjectName. Có thể dùng:

```java
String logicalName = "Billing,Priority";
String objectNameText =
    "com.example.billing:type=Queue,name="
    + ObjectName.quote(logicalName);

ObjectName name = new ObjectName(objectNameText);
```

Không tự ghép input không tin cậy vào ObjectName mà không kiểm soát cú pháp và giá trị. Một ký tự wildcard có thể biến tên thành pattern, không phải tên concrete dùng cho registration.

## 17. Tên thực tế có ổn định sau restart không?

Một diagnostic test quan trọng:

```text
Run 1:
  ObjectName = com.example.billing:type=Queue,name=Payment

Run 2:
  ObjectName = com.example.billing:type=Queue,name=Payment
```

Nếu ObjectName thay đổi qua restart dù resource logic vẫn là một, cần kiểm tra:

- Naming dựa vào UUID/time/PID.
- Naming dựa trên runtime class/proxy identity.
- Bean key được sinh động.
- Môi trường hoặc deployment properties thay đổi.
- Sự khác nhau giữa profiles/configuration đang bật.
- Nhiều exporter chọn naming strategy khác nhau.

Dashboard, alert và runbook nên dựa vào tên logic ổn định, trừ khi mục tiêu cố ý phân biệt instance bằng một key có nghĩa.

## 18. Cách điều tra khi remote JMX không tìm thấy tên

Một remote client có thể kết nối tới JVM khác cùng ObjectName. Vì vậy, khi JConsole báo không có MBean:

1. Xác minh `JMXServiceURL` hoặc hostname/port.
2. Xác minh environment (dev/staging/prod) và instance.
3. Kết nối thành công với remote `MBeanServerConnection`.
4. Gọi `getDomains()`/`queryNames()` trên connection đó.
5. So sánh exact ObjectName.
6. Nếu MBean không có, kiểm tra exporter bên JVM đích.
7. Xem lại có custom MBeanServer không được connector phục vụ hay không.

Một ObjectName đúng nhưng trên **sai endpoint** vẫn sẽ không truy cập được MBean mong muốn. Đừng thay đổi ObjectName chỉ để khớp sai JVM.

## 19. Quy trình chẩn đoán từng bước

```text
1. Ghi expected ObjectName
          |
          v
2. Parse bằng new ObjectName(...)
          |
          v
3. Xác định đúng MBeanServer / remote endpoint
          |
          v
4. isRegistered(expected)?
       /           \
     yes           no
      |             |
      v             v
5. Đọc MBeanInfo   6. queryNames(domain/pattern)
      |             |
      v             v
Đã có đúng tên?    Có candidate?
                    /       \
                  yes       no
                   |         |
                   v         v
              So sánh       Kiểm tra exporter,
              canonical     server, context,
              name/key      lifecycle
                   |
                   v
              Truy nguồn:
              bean key / strategy /
              annotation / proxy
```

Sau khi tìm được nguyên nhân, sửa tại nguồn sinh tên rồi chạy lại integration test. Đừng chữa bằng cách hardcode tên ngẫu nhiên vừa thấy trong JConsole mà không hiểu semantics.

## 20. Bảng nguyên nhân và biện pháp

| Triệu chứng | Nguyên nhân phổ biến | Cách xử lý |
| --- | --- | --- |
| JConsole hiển thị key theo thứ tự khác | Canonicalization | So sánh `ObjectName.equals()`, không sửa |
| `isRegistered` false | Sai MBeanServer hoặc exporter chưa chạy | Kiểm tra server/context/lifecycle |
| `@ManagedResource` không được dùng làm tên | Exporter không dùng annotation metadata naming | Cấu hình đúng exporter/strategy |
| ObjectName đổi sau bật AOP | Naming dựa vào proxy runtime class | Dùng ObjectName logic ổn định |
| MBean xuất hiện hai tên | Hai exporters hoặc hai đường export | Xác định một owner |
| `InstanceAlreadyExistsException` | Đăng ký trùng canonical ObjectName | Kiểm tra ownership và policy |
| Tên khác chữ hoa/thường | Input key/value khác | Chuẩn hóa tại nguồn naming |
| Tên không hợp lệ | Dấu phân cách chưa quote | Dùng `ObjectName.quote` hoặc constructor phù hợp |
| Sai tên sau restart | ID động, profile/config khác | Sử dụng logical identifier ổn định |
| Không thấy MBean remote | Connector phục vụ server khác hoặc nhầm JVM | Kiểm tra endpoint và server đích |

## 21. Kiểm thử ngăn regression về naming

Một test suite nên có:

1. **Unit test strategy:** đưa vào cùng logical bean/key phải tạo cùng `ObjectName`.
2. **Canonical equality test:** đảo thứ tự key nhưng vẫn tương đương.
3. **Special characters test:** tên có dấu phẩy, dấu bằng, wildcard được xử lý đúng.
4. **Integration test exporter:** ApplicationContext đăng ký exact ObjectName vào đúng server.
5. **MBeanInfo test:** xác minh MBean có attribute/operation tương ứng.
6. **AOP proxy test:** bật AOP rồi xác minh ObjectName không đổi.
7. **Multi-context test:** hai contexts không cùng đăng ký một ObjectName ngoài ý muốn.
8. **Lifecycle test:** khi đóng context, MBean do exporter sở hữu được unregister.
9. **Remote target test:** nếu dùng remote JMX, xác minh endpoint cùng ObjectName và instance identity.

Test dùng MBeanServer riêng thường đáng tin cậy hơn platform server dùng chung trong JUnit chạy song song.

## 22. Bài tập thực hành

1. Tạo hai chuỗi ObjectName khác thứ tự key, dùng `ObjectName.equals()` để giải thích vì sao chúng là cùng MBean identity.
2. Cấu hình Spring exporter với key explicit và kiểm tra `isRegistered` sau khi context khởi tạo.
3. Đổi `KeyNamingStrategy` hoặc đổi bean key và ghi nhận ObjectName khác.
4. Dùng `@ManagedResource(objectName=...)` và annotation exporter; so sánh với exporter dùng explicit beans map.
5. Bật Spring AOP proxy cho một service; quan sát runtime class và so sánh naming dựa class với tên explicit.
6. Tạo hai exporter cùng đăng ký một ObjectName trong server test; chẩn đoán lỗi trùng tên.
7. Viết test chạy hai lần khởi tạo context để xác minh tên ổn định qua restart.
8. Tạo một JMX client kết nối sai endpoint rồi tìm nguyên nhân `InstanceNotFoundException`.

## 23. Câu hỏi tự kiểm tra

- Spring bean name có bắt buộc là ObjectName không?
- Hai ObjectName chỉ khác thứ tự key property có khác danh tính không?
- Vì sao phải kiểm tra MBeanServer trước khi kết luận naming strategy sai?
- `@ManagedResource(objectName=...)` có luôn được mọi `MBeanExporter` dùng không?
- Proxy Spring có thể ảnh hưởng tên sinh từ `bean.getClass()` thế nào?
- Nếu một bean xuất hiện dưới hai ObjectName, cần tìm những cấu hình nào?
- Vì sao một ObjectName ổn định quan trọng với dashboard và alert?
- Khi remote JMX không tìm thấy MBean, cần xác minh endpoint nào?

**Ghi nhớ:** Khi ObjectName khác dự kiến, đừng sửa cấu hình ngay. Hãy phân biệt cách hiển thị và danh tính thật bằng `ObjectName.equals()`, kiểm tra **đúng MBeanServer**, truy vấn danh sách tên thực tế rồi lần theo exporter, naming strategy, annotation, bean key và proxy. Giữ ObjectName theo định danh logic ổn định và bảo vệ hợp đồng tên bằng integration test.