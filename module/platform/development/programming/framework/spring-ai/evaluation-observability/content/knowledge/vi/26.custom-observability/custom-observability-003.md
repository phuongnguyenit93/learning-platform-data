# Sử dụng filter, predicate hoặc handler theo cơ chế Micrometer

> **Chương:** Quan sát tùy chỉnh
>
> **Module:** SPRING_AI_EVALUATION_OBSERVABILITY — đánh giá chất lượng ứng dụng Spring AI bằng tập dữ liệu, tiêu chí relevance, fact checking và kiểm thử luồng RAG hoặc gọi công cụ. Đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện nguyên nhân suy giảm chất lượng qua từng phiên bản prompt, model và pipeline.
>
> **Bối cảnh kỹ thuật:** Java 21, Spring Boot 4.2.x và Spring AI 2.1.x. Ví dụ dùng Micrometer Observation API; cần đối chiếu extension points và dependency versions với BOM thực tế của ứng dụng.

## 1. Vì sao cần filter, predicate và handler?

Một ứng dụng Spring AI có thể tạo nhiều Observation cho cùng một request:
- business task bao trọn workflow;
- retrieval, prompt preparation và answer validation;
- ChatClient/ChatModel, EmbeddingModel, VectorStore;
- tool execution và các lần retry.

Sau khi instrumentation hoạt động, nhóm phát triển thường cần giải quyết ba nhu cầu khác nhau:

1. **Có nên tạo observation này không?** Ví dụ bỏ qua một số observation debug nội bộ hoặc operation quá nhiễu.
2. **Cần bổ sung hoặc chuẩn hóa metadata nào?** Ví dụ thêm outcome sau khi workflow kết thúc hoặc chuẩn hóa một key chung.
3. **Cần làm gì khi observation start/error/stop?** Ví dụ ghi một business counter hoặc kết nối với hệ thống nội bộ.

Micrometer Observation cung cấp ba extension points tương ứng:

| Extension point | Câu hỏi chính | Vai trò |
|---|---|---|
| ObservationPredicate | Có ghi nhận observation này không? | Chấp nhận hoặc loại observation trước khi instrumentation chạy |
| ObservationFilter | Context cần được bổ sung/biến đổi ra sao? | Chuẩn hóa metadata trong lifecycle |
| ObservationHandler | Cần phản ứng thế nào với lifecycle event? | Ghi nhận, tạo meter/span hoặc tích hợp logic quan sát |

Ba thành phần này không thay thế nhau. Dùng sai extension point có thể làm mất metrics, tạo tags sai, tăng latency hoặc vô tình loại bỏ cả trace lẫn meter.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt Predicate, Filter và Handler.
2. Chọn đúng extension point cho một yêu cầu observability.
3. Đăng ký chúng vào ObservationRegistry do Spring Boot quản lý.
4. Lọc observation theo name và context có kiểm soát.
5. Bổ sung metadata bằng ObservationFilter ở đúng thời điểm.
6. Xử lý outcome cuối cùng mà không gắn nhãn sai từ đầu request.
7. Viết ObservationHandler có phạm vi context rõ ràng.
8. Tránh duplicate metrics/traces và handler blocking.
9. Phân biệt predicate filtering với trace sampling.
10. Kiểm thử từng extension point và lifecycle.
11. Áp dụng cho business task, RAG, tool calling và evaluation.
12. Thiết kế policy bảo mật, cardinality và vận hành cho telemetry.

## 2. Vị trí của ba extension points trong Observation lifecycle

Micrometer Observation có một lifecycle điển hình:

~~~text
Application creates Observation
        |
        v
ObservationPredicate
  | false -> NOOP observation
  | true
  v
ObservationConvention / Context
        |
        v
start()
  ├── ObservationHandler.onStart()
  └── open scope
        |
        v
business operation executes
  ├── ObservationHandler.onEvent()
  ├── ObservationHandler.onError() nếu có exception
  └── scope open/close callbacks
        |
        v
stop()
  ├── ObservationFilter.map(context)
  └── ObservationHandler.onStop()
        |
        v
meters / spans / custom counters
~~~

Đây là mô hình khái niệm của lifecycle. Chi tiết callback và thời điểm context được exporter đọc phụ thuộc phiên bản Micrometer và handlers đã đăng ký.

Điểm cần nhớ:
- Predicate quyết định observation có được tạo/ghi nhận hay không.
- Filter biến đổi context trong quá trình hoàn tất observation.
- Handler nhận các lifecycle callbacks và thực hiện công việc quan sát.
- Convention chịu trách nhiệm tên và key-values theo context type; chủ đề này đã được trình bày ở bài đăng ký convention.

