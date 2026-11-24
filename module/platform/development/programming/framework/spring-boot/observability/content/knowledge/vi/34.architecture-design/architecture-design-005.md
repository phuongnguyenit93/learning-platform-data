# Đặt tag có bounded values

Trong kiến trúc observability của Spring Boot, tag giúp nhóm các lần gọi và so sánh hành vi của ứng dụng qua metrics, logs và distributed traces. Một tag hữu ích khi giá trị của nó có ý nghĩa ổn định và tập giá trị có giới hạn nhỏ, có thể dự đoán. Đây là nguyên tắc **bounded values**: mỗi chiều dữ liệu dùng để phân loại telemetry phải có miền giá trị được kiểm soát.

Nguyên tắc này đặc biệt quan trọng với metrics. Mỗi tổ hợp tên metric và bộ tag có thể tạo thành một time series riêng. Nếu tag nhận vô số giá trị như `userId`, `requestId` hoặc URL chứa ID tài nguyên, số time series có thể tăng theo lưu lượng và dữ liệu thực tế. Hệ quả là Prometheus hoặc hệ thống metrics phải lưu trữ, truy vấn và xử lý lượng dữ liệu lớn, trong khi dashboard lại khó tổng hợp thành thông tin có ích.

Bài học này thuộc chương **Thiết kế kiến trúc** của module **SPRING_BOOT_OBSERVABILITY**. Module hướng dẫn thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; nội dung tập trung vào cách thiết kế tag có miền giá trị hữu hạn để theo dõi lỗi, độ trễ và hành vi ứng dụng ổn định khi chạy thực tế.

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích bounded values và mối liên hệ giữa tag cardinality với số lượng time series.
- Phân biệt low-cardinality key values và high-cardinality key values trong Micrometer Observation.
- Chuẩn hóa dữ liệu đầu vào thành tập giá trị được cho phép trước khi đưa vào metric tags.
- Chọn các chiều phân loại hữu ích, tránh đưa định danh cá nhân hoặc giá trị thay đổi theo từng request vào metrics.
- Kiểm tra cardinality trong quá trình phát triển và vận hành.

## Bounded values là gì?

Tag là một cặp key-value gắn với metric hoặc observation. Ví dụ, metric số lần tra cứu sản phẩm có thể được phân loại theo kênh tiếp nhận và kết quả:

```text
catalog.product.lookup{channel="web", outcome="found"}
catalog.product.lookup{channel="mobile", outcome="not_found"}
```

Trong ví dụ này, `channel` có thể chỉ nhận một số giá trị như `web`, `mobile`, `partner`, `other`; `outcome` có thể chỉ nhận `found`, `not_found`, `error`. Hai tag đều có miền giá trị nhỏ và được định nghĩa trước.

Một giá trị không trở thành bounded chỉ vì chuỗi của nó có độ dài tối đa. Ví dụ, `customerId` luôn dài 12 ký tự nhưng vẫn có thể có hàng triệu giá trị khác nhau. Bounded values nói về **số lượng giá trị phân biệt có thể xuất hiện**, không nói về độ dài của chuỗi.

Tập giá trị cũng cần đủ nhỏ để có ích. Một danh sách vài chục nghìn mã thành phố được quản lý trước vẫn có thể tạo cardinality quá cao cho một metric. Vì vậy, miền giá trị phải được giới hạn theo mục đích phân tích và ngân sách cardinality của hệ thống.

## Cardinality ảnh hưởng đến metrics như thế nào?

Cardinality của một tag là số giá trị phân biệt mà tag đó có thể nhận. Với một metric có nhiều tag, số tổ hợp có thể xuất hiện tăng theo tích số lượng giá trị của từng chiều.

Ví dụ, một metric có ba tag:

| Tag | Số giá trị dự kiến |
|---|---:|
| `channel` | 3 |
| `outcome` | 4 |
| `region` | 5 |

Nếu mọi tổ hợp đều xuất hiện, metric có thể tạo tối đa `3 × 4 × 5 = 60` time series cho mỗi bộ metric tương ứng. Nếu thêm `customerId` với 100.000 giá trị, số tổ hợp lý thuyết tăng lên `60 × 100.000 = 6.000.000` time series.

Đây là lý do một tag có vẻ đơn giản vẫn có thể gây ra vấn đề lớn. Chi phí không chỉ đến từ một tag riêng lẻ mà còn từ tích của các chiều tag kết hợp. Khi số time series tăng nhanh, hệ thống có thể gặp:

