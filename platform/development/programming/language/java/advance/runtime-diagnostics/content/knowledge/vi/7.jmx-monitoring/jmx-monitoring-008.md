# 7.8 Quản lý kết nối, tần suất truy vấn và giới hạn cardinality của dữ liệu giám sát

Một JVM có thể trả về hàng trăm thuộc tính JMX, nhiều `ObjectName` và các thông báo quản lý. Điều khó trong production không chỉ là gọi `getAttribute()`, mà còn là **quan sát lâu dài mà không làm quá tải JVM, không tạo bão kết nối và không khiến hệ thống time-series bùng nổ số lượng chuỗi dữ liệu**. Ba quyết định có liên hệ chặt chẽ:

1. **Quản lý kết nối:** ai mở kết nối JMX, kết nối sống bao lâu, khi nào đóng, xử lý timeout/reconnect và phân quyền ra sao?
2. **Tần suất truy vấn:** hỏi MBean nào, bao nhiêu lần mỗi giây, bao nhiêu request song song, có chồng lấn khi lượt trước chưa xong không?
3. **Giới hạn cardinality:** khi chuyển attributes/ObjectNames thành metrics, có bao nhiêu tổ hợp nhãn duy nhất và chúng thay đổi nhanh đến mức nào?

Ví dụ: mỗi 15 giây thu 20 attributes ở 100 JVM nghe có vẻ nhỏ, nhưng nếu mỗi thuộc tính yêu cầu một remote round-trip thì một lượt có thể gồm khoảng **2.000 lời gọi**. Nếu mỗi metric còn gắn `request_id` hoặc `user_id` động, hàng triệu chuỗi thời gian có thể xuất hiện; tăng CPU, memory, network, chi phí lưu trữ và làm cho dashboard/alert khó tin cậy. Một giải pháp tốt phải kiểm soát **chi phí ở cả phía JVM, collector và hệ thống metrics**.

Bài này xây dựng mô hình vận hành cho JMX trong Java 17+: vòng đời `JMXConnector` và `MBeanServerConnection`, timeout, backoff, giới hạn song song, polling cadence, khác biệt counter/gauge, chọn attributes bằng allowlist, tính cardinality và thiết kế nhãn an toàn. Mã thực hành Java 17+ chạy độc lập bằng platform MBeanServer **nội bộ**, không yêu cầu mở cổng JMX remote hay có dịch vụ bên ngoài.

## 1. Mô hình một hệ thống giám sát JMX

Một pipeline phổ biến:

```text
 [JVM A]       [JVM B]       [JVM C]
    |             |             |
 MBeanServer   MBeanServer   MBeanServer
    |             |             |
 JMX connector/JMX access (nếu được cấu hình, phân quyền)
    \             |             /
     \            |            /
      +--- monitoring collector ---+
          | connect/reconnect      |
          | discover + getAttrs    |
          | schedule + retry       |
          | transform + filter     |
          | limit labels/series    |
          +-----------+------------+
                      |
                 metrics backend
                      |
             dashboards / alerts
```

Các tầng có nhiệm vụ riêng:

| Tầng | Nhiệm vụ | Rủi ro nếu thiết kế sai |
| --- | --- | --- |
| JVM/MBean | Cung cấp các giá trị quản trị | Getter chậm/lock, đối tượng MBean quá nhiều, thông tin nhạy cảm |
| Connector | Vận chuyển request/response và events | Mở quá nhiều kết nối, mất mạng, auth/TLS sai, timeout |
| Collector | Chọn attributes, lịch polling, retry, transform | Thundering herd, overlapping polls, data missing bị biến thành 0 |
| Exporter/mapper | Chuyển `ObjectName` và values thành metrics có labels | Dynamic labels, series churn, sai units và metric types |
| Time-series backend | Lưu series, truy vấn/rate/alert | Bùng nổ active series, RAM/đĩa/query latency |
| Người vận hành | Đọc dữ liệu và quyết định | Nhầm snapshot với lịch sử, nhầm reconnect với restart, alert nhiễu |

**JMX API là mô hình truy cập quản trị, không tự cung cấp retention, rate calculation hoặc cardinality guardrails.** Cần tự thiết kế các lớp trên hoặc dùng exporter đã được kiểm chứng cấu hình tương đương. Phân biệt rõ **remote connection** với **local MBeanServerConnection**: cùng các phương thức đọc, nhưng chi phí, lỗi mạng và vòng đời tài nguyên khác nhau.

### 1.1 Đơn vị cần quản lý là “target JVM instance”, không phải chỉ hostname

Một host có thể chạy nhiều JVM. Một pod/container có thể restart và đổi PID. Một service có thể có nhiều replicas. Vì vậy identity nên gồm:

- Workload/service đã được phép quan sát.
- Environment/cluster/namespace theo chính sách; không phải tất cả phải làm metric labels.
- Process/JVM instance ID hoặc startup time để nhận biết restart.
- Endpoint và cơ chế kết nối (local JMX, secured remote JMX hay agent/exporter nội bộ).
- MBean ObjectName và tên attribute cụ thể.
- Timestamp lấy mẫu, trạng thái kết nối và chất lượng dữ liệu.

Không coi kết nối tới `host:port` là bằng chứng đúng JVM nếu endpoint routing, NAT, sidecar hay deployment đã thay đổi. `ObjectName` chỉ định danh trong **một MBeanServer**, có thể trùng ở nhiều JVM. `JMXConnector.getConnectionId()` định danh một kết nối **trong vòng đời kết nối**, không phải identity bền vững của service hay nhãn metric nên giữ mãi.

## 2. Quản lý vòng đời kết nối JMX

### 2.1 Các API cốt lõi

Trong Java SE, các thành phần quan trọng:

| API | Công dụng | Lưu ý |
| --- | --- | --- |
| `JMXServiceURL` | Mô tả endpoint của JMX connector | Không có nghĩa endpoint an toàn hay luôn truy cập được |
| `JMXConnectorFactory.connect(url, env)` | Tạo và thiết lập kết nối, trả `JMXConnector` đã connect | Có thể lỗi I/O, bảo mật, protocol/provider |
| `JMXConnector.getMBeanServerConnection()` | Lấy đối tượng gọi các method JMX remote | Phương thức trên connection có thể tiếp tục lỗi sau handshake |
| `MBeanServerConnection.getAttributes(...)` | Đọc nhiều attributes của một MBean | Một số thuộc tính không lấy được có thể bị bỏ qua |
| `JMXConnector.close()` | Đóng kết nối client | Có thể throw `IOException` và bản thân close có thể chậm |
| `addConnectionNotificationListener(...)` | Nghe trạng thái kết nối JMX | Không phải event lịch sử bền vững |
| `JMXConnector.getConnectionId()` | ID được server cấp cho kết nối | Không dùng làm label per reconnect |

`MBeanServerConnection` đại diện cho đường truy cập tới MBeanServer **cục bộ hoặc từ xa**; `MBeanServer` cục bộ kế thừa giao diện đó. Ở remote, kết nối có thể thành công rồi sau đó mất mạng hoặc mất quyền; đừng coi successful handshake là bảo đảm mọi `getAttribute` tiếp theo sẽ thành công.

### 2.2 Connect once, reuse có điều kiện, close có kỷ luật

Một collector thường nên **tái sử dụng kết nối đang khỏe** qua nhiều lượt polling thay vì liên tục connect/auth mỗi 1 giây, nhưng không có quy tắc “giữ kết nối bất tử”:

1. Chỉ mở kết nối tới target và endpoint được phê duyệt.
2. Xác thực/TLS và kiểm tra identity server qua transport được cấu hình phù hợp.
3. Thực hiện một probe nhẹ có bounded cost, xác nhận target đúng JVM.
4. Tái sử dụng khi connector khỏe và chính sách transport cho phép.
5. Khi gặp lỗi I/O/connection-failed, phân loại kết nối hỏng; không tiếp tục dùng `MBeanServerConnection` cũ như luôn hợp lệ.
6. Reconnect có backoff/jitter, giới hạn số attempt và quản lý tài nguyên.
7. Khi collector shutdown hoặc target bị bỏ khỏi inventory, tháo listener và `close()` trong lifecycle cleanup.

