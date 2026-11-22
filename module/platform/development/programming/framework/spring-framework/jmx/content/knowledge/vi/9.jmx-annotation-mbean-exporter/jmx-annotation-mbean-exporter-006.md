# Kiểm tra bean được scan có đúng phạm vi không trong AnnotationMBeanExporter

## 1. Vấn đề cần giải quyết

Trong Spring Framework JMX, **AnnotationMBeanExporter** giúp tìm các Spring bean có metadata quản trị JMX, chẳng hạn `@ManagedResource`, rồi xuất chúng thành MBean trong `MBeanServer`. Tuy nhiên, một ứng dụng có thể có rất nhiều bean, nhiều package, nhiều `ApplicationContext` và nhiều cách cấu hình exporter. Vì vậy, câu hỏi thực tế không chỉ là “Bean đã được đánh dấu annotation chưa?” mà còn là:

- Bean có được Spring tạo và quản lý trong context mà exporter nhìn thấy hay không?
- Exporter đang phát hiện những bean nào và với quy tắc nào?
- Có vô tình xuất cả bean ngoài phạm vi mong muốn không?
- Có bỏ sót bean cần quản trị do component scanning, điều kiện khởi tạo hoặc nhiều context không?
- Những bean được chọn có thực sự đăng ký thành MBean với `ObjectName` đúng không?

**Cần phân biệt hai quá trình:** *Spring component scanning* tìm component để tạo Spring bean; *JMX autodetection/export* lựa chọn bean đã tồn tại trong Spring container để công bố qua JMX. Cấu hình sai ở một trong hai quá trình có thể khiến danh sách MBean thực tế lệch kỳ vọng.

Bài học này hướng dẫn kiểm tra phạm vi phát hiện và xuất MBean bằng cách đối chiếu bean definitions, annotation, cấu hình exporter và registry trong MBeanServer.

## 2. Luồng phát hiện bean và xuất JMX

Một kiến trúc điển hình:

```text
Classpath
    |
    | @ComponentScan / @SpringBootApplication / @Import
    v
Spring ApplicationContext
    |
    +-- Bean A: @ManagedResource
    +-- Bean B: @ManagedResource
    +-- Bean C: không có @ManagedResource
    +-- Bean D: không được tạo vì @Profile / @Conditional
    |
    | AnnotationMBeanExporter / metadata assembler
    v
Tập bean được chọn để export
    |
    | ObjectNamingStrategy + RegistrationPolicy
    v
MBeanServer
    |
    +-- ObjectName của Bean A
    +-- ObjectName của Bean B
    |
    v
JConsole / VisualVM / MBeanServerConnection
```

Một bean có annotation trong mã nguồn nhưng **không tồn tại trong context** sẽ không tự xuất hiện trong JMX. Ngược lại, một bean được tạo trong context chưa chắc đã được export; exporter còn phải nhận diện bean có metadata phù hợp và đăng ký thành công.

### Hai tập hợp cần đối chiếu

Gọi:

- **S**: tập Spring bean mà context đang quản lý.
- **E**: tập bean được exporter chọn để xuất.
- **R**: tập `ObjectName` thực sự đã đăng ký trong MBeanServer.

Kết quả mong đợi là các bean cần quản trị thuộc **S**, được chọn vào **E**, và có tên tương ứng trong **R**. Không thể chỉ nhìn vào annotation hoặc chỉ nhìn thấy một tên trong JConsole để kết luận toàn bộ quá trình scan đã đúng.

## 3. Hiểu rõ AnnotationMBeanExporter làm gì

Spring Framework cung cấp `AnnotationMBeanExporter` trong gói `org.springframework.jmx.export.annotation`. Lớp này tích hợp xuất bean theo các annotation quản trị:

- `@ManagedResource`: chỉ định một tài nguyên quản trị và metadata chung.
- `@ManagedAttribute`: mô tả getter/setter được công bố thành attribute.
- `@ManagedOperation`: mô tả operation.
- `@ManagedOperationParameter`: mô tả tham số operation.
- `@ManagedNotification`: metadata notification.
- `@ManagedMetric`: metadata metric nếu sử dụng.

Ví dụ:

```java
package com.example.orders.management;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=payments",
    description = "Payment queue monitoring"
)
public class PaymentQueueManagement {

    private volatile int pendingCount;

    @ManagedAttribute
    public int getPendingCount() {
        return pendingCount;
    }

    @ManagedOperation
    public void resetStatistics() {
        pendingCount = 0;
    }
}
```

