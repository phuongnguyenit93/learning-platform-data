# Đảm bảo gọi gắn phép đo lặp lại không tạo số liệu sai

MeterBinder đóng gói việc đăng ký các meter cho một thành phần của ứng dụng. Một binder có thể được Spring Boot tự động áp dụng vào registry, được gọi thủ công trong Java hoặc được gắn vào nhiều registry khác nhau. Vì vậy, phương thức bindTo(MeterRegistry) cần được thiết kế để có thể gọi lại an toàn.

Gọi bindTo nhiều lần với cùng registry không nên tạo thêm time series ngoài ý muốn, làm tăng Counter chỉ vì binder chạy lại hoặc thay nguồn dữ liệu của Gauge bằng một đối tượng tạm. Muốn đạt được điều đó, cần hiểu cách registry nhận diện meter, giữ ổn định đối tượng được Gauge quan sát và tách đăng ký meter khỏi việc ghi nhận sự kiện nghiệp vụ.

## 1. bindTo có thể được gọi nhiều lần trong những trường hợp nào?

MeterBinder có một phương thức chính:

~~~java
public interface MeterBinder {
    void bindTo(MeterRegistry registry);
}
~~~

Phương thức này nhận registry và đăng ký các meter mà thành phần cần công bố. Trong ứng dụng thực tế, một binder có thể được gọi:

- Khi Spring Boot khởi tạo MeterRegistry và áp dụng các bean MeterBinder.
- Khi ứng dụng Java tự gọi binder.bindTo(registry) lúc khởi động.
- Khi một registry mới được tạo để xuất metrics đến một backend khác.
- Trong kiểm thử, khi test cố ý gọi binder nhiều lần để xác minh tính lặp lại.
- Khi cấu hình ứng dụng vô tình vừa tự đăng ký binder vừa để Spring Boot tự động đăng ký.

Một binder tốt cần phân biệt hai tình huống: gọi lại trên cùng registry và bind sang registry khác. Trên cùng registry, việc đăng ký cùng meter identity cần ổn định. Trên registry khác, meter cần được đăng ký độc lập vào registry mới.

## 2. Registry nhận diện meter như thế nào?

Trong Micrometer, tên meter và tập tag tạo nên định danh dùng để tìm meter trong registry. Loại meter cũng phải nhất quán. Ví dụ:

~~~java
registry.counter("queue.messages.received", "queue", "orders");
~~~

Mỗi lần gọi đoạn mã này trên cùng registry, ứng dụng nhận lại Counter có cùng tên và tag. Registry không tạo một Counter mới chỉ vì phương thức được gọi thêm lần nữa.

Điều này giúp đăng ký meter có tính lặp lại, nhưng không có nghĩa mọi lần đăng ký trùng ID đều vô hại:

- Nếu cùng tên và tag được dùng cho cùng loại meter, registry thường trả lại meter đã tồn tại.
- Nếu hai thành phần dùng cùng tên và tag nhưng khác loại meter, registry có thể báo lỗi xung đột kiểu.
- Nếu hai binder cùng sở hữu một meter ID, chúng có thể vô tình dùng chung số liệu hoặc tranh chấp định nghĩa.
- Với Gauge, đăng ký trùng ID không bảo đảm nguồn đối tượng mới sẽ thay thế nguồn đã đăng ký trước đó.

Vì vậy, hãy quản lý tên và tag như hợp đồng của instrumentation. Mỗi meter ID cần có một ý nghĩa và một nơi sở hữu rõ ràng.

## 3. Ví dụ binder có thể gọi lặp lại an toàn

Giả sử ứng dụng cần theo dõi độ sâu của queue orders. Trạng thái queue được quản lý bởi một đối tượng có vòng đời dài:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class QueueState {

    private final AtomicInteger depth = new AtomicInteger();

    public int depth() {
        return depth.get();
    }

    public void jobAdded() {
        depth.incrementAndGet();
    }

    public void jobTaken() {
        depth.decrementAndGet();
    }
}
~~~

Binder giữ tham chiếu đến QueueState và chỉ đăng ký Gauge:

~~~java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterBinder;
import io.micrometer.core.instrument.MeterRegistry;

