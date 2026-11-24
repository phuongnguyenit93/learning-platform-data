# Nguy cơ đưa user_id, request_id hoặc thông báo lỗi nguyên văn vào tag

Tag giúp phân tách metrics theo những chiều có ý nghĩa, chẳng hạn HTTP method, kết quả xử lý hoặc kênh bán hàng. Nhưng mỗi tổ hợp tag có thể tạo một meter ID riêng trong Micrometer và một time series riêng ở backend như Prometheus. Nếu đưa `user_id`, `request_id` hoặc thông báo lỗi nguyên văn vào tag, số lượng giá trị có thể tăng gần như theo từng người dùng, từng request hoặc từng lỗi. Hệ quả là cardinality tăng mạnh, chi phí lưu trữ và truy vấn tăng, dashboard khó tổng hợp, đồng thời dữ liệu định danh hoặc thông tin nhạy cảm có thể bị phát tán qua hệ thống metrics.

Quy tắc thiết kế quan trọng là: **tag mô tả nhóm có miền giá trị nhỏ và ổn định; dữ liệu nhận diện một cá thể hoặc một sự kiện cụ thể thuộc về log và trace**. Bài học này phân tích rủi ro, minh họa cách viết instrumentation an toàn hơn và chỉ ra những lớp bảo vệ có thể áp dụng trong Micrometer.

## Tag ảnh hưởng đến danh tính meter như thế nào?

Một meter được đăng ký bằng tên và tập tag. Ví dụ:

~~~java
Counter.builder("payment.failures")
    .tag("dependency", "gateway")
    .tag("outcome", "timeout")
    .register(registry);
~~~

Tên `payment.failures` cùng hai cặp tag tạo thành danh tính của meter. Khi giá trị tag thay đổi, một meter ID khác có thể được đăng ký. Ở backend time series, tên metric cùng toàn bộ label cũng xác định một chuỗi dữ liệu riêng.

Với các tag có miền giá trị nhỏ, số meter có thể dự đoán được:

- `dependency`: `gateway`, `database`, `inventory`.
- `outcome`: `success`, `client_error`, `server_error`.
- `method`: `GET`, `POST`, `PUT`, `DELETE`.

Ngược lại, nếu tag nhận một giá trị mới cho mỗi request, số meter và time series có thể tăng theo lưu lượng thực tế. Khác biệt này là cốt lõi của cardinality.

## Rủi ro 1: đưa `user_id` vào tag

Một cách triển khai có vẻ tiện lợi là gắn ID người dùng vào counter để xem ai tạo nhiều request hoặc ai thường gặp lỗi:

~~~java
// Không nên: mỗi user_id có thể tạo một meter ID riêng.
registry.counter(
    "api.requests",
    "user_id", user.getId()
).increment();
~~~

Nếu hệ thống có một triệu người dùng hoạt động, metric này có thể tạo đến một triệu giá trị tag `user_id`. Nếu cùng metric còn có `method`, `status` và `instance`, số tổ hợp tiềm năng còn tăng theo tích các chiều đó.

### Hệ quả về vận hành

- **Cardinality tăng cao:** backend phải quản lý nhiều time series riêng, tiêu tốn bộ nhớ, chỉ mục, dung lượng lưu trữ và tài nguyên truy vấn.
- **Series churn:** người dùng mới hoặc người dùng hoạt động theo thời điểm làm phát sinh các chuỗi mới. Ngay cả khi mỗi chuỗi chỉ tồn tại ngắn, việc tạo và loại bỏ liên tục vẫn gây tải cho hệ thống nhận.
- **Dashboard mất ý nghĩa tổng hợp:** biểu đồ bị chia thành quá nhiều series, khó đọc và khó tạo cảnh báo ổn định.
- **Dễ chạm giới hạn backend:** một số hệ thống giới hạn số series, số label hoặc kích thước dữ liệu. Khi vượt giới hạn, dữ liệu có thể bị từ chối, loại bỏ hoặc làm ảnh hưởng đến khả năng thu thập của workload khác.
- **Rủi ro riêng tư:** ID có thể liên kết ngược đến tài khoản hoặc hồ sơ người dùng. Metrics thường được chia sẻ rộng trong tổ chức, lưu giữ lâu và sao chép sang nhiều hệ thống.