**Mỗi lần connect mới có chi phí**: bắt tay transport, authentication, tài nguyên thread/socket, kiểm tra MBeans. **Mỗi kết nối giữ quá lâu** cũng có thể gặp stale state, server redeploy và resource leak. Chọn lifetime theo provider, network policy, số target, failure rate và tải thực tế.

### 2.3 Mẫu API để đóng kết nối bằng try-with-resources

Đoạn Java sau là **một method minh họa**; caller phải cung cấp endpoint hợp lệ, môi trường xác thực và chỉ dùng trong mạng được cấp quyền:

```java
import java.util.Map;
import javax.management.AttributeList;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

static AttributeList readOnce(
        JMXServiceURL url, Map<String, ?> approvedEnvironment)
        throws Exception {
    try (JMXConnector connector =
                 JMXConnectorFactory.connect(url, approvedEnvironment)) {
        MBeanServerConnection connection =
                connector.getMBeanServerConnection();
        ObjectName threading = new ObjectName("java.lang:type=Threading");
        return connection.getAttributes(threading,
                new String[] {"ThreadCount", "DaemonThreadCount"});
    }
}
```

Đây **không phải tệp Java độc lập**: đoạn method cần đặt bên trong một class, và cấu hình bảo mật `approvedEnvironment` phải được chuẩn bị bởi deployment. Nếu muốn tránh kết nối lại mỗi scrape, lưu connector trong một **resource owner** chịu trách nhiệm health/reconnect/close, thay vì tạo nó ở mọi lần gọi hàm như mẫu ngắn. `AttributeList` được trả về sau khi đã đọc xong; không giữ `MBeanServerConnection` rồi dùng sau khi connector bị đóng.

**Quan trọng:** `JMXConnector.close()` trong JDK 21 có thể **chặn một khoảng thời gian đáng kể** khi server bị lỗi/không phản hồi. `try-with-resources` giúp đảm bảo gọi cleanup nhưng **không biến close thành non-blocking**. Nếu production yêu cầu time budget chặt, cần cơ chế quản lý transport và shutdown có kiểm soát, không mặc định `close()` luôn tức thì.

### 2.4 Không tự chế tên timeout property như một chuẩn JMX chung

JMX tiêu chuẩn xác định API connector; **timeout cho connect/read/idle/retry phụ thuộc provider, transport, JDK release và môi trường**. Không có một `-D...timeout` tùy ý có thể được khẳng định là mặc định áp dụng cho mọi connector.

Thiết kế timeout phải tách:

- **DNS/endpoint resolution**: tên host có phân giải đúng không?
- **Connection establishment/TLS/auth**: thời gian bắt tay và xác thực.
- **Remote request/read**: `getAttribute` bị chậm do mạng hay getter?
- **Total scrape deadline**: toàn bộ lượt có còn kịp cadence không?
- **Shutdown/close**: cleanup có thể chậm.
- **Retry/reconnect budget**: tránh thử mãi một target chết.

Cấu hình timeouts cụ thể phải dựa trên tài liệu **đúng provider/phiên bản** và kiểm thử network failures. Chỉ đặt timeout bên ngoài bằng `Future.get(timeout)` cũng **không bảo đảm** kết thúc ngay lời gọi I/O bị block: `cancel(true)` là yêu cầu interrupt, không phải cơ chế đóng socket chắc chắn trong mọi RMI/provider. Không tạo unbounded threads khi lời gọi trước không chịu thoát.

### 2.5 Phân biệt status kết nối, dữ liệu rỗng và target chết

| Hiện tượng | Có thể do | Phản ứng phù hợp |
| --- | --- | --- |
| Kết nối thất bại từ đầu | Endpoint sai, auth/TLS, network, server chưa bật | Kiểm tra endpoint và security; backoff |
| Kết nối đang dùng phát `FAILED` | Mạng/server hỏng, connector state thay đổi | Mark connector unhealthy; quản lý cleanup/reconnect |
| `getAttributes` trả thiếu field | Attribute không tồn tại/không readable/permission hoặc getter lỗi | Kiểm tra danh sách nhận, không tự điền 0 |
| `InstanceNotFoundException` | MBean biến mất/redeploy, sai ObjectName/JVM | Re-discover có giới hạn, xác minh instance |
| Timeout từng request | Getter block, JVM quá tải, mạng/transport | Ghi timeout; giảm fan-out, kiểm tra tài nguyên |
| Không có sample mới | Target/collector/export pipeline lỗi | Giữ missing/stale và scrape health; không tạo success giả |
| `getConnectionId` thay đổi | Reconnect/connection instance khác | Dùng để chẩn đoán connection churn, không kết luận JVM restart |

Một số tình huống có nhiều nguyên nhân cùng lúc. Không suy “GC làm đứt JMX” chỉ từ một timeout.

## 3. Connection notifications và health của collector

`JMXConnector.addConnectionNotificationListener(...)` nhận các `JMXConnectionNotification` (khi provider phát theo contract) như:

- `OPENED`: kết nối được mở.
- `CLOSED`: kết nối đóng.
- `FAILED`: kết nối thất bại bất thường.
- `NOTIFS_LOST`: client có thể đã mất một số notifications từ remote.

Đây là **connection events**, khác với notification của một MBean về heap threshold hoặc hàng đợi ứng dụng. Một notification `NOTIFS_LOST` cảnh báo về tính đầy đủ dữ liệu event stream; nó không tự nói metric polling đã mất cùng số mẫu.

Các nguyên tắc vận hành:

1. Theo dõi connection health bằng status, số lần reconnect, thời gian connect và lỗi I/O, **không chỉ** dựa vào số TCP sockets.
2. Đăng ký listener một lần theo connector lifecycle, tháo khi cleanup.
3. Không thực hiện reconnect blocking hoặc truy vấn MBean nặng trực tiếp trong callback.
4. Sau reconnect, xác minh MBean registry/target identity; resubscribe listeners khi cần.
5. Không dựa vào `OPENED`/`CLOSED` như **lịch sử bền vững**; event stream có thể mất.
6. Nếu monitoring dựa trên notification, dùng polling định kỳ để đối soát trạng thái và có cơ chế lưu event khi business yêu cầu.

**Tại sao không dùng connection ID làm label?** Vì ID có thể thay khi reconnect; label mới tạo một chuỗi time series khác. Nếu hàng trăm targets reconnect thường xuyên, số series tăng dù chỉ có một JVM mỗi target. Giữ connection ID ở **log chẩn đoán có hạn chế quyền** khi cần trace, còn metric nên dùng target identity ổn định hơn.

## 4. Tần suất truy vấn: cadence, cửa sổ đo và chi phí

### 4.1 Polling một attribute không bằng nhận một event

Một MBean attribute thường là **snapshot hiện tại** hoặc **counter tích lũy**. Gọi `getAttribute` mỗi 30 giây không giúp nhìn những đỉnh ngắn đã xảy ra và biến mất giữa hai lần lấy mẫu.

Ví dụ một queue depth:

```text
T=00s: depth = 4   (poll được)
T=10s: depth = 250 (spike)
T=20s: depth = 3   (hết spike)
T=30s: depth = 4   (poll được)
```

Nếu chỉ poll mỗi 30 giây, dashboard có thể luôn hiện 4 và **bỏ sót spike 250**. Muốn ghi nhận peak/cause, cần event/histogram/high-watermark hoặc sampling nhanh hơn có kiểm soát, tùy mục đích. Poll nhanh hơn cũng không bảo đảm bắt được mọi spike nếu không có event capture.

### 4.2 Phân loại dữ liệu trước khi chọn interval