public final class QueueMetricsBinder implements MeterBinder {

    private final QueueState queueState;

    public QueueMetricsBinder(QueueState queueState) {
        this.queueState = queueState;
    }

    @Override
    public void bindTo(MeterRegistry registry) {
        Gauge.builder("queue.depth", queueState, QueueState::depth)
                .description("Current number of jobs waiting in the orders queue")
                .tag("queue", "orders")
                .register(registry);
    }
}
~~~

Nếu bindTo được gọi hai lần trên cùng registry, tên và tag của Gauge vẫn giống nhau, còn đối tượng QueueState được giữ ổn định. Registry có thể tái sử dụng Gauge đã đăng ký. Binder không tạo thêm một queue state mới và không làm thay đổi giá trị queue chỉ vì đăng ký meter.

## 4. Không tạo đối tượng Gauge tạm bên trong bindTo

Một lỗi phổ biến là tạo đối tượng mới mỗi lần binder chạy:

~~~java
@Override
public void bindTo(MeterRegistry registry) {
    AtomicInteger depth = new AtomicInteger();

    Gauge.builder("queue.depth", depth, AtomicInteger::get)
            .tag("queue", "orders")
            .register(registry);
}
~~~

Đoạn mã này có hai vấn đề:

1. Gauge thường giữ weak reference đến đối tượng được quan sát. Khi bindTo kết thúc, biến depth không còn tham chiếu mạnh bên ngoài; đối tượng có thể bị garbage collector thu hồi.
2. Nếu bindTo được gọi lại với cùng tên và tag, registry đã có Gauge cùng ID. Đăng ký mới không bảo đảm thay nguồn quan sát cũ bằng AtomicInteger mới; registry thường giữ meter đã tồn tại và có thể ghi cảnh báo về đăng ký Gauge trùng.

Kết quả có thể là Gauge trả về NaN hoặc không phản ánh trạng thái mà lần bind mới tạo ra, tùy vòng đời và registry. Cách sửa là tạo state holder ở constructor hoặc trong bean sở hữu tài nguyên, giữ nó bằng field và truyền cùng đối tượng đó vào Gauge.builder.

Không chỉ Gauge mới cần chú ý vòng đời. Các object, callback hoặc function được dùng để đọc trạng thái cũng cần tham chiếu đến dữ liệu có vòng đời phù hợp. Không tạo nguồn dữ liệu tạm chỉ để đăng ký một meter tồn tại lâu hơn nguồn đó.

## 5. Không ghi nhận sự kiện trong bindTo

bindTo là nơi đăng ký meter, không phải nơi mô phỏng sự kiện nghiệp vụ. Ví dụ sau làm sai số liệu:

~~~java
@Override
public void bindTo(MeterRegistry registry) {
    Counter counter = registry.counter("application.started");
    counter.increment();
}
~~~

Mỗi lần binder được áp dụng, Counter lại tăng một lần. Nếu Spring Boot và mã ứng dụng cùng gọi binder, hoặc binder được áp dụng lại khi tạo registry, số liệu sẽ tăng dù ứng dụng không thực sự khởi động thêm lần nào.

Hãy chỉ đăng ký Counter trong binder:

~~~java
@Override
public void bindTo(MeterRegistry registry) {
    registry.counter("queue.messages.received", "queue", "orders");
}
~~~

Sau đó, tăng Counter tại nơi sự kiện thực sự xảy ra:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

public final class QueueMessageRecorder {

    private final Counter received;

    public QueueMessageRecorder(MeterRegistry registry) {
        this.received = registry.counter(
                "queue.messages.received",
                "queue", "orders");
    }

    public void messageReceived() {
        received.increment();
    }
}
~~~

Hai đoạn mã dùng cùng tên và tag trên cùng registry nên lấy cùng meter. Tuy nhiên, chỉ messageReceived mới tăng Counter. Số lần binder chạy không ảnh hưởng đến số message được ghi nhận.

Nguyên tắc tương tự áp dụng cho Timer và DistributionSummary: bindTo có thể đăng ký meter, còn record hoặc record(duration) phải được gọi tại thời điểm thao tác thực tế xảy ra.

