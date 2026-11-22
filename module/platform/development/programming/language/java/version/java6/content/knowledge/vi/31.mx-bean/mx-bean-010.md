# MXBean: Thiết kế chỉ số, thao tác quản trị và giới hạn truy cập phù hợp

## 1. Mục tiêu học tập

Một ứng dụng Java hoạt động lâu dài cần có dữ liệu quan sát về số yêu cầu, lỗi, lượng tác vụ đang xử lý, cấu hình hiện tại và một số thao tác bảo trì được kiểm soát. **JMX (Java Management Extensions)** và **MXBean** cung cấp khả năng xuất trạng thái và thao tác quản trị cho các công cụ giám sát.

Tuy nhiên, MXBean không tự tạo một hệ thống metric đầy đủ, không tự phân biệt counter với gauge, không tự bảo đảm snapshot đồng nhất và cũng không tự cấp quyền read-only cho người dùng chỉ vì tên interface có chữ Metrics. Thiết kế tốt cần kết hợp **ngữ nghĩa chỉ số**, **operation có validation** và **bảo vệ connector truy cập quản trị**.

Sau bài này, bạn sẽ:

1. Thiết kế counter, gauge, các đại lượng suy diễn, đơn vị, phạm vi, reset semantics và thời gian lấy mẫu.
2. Tạo custom MXBean interface dùng **javax.management.MXBean** và các getters/operations tối thiểu.
3. Tách giao diện metric chỉ đọc khỏi giao diện quản trị có thao tác thay đổi state.
4. Dùng **javax.management.DescriptorKey** để gắn metadata **units** và **metricType** vào MBeanAttributeInfo.
5. Hiểu vai trò của MBeanServer, ObjectName, MBeanInfo, MBeanServerConnection và Open Data.
6. Tạo immutable record Snapshot và cập nhật qua AtomicReference để cung cấp một ảnh chụp nhất quán.
7. Kiểm tra tham số operation, tránh side effects ngoài ý muốn và thiết kế idempotency, audit, rollback.
8. Phân biệt việc tách MXBean theo ObjectName với việc **thực thi authentication/authorization thực sự**.
9. Hiểu quyền readonly/readwrite của ready-to-use JMX agent và giới hạn của quyền readwrite quá rộng.
10. Biết các rủi ro JMX remote qua RMI registry, TLS, mật khẩu file dạng clear text, giới hạn mạng và credential lifecycle.
11. Dùng Java 17+ chạy một ví dụ đầy đủ với **hai MXBeans**, counter/gauge, descriptor metadata và operation hợp lệ/không hợp lệ.
12. Kiểm thử security, concurrency, schema evolution, counter reset, cardinality và resource budgets.

**Phạm vi hiện hành:** Các APIs **javax.management**, **javax.management.openmbean** và module **java.management** vẫn còn trong Java 17 và Java SE 26. Ví dụ sử dụng record và Java 17 API, đã biên dịch với **javac --release 17** và chạy trên **OpenJDK 24.0.2**. Bài không dùng các cơ chế bảo mật Java đã lỗi thời.

---

## 2. Ba câu hỏi thiết kế cốt lõi

### 2.1. Chỉ số dùng để ra quyết định gì?

Đừng xuất tất cả fields của service một cách máy móc. Trước hết xác định người vận hành cần trả lời:

- Dịch vụ có nhận và hoàn thành request hay không?
- Có bao nhiêu yêu cầu thất bại trong cửa sổ thời gian vừa qua?
- Bao nhiêu công việc đang xử lý và hàng đợi có tăng bất thường?
- Có lỗi thuộc backend dependency hay lỗi do client gửi input?
- Sau deploy hoặc restart, chỉ số reset có được phát hiện?
- Bộ thu thập metrics đọc những trường nào, với tần suất nào?

Những câu hỏi này quyết định metric name, type, scope, unit và update policy. Khi không thể giải thích chính xác ý nghĩa một metric, đừng công bố nó chỉ vì một getter đã có sẵn.

### 2.2. Operation nào thực sự cần từ xa?

Không phải hàm Java nào cũng nên trở thành management operation. Một operation có thể thay đổi cấu hình, xóa hàng đợi, giải phóng cache hoặc tạm dừng service. Mỗi operation cần rõ:

- Mục đích, tác động và giới hạn phạm vi.
- Quyền người gọi.
- Kiểu tham số và min/max.
- Kết quả trả về và error contract.
- Có thể gọi lặp lại an toàn không.
- Có cần audit, phê duyệt hoặc rollback không.
- Có thể chạy lâu hay phải tách thành job không.
- Tác động khi nhiều operators cùng gọi hoặc network bị ngắt.

### 2.3. Ai được quyền đọc và ai được quyền sửa?

Một caller có reference tới **MBeanServerConnection toàn quyền** có thể gọi các operations được expose, dù interface đó mang tên Admin hay Metrics. Việc đặt hai ObjectNames riêng chỉ tổ chức API, không tạo ACL. Quyền phải được thực thi tại JMX connector/server access boundary, kèm authentication và network security.

~~~text
                Ứng dụng Java
                      │
               Application state
                      │
             ┌────────┴────────┐
             ▼                 ▼
      Metrics MXBean       Admin MXBean
      (getters only)       (operations)
             └────────┬────────┘
                      ▼
                  MBeanServer
                      │
             Connector/Policy Layer
             TLS + Authentication
             Authorization + Audit
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
      Observer               Operator
      Đọc metrics           Chỉ thao tác
      không mutate          được cấp quyền
~~~

Sơ đồ thể hiện **chính sách cần thiết kế và kiểm thử**, không phải những quyền mà bản thân MXBean tự động cung cấp.

---

## 3. Metric contract: counter, gauge và thống kê

### 3.1. Counter: giá trị tích lũy

Counter là một đại lượng tích lũy không giảm trong một vòng đời process/metric epoch, trừ trường hợp reset đã được định nghĩa rõ.

~~~text
RequestsTotal        = 10234
FailuresTotal        =   128
JobsProcessedTotal   =  5520
BytesSentTotal       = 89102
~~~

**RequestsTotal** cần ghi rõ đếm request *bắt đầu*, *được chấp nhận* hay *đã hoàn thành*. **FailuresTotal** phải định nghĩa một request retry có được đếm thêm hay không, và lỗi do server với lỗi của client có tách nhau không.

~~~java
// MẢNH MINH HỌA management interface.
long getRequestsTotal();
long getFailuresTotal();
~~~

Nếu metric giảm đột ngột sau restart, hệ thống monitoring cần phát hiện counter reset để không tính rate âm. Nếu ứng dụng cho phép reset thủ công, tốt hơn là có metric window riêng thay vì phá contract của Total.

### 3.2. Gauge: giá trị trạng thái hiện tại

Gauge có thể tăng hoặc giảm:

~~~text
InFlightRequests = 3
QueueDepth       = 42
ActiveWorkers    = 8
CacheEntries     = 120
~~~

Ví dụ:

~~~java
// MẢNH MINH HỌA.
int getInFlight();
int getQueueDepth();
~~~