Nếu bean trên được Spring container tạo, exporter hoạt động đúng và việc đăng ký không bị lỗi, MBean tương ứng có thể xuất hiện dưới:

```text
com.example.orders:type=Queue,name=payments
```

Tuy nhiên, việc có `@ManagedResource` trên class **không thay thế** việc bật Spring JMX export. Annotation chỉ là nguồn metadata; exporter phải tồn tại và được kích hoạt trong application context.

## 4. Component scan và JMX export scan khác nhau ra sao?

### 4.1. Component scan

Cấu hình:

```java
@Configuration
@ComponentScan(basePackages = "com.example.orders")
public class OrdersConfiguration {
}
```

cho phép Spring quét các component phù hợp dưới package `com.example.orders` và các package con. Nếu `PaymentQueueManagement` nằm ở `com.example.orders.management` và được đánh dấu `@Component`, nó có thể được tạo thành Spring bean khi các điều kiện khởi tạo đều thỏa mãn.

Nếu cấu hình chỉ quét:

```java
@ComponentScan(basePackages = "com.example.orders.web")
```

thì package `com.example.orders.management` nằm ngoài phạm vi quét này. Annotation JMX trên lớp không tự làm cho lớp được đăng ký thành bean.

### 4.2. Phát hiện để export MBean

Sau khi Spring đã tạo các bean, exporter có thể phát hiện những bean có metadata JMX được hỗ trợ. Đây là quá trình khác với quét classpath để tạo component.

Ví dụ:

```text
com.example.orders.web.OrderController
com.example.orders.management.PaymentQueueManagement
com.example.orders.service.OrderService
```

Giả sử cả ba đều là Spring bean, nhưng chỉ `PaymentQueueManagement` được đánh dấu `@ManagedResource`, thì exporter dùng annotation thường chỉ nên đưa bean này vào tập MBean được phát hiện tự động.

Nếu exporter còn được cấu hình **explicit beans**, danh sách được xuất có thể bổ sung hoặc bị điều chỉnh theo cấu hình. Do đó phải xem toàn bộ cấu hình, không suy đoán chỉ dựa trên annotation.

### 4.3. ApplicationContext cũng là một ranh giới

Nhiều Spring context có thể cùng chạy trong một JVM:

```text
Parent context
  ├── SharedService
  └── SharedManagement

Child context A
  └── WebManagementA

Child context B
  └── WebManagementB
```

Exporter trong context nào nhìn thấy bean nào phụ thuộc bean factory, quan hệ context và cấu hình cụ thể. Không nên mặc định exporter trong một child context luôn thấy tất cả bean của các context anh em.

Ngoài ra, nhiều context có thể dùng chung **platform MBeanServer**. Khi đó hai exporter ở context khác nhau vẫn có nguy cơ đăng ký trùng một `ObjectName`.

## 5. Kiểm tra bean có tồn tại trong Spring ApplicationContext

Bước đầu tiên là xác minh bean thực sự được tạo trong context mong muốn.

Ví dụ:

```java
import org.springframework.context.ApplicationContext;

public final class BeanPresenceCheck {

    public static void inspect(ApplicationContext context) {
        String[] names = context.getBeanNamesForType(
                PaymentQueueManagement.class
        );

        System.out.println("Matching beans: " + names.length);

        for (String name : names) {
            System.out.println("Bean: " + name);
        }
    }
}
```

Nếu không tìm thấy bean:

1. Kiểm tra package của class so với `@ComponentScan`.
2. Kiểm tra class có `@Component`, `@Service` hoặc được khai báo bằng `@Bean` không.
3. Kiểm tra `@Profile`, `@Conditional` và điều kiện khởi tạo khác.
4. Kiểm tra context đang inspect có phải context thực tế chạy exporter không.
5. Kiểm tra lỗi tạo bean trong log khởi động.

Nếu có nhiều bean cùng loại, xác minh tên bean nào thực sự cần được quản trị và liệu exporter có đăng ký toàn bộ các bean ấy không.

**Lưu ý:** một phương thức như `getBeanNamesForType` chỉ phản ánh đối tượng/type Spring biết trong context. Nó không tự chứng minh rằng mỗi bean đã được đăng ký thành MBean.

## 6. Cấu hình exporter tối thiểu và phạm vi dự kiến

