# Cập nhật, thay thế và dọn hàng cũ trong MultiGauge theo chính sách rõ ràng

Một số metric cần phản ánh một tập đối tượng thay đổi theo thời gian. Ví dụ, hệ thống có thể muốn công bố số đơn hàng theo trạng thái, số message theo từng queue hoặc số kết nối theo từng pool. Danh sách trạng thái, queue hay pool có thể thay đổi khi cấu hình được cập nhật hoặc khi một đối tượng không còn tồn tại.

Micrometer cung cấp MultiGauge để đăng ký nhiều Gauge có cùng tên nhưng khác tag. Mỗi hàng dữ liệu đầu vào tạo ra một Gauge riêng. Khi tập hàng thay đổi, ứng dụng cần quyết định rõ những hàng cũ sẽ được giữ lại, cập nhật hay xóa. Chính sách này ảnh hưởng trực tiếp đến tính đúng đắn của dashboard và cảnh báo.

## 1. MultiGauge giải quyết bài toán nào?

Gauge thông thường phù hợp khi ứng dụng có một giá trị trạng thái cụ thể cần đọc. MultiGauge phù hợp khi số chiều hoặc số hàng cần theo dõi chỉ được biết tại runtime và có thể thay đổi.

Ví dụ, một truy vấn cơ sở dữ liệu trả về số đơn hàng theo trạng thái:

| status | orders |
| --- | ---: |
| pending | 18 |
| paid | 240 |
| shipped | 72 |

Ứng dụng có thể công bố cùng một metric orders.by.status với tag status khác nhau:

- orders.by.status{status=pending} = 18
- orders.by.status{status=paid} = 240
- orders.by.status{status=shipped} = 72

Khi không còn đơn hàng ở trạng thái pending, truy vấn nguồn có thể không trả về hàng pending. Khi đó, ứng dụng cần quyết định liệu series pending cũ phải biến mất hay vẫn được giữ với giá trị cuối cùng.

MultiGauge giúp quản lý tập Gauge này bằng một lần đăng ký theo danh sách Row. Mỗi Row cung cấp tag và giá trị hoặc đối tượng cùng hàm đọc giá trị.

## 2. Tách meter identity khỏi từng Row

MultiGauge có một định danh meter cơ sở gồm tên, tag chung, description và các thuộc tính cấu hình. Mỗi Row bổ sung tag riêng để tạo định danh cho Gauge con.

Ví dụ:

~~~java
MultiGauge orderCounts = MultiGauge.builder("orders.by.status")
        .description("Number of orders grouped by status")
        .tag("application", "orders-api")
        .register(registry);
~~~

Trong ví dụ, tên orders.by.status và tag application=orders-api là phần chung. Các Row có thể bổ sung status=pending, status=paid hoặc status=shipped.

Định danh của mỗi Gauge con được tạo từ tên meter, tag chung và tag của Row. Vì vậy:

- Các Row phải dùng cùng một schema tag có ý nghĩa nhất quán.
- Tổ hợp tag phải phân biệt được từng hàng cần theo dõi.
- Không tạo hai Row có cùng định danh nhưng mang hai giá trị khác nhau.
- Tên và tag chung nên ổn định trong suốt vòng đời meter.

Nếu hai hàng cùng có status=paid, chúng sẽ trùng định danh. Nếu cần phân biệt theo khu vực, hãy thêm tag region có miền giá trị hữu hạn; không tạo một metric mới cho mỗi bản ghi.

MeterFilter có thể đổi tên meter hoặc loại bỏ/thay đổi tag trước khi registry đăng ký Gauge. Hai Row vốn khác nhau có thể trở thành cùng meter ID sau bước lọc. Hãy kiểm tra tập tag cuối cùng sau filter và tránh cấu hình filter làm mất chiều phân biệt giữa các hàng.

Hãy giữ tham chiếu đến chính đối tượng MultiGauge trong field của bean hoặc component sống đủ lâu. MultiGauge quản lý các Gauge con của nó; nếu đối tượng MultiGauge bị garbage collector thu hồi, các hàng đã đăng ký không được bảo đảm tiếp tục công bố, kể cả khi đối tượng nguồn của từng Row vẫn còn tồn tại.

## 3. Đăng ký tập Row đầu tiên

Ví dụ sau tạo các hàng từ dữ liệu đã tổng hợp:

~~~java
import java.util.List;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.MultiGauge;
import io.micrometer.core.instrument.Tags;
import org.springframework.stereotype.Component;