Khi một request bắt đầu, InFlightRequests tăng. Khi request kết thúc, gauge giảm. Không dùng giá trị gauge cuối cùng để suy ra lượng request đã xử lý từ khi startup.

### 3.3. Rate và tỷ lệ lỗi không đồng nhất với total

Nếu monitoring thu hai mẫu cách nhau 30 giây:

~~~text
T0: RequestsTotal=1000, FailuresTotal=40
T1: RequestsTotal=1120, FailuresTotal=46

requestsPerSecond = (1120 - 1000) / 30 = 4
errorRatio         = (46 - 40) / (1120 - 1000) = 0.05
~~~

Đây là ví dụ số học minh họa, không phải số liệu thật. **ErrorRatio 5% của 30 giây vừa qua** khác với chia toàn bộ FailuresTotal cho RequestsTotal của cả đời process.

Khi mẫu số bằng 0, lựa chọn biểu diễn **N/A** hoặc một giá trị thiếu có contract rõ. Đừng tự báo 0% lỗi như thể đã quan sát một lượng traffic có ý nghĩa.

### 3.4. Percentile latency và histogram

P95 latency của một cửa sổ là phân vị 95 của các samples thuộc cửa sổ đó. Nó không được tính từ một average đơn lẻ. Nếu expose p95 qua MXBean:

- Chỉ định rõ thời gian cửa sổ.
- Cho biết đơn vị: milliseconds hay microseconds.
- Xác định missing/low-volume behavior.
- Dùng bounded histogram/sketch được kiểm thử.
- Không giữ danh sách không giới hạn mọi request để sort mỗi lần getter chạy.
- Có policy cho process restart và sample rollover.

Với hệ thống đo latency phức tạp, OpenTelemetry/Micrometer/Prometheus exporter có thể phù hợp hơn. MXBean vẫn hữu ích để xuất một giá trị tổng hợp có giới hạn.

### 3.5. Unit, scope, cadence và freshness

| Chỉ số | Java type | Unit | Scope | Hành vi |
| --- | --- | --- | --- | --- |
| RequestsTotal | long | requests | process instance | counter |
| FailuresTotal | long | requests | process instance | counter |
| InFlight | int | requests | process instance | gauge |
| QueueDepth | int | items | queue instance | gauge |
| BytesProcessedTotal | long | bytes | instance | counter |
| SampleAgeMillis | long | milliseconds | last snapshot | gauge |
| WindowSeconds | int | seconds | configuration | setting |
| P95LatencyMillis | double | milliseconds | sample window | derived |

**WindowSeconds là cấu hình**, không phải số liệu đo traffic. Không gắn nhãn counter cho mọi con số.

Metadata nên ghi tên, đơn vị, scope, thời điểm cập nhật, khả năng reset và ý nghĩa null/NaN. Một metric được cache cách đây 10 phút không nên được hiển thị như thể vừa đo ngay lúc client đọc.

### 3.6. Kích thước và cardinality

Các attributes và ObjectNames quá nhiều có thể gây overhead CPU/GC, bộ nhớ và tải collector. **Không tạo một MBean hoặc metric riêng cho từng user, request, transaction, session hay IP ngẫu nhiên.**

~~~text
Phù hợp:
demo.metrics:type=Requests,name=primary

Không phù hợp:
demo.metrics:type=Request,userId=<một-id-riêng-cho-mỗi-người>
~~~

Thiết lập giới hạn cho số beans, số phần tử Map/List, chiều dài String, độ sâu CompositeData, số labels và tần suất polling. Tránh đưa PII vào ObjectName.

---

## 4. MXBean API và ranh giới trách nhiệm

### 4.1. Interface quan sát chỉ chứa getters

~~~java
// MẢNH MINH HỌA.
@MXBean
public interface RequestMetrics {
    long getRequestsTotal();
    long getFailuresTotal();
    int getInFlight();
    Snapshot getSnapshot();
}
~~~

**getRequestsTotal** trở thành JMX attribute **RequestsTotal**. **getSnapshot** trở thành attribute **Snapshot**. Interface chỉ có getters nên không khai báo custom management operation hay writable attribute.

Nhưng một getter vẫn chạy code application. Nếu getter query database, đợi lock hoặc tạo Map hàng triệu entries thì monitoring có thể làm giảm chất lượng dịch vụ. Hãy giữ getter nhẹ, side-effect-free và có kích thước kết quả được giới hạn.

### 4.2. Interface thao tác quản trị

~~~java
// MẢNH MINH HỌA.
@MXBean
public interface WindowControl {
    int getWindowSeconds();
    void changeWindowSeconds(int seconds);
}
~~~

Đây là hai thành phần:

- **WindowSeconds**: read-only attribute cho cấu hình hiện tại.
- **changeWindowSeconds(int)**: operation có side effect, chỉ nên chạy khi caller đã được cấp quyền tại connector boundary và tham số hợp lệ.

Một setter kiểu **setWindowSeconds** sẽ khiến **WindowSeconds** có thể trở thành writable attribute. Đó vẫn là API hợp lệ, nhưng phải bảo vệ thao tác ghi tương đương với một operation quản trị.

### 4.3. Không đưa mọi hành vi service vào JMX

Không expose operations mơ hồ như:

~~~java
// PHẢN VÍ DỤ: API nguy hiểm, không nên triển khai.
void executeCommand(String command);
void writeAnyProperty(String key, Object value);
void deleteAllData();
~~~

Những methods này mở rộng attack surface, khó audit, khó kiểm tra giới hạn và có nguy cơ tạo một remote code execution/data-destruction surface.

Chỉ công bố operations cụ thể như **changeWindowSeconds**, **requestGracefulDrain** hoặc **reloadValidatedConfig**, với validation, authorization, audit và rollback plan.

### 4.4. Tách hai ObjectNames nhưng không tự có ACL

~~~text
demo.metrics:type=Requests,name=primary
demo.admin:type=Window,name=primary
~~~

Sự phân tách giúp client dễ tìm đúng bean, kiểm thử interface, giảm nguy cơ một monitoring bean vô tình có operation thay đổi state. Nhưng **caller có MBeanServerConnection toàn quyền vẫn có thể invoke cả admin bean**.

Một policy read-only cần được thực thi và test bằng **connector/server authorization**, không chỉ bằng class name hoặc UI ẩn nút.

### 4.5. Open Data và generic client

MXBean dùng quy tắc mapping để dữ liệu có thể được đọc qua JMX Open Types chuẩn:

| Server-side type | Raw JMX value |
| --- | --- |
| long / int | Long / Integer |
| String | String |
| enum | String |
| List of String | String[] |
| Map với kiểu hợp lệ | TabularData |
| record phù hợp | CompositeData |

Client dùng **MBeanServerConnection.getAttribute(name,"Snapshot")** sẽ nhận **CompositeData**, không cần có class record của service.

**Không phụ thuộc model class** khác với **không cần schema**: client vẫn cần biết item names, units và semantics. Việc đổi field name/type có thể phá dashboard.

---

## 5. Descriptor metadata: units và metricType

JMX định nghĩa **DescriptorKey** để gắn fields từ annotation lên MBean descriptors. Hai trường hữu ích cho metric là **units** và **metricType**, với metricType thường là **counter** hoặc **gauge**.

