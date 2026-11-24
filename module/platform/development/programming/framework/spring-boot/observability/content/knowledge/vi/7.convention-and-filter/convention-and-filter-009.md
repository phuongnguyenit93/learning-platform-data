# Loại bỏ observation không cần thiết trong Spring Boot

Trong chương **Convention và filter** của module **SPRING_BOOT_OBSERVABILITY**, một phần quan trọng của thiết kế observability là biết **khi nào không nên tạo telemetry**. Spring Boot kết hợp Micrometer Observation với metrics, logs và distributed tracing để giúp điều tra lỗi, độ trễ, sự phụ thuộc giữa dịch vụ và hành vi của ứng dụng. Nhưng không phải mọi thao tác đều cần một observation riêng: heartbeat nội bộ vài trăm lần mỗi giây, một tác vụ polling vô hại hoặc observation lặp lại cùng ranh giới có thể tạo thêm chi phí và khiến dashboard, trace khó đọc.

**Loại bỏ observation không cần thiết** là lựa chọn có chủ đích dựa trên giá trị vận hành, không phải cách giảm dữ liệu bằng cách tắt mọi thứ. Cần giữ các tín hiệu làm nền cho SLI/SLO, điều tra sự cố và liên kết metrics–logs–traces, đồng thời loại đúng những observation không giúp trả lời câu hỏi nào mới.

## 1. Thế nào là observation không cần thiết?

Observation là một đơn vị đo của Micrometer, có tên, context, vòng đời `start/stop` và các handler có thể sinh metric hoặc span. Một observation có thể được xem là không cần thiết **trong một hệ thống và mục tiêu vận hành cụ thể** nếu:

- Cùng ranh giới đã được instrument đáng tin cậy ở nơi khác, nên observation mới chỉ đo trùng ý nghĩa.
- Thao tác diễn ra với tần suất rất cao nhưng độ trễ, lỗi và quan hệ nguyên nhân của từng lần đều không được sử dụng.
- Đã có một nguồn tín hiệu đáng tin cậy hơn cho câu hỏi cần trả lời, như một health metric tổng hợp thay cho từng nhịp heartbeat kỹ thuật.
- Telemetry tạo ra không phục vụ dashboard, alert, SLI/SLO hay phân tích sự cố và không có nhu cầu hợp lý sẽ dùng trong tương lai gần.

Không thể suy ra “không cần thiết” chỉ từ **tần suất cao**. Một endpoint thanh toán nhận nhiều request vẫn rất quan trọng để đo p95 latency, tỉ lệ lỗi và quan hệ trace qua nhiều service. Ngược lại, một job chạy ít nhưng làm hỏng dữ liệu có thể cần observation chính xác cho từng lần chạy.

| Hoạt động | Nhận định ban đầu | Câu hỏi trước khi bỏ |
| --- | --- | --- |
| `internal.heartbeat.tick` chỉ báo một vòng lặp nội bộ còn sống | **Ứng viên loại bỏ** nếu đã có health/availability metric khác | Có còn phát hiện được heartbeat ngừng chạy hoặc lỗi liên tục không? |
| HTTP server observation cho `POST /checkout` | **Nên giữ** | Dashboard RED, SLO và cảnh báo có phụ thuộc không? |
| Span tùy biến bao quanh đúng cùng một HTTP client call đã có instrumentation | **Ứng viên bỏ phần trùng** | Span này có thêm ranh giới nghiệp vụ độc lập không? |
| `inventory.reserve` thể hiện bước giữ tồn kho | **Thường nên giữ** | Có giúp tách latency/exception của bước nghiệp vụ khỏi HTTP tổng thể không? |
| Từng vòng kiểm tra “queue rỗng” của poller | **Có thể giảm** | Có metric chiều sâu queue, số lần poll và cảnh báo lỗi đáng tin cậy khác không? |
| Consumer xử lý message thất bại và retry | **Cẩn trọng, thường nên giữ** | Nếu bỏ, có còn điều tra được retry, dead-letter và latency không? |

