# Giải quyết bean name, ObjectName và tên hiển thị trong Spring Framework JMX

## 1. Mục tiêu

Khi đưa một Spring bean ra Java Management Extensions (JMX), có ít nhất ba cách “gọi tên” cùng một đối tượng:

- **Bean name**: tên định danh của bean trong Spring ApplicationContext.
- **ObjectName**: định danh MBean trong MBeanServer, có cú pháp JMX gồm domain và các key properties.
- **Tên hiển thị**: nhãn hoặc mô tả do công cụ quản trị như JConsole, VisualVM hay dashboard hiển thị; có thể đến từ ObjectName, MBean metadata hoặc logic của chính công cụ.

Ví dụ, một Spring bean có thể tên \`checkoutMonitor\`, được export bằng ObjectName \`com.example.shop:type=Queue,name=Checkout\`, còn JConsole hiển thị nút \`Queue\` → \`Checkout\` hoặc mô tả \`Checkout queue monitor\`.

Ba cách gọi này **không tự động đồng nhất**. Cấu hình thiếu rõ ràng dễ dẫn tới MBean không tìm thấy, ObjectName trùng, tên không ổn định sau restart, hoặc UI hiển thị khác điều người vận hành mong đợi.

Sau bài học, bạn có thể:

1. Phân biệt ba lớp tên và phạm vi duy nhất của chúng.
2. Biết thành phần nào của Spring quyết định bean name và ObjectName.
3. Dùng \`@ManagedResource\`, \`MBeanExporter\` và naming strategy để kiểm soát tên.
4. Chẩn đoán khác biệt giữa tên trong Spring context và tên trong MBeanServer.
5. Thiết kế domain/key properties ổn định cho monitoring.
6. Xác minh tên hiển thị bằng \`ObjectName\` và \`MBeanInfo\`.
7. Xử lý collision, AOP proxy và nhiều ApplicationContext.

## 2. Ba lớp tên trong một sơ đồ

\`\`\`text
Spring ApplicationContext
    |
    +-- bean name: "checkoutMonitor"
    |         |
    |         v
    |    Java bean object
    |         |
    |         v
    |    MBeanExporter
    |         |
    |         +--> ObjectNamingStrategy / @ManagedResource
    |                  |
    |                  v
    +---------- MBeanServer -------------------+
               ObjectName:                    |
               com.example.shop:              |
                 type=Queue,name=Checkout     |
                                              |
                                   JMX client / JConsole
                                              |
                                              v
                                 Nhãn và nhóm hiển thị
                                 theo ObjectName + metadata
\`\`\`

| Loại tên | Ví dụ | Ai quản lý | Phạm vi |
|---|---|---|---|
| Spring bean name | \`checkoutMonitor\` | Spring BeanFactory/ApplicationContext | Bean namespace của context |
| JMX ObjectName | \`com.example.shop:type=Queue,name=Checkout\` | MBeanServer + exporter | Duy nhất trong một MBeanServer |
| Display name/description | \`Checkout queue monitor\` | MBean metadata hoặc JMX client | Tùy công cụ và cách dựng UI |

**Điểm mấu chốt:** bean name không phải ObjectName, và một description trong MBeanInfo cũng không phải khóa JMX dùng để gọi \`getAttribute\` hoặc \`invoke\`.

## 3. Bean name trong Spring

Spring quản lý bean bằng tên trong context. Với Java configuration:

\`\`\`java
@Bean("checkoutMonitor")
public CheckoutMonitor monitor() {
    return new CheckoutMonitor();
}
\`\`\`

Hoặc component scanning:

\`\`\`java
@Component("checkoutMonitor")
public class CheckoutMonitor {
    // ...
}
\`\`\`

Dù hai cách đều đặt tên bean là \`checkoutMonitor\`, chúng không quyết định chắc chắn MBean sẽ được đăng ký dưới ObjectName nào.

Có thể lấy bean:

\`\`\`java
Object bean = context.getBean("checkoutMonitor");
\`\`\`

Lời gọi này là Spring container lookup, hoàn toàn khác:

\`\`\`java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
server.getAttribute(
    new ObjectName("com.example.shop:type=Queue,name=Checkout"),
    "PendingCount");
\`\`\`

Cái thứ hai là JMX lookup trên một MBeanServer.

### 3.1. Tên bean, alias và context hierarchy

Một bean có thể có alias trong Spring. Alias không tự tạo nhiều MBean. Root context và child context có thể chứa bean cùng tên hoặc shadow tên lẫn nhau; nhưng nếu cả hai exporter đăng ký một ObjectName giống nhau vào cùng server thì bị trùng JMX, bất kể hai context khác nhau.

**Quy tắc:** tính duy nhất của bean name và ObjectName được kiểm soát bởi các registry khác nhau.

## 4. ObjectName trong JMX

Cú pháp chung:

\`\`\`text
<domain>:<key>=<value>,<key>=<value>
\`\`\`

Ví dụ:

\`\`\`text
com.example.shop:type=Queue,name=Checkout
\`\`\`

Trong đó:

- \`com.example.shop\`: domain.
- \`type=Queue\`: nhóm resource.
- \`name=Checkout\`: instance hoặc resource logic.
- Có thể thêm \`module=orders\`, \`region=vn\`, \`instance=node-1\` nếu cần phân biệt.

Một ObjectName không phải chuỗi tùy ý. Java JMX có quy tắc ký tự đặc biệt và quoting. Tạo từ Java API:

\`\`\`java
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.shop:type=Queue,name=Checkout");
\`\`\`

Hai ObjectName có cùng domain và cùng tập key-value bằng nhau, dù thứ tự property khác nhau:

\`\`\`java
ObjectName a = new ObjectName(
    "com.example.shop:type=Queue,name=Checkout");
ObjectName b = new ObjectName(
    "com.example.shop:name=Checkout,type=Queue");

System.out.println(a.equals(b)); // true
\`\`\`

Khi đặt tên từ dữ liệu có ký tự đặc biệt, dùng validation và \`ObjectName.quote\` khi phù hợp. Đừng nối trực tiếp giá trị lấy từ request không tin cậy vào ObjectName.

### 4.1. Default domain không thay mọi ObjectName

Một \`MBeanServer\` có default domain, nhưng nếu một MBean được đăng ký với ObjectName đã chỉ rõ domain, default domain không viết đè domain ấy. Đừng đặt \`defaultDomain\` trên server rồi mong nó thay đổi mọi ObjectName của Spring beans.

### 4.2. ObjectName là public contract

Client JMX tìm MBean bằng ObjectName. Khi đổi:

\`\`\`text
com.example.shop:type=Queue,name=Checkout
\`\`\`

thành:

\`\`\`text
com.example.shop:type=Queue,name=CheckoutV2
\`\`\`

dashboard và automation dùng tên cũ có thể hỏng dù bean name vẫn là \`checkoutMonitor\`. Với MBean được monitoring lâu dài, nên chọn tên ổn định theo resource logic.

## 5. Tên hiển thị đến từ đâu?

Đối với các công cụ JMX, “display name” không phải một field bắt buộc, thống nhất trên mọi MBean. UI có thể dựa vào:

1. Domain và key properties của \`ObjectName\` để dựng cây MBeans.
2. \`MBeanInfo.getDescription()\` để mô tả resource.
3. \`MBeanAttributeInfo.getDescription()\` và \`MBeanOperationInfo.getDescription()\`.
4. Quy tắc sắp xếp/nhóm của JConsole, VisualVM hoặc sản phẩm dashboard.
5. Cấu hình riêng ở công cụ giám sát.

Ví dụ:

\`\`\`java
@ManagedResource(
    objectName = "com.example.shop:type=Queue,name=Checkout",
    description = "Checkout queue operational view")
public class CheckoutMonitor {
    // ...
}
\`\`\`

Ở đây \`description\` là thông tin metadata cho con người, **không thay ObjectName**. JConsole có thể hiển thị resource theo \`type\`, \`name\` hoặc cấu trúc riêng của công cụ; không có bảo đảm mọi JMX client sẽ hiển thị chính xác \`description\` làm nhãn chính.

### 5.1. Không dùng nhãn UI làm khóa kết nối

Một nhân viên vận hành thấy “Checkout queue operational view” trong UI có thể nghĩ đó là tên MBean. Nhưng client code phải sử dụng ObjectName thật:

\`\`\`java
ObjectName name = new ObjectName(
    "com.example.shop:type=Queue,name=Checkout");
\`\`\`

Không gọi:

\`\`\`java
new ObjectName("Checkout queue operational view");
\`\`\`

vì không đúng cú pháp ObjectName.

## 6. Ví dụ Spring @ManagedResource: tên đầy đủ, rõ ràng

Một bean giám sát:

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component("checkoutMonitor")
@ManagedResource(
    objectName = "com.example.shop:type=Queue,name=Checkout",
    description = "Checkout queue operational view")
public class CheckoutMonitor {

    private final AtomicInteger pending =
        new AtomicInteger();

    @ManagedAttribute(
        description = "Number of pending checkout tasks")
    public int getPendingCount() {
        return pending.get();
    }

    @ManagedOperation(
        description = "Reset demonstration counter")
    public void resetDemoCounter() {
        pending.set(0);
    }

    public void recordPendingTask() {
        pending.incrementAndGet();
    }
}
\`\`\`

Spring configuration:

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@ComponentScan(basePackageClasses = CheckoutMonitor.class)
@EnableMBeanExport
public class AppConfig {
}
\`\`\`

Spring exporter nhận metadata khi được cấu hình phù hợp, đăng ký object dưới ObjectName được khai báo. Một ứng dụng có nhiều exporter hoặc MBeanServer phải chỉ rõ server/ownership để tránh trùng đăng ký.

Để chạy trong một demo:

\`\`\`java
package example.jmx;

import org.springframework.context.annotation
    .AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(
                    AppConfig.class)) {

            CheckoutMonitor monitor =
                context.getBean("checkoutMonitor",
                    CheckoutMonitor.class);

            monitor.recordPendingTask();

            System.out.println(
                "Spring bean name: checkoutMonitor");
            System.out.println(
                "PID: " + ProcessHandle.current().pid());

            Thread.sleep(120_000);
        }
    }
}
\`\`\`

Dùng JConsole local để quan sát MBean đã được export. **Đừng đồng nhất tên \`checkoutMonitor\` với ObjectName** chỉ vì trong ví dụ cùng trỏ đến một resource.

## 7. Cấu hình MBeanExporter tường minh

Khi cần kiểm soát ObjectName từ cấu hình thay vì annotation, dùng \`MBeanExporter\`:

\`\`\`java
import java.util.Map;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.MethodNameBasedMBeanInfoAssembler;

@Configuration
public class ExplicitJmxConfig {

    @Bean("checkoutMonitor")
    public CheckoutMonitor checkoutMonitor() {
        return new CheckoutMonitor();
    }

    @Bean
    public MethodNameBasedMBeanInfoAssembler assembler() {
        MethodNameBasedMBeanInfoAssembler a =
            new MethodNameBasedMBeanInfoAssembler();
        a.setManagedMethods(
            "getPendingCount", "resetDemoCounter");
        return a;
    }

    @Bean
    public MBeanExporter mbeanExporter(
            MBeanServer server,
            CheckoutMonitor checkoutMonitor,
            MethodNameBasedMBeanInfoAssembler assembler) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(server);
        exporter.setAssembler(assembler);
        exporter.setBeans(Map.of(
            "com.example.shop:type=Queue,name=Checkout",
            checkoutMonitor));
        return exporter;
    }
}
\`\`\`

Ví dụ giả định context đã có đúng một bean \`MBeanServer\`; có thể khai báo:

\`\`\`java
@Bean
public MBeanServer mbeanServer() {
    return java.lang.management.ManagementFactory
        .getPlatformMBeanServer();
}
\`\`\`

Trong cấu hình explicit:

- Bean key \`checkoutMonitor\` phục vụ Spring DI.
- Mapping \`setBeans\` đặt ObjectName JMX.
- Assembler chọn methods/attributes được expose.
- \`MBeanServer\` là registry đích.

**Không bật thêm \`@EnableMBeanExport\` một cách vô ý cho cùng bean khi đã có exporter explicit**, bởi hai exporters có thể đăng ký cùng ObjectName.

## 8. ObjectNamingStrategy: khi không muốn hard-code từng tên

Spring có \`ObjectNamingStrategy\` để xác định ObjectName theo chiến lược. Một số kiểu phổ biến:

| Strategy | Nguồn tên | Tình huống |
|---|---|---|
| \`KeyNamingStrategy\` | Mapping key/bean key được quy đổi sang ObjectName | Tên ổn định do config quản lý |
| \`MetadataNamingStrategy\` | Metadata \`@ManagedResource\` | Tên được khai báo ở managed class |
| \`IdentityNamingStrategy\` | Identity của managed object | Cần phân biệt instances ở runtime |
| Custom strategy | Module ID/resource ID được chuẩn hóa | Quy ước tên đặc thù |

Khi dùng naming strategy, phải hiểu interaction giữa keys trong \`setBeans\`, metadata annotation và ObjectNames tường minh.

### 8.1. Bean name không nhất thiết là ObjectName do strategy trả về

Ví dụ:

\`\`\`text
Spring bean name = checkoutMonitor
ObjectNamingStrategy -> com.example.shop:type=Queue,name=Checkout
\`\`\`

Đây là ánh xạ hợp lệ. Một naming strategy có thể dùng bean name như một phần input, nhưng nó vẫn phải tạo \`ObjectName\` hợp lệ và duy nhất.

### 8.2. Identity naming và độ ổn định

Một strategy dựa trên object identity có thể sinh tên khác sau restart hoặc khi AOP proxy được tạo lại. Điều đó hữu ích cho phân biệt Java instances nhưng không lý tưởng cho dashboard với ObjectName hard-coded. Nếu cần theo dõi cùng resource logic, dùng key/metadata ổn định.

## 9. Debug bằng API: xem bean name và ObjectName

Đừng dựa vào UI. Hãy hỏi hai registry tương ứng.

### 9.1. Liệt kê Spring bean names có liên quan

\`\`\`java
String[] names =
    context.getBeanNamesForType(CheckoutMonitor.class);

for (String beanName : names) {
    System.out.println("Spring bean: " + beanName);
}
\`\`\`

Đoạn này chỉ cung cấp bean names theo type trong context, không tự trả ObjectNames JMX.

### 9.2. Liệt kê JMX ObjectNames

\`\`\`java
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.util.Set;

MBeanServer server =
    context.getBean(MBeanServer.class);

Set<ObjectName> names = server.queryNames(
    new ObjectName("com.example.shop:*"), null);

for (ObjectName name : names) {
    System.out.println("JMX ObjectName: " +
        name.getCanonicalName());
}
\`\`\`

Nếu context không có MBeanServer bean, cần lấy server thực tế exporter dùng hoặc platform server khi phù hợp. Đừng dùng \`getBean(MBeanServer.class)\` và giả định có sẵn trong mọi cấu hình.

### 9.3. Đọc MBean metadata để thấy description

\`\`\`java
ObjectName name = new ObjectName(
    "com.example.shop:type=Queue,name=Checkout");

MBeanInfo info = server.getMBeanInfo(name);

System.out.println("MBean class: " + info.getClassName());
System.out.println("Description: " + info.getDescription());

for (MBeanAttributeInfo a : info.getAttributes()) {
    System.out.println(
        "Attribute " + a.getName() +
        " description=" + a.getDescription());
}
\`\`\`

Description có thể khác tên node JConsole và có thể trống tùy assembler hoặc implementation.

## 10. Chẩn đoán mismatch giữa các tên

| Hiện tượng | Nguyên nhân thường gặp | Cách xác nhận |
|---|---|---|
| Có Spring bean nhưng không có JMX MBean | Chưa bật export hoặc bean chưa được chọn | Kiểm tra exporter, annotation, context |
| JConsole hiển thị tên khác \`checkoutMonitor\` | UI dùng ObjectName thay vì bean name | Xem \`queryNames\` và metadata |
| \`getAttribute\` trả \`InstanceNotFoundException\` | Sai ObjectName hoặc server | Kiểm tra \`isRegistered\` |
| MBean đổi tên sau bật AOP | Naming strategy dựa trên class/identity proxy | So ObjectNames và proxy type |
| Hai beans khác tên nhưng trùng JMX | Cùng ObjectName trong exporter | Kiểm tra mappings và registration |
| UI description không thay đổi | Metadata assembler chưa dùng annotation | Đọc \`MBeanInfo\` trực tiếp |
| Tên hiển thị biến mất sau restart | Dùng identity-generated name | Chuyển sang naming ổn định |
| Remote client thấy MBean khác local | Kết nối tới server/endpoint khác | So ObjectNames và server identity |

Một cách chẩn đoán hiệu quả:

\`\`\`text
1. Spring bean có tồn tại?
2. Exporter nào quản lý bean?
3. Naming strategy nào được dùng?
4. ObjectName thực tế là gì?
5. MBeanServer nào chứa ObjectName?
6. MBeanInfo mô tả gì?
7. JMX client đang kết nối đâu và dựng UI ra sao?
\`\`\`

## 11. Collision: Bean name khác vẫn có thể trùng ObjectName

Hai beans:

\`\`\`text
Bean A: inventoryCheckoutMonitor
Bean B: billingCheckoutMonitor
\`\`\`

nhưng cùng được export dưới:

\`\`\`text
com.example:type=Monitor,name=Primary
\`\`\`

Khi vào cùng MBeanServer, chúng xung đột dù tên bean khác nhau. \`RegistrationPolicy\` của Spring exporter có các hành vi như:

- \`FAIL_ON_EXISTING\`: báo lỗi.
- \`IGNORE_EXISTING\`: bỏ qua registration mới.
- \`REPLACE_EXISTING\`: thay registration đã có.

Chính sách chỉ xử lý collision, không thay thế naming convention tốt. Dùng \`IGNORE_EXISTING\` có thể khiến MBean mới không hiện mà không phát hiện ngay; dùng \`REPLACE_EXISTING\` có thể ảnh hưởng object do context khác quản lý.

Để có hai MBeans độc lập, sử dụng ObjectNames độc lập:

\`\`\`text
com.example:type=Monitor,module=inventory,name=Primary
com.example:type=Monitor,module=billing,name=Primary
\`\`\`

Khi naming từ input có thể chứa dấu phẩy, dấu hai chấm hoặc wildcard, hãy validate và quote đúng cú pháp JMX. Với hệ thống nhiều tenant, không đưa dữ liệu riêng tư hay secret vào ObjectName.

## 12. Multiple ApplicationContext và cùng một MBeanServer

Một JVM có thể chứa root và child contexts hoặc nhiều module contexts độc lập:

\`\`\`text
RootContext
  - sharedMonitor
  - rootExporter

ChildContext
  - checkoutMonitor
  - childExporter
\`\`\`

Bean names có thể hợp lệ trong từng context, nhưng MBeanServer dùng chung vẫn yêu cầu ObjectName duy nhất.

Các nguyên tắc:

1. Mỗi context/exporter có ownership rõ ràng.
2. Không tự động export cùng shared bean ở hai context.
3. Tên JMX chứa thông tin phân biệt module khi cần.
4. Đóng context phải unregister đúng MBeans thuộc nó.
5. Một client local kết nối platform server không tự tìm MBeans ở server custom.
6. Không sử dụng identity/proxy class làm hợp đồng tên dài hạn nếu client cần tên ổn định.

## 13. AOP proxy và thay đổi tên

Spring AOP có thể thay đổi class của object được exporter thấy. Với JDK dynamic proxy, class runtime không giống target class; với class-based proxy, lớp proxy là subclass.

Nếu naming strategy dùng class name hoặc identity, ObjectName có thể thay đổi sau khi bật \`@Transactional\`, \`@Cacheable\` hoặc advice khác. Nhưng nếu dùng ObjectName khai báo rõ:

\`\`\`java
@ManagedResource(
    objectName = "com.example.shop:type=Queue,name=Checkout")
\`\`\`

tên được thiết kế ổn định, miễn là exporter chọn đúng metadata và registration thành công.

Không tự đoán tên bằng cách đọc \`bean.getClass().getName()\`; hãy query ObjectNames thực tế và kiểm tra \`MBeanInfo\`.

## 14. Tên hiển thị có nên dịch ra nhiều ngôn ngữ?

JMX ObjectName nên ổn định, có quy tắc dễ tra cứu và không đổi theo locale. Nếu UI cần tiếng Việt hoặc tiếng Anh, nên dịch **nhãn hiển thị** ở tầng dashboard/application UI, thay vì biến ObjectName thành chuỗi ngôn ngữ tự nhiên có thể thay đổi.

Ví dụ:

\`\`\`text
ObjectName (stable):
  com.example.shop:type=Queue,name=Checkout

Vietnamese UI label:
  Hàng đợi thanh toán

English UI label:
  Checkout queue
\`\`\`

Cách này cho phép automation và monitoring tiếp tục hoạt động khi thay đổi ngôn ngữ giao diện. \`description\` trong metadata có thể giúp người vận hành, nhưng không phải hệ thống đa ngôn ngữ hoàn chỉnh.

## 15. Bảo vệ hợp đồng tên bằng kiểm thử

Một integration test nên xác minh ObjectName, metadata và Spring bean mapping.

\`\`\`java
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation
    .AnnotationConfigApplicationContext;

import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.lang.management.ManagementFactory;

import static org.junit.jupiter.api.Assertions.*;

class JmxNamingContractTest {

    @Test
    void exportedNameRemainsStable() throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(
                    AppConfig.class)) {

            assertNotNull(context.getBean("checkoutMonitor"));

            MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

            ObjectName name = new ObjectName(
                "com.example.shop:type=Queue,name=Checkout");

            assertTrue(server.isRegistered(name));

            assertEquals(
                0,
                server.getAttribute(name, "PendingCount"));

            String description =
                server.getMBeanInfo(name).getDescription();

            assertNotNull(description);
        }
    }
}
\`\`\`

Ví dụ giả định exporter dùng platform MBeanServer và test không chạy song song với một test khác đăng ký trùng ObjectName. Nếu có server riêng, dùng server chính xác mà exporter nhận. Không chỉ assert \`description\` bằng một chuỗi cứng nếu business contract không yêu cầu nội dung description cố định.

Các test có giá trị khác:

- Hai Spring bean khác nhau phải xuất thành hai ObjectNames nếu chúng là hai resources.
- Đóng một context không unregister MBean của context khác.
- Bật AOP không làm thay đổi ObjectName dự kiến.
- Query theo domain/type trả đúng nhóm MBeans.
- Một JMX client chỉ dựa vào ObjectName vẫn truy cập được sau nâng cấp.

## 16. Thiết kế quy ước tên cho production

Một quy ước nhất quán:

\`\`\`text
<reverse-domain>:type=<resourceType>,module=<module>,name=<resourceName>
\`\`\`

Ví dụ:

\`\`\`text
com.example.platform:type=Cache,module=orders,name=Products
com.example.platform:type=Queue,module=orders,name=Checkout
com.example.platform:type=Worker,module=billing,name=Invoice
\`\`\`

Quy tắc thực tế:

- Sử dụng domain giống namespace Java hoặc tên hệ thống ổn định.
- \`type\` biểu diễn loại resource, \`name\` biểu diễn instance logic.
- \`module\` hoặc \`instance\` chỉ thêm khi cần phân biệt.
- Không dùng timestamp, thread ID hoặc số đếm thay đổi liên tục làm key.
- Không để email, access token hoặc secret vào ObjectName.
- Không phụ thuộc vào thứ tự key properties khi so sánh.
- Viết test chống rename ngẫu nhiên ở mỗi release.
- Giữ UI label tách khỏi technical identity.

Một ObjectName quá nhiều key làm query phức tạp; một tên quá ít key có thể gây collision. Chọn đủ thông tin định danh theo yêu cầu thực tế.

## 17. Bài tập thực hành

### Bài tập A — Phân biệt ba tên

Tạo Spring bean có tên \`inventoryMonitor\`, export thành \`training.shop:type=Inventory,name=Primary\`, khai báo description \`Inventory status monitor\`. In tên bean từ ApplicationContext, ObjectName từ MBeanServer và description từ MBeanInfo. Giải thích sự khác nhau.

### Bài tập B — Collision

Tạo hai beans \`monitorA\`, \`monitorB\` và cố export cùng ObjectName. Ghi nhận lỗi registration. Sửa bằng key \`module\` và kiểm tra hai ObjectNames tồn tại đồng thời.

### Bài tập C — Đổi tên bean không đổi JMX

Đổi Spring bean name từ \`checkoutMonitor\` thành \`checkoutStatusMonitor\` nhưng giữ \`@ManagedResource.objectName\` cố định. Quan sát JMX client vẫn tìm MBean theo tên cũ nếu export cấu hình đúng.

### Bài tập D — Thay đổi description

Đổi description từ tiếng Anh sang tiếng Việt, giữ ObjectName không đổi. Kiểm tra metadata và JConsole; giải thích vì sao automation không nên dựa trên description.

### Bài tập E — Query theo nhóm

Đăng ký ba MBeans với domain \`training.shop\`. Dùng pattern \`training.shop:type=Queue,*\` để tìm tất cả queue. Giải thích vì sao \`,*\` cần thiết khi ObjectName có thêm key properties.

## 18. Câu hỏi tự kiểm tra

1. Bean name có phải ObjectName không?
2. Ai quyết định tên bean trong Spring và ai quyết định ObjectName JMX?
3. Tên hiển thị trong JConsole lấy từ nguồn nào?
4. Một description có thể dùng thay \`ObjectName\` khi gọi \`getAttribute\` không?
5. Hai bean names khác nhau có thể trùng ObjectName không?
6. Tại sao ObjectName nên ổn định qua restart?
7. Khi nào nên chọn \`IdentityNamingStrategy\`?
8. Vì sao AOP proxy có thể làm tên JMX generated thay đổi?
9. Làm sao biết exporter đăng ký vào MBeanServer nào?
10. Vì sao UI label đa ngôn ngữ không nên làm đổi JMX technical identity?

## 19. Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework API — \`ObjectNamingStrategy\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/naming/ObjectNamingStrategy.html
- Spring Framework API — \`@ManagedResource\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedResource.html
- Java SE 21 API — \`ObjectName\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
- Java SE 21 API — \`MBeanInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html

**Ghi nhớ:** bean name dùng cho Spring DI, ObjectName dùng cho JMX registry và automation, còn tên hiển thị phục vụ con người. Thiết kế ba lớp tên rõ ràng giúp tránh collision, giảm lỗi tìm MBean và giữ hợp đồng quản trị ổn định khi ứng dụng thay đổi.