Một cấu hình minh họa:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.annotation.AnnotationMBeanExporter;

@Configuration
public class JmxConfiguration {

    @Bean
    static AnnotationMBeanExporter annotationMBeanExporter() {
        return new AnnotationMBeanExporter();
    }
}
```

Khi annotation exporter được kích hoạt trong context, những bean có metadata JMX phù hợp có thể được phát hiện và export. Nếu ứng dụng đã bật Spring JMX bằng cơ chế khác (ví dụ cấu hình framework hoặc auto-configuration của Spring Boot), cần tránh vô tình tạo nhiều exporter cùng đăng ký một bean.

### Vì sao không chỉ nhìn vào component scan?

Giả sử context quét `com.example` rộng hơn dự kiến. Tất cả component hợp lệ có thể được tạo, nhưng exporter chỉ quan tâm những bean có metadata quản trị. Nếu một thư viện bên thứ ba cũng đăng ký bean có `@ManagedResource` vào cùng context, chúng cũng có thể xuất hiện trong JMX tùy phạm vi autodetection và cấu hình thực tế.

Điều này tạo ra hai câu hỏi riêng:

- **Ứng dụng có scan quá nhiều component không?**
- **Exporter có export quá nhiều management bean không?**

Câu trả lời có thể khác nhau. Việc tinh chỉnh component scanning có thể ảnh hưởng dependency injection và hành vi ứng dụng; để giới hạn JMX, đôi khi phù hợp hơn là điều chỉnh exporter, naming strategy hoặc cách khai báo metadata.

## 7. Kiểm tra ObjectName thực tế trong MBeanServer

Sau khi xác nhận bean tồn tại, cần xác minh nó đã được export.

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class JmxRegistrationCheck {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
                "com.example.orders:type=Queue,name=payments"
        );

        System.out.println(
                "Registered: " + server.isRegistered(name)
        );
    }
}
```

Kết quả `true` nghĩa là một MBean với ObjectName đó tồn tại trong **MBeanServer được kiểm tra**. Kết quả không cho biết chắc chắn Spring exporter nào đăng ký nó hoặc Java bean nào là nguồn gốc nếu nhiều thành phần có thể dùng cùng tên.

Nếu ứng dụng cấu hình một MBeanServer riêng, `ManagementFactory.getPlatformMBeanServer()` có thể không phải nơi exporter đăng ký MBean. Trong trường hợp đó cần inspect đúng MBeanServer được inject vào exporter.

### Truy vấn theo domain

```java
import java.util.Set;
import javax.management.ObjectName;

Set<ObjectName> names = server.queryNames(
        new ObjectName("com.example.orders:*"),
        null
);

for (ObjectName name : names) {
    System.out.println(name.getCanonicalName());
}
```

Dùng kết quả để nhận diện **toàn bộ MBean trong namespace ứng dụng**, bao gồm những bean xuất hiện ngoài kỳ vọng.

### So sánh danh sách mong đợi

Ví dụ tập dự kiến:

```text
com.example.orders:type=Queue,name=payments
com.example.orders:type=Queue,name=shipping
com.example.orders:type=Scheduler,name=background
```

Danh sách thực tế được query từ MBeanServer nên được đối chiếu với danh sách đó. Nếu thiếu một tên, điều tra đường đăng ký. Nếu có tên ngoài ý muốn, xác định nguồn exporter và lý do metadata được phát hiện.

## 8. Kiểm tra qua JConsole hoặc VisualVM

Ngoài API, có thể dùng công cụ JMX để quan sát trực tiếp:

1. Chạy ứng dụng Spring ở môi trường phù hợp.
2. Mở `jconsole` từ JDK và kết nối tới JVM của ứng dụng.
3. Chọn tab **MBeans**.
4. Tìm domain của ứng dụng, ví dụ `com.example.orders`.
5. Mở các node và đọc ObjectName, attributes, operations.
6. So sánh với danh sách bean cần export.
7. Ghi nhận bean thiếu hoặc bean ngoài phạm vi dự kiến.

**Cần phân biệt tên hiển thị với ObjectName:** JConsole có thể sắp xếp key properties thành cây theo cách riêng. Hãy đối chiếu ObjectName đầy đủ thay vì chỉ nhìn tên node cuối.

