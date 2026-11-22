# Gọi operation với chữ ký và tham số trong MBeanServer

> **Chủ đề:** Spring Framework JMX  
> **Nhóm kiến thức:** MBeanServer  
> **Bài học:** Gọi operation với chữ ký và tham số

## 1. Mục tiêu

Sau bài này, bạn có thể:

- Giải thích cơ chế **\`MBeanServer.invoke(ObjectName, String, Object[], String[])\`** để gọi một operation đã được MBean công bố.
- Phân biệt **tên operation**, **mảng giá trị tham số** (\`params\`) và **mảng tên kiểu tham số** (\`signature\`).
- Đọc \`MBeanInfo\`/\`MBeanOperationInfo\` để tìm hợp đồng thực tế trước khi invoke.
- Gọi operation không tham số, có một hoặc nhiều tham số, và xử lý trả về.
- Nhận diện lỗi khi sai tên, số lượng/kiểu tham số, MBean chưa đăng ký hoặc method thực thi ném exception.
- Hiểu vai trò của Spring JMX exporter và client JMX trong đường đi của lời gọi.

## 2. Mô hình tư duy: invoke là một lời gọi theo hợp đồng quản trị

Khi một Spring bean được đăng ký thành MBean, các operation được expose tạo nên **hợp đồng quản trị** của nó. JMX client không tự tìm method bất kỳ trên Java object; client chuyển yêu cầu tới \`MBeanServer\`, dùng \`ObjectName\` xác định MBean, rồi dùng **tên operation + chữ ký tham số** để tìm operation tương ứng.

\`\`\`text
Spring Bean
  |
  | MBeanExporter / ModelMBean hoặc Standard MBean
  v
MBeanServer
  |
  +-- ObjectName: training.jmx:type=JobController,name=primary
  |       +-- Attributes
  |       +-- Operations
  |             +-- refresh()
  |             +-- resize(int)
  |             +-- move(java.lang.String, int)
  |
  ^ MBeanServer.invoke(ObjectName, name, params, signature)
  |
JMX client / JConsole / remote JMX connector
\`\`\`

Trong mô hình này, \`MBeanServer\` là điểm định tuyến và thực thi. Nó cần biết **MBean nào**, **operation nào** và **cách diễn giải từng đối số**. Việc Spring tạo bean hoặc export MBean không thay thế hợp đồng JMX: client vẫn phải gọi đúng operation được công bố.

Đừng nhầm \`invoke(...)\` với \`getAttribute(...)\` hoặc \`setAttribute(...)\`. Một getter được export dưới dạng JMX attribute thường nên được truy cập bằng \`getAttribute\`, còn một hành động như \`reset\`, \`refresh\`, \`resize\` có thể được công bố là JMX operation.

## 3. API cốt lõi

Phương thức quan trọng trong \`javax.management.MBeanServer\`:

\`\`\`java
Object invoke(
    ObjectName name,
    String operationName,
    Object[] params,
    String[] signature
) throws InstanceNotFoundException,
         MBeanException,
         ReflectionException;
\`\`\`

Ý nghĩa từng đối số:

| Đối số | Vai trò | Ví dụ |
|---|---|---|
| \`name\` | \`ObjectName\` định danh MBean đã đăng ký | \`training.jmx:type=JobController,name=primary\` |
| \`operationName\` | Tên operation được MBean công bố | \`"resize"\` |
| \`params\` | Giá trị đối số theo đúng thứ tự của chữ ký | \`new Object[] { 8 }\` |
| \`signature\` | Tên kiểu Java đầy đủ tương ứng từng tham số | \`new String[] { "int" }\` |
| Giá trị trả về | \`Object\`, phụ thuộc kiểu trả về của operation; operation \`void\` thường trả về \`null\` | \`Integer\`, \`String\`, \`null\` |

**Hai mảng \`params\` và \`signature\` phải song hành theo vị trí.** Phần tử thứ \`i\` của \`params\` là giá trị cho tham số có kiểu được mô tả ở phần tử thứ \`i\` của \`signature\`.

Ví dụ:

\`\`\`java
server.invoke(
    objectName,
    "move",
    new Object[] { "retry", 3 },
    new String[] { "java.lang.String", "int" }
);
\`\`\`

Lệnh này yêu cầu operation có chữ ký tương ứng \`move(String, int)\`. Hai kiểu trong \`signature\` **không phải** tên biến \`queueName\`, \`count\`; đó là tên kiểu theo metadata JMX.

## 4. Vì sao cần truyền signature?

Java hỗ trợ overload: các method có thể trùng tên nhưng khác danh sách kiểu tham số.

\`\`\`java
void resize(int size)
void resize(long size)
void resize(String profile)
\`\`\`

Nếu client chỉ gửi tên \`resize\`, hệ thống không đủ thông tin để lựa chọn một overload một cách chính xác. \`signature\` mô tả kiểu mong muốn:

\`\`\`java
new String[] { "int" }                  // resize(int)
new String[] { "long" }                 // resize(long)
new String[] { "java.lang.String" }     // resize(String)
\`\`\`

Trong JMX, việc so khớp thường dựa vào chữ ký operation được công bố, thay vì thử cơ chế ép kiểu tùy ý như khi biên dịch Java. Vì thế truyền giá trị \`Integer.valueOf(8)\` cùng chữ ký \`"java.lang.Integer"\` **không thay thế** chữ ký \`"int"\` nếu operation khai báo tham số \`int\`.

Phân biệt hai lớp thông tin:

- **Kiểu khai báo của tham số**: \`int\`, \`long\`, \`boolean\`, \`java.lang.String\`, ...
- **Đối tượng thực tế vận chuyển trong \`Object[]\`**: các primitive như \`int\` được boxing thành wrapper (\`Integer\`), trong khi chuỗi là \`String\`.

Ví dụ \`resize(int)\`:

\`\`\`java
Object[] params = { Integer.valueOf(8) };
String[] signature = { "int" };

server.invoke(objectName, "resize", params, signature);
\`\`\`

Không ghi \`"Integer"\` chỉ vì phần tử \`params[0]\` là một \`Integer\`. Với kiểu reference, sử dụng tên lớp đầy đủ (ví dụ \`java.lang.String\`), không dùng tên ngắn \`String\`.

## 5. Ví dụ đầy đủ: tạo Standard MBean và gọi operation

Ví dụ dưới đây chạy trong một JVM với platform MBeanServer, không yêu cầu mở remote JMX. Một Standard MBean được định nghĩa qua interface có hậu tố \`MBean\` và class triển khai tương ứng.

### 5.1. Hợp đồng quản trị

\`\`\`java
package example.jmx;

public interface JobControllerMBean {
    void refresh();

    void resize(int workers);

    String move(String queueName, int batchSize);

    int getWorkerCount();
}
\`\`\`

### 5.2. Implementation

\`\`\`java
package example.jmx;

public class JobController implements JobControllerMBean {

    private int workerCount = 2;

    @Override
    public void refresh() {
        System.out.println("Refreshing scheduler");
    }

    @Override
    public void resize(int workers) {
        if (workers <= 0) {
            throw new IllegalArgumentException(
                "workers must be greater than zero"
            );
        }
        workerCount = workers;
    }

    @Override
    public String move(String queueName, int batchSize) {
        if (queueName == null || queueName.isBlank()) {
            throw new IllegalArgumentException("queueName is required");
        }
        if (batchSize <= 0) {
            throw new IllegalArgumentException("batchSize must be positive");
        }
        return "Moved " + batchSize + " item(s) to " + queueName;
    }

    @Override
    public int getWorkerCount() {
        return workerCount;
    }
}
\`\`\`

Các method trong interface \`JobControllerMBean\` tạo nên bề mặt quản trị. \`getWorkerCount()\` được biểu diễn thành attribute \`WorkerCount\`; các method \`refresh\`, \`resize\`, \`move\` là operation. Việc MBean implementation có thêm các public method khác không đồng nghĩa các method ấy cũng được expose.

### 5.3. Đăng ký rồi invoke

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class JmxInvokeDemo {

    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
            "training.jmx:type=JobController,name=primary"
        );

        // Đăng ký Standard MBean; ví dụ giả định tên này chưa được dùng.
        server.registerMBean(new JobController(), name);

        try {
            // 1) Operation không có tham số
            server.invoke(
                name,
                "refresh",
                new Object[0],
                new String[0]
            );

            // 2) Operation nhận int
            server.invoke(
                name,
                "resize",
                new Object[] { 8 },
                new String[] { "int" }
            );

            // 3) Operation nhận String + int và trả về String
            Object outcome = server.invoke(
                name,
                "move",
                new Object[] { "retry", 3 },
                new String[] { "java.lang.String", "int" }
            );
            System.out.println(outcome);

            // Attribute read: khác với operation invoke
            Object current = server.getAttribute(
                name,
                "WorkerCount"
            );
            System.out.println("workers = " + current);
        } finally {
            server.unregisterMBean(name);
        }
    }
}
\`\`\`

Kết quả minh họa:

\`\`\`text
Refreshing scheduler
Moved 3 item(s) to retry
workers = 8
\`\`\`

Trình tự xử lý:

\`\`\`text
invoke("resize", [8], ["int"])
      |
      v
MBeanServer tìm ObjectName
      |
      v
MBeanServer định tuyến operation resize(int)
      |
      v
JobController.resize(8)
      |
      v
Trạng thái workerCount được cập nhật
      |
      v
getAttribute("WorkerCount") -> 8
\`\`\`

Cần nhớ: mặc dù ví dụ chạy qua API JMX, \`workerCount\` là trạng thái của đối tượng implementation. Khi gọi operation làm thay đổi trạng thái, các lần đọc attribute sau đó phản ánh trạng thái mới.

## 6. Gọi không tham số và khác biệt giữa mảng rỗng với null

Operation không tham số được gọi một cách rõ ràng với:

\`\`\`java
server.invoke(
    name,
    "refresh",
    new Object[0],
    new String[0]
);
\`\`\`

API JMX cho phép truyền \`null\` cho \`params\` và \`signature\` trong tình huống không có tham số, nhưng dùng hai mảng rỗng làm ý định của client dễ đọc hơn, nhất là khi xây dựng lời gọi từ metadata. Không truyền mảng chứa một phần tử \`null\` nếu operation **không có tham số**: \`new Object[]{ null }\` nghĩa là một đối số, không phải không có đối số.

So sánh:

\`\`\`java
// refresh(): đúng
new Object[0];
new String[0];

// setLabel(String): một đối số có giá trị null
new Object[] { null };
new String[] { "java.lang.String" };
\`\`\`

Đối với operation nhận kiểu primitive, \`null\` không thể được unbox thành giá trị primitive hợp lệ. Với tham số reference, việc chấp nhận \`null\` còn phụ thuộc implementation của MBean.

## 7. Đọc metadata trước khi gọi

Không nên đoán chữ ký chỉ dựa trên code hoặc tên hiển thị trong UI. Với MBean đã đăng ký, \`MBeanServer.getMBeanInfo(ObjectName)\` trả về metadata, trong đó có danh sách operation và các tham số tương ứng.

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;

// server và name đã được khởi tạo.
MBeanInfo info = server.getMBeanInfo(name);

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.print(op.getName() + "(");

    MBeanParameterInfo[] parameters = op.getSignature();
    for (int i = 0; i < parameters.length; i++) {
        if (i > 0) {
            System.out.print(", ");
        }
        System.out.print(parameters[i].getType());
    }

    System.out.println(") -> " + op.getReturnType());
}
\`\`\`

Với ví dụ ở trên, metadata tương ứng về bản chất có:

\`\`\`text
refresh() -> void
resize(int) -> void
move(java.lang.String, int) -> java.lang.String
\`\`\`

Tên operation và tên kiểu trong \`MBeanOperationInfo\`/\`MBeanParameterInfo\` là điểm tham chiếu để dựng \`signature\` chính xác. Mã client tổng quát có thể lọc theo \`op.getName()\`, số tham số và \`getType()\` để chọn operation phù hợp, sau đó chuyển đổi dữ liệu nhập từ UI thành đối tượng Java đúng kiểu.

### Xây signature trực tiếp từ MBeanOperationInfo

\`\`\`java
import java.util.Arrays;
import javax.management.MBeanOperationInfo;

MBeanOperationInfo moveOperation = Arrays.stream(
        server.getMBeanInfo(name).getOperations()
    )
    .filter(op -> op.getName().equals("move"))
    .filter(op -> op.getSignature().length == 2)
    .findFirst()
    .orElseThrow();

String[] signature = Arrays.stream(
        moveOperation.getSignature()
    )
    .map(param -> param.getType())
    .toArray(String[]::new);
\`\`\`

Ví dụ này chỉ lấy overload đầu tiên tên \`move\` có hai tham số; ở ứng dụng hỗ trợ overload thực sự, cần so khớp **toàn bộ danh sách kiểu**, tránh tùy tiện chọn overload đầu tiên.

## 8. Sai chữ ký và lỗi thường gặp

### Sai kiểu primitive/wrapper

\`\`\`java
// Operation thực tế là resize(int)
server.invoke(
    name,
    "resize",
    new Object[] { 8 },
    new String[] { "java.lang.Integer" } // Không khớp "int"
);
\`\`\`

Một \`Integer\` trong \`params\` không làm chữ ký khai báo đổi từ \`int\` thành \`java.lang.Integer\`. Phải dùng \`new String[]{"int"}\`.

### Sai thứ tự tham số

\`\`\`java
// Thực tế: move(String, int)
server.invoke(
    name,
    "move",
    new Object[] { 3, "retry" },
    new String[] { "int", "java.lang.String" }
);
\`\`\`

Đây là một hợp đồng khác \`move(int, String)\`, không khớp operation \`move(String, int)\`.

### Thiếu tham số hoặc lệch độ dài hai mảng

\`\`\`java
server.invoke(
    name,
    "move",
    new Object[] { "retry", 3 },
    new String[] { "java.lang.String" }
);
\`\`\`

\`params.length\` và \`signature.length\` không khớp. Client nên kiểm tra trước khi gửi. Ngay cả khi chúng bằng nhau, vẫn phải bảo đảm từng kiểu khớp chữ ký operation đã công bố.

### Đúng chữ ký nhưng implementation ném exception

\`\`\`java
server.invoke(
    name,
    "resize",
    new Object[] { -1 },
    new String[] { "int" }
);
\`\`\`

JMX đã tìm được \`resize(int)\`, nhưng logic nghiệp vụ từ chối \`-1\`. Với Standard MBean, exception từ method được gọi có thể được bao bọc trong \`MBeanException\` nếu là checked exception, hoặc \`RuntimeMBeanException\` nếu là runtime exception. Vì vậy cần phân biệt **lỗi định tuyến/chữ ký** và **lỗi khi thực thi method**.

## 9. Xử lý exception theo tầng

Các exception quan trọng với \`MBeanServer.invoke\`:

| Exception | Ý nghĩa thực tế | Hướng xử lý |
|---|---|---|
| \`InstanceNotFoundException\` | Không tìm thấy MBean theo \`ObjectName\`. | Kiểm tra đăng ký, tên và đúng MBeanServer. |
| \`ReflectionException\` | Lỗi phản chiếu hoặc không thể định tuyến/khớp operation. | Đối chiếu \`getMBeanInfo\` và \`signature\`; xem nguyên nhân bên trong. |
| \`MBeanException\` | Method MBean ném một checked exception được JMX bao bọc. | Đọc \`getTargetException()\` hoặc cause. |
| \`RuntimeMBeanException\` | Runtime exception phát sinh trong MBean, được JMX bao bọc. | Xem exception gốc và input nghiệp vụ. |
| \`RuntimeErrorException\` | Một \`Error\` phát sinh từ việc thực thi MBean và được JMX bao bọc. | Xem lỗi nghiêm trọng từ implementation/runtime. |
| \`SecurityException\` | Quyền gọi bị chặn theo cơ chế security hiện có. | Kiểm tra policy, quyền và cách kết nối. |

Mẫu xử lý có mục tiêu:

\`\`\`java
import javax.management.InstanceNotFoundException;
import javax.management.MBeanException;
import javax.management.ReflectionException;
import javax.management.RuntimeMBeanException;

try {
    Object result = server.invoke(
        name,
        "resize",
        new Object[] { 8 },
        new String[] { "int" }
    );
    System.out.println("Result: " + result);
} catch (InstanceNotFoundException e) {
    System.err.println("MBean is not registered: " + name);
} catch (ReflectionException e) {
    System.err.println("Operation/signature mismatch: " + e);
} catch (MBeanException e) {
    System.err.println(
        "MBean checked exception: " + e.getTargetException()
    );
} catch (RuntimeMBeanException e) {
    System.err.println(
        "MBean runtime exception: " + e.getTargetException()
    );
}
\`\`\`

Thông điệp “operation/signature mismatch” là **gợi ý chẩn đoán** khi nhận \`ReflectionException\`, không phải lời khẳng định mọi \`ReflectionException\` đều do sai signature. Kiểm tra cause và metadata để xác định nguyên nhân thật.

## 10. Liên hệ với Spring Framework JMX

Trong Spring, \`MBeanExporter\` có thể xuất bản bean thường dưới dạng MBean với metadata từ \`@ManagedResource\`, \`@ManagedOperation\`, \`@ManagedAttribute\` hoặc cấu hình assembler. Client JMX vẫn gọi vào \`MBeanServer\` theo contract JMX.

Ví dụ bean Spring:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "training.jmx:type=JobController,name=spring"
)
public class SpringJobController {

    private int workerCount = 2;

    @ManagedOperation(description = "Resize worker pool")
    @ManagedOperationParameters({
        @ManagedOperationParameter(
            name = "workers",
            description = "New worker count"
        )
    })
    public void resize(int workers) {
        if (workers <= 0) {
            throw new IllegalArgumentException(
                "workers must be positive"
            );
        }
        this.workerCount = workers;
    }
}
\`\`\`

Cấu hình export:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfig {
}
\`\`\`

Khi bean được export thành công, client gọi:

\`\`\`java
ObjectName springBean = new ObjectName(
    "training.jmx:type=JobController,name=spring"
);

server.invoke(
    springBean,
    "resize",
    new Object[] { 6 },
    new String[] { "int" }
);
\`\`\`

Ví dụ \`server\` ở đây phải là **chính MBeanServer mà Spring exporter sử dụng**. Khi dùng platform MBeanServer, có thể lấy qua \`ManagementFactory.getPlatformMBeanServer()\`; khi export vào một MBeanServer khác, phải kết nối đúng server đó.

Đường đi:

\`\`\`text
JMX Client
  -> MBeanServer.invoke(name, "resize", [6], ["int"])
  -> MBean implementation / Spring ModelMBean adapter
  -> SpringJobController.resize(6)
  -> state được cập nhật
\`\`\`

\`@ManagedOperationParameters\` mô tả **tên và ý nghĩa** tham số để công cụ đọc metadata; nó không đổi kiểu Java \`int\` hoặc thứ tự tham số. \`signature\` trong \`invoke\` vẫn dùng tên kiểu được JMX công bố.

### JConsole và operation

Trong tab MBeans, JConsole hiển thị các operation công bố cùng các trường nhập tham số được hỗ trợ. Khi nhấn nút invoke, công cụ gửi yêu cầu JMX có tên operation và chữ ký tương ứng. Khả năng nhập và chuyển đổi một kiểu dữ liệu cụ thể tùy client; không phải tất cả kiểu Java đều được UI JConsole hỗ trợ trực tiếp. Đối với automation, \`MBeanServerConnection.invoke(...)\` thường cho phép kiểm soát chính xác đối số/chữ ký hơn.

## 11. MBeanServerConnection và remote invocation

Một client từ xa thường giữ \`MBeanServerConnection\`, không nhất thiết có \`MBeanServer\` local. \`MBeanServerConnection\` cung cấp cùng thao tác \`invoke\`.

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

// URL minh họa: phụ thuộc cấu hình connector RMI thực tế.
JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://localhost:9999/jmxrmi"
);

try (JMXConnector connector =
         JMXConnectorFactory.connect(url)) {

    MBeanServerConnection connection =
        connector.getMBeanServerConnection();

    ObjectName name = new ObjectName(
        "training.jmx:type=JobController,name=primary"
    );

    Object result = connection.invoke(
        name,
        "move",
        new Object[] { "retry", 3 },
        new String[] { "java.lang.String", "int" }
    );

    System.out.println(result);
}
\`\`\`

Ví dụ giả định JMX connector đã được cấu hình riêng và đang lắng nghe tại URL trên. \`@EnableMBeanExport\` tự nó **không mở endpoint remote**. Remote JMX phải có bảo vệ truy cập thích hợp như xác thực, phân quyền, TLS và giới hạn network; operation thay đổi trạng thái nên được cấp quyền có chủ ý.

Đối với remote JMX, dữ liệu tham số/trả về phải thỏa yêu cầu truyền qua connector, thường liên quan serialization và class availability; hãy ưu tiên các kiểu đơn giản, chuẩn JMX khi thiết kế MBean API.

## 12. Thiết kế operation dễ gọi và dễ vận hành

Một operation JMX tốt nên có:

- **Tên rõ ràng**: \`refreshCache\`, \`pauseScheduler\`, \`resizePool\`, thay vì \`doIt\`.
- **Tham số đơn giản và ổn định**: primitive, \`String\`, hoặc kiểu JMX phù hợp. Tránh phụ thuộc class nội bộ phức tạp cho remote client.
- **Kiểm tra đầu vào**: số âm, chuỗi rỗng, trạng thái không hợp lệ phải bị từ chối có thông điệp dễ hiểu.
- **Phản hồi xác định**: có thể trả về kết quả hoặc trạng thái; một operation \`void\` thường biểu thị hoàn tất qua việc không ném lỗi.
- **Kiểm soát tác dụng phụ**: thao tác có thể xóa cache, dừng service, thay đổi tài nguyên cần giới hạn quyền, timeout và log phù hợp.
- **Metadata hữu ích**: mô tả operation/parameter bằng annotation hoặc MBean interface để operator thấy được ý nghĩa.
- **Tránh overload khó phân biệt**: nếu khách hàng quản trị chủ yếu là GUI, tên riêng như \`resizeWorkers\`, \`resizeQueues\` thường dễ thao tác hơn overload \`resize\`.

Một operation dài hạn có thể làm thread quản trị chờ. Cân nhắc operation kích hoạt công việc và trả về job ID/trạng thái, rồi cung cấp attribute/operation truy vấn tiến độ. Tuy nhiên cần bảo đảm kết quả phản ánh rõ việc “đã nhận yêu cầu” hay “đã hoàn tất”.

## 13. Bài tập thực hành

Giả sử \`MBeanInfo\` công bố các operation sau:

\`\`\`text
reload() -> void
setThrottle(int) -> void
send(java.lang.String, long, boolean) -> java.lang.String
\`\`\`

Hãy điền lời gọi JMX tương ứng.

**A.** Gọi \`reload()\`:

\`\`\`java
server.invoke(
    name,
    "reload",
    new Object[0],
    new String[0]
);
\`\`\`

**B.** Gọi \`setThrottle(25)\`:

\`\`\`java
server.invoke(
    name,
    "setThrottle",
    new Object[] { 25 },
    new String[] { "int" }
);
\`\`\`

**C.** Gọi \`send("orders", 100L, true)\`:

\`\`\`java
Object response = server.invoke(
    name,
    "send",
    new Object[] { "orders", 100L, true },
    new String[] {
        "java.lang.String",
        "long",
        "boolean"
    }
);
\`\`\`

**D.** Giải thích vì sao chữ ký sau không đúng với \`send(String, long, boolean)\`:

\`\`\`java
new String[] {
    "String",
    "java.lang.Long",
    "java.lang.Boolean"
}
\`\`\`

Vì \`String\` thiếu tên kiểu đầy đủ (\`java.lang.String\`) và \`Long\`/\`Boolean\` là wrapper khác tên kiểu primitive \`long\`/\`boolean\` được khai báo. Hãy lấy kiểu thực tế từ \`MBeanOperationInfo.getSignature()\`, không suy đoán từ class của giá trị runtime.

## 14. Checklist xử lý khi invoke không thành công

1. **Đúng MBeanServer chưa?** Local/remote có đang truy cập cùng registry nơi MBean được đăng ký?
2. **Đúng ObjectName chưa?** \`isRegistered(name)\` cho local server hoặc \`isRegistered\` trên \`MBeanServerConnection\` giúp kiểm tra.
3. **Operation có được expose không?** Đọc \`getMBeanInfo(name).getOperations()\`, tránh suy luận từ public method.
4. **Tên operation có khớp chính xác không?** JMX phân biệt tên và kiểu; không dùng tên hiển thị tùy ý.
5. **Số tham số đã khớp chưa?** \`params.length == signature.length\` và bằng số tham số khai báo.
6. **Kiểu và thứ tự chính xác chưa?** Dùng \`int\`, \`long\`, \`boolean\` cho primitive; FQCN cho object như \`java.lang.String\`.
7. **Giá trị có hợp lệ không?** Kiểu đúng vẫn có thể sai quy tắc nghiệp vụ.
8. **Lỗi ở tầng nào?** Phân biệt MBean không tồn tại, operation không khớp, method ném exception và remote connector lỗi.
9. **Quyền truy cập phù hợp chưa?** Đặc biệt với operation quản trị có tác dụng thay đổi trạng thái.
10. **Kết quả được diễn giải đúng chưa?** Operation \`void\` thường trả \`null\`; trạng thái mới có thể cần đọc lại attribute.

## 15. Tổng kết mô hình

Một lời gọi operation JMX được xác định bởi bộ tứ:

\`\`\`text
ObjectName + OperationName + Params[] + Signature[]
\`\`\`

Ví dụ điển hình:

\`\`\`java
server.invoke(
    new ObjectName("training.jmx:type=JobController,name=primary"),
    "move",
    new Object[] { "retry", 3 },
    new String[] { "java.lang.String", "int" }
);
\`\`\`

**Quy tắc quan trọng nhất:** \`params\` chứa **giá trị**, \`signature\` chứa **tên kiểu khai báo**, và hai mảng phải khớp theo **số lượng, thứ tự và hợp đồng operation được MBean công bố**. Dùng \`MBeanInfo\` làm nguồn xác thực chữ ký, rồi theo dõi exception ở đúng tầng để chẩn đoán lỗi.