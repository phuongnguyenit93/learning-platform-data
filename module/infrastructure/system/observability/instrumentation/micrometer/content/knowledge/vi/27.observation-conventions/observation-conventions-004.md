# ObservationConvention để tách quy ước khỏi mã thực thi thao tác

Micrometer Observation cung cấp một vòng đời chung để ứng dụng quan sát thao tác: tạo Observation, bắt đầu, mở scope, ghi nhận lỗi hoặc sự kiện, rồi kết thúc. Mã nghiệp vụ cần biết thao tác nào đang chạy và dữ liệu ngữ cảnh nào liên quan. Tuy nhiên, mã nghiệp vụ không nên phải quyết định tên metric, tên span hay cách đặt mọi tag cho từng backend.

ObservationConvention giải quyết phần cấu hình đó. Nó nhận một Observation.Context và chuyển dữ liệu ngữ cảnh thành tên Observation cùng các key-value có cardinality thấp hoặc cao. Nhờ vậy, instrumentation chỉ mô tả vòng đời thao tác và cung cấp context; quy ước đặt tên và metadata có thể được thay đổi riêng mà không phải sửa logic thực thi.

## 1. Vấn đề khi đặt tên và tag ngay trong mã thực thi

Giả sử ứng dụng có thao tác xác nhận đơn hàng. Mã thực thi có thể tự tạo Observation như sau:

~~~java
Observation.createNotStarted("orders.confirm", registry)
        .lowCardinalityKeyValue("order.channel", order.getChannel())
        .lowCardinalityKeyValue("order.type", "standard")
        .highCardinalityKeyValue("order.id", String.valueOf(order.getId()))
        .observe(() -> orderService.confirm(order));
~~~

Đoạn mã hoạt động, nhưng đang trộn hai trách nhiệm:

- Điều phối vòng đời thao tác: bắt đầu quan sát, chạy logic và kết thúc.
- Quyết định hợp đồng quan sát: tên Observation, tên key, giá trị tag và phân loại cardinality.

Khi đội vận hành muốn đổi tên từ orders.confirm sang order.confirmation, đổi key channel thành order.channel hoặc bổ sung tag source, mọi nơi tạo Observation có thể phải sửa. Nếu nhiều service tự xây dựng các tag theo cách khác nhau, dashboard và trace sẽ thiếu nhất quán.

ObservationConvention đưa hợp đồng metadata vào một thành phần riêng. Mã thực thi chỉ tạo context có dữ liệu cần thiết rồi dùng convention để tạo Observation.

## 2. ObservationConvention chịu trách nhiệm gì?

ObservationConvention là interface có kiểu context:

~~~java
public interface ObservationConvention<T extends Observation.Context>
        extends KeyValuesConvention {

    String getName();

    boolean supportsContext(Observation.Context context);
}
~~~

Ngoài các phương thức chính, interface còn cung cấp các phương thức mặc định để lấy contextual name và key-value:

| Phương thức | Trách nhiệm |
| --- | --- |
| getName() | Trả về tên kỹ thuật ổn định của Observation. |
| getContextualName(context) | Trả về tên thân thiện theo ngữ cảnh, thường hữu ích cho span hoặc hiển thị. |
| getLowCardinalityKeyValues(context) | Trả về các key-value có tập giá trị hữu hạn để dùng làm tag metric và metadata trace. |
| getHighCardinalityKeyValues(context) | Trả về metadata có thể có rất nhiều giá trị khác nhau, thường dành cho trace hoặc hệ thống hỗ trợ cardinality cao. |
| supportsContext(context) | Xác định convention có áp dụng cho loại context được truyền vào hay không. |

Convention không thực thi thao tác nghiệp vụ và không điều khiển thời điểm bắt đầu/kết thúc Observation. Nó chỉ mô tả cách đặt tên và trích xuất metadata từ context.

## 3. Phân biệt tên kỹ thuật và contextual name

Một Observation có thể có hai tên với mục đích khác nhau:

- **Tên kỹ thuật** xác định loại thao tác và thường trở thành tên meter. Tên này cần ổn định qua các lần triển khai.
- **Contextual name** mô tả thao tác cụ thể bằng ngôn ngữ dễ đọc hơn, thường được tracing handler dùng làm tên span.

Ví dụ:

| Thuộc tính | Giá trị |
| --- | --- |
| Observation name | orders.confirm |
| Contextual name | confirm order |
| Low-cardinality tag | order.channel=web |
| Low-cardinality tag | order.type=standard |
| High-cardinality key | order.id=ORD-84921 |

Không đưa order ID vào tên Observation hoặc contextual name. Nếu mỗi đơn hàng tạo một tên khác nhau, hệ thống sẽ mất khả năng tổng hợp theo operation và có thể tạo quá nhiều series hoặc span name không nhất quán.

## 4. Thiết kế context riêng cho thao tác

Context là nơi chứa dữ liệu mà convention và handler cần đọc. Với thao tác xác nhận đơn hàng, có thể tạo context chuyên biệt:

~~~java
import io.micrometer.observation.Observation;

public final class OrderConfirmationContext extends Observation.Context {

    private final String channel;
    private final String orderId;
    private final String orderType;

    public OrderConfirmationContext(
            String channel,
            String orderId,
            String orderType) {
        this.channel = channel;
        this.orderId = orderId;
        this.orderType = orderType;
    }

    public String getChannel() {
        return channel;
    }

    public String getOrderId() {
        return orderId;
    }

    public String getOrderType() {
        return orderType;
    }
}
~~~

Context nên chứa dữ liệu cần thiết để diễn giải Observation. Hãy giữ nó nhỏ, rõ ràng và có kiểu. Không dùng context làm nơi lưu toàn bộ entity, request body hoặc đối tượng lớn nếu handler chỉ cần vài thuộc tính.

Các trường trong ví dụ được truyền khi tạo context và mô tả dữ liệu đã biết trước khi thao tác bắt đầu. Nếu một kết quả như confirmed hoặc rejected chỉ biết sau khi thao tác kết thúc, không gắn nó như thể đã biết từ đầu. Có thể cập nhật context hoặc thêm low-cardinality key-value trước khi Observation dừng nếu cần kết quả đó trong Timer; riêng LongTaskTimer chỉ nhận tag có sẵn tại thời điểm start.

## 5. Tạo default convention

Default convention xác định quy ước mặc định khi không có convention tùy chỉnh hoặc global convention phù hợp:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationConvention;

public class DefaultOrderConfirmationConvention
        implements ObservationConvention<OrderConfirmationContext> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof OrderConfirmationContext;
    }

    @Override
    public String getName() {
        return "orders.confirm";
    }

    @Override
    public String getContextualName(OrderConfirmationContext context) {
        return "confirm order";
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(
            OrderConfirmationContext context) {
        return KeyValues.of(
                KeyValue.of("order.channel", context.getChannel()),
                KeyValue.of("order.type", context.getOrderType()));
    }

    @Override
    public KeyValues getHighCardinalityKeyValues(
            OrderConfirmationContext context) {
        return KeyValues.of(
                KeyValue.of("order.id", context.getOrderId()));
    }
}
~~~

Default convention ở đây thiết lập:

- Tên kỹ thuật orders.confirm.
- Contextual name confirm order.
- Channel và loại đơn hàng là low-cardinality key-value.
- Order ID là high-cardinality key-value.

Phương thức supportsContext phải kiểm tra đúng kiểu context. Nếu trả về true cho mọi context, convention có thể áp dụng nhầm lên Observation của HTTP client, database hoặc một module khác.

## 6. Tách mã thực thi khỏi quy ước

