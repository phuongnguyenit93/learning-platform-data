# ObservationFilter để bổ sung hoặc loại thông tin theo vòng đời

## Mục tiêu

Micrometer Observation cho phép instrumentation tạo một Observation với Context chứa trạng thái và metadata. Trong một ứng dụng lớn, nhiều thư viện có thể tạo Observation theo những quy ước riêng. Có những thông tin cần được bổ sung đồng nhất cho mọi Observation, chẳng hạn vùng triển khai; cũng có những key-value cần được chuẩn hóa hoặc loại bỏ trước khi handler xử lý kết quả cuối cùng.

ObservationFilter là extension point để biến đổi Observation.Context ở giai đoạn Observation dừng. Filter được gọi sau các callback lifecycle trước đó và ngay trước các callback onStop của ObservationHandler. Vì vậy, nó phù hợp để bổ sung hoặc loại metadata cho bước xử lý cuối, đồng thời có một giới hạn quan trọng: filter không thể sửa ngược thông tin mà handler đã tiêu thụ ở onStart hoặc khi event xảy ra.

Sau bài này, bạn có thể:

- Đăng ký ObservationFilter trên ObservationRegistry.
- Bổ sung low-cardinality hoặc high-cardinality key-value.
- Loại bỏ key-value không còn phù hợp.
- Chuyển một key-value từ high cardinality sang low cardinality khi giá trị đã được giới hạn.
- Phân biệt ObservationFilter với ObservationConvention, ObservationPredicate và ObservationHandler.
- Kiểm thử metadata trước và sau filter, kể cả ảnh hưởng đến Timer.

## ObservationFilter nằm ở đâu trong vòng đời?

Một Observation đi qua các giai đoạn chính:

1. Tạo Observation và Context.
2. Chọn convention để xác định tên và key-value mặc định.
3. Chạy ObservationPredicate để quyết định tạo Observation thật hay no-op.
4. Bắt đầu Observation và gọi ObservationHandler.onStart().
5. Trong quá trình thực thi, handler có thể nhận scope, event hoặc error.
6. Khi Observation.stop() được gọi, ObservationFilter biến đổi Context.
7. Sau filter, ObservationHandler.onStop() nhận Context đã được biến đổi.

Sơ đồ:

~~~text
Create Observation + Context
          |
          v
ObservationConvention
  name + key-values
          |
          v
ObservationPredicate
  allow or no-op
          |
          v
Observation.start()
          |
          v
ObservationHandler.onStart()
          |
          v
Scope / Event / Error
          |
          v
Observation.stop()
          |
          v
ObservationFilter.map(context)
          |
          v
ObservationHandler.onStop()
          |
          v
Timer / Span / Log output
~~~

ObservationFilter chỉ tham gia ở bước stop. Nó không chạy thay cho mọi callback và không quyết định Observation có được tạo hay không.

### Vì sao thời điểm áp dụng quan trọng?

DefaultMeterObservationHandler minh họa rõ sự khác biệt giữa các callback:

- Timer được tạo trong onStop và sử dụng low-cardinality key-value có tại thời điểm đó.
- Counter cho Observation event được cập nhật tại thời điểm event xảy ra, dùng low-cardinality key-value có sẵn lúc event.
- LongTaskTimer theo dõi Observation đang chạy được tạo ở onStart và chỉ có low-cardinality key-value có sẵn lúc start.

Do đó, một low-cardinality key được thêm bởi ObservationFilter có thể xuất hiện trên Timer cuối cùng, nhưng không thể xuất hiện ngược vào Counter đã được ghi ở event trước đó hoặc LongTaskTimer đã tạo khi start.

Nếu metadata phải có mặt từ đầu vòng đời, hãy thêm nó trước start bằng ObservationConvention hoặc khi tạo Observation. Dùng filter cho phần hậu xử lý trước onStop.

## Observation.Context chứa những loại thông tin nào?

Observation.Context là một cấu trúc mutable, dạng map, được gắn với Observation. Nó truyền dữ liệu giữa instrumentation và các ObservationHandler.

Có hai nhóm thông tin cần phân biệt:

| API | Mục đích | Có tự trở thành tag không? |
|---|---|---|
| context.put(key, value) | Lưu dữ liệu nội bộ hoặc trạng thái tùy chỉnh | Không |
| addLowCardinalityKeyValue(...) | Thêm metadata có tập giá trị hữu hạn | Có thể thành tag của metrics và tracing |
| addHighCardinalityKeyValue(...) | Thêm metadata có nhiều giá trị hoặc gần như không giới hạn | Dùng cho tracing; không dùng làm tag metrics mặc định |
| removeLowCardinalityKeyValue(key) | Loại low-cardinality key-value khỏi phần metadata trong Context | Không còn được cung cấp từ phần Context đã loại |
| removeHighCardinalityKeyValue(key) | Loại high-cardinality key-value khỏi phần metadata trong Context | Không còn được cung cấp từ phần Context đã loại |

Low cardinality là các giá trị có tập hữu hạn, được kiểm soát, ví dụ region, operation, result hoặc loại message. High cardinality là các giá trị có thể thay đổi gần như theo từng request, ví dụ request ID, user ID hoặc message ID.

Các phương thức removeLowCardinalityKeyValue() và removeHighCardinalityKeyValue() có từ Micrometer 1.10.1. Nếu dự án dùng phiên bản cũ hơn, hãy kiểm tra API theo BOM đang sử dụng trước khi áp dụng ví dụ.

Không dùng context.remove("request.id") để xóa một tag. remove() thao tác trên dữ liệu map nội bộ; hãy dùng removeLowCardinalityKeyValue() hoặc removeHighCardinalityKeyValue() cho metadata tương ứng.

## Bổ sung metadata dùng chung cho mọi Observation

Một trường hợp phổ biến là gắn region hoặc deployment zone cho tất cả Observation. Tạo một filter bất biến, lấy cấu hình một lần và thêm key-value khi Context đi qua filter:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationFilter;

public final class DeploymentObservationFilter implements ObservationFilter {
    private final String region;

    public DeploymentObservationFilter(String region) {
        this.region = region;
    }

    @Override
    public Observation.Context map(Observation.Context context) {
        context.addLowCardinalityKeyValue(
                KeyValue.of("deployment.region", region)
        );
        return context;
    }
}
~~~

Với ứng dụng Spring Boot, có thể khai báo filter thành bean:

~~~java
import io.micrometer.observation.ObservationFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class ObservationConfiguration {

    @Bean
    ObservationFilter deploymentObservationFilter(Environment environment) {
        String region = environment.getProperty(
                "app.deployment.region", "unknown");
        return new DeploymentObservationFilter(region);
    }
}
~~~

Spring Boot tự đăng ký các bean ObservationFilter vào ObservationRegistry được auto-configure. Vì vậy, bean filter ở trên sẽ áp dụng cho những Observation dùng registry đó.

Với ứng dụng không dùng Spring Boot, đăng ký trực tiếp:

~~~java
ObservationRegistry registry = ObservationRegistry.create();
registry.observationConfig()
        .observationFilter(new DeploymentObservationFilter("ap-southeast-1"));
~~~

Hãy dùng tên key có namespace rõ ràng như deployment.region để tránh trùng với key do instrumentation hoặc thư viện khác cung cấp.

## Loại bỏ key-value không còn phù hợp

Filter có thể loại metadata khỏi Context trước khi các handler nhận onStop. Ví dụ, một instrumentation đã gắn request ID để tracing có thể quyết định không chuyển key đó tới các handler xử lý kết thúc:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationFilter;

public final class RequestMetadataFilter implements ObservationFilter {

    @Override
    public Observation.Context map(Observation.Context context) {
        context.removeHighCardinalityKeyValue("request.id");
        context.removeHighCardinalityKeyValue("customer.id");
        return context;
    }
}
~~~

Có thể loại một low-cardinality key nếu nó không còn hữu ích cho output cuối:

~~~java
context.removeLowCardinalityKeyValue("debug.mode");
~~~

