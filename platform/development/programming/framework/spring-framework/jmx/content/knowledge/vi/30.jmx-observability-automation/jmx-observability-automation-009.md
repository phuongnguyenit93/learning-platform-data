# Xử lý server không phản hồi hoặc dữ liệu cũ trong Spring Framework JMX

## Mục tiêu học tập

Trong nhóm **Quan sát và tự động hóa**, Spring Framework JMX cung cấp giao diện quản trị giúp đọc metrics và thực thi operation qua MBeanServer. Khi server không phản hồi hoặc số liệu liên tục hiển thị giá trị cũ, nguyên nhân có thể thuộc Spring bean, MBeanExporter, MBeanServer, JMXConnectorServer, RMI transport hoặc client/dashboard.

Sau bài học, bạn có thể:

- Phân biệt lỗi kết nối, lỗi invocation, sai ObjectName, dữ liệu không cập nhật và client cache.
- Xác định chính xác server, JVM, managed bean và exporter đang cung cấp dữ liệu.
- Thiết kế heartbeat, timestamp, sequence number, polling deadline và kiểm tra freshness.
- Chẩn đoán bằng JMX API, thread dump, logs, health signals và network metrics.
- Reconnect có backoff mà không retry mù operation có tác dụng phụ.
- Thiết kế trạng thái FRESH, STALE, UNKNOWN, UNAVAILABLE và giới hạn tự động khắc phục.
- Kiểm thử bằng các fixture độc lập và xây dựng runbook thực tế.

## 1. Phân loại đúng triệu chứng trước khi xử lý

| Triệu chứng | Nguyên nhân có thể | Phép kiểm tra trước tiên |
| --- | --- | --- |
| JMX client không kết nối được | Connector chưa chạy, sai URL, port, DNS, TLS hoặc authentication | Connector logs, URL và network |
| Kết nối được nhưng request bị treo | JVM bận, thread bị chặn, operation dài hoặc transport lỗi | Thread dump, request latency |
| Một operation treo, các attribute khác vẫn đọc được | Business code của operation có lock/I/O chậm | Stack trace và dependency metrics |
| InstanceNotFoundException | Tên JMX không có trên server hiện tại | isRegistered và queryNames |
| Attribute vẫn trả kết quả nhưng số không đổi | Không có event mới, bean không cập nhật hoặc dữ liệu cache | Heartbeat và lastUpdated |
| Sau deploy vẫn thấy số liệu phiên bản cũ | Exporter giữ bean cũ hoặc client kết nối JVM cũ | InstanceId, buildId, registration policy |
| Một dashboard stale nhưng client khác bình thường | Cache, polling hoặc endpoint khác nhau | So sánh observedAt và target URL |
| Notification ngừng nhưng attributes vẫn đọc được | Listener/connection mất, không có re-subscribe | Notification sequence và snapshot |
| Sau restart số liệu reset | Counter thuộc JVM mới | Instance identity và counter semantics |

Không nên xem mọi giá trị không thay đổi là dữ liệu lỗi. Một queue trống có thể giữ QueueDepth=0 trong nhiều giờ. Cần thêm tín hiệu chứng minh dữ liệu được quan sát đúng lúc và nguồn còn sống.

## 2. Pipeline dữ liệu cần khoanh vùng

Các thành phần liên quan:

~~~text
Business event hoặc scheduled update
               |
               v
       Spring-managed bean
               |
               | MBeanExporter
               v
      MBeanServer registry
        ObjectName -> MBean
               |
        +------+------+
        |             |
   Local client   JMXConnectorServer
                      |
                      | RMI / SSL / auth / network
                      v
                Remote client
                      |
                      v
            Poller / cache / dashboard
~~~

Một triệu chứng ở dashboard không đủ chứng minh bean bị lỗi. Hãy xác định tầng cuối cùng đã phản hồi chính xác.

Nếu local MBeanServer trả dữ liệu mới mà remote client không đọc được, ưu tiên connector, transport và client. Nếu cả local lẫn remote cùng trả dữ liệu cũ, kiểm tra managed bean, vòng đời exporter, cache và naming.

## 3. MBeanServer không đồng nghĩa connector từ xa

MBeanServer chứa registry. JMXConnectorServer mở endpoint cho client từ xa. MBeanExporter giúp Spring đăng ký bean lên server.

