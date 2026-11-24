# ObservationPredicate để quyết định thao tác nào được quan sát

`ObservationPredicate` cho phép quyết định một observation có được tạo và chuyển đến các observation handler hay không. Predicate nhận tên observation cùng `Observation.Context`, sau đó trả về `true` để cho phép hoặc `false` để bỏ qua observation đó. Đây là cách áp dụng một chính sách tập trung khi ứng dụng có nhiều instrumentation từ Spring Boot, Micrometer hoặc code tự viết.

Trong module `OBSERVABILITY_INSTRUMENTATION_MICROMETER`, các observation có thể được nối với metrics như Counter, Gauge, Timer và DistributionSummary, đồng thời cung cấp context cho tracing. `ObservationPredicate` quyết định thao tác nào được đi vào pipeline observation trước khi các handler tương ứng xử lý; vì vậy, chính sách cần phù hợp với mục tiêu giám sát của ứng dụng.

Ví dụ, ứng dụng có thể bỏ qua một số thao tác nội bộ phát sinh quá thường xuyên nhưng ít giá trị vận hành, trong khi vẫn giữ các observation của luồng nghiệp vụ chính. Khi predicate từ chối một observation, Micrometer sử dụng no-op observation; các handler không xử lý một observation hoạt động như bình thường. Vì predicate tác động ở tầng Observation, cần hiểu rằng nó có thể ảnh hưởng đồng thời đến nhiều handler như metrics và tracing.

## 1. ObservationPredicate giải quyết vấn đề nào?

Trong ứng dụng Java dùng Micrometer, nhiều thành phần có thể tạo observation:

- HTTP server và HTTP client instrumentation của Spring.
- Các thao tác database, messaging hoặc client được instrument.
- Observation do ứng dụng tạo thủ công.
- Các thao tác nghiệp vụ được bao quanh bởi Observation API.

Không phải observation nào cũng có giá trị như nhau. Một số thao tác nội bộ có tần suất rất cao, chẳng hạn polling, cache refresh hoặc housekeeping. Nếu không cần metrics/tracing cho các thao tác này, có thể dùng `ObservationPredicate` để từ chối chúng theo tên hoặc thông tin có sẵn trong context.

Predicate tập trung hóa chính sách quyết định observation nào được ghi nhận. Thay vì thêm điều kiện ở mọi service, ta cấu hình một nơi tại `ObservationRegistry`.

## 2. Hợp đồng của ObservationPredicate

`ObservationPredicate` là functional interface của Micrometer Observation. Phương thức `test` nhận hai đối số:

```java
boolean test(String name, Observation.Context context);
```

| Đối số | Ý nghĩa | Cách sử dụng |
| --- | --- | --- |
| `name` | Tên observation đang được tạo | So khớp chính xác hoặc theo prefix ổn định. |
| `context` | Context gắn với observation | Dùng thêm thông tin loại context hoặc thuộc tính đã có tại thời điểm kiểm tra. |

Kết quả:

- `true`: cho phép observation tiếp tục vòng đời bình thường và được các handler xử lý.
- `false`: từ chối observation; Micrometer trả về no-op observation để các lời gọi API tiếp theo không tạo hoạt động quan sát thực sự.

Ví dụ predicate đơn giản:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationPredicate;

public final class InternalOperationPredicate implements ObservationPredicate {
    @Override
    public boolean test(String name, Observation.Context context) {
        return !name.startsWith("internal.housekeeping.");
    }
}
```

Predicate trên từ chối các observation có tên bắt đầu bằng `internal.housekeeping.` và cho phép các tên còn lại. Tên observation nên ổn định và có quy ước rõ ràng để chính sách không vô tình loại bỏ các luồng cần giám sát.

## 3. Đăng ký predicate trực tiếp với ObservationRegistry

Trong ứng dụng Java độc lập, có thể cấu hình predicate trên registry trước khi tạo observation:

```java
import io.micrometer.observation.ObservationRegistry;

ObservationRegistry registry = ObservationRegistry.create();

registry.observationConfig().observationPredicate(
        (name, context) -> !name.startsWith("internal.poller."));