Mã thực thi tạo context và gọi Observation. Nó không cần biết tên metric hoặc tên tag:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public final class OrderConfirmationInstrumentation {

    private final ObservationRegistry observationRegistry;
    private final DefaultOrderConfirmationConvention defaultConvention;

    public OrderConfirmationInstrumentation(
            ObservationRegistry observationRegistry,
            DefaultOrderConfirmationConvention defaultConvention) {
        this.observationRegistry = observationRegistry;
        this.defaultConvention = defaultConvention;
    }

    public void observeConfirmation(
            String channel,
            String orderId,
            String orderType,
            Runnable operation) {

        OrderConfirmationContext context =
                new OrderConfirmationContext(channel, orderId, orderType);

        Observation.createNotStarted(
                null,
                defaultConvention,
                () -> context,
                observationRegistry)
                .observe(operation);
    }
}
~~~

Overload createNotStarted nhận bốn tham số ở ví dụ trên:

1. Custom convention tùy chọn. null có nghĩa là không truyền convention riêng cho lần tạo này.
2. Default convention bắt buộc để dùng khi registry không tìm thấy global convention phù hợp.
3. Supplier tạo context.
4. ObservationRegistry quản lý handler, predicate, filter và convention toàn cục.

Supplier giúp Micrometer tránh tạo context khi ObservationRegistry là no-op hoặc Observation bị predicate loại bỏ. Đây là một tối ưu hữu ích khi instrumentation được gọi rất thường xuyên.

Phương thức observe điều phối vòng đời: bắt đầu Observation, mở scope, chạy operation, ghi nhận lỗi nếu có, đóng scope và kết thúc Observation. Nếu tự điều khiển vòng đời bằng start/openScope/stop, phải bảo đảm stop luôn được gọi trong finally.

## 7. Thứ tự ưu tiên khi chọn convention

Micrometer chọn convention theo thứ tự:

1. **Custom convention truyền trực tiếp:** nếu lần tạo Observation truyền một custom convention khác null, convention này được sử dụng.
2. **GlobalObservationConvention phù hợp:** nếu không truyền custom convention, registry tìm global convention có supportsContext(context) trả về true.
3. **Default convention:** nếu không có custom convention và không có global convention phù hợp, default convention được sử dụng.

Thứ tự này giúp thư viện cung cấp default convention hợp lý, ứng dụng có thể áp dụng quy tắc chung qua registry, và một điểm gọi cụ thể vẫn có thể chủ động ghi đè bằng custom convention.

Không nhầm GlobalObservationConvention với bất kỳ ObservationConvention thông thường nào. Registry đăng ký convention toàn cục thông qua API dành cho GlobalObservationConvention.

## 8. Dùng GlobalObservationConvention cho quy ước cấp ứng dụng

Nếu muốn mọi thao tác xác nhận đơn hàng trong ứng dụng dùng một quy tắc thống nhất, có thể tạo global convention:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.GlobalObservationConvention;
import io.micrometer.observation.Observation;

public class GlobalOrderConvention
        implements GlobalObservationConvention<OrderConfirmationContext> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof OrderConfirmationContext;
    }

    @Override
    public String getName() {
        return "order.confirmation";
    }

    @Override
    public String getContextualName(OrderConfirmationContext context) {
        return "confirm order";
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(
            OrderConfirmationContext context) {
        return KeyValues.of(
                KeyValue.of("order.channel", context.getChannel()),
                KeyValue.of("order.type", context.getOrderType()));
    }

    @Override
    public KeyValues getHighCardinalityKeyValues(
            OrderConfirmationContext context) {
        return KeyValues.of(
                KeyValue.of("order.id", context.getOrderId()));
    }
}
~~~

Global convention có thể được đăng ký trực tiếp với registry:

~~~java
observationRegistry.observationConfig()
        .observationConvention(new GlobalOrderConvention());
~~~

Khi dùng Spring Boot, bean có kiểu GlobalObservationConvention được tự động đăng ký vào ObservationRegistry do Boot cấu hình. Có thể khai báo bằng @Bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderObservationConfiguration {

    @Bean
    GlobalOrderConvention globalOrderConvention() {
        return new GlobalOrderConvention();
    }
}
~~~

Chỉ những context mà supportsContext chấp nhận mới dùng convention này. Những Observation khác tiếp tục dùng convention tương ứng của chúng.

