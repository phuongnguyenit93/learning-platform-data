# Đo tỷ lệ dùng fallback mà không che mất sự cố thực tế

## Vì sao cần đo fallback riêng?

Trong Spring Cloud Circuit Breaker, fallback giúp ứng dụng tiếp tục trả lời khi lời gọi đến dịch vụ phụ thuộc thất bại hoặc Circuit Breaker đang `OPEN`. Tuy nhiên, nếu chỉ theo dõi HTTP status cuối cùng, một fallback trả về HTTP 200 có thể khiến dashboard trông như mọi thứ vẫn bình thường trong khi dịch vụ phụ thuộc đã lỗi liên tục.

Vì vậy, cần quan sát riêng ba phần của một thao tác được bảo vệ:

1. **Thao tác nghiệp vụ đi vào vùng bảo vệ:** tổng số yêu cầu mà ứng dụng định xử lý qua Circuit Breaker.
2. **Lời gọi chính đến dependency:** số lần supplier thực sự bắt đầu, số ngoại lệ và thời gian thực thi.
3. **Fallback:** số lần handler được gọi, số phản hồi fallback được tạo, số lần chính fallback thất bại và thời gian xử lý.

Ba phần này trả lời những câu hỏi khác nhau. Tỷ lệ fallback cho biết ứng dụng thường phải dùng đường dự phòng đến mức nào. Tỷ lệ lỗi của dependency cho biết các lần gọi thực sự được thực thi gặp lỗi ra sao. Số lần bị từ chối khi mạch mở cho biết Circuit Breaker đang ngăn request mới đi đến dependency.

## Xác định đúng mẫu số trước khi tính tỷ lệ

Không có một mẫu số duy nhất phù hợp cho mọi dashboard. Hãy đặt tên rõ cho từng tỷ lệ và chỉ chia các số đếm cùng phạm vi:

| Chỉ số | Công thức | Ý nghĩa |
| --- | --- | --- |
| Tỷ lệ thao tác dùng fallback | Số lần fallback được gọi / số thao tác đi vào vùng bảo vệ | Bao nhiêu thao tác nghiệp vụ cần đường dự phòng. |
| Tỷ lệ ngoại lệ của lời gọi chính | Số ngoại lệ từ supplier / số lần supplier thực sự bắt đầu | Lời gọi đã thử đến dependency gặp ngoại lệ với tần suất nào. |
| Tỷ lệ fallback trả được phản hồi | Số phản hồi fallback được tạo / số lần fallback được gọi | Handler có tạo được kết quả thay thế hay không. |
| Tỷ lệ fallback thất bại | Số lần handler ném lỗi / số lần fallback được gọi | Đường dự phòng có tự gặp lỗi hay không. |
| Tỷ lệ bị Circuit Breaker từ chối | Số lần bị từ chối khi mạch mở / số thao tác đi vào vùng bảo vệ | Bao nhiêu thao tác không được gửi đến dependency vì mạch đang mở. |

Một điểm quan trọng: khi Circuit Breaker đang `OPEN`, supplier không chạy. Lời gọi bị từ chối có thể đi thẳng đến fallback, vì vậy nó làm tăng số lần fallback nhưng không làm tăng số lần supplier bắt đầu. Nếu lấy số lần fallback chia cho số lần supplier bắt đầu, tỷ lệ có thể vượt 100% và không còn mang ý nghĩa của một tỷ lệ thao tác. Dùng số thao tác đi vào vùng bảo vệ làm mẫu số cho fallback rate.

Ví dụ trong một khoảng 5 phút có 1.000 thao tác đi vào vùng bảo vệ, 180 lần fallback được gọi, 820 lần supplier bắt đầu và 90 ngoại lệ từ supplier:

- Tỷ lệ thao tác dùng fallback: (180 / 1.000 = 18\%\).
- Tỷ lệ ngoại lệ của supplier: (90 / 820 \approx 10,98\%\).
- Có 180 lần fallback được gọi, trong đó cần tiếp tục phân biệt handler trả phản hồi hay ném lỗi.