### 5.1. Định nghĩa annotation

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import javax.management.DescriptorKey;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface Metric {
    @DescriptorKey("units") String units();
    @DescriptorKey("metricType") String kind();
}
~~~

Annotation này được gắn vào getter của management interface:

~~~java
@Metric(units="requests",kind="counter")
long getRequestsTotal();

@Metric(units="requests",kind="gauge")
int getInFlight();
~~~

**JMX metadata không tự enforce metric semantics.** Nếu application decrement RequestsTotal, không có cơ chế mặc định trong DescriptorKey tự ngăn điều đó. Tests và implementation vẫn phải bảo đảm correctness.

### 5.2. Đọc metadata

~~~java
// MẢNH MINH HỌA: monitoring/name đã được định nghĩa.
MBeanInfo info = monitoring.getMBeanInfo(metricsName);
MBeanAttributeInfo counter = Arrays.stream(info.getAttributes())
        .filter(a -> a.getName().equals("RequestsTotal"))
        .findFirst().orElseThrow();

Object units = counter.getDescriptor().getFieldValue("units");
Object kind = counter.getDescriptor().getFieldValue("metricType");
~~~

Ví dụ runnable đã kiểm chứng:

~~~text
counterUnits=requests
counterKind=counter
~~~

Dù chuẩn Descriptor có field conventions, không phải mọi dashboard/collector tự hiểu custom metadata. Cần thêm tài liệu contract, integration test và conventions đồng nhất.

### 5.3. Không nhầm OpenType metadata với quyền caller

**MBeanInfo** cho biết attribute/operation nào được công bố và kiểu gì. **MBeanAttributeInfo.isWritable** mô tả writable capability; **MBeanOperationInfo.getImpact** là thông tin mô tả tác động. Chúng **không phải một ACL** và không chứng minh một principal cụ thể được phép ghi/gọi.

---

## 6. Immutable snapshot và consistency

### 6.1. Vấn đề của nhiều counters độc lập

Nếu requestsTotal và failuresTotal được cập nhật gần nhau nhưng không cùng boundary, một collector có thể đọc hai values từ hai thời điểm khác nhau:

~~~text
T0: RequestsTotal=10
T1: Request lỗi được ghi nhận
T2: FailuresTotal=3
~~~

Đọc hai attributes riêng rẽ không tự tạo một transaction. Ngay cả hai AtomicLong riêng vẫn không nhất thiết cho một multi-field snapshot nhất quán.

### 6.2. Dùng record + AtomicReference

~~~java
public record Snapshot(
        long requestsTotal,
        long failuresTotal,
        int inFlight,
        int windowSeconds) {}

private final AtomicReference<Snapshot> current =
        new AtomicReference<>(new Snapshot(10, 2, 3, 60));
~~~

Một getter chỉ trả object hiện tại:

~~~java
public Snapshot getSnapshot() {
    return current.get();
}
~~~

Mỗi update tạo một record mới và publish qua AtomicReference, nên **một lần lấy Snapshot** sẽ nhìn thấy bốn fields thuộc cùng immutable state.

### 6.3. Cập nhật nguyên tử mà không gây side effects trong CAS lambda

~~~java
// MẢNH MINH HỌA:
current.updateAndGet(s -> new Snapshot(
        s.requestsTotal() + 1,
        s.failuresTotal(),
        s.inFlight(),
        s.windowSeconds()));
~~~

**AtomicReference.updateAndGet có thể gọi update function nhiều lần khi CAS contention.** Vì vậy lambda phải là phép tính thuần, không gửi event/network request, không ghi log quan trọng hoặc thực hiện transaction trong lambda. Side effects cần được thực hiện ở boundary nghiệp vụ có idempotency phù hợp.

### 6.4. Invariants cơ bản

~~~text
requestsTotal >= 0
failuresTotal >= 0
failuresTotal <= requestsTotal
inFlight >= 0
10 <= windowSeconds <= 3600
~~~

Đây là invariants ví dụ của ứng dụng, **không phải ràng buộc JMX**.

Demo bắt đầu với requestsTotal=10, failuresTotal=2, inFlight=3. Sau startRequest, InFlight thành 4. Sau completeRequest(true), RequestsTotal thành 11, FailuresTotal thành 3 và InFlight về 3.

### 6.5. Giới hạn snapshot logic

Immutable record không tự làm dữ liệu từ nhiều database/threads thành nhất quán. Nếu một field đọc từ DB và field khác đọc từ service khác mà không có coordination, tạo record sau đó vẫn chứa hai mẫu từ hai thời điểm.

Khi snapshot đòi hỏi consistency chặt chẽ, phải có atomic publication, transaction, lock hoặc một snapshot mechanism thực. Nếu chỉ là approximate metrics, mô tả rõ tính chất eventually consistent.

### 6.6. Không dựa vào nhiều getAttribute để có atomic read

Một generic client có thể đọc:

~~~java
CompositeData data = (CompositeData)
        monitoring.getAttribute(metricsName, "Snapshot");

long total = (Long) data.get("requestsTotal");
long failures = (Long) data.get("failuresTotal");
~~~

Đây là một lần đọc getter Snapshot. Hai lời gọi getAttribute khác nhau có thể lệch nhau do concurrent state updates; **getAttributes bulk cũng không được hiểu là transaction tổng quát**.

---

## 7. Thiết kế management operations an toàn

### 7.1. Operation thay cấu hình có bounded input

Operation minh họa:

~~~java
public void changeWindow(int seconds) {
    if (seconds < 10 || seconds > 3600) {
        throw new IllegalArgumentException(
                "windowSeconds must be 10..3600");
    }
    current.updateAndGet(s -> new Snapshot(
            s.requestsTotal(), s.failuresTotal(),
            s.inFlight(), seconds));
}
~~~

Điểm cần nhớ: **đã có quyền admin không có nghĩa input được bỏ qua validation**. Một giá trị âm hoặc cực lớn có thể làm hỏng sampling, tăng memory, kéo dài timeout hoặc phá SLA.

### 7.2. Các lớp validation

| Kiểm tra | Mục đích |
| --- | --- |
| Type và encoding | Không nhận dữ liệu sai kiểu |
| Min/max | Chống giá trị không thực tế |
| Business precondition | Không đổi config ở trạng thái không cho phép |
| Caller authorization | Chỉ người có quyền được invoke |
| Rate/concurrency limit | Chống spam operations |
| Time budget | Không block vô thời hạn |
| Idempotency | Gọi lặp an toàn khi client retry |
| Audit | Điều tra khi config thay đổi |
| Rollback | Khôi phục sau operation thất bại |

**Validation trong operation không thay authorization ở connector.** Connector authorization không thay bounds validation trong implementation.

### 7.3. Operation result, retry và exception

Một raw caller có thể gọi:

~~~java
monitoring.invoke(
        adminName,
        "changeWindowSeconds",
        new Object[]{120},
        new String[]{"int"});
~~~

JMX operation signature dùng Java method signature, nên parameter **int** có signature là **"int"**, không phải **"java.lang.Integer"**.

