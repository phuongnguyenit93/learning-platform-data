# ObjectName, domain, key property và định danh MBean

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích tại sao mỗi MBean được đăng ký trong một \`MBeanServer\` cần một định danh \`ObjectName\`.
- Đọc và tạo tên theo dạng \`domain:key=value,key2=value2\`; phân biệt domain với các key property.
- Hiểu \`ObjectName\` biểu diễn một tên cụ thể hay một mẫu dùng để truy vấn.
- Phân biệt tên hiển thị, tên Java class, tên bean Spring và định danh JMX.
- Đăng ký, tìm kiếm, thao tác và hủy đăng ký MBean bằng Java Management Extensions (JMX).
- Tránh lỗi ký tự đặc biệt, thứ tự property và trùng định danh trong ứng dụng.

## 2. Bối cảnh: MBean được nhận diện ở đâu?

JMX (Java Management Extensions) là cơ chế chuẩn của Java để theo dõi và quản trị tài nguyên khi ứng dụng đang chạy. Một tài nguyên có thể là bộ nhớ đệm, hàng đợi, bộ kết nối, bộ đếm hoặc một thành phần nghiệp vụ có trạng thái vận hành.

Một **MBean** cung cấp các thuộc tính có thể đọc/ghi, thao tác có thể gọi và thông báo quản trị. **MBeanServer** là nơi đăng ký các MBean để công cụ quản trị truy cập được chúng. Khi đăng ký, mỗi MBean có một **\`javax.management.ObjectName\`** làm khóa định danh trong phạm vi MBeanServer đó.

Ví dụ, một ứng dụng có hai cache:

\`\`\`text
com.example.app:type=Cache,name=products
com.example.app:type=Cache,name=customers
\`\`\`

Cả hai có cùng domain và loại tài nguyên, nhưng khác giá trị \`name\`. Công cụ như JConsole có thể liệt kê hai MBean riêng biệt, đọc \`Size\`, gọi \`clear()\`, v.v. nếu các thuộc tính/thao tác ấy thực sự được MBean cung cấp.

**Lưu ý:** \`ObjectName\` không tự tạo thuộc tính, operation hay quyền truy cập. Nó chỉ là định danh để server tra cứu đúng MBean. Những khả năng quản trị có sẵn do interface/metadata MBean định nghĩa.

## 3. Cấu trúc một ObjectName

Dạng khái quát:

\`\`\`text
<domain>:<key1>=<value1>,<key2>=<value2>,...
\`\`\`

Ví dụ:

\`\`\`text
com.example.shop:type=Cache,name=productCache,instance=primary
\`\`\`

| Thành phần | Giá trị trong ví dụ | Ý nghĩa |
|---|---|---|
| Domain | \`com.example.shop\` | Không gian tên để nhóm tài nguyên |
| Key property \`type\` | \`Cache\` | Phân loại MBean |
| Key property \`name\` | \`productCache\` | Tên tài nguyên cụ thể |
| Key property \`instance\` | \`primary\` | Phân biệt một instance khi cần |

Tên domain thường theo quy ước reverse DNS (\`com.example.shop\`, \`org.acme.orders\`) để giảm va chạm giữa thư viện và ứng dụng, nhưng JMX không bắt buộc domain phải là một Java package hay DNS hợp lệ. Domain thuộc thành phần định danh, không phải hostname, URL hoặc nơi MBean được triển khai.

**Key property** là cặp \`key=value\`. Chúng không nhất thiết tương ứng với field hay thuộc tính JMX của MBean. Ví dụ key \`name=productCache\` chỉ được dùng để định danh; MBean không tự động có attribute \`Name\`.

Một \`ObjectName\` cụ thể bắt buộc có domain, dấu \`:\` và ít nhất một key property. \`ObjectName\` có thể là tên chính xác (để đăng ký hoặc truy cập một MBean) hoặc một pattern (để tìm các MBean khớp điều kiện). Hai loại có vai trò khác nhau.

## 4. Domain: không gian tên logic

Domain giúp phân biệt các MBean đến từ các hệ thống/thư viện khác nhau trong cùng MBeanServer.

\`\`\`text
java.lang:type=Memory
java.lang:type=Threading
com.example.shop:type=Cache,name=products
com.example.shop:type=Queue,name=orders
\`\`\`

- \`java.lang\` là một domain chuẩn thường thấy trong platform MBeanServer.
- \`com.example.shop\` là domain riêng của ứng dụng trong ví dụ.
- Domain có thể trùng nhau giữa nhiều MBean; tập hợp **domain + toàn bộ key property** mới tạo định danh.
- Tên miền JMX không tự bảo đảm cách ly bảo mật hay đa thuê bao. Các quyền truy cập và cơ chế kết nối được quản lý riêng.

Nếu tạo \`ObjectName\` với domain rỗng, MBeanServer có thể áp dụng default domain khi đăng ký. Trong nội dung ứng dụng, nên đặt domain rõ ràng để tên ổn định và dễ tra cứu giữa các môi trường.

Khi nhiều thư viện cùng dùng \`type=Cache,name=default\` trong một server, domain riêng giúp tránh va chạm. Tuy nhiên, domain riêng không giải quyết trường hợp hai instance của chính ứng dụng vẫn dùng cùng tên: cần thêm key phân biệt.

## 5. Key property và tên duy nhất

Các key phổ biến theo quy ước là:

- \`type\`: loại tài nguyên, ví dụ \`Cache\`, \`DataSource\`, \`Worker\`.
- \`name\`: tên logic, ví dụ \`products\`, \`orders\`.
- \`id\`, \`instance\` hoặc \`node\`: định danh instance.
- \`module\`, \`component\`, \`tenant\`: nhóm ứng dụng hoặc phạm vi nghiệp vụ, nếu thực sự cần.

JMX không quy định bắt buộc phải có \`type\` hoặc \`name\`: đó là lựa chọn thiết kế. Không có ý nghĩa đặc biệt cho các key này ở cấp \`ObjectName\`. Hai \`ObjectName\` có cùng domain và cùng *tập hợp* key-value là cùng định danh ngay cả khi thứ tự viết các key khác nhau.

Ví dụ:

\`\`\`text
com.example.shop:type=Cache,name=products
com.example.shop:name=products,type=Cache
\`\`\`

Hai dòng trên đại diện cùng một tên JMX theo so sánh \`ObjectName.equals()\`, vì thứ tự key không tạo định danh mới.

Ngược lại:

\`\`\`text
com.example.shop:type=Cache,name=products
com.example.shop:type=Cache,name=customers
\`\`\`

là hai tên khác nhau vì giá trị key \`name\` khác.

Trong một \`MBeanServer\`, hai MBean không thể cùng đăng ký dưới một \`ObjectName\` cụ thể tại cùng thời điểm. Nếu tên đã tồn tại, \`registerMBean\` ném \`InstanceAlreadyExistsException\`. Tên cùng chuỗi ở hai MBeanServer độc lập không mặc nhiên chỉ đến cùng object; server là một phần của ngữ cảnh tra cứu.

### Thiết kế key ổn định

Nên dùng key đủ để phân biệt những tài nguyên thật sự cần quản trị độc lập. Chẳng hạn mỗi pool cơ sở dữ liệu có \`name\` riêng:

\`\`\`text
com.example.shop:type=ConnectionPool,name=orders
com.example.shop:type=ConnectionPool,name=analytics
\`\`\`

Tránh đưa vào tên một giá trị thay đổi liên tục như kích thước cache, số request hiện tại hoặc timestamp cập nhật. Đổi key đồng nghĩa với đổi định danh; công cụ đang tìm tên cũ có thể không còn truy cập được MBean. Các số đo động nên là JMX attributes.

## 6. Xây dựng ObjectName trong Java

\`ObjectName\` thuộc gói \`javax.management\`, là API JDK; không cần thư viện Spring riêng để tạo tên.

\`\`\`java
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;

public class ObjectNameExample {
    public static void main(String[] args)
            throws MalformedObjectNameException {

        ObjectName cache = new ObjectName(
                "com.example.shop:type=Cache,name=products");

        System.out.println(cache.getDomain());
        // com.example.shop

        System.out.println(cache.getKeyProperty("type"));
        // Cache

        System.out.println(cache.getKeyProperty("name"));
        // products

        System.out.println(cache.isPattern());
        // false

        System.out.println(cache.getCanonicalName());
        // com.example.shop:name=products,type=Cache
    }
}
\`\`\`

\`getCanonicalName()\` biểu diễn các key property ở thứ tự chuẩn hóa theo key. \`toString()\`/\`getKeyPropertyListString()\` có thể giữ thứ tự hiển thị theo dạng đã nhập; không dùng thứ tự trong chuỗi đó để suy ra tên khác nhau. Khi cần so sánh ngữ nghĩa, hãy dùng \`equals()\` hoặc các cấu trúc dữ liệu dựa vào \`ObjectName\`.

Có thể tạo \`ObjectName\` từ \`Hashtable\` các key property nhằm giảm lỗi lắp ghép thủ công:

\`\`\`java
import java.util.Hashtable;
import javax.management.ObjectName;

Hashtable<String, String> props = new Hashtable<>();
props.put("type", "Cache");
props.put("name", "products");

ObjectName name = new ObjectName("com.example.shop", props);
\`\`\`

Cả constructor dạng string và dạng bảng đều cần tuân thủ các quy tắc ký tự của \`ObjectName\`. Đối với giá trị lấy từ người dùng, không nối trực tiếp chúng vào chuỗi nếu chưa xử lý ký tự đặc biệt.

## 7. Ký tự đặc biệt, quote và giá trị động

Ngữ pháp \`ObjectName\` dùng các ký tự như \`:\`, \`,\`, \`=\`, \`*\` và \`?\` cho mục đích cú pháp hoặc wildcard. Giá trị có dấu phẩy, dấu bằng, dấu hai chấm, dấu nháy kép, dấu xuống dòng hay wildcard phải được xử lý đúng nếu bạn muốn lưu giá trị đó như một giá trị dữ liệu nguyên vẹn.

JMX cung cấp \`ObjectName.quote(String)\` để tạo biểu diễn giá trị được trích dẫn; \`ObjectName.unquote(String)\` giải mã một biểu diễn đã quote hợp lệ.

\`\`\`java
import javax.management.ObjectName;

String logicalName = "inventory,west=primary";
String encoded = ObjectName.quote(logicalName);

ObjectName name = new ObjectName(
        "com.example.shop:type=Cache,name=" + encoded);

System.out.println(name.getKeyProperty("name"));
// "inventory,west=primary" (giá trị theo cú pháp đã quote)

System.out.println(ObjectName.unquote(
        name.getKeyProperty("name")));
// inventory,west=primary
\`\`\`

Cần đặc biệt chú ý: \`getKeyProperty("name")\` của tên có giá trị quote trả lại biểu diễn key property có dấu quote, không phải lúc nào cũng là chuỗi dữ liệu đã được unquote. Điều này quan trọng khi ánh xạ hai chiều giữa tên trong hệ thống và tên trong JMX.

**Wildcard trong quote vẫn có thể mang nghĩa pattern.** \`ObjectName.quote\` thoát đúng cú pháp nhưng không phải cơ chế vô hiệu hóa mọi wildcard: ký tự \`*\` và \`?\` thuộc quy tắc pattern của \`ObjectName\`; hãy kiểm tra \`isPattern()\` nếu tên bắt buộc là tên đăng ký cụ thể. Tránh đưa input tùy ý có ký tự wildcard vào tên đăng ký. Nếu cần tên an toàn tuyệt đối cho dữ liệu bất kỳ, có thể mã hóa dữ liệu thành tập ký tự không đặc biệt (ví dụ URL-safe Base64 không padding) rồi lưu giá trị gốc ở attribute của MBean. Đừng cố đăng ký một pattern.

Ví dụ kiểm tra:

\`\`\`java
ObjectName concrete = new ObjectName(
        "com.example.shop:type=Cache,name=products");

if (concrete.isPattern()) {
    throw new IllegalArgumentException(
            "Tên đăng ký MBean phải là ObjectName cụ thể");
}
\`\`\`

### Quy tắc phân biệt hoa thường

Tên JMX có phân biệt chữ hoa và chữ thường:

\`\`\`text
com.example.shop:type=Cache,name=products
com.example.shop:type=cache,name=products
\`\`\`

Đây là hai \`ObjectName\` khác nhau. Hãy thống nhất quy tắc viết \`type\`, \`name\`, domain để truy vấn và dashboard không bỏ sót tài nguyên.

## 8. ObjectName pattern để tìm MBean

\`MBeanServer.queryNames\` cho phép tra cứu các tên khớp một \`ObjectName\` pattern. Ký tự \`*\` đại diện cho chuỗi ký tự bất kỳ, \`?\` đại diện cho một ký tự trong các phần được cho phép. Ngoài value pattern còn có property-list pattern với \`,*\`.

Ví dụ:

\`\`\`text
com.example.shop:type=Cache,*
com.example.shop:type=Cache,name=prod*
com.example.*:type=Cache,*
*:type=Cache,*
\`\`\`

- \`com.example.shop:type=Cache,*\` khớp MBean trong đúng domain và có \`type=Cache\`, kể cả khi có thêm các key property.
- \`com.example.shop:type=Cache,name=prod*\` khớp các tên có key \`name\` bắt đầu bằng \`prod\` và có thể chứa các key bổ sung.
- \`com.example.*:type=Cache,*\` biểu thị domain pattern.
- \`*:type=Cache,*\` truy vấn nhiều domain theo thuộc tính \`type\`.

Sự khác biệt dễ nhầm:

\`\`\`text
com.example.shop:type=Cache
com.example.shop:type=Cache,*
\`\`\`

Tên thứ nhất là một tên **cụ thể** với đúng một key. Tên thứ hai là **property-list pattern** có thể khớp MBean chứa \`type=Cache\` cộng với các key khác. Dùng \`isPropertyListPattern()\`, \`isPropertyValuePattern()\` và \`isDomainPattern()\` để nhận biết loại pattern.

Ví dụ truy vấn:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName query = new ObjectName(
        "com.example.shop:type=Cache,*");

Set<ObjectName> matching = server.queryNames(query, null);

for (ObjectName candidate : matching) {
    System.out.println(candidate.getCanonicalName());
}
\`\`\`

\`null\` ở tham số \`QueryExp\` nghĩa là không bổ sung bộ lọc \`QueryExp\`; vẫn lọc theo \`ObjectName\` đã truyền. Kết quả là một \`Set\`, không nên giả định thứ tự duyệt ổn định. Sắp xếp khi cần hiển thị theo thứ tự xác định.

Không đăng ký MBean dưới \`ObjectName\` là pattern. Pattern chỉ dùng để so khớp/truy vấn.

## 9. Ví dụ hoàn chỉnh: đăng ký và tra cứu Standard MBean

Một Standard MBean được định nghĩa bằng interface đặt tên theo quy ước \`<TênClass>MBean\`, với các getter và operation public, cùng class thực thi tương ứng.

**File \`CacheMetricsMBean.java\`:**

\`\`\`java
public interface CacheMetricsMBean {
    int getEntryCount();
    void clear();
}
\`\`\`

**File \`CacheMetrics.java\`:**

\`\`\`java
public class CacheMetrics implements CacheMetricsMBean {
    private int entryCount = 3;

    @Override
    public int getEntryCount() {
        return entryCount;
    }

    @Override
    public void clear() {
        entryCount = 0;
    }
}
\`\`\`

**File \`JmxRegistrationDemo.java\`:**

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class JmxRegistrationDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
                "com.example.shop:type=Cache,name=products");

        if (server.isRegistered(name)) {
            throw new IllegalStateException(
                    "MBean đã tồn tại: " + name);
        }

        server.registerMBean(new CacheMetrics(), name);

        try {
            Object before =
                    server.getAttribute(name, "EntryCount");
            System.out.println("Trước khi clear: " + before);

            server.invoke(name, "clear",
                    new Object[0], new String[0]);

            Object after =
                    server.getAttribute(name, "EntryCount");
            System.out.println("Sau khi clear: " + after);
        } finally {
            server.unregisterMBean(name);
        }
    }
}
\`\`\`

Kết quả dự kiến:

\`\`\`text
Trước khi clear: 3
Sau khi clear: 0
\`\`\`

Giải thích luồng:

1. \`getPlatformMBeanServer()\` lấy server JMX của JVM đang chạy.
2. \`new ObjectName(...)\` xây dựng định danh cụ thể.
3. \`registerMBean\` ánh xạ định danh tới instance \`CacheMetrics\`.
4. \`getAttribute\` đọc JMX attribute \`EntryCount\`, do \`getEntryCount()\` công bố.
5. \`invoke\` gọi operation \`clear\`, rồi kiểm tra lại thuộc tính.
6. \`unregisterMBean\` hủy đăng ký, giúp tránh định danh còn tồn tại sau vòng đời demo.

\`isRegistered\` trước \`registerMBean\` chỉ để thông báo rõ ràng; nó không tránh được race condition nếu nhiều luồng đăng ký đồng thời. Code ứng dụng thực tế vẫn phải xử lý \`InstanceAlreadyExistsException\` phát sinh từ thao tác đăng ký.

Để chạy demo, đặt ba file cùng thư mục, biên dịch bằng \`javac *.java\` (hoặc lệnh tương đương theo shell), rồi \`java JmxRegistrationDemo\`. Chương trình demo kết thúc ngay, vì vậy khó quan sát nó bằng JConsole. Để quan sát qua GUI, giữ JVM chạy trong khi MBean còn đăng ký.

## 10. Tương tác với Spring Framework

Spring JMX hỗ trợ xuất bean thành MBean thông qua \`MBeanExporter\` hoặc \`@ManagedResource\`/\`@ManagedAttribute\`/\`@ManagedOperation\`, nếu ứng dụng cấu hình cơ chế export phù hợp. Annotation hỗ trợ khai báo một ObjectName trong tên tài nguyên.

Ví dụ minh họa:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.shop:type=Cache,name=products",
    description = "Cache metrics")
public class ProductCacheMonitor {

    private volatile int entryCount;

    @ManagedAttribute
    public int getEntryCount() {
        return entryCount;
    }
}
\`\`\`

\`@ManagedResource\` và \`@ManagedAttribute\` mô tả tài nguyên và attribute; class phải được Spring quản lý và được export thông qua cơ chế JMX thích hợp thì MBean mới xuất hiện trong MBeanServer. Đừng suy luận rằng chỉ thêm annotation vào class bất kỳ sẽ tự động đăng ký MBean.

Cùng một bean Spring có thể có tên trong application context như \`productCacheMonitor\` và tên JMX như \`com.example.shop:type=Cache,name=products\`. Hai tên thuộc **hai namespace khác nhau**. Nếu chuyển hoặc đổi tên bean Spring, tên JMX chưa chắc thay đổi, tùy cấu hình exporter/naming strategy.

Spring có các cơ chế lựa chọn tên khi export và giải quyết collision. Dù dùng Spring Boot hay Spring Framework thuần, nên kiểm tra \`ObjectName\` thực tế trong MBeanServer/JConsole thay vì giả định mọi bean đều được export theo một mẫu tên.

## 11. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| \`MalformedObjectNameException\` | Sai cú pháp \`domain:key=value\`, ký tự đặc biệt chưa encode hoặc key không hợp lệ | Dùng constructor đúng, quote/encode dữ liệu, kiểm tra pattern |
| \`InstanceAlreadyExistsException\` | Đã có MBean cùng ObjectName trong cùng server | Thống nhất naming convention, thêm key \`instance\` cần thiết, quản lý vòng đời |
| \`InstanceNotFoundException\` | Tra cứu tên không tồn tại hoặc MBean đã bị unregister | Kiểm tra tên chính xác và server đích, đối chiếu domain/key/case |
| Query \`type=Cache\` không thấy kết quả | Query không có \`,*\` trong khi MBean có key khác | Dùng \`type=Cache,*\` nếu muốn chấp nhận các key bổ sung |
| Có MBean nhưng thiếu attribute | ObjectName đúng nhưng MBean interface/metadata không expose attribute đó | Kiểm tra Standard MBean/MXBean interface hoặc annotation/exporter |
| Dashboard mất dữ liệu sau deploy | Key chứa ID thay đổi không cần thiết hoặc naming convention đổi | Dùng tên ổn định cho tài nguyên logic, tách metadata động thành attribute |
| Trùng tên khi chạy nhiều instance | Cùng domain và key-value trong một MBeanServer | Thêm key chỉ instance khi các đối tượng cùng tồn tại trong server |
| Truy vấn trả kết quả ngoài ý muốn | Dùng wildcard rộng hoặc nhập giá trị pattern | Giới hạn domain/key và kiểm tra \`isPattern()\` |

Một số ngoại lệ khác liên quan interface MBean không hợp lệ, kiểm soát truy cập hoặc kết nối JMX từ xa. Phân biệt lỗi **định danh** với lỗi **cấu hình export / networking / quyền truy cập** giúp chẩn đoán nhanh hơn.

## 12. Thực hành: kiểm chứng định danh và pattern

### Bài tập A — So sánh ObjectName

Dự đoán kết quả:

\`\`\`java
ObjectName a = new ObjectName(
        "com.example.shop:type=Cache,name=products");
ObjectName b = new ObjectName(
        "com.example.shop:name=products,type=Cache");
ObjectName c = new ObjectName(
        "com.example.shop:type=Cache,name=customers");

System.out.println(a.equals(b));
System.out.println(a.equals(c));
\`\`\`

**Đáp án:** \`true\` rồi \`false\`. Thứ tự key không phân biệt tên; giá trị \`name\` thì có.

### Bài tập B — Truy vấn có key bổ sung

Giả sử MBean được đăng ký với tên:

\`\`\`text
com.example.shop:type=Cache,name=products,instance=a
com.example.shop:type=Cache,name=products,instance=b
com.example.shop:type=Queue,name=orders
\`\`\`

Chọn pattern để tìm cả hai cache:

\`\`\`text
com.example.shop:type=Cache,name=products,*
\`\`\`

Pattern có \`,*\` khớp tên chứa thêm \`instance\`. Tên \`com.example.shop:type=Cache,name=products\` (không có wildcard) sẽ không khớp hai tên đang có thêm key.

### Bài tập C — Tạo ObjectName với dữ liệu đặc biệt

Cho tên logic \`inventory,west=primary\`. Hãy dùng \`ObjectName.quote\` để tạo biểu diễn, gọi \`ObjectName.unquote\` để thu lại đúng dữ liệu, và kiểm tra \`isPattern()\`. Sau đó thử dữ liệu chứa \`*\` hoặc \`?\` để thấy vì sao phải phân biệt quote cú pháp với wildcard pattern.

### Bài tập D — Vòng đời đăng ký

Chạy demo \`JmxRegistrationDemo\`, quan sát:

- Trước đăng ký, \`server.isRegistered(name)\` trả \`false\`.
- Sau đăng ký, trả \`true\`; gọi \`getAttribute\` và \`invoke\` theo tên.
- Sau hủy đăng ký, trả \`false\`; truy cập attribute bằng tên cũ sẽ không tìm thấy instance.

## 13. Ghi nhớ

- \`ObjectName\` là định danh JMX cho MBean trong một **MBeanServer cụ thể**.
- Cú pháp gồm domain và key property: \`domain:key=value,...\`.
- Domain nhóm namespace; tập hợp key property phân biệt tài nguyên. Thứ tự key không ảnh hưởng tính bằng nhau; chữ hoa/chữ thường có ảnh hưởng.
- \`getCanonicalName()\` chuẩn hóa biểu diễn key; \`equals()\` so sánh định danh.
- \`ObjectName\` cụ thể dùng đăng ký, đọc attribute và invoke operation; \`ObjectName\` pattern dùng query.
- Giá trị nhận từ bên ngoài cần xử lý ký tự đặc biệt và wildcard. \`quote\` giải quyết cú pháp trích dẫn nhưng cần kiểm tra \`isPattern()\` trước khi đăng ký.
- Tên bean Spring, Java class và tên JMX độc lập về khái niệm; export và naming strategy quyết định mối liên hệ thực tế.
- Chọn naming convention ổn định, có chủ đích, dễ truy vấn và không lẫn dữ liệu vận hành thay đổi nhanh vào ObjectName.

## 14. Tài liệu tham khảo

- Java SE API — \`javax.management.ObjectName\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
- Java SE API — \`javax.management.MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Oracle JMX Technology Tutorial: https://docs.oracle.com/javase/tutorial/jmx/
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
