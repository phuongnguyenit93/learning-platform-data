# Kiểm tra MBeanInfo thực tế sau khi export trong Spring JMX

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao cần kiểm tra **MBeanInfo sau khi MBean thực sự được đăng ký** thay vì chỉ dựa trên interface, annotation hoặc cấu hình \`MBeanExporter\`.
- Dùng \`MBeanServer.getMBeanInfo(ObjectName)\` và \`MBeanServer.isRegistered(ObjectName)\` để xác minh bề mặt quản trị.
- Đọc **attributes**, **operations**, **constructors**, **notifications**, **descriptors** và các thông tin kiểu dữ liệu mà JMX công bố.
- Phân biệt metadata của **Standard MBean**, **MXBean**, **Model MBean** và những implementation khác.
- Xác định sai lệch giữa cấu hình Spring JMX với hợp đồng được client như JConsole thực sự nhìn thấy.
- Viết phép kiểm tra tự động cho tên và chữ ký operation, read/write attribute, tính vắng mặt của API nội bộ, và metadata description.
- Chẩn đoán các lỗi exporter thường gặp: sai \`ObjectName\`, đăng ký trùng, sai assembler, exporter khác, quản lý sai \`MBeanServer\` hoặc lifecycle.
- Thiết kế quy trình kiểm tra bề mặt JMX an toàn, không vô tình gọi operation có tác dụng phụ.

## 2. Vì sao phải kiểm tra runtime MBeanInfo?

Trong Spring Framework, một bean có thể được xuất qua JMX bằng \`MBeanExporter\`, annotation \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\` hoặc interface quản trị. Tuy nhiên code nguồn chỉ mô tả **ý định**; metadata thực tế còn phụ thuộc:

1. Exporter nào được cấu hình và khởi tạo.
2. Bean nào được đưa vào danh sách export.
3. \`ObjectName\` được tạo ra bởi naming strategy nào.
4. Assembler nào được dùng để chọn attributes/operations.
5. MBean thuộc loại Standard, MXBean hay Model MBean.
6. Quá trình đăng ký có thành công hay bị trùng tên.
7. MBeanServer nào đang được JConsole hoặc client kết nối.
8. Ứng dụng đã chạy đến thời điểm đăng ký hay đã hủy MBean.
9. Phiên bản Spring/JDK và custom implementation có thay đổi metadata không.

**MBeanInfo runtime** là hợp đồng mà một JMX client thực sự có thể khám phá ở thời điểm truy vấn. Kiểm tra trực tiếp giúp phát hiện interface bị xuất thừa, thiếu thông tin hoặc khác với cấu hình dự kiến.

\`\`\`text
Java interface / annotations / configuration
                |
                v
   MBeanExporter + MBeanInfoAssembler
                |
                v
        MBeanServer.registerMBean
                |
                v
       MBeanInfo của MBean thực tế
                |
         +------+------+
         |             |
         v             v
     JConsole     Java JMX client
         |             |
         +------> attributes / operations
                  signatures / descriptions
\`\`\`

Nếu Spring bean có annotation đúng nhưng exporter không đăng ký, \`getMBeanInfo\` sẽ không tìm thấy MBean. Nếu exporter dùng assembler không đọc annotation, các operation dự định có thể không xuất hiện. Nếu exporter phát hiện quá nhiều method, method nội bộ có thể bị phơi bày. Runtime verification giải quyết các trường hợp đó.

## 3. Các API JMX cần biết

| API | Ý nghĩa |
| --- | --- |
| \`MBeanServer.isRegistered(name)\` | Kiểm tra \`ObjectName\` hiện có trong registry không. |
| \`MBeanServer.getMBeanInfo(name)\` | Lấy metadata của MBean được đăng ký. |
| \`MBeanServer.queryNames(pattern, null)\` | Tìm những \`ObjectName\` phù hợp. |
| \`MBeanInfo.getClassName()\` | Tên class mô tả MBean. |
| \`MBeanInfo.getDescription()\` | Mô tả chung của MBean. |
| \`MBeanInfo.getAttributes()\` | Danh sách metadata thuộc tính. |
| \`MBeanInfo.getOperations()\` | Danh sách metadata operation. |
| \`MBeanInfo.getConstructors()\` | Metadata constructor được công bố. |
| \`MBeanInfo.getNotifications()\` | Loại notification được công bố. |
| \`MBeanInfo.getDescriptor()\` | Descriptor tổng thể của MBean. |
| \`MBeanAttributeInfo.getType()\` | Kiểu JMX của thuộc tính. |
| \`MBeanAttributeInfo.isReadable()\` | Thuộc tính được đọc qua JMX hay không. |
| \`MBeanAttributeInfo.isWritable()\` | Thuộc tính được ghi qua JMX hay không. |
| \`MBeanAttributeInfo.isIs()\` | Getter Boolean dạng \`isX()\` theo thông tin JMX. |
| \`MBeanOperationInfo.getSignature()\` | Danh sách kiểu/tham số operation. |
| \`MBeanOperationInfo.getReturnType()\` | Kiểu trả về operation. |
| \`MBeanOperationInfo.getImpact()\` | Mô tả mức tác động INFO/ACTION/ACTION_INFO/UNKNOWN. |
| \`MBeanFeatureInfo.getDescriptor()\` | Descriptor bổ sung của một feature. |

**Không phải mỗi metadata đều được mọi công cụ GUI trình bày đầy đủ**. Với kiểm tra chính xác, dùng API JMX để đọc đầy đủ thông tin.

## 4. Phân biệt “registered” và “exported as intended”

Đăng ký thành công chưa đủ để khẳng định hợp đồng đúng.

Ví dụ kỳ vọng:

\`\`\`text
com.example.jobs:type=ImportJob,name=Daily

Attributes:
  Running          boolean  read-only
  CompletedCount   long     read-only

Operations:
  requestPause()   void
\`\`\`

Các tình huống sai lệch có thể xảy ra:

- \`isRegistered(name)=true\` nhưng \`CompletedCount\` bị writable.
- \`requestPause\` không có trong operation list.
- \`stopProcessNow\` xuất hiện dù không dự định công bố.
- Description không được gắn vào metadata do assembler sai.
- Tham số operation bị sai tên/kiểu hoặc overload.
- \`ObjectName\` thực tế khác tên nhóm vận hành dùng.
- Một MBean cũ với cùng tên còn tồn tại do registration policy; client thấy metadata của object cũ thay vì bean mới.

Bởi vậy nên kiểm tra ít nhất: **đăng ký → metadata identity → danh sách attributes/operations → thuộc tính read/write → signature → các khả năng không được phép**.

## 5. Ví dụ Standard MBean tối thiểu

Tạo interface quản trị:

\`\`\`java
package example.jmx;

public interface ImportJobMonitorMBean {
    boolean isRunning();
    long getCompletedCount();
    void requestPause();
}
\`\`\`

Lớp triển khai:

\`\`\`java
package example.jmx;

public final class ImportJobMonitor implements ImportJobMonitorMBean {

    private volatile boolean running = true;
    private volatile long completedCount = 125L;

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public long getCompletedCount() {
        return completedCount;
    }

    @Override
    public void requestPause() {
        running = false;
    }

    // Public trong Java nhưng không nằm trong MBean interface.
    public String getInternalCredentialAlias() {
        return "internal-alias";
    }
}
\`\`\`

Vì đây là Standard MBean dùng interface \`ImportJobMonitorMBean\`, các method trong interface được JMX công bố thành attributes và operations theo quy ước.

- \`isRunning()\` → thuộc tính \`Running\`, \`boolean\`, đọc.
- \`getCompletedCount()\` → thuộc tính \`CompletedCount\`, \`long\`, đọc.
- \`requestPause()\` → operation không tham số, trả về \`void\`.
- \`getInternalCredentialAlias()\` **không** thuộc interface quản trị, nên không được xuất thông qua hợp đồng Standard MBean này.

**Lưu ý:** nếu dùng assembler phản xạ khác trên object này, kết quả có thể khác. Ví dụ ở đây giả định đúng cơ chế Standard MBean.

## 6. Đăng ký MBean và kiểm tra trực tiếp

Ví dụ Java SE đầy đủ để đọc metadata:

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class InspectMBeanInfoDemo {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.jobs:type=ImportJob,name=Daily"
        );

        server.registerMBean(new ImportJobMonitor(), name);
        try {
            System.out.println(
                "Registered: " + server.isRegistered(name)
            );

            MBeanInfo info = server.getMBeanInfo(name);
            System.out.println("Class: " + info.getClassName());
            System.out.println("Description: " + info.getDescription());

            for (MBeanAttributeInfo attribute
                    : info.getAttributes()) {
                System.out.printf(
                    "ATTRIBUTE name=%s type=%s read=%s write=%s is=%s%n",
                    attribute.getName(),
                    attribute.getType(),
                    attribute.isReadable(),
                    attribute.isWritable(),
                    attribute.isIs()
                );
            }

            for (MBeanOperationInfo operation
                    : info.getOperations()) {
                System.out.printf(
                    "OPERATION name=%s return=%s impact=%d%n",
                    operation.getName(),
                    operation.getReturnType(),
                    operation.getImpact()
                );

                for (MBeanParameterInfo parameter
                        : operation.getSignature()) {
                    System.out.printf(
                        "  PARAM name=%s type=%s desc=%s%n",
                        parameter.getName(),
                        parameter.getType(),
                        parameter.getDescription()
                    );
                }
            }
        } finally {
            server.unregisterMBean(name);
        }
    }
}
\`\`\`

Kết quả mong đợi về mặt hợp đồng: có \`Running\` và \`CompletedCount\` read-only, có \`requestPause\`, không có attribute \`InternalCredentialAlias\`. Kiểu primitive được mô tả bằng tên như \`boolean\`, \`long\` và \`void\`.

Cách trình bày thứ tự attributes/operations không phải hợp đồng ổn định giữa các implementation. Khi kiểm tra tự động nên so sánh tập tên và signature, không phụ thuộc thứ tự ngẫu nhiên.

## 7. Đọc metadata của Spring-exported MBean

Với Spring, bean có thể được đánh dấu:

\`\`\`java
package example.springjmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=ImportJob,name=Daily",
    description = "Daily import job management"
)
public class ImportJobManagement {

    @ManagedAttribute(description = "Whether import is running")
    public boolean isRunning() {
        return true;
    }

    @ManagedAttribute(description = "Processed item count")
    public long getCompletedCount() {
        return 125L;
    }

    @ManagedOperation(
        description = "Request a graceful pause of the import job"
    )
    public void requestPause() {
        // Request the worker to pause.
    }

    public String readInternalSecret() {
        return "must-not-export";
    }
}
\`\`\`

Khi \`MBeanExporter\` dùng \`MetadataMBeanInfoAssembler\` với \`AnnotationJmxAttributeSource\`, các annotation được dùng để tạo metadata quản trị cho bean. Sau khi export, client đọc \`MBeanInfo\` để xác nhận:

- MBean đã đăng ký tại \`ObjectName\` dự kiến.
- \`Running\` và \`CompletedCount\` có description phù hợp.
- \`requestPause\` xuất hiện với đúng return type và signature.
- \`readInternalSecret\` không trở thành operation/attribute ngoài mong muốn.

### 7.1. Cấu hình Spring exporter tường minh

\`\`\`java
package example.springjmx;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxExportConfig {

    @Bean
    public MBeanExporter mBeanExporter(ImportJobManagement admin) {
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
        exporter.setBeans(Map.of("importJobManagement", admin));

        return exporter;
    }
}
\`\`\`

Trong ứng dụng Spring Boot, có thể có JMX auto-configuration sẵn. Nếu tạo exporter riêng, tránh xuất cùng \`ObjectName\` hai lần và xác định rõ MBeanServer mục tiêu. Ví dụ trên là mẫu độc lập để giải thích cơ chế.

### 7.2. Cần kiểm tra đúng MBeanServer

Không phải mọi ứng dụng đều xuất vào platform MBeanServer mặc định. Spring có thể được cấu hình dùng custom \`MBeanServer\` hoặc một factory/provider khác.

Nếu \`ManagementFactory.getPlatformMBeanServer().isRegistered(name)\` trả \`false\`, đừng vội kết luận bean chưa export. Xác định đúng \`MBeanServer\` mà exporter được cấu hình sử dụng trước khi kiểm tra.

## 8. Viết hàm inspect MBeanInfo tái sử dụng

Một tiện ích có thể in metadata của MBean bất kỳ:

\`\`\`java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanConstructorInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanNotificationInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public final class JmxMetadataPrinter {

    public static void print(
            MBeanServerConnection connection,
            ObjectName name) throws Exception {

        MBeanInfo info = connection.getMBeanInfo(name);

        System.out.println("MBean: " + name.getCanonicalName());
        System.out.println("Class: " + info.getClassName());
        System.out.println("Description: " + info.getDescription());

        for (MBeanAttributeInfo attribute
                : info.getAttributes()) {
            System.out.println(
                "Attribute " + attribute.getName()
                + ", type=" + attribute.getType()
                + ", read=" + attribute.isReadable()
                + ", write=" + attribute.isWritable()
                + ", description=" + attribute.getDescription()
            );
        }

        for (MBeanOperationInfo operation
                : info.getOperations()) {
            System.out.println(
                "Operation " + operation.getName()
                + ", return=" + operation.getReturnType()
                + ", impact=" + operation.getImpact()
                + ", description=" + operation.getDescription()
            );

            for (MBeanParameterInfo parameter
                    : operation.getSignature()) {
                System.out.println(
                    "  Parameter " + parameter.getName()
                    + ", type=" + parameter.getType()
                    + ", desc=" + parameter.getDescription()
                );
            }
        }

        for (MBeanConstructorInfo ctor
                : info.getConstructors()) {
            System.out.println(
                "Constructor: " + ctor.getName()
            );
        }

        for (MBeanNotificationInfo notification
                : info.getNotifications()) {
            System.out.println(
                "Notification: " + notification.getName()
            );
        }
    }

    private JmxMetadataPrinter() { }
}
\`\`\`

Hàm nhận \`MBeanServerConnection\` nên có thể làm việc với local \`MBeanServer\` hoặc remote JMX connector, miễn kết nối có quyền đọc metadata. Tuy nhiên đọc metadata từ remote cũng cần cấu hình bảo mật mạng/JMX phù hợp.

Đây là thao tác inspection, không gọi \`invoke\` hay \`setAttribute\`, do đó ít rủi ro thay đổi trạng thái hơn. Nhưng metadata có thể vẫn chứa tên class, đường dẫn, domain và thông tin topology nội bộ; cần giới hạn nơi xuất kết quả.

## 9. Xem MBeanInfo bằng JConsole

Một cách trực quan:

1. Khởi chạy ứng dụng Spring có export JMX.
2. Mở JConsole và kết nối tới đúng JVM, local hoặc remote.
3. Chọn tab **MBeans**.
4. Tìm domain và \`ObjectName\`, ví dụ \`com.example.jobs:type=ImportJob,name=Daily\`.
5. Mở **Attributes** để xem tên, kiểu và giá trị mà công cụ hiển thị.
6. Mở **Operations** để xem những operation có thể được gọi.
7. Xem mô tả và metadata mà giao diện hỗ trợ hiển thị.

JConsole là một công cụ thuận tiện nhưng có thể không trình bày toàn bộ \`Descriptor\`, \`impact\` hoặc metadata của tham số. Khi cần kiểm tra chính xác, sử dụng \`MBeanServer.getMBeanInfo\` hoặc \`MBeanServerConnection.getMBeanInfo\`.

**Không bấm operation chỉ để “kiểm tra có tồn tại”**. Gọi operation qua JConsole có thể làm thay đổi trạng thái ứng dụng. Nếu chỉ cần kiểm tra surface API, hãy đọc metadata.

## 10. Attributes: kiểm tra tên, kiểu và quyền đọc/ghi

Một thuộc tính JMX có:

- \`name\`: tên quản trị, ví dụ \`Running\`.
- \`type\`: kiểu Java/JMX, ví dụ \`boolean\`, \`java.lang.String\`.
- \`readable\`: client có thể gọi \`getAttribute\` không.
- \`writable\`: client có thể gọi \`setAttribute\` không.
- \`isIs\`: getter dạng \`isX\` cho Boolean/boolean theo JMX semantics.
- \`description\`: thông tin giải thích nghiệp vụ.
- \`descriptor\`: metadata bổ sung nếu MBean cung cấp.

Ví dụ kỳ vọng:

\`\`\`text
Running:
  type = boolean
  readable = true
  writable = false

CompletedCount:
  type = long
  readable = true
  writable = false
\`\`\`

Nếu một attribute đo lường xuất hiện với \`writable=true\`, hãy kiểm tra setter hoặc strategy introspection của exporter. Một chỉ số như \`CompletedCount\` thường không nên cho JMX client chỉnh tùy ý.

### 10.1. Kiểm tra tự động attribute

\`\`\`java
import java.util.Arrays;
import javax.management.MBeanAttributeInfo;

MBeanAttributeInfo running = Arrays.stream(info.getAttributes())
    .filter(a -> a.getName().equals("Running"))
    .findFirst()
    .orElseThrow(() ->
        new AssertionError("Missing Running attribute")
    );

if (!running.isReadable() || running.isWritable()) {
    throw new AssertionError(
        "Running must be readable and not writable"
    );
}
\`\`\`

Không chỉ kiểm tra một field. Nếu một getter bí mật được xuất thừa, cần kiểm tra danh sách allowed attributes hoặc forbidden attributes.

## 11. Operations: tên và signature quan trọng

Metadata một operation gồm tên, kiểu trả về và danh sách tham số theo thứ tự.

Ví dụ:

\`\`\`java
public int retryFailedItems(int limit, boolean dryRun)
\`\`\`

Signature có thể là:

\`\`\`text
operation.name       = retryFailedItems
operation.returnType = int
operation.signature:
  0: int
  1: boolean
\`\`\`

Client gọi:

\`\`\`java
connection.invoke(
    objectName,
    "retryFailedItems",
    new Object[] { 10, true },
    new String[] { "int", "boolean" }
);
\`\`\`

Tuy nhiên việc thử invoke chỉ nên diễn ra trong test/lab khi operation có side effect, không phải bước inspection metadata mặc định.

### 11.1. Kiểm tra chính xác một operation

\`\`\`java
import java.util.Arrays;
import javax.management.MBeanOperationInfo;

boolean hasPause = Arrays.stream(info.getOperations())
    .anyMatch(o ->
        o.getName().equals("requestPause")
        && o.getSignature().length == 0
        && o.getReturnType().equals("void")
    );

if (!hasPause) {
    throw new AssertionError(
        "Expected requestPause() operation is missing"
    );
}
\`\`\`

Khi có overloaded operations, tên alone không đủ; cần so sánh signature. Khi thay đổi primitive \`int\` thành reference \`java.lang.Integer\`, JMX signature có thể khác dù một số code ứng dụng coi chúng tương tự.

### 11.2. Kiểm tra operation không được phép

\`\`\`java
boolean exposesInternalMethod =
    Arrays.stream(info.getOperations())
        .anyMatch(o ->
            o.getName().equals("stopAllServicesInternal")
        );

if (exposesInternalMethod) {
    throw new AssertionError(
        "Internal operation must not be exported"
    );
}
\`\`\`

Với \`DynamicMBean\`, cần bổ sung kiểm tra implementation \`invoke\` thực sự từ chối các tên không được phép. Việc giấu method khỏi metadata không bảo đảm code dynamic không xử lý lời gọi thủ công theo tên.

## 12. Kiểm tra descriptions và metadata tham số

Nếu Spring annotation ghi:

\`\`\`java
@ManagedOperation(
    description = "Request a graceful pause of the import job"
)
public void requestPause() { }
\`\`\`

thì trong cấu hình annotation-based assembler phù hợp, \`MBeanOperationInfo.getDescription()\` nên thể hiện ý nghĩa tương ứng.

Với tham số:

\`\`\`java
@ManagedOperationParameters({
    @ManagedOperationParameter(
        name = "limit",
        description = "Maximum retry items (1..100)"
    )
})
\`\`\`

\`MBeanParameterInfo\` có thể cung cấp tên, kiểu và mô tả. Khi công cụ quản trị hiện tên như \`p1\` hoặc description rỗng, có thể cần xem assembler/annotation thay vì cho rằng Java compiler không lưu tên biến.

Description không là validation hoặc authorization; ứng dụng vẫn phải từ chối input ngoài phạm vi và bảo vệ operation có tác dụng phụ.

## 13. Descriptor: dữ liệu bổ sung cần xem đúng cấp

Một \`MBeanInfo\` và mỗi \`MBeanFeatureInfo\` đều có thể có \`Descriptor\`:

\`\`\`java
import javax.management.Descriptor;

Descriptor beanDescriptor = info.getDescriptor();

for (String field : beanDescriptor.getFieldNames()) {
    System.out.println(
        field + "=" + beanDescriptor.getFieldValue(field)
    );
}
\`\`\`

Tương tự, đọc descriptor của từng attribute hoặc operation:

\`\`\`java
for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "%s descriptor=%s%n",
        attribute.getName(),
        attribute.getDescriptor()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.printf(
        "%s descriptor=%s%n",
        operation.getName(),
        operation.getDescriptor()
    );
}
\`\`\`

Một số Model MBean descriptor có field như \`currencyTimeLimit\`, \`persistPolicy\`, \`persistPeriod\`, \`persistName\` hoặc \`persistLocation\`. Chúng chỉ có hành vi thực tế khi một implementation tương ứng sử dụng metadata. Không coi các field này như Spring Cache TTL hoặc persistence của database.

**Lưu ý:** descriptor cũng có thể chứa metadata tùy chỉnh hoặc thông tin nội bộ. Đừng in tất cả descriptor vào log production công khai mà chưa xem chính sách bảo mật.

## 14. ModelMBeanInfo và MXBean metadata

### 14.1. Model MBean

Spring exporter với metadata assembler có thể xây dựng cấu trúc metadata theo mô hình Model MBean. Có thể kiểm tra:

\`\`\`java
import javax.management.modelmbean.ModelMBeanInfo;

if (info instanceof ModelMBeanInfo) {
    System.out.println("Model MBean metadata available");
}
\`\`\`

Một \`ModelMBeanInfo\` có các API bổ sung để lấy descriptor theo loại feature. Cần dùng khi bạn muốn đọc những field Model MBean đặc thù.

### 14.2. MXBean

MXBean ánh xạ một số kiểu Java sang dữ liệu mở tiêu chuẩn của JMX, có thể sử dụng \`CompositeData\` hoặc \`TabularData\`. Khi kiểm tra một MXBean:

- Đọc kiểu thuộc tính mà JMX công bố, không mặc định trùng class nghiệp vụ.
- Kiểm tra \`Descriptor\` hoặc \`OpenType\` khi cần hiểu cấu trúc dữ liệu.
- Với \`CompositeData\`, client không nhất thiết cần class implementation của ứng dụng.
- Đừng suy ra rằng một MBean có dữ liệu dạng \`CompositeData\` thì mọi operation đều an toàn hoặc read-only.

### 14.3. MBeanInfo khác runtime value

\`MBeanInfo\` mô tả **schema**, không cung cấp tất cả giá trị hiện tại của attribute. Muốn lấy giá trị cần \`getAttribute\` hoặc \`getAttributes\`, nhưng việc đọc getter có thể gây chi phí hoặc tác dụng phụ nếu implementation kém an toàn. Trong quá trình kiểm tra contract, metadata thường là điểm khởi đầu an toàn hơn.

## 15. Phân biệt MBeanServer và MBeanServerConnection

\`MBeanServer\` là registry/server nằm trong JVM hoặc môi trường quản trị. \`MBeanServerConnection\` là giao diện client có thể dùng cho local hoặc remote.

\`\`\`java
MBeanServer local = ManagementFactory.getPlatformMBeanServer();
MBeanInfo localInfo = local.getMBeanInfo(name);
\`\`\`

Đối với remote:

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://localhost:9010/jmxrmi"
);

try (JMXConnector connector =
         JMXConnectorFactory.connect(url)) {
    MBeanServerConnection remote =
        connector.getMBeanServerConnection();

    MBeanInfo remoteInfo = remote.getMBeanInfo(name);
    System.out.println(remoteInfo.getDescription());
}
\`\`\`

Ví dụ remote giả định endpoint local lab tồn tại và quyền kết nối cho phép. Trong production cần cấu hình TLS, authentication và giới hạn mạng phù hợp. Không mở remote JMX chỉ để phục vụ bài kiểm tra hợp đồng nếu việc kiểm tra local bằng MBeanServer đã đủ.

## 16. Xử lý trường hợp không tìm thấy MBean

Khi \`getMBeanInfo(name)\` ném \`InstanceNotFoundException\`, đi theo các bước:

1. **Kiểm tra đúng ObjectName:** domain, key properties và giá trị được quote.
2. **Kiểm tra đúng server:** exporter có đang dùng platform MBeanServer hay một custom server?
3. **Kiểm tra exporter:** bean có trong \`setBeans\`, được auto-detect hoặc được component phù hợp đăng ký chưa?
4. **Kiểm tra assembler:** annotation và interface có được diễn giải không?
5. **Kiểm tra lifecycle:** context đã khởi tạo xong chưa, MBean có bị unregister chưa?
6. **Kiểm tra xung đột tên:** MBean có bị bỏ qua hoặc thay thế theo registration policy không?
7. **Kiểm tra chính sách bảo mật:** remote connection có đủ quyền xem metadata không?

Có thể tìm tên trong phạm vi domain:

\`\`\`java
import javax.management.ObjectName;

for (ObjectName found :
        server.queryNames(
            new ObjectName("com.example.jobs:*"),
            null)) {
    System.out.println(found.getCanonicalName());
}
\`\`\`

Không nên quét toàn bộ MBeanServer từ một hệ thống production rồi ghi tất cả metadata ra log công khai nếu không có lý do vận hành cụ thể.

## 17. Sai lệch thường gặp giữa annotation/interface và metadata

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Class có \`@ManagedResource\` nhưng không có MBean | Không có exporter hoặc bean không được chọn. | Kiểm tra Spring JMX config và \`isRegistered\`. |
| Description trống | Assembler không đọc annotation hoặc metadata không được chuyển. | Kiểm tra \`MetadataMBeanInfoAssembler\`. |
| Operation thiếu | Không được annotate hoặc interface/assembler chọn khác. | So sánh method với runtime operation list. |
| Xuất thừa public method | Autodetect/reflective assembler quá rộng. | Dùng allowlist interface hoặc annotation-based metadata. |
| Attribute writable ngoài ý muốn | Setter được xuất hoặc strategy introspection. | Kiểm tra \`isWritable\`, giới hạn setter. |
| Không đúng ObjectName | Naming strategy, bean key hoặc domain khác. | Truy \`queryNames\` trong domain liên quan. |
| MBean cũ vẫn còn | Registration policy ignore hoặc cleanup không đúng. | Kiểm tra ownership, lifecycle và policy. |
| Client không hiểu kiểu MXBean | Cách map dữ liệu, version hoặc open data schema khác. | Đọc metadata và OpenType theo JMX API. |
| Kết quả local và remote khác nhau | Client trỏ MBeanServer/JVM khác nhau. | Xác định PID, endpoint và ObjectName. |
| Code đúng nhưng test thất bại ngẫu nhiên | MBeanServer dùng chung, trùng ObjectName hoặc test song song. | Dùng domain/name duy nhất, cleanup chặt. |

## 18. Viết test tự động bảo vệ hợp đồng JMX

Một bài kiểm tra có thể chạy cùng Spring ApplicationContext, sau khi exporter khởi tạo:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.util.Arrays;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.jobs:type=ImportJob,name=Daily"
);

if (!server.isRegistered(name)) {
    throw new AssertionError("Expected MBean missing");
}

MBeanInfo info = server.getMBeanInfo(name);

MBeanAttributeInfo count =
    Arrays.stream(info.getAttributes())
        .filter(a -> a.getName().equals("CompletedCount"))
        .findFirst()
        .orElseThrow(() ->
            new AssertionError("Missing CompletedCount")
        );

if (!count.isReadable() || count.isWritable()) {
    throw new AssertionError(
        "CompletedCount must be read-only"
    );
}

boolean hasPause =
    Arrays.stream(info.getOperations())
        .anyMatch(op ->
            op.getName().equals("requestPause")
            && op.getSignature().length == 0
            && "void".equals(op.getReturnType())
        );

if (!hasPause) {
    throw new AssertionError("Missing requestPause()");
}

boolean leaked = Arrays.stream(info.getOperations())
    .anyMatch(op ->
        op.getName().equals("readInternalSecret")
    );

if (leaked) {
    throw new AssertionError(
        "Internal method unexpectedly exported"
    );
}
\`\`\`

Đây là test *contract*, không cần thực thi operation. Nó bảo vệ tên, signature, khả năng đọc/ghi và ngăn export API nội bộ. Với test thực tế nên dùng JUnit và assert trên Spring context được cấu hình trong test.

### 18.1. Nên kiểm tra allowlist hay denylist?

Denylist chỉ chặn những method nguy hiểm đã biết. Allowlist là danh sách các attribute/operation được phép xuất nên hữu ích hơn khi muốn ngăn future method bị lộ qua reflective assembler.

Ví dụ kỳ vọng:

\`\`\`text
Attributes allowed:
  Running
  CompletedCount

Operations allowed:
  requestPause()
\`\`\`

Một bài kiểm tra có thể so sánh danh sách canonical name/signature với expected set; khi developer thêm operation mới, test buộc họ chủ động cập nhật hợp đồng.

Không nên kiểm tra mọi metadata luôn đúng một chuỗi mô tả dài nếu wording có thể chỉnh nhẹ thường xuyên, trừ khi description là phần hợp đồng được yêu cầu ổn định.

## 19. Kiểm tra lifecycle của exported MBean

Khi Spring context đóng, \`MBeanExporter\` thông thường unregister những MBean nó đã quản lý. Có thể kiểm tra:

\`\`\`java
AnnotationConfigApplicationContext context =
    new AnnotationConfigApplicationContext(JmxExportConfig.class);

try {
    if (!server.isRegistered(name)) {
        throw new AssertionError(
            "MBean not registered after context startup"
        );
    }
} finally {
    context.close();
}

if (server.isRegistered(name)) {
    throw new AssertionError(
        "MBean still registered after context close"
    );
}
\`\`\`

Đoạn này giả định không có exporter khác đang sở hữu cùng \`ObjectName\` và một \`MBeanServer\` được dùng nhất quán. Nếu context chưa được đóng bình thường (JVM kill cứng), không thể bảo đảm callback cleanup được thực thi.

Đừng unregister MBean của ứng dụng production chỉ để thử contract trong khi hệ thống đang phục vụ người dùng. Các kiểm tra lifecycle có tác dụng thay đổi trạng thái nên thực hiện trong môi trường test.

## 20. Mẫu checklist kiểm tra MBeanInfo sau export

Khi một MBean mới được thêm vào Spring, thực hiện theo thứ tự:

1. Xác định **MBeanServer** thực sự mà exporter sử dụng.
2. Xác định \`ObjectName\` chính xác.
3. Kiểm tra \`isRegistered(name)\` sau khi context khởi tạo.
4. Đọc \`MBeanInfo\` bằng \`getMBeanInfo(name)\`.
5. So sánh tên và kiểu **attributes** với hợp đồng mong đợi.
6. Kiểm tra **readable/writable/isIs** cho từng attribute quan trọng.
7. So sánh tên và signature **operations**.
8. Kiểm tra description và parameter metadata khi cần.
9. Kiểm tra descriptor/OpenType/ModelMBean metadata nếu có.
10. Kiểm tra **không có** attribute/operation nội bộ hoặc nhạy cảm.
11. Xem constructor/notification metadata nếu chức năng liên quan.
12. Xác nhận JConsole hoặc remote client dùng đúng JVM/server.
13. Chỉ thực hiện test có side effect trong môi trường phù hợp.
14. Kiểm tra cleanup sau khi đóng context trong integration test.
15. Nếu thay đổi hợp đồng, ghi nhận compatibility/version cho client phụ thuộc vào JMX.

Đây là quy trình để người học vận dụng khi phát triển JMX; khi viết code tự động, có thể dùng một expected schema nhỏ thay vì phụ thuộc vào cách sắp xếp danh sách metadata.

## 21. Các bài tập thực hành

### Bài tập 1 — Standard MBean

Tạo \`ImportJobMonitorMBean\` và \`ImportJobMonitor\`. Đăng ký lên platform MBeanServer, đọc \`MBeanInfo\`, xác nhận có \`Running\`, \`CompletedCount\`, \`requestPause\`, và không có \`InternalCredentialAlias\`.

**Mục tiêu:** hiểu interface quản trị quyết định bề mặt Standard MBean.

### Bài tập 2 — Spring annotation

Tạo một \`@ManagedResource\` có hai \`@ManagedAttribute\` và một \`@ManagedOperation\`. Export qua metadata assembler phù hợp; kiểm tra description và metadata runtime.

**Mục tiêu:** chứng minh annotation có đi tới MBeanInfo sau export.

### Bài tập 3 — Negative test

Thêm method public \`deleteAllJobsInternal()\` vào Spring bean nhưng không annotate. Viết phép kiểm tra khẳng định method này không xuất hiện trong \`MBeanInfo.getOperations()\`.

**Mục tiêu:** phát hiện exporter hoặc assembler xuất quá nhiều method.

### Bài tập 4 — Signature

Tạo \`retry(int limit, boolean dryRun)\`, khai báo parameter metadata và kiểm tra \`MBeanOperationInfo.getSignature()\`. Thử đổi \`int\` thành \`Integer\` và quan sát hợp đồng thay đổi.

**Mục tiêu:** hiểu signature là một phần API JMX.

### Bài tập 5 — Descriptor

Đọc \`MBeanInfo.getDescriptor()\` và descriptor của từng attribute/operation, ghi nhận field \`currencyTimeLimit\` nếu có. Giải thích tại sao descriptor không đồng nghĩa có cache hoặc persistence nghiệp vụ.

**Mục tiêu:** phân biệt metadata với behavior.

### Bài tập 6 — Wrong MBeanServer

Cấu hình exporter dùng custom MBeanServer trong môi trường lab. So sánh kết quả \`isRegistered\` từ custom server và platform server.

**Mục tiêu:** biết kiểm tra đúng registry thay vì suy đoán.

### Bài tập 7 — Lifecycle

Khởi tạo Spring context, xác nhận MBean đăng ký; đóng context rồi xác nhận MBean được hủy. Dùng tên riêng để tránh xung đột giữa các test.

**Mục tiêu:** hiểu vòng đời exporter và cleanup.

## 22. Câu hỏi ôn tập

**1. Vì sao phải đọc MBeanInfo runtime thay vì chỉ đọc @ManagedResource?** Vì exporter, naming strategy, assembler và lifecycle quyết định những gì thực sự được đăng ký và công bố.

**2. \`isRegistered(name)\` trả true có nghĩa hợp đồng đúng hoàn toàn không?** Không. Nó chỉ xác nhận tên đang tồn tại; cần kiểm tra attributes/operations/signatures.

**3. API nào cho biết attribute có writable không?** \`MBeanAttributeInfo.isWritable()\`.

**4. API nào cho biết signature của operation?** \`MBeanOperationInfo.getSignature()\`.

**5. Nếu description trống, cần xem gì?** Metadata assembler và cách Spring JMX exporter xử lý annotation.

**6. Một Java public method ngoài management interface có tự trở thành operation Standard MBean không?** Không, nếu dùng Standard MBean đúng quy ước.

**7. MBeanInfo có chứa giá trị attribute hiện tại không?** Không. Metadata mô tả schema; muốn lấy giá trị cần \`getAttribute\`.

**8. Tại sao nên có negative tests?** Để phát hiện việc xuất nhầm method hoặc attribute nội bộ.

**9. Nếu client không thấy MBean, cần kiểm tra những gì đầu tiên?** ObjectName, đúng MBeanServer, exporter, lifecycle và registration policy.

**10. Có nên gọi \`requestPause()\` để kiểm tra nó tồn tại không?** Không cần. Dùng \`MBeanInfo\` để inspection an toàn; gọi operation chỉ trong test phù hợp.

## 23. Tổng kết

Kiểm tra **MBeanInfo thực tế sau khi export** là bước cần thiết để xác nhận Spring đã công bố đúng hợp đồng JMX. \`MBeanServer.getMBeanInfo\` cung cấp metadata của attributes, operations, constructors, notifications và descriptors; những thông tin này giúp phát hiện sai ObjectName, sai assembler, sai quyền read/write, thiếu operation hoặc rò rỉ API nội bộ.

Mục tiêu là bảo vệ bề mặt quản trị ở **runtime**, không chỉ tin vào annotation hoặc interface trên source code. Một bộ test contract nhỏ, dựa vào allowlist và negative assertions, giúp ứng dụng Spring giữ giao diện quản trị ổn định và an toàn qua các lần thay đổi.

## Tài liệu tham khảo

- Java SE 21 — \`MBeanInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
- Java SE 21 — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 — \`MBeanAttributeInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanAttributeInfo.html
- Java SE 21 — \`MBeanOperationInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanOperationInfo.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Javadoc — \`MetadataMBeanInfoAssembler\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/assembler/MetadataMBeanInfoAssembler.html