Mã hóa hoặc băm `user_id` không giải quyết được cardinality. Nếu mỗi người dùng vẫn tạo một giá trị băm khác nhau, backend vẫn phải lưu gần như cùng số lượng chuỗi. Hash cũng không tự động biến dữ liệu thành vô danh; nó có thể vẫn liên kết được với một cá nhân khi có dữ liệu đối chiếu.

### Nên làm gì?

Nếu mục tiêu là so sánh mức sử dụng theo nhóm, hãy dùng một phân loại có miền giá trị được kiểm soát, chẳng hạn loại gói dịch vụ:

~~~java
private static String normalizePlan(String plan) {
    if (plan == null) {
        return "other";
    }

    return switch (plan) {
        case "free", "pro", "enterprise" -> plan;
        default -> "other";
    };
}

registry.counter(
    "api.requests",
    "plan", normalizePlan(account.getPlan())
).increment();
~~~

Ở đây tag `plan` chỉ nhận bốn giá trị: `free`, `pro`, `enterprise` hoặc `other`. Bạn vẫn có thể so sánh hành vi ở cấp phân khúc mà không tạo một chuỗi riêng cho từng tài khoản. Chỉ đưa chiều phân tích này vào metrics nếu nó phục vụ một câu hỏi vận hành hoặc sản phẩm cụ thể và được phép theo chính sách dữ liệu của hệ thống.

Nếu cần tìm chính xác người dùng nào tạo request, hãy dùng log hoặc công cụ phân tích được thiết kế cho truy vấn sự kiện và áp dụng kiểm soát truy cập, thời hạn lưu giữ phù hợp.

## Rủi ro 2: đưa `request_id` vào tag

Request ID thường được tạo riêng cho từng request để lần theo một yêu cầu xuyên suốt nhiều thành phần. Vì giá trị gần như duy nhất cho mỗi request, nó là một ví dụ điển hình của tag có cardinality rất cao.

~~~java
// Không nên: request_id gần như thay đổi ở mỗi lần gọi.
registry.timer(
    "http.server.request",
    "request_id", request.getRequestId()
).record(() -> handler.handle(request));
~~~

Với 10.000 request mỗi phút, metric có thể phát sinh hàng nghìn giá trị `request_id` mới trong một khoảng thời gian ngắn. Nếu mỗi request còn đi qua nhiều route hoặc instance, số series có thể tăng thêm. Thêm `request_id` cũng không giúp dashboard đo độ trễ tổng thể tốt hơn; nó chia phân phối thời gian thành những mảnh nhỏ, mỗi mảnh thường chỉ có một quan sát.

### Phân chia trách nhiệm giữa metrics, logs và traces

| Loại dữ liệu | Câu hỏi phù hợp | Ví dụ trường |
|---|---|---|
| Metrics | Hệ thống đang khỏe đến mức nào? Xu hướng lỗi và độ trễ ra sao? | `route`, `method`, `status_class`, `outcome` |
| Logs | Request cụ thể đã ghi lại sự kiện gì? | `request_id`, mã lỗi, thông tin xử lý đã được lọc |
| Traces | Request đi qua những service/span nào và mất thời gian ở đâu? | trace ID, span ID, span attributes phù hợp |

Metrics nên dùng các chiều tổng hợp. Request ID nên được giữ trong log có cấu trúc hoặc context của trace để kỹ sư có thể lần theo một request cụ thể. Hệ thống tracing có thể hỗ trợ liên kết giữa trace và log; cách liên kết cụ thể phụ thuộc nền tảng triển khai.

Không nên đưa request ID vào tag chỉ để tạo liên kết giữa metrics và trace. Hãy dùng khả năng correlation sẵn có của logging/tracing, đồng thời giữ các label của metrics ổn định.

### Ví dụ instrumentation HTTP với tag hữu hạn

Thay vì ID request và URL thực tế, dùng route template, method và nhóm trạng thái:

~~~java
String route = request.getRouteTemplate(); // Ví dụ: /orders/{id}
String method = request.getMethod();
String statusClass = switch (response.getStatusCode() / 100) {
    case 2 -> "2xx";
    case 3 -> "3xx";
    case 4 -> "4xx";
    case 5 -> "5xx";
    default -> "other";
};

Timer.builder("http.server.requests")
    .tag("route", normalizeRoute(route))
    .tag("method", normalizeMethod(method))
    .tag("status_class", statusClass)
    .register(registry)
    .record(() -> handler.handle(request));
~~~