Đối với VisualVM, chức năng JMX/MBeans có thể cần plugin tùy phiên bản. Với hệ thống remote, cần thiết lập kết nối JMX được bảo vệ; không mở cổng quản trị công khai để tiện kiểm thử.

## 9. Kiểm tra metadata để biết có export đúng bean không

Ngay cả khi `ObjectName` đã xuất hiện, cần xác minh các attributes/operations có đúng với hợp đồng dự kiến.

```java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class JmxContractInspector {

    public static void inspect(
            MBeanServer server,
            ObjectName name
    ) throws Exception {
        MBeanInfo info = server.getMBeanInfo(name);

        System.out.println("MBean: " + name);
        System.out.println("Implementation: " + info.getClassName());

        for (MBeanAttributeInfo attribute : info.getAttributes()) {
            System.out.printf(
                "ATTRIBUTE %s type=%s readable=%s writable=%s%n",
                attribute.getName(),
                attribute.getType(),
                attribute.isReadable(),
                attribute.isWritable()
            );
        }

        for (MBeanOperationInfo operation : info.getOperations()) {
            System.out.printf(
                "OPERATION %s return=%s%n",
                operation.getName(),
                operation.getReturnType()
            );
        }
    }
}
```

Với `PaymentQueueManagement`, kỳ vọng có attribute `PendingCount` và operation `resetStatistics`. Nếu có MBean dưới ObjectName đúng nhưng metadata không khớp, có thể một exporter khác hoặc cấu hình metadata khác đã đăng ký tài nguyên.

Không nên dựa riêng vào `MBeanInfo.getClassName()` để xác định bean implementation khi Spring dùng Model MBean hoặc proxy; kết quả có thể phản ánh lớp mô tả hoặc kiểu được export, tùy assembler.

## 10. Các lý do phổ biến khiến bean không được scan/export

### 10.1. Package nằm ngoài component scan

```java
@ComponentScan("com.example.orders.web")
```

không bao phủ class trong `com.example.orders.management`. Bean không được tạo, nên exporter cũng không thấy bean.

Hướng xử lý: mở rộng component scan đúng phạm vi, cấu hình `@Import` hoặc khai báo `@Bean` cụ thể.

### 10.2. Chỉ gắn @ManagedResource mà không đăng ký Spring bean

```java
@ManagedResource
public class QueueAdmin {
}
```

Class này chưa có `@Component` và chưa được tạo bằng `@Bean`; annotation JMX không tự đưa nó vào ApplicationContext.

Hướng xử lý: bảo đảm class được Spring quản lý trước khi kiểm tra JMX export.

### 10.3. Bean bị loại bởi @Profile hoặc @Conditional

```java
@Profile("operations")
@Component
@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=payments"
)
public class PaymentQueueManagement {
}
```

Nếu profile `operations` không được kích hoạt, bean không tồn tại trong context, vì vậy không xuất ra JMX.

Hướng xử lý: xác minh active profiles và condition evaluation phù hợp với môi trường.

### 10.4. Có nhiều ApplicationContext

Bean tồn tại trong một child context nhưng exporter đặt ở context khác. Phạm vi phát hiện có thể không bao gồm bean đó.

Hướng xử lý: xác định nơi tạo bean, nơi tạo exporter và MBeanServer dùng chung. Tránh tạo exporter trùng nếu có thể quản lý tập bean bằng một chủ sở hữu rõ ràng.

### 10.5. Exporter chưa được bật

Ứng dụng có `@ManagedResource`, nhưng không có `AnnotationMBeanExporter` hoặc cấu hình tích hợp JMX tương ứng.

Hướng xử lý: kiểm tra bean exporter thực tế trong context và cấu hình Spring/Spring Boot theo phiên bản đang chạy.

### 10.6. ObjectName trùng với MBean đã có

Hai bean cùng export dưới:

```text
com.example.orders:type=Queue,name=primary
```

sẽ xung đột nếu dùng chung MBeanServer. Việc đăng ký có thể thất bại hoặc được xử lý theo `RegistrationPolicy`.

Hướng xử lý: quy định ObjectName duy nhất cho từng tài nguyên, kiểm tra registration policy và ownership; tránh dùng replace/ignore chỉ để che khuất lỗi đặt tên.

### 10.7. Proxy hoặc metadata không được nhận diện như kỳ vọng

Bean có thể bị proxy bởi Spring AOP, transaction hoặc security. Tùy cách tạo proxy và metadata assembler, việc truy xuất annotation trên bean thực tế có thể khác kỳ vọng.

