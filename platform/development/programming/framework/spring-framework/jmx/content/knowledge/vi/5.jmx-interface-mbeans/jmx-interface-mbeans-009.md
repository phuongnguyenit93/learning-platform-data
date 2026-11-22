# Kiểm thử giao diện quản trị như một hợp đồng công khai

## 1. Mục tiêu và ý nghĩa

Trong Java Management Extensions (JMX), một MBean không chỉ là một đối tượng Java có thể gọi phương thức. Khi đăng ký với \`MBeanServer\`, MBean công bố một **giao diện quản trị** gồm tên định danh (\`ObjectName\`), thuộc tính (attributes), thao tác (operations), kiểu dữ liệu, quyền đọc/ghi, ngoại lệ và đôi khi cả notifications. Giao diện này có thể được sử dụng bởi JConsole, công cụ giám sát, hệ thống tự động hóa vận hành hoặc client do nhóm khác phát triển.

Vì thế, cần **kiểm thử giao diện JMX như một hợp đồng công khai**: kiểm thử điều mà client thực sự nhìn thấy và làm được qua JMX, thay vì chỉ kiểm tra các phương thức Java nội bộ.

Sau bài học, bạn có thể:

- Nêu các thành phần tạo nên hợp đồng công khai của một MBean.
- Phân biệt kiểm thử phương thức Java trực tiếp với kiểm thử qua \`MBeanServerConnection\`.
- Kiểm tra \`ObjectName\`, \`MBeanInfo\`, attributes, operations và kiểu tham số/giá trị trả về.
- Xây dựng kiểm thử tự động xác minh hành vi và lỗi khi client gửi yêu cầu không hợp lệ.
- Xác định giới hạn tương thích khi thay đổi tên, kiểu, writable/readable hoặc operation.
- Phân biệt kiểm thử hợp đồng chức năng với kiểm thử bảo mật, phân quyền, concurrency và remote connector.
- Áp dụng tư duy kiểm thử tương tự với MBean được xuất từ Spring Framework.

## 2. MBean là một API công khai ở cấp quản trị

Khi client chỉ biết \`ObjectName\`, client có thể gọi:

\`\`\`java
MBeanInfo info = connection.getMBeanInfo(name);
Object value = connection.getAttribute(name, "QueueSize");
connection.setAttribute(name, new Attribute("Enabled", false));
Object result = connection.invoke(
    name, "resetStatistics", new Object[0], new String[0]);
\`\`\`

Điều này tương tự một API ở cấp application: client phụ thuộc vào các tên và cấu trúc được công bố. Đổi method nội bộ từ \`resetCount()\` sang \`clearCount()\` có thể vô hại nếu hợp đồng MBean vẫn giữ nguyên; đổi tên operation JMX từ \`resetStatistics\` sang \`reset\` có thể làm hỏng client vận hành.

\`\`\`text
Application code
  |
  |  Standard MBean / MXBean / DynamicMBean / Spring exporter
  v
MBeanServer
  |
  |  getMBeanInfo / getAttribute / setAttribute / invoke
  v
JConsole, monitoring agents, automation, remote clients
\`\`\`

**Ranh giới kiểm thử quan trọng:** client nhìn thấy thông qua JMX mới là điều cần được xác nhận. Một unit test gọi trực tiếp Java object vẫn hữu ích, nhưng không chứng minh bean đã được đăng ký đúng tên, expose đúng metadata, hoặc có thể truy cập qua JMX.

## 3. Thành phần nào thuộc hợp đồng?

| Thành phần | Khía cạnh cần kiểm thử | Ví dụ rủi ro |
|---|---|---|
| \`ObjectName\` | Domain, key properties, tên ổn định, tên duy nhất | Dashboard không tìm thấy MBean sau đổi tên |
| Attributes | Tên, kiểu, readable/writable, giá trị, giới hạn | Client đọc được nhưng kiểu đã đổi từ \`Integer\` sang \`String\` |
| Operations | Tên, tham số, signature, kiểu trả về, tác dụng | Script gọi operation cũ bị \`ReflectionException\` |
| Metadata | \`MBeanInfo\`, description, impact, notifications | Công cụ sinh UI sai hoặc hiển thị thiếu hành động |
| Exceptions | Tình huống lỗi và cách JMX phản ánh lỗi | Client nhận ngoại lệ khó phân biệt input sai với lỗi hệ thống |
| Lifecycle | Đăng ký, hủy đăng ký, restart, reload | MBean trùng tên hoặc không được unregister |
| Behavior | Ý nghĩa nghiệp vụ của attribute/operation | \`resetStatistics\` không reset đúng dữ liệu |
| Security | Ai được quan sát hoặc điều khiển | Người không được phép gọi operation quản trị |
| Compatibility | Hợp đồng giữa các phiên bản | Client cũ ngừng hoạt động khi phát hành bản mới |

Trong kiểm thử hợp đồng, metadata không nên xem là trang trí. \`isReadable()\`, \`isWritable()\`, \`getType()\`, \`getSignature()\` và \`getReturnType()\` đều có thể ảnh hưởng hành vi client.

## 4. Thiết kế một hợp đồng JMX có thể kiểm thử

Giả sử ứng dụng có một bộ quản lý hàng đợi với hợp đồng:

\`\`\`text
ObjectName:
  training.contract:type=Queue,name=Orders

Attributes:
  PendingCount : int      read-only
  Enabled      : boolean  read/write

Operations:
  resetStatistics() : void

Behavior:
  PendingCount >= 0
  Enabled = false khiến việc nhận tác vụ mới bị từ chối
  resetStatistics() đặt bộ đếm về 0
\`\`\`

Hợp đồng được biểu diễn bằng Standard MBean:

\`\`\`java
// QueueControlMBean.java
public interface QueueControlMBean {
    int getPendingCount();
    boolean isEnabled();
    void setEnabled(boolean enabled);
    void resetStatistics();
}
\`\`\`

Triển khai minh họa:

\`\`\`java
// QueueControl.java
import java.util.concurrent.atomic.AtomicInteger;

public final class QueueControl implements QueueControlMBean {
    private final AtomicInteger pending = new AtomicInteger();
    private volatile boolean enabled = true;

    @Override
    public int getPendingCount() {
        return pending.get();
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
    public void resetStatistics() {
        pending.set(0);
    }

    public boolean submitTask() {
        if (!enabled) {
            return false;
        }
        pending.incrementAndGet();
        return true;
    }
}
\`\`\`

Trong một hệ thống thực, cần định nghĩa rõ \`PendingCount\` là số tác vụ đang chờ, đang xử lý hay đã hoàn thành; hành vi reset có thể khác. Ví dụ cố tình tối giản để tập trung vào JMX. Do check \`enabled\` và \`incrementAndGet\` không atomic với nhau, ví dụ không bảo đảm điều kiện tuyến tính tuyệt đối trong tình huống cập nhật đa luồng; nếu hợp đồng yêu cầu điều đó, cần đồng bộ trạng thái và kiểm thử concurrency bổ sung.

### 4.1. Ghi hợp đồng dưới dạng tiêu chí có thể xác minh

Một mô tả hợp đồng tốt nên nói chính xác:

1. \`ObjectName\` nào phải có sau khi khởi động.
2. Tập attribute nào phải công khai, kiểu gì, có quyền đọc/ghi ra sao.
3. Operation nào được expose, chữ ký tham số và kiểu trả về là gì.
4. Giá trị hoặc hậu điều kiện mong đợi sau từng thao tác.
5. Hành vi khi thao tác không hợp lệ.
6. Điều gì vẫn ổn định qua các bản phát hành.
7. Quyền nào phải có khi truy cập từ xa và yêu cầu audit, nếu hệ thống hỗ trợ.

Nếu hợp đồng không định nghĩa kết quả, một test chỉ kiểm tra “không ném exception” thường quá yếu để bảo vệ client.

## 5. Tạo môi trường kiểm thử qua MBeanServer

Không bắt buộc chạy cả ứng dụng production hay mở JMX remote port. Với kiểm thử hợp đồng ở cấp JMX, có thể tạo \`MBeanServer\` riêng để tránh va chạm platform MBeanServer của tiến trình test:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

MBeanServer server = MBeanServerFactory.newMBeanServer();
ObjectName name = new ObjectName(
    "training.contract:type=Queue,name=Orders");

QueueControl bean = new QueueControl();
server.registerMBean(bean, name);
\`\`\`

\`MBeanServerFactory.newMBeanServer()\` tạo một MBeanServer mới không tự đăng ký vào danh sách MBeanServer có thể tìm qua \`findMBeanServer\`. Điều này giúp kiểm thử cô lập. Một \`MBeanServer\` cũng thực hiện \`MBeanServerConnection\`, vì thế test gọi qua cùng contract client với kết nối JMX khác JVM.

Đừng dùng \`ManagementFactory.getPlatformMBeanServer()\` cho nhiều test song song có tên cố định nếu các test có thể đụng nhau. Với Spring integration test, có thể chọn server riêng và cấu hình exporter dùng server đó; điều này quan trọng để test không làm hỏng môi trường hiện tại.

## 6. Kiểm thử tự động bằng JUnit 5

Đoạn code dưới đây minh họa một test class cho JDK 21 và JUnit Jupiter 5. Giả định hai file \`QueueControl.java\` và \`QueueControlMBean.java\` đã có trong test project.

\`\`\`java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import javax.management.*;
import java.util.Arrays;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

class QueueControlContractTest {
    private MBeanServer server;
    private ObjectName name;
    private QueueControl queue;

    @BeforeEach
    void setup() throws Exception {
        server = MBeanServerFactory.newMBeanServer();
        name = new ObjectName(
            "training.contract:type=Queue,name=Orders");
        queue = new QueueControl();
        server.registerMBean(queue, name);
    }

    @Test
    void registrationAndPublicAttributesMatchContract()
            throws Exception {
        assertTrue(server.isRegistered(name));

        MBeanInfo info = server.getMBeanInfo(name);
        Map<String, MBeanAttributeInfo> attrs =
            Arrays.stream(info.getAttributes())
                  .collect(Collectors.toMap(
                      MBeanAttributeInfo::getName,
                      Function.identity()));

        assertEquals(2, attrs.size());

        MBeanAttributeInfo pending = attrs.get("PendingCount");
        assertNotNull(pending);
        assertEquals("int", pending.getType());
        assertTrue(pending.isReadable());
        assertFalse(pending.isWritable());

        MBeanAttributeInfo enabled = attrs.get("Enabled");
        assertNotNull(enabled);
        assertEquals("boolean", enabled.getType());
        assertTrue(enabled.isReadable());
        assertTrue(enabled.isWritable());

        assertEquals(0, server.getAttribute(name, "PendingCount"));
        assertEquals(true, server.getAttribute(name, "Enabled"));
    }

    @Test
    void writableAttributeChangesManagedBehavior()
            throws Exception {
        server.setAttribute(name, new Attribute("Enabled", false));
        assertEquals(false, server.getAttribute(name, "Enabled"));

        assertFalse(queue.submitTask());
        assertEquals(0, server.getAttribute(name, "PendingCount"));

        server.setAttribute(name, new Attribute("Enabled", true));
        assertTrue(queue.submitTask());
        assertEquals(1, server.getAttribute(name, "PendingCount"));
    }

    @Test
    void operationSignatureAndBehaviorMatchContract()
            throws Exception {
        MBeanInfo info = server.getMBeanInfo(name);
        MBeanOperationInfo reset =
            Arrays.stream(info.getOperations())
                  .filter(op -> op.getName().equals("resetStatistics"))
                  .findFirst()
                  .orElseThrow();

        assertEquals(0, reset.getSignature().length);
        assertEquals("void", reset.getReturnType());

        queue.submitTask();
        queue.submitTask();
        assertEquals(2, server.getAttribute(name, "PendingCount"));

        server.invoke(
            name, "resetStatistics",
            new Object[0], new String[0]);

        assertEquals(0, server.getAttribute(name, "PendingCount"));
    }

    @Test
    void invalidRequestsFailThroughJmxBoundary() {
        assertThrows(
            AttributeNotFoundException.class,
            () -> server.getAttribute(name, "UnknownAttribute"));

        assertThrows(
            AttributeNotFoundException.class,
            () -> server.setAttribute(
                name, new Attribute("PendingCount", 9)));

        assertThrows(
            InvalidAttributeValueException.class,
            () -> server.setAttribute(
                name, new Attribute("Enabled", "false")));

        assertThrows(
            ReflectionException.class,
            () -> server.invoke(
                name, "unknownOperation",
                new Object[0], new String[0]));
    }
}
\`\`\`

Ví dụ tập trung vào **public JMX boundary**: test hỏi metadata và gọi \`server.getAttribute\`, \`server.setAttribute\`, \`server.invoke\`. Gọi \`queue.submitTask()\` trực tiếp chỉ dùng để kích thích thay đổi trạng thái của resource, còn quan sát trạng thái và điều khiển quản trị vẫn thực hiện qua JMX.

### 6.1. Vì sao so metadata và kết quả thực tế?

Test đọc \`MBeanInfo\` giúp phát hiện những thay đổi không chủ ý trong interface; test invocation chứng minh interface không chỉ được khai báo mà còn hoạt động. Cần cả hai:

\`\`\`text
Metadata test:
  Khách hàng có nhìn thấy đúng hợp đồng không?

Behavior test:
  Các lời gọi hợp lệ có thực hiện đúng hợp đồng không?
\`\`\`

Một MBean có thể công bố method đúng nhưng implementation sai; ngược lại, implementation đúng nhưng exporter/assembler không expose method ấy thì client cũng không sử dụng được.

### 6.2. Vấn đề khi so sánh mọi metadata tuyệt đối

Không phải mọi trường mô tả đều cần cố định mãi. Nếu \`description\` chỉ phục vụ UI, bản sửa câu chữ có thể hợp lệ. Vì vậy test hợp đồng nên chốt những phần client thực sự phụ thuộc: tên, kiểu, quyền, signatures, ý nghĩa hành vi và tên ObjectName. Nếu client sử dụng description để sinh tài liệu, lúc đó description cũng có thể trở thành hợp đồng.

## 7. Kiểm thử trường hợp lỗi và hành vi biên

### 7.1. Attribute không tồn tại

Client yêu cầu một tên không đăng ký trong MBean:

\`\`\`java
connection.getAttribute(name, "NotExists");
\`\`\`

Kỳ vọng: lỗi JMX phù hợp, chẳng hạn \`AttributeNotFoundException\`. Test không nên chỉ yêu cầu exception chung \`Exception\`, vì như vậy một lỗi kết nối cũng có thể làm test “đạt”.

### 7.2. Ghi attribute chỉ đọc

Nếu \`PendingCount\` được công bố read-only, client không được sửa trực tiếp:

\`\`\`java
connection.setAttribute(
    name, new Attribute("PendingCount", 123));
\`\`\`

Kỳ vọng: thất bại theo contract JMX; với Standard MBean, thường là \`AttributeNotFoundException\` cho thuộc tính không thể ghi. Với DynamicMBean tùy implementation, lỗi cụ thể phải được kiểm tra theo hợp đồng được định nghĩa.

### 7.3. Kiểu dữ liệu sai

\`\`\`java
connection.setAttribute(
    name, new Attribute("Enabled", "false"));
\`\`\`

\`Enabled\` là boolean. Chuỗi \`"false"\` không phải \`Boolean.FALSE\`. Client không nên dựa vào ép kiểu ngầm trừ khi hợp đồng MBean hoặc lớp adapter ghi rõ quy tắc chuyển đổi.

### 7.4. Operation không tồn tại hoặc signature không khớp

\`\`\`java
connection.invoke(
    name, "resetStatistics",
    new Object[]{"extra"},
    new String[]{String.class.getName()});
\`\`\`

Mặc dù tên operation đúng, signature khác hợp đồng không tham số. Kỳ vọng invocation bị từ chối. Điều này đặc biệt quan trọng khi MBean có overload.

### 7.5. Thao tác có tác dụng phụ

Không bao giờ kiểm thử operation phá hủy dữ liệu trên hệ thống đang phục vụ người dùng bằng cách gọi thật ngoài phạm vi kiểm soát. Dùng bean giả lập hoặc data fixture riêng. Nếu operation quản trị liên quan cache clear, restart, drain queue, thay đổi mức log, shutdown, hãy thiết kế test với hậu điều kiện rõ ràng và phạm vi cô lập.

## 8. Kiểm thử hợp đồng của MXBean và DynamicMBean

### 8.1. MXBean: kiểm thử kiểu Open Data

MXBean hỗ trợ mapping kiểu Java sang các kiểu JMX Open Data để client có thể tương tác qua một tập kiểu dữ liệu chuẩn. Một method Java trả DTO có thể được công bố dưới dạng \`CompositeData\` thay vì trả trực tiếp DTO cho client JMX.

Khi kiểm thử MXBean:

- Xem metadata được expose, không chỉ return type trong interface Java.
- Xác minh các trường và kiểu của \`CompositeData\` hoặc \`TabularData\` nếu client phụ thuộc vào chúng.
- Kiểm tra giá trị null, tập dữ liệu rỗng và tương thích khi thêm/bớt trường.
- Kiểm tra operation có thể gọi qua \`MBeanServerConnection\`, không chỉ gọi Java proxy nội bộ.

Ví dụ đọc kiểu composite:

\`\`\`java
Object raw = connection.getAttribute(name, "WorkerStatus");
if (raw instanceof javax.management.openmbean.CompositeData data) {
    Object state = data.get("state");
    System.out.println(state);
}
\`\`\`

Tên \`WorkerStatus\` và key \`state\` là ví dụ minh họa; định dạng thực tế phụ thuộc MXBean đã định nghĩa.

### 8.2. DynamicMBean: metadata và dispatch phải tương thích

\`DynamicMBean\` tự trả \`MBeanInfo\` và tự xử lý các thao tác:

\`\`\`java
Object getAttribute(String attribute);
void setAttribute(Attribute attribute);
AttributeList getAttributes(String[] attributes);
AttributeList setAttributes(AttributeList attributes);
Object invoke(String actionName, Object[] params, String[] signature);
MBeanInfo getMBeanInfo();
\`\`\`

Kiểm thử cần đối chiếu:

1. Mọi attribute được công bố có thể xử lý đúng theo cờ readable/writable.
2. Mọi operation trong metadata có thể gọi bằng đúng \`signature\`.
3. Mọi tên hoặc signature không có trong metadata bị từ chối rõ ràng.
4. Kiểu dữ liệu trả về và giá trị nhập đúng theo metadata.
5. Các phương thức batch cho kết quả phù hợp, kể cả khi chỉ một số entry thành công.
6. Nếu metadata có thể thay đổi lúc chạy, client cũ hoặc cache metadata được xử lý theo quy ước tương thích đã công bố.

Một \`DynamicMBean\` có metadata đúng nhưng handler dùng sai tên vẫn vi phạm hợp đồng. Hãy dùng chính \`MBeanServerConnection\` làm đường kiểm thử chung để tránh bỏ sót logic của MBeanServer.

## 9. Spring Framework JMX: kiểm thử từ ApplicationContext đến MBeanServer

Trong Spring Framework, \`MBeanExporter\`, \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\` và assembler phù hợp có thể công bố Spring bean dưới dạng MBean. Khi đó hợp đồng của client gồm **cấu hình export** cộng với behavior của bean.

Ví dụ bean quản trị:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "training.spring:type=Worker,name=Primary",
    description = "Worker management interface")
public class WorkerManagement {
    private volatile boolean enabled = true;

    @ManagedAttribute
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @ManagedOperation
    public void disable() {
        this.enabled = false;
    }
}
\`\`\`

Ứng dụng cần bật/cấu hình hỗ trợ export annotation thích hợp, chẳng hạn \`@EnableMBeanExport\`, hoặc định nghĩa \`MBeanExporter\` và assembler metadata. Chỉ thêm \`@ManagedResource\` vào class mà không có exporter phù hợp không bảo đảm MBean được đăng ký.

### 9.1. Các cấp kiểm thử với Spring

**Cấp 1 — Unit test bean:** xác minh business logic của \`WorkerManagement\` khi gọi Java trực tiếp.

**Cấp 2 — Spring integration test:** tạo \`ApplicationContext\` chứa bean và JMX exporter; xác minh MBean đã đăng ký dưới ObjectName mong đợi.

**Cấp 3 — JMX contract test:** gọi \`MBeanServerConnection\` để kiểm metadata, thuộc tính và operation như một client độc lập.

**Cấp 4 — Remote integration test:** chạy connector có xác thực, mã hóa và quy tắc mạng trong môi trường thử nghiệm có kiểm soát; xác minh client truy cập theo chính sách quyền.

Nếu hệ thống dùng Spring Boot, cần kiểm tra các thiết lập JMX của phiên bản Boot cụ thể. Mặc định và tích hợp Actuator là mối quan tâm bổ sung; không suy ra hành vi của Boot từ ví dụ Spring Framework thuần.

### 9.2. Kiểm thử trùng ObjectName và vòng đời

Một lỗi tích hợp thường gặp là hai bean cùng được export thành một \`ObjectName\`. Test nên chứng minh quy ước naming tạo tên duy nhất. Nếu ứng dụng mở/đóng context nhiều lần, cũng cần kiểm tra unregister để không còn MBean cũ hoặc gây \`InstanceAlreadyExistsException\` khi khởi tạo lại.

Trong cùng JVM, dùng platform MBeanServer có thể làm các Spring integration test ảnh hưởng lẫn nhau. Ưu tiên server riêng, unique ObjectName hoặc chiến lược cleanup nhất quán.

## 10. Kiểm thử tương thích khi giao diện thay đổi

Một thay đổi code có thể là breaking change của JMX client dù ứng dụng vẫn biên dịch và chạy.

| Thay đổi | Rủi ro tương thích | Chiến lược |
|---|---|---|
| Đổi \`ObjectName\` | Client không tìm thấy resource | Duy trì alias/mapping chuyển tiếp nếu cần |
| Đổi tên attribute | Dashboard/script đọc tên cũ lỗi | Thêm tên mới song song trong giai đoạn chuyển đổi khi khả thi |
| Đổi kiểu \`int\` thành \`String\` | Parse và so sánh dữ liệu sai | Đặt attribute mới hoặc version schema |
| Đổi read-only thành writable | Mở thêm khả năng thay đổi trạng thái | Rà soát quyền và kiểm thử ghi |
| Đổi writable thành read-only | Automation thao tác cũ thất bại | Thông báo migration và test tác động |
| Xóa operation | Client gọi bị lỗi | Quy hoạch deprecation/chuyển tiếp |
| Thêm operation | Có thể là bổ sung tương thích | Kiểm soát quyền và tác dụng phụ |
| Đổi overload/signature | Invoke client cũ không khớp | Giữ signature cũ hoặc nâng version |
| Đổi ý nghĩa số đo | Dashboard có thể báo sai dù kiểu không đổi | Tài liệu hóa semantic contract và test hậu điều kiện |
| Đổi \`CompositeData\` schema | Client phụ thuộc key/type có thể lỗi | Thử trên consumer thực tế |

Một cách kiểm thử regression: lưu bản mô tả hợp đồng đã phê duyệt (ví dụ danh sách ObjectName, attribute, operation và kỳ vọng hành vi) trong test fixture; mỗi bản phát hành kiểm tra những thành phần bắt buộc vẫn còn. Nếu có thay đổi có chủ đích, chỉnh contract fixture cùng tài liệu migration và cập nhật client liên quan.

Không nhất thiết snapshot toàn bộ chuỗi \`MBeanInfo.toString()\` vì thứ tự hiển thị hoặc nội dung mô tả không quan trọng có thể khác theo JDK hoặc implementation. Nên so sánh theo thành phần có ngữ nghĩa.

## 11. Kiểm thử bảo mật và remote access

Kiểm thử hợp đồng chức năng trên local server không chứng minh endpoint remote đã an toàn. Đối với JMX remote, cần có test riêng trong môi trường kiểm soát:

- Client hợp lệ có thể xác thực và chỉ truy cập những MBean/operations được phép.
- Client không được phép bị từ chối.
- Kết nối bảo vệ dữ liệu khi truyền theo chính sách TLS của hệ thống.
- Cổng/hostname JMX RMI được cấu hình và giới hạn mạng đúng.
- Thông tin nhạy cảm không được expose qua attribute/notification.
- Operation thay đổi trạng thái được giới hạn quyền và có audit nếu chính sách yêu cầu.
- Các lỗi truy cập không làm rò secret trong thông báo lỗi hoặc logs.

**Không dùng việc truy cập được từ mạng công cộng làm tiêu chí thành công.** Một mô hình vận hành an toàn thường giới hạn JMX vào mạng quản trị, VPN hoặc tunnel phù hợp; mọi thử nghiệm remote phải nằm trong phạm vi được cấp quyền.

Các kiểm tra này khác với \`MBeanInfo\`: metadata có thể công bố một operation, nhưng authorization là trách nhiệm của cấu hình connector/access controller hoặc chính sách ứng dụng. \`MBeanOperationInfo.ACTION\` không tự cấp hoặc chặn quyền.

## 12. Kiểm thử notification và giám sát trạng thái

Nếu MBean phát notification, hợp đồng còn gồm loại notification, thời điểm phát và payload. Test cần:

1. Đăng ký listener qua JMX.
2. Kích hoạt một sự kiện xác định trong fixture.
3. Chờ notification bằng đồng bộ hóa có timeout hữu hạn.
4. Kiểm tra type, source, sequence number (nếu có yêu cầu), timestamp và userData.
5. Hủy listener sau test.
6. Kiểm tra không phát notification sai khi không có sự kiện.

Không phụ thuộc vào \`Thread.sleep\` cố định rồi hy vọng notification đã đến. Có thể dùng \`CountDownLatch\` trong test với timeout rõ ràng. Nếu thực thi asynchronous, thiết kế test tách thời điểm gọi operation với thời điểm hoàn tất xử lý.

JMX notification không thay thế một hàng đợi thông điệp bền vững. Hợp đồng nên mô tả rõ đảm bảo delivery, ordering và replay (nếu có) thay vì ngầm giả định notification không thể mất.

## 13. Một ma trận kiểm thử thực tế

| Lớp kiểm thử | Kiểm tra | Loại lỗi tìm ra |
|---|---|---|
| API metadata | ObjectName, attributes, operations, types | Breaking change hợp đồng |
| API behavior | Read/write/invoke và hậu điều kiện | Implementation sai |
| Negative cases | Tên, kiểu và chữ ký không hợp lệ | Validation/exception sai |
| Registration lifecycle | Đăng ký, trùng tên, unregister | MBean thiếu, rò tài nguyên |
| Spring integration | Bean/exporter/assembler/naming strategy | Chỉ hoạt động khi gọi trực tiếp, không xuất qua JMX |
| Concurrency | Đọc/ghi trong nhiều thread | Race condition, trạng thái không nhất quán |
| Notification | Event type, payload, timing | Subscriber nhận sai dữ liệu |
| Security integration | Xác thực, authorization, TLS, mạng | Quyền quản trị bị lộ |
| Compatibility | So sánh hợp đồng cũ/mới | Script, dashboard và agent cũ hỏng |

Không cần mọi bài học hoặc mọi MBean đều có đầy đủ tất cả bài test trên. Mức độ cần thiết phụ thuộc độ nguy hiểm của thao tác quản trị, số lượng consumer và khả năng phát hành độc lập giữa producer/client.

## 14. Bài tập thực hành

### Bài tập A — Viết contract fixture

Tạo file dữ liệu kiểm thử chứa:

\`\`\`yaml
objectName: training.contract:type=Queue,name=Orders
attributes:
  - name: PendingCount
    type: int
    readable: true
    writable: false
  - name: Enabled
    type: boolean
    readable: true
    writable: true
operations:
  - name: resetStatistics
    signature: []
    returnType: void
\`\`\`

Từ fixture, viết assertions trên \`getMBeanInfo\`. Không cần viết trình parser YAML phức tạp nếu mục tiêu chỉ là luyện hợp đồng; có thể bắt đầu bằng cấu trúc Java tương đương.

### Bài tập B — Cố tình tạo breaking change

Đổi \`getPendingCount()\` thành \`getQueueLength()\` trong interface. Chạy test hợp đồng và ghi nhận metadata nào thay đổi. Sau đó khôi phục interface cũ, giữ implementation nội bộ tùy ý. Quan sát sự khác biệt giữa tên method Java và tên attribute công khai.

### Bài tập C — Thay đổi quyền ghi

Xóa setter \`setEnabled\`. Dùng test metadata xác minh \`Enabled\` chuyển thành read-only, và test ghi qua JMX báo lỗi. Thảo luận khi nào sự thay đổi này là breaking change đối với automation hiện có.

### Bài tập D — Spring integration

Tạo Spring context có \`WorkerManagement\` và exporter tương ứng. Dùng \`MBeanServerConnection\` kiểm tra đúng \`ObjectName\` và operation \`disable\`. Sau đó cố tình bỏ export configuration để thấy test thất bại ngay cả khi unit test bean vẫn chạy.

### Bài tập E — Client giả lập consumer cũ

Tạo một client chỉ biết ObjectName và names/signatures đã công bố, hoàn toàn không tham chiếu \`QueueControl\` trong source. Dùng nó làm consumer contract test trên cả implementation cũ và mới. Đây là cách xác minh tốt rằng hợp đồng được bảo vệ độc lập khỏi chi tiết code.

## 15. Câu hỏi tự kiểm tra

1. Vì sao gọi trực tiếp một Java method chưa phải là kiểm thử hợp đồng JMX?
2. Những thành phần nào của \`MBeanInfo\` có thể làm client hỏng nếu thay đổi?
3. Tại sao test \`isRegistered\` chưa đủ để kết luận MBean hoạt động đúng?
4. Khi nào thay đổi tên attribute là breaking change?
5. Vì sao phải kiểm tra \`signature\` của operation?
6. Làm thế nào để test thuộc tính read-only và dữ liệu sai kiểu?
7. Lợi ích của \`MBeanServerFactory.newMBeanServer()\` trong test là gì?
8. Spring JMX cần kiểm thử thêm điểm nào ngoài unit test của bean?
9. Tại sao kiểm thử metadata không thay thế kiểm thử bảo mật remote JMX?
10. Khi hệ thống phát notification, những yếu tố nào thuộc contract của subscriber?

## 16. Tài liệu tham khảo

- Java SE 21 — \`MBeanServerConnection\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE 21 — \`MBeanInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
- Java SE 21 — \`MBeanAttributeInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanAttributeInfo.html
- Java SE 21 — \`MBeanOperationInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanOperationInfo.html
- Java SE 21 — \`MBeanServerFactory\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerFactory.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/

**Ghi nhớ:** kiểm thử MBean như một hợp đồng công khai nghĩa là quan sát và gọi nó theo góc nhìn của JMX client. Hãy xác minh cả metadata lẫn hành vi, kiểm thử lỗi và lifecycle, bảo vệ tính tương thích, và tách rõ kiểm thử chức năng với quyền truy cập từ xa.