## 6. Phân biệt idempotent registration và idempotent business event

Hai khái niệm này không giống nhau:

| Hoạt động | Có thể lặp lại an toàn? | Lý do |
| --- | --- | --- |
| Đăng ký Counter cùng tên và tag trên cùng registry | Có, nếu loại và ý nghĩa meter nhất quán | Registry tìm meter theo identity và trả lại meter đã có. |
| Đăng ký Timer cùng tên và tag trên cùng registry | Có, nếu cấu hình và loại meter tương thích | Không tạo thêm meter chỉ vì builder được gọi lại. |
| Đăng ký Gauge cùng ID với cùng nguồn quan sát ổn định | Có thể, nhưng nên tránh đăng ký trùng không cần thiết | Registry giữ meter hiện có; nguồn Gauge phải có vòng đời đúng. |
| Tạo Gauge với một object mới nhưng cùng ID | Không nên dựa vào hành vi này | Đăng ký sau có thể bị bỏ qua; object mới có thể bị thu hồi. |
| Gọi Counter.increment() trong bindTo | Không | Mỗi lần bind tạo thêm một lần tăng giả. |
| Ghi Timer.record() trong bindTo | Không | Mỗi lần bind tạo thêm một quan sát không đại diện thao tác nghiệp vụ. |
| Bind cùng binder sang registry khác | Có, nếu binder hỗ trợ nhiều registry | Mỗi registry có không gian meter riêng và cần nhận meter của nó. |

Tính lặp lại của đăng ký không làm cho một sự kiện nghiệp vụ trở thành idempotent. Nếu một message được giao lại hai lần, logic xử lý message cần quyết định có tính hai lần nhận hay chỉ một lần xử lý thành công. MeterBinder không giải quyết vấn đề trùng sự kiện ở tầng nghiệp vụ.

## 7. Không dùng registry.find như khóa chống đăng ký trùng

Có thể thấy một số mã kiểm tra trước khi đăng ký:

~~~java
if (registry.find("queue.depth").gauge() == null) {
    Gauge.builder("queue.depth", queueState, QueueState::depth)
            .register(registry);
}
~~~

Đây không phải cơ chế bảo đảm idempotence đáng tin cậy:

- Kiểm tra và đăng ký là hai thao tác riêng; hai thread có thể cùng thấy meter chưa tồn tại rồi cùng đăng ký.
- Việc tìm theo tên nhưng bỏ qua tag có thể kiểm tra nhầm meter khác.
- Điều kiện này có thể che giấu xung đột loại meter hoặc sai cấu hình.
- Registry đã có cơ chế quản lý meter theo identity khi đăng ký.

Hãy gọi builder/register với tên và tag ổn định. Nếu có hai binder cạnh tranh cùng một meter ID, giải quyết quyền sở hữu và naming convention thay vì thêm một lớp check-then-register.

## 8. Spring Boot: chỉ chọn một đường đăng ký binder

Spring Boot có thể tự động áp dụng các bean triển khai MeterBinder vào MeterRegistry. Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MetricsConfiguration {

    @Bean
    QueueState queueState() {
        return new QueueState();
    }

    @Bean
    QueueMetricsBinder queueMetricsBinder(QueueState queueState) {
        return new QueueMetricsBinder(queueState);
    }
}
~~~

Khi QueueMetricsBinder là bean, Spring Boot sẽ phát hiện và áp dụng nó vào registry theo cơ chế auto-configuration. Trong trường hợp này, không cần gọi thủ công queueMetricsBinder.bindTo(meterRegistry) trong ApplicationRunner hoặc một bean khởi tạo khác.

Nếu vừa khai báo binder bean vừa gọi bindTo thủ công, binder có thể bị áp dụng lặp lại trên cùng registry. Registry thường ngăn tạo meter trùng ID, nhưng cách đăng ký kép vẫn không cần thiết và có thể gây lỗi nếu binder chứa side effect hoặc tạo nguồn Gauge mới.

Với ứng dụng không dùng Spring Boot, gọi bindTo một lần cho mỗi registry trong giai đoạn khởi tạo:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();
QueueState state = new QueueState();
QueueMetricsBinder binder = new QueueMetricsBinder(state);

