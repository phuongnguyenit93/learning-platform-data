# Ném exception từ @ManagedOperation và cách người gọi nhìn thấy trong Spring Framework JMX

## 1. Mục tiêu và tình huống

Một operation quản trị JMX có thể thay đổi cấu hình, xóa cache, khởi động lại worker hoặc thực hiện tác vụ khắc phục sự cố. Những hành động này có thể thất bại vì dữ liệu đầu vào không hợp lệ, trạng thái ứng dụng không cho phép, quyền truy cập bị hạn chế hoặc lỗi hạ tầng. Khi một method được Spring Framework công khai qua \`@ManagedOperation\`, câu hỏi không chỉ là “method ném exception nào?” mà còn là **JMX client nhận được exception đó qua tầng nào, dưới dạng gì và nên xử lý thế nào**.

Ví dụ:

\`\`\`java
@ManagedOperation(description = "Clear a named cache")
public void clearCache(String cacheName) {
    if (!knownCaches.contains(cacheName)) {
        throw new IllegalArgumentException(
            "Unknown cache: " + cacheName);
    }
    cacheService.clear(cacheName);
}
\`\`\`

Một Java caller gọi trực tiếp \`clearCache("missing")\` có thể nhận \`IllegalArgumentException\`. Nhưng một JMX caller gọi \`MBeanServerConnection.invoke\` thường gặp wrapper JMX như \`MBeanException\` hoặc \`RuntimeMBeanException\`, tùy loại lỗi và cơ chế dispatch; còn client từ xa có thể gặp lỗi \`IOException\` trước khi invocation tới method.

Sau bài học, bạn có thể:

1. Phân biệt lỗi nghiệp vụ, lỗi metadata/dispatch, lỗi quyền truy cập và lỗi kết nối.
2. Hiểu API \`MBeanServerConnection.invoke\` và các JMX exception liên quan.
3. Biết cách Spring \`@ManagedOperation\` được công khai thành MBean operation.
4. Kiểm tra root cause khi nhận \`MBeanException\`, \`RuntimeMBeanException\`, \`ReflectionException\`.
5. Dùng JConsole và Java JMX client để quan sát lỗi.
6. Thiết kế operation có thông điệp lỗi an toàn, có thể vận hành và có hợp đồng rõ.
7. Viết integration test xác nhận exception được phản ánh đúng qua ranh giới JMX.

## 2. Đường đi của một lời gọi operation

\`\`\`text
JMX client
    |
    | connection.invoke(objectName, action, params, signature)
    v
MBeanServerConnection
    |
    | MBeanServer dispatch theo ObjectName và MBeanInfo
    v
MBean được export bởi Spring
    |
    | Spring assembler / adapter / invocation
    v
Java method có @ManagedOperation
    |
    +--> thành công: return value
    |
    +--> lỗi: exception từ method / adapter / JMX layer
                 |
                 v
           wrapper hoặc transport failure
                 |
                 v
           JMX client nhận và xử lý
\`\`\`

Không phải mọi lỗi đều xuất phát từ Java method. Cần xác định **lỗi phát sinh trước invocation, bên trong method, hay khi đưa kết quả về client**. Ba loại lỗi này có cách xử lý khác nhau.

| Tầng | Lỗi ví dụ | Ý nghĩa |
|---|---|---|
| Tìm MBean | \`InstanceNotFoundException\` | ObjectName không đăng ký trong server đang gọi |
| Tìm operation/chữ ký | \`ReflectionException\` | Tên/signature không hợp lệ hoặc lỗi phản chiếu |
| Logic bên trong method | \`MBeanException\`, \`RuntimeMBeanException\` | Operation đã đi vào logic/adapter và ném lỗi |
| Truy cập MBean/server | \`SecurityException\` hoặc lỗi authorization | Client không có quyền thực hiện |
| Giao tiếp remote | \`IOException\` | Connection/RMI/protocol bị lỗi |
| Lỗi nghiêm trọng của runtime | \`RuntimeErrorException\` | Lỗi Java \`Error\` được bao bởi JMX |

Các exception thực tế phụ thuộc loại MBean (Standard, MXBean, Dynamic hoặc Spring-exported), cách exporter/adapter gọi method và implementation JMX của JVM. Không dựa trên tên một wrapper duy nhất để kết luận root cause nếu chưa inspect exception chain.

## 3. @ManagedOperation và cơ chế export của Spring

Một method Java chỉ trở thành JMX operation khi Spring JMX exporter và metadata assembler phù hợp công bố nó.

Ví dụ:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "training.spring:type=CacheManager,name=Primary",
    description = "Administrative cache operations")
public class CacheManagerControl {

    @ManagedOperation(description = "Clear one cache by name")
    public void clearCache(String cacheName) {
        if (cacheName == null || cacheName.isBlank()) {
            throw new IllegalArgumentException(
                "cacheName must not be blank");
        }
        if (!cacheName.equals("products")) {
            throw new IllegalArgumentException(
                "Cache does not exist");
        }
        // Perform controlled, idempotent cache invalidation.
    }
}
\`\`\`

Spring configuration cần bật annotation export, ví dụ:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@ComponentScan(basePackageClasses = CacheManagerControl.class)
@EnableMBeanExport
public class JmxConfig {
}
\`\`\`

\`@ManagedOperation\` xác định method có thể gọi qua JMX, còn \`@ManagedResource\` cung cấp thông tin MBean. \`@EnableMBeanExport\` kích hoạt hạ tầng export annotation. Trong Spring application có custom \`MBeanExporter\`, cần cấu hình \`MBeanInfoAssembler\`/attribute source phù hợp, server đúng và registration không trùng.

Điều cần kiểm thử: tên operation, tên class của tham số, kiểu trả về và việc invocation thực sự tới đúng method.

## 4. API invoke của JMX client

Một client dùng:

\`\`\`java
Object result = connection.invoke(
    objectName,
    "clearCache",
    new Object[]{"products"},
    new String[]{String.class.getName()}
);
\`\`\`

Tham số gồm:

- \`objectName\`: ObjectName cụ thể của MBean.
- \`"clearCache"\`: tên operation được expose.
- \`new Object[]{"products"}\`: giá trị tham số truyền vào.
- \`new String[]{"java.lang.String"}\`: signature biểu diễn tên kiểu tham số.
- Giá trị trả về: đối tượng Java hoặc JMX Open Data theo contract của MBean.

**Quan trọng:** \`signature\` mô tả các *kiểu Java*, không phải giá trị tham số. Nếu operation nhận \`int\`, signature thường là \`"int"\`, không phải \`"java.lang.Integer"\`; nếu nhận \`String\`, signature là \`"java.lang.String"\`.

Ví dụ operation không tham số:

\`\`\`java
connection.invoke(
    objectName,
    "resetCounters",
    new Object[0],
    new String[0]);
\`\`\`

Khi client gửi sai operation name hoặc signature, lời gọi thường thất bại **trước khi method được thực hiện**. Không phân loại lỗi này là “nghiệp vụ ném exception”.

## 5. MBeanException: method ném checked exception

\`javax.management.MBeanException\` là wrapper tiêu biểu khi method do MBean thực thi ném một checked exception. Cụ thể với Spring-exported MBean, adapter có thể chuyển invocation failure sang wrapper JMX theo loại cause và cơ chế expose.

Ví dụ method:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;
import java.io.IOException;

@ManagedOperation(description = "Reload configuration file")
public void reloadConfiguration() throws IOException {
    throw new IOException("Configuration source is unavailable");
}
\`\`\`

Client:

\`\`\`java
try {
    connection.invoke(
        name, "reloadConfiguration",
        new Object[0], new String[0]);
} catch (javax.management.MBeanException ex) {
    Exception cause = ex.getTargetException();
    System.err.println(
        "Business operation failed: " + cause.getClass().getName());
}
\`\`\`

\`MBeanException.getTargetException()\` trả về checked exception được bao. \`getCause()\` cũng giúp theo dõi exception chain. Với Spring, nên kiểm thử đường thực thi cụ thể trong project thay vì giả định mọi checked exception luôn đi qua đúng một wrapper.

### 5.1. Không nhầm wrapper với nguyên nhân

Nếu chỉ log \`MBeanException: Exception thrown in operation\`, thông tin quan trọng có thể bị mất. Một client tốt phân biệt wrapper JMX với \`cause\`:

\`\`\`java
Throwable root = exception;
while (root.getCause() != null) {
    root = root.getCause();
}
\`\`\`

Tuy nhiên, không nên hiển thị toàn bộ exception chain lên UI công khai nếu có nguy cơ rò rỉ path nội bộ, credentials hoặc dữ liệu riêng. Chi tiết kỹ thuật nên ở server logs được kiểm soát; thông điệp client nên được thiết kế cho người vận hành.

## 6. RuntimeMBeanException: method ném RuntimeException

Một operation có thể ném \`IllegalArgumentException\`, \`IllegalStateException\` hoặc một runtime exception khác.

\`\`\`java
@ManagedOperation
public void pauseProcessing() {
    if (currentlyRebalancing) {
        throw new IllegalStateException(
            "Cannot pause while rebalancing");
    }
    paused = true;
}
\`\`\`

Trong JMX, nhiều implementation bao \`RuntimeException\` của MBean thành \`javax.management.RuntimeMBeanException\`.

Client:

\`\`\`java
try {
    connection.invoke(
        name, "pauseProcessing",
        new Object[0], new String[0]);
} catch (RuntimeMBeanException ex) {
    RuntimeException cause = ex.getTargetException();
    System.err.println(
        "Operation rejected: " + cause.getMessage());
}
\`\`\`

\`RuntimeMBeanException\` là **unchecked exception**. Vì vậy đoạn Java chỉ \`catch (MBeanException)\` không bắt được nhánh này. Nếu muốn phân loại lỗi nghiệp vụ đầy đủ, cần tính tới cả checked và unchecked JMX wrappers.

Cần nhớ: một \`RuntimeException\` cũng có thể đến từ adapter, metadata conversion hoặc logic JMX chứ không nhất thiết từ business method. Điều tra cause và stack trace tại server khi cần.

## 7. ReflectionException: method chưa hề được gọi

Ví dụ MBean công bố:

\`\`\`java
@ManagedOperation
public void clearCache(String cacheName) { ... }
\`\`\`

Nhưng client gọi:

\`\`\`java
connection.invoke(
    name, "clearCache",
    new Object[]{"products"},
    new String[]{"int"});
\`\`\`

Với chữ ký khác hợp đồng, MBeanServer hoặc adapter thường không tìm được operation khớp và có thể ném \`ReflectionException\`. Tương tự, tên operation viết sai:

\`\`\`java
connection.invoke(
    name, "clearCaches",
    new Object[]{"products"},
    new String[]{String.class.getName()});
\`\`\`

Điểm chẩn đoán: kiểm tra \`MBeanInfo.getOperations()\` trước khi kết luận method có lỗi.

\`\`\`java
MBeanInfo info = connection.getMBeanInfo(name);
for (MBeanOperationInfo op : info.getOperations()) {
    System.out.print(op.getName() + "(");
    for (MBeanParameterInfo p : op.getSignature()) {
        System.out.print(p.getType() + " ");
    }
    System.out.println(")");
}
\`\`\`

Nếu operation không nằm trong metadata, có thể do annotation chưa được assembler nhận, exporter cấu hình sai, class proxy không phù hợp hoặc đang kết nối tới MBeanServer khác.

## 8. InstanceNotFoundException và ObjectName sai

\`\`\`java
ObjectName name = new ObjectName(
    "training.spring:type=CacheManager,name=Missing");
connection.invoke(
    name, "clearCache",
    new Object[]{"products"},
    new String[]{String.class.getName()});
\`\`\`

Nếu MBean không được đăng ký, client nhận \`InstanceNotFoundException\`. Không được gọi nó là exception bên trong operation. Trình tự điều tra:

1. Client đang kết nối tới JVM/MBeanServer nào?
2. ObjectName có chính xác domain, key và value không?
3. Bean có được Spring export không?
4. Context đã khởi động/đóng hoặc MBean đã unregister chưa?
5. Có nhiều ApplicationContext hoặc MBeanServer khiến tìm sai registry không?

Dùng \`connection.queryNames\` hoặc \`connection.isRegistered\` với quyền phù hợp để xác nhận tên MBean có tồn tại.

## 9. IOException: lỗi kết nối không phải business exception

\`MBeanServerConnection\` là giao diện chung cho local và remote access. Với remote JMX/RMI, \`invoke\` có thể thất bại vì:

- Mạng mất kết nối.
- Endpoint RMI không reachable.
- JVM/server đã khởi động lại.
- TLS handshake hoặc truststore cấu hình sai.
- Timeout hoặc transport failure.
- Kết nối đóng khi method đang chạy.

\`\`\`java
try {
    connection.invoke(
        name, "clearCache",
        new Object[]{"products"},
        new String[]{String.class.getName()});
} catch (java.io.IOException ex) {
    System.err.println("JMX transport failure: " + ex);
}
\`\`\`

**Vấn đề quan trọng:** khi remote call bị \`IOException\`, client có thể không biết operation đã thực hiện thành công trên server rồi nhưng response bị mất, hay invocation chưa tới server. Đây là tình huống kết quả không chắc chắn. Không retry mù một operation có side effect như xóa dữ liệu, restart hoặc rotate secrets. Cần kiểm tra trạng thái/idempotency, thiết kế operation an toàn khi lặp hoặc sử dụng request ID nếu cơ chế quản trị hỗ trợ.

## 10. SecurityException: quyền truy cập và chính sách quản trị

Một remote client có thể được xác thực nhưng không có quyền gọi operation thay đổi trạng thái. Tùy cơ chế JMX agent, access file, custom authenticator/authorizer và môi trường JVM, lỗi quyền có thể được thể hiện qua \`SecurityException\` hoặc failure cụ thể.

Không coi \`@ManagedOperation\` là cơ chế cấp quyền. Annotation chỉ công khai operation trong metadata MBean; kiểm soát quyền cần được thiết kế ở tầng management agent, connector, MBeanServer authorization hoặc logic ứng dụng theo chính sách bảo mật.

Một client không nên tự động thử operation khác khi bị từ chối quyền. Ghi nhận tình trạng và yêu cầu quyền hợp lệ.

## 11. RuntimeErrorException và lỗi nghiêm trọng

Nếu logic MBean ném \`Error\` — chẳng hạn lỗi nghiêm trọng của JVM — JMX có thể bao nó trong \`RuntimeErrorException\`. Đây không phải dạng lỗi nghiệp vụ thông thường. Client cần tránh bắt toàn bộ \`Throwable\` rồi tiếp tục vận hành như không có gì; cần có chiến lược cảnh báo và phục hồi riêng phù hợp mức độ sự cố.

Một operation quản trị cần tránh chủ động ném \`Error\` để báo input sai. Dùng checked exception hoặc runtime exception phù hợp với hợp đồng.

## 12. JConsole hiển thị exception thế nào?

Trong JConsole, tab **MBeans** cho phép xem attributes và gọi operations được expose. Khi operation thất bại:

1. JConsole gửi request tới MBeanServer.
2. Server trả lỗi theo cơ chế JMX.
3. GUI hiển thị lỗi trong dialog/thông báo hoặc vùng kết quả tùy bản JDK.
4. Thông điệp có thể chứa tên wrapper, class exception hoặc message từ cause.

Không dựa vào format dialog để thiết kế contract vì GUI có thể khác theo JDK, phiên bản và công cụ. Với tự động hóa, \`MBeanServerConnection.invoke\` là API phù hợp để assert loại lỗi và cause.

Ví dụ lỗi có thể xuất hiện dưới dạng:

\`\`\`text
javax.management.RuntimeMBeanException
  caused by java.lang.IllegalArgumentException:
  Cache does not exist
\`\`\`

Đây là minh họa; không bảo đảm JConsole hiển thị đúng từng dòng như vậy.

## 13. Integration test: kiểm tra đường đi qua MBeanServer

Unit test gọi Java method trực tiếp không đủ:

\`\`\`java
assertThrows(IllegalArgumentException.class,
    () -> bean.clearCache("unknown"));
\`\`\`

Test này xác nhận logic class, nhưng **không chứng minh JMX caller nhận lỗi thế nào**. Hãy khởi động Spring context và gọi qua \`MBeanServer\`.

Ví dụ JUnit 5:

\`\`\`java
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation
    .AnnotationConfigApplicationContext;

import javax.management.*;
import java.lang.management.ManagementFactory;

import static org.junit.jupiter.api.Assertions.*;

class CacheManagerJmxTest {

    @Test
    void invalidCacheIsVisibleThroughJmxWrapper()
            throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(
                    JmxConfig.class)) {

            MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

            ObjectName name = new ObjectName(
                "training.spring:type=CacheManager,name=Primary");

            assertTrue(server.isRegistered(name));

            RuntimeMBeanException failure = assertThrows(
                RuntimeMBeanException.class,
                () -> server.invoke(
                    name, "clearCache",
                    new Object[]{"unknown"},
                    new String[]{String.class.getName()}));

            assertInstanceOf(
                IllegalArgumentException.class,
                failure.getTargetException());
        }
    }

    @Test
    void unknownOperationFailsBeforeBusinessMethod()
            throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(
                    JmxConfig.class)) {

            MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

            ObjectName name = new ObjectName(
                "training.spring:type=CacheManager,name=Primary");

            assertThrows(
                ReflectionException.class,
                () -> server.invoke(
                    name, "clearCaches",
                    new Object[]{"products"},
                    new String[]{String.class.getName()}));
        }
    }
}
\`\`\`

Ví dụ giả định exporter dùng platform MBeanServer và không có conflict ObjectName giữa các test. Trong project nhiều ApplicationContext, hãy inject server riêng cho test để tránh xung đột. Ngoài ra, wrapper cụ thể phải được xác minh với Spring exporter, assembler và JDK thực tế; nếu adapter chuyển exception theo cách khác, test nên phản ánh hợp đồng đã được chấp nhận thay vì ép implementation vào một giả định không đúng.

## 14. Exception chain và logging đúng cách

Một JMX operation có thể gây nhiều lớp wrapper, đặc biệt khi proxy, Spring AOP, reflection và remote transport cùng tham gia.

Ví dụ helper dành cho **logging nội bộ**:

\`\`\`java
static void logExceptionChain(Throwable failure) {
    Throwable current = failure;
    int depth = 0;
    while (current != null && depth < 12) {
        System.err.printf(
            "[%d] %s: %s%n",
            depth,
            current.getClass().getName(),
            current.getMessage());
        if (current.getCause() == current) {
            break;
        }
        current = current.getCause();
        depth++;
    }
}
\`\`\`

Cần giới hạn độ sâu, tránh vòng cause bất thường và không xuất dữ liệu nhạy cảm. Với môi trường vận hành, dùng logger có cấu trúc và correlation/request ID nếu có.

Một client console có thể xử lý theo nhóm:

\`\`\`java
try {
    connection.invoke(
        name,
        "clearCache",
        new Object[]{"products"},
        new String[]{String.class.getName()});

} catch (InstanceNotFoundException ex) {
    // Wrong ObjectName or MBean no longer registered.

} catch (ReflectionException ex) {
    // Wrong operation/signature or JMX reflection failure.

} catch (MBeanException ex) {
    // Target method threw checked exception or adapter wrapped it.
    Throwable cause = ex.getTargetException();

} catch (RuntimeMBeanException ex) {
    // RuntimeException from MBean execution.
    Throwable cause = ex.getTargetException();

} catch (SecurityException ex) {
    // Denied according to configured authorization.

} catch (java.io.IOException ex) {
    // Transport failure: execution outcome may be unknown.
}
\`\`\`

Đây là mẫu phân nhánh cơ bản; API và runtime có thể sinh các exception khác. Nếu xử lý \`RuntimeErrorException\`, thường cần báo lỗi nghiêm trọng thay vì cố retry. Đừng nuốt exception mà không log hoặc trả về kết quả có nghĩa.

## 15. Thiết kế operation có hợp đồng lỗi tốt

### 15.1. Validate input sớm

Một operation nên từ chối tham số sai rõ ràng:

\`\`\`java
if (cacheName == null || cacheName.isBlank()) {
    throw new IllegalArgumentException(
        "cacheName must not be blank");
}
\`\`\`

Điều này giúp client phân biệt input không hợp lệ với hạ tầng gặp sự cố.

### 15.2. Thông điệp ngắn và an toàn

Thông điệp lỗi nên có ý nghĩa cho người vận hành nhưng không tiết lộ token, password, đường dẫn nhạy cảm hay dữ liệu cá nhân. Không trả raw SQL hay toàn bộ config bí mật qua JMX exception message.

### 15.3. Hạn chế operation tác động lớn

Operation xóa dữ liệu, làm gián đoạn dịch vụ hoặc thay đổi bảo mật cần authorization, audit và điều kiện bảo vệ riêng. Không lấy \`MBeanOperationInfo.ACTION\` làm cơ chế cấp quyền; đây chỉ là metadata phân loại tác động.

### 15.4. Idempotency và retry

Nếu có khả năng remote client mất kết nối giữa request và response, một operation có side effect nên có semantics rõ: idempotent, có request ID, có query trạng thái hoặc quy trình reconcile. Không retry tự động chỉ dựa vào \`IOException\`.

### 15.5. Không chạy operation quá lâu

Một lời gọi JMX đồng bộ có thể giữ thread client/server trong thời gian dài. Với tác vụ quản trị lâu, cân nhắc operation \`startJob\` trả ID, rồi attribute hoặc operation truy vấn trạng thái. Chỉ áp dụng khi thiết kế hệ thống cần và được bảo vệ quyền phù hợp.

## 16. Trường hợp lỗi đặc biệt với Spring AOP và proxy

Một Spring bean có thể được bọc bởi proxy để xử lý transaction, security hoặc logging. Khi export qua JMX, đường invocation có thể đi qua proxy/adapter tùy cấu hình. Điều này dẫn tới các lưu ý:

- Method quản trị cần thật sự được exporter công bố; kiểm tra \`MBeanInfo\`.
- Exception có thể đi qua Spring AOP interceptor trước khi tới JMX boundary.
- Transaction rollback không phải chức năng của JMX; nó phụ thuộc Spring transaction semantics.
- Một checked exception có thể bị wrap khác đi bởi proxy/lớp reflection trước khi đến JMX.
- Việc gọi qua JMX không bảo đảm giống hoàn toàn với self-invocation trong cùng object.

Nếu gặp wrapper bất ngờ, xác minh class/proxy được export và exception chain thực tế. Đừng ép JMX client bắt một exception của Spring cụ thể nếu nó đã được chuyển thành JMX wrapper.

## 17. So sánh Standard MBean, MXBean và DynamicMBean

| Kiểu MBean | Cách dispatch | Lưu ý exception |
|---|---|---|
| Standard MBean | JMX ánh xạ operation vào method qua interface | Checked/runtime exception có thể được bao bởi JMX wrappers |
| MXBean | Như MBean interface cùng chuyển đổi Open Types | Có thể phát sinh lỗi chuyển đổi type ngoài lỗi nghiệp vụ |
| DynamicMBean | Implementation tự xử lý \`invoke\` | Phải tuân hợp đồng JMX, tự kiểm tra name/signature và wrap exception phù hợp |
| Spring-exported bean | Spring metadata + exporter/adapter | Wrapper phụ thuộc Spring assembler/adapter và loại exception |

Với DynamicMBean, signature của \`invoke\` cho phép ném \`MBeanException\` và \`ReflectionException\`. Một implementation thường bao checked exception của logic trong \`MBeanException\` và dùng \`ReflectionException\` cho operation/chữ ký không tồn tại. Đừng để client gặp lỗi vô nghĩa do dispatch sai.

## 18. Cách chẩn đoán lỗi theo từng câu hỏi

| Câu hỏi | Bằng chứng cần lấy |
|---|---|
| MBean đã tồn tại? | \`connection.isRegistered(name)\` |
| Operation đã được expose? | \`getMBeanInfo(name).getOperations()\` |
| Signature chính xác? | \`MBeanOperationInfo.getSignature()\` |
| Method đã bắt đầu chạy? | Structured logs/trace có correlation ID |
| Lỗi do method ném? | JMX wrapper và target exception |
| Có proxy/interceptor? | Spring bean type/proxy, logs |
| Lỗi khi kết nối? | IOException, JMXConnector logs, network/TLS |
| Trạng thái đã thay đổi? | Read-only state attribute hoặc query trạng thái |
| Client có quyền? | Auth/access configuration và audit |
| Có dữ liệu nhạy cảm trong exception? | Kiểm tra sanitized message/log policy |

Không nên quy tất cả lỗi \`invoke\` là \`MBeanException\`; phân loại đúng giúp tránh thao tác khắc phục sai.

## 19. Bài tập thực hành

### Bài tập A — Checked exception

Tạo method:

\`\`\`java
@ManagedOperation
public void reload() throws java.io.IOException {
    throw new java.io.IOException("Dependency unavailable");
}
\`\`\`

Gọi qua JMX, ghi lại exception class ở client và target exception. So sánh với gọi trực tiếp method Java.

### Bài tập B — Runtime exception

Tạo operation ném \`IllegalStateException\` khi service đang ở trạng thái \`MAINTENANCE\`. Viết test xác nhận wrapper và cause; định nghĩa thông điệp lỗi không tiết lộ thông tin nội bộ.

### Bài tập C — Sai signature

Tạo \`clearCache(String)\`, gọi với chữ ký \`int\` và ghi nhận lỗi dispatch. Chứng minh method chưa chạy bằng counter/tracing trong fixture.

### Bài tập D — Lỗi remote sau khi operation có tác dụng phụ

Mô phỏng một client bị mất kết nối sau khi gửi request. Giải thích vì sao client không biết chắc operation đã chạy chưa. Đề xuất một attribute \`LastOperationId\` hoặc \`JobStatus\` để đối chiếu mà không retry mù.

### Bài tập E — Spring proxy

Bọc một bean quản trị bằng một Spring advice có logging. Gọi operation qua JMX và quan sát exception chain. Giải thích vai trò của proxy và adapter. Thực hiện trong test context riêng, không áp dụng operation phá hủy trên production.

## 20. Câu hỏi tự kiểm tra

1. Tại sao client JMX có thể không nhận trực tiếp \`IllegalArgumentException\` như caller Java?
2. Khác nhau giữa \`MBeanException\` và \`RuntimeMBeanException\` là gì?
3. Khi nào \`ReflectionException\` có thể xảy ra trước khi method chạy?
4. \`InstanceNotFoundException\` nói gì về ObjectName và server?
5. Vì sao \`IOException\` không chứng minh operation chưa được thực hiện?
6. \`@ManagedOperation\` có tự cấp quyền gọi operation không?
7. Vì sao test gọi method trực tiếp chưa đủ kiểm tra exception qua JMX?
8. Trường nào của \`MBeanInfo\` giúp kiểm tra operation signature?
9. Nếu client tự động retry sau network failure, rủi ro nào có thể xảy ra?
10. Với Spring proxy, vì sao cần xem toàn bộ exception chain?

## 21. Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — \`@ManagedOperation\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedOperation.html
- Java SE 21 — \`MBeanServerConnection\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE 21 — \`MBeanException\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanException.html
- Java SE 21 — \`RuntimeMBeanException\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/RuntimeMBeanException.html
- Java SE 21 — \`ReflectionException\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ReflectionException.html

**Ghi nhớ:** exception từ một \`@ManagedOperation\` đi qua nhiều tầng trước khi client nhìn thấy. Hãy phân biệt wrapper JMX với root cause, lỗi dispatch với lỗi nghiệp vụ và lỗi transport với kết quả thực thi. Thiết kế operation có hợp đồng lỗi rõ ràng, thông điệp an toàn và không retry mù khi trạng thái không chắc chắn.