Nếu implementation ném IllegalArgumentException, lời gọi local MBeanServer có thể bọc thành **RuntimeMBeanException**. Với remote connector còn có lỗi transport/auth/authorization riêng. Khi network timeout sau một operation có side effect, client không được mặc định server chưa thực hiện operation; cần idempotency và readback trạng thái sau timeout.

### 7.4. Chọn set-to-value dễ an toàn hơn increment

Operation **changeWindowSeconds(120)** mô tả target state. Nếu gọi hai lần, cuối cùng vẫn là 120 trong demo. Một operation như **increaseLimitBy(100)** không idempotent nếu retry hai lần.

Tuy nhiên, ngay cả set-to-value cũng có thể gây side effects phụ (reload, reallocation, notification), cần xác định rõ hành vi khi gọi lặp. Nếu operation có chi phí lớn, cân nhắc request ID, duplicate suppression hoặc async job model.

### 7.5. Operation chạy lâu

Không nên đặt xóa hàng triệu items hoặc rebuild database trong một JMX invocation synchronous không có time budget.

Một thiết kế thay thế:

~~~text
invoke(startRebuild) -> jobId
getJobStatus(jobId)  -> bounded status
invoke(cancelJob)    -> cancellation request
~~~

Cần bảo đảm jobId không lộ thông tin nhạy cảm, có quyền truy cập phù hợp và không để stale jobs tích lũy không giới hạn. Nếu chuyển operation sang thread khác, đừng đánh mất context authorization/audit.

---

## 8. Ví dụ Java 17+ đầy đủ: Metrics MXBean và Admin MXBean

**File:** MxBeanMetricsAndAdminDemo.java

Ví dụ gồm hai public interfaces đánh dấu **@MXBean**:

- **RequestMetrics**: RequestsTotal/FailuresTotal dạng counter, InFlight dạng gauge, Snapshot dạng record.
- **WindowControl**: getter cấu hình và một operation **changeWindowSeconds**.

Một State chung sử dụng **AtomicReference<Snapshot>**. Metadata metricType và units được gắn qua custom annotation. MBeanServer cục bộ được tạo bằng **MBeanServerFactory.newMBeanServer("example")** để thử nghiệm không cần remote port, database hay JMX connector.

### 8.1. Toàn bộ source

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicReference;
import javax.management.DescriptorKey;
import javax.management.JMX;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.MBeanServerConnection;
import javax.management.MBeanServerFactory;
import javax.management.MXBean;
import javax.management.ObjectName;
import javax.management.RuntimeMBeanException;
import javax.management.openmbean.CompositeData;

public final class MxBeanMetricsAndAdminDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    public @interface Metric {
        @DescriptorKey("units") String units();
        @DescriptorKey("metricType") String kind();
    }

    // Immutable point-in-time management snapshot, no secrets/PII.
    public record Snapshot(long requestsTotal, long failuresTotal,
                           int inFlight, int windowSeconds) {}

    public static final class State {
        private final AtomicReference<Snapshot> current =
                new AtomicReference<>(new Snapshot(10, 2, 3, 60));
        public Snapshot snapshot() { return current.get(); }

        public void startRequest() {
            current.updateAndGet(s -> new Snapshot(
                    s.requestsTotal(), s.failuresTotal(),
                    s.inFlight() + 1, s.windowSeconds()));
        }

        public void completeRequest(boolean failed) {
            current.updateAndGet(s -> {
                if (s.inFlight() <= 0) {
                    throw new IllegalStateException("no request in flight");
                }
                return new Snapshot(
                        s.requestsTotal() + 1,
                        s.failuresTotal() + (failed ? 1 : 0),
                        s.inFlight() - 1, s.windowSeconds());
            });
        }

        public void changeWindow(int seconds) {
            if (seconds < 10 || seconds > 3600) {
                throw new IllegalArgumentException("windowSeconds must be 10..3600");
            }
            current.updateAndGet(s -> new Snapshot(s.requestsTotal(),
                    s.failuresTotal(), s.inFlight(), seconds));
        }
    }

    @MXBean
    public interface RequestMetrics {
        @Metric(units="requests",kind="counter")
        long getRequestsTotal();

        @Metric(units="requests",kind="counter")
        long getFailuresTotal();

        @Metric(units="requests",kind="gauge")
        int getInFlight();

        Snapshot getSnapshot();
    }

    public static final class Metrics implements RequestMetrics {
        private final State state;
        public Metrics(State state) { this.state = state; }
        public long getRequestsTotal() { return state.snapshot().requestsTotal(); }
        public long getFailuresTotal() { return state.snapshot().failuresTotal(); }
        public int getInFlight() { return state.snapshot().inFlight(); }
        public Snapshot getSnapshot() { return state.snapshot(); }
    }

    @MXBean
    public interface WindowControl {
        int getWindowSeconds();
        void changeWindowSeconds(int seconds);
    }

    public static final class Admin implements WindowControl {
        private final State state;
        public Admin(State state) { this.state = state; }
        public int getWindowSeconds() { return state.snapshot().windowSeconds(); }
        public void changeWindowSeconds(int seconds) { state.changeWindow(seconds); }
    }

    public static void main(String[] args) throws Exception {
        MBeanServer server = MBeanServerFactory.newMBeanServer("example");
        ObjectName metricsName = new ObjectName("demo.metrics:type=Requests,name=primary");
        ObjectName adminName = new ObjectName("demo.admin:type=Window,name=primary");
        State state = new State();

        server.registerMBean(new Metrics(state), metricsName);
        server.registerMBean(new Admin(state), adminName);
        try {
            MBeanServerConnection monitoring = server;
            System.out.println("metricsRegistered=" + server.isRegistered(metricsName));
            System.out.println("adminRegistered=" + server.isRegistered(adminName));
            MBeanInfo metricsInfo = monitoring.getMBeanInfo(metricsName);
            System.out.println("metricsOperations=" + metricsInfo.getOperations().length);
            MBeanAttributeInfo requestCounter = Arrays.stream(
                    metricsInfo.getAttributes())
                    .filter(a -> a.getName().equals("RequestsTotal"))
                    .findFirst().orElseThrow();
            System.out.println("counterUnits="
                    + requestCounter.getDescriptor().getFieldValue("units"));
            System.out.println("counterKind="
                    + requestCounter.getDescriptor().getFieldValue("metricType"));

            CompositeData before=(CompositeData)monitoring.getAttribute(
                    metricsName,"Snapshot");
            System.out.println("before=requests:"+before.get("requestsTotal")
                    +",failed:"+before.get("failuresTotal")
                    +",active:"+before.get("inFlight")
                    +",window:"+before.get("windowSeconds"));
            state.startRequest();
            CompositeData active=(CompositeData)monitoring.getAttribute(
                    metricsName,"Snapshot");
            System.out.println("duringActive="+active.get("inFlight"));
            state.completeRequest(true);
            CompositeData after=(CompositeData)monitoring.getAttribute(
                    metricsName,"Snapshot");
            System.out.println("after=requests:"+after.get("requestsTotal")
                    +",failed:"+after.get("failuresTotal")
                    +",active:"+after.get("inFlight"));

            long failures=(Long)monitoring.getAttribute(
                    metricsName,"FailuresTotal");
            System.out.println("failuresRead="+failures);
            MBeanInfo adminInfo=monitoring.getMBeanInfo(adminName);
            System.out.println("adminOperations="+adminInfo.getOperations().length);

            try {
                monitoring.invoke(adminName,"changeWindowSeconds",
                        new Object[]{0},new String[]{"int"});
                System.out.println("invalidRejected=false");
            } catch(RuntimeMBeanException e) {
                System.out.println("invalidRejected="
                    +(e.getCause() instanceof IllegalArgumentException));
            }
            System.out.println("windowAfterInvalid="+
                    monitoring.getAttribute(adminName,"WindowSeconds"));

            monitoring.invoke(adminName,"changeWindowSeconds",
                    new Object[]{120},new String[]{"int"});
            System.out.println("windowAfterValid="+
                    monitoring.getAttribute(adminName,"WindowSeconds"));
            CompositeData finalSnapshot=(CompositeData)monitoring.getAttribute(
                    metricsName,"Snapshot");
            System.out.println("snapshotWindow="+finalSnapshot.get("windowSeconds"));
            System.out.println("remoteConnectorOpened=false");
        } finally {
            server.unregisterMBean(adminName);
            server.unregisterMBean(metricsName);
        }
        System.out.println("unregistered="+
                (!server.isRegistered(metricsName) && !server.isRegistered(adminName)));
    }
}
~~~