Một MBean có thể được đăng ký thành công trong JVM nhưng JConsole từ xa vẫn không tới được connector. Ngược lại, remote connector có thể chấp nhận kết nối nhưng registry không có ObjectName mà client yêu cầu.

Ví dụ local check:

~~~java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
        "com.example.jobs:type=ProcessingMonitor,name=primary");

System.out.println(server.isRegistered(name));
~~~

Đoạn này chỉ chính xác nếu exporter thật sự dùng platform server. Khi sử dụng custom MBeanServer, phải lấy đúng server được inject vào exporter, không suy luận từ platform server.

Trong cùng JVM cũng có thể tồn tại nhiều ApplicationContext và MBeanServer độc lập. ObjectName chỉ duy nhất trong phạm vi từng server.

## 4. Tạo management contract có thông tin freshness

Một metric biến động theo nghiệp vụ không thể tự chứng minh liveness. Nên công bố các thuộc tính hỗ trợ điều tra:

~~~java
package com.example.jmx;

public interface ProcessingMonitorMBean {
    String getInstanceId();
    long getProcessedCount();
    long getSnapshotVersion();
    long getLastUpdatedEpochMillis();
    long getHeartbeatEpochMillis();
}
~~~

Implementation:

~~~java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;

public class ProcessingMonitor implements ProcessingMonitorMBean {

    private final String instanceId;
    private final AtomicLong count = new AtomicLong();
    private final AtomicLong version = new AtomicLong();
    private final AtomicLong updatedAt =
            new AtomicLong(System.currentTimeMillis());
    private final AtomicLong heartbeatAt =
            new AtomicLong(System.currentTimeMillis());

    public ProcessingMonitor(String instanceId) {
        this.instanceId = instanceId;
    }

    public void recordProcessed() {
        count.incrementAndGet();
        updatedAt.set(System.currentTimeMillis());
        version.incrementAndGet();
    }

    public void recordHeartbeat() {
        heartbeatAt.set(System.currentTimeMillis());
    }

    @Override
    public String getInstanceId() {
        return instanceId;
    }

    @Override
    public long getProcessedCount() {
        return count.get();
    }

    @Override
    public long getSnapshotVersion() {
        return version.get();
    }

    @Override
    public long getLastUpdatedEpochMillis() {
        return updatedAt.get();
    }

    @Override
    public long getHeartbeatEpochMillis() {
        return heartbeatAt.get();
    }
}
~~~

InstanceId phân biệt các phiên bản bean/JVM. SnapshotVersion thay đổi khi có business update. LastUpdatedEpochMillis cho biết lần cập nhật nguồn. HeartbeatEpochMillis nên được cập nhật theo cadence riêng để quan sát liveness khi không có công việc mới.

Mã minh họa dùng nhiều AtomicLong nên đọc từng attribute không tạo snapshot đa trường hoàn toàn nhất quán. Nếu cần atomicity, đưa toàn bộ dữ liệu vào một immutable snapshot và công bố qua MXBean-compatible type hoặc CompositeData thích hợp.

## 5. Cấu hình Spring MBeanExporter trỏ đúng instance

~~~java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class MonitorJmxConfiguration {

    @Bean
    public ProcessingMonitor processingMonitor() {
        return new ProcessingMonitor("orders-node-A");
    }

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter monitorExporter(
            ProcessingMonitor monitor,
            MBeanServer platformMBeanServer) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(platformMBeanServer);
        exporter.setBeans(Map.of(
            "com.example.jobs:type=ProcessingMonitor,name=primary",
            monitor));
        return exporter;
    }
}
~~~

Exporter phải nhận cùng instance mà business service đang cập nhật. Nếu tự new ProcessingMonitor bên trong exporter trong khi service sử dụng bean khác, JMX sẽ thấy dữ liệu không thay đổi dù ứng dụng xử lý tác vụ bình thường.

Một startup thành công không đủ chứng minh ObjectName đã được đăng ký chính xác. Nên xác minh isRegistered và instanceId từ chính registry.

## 6. Đọc các thuộc tính để khoanh vùng

~~~java
MBeanServer server = context.getBean(MBeanServer.class);

ObjectName name = new ObjectName(
        "com.example.jobs:type=ProcessingMonitor,name=primary");