Chỉ loại key khi đã xác định rõ handler downstream không cần nó. Xóa một dimension đang được dashboard hoặc alert sử dụng có thể làm mất khả năng phân tích theo chiều đó.

### Filter không phải ranh giới bảo mật

Filter chỉ chạy trước onStop. Một ObservationHandler đã nhận Context ở onStart, onError hoặc event có thể đã đọc, ghi log hoặc đưa dữ liệu vào span trước khi filter chạy. Vì vậy, không đưa mật khẩu, access token, thông tin thanh toán hoặc dữ liệu cá nhân vào Context với hy vọng sẽ xóa chúng ở cuối vòng đời.

Nếu một giá trị tuyệt đối không được phép xuất hiện trong telemetry, hãy loại hoặc biến đổi nó trước khi thêm vào Observation. Filter chỉ là lớp hậu xử lý bổ sung.

## Chuyển high cardinality thành low cardinality có kiểm soát

Một số integration đưa destination name vào high-cardinality key vì destination có thể là temporary queue với tên thay đổi liên tục. Trong hệ thống chỉ dùng một tập queue cố định, destination có thể hữu ích như dimension của metrics.

Chỉ chuyển key sang low cardinality khi giá trị đã được kiểm tra với allow-list:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationFilter;

import java.util.Set;

public final class MessagingDestinationFilter implements ObservationFilter {
    private final Set<String> knownDestinations =
            Set.of("orders", "payments", "dead-letter");

    @Override
    public Observation.Context map(Observation.Context context) {
        KeyValue destination = context.getHighCardinalityKeyValue(
                "messaging.destination.name");

        if (destination != null
                && knownDestinations.contains(destination.getValue())) {
            context.removeHighCardinalityKeyValue(destination.getKey());
            context.addLowCardinalityKeyValue(destination);
        }

        return context;
    }
}
~~~

Kết quả:

- orders, payments và dead-letter được đưa vào low-cardinality metadata.
- Destination không nằm trong allow-list vẫn là high-cardinality metadata.
- Temporary queue hoặc destination động không tạo thêm metric series.

Không chuyển tất cả destination thành low cardinality chỉ vì hiện tại số lượng queue còn nhỏ. Hãy kiểm tra quy trình tạo queue, khả năng xuất hiện tên mới và giới hạn số giá trị trong vận hành.

## Chuẩn hóa thông tin theo loại Context

ObservationRegistry có thể nhận Observation từ HTTP server, database, messaging và code nghiệp vụ. Filter toàn cục nên kiểm tra kiểu Context trước khi truy cập dữ liệu riêng của một instrumentation.

Ví dụ với custom Context:

~~~java
public final class PaymentObservationContext extends Observation.Context {
    private final String paymentMethod;
    private final String rawResult;

    public PaymentObservationContext(String paymentMethod, String rawResult) {
        this.paymentMethod = paymentMethod;
        this.rawResult = rawResult;
    }

    public String getPaymentMethod() {
        return paymentMethod;
    }

    public String getRawResult() {
        return rawResult;
    }
}
~~~

Filter chỉ chuẩn hóa metadata cho loại Context này:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationFilter;

public final class PaymentObservationFilter implements ObservationFilter {

    @Override
    public Observation.Context map(Observation.Context context) {
        if (context instanceof PaymentObservationContext payment) {
            context.addLowCardinalityKeyValue(
                    KeyValue.of("payment.method", normalizePaymentMethod(
                            payment.getPaymentMethod()))
            );

            String result = normalizeResult(payment.getRawResult());
            context.addLowCardinalityKeyValue(
                    KeyValue.of("payment.result", result)
            );
        }

        return context;
    }

    private String normalizeResult(String rawResult) {
        if ("APPROVED".equals(rawResult)) {
            return "approved";
        }
        if ("DECLINED".equals(rawResult) || "REJECTED".equals(rawResult)) {
            return "rejected";
        }
        if ("TIMEOUT".equals(rawResult)) {
            return "timeout";
        }
        return "other";
    }

