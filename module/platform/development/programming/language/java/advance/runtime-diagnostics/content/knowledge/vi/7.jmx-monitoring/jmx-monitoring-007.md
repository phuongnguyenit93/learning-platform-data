# 7.7 Xuất MBean cho chỉ số riêng của ứng dụng với kiểu dữ liệu phù hợp

## Mục tiêu học tập

JMX (Java Management Extensions) không chỉ cung cấp số liệu của JVM như heap, GC hoặc threads. Một dịch vụ Java có thể **đăng ký MBean do ứng dụng sở hữu** để công cụ quản trị quan sát số request đã hoàn tất, số request lỗi, backlog, số công việc đang xử lý, tình trạng sức khỏe hay trạng thái của một thành phần nghiệp vụ.

Điểm khó không nằm ở việc viết một getter trả về số nguyên; điểm khó là **xuất đúng ngữ nghĩa và kiểu dữ liệu**, tránh số đếm sai khi nhiều threads cập nhật, không gây tải lớn mỗi lần client poll và không để MBean quản trị vô tình mở quyền thay đổi runtime.

Sau bài học, bạn có thể:

- Phân biệt **Standard MBean**, **MXBean** và **Dynamic MBean**, chọn giải pháp phù hợp cho Java 17.
- Thiết kế các JMX attributes với kiểu dữ liệu có ý nghĩa: `long` counter, `int`/`long` gauge, `double` ratio, `boolean` health flag, `String` trạng thái hữu hạn.
- Hiểu khi nào nên công bố một snapshot bằng **Open Types**, `CompositeData` hoặc `TabularData`, thay vì truyền object Java riêng qua JMX.
- Tạo Standard MBean **chỉ đọc** bằng interface `*MBean`, `StandardMBean`, `MBeanServer` và `ObjectName`.
- Xác minh tên/kiểu và quyền đọc/ghi thực sự bằng `getAttribute()` và `getMBeanInfo()`.
- Cập nhật counters, gauges an toàn giữa nhiều threads; giải thích giới hạn của các getter được đọc ở thời điểm khác nhau.
- Chạy chương trình Java 17 độc lập, có stdout xác định và chế độ giữ JVM sống để quan sát bằng JConsole local.
- Viết đặc tả metrics với units, reset semantics, scope, cardinality, sampling window, bảo mật và cách tổng hợp qua replicas.

## 1. MBean là gì, tại sao ứng dụng cần MBean riêng?

Một **Managed Bean (MBean)** là Java object mà giao diện quản trị được công bố qua **MBeanServer**. Client có quyền truy cập có thể đọc thuộc tính, gọi operation được công bố và đôi khi nhận notification. MBean không bắt buộc phải là JavaBean theo nghĩa thông thường; nó tuân theo quy ước và metadata của JMX.

```text
Application / Java service
  ├── Business requests and background jobs
  │     └── cập nhật counters/gauges của component
  ├── Metrics implementation
  └── Management interface (MBean/MXBean)
                 │
                 v
        Platform MBeanServer
                 │
     ObjectName duy nhất trong JVM
                 │
        ┌────────┴─────────┐
        v                  v
     JConsole        JMX connector/exporter
                      → monitoring system
```

**Điều MBean cung cấp:**

- **Attribute:** giá trị được đặt tên và có kiểu; getter `getRequestsTotal()` xuất thuộc tính `RequestsTotal`.
- **Operation:** hành động công bố để client gọi; ví dụ `resetCache()` nếu và chỉ nếu bạn thật sự chủ động expose.
- **Notification:** sự kiện đẩy tới listener theo cơ chế JMX.
- **Metadata:** `MBeanInfo` mô tả tên, kiểu, khả năng đọc/ghi, operation và những thông tin khác.

Đối với metrics chỉ quan sát, **interface chỉ nên chứa getters**. Không thêm setter/operation có side effect vào MBean đo lường chỉ để tiện thao tác. Một MBean riêng cho ứng dụng là một phần của **hợp đồng vận hành**: dashboard có thể dựa vào tên attribute, ObjectName và kiểu dữ liệu trong nhiều lần triển khai.

**Phạm vi quan trọng:** mỗi JVM có một platform MBeanServer riêng; `RequestsTotal` trong replica A là counter của **replica A**, không tự động là tổng request của cả cluster. Khi nhân nhiều replicas, hệ thống giám sát phải có identity của instance và quy tắc tổng hợp.

## 2. Chọn Standard MBean, MXBean hay Dynamic MBean?

| Loại | Mô hình | Lợi ích | Khi phù hợp |
| --- | --- | --- | --- |
| Standard MBean | Interface public có hậu tố `MBean`, getters/setters và operations theo JMX conventions | Đơn giản, schema dễ đọc và test | Metrics cơ bản có kiểu primitive/String |
| MXBean | Interface public có hậu tố `MXBean` hoặc `@MXBean`; giá trị được map sang Open Types | Client không cần class dữ liệu riêng của ứng dụng | Snapshot nhiều trường, cấu trúc/map/list được hỗ trợ |
| Dynamic MBean | Tự triển khai `DynamicMBean` và metadata/attribute access | Linh hoạt khi schema thật sự động | Framework, công cụ chẩn đoán tự xây |
| `StandardMBean` wrapper | Dùng `StandardMBean(implementation, interfaceClass, false)` cho Standard MBean | Expose chính xác interface được chọn, không phụ thuộc tên class implementation | Một file demo, implementation không trùng naming convention |

**Standard MBean mặc định:** theo JMX conventions, class `CheckoutMetrics` implement interface public `CheckoutMetricsMBean`. Một `boolean isHealthy()` là attribute tên `Healthy`; `long getRequestsTotal()` là attribute tên `RequestsTotal`.

Trong ví dụ bài này dùng `StandardMBean(..., false)` để chỉ rõ phần nào là **giao diện quản trị**. Tham số `false` ở đây có nghĩa **không tạo MXBean**. JDK cũng cho phép `StandardMBean(..., true)` khi muốn tạo MXBean với interface đáp ứng quy tắc tương ứng.

