# Đo chi phí JMX trong môi trường gần production

## 1. Vì sao phải đo chi phí JMX?

JMX (Java Management Extensions) là cơ chế quản trị JVM và ứng dụng Java. Trong Spring Framework, `MBeanExporter` có thể công bố bean dưới dạng MBean, `@ManagedAttribute` công bố trạng thái và `@ManagedOperation` công bố thao tác. Công cụ như JConsole, VisualVM hoặc monitoring agent thường gọi các attribute theo chu kỳ.

JMX không miễn phí về tài nguyên. Chi phí có thể đến từ:

- Thực thi getter/operation trong MBean: lấy lock, duyệt collection, đọc database hoặc truy vấn hệ thống khác.
- Reflection, metadata inspection, chuyển đổi dữ liệu, serialisation và allocation.
- Những request JMX đồng thời trên `MBeanServer` hoặc connector.
- RMI/JMX remote connector, network, TLS, authentication và notification delivery.
- Tác động gián tiếp đến CPU, heap, GC, thread pools và lock contention của ứng dụng.
- Logging/metrics được bổ sung để quan sát chính đường JMX.

**Một MBean hiển thị được trong JConsole không chứng minh tác động vận hành của nó là nhỏ.** Để triển khai đáng tin cậy, cần đo chi phí trên môi trường gần production, với workload và tần suất polling tương tự thực tế.

Bài này hướng dẫn lập thí nghiệm, xác định baseline, chọn metric, đo latency, tránh sai lệch benchmark và đưa ra tiêu chí chấp nhận dựa trên yêu cầu của hệ thống.

## 2. Mục tiêu đo: chia ba loại chi phí

### 2.1. Chi phí công bố MBean

Đo startup và runtime sau khi `MBeanExporter` đăng ký MBean:

- Thời gian khởi tạo Spring context.
- Số MBean và kích thước metadata cần duy trì.
- Thời gian registration/unregistration.
- Bộ nhớ bổ sung do MBean descriptors, listeners hoặc proxy.
- Tác động khi redeploy, đăng ký hàng loạt hoặc nhiều context cùng JVM.

Thí nghiệm này quan trọng khi ứng dụng export hàng nghìn MBean hoặc tên ObjectName sinh theo tenant/instance.

### 2.2. Chi phí khi client đọc hoặc gọi MBean

Đây thường là thành phần lớn nhất khi JMX được monitoring agent polling liên tục:

- Thời gian mỗi `getAttribute`, `getAttributes`, `getMBeanInfo` và `invoke`.
- Chênh lệch local versus remote JMX.
- Số request/giây, số client và concurrency.
- Payload/serialization size và network bytes.
- Giá trị p50, p95, p99 và timeout/error rate.

### 2.3. Tác động lên ứng dụng nghiệp vụ

Đây mới là metric quan trọng nhất:

- Throughput xử lý request/message/job.
- Latency p95/p99 của nghiệp vụ.
- CPU utilization và CPU time.
- Heap occupancy, allocation rate, GC pause và GC frequency.
- Thread states, lock contention và blocked time.
- Database pool utilization và query count nếu getter liên quan DB.

Một phép đo JMX nhanh không đủ nếu nó làm nghiệp vụ chậm rõ rệt. Cần nhìn cả **chi phí trực tiếp của JMX** và **chi phí gián tiếp trên workload chính**.

## 3. “Gần production” nghĩa là gì?

Môi trường gần production không nhất thiết phải dùng dữ liệu thật. Nó cần phản ánh những đặc điểm ảnh hưởng tới hiệu năng:

| Yếu tố | Cần tương đồng |
| --- | --- |
| JVM/JDK | Major version, GC, heap sizing, flags quan trọng |
| Spring Framework/Boot | Phiên bản, AOP proxy, exporter configuration |
| CPU | Số core, CPU quota/container throttling, architecture |
| Memory | Heap, direct memory và container limit |
| Workload | Request mix, transaction rate, queue depth, concurrency |
| Dữ liệu | Kích thước/cấu trúc đại diện, phân phối hot keys |
| MBeans | Số lượng, loại getter/operation, frequency |
| Monitoring | Số agent, số request/giây, polling interval |
| Remote JMX | Network latency, TLS/auth, ports và topology |
| Dependencies | Database/cache/remote service với hành vi tương ứng |

