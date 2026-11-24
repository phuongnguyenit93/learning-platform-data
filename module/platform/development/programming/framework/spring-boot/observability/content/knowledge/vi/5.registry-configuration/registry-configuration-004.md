# ObservationPredicate: quyết định Observation nào được ghi nhận

Trong chương **Cấu hình registry** của module **SPRING_BOOT_OBSERVABILITY**, `ObservationPredicate` là một điểm kiểm soát quan trọng của Micrometer Observation. Nó giúp ứng dụng Spring Boot **quyết định có kích hoạt một observation hay không** ngay tại ranh giới tạo observation, dựa trên tên và ngữ cảnh ban đầu của thao tác.

Trong hệ thống thực, observability cần kết hợp **metrics, logs và distributed tracing** để điều tra lỗi, độ trễ, hành vi ứng dụng. Tuy nhiên, một số hoạt động lặp lại rất nhiều như heartbeat, tác vụ nội bộ hoặc polling không có giá trị chẩn đoán tương ứng với lượng telemetry chúng tạo ra. `ObservationPredicate` có thể loại những observation này khỏi quy trình xử lý của registry, miễn là việc loại bỏ không làm mất tín hiệu cần thiết cho vận hành.

> **Ý chính:** `ObservationPredicate` trả lời câu hỏi **“Observation này có được phép hoạt động không?”**. Nó không phải cơ chế để đổi tên/tag, sửa lỗi cardinality, quyết định sampling của trace hoặc ngăn nghiệp vụ chạy.

## 1. ObservationPredicate nằm ở đâu trong luồng Micrometer?

Một observation biểu diễn một công việc có ngữ nghĩa: nhận request, gọi dependency, thực thi job hoặc xử lý một bước nghiệp vụ. `ObservationRegistry` quản lý các bộ phận tham gia vòng đời observation, gồm predicate, convention, filter và handler theo cấu hình của phiên bản đang sử dụng.

Sơ đồ khái niệm:

```text
Ứng dụng / instrumentation của framework
         |
         v
  Tạo Observation (name + context)
         |
         v
  ObservationPredicate.test(name, context)
         |
         +----- false -----> Observation không hoạt động (no-op)
         |                     | 
         |                     +--> Code nghiệp vụ trong observe(...) vẫn chạy
         |
         +----- true ------> Observation hoạt động
                               |
                               +--> start / scope / event / error / stop
                               |
                               +--> ObservationHandler(s)
                                     |
                                     +--> Metric handler, nếu có
                                     +--> Tracing handler, nếu có
```

Đây là sơ đồ **quyết định kích hoạt**, không mô tả chính xác mọi callback nội bộ của từng handler. Handler và exporter thực tế còn phụ thuộc dependency và cấu hình của Spring Boot/Micrometer.

Giao diện cốt lõi:

```java
package io.micrometer.observation;

@FunctionalInterface
public interface ObservationPredicate {
    boolean test(String observationName, Observation.Context context);
}
```

- `observationName` là tên quan sát do instrumentation chỉ định, ví dụ `internal.heartbeat` hoặc `payment.authorize`.
- `context` là ngữ cảnh gắn với observation; kiểu cụ thể tùy nơi tạo observation (HTTP, messaging, custom job...).
- Kết quả `true`: observation được phép hoạt động và tiếp tục đi qua các thành phần registry.
- Kết quả `false`: observation được vô hiệu hóa; các handler của observation đó không tạo tín hiệu tương ứng theo cách thông thường.

**Một điểm dễ hiểu nhầm:** predicate không phải là điều kiện `if` bao quanh nghiệp vụ. Nếu gọi `observation.observe(() -> processOrder())` mà predicate từ chối, `processOrder()` **vẫn được thực thi**. Chỉ phần quan sát trở thành no-op.

## 2. Khi nào nên dùng?