**Không cần Dynamic MBean** chỉ để trả một counter và một ratio. Tự quản lý `MBeanInfo`/`getAttribute` động gây thêm độ phức tạp, dễ lệch kiểu hoặc không nhất quán schema.

## 3. Chọn kiểu dữ liệu phù hợp với phép đo

| Metric | Loại đại lượng | Java/JMX type | Định nghĩa và đơn vị |
| --- | --- | --- | --- |
| Requests đã hoàn tất | Counter tích lũy | `long` | Số lần; từ lúc instance bắt đầu |
| Requests lỗi đã hoàn tất | Counter tích lũy | `long` | Số lần; định nghĩa failure rõ |
| Request đang xử lý | Gauge tức thời | `int` hoặc `long` | Số request hiện tại |
| Tác vụ đang chờ | Gauge tức thời | `int`/`long` | Queue depth, đo tại thời điểm đọc |
| Error ratio | Ratio | `double` | Fraction từ 0 đến 1 |
| Utilization ratio | Ratio | `double` | Fraction 0–1, mẫu số phải rõ |
| Có đạt health criteria? | Boolean | `boolean` | `true`/`false` |
| Lifecycle state | Giá trị phân loại | `String` | Tập hữu hạn: `STARTING`, `RUNNING`, `DRAINING`... |
| Lần thành công gần nhất | Timestamp | `long` | Unix epoch milliseconds |
| Tổng queue wait time | Duration accumulator | `long` | Nanoseconds hoặc milliseconds có ghi rõ |
| Latency p95 | Quantile từ snapshot | `double` | Milliseconds, **phải** có window và sample count |

### 3.1 Counter: dùng `long` cho số lượng tích lũy

Counter được tăng theo một sự kiện đã định và **không giảm** trong một vòng đời instance thông thường. `RequestsTotal` không phải RPS; cần **chênh lệch của hai mẫu**:

```text
Rate(T1,T2) =
  (RequestsTotal(T2) - RequestsTotal(T1)) / elapsedSeconds
```

Ví dụ một JVM hoàn tất 240 request trong 30 giây thì rate trung bình trong cửa sổ là **8 requests/giây**, miễn counter chưa reset. Nếu JVM restart trong cửa sổ, phải nhận diện reset và không lấy delta âm làm tốc độ xử lý.

`long` giúp tránh giới hạn nhỏ của `int` đối với service chạy lâu. Không dùng `double` cho số lượng chính xác chỉ vì dashboard thích số thực; số nguyên lớn có thể mất độ chính xác biểu diễn bằng floating point.

Một counter cần hợp đồng rõ:

- “RequestsTotal” đếm request **đã bắt đầu**, **đã nhận**, hay **đã hoàn tất**?
- Có tính retry là một request riêng không?
- “FailuresTotal” gồm 5xx, timeout, validation/business failure hay exception chưa bắt?
- Cả hai có cùng phạm vi instance/lifecycle không?

Tên đẹp mà không có định nghĩa vẫn là metric không đáng tin.

### 3.2 Gauge: giá trị có thể tăng và giảm

`InFlight` là số request đang chạy; nó không phải counter lifetime.

```text
T1 InFlight=5
T2 InFlight=17
T3 InFlight=2
```

Các giá trị đều hợp lệ. Gauge phải tăng khi bắt đầu và **giảm chính xác một lần** khi xử lý kết thúc, kể cả khi xảy ra exception/cancellation/timeout. Một đường `finally` phù hợp thường giúp chống quên decrement.

`QueueDepth` cần đọc từ cơ chế queue thực. Một queue báo `size()` không nhất thiết snapshot tuyệt đối chính xác khi concurrent modifications; định nghĩa của queue/JDK implementation cần được xem. Không gọi API duyệt hàng triệu phần tử trong getter chỉ để có queue size.

### 3.3 Ratio: `double` với mẫu số rõ ràng

Đối với hợp đồng **completed requests**, ratio tích lũy:

```text
RequestsTotal = 300
FailuresTotal = 9
ErrorRatio = 9 / 300 = 0.03 = 3%
```

`0.03` trong `ErrorRatio` là **3%**, không phải **0,03%**. Nếu muốn giá trị 3.0, hãy đặt tên `ErrorPercent` và tài liệu hóa 0–100; không dùng lẫn cả hai.

Với mẫu số bằng 0, quyết định và công bố chính sách no-data. Demo Java bên dưới trả `0.0` khi chưa có completed request, nhưng nghĩa là **“chưa có lỗi được ghi nhận” theo quy ước demo**, không chứng minh hệ thống healthy. Trong hệ thống phân tích có thể cần `HasSamples` hoặc metadata về sample count.

`NaN` và infinity có thể làm một số JMX client, exporter hoặc time-series pipeline khó xử lý; tránh dùng tùy tiện để biểu diễn no-data.

### 3.4 Boolean và String: đừng biến thành text/numeric mơ hồ

`boolean isHealthy()` tạo attribute tên `Healthy` có kiểu Boolean ở JMX. Trả `String "true"` khiến client phải parse và dễ không tương thích. Trả `int 0/1` chỉ phù hợp nếu hợp đồng chủ động định nghĩa mã số; đừng tự thay hai trạng thái rõ ràng thành number.

`String getState()` phù hợp với tập trạng thái hữu hạn. Tránh chứa stack trace, thông tin cá nhân, request ID, token hoặc arbitrary error message trong một String attribute. Dữ liệu đó nên đi vào logs/traces với quản lý quyền truy cập riêng.

Một Boolean `Healthy=true` **không tự chứng minh** endpoint trả lời nhanh; phải ghi chính xác tiêu chí health, ví dụ “component đã tải config, kết nối phụ thuộc thiết yếu sẵn sàng, còn nhận task mới”.

### 3.5 Timestamp và duration không cùng loại

- `LastSuccessEpochMillis`: `long` số milliseconds kể từ Unix epoch; dùng để ghép timeline giữa hệ thống.
- `QueueWaitNanosTotal`: `long` nanoseconds tích lũy; phục vụ delta và average khi có counter số task tương ứng.
- `System.nanoTime()`: thích hợp đo **elapsed delta trong một JVM**, không phải UTC epoch timestamp.
- Không trả `String "23 ms"` nếu người dùng cần dashboard tính toán; trả số và khai báo unit ở tên/tài liệu.