- Tăng bộ nhớ, dung lượng lưu trữ và chi phí ingest metrics.
- Truy vấn và dashboard chậm hơn do phải xử lý nhiều chuỗi dữ liệu.
- Khó đặt cảnh báo có ý nghĩa vì mỗi giá trị tạo ra một chuỗi riêng.
- Metrics backend từ chối dữ liệu hoặc áp dụng giới hạn cardinality, làm mất khả năng quan sát một phần hệ thống.

Con số trên là giới hạn tổ hợp lý thuyết. Số time series thực tế còn phụ thuộc vào tổ hợp nào đã xuất hiện, loại metric và cách exporter biểu diễn metric. Dù vậy, phép nhân là cách ước lượng hữu ích khi thiết kế tag.

## Low-cardinality và high-cardinality trong Micrometer Observation

Micrometer Observation phân biệt hai nhóm key-value để các handler có thể xử lý chúng phù hợp với từng tín hiệu:

| Loại key-value | Mục đích | Ví dụ | Cách dùng |
|---|---|---|---|
| Low-cardinality | Phân loại observation bằng một tập giá trị nhỏ; phù hợp để tạo metric tags | `channel=web`, `outcome=success`, `method=GET` | Dùng cho các chiều phân tích cần tổng hợp trên metrics |
| High-cardinality | Bổ sung chi tiết có thể có nhiều giá trị; thường hữu ích trong trace | `product.id=PRD-83921`, `request.id=...` | Chỉ thêm khi cần điều tra một request cụ thể và chính sách dữ liệu cho phép |

Khi Observation được xử lý bởi meter handler, low-cardinality key values được dùng làm tag cho metrics. High-cardinality key values không được đưa vào metric tags theo cách xử lý mặc định của Micrometer Observation; chúng có thể được handler của tracing sử dụng làm thuộc tính span. Cách xuất cuối cùng phụ thuộc các handler và exporter đang cấu hình.

Không nên hiểu rằng mọi giá trị có thể đưa vào high-cardinality đều an toàn. ID khách hàng, email, token, địa chỉ IP hoặc dữ liệu nhạy cảm vẫn cần được đánh giá theo chính sách bảo mật và quyền riêng tư. High-cardinality chỉ mô tả đặc tính số lượng giá trị, không phải nhãn cho phép thu thập dữ liệu tùy ý.

Một quy tắc thiết kế thực tế là: metrics trả lời câu hỏi **điều gì đang xảy ra với một nhóm request?**; traces giúp trả lời **điều gì đã xảy ra trong request cụ thể này?**. Hãy dùng low-cardinality tags cho câu hỏi thứ nhất và chỉ thêm chi tiết định danh vào trace khi thực sự cần cho câu hỏi thứ hai.

## Thiết kế miền giá trị cho tag

### 1. Chọn chiều phân loại có ý nghĩa vận hành

Mỗi tag nên giúp trả lời một câu hỏi cụ thể. Với một thao tác tra cứu sản phẩm, các chiều sau thường có ích:

- `channel`: request đến từ `web`, `mobile` hay `partner`?
- `outcome`: thao tác thành công, không tìm thấy dữ liệu hay gặp lỗi?
- `region`: request được xử lý tại vùng triển khai nào trong danh sách cấu hình?
- `method`: request dùng HTTP method nào?
- `status`: response có mã trạng thái nào hoặc thuộc nhóm 2xx, 4xx, 5xx?

Tránh thêm tag chỉ vì dữ liệu có sẵn. Một chiều phân loại không giúp đưa ra quyết định vận hành sẽ làm tăng số tổ hợp mà không tăng giá trị quan sát.

### 2. Định nghĩa tập giá trị được phép

Ưu tiên enum, hằng số hoặc một hàm chuẩn hóa có allowlist rõ ràng. Ví dụ, `channel` chỉ chấp nhận ba giá trị đã thống nhất. Mọi giá trị khác được gom vào `other`; dữ liệu thiếu có thể được biểu diễn bằng `unknown`.

```java
import java.util.Locale;

static String normalizeChannel(String rawChannel) {
    if (rawChannel == null || rawChannel.isBlank()) {
        return "unknown";
    }

    return switch (rawChannel.trim().toLowerCase(Locale.ROOT)) {
        case "web" -> "web";
        case "mobile" -> "mobile";
        case "partner" -> "partner";
        default -> "other";
    };
}
```

Hàm chuẩn hóa bảo đảm tag `channel` chỉ có năm giá trị: `web`, `mobile`, `partner`, `other`, `unknown`. Dù client gửi một chuỗi ngẫu nhiên khác nhau ở mỗi request, metric vẫn chỉ nhìn thấy một trong năm giá trị này.