binder.bindTo(registry);
~~~

Giữ quy tắc đăng ký tập trung: hoặc framework tự quản lý binder, hoặc ứng dụng tự gọi binder. Không để cả hai cùng làm một việc.

## 9. Một binder có thể được gắn vào nhiều registry

Một MeterBinder không nên mặc định chỉ được sử dụng với một registry. Ví dụ ứng dụng có thể xuất metrics sang hai backend:

~~~java
QueueState state = new QueueState();
QueueMetricsBinder binder = new QueueMetricsBinder(state);

MeterRegistry prometheusRegistry = createPrometheusRegistry();
MeterRegistry testRegistry = new SimpleMeterRegistry();

binder.bindTo(prometheusRegistry);
binder.bindTo(testRegistry);
~~~

Hai registry có hai tập meter riêng. Cùng một state holder có thể được quan sát bởi cả hai registry, nhưng meter object của từng registry là độc lập.

Tránh lưu một Counter hoặc Gauge được tạo trong bindTo vào field đơn của binder nếu cùng binder có thể được gọi với nhiều registry:

~~~java
public final class IncorrectBinder implements MeterBinder {

    private Counter received;

    @Override
    public void bindTo(MeterRegistry registry) {
        this.received = registry.counter("queue.messages.received");
    }
}
~~~

Khi binder được gắn vào registry thứ hai, field received bị thay bằng Counter của registry thứ hai. Nếu code nghiệp vụ sau đó gọi field này, chỉ registry cuối cùng nhận được cập nhật. Với nhiều registry, hãy để từng thành phần ghi nhận sự kiện lấy meter từ registry tương ứng, hoặc quản lý rõ ràng một bộ meter theo registry thay vì một field đơn.

Nếu dùng CompositeMeterRegistry, hãy thống nhất bind vào composite hay vào các registry con theo kiến trúc đã chọn. Tránh đăng ký cùng binder qua nhiều đường không cần thiết; điều đó làm luồng cấu hình khó hiểu dù registry có thể hợp nhất các meter cùng identity.

## 10. Tên và tag ổn định giúp tránh chia tách số liệu

Đăng ký lặp lại không tạo meter mới khi identity giống nhau. Ngược lại, chỉ cần thay tag-value hoặc tag-key là có thể tạo một meter identity khác:

~~~java
registry.counter("queue.messages.received", "queue", "orders");
registry.counter("queue.messages.received", "queue", "orders-v2");
~~~

Hai Counter trên là hai chuỗi thời gian khác nhau. Nếu binder vô tình tạo tag-value từ UUID, timestamp hoặc object.toString(), mỗi lần bind có thể tạo một series mới và làm cardinality tăng.

Hãy dùng tag có tập giá trị hữu hạn, được chuẩn hóa:

- queue: orders, emails, images.
- pool: primary, reporting.
- result: success, failure, timeout.
- region: mã khu vực triển khai đã được quản lý.

Không dùng request ID, user ID, order ID, tên file hoặc nội dung lỗi làm tag. Không dùng giá trị hiện tại của Gauge làm tag; giá trị phải là số đo, còn tag chỉ mô tả chiều phân nhóm.

## 11. Khi binder thực sự cần thay đổi cấu hình meter

Nếu binder được gọi lại với cùng meter ID nhưng description, base unit hoặc tag convention khác, registry không nên bị xem như nơi tự động hòa giải mọi khác biệt. Một meter ID cần có một hợp đồng ổn định. Cấu hình không đồng nhất giữa các binder có thể tạo cảnh báo hoặc khiến cấu hình đầu tiên được giữ lại.

Nếu muốn thay đổi ý nghĩa metric:

1. Xác định liệu đây là thay đổi mô tả hay thay đổi ngữ nghĩa đo lường.
2. Nếu ngữ nghĩa thay đổi, cân nhắc tên metric mới để không trộn dữ liệu lịch sử khác ý nghĩa.
3. Cập nhật dashboard, alert và recording rule liên quan.
4. Loại bỏ đăng ký cũ qua quy trình cấu hình/vòng đời rõ ràng.
5. Không đổi tag-value chỉ để ép meter mới xuất hiện nếu điều đó không phải chiều phân tích thực.