Các hàm `normalizeRoute` và `normalizeMethod` nên ánh xạ đầu vào vào danh sách route/method được hỗ trợ, trả về `other` hoặc `unmatched` khi không nhận diện được. Đặc biệt, `route` phải là route template do framework cung cấp hoặc được ứng dụng chuẩn hóa; không lấy URL đầy đủ đã chứa ID thực tế làm tag.

Request ID vẫn có thể xuất hiện trong log hoặc trace nếu chính sách bảo mật và quyền truy cập cho phép. Tránh ghi token, cookie, thông tin xác thực hoặc dữ liệu cá nhân vào bất kỳ trường nào.

## Rủi ro 3: đưa thông báo lỗi nguyên văn vào tag

Thông báo lỗi thường được tạo từ dữ liệu động. Ví dụ:

- `User 92831 was not found`.
- `Connection to 10.0.4.17 timed out after 3000ms`.
- `Invalid email someone@example.com`.
- `Duplicate order 7f83...`.
- `SQL constraint failed for value ...`.

Nếu dùng nội dung này làm tag, mỗi lần lỗi có thể tạo một giá trị mới. Một message có thể chứa user ID, email, địa chỉ IP, dữ liệu đầu vào, câu truy vấn, tên bảng hoặc thông tin từ dịch vụ bên ngoài. Vì vậy, tag bằng thông báo lỗi nguyên văn vừa làm cardinality tăng, vừa có thể đưa dữ liệu nhạy cảm vào metrics.

~~~java
try {
    paymentGateway.charge(command);
} catch (RuntimeException exception) {
    // Không nên: message thay đổi theo request và có thể chứa dữ liệu nhạy cảm.
    registry.counter(
        "payment.failures",
        "error", exception.getMessage()
    ).increment();

    throw exception;
}
~~~

Không nên thay thông báo bằng `exception.toString()` hoặc toàn bộ stack trace; các dạng này vẫn có thể chứa nội dung động và dữ liệu đầu vào. Dùng tên class exception cũng cần cân nhắc: một hệ thống plugin hoặc mã ứng dụng có thể sinh nhiều loại exception. Phân loại về một tập nhóm lỗi hữu hạn thường dễ kiểm soát hơn.

### Phân loại lỗi thành nhóm ổn định

Ví dụ sau chuyển exception sang một tập category đã định nghĩa:

~~~java
import java.net.ConnectException;
import java.net.SocketTimeoutException;

private static String classifyError(Throwable error) {
    if (error instanceof SocketTimeoutException) {
        return "timeout";
    }
    if (error instanceof ConnectException) {
        return "connection";
    }
    if (error instanceof IllegalArgumentException) {
        return "invalid_argument";
    }
    return "unexpected";
}
~~~

Sử dụng category khi ghi nhận metric:

~~~java
try {
    paymentGateway.charge(command);
} catch (RuntimeException exception) {
    registry.counter(
        "payment.failures",
        "dependency", "gateway",
        "error_category", classifyError(exception)
    ).increment();

    throw exception;
}
~~~

Tag `error_category` chỉ có các giá trị `timeout`, `connection`, `invalid_argument` và `unexpected`. Có thể mở rộng danh sách khi có một nhóm lỗi mới thực sự hữu ích cho vận hành, nhưng cần xem xét miền giá trị trước khi triển khai.

Thông báo đầy đủ và stack trace có thể được ghi vào log theo cấu trúc, với dữ liệu nhạy cảm đã được loại bỏ hoặc che theo chính sách. Metric trả lời câu hỏi “nhóm lỗi nào đang tăng?”, còn log cung cấp ngữ cảnh để điều tra một sự kiện cụ thể.

## Cardinality tăng theo tổ hợp tag

Giả sử một metric HTTP có các chiều sau:

| Tag | Số giá trị được quan sát |
|---|---:|
| `route` | 40 |
| `method` | 4 |
| `status_class` | 5 |
| `instance` | 12 |

Số tổ hợp tối đa theo tích các miền giá trị là:

~~~text
40 × 4 × 5 × 12 = 9.600 chuỗi thời gian
~~~

Đây là ước lượng tối đa khi mọi tổ hợp đều xuất hiện. Số thực tế phụ thuộc dữ liệu và cách thu thập. Nếu thêm `user_id` với 100.000 giá trị, không gian tổ hợp lý thuyết tăng lên 960 triệu. Nếu thêm `request_id`, số giá trị mới có thể tiếp tục tăng theo lưu lượng.

