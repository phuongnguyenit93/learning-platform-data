# MultiGauge cho tập Gauge có thành viên thay đổi

Trong nhiều hệ thống, một đại lượng cần theo dõi được chia thành các nhóm có thể xuất hiện hoặc biến mất theo thời gian. Ví dụ, số đơn hàng theo trạng thái, số message theo loại, số tác vụ theo hàng đợi hoặc số kết nối theo pool. Tập nhóm này không phải lúc nào cũng cố định khi ứng dụng khởi động.

Nếu đăng ký một Gauge riêng cho từng nhóm bằng code thủ công, ứng dụng phải tự quản lý việc thêm, cập nhật và gỡ meter khi nhóm thay đổi. **MultiGauge** của Micrometer giải quyết bài toán này bằng cách quản lý một tập Gauge có cùng tên và tag chung; mỗi hàng (row) tạo ra một Gauge với các tag riêng. Khi dữ liệu nguồn thay đổi, ứng dụng đăng ký snapshot mới để cập nhật tập row.

Trong module **OBSERVABILITY_INSTRUMENTATION_MICROMETER**, MultiGauge là một meter nâng cao hữu ích khi cần theo dõi một tập tiêu chí nhỏ, có giới hạn và thay đổi vừa phải. Bài này trình bày cách thiết kế row, cập nhật snapshot, xử lý row không còn tồn tại, quản lý vòng đời MultiGauge và kiểm soát cardinality.

## 1. Khi nào nên dùng MultiGauge?

Giả sử một dịch vụ xử lý đơn hàng có các trạng thái NEW, PAID, SHIPPED và CANCELLED. Tập trạng thái có thể thay đổi theo quy trình nghiệp vụ hoặc cấu hình. Người vận hành muốn biết hiện có bao nhiêu đơn hàng ở mỗi trạng thái.

Có thể biểu diễn mỗi trạng thái thành một Gauge riêng:

~~~text
orders.by.status{status="NEW"} 12
orders.by.status{status="PAID"} 35
orders.by.status{status="SHIPPED"} 21
~~~

Khi không còn đơn hàng ở trạng thái NEW, row tương ứng nên được gỡ khỏi tập metrics hiện tại. Khi xuất hiện trạng thái mới đã được hệ thống cho phép, một row mới có thể được đăng ký.

MultiGauge phù hợp khi:

- Tập nhóm có số lượng nhỏ hoặc được giới hạn bởi danh mục nghiệp vụ.
- Nhóm có thể xuất hiện hoặc biến mất theo kết quả truy vấn.
- Mỗi nhóm cần một Gauge có cùng tên metric và khác nhau bằng tag.
- Ứng dụng có thể định kỳ lấy snapshot dữ liệu và đăng ký lại tập row.

Ví dụ điển hình là truy vấn SQL GROUP BY status, GROUP BY queue_name với danh mục queue đã được kiểm soát, hoặc số lượng tác vụ theo một tập trạng thái hữu hạn.

MultiGauge không phải giải pháp để xuất mọi bản ghi hoặc mọi người dùng thành một Gauge. Nếu mỗi row tương ứng với userId, orderId, requestId hoặc một giá trị gần như duy nhất, cardinality sẽ tăng nhanh. Những dữ liệu chi tiết theo từng thực thể nên được xử lý bằng log, trace hoặc truy vấn dữ liệu nghiệp vụ phù hợp.

## 2. MultiGauge quản lý nhiều Gauge dưới cùng một tên

MultiGauge là một đối tượng quản lý (virtual meter), không phải một chuỗi thời gian đơn lẻ. Nó tạo và gỡ các Gauge thực tế trong MeterRegistry.

Mỗi Gauge do MultiGauge quản lý có:

- Tên chung do builder chỉ định.
- Các tag chung được cấu hình trên builder hoặc registry.
- Các tag riêng của row để phân biệt từng nhóm.
- Một giá trị được đọc từ Number hoặc từ object và hàm lấy giá trị.

Ví dụ, tạo MultiGauge theo trạng thái đơn hàng:

~~~java
import io.micrometer.core.instrument.MultiGauge;
import io.micrometer.core.instrument.MeterRegistry;

public class OrderStatusMetrics {
    private final MultiGauge ordersByStatus;

    public OrderStatusMetrics(MeterRegistry registry) {
        this.ordersByStatus = MultiGauge.builder("orders.by.status")
                .description("Number of orders grouped by status")
                .baseUnit("orders")
                .register(registry);
    }
}
~~~