    private String normalizePaymentMethod(String rawMethod) {
        if ("CARD".equals(rawMethod)) {
            return "card";
        }
        if ("BANK_TRANSFER".equals(rawMethod)) {
            return "bank_transfer";
        }
        if ("WALLET".equals(rawMethod)) {
            return "wallet";
        }
        return "other";
    }
}
~~~

Giá trị đầu ra payment.result có tập cố định gồm approved, rejected, timeout và other; payment.method cũng được giới hạn thành card, bank_transfer, wallet và other. Không đưa rawResult hoặc paymentMethod tùy ý vào metric tag vì chúng có thể chứa mã lỗi, thông điệp hoặc dữ liệu từ hệ thống ngoài.

Nếu filter cần thay đổi field của custom Context, hãy giữ nguyên object Context gốc và trả về chính nó. Không thay bằng một Observation.Context mới vì handler có thể cần các field hoặc kiểu Context cụ thể của instrumentation.

## Phân biệt ObservationFilter với các extension point khác

Các thành phần Observation có trách nhiệm riêng:

| Thành phần | Thời điểm | Trách nhiệm | Kết quả |
|---|---|---|---|
| ObservationConvention | Khi tạo Observation | Định nghĩa tên, contextual name và key-values mặc định | Quy ước metadata |
| ObservationPredicate | Khi quyết định tạo Observation | Cho phép hoặc từ chối tạo Observation | Observation thật hoặc no-op |
| ObservationHandler | Trong các callback lifecycle | Tạo metrics, span, log hoặc hành vi tùy chỉnh | Telemetry output |
| ObservationFilter | Khi stop, trước onStop | Biến đổi Context cuối vòng đời | Context đã hậu xử lý |

Ví dụ:

- Muốn đổi tên http.server.requests thành tên riêng: dùng convention.
- Muốn bỏ qua Observation của một endpoint theo điều kiện: dùng predicate.
- Muốn tạo Timer hoặc Span từ lifecycle: dùng handler.
- Muốn gắn deployment.region cho mọi Observation bất kể convention nào: dùng filter.
- Muốn loại một high-cardinality key trước onStop: dùng filter.

ObservationFilter không thay thế convention. Convention vẫn chịu trách nhiệm định nghĩa metadata chuẩn cho instrumentation; filter bổ sung quy tắc hậu xử lý chung sau khi Observation đã chạy.

ObservationPredicate cũng không phải filter. Predicate trả về boolean và có thể khiến Observation trở thành no-op. ObservationFilter luôn trả về Context đã biến đổi; nó không quyết định có tạo Observation hay không.

## Tác động đến metrics và tracing

DefaultMeterObservationHandler sử dụng low-cardinality key-values làm meter tags. High-cardinality key-values không được thêm vào meter mặc định vì có thể gây bùng nổ cardinality.

Khi filter thêm low-cardinality key-value trước onStop:

- Timer được tạo ở onStop có thể nhận key-value mới.
- Counter của event đã ghi trước đó không được cập nhật ngược.
- LongTaskTimer được tạo ở onStart không nhận key-value chỉ được thêm khi stop.

Tracing handler có lifecycle riêng. Một handler có thể đọc metadata ở onStart, event hoặc onStop. Filter chỉ bảo đảm Context đã biến đổi khi handler nhận onStop; không thể xóa ngược attribute mà handler đã ghi trước đó.

Đây là lý do cần quyết định metadata nào phải có từ đầu, metadata nào chỉ cần ở kết quả cuối và metadata nào không nên đưa vào telemetry.

## Đăng ký nhiều filter và lưu ý concurrency

Có thể đăng ký nhiều ObservationFilter:

~~~java
registry.observationConfig()
        .observationFilter(new DeploymentObservationFilter("ap-southeast-1"))
        .observationFilter(new RequestMetadataFilter())
        .observationFilter(new MessagingDestinationFilter());
~~~

Mỗi filter nên có một trách nhiệm rõ ràng. Nếu filter sau phụ thuộc kết quả của filter trước, hãy kiểm thử thứ tự áp dụng trên đúng phiên bản Micrometer của ứng dụng. Với một quy trình biến đổi phức tạp, một filter điều phối duy nhất có thể dễ hiểu hơn nhiều filter cùng sửa một key.