Một quyết định tốt nêu rõ **bỏ observation nào**, **tín hiệu nào thay thế** và **câu hỏi điều tra nào vẫn trả lời được**.

## 2. Vì sao cần giảm telemetry nhiễu?

Loại bỏ observation có thể mang lại ba lợi ích, nhưng mức tiết kiệm thực tế phụ thuộc handler và exporter:

1. **Giảm khối lượng xử lý:** ít callback/record được tạo từ observation bị loại; giảm dữ liệu cho backend tracing hoặc metrics nếu chính observation đó là nguồn tạo tín hiệu.
2. **Giảm chi phí lưu trữ/truy vấn:** ít span và time series không có ích. Tuy nhiên, chi phí metrics còn phụ thuộc **số tổ hợp tag**, không chỉ số request hay số observation.
3. **Tăng tín hiệu trên nhiễu:** trace thể hiện các bước nghiệp vụ quan trọng, dashboard ít series dư thừa, kỹ sư dễ tìm nguyên nhân hơn.

Ví dụ có một poller chạy 40 lần/giây trên 20 instance: trong một phút có **40 × 20 × 60 = 48.000 lượt poll**. Nếu mỗi lượt sinh một span dù queue rỗng, backend tracing có thể nhận lượng span lớn nhưng ít giá trị chẩn đoán. Một gauge biểu thị queue depth, một counter phản ánh lỗi poll và observation của lần *thực sự xử lý công việc* có thể cung cấp tín hiệu phù hợp hơn.

Đây chỉ là tính toán số lượt, **không phải ước lượng chính xác số span được xuất**: sampling, handler, exporter và bản thân instrumentation có thể làm số lượng khác đi. Cần đo kết quả trước/sau ở môi trường triển khai.

## 3. Cơ chế chính: ObservationPredicate

Với Spring Boot sử dụng Micrometer Observation, `ObservationPredicate` là cơ chế phù hợp khi cần **từ chối cả một observation**. Predicate được đăng ký với `ObservationRegistry` và trả về quyết định dựa trên tên observation và context:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationPredicate;

ObservationPredicate predicate =
        (String name, Observation.Context context) ->
                !"internal.heartbeat.tick".equals(name);
```

Về mặt ý nghĩa:

```text
Instrumentation tạo observation
          |
          v
ObservationPredicate.test(name, context)
          |
          +-- true  --> observation hoạt động
          |             --> handlers có thể ghi metrics, spans, ...
          |
          +-- false --> observation trở thành no-op
                        --> không sinh telemetry từ observation đó
                        --> code nghiệp vụ được bao bởi observe(...) vẫn chạy
```

**No-op observation không có nghĩa là bỏ qua nghiệp vụ.** Predicate kiểm soát telemetry, không dừng tác vụ, không chặn HTTP request, không thay đổi kết quả trả về và không tự xóa các log mà ứng dụng chủ động ghi. Những meter/span độc lập được thư viện khác tạo ra cũng có thể vẫn tồn tại.

Predicate dùng để quyết định observation **có tham gia vòng đời quan sát hay không**. Nó không cung cấp một cách chọn riêng “chỉ tắt tracing, giữ metrics” hoặc “chỉ tắt metric, giữ tracing” cho cùng observation. Muốn chọn theo tín hiệu, dùng cơ chế dành riêng cho từng hệ thống tín hiệu.

## 4. Ví dụ Spring Boot: loại một heartbeat nội bộ

Giả sử ứng dụng có observation tên `internal.heartbeat.tick`, dùng để đánh dấu một vòng lặp kỹ thuật đang hoạt động. Vòng lặp này đã có một health/availability metric tổng hợp và một cơ chế alert đáng tin cậy; không cần thêm duration/span cho mỗi nhịp.

Đăng ký predicate qua `ObservationRegistryCustomizer` để bổ sung vào registry mà Spring Boot quản lý:

```java
import io.micrometer.observation.ObservationRegistry;
import org.springframework.boot.actuate.autoconfigure.observation.ObservationRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ObservationNoiseConfiguration {

    @Bean
    ObservationRegistryCustomizer<ObservationRegistry> dropHeartbeatTick() {
        return registry -> registry.observationConfig()
                .observationPredicate((name, context) ->
                        !"internal.heartbeat.tick".equals(name));
    }
}
```

Quy tắc chỉ từ chối **một tên chính xác**. Nó không từ chối `internal.heartbeat.failure` nếu application có observation riêng để mô tả sự cố, và cũng không ảnh hưởng trực tiếp các observation khác như `payment.authorize`.

Ví dụ instrumentation trong service:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class HeartbeatService {
    private final ObservationRegistry observationRegistry;

    public HeartbeatService(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    public void tick() {
        Observation.createNotStarted(
                "internal.heartbeat.tick", observationRegistry)
                .observe(this::runHeartbeat);
    }

    private void runHeartbeat() {
        // Công việc thật vẫn chạy khi predicate từ chối observation.
    }
}
```