```

Sau khi cấu hình, mọi observation được tạo qua registry này sẽ đi qua chính sách predicate đã đăng ký.

Ví dụ kiểm tra nhanh:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

ObservationRegistry registry = ObservationRegistry.create();
registry.observationConfig().observationPredicate(
        (name, context) -> !name.equals("internal.poller.refresh"));

Observation allowed = Observation.createNotStarted("shop.order.process", registry);
Observation ignored = Observation.createNotStarted("internal.poller.refresh", registry);

allowed.start().stop();
ignored.start().stop();
```

Lời gọi trên vẫn có thể được thực hiện với no-op observation. Code nghiệp vụ không cần rải điều kiện `if` quanh từng lời gọi `start()` hoặc `stop()`.

Hãy cấu hình predicate sớm trong giai đoạn khởi tạo registry. Một observation đã được tạo và handler đã xử lý không thể bị predicate đăng ký sau đó thu hồi ngược lại.

## 4. Cấu hình ObservationPredicate trong Spring Boot

Trong Spring Boot, có thể đăng ký bean `ObservationRegistryCustomizer` để tùy chỉnh `ObservationRegistry` do Boot quản lý:

```java
import io.micrometer.observation.ObservationRegistry;
import java.util.Set;
import org.springframework.boot.actuate.autoconfigure.observation.ObservationRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ObservationPolicyConfiguration {
    private static final Set<String> EXCLUDED_OBSERVATIONS = Set.of(
            "internal.cache.refresh",
            "internal.scheduler.heartbeat"
    );

    @Bean
    ObservationRegistryCustomizer<ObservationRegistry> observationPolicy() {
        return registry -> registry.observationConfig()
                .observationPredicate((name, context) ->
                        !EXCLUDED_OBSERVATIONS.contains(name));
    }
}
```

Spring Boot áp dụng customizer vào registry được cấu hình trong application context. Các observation có tên nằm trong tập `EXCLUDED_OBSERVATIONS` sẽ bị từ chối; các tên khác tiếp tục được xử lý bình thường.

Ví dụ dùng `Set.of`, có từ Java 9. Nếu dự án dùng Java 8, thay bằng một tập bất biến tương đương được tạo từ `Collections.unmodifiableSet(...)`.

API package và cơ chế auto-configuration cần khớp phiên bản Spring Boot đang dùng. Hãy dùng dependency management của dự án để đồng bộ phiên bản Spring Boot và Micrometer.

## 5. Dùng cả tên và context để đưa ra quyết định

Predicate nhận cả tên và context để hỗ trợ chính sách linh hoạt hơn. Tên thường là tín hiệu ổn định và dễ kiểm soát nhất. Context có thể cung cấp thêm thông tin về loại observation hoặc dữ liệu mà instrumentation đã chuẩn bị tại thời điểm predicate được gọi.

Ví dụ mở rộng chính sách theo tên:

```java
registry.observationConfig().observationPredicate((name, context) -> {
    if (name.startsWith("internal.housekeeping.")) {
        return false;
    }

    if (name.startsWith("shop.order.")) {
        return true;
    }

    return true;
});
```

Đoạn code trên minh họa cách chia nhánh theo tên; có thể mở rộng để kiểm tra kiểu context khi ứng dụng có context class riêng. Không nên giả định mọi trường trong context đều đã được điền ở thời điểm predicate chạy. Hãy kiểm tra lifecycle của instrumentation cụ thể trước khi dựa vào một thuộc tính context.

### 5.1. Context phải cung cấp dữ liệu sẵn có, không phải nơi để chạy nghiệp vụ

Predicate có thể được gọi thường xuyên và nằm trên đường tạo observation. Vì vậy, không nên:

- Truy vấn database để quyết định có ghi observation hay không.
- Gọi HTTP service hoặc cache từ predicate.
- Đọc request body hoặc parse payload lớn.
- Thực hiện phép tính tốn CPU.
- Dựa vào dữ liệu có thể thay đổi không kiểm soát để tạo policy khó dự đoán.

