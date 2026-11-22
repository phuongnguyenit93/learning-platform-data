# ObjectName: tên thuộc tính, giá trị thuộc tính và ký tự cần escape

## 1. ObjectName dùng để làm gì?

Trong Java Management Extensions (JMX), \`javax.management.ObjectName\` định danh một MBean bên trong một \`MBeanServer\`. Khi đăng ký, đọc attribute, gọi operation hoặc tìm kiếm MBean, ứng dụng dùng \`ObjectName\` thay vì một chuỗi tên tùy ý.

Một tên có cấu trúc:

\`\`\`text
domain:key1=value1,key2=value2,...
\`\`\`

Ví dụ:

\`\`\`text
com.example.orders:type=Cache,name=Products,region=asia
\`\`\`

Ở đây \`com.example.orders\` là **domain**; \`type\`, \`name\`, \`region\` là **property keys** (tên thuộc tính trong key-property list), còn \`Cache\`, \`Products\`, \`asia\` là **property values**. Những key-property này tạo danh tính cho MBean. Chúng **khác với MBean attributes** được đọc bằng \`MBeanServer.getAttribute(name, "Size")\`: \`name=Products\` nằm trong định danh, còn \`Size\` là một thuộc tính quản trị của MBean.

Cần phân biệt ba khái niệm:

1. **Domain**: vùng tên trước dấu \`:\`.
2. **Key properties**: cặp \`key=value\` sau dấu \`:\`, phân cách bằng dấu phẩy.
3. **Pattern**: một \`ObjectName\` dùng dấu đại diện để truy vấn nhiều MBean, không phải tên cụ thể dùng để đăng ký.

## 2. Cú pháp và quy tắc cơ bản

\`\`\`text
domain:key=value[,key=value...]
\`\`\`

- Domain có thể dùng tên package đảo ngược, chẳng hạn \`com.example.app\`, để tránh trùng.
- Mỗi property key phải có tên hợp lệ, không được trống và không được lặp trong cùng một \`ObjectName\`.
- Property value có thể là giá trị **không trích dẫn** hoặc **được bao bởi dấu nháy kép**. Dấu nháy kép có ý nghĩa cú pháp; khi hiển thị toàn bộ tên, chúng vẫn được giữ trong chuỗi biểu diễn của value.
- Với một tên cụ thể, các ký tự đặc biệt phải được xử lý sao cho \`ObjectName\` không trở thành pattern ngoài ý muốn.
- Thứ tự các cặp key-property trong chuỗi đầu vào không xác định danh tính. Hai tên có cùng domain và cùng tập key/value được coi là cùng \`ObjectName\`, dù thứ tự cặp khác nhau.

Ví dụ:

\`\`\`java
import javax.management.ObjectName;

ObjectName first =
    new ObjectName("com.example:type=Cache,name=Products");
ObjectName second =
    new ObjectName("com.example:name=Products,type=Cache");

System.out.println(first.equals(second)); // true
System.out.println(first.getCanonicalName());
// com.example:name=Products,type=Cache
\`\`\`

\`getCanonicalName()\` sắp các key properties theo thứ tự canonical. Khi lưu tên để đối chiếu, ghi log hoặc khử trùng lặp, dùng \`ObjectName\` hoặc canonical name đáng tin cậy hơn so sánh chuỗi thô.

## 3. Tên property key: có gì hợp lệ?

Key đứng bên trái dấu \`=\`. Nó phải là một tên không rỗng và không chứa những ký tự cú pháp dành riêng như:

\`\`\`text
,  =  :  *  ?
\`\`\`

Các ký tự xuống dòng và nháy kép cũng không hợp lệ trong property key. Dấu cách có thể xuất hiện theo cú pháp, nhưng nên dùng các key ngắn, ổn định, dễ đọc, không có khoảng trắng, ví dụ \`type\`, \`name\`, \`component\`, \`tenant\`, \`instance\`.

Ví dụ tên rõ ràng:

\`\`\`text
com.example:type=Worker,name=Import,instance=one
\`\`\`

Tránh sử dụng trực tiếp tên do người dùng nhập làm key. Nếu cần một dimension động như mã tenant, để tên key cố định (\`tenant\`) và xử lý mã tenant như **value** sau khi chuẩn hóa/quote.

Các key như \`type\` hoặc \`name\` là quy ước phổ biến, không phải trường bắt buộc mang ý nghĩa đặc biệt của JMX. Bạn có thể dùng \`service\`, \`shard\`, \`region\`, \`pool\` miễn tên hợp lệ và nhất quán.

## 4. Giá trị chưa quote và giá trị đã quote

Một property value không quote thường thích hợp với giá trị đơn giản:

\`\`\`text
com.example:type=Queue,name=jobs
com.example:type=Queue,name=jobs-prod
com.example:type=Queue,name=jobs_01
\`\`\`

Những ký tự như dấu phẩy \`,\`, dấu bằng \`=\`, dấu hai chấm \`:\` hoặc dấu nháy kép \`"\` không thể được đưa tùy tiện vào giá trị không quote; chúng có thể khiến việc parse bị lỗi hoặc khiến parser diễn giải sang cấu trúc khác. Dấu \`*\` và \`?\` đặc biệt nguy hiểm vì chúng đại diện wildcard trong các pattern.

Với giá trị chứa ký tự đặc biệt, sử dụng dạng quoted:

\`\`\`text
com.example:type=Queue,name="jobs,urgent"
com.example:type=Queue,name="region=apac"
com.example:type=Queue,name="https://internal.example"
\`\`\`

Dấu nháy kép ngoài cùng là cú pháp của value. Java có API \`ObjectName.quote(String)\` để tạo value an toàn từ dữ liệu động, thay vì tự thay thế ký tự.

\`\`\`java
import javax.management.ObjectName;

String displayName = "orders,priority=high";
String safeValue = ObjectName.quote(displayName);

ObjectName objectName = new ObjectName(
    "com.example:type=Queue,name=" + safeValue
);

System.out.println(objectName.getKeyProperty("name"));
// "orders,priority=high" (dạng quoted)
System.out.println(
    ObjectName.unquote(objectName.getKeyProperty("name"))
);
// orders,priority=high
\`\`\`

**Điểm dễ nhầm:** \`getKeyProperty("name")\` có thể trả lại value **kèm dấu nháy kép và các escape**, không tự bỏ quote. Nếu muốn chuỗi gốc đã quote, dùng \`ObjectName.unquote(...)\` đúng trường hợp. \`unquote\` mong đợi một chuỗi quoted hợp lệ; không gọi tùy tiện cho mọi unquoted value.

## 5. Các ký tự escape trong giá trị quoted

Trong quoted value, backslash \`\\\` là escape character. Cách biểu diễn quan trọng:

| Ký tự trong dữ liệu | Biểu diễn bên trong quoted ObjectName value | Ghi chú |
| --- | --- | --- |
| Dấu nháy kép \`"\` | \`\"\` | Không kết thúc quoted value |
| Backslash \`\\\` | \`\\\` | Giữ dấu gạch chéo ngược trong dữ liệu |
| Xuống dòng (newline) | \`\n\` | Escape newline trong value |
| Dấu \`*\` | \`\\*\` | Dấu sao literal, không biến thành wildcard |
| Dấu \`?\` | \`\\?\` | Dấu hỏi literal, không biến thành wildcard |
| Dấu phẩy \`,\` | Để nguyên giữa dấu nháy kép | Không bị xem là dấu ngăn key-property |
| Dấu bằng \`=\` | Để nguyên giữa dấu nháy kép | Không bị xem là dấu ngăn key/value |

Ví dụ tên biểu diễn literal wildcard:

\`\`\`text
com.example:type=Queue,name="orders\*"
com.example:type=Queue,name="requests\?"
\`\`\`

Cả hai có thể là tên cụ thể vì dấu đại diện được escape. Ngược lại \`name="orders*"\` biểu diễn một value pattern, dù đang ở trong dấu nháy kép.

Để không nhầm số tầng escape, phân biệt:

- **Chuỗi dữ liệu Java:** các ký tự mà ứng dụng muốn đặt tên.
- **Chuỗi ObjectName:** có quote/escape theo ngữ pháp JMX.
- **Java source literal:** muốn ghi dấu \`\\\` vào String trong mã nguồn Java phải viết \`\\\\\`; muốn ghi dấu nháy kép phải viết \`\"\` trong literal.

Cách đáng tin cậy là tạo ObjectName value bằng API:

\`\`\`java
import javax.management.ObjectName;

String raw = "order\"batch\\A,*?\nnext";
String quoted = ObjectName.quote(raw);
String recovered = ObjectName.unquote(quoted);

System.out.println(raw.equals(recovered)); // true

ObjectName name = new ObjectName(
    "com.example:type=Queue,name=" + quoted
);

System.out.println(name.isPattern()); // false
\`\`\`

\`quote\` thực hiện escaping cần thiết cho dấu nháy kép, backslash, newline, dấu sao và dấu hỏi. Nó không thay đổi ý nghĩa của dữ liệu gốc khi \`unquote\`. Đây là lựa chọn mặc định khi giá trị được lấy từ tên service, tenant, file, URL, key của hệ thống ngoài hoặc input người dùng.

## 6. Wildcard: giá trị literal hay pattern?

Trong \`ObjectName\`, dấu \`*\` khớp một chuỗi ký tự bất kỳ và \`?\` khớp một ký tự. Pattern được dùng để **truy vấn**, điển hình với \`MBeanServer.queryNames\`. Một tên pattern không hợp lệ để dùng như tên MBean cụ thể khi đăng ký.

\`\`\`java
import javax.management.ObjectName;

ObjectName exact =
    new ObjectName("com.example:type=Queue,name=orders");

ObjectName valuePattern =
    new ObjectName("com.example:type=Queue,name=order*");

ObjectName propertyListPattern =
    new ObjectName("com.example:type=Queue,*");

System.out.println(exact.isPattern());                // false
System.out.println(valuePattern.isPattern());         // true
System.out.println(propertyListPattern.isPattern());  // true
\`\`\`

Ba loại pattern cần phân biệt:

1. **Domain pattern:** \`com.example.*:type=Cache\` tìm domain phù hợp.
2. **Property value pattern:** \`com.example:type=Cache,name=cache*\` tìm tên có phần value khớp.
3. **Property list pattern:** \`com.example:type=Cache,*\` cho phép danh sách key-property bổ sung.

Khi tên cụ thể chứa dấu \`*\` hoặc \`?\` do dữ liệu người dùng cung cấp, dùng \`ObjectName.quote(rawValue)\` để escape thành literal. Nếu viết trực tiếp \`name=orders*\`, đối tượng sẽ là pattern và có thể khiến \`registerMBean\` từ chối.

\`\`\`java
String rawName = "orders*";
ObjectName safe = new ObjectName(
    "com.example:type=Queue,name=" + ObjectName.quote(rawName)
);

System.out.println(safe.isPattern()); // false
\`\`\`

Không tự tạo pattern từ dữ liệu thiếu tin cậy nếu mục tiêu là lookup đúng một MBean.

## 7. Tạo ObjectName bằng constructor nhiều tham số

Đối với tên có nhiều key, constructor chuyên dụng tránh phải tự ghép phần \`key=value\` và dấu phẩy:

\`\`\`java
import javax.management.ObjectName;
import java.util.Hashtable;

Hashtable<String, String> properties = new Hashtable<>();
properties.put("type", "Queue");
properties.put("name", "orders");

ObjectName name =
    new ObjectName("com.example", properties);
\`\`\`

Nhưng constructor này **không tự quote dữ liệu value** cho bạn. Nếu \`name\` có ký tự đặc biệt, vẫn nên cung cấp giá trị dưới dạng \`ObjectName.quote(rawValue)\`:

\`\`\`java
properties.put("name", ObjectName.quote("orders,urgent"));
ObjectName safelyNamed = new ObjectName("com.example", properties);
\`\`\`

Với các tham số đơn, có thể dùng constructor:

\`\`\`java
ObjectName one = new ObjectName(
    "com.example",
    "type",
    "Queue"
);
\`\`\`

Đối với domain hoặc property key **động**, \`quote\` không giải quyết tính hợp lệ của tên domain/key; validate chúng bằng một quy tắc riêng hoặc ưu tiên domain/key cố định, có kiểm soát.

## 8. Chuẩn hóa, đọc và so sánh tên

Các API hữu ích:

\`\`\`java
ObjectName objectName =
    new ObjectName("com.example:region=asia,type=Cache,name=Products");

String domain = objectName.getDomain();
String type = objectName.getKeyProperty("type");
String rawList = objectName.getKeyPropertyListString();
String canonical = objectName.getCanonicalName();
boolean pattern = objectName.isPattern();
\`\`\`

Giá trị \`getKeyPropertyListString()\` là chuỗi properties theo thứ tự biểu diễn, còn \`getCanonicalKeyPropertyListString()\` trả properties được sắp thứ tự canonical. Khi quan tâm danh tính, tránh dựa vào thứ tự gõ ban đầu.

**Không đồng nhất domain với hostname:** \`ObjectName\` chỉ là định danh logic trong \`MBeanServer\`. Các JVM khác nhau có thể cùng đăng ký \`com.example:type=Queue,name=orders\` mà không xung đột vì chúng thuộc registry khác nhau.

## 9. Ví dụ hoàn chỉnh: đăng ký MBean với tên từ dữ liệu bên ngoài

Giả sử ứng dụng có các hàng đợi mang tên \`priority,eu\` và \`bulk*\`. Ta muốn đăng ký MBean an toàn với cả hai tên mà không biến tên thành pattern.

\`\`\`java
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.lang.management.ManagementFactory;
import java.util.List;

public class QueueRegistration {
    public interface QueueMetricsMBean {
        int getPending();
    }

    public static final class QueueMetrics implements QueueMetricsMBean {
        private final int pending;
        public QueueMetrics(int pending) { this.pending = pending; }
        public int getPending() { return pending; }
    }

    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();

        for (String queueName : List.of("priority,eu", "bulk*")) {
            ObjectName name = new ObjectName(
                "com.example.queues:type=Queue,name=" +
                ObjectName.quote(queueName)
            );

            server.registerMBean(new QueueMetrics(12), name);

            System.out.printf("%s -> %s%n", queueName, name);
            System.out.println("Pattern? " + name.isPattern());
        }
    }
}
\`\`\`

Trong ứng dụng sống lâu, \`MBeanExporter\` của Spring thường giúp quản lý vòng đời đăng ký và unregister; ở ví dụ Java SE thuần, cần chủ động unregister những tên đã tạo khi kết thúc module nếu server còn sống. Đối với hai queue có cùng tên, phải thiết kế thêm dimension/instance hoặc xử lý trùng tên, bởi một server không cho đăng ký hai MBean cùng một \`ObjectName\`.

## 10. Một số input sai và cách sửa

| Input | Vấn đề | Cách sửa |
| --- | --- | --- |
| \`com.example:type=Queue,name=a,b\` | \`b\` không phải cặp key=value | \`name="a,b"\` |
| \`com.example:type=Queue,name=a=b\` | Ký tự \`=\` trong unquoted value | \`name="a=b"\` |
| \`com.example:type=Queue,name=a*b\` | Trở thành property-value pattern | \`name="a\*b"\` |
| \`com.example:type=Queue,name=a?b\` | Trở thành property-value pattern | \`name="a\?b"\` |
| \`com.example:type=Queue,name=one,name=two\` | Lặp property key | Chỉ dùng một key \`name\`, hoặc thêm key phân biệt khác |
| \`com.example:type=Queue,=abc\` | Key rỗng | Chọn key có tên, ví dụ \`name=abc\` |
| \`com.example:type=Queue,name="a"b"\` | Dấu nháy kép không được escape | Dùng \`ObjectName.quote\` từ raw input |

Với bảng trên, các chuỗi có dấu nháy kép là **ObjectName notation**, không phải Java string literal. Nếu đặt chúng trực tiếp trong Java source, cần escape thêm theo quy tắc Java.

## 11. Spring Framework: đặt ObjectName cho bean quản trị

Spring JMX cho phép khai báo tên trực tiếp:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example:type=Queue,name=Orders",
    description = "Operational state of the orders queue"
)
public class OrdersQueueManagement {
    // Các @ManagedAttribute và @ManagedOperation phù hợp.
}
\`\`\`

Khi giá trị tên đến từ cấu hình động, đừng nối thẳng vào một literal \`objectName\` mà không quote. Có thể cấu hình \`MBeanExporter\` bằng map từ \`ObjectName\` đã tạo và được validate, hoặc đưa logic đặt tên vào \`ObjectNamingStrategy\` của Spring. Mục tiêu là để code quản trị chịu trách nhiệm chuyển dữ liệu thành một \`ObjectName\` hợp lệ, thay vì buộc lớp nghiệp vụ phải hiểu cú pháp JMX.

Ví dụ factory nhỏ để tái sử dụng:

\`\`\`java
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;

public final class QueueObjectNames {
    private QueueObjectNames() {}

    public static ObjectName forQueue(String queueName)
            throws MalformedObjectNameException {
        if (queueName == null || queueName.isBlank()) {
            throw new IllegalArgumentException("Queue name is required");
        }

        return new ObjectName(
            "com.example:type=Queue,name=" +
            ObjectName.quote(queueName)
        );
    }
}
\`\`\`

Factory này giữ domain và key ổn định, chỉ quote phần dữ liệu động. Có thể thêm \`instance\`, \`region\`, \`tenant\` nếu chúng là thành phần định danh thật sự cần thiết và được quản lý nhất quán.

## 12. Kiểm thử tên và escaping

Không cần chạy một \`MBeanServer\` để kiểm tra mọi trường hợp tên. Dùng \`ObjectName\` trực tiếp:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import javax.management.ObjectName;

class ObjectNameEscapingTest {
    @Test
    void quoteRoundTripsSpecialCharacters() throws Exception {
        String raw = "orders,eu=\"priority\"\\tier*?\nnext";
        ObjectName name = new ObjectName(
            "com.example:type=Queue,name=" + ObjectName.quote(raw)
        );

        assertFalse(name.isPattern());
        assertEquals(
            raw,
            ObjectName.unquote(name.getKeyProperty("name"))
        );
    }

    @Test
    void canonicalNameIgnoresPropertyOrder() throws Exception {
        ObjectName a =
            new ObjectName("com.example:type=Queue,name=orders");
        ObjectName b =
            new ObjectName("com.example:name=orders,type=Queue");

        assertEquals(a, b);
        assertEquals(a.getCanonicalName(), b.getCanonicalName());
    }

    @Test
    void unescapedStarMakesPattern() throws Exception {
        ObjectName pattern =
            new ObjectName("com.example:type=Queue,name=orders*");

        assertTrue(pattern.isPropertyValuePattern("name"));
        assertTrue(pattern.isPattern());
    }
}
\`\`\`

Với tích hợp JMX, bổ sung kiểm tra đăng ký/tra cứu bằng đúng \`ObjectName\`, xử lý \`MalformedObjectNameException\` từ cấu hình và phát hiện collision khi hai thành phần sinh cùng danh tính.

## 13. Quy tắc thực hành

1. Giữ **domain và key cố định**, có quy ước đặt tên rõ.
2. Với mọi **value động**, dùng \`ObjectName.quote(raw)\` và chỉ \`unquote\` khi biết giá trị đang ở dạng quoted.
3. Dùng \`isPattern()\` hoặc \`isPropertyValuePattern(key)\` để phát hiện wildcard khi tên cần là định danh cụ thể.
4. Dùng \`ObjectName\` hoặc \`getCanonicalName()\` để so sánh, không giả định thứ tự cặp property.
5. Xử lý riêng **key không hợp lệ**, **giá trị đặc biệt**, **pattern**, và **đụng tên MBean**; chúng là các loại lỗi khác nhau.
6. Đừng đưa thông tin nhạy cảm vào \`ObjectName\`: tên MBean thường hiển thị trong log, dashboard và công cụ vận hành.

## 14. Ghi nhớ

\`ObjectName\` là một định danh có ngữ pháp, không phải nhãn tùy ý. **Key** là tên các chiều định danh, **value** là dữ liệu của chiều đó, còn \`quote\` và escaping quyết định ký tự đặc biệt được hiểu là literal hay cú pháp. Khi đặt tên từ dữ liệu động, giữ key ổn định và dùng \`ObjectName.quote\`; khi tra cứu hàng loạt, sử dụng pattern có chủ đích. Hai nguyên tắc này giúp tránh các lỗi khó tìm như MBean bị coi là pattern, tên sai cấu trúc hoặc client không tìm thấy MBean theo tên mong đợi.
