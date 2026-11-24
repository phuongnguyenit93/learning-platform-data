# Chính sách dữ liệu nhạy cảm và ngân sách số chuỗi cho từng nhóm phép đo

Micrometer giúp ứng dụng Java ghi nhận metrics để quan sát hiệu năng và tình trạng vận hành. Tuy nhiên, mỗi tổ hợp tên meter và tag có thể tạo ra một chuỗi thời gian riêng trong hệ thống giám sát. Nếu tag chứa dữ liệu nhận dạng cá nhân, thông tin xác thực hoặc giá trị thay đổi liên tục, metrics vừa có nguy cơ làm lộ dữ liệu vừa có thể tăng cardinality ngoài dự kiến.

Thiết kế tag vì vậy cần hai chính sách đi cùng nhau: chính sách dữ liệu quy định loại thông tin nào được phép xuất hiện trong tag; ngân sách cardinality quy định mỗi nhóm phép đo được phép tạo tối đa bao nhiêu chuỗi thời gian. Chính sách phải được áp dụng từ lúc thiết kế instrumentation, được bảo vệ thêm ở MeterRegistry và được theo dõi trong vận hành.

Bài học thuộc module OBSERVABILITY_INSTRUMENTATION_MICROMETER. Module này hướng dẫn sử dụng Micrometer để đo lường ứng dụng Java bằng counter, gauge, timer, distribution summary và nhãn có kiểm soát; tích hợp Spring Boot, xuất metrics đến hệ giám sát, kiểm soát cardinality, kiểm thử instrumentation và diễn giải số đo vận hành.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Nhận diện dữ liệu nhạy cảm và dữ liệu có nguy cơ tạo cardinality cao trong tag.
- Xây dựng allow-list cho key và value của tag theo từng nhóm phép đo.
- Ước tính số chuỗi thời gian từ số meter, các chiều tag, histogram và số instance.
- Phân bổ ngân sách cardinality cho HTTP, database, cache, nghiệp vụ và tài nguyên nền tảng.
- Dùng MeterFilter để giới hạn số meter và số giá trị tag.
- Thiết kế quy trình review, kiểm thử và giám sát ngân sách theo thời gian.

## 1. Vì sao phải quản lý dữ liệu tag?

Tag là các cặp key-value gắn với Meter.Id. Chúng cho phép chia nhỏ số đo theo những chiều có ích cho phân tích, chẳng hạn HTTP method, route template, status class, channel hoặc tên connection pool.

Ví dụ, meter `http.server.requests` có thể được phân loại bằng các tag:

- `method=GET`
- `uri=/orders/{id}`
- `status=2xx`

Mỗi tổ hợp giá trị tag có thể tạo một chuỗi thời gian riêng. Nếu thêm tag `userId` và mỗi request có một user ID khác nhau, số chuỗi thời gian có thể tăng theo số người dùng. Nếu giá trị tag chứa email hoặc token, thông tin đó còn được chuyển đến hệ thống metrics, dashboard, bộ lưu trữ và các thành phần có quyền truy cập tương ứng.

Hai rủi ro chính cần kiểm soát:

| Rủi ro | Nguyên nhân | Hệ quả |
| --- | --- | --- |
| Lộ dữ liệu nhạy cảm | Tag chứa thông tin cá nhân, định danh tài khoản, token, dữ liệu thanh toán hoặc nội dung request | Dữ liệu có thể xuất hiện trong backend metrics, dashboard, truy vấn, bản sao lưu hoặc hệ thống nhận dữ liệu |
| Cardinality tăng cao | Tag có nhiều giá trị hoặc nhiều chiều được kết hợp với nhau | Tăng bộ nhớ, dung lượng lưu trữ, chi phí ingest, độ trễ truy vấn và tải cho hệ thống giám sát |

Không thể xem metrics là nơi lưu dữ liệu nghiệp vụ chi tiết. Metrics nên mô tả hành vi tổng hợp của ứng dụng. Thông tin cần truy vết đến một cá nhân hoặc một request cụ thể phải được xử lý trong hệ thống log hoặc tracing có chính sách phân quyền, lọc dữ liệu và thời hạn lưu giữ phù hợp.

## 2. Phân loại dữ liệu trước khi đưa vào tag