Không sử dụng dữ liệu khách hàng nhạy cảm khi có thể tạo synthetic dataset tương đương về quy mô và độ phức tạp.

Nếu test chỉ chạy một JVM nhàn rỗi trên laptop, kết quả khó dự đoán tác động khi production đang chạy ở CPU quota sát ngưỡng hoặc gặp GC pressure.

## 4. Xác định câu hỏi và giả thuyết trước khi đo

Một bài đo có mục tiêu rõ ràng hơn “xem JMX có chậm không”.

Ví dụ:

- Với 3 monitoring agents polling 20 attributes mỗi 10 giây, JMX có làm tăng CPU trung bình quá ngưỡng vận hành không?
- Khi getter `PendingOrders` lấy số liệu từ database, nó có làm tăng query rate/latency p99 lúc DB tải cao không?
- Với 500 MBean thay vì 50 MBean, thời gian khởi động/export có thay đổi đáng kể không?
- Khi gọi `getMBeanInfo` hàng loạt sau startup, allocation/GC tăng ở mức nào?
- Nếu tăng polling từ 60 giây xuống 5 giây, tác động lên application throughput là bao nhiêu?
- Remote JMX qua TLS tăng độ trễ so với local connection thế nào?

Nên ghi lại **baseline expectation** và **acceptance threshold** trước test, theo SLO/budget thực tế thay vì sau khi có số liệu mới chọn ngưỡng cho dễ qua.

## 5. Tính polling load trước khi chạy

Một xấp xỉ đơn giản:

```text
JMX attribute reads/second
  ≈ số client × số attribute mỗi lượt ÷ polling interval (giây)
```

Ví dụ:

```text
4 clients × 30 attributes / 10 seconds
= 12 attribute reads/second
```

Nếu mỗi lượt polling gọi cả `getMBeanInfo`, `queryNames`, notifications hoặc batch `getAttributes`, khối lượng request thực tế khác con số trên. Nhiều agent thực hiện discovery và metadata refresh theo lịch riêng.

Một mô hình chi phí:

```text
C_request
 = C_connector
 + C_dispatch
 + C_getter
 + C_serialization
 + C_network
```

Không nhất thiết đo tách biệt từng hạng mục bằng số tuyệt đối; mô hình giúp tìm thành phần cần tối ưu khi quan sát thấy tail latency cao.

Đặc biệt, `C_getter` có thể biến đổi theo kích thước dữ liệu hoặc tải DB. Một getter `O(N)` sẽ đắt dần khi collection lớn, dù benchmark ban đầu thấy nhanh.

## 6. Thiết lập các nhóm thí nghiệm

Một thiết kế thí nghiệm thực tế:

| Kịch bản | JMX exporter | JMX polling | Workload nghiệp vụ |
| --- | --- | --- | --- |
| A - Baseline | Tắt/không export các MBean thử nghiệm | Không | Giữ ổn định |
| B - Export only | Bật exporter | Không | Giữ như A |
| C - Normal monitoring | Bật | Tần suất dự kiến | Giữ như A |
| D - Peak monitoring | Bật | Tần suất cao hơn | Giữ như A |
| E - Failure mode | Bật | Polling lúc DB/CPU bị áp lực | Workload gần ngưỡng |
| F - Remote/TLS | Bật remote JMX an toàn | Client từ network đại diện | Giữ như A |

So sánh A với B giúp ước lượng overhead của việc export mà không polling. So sánh B với C/D đo chi phí chính của việc quan sát. So sánh C với F giúp phân biệt overhead remote connector/TLS/topology.

Để giảm ảnh hưởng của môi trường thay đổi theo thời gian, có thể chạy lặp các kịch bản và thay đổi thứ tự có kiểm soát. Không chạy load test production thật nếu không có phê duyệt và giới hạn rủi ro.

## 7. Instrument JMX client: đo từ góc nhìn caller

Một phép thử dùng `MBeanServerConnection` có thể đo latency của thao tác đọc:

```java
import java.util.concurrent.TimeUnit;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public final class JmxReadProbe {

    public static long readNanos(
            MBeanServerConnection connection,
            ObjectName objectName,
            String attribute) throws Exception {

        long start = System.nanoTime();
        connection.getAttribute(objectName, attribute);
        return System.nanoTime() - start;
    }

    public static double nanosToMillis(long nanos) {
        return nanos / 1_000_000.0;
    }
}
```