## 3. ObservationPredicate: quyết định observation có được ghi nhận

ObservationPredicate nhận observation name và context, sau đó trả về boolean.

- true: cho phép observation tiếp tục lifecycle bình thường.
- false: observation trở thành NOOP; các handlers không ghi nhận operation đó.

Ví dụ, ứng dụng có thể loại một nhóm observation debug nội bộ:

~~~java
registry.observationConfig().observationPredicate(
        (name, context) -> !name.startsWith("app.ai.internal.debug."));
~~~

Predicate không hủy business operation. Code trong observe(...) vẫn chạy; chỉ phần instrumentation của observation bị bỏ qua.

### Predicate phù hợp khi nào?

- Loại observation debug/test không cần xuất telemetry.
- Loại operation nội bộ có volume lớn nhưng không có giá trị vận hành.
- Chặn một nhóm observation theo policy instrumentation đã thống nhất.
- Bật/tắt một nhóm custom observations trong môi trường cụ thể.

### Predicate không phù hợp khi nào?

- Muốn thêm tags: dùng Filter hoặc Convention.
- Muốn đếm outcome: dùng Handler hoặc metric riêng.
- Muốn giảm tỷ lệ trace: dùng tracing sampler.
- Muốn chặn user hoặc ngăn tool execution: dùng authorization/business policy.
- Muốn che dữ liệu nhạy cảm: không đưa dữ liệu đó vào context; predicate không phải cơ chế redaction.

Predicate có thể làm mất cả meter và span của observation đó. Vì vậy, không loại một observation quan trọng chỉ để giảm noise trên dashboard.

## 4. Thiết kế Predicate theo tên và context

Predicate có hai đầu vào:
- name: tên observation đã được xác định;
- context: dữ liệu gắn với operation.

Nên ưu tiên tên ổn định và context type có cấu trúc.

Ví dụ:
- Bỏ qua app.ai.internal.debug.*;
- Giữ app.ai.business.task.
- Giữ spring.ai.* hoặc tên framework convention đang sử dụng.
- Không quyết định bằng cách phân tích raw prompt hay exception message.

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationPredicate;

public final class AiObservationPredicate implements ObservationPredicate {

    @Override
    public boolean test(String name, Observation.Context context) {
        if (name == null) {
            return false;
        }

        if (name.startsWith("app.ai.internal.debug.")) {
            return false;
        }

        return true;
    }
}
~~~

Ví dụ trên loại duy nhất namespace debug. Production policy nên allow/deny rõ ràng theo taxonomy thực tế, có test để bảo đảm business observations và Spring AI component observations quan trọng vẫn được giữ.

### Không dựa vào thứ tự đăng ký tình cờ

Nếu có nhiều predicates, hãy xác định cách chúng kết hợp theo API/version đang dùng. Tập trung policy ở một nơi hoặc viết test cho các trường hợp giao nhau. Đừng để nhiều bean độc lập cùng âm thầm loại một observation.

## 5. Predicate không phải tracing sampler

Đây là khác biệt quan trọng:

| Cơ chế | Phạm vi | Kết quả |
|---|---|---|
| ObservationPredicate | Observation | Có tạo/ghi nhận observation hay không |
| Tracing sampler | Span/trace | Trace/span nào được lấy mẫu và export |
| Meter filter | Meter registration | Meter nào được đăng ký hoặc cấu hình |
| Logging level/filter | Log event | Log nào được ghi |

Nếu Predicate trả false, meter handler và tracing handler của observation đều không nhận lifecycle như bình thường. Nếu tracing sampler không lấy trace, metrics từ meter handler vẫn có thể được ghi.

Ví dụ, muốn metrics cho mọi request nhưng chỉ export 10% traces, hãy cấu hình tracing sampling ở tracing bridge. Không dùng ObservationPredicate để thay sampler vì điều đó có thể làm mất luôn metrics.

## 6. ObservationFilter: bổ sung hoặc chuẩn hóa context

ObservationFilter nhận Observation.Context, có thể bổ sung hoặc biến đổi context và trả lại context đó.

Một filter phù hợp cho các thay đổi metadata có tính cross-cutting:
- thêm environment classification đã được cấu hình;
- chuẩn hóa một key chung;
- thêm outcome đã biết tại thời điểm kết thúc;
- áp dụng một quy ước metadata chung cho một loại context.

