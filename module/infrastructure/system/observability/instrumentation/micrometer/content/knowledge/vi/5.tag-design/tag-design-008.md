# Lựa chọn tag có thể biết từ đầu và tag chỉ có khi thao tác kết thúc

Khi đo lường một thao tác trong ứng dụng, có những thông tin đã biết ngay lúc bắt đầu và có những thông tin chỉ xác định được sau khi thao tác hoàn tất. Ví dụ, ứng dụng biết thao tác là tạo đơn hàng và kênh nhận đơn ngay khi nhận request; kết quả thành công, thất bại hay timeout chỉ có thể biết sau khi xử lý.

Micrometer dùng tags để phân loại meter. Một meter đã đăng ký có danh tính gồm tên và tập tags; các tags đó không thay đổi theo từng lần ghi nhận. Vì vậy, thời điểm chọn meter cần phù hợp với thời điểm có đủ thông tin để xác định tags. Với Timer, mẫu đo Timer.Sample cho phép bắt đầu đo trước, rồi chọn Timer có tags hoàn chỉnh khi thao tác kết thúc.

## 1. Hai nhóm thông tin theo thời điểm có thể xác định

### Tag có thể biết từ đầu

Đây là thông tin đã có trước khi phần việc cần đo bắt đầu hoặc ngay tại ranh giới bắt đầu. Ví dụ:

- operation: tên thao tác như create, cancel hoặc refund.
- channel: kênh nhận yêu cầu như web, mobile hoặc partner.
- method: phương thức HTTP như GET hoặc POST.
- route: route template như /orders/{id}.
- region hoặc environment: ngữ cảnh triển khai đã được cấu hình.

Những thông tin này thường được dùng để chọn meter ngay từ đầu. Nếu tất cả tags cần thiết đều đã có, có thể lấy Timer hoặc Counter từ registry và ghi nhận trực tiếp.

### Tag chỉ biết khi thao tác kết thúc

Đây là thông tin phụ thuộc vào kết quả thực thi. Ví dụ:

- result: success, failure, timeout hoặc conflict.
- status: nhóm mã phản hồi HTTP như 2xx, 4xx hoặc 5xx.
- cache_result: hit hoặc miss, nếu kết quả tra cache chỉ được xác định sau khi gọi cache.
- retry_outcome: thành công sau retry hoặc hết số lần retry.
- error_category: nhóm lỗi đã được chuẩn hóa như validation, dependency hoặc unexpected.

Những tags này chỉ có thể được chọn khi ứng dụng đã có kết quả tương ứng. Với Timer, nên bắt đầu bằng Timer.Sample và đăng ký/chọn Timer cuối cùng khi đã xác định outcome.

| Nhóm | Ví dụ | Thời điểm có giá trị | Cách chọn meter |
| --- | --- | --- | --- |
| Tag biết từ đầu | operation, channel, method, route | Trước hoặc tại lúc bắt đầu | Có thể lấy meter trước khi chạy thao tác |
| Tag biết khi kết thúc | result, status, error_category | Sau khi thao tác hoàn tất hoặc thất bại | Chọn meter có tags cuối cùng khi ghi nhận kết quả |

Lưu ý: thông tin có sẵn không đồng nghĩa với việc nên đưa vào tag. Request ID, user ID, mã đơn hàng và URL thô có thể biết ngay từ đầu nhưng thường có cardinality quá cao để dùng làm tags của metrics.

## 2. Tags là một phần của định danh meter

Tên meter mô tả đại lượng được đo; tags xác định các chiều phân nhóm của đại lượng đó. Ví dụ, orders.create.duration là thời gian xử lý thao tác tạo đơn. Nếu meter có tags operation=create và channel=web, nó đại diện cho thời gian tạo đơn qua kênh web.

Khi cùng một registry đăng ký meter với cùng tên và cùng tags, Micrometer có thể dùng lại meter đã tồn tại. Nếu tags khác nhau, đó là một meter identity khác và thường tạo ra một chuỗi thời gian riêng khi xuất dữ liệu.