Hai tỷ lệ đầu không mâu thuẫn nhau. Một phần fallback có thể được gọi vì Circuit Breaker từ chối lời gọi khi đang mở, không phải vì supplier vừa phát sinh ngoại lệ.

## Phân biệt fallback được gọi và fallback thành công

Fallback được gọi không đồng nghĩa fallback đã tạo được kết quả hữu ích. Cần ghi nhận ít nhất ba kết quả:

- `cache`: handler trả dữ liệu cache còn trong giới hạn tuổi cho phép.
- `unavailable`: handler trả trạng thái không có dữ liệu hoặc dịch vụ tạm thời không khả dụng.
- `error`: chính handler ném lỗi, chẳng hạn cache cũng không truy cập được.

`unavailable` vẫn là một phản hồi fallback được tạo thành công về mặt thực thi handler, nhưng không phải dữ liệu thay thế có sẵn. Nếu gộp `cache` và `unavailable` vào một số “fallback thành công”, dashboard có thể che khuất việc hệ thống không còn dữ liệu để phục vụ. Hãy giữ nhãn chế độ phản hồi để người vận hành biết người dùng đang nhận gì.

Tương tự, số lần fallback trả được response không chứng minh dependency khỏe. Nếu dependency đang lỗi và cache vẫn hoạt động, fallback có thể trả response liên tục trong khi tỷ lệ lỗi của dependency tăng cao.

## Instrumentation bằng Micrometer

Micrometer có thể ghi nhận các counter và timer cho thao tác chính lẫn fallback. Ví dụ dưới đây đo một dịch vụ danh mục đồng bộ. Các kiểu `CatalogClient`, `ProductCache`, `CachedProduct` và `ProductView` là kiểu của ứng dụng.

```java
import java.util.Optional;
import java.util.concurrent.TimeoutException;

import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;

@Service
public class CatalogService {
    private final CatalogClient catalogClient;
    private final ProductCache productCache;
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final MeterRegistry registry;

    public CatalogService(
            CatalogClient catalogClient,
            ProductCache productCache,
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            MeterRegistry registry) {
        this.catalogClient = catalogClient;
        this.productCache = productCache;
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.registry = registry;
    }

    public ProductView find(String productId) {
        increment("catalog.protected.operations");

        return circuitBreakerFactory.create("catalog").run(
            () -> {
                increment("catalog.primary.attempts");
                Timer.Sample sample = Timer.start(registry);
                try {
                    ProductView result = ProductView.current(
                        catalogClient.find(productId)
                    );
                    sample.stop(timer("catalog.primary.duration", "success"));
                    return result;
                } catch (RuntimeException error) {
                    increment("catalog.primary.exceptions", "reason", reason(error));
                    sample.stop(timer("catalog.primary.duration", "error"));
                    throw error;
                }
            },
            error -> fallback(productId, error)
        );
    }

    private ProductView fallback(String productId, Throwable cause) {
        String reason = reason(cause);
        increment("catalog.fallback.invocations", "reason", reason);
        Timer.Sample sample = Timer.start(registry);

        try {
            Optional<CachedProduct> cached = productCache.find(productId);
            if (cached.isPresent()) {
                CachedProduct entry = cached.get();
                ProductView result = ProductView.stale(entry.details(), entry.cachedAt());
                increment("catalog.fallback.responses", "mode", "cache");
                sample.stop(timer("catalog.fallback.duration", "response"));
                return result;
            }

            ProductView result = ProductView.unavailable(productId);
            increment("catalog.fallback.responses", "mode", "unavailable");
            sample.stop(timer("catalog.fallback.duration", "response"));
            return result;
        } catch (RuntimeException fallbackError) {
            increment("catalog.fallback.errors", "reason", reason);
            sample.stop(timer("catalog.fallback.duration", "error"));
            throw fallbackError;
        }
    }

    private String reason(Throwable error) {
        if (error instanceof CallNotPermittedException) return "circuit_open";
        if (error instanceof TimeoutException) return "timeout";
        if (error instanceof ResourceAccessException) return "connection_or_io";
        if (error instanceof HttpServerErrorException) return "http_5xx";
        return "other";
    }

    private void increment(String name, String... tags) {
        Counter.builder(name)
            .tags(tags)
            .register(registry)
            .increment();
    }

    private Timer timer(String name, String outcome) {
        return Timer.builder(name)
            .tag("outcome", outcome)
            .register(registry);
    }
}
```