Ví dụ filter bổ sung outcome khi business task kết thúc:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationFilter;

public final class BusinessOutcomeObservationFilter
        implements ObservationFilter {

    @Override
    public Observation.Context map(Observation.Context context) {
        if (context instanceof BusinessTaskContext task) {
            context.addLowCardinalityKeyValue(
                    KeyValue.of("outcome", task.outcome().tagValue()));
        }
        return context;
    }
}
~~~

BusinessTaskContext trong ví dụ là context nghiệp vụ có field outcome được cập nhật trước khi observation stop. Key outcome phải có vocabulary đóng như success, rejected, abstained, error, timeout.

### Vì sao thêm outcome bằng Filter?

Khi business task bắt đầu, chưa thể biết nó sẽ thành công, timeout hay bị policy từ chối. Nếu gắn outcome=success từ đầu, metric và span có thể mang nhãn sai.

Filter chạy trong quá trình hoàn tất Observation, vì vậy có thể đọc terminal outcome đã được cập nhật trước khi stop và bổ sung tag cho handlers xử lý lúc kết thúc. Cần xác minh chính xác callback order trên Micrometer version của ứng dụng bằng integration test.

Không thêm cùng key ở cả factory, convention và filter. Chọn một nơi sở hữu key outcome.

## 7. ObservationFilter không phải bộ lọc bảo mật

Filter có thể biến đổi context nhưng không nên được xem là lớp bảo vệ duy nhất cho dữ liệu nhạy cảm.

Không đưa các dữ liệu sau vào Observation ngay từ đầu:
- raw prompt hoặc conversation history;
- email, số điện thoại, account ID;
- API key, access token, cookie;
- raw tool arguments;
- toàn bộ document content;
- dữ liệu thanh toán hoặc thông tin cá nhân.

Nếu một handler hoặc exporter đã nhận dữ liệu nhạy cảm trước khi filter chạy, việc xóa key ở filter có thể đã quá muộn.

Thiết kế an toàn là:
1. Chỉ đưa metadata cần thiết vào context.
2. Dùng enum và opaque references có policy.
3. Chọn high-cardinality attributes có retention/access control.
4. Kiểm tra payload thực tế ở staging.
5. Không dựa vào filter để làm sạch raw content.

## 8. Khi nào dùng Convention, khi nào dùng Filter?

Hai extension points này dễ bị dùng nhầm.

| Nhu cầu | Extension phù hợp |
|---|---|
| Đặt observation name theo context type | ObservationConvention |
| Chọn contextual name | ObservationConvention |
| Chuẩn hóa low/high-cardinality keys cho một loại observation | ObservationConvention |
| Bổ sung outcome sau khi business operation hoàn tất | ObservationFilter |
| Thêm metadata chung cho nhiều loại observation | ObservationFilter |
| Chuyển context thành meter/span | ObservationHandler |
| Loại observation theo policy | ObservationPredicate |

Convention diễn tả taxonomy của loại operation. Filter thực hiện biến đổi context mang tính bổ sung hoặc cross-cutting. Nếu một key là phần cốt lõi của schema một context type, ưu tiên Convention; nếu key chỉ có thể biết ở giai đoạn cuối hoặc áp dụng chung, cân nhắc Filter.

## 9. ObservationHandler: phản ứng với lifecycle callbacks

ObservationHandler nhận các callbacks khi observation thay đổi trạng thái.

| Callback | Thời điểm / mục đích |
|---|---|
| supportsContext | Xác định handler có xử lý context này không |
| onStart | Observation bắt đầu |
| onError | Operation ghi nhận exception |
| onEvent | Observation phát ra event |
| onScopeOpened | Context được mở trong execution scope |
| onScopeClosed | Scope được đóng |
| onScopeReset | Scope được reset |
| onStop | Observation hoàn tất |

Handlers là nơi các integration biến Observation thành meter hoặc span. Spring Boot/Micrometer có thể đã đăng ký các handlers mặc định. Khi thêm custom handler, phải giữ nguyên những handlers đang hoạt động.

### Khi nào viết custom handler?

- Ghi business completion counter có vocabulary riêng.
- Chuyển một lifecycle event sang in-memory queue nội bộ.
- Tích hợp với hệ thống telemetry không có exporter phù hợp.
- Kiểm thử callbacks và metadata.
- Bổ sung logic quan sát domain-specific mà meter/tracing handlers mặc định không cung cấp.