Sau khi cấu hình được áp dụng, `runHeartbeat()` vẫn được gọi. Phần instrumentation của `internal.heartbeat.tick` không còn đóng góp metric/span qua các observation handlers thông thường. Nếu service có `Counter` hoặc log ghi trực tiếp trong `runHeartbeat()`, các tín hiệu **độc lập** ấy không tự biến mất.

**Giới hạn của ví dụ:** để xác nhận metric và span thật sự giảm, môi trường phải có observation handler, registry và exporter tương ứng. Chỉ chạy code với `ObservationRegistry.create()` mặc định mà không cấu hình handlers sẽ không chứng minh được sự khác nhau ở backend.

## 5. Lọc theo context mà không loại nhầm công việc quan trọng

Đôi khi cùng một loại observation bao gồm cả hoạt động nền ít giá trị và công việc quan trọng. Chỉ so sánh tên sẽ quá rộng; thay vào đó dùng **context có kiểu rõ ràng**, được tạo cùng observation.

Giả sử một poller có hai chế độ được xác định **trước khi chạy**:

- `HEARTBEAT`: một lượt kiểm tra kỹ thuật đã có metric tổng hợp.
- `BUSINESS_SYNC`: một lượt đồng bộ dữ liệu quan trọng cần đo latency, lỗi và trace.

Định nghĩa context:

```java
import io.micrometer.observation.Observation;
import java.util.Objects;

enum PollMode {
    HEARTBEAT, BUSINESS_SYNC
}

final class PollObservationContext extends Observation.Context {
    private final PollMode mode;

    PollObservationContext(PollMode mode) {
        this.mode = Objects.requireNonNull(mode);
    }

    PollMode mode() {
        return mode;
    }
}
```

Predicate chỉ từ chối `integration.poll` nếu context đúng kiểu và `mode == HEARTBEAT`:

```java
import io.micrometer.observation.ObservationRegistry;
import org.springframework.boot.actuate.autoconfigure.observation.ObservationRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class PollObservationConfiguration {

    @Bean
    ObservationRegistryCustomizer<ObservationRegistry> pollPredicate() {
        return registry -> registry.observationConfig()
                .observationPredicate((name, context) -> {
                    if (!"integration.poll".equals(name)) {
                        return true;
                    }
                    if (context instanceof PollObservationContext poll) {
                        return poll.mode() != PollMode.HEARTBEAT;
                    }
                    // Context lạ: giữ observation để tránh mất tín hiệu.
                    return true;
                });
    }
}
```