Tags không phải thuộc tính có thể sửa sau khi meter đã được đăng ký. Không thể lấy Timer đã đăng ký với channel=web rồi thêm result=success vào chính Timer đó sau khi thao tác kết thúc. Muốn phân nhóm theo outcome, cần chọn hoặc đăng ký meter có tags phù hợp với outcome.

Có thể hình dung các chuỗi thời gian sau:

~~~text
orders.create.duration{operation="create", channel="web", result="success"}
orders.create.duration{operation="create", channel="web", result="failure"}
orders.create.duration{operation="create", channel="mobile", result="success"}
~~~

Chúng cùng đo thời gian tạo đơn, nhưng phân biệt theo kênh và kết quả. Tập tags cần nhất quán giữa các nhánh để backend có thể truy vấn và so sánh.

## 3. Khi mọi tags đều biết từ đầu: dùng Timer trực tiếp

Nếu chỉ cần đo thời gian theo operation và channel, hai tags này đã có trước khi gọi nghiệp vụ. Có thể đăng ký Timer rồi ghi nhận toàn bộ thao tác:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.Timer;

public class OrderMetrics {

    private final MeterRegistry registry;

    public OrderMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordCreate(String channel, Runnable operation) {
        Tags tags = Tags.of(
            "operation", "create",
            "channel", normalizeChannel(channel)
        );

        Timer timer = registry.timer("orders.operation.duration", tags);
        timer.record(operation);
    }

    private String normalizeChannel(String channel) {
        if (channel == null) {
            return "unknown";
        }

        return switch (channel.trim().toLowerCase(java.util.Locale.ROOT)) {
            case "web" -> "web";
            case "mobile" -> "mobile";
            case "partner" -> "partner";
            default -> "other";
        };
    }
}
~~~

Trong ví dụ, Timer được chọn trước khi Runnable chạy vì operation và channel đã được biết. Timer tự ghi nhận thời gian và số lần thực hiện. Cách này gọn và phù hợp khi không cần thêm chiều phân loại phụ thuộc vào kết quả.

Nếu muốn phân biệt success và failure, không nên cố sửa tags của Timer đã lấy ở đầu thao tác. Hãy dùng Timer.Sample để chờ đến lúc outcome được xác định.

## 4. Khi có tag chỉ biết sau: dùng Timer.Sample

Timer.Sample tách thời điểm bắt đầu đo khỏi thời điểm chọn Timer để ghi kết quả. Khi bắt đầu, sample lưu mốc thời gian. Khi kết thúc, gọi sample.stop(timer) với Timer có tên và tags hoàn chỉnh. Thời gian trôi qua được ghi vào Timer được truyền cho stop.

Luồng xử lý:

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant Sample as Timer.Sample
    participant Registry as MeterRegistry
    participant Timer as Timer cuối cùng

    App->>Registry: Xác định tags đã biết từ đầu
    App->>Sample: Timer.start(registry)
    Note over App,Sample: Thực hiện thao tác nghiệp vụ
    App->>App: Xác định result
    App->>Registry: timer(name, tags + result)
    Registry-->>App: Timer có tags hoàn chỉnh
    App->>Sample: stop(Timer)
    Sample->>Timer: Ghi thời gian đã trôi qua
~~~