Đầu tiên hãy xác định **câu hỏi vận hành** cần trả lời và đo xem tín hiệu hiện có đã đủ chưa. Predicate hữu ích khi *cả observation* là không cần thiết trong một phạm vi rõ ràng.

| Tình huống | Có nên dùng `ObservationPredicate`? | Lý do |
| --- | --- | --- |
| Observation `internal.heartbeat` phát sinh liên tục, đã có health check/availability metric khác | **Có thể** | Giảm observation không đem lại thông tin mới |
| Một tác vụ nội bộ chuyên dọn bộ nhớ đệm không ảnh hưởng SLO, không cần trace hoặc metric riêng | **Có thể** | Tránh số lượng span/metric lớn nếu đã chứng minh không cần tín hiệu |
| Muốn loại toàn bộ observation của một tên đã biết, ổn định | **Phù hợp** | Quyết định đơn giản theo tên ngay khi khởi tạo |
| Muốn bỏ một tag nhạy cảm nhưng giữ latency/error của observation | **Không phù hợp** | Cần sửa cách gắn tag, convention/filter hoặc chính sách dữ liệu |
| Muốn giữ metrics nhưng giảm lượng trace gửi exporter | **Không phù hợp** | Dùng cấu hình sampling/tracing để giữ tín hiệu metric |
| Muốn bỏ metric nhưng giữ trace của cùng thao tác | **Không phù hợp** | Cần kiểm soát metric handler, meter hoặc `MeterFilter` phù hợp |
| Muốn ngăn request tới `/actuator/health` chạy | **Không phù hợp** | Predicate chỉ kiểm soát telemetry, không chặn HTTP request |
| Cần lọc observation dựa trên kết quả lỗi xuất hiện sau khi thao tác kết thúc | **Thường không phù hợp** | Tại thời điểm quyết định kích hoạt, kết quả chưa tồn tại |

Ví dụ: hệ thống có một triệu lượt `internal.heartbeat` mỗi giờ và chúng chỉ bổ sung trùng lặp cho một health metric đáng tin cậy. Loại observation đó có thể hợp lý. Ngược lại, tắt `http.server.requests` chỉ để giảm số series có thể khiến dashboard latency/error, SLI và alert bị mất dữ liệu quan trọng.

## 3. Đăng ký predicate vào ObservationRegistry trong Spring Boot

Trong Spring Boot sử dụng Micrometer Observation, cách rõ ràng để bổ sung quy tắc là dùng `ObservationRegistryCustomizer`, để framework tiếp tục cấu hình registry và các handler liên quan.

```java
import io.micrometer.observation.ObservationRegistry;
import org.springframework.boot.actuate.autoconfigure.observation.ObservationRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ObservationPolicyConfiguration {

    @Bean
    ObservationRegistryCustomizer<ObservationRegistry> ignoreInternalHeartbeat() {
        return registry -> registry.observationConfig()
                .observationPredicate((name, context) ->
                        !"internal.heartbeat".equals(name));
    }
}
```

Giải thích:

1. Cấu hình bổ sung predicate vào registry mà Spring Boot đang sử dụng.
2. Observation có tên chính xác `internal.heartbeat` bị từ chối; tên khác trả về `true` và tiếp tục hoạt động.
3. So sánh bằng `equals` làm phạm vi loại bỏ rõ ràng; không vô tình loại `internal.heartbeat.failed` hay `internal.heartbeat.recovery` nếu chúng là hai loại thao tác quan trọng khác.
4. Không cần gọi một exporter hay truy cập network trong predicate. Quy tắc chỉ dựa trên dữ liệu tại chỗ nên nhẹ, dễ kiểm tra và nhất quán.