if (!server.isRegistered(name)) {
    throw new IllegalStateException("Missing MBean: " + name);
}

String instance = (String)
        server.getAttribute(name, "InstanceId");

long version = (Long)
        server.getAttribute(name, "SnapshotVersion");

long lastUpdate = (Long)
        server.getAttribute(name, "LastUpdatedEpochMillis");

long heartbeat = (Long)
        server.getAttribute(name, "HeartbeatEpochMillis");

System.out.println("instance=" + instance);
System.out.println("version=" + version);
System.out.println("sourceUpdatedAt=" + lastUpdate);
System.out.println("heartbeatAt=" + heartbeat);
~~~

Nếu MBean không tồn tại, sử dụng queryNames để tìm domain/key thực tế:

~~~java
for (ObjectName found : server.queryNames(
        new ObjectName("com.example.jobs:*"), null)) {
    System.out.println(found.getCanonicalName());
}
~~~

Không đoán ObjectName từ Spring bean name. Naming strategy và registration policy có thể quyết định tên thực tế khác với giả định.

## 7. Phân biệt sourceUpdatedAt, observedAt và renderedAt

Có ít nhất ba đồng hồ cần phân biệt:

| Trường | Được ghi ở đâu? | Ý nghĩa |
| --- | --- | --- |
| sourceUpdatedAt | Spring bean/MBean | Lần nguồn cập nhật nghiệp vụ |
| heartbeatAt | Nguồn hoặc health scheduler | Lần heartbeat cuối |
| observedAt | JMX polling client | Lần client đọc thành công |
| renderedAt | Dashboard | Lần giao diện cập nhật giá trị |
| instanceId | JVM/bean instance | Xác định nguồn đang được đọc |

Ví dụ:

~~~text
ProcessedCount: 8214
Source updated: 10:05:00 UTC
Last heartbeat: 10:07:50 UTC
Last successful JMX poll: 10:05:15 UTC
Dashboard rendered: 10:08:00 UTC
Status: STALE_POLL
~~~

Trong ví dụ, heartbeat có thể vẫn cập nhật ở nguồn nhưng client không poll thành công sau 10:05:15. Vì vậy vấn đề có khả năng thuộc polling/connector hơn là logic business metric.

Nếu sourceUpdatedAt cũ nhưng heartbeat mới và hệ thống không có job, đó chưa phải lỗi. Freshness policy phải dựa trên loại dữ liệu.

## 8. Thiết kế freshness SLO

Giả sử:

~~~text
heartbeat interval: 10 seconds
poll interval: 15 seconds
maximum heartbeat age: 45 seconds
maximum time since successful poll: 45 seconds
alert threshold: 3 consecutive failures
~~~

Các giá trị chỉ là ví dụ. Chọn threshold theo SLO của sản phẩm, GC pauses, network jitter, application load và độ nhạy cảnh báo.

Một mô hình đơn giản:

- FRESH: poll gần đây thành công và heartbeat trong giới hạn.
- STALE: poll thành công nhưng dữ liệu heartbeat quá cũ.
- UNAVAILABLE: không thể đọc từ JMX trong thời hạn.
- UNKNOWN: thiếu dữ liệu để xác định chính xác tình trạng.
- INVALID: timestamp không hợp lệ, sai đơn vị hoặc bất nhất với kỳ vọng.

Không tự động coi counter đứng yên là STALE. Hãy theo dõi heartbeat/snapshot revision phù hợp.

## 9. Phát hiện stale do IGNORE_EXISTING

Spring MBeanExporter hỗ trợ registration policy. Khi hai contexts cùng đăng ký một ObjectName:

~~~text
Context A -> monitor A -> ObjectName X
Context B -> monitor B -> ObjectName X
Context B policy = IGNORE_EXISTING

MBeanServer:
  X -> monitor A
~~~

Context B có thể khởi tạo thành công nhưng JMX vẫn đọc monitor A. Sau deploy, client tưởng mình đang xem phiên bản B, nhưng thực tế vẫn nhận state của A.

Dấu hiệu:
- InstanceId qua JMX khác instance đang phục vụ request.
- Build/version của MBean không trùng deployment hiện tại.
- MBeanExporter B có policy IGNORE_EXISTING.
- Context A hoặc một exporter khác đã đăng ký trước.
- Tên MBean biến mất khi owner A đóng thay vì chuyển sang B.

