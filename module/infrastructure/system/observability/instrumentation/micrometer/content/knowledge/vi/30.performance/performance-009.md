# Đo chi phí bằng tải thực tế và so sánh khi bật hoặc tắt phép đo

Instrumentation của Micrometer thường có chi phí nhỏ trên mỗi lần ghi nhận, nhưng chi phí tổng thể phụ thuộc vào tần suất operation, số meter, số tag, histogram, handler, exporter và tải đồng thời. Một Timer đơn giản có thể rất rẻ ở tải thấp nhưng trở nên đáng kể khi được gọi hàng trăm nghìn lần mỗi giây hoặc khi mỗi lần ghi tạo thêm nhiều series.

Muốn biết chi phí thực tế, hãy chạy cùng một workload đại diện cho production với instrumentation bật và tắt, giữ nguyên môi trường và điều kiện tải. So sánh latency, throughput, CPU, allocation, GC và error rate. Đo ở cấp ứng dụng giúp đánh giá tác động tổng thể; benchmark vi mô như JMH chỉ nên bổ trợ để tìm chi phí của một thao tác riêng lẻ.

## 1. Những thành phần tạo nên chi phí instrumentation

Chi phí không chỉ nằm ở lệnh `counter.increment()`. Một pipeline quan sát có thể bao gồm nhiều bước:

~~~text
Request / business operation
          |
          v
Create Observation / start Timer
          |
          v
Build or read context and key-values
          |
          v
ObservationHandler callbacks
          |
          +------> Timer / Counter / Gauge update
          |
          +------> Histogram buckets / exemplars
          |
          +------> Tracing span / event
          |
          v
Registry bookkeeping and filters
          |
          v
Scrape endpoint or scheduled exporter
          |
          v
Network, collector and backend ingestion
~~~

Các nhóm chi phí thường gặp:

| Thành phần | Chi phí có thể phát sinh |
|---|---|
| Tạo Observation | Tạo context, object, scope và callback |
| Tạo hoặc tra meter | Lookup, tag matching, registry bookkeeping |
| Ghi Counter/Timer | Atomic update, đo thời gian, đồng bộ nội bộ |
| Tag values | Tạo chuỗi, chuẩn hóa, tìm meter theo identity |
| Histogram/SLO | Cập nhật nhiều bucket và tăng số series |
| Tracing handler | Tạo span, attributes, event và sampling |
| Exporter | Batch, serialize, nén, network và retry |
| Scrape endpoint | Đọc registry, serialize payload và phục vụ HTTP |
| Backend | Ingest, index, lưu trữ và truy vấn |

Cần phân biệt chi phí trên đường request với chi phí nền. Ví dụ Timer.record() ảnh hưởng trực tiếp tới thread xử lý request; exporter chạy theo chu kỳ có thể tiêu thụ CPU và network ở thread riêng. Khi chỉ đo latency request, bạn có thể bỏ sót chi phí nền của pipeline metrics.

## 2. Đặt câu hỏi đo lường trước khi chạy benchmark

Một phép thử hữu ích phải trả lời một câu hỏi cụ thể. Ví dụ:

- Việc tạo Observation và mở scope làm tăng bao nhiêu latency?
- DefaultMeterObservationHandler ghi Timer/Counter tốn bao nhiêu CPU?
- Bật histogram làm tăng allocation và số series bao nhiêu?
- Thêm tracing handler với sampling có làm giảm throughput không?
- Exporter và scrape endpoint tiêu thụ bao nhiêu CPU, memory và network?
- Với cùng latency SLO, hệ thống còn xử lý được bao nhiêu request mỗi giây?

Không gộp mọi thay đổi vào một lần so sánh duy nhất. Nếu đồng thời bật Observation, histogram, tracing và exporter, bạn chỉ biết tổng tác động, không biết thành phần nào gây ra thay đổi.

## 3. Xây dựng các cấu hình so sánh

Nên có một baseline và các mức bật instrumentation tăng dần:

| Biến thể | Nội dung | Chi phí được cô lập |
|---|---|---|
| A — baseline | Không tạo Observation hoặc gọi meter trong đường được thử | Chi phí xử lý nghiệp vụ |
| B — Observation only | Tạo Observation với handler rỗng, không ghi meter | Context, lifecycle và scope |
| C — metrics | Observation + DefaultMeterObservationHandler + Timer/Counter | Chi phí ghi meter |
| D — histogram | Như C, thêm histogram/SLO | Chi phí bucket và series |
| E — tracing | Như C hoặc D, thêm tracing handler và sampling | Chi phí span và context propagation |
| F — full pipeline | Registry, exporter/scrape và cấu hình gần production | Chi phí vận hành tổng thể |

Các mức này giúp xác định chi phí tăng ở đâu. Không phải ứng dụng nào cũng cần đủ sáu biến thể; chọn những lớp thực sự được triển khai.

Để biến thể B thực sự đi qua lifecycle, đăng ký một handler chỉ hỗ trợ context và không ghi meter. Nếu registry không có handler và phiên bản Micrometer tối ưu Observation thành no-op, biến thể đó có thể không đo được chi phí lifecycle:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;

ObservationHandler<Observation.Context> lifecycleOnly =
    new ObservationHandler<>() {
        @Override
        public boolean supportsContext(Observation.Context context) {
            return true;
        }
    };

registry.observationConfig().observationHandler(lifecycleOnly);
~~~

Khi so sánh A và C, chỉ thay đổi instrumentation thuộc phạm vi đang nghiên cứu. Giữ nguyên business logic, database, cache, thread pool, JVM flags, resource limits và traffic mix. Nếu hệ thống có auto-instrumentation của Spring Boot, cần ghi rõ nó còn bật hay đã được loại khỏi cả hai biến thể.

## 4. Tắt đúng phạm vi instrumentation

Một cờ cấu hình có thể giúp bật/tắt instrumentation thủ công:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import java.util.function.Supplier;

@ConfigurationProperties(prefix = "app.observation")
record ObservationProperties(boolean checkoutEnabled) {}

@Component
public class CheckoutObservation {
    private final ObservationRegistry registry;
    private final boolean enabled;

    public CheckoutObservation(
            ObservationRegistry registry,
            ObservationProperties properties) {
        this.registry = registry;
        this.enabled = properties.checkoutEnabled();
    }

    public <T> T observe(Supplier<T> work) {
        if (!enabled) {
            return work.get();
        }

        return Observation.createNotStarted(
                "checkout.submit",
                registry
            )
            .lowCardinalityKeyValue("operation", "submit")
            .observe(work);
    }
}
~~~