| Loại quan sát | Ví dụ JMX | Cách tính/thói quen polling |
| --- | --- | --- |
| Gauge tức thời | ThreadCount, QueueDepth, HeapMemoryUsage.used | Lấy mẫu theo mục tiêu và độ biến động; không suy min/max giữa hai mẫu |
| Counter tích lũy | GC collection count, completed tasks, request total | Tính delta/rate theo thời gian; nhận diện restart/reset |
| Metadata/config ít đổi | JVM vendor, version, bean names, capacity cố định | Discover/cache theo lifecycle; không query mỗi giây |
| Event/notification | Threshold crossing, MBean registered/unregistered | Subscribe nếu hỗ trợ; có cơ chế reconcile/mất event |
| Expensive diagnostic | Heap dump, full thread dump, histograms nặng | Không đưa vào vòng polling phổ thông |
| Per-request trace | Latency từng request, stack/context | Không biến mỗi request thành dynamic MBean/metric label |

**Không có một cadence đúng cho mọi MBean.** Chọn dựa trên nhu cầu SLO, hành vi dữ liệu, chi phí getter/round-trip, số target, và khoảng thời gian phát hiện sự cố mong muốn. Ví dụ lấy mẫu 15–30 giây có thể phù hợp với dashboard tổng quan của một hệ thống, còn phát hiện spike vài mili giây cần nguồn sự kiện phù hợp — không đơn giản tăng poll lên hàng nghìn lần mỗi giây.

### 4.3 Mối liên hệ giữa interval và lượng truy vấn

Giả sử:

- `T` = số JVM targets.
- `B` = số MBeans được hỏi trên mỗi target.
- `A` = số attributes cần mỗi bean.
- `P` = giây giữa hai lượt polling.

Nếu naïve client gọi từng attribute qua remote:

```text
attribute_reads_per_cycle = T × B × A
attribute_reads_per_second_average ≈ (T × B × A) / P
```

Ví dụ `T=60, B=4, A=3, P=15`:

```text
60 × 4 × 3 = 720 attribute values / cycle
720 / 15 = 48 attribute values / second (trung bình)
720 × (3600 / 15) = 172800 values / hour
```

Nếu dùng `getAttributes(name, String[])` theo bean để **giảm remote round trips**, số method calls về lý thuyết là `T × B = 240 calls/cycle`, tức khoảng **16 calls/giây**, nhưng **vẫn cần đọc 720 giá trị** ở phía JVM. Đây là tính toán sizing, **không phải benchmark đo thực tế**: getter cost/transport/overhead và số attributes mỗi bean không đều nhau.

Một batch multi-attribute không phải snapshot nguyên tử toàn MBean/JVM; có thể thiếu một số field (API bỏ chúng khỏi `AttributeList`). **Không được xem 720 giá trị request tương đương 720 giá trị có đủ**.

### 4.4 Chi phí có thể nằm trong getter chứ không ở mạng

Một getter tốt có thể chỉ đọc atomic counter, trong khi getter khác có thể khóa một cấu trúc dữ liệu, scan collection lớn, tính histogram hoặc lấy thông tin hệ điều hành. Nếu hỏi MBean quá thường xuyên, chính hoạt động giám sát có thể gây CPU load, lock contention hoặc làm chậm request.

Một policy hợp lý:

1. Chỉ lấy những attributes thật sự cần, theo allowlist.
2. Phân loại cheap/medium/expensive và thiết lập cadence riêng.
3. Đo p50/p95/p99 của **scrape duration** và rate lỗi thu thập, không chỉ metric nghiệp vụ.
4. Giới hạn thời gian/in-flight để getter chậm không tạo chuỗi yêu cầu chồng lấn.
5. Với dữ liệu ít thay đổi, cache metadata/`MBeanInfo` có invalidation khi MBean đổi.
6. Khi thấy latency ứng dụng tăng đồng thời monitoring load tăng, thử giảm cadence trong môi trường kiểm soát rồi đối chiếu.

Giảm round trips không thay thế việc **thiết kế getter rẻ** hoặc giới hạn total work mỗi scrape.

## 5. Lập lịch polling an toàn

### 5.1 fixed-rate, fixed-delay và overlapping jobs

Với một target được poll mỗi 10 giây nhưng một scrape mất 18 giây:

- Nếu scheduler cho phép overlap, có thể có **hai scrape cùng chạy** trên JVM, tạo áp lực tăng thêm và khó xác định timestamp.
- Nếu có **một worker tuần tự** hoặc cơ chế single-flight, lượt tiếp theo không overlap; thời gian giữa hai mẫu dài hơn dự kiến. Đây là lựa chọn an toàn hơn cho nhiều workload.
- `scheduleAtFixedRate` trên một `ScheduledThreadPoolExecutor` không thực thi **các lần chạy kế tiếp của cùng một periodic task** đồng thời theo contract, nhưng nhiều task riêng/instances khác nhau vẫn có thể làm trùng target; không suy rằng toàn bộ hệ thống được bảo vệ khỏi overlap.
- `scheduleWithFixedDelay` tính khoảng nghỉ sau khi lượt trước hoàn tất, phù hợp khi muốn giảm overlap và tạo khoảng thở. Nhưng cadence thực tế sẽ là **thời gian job + delay**.

Mô hình khuyến nghị cho collector phân tán:

```text
target JVM ──> one owner ──> at most one in-flight poll
                        |
                   bounded timeout
                        |
                 success / missing
                        |
          next schedule + jitter/backoff
```

Nếu cluster có nhiều collector replicas cùng poll một target, local mutex **không đủ**. Cần phân chia ownership theo shard/leader hoặc thống nhất một exporter per JVM rồi để backend scrape, tránh double-collect.

### 5.2 Jitter tránh thundering herd

Nếu 1.000 JVM cùng được scrape chính xác lúc 00:00:00, 00:00:15, ... có thể tạo burst network/CPU. **Jitter nhỏ** phân tán lịch bắt đầu:

```text
nominal_interval = 15 s
start_offset_per_target ∈ [0 s, 3 s]
retry_delay = capped_exponential_backoff + bounded_jitter
```

Các số chỉ là **mẫu thiết kế**, không phải mặc định của JMX. Jitter phải ổn định/tái lập đủ để tránh tất cả targets đổi giờ liên tục; có thể tính từ hash của target identity, nhưng cần tránh hash collision có ý nghĩa vận hành và phải đo phân bố tải thực.

Với cửa sổ cố định 15 giây, nếu scrape bị chậm hãy ghi timestamp lúc lấy số liệu và khoảng cách mẫu thực tế; không tính rate bằng hằng số 15 khi elapsed thực là 23 giây.

### 5.3 Bound concurrency ở nhiều mức

Nên đặt giới hạn:

- **Per target:** tối đa một scrape chủ động, tránh request chồng.
- **Per collector:** tổng số kết nối và requests in-flight có giới hạn.
- **Per host/pod/network:** không đổ cùng lúc nhiều task lên một JVM/node.
- **Retry budget:** số lần reconnect và tốc độ retry được quản lý.
- **Memory buffer/queue:** bounded; khi full, drop hoặc delay có chú giải, không tăng queue vô hạn.

Nếu collector có 100 worker nhưng chỉ 20 JVM targets, số thread dư không tạo thông tin tốt hơn. Nếu có 10.000 targets, 1 worker có thể quá chậm; giải pháp không chỉ tăng worker vô hạn mà cần **sharding, prioritization, batching và capacity planning**.

## 6. Backoff, circuit breaker và cách diễn giải missing data

### 6.1 Không retry liên tục khi endpoint chết

Khi JVM restart hoặc mạng đứt, việc thử kết nối mỗi 10 ms từ nhiều collector có thể tạo **retry storm**. Một lịch backoff minh họa:

```text
initial_delay = 15 s
after 1 failure = 30 s
after 2 failures = 60 s
subsequent = 60 s capped + small jitter
```

Khi kết nối thành công ổn định, reset failure counter. Có thể dùng circuit breaker để tạm dừng phần truy vấn nặng vào target lỗi, sau đó cho phép probe nhẹ khi hết cooldown. Phân biệt lỗi xác thực/certificate (thường cần cấu hình lại) với lỗi tạm thời (có thể retry có giới hạn). Không log password/token trong error context.