Ví dụ, operation và channel được biết trước, còn result được xác định sau khi lưu đơn hàng:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final MeterRegistry registry;
    private final OrderRepository orderRepository;

    public OrderService(
        MeterRegistry registry,
        OrderRepository orderRepository
    ) {
        this.registry = registry;
        this.orderRepository = orderRepository;
    }

    public Order create(CreateOrderCommand command) {
        Tags knownTags = Tags.of(
            "operation", "create",
            "channel", normalizeChannel(command.channel())
        );

        Timer.Sample sample = Timer.start(registry);

        try {
            Order order = orderRepository.save(Order.from(command));
            recordCompletion(sample, knownTags, "success");
            return order;
        } catch (DuplicateOrderException ex) {
            recordCompletion(sample, knownTags, "conflict");
            throw ex;
        } catch (RuntimeException ex) {
            recordCompletion(sample, knownTags, "failure");
            throw ex;
        }
    }

    private void recordCompletion(
        Timer.Sample sample,
        Tags knownTags,
        String result
    ) {
        Tags completedTags = knownTags.and("result", result);

        Timer timer = registry.timer(
            "orders.operation.duration",
            completedTags
        );
        sample.stop(timer);

        registry.counter(
            "orders.operation.total",
            completedTags
        ).increment();
    }

    private String normalizeChannel(String channel) {
        if (channel == null) {
            return "unknown";
        }

        return switch (channel.trim().toLowerCase(java.util.Locale.ROOT)) {
            case "web" -> "web";
            case "mobile" -> "mobile";
            case "partner" -> "partner";
            default -> "other";
        };
    }
}
~~~

Trong ví dụ:

1. knownTags chứa operation và channel vì hai giá trị đã có khi bắt đầu.
2. Timer.Sample bắt đầu đo trước khi gọi repository.
3. Khi thao tác kết thúc, nhánh xử lý xác định result là success, conflict hoặc failure.
4. recordCompletion kết hợp tags ban đầu với result, chọn Timer tương ứng và dừng sample.
5. Counter được tăng với cùng tập tags để đếm số thao tác hoàn tất theo kết quả.

Các exception cụ thể cần được điều chỉnh theo quy tắc nghiệp vụ của ứng dụng. Chỉ phân loại những nhóm lỗi có ý nghĩa vận hành và có tập giá trị hữu hạn. Ví dụ trên bắt các RuntimeException dự kiến để ghi nhận failure rồi ném lại exception cho luồng xử lý hiện tại; không nuốt lỗi để đổi lấy metrics.

## 5. Vì sao Timer.Sample phù hợp với outcome tag?

Timer.record(...) phù hợp khi meter đã được chọn trước lúc thực thi. Nó nhận một Runnable, Supplier hoặc Callable tùy overload và tự ghi thời gian vào Timer đó.

Khi outcome chỉ biết sau khi chạy, Timer.Sample giúp giữ thời gian bắt đầu mà chưa buộc ứng dụng phải chọn một meter cụ thể. Sau khi có kết quả, ứng dụng tạo hoặc lấy Timer với tags cuối cùng rồi gọi stop.

| Tiêu chí | Timer.record(...) | Timer.Sample |
| --- | --- | --- |
| Chọn Timer | Trước khi thực thi | Có thể chọn sau khi thực thi |
| Tag phụ thuộc kết quả | Không thuận tiện nếu chưa biết outcome | Phù hợp |
| Mã nguồn | Ngắn gọn | Cần quản lý các nhánh kết thúc |
| Trường hợp phù hợp | Đo thời gian với tags đã biết | Đo thời gian và phân loại theo kết quả cuối |

Timer.Sample không tự suy ra result, không lưu tags để tự thêm sau này và cũng không tự ghi metric khi sample bị bỏ quên. Ứng dụng phải gọi stop đúng một lần với Timer mong muốn.

## 6. Counter và các meter khác khi tag chỉ biết lúc kết thúc

Counter không đo khoảng thời gian. Nếu cần đếm số thao tác theo kết quả, chỉ cần đợi đến lúc outcome được xác định rồi chọn Counter có tags phù hợp:

~~~java
Tags completedTags = knownTags.and("result", result);

registry.counter(
    "orders.operation.total",
    completedTags
).increment();
~~~

Không cần tạo Counter lúc bắt đầu rồi tìm cách thay đổi tags sau đó. Counter được chọn ở thời điểm hoàn tất sẽ thuộc đúng nhóm outcome.