## 4. Thiết kế một hợp đồng metrics trước khi code

Ví dụ quản lý thành phần checkout:

| Attribute | Kiểu | Loại | Đơn vị | Quy tắc |
| --- | --- | --- | --- | --- |
| `RequestsTotal` | `long` | Counter | requests | Tăng một lần khi request hoàn tất |
| `FailuresTotal` | `long` | Counter | requests | Tăng cho một request thất bại đã hoàn tất |
| `InFlight` | `int` | Gauge | requests | Tăng lúc bắt đầu, giảm khi kết thúc |
| `ErrorRatio` | `double` | Ratio | fraction 0–1 | `FailuresTotal / RequestsTotal`, khi mẫu số 0 trả 0 |
| `Healthy` | `boolean` | State | — | Tiêu chí readiness/health đã định |
| `State` | `String` | State | enum-like | `STARTING`, `RUNNING`, `DRAINING`, `STOPPED` |

Ở cấp hợp đồng cần ghi thêm: owner, dữ liệu được cập nhật từ đâu, thread-safety, reset policy, thang thời gian và ý nghĩa khi thiếu dữ liệu. Chỉ số p95/p99 riêng nên có **window** và phương pháp ước lượng. Nếu không có dữ liệu phân phối phù hợp, không đưa một số p95 giả vào JMX.

Một điểm quan trọng: mỗi getter có thể được gọi độc lập bởi client JMX. Đừng mặc định `ErrorRatio` tính từ đúng **cùng snapshot nguyên tử** của `RequestsTotal` và `FailuresTotal` đã được đọc trước đó trong khi nhiều requests vẫn đang hoàn tất.

## 5. Đặt ObjectName rõ ràng và có cardinality hữu hạn

Mọi MBean được đăng ký dưới một `javax.management.ObjectName`. Dạng phổ biến:

```text
domain:key1=value1,key2=value2
```

Ví dụ:

```text
demo.metrics:type=Checkout,name=Primary
```

Code:

```java
ObjectName name = new ObjectName(
        "demo.metrics:type=Checkout,name=Primary");
```

Đây là đoạn mã minh họa bên trong phương thức có xử lý `MalformedObjectNameException`. Với JVM của một dịch vụ thật, domain có thể do tổ chức sở hữu, chẳng hạn `com.example.app.metrics`.

**Không sử dụng các giá trị không giới hạn** trong ObjectName:

- Không tạo MBean cho từng request/session/order/user.
- Không dùng email/khách hàng/trace ID làm `name=...`.
- Không sinh key/value từ URL chứa ID động mà không chuẩn hóa.
- Không cho dữ liệu tùy ý chứa `,`, `=`, `:`, `*`, `?` vào ObjectName bằng cách nối chuỗi chưa kiểm tra.

`ObjectName.quote(value)` giúp quote **giá trị key property** có ký tự đặc biệt; nó không thay thế kiểm soát cardinality và yêu cầu không lộ PII. `ObjectName` có cả giá trị được quote và unquoted với quy tắc cú pháp riêng.

Một schema có thể dùng:

```text
com.example.app.metrics:type=WorkerPool,name=Payments
com.example.app.metrics:type=Cache,name=Products
com.example.app.metrics:type=Queue,name=Invoices
```

Tên ổn định qua rollout giúp dashboard query bền vững. Một `ObjectName` có thể xuất hiện ở nhiều JVM khác nhau: identity toàn cluster phải kết hợp **service/instance/pod** từ monitoring.

MBeanServer yêu cầu **ObjectName duy nhất trong mỗi server**. Khi trùng, `registerMBean` có thể báo `InstanceAlreadyExistsException`. Không tự hủy bean của thành phần khác để “giành tên”.

## 6. Standard MBean read-only: getters và interface

Một interface quản trị đơn giản:

```java
public interface CheckoutMetricsMBean {
    long getRequestsTotal();
    long getFailuresTotal();
    int getInFlight();
    double getErrorRatio();
    boolean isHealthy();
    String getState();
}
```

Đây là **đoạn giao diện minh họa**; chương trình độc lập ở phần 9 khai báo interface tương đương bên trong class public.

Với JMX:

- `getRequestsTotal()` → attribute `RequestsTotal`, kiểu `long`.
- `getInFlight()` → attribute `InFlight`, kiểu `int`.
- `getErrorRatio()` → attribute `ErrorRatio`, kiểu `double`.
- `isHealthy()` → attribute `Healthy`, kiểu `boolean`.
- `getState()` → attribute `State`, kiểu `java.lang.String`.
- **Không có setters tương ứng:** các attribute **chỉ đọc**.

Nếu viết thêm `void resetAllCounters()` **trong management interface**, JMX có thể expose nó như **operation**, dù tác giả nghĩ đó chỉ là helper. Vì mục tiêu hiện tại là metrics, không đưa operation có side effect vào interface quan sát.

Việc không có setter trong MBean riêng giảm bề mặt điều khiển, nhưng **không bảo đảm JMX remote tổng thể chỉ đọc**: platform MBeanServer còn có thể chứa nhiều MBeans khác với operations thay đổi trạng thái. Bảo mật connector vẫn phải được quản lý riêng.

## 7. Thread-safety và những gì getter được phép làm

Một Java service thường xử lý request đồng thời. Nếu nhiều thread cùng gọi `requestsTotal++` trên một field thông thường mà không có đồng bộ phù hợp, có thể **mất update**. Nếu một thread ghi state mà thread khác đọc không có visibility bảo đảm, getter có thể thấy dữ liệu cũ.

Các lựa chọn phổ biến:

- `AtomicLong`: counter tích lũy có `incrementAndGet`, `get`.
- `AtomicInteger`: gauge có phép tăng/giảm thread-safe.
- `LongAdder`: counter tăng nhiều từ nhiều threads với contention cao, nhưng `sum()` **không phải snapshot nguyên tử** khi còn cập nhật.
- `volatile boolean`/`volatile String`: công bố trạng thái mới giữa các threads theo Java Memory Model.
- `AtomicReference<ImmutableSnapshot>`: khi nhiều trường **phải nhất quán cùng nhau**.
- Lock có thời gian giữ rất ngắn: có thể dùng khi bảo đảm invariant phức tạp, tránh khóa kéo dài trong JMX getter.

