# IdentityNamingStrategy và định danh theo identity trong Spring Framework JMX

## 1. Mục tiêu bài học

Khi Spring Framework đưa bean ra JMX bằng \`MBeanExporter\`, mỗi MBean phải được đăng ký dưới một \`javax.management.ObjectName\` duy nhất trong phạm vi \`MBeanServer\`. Spring có giao diện \`ObjectNamingStrategy\` để quyết định tên này. Một trong các implementation có sẵn là **\`IdentityNamingStrategy\`**, tạo ObjectName dựa trên *identity* của đối tượng được export.

Ý tưởng là phân biệt **những object instance khác nhau**, ngay cả khi chúng có cùng class hoặc cùng tên bean logic. Đổi lại, tên được sinh từ identity có thể không ổn định khi application restart hoặc khi tạo lại instance. Vì vậy chiến lược này phù hợp với một số nhu cầu kỹ thuật, nhưng không mặc định là lựa chọn tốt nhất cho monitoring/dashboard lâu dài.

Sau bài học, bạn có thể:

- Hiểu vai trò của \`ObjectNamingStrategy\` trong đường export Spring JMX.
- Phân biệt object identity, \`equals()\`, \`hashCode()\` và tên logic của resource.
- Mô tả cách \`IdentityNamingStrategy\` tạo tên để phân biệt các instance.
- Cấu hình chiến lược đặt tên trong \`MBeanExporter\`.
- Hiểu lợi ích và giới hạn đối với multiple instances, proxies, restart và ApplicationContext.
- Xác minh tên thực tế qua \`MBeanServer.queryNames()\` thay vì đoán.
- Lựa chọn identity naming hoặc naming strategy ổn định theo consumer contract.

## 2. ObjectName là danh tính JMX, không phải tên Java bean

Một \`ObjectName\` có cú pháp:

\`\`\`text
<domain>:<key1>=<value1>,<key2>=<value2>
\`\`\`

Ví dụ:

\`\`\`text
com.example:type=Worker,name=Primary
\`\`\`

Tên này chỉ duy nhất một MBean **trong một \`MBeanServer\`**. Cùng một ObjectName có thể tồn tại trong hai MBeanServer khác nhau. Mặt khác, hai Spring beans cùng class nhưng khác instance không thể cùng đăng ký vào một MBeanServer dưới đúng một ObjectName.

Ví dụ:

\`\`\`java
Worker first = new Worker();
Worker second = new Worker();

System.out.println(first == second); // false
\`\`\`

Nếu bạn dùng cùng tên \`com.example:type=Worker,name=Default\` cho cả hai, lượt đăng ký thứ hai sẽ gặp xung đột \`InstanceAlreadyExistsException\`, trừ khi exporter có chính sách xử lý trùng tên khác.

\`IdentityNamingStrategy\` nhằm giải quyết bài toán phân biệt object theo identity thay vì buộc lập trình viên gán một tên logic duy nhất cho từng instance.

### 2.1. Object identity khác logical equality

Trong Java:

\`\`\`java
a == b
\`\`\`

kiểm tra hai tham chiếu có trỏ đến cùng một object hay không.

\`\`\`java
a.equals(b)
\`\`\`

kiểm tra quy tắc equality do class định nghĩa. Hai object khác nhau có thể \`equals() == true\`.

\`\`\`java
System.identityHashCode(a)
\`\`\`

trả về hash code dựa trên identity semantics của object, không phụ thuộc implementation \`hashCode()\` do class override. Tuy nhiên giá trị này không phải định danh bền vững và không được bảo đảm duy nhất tuyệt đối trong mọi thời điểm.

**Chú ý:** “định danh theo identity” là định danh trong vòng đời JVM/object, không phải khóa nghiệp vụ, UUID ổn định hoặc hostname.

## 3. ObjectNamingStrategy trong đường export

Trong Spring JMX, \`org.springframework.jmx.export.naming.ObjectNamingStrategy\` là chiến lược trả về \`ObjectName\` cho object được xuất.

Đường đi khái quát:

\`\`\`text
Spring-managed bean / object to export
                  |
                  v
             MBeanExporter
                  |
                  +----> ObjectNamingStrategy
                  |            |
                  |            v
                  |        ObjectName
                  |
                  +----> MBeanInfoAssembler
                  |      (metadata của MBean)
                  |
                  v
      MBeanServer.registerMBean(...)
                  |
                  v
         JMX clients / JConsole
\`\`\`

\`ObjectNamingStrategy\` quyết định **đặt tên**, còn \`MBeanInfoAssembler\` quyết định **attributes/operations** được công bố. Hai cơ chế không thay thế nhau. Khi metadata/JMX interface không hợp lệ, đổi naming strategy không giải quyết được lỗi tuân thủ MBean.

Các lựa chọn phổ biến:

| Chiến lược | Nguồn quyết định tên | Phù hợp |
|---|---|---|
| \`IdentityNamingStrategy\` | Identity của object được export | Instance tạm thời, cần phân biệt object cùng class |
| \`KeyNamingStrategy\` | Mapping/configuration key được định nghĩa | Tên quản trị có quy ước ổn định |
| \`MetadataNamingStrategy\` | Metadata trên managed resource | Tên khai báo qua \`@ManagedResource\` |
| Naming strategy tùy chỉnh | Class/module/tenant/instance đã chuẩn hóa | Hợp đồng monitoring có naming convention đặc thù |

Spring có thể dùng \`ObjectName\` tường minh từ mapping, hoặc naming strategy theo cách cấu hình. Không giả định tất cả exporter mặc định luôn sử dụng \`IdentityNamingStrategy\`: cần kiểm tra cấu hình exporter thực tế và phiên bản Spring đang dùng.

## 4. IdentityNamingStrategy tạo tên thế nào?

\`IdentityNamingStrategy\` là implementation của \`ObjectNamingStrategy\` dùng identity của managed object để xây dựng một ObjectName. Ý tưởng quan trọng là tên có thể phân biệt instance, thay vì dựa đơn thuần vào bean name.

\`\`\`text
Instance A của Worker ----> ObjectName A
Instance B của Worker ----> ObjectName B
\`\`\`

Khi cùng một instance được hỏi tên lại theo cùng strategy, mục tiêu là tên gắn với instance ấy. Tuy nhiên các chi tiết cụ thể của domain, key-property và biểu diễn identity do implementation Spring quyết định. **Không tự suy đoán một chuỗi ObjectName cụ thể** nếu chưa gọi strategy hoặc quan sát tên được đăng ký trên JVM của chính bạn.

Một cách kiểm tra trực tiếp:

\`\`\`java
import org.springframework.jmx.export.naming.IdentityNamingStrategy;
import javax.management.ObjectName;

public class IdentityNameDemo {
    static class Worker {}

    public static void main(String[] args) throws Exception {
        IdentityNamingStrategy naming = new IdentityNamingStrategy();

        Worker a = new Worker();
        Worker b = new Worker();

        ObjectName nameA = naming.getObjectName(a, "worker");
        ObjectName nameB = naming.getObjectName(b, "worker");

        System.out.println("A = " + nameA);
        System.out.println("B = " + nameB);
        System.out.println("Equal? " + nameA.equals(nameB));
        System.out.println("A is pattern? " + nameA.isPattern());
    }
}
\`\`\`

Khi chạy ví dụ với dependency Spring JMX phù hợp, hãy đọc chính kết quả runtime để biết ObjectName thực tế. Nếu \`ObjectName\` thay đổi giữa các lần chạy JVM, đó là dấu hiệu chiến lược đang phù hợp với định danh theo instance hơn là hợp đồng cố định.

**Giới hạn cần nhớ:** identity hash code có thể va chạm về mặt lý thuyết; vì vậy nó không phải giải pháp bảo đảm định danh duy nhất toàn cục cho mọi object hoặc mọi JVM. Khi hệ thống yêu cầu định danh tuyệt đối, dài hạn, hãy dùng khóa ổn định được quản lý riêng.

## 5. Ví dụ: hai object có cùng class

Giả sử một ứng dụng quản lý hai worker:

\`\`\`java
public class QueueWorker {
    private final String queue;

    public QueueWorker(String queue) {
        this.queue = queue;
    }

    public String getQueue() {
        return queue;
    }
}
\`\`\`

Hai instance:

\`\`\`java
QueueWorker orders = new QueueWorker("orders");
QueueWorker returns = new QueueWorker("returns");
\`\`\`

Một naming strategy chỉ sử dụng class name có thể sinh cùng ObjectName cho cả hai:

\`\`\`text
example:type=QueueWorker
example:type=QueueWorker
\`\`\`

Identity naming nhằm tạo hai ObjectName khác nhau, không cần biết \`orders\` hay \`returns\` là tên queue. Tuy nhiên dashboard muốn quan sát riêng queue \`orders\` sẽ khó hơn nếu tên chỉ gắn với instance. Nếu nhu cầu là resource theo **nghiệp vụ**, nên ưu tiên đặt tên dạng:

\`\`\`text
example.queue:type=QueueWorker,name=orders
example.queue:type=QueueWorker,name=returns
\`\`\`

Các tên đó ổn định khi cùng queue được tạo lại ở lần khởi động sau.

### 5.1. Mục tiêu lựa chọn khác nhau

Nếu mục tiêu là chẩn đoán những object sống tạm trong một JVM, identity naming có thể hữu ích.

Nếu mục tiêu là cấu hình cảnh báo lâu dài:

\`\`\`text
Alert when example.queue:type=QueueWorker,name=orders is unhealthy
\`\`\`

naming theo khóa nghiệp vụ giúp client không phải tìm lại ObjectName mới mỗi lần restart.

## 6. Cấu hình MBeanExporter với IdentityNamingStrategy

Một ví dụ Spring Java configuration sử dụng explicit export:

\`\`\`java
package example.jmx;

import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.naming.IdentityNamingStrategy;

@Configuration
public class JmxConfiguration {

    @Bean
    public WorkerStatus workerStatus() {
        return new WorkerStatus();
    }

    @Bean
    public MBeanExporter mbeanExporter(
            MBeanServer mbeanServer,
            WorkerStatus workerStatus) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mbeanServer);
        exporter.setNamingStrategy(new IdentityNamingStrategy());
        exporter.setBeans(Map.of("workerStatus", workerStatus));
        return exporter;
    }
}
\`\`\`

Class quản trị có thể tuân theo Standard MBean interface:

\`\`\`java
// WorkerStatusMBean.java
public interface WorkerStatusMBean {
    boolean isHealthy();
}
\`\`\`

\`\`\`java
// WorkerStatus.java
public class WorkerStatus implements WorkerStatusMBean {
    @Override
    public boolean isHealthy() {
        return true;
    }
}
\`\`\`

Và cung cấp MBeanServer trong cấu hình:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;

@Bean
public MBeanServer mbeanServer() {
    return ManagementFactory.getPlatformMBeanServer();
}
\`\`\`

Đoạn \`@Bean\` cho server cần nằm trong một class \`@Configuration\`, hoặc bạn có thể dùng configuration class khác cung cấp bean server. Ở ví dụ, \`setBeans\` chứa key logic \`workerStatus\`, còn naming strategy quyết định ObjectName khi exporter sử dụng chiến lược ấy.

**Điểm quan trọng khi cấu hình:** mapping key có thể là ObjectName tường minh hoặc là một key mà naming strategy diễn giải; cách kết hợp cụ thể cần được hiểu theo Spring API. Đừng giả định \`IdentityNamingStrategy\` sẽ ghi đè mọi ObjectName hard-coded đã cung cấp trong một cấu hình khác.

## 7. Kiểm chứng tên trong MBeanServer

Cách an toàn để xác minh tên thật của bean là query MBeanServer sau khi exporter hoàn tất đăng ký.

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.util.Set;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

Set<ObjectName> names =
    server.queryNames(new ObjectName("*:*"), null);

for (ObjectName name : names) {
    System.out.println(name.getCanonicalName());
}
\`\`\`

Trong production, \`*:* \` có thể trả nhiều platform/application MBeans; thay bằng domain hoặc pattern hẹp sau khi xác định format name do strategy tạo. Nên dùng \`MBeanServer.queryNames\` vì tên generated có thể không quen thuộc với client.

Sau khi tìm được ObjectName, client có thể:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(name);
Object healthy = server.getAttribute(name, "Healthy");
\`\`\`

Nhưng client cần chọn đúng MBean, không thể chỉ dựa vào tên class nếu nhiều instance cùng class. Nếu identity naming không chứa thông tin nghiệp vụ để phân biệt, có thể cần attribute \`QueueName\` hoặc registry riêng để map resource sang ObjectName.

### 7.1. Tại sao không dùng tên in từ lần chạy trước?

Identity của object thường chỉ có ý nghĩa trong một vòng đời. Sau restart, object mới có thể nhận identity khác. Hard-code ObjectName generated vào dashboard tạo dependency vào chi tiết runtime dễ biến động.

## 8. Object identity, equals và hashCode

Ba loại nhận diện thường bị đánh đồng:

\`\`\`java
a == b                      // cùng instance?
a.equals(b)                 // logic equality?
System.identityHashCode(a)  // identity-based hash value
\`\`\`

Ví dụ:

\`\`\`java
record WorkerKey(String queue) {}

WorkerKey a = new WorkerKey("orders");
WorkerKey b = new WorkerKey("orders");

System.out.println(a == b);                        // false
System.out.println(a.equals(b));                    // true
System.out.println(a.hashCode() == b.hashCode());  // true
\`\`\`

Dù \`a.equals(b)\` là true, chúng vẫn là hai Java objects khác nhau. Naming theo **identity** muốn nhận diện đối tượng, không phải khóa \`queue\`.

Nhưng \`identityHashCode\` chỉ là hash code, **không phải UUID**. Giá trị này không được bảo đảm không trùng trên mọi object; không ổn định qua JVM restart; không nên làm khóa phân tán hoặc khóa persistence.

## 9. Spring AOP proxy và identity

Spring beans có thể được bọc bởi JDK dynamic proxy hoặc CGLIB proxy để thực thi transaction, security, caching hoặc logging.

\`\`\`text
Target object
    |
    v
Spring proxy
    |
    v
MBeanExporter registers an object
\`\`\`

Câu hỏi cốt lõi: strategy nhận instance nào? Target hay proxy? Điều đó phụ thuộc đường export và cấu hình.

Nếu naming tính theo identity của proxy, việc tạo lại proxy có thể đổi tên MBean dù target logic chưa thay đổi. Vì vậy:

- Xem ObjectName đã đăng ký thay vì suy đoán theo identity của object ban đầu.
- Test khi chuyển bean từ không proxy sang có proxy.
- Nếu naming cần ổn định theo resource, dùng khóa nghiệp vụ.
- Tránh phụ thuộc vào generated name khi proxy lifecycle không do bạn kiểm soát.

Cũng cần kiểm tra assembler/adapter có expose đúng MBean attributes và operations khi đối tượng là proxy; naming strategy chỉ giải quyết tên, không tự giải quyết metadata.

## 10. Nhiều ApplicationContext và identity naming

Khi nhiều ApplicationContext export MBean vào cùng MBeanServer, identity naming có thể giúp phân biệt những instance khác nhau của cùng class. Tuy nhiên:

1. Mỗi context có thể có exporter và vòng đời riêng.
2. Tên được tạo không phải hợp đồng ổn định cho external client.
3. Nếu cùng một object được export bởi hai exporter, có thể có cùng identity-derived name và collision.
4. Nếu two distinct objects trùng identity hash ở trường hợp hiếm, chiến lược chỉ dựa vào hash có thể không tránh được collision tuyệt đối.
5. Nếu object bị thay thế khi context refresh, generated ObjectName có thể đổi.
6. Dù naming strategy khác nhau, tính duy nhất vẫn được kiểm tra trong MBeanServer chung.

Với module ổn định, nên cân nhắc:

\`\`\`text
example.platform:type=Worker,module=inventory,name=Primary
example.platform:type=Worker,module=billing,name=Primary
\`\`\`

Với plugin instance động, có thể dùng một instance ID do ứng dụng tạo và quản lý, ví dụ:

\`\`\`text
example.platform:type=PluginWorker,plugin=exporter,instance=8a7b
\`\`\`

Không đưa token, email hay dữ liệu nhạy cảm vào ObjectName. Instance ID nên được validate/escape đúng quy tắc ObjectName và có chính sách vòng đời.

## 11. Vòng đời: registration và unregistration

ObjectName generated phản ánh object tồn tại trong một giai đoạn. Khi Spring context đóng, exporter thông thường hủy đăng ký các MBean mà nó sở hữu. Nếu ứng dụng tạo rồi hủy plugin contexts, cần bảo đảm:

\`\`\`text
Context start -> new object -> new ObjectName -> registered
Context close -> exporter cleanup -> ObjectName unregistered
Context restart -> new object -> possibly new ObjectName
\`\`\`

Các lỗi thường gặp:

- Không đóng ApplicationContext đã tạo.
- Đăng ký MBean thủ công ngoài exporter nhưng không unregister.
- Hai exporter cùng nhận một object và đăng ký cùng tên.
- Sử dụng \`RegistrationPolicy.REPLACE_EXISTING\` làm mờ ownership.
- Client vẫn giữ ObjectName cũ sau khi context refresh.

**Không giải quyết lỗi lifecycle bằng cách xóa mọi MBean có cùng domain**. Một module khác có thể đang sở hữu chúng. Từng exporter/context phải quản lý chính xác registrations của mình.

## 12. IdentityNamingStrategy so với KeyNamingStrategy và MetadataNamingStrategy

| Tiêu chí | IdentityNamingStrategy | KeyNamingStrategy | MetadataNamingStrategy |
|---|---|---|---|
| Nguồn tên | Identity object | Mapping tên do cấu hình chỉ định | Metadata quản trị |
| Tên ổn định qua restart | Không nên kỳ vọng | Có, nếu mapping giữ nguyên | Có, nếu metadata giữ nguyên |
| Phân biệt nhiều instance cùng class | Hướng tới phân biệt instance | Phải cấp key khác nhau | Phải cấp metadata/name khác nhau |
| Dễ dùng cho dashboard cố định | Không lý tưởng | Thường tốt | Thường tốt |
| Phụ thuộc vào instance/proxy | Cao hơn | Thấp hơn nếu dùng ID logic | Thấp hơn nếu metadata ổn định |
| Dễ debug theo tên resource | Có thể khó | Tốt nếu key rõ nghĩa | Tốt nếu metadata rõ nghĩa |

Chọn theo **loại danh tính cần bảo vệ**:

- Identity của Java instance: object tồn tại trong JVM lúc này.
- Identity nghiệp vụ: resource \`inventoryQueue\` tồn tại qua nhiều lần restart.
- Identity triển khai: instance ứng dụng \`node-1\`, pod ID hoặc plugin instance.

Không có naming strategy duy nhất tốt nhất cho mọi hệ thống.

## 13. Thiết kế naming strategy tùy chỉnh theo resource ID

Nếu client cần một ObjectName ổn định, có thể triển khai \`ObjectNamingStrategy\` dựa trên một interface chỉ danh tính.

\`\`\`java
public interface ManagedIdentity {
    String managementType();
    String managementName();
}
\`\`\`

\`\`\`java
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;
import org.springframework.jmx.export.naming.ObjectNamingStrategy;

public class ResourceNamingStrategy implements ObjectNamingStrategy {
    @Override
    public ObjectName getObjectName(Object managedBean, String beanKey)
            throws MalformedObjectNameException {
        if (!(managedBean instanceof ManagedIdentity resource)) {
            throw new IllegalArgumentException(
                "ManagedIdentity required: " + beanKey);
        }

        String type = ObjectName.quote(resource.managementType());
        String name = ObjectName.quote(resource.managementName());

        return new ObjectName(
            "example.management:type=" + type + ",name=" + name);
    }
}
\`\`\`

Lưu ý: \`ObjectName.quote\` tạo giá trị property được quote; cần xét tương tác với wildcard và kiểm tra \`isPattern()\` nếu giá trị nguồn chứa ký tự đặc biệt. Các giá trị resource ID có thể được chuẩn hóa và validate trước khi tạo ObjectName. Đối với interface này, nên tránh nhận arbitrary input chưa kiểm soát.

Nếu bean là Spring proxy không trực tiếp implement \`ManagedIdentity\`, cần cách tìm ID thông qua cấu hình/metadata hoặc target-aware strategy phù hợp; không nên giả định cast luôn thành công.

### 13.1. Stable ID và uniqueness

Một naming strategy theo resource ID phải bảo đảm unique trong server:

\`\`\`text
example.management:type="Worker",name="orders"
example.management:type="Worker",name="returns"
\`\`\`

Nếu hai instance đồng thời có cùng resource ID, vẫn xảy ra collision. Điều này là đúng: hệ thống cần quyết định liệu hai instance đại diện cho một resource hay hai resource riêng và bổ sung key \`instance\` nếu cần.

## 14. Kiểm thử naming strategy

### 14.1. Kiểm thử cùng instance và hai instance

\`\`\`java
import org.junit.jupiter.api.Test;
import org.springframework.jmx.export.naming.IdentityNamingStrategy;

import javax.management.ObjectName;

import static org.junit.jupiter.api.Assertions.*;

class IdentityNamingStrategyTest {

    @Test
    void namingReflectsObjectIdentity() throws Exception {
        IdentityNamingStrategy strategy =
            new IdentityNamingStrategy();

        Object first = new Object();
        Object second = new Object();

        ObjectName a1 =
            strategy.getObjectName(first, "firstBean");
        ObjectName a2 =
            strategy.getObjectName(first, "firstBean");
        ObjectName b =
            strategy.getObjectName(second, "secondBean");

        assertEquals(a1, a2);
        assertFalse(a1.isPattern());
        assertFalse(b.isPattern());

        // Thường khác nhau với hai object khác nhau, nhưng
        // không coi identity hash là bảo đảm uniqueness tuyệt đối.
    }
}
\`\`\`

### 14.2. Integration test qua MBeanServer

Một test cần đăng ký hai MBean bằng exporter, rồi hỏi MBeanServer:

\`\`\`java
Set<ObjectName> names =
    server.queryNames(new ObjectName("*:*"), null);
\`\`\`

Từ kết quả, lọc theo domain/key thực tế do strategy tạo; xác minh có hai registrations cho hai managed objects. Test cần quản lý context lifecycle và unregister sau khi kết thúc.

### 14.3. Test sau context refresh

Nếu context tạo lại bean, ObjectName mới có thể đổi. Hãy test **hợp đồng client thực sự yêu cầu**: nếu client phải dùng query động, test query; nếu client phải dùng tên ổn định, identity naming không phù hợp và nên chuyển sang strategy theo stable resource ID.

## 15. Một số lỗi và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Client không thấy ObjectName cố định | Identity name generated khác dự kiến | Query ObjectNames thực tế |
| Sau restart dashboard mất dữ liệu | ObjectName thay đổi | Đổi sang tên ổn định hoặc discovery động |
| \`InstanceAlreadyExistsException\` | Export cùng object nhiều lần, collision hoặc naming config sai | Kiểm tra exporter và ObjectName thực |
| Hai bean cùng class chỉ thấy một MBean | Registration policy bỏ qua conflict | Kiểm tra \`IGNORE_EXISTING\` và naming |
| Cấu hình naming strategy nhưng tên không đổi | Exporter dùng ObjectName tường minh hoặc bean được đăng ký qua đường khác | Kiểm tra mapping key, exporter và naming strategy |
| Tên thay đổi khi bật Spring AOP | Proxy/object được đặt tên khác | Kiểm tra instance thực export |
| JConsole thấy MBean nhưng attribute không đúng | Lỗi assembler/metadata, không phải naming | Đọc \`MBeanInfo\` |
| MBean cũ còn sau context close | Unregister/lifecycle không đúng | Theo dõi registrations theo context |

Đừng kết luận \`IdentityNamingStrategy\` “hỏng” chỉ vì ObjectName không trùng kỳ vọng hard-coded. Bản chất của nó là dựa trên identity runtime.

## 16. Những lưu ý vận hành

### 16.1. Discovery động

Nếu dùng identity-generated names, consumer nên:

1. Kết nối đến đúng MBeanServer.
2. Query theo domain/type pattern đủ hẹp.
3. Đọc \`MBeanInfo\` và attributes để xác định managed resource.
4. Dùng \`ObjectName\` đã phát hiện để thao tác.
5. Phát hiện MBean unregistration/re-registration để làm mới cache tên.

Không nên lưu một generated ObjectName như cấu hình vĩnh viễn mà không có cơ chế discovery.

### 16.2. Quyền truy cập và bảo mật

ObjectName có thể được nhìn thấy trong JConsole hoặc logs. Không gắn dữ liệu cá nhân/secret vào name. Identity naming không tạo security boundary giữa các MBean; access control phải đặt ở management agent, connector hoặc policy ứng dụng.

### 16.3. Monitoring cardinality

Nếu tạo MBean theo hàng nghìn object tạm thời, số lượng ObjectNames và chi phí query/monitoring có thể tăng nhanh. Không dùng identity naming để export tùy tiện từng request/session. Chỉ export resource quản trị có giá trị vận hành và vòng đời kiểm soát được.

### 16.4. Độ ổn định cho dashboard

Dashboard thường muốn theo dõi một **resource logic** qua nhiều lần restart. Nếu phải dùng identity naming, cần lớp discovery/mapping từ resource ID sang ObjectName hiện hành. Nếu không, naming theo metadata hoặc key ổn định thường dễ bảo trì hơn.

## 17. Bài tập thực hành

### Bài tập A — So sánh object identity

Tạo hai object cùng class có \`equals()\` trả \`true\`, nhưng \`==\` trả \`false\`. Dùng \`IdentityNamingStrategy\` lấy ObjectName. Ghi lại tên và so sánh với \`System.identityHashCode\`. Giải thích vì sao equality không đủ để phân biệt instance.

### Bài tập B — Chạy lại JVM

Chạy demo identity naming hai lần. Quan sát ObjectNames. Đưa ra nhận xét về khả năng giữ tên cố định và vì sao dashboard không nên hard-code tên runtime.

### Bài tập C — So sánh strategies

Dùng cùng hai bean, lần lượt cấu hình \`IdentityNamingStrategy\`, \`KeyNamingStrategy\` và tên từ \`@ManagedResource\`/metadata. Quan sát tên trong MBeanServer. Chọn strategy phù hợp cho một hệ thống monitoring queue lâu dài.

### Bài tập D — Hai ApplicationContext

Tạo context A và B có cùng class \`WorkerStatus\`. Export vào cùng \`MBeanServer\` với identity naming. Xác định ObjectNames, đóng context A rồi kiểm tra chỉ registration của A được xóa. Xác minh context B vẫn hoạt động.

### Bài tập E — ResourceNamingStrategy

Dùng implementation custom trong mục 13, tạo hai managed objects có management names \`orders\` và \`returns\`. Kiểm tra tên ổn định qua các lần khởi tạo và lỗi rõ ràng nếu hai objects cố đăng ký cùng resource ID.

## 18. Câu hỏi tự kiểm tra

1. \`ObjectNamingStrategy\` khác \`MBeanInfoAssembler\` ở trách nhiệm nào?
2. Tại sao hai Spring beans khác nhau vẫn có thể gặp \`InstanceAlreadyExistsException\`?
3. Object identity khác \`equals()\` ra sao?
4. \`System.identityHashCode\` có phải định danh duy nhất toàn cục không?
5. Vì sao identity-generated ObjectName thường không thích hợp để hard-code trong dashboard?
6. Spring AOP proxy có thể ảnh hưởng identity naming như thế nào?
7. Nếu có nhiều ApplicationContext, tính duy nhất của ObjectName được xét ở đâu?
8. Khi nào \`KeyNamingStrategy\` hoặc \`MetadataNamingStrategy\` phù hợp hơn?
9. Client cần làm gì để theo dõi MBean có tên thay đổi sau restart?
10. Identity naming có tự tạo quyền truy cập hoặc remote JMX endpoint không?

## 19. Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — \`IdentityNamingStrategy\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/naming/IdentityNamingStrategy.html
- Spring Framework API — \`ObjectNamingStrategy\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/naming/ObjectNamingStrategy.html
- Spring Framework API — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Java SE 21 API — \`ObjectName\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html

**Ghi nhớ:** \`IdentityNamingStrategy\` là công cụ đặt tên theo identity của managed object để phân biệt instance trong JMX. Nó không đại diện cho resource ID bền vững. Khi chọn strategy, hãy bắt đầu từ yêu cầu của JMX consumer: cần nhận diện một Java object đang sống, hay cần theo dõi cùng resource logic qua nhiều lần triển khai?