### 8.2. Cách biên dịch và chạy

Dùng JDK 17 trở lên. Lưu source đúng tên **MxBeanMetricsAndAdminDemo.java** trong một thư mục trống và chạy:

~~~bash
javac -encoding UTF-8 --release 17 MxBeanMetricsAndAdminDemo.java
java MxBeanMetricsAndAdminDemo
~~~

JMX API thuộc **module java.management**, có trong JDK; ví dụ chạy theo classpath không cần thêm thư viện Maven/Gradle. Với JPMS, module ứng dụng cần khai báo:

~~~java
// MẢNH MINH HỌA module-info.java cho project modular.
module com.example.management {
    requires java.management;
}
~~~

**Ví dụ này không mở JMX remote connector**, nên không cần cấu hình TLS/password/port; nó cũng **không thực hiện kiểm thử quyền JMX của các principal**. Local MBeanServer cho phép kiểm tra chính xác behavior MXBean mapping/validation mà không tăng attack surface.

### 8.3. Kết quả stdout đã kiểm chứng

~~~text
metricsRegistered=true
adminRegistered=true
metricsOperations=0
counterUnits=requests
counterKind=counter
before=requests:10,failed:2,active:3,window:60
duringActive=4
after=requests:11,failed:3,active:3
failuresRead=3
adminOperations=1
invalidRejected=true
windowAfterInvalid=60
windowAfterValid=120
snapshotWindow=120
remoteConnectorOpened=false
unregistered=true
~~~

**Đã biên dịch bằng javac 24.0.2 với --release 17, chạy trên OpenJDK 24.0.2 và đối chiếu chính xác 16 dòng kết quả.** Không cần HTTP server, database, remote JMX hay dependency bên ngoài. Files thử nghiệm tạm thời đã được dọn.

### 8.4. Phân tích kết quả chi tiết

**Đăng ký và metadata:**
- metricsRegistered/adminRegistered true: hai ObjectNames có tồn tại.
- metricsOperations=0: Metrics MXBean chỉ có getters.
- counterUnits=requests: DescriptorKey units được JMX phản ánh.
- counterKind=counter: DescriptorKey metricType được phản ánh.

**Counters và gauge:**
- Trước mô phỏng, tổng requests 10, failed 2, inFlight 3.
- Khi startRequest, inFlight=4, counters chưa tăng.
- Khi completeRequest(true), total=11, failed=3, inFlight=3.
- Raw JMX getAttribute FailuresTotal trả Long bằng 3.

**Operation và validation:**
- adminOperations=1: có operation changeWindowSeconds.
- changeWindowSeconds(0) bị reject, cause là IllegalArgumentException, window vẫn bằng 60.
- changeWindowSeconds(120) thành công; cả getter của admin bean và metrics snapshot đều thấy 120.

**Lifecycle:**
- remoteConnectorOpened=false: không mở remote port.
- unregistered=true: cuối chương trình đã unregister hai beans.

### 8.5. Phân biệt điều ví dụ chứng minh và điều chưa chứng minh

| Điều đã kiểm chứng | Điều chưa kiểm chứng |
| --- | --- |
| Hai MXBeans đăng ký đúng | Remote TLS/auth được cấu hình |
| Metadata counter/gauge/units có mặt | Collector tự diễn giải metadata đúng |
| Immutable Snapshot có bốn fields | Tính nhất quán của mọi external data source |
| Valid/invalid admin parameter | Một observer role bị từ chối invoke |
| MBeanInfo liệt kê số operations đúng | ACL theo từng ObjectName |
| Local MBeanServer cleanup | RMI registry đã được bảo vệ |
| Biên dịch Java 17-compatible | Load test/concurrency production |

Một bài test local là bước đầu để xác nhận API và dữ liệu. **Không dùng kết quả local để tuyên bố hệ thống remote JMX đã an toàn.**

### 8.6. Những chi tiết cần cải thiện cho production

- Source demo đăng ký bean metrics trước bean admin, rồi mới vào try/finally. Nếu đăng ký bean admin lỗi, metrics bean có thể chưa được unregister; production nên có startup rollback cho **partial registration failures**.
- Counter long có thể overflow nếu dùng rất lâu với tốc độ cực cao; có policy/monitoring theo epoch.
- Một instance reset counters sau restart; expose process start time cho collector.
- Getter chỉ tính toán trong memory; thực tế có thể cần bounded cache và sample timestamp.
- Operation thay cấu hình theo AtomicReference nhưng chưa có audit principal, because không có remote auth context.
- Không có separate admin role thật trong source; phải triển khai ở connector/server boundary.
- Không có rate limiting; cần budget cho môi trường nhiều collectors.

---

## 9. Giới hạn truy cập JMX: ba tầng bảo vệ

### 9.1. Network và transport

JMX remote qua RMI có thể đưa bề mặt quản trị của JVM ra mạng. Khi mở remote connector, phải giới hạn:

- Mạng private/quản trị được phép.
- Firewall ingress/egress.
- TLS encryption và server identity verification.
- Client authentication/certificates khi phù hợp.
- RMI registry và connector endpoint; không chỉ một port.
- Credential rotation, revocation và expiration.
- Giới hạn số kết nối và timeouts.
- Không public JMX endpoint ra Internet.

**Không đặt cấu hình tắt authentication hoặc TLS trên production** chỉ vì công cụ JConsole kết nối khó.

### 9.2. Authentication và Authorization

Ready-to-use JMX management agent có chính sách cơ bản dựa trên authentication và role access file. Theo Oracle Java SE 26 Monitoring and Management Guide, các mức thường gặp:

| Role/access | Hành vi cơ bản |
| --- | --- |
| readonly | Đọc MBean attributes, nghe notifications; không được mutate |
| readwrite | Đọc/ghi attributes và invoke operations, trong phạm vi policy tương ứng |

Đây là một mô hình quyền cơ bản. **readwrite có thể rộng hơn nhu cầu của một operator chỉ cần đổi WindowSeconds**, nên phải đánh giá cơ chế fine-grained authorization nếu có yêu cầu quyền tối thiểu.

Một connector custom có thể dùng **MBeanServerForwarder** hoặc lớp ủy quyền tương đương để kiểm soát ObjectName, operation và principal; việc triển khai phải kiểm tra mọi đường thao tác, không chỉ invoke mà cả setAttribute, register/unregister.

### 9.3. File password và cảnh báo hiện hành

Oracle Java SE 26 ghi rõ **file-based password authentication của ready-to-use JMX agent lưu password dạng clear text và được xem là chỉ phù hợp development**. Với production, cân nhắc secure login configuration, certificate-based client authentication hoặc hạ tầng identity được thiết kế an toàn.

Ngoài ra, tài liệu cảnh báo nguy cơ khi client lấy remote connector stub từ **RMI registry không an toàn**, kể cả khi một phần kết nối bật TLS. Đừng coi mỗi thiết lập ssl=true là đủ bảo vệ mọi endpoint. Bảo vệ registry, connector, credentials và network boundary đầy đủ.

### 9.4. Fine-grained policy mong muốn

~~~text
Observer:
  ALLOW getAttribute(metricsName, RequestsTotal)
  ALLOW getAttribute(metricsName, Snapshot)
  DENY invoke(adminName, changeWindowSeconds)
  DENY setAttribute
  DENY registerMBean, unregisterMBean

Window operator:
  ALLOW read metrics
  ALLOW invoke(adminName, changeWindowSeconds)
  DENY unrelated/destructive operations

Platform administrator:
  broader access with approved authentication, audit, TLS
~~~

Sơ đồ này là **policy cần cấu hình và test**, không phải điều tự diễn ra vì tên domain có chữ metrics/admin. Nếu quyền readwrite của connector áp dụng quá rộng, lựa chọn an toàn có thể là **không expose operation nguy hiểm** qua JMX.

### 9.5. Ba loại kiểm tra không thay thế nhau

1. **Transport security**: người ngoài không thể nghe lén/giả mạo kết nối.
2. **Authorization**: caller được phép đọc/gọi đúng những thao tác nào.
3. **Business validation**: dù caller hợp lệ, operation vẫn từ chối input nguy hiểm hoặc sai range.

Một connector có TLS nhưng cho readwrite mọi operation vẫn có rủi ro; một operation validation tốt nhưng không auth vẫn có rủi ro; một role readonly không loại bỏ nhu cầu redaction nếu attributes chứa secret.

### 9.6. Operation impact metadata không phải ACL

**MBeanOperationInfo.getImpact()** có thể là ACTION, INFO, ACTION_INFO hoặc UNKNOWN. Đây là metadata, **không tự thực thi quyền**. Tương tự, việc getOperations() thấy một operation tồn tại không có nghĩa client có quyền invoke nó.

---

## 10. Thiết kế và giới hạn thao tác quản trị

### 10.1. Giới hạn tham số

Với changeWindowSeconds, demo nhận 10–3600. Production nên test ít nhất:

| Input | Expected |
| --- | --- |
| -1 | Reject |
| 0 | Reject |
| 9 | Reject |
| 10 | Accept |
| 60 | Accept |
| 120 | Accept |
| 3600 | Accept |
| 3601 | Reject |
| Wrong Java signature | JMX lookup/ReflectionException |
| Unauthenticated/unauthorized | Deny trước implementation |
| Repeated 120 | Target state remains 120 |

Chương trình chính đã thực sự kiểm tra 0 và 120. Những inputs khác là **danh sách QA cần bổ sung**, không được gọi là đã chạy.

### 10.2. Idempotency và timeout

Một operation thay config theo target value thường an toàn hơn operation tăng/giảm tương đối. Nếu remote JMX timeout, client không thể suy rằng operation chưa chạy; phải đọc lại state, xác định retry semantics, tránh thay đổi lặp.

Nếu operation có side effects phức tạp, cân nhắc requestId/idempotency key, một job status hoặc approval workflow thay vì gọi đồng bộ.

### 10.3. Audit cho admin calls

Một audit event có thể có:

~~~text
event=jmx_operation
principal=window-operator
objectName=demo.admin:type=Window,name=primary
operation=changeWindowSeconds
requestedWindowSeconds=120
result=success
durationMs=...
correlationId=...
~~~

Đây là ví dụ định dạng, **không phải output của chương trình**. Không ghi raw password, session tokens, PII hoặc arbitrary body values. Với thao tác bị từ chối, cũng cần audit điều kiện và caller identity nếu đã xác minh.

### 10.4. Read-only monitoring không đồng nghĩa dữ liệu được công khai

Ngay cả metrics getter cũng có thể rò:

- Token/credential nếu expose nhầm.
- Hostname, internal topology, socket addresses nhạy cảm.
- User IDs trong ObjectName/Map keys.
- Business secrets qua error message.
- Transaction details nếu lộ ở Snapshot.

Chỉ export aggregate values đã được duyệt, kiểm soát retention của logs và cân nhắc query allowlist/size limits.

### 10.5. Rate limiting cho monitoring và admin

Mỗi lời gọi getAttribute có thể chạy code application. Dù readonly, một caller polling liên tục vẫn có thể gây CPU/GC pressure. Giới hạn access/collector frequency, getter latency, map size và số concurrent connections.

Đối với admin operation, cần thêm operation-specific concurrency policy, chẳng hạn chỉ cho một reconfiguration đang chạy, có cancellation/rollback và timeout.

---

## 11. Kiểm thử metrics và schema

### 11.1. Metric semantics unit tests

| Case | Expected |
| --- | --- |
| Initial state | requests=10, failed=2, active=3 |
| startRequest | active=4, counters unchanged |
| completeRequest(true) | requests=11, failed=3, active=3 |
| completeRequest(false) | requests tăng, failures giữ nguyên |
| No active request to complete | Fail, không giảm active âm |
| Concurrent updates | Không mất increment |
| Atomic snapshot read | Invariants trên một record giữ đúng |
| Process reset | Collector nhận diện epoch thay đổi |
| Counter overflow | Policy rõ, không âm bất ngờ |
| GetSnapshot under load | Latency/size nằm trong budget |

Không nên viết tests phụ thuộc vào lịch chạy thread không xác định. Với concurrency tests, dùng CountDownLatch và assert tổng số increments, không dựa vào order log.

### 11.2. Metadata tests

- Kiểm tra RequestMetrics đã được MXBean introspection nhận diện.
- Kiểm tra **RequestsTotal** là read-only attribute.
- Kiểm tra **metricsOperations=0** theo fixture.
- Kiểm tra descriptor fields **units=requests**, **metricType=counter**.
- Kiểm tra **InFlight** có kind=gauge.
- Kiểm tra Snapshot được trả là **CompositeData** với bốn items.
- Kiểm tra không có secret-bearing attribute.
- Kiểm tra attribute names/types/units giữ tương thích khi đổi phiên bản.