Trước khi thêm một tag, hãy xác định nguồn dữ liệu, mức độ nhạy cảm, tập giá trị có thể xuất hiện và mục đích truy vấn. Có thể dùng ba nhóm chính sách sau làm điểm khởi đầu:

| Nhóm dữ liệu | Ví dụ | Chính sách với metrics tag |
| --- | --- | --- |
| Giá trị vận hành có tập hữu hạn | HTTP method, status class, channel, kết quả xử lý | Có thể cho phép theo allow-list và giới hạn cardinality |
| Dữ liệu nội bộ cần kiểm soát | Tên pool, tên queue, tên dependency, region nội bộ | Chỉ cho phép nếu có danh mục được duyệt, số lượng hữu hạn và không tiết lộ kiến trúc ngoài phạm vi cần thiết |
| Dữ liệu nhạy cảm hoặc định danh cá nhân | Email, số điện thoại, user ID, session ID, access token, API key, cookie, số thẻ, địa chỉ, nội dung request | Không đưa vào metric name, tag, description hoặc exemplar nếu chưa có cơ chế bảo vệ và phê duyệt phù hợp |

Chính sách an toàn nên dựa trên bản chất dữ liệu, không chỉ dựa vào tên key. Một key tên `customer` có thể chứa mã khách hàng; một key tên `value` cũng có thể vô tình chứa email hoặc token. Cần xem xét cả nguồn dữ liệu và cách giá trị được tạo ra.

### Những giá trị không nên trở thành tag

Không dùng các giá trị sau làm tag:

- Định danh cá nhân hoặc tài khoản: email, số điện thoại, tên đăng nhập, user ID, customer ID.
- Định danh phiên hoặc request: session ID, request ID, correlation ID, trace ID.
- Thông tin xác thực: mật khẩu, access token, refresh token, API key, cookie, authorization header.
- Thông tin thanh toán hoặc tài chính: số thẻ, tài khoản ngân hàng, mã giao dịch cá nhân hoặc dữ liệu thanh toán có thể nhận diện khách hàng.
- Nội dung động: raw URL có ID, query string, exception message, SQL chứa tham số, payload hoặc dữ liệu do người dùng nhập.
- Giá trị tự do không có danh mục: tên file do người dùng gửi, tên tenant tùy ý, chuỗi lỗi hoặc tên class được tạo động.

Ngay cả khi một giá trị được băm hoặc mã hóa, nó vẫn có thể là định danh ổn định, có thể đối chiếu giữa các hệ thống và vẫn tạo cardinality cao. Hash email hoặc user ID không biến chúng thành tag an toàn. Hãy loại bỏ chiều định danh hoặc thay bằng một nhóm tổng hợp đã được duyệt.

### Metrics nên giữ thông tin ở mức tổng hợp

Thay vì gắn một user ID vào meter, hãy đếm số sự kiện theo một nhóm đã được phê duyệt như `channel=web`. Thay vì gắn exception message, hãy phân loại lỗi vào tập nhỏ như `error_type=validation`, `dependency_timeout` hoặc `unknown`. Thay vì dùng URL thực tế, hãy dùng route template do framework hoặc router cung cấp.

Việc phân nhóm phải diễn ra trước khi đăng ký meter. Không đợi exporter hoặc dashboard xử lý dữ liệu nhạy cảm sau khi tag đã được tạo.

## 3. Allow-list cho tag key và tag value

Allow-list xác định rõ key nào được dùng và mỗi key được nhận những value nào. Cách này giúp người viết instrumentation biết giới hạn trước khi meter được tạo.

Ví dụ với HTTP server:

| Tag key | Giá trị được phép | Giá trị không được phép |
| --- | --- | --- |
| `method` | GET, POST, PUT, PATCH, DELETE, OTHER | Method tự do do client gửi |
| `status` | 1xx, 2xx, 3xx, 4xx, 5xx | Mã lỗi hoặc chuỗi trạng thái không chuẩn không được giới hạn |
| `uri` | Route template như /orders/{id}, /health, /checkout | Raw URL, query string, ID thực tế |
| `outcome` | SUCCESS, CLIENT_ERROR, SERVER_ERROR, UNKNOWN | Exception message hoặc nội dung response |
| `exception` | Một danh mục lớp lỗi nhỏ đã được duyệt, hoặc NONE/OTHER | Stack trace, message, tên lớp tùy biến không giới hạn |

