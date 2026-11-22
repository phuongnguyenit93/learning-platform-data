# Độ trễ, timeout và lỗi mạng khi gọi operation qua Remote JMX Connector

## 1. Mục tiêu và bối cảnh

Khi ứng dụng Spring Framework xuất MBean bằng JMX, một client cục bộ có thể gọi operation qua \`MBeanServer.invoke(...)\`. Với **remote connector**, client thường dùng \`JMXConnector\` và \`MBeanServerConnection\` để gửi lời gọi qua mạng. Lúc đó, việc operation thành công hay thất bại không chỉ phụ thuộc business logic mà còn phụ thuộc độ trễ, DNS, TLS, xác thực, RMI, firewall, timeout và lifecycle của JVM.

Ví dụ:

\`\`\`java
Object result = connection.invoke(
    new ObjectName("com.example:type=Queue,name=Orders"),
    "drain",
    new Object[0],
    new String[0]
);
\`\`\`

Nếu lời gọi mất kết nối giữa chừng, client có thể nhận \`IOException\` trong khi **operation đã chạy trên server**. Đây là vấn đề quan trọng nhất: lỗi transport không đủ để khẳng định lời gọi chưa có tác dụng.

Sau bài này, bạn có thể:

1. Phân biệt thời gian chờ kết nối, thời gian thực thi operation và thời gian nhận phản hồi.
2. Phân tích đường đi của lời gọi \`invoke\` qua JMX/RMI.
3. Nhận diện các lỗi mạng, TLS, authorization, lookup và exception do MBean.
4. Hiểu giới hạn của các thiết lập timeout trong client JMX/RMI.
5. Tránh retry mù những operation không idempotent.
6. Thiết kế operation bất đồng bộ có \`operationId\`, trạng thái và khả năng đối chiếu kết quả.
7. Xây dựng kiểm thử lỗi mạng và giám sát độ trễ theo từng tầng.

## 2. Một lời gọi remote operation đi qua những đâu?

\`\`\`text
JMX Client
   |
   | JMXConnectorFactory.connect(serviceUrl, env)
   v
JMX/RMI connector client
   |
   +-- DNS / network route / TCP
   +-- TLS & authentication (nếu cấu hình)
   +-- RMI registry lookup / connector stub
   |
   v
Remote JMX Connector Server
   |
   v
MBeanServerConnection.invoke(...)
   |
   v
MBeanServer
   |
   +-- tìm ObjectName
   +-- xác định operation/signature
   +-- kiểm tra quyền theo cấu hình
   |
   v
Spring-exported MBean / managed bean
   |
   +-- business operation
   |
   v
Return value hoặc exception
   |
   v
RMI serialization / network response
   |
   v
Client
\`\`\`

Thời gian client quan sát được gồm nhiều phần:

\`\`\`text
T_client = T_dispatch_client
         + T_network_request
         + T_server_queue
         + T_operation
         + T_serialization
         + T_network_response
         + T_client_decode
\`\`\`

Đây là mô hình tư duy, không phải công thức đo đạc chính xác: các thành phần có thể chồng lấn hoặc bị ảnh hưởng bởi reconnect, GC và thread scheduling.

**Quan trọng:** thời gian \`JMXConnectorFactory.connect\` không giống thời gian \`connection.invoke\`. Kết nối thành công chưa chứng minh các operation đều nhanh hoặc có thể hoàn tất.

## 3. Phân biệt latency, timeout và lỗi mạng

| Khái niệm | Dấu hiệu | Ý nghĩa |
|---|---|---|
| Connection latency | Chậm khi connect | DNS, TCP, TLS, RMI registry, authentication |
| Invocation latency | Chậm khi gọi operation | Mạng, server dispatch, lock, business logic, GC |
| Connection timeout | Không thiết lập được kết nối trong giới hạn | Client không kết nối được; operation chưa được gọi qua connection này |
| Read/response timeout | Đợi phản hồi quá lâu | Không biết chắc server đã thực thi đến đâu |
| Network disconnect | Kết nối đang hoạt động bị đứt | Kết quả invocation có thể không xác định |
| Server-side timeout | Logic hoặc lớp ứng dụng tự giới hạn thời gian | Tùy implementation; không mặc định có deadline cho mọi MBean operation |
| Business exception | MBean chủ động báo lỗi | Có thể được JMX bao bằng \`MBeanException\`, \`RuntimeMBeanException\` |

Một operation có thể chạy thành công sau khi client đã hết kiên nhẫn hoặc mất kết nối. Do đó thời gian chờ trên client **không phải cơ chế hủy operation có bảo đảm**.

## 4. Remote JMX bằng JMXConnector

Ví dụ client Java:

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public final class RemoteInvokeDemo {
    public static void main(String[] args) throws Exception {
        JMXServiceURL url = new JMXServiceURL(
            "service:jmx:rmi:///jndi/rmi://jmx.internal.example:9010/jmxrmi");

        try (JMXConnector connector =
                 JMXConnectorFactory.connect(url)) {

            MBeanServerConnection connection =
                connector.getMBeanServerConnection();

            ObjectName name = new ObjectName(
                "com.example:type=Queue,name=Orders");

            Object result = connection.invoke(
                name, "getDrainStatus",
                new Object[0], new String[0]);

            System.out.println(result);
        }
    }
}
\`\`\`

Ví dụ chỉ minh họa **đường client**, không tự thiết lập xác thực/TLS. Trong môi trường thực tế, không kết nối tới endpoint quản trị không bảo vệ. Cần truyền môi trường kết nối và trust/auth configuration phù hợp với connector đang sử dụng.

JMX/RMI có thể liên quan hai bước: lookup connector qua RMI registry và kết nối remote object theo thông tin trong stub. Firewall cho phép registry port nhưng chặn RMI server port vẫn có thể khiến lời gọi thất bại.

## 5. Khi nào độ trễ tăng?

### 5.1. Trễ mạng

- Khoảng cách địa lý hoặc đường truyền nhiều hop.
- Packet loss gây retransmission.
- VPN/tunnel hoặc gateway nhiều lớp.
- DNS lookup hoặc failover chậm.
- NAT/firewall quản lý connection state.

### 5.2. Trễ JVM và MBeanServer

- Garbage collection hoặc safepoints.
- CPU bị contention.
- Thread pool/connector chờ phục vụ request.
- MBean implementation giữ lock hoặc chờ I/O.
- Operation cần truy vấn database hoặc gọi service khác.
- Serialization giá trị trả về quá lớn.

### 5.3. Trễ do công cụ quản trị

- Client gọi \`getMBeanInfo\` rồi mới \`invoke\`.
- Client poll nhiều attributes liên tiếp.
- JConsole hoặc monitoring agent tạo nhiều kết nối.
- JMX proxy phát sinh thêm metadata lookup tùy cấu hình.

Không kết luận “mạng chậm” chỉ vì total \`invoke\` time cao. Cần tách connection, network và thời gian chạy logic tại server.

## 6. Timeout trong JMX/RMI: không có một nút bấm cho mọi trường hợp

JMX API \`MBeanServerConnection.invoke\` không nhận trực tiếp đối số \`Duration timeout\`:

\`\`\`java
Object invoke(
    ObjectName name,
    String operationName,
    Object[] params,
    String[] signature)
    throws ...
\`\`\`

Vì vậy khi cần deadline, phải xem:

1. JMX connector đang dùng protocol nào.
2. RMI implementation/JDK cung cấp cấu hình timeout nào.
3. Network/proxy/load balancer có timeout riêng không.
4. Client có cấu hình timeout ở tầng wrapper hay executor không.
5. Server operation có hỗ trợ deadline/cancellation/idempotency không.

Một số tùy chọn RMI/JDK như \`sun.rmi.transport.tcp.responseTimeout\` hoặc \`sun.rmi.transport.connectionTimeout\` tồn tại trong những implementation, nhưng đây là **tùy chọn implementation-specific**, không phải bảo đảm chuẩn của JMX API. Tên, phạm vi, tính hỗ trợ và ý nghĩa có thể thay đổi theo JDK. Cần kiểm tra tài liệu của JDK đang chạy và test end-to-end; không dựa vào một property ngầm định cho hệ thống quan trọng.

### 6.1. Không nhầm connect timeout với invoke timeout

Client có thể connect nhanh:

\`\`\`text
connect: 120 ms
invoke : 45 seconds
\`\`\`

Nếu business operation đợi database 45 giây, tăng connect timeout không giải quyết được. Cần phân tích chính operation, giới hạn tài nguyên và phương án bất đồng bộ.

### 6.2. Java Future timeout có giới hạn

Ví dụ muốn caller không đợi quá lâu:

\`\`\`java
ExecutorService executor = Executors.newSingleThreadExecutor();

try {
    Future<Object> task = executor.submit(
        () -> connection.invoke(
            name, "longRunningOperation",
            new Object[0], new String[0]));

    Object result = task.get(5, TimeUnit.SECONDS);

} catch (TimeoutException timeout) {
    // Client stopped waiting for result.
} finally {
    executor.shutdownNow();
}
\`\`\`

Đây chỉ là **client-side waiting deadline**. \`Future.cancel(true)\` hoặc \`shutdownNow()\` không bảo đảm JMX/RMI call bị hủy ngay, càng không bảo đảm server operation dừng. Thread có thể tiếp tục bị block đến khi transport hoặc server hoàn tất. Với số lượng lời gọi lớn, cần quản lý executor capacity và tránh tạo thread vô hạn.

## 7. IOException và trạng thái thực thi không chắc chắn

Kịch bản:

\`\`\`text
T0: Client gửi drain() qua JMX
T1: Server nhận request
T2: Server bắt đầu drain queue
T3: Server drain hoàn tất
T4: Kết nối mạng đứt trước response
T5: Client nhận IOException
\`\`\`

Client thấy lỗi, nhưng server đã hoàn tất operation.

Kịch bản khác:

\`\`\`text
T0: Client chuẩn bị gửi drain()
T1: Kết nối đứt
T2: Server không nhận request
T3: Client nhận IOException
\`\`\`

Hai trường hợp có thể đều hiện ra như lỗi transport. Do đó:

**Không retry một operation có tác dụng phụ chỉ dựa vào \`IOException\` hoặc timeout.**

Đặc biệt nguy hiểm với:

- Xóa cache hoặc invalidation theo batch.
- Restart/shutdown worker.
- Rotate credential.
- Replay/consume message.
- Điều chỉnh quota hoặc trạng thái workflow.
- Thay đổi cấu hình với tác dụng không idempotent.

Ngay cả thao tác tưởng như idempotent cũng cần định nghĩa rõ semantics và tác động tới hệ thống khác.

## 8. Idempotency và operationId

Một cách thiết kế API quản trị bền vững là cung cấp mã định danh request:

\`\`\`text
startDrain(operationId: String) -> accepted: boolean
getDrainStatus(operationId: String) -> status
\`\`\`

Nếu client gửi lại cùng \`operationId\`, server không khởi chạy tác vụ lần thứ hai. Điều này đòi hỏi server lưu trạng thái đủ lâu và xử lý đồng thời an toàn.

Mô hình:

\`\`\`text
Client creates opId = "drain-2026-11-11-001"
         |
         v
invoke startDrain(opId)
         |
         +-- response received -> poll status
         |
         +-- timeout / IOException
                 |
                 v
             query getDrainStatus(opId)
                 |
          +------+------+
          |             |
       Found          Not found
          |             |
      Observe       Retry policy
      result        only if safe
\`\`\`

**Không suy luận “not found” chắc chắn request chưa chạy**, nhất là khi trạng thái được lưu không bền hoặc có replication delay. Cần định nghĩa retention, consistency và xử lý duplicate.

### 8.1. Trạng thái tác vụ

Một mô hình có thể gồm:

\`\`\`text
UNKNOWN
ACCEPTED
RUNNING
SUCCEEDED
FAILED
CANCEL_REQUESTED
CANCELLED
\`\`\`

\`UNKNOWN\` là trạng thái của **client quan sát**, không nhất thiết là trạng thái nội bộ của server. \`CANCEL_REQUESTED\` không đồng nghĩa hủy đã thành công.

## 9. Thiết kế operation bất đồng bộ thay cho lời gọi dài

Một operation JMX đồng bộ chờ đến khi method return. Nếu thao tác mất nhiều phút, giữ kết nối lâu vừa dễ timeout vừa khó quản lý cancellation.

Thay vì:

\`\`\`java
@ManagedOperation
public void rebuildIndex() {
    expensiveRebuild();
}
\`\`\`

có thể thiết kế:

\`\`\`java
@ManagedOperation
public String startRebuild() {
    String jobId = java.util.UUID.randomUUID().toString();
    executor.submit(() -> rebuild(jobId));
    return jobId;
}

@ManagedOperation
public String getRebuildStatus(String jobId) {
    return statusStore.getOrDefault(jobId, "UNKNOWN");
}
\`\`\`

Đây là pseudocode cấu trúc: \`executor\`, \`rebuild\` và \`statusStore\` cần được định nghĩa, quản lý lifecycle, concurrency, lỗi và retention thực tế.

Ưu điểm:

- Lời gọi khởi chạy nhanh.
- Có thể trả \`jobId\` để đối chiếu.
- Client theo dõi tiến độ qua operation/attribute.
- Giảm rủi ro client giữ một RMI call hàng phút.
- Có thể định nghĩa cancellation có kiểm soát.

Nhưng nếu mất response chứa \`jobId\`, client vẫn có thể gặp bất định. Muốn retry an toàn, tốt hơn để **client cung cấp operationId**, thay vì chỉ sinh ID phía server.

## 10. Phân loại exception khi gọi remote operation

| Exception | Thường gợi ý | Hướng xử lý |
|---|---|---|
| \`InstanceNotFoundException\` | Sai ObjectName hoặc MBean đã unregister | Query MBeans, kiểm tra lifecycle/server |
| \`ReflectionException\` | Operation/signature không khớp | Đọc \`MBeanInfo.getOperations()\` |
| \`MBeanException\` | Checked exception do MBean/adapter trả | Inspect target exception, xử lý nghiệp vụ |
| \`RuntimeMBeanException\` | Runtime exception trong MBean path | Inspect cause, logs tại server |
| \`SecurityException\` | Quyền không đủ | Kiểm tra policy/auth, không tự bypass |
| \`IOException\` | Transport/connector failure | Xác định trạng thái operation trước retry |
| \`RuntimeErrorException\` | Java \`Error\` từ MBean path | Cảnh báo lỗi nghiêm trọng |
| \`ClassNotFoundException\` trong deserialize/codec path | Kiểu dữ liệu không có ở client | Kiểm tra classpath, dùng Open Types khi phù hợp |

Wrapper và chi tiết lỗi tùy MBean implementation, client và connector. \`IOException\` ở client không phải bằng chứng chắc chắn về trạng thái server.

### 10.1. Ví dụ client phân nhánh lỗi

\`\`\`java
try {
    connection.invoke(
        name, "startDrain",
        new Object[]{"op-123"},
        new String[]{String.class.getName()});

} catch (InstanceNotFoundException ex) {
    // Wrong ObjectName or context lifecycle change.

} catch (ReflectionException ex) {
    // Wrong name/signature, inspect MBeanInfo.

} catch (MBeanException ex) {
    Throwable target = ex.getTargetException();
    // Operation failure reported by MBean.

} catch (RuntimeMBeanException ex) {
    Throwable target = ex.getTargetException();
    // Runtime failure reported through JMX.

} catch (SecurityException ex) {
    // Permission denied; do not retry with bypass.

} catch (IOException ex) {
    // Execution outcome may be unknown.
    // Reconcile using operationId/status when supported.
}
\`\`\`

Trong hệ thống thật, không được nuốt exception như đoạn minh họa. Hãy ghi log có cấu trúc, xử lý trạng thái kết quả và trả thông báo vận hành an toàn.

## 11. JMX/RMI: registry port, connector port và hostname

Remote JMX/RMI có thể gồm:

\`\`\`text
Client -> RMI registry port -> connector stub
                                   |
                                   v
                             RMI server port
                                   |
                                   v
                               MBeanServer
\`\`\`

Một URL dạng:

\`\`\`text
service:jmx:rmi:///jndi/rmi://jmx.internal.example:9010/jmxrmi
\`\`\`

có thể chỉ ra registry lookup, nhưng stub RMI có thể chứa host/port khác. Một số cấu hình JVM sử dụng:

\`\`\`text
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9011
-Djava.rmi.server.hostname=jmx.internal.example
\`\`\`

Đây là ví dụ cấu hình endpoint, **không phải cấu hình production hoàn chỉnh**. Còn cần xác thực, TLS, firewall và phân quyền theo JDK và môi trường. Không bật remote JMX không xác thực trên mạng công cộng.

Nếu client kết nối registry được nhưng \`invoke\` timeout hoặc connection fail, kiểm tra:

1. RMI stub quảng bá hostname nào.
2. Client phân giải hostname đó có đúng không.
3. Cổng RMI server có được firewall cho phép không.
4. DNS/NAT/VPN có thay đổi đường đi không.
5. TLS và authentication có nhất quán không.
6. Server có đang quá tải hoặc đóng connector không.

## 12. Đo latency chính xác hơn

### 12.1. Đo ở client

\`\`\`java
long started = System.nanoTime();

try {
    connection.invoke(
        name, "getDrainStatus",
        new Object[0], new String[0]);
} finally {
    long elapsedNanos = System.nanoTime() - started;
    System.out.printf(
        "JMX invoke latency: %.2f ms%n",
        elapsedNanos / 1_000_000.0);
}
\`\`\`

\`System.nanoTime()\` thích hợp để đo khoảng thời gian tương đối, không dùng làm timestamp tuyệt đối. Nên ghi tên operation, ObjectName đã chuẩn hóa, kết quả (success/error) và correlation ID nếu có.

### 12.2. Đo tại server

Trong managed operation, đo thời gian xử lý nghiệp vụ:

\`\`\`java
@ManagedOperation
public void refreshIndex() {
    long started = System.nanoTime();
    try {
        indexService.refresh();
    } finally {
        long elapsed = System.nanoTime() - started;
        metrics.recordRefreshDuration(elapsed);
    }
}
\`\`\`

\`indexService\` và \`metrics\` là dependencies minh họa. Nếu client đo 20 giây nhưng server operation đo 50 ms, vấn đề có thể nằm ngoài business logic (network, queue, serialization, connector). Nếu cả hai đều chậm, ưu tiên điều tra server logic và tài nguyên.

### 12.3. Đo phân phối thay vì chỉ một mẫu

Một giá trị trung bình che mất tail latency. Với hệ thống nhiều lời gọi, theo dõi:

- Số lần gọi thành công/thất bại.
- P50/P95/P99 latency nếu đủ số mẫu.
- Số timeout/network disconnect.
- Thời gian connect và invoke riêng biệt.
- Số MBean operations đang chạy và hàng chờ.
- Tỉ lệ retry và kết quả reconcile.

Không gắn secret hoặc tham số nhạy cảm vào metric labels, logs hoặc ObjectName.

## 13. Circuit breaker, retry và backoff

Các pattern resilience thường được áp dụng ở tầng client:

**Timeout budget:** giới hạn thời gian chờ của một workflow, nhưng không tự hủy server invocation.

**Retry có điều kiện:** chỉ retry khi operation được định nghĩa idempotent hoặc có operationId/deduplication bảo đảm.

**Exponential backoff:** giảm áp lực khi connector/server tạm thời quá tải.

**Circuit breaker:** ngừng gửi request đến endpoint đang lỗi lặp lại, tránh tạo thêm tải.

**Bulkhead:** giới hạn số lời gọi JMX chậm đồng thời để không chiếm hết thread pool của ứng dụng client.

Với operation quản trị có side effect, nên phân loại:

| Operation | Có thể tự động retry? | Lý do |
|---|---|---|
| \`getStatus()\` | Thường có thể với chính sách phù hợp | Chủ yếu read-only |
| \`getQueueSize()\` | Thường có thể | Không có side effect mong đợi |
| \`setEnabled(true)\` | Có điều kiện | Idempotent nếu semantics đúng và không kích hoạt side effect lặp |
| \`startJob(operationId)\` | Có thể nếu server deduplicate đúng | Cùng ID không tạo thêm job |
| \`restart()\` | Không retry mù | Có thể gây restart nhiều lần |
| \`drain()\` | Không retry mù | Có thể làm thay đổi trạng thái nhiều lần |
| \`rotateCredentials()\` | Không retry mù | Tác động bảo mật và không chắc chắn |

Không lấy \`IOException\` làm tín hiệu retry tự động cho mọi operation.

## 14. Kiểm thử lỗi mạng và timeout

Một integration test remote JMX nên dùng môi trường lab, connector riêng và một MBean có tác dụng phụ được kiểm soát.

### 14.1. Các kịch bản cần thử

1. **Server chưa chạy:** client connect thất bại.
2. **Sai hostname:** DNS hoặc network failure.
3. **Sai RMI port:** registry lookup thành công nhưng connector handshake thất bại.
4. **Operation chậm:** server ngủ có kiểm soát để đo latency.
5. **Disconnect trước request:** invocation không tới server.
6. **Disconnect sau request nhưng trước response:** client không biết trạng thái kết quả.
7. **Server restart:** ObjectName có thể cần discovery lại.
8. **Authorization denied:** phân biệt security failure với transport failure.
9. **Operation throws:** \`MBeanException\` hoặc \`RuntimeMBeanException\`, không phải timeout.
10. **Nhiều request cùng lúc:** kiểm tra thread pool saturation và queueing.

Không cố tình ngắt mạng production hoặc chạy operation gây mất dữ liệu để thử nghiệm. Dùng test service cô lập và operation như increment counter trong fixture.

### 14.2. Test “at most once” bằng operationId

Tạo \`startTask(String id)\` trong MBean với cấu trúc concurrent map:

\`\`\`java
private final ConcurrentMap<String, String> states =
    new ConcurrentHashMap<>();

public String startTask(String id) {
    return states.computeIfAbsent(id, key -> {
        executor.submit(() -> runTask(key));
        return "ACCEPTED";
    });
}
\`\`\`

Đây là mô hình khởi đầu, không phải implementation production hoàn chỉnh. Cần xử lý race, lỗi submit task, status update, retention, restart/persistence và tính atomic của deduplication nếu yêu cầu mạnh. Nếu \`executor.submit\` ném exception trong mapping function, entry có thể không được lưu. Nếu task hoàn tất quá sớm, logic ghi \`ACCEPTED\` có thể ghi đè một status mới; nên tách trạng thái và submit một cách có kiểm soát.

Một test nên gửi cùng ID nhiều lần và xác minh tác vụ thực tế chỉ chạy một lần. Sau đó mô phỏng mất response để kiểm tra client có thể dùng ID để query status.

## 15. Quan hệ với Spring Framework JMX

Spring hỗ trợ export bean qua \`MBeanExporter\`, \`@ManagedResource\` và \`@ManagedOperation\`. Điều này không tự thay đổi semantics của remote transport.

Ví dụ:

\`\`\`java
@Component
@ManagedResource(
    objectName = "training.remote:type=Maintenance,name=Primary")
public class MaintenanceControl {

    @ManagedOperation
    public String startReindex(String requestId) {
        return maintenanceService.startIdempotent(requestId);
    }
}
\`\`\`

MBean được Spring export vào \`MBeanServer\`. Remote client cần một \`JMXConnectorServer\` hoặc management agent kết nối tới server đó. Có thể sử dụng Spring \`ConnectorServerFactoryBean\` khi cần cấu hình connector, nhưng phải quản lý network, authentication và TLS phù hợp.

### 15.1. MBeanExporter không quyết định timeout mạng

\`MBeanExporter\` chỉ chịu trách nhiệm đăng ký MBean và metadata/exposure. Nó không phải component điều khiển packet loss, socket timeout hoặc RMI registry. Để chẩn đoán remote call chậm, cần quan sát connector/client và operation implementation, không chỉ chỉnh exporter.

### 15.2. Local proxy và remote proxy

\`MBeanProxyFactoryBean\` có thể cung cấp Java interface phía client. Khi proxy dùng local MBeanServer, không có network transport. Khi proxy dùng remote JMX, cùng method \`startReindex\` có thể ném exception do connector/network. Một wrapper interface thân thiện không loại bỏ khả năng timeout hoặc kết quả không chắc chắn.

## 16. Một quy trình xử lý sự cố theo tầng

Khi \`invoke\` timeout hoặc báo lỗi:

**Bước 1 — Xác nhận endpoint:** service URL, hostname, registry port, connector port, DNS và routing.

**Bước 2 — Xác nhận TLS/auth:** chứng chỉ, truststore, credentials, access policy và quyền thực hiện operation.

**Bước 3 — Xác nhận MBean:** dùng \`queryNames\`, \`isRegistered\`, \`getMBeanInfo\`; kiểm tra ObjectName và operation signature.

**Bước 4 — Xác nhận client latency:** tách connect và invoke, ghi thời gian/exception class.

**Bước 5 — Xác nhận server execution:** tìm logs/correlation ID, thời gian operation và trạng thái task.

**Bước 6 — Xác nhận outcome:** nếu client timeout sau khi request có thể đã gửi, query trạng thái trước khi quyết định retry.

**Bước 7 — Cải thiện thiết kế:** dùng asynchronous operation, operationId, deduplication, deadline và monitoring khi cần.

Một bảng chẩn đoán nhanh:

| Triệu chứng | Nguyên nhân khả dĩ | Bằng chứng |
|---|---|---|
| Connect timeout | DNS, TCP, firewall, RMI endpoint | Connector logs, network path |
| Connect OK nhưng invoke chậm | Business logic, GC, server queue | Server execution timing |
| Registry reachable, client vẫn lỗi | RMI stub host/port sai | RMI configuration |
| Invoke \`IOException\` sau vài giây | Disconnect hoặc response mất | Reconcile status bằng request ID |
| Invoke \`ReflectionException\` | Sai tên/signature | \`MBeanInfo\` |
| Invoke \`InstanceNotFoundException\` | Sai server/ObjectName hoặc unregister | \`queryNames\` |
| Invoke \`SecurityException\` | Thiếu quyền | Access logs và policy |
| Operation hoàn tất nhưng client báo timeout | Response path lỗi/chậm | Correlation ID + server status |

## 17. Bài tập thực hành

### Bài tập A — Đo local và remote latency

Tạo MBean với operation \`ping()\` trả chuỗi ngắn, rồi gọi qua local MBeanServer và JMXConnector lab. Đo P50/P95 khi chạy nhiều lần. Giải thích vì sao remote thường thêm chi phí kết nối và serialization.

### Bài tập B — Operation chậm

Tạo operation \`sleepFor(long millis)\` chỉ trong lab. Dùng client waiting deadline 2 giây và operation ngủ 5 giây. Quan sát việc client ngừng chờ không chứng minh server method dừng. Không dùng operation này trên production.

### Bài tập C — Mất kết nối

Dùng một counter operation có request ID. Mô phỏng ngắt kết nối sau khi gửi request; xác minh cách client đối chiếu trạng thái thay vì tăng counter lần hai.

### Bài tập D — RMI ports

Cấu hình môi trường lab có registry port và RMI server port cố định. Kiểm tra các trường hợp cổng registry mở nhưng cổng server bị chặn; ghi lại lỗi client. Chỉ triển khai trong mạng thử nghiệm được cấp quyền.

### Bài tập E — Phân loại exceptions

Gọi lần lượt operation sai tên, ObjectName sai và operation ném \`IllegalStateException\`. Viết client phân biệt \`ReflectionException\`, \`InstanceNotFoundException\` và \`RuntimeMBeanException\`. Thêm trường hợp connector bị ngắt để thấy \`IOException\` khác lỗi nghiệp vụ.

### Bài tập F — Thiết kế start/status

Chuyển một operation chạy 30 giây thành \`startJob(id)\` và \`getJobStatus(id)\`. Viết test gọi lặp cùng ID và xác minh side effect chỉ thực hiện một lần; bổ sung retention và recovery policy khi server restart.

## 18. Câu hỏi tự kiểm tra

1. \`JMXConnectorFactory.connect\` timeout khác \`MBeanServerConnection.invoke\` timeout thế nào?
2. Vì sao \`IOException\` không chứng minh server operation chưa chạy?
3. Lời gọi remote JMX/RMI có thể cần những endpoint mạng nào?
4. \`Future.get(timeout)\` có hủy được MBean operation trên server không?
5. Khi nào một operation có thể retry an toàn?
6. \`operationId\` giúp xử lý duplicate requests ra sao?
7. Tại sao operation dài nên có API start/status?
8. Những yếu tố nào khiến total invoke latency cao dù business logic nhanh?
9. \`MBeanExporter\` có điều khiển timeout mạng không?
10. Tại sao client phải phân biệt JMX exception với transport exception?

## 19. Tài liệu tham khảo

- Java SE 21 — \`MBeanServerConnection\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE 21 — \`JMXConnectorFactory\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXConnectorFactory.html
- Java SE 21 — \`JMXConnector\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXConnector.html
- Java SE 21 — \`JMXServiceURL\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXServiceURL.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html

**Ghi nhớ:** remote JMX \`invoke\` là một lời gọi qua mạng, không phải method call local có bảo đảm phản hồi. Timeout hoặc \`IOException\` có thể để lại kết quả không xác định. Hãy tách latency kết nối khỏi thời gian xử lý, quan sát theo correlation ID, thiết kế operation an toàn khi lặp và **không retry mù khi có side effect**.