Ở đây ordersByStatus quản lý các Gauge có tên orders.by.status. Các row sẽ thêm tag status như NEW, PAID hoặc SHIPPED. Nếu registry đã có common tags như service, environment và region, những tag đó cũng được áp dụng theo cấu hình registry.

Cần giữ tham chiếu đến đối tượng MultiGauge trong một field có vòng đời đủ dài, chẳng hạn field của Spring singleton. Không tạo MultiGauge trong một biến cục bộ rồi bỏ tham chiếu sau khi đăng ký row. Các row không được bảo đảm tiếp tục được báo cáo nếu chính MultiGauge đã bị garbage collector thu gom, ngay cả khi object nguồn của row vẫn còn sống.

## 3. Tạo row bằng tag và giá trị snapshot

Cách đơn giản nhất là dùng MultiGauge.Row.of(Tags, Number). Giá trị Number được dùng làm giá trị Gauge cho snapshot hiện tại.

Ví dụ:

~~~java
import io.micrometer.core.instrument.MultiGauge;
import io.micrometer.core.instrument.Tags;

List<MultiGauge.Row<?>> rows = Arrays.asList(
        MultiGauge.Row.of(Tags.of("status", "NEW"), 12),
        MultiGauge.Row.of(Tags.of("status", "PAID"), 35),
        MultiGauge.Row.of(Tags.of("status", "SHIPPED"), 21)
);

ordersByStatus.register(rows, true);
~~~

Mỗi row tạo một Gauge có tên orders.by.status và tag riêng status. Các giá trị 12, 35 và 21 là snapshot tại thời điểm đăng ký. Khi truy vấn nguồn dữ liệu lần tiếp theo, ứng dụng tạo danh sách row mới và đăng ký lại để cập nhật số lượng.

Dùng Tags.of(...) để tạo tập tag của row. Những tag này cần xác định duy nhất một row trong MultiGauge. Ví dụ, với metric đơn hàng theo trạng thái, tag status là đủ nếu mỗi trạng thái chỉ có một kết quả.

Nếu cần thêm một chiều phân loại như kênh bán hàng, row có thể dùng hai tag status và channel. Tuy nhiên, cần cân nhắc số tổ hợp trước khi thêm tag.

## 4. Cập nhật snapshot và xử lý row không còn tồn tại

MultiGauge được thiết kế để đăng ký lại tập row mỗi khi ứng dụng lấy được snapshot mới. Khi gọi register(rows, true):

- Row mới được thêm vào registry.
- Row đã có cùng tag được cập nhật để sử dụng giá trị mới.
- Row cũ không còn xuất hiện trong danh sách mới sẽ được gỡ khỏi registry.
- Nếu nhiều row trong cùng snapshot có cùng meter ID, row cuối cùng trong thứ tự lặp sẽ được ưu tiên.

Tham số overwrite quyết định cách xử lý row có cùng tag:

| Cách gọi | Row có tag đã tồn tại | Row mới | Row không còn trong snapshot |
|---|---|---|---|
| register(rows, true) | Cập nhật theo row mới | Được thêm | Được gỡ |
| register(rows, false) | Giữ định nghĩa/giá trị đã đăng ký trước | Được thêm | Được gỡ |

Khi mỗi lần đăng ký đại diện cho một snapshot mới từ database hoặc API, thường nên dùng overwrite=true. Nếu dùng false, một row đã tồn tại sẽ không nhận giá trị mới dù dữ liệu nguồn đã thay đổi.

Ví dụ, snapshot đầu tiên có NEW=12, PAID=35; snapshot sau có NEW=8, SHIPPED=21. Với overwrite=true, giá trị NEW được cập nhật thành 8, row PAID được gỡ và row SHIPPED được thêm.

Nếu danh sách mới rỗng, các row đã được MultiGauge quản lý sẽ bị gỡ. Vì vậy, chỉ đăng ký danh sách rỗng khi đó thực sự là snapshot hợp lệ có nghĩa không còn nhóm nào. Nếu truy vấn database thất bại hoặc dữ liệu nguồn tạm thời không truy cập được, không nên coi lỗi đó như danh sách rỗng và xóa toàn bộ row đang có. Hãy xử lý lỗi riêng và giữ snapshot hợp lệ gần nhất cho đến khi có dữ liệu mới.

## 5. Ví dụ Spring Boot lấy số lượng theo trạng thái

Một ứng dụng có thể truy vấn số đơn hàng theo trạng thái từ repository. Repository trả về projection gồm tên trạng thái và số lượng:

~~~sql
SELECT status, COUNT(*) AS order_count
FROM orders
GROUP BY status
~~~

Component giữ MultiGauge trong field và cập nhật row sau mỗi lần lấy snapshot:

~~~java
import java.util.List;
import java.util.stream.Collectors;

import io.micrometer.core.instrument.MultiGauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Tags;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class OrderStatusMetrics {
    private final MultiGauge ordersByStatus;
    private final OrderRepository orderRepository;

    public OrderStatusMetrics(
            MeterRegistry registry,
            OrderRepository orderRepository) {
        this.ordersByStatus = MultiGauge.builder("orders.by.status")
                .description("Number of orders grouped by status")
                .baseUnit("orders")
                .register(registry);
        this.orderRepository = orderRepository;
    }

    @Scheduled(fixedDelayString = "${metrics.orders.refresh-delay:30000}")
    public void refresh() {
        List<MultiGauge.Row<?>> rows = orderRepository.countByStatus()
                .stream()
                .map(result -> MultiGauge.Row.of(
                        Tags.of("status", result.getStatus()),
                        result.getCount()
                ))
                .collect(Collectors.toList());

        ordersByStatus.register(rows, true);
    }
}
~~~

Trong ví dụ, countByStatus() trả về danh sách projection hoặc DTO có getStatus() và getCount(). Cần bật scheduling trong ứng dụng nếu sử dụng @Scheduled. Khoảng refresh 30 giây chỉ là giá trị minh họa; chọn chu kỳ phù hợp với tốc độ thay đổi dữ liệu và chi phí truy vấn.

Mỗi lần refresh, ứng dụng thực hiện các bước:

1. Lấy snapshot số lượng theo trạng thái.
2. Chuyển từng kết quả thành MultiGauge.Row.
3. Đăng ký toàn bộ row bằng overwrite=true.
4. MultiGauge cập nhật row hiện có, thêm row mới và gỡ row đã biến mất khỏi snapshot.

Không tạo một MultiGauge mới trong mỗi lần refresh. Nếu tạo mới, đối tượng cũ vẫn có thể giữ các row đã đăng ký và việc quản lý vòng đời trở nên khó kiểm soát. Tạo một MultiGauge cho một tập metrics logic rồi tái sử dụng nó.

## 6. Row có thể đọc snapshot hoặc object đang thay đổi

MultiGauge hỗ trợ các kiểu row khác nhau.

**Row từ Number** phù hợp với kết quả truy vấn snapshot:

~~~java
MultiGauge.Row.of(Tags.of("status", "PAID"), 35)
~~~

Giá trị 35 đại diện cho kết quả tại lần đăng ký. Khi số lượng thay đổi, ứng dụng lấy snapshot mới và gọi register(..., true) để cập nhật row.

**Row từ object và hàm lấy giá trị** phù hợp khi muốn Gauge đọc trạng thái từ object:

~~~java
AtomicInteger activeWorkers = new AtomicInteger(4);

MultiGauge.Row.of(
        Tags.of("pool", "email"),
        activeWorkers,
        AtomicInteger::get
)
~~~

Hàm lấy giá trị được gọi khi registry đọc Gauge. Object cần được quản lý vòng đời rõ ràng và giá trị phải có thể đọc an toàn khi nhiều thread cùng hoạt động. MultiGauge giữ các row đã đăng ký; bản thân MultiGauge cũng phải được giữ sống trong suốt thời gian cần báo cáo.

**Row từ Supplier** có thể dùng khi nguồn giá trị là một hàm cung cấp Number:

~~~java
MultiGauge.Row.of(
        Tags.of("pool", "email"),
        () -> activeWorkers.get()
)
~~~

Chọn kiểu row theo ý nghĩa dữ liệu. Nếu nguồn là kết quả GROUP BY vừa truy vấn, Number snapshot thường dễ hiểu và ổn định. Nếu muốn đọc một trạng thái đang thay đổi liên tục từ object, dùng row có object và value function hoặc supplier.

Không nên gọi truy vấn database bên trong value function của từng Gauge. Một lần scrape có thể đọc nhiều row; nếu mỗi row lại chạy một truy vấn riêng, hệ thống giám sát có thể tạo ra tải database không mong muốn. Hãy lấy snapshot một lần, sau đó đăng ký các row từ kết quả đó.

## 7. Chọn tag riêng của row và kiểm soát cardinality

Tag của row xác định danh tính chuỗi thời gian. Một MultiGauge với tag status có thể tạo một series cho mỗi trạng thái. Nếu thêm region, channel và payment_method, số tổ hợp có thể tăng theo tích của số giá trị từng tag.