`System.nanoTime()` phù hợp với đo khoảng thời gian trôi qua, không dùng `currentTimeMillis()` để tính latency chính xác khi test micro/millisecond.

Đo nhiều lần và tính percentile theo sample distribution, không chỉ đo một request đầu tiên vì request đầu có thể chứa kết nối, metadata discovery, class loading và JIT warmup.

Với remote client:

```java
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://jmx.internal:9010/jmxrmi"
);

try (JMXConnector connector =
        JMXConnectorFactory.connect(url)) {
    MBeanServerConnection remote =
        connector.getMBeanServerConnection();

    // Chạy warmup và đo getAttribute/invoke có kiểm soát.
}
```

Đoạn trên là mô hình test; deployment remote thật phải cấu hình TLS, authentication và credential store phù hợp. Không dùng kết nối JMX không bảo vệ trên mạng công khai.

## 8. Percentile, throughput và error rate

Nên báo cáo ít nhất:

- **p50**: trạng thái thông thường.
- **p95**: vùng tail chịu tác động khi tải tăng.
- **p99**: những lời gọi chậm nhất, đáng quan tâm nếu polling ảnh hưởng service.
- **Max/timeout**: giá trị ngoại lệ hoặc lỗi kết nối.
- **Throughput**: số attribute reads/operations mỗi giây.
- **Error rate**: tỉ lệ `JMException`, IOException, authentication failures hoặc operation errors.

Ví dụ một bảng đo (số liệu chỉ minh họa, không phải kết quả benchmark):

| Kịch bản | Reads/s | p50 (ms) | p95 (ms) | p99 (ms) | Errors |
| --- | ---: | ---: | ---: | ---: | ---: |
| Export only | 0 | - | - | - | 0 |
| Normal local polling | 20 | 0.7 | 2.1 | 4.5 | 0 |
| Peak local polling | 200 | 1.1 | 6.4 | 15.2 | 0 |
| Remote polling TLS | 20 | 4.2 | 12.0 | 28.5 | 0 |

Không suy ra kết quả production từ bảng mẫu. Báo cáo thật cần nêu hardware, JDK, workload, cỡ mẫu, thời gian đo và các điều kiện quan trọng.

Một mean latency thấp có thể che p99 cao do GC hoặc lock contention. Khi đánh giá tác động lên người dùng, ưu tiên các percentile của workload nghiệp vụ song song.

## 9. Microbenchmark và JMH: dùng đúng chỗ

Một benchmark gọi trực tiếp `getAttribute` trong vòng lặp có thể bị nhiễu bởi JVM warmup, GC, scheduling, CPU frequency và test harness. Nếu cần đo chi phí của một getter Java thuần hoặc một adapter nhỏ, JMH (Java Microbenchmark Harness) phù hợp hơn một vòng `for` đo thủ công.

Tuy nhiên JMH đo **thành phần hẹp**:

- Getter trả về một `AtomicInteger`.
- Getter dựng snapshot từ một immutable record.
- Tạo ObjectName hoặc xử lý metadata đã cache.
- So sánh implementation getter trước và sau tối ưu.

JMH không thay thế integration benchmark, vì nó không tái hiện toàn bộ Spring context, JMX connector, network, DB hoặc mức độ tranh chấp tài nguyên production.

Một phép đo tốt có hai lớp:

1. **Component microbenchmark** để xác định hotspot và hướng tối ưu.
2. **System benchmark** dưới workload đại diện để đo impact lên service.

## 10. Getter đắt: trường hợp cần chú ý

Ví dụ không nên đặt truy vấn database trực tiếp trong `@ManagedAttribute` khi monitoring polling dày:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;

@ManagedAttribute
public long getPendingOrders() {
    return orderRepository.countPendingOrders();
}
```

Nếu monitoring agent poll 10 lần/giây, lời gọi đó có thể tạo 10 query/giây, chưa kể nhiều agent đồng thời. Khi DB đang quá tải, việc quan sát có thể làm hệ thống chậm hơn và gây amplification.

Một phương án là duy trì snapshot ở background:

```java
import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;

public record PendingOrderSnapshot(
    long count,
    Instant updatedAt,
    boolean available
) {}

public final class OrderManagementSnapshot {
    private final AtomicReference<PendingOrderSnapshot> latest =
        new AtomicReference<>(
            new PendingOrderSnapshot(0, Instant.EPOCH, false)
        );