@Component
public class OrderStatusMetrics {

    private final MultiGauge orderCounts;

    public OrderStatusMetrics(MeterRegistry registry) {
        this.orderCounts = MultiGauge.builder("orders.by.status")
                .description("Number of orders grouped by status")
                .register(registry);
    }

    public void publish(List<OrderStatusCount> counts) {
        List<MultiGauge.Row<?>> rows = counts.stream()
                .map(item -> MultiGauge.Row.of(
                        Tags.of("status", item.status()),
                        item.count()))
                .toList();

        orderCounts.register(rows, true);
    }
}
~~~

Ví dụ dùng record OrderStatusCount với hai trường status và count. Phương thức publish chuyển mỗi kết quả tổng hợp thành một Row, sau đó đăng ký toàn bộ tập hàng.

Đối số boolean thứ hai trong register điều khiển việc thay thế các Row đã tồn tại với cùng định danh tag. Khi đặt true, MultiGauge cập nhật Gauge hiện có để theo dõi giá trị hoặc hàm đọc từ Row mới. Khi đặt false, Gauge đã đăng ký với cùng tag được giữ nguyên, không nhận giá trị mới.

Một điểm cần nhớ: ở cả hai chế độ, những Row đã đăng ký trước đó nhưng không có trong danh sách mới đều bị loại khỏi MultiGauge. Mỗi lần register là một lần đối soát tập Row hiện tại, không phải một thao tác thêm delta. Vì vậy, lựa chọn overwrite không quyết định có dọn hàng vắng mặt hay không; nó chỉ quyết định cách xử lý các hàng trùng định danh.

## 4. Hiểu rõ overwrite=true

Với overwrite=true, các Row có cùng định danh với hàng đã đăng ký được cập nhật theo giá trị hoặc hàm đọc mới. Các hàng đã đăng ký trước đó nhưng không còn trong danh sách mới cũng được dọn khỏi MultiGauge. Đây là lựa chọn phù hợp khi mỗi lần refresh tạo ra snapshot đầy đủ và giá trị cần phản ánh snapshot mới nhất.

Ví dụ:

Lần đầu đăng ký:

~~~java
List<MultiGauge.Row<?>> firstRows = List.of(
        MultiGauge.Row.of(Tags.of("status", "pending"), 18),
        MultiGauge.Row.of(Tags.of("status", "paid"), 240),
        MultiGauge.Row.of(Tags.of("status", "shipped"), 72)
);
orderCounts.register(firstRows, true);
~~~

Lần tiếp theo, không còn đơn pending:

~~~java
List<MultiGauge.Row<?>> currentRows = List.of(
        MultiGauge.Row.of(Tags.of("status", "paid"), 252),
        MultiGauge.Row.of(Tags.of("status", "shipped"), 80)
);
orderCounts.register(currentRows, true);
~~~

Sau lần đăng ký thứ hai, hàng pending cũ được dọn khỏi MultiGauge. Các hàng paid và shipped tiếp tục được công bố với giá trị từ snapshot mới.

Trường hợp tập mới rỗng cũng có ý nghĩa rõ ràng:

~~~java
orderCounts.register(List.of(), true);
~~~

Nếu danh sách rỗng là snapshot đầy đủ và hợp lệ, mọi hàng đã đăng ký trước đó sẽ bị loại bỏ. Việc dọn các hàng vắng mặt cũng xảy ra khi overwrite=false; do đó, không gọi register với danh sách rỗng chỉ vì truy vấn nguồn thất bại.

## 5. Hiểu rõ overwrite=false

Với overwrite=false, MultiGauge giữ nguyên Gauge đã đăng ký nếu Row mới có cùng định danh tag. Giá trị hoặc hàm đọc mới của Row đó không thay thế định nghĩa đang có. Tuy nhiên, những Row cũ không xuất hiện trong danh sách mới vẫn bị dọn. Vì vậy, overwrite=false không biến register thành thao tác cập nhật một phần.

Ví dụ, một tiến trình nhận được Row mới cho trạng thái paid:

~~~java
List<MultiGauge.Row<?>> changedRows = List.of(
        MultiGauge.Row.of(Tags.of("status", "paid"), 252)
);
orderCounts.register(changedRows, false);
~~~

Nếu status=paid đã được đăng ký trước đó, giá trị mới 252 không thay thế giá trị cũ khi overwrite=false. Các hàng khác không có trong danh sách changedRows vẫn bị loại khỏi MultiGauge. Vì vậy, không truyền trực tiếp một delta vào register nếu muốn duy trì toàn bộ tập hiện tại.