Không viết custom handler chỉ để tạo lại timer/span đã có sẵn. Điều đó có thể đếm trùng hoặc làm trace tree rối hơn.

## 10. Handler phải giới hạn đúng context type

Handler thường được đăng ký ở cấp registry và có thể gặp nhiều loại Observation.Context. Vì vậy supportsContext cần kiểm tra context mà handler hiểu.

Ví dụ:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;

public final class BusinessTaskLifecycleHandler
        implements ObservationHandler<Observation.Context> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof BusinessTaskContext;
    }

    @Override
    public void onStart(Observation.Context context) {
        BusinessTaskContext task = (BusinessTaskContext) context;
        // Ghi nhận thông tin bắt đầu có cardinality thấp.
    }

    @Override
    public void onStop(Observation.Context context) {
        BusinessTaskContext task = (BusinessTaskContext) context;
        // Xử lý completion sau khi task kết thúc.
    }
}
~~~

Dùng generic Observation.Context và kiểm tra instanceof giúp handler không bị gọi nhầm với context của Spring MVC, database hoặc Spring AI component khác.

Không viết supportsContext luôn trả true rồi ép kiểu trong callback. Nếu handler không hiểu context, nó phải trả false.

## 11. Ví dụ custom context có terminal outcome

Một context có thể giữ dữ liệu cần cho handler và filter:

~~~java
package com.example.ai.observability;

import io.micrometer.observation.Observation;
import java.util.Objects;

public final class BusinessTaskContext extends Observation.Context {

    public enum Workflow {
        SUPPORT_ANSWER,
        ORDER_LOOKUP,
        POLICY_SUMMARY
    }

    public enum Outcome {
        UNKNOWN,
        SUCCESS,
        ABSTAINED,
        REJECTED,
        NOT_FOUND,
        ERROR,
        TIMEOUT;

        public String tagValue() {
            return name().toLowerCase(java.util.Locale.ROOT);
        }
    }

    private final Workflow workflow;
    private Outcome outcome = Outcome.UNKNOWN;

    public BusinessTaskContext(Workflow workflow) {
        this.workflow = Objects.requireNonNull(workflow, "workflow");
    }

    public Workflow workflow() {
        return workflow;
    }

    public Outcome outcome() {
        return outcome;
    }

    public void markOutcome(Outcome outcome) {
        if (this.outcome != Outcome.UNKNOWN) {
            throw new IllegalStateException("Outcome was already assigned");
        }
        this.outcome = Objects.requireNonNull(outcome, "outcome");
    }
}
~~~

Outcome chỉ được gán một lần, ở nơi workflow biết terminal result. Nếu có retry bên trong task, retry outcome là metadata của attempt riêng; không ghi đè terminal outcome của business task.

Không dùng chuỗi outcome tùy ý lấy từ user hoặc exception message. Enum giúp giới hạn số series metrics.

## 12. Kết hợp Filter và Handler cho business completion

Ví dụ filter thêm outcome vào context trước khi handlers hoàn tất observation:

~~~java
registry.observationConfig().observationFilter(context -> {
    if (context instanceof BusinessTaskContext task) {
        context.addLowCardinalityKeyValue(
                KeyValue.of("outcome", task.outcome().tagValue()));
    }
    return context;
});
~~~

Handler có thể đếm business task đã hoàn tất:

~~~java
package com.example.ai.observability;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;

public final class BusinessTaskCompletionHandler
        implements ObservationHandler<Observation.Context> {

    private final MeterRegistry meterRegistry;

    public BusinessTaskCompletionHandler(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof BusinessTaskContext;
    }

    @Override
    public void onError(Observation.Context context) {
        BusinessTaskContext task = (BusinessTaskContext) context;
        if (task.outcome() == BusinessTaskContext.Outcome.UNKNOWN) {
            task.markOutcome(BusinessTaskContext.Outcome.ERROR);
        }
    }

    @Override
    public void onStop(Observation.Context context) {
        BusinessTaskContext task = (BusinessTaskContext) context;

        Counter.builder("app.ai.business.task.completed")
                .description("Completed AI business tasks by workflow and outcome")
                .tag("workflow", task.workflow().name().toLowerCase(
                        java.util.Locale.ROOT))
                .tag("outcome", task.outcome().tagValue())
                .register(meterRegistry)
                .increment();
    }
}
~~~

Handler trên chỉ tăng counter trong MeterRegistry. Không gọi HTTP hoặc ghi đồng bộ vào database trong callback. Metric name và tag values phải nằm trong schema đã thống nhất.