Để thử quyết định trong mã ứng dụng, có thể dùng:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public class HeartbeatService {
    private final ObservationRegistry registry;

    public HeartbeatService(ObservationRegistry registry) {
        this.registry = registry;
    }

    public void sendHeartbeat() {
        Observation.createNotStarted("internal.heartbeat", registry)
                .observe(this::actuallySendHeartbeat);
    }

    private void actuallySendHeartbeat() {
        // Tác vụ heartbeat vẫn chạy dù observation bị từ chối.
    }
}
```

Trong ứng dụng Spring Boot, registry này cần đi kèm các handler/bridge/exporter thích hợp mới có metric hoặc trace để quan sát. Nếu tự tạo `ObservationRegistry.create()` trong một chương trình độc lập mà không đăng ký handler, observation được phép hoạt động cũng **không tự xuất metrics/traces**.

### Nhiều predicate cùng tồn tại

Một ứng dụng có thể có predicate từ cấu hình ứng dụng, thư viện tích hợp hoặc nhiều customizer. **Một quy tắc trả về `false` đủ để observation bị từ chối**, nên cần xem xét các quy tắc đang có cùng nhau. Đừng thiết kế predicate A kỳ vọng rằng predicate B có thể “bật lại” observation đã bị A loại.

Nếu đặt một predicate theo tiền tố tên (ví dụ `name.startsWith("http.")`), hãy kiểm tra phạm vi rất kỹ: nó có thể loại cả client/server observation đang phục vụ trace propagation và các metric thiết yếu.

## 4. Lọc theo context: dùng dữ liệu đã biết khi tạo Observation

`ObservationPredicate` nhận cả `Observation.Context` nên có thể đưa ra quyết định phức tạp hơn so với chỉ so sánh tên. Điều kiện quan trọng là **thông tin dùng để lọc phải có sẵn khi predicate được đánh giá**. Không nên dựa vào nhãn được thêm sau khi `start()`, sau khi trả kết quả, hoặc sau khi phát sinh exception.

Giả sử một hệ thống có job `job.execute` thuộc hai loại `business` và `housekeeping`. Môi trường này đã có metric riêng cho housekeeping và muốn giữ observation chỉ cho job nghiệp vụ:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.boot.actuate.autoconfigure.observation.ObservationRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

final class JobObservationContext extends Observation.Context {
    private final String jobType;

    JobObservationContext(String jobType) {
        this.jobType = jobType;
    }

    String jobType() {
        return jobType;
    }
}

@Configuration(proxyBeanMethods = false)
class JobObservationConfiguration {

    @Bean
    ObservationRegistryCustomizer<ObservationRegistry> jobObservationPolicy() {
        return registry -> registry.observationConfig()
                .observationPredicate((name, context) -> {
                    if (!"job.execute".equals(name)) {
                        return true;
                    }
                    if (context instanceof JobObservationContext jobContext) {
                        return !"housekeeping".equals(jobContext.jobType());
                    }
                    // Context không nhận diện được: ưu tiên giữ telemetry.
                    return true;
                });
    }
}

class JobRunner {
    private final ObservationRegistry registry;

    JobRunner(ObservationRegistry registry) {
        this.registry = registry;
    }

    void execute(String jobType, Runnable task) {
        Observation.createNotStarted(
                "job.execute",
                () -> new JobObservationContext(jobType),
                registry)
            .observe(task);
    }
}
```

Trong mẫu này, `jobType` đã biết **trước khi chạy job**, nên có thể đưa vào context ngay khi tạo observation. Nếu job type chỉ được suy ra sau khi chạy, predicate không thích hợp để quyết định dựa trên thông tin ấy.

**Chú ý với instrumentation của framework:** context của HTTP server, HTTP client hoặc messaging có kiểu và thông tin khác nhau tùy công nghệ. Không ép kiểu context không kiểm tra, không giả định URL, request body hay kết quả nghiệp vụ luôn sẵn có. Nếu muốn loại health probe theo đường dẫn HTTP, cần sử dụng đúng context request của phiên bản/framework đang dùng, kiểm tra URI đã chuẩn hóa và thử trên cả đường hợp lệ lẫn đường lỗi. Một observation tên `http.server.requests` có thể bao phủ nhiều endpoint; lọc đơn thuần theo tên sẽ bỏ *toàn bộ* HTTP server observations thuộc tên đó.