    public PendingOrderSnapshot current() {
        return latest.get();
    }

    public void publish(PendingOrderSnapshot snapshot) {
        latest.set(snapshot);
    }
}
```

Getter JMX:

```java
@ManagedAttribute
public long getPendingOrders() {
    return snapshot.current().count();
}

@ManagedAttribute
public String getSnapshotUpdatedAt() {
    return snapshot.current().updatedAt().toString();
}

@ManagedAttribute
public boolean isSnapshotAvailable() {
    return snapshot.current().available();
}
```

Một scheduled job khác tính lại số liệu với timeout, frequency và error handling rõ ràng. Benchmark cả chi phí refresh nền và chi phí getter: chuyển sang background chỉ chuyển chỗ tốn tài nguyên, không làm nó tự biến mất.

## 11. Đo CPU và GC

Bên cạnh latency JMX, thu thập CPU/GC của JVM bằng công cụ phù hợp:

- Java Flight Recorder (JFR) cho CPU profiling, allocation, lock và thread events.
- JDK Mission Control (JMC) để phân tích JFR.
- `jcmd` cho thông tin JVM và các tác vụ chẩn đoán được phép.
- Micrometer/metrics stack để quan sát CPU, GC, heap và application metrics.
- Profiler hoặc tracing agent nếu được đánh giá overhead trước.

Ví dụ triển khai JFR trong một test có giới hạn, theo công cụ và quy trình của môi trường:

```text
jcmd <pid> JFR.start name=jmx-load settings=profile duration=120s
```

Không bật profiler nặng không giới hạn trên production chỉ để đo JMX; profiler cũng có overhead và có thể làm sai lệch kết quả. Khi đo, ghi rõ công cụ nào đang chạy và mức sampling.

Các metric cần nhìn:

- Process CPU và CPU throttling của container.
- Young/old GC count, pause durations.
- Allocation rate và heap occupancy.
- Safepoint stalls nếu môi trường có khả năng quan sát.
- Số thread BLOCKED/WAITING liên quan getter hoặc connector.

## 12. Lock contention và thread blocking

Một getter quản trị có thể lấy cùng lock với luồng nghiệp vụ:

```java
@ManagedAttribute
public int getActiveTasks() {
    synchronized (taskLock) {
        return activeTasks.size();
    }
}
```

Nếu `taskLock` bị giữ lâu, client JMX block và có thể góp phần tăng contention. Dưới workload thật, các request nghiệp vụ cũng chậm đi.

Dùng snapshot/counter khi có thể:

```java
private final java.util.concurrent.atomic.AtomicInteger activeCount =
    new java.util.concurrent.atomic.AtomicInteger();

@ManagedAttribute
public int getActiveTasks() {
    return activeCount.get();
}
```

Counter phải được cập nhật nhất quán khi task bắt đầu/kết thúc. Khi có fail path hoặc cancellation, `finally` có thể giúp tránh counter leak.

Để đo lock contention, kết hợp JFR, thread dumps, blocked time và latency nghiệp vụ. Không chỉ nhìn thời gian getter mà bỏ qua tác động lên threads khác.

## 13. Concurrency và polling burst

Hai agent cùng poll mỗi 10 giây có thể vô tình đồng bộ thời điểm:

```text
t = 0s:  Agent A + B + C đọc 50 attributes
t = 10s: Agent A + B + C đọc 50 attributes
t = 20s: Agent A + B + C đọc 50 attributes
```

Thời điểm burst dễ tạo spike CPU, allocation và network. Trong test, nên thử:

- Polling đều (steady state).
- Polling đồng thời theo burst.
- Polling với jitter để phân tán tải.
- Concurrency cao hơn dự kiến để có safety margin.
- Client disconnect/reconnect liên tục hoặc metadata discovery.
- Phía server đang chịu load peak, GC pressure hoặc DB degraded.

Nếu agent hỗ trợ jitter và batch reads, kiểm tra khả năng giảm spike, nhưng phải đo thật. Một `getAttributes` nhiều tên có thể giảm overhead round-trip remote; chi phí getter bên trong vẫn còn.

## 14. Chi phí getMBeanInfo và discovery

Monitoring agents thường khám phá MBean bằng:

```java
connection.queryNames(
    new ObjectName("com.example:*"),
    null
);