Với DistributionSummary, nếu giá trị cần ghi nhận và tags đều chỉ có sau khi thao tác hoàn tất, có thể chọn DistributionSummary ở thời điểm đó rồi gọi record(value). Với Gauge, cần thiết kế theo trạng thái được quan sát; Gauge thường phản ánh giá trị hiện tại tại thời điểm scrape, nên không nên dùng nó để biểu diễn một outcome đã xảy ra trong quá khứ.

## 7. Chọn nhóm outcome có giới hạn

Outcome nên là một tập giá trị ngắn, có ý nghĩa và ổn định. Ví dụ:

| Tình huống | Value đề xuất | Ghi chú |
| --- | --- | --- |
| Hoàn tất bình thường | success | Thao tác nghiệp vụ hoàn tất |
| Dữ liệu không hợp lệ | validation | Lỗi đầu vào có thể phân loại |
| Xung đột nghiệp vụ | conflict | Ví dụ đơn hàng đã tồn tại |
| Hệ thống phụ trợ lỗi | dependency | Lỗi từ database hoặc dịch vụ phụ trợ |
| Hết thời gian chờ | timeout | Thao tác vượt quá thời gian cho phép |
| Lỗi không phân loại được | unexpected | Nhóm dự phòng có kiểm soát |

Không dùng exception message làm tag value vì message có thể chứa ID, dữ liệu đầu vào hoặc nội dung thay đổi theo từng request. Tên class exception cũng cần được cân nhắc: nếu ứng dụng có nhiều lớp exception động hoặc do plugin cung cấp, hãy ánh xạ chúng về một tập category hữu hạn.

Đối với HTTP, thường nên gom status code thành nhóm 2xx, 4xx và 5xx nếu mục tiêu chỉ là theo dõi xu hướng. Chỉ dùng status code chi tiết khi có câu hỏi vận hành rõ ràng và số lượng giá trị vẫn được kiểm soát.

## 8. Xử lý thao tác bất đồng bộ

Với thao tác bất đồng bộ, thời gian đo thường kéo dài từ lúc gửi công việc đến lúc nhận kết quả. Có thể tạo Timer.Sample trước khi bắt đầu và dừng sample trong callback hoàn tất:

~~~java
Timer.Sample sample = Timer.start(registry);
Tags knownTags = Tags.of(
    "operation", "submit",
    "channel", "partner"
);

return partnerClient.submitAsync(command)
    .whenComplete((response, error) -> {
        String result = error == null ? "success" : "failure";
        Tags completedTags = knownTags.and("result", result);

        sample.stop(
            registry.timer("partner.submit.duration", completedTags)
        );
        registry.counter(
            "partner.submit.total", completedTags
        ).increment();
    });
~~~

Ví dụ này minh họa cách đo đến thời điểm future hoàn tất. Trong ứng dụng thực tế, cần xác định rõ timeout, cancellation và exception được bọc trong CompletionException sẽ được phân loại ra sao. Callback hoàn tất chỉ nên ghi nhận một lần; không dừng sample đồng thời ở callback timeout và callback hoàn tất thông thường.

Nếu cần phân biệt timeout với failure, hãy chuẩn hóa error thành các outcome như success, timeout và failure trước khi tạo tags. Không đưa nội dung exception vào metrics.

## 9. Tránh các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chọn Timer trước khi biết result rồi mong thay đổi tags sau | Meter vẫn giữ tập tags ban đầu | Dùng Timer.Sample và chọn Timer ở thời điểm kết thúc |
| Đăng ký meter với request ID hoặc order ID | Tạo cardinality rất cao | Đưa ID vào trace/log; dùng tags tổng hợp |
| Mỗi nhánh dùng key khác nhau như result, status, outcome | Khó truy vấn và so sánh | Thống nhất một key cho cùng khái niệm |
| Một nhánh quên gọi sample.stop | Thiếu quan sát thời gian của nhánh đó | Gom thao tác ghi nhận vào helper hoặc cấu trúc kết thúc chung |
| Gọi sample.stop hai lần | Ghi nhận trùng hoặc tạo số liệu sai | Bảo đảm chỉ có một đường kết thúc chịu trách nhiệm dừng sample |
| Ghi nhận success trước khi thao tác thật sự hoàn tất | Metrics phản ánh sai kết quả | Chỉ ghi outcome sau khi đã xác định trạng thái cuối |
| Nuốt exception để ghi metrics | Thay đổi hành vi nghiệp vụ và che giấu lỗi | Ghi metrics rồi ném lại lỗi hoặc để cơ chế xử lý lỗi hiện có tiếp tục |