Chế độ này hữu ích khi muốn đăng ký một hàng lần đầu và không muốn định nghĩa của một hàng cùng tag bị thay thế bởi lần đăng ký sau. Với dữ liệu snapshot thông thường, overwrite=true thường phù hợp hơn vì nó cập nhật các giá trị hiện tại.

Nếu nguồn phát dữ liệu dạng delta, hãy duy trì trạng thái đầy đủ ở một cấu trúc riêng: áp dụng từng thay đổi vào cấu trúc đó, sau đó gửi toàn bộ tập hiện tại vào register. Khi cần cập nhật giá trị các hàng hiện có, dùng overwrite=true. Nếu chưa thể tạo snapshot đầy đủ, không gọi register cho đến khi có đủ dữ liệu.

## 6. Quyết định chính sách từ ý nghĩa dữ liệu

| Loại đầu vào | Ý nghĩa khi một hàng vắng mặt | Chính sách phù hợp |
| --- | --- | --- |
| Truy vấn tổng hợp trả về toàn bộ trạng thái hiện tại | Hàng vắng mặt nghĩa là trạng thái đó hiện không có dữ liệu; giá trị hàng hiện có cần được cập nhật | overwrite=true |
| Snapshot đầy đủ danh sách queue hoặc pool | Hàng vắng mặt nghĩa là queue hoặc pool đã bị loại bỏ | Gửi toàn bộ snapshot; thường dùng overwrite=true để thay giá trị các hàng còn lại |
| Sự kiện chỉ thông báo các hàng vừa thay đổi | Dữ liệu chưa đại diện cho toàn bộ tập hiện tại | Gộp delta vào state đầy đủ rồi register toàn bộ state |
| Phân trang chưa tải hết dữ liệu | Hàng vắng mặt có thể chỉ nằm ở trang chưa đọc | Chờ tải đủ các trang rồi mới register |
| Truy vấn nguồn thất bại hoặc timeout | Không biết tập hiện tại là gì | Không gọi register; giữ snapshot đã công bố và ghi nhận lỗi |
| Snapshot hợp lệ nhưng không có hàng | Không còn đối tượng nào thuộc tập cần công bố | Gọi register với danh sách rỗng; các hàng cũ sẽ bị dọn |
| Muốn giữ định nghĩa của hàng cùng tag đã đăng ký trước đó | Row mới cùng ID không được thay giá trị hiện tại | Dùng overwrite=false, đồng thời vẫn cung cấp đầy đủ tập Row cần giữ |

Một quy tắc vận hành an toàn: mỗi lần gọi register phải nhận một danh sách đầy đủ các Row cần tiếp tục được công bố. Chỉ gọi khi ứng dụng biết chắc danh sách đầu vào là đầy đủ và việc đọc nguồn đã thành công.

## 7. Không biến lỗi truy vấn thành snapshot rỗng

Một lỗi phổ biến là bắt exception khi đọc dữ liệu rồi thay bằng danh sách rỗng:

~~~java
List<OrderStatusCount> counts;
try {
    counts = repository.countByStatus();
} catch (RuntimeException error) {
    counts = List.of();
}

publish(counts);
~~~

Nếu publish dùng overwrite=true, lỗi cơ sở dữ liệu sẽ khiến tất cả hàng hiện tại bị xóa khỏi MultiGauge. Dashboard có thể trông như không có đơn hàng, trong khi thực tế ứng dụng chỉ không đọc được dữ liệu.

Hãy phân biệt ba trạng thái:

1. **Snapshot thành công và có dữ liệu:** công bố các hàng mới với overwrite=true.
2. **Snapshot thành công nhưng rỗng:** công bố danh sách rỗng với overwrite=true nếu rỗng là trạng thái hợp lệ.
3. **Không lấy được snapshot:** giữ dữ liệu đã công bố trước đó hoặc đánh dấu lỗi thu thập bằng metric riêng; không giả vờ rằng tập hiện tại rỗng.

Ví dụ:

~~~java
public void refresh() {
    List<OrderStatusCount> counts;
    try {
        counts = repository.countByStatus();
    } catch (RuntimeException error) {
        refreshFailures.increment();
        return;
    }

    List<MultiGauge.Row<?>> rows = counts.stream()
            .map(item -> MultiGauge.Row.of(
                    Tags.of("status", item.status()),
                    item.count()))
            .toList();

    orderCounts.register(rows, true);
}
~~~