## 5. Khác gì với ObservationFilter, MeterFilter và trace sampling?

Đây là bốn cơ chế dễ bị dùng nhầm vì đều có thể làm thay đổi dữ liệu quan sát được:

| Cơ chế | Phạm vi quyết định | Dùng khi |
| --- | --- | --- |
| **`ObservationPredicate`** | Chọn observation có hoạt động hay không, tại thời điểm khởi tạo | Muốn loại một loại observation khỏi pipeline observation |
| **`ObservationFilter`** | Bổ sung hoặc chỉnh context/key-value của observation được xử lý | Muốn gắn metadata chuẩn, sửa quy ước tag/context; không dùng để quyết định bật/tắt |
| **`MeterFilter`** | Điều khiển meter/tags trong `MeterRegistry` | Muốn từ chối/đặt giới hạn meter hoặc sửa nhãn metrics; tracing có thể vẫn hoạt động |
| **Trace sampling** | Quyết định trace/span nào được ghi nhận hoặc xuất theo bộ lấy mẫu | Muốn giảm dung lượng tracing nhưng vẫn giữ metrics và quan hệ propagation theo cấu hình |

Ví dụ các quyết định khác nhau:

- **“Không cần quan sát heartbeat này nữa.”** Dùng `ObservationPredicate` nếu chấp nhận mất cả tín hiệu phát sinh từ observation đó.
- **“Giữ `payment.authorize` nhưng thêm tag `service.tier=gold`.”** Dùng convention/filter hoặc thiết lập tag ở nơi instrument, với tập giá trị được kiểm soát.
- **“Metric `http.server.requests` có một nhãn mang order ID gây nổ cardinality.”** Loại bỏ hoặc chuẩn hóa nhãn từ nguồn; có thể dùng `MeterFilter` để bảo vệ metric registry. Predicate loại toàn bộ observation sẽ làm mất quá nhiều tín hiệu.
- **“Chỉ cần xuất 10% distributed traces nhưng muốn giữ đầy đủ metrics.”** Dùng cấu hình tracing sampling phù hợp, không dùng predicate như bộ lấy mẫu.

### Vì sao không thay trace sampling bằng predicate ngẫu nhiên?

Một predicate trả về `Math.random() < 0.1` để chỉ cho 10% observation hoạt động nghe có vẻ tiết kiệm, nhưng nó có thể làm méo metrics, cắt đoạn trace cha/con và khiến quan hệ giữa logs/traces khó giải thích. Distributed tracing cần quyết định sampling và propagation **nhất quán xuyên service**. Hãy dùng sampler của hệ thống tracing; nếu muốn loại hẳn một loại observation theo ngữ nghĩa, dùng predicate tường minh.

## 6. Ảnh hưởng lên metrics, logs và distributed tracing

Đối với một observation được đăng ký với cả metric handler và tracing handler, một predicate trả về `false` có thể khiến **cả metric lẫn span do observation đó tạo ra đều không xuất hiện**. Điều này khác với việc trace không được lấy mẫu hoặc exporter chưa gửi dữ liệu thành công.

Giả sử luồng thanh toán:

```text
HTTP server observation: http.server.requests
  └─ Business observation: payment.authorize
       └─ HTTP client observation: http.client.requests
```

Nếu từ chối `payment.authorize`, thông tin ranh giới nghiệp vụ có thể biến mất khỏi trace; HTTP client observation vẫn có thể tồn tại nhưng quan hệ cha/con sẽ phụ thuộc ngữ cảnh còn hoạt động. Nếu từ chối `http.server.requests`, ứng dụng có thể mất span gốc tương ứng request cùng metric HTTP liên quan, ảnh hưởng SLI, alert và tương quan log/trace. Trên hệ thống thực phải kiểm chứng đầy đủ luồng thay vì đoán từ sơ đồ.