Code tạo observation:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public class IntegrationPoller {
    private final ObservationRegistry registry;

    public IntegrationPoller(ObservationRegistry registry) {
        this.registry = registry;
    }

    public void poll(PollMode mode, Runnable action) {
        Observation.createNotStarted(
                "integration.poll",
                () -> new PollObservationContext(mode),
                registry)
                .observe(action);
    }
}
```

Ở đây, `mode` đã biết ngay khi khởi tạo observation. **Đừng dùng kết quả chỉ biết sau khi xử lý** (ví dụ “queue rỗng hay không” khi poll hoàn tất) làm điều kiện trong predicate mà kỳ vọng nó tự chờ đến cuối vòng đời. Nếu muốn phân tích `outcome=empty/processed/error`, cần giữ observation và ghi outcome khi có kết quả, hoặc thiết kế lại ranh giới để chỉ tạo observation khi thực sự bắt đầu xử lý message.

Không nên ép kiểu context của HTTP server, HTTP client hay messaging một cách mù quáng. Các context tích hợp có thuộc tính khác nhau giữa framework và phiên bản. Đặc biệt, một tên như `http.server.requests` thường dùng cho **nhiều endpoint**: predicate chỉ so khớp tên ấy có thể vô hiệu hóa mọi HTTP server observation, bao gồm cả endpoint nghiệp vụ.

## 6. Phân biệt predicate với convention, filter và sampling

Các công cụ sau giải quyết những vấn đề khác nhau:

| Cơ chế | Tác dụng chính | Ví dụ phù hợp |
| --- | --- | --- |
| **`ObservationPredicate`** | Quyết định có kích hoạt **toàn bộ observation** hay không | Bỏ `internal.heartbeat.tick` |
| **`ObservationConvention`** | Chuẩn hóa tên, contextual name, low/high-cardinality key-values | Đặt cùng tên `inventory.reserve` trên nhiều call site |
| **`ObservationFilter`** | Bổ sung hoặc chỉnh sửa context/key-values trong vòng đời observation | Thêm tag chung có giá trị hữu hạn cho các observation |
| **`MeterFilter`** | Điều khiển meters và tags trong `MeterRegistry` | Từ chối metric cụ thể hoặc giới hạn tag cardinality |
| **Tracing sampler** | Quyết định trace/span nào được ghi nhận hoặc xuất, tùy setup tracing | Giảm tỉ lệ traces trong môi trường tải lớn |
| **Collector/exporter filter** | Lọc hoặc biến đổi telemetry sau instrumentation | Hạn chế dữ liệu gửi tới một backend cụ thể |

Ví dụ ba yêu cầu rất dễ nhầm:

1. **“Không cần duration/span của heartbeat nữa.”** Predicate phù hợp nếu chấp nhận loại các tín hiệu được tạo từ observation đó.
2. **“Vẫn cần metrics 100% nhưng chỉ xuất một phần distributed traces.”** Dùng sampling cho tracing, không dùng predicate ngẫu nhiên.
3. **“Cần giữ observation nhưng tag chứa customer ID làm tăng time series.”** Sửa nguồn tag, convention/filter hoặc dùng `MeterFilter` thích hợp. Loại cả observation sẽ làm mất latency và error có ích.

### Vì sao không dùng predicate để sampling ngẫu nhiên?

Một đoạn như sau là **phản ví dụ**, không nên dùng để thay tracing sampler:

```java
// Không nên: quyết định ngẫu nhiên cho cả Observation.
registry.observationConfig()
        .observationPredicate((name, context) ->
                java.util.concurrent.ThreadLocalRandom.current()
                        .nextDouble() < 0.10);
```

Nó có thể làm giảm cả metric lẫn span từ observation, khiến số liệu tổng hợp bị thiếu, đồng thời khiến quan hệ trace cha/con và propagation khó suy luận. Sampler của tracing có nhiệm vụ riêng để xử lý quyết định lấy mẫu theo trace và ngữ cảnh truyền qua các service. Predicate nên dựa trên **quy tắc ngữ nghĩa rõ ràng**, ít biến động và dễ kiểm chứng.

## 7. Đặc biệt cẩn trọng với HTTP health checks

Health probes là ứng viên phổ biến khi muốn giảm telemetry do lặp lại, nhưng quyết định phải xét đến cách Spring Boot đang instrument HTTP:

```text
Load balancer / Kubernetes probe
         |
         v