Spring Boot có thể đã xuất duration/count cho Observation thông qua meter handler mặc định. Custom completion counter là metric domain-specific; hãy xác nhận dashboard không đếm cùng một khái niệm hai lần.

## 13. Đặt outcome đúng thời điểm trong application service

Workflow phải cập nhật outcome trước khi Observation dừng:

~~~java
package com.example.ai.observability;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.util.function.Supplier;

public final class SupportTaskRunner {

    private final ObservationRegistry registry;

    public SupportTaskRunner(ObservationRegistry registry) {
        this.registry = registry;
    }

    public <T> T run(Supplier<T> work) {
        BusinessTaskContext context = new BusinessTaskContext(
                BusinessTaskContext.Workflow.SUPPORT_ANSWER);

        Observation observation = Observation.createNotStarted(
                "app.ai.business.task",
                () -> context,
                registry);

        return observation.observe(() -> {
            try {
                T result = work.get();
                context.markOutcome(BusinessTaskContext.Outcome.SUCCESS);
                return result;
            } catch (PolicyRejectedException ex) {
                context.markOutcome(BusinessTaskContext.Outcome.REJECTED);
                throw ex;
            } catch (RuntimeException ex) {
                context.markOutcome(BusinessTaskContext.Outcome.ERROR);
                throw ex;
            }
        });
    }
}
~~~

Ví dụ dùng PolicyRejectedException như một exception nghiệp vụ riêng của ứng dụng. Nếu rejection là kết quả bình thường được trả về như một value, hãy gán REJECTED trước khi return thay vì ném exception.

Với timeout do deadline, gán TIMEOUT ở nơi timeout được xác định. Nếu exception phát sinh trước khi application code phân loại được, onError có thể dùng ERROR làm fallback.

Không bắt mọi Throwable rồi nuốt lỗi chỉ để observation được stop; observe(...) đã quản lý lifecycle và exception propagation.

## 14. Đăng ký Predicate, Filter và Handler trong Spring Boot

Spring Boot cung cấp ObservationRegistry do container quản lý. Có thể đăng ký các extension points bằng ObservationRegistryCustomizer.

~~~java
package com.example.ai.observability;

import io.micrometer.common.KeyValue;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.boot.actuate.autoconfigure.observation.ObservationRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import io.micrometer.core.instrument.MeterRegistry;

@Configuration
public class AiObservationConfiguration {

    @Bean
    ObservationRegistryCustomizer<ObservationRegistry> aiObservationCustomizer(
            MeterRegistry meterRegistry) {

        return registry -> {
            var config = registry.observationConfig();

            config.observationPredicate((name, context) ->
                    !name.startsWith("app.ai.internal.debug."));

            config.observationFilter(context -> {
                if (context instanceof BusinessTaskContext task) {
                    context.addLowCardinalityKeyValue(
                            KeyValue.of("outcome", task.outcome().tagValue()));
                }
                return context;
            });

            config.observationHandler(
                    new BusinessTaskCompletionHandler(meterRegistry));
        };
    }
}
~~~

Đây là một registration path minh họa. Kiểm tra package/API ObservationRegistryCustomizer theo Spring Boot BOM của ứng dụng. Đừng tạo ObservationRegistry riêng cho mỗi request hoặc thay thế registry auto-configured, vì có thể làm mất tracing/meter handlers mặc định.

Nếu đã có nhiều customizers, hãy review chúng cùng nhau để phát hiện:
- predicate chồng lấn;
- filter thêm duplicate keys;
- handler nhận nhầm context;
- handler registration lặp;
- thay đổi semantics của metric series.

## 15. Thứ tự và tương tác giữa Filter với Handler

Filter thường được áp dụng khi Observation kết thúc để handlers có thể đọc context đã được bổ sung. Vì vậy:
- outcome phải được gán trước khi stop;
- filter chỉ nên thực hiện phép biến đổi nhanh, xác định;
- handler onStop đọc context sau filter theo lifecycle của phiên bản Micrometer;
- integration test phải xác minh low-cardinality key được meter handler nhìn thấy.

Không dựa vào thứ tự của nhiều filters nếu chúng cùng sửa một key. Hãy chỉ định một owner cho mỗi metadata key hoặc gộp logic liên quan vào một filter rõ ràng.

Không thêm lại một key đã có trong convention. Nếu convention và filter cùng sở hữu outcome, metrics có thể xuất duplicate values hoặc kết quả phụ thuộc implementation.

## 16. Handler không phải nơi chạy công việc nặng

