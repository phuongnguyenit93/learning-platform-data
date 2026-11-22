# DynamicMBean và mô tả giao diện được tạo lúc chạy

## 1. Mục tiêu học tập

JMX (Java Management Extensions) dùng MBean để công khai trạng thái và thao tác quản trị của ứng dụng Java. Với **Standard MBean**, Java suy ra giao diện quản trị từ interface tuân theo quy ước đặt tên. Với **DynamicMBean**, chính đối tượng cung cấp metadata và tự xử lý yêu cầu đọc thuộc tính, ghi thuộc tính, gọi operation. Nhờ đó, giao diện quản trị có thể được xây dựng từ cấu hình hoặc đặc điểm của thành phần trong lúc chạy.

Học xong bài này, bạn có thể:

- Giải thích vì sao DynamicMBean phù hợp khi danh sách thuộc tính hoặc thao tác không cố định lúc biên dịch.
- Hiểu sáu phương thức của \`javax.management.DynamicMBean\` và cách chúng phối hợp.
- Tạo một DynamicMBean với \`MBeanInfo\`, \`MBeanAttributeInfo\`, \`MBeanOperationInfo\` và \`MBeanParameterInfo\`.
- Đăng ký DynamicMBean vào \`MBeanServer\` và quan sát từ JConsole hoặc Java JMX client.
- Kiểm soát lỗi, quyền ghi, kiểu dữ liệu, concurrency và tính ổn định của metadata.
- Phân biệt tính năng JMX nền tảng với các cách Spring Framework xuất MBean.

## 2. Mô hình tư duy: metadata là hợp đồng quản trị

Một client JMX có thể không biết trước lớp Java cụ thể của MBean. Nó hỏi MBeanServer: “Đối tượng này có thuộc tính nào, kiểu dữ liệu gì, có đọc/ghi được không, operation nào có thể gọi?” MBeanServer lấy thông tin từ \`getMBeanInfo()\`; client sử dụng thông tin đó để dựng giao diện, sau đó gọi các phương thức truy cập tương ứng.

\`\`\`text
             Client: JConsole / JMX client
                         |
                 getMBeanInfo()
                         |
                     MBeanServer
                         |
                 DynamicMBean
             /            |            \
 getAttribute(s)     setAttribute(s)   invoke(...)
             \            |            /
                  Trạng thái nghiệp vụ
\`\`\`

Điểm cốt lõi: **metadata mô tả khả năng; các phương thức đọc/ghi/gọi mới thực thi khả năng đó**. Nếu metadata khai báo một attribute có thể ghi nhưng \`setAttribute\` luôn từ chối, client sẽ gặp hợp đồng không nhất quán. Nếu metadata khai báo kiểu \`java.lang.Integer\` nhưng \`getAttribute\` trả về \`String\`, client có thể lỗi hoặc diễn giải sai.

DynamicMBean “động” không có nghĩa JMX tự phát hiện mọi method trên object. Người viết DynamicMBean chủ động quyết định những gì công khai, ánh xạ tên với dữ liệu và trả về metadata.

## 3. Sáu phương thức của DynamicMBean

\`\`\`java
public interface DynamicMBean {
    Object getAttribute(String attribute)
        throws AttributeNotFoundException, MBeanException, ReflectionException;

    void setAttribute(Attribute attribute)
        throws AttributeNotFoundException, InvalidAttributeValueException,
               MBeanException, ReflectionException;

    AttributeList getAttributes(String[] attributes);

    AttributeList setAttributes(AttributeList attributes);

    Object invoke(String actionName, Object[] params, String[] signature)
        throws MBeanException, ReflectionException;

    MBeanInfo getMBeanInfo();
}
\`\`\`

| Phương thức | Vai trò | Lưu ý |
|---|---|---|
| \`getMBeanInfo()\` | Trả metadata của MBean | Attribute, operation, constructor, notification, className, description |
| \`getAttribute(name)\` | Đọc một attribute | Phải báo rõ khi attribute không tồn tại hoặc không đọc được |
| \`setAttribute(attribute)\` | Ghi một attribute | Kiểm tra tên, quyền ghi, kiểu và miền giá trị |
| \`getAttributes(names)\` | Đọc nhiều attribute | Trả về \`AttributeList\`; attribute lỗi có thể được bỏ qua |
| \`setAttributes(list)\` | Ghi nhiều attribute | Trả về các attribute ghi thành công; không mặc định atomic |
| \`invoke(name, params, signature)\` | Gọi operation | Phải kiểm tra cả tên, tham số, chữ ký và quyền gọi |

\`MBeanInfo\` không phải snapshot giá trị của attribute. Nó là **mô tả giao diện**; các giá trị được lấy bằng \`getAttribute\` tại thời điểm đọc.

## 4. Metadata được biểu diễn thế nào?

Các lớp metadata quan trọng nằm trong \`javax.management\`:

- \`MBeanInfo\`: thông tin tổng thể, gồm tên lớp, mô tả, mảng attributes, constructors, operations, notifications và descriptor tùy chọn.
- \`MBeanAttributeInfo\`: tên, kiểu Java, mô tả, khả năng đọc/ghi, cờ isGetter.
- \`MBeanOperationInfo\`: tên operation, mô tả, danh sách tham số, kiểu trả về và impact.
- \`MBeanParameterInfo\`: tên, kiểu và mô tả tham số.
- \`MBeanNotificationInfo\`: loại notification mà MBean có thể phát, nếu có.
- \`Descriptor\`: metadata bổ sung theo hợp đồng JMX, nếu một công cụ hoặc framework cần.

Ví dụ:

\`\`\`java
new MBeanAttributeInfo(
    "Enabled",                // tên client truy vấn
    Boolean.class.getName(),  // kiểu attribute công bố
    "Whether processing is enabled",
    true,                     // readable
    true,                     // writable
    false                     // isGetter
);
\`\`\`

Tên kiểu trong metadata phải phản ánh kiểu runtime trả về/chấp nhận. \`int.class.getName()\` cho ra \`"int"\`, còn \`Integer.class.getName()\` là \`"java.lang.Integer"\`. Chọn một cách nhất quán với giá trị được đóng hộp khi truyền qua API JMX.

Mô tả operation:

\`\`\`java
new MBeanOperationInfo(
    "reset",
    "Reset the completed count",
    new MBeanParameterInfo[0],
    Void.TYPE.getName(),
    MBeanOperationInfo.ACTION
);
\`\`\`

Các giá trị impact phổ biến: \`INFO\` (truy vấn thông tin), \`ACTION\` (thay đổi trạng thái), \`ACTION_INFO\` (cả hai), \`UNKNOWN\`. Đây là thông tin dành cho công cụ/client; nó **không tự áp đặt phân quyền**.

## 5. Ví dụ hoàn chỉnh: DynamicMBean cho bộ đếm tác vụ

Ví dụ sau tạo một MBean có ba thuộc tính: \`Name\` chỉ đọc, \`Enabled\` đọc/ghi, \`Completed\` chỉ đọc; operation \`reset\` đặt số công việc đã hoàn thành về 0.

File \`TaskCounterDynamic.java\`:

\`\`\`java
import javax.management.*;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

public final class TaskCounterDynamic implements DynamicMBean {
    private final String name;
    private final AtomicInteger completed = new AtomicInteger();
    private volatile boolean enabled = true;
    private final MBeanInfo metadata;

    public TaskCounterDynamic(String name) {
        this.name = Objects.requireNonNull(name, "name");

        MBeanAttributeInfo[] attributes = {
            new MBeanAttributeInfo(
                "Name", String.class.getName(),
                "Logical counter name", true, false, false),
            new MBeanAttributeInfo(
                "Enabled", Boolean.class.getName(),
                "Whether counting is enabled", true, true, false),
            new MBeanAttributeInfo(
                "Completed", Integer.class.getName(),
                "Completed task count", true, false, false)
        };

        MBeanOperationInfo[] operations = {
            new MBeanOperationInfo(
                "reset", "Reset the completed count",
                new MBeanParameterInfo[0],
                Void.TYPE.getName(),
                MBeanOperationInfo.ACTION)
        };

        this.metadata = new MBeanInfo(
            getClass().getName(),
            "Dynamic task counter used for JMX training",
            attributes,
            null,
            operations,
            null
        );
    }

    public void taskCompleted() {
        if (enabled) {
            completed.incrementAndGet();
        }
    }

    @Override
    public Object getAttribute(String attribute)
            throws AttributeNotFoundException {
        if (attribute == null) {
            throw new AttributeNotFoundException("Attribute name is null");
        }
        switch (attribute) {
            case "Name":
                return name;
            case "Enabled":
                return enabled;
            case "Completed":
                return completed.get();
            default:
                throw new AttributeNotFoundException(attribute);
        }
    }

    @Override
    public void setAttribute(Attribute attribute)
            throws AttributeNotFoundException,
                   InvalidAttributeValueException {
        if (attribute == null) {
            throw new InvalidAttributeValueException(
                "Attribute must not be null");
        }
        String key = attribute.getName();
        if (!"Enabled".equals(key)) {
            throw new AttributeNotFoundException(
                "Unknown or read-only attribute: " + key);
        }
        if (!(attribute.getValue() instanceof Boolean value)) {
            throw new InvalidAttributeValueException(
                "Enabled expects java.lang.Boolean");
        }
        enabled = value;
    }

    @Override
    public AttributeList getAttributes(String[] attributes) {
        AttributeList values = new AttributeList();
        if (attributes == null) {
            return values;
        }
        for (String key : attributes) {
            try {
                values.add(new Attribute(key, getAttribute(key)));
            } catch (AttributeNotFoundException ignored) {
                // JMX bulk reads return only successful entries.
            }
        }
        return values;
    }

    @Override
    public AttributeList setAttributes(AttributeList attributes) {
        AttributeList changed = new AttributeList();
        if (attributes == null) {
            return changed;
        }
        for (Object candidate : attributes) {
            if (!(candidate instanceof Attribute attribute)) {
                continue;
            }
            try {
                setAttribute(attribute);
                changed.add(new Attribute(
                    attribute.getName(),
                    getAttribute(attribute.getName())));
            } catch (AttributeNotFoundException |
                     InvalidAttributeValueException ignored) {
                // JMX bulk writes return only successful entries.
            }
        }
        return changed;
    }

    @Override
    public Object invoke(String actionName,
                         Object[] params,
                         String[] signature)
            throws ReflectionException {
        boolean noParams = params == null || params.length == 0;
        boolean noSignature =
            signature == null || signature.length == 0;
        if ("reset".equals(actionName) && noParams && noSignature) {
            completed.set(0);
            return null;
        }
        throw new ReflectionException(
            new NoSuchMethodException(
                String.valueOf(actionName)),
            "Unknown operation or invalid signature");
    }

    @Override
    public MBeanInfo getMBeanInfo() {
        return metadata;
    }
}
\`\`\`

**Vì sao ví dụ có chủ ý đơn giản?**

- \`metadata\` được tạo một lần trong constructor: giao diện được tạo ở runtime nhưng ổn định trong vòng đời object.
- \`AtomicInteger\` cho phép cập nhật/đọc bộ đếm an toàn giữa nhiều thread.
- \`volatile boolean\` giúp thread khác nhìn thấy cập nhật trạng thái \`Enabled\`.
- \`setAttribute\` kiểm tra đúng \`Boolean\`, không ép kiểu tùy tiện từ chuỗi.
- \`invoke\` từ chối tên hoặc chữ ký không hợp lệ.
- Các phương thức bulk chỉ báo entry thành công; code production nên ghi log/telemetry hoặc phản hồi lỗi theo chính sách phù hợp để dễ chẩn đoán.

Cần lưu ý: việc kiểm tra \`enabled\` và tăng \`completed\` không tạo một transaction nguyên tử giữa hai biến. Nếu nghiệp vụ đòi hỏi bảo đảm không tăng sau một điểm chuyển trạng thái cụ thể, cần đồng bộ hóa hoặc cấu trúc state nhất quán hơn.

## 6. Đăng ký lên MBeanServer và chạy thử

File \`Main.java\`:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class Main {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();

        TaskCounterDynamic counter =
            new TaskCounterDynamic("batch-worker");
        ObjectName objectName = new ObjectName(
            "training.dynamic:type=TaskCounter,name=Batch");

        server.registerMBean(counter, objectName);

        for (int i = 0; i < 3; i++) {
            counter.taskCompleted();
        }

        System.out.println("Registered: " + objectName);
        System.out.println("PID: " + ProcessHandle.current().pid());
        Thread.sleep(300_000);
    }
}
\`\`\`

Với JDK 21, đặt hai file cùng thư mục và chạy:

\`\`\`bash
javac TaskCounterDynamic.java Main.java
java Main
\`\`\`

Trong terminal khác:

\`\`\`bash
jconsole
\`\`\`

Chọn Java process đang chạy, mở tab **MBeans**, tìm domain \`training.dynamic\`. Kiểm tra:

1. Đọc \`Name\` thấy \`batch-worker\`.
2. Đọc \`Completed\` thấy \`3\`.
3. Chỉnh \`Enabled\` từ \`true\` sang \`false\`, rồi đọc lại.
4. Gọi \`reset\` và xác nhận \`Completed = 0\`.
5. Xem thông tin MBean: ba attributes, một operation với mô tả từ \`MBeanInfo\`.

Khi chạy ví dụ trên, JMX local dựa vào platform \`MBeanServer\`. Ví dụ không tạo một endpoint JMX/RMI từ xa và không mở firewall.

## 7. Truy cập chương trình bằng JMX client

Ngoài JConsole, client Java có thể dùng \`MBeanServerConnection\` để đọc metadata, attribute và gọi operation; khi trong cùng JVM, \`MBeanServer\` triển khai giao diện này.

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.*;

public class Inspect {
    public static void inspect(ObjectName name) throws Exception {
        MBeanServerConnection connection =
            ManagementFactory.getPlatformMBeanServer();

        MBeanInfo info = connection.getMBeanInfo(name);

        for (MBeanAttributeInfo attr : info.getAttributes()) {
            System.out.printf("%s: %s; read=%s; write=%s%n",
                attr.getName(), attr.getType(),
                attr.isReadable(), attr.isWritable());
        }

        Object before = connection.getAttribute(name, "Completed");
        System.out.println("Before reset: " + before);

        connection.invoke(name, "reset",
            new Object[0], new String[0]);

        System.out.println("After reset: " +
            connection.getAttribute(name, "Completed"));
    }
}
\`\`\`

Hàm \`inspect\` giả định tên MBean đã được đăng ký vào **cùng JVM**. Nếu đặt trong JVM khác, phải lấy \`MBeanServerConnection\` từ \`JMXConnector\` hợp lệ. Đây là hai bước khác nhau: xuất MBean lên server và thiết lập kênh client đến server.

Một công cụ quản trị tổng quát thường làm việc theo chuỗi:

\`\`\`text
queryNames(pattern) → getMBeanInfo(name)
                   → render attribute / operation controls
                   → getAttribute / setAttribute / invoke
\`\`\`

Dữ liệu trả về có thể là Java primitive wrapper, String, enum/kiểu đơn giản, hoặc các loại JMX Open Types. Nếu dự kiến client dùng công nghệ khác Java, hãy cân nhắc khả năng tuần tự hóa và tương thích kiểu; không nên mặc định rằng một POJO tùy ý sẽ hiển thị đúng trên mọi client.

## 8. Khi nào metadata thực sự thay đổi lúc chạy?

Trong ví dụ trước, metadata được **tạo trong constructor** và giữ nguyên. Đây đã là DynamicMBean vì chính class triển khai hợp đồng JMX, nhưng giao diện không đổi sau khi đăng ký.

Một tình huống nâng cao: ứng dụng tải danh sách chỉ số từ cấu hình, ví dụ:

\`\`\`text
metric CPU_Load   → readable Double
metric Queue_Size → readable Integer
metric Enabled    → readable/writable Boolean
operation reload  → no arguments
\`\`\`

Khi ứng dụng reload cấu hình, nó có thể tạo snapshot mới cho cả **danh sách attributes** và **cách đọc giá trị**. Mục tiêu là client không nhìn metadata của phiên bản A nhưng truy vấn giá trị bằng registry phiên bản B.

Thiết kế gợi ý:

\`\`\`java
record AttributeSpec(
    String type,
    boolean readable,
    boolean writable,
    String description
) {}

record ModelSnapshot(
    java.util.Map<String, AttributeSpec> attributes,
    MBeanInfo info
) {}

private volatile ModelSnapshot currentModel;
\`\`\`

Quy trình reload:

1. Đọc và validate toàn bộ định nghĩa mới vào cấu trúc tạm.
2. Tạo \`MBeanInfo\` tương ứng trên dữ liệu đã xác thực.
3. Publish một snapshot bất biến bằng một thao tác gán tham chiếu.
4. Với mỗi yêu cầu đọc/ghi, lấy snapshot một lần rồi xử lý dựa trên snapshot đó.
5. Xác định rõ hành vi nếu attribute bị xóa giữa thời điểm client đọc metadata và gọi \`getAttribute\`.

**Giới hạn cần hiểu:** hai lời gọi JMX độc lập không tạo thành transaction với nhau. Dù cập nhật snapshot atomic, client có thể nhận \`MBeanInfo\` cũ rồi gặp \`AttributeNotFoundException\` vì schema đã đổi. Một thiết kế vận hành tốt cần versioning, thông báo thay đổi nếu phù hợp, hoặc giữ các tên cũ trong giai đoạn chuyển tiếp.

JMX có các cơ chế thông báo hỗ trợ client biết MBean được đăng ký/hủy đăng ký (qua \`MBeanServerDelegate\`), và DynamicMBean có thể phát notification riêng nếu triển khai các giao diện tương ứng. Không giả định chỉ đổi \`getMBeanInfo()\` sẽ tự động khiến mọi client làm mới giao diện ngay.

## 9. DynamicMBean so với Standard MBean, MXBean và Spring JMX

| Loại | Ai mô tả giao diện? | Khi nào dùng? | Hạn chế |
|---|---|---|---|
| Standard MBean | Interface theo quy ước tên | Giao diện ổn định, ít công việc bổ sung | Cần hợp đồng Java tĩnh |
| MXBean | Interface MXBean và mapping Open Types | Trao đổi dữ liệu quản trị dễ tương thích | Có quy tắc mapping dữ liệu |
| DynamicMBean | \`getMBeanInfo()\` và các method dispatch | Schema được cấu hình, plugin hoặc phát hiện runtime | Nhiều code xử lý lỗi/metadata |
| Spring-exported bean | Spring \`MBeanExporter\` và assembler | Muốn công khai bean Spring với cấu hình tập trung | Phụ thuộc cơ chế mapping/export |

Một DynamicMBean vẫn có thể là một object được Spring container quản lý. Tuy nhiên, không nên coi hai mô hình export của Spring và JMX là một: Spring quản lý vòng đời/đăng ký; \`DynamicMBean\` cung cấp hợp đồng xử lý yêu cầu JMX. Kiểm tra cách exporter và assembler cụ thể xử lý đối tượng đã triển khai \`DynamicMBean\`; tránh giả định tự động kết hợp mọi annotation và dynamic metadata.

**Quy tắc lựa chọn:** nếu giao diện đã biết tại compile time, bắt đầu với Standard MBean hoặc MXBean. Chỉ chọn DynamicMBean khi sự linh hoạt của metadata thực sự mang lại giá trị, như plugin có cấu trúc thay đổi, quy tắc runtime hoặc quản trị module theo cấu hình.

## 10. Lỗi thường gặp và cách chẩn đoán

### 10.1. \`NotCompliantMBeanException\` lúc đăng ký

Kiểm tra lớp có triển khai đúng \`DynamicMBean\` và các method hợp lệ. Với Standard MBean, kiểm tra interface naming convention; đừng trộn quy tắc đặt tên Standard MBean vào việc định nghĩa DynamicMBean.

### 10.2. \`AttributeNotFoundException\`

Tên trong \`MBeanAttributeInfo\` phải khớp chính xác tên mà \`getAttribute\` và \`setAttribute\` nhận. JMX phân biệt chữ hoa/thường. Cũng có thể client đã cache metadata trước một lần reload schema.

### 10.3. \`InvalidAttributeValueException\`

Kiểm tra đúng type và miền dữ liệu. Một số console gửi kiểu đóng hộp (\`Boolean\`, \`Integer\`), không phải chuỗi. Đừng chuyển \`"false"\` thành \`Boolean\` tùy ý nếu metadata đã tuyên bố type cụ thể.

### 10.4. \`ReflectionException\` khi invoke

Xác nhận action name, số tham số, \`signature[]\` và tên class kiểu tham số. Với overload, chỉ tên operation là không đủ để xác định method.

### 10.5. Metadata và runtime lệch nhau

Ví dụ metadata nói attribute writable nhưng \`setAttribute\` luôn từ chối; operation tuyên bố trả \`int\` nhưng thực thi trả \`String\`. Cần tạo metadata và handler từ cùng một tập đặc tả, rồi thử bằng một client thực tế.

### 10.6. Race condition khi reload

Không sửa trực tiếp một \`HashMap\` toàn cục trong khi thread JMX đang đọc. Ưu tiên immutable snapshot và publication an toàn; giữ hợp đồng exception rõ ràng khi client dùng schema cũ.

### 10.7. Truy cập từ xa thất bại

Nếu MBean xuất hiện trong JConsole local mà remote không truy cập được, vấn đề có thể nằm ở connector/RMI, hostname, firewall, TLS hoặc xác thực. **DynamicMBean không tự cấu hình kết nối từ xa**.

## 11. Bảo mật và khả năng vận hành

JMX là kênh quản trị có thể đọc trạng thái hệ thống hoặc kích hoạt operation thay đổi dữ liệu. Cần cân nhắc:

- Chỉ expose dữ liệu phù hợp; không đặt token, password, dữ liệu người dùng trong attribute hoặc ObjectName.
- Phân biệt operation chỉ đọc và operation thay đổi trạng thái, nhưng không xem cờ \`INFO\`/\`ACTION\` là cơ chế kiểm soát quyền.
- Dùng cơ chế xác thực, mã hóa và giới hạn mạng khi có remote access; không mở endpoint JMX trực tiếp ra Internet.
- Giới hạn truy vấn tốn tài nguyên; tránh operation chạy dài hoặc khóa toàn bộ ứng dụng.
- Viết handler thread-safe; tránh giữ lock lâu trong \`getAttribute\`.
- Theo dõi lỗi dispatch, schema change, truy cập bị từ chối và số operation quản trị, nếu chính sách vận hành cho phép.
- Quy hoạch tên ObjectName ổn định, duy nhất và đủ dễ tra cứu.
- Không cam kết việc \`setAttributes\` là all-or-nothing; tài liệu hóa partial success và cung cấp operation nghiệp vụ nếu cần transaction.

## 12. Bài tập ứng dụng

### Bài tập A — Metadata từ cấu hình

Cho các dòng cấu hình \`name,type,readable,writable\`, xây dựng \`MBeanAttributeInfo[]\` trong constructor. Chỉ chấp nhận kiểu trong danh sách cho phép như \`String\`, \`Integer\`, \`Boolean\`; từ chối kiểu không hợp lệ trước khi publish MBean.

**Kết quả mong đợi:** thêm một metric hợp lệ vào cấu hình rồi khởi động lại sẽ làm JConsole xuất hiện thêm attribute mà không sửa mã \`getMBeanInfo()\` thủ công.

### Bài tập B — Dispatch từ registry

Thay \`switch\` trong \`getAttribute\` bằng map các handler đã kiểm tra kiểu. Đảm bảo không công khai method Java tùy ý qua reflection.

**Kết quả mong đợi:** tên không tồn tại trả \`AttributeNotFoundException\`, writable=false bị chặn, dữ liệu trả đúng type.

### Bài tập C — Schema reload

Dùng snapshot bất biến để thay toàn bộ metadata trong một lần publish. Viết hai thread: thread A gọi \`getMBeanInfo\`/đọc attribute liên tục, thread B reload danh sách attributes.

**Kết quả mong đợi:** không gặp \`ConcurrentModificationException\`; khi client dùng schema cũ, exception được xử lý rõ ràng và hệ thống tiếp tục hoạt động.

### Bài tập D — Kiểm chứng độc lập với UI

Viết một JMX client tự động:
1. Tìm ObjectName bằng \`queryNames\`.
2. Lấy \`MBeanInfo\` và in tên/type/readable/writable.
3. Thử đọc các attribute readable.
4. Kiểm tra operation \`reset\`.
5. Kiểm tra attribute không tồn tại và input sai kiểu được báo lỗi thích hợp.

## 13. Câu hỏi tự kiểm tra

1. Lý do nào khiến DynamicMBean hữu ích hơn Standard MBean trong một plugin system?
2. \`getMBeanInfo\` khác \`getAttribute\` về chức năng như thế nào?
3. Tại sao metadata writable phải khớp \`setAttribute\`?
4. \`getAttributes\` có bắt buộc trả entry cho mọi tên yêu cầu không?
5. Vì sao operation cần cả \`actionName\` và \`signature\`?
6. \`MBeanOperationInfo.ACTION\` có tự chặn client không có quyền không?
7. Vì sao đổi metadata runtime có thể gây lỗi cho client cache schema?
8. Cách nào tránh dữ liệu định nghĩa bị đọc dở trong lúc reload?
9. Spring \`MBeanExporter\` giải quyết phần nào so với \`DynamicMBean\`?
10. Nếu JConsole local thấy MBean nhưng remote client không thấy, nên kiểm tra những tầng nào?

## 14. Tài liệu đọc thêm

- Java SE 21 — \`DynamicMBean\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/DynamicMBean.html
- Java SE 21 — \`MBeanInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
- Java SE 21 — \`MBeanAttributeInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanAttributeInfo.html
- Java SE 21 — \`MBeanOperationInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanOperationInfo.html
- Java SE 21 — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html

**Ghi nhớ:** DynamicMBean trao quyền kiểm soát trực tiếp hợp đồng quản trị cho lập trình viên. Điều quan trọng là bảo đảm metadata, xử lý request và trạng thái ứng dụng luôn nhất quán; chỉ sau đó mới cân nhắc schema thay đổi trong lúc chạy và remote JMX.
