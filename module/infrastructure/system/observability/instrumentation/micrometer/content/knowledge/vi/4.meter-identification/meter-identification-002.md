# Tên, mô tả, đơn vị cơ sở và loại meter

Micrometer cung cấp API thống nhất để ứng dụng Java ghi nhận metrics vận hành, từ số lượt xử lý, trạng thái hàng đợi đến thời gian phản hồi và kích thước dữ liệu. Trong chương Định danh meter, trọng tâm là cách mô tả mỗi phép đo bằng một định danh rõ ràng để người vận hành hiểu nó đo điều gì, hệ thống giám sát phân biệt nó với phép đo khác và backend diễn giải giá trị theo đúng đơn vị.

Một Meter trong Micrometer có một Meter.Id. Định danh này chứa tên, tag, loại meter, description và base unit. Bốn thông tin tên, description, base unit và type trả lời những câu hỏi khác nhau: phép đo được gọi là gì, nó có ý nghĩa gì, giá trị được biểu diễn theo đơn vị nào và nó tuân theo ngữ nghĩa đo lường nào. Tag bổ sung chiều phân loại cho phép đo. Thiết kế nhất quán các trường này giúp metrics dễ tìm, dễ đọc, dễ tổng hợp và an toàn khi vận hành.

Bài học thuộc module OBSERVABILITY_INSTRUMENTATION_MICROMETER. Module này hướng dẫn sử dụng Micrometer để đo lường ứng dụng Java bằng counter, gauge, timer, distribution summary và nhãn có kiểm soát; tích hợp Spring Boot, xuất metrics đến hệ giám sát, kiểm soát cardinality, kiểm thử instrumentation và diễn giải số đo vận hành.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò của Meter.Id trong định danh một meter.
- Đặt tên meter theo quy ước ổn định và dễ tra cứu.
- Viết description mô tả đúng ý nghĩa của phép đo.
- Phân biệt base unit với đơn vị mà API dùng khi ghi nhận dữ liệu.
- Nhận biết các loại meter và hiểu ảnh hưởng của type đến cách diễn giải số đo.
- Dùng tag để phân loại phép đo mà không tạo cardinality không kiểm soát.
- Kiểm tra metadata của meter trong registry và hiểu sự khác nhau giữa tên logic với tên được exporter chuyển đổi.

## 1. Meter và Meter.Id

Meter là abstraction đại diện cho một phép đo trong Micrometer. Một meter thường cung cấp một hoặc nhiều measurement, chẳng hạn giá trị đếm, tổng thời lượng, giá trị hiện tại hoặc phân phối quan sát được.

Mỗi meter có một Meter.Id. Có thể xem Meter.Id là bộ metadata mô tả meter trong registry:

| Trường | Câu hỏi được trả lời | Ý nghĩa |
| --- | --- | --- |
| Name | Phép đo có tên gì? | Tên logic ổn định của metric |
| Tags | Phép đo thuộc chiều phân loại nào? | Các cặp key-value dùng để phân biệt các nhóm dữ liệu |
| Type | Phép đo có ngữ nghĩa gì? | Counter, Gauge, Timer, DistributionSummary và các loại khác |
| Description | Phép đo có ý nghĩa gì? | Mô tả ngắn gọn mục đích và nội dung của số đo |
| Base unit | Giá trị được biểu diễn theo đơn vị cơ sở nào? | Metadata đơn vị, ví dụ bytes hoặc orders |

Tên và tag là phần định danh mà ứng dụng cần thiết kế ổn định. Description và base unit giúp con người cùng backend hiểu dữ liệu. Type cho biết cách diễn giải phép đo. Không nên dùng một trường để thay thế trách nhiệm của trường khác: thêm đơn vị vào description không thay cho base unit; đưa tên môi trường vào name không thay cho tag; và đặt chữ `timer` trong name không biến một Gauge thành Timer.

Ví dụ, meter `checkout.completed` có tag `channel=web` biểu diễn số lượt checkout hoàn tất trên kênh web. Cùng tên đó với tag `channel=mobile` biểu diễn một chuỗi dữ liệu khác. Description có thể là “Số lượt checkout hoàn tất”, base unit có thể là “orders”, còn type là COUNTER.

## 2. Đặt tên meter