GET /actuator/health
         |
         +--> HTTP server observation (có thể dùng chung tên với endpoint khác)
         |
         +--> Actuator health logic
```

Không nên thêm predicate kiểu `name.equals("http.server.requests") ? false : true` chỉ để “bỏ health checks”, vì tên observation đó có thể được dùng cho **tất cả** HTTP requests. Cần hiểu context thực tế, thời điểm thông tin đường dẫn đã có, và các convention của framework trước khi lọc theo route.

Các lựa chọn hợp lý theo mục tiêu:

- Nếu chỉ muốn **dashboard bớt nhiễu**, lọc health route trong truy vấn hoặc panel. Dữ liệu vẫn được giữ khi cần điều tra.
- Nếu muốn **giảm traces**, cấu hình sampling/tracing theo endpoint hoặc chính sách được tracing stack hỗ trợ, đồng thời bảo đảm giữ đúng context propagation.
- Nếu thực sự muốn **loại telemetry của health route ở nguồn**, xác nhận cách instrumentation/version cho phép chọn riêng route đó, kiểm tra đường dẫn đã chuẩn hóa, và chứng minh không tác động đến metric/spans của request nghiệp vụ.
- Nếu health checks là một nguồn tín hiệu khả dụng quan trọng, giữ một metric tổng hợp thích hợp thay vì bỏ mọi thứ rồi mất khả năng cảnh báo.

Quy tắc là **không suy tên endpoint từ một tên observation chung**. Dữ liệu route và request có thể chưa sẵn có tại thời điểm predicate quyết định; vì thế cần xác minh bằng ứng dụng thực tế thay vì áp dụng một ví dụ theo giả định.

## 8. Hệ quả lên metrics, logs và distributed tracing

Khi một observation tạo cả metric và span thông qua các handler, việc từ chối nó có thể loại **cả hai loại tín hiệu**. Không thể giả định rằng việc loại bỏ chỉ tác động đến biểu đồ mà không tác động đến khả năng truy dấu.

Xét luồng:

```text
POST /checkout                 [HTTP server observation]
    |
    +-- inventory.reserve      [custom business observation]
    |      |
    |      +-- database call   [tùy instrumentation]
    |
    +-- payment.authorize      [custom business observation]
           |
           +-- HTTP client     [tùy instrumentation]
