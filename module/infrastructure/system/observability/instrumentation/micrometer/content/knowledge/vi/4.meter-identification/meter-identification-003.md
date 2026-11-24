# Tag, Tags và cách xây dựng tập nhãn nhất quán

Trong Micrometer, một meter thường cần nhiều chiều thông tin để trả lời câu hỏi vận hành: request đến từ khu vực nào, thao tác nào đang chạy, kết quả thành công hay thất bại, hoặc đơn hàng được tạo qua kênh nào. Micrometer biểu diễn các chiều đó bằng **tag**. Một tag là một cặp key/value; tập hợp nhiều tag được dùng khi đăng ký hoặc tra cứu meter.

Thiết kế tags quyết định cách metrics được phân nhóm và truy vấn ở hệ thống nhận. Nếu các meter dùng tên tag và giá trị không nhất quán, dashboard khó so sánh và truy vấn trở nên phức tạp. Nếu tag nhận quá nhiều giá trị khác nhau, số chuỗi thời gian có thể tăng nhanh. Vì vậy, cần xây dựng một quy ước nhãn ổn định, có ý nghĩa nghiệp vụ và giới hạn được cardinality.

## 1. Tag và Tags trong Micrometer

Micrometer cung cấp hai kiểu API cơ bản:

- **Tag** biểu diễn một nhãn đơn, gồm tên khóa (key) và giá trị (value).
- **Tags** biểu diễn một tập hợp các Tag để truyền vào API đăng ký meter. Đây là kiểu collection bất biến; các thao tác kết hợp tạo ra tập Tags mới thay vì sửa tập ban đầu.

Ví dụ:

~~~java
import io.micrometer.core.instrument.Tag;
import io.micrometer.core.instrument.Tags;

Tag region = Tag.of("region", "ap-southeast-1");

Tags dimensions = Tags.of(
    Tag.of("operation", "create"),
    Tag.of("result", "success"),
    region
);
~~~

Có thể tạo Tags trực tiếp từ các cặp key/value:

~~~java
Tags dimensions = Tags.of(
    "operation", "create",
    "result", "success",
    "region", "ap-southeast-1"
);
~~~

Mỗi key cần mô tả một chiều phân loại ổn định; value cho biết meter thuộc nhóm nào trên chiều đó. Trong ví dụ, operation phân loại thao tác, result phân loại kết quả và region phân loại khu vực triển khai hoặc xử lý.

Trong hệ sinh thái metrics, một số backend gọi các cặp này là label. Chẳng hạn, Prometheus biểu diễn tag của Micrometer thành label trên metric được xuất. Trong mã ứng dụng, nên dùng thuật ngữ và API Tag/Tags của Micrometer; backend có thể áp dụng quy tắc tên riêng khi xuất dữ liệu.

## 2. Tags tham gia vào định danh meter như thế nào?

Tên meter mô tả đại lượng được đo, còn tags bổ sung các chiều phân tích. Ví dụ, orders.created là số đơn hàng được tạo; các tags channel=web và result=success xác định nhóm đơn hàng cần quan sát.

Với cùng tên meter, mỗi tổ hợp tags khác nhau có thể tạo thành một chuỗi thời gian riêng ở backend. Có thể hình dung:

~~~text
orders.created{channel="web", result="success"}
orders.created{channel="mobile", result="success"}
orders.created{channel="web", result="failure"}
~~~

Ba chuỗi trên cùng đo số đơn hàng được tạo, nhưng đại diện cho ba nhóm khác nhau. Nhờ vậy, hệ thống giám sát có thể so sánh kênh bán hàng và kết quả xử lý.

Trong Micrometer, khi đăng ký một meter với cùng tên và cùng tags trên cùng registry, ứng dụng thường nhận lại meter đã đăng ký để tiếp tục cập nhật số đo. Vì thế, có thể tra cứu meter theo tags ở mỗi lần xử lý nếu các giá trị thuộc một tập hữu hạn. Nếu giá trị tag thay đổi liên tục theo từng request, mỗi tổ hợp mới có thể làm tăng số meter và chuỗi thời gian.

Không nên dùng tên meter để mã hóa những chiều phân loại có thể biểu diễn bằng tags. Ví dụ, thay vì tạo riêng orders.created.web và orders.created.mobile, nên dùng một meter orders.created với tag channel. Cách này giúp truy vấn và so sánh các nhóm nhất quán hơn.

## 3. Xây dựng tập tags có cấu trúc

Một tập tags tốt có ba đặc điểm:

1. **Ý nghĩa rõ ràng:** mỗi key trả lời một câu hỏi phân tích cụ thể.
2. **Nhất quán:** các meter cùng miền nghiệp vụ dùng chung cách viết key và quy ước value.
3. **Có giới hạn:** mỗi key chỉ nhận một số lượng value hữu hạn, dự đoán được.

