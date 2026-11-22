# ObjectName trong Spring JMX: Chiến lược đặt tên khi triển khai nhiều instance

## 1. Vấn đề cần giải quyết

Trong ứng dụng Java nhỏ, một MBean có thể dùng tên tĩnh như:

\`\`\`text
com.example.app:type=CacheManager
\`\`\`

Tên đó có vẻ đủ khi chỉ có một MBean trong một JVM. Nhưng hệ thống thực tế có thể có nhiều \`ApplicationContext\`, nhiều cache, nhiều datasource, nhiều tenant hoặc nhiều instance của cùng một thành phần. Khi ấy, một tên tĩnh thường không đủ để xác định **đối tượng nào đang được quản trị**.

JMX định danh MBean bằng \`javax.management.ObjectName\`. Một \`ObjectName\` gồm **domain** và tập **key properties**:

\`\`\`text
com.example.platform:type=CacheManager,service=orders,cache=product
└────────domain────────┘ └─────── key properties ────────┘
\`\`\`

Với \`MBeanServer\` cụ thể, hai MBean có cùng \`ObjectName\` không thể được đăng ký cùng lúc. Trong một JVM, trùng tên có thể gây \`InstanceAlreadyExistsException\`. Tuy nhiên, các JVM **khác nhau** có \`MBeanServer\` riêng nên có thể đăng ký cùng \`ObjectName\` mà không xung đột trực tiếp. Điều này dẫn đến hai nhu cầu phân biệt:

1. **Duy nhất trong một MBeanServer** để đăng ký thành công và không nhầm bean.
2. **Nhận diện xuyên instance/cluster** để dashboard, monitoring và script biết MBean thuộc process hoặc node nào.

ObjectName không tự cung cấp định danh toàn cục xuyên mọi JVM. Định danh ngoài JVM thường cần thêm endpoint/target, process, pod hoặc instance metadata.

## 2. Mô hình tư duy: tên ổn định và phạm vi duy nhất

Một chiến lược đặt tên tốt trả lời bốn câu hỏi:

- **Đây là loại thành phần nào?** Ví dụ \`type=CacheManager\`, \`type=WorkerPool\`.
- **Nó phục vụ nghiệp vụ nào?** Ví dụ \`service=orders\`, \`service=billing\`.
- **Trong cùng phạm vi, nó là instance nào?** Ví dụ \`name=primary\`, \`pool=async\`, \`tenant=acme\`.
- **Client cần tìm nó bằng mẫu nào?** Ví dụ truy vấn tất cả worker pools của service \`orders\`.

Một cách phân lớp phổ biến:

\`\`\`text
domain             = com.example.platform
type               = WorkerPool
service            = orders
name               = notification
instance           = 7f3a2
\`\`\`

Tạo thành:

\`\`\`text
com.example.platform:type=WorkerPool,service=orders,name=notification,instance=7f3a2
\`\`\`

Không phải lúc nào cũng cần \`instance\` bên trong ObjectName. Nếu mỗi JVM chỉ có một \`WorkerPool\` cho \`service=orders,name=notification\`, tên ổn định:

\`\`\`text
com.example.platform:type=WorkerPool,service=orders,name=notification
\`\`\`

đã đủ duy nhất trong JVM và dễ tái sử dụng trên mọi replica. Hệ thống giám sát sẽ phân biệt replica bằng nhãn mục tiêu JMX endpoint, node hoặc \`instance\` ở tầng thu thập metric.

**Nguyên tắc:** chọn bộ key tối thiểu đủ duy nhất trong MBeanServer, rồi thêm chiều định danh chỉ khi cần phục vụ quản trị hoặc khi thực sự có nhiều MBean cùng nhóm trong một JVM.

## 3. Quy tắc cấu trúc ObjectName

Cấu trúc chuẩn:

\`\`\`text
<domain>:<key1>=<value1>,<key2>=<value2>,...
\`\`\`

Ví dụ:

\`\`\`text
com.example.app:type=DataSource,name=primary,service=catalog
com.example.app:type=DataSource,name=reporting,service=catalog
com.example.app:type=Executor,name=imports,service=catalog
\`\`\`

Domain nên có namespace do tổ chức kiểm soát, chẳng hạn tên package đảo ngược. Key property nên nhất quán chữ hoa/thường và ngữ nghĩa qua các module.

Đề xuất hợp đồng đặt tên:

| Thành phần | Ý nghĩa | Ví dụ | Gợi ý |
|---|---|---|---|
| \`domain\` | Namespace của ứng dụng/tổ chức | \`com.example.platform\` | Ổn định, tránh domain dùng chung quá rộng |
| \`type\` | Loại tài nguyên MBean | \`CacheManager\` | Bắt buộc theo convention của dự án |
| \`service\` | Dịch vụ sở hữu | \`orders\` | Hữu ích trong ứng dụng đa module |
| \`name\` | Tên logic trong loại tài nguyên | \`primary\` | Phân biệt tài nguyên cùng type |
| \`tenant\` | Tenant nếu có nhiều MBean theo tenant | \`customer-a\` | Chỉ thêm khi thực sự export theo tenant |
| \`instance\` | Định danh runtime khi cần | \`node-03\` | Chỉ thêm nếu cần trong phạm vi JMX/quản trị |
| \`role\` | Vai trò ổn định | \`writer\` | Hợp với topology có vai trò rõ ràng |

Các key này là convention do đội phát triển chọn, không phải tập khóa bắt buộc của JMX. JMX chỉ yêu cầu \`ObjectName\` hợp lệ và các key property không bị lặp trong cùng tên.

ObjectName không xem thứ tự key property là bản sắc định danh. Hai chuỗi:

\`\`\`text
com.example.app:type=Cache,name=products
com.example.app:name=products,type=Cache
\`\`\`

biểu diễn cùng một \`ObjectName\`. Vì vậy, hãy dựa vào \`ObjectName.equals\` hoặc cấu trúc \`ObjectName\`, đừng so khớp bằng string thô với thứ tự property cố định.

## 4. Các kiểu triển khai nhiều instance

### 4.1. Nhiều JVM replica, mỗi JVM một MBean cùng vai trò

Ví dụ ba process \`orders\` chạy trên ba pod. Mỗi JVM đăng ký:

\`\`\`text
com.example.app:type=WorkerPool,service=orders,name=default
\`\`\`

Điều này hợp lệ vì mỗi MBeanServer thuộc JVM riêng. Monitoring nên biểu diễn:

\`\`\`text
target=orders-pod-a + ObjectName=...name=default
target=orders-pod-b + ObjectName=...name=default
target=orders-pod-c + ObjectName=...name=default
\`\`\`

Với mô hình này, dùng tên ổn định giúp bảng điều khiển có chung truy vấn trên mọi replica. Không nhất thiết phải chèn UUID pod vào ObjectName. Pod có thể thay đổi thường xuyên, trong khi tên logic \`default\` giữ nguyên.

### 4.2. Một JVM chứa nhiều ApplicationContext

Trong một JVM, nhiều context có thể dùng chung platform \`MBeanServer\`. Nếu mỗi context export cùng:

\`\`\`text
com.example.app:type=WorkerPool,name=default
\`\`\`

thì có nguy cơ trùng \`ObjectName\`. Có thể bổ sung định danh context:

\`\`\`text
com.example.app:type=WorkerPool,context=admin,name=default
com.example.app:type=WorkerPool,context=public,name=default
\`\`\`

Giá trị \`context\` phải ổn định và do ứng dụng kiểm soát, không lấy ngẫu nhiên mỗi lần export nếu không có nhu cầu. Nếu chọn dùng \`contextId\`, hãy xác định giá trị đó có ổn định qua restart hay không.

### 4.3. Một JVM chứa nhiều bean cùng loại

Một service có hai datasource:

\`\`\`text
com.example.app:type=DataSource,service=orders,name=writer
com.example.app:type=DataSource,service=orders,name=reader
\`\`\`

Một service có ba consumer cùng loại:

\`\`\`text
com.example.app:type=Consumer,service=orders,name=payments
com.example.app:type=Consumer,service=orders,name=notifications
com.example.app:type=Consumer,service=orders,name=analytics
\`\`\`

Ở đây \`name\` là **định danh logic** chứ không phải \`toString()\` hay địa chỉ bộ nhớ của object.

### 4.4. Nhiều tenant hoặc đối tượng động

Nếu mỗi tenant có MBean riêng:

\`\`\`text
com.example.app:type=Quota,service=orders,tenant=tenant-a
com.example.app:type=Quota,service=orders,tenant=tenant-b
\`\`\`

Cần kiểm soát số lượng MBean và vòng đời register/unregister khi tenant được thêm hoặc xóa. Không nên công bố một MBean cho mỗi request/session có vòng đời ngắn và số lượng không giới hạn; JMX phù hợp hơn với thành phần quản trị ổn định.

### 4.5. Nhiều instance cùng một loại trong cùng JVM

Khi thực sự có hai instance runtime độc lập, thêm key \`instance\`:

\`\`\`text
com.example.app:type=WorkerPool,service=orders,name=mailer,instance=worker-a
com.example.app:type=WorkerPool,service=orders,name=mailer,instance=worker-b
\`\`\`

Định danh instance nên có nguồn rõ ràng: cấu hình orchestration, tên node, stable bean ID hoặc ID được cấp từ registry. Tránh dùng timestamp hoặc random UUID như lựa chọn mặc định vì script, dashboard và người vận hành sẽ khó tìm lại cùng tài nguyên qua restart.

## 5. Xây dựng ObjectName bằng Java an toàn

API \`ObjectName\` có nhiều constructor. Khi tất cả property có dạng ký tự đơn giản, có thể khai báo tĩnh:

\`\`\`java
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.app:type=WorkerPool,service=orders,name=mailer"
);
\`\`\`

Nhưng khi một property lấy từ cấu hình hoặc input, đừng nối string tùy tiện. Các ký tự như dấu phẩy, dấu bằng, dấu ngoặc kép, dấu hai chấm trong phần domain hoặc ký tự pattern có thể làm tên sai cú pháp hay thay đổi ý nghĩa.

Dùng constructor nhận tập key/value để xây dựng có cấu trúc; với value động, cần xử lý quote đúng để không đưa ký tự có ý nghĩa đặc biệt vào tên:

\`\`\`java
import java.util.Hashtable;
import javax.management.ObjectName;

static ObjectName workerName(
        String service,
        String logicalName,
        String instanceId) throws Exception {

    Hashtable<String, String> properties = new Hashtable<>();
    properties.put("type", "WorkerPool");
    properties.put("service", ObjectName.quote(service));
    properties.put("name", ObjectName.quote(logicalName));
    properties.put("instance", ObjectName.quote(instanceId));

    return new ObjectName(
        "com.example.app",
        properties
    );
}
\`\`\`

\`ObjectName.quote(...)\` tạo dạng value được đặt trong dấu ngoặc kép với escape JMX thích hợp. Ví dụ \`ObjectName.quote("blue,green")\` cho phép lưu giá trị có dấu phẩy mà không biến nó thành dấu phân cách key property. **Tuy nhiên, không nên quote mọi giá trị một cách máy móc khi convention của nhóm chỉ cho phép token đơn giản**, bởi quoted value và unquoted value có thể có biểu diễn khác nhau và ảnh hưởng việc client tạo/so khớp ObjectName. Cần thống nhất quy tắc và test với tên thực tế.

Một chính sách thường dễ vận hành hơn là chuẩn hóa các key định danh như \`service\`, \`name\` và \`instance\` theo tập ký tự cho phép:

\`\`\`text
[a-z0-9][a-z0-9._-]*
\`\`\`

Sau khi validation với regular expression, các giá trị này có thể đưa vào constructor \`ObjectName(domain, properties)\` dưới dạng chuỗi thông thường. Đừng ngầm biến những giá trị khác nhau thành cùng một slug vì sẽ tạo collision. Khi cần hỗ trợ tên người dùng chứa Unicode hoặc dấu phẩy, dùng \`ObjectName.quote\` theo hợp đồng rõ ràng.

Ví dụ xác thực trước khi tạo:

\`\`\`java
import java.util.Hashtable;
import java.util.regex.Pattern;
import javax.management.ObjectName;

public final class JmxNames {
    private static final Pattern TOKEN =
        Pattern.compile("[a-z0-9][a-z0-9._-]*");

    private JmxNames() {}

    private static String token(String value, String key) {
        if (value == null || !TOKEN.matcher(value).matches()) {
            throw new IllegalArgumentException(
                "Invalid JMX key value for " + key + ": " + value
            );
        }
        return value;
    }

    public static ObjectName worker(
            String service,
            String name,
            String instance) throws Exception {
        Hashtable<String, String> props = new Hashtable<>();
        props.put("type", "WorkerPool");
        props.put("service", token(service, "service"));
        props.put("name", token(name, "name"));
        props.put("instance", token(instance, "instance"));

        return new ObjectName("com.example.app", props);
    }
}
\`\`\`

Trong production, nên tránh đưa raw input nhạy cảm vào thông báo exception/log. Thông điệp trên dành cho dữ liệu identifier không nhạy cảm của ví dụ.

## 6. Spring Framework: chiến lược đặt tên khi export MBean

Spring JMX cung cấp \`MBeanExporter\` để export bean vào \`MBeanServer\`. Khi sử dụng \`@ManagedResource(objectName=...)\`, tên có thể được định nghĩa trực tiếp:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.app:type=WorkerPool,service=orders,name=mailer"
)
public class MailerControl {
    @ManagedAttribute
    public int getQueueSize() {
        return 0;
    }
}
\`\`\`

Tên annotation ở đây là tên tĩnh. Nó phù hợp nếu bean đó duy nhất trong \`MBeanServer\` của JVM. Nếu một class được tạo thành nhiều bean và cùng dùng một \`objectName\` tĩnh, cần chiến lược khác để tránh xung đột.

Có hai cách phổ biến:

**A. Đặt ObjectName rõ ràng theo từng bean khi cấu hình exporter.**

\`\`\`java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
class JmxExportConfiguration {
    @Bean
    MBeanExporter exporter(
            MailerControl primaryControl,
            MailerControl secondaryControl) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
            "com.example.app:type=MailerControl,name=primary",
            primaryControl,
            "com.example.app:type=MailerControl,name=secondary",
            secondaryControl
        ));
        return exporter;
    }
}
\`\`\`

Đây là ví dụ minh họa mapping ObjectName cho từng bean. Trong ứng dụng thực tế, nếu sử dụng Spring Boot auto-configuration, annotation export hoặc exporter khác, cần bảo đảm cùng bean không bị export hai lần và tên thực tế đúng với thiết kế.

**B. Dùng NamingStrategy để tạo ObjectName nhất quán.**

Spring có \`org.springframework.jmx.export.naming.ObjectNamingStrategy\`, được \`MBeanExporter\` sử dụng để chọn tên export. Một implementation có thể lấy bean key và metadata cấu hình của từng instance để tạo \`ObjectName\` theo convention.

\`\`\`java
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;
import org.springframework.jmx.export.naming.ObjectNamingStrategy;

public class StableObjectNamingStrategy
        implements ObjectNamingStrategy {

    @Override
    public ObjectName getObjectName(
            Object managedBean,
            String beanKey) throws MalformedObjectNameException {

        String safeName = beanKey.replaceAll("[^a-zA-Z0-9._-]", "_");

        return new ObjectName(
            "com.example.app:type=ManagedComponent,name=" + safeName
        );
    }
}
\`\`\`

Ví dụ này giúp hình dung hook naming. Với code dùng thật, cần xác thực collision và quy tắc normalize: hai bean key khác nhau có thể bị biến thành cùng một \`safeName\`. Có thể thay bằng registry tên ổn định hoặc ID duy nhất có định nghĩa rõ. Lưu ý một naming strategy do ứng dụng viết cần tương thích với export mode và cấu hình exporter đang dùng.

### Điều cần tránh khi Spring export nhiều bean

- Đừng tự động thêm \`System.identityHashCode(bean)\` hoặc \`bean.toString()\` vào tên nếu mục tiêu là tên ổn định.
- Đừng trông chờ tên bean Spring mặc định luôn có ý nghĩa nghiệp vụ; những tên do container sinh có thể thay đổi khi refactor.
- Đừng đổi ObjectName chỉ để che lỗi đăng ký trùng: trước tiên xác định có hai MBean đúng nghĩa hay có double-registration từ cấu hình.
- Đừng dựa vào \`@ManagedResource\` như một bảo đảm duy nhất về uniqueness nếu nhiều đối tượng cùng class được export.
- Khi export cùng một object dưới nhiều tên khác nhau, cần cân nhắc liệu đó là chủ ý hay làm monitoring đếm trùng.

## 7. Phát hiện và xử lý trùng tên

Khi hai MBean cố đăng ký cùng một ObjectName trong một server, một lần đăng ký có thể thất bại với \`InstanceAlreadyExistsException\`. Ví dụ:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName target = new ObjectName(
    "com.example.app:type=WorkerPool,name=default"
);

server.registerMBean(firstMBean, target);
server.registerMBean(secondMBean, target);
// Lần đăng ký thứ hai sẽ lỗi nếu tên vẫn đang được dùng.
\`\`\`

Trong Spring, exporter có các lựa chọn xử lý xung đột registration tùy phiên bản/cấu hình, nhưng cần quyết định rõ ràng ý nghĩa nghiệp vụ trước khi dùng cơ chế replace/ignore. Nếu \`secondMBean\` phải là một tài nguyên độc lập, giải pháp đúng là cấp một ObjectName khác; bỏ qua lỗi hoặc ghi đè có thể làm biến mất MBean mong muốn.

Có thể kiểm tra đăng ký:

\`\`\`java
if (server.isRegistered(target)) {
    System.out.println("Already registered: " + target);
}
\`\`\`

Tuy nhiên \`isRegistered\` rồi \`registerMBean\` không phải thao tác nguyên tử. Một thread khác vẫn có thể đăng ký cùng tên giữa hai lệnh. Hãy xử lý exception từ \`registerMBean\` như nguồn sự thật cuối cùng.

### Bảng quyết định collision

| Bối cảnh | Biểu hiện | Hướng xử lý |
|---|---|---|
| Hai replica ở hai JVM | Cùng ObjectName nhưng server khác | Hợp lệ; phân biệt bằng endpoint/target |
| Hai bean cùng loại trong một JVM | Cùng domain, type, name | Bổ sung tên logic khác nhau |
| Hai ApplicationContext dùng chung MBeanServer | Cùng tên export | Thêm context key hoặc dùng namespace tách biệt |
| Spring exporter đăng ký bean hai lần | Một ObjectName bị đăng ký hai nguồn | Bỏ đăng ký trùng/điều chỉnh cấu hình export |
| Bean động được tạo rồi hủy | ObjectName cũ vẫn đăng ký | Quản lý unregister theo vòng đời |
| Instance ID ngẫu nhiên mỗi restart | Dashboard mất khả năng tìm tên cũ | Dùng tên logic ổn định và metadata runtime riêng |

## 8. Truy vấn nhiều MBean bằng ObjectName pattern

Một trong những lợi ích lớn nhất của naming convention nhất quán là client có thể tìm nhóm MBean bằng pattern thay vì hardcode từng tên.

Ví dụ truy vấn tất cả \`WorkerPool\` thuộc service \`orders\`:

\`\`\`java
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

ObjectName pattern = new ObjectName(
    "com.example.app:type=WorkerPool,service=orders,*"
);

Set<ObjectName> names = server.queryNames(pattern, null);

for (ObjectName candidate : names) {
    System.out.println(candidate.getCanonicalName());
}
\`\`\`

Dấu \`*\` trong property list pattern cho phép MBean có thêm các key properties khác, chẳng hạn \`name\` hoặc \`instance\`.

Một số pattern:

\`\`\`text
com.example.app:type=WorkerPool,* 
com.example.app:type=WorkerPool,service=orders,*
com.example.app:type=DataSource,service=billing,*
com.example.app:*
\`\`\`

Pattern rộng như \`com.example.app:*\` giúp khám phá nhưng có thể trả nhiều MBean không liên quan. Script automation nên giới hạn domain/type/service để tránh vô tình gọi operation lên nhiều đối tượng.

Đối với \`ObjectName\`, ký tự \`*\` và \`?\` có ý nghĩa pattern ở ngữ cảnh thích hợp. Khi một giá trị business thực sự chứa ký tự pattern, phải dùng encoding/quoting và hiểu semantics của ObjectName query. Tránh lấy raw user input rồi ghép trực tiếp vào pattern.

### Truy vấn theo canonical name

\`\`\`java
for (ObjectName candidate : names) {
    System.out.println(candidate.getDomain());
    System.out.println(candidate.getKeyProperty("type"));
    System.out.println(candidate.getKeyProperty("service"));
    System.out.println(candidate.getCanonicalName());
}
\`\`\`

\`getCanonicalName()\` cung cấp biểu diễn chuẩn về thứ tự key properties, hữu ích để log hoặc so sánh text. Dù vậy, **lý tưởng vẫn xử lý ObjectName như đối tượng có cấu trúc**, nhất là khi xây dựng pattern hoặc trích thuộc tính.

## 9. Thiết kế định danh cho Kubernetes, container và autoscaling

Với ứng dụng container, pod/instance có vòng đời ngắn; tên vật lý không đồng nghĩa tên logic. Có hai lựa chọn:

**Lựa chọn 1 — ObjectName logic ổn định, instance nằm ở target metadata.**

\`\`\`text
ObjectName = com.example.app:type=CacheManager,service=orders,name=products
target.labels = {cluster=prod-a, namespace=shop, pod=orders-7d9f...}
\`\`\`

Ưu điểm: mọi replica expose cùng cấu trúc JMX; dashboard dùng một query chung. Đây thường là hướng mặc định tốt khi mỗi JVM một context/vai trò tương ứng.

**Lựa chọn 2 — Đưa instanceId vào ObjectName khi có yêu cầu cụ thể.**

\`\`\`text
com.example.app:type=CacheManager,service=orders,name=products,instance=orders-3
\`\`\`

Ưu điểm: khi dữ liệu từ nhiều nguồn được gom về một không gian truy vấn hoặc khi một JVM chứa nhiều instance cùng tên, vẫn có thể phân biệt trong ObjectName. Nhược điểm: tên có thể thay đổi theo deployment; query cần dùng wildcard và dashboard không nên hardcode instance ID.

Đừng nhầm **duy nhất trong JVM** với **duy nhất toàn cluster**. Phần \`ObjectName\` không bao gồm định danh MBeanServer/endpoint. Hai MBean nằm ở hai JVM là hai thực thể khác nhau dù cùng ObjectName.

Trong hệ thống distributed, nên giữ các metadata môi trường như \`cluster\`, \`region\`, \`namespace\` ở lớp thu thập metric/observability nếu mục đích chỉ để lọc biểu đồ. Thêm quá nhiều key vào ObjectName khiến API quản trị giòn hơn khi tổ chức triển khai thay đổi.

## 10. Nhiều instance và bài toán restart

Giả sử một worker MBean có:

\`\`\`text
com.example.app:type=WorkerPool,name=shipping,instance=2026-11-11T08:00:00Z
\`\`\`

Khi restart, timestamp đổi và mọi script lưu tên cũ sẽ không còn tìm được MBean. Nếu mục tiêu của hệ thống là tìm worker \`shipping\`, dùng:

\`\`\`text
com.example.app:type=WorkerPool,service=orders,name=shipping
\`\`\`

rồi expose thông tin run hiện tại dưới dạng attribute:

\`\`\`text
StartTime
ProcessId
BuildVersion
InstanceId
\`\`\`

Các runtime metadata có thể thay đổi mà ObjectName logic vẫn ổn định. Với nhiều đối tượng \`shipping\` trong **cùng JVM**, tên logic phải thêm một chiều phân biệt (chẳng hạn \`lane\`, \`shard\` hoặc \`instance\`), đồng thời tránh tạo key không cần thiết chỉ để đưa thông tin lên dashboard.

Để phát hiện đã restart, client có thể đọc \`StartTime\` hoặc thuộc tính riêng; tên giống nhau không chứng minh đây là cùng process vật lý qua thời gian.

## 11. Thiết kế naming contract có thể bảo trì

Đặt ra một hợp đồng cho toàn ứng dụng:

\`\`\`text
Domain: com.example.platform
Required keys: type,service,name
Optional keys: context,tenant,shard,instance
Case: key names lowerCamelCase hoặc lowercase (chọn một)
Values: stable token được validate, tránh dữ liệu nhạy cảm
Uniqueness: domain+property set duy nhất trong mỗi MBeanServer
Discovery: client query theo domain,type,service và property-list wildcard
Ownership: mỗi component có một nơi duy nhất quyết định ObjectName
\`\`\`

Sau đó có thể quy định:

- \`type\` ổn định theo nhóm tài nguyên, không đổi vì refactor package Java.
- \`service\` là ID service canonical, không phải display name tùy ý.
- \`name\` mô tả vai trò logic, ví dụ \`primary\`, \`writer\`, \`batch\`.
- \`shard\` chỉ được thêm nếu thực sự có nhiều shard cùng vai trò.
- Không đưa IP, port, PID, hostname hoặc timestamp vào tên nếu chúng chỉ là thông tin môi trường và không cần để phân biệt MBean cùng server.
- Đổi naming contract là thay đổi giao diện quản trị; script, dashboard, exporter JMX metrics và alert có thể phụ thuộc vào tên cũ.

Ví dụ kế hoạch đổi tên khi đã có monitoring:

\`\`\`text
Cũ: com.example.app:type=Cache,name=product
Mới: com.example.app:type=Cache,service=catalog,name=product
\`\`\`

Cần cập nhật query, dashboard và scripts theo tên mới. Nếu phải duy trì compatibility trong giai đoạn chuyển đổi, cân nhắc lớp mapping ở monitoring hoặc kế hoạch chuyển đổi rõ ràng; không tự đăng ký hai alias MBean vĩnh viễn nếu điều đó làm metrics bị đếm đôi.

## 12. Quản lý vòng đời MBean

Nhiều instance có thể được tạo động khi cấu hình thay đổi hoặc khi tenant thêm/bớt. Đặt tên đúng chỉ là một phần; cần quản lý vòng đời:

1. Khi tạo instance, tính \`ObjectName\` duy nhất từ định danh bền vững của instance.
2. Register MBean sau khi đối tượng sẵn sàng quản trị.
3. Giữ mapping \`instanceId -> ObjectName\` để tìm lại.
4. Khi instance ngừng hoạt động, unregister đúng MBean do component sở hữu.
5. Xử lý trường hợp MBean đã bị unregister hoặc context đang shutdown.

Ví dụ minh họa với Java API:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.ObjectName;

void register(MBeanServer server, ObjectName name, Object mbean)
        throws Exception {
    server.registerMBean(mbean, name);
}

void unregister(MBeanServer server, ObjectName name)
        throws Exception {
    if (server.isRegistered(name)) {
        server.unregisterMBean(name);
    }
}
\`\`\`

Đoạn ví dụ không giải quyết race khi có nhiều owner cùng đăng ký. Trong production, cần quản lý ownership để không unregister nhầm MBean do component khác tạo, và xử lý \`InstanceNotFoundException\` nếu bị race.

Với Spring exporter, ưu tiên để lifecycle của \`ApplicationContext\` quản lý registration/unregistration theo cơ chế exporter khi phù hợp. Khi tự quản lý MBean động, hãy xác định rõ bên nào sở hữu lifecycle.

## 13. Bảo mật và vận hành

ObjectName được dùng trong logs, dashboards và công cụ quản trị. Không đưa dữ liệu nhạy cảm vào key property, chẳng hạn access token, email khách hàng hoặc bí mật nội bộ. Nếu phải expose một tenant ID, bảo đảm ID không mang thông tin cá nhân và số lượng MBean được giới hạn hợp lý.

Lưu ý:

- JMX remote cần giới hạn network, authentication, authorization và transport protection phù hợp.
- Đừng để script query pattern quá rộng rồi invoke operation có tác dụng phụ lên mọi MBean tìm thấy.
- Khi thao tác thay đổi state, log ObjectName, operation và kết quả đủ để truy vết nhưng loại trừ secrets.
- Quyền đối với MBean có thể khác giữa môi trường; ObjectName không thay thế cơ chế phân quyền.

## 14. Bài thực hành thiết kế tên

### Bài 1: Hai DataSource trong cùng service

Có một JVM chứa datasource ghi và đọc của \`orders\`. Hãy đặt hai ObjectName.

Một lựa chọn:

\`\`\`text
com.example.platform:type=DataSource,service=orders,name=writer
com.example.platform:type=DataSource,service=orders,name=reader
\`\`\`

Hai tên duy nhất trong JVM vì khác property \`name\`.

### Bài 2: Ba replica chạy trên ba pod

Mỗi replica có một \`CacheManager\` cùng role \`product\`. Có nhất thiết thêm pod ID vào ObjectName?

Không. Có thể dùng cùng tên:

\`\`\`text
com.example.platform:type=CacheManager,service=catalog,name=product
\`\`\`

trong mỗi JVM, rồi phân biệt replica bằng JMX target metadata.

### Bài 3: Một JVM chứa hai context admin và public

Mỗi context export một \`WorkerPool\` tên \`default\`. Cần bổ sung key nào?

\`\`\`text
com.example.platform:type=WorkerPool,service=orders,name=default,context=admin
com.example.platform:type=WorkerPool,service=orders,name=default,context=public
\`\`\`

### Bài 4: Query tất cả WorkerPool của orders

\`\`\`java
ObjectName pattern = new ObjectName(
    "com.example.platform:type=WorkerPool,service=orders,*"
);

for (ObjectName value : server.queryNames(pattern, null)) {
    System.out.println(value);
}
\`\`\`

### Bài 5: Kiểm tra tính duy nhất qua thứ tự key

Hai tên sau có khác nhau không?

\`\`\`text
com.example.platform:type=Cache,name=product
com.example.platform:name=product,type=Cache
\`\`\`

Không. Thứ tự key properties không biến chúng thành hai ObjectName độc lập.

### Bài 6: Phát hiện lỗi do ID động

Một hệ thống chèn timestamp mới vào \`instance\` mỗi lần restart. Sau một tuần, script query exact tên cũ thất bại. Nêu hai hướng sửa.

- Dùng ObjectName logic ổn định nếu mỗi JVM chỉ có một đối tượng cần quản trị.
- Nếu cần instance key, dùng ID quản lý ổn định hoặc query bằng pattern và lấy runtime instance metadata để xác định đối tượng hiện tại.

## 15. Ghi nhớ

**Một ObjectName là định danh duy nhất trong phạm vi một MBeanServer**, không phải định danh toàn cầu của mọi JVM. Đối với nhiều replica, giữ tên logic ổn định và dùng endpoint/target labels để phân biệt nguồn. Đối với nhiều MBean trong cùng JVM, thêm các key có ý nghĩa như \`name\`, \`context\`, \`shard\` hoặc \`instance\` để tránh collision.

Một chiến lược đặt tên tốt phải đạt đồng thời ba mục tiêu: **đăng ký không trùng**, **truy vấn theo pattern dễ**, và **ổn định trước restart/refactor**. Hãy coi schema ObjectName là một phần giao diện vận hành cần versioning và duy trì như các API khác.