Callback lifecycle thường nằm trên đường thực thi của operation. Nếu handler làm công việc chậm, nó có thể làm chậm request.

Tránh:
- gọi HTTP tới telemetry server trong onStop;
- ghi database đồng bộ;
- gọi LLM để phân loại exception;
- serialize toàn bộ context;
- đọc file hoặc query repository;
- thực hiện retry/network backoff trong callback.

Nên:
- dùng MeterRegistry để cập nhật counter/timer trong memory;
- dùng tracing bridge/exporter đã được cấu hình;
- nếu cần xử lý riêng, đẩy một event nhỏ vào queue bounded/non-blocking;
- có policy xử lý queue đầy;
- tránh giữ object request/document lớn trong event.

Không tạo một executor không giới hạn chỉ để chuyển việc nặng khỏi handler. Queue phải có capacity, backpressure/drop policy và metric riêng.

## 17. Khi nào dùng ObservationHandler và khi nào dùng ObservationFilter?

| Nhu cầu | Filter | Handler |
|---|---:|---:|
| Chuẩn hóa context | Phù hợp | Không phải mục tiêu chính |
| Thêm terminal outcome tag trước khi stop | Phù hợp | Có thể đọc/ghi event |
| Ghi completion counter | Không | Phù hợp |
| Tạo span/timer | Không | Thường do handler mặc định |
| Gửi business completion event vào queue | Không | Phù hợp |
| Xóa dữ liệu nhạy cảm đã được ghi | Không nên dựa vào | Không nên dựa vào |
| Thực hiện authorization | Không | Không |
| Thay đổi observation name theo context type | Convention | Không |

Một rule dễ áp dụng:
- Predicate: có giữ observation hay không?
- Convention: operation được gọi tên và gắn tags cơ bản ra sao?
- Filter: context cần được bổ sung/chuẩn hóa gì khi hoàn tất?
- Handler: khi lifecycle diễn ra, cần ghi nhận hoặc export điều gì?

## 18. Không để custom handler nhân đôi instrumentation mặc định

Spring Boot/Micrometer có thể tự đăng ký:
- meter observation handler;
- tracing observation handler;
- logging/correlation integration tùy cấu hình.

Custom handler không nên tạo lại span hoặc timer cho operation đã có instrumentation mặc định.

Ví dụ, Spring AI đã instrument ChatModel call:
- giữ observation của ChatModel;
- tạo business parent bao toàn bộ request;
- thêm filter cho business outcome nếu cần;
- thêm handler cho completion counter domain-specific;
- không tạo thêm custom ChatModel span cùng boundary chỉ để lấy duration.

Khi kiểm tra registry, đừng xóa các handlers mặc định để đơn giản hóa test rồi kết luận cấu hình production tương tự.

## 19. Áp dụng Predicate cho Spring AI RAG và tool calling

Predicate nên loại những observation thật sự không cần thiết, chẳng hạn custom debug spans được tạo trong môi trường dev. Không loại toàn bộ tool hoặc model observations chỉ vì chúng có volume cao; đó có thể là dữ liệu quan trọng nhất để giải thích latency/cost.

Ví dụ policy:

| Observation group | Predicate policy |
|---|---|
| app.ai.business.task | Keep |
| app.ai.rag.retrieve | Keep |
| spring.ai.chat.* | Keep theo tên thực tế của phiên bản |
| app.ai.internal.debug.* | Drop |
| synthetic probe không thuộc production SLO | Có thể drop nếu policy đã ghi rõ |

Tên observation của Spring AI có thể khác giữa các phiên bản và integrations. Kiểm tra registry/traces thực tế trước khi viết name-based predicate.

Không dùng predicate để loại case evaluation khó hoặc request có outcome fail. Làm vậy sẽ tạo measurement bias và khiến metrics có vẻ tốt hơn.

## 20. Filter và Handler cho evaluation pipeline

Evaluation offline có thể cần metadata:
- suite;
- dataset revision;
- evaluator role;
- outcome;
- severity;
- run reference.

Dùng low-cardinality tags cho suite/metric/outcome nếu tập giá trị được giới hạn. Dataset/run/case references thường phù hợp hơn với report store hoặc trace attributes có retention policy.

Một filter có thể thêm evaluation.outcome vào context khi case kết thúc. Handler có thể tăng counter theo suite, metric và outcome. Không thêm raw question, expected answer hoặc model response vào metrics/traces.

Nếu judge bị lỗi, phân biệt evaluation_error với case_fail. Một lỗi chấm điểm không có nghĩa model answer đã sai.