### 6.2 Missing không phải zero

Giả sử đọc queue depth ở T0 = 50; T1 timeout; T2 = 80. Những cách sai:

- Ghi T1 = 0: tạo đỉnh sụt giả.
- Ghi mãi T0 = 50 mà không đánh dấu stale: hiển thị “healthy” dù không có dữ liệu.
- Tính delta 80 - 0 để báo queue tăng 80, trong khi T1 không đo được.
- Lấy GC counter trước restart trừ counter sau restart rồi báo rate âm.

Hệ thống cần trạng thái collector riêng như `scrape_success` (1/0), thời gian scrape, thời điểm sample cuối và error category. **Missing data** là trạng thái đo; không được bị ép thành một giá trị nghiệp vụ “không có lỗi”.

### 6.3 Vì sao timeout đơn giản không luôn đủ?

Mỗi request remote có thể block bên dưới Java RMI hoặc một provider khác. Nếu tạo một thread mới cho mọi timeout và không bao giờ giải phóng thread bị kẹt, collector sẽ cạn worker/heap. `Future.cancel(true)` có thể yêu cầu interrupt nhưng không phải mọi transport I/O đều dừng tức thì. Giải pháp production gồm provider-supported transport timeout, giới hạn worker và connection lifecycle, cô lập tác vụ lỗi, giám sát thread leak và cách phục hồi connector an toàn.

**Tuyệt đối không tự đặt một JMX timeout property chưa được tài liệu hóa** rồi khẳng định có hiệu lực cho mọi JVM/JDK.

## 7. Truy vấn đúng MBeans và giảm số lời gọi

### 7.1 Chỉ discover thường xuyên khi thật sự cần

Không nên mỗi 5 giây chạy `queryNames(null,null)` để liệt kê **mọi MBean**, rồi đọc toàn bộ attributes từ mọi bean. Vấn đề:

- Registry có thể chứa platform beans, application beans, thư viện, diagnostic beans.
- Một số beans động được tạo/hủy theo workload.
- Metadata và attribute values có thể chứa tên nội bộ/secret hoặc tốn nhiều chi phí.
- Mỗi `ObjectName` động có thể trở thành một nhóm metric mới.
- Trong môi trường nhiều người dùng, truy vấn quá rộng tạo gánh nặng quan sát không liên quan.

Nên bắt đầu bằng **tập ObjectName/mẫu domain có giới hạn**, ví dụ `java.lang:type=Threading` hoặc `com.example.monitoring:type=Queue,name=Orders`, cùng danh sách attributes được cho phép. Cache discovery trong vòng đời JVM hoặc refresh thưa; khi `InstanceNotFoundException`/redeploy thì refresh có backoff.

### 7.2 getAttributes thay cho N getAttribute, nhưng kiểm tra thiếu field

`MBeanServerConnection.getAttributes(ObjectName,String[])` cho phép yêu cầu nhiều attributes của **một** MBean:

```java
AttributeList list = connection.getAttributes(
        new ObjectName("java.lang:type=Threading"),
        new String[] {"ThreadCount", "DaemonThreadCount"});
```

Đây là **đoạn minh họa nằm trong method đã có** `connection`; nó không phải chương trình độc lập. API cho phép **bỏ các attributes không lấy được** khỏi `AttributeList`. Kết quả không được giả định có đủ hai giá trị hoặc theo thứ tự mảng yêu cầu; đối chiếu tên từng `Attribute`.

Không gom hàng trăm attributes “cho tiện” nếu chúng đến từ nhiều MBeans; mỗi lời gọi chỉ định **một** ObjectName. Với dữ liệu đòi atomic snapshot của nhiều fields, JMX không tự cung cấp contract đó; ứng dụng có thể expose một composite snapshot read-only riêng, hoặc dashboard phải chấp nhận consistency window.

### 7.3 Cache MBeanInfo nhưng không cache mù đời sống JVM

`getMBeanInfo` trả metadata attribute/operation của MBean. Thường chỉ cần lấy lúc discovery hoặc khi bean thay đổi, không cần lấy mọi scrape. Tuy nhiên:

- MBean có thể unregister/re-register với contract mới.
- DynamicMBean có metadata phụ thuộc trạng thái.
- Service redeploy/restart có thể đổi attribute names/types.
- JMX endpoint có thể chuyển qua instance khác sau reconnect.

Vì thế cache cần key có **JVM instance + ObjectName**, TTL/invalidation hợp lý và xử lý lỗi khi contract khác. Không cho metadata cache tồn tại vĩnh viễn qua mọi restart.

### 7.4 Ràng buộc quyền truy cập và tính an toàn

Collector nên dùng **read-only permissions** nếu chỉ giám sát. Không cho phép `setAttribute` hay `invoke` rộng quyền chỉ để lấy metrics. Một operation có thể flush cache, reset counters hoặc restart component. Bảo vệ remote connector bằng network boundary, authentication, TLS và least privilege; không mở JMX remote không xác thực trên Internet.

Command line/URL credentials, session ID, ObjectName và notifications có thể mang dữ liệu nhạy cảm. Chỉ log connection ID/target alias khi cần chẩn đoán, không in password hoặc raw environment.

## 8. Cardinality là gì, tại sao nó gây vấn đề?

**Cardinality của một metric trong time-series backend** là số tổ hợp nhãn khác nhau mà backend phải lưu cho metric đó. Với mô hình Prometheus, mỗi kết hợp duy nhất của **metric name + label names/values** tạo một time series. Thay một giá trị label từ `instance=A` sang `instance=B` có thể tạo thêm một series. Các nhãn định danh biến thiên nhanh gây **series churn**: chuỗi cũ hết cập nhật nhưng vẫn chiếm tài nguyên lưu trữ/metadata trong một thời gian.

Cardinality khác với:

- **Số sample:** một series lấy 240 mẫu/giờ vẫn là một series (cho mỗi giá trị nhãn liên tục).
- **Số metrics names:** một metric có thể có hàng triệu series vì labels.
- **Số MBeans:** một MBean có nhiều attributes/series; một application có hàng nghìn MBeans động.
- **Số JVM targets:** mỗi target có thể phát hàng trăm series.
- **Dung lượng log text:** số series là bài toán metadata/index/query, không chỉ số byte raw samples.

### 8.1 Công thức upper-bound tổ hợp

Nếu một metric có các nhãn độc lập với tối đa `n1, n2, ..., nk` giá trị, số chuỗi tiềm năng:

```text
potential_series_per_metric ≤ n1 × n2 × ... × nk
```

Dấu “≤” vì trong thực tế không nhất thiết mọi tổ hợp tồn tại. Tuy nhiên đây là phép **ước lượng upper bound** để kiểm soát rủi ro thiết kế khi không có dữ liệu phân bố thật.

Ví dụ giả định:

| Label | Số giá trị tối đa |
| --- | ---: |
| `service` | 3 |
| `environment` | 2 |
| `instance` (mỗi service/env) | 4 |
| `collector` | 3 |
| `status` | 2 |

Upper bound: `3 × 2 × 4 × 3 × 2 = 144 series` cho một metric. Thêm `request_id` với 10.000 giá trị có thể tăng upper bound thành **1.440.000 series**. Hầu hết metrics JMX **không có lý do** gắn request ID ở cấp series; request tracing thuộc hệ thống logs/traces với retention, sampling và quyền phù hợp.

**Chỉ một nhãn không giới hạn** có thể phá hủy budget dù các nhãn khác đều có vài giá trị.

### 8.2 Các nhãn tưởng vô hại nhưng thực chất rất động

