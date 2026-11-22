# Kiểm tra ObjectName bằng API thay vì ghép chuỗi tùy tiện

## 1. Mục tiêu

Trong Java Management Extensions (JMX), \`javax.management.ObjectName\` là định danh dùng để đăng ký, tra cứu và quản lý MBean trong \`MBeanServer\`. Một \`ObjectName\` có cấu trúc và quy tắc cú pháp riêng; nó không đơn thuần là một chuỗi có dấu hai chấm và dấu phẩy.

Khi làm việc với Spring Framework JMX, việc tạo tên MBean bằng các phép nối chuỗi tùy tiện dễ gây lỗi vì:
- Giá trị động có thể chứa dấu phẩy, dấu bằng, dấu hai chấm, dấu ngoặc kép, dấu gạch chéo ngược hoặc ký tự mang nghĩa wildcard.
- Thứ tự các thuộc tính khóa có thể khác nhau dù cùng định danh một MBean.
- Một tên có thể là **pattern** dùng để truy vấn, chứ không phải tên cụ thể được đăng ký.
- Chuỗi hợp lệ về mặt cú pháp chưa chắc thuộc domain hoặc nhóm MBean mà ứng dụng cho phép.
- Tên hợp lệ không chứng minh MBean đang được đăng ký trong máy chủ JMX.

Bài này tập trung vào cách dùng **API của Java**, từ \`ObjectName\` tới \`MBeanServer\`, để xây dựng và kiểm tra tên MBean một cách có cấu trúc.

Sau bài học, bạn có thể:
1. Hiểu cú pháp \`domain:key=value,key=value\` và sự khác nhau giữa tên cụ thể với pattern.
2. Dùng constructor, \`ObjectName.quote()\`, \`ObjectName.unquote()\` và \`MalformedObjectNameException\` đúng chỗ.
3. Kiểm tra domain, các key bắt buộc, giá trị, wildcard và tên canonical bằng API.
4. Phân biệt **hợp lệ về cú pháp**, **hợp lệ theo quy ước ứng dụng** và **đang tồn tại trong MBeanServer**.
5. Áp dụng quy trình kiểm tra khi Spring xuất bản bean thành MBean.

## 2. Cấu trúc của một ObjectName

Một tên thông thường có dạng:

\`\`\`text
com.example.orders:type=Worker,name=ImportJob
└──── domain ────┘ └──── key properties ────┘
\`\`\`

- **Domain** phân nhóm tên, ví dụ \`com.example.orders\`, \`java.lang\`.
- **Key property** là cặp \`key=value\`, ví dụ \`type=Worker\`, \`name=ImportJob\`.
- Tổ hợp domain và key properties xác định một tên JMX. Không thể coi \`name\` riêng lẻ là định danh toàn cục.
- Một domain có thể rỗng ở mức API, nhưng ứng dụng thường nên dùng domain tường minh theo quy ước.
- Các ký tự \`*\` và \`?\` có thể mang ý nghĩa mẫu khớp (pattern), tùy vị trí và cách escape.

Ví dụ tên cụ thể:

\`\`\`text
com.example.orders:type=Worker,name=ImportJob
java.lang:type=Memory
\`\`\`

Ví dụ pattern dùng trong truy vấn:

\`\`\`text
com.example.orders:type=Worker,*
com.example.orders:type=Worker,name=*
com.example.*:type=Worker,name=ImportJob
\`\`\`

**Phân biệt quan trọng:** \`ObjectName\` là một đối tượng Java đã được phân tích cú pháp. Việc gọi \`toString()\` để ghi log là được, nhưng với logic so sánh hoặc xác thực nên dùng các phương thức truy cập thuộc tính và so sánh của API.

## 3. Ba cấp độ kiểm tra không được đánh đồng

| Cấp độ | Câu hỏi | API/biện pháp |
|---|---|---|
| **Cú pháp** | Chuỗi có phải ObjectName hợp lệ không? | \`new ObjectName(text)\`, bắt \`MalformedObjectNameException\` |
| **Chính sách ứng dụng** | Domain, key, type, wildcard có đúng phạm vi cho phép? | \`getDomain()\`, \`getKeyProperty()\`, \`getKeyPropertyList()\`, \`isPattern()\` |
| **Đăng ký thực tế** | MBean có mặt trong MBeanServer này không? | \`MBeanServer.isRegistered(name)\` |

Một chuỗi \`java.lang:type=Memory\` có thể đúng cú pháp nhưng không hợp lệ cho một API chỉ cho phép MBean riêng thuộc domain \`com.example.orders\`. Ngược lại, \`com.example.orders:type=Worker,name=ImportJob\` có thể đúng cú pháp và đúng chính sách nhưng hiện chưa được đăng ký.

Quy trình đúng phải xét từng cấp độ theo nhu cầu, không lấy kết quả của cấp độ này thay cho cấp độ khác.

## 4. Xây dựng tên từ dữ liệu có cấu trúc

### 4.1. Tránh đưa giá trị động vào cú pháp thô

Giả sử tên worker lấy từ cấu hình hoặc dữ liệu vận hành:

\`\`\`java
String workerName = "Import,Asia=East";
String raw = "com.example.orders:type=Worker,name=" + workerName;
\`\`\`

\`raw\` trở thành:

\`\`\`text
com.example.orders:type=Worker,name=Import,Asia=East
\`\`\`

Ở đây dấu phẩy và dấu bằng trong \`workerName\` bị hiểu như cú pháp khai báo **key property mới** (\`Asia=East\`). Nếu tên chứa ký tự khác, parser có thể ném lỗi. Việc kiểm tra chuỗi bằng \`contains("type=Worker")\` hoặc cắt theo dấu phẩy không giải quyết được nguyên nhân.

### 4.2. Dùng constructor và ObjectName.quote

Khi có giá trị động, hãy cố định domain/key ở lớp tạo tên và escape **giá trị** bằng \`ObjectName.quote()\`:

\`\`\`java
import java.util.Hashtable;
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;

public final class WorkerObjectNames {
    private static final String DOMAIN = "com.example.orders";

    private WorkerObjectNames() {}

    public static ObjectName forWorker(String workerName)
            throws MalformedObjectNameException {
        if (workerName == null || workerName.isBlank()) {
            throw new IllegalArgumentException("workerName must not be blank");
        }

        Hashtable<String, String> keys = new Hashtable<>();
        keys.put("type", "Worker");
        keys.put("name", ObjectName.quote(workerName));

        return new ObjectName(DOMAIN, keys);
    }
}
\`\`\`

Sử dụng:

\`\`\`java
ObjectName objectName =
        WorkerObjectNames.forWorker("Import,Asia=East");

System.out.println(objectName.getDomain());
System.out.println(objectName.getKeyProperty("type"));
System.out.println(objectName.getCanonicalName());
\`\`\`

\`ObjectName.quote(value)\` thêm dấu ngoặc kép và escape các ký tự có ý nghĩa đặc biệt trong **giá trị** để parser không coi chúng là thành phần cấu trúc ngoài ý muốn. Nó cũng escape \`*\` và \`?\` để chúng được hiểu là ký tự dữ liệu, thay vì wildcard trong property value.

Cần hiểu rằng constructor nhận \`Hashtable\` giúp phân chia key/value rõ ràng, nhưng **không nên giả định constructor tự escape mọi chuỗi giá trị tùy ý**. Vì vậy, ở ví dụ trên, \`workerName\` được quote có chủ đích.

Có thể dùng constructor ba đối số khi chỉ có một key:

\`\`\`java
ObjectName name = new ObjectName(
        "com.example.orders",
        "name",
        ObjectName.quote("Import,Asia=East")
);
\`\`\`

Nếu domain hoặc tên key cũng đến từ nguồn không tin cậy, \`quote()\` cho property value không đủ để làm chúng an toàn; domain và key cần được **kiểm tra/giới hạn riêng**. Trong ứng dụng thực tế, thường giữ domain/key cố định và chỉ cho phép thay đổi phần giá trị đã kiểm soát.

### 4.3. Vì sao không phải mọi phép nối chuỗi đều sai?

Mục tiêu không phải cấm tuyệt đối phép nối chuỗi. Ví dụ sau vẫn có thể hợp lệ nếu domain và key cố định, còn giá trị động đã được quote:

\`\`\`java
ObjectName name = new ObjectName(
        "com.example.orders:type=Worker,name="
                + ObjectName.quote(workerName)
);
\`\`\`

Tuy nhiên constructor có cấu trúc và một hàm tạo tên tập trung giúp người đọc thấy rõ domain, key, xử lý giá trị động và chính sách của ứng dụng. Hạn chế sao chép các đoạn format tên rải rác ở nhiều nơi.

## 5. Parse tên bằng ObjectName API

Khi nhận một chuỗi tên đầy đủ từ cấu hình, CLI hoặc request quản trị, hãy dùng parser của JMX:

\`\`\`java
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;

public static ObjectName parse(String input)
        throws MalformedObjectNameException {
    if (input == null || input.isBlank()) {
        throw new IllegalArgumentException("ObjectName is required");
    }
    return new ObjectName(input);
}
\`\`\`

Các chuỗi không hợp lệ, ví dụ sai cú pháp key properties hoặc dùng ký tự đặc biệt không đúng quy tắc, dẫn đến \`MalformedObjectNameException\`. Đây là cơ chế phân tích cú pháp chính thức, đáng tin cậy hơn các regex tự viết nhằm mô phỏng toàn bộ cú pháp JMX.

Ví dụ xử lý lỗi ở ranh giới API:

\`\`\`java
try {
    ObjectName objectName = parse(userInput);
    // Tiếp tục kiểm tra domain, key và pattern.
} catch (MalformedObjectNameException
         | IllegalArgumentException ex) {
    // Trả lỗi đầu vào phù hợp với ứng dụng, không đăng ký hay truy vấn MBean.
}
\`\`\`

**Lưu ý:** Constructor chấp nhận cả **ObjectName pattern** hợp lệ. Parse thành công chưa chắc có nghĩa tên được phép dùng cho thao tác đăng ký hoặc truy cập một MBean cụ thể.

## 6. Chặn wildcard không mong muốn

JMX có các phương thức chuyên biệt:

- \`isPattern()\`: tên có phải pattern ở bất kỳ thành phần nào?
- \`isDomainPattern()\`: domain có pattern?
- \`isPropertyPattern()\`: danh sách hoặc giá trị key properties có pattern?
- \`isPropertyListPattern()\`: có pattern mở rộng danh sách key properties, ví dụ \`type=Worker,*\`?
- \`isPropertyValuePattern()\`: có property value mang wildcard?
- \`isPropertyValuePattern("name")\`: riêng giá trị property \`name\` có pattern không?

Ví dụ:

\`\`\`java
ObjectName query =
        new ObjectName("com.example.orders:type=Worker,name=*");

System.out.println(query.isPattern());                  // true
System.out.println(query.isPropertyValuePattern());     // true
System.out.println(query.isDomainPattern());            // false
\`\`\`

Trong khi đó:

\`\`\`java
ObjectName exact = WorkerObjectNames.forWorker("Import*");
System.out.println(exact.isPattern()); // false
\`\`\`

Trong trường hợp thứ hai, dấu \`*\` là ký tự trong tên worker, đã được \`ObjectName.quote()\` escape để giữ nghĩa literal.

**Quy tắc thiết kế:** Nếu một thao tác cần xác định đúng một MBean (ví dụ \`getAttribute\`, \`invoke\`, \`unregisterMBean\`, hoặc đăng ký tên cụ thể), đầu vào nên là **concrete ObjectName**, và nên từ chối \`isPattern() == true\`. Pattern dành cho những thao tác tìm kiếm có chủ đích như \`queryNames()\`.

Đừng dùng thủ thuật \`input.contains("*")\` để phát hiện pattern. Chuỗi \`*\` có thể đã được escape và mang nghĩa dữ liệu. Hãy hỏi chính \`ObjectName\`.

## 7. Kiểm tra domain và key properties theo chính sách

Một API quản trị chỉ cho phép Worker MBean trong domain \`com.example.orders\` có thể kiểm tra như sau:

\`\`\`java
import java.util.Map;
import java.util.Set;
import javax.management.ObjectName;

public final class WorkerNamePolicy {
    private static final String DOMAIN = "com.example.orders";
    private static final Set<String> REQUIRED_KEYS =
            Set.of("type", "name");

    private WorkerNamePolicy() {}

    public static boolean isAllowed(ObjectName name) {
        if (name == null || name.isPattern()) {
            return false;
        }
        if (!DOMAIN.equals(name.getDomain())) {
            return false;
        }

        Map<String, String> keys = name.getKeyPropertyList();

        if (!REQUIRED_KEYS.equals(keys.keySet())) {
            return false;
        }
        if (!"Worker".equals(name.getKeyProperty("type"))) {
            return false;
        }

        String worker = name.getKeyProperty("name");
        if (worker == null) {
            return false;
        }

        // Với chính sách này, name buộc phải là giá trị đã quote.
        if (worker.length() < 2
                || worker.charAt(0) != '"'
                || worker.charAt(worker.length() - 1) != '"') {
            return false;
        }

        try {
            String decoded = ObjectName.unquote(worker);
            return !decoded.isBlank() && decoded.length() <= 128;
        } catch (IllegalArgumentException ex) {
            return false;
        }
    }
}
\`\`\`

Ví dụ chọn chính sách **giá trị \`name\` luôn được quote**, vì factory ở mục 4 luôn tạo tên theo cách đó. Nếu ứng dụng đã có ObjectName hợp lệ với giá trị không quote, chính sách này sẽ từ chối chúng có chủ ý; hãy điều chỉnh quy ước sao cho tương thích với hệ thống thật.

Ở đây:

- \`getDomain()\` kiểm tra domain bằng so sánh chính xác, không dùng \`startsWith()\` quá rộng.
- \`getKeyPropertyList().keySet()\` yêu cầu chính xác hai key, không tự ý chấp nhận thêm các key ngoài hợp đồng.
- \`getKeyProperty("type")\` xác minh loại đối tượng.
- \`getKeyProperty("name")\` lấy giá trị đã biểu diễn theo cú pháp ObjectName; \`ObjectName.unquote()\` chỉ được dùng khi giá trị có biểu diễn quoted.
- \`isPattern()\` ngăn wildcard đi vào ngữ cảnh yêu cầu một tên cụ thể.

Đây là **ví dụ về một policy cụ thể**, không phải quy tắc toàn cầu cho mọi ObjectName. Một hệ thống khác có thể cho phép thêm \`instance\`, \`tenant\` hoặc \`node\`, và có thể chấp nhận cả tên không quote.

### Lưu ý về dữ liệu và phân quyền

Kiểm tra cấu trúc \`ObjectName\` không thay thế kiểm tra quyền. Nếu người gọi được phép quản trị một tenant hoặc một nhóm worker cụ thể, cần kiểm tra **quan hệ sở hữu và quyền gọi**, không chỉ xác nhận tên nằm trong domain cho phép.

Ngoài ra, giới hạn độ dài \`name\` chỉ là ví dụ. Chọn chính sách phù hợp với dữ liệu thực tế, tránh dữ liệu bất thường gây tốn tài nguyên hoặc khó đọc log.

## 8. So sánh đúng: equals và canonical name

Các key properties có thể được viết theo thứ tự khác nhau:

\`\`\`java
ObjectName a = new ObjectName(
        "com.example.orders:type=Worker,name=ImportJob");

ObjectName b = new ObjectName(
        "com.example.orders:name=ImportJob,type=Worker");

System.out.println(a.equals(b)); // true
System.out.println(a.getCanonicalName()
        .equals(b.getCanonicalName())); // true
\`\`\`

Không nên dùng so sánh \`a.toString().equals(b.toString())\` như nguồn chân lý, vì representation có thể phản ánh thứ tự key ban đầu. \`getCanonicalName()\` cung cấp dạng chuẩn hóa để lưu log, cache key hoặc đối chiếu khi hợp đồng yêu cầu, còn \`ObjectName.equals()\` là lựa chọn tự nhiên khi so sánh hai đối tượng \`ObjectName\`.

Một số API hữu ích:

| API | Mục đích |
|---|---|
| \`getDomain()\` | Lấy domain |
| \`getKeyProperty("type")\` | Lấy giá trị key cụ thể |
| \`getKeyPropertyList()\` | Lấy các key/value đã parse |
| \`getKeyPropertyListString()\` | Biểu diễn phần key properties |
| \`getCanonicalKeyPropertyListString()\` | Biểu diễn phần key properties đã chuẩn hóa thứ tự |
| \`getCanonicalName()\` | Tên đầy đủ ở dạng canonical |
| \`equals(other)\` | So sánh định danh theo ngữ nghĩa của ObjectName |
| \`isPattern()\` | Kiểm tra wildcard/pattern |
| \`apply(other)\` | Kiểm tra ObjectName pattern có khớp tên được đưa vào hay không |

Khi cần so khớp nhiều MBean trong một truy vấn, tạo pattern rõ ràng và dùng \`queryNames()\` hoặc \`apply()\`. Khi cần định danh chính xác một MBean, tạo concrete ObjectName rồi dùng \`equals()\`.

## 9. Kiểm tra MBean đã được đăng ký hay chưa

Sau khi đã parse và kiểm tra chính sách, dùng \`MBeanServer\` để xác minh sự tồn tại:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = WorkerObjectNames.forWorker("ImportJob");

if (WorkerNamePolicy.isAllowed(name)
        && server.isRegistered(name)) {
    System.out.println("MBean da duoc dang ky");
} else {
    System.out.println("MBean khong ton tai hoac ten khong duoc phep");
}
\`\`\`

\`isRegistered(name)\` kiểm tra **máy chủ MBean được chỉ định**. Nếu ứng dụng sử dụng MBeanServer khác, JMX connector từ xa hoặc MBean được đăng ký ở JVM khác, cần kiểm tra đúng server/connection tương ứng.

Lưu ý thêm:
- \`isRegistered()\` không thay thế kiểm tra trước khi thao tác; trạng thái có thể thay đổi giữa lúc kiểm tra và lúc \`getAttribute()\`/\`invoke()\`.
- Nếu MBean bị gỡ sau kiểm tra, thao tác sau đó vẫn có thể phát sinh \`InstanceNotFoundException\`.
- Nếu thao tác có thể thay đổi trạng thái, cần xét authentication, authorization và audit phù hợp.
- Tên tồn tại chưa chứng minh MBean có attribute hoặc operation mà caller muốn dùng. Có thể kiểm tra metadata qua \`getMBeanInfo()\` hoặc xử lý exception khi truy cập.

Ví dụ pattern tìm tất cả worker:

\`\`\`java
ObjectName pattern = new ObjectName(
        "com.example.orders:type=Worker,*");

for (ObjectName candidate : server.queryNames(pattern, null)) {
    System.out.println(candidate.getCanonicalName());
}
\`\`\`

Ở đây \`queryNames\` phù hợp vì mục đích là tìm **nhiều** MBean. Nếu muốn chỉ lấy các tên thỏa policy chính xác, hãy lọc thêm bằng policy ở trên; pattern \`type=Worker,*\` có thể khớp các MBean chứa những key khác \`name\`.

## 10. Áp dụng vào Spring Framework JMX

Spring Framework có cơ chế export Spring-managed bean thành JMX MBean, chẳng hạn \`MBeanExporter\`, annotation \`@ManagedResource\` và quy tắc đặt tên MBean.

Ví dụ MBean được gắn ObjectName cố định:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.orders:type=Worker,name=ImportJob"
)
public class ImportWorkerMonitor {
    @ManagedAttribute
    public String getStatus() {
        return "RUNNING";
    }
}
\`\`\`

Tên khai báo ở annotation là tĩnh. Nếu tên cần chứa giá trị động (tenant, instance hoặc worker name), không nên nhét trực tiếp chuỗi cấu hình chưa kiểm tra vào biểu diễn JMX. Có thể xây dựng tên qua \`ObjectName\` factory rồi dùng cơ chế đăng ký/naming strategy hoặc \`MBeanExporter\` phù hợp với cách cấu hình ứng dụng.

Ví dụ một cách chuẩn bị ánh xạ tên có kiểm tra:

\`\`\`java
import java.util.Map;
import javax.management.ObjectName;
import org.springframework.jmx.export.MBeanExporter;

public static MBeanExporter exporterFor(
        Object monitorBean,
        String workerName
) throws Exception {
    ObjectName objectName =
            WorkerObjectNames.forWorker(workerName);

    MBeanExporter exporter = new MBeanExporter();
    exporter.setBeans(Map.of(objectName, monitorBean));
    return exporter;
}
\`\`\`

Đây là minh họa cơ chế export programmatic. Trong ứng dụng Spring thực tế, thường khai báo \`MBeanExporter\` là Spring bean, kết nối đúng \`MBeanServer\`, tránh tạo nhiều exporter đăng ký cùng một ObjectName. Việc lựa chọn lifecycle, behavior khi trùng tên và unregister được cấu hình nhất quán với application context.

**Quan trọng:** Spring bean name (\`importWorkerMonitor\`) và JMX ObjectName (\`com.example.orders:type=Worker,name=ImportJob\`) là hai định danh thuộc hai hệ thống khác nhau. Đừng kiểm tra ObjectName bằng cách tìm trong Spring \`ApplicationContext\`; hãy dùng API JMX.

## 11. Một bộ hàm tiện ích nhỏ để dùng tập trung

Trong codebase thực tế, nên đưa logic tạo tên, parse và kiểm tra về một lớp riêng để tránh nơi nào cũng tạo tên theo một quy tắc khác nhau:

\`\`\`java
import java.util.Hashtable;
import java.util.Set;
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;

public final class JmxWorkerNames {
    private static final String DOMAIN = "com.example.orders";
    private static final Set<String> KEYS = Set.of("type", "name");

    private JmxWorkerNames() {}

    public static ObjectName create(String workerName)
            throws MalformedObjectNameException {
        if (workerName == null
                || workerName.isBlank()
                || workerName.length() > 128) {
            throw new IllegalArgumentException("Invalid worker name");
        }

        Hashtable<String, String> keyProperties = new Hashtable<>();
        keyProperties.put("type", "Worker");
        keyProperties.put("name", ObjectName.quote(workerName));
        return new ObjectName(DOMAIN, keyProperties);
    }

    public static ObjectName parseAndValidate(String input)
            throws MalformedObjectNameException {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("ObjectName required");
        }

        ObjectName name = new ObjectName(input);

        if (name.isPattern()
                || !DOMAIN.equals(name.getDomain())
                || !KEYS.equals(name.getKeyPropertyList().keySet())
                || !"Worker".equals(name.getKeyProperty("type"))) {
            throw new IllegalArgumentException(
                    "ObjectName outside Worker policy");
        }

        String encoded = name.getKeyProperty("name");
        if (encoded == null
                || encoded.length() < 2
                || encoded.charAt(0) != '"'
                || encoded.charAt(encoded.length() - 1) != '"') {
            throw new IllegalArgumentException(
                    "Worker name must be quoted");
        }

        String decoded = ObjectName.unquote(encoded);
        if (decoded.isBlank() || decoded.length() > 128) {
            throw new IllegalArgumentException("Invalid worker name");
        }

        return name;
    }
}
\`\`\`

Ứng dụng có thể sử dụng:

\`\`\`java
ObjectName created = JmxWorkerNames.create("Import,Asia=East");
ObjectName restored = JmxWorkerNames.parseAndValidate(
        created.toString()
);

System.out.println(created.equals(restored)); // true
\`\`\`

Bộ tiện ích này chọn **một quy ước cụ thể**: chỉ domain \`com.example.orders\`, đúng hai key \`type\` và \`name\`, loại \`Worker\`, không wildcard và \`name\` luôn quote. Khi cần hỗ trợ legacy names, nhiều loại MBean hoặc nhiều domain, hãy mở rộng policy một cách có chủ đích; đừng bỏ toàn bộ validation.

### Kiểm tra thủ công vài tình huống đầu vào

| Đầu vào | Kết quả mong đợi |
|---|---|
| \`com.example.orders:type=Worker,name="ImportJob"\` | Cú pháp hợp lệ; qua policy trên |
| \`com.example.orders:name="ImportJob",type=Worker\` | Qua policy; thứ tự key không quan trọng |
| \`com.example.orders:type=Worker,name=ImportJob\` | Cú pháp hợp lệ nhưng bị policy ví dụ từ chối vì \`name\` không quote |
| \`com.example.orders:type=Worker,name=*\` | Là pattern; từ chối cho thao tác tên cụ thể |
| \`java.lang:type=Memory\` | Có thể đúng cú pháp; sai domain/type của policy |
| \`com.example.orders:type=Worker,name="Import,Asia=East"\` | Giá trị động có dấu phân cách được biểu diễn hợp lệ |
| \`com.example.orders:type=Worker,name="Import\*"\` với dấu \`*\` literal được escape bởi \`ObjectName.quote()\` | Concrete name; dấu \`*\` được hiểu là dữ liệu |

Bảng trên minh họa **chính sách của ví dụ**, không áp đặt cách quote bắt buộc cho tất cả JMX ObjectName.

## 12. Sai lầm phổ biến và cách thay thế

**Sai lầm 1 — Tự ghép giá trị chưa escape.**

\`\`\`java
String text = domain + ":type=Worker,name=" + workerName;
\`\`\`

Hãy cố định domain/key và dùng \`ObjectName.quote(workerName)\`, rồi tạo \`ObjectName\` bằng constructor phù hợp.

**Sai lầm 2 — Kiểm tra cấu trúc bằng regex hoặc split theo dấu phẩy.**

\`\`\`java
String[] parts = text.split(",");
\`\`\`

Dấu phẩy có thể nằm trong giá trị đã quote. Dùng \`new ObjectName(text)\` và \`getKeyPropertyList()\`.

**Sai lầm 3 — So chuỗi để xác định cùng một tên.**

\`\`\`java
first.toString().equals(second.toString());
\`\`\`

Dùng \`first.equals(second)\`; dùng \`getCanonicalName()\` khi thật sự cần representation chuẩn hóa.

**Sai lầm 4 — Cho rằng parse thành công là được phép thao tác.**

Một pattern hợp lệ có thể rộng hơn phạm vi người dùng được phép truy cập. Kiểm tra domain, key, giá trị, \`isPattern()\` và quyền thực tế.

**Sai lầm 5 — Tự tìm ký tự \`*\` để kết luận tên là pattern.**

Một wildcard đã escape có thể là ký tự literal trong property. Dùng \`isPattern()\` và các API chuyên biệt.

**Sai lầm 6 — Coi ObjectName hợp lệ nghĩa là MBean tồn tại.**

Chỉ \`MBeanServer.isRegistered()\` hoặc thao tác JMX thực tế trên đúng server mới xác nhận trạng thái đăng ký tại thời điểm đó.

**Sai lầm 7 — Chỉ kiểm tra tên mà quên bảo mật.**

ObjectName là một định danh, không phải bằng chứng được ủy quyền. Đối với \`invoke\` hoặc \`setAttribute\`, luôn yêu cầu xác thực/phân quyền và xem xét tác động của thao tác.

## 13. Bài tập tự kiểm tra

**Câu 1:** Worker có tên \`East,Backup=1\`. Vì sao nối trực tiếp vào \`name=\` dễ sai?  
**Gợi ý đáp án:** Dấu phẩy và dấu bằng có ý nghĩa trong cú pháp key properties. Dùng \`ObjectName.quote()\` cho giá trị động.

**Câu 2:** Hai chuỗi cùng domain, cùng key/value, nhưng thứ tự key đảo ngược. Chúng có định danh cùng MBean không?  
**Gợi ý đáp án:** Có thể có. Parse thành \`ObjectName\` và so bằng \`equals()\` hoặc kiểm tra canonical name.

**Câu 3:** \`new ObjectName(text)\` không ném exception. Có thể dùng \`text\` để unregister một MBean ngay không?  
**Gợi ý đáp án:** Chưa. Phải xác minh đây là concrete name, thuộc domain/type cho phép, và người gọi được cấp quyền thực hiện thao tác.

**Câu 4:** Muốn tìm tất cả MBean có \`type=Worker\` trong domain ứng dụng thì dùng API nào?  
**Gợi ý đáp án:** Tạo một \`ObjectName\` pattern có chủ đích rồi dùng \`MBeanServer.queryNames(pattern, null)\`; có thể lọc kết quả theo policy ứng dụng.

**Câu 5:** Một ObjectName đúng policy nhưng \`server.isRegistered(name)\` trả \`false\`. Kết luận gì?  
**Gợi ý đáp án:** Tên phù hợp quy ước nhưng không được đăng ký trên MBeanServer được kiểm tra tại thời điểm gọi; cần xem đúng server, lifecycle và cấu hình export.

## 14. Ghi nhớ

- Dùng \`ObjectName\` API để **parse, tạo, so sánh và truy vấn thành phần**; tránh tự mô phỏng cú pháp bằng phép cắt/ghép chuỗi tùy tiện.
- Dùng \`ObjectName.quote()\` với **property value động**; nó không thay thế kiểm tra domain và key.
- \`MalformedObjectNameException\` cho biết lỗi cú pháp; \`isPattern()\` cho biết khả năng wildcard; policy ứng dụng quy định tên nào được chấp nhận.
- \`equals()\` và \`getCanonicalName()\` xử lý đúng ngữ nghĩa của key properties không phụ thuộc thứ tự đầu vào.
- \`MBeanServer.isRegistered()\` kiểm tra đăng ký trên **một MBeanServer cụ thể** và không bảo đảm tồn tại tại thời điểm thao tác sau đó.
- Với Spring JMX, hãy kiểm tra ObjectName ở ranh giới export và quản trị, giữ rõ ràng trách nhiệm giữa Spring bean, MBean, và caller được phép thao tác.

### Tài liệu tham khảo

- Java SE API — \`javax.management.ObjectName\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
- Java SE API — \`javax.management.MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Reference — Exporting Beans: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Oracle JMX Tutorial — Using ObjectNames: https://docs.oracle.com/javase/tutorial/jmx/mbeans/objectname.html