### 11.3. Operation tests

- Gọi invalid input: ném exception và state unchanged.
- Gọi valid input: state được cập nhật.
- Gọi lại cùng target: final state giữ nguyên.
- Gọi sai method name hoặc signature: lỗi có ngữ nghĩa rõ.
- Gọi sau unregister: **InstanceNotFoundException**.
- Đăng ký trùng ObjectName: **InstanceAlreadyExistsException**.
- Lỗi khi register bean thứ hai: rollback bean thứ nhất.
- Hai operators race: không mất hoặc ghi đè sai state theo contract.
- Long-running operation timeout: không tạo orphan state.
- Audit có principal, operation name và outcome.

### 11.4. Security tests bắt buộc khi có remote connector

Trong **môi trường test cô lập**:

1. Observer principal có thể đọc metric attributes được cấp quyền.
2. Observer **không thể invoke** admin operation.
3. Observer không thể set writable attribute nếu có.
4. Operator có thể gọi đúng operation đã whitelist.
5. Operator không thể gọi các unrelated destructive operations.
6. Unauthenticated user không thể kết nối remote connector.
7. TLS handshake với certificate/hostname sai bị từ chối.
8. Firewall từ mạng ngoài phạm vi chặn management endpoints.
9. RMI registry không bị spoofing/stub retrieval attack theo cấu hình.
10. Denied access tạo audit phù hợp mà không lộ password.
11. Gọi operation invalid từ admin vẫn bị business validation từ chối.
12. Khi connection bị ngắt giữa operation, client không retry mù quáng.

**Ví dụ Java 17+ không thực hiện những security tests này.** Nó kiểm chứng API/logic, không chứng minh remote JMX security.

### 11.5. Schema compatibility tests

Một generic client không cần domain class vẫn phải biết item names/types. Nếu đổi Snapshot.requestsTotal thành Snapshot.completed, client cũ có thể hỏng. Hãy:

- Tránh rename types/attribute names âm thầm.
- Không đổi units từ ms sang seconds khi giữ cùng tên.
- Thêm fields với contract backward-compatible.
- Có versioned ObjectName/interface khi breaking changes.
- Test Java 17 client với runtime production.
- Test enum/String conversions và nullability.
- Đối chiếu các fields quan trọng của MBeanInfo, không so toàn bộ toString dễ bị thay đổi metadata thứ yếu.

---

## 12. Concurrency và vòng đời của MXBean

### 12.1. Getter có thể bị gọi đồng thời

Một JMX connector có thể phục vụ nhiều collectors/callers. Getters phải an toàn trước concurrent reads. Demo dùng **AtomicReference<Snapshot>**. Với dữ liệu phức tạp, dùng immutable publication hoặc synchronization đúng.

Không trả một Map mutable được internal service sử dụng rồi sửa trong lúc JMX đang serialize; tốt hơn tạo bounded immutable snapshot.

### 12.2. Registration/unregistration lifecycle

Dịch vụ cần register MBeans khi component khởi động thành công và unregister khi shutdown. **ObjectName** phải có convention ổn định và tránh collisions với MBeans khác.

~~~java
// MẢNH MINH HỌA:
ObjectName name = new ObjectName(
        "demo.metrics:type=Requests,name=primary");
server.registerMBean(new Metrics(state), name);
try {
    // Workload lifecycle.
} finally {
    server.unregisterMBean(name);
}
~~~

Nếu register nhiều beans, phải xử lý **partial startup failure**. Không để bean đầu tiên sống sót nếu bean sau đăng ký lỗi và component đã được rollback.

### 12.3. Client không nên giữ trạng thái registry vĩnh viễn

MBean có thể bị unregister/re-register giữa **queryNames**, **getMBeanInfo** và **getAttribute**. Caller phải xử lý InstanceNotFoundException hoặc schema mismatch, có retry/backoff hạn chế nếu phù hợp. Cache metadata có thể cần refresh sau redeploy.

### 12.4. Mỗi JVM là một metric scope

Hai JVMs có cùng ObjectName không chia sẻ số liệu; counter của mỗi instance khác nhau. Dashboard cluster phải gắn instance identity/epoch, nhận biết restart và có aggregation phù hợp.

~~~text
JVM A: RequestsTotal=100
JVM B: RequestsTotal=70

Nếu định nghĩa và khoảng đo khớp, tổng có thể =170.
Nhưng gauge của replicated queue không được sum mù quáng.
~~~

OS/container networking và JMX connector exposure cũng cần được tính riêng cho từng instance. Không nhất thiết mở remote JMX cho mọi pod chỉ để lấy metrics; có thể dùng exporter/collector cục bộ theo mô hình bảo mật của platform.

### 12.5. Tính sẵn sàng của ứng dụng chính quan trọng hơn dashboard

Một monitoring getter thất bại không nên làm service chính dừng xử lý request. Một MXBean admin operation lỗi không được để lại cấu hình nửa chừng. Nếu endpoint quản trị down, core application vẫn cần failure isolation phù hợp. Đặt timeout, circuit breaker hoặc cache theo ngữ cảnh nếu getter buộc phụ thuộc remote data.

---

## 13. Anti-pattern và khắc phục

| Sai lầm | Rủi ro | Hướng đúng |
| --- | --- | --- |
| Export tất cả service getters | Rò secrets/PII | Public management contract tối thiểu |
| Counter bị decrement thường xuyên | Rate sai | Dùng gauge hoặc định nghĩa reset rõ |
| Gauge bị dùng làm total | Chẩn đoán sai | Chọn metric type đúng |
| Error ratio dùng totals cả đời nhưng gọi 5-minute ratio | Misleading | Window deltas |
| Không ghi units | Dashboard nhầm ms/s | Descriptor và tài liệu |
| Tưởng DescriptorKey ép metric behavior | Không có enforcement | Tests và business semantics |
| Đọc nhiều Atomics riêng như một transaction | Snapshot lệch thời điểm | Immutable snapshot |
| CAS lambda có side effects | Side effects có thể lặp | Pure update function |
| Tạo MBean per user/request | Cardinality/PII bùng nổ | Aggregation/quotas |
| Getter query DB lâu | Collector làm treo service | Cached/bounded getter |
| Operation không check bounds | Config nguy hiểm | Validation |
| Admin operation không có audit | Không truy vết | Audit + principal |
| Operation retry không idempotent | Side effects nhân đôi | Set-target/check status |
| Tách metrics/admin rồi tưởng readonly đã được cấp | Bypass quyền | Connector access controls |
| Dựa vào operation impact metadata làm ACL | Unauthorized invoke | Authorization thật |
| Mở JMX remote public | Attack surface lớn | Private network + TLS/auth |
| RMI registry chưa bảo vệ | Stub/credential risk | Secure registry/connector |
| Dùng file JMX password clear text làm production secret store | Lộ mật khẩu | Secure login/cert |
| Readwrite quá rộng | Least-privilege violation | Fine-grained authorization |
| Log tokens/PII trong JMX attributes | Sensitive data leakage | Aggregates/redaction |
| Không test denied invoke | False assurance | Negative role test |
| Không unregister MBeans | Leaks/stale registry | Lifecycle cleanup |
| Partial registration failure | Leaked MBean | Rollback registrations |
| Raw getAttribute cast sai OpenType | ClassCastException | CompositeData/OpenType |
| Thay metric name/type/units không version | Dashboard hỏng | Compatibility tests |
| Không kiểm thử restart | Negative deltas | Process epoch metrics |
| MBean getter trả Map quá lớn | Out-of-memory/GC pressure | Bounded snapshots |