Một predicate **không tự tắt logging ứng dụng**: lệnh ghi log thông thường vẫn thực hiện. Tuy nhiên, log có `traceId`/`spanId` nhờ tracing và MDC correlation có thể không còn cùng ngữ cảnh như trước nếu observation làm nguồn span đã bị loại. Đây là lý do phải xem xét mối liên hệ giữa ba tín hiệu, đặc biệt khi điều tra lỗi và độ trễ.

Về context propagation, predicate không truyền hoặc khôi phục context. Nếu quan sát vẫn được giữ nhưng task chạy ở executor khác, cần cơ chế propagation thích hợp của framework/Micrometer. Lọc observation ở ranh giới gốc có thể tác động lên span và baggage được truyền đi; cần kiểm tra với service downstream.

## 7. Thực hành thiết kế predicate an toàn và dễ vận hành

### 7.1. Bắt đầu với danh sách loại trừ hẹp

Ưu tiên so khớp **tên chính xác** của các observation bạn chủ động tạo. Với observation framework, hãy kiểm tra tên, convention và context thực tế trước khi sửa. Tránh blacklist tên dạng `contains("http")` hoặc `startsWith("spring")` khi chưa liệt kê những tín hiệu bị ảnh hưởng.

### 7.2. Đừng dùng predicate để chữa cardinality

Cardinality cao thường đến từ tags/attributes như `userId`, `orderId`, email, đường dẫn chưa chuẩn hóa, exception message hoặc tham số query. Predicate không giải quyết gốc của vấn đề nếu vẫn cần giữ metric/trace cho tác vụ đó. Thiết kế low-cardinality tags có tập giá trị nhỏ và hữu hạn; thông tin high-cardinality chỉ sử dụng trong trace/log theo chính sách bảo mật và giới hạn volume.

Ví dụ bộ nhãn ổn định:

| Nhãn | Giá trị điển hình | Ghi chú |
| --- | --- | --- |
| `operation` | `authorize`, `capture`, `refund` | Tập thao tác cố định |
| `outcome` | `success`, `declined`, `error` | Phân biệt kết quả nghiệp vụ và lỗi hệ thống |
| `provider` | `provider_a`, `provider_b` | Chuẩn hóa theo số provider được hỗ trợ |
| `order_id` | Giá trị khác nhau theo từng đơn | **Không** dùng làm low-cardinality metric tag |

### 7.3. Giữ predicate nhẹ và thuần quyết định

Predicate được chạy trên đường instrument của ứng dụng, có thể rất thường xuyên. Trong `test(name, context)`, tránh truy vấn DB, gọi mạng, đọc cấu hình ngoài tiến trình, khóa lâu hoặc tạo log liên tục. Ưu tiên điều kiện rẻ, không có side effect. Nếu quy tắc cần thay đổi theo môi trường, hãy đưa cấu hình vào một giá trị được khởi tạo trước và có hành vi ổn định, đồng thời kiểm soát cách cập nhật khi chạy.

### 7.4. Fail open với context không nhận diện được

Khi một predicate dựa vào subtype của `Observation.Context`, nên trả về `true` nếu context không đúng subtype dự kiến, trừ khi có yêu cầu rõ khác. Điều này tránh mất telemetry âm thầm khi instrumentation thay đổi sau nâng cấp thư viện hoặc một nguồn khác dùng cùng observation name.

### 7.5. Đánh giá hệ quả trước khi triển khai

Trước khi lọc, kiểm kê dashboard, alert, SLI/SLO, log correlation và tracing hiện đang dựa vào observation đó. Cần thống nhất liệu việc loại metric/span có chấp nhận được và xem xét điều chỉnh alert nếu số liệu sẽ không còn được sinh ra. Với ứng dụng nhiều instance, bảo đảm chính sách nhất quán hoặc phân biệt được khác biệt cấu hình.

## 8. Kiểm chứng bằng kịch bản cụ thể