Trong ví dụ, khi truy vấn thất bại, các hàng đã công bố được giữ nguyên và counter refreshFailures ghi nhận lỗi. Cần có thêm cơ chế quan sát độ mới của dữ liệu, ví dụ thời điểm refresh thành công gần nhất, để dashboard không nhầm giá trị cũ với giá trị hiện tại.

## 8. Thay thế Row khi giá trị thay đổi

Một Row được nhận diện bằng meter ID được tạo từ tên và tập tag. Khi cùng định danh được đăng ký lại, MultiGauge có thể thay thế định nghĩa Gauge hiện có bằng Row mới nếu overwrite=true. Với overwrite=false, định nghĩa đã đăng ký được giữ nguyên. Vì vậy, cần chọn cờ theo ý định cập nhật và không dùng tag-value để nhúng số liệu.

Ví dụ, giá trị pending thay đổi từ 18 thành 25:

~~~java
MultiGauge.Row<?> pendingRow = MultiGauge.Row.of(
        Tags.of("status", "pending"),
        25
);
orderCounts.register(List.of(pendingRow), true);
~~~

Với hàng có cùng tag status=pending, lần đăng ký mới thay giá trị đang theo dõi khi dùng overwrite=true. Nếu dùng overwrite=false, Gauge đã đăng ký vẫn giữ giá trị hoặc hàm đọc trước đó. Những hàng khác không được nhắc đến trong danh sách mới đều bị dọn ở cả hai chế độ. Vì vậy, danh sách truyền vào phải là toàn bộ tập hàng cần tiếp tục công bố.

Khi giá trị của một dimension thay đổi, ví dụ trạng thái cũ waiting được thay bằng queued, định danh tag cũng thay đổi. Hàng waiting cũ không tự trở thành queued; nó là một meter ID khác. Dùng overwrite=true với snapshot đầy đủ để loại hàng waiting nếu nó không còn tồn tại.

## 9. Dùng Row với đối tượng và hàm đọc

Ngoài Row chứa một giá trị Number, MultiGauge còn hỗ trợ Row gắn với đối tượng và hàm chuyển đối tượng thành double. Cách này hữu ích khi cần Gauge đọc một thuộc tính hiện tại từ state holder:

~~~java
QueueState state = queueStates.get(queueName);

MultiGauge.Row<?> row = MultiGauge.Row.of(
        Tags.of("queue", queueName),
        state,
        QueueState::depth
);
~~~

Khi dùng đối tượng làm nguồn đọc, cần giữ tham chiếu mạnh đến state holder trong suốt thời gian Gauge cần hoạt động. Gauge của Micrometer thường dùng weak reference để không giữ đối tượng ứng dụng sống mãi chỉ vì registry đã đăng ký meter.

Nếu Row dùng một giá trị Number đã chụp từ snapshot, giá trị đó đại diện cho lần refresh. Nếu Row dùng object và hàm đọc, Gauge quan sát trạng thái của object khi được scrape. Hai cách có ngữ nghĩa khác nhau; hãy chọn dựa trên nguồn dữ liệu và yêu cầu cập nhật.

## 10. Dọn hàng khi dimension không còn tồn tại

Hãy coi tập Row của MultiGauge như một tập hợp có vòng đời:

- Một dimension xuất hiện lần đầu: tạo Gauge mới.
- Dimension vẫn tồn tại: cập nhật giá trị theo Row mới nếu overwrite=true; với overwrite=false, định nghĩa Gauge đã đăng ký được giữ nguyên.
- Dimension biến mất khỏi danh sách register: xóa Gauge cũ, bất kể overwrite là true hay false.
- Dimension đổi tên: định danh mới xuất hiện và định danh cũ phải được dọn.
- Toàn bộ tập rỗng hợp lệ: xóa mọi hàng cũ bằng snapshot rỗng và overwrite=true.

Không cần tạo metric riêng như orders.pending, orders.paid và orders.shipped nếu những trạng thái đó chỉ là các giá trị của cùng một dimension. Dùng một tên meter và tag status giúp truy vấn, dashboard và alert thống nhất hơn.

## 11. Cardinality và chính sách tag

MultiGauge thuận tiện để biểu diễn tập hàng động, nhưng không có nghĩa số hàng có thể tăng vô hạn. Mỗi tổ hợp tag là một Gauge riêng và có thể tạo một time series riêng ở backend.

