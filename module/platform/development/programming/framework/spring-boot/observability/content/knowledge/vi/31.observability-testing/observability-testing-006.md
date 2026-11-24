# Kiểm thử ObservationPredicate trong Micrometer

Trong chương **Testing observability** của module **SPRING_BOOT_OBSERVABILITY**, ObservationPredicate là bộ lọc quyết định một observation có được phép tiếp tục hay không dựa trên tên observation và context của nó. Kiểm thử predicate giúp bảo đảm các operation cần theo dõi vẫn tạo metrics/traces, còn những operation bị loại được xử lý đúng theo chính sách instrumentation.

Predicate thường được dùng để bỏ qua observation nội bộ, health probe, endpoint không cần theo dõi hoặc operation có volume quá lớn. Một điều kiện lọc sai có thể âm thầm làm mất metrics và spans, khiến dashboard thiếu dữ liệu hoặc trace bị đứt. Vì vậy, test cần kiểm tra cả trường hợp được giữ và bị loại, đồng thời xác nhận tác động lên observation handlers.

Trong **SPRING_BOOT_OBSERVABILITY**, Observation là điểm kết nối giữa instrumentation và các handler như metrics hoặc tracing. Bài này tập trung vào semantics của ObservationPredicate, cách đăng ký trong ObservationRegistry/Spring Boot, unit test và context test, negative cases, thứ tự lọc và cách tránh nhầm predicate với sampling.

## 1. ObservationPredicate làm gì?

Micrometer Observation có tên và context. Instrumentation tạo observation, sau đó registry áp dụng cấu hình để quyết định observation có được tiếp tục và được các observation handler xử lý hay không. ObservationPredicate cung cấp điều kiện lọc dựa trên tên và context.

Về ý tưởng, predicate nhận hai thông tin:

- Tên observation, thường là tên ổn định do instrumentation/convention đặt.
- Observation.Context, chứa dữ liệu gắn với operation và có thể có subtype cụ thể.

Nếu predicate trả true, observation được chấp nhận để tiếp tục lifecycle. Nếu trả false, observation bị no-op/không được ghi nhận bởi các handlers như observation thông thường. Chi tiết lifecycle và cách kết hợp nhiều predicate cần xác minh theo Micrometer version đang dùng.

```text
Instrumentation creates observation
              |
              v
       ObservationPredicate
          /         \
       true         false
        |             |
        v             v
 Continue lifecycle  No-op / filtered
        |
        v
 Observation handlers
   |              |
   v              v
 Metrics        Tracing
```

Predicate là một quyết định ở tầng Observation. Nó không phải query filter trong Prometheus, không phải retention policy của trace backend và cũng không phải sampling policy của tracing SDK.

## 2. ObservationPredicate và ObservationFilter khác nhau

| Extension point | Vai trò | Câu hỏi |
| --- | --- | --- |
| ObservationPredicate | Chấp nhận hoặc loại observation trước khi lifecycle được xử lý như observation bình thường | Operation này có nên được quan sát không? |
| ObservationFilter | Chỉnh sửa context sau khi observation được tạo, thường để chuẩn hóa/thêm metadata | Observation được giữ cần thêm hoặc chuẩn hóa dữ liệu gì? |
| ObservationConvention | Định nghĩa tên và key-values theo quy ước instrumentation | Observation này nên được mô tả bằng tên/tag nào? |
| Tracing sampler | Quyết định span/trace có được ghi hoặc export theo tracing SDK hay không | Trace này có được sampling không? |

Không dùng predicate để thay thế convention hoặc filter nếu mục tiêu chỉ là đổi tên hay chuẩn hóa metadata. Ngược lại, không dùng ObservationFilter để cố loại bỏ một operation mà instrumentation không nên ghi nhận.

## 3. API và đăng ký predicate

Trong Micrometer Observation, predicate được đăng ký vào ObservationRegistry thông qua observation configuration. API cụ thể có thể khác nhẹ giữa các phiên bản; ví dụ thường gặp là observationConfig().observationPredicate(...).