### 7.1 Vòng đời request cần cặp begin/finish

Một đoạn mã tích hợp (biến `failed` phải được khởi tạo trước `try`):

```java
metrics.beginRequest();
boolean failed = false;
try {
    // Gọi logic xử lý request.
} catch (RuntimeException ex) {
    failed = true;
    throw ex;
} finally {
    metrics.finishRequest(failed);
}
```

Thực tế, lỗi HTTP, timeout hoặc cancellation có thể không đi qua chính `catch` này; phải chọn nơi đặt `finishRequest` và phân loại failure phù hợp với framework/lifecycle. Cũng cần bảo đảm không có đường code nào gọi finish **hai lần**, gây InFlight âm.

### 7.2 Nhiều getters không tạo snapshot chung

Ví dụ trong khi worker vẫn chạy:

```text
T1: client đọc RequestsTotal = 100
T2: vài request hoàn tất, trong đó có lỗi
T3: client đọc FailuresTotal = 11
T4: client đọc ErrorRatio = 0.101
```

Các số không nhất thiết khớp khi tự chia giá trị lấy ở những thời điểm khác nhau. Một bulk `getAttributes()` cũng không mặc nhiên bảo đảm tính nguyên tử giữa getters.

Nếu một báo cáo cần bộ số nhất quán, tạo snapshot bất biến được công bố theo cơ chế đồng bộ phù hợp rồi expose một attribute tổng hợp qua MXBean/Open Type. Nếu chỉ cần monitoring xu hướng, đọc counters độc lập theo cùng cửa sổ thường đủ.

**Đừng** giữ một lock toàn service để JMX client có thể đọc mọi thuộc tính “thật nhất quán”: khóa nặng có thể làm tăng chính request latency đang điều tra.

### 7.3 Getter JMX phải nhẹ, không có side effect

Tránh một getter thực hiện:

```java
// KHÔNG đưa các tác vụ này vào getter polling định kỳ:
// 1. Quét tất cả objects trong heap để tính histogram.
// 2. Truy vấn database/network để đếm dữ liệu mỗi lần poll.
// 3. Sort hàng triệu latency samples để tính p99.
// 4. Ghi file log lớn, reset counters hoặc thay trạng thái component.
```

Thay vào đó, cập nhật metrics trong đường xử lý hoặc snapshot định kỳ có budget rõ. JMX getter chỉ đọc giá trị đã chuẩn bị. Định nghĩa rõ độ trễ cập nhật nếu snapshot không hoàn toàn tức thời.

## 8. MBeanServer, metadata và lifecycle

Lấy server chung của JVM:

```java
MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();
```

Đăng ký:

```java
StandardMBean bean = new StandardMBean(
        metrics, CheckoutMetricsMBean.class, false);
server.registerMBean(bean, objectName);
```

Đây là các đoạn mã tích hợp; các tên `metrics`, `objectName` và import được cung cấp trong ví dụ hoàn chỉnh bên dưới.

Sau khi đăng ký, client có thể đọc:

```java
Object value = server.getAttribute(objectName, "RequestsTotal");
MBeanInfo info = server.getMBeanInfo(objectName);
```

**Kiểm tra bằng metadata thật:**

- `MBeanAttributeInfo.getName()`: tên attribute.
- `getType()`: kiểu được công bố.
- `isReadable()`: có thể đọc.
- `isWritable()`: có thể ghi.
- `MBeanInfo.getOperations()`: các operation được công bố.

Đừng đọc tên từ Java implementation class rồi suy mọi method đều expose; quản lý interface mới quyết định phần lớn schema cho Standard MBean.

Khi component kết thúc, `server.unregisterMBean(objectName)` giúp dọn registry. Trong ứng dụng có component restart/reload, nên quản lý owner và không unregister một bean đã được thay bằng owner khác một cách mù quáng. Một bean giữ tham chiếu tới đối tượng trạng thái cũ có thể gây số liệu stale và ảnh hưởng memory.

## 9. Ví dụ Java 17 hoàn chỉnh: Standard MBean chỉ đọc

Chương trình dưới đây:

1. Định nghĩa public management interface gồm sáu getters có kiểu rõ.
2. Dùng `AtomicLong`, `AtomicInteger` để cập nhật các metrics từ một tình huống mô phỏng.
3. Đăng ký bằng `StandardMBean` với interface được chọn tường minh.
4. Đọc attributes qua `MBeanServer` (không chỉ gọi trực tiếp implementation).
5. Kiểm tra metadata để xác nhận đúng sáu attributes và **không writable**.
6. Hủy đăng ký qua `finally`.
7. Có chế độ `serve` giữ JVM sống khoảng 60 giây để quan sát bằng JConsole local.