| Nhãn được đề xuất | Rủi ro | Cách thay thế |
| --- | --- | --- |
| `request_id`, `trace_id` | Gần như mỗi request tạo series mới | Giữ trong trace/log, không làm metric label |
| `user_id`, email, phone | Unbounded, dữ liệu riêng tư | Bỏ; aggregate theo nhóm được phép |
| `session_id`, token | Unbounded, nhạy cảm | Không đưa vào metrics |
| Full URL/path có ID | Mỗi path/query khác nhau tạo series | Route template như `/orders/{id}`, không in ID thật |
| `exception_message` | Chuỗi tự do theo input, có thể chứa secret | Dùng exception class/category allowlist |
| `sql_query` nguyên văn | Mỗi literal/query khác nhau, lộ dữ liệu | Query type/normalized operation |
| `thread_name` động | Chứa số/ID/session; số giá trị có thể lớn | Nhóm thread pool hoặc role |
| `ObjectName` đầy đủ | Có thể chứa ID động | Map sang stable MBean type/name subset |
| `connection_id` | Mỗi reconnect tạo ID mới | Metric `reconnect_total` theo target ổn định |
| `pid` | Thay qua restart, trùng container namespace | Dùng instance identity ở metadata/target label có vòng đời rõ |
| Timestamp trong label | Mỗi lần scrape một series mới | Timestamp là **sample timestamp**, không là label |

Nhiều nhãn không chỉ tiêu tốn bộ nhớ mà còn gây **rò rỉ dữ liệu**: tên tài khoản, host/private endpoint, chuỗi SQL, credential, path cấu hình. Quy tắc “không gắn ID động” vừa là hiệu năng, vừa là quản trị dữ liệu.

### 8.3 Giá trị cardinality thấp hay cao không cố định theo tên

`status` có thể có đúng ba giá trị `ok|warn|error`, nhưng nếu lấy raw error message làm status thì giá trị trở nên không giới hạn. `endpoint` có thể là năm route templates ổn định hoặc hàng triệu URL riêng lẻ. `instance` hữu ích cho phân tích một JVM, nhưng tự nó tăng theo số replica và đợt deploy.

Vì vậy cần kiểm tra **nguồn gốc của giá trị**, không chỉ tên label. Một danh sách label “trông ổn” có thể biến thành high cardinality nếu dữ liệu ứng dụng thay đổi.

## 9. Từ ObjectName/attribute đến metric labels

JMX thường tổ chức tên như:

```text
com.example:type=Queue,name=Orders,tenant=ACME42
```

Một exporter có thể lấy domain/type/name/tenant làm labels. Nếu `tenant` có hàng nghìn giá trị và mỗi MBean được tạo theo request, series sẽ tăng mạnh. Tốt hơn định nghĩa allowlist mapping **từ ObjectName đến metric schema**, có giới hạn số giá trị được chấp nhận.

### 9.1 Chọn metric contract trước khi mapping

Ví dụ schema được **thiết kế**:

```text
java_app_queue_depth{service="orders",environment="prod",pool="primary"} 12
java_app_queue_processing_total{service="orders",environment="prod",pool="primary"} 4210
```

Hai dòng là **minh họa định dạng metrics**, không phải số liệu đo ở một hệ thống thực. Không mang `tenant_id`, `session_id` hoặc toàn bộ ObjectName vào labels. Nếu cần phân tích theo nhóm khách hàng, xem xét **aggregate có số nhóm hữu hạn** và chính sách riêng tư, không tự đưa ID thật vào time series.

### 9.2 Kiểm soát giá trị labels bằng allowlist

Quy trình:

1. Định nghĩa **metric name**, đơn vị, loại gauge/counter và ý nghĩa theo mỗi scrape.
2. Chỉ định những label keys cố định được phép.
3. Với mỗi label key, quyết định danh sách giá trị hợp lệ hoặc nguồn có thể giới hạn.
4. Nếu giá trị không hợp lệ/quá nhiều, ưu tiên **bỏ dimension** hoặc nhóm vào bucket `other` theo một chính sách đã kiểm thử, không tạo series mới tự do.
5. Không đổi tên label schema liên tục; schema changes cần version/review.
6. Đo actual unique series và churn; so với budget/alerts của backend.

Một allowlist chỉ tên label **chưa đủ** nếu giá trị bị nhồi request ID vào trường `pool`; cần validate **cả nguồn và miền giá trị**.

### 9.3 Một số nhãn cần thiết nhưng phải có quản lý lifecycle

`instance`, `pod`, `container` hữu ích để điều tra restart và phân biệt JVM. Chúng tạo churn khi deployment thay instance. Đây là churn có lý do, cần:

- Tự động dừng export cho targets bị xóa/không còn hợp lệ.
- Quy trình stale marker hoặc xóa series theo backend, không tự lấp giá trị giả.
- Retention và scrape interval phù hợp.
- Giới hạn replica/scrape targets trong monitoring budget.
- Aggregate dashboard theo `service`/`environment` khi mục tiêu là SLO, dùng instance label khi drill-down.

Không xóa mọi nhãn instance chỉ để giảm cardinality nếu sẽ làm ghép số của các JVM khác nhau và khiến counter reset bị diễn giải sai.

## 10. Series budget, churn budget và chi phí lưu trữ

### 10.1 Series budget không phải sample budget

Với `S` series đang hoạt động và interval `P` giây:

```text
samples_per_hour_approx ≈ S × (3600 / P)
```

Ví dụ `S=144, P=15` thì khoảng `144 × 240 = 34.560 samples/giờ` cho những series này nếu mỗi scrape thành công. Nếu gắn request ID làm `S=1.440.000`, ta có khoảng **345.600.000 samples/giờ** theo giả định mọi series đều tồn tại ở mọi lần scrape. **Đây là upper-bound giả định** chứ không phải dự báo usage thực: request ID thực tế có thể chỉ tồn tại ở một scrape, gây high **series churn** thay vì liên tục nạp đủ 1,44 triệu series. Tuy vậy, churn này cũng gây chi phí metadata/index/retention.

Không lấy số “samples/giờ” rồi kết luận số byte disk bằng một phép nhân cố định nếu chưa biết encoding, replication, label set, histogram formats và retention.

### 10.2 Hai loại giới hạn nên đo

- **Active series cardinality:** số series còn được coi active ở thời điểm/cửa sổ backend định nghĩa.
- **Series churn:** số series mới xuất hiện hoặc biến mất trên một khoảng thời gian.

Một dịch vụ có 10.000 active series ổn định có thể dễ vận hành hơn một dịch vụ chỉ 2.000 active tại mỗi thời điểm nhưng sinh thêm hàng trăm nghìn series mới mỗi giờ. Mỗi lần reconnect, MBean dynamic creation hoặc deployment với tên chứa timestamp đều có thể gây churn.

### 10.3 Đặt budget theo cấp

Gợi ý chính sách **ví dụ, không phải chuẩn JMX**:

| Cấp | Ngưỡng/điều kiện có thể thiết kế | Cách phản ứng |
| --- | --- | --- |
| Một MBean | Số attributes/labels xuất có allowlist | Bỏ fields ngoài mục tiêu |
| Một JVM target | Max exported series, max scrape duration | Giảm phạm vi/interval, báo sample loss |
| Một collector | Max connections/in-flight requests, memory queue | Rate-limit/shard và backoff |
| Một service | Max unique series/churn per hour | Review labels/object creation |
| Toàn backend | Active series, ingest rate, storage/query budget | Capacity planning và alert |
| Privacy | Không cho secret/PII ở label values | Loại trường trước khi xuất |

**Không lặng lẽ drop series rồi hiển thị biểu đồ như đầy đủ.** Nếu budget bị vượt, phát cảnh báo `exporter_series_dropped_total` hoặc trạng thái tương đương, cùng thông tin rõ về các metrics bị ảnh hưởng. Nhưng bản thân metric “dropped count” cũng phải dùng labels hữu hạn, không nhét tên request/user bị drop vào nó.

## 11. Đúng loại metric: gauge, counter và histogram

### 11.1 Gauge

Gauge phản ánh trạng thái tại thời điểm mẫu, ví dụ `ThreadCount` hoặc `HeapMemoryUsage.used`. Giảm từ 50 xuống 40 là hợp lệ. Không dùng `rate` trên một gauge rồi suy số sự kiện hoàn tất, trừ khi có mô hình đạo hàm rõ ràng.

### 11.2 Counter

