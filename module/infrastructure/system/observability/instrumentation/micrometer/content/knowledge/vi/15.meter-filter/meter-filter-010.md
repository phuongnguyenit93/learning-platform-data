# Đăng ký bộ lọc trước meter và kiểm tra chính sách bằng trường hợp đối chứng

MeterFilter cho phép áp dụng chính sách chung lên các meter trước khi chúng được đăng ký vào MeterRegistry. Có thể dùng filter để từ chối một nhóm metric, giới hạn số giá trị tag, chuẩn hóa tên hoặc tag, và điều chỉnh cấu hình phân phối. Tuy nhiên, filter chỉ phát huy tác dụng đúng như mong đợi khi được gắn vào registry trước lúc meter cần kiểm soát được tạo ra.

Khi kiểm tra một chính sách MeterFilter, không nên chỉ chứng minh rằng meter bị chặn không xuất hiện. Cần có cả trường hợp đối chứng: một meter nằm ngoài phạm vi filter phải được đăng ký bình thường. Nếu không có trường hợp đối chứng, một cấu hình vô tình từ chối tất cả meter vẫn có thể làm test vượt qua.

Trong module **OBSERVABILITY_INSTRUMENTATION_MICROMETER**, MeterFilter là cơ chế quan trọng để kiểm soát instrumentation và cardinality. Bài này trình bày thời điểm đăng ký filter, cách Spring Boot cấu hình filter sớm, ngữ nghĩa filter chain và cách viết kiểm thử gồm cả trường hợp bị từ chối lẫn trường hợp được phép.

## 1. MeterFilter tác động ở thời điểm đăng ký meter

Micrometer nhận diện một meter bằng Meter.Id, gồm tên, tag và một số metadata khác. Khi ứng dụng đăng ký Counter, Gauge, Timer hoặc DistributionSummary, registry áp dụng các MeterFilter đã cấu hình lên ID và cấu hình phân phối của meter đó.

Một filter có thể thực hiện các việc như:

- Từ chối meter theo tên hoặc theo điều kiện.
- Chấp nhận hoặc tiếp tục đánh giá meter.
- Đổi tên meter hoặc biến đổi tag.
- Giới hạn số lượng giá trị tag khác nhau.
- Điều chỉnh histogram, percentile hoặc cấu hình thống kê phân phối.

Filter không phải bộ lọc truy vấn dashboard. Nó chạy trong ứng dụng ở thời điểm meter được đăng ký vào registry, trước khi registry xuất dữ liệu đến Prometheus, OTLP hoặc backend khác.

Ví dụ, một dịch vụ muốn bỏ qua các meter debug và giới hạn số route được ghi nhận cho metric HTTP. Chính sách có thể được diễn đạt như sau:

1. Metric có tên bắt đầu bằng debug. bị từ chối.
2. Metric api.requests chỉ được có tối đa hai giá trị route khác nhau.
3. Metric orders.created không thuộc hai quy tắc trên nên vẫn được đăng ký.

Quy tắc thứ ba là trường hợp đối chứng. Nó xác nhận filter chỉ tác động đến phạm vi đã định và registry vẫn tiếp tục nhận các meter bình thường.

## 2. Vì sao phải đăng ký filter trước khi tạo meter?

MeterFilter được áp dụng khi meter được đăng ký. Vì vậy, hãy cấu hình filter trước các lệnh như registry.counter(...), Counter.builder(...).register(registry), Timer.builder(...).register(registry) hoặc các binder tạo meter.

Nếu meter đã được đăng ký trước, việc thêm một filter mới không tự động quét lại registry, xóa meter cũ hay biến đổi các ID đã tồn tại. Filter mới được dùng cho những lần đăng ký meter tiếp theo.

Ví dụ thứ tự không phù hợp:

~~~java
Counter requests = registry.counter("api.requests");

// Filter được thêm sau khi meter đã tồn tại.
registry.config().meterFilter(MeterFilter.denyNameStartsWith("api."));
~~~

Counter api.requests đã được tạo trước khi filter được thêm. Không nên kỳ vọng filter mới tự động xóa Counter này khỏi registry.

Thứ tự phù hợp:

~~~java
registry.config()
        .meterFilter(MeterFilter.denyNameStartsWith("debug."))
        .meterFilter(MeterFilter.maximumAllowableTags(
                "api.requests", "route", 100, MeterFilter.deny()
        ));

// Chỉ đăng ký meter sau khi chính sách đã được gắn vào registry.
Counter requests = registry.counter("api.requests", "route", "/orders");
~~~

Trong production, cần bảo đảm filter được cài trước khi component nghiệp vụ hoặc binder bắt đầu đăng ký meter. Đừng dựa vào một phương thức chạy muộn như @PostConstruct của component tùy ý nếu registry đã được các bean khác sử dụng.