Không nên dùng MeterFilter để âm thầm đổi tag của hai binder thành cùng một identity. Filter có thể làm mất khác biệt giữa meter vốn được thiết kế riêng; hãy kiểm tra ID cuối cùng sau filter.

## 12. Kiểm thử binder được gọi nhiều lần

Kiểm thử với SimpleMeterRegistry có thể xác nhận binder không tạo thêm meter và Gauge tiếp tục đọc cùng nguồn trạng thái:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class QueueMetricsBinderTest {

    @Test
    void repeatedBindingToSameRegistryDoesNotDuplicateGauge() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        QueueState state = new QueueState();
        QueueMetricsBinder binder = new QueueMetricsBinder(state);

        state.jobAdded();
        state.jobAdded();

        binder.bindTo(registry);
        binder.bindTo(registry);

        assertThat(registry.getMeters().stream()
                .filter(meter -> meter.getId().getName().equals("queue.depth"))
                .count()).isEqualTo(1);

        assertThat(registry.get("queue.depth")
                .tag("queue", "orders")
                .gauge()
                .value()).isEqualTo(2.0);
    }
}
~~~

Kiểm thử này xác minh:

- Gọi bindTo hai lần không tạo hai Gauge cùng meter ID.
- Gauge vẫn đọc QueueState được binder giữ.
- Việc bind không tự tăng hoặc giảm độ sâu queue.

Có thể bổ sung kiểm thử cho nhiều registry:

~~~java
@Test
void sameBinderCanBindToTwoIndependentRegistries() {
    SimpleMeterRegistry first = new SimpleMeterRegistry();
    SimpleMeterRegistry second = new SimpleMeterRegistry();
    QueueMetricsBinder binder = new QueueMetricsBinder(new QueueState());

    binder.bindTo(first);
    binder.bindTo(second);

    assertThat(first.find("queue.depth").gauge()).isNotNull();
    assertThat(second.find("queue.depth").gauge()).isNotNull();
}
~~~

Ngoài ra, nên kiểm thử rằng Counter chỉ tăng khi phương thức ghi nhận sự kiện được gọi, không tăng sau khi bindTo chạy lại. Kiểm thử xung đột meter type cũng hữu ích nếu nhiều binder cùng sở hữu một nhóm tên metric.

## 13. Checklist trước khi phát hành MeterBinder

- [ ] bindTo chỉ đăng ký meter, không mô phỏng sự kiện nghiệp vụ.
- [ ] Tên meter và tag ổn định qua các lần gọi.
- [ ] Mỗi meter ID có một loại meter và một ý nghĩa thống nhất.
- [ ] Không có hai binder vô tình sở hữu cùng meter ID.
- [ ] Gauge dùng nguồn quan sát có vòng đời đủ dài và được giữ bằng tham chiếu mạnh.
- [ ] Không tạo Gauge source object tạm bên trong bindTo.
- [ ] Không dùng registry.find như khóa check-then-register.
- [ ] Spring Boot chỉ có một đường áp dụng binder; không vừa auto-bind vừa gọi thủ công.
- [ ] Binder hoạt động đúng khi được gắn vào nhiều registry.
- [ ] Không lưu meter của registry cuối cùng vào một field đơn dùng chung cho nhiều registry.
- [ ] Đã kiểm thử gọi bindTo lặp lại trên cùng registry.
- [ ] Đã kiểm thử meter được tạo trên registry thứ hai nếu ứng dụng có nhiều backend.

Một MeterBinder đáng tin cậy có thể được áp dụng lại mà không làm thay đổi số liệu nghiệp vụ. Registry quản lý meter theo identity; binder giữ nguồn Gauge ổn định và chỉ đăng ký meter; còn Counter, Timer hoặc DistributionSummary chỉ được cập nhật tại điểm sự kiện hoặc thao tác thực sự xảy ra.

## Tài liệu tham khảo

- [Micrometer MeterBinder API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/binder/MeterBinder.html)
- [Micrometer MeterRegistry API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/MeterRegistry.html)
- [Spring Boot Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