Cách xử lý là thiết kế một registration owner rõ ràng, ObjectName duy nhất cho nhiều instances và quy trình chuyển giao khi deploy. Không dùng IGNORE_EXISTING như cách làm mới dữ liệu.

## 10. Đảm bảo đúng server và đúng JVM

Các lỗi nhầm đích phổ biến:

- Client đang kết nối JVM A nhưng dashboard kỳ vọng JVM B.
- Exporter đăng ký custom MBeanServer nhưng công cụ kiểm tra platform MBeanServer.
- MBeanServerFactoryBean trong nhiều contexts tạo nhiều servers độc lập.
- Hai endpoints dùng cùng domain và ObjectName nhưng mang state khác nhau.
- Client cache JMXConnector và không reconnect khi deployment đổi process.

Một JMX client nên lưu endpoint, instanceId, process/build identity và ObjectName cùng mỗi poll. Với môi trường container, thêm pod/replica identity khi có.

Trên remote connector, không giả định một DNS name luôn trỏ cùng process sau failover.

## 11. JMX remote connector không phản hồi

Cấu hình JMX/RMI phổ biến có dạng:

~~~text
service:jmx:rmi:///jndi/rmi://jmx-host:9010/jmxrmi
~~~

RMI có thể có registry port và exported remote object port riêng. Nếu registry lookup thành công mà invocation thất bại, kiểm tra advertised host/port trong stub, firewall và container networking.

Các nguyên nhân:

| Hiện tượng | Khả năng | Cần xác minh |
| --- | --- | --- |
| Connection refused | Server chưa bind/listen hoặc port sai | Startup logs, socket |
| Connection timeout | Route/firewall/host sai | Network policy, DNS |
| NameNotFound jmxrmi | RMI registry không có binding | Registry URL và lifecycle |
| Lookup OK, invocation fail | Remote object endpoint không reachable | Advertised address/port |
| SecurityException | Auth/role không phù hợp | Cấu hình JMX security |
| SSLHandshakeException | TLS trust hoặc protocol mismatch | Test certificates, truststore |
| InstanceNotFoundException | Kết nối đúng transport nhưng sai registry/name | queryNames trên server |
| AttributeNotFoundException | Metadata không có attribute client yêu cầu | getMBeanInfo |

Bất kỳ lỗi nào ở transport cần được tách khỏi lỗi của managed bean. Không thay exporter khi local registry vẫn đọc đúng dữ liệu.

## 12. Timeout client không hủy server-side operation

Khi gọi:

~~~java
Object result = connection.invoke(
        name, "rebuildIndex",
        new Object[0], new String[0]);
~~~

operation có thể chặn trong DB, remote API hoặc lock. Client dùng một Future.get(5, SECONDS) để giới hạn chờ chỉ khiến caller ngừng đợi. Công việc phía server có thể tiếp tục.

Đối với operation có tác dụng phụ:
- Cần request/job ID hoặc idempotency key.
- Truy vấn trạng thái cuối khi timeout.
- Không retry mù vì có thể thực thi hai lần.
- Sử dụng deadline ở business layer, bounded executor và timeout ở external calls.
- Phản hồi ACCEPTED không tương đương SUCCEEDED.

Nếu chỉ có một operation treo, hãy lấy thread dump và kiểm tra path thực thi thay vì coi toàn bộ connector đã chết.

## 13. Dùng thread dump để chẩn đoán JVM không đáp ứng

Công cụ JDK có thể cung cấp thread dump:

~~~bash
jcmd <pid> Thread.print
~~~

Đọc các nhóm thread:
- JMX/RMI dispatch threads.
- Business thread đang thực thi operation.
- Threads chờ database connection/HTTP response.
- Deadlocks hoặc lock contention.
- Worker pools bị saturate.
- Thread nằm trong long GC/safepoint context khi so với GC logs.

Một thread có trạng thái WAITING không tự chứng minh deadlock. Cần xem stack trace, lock ownership và các snapshot tại nhiều thời điểm.

Nếu JVM đang chịu stop-the-world GC pause, request có thể tạm thời không phản hồi. Hãy so sánh timeout với GC pause durations và CPU throttling trước khi thiết kế cảnh báo quá nhạy.