Nếu instrumentation truyền custom convention trực tiếp, custom convention đó thắng global convention. Đây là cách một thư viện hoặc một điểm tích hợp cho phép ứng dụng ghi đè có chủ đích.

## 9. Custom convention cho một trường hợp đặc biệt

Đôi khi một ứng dụng muốn thay đổi cách đặt tên hoặc metadata chỉ cho một luồng cụ thể. Khi đó, truyền custom convention trực tiếp:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

public final class PartnerOrderConvention
        extends DefaultOrderConfirmationConvention {

    @Override
    public String getName() {
        return "partner.orders.confirm";
    }

    @Override
    public String getContextualName(OrderConfirmationContext context) {
        return "confirm partner order";
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(
            OrderConfirmationContext context) {
        return super.getLowCardinalityKeyValues(context)
                .and(KeyValue.of("integration", "partner"));
    }
}
~~~

Tạo Observation bằng convention này:

~~~java
Observation.createNotStarted(
        new PartnerOrderConvention(),
        defaultConvention,
        () -> context,
        observationRegistry)
        .observe(operation);
~~~

Custom convention được chọn trực tiếp và có ưu tiên cao hơn GlobalOrderConvention đã đăng ký trong registry. Hãy dùng cách này khi khác biệt là có chủ đích và chỉ thuộc một integration hoặc operation cụ thể.

Không tạo custom convention cho từng request. Convention là cấu hình có vòng đời dài, còn context chứa dữ liệu thay đổi theo từng lần thực thi.

## 10. Phân loại low và high cardinality trong convention

Convention là nơi quan trọng để kiểm soát dữ liệu đi vào metrics và tracing.

| Loại key-value | Đặc điểm | Ví dụ |
| --- | --- | --- |
| Low cardinality | Số lượng giá trị có giới hạn và có thể dự đoán. | order.channel=web, mobile, partner. |
| High cardinality | Có thể có rất nhiều giá trị khác nhau. | order.id, user.id, trace.id. |

DefaultMeterObservationHandler chỉ đưa low-cardinality key-value vào meter tags. High-cardinality key-value không được đưa vào metrics vì có thể làm cardinality tăng mạnh. Tracing handler có thể dùng high-cardinality values trong span attributes.

Ví dụ phù hợp:

- Low: order.channel = web hoặc mobile.
- Low: order.type = standard, subscription hoặc digital.
- Low: payment.provider = primary hoặc backup.
- High: order.id = ORD-84921.
- High: customer.id = CUST-29173.

High cardinality không có nghĩa là dữ liệu luôn an toàn để xuất. ID khách hàng, email, token, số điện thoại và dữ liệu cá nhân vẫn có thể nhạy cảm. Chỉ đưa vào trace nếu chính sách bảo mật, quyền truy cập và thời hạn lưu trữ cho phép.

Không chuyển một giá trị không giới hạn thành low-cardinality chỉ bằng cách đổi tên key. Nếu URL có ID động, hãy chuẩn hóa thành route template. Nếu tenant có thể tăng không giới hạn, hãy nhóm theo tier hoặc loại tenant thay vì tag từng tenant.

## 11. Vì sao convention cần trả về KeyValues ổn định?

KeyValues từ convention trở thành metadata đầu vào cho các handler. Khi metric handler tạo meter, low-cardinality values thường trở thành tag của meter. Nếu cùng một Observation name nhưng các convention trả về schema tag khác nhau tùy nhánh, backend có thể khó truy vấn hoặc từ chối dữ liệu.

Hãy giữ ổn định:

- Tên key.
- Kiểu ngữ nghĩa của giá trị.
- Miền giá trị của low-cardinality key.
- Tên Observation cho cùng một loại thao tác.
- Chính sách high-cardinality cho từng backend.

Nếu cần thêm key mới, hãy đánh giá ảnh hưởng đến dashboard, alert, recording rule và số lượng series. Không thêm tag tùy tiện trong convention chỉ vì context có sẵn dữ liệu.

## 12. Phân biệt ObservationConvention với ObservationFilter

Hai thành phần này đều có thể thay đổi metadata trong context, nhưng mục đích khác nhau:

| Thành phần | Phạm vi | Trách nhiệm phù hợp |
| --- | --- | --- |
| ObservationConvention | Một loại context hoặc một nhóm Observation được hỗ trợ. | Đặt tên, contextual name và key-value theo ngữ nghĩa operation. |
| ObservationFilter | Áp dụng khi Observation chuẩn bị dừng. | Bổ sung hoặc chuẩn hóa metadata dùng chung, độc lập với convention đã chọn. |

Ví dụ, convention của đơn hàng quyết định order.channel và order.type. Filter chung có thể bổ sung cloud.zone hoặc deployment.environment cho mọi Observation.

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationFilter;

public class EnvironmentObservationFilter implements ObservationFilter {

    private final String environment;

    public EnvironmentObservationFilter(String environment) {
        this.environment = environment;
    }

    @Override
    public Observation.Context map(Observation.Context context) {
        return context.addLowCardinalityKeyValue(
                KeyValue.of("deployment.environment", environment));
    }
}
~~~

Đăng ký filter:

~~~java
observationRegistry.observationConfig()
        .observationFilter(new EnvironmentObservationFilter("production"));
~~~

Filter chạy trước các handler onStop. Vì vậy, metadata được thêm ở filter có thể xuất hiện trong Timer được ghi khi Observation dừng. Tuy nhiên, LongTaskTimer được tạo ngay khi Observation bắt đầu nên chỉ có những low-cardinality values đã có ở thời điểm start. Không dựa vào filter ở cuối vòng đời để bổ sung tag cần thiết cho meter theo dõi tác vụ đang chạy.

Nếu cần thêm metadata chung cho mọi Observation, filter thường phù hợp hơn việc sao chép cùng logic vào từng convention. Nếu metadata mô tả riêng một operation, đặt nó trong convention của operation đó.

## 13. Phân biệt convention với ObservationPredicate và ObservationHandler

Các thành phần trong Observation có trách nhiệm riêng:

| Thành phần | Câu hỏi nó trả lời |
| --- | --- |
| ObservationConvention | Observation này tên gì và có metadata nào? |
| ObservationPredicate | Có nên tạo Observation này hay trả về no-op? |
| ObservationHandler | Khi Observation bắt đầu, lỗi, phát event hoặc kết thúc thì cần làm gì? |
| ObservationFilter | Cần biến đổi context thế nào trước khi kết thúc? |
| Observation.Context | Những dữ liệu nào cần được chia sẻ giữa instrumentation và handler? |

Convention không quyết định Observation có được bật hay không. Predicate quyết định việc đó. Convention cũng không tự xuất metrics hoặc trace; handler mới thực hiện các hành động tương ứng.

Ví dụ, DefaultMeterObservationHandler chuyển Observation thành Timer và Counter. Một tracing handler có thể tạo span. Cả hai đọc cùng context nhưng sử dụng metadata theo khả năng của từng backend.

## 14. Tích hợp với Spring Boot

Spring Boot cấu hình ObservationRegistry và tự đăng ký các bean thuộc một số loại mở rộng:

- GlobalObservationConvention.
- ObservationFilter.
- ObservationPredicate.
- ObservationHandler.

Ứng dụng có thể tạo bean global convention mà không cần tự lấy registry rồi gọi observationConfig thủ công.

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
public class ObservationConfiguration {

    @Bean
    GlobalOrderConvention orderConvention() {
        return new GlobalOrderConvention();
    }

    @Bean
    EnvironmentObservationFilter environmentFilter(
            Environment environment) {
        return new EnvironmentObservationFilter(
                environment.getActiveProfiles().length == 0
                        ? "default"
                        : environment.getActiveProfiles()[0]);
    }
}
~~~

Ví dụ dùng Spring Environment để minh họa việc lấy profile. Trong production, nếu một ứng dụng có nhiều active profile, nên chọn một property triển khai rõ ràng như deployment.environment thay vì tùy tiện lấy phần tử đầu tiên.

Khi dùng Spring Boot, inject ObservationRegistry từ container. Không tạo ObservationRegistry.create() riêng trong từng service vì registry mới có thể không có meter handler, tracing handler, global conventions hoặc filters mà Boot đã cấu hình.

## 15. ObservationConvention và ObservationDocumentation

ObservationDocumentation là một cách khai báo schema Observation có cấu trúc. Nó có thể mô tả prefix, contextual name, default convention và danh sách key names có cardinality thấp/cao.

Khi module có nhiều Observation, schema tập trung giúp:

- Liệt kê các operation được instrument.
- Chuẩn hóa key names.
- Sinh tài liệu Observation bằng công cụ hỗ trợ.
- Giúp reviewer nhận ra tag mới hoặc thay đổi ngữ nghĩa.

ObservationConvention vẫn là thành phần cung cấp tên và KeyValues từ context. ObservationDocumentation bổ sung hợp đồng tài liệu hóa cho một loại Observation. Không bắt buộc phải dùng ObservationDocumentation cho một convention đơn giản, nhưng nó hữu ích khi module cần quản lý nhiều convention như một API quan sát ổn định.

## 16. Kiểm thử convention với SimpleMeterRegistry

Có thể kiểm tra convention đã tạo đúng tên và low-cardinality tags bằng DefaultMeterObservationHandler:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.junit.jupiter.api.Test;

class OrderConventionTest {

    @Test
    void appliesConventionNameAndLowCardinalityTags() {
        SimpleMeterRegistry meters = new SimpleMeterRegistry();
        ObservationRegistry observations = ObservationRegistry.create();
        observations.observationConfig().observationHandler(
                new DefaultMeterObservationHandler(meters));

        DefaultOrderConfirmationConvention convention =
                new DefaultOrderConfirmationConvention();

        Observation.createNotStarted(
                convention,
                convention,
                () -> new OrderConfirmationContext(
                        "web", "ORD-84921", "standard"),
                observations)
                .observe(() -> {
                    // Execute the operation under observation.
                });

        assertThat(meters.get("orders.confirm")
                .tag("order.channel", "web")
                .tag("order.type", "standard")
                .timer()
                .count()).isEqualTo(1);

        assertThat(meters.get("orders.confirm")
                .tag("order.channel", "web")
                .tag("order.type", "standard")
                .tag("error", "none")
                .timer()
                .getId()
                .getTag("order.id")).isNull();
    }
}
~~~

Kiểm thử xác minh:

- Convention đặt tên orders.confirm.
- Low-cardinality tags được đưa vào Timer.
- Order ID không trở thành meter tag.
- Observation được dừng sau khi operation hoàn tất.

Trong test thực tế, có thể kiểm tra contextual name bằng TestObservationRegistry hoặc custom handler. SimpleMeterRegistry phù hợp để xác minh phần metrics, nhưng không phải công cụ kiểm tra span name.

## 17. Kiểm thử thứ tự ưu tiên convention

Nên có test riêng cho ba cấp convention:

1. Truyền custom convention trực tiếp và xác minh tên custom được sử dụng.
2. Không truyền custom convention, đăng ký GlobalObservationConvention phù hợp và xác minh tên global được sử dụng.
3. Không có global convention phù hợp và xác minh default convention được sử dụng.

Một global convention phải có supportsContext kiểm tra đúng context. Nếu trả false, registry bỏ qua nó và dùng convention tiếp theo.

Đối với ứng dụng Spring Boot, có thể dùng ApplicationContext test để xác minh bean GlobalObservationConvention được tự động đăng ký. Với unit test thuần Micrometer, gọi observationConfig().observationConvention(...) trực tiếp.

## 18. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Đặt tên và tag trong từng đoạn code nghiệp vụ | Quy ước bị lặp và khó thay đổi đồng bộ. | Đưa metadata vào ObservationConvention. |
| supportsContext luôn trả true | Convention có thể áp dụng nhầm cho context khác. | Kiểm tra kiểu context cụ thể. |
| Truyền custom convention nhưng mong global convention ghi đè | Custom convention có độ ưu tiên cao hơn. | Không truyền custom nếu muốn registry chọn global convention. |
| Dùng ObservationConvention thường như global bean | Registry chỉ đăng ký global convention qua GlobalObservationConvention. | Implement GlobalObservationConvention hoặc đăng ký đúng API. |
| Đưa ID vào low-cardinality tags | Tạo cardinality explosion ở metrics backend. | Chuyển dữ liệu không giới hạn sang high cardinality nếu cần trace và được phép. |
| Cho rằng high-cardinality luôn an toàn | Trace có thể chứa dữ liệu nhạy cảm và chi phí lưu trữ cao. | Áp dụng chính sách dữ liệu, quyền truy cập và retention. |
| Dùng filter để đặt tên từng operation | Filter không phải nơi chọn tên convention. | Dùng convention cho tên và metadata theo operation. |
| Thêm tag sau start nhưng mong LongTaskTimer có tag | LongTaskTimer đã được tạo khi Observation bắt đầu. | Đưa low-cardinality values cần thiết vào context/convention trước start. |
| Tạo ObservationRegistry mới trong từng service | Có thể bỏ qua handler, filter và convention do framework cấu hình. | Inject registry do Spring Boot quản lý. |
| Trả về tag schema thay đổi tùy nhánh | Dashboard và backend khó tổng hợp các series cùng meter. | Chuẩn hóa key names và miền giá trị. |

## 19. Checklist thiết kế ObservationConvention

- [ ] Đã xác định loại thao tác và context chuyên biệt.
- [ ] Context chỉ chứa dữ liệu cần cho convention và handler.
- [ ] getName trả về tên kỹ thuật ổn định.
- [ ] getContextualName có ý nghĩa và không chứa ID động.
- [ ] supportsContext chỉ chấp nhận đúng loại context.
- [ ] Low-cardinality key-value có miền giá trị hữu hạn.
- [ ] High-cardinality key-value không chứa dữ liệu nhạy cảm nếu chưa được phép.
- [ ] Convention mặc định được cung cấp cho instrumentation.
- [ ] Đã xác định có cần GlobalObservationConvention ở cấp ứng dụng hay không.
- [ ] Hiểu custom convention truyền trực tiếp có ưu tiên cao nhất.
- [ ] Dùng ObservationFilter cho metadata chung cần bổ sung xuyên suốt nhiều convention.
- [ ] Dùng ObservationPredicate để loại Observation khi cần.
- [ ] Handler tương ứng đã được cấu hình để tạo metrics hoặc tracing.
- [ ] Đã kiểm thử tên, tag, cardinality và thứ tự ưu tiên.
- [ ] Đã kiểm tra dashboard và tracing sau khi thay đổi convention.

ObservationConvention giúp tách hợp đồng metadata khỏi vòng đời và logic thực thi. Context mang dữ liệu của thao tác; convention chuyển dữ liệu đó thành tên và key-value có quy tắc; handler chuyển Observation thành metrics, trace hoặc hành động khác. Khi giữ rõ các vai trò này, ứng dụng có thể thay đổi cách đặt tên và tag mà không phải sửa mã thực thi, đồng thời kiểm soát được cardinality và tính nhất quán của dữ liệu quan sát.

## Tài liệu tham khảo

- [Micrometer Observation - Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Micrometer Observation - Components and ObservationConvention](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [ObservationConvention API](https://javadoc.io/static/io.micrometer/micrometer-observation/1.15.0/io/micrometer/observation/ObservationConvention.html)
- [GlobalObservationConvention API](https://javadoc.io/static/io.micrometer/micrometer-observation/1.15.0/io/micrometer/observation/GlobalObservationConvention.html)
- [Spring Boot Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