Ví dụ với nghiệp vụ checkout:

| Tag key | Giá trị được phép | Ghi chú |
| --- | --- | --- |
| `channel` | web, mobile, partner, other | Nguồn kênh có tập hữu hạn |
| `result` | success, rejected, failed, unknown | Không dùng lý do lỗi tự do |
| `payment_method` | card, bank_transfer, wallet, other | Chỉ dùng loại phương thức, không dùng thông tin thẻ |
| `region` | Danh sách vùng đã chuẩn hóa | Không dùng địa chỉ hoặc vị trí chính xác của khách hàng |

Một allow-list cần có chủ sở hữu. Khi thêm giá trị mới, người thay đổi phải nêu mục đích phân tích, số lượng giá trị tối đa và ảnh hưởng đến ngân sách. Không cho phép một tag nhận chuỗi bất kỳ chỉ vì API builder chấp nhận String.

### Chuẩn hóa giá trị đầu vào

Ví dụ dưới đây chuyển giá trị kênh về một tập hữu hạn trước khi sử dụng làm tag:

```java
enum Channel {
    WEB, MOBILE, PARTNER, OTHER
}

static String metricChannel(String rawChannel) {
    if (rawChannel == null) {
        return Channel.OTHER.name().toLowerCase();
    }

    return switch (rawChannel.toLowerCase()) {
        case "web" -> "web";
        case "mobile" -> "mobile";
        case "partner" -> "partner";
        default -> "other";
    };
}
```

Mã instrumentation chỉ nhận giá trị đã chuẩn hóa:

```java
Counter.builder("checkout.completed")
        .description("Số lượt checkout hoàn tất")
        .tag("channel", metricChannel(channel))
        .register(registry)
        .increment();
```

Không đưa rawChannel vào một tag khác để phục vụ debug. Nếu cần biết giá trị gốc của một request, hãy ghi nhận theo cơ chế log hoặc tracing đã được kiểm soát.

### Chuẩn hóa route

Với HTTP, tag route nên là route template như `/orders/{id}` thay vì đường dẫn thực tế như `/orders/839201`. Ưu tiên lấy route pattern từ framework sau khi route đã được xác định. Nếu không có route template, có thể ánh xạ vào một nhóm như `NOT_FOUND`, `UNMATCHED` hoặc `OTHER`.

Không tự cắt chuỗi URL theo một quy tắc đơn giản rồi cho rằng đã loại bỏ dữ liệu nhạy cảm. Query string, segment động và dữ liệu mã hóa có thể vẫn chứa thông tin cá nhân.

## 4. Cardinality là gì và tăng như thế nào?

Cardinality của một meter là số tổ hợp định danh khác nhau được tạo từ tên meter và các giá trị tag. Trong hệ thống time-series, mỗi tổ hợp label khác nhau thường tương ứng với một chuỗi thời gian riêng.

Giả sử một meter có ba chiều tag:

- `method` có 5 giá trị.
- `status` có 5 giá trị.
- `uri` có 40 route template.

Số tổ hợp label tối đa theo lý thuyết là **5 × 5 × 40 = 1.000**.

Nếu thêm tag `channel` có 4 giá trị, số tổ hợp tăng thành **5 × 5 × 40 × 4 = 4.000**.

Một tag mới có vẻ nhỏ nhưng có thể nhân số chuỗi thời gian lên nhiều lần. Nếu tag nhận giá trị tùy ý, số tổ hợp không còn giới hạn rõ ràng.

### Ước tính số chuỗi theo nhóm meter

Với một nhóm meter, có thể ước tính bằng công thức:

**S_group ≈ Σ(j=1..M) [(Π(i=1..n_j) C_j,i) × F_j]**

Trong đó:

- **M** là số meter family trong nhóm.
- **n_j** là số chiều tag của meter family thứ j.
- **C_j,i** là số giá trị tối đa được phép của tag thứ i.
- **F_j** là số chuỗi backend có thể tạo ra cho mỗi tổ hợp tag của meter đó.