Tạo file **`AppJmxMetricsDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.util.Arrays;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.StandardMBean;

public class AppJmxMetricsDemo {
    public interface CheckoutMetricsMBean {
        long getRequestsTotal();
        long getFailuresTotal();
        int getInFlight();
        double getErrorRatio();
        boolean isHealthy();
        String getState();
    }

    public static final class CheckoutMetrics
            implements CheckoutMetricsMBean {
        private final AtomicLong completed = new AtomicLong();
        private final AtomicLong failed = new AtomicLong();
        private final AtomicInteger inFlight = new AtomicInteger();
        private volatile boolean healthy = true;
        private volatile String state = "RUNNING";

        // Cập nhật nội bộ, không expose như JMX operations.
        void beginRequest() {
            inFlight.incrementAndGet();
        }

        void finishRequest(boolean requestFailed) {
            completed.incrementAndGet();
            if (requestFailed) {
                failed.incrementAndGet();
            }
            inFlight.decrementAndGet();
        }

        @Override
        public long getRequestsTotal() {
            return completed.get();
        }

        @Override
        public long getFailuresTotal() {
            return failed.get();
        }

        @Override
        public int getInFlight() {
            return inFlight.get();
        }

        @Override
        public double getErrorRatio() {
            long total = completed.get();
            return total == 0 ? 0.0
                    : (double) failed.get() / total;
        }

        @Override
        public boolean isHealthy() {
            return healthy;
        }

        @Override
        public String getState() {
            return state;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length > 1 ||
                (args.length == 1 && !args[0].equals("serve"))) {
            System.out.println(
                    "Usage: java AppJmxMetricsDemo [serve]");
            return;
        }

        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
                "demo.metrics:type=Checkout,name=Primary");

        CheckoutMetrics metrics = new CheckoutMetrics();
        StandardMBean bean = new StandardMBean(
                metrics, CheckoutMetricsMBean.class, false);

        server.registerMBean(bean, name);
        try {
            metrics.beginRequest();
            metrics.finishRequest(false);

            metrics.beginRequest();
            metrics.finishRequest(true);

            metrics.beginRequest();
            metrics.finishRequest(false);

            System.out.println("registered="
                    + server.isRegistered(name));
            System.out.println("requestsTotal="
                    + server.getAttribute(name, "RequestsTotal"));
            System.out.println("failuresTotal="
                    + server.getAttribute(name, "FailuresTotal"));
            System.out.println("inFlight="
                    + server.getAttribute(name, "InFlight"));

            double errorRatio = (Double) server.getAttribute(
                    name, "ErrorRatio");
            System.out.printf(Locale.ROOT,
                    "errorRatio=%.4f%n", errorRatio);

            System.out.println("healthy="
                    + server.getAttribute(name, "Healthy"));
            System.out.println("state="
                    + server.getAttribute(name, "State"));

            MBeanInfo info = server.getMBeanInfo(name);
            MBeanAttributeInfo[] attrs = info.getAttributes();
            boolean allReadOnly = Arrays.stream(attrs)
                    .allMatch(a -> a.isReadable() && !a.isWritable());

            System.out.println("attributeCount=" + attrs.length);
            System.out.println("allReadOnly=" + allReadOnly);

            if (args.length == 1) {
                System.out.println("localPid="
                        + ProcessHandle.current().pid());
                Thread.sleep(60_000L);
            }
        } finally {
            server.unregisterMBean(name);
        }
        System.out.println("unregistered="
                + !server.isRegistered(name));
    }
}
```

Biên dịch và chạy:

```bash
javac AppJmxMetricsDemo.java
java AppJmxMetricsDemo
```

Stdout **chính xác** của chế độ không có argument trên JVM Java 17 có JMX chuẩn:

```text
registered=true
requestsTotal=3
failuresTotal=1
inFlight=0
errorRatio=0.3333
healthy=true
state=RUNNING
attributeCount=6
allReadOnly=true
unregistered=true
```

**Giải thích kết quả:**

- MBean được đăng ký và `server.isRegistered(name)` trả `true`.
- Ba cặp `beginRequest()`/`finishRequest()` làm `RequestsTotal=3`, `FailuresTotal=1`, `InFlight=0`.
- `ErrorRatio=1/3` được format bằng `Locale.ROOT` thành `0.3333`; JMX vẫn trả kiểu `double`.
- `isHealthy()` tạo `Healthy=true`; trạng thái ví dụ là `RUNNING`.
- Interface có sáu getters, không có setters nên sáu JMX attributes đều read-only.
- `unregisterMBean` chạy trong `finally`; sau đó `isRegistered(name)` trả `false`.

**Quan trọng:** demo mô phỏng ba request **tuần tự** để stdout ổn định; nó không tự chứng minh invariants vẫn đúng dưới mọi race của production. `healthy=true` là trạng thái demo được khởi tạo, không phải health check thực.

### 9.1 Quan sát live bằng JConsole local

Chạy:

```bash
java AppJmxMetricsDemo serve
```

Chế độ này in thêm `localPid=<PID>` rồi giữ JVM sống khoảng **60 giây**. Trong cửa sổ đó, mở công cụ JConsole có trong JDK desktop:

```bash
jconsole
```

Chọn local Java process có PID vừa in, tìm trong cây MBeans tên:

```text
demo.metrics:type=Checkout,name=Primary
```

Mỗi phiên bản UI có thể nhóm `type`/`name` khác nhau; tìm theo **ObjectName** và xác minh sáu attributes, kiểu và trạng thái read-only. Không cần mở remote JMX port chỉ để làm lab này.

Chế độ `serve` không có stdout cố định vì PID và thời gian chạy phụ thuộc máy. Nếu attach thất bại, kiểm tra JDK tools, quyền OS, process còn sống và cơ chế local monitoring; không kết luận “service không có MBean” chỉ từ một lỗi attach.

### 9.2 Vì sao client dùng MBeanServer thay vì gọi implementation trực tiếp?

Một client JMX remote không có tham chiếu Java tới object `CheckoutMetrics` bên trong JVM khác. Nó sử dụng **ObjectName** với `MBeanServerConnection` hoặc proxy. Các kiểu primitive/String được JMX và Java client hỗ trợ tốt.

Client đọc `RequestsTotal` từ MBeanServer nhận giá trị được boxing thành `Long` tương ứng với Java `long`. Hợp đồng metric không nên dựa vào các class nội bộ không có trên máy client.

### 9.3 Nếu đăng ký gặp lỗi?

- `InstanceAlreadyExistsException`: ObjectName đã tồn tại trong cùng server.
- `NotCompliantMBeanException`: đối tượng/interface không đúng quy ước JMX.
- `MBeanRegistrationException`: lỗi trong quá trình lifecycle registration.
- `MalformedObjectNameException`: cú pháp ObjectName không hợp lệ (khi tạo `ObjectName`).

Không tự động xóa bean trùng tên của một component khác. Trong service thật, handle lỗi startup có thông tin context và ownership rõ; hủy đăng ký bean do **chính mình** đăng ký khi component đóng.

## 10. Khi nào cần MXBean và Open Types?

Nếu cần expose dữ liệu nhiều trường để client không có class model riêng vẫn đọc được, **MXBean** hữu ích vì các kiểu Java được hỗ trợ sẽ ánh xạ tới **JMX Open Types**.

Ví dụ contract **mang tính minh họa**, cần implementation mới chạy được:

```java
import javax.management.MXBean;

@MXBean
public interface CacheView {
    long getEntriesTotal();
    java.util.Map<String, Long> getEntriesByTier();
}
```