## 14. Khi JMX hỏng, dùng tín hiệu ngoài JMX

Nếu chính JMX endpoint không phản hồi, không thể chỉ dựa vào JMX để xác định nguyên nhân. Nguồn ngoài có thể gồm:

- Application structured logs.
- JVM GC logs và thread dumps.
- Container CPU/memory/throttling metrics.
- Host process liveness.
- Health endpoint riêng đã được bảo vệ.
- Network probe/connector startup logs.
- Alert history và deployment timeline.

Cần đối chiếu timeline theo thời gian và JVM identity. Nếu metrics từ ứng dụng vẫn tăng nhưng JMX read fail, có thể đây là sự cố observability connector, không phải toàn bộ business service.

## 15. Thực hiện reconnect với exponential backoff

Với network lỗi tạm thời, polling client nên thử lại read-only request theo backoff:

~~~text
attempt 1: 1 s
attempt 2: 2 s
attempt 3: 4 s
attempt 4: 8 s
cap: 30 s
add jitter: random small deviation
~~~

Khi authentication failure, không spam cùng credentials sai. Tạo trạng thái cần can thiệp cấu hình.

Sau reconnect cần:
1. Đọc server/instance identity.
2. Đối chiếu ObjectName và MBeanInfo.
3. Reset cache metadata nếu target version đã đổi.
4. Đọc snapshot mới.
5. Đăng ký lại notification listeners nếu cần.
6. Không tự retry operations có side effects đang unknown.

Mỗi reconnect cần quản lý JMXConnector cũ và resource cleanup rõ ràng.

## 16. Polling client biểu diễn lỗi minh bạch

Một record quản lý kết quả:

~~~java
package com.example.monitoring;

import java.time.Instant;

public record JmxPollResult(
        String instanceId,
        long processedCount,
        Instant sourceUpdatedAt,
        Instant heartbeatAt,
        Instant observedAt,
        String status,
        String errorCategory) {
}
~~~

Hàm diễn giải:

~~~java
public static JmxPollResult classify(
        String instanceId,
        long count,
        long sourceUpdatedMillis,
        long heartbeatMillis,
        Instant observed,
        long maxHeartbeatAgeMillis) {

    long age = observed.toEpochMilli() - heartbeatMillis;
    String status = age < 0
            ? "INVALID"
            : age <= maxHeartbeatAgeMillis ? "FRESH" : "STALE";

    return new JmxPollResult(
            instanceId,
            count,
            Instant.ofEpochMilli(sourceUpdatedMillis),
            Instant.ofEpochMilli(heartbeatMillis),
            observed,
            status,
            "");
}
~~~

Khi poll thất bại, không tái sử dụng giá trị cuối rồi gắn trạng thái FRESH. Có thể giữ last-known-good value để hiển thị nhưng phải ghi rõ observedAt cũ và trạng thái UNAVAILABLE/STALE.

Chú ý clock skew: nếu timestamp nguồn nằm ở tương lai so với client, không phải dữ liệu mới hơn thực tại. Cần đồng bộ clocks và kiểm tra epoch units.

## 17. Tự động hóa không nên coi lỗi nhất thời là lý do restart

Một monitoring agent nên phân biệt các trường hợp:

| Trạng thái | Hành động phù hợp | Hành động cần tránh |
| --- | --- | --- |
| Một lần read timeout | Ghi nhận và retry read-only với backoff | Restart JVM ngay |
| Nhiều lần poll thất bại | Alert và kiểm tra endpoint/instance | Tắt xác thực |
| Heartbeat stale nhưng connect OK | Điều tra source update và scheduling | Clear cache bừa bãi |
| Connector hỏng nhưng business healthy | Sửa connector/network, ưu tiên logs | Kết luận app chết |
| Instance ID đổi | Reset client cache và counter baseline | Gộp counters như cùng JVM |
| Operation timeout không rõ outcome | Tra cứu job status/request ID | Invoke lại vô điều kiện |
| Server mất thật | Escalate theo runbook và orchestration | Giữ connector cũ vô thời hạn |

Automation nên có rate limit, circuit breaker, cooldown và audit log. Việc thực thi thao tác sửa chữa cần có bằng chứng và giới hạn tác động phù hợp.

## 18. Kiểm thử freshness trên MBeanServer độc lập