Tên meter là nhãn chính để tìm kiếm và truy vấn metrics. Tên nên mô tả đối tượng hoặc hoạt động được đo, có cấu trúc nhất quán giữa các thành phần và giữ ổn định qua các phiên bản ứng dụng.

Một quy ước phổ biến của Micrometer là dùng tên chữ thường, phân tách các thành phần bằng dấu chấm. Ví dụ:

- `checkout.completed`: số lượt checkout hoàn tất.
- `checkout.payment`: thời gian xử lý thanh toán nếu meter được tạo bằng Timer.
- `http.server.requests`: hoạt động request phía máy chủ.
- `queue.depth`: độ sâu hiện tại của hàng đợi.
- `http.request.payload`: kích thước payload của request.

Tên nên trả lời “đang đo hoạt động hoặc đại lượng nào?”. Những chiều như HTTP method, status, route, channel hoặc region thường nên được biểu diễn bằng tag khi chúng có tập giá trị hữu hạn và có ích cho truy vấn.

### Quy tắc đặt tên thực tế

**Dùng một quy ước xuyên suốt.** Nếu một module dùng `checkout.completed`, module khác không nên tự tạo các biến thể như `completed_checkout_count` cho cùng một ý nghĩa nếu không có lý do tương thích rõ ràng.

**Dùng tên mô tả nghiệp vụ hoặc tài nguyên.** Tên `queue.depth` nói rõ đại lượng được đo. Tên `value1` hoặc `metric.temp` không cung cấp ngữ cảnh đủ tốt cho người vận hành.

**Giữ tên ổn định.** Không đưa ID đơn hàng, user ID, request ID, timestamp, URL động hoặc dữ liệu đầu vào vào tên. Các giá trị thay đổi theo từng sự kiện sẽ làm phát sinh nhiều meter khác nhau và gây khó khăn khi truy vấn.

**Không mã hóa chiều phân loại vào tên nếu đó là tag.** Ví dụ, thay vì tạo `http.requests.get`, `http.requests.post`, `http.requests.delete`, hãy cân nhắc dùng một meter `http.requests` với tag `method=GET|POST|DELETE`. Cách này giúp so sánh các nhóm trên cùng một metric.

**Chọn mức chi tiết phù hợp.** Một tên quá chung khiến nhiều phép đo không liên quan bị gom vào cùng một khái niệm; một tên quá cụ thể lại khó tái sử dụng và dễ làm phân mảnh hệ thống metrics.

Ví dụ, một bộ tên có cấu trúc nhất quán:

| Đại lượng | Tên meter | Tag minh họa |
| --- | --- | --- |
| Số checkout hoàn tất | `checkout.completed` | `channel=web` |
| Thời gian thanh toán | `checkout.payment` | `provider=card` |
| Độ sâu hàng đợi | `queue.depth` | `queue=invoice` |
| Kích thước payload | `http.request.payload` | `route=/orders/{id}` |
| Số request lỗi | `http.server.errors` | `status=5xx` |

Tên trong Micrometer là tên logic. Registry hoặc exporter có thể áp dụng NamingConvention để chuyển đổi dấu phân tách, ký tự và hậu tố theo yêu cầu của backend. Ví dụ, backend có thể hiển thị tên dùng dấu gạch dưới hoặc thêm hậu tố đơn vị và loại thống kê. Vì vậy, khi đối chiếu dashboard với mã Java, cần hiểu cả tên logic trong ứng dụng và quy tắc chuyển đổi của registry đang dùng.

## 3. Description: mô tả ý nghĩa phép đo

Description là văn bản ngắn giải thích metric đo điều gì. Nó giúp người đọc dashboard, người xây cảnh báo và người bảo trì mã hiểu được mục đích của meter mà không cần lần ngược toàn bộ code.

Một description tốt nên:

- Mô tả đại lượng được đo và phạm vi của nó.
- Nêu rõ đây là số lượt, giá trị hiện tại, thời lượng hay kích thước.
- Dùng thuật ngữ thống nhất với nghiệp vụ.
- Ngắn gọn, không chứa dữ liệu thay đổi theo từng request.
- Giữ ổn định giữa các instance của cùng một dịch vụ.

Ví dụ:

| Description tốt | Description chưa tốt | Vấn đề |
| --- | --- | --- |
| Số lượt checkout hoàn tất | Checkout | Không rõ là đếm, thời gian hay trạng thái |
| Thời gian xử lý thanh toán | Thời gian | Thiếu đối tượng được đo |
| Số phần tử hiện có trong hàng đợi hóa đơn | Queue metric | Không rõ đại lượng và phạm vi |
| Kích thước payload request tính bằng byte | Payload | Thiếu ý nghĩa và đơn vị |

Description không phải tag. Không đưa `userId`, `orderId`, đường dẫn đầy đủ hoặc giá trị request vào description. Một meter thường được đăng ký một lần và metadata của nó được dùng chung cho các phép đo sau đó; nội dung description phải mô tả metric, không mô tả một sự kiện đơn lẻ.

### Khai báo description bằng builder

Hầu hết builder của meter hỗ trợ khai báo description:

```java
Counter completed = Counter.builder("checkout.completed")
        .description("Số lượt checkout hoàn tất")
        .tag("channel", "web")
        .register(registry);
```

Khai báo description ngay tại nơi định nghĩa meter giúp metadata nằm cạnh tên và tag, giảm nguy cơ các thành phần khác nhau mô tả cùng một metric theo cách không thống nhất.

## 4. Base unit: đơn vị cơ sở của số đo

Base unit mô tả đơn vị mà giá trị đo đại diện. Đơn vị rõ ràng giúp dashboard, truy vấn, cảnh báo và backend hiểu con số đang nói về đại lượng nào.

Một số đơn vị thường gặp:

| Đại lượng | Base unit thường dùng | Ví dụ |
| --- | --- | --- |
| Dung lượng hoặc kích thước dữ liệu | `bytes` | Kích thước payload |
| Thời lượng | `seconds` | Thời gian xử lý |
| Số lượt nghiệp vụ | `orders`, `requests` hoặc đơn vị đếm phù hợp | Số đơn hàng hoàn tất |
| Tỷ lệ | `ratio` hoặc quy ước tỷ lệ của hệ thống | Tỷ lệ cache hit |
| Số phần tử | Đơn vị đếm phù hợp như `tasks` | Độ sâu hàng đợi |

Base unit là metadata mô tả giá trị. Nó không tự động sửa sai dữ liệu do ứng dụng ghi nhận. Nếu ứng dụng ghi số byte nhưng khai báo đơn vị kilobyte, số đo sẽ bị diễn giải sai. Giá trị được ghi và metadata đơn vị phải nhất quán.

### Khai báo base unit

Với các builder hỗ trợ base unit, khai báo đơn vị cùng tên và description:

```java
Counter completed = Counter.builder("checkout.completed")
        .description("Số lượt checkout hoàn tất")
        .baseUnit("orders")
        .register(registry);

DistributionSummary payloadSize =
        DistributionSummary.builder("http.request.payload")
                .description("Kích thước payload của request")
                .baseUnit("bytes")
                .register(registry);
```

Trong ví dụ, Counter đếm số order hoàn tất và DistributionSummary ghi nhận các giá trị kích thước theo byte. Khi ghi dữ liệu, phải truyền giá trị theo đúng đơn vị đã thống nhất:

```java
completed.increment();
payloadSize.record(payload.length);
```

Không chuyển `payload.length` sang kilobyte trong lúc ghi nhưng vẫn khai báo base unit là bytes. Nếu cần biểu diễn một đơn vị khác, hãy chuyển đổi dữ liệu một cách tường minh và cập nhật metadata tương ứng.

### Đơn vị thời gian của Timer

Timer có ngữ nghĩa riêng cho thời lượng. Ứng dụng có thể ghi Duration hoặc giá trị đi kèm TimeUnit; Micrometer chuyển đổi thời gian theo đơn vị phù hợp với registry khi xuất metrics. Ví dụ:

```java
Timer paymentTimer = Timer.builder("checkout.payment")
        .description("Thời gian xử lý thanh toán")
        .register(registry);

paymentTimer.record(Duration.ofMillis(120));
```

Khi đọc tổng thời gian từ Timer, cần chỉ rõ TimeUnit mong muốn:

```java
double totalSeconds = paymentTimer.totalTime(TimeUnit.SECONDS);
```

Không nên tự thêm một tag `unit=ms` cho Timer chỉ để diễn tả đơn vị. Timer đã có ngữ nghĩa thời gian và API chuyển đổi đơn vị. Backend có thể chuẩn hóa hoặc thêm hậu tố đơn vị theo naming convention của nó.