ObservationRegistry thường được dùng chung giữa nhiều thread. Filter phải an toàn khi được gọi đồng thời:

- Ưu tiên field final và cấu hình bất biến.
- Không lưu Context hiện tại vào field dùng chung.
- Không giữ dữ liệu của một request để dùng cho Observation tiếp theo.
- Tránh gọi dịch vụ mạng hoặc thao tác blocking trong map().
- Không thay đổi cấu hình registry sau khi ứng dụng đã bắt đầu xử lý tải nếu không có lý do rõ ràng.

map() chạy ở đường kết thúc Observation. Logic chậm ở đây có thể làm tăng latency của luồng kết thúc request hoặc task.

## Kiểm thử ObservationFilter

Nên kiểm thử hai hành vi: Context được biến đổi trước onStop và low-cardinality metadata được dùng để tạo Timer.

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationFilter;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.DefaultMeterObservationHandler;
import org.junit.jupiter.api.Test;

import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;

class ObservationFilterTest {

    @Test
    void enrichesTimerAndRemovesHighCardinalityValueBeforeOnStop() {
        SimpleMeterRegistry meterRegistry = new SimpleMeterRegistry();
        ObservationRegistry observationRegistry = ObservationRegistry.create();
        AtomicReference<KeyValue> valueAtStart = new AtomicReference<>();
        AtomicReference<Observation.Context> contextAtStop = new AtomicReference<>();

        ObservationFilter filter = context -> {
            context.addLowCardinalityKeyValue(
                    KeyValue.of("deployment.region", "ap-southeast-1"));
            context.removeHighCardinalityKeyValue("request.id");
            return context;
        };

        ObservationHandler<Observation.Context> captureHandler =
                new ObservationHandler<>() {
                    @Override
                    public void onStart(Observation.Context context) {
                        valueAtStart.set(
                                context.getHighCardinalityKeyValue("request.id"));
                    }

                    @Override
                    public void onError(Observation.Context context) {
                    }

                    @Override
                    public void onEvent(
                            Observation.Event event,
                            Observation.Context context) {
                    }

                    @Override
                    public void onStop(Observation.Context context) {
                        contextAtStop.set(context);
                    }

                    @Override
                    public boolean supportsContext(Observation.Context context) {
                        return true;
                    }
                };

        observationRegistry.observationConfig()
                .observationFilter(filter)
                .observationHandler(
                        DefaultMeterObservationHandler.builder(meterRegistry).build())
                .observationHandler(captureHandler);

        try {
            Observation.createNotStarted("payment.authorize", observationRegistry)
                    .lowCardinalityKeyValue("payment.method", "card")
                    .highCardinalityKeyValue("request.id", "req-123")
                    .observe(() -> {
                    });

            Timer timer = meterRegistry.get("payment.authorize")
                    .tag("payment.method", "card")
                    .tag("deployment.region", "ap-southeast-1")
                    .timer();

            assertThat(timer.count()).isEqualTo(1);
            assertThat(valueAtStart.get()).isEqualTo(
                    KeyValue.of("request.id", "req-123"));
            assertThat(contextAtStop.get()).isNotNull();
            assertThat(contextAtStop.get()
                    .getHighCardinalityKeyValue("request.id")).isNull();
        } finally {
            meterRegistry.close();
        }
    }
}
~~~

Test chứng minh:

1. Handler onStart đã nhìn thấy request.id trước khi filter chạy.
2. Filter thêm deployment.region vào low-cardinality metadata.
3. Filter loại request.id trước onStop.
4. Timer được tạo với payment.method và deployment.region.

Đây cũng là bằng chứng filter không phải cơ chế bảo mật để xóa dữ liệu khỏi mọi handler: handler onStart đã có thể đọc giá trị trước khi filter chạy.

### Kiểm thử chuyển high sang low

Với MessagingDestinationFilter, hãy kiểm thử ít nhất hai trường hợp:

- Destination nằm trong allow-list được chuyển sang low cardinality và bị loại khỏi high cardinality.
- Destination động không nằm trong allow-list vẫn giữ ở high cardinality.