Hãy thống nhất ý nghĩa của `other` và `unknown`. `other` thường có nghĩa là đã nhận được giá trị nhưng giá trị đó nằm ngoài danh sách hỗ trợ; `unknown` thường biểu thị dữ liệu bị thiếu hoặc không xác định. Nếu gộp hai trường hợp, cần chắc chắn rằng việc đó không làm mất thông tin cần thiết cho vận hành.

### 3. Chuẩn hóa đường dẫn và kết quả

Với HTTP server metrics, hãy dùng route template thay vì đường dẫn thực tế. Ví dụ:

| Không nên đưa vào tag | Nên dùng |
|---|---|
| `/orders/982341` | `/orders/{orderId}` |
| `/customers/abc-123/profile` | `/customers/{customerId}/profile` |
| URL đầy đủ kèm query string | Route template đã chuẩn hóa |

Đường dẫn thực tế có thể chứa ID khác nhau ở mỗi request. Route template giữ được ý nghĩa của endpoint mà không tạo một series cho từng tài nguyên. Với Spring Boot Web MVC và WebFlux, hãy giữ cơ chế quan sát HTTP mặc định và bảo đảm tag URI là mẫu route đã chuẩn hóa; không tự thay nó bằng raw path hoặc query string.

Tương tự, hãy ánh xạ kết quả nghiệp vụ về một tập giá trị rõ ràng như `success`, `not_found`, `invalid`, `rejected`, `error`. Không đưa thông báo exception, nội dung request hoặc câu trả lời từ dịch vụ bên ngoài trực tiếp vào tag.

### 4. Giữ key ổn định

Tên tag nên là tập key cố định, có cùng ý nghĩa trên mọi request. Không tạo key động như `customer_123_status` hoặc `error_<message>`. Cách đặt key động làm tăng số chiều và khiến dashboard khó truy vấn nhất quán.

Không dùng các biến thể tên key cho cùng một khái niệm, chẳng hạn `client`, `source`, `channel` ở các nơi khác nhau mà không có định nghĩa rõ ràng. Hãy thống nhất từ vựng trong toàn service để metrics có thể so sánh qua các phiên bản.

## Gắn bounded tags bằng Micrometer Observation trong Spring Boot

Spring Boot tích hợp Micrometer Observation để tạo một điểm chung cho việc ghi nhận hoạt động. Khi ứng dụng có cấu hình Actuator và các meter/tracing handler tương ứng, Observation có thể được chuyển thành metrics và trace. Spring Boot cung cấp `ObservationRegistry` để ứng dụng sử dụng; có thể inject registry này vào service thay vì tự tạo một registry riêng.