## 5. Type: loại meter và ngữ nghĩa đo lường

Type cho biết meter hoạt động theo ngữ nghĩa nào. Đây là thông tin quan trọng vì cùng một con số có thể mang ý nghĩa khác nhau tùy cách thu thập.

Các loại phổ biến trong Micrometer:

| Type | Ý nghĩa | Measurement thường gặp | Ví dụ |
| --- | --- | --- | --- |
| COUNTER | Bộ đếm tích lũy, chỉ tăng | Giá trị đếm | Số checkout hoàn tất |
| GAUGE | Giá trị tại thời điểm quan sát, có thể tăng hoặc giảm | Giá trị hiện tại | Số tác vụ đang chờ |
| TIMER | Đo thời lượng các lần thực hiện | Count, total time và thống kê phân phối nếu cấu hình | Latency xử lý thanh toán |
| DISTRIBUTION_SUMMARY | Đo phân phối của các giá trị số không phải thời gian | Count, total amount và thống kê phân phối nếu cấu hình | Kích thước payload |
| LONG_TASK_TIMER | Theo dõi tác vụ đang chạy và thời lượng của chúng | Số tác vụ đang hoạt động và thời lượng đang chạy | Tác vụ import dài |
| OTHER | Loại meter tùy biến hoặc không thuộc các nhóm chuẩn trên | Phụ thuộc implementation | Meter tùy biến |

Type được quyết định bởi loại meter được tạo ra. Không thể đổi một Counter thành Gauge chỉ bằng cách đổi tên hoặc description. Ví dụ, `queue.depth` phải là Gauge nếu nó biểu diễn số phần tử hiện tại và có thể giảm khi consumer lấy phần tử ra khỏi hàng đợi.

### Counter

Counter dùng để đếm sự kiện tích lũy. Giá trị tăng khi sự kiện xảy ra:

```java
Counter.builder("checkout.completed")
        .description("Số lượt checkout hoàn tất")
        .baseUnit("orders")
        .register(registry)
        .increment();
```

Counter phù hợp với số lượt hoàn tất, số lần retry hoặc số lỗi đã xảy ra. Không dùng Counter để biểu diễn số kết nối đang mở vì số kết nối có thể tăng và giảm.

### Gauge

Gauge quan sát một giá trị hiện tại:

```java
Gauge.builder("queue.depth", queue, Queue::size)
        .description("Số phần tử hiện có trong hàng đợi")
        .register(registry);
```

Gauge đọc trạng thái tại thời điểm thu thập. Đối tượng được quan sát phải có vòng đời phù hợp và còn được giữ tham chiếu. Nếu đối tượng bị garbage collector thu hồi, Gauge có thể không còn giá trị hữu ích. Không dùng Gauge để cộng dồn các sự kiện đã xảy ra.

### Timer

Timer đo thời lượng và số lần thao tác được ghi nhận. Ngoài count và total time, Timer có thể cung cấp max hoặc thống kê phân phối tùy cấu hình và backend:

```java
Timer paymentTimer = Timer.builder("checkout.payment")
        .description("Thời gian xử lý thanh toán")
        .tag("provider", "card")
        .register(registry);

paymentTimer.record(() -> paymentGateway.charge(order));
```

Timer phù hợp với latency của request, thao tác database, gọi dịch vụ bên ngoài hoặc xử lý nghiệp vụ. Không cần tự ghép Counter và Gauge để mô phỏng một phép đo thời lượng thông thường.

### DistributionSummary

DistributionSummary đo phân phối của các giá trị số không phải thời gian:

```java
DistributionSummary payloadSize =
        DistributionSummary.builder("http.request.payload")
                .description("Kích thước payload của request")
                .baseUnit("bytes")
                .register(registry);

payloadSize.record(payload.length);
```

Nó phù hợp với kích thước payload, số bản ghi trong batch hoặc lượng dữ liệu được xử lý mỗi lần. Nếu giá trị là thời gian, nên dùng Timer để giữ đúng ngữ nghĩa thời lượng.

### LongTaskTimer

LongTaskTimer theo dõi các tác vụ có thể chạy lâu và vẫn đang hoạt động. Nó hữu ích khi cần quan sát thời lượng của các tác vụ chưa hoàn tất, chẳng hạn import dữ liệu hoặc tạo báo cáo. Timer thông thường tập trung ghi nhận một lần thực hiện sau khi thao tác kết thúc; LongTaskTimer còn cung cấp góc nhìn về các tác vụ đang chạy.