## 3. Đăng ký MeterFilter trong Spring Boot

Với Spring Boot Actuator, cách phổ biến là khai báo MeterRegistryCustomizer dưới dạng bean. Spring Boot áp dụng customizer khi cấu hình registry, trước khi các binder được dùng để đăng ký meter.

Ví dụ:

~~~java
import io.micrometer.core.instrument.MeterFilter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.actuate.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MetricsPolicyConfiguration {

    @Bean
    MeterRegistryCustomizer<MeterRegistry> metricsPolicy() {
        return registry -> registry.config()
                .meterFilter(MeterFilter.denyNameStartsWith("debug."))
                .meterFilter(MeterFilter.maximumAllowableTags(
                        "api.requests",
                        "route",
                        100,
                        MeterFilter.deny()
                ));
    }
}
~~~

Chính sách trên có hai phần:

- denyNameStartsWith("debug.") từ chối meter có tên bắt đầu bằng debug.
- maximumAllowableTags(...) giới hạn tối đa 100 giá trị khác nhau của tag route đối với các meter có tên bắt đầu bằng api.requests. Khi vượt giới hạn, MeterFilter.deny() từ chối meter có giá trị route mới.

Nếu ứng dụng có nhiều MeterRegistryCustomizer hoặc nhiều nơi đăng ký filter, hãy quản lý thứ tự rõ ràng và kiểm thử cấu hình cuối cùng. Có thể dùng thứ tự bean của Spring khi chính sách phụ thuộc thứ tự áp dụng. Tránh chia cùng một chính sách thành nhiều cấu hình rải rác khiến khó biết filter nào được thực thi trước.

Với ứng dụng Micrometer thuần không dùng Spring Boot, đăng ký filter trực tiếp trên registry ngay sau khi tạo registry và trước khi đăng ký meter:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();

registry.config()
        .meterFilter(MeterFilter.denyNameStartsWith("debug."))
        .meterFilter(MeterFilter.maximumAllowableTags(
                "api.requests", "route", 100, MeterFilter.deny()
        ));

// Sau điểm này mới đăng ký meter.
~~~

Không tạo một registry khác chỉ để gắn filter nếu các meter nghiệp vụ đang dùng registry ban đầu. Filter phải được gắn vào chính registry mà ứng dụng dùng để đăng ký và xuất meter.

## 4. Hiểu phản hồi của filter chain

MeterFilter có thể đưa ra một trong ba kết quả qua MeterFilterReply:

| Kết quả | Ý nghĩa | Hành vi |
|---|---|---|
| NEUTRAL | Filter hiện tại không quyết định | Tiếp tục đánh giá filter tiếp theo |
| ACCEPT | Chấp nhận meter | Kết thúc quá trình quyết định và chấp nhận meter |
| DENY | Từ chối meter | Kết thúc quá trình quyết định và không đăng ký meter |

Một filter có thể trả về NEUTRAL để cho các filter tiếp theo tiếp tục kiểm tra. ACCEPT và DENY là các quyết định kết thúc. Vì vậy, thứ tự filter có ý nghĩa: một filter chấp nhận sớm có thể khiến các filter phía sau không còn cơ hội từ chối meter.

Các factory method thường dùng:

~~~java
MeterFilter.deny()
MeterFilter.accept()
MeterFilter.neutral()
MeterFilter.denyNameStartsWith("debug.")
MeterFilter.acceptNameStartsWith("business.")
~~~

Chỉ dùng acceptNameStartsWith khi thực sự muốn chấp nhận ngay nhóm meter đó và hiểu rằng các filter phía sau có thể bị bỏ qua. Nếu mục tiêu là cho meter tiếp tục qua các chính sách giới hạn tag, đừng dùng ACCEPT quá sớm; hãy để filter trả NEUTRAL khi chưa có quyết định cuối.

## 5. Chặn meter theo tên

Có thể từ chối một nhóm meter theo tiền tố tên:

~~~java
registry.config()
        .meterFilter(MeterFilter.denyNameStartsWith("debug."));
~~~

Sau cấu hình này, các meter như debug.cache.refresh hoặc debug.internal.calls bị từ chối khi đăng ký. Các meter khác như orders.created vẫn được phép.

Đây là cách đơn giản để bỏ các metric tạm thời hoặc metric nội bộ không cần xuất trong môi trường production. Cần chọn tiền tố đủ cụ thể để không vô tình chặn metric nghiệp vụ hợp lệ.

Nếu muốn kiểm soát tên cụ thể hoặc kết hợp điều kiện phức tạp, có thể tạo MeterFilter tùy chỉnh và đánh giá Meter.Id:

~~~java
MeterFilter denyTemporaryMetrics = new MeterFilter() {
    @Override
    public MeterFilterReply accept(Meter.Id id) {
        if (id.getName().startsWith("temporary.")) {
            return MeterFilterReply.DENY;
        }
        return MeterFilterReply.NEUTRAL;
    }
};
~~~

