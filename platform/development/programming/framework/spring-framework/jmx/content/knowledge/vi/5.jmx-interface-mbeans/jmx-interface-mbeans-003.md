# Operation có tham số, kiểu trả về và overload trong giao diện MBean

## Mục tiêu

Một **operation** trong Java Management Extensions (JMX) là hành động quản trị được phơi bày qua giao diện MBean. Khác với việc đọc attribute, operation có thể nhận tham số, trả kết quả và thay đổi trạng thái hệ thống. Trong Spring Framework, operation có thể xuất hiện từ một Standard MBean, MXBean, DynamicMBean hoặc từ Spring JMX exporter với metadata \`@ManagedOperation\`, \`@ManagedOperationParameter\`.

Hiểu đúng chữ ký operation quan trọng vì người gọi JMX không gọi Java method một cách trực tiếp như code nội bộ: họ dùng \`MBeanServerConnection.invoke(ObjectName, String, Object[], String[])\`, trong đó **mảng tham số và mảng tên kiểu tham số** quyết định phương thức nào được chọn. Điều này đặc biệt quan trọng khi có **overload** — nhiều operation cùng tên nhưng khác danh sách kiểu tham số.

Bạn sẽ học cách:

- Mô tả operation bằng tên, danh sách tham số có thứ tự, kiểu trả về và ý nghĩa tác động.
- Phân biệt operation không tham số, có tham số, trả \`void\`, primitive, String, Java object hoặc dữ liệu Open MBean.
- Gọi overload chính xác thông qua \`MBeanServer.invoke\` và lý giải khác biệt giữa kiểu giá trị runtime với chuỗi signature.
- Thiết kế API quản trị dễ gọi từ JConsole, JMX client, script và các agent giám sát.
- Áp dụng Spring JMX annotations, metadata và quy tắc thiết kế an toàn cho lệnh điều khiển.
- Nhận diện các lỗi thường gặp về signature, null, primitive/wrapper, exception, serialization và overload mơ hồ.

## 1. Operation là một hợp đồng quản trị

MBean interface là hợp đồng cho các tài nguyên quản trị chạy trong JVM. JMX phân biệt:

| Thành phần | Mục đích chính | Ví dụ |
|---|---|---|
| Attribute | Quan sát hoặc chỉnh một thuộc tính được công bố | \`QueueDepth\`, \`Enabled\` |
| Operation | Gọi một hành động hoặc phép tính có tham số/kết quả | \`pause()\`, \`findJobs(int limit)\`, \`setThreshold(int newLimit)\` |
| Notification | Phát tín hiệu sự kiện theo cơ chế đăng ký lắng nghe | \`worker.failed\`, \`config.changed\` |

Một operation có thể chỉ đọc dữ liệu, chạy chẩn đoán hoặc thực hiện điều khiển. Tên API không bảo đảm an toàn: \`getFullSnapshot()\` có thể cực kỳ tốn tài nguyên, còn \`refresh()\` thường có tác dụng thay đổi trạng thái. Tài liệu của mỗi operation nên nêu **tiền điều kiện, tác dụng phụ, thời gian xử lý, phạm vi ảnh hưởng, idempotency, kiểu lỗi và cách xác minh kết quả**.

Mô hình:

\`\`\`text
JMX client
  |
  | invoke(objectName, operationName, parameters[], signature[])
  v
MBeanServer
  |
  | tra cứu ObjectName + operation name + kiểu tham số
  v
MBean implementation
  |
  | thực hiện logic, trả kết quả hoặc ném lỗi
  v
JMX client
\`\`\`

\`ObjectName\` xác định MBean, còn \`operationName\` cùng \`signature\` xác định operation tương ứng. Trả về \`null\` có thể là kết quả hợp lệ của operation trả đối tượng hoặc kết quả của một operation trả \`void\`; người gọi phải đọc metadata để hiểu.

## 2. Chữ ký operation: tên, kiểu tham số và kiểu trả về

Ví dụ Java:

\`\`\`java
public String inspectQueue(String queueName, int limit)
\`\`\`

Chữ ký JMX tương ứng mô tả:

\`\`\`text
Operation name: inspectQueue
Parameter 0:   java.lang.String queueName
Parameter 1:   int limit
Return type:   java.lang.String
\`\`\`

Có ba khía cạnh độc lập:

1. **Tên operation**: \`inspectQueue\`.
2. **Danh sách tham số có thứ tự**: \`java.lang.String\` rồi \`int\`. Vị trí là một phần của hợp đồng; đảo thứ tự có thể gọi operation khác hoặc thất bại.
3. **Kiểu trả về**: \`java.lang.String\`. JMX trả kết quả qua \`Object\` của \`invoke\`, nên client có trách nhiệm kiểm tra/cast kết quả phù hợp.

**Kiểu trả về không phải tiêu chí phân biệt overload trong Java**. Java không cho phép hai method chỉ khác return type. Vì vậy không thiết kế hai operation cùng tên, cùng input nhưng trả kiểu khác.

Metadata JMX gồm \`MBeanOperationInfo\` và danh sách \`MBeanParameterInfo\`; mỗi \`MBeanParameterInfo\` mô tả tên tham số, kiểu và mô tả của một vị trí. \`MBeanOperationInfo.getReturnType()\` cung cấp tên kiểu trả về. Những giá trị này giúp công cụ hiển thị hoặc tự xây dựng đúng lời gọi.

## 3. Standard MBean: operation có tham số và giá trị trả về

Standard MBean yêu cầu interface theo quy ước \`<ImplementationClassName>MBean\`. Interface định nghĩa những thành viên được phơi bày qua JMX; không phải mọi public method trong implementation đều tự động xuất hiện.

\`\`\`java
package com.example.management;

public interface QueueManagerMBean {
    String inspect(String queueName, int limit);
    boolean pause(String queueName);
    void resume(String queueName);
    int getQueueDepth(String queueName);
}
\`\`\`

\`\`\`java
package com.example.management;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;

public class QueueManager implements QueueManagerMBean {

    private final Map<String, AtomicBoolean> paused =
            new ConcurrentHashMap<>();

    @Override
    public String inspect(String queueName, int limit) {
        if (queueName == null || queueName.isBlank()) {
            throw new IllegalArgumentException("queueName is required");
        }
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("limit must be 1..100");
        }
        // Ví dụ minh họa: dữ liệu thật đến từ một queue service.
        return "queue=" + queueName + ", sampleLimit=" + limit;
    }

    @Override
    public boolean pause(String queueName) {
        if (queueName == null || queueName.isBlank()) {
            throw new IllegalArgumentException("queueName is required");
        }
        AtomicBoolean state = paused.computeIfAbsent(
                queueName, ignored -> new AtomicBoolean(false));
        return state.compareAndSet(false, true);
    }

    @Override
    public void resume(String queueName) {
        AtomicBoolean state = paused.get(queueName);
        if (state != null) {
            state.set(false);
        }
    }

    @Override
    public int getQueueDepth(String queueName) {
        // Demo: không kết nối queue thật.
        return 0;
    }
}
\`\`\`

Đăng ký:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
        "com.example.management:type=QueueManager,name=Primary");
server.registerMBean(new QueueManager(), name);
\`\`\`

Điểm cần phân biệt: \`getQueueDepth(String)\` **vẫn là operation** theo quy tắc Standard MBean vì nó có tham số; getter attribute theo quy ước thông thường không nhận tham số. Một method trả \`boolean\` không nhất thiết là getter; \`pause(String)\` là operation vì nó biểu thị hành động.

Khi được quản lý bởi Spring, hãy bảo đảm việc đăng ký có owner và cleanup khi context bị đóng. Nếu tự gọi \`registerMBean\`, code đó cũng cần cơ chế \`unregisterMBean\`; không giả định Spring sẽ tự dọn mọi đăng ký thủ công.

## 4. Gọi operation qua MBeanServer.invoke

Đoạn mã client gọi \`inspect(String, int)\`:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.ObjectName;

Object result = server.invoke(
    name,
    "inspect",
    new Object[]{"orders", 20},
    new String[]{"java.lang.String", "int"}
);

String summary = (String) result;
\`\`\`

Cần giữ cùng số phần tử và cùng thứ tự giữa hai mảng:

\`\`\`text
params[0]     = "orders"  → signature[0] = "java.lang.String"
params[1]     = 20        → signature[1] = "int"
\`\`\`

Lỗi thường gặp:

\`\`\`java
// Sai: String literal "int" bị mô tả thành Integer class.
new String[]{"java.lang.String", "java.lang.Integer"}
\`\`\`

Nếu MBean công bố method với tham số primitive \`int\`, signature thường phải ghi tên primitive \`"int"\`, dù giá trị runtime được bọc thành \`Integer\` để nằm trong \`Object[]\`. JMX invocation không nên dựa vào việc tự động chọn overload như Java compiler làm khi gọi method trực tiếp. Client phải truyền đúng kiểu do metadata MBean mô tả.

Gọi không tham số:

\`\`\`java
Object status = server.invoke(
    name, "status",
    new Object[0],
    new String[0]
);
\`\`\`

Các implementation có thể chấp nhận \`null\` cho hai mảng để biểu diễn không tham số theo quy định JMX, nhưng dùng hai mảng rỗng nhất quán giúp trình bày ý định rõ ràng.

### 4.1 Đọc metadata để dựng lời gọi

\`\`\`java
import javax.management.*;

MBeanInfo info = server.getMBeanInfo(name);
for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println("Name: " + operation.getName());
    System.out.println("Return: " + operation.getReturnType());
    for (MBeanParameterInfo parameter : operation.getSignature()) {
        System.out.println("  " + parameter.getType()
                + " " + parameter.getName());
    }
}
\`\`\`

Khi viết client tổng quát, lấy signature từ metadata, chọn operation theo cả tên và danh sách kiểu, sau đó chuyển input của người dùng thành đúng object Java. Đừng suy luận kiểu chỉ từ chuỗi hiển thị trên UI.

## 5. Overload: một tên, nhiều chữ ký

Overload là các Java method có cùng tên nhưng khác danh sách kiểu tham số:

\`\`\`java
public interface CacheAdminMBean {
    String clear(String cacheName);
    String clear(String cacheName, boolean includeRelated);
    String clear(long cacheId);
}
\`\`\`

Các operation được phân biệt bởi:

\`\`\`text
clear(java.lang.String)
clear(java.lang.String, boolean)
clear(long)
\`\`\`

Client gọi đúng overload:

\`\`\`java
server.invoke(
    name,
    "clear",
    new Object[]{"catalog"},
    new String[]{"java.lang.String"}
);

server.invoke(
    name,
    "clear",
    new Object[]{"catalog", Boolean.TRUE},
    new String[]{"java.lang.String", "boolean"}
);

server.invoke(
    name,
    "clear",
    new Object[]{Long.valueOf(42)},
    new String[]{"long"}
);
\`\`\`

Vì các overload có thể mang ý nghĩa rất khác nhau, một UI hoặc script quản trị cần hiển thị signature rõ ràng trước khi chạy. Nếu có hai operation \`reset(String)\` và \`reset(boolean)\`, một người dùng nhập chuỗi \`"true"\` sẽ không tự động chọn được overload Boolean.

### 5.1 Overload và null

Giả sử:

\`\`\`java
String lookup(String id)
String lookup(Integer id)
\`\`\`

Giá trị \`null\` tự nó không giúp JMX suy ra method nào. Với invocation:

\`\`\`java
server.invoke(
    name,
    "lookup",
    new Object[]{null},
    new String[]{"java.lang.String"}
);
\`\`\`

signature tường minh quyết định overload nhận \`String\`. Tuy nhiên operation có thể từ chối \`null\` theo validation. Thiết kế tốt hơn là không dùng null làm “chế độ mặc định” khó đoán trong bề mặt quản trị.

### 5.2 Overload có thể là một gánh nặng vận hành

Overload giúp API Java gọn tên nhưng khiến công cụ JMX và tài liệu phức tạp hơn. Với operation thay đổi trạng thái, tên thể hiện ý định thường an toàn hơn:

\`\`\`text
removeCacheEntry(String key)
clearEntireCache()
clearCacheByPrefix(String prefix)
\`\`\`

rõ ràng hơn ba overload \`clear(...)\`. Có thể dùng overload khi các lời gọi có cùng ngữ nghĩa và khác dữ liệu đầu vào, nhưng cần cân nhắc khả năng thao tác nhầm từ console hoặc automation.

## 6. Primitive, wrapper, chuỗi, enum và object phức tạp

\`MBeanServer.invoke\` dùng \`Object[]\` vì Java không đưa primitive trực tiếp vào mảng đối tượng. Autoboxing tạo wrapper, nhưng kiểu **trong signature vẫn là tên kiểu Java của declaration**.

| Khai báo method | Tên signature | Giá trị trong Object[] |
|---|---|---|
| \`setRetries(int retries)\` | \`int\` | \`Integer.valueOf(3)\` |
| \`setEnabled(boolean enabled)\` | \`boolean\` | \`Boolean.TRUE\` |
| \`setTimeout(long millis)\` | \`long\` | \`Long.valueOf(5000L)\` |
| \`rename(String name)\` | \`java.lang.String\` | \`"worker-a"\` |
| \`setThreshold(Integer value)\` | \`java.lang.Integer\` | \`Integer.valueOf(8)\` |

Với Standard MBean, một operation có thể dùng những object Java khác, nhưng client từ xa phải có class tương ứng và đối tượng phải truyền được qua đường JMX connector. Đừng giả định bất kỳ DTO ứng dụng nào cũng có thể dùng được từ JConsole/JMX remote client.

MXBean áp dụng quy tắc ánh xạ các kiểu Java sang **Open Types**, thường biểu diễn dữ liệu quản trị bằng kiểu chuẩn, mảng, \`CompositeData\`, \`TabularData\` và các cấu trúc tương thích. Với MXBean, client cần hiểu **metadata được phơi bày** và cơ chế chuyển đổi ở tầng MXBean, không mặc định mọi value/return đều là POJO giống như khi gọi Java method trực tiếp.

Ví dụ khi kết quả cần được sử dụng từ nhiều công cụ, có thể chọn:

- Chuỗi ngắn có format được định nghĩa rõ.
- Primitive/String/array đơn giản.
- Open MBean types cho dữ liệu cấu trúc.
- MXBean interface với các kiểu dữ liệu phù hợp quy tắc mapping.

Tránh trả đối tượng chứa graph lớn, cache nội bộ, credentials, exception payload đầy đủ hoặc type phụ thuộc classloader khó chia sẻ.

## 7. Kiểu trả về: kết quả quản trị khác kết quả nghiệp vụ

Một operation có thể trả:

- \`void\`: lệnh đã được tiếp nhận/hoàn thành tùy hợp đồng; API invoke thường trả \`null\`.
- \`boolean\`: ví dụ \`true\` khi thực sự chuyển trạng thái, \`false\` khi đã ở trạng thái đó. Cần tài liệu giải nghĩa.
- \`int\`/\`long\`: số mục bị ảnh hưởng, số job được tìm thấy hoặc mã kết quả, kèm đơn vị rõ ràng.
- \`String\`: mã trạng thái hoặc summary; nên ổn định và không lộ thông tin nhạy cảm.
- Kiểu dữ liệu cấu trúc: phù hợp khi client cần phân tích máy, nhưng cần kiểm tra tính tương thích với MXBean hoặc Open MBean.

Không nên coi một kết quả \`true\` đồng nghĩa trạng thái đã ổn định nếu operation chỉ đưa yêu cầu vào queue xử lý bất đồng bộ. Ví dụ \`requestPause()\` có thể trả \`true\` nghĩa là yêu cầu đã được chấp nhận; client phải đọc attribute \`EffectiveState\` sau đó để biết worker có thật sự dừng tiếp nhận công việc hay chưa.

### 7.1 Kết quả bất đồng bộ

Nếu thao tác không kết thúc ngay:

\`\`\`text
requestReindex(String index) -> String operationId
getOperationState(String operationId) -> String
\`\`\`

Thiết kế này giúp client theo dõi tiến trình và lỗi. Trạng thái có thể gồm \`ACCEPTED\`, \`RUNNING\`, \`SUCCEEDED\`, \`FAILED\`. Cần quy định retention của operation record, chống gọi lặp và giới hạn số job có thể chạy đồng thời. JMX là kênh quản trị, không nên được sử dụng để chuyển khối lượng lớn dữ liệu nghiệp vụ.

## 8. Spring JMX annotations cho operation

Spring Framework cung cấp annotation để mô tả bean quản trị. Ví dụ:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.operations:type=CacheAdmin,name=Catalog")
public class CatalogCacheAdmin {

    @ManagedOperation(
        description = "Evict exactly one catalog cache key")
    @ManagedOperationParameters({
        @ManagedOperationParameter(
            name = "cacheKey",
            description = "Exact cache key; must not be empty")
    })
    public String evictKey(String cacheKey) {
        if (cacheKey == null || cacheKey.isBlank()) {
            throw new IllegalArgumentException("cacheKey is required");
        }
        // Demo: thay bằng service kiểm soát cache thật.
        return "eviction requested for " + cacheKey;
    }

    @ManagedOperation(
        description = "Return a bounded diagnostic summary")
    @ManagedOperationParameters({
        @ManagedOperationParameter(name = "maxEntries",
            description = "Maximum sample size: 1..50")
    })
    public String diagnose(int maxEntries) {
        if (maxEntries < 1 || maxEntries > 50) {
            throw new IllegalArgumentException("maxEntries must be 1..50");
        }
        return "sample size=" + maxEntries;
    }
}
\`\`\`

Kích hoạt annotation export theo cơ chế ứng dụng sử dụng:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
class JmxConfiguration { }
\`\`\`

Trong Spring Boot, cấu hình JMX export có thể được auto-configure, nên cần tránh khai báo nhiều exporter trùng phạm vi. \`@ManagedOperation\` đánh dấu operation; \`@ManagedOperationParameter\` cung cấp metadata dễ hiểu cho công cụ client. Các annotation **không tự cung cấp authentication, authorization hoặc audit**. Quyền truy cập JMX phải được kiểm soát ở connector/hạ tầng và cơ chế vận hành phù hợp.

### 8.1 Operation overload trong bean được Spring export

\`\`\`java
@ManagedOperation
public String inspect(String cacheName) { ... }

@ManagedOperation
public String inspect(String cacheName, int maxEntries) { ... }
\`\`\`

Đối với cùng tên operation, metadata JMX phải giữ các signature khác nhau. Một client dùng \`MBeanInfo.getOperations()\` để phân biệt thay vì chỉ chọn theo tên. Các công cụ hiển thị tên tham số từ annotation có thể thuận tiện cho người dùng, nhưng cơ chế chọn overload thực tế vẫn dựa trên danh sách kiểu/position.

Khi API quản trị có thể dùng từ script ngoài Java, tên operation riêng biệt thường dễ vận hành hơn overload sâu hoặc tham số object phức tạp.

## 9. Exception khi invoke: nhìn đúng lỗi tầng nào

Các nhóm lỗi đáng biết:

| Ngoại lệ | Tình huống |
|---|---|
| \`InstanceNotFoundException\` | Không tìm thấy MBean theo \`ObjectName\` |
| \`ReflectionException\` | Lỗi khi ánh xạ/tìm hoặc gọi method theo signature ở tầng reflection |
| \`MBeanException\` | MBean method ném checked exception và được đóng gói theo hợp đồng JMX |
| \`RuntimeMBeanException\` | Runtime exception phát sinh từ logic MBean được bọc lại |
| \`RuntimeErrorException\` | Error từ phía MBean |
| \`IOException\` (qua \`MBeanServerConnection\` từ xa) | Kết nối/remote invocation có vấn đề |

Không nên bắt mọi \`Exception\` rồi trả \`"OK"\`. Một lỗi như \`InstanceNotFoundException\` cần xử lý khác \`IllegalArgumentException\` do input sai, khác \`IOException\` do mạng. Khi dùng remote JMX, sau timeout không thể suy luận chắc chắn lệnh thay đổi trạng thái chưa chạy; cần kiểm tra trạng thái thực tế trước khi retry.

Ví dụ gọi có quản lý lỗi:

\`\`\`java
try {
    Object result = connection.invoke(
        objectName,
        "diagnose",
        new Object[]{10},
        new String[]{"int"}
    );
    System.out.println(result);
} catch (javax.management.InstanceNotFoundException e) {
    // MBean không tồn tại hoặc đã bị unregister.
} catch (javax.management.ReflectionException e) {
    // Kiểm tra operation name/signature và metadata.
} catch (javax.management.MBeanException e) {
    // Xem exception đích theo chính sách logging an toàn.
} catch (java.io.IOException e) {
    // Có thể mất kết nối; xác minh trạng thái trước retry.
}
\`\`\`

Các lớp wrapper phụ thuộc đường gọi local/remote. Không log raw parameters nếu chúng có thể chứa thông tin nhạy cảm.

## 10. Thiết kế operation có tham số an toàn

Những tiêu chí cần định nghĩa trước khi export:

### 10.1 Input validation

- Chuỗi có được rỗng/null không?
- Số có min/max và đơn vị rõ không, ví dụ \`timeoutMillis\`?
- ID có thuộc namespace đúng không?
- Giá trị enum có tương thích phiên bản client không?
- Hai tham số có quan hệ ràng buộc nào, ví dụ \`from <= to\`?
- Có tham số nào khiến truy vấn hoặc thao tác không giới hạn không?

Ví dụ tránh \`scan(int limit)\` mà \`limit = 0\` nghĩa là “không giới hạn” nếu interface không nói rõ; có thể dùng giá trị tối đa bắt buộc.

### 10.2 Quyền và phạm vi

Một operation \`pauseTenant(String tenantId)\` có tác động đến đối tượng cụ thể; JMX role được cấp quyền gọi MBean không đương nhiên đảm bảo kiểm tra tenant-level. Nếu cần phân quyền theo đối tượng, logic server cần xác định nguồn identity đáng tin cậy và kiểm tra thẩm quyền đúng tầng. Không giả định Spring Security trên HTTP tự áp dụng cho mọi JMX connection.

### 10.3 Tính lặp lại, timeout và ảnh hưởng

- Operation đã chạy rồi thì gọi lại có an toàn không?
- Một lần gọi có làm cache stampede, tăng load hoặc ghi dữ liệu không?
- Có giới hạn concurrent operations và cancellation không?
- Kết quả trả về có đủ để xác định trạng thái sau lệnh không?
- Có thể quay lại cấu hình cũ không?

Một \`clearAllCache()\` trả \`void\` và không có metric/notification theo dõi khiến vận hành khó biết lệnh đã gây tác động gì. Thay bằng operation có phạm vi nhỏ và metrics quan sát được nếu phù hợp.

## 11. Ví dụ thiết kế overload trong thực tế

Giả sử nhóm vận hành muốn tìm job bị lỗi:

\`\`\`java
String findFailures(int limit);
String findFailures(int limit, String queueName);
String findFailures(int limit, String queueName, boolean includeDetails);
\`\`\`

Về kỹ thuật, đây là ba overload hợp lệ. Tuy nhiên, để hạn chế thao tác sai và dữ liệu nhạy cảm, API quản trị có thể tách:

\`\`\`java
String summarizeRecentFailures(int limit);
String summarizeFailuresForQueue(String queueName, int limit);
\`\`\`

Không xuất \`includeDetails=true\` nếu “details” chứa payload hoặc token. Nếu cần dữ liệu chẩn đoán sâu, dùng kênh riêng có quyền và redaction phù hợp.

Client có thể tự sinh menu:

\`\`\`text
1. summarizeRecentFailures(int limit) -> String
2. summarizeFailuresForQueue(java.lang.String queueName, int limit) -> String
\`\`\`

Từng mục thể hiện rõ hành động, tham số, kiểu và đầu ra. Khi hành động có thay đổi trạng thái, có thể bổ sung bước xác nhận ở UI vận hành, nhưng không nên coi UI confirmation là cơ chế bảo mật duy nhất.

## 12. Câu hỏi thực hành

**Bài 1.** Cho interface:

\`\`\`java
public interface WorkerAdminMBean {
    String restart(String workerId);
    String restart(String workerId, boolean force);
    void reset(int partition);
    void reset(long partition);
}
\`\`\`

Hãy viết đầy đủ các mảng \`Object[]\` và \`String[]\` cho lời gọi \`restart("import", true)\` và \`reset(7L)\`. Đáp án:

\`\`\`java
new Object[]{"import", Boolean.TRUE};
new String[]{"java.lang.String", "boolean"};

new Object[]{Long.valueOf(7L)};
new String[]{"long"};
\`\`\`

**Bài 2.** Vì sao signature \`"java.lang.Integer"\` không tương đương \`"int"\`? Vì Java declaration khác nhau và lựa chọn overload qua JMX signature không nên dựa vào cơ chế boxing của Java compiler.

**Bài 3.** \`probeDependency(String)\` trả \`boolean\`, nhưng probe tạo một request HTTP đến downstream và có thể thay đổi trạng thái connection pool. Hãy phân loại: đây là operation chẩn đoán có chi phí/tác động; cần timeout, rate limit, quyền và thông tin kết quả rõ.

**Bài 4.** Thiết kế một operation quản trị trả kết quả bất đồng bộ sau khi khởi chạy một tác vụ dài. Hãy mô tả operation ID, state machine, cách client query tiến độ, xử lý timeout và chống chạy lặp.

**Bài 5.** Một client chỉ có tên operation \`clear\` nhưng MBean có ba overload. Cần đọc metadata nào? \`MBeanInfo.getOperations()\` và \`MBeanOperationInfo.getSignature()\`, không chỉ dùng \`getName()\`.

## Tổng kết

Operation JMX được gọi chính xác bằng **\`ObjectName\` + tên operation + danh sách tên kiểu tham số có thứ tự**. Kiểu trả về giúp diễn giải kết quả nhưng không phân biệt overload. Spring JMX annotations làm cho operation và metadata dễ công bố hơn; chúng không thay thế kiểm tra input, quyền truy cập, quản lý hiệu ứng hay thiết kế API. Đối với hoạt động quản trị quan trọng, hãy ưu tiên operation rõ nghĩa, tham số giới hạn, kiểu đơn giản, signature dễ gọi từ nhiều client và cơ chế xác minh trạng thái sau khi thực thi.