## 6. Tag bổ sung chiều định danh

Tag là cặp key-value gắn vào Meter.Id. Một meter có thể có nhiều tag để phân loại số đo theo những chiều ổn định.

Ví dụ:

```java
Counter.builder("checkout.completed")
        .description("Số lượt checkout hoàn tất")
        .tag("channel", "web")
        .tag("region", "north")
        .register(registry);
```

Trong ví dụ, name cho biết đang đếm checkout hoàn tất; tag channel và region cho phép phân tích theo kênh và khu vực. Nếu đổi giá trị tag, registry xem đó là một meter khác trong cùng họ metric.

Tag nên có tập giá trị hữu hạn, dễ hiểu và có ích cho truy vấn. Các giá trị như `method=GET`, `status=2xx`, `channel=web` thường có cardinality có thể kiểm soát. Các giá trị như email, user ID, order ID, session ID, request ID hoặc URL chứa mã tài nguyên thường không phù hợp vì mỗi giá trị mới có thể tạo thêm chuỗi thời gian.

Không đưa các chiều phân loại vào name khi chúng có thể được biểu diễn bằng tag có giới hạn. Đồng thời, không tạo tag chỉ vì dữ liệu có sẵn; mỗi tag làm tăng số tổ hợp meter và chi phí lưu trữ, truy vấn.

## 7. Ví dụ hoàn chỉnh và kiểm tra Meter.Id

Đoạn mã sau đăng ký Counter với name, description, base unit và tag, sau đó đọc metadata từ Meter.Id:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class CheckoutMetrics {

    private final Counter completed;

    public CheckoutMetrics(MeterRegistry registry) {
        this.completed = Counter.builder("checkout.completed")
                .description("Số lượt checkout hoàn tất")
                .baseUnit("orders")
                .tag("channel", "web")
                .register(registry);
    }

    public void checkoutCompleted() {
        completed.increment();
    }

    public Meter.Id meterId() {
        return completed.getId();
    }
}
```

Có thể đọc từng trường của Meter.Id để ghi log phục vụ chẩn đoán:

```java
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.Tag;

Meter.Id id = completed.getId();