Nếu cần quyết định dựa trên thuộc tính nghiệp vụ, hãy chuẩn bị thuộc tính đó ở nơi tạo observation và chỉ đọc giá trị đã có. Ưu tiên tên observation và các context type/field ổn định.

## 6. Allowlist và denylist cho observation

Có hai cách phổ biến để định nghĩa chính sách:

| Cách | Ý tưởng | Phù hợp khi |
| --- | --- | --- |
| Denylist | Mặc định cho phép, loại bỏ một số tên cụ thể | Ứng dụng cần giữ phần lớn instrumentation và chỉ bỏ một vài thao tác nhiễu. |
| Allowlist | Mặc định từ chối, chỉ cho phép các tên đã chọn | Môi trường hoặc pipeline chỉ cần một tập observation rất nhỏ. |

Ví dụ denylist:

```java
Set<String> excluded = Set.of(
        "internal.cache.refresh",
        "internal.scheduler.heartbeat"
);

registry.observationConfig().observationPredicate(
        (name, context) -> !excluded.contains(name));
```

Ví dụ allowlist:

```java
Set<String> included = Set.of(
        "shop.order.process",
        "shop.payment.authorize",
        "http.server.requests"
);

registry.observationConfig().observationPredicate(
        (name, context) -> included.contains(name));
```

Allowlist cần được duy trì cẩn thận. Khi thêm instrumentation mới, observation có thể bị loại bỏ cho đến khi được đưa vào danh sách. Điều này dễ làm mất dữ liệu quan sát mà không gây lỗi nghiệp vụ.

## 7. Phân biệt ObservationPredicate, ObservationFilter và MeterFilter

Ba extension point này nằm ở các tầng khác nhau:

| Cơ chế | Câu hỏi nó trả lời | Tác động |
| --- | --- | --- |
| `ObservationPredicate` | Có nên tạo observation này không? | Cho phép hoặc bỏ qua toàn bộ observation trước khi các handler xử lý. |
| `ObservationFilter` | Context của observation cần được chuẩn hóa hoặc bổ sung thế nào? | Biến đổi context của observation được chấp nhận. |
| `MeterFilter` | Meter nào được đăng ký hoặc được điều chỉnh ra sao? | Lọc, đổi ID hoặc cấu hình meter trong một `MeterRegistry`. |

Ví dụ:

- Muốn bỏ hoàn toàn observation `internal.poller.refresh` khỏi các handler: dùng `ObservationPredicate`.
- Muốn chuẩn hóa hoặc bổ sung thông tin vào context của observation: dùng `ObservationFilter`.
- Muốn chỉ loại bỏ meter có tên không mong muốn khỏi Prometheus registry nhưng vẫn giữ observation cho tracing: cân nhắc `MeterFilter`.

`ObservationPredicate` tác động ở tầng Observation, nên có thể ngăn cả metrics handler và tracing handler nhận observation. `MeterFilter` chỉ tác động đến meter registry tương ứng; nó không tự ngăn tracing handler tạo span.

Không dùng predicate để giải quyết mọi vấn đề cardinality. Nếu observation vẫn cần cho trace nhưng metric không nên tạo một số series, hãy kiểm soát low-cardinality key-value hoặc dùng `MeterFilter` phù hợp.

## 8. Ảnh hưởng đến metrics và tracing

Một observation có thể được nhiều handler xử lý. Ví dụ, cùng một HTTP observation có thể tạo timer trong Micrometer và span trong tracing bridge. Nếu predicate trả về `false`, observation bị bỏ qua ở tầng chung; do đó cả metrics và tracing gắn với observation đó có thể không được tạo.

Điều này quan trọng khi lựa chọn chính sách:

- Nếu một thao tác không cần bất kỳ telemetry nào, predicate là lựa chọn phù hợp.
- Nếu vẫn cần trace nhưng không cần meter, giữ observation và lọc ở tầng metrics.
- Nếu chỉ muốn sampling trace, dùng cơ chế sampling của tracing exporter/SDK thay vì loại bỏ observation toàn cục.
- Nếu chỉ muốn bỏ một meter do cardinality hoặc naming, dùng meter filter và quy ước tag phù hợp.

