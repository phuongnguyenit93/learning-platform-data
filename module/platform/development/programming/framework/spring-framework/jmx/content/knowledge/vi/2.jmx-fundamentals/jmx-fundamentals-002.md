# MBeanServer như một registry và điểm thực thi quản trị

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò trung tâm của **MBeanServer** trong Java Management Extensions (JMX): nơi đăng ký, tra cứu, quan sát và điều khiển các MBean.
- Phân biệt **registry** (quản lý tên và định danh đối tượng quản trị) với **điểm thực thi quản trị** (đọc/ghi thuộc tính, gọi operation và nhận notification).
- Sử dụng \`ObjectName\`, \`MBeanServerFactory\` và \`ManagementFactory.getPlatformMBeanServer()\` để đăng ký và thao tác MBean.
- Nhận biết ranh giới giữa \`MBeanServer\` chạy trong JVM và \`MBeanServerConnection\` dùng chung cho truy cập cục bộ hoặc qua connector.
- Xử lý các lỗi phổ biến: trùng tên, chưa đăng ký, sai kiểu thuộc tính, lỗi nghiệp vụ và quyền truy cập.
- Thiết kế namespace, vòng đời đăng ký và các thao tác quản trị an toàn cho ứng dụng Spring Framework.

## 2. Bức tranh tổng thể: MBean, ObjectName và MBeanServer

JMX cho phép đưa trạng thái và thao tác vận hành của ứng dụng Java ra một giao diện quản trị có cấu trúc. Một thành phần muốn được quản trị được biểu diễn dưới dạng **MBean** (Managed Bean). MBeanServer đóng vai trò trung gian: công cụ quản trị tương tác với server, còn server định tuyến yêu cầu tới MBean phù hợp.

\`\`\`text
Ứng dụng / Spring bean
       |
       | tạo, đăng ký MBean
       v
+--------------------------------------+
| MBeanServer (trong JVM)              |
|                                      |
| ObjectName -> MBean                  |
| com.example:type=Cache,name=Products |
| com.example:type=Jobs,name=Importer  |
|                                      |
| getAttribute / setAttribute          |
| invoke / queryNames / notifications  |
+--------------------------------------+
       ^
       | MBeanServerConnection
       |
JConsole / VisualVM / JMX client
       |
   có thể đi qua JMXConnectorServer
   khi cần quản trị từ xa
\`\`\`

Các khái niệm cốt lõi:

| Thành phần | Trách nhiệm |
| --- | --- |
| **MBean** | Cung cấp thuộc tính, thao tác hoặc thông báo có ý nghĩa quản trị. |
| **ObjectName** | Định danh MBean trong MBeanServer theo mẫu \`domain:key=value,...\`. |
| **MBeanServer** | Đăng ký, hủy đăng ký, tra cứu và thực thi yêu cầu quản trị trên MBean. |
| **MBeanServerConnection** | Hợp đồng thao tác JMX mà cả client cục bộ và client từ xa có thể sử dụng. |
| **JMXConnectorServer** | Cung cấp đầu cuối kết nối từ xa tới một MBeanServer khi được cấu hình. |

Điểm quan trọng: \`MBeanServer\` không phải kho dữ liệu nghiệp vụ hay hệ thống service discovery phân tán. Nó là **registry MBean trong phạm vi một JVM/server** và là đầu mối gọi các API quản trị.

## 3. Vai trò thứ nhất: registry của các MBean

### 3.1. Đăng ký theo ObjectName

Mỗi MBean đăng ký phải có một \`ObjectName\` duy nhất trong cùng \`MBeanServer\`. Ví dụ:

\`\`\`text
com.example.application:type=Cache,name=Products
com.example.application:type=Cache,name=Customers
com.example.application:type=Jobs,name=DailyImport
\`\`\`

\`com.example.application\` là domain; phần sau dấu hai chấm chứa các key property. Domain và tập key property tạo nên tên định danh. Thứ tự key property trong một tên không nên dùng để phân biệt MBean: \`ObjectName\` xử lý tên theo ngữ nghĩa key/value.

Một MBean có thể được đăng ký bằng:

\`\`\`java
ObjectName name =
    new ObjectName("com.example.application:type=Cache,name=Products");
server.registerMBean(cacheMonitor, name);
\`\`\`

Khi một MBean đã được đăng ký với tên đó, đăng ký thêm MBean khác cùng tên sẽ phát sinh \`InstanceAlreadyExistsException\`. Đăng ký không tự ghi đè đối tượng cũ.

### 3.2. Tra cứu và kiểm kê

Các API registry thường dùng:

\`\`\`java
boolean exists = server.isRegistered(name);

Set<ObjectName> allCaches = server.queryNames(
    new ObjectName("com.example.application:type=Cache,*"),
    null
);

int count = server.getMBeanCount();
ObjectInstance instance = server.getObjectInstance(name);
\`\`\`

- \`isRegistered\`: kiểm tra một định danh đã có hay chưa.
- \`queryNames\`: tìm những \`ObjectName\` khớp một pattern; tham số \`QueryExp\` tùy chọn cho điều kiện lọc.
- \`getMBeanCount\`: đếm số MBean trong server.
- \`getObjectInstance\`: trả về tên và class name của MBean đã đăng ký.

\`queryNames\` là thao tác khám phá các đối tượng quản trị; nó không quét Spring application context và không tìm các Java object chưa đăng ký thành MBean.

### 3.3. Vòng đời registry

Đường đi điển hình:

\`\`\`text
Khởi tạo thành phần
    -> tạo MBean adapter
    -> tạo ObjectName ổn định
    -> registerMBean
    -> vận hành và xử lý các lệnh quản trị
    -> unregisterMBean khi đóng thành phần/ứng dụng
\`\`\`

Hủy đăng ký:

\`\`\`java
if (server.isRegistered(name)) {
    server.unregisterMBean(name);
}
\`\`\`

Trong ứng dụng có nhiều luồng hoặc nhiều thành phần cùng quản lý tên, chuỗi \`isRegistered\` rồi \`unregisterMBean\` không phải thao tác nguyên tử. Đối tượng có thể bị gỡ ngay sau khi kiểm tra; vì vậy cần xử lý \`InstanceNotFoundException\` nếu có cạnh tranh.

## 4. Vai trò thứ hai: điểm thực thi yêu cầu quản trị

Đăng ký chỉ là bước đầu. Điểm khác biệt của MBeanServer là nó tiếp nhận lệnh, xác định MBean đích và chuyển thao tác quản trị tới MBean đó.

| Yêu cầu | API tiêu biểu | Ý nghĩa |
| --- | --- | --- |
| Đọc trạng thái | \`getAttribute(name, "Hits")\` | Lấy giá trị một thuộc tính được công bố. |
| Cập nhật cấu hình | \`setAttribute(name, new Attribute("Enabled", false))\` | Ghi thuộc tính có hỗ trợ setter và được phép ghi. |
| Chạy tác vụ | \`invoke(name, "clear", ..., ...)\` | Gọi operation MBean được công bố. |
| Khám phá giao diện | \`getMBeanInfo(name)\` | Đọc metadata thuộc tính, operation và notification. |
| Nhận sự kiện | \`addNotificationListener(...)\` | Đăng ký người lắng nghe notification. |

MBeanServer **không tự cung cấp** mọi thuộc tính hoặc method của Java object. Những gì có thể gọi được phụ thuộc vào giao diện JMX của MBean (Standard MBean, MXBean, Dynamic MBean, v.v.) và cấu hình/quyền truy cập thực tế.

### 4.1. Đọc và ghi thuộc tính

\`\`\`java
Long hits = (Long) server.getAttribute(name, "Hits");

server.setAttribute(
    name,
    new Attribute("Enabled", Boolean.FALSE)
);
\`\`\`

Thuộc tính \`Hits\` chỉ có thể đọc nếu giao diện MBean công bố getter phù hợp. \`Enabled\` chỉ ghi được nếu có setter được công bố và kiểu giá trị tương thích. Tên thuộc tính JMX phân biệt chữ hoa/chữ thường.

Với nhiều thuộc tính, có thể dùng \`getAttributes\` / \`setAttributes\`; kết quả cần được kiểm tra vì yêu cầu hàng loạt có thể không thành công đồng đều ở từng thuộc tính.

### 4.2. Gọi operation

\`\`\`java
server.invoke(
    name,
    "clear",
    new Object[0],
    new String[0]
);
\`\`\`

Bốn tham số lần lượt là \`ObjectName\`, tên operation, mảng tham số và mảng tên kiểu của tham số. Khi operation có overload, signature giúp MBeanServer chọn đúng operation. Ví dụ operation \`resize(int)\` có thể dùng:

\`\`\`java
server.invoke(
    name,
    "resize",
    new Object[] { 250 },
    new String[] { "int" }
);
\`\`\`

Việc gọi một operation có thể tạo ra tác dụng phụ thật như xóa cache, làm mới cấu hình hay dừng một tác vụ. Không nên xem endpoint JMX chỉ là nơi đọc số liệu.

### 4.3. Metadata và khả năng khám phá

\`\`\`java
MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "%s: type=%s, readable=%s, writable=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println(operation.getName());
}
\`\`\`

Công cụ như JConsole dựa vào metadata này để trình bày phần Attributes và Operations. Metadata mô tả khả năng quản trị đã được công bố, không phải toàn bộ API nội bộ của ứng dụng.

## 5. Ví dụ chạy được: đăng ký, tra cứu, đọc/ghi và invoke

Ví dụ dùng Java chuẩn, không cần phụ thuộc Spring, để thấy rõ bản chất của \`MBeanServer\`.

### 5.1. Khai báo Standard MBean

Tên interface phải phù hợp quy ước Standard MBean: class \`CacheMonitor\` có interface \`CacheMonitorMBean\`.

\`\`\`java
package example.jmx;

public interface CacheMonitorMBean {
    int getSize();
    boolean isEnabled();
    void setEnabled(boolean enabled);
    void clear();
}
\`\`\`

\`\`\`java
package example.jmx;

public final class CacheMonitor implements CacheMonitorMBean {
    private volatile boolean enabled = true;
    private volatile int size = 42;

    @Override
    public int getSize() {
        return size;
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    @Override
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @Override
    public void clear() {
        size = 0;
    }
}
\`\`\`

Ở đây \`Size\` là thuộc tính chỉ đọc, \`Enabled\` là thuộc tính đọc/ghi và \`clear\` là operation. \`volatile\` giúp quan sát các cập nhật đơn giản giữa các luồng; với trạng thái phức tạp, cần cơ chế đồng bộ riêng.

### 5.2. Thực thi qua platform MBeanServer

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.Attribute;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class JmxRegistryDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
            "com.example.application:type=Cache,name=Products"
        );

        CacheMonitor monitor = new CacheMonitor();
        server.registerMBean(monitor, name);

        try {
            System.out.println("Registered = " + server.isRegistered(name));
            System.out.println("Names = " + server.queryNames(
                new ObjectName("com.example.application:type=Cache,*"),
                null
            ));
            System.out.println("Size before = "
                + server.getAttribute(name, "Size"));

            server.setAttribute(
                name,
                new Attribute("Enabled", Boolean.FALSE)
            );
            System.out.println("Enabled = "
                + server.getAttribute(name, "Enabled"));

            server.invoke(name, "clear", new Object[0], new String[0]);
            System.out.println("Size after = "
                + server.getAttribute(name, "Size"));

            MBeanInfo info = server.getMBeanInfo(name);
            System.out.println("MBean class = " + info.getClassName());
        } finally {
            server.unregisterMBean(name);
        }
    }
}
\`\`\`

Kết quả mong đợi về mặt ý nghĩa:

\`\`\`text
Registered = true
Names = [com.example.application:type=Cache,name=Products]
Size before = 42
Enabled = false
Size after = 0
MBean class = example.jmx.CacheMonitor
\`\`\`

Dòng \`Names\` có thể khác thứ tự hiển thị trong các trường hợp nhiều MBean khớp truy vấn. Các giá trị quan trọng để tự kiểm chứng là: đăng ký thành công, đọc được \`Size=42\`, ghi được \`Enabled=false\` và gọi \`clear\` làm \`Size=0\`.

Chạy trong dự án Java với cấu trúc package phù hợp và JDK có module \`java.management\` (JDK tiêu chuẩn thường cung cấp sẵn). Nếu app được quản lý bởi container/Spring, dùng vòng đời bean/container thay cho tự đăng ký lại cùng \`ObjectName\` từ nhiều nơi.

## 6. MBeanServer và MBeanServerConnection

\`MBeanServer\` kế thừa giao diện thao tác \`MBeanServerConnection\`. Client có thể viết mã dựa vào \`MBeanServerConnection\` để sử dụng cùng các lệnh như \`getAttribute\`, \`invoke\` và \`queryNames\` mà không cần biết kết nối cục bộ hay từ xa.

\`\`\`java
import javax.management.MBeanServerConnection;

MBeanServerConnection connection =
    ManagementFactory.getPlatformMBeanServer();

Object value = connection.getAttribute(name, "Size");
\`\`\`

Trong quản trị từ xa, client thường nhận \`MBeanServerConnection\` từ \`JMXConnector\`, còn server-side \`JMXConnectorServer\` chuyển yêu cầu tới MBeanServer thực sự. Kết nối từ xa phụ thuộc vào connector, xác thực, mạng và cấu hình an toàn. \`ManagementFactory.getPlatformMBeanServer()\` tự nó không tự động mở cổng từ xa.

**Phân biệt ba phạm vi:**

1. **MBean Java** giữ logic quản trị và trạng thái.
2. **MBeanServer trong JVM** quản lý namespace và chuyển lệnh đến MBean.
3. **JMX connector/client** vận chuyển yêu cầu qua ranh giới tiến trình nếu được bật.

Một JVM có thể có nhiều MBeanServer được tạo qua \`MBeanServerFactory\`; vì vậy cùng \`ObjectName\` có thể tồn tại độc lập trên các server khác nhau. Với ứng dụng thông thường, platform MBeanServer thường là lựa chọn thuận tiện để các công cụ JMX quan sát.

## 7. ObjectName và quy tắc thiết kế namespace

Một quy ước dễ vận hành:

\`\`\`text
<domain>:type=<loại thành phần>,name=<định danh ổn định>
\`\`\`

Ví dụ:

\`\`\`text
com.acme.orders:type=Cache,name=OrderReadCache
com.acme.orders:type=Scheduler,name=Reconciliation
com.acme.orders:type=Queue,name=RetryQueue
\`\`\`

Nguyên tắc:

- Chọn domain có khả năng phân biệt tổ chức hoặc ứng dụng; tránh chiếm namespace chuẩn như \`java.lang\`.
- Dùng \`type\` cho loại MBean, \`name\` cho một instance cụ thể; có thể thêm \`component\`, \`tenant\` hoặc \`id\` khi cần.
- Đặt tên ổn định qua vòng đời tiến trình để công cụ giám sát có thể truy vấn nhất quán.
- Không đưa mật khẩu, token hoặc thông tin cá nhân vào \`ObjectName\`: tên được hiển thị với công cụ quản trị và có thể xuất hiện trong log.
- Với giá trị tên động có ký tự đặc biệt, sử dụng cơ chế quote của \`ObjectName\` và kiểm tra quy tắc tên; không nối chuỗi đầu vào tùy ý rồi giả định hợp lệ.
- Khi có nhiều phiên bản ứng dụng trong nhiều JVM, nhớ rằng ObjectName duy nhất chỉ trong từng MBeanServer; định danh host/instance thuộc lớp quản lý kết nối hoặc namespace có chủ ý.

\`ObjectName\` còn hỗ trợ pattern, chẳng hạn:

\`\`\`java
ObjectName pattern = new ObjectName(
    "com.acme.orders:type=Cache,*"
);
Set<ObjectName> matches = server.queryNames(pattern, null);
\`\`\`

Pattern chủ yếu dùng để tìm kiếm; \`registerMBean\` cần tên cụ thể, không phải tên pattern.

## 8. Tích hợp với Spring Framework

Trong Spring, các bean ứng dụng có thể được xuất ra JMX bằng cơ chế Spring JMX, tiêu biểu là \`MBeanExporter\`, \`@ManagedResource\`, \`@ManagedAttribute\` và \`@ManagedOperation\` (khi dùng mô hình annotation phù hợp).

### 8.1. Bean quản trị và annotation

\`\`\`java
package example.springjmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.application:type=Cache,name=Products",
    description = "Product cache operations"
)
public class ProductCacheAdmin {

    private volatile boolean enabled = true;

    @ManagedAttribute(description = "Whether cache is enabled")
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @ManagedOperation(description = "Clear product cache")
    public void clear() {
        // Gọi API xóa cache thật trong ứng dụng khi triển khai.
    }
}
\`\`\`

Đây là bean Spring bình thường. Các annotation cung cấp metadata JMX; để xuất MBean thực sự cần có cấu hình exporter phù hợp. Việc có annotation đơn thuần không đủ để khẳng định MBean đã được đăng ký ở mọi cấu hình Spring.

### 8.2. Đăng ký exporter trong Spring thuần

\`\`\`java
package example.springjmx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxConfig {

    @Bean
    public MBeanExporter mBeanExporter(
            ProductCacheAdmin productCacheAdmin) {
        AnnotationJmxAttributeSource source =
            new AnnotationJmxAttributeSource();

        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);

        MetadataNamingStrategy naming =
            new MetadataNamingStrategy();
        naming.setAttributeSource(source);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        exporter.setBeans(java.util.Map.of(
            "productCacheAdmin", productCacheAdmin
        ));
        return exporter;
    }
}
\`\`\`

Ví dụ chủ ý khai báo exporter rõ ràng để thấy cơ chế xuất. Khi dùng Spring Boot, cấu hình quản lý JMX có thể được auto-configure theo dependency và thuộc tính cấu hình; cần kiểm tra cấu hình của ứng dụng cụ thể để tránh đăng ký hai exporter cùng tên.

Lúc container khởi tạo exporter, MBean được đăng ký trong MBeanServer được chọn; lúc hủy context, exporter có thể hủy đăng ký những MBean thuộc quyền quản lý của mình. Không trộn tự gọi \`registerMBean\` và exporter trên cùng \`ObjectName\` nếu chưa thiết kế rõ ownership.

### 8.3. JMX không thay thế Spring bean registry

| Spring ApplicationContext | JMX MBeanServer |
| --- | --- |
| Quản lý dependency injection, lifecycle và bean scope. | Quản lý MBean được công bố và tương tác quản trị. |
| Tìm bean bằng tên/kiểu/qualifier. | Tìm MBean bằng \`ObjectName\` và JMX pattern. |
| Gọi method Java trong code ứng dụng. | Đọc/ghi thuộc tính và gọi operation đã xuất qua JMX. |
| Phục vụ logic ứng dụng. | Phục vụ quan sát và điều khiển vận hành. |

Một Spring bean không tự động xuất hiện trên JMX chỉ vì nó tồn tại trong ApplicationContext.

## 9. Notification: MBeanServer còn hỗ trợ luồng sự kiện quản trị

Bên cạnh đọc/ghi/gọi operation, một MBean có thể phát ra \`Notification\`. MBeanServer cho phép đăng ký listener theo \`ObjectName\`:

\`\`\`java
NotificationListener listener = (notification, handback) ->
    System.out.println(
        notification.getType() + ": " + notification.getMessage()
    );

server.addNotificationListener(
    name,
    listener,
    null,
    null
);

try {
    // Thao tác khác và xử lý notification từ MBean nếu có.
} finally {
    server.removeNotificationListener(name, listener);
}
\`\`\`

Đoạn này chỉ hoạt động nếu MBean đích hỗ trợ phát notification (ví dụ hiện thực \`NotificationBroadcaster\`); Standard MBean \`CacheMonitor\` trong ví dụ trước chưa cung cấp tính năng đó. Listener cần được tháo để tránh giữ tham chiếu lâu hơn vòng đời mong muốn.

Một số sự kiện đăng ký/hủy đăng ký MBean có thể quan sát qua delegate MBean \`JMImplementation:type=MBeanServerDelegate\`. Đây là notification về thay đổi registry, khác với notification nghiệp vụ từ một MBean ứng dụng.

## 10. Xử lý lỗi và điều kiện tranh chấp

Các exception đáng nhận diện:

| Exception | Tình huống thường gặp | Cách xử lý |
| --- | --- | --- |
| \`InstanceAlreadyExistsException\` | Đăng ký trùng \`ObjectName\`. | Xác định ownership, tránh đăng ký lặp; không ghi đè tùy tiện. |
| \`InstanceNotFoundException\` | Truy cập MBean chưa có hoặc đã bị hủy đăng ký. | Xử lý vòng đời, kiểm tra lại danh sách registry. |
| \`MalformedObjectNameException\` | Chuỗi tên sai định dạng. | Sửa quy tắc đặt tên, quote dữ liệu động. |
| \`AttributeNotFoundException\` | Tên thuộc tính không tồn tại/không có accessor phù hợp. | Kiểm tra \`getMBeanInfo\` và phân biệt hoa/thường. |
| \`InvalidAttributeValueException\` | Giá trị ghi không phù hợp. | Kiểm tra kiểu, ràng buộc và setter. |
| \`ReflectionException\` | Lỗi phản xạ khi xử lý yêu cầu. | Kiểm tra signature và nguyên nhân gốc. |
| \`MBeanException\` | Operation hoặc getter/setter của MBean ném checked exception được bọc lại. | Xem target exception và khôi phục nghiệp vụ phù hợp. |
| \`RuntimeMBeanException\` | Runtime exception phát sinh trong MBean. | Xem nguyên nhân gốc; không nuốt lỗi. |
| \`NotCompliantMBeanException\` | Đối tượng không tuân thủ hợp đồng MBean lúc đăng ký. | Rà quy tắc Standard MBean/MXBean hoặc dùng adapter phù hợp. |

Đừng thiết kế logic chỉ theo \`isRegistered\` rồi mặc định thao tác kế tiếp sẽ thành công. Một luồng khác có thể hủy đăng ký giữa hai lệnh (time-of-check/time-of-use).

Đối với thao tác có side effect, exception từ \`invoke\` không luôn chứng minh tác vụ chưa chạy. Tác vụ có thể đã bắt đầu hoặc hoàn tất một phần trước khi lỗi được chuyển về. Nên thiết kế operation có tính lặp an toàn hoặc có thông tin trạng thái riêng khi cần.

## 11. Bảo mật và vận hành thực tế

MBeanServer có thể mở quyền điều khiển tài nguyên quan trọng của ứng dụng. Ví dụ, \`clearCache\`, \`reloadConfiguration\`, \`stopJob\` hoặc đổi cờ chức năng đều có tác động vận hành.

Nên áp dụng các nguyên tắc sau:

1. **Giới hạn giao diện**: chỉ công bố thuộc tính/operation phục vụ giám sát và quản trị đã có chủ đích.
2. **Ưu tiên read-only** cho số liệu giám sát; chỉ mở setter hay operation thay đổi trạng thái khi thật sự cần.
3. **Bảo vệ remote JMX**: nếu bật connector từ xa, cấu hình xác thực, phân quyền, mã hóa và giới hạn truy cập mạng theo môi trường triển khai. Không xem việc đã bật JMX là đã có bảo mật mặc định đầy đủ.
4. **Không công bố bí mật**: getter quản trị, \`ObjectName\` và notification không được rò token, mật khẩu hoặc dữ liệu nhạy cảm.
5. **Kiểm soát tải**: getter được gọi bởi công cụ giám sát nên nhanh và ít side effect; operation tốn thời gian cần có trạng thái tiến độ/cơ chế bất đồng bộ phù hợp.
6. **Đảm bảo dọn dẹp**: hủy đăng ký MBean và listener khi thành phần kết thúc để tránh trùng tên hoặc leak tham chiếu.
7. **Quan sát lỗi**: log operation quản trị có ảnh hưởng lớn với ngữ cảnh phù hợp; tránh đưa dữ liệu nhạy cảm vào log.

Phân biệt việc **có thể gọi một operation qua JMX** với việc **người gọi được phép làm vậy**. Quyền thực tế phụ thuộc kiến trúc connector, chính sách bảo mật, lớp authorization hoặc proxy của hệ thống. API \`MBeanServer\` tự nó không thay thế chính sách an toàn của ứng dụng.

## 12. Khi nào nên dùng MBeanServer trực tiếp?

**Dùng trực tiếp** khi cần kiểm soát việc tạo MBean, tên đăng ký, vòng đời, truy vấn hoặc thực thi qua API JMX trong Java; ví dụ một thư viện hạ tầng muốn công bố trạng thái pool hoặc scheduler.

**Dùng Spring JMX exporter** khi muốn quản lý vòng đời cùng ApplicationContext và xuất các bean của ứng dụng có metadata rõ ràng.

**Dùng công cụ metrics/observability khác** khi mục tiêu chủ yếu là thu thập chuỗi thời gian, vẽ dashboard hoặc cảnh báo theo hệ metrics. JMX là nguồn cung cấp thuộc tính quản trị; hệ giám sát có thể lấy dữ liệu JMX thông qua exporter/collector, nhưng JMX không tự thay thế hệ lưu trữ metrics.

Một ứng dụng có thể kết hợp các lựa chọn này: Spring xuất MBean vào platform MBeanServer, JConsole truy cập để chẩn đoán cục bộ, còn một thành phần monitor đọc các thuộc tính được chọn để phát metrics.

## 13. Bài tập tự thực hành

**Bài tập 1 — Registry.** Tạo hai instance MBean theo tên \`com.example:type=Cache,name=A\` và \`com.example:type=Cache,name=B\`. Dùng \`queryNames("com.example:type=Cache,*", null)\` để liệt kê cả hai. Thử đăng ký lần hai với tên A và quan sát \`InstanceAlreadyExistsException\`.

**Bài tập 2 — Attribute và operation.** Thêm thuộc tính \`Threshold\` có getter/setter và operation \`resetStatistics()\`. Gọi \`getMBeanInfo\` để thấy khả năng đọc/ghi và method được công bố, sau đó thử \`setAttribute\` và \`invoke\`.

**Bài tập 3 — Vòng đời.** Tạo MBean khi khởi động và hủy đăng ký khi ứng dụng dừng. Kiểm tra \`isRegistered\` trước và sau khi kết thúc. Xử lý trường hợp lệnh truy cập xảy ra đúng lúc MBean bị gỡ.

**Bài tập 4 — Spring.** Tạo bean có \`@ManagedResource\` và một \`@ManagedOperation\`, cấu hình \`MBeanExporter\`, rồi dùng JConsole quan sát domain, thuộc tính và operation. Chứng minh rằng chỉ khai báo Spring bean mà không xuất JMX thì tên tương ứng chưa xuất hiện trong registry.

## 14. Câu hỏi kiểm tra hiểu biết

**1. Vì sao gọi MBeanServer là registry?** Vì nó quản lý ánh xạ \`ObjectName\` tới các MBean đã đăng ký, hỗ trợ đăng ký/hủy đăng ký và tra cứu theo tên/pattern.

**2. Vì sao gọi MBeanServer là điểm thực thi quản trị?** Vì nó nhận các yêu cầu JMX như \`getAttribute\`, \`setAttribute\`, \`invoke\`, kiểm tra/định tuyến rồi thực hiện trên MBean đích.

**3. \`ObjectName\` có duy nhất toàn hệ thống không?** Không. Tính duy nhất được đảm bảo trong một MBeanServer; nhiều JVM hoặc nhiều server độc lập có thể có cùng ObjectName.

**4. Có thể gọi mọi public method của MBean bằng \`invoke\` không?** Không. Chỉ operation được công bố qua giao diện quản trị JMX phù hợp mới là một phần của hợp đồng gọi.

**5. Platform MBeanServer có đồng nghĩa remote JMX đang bật?** Không. Remote access cần connector và cấu hình truy cập riêng.

**6. \`queryNames\` có liệt kê tất cả Spring bean không?** Không. Nó chỉ trả về MBean đã đăng ký trong MBeanServer tương ứng.

**7. Vì sao cần \`finally\` khi hủy đăng ký?** Để giải phóng tên và tài nguyên kể cả khi các thao tác quản trị phát sinh exception.

## 15. Tổng kết

\`MBeanServer\` đảm nhiệm hai vai trò gắn kết: **registry** đảm bảo mỗi MBean có danh tính quản trị và có thể được khám phá; **điểm thực thi** tiếp nhận các lệnh đọc/ghi/gọi operation/sự kiện dựa trên danh tính đó. \`ObjectName\` là khóa định tuyến; metadata JMX xác định những thao tác hợp lệ; connector quyết định cách client truy cập. Trong Spring Framework, \`MBeanExporter\` nối vòng đời Spring bean với MBeanServer, giúp công bố khả năng vận hành có kiểm soát.

### Tài liệu tham khảo

- Java SE — \`javax.management.MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE — \`javax.management.ObjectName\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
- Java SE — \`java.lang.management.ManagementFactory\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html
- Java Management Extensions (JMX) Technology: https://docs.oracle.com/javase/tutorial/jmx/
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html