Một lưu ý quan trọng: tags được chọn ở thời điểm kết thúc không nên làm cho ứng dụng giữ lại toàn bộ request hoặc response lớn chỉ để ghi metrics. Chỉ giữ các giá trị nhỏ, đã chuẩn hóa cần thiết cho việc phân loại.

## 10. Kiểm thử cách chọn tags

Có thể dùng SimpleMeterRegistry để xác nhận sample được ghi vào meter có outcome tag mong muốn:

~~~java
import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

SimpleMeterRegistry registry = new SimpleMeterRegistry();
Tags knownTags = Tags.of(
    "operation", "create",
    "channel", "web"
);

Timer.Sample sample = Timer.start(registry);
Tags successTags = knownTags.and("result", "success");
sample.stop(
    registry.timer("orders.operation.duration", successTags)
);

Timer successTimer = registry.find("orders.operation.duration")
    .tags("operation", "create", "channel", "web", "result", "success")
    .timer();

assertThat(successTimer).isNotNull();
assertThat(successTimer.count()).isEqualTo(1L);
~~~

Các kiểm thử nên xác minh:

- Tags biết từ đầu được giữ nguyên qua mọi nhánh kết thúc.
- Mỗi outcome hợp lệ tạo đúng tập tags và meter tương ứng.
- Nhánh success, conflict, timeout và failure được phân loại nhất quán.
- Timer.Sample được dừng đúng một lần trên mỗi lần thực hiện.
- Counter chỉ tăng sau khi kết quả đã được xác định.
- Các tag value đều nằm trong danh sách hữu hạn đã thiết kế.
- Không có request ID, mã đơn hàng hoặc exception message trong tags.

Kiểm thử SimpleMeterRegistry xác minh logic instrumentation trong ứng dụng. Để kiểm tra cách tên/tag được chuyển đổi và dữ liệu được backend nhận, cần kiểm tra thêm endpoint export hoặc registry thực tế.

## 11. Quy trình quyết định tag nào được chọn lúc nào

Khi thiết kế một meter cho thao tác nghiệp vụ, hãy đi theo trình tự:

1. Xác định đại lượng cần đo: số lần, thời gian, trạng thái hiện tại hay phân phối giá trị.
2. Liệt kê các chiều phân loại cần cho truy vấn.
3. Với mỗi chiều, xác định giá trị đã có ở thời điểm bắt đầu hay chỉ có sau khi xử lý.
4. Kiểm tra cardinality và chuẩn hóa value trước khi dùng làm tag.
5. Nếu mọi tags đều biết trước, chọn meter trực tiếp và dùng record/increment phù hợp.
6. Nếu Timer cần tag outcome chỉ biết sau, bắt đầu Timer.Sample rồi chọn Timer cuối cùng ở nhánh hoàn tất.
7. Nếu Counter cần tag outcome, chỉ chọn và tăng Counter sau khi đã biết outcome.
8. Kiểm thử tất cả nhánh kết thúc, bao gồm lỗi, timeout và cancellation nếu có.

Việc phân biệt tags biết từ đầu với tags chỉ biết khi kết thúc giúp instrumentation phản ánh đúng vòng đời thao tác. Dùng meter trực tiếp cho các chiều đã có sẵn; dùng Timer.Sample khi cần đo từ đầu đến cuối nhưng chỉ có thể chọn đầy đủ tags ở cuối. Trong cả hai trường hợp, giữ tập tag value hữu hạn và nhất quán để metrics có thể truy vấn, so sánh và vận hành lâu dài.