Ví dụ một quy ước cho dịch vụ đơn hàng:

| Key | Ý nghĩa | Tập giá trị ví dụ |
| --- | --- | --- |
| service | Dịch vụ tạo ra metric | order-service, payment-service |
| environment | Môi trường chạy | dev, staging, production |
| region | Khu vực triển khai | ap-southeast-1, ap-southeast-2 |
| operation | Thao tác nghiệp vụ | create, cancel, refund |
| result | Kết quả thao tác | success, failure, timeout |
| channel | Kênh tạo đơn | web, mobile, partner, other |

Các key trên chỉ là ví dụ. Một meter không cần mang tất cả các key này. Chỉ thêm chiều dữ liệu khi nó có ích cho câu hỏi vận hành của meter đó. Chẳng hạn, metric về số đơn hàng có thể cần channel và result; metric về kích thước payload có thể chỉ cần operation.

### Quy ước cho key

- Dùng tên ngắn, có ý nghĩa và viết theo một kiểu thống nhất, ví dụ chữ thường với dấu gạch dưới: payment_method, deployment_zone.
- Giữ cùng một key cho cùng một khái niệm trên toàn ứng dụng. Không dùng lúc status, lúc result, lúc outcome nếu cả ba cùng biểu diễn kết quả xử lý.
- Không tạo key động từ dữ liệu request. Key phải được định nghĩa trước trong mã hoặc cấu hình.
- Không đặt tên key theo một backend cụ thể. Micrometer có thể chuyển đổi tên khi xuất qua NamingConvention của registry.

### Quy ước cho value

- Chuẩn hóa chữ hoa/thường, khoảng trắng và cách viết trước khi ghi nhận.
- Dùng tập giá trị hữu hạn, có danh sách hoặc enum rõ ràng.
- Dùng giá trị đại diện như other hoặc unknown cho dữ liệu không nhận diện được.
- Không đưa giá trị null, chuỗi tùy ý hoặc nội dung lỗi tự do vào tag.
- Giữ cùng một ý nghĩa cho một value. Ví dụ, success luôn có nghĩa là thao tác nghiệp vụ hoàn tất thành công, không dùng khi chỗ khác lại có nghĩa là request chỉ được tiếp nhận.

## 4. Dùng Tag và Tags khi đăng ký meter

API của MeterRegistry nhận một tập tags để tìm hoặc đăng ký meter. Ví dụ sau ghi nhận số đơn tạo thành công theo kênh:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Tag;
import io.micrometer.core.instrument.Tags;
import org.springframework.stereotype.Service;

@Service
public class OrderMetrics {

    private final MeterRegistry registry;