Hướng xử lý: xem lớp gốc, lớp proxy, cấu hình exporter và metadata thực tế từ MBeanServer. Nếu cần, tách bean quản trị thành adapter đơn giản hoặc cấu hình explicit export.

### 10.8. Exporter được cấu hình để chọn bean theo cách khác

Một ứng dụng có thể có `MBeanExporter` thông thường, danh sách bean tường minh, assembler hoặc naming strategy riêng. Đừng chỉ tìm `AnnotationMBeanExporter` rồi kết luận toàn bộ chính sách export.

Hướng xử lý: xác định tất cả exporter có hiệu lực trong context và các MBean mà từng exporter chịu trách nhiệm đăng ký.

## 11. Tránh export ngoài phạm vi mong muốn

Xuất một bean quản trị ngoài dự kiến có thể làm lộ thông tin vận hành hoặc thao tác thay đổi trạng thái. Những giải pháp thực tế:

### 11.1. Thiết kế package quản trị rõ ràng

Ví dụ:

```text
com.example.orders
  ├── application
  ├── domain
  ├── infrastructure
  └── management
      ├── PaymentQueueManagement
      └── ShippingQueueManagement
```

Package riêng giúp xác định chủ sở hữu và kiểm soát các bean có annotation JMX. Tuy nhiên, **package không tự là bộ lọc của mọi exporter**; phải đối chiếu cấu hình thực tế.

### 11.2. Dùng adapter quản trị

Nếu service nghiệp vụ có nhiều method nhạy cảm, tạo bean quản trị nhỏ:

```java
@Component
@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=payments"
)
public class PaymentQueueMonitor {

    private final PaymentQueueService service;

    public PaymentQueueMonitor(PaymentQueueService service) {
        this.service = service;
    }

    @ManagedAttribute
    public long getPendingCount() {
        return service.pendingCount();
    }
}
```

`PaymentQueueService` là interface/service minh họa. Adapter giúp giới hạn tập method JMX mà không phải công bố toàn bộ API nghiệp vụ.

### 11.3. Đặt tên theo namespace và resource

```text
com.example.orders:type=Queue,application=checkout,name=payments
com.example.orders:type=Queue,application=checkout,name=shipping
```

Một chiến lược ObjectName nhất quán vừa ngăn xung đột, vừa giúp query và kiểm tra ngoài phạm vi.

### 11.4. Tách quyền đọc và thao tác

Với operation có thể thay đổi trạng thái, cần cấu hình kiểm soát truy cập JMX remote và quyền ở tầng runtime phù hợp. Annotation không phải cơ chế phân quyền. Hãy hạn chế export operation thay đổi dữ liệu nếu không cần thiết.

### 11.5. Giữ bản danh sách MBean được phép

Với hệ thống lớn, có thể lưu danh sách ObjectName kỳ vọng hoặc pattern theo môi trường. Khi chạy integration test, query MBeanServer và so sánh. Đây là cách phát hiện sớm bean mới bị export do cấu hình quét quá rộng.

## 12. Minh họa kiểm tra tập MBean được phép

Giả sử ứng dụng dự kiến chỉ có hai MBean trong domain `com.example.orders`.

```java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class ExpectedJmxNamesCheck {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        Set<ObjectName> expected = Set.of(
                new ObjectName(
                    "com.example.orders:type=Queue,name=payments"
                ),
                new ObjectName(
                    "com.example.orders:type=Queue,name=shipping"
                )
        );

        Set<ObjectName> actual = server.queryNames(
                new ObjectName("com.example.orders:*"),
                null
        );

        Set<ObjectName> missing =
                new java.util.HashSet<>(expected);
        missing.removeAll(actual);

        Set<ObjectName> unexpected =
                new java.util.HashSet<>(actual);
        unexpected.removeAll(expected);

        System.out.println("Missing: " + missing);
        System.out.println("Unexpected: " + unexpected);
    }
}
```

Nếu kết quả `missing` hoặc `unexpected` khác rỗng, cần kiểm tra cấu hình export và naming. Đoạn kiểm tra này phải chạy trong JVM hoặc với MBeanServerConnection tương ứng với **server thực**; chạy một tiến trình Java độc lập có platform MBeanServer riêng sẽ không tự thấy MBean của ứng dụng khác.

### Khi nhiều nguồn cùng dùng domain