connection.getMBeanInfo(someObjectName);
```

Những lời gọi này không gọi getter nghiệp vụ theo cách `getAttribute`, nhưng vẫn có chi phí metadata, lookup, transport và allocation. Khi có hàng nghìn MBean, việc query mọi name mỗi vài giây có thể tạo overhead đáng kể.

Phép đo riêng:

- Thời gian `queryNames` với số lượng MBean tăng dần.
- Thời gian `getMBeanInfo` cho mỗi MBean hoặc một tập.
- Kích thước metadata và network bytes ở remote connector.
- Số MBean biến động do runtime registration.
- Tần suất discovery và caching của agent.

Không áp dụng `ObjectName` wildcard quá rộng trong mỗi chu kỳ nếu công cụ chỉ cần một tập MBean ổn định. Quản lý pattern có mục tiêu và làm discovery theo lịch phù hợp.

## 15. Chi phí notification

Nếu ứng dụng phát JMX notifications, ngoài polling còn cần đo:

- Số notifications/giây.
- Số listeners.
- Payload size và serialization.
- Thread hoặc executor thực hiện dispatch.
- Queue depth, callback latency và dropping/backpressure.
- Remote connector bandwidth khi nhiều client lắng nghe.

Một listener nặng có thể làm tăng thời gian xử lý của emitter tùy cấu hình dispatch. Không giả định mọi notification luôn bất đồng bộ; cần xem `NotificationBroadcasterSupport` và executor được cung cấp.

Không đưa dữ liệu nhạy cảm vào userData để làm benchmark; dùng dữ liệu tổng hợp và payload sizes đại diện.

## 16. Network và TLS overhead

Remote JMX thường sử dụng RMI, có bước registry lookup rồi kết nối tới endpoint trong stub. Khi benchmark remote:

- Client chạy từ topology tương tự monitoring thực.
- Địa chỉ `java.rmi.server.hostname` và cổng RMI tương thích NAT.
- TLS và authentication bật như môi trường production.
- Network RTT, packet loss và bandwidth đại diện.
- Kết nối reuse hoặc reconnect đúng hành vi agent.
- Socket timeout và lỗi connection được đo, không loại khỏi thống kê.

Không so sánh local `MBeanServer.getAttribute` với remote JMX RMI rồi quy toàn bộ chênh lệch cho chi phí Spring exporter: remote path còn bao gồm network, connector, authentication/TLS và serialization.

Đo cả throughput/latency nghiệp vụ khi remote JMX polling để biết overhead mà production thực sự chịu.

## 17. Lỗi benchmark thường gặp

| Sai lầm | Hệ quả | Hướng khắc phục |
| --- | --- | --- |
| Đo vài request đầu tiên | Warmup/JIT làm kết quả nhiễu | Warmup tách riêng, đo nhiều lần |
| Chỉ đo mean | Che tail latency | Báo cáo p50/p95/p99 và max |
| Test khi JVM idle | Không thấy contention khi peak | Dùng workload đại diện |
| Chỉ đo client time | Không thấy tác động business | Đo CPU/GC/SLO nghiệp vụ song song |
| Tắt TLS/auth cho tiện | Không phản ánh remote setup | Giữ production-like security |
| Không cố định dataset | Chi phí thay đổi khó giải thích | Dataset/version có kiểm soát |
| Thay nhiều biến cùng lúc | Không biết nguyên nhân | Thí nghiệm từng yếu tố |
| Không lặp kịch bản | Dễ nhầm noise thành hiệu ứng | Nhiều run và thống kê |
| Không đo error rate | Request timeout bị bỏ qua | Đếm toàn bộ lỗi và timeouts |
| Chạy profiler quá nặng | Profiler tự tạo overhead | Chọn sampling phù hợp, ghi rõ overhead |
| Poll vào DB thật | Có thể ảnh hưởng dữ liệu/chi phí production | Staging hoặc dữ liệu đại diện |
| Dùng `Thread.sleep` làm tải | Nhịp polling không chính xác | Load generator có scheduling/measurement |

## 18. Mẫu báo cáo một lần đo

Một báo cáo nên có cấu trúc tái hiện được:

```text
Experiment ID: jmx-cost-2026-11
Application build: <commit/build id>
Spring Framework/Boot: <versions>
JDK: <version and GC>
Host/container resources: <CPU/heap/quota>
Dataset: <scale and characteristics>
Business workload: <RPS/transactions/jobs>
MBean count and sampled ObjectNames: <count/list>
JMX clients: <N>, interval: <seconds>, remote TLS: <on/off>
Warmup duration: <minutes>
Measured duration: <minutes>
Runs/repetitions: <N>
JMX request rate / p50 / p95 / p99 / errors: <values>
Business throughput / p95 / p99: <values>
CPU / allocation / GC / locks: <values>
Baseline comparison: <delta and uncertainty>
Decision: <accept/reject/needs investigation>
~~~