## 21. Kiểm thử Predicate

Predicate có thể kiểm thử bằng registry và handler đếm số lần onStart.

~~~java
package com.example.ai.observability;

import static org.junit.jupiter.api.Assertions.assertEquals;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class AiObservationPredicateTest {

    @Test
    void skipsOnlyInternalDebugObservations() {
        ObservationRegistry registry = ObservationRegistry.create();
        AtomicInteger starts = new AtomicInteger();

        registry.observationConfig().observationPredicate(
                (name, context) ->
                        !name.startsWith("app.ai.internal.debug."));

        registry.observationConfig().observationHandler(
                new ObservationHandler<Observation.Context>() {
                    @Override
                    public boolean supportsContext(Observation.Context context) {
                        return true;
                    }

                    @Override
                    public void onStart(Observation.Context context) {
                        starts.incrementAndGet();
                    }
                });

        Observation.createNotStarted(
                "app.ai.internal.debug.probe", registry)
                .observe(() -> "debug");

        Observation.createNotStarted(
                "app.ai.business.task", registry)
                .observe(() -> "business");

        assertEquals(1, starts.get());
    }
}
~~~

Test này chứng minh Predicate bỏ qua lifecycle instrumentation của debug observation nhưng business observation vẫn được ghi nhận. Business supplier vẫn chạy trong cả hai trường hợp.

## 22. Kiểm thử Filter và Handler

Test filter cần xác nhận key được thêm vào context khi observation hoàn tất. Test handler cần xác nhận callbacks chỉ chạy với context mà handler hỗ trợ.

~~~java
package com.example.ai.observability;

import static org.junit.jupiter.api.Assertions.*;

import io.micrometer.common.KeyValue;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class AiObservationFilterHandlerTest {

    @Test
    void filterAddsTerminalOutcomeBeforeStopHandlerReadsContext() {
        ObservationRegistry registry = ObservationRegistry.create();
        BusinessTaskContext task = new BusinessTaskContext(
                BusinessTaskContext.Workflow.SUPPORT_ANSWER);

        registry.observationConfig().observationFilter(context -> {
            if (context instanceof BusinessTaskContext businessTask) {
                context.addLowCardinalityKeyValue(
                        KeyValue.of("outcome",
                                businessTask.outcome().tagValue()));
            }
            return context;
        });

        List<KeyValue> stoppedValues = new ArrayList<>();
        registry.observationConfig().observationHandler(
                new ObservationHandler<Observation.Context>() {
                    @Override
                    public boolean supportsContext(Observation.Context context) {
                        return context instanceof BusinessTaskContext;
                    }

                    @Override
                    public void onStop(Observation.Context context) {
                        context.getLowCardinalityKeyValues()
                                .forEach(stoppedValues::add);
                    }
                });

        Observation.createNotStarted(
                "app.ai.business.task",
                () -> task,
                registry)
                .observe(() -> {
                    task.markOutcome(BusinessTaskContext.Outcome.SUCCESS);
                    return "done";
                });

        assertTrue(stoppedValues.contains(KeyValue.of("outcome", "success")));
    }

    @Test
    void handlerIgnoresUnrelatedObservationContexts() {
        ObservationHandler<Observation.Context> handler =
                new ObservationHandler<>() {
                    @Override
                    public boolean supportsContext(Observation.Context context) {
                        return context instanceof BusinessTaskContext;
                    }
                };

        assertFalse(handler.supportsContext(new Observation.Context()));
        assertTrue(handler.supportsContext(
                new BusinessTaskContext(
                        BusinessTaskContext.Workflow.ORDER_LOOKUP)));
    }
}
~~~

Đây là unit test cho extension points. Với phiên bản Micrometer thực tế, cần xác minh callback order/filter semantics bằng test integration chạy trên dependency BOM của project. Không chỉ dựa vào test registry tự tạo để kết luận exporter production đã nhận attributes.