Dùng factory method cho quy tắc đơn giản; dùng filter tùy chỉnh khi cần nhiều điều kiện hoặc logic có thể kiểm thử riêng.

## 6. Giới hạn cardinality bằng maximumAllowableTags

Một nguyên nhân phổ biến làm metrics tăng quá nhanh là tag có quá nhiều giá trị. Ví dụ, tag route nhận giá trị URL thô như /orders/1001, /orders/1002, /orders/1003. Mỗi URL khác nhau có thể tạo một meter ID và một time series mới.

Có thể đặt giới hạn số giá trị khác nhau cho một tag:

~~~java
MeterFilter.maximumAllowableTags(
        "api.requests",
        "route",
        100,
        MeterFilter.deny()
)
~~~

Các tham số gồm:

- Tiền tố tên meter cần áp dụng chính sách.
- Khóa tag cần giới hạn.
- Số giá trị tag tối đa được chấp nhận.
- Filter sẽ được áp dụng khi số giá trị mới vượt giới hạn.

Ví dụ trên cho phép tối đa 100 giá trị route khác nhau đối với nhóm meter api.requests. Khi một giá trị route mới làm vượt ngưỡng, MeterFilter.deny() từ chối meter tương ứng.

Giới hạn này là hàng rào bảo vệ cardinality. Nó không thay thế việc chuẩn hóa route. Nên chuyển URL động thành route template như /orders/{id} trước khi ghi metric. Nếu chỉ dựa vào giới hạn, những route xuất hiện trước có thể chiếm hết quota; route quan trọng xuất hiện sau có thể bị từ chối. Khi đăng ký đồng thời, tập giá trị nào được chấp nhận cũng có thể phụ thuộc thứ tự đăng ký.

Không dùng userId, orderId, requestId, email hoặc URL chứa định danh làm tag. MeterFilter có thể hạn chế thiệt hại, nhưng tag có cardinality cao vẫn là thiết kế instrumentation không tốt.

## 7. Kiểm tra chính sách bằng trường hợp bị chặn và trường hợp đối chứng

Một kiểm thử chính sách tốt phải chứng minh ít nhất hai điều:

1. Meter nằm trong phạm vi bị chặn thực sự không được đăng ký.
2. Meter hợp lệ nằm ngoài phạm vi filter vẫn được đăng ký bình thường.

Với giới hạn tag, cần kiểm tra cả hai giá trị đầu tiên được phép và giá trị vượt ngưỡng bị từ chối.

Ví dụ dùng SimpleMeterRegistry:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.MeterFilter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class MeterFilterPolicyTest {

    @Test
    void appliesDenyAndTagLimitWithoutBlockingControlMeters() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        registry.config()
                .meterFilter(MeterFilter.denyNameStartsWith("debug."))
                .meterFilter(MeterFilter.maximumAllowableTags(
                        "api.requests",
                        "route",
                        2,
                        MeterFilter.deny()
                ));

        // Trường hợp bị chặn theo tên.
        registry.counter("debug.internal.calls").increment();

        // Hai route đầu tiên nằm trong giới hạn.
        registry.counter("api.requests", "route", "/orders").increment();
        registry.counter("api.requests", "route", "/payments").increment();

        // Route thứ ba vượt giới hạn và bị từ chối.
        registry.counter("api.requests", "route", "/customers").increment();

        // Trường hợp đối chứng: metric không thuộc chính sách deny vẫn được đăng ký.
        registry.counter("orders.created").increment();

        // Trường hợp đối chứng cho tag cap: tên metric khác vẫn được phép.
        registry.counter("billing.requests", "route", "/customers").increment();

        assertThat(registry.find("debug.internal.calls").counter()).isNull();

        assertThat(registry.find("api.requests")
                .tag("route", "/orders").counter()).isNotNull();
        assertThat(registry.find("api.requests")
                .tag("route", "/payments").counter()).isNotNull();
        assertThat(registry.find("api.requests")
                .tag("route", "/customers").counter()).isNull();

        assertThat(registry.find("orders.created").counter()).isNotNull();
        assertThat(registry.find("billing.requests")
                .tag("route", "/customers").counter()).isNotNull();

        registry.close();
    }
}
~~~

Kiểm thử này có các trường hợp rõ ràng:

| Meter | Kỳ vọng | Lý do |
|---|---|---|
| debug.internal.calls | Bị từ chối | Tên bắt đầu bằng debug. |
| api.requests route=/orders | Được đăng ký | Giá trị route thứ nhất |
| api.requests route=/payments | Được đăng ký | Giá trị route thứ hai |
| api.requests route=/customers | Bị từ chối | Vượt giới hạn hai giá trị route |
| orders.created | Được đăng ký | Không thuộc tiền tố bị chặn hoặc giới hạn tag |
| billing.requests route=/customers | Được đăng ký | Tag cap chỉ áp dụng cho api.requests |