Một domain có thể chứa MBean do nhiều subsystem chủ động đăng ký. Khi đó, danh sách expected nên xác định scope rõ hơn (chẳng hạn `application=checkout`) để tránh đánh dấu sai các MBean hợp lệ của subsystem khác.

## 13. Kiểm tra context và exporter bằng Spring code

Có thể xem các bean exporter có mặt trong context:

```java
import java.util.Map;
import org.springframework.context.ApplicationContext;
import org.springframework.jmx.export.MBeanExporter;

public final class ExporterBeanInspector {

    public static void inspect(ApplicationContext context) {
        Map<String, MBeanExporter> exporters =
                context.getBeansOfType(MBeanExporter.class);

        exporters.forEach((name, exporter) ->
                System.out.println(
                    "Exporter bean: " + name
                    + ", type=" + exporter.getClass().getName()
                )
        );
    }
}
```

Do `AnnotationMBeanExporter` kế thừa `MBeanExporter`, phép tìm trên có thể phát hiện các exporter tương ứng. Nếu kết quả có nhiều exporter, cần tìm hiểu mỗi exporter được tạo từ configuration nào và chúng có cùng xử lý một bean hay không.

Đừng kết luận chắc chắn một bean được exporter nào đăng ký chỉ dựa trên class của exporter; cần đối chiếu cấu hình và registry.

### Kiểm tra bean có annotation quản trị

Có thể dùng `ApplicationContext` và các tiện ích Spring để tìm metadata, nhưng proxy, factory bean và composed annotation khiến việc tự duyệt trực tiếp `bean.getClass().isAnnotationPresent(...)` có thể bỏ sót metadata. Với nhiệm vụ xác định chính xác tập export, ưu tiên quan sát kết quả của exporter hoặc kiểm tra `MBeanInfo` thực tế.

## 14. Tình huống thực hành: bean thiếu trong JConsole

Giả sử mã nguồn có:

```text
com.acme.shop.web.ShopController
com.acme.shop.management.InventoryAdmin
com.acme.shop.management.PaymentQueueAdmin
```

Hai class management đều có `@ManagedResource`, nhưng JConsole chỉ thấy `InventoryAdmin`.

Cách điều tra:

1. Xác nhận `PaymentQueueAdmin` có bean instance trong context hay không.
2. Nếu không có, xem component scan, `@Profile` và `@Conditional`.
3. Nếu có, xác định exporter/assembler có hỗ trợ metadata của class đó.
4. Kiểm tra `ObjectName` trên annotation và naming strategy.
5. Kiểm tra log startup để phát hiện `InstanceAlreadyExistsException` hoặc `NotCompliantMBeanException`.
6. Kiểm tra đúng MBeanServer mà exporter đăng ký.
7. Query `MBeanServer` theo domain để loại trừ việc công cụ hiển thị MBean ở nhánh khác.
8. Xem `MBeanInfo` để xác nhận attributes/operations đúng bean.

Ví dụ nếu cả hai bean dùng:

```text
com.acme.shop:type=Management,name=default
```

thì nguyên nhân có thể là xung đột ObjectName. Sửa bằng cách đặt:

```text
com.acme.shop:type=Management,name=inventory
com.acme.shop:type=Management,name=payments
```

thay vì dùng `REPLACE_EXISTING` làm giải pháp mặc định.

## 15. Tình huống thực hành: bean không mong muốn được export

Giả sử JConsole xuất hiện MBean:

```text
com.acme.shop:type=Maintenance,name=internal
```

mặc dù danh sách vận hành chỉ dự kiến hai queue monitor.

Phân tích:

1. Xác định bean thật qua configuration hoặc metadata.
2. Tìm `@ManagedResource` hoặc explicit export mapping tương ứng.
3. Kiểm tra có thư viện/module nào đưa bean đó vào ApplicationContext không.
4. Xác định exporter có phát hiện toàn bộ annotated beans trong context hay đang dùng danh sách được cấu hình tường minh.
5. Nếu bean không cần công bố, loại khỏi tập export theo cấu hình phù hợp hoặc tách metadata quản trị ra khỏi class.
6. Sau thay đổi, query MBeanServer để xác nhận tên đã biến mất.
7. Kiểm tra lifecycle để bảo đảm MBean không còn đăng ký sót từ context cũ.