MXBean có quy tắc mapping tới các dạng như `SimpleType`, `ArrayType`, `CompositeType`, `TabularType`, với `CompositeData` và `TabularData` đại diện cho cấu trúc tổng hợp ở phía JMX.

| Kiểu dữ liệu | Khi thích hợp | Điều cần chú ý |
| --- | --- | --- |
| Primitive, wrapper, `String` | Counter/gauge/ratio/status đơn giản | Tài liệu hóa unit/semantics |
| Enum có tập giá trị ổn định | Trạng thái hữu hạn | Schema và name không đổi tùy tiện |
| `CompositeData` từ snapshot | Nhiều trường cần đọc cùng một lần | Mapping/metadata phải rõ, snapshot phải được lấy nhất quán |
| `TabularData` từ map/bảng nhỏ | Breakdown theo vài chiều hữu hạn | Giới hạn cardinality và response size |
| Java object riêng trong Standard MBean | Giao diện client Java nội bộ cùng model | Client remote có thể cần class tương ứng; ưu tiên MXBean/Open Types nếu muốn tương thích rộng |

Một **immutable snapshot** với `sampleEpochMillis`, `completed`, `failed`, `inFlight` có thể được tạo ở một thời điểm được đồng bộ thích hợp, rồi expose như một MXBean attribute tổng hợp. Nhờ đó consumer có bộ số liên quan chặt hơn so với nhiều lần gọi getters độc lập.

Dù dùng MXBean, không bảo đảm mọi object Java đều map được tự động; phải theo Javadoc và test trên JDK mục tiêu. Không biến `Map<String,Long>` có hàng triệu request IDs thành TabularData lớn chỉ vì interface cho phép.

## 11. Vì sao high-cardinality vẫn nguy hiểm khi chỉ có một MBean?

Có hai kiểu cardinality:

1. **Cardinality của MBeans:** số ObjectNames trong registry. Một MBean cho mỗi session/user/order là nguy hiểm.
2. **Cardinality của attribute values:** chỉ một MBean nhưng trả `Map<String,Long>` với hàng triệu keys cũng có thể quá lớn.

Với monitoring:

- Tên pool/cache/dependency nên là tập hữu hạn đã tài liệu hóa.
- Nhóm operation nên chuẩn hóa, ví dụ `READ`, `WRITE`, `DELETE`.
- Không đưa path URL chứa ID động hoặc string do người dùng nhập vào metric labels.
- Chuyển request-specific details sang logs/traces với trace ID thay vì JMX.
- Đặt giới hạn số entries, kích thước dữ liệu và thời gian xử lý getters.

Tính sẵn sàng của ứng dụng quan trọng hơn việc xuất được “mọi chiều” trên một endpoint quan sát.

## 12. Read-only metrics khác operation quản trị

Một số method không nên xuất trong interface metrics mặc định:

```java
void resetCounters();
void clearCache();
void drainWorkerPool();
void setHealthy(boolean value);
```

Đây là các method **có side effect**. Nếu cho client gọi trong MBean, bạn đã mở một API điều khiển runtime, không chỉ đo lường.

Nếu nghiệp vụ thật sự cần control plane, tách interface/đối tượng và quyền, ghi audit, xác nhận identity, thiết kế cơ chế rollback/guardrails. Đừng cho dashboard định kỳ có quyền reset counters chỉ vì chúng nằm chung trong MBeanServer.

**Lưu ý:** getter cũng có thể vô tình gây side effect nếu implementation gọi DB, reset cache, tạo file hoặc giữ lock. “Read-only” phải đúng trong cả **schema** lẫn **implementation**.

## 13. Tích hợp với JMX exporter và time-series monitoring

JMX thường được một collector **poll** theo chu kỳ. Ví dụ một exporter đọc `RequestsTotal` mỗi 15 giây rồi chuyển giá trị sang time series. Exporter phải được cấu hình đúng **loại metric**, đơn vị và labels; JMX không tự biến `RequestsTotal` thành Counter Prometheus đúng ngữ nghĩa.

Các điểm cần chú ý:

- Counter lifetime: tính rate/increase trên từng instance và xử lý restart/reset.
- Gauge: dùng giá trị hiện tại, không mặc định dùng `rate`.
- Ratio: phân biệt lifetime ratio với rolling/window error ratio.
- Percentile: không tính average của p95 giữa replicas để ra global p95.
- Missing data: JMX disconnect/exporter error là **không có mẫu**, không phải bằng 0.
- Khác biệt thời điểm poll: hai attributes lấy cách nhau vài milliseconds không phải ảnh chụp nguyên tử.
- Java process restart: identity và uptime/start timestamp giúp phát hiện reset.
- Sampling frequency: đừng poll quá dày làm nhiều getter tranh CPU/lock.
- Cardinality: domain/keys/schema phải ổn định qua rollout.

Một counter có thể giảm sau restart:

```text
09:00 RequestsTotal = 152000
09:01 RequestsTotal = 153800
09:02 JVM restarted
09:03 RequestsTotal = 230
```

Không tính `230 - 153800` thành throughput âm. Pipeline phải nhận ra instance reset và xử lý dữ liệu phù hợp.

### 13.1 Error ratio rolling và lifetime ratio

`ErrorRatio` trong demo là ratio kể từ lúc JVM khởi động. Nếu service chạy lâu, một burst lỗi ngắn có thể bị “pha loãng” bởi hàng triệu requests thành công trước đó.

Trong cửa sổ [T1,T2] có cùng instance, nếu không reset:

```text
windowErrorRatio =
    delta(FailuresTotal) / delta(RequestsTotal)
```

Chỉ tính khi delta completed requests lớn hơn 0; nếu không có dữ liệu, cần giữ trạng thái no-data. Đừng tạo alert “error ratio dưới 0.1%” chỉ từ lifetime metric nếu mục tiêu là phát hiện sự cố trong 5 phút gần nhất.

### 13.2 Quantile/histogram nên xuất thế nào?

Nếu cần latency p95/p99:

- Ghi rõ đơn vị (`Millis`/`Seconds`), kích thước cửa sổ, sample count và phương pháp ước lượng.
- Không sort danh sách mọi request khi client poll; dùng histogram/snapshot đã chuẩn bị.
- Không lấy trung bình p95 của từng replica để kết luận p95 toàn cluster.
- Nếu cần tính global quantile, export histogram buckets/distribution có thể tổng hợp theo phương pháp được hỗ trợ.
- `Double.NaN`/Infinity phải được xử lý theo hợp đồng pipeline; không tự dùng làm metric giả.
- Đừng xuất histogram buckets như một String dài khó parse; dùng Open Types/metric exporter thích hợp.

## 14. JMX local, remote và bảo mật

**Local JMX** hữu ích khi developer đang kiểm tra một Java process trên cùng máy. **Remote JMX** là bề mặt quản trị nhạy cảm vì một platform MBeanServer có thể chứa MBeans có operations ảnh hưởng ứng dụng/JVM.

Nguyên tắc:

- Không mở remote JMX port công khai hoặc vô hiệu hóa authentication/TLS chỉ để debug.
- Áp dụng network controls, identity, authorization, audit và nguyên tắc đặc quyền tối thiểu.
- Không nhét token, password, customer ID vào ObjectName hoặc String attribute.
- Với môi trường container, xác định **đúng PID, container, pod, JVM build và timeframe**.
- Phân quyền đọc metrics khác với gọi operation thay đổi cấu hình trên những MBeans khác.
- Nếu client ngoài tổ chức cần đọc, ưu tiên exporter đã bảo vệ và chỉ công bố các số liệu cần thiết.

Ngay cả khi MBean do bạn viết chỉ đọc, nó không thay đổi chính sách của các platform MBeans khác. Không được xem sự hiện diện của một interface `*MBean` read-only là bảo đảm remote JMX an toàn.

## 15. Quy trình triển khai metrics MBean trong Java service

### Bước 1 — Đặt câu hỏi chẩn đoán cụ thể

Ví dụ “request lỗi tăng trong 5 phút gần đây?”, “pool có backlog?”, “worker còn xử lý task hay đang chờ phụ thuộc?”. Chọn số đo thực sự giúp quyết định thay vì expose mọi field.

### Bước 2 — Viết contract

Ghi tên, ObjectName, data type, counter/gauge/ratio/state, unit, update event, reset semantics, no-data rule, concurrency/snapshot guarantees, owner và người sử dụng.

### Bước 3 — Instrument ở đúng điểm nghiệp vụ

Đảm bảo completed counter tăng đúng một lần; failure được phân loại nhất quán; InFlight được cleanup kể cả lỗi; health/state phản ánh điều kiện có định nghĩa. Không tăng counter chỉ khi log thành công, vì lỗi logging không phải lỗi nghiệp vụ.

### Bước 4 — Đăng ký MBean đúng lifecycle

Dùng ObjectName hữu hạn và ổn định. Đăng ký khi component có dữ liệu thực, xử lý tên trùng và rollback startup nếu cần, unregister khi component đóng. Không đăng ký trong mỗi request.

### Bước 5 — Test bằng JMX API thật

Truy vấn `isRegistered`, `getMBeanInfo`, `getAttribute` để xác nhận tên/kiểu/read-only đúng schema. Demo phần 9 là baseline cho bước này.

### Bước 6 — Stress concurrency

Tạo nhiều requests đồng thời, bao gồm failure, timeout, cancellation. Đối chiếu counters với số task; bảo đảm InFlight không âm hoặc rò. Kiểm tra metrics getter không tranh lock nặng với request processing.

### Bước 7 — Test exporter và dashboard

Kiểm tra mapping loại metric, đơn vị, labels, reset/restart, missing data, multi-replica aggregation và alert. Đừng chỉ nhìn một biểu đồ “có số”.

### Bước 8 — Theo dõi chi phí và bảo mật

Thử poll ở tần suất dự kiến, đo overhead, kích thước response, quyền remote, schema compatibility. Ghi rõ giới hạn đo và kế hoạch thay đổi khi API tiến hóa.

## 16. Ba tình huống chẩn đoán

### 16.1 RequestsTotal tăng chậm, InFlight và QueueDepth tăng

Điều này ủng hộ khả năng backlog hoặc downstream processing chậm, nhưng **chưa đủ** để kết luận CPU hay lock là nguyên nhân. Đối chiếu RPS offered/completed, latency, queue wait, thread dump/JFR, CPU/GC và dependency traces trong cùng cửa sổ. Không tăng thread pool một cách máy móc.

### 16.2 Healthy=true nhưng dịch vụ trả nhiều timeout

Cờ `Healthy` chỉ mạnh bằng **tiêu chí triển khai** của nó. Nếu chỉ dựa vào “process còn sống”, một service có thể vẫn healthy=true khi queue quá tải hoặc dependency critical không đáp ứng. Cần phân biệt liveness, readiness và degraded state; thêm metrics/error ratio và health policy phù hợp.

### 16.3 MBean xuất hiện ở staging nhưng không có ở production

Xác minh đúng bản build/PID/container, component đã khởi tạo, ObjectName và cách exporter query. Kiểm tra lỗi `InstanceAlreadyExistsException`, `NotCompliantMBeanException`, quyền JMX, kết nối/agent và tình trạng unregister. Dashboard không hiện số **không tự chứng minh** bean không tồn tại.

## 17. Mẫu đặc tả vận hành

```text
COMPONENT
- Service/build/JDK, owner:
- ObjectName domain/key schema:
- Scope: JVM instance/replica/component:
- Expected number of MBeans and cardinality cap:

METRIC CONTRACT
- Attribute name:
- Type: long/int/double/boolean/String/Open Type:
- Kind: counter/gauge/ratio/state:
- Unit, bounds and no-data rule:
- Precise update trigger:
- Reset/restart behavior and lifetime/window:
- Concurrency and snapshot consistency guarantees:
- Sensitive-data classification:

COLLECTION
- Local JMX / authenticated remote JMX / exporter:
- Poll interval, timeout and failure behavior:
- Exported metric type/name/units/labels:
- Multi-instance aggregation rule:

VALIDATION
- MBeanInfo name/type/readable/writable:
- Functional events vs observed values:
- Parallel load, failure/cancellation coverage:
- Restart/reset, missing data and scale-out:
- Getter overhead and access-control review:

CONCLUSION
- Observations backed by measurements:
- Limits: window, race, stale data, scope:
- Known unsupported questions:
- Change owner and rollback criteria:
```