Trường hợp đối chứng giúp phát hiện lỗi cấu hình quá rộng. Ví dụ, nếu vô tình dùng MeterFilter.deny() như filter toàn cục, test chỉ kiểm tra debug bị chặn vẫn có thể xanh; assertion orders.created được giữ lại sẽ làm lộ lỗi đó.

Dùng registry mới trong mỗi test để các meter đã đăng ký ở test khác không ảnh hưởng kết quả. Thứ tự đăng ký các giá trị route trong test cần cố định để kết quả kiểm tra giới hạn có thể lặp lại.

## 8. Kiểm tra filter đã được gắn đủ sớm trong Spring Boot

Unit test với SimpleMeterRegistry xác minh chính sách MeterFilter. Nhưng nó chưa chứng minh ứng dụng Spring Boot thực tế đã áp dụng customizer trước khi các binder hoặc component đăng ký meter.

Có thể bổ sung một kiểm thử context Spring Boot:

- Khởi động context với bean MeterRegistryCustomizer chứa chính sách.
- Lấy MeterRegistry được Spring Boot cấu hình.
- Xác nhận meter bị chặn không có trong registry.
- Xác nhận một meter đối chứng vẫn tồn tại.
- Xác nhận meter do binder tạo ra vẫn hoạt động nếu chính sách không nhắm đến nó.

Nếu component tự đăng ký meter trong constructor, hãy bảo đảm test tạo context đúng thứ tự như production. Một customizer được cấu hình đúng trong unit test nhưng không được Spring Boot phát hiện do thiếu bean hoặc profile sai vẫn có thể khiến production không có filter.

Cũng cần kiểm tra endpoint export thực tế. Với Prometheus, gọi /actuator/prometheus và xác nhận metric bị từ chối không xuất hiện trong khi metric đối chứng có mặt. Với OTLP, có thể kiểm tra dữ liệu nhận tại Collector hoặc backend. Đừng chỉ kiểm tra dashboard vì truy vấn, bộ lọc và time range có thể che giấu cả metric được xuất lẫn metric bị chặn.

## 9. Những lỗi thường gặp khi đăng ký MeterFilter

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Thêm filter sau khi meter đã đăng ký | Meter cũ không tự bị lọc lại | Đăng ký filter trước binder và component |
| Dùng ACCEPT quá sớm | Filter phía sau có thể không được đánh giá | Dùng NEUTRAL nếu muốn tiếp tục filter chain |
| Chỉ test meter bị chặn | Có thể không phát hiện filter chặn nhầm mọi meter | Thêm trường hợp đối chứng được phép |
| Dùng maximumAllowableTags thay cho route normalization | Route quan trọng có thể bị từ chối khi hết quota | Chuẩn hóa URL thành route template |
| Dùng cap toàn cục quá thấp | Meter hợp lệ mới có thể bị từ chối | Chọn prefix, tag key và ngưỡng theo tải thực tế |
| Dùng registry dùng chung giữa các test | Meter cũ làm sai kết quả kiểm tra | Tạo registry mới cho từng test |
| Chỉ xem dashboard | Query có thể che giấu metric | Kiểm tra registry và endpoint export trực tiếp |

## 10. Checklist trước khi đưa MeterFilter vào production

Trước khi triển khai chính sách, hãy xác nhận:

- Filter được đăng ký trên đúng MeterRegistry mà ứng dụng sử dụng.
- Filter được cài trước khi component và binder đăng ký meter.
- Phạm vi tên meter và tag key đủ cụ thể.
- Thứ tự filter chain không làm ACCEPT bỏ qua chính sách cần thiết.
- Có kiểm thử meter bị từ chối và meter đối chứng được phép.
- Có kiểm thử giới hạn tag ở cả phía dưới và phía trên ngưỡng.
- Route hoặc giá trị tag động đã được chuẩn hóa trước khi đăng ký meter.
- Đã đánh giá tác động khi meter bị từ chối: số liệu bị thiếu có được phát hiện và giải thích không?
- Đã kiểm tra endpoint export hoặc dữ liệu backend trong môi trường tích hợp.

MeterFilter là một điểm thực thi chính sách ở tầng instrumentation. Đăng ký filter sớm giúp các meter tuân theo cùng quy tắc ngay từ lúc được tạo; kiểm thử bằng cả trường hợp bị chặn và trường hợp đối chứng xác nhận chính sách vừa có hiệu lực vừa không ảnh hưởng ngoài phạm vi. Kết hợp giới hạn tag với chuẩn hóa dữ liệu đầu vào sẽ giúp metrics giữ cardinality trong tầm kiểm soát mà vẫn bảo toàn những số đo vận hành cần thiết.
