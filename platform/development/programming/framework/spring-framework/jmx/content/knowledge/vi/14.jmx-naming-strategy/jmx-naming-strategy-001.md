# Spring Framework JMX: ObjectNamingStrategy và vai trò trong MBeanExporter

## 1. Mục tiêu

Trong Spring Framework JMX, **\`MBeanExporter\`** đăng ký các Spring bean làm MBean để công cụ quản trị có thể truy cập qua \`MBeanServer\`. Mọi MBean cần một tên JMX kiểu \`javax.management.ObjectName\`, ví dụ:

\`\`\`text
com.example.app:type=WorkerPool,name=primary
\`\`\`

Khi một ứng dụng export nhiều bean, cần trả lời câu hỏi: **ObjectName của từng bean được xác định thế nào?** Có thể gắn tên trực tiếp trong cấu hình exporter, trong annotation \`@ManagedResource\`, hoặc dùng một **\`ObjectNamingStrategy\`** để xây dựng tên nhất quán theo quy tắc tập trung.

Bài học giải thích interface \`org.springframework.jmx.export.naming.ObjectNamingStrategy\`, vai trò của nó trong \`MBeanExporter\`, cách triển khai một naming strategy, những trường hợp strategy có hoặc không được áp dụng, cũng như quản lý collision, nhiều instance và sự ổn định của tên quản trị.

Mô hình tổng quan:

\`\`\`text
ApplicationContext
  |
  +-- Bean "primaryPool"  -----------+
  +-- Bean "secondaryPool" ----------+--> MBeanExporter
  +-- Bean "cacheManager" -----------+          |
                                                v
                                     ObjectNamingStrategy
                                     (managedBean, beanKey)
                                                |
                                          ObjectName
                                                |
                                                v
                                           MBeanServer
                                                |
                                           JMX clients
\`\`\`

**Ý quan trọng:** Naming strategy xác định **danh tính JMX** của bean, không quyết định trực tiếp thuộc tính hay operation nào được expose. Phần metadata quản trị thường thuộc trách nhiệm MBean contract hoặc \`MBeanInfoAssembler\`.

## 2. Ba thành phần cần phân biệt

| Thành phần | Câu hỏi giải quyết | Ví dụ |
|---|---|---|
| \`MBeanExporter\` | Bean nào được đưa vào JMX và đăng ký ở server nào? | Export bean \`primaryPool\` |
| \`ObjectNamingStrategy\` | Bean sẽ có ObjectName nào? | \`com.example.app:type=WorkerPool,name=primary\` |
| \`MBeanInfoAssembler\` | Client thấy những attribute/operation nào? | \`ActiveCount\`, \`resize(int)\` |

Ngoài ra:

- \`MBeanServer\` là registry thực tế lưu các MBean đã đăng ký.
- \`ObjectName\` là định danh trong registry, gồm domain và key properties.
- \`MBeanExporter\` có thể dùng tên tường minh hoặc naming strategy tùy cách bean được khai báo/cấu hình.
- Các bean đã là Standard MBean/DynamicMBean có hợp đồng JMX sẵn; POJO thường cần assembler/model MBean adapter để công bố giao diện quản trị.

Không nên dùng tên của bean để suy luận rằng tất cả public methods đã được export. Chọn ObjectName và chọn bề mặt JMX là hai vấn đề khác nhau.

## 3. ObjectName là gì?

ObjectName có dạng:

\`\`\`text
<domain>:<key>=<value>,<key>=<value>,...
\`\`\`

Ví dụ:

\`\`\`text
com.example.app:type=WorkerPool,name=primary,service=orders
com.example.app:type=WorkerPool,name=secondary,service=orders
com.example.app:type=CacheManager,name=products,service=catalog
\`\`\`

Domain thường dùng namespace do ứng dụng kiểm soát. Key properties mô tả loại, vai trò và danh tính của tài nguyên.

Hai điểm kỹ thuật:

1. Trong cùng một \`MBeanServer\`, một ObjectName chỉ có thể định danh một MBean đang đăng ký. Đăng ký trùng thường gây \`InstanceAlreadyExistsException\`.
2. ObjectName là cấu trúc, không phải chuỗi thường. Thứ tự key properties không tạo nên danh tính mới: \`type=Cache,name=products\` và \`name=products,type=Cache\` tương đương.

Do đó một naming strategy tốt phải tạo tên **hợp lệ**, **không va chạm trong server**, và **có ý nghĩa ổn định đối với client quản trị**.

## 4. Interface ObjectNamingStrategy

Spring cung cấp interface:

\`\`\`java
package org.springframework.jmx.export.naming;

public interface ObjectNamingStrategy {
    ObjectName getObjectName(
        Object managedBean,
        String beanKey
    ) throws MalformedObjectNameException;
}
\`\`\`

Phương thức nhận:

- \`managedBean\`: đối tượng Spring muốn export.
- \`beanKey\`: khóa/tên được exporter dùng để nhận diện bean trong cấu hình export.
- Kết quả: \`javax.management.ObjectName\`.

\`beanKey\` thường có quan hệ với tên bean hoặc khóa mapping trong exporter, nhưng không nên mặc định nó luôn là tên nghiệp vụ ổn định. Khi có proxy, bean key được tạo tự động hoặc cấu hình map khác nhau, cần hiểu nguồn cấp \`beanKey\` trong cách export thực tế.

Ví dụ một strategy tưởng tượng:

\`\`\`java
ObjectName getObjectName(Object bean, String beanKey) {
    // Chuyển beanKey thành ObjectName theo naming contract.
}
\`\`\`

Strategy **không tự đăng ký** MBean. Nó trả tên để \`MBeanExporter\` dùng trong quá trình export.

## 5. Chiến lược mặc định và tên tường minh

Spring có các cơ chế đặt tên, trong đó \`KeyNamingStrategy\` dùng key của bean và mapping nếu được cấu hình. Tên ObjectName cũng có thể được chỉ định trực tiếp khi đăng ký bean:

\`\`\`java
MBeanExporter exporter = new MBeanExporter();
exporter.setBeans(Map.of(
    "com.example.app:type=WorkerPool,name=primary",
    primaryPool
));
\`\`\`

Ở cấu hình trên, khóa map đã là ObjectName dạng chuỗi. Nhiều trường hợp exporter có thể diễn giải nó trực tiếp theo naming strategy hoặc convention tương ứng.

Một số ứng dụng dùng annotation:

\`\`\`java
@ManagedResource(
    objectName = "com.example.app:type=WorkerPool,name=primary"
)
public class WorkerPoolControl {
    // ...
}
\`\`\`

Khi \`MetadataNamingStrategy\`/annotation infrastructure được dùng, tên metadata có thể tham gia quyết định ObjectName.

**Không nên giả định một custom strategy luôn ghi đè mọi dạng tên tường minh hoặc tên annotation.** Thứ tự và cơ chế lựa chọn tên phụ thuộc exporter, chiến lược được cấu hình và loại bean. Khi thiết kế, chọn một nguồn đặt tên chủ đạo, rồi xác minh ObjectName đã đăng ký bằng \`MBeanServer\`.

## 6. Ví dụ triển khai custom ObjectNamingStrategy

Một ứng dụng quản trị có các bean tên:

\`\`\`text
ordersPrimaryPool
ordersBackgroundPool
catalogProductCache
\`\`\`

Ta muốn một convention chung:

\`\`\`text
com.example.platform:type=ManagedComponent,name=<beanKey>
\`\`\`

Ví dụ:

\`\`\`java
package com.example.jmx;

import java.util.Hashtable;
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;

import org.springframework.jmx.export.naming.ObjectNamingStrategy;

public final class ApplicationObjectNamingStrategy
        implements ObjectNamingStrategy {

    @Override
    public ObjectName getObjectName(
            Object managedBean,
            String beanKey
    ) throws MalformedObjectNameException {

        if (beanKey == null || beanKey.isBlank()) {
            throw new MalformedObjectNameException(
                "beanKey must be non-blank"
            );
        }

        Hashtable<String, String> props = new Hashtable<>();
        props.put("type", "ManagedComponent");
        props.put("name", validateToken(beanKey));

        return new ObjectName(
            "com.example.platform",
            props
        );
    }

    private static String validateToken(String key)
            throws MalformedObjectNameException {

        if (!key.matches("[A-Za-z0-9][A-Za-z0-9._-]*")) {
            throw new MalformedObjectNameException(
                "Unsupported bean key in JMX name"
            );
        }
        return key;
    }
}
\`\`\`

Ưu điểm của cách dùng \`Hashtable\` và constructor \`ObjectName(domain, properties)\` là tránh việc tự ghép các dấu \`:\`, \`,\`, \`=\` tùy tiện. Validation vẫn cần thiết vì giá trị động có thể chứa ký tự đặc biệt hoặc không tuân thủ naming contract.

Điểm lưu ý: \`getObjectName\` có thể được gọi trong giai đoạn Spring khởi tạo exporter. Nếu key không hợp lệ, exception phải cho phép người vận hành biết sai ở đâu mà không tiết lộ dữ liệu nhạy cảm.

### Vì sao không dùng replaceAll tùy tiện?

Ví dụ:

\`\`\`java
String safe = beanKey.replaceAll("[^A-Za-z0-9._-]", "_");
\`\`\`

\`orders/pool\` và \`orders:pool\` đều có thể thành \`orders_pool\`, gây collision. Nếu muốn thay ký tự, phải có chiến lược chứng minh ánh xạ là một-một trong tập đầu vào thực tế hoặc cấp ID ổn định riêng.

Với tên có ký tự đặc biệt cần giữ nguyên, có thể dùng \`ObjectName.quote\` theo quy tắc JMX; nhưng hãy thống nhất cách quote giữa exporter và client, vì biểu diễn quoted/unquoted có ý nghĩa khác nhau khi so khớp tên.

## 7. Cấu hình naming strategy vào MBeanExporter

Cấu hình Java Spring:

\`\`\`java
package com.example.jmx;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxExportConfig {

    @Bean
    public ApplicationObjectNamingStrategy objectNamingStrategy() {
        return new ApplicationObjectNamingStrategy();
    }

    @Bean
    public MBeanExporter mBeanExporter(
            ApplicationObjectNamingStrategy namingStrategy,
            WorkerPoolControl primaryPool,
            WorkerPoolControl backgroundPool) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setNamingStrategy(namingStrategy);
        exporter.setBeans(Map.of(
            "primaryPool", primaryPool,
            "backgroundPool", backgroundPool
        ));

        return exporter;
    }
}
\`\`\`

Đây là cách cấu hình trực tiếp một naming strategy cho exporter. Với map keys \`primaryPool\` và \`backgroundPool\`, strategy có thể sinh:

\`\`\`text
com.example.platform:type=ManagedComponent,name=primaryPool
com.example.platform:type=ManagedComponent,name=backgroundPool
\`\`\`

Trong ứng dụng thật, bean \`WorkerPoolControl\` phải được định nghĩa như các Spring beans, và cần cung cấp assembler nếu chúng là POJO chưa tuân thủ Standard/Dynamic MBean convention.

Ví dụ bean có annotation:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(description = "Worker pool controls")
public class WorkerPoolControl {
    private int size = 8;

    @ManagedAttribute
    public int getSize() {
        return size;
    }
}
\`\`\`

Nếu exporter sử dụng \`MetadataMBeanInfoAssembler\`, nó sẽ lấy các attributes/operations từ annotation. Naming strategy ở trên vẫn là thành phần riêng chịu trách nhiệm ObjectName.

### Cấu hình exporter và assembler đầy đủ

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;

@Bean
AnnotationJmxAttributeSource jmxAttributeSource() {
    return new AnnotationJmxAttributeSource();
}

@Bean
MetadataMBeanInfoAssembler jmxAssembler(
        AnnotationJmxAttributeSource source) {
    MetadataMBeanInfoAssembler assembler =
        new MetadataMBeanInfoAssembler();
    assembler.setAttributeSource(source);
    return assembler;
}

@Bean
MBeanExporter exporter(
        ApplicationObjectNamingStrategy namingStrategy,
        MetadataMBeanInfoAssembler assembler,
        WorkerPoolControl primaryPool) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setNamingStrategy(namingStrategy);
    exporter.setAssembler(assembler);
    exporter.setBeans(Map.of("primaryPool", primaryPool));
    return exporter;
}
\`\`\`

Đây là một cấu hình thay thế, không phải bổ sung exporter thứ hai đồng thời với cấu hình ví dụ trước. Khi có \`@EnableMBeanExport\` hoặc Spring Boot auto-configuration, cần tránh nhiều exporter cùng đăng ký một bean.

## 8. Phân biệt naming và assembling

Giả sử cùng một bean:

\`\`\`java
public class WorkerPoolControl {
    public int getActiveCount() { return 3; }
    public void resetCounters() { /* ... */ }
    public void internalShutdown() { /* ... */ }
}
\`\`\`

Dù custom naming strategy trả:

\`\`\`text
com.example.platform:type=WorkerPool,name=primary
\`\`\`

nó không có quyền quyết định \`ActiveCount\`, \`resetCounters\` hay \`internalShutdown\` được công bố.

Để chọn member JMX, dùng hợp đồng MBean hoặc assembler:

- \`MetadataMBeanInfoAssembler\`: dựa trên metadata Spring annotations.
- \`MethodNameBasedMBeanInfoAssembler\`: chọn method theo whitelist.
- \`InterfaceBasedMBeanInfoAssembler\`: chọn theo interface quản trị.
- Standard MBean: interface \`XxxMBean\` xác định bề mặt JMX.

**Tóm tắt:** Naming trả lời *“MBean này ở địa chỉ nào?”*. Assembling trả lời *“đến địa chỉ đó rồi, client làm được gì?”*.

## 9. Các tình huống khi có nhiều instance

### 9.1. Hai bean cùng class trong một JVM

\`\`\`java
@Bean("primaryPool")
WorkerPoolControl primaryPool() {
    return new WorkerPoolControl();
}

@Bean("backupPool")
WorkerPoolControl backupPool() {
    return new WorkerPoolControl();
}
\`\`\`

Nếu strategy chỉ dùng \`managedBean.getClass().getSimpleName()\`, cả hai có thể thành:

\`\`\`text
com.example.app:type=WorkerPoolControl
\`\`\`

và gây collision. Bổ sung bean key hoặc tên logic:

\`\`\`text
com.example.app:type=WorkerPoolControl,name=primary
com.example.app:type=WorkerPoolControl,name=backup
\`\`\`

### 9.2. Nhiều ApplicationContext dùng chung server

Hai context khác nhau có thể đều dùng key \`workerPool\`. Nếu cùng MBeanServer và cùng strategy, ObjectName có thể trùng. Có thể thêm \`context\`:

\`\`\`text
com.example.app:type=WorkerPool,name=workerPool,context=admin
com.example.app:type=WorkerPool,name=workerPool,context=public
\`\`\`

Không nên mặc định \`ApplicationContext.getId()\` luôn ổn định giữa các lần restart. Nếu muốn tên bền vững cho monitoring, context identifier nên được kiểm soát bằng cấu hình.

### 9.3. Nhiều replica ở JVM khác nhau

Mỗi JVM có \`MBeanServer\` riêng. Hai replica có thể export cùng:

\`\`\`text
com.example.app:type=WorkerPool,service=orders,name=primary
\`\`\`

mà không collision trực tiếp. Monitoring thường phân biệt replica bằng endpoint, pod, node hoặc target labels.

Đừng đưa UUID ngẫu nhiên vào ObjectName chỉ vì có nhiều pod; tên logic ổn định giúp script chung dễ tái sử dụng hơn.

### 9.4. Tài nguyên tenant/shard

Nếu cùng JVM có nhiều cache theo tenant:

\`\`\`text
com.example.app:type=Cache,service=orders,tenant=tenant-a
com.example.app:type=Cache,service=orders,tenant=tenant-b
\`\`\`

Naming strategy có thể lấy tenant ID từ một interface định danh của bean. Nhưng phải giới hạn số lượng MBean và bảo đảm unregister khi tenant bị xóa. JMX không thích hợp để export một MBean cho từng request/session số lượng không giới hạn.

## 10. Chiến lược đặt tên dựa vào contract của bean

Khi cần nhiều key properties, có thể xây interface định danh riêng, thay vì suy luận từ class name hoặc chuỗi bean key:

\`\`\`java
package com.example.jmx;

public interface ManagedResourceIdentity {
    String getResourceType();
    String getServiceName();
    String getResourceName();
}
\`\`\`

Một bean:

\`\`\`java
public class WorkerPoolControl implements ManagedResourceIdentity {
    @Override
    public String getResourceType() {
        return "WorkerPool";
    }

    @Override
    public String getServiceName() {
        return "orders";
    }

    @Override
    public String getResourceName() {
        return "async";
    }
}
\`\`\`

Naming strategy:

\`\`\`java
import java.util.Hashtable;
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;
import org.springframework.jmx.export.naming.ObjectNamingStrategy;

public class IdentityNamingStrategy implements ObjectNamingStrategy {

    @Override
    public ObjectName getObjectName(
            Object bean,
            String beanKey) throws MalformedObjectNameException {

        if (!(bean instanceof ManagedResourceIdentity id)) {
            throw new MalformedObjectNameException(
                "Bean does not expose ManagedResourceIdentity: "
                    + beanKey
            );
        }

        Hashtable<String, String> props = new Hashtable<>();
        props.put("type", token(id.getResourceType()));
        props.put("service", token(id.getServiceName()));
        props.put("name", token(id.getResourceName()));

        return new ObjectName("com.example.platform", props);
    }

    private static String token(String value)
            throws MalformedObjectNameException {

        if (value == null ||
            !value.matches("[A-Za-z0-9][A-Za-z0-9._-]*")) {
            throw new MalformedObjectNameException(
                "Invalid JMX naming token"
            );
        }
        return value;
    }
}
\`\`\`

Lợi ích:
- ID của tài nguyên độc lập với tên class Java.
- Refactor tên bean hoặc package không tự đổi ObjectName.
- Mỗi thành phần tự công bố danh tính logic theo contract.
- Cấu trúc ObjectName phản ánh những chiều người vận hành dùng để tìm kiếm.

Nhược điểm: bean management facade phải triển khai interface hoặc có adapter. Với AOP proxy, \`managedBean\` mà strategy nhận có thể là proxy, không phải class implementation trực tiếp; cần bảo đảm contract hiển lộ qua proxy hoặc dùng metadata ổn định khác.

## 11. Dùng metadata annotation với naming strategy

Khi quản trị theo annotation:

\`\`\`java
@ManagedResource(
    objectName = "com.example.app:type=WorkerPool,name=main"
)
public class WorkerPoolControl {
    @ManagedAttribute
    public int getSize() {
        return 8;
    }
}
\`\`\`

Spring có cơ chế đặt tên đọc metadata, ví dụ \`MetadataNamingStrategy\`. Nó khác custom strategy dựa trên bean key. Một hệ thống nên thống nhất:

- Tên **đặt trong \`@ManagedResource\`** nếu mỗi bean có tên tĩnh rõ ràng.
- Tên **do naming strategy sinh** nếu cần quản trị nhiều instances hoặc tên phụ thuộc cấu hình.
- Tên **tường minh trong \`setBeans\`** khi mapping cụ thể là nguồn sự thật.

Không nên dùng cả ba nguồn tên mà không biết thứ tự ưu tiên. Hãy kiểm tra ObjectName được đăng ký thực tế thay vì chỉ đọc một annotation để kết luận.

## 12. Kiểm tra kết quả trong MBeanServer

Sau khi exporter hoạt động, có thể truy vấn các MBean theo pattern:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName pattern = new ObjectName(
    "com.example.platform:type=ManagedComponent,*"
);

for (ObjectName name : server.queryNames(pattern, null)) {
    System.out.println(name.getCanonicalName());
}
\`\`\`

Nếu exporter dùng MBeanServer khác với platform server, thay bằng đúng server được cấu hình. Hai server khác nhau không tự chia sẻ registry.

Xác minh từng ObjectName:

\`\`\`java
ObjectName expected = new ObjectName(
    "com.example.platform:type=ManagedComponent,name=primaryPool"
);

boolean registered = server.isRegistered(expected);
System.out.println("Registered = " + registered);

if (registered) {
    var info = server.getMBeanInfo(expected);
    System.out.println("MBean class = " + info.getClassName());

    for (var attr : info.getAttributes()) {
        System.out.println(
            attr.getName() + " type=" + attr.getType()
        );
    }

    for (var operation : info.getOperations()) {
        System.out.println(operation.getName());
    }
}
\`\`\`

Đây là bước xác minh kết quả runtime:
- Naming strategy tạo tên đúng?
- Exporter thực sự đăng ký tên đó?
- MBean contract/assembler expose member mong muốn?

Nếu chỉ check \`isRegistered\` nhưng không xem metadata, chưa thể xác nhận giao diện quản trị chính xác.

## 13. Hạn chế va chạm và xử lý InstanceAlreadyExistsException

Trong một \`MBeanServer\`, đăng ký hai MBean cùng ObjectName có thể ném \`InstanceAlreadyExistsException\`. Ví dụ strategy chỉ dùng type:

\`\`\`java
return new ObjectName("com.example.app:type=WorkerPool");
\`\`\`

Nếu có hai worker pools, chúng sẽ tranh cùng tên.

Một naming strategy nên có đủ key phân biệt, ví dụ:

\`\`\`text
com.example.app:type=WorkerPool,service=orders,name=mailer
com.example.app:type=WorkerPool,service=orders,name=processor
\`\`\`

Trước khi thay đổi collision policy của exporter, hãy tìm nguyên nhân:
1. Có thật hai instance khác nhau cần export?
2. Có hai exporter cùng export một bean?
3. Có hai \`ApplicationContext\` dùng cùng server?
4. Có MBean cũ chưa được unregister?
5. Strategy có ánh xạ nhiều input về cùng tên không?

Không nên mặc định \`IGNORE_EXISTING\` hoặc \`REPLACE_EXISTING\` là giải pháp. Chúng có thể khiến ứng dụng quản trị nhầm tài nguyên hoặc làm thay đổi ownership khi shutdown.

### Race khi đăng ký

\`\`\`java
if (!server.isRegistered(name)) {
    server.registerMBean(bean, name);
}
\`\`\`

Kiểm tra trước không làm việc đăng ký thành thao tác nguyên tử. Trong môi trường nhiều thread/context, một bên khác có thể đăng ký cùng tên sau bước kiểm tra. Exception tại lúc register vẫn phải được xử lý.

## 14. Naming strategy và vòng đời exporter

Một ObjectName được tạo ở thời điểm đăng ký phải được dùng nhất quán để quản lý MBean đến cuối vòng đời. Khi Spring context dừng, exporter thường unregister những MBean mà nó quản lý.

Đối với bean động hoặc context khởi động lại:
- Tránh tên dựa trên timestamp hoặc random UUID nếu người dùng cần truy vấn tên ổn định.
- Giữ mapping ID logic → ObjectName để cleanup.
- Bảo đảm chỉ owner có trách nhiệm unregister MBean.
- Nếu tên đổi giữa hai lần register, script giám sát sẽ phải tìm lại.
- Nếu nhiều contexts cùng server, cần chiến lược namespacing và ownership rõ ràng.

Đừng đưa IP, PID, ephemeral port hoặc pod UID vào tên một cách máy móc. Đó có thể là metadata của JMX target thay vì thành phần định danh MBean trong một JVM.

## 15. Bảo mật khi đặt tên MBean

ObjectName thường xuất hiện trong JMX browser, logs, metrics exporter và monitoring. Không đặt secret hoặc thông tin cá nhân trực tiếp vào key properties.

Ví dụ không phù hợp:

\`\`\`text
com.example.app:type=ApiClient,token=secret-value
com.example.app:type=User,email=private@example.com
\`\`\`

Hãy dùng định danh quản trị không nhạy cảm:

\`\`\`text
com.example.app:type=ApiClient,name=primary
com.example.app:type=TenantQuota,tenant=tenant-042
\`\`\`

Nếu \`tenant\` là một định danh nội bộ nhạy cảm, cần đánh giá mức độ exposure và cơ chế bảo vệ riêng. Naming strategy không phải cơ chế phân quyền; JMX remote phải có authentication, authorization và transport security thích hợp.

## 16. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách điều tra |
|---|---|---|
| \`MalformedObjectNameException\` | Domain/key/value không hợp lệ | Validate token và tạo ObjectName có cấu trúc |
| \`InstanceAlreadyExistsException\` | Strategy tạo tên trùng hoặc export lặp | Kiểm tra mapping/owner và \`queryNames\` |
| Không tìm thấy MBean | Client dùng tên khác tên exporter đăng ký | Truy vấn pattern, dùng canonical name |
| Cùng class chỉ thấy một MBean | Strategy chỉ dùng tên class, không phân biệt instance | Bổ sung \`name\` hoặc key logic |
| Tên thay đổi sau restart | Sinh tên bằng timestamp/random ID | Dùng định danh ổn định |
| Annotation ghi một tên nhưng runtime có tên khác | Nhiều nguồn naming cùng tồn tại | Xác định strategy thực tế đang được dùng |
| Proxy gây lỗi lấy metadata | Strategy cast theo class implementation | Dựa vào interface hoặc bean key ổn định |
| Không thấy operation/attribute | Đây không phải lỗi naming | Kiểm tra \`MBeanInfoAssembler\` và metadata MBean |
| JConsole kết nối đúng JVM nhưng vẫn không thấy | Exporter dùng MBeanServer khác | Kiểm tra server configuration |
| MBean bị unregister ngoài ý muốn | Nhiều exporter/context tranh ownership | Kiểm tra lifecycle và duplicate registration |

**Phân biệt lỗi tên với lỗi giao diện quản trị:** \`ObjectNamingStrategy\` chỉ trả ObjectName. Nếu tên tồn tại mà attribute bị thiếu hoặc operation không gọi được, cần điều tra assembler, Standard MBean contract hoặc signature của operation.

## 17. Bài thực hành

### Bài 1 — Cùng một class, hai bean

Cho \`primaryPool\` và \`secondaryPool\` là hai bean thuộc \`WorkerPoolControl\). Nếu naming strategy chỉ dùng \`managedBean.getClass().getSimpleName()\`, điều gì xảy ra?

**Giải thích:** Hai bean có thể nhận cùng tên và xung đột trong một \`MBeanServer\`. Nên dùng bean key hoặc resource ID logic để phân biệt.

### Bài 2 — Truy vấn bằng ObjectName pattern

Viết Java code tìm tất cả worker pools trong domain \`com.example.platform\`:

\`\`\`java
ObjectName pattern = new ObjectName(
    "com.example.platform:type=WorkerPool,*"
);

for (ObjectName candidate : server.queryNames(pattern, null)) {
    System.out.println(candidate);
}
\`\`\`

Pattern dùng wildcard property list, tìm được MBean có thêm \`service\`, \`name\` hoặc các keys khác.

### Bài 3 — Vì sao không lấy class name làm định danh duy nhất?

Vì một class có thể có nhiều instances trong một JVM. Ngoài ra refactor tên class có thể làm đổi ObjectName dù vai trò quản trị không đổi.

### Bài 4 — Dùng annotation và custom strategy cùng lúc

Một bean có \`@ManagedResource(objectName="...")\`, exporter lại cấu hình custom strategy từ bean key. Cần làm gì?

**Giải thích:** Xác định nguồn tên được ưu tiên theo exporter/strategy đang dùng và kiểm tra ObjectName thực tế bằng \`queryNames\`. Về thiết kế, giảm số nguồn đặt tên để tránh mơ hồ.

### Bài 5 — Có cần thêm pod UID vào mỗi ObjectName không?

Không bắt buộc. Các pod/JVM có MBeanServer độc lập. Monitoring thường phân biệt pod bằng target metadata; ObjectName có thể giữ tên logic giống nhau trên các replicas.

### Bài 6 — Naming strategy tạo đúng tên nhưng client không thấy operation

Nên điều tra gì?

**Giải thích:** Kiểm tra \`MBeanInfo\`, assembler, annotation hoặc Standard MBean interface. Naming strategy không chọn method được expose.

## 18. Checklist áp dụng trong dự án

1. Xác định domain JMX cố định và được tổ chức sở hữu.
2. Định nghĩa key properties thống nhất: \`type\`, \`service\`, \`name\`, optional \`context\`, \`tenant\`, \`shard\`.
3. Chọn một nguồn sự thật về tên: explicit mapping, annotation metadata hoặc custom naming strategy.
4. Đảm bảo tên duy nhất trong từng MBeanServer.
5. Không phụ thuộc vào object identity, memory address hoặc random ID khi không cần.
6. Validation input để tránh ObjectName lỗi cú pháp và collision sau chuẩn hóa.
7. Tách naming khỏi MBean metadata assembling.
8. Kiểm tra MBeanServer đích và naming trong môi trường chạy thật.
9. Xác định ownership đăng ký/unregister và không export trùng qua nhiều exporter.
10. Coi thay đổi ObjectName là thay đổi API quản trị ảnh hưởng dashboards/scripts.

## 19. Tổng kết

**\`ObjectNamingStrategy\` là bộ quy tắc chuyển một bean và khóa nhận diện của nó thành \`ObjectName\`**. \`MBeanExporter\` sử dụng tên đó để đăng ký MBean trong \`MBeanServer\`; \`MBeanInfoAssembler\` hoặc hợp đồng MBean quyết định những gì client có thể đọc, ghi và gọi.

Dùng naming strategy khi cần tên nhất quán, nhiều bean hoặc nhiều instance, nhưng đừng làm tên phụ thuộc vào những chi tiết ngẫu nhiên của runtime. Hợp đồng tên tốt phải **hợp lệ, không trùng, dễ truy vấn, ổn định và không làm lộ dữ liệu nhạy cảm**. Sau khi export, kiểm tra \`queryNames\`, \`isRegistered\` và \`MBeanInfo\` để xác nhận ứng dụng đã công bố đúng tài nguyên quản trị.