```

Nếu loại `inventory.reserve` vì “đã có SQL span”, ta có thể mất thông tin bước **giữ tồn kho theo nghiệp vụ**, trong khi SQL span chỉ phản ánh lời gọi database. Ngược lại, nếu custom observation chỉ bao quanh một HTTP client call đã được instrument và không thêm ngữ nghĩa, bỏ custom observation đó có thể làm trace gọn hơn.

**Metrics:** nhiều SLI dựa vào thời lượng và tỉ lệ lỗi của operation. Trước khi loại observation, kiểm tra dashboard, cảnh báo và truy vấn p95/p99. Predicate không tự tái tạo các metric đã mất; các counter/gauge độc lập còn hay mất tùy được instrument ở đâu.

**Traces:** việc loại một span có thể làm mất điểm chuyển tiếp ngữ nghĩa. Các span con hoặc upstream/downstream vẫn có thể được tạo nếu được instrument độc lập, nhưng quan hệ cha/con và chi tiết tracing phụ thuộc context còn hoạt động, sampling và propagation.

**Logs:** predicate không tự dừng `logger.info(...)` hoặc `logger.error(...)` trong business code. Tuy nhiên, một log mang `traceId`/`spanId` nhờ tracing và MDC correlation có thể khác đi khi observation cung cấp span bị loại. Nên kiểm tra khả năng mở một log lỗi và tìm lại trace liên quan.

**Async/queue propagation:** nếu việc xử lý chạy trong executor hoặc message consumer, observation scope trên thread ban đầu không tự bảo đảm truyền context. Muốn điều tra xuyên dịch vụ, cần cơ chế Micrometer Context Propagation, instrumentation của framework và trace propagator phù hợp. Không dùng việc tắt observation để khắc phục lỗi propagation.

## 9. Thiết kế quy tắc loại bỏ có kiểm soát

### 9.1. Tên ổn định và phạm vi hẹp

Ưu tiên allow/deny theo **tên chính xác do ứng dụng sở hữu** như `internal.heartbeat.tick`. Tránh biểu thức rộng như `startsWith("http")` hoặc `contains("health")` khi chưa biết mọi observation có thể bị ảnh hưởng. Một quy tắc quá rộng có thể làm biến mất telemetry của endpoint nghiệp vụ trong một đợt triển khai.

### 9.2. Kiểm soát context và thứ tự thông tin

Predicate chỉ nên đọc dữ liệu đã có khi quyết định được đánh giá. Dùng context có kiểu riêng khi filter custom operation; với context không nhận diện được, thường nên **giữ observation** để tránh mất tín hiệu sau nâng cấp dependency.

### 9.3. Nhiều predicate

Một registry có thể được cấu hình bởi nhiều customizer hoặc thư viện. Nếu bất kỳ predicate có hiệu lực nào từ chối observation, quy tắc khác không thể “bật lại” observation đó một cách đáng tin cậy. Vì thế cần ghi nhận chủ sở hữu và mục đích từng quy tắc, tránh để hai thành phần cùng loại hoặc cho phép trái ngược.

### 9.4. Đường instrument phải nhẹ

Predicate có thể chạy rất thường xuyên. Nó nên là phép so sánh nhanh hoặc đọc một thuộc tính context đã có; tránh gọi DB, network, lấy khóa lâu, xử lý regex phức tạp hay logging trên mỗi lần gọi. Một predicate nặng có thể tạo thêm latency đáng kể trên đường request nóng.

### 9.5. Không dùng việc loại bỏ để che cardinality

Low-cardinality tags phải có tập giá trị hữu hạn, ví dụ `outcome=success/declined/error` hoặc `provider=a/b/c`. Không dùng `userId`, `orderId`, email, raw URL, query string hay exception message làm nhãn time series. Nếu cần detail cho từng request, dùng trace/log attributes có chọn lọc theo chính sách bảo mật; tránh đưa token hoặc dữ liệu nhạy cảm vào telemetry.

## 10. Quy trình đánh giá và xác minh trước/sau

Khi chuẩn bị loại một observation, làm theo các bước:

1. **Xác định câu hỏi vận hành:** hệ thống cần phát hiện/điều tra điều gì? Ví dụ “poller có bị kẹt không?” hay “p95 của payment authorize có tăng không?”.
2. **Kiểm kê tín hiệu hiện hữu:** metrics, logs, spans, alert, SLO và dashboards nào đang sử dụng observation dự kiến bỏ? Có tín hiệu thay thế đáng tin cậy không?
3. **Xác định chính xác mục tiêu:** tên observation ổn định, context và thời điểm dữ liệu có sẵn; chọn predicate hay cơ chế khác cho đúng yêu cầu.
4. **Ước lượng lợi ích:** số observation/span/time series trước và sau; latency/CPU overhead; retention và chi phí exporter/backend.
5. **Thử đường thành công và lỗi:** xác minh nghiệp vụ vẫn chạy, errors vẫn có chỗ quan sát, và các operation quan trọng không bị loại nhầm.
6. **Kiểm tra tương quan:** từ một alert hoặc log lỗi có tìm được metric/trace và xác định nguyên nhân xuyên service không?
7. **Theo dõi khi triển khai:** so sánh lưu lượng telemetry, cảnh báo và khả năng điều tra; có kế hoạch gỡ quy tắc nếu thiếu tín hiệu.

### Bảng kiểm thử với chính sách mẫu

Giả định predicate theo tên ở mục 4 và predicate theo context ở mục 5 được đăng ký:

| Kịch bản | Kết quả nghiệp vụ | Tín hiệu kỳ vọng |
| --- | --- | --- |
| `internal.heartbeat.tick` | Vòng heartbeat tiếp tục chạy | Observation bị từ chối; không có metric/span **do observation này** tạo |
| `internal.heartbeat.failure` | Logic xử lý lỗi vẫn hoạt động | Observation khác tên được giữ nếu không có quy tắc loại khác |
| `integration.poll`, `HEARTBEAT` | Tác vụ polling vẫn chạy | Observation bị từ chối |
| `integration.poll`, `BUSINESS_SYNC` | Job đồng bộ chạy | Observation được cho phép; handler có thể tạo metric/span |
| `integration.poll`, context lạ | Logic vẫn chạy | Mặc định giữ observation |
| `payment.authorize` thành công/lỗi | Giữ nguyên hành vi và exception | Observation tiếp tục hoạt động để đo duration/error |
| Sampled-out trace | Không đổi nghiệp vụ | Span có thể không được xuất; **không đủ** để kết luận predicate đã loại |

Để kiểm chứng ở môi trường thật, phân biệt ba tầng:

- **Instrumentation:** observation được tạo với tên/context nào và predicate quyết định ra sao?
- **Handler/registry:** khi được cho phép, handler metrics/tracing có được cấu hình để xử lý không?
- **Exporter/backend:** dữ liệu có được scrape hoặc xuất không, có bị sampling, filtering hoặc đổi tên metric trong backend không?

Một biểu đồ trống có thể do Prometheus chưa scrape, exporter chưa bật, trace sampling, tag khác kỳ vọng hoặc backend bị trễ; không nhất thiết do predicate. Ngược lại, nếu predicate đã loại observation, việc tăng sampling về 100% cũng không làm quan sát đó xuất hiện trở lại.

## 11. Tình huống tổng hợp: hệ thống xử lý đơn hàng

Một dịch vụ Spring Boot có các thao tác:

```text
HTTP POST /orders
  +-- inventory.reserve        (business operation)
  +-- payment.authorize        (business operation)
  +-- publishOrderEvent        (async / message)

