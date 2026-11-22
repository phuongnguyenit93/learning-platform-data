# ObjectName cụ thể và mẫu ObjectName có wildcard trong JMX

## 1. Mục tiêu và bối cảnh

Trong Java Management Extensions (JMX), mỗi MBean được đăng ký vào một \`MBeanServer\` bằng một **\`ObjectName\`**. Một ObjectName chứa *domain* và tập các cặp *key property*, ví dụ:

\`\`\`text
com.example.orders:type=Queue,name=Checkout
\`\`\`

Khi quản trị ứng dụng có nhiều MBean, cần phân biệt hai cách dùng:

- **ObjectName cụ thể (concrete ObjectName):** định danh chính xác một MBean để đăng ký, đọc thuộc tính hoặc gọi operation.
- **Mẫu ObjectName (ObjectName pattern):** biểu thức chứa wildcard hoặc dấu hiệu khớp một tập key properties, dùng để truy vấn danh sách MBean.

Bài học giúp bạn thiết kế tên ổn định, hiểu phép khớp mẫu và áp dụng đúng với JMX thuần Java cũng như Spring Framework JMX.

Sau bài này, bạn có thể:

1. Phân tích domain và key properties của ObjectName.
2. Tạo ObjectName cụ thể hợp lệ bằng Java API.
3. Phân biệt wildcard trong domain, giá trị property và property-list pattern \`,*\`.
4. Dùng \`MBeanServer.queryNames\` để tìm MBean theo tên và mẫu.
5. Giải thích hành vi khớp của các pattern thường gặp, bao gồm trường hợp dễ nhầm.
6. Thiết kế quy ước ObjectName dễ quản trị và tránh lỗi bảo mật, thay đổi tên hoặc trùng đăng ký.

## 2. Cấu trúc ObjectName

Cú pháp khái quát:

\`\`\`text
<domain>:<key1>=<value1>,<key2>=<value2>,...
\`\`\`

Ví dụ:

\`\`\`text
com.example.orders:type=Queue,name=Checkout,region=ap-southeast-1
\`\`\`

| Thành phần | Giá trị ví dụ | Vai trò |
|---|---|---|
| Domain | \`com.example.orders\` | Nhóm logic của các MBean |
| Key \`type\` | \`Queue\` | Phân loại resource |
| Key \`name\` | \`Checkout\` | Xác định instance |
| Key \`region\` | \`ap-southeast-1\` | Phân tách instance theo vùng |
| ObjectName đầy đủ | Toàn bộ chuỗi | Định danh duy nhất trong một MBeanServer |

**Điều quan trọng:** danh sách key properties không mang ý nghĩa thứ tự đối với danh tính. Hai ObjectName có cùng domain và cùng tập key/value vẫn bằng nhau dù thứ tự cặp thuộc tính khác nhau.

\`\`\`java
import javax.management.ObjectName;

ObjectName first = new ObjectName(
    "com.example.orders:type=Queue,name=Checkout"
);
ObjectName second = new ObjectName(
    "com.example.orders:name=Checkout,type=Queue"
);

System.out.println(first.equals(second)); // true
\`\`\`

ObjectName có thể được tạo từ chuỗi hoặc các constructor nhận domain cùng key/value properties. Dùng API tạo tên thay vì tự nối các đoạn lấy từ dữ liệu không tin cậy.

### 2.1. Quy tắc ký tự và quoting

Một ObjectName sử dụng các ký tự đặc biệt để phân tách cú pháp. Nếu giá trị thực chứa dấu phẩy, dấu bằng, dấu hai chấm, dấu sao, dấu hỏi, dấu ngoặc kép hoặc ký tự xuống dòng, cần hiểu quy tắc quote/escape và validate phù hợp. \`ObjectName.quote(...)\` giúp biến một chuỗi thành giá trị property có dấu ngoặc kép theo cú pháp ObjectName.

\`\`\`java
String displayName = "Orders, Priority";
ObjectName quotedName = new ObjectName(
    "com.example:type=Queue,name=" + ObjectName.quote(displayName)
);
System.out.println(quotedName);
\`\`\`

**Phân biệt:** quoting để biểu diễn ký tự trong giá trị và wildcard matching là hai chủ đề liên quan nhưng không đồng nhất. Khi tạo một identifier cụ thể chứa các ký tự có thể mang ý nghĩa pattern, hãy luôn kiểm tra \`isPattern()\` để xác nhận mục tiêu của tên đó. Một ObjectName dùng cho \`registerMBean\` phải là tên cụ thể.

## 3. ObjectName cụ thể: định danh đúng một MBean

Ví dụ:

\`\`\`java
ObjectName exact = new ObjectName(
    "training.jmx:type=Cache,name=Products"
);

System.out.println(exact.isPattern()); // false
\`\`\`

\`ObjectName\` cụ thể có một domain và các key property xác định. Trên một \`MBeanServer\`, cùng một ObjectName không thể được dùng để đăng ký đồng thời hai MBean riêng biệt. Việc cố đăng ký trùng thường phát sinh \`InstanceAlreadyExistsException\`.

\`\`\`java
import javax.management.*;
import java.lang.management.ManagementFactory;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "training.jmx:type=Cache,name=Products"
);

// server.registerMBean(cacheMBean, name);
// Lần đăng ký thứ hai với cùng tên sẽ bị từ chối.
\`\`\`

Trong vận hành, tên cụ thể thích hợp để:

- Đọc một attribute: \`connection.getAttribute(exact, "Size")\`.
- Gọi operation: \`connection.invoke(exact, "clear", new Object[0], new String[0])\`.
- Xác minh đăng ký: \`connection.isRegistered(exact)\`.
- Hủy đăng ký: \`server.unregisterMBean(exact)\` với quyền và vòng đời phù hợp.

Một ObjectName không chỉ ra URL hay địa chỉ máy chủ JMX. Để xác định một MBean từ xa, client phải biết **kết nối đến MBeanServer nào** và **ObjectName của MBean trong server đó**.

## 4. ObjectName pattern và các cơ chế wildcard

Một mẫu ObjectName dùng cho các phép truy vấn như \`queryNames\`. Java API phân biệt:

1. **Domain pattern:** wildcard \`*\` hoặc \`?\` trong domain.
2. **Property value pattern:** wildcard trong *giá trị property* khi được biểu diễn theo quy tắc pattern của ObjectName.
3. **Property list pattern:** dấu \`,*\` cuối danh sách thuộc tính (hoặc dấu \`*\` ngay sau dấu hai chấm nếu không chỉ định thuộc tính nào), cho phép thêm key properties ngoài những key đã chỉ định.

\`*\` khớp chuỗi ký tự bất kỳ, gồm cả chuỗi rỗng; \`?\` khớp đúng một ký tự. Dấu \`,*\` ở cấp danh sách property có ngữ nghĩa khác với \`*\` trong giá trị.

### 4.1. Domain pattern

\`\`\`text
training.*:type=Cache,name=Products
training.?:type=Cache,name=Products
\`\`\`

- Mẫu thứ nhất có thể khớp \`training.east:type=Cache,name=Products\`.
- Mẫu thứ hai yêu cầu một ký tự sau \`training.\`, ví dụ \`training.a:type=Cache,name=Products\`.

Nếu key properties không có property-list wildcard, mẫu vẫn yêu cầu **tập key properties trùng chính xác**; domain wildcard chỉ nới phần domain.

### 4.2. Property value pattern

\`\`\`text
training.jmx:type=Cache,name=Prod*
training.jmx:type=Cache,name=Product?
\`\`\`

- \`name=Prod*\` có thể khớp \`Products\` và \`Production\`.
- \`name=Product?\` có thể khớp \`Products\` vì ký tự cuối là \`s\`, nhưng không khớp \`Product\` vì thiếu ký tự.

Khi dùng Java API, tạo đối tượng rồi kiểm tra:

\`\`\`java
ObjectName pattern = new ObjectName(
    "training.jmx:type=Cache,name=Prod*"
);

System.out.println(pattern.isPattern());              // true
System.out.println(pattern.isPropertyValuePattern()); // true
\`\`\`

### 4.3. Property list pattern

Đây là điểm rất dễ nhầm trong JMX:

\`\`\`text
training.jmx:type=Cache,*
\`\`\`

Mẫu trên chỉ yêu cầu có \`type=Cache\`; các property như \`name\`, \`region\`, \`tenant\` có thể tồn tại thêm.

Trong khi đó:

\`\`\`text
training.jmx:type=Cache
\`\`\`

không có \`,*\` nên chỉ khớp các ObjectName có **duy nhất** property \`type=Cache\`, không khớp tên có thêm \`name=Products\`.

Mẫu:

\`\`\`text
training.jmx:*
\`\`\`

khớp mọi tập key properties trong domain \`training.jmx\`. Mẫu:

\`\`\`text
*:*
\`\`\`

khớp mọi ObjectName đăng ký trên MBeanServer có thể truy cập, tùy quyền của client.

\`*:* \` là một truy vấn rất rộng; trên server lớn, hãy ưu tiên domain/type cụ thể để giảm chi phí truy vấn và dữ liệu trả về.

## 5. So sánh chính xác: các mẫu nào khớp tên nào?

Giả sử MBeanServer đã đăng ký:

\`\`\`text
A = shop.orders:type=Queue,name=Checkout
B = shop.orders:type=Queue,name=Checkout,region=vn
C = shop.orders:type=Queue,name=Returns
D = shop.orders:type=Cache,name=Checkout
E = shop.billing:type=Queue,name=Checkout
F = shop.orders:type=Queue
\`\`\`

| ObjectName dùng truy vấn | Kết quả khớp | Giải thích |
|---|---|---|
| \`shop.orders:type=Queue,name=Checkout\` | A | Tên cụ thể, tập key/value trùng chính xác |
| \`shop.orders:type=Queue,name=Checkout,*\` | A, B | Yêu cầu 2 key, cho phép thêm key |
| \`shop.orders:type=Queue,*\` | A, B, C, F | Bắt buộc type Queue, còn lại tùy ý |
| \`shop.orders:type=Queue\` | F | Không có property-list wildcard |
| \`shop.orders:type=Queue,name=Check*\` | A | Giá trị name pattern, nhưng tập key phải đúng: B có thêm region |
| \`shop.orders:type=Queue,name=Check*,*\` | A, B | Value pattern kết hợp property-list pattern |
| \`shop.*:type=Queue,name=Checkout\` | A, E | Domain pattern; B bị loại vì thêm region |
| \`shop.*:type=Queue,name=Checkout,*\` | A, B, E | Domain wildcard và danh sách key mở rộng |
| \`shop.orders:*\` | A, B, C, D, F | Mọi key properties của đúng domain |
| \`*:*\` | A, B, C, D, E, F | Truy vấn toàn bộ MBeanServer |

Bảng trên minh họa **matching theo ObjectName**; một phép \`queryNames\` còn có thể dùng đối số thứ hai \`QueryExp\` để lọc theo biểu thức điều kiện.

## 6. Thực hành Java: đăng ký MBean và truy vấn theo pattern

### 6.1. Viết Standard MBean đơn giản

File \`QueueStatsMBean.java\`:

\`\`\`java
public interface QueueStatsMBean {
    int getPendingCount();
}
\`\`\`

File \`QueueStats.java\`:

\`\`\`java
public class QueueStats implements QueueStatsMBean {
    private final int pendingCount;

    public QueueStats(int pendingCount) {
        this.pendingCount = pendingCount;
    }

    @Override
    public int getPendingCount() {
        return pendingCount;
    }
}
\`\`\`

File \`ObjectNameDemo.java\`:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.util.Set;
import java.util.TreeSet;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class ObjectNameDemo {
    private static final String DOMAIN = "shop.orders";

    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName checkout = new ObjectName(
            DOMAIN + ":type=Queue,name=Checkout");
        ObjectName checkoutVn = new ObjectName(
            DOMAIN + ":type=Queue,name=Checkout,region=vn");
        ObjectName returns = new ObjectName(
            DOMAIN + ":type=Queue,name=Returns");

        server.registerMBean(new QueueStats(5), checkout);
        server.registerMBean(new QueueStats(8), checkoutVn);
        server.registerMBean(new QueueStats(2), returns);

        printMatches(server, DOMAIN + ":type=Queue,name=Checkout");
        printMatches(server, DOMAIN + ":type=Queue,name=Checkout,*");
        printMatches(server, DOMAIN + ":type=Queue,name=Check*");
        printMatches(server, DOMAIN + ":type=Queue,name=Check*,*");
        printMatches(server, DOMAIN + ":type=Queue,*");

        System.out.println("JConsole can inspect this process.");
        Thread.sleep(120_000);
    }

    private static void printMatches(MBeanServer server, String expression)
            throws Exception {
        ObjectName search = new ObjectName(expression);
        Set<ObjectName> found = server.queryNames(search, null);
        System.out.println("\\nPattern: " + search);
        for (String name : new TreeSet<>(
                found.stream()
                     .map(ObjectName::getCanonicalName)
                     .toList())) {
            System.out.println("  " + name);
        }
    }
}
\`\`\`

Chạy bằng JDK 21 (hoặc JDK tương thích):

\`\`\`bash
javac QueueStatsMBean.java QueueStats.java ObjectNameDemo.java
java ObjectNameDemo
\`\`\`

Kết quả dự kiến:

- \`name=Checkout\`: một tên.
- \`name=Checkout,*\`: hai tên.
- \`name=Check*\`: một tên vì thiếu \`,*\`.
- \`name=Check*,*\`: hai tên.
- \`type=Queue,*\`: ba tên.

Chú ý \`getCanonicalName()\` có thể sắp xếp key properties theo thứ tự chuẩn, dù tên được nhập theo thứ tự khác. Vì vậy khi so sánh, nên dùng chính \`ObjectName.equals\` hoặc canonical name; không dựa vào thứ tự chuỗi ban đầu.

### 6.2. Vì sao dùng \`queryNames\`, không chỉ \`isRegistered\`?

\`\`\`java
server.isRegistered(checkout); // kiểm tra đúng một ObjectName
server.queryNames(
    new ObjectName("shop.orders:type=Queue,*"), null
); // tìm nhiều MBean
\`\`\`

\`isRegistered\` dành cho tên cụ thể. \`queryNames\` nhận pattern và trả \`Set<ObjectName>\`. Một tên cụ thể cũng có thể được dùng làm tham số \`queryNames\` để truy vấn duy nhất tên đó. Nếu mục tiêu là tìm tập MBean, dùng pattern rõ ràng.

Khi cần lấy trực tiếp thông tin chi tiết, duyệt từng tên trong kết quả và gọi \`getMBeanInfo\`, \`getAttribute\` hoặc \`invoke\` tùy nhu cầu/quyền truy cập.

## 7. Kiểm tra API ObjectName bằng Java

Một số method cần nhớ:

\`\`\`java
ObjectName n = new ObjectName(
    "shop.orders:type=Queue,name=Checkout,*"
);

System.out.println(n.getDomain());
// shop.orders

System.out.println(n.getKeyProperty("type"));
// Queue

System.out.println(n.getKeyPropertyList());
// Map chứa type=Queue, name=Checkout

System.out.println(n.getCanonicalName());
// tên được chuẩn hóa theo thứ tự key

System.out.println(n.isPattern());
// true

System.out.println(n.isDomainPattern());
// false

System.out.println(n.isPropertyPattern());
// true

System.out.println(n.isPropertyListPattern());
// true

System.out.println(n.isPropertyValuePattern());
// false
\`\`\`

Dùng \`ObjectName.apply(ObjectName)\` để kiểm tra quy tắc matching phía client nếu cần:

\`\`\`java
ObjectName pattern = new ObjectName(
    "shop.orders:type=Queue,name=Checkout,*"
);
ObjectName candidate = new ObjectName(
    "shop.orders:type=Queue,name=Checkout,region=vn"
);
System.out.println(pattern.apply(candidate)); // true
\`\`\`

**Lưu ý:** \`apply\` đánh giá matching tên, không truy cập server và không kiểm tra MBean thực sự được đăng ký hay chưa. Query thực tế dùng \`MBeanServer.queryNames\`.

## 8. Wildcard trong domain, value và property-list: ba mức độ khác nhau

Hãy đọc mẫu theo từng tầng, không chỉ nhìn thấy \`*\` rồi kết luận “khớp tất cả”:

\`\`\`text
shop.*:type=Queue,name=Check*,*
^^^^^^ ^^^^^^^^^^^^^^^^^^^^^^
domain  key-value matching +
pattern property-list matching
\`\`\`

Quy tắc:

1. Domain phải khớp domain pattern.
2. Tất cả key property được chỉ định trong mẫu phải tồn tại và có giá trị khớp.
3. Nếu **không có** property-list pattern, candidate không được có thêm key ngoài danh sách trong mẫu.
4. Nếu **có** property-list pattern, candidate được có thêm key.
5. Nếu một value có wildcard, wildcard chỉ áp dụng cho value của đúng key đó.

Ví dụ:

\`\`\`text
Mẫu:     shop.orders:type=Queue,name=Check*,*
Candidate: shop.orders:type=Queue,name=Checkout,region=vn
\`\`\`

Khớp vì domain đúng, type đúng, name khớp \`Check*\`, và \`,*\` cho phép thêm \`region\`.

Ngược lại:

\`\`\`text
Mẫu:     shop.orders:type=Queue,name=Check*
Candidate: shop.orders:type=Queue,name=Checkout,region=vn
\`\`\`

Không khớp vì mẫu yêu cầu tập property chính xác \`{type,name}\`.

## 9. Quy tắc đặt ObjectName cho ứng dụng lớn

### 9.1. Dùng domain có namespace rõ ràng

Nên chọn domain ổn định, ví dụ:

\`\`\`text
com.example.shop.orders:type=Queue,name=Checkout
com.example.shop.orders:type=Queue,name=Returns
com.example.shop.billing:type=InvoiceProcessor,name=Primary
\`\`\`

Không nên dùng domain chung \`app\` cho nhiều ứng dụng có thể chia sẻ MBeanServer nếu dễ dẫn đến trùng tên.

### 9.2. Chọn key properties có ý nghĩa

Các key thường gặp là \`type\`, \`name\`, \`component\`, \`instance\`, \`region\`. Chúng là **quy ước do ứng dụng chọn**, không phải danh sách thuộc tính được JMX bắt buộc.

Thống nhất cách đặt tên để query nhất quán:

\`\`\`text
com.example.shop:type=Cache,name=Products
com.example.shop:type=Cache,name=Customers
com.example.shop:type=Queue,name=Checkout
\`\`\`

Query theo nhóm:

\`\`\`text
com.example.shop:type=Cache,*
\`\`\`

### 9.3. Tránh dữ liệu thay đổi thường xuyên trong định danh

Không nên đưa các giá trị như số lượng request hiện tại, timestamp tức thời hoặc trạng thái \`online/offline\` vào ObjectName. Những dữ liệu đó phù hợp với **attribute**; tên MBean nên giữ ổn định trong vòng đời quản trị.

Ví dụ:

\`\`\`text
Không nên: com.example:type=Queue,name=Checkout,pending=123
Nên:       com.example:type=Queue,name=Checkout
Attribute: PendingCount = 123
\`\`\`

Khi MBean có vòng đời ngắn, cần có chiến lược đăng ký/hủy đăng ký và truy vấn phù hợp. Tránh tạo vô số ObjectName theo dữ liệu đầu vào từ request.

### 9.4. Không nhét dữ liệu nhạy cảm vào tên

ObjectName có thể xuất hiện trong logs, console quản trị hoặc công cụ monitoring. Tránh user ID, email, token, secret hoặc thông tin cá nhân nếu không thực sự cần. Dùng tên định danh nội bộ an toàn và thuộc tính được kiểm soát khi cần biểu diễn thêm trạng thái.

### 9.5. Canonical name và tính duy nhất

Nếu một client nhận:

\`\`\`text
shop.orders:name=Checkout,type=Queue
shop.orders:type=Queue,name=Checkout
\`\`\`

hai chuỗi có thứ tự key khác nhau nhưng cùng một ObjectName. \`getCanonicalName()\` giúp trình bày nhất quán; \`ObjectName.equals\` giúp so sánh đúng semantics.

## 10. Liên hệ với Spring Framework JMX

Spring Framework có các cơ chế xuất Spring bean thành MBean, trong đó \`MBeanExporter\` và \`@ManagedResource\` có thể sử dụng ObjectName cụ thể.

Ví dụ minh họa:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.shop:type=Queue,name=Checkout",
    description = "Checkout queue management view"
)
public class CheckoutQueueMonitor {
    private volatile int pendingCount;

    @ManagedAttribute(description = "Current pending jobs")
    public int getPendingCount() {
        return pendingCount;
    }

    public void setPendingCountForDemo(int pendingCount) {
        this.pendingCount = pendingCount;
    }
}
\`\`\`

Trong ứng dụng đã kích hoạt export JMX thích hợp (ví dụ Spring Framework \`@EnableMBeanExport\` hoặc cấu hình \`MBeanExporter\` tương đương), bean có thể được đăng ký dưới tên đã khai báo. **ObjectName trong metadata export phải là tên cụ thể; wildcard pattern được dành cho truy vấn.**

Ở phía client, không cần biết bean được xuất bởi Spring hay Java thuần để tìm nó:

\`\`\`java
ObjectName allQueues = new ObjectName(
    "com.example.shop:type=Queue,*"
);
Set<ObjectName> names = connection.queryNames(allQueues, null);
\`\`\`

Cùng một truy vấn hoạt động đối với những MBean thỏa cấu trúc tên, dù cơ chế đăng ký đến từ Spring hay \`registerMBean\` trực tiếp.

### 10.1. ObjectNamingStrategy trong Spring

Khi một ứng dụng có nhiều bean, \`MBeanExporter\` có thể sử dụng chiến lược đặt tên như \`ObjectNamingStrategy\` để xác định ObjectName từ bean. Mục đích là giữ quy ước domain/key thống nhất thay vì đặt tên tùy ý cho từng bean. Tuy nhiên, chiến lược đặt tên không thay đổi semantics của \`ObjectName\`: mỗi MBean đăng ký phải có tên cụ thể và không trùng trên cùng MBeanServer.

### 10.2. Đặt tên Spring bean không phải đặt tên MBean

Một bean có tên \`checkoutQueueMonitor\` trong ApplicationContext không có nghĩa ObjectName JMX cũng là \`checkoutQueueMonitor\`. Tên bean và ObjectName thuộc hai namespace khác nhau. MBeanExporter/metadata/chiến lược đặt tên quyết định mapping thực tế. Khi debug, phải kiểm tra tên được đăng ký trên MBeanServer.

## 11. Chẩn đoán các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| \`MalformedObjectNameException\` | Chuỗi tên sai cú pháp hoặc ký tự chưa quote đúng | Tạo \`new ObjectName(...)\` trong ví dụ nhỏ; kiểm tra domain/key/value |
| \`InstanceAlreadyExistsException\` | Đăng ký cùng ObjectName hai lần | Kiểm tra \`isRegistered\`, chiến lược naming và vòng đời exporter |
| \`queryNames\` trả rỗng | Domain/key không khớp hoặc mẫu quá chặt | So sánh \`getCanonicalName\`; kiểm tra thiếu \`,*\` |
| Kết quả query nhiều hơn mong đợi | Dùng \`:*\` hoặc \`,*\` quá rộng | Giới hạn domain, type, name |
| Mẫu không khớp tên có region | Không có property-list wildcard | So sánh \`type=Queue,name=X\` với \`type=Queue,name=X,*\` |
| Client truy vấn đúng tên mà vẫn không có MBean | Kết nối nhầm MBeanServer/process | Xác nhận JVM, connector và danh sách tên đăng ký |
| Spring bean tồn tại nhưng không thấy qua JMX | Chưa export hoặc tên JMX khác dự kiến | Kiểm tra MBeanExporter, annotation và naming strategy |

Không sửa lỗi \`queryNames\` rỗng bằng cách thử \`*:* \` trên hệ thống lớn ngay lập tức. Ưu tiên đọc domain thực tế từ một danh sách hẹp, sau đó mở rộng truy vấn có chủ đích.

## 12. Bài tập thực hành

### Bài tập A — Phân loại tên

Cho các chuỗi:

\`\`\`text
alpha:type=Worker,name=A
alpha:type=Worker,*
alpha:type=Worker,name=A*
alpha:*
*:type=Worker,*
\`\`\`

Hãy tạo \`ObjectName\` cho từng chuỗi và in \`isPattern\`, \`isDomainPattern\`, \`isPropertyValuePattern\`, \`isPropertyListPattern\`. Giải thích tại sao kết quả khác nhau.

### Bài tập B — Chọn pattern đúng

Giả sử server có:

\`\`\`text
training:type=Cache,name=Products
training:type=Cache,name=Products,region=vn
training:type=Cache,name=Customers
training:type=Queue,name=Orders
\`\`\`

Tạo pattern để:

1. Chỉ tìm đúng cache Products không có thuộc tính khác.
2. Tìm cache Products với mọi vùng.
3. Tìm tất cả Cache.
4. Tìm mọi loại resource trong domain training.
5. Tìm tất cả resource có \`name\` bắt đầu bằng \`Prod\`, kể cả khi có key khác.

Gợi ý đáp án:

\`\`\`text
1. training:type=Cache,name=Products
2. training:type=Cache,name=Products,*
3. training:type=Cache,*
4. training:*
5. training:name=Prod*,*
\`\`\`

### Bài tập C — Tên có ký tự đặc biệt

Tạo tên cho một queue có tên hiển thị \`Urgent, East\`. Dùng \`ObjectName.quote\`, so sánh với tên nhập bằng chuỗi chưa quote và giải thích vì sao dấu phẩy được hiểu khác nhau.

### Bài tập D — So sánh canonical

Tạo hai ObjectName với cùng domain và cùng cặp \`type/name\` nhưng đảo thứ tự. In \`equals\`, \`toString\` và \`getCanonicalName\`. Tự giải thích vì sao chỉ so sánh chuỗi nhập ban đầu có thể gây lỗi.

### Bài tập E — Spring JMX

Với một ứng dụng Spring đã bật JMX export, tạo hai bean quản trị với ObjectName:

\`\`\`text
com.example.demo:type=Worker,name=Email
com.example.demo:type=Worker,name=Export
\`\`\`

Dùng JConsole hoặc một client gọi \`queryNames("com.example.demo:type=Worker,*")\` và kiểm tra cả hai. Thử đổi một tên thành trùng và quan sát lỗi đăng ký.

## 13. Câu hỏi tự kiểm tra

1. ObjectName xác định MBean trong phạm vi nào?
2. Sự khác nhau giữa ObjectName cụ thể và ObjectName pattern là gì?
3. \`*\` trong giá trị \`name=App*\` khác gì \`,*\` cuối danh sách key properties?
4. Vì sao \`shop:type=Queue\` không tìm thấy \`shop:type=Queue,name=Checkout\`?
5. Vì sao \`shop:type=Queue,*\` có thể tìm thấy cả hai tên vừa nêu?
6. Khi nào nên dùng \`isRegistered\` thay cho \`queryNames\`?
7. Tại sao phải chuẩn hóa hoặc quote dữ liệu được dùng trong ObjectName?
8. \`ObjectName.apply\` có xác nhận MBean tồn tại trên server không?
9. Nếu Spring bean tên \`workerService\`, ObjectName JMX của nó có buộc trùng tên này không?
10. Những nguy cơ nào xuất hiện nếu dùng \`*:* \` như một truy vấn monitoring mặc định?

## 14. Tài liệu tham khảo

- Java SE 21 — \`ObjectName\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
- Java SE 21 — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 — \`MBeanServerConnection\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html

**Ghi nhớ:** ObjectName cụ thể giúp định danh và thao tác chính xác một MBean; ObjectName pattern giúp tìm một tập MBean. Khi viết pattern, luôn tách biệt wildcard của domain, wildcard của giá trị và property-list wildcard \`,*\` — đây là chìa khóa để truy vấn đúng và ổn định.