Đây là template ghi chép, không phải benchmark result. Nếu sử dụng percent change:

```text
relative delta (%) = (JMX_enabled - baseline) / baseline × 100
```

Đối với metric mà **thấp hơn là tốt** (latency, CPU, GC pause), delta dương thường là overhead. Với throughput, delta âm có thể phản ánh suy giảm. Cần diễn giải theo hướng của metric.

Các số liệu p99 dễ biến động nếu sample size thấp; ghi cỡ mẫu và khoảng tin cậy/biến thiên giữa các run khi yêu cầu quyết định hiệu năng nghiêm ngặt.

## 19. Chọn ngưỡng chấp nhận

Ngưỡng không nên hard-code giống nhau cho mọi ứng dụng. Xây dựa trên:

1. SLO hiện tại của service và khoảng cách tới ngưỡng vi phạm.
2. CPU/memory headroom khi peak.
3. Mức độ quan trọng của JMX telemetry.
4. Tần suất polling và số lượng monitoring clients.
5. Độ trễ/freshness có thể chấp nhận của các attribute.
6. Rủi ro khi DB/cache/service phụ thuộc bị degraded.
7. Chi phí kết nối remote và bảo mật.

Ví dụ một nhóm có thể đặt tiêu chí (chỉ minh họa):

- JMX normal polling không làm p99 nghiệp vụ tăng quá một tỷ lệ đã thống nhất.
- CPU overhead dưới budget đã được chủ hệ thống chấp thuận.
- Không phát sinh query DB ở đường getter thường xuyên.
- Không có timeout/exception do polling trong workload chuẩn.
- Không có memory growth liên tục hoặc MBean/notification-listener leak qua restart.

Tính bền vững quan trọng hơn một phép đo đẹp: sau vài giờ soak test, bộ nhớ, thread hoặc latency không được tăng dần do registry/listener không được dọn.

## 20. Quy trình đo thực hành

Một đợt đo hoàn chỉnh:

1. **Chốt hợp đồng JMX:** liệt kê ObjectName, attributes, operations, notifications được dùng.
2. **Chốt workload nghiệp vụ:** phân phối request và mức peak.
3. **Thiết lập staging gần production:** JVM, hardware, data scale và dependencies.
4. **Chạy baseline:** đo service không JMX polling, ghi CPU/GC/latency.
5. **Bật exporter không polling:** quan sát startup/registration overhead.
6. **Bật polling thực tế:** số client, nhịp, batch và metadata discovery.
7. **Thử burst và failure:** tải cao, DB chậm, reconnect.
8. **Đo đồng thời:** JMX latency và tác động lên service.
9. **Lặp lại và phân tích:** median/percentiles, delta, noise.
10. **Tối ưu điểm nghẽn:** snapshot getters, giảm discovery, cache metadata hoặc interval.
11. **Đo lại cùng điều kiện:** chứng minh hiệu quả tối ưu.
12. **Ghi quyết định vận hành:** ngưỡng, polling interval, owners và phương án rollback.

Nếu test cho thấy một attribute có chi phí không chấp nhận được, không nhất thiết bỏ JMX hoàn toàn. Có thể đổi getter thành đọc cached snapshot, giảm polling rate hoặc tách operation lấy số liệu đắt có giới hạn.

## 21. Ghi nhớ

**Đo chi phí JMX trong môi trường gần production phải đo cả ứng dụng, không chỉ JMX client.** `MBeanExporter`/MBeanServer có chi phí đăng ký và metadata, còn polling, remote connector, notification và getter nghiệp vụ tạo chi phí runtime. Dùng baseline và các kịch bản export-only/normal/burst, ghi p95/p99, CPU, GC, lock contention và tác động lên throughput nghiệp vụ. Giữ TLS/auth, dữ liệu và workload tương đồng production; lặp phép đo, công bố điều kiện và đặt ngưỡng dựa trên SLO trước khi quyết định triển khai.