Đăng ký configuration properties bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties(ObservationProperties.class)`. Cấu hình biến thể:

~~~properties
# Instrumentation bật
app.observation.checkout-enabled=true

# Baseline cho riêng checkout wrapper
app.observation.checkout-enabled=false
~~~

Cờ này chỉ tắt Observation được tạo qua wrapper trên. Nó không tự tắt Spring MVC observations, datasource instrumentation, các Counter/Timer gọi trực tiếp hoặc exporter khác. Muốn đo toàn bộ pipeline, phải liệt kê rõ thành phần nào còn hoạt động trong từng biến thể.

Không thay đổi business behavior khi tắt đo. Hai nhánh phải gọi cùng một hàm work, cùng transaction và cùng downstream operations. Không dùng hai build khác nhau nếu có thể giữ một binary và thay đổi bằng cấu hình.

## 5. Chọn workload gần với production

Tải thử nên đại diện cho cách ứng dụng thực sự được sử dụng:

- Tỷ lệ request theo endpoint hoặc use case.
- Kích thước payload và phân bố dữ liệu.
- Tỷ lệ cache hit/miss.
- Số lần gọi database và downstream service.
- Tỷ lệ thành công, validation failure và lỗi kỹ thuật.
- Mức đồng thời và phân bố thời gian giữa các request.
- Các tác vụ nền, batch và scheduled jobs.
- Kích thước tag set và số lượng meter đã đăng ký.

Nếu chỉ benchmark một endpoint nhẹ với cache nóng, kết quả không đại diện cho một workflow có nhiều query, event và histogram. Nếu database chiếm gần toàn bộ thời gian, overhead của instrumentation có thể bị che khuất; điều đó vẫn có ý nghĩa cho production nhưng không giúp hiểu chi phí riêng của meter.

Nên dùng dữ liệu đã được chuẩn bị và lặp lại được. Tránh để mỗi lần chạy có dataset, cache state hoặc downstream latency khác nhau.

## 6. Chọn mô hình tải: arrival rate hay concurrency

Hai mô hình tải phổ biến trả lời những câu hỏi khác nhau:

| Mô hình | Cách tạo tải | Phù hợp |
|---|---|---|
| Open workload / fixed arrival rate | Gửi số request mục tiêu mỗi giây, bất kể latency hiện tại | So sánh latency ở cùng offered load |
| Closed workload / fixed virtual users | Mỗi virtual user chờ response rồi mới gửi request tiếp | Mô phỏng nhóm client có concurrency cố định |

Với fixed arrival rate, nếu hệ thống chậm lại, request có thể xếp hàng hoặc generator báo không đủ VU để duy trì tốc độ. Đây là tín hiệu quan trọng khi đánh giá khả năng chịu tải.

Với fixed virtual users, khi latency tăng thì tốc độ gửi request tự giảm. Nếu chỉ nhìn throughput, biến thể chậm hơn có thể trông như đang chịu tải nhẹ hơn. Vì vậy, cần biết rõ load model và theo dõi cả offered rate lẫn completed rate.

Khi so sánh instrumentation, hãy bắt đầu ở một mức tải ổn định dưới ngưỡng bão hòa, sau đó tăng tải theo các nấc để tìm điểm mà latency hoặc error rate vượt SLO.

## 7. Warm-up, steady state và lặp lại phép thử

JVM cần thời gian để nạp class, biên dịch JIT, khởi tạo connection pool và làm nóng cache. Đo ngay sau khi process khởi động có thể phản ánh startup cost thay vì chi phí steady-state.

Một lần chạy nên có các giai đoạn:

1. **Khởi động:** chờ ứng dụng sẵn sàng, kiểm tra health và kết nối downstream.
2. **Warm-up:** phát workload đại diện nhưng chưa dùng kết quả làm số đo chính.
3. **Steady-state measurement:** giữ offered load ổn định trong một khoảng đủ dài.
4. **Cool-down:** dừng tải và quan sát GC, queue, exporter hoặc tác vụ nền còn tồn đọng.
5. **Lặp lại:** chạy lại từng biến thể nhiều lần để biết độ dao động.

Không chọn warm-up chỉ theo một con số cố định. Hãy quan sát throughput, latency, CPU và JIT/GC cho tới khi các chỉ số ổn định tương đối. Mỗi lần chạy cần cùng thời lượng warm-up và measurement.

Nếu có thể, đổi thứ tự biến thể giữa các lần lặp, ví dụ A-B-B-A hoặc ngẫu nhiên có kiểm soát. Cách này giảm ảnh hưởng của nhiệt độ CPU, noisy neighbor, cache state và tải nền thay đổi theo thời gian.

## 8. Giữ môi trường thử nghiệm giống nhau

Để kết quả có thể so sánh, ghi lại và giữ cố định:

- JDK vendor/version và JVM flags.
- CPU model, số core được cấp và container CPU quota.
- Memory limit, heap size và GC algorithm.
- Số replica, thread pool, connection pool và autoscaling policy.
- Database version, dataset, cache state và downstream dependencies.
- Network path, TLS và proxy.
- Prometheus scrape interval, OTLP export step và tracing sampling.
- Phiên bản ứng dụng, cấu hình feature flags và traffic mix.

Không chạy load generator trên cùng một CPU quota với ứng dụng nếu điều đó làm hai bên tranh tài nguyên. Theo dõi load generator để chắc chắn nó đủ khả năng phát offered rate và không trở thành bottleneck.

Nếu dùng Kubernetes, ghi nhận request/limit CPU và memory, node placement, throttling và restart. Hai pod chạy trên node có mức tranh chấp khác nhau có thể tạo kết quả sai lệch dù cấu hình ứng dụng giống nhau.

## 9. Các chỉ số cần thu thập

Đừng chỉ nhìn latency trung bình. Hãy thu thập tối thiểu:

| Nhóm | Chỉ số |
|---|---|
| Client/load generator | Offered RPS, completed RPS, p50/p95/p99 latency, timeout và error rate |
| Ứng dụng | CPU, memory, thread count, queue depth, active requests |
| JVM | Allocation rate, heap occupancy, GC count/time/pause, safepoint |
| Metrics pipeline | Số meter/series, scrape duration, payload size, export failures |
| Hạ tầng | CPU throttling, network bytes, disk/collector ingest nếu có |

Dùng load generator để đo latency từ góc nhìn client. Timer của Micrometer rất hữu ích để phân tích operation bên trong ứng dụng, nhưng không bao gồm toàn bộ network, queue và thời gian chờ phía client.

Nếu chỉ dùng Timer do chính instrumentation đang được thử tạo ra để chứng minh overhead của nó, phép đo có thể tự ảnh hưởng đến kết quả. Vì vậy, cần một nguồn quan sát độc lập như load generator, process CPU metrics hoặc JFR được bật giống nhau trong mọi biến thể.

## 10. Tính overhead và chuẩn hóa kết quả

Giả sử cùng offered load và cùng workload:

- p95 baseline là 40 ms.
- p95 khi bật instrumentation là 42 ms.

Mức tăng tuyệt đối là 2 ms. Tỷ lệ tăng:

\[
\text{latency overhead (\%)} =
\frac{p95_{\text{on}} - p95_{\text{off}}}
     {p95_{\text{off}}} \times 100
\]

Với ví dụ trên, mức tăng là 5%. Đây chỉ là minh họa cách tính, không phải mức overhead mặc định của Micrometer.

Có thể chuẩn hóa CPU theo số request hoàn tất:

\[
\text{CPU seconds/request} =
\frac{\text{process CPU seconds}}
     {\text{completed requests}}
\]

Chỉ số này hữu ích hơn CPU percentage đơn lẻ khi hai lần chạy có throughput khác nhau. Có thể chuẩn hóa allocation tương tự:

\[
\text{allocated bytes/request} =
\frac{\text{allocated bytes}}
     {\text{completed requests}}
\]

Khi báo cáo, hãy giữ cả giá trị tuyệt đối và tỷ lệ thay đổi. Phần trăm có thể gây hiểu nhầm nếu baseline rất nhỏ; giá trị tuyệt đối giúp đánh giá tác động lên SLO.

Nếu thử nghiệm ở vùng bão hòa, so sánh sustainable throughput tại cùng giới hạn p95/p99 và error rate. Không kết luận từ maximum RPS nếu một biến thể đã vi phạm latency SLO hoặc làm timeout tăng.

## 11. Ví dụ load test với fixed arrival rate

Có thể dùng k6 để phát một tốc độ request ổn định. Ví dụ sau minh họa cấu hình, các giá trị cần điều chỉnh theo năng lực hệ thống:

~~~javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    steady_load: {
      executor: 'constant-arrival-rate',
      rate: 200,
      timeUnit: '1s',
      duration: '10m',
      preAllocatedVUs: 50,
      maxVUs: 200
    }
  }
};

export default function () {
  const response = http.get(__ENV.BASE_URL + '/orders');
  check(response, {
    'response is successful': (r) => r.status >= 200 && r.status < 300
  });
}
~~~

Chạy cùng script cho từng biến thể. Chỉ thay đổi cấu hình instrumentation; giữ nguyên target workload, test data, duration và load generator. Ghi lại dropped iterations hoặc cảnh báo thiếu VU vì chúng cho biết generator không duy trì được offered rate.

Nếu endpoint có nhiều loại request, dùng scenario mix với tỷ lệ gần production thay vì chỉ gọi một route. Với workflow cần đăng nhập hoặc ghi dữ liệu, chuẩn bị dữ liệu và reset state giữa các lần chạy để kết quả có thể lặp lại.

## 12. Theo dõi CPU, allocation và GC

Instrumentation có thể làm tăng allocation do tạo Observation context, key-value, scope, span hoặc chuỗi tag. Allocation cao có thể dẫn tới GC thường xuyên hơn và làm p99 tăng dù CPU trung bình chỉ thay đổi ít.

Dùng Java Flight Recorder (JFR) hoặc profiler phù hợp để kiểm tra:

- Hot methods liên quan đến Observation, registry và meter recording.
- Object allocation theo class và call stack.
- Lock contention hoặc thread parking.
- GC pause, allocation pressure và heap occupancy.
- CPU time ở exporter, serializer hoặc tracing SDK.

Chạy profiler với cấu hình giống nhau ở cả baseline và instrumented run, hoặc thực hiện một lượt profiling riêng sau khi đã xác định được chênh lệch. Profiler cũng có overhead; không bật nó chỉ ở một biến thể rồi so sánh trực tiếp.

Nếu chạy trong container, theo dõi CPU throttling. Một biến thể có thêm công việc nhỏ có thể bị throttle và tạo latency tail lớn hơn khi đã chạm quota. Đây là tác động vận hành thực tế cần được ghi nhận, không nên bỏ qua bằng cách chỉ đo trên máy developer không giới hạn CPU.


## 13. Dùng JMH để cô lập chi phí một thao tác

Load test đo tác động ở cấp hệ thống. Khi cần biết riêng chi phí của Timer.record() hoặc tạo Observation, có thể dùng JMH để benchmark một đoạn code nhỏ trong JVM.

Ví dụ so sánh một phép tính với và không ghi Timer:

~~~java
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.infra.Blackhole;

@State(Scope.Thread)
public class TimerRecordingBenchmark {
    private Timer timer;

    @Setup(Level.Trial)
    public void setup() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        timer = registry.timer("benchmark.operation");
    }

    private long work() {
        return 42L * 17L;
    }

    @Benchmark
    public void baseline(Blackhole blackhole) {
        blackhole.consume(work());
    }

    @Benchmark
    public void withTimer(Blackhole blackhole) {
        timer.record(() -> blackhole.consume(work()));
    }
}
~~~

JMH tự quản lý warm-up, measurement iterations và forks theo cấu hình benchmark. Kết quả cho biết chi phí tương đối của thao tác trong điều kiện cô lập, không dự đoán trực tiếp latency của HTTP request trong production.

Khi benchmark Observation, tạo các biến thể riêng: không Observation, Observation với registry không có meter handler và Observation với DefaultMeterObservationHandler. Như vậy có thể phân biệt chi phí tạo context/lifecycle với chi phí ghi meter.

Không tự viết vòng lặp gọi System.nanoTime() để thay JMH. Cách đo đơn giản dễ bị ảnh hưởng bởi JIT, dead-code elimination, timer resolution và scheduling.

## 14. Tách các lớp để tìm nguồn overhead

Một ma trận thử nghiệm có thể giúp định vị phần tốn kém:

| Thử nghiệm | Observation | Meter handler | Histogram | Tracing | Export/scrape |
|---|---:|---:|---:|---:|---:|
| Baseline | Tắt | Tắt | Tắt | Tắt | Tắt |
| Lifecycle | Bật | Tắt | Tắt | Tắt | Tắt |
| Basic metrics | Bật | Bật | Tắt | Tắt | Tắt hoặc cố định |
| Histogram | Bật | Bật | Bật | Tắt | Tắt hoặc cố định |
| Tracing | Bật | Bật | Theo cấu hình | Bật | Theo cấu hình |
| Full pipeline | Bật | Bật | Theo production | Theo production | Bật |

Giữ cùng registry backend trong các biến thể cần so sánh. Nếu thay SimpleMeterRegistry bằng Prometheus registry cùng lúc với bật histogram, bạn đang thay hai yếu tố. Khi cần đánh giá backend cụ thể, tách thành một thử nghiệm riêng.

Đối với Prometheus pull, ghi meter thường diễn ra trong request, còn serialize payload xảy ra khi scrape. Chạy scrape đồng thời để đo tác động export lên CPU và latency. Với push registry, giữ export step, batch size và collector giống nhau giữa các lần chạy.

Tracing sampling là một biến độc lập. So sánh tracing tắt, sampling thấp và sampling cao nếu cần biết chi phí span. Sampling trace không thay thế metrics và không nên dùng để giảm tần suất Counter/Timer nghiệp vụ.

## 15. Kiểm tra cách đăng ký và tái sử dụng meter

Meter nên được đăng ký một lần và tái sử dụng. Tìm meter trong registry hoặc tạo builder cùng tag trên mỗi request có thể thêm lookup và allocation không cần thiết.

~~~java
@Component
public class OrderMetrics {
    private final Counter created;

    public OrderMetrics(MeterRegistry registry) {
        this.created = Counter.builder("orders.created")
            .description("Số đơn hàng đã tạo")
            .register(registry);
    }

    public void recordCreated() {
        created.increment();
    }
}
~~~

Tránh tạo tag value từ dữ liệu thay đổi theo request:

~~~java
// Không nên: mỗi order ID có thể tạo một meter identity mới.
registry.counter("orders.created", "order.id", orderId).increment();
~~~

Chi phí của cardinality cao không chỉ là lookup trong ứng dụng. Nó còn làm tăng số series, memory, network payload, index và backend storage. Trong benchmark, hãy dùng cùng tập tag và cùng số series ở mọi biến thể, sau đó chạy một thí nghiệm riêng để đánh giá tác động của cardinality.

## 16. Đánh giá histogram và percentile

Histogram có thể làm tăng chi phí ghi vì mỗi observation cập nhật cấu trúc phân phối và có thể cập nhật nhiều bucket. Số bucket và số tổ hợp tag quyết định số series được xuất.

Nên so sánh ít nhất:

- Timer không bật histogram.
- Timer bật percentile histogram với bucket mặc định.
- Timer có SLO boundaries theo nhu cầu.
- Các cấu hình tag đại diện cho production.

Không so sánh histogram với non-histogram nếu traffic hoặc số meter khác nhau. Ghi lại số series và payload size để giải thích mức tăng backend ingest.

Client-side percentile có thể cần bộ đệm và thống kê trong process. Histogram bucket thường hữu ích hơn khi cần tổng hợp phân phối trên nhiều instance. Hãy chọn theo backend và câu hỏi vận hành, không bật tất cả percentile chỉ để dashboard có nhiều con số.

## 17. Mẫu ghi nhận kết quả

Điền số đo thực tế sau mỗi lần chạy. Không dùng số liệu từ một lần chạy đơn lẻ nếu hệ thống có độ dao động đáng kể.

| Chỉ số | A — baseline | C — metrics | D — histogram | F — full pipeline |
|---|---:|---:|---:|---:|
| Offered RPS | | | | |
| Completed RPS | | | | |
| p50 latency (ms) | | | | |
| p95 latency (ms) | | | | |
| p99 latency (ms) | | | | |
| Error rate (%) | | | | |
| CPU seconds/request | | | | |
| Allocated bytes/request | | | | |
| GC pause time (%) | | | | |
| Active time series | | | | |
| Scrape/export duration | | | | |
| Payload size (bytes) | | | | |

Ghi kèm cấu hình test: commit/build, JDK, CPU/memory limit, replica count, load model, request mix, warm-up duration, measurement duration, scrape interval, export step và tracing sampling rate.

Báo cáo median của nhiều lần chạy cùng độ phân tán, ví dụ min/max hoặc percentile của các kết quả theo run. Nếu hai biến thể chênh lệch ít hơn mức dao động tự nhiên của môi trường, chưa đủ bằng chứng để kết luận có regression.

## 18. Diễn giải kết quả và ra quyết định

Một số cách đọc kết quả:

- p95 tăng nhưng CPU/request không đổi: kiểm tra allocation, lock contention, queueing và GC.
- CPU/request tăng cùng allocation/request: kiểm tra context, tag construction, histogram hoặc span creation.
- Request latency ổn định nhưng CPU nền tăng: kiểm tra exporter, scrape serialization, batch và retry.
- Throughput giảm khi offered rate cố định: kiểm tra CPU saturation, thread pool, queue depth và downstream capacity.
- Chỉ p99 tăng: kiểm tra GC pause, scheduling, contention và scrape/export trùng thời điểm.
- Số series tăng mạnh khi bật histogram: kiểm tra bucket count, tag combinations và instance count.

Không kết luận rằng Micrometer quá tốn kém chỉ từ một biến thể có histogram, tracing và high-cardinality tags. Trước tiên xác định phần nào tạo chi phí và liệu cấu hình đó có thật sự cần thiết.

Quyết định nên dựa trên tác động so với SLO và ngân sách tài nguyên. Nếu overhead nhỏ hơn mức biến động đo được và không làm giảm capacity, giữ instrumentation có giá trị vận hành. Nếu chi phí vượt ngân sách, tối ưu tag, giảm histogram không cần thiết, điều chỉnh sampling tracing, cache meter reference hoặc tách exporter; sau đó chạy lại đúng workload để xác nhận.

## 19. Các lỗi thường gặp

- **Đo ngay sau khi khởi động JVM:** kết quả bị chi phối bởi JIT, class loading và cache warm-up.
- **So sánh hai workload khác nhau:** chênh lệch không thể quy cho instrumentation.
- **Chỉ nhìn latency trung bình:** tail latency và error rate có thể xấu đi.
- **Dùng fixed VU nhưng bỏ qua offered rate:** biến thể chậm có thể tự nhận ít request hơn.
- **Chạy load generator chung CPU với ứng dụng:** hai bên tranh tài nguyên.
- **Tắt wrapper nhưng quên auto-instrumentation:** baseline vẫn còn metrics khác.
- **Bật profiler ở một biến thể:** profiler tạo overhead không đồng đều.
- **Đo một lần duy nhất:** kết quả có thể là nhiễu môi trường.
- **Bật histogram và tracing cùng lúc mà không tách lớp:** không biết thành phần nào gây overhead.
- **Dùng JMH để dự đoán trực tiếp production throughput:** benchmark vi mô không mô phỏng network, DB và queueing.
- **Bỏ qua chi phí scrape/export:** chỉ nhìn request path sẽ thiếu phần chi phí nền.
- **Không ghi lại số series:** bỏ qua tác động cardinality và storage.

## 20. Checklist benchmark

- [ ] Viết rõ câu hỏi và phạm vi instrumentation cần đánh giá.
- [ ] Có baseline không thực hiện phép đo trong đường code được thử.
- [ ] Tách Observation lifecycle, meter handler, histogram, tracing và exporter.
- [ ] Giữ nguyên binary, JVM, resource limit và downstream dependencies.
- [ ] Dùng dataset và request mix đại diện production.
- [ ] Chọn open hoặc closed load model và ghi rõ offered rate.
- [ ] Warm-up đến khi hệ thống ổn định tương đối.
- [ ] Đo steady state đủ lâu và lặp lại nhiều lần.
- [ ] Theo dõi p50/p95/p99, throughput và error rate.
- [ ] Chuẩn hóa CPU và allocation theo request hoàn tất.
- [ ] Theo dõi GC, queue, throttling, series count và payload size.
- [ ] Dùng JMH chỉ để cô lập thao tác nhỏ.
- [ ] Giữ profiler giống nhau giữa các biến thể hoặc tách riêng lượt profiling.
- [ ] Ghi lại cấu hình và kết quả để có thể tái lập.
- [ ] Chỉ tối ưu sau khi xác định được nguồn overhead.

Đánh giá chi phí Micrometer cần kết hợp tải thực tế và phép thử cô lập. Load test cho biết tác động tổng thể lên latency, throughput và tài nguyên; JMH giúp hiểu chi phí của một thao tác trong JVM. Khi bật/tắt từng lớp có kiểm soát, giữ workload và môi trường ổn định, bạn có thể xác định chính xác phần instrumentation nào tiêu tốn ngân sách và tối ưu mà vẫn giữ lại tín hiệu vận hành cần thiết.