Trong ví dụ:

- `catalog.protected.operations` tăng một lần cho mỗi thao tác đi vào vùng bảo vệ.
- `catalog.primary.attempts` chỉ tăng khi supplier thực sự bắt đầu. Khi Circuit Breaker mở và từ chối lời gọi, counter này không tăng.
- `catalog.primary.exceptions` đếm ngoại lệ supplier ném ra. Counter này không nhất thiết bằng số lỗi mà Resilience4j ghi nhận, vì predicate `recordException` hoặc `ignoreException` có thể phân loại một số ngoại lệ thành bỏ qua hoặc thành công trong thống kê.
- `catalog.fallback.invocations` tăng khi handler bắt đầu chạy, kể cả khi nguyên nhân là `CallNotPermittedException`.
- `catalog.fallback.responses` đếm các phản hồi fallback đã tạo và gắn `mode` để phân biệt cache với trạng thái unavailable.
- `catalog.fallback.errors` đếm trường hợp chính fallback ném lỗi.
- Hai timer tách latency của lời gọi chính và latency của handler fallback.

Đây là instrumentation minh họa; khi dùng production, nên chuẩn hóa tên metric theo quy ước của hệ thống và bảo đảm các bean, kiểu kết quả cùng API của provider khớp phiên bản đang dùng. Nếu fallback có nhiều nhánh hơn, thêm các giá trị `mode` hữu hạn, có ý nghĩa.

## Phân loại nguyên nhân bằng tag có giới hạn

Tag `reason` giúp biết fallback xảy ra vì mạch đang mở, timeout, lỗi kết nối hay phản hồi 5xx. Giá trị tag phải là một tập nhỏ và ổn định. Ví dụ:

| Giá trị `reason` | Ý nghĩa |
| --- | --- |
| `circuit_open` | Circuit Breaker từ chối lời gọi mới. |
| `timeout` | Lời gọi bị timeout. |
| `connection_or_io` | Lỗi kết nối hoặc truy cập tài nguyên. |
| `http_5xx` | Dịch vụ hoặc gateway trả phản hồi 5xx. |
| `other` | Nhóm lỗi còn lại cần điều tra. |

Không đưa `productId`, `customerId`, URL đầy đủ, request ID, exception message hoặc stack trace vào metric tag. Những giá trị này tạo cardinality rất cao, làm tăng bộ nhớ và chi phí lưu trữ của hệ thống metrics. Nếu cần điều tra một request cụ thể, dùng log hoặc distributed trace với correlation ID; giữ metric ở mức tổng hợp.

Phân loại trong ví dụ chỉ nhận diện một số lớp ngoại lệ thường gặp. Nếu HTTP client bọc lỗi trong `ResourceAccessException` hoặc `CompletionException`, hãy chuẩn hóa `cause` theo các wrapper đã biết trước khi phân loại. Cũng cần nhớ rằng lỗi 4xx có thể là lỗi nghiệp vụ bình thường, lỗi xác thực hoặc tín hiệu cấu hình; không nên gộp tất cả vào một nhóm mà không dựa trên hợp đồng API.

## Đối chiếu metric tùy chỉnh với Resilience4j

Counter tùy chỉnh đo hành vi ở ranh giới ứng dụng. Resilience4j metrics đo kết quả theo quy tắc của Circuit Breaker và cửa sổ trượt. Hai nguồn nên được hiển thị cạnh nhau:

| Nguồn | Chỉ số nên xem | Câu hỏi trả lời |
| --- | --- | --- |
| Micrometer của ứng dụng | Protected operations, primary attempts, fallback invocations, fallback responses/errors. | Người dùng có phải nhận kết quả dự phòng không và handler có hoạt động không? |
| Resilience4j | State, buffered calls, failed calls, successful calls, not-permitted calls, failure rate, slow-call rate. | Theo chính sách ghi nhận và sliding window, Circuit Breaker đánh giá dependency thế nào? |
| HTTP client | Connection timeout, read timeout, status code, latency. | Lỗi phát sinh ở kết nối, chờ phản hồi hay xử lý status? |
| Distributed tracing | Span của request chính và span fallback/cache. | Một request cụ thể đã đi qua đường nào và mất thời gian ở đâu? |

`primary.exceptions` không thay thế failure rate của Resilience4j. Ví dụ, một ngoại lệ bị `ignoreException` vẫn được counter tùy chỉnh đếm là ngoại lệ supplier, nhưng không được cộng vào failure rate của Circuit Breaker. Ngược lại, nếu muốn có counter tích lũy chỉ cho các kết quả Resilience4j thực sự ghi nhận là thất bại, hãy dùng event publisher của Circuit Breaker hoặc metric do integration cung cấp và xác nhận sự kiện tương ứng với phiên bản thư viện.

Khi mạch đang `OPEN`, `not-permitted calls` tăng trong khi `primary.attempts` có thể giảm. Đây là hành vi mong đợi: Circuit Breaker đang chặn request mới để bảo vệ dependency. Đừng diễn giải việc số lần gọi chính giảm đột ngột là dependency đã phục hồi; đối chiếu state và số lần bị từ chối.

## Tính tỷ lệ trên dashboard

Với Prometheus, Micrometer thường chuyển tên metric dạng dấu chấm thành tên dạng dấu gạch dưới và counter có hậu tố `_total`. Tên thực tế cần kiểm tra tại endpoint metrics của ứng dụng. Với các tên trong ví dụ, có thể xây dựng biểu thức tương tự:

```promql
# Tỷ lệ thao tác cần fallback trong 5 phút
sum(rate(catalog_fallback_invocations_total[5m]))
/
clamp_min(sum(rate(catalog_protected_operations_total[5m])), 1)

# Tỷ lệ ngoại lệ từ supplier trong số lần supplier bắt đầu
sum(rate(catalog_primary_exceptions_total[5m]))
/
clamp_min(sum(rate(catalog_primary_attempts_total[5m])), 1)

# Tỷ lệ handler fallback ném lỗi trong số lần fallback được gọi
sum(rate(catalog_fallback_errors_total[5m]))
/
clamp_min(sum(rate(catalog_fallback_invocations_total[5m])), 1)
```

Các biểu thức trả về tỷ lệ từ 0 đến 1; nhân 100 nếu dashboard cần hiển thị phần trăm. `clamp_min` tránh phép chia cho 0 trong lúc không có lưu lượng. Nếu dashboard lọc theo dependency hoặc instance, phải áp dụng cùng bộ lọc cho cả tử số và mẫu số.

Nên hiển thị cả số tuyệt đối và tỷ lệ. Ví dụ, 100% fallback trên một request có thể là một sự kiện đơn lẻ; 20% fallback trên hàng nghìn request có ý nghĩa vận hành khác. Dùng cửa sổ thời gian phù hợp với lưu lượng và đặt ngưỡng cảnh báo có điều kiện về số lượng request tối thiểu.

## Thiết kế dashboard để không che sự cố

Một dashboard hữu ích nên đặt cạnh nhau:

- Tỷ lệ fallback trên tổng thao tác được bảo vệ.
- Số lần fallback theo `reason`, đặc biệt là `circuit_open`.
- Tỷ lệ và latency của lời gọi chính.
- Trạng thái Circuit Breaker và số lần bị từ chối.
- Tỷ lệ fallback trả cache, trả unavailable và ném lỗi.
- Tuổi dữ liệu cache được sử dụng và latency của fallback.