**Chú ý:** chỉ đổi package hoặc vô hiệu hóa component scanning để ẩn JMX có thể làm hỏng chức năng nghiệp vụ phụ thuộc bean đó. Cần xác định chính xác tầng cấu hình gây export.

## 16. Spring Boot: điểm khác biệt cần chú ý

Trong ứng dụng Spring Boot, trạng thái bật JMX có thể phụ thuộc cấu hình Boot và starter/dependency. Ở nhiều cấu hình Boot, việc xuất Spring bean qua JMX được điều khiển bởi thuộc tính:

```properties
spring.jmx.enabled=true
```

Tuy nhiên, cơ chế auto-configuration, domain, naming và các endpoint quản trị có thể thay đổi theo phiên bản Boot, dependency và cấu hình ứng dụng. Không nên chỉ dựa vào một property để kết luận chính xác bean nào được export.

Cách kiểm tra thực tế:

- Xác định property và profile đang có hiệu lực.
- Kiểm tra exporter bean nào được auto-configured.
- Xem có exporter tường minh khác trùng chức năng hay không.
- Kiểm tra tên MBean thực tế qua MBeanServer.
- Nếu dùng Spring Boot Actuator, phân biệt endpoint JMX của Actuator với các MBean ứng dụng được export theo annotation.

Trong đa số tình huống, **đọc registry thực tế là bằng chứng xác nhận cuối cùng**, còn configuration cho biết vì sao registry có kết quả đó.

## 17. Tránh kiểm tra nhầm JVM hoặc MBeanServer

Một sai lầm phổ biến là chạy đoạn code:

```java
ManagementFactory.getPlatformMBeanServer()
```

trong chương trình kiểm tra riêng, rồi nhận `false` và kết luận bean không được export. Mỗi tiến trình Java thường có platform MBeanServer riêng. Đoạn code ở tiến trình kiểm tra độc lập sẽ quan sát server của chính nó.

Khi dùng JConsole:

1. Xác định process ID chính xác.
2. Chọn đúng JVM của ứng dụng.
3. Xác nhận tên ứng dụng hoặc main class.
4. Kiểm tra domain từ MBeanServer đó.

Khi dùng remote client, lấy `MBeanServerConnection` từ JMX connector của JVM đích:

```java
import javax.management.MBeanServerConnection;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL url = new JMXServiceURL(
        "service:jmx:rmi:///jndi/rmi://127.0.0.1:9999/jmxrmi"
);

try (JMXConnector connector =
             JMXConnectorFactory.connect(url)) {
    MBeanServerConnection connection =
            connector.getMBeanServerConnection();

    // Query MBeans from the target JVM.
}
```

URL chỉ là ví dụ cho endpoint đã được cấu hình riêng; không mặc định JVM nào cũng có JMX RMI ở port 9999. Môi trường production cần cơ chế authentication/TLS và giới hạn network access thích hợp.

## 18. Những lỗi thường gặp và hướng xử lý

| Hiện tượng | Nguyên nhân có thể | Bước kiểm tra |
| --- | --- | --- |
| Class có `@ManagedResource` nhưng không xuất hiện | Class không được tạo thành Spring bean | Component scan, `@Bean`, profile, condition |
| Bean tồn tại nhưng không được export | Exporter chưa bật hoặc metadata không phù hợp | Danh sách exporter và assembler |
| Một số bean xuất hiện trong context khác | Khác ApplicationContext / bean factory | Phân tích quan hệ context |
| Hai bean tranh cùng tên | ObjectName trùng | Domain, key properties, registration policy |
| Bean có MBean nhưng attribute thiếu | Method không được annotation hoặc assembler không chọn | `MBeanInfo` và metadata |
| MBean xuất hiện với tên lạ | Naming strategy hoặc ObjectName bị biến đổi | Full ObjectName và exporter configuration |
| MBean dư xuất hiện | Scan/auto-detection quá rộng hoặc explicit registration | Trace bean definition và exporter mapping |
| JConsole không thấy domain | Kết nối sai JVM hoặc server không đăng ký | PID, JMX URL, MBeanServer |
| Registration lỗi lúc startup | Sai tên, trùng tên hoặc MBean không compliant | Log exception và root cause |
| Bean có proxy khiến metadata lệch | AOP/proxy ảnh hưởng cách phát hiện | Metadata trên class gốc và cấu hình exporter |

## 19. Checklist triển khai