Các dimension thường có thể kiểm soát:

- status: pending, paid, shipped, cancelled.
- queue: tên queue được khai báo trong cấu hình.
- pool: tên connection pool của các dịch vụ đã biết.
- region: mã vùng triển khai hữu hạn.
- result_type: success, failure, timeout.

Các dimension rủi ro:

- user_id, customer_id, order_id hoặc request_id.
- Tên file, URL động, SQL text hoặc exception message.
- Tên tenant không giới hạn nếu hệ thống có thể tạo tenant liên tục.
- Giá trị lấy trực tiếp từ input người dùng.

Nếu một hàng tương ứng với từng người dùng hoặc từng đơn hàng, metrics thường không phải nơi phù hợp để lưu từng đối tượng. Dùng log, trace hoặc hệ thống truy vấn nghiệp vụ cho dữ liệu chi tiết. MultiGauge nên đại diện cho các nhóm có ý nghĩa vận hành và tập giá trị được giới hạn.

## 12. Đồng bộ định kỳ và tránh các lần refresh chồng lấn

Một ứng dụng có thể refresh MultiGauge theo lịch, chẳng hạn mỗi 30 giây đọc số lượng theo trạng thái từ cơ sở dữ liệu. Nếu hai lần refresh chạy đồng thời, snapshot cũ có thể ghi đè snapshot mới hoặc dọn hàng vừa được thêm.

Ví dụ tình huống:

1. Refresh A bắt đầu trước và truy vấn chậm.
2. Refresh B bắt đầu sau, lấy snapshot mới hơn và đăng ký trước.
3. Refresh A hoàn tất sau đó và đăng ký snapshot cũ với overwrite=true.
4. Dữ liệu mới bị thay bằng dữ liệu cũ.

Để tránh vấn đề này:

- Chỉ cho phép một refresh chạy tại một thời điểm bằng scheduler không chồng lấn hoặc lock phù hợp.
- Có thể gắn sequence/version cho snapshot và bỏ qua kết quả cũ nếu refresh mới hơn đã được áp dụng.
- Chỉ gọi register sau khi đã đọc và chuẩn hóa xong toàn bộ snapshot.
- Không giữ lock trong lúc thực hiện truy vấn I/O; chỉ đồng bộ phần áp dụng snapshot nếu cần.
- Đặt timeout cho nguồn dữ liệu và theo dõi lỗi refresh.
- Giữ MultiGauge trong một field có vòng đời phù hợp; không tạo biến cục bộ rồi để nó mất tham chiếu sau lần đăng ký.

Nếu dùng nhiều thread để tạo rows, hãy hoàn thành việc xây dựng danh sách trước khi gọi register. Không sửa collection rows trong lúc MultiGauge đang đăng ký.

## 13. Kiểm thử cập nhật và dọn hàng

Có thể dùng SimpleMeterRegistry để kiểm tra chính sách overwrite:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import io.micrometer.core.instrument.MultiGauge;
import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class MultiGaugeTest {

    @Test
    void overwriteControlsReplacementAndMissingRowsAreAlwaysRemoved() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        MultiGauge gauge = MultiGauge.builder("orders.by.status")
                .register(registry);

        gauge.register(List.of(
                MultiGauge.Row.of(Tags.of("status", "pending"), 18),
                MultiGauge.Row.of(Tags.of("status", "paid"), 240)
        ), true);

        assertThat(registry.find("orders.by.status")
                .tag("status", "pending").gauge()).isNotNull();

        gauge.register(List.of(
                MultiGauge.Row.of(Tags.of("status", "paid"), 252)
        ), false);

        assertThat(registry.find("orders.by.status")
                .tag("status", "pending").gauge()).isNull();
        assertThat(registry.find("orders.by.status")
                .tag("status", "paid").gauge().value()).isEqualTo(240.0);

        gauge.register(List.of(
                MultiGauge.Row.of(Tags.of("status", "paid"), 252)
        ), true);

        assertThat(registry.find("orders.by.status")
                .tag("status", "paid").gauge().value()).isEqualTo(252.0);
    }
}
~~~

Nên có thêm các kiểm thử cho những trường hợp:

1. overwrite=false giữ nguyên giá trị của hàng cùng tag đã đăng ký trước đó.
2. overwrite=true thay giá trị của hàng cùng tag bằng Row mới.
3. Hàng vắng mặt bị dọn ở cả hai chế độ overwrite.
4. Snapshot rỗng hợp lệ dọn toàn bộ hàng đã đăng ký.
5. Lỗi truy vấn không gọi register với danh sách rỗng.
6. Một tổ hợp tag không xuất hiện hai lần trong cùng snapshot.
7. Delta được gộp vào state đầy đủ trước khi gọi register.
8. Hai lần refresh không thể áp dụng ngược thứ tự thời gian.

## 14. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng overwrite=false và nghĩ rằng hàng vắng mặt sẽ được giữ | Hàng không có trong danh sách mới vẫn bị dọn; hàng cùng tag thì giữ giá trị cũ. | Gửi toàn bộ tập Row cần giữ; dùng overwrite=true khi cần thay giá trị hiện tại. |
| Truyền delta trực tiếp vào register | Các hàng không có trong delta bị dọn khỏi MultiGauge. | Gộp delta vào state đầy đủ rồi register toàn bộ state. |
| Dùng overwrite=true cho dữ liệu phân trang chưa hoàn tất | Hàng ở trang chưa tải bị dọn. | Chờ tải đủ các trang rồi mới register. |
| Chuyển lỗi truy vấn thành danh sách rỗng | Toàn bộ series hiện tại có thể bị xóa. | Giữ dữ liệu cũ và ghi nhận lỗi refresh. |
| Dùng tag là ID từng bản ghi | Cardinality tăng rất nhanh. | Nhóm theo dimension hữu hạn có ý nghĩa vận hành. |
| Tạo MultiGauge mới mỗi lần refresh | Khó quản lý vòng đời và dễ để lại meter ngoài ý muốn. | Tạo một MultiGauge lâu dài và đăng ký lại các Row. |
| Hai Row có cùng tag | Hai hàng cạnh tranh cùng một meter identity. | Đảm bảo mỗi tổ hợp tag chỉ xuất hiện một lần. |
| Refresh chồng lấn | Snapshot cũ có thể ghi đè hoặc xóa snapshot mới. | Tuần tự hóa hoặc kiểm soát phiên bản snapshot. |
| Nhầm số Row với số sự kiện tích lũy | Chọn sai loại meter và sai cách diễn giải. | Dùng MultiGauge cho trạng thái theo nhóm; dùng Counter cho sự kiện. |

## 15. Checklist thiết kế chính sách MultiGauge

- [ ] Đã xác định mỗi Row đại diện cho dimension nào.
- [ ] Tên meter và tag chung ổn định.
- [ ] Tổ hợp tag của mỗi Row là duy nhất.
- [ ] Miền giá trị tag hữu hạn và không chứa định danh từng bản ghi.
- [ ] Mỗi lần register cung cấp đầy đủ tập Row cần tiếp tục được công bố.
- [ ] overwrite=true được dùng khi giá trị của hàng cùng tag cần thay bằng dữ liệu mới.
- [ ] overwrite=false chỉ được dùng khi muốn giữ nguyên định nghĩa của hàng cùng tag đã đăng ký.
- [ ] Delta được gộp vào state đầy đủ trước khi gọi register.
- [ ] Đã hiểu hàng vắng mặt bị dọn bất kể overwrite là true hay false.
- [ ] Snapshot rỗng được phân biệt với lỗi truy vấn.
- [ ] Mỗi lần refresh áp dụng đúng thứ tự và không ghi đè dữ liệu mới bằng snapshot cũ.
- [ ] Đã kiểm thử cả cập nhật, giữ hàng cũ và dọn hàng cũ.
- [ ] Đã xác minh series thực tế trên registry và backend.

MultiGauge hữu ích khi ứng dụng cần công bố một tập Gauge có dimension thay đổi. Mỗi lần register đối soát tập Row và dọn những hàng vắng mặt; overwrite chỉ quyết định có thay định nghĩa của hàng cùng tag hay giữ nguyên hàng đã đăng ký. Vì vậy, dữ liệu delta phải được gộp thành tập đầy đủ trước khi đăng ký. Phân biệt snapshot rỗng với lỗi thu thập và kiểm soát thứ tự refresh giúp tránh xóa nhầm hoặc giữ lại số liệu lỗi thời.

## Tài liệu tham khảo

- [Micrometer MultiGauge API 1.17.0](https://javadoc.io/static/io.micrometer/micrometer-core/1.17.0/io/micrometer/core/instrument/MultiGauge.html)
- [Micrometer Gauges reference](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html)