Ví dụ predicate loại các observation có prefix internal.:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationPredicate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class ObservationConfiguration {

    @Bean
    ObservationPredicate skipInternalObservations() {
        return (name, context) ->
                name == null || !name.startsWith("internal.");
    }
}
```

Ví dụ trên minh họa ý tưởng predicate; xác minh cách Spring Boot/Micrometer version đang dùng thu thập các bean ObservationPredicate và đăng ký chúng vào registry. Trong ứng dụng Spring Boot auto-configured, bean predicate có thể được Boot phát hiện và áp dụng. Nếu tự tạo ObservationRegistry, cần đăng ký predicate trên registry đó; việc khai báo bean trong context không tự động cấu hình mọi registry được tạo thủ công.

Một cách đăng ký trực tiếp ở mức registry (API minh họa):

```java
ObservationRegistry registry = ObservationRegistry.create();

registry.observationConfig()
        .observationPredicate((name, context) ->
                name == null || !name.startsWith("internal."));
```

Không cấu hình cùng một predicate nhiều lần trên nhiều registry rồi chỉ test một registry khác với registry runtime. Test phải lấy đúng bean/registry mà instrumentation thực tế sử dụng.

## 4. Viết predicate ổn định

Predicate nên dựa trên tên observation và context type/metadata ổn định. Tránh dựa trên dữ liệu request tùy ý hoặc giá trị thay đổi theo từng lần gọi.

Ví dụ các điều kiện có thể phù hợp:

- Bỏ qua observation có tên thuộc namespace internal.
- Bỏ qua một loại health check có context/type xác định.
- Giữ observation nghiệp vụ và dependency quan trọng.
- Chỉ áp dụng policy cho một nhóm instrumentation đã biết.

Không nên lọc bằng URL đầy đủ có query parameters động; dùng user ID, tenant ID hoặc request ID làm điều kiện tạo ra số lượng rule không giới hạn; giả định mọi observation có cùng context subtype; dựa vào exception message hoặc payload; dùng tên span/observation có dynamic suffix làm policy lâu dài.

Ví dụ predicate kiểm tra context type:

```java
ObservationPredicate predicate = (name, context) -> {
    if (context == null) {
        return true;
    }

    if (context instanceof HealthCheckObservationContext) {
        return false;
    }

    return name == null || !name.startsWith("internal.");
};
```

HealthCheckObservationContext ở đây là context type minh họa do ứng dụng định nghĩa, không phải class Micrometer có sẵn. Trong code thật, thay bằng context type cụ thể mà instrumentation của ứng dụng cung cấp. Kiểm tra null và subtype trước khi ép kiểu để predicate không gây lỗi trong đường instrumentation.

## 5. Test predicate như một hàm độc lập

Nếu logic predicate có nhiều nhánh, tách factory hoặc class riêng để có thể unit test trực tiếp. Unit test nên bao phủ:

1. Tên observation thuộc nhóm bị loại.
2. Tên observation thuộc nhóm được giữ.
3. Tên null hoặc rỗng theo policy đã định nghĩa.
4. Context null nếu API/call path cho phép.
5. Context subtype được lọc riêng.
6. Context subtype không liên quan vẫn được giữ.
7. Tên gần giống prefix nhưng không thuộc namespace bị loại.

Ví dụ:

```java
class InternalObservationPredicate implements ObservationPredicate {
    @Override
    public boolean test(String name, Observation.Context context) {
        return name == null || !name.startsWith("internal.");
    }
}
```

```java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;

class InternalObservationPredicateTest {

    private final InternalObservationPredicate predicate =
            new InternalObservationPredicate();

    @Test
    void rejectsInternalObservation() {
        assertThat(predicate.test("internal.cache.lookup",
                new Observation.Context())).isFalse();
    }

    @Test
    void acceptsBusinessObservation() {
        assertThat(predicate.test("order.submit",
                new Observation.Context())).isTrue();
    }

    @Test
    void acceptsNameWithoutInternalPrefix() {
        assertThat(predicate.test("internalized.operation",
                new Observation.Context())).isTrue();
    }