Ngoài ra, các meter được tạo trực tiếp bằng `Counter`, `Timer` hoặc `@Timed` aspect có thể không đi qua Observation API. `ObservationPredicate` không phải bộ lọc toàn cục cho mọi meter trong ứng dụng; nó chỉ quyết định các observation được tạo qua registry tương ứng.

## 9. Predicate không phải công cụ sửa tag hoặc giảm cardinality sau khi tạo meter

Predicate quyết định observation có được chấp nhận hay không. Nó không đổi tên observation, không chuẩn hóa tag và không xóa các meter đã đăng ký trước đó.

Nếu vấn đề là tag có quá nhiều giá trị, hãy xem lại:

- Low-cardinality key-value được dùng để tạo metrics.
- Observation convention tạo tên và tag.
- `ObservationFilter` nếu cần chuẩn hóa context.
- `MeterFilter` nếu cần chặn hoặc điều chỉnh meter ở registry.

Ví dụ, không nên loại toàn bộ observation `http.server.requests` chỉ vì một tag route có ID động. Hãy sửa URI template hoặc convention để route được chuẩn hóa thành `/orders/{id}`. Như vậy vẫn giữ được số liệu request hữu ích mà không tạo một series cho từng order ID.

## 10. Tên observation cần ổn định

Predicate thường dựa vào tên observation. Nếu tên được tạo động từ user ID, order ID hoặc URL đầy đủ, chính sách sẽ khó quản lý và có thể tạo thêm chi phí không cần thiết.

Nên dùng tên biểu thị loại thao tác:

- `shop.order.process`
- `shop.payment.authorize`
- `shop.inventory.reserve`
- `internal.cache.refresh`

Không dùng:

- `shop.order.123456.process`
- `shop.user.alice@example.com.lookup`
- `http://host/orders/123456`

Tên ổn định giúp predicate dễ đọc, dễ kiểm thử và không phụ thuộc dữ liệu từng request.

## 11. Kiểm thử predicate độc lập

Có thể kiểm thử chính sách bằng một `ObservationRegistry` và handler đếm số lần nhận sự kiện:

```java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class ObservationPredicateTest {
    @Test
    void rejectsInternalObservationAndKeepsBusinessObservation() {
        AtomicInteger started = new AtomicInteger();
        AtomicInteger stopped = new AtomicInteger();

        ObservationRegistry registry = ObservationRegistry.create();
        registry.observationConfig()
                .observationPredicate((name, context) ->
                        !name.startsWith("internal."))
                .observationHandler(new ObservationHandler<Observation.Context>() {
                    @Override
                    public boolean supportsContext(Observation.Context context) {
                        return true;
                    }

                    @Override
                    public void onStart(Observation.Context context) {
                        started.incrementAndGet();
                    }

                    @Override
                    public void onStop(Observation.Context context) {
                        stopped.incrementAndGet();
                    }
                });

        Observation.createNotStarted("shop.order.process", registry)
                .start().stop();
        Observation.createNotStarted("internal.cache.refresh", registry)
                .start().stop();

        assertThat(started).hasValue(1);
        assertThat(stopped).hasValue(1);
    }
}
```

Test xác minh observation nghiệp vụ được handler xử lý, còn observation có prefix `internal.` bị bỏ qua. Có thể bổ sung assertion cho `onError` nếu muốn kiểm tra lỗi trên observation được chấp nhận.

### 11.1. Kiểm thử predicate với context

Nếu predicate đọc context type hoặc thuộc tính tùy chỉnh, hãy tạo context giống với context do instrumentation thực tế cung cấp. Test cần xác minh:

- Context có mặt trước thời điểm predicate được gọi.
- Giá trị null hoặc thiếu trường được xử lý an toàn.
- Predicate không phụ thuộc vào thứ tự handler hoặc trạng thái mutable không ổn định.
- Các observation không thuộc phạm vi policy vẫn được chấp nhận.

Không chỉ test trường hợp bị từ chối. Một predicate sai có thể loại bỏ toàn bộ observation và làm mất telemetry trên diện rộng.

## 12. Cấu hình nhiều chính sách mà vẫn dễ kiểm soát