Đây là ước tính theo trường hợp tối đa; số tổ hợp thực tế có thể thấp hơn nếu các giá trị tag không xuất hiện cùng nhau. Với Counter hoặc Gauge đơn giản, **F_j** thường gần 1. Với histogram dạng classic, mỗi tổ hợp tag có thể tạo nhiều chuỗi như bucket, sum và count. Nếu có **B** bucket, số chuỗi thường ít nhất xấp xỉ **B + 2**, chưa tính các chuỗi bổ sung tùy exporter hoặc cấu hình. Summary, percentile và các kiểu export khác có quy tắc riêng, vì vậy phải kiểm tra định dạng thực tế của backend.

Tổng quy mô triển khai còn phụ thuộc số instance: **S_deployment ≈ S_per-instance × R**.

Trong đó **R** là số target hoặc instance được scrape độc lập. Một dịch vụ có 20.000 chuỗi trên mỗi instance và 10 instance có thể tạo khoảng 200.000 chuỗi trên toàn deployment, trước khi tính các job hoặc môi trường khác.

Đây là công thức ước tính để lập ngân sách. Số chuỗi thực tế cần được xác minh bằng dữ liệu exporter và backend, vì registry, histogram, percentile và naming convention có thể làm thay đổi số lượng.

## 5. Lập ngân sách cardinality theo nhóm phép đo

Không nên đặt một con số duy nhất cho toàn hệ thống rồi để các nhóm metric tự cạnh tranh. Hãy chia theo miền quan sát và xác định chủ sở hữu cho từng nhóm. Ngân sách dưới đây chỉ là ví dụ minh họa cho một dịch vụ; cần điều chỉnh theo số route, dependency, histogram, số instance và khả năng của backend.

| Nhóm phép đo | Các chiều thường dùng | Ngân sách chuỗi / instance (ví dụ) | Nguyên tắc |
| --- | --- | ---: | --- |
| HTTP server | route, method, status class, outcome | 25.000 | Route template có allow-list; không có raw URL |
| Database và connection pool | pool, operation, result | 5.000 | Pool và operation lấy từ danh mục cấu hình |
| Cache | cache name, operation, result | 1.500 | Không dùng cache key hoặc tenant ID |
| Checkout nghiệp vụ | channel, result, payment method | 1.000 | Giá trị enum hữu hạn, không chứa định danh thanh toán |
| Queue và worker | queue name, operation, result | 1.000 | Queue name được cấu hình trước; không dùng message ID |
| JVM và process | area, state, pool | 3.000 | Tận dụng binder chuẩn; tránh tag động |
| External dependency | dependency, operation, result | 2.500 | Dependency là tên dịch vụ đã đăng ký |

Ngân sách ví dụ không phải giới hạn mặc định của Micrometer. Nhóm vận hành cần xác định ngân sách dựa trên mục tiêu quan sát, mức tải, cấu hình histogram và chi phí backend. Một nhóm ít phép đo nhưng dùng histogram với nhiều bucket có thể tạo nhiều chuỗi hơn một nhóm có nhiều Counter đơn giản.

### Chia ngân sách cho từng chiều tag

Trong mỗi nhóm, ghi rõ giới hạn giá trị tối đa của từng tag:

| Meter group | Tag key | Giá trị tối đa dự kiến | Nguồn giá trị |
| --- | --- | ---: | --- |
| HTTP server | uri | 40 | Route template đã đăng ký |
| HTTP server | method | 6 | HTTP method allow-list |
| HTTP server | status | 5 | Status class |
| HTTP server | outcome | 4 | Enum kết quả |
| Checkout | channel | 4 | Enum Channel |
| Checkout | result | 4 | Enum kết quả |
| Checkout | payment_method | 4 | Danh mục phương thức |
| Database | pool | 8 | Tên pool cấu hình |
| Database | operation | 6 | SELECT, INSERT, UPDATE, DELETE, COMMIT, OTHER |

Các giới hạn trên giúp ước tính tích số chiều tag, nhưng không thay thế ngân sách chuỗi tổng thể. Giới hạn riêng từng tag không ngăn tích số của nhiều chiều tăng lớn. Ví dụ, bốn tag mỗi tag có 20 giá trị vẫn có thể tạo tới **20^4 = 160.000** tổ hợp cho một meter family.