Ví dụ chính sách: từ chối `internal.heartbeat` và giữ `payment.authorize`. Cần kiểm tra ít nhất các trường hợp sau trong môi trường đã cấu hình handler/exporter:

| Kịch bản | Kỳ vọng |
| --- | --- |
| Chạy heartbeat với tên `internal.heartbeat` | Logic heartbeat vẫn chạy; không có tín hiệu mới do observation này sinh ra |
| Chạy thao tác `payment.authorize` thành công | Observation hoạt động, được metric/tracing handler xử lý theo cấu hình |
| `payment.authorize` ném exception | Ngoại lệ nghiệp vụ không bị predicate nuốt; handler lỗi vẫn xử lý nếu instrumentation ghi nhận lỗi |
| `internal.heartbeat.failed` là observation khác | Vẫn được phép hoạt động nếu so khớp tên chính xác như ví dụ |
| Job `housekeeping` có `JobObservationContext` | Observation `job.execute` bị loại; job vẫn được thực thi |
| Job `business` hoặc context không nhận diện | Observation `job.execute` được giữ |
| Có nhiều predicate | Một predicate từ chối thì observation không hoạt động; không có quy tắc sau “bật lại” |
| Tracing sampling thấp | Không suy ra predicate đã từ chối chỉ vì không thấy một span; đối chiếu metric, sampling và exporter |

Các lớp kiểm tra cần tách biệt:

1. **Hành vi ứng dụng:** code trong `observe(...)` chạy đúng và exception vẫn được truyền như trước.
2. **Registry và handler:** observation nào được cho phép, observation nào thành no-op.
3. **Tín hiệu đầu ra:** metric và span có/không xuất hiện như mong đợi sau exporter, scrape, sampling và lọc của backend.
4. **Điều tra end-to-end:** request có thể truy dấu qua service, log correlation hợp lệ và alert dựa trên metric thiết yếu vẫn còn dữ liệu.

Nếu một metric không thấy trên dashboard, đừng vội quy lỗi cho predicate. Cần xem thêm metric handler, `MeterRegistry`, cấu hình exporter, scrape, naming convention và thời gian tổng hợp. Tương tự, span vắng mặt có thể do sampling hoặc thiếu tracing bridge/context propagation.

## 9. Tình huống thực tế: giảm telemetry nhiễu mà giữ khả năng điều tra

Một hệ thống Spring Boot xử lý đơn hàng có ba observation:

```text
internal.heartbeat      (rất nhiều, có health metric khác thay thế)
order.confirm           (gắn với SLO xác nhận đơn)
payment.authorize       (gắn với lỗi/độ trễ provider)
```

Đội vận hành muốn giảm overhead mà vẫn trả lời được: *bao nhiêu đơn lỗi? xác nhận đơn có chậm không? provider nào chậm? trace của request bị lỗi đi qua những bước nào?*

Thiết kế phù hợp:

1. Dùng predicate chỉ để từ chối `internal.heartbeat` sau khi đã xác nhận health metric khác đủ nhu cầu.
2. Giữ `order.confirm` và `payment.authorize` để còn metric latency/error và span nghiệp vụ.
3. Chuẩn hóa low-cardinality tags như `outcome`, `provider`; không đưa order ID vào nhãn metric.
4. Dùng trace sampling để khống chế dung lượng distributed tracing; tiếp tục bảo đảm propagation.
5. So sánh trước/sau bằng số observation/span và metric time series, đồng thời chạy thử kịch bản lỗi thực tế để xác nhận vẫn điều tra được.

**Ghi nhớ:** `ObservationPredicate` là **cổng cho phép hoặc từ chối toàn bộ observation**. Hãy dùng nó cho các tín hiệu thực sự không cần thiết, giữ các observation làm nền cho SLI, metrics, logs correlation và distributed tracing, và dùng cơ chế đúng mục đích cho chỉnh tag, quản lý cardinality hoặc trace sampling.