~~~java
package com.example.jmx;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class FreshnessTest {

    @Test
    void versionIncreasesWhenSourceUpdates() throws Exception {
        MBeanServer server =
                MBeanServerFactory.createMBeanServer("isolated-freshness");
        ObjectName name = new ObjectName(
                "isolated-freshness:type=ProcessingMonitor,name=test");

        try {
            ProcessingMonitor monitor =
                    new ProcessingMonitor("test-instance");
            server.registerMBean(monitor, name);

            long before = (Long)
                    server.getAttribute(name, "SnapshotVersion");

            monitor.recordProcessed();

            long after = (Long)
                    server.getAttribute(name, "SnapshotVersion");

            assertEquals(before + 1, after);
            assertEquals("test-instance",
                    server.getAttribute(name, "InstanceId"));
        } finally {
            if (server.isRegistered(name)) {
                server.unregisterMBean(name);
            }
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
~~~

Đây là test nguồn local, chưa test connector. Mục tiêu là chứng minh metric JMX phản ánh update thực tế.

## 19. Test dữ liệu stale không dùng Thread.sleep

Hàm classify nhận clock/time point, cho phép test deterministic:

~~~java
@Test
void identifiesStaleHeartbeat() {
    Instant observed =
            Instant.parse("2026-11-11T10:00:00Z");
    long source = Instant.parse(
            "2026-11-11T09:58:00Z").toEpochMilli();

    JmxPollResult result = classify(
            "test-instance", 12L,
            source, source, observed, 45_000L);

    assertEquals("STALE", result.status());
}
~~~

Bổ sung case:
- Heartbeat đúng ngưỡng.
- Heartbeat trong tương lai.
- Không có timestamp.
- Poll lỗi kéo dài.
- InstanceId thay đổi.
- Last successful poll đã quá hạn.

Không dùng business counter không đổi làm điều kiện duy nhất để đánh dấu stale.

## 20. Remote connector integration test

Thiết kế fixture:

~~~text
Test JVM
  +-- MBeanServer riêng
  +-- ProcessingMonitor
  +-- JMXConnectorServer bind loopback
  +-- Remote client JMXConnector
~~~

Bài test cần:
1. Tạo server cô lập.
2. Đăng ký MBean fixture.
3. Start connector RMI trên địa chỉ an toàn.
4. Kết nối remote qua JMXConnectorFactory.
5. Đọc InstanceId và SnapshotVersion qua MBeanServerConnection.
6. Dừng connector để giả lập disconnect.
7. Xác minh poller trả UNAVAILABLE.
8. Dọn client, connector, MBean và server trong finally.

Không dùng production JMX URL trong integration test. RMI có thể mở cổng cho registry và remote object riêng; giới hạn loopback hoặc network fixture phù hợp.

## 21. Notification có thể bị mất và không tự replay

Nếu ứng dụng dùng JMX NotificationListener:
- Notification trong thời gian mất kết nối có thể bị bỏ lỡ.
- Sau reconnect cần đăng ký lại listener nếu session cũ không còn.
- Có thể xảy ra duplicate callback nếu client không tháo subscriptions cũ.
- Sequence number giúp nhận ra gap nhưng không tự replay missing events.
- Nên lấy một snapshot mới sau reconnect để reconcile trạng thái.

Pattern phù hợp là notification để báo thay đổi nhanh, còn polling định kỳ giúp tự sửa thiếu sót. Không xem notification như durable event log trừ khi có cơ chế lưu/replay được xây dựng riêng.

## 22. Server đã thay đổi sau deployment

Một endpoint ổn định có thể chỉ đến JVM mới:

~~~text
Before:
  endpoint: jmx-service:9010
  instanceId: pod-A/build-100
  count: 42000

After:
  endpoint: jmx-service:9010
  instanceId: pod-B/build-101
  count: 0
~~~

Đây có thể là counter reset hợp lệ do process restart, không phải dữ liệu sai. Cần dùng instance ID để xác định reset boundary và tránh tính nhầm negative delta.

Nếu ObjectName không đổi, monitoring vẫn phải đối chiếu JVM identity. Cùng một ObjectName có thể tồn tại trên nhiều JVM mà không xung đột.

## 23. Logs nên ghi những gì?

Ví dụ structured log của polling agent:

~~~text
timestamp=2026-11-11T10:00:00Z
endpoint=jmx-service:9010
objectName=com.example.jobs:type=ProcessingMonitor,name=primary
instanceId=pod-A/build-101
attribute=SnapshotVersion
value=124
observedAt=2026-11-11T10:00:00Z
durationMs=32
outcome=SUCCESS
~~~

Ví dụ lỗi:

~~~text
timestamp=2026-11-11T10:00:15Z
endpoint=jmx-service:9010
objectName=com.example.jobs:type=ProcessingMonitor,name=primary
outcome=UNAVAILABLE
errorCategory=CONNECT_TIMEOUT
lastSuccessfulPoll=2026-11-11T10:00:00Z
~~~

Không ghi credentials, keystore password, token hoặc dữ liệu nhạy cảm. Logs của exporter đăng ký/unregister, connector start/stop, Spring context refresh/close và GC rất hữu ích để ghép timeline.

## 24. Runbook chẩn đoán nhanh

### A. Không thể kết nối
1. Xác nhận client đang dùng đúng endpoint/JVM.
2. Đọc connector startup log và port listening.
3. Kiểm tra RMI registry, advertised host/port.
4. Kiểm tra network, TLS và authentication.
5. Kiểm tra GC pauses, resource pressure.
6. Chỉ retry read-only request với backoff.

### B. Kết nối được nhưng dữ liệu cũ
1. Đọc InstanceId và heartbeat timestamp.
2. So sánh MBeanServer local với remote client.
3. Kiểm tra exporter có đăng ký đúng Spring bean không.
4. Kiểm tra policy IGNORE_EXISTING hoặc owner cũ.
5. Kiểm tra dashboard cache/last-known-good.
6. Đánh dấu STALE minh bạch.

### C. Operation bị treo
1. Ghi operation name và thời điểm bắt đầu.
2. Lấy thread dump/GC/resource metrics.
3. Kiểm tra I/O timeout, locks và worker saturation.
4. Không retry operation có side effect khi outcome chưa rõ.
5. Thiết kế background job/status và deadline.

### D. Sau deploy số liệu khác
1. Kiểm tra InstanceId và build version.
2. Đối chiếu MBeanServer/connector.
3. Xác định metric counter có reset không.
4. Kiểm tra exporter registration.
5. Tạo baseline mới cho client nếu đã đổi JVM.

## 25. Bài tập thực hành

**Bài 1:** Tạo ProcessingMonitor có heartbeat riêng, giả lập không có business event và chứng minh count đứng yên không gây stale.

**Bài 2:** Tạo hai contexts dùng cùng ObjectName, context thứ hai có IGNORE_EXISTING, rồi xác định InstanceId thực sự xuất hiện qua JMX.

**Bài 3:** Xây dashboard cache giữ last-known-good value sau disconnect nhưng luôn hiển thị observedAt và trạng thái UNAVAILABLE.

**Bài 4:** Tạo connector RMI trong fixture cô lập, stop và restart connector; thử reconnect với backoff và xác minh server identity.

**Bài 5:** Giả lập JMX operation chạy quá lâu rồi ngắt chờ phía client; giải thích vì sao server-side operation có thể vẫn đang chạy.

**Bài 6:** Tạo JUnit tests cho freshness, clock skew, instance restart và counter reset.

**Bài 7:** Viết báo cáo sự cố theo cấu trúc symptom, endpoint, instanceId, ObjectName, evidence, root cause, remediation và verification.

## Kết luận

Xử lý **server không phản hồi hoặc dữ liệu cũ** trong Spring Framework JMX đòi hỏi phân biệt availability, freshness và target identity. Hãy kiểm tra cùng ObjectName trên đúng MBeanServer, đối chiếu nguồn với client và dashboard, bổ sung heartbeat cùng timestamps để đo tuổi dữ liệu, rồi dùng logs, thread dumps và connector metrics để khoanh vùng. Trong tự động hóa, đặt deadline, backoff và trạng thái STALE/UNAVAILABLE rõ ràng; không retry mù operation có side effect hay restart JVM sau một lần poll lỗi. Mỗi kết quả quan sát đáng tin cậy cần trả lời được ba câu hỏi: **đang đọc instance nào, nguồn cập nhật khi nào, và lần đọc thành công gần nhất lúc nào?**