Ví dụ sau ghi nhận thao tác tra cứu sản phẩm. Giả sử ứng dụng đã có các kiểu miền `Product` và `ProductRepository`. `channel` được chuẩn hóa trước khi trở thành low-cardinality key value. `outcome` cũng chỉ nhận ba giá trị được định nghĩa trong code.

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.util.Locale;
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final ProductRepository productRepository;
    private final ObservationRegistry observationRegistry;

    public CatalogService(
            ProductRepository productRepository,
            ObservationRegistry observationRegistry) {
        this.productRepository = productRepository;
        this.observationRegistry = observationRegistry;
    }

    public Optional<Product> findProduct(String productId, String channel) {
        Observation observation = Observation
                .createNotStarted("catalog.product.lookup", observationRegistry)
                .lowCardinalityKeyValue("channel", normalizeChannel(channel));

        observation.start();
        try (Observation.Scope scope = observation.openScope()) {
            Optional<Product> result = productRepository.findById(productId);
            observation.lowCardinalityKeyValue(
                    "outcome", result.isPresent() ? "found" : "not_found");
            return result;
        } catch (RuntimeException exception) {
            observation.lowCardinalityKeyValue("outcome", "error");
            observation.error(exception);
            throw exception;
        } finally {
            observation.stop();
        }
    }

    static String normalizeChannel(String rawChannel) {
        if (rawChannel == null || rawChannel.isBlank()) {
            return "unknown";
        }

        return switch (rawChannel.trim().toLowerCase(Locale.ROOT)) {
            case "web" -> "web";
            case "mobile" -> "mobile";
            case "partner" -> "partner";
            default -> "other";
        };
    }
}
```

Trong ví dụ:

- Tên observation `catalog.product.lookup` ổn định và mô tả thao tác.
- `channel` được giới hạn trong năm giá trị.
- `outcome` chỉ có `found`, `not_found` hoặc `error`.
- `productId` được dùng để truy vấn repository nhưng không trở thành metric tag.
- `observation.error(exception)` ghi nhận exception cho observation; nội dung exception không được đưa vào low-cardinality tag.
- `observation.stop()` luôn được gọi để kết thúc observation, kể cả khi thao tác ném exception.

Nếu trace backend cần định danh sản phẩm để điều tra một span cụ thể, có thể cân nhắc thêm high-cardinality key value trước khi bắt đầu observation:

```java
observation.highCardinalityKeyValue("product.id", productId);
```

Chỉ thêm thuộc tính này khi có nhu cầu điều tra rõ ràng, backend tracing hỗ trợ và dữ liệu được phép xuất. Không đổi `product.id` thành low-cardinality chỉ để tiện lọc dashboard. Nếu cần thống kê theo nhóm sản phẩm, hãy ánh xạ sản phẩm sang một nhóm có tập giá trị nhỏ, ví dụ `category=electronics` hoặc `category=home`.

## Những giá trị thường không nên dùng làm metric tags

| Giá trị đầu vào | Vì sao không phù hợp | Cách xử lý |
|---|---|---|
| `userId`, `customerId`, `orderId` | Số lượng ID lớn, thay đổi liên tục | Dùng trong trace khi cần và được phép; metrics chỉ dùng nhóm khách hàng hoặc loại giao dịch đã chuẩn hóa |
| `requestId`, `traceId`, `spanId` | Gần như mỗi request có một giá trị riêng | Dùng cơ chế correlation của tracing và logging |
| Email, số điện thoại, token | Cardinality cao và có thể là dữ liệu nhạy cảm | Không đưa vào metric tags; che hoặc loại bỏ theo chính sách dữ liệu |
| Raw URL, query string | Có thể chứa ID, từ khóa tìm kiếm hoặc tham số tùy ý | Dùng route template và các chiều đã chuẩn hóa |
| Exception message | Nội dung thay đổi theo dữ liệu và có thể chứa thông tin nhạy cảm | Dùng outcome hoặc nhóm lỗi được kiểm soát; giữ stack trace trong log/trace theo chính sách |
| Tên pod hoặc container instance | Thay đổi khi scale hoặc triển khai lại | Chỉ dùng ở nơi cần phân tích hạ tầng; ưu tiên các chiều ổn định như service, environment hoặc region |
| Timestamp hoặc giá trị ngẫu nhiên | Mỗi lần ghi nhận có thể tạo một giá trị mới | Dùng timestamp của hệ thống telemetry, không biến timestamp thành tag |

Không phải mọi chiều có cardinality cao đều phải xóa khỏi mọi tín hiệu. Một ID có thể cần thiết để lần theo một trace hoặc nối log với trace. Điều cần tránh là biến ID đó thành chiều phân loại của metrics. Hãy chọn loại key value theo tín hiệu sẽ tiêu thụ nó và mục đích điều tra.

## Kiểm soát cardinality trong thiết kế và vận hành

### Đặt ngân sách cho từng metric

Trước khi thêm tag, ghi lại:

1. Tên metric hoặc observation sẽ nhận tag.
2. Ý nghĩa của tag và tập giá trị được phép.
3. Số giá trị tối đa dự kiến cho mỗi tag.
4. Số tổ hợp có thể phát sinh khi kết hợp với các tag hiện có.
5. Câu hỏi vận hành mà tag giúp trả lời.

Nếu không thể mô tả tập giá trị hoặc không giải thích được tag hỗ trợ quyết định nào, hãy xem lại thiết kế trước khi đưa tag vào metrics.

### Kiểm thử hàm chuẩn hóa

Hàm chuẩn hóa là ranh giới bảo vệ cardinality, vì vậy cần kiểm thử cả giá trị hợp lệ và đầu vào bất thường:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class ChannelNormalizerTest {
    @Test
    void mapsSupportedChannelsToCanonicalValues() {
        assertEquals("web", CatalogService.normalizeChannel("WEB"));
        assertEquals("mobile", CatalogService.normalizeChannel("mobile"));
        assertEquals("partner", CatalogService.normalizeChannel(" partner "));
    }

    @Test
    void mapsMissingAndUnsupportedChannelsToBoundedValues() {
        assertEquals("unknown", CatalogService.normalizeChannel(null));
        assertEquals("unknown", CatalogService.normalizeChannel("  "));
        assertEquals("other", CatalogService.normalizeChannel("affiliate-9382"));
    }
}
```

Trong ví dụ, hàm chuẩn hóa có phạm vi package-private để test cùng package có thể kiểm tra trực tiếp. Đoạn test minh họa hợp đồng cần giữ: mọi đầu vào đều ánh xạ về một giá trị thuộc allowlist. Trong dự án thực tế, có thể tách logic này thành utility hoặc component riêng, hoặc kiểm thử thông qua hành vi công khai của service.