Counter tích lũy như `GarbageCollectorMXBean.getCollectionCount()` hoặc task total. Đọc một số cuối không cho biết rate hiện tại. Phải lấy delta qua hai mẫu **cùng JVM instance**, xử lý reset/restart, giá trị undefined (`-1` với một số MXBeans) và missing samples. Khi chuyển thời gian từ milliseconds sang seconds cho backend, đổi unit đúng và ghi vào metric name/metadata.

Nếu count giảm do restart, không báo “số GC âm”; chia series theo instance/metadata hoặc dùng hàm counter-aware của hệ thống phù hợp. Không gọi một counter cumulative là histogram pause.

### 11.3 Histogram và event data

Nếu cần p95/p99 latency, mỗi lần poll `getAttribute("AverageLatency")` không đủ để tái tạo phân bố. Cần histogram buckets/summary/event-level data được instrument đúng semantics và kiểm soát cardinality labels. Histogram với nhiều buckets **nhân số series**: giả sử mỗi label combination có 12 bucket series cộng count/sum, metric family có thể tạo nhiều series cho mỗi tổ hợp. Kiểm tra model của backend/exporter cụ thể trước khi dự toán.

### 11.4 Type/units phải được chốt

Ví dụ:

- `getCollectionTime()` theo Java API trả **milliseconds**, nhưng metrics convention của Prometheus thường ưu tiên **seconds**.
- Heap dùng bytes; không đặt `_mb` nếu thực tế trả bytes.
- Durations nên có suffix `_seconds` khi chuẩn metrics backend yêu cầu.
- Counter thường dùng `_total` trong Prometheus naming; gauge không nên tùy tiện mang suffix này.
- Java `System.nanoTime()` là clock đo elapsed, không dùng làm timestamp UTC.

Nhầm units có thể gây cảnh báo sai vài nghìn lần mà không liên quan đến kết nối.

## 12. Notification không thay thế một lịch polling đáng tin

Một MBean có thể phát `Notification` khi vượt threshold, nhưng:

- Nó có thể không hỗ trợ loại event bạn cần.
- Có thể phát trước khi bạn subscribe.
- Listener mất kết nối có thể bỏ lỡ event và JMX không bảo đảm replay.
- `NOTIFS_LOST` ở connection layer chỉ cảnh báo có thể mất notifications, không cung cấp toàn bộ event bị mất.
- Callback có thể bị quá tải nếu hàng nghìn events/s; listener cần bounded processing.
- Notification message/userData có thể chứa thông tin nhạy cảm.

Mô hình kết hợp: dùng notification làm **tín hiệu nhanh**, polling chậm để **reconcile trạng thái**, lưu events vào hệ thống được thiết kế cho lịch sử khi cần audit. Nếu event có sequenceNumber, xem đó là thứ tự trong nguồn phát, không phải global ordering cho nhiều JVM.

Đừng biến notification type động hoặc event sequence number thành metric label. Có thể tăng counter `jmx_notifications_total{type="threshold"}` với danh sách type được duyệt; không xuất `sequence_number` dưới dạng label.

## 13. Bài thực hành Java 17+ độc lập: tính budget và đọc attributes cục bộ

Mã demo minh họa hai mục tiêu:

1. **Chế độ mặc định, deterministic:** tính series upper bound, số scrapes/giờ, giới hạn label và backoff theo chính sách giả định. Không kết nối từ xa và không cần workload ngoài.
2. **`--local`, nondeterministic data:** đọc hai attributes từ **platform MBeanServer của JVM demo** để thấy cách dùng `MBeanServerConnection.getAttributes` và phát hiện field bị thiếu. Nó không hỏi một JVM từ xa và không công bố số thread tuyệt đối cố định.

Lưu tệp `JmxMonitoringBudgetDemo.java`:

```java
import java.lang.management.ManagementFactory;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import javax.management.Attribute;
import javax.management.AttributeList;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public class JmxMonitoringBudgetDemo {
    private static final Set<String> ALLOWED_LABEL_KEYS =
            Set.of("service", "environment", "instance", "collector", "status");

    static long product(int... dimensions) {
        long total = 1;
        for (int dimension : dimensions) {
            if (dimension <= 0) {
                throw new IllegalArgumentException("dimension must be positive");
            }
            total = Math.multiplyExact(total, dimension);
        }
        return total;
    }

    static long retryDelaySeconds(int consecutiveFailures) {
        int bounded = Math.min(Math.max(consecutiveFailures, 0), 2);
        return Math.min(60L, 15L << bounded);
    }

    static void showPolicy() {
        int secondsBetweenPolls = 15;
        long baseSeries = product(3, 2, 4, 3, 2);
        long withRequestIds = Math.multiplyExact(baseSeries, 10_000L);

        System.out.println("POLL_INTERVAL_SECONDS=" + secondsBetweenPolls);
        System.out.println("SCRAPES_PER_HOUR=" + 3600 / secondsBetweenPolls);
        System.out.println("BASE_SERIES_UPPER_BOUND=" + baseSeries);
        System.out.println("WITH_10000_REQUEST_IDS=" + withRequestIds);
        System.out.println("REQUEST_ID_ALLOWED="
                + ALLOWED_LABEL_KEYS.contains("request_id"));
        System.out.println("BACKOFF_FAILURE_0_SECONDS=" + retryDelaySeconds(0));
        System.out.println("BACKOFF_FAILURE_1_SECONDS=" + retryDelaySeconds(1));
        System.out.println("BACKOFF_FAILURE_2_SECONDS=" + retryDelaySeconds(2));
        System.out.println("BACKOFF_FAILURE_3_SECONDS=" + retryDelaySeconds(3));
    }

    static void showLocalAttributes() throws Exception {
        MBeanServerConnection connection =
                ManagementFactory.getPlatformMBeanServer();
        ObjectName threading = new ObjectName("java.lang:type=Threading");
        String[] requested = {"ThreadCount", "DaemonThreadCount"};

        AttributeList list = connection.getAttributes(threading, requested);
        Map<String, Object> received = new HashMap<>();
        for (Object entry : list) {
            Attribute attribute = (Attribute) entry;
            received.put(attribute.getName(), attribute.getValue());
        }

        System.out.println("LOCAL_REQUESTED=" + requested.length);
        System.out.println("LOCAL_RETURNED=" + received.size());
        System.out.println("LOCAL_THREAD_COUNT_PRESENT="
                + received.containsKey("ThreadCount"));
        System.out.println("LOCAL_DAEMON_COUNT_PRESENT="
                + received.containsKey("DaemonThreadCount"));
    }

    public static void main(String[] args) throws Exception {
        showPolicy();
        if (args.length == 1 && "--local".equals(args[0])) {
            showLocalAttributes();
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac JmxMonitoringBudgetDemo.java
java JmxMonitoringBudgetDemo
```

**Stdout chính xác của chế độ mặc định:**

```text
POLL_INTERVAL_SECONDS=15
SCRAPES_PER_HOUR=240
BASE_SERIES_UPPER_BOUND=144
WITH_10000_REQUEST_IDS=1440000
REQUEST_ID_ALLOWED=false
BACKOFF_FAILURE_0_SECONDS=15
BACKOFF_FAILURE_1_SECONDS=30
BACKOFF_FAILURE_2_SECONDS=60
BACKOFF_FAILURE_3_SECONDS=60
```

Giải thích:

- 3600/15 = **240** lần lấy mẫu mỗi giờ theo lịch lý thuyết; bỏ qua lỗi, jitter và thời gian xử lý thực.
- 3 services × 2 environments × 4 instances × 3 collectors × 2 states = **144** tổ hợp tối đa.
- Thêm 10.000 request IDs: `144 × 10.000 = 1.440.000` upper bound, nêu rủi ro nếu dùng request ID làm label.
- `ALLOWED_LABEL_KEYS` không chứa `request_id`, nên mã in `false`. Trong hệ thống thật còn cần kiểm soát **giá trị** của labels.
- Backoff sau 0, 1, 2, 3 failures lần lượt 15, 30, 60, 60 giây; đây là mô hình chính sách giả định, **không tự kết nối, không thực hiện retry thật, chưa có jitter**.