Với `Timer` hoặc `DistributionSummary` bật histogram, mỗi meter ID còn có thể xuất nhiều chuỗi thống kê như bucket, count và sum. Vì thế chi phí của một tag không chỉ là số meter ID mà còn có thể nhân lên theo số chuỗi được xuất cho từng meter.

Cardinality cũng khác với tốc độ ghi sample. Một metric có ít series vẫn có thể có tần suất scrape cao; ngược lại, metric có nhiều series có thể gây áp lực lên bộ nhớ và chỉ mục ngay cả khi mỗi series ít sample. Khi đánh giá chi phí, cần xem cả số series đồng thời, số series mới theo thời gian và tần suất ghi dữ liệu.

## Thiết kế tag an toàn và hữu ích

Trước khi thêm tag, hãy xác định câu hỏi mà dashboard hoặc alert cần trả lời. Nếu không có câu hỏi cụ thể, tag mới có thể chỉ làm tăng chi phí và độ phức tạp.

### Chọn tag theo nhóm ổn định

| Nhu cầu phân tích | Tag nên cân nhắc | Giá trị ví dụ |
|---|---|---|
| Phân biệt thao tác HTTP | `method` | `GET`, `POST`, `PUT`, `DELETE` |
| Phân biệt endpoint | `route` | `/orders`, `/orders/{id}` |
| Nhóm kết quả HTTP | `status_class` | `2xx`, `3xx`, `4xx`, `5xx` |
| Nhóm kết quả nghiệp vụ | `outcome` | `success`, `rejected`, `failed` |
| Nhóm lỗi | `error_category` | `timeout`, `connection`, `validation`, `unexpected` |
| Phân biệt loại phụ thuộc | `dependency` | `database`, `gateway`, `inventory` |
| Phân khúc tài khoản có kiểm soát | `plan` | `free`, `pro`, `enterprise`, `other` |

Các giá trị trong bảng là ví dụ. Ứng dụng cần chuẩn hóa đầu vào theo enum hoặc allowlist riêng để tránh biến thể như `ServerError`, `server_error`, `SERVER_ERROR` cùng xuất hiện như các giá trị khác nhau.

### Danh sách kiểm tra trước khi thêm tag

1. **Có mục đích truy vấn rõ ràng không?** Tag phải hỗ trợ dashboard, alert hoặc phân tích vận hành cụ thể.
2. **Miền giá trị có hữu hạn không?** Liệt kê các giá trị hợp lệ và ước lượng số tổ hợp với những tag hiện có.
3. **Giá trị có thay đổi theo từng request hoặc cá thể không?** Nếu có, không nên dùng làm tag metrics.
4. **Có chứa dữ liệu cá nhân hoặc bí mật không?** Không đưa ID tài khoản, email, token, cookie, nội dung request hay thông báo lỗi nguyên văn vào tag.
5. **Có thể chuẩn hóa không?** Ánh xạ đầu vào vào enum, route template hoặc category ổn định.
6. **Có cần thêm tag này ở mọi meter không?** Tag chung làm tăng cardinality của nhiều metric cùng lúc.
7. **Đã xem tác động của histogram chưa?** Histogram có thể nhân số chuỗi cho mỗi meter ID.

Một nguyên tắc thực tế là ưu tiên số ít chiều phân tích có giá trị cao. Mỗi tag bổ sung cần có lý do và ước lượng cardinality trước khi phát hành.

## Phòng vệ bổ sung bằng MeterFilter

Thiết kế tag ở nơi tạo meter là lớp kiểm soát đầu tiên. `MeterFilter` có thể bổ sung giới hạn để giảm tác động khi một tag ngoài dự kiến xuất hiện.

Ví dụ dưới đây giới hạn số giá trị `uri` cho metric HTTP server:

~~~java
registry.config().meterFilter(
    MeterFilter.maximumAllowableTags(
        "http.server.requests",
        "uri",
        100,
        MeterFilter.deny()
    )
);
~~~

Khi số giá trị `uri` vượt giới hạn, filter cuối cùng từ chối các meter mới tương ứng. Đây là hàng rào bảo vệ, không phải cách thay thế chuẩn hóa route. Nếu filter từ chối meter, dashboard có thể thiếu dữ liệu cho route mới. Hãy theo dõi việc từ chối, chọn giới hạn có căn cứ và kiểm thử trong môi trường phù hợp.