## 23. Các lỗi vận hành thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng Predicate thay tracing sampler | Mất cả metrics và traces | Sampling ở tracing bridge |
| Predicate loại business task | Không còn tổng workflow | Allowlist các business observations |
| Filter chạy network I/O | Tăng latency | Filter chỉ map context trong memory |
| Handler ghi DB đồng bộ | Request bị block | Queue bounded hoặc exporter phù hợp |
| Handler supportsContext luôn true | Ép kiểu sai context | Kiểm tra context type |
| Filter thêm duplicate key | Tag không nhất quán | Một owner cho mỗi key |
| Outcome gán sau khi stop | Metrics có outcome unknown/sai | Gán outcome trong supplier trước khi kết thúc |
| Gắn success lúc start | Sai khi timeout/reject | Bổ sung outcome ở Filter khi stop |
| Dùng exception message làm tag | Cardinality cao và lộ dữ liệu | Error category enum |
| Xóa handler mặc định | Mất meter/span | Bổ sung custom handler, giữ auto-config |
| Handler tạo lại timer/span | Double-count | Dùng handler mặc định |
| Dùng Predicate để bỏ case fail | Measurement bias | Chỉ lọc theo instrumentation policy |
| Filter được xem là redaction layer | Có thể lộ dữ liệu trước filter | Không đưa raw data vào context |
| Không test callback order | Outcome tag thiếu | Integration test theo BOM |

## 24. Bài thực hành: policy cho business task observations

Tạo policy cho workflow support_answer:

1. Giữ business task, RAG retrieval, model và tool observations.
2. Loại namespace app.ai.internal.debug.*
3. Khi task stop, Filter thêm outcome vào low-cardinality values.
4. Handler ghi counter app.ai.business.task.completed theo workflow/outcome.
5. Handler không gọi mạng hoặc database đồng bộ.
6. Raw prompt và tool arguments không xuất hiện trong context.
7. Exception được phân loại thành error/timeout.
8. Rejected và abstained là business outcomes riêng.
9. Unit test xác minh Predicate, Filter và Handler.
10. Integration test xác minh meter handler nhận outcome sau filter.

### Trace/meter kỳ vọng

~~~text
Observation: app.ai.business.task
  workflow=support_answer
  outcome=success
  duration=1.8s

Counter: app.ai.business.task.completed
  workflow=support_answer
  outcome=success
  value=1
~~~

Nếu Predicate loại observation, supplier vẫn chạy nhưng completion counter từ handler của observation đó không được tăng. Đây là lý do phải cân nhắc policy loại observation rất kỹ.

## 25. Checklist trước khi đưa extension points vào production

- [ ] Predicate chỉ loại observations có lý do rõ ràng.
- [ ] Business task và Spring AI component observations quan trọng vẫn được giữ.
- [ ] Predicate không được dùng thay tracing sampler.
- [ ] Filter chỉ thực hiện biến đổi context nhanh, xác định.
- [ ] Terminal outcome được gán trước khi Observation stop.
- [ ] Filter không được coi là lớp redaction dữ liệu nhạy cảm.
- [ ] Handler có supportsContext hẹp và an toàn.
- [ ] Handler không thực hiện network/database I/O đồng bộ.
- [ ] Meter/tracing handlers mặc định vẫn được giữ.
- [ ] Custom handler không tạo duplicate timer/span.
- [ ] Key-values có cardinality được kiểm soát.
- [ ] Exception message và raw user data không thành tags.
- [ ] Registration qua registry do Spring Boot quản lý.
- [ ] Không đăng ký predicate/filter/handler trùng lặp.
- [ ] Unit tests kiểm tra predicate accept/reject.
- [ ] Unit tests kiểm tra filter output và handler callbacks.
- [ ] Integration tests xác minh callback order theo BOM.
- [ ] Dashboard phân biệt business outcomes với execution errors.
- [ ] Sampling và retention policy được ghi rõ.
- [ ] Có owner cho policy thay đổi extension points.

## Tài liệu tham khảo

1. [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation.html): Observation lifecycle, registry và extension points.
2. [Micrometer Observation API](https://docs.micrometer.io/micrometer/reference/observation/instrumenting.html): instrument operation và cấu hình Observation.
3. [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): ObservationRegistry, customizers, metrics và tracing.
4. [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/): observations của ChatClient, model, vector store và tools.
5. [Micrometer Context Propagation](https://docs.micrometer.io/context-propagation/reference/): context propagation qua thread và reactive execution.
6. [OpenTelemetry — Trace API](https://opentelemetry.io/docs/specs/otel/trace/api/): span lifecycle và sampling context.
7. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): bảo vệ dữ liệu nhạy cảm trong telemetry/logging.

> **Ghi nhớ:** Predicate quyết định observation có được ghi nhận; Filter chuẩn hóa context; Handler phản ứng với lifecycle. Hãy dùng Predicate có chọn lọc, Filter nhẹ và xác định, Handler không blocking, đồng thời giữ nguyên các handlers mặc định để metrics và traces của Spring AI tiếp tục hoạt động.
