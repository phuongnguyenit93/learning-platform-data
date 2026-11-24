# Đặt tên observation ổn định

Trong module `SPRING_BOOT_OBSERVABILITY`, ứng dụng Spring Boot dùng Micrometer Observation làm điểm chung để ghi nhận hoạt động, sau đó chuyển dữ liệu thành metrics, logs và distributed traces. Các tín hiệu này giúp đội ngũ theo dõi hành vi ứng dụng, phát hiện lỗi và điều tra độ trễ trên môi trường thực. Để các tín hiệu có thể được tổng hợp và so sánh qua nhiều lần triển khai, mỗi observation cần một tên ổn định, có ý nghĩa và không phụ thuộc vào dữ liệu của từng request.

Tên observation là một phần của thiết kế kiến trúc observability. Nếu tên thay đổi theo mã đơn hàng, URL thực tế hoặc tên người dùng, cùng một thao tác nghiệp vụ sẽ bị chia thành nhiều nhóm dữ liệu. Metrics khó tổng hợp, dashboard mất tính liên tục và việc so sánh trước sau khi phát hành trở nên thiếu tin cậy. Ngược lại, tên mô tả đúng loại thao tác giúp metrics và traces kể cùng một câu chuyện dù ứng dụng chạy ở instance, phiên bản hay môi trường nào.

## 1. Observation name có vai trò gì?

Một observation biểu diễn một hoạt động mà hệ thống muốn đo lường hoặc quan sát, chẳng hạn xử lý một yêu cầu HTTP, gọi một dịch vụ bên ngoài, truy vấn dữ liệu hoặc thực hiện một thao tác nghiệp vụ. Trong Spring Boot, nhiều thành phần đã được instrument sẵn. Với các luồng nghiệp vụ riêng, ứng dụng có thể tạo observation bằng Micrometer Observation API hoặc dùng annotation `@Observed`.

`ObservationRegistry` tiếp nhận observation và điều phối các handler đã đăng ký. Tùy cấu hình, một observation có thể được chuyển thành timer hoặc meter, span trong hệ thống tracing, hay thông tin phục vụ liên kết logs với trace. Observation name là định danh chung mà các handler sử dụng để nhận biết loại hoạt động.

Ví dụ, thao tác giữ chỗ hàng tồn kho có thể mang tên:

```text
inventory.reservation.create
```

Tên này mô tả loại công việc đang diễn ra. Nó không phụ thuộc vào mã đơn hàng, mã sản phẩm, người gọi hay kết quả cụ thể của lần thực thi. Vì vậy, mọi lần tạo reservation đều có thể được tổng hợp dưới cùng một tên.

Nên phân biệt bốn thành phần sau:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Observation name | Định danh ổn định của loại hoạt động | `inventory.reservation.create` |
| Contextual name | Tên dễ đọc, cung cấp ngữ cảnh cho người xem trace | `create inventory reservation` |
| Low-cardinality key-value | Thuộc tính có tập giá trị hữu hạn, phù hợp để phân nhóm metrics | `inventory.channel=web` |
| High-cardinality key-value | Thuộc tính có nhiều giá trị khác nhau, hữu ích khi điều tra một trace cụ thể | `order.id=ORD-84219` |

Observation name trả lời câu hỏi “đây là loại hoạt động nào?”. Contextual name giúp người đọc hiểu hoạt động đó trong trace. Các key-value mô tả thêm đặc điểm của một lần thực thi. Không nên đưa tất cả thông tin vào tên observation.

## 2. Quy tắc đặt tên ổn định

Một quy ước đơn giản và dễ mở rộng là:

```text
<domain>.<capability>.<operation>
```

Trong đó:

- `domain` là miền nghiệp vụ hoặc thành phần sở hữu hoạt động, ví dụ `inventory`, `payment`, `checkout`.
- `capability` là năng lực hoặc tài nguyên đang được xử lý, ví dụ `reservation`, `authorization`, `order`.
- `operation` mô tả hành động có ý nghĩa, ví dụ `create`, `confirm`, `cancel`, `lookup`.