Ví dụ, 6 trạng thái, 4 vùng và 3 kênh bán hàng có thể tạo đến 6 × 4 × 3 = 72 row cho cùng một metric. Nếu thêm userId hoặc orderId, số row có thể tăng theo số người dùng hoặc đơn hàng và vượt khỏi giới hạn vận hành.

Các tag phù hợp thường có tập giá trị được kiểm soát:

- status: new, paid, shipped, cancelled.
- queue: tên queue đã được khai báo trong cấu hình.
- pool: tên connection pool hoặc worker pool.
- region: vùng triển khai trong danh mục được quản lý.
- outcome: success, failure.

Không dùng các giá trị gần như duy nhất như userId, orderId, requestId, email hoặc URL chứa ID làm tag. MultiGauge hỗ trợ tập row thay đổi, nhưng không có nghĩa nên biến mọi thực thể nghiệp vụ thành một series riêng.

Nên giới hạn rõ nguồn tạo row, chuẩn hóa chữ hoa/chữ thường và loại bỏ các giá trị không thuộc danh mục được phép. Nếu một hệ thống cho phép trạng thái tùy biến không giới hạn, hãy nhóm chúng thành các nhóm có ý nghĩa hoặc dùng log/trace để điều tra chi tiết.

## 8. Tránh row trùng tag và xung đột sau MeterFilter

Trong một lần đăng ký, mỗi row nên có một tổ hợp tag riêng. Nếu hai kết quả cùng có status="PAID", chúng cùng ánh xạ đến một meter ID. Với overwrite=true, row cuối cùng trong thứ tự lặp sẽ được ưu tiên; với overwrite=false, row đầu tiên được ưu tiên.

Tốt nhất là bảo đảm truy vấn nguồn trả đúng một dòng cho mỗi tổ hợp tag. Ví dụ, truy vấn GROUP BY status tự nhiên tạo một dòng cho mỗi trạng thái. Nếu dữ liệu đến từ nhiều nguồn, hãy gộp hoặc chuẩn hóa trước khi tạo row.

Cũng cần chú ý MeterFilter. Filter có thể đổi tên meter, xóa tag hoặc chuẩn hóa tag. Nếu sau khi áp dụng filter, hai row khác nhau ban đầu trở thành cùng một meter ID, chúng sẽ cạnh tranh để đăng ký cùng một Gauge. Hãy kiểm tra cấu hình filter và giữ tổ hợp tag sau biến đổi vẫn duy nhất.

## 9. Kiểm thử MultiGauge

Có thể dùng SimpleMeterRegistry để kiểm tra thêm row, cập nhật giá trị và gỡ row không còn trong snapshot:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Arrays;

import io.micrometer.core.instrument.MultiGauge;
import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class OrderStatusMetricsTest {

    @Test
    void updatesRowsAndRemovesRowsMissingFromSnapshot() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        MultiGauge ordersByStatus = MultiGauge.builder("orders.by.status")
                .register(registry);

        ordersByStatus.register(Arrays.asList(
                MultiGauge.Row.of(Tags.of("status", "NEW"), 12),
                MultiGauge.Row.of(Tags.of("status", "PAID"), 35)
        ), true);

        assertThat(registry.get("orders.by.status")
                .tag("status", "NEW").gauge().value()).isEqualTo(12.0);

        ordersByStatus.register(Arrays.asList(
                MultiGauge.Row.of(Tags.of("status", "NEW"), 8),
                MultiGauge.Row.of(Tags.of("status", "SHIPPED"), 21)
        ), true);

        assertThat(registry.get("orders.by.status")
                .tag("status", "NEW").gauge().value()).isEqualTo(8.0);
        assertThat(registry.get("orders.by.status")
                .tag("status", "SHIPPED").gauge().value()).isEqualTo(21.0);
        assertThat(registry.find("orders.by.status")
                .tag("status", "PAID").gauge()).isNull();

        registry.close();
    }
}
~~~

Kiểm thử này xác nhận:

- Row NEW được cập nhật từ 12 thành 8.
- Row SHIPPED được thêm với giá trị 21.
- Row PAID bị gỡ vì không còn trong snapshot mới.

Có thể bổ sung các tình huống:

- Đăng ký danh sách rỗng hợp lệ và xác nhận các row cũ được gỡ.
- Đăng ký cùng tag với overwrite=false và xác nhận giá trị cũ không bị thay.
- Đăng ký cùng tag với overwrite=true và xác nhận giá trị mới được sử dụng.
- Xác nhận không có row trùng tag trong một snapshot.
- Kiểm tra số lượng row vẫn trong giới hạn cardinality dự kiến.