### Quan sát số lượng series thực tế

Sau khi triển khai, kiểm tra metric ở endpoint hoặc backend metrics đang dùng. Với Prometheus, có thể xem các series theo tên metric và nhóm theo label để phát hiện tag có nhiều giá trị bất thường. Đối chiếu số lượng series với ngân sách đã dự kiến, đặc biệt sau khi thêm một tag mới hoặc tăng lưu lượng.

Nên thực hiện kiểm tra trong các tình huống sau:

- Gửi nhiều request với ID khác nhau và xác nhận số series không tăng theo số ID.
- Gửi giá trị channel không được hỗ trợ và xác nhận chúng cùng được gom vào `other`.
- Kiểm tra các route có ID động để bảo đảm metrics dùng route template.
- So sánh số series trước và sau khi thêm tag mới.
- Kiểm tra dashboard và alert để xác nhận tag mới giúp lọc dữ liệu có ích.

Một dấu hiệu tốt là khi tăng số lượng request hoặc thay đổi ID tài nguyên, số chuỗi metrics vẫn ổn định. Số lần ghi nhận tăng theo request; số series không nên tăng tương ứng với từng request.

## Các lỗi thiết kế thường gặp

### Chỉ giới hạn độ dài chuỗi

Giới hạn `customerId` còn 20 ký tự không giải quyết cardinality. Cần giới hạn tập giá trị, ví dụ chuyển sang `customer_tier=standard|premium|enterprise` nếu câu hỏi vận hành là so sánh theo phân khúc.

### Dùng `toString()` của object làm tag

`toString()` có thể chứa ID, tên, dữ liệu đầu vào hoặc chi tiết thay đổi theo từng object. Hãy lấy một thuộc tính phân loại đã chuẩn hóa và có miền giá trị rõ ràng.

### Dùng raw path thay cho route template

`/orders/1001` và `/orders/1002` là hai chuỗi khác nhau dù cùng đi qua một endpoint. Dùng `/orders/{orderId}` để nhóm chúng thành một chiều ổn định.

### Cho rằng high-cardinality luôn an toàn

High-cardinality key value có thể hữu ích trong trace nhưng vẫn có thể làm tăng dung lượng trace hoặc làm lộ dữ liệu nhạy cảm. Cần chọn lọc thuộc tính, thời gian lưu trữ và quyền truy cập theo chính sách của hệ thống.

### Thêm quá nhiều tag có cardinality thấp

Mỗi tag riêng lẻ có thể nhỏ nhưng tích của chúng vẫn lớn. Ví dụ 8 kênh × 12 vùng × 10 kết quả × 6 phương thức tạo ra tối đa 5.760 tổ hợp. Hãy tính cả tổ hợp trước khi thêm chiều mới.

### Gom mọi trường hợp vào một giá trị mà không có chủ đích

Gom tất cả thành `other` giúp giảm cardinality nhưng có thể che khuất lỗi tích hợp hoặc một client mới. Nếu cần theo dõi dữ liệu ngoài allowlist, hãy dùng một metric tổng hợp riêng có tag bounded như `source=unknown` hoặc ghi log có kiểm soát; không đưa nguyên giá trị lạ vào metric tag.

## Checklist trước khi đưa tag vào production

- [ ] Tag có một mục đích phân tích hoặc vận hành cụ thể.
- [ ] Tên key ổn định, không được tạo động.
- [ ] Miền giá trị nhỏ, được định nghĩa và có thể kiểm thử.
- [ ] Đầu vào ngoài allowlist được chuẩn hóa thành `other` hoặc `unknown`.
- [ ] Không dùng ID, email, token, raw URL, exception message hoặc timestamp làm metric tag.
- [ ] Đã tính số tổ hợp của tag mới với các tag hiện có.
- [ ] Dữ liệu cần truy vết request cụ thể được cân nhắc ở high-cardinality trace attributes và tuân thủ chính sách dữ liệu.
- [ ] Dashboard, alert và backend metrics đã được kiểm tra sau khi triển khai.

## Kết luận

Bounded values giúp metrics giữ được số lượng time series có thể dự đoán và dễ tổng hợp. Trong Spring Boot, hãy dùng low-cardinality key values của Micrometer Observation cho các chiều phân loại ổn định, chuẩn hóa mọi đầu vào theo allowlist và giữ các định danh có cardinality cao ở tín hiệu phù hợp như tracing khi thực sự cần. Thiết kế tag tốt bắt đầu từ câu hỏi vận hành, tập giá trị được kiểm soát và việc tính cardinality của toàn bộ tổ hợp trước khi phát hành.
