# Gọi operation và xử lý lỗi từ MBeanServer qua Proxy MBean local trong Spring JMX

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích luồng gọi một **JMX operation** từ client tới \`MBeanServer\`, đặc biệt khi client và MBean ở **cùng JVM**.
- Phân biệt **gọi trực tiếp \`MBeanServer.invoke(...)\`** với **gọi qua Spring \`MBeanProxyFactoryBean\`**.
- Hiểu cách \`ObjectName\`, tên operation, mảng arguments và mảng signature xác định lời gọi.
- Nhận diện và xử lý lỗi ở các lớp: **không tìm thấy MBean**, **không tìm thấy operation**, **sai signature**, **lỗi nghiệp vụ**, **lỗi reflection**, **lỗi bảo mật** và **lỗi vòng đời**.
- Đọc nguyên nhân thực từ \`MBeanException\` hoặc \`ReflectionException\`, không nhầm wrapper JMX với lỗi gốc.
- Thiết kế interface quản trị phù hợp cho proxy, biết cách kiểm soát timeout, retry và side effect.
- Kiểm tra behavior trong integration test Spring mà không vô tình gây ảnh hưởng tới production.
- Áp dụng cách logging, phân quyền và quan sát operation giúp vận hành an toàn.

## 2. Operation là gì trong JMX?

JMX hỗ trợ hai loại khả năng quản trị quan trọng:

- **Attribute:** đọc/ghi một thuộc tính của MBean bằng \`getAttribute\` hoặc \`setAttribute\`.
- **Operation:** gọi một phương thức quản trị được công bố bằng \`invoke\`.

Ví dụ một MBean quản lý worker:

\`\`\`text
ObjectName:
  com.example.jobs:type=Worker,name=Importer

Attributes:
  Running          boolean (read-only)
  QueueDepth       long    (read-only)

Operations:
  requestPause()                    void
  retryFailedTasks(int maxTasks)    int
\`\`\`

Operation \`requestPause()\` có thể thay đổi trạng thái ứng dụng; \`retryFailedTasks(int)\` có thể gây tải hệ thống. Gọi operation không giống đọc metadata: nó yêu cầu server thực sự thực thi logic.

Với Standard MBean, operation được công bố qua management interface theo convention Java. Với Spring POJO được xuất dưới dạng Model MBean, assembler và annotation như \`@ManagedOperation\` có thể quyết định operation nào được công bố. Dù cơ chế export khác nhau, client cần nhìn vào \`MBeanInfo\` thực tế để biết interface được MBeanServer nhận diện.

## 3. Kiến trúc Proxy MBean local

Khi dùng proxy local trong Spring, caller có thể làm việc với một Java interface bình thường. Spring proxy biến method call thành thao tác quản trị lên \`MBeanServerConnection\` của một \`ObjectName\`.

\`\`\`text
Business/admin component (Spring bean)
              |
       interface WorkerAdmin
              |
              v
      MBeanProxyFactoryBean
              |
        JMX client proxy
              |
              v
   MBeanServerConnection (local)
              |
              v
      MBeanServer.invoke(...)
              |
              v
     MBean đã đăng ký
              |
              v
        Logic quản trị
\`\`\`

Một proxy local **không tự đăng ký MBean**. MBean cần tồn tại trong MBeanServer và được exporter hoặc code JMX khác đăng ký.

**Local** có nghĩa client proxy và MBeanServer được kết nối trong cùng môi trường JVM phù hợp, không cần remote JMX connector/RMI. Nếu client kết nối tới JVM khác bằng \`JMXConnector\`, proxy có thể sử dụng một \`MBeanServerConnection\` remote, nhưng lúc đó có thêm các loại lỗi mạng.

## 4. Ví dụ Standard MBean được đăng ký local

Trước khi dùng proxy, tạo một MBean có operation rõ ràng.

### 4.1. Interface quản trị

\`\`\`java
package example.jmx;

public interface WorkerAdminMBean {
    boolean isRunning();
    long getQueueDepth();
    void requestPause();
    int retryFailedTasks(int maxTasks);
}
\`\`\`

### 4.2. Implementation

\`\`\`java
package example.jmx;

public final class WorkerAdmin implements WorkerAdminMBean {

    private volatile boolean running = true;

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public long getQueueDepth() {
        return 12L;
    }

    @Override
    public void requestPause() {
        running = false;
    }

    @Override
    public int retryFailedTasks(int maxTasks) {
        if (maxTasks < 1 || maxTasks > 100) {
            throw new IllegalArgumentException(
                "maxTasks must be between 1 and 100"
            );
        }
        return maxTasks; // Kết quả minh họa.
    }

    // Không thuộc WorkerAdminMBean, không là operation
    // Standard MBean chỉ vì method được khai báo public.
    public void deleteAllInternalData() {
        // Không công bố qua management interface.
    }
}
\`\`\`

### 4.3. Đăng ký trong platform MBeanServer

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class LocalJmxRegistration {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.jobs:type=Worker,name=Importer"
        );

        server.registerMBean(new WorkerAdmin(), name);
        try {
            System.out.println(
                server.getAttribute(name, "Running")
            );

            Object result = server.invoke(
                name,
                "retryFailedTasks",
                new Object[] { 5 },
                new String[] { "int" }
            );

            System.out.println("Accepted: " + result);
        } finally {
            server.unregisterMBean(name);
        }
    }
}
\`\`\`

Ở ví dụ này, \`MBeanServer\` là đối tượng local. Lệnh \`invoke\` vẫn sử dụng cơ chế điều phối JMX tới operation mà MBean công bố.

## 5. Cú pháp MBeanServer.invoke(...)

Phương thức quan trọng:

\`\`\`java
Object invoke(
    ObjectName name,
    String operationName,
    Object[] params,
    String[] signature
)
\`\`\`

Giải thích:

| Tham số | Ý nghĩa |
| --- | --- |
| \`name\` | \`ObjectName\` xác định MBean đích trong registry. |
| \`operationName\` | Tên operation mà MBean công bố. |
| \`params\` | Các đối số thực tế theo đúng thứ tự. |
| \`signature\` | Tên kiểu Java của từng tham số, theo thứ tự tương ứng. |
| Giá trị trả về | \`Object\`, hoặc \`null\` nếu operation trả \`void\`. |

Ví dụ không có tham số:

\`\`\`java
server.invoke(
    name,
    "requestPause",
    new Object[0],
    new String[0]
);
\`\`\`

Ví dụ một tham số primitive \`int\`:

\`\`\`java
Object accepted = server.invoke(
    name,
    "retryFailedTasks",
    new Object[] { 10 },
    new String[] { "int" }
);
\`\`\`

**Điểm dễ nhầm:** \`new String[] { "int" }\` khác \`new String[] { "java.lang.Integer" }\`. JMX signature là danh sách **tên kiểu được công bố**, không phải danh sách class tương thích theo cơ chế boxing của Java ở mọi tình huống.

Với method overload, signature thường là yếu tố quyết định để phân biệt operation:

\`\`\`java
void refresh(String region);
void refresh(int partitionId);
\`\`\`

Nếu client chỉ dùng tên \`refresh\` mà không truyền đúng signature, invocation có thể thất bại hoặc chọn không đúng hợp đồng.

## 6. Lấy signature từ MBeanInfo thay vì đoán

Để biết operation nào được công bố:

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println(
        op.getName() + " -> " + op.getReturnType()
    );

    for (MBeanParameterInfo param : op.getSignature()) {
        System.out.println(
            "  " + param.getName()
                + ": " + param.getType()
        );
    }
}
\`\`\`

Ví dụ metadata:

\`\`\`text
requestPause -> void
retryFailedTasks -> int
  p1: int
\`\`\`

Tên tham số \`p1\` chỉ minh họa. Nếu Spring \`@ManagedOperationParameter\` được xử lý, metadata có thể có tên và mô tả rõ hơn. Quan trọng nhất với \`invoke\` là **tên operation và signature type**.

Đừng gọi thử các operation nguy hiểm chỉ để khám phá chúng. \`getMBeanInfo\` là cách kiểm tra hợp đồng không thực thi side effect của operation.

## 7. Spring MBeanProxyFactoryBean

Spring Framework cung cấp **\`org.springframework.jmx.access.MBeanProxyFactoryBean\`** để tạo proxy Java tới một MBean. Component sử dụng proxy gọi method giống đối tượng Java bình thường; Spring chuyển lời gọi thành JMX access tương ứng.

Một proxy cần:

1. \`ObjectName\` của MBean.
2. Management interface mà caller sẽ sử dụng.
3. \`MBeanServerConnection\` hoặc server thích hợp.
4. MBean đã được đăng ký trước khi cần truy cập.

### 7.1. Interface phía client

Có thể dùng interface riêng để mô tả hợp đồng cần gọi:

\`\`\`java
package example.springjmx;

public interface WorkerAdminClient {
    boolean isRunning();
    long getQueueDepth();
    void requestPause();
    int retryFailedTasks(int maxTasks);
}
\`\`\`

Interface proxy không nhất thiết phải mang suffix \`MBean\`; quan trọng là phương thức và kiểu tương thích với operations/attributes được MBean đích công bố.

### 7.2. Cấu hình proxy local

\`\`\`java
package example.springjmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

@Configuration
public class LocalJmxClientConfig {

    @Bean
    public MBeanProxyFactoryBean workerAdminProxyFactory()
            throws Exception {

        MBeanServer localServer =
            ManagementFactory.getPlatformMBeanServer();

        MBeanProxyFactoryBean factory =
            new MBeanProxyFactoryBean();

        factory.setServer(localServer);
        factory.setObjectName(
            "com.example.jobs:type=Worker,name=Importer"
        );
        factory.setProxyInterface(WorkerAdminClient.class);

        return factory;
    }
}
\`\`\`

\`MBeanProxyFactoryBean\` là Spring \`FactoryBean\`, nên bean được inject cho consumer thường là **proxy theo interface**, không phải factory object. Để truy cập factory bean bằng tên trong Spring có thể dùng quy ước prefix \`&\`, nhưng consumer ứng dụng thường chỉ cần interface.

Ví dụ consumer:

\`\`\`java
package example.springjmx;

import org.springframework.stereotype.Component;

@Component
public class WorkerControlPanel {

    private final WorkerAdminClient worker;

    public WorkerControlPanel(WorkerAdminClient worker) {
        this.worker = worker;
    }

    public void pauseIfRunning() {
        if (worker.isRunning()) {
            worker.requestPause();
        }
    }
}
\`\`\`

**Điều kiện quan trọng:** MBean phải được đăng ký đúng tên trong cùng server trước khi proxy cần gọi. Nếu proxy khởi tạo hoặc được gọi quá sớm, có thể gặp lỗi khi chưa có MBean hoặc metadata chưa sẵn sàng.

## 8. Đăng ký MBean bằng Spring MBeanExporter

Ví dụ cấu hình một Standard MBean ở Spring:

\`\`\`java
package example.springjmx;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class LocalJmxExporterConfig {

    @Bean
    public example.jmx.WorkerAdmin workerAdminTarget() {
        return new example.jmx.WorkerAdmin();
    }

    @Bean
    public MBeanExporter workerExporter(
            example.jmx.WorkerAdmin workerAdminTarget) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
            "com.example.jobs:type=Worker,name=Importer",
            workerAdminTarget
        ));
        return exporter;
    }
}
\`\`\`

Trong Spring Boot có thể có exporter auto-configured. Khi ứng dụng tạo exporter riêng, cần tránh hai exporter đăng ký cùng \`ObjectName\`. Cấu hình trên nhằm minh họa local JMX mà không cần bật remote JMX connector.

### 8.1. Quản lý thứ tự khởi tạo

Có thể cần đảm bảo exporter đã hoàn tất đăng ký trước khi proxy thực hiện truy cập. Nếu các bean được sử dụng trong startup hooks hoặc \`@PostConstruct\`, nên cân nhắc dependency/lifecycle tường minh.

Một phương án là đặt client logic chạy sau khi context hoàn tất khởi động hoặc dùng \`dependsOn\` phù hợp. Tuy nhiên chỉ thêm annotation phụ thuộc không tự bảo đảm mọi custom exporter/connector đã kết nối ổn định; integration test nên xác nhận thứ tự thực tế.

## 9. MBeanServer.invoke và Spring proxy khác nhau thế nào?

| Tiêu chí | Gọi trực tiếp \`MBeanServer.invoke\` | Gọi qua \`MBeanProxyFactoryBean\` |
| --- | --- | --- |
| API phía client | Tên operation dạng chuỗi, mảng args, mảng signature. | Gọi Java interface method. |
| Phát hiện sai signature | Khi client tự xây lời gọi, thường biểu hiện ở runtime. | Proxy có interface typed nhưng vẫn có thể sai so với MBean thực tế. |
| Tính dễ đọc | Rõ tầng JMX và ObjectName. | Tự nhiên với code Spring consumer. |
| Mức kết dính | Phụ thuộc trực tiếp API JMX. | Consumer phụ thuộc interface; config nối tới JMX. |
| Xử lý lỗi | Nhận checked exceptions JMX trực tiếp. | Có thể nhận exceptions được Spring chuyển đổi/wrap. |
| Kiểm tra hợp đồng | Tự đọc MBeanInfo và so sánh. | Có thể cấu hình kiểm tra interface/metadata và vẫn nên test runtime. |
| Local/remote | Dùng \`MBeanServerConnection\` thích hợp. | Factory proxy có thể dùng connection phù hợp. |

Proxy giúp **ẩn cơ chế gọi JMX** khỏi service consumer, nhưng không làm exception, side effect hoặc vấn đề quyền truy cập biến mất.

## 10. Các exception quan trọng từ MBeanServer

### 10.1. InstanceNotFoundException

Xảy ra khi MBean với \`ObjectName\` chỉ định không tồn tại trong MBeanServer đang dùng.

\`\`\`java
try {
    server.invoke(
        name,
        "requestPause",
        new Object[0],
        new String[0]
    );
} catch (javax.management.InstanceNotFoundException ex) {
    // Sai ObjectName, MBean chưa đăng ký hoặc đã unregister.
}
\`\`\`

Cách chẩn đoán:

- Kiểm tra \`server.isRegistered(name)\`.
- Kiểm tra domain và key properties của \`ObjectName\`.
- Đảm bảo exporter và client dùng cùng \`MBeanServer\`.
- Kiểm tra Spring context đã khởi động và MBean chưa bị cleanup.
- Kiểm tra registration policy \`IGNORE_EXISTING\` có khiến một object khác nằm ở tên đó không.

**Chú ý race condition:** \`isRegistered(name)\` có thể trả true nhưng MBean bị unregister trước lệnh \`invoke\`; vẫn phải xử lý \`InstanceNotFoundException\`.

### 10.2. ReflectionException

JMX có thể bọc lỗi reflection/dispatch trong \`ReflectionException\`, ví dụ operation name không hợp lệ hoặc signature không khớp.

\`\`\`java
try {
    server.invoke(
        name,
        "unknownOperation",
        new Object[0],
        new String[0]
    );
} catch (javax.management.ReflectionException ex) {
    System.err.println(
        "JMX reflection/dispatch failure: "
            + ex.getMessage()
    );
}
\`\`\`

Một lỗi thường gặp là:

\`\`\`text
NoSuchMethodException: unknownOperation
\`\`\`

Tuy nhiên không nên gán mọi \`ReflectionException\` thành “operation không tồn tại”; cần đọc **cause** và \`MBeanInfo\` để hiểu lỗi reflection thực tế.

### 10.3. MBeanException

\`MBeanException\` thường đại diện exception được ném từ code quản trị được invoke hoặc từ quá trình gọi phương thức quản trị.

Ví dụ getter/operation thực thi:

\`\`\`java
public void requestPause() {
    throw new IllegalStateException(
        "Cannot pause while committing a batch"
    );
}
\`\`\`

Khi đi qua JMX, lỗi nghiệp vụ có thể được biểu diễn dưới dạng \`MBeanException\` nếu loại exception/hợp đồng tương ứng. Truy xuất exception được bọc bằng \`getTargetException()\` hoặc nguyên nhân:

\`\`\`java
catch (javax.management.MBeanException ex) {
    Exception target = ex.getTargetException();

    System.err.println(
        "MBean operation failed: "
            + target.getClass().getSimpleName()
    );
}
\`\`\`

**Quan trọng:** Java runtime exceptions do operation phát sinh có thể đi qua \`RuntimeMBeanException\`, không nhất thiết luôn nằm trong \`MBeanException\`. Vì vậy một handler chỉ catch \`MBeanException\` là chưa đủ.

### 10.4. RuntimeMBeanException

\`RuntimeMBeanException\` đóng gói \`RuntimeException\` phát sinh trong MBean.

\`\`\`java
catch (javax.management.RuntimeMBeanException ex) {
    RuntimeException target = ex.getTargetException();
    // Phân loại lỗi nghiệp vụ, trạng thái hoặc validation.
}
\`\`\`

Ví dụ \`IllegalArgumentException\` khi \`maxTasks\` ngoài phạm vi có thể đi theo đường này. Ứng dụng nên định nghĩa hợp đồng lỗi rõ ràng; không phụ thuộc client tự giải mã một chuỗi exception message tùy ý.

### 10.5. RuntimeErrorException

Nếu MBean phát sinh một \`Error\` của JVM, JMX có thể bọc trong \`RuntimeErrorException\`. Đây là nhóm lỗi nghiêm trọng, không nên tự động retry hoặc bỏ qua như lỗi validation thông thường.

### 10.6. SecurityException và lỗi quyền

Một JMX client có thể bị từ chối thao tác do chính sách quyền trên MBeanServer, connector hoặc security layer của ứng dụng.

\`\`\`java
catch (SecurityException ex) {
    // Không được phép gọi operation trong security context này.
}
\`\`\`

Đừng xử lý lỗi quyền bằng cách tắt authentication/authorization hoặc chuyển sang tài khoản quản trị rộng hơn khi chưa được phê duyệt theo chính sách hệ thống.

### 10.7. IOException khi dùng remote

Với **local \`MBeanServer\`**, lệnh gọi thường không có lỗi network. Nhưng khi làm việc với \`MBeanServerConnection\` remote, API có thể ném \`IOException\` do endpoint/connector/network.

Lỗi mạng sau khi gửi \`invoke\` là một trường hợp đặc biệt: không thể suy ra operation **chắc chắn chưa chạy**. Nếu client tự retry lệnh không idempotent, thao tác có thể thực hiện hai lần.

## 11. Bảng phân loại lỗi và hành động

| Lỗi hoặc triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| \`InstanceNotFoundException\` | MBean không tồn tại tại ObjectName đó. | Kiểm tra registry, exporter, lifecycle và đúng server. |
| \`ReflectionException\` | Không tìm thấy method, sai signature hoặc lỗi dispatch. | Đọc \`MBeanInfo.getOperations()\`, compare signature. |
| \`MBeanException\` | Checked exception từ MBean operation hoặc wrapper liên quan. | Lấy target exception, phân loại theo hợp đồng. |
| \`RuntimeMBeanException\` | RuntimeException trong code MBean. | Xem target, validation/trạng thái, không retry mù. |
| \`RuntimeErrorException\` | Error nghiêm trọng từ MBean. | Ghi nhận incident và xử lý phù hợp, tránh che giấu. |
| \`SecurityException\` | Thiếu quyền thao tác. | Kiểm tra policy/role, không nới quyền tùy tiện. |
| \`IOException\` (remote) | Lỗi kết nối/transport. | Kiểm tra connector, phân biệt retry an toàn. |
| \`IllegalArgumentException\` | Input không hợp lệ; hoặc lỗi ở client proxy. | Kiểm tra range, types, validation và nguồn ném lỗi. |
| Operation tồn tại nhưng trả sai kiểu | Interface proxy và metadata không khớp. | So sánh \`MBeanOperationInfo.getReturnType()\`. |
| Operation bị treo | Code MBean thực thi lâu hoặc lock. | Thiết kế async request, timeout tại tầng phù hợp, giám sát thread. |

Không nên bắt \`Exception\` rồi chỉ in \`ex.getMessage()\` cho mọi tình huống, vì bạn sẽ mất loại lỗi và cause chain cần thiết.

## 12. Ví dụ gọi trực tiếp và xử lý lỗi có phân loại

Ví dụ method tiện ích chỉ dùng local \`MBeanServer\`:

\`\`\`java
import javax.management.InstanceNotFoundException;
import javax.management.MBeanException;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.ReflectionException;
import javax.management.RuntimeErrorException;
import javax.management.RuntimeMBeanException;

public final class WorkerJmxInvoker {

    private final MBeanServer server;
    private final ObjectName name;

    public WorkerJmxInvoker(
            MBeanServer server,
            ObjectName name) {
        this.server = server;
        this.name = name;
    }

    public int retryFailedTasks(int limit) throws Exception {
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException(
                "limit must be between 1 and 100"
            );
        }

        try {
            Object value = server.invoke(
                name,
                "retryFailedTasks",
                new Object[] { limit },
                new String[] { "int" }
            );

            return ((Number) value).intValue();

        } catch (InstanceNotFoundException ex) {
            throw new IllegalStateException(
                "Worker MBean is not registered: " + name,
                ex
            );

        } catch (ReflectionException ex) {
            throw new IllegalStateException(
                "JMX operation/signature mismatch",
                ex
            );

        } catch (MBeanException ex) {
            Exception cause = ex.getTargetException();
            throw new IllegalStateException(
                "Worker operation failed",
                cause != null ? cause : ex
            );

        } catch (RuntimeMBeanException ex) {
            throw new IllegalStateException(
                "Worker rejected the operation",
                ex.getTargetException()
            );

        } catch (RuntimeErrorException ex) {
            throw ex; // Không biến Error nghiêm trọng thành lỗi thường.
        }
    }
}
\`\`\`

Đây là minh họa cách phân loại, không phải thiết kế exception chung cho mọi dự án. Trong ứng dụng thực, có thể tạo exception domain \`WorkerUnavailableException\`, \`InvalidJmxContractException\`, \`WorkerActionRejectedException\` thay vì dồn hết vào \`IllegalStateException\`.

Vì method local này không dùng remote connection, nó không catch \`IOException\`; nếu chuyển sang \`MBeanServerConnection\` thì phải xét thêm checked exception kết nối.

## 13. Exception mapping khi gọi qua Spring proxy

Khi Spring \`MBeanProxyFactoryBean\` tạo proxy, phần gọi JMX và xử lý exceptions được thực hiện bởi lớp proxy/interceptor của Spring. Client thường không catch trực tiếp toàn bộ checked exceptions của \`MBeanServer.invoke\` nếu interface Java không khai báo chúng.

Tùy đường lỗi và phiên bản Spring, lỗi có thể:

- Được truyền tiếp nếu kiểu exception phù hợp với method signature.
- Bị wrap trong một runtime exception của Spring/JMX access.
- Đi theo \`UndeclaredThrowableException\` nếu Java dynamic proxy gặp checked exception không khai báo.
- Có \`cause\` là \`MBeanException\`, \`ReflectionException\` hoặc exception gốc từ MBean.

Không nên viết logic chỉ phụ thuộc một class wrapper duy nhất khi cần hỗ trợ nhiều phiên bản Spring.

### 13.1. Duyệt cause chain

\`\`\`java
public static Throwable rootCause(Throwable failure) {
    Throwable current = failure;
    while (current.getCause() != null
            && current.getCause() != current) {
        current = current.getCause();
    }
    return current;
}
\`\`\`

Dùng cho logging chẩn đoán:

\`\`\`java
try {
    workerAdminClient.retryFailedTasks(10);
} catch (RuntimeException ex) {
    Throwable root = rootCause(ex);

    log.error(
        "Local JMX operation failed, target={}, errorType={}",
        "com.example.jobs:type=Worker,name=Importer",
        root.getClass().getSimpleName(),
        ex
    );
}
\`\`\`

Đoạn này giả định consumer có \`workerAdminClient\` và logger \`log\`. Lưu ý: cause sâu nhất không phải lúc nào cũng mô tả tốt nhất **ngữ cảnh** của sự cố; cần giữ nguyên wrapper, \`ObjectName\`, operation và signature trong log có bảo vệ.

### 13.2. Không tự động retry mọi exception

Một operation có thể đã bắt đầu hoặc đã hoàn thành dù client nhận exception do timeout hoặc wrapper. Với \`requestPause()\` hoặc \`retryFailedTasks()\`, lặp lại có thể làm thay đổi trạng thái lần nữa.

Nên thiết kế các thao tác điều khiển sao cho có:

- **Idempotency key** hoặc yêu cầu an toàn khi gọi lặp.
- **Query trạng thái** để xác nhận hành động.
- **Giới hạn lần thử** và khoảng chờ phù hợp nếu được phép retry.
- **Kiểm tra quyền** trước invocation.
- **Audit** thao tác có tác động lớn.

## 14. Xác minh interface proxy có khớp MBean

Một nguyên nhân khó chẩn đoán là interface Java ở client không khớp MBeanInfo thực tế.

Giả sử client interface:

\`\`\`java
int retryFailedTasks(Integer maxTasks);
\`\`\`

nhưng MBean export:

\`\`\`java
int retryFailedTasks(int maxTasks);
\`\`\`

Dù Java hỗ trợ boxing khi gọi method thông thường, tên signature trong JMX metadata có thể lần lượt là \`java.lang.Integer\` và \`int\`. Proxy có thể gọi sai signature.

Một phép kiểm tra đơn giản:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(name);

boolean found = false;

for (var operation : info.getOperations()) {
    if ("retryFailedTasks".equals(operation.getName())
            && operation.getSignature().length == 1
            && "int".equals(
                operation.getSignature()[0].getType())
            && "int".equals(operation.getReturnType())) {
        found = true;
    }
}

if (!found) {
    throw new IllegalStateException(
        "JMX interface mismatch for retryFailedTasks(int)"
    );
}
\`\`\`

Nên đưa kiểm tra này vào integration test hoặc startup validation khi hợp đồng JMX là dependency quan trọng.

## 15. Kiểm soát các operation thay đổi trạng thái

JMX là bề mặt quản trị. Một operation có thể reset cache, reload cấu hình, tạm dừng worker hoặc kích hoạt retry. Vì thế cần:

1. **Allowlist** operation được phép công bố.
2. **Validation** tham số và trạng thái server.
3. **Authorization** và bảo vệ remote connector nếu có.
4. **Idempotency** hoặc cơ chế chống chạy trùng.
5. **Audit logging** có phạm vi, tránh log secret.
6. **Timeout/rate limit** ở nơi thực sự hỗ trợ.
7. **Status attribute** để operator xem kết quả sau khi gọi.
8. **Không dùng operation tùy ý** như \`executeShell(String)\` hoặc \`deleteAllData()\` nếu không thật sự cần và được kiểm soát chặt.

### 15.1. Pattern request/observe

Thay vì một lời gọi chạy vài phút:

\`\`\`java
void rebuildEntireSearchIndex();
\`\`\`

có thể thiết kế:

\`\`\`java
String requestIndexRebuild();
String getRebuildStatus(String requestId);
\`\`\`

Operation đầu tiên chỉ nhận yêu cầu và trả ID; client theo dõi trạng thái bằng operation đọc hoặc attribute. Một implementation thực cần queue/executor, storage trạng thái, validation và bảo vệ concurrency.

### 15.2. Thời gian chờ trong local proxy

Với local \`MBeanServer\`, operation có thể chạy **đồng bộ trên thread caller**. Không có bảo đảm \`MBeanProxyFactoryBean\` tự ngắt một method đang block lâu chỉ vì bạn đặt một trường \`currencyTimeLimit\` trong descriptor.

Nếu cần timeout thực, nên thiết kế operation bất đồng bộ hoặc quy định thời gian chờ ở tầng service/concurrency phù hợp. Nếu chạy operation trong một thread riêng rồi dùng timeout ở phía caller, việc hủy task không luôn dừng được logic server nếu nó không hỗ trợ interrupt.

## 16. MBeanInfo và discovery trước khi gọi

Một client cẩn trọng có thể xác nhận MBean đã đăng ký và operation có signature mong đợi:

\`\`\`java
if (!server.isRegistered(name)) {
    throw new IllegalStateException(
        "Expected Worker MBean is missing"
    );
}

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.printf(
        "Operation=%s return=%s%n",
        operation.getName(),
        operation.getReturnType()
    );
}
\`\`\`

Tuy nhiên check trước vẫn có **time-of-check/time-of-use race**: MBean có thể bị unregister sau khi \`isRegistered\` hoặc \`getMBeanInfo\`, rồi invocation thất bại. Vì vậy cần xử lý exception tại lời gọi thật, không chỉ làm preflight.

## 17. Vòng đời Spring và lỗi MBean chưa sẵn sàng

Các tình huống thường gặp:

- Consumer gọi proxy trong \`@PostConstruct\` trước khi exporter đăng ký.
- Hai \`ApplicationContext\` khởi động theo thứ tự khác nhau.
- Exporter đăng ký vào custom MBeanServer, còn proxy trỏ platform server.
- MBean bị unregister khi context đóng nhưng consumer vẫn giữ proxy.
- Bean bị thay thế hoặc ObjectName khác sau redeploy.
- Spring Boot auto-exporter và exporter riêng gây xung đột tên.

Để giảm rủi ro:

- Đảm bảo exporter và proxy dùng cùng MBeanServer.
- Tạo lifecycle dependency khi thật sự cần.
- Gọi operation sau khi context ready.
- Cung cấp xử lý “MBean not available” rõ ràng cho consumer.
- Tránh giữ proxy vượt vòng đời của context chứa exporter.
- Kiểm tra integration trong startup/shutdown bình thường.

Nếu exporter sử dụng policy \`IGNORE_EXISTING\`, tên MBean vẫn có thể tồn tại nhưng do thành phần khác sở hữu. Khi đó proxy sẽ gọi object thực tế ở tên đó; cần xác minh metadata trước khi tin nó đúng bean mong đợi.

## 18. Giám sát log và phân loại lỗi

Một log hữu ích khi invocation thất bại nên có:

\`\`\`text
event=JMX_OPERATION_FAILURE
objectName=com.example.jobs:type=Worker,name=Importer
operation=retryFailedTasks
signature=int
errorType=RuntimeMBeanException
rootCause=IllegalArgumentException
\`\`\`

Đây là ví dụ log do ứng dụng tự thiết kế, không phải định dạng tự động của Spring. Nên tránh log toàn bộ giá trị tham số nếu chúng có thể chứa token, PII hoặc dữ liệu nghiệp vụ nhạy cảm.

### 18.1. Gợi ý phân loại theo mức độ

| Loại lỗi | Mức xem xét | Hành động |
| --- | --- | --- |
| Input không hợp lệ | Thường là lỗi client/use case | Trả thông báo rõ, không retry. |
| MBean không tồn tại | Lỗi cấu hình hoặc lifecycle | Kiểm tra exporter, ObjectName và readiness. |
| Operation/signature không hợp đồng | Lỗi tương thích hoặc deploy | Kiểm tra metadata runtime, version. |
| Business state không cho phép | Lỗi từ chối có chủ đích | Đọc trạng thái và hướng dẫn người vận hành. |
| Remote I/O timeout | Không chắc invocation đã chạy | Kiểm tra trạng thái, chỉ retry khi an toàn. |
| RuntimeErrorException | Lỗi nghiêm trọng | Escalate, không swallow exception. |
| SecurityException | Lỗi quyền | Không tự cấp quyền rộng hơn. |

### 18.2. Không biến toàn bộ lỗi thành “MBean unavailable”

Nếu một operation đã chạy và ném \`IllegalArgumentException\`, đó là lỗi validation, khác với việc MBean không đăng ký. Trộn mọi lỗi vào cùng thông điệp “unavailable” làm giảm khả năng chẩn đoán và dễ khiến client retry sai.

## 19. Bài tập thực hành

### Bài tập 1 — Gọi trực tiếp

Đăng ký \`WorkerAdminMBean\` theo phần 4. Gọi \`retryFailedTasks(5)\` bằng \`MBeanServer.invoke\` với signature \`int\`. Kiểm tra giá trị trả về.

**Mục tiêu:** hiểu \`ObjectName\`, operation name, params và signature.

### Bài tập 2 — Sai signature

Gọi cùng operation nhưng truyền \`"java.lang.Integer"\` thay vì \`"int"\`. Quan sát exception và \`getMBeanInfo\` để hiểu kiểu được công bố.

**Mục tiêu:** tránh dựa vào autoboxing của Java khi điều phối JMX.

### Bài tập 3 — MBean không tồn tại

Unregister MBean trong một test cô lập, rồi gọi proxy hoặc \`invoke\`. Ghi nhận lỗi và kiểm tra \`isRegistered\`.

**Mục tiêu:** nhận diện lỗi lifecycle và race.

### Bài tập 4 — Operation ném exception

Gọi \`retryFailedTasks(0)\`, quan sát exception được JMX bọc và lấy \`getTargetException()\` nếu phù hợp.

**Mục tiêu:** phân biệt lỗi validation từ MBean với lỗi dispatch của JMX.

### Bài tập 5 — Spring proxy local

Cấu hình \`MBeanExporter\` và \`MBeanProxyFactoryBean\` trong cùng ApplicationContext. Inject \`WorkerAdminClient\`, gọi \`requestPause()\` và kiểm tra attribute \`Running\`.

**Mục tiêu:** hiểu proxy typed thay thế mã \`invoke\` thủ công.

### Bài tập 6 — Integration contract test

Tạo test đọc \`MBeanInfo\` để khẳng định có \`retryFailedTasks(int)\`, trả \`int\`, và không có \`deleteAllInternalData\`. Chỉ sau đó chạy một operation an toàn trong môi trường test.

**Mục tiêu:** bảo vệ interface JMX khi refactor.

## 20. Câu hỏi ôn tập

**1. \`MBeanServer.invoke\` cần những tham số nào?** \`ObjectName\`, tên operation, mảng đối số và mảng tên kiểu signature.

**2. Vì sao \`"int"\` khác \`"java.lang.Integer"\` trong signature?** Vì JMX dùng tên kiểu khai báo trong metadata để chọn operation, không mặc định dùng boxing như lời gọi Java bình thường.

**3. \`MBeanProxyFactoryBean\` có tự đăng ký MBean không?** Không. Nó tạo proxy để truy cập MBean đã tồn tại trong MBeanServer.

**4. \`InstanceNotFoundException\` thường báo gì?** ObjectName không tồn tại ở server đang dùng hoặc MBean đã bị unregister.

**5. \`ReflectionException\` thường cần kiểm tra gì?** Tên operation, signature và lỗi reflection/dispatch được bọc.

**6. Có phải mọi lỗi operation đều nằm trong \`MBeanException\`?** Không. Runtime exception có thể nằm trong \`RuntimeMBeanException\`; \`Error\` có thể nằm trong \`RuntimeErrorException\`.

**7. Proxy Spring có tự động retry an toàn không?** Không nên giả định. Client cần chính sách retry dựa trên idempotency và trạng thái thực tế.

**8. Gọi local có cần JMX/RMI port không?** Không, khi dùng trực tiếp MBeanServer local trong cùng JVM.

**9. Vì sao cần đọc \`MBeanInfo\`?** Để biết operation thực tế được công bố, kiểu trả về và signature chính xác.

**10. Tại sao không gọi operation production chỉ để kiểm tra metadata?** Vì operation có thể thay đổi trạng thái hoặc gây tải; \`getMBeanInfo\` là lựa chọn ít side effect hơn.

## 21. Tổng kết

Trong Spring JMX, **proxy MBean local** giúp code Spring gọi operation quản trị thông qua Java interface mà không phải tự viết \`MBeanServer.invoke\` ở mọi nơi. Tuy nhiên lời gọi vẫn đi qua hợp đồng JMX gồm \`ObjectName\`, tên operation và signature, nên vẫn có thể thất bại do thiếu MBean, sai hợp đồng, lỗi runtime hoặc lỗi quyền.

Thiết kế tốt phải kết hợp **kiểm tra metadata runtime**, **xử lý wrapper exception theo loại**, **validation và authorization**, **idempotency/quan sát kết quả** cho operation có side effect, đồng thời quản lý lifecycle giữa exporter và proxy. Khi cần chẩn đoán, giữ nguyên cause chain và bối cảnh operation thay vì chỉ log một thông điệp tổng quát.

## Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — \`MBeanProxyFactoryBean\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/access/MBeanProxyFactoryBean.html
- Spring Framework Javadoc — \`MBeanClientInterceptor\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/access/MBeanClientInterceptor.html
- Java SE 21 — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 — \`MBeanServerConnection\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE 21 — \`MBeanException\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanException.html
- Java SE 21 — \`RuntimeMBeanException\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/RuntimeMBeanException.html
- Java SE 21 — \`ReflectionException\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ReflectionException.html