Đây là **mẫu báo cáo**, không phải số liệu đã quan sát từ một JVM thật. Ghi rõ chứng cứ, môi trường, phiên bản và thời gian để người khác có thể kiểm chứng.

## 18. Những lỗi thường gặp

1. **Trả String cho mọi con số.** Mất kiểu, phải parse, sai unit/locale.
2. **Dùng int cho lifetime counter.** Có nguy cơ tràn sau thời gian dài.
3. **Dùng double cho số lượng nguyên.** Không phù hợp với đếm chính xác.
4. **Nhầm RequestsTotal với requests/second.** Rate cần delta theo thời gian.
5. **Nhầm ErrorRatio 0–1 với ErrorPercent 0–100.** Dashboard có thể sai 100 lần.
6. **Gộp mọi lỗi vào FailuresTotal không định nghĩa failure.** Không thể so giữa endpoints/versions.
7. **Để InFlight không được decrement khi lỗi.** Gauge tăng giả tạo.
8. **Cộng counter bằng toán tử `++` trên field không thread-safe.** Mất updates.
9. **Đòi các getters tự cung cấp snapshot nguyên tử.** Mỗi getter được gọi ở thời điểm khác.
10. **Lấy health boolean làm bằng chứng duy nhất về SLO.** Thiếu latency, correctness và capacity.
11. **Quét DB hoặc sort histogram trong getter.** Polling có thể làm chậm service.
12. **Công khai reset/shutdown operations trong metrics interface.** Tăng rủi ro cấu hình/quản trị.
13. **Đăng ký MBean theo request/user/session.** Cardinality và privacy bùng nổ.
14. **Đưa untrusted input vào ObjectName.** Có thể gây lỗi cú pháp hoặc wildcard/pattern ngoài ý muốn.
15. **Không unregister khi component đóng.** Stale bean giữ state/đối tượng cũ.
16. **Xóa bean trùng tên mà chưa biết owner.** Có thể phá monitoring của component khác.
17. **Coi MXBean nhận mọi object Java tùy ý.** Phải tuân thủ Open Type mapping.
18. **Dùng Map dữ liệu động quá lớn trong một MXBean.** Vẫn có cardinality và response-size risk.
19. **Lấy trung bình p95 giữa replicas.** Không tính ra global percentile chính xác.
20. **Biến missing data thành 0.** Mất khả năng phát hiện exporter/JMX failure.
21. **Không xử lý counter reset sau JVM restart.** Rate sai hoặc báo alert giả.
22. **Đổi tên hoặc type không có migration.** Dashboard/alerts bị gãy.
23. **Chỉ test demo tuần tự.** Chưa chứng minh concurrency correctness.
24. **Mở remote JMX thiếu auth/TLS.** Tăng bề mặt tấn công cho toàn bộ JVM, không chỉ metrics của bạn.
25. **Nhầm số liệu một instance với tổng cluster.** Phải có instance identity và aggregation rules.
26. **Không ghi window của p95/ratio.** Không biết giá trị đại diện cho khoảng nào.
27. **Dùng `System.nanoTime` như UTC timestamp.** Sai ngữ nghĩa clock.
28. **Không kiểm tra schema qua MBeanInfo.** Implementation method không đồng nghĩa được expose.

## 19. Tự kiểm tra

1. Method `long getRequestsTotal()` trong Standard MBean tạo attribute gì? Kiểu và read-only status xác định ra sao?
2. Vì sao lifetime count nên là `long`, còn ratio nên là `double`?
3. ErrorRatio=0.025 theo hợp đồng [0,1] tương đương bao nhiêu phần trăm?
4. Counter tăng từ 1.000 lên 1.300 trong 60 giây thì completed rate trung bình là bao nhiêu nếu không có restart?
5. Vì sao `InFlight` phải giảm qua `finally` và không thể dùng rate của InFlight thay request throughput?
6. Trong lúc nhiều requests chạy, `getAttribute` cho RequestsTotal và FailuresTotal có tự bảo đảm cùng một snapshot không?
7. Việc dùng user ID làm `ObjectName` gây hai rủi ro lớn nào?
8. Khi nào dùng MXBean để trả `CompositeData` thay cho nhiều getters?
9. `isHealthy()` trả true có chứng minh mọi request đang thành công không? Cần xác minh thêm gì?
10. Nếu `MBeanAttributeInfo.isWritable()` trả true cho attribute bạn muốn chỉ đọc, phải kiểm tra phần nào?
11. Counter giảm mạnh sau restart thì exporter phải làm gì, thay vì tính rate âm?
12. Có thể lấy average của p95 trên từng replica để có p95 toàn cluster không?
13. Vì sao việc getter gọi DB trong mỗi lần poll có thể tạo ra sự cố mới?
14. Một ObjectName đã tồn tại: tại sao không nên unregister nó khi chưa biết component đang sở hữu?
15. Những tests nào cần có trước khi cho exporter đọc MBean trong production?

## Tài liệu đối chiếu

- Oracle Java SE 17 — JMX package/MBeans: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/package-summary.html
- Oracle Java SE 17 — StandardMBean: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/StandardMBean.html
- Oracle Java SE 17 — MBeanServer: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/MBeanServer.html
- Oracle Java SE 17 — ObjectName: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/ObjectName.html
- Oracle Java SE 17 — MXBean: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/MXBean.html
- Oracle Java SE 17 — MBeanAttributeInfo: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/MBeanAttributeInfo.html

**Ghi nhớ:** xuất MBean riêng không có nghĩa công khai tất cả biến trong ứng dụng. Một MBean có giá trị khi chỉ số có **kiểu phù hợp, unit rõ, định nghĩa cập nhật và reset chính xác, getter nhẹ, ObjectName ổn định, concurrent reads an toàn và quyền truy cập được kiểm soát**. Chỉ khi đó MBean mới là chứng cứ đáng tin cho chẩn đoán vận hành.