    @Test
    void acceptsNullNameAccordingToPolicy() {
        assertThat(predicate.test(null,
                new Observation.Context())).isTrue();
    }
}
```

Đây là ví dụ JUnit/AssertJ; constructor và API của context cần khớp Micrometer version trong dependency management. Nếu interface/version yêu cầu cách khởi tạo context khác, dùng context test fixture tương ứng. Điều quan trọng là test boundary của prefix và cả nhánh null theo policy đã chọn.

## 6. Test bằng ObservationRegistry và handler

Unit test predicate chưa chứng minh registry runtime thực sự áp dụng predicate. Thêm test ở mức registry để xác nhận lifecycle và handler behavior.

Có thể đăng ký một handler test đếm số lần start/stop:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import java.util.concurrent.atomic.AtomicInteger;

class CountingObservationHandler
        implements ObservationHandler<Observation.Context> {

    final AtomicInteger starts = new AtomicInteger();
    final AtomicInteger stops = new AtomicInteger();

    @Override
    public void onStart(Observation.Context context) {
        starts.incrementAndGet();
    }

    @Override
    public void onStop(Observation.Context context) {
        stops.incrementAndGet();
    }

    @Override
    public boolean supportsContext(Observation.Context context) {
        return true;
    }
}
```

Test có thể tạo registry, đăng ký predicate và handler, sau đó chạy hai observations:

```java
ObservationRegistry registry = ObservationRegistry.create();
CountingObservationHandler handler = new CountingObservationHandler();

registry.observationConfig()
        .observationPredicate((name, context) ->
                name == null || !name.startsWith("internal."));
registry.observationConfig().observationHandler(handler);

Observation.createNotStarted("order.submit", registry)
        .observe(() -> {});

Observation.createNotStarted("internal.cache.lookup", registry)
        .observe(() -> {});

assertThat(handler.starts).hasValue(1);
assertThat(handler.stops).hasValue(1);
```

Đây là integration-test sketch. API của handler, predicate chaining và no-op behavior cần khớp version đang dùng. Test quan trọng là observation được chấp nhận đi qua handler, observation bị loại không tạo callback như một observation bình thường. Nếu dùng nhiều handlers, kiểm tra từng handler cần thiết thay vì chỉ đếm tổng một handler.

## 7. Kiểm tra tác động lên metrics

Trong Spring Boot, metrics handler thường chuyển observations thành timers/counters hoặc meters theo convention. Nếu predicate loại một observation, meter liên quan có thể không được cập nhật bởi observation đó.

Một test metrics nên xác minh observation được giữ làm meter xuất hiện hoặc count tăng; observation bị loại không làm meter count tăng; tên meter và tags ổn định theo convention; không tạo series mới cho request ID, user ID hoặc dynamic URL; một observation bị loại không vô tình làm mất metric nghiệp vụ quan trọng.

Ví dụ dùng SimpleMeterRegistry:

```java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

SimpleMeterRegistry meters = new SimpleMeterRegistry();
ObservationRegistry observations = ObservationRegistry.create();

// Gắn metrics handler theo cách được hỗ trợ bởi Micrometer version.
// Đăng ký predicate trên chính registry này trước khi chạy observation.
```

Đoạn code trên chỉ phác thảo setup vì cách gắn DefaultMeterObservationHandler và convention phụ thuộc version. Trong project, ưu tiên cấu hình handler như production hoặc dùng Spring Boot test context để xác minh auto-configuration thực tế.

Không assert tên meter chỉ bằng phỏng đoán. Đọc registry sau khi chạy test và xác nhận meter names/tags theo Micrometer version và convention đang được dùng.

## 8. Predicate không thay thế tracing sampling

ObservationPredicate và tracing sampler có thể cùng ảnh hưởng dữ liệu quan sát, nhưng ở hai tầng khác nhau:

| Tình huống | Predicate | Tracing sampler |
| --- | --- | --- |
| Loại observation nội bộ | Có thể loại observation trước handlers | Không phải mục tiêu chính |
| Giữ metrics nhưng bỏ trace | Không phù hợp nếu loại toàn observation | Có thể sampler trace/span theo tracing setup |
| Giữ trace nhưng không ghi metrics | Cần thiết kế handler/registry riêng hoặc policy phù hợp | Sampler chỉ điều khiển tracing |
| Giảm volume traces | Có thể loại cả observation và các handlers | Sampler chọn traces theo policy |
| Bỏ meter theo convention | Có thể loại observation | Sampler không quyết định metrics |

Nếu yêu cầu là vẫn giữ metrics nhưng giảm số trace, cấu hình tracing sampler hoặc tracing-specific policy thay vì loại toàn bộ observation. Nếu predicate trả false trước khi các handlers nhận observation, cả metrics và tracing có thể bị ảnh hưởng.

Test cần xác minh chính xác mục tiêu: filtered observation, sampled-out span và export failure là ba trạng thái khác nhau. Một trace không xuất hiện ở backend không tự chứng minh predicate đã loại observation.

## 9. Kết hợp nhiều predicate

Một ứng dụng có thể nhận nhiều predicate từ auto-configuration và custom beans. Thứ tự kết hợp, short-circuit behavior và cách đăng ký phụ thuộc API/version. Không giả định thứ tự chỉ dựa trên thứ tự khai báo bean.

Nếu có nhiều policy, nên gom logic liên quan vào một predicate có tên rõ ràng hoặc kiểm tra ordering theo cơ chế framework hỗ trợ. Test các trường hợp một predicate chấp nhận, predicate khác loại; nhiều predicate cùng chấp nhận; prefix overlap; context type cụ thể và context tổng quát; policy theo môi trường.

Tránh tạo predicate có điều kiện đối nghịch khó hiểu, ví dụ một predicate loại http.server.requests trong khi predicate khác cố giữ toàn bộ HTTP observations. Ghi rõ policy và test thứ tự thực thi thực tế.

## 10. Test Spring Boot auto-configuration

Một SpringBootTest hoặc context runner test có thể xác minh bean predicate được Boot áp dụng vào registry được auto-configure. Điều này quan trọng vì unit test predicate không kiểm tra wiring.

Các điểm cần kiểm tra:

1. Predicate bean xuất hiện trong application context.
2. ObservationRegistry được inject vào instrumentation là registry dự kiến.
3. Observation được tạo từ component Spring thực tế đi qua registry đó.
4. Handler test nhận observation được giữ.
5. Handler không nhận observation bị loại.
6. Custom registry do code tự tạo không bị nhầm với registry auto-configured.
7. Profile/configuration test phản ánh policy của môi trường.

Nếu application context có nhiều registry, log hoặc inspect bean identity trong test để xác định registry mà component đang dùng. Không chỉ assert bean predicate tồn tại rồi kết luận mọi instrumentation đã được lọc.

## 11. Negative cases và lỗi thường gặp

| Lỗi | Hậu quả | Cách kiểm tra |
| --- | --- | --- |
| Predicate lọc prefix quá rộng | Mất metrics/traces nghiệp vụ | Test boundary và tên gần giống |
| Dùng dynamic URL làm rule | Rule khó ổn định, có thể không match route template | Dùng tên/context ổn định |
| Ép context subtype không kiểm tra | ClassCastException trong instrumentation | Kiểm tra instanceof và null |
| Đăng ký predicate vào registry sai | Runtime không bị lọc | Test bean identity và actual instrumentation |
| Nhầm predicate với sampler | Mất cả metrics khi chỉ muốn giảm traces | Test metrics và tracing riêng |
| Nhiều predicate không rõ thứ tự | Kết quả khác dự kiến | Kiểm tra chaining/order theo version |
| Test chỉ kiểm tra method predicate | Không phát hiện lỗi Spring wiring | Thêm registry/context test |
| Không test no-op path | Code downstream giả định context luôn có | Test instrumentation khi predicate trả false |

Một số instrumentation code có thể lấy current observation/span hoặc dựa vào context. Khi predicate loại observation, cần bảo đảm application code không giả định luôn có observation hiện hành. Không dùng observation như nơi lưu business state bắt buộc.