    public OrderMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordCreated(String channel) {
        Tags tags = Tags.of(
            Tag.of("channel", normalizeChannel(channel)),
            Tag.of("result", "success")
        );

        Counter counter = registry.counter("orders.created", tags);
        counter.increment();
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

Hàm normalizeChannel chuyển dữ liệu đầu vào thành một trong bốn giá trị đã định nghĩa. Nếu client gửi một chuỗi mới hoặc bất thường, metric vẫn được ghi vào nhóm other thay vì tạo thêm một chuỗi thời gian mới cho mỗi giá trị.

Có thể dùng cùng cách cho Timer:

~~~java
Timer timer = Timer.builder("orders.create.duration")
    .description("Thời gian xử lý thao tác tạo đơn")
    .tags(Tags.of(
        "channel", "web",
        "result", "success"
    ))
    .register(registry);

timer.record(() -> orderRepository.save(order));
~~~

Đoạn mã trên minh họa việc gắn tags khi đăng ký Timer. Trong luồng thực tế, result cần phản ánh kết quả thật của thao tác; nếu thao tác có thể thất bại hoặc timeout, hãy ghi nhận các trường hợp đó bằng nhánh instrumentation tương ứng. Không gắn cố định result=success cho mọi lần thực hiện nếu kết quả có thể thay đổi.

### Kết hợp các tập Tags

Tags có thể được tái sử dụng và kết hợp. Ví dụ, ứng dụng có thể tạo một tập tags chung cho ngữ cảnh nghiệp vụ rồi bổ sung chiều cụ thể:

~~~java
Tags serviceTags = Tags.of(
    "service", "order-service",
    "environment", "production"
);

Tags operationTags = serviceTags.and(
    "operation", "create"
);

Tags successTags = operationTags.and(
    "result", "success"
);
~~~

Các lời gọi and tạo ra tập tags mới. serviceTags vẫn giữ nội dung ban đầu; operationTags và successTags là các tập riêng. Không thêm lặp cùng một key với những value mâu thuẫn trong một meter. Nếu một chiều là thông tin chung của toàn ứng dụng, cân nhắc cấu hình common tags ở registry thay vì tự thêm lại trong từng service.

## 5. Common tags và tags riêng của meter

Common tags là những chiều áp dụng cho hầu hết hoặc toàn bộ metrics trong một ứng dụng, ví dụ service, environment hoặc region. Micrometer cho phép cấu hình chúng ở registry:

~~~java
registry.config().commonTags(
    "service", "order-service",
    "environment", "production"
);
~~~

Trong Spring Boot, có thể cấu hình common tags tập trung qua MeterRegistryCustomizer:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MetricsConfiguration {

    @Bean
    MeterRegistryCustomizer<MeterRegistry> commonTags() {
        return registry -> registry.config().commonTags(
            "service", "order-service",
            "environment", "production"
        );
    }
}
~~~

Common tags giúp mọi metrics có cùng ngữ cảnh triển khai. Tags riêng của meter mô tả chiều đặc thù của phép đo như operation, result hoặc channel.

Trước khi chọn common tags, hãy cân nhắc:

- Giá trị có thực sự giống nhau cho toàn bộ meter trong registry không?
- Có cần chiều này để lọc hoặc phân nhóm metrics trên dashboard không?
- Giá trị có ổn định trong suốt vòng đời tiến trình không?
- Key có bị trùng với tags riêng mà các service sẽ thêm không?

Không nên dùng common tag cho dữ liệu thay đổi theo từng request. Common tags thường được cấu hình một lần lúc khởi tạo registry; chúng không phải nơi truyền thông tin của request hiện tại.

## 6. Cardinality và tác động của tập tags

Cardinality là số tổ hợp nhãn khác nhau được tạo ra cho một metric. Mỗi tổ hợp tên metric và tags thường tương ứng với một chuỗi thời gian riêng ở backend.

Giả sử metric orders.created có các chiều:

- channel có 4 giá trị.
- result có 3 giá trị.
- region có 2 giá trị.

Nếu mọi tổ hợp đều xuất hiện, metric có thể tạo tối đa:

\[
4 \times 3 \times 2 = 24
\]

chuỗi thời gian. Khi thêm customerId với hàng trăm nghìn giá trị, số chuỗi có thể tăng rất lớn. Các histogram còn có thể xuất nhiều chuỗi bổ sung cho bucket, count và sum tùy registry và backend.

| Tag có cardinality thấp | Tag có cardinality cao |
| --- | --- |
| result=success/failure/timeout | request_id với giá trị gần như duy nhất mỗi request |
| channel=web/mobile/partner | customer_id với một giá trị cho mỗi khách hàng |
| method=GET/POST/PUT/DELETE | URL thô có path chứa ID tài nguyên |
| region=ap-southeast-1/ap-southeast-2 | email, session ID hoặc mã đơn hàng |

Tags có cardinality cao làm tăng:

- Số meter và bộ nhớ cần quản lý trong tiến trình ứng dụng.
- Số chuỗi thời gian và dung lượng lưu trữ ở backend.
- Chi phí thu thập, truyền dữ liệu và truy vấn.
- Độ phức tạp khi xây dựng dashboard và cảnh báo.

Hãy đưa dữ liệu định danh một request hoặc một thực thể cụ thể vào trace hoặc log khi cần điều tra chi tiết. Metrics phù hợp hơn với số liệu tổng hợp theo những chiều có giới hạn.

### Chuẩn hóa route thay vì dùng URL thực tế

Với HTTP server metrics, không dùng URL chứa ID thực tế như /orders/839201 làm tag. Hãy dùng route template /orders/{id}. Các request thuộc cùng endpoint khi đó được gom vào một nhóm, trong khi vẫn giữ được thông tin route cần cho phân tích.

Tương tự, không đưa exception message, SQL query, token, địa chỉ email hoặc nội dung do người dùng nhập vào tags. Những giá trị này khó giới hạn và thường không phải chiều tổng hợp phù hợp.

## 7. Bảo vệ registry bằng MeterFilter

Thiết kế tags trong mã là lớp kiểm soát đầu tiên. Có thể bổ sung MeterFilter để giới hạn số giá trị của một tag cho nhóm meter nhất định:

~~~java
import io.micrometer.core.instrument.config.MeterFilter;

registry.config().meterFilter(
    MeterFilter.maximumAllowableTags(
        "orders.",
        "channel",
        4,
        MeterFilter.deny()
    )
);
~~~

Ví dụ này giới hạn tối đa bốn giá trị khác nhau cho tag channel của các meter có tên bắt đầu bằng orders. Khi vượt ngưỡng, filter được cấu hình để từ chối meter mới có tag value vượt giới hạn.

Hãy cài đặt filter trong giai đoạn cấu hình registry, trước khi các meter liên quan được đăng ký. Chọn ngưỡng dựa trên danh sách giá trị hợp lệ đã thiết kế. Filter là lớp bảo vệ bổ sung; nó không thay thế việc chuẩn hóa dữ liệu đầu vào và cũng không xóa các chuỗi thời gian đã được backend lưu trước đó.

## 8. Duy trì quy ước tags nhất quán

Trong ứng dụng có nhiều service hoặc nhiều nhóm phát triển, quy ước tags cần được quản lý như một phần của hợp đồng metrics.

Một cách tổ chức thực tế:

1. Tạo danh mục key dùng chung, ghi rõ ý nghĩa, kiểu dữ liệu và tập value hợp lệ.
2. Dùng enum hoặc hàm chuẩn hóa để chuyển dữ liệu đầu vào sang value chuẩn.
3. Định nghĩa helper hoặc component metrics cho các nhóm nghiệp vụ dùng chung.
4. Dùng common tags cho ngữ cảnh triển khai ổn định.
5. Dùng tags riêng cho chiều phân tích của từng meter.
6. Review cardinality trước khi thêm tag mới vào metric được xuất thường xuyên.

Ví dụ một helper cho kết quả xử lý:

~~~java
public enum OperationResult {
    SUCCESS("success"),
    FAILURE("failure"),
    TIMEOUT("timeout");

    private final String tagValue;

    OperationResult(String tagValue) {
        this.tagValue = tagValue;
    }

    public String tagValue() {
        return tagValue;
    }
}
~~~

Khi ghi nhận metric, dùng tagValue() để mọi nơi cùng biểu diễn kết quả theo một bộ giá trị:

~~~java
Tags tags = Tags.of(
    "operation", "create",
    "result", result.tagValue()
);

registry.counter("orders.operation", tags).increment();
~~~

Không cần ép mọi metric trong ứng dụng dùng cùng một tập tags. Điều cần thống nhất là cùng một key phải có cùng ý nghĩa, cùng một khái niệm phải dùng cùng cách đặt tên, và mỗi meter chỉ mang những chiều có ích cho việc phân tích nó.

## 9. Kiểm thử tập tags

Có thể dùng SimpleMeterRegistry để kiểm tra meter được đăng ký với đúng tên và tags, không cần khởi động backend:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

SimpleMeterRegistry registry = new SimpleMeterRegistry();
Tags tags = Tags.of(
    "channel", "web",
    "result", "success"
);

Counter counter = registry.counter("orders.created", tags);
counter.increment();

assertThat(counter.count()).isEqualTo(1.0);
assertThat(counter.getId().getTag("channel")).isEqualTo("web");
assertThat(counter.getId().getTag("result")).isEqualTo("success");
~~~

Các kiểm thử hữu ích nên bao gồm:

- Giá trị đầu vào hợp lệ được ánh xạ sang đúng tag value.
- Giá trị null hoặc ngoài danh sách được chuyển thành other hoặc unknown.
- Cùng một khái niệm dùng cùng key và value trên các meter liên quan.
- Không có ID, URL thô hoặc dữ liệu tự do lọt vào tags.
- Các tổ hợp tags nằm trong giới hạn cardinality đã dự kiến.
- Common tags xuất hiện trên meter được đăng ký qua registry đã cấu hình.

Kiểm thử SimpleMeterRegistry xác nhận hành vi đăng ký và ghi nhận trong ứng dụng. Muốn xác minh tên label sau khi chuyển đổi hoặc dữ liệu đến backend, cần kiểm tra endpoint export và cấu hình của registry đích.

## 10. Checklist khi thiết kế tag mới

Trước khi thêm một tag vào meter, hãy trả lời:

- Tag này giúp trả lời câu hỏi vận hành nào?
- Key đã tồn tại với cùng ý nghĩa ở nơi khác chưa?
- Value có tập hữu hạn và có thể chuẩn hóa không?
- Số tổ hợp tags tối đa dự kiến là bao nhiêu?
- Có thể dùng route template, enum hoặc nhóm giá trị thay cho dữ liệu thô không?
- Đây là chiều chung của toàn ứng dụng hay chỉ áp dụng cho meter này?
- Có cần thêm kiểm thử hoặc MeterFilter để bảo vệ cardinality không?

Tag và Tags là cơ chế đơn giản để phân nhóm metrics, nhưng chất lượng của dữ liệu phụ thuộc vào quy ước mà ứng dụng áp dụng. Một tập nhãn nhỏ, rõ nghĩa và nhất quán giúp dashboard dễ đọc, truy vấn dễ viết và chi phí giám sát có thể dự đoán. Hãy xem mỗi tag như một phần của hợp đồng dữ liệu vận hành: xác định ý nghĩa trước, giới hạn giá trị, dùng thống nhất và kiểm thử trước khi đưa vào production.