Khi fallback rate tăng cùng lúc với `circuit_open` và failure rate của Resilience4j tăng, dependency có thể đang suy giảm và Circuit Breaker đang bảo vệ hệ thống. Khi fallback rate tăng nhưng failure rate không tăng, hãy kiểm tra chính sách fallback, lỗi nghiệp vụ bị phân loại, hoặc các lần gọi bị từ chối từ một nguyên nhân khác. Khi fallback handler error tăng, đường dự phòng cũng đang có vấn đề và cần cảnh báo riêng.

Không đặt cảnh báo chỉ dựa trên tỷ lệ fallback thấp. Một tỷ lệ bằng 0 có thể là dấu hiệu khỏe mạnh, nhưng cũng có thể do fallback instrumentation chưa chạy hoặc request không đi qua vùng được đo. Kiểm tra số lượng thao tác, counter fallback và trace mẫu để xác nhận instrumentation hoạt động.

## Kiểm thử instrumentation

Hãy kiểm thử cả đường chính và các nhánh fallback, rồi xác nhận counter tăng đúng một lần cho mỗi thao tác:

| Kịch bản | Protected operations | Primary attempts | Fallback invocations | Kết quả mong đợi |
| --- | ---: | ---: | ---: | --- |
| Dependency trả thành công | +1 | +1 | Không tăng | Primary duration ghi `success`. |
| Dependency ném timeout | +1 | +1 | +1 | Primary exception và fallback response được ghi nhận. |
| Circuit Breaker đang `OPEN` | +1 | Không tăng | +1 | Reason là `circuit_open`; primary không được gọi. |
| Cache có dữ liệu hợp lệ | +1 | Theo nhánh chính | +1 khi fallback chạy | Fallback response có mode `cache`. |
| Cache không có dữ liệu | +1 | Theo nhánh chính | +1 khi fallback chạy | Fallback response có mode `unavailable`. |
| Cache cũng ném lỗi | +1 | Theo nhánh chính | +1 | Fallback error tăng; lỗi được truyền theo hợp đồng của ứng dụng. |

Ngoài kiểm thử unit, nên chạy một kịch bản tích hợp có thể chuyển Circuit Breaker sang `OPEN`, sau đó gửi request để xác nhận supplier không chạy và fallback vẫn được đo. Kiểm tra metrics sau khi request hoàn tất; counter và timer có thể được cập nhật ở các thời điểm khác nhau tùy cách export.

## Những lỗi quan sát thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ theo dõi HTTP 2xx/5xx cuối cùng. | Fallback 200 che mất lỗi của dependency. | Đo primary, fallback và Circuit Breaker riêng. |
| Lấy fallback invocations chia cho primary attempts. | Tỷ lệ sai khi mạch mở vì supplier không chạy. | Dùng protected operations làm mẫu số cho fallback rate. |
| Coi primary exceptions bằng failure rate của Circuit Breaker. | Bỏ qua khác biệt giữa exception thực tế và predicate ghi nhận. | Đối chiếu counter ứng dụng với metrics Resilience4j. |
| Gộp cache và unavailable thành cùng một kết quả. | Không biết fallback có dữ liệu thay thế hay không. | Gắn mode hữu hạn cho fallback response. |
| Đưa ID hoặc exception message vào metric tag. | Cardinality tăng mạnh và có thể làm lộ dữ liệu. | Dùng nhóm nguyên nhân có giới hạn; chi tiết đặt trong log/trace. |
| Chỉ xem tỷ lệ mà không xem số lượng. | Một vài request có thể tạo tỷ lệ cao gây báo động giả. | Hiển thị volume và đặt điều kiện số mẫu tối thiểu. |

Đo fallback đúng cách giúp phân biệt ba trạng thái: dependency đang phục vụ bình thường, ứng dụng đang trả kết quả suy giảm để duy trì trải nghiệm, và chính đường fallback cũng gặp sự cố. Khi theo dõi fallback song song với primary attempts, Circuit Breaker metrics và trạng thái dữ liệu thay thế, dashboard phản ánh được sức khỏe thật của dependency thay vì chỉ phản ánh response cuối cùng mà người dùng nhìn thấy.