Để đọc JMX cục bộ:

```bash
java JmxMonitoringBudgetDemo --local
```

Chương trình in thêm bốn dòng prefix `LOCAL_...`. Dữ liệu có thể phụ thuộc implementation, quyền và JVM; mã **không cố định** số lượng attributes thành công. `ThreadCount` và `DaemonThreadCount` là attributes tiêu chuẩn của `java.lang:type=Threading` trên HotSpot/JDK phù hợp, nhưng cách xử lý list vẫn kiểm tra hiện diện từng trường thay vì tin rằng request hai field sẽ trả đúng hai field.

### 13.1 Học gì từ code và còn thiếu gì ở production?

Code minh họa **budget math, label allowlist và đọc dữ liệu theo tên attribute**, không phải một monitoring agent production. Nó chưa lập lịch, chưa có remote network, authentication/TLS, timeout provider, persistence, Prometheus exposition, reconnect hoặc alert. Cố tình không mở JMX port để bài có thể chạy an toàn trên máy học.

Nếu phát triển thành collector thực, cần bổ sung resource owner quản lý `JMXConnector`, deadline/retries có giới hạn, scheduler không overlap, logging/scrape health, metric schema với đơn vị, test timeout/restart và full integration tests.

### 13.2 Snippet remote lifecycle để đối chiếu

Đoạn method **không phải tệp Java độc lập**; đây là cấu trúc API khi ứng dụng đã có một `JMXServiceURL` được phê duyệt và một `Map<String,?>` chứa cấu hình transport/auth hợp lệ:

```java
import java.util.Map;
import javax.management.MBeanServerConnection;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

static void withAuthorizedConnection(
        JMXServiceURL endpoint,
        Map<String, ?> securedEnvironment) throws Exception {
    try (JMXConnector connector =
                 JMXConnectorFactory.connect(endpoint, securedEnvironment)) {
        MBeanServerConnection connection =
                connector.getMBeanServerConnection();
        // Ở đây mới đọc các ObjectName/attributes được allowlist.
        // Không ghi secret ra log, không gọi operation mutating.
    }
}
```

Không khuyên gọi `connect` lại trên mọi vòng poll; với polling liên tục có thể giữ kết nối trong component có lifecycle rõ. Đoạn code cũng **không** tự cung cấp timeout phổ quát, TLS hay quyền: những điều này phải được cấu hình và kiểm thử cho connector provider thực tế. Không copy snippet rồi mở JMX RMI không xác thực.

## 14. Ví dụ cấu hình chính sách vận hành (không phải cú pháp JMX tiêu chuẩn)

Một file cấu hình cho monitoring service **có thể** có dạng:

```yaml
jmx_monitoring:
  enabled: true
  targets:
    source: "approved-service-discovery"
    maximum_total: 500
  connection:
    mode: "authenticated-tls-only"
    maximum_in_flight_per_target: 1
    maximum_in_flight_global: 40
    reconnect_initial_seconds: 15
    reconnect_cap_seconds: 60
    jitter_max_seconds: 3
  polling:
    cheap_interval_seconds: 15
    metadata_refresh_seconds: 600
    expensive_attributes_enabled: false
    allowed_mbeans:
      - "java.lang:type=Threading"
      - "java.lang:type=Memory"
    allowed_attributes:
      "java.lang:type=Threading": ["ThreadCount", "DaemonThreadCount"]
      "java.lang:type=Memory": ["HeapMemoryUsage"]
  cardinality:
    allowed_label_keys: ["service", "environment", "instance", "pool"]
    reject_label_keys: ["request_id", "user_id", "session_id", "full_url"]
    maximum_series_per_target: 300
    track_series_dropped: true
  quality:
    emit_scrape_success: true
    emit_scrape_duration: true
    emit_last_sample_age: true
```

**Đây là một manifest thiết kế giả định**, không phải configuration format có sẵn của JMX/JConsole/Prometheus/JMX Exporter. Những key và giá trị cụ thể phải được thực thi trong collector mình xây hoặc ánh xạ sang schema của sản phẩm đang sử dụng. Ví dụ `authenticated-tls-only` là **yêu cầu chính sách**, không phải một thiết lập Java có thể bật chỉ bằng dòng YAML.

**Điểm thiết kế đáng chú ý:**

- Giới hạn targets/global in-flight để không tạo bão connection.
- Mỗi target một lượt polling, tránh overlap.
- Metadata refresh thưa hơn data sampling.
- Chỉ hai ObjectNames với một vài attributes được phép.
- Không cho labels động mang định danh người dùng/request.
- Có metric health riêng và theo dõi series bị drop.
- Không dùng generic “poll every MBean, every attribute”.

## 15. Các kịch bản vận hành để kiểm tra chính sách

### 15.1 Một JVM không phản hồi, các JVM còn lại ổn định

**Bối cảnh:** một target có getter chậm, còn 49 targets khác phản hồi. Nếu collector dùng 50 threads mà mỗi target được retry không giới hạn, target lỗi có thể chiếm hết worker/sockets.

**Cách xử lý:** budget per-target, timeout theo provider, circuit breaker/backoff, bounded queue và independent target ownership. Đánh dấu `scrape_success=0` cho target lỗi (nếu exporter contract định nghĩa như vậy), giữ dữ liệu nghiệp vụ thành missing/stale. Không thay queue depth thành 0.

### 15.2 Sau deploy, số active series tăng gấp 20

**Bối cảnh:** team thêm label `exception_message` chứa văn bản lỗi. Mỗi giá trị mới tạo series; số samples/giây ban đầu có thể chưa tăng tương ứng vì một lỗi chỉ tồn tại ngắn.

**Cách xử lý:** kiểm tra schema diff, top labels theo unique values, series churn, metric names mới. Bỏ field nhạy cảm/tự do khỏi labels và thay bằng exception class/category có miền giá trị hữu hạn. Đừng chỉ tăng memory backend để che vấn đề.

### 15.3 Dashboard hiển thị GC counter giảm đột ngột

**Bối cảnh:** collector reconnect đúng lúc JVM restart; `GarbageCollectorMXBean.getCollectionCount()` từ 5.000 về 10. Nếu cùng một time series không có restart marker, dashboard có thể tính negative delta hoặc spike sai.

**Cách xử lý:** theo dõi process/JVM instance, uptime/start time, counter reset và collector identity. Dùng hàm rate counter-aware của backend khi phù hợp; không trực tiếp trừ hai counters của **hai JVM instances** rồi coi kết quả là thật.

### 15.4 Việc giám sát làm tăng CPU hoặc request latency

**Bối cảnh:** remote collector query toàn bộ `queryNames(null,null)` mỗi giây, rồi đọc hàng nghìn attributes.

**Cách xử lý:** xác định expensive getters, giảm discovery cadence, dùng allowlist, batch `getAttributes`, giới hạn concurrency và đo scrape latency. Nếu triệu chứng vẫn còn, profile/tối ưu getter hoặc đổi sang ứng dụng tự xuất metric cheap. **Không tự kết luận JMX API “luôn nặng”**: chi phí phụ thuộc vào bean, transport và tần suất.

### 15.5 Notification giảm sau khi reconnect

**Bối cảnh:** JMX notifications không còn đầy đủ, connector từng phát `NOTIFS_LOST`.

**Cách xử lý:** xác minh resubscribe, kiểm tra filter, target identity, bổ sung polling reconcile. Không coi việc không nhận notification mới là không có sự kiện. Nếu cần event completeness, lưu events vào một hệ thống bền vững chuyên dụng.

### 15.6 Hai exporter cùng scrape một target

**Bối cảnh:** cùng một JVM có hai collectors trên cùng cluster, mỗi collector đều poll 200 attributes/10 giây. Dữ liệu có thể bị gửi lên backend hai lần hoặc tạo labels khác nhau.

**Cách xử lý:** xác định ownership per target/shard, thống nhất metric mapping/labels, deduplicate hợp lệ hoặc giảm số collectors. Đừng tự tin rằng chỉ dùng lock trong một process sẽ ngăn scraper ở process khác.