Khi cần xác nhận `AnnotationMBeanExporter` scan đúng phạm vi, có thể dùng checklist sau:

1. **Xác định mục tiêu:** liệt kê các Spring bean và ObjectName dự kiến xuất.
2. **Xác nhận Spring context:** đúng `ApplicationContext`, đúng active profiles và component scan.
3. **Xác nhận bean presence:** các bean mong đợi thực sự tồn tại trong context.
4. **Xác nhận exporter:** có exporter phù hợp và không có cấu hình export trùng ngoài ý muốn.
5. **Xác nhận metadata:** annotation `@ManagedResource`, attributes, operations đúng trên bean đã chọn.
6. **Xác nhận naming:** mọi MBean có ObjectName hợp lệ và duy nhất trong MBeanServer.
7. **Xác nhận registry:** so sánh tập ObjectName thực tế với tập dự kiến.
8. **Xác nhận hợp đồng:** các attributes/operations được công bố đúng và không để lộ method ngoài dự kiến.
9. **Xác nhận lifecycle:** MBean được hủy đăng ký khi exporter/context ngừng.
10. **Xác nhận bảo mật:** những chức năng được export phù hợp quyền truy cập JMX và nhu cầu vận hành.

Đây là cách kiểm tra **phạm vi thực sự**, không chỉ cấu hình được khai báo.

## 20. Câu hỏi tự kiểm tra

**1. Vì sao có `@ManagedResource` nhưng JConsole không thấy bean?**

Có thể class không được Spring tạo thành bean, exporter chưa bật, bean nằm ở context khác, ObjectName không hợp lệ, đăng ký thất bại hoặc JConsole kết nối sai JVM.

**2. `@ComponentScan` có phải chính là scan của AnnotationMBeanExporter không?**

Không. Component scan chọn class để tạo Spring bean; exporter lựa chọn bean và metadata để đăng ký MBean.

**3. Vì sao cần kiểm tra cả ApplicationContext và MBeanServer?**

Vì bean có thể tồn tại trong Spring nhưng chưa được export; chỉ registry thực tế mới xác nhận MBean đã đăng ký.

**4. Nhiều context trong cùng JVM có thể trùng ObjectName không?**

Có. Nếu các exporter cùng dùng một MBeanServer, ObjectName phải duy nhất trong server đó.

**5. Có thể dựa vào `MBeanInfo.getClassName()` để biết chính xác Spring bean gốc không?**

Không phải lúc nào cũng được, vì Model MBean/proxy và metadata assembler có thể ảnh hưởng tên lớp hiển thị.

**6. Nếu exporter phát hiện quá nhiều bean thì nên tắt component scan rộng ngay không?**

Không nhất thiết. Cần tìm nguyên nhân ở component registration và JMX export riêng biệt; thay đổi component scan có thể ảnh hưởng chức năng ứng dụng.

**7. `isRegistered(ObjectName)` có đủ chứng minh bean đúng được export không?**

Chỉ chứng minh có một MBean cùng tên trong server đó. Cần kiểm tra metadata và cấu hình để xác định chính xác resource và giao diện quản trị.

## 21. Tổng kết

Để xác minh `AnnotationMBeanExporter` phát hiện đúng phạm vi, hãy đối chiếu **ba lớp độc lập nhưng liên quan**:

```text
Spring bean thực sự có trong ApplicationContext
                  |
                  v
Bean được exporter chọn theo metadata/configuration
                  |
                  v
ObjectName được đăng ký thành công trong MBeanServer
```

Cần kết hợp kiểm tra **component scan**, **ApplicationContext**, **exporter**, **ObjectName** và **MBeanInfo**. Khi có bean thiếu hoặc dư, hãy truy vết từ tập bean được tạo tới tập MBean được đăng ký, kiểm tra ranh giới context, naming và các điều kiện khởi tạo.

Việc scan đúng không chỉ giúp tránh thiếu dữ liệu giám sát, mà còn ngăn công bố ngoài ý muốn các operation quản trị. Một cấu hình Spring JMX tốt xác định rõ **bean nào được export, qua ObjectName nào, với những attributes/operations nào và dưới quyền quản lý lifecycle của exporter nào**.

### Tài liệu tham khảo

- Spring Framework Reference — JMX Exporting: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — `AnnotationMBeanExporter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/AnnotationMBeanExporter.html
- Spring Framework API — `MBeanExporter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Java SE API — `MBeanServerConnection`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