Khi có nhiều quy tắc, hãy gom chúng thành một predicate có tên rõ ràng hoặc các hàm nhỏ:

```java
private boolean isAllowedObservation(String name) {
    return !name.startsWith("internal.housekeeping.")
            && !name.equals("internal.scheduler.heartbeat");
}

@Bean
ObservationRegistryCustomizer<ObservationRegistry> observationPolicy() {
    return registry -> registry.observationConfig()
            .observationPredicate((name, context) ->
                    isAllowedObservation(name));
}
```

Nếu đăng ký nhiều predicate riêng, hãy kiểm tra semantics kết hợp của phiên bản Micrometer đang dùng. Để tránh bất ngờ, có thể gộp chính sách vào một hàm duy nhất và viết test cho các trường hợp biên.

Đừng đưa danh sách exclude vào cấu hình mutable bị thay đổi đồng thời trong lúc request đang chạy trừ khi thật sự cần policy động. Chính sách bất biến khởi tạo lúc startup dễ dự đoán hơn và tránh race condition.

## 13. Những lỗi thường gặp

- **Nhầm predicate với filter meter:** predicate loại observation ở tầng chung; meter filter chỉ tác động đến registry metrics.
- **Từ chối observation quá rộng:** prefix hoặc allowlist sai có thể làm mất cả metrics lẫn tracing.
- **Dùng tên động:** policy không ổn định và khó kiểm soát.
- **Đọc context field chưa được khởi tạo:** predicate chạy trước khi instrumentation hoàn tất việc thêm thuộc tính.
- **Thực hiện I/O trong predicate:** tăng latency và tạo phụ thuộc ngoài không cần thiết.
- **Cho rằng predicate xóa meter đã có:** predicate chỉ tác động đến observation được tạo sau khi policy có hiệu lực.
- **Dùng predicate để chữa tag cardinality:** cần chuẩn hóa convention/tag hoặc dùng MeterFilter ở tầng registry.
- **Cho rằng mọi meter đều bị predicate kiểm soát:** meter được đăng ký trực tiếp không đi qua Observation API có thể vẫn tồn tại.
- **Chỉ test trường hợp bị từ chối:** bỏ sót lỗi predicate chặn nhầm observation hợp lệ.
- **Muốn chỉ bỏ trace nhưng dùng predicate:** predicate có thể ngăn cả metrics handler; dùng sampling ở tracing layer nếu đó là mục tiêu.

## 14. Checklist triển khai ObservationPredicate

- [ ] Xác định rõ nhóm observation cần cho phép hoặc từ chối.
- [ ] Dùng tên observation ổn định và có quy ước.
- [ ] Cấu hình predicate trên đúng `ObservationRegistry`.
- [ ] Với Spring Boot, đăng ký `ObservationRegistryCustomizer` phù hợp phiên bản.
- [ ] Chỉ đọc context field đã có tại thời điểm predicate chạy.
- [ ] Giữ predicate thuần, nhanh, không I/O và không có tác dụng phụ.
- [ ] Xác định tác động đến cả metrics, tracing và các handler khác.
- [ ] Dùng `ObservationFilter` để biến đổi context, `MeterFilter` để lọc meter.
- [ ] Không dùng predicate thay cho chuẩn hóa tag/cardinality.
- [ ] Kiểm thử cả observation được chấp nhận và bị từ chối.
- [ ] Xác minh instrumentation trực tiếp không dùng Observation có còn hoạt động như mong muốn.
- [ ] Đăng ký policy trước khi ứng dụng bắt đầu tạo observation.

`ObservationPredicate` là cổng quyết định ở tầng Observation: cho phép một thao tác đi vào pipeline telemetry hoặc chuyển nó thành no-op. Dùng predicate cho chính sách include/exclude có chủ đích, tên ổn định và kiểm tra nhanh; dùng các filter ở tầng phù hợp khi mục tiêu chỉ là thay đổi context hoặc kiểm soát meter. Luôn kiểm thử cả nhánh được phép lẫn nhánh bị loại bỏ vì một predicate quá rộng có thể làm mất đồng thời metrics và tracing của những thao tác quan trọng.