## 12. Ví dụ policy thực tế

Giả sử service muốn bỏ qua health probes và internal cache operations, nhưng vẫn giữ HTTP server requests và business operations:

```java
ObservationPredicate productionPredicate = (name, context) -> {
    if (name == null) {
        return true;
    }

    if (name.startsWith("internal.cache.")) {
        return false;
    }

    if (name.startsWith("http.server.requests") &&
            context instanceof HealthProbeContext) {
        return false;
    }

    return true;
};
```

HealthProbeContext là kiểu context minh họa. HTTP server observation context thực tế tùy Spring/Micrometer version; health probe có thể được nhận diện bằng URI/route hoặc metadata do convention thêm vào. Không tạo context giả rồi mong auto-instrumentation tự sử dụng nó.

Nếu health probes cần loại dựa trên route, hãy dùng route template/metadata ổn định, không so sánh raw URI có port, query string hoặc path variable. Test cả health route đúng và business route gần giống để tránh false positive.

Trong nhiều hệ thống, giữ health probe metrics riêng vẫn có ích để theo dõi probe latency/failure. Có thể dùng tên/tag riêng hoặc dashboard filter thay vì loại toàn bộ health observation. Quyết định phải theo mục tiêu vận hành.

## 13. Bài tập tình huống

Một ứng dụng Spring Boot có custom predicate:

```java
return !name.startsWith("http.");
```

Sau khi deploy, dashboard không còn HTTP server request metrics. Nhóm phát triển chỉ muốn bỏ qua một endpoint health probe vì probe được gọi rất thường xuyên.

**Câu hỏi:**

1. Vì sao predicate hiện tại làm mất toàn bộ HTTP observations?
2. Nên thay rule theo prefix nào hoặc context nào?
3. Làm thế nào test health observation bị loại nhưng business route vẫn được giữ?
4. Nếu chỉ muốn giảm tracing cho health probes nhưng vẫn giữ metrics thì nên thay đổi tầng nào?
5. Cần kiểm tra gì để chắc predicate bean đã được áp dụng vào registry runtime?

**Gợi ý phân tích:**

- startsWith("http.") loại mọi observation có namespace http, bao gồm server/client requests tùy convention.
- Rule cần nhận diện health route bằng route template hoặc context metadata ổn định, có kiểm tra null và tránh raw URL động.
- Test ít nhất một health observation và một business HTTP observation; dùng handler/registry để kiểm tra callback, sau đó test metrics output.
- Nếu giữ metrics nhưng giảm traces, cấu hình tracing sampler hoặc tracing-specific policy; không loại toàn observation.
- Dùng Spring Boot context test, lấy đúng ObservationRegistry và xác minh handler nhận/không nhận observations như policy.

### Checklist hoàn thành

| Nội dung | Có thể giải thích/kiểm tra |
| --- | --- |
| Predicate semantics | Hiểu true/false và vị trí lọc |
| Context/name | Dùng tên và context ổn định |
| Registration | Đăng ký vào đúng ObservationRegistry |
| Unit tests | Test accepted, rejected, null và prefix boundary |
| Handler tests | Xác minh lifecycle callbacks |
| Metrics tests | Kiểm tra meter/count/tags |
| Tracing distinction | Phân biệt predicate với sampler và exporter |
| Multiple predicates | Kiểm tra ordering/chaining theo version |
| Spring Boot wiring | Xác minh auto-configuration và registry runtime |
| No-op path | Không giả định luôn có current observation |

**Ghi nhớ:** ObservationPredicate quyết định một observation có được tiếp tục qua registry hay bị loại. Predicate dựa trên tên và context ổn định; hãy kiểm tra null/subtype và tránh rule quá rộng. Unit test chỉ xác minh logic, còn registry/handler và Spring Boot context tests xác nhận wiring cùng tác động thực tế lên metrics/tracing. Phân biệt filtered observation với tracing sampling và export failure: nếu muốn giữ metrics nhưng giảm traces, điều chỉnh tracing policy thay vì loại toàn observation.