background:
  +-- internal.heartbeat.tick  (high frequency)
  +-- integration.poll         (HEARTBEAT or BUSINESS_SYNC)
```

Đội vận hành muốn giảm telemetry nhưng vẫn trả lời được: “Đơn lỗi do thanh toán hay tồn kho?”, “Request chậm ở đâu?”, “Message có được xử lý sau khi HTTP response kết thúc không?”.

Một thiết kế hợp lý là giữ HTTP server observation và các observation nghiệp vụ `inventory.reserve`, `payment.authorize`, giữ instrumentation xử lý message cùng context propagation, nhưng loại `internal.heartbeat.tick` khi health metric khác đã đáp ứng mục tiêu. Với `integration.poll`, chỉ từ chối chế độ `HEARTBEAT` đã biết trước, còn chế độ `BUSINESS_SYNC` được quan sát.

Các tag còn lại cần được chuẩn hóa, chẳng hạn `outcome=success/declined/error` và `provider=a/b`; không tạo metric tag theo order ID. Để giảm lượng trace, cấu hình sampling riêng; để thay đổi tên/tag, dùng convention/filter; để từ chối một meter cụ thể nhưng giữ trace, dùng cơ chế của meter registry.

**Điểm cần nhớ:** observation được loại bỏ **phải là một quyết định có chứng cứ**. Dùng `ObservationPredicate` cho loại bỏ toàn bộ một observation theo tên/context, giữ ranh giới nghiệp vụ có ích, dùng đúng công cụ cho tag/cardinality và sampling, rồi xác minh metrics–logs–traces còn đủ để phát hiện và điều tra sự cố trên hệ thống thực.
