# Cấu trúc \`domain:key=value\` của ObjectName trong JMX

## 1. ObjectName dùng để làm gì?

Trong Java Management Extensions (JMX), mỗi MBean được đăng ký trong một \`MBeanServer\` bằng một **\`javax.management.ObjectName\`**. ObjectName là định danh có cấu trúc giúp công cụ quản trị và chương trình Java tìm MBean, đọc/ghi thuộc tính, gọi operation và nhận notification.

Một ObjectName thường có dạng:

\`\`\`text
domain:key1=value1,key2=value2,...
\`\`\`

Ví dụ:

\`\`\`text
java.lang:type=Memory
java.lang:type=Threading
demo.app:type=Cache,name=Primary
demo.app:type=Worker,name=invoice,instance=2
\`\`\`

**Cách đọc:** phần trước dấu hai chấm là **domain**; phía sau là một hoặc nhiều **key property** viết dưới dạng \`key=value\`, ngăn cách bằng dấu phẩy. Chính cặp \`domain + tập key properties\` xác định tên của MBean trong một MBeanServer. Tên Java class hoặc tên Spring bean không tự động đồng nhất với ObjectName.

Với ví dụ:

\`\`\`text
demo.app:type=Cache,name=Primary
\`\`\`

- \`demo.app\`: domain, tức không gian tên logic.
- \`type=Cache\`: key property chỉ loại tài nguyên được quản lý.
- \`name=Primary\`: key property phân biệt một cache cụ thể.
- Toàn bộ chuỗi: ObjectName của MBean; hai property \`type\` và \`name\` cùng góp phần xác định danh tính.

Không có quy tắc bắt buộc rằng mọi MBean phải có key \`type\` hoặc \`name\`. Đó là các quy ước phổ biến, không phải hai trường đặc biệt được JMX bắt buộc. Một ObjectName hợp lệ chỉ cần tuân thủ cú pháp của \`ObjectName\` và chứa danh sách key property hợp lệ.

## 2. Cấu trúc ba phần nhìn từ trái sang phải

### 2.1. Domain: namespace logic

Domain đứng trước dấu \`:\`:

\`\`\`text
java.lang:type=Memory
^^^^^^^^^
 domain
\`\`\`

Domain thường diễn tả nhóm MBean hoặc ứng dụng sở hữu chúng. Ví dụ \`java.lang\` là domain có các platform MBean của JVM; ứng dụng có thể chọn \`com.example.orders\` hoặc \`demo.app\`. Domain **không** phải host, IP, port hay URL của JMX server. Một server chứa MBean thuộc nhiều domain, và hai server khác nhau có thể có cùng ObjectName.

Trong một **tên chính xác** (không phải pattern), domain không được chứa các ký tự được dành riêng cho cú pháp như dấu \`:\`, \`*\`, \`?\` hoặc xuống dòng; dấu \`*\` và \`?\` có thể dùng ở vị trí thích hợp khi muốn tạo **domain pattern**. Domain rỗng cũng được parser cho phép trong một số dạng ObjectName; khi dùng với MBeanServer, domain mặc định của server có thể được áp dụng. Trong ứng dụng thật, nên khai báo domain rõ ràng để tránh hiểu nhầm.

Một domain nên có tên dễ nhận diện và ít thay đổi qua các phiên bản ứng dụng, ví dụ:

\`\`\`text
com.example.orders:type=Queue,name=Pending
com.example.orders:type=Cache,name=Product
\`\`\`

### 2.2. Dấu hai chấm \`:\`: ranh giới

Dấu \`:\` phân cách domain và danh sách key properties. Ví dụ:

\`\`\`text
com.example.orders : type=Queue,name=Pending
                   ^
                 phân cách
\`\`\`

Khoảng trắng trong ví dụ minh họa để dễ nhìn, không nên tự chèn khoảng trắng khi tạo tên. Parser không hiểu hai dấu \`:\` như hai cấp namespace. Nếu cần phân cấp ý nghĩa trong domain, có thể dùng dấu chấm \`.\` theo quy ước tổ chức.

### 2.3. Key properties: các cặp key=value

Bên phải dấu hai chấm là danh sách các key property:

\`\`\`text
demo.app:type=Cache,name=Primary,instance=2
         |---------| |----------| |--------|
          property1   property2   property3
\`\`\`

Mỗi key chỉ xuất hiện **một lần** trong một ObjectName; lặp cùng một key là không hợp lệ. Key không được rỗng và không thể chứa các ký tự cú pháp \`:\`, \`,\`, \`=\`, \`*\`, \`?\` hoặc xuống dòng. Key có phân biệt chữ hoa và chữ thường: \`type\` khác \`Type\`; \`name\` khác \`Name\`.

Value cũng phân biệt chữ hoa và chữ thường: \`Primary\` khác \`primary\`. Trong tên chính xác, giá trị đơn giản thường không cần dấu ngoặc kép:

\`\`\`text
demo.app:type=Cache,name=Primary
\`\`\`

Một ObjectName có thể có nhiều key tùy bài toán, nhưng key phải đại diện cho định danh ổn định, không nên đưa các số liệu dao động liên tục như \`requestsPerSecond\` vào tên MBean. Những số liệu đó nên được expose dưới dạng **attribute** của MBean.

## 3. Danh tính không phụ thuộc vào thứ tự key properties

Hai chuỗi này chỉ cùng một ObjectName:

\`\`\`text
demo.app:type=Cache,name=Primary
demo.app:name=Primary,type=Cache
\`\`\`

JMX coi key property list như tập ánh xạ key → value khi xác định tính bằng nhau. \`ObjectName.equals()\` so sánh danh tính đã chuẩn hóa; \`getCanonicalName()\` trả về biểu diễn có thứ tự key ổn định.

\`\`\`java
import javax.management.ObjectName;

public class CanonicalObjectNameExample {
    public static void main(String[] args) throws Exception {
        ObjectName a =
            new ObjectName("demo.app:type=Cache,name=Primary");
        ObjectName b =
            new ObjectName("demo.app:name=Primary,type=Cache");

        System.out.println(a.equals(b)); // true
        System.out.println(a.getCanonicalName());
        // demo.app:name=Primary,type=Cache

        System.out.println(a.getDomain()); // demo.app
        System.out.println(a.getKeyProperty("type")); // Cache
        System.out.println(a.getKeyProperty("name")); // Primary
    }
}
\`\`\`

Vì vậy, không nên so sánh hai chuỗi \`ObjectName.toString()\` để quyết định chúng có cùng MBean hay không; hãy tạo \`ObjectName\` và dùng \`equals()\`. Khi log hoặc lưu khóa để đối chiếu, \`getCanonicalName()\` thường hữu ích.

## 4. Quy tắc về dấu phẩy, dấu bằng và dấu ngoặc kép trong value

Value có thể chứa các ký tự đặc biệt, nhưng khi đó phải dùng đúng cú pháp quoted value. Ví dụ tên ứng dụng chứa dấu phẩy:

\`\`\`text
demo.app:type=Service,name="order,processor"
\`\`\`

Nếu viết:

\`\`\`text
demo.app:type=Service,name=order,processor
\`\`\`

thì dấu phẩy bị hiểu là dấu phân cách property; phần \`processor\` không có \`=\` nên chuỗi không hợp lệ.

Trong Java, nên dùng \`ObjectName.quote(value)\` khi một giá trị tự do có thể chứa ký tự đặc biệt:

\`\`\`java
import javax.management.ObjectName;

String serviceName = "order,processor";
String quotedName = ObjectName.quote(serviceName);

ObjectName objectName =
    new ObjectName("demo.app:type=Service,name=" + quotedName);

System.out.println(objectName);
// demo.app:type=Service,name="order,processor"
\`\`\`

Các ký tự đặc biệt đáng lưu ý trong value gồm \`,\`, \`=\`, \`:\`, \`"\`, \`*\`, \`?\`, dấu gạch chéo ngược và xuống dòng. Khi quote, JMX có quy tắc escape riêng; \`ObjectName.quote\` giúp tạo quoted value đúng cú pháp cho dữ liệu dạng literal. Đừng tự chế hàm escape chỉ thay dấu ngoặc kép, và đừng tự nối dữ liệu chưa kiểm soát vào domain hoặc key.

Một ví dụ khác:

\`\`\`java
String fileLabel = "cache=\"hot\",region=west";
ObjectName name = new ObjectName(
    "demo.app:type=Resource,label=" + ObjectName.quote(fileLabel)
);
\`\`\`

Lưu ý: **dấu ngoặc kép là một phần cú pháp ObjectName**. Khi đọc property bằng \`getKeyProperty\`, giá trị quoted có thể còn bao gồm dấu ngoặc kép và escape theo representation của ObjectName. Nếu cần giá trị Java gốc, dùng \`ObjectName.unquote(...)\` cho chuỗi đã quote hợp lệ:

\`\`\`java
String raw = ObjectName.unquote(name.getKeyProperty("label"));
System.out.println(raw); // cache="hot",region=west
\`\`\`

Không tự động gọi \`unquote\` lên một property value không ở dạng quoted.

## 5. Exact ObjectName và ObjectName pattern

ObjectName có hai mục đích quan trọng:

1. **Exact name:** chỉ định một MBean cụ thể.
2. **Pattern:** mô tả một tập ObjectName để truy vấn.

Ví dụ exact name:

\`\`\`text
demo.app:type=Cache,name=Primary
\`\`\`

Ví dụ pattern:

\`\`\`text
demo.app:*
demo.app:type=Cache,*
demo.app:type=Cache,name=*
*:type=Cache,*
\`\`\`

Các ký hiệu thường gặp:

| Cú pháp | Ý nghĩa |
| --- | --- |
| \`*\` trong domain | Khớp với chuỗi domain theo wildcard |
| \`?\` trong domain | Khớp một ký tự domain |
| \`name=foo*\` | Mẫu property value bắt đầu bằng \`foo\` |
| \`name=foo?\` | Mẫu property value bắt đầu \`foo\` và thêm đúng một ký tự |
| \`,*\` ở cuối danh sách key properties | Cho phép các property bổ sung ngoài những key đã nêu |
| \`domain:*\` | Khớp mọi danh sách property trong domain tương ứng |

Ví dụ:

\`\`\`text
demo.app:type=Cache,*
\`\`\`

khớp với những tên như:

\`\`\`text
demo.app:type=Cache,name=Primary
demo.app:type=Cache,name=Secondary,instance=2
\`\`\`

vì chúng đều có \`type=Cache\` và được phép có property khác. Ngược lại, pattern:

\`\`\`text
demo.app:type=Cache,name=*
\`\`\`

có ý nghĩa khác: ở đây có **value pattern** cho \`name\`, nhưng nếu thiếu \`,*\` thì danh sách key trong đối tượng khớp phải tương ứng với những key đã nêu; một MBean có thêm \`instance=2\` có thể không khớp.

Đây là điểm dễ nhầm: **wildcard trong value** và **wildcard cho danh sách key properties** là hai cơ chế riêng.

\`\`\`java
import javax.management.ObjectName;

ObjectName exact =
    new ObjectName("demo.app:type=Cache,name=Primary");
ObjectName byType =
    new ObjectName("demo.app:type=Cache,*");
ObjectName byNamePattern =
    new ObjectName("demo.app:type=Cache,name=Pri*");

System.out.println(exact.isPattern()); // false
System.out.println(byType.isPattern()); // true
System.out.println(byType.isPropertyListPattern()); // true
System.out.println(byNamePattern.isPropertyValuePattern()); // true
\`\`\`

ObjectName pattern được dùng cho **truy vấn**, chẳng hạn \`MBeanServer.queryNames(pattern, null)\`. Không đăng ký MBean với ObjectName pattern: mỗi MBean được đăng ký bằng một **tên chính xác**.

## 6. Phân biệt ký tự wildcard literal và wildcard của pattern

Khi một giá trị thực sự chứa \`*\` hoặc \`?\`, ứng dụng cần mô tả chúng là dữ liệu, không phải điều kiện tìm kiếm. Việc value được đặt trong dấu ngoặc kép **không tự bảo đảm** mọi ký tự wildcard mất ý nghĩa pattern: ObjectName có quy tắc escape riêng cho dấu \`*\` và \`?\`. Hãy dùng API \`ObjectName.quote(value)\`, vì phương thức này escape wildcard khi cần.

\`\`\`java
String logicalName = "batch*special";
ObjectName literalName = new ObjectName(
    "demo.app:type=Job,name=" + ObjectName.quote(logicalName)
);

System.out.println(literalName.isPattern()); // false
\`\`\`

Ngược lại, nếu mục tiêu là tìm tên bắt đầu bằng \`batch\`, chủ động tạo một pattern:

\`\`\`java
ObjectName pattern =
    new ObjectName("demo.app:type=Job,name=batch*,*");

System.out.println(pattern.isPattern()); // true
\`\`\`

Điều này khác với việc dùng \`ObjectName.quote("batch*")\`: hàm quote diễn tả chuỗi literal có dấu sao. Lựa chọn đúng phụ thuộc vào việc bạn muốn **định danh một MBean có tên chứa ký tự đặc biệt** hay **tìm nhiều MBean bằng wildcard**.

## 7. Tạo ObjectName an toàn bằng Java API

Với tên tĩnh, cách dễ đọc nhất là truyền nguyên chuỗi vào constructor:

\`\`\`java
ObjectName name =
    new ObjectName("com.example.orders:type=Queue,name=Pending");
\`\`\`

Với các key/value động, có thể dùng constructor \`ObjectName(String domain, Hashtable<String,String> table)\`:

\`\`\`java
import java.util.Hashtable;
import javax.management.ObjectName;

Hashtable<String, String> properties = new Hashtable<>();
properties.put("type", "Queue");
properties.put("name", "Pending");

ObjectName name =
    new ObjectName("com.example.orders", properties);
\`\`\`

Constructor này tránh việc tự nối dấu phẩy và dấu bằng cho các property đơn giản. Khi giá trị có ký tự cần quote, vẫn phải bảo đảm value được biểu diễn theo cú pháp ObjectName phù hợp; constructor không tự biến mọi chuỗi không hợp lệ thành giá trị literal an toàn.

Ví dụ một hàm tạo tên với phần name bất kỳ:

\`\`\`java
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;

public final class JmxNames {
    private JmxNames() {}

    public static ObjectName queue(String queueName)
            throws MalformedObjectNameException {
        return new ObjectName(
            "com.example.orders:type=Queue,name="
            + ObjectName.quote(queueName)
        );
    }
}
\`\`\`

Với \`queue("priority,west")\`, tên trả về sẽ chứa value \`"priority,west"\`, nhờ đó không bị tách nhầm thành hai properties.

**Lưu ý về quy ước:** một khi quyết định \`type\`, \`name\`, \`instance\` mang ý nghĩa gì, hãy dùng nhất quán giữa các service và các lần deployment. Đổi key hoặc value làm thay đổi ObjectName, từ đó có thể làm hỏng dashboard hoặc client đang tham chiếu tên cũ.

## 8. Đăng ký và tra cứu MBean bằng ObjectName

Đây là ví dụ sử dụng một platform MBean sẵn có để tra cứu, không cần viết MBean mới:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class ObjectNameLookupDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName exact =
            new ObjectName("java.lang:type=Memory");

        System.out.println(server.isRegistered(exact)); // true

        ObjectName pattern =
            new ObjectName("java.lang:type=GarbageCollector,*");

        Set<ObjectName> names = server.queryNames(pattern, null);

        names.stream()
            .map(ObjectName::getCanonicalName)
            .sorted()
            .forEach(System.out::println);
    }
}
\`\`\`

Trong ví dụ:

- \`isRegistered(exact)\` kiểm tra tên chính xác đã có trên MBeanServer hay chưa.
- \`queryNames(pattern, null)\` trả về tập tên khớp với pattern và đang được đăng ký.
- \`getCanonicalName()\` giúp log ở thứ tự key ổn định; \`sorted()\` ổn định thứ tự hiển thị vì \`Set\` không cam kết thứ tự.
- Kết quả garbage collector phụ thuộc JVM, cấu hình GC và runtime; không nên hard-code tên collector.

Muốn đọc một attribute sau khi tra cứu tên cụ thể:

\`\`\`java
ObjectName memory =
    new ObjectName("java.lang:type=Memory");

Object heapUsage =
    server.getAttribute(memory, "HeapMemoryUsage");

System.out.println(heapUsage);
\`\`\`

Nếu ObjectName không được đăng ký, \`getAttribute\` có thể ném \`InstanceNotFoundException\`. Nếu MBean không công bố attribute đã yêu cầu, lời gọi có thể ném \`AttributeNotFoundException\`. Cần kiểm tra \`getMBeanInfo\` khi không chắc giao diện quản trị của MBean.

## 9. Spring Framework sử dụng ObjectName như thế nào?

Spring Framework tích hợp với JMX qua \`MBeanExporter\`, annotation quản trị và các chiến lược đặt tên. ObjectName **vẫn dùng đúng cú pháp JMX chuẩn**.

Ví dụ expose một Spring bean:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=Pending",
    description = "Số lượng công việc chờ xử lý"
)
public class PendingQueueMonitor {
    @ManagedAttribute
    public int getPendingCount() {
        return 12; // Thay bằng dữ liệu thật.
    }
}
\`\`\`

Kích hoạt annotation export:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {}
\`\`\`

Spring đọc metadata, tạo hoặc thích ứng MBean, rồi đăng ký với MBeanServer. Công cụ JMX vẫn truy cập bằng:

\`\`\`text
com.example.orders:type=Queue,name=Pending
\`\`\`

Nếu không đặt ObjectName tĩnh qua annotation, Spring có thể dùng \`ObjectNamingStrategy\` để sinh tên dựa trên thông tin bean/metadata. Ví dụ \`MetadataNamingStrategy\` dùng metadata quản trị; \`KeyNamingStrategy\` dùng ánh xạ tên đã cấu hình. Dù sinh tên bằng chiến lược nào, kết quả cuối cùng vẫn là một \`ObjectName\` hợp lệ của JMX.

Một số quy tắc khi thiết kế ObjectName trong ứng dụng Spring:

1. Tách **Spring bean name** khỏi **JMX ObjectName**: hai loại tên phục vụ hai registry khác nhau.
2. Dùng domain và key properties rõ nghĩa, ví dụ \`com.example.orders:type=Queue,name=Pending\`.
3. Khi deploy nhiều instance vào cùng MBeanServer, bảo đảm ObjectName không trùng nhau, chẳng hạn thêm \`instance=...\` ổn định.
4. Đừng dùng giá trị bí mật, token, password hoặc dữ liệu cá nhân làm key property: ObjectName dễ xuất hiện trong công cụ giám sát và log.
5. Đừng dùng ObjectName để diễn đạt các metric thay đổi liên tục; metrics là thuộc tính hoặc nguồn observability tương ứng.

## 10. Những lỗi cú pháp và lỗi mô hình thường gặp

| Trường hợp | Vì sao có vấn đề | Cách xử lý |
| --- | --- | --- |
| \`demo.app:type=Cache,name=Primary\` | Tên chính xác hợp lệ | Dùng khi biết MBean cụ thể |
| \`demo.app:type=Cache,name=Primary,name=Other\` | Key \`name\` bị lặp | Đổi thành các key khác nhau hoặc loại phần trùng |
| \`demo.app:type=Cache,name=order,processor\` | \`processor\` thiếu \`=...\` | Quote toàn bộ value chứa dấu phẩy |
| \`demo.app:type=Cache,name=order:processor\` | Dấu \`:\` xuất hiện trong value không quote | Dùng \`ObjectName.quote\` |
| \`demo.app:type=Cache,*\` | Là pattern, không phải tên đăng ký cụ thể | Chỉ dùng để query |
| \`demo.app:type=Cache,name=Primary\` và \`demo.app:name=Primary,type=Cache\` | Hai chuỗi khác thứ tự nhưng cùng định danh | So sánh bằng \`ObjectName.equals()\` |
| \`demo.app:type=cache\` và \`demo.app:type=Cache\` | Value phân biệt chữ hoa/thường | Thống nhất quy tắc đặt tên |
| \`demo.app:Name=Primary\` và \`demo.app:name=Primary\` | Key phân biệt chữ hoa/thường | Thống nhất tên key |
| \`demo.app:type=Cache,name=Primary\` trong hai JVM | Có thể là hai MBean khác nhau trên hai server | Xác định đúng kết nối MBeanServer |

Các phương thức hữu ích để chẩn đoán:

\`\`\`java
ObjectName name =
    new ObjectName("demo.app:type=Cache,name=Primary");

System.out.println(name.getDomain());
System.out.println(name.getKeyPropertyList());
System.out.println(name.getKeyProperty("type"));
System.out.println(name.getCanonicalName());
System.out.println(name.isPattern());
System.out.println(name.isDomainPattern());
System.out.println(name.isPropertyPattern());
\`\`\`

Khi gặp \`MalformedObjectNameException\`, hãy kiểm tra ranh giới \`domain:properties\`, key trùng, ký tự đặc biệt trong value và việc quote/escape. Khi tên hợp lệ nhưng không tìm thấy MBean, nguyên nhân thường liên quan server kết nối, tên đăng ký thực tế hoặc vòng đời MBean, không nhất thiết là lỗi cú pháp.

## 11. Mô hình tư duy ngắn gọn

\`\`\`text
ObjectName = domain : key=value [, key=value ...]
             |          |
             |          +-- Những thuộc tính ĐỊNH DANH MBean
             +------------- Namespace logic

Ví dụ:
com.example.orders:type=Queue,name=Pending,instance=1
|----------------| |--------| |----------| |--------|
      domain       key/value   key/value   key/value

ObjectName exact  -> registerMBean / isRegistered / getAttribute / invoke
ObjectName pattern -> queryNames / queryMBeans
MBeanServer        -> registry lưu các ObjectName và MBean tương ứng
\`\`\`

**Điều cần nhớ:** ObjectName là tên có cấu trúc và phân biệt chữ hoa/thường; domain và **toàn bộ tập key/value** xác định MBean; thứ tự key không thay đổi danh tính; value có ký tự đặc biệt phải quote/escape đúng; wildcard tạo pattern phục vụ truy vấn. Spring giúp xuất bản và đặt tên MBean tiện hơn, nhưng cú pháp \`domain:key=value\` vẫn hoàn toàn thuộc chuẩn JMX.