String name = id.getName();
String description = id.getDescription();
String baseUnit = id.getBaseUnit();
Meter.Type type = id.getType();
Iterable<Tag> tags = id.getTags();
```

Các trường này giúp xác nhận meter được tạo với metadata mong muốn. Trong ứng dụng thực tế, không cần đọc Meter.Id ở mỗi lần xử lý request. Hãy kiểm tra metadata trong test, lúc khởi tạo hoặc trong công cụ chẩn đoán phù hợp.

### Kiểm thử metadata bằng SimpleMeterRegistry

SimpleMeterRegistry phù hợp để kiểm thử định danh và giá trị của meter mà không cần kết nối backend bên ngoài:

```java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class MeterIdentityTest {

    @Test
    void registersCounterWithExpectedIdentity() {
        var registry = new SimpleMeterRegistry();

        Counter completed = Counter.builder("checkout.completed")
                .description("Số lượt checkout hoàn tất")
                .baseUnit("orders")
                .tag("channel", "web")
                .register(registry);

        Meter.Id id = completed.getId();

        assertThat(id.getName()).isEqualTo("checkout.completed");
        assertThat(id.getDescription())
                .isEqualTo("Số lượt checkout hoàn tất");
        assertThat(id.getBaseUnit()).isEqualTo("orders");
        assertThat(id.getType()).isEqualTo(Meter.Type.COUNTER);
        assertThat(id.getTags())
                .contains(io.micrometer.core.instrument.Tag.of("channel", "web"));

        completed.increment();
        assertThat(completed.count()).isEqualTo(1.0);
    }
}
```

Bài kiểm thử xác nhận tên, description, base unit, type, tag và hành vi đếm. Có thể viết các kiểm thử tương tự cho Gauge, Timer và DistributionSummary để đảm bảo loại meter phù hợp với đại lượng cần quan sát.

## 8. Metadata và backend xuất metrics

Meter.Id mô tả meter ở lớp API Micrometer. Khi metrics được xuất, registry hoặc exporter có thể chuyển đổi tên, đơn vị, tag và cách biểu diễn measurement để phù hợp với backend.

Ví dụ, một Timer có thể được backend biểu diễn thành các trường count và sum, hoặc histogram buckets nếu cấu hình histogram. Tên logic của Timer trong mã Java có thể được chuyển thành tên theo quy tắc Prometheus. Một số backend chuẩn hóa dấu chấm, đổi ký tự hoặc thêm hậu tố đơn vị.

Vì vậy:

- Giữ tên và metadata trong mã Java theo quy ước chung của ứng dụng.
- Dùng đơn vị đúng với dữ liệu thực tế được ghi.
- Kiểm tra quy tắc NamingConvention của registry cụ thể.
- Xem dữ liệu thực tế ở endpoint hoặc backend khi xác minh quá trình export.
- Không suy luận rằng mỗi Meter luôn được backend lưu thành đúng một trường dữ liệu; một số type sinh ra nhiều measurement.

Kiểm thử SimpleMeterRegistry xác nhận instrumentation và Meter.Id ở phía ứng dụng. Nó không chứng minh exporter đã gửi dữ liệu đúng, endpoint đã mở hoặc backend đã nhận và lưu metrics. Các phần đó cần kiểm thử tích hợp phù hợp với registry và hệ giám sát triển khai.

## 9. Những lỗi định danh thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Dùng tên chung như `value` hoặc `metric1` | Khó tìm và hiểu số liệu | Đặt tên theo đối tượng hoặc hoạt động được đo |
| Đưa ID động vào name hoặc tag | Cardinality tăng nhanh | Dùng route template và tập tag hữu hạn |
| Description chỉ ghi tên chung chung | Người vận hành không biết đại lượng | Mô tả rõ số lượt, trạng thái, thời lượng hoặc kích thước |
| Khai báo base unit khác đơn vị dữ liệu | Dashboard và cảnh báo diễn giải sai | Thống nhất đơn vị ghi nhận với metadata |
| Dùng tag `unit=ms` cho Timer | Tạo chiều phân loại không cần thiết và dễ gây hiểu nhầm | Dùng API thời gian của Timer và đơn vị xuất phù hợp |
| Đặt chữ `timer` trong tên rồi tạo Counter | Tên gợi sai ngữ nghĩa | Chọn đúng loại meter từ API |
| Dùng Counter cho trạng thái có thể giảm | Không thể biểu diễn giá trị hiện tại | Dùng Gauge |
| Đưa method hoặc status vào name dù tập giá trị hữu hạn | Tên bị phân mảnh, truy vấn khó tổng hợp | Dùng tag |
| Chỉ kiểm tra tên logic trong code | Có thể không khớp tên hiển thị ở backend | Kiểm tra NamingConvention và dữ liệu export thực tế |

## 10. Checklist thiết kế một meter

Trước khi đăng ký meter, hãy tự trả lời các câu hỏi sau:

1. Đại lượng cần đo là sự kiện tích lũy, trạng thái hiện tại, thời lượng hay phân phối giá trị?
2. Type được chọn có đúng ngữ nghĩa của đại lượng không?
3. Name có ổn định, dễ đọc và theo quy ước của module không?
4. Description có nói rõ meter đo gì và phạm vi nào không?
5. Giá trị được ghi có dùng cùng đơn vị với base unit không?
6. Các tag có tập giá trị hữu hạn và cần thiết cho truy vấn không?
7. Tổ hợp name và tag có thể xung đột với một meter khác hoặc bị đăng ký bằng type không phù hợp không?
8. Đã kiểm tra metadata trong registry và tên thực tế ở backend chưa?

## Kết luận

Một Meter được định danh tốt cần tên ổn định, description dễ hiểu, base unit đúng với dữ liệu và type phản ánh đúng ngữ nghĩa phép đo. Tag bổ sung các chiều phân tích với cardinality có kiểm soát. Meter.Id tập hợp metadata này để registry quản lý meter và exporter chuyển đổi dữ liệu sang định dạng backend.

Khi instrumentation Micrometer được thiết kế theo cùng một quy ước, đội phát triển có thể đọc code và hiểu số đo; đội vận hành có thể tìm metric, xây dashboard và cảnh báo mà không phải đoán đơn vị hoặc ngữ nghĩa.