Để kiểm tra hành vi cập nhật thật từ database, cần có integration test cho repository và lịch refresh. SimpleMeterRegistry chỉ xác minh việc MultiGauge quản lý các row trong bộ nhớ; nó không chứng minh backend Prometheus hoặc OTLP đã nhận và lưu metrics.

## 10. Vận hành chu kỳ refresh an toàn

MultiGauge thường được cập nhật từ một snapshot lấy theo lịch hoặc sau một sự kiện làm thay đổi dữ liệu. Chu kỳ refresh cần cân bằng giữa độ mới của số liệu và tải nguồn dữ liệu.

Một số nguyên tắc:

- Không truy vấn database ở mỗi lần Prometheus scrape; hãy cập nhật MultiGauge theo lịch phù hợp.
- Dùng một lần truy vấn tổng hợp cho cả tập row thay vì truy vấn riêng từng tag.
- Chỉ gọi register sau khi đã lấy được snapshot hoàn chỉnh.
- Phân biệt snapshot hợp lệ rỗng với lỗi truy vấn hoặc lỗi kết nối.
- Giữ một MultiGauge ổn định trong component sống lâu.
- Tránh hai lần refresh chạy đồng thời nếu nguồn dữ liệu và chính sách cập nhật không hỗ trợ điều đó.
- Theo dõi thời điểm refresh thành công và lỗi refresh bằng metrics hoặc log riêng.

Nếu truy vấn lỗi, không nên đăng ký một danh sách rỗng chỉ để tránh giữ số liệu cũ. Danh sách rỗng có nghĩa là tập row hiện tại thực sự không có phần tử và sẽ gỡ các row đã đăng ký. Khi nguồn dữ liệu không sẵn sàng, hãy ghi nhận lỗi refresh, giữ snapshot trước đó hoặc áp dụng chính sách stale-data đã được xác định rõ.

## 11. MultiGauge trong pipeline metrics

MultiGauge hoạt động ở phía instrumentation của ứng dụng. Nó tạo các Gauge riêng lẻ trong MeterRegistry; registry sau đó xuất chúng qua định dạng hoặc giao thức đã cấu hình.

Ví dụ với Prometheus, các row có thể xuất hiện như các series cùng tên và khác tag:

~~~text
# TYPE orders_by_status gauge
orders_by_status{status="NEW"} 8
orders_by_status{status="SHIPPED"} 21
~~~

Prometheus scrape endpoint của ứng dụng và lưu các mẫu theo thời gian. Grafana truy vấn Prometheus để hiển thị số lượng đơn hàng theo trạng thái. MultiGauge không truy vấn dashboard và cũng không phải nơi lưu lịch sử metrics.

Có thể truy vấn tổng số đơn hàng theo các trạng thái được xuất:

~~~promql
sum(orders_by_status)
~~~

Hoặc xem một trạng thái cụ thể:

~~~promql
orders_by_status{status="PAID"}
~~~

Nếu một row bị gỡ khỏi registry do không còn trong snapshot, series đó sẽ ngừng được xuất ở những lần scrape tiếp theo. Backend có thể vẫn giữ lịch sử của series theo chính sách retention riêng. Việc row không còn hiện tại không có nghĩa dữ liệu lịch sử lập tức bị xóa khỏi backend.

## 12. Checklist thiết kế MultiGauge

Trước khi đưa MultiGauge vào production, hãy xác nhận:

- Tập row có giới hạn và mỗi row đại diện cho một nhóm có ý nghĩa vận hành.
- Mỗi row có tổ hợp tag duy nhất sau khi áp dụng MeterFilter.
- MultiGauge được giữ trong field của component có vòng đời phù hợp.
- Snapshot được lấy một lần và chuyển thành danh sách row hoàn chỉnh.
- Dùng overwrite=true khi cần cập nhật giá trị của các row đã tồn tại.
- Row không còn trong snapshot được gỡ theo đúng ý nghĩa dữ liệu.
- Snapshot rỗng hợp lệ được phân biệt với lỗi nguồn dữ liệu.
- Không dùng ID duy nhất hoặc dữ liệu nhạy cảm làm tag.
- Có kiểm thử thêm, cập nhật và gỡ row.
- Đã xác minh metrics được xuất đến registry/backend thực tế.

MultiGauge giúp quản lý một tập Gauge có thành viên thay đổi mà vẫn giữ tên metric và quy ước tag nhất quán. Khi mỗi row có danh tính rõ ràng, snapshot được cập nhật đúng lúc, đối tượng MultiGauge có vòng đời ổn định và cardinality được giới hạn, số liệu theo nhóm sẽ phản ánh trạng thái hiện tại mà không để lại các row cũ hoặc tạo quá nhiều chuỗi thời gian.