---

## 14. Bài tập tự luyện

1. Chạy chương trình, giải thích vì sao metricsOperations=0 và adminOperations=1.
2. Tìm descriptor của InFlight và assert metricType=gauge.
3. Thêm BytesProcessedTotal kiểu long, đơn vị bytes, type counter.
4. Thêm QueueDepth gauge và cho nó tăng/giảm trong simulation.
5. Thêm processStartEpochMillis để báo counter reset.
6. Thêm sample timestamp, đo thời gian stale của Snapshot.
7. Viết errorRatio cho cùng sample window, xử lý denominator=0.
8. Thiết kế bounded latency histogram và expose P95LatencyMillis.
9. Thử completeRequest(false); xác minh FailuresTotal không tăng.
10. Thử completeRequest khi inFlight=0; đảm bảo reject.
11. Gửi 1000 updates concurrent và assert counters không mất increments.
12. Thử window=9, 10, 3600, 3601 và kiểm tra state invariants.
13. Thay changeWindowSeconds bằng setter, quan sát writable attribute behavior.
14. Đọc MBeanInfo và khẳng định Metrics không có operations.
15. Đọc CompositeData Snapshot bằng generic client không có server record class.
16. Đổi tên một record component và viết schema compatibility test.
17. Thêm một metrics getter tốn CPU vào sandbox và đo polling overhead.
18. Tạo fake collector có rate limit và backoff.
19. Mô phỏng partial registration failure và rollback.
20. Unregister MBean rồi thử getAttribute để xử lý InstanceNotFoundException.
21. Tạo một operation không idempotent và thiết kế idempotency key.
22. Thử wrong method signature trong JMX invoke.
23. Thiết kế policy observer chỉ đọc metrics và operator chỉ được gọi changeWindowSeconds.
24. Tạo remote connector bảo mật trong môi trường test, xác nhận observer bị deny khi invoke.
25. Kiểm thử xác thực TLS/hostname và RMI registry policy.
26. Tạo audit log cho valid/invalid/denied operation, không chứa credentials.
27. Viết threat model cho remote JMX trong container/private network.
28. Xây collector nhận biết counter reset sau restart.
29. Test instance A/B aggregation và tránh sum gauge của replicated resource.
30. So sánh MXBean với OpenTelemetry/Prometheus exporter trong workload có nhiều metrics.

---

## 15. Checklist production

- [ ] Có public MXBean interface đúng convention/annotation.
- [ ] Management API chỉ expose các giá trị và thao tác thực sự cần thiết.
- [ ] Counter/gauge/derived statistics được phân loại chính xác.
- [ ] Mỗi metric có name/type/unit/scope/update/reset semantics.
- [ ] Không coi descriptor metadata là runtime validation.
- [ ] Counter không giảm vô ý, gauge không âm khi contract cấm âm.
- [ ] Có immutable snapshot khi cần tính nhất quán đa fields.
- [ ] CAS update lambda không có side effects.
- [ ] Tránh high cardinality và maps/lists không giới hạn.
- [ ] Getters nhẹ, bounded, side-effect-free.
- [ ] Có latency/CPU/GC budget cho polling.
- [ ] Phân tách metrics và admin operations theo trách nhiệm.
- [ ] Không nghĩ ObjectName riêng tự tạo authorization.
- [ ] Admin operations có min/max, preconditions, timeouts.
- [ ] Operations có idempotency/retry/audit/rollback plan.
- [ ] Chỉ trao quyền invoke/write cho principals được phép.
- [ ] Khi cần least privilege, dùng fine-grained connector/server authorization.
- [ ] MBeanOperationInfo impact không được dùng như ACL.
- [ ] Remote JMX chỉ có trên quản trị network đã được phép.
- [ ] TLS/authentication và RMI registry security được cấu hình, xác minh.
- [ ] Không tắt TLS/auth để dùng production.
- [ ] Không dùng password file cleartext như production secret store.
- [ ] Không để metrics attrs chứa secrets/PII/raw tokens.
- [ ] Kiểm thử observer role không thể invoke operation.
- [ ] Kiểm thử operator không thể gọi unrelated destructive operations.
- [ ] Kiểm thử valid/invalid parameters và state unchanged khi reject.
- [ ] Kiểm thử concurrency, stale snapshot, restart và overflow.
- [ ] Có schema versioning và compatibility tests.
- [ ] Có register/unregister lifecycle và partial failure cleanup.
- [ ] Tách local Java API tests khỏi remote security integration tests.
- [ ] Triển khai API còn được hỗ trợ trên Java 17+.

## Kết luận

Thiết kế MXBean đúng bắt đầu từ ba câu hỏi: **chỉ số có ý nghĩa gì, thao tác nào có tác động gì và ai được phép truy cập?** Metrics phải có đơn vị, scope, loại counter/gauge và chính sách reset/sampling rõ ràng. Với nhiều fields cần nhất quán, xuất một immutable snapshot qua boundary được đồng bộ. Operations phải kiểm tra input, giới hạn side effects và có audit/idempotency plan.

**Việc tách Metrics MXBean và Admin MXBean chỉ tạo phân chia hợp đồng phần mềm, không tự bảo đảm bảo mật.** Phân quyền phải được thực thi ở JMX connector/server access layer. Với remote JMX, cần private network, TLS, authentication, least privilege, RMI registry protection và negative authorization tests.

Ví dụ Java 17+ trong bài đã kiểm chứng counter/gauge, DescriptorKey metadata, immutable CompositeData snapshot, validation của operation và unregister lifecycle với **16 dòng output chính xác**. Hãy kết hợp những tests chức năng này với một bộ security integration tests riêng trước khi mở đường truy cập quản trị thật.

**Tài liệu chính thức và tiêu chuẩn hiện hành:**

- [MXBean — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/MXBean.html)
- [MXBean — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/MXBean.html)
- [DescriptorKey — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/DescriptorKey.html)
- [Descriptor — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/Descriptor.html)
- [MBeanAttributeInfo — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/MBeanAttributeInfo.html)
- [MBeanOperationInfo — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/MBeanOperationInfo.html)
- [MBeanInfo — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/MBeanInfo.html)
- [MBeanServer — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/MBeanServer.html)
- [MBeanServerConnection — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/MBeanServerConnection.html)
- [MBeanServerForwarder — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/remote/MBeanServerForwarder.html)
- [CompositeData — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/openmbean/CompositeData.html)
- [Java SE 26 Monitoring and Management Guide](https://docs.oracle.com/en/java/javase/26/management/java-se-monitoring-and-management-guide.pdf)