Không chỉ kiểm thử một queue cố định rồi giả định mọi destination trong production đều có cardinality thấp.

## Những lỗi thường gặp

**Dùng ObservationFilter để đặt metadata cần cho onStart.** Filter chỉ chạy khi stop. Hãy dùng convention hoặc thêm key-value trước start.

**Dùng filter để tắt Observation.** Filter không trả quyết định allow/deny. Dùng ObservationPredicate nếu muốn tạo no-op Observation.

**Nhầm context.put() với metric tag.** put() lưu state nội bộ; dùng addLowCardinalityKeyValue() hoặc addHighCardinalityKeyValue() cho metadata.

**Đưa ID riêng vào low cardinality.** Request ID, user ID và message ID không phải metric tag. Giữ chúng ở high cardinality cho tracing nếu chính sách cho phép, hoặc không đưa vào telemetry.

**Chuyển mọi high-cardinality key thành low-cardinality.** Chỉ chuyển khi có allow-list và giới hạn số giá trị rõ ràng.

**Cho rằng remove ở onStop xóa dữ liệu đã phát trước đó.** Handler có thể đã đọc Context ở onStart hoặc event. Loại dữ liệu nhạy cảm trước khi đưa vào Observation.

**Thay Context bằng một object mới.** Việc này có thể làm mất field riêng của instrumentation. Hãy biến đổi Context gốc và trả lại chính nó.

**Gọi API bên ngoài trong map().** Filter chạy khi stop; logic blocking sẽ kéo dài luồng kết thúc Observation.

**Tạo state dùng chung trong filter.** Context của nhiều Observation có thể đi qua cùng filter đồng thời. Không lưu request data trong field dùng chung.

**Để nhiều filter ghi đè cùng key mà không có quy ước.** Chọn ownership rõ ràng cho từng key và kiểm thử thứ tự khi có phụ thuộc.

## Checklist triển khai

1. Xác định metadata cần bổ sung hoặc loại bỏ.
2. Xác định metadata phải có ở onStart, event hay chỉ cần ở onStop.
3. Dùng ObservationConvention cho tên và key-value mặc định.
4. Dùng ObservationPredicate để bỏ qua Observation.
5. Dùng ObservationFilter cho hậu xử lý Context trước onStop.
6. Phân biệt dữ liệu nội bộ trong Context với low/high-cardinality key-values.
7. Giữ low-cardinality values trong tập hữu hạn.
8. Chỉ chuyển high sang low khi đã có allow-list.
9. Không dựa vào filter để xóa dữ liệu nhạy cảm đã được handler tiêu thụ.
10. Giữ filter bất biến, nhanh và thread-safe.
11. Kiểm thử cả onStart, onStop, Timer tags và các key-value đã bị loại.
12. Xác minh LongTaskTimer và event counters không cần metadata chỉ được thêm ở stop.

## Kết luận

ObservationFilter là bước hậu xử lý cho Observation.Context khi Observation dừng, ngay trước các callback onStop của handler. Nó có thể thêm low/high-cardinality key-values, loại metadata hoặc chuẩn hóa Context theo loại instrumentation. Hãy dùng convention để định nghĩa metadata mặc định, predicate để quyết định có tạo Observation và handler để tạo telemetry; dùng filter cho chính sách chung ở cuối vòng đời. Vì filter chạy muộn, nó không sửa ngược thông tin đã được handler tiêu thụ ở onStart hoặc event và không thay thế việc loại dữ liệu nhạy cảm ngay tại nguồn.

## Tài liệu tham khảo

- [Micrometer - Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html): vòng đời Observation, Context, Handler, Convention, Predicate và Filter.
- [Micrometer - Observation Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): low/high-cardinality key-values và cách Observation truyền Context.
- [Spring Boot - Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): tự động đăng ký ObservationFilter beans và ObservationRegistryCustomizer.
- [Micrometer - JMS Instrumentation](https://docs.micrometer.io/micrometer/reference/reference/jms.html): ví dụ chuyển destination name từ high sang low cardinality khi destination được giới hạn.
