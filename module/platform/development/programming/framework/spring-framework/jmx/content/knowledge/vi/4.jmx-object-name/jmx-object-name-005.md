# Chọn domain theo sản phẩm, mô-đun và môi trường trong JMX ObjectName

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của **domain** trong \`javax.management.ObjectName\` và phân biệt domain với key property.
- Thiết kế quy ước domain có hệ thống cho **sản phẩm**, **mô-đun** và **môi trường triển khai**.
- Quyết định khi nào cần đặt môi trường vào domain, khi nào nên đặt thành key property, và khi nào không cần mã hóa môi trường vào ObjectName.
- Tránh xung đột tên giữa nhiều MBean, thư viện, ứng dụng và instance.
- Thực hiện quy ước đặt tên bằng Java thuần và Spring JMX.
- Lập kế hoạch truy vấn, thay đổi tên và vận hành dashboard mà không làm mất khả năng tìm kiếm MBean.

## 2. Vì sao thiết kế domain từ đầu?

JMX (Java Management Extensions) cung cấp cơ chế giám sát và quản trị ứng dụng Java lúc đang chạy. Một MBean được đăng ký trong \`MBeanServer\` dưới một định danh \`ObjectName\`:

\`\`\`text
domain:key=value,key2=value2
\`\`\`

Ví dụ:

\`\`\`text
com.example.shop.orders:type=Queue,name=paymentEvents
\`\`\`

Trong đó:

- **Domain**: \`com.example.shop.orders\`.
- **Key properties**: \`type=Queue\`, \`name=paymentEvents\`.
- **MBeanServer**: phạm vi đăng ký và tìm kiếm ObjectName.

Domain giúp **tổ chức không gian tên** theo một quy tắc nhất quán. Nếu sản phẩm có nhiều mô-đun, chẳng hạn \`catalog\`, \`orders\` và \`payments\`, bạn muốn người vận hành nhận ra ngay MBean thuộc hệ thống nào:

\`\`\`text
com.example.shop.catalog:type=Cache,name=products
com.example.shop.orders:type=Queue,name=outbox
com.example.shop.payments:type=ConnectionPool,name=primary
\`\`\`

Khi mở JConsole hoặc truy vấn bằng \`MBeanServer.queryNames()\`, domain đóng vai trò điểm bắt đầu để nhóm và tìm tài nguyên.

Tuy nhiên, **domain không tạo ranh giới bảo mật**. Hai domain khác nhau trong cùng MBeanServer vẫn chịu chung cơ chế đăng ký và kiểm soát truy cập của server. Tách domain không thay thế việc phân quyền JMX, xác thực và giới hạn network exposure.

## 3. Domain trong đặc tả ObjectName

\`ObjectName\` gồm hai phần, ngăn cách bởi dấu hai chấm đầu tiên:

\`\`\`text
com.example.shop.orders:type=Queue,name=outbox
|---------------------| |--------------------|
         domain             key properties
\`\`\`

Domain là chuỗi mang tính logic, **không bắt buộc là tên Java package hoặc DNS thực**. Dùng dạng reverse DNS (ví dụ \`com.example...\`) là quy ước hữu ích vì giảm khả năng hai tổ chức đặt trùng tên.

Một số điều cần nhớ:

1. Domain là một phần của ObjectName: đổi domain sẽ tạo định danh JMX khác.
2. Domain có thể chứa các dấu chấm \`.\`; dấu chấm dùng để thể hiện phân cấp theo quy ước, không biến nó thành cấu trúc con bắt buộc.
3. ObjectName có phân biệt chữ hoa/chữ thường; \`com.example.Shop\` và \`com.example.shop\` là hai domain khác nhau.
4. Ký tự \`*\` và \`?\` trong domain có thể tạo một **domain pattern** dùng để truy vấn; tên đăng ký cần là ObjectName cụ thể.
5. Một domain có thể chứa nhiều MBean. Tính duy nhất khi đăng ký phụ thuộc vào **toàn bộ ObjectName**, gồm domain và tập hợp key property, trong phạm vi một MBeanServer.

Dùng \`getDomain()\` để lấy domain và \`isDomainPattern()\` để kiểm tra một tên có dùng pattern cho domain hay không.

Ví dụ:

\`\`\`java
import javax.management.ObjectName;

ObjectName name = new ObjectName(
        "com.example.shop.orders:type=Queue,name=outbox");

System.out.println(name.getDomain());
// com.example.shop.orders

System.out.println(name.isDomainPattern());
// false
\`\`\`

Trong thực tế, nếu một \`ObjectName\` có domain trống, MBeanServer có thể áp dụng default domain trong quá trình đăng ký. Với ứng dụng nhiều mô-đun, khai báo domain rõ ràng giúp tránh lệ thuộc vào default domain của từng server.

## 4. Ba trục cần xác định trước khi đặt tên

Trong một hệ thống có nhiều ứng dụng, dễ nhầm ba chiều phân loại sau:

| Trục | Câu hỏi | Ví dụ |
|---|---|---|
| **Sản phẩm / hệ thống** | MBean thuộc sản phẩm nào? | \`shop\`, \`billing\`, \`learning\` |
| **Mô-đun / thành phần** | Tài nguyên thuộc phần chức năng nào? | \`orders\`, \`catalog\`, \`payments\` |
| **Môi trường** | Instance đang chạy ở đâu? | \`dev\`, \`staging\`, \`prod\` |

Bạn cần thiết kế một **quy ước có thể vận hành**, không phải cố nhét mọi thông tin vào cùng một chuỗi domain.

Ví dụ một domain ngắn:

\`\`\`text
com.example.shop.orders
\`\`\`

và key property cho môi trường:

\`\`\`text
com.example.shop.orders:type=Queue,name=outbox,env=prod
\`\`\`

Có thể biểu diễn môi trường trong domain:

\`\`\`text
com.example.shop.prod.orders:type=Queue,name=outbox
\`\`\`

Hai lựa chọn này đều có thể hợp lệ, nhưng có hệ quả khác nhau về **truy vấn, đổi tên, biểu đồ giám sát và khả năng tái sử dụng cấu hình**. Không nên thay đổi tùy ý giữa các ứng dụng trong cùng một tổ chức.

## 5. Domain theo sản phẩm: namespace ổn định

Một quy ước cơ bản là:

\`\`\`text
<reverse-dns>.<product>
\`\`\`

Ví dụ:

\`\`\`text
com.example.shop:type=Cache,name=products
com.example.shop:type=Queue,name=orders
com.example.billing:type=BatchJob,name=settlement
\`\`\`

Cách này phù hợp khi mỗi sản phẩm có số lượng MBean vừa phải, hoặc bạn muốn giữ domain tương đối ngắn.

**Ưu điểm:**

- Dễ nhận biết đơn vị sở hữu.
- Ít rủi ro trùng domain với các thư viện ngoài.
- Domain có tính ổn định ngay cả khi tổ chức lại các package Java.
- Một truy vấn \`com.example.shop:*\` có thể tìm các MBean của sản phẩm trong cùng domain (khi dùng pattern phù hợp).

**Hạn chế:**

- Domain chỉ phân biệt đến cấp sản phẩm; các MBean của nhiều module cùng xuất hiện dưới một nhóm.
- Cần dùng các key property như \`module\`, \`type\`, \`name\` để tiếp tục phân loại.

Nếu chọn một domain chung toàn sản phẩm, có thể bổ sung key module:

\`\`\`text
com.example.shop:module=catalog,type=Cache,name=products
com.example.shop:module=orders,type=Queue,name=outbox
com.example.shop:module=payments,type=Pool,name=primary
\`\`\`

Mô hình này đặc biệt phù hợp khi dashboard muốn query cố định theo một domain và phân nhóm module bằng key.

## 6. Domain theo mô-đun: thuận tiện cho quan sát quy mô lớn

Với nhiều mô-đun hoặc nhiều nhóm phát triển, có thể dùng:

\`\`\`text
<reverse-dns>.<product>.<module>
\`\`\`

Ví dụ:

\`\`\`text
com.example.shop.catalog:type=Cache,name=products
com.example.shop.orders:type=Queue,name=outbox
com.example.shop.payments:type=ConnectionPool,name=primary
\`\`\`

Thiết kế này gom MBean theo module ngay trong domain. Công cụ JMX thường hiển thị danh sách domain, nên người vận hành dễ tìm tới nhóm thích hợp.

Quy tắc nên thống nhất:

- Tên sản phẩm/module viết chữ thường và ổn định.
- Đặt tên theo ranh giới sở hữu hoặc khả năng vận hành, không nhất thiết theo package Java.
- Tránh tên quá chi tiết như \`com.example.shop.orders.application.service.impl\` nếu tầng package có thể thay đổi thường xuyên.
- Giữ cùng ngữ nghĩa: \`orders\` luôn chỉ một module; không lúc dùng \`order\`, lúc dùng \`order-service\`.
- Sử dụng key \`type\` và \`name\` để phân biệt tài nguyên bên trong module.

**Quan trọng:** Dấu chấm trong domain không làm JMX hiểu \`com.example.shop\` là cha của \`com.example.shop.orders\` theo nghĩa quản lý cấu trúc. Đây chỉ là chuỗi tên. Muốn truy vấn theo tiền tố, phải dùng **domain pattern**.

Ví dụ:

\`\`\`text
com.example.shop.*:type=Queue,*
\`\`\`

được dùng để tìm các domain bắt đầu với \`com.example.shop.\` và có MBean với key \`type=Queue\`. Query này không bao gồm domain chính xác \`com.example.shop\` vì pattern có dấu chấm sau \`shop\`.

## 7. Nên đưa môi trường vào domain hay key property?

Không có một cách duy nhất đúng cho mọi hệ thống. Quyết định nên dựa trên cách tổ chức MBeanServer, yêu cầu giám sát và convention đã có.

### Phương án A: domain gồm môi trường

\`\`\`text
com.example.shop.dev.orders:type=Queue,name=outbox
com.example.shop.staging.orders:type=Queue,name=outbox
com.example.shop.prod.orders:type=Queue,name=outbox
\`\`\`

Ưu điểm:

- Tên domain tự thể hiện môi trường.
- Có thể xem danh sách domain theo môi trường nếu nhiều environment cùng được đăng ký vào một MBeanServer hoặc cùng được tổng hợp trong hệ thống giám sát.
- Query theo \`com.example.shop.prod.*:type=Queue,*\` dễ hiểu.

Đánh đổi:

- Mỗi môi trường có domain khác nhau; script/dashboard phải dùng pattern hoặc tham số cấu hình theo môi trường.
- Nếu trộn môi trường vào giữa sản phẩm và module, truy vấn tất cả domain của một module sẽ cần wildcard theo cả hai chiều.
- Việc đổi tên từ \`stage\` sang \`staging\` là thay đổi định danh, có thể làm hỏng dashboard hoặc client dùng tên cố định.

### Phương án B: môi trường là key property

\`\`\`text
com.example.shop.orders:type=Queue,name=outbox,env=dev
com.example.shop.orders:type=Queue,name=outbox,env=staging
com.example.shop.orders:type=Queue,name=outbox,env=prod
\`\`\`

Ưu điểm:

- Domain của module ổn định qua các môi trường.
- Dễ query mọi môi trường bằng \`com.example.shop.orders:type=Queue,*\`.
- Hệ thống có thể lọc hoặc nhóm theo key \`env\`.

Đánh đổi:

- Query theo domain đơn thuần không chỉ chọn một environment.
- Khi dùng key bắt buộc \`env\`, mọi code đăng ký cần thống nhất key này; quên key sẽ dẫn tới tên khác quy ước.
- Tên trở nên dài hơn, nhất là khi có nhiều chiều phân loại.

### Phương án C: không mã hóa môi trường vào ObjectName

\`\`\`text
com.example.shop.orders:type=Queue,name=outbox
\`\`\`

Trường hợp phổ biến: mỗi JVM và MBeanServer thuộc đúng một môi trường triển khai; hệ thống giám sát biết môi trường thông qua **kết nối, host, cluster, namespace Kubernetes hoặc metadata của collector**.

Ưu điểm:

- Cùng một ObjectName cho cùng một loại tài nguyên ở dev, staging, production.
- Script và dashboard dùng lại tên tương đối dễ.
- Không phụ thuộc biến môi trường trong code tạo \`ObjectName\`.

Đánh đổi:

- Khi xuất danh sách tên JMX khỏi ngữ cảnh MBeanServer, riêng ObjectName không đủ cho biết môi trường.
- Hệ thống thu thập và quan sát phải gắn môi trường từ nguồn dữ liệu ngoài.

**Cần phân biệt:** ObjectName duy nhất trong *một MBeanServer*, không phải trên toàn bộ máy chủ, cluster hay công ty. Hai JVM khác nhau có thể đăng ký cùng chuỗi \`com.example.shop.orders:type=Queue,name=outbox\` hoàn toàn bình thường. Do đó, không cần thêm \`env\` chỉ để ngăn trùng tên giữa hai JVM tách biệt.

## 8. Ma trận lựa chọn thực tế

| Bối cảnh | Cách tổ chức đề xuất | Vì sao |
|---|---|---|
| Một sản phẩm, vài MBean | Domain theo sản phẩm; key \`type\`, \`name\` | Đơn giản, ổn định |
| Sản phẩm nhiều module | Domain theo \`product.module\` | Phân nhóm rõ trên JConsole |
| Dashboard gom nhiều module | Domain chung theo sản phẩm + key \`module\` | Query cùng domain thuận tiện |
| Mỗi JVM thuộc một môi trường duy nhất | Không bắt buộc đưa \`env\` vào ObjectName | Server/collector đã cung cấp ngữ cảnh |
| Một MBeanServer thực sự chứa MBean đại diện nhiều môi trường | Domain môi trường hoặc key \`env\` | Cần phân biệt tài nguyên cùng tên |
| Công cụ vận hành lọc thường xuyên theo môi trường | Quy ước \`env\` nhất quán, trong domain hoặc key | Truy vấn có thể đoán trước |
| Nhiều instance cùng loại trong một MBeanServer | Key \`instance\` hoặc \`name\` phân biệt | Tránh \`InstanceAlreadyExistsException\` |

Ma trận này là hướng dẫn thiết kế, không phải quy tắc bắt buộc của JMX. Tốt nhất là công bố một naming convention và dùng thống nhất cho toàn bộ sản phẩm.

## 9. Một quy ước hoàn chỉnh cho sản phẩm Shop

Giả sử sản phẩm có ba module \`catalog\`, \`orders\`, \`payments\`. Mỗi module có cache, queue hoặc pool riêng.

### Mẫu domain

\`\`\`text
com.example.shop.<module>
\`\`\`

### Mẫu ObjectName

\`\`\`text
com.example.shop.<module>:type=<type>,name=<logical-name>
\`\`\`

Thêm các key khi có lý do cụ thể:

\`\`\`text
com.example.shop.<module>:type=<type>,name=<logical-name>,instance=<id>
\`\`\`

Danh sách ví dụ:

\`\`\`text
com.example.shop.catalog:type=Cache,name=productDetails
com.example.shop.catalog:type=Cache,name=categoryTree
com.example.shop.orders:type=Queue,name=outbox
com.example.shop.orders:type=WorkerPool,name=delivery
com.example.shop.payments:type=ConnectionPool,name=primary
\`\`\`

Nếu cần ghi môi trường trong cùng một server:

\`\`\`text
com.example.shop.orders:type=Queue,name=outbox,env=prod
\`\`\`

Một convention nội bộ có thể viết rõ:

1. Domain dùng \`com.example.shop.<module>\`, chữ thường, module lấy từ danh sách chính thức.
2. Key \`type\` mô tả loại tài nguyên bằng PascalCase (\`Cache\`, \`Queue\`, \`ConnectionPool\`).
3. Key \`name\` mô tả tên logic ổn định; không lấy từ random ID hoặc timestamp.
4. Key \`instance\` chỉ xuất hiện khi nhiều tài nguyên cùng \`type\` và \`name\` cùng tồn tại trong một MBeanServer.
5. Key \`env\` chỉ xuất hiện khi thực sự cần phân biệt môi trường trong ObjectName; giá trị lấy từ cấu hình xác thực của deployment.
6. Không đưa password, token, số thẻ, email khách hàng hoặc dữ liệu nhạy cảm vào domain hay key property.

Cần thống nhất **danh sách giá trị module** ở cấp sản phẩm. Nếu \`checkout\` đổi tên thành \`payments\`, phải coi đó là thay đổi hợp đồng định danh JMX và lập kế hoạch chuyển đổi client tương ứng.

## 10. Java: xây dựng ObjectName từ cấu hình

Ví dụ một factory tập trung cách đặt tên, tránh mỗi module nối chuỗi tùy ý.

\`\`\`java
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;
import java.util.Hashtable;
import java.util.Set;

public final class ShopJmxNames {
    private static final String ROOT_DOMAIN = "com.example.shop";
    private static final Set<String> MODULES =
            Set.of("catalog", "orders", "payments");

    private ShopJmxNames() {}

    public static ObjectName forResource(
            String module,
            String type,
            String logicalName) throws MalformedObjectNameException {

        if (!MODULES.contains(module)) {
            throw new IllegalArgumentException(
                    "Unsupported JMX module: " + module);
        }

        Hashtable<String, String> keys = new Hashtable<>();
        keys.put("type", requireSafeValue(type));
        keys.put("name", requireSafeValue(logicalName));

        ObjectName result = new ObjectName(
                ROOT_DOMAIN + "." + module, keys);

        if (result.isPattern()) {
            throw new IllegalArgumentException(
                    "Registration name must be concrete");
        }
        return result;
    }

    private static String requireSafeValue(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "JMX key value must not be blank");
        }

        // Quy ước đơn giản cho tên logic được kiểm soát.
        if (!value.matches("[A-Za-z0-9_.-]+")) {
            throw new IllegalArgumentException(
                    "Unsupported JMX key characters: " + value);
        }
        return value;
    }
}
\`\`\`

Sử dụng:

\`\`\`java
ObjectName queueName = ShopJmxNames.forResource(
        "orders", "Queue", "outbox");

System.out.println(queueName.getCanonicalName());
// com.example.shop.orders:name=outbox,type=Queue
\`\`\`

Tại sao dùng allowlist trong ví dụ? Trong ObjectName, dấu \`,\`, \`=\`, \`:\`, \`*\`, \`?\` và các ký tự đặc biệt khác có vai trò cú pháp hoặc pattern. Giá trị lấy từ cấu hình tùy ý cần được xử lý kỹ. Nếu muốn hỗ trợ tên người dùng chứa ký tự đặc biệt, có thể dùng \`ObjectName.quote()\` và cơ chế xử lý phù hợp, nhưng vẫn phải kiểm tra \`isPattern()\` trước khi đăng ký.

Factory phía trên chọn **quy ước hạn chế** thay vì hỗ trợ mọi chuỗi Unicode; đây là quyết định thiết kế cho ví dụ, không phải giới hạn phổ quát của Java JMX.

## 11. Đăng ký MBean với domain đã chọn

Giả sử có một Standard MBean quản lý queue:

\`\`\`java
public interface QueueMonitorMBean {
    int getPendingCount();
    void pause();
}

public class QueueMonitor implements QueueMonitorMBean {
    private int pendingCount = 5;

    @Override
    public int getPendingCount() {
        return pendingCount;
    }

    @Override
    public void pause() {
        // Tạm dừng queue theo logic ứng dụng.
    }
}
\`\`\`

Đăng ký vào platform MBeanServer:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName objectName =
        ShopJmxNames.forResource("orders", "Queue", "outbox");

server.registerMBean(new QueueMonitor(), objectName);

try {
    Object pending =
            server.getAttribute(objectName, "PendingCount");
    System.out.println("Pending: " + pending);
} finally {
    server.unregisterMBean(objectName);
}
\`\`\`

Trong chương trình dài hạn, không hủy đăng ký ngay sau khi đọc attribute; hãy gắn thao tác unregister với lifecycle shutdown của component. Nếu tên đã được sử dụng, \`registerMBean()\` báo \`InstanceAlreadyExistsException\`. Factory chỉ giúp đặt tên nhất quán, **không tự ngăn hai đối tượng đăng ký trùng một ObjectName**.

## 12. Lọc theo sản phẩm, mô-đun và môi trường

Có thể sử dụng \`ObjectName\` pattern trong \`MBeanServer.queryNames()\`:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

// Tìm Queue của mọi module thuộc sản phẩm Shop.
ObjectName allShopQueues = new ObjectName(
        "com.example.shop.*:type=Queue,*");

Set<ObjectName> result =
        server.queryNames(allShopQueues, null);

result.stream()
        .map(ObjectName::getCanonicalName)
        .sorted()
        .forEach(System.out::println);
\`\`\`

Khi \`env\` là key property:

\`\`\`java
ObjectName prodQueues = new ObjectName(
        "com.example.shop.*:type=Queue,env=prod,*");

Set<ObjectName> prod = server.queryNames(prodQueues, null);
\`\`\`

Khi \`env\` nằm trong domain:

\`\`\`java
ObjectName prodDomainQueues = new ObjectName(
        "com.example.shop.prod.*:type=Queue,*");
\`\`\`

Phần \`,*\` rất quan trọng: nó cho phép tên có thêm key properties ngoài những key liệt kê trong pattern.

### Cạm bẫy với domain pattern

Nếu một sản phẩm dùng lẫn:

\`\`\`text
com.example.shop:type=Cache,name=root
com.example.shop.orders:type=Queue,name=outbox
\`\`\`

thì pattern:

\`\`\`text
com.example.shop.*:*
\`\`\`

chỉ tìm các domain có tiền tố \`com.example.shop.\` mà không bao gồm đúng domain \`com.example.shop\`. Nếu muốn liệt kê cả hai dạng, hãy tạo truy vấn phù hợp cho từng nhóm hoặc chuẩn hóa domain từ đầu. Đừng giả định dấu chấm biểu thị quan hệ parent/child mà API tự xử lý.

### Cạm bẫy khi environment nằm bên ngoài MBeanServer

Một MBeanServer trong JVM \`prod\` không tự trả về MBean của JVM \`staging\` dù dùng pattern \`env=*\`. \`queryNames\` chỉ truy vấn **server đang kết nối**. Truy vấn toàn cluster hoặc mọi environment là trách nhiệm của hệ thống thu thập kết nối tới nhiều JVM.

## 13. Spring Framework: dùng domain thống nhất khi export

Spring Framework hỗ trợ xuất bean ra JMX thông qua \`MBeanExporter\` và các annotation như \`@ManagedResource\`, \`@ManagedAttribute\` và \`@ManagedOperation\`.

Ví dụ:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
        objectName = "com.example.shop.orders:type=Queue,name=outbox",
        description = "Order outbox monitor")
public class OrderOutboxManagement {

    private volatile int pendingCount;

    @ManagedAttribute
    public int getPendingCount() {
        return pendingCount;
    }
}
\`\`\`

\`@ManagedResource.objectName\` mô tả tên JMX dự kiến. Để MBean xuất hiện, object phải được quản lý và export bằng cơ chế Spring JMX thích hợp. Chỉ thêm annotation vào một class không bảo đảm MBean được đăng ký.

### Tên động theo cấu hình

Một số dự án cần domain hoặc key phụ thuộc môi trường. Không nên hardcode \`prod\` vào class dùng lại cho staging/dev. Thay vào đó, cấu hình một nơi tạo ObjectName hoặc naming strategy và đưa thông tin deployment vào lúc đăng ký.

Với Spring \`MBeanExporter\`, có thể ánh xạ tên ObjectName tường minh khi cấu hình:

\`\`\`java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxConfiguration {

    @Bean
    MBeanExporter queueExporter(QueueMonitor queueMonitor) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
                "com.example.shop.orders:type=Queue,name=outbox",
                queueMonitor));
        return exporter;
    }
}
\`\`\`

Ví dụ cần một \`QueueMonitor\` bean đã được định nghĩa ở nơi khác; Java class triển khai đúng Standard MBean interface \`QueueMonitorMBean\`. Trong ứng dụng thực tế, chỉ dùng một cơ chế export cho cùng ObjectName để tránh đăng ký hai lần. Spring có cơ chế đăng ký và quản lý lifecycle, nhưng xung đột giữa exporter hoặc MBean thủ công vẫn cần được kiểm soát.

Để lấy domain theo cấu hình, có thể đọc giá trị từ \`@ConfigurationProperties\` hoặc \`Environment\`, xác thực danh sách module/environment rồi dựng tên bằng factory trước khi đăng ký. Không nối dữ liệu deployment tùy ý vào ObjectName mà bỏ qua kiểm tra cú pháp.

## 14. Thiết kế cho nhiều instance và nhiều JVM

Một câu hỏi thường gặp: “Nếu chạy ba replica của cùng một service, phải thêm \`instance\` vào ObjectName không?”

Câu trả lời phụ thuộc phạm vi **MBeanServer**:

- Nếu mỗi replica là một JVM riêng, mỗi replica có platform MBeanServer riêng; cùng ObjectName được đăng ký ở mỗi JVM là bình thường.
- Nếu trong **cùng một JVM/MBeanServer** có nhiều queue monitor cùng \`type\` và \`name\`, phải có key phân biệt, ví dụ \`instance\`.
- Khi hệ thống monitoring hợp nhất số đo nhiều JVM, identity bên ngoài còn gồm target/connection/instance metadata, không nên chỉ dựa vào ObjectName.

Ví dụ hai queue instance trong cùng JVM:

\`\`\`text
com.example.shop.orders:type=Queue,name=outbox,instance=primary
com.example.shop.orders:type=Queue,name=outbox,instance=retry
\`\`\`

Ví dụ hai replica khác JVM đều có:

\`\`\`text
com.example.shop.orders:type=Queue,name=outbox
\`\`\`

Không gây xung đột đăng ký vì thuộc hai MBeanServer khác nhau.

**Tránh đưa pod ID ngẫu nhiên vào domain mặc định.** Nếu pod ID chỉ là metadata triển khai, đưa nó vào tên làm ObjectName thay đổi mỗi lần rollout, có thể phá vỡ dashboard dùng tên tĩnh. Nếu một JVM thật sự chứa nhiều instance cần phân biệt, key \`instance\` có thể phù hợp hơn. Chỉ chọn ID động khi quy trình quan sát đã được thiết kế để xử lý identity đó.

## 15. Domain và tính ổn định của hợp đồng vận hành

ObjectName là một phần của **hợp đồng vận hành** giữa ứng dụng và công cụ giám sát. Thay đổi domain có thể ảnh hưởng tới:

- JConsole/JMC hoặc công cụ JMX tìm MBean theo domain cố định.
- Dashboard, alert rule và exporter chọn metric dựa trên ObjectName.
- Script quản trị gọi \`MBeanServer.getAttribute\`, \`invoke\` hoặc \`queryNames\`.
- Tài liệu vận hành và quy trình hỗ trợ sự cố.

Ví dụ:

\`\`\`text
Tên cũ:
com.example.shop.orders:type=Queue,name=outbox

Tên mới:
com.example.shop.fulfillment:type=Queue,name=outbox
\`\`\`

Dù tên Java class hoặc operation không thay đổi, các client dùng ObjectName cũ vẫn không tự tìm được tên mới.

### Quy trình chuyển đổi tên

1. Ghi nhận danh sách ObjectName hiện hành và client đang sử dụng chúng.
2. Chọn naming convention mới và mô tả lý do thay đổi.
3. Cập nhật query/dashboard để có thể hiểu tên mới.
4. Khi phù hợp, dùng một giai đoạn chuyển tiếp có kiểm soát; cân nhắc khả năng đăng ký thêm alias MBean hoặc xuất song song qua lớp quản trị riêng, nếu thiết kế triển khai cho phép và không xung đột.
5. Kiểm tra các truy vấn và alert sau rollout, rồi loại bỏ đường tên cũ khi không còn consumer.

Việc đăng ký một **MBean instance** dưới nhiều ObjectName có thể chịu ảnh hưởng của lifecycle và quy tắc đăng ký của implementation; không mặc định alias sẽ khả dụng cho mọi MBean. Tốt hơn nên xem chuyển đổi naming là thay đổi hợp đồng và thử nghiệm trên hệ thống phù hợp trước khi triển khai.

## 16. Những lỗi thường gặp

| Vấn đề | Vì sao xảy ra | Cách tránh |
|---|---|---|
| Domain quá chung như \`app\` | Nhiều thư viện/module dùng cùng namespace | Dùng prefix theo tổ chức/sản phẩm |
| Domain chứa chi tiết package \`impl\` | Refactor Java làm thay đổi tên quản trị | Dùng tên theo module logic ổn định |
| Cùng sản phẩm nhưng tên \`order\` và \`orders\` | Convention không thống nhất | Chuẩn hóa danh mục module |
| Ghi \`prod\` cứng trong source | Không tái sử dụng được giữa môi trường | Dùng cấu hình hoặc collector metadata |
| Thêm \`env\` vì sợ trùng tên giữa JVM | Nhầm phạm vi duy nhất của ObjectName | Hiểu identity gắn với từng MBeanServer |
| Query theo domain con nhưng bỏ sót domain gốc | Pattern \`com.example.shop.*\` chỉ khớp tiền tố có dấu chấm | Tách query hoặc chuẩn hóa naming |
| \`MalformedObjectNameException\` | Chứa ký tự cú pháp chưa xử lý | Validate/encode giá trị domain và key |
| \`InstanceAlreadyExistsException\` | Hai MBean cùng domain + key properties trong một server | Thêm key phân biệt hoặc sửa lifecycle |
| Dashboard mất metric sau đổi domain | Client tìm ObjectName cũ | Migration và cập nhật query/alert |
| Tên chứa thông tin khách hàng | ObjectName có thể hiển thị qua công cụ quản trị/log | Không đưa secret/PII vào identity |

## 17. Thực hành

### Bài tập 1 — Thiết kế domain cho một sản phẩm

Sản phẩm \`learning\` có các module \`course\`, \`enrollment\` và \`notification\`. Hãy đặt ObjectName cho:

- Cache danh sách khóa học.
- Queue email thông báo.
- Bộ đếm enrollment đang xử lý.

Một phương án tham khảo:

\`\`\`text
com.example.learning.course:type=Cache,name=courseList
com.example.learning.notification:type=Queue,name=email
com.example.learning.enrollment:type=Counter,name=inProgress
\`\`\`

Hãy giải thích lý do domain theo module và key \`name\` theo tài nguyên.

### Bài tập 2 — So sánh mô hình môi trường

Hai cách đặt tên:

\`\`\`text
com.example.shop.prod.orders:type=Queue,name=outbox
com.example.shop.orders:type=Queue,name=outbox,env=prod
\`\`\`

Hãy viết một query chọn các queue \`prod\` theo từng mô hình và giải thích vì sao hai query không thay thế cho nhau.

Đáp án tham khảo:

\`\`\`text
com.example.shop.prod.*:type=Queue,*
com.example.shop.*:type=Queue,env=prod,*
\`\`\`

Pattern thứ nhất giả định \`prod\` nằm trong domain; pattern thứ hai giả định \`env\` là key. Cả hai chỉ tìm trong MBeanServer mà client đang truy vấn.

### Bài tập 3 — Phát hiện trùng tên

Một JVM đăng ký:

\`\`\`text
com.example.shop.orders:type=Queue,name=outbox
com.example.shop.orders:type=Queue,name=outbox
\`\`\`

Lần đăng ký thứ hai sẽ thất bại nếu tên đầu vẫn đang tồn tại. Hãy đề xuất \`instance=primary\` và \`instance=retry\` nếu thực sự có hai hàng đợi độc lập cùng tên logic.

### Bài tập 4 — Thiết kế factory

Viết \`ObjectNameFactory\` với ba tham số: \`module\`, \`type\`, \`name\`. Quy ước:

- Root domain: \`com.example.shop\`.
- Module hợp lệ: \`orders\`, \`payments\`, \`catalog\`.
- Key \`type\` và \`name\` không được rỗng.
- Nếu giá trị có ký tự đặc biệt, reject hoặc encode có chủ đích.
- Sau khi tạo tên, kiểm tra \`isPattern() == false\`.

Tạo 3 ObjectName và in \`getCanonicalName()\`; giải thích vì sao thứ tự key in ra có thể khác thứ tự khai báo.

### Bài tập 5 — Lập kế hoạch đổi domain

Một ứng dụng đổi module \`orders\` thành \`fulfillment\`. Hãy mô tả những tài nguyên bên ngoài mã Java cần kiểm tra: dashboard, JMX exporter, alert, scripts, tài liệu vận hành, và những consumer dùng ObjectName cố định.

## 18. Câu hỏi tự kiểm tra

**1. Có bắt buộc thêm môi trường vào domain để tên JMX duy nhất trên toàn cluster không?**

Không. Tính duy nhất của một ObjectName khi đăng ký là trong một MBeanServer. Một cluster có nhiều JVM và MBeanServer độc lập.

**2. Domain \`com.example.shop.orders\` có phải Java package thật không?**

Không. Đó có thể là tên logic theo quy ước, không bắt buộc trùng package.

**3. \`com.example.shop.*:type=Queue,*\` có tìm được MBean thuộc domain \`com.example.shop\` không?**

Không, vì pattern yêu cầu tiền tố \`com.example.shop.\`.

**4. Khi nào môi trường nên là key \`env\`?**

Khi cần phân biệt hoặc lọc môi trường trực tiếp trong ObjectName trong cùng ngữ cảnh quản lý, và tổ chức đã thống nhất convention đó.

**5. Nếu đổi domain mà giữ nguyên các key, có còn là cùng ObjectName không?**

Không. Domain là một phần của định danh.

**6. Domain khác nhau có cách ly quyền JMX không?**

Không. Việc kiểm soát quyền nằm ở cơ chế bảo mật và quản lý kết nối/MBeanServer.

## 19. Ghi nhớ

- Domain là **namespace logic** trong \`ObjectName\`, nên phản ánh sản phẩm và mô-đun theo quy ước dễ đọc, ổn định.
- Phân chia theo sản phẩm hay module là quyết định kiến trúc vận hành, không có một hierarchy JMX bắt buộc.
- Môi trường có thể nằm trong domain, key property hoặc metadata ngoài JMX; chọn theo nhu cầu truy vấn và phạm vi MBeanServer.
- Cùng một ObjectName có thể tồn tại trong các JVM khác nhau; trong cùng MBeanServer thì không thể đăng ký hai MBean đồng thời dưới tên cụ thể trùng nhau.
- Query domain là **pattern matching chuỗi**, không có nhận thức cây thư mục; đừng bỏ qua dấu chấm trong domain prefix.
- Naming convention cần đi kèm factory/configuration thống nhất, quy tắc tránh tên động và kế hoạch migration nếu đổi domain.
- Không đưa thông tin nhạy cảm vào ObjectName; domain cũng không phải ranh giới authorization.

## 20. Tài liệu tham khảo

- Java SE 21 API — \`javax.management.ObjectName\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
- Java SE 21 API — \`javax.management.MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Oracle JMX Tutorial: https://docs.oracle.com/javase/tutorial/jmx/
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