### Phân bổ ngân sách có dự phòng

Không nên dùng hết ngân sách ngay từ đầu. Hãy để khoảng dự phòng cho route mới, dependency mới và nhu cầu vận hành hợp lệ. Có thể thiết lập:

- Mức mục tiêu: khoảng 60–70% ngân sách.
- Ngưỡng cảnh báo: khoảng 80%.
- Ngưỡng chặn: 100% ngân sách đã được duyệt.

Các tỷ lệ này là gợi ý quản trị, không phải hằng số kỹ thuật. Với nhóm ít thay đổi, ngưỡng có thể chặt hơn. Với nhóm có thay đổi theo release, cần có quy trình cập nhật ngân sách trước khi triển khai.

## 6. Bảo vệ bằng MeterFilter

Micrometer cung cấp MeterFilter để áp dụng chính sách khi meter được đăng ký vào MeterRegistry. Có thể dùng filter để giới hạn tổng số meter và giới hạn số giá trị của một tag cho một nhóm tên meter.

### Giới hạn số giá trị của một tag

Ví dụ sau giới hạn số giá trị tag `uri` của meter có tên bắt đầu bằng `http.server.requests`:

```java
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MetricsPolicyConfiguration {

    @Bean
    MeterFilter httpUriCardinalityLimit() {
        return MeterFilter.maximumAllowableTags(
                "http.server.requests",
                "uri",
                40,
                MeterFilter.deny()
        );
    }
}
```

Khi số giá trị tag khác nhau vượt giới hạn, filter cuối cùng từ chối meter mới vượt ngưỡng. Ví dụ này bảo vệ nhóm HTTP khỏi việc route template phát sinh quá nhiều giá trị. Tên meter và tag key cần khớp với instrumentation thực tế của ứng dụng; Spring Boot hoặc thư viện khác có thể sử dụng tên và tag khác theo phiên bản hoặc cấu hình.

Có thể áp dụng giới hạn riêng cho các nhóm khác:

```java
@Bean
MeterFilter checkoutChannelLimit() {
    return MeterFilter.maximumAllowableTags(
            "checkout",
            "channel",
            4,
            MeterFilter.deny()
    );
}

@Bean
MeterFilter databasePoolLimit() {
    return MeterFilter.maximumAllowableTags(
            "jdbc",
            "pool",
            8,
            MeterFilter.deny()
    );
}
```

Các filter này giới hạn số giá trị của từng key đối với meter name prefix tương ứng. Hãy kiểm tra tên metric và tag key thực tế trước khi đưa cấu hình vào production.

### Giới hạn tổng số meter trong registry

Có thể thêm giới hạn toàn cục để bảo vệ registry khỏi việc tạo quá nhiều meter:

```java
@Bean
MeterFilter registryMeterLimit() {
    return MeterFilter.maximumAllowableMetrics(5000);
}
```

Giới hạn này kiểm soát số meter được đăng ký trong registry. Nó không đồng nghĩa với giới hạn tổng số chuỗi thời gian ở backend. Một Timer hoặc histogram có thể được xuất thành nhiều chuỗi cho mỗi Meter.Id. Vì vậy, cần kết hợp giới hạn meter, giới hạn tag và đo cardinality thực tế tại backend.

### Hiểu đúng giới hạn của MeterFilter

MeterFilter là lớp bảo vệ bổ sung, không phải cơ chế làm sạch dữ liệu nhạy cảm. Nếu một tag chứa email, token hoặc user ID, filter giới hạn cardinality không tự xóa hay che giá trị đó. Các giá trị đầu tiên vẫn có thể được chấp nhận và xuất đi.

Một số filter có thể bỏ hoặc ánh xạ tag, nhưng không nên dựa vào chúng để xử lý dữ liệu nhạy cảm không được phép thu thập. Hãy loại bỏ hoặc chuẩn hóa dữ liệu tại nguồn trước khi tạo meter. Filter chỉ nên là hàng rào thứ hai để giới hạn các trường hợp vượt chính sách.

Cũng cần nhớ rằng filter được áp dụng khi đăng ký meter. Khi meter đã được tạo, việc thay đổi filter không tự động sửa metadata của meter đã tồn tại. Cấu hình chính sách ngay từ lúc khởi tạo registry.