### 15.7 MBean mỗi session sinh series không giới hạn

**Bối cảnh:** ứng dụng đăng ký ObjectName `com.example:type=Session,id=<session-id>` cho mọi phiên, exporter thu tự động tất cả.

**Cách xử lý:** cân nhắc thay thiết kế MBean registry bằng aggregate metrics theo pool/service, hủy MBean khi session kết thúc, không xuất ID session ra label, và quan sát churn. Quản trị dữ liệu cá nhân cũng cần xử lý vì tên ObjectName có thể làm lộ định danh.

## 16. Checklist trước khi đưa JMX monitoring lên production

- [ ] Đã xác minh đúng JVM instance, endpoint, ObjectName và các attributes cần đo.
- [ ] Remote JMX chỉ mở trong phạm vi được phép, có TLS/authentication/authorization và phân tách read-only/mutating.
- [ ] Connector có owner, lifecycle, cleanup/close và reconnect được thiết kế rõ.
- [ ] Timeout của transport/provider được kiểm chứng, không dùng property chưa xác nhận.
- [ ] Có giới hạn in-flight per target/global và không cho nhiều scrape chồng lấn.
- [ ] Polling interval dựa trên mục tiêu quan sát, chi phí getter và độ dài sự kiện muốn phát hiện.
- [ ] Có jitter/backoff và retry budget, tránh thundering herd.
- [ ] Cho phép `getAttributes` batching khi hợp lý, nhưng kiểm tra field bị thiếu và consistency.
- [ ] Discover `queryNames`/`MBeanInfo` có giới hạn phạm vi, tần suất, TTL và invalidation sau redeploy.
- [ ] Metrics phân biệt gauge/counter/histogram; units và reset logic được ghi rõ.
- [ ] Missing data không bị thay bằng 0; có scrape health và last sample age.
- [ ] Đã tính upper-bound label combinations, actual active series và churn budget.
- [ ] Không có `request_id`, `user_id`, email, token, URL có ID, dynamic ObjectName hoặc connection ID trong metric labels.
- [ ] Labels được kiểm tra cả key **và miền giá trị**, không chỉ tên.
- [ ] Có hành động rõ khi vượt cardinality limit và số liệu drop được công bố.
- [ ] Không suy p99 từ attribute trung bình, không gọi GC collection time là CPU %.
- [ ] JMX notifications có cơ chế resubscribe/reconciliation, không được xem là event store bền vững.
- [ ] Đã thử các trường hợp target down, auth fail, timeout, restart, deploy, scale-out và exporter duplicated.
- [ ] Có tài liệu vận hành để đánh giá collector overhead, số connection, worker queue, latency và lượng series.
- [ ] Đầu ra JMX/metadata/labels được xử lý phù hợp quyền riêng tư và retention.

## 17. Bài tập tự kiểm tra

**Câu 1.** Một collector poll 60 JVM, mỗi JVM bốn MBeans, mỗi bean ba attributes, cứ 15 giây. Nếu gọi từng attribute riêng, lượng đọc trung bình bao nhiêu?

**Đáp án:** 60 × 4 × 3 = 720 attribute reads/cycle, tương đương 48 reads/giây và 172.800 reads/giờ theo lịch lý thuyết. Nếu batch `getAttributes` theo từng bean, số remote calls có thể giảm về 240/cycle, nhưng JVM vẫn phải đọc các giá trị, và có thể có field thiếu.

**Câu 2.** Tại sao không dùng `JMXConnector.getConnectionId()` làm metric label?

**Đáp án:** Connection ID thay qua reconnect, tạo series churn không phản ánh thay đổi service. Dùng target/JVM instance identity ổn định hơn; giữ connection ID trong log điều tra hạn chế quyền.

**Câu 3.** `getAttributes` được yêu cầu năm fields nhưng trả bốn. Có thể coi field thứ năm là 0 không?

**Đáp án:** Không. API có thể bỏ thuộc tính không lấy được. Phải đối chiếu tên field nhận, ghi missing và kiểm tra lỗi bằng `getAttribute` riêng nếu cần.

**Câu 4.** Mỗi request mới tạo một `ObjectName` với `request_id`. Đây là rủi ro gì?

**Đáp án:** Registry/MBean count tăng, MBean lifecycle phức tạp và nếu exporter biến request ID thành label sẽ gây cardinality/churn rất lớn. Nên dùng aggregate MBean và tracing riêng cho từng request.

**Câu 5.** Một vòng poll mất 20 giây trong khi interval đặt 10 giây. Điều gì cần thay đổi?

**Đáp án:** Tránh overlap, đặt deadline/giới hạn concurrent work, xem expensive getter hoặc giảm tốc độ/đổi scope. Không mở vô hạn threads để giữ “đúng lịch”.

**Câu 6.** Một metric có 3 services × 2 environments × 4 instances × 3 collector types × 2 states. Upper bound là bao nhiêu?

**Đáp án:** 144 series cho metric đó. Thêm 10.000 request IDs có thể tạo upper bound 1.440.000; đây là rủi ro thiết kế, không nhất thiết mọi tổ hợp đều hiện hữu.

**Câu 7.** Khi JVM mất kết nối trong một lượt, biểu đồ queue depth có được ghi 0 không?

**Đáp án:** Không, 0 biểu thị giá trị nghiệp vụ. Phải ghi missing/stale và trạng thái scrape failure riêng. Khi khôi phục, không tính delta giả từ 0.

**Câu 8.** Vì sao `Future.cancel(true)` không là biện pháp timeout đủ cho mọi remote JMX request?

**Đáp án:** Interrupt có thể không làm transport/provider blocking I/O dừng ngay. Cần timeout đúng provider, connection lifecycle có kiểm soát và bounded worker/thread resources.

**Câu 9.** Đã có JMX notifications rồi có cần polling nữa không?

**Đáp án:** Tùy yêu cầu; notifications không bảo đảm persistence/replay và có thể mất khi reconnect. Polling đối soát trạng thái giúp phát hiện event miss, còn hệ thống lưu event phải dùng nếu cần lịch sử đầy đủ.

**Câu 10.** Đặt poll interval 1 giây thay 15 giây có giải quyết được p99 request latency không?

**Đáp án:** Không tự động. Một snapshot mỗi giây không tái tạo phân bố request latency và có thể tăng overhead. Cần histogram/event trace và chọn cadence theo câu hỏi chẩn đoán.

## Tài liệu tham khảo

- [Java SE 21 — JMXConnector](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXConnector.html): kết nối, `close()`, listener và connection ID.
- [Java SE 21 — JMXConnectorFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXConnectorFactory.html): tạo connector, `connect`, provider/environment.
- [Java SE 21 — MBeanServerConnection](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html): `getAttribute`, `getAttributes`, query và các trường hợp bỏ field.
- [Java SE 21 — JMXConnectionNotification](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXConnectionNotification.html): opened, closed, failed, notifications lost.
- [Java SE 21 — ManagementFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html): platform MBeanServer và MXBeans.
- [Java SE 21 — ScheduledThreadPoolExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html): periodic tasks, scheduling và concurrency semantics.
- [Prometheus — Metric and Label Naming](https://prometheus.io/docs/practices/naming/): một tập labels tạo một time series; không dùng unbounded identifiers.
- [Prometheus — The Zen of Prometheus](https://prometheus.io/docs/practices/the_zen/): series cardinality, nhãn và metric instrumentation.

**Ghi nhớ:** quản lý JMX monitoring là bài toán **hạn chế tài nguyên và bảo toàn ý nghĩa dữ liệu**. Tái sử dụng kết nối có lifecycle và security, timeout/retry đúng provider, không poll chồng, đo đúng elapsed window, chọn attributes bằng allowlist và giới hạn label cardinality ngay tại nguồn. Một hệ thống “thu được mọi số” nhưng làm JVM chậm, phát hàng triệu series hoặc thay missing thành 0 **không phải** hệ thống giám sát đáng tin.