Không phải observation nào cũng cần đủ ba phần. Nếu tên ngắn hơn vẫn thể hiện rõ ý nghĩa và tuân theo quy ước chung của hệ thống, có thể dùng `payment.authorization` hoặc `catalog.product.lookup`. Điều quan trọng là các nhóm phát triển sử dụng cùng một cấu trúc, cùng cách viết và cùng mức độ chi tiết.

Áp dụng các nguyên tắc sau:

1. **Dùng danh từ và động từ mô tả nghiệp vụ.** Chọn tên theo hoạt động mà hệ thống thực hiện, không theo tên class hoặc method hiện tại. `payment.authorization` có ý nghĩa lâu dài hơn `PaymentService.authorizeV2`.
2. **Dùng chữ thường và dấu chấm để phân cấp.** Ví dụ `checkout.order.submit`. Tránh trộn lẫn camelCase, dấu gạch dưới và dấu cách giữa các tên.
3. **Giữ tên độc lập với dữ liệu runtime.** Không nối mã đơn hàng, mã khách hàng, địa chỉ IP, URL đầy đủ, query string hay giá trị đầu vào vào tên.
4. **Giữ cùng một ý nghĩa qua các lần triển khai.** Đổi tên method, package hoặc cấu trúc class không nhất thiết làm thay đổi observation name.
5. **Chọn đúng ranh giới hoạt động.** Tạo observation cho một thao tác có ý nghĩa về hiệu năng hoặc nghiệp vụ. Không cần tạo observation cho mọi getter, setter hoặc helper nhỏ.
6. **Dùng tên nhất quán giữa các đường gọi.** Cùng một thao tác tạo reservation nên có cùng tên dù được gọi từ REST controller, message consumer hay scheduled job.

Tên nên đủ cụ thể để phân biệt các thao tác có đặc tính vận hành khác nhau, nhưng không chia nhỏ đến mức mỗi biến thể dữ liệu tạo ra một tên mới. Ví dụ, `payment.authorization` và `payment.refund` là hai hoạt động khác nhau. Trong khi đó, `payment.authorization.card` và `payment.authorization.bank` chỉ nên là hai tên riêng nếu chúng thực sự là hai luồng có vòng đời và mục tiêu đo lường khác nhau. Nếu chỉ là hai phương thức thanh toán trong cùng một hoạt động, hãy giữ một tên và đưa phương thức vào tag có tập giá trị hữu hạn.

## 3. Những tên dễ gây cardinality bùng nổ

Cardinality là số lượng chuỗi thời gian hoặc nhóm dữ liệu khác nhau được tạo ra từ tên metric và các tag. Một tên observation thay đổi liên tục có thể khiến hệ thống metrics tạo ra rất nhiều chuỗi riêng lẻ. Điều này làm tăng dung lượng lưu trữ, chi phí truy vấn và tải lên backend observability.

| Không nên dùng | Nên dùng | Lý do |
| --- | --- | --- |
| `order.ORD-84219.submit` | `checkout.order.submit` | Mã đơn hàng thay đổi theo từng request |
| `http.server./orders/84219` | `http.server.requests` hoặc tên nghiệp vụ ổn định | URL thực tế chứa ID động |
| `payment.authorize.customer-91` | `payment.authorization` | Mã khách hàng không phải một phần của loại hoạt động |
| `inventory.reserve.sku-ABC-001` | `inventory.reservation.create` | SKU có thể có rất nhiều giá trị |
| `db.query.SELECT-...-timestamp` | Tên observation truy vấn có cấu trúc ổn định | SQL hoặc timestamp động làm phân mảnh dữ liệu |
| `external.call.` kèm host hoặc URL đầy đủ | `partner.api.request` | Host và endpoint nên được biểu diễn bằng thuộc tính có kiểm soát |

Tên chứa dữ liệu động thường xuất hiện khi ghép chuỗi trực tiếp:

```java
// Không nên: mỗi orderId có thể tạo ra một observation name khác nhau.
String observationName = "order." + orderId + ".submit";
```

Thay vào đó, giữ tên cố định và phân loại dữ liệu bằng key-value phù hợp:

```java
Observation.createNotStarted("checkout.order.submit", observationRegistry)
    .highCardinalityKeyValue("order.id", orderId)
    .observe(() -> orderService.submit(orderId));
```

Trong ví dụ này, `checkout.order.submit` giữ vai trò định danh ổn định. `order.id` là thuộc tính của lần thực thi và được khai báo ở nhóm high-cardinality. Việc handler nào xuất dữ liệu này ra backend nào phụ thuộc cấu hình; không nên mặc định rằng mọi high-cardinality key-value đều được ghi thành metric label.

## 4. Phân biệt low-cardinality và high-cardinality tags

Sau khi đặt observation name, hãy chọn tag theo số lượng giá trị có thể xuất hiện và mục đích sử dụng.

**Low-cardinality** phù hợp với thuộc tính có tập giá trị hữu hạn, được kiểm soát, chẳng hạn:

- `payment.method`: `card`, `bank_transfer`, `wallet`.
- `operation.outcome`: `success`, `failure`, `rejected`.
- `inventory.channel`: `web`, `mobile`, `partner`.
- `region`: các mã vùng đã được định nghĩa trước.

Các thuộc tính này hữu ích khi nhóm và so sánh metrics. Trước khi thêm một tag, hãy xác định tập giá trị hợp lệ. Nếu giá trị có thể tăng theo số khách hàng, đơn hàng, request hoặc phiên làm việc, tag đó không phải low-cardinality.

**High-cardinality** dành cho thông tin có nhiều giá trị, thường hữu ích khi truy tìm một lần thực thi cụ thể trong trace:

- `order.id`.
- `request.id`.
- `reservation.id`.

Không dùng high-cardinality key-value như một cách né tránh kiểm soát dữ liệu. Tracing backend vẫn có chi phí lưu trữ và truy vấn. Chỉ ghi các định danh thực sự cần cho điều tra, áp dụng chính sách lưu trữ phù hợp và tránh dữ liệu nhạy cảm như access token, mật khẩu, email, số điện thoại hoặc thông tin thanh toán.

Không nên đưa dữ liệu có cardinality cao vào low-cardinality tags. Ví dụ, `customer.id` có thể có hàng triệu giá trị; dùng nó làm metric label sẽ tạo ra lượng chuỗi thời gian lớn và khó vận hành. Nếu cần liên kết đến một khách hàng trong một trace, hãy đánh giá việc ghi định danh đó như high-cardinality attribute theo chính sách bảo mật của hệ thống.

## 5. Tạo observation trong Spring Boot

Với một thao tác nghiệp vụ, có thể tạo observation trực tiếp bằng `ObservationRegistry`. Ví dụ sau minh họa việc đặt tên ổn định cho thao tác tạo reservation. Kênh bán hàng có tập giá trị hữu hạn nên được ghi dưới dạng low-cardinality; mã đơn hàng được giữ như một thuộc tính high-cardinality để hỗ trợ điều tra trace.

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.util.Locale;
import org.springframework.stereotype.Service;

@Service
public class ReservationService {

    private final ObservationRegistry observationRegistry;
    private final InventoryRepository inventoryRepository;

    public ReservationService(
            ObservationRegistry observationRegistry,
            InventoryRepository inventoryRepository) {
        this.observationRegistry = observationRegistry;
        this.inventoryRepository = inventoryRepository;
    }

    public Reservation reserve(
            String orderId,
            String sku,
            int quantity,
            SalesChannel channel) {

        return Observation
                .createNotStarted("inventory.reservation.create", observationRegistry)
                .contextualName("create inventory reservation")
                .lowCardinalityKeyValue(
                        "inventory.channel", channel.name().toLowerCase(Locale.ROOT))
                .highCardinalityKeyValue("order.id", orderId)
                .observe(() -> inventoryRepository.reserve(orderId, sku, quantity));
    }
}
```

Ở đây, observation name không chứa `orderId`, `sku` hay `channel`. Tên giữ nguyên cho mọi lần tạo reservation. Contextual name giúp trace dễ đọc hơn. `inventory.channel` hỗ trợ phân nhóm theo một tập giá trị được kiểm soát; `order.id` giúp truy vết một đơn hàng khi backend tracing hỗ trợ thuộc tính này.

Ví dụ trên dùng `String` cho kênh để giữ phần minh họa ngắn gọn. Trong mã thực tế, nên chuẩn hóa giá trị enum một cách nhất quán, chẳng hạn dùng `Locale.ROOT` khi chuyển chữ thường, và bảo đảm enum không có giá trị do người dùng tự do nhập.

Nếu dùng annotation, `@Observed` giúp gắn observation vào method:

```java
import io.micrometer.observation.annotation.Observed;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    @Observed(
            name = "payment.authorization",
            contextualName = "authorize payment")
    public PaymentResult authorize(PaymentCommand command) {
        // Thực hiện xác thực và ủy quyền thanh toán.
        return paymentGateway.authorize(command);
    }
}
```

Để annotation hoạt động, ứng dụng cần đăng ký `ObservedAspect` với `ObservationRegistry`. Một cấu hình điển hình là:

```java
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.aop.ObservedAspect;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ObservabilityConfiguration {

    @Bean
    ObservedAspect observedAspect(ObservationRegistry observationRegistry) {
        return new ObservedAspect(observationRegistry);
    }
}
```

Ứng dụng cũng cần cấu hình AOP phù hợp để Spring áp dụng aspect. Với cách proxy AOP, lời gọi nội bộ từ một method sang method khác trong cùng instance không đi qua proxy; vì vậy không nên dựa vào `@Observed` trên method nội bộ để tạo observation. Hãy đặt annotation ở ranh giới bean được gọi qua Spring proxy hoặc dùng Observation API trực tiếp khi cần kiểm soát rõ vòng đời.

Chọn một cách instrument cho mỗi ranh giới. Nếu một method vừa được bao bởi `@Observed` vừa tự tạo observation cùng mục đích, trace có thể xuất hiện hai span lồng nhau và metrics bị đếm trùng. Observation lồng nhau chỉ nên được tạo khi mỗi lớp thực sự đại diện cho một hoạt động riêng có giá trị điều tra.

## 6. Giữ tên nhất quán với instrumentation có sẵn

Spring Boot và các thư viện Micrometer có thể tự tạo observation cho HTTP server, HTTP client, truy cập dữ liệu và các thành phần được hỗ trợ. Nên tận dụng instrumentation có sẵn trước khi bổ sung observation thủ công. Nếu framework đã đo một request HTTP, không cần tạo một observation thứ hai chỉ để ghi lại cùng vòng đời request.

Observation nghiệp vụ nên bổ sung góc nhìn mà instrumentation kỹ thuật chưa thể hiện. Chẳng hạn, HTTP observation cho biết request đi vào endpoint nào và mất bao lâu; `checkout.order.submit` cho biết hệ thống đang thực hiện thao tác nghiệp vụ nào bên trong request đó.

Không đổi tên observation mặc định của framework một cách tùy tiện. Tên chuẩn có thể được dashboard, alert, exporter hoặc công cụ tracing dựa vào. Nếu cần điều chỉnh cách biểu diễn, hãy kiểm tra convention và cấu hình tương ứng của phiên bản Spring Boot/Micrometer đang dùng, đồng thời đánh giá ảnh hưởng đến các hệ thống tiêu thụ dữ liệu.

Với các observation tự định nghĩa, nên duy trì một danh mục tên trong nhóm phát triển. Danh mục có thể ghi tên, ý nghĩa, vị trí instrument, các low-cardinality tags được phép và chủ sở hữu. Việc này giúp tránh trường hợp hai nhóm dùng hai tên khác nhau cho cùng một thao tác hoặc dùng cùng một tên cho hai hoạt động khác nghĩa.

## 7. Kiểm chứng tên observation

Sau khi thêm observation, cần kiểm tra cả ý nghĩa lẫn dữ liệu thực tế được xuất ra:

1. **Kiểm tra tên trong mã nguồn.** Tên phải cố định, mô tả đúng thao tác và không chứa dữ liệu đầu vào. Tìm các đoạn nối chuỗi để phát hiện tên được tạo động.
2. **Gọi thao tác với nhiều bộ dữ liệu.** Ví dụ tạo reservation cho nhiều đơn hàng, SKU và kênh. Tất cả lần gọi của cùng một thao tác phải giữ chung observation name.
3. **Kiểm tra metrics.** Xem tên meter và tập tag được exporter/backend nhận. Đảm bảo các chiều phân nhóm đều có miền giá trị hữu hạn và không có ID động trong metric labels.
4. **Kiểm tra trace.** Xác nhận span có tên dễ hiểu, các span con thể hiện đúng quan hệ cha-con và thuộc tính cần thiết xuất hiện ở đúng nơi.
5. **Kiểm tra logs và liên kết tín hiệu.** Khi ứng dụng ghi log trong phạm vi observation, kiểm tra trace ID/span ID được liên kết theo cấu hình logging và context propagation của ứng dụng.
6. **Theo dõi cardinality sau triển khai.** Quan sát số lượng chuỗi thời gian, số lượng tag values và chi phí ingest. Nếu cardinality tăng bất thường, tìm tag hoặc tên chứa dữ liệu động.

Tên observation không bảo đảm rằng mọi backend đều xuất dữ liệu theo cùng một tên hoặc cùng một cấu trúc. Handler, convention, registry và exporter có thể ánh xạ observation thành meter hoặc span theo cách riêng. Vì vậy, hãy kiểm tra dữ liệu ở đầu ra thực tế thay vì chỉ suy luận từ tên trong mã nguồn.

Đối với luồng bất đồng bộ, cần kiểm tra cả việc truyền context qua executor, message broker hoặc ranh giới thread. Tên observation có thể đúng nhưng trace vẫn bị đứt nếu context không được propagation. Đây là vấn đề riêng với việc đặt tên, song cần được xác minh để các span của cùng một thao tác có thể liên kết chính xác.

## 8. Quản lý thay đổi tên theo thời gian

Khi observation name đã được dùng trong metrics, traces, dashboard hoặc alert, hãy xem nó như một phần của hợp đồng dữ liệu vận hành. Việc đổi tên có thể tạo ra một chuỗi metric mới, khiến biểu đồ lịch sử bị chia đoạn và làm alert không còn khớp với dữ liệu trước đó.

Đổi tên method hoặc tái cấu trúc package không phải lý do đủ để đổi observation name. Giữ tên nếu ý nghĩa nghiệp vụ và ranh giới đo lường vẫn giống nhau. Nếu ý nghĩa của hoạt động thay đổi đáng kể, có thể cần một tên mới; khi đó hãy cập nhật dashboard, alert, tài liệu vận hành và kế hoạch chuyển đổi dữ liệu liên quan.

Trước khi đưa một tên mới vào production, hãy rà soát:

- Tên có mô tả một hoạt động rõ ràng và có thể giữ ổn định qua nhiều phiên bản không?
- Tên có chứa ID, URL, query, dữ liệu người dùng hoặc giá trị runtime không?
- Những thuộc tính nào là low-cardinality và tập giá trị của chúng có được kiểm soát không?
- Thuộc tính high-cardinality có thật sự cần cho điều tra trace và có tuân thủ chính sách dữ liệu không?
- Observation có trùng với instrumentation mặc định hoặc observation ở lớp khác không?
- Dashboard, alert và truy vấn hiện có có phụ thuộc vào tên này không?

Một quy ước đặt tên tốt giúp metrics duy trì cardinality có thể kiểm soát, traces dễ đọc và logs có thể liên kết với đúng hoạt động. Với Spring Boot và Micrometer Observation, hãy giữ observation name cố định theo nghiệp vụ, dùng contextual name để tăng khả năng đọc, và đặt dữ liệu biến thiên vào key-value phù hợp. Khi tuân thủ các nguyên tắc này, đội ngũ có thể theo dõi cùng một hoạt động xuyên suốt các lớp ứng dụng và các lần triển khai mà không làm mất tính liên tục của dữ liệu observability.