## 7. Tổ chức chính sách trong Spring Boot

Trong Spring Boot, các bean MeterFilter có thể được auto-configuration áp dụng vào MeterRegistry. Có thể tập trung các chính sách vào một lớp cấu hình:

```java
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MetricsPolicyConfiguration {

    @Bean
    MeterFilter httpUriCardinalityLimit() {
        return MeterFilter.maximumAllowableTags(
                "http.server.requests",
                "uri",
                40,
                MeterFilter.deny()
        );
    }

    @Bean
    MeterFilter checkoutChannelLimit() {
        return MeterFilter.maximumAllowableTags(
                "checkout",
                "channel",
                4,
                MeterFilter.deny()
        );
    }

    @Bean
    MeterFilter registryMeterLimit() {
        return MeterFilter.maximumAllowableMetrics(5000);
    }
}
```

Đây là ví dụ minh họa. Trước khi dùng, cần xác nhận các metric prefix, tag key và số lượng giá trị phù hợp với phiên bản Micrometer, Spring Boot và instrumentation đang triển khai. Không sao chép nguyên ngưỡng ví dụ vào mọi môi trường.

Nếu ứng dụng tự tạo registry, cần gắn filter vào cấu hình registry trước khi đăng ký meter:

```java
registry.config()
        .meterFilter(MeterFilter.maximumAllowableTags(
                "http.server.requests",
                "uri",
                40,
                MeterFilter.deny()
        ));
```

Không tạo một registry riêng cho từng request hoặc từng component chỉ để áp dụng ngân sách. Các component cần dùng registry được quản lý theo vòng đời ứng dụng để chính sách được áp dụng nhất quán.

## 8. Thiết kế tag an toàn cho từng nhóm phép đo

### HTTP server

Nên dùng:

- `method`: HTTP method từ allow-list.
- `uri`: route template, không phải URL thực.
- `status`: status code hoặc status class theo quy ước thống nhất.
- `outcome`: kết quả đã chuẩn hóa.

Không dùng:

- Raw URL hoặc query string.
- User ID, session ID, request ID.
- Header, cookie hoặc nội dung request.
- Exception message hoặc stack trace.

### Database và connection pool

Nên dùng tên pool cấu hình trước, operation đã chuẩn hóa và kết quả thành công/thất bại. Không đưa SQL có tham số, tên schema do người dùng nhập, connection ID hoặc transaction ID vào tag.

Nếu cần phân biệt câu lệnh, hãy phân nhóm theo operation như SELECT, INSERT, UPDATE, DELETE hoặc OTHER. Không dùng nguyên văn SQL làm label.

### Cache

Có thể dùng cache name, operation và result khi danh sách cache được cấu hình hữu hạn. Không dùng cache key, user ID hoặc tenant ID làm tag. Cache key thường có số lượng rất lớn và có thể chứa thông tin nghiệp vụ nhạy cảm.

### Queue và worker

Có thể dùng queue name, operation và result nếu queue name đến từ cấu hình. Không dùng message ID, job ID, payload, tên file người dùng gửi hoặc nội dung lỗi tự do.

### Nghiệp vụ checkout

Dùng channel, result, payment method ở mức loại phương thức. Không dùng số thẻ, mã giao dịch, customer ID, email hoặc token thanh toán. Khi cần điều tra một giao dịch, sử dụng mã tham chiếu trong hệ thống nghiệp vụ hoặc tracing đã được bảo vệ, không biến nó thành metric label.

### JVM và process

Ưu tiên binder chuẩn của Micrometer để ghi nhận bộ nhớ, garbage collection, thread và process. Tag như area, pool hoặc state cần có tập giá trị giới hạn. Không gắn thread name tùy ý, tên tác vụ do người dùng tạo hoặc ID của request vào meter hệ thống.

## 9. Kiểm thử chính sách dữ liệu và cardinality

Kiểm thử cần xác nhận cả dữ liệu đầu vào và kết quả đăng ký meter. Không chỉ kiểm tra Counter tăng đúng một đơn vị.

### Kiểm thử chuẩn hóa tag

Với hàm chuẩn hóa channel, kiểm tra:

- Giá trị hợp lệ được giữ nguyên.
- Giá trị không nằm trong allow-list trở thành OTHER.
- Giá trị null hoặc rỗng không gây lỗi và không tạo tag mới.
- Dữ liệu gốc không được truyền vào meter dưới một key khác.

### Kiểm thử MeterFilter

Có thể dùng SimpleMeterRegistry để kiểm tra giới hạn tag. Ví dụ:

```java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class MetricsCardinalityPolicyTest {

    @Test
    void deniesNewUriValuesAfterLimit() {
        var registry = new SimpleMeterRegistry();

        registry.config().meterFilter(
                MeterFilter.maximumAllowableTags(
                        "http.server.requests",
                        "uri",
                        2,
                        MeterFilter.deny()
                )
        );

        Counter.builder("http.server.requests")
                .tag("uri", "/orders")
                .register(registry);

        Counter.builder("http.server.requests")
                .tag("uri", "/checkout")
                .register(registry);

        Counter.builder("http.server.requests")
                .tag("uri", "/customers")
                .register(registry);

        assertThat(registry.find("http.server.requests")
                .tag("uri", "/orders")
                .counter()).isNotNull();

        assertThat(registry.find("http.server.requests")
                .tag("uri", "/checkout")
                .counter()).isNotNull();

        assertThat(registry.find("http.server.requests")
                .tag("uri", "/customers")
                .counter()).isNull();
    }
}
```

Bài kiểm thử này minh họa việc filter từ chối giá trị tag mới sau khi đạt ngưỡng. Khi áp dụng vào dự án, hãy xác nhận API và hành vi của phiên bản Micrometer đang dùng. Với filter giới hạn tổng meter, hãy kiểm thử riêng trường hợp dưới ngưỡng và vượt ngưỡng.

Kiểm thử SimpleMeterRegistry không thay thế kiểm thử exporter. Cần xác minh thêm số chuỗi thực tế ở endpoint hoặc backend, nhất là với Timer, histogram và các registry có quy tắc chuyển đổi riêng.

### Kiểm thử không rò rỉ dữ liệu nhạy cảm

Tạo dữ liệu thử đại diện như email giả, token giả, user ID và URL có query string. Gọi instrumentation rồi kiểm tra:

- Meter name không chứa dữ liệu đầu vào.
- Tag keys và values chỉ thuộc allow-list.
- Description không chứa nội dung request hoặc dữ liệu định danh.
- Exported metrics không chứa chuỗi nhạy cảm giả lập.
- Khi dữ liệu không hợp lệ, instrumentation dùng nhóm OTHER hoặc bỏ chiều tag theo chính sách.

Không dùng dữ liệu thật của khách hàng để kiểm thử chính sách. Có thể dùng chuỗi giả có cấu trúc giống dữ liệu thật để phát hiện việc vô tình đưa dữ liệu vào tag.

## 10. Theo dõi ngân sách trong vận hành

Ngân sách cardinality phải được theo dõi liên tục vì route, dependency, cache, tenant và instrumentation có thể thay đổi qua từng release.

Nên theo dõi:

- Tổng số chuỗi thời gian đang hoạt động theo job, service và môi trường.
- Số chuỗi theo nhóm metric hoặc prefix.
- Số giá trị khác nhau của các tag quan trọng như uri, pool, queue, channel.
- Tốc độ tăng cardinality sau mỗi release.
- Số meter bị từ chối do MeterFilter.
- Mức sử dụng bộ nhớ và chi phí ingest của backend.

Khi backend hỗ trợ, hãy tạo dashboard hoặc cảnh báo cho mức sử dụng ngân sách. Nếu chỉ có giới hạn ở MeterFilter mà không quan sát số liệu bị từ chối, ứng dụng có thể âm thầm mất metrics của các giá trị mới. Cần có cách nhận biết filter đã chặn meter, chẳng hạn metric nội bộ, log cấu hình có kiểm soát hoặc kiểm tra trong test triển khai.

Một quy trình xử lý khi vượt ngân sách:

1. Xác định nhóm metric và tag key gây tăng.
2. Kiểm tra giá trị mới đến từ route, dependency hay dữ liệu đầu vào nào.
3. Xác định giá trị đó có cần cho truy vấn vận hành hay không.
4. Nếu cần, chuẩn hóa hoặc thêm vào allow-list sau khi đánh giá ngân sách.
5. Nếu không cần, loại bỏ chiều tag hoặc gộp vào nhóm OTHER.
6. Cập nhật kiểm thử và tài liệu chính sách trước khi phát hành.
7. Theo dõi lại cardinality sau triển khai.

Không tăng giới hạn chỉ để làm cảnh báo biến mất. Trước tiên phải hiểu nguyên nhân và chứng minh giá trị mới cần thiết.

## 11. Quy trình quản trị thay đổi tag

Mỗi nhóm meter cần có người sở hữu và ngân sách được ghi nhận. Khi thêm hoặc đổi tag, review cần trả lời:

| Nội dung review | Bằng chứng cần có |
| --- | --- |
| Mục đích | Truy vấn, dashboard hoặc cảnh báo nào cần chiều mới? |
| Nguồn dữ liệu | Tag lấy từ enum, route template, cấu hình hay input tự do? |
| Phân loại dữ liệu | Có chứa dữ liệu cá nhân, bí mật hoặc thông tin nghiệp vụ nhạy cảm không? |
| Cardinality | Số giá trị tối đa và tích số với các tag khác là bao nhiêu? |
| Phạm vi | Áp dụng cho một meter family hay toàn bộ registry? |
| Export | Histogram, percentile hoặc exporter có làm tăng số chuỗi không? |
| Kiểm thử | Có test allow-list, giá trị vượt giới hạn và dữ liệu nhạy cảm không? |
| Chủ sở hữu | Ai chịu trách nhiệm khi ngân sách vượt ngưỡng? |

Một tag mới phải có lý do vận hành cụ thể. Nếu không thể chỉ ra truy vấn hoặc quyết định nào cần tag đó, không nên thêm nó.

## 12. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Đưa email hoặc user ID vào tag | Lộ dữ liệu cá nhân và cardinality cao | Bỏ định danh, chỉ giữ số liệu tổng hợp |
| Băm user ID rồi dùng làm tag | Giá trị vẫn có thể liên kết và số lượng vẫn lớn | Không dùng định danh đã băm làm tag |
| Dùng raw URL làm uri | Mỗi resource ID tạo một chuỗi mới | Dùng route template |
| Dùng exception message làm error tag | Nội dung lỗi có thể chứa dữ liệu nhạy cảm và không giới hạn | Ánh xạ sang error category hữu hạn |
| Chỉ giới hạn số giá trị của từng tag | Tích số nhiều chiều vẫn có thể rất lớn | Ước tính và theo dõi ngân sách theo tổ hợp |
| Chỉ giới hạn tổng số Meter | Histogram có thể tạo nhiều chuỗi cho một meter | Kiểm tra series ở backend |
| Tăng giới hạn khi bị từ chối | Có thể che giấu thiết kế tag sai | Điều tra nguồn và mục đích của giá trị mới |
| Chỉ kiểm thử tên và giá trị Counter | Không phát hiện rò rỉ dữ liệu hoặc tăng cardinality | Kiểm thử allow-list, filter và dữ liệu export |
| Chỉ cấu hình filter sau khi meter đã đăng ký | Meter hiện có có thể không chịu chính sách mới | Cấu hình filter trước khi đăng ký meter |

## Kết luận

Tag chỉ nên chứa những chiều phân tích cần thiết, có nguồn dữ liệu rõ ràng và tập giá trị được kiểm soát. Dữ liệu cá nhân, thông tin xác thực, định danh request và nội dung đầu vào không thuộc metric label. Hash hoặc đổi tên các giá trị đó không giải quyết được rủi ro về quyền riêng tư và cardinality.

Ngân sách cardinality cần được tính theo từng nhóm phép đo, có xét tích số các chiều tag, số meter family, histogram và số instance. MeterFilter cung cấp hàng rào giới hạn ở registry; allow-list và chuẩn hóa dữ liệu ở nguồn mới là lớp bảo vệ chính. Kết hợp review, kiểm thử và theo dõi backend giúp metrics duy trì giá trị quan sát mà không tạo chi phí hoặc rủi ro dữ liệu ngoài dự kiến.