Có thể dùng filter để từ chối một meter hoặc chuẩn hóa tên/tag theo quy tắc của ứng dụng. Tuy nhiên, filter không thể biến một thiết kế có vô số giá trị thành thiết kế tốt nếu dữ liệu đầu vào vẫn không được kiểm soát. Đừng dựa hoàn toàn vào giới hạn ở registry để xử lý `user_id`, `request_id` hoặc thông báo lỗi động.

## Điều tra một request cụ thể mà không làm bẩn metrics

Một nhu cầu phổ biến là muốn biết request nào gây ra spike độ trễ hoặc lỗi. Hãy kết hợp các lớp quan sát:

1. Metrics cho thấy `http.server.requests` tăng độ trễ p95 hoặc tỷ lệ `5xx` ở route cụ thể.
2. Trace cho biết request đi qua service nào, span nào chậm hoặc thất bại.
3. Log có cấu trúc chứa correlation ID hoặc trace ID cho phép tìm các sự kiện liên quan, sau khi áp dụng kiểm soát dữ liệu và quyền truy cập.

Cách làm này giữ metrics ở mức tổng hợp nhưng vẫn cho phép điều tra sâu. Đừng thêm request ID vào mọi metric để giải quyết bài toán liên kết; hãy dùng trace context và correlation trong logging.

Khi thiết kế luồng log/trace, cũng cần tránh ghi nguyên dữ liệu nhạy cảm. Chuyển một trường từ metrics sang logs không có nghĩa là có thể lưu mọi giá trị tùy ý. Hãy giới hạn quyền truy cập, thời hạn lưu, che dữ liệu và tuân thủ chính sách dữ liệu của hệ thống.

## Ví dụ kiểm thử để phát hiện tag không an toàn

Có thể kiểm tra instrumentation bằng `SimpleMeterRegistry` mà không cần kết nối backend. Ví dụ sau minh họa rằng nhiều request khác nhau vẫn được gom vào một số category hữu hạn:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();

registry.counter(
    "payment.failures",
    "error_category", "timeout"
).increment();

registry.counter(
    "payment.failures",
    "error_category", "timeout"
).increment();

registry.counter(
    "payment.failures",
    "error_category", "connection"
).increment();

assertEquals(
    2.0,
    registry.get("payment.failures")
        .tag("error_category", "timeout")
        .counter()
        .count()
);

assertEquals(
    2,
    registry.find("payment.failures").meters().size()
);
~~~

Kiểm thử này xác nhận hai lần timeout dùng chung meter ID và category `connection` tạo meter ID thứ hai. Có thể mở rộng kiểm thử với hàm chuẩn hóa để bảo đảm mọi đầu vào lạ đều được ánh xạ về `other` hoặc `unexpected`.

Một kiểm tra bổ sung có thể duyệt các meter và xác nhận tag keys không chứa các tên bị cấm như `user_id`, `request_id`, `email` hoặc `error_message`. Với hệ thống lớn, hãy đưa quy tắc này vào code review hoặc kiểm thử kiến trúc để mọi module instrumentation tuân theo cùng tiêu chuẩn.

## Ghi nhớ

- `user_id` và `request_id` thường có miền giá trị gần như không giới hạn; đưa chúng vào tag sẽ làm cardinality tăng theo người dùng hoặc request.
- Thông báo lỗi nguyên văn có thể thay đổi liên tục, chứa dữ liệu nhạy cảm và không phù hợp làm tag.
- Băm ID không làm giảm số giá trị duy nhất và không tự động loại bỏ rủi ro riêng tư.
- Metrics dùng tag ổn định, hữu hạn để phân nhóm; log và trace dùng correlation ID để điều tra từng request.
- Chuẩn hóa route, method, outcome và error category bằng enum hoặc allowlist.
- Histogram có thể nhân số chuỗi theo từng meter ID, vì vậy phải tính cả cấu hình phân phối khi ước lượng cardinality.
- `MeterFilter` là hàng rào bổ sung; nó không thay thế việc thiết kế tag đúng ngay từ đầu.

Khi một tag được đề xuất, hãy hỏi liệu giá trị của nó có giúp trả lời một câu hỏi vận hành ở mức tổng hợp hay chỉ nhận diện một người dùng, request hoặc thông báo cụ thể. Nếu là trường hợp thứ hai, hãy giữ dữ liệu đó trong log hoặc trace với biện pháp bảo vệ phù hợp. Metrics sẽ nhẹ hơn, dễ tổng hợp hơn và đáng tin cậy hơn cho dashboard cùng cảnh báo.

