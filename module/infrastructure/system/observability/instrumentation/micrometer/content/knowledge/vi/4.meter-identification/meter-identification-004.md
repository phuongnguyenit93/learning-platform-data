# Quy ước tên có dấu chấm và chuyển đổi sang tên của hệ thống nhận

Trong Micrometer, tên meter là định danh ổn định cho một đại lượng cần quan sát. Quy ước phổ biến là viết tên bằng chữ thường và phân tách các thành phần bằng dấu chấm, chẳng hạn `http.server.requests`, `jvm.memory.used` hoặc `payment.authorization`. Khi xuất dữ liệu, registry có thể chuyển tên này sang định dạng mà hệ thống nhận yêu cầu, ví dụ đổi dấu chấm thành dấu gạch dưới cho Prometheus.

Điểm quan trọng là tên trong mã ứng dụng và tên xuất hiện ở backend có thể khác nhau. Mã ứng dụng nên giữ một tên logic nhất quán; registry đảm nhiệm việc chuyển đổi thông qua naming convention. Nhờ vậy, cùng một instrumentation có thể hoạt động với nhiều hệ thống metrics mà không phải rải các quy tắc đặt tên của từng backend vào mã nghiệp vụ.

## 1. Tên logic và tên được xuất ra là hai lớp khác nhau

Khi đăng ký meter, ứng dụng tạo một định danh gồm tên, loại meter, tag và một số metadata như mô tả hoặc đơn vị cơ sở. Ví dụ:

~~~java
Timer.builder("http.server.requests")
        .description("Time spent handling an HTTP request")
        .tag("method", "GET")
        .tag("outcome", "success")
        .register(meterRegistry);
~~~

Trong đoạn mã này, `http.server.requests` là tên logic do ứng dụng đặt. `method` và `outcome` là các chiều phân loại. Khi registry thu thập hoặc xuất dữ liệu, nó áp dụng quy ước tên tương ứng với backend.

Micrometer cung cấp abstraction `NamingConvention` để thực hiện chuyển đổi. Về cơ bản, convention có thể chuyển đổi:

- Tên meter dựa trên tên gốc, loại meter và đơn vị cơ sở.
- Tên tag key.
- Giá trị tag.

Mỗi `MeterRegistry` có naming convention phù hợp với hệ thống nhận. Vì vậy, tên logic mà ứng dụng đăng ký không nhất thiết giống nguyên văn tên xuất hiện trên endpoint scrape hoặc trong giao diện backend.

Ví dụ minh họa:

| Lớp định danh | Giá trị |
|---|---|
| Tên logic trong Micrometer | `http.server.requests` |
| Tag logic | `method=GET`, `outcome=success` |
| Tên thường thấy trong Prometheus | `http_server_requests_seconds_count`, `http_server_requests_seconds_sum` |
| Nhãn trong Prometheus | `method="GET"`, `outcome="success"` |

Với Timer, registry Prometheus biểu diễn số lần ghi nhận và tổng thời lượng bằng các chuỗi thời gian có đơn vị giây. Nếu bật histogram, có thể xuất thêm các chuỗi thời gian bucket. Ví dụ trên chỉ minh họa quy tắc phổ biến; tên cuối cùng phụ thuộc phiên bản registry, cấu hình và loại meter.

Không nên sửa tên trong mã thành `http_server_requests_seconds_count` chỉ vì backend đang hiển thị như vậy. Đó là dạng biểu diễn của registry cho một Timer, không phải tên logic cần dùng để đăng ký meter.

## 2. Vì sao nên dùng dấu chấm trong tên logic?

Dấu chấm giúp chia tên thành các thành phần có ý nghĩa và dễ đọc. Một tên có cấu trúc tốt cho người phát triển biết số đo thuộc miền nào, thành phần nào và đang mô tả điều gì.

Ví dụ:

| Tên logic | Ý nghĩa |
|---|---|
| `http.server.requests` | Thời lượng hoặc số lượng request HTTP ở phía server |
| `jvm.memory.used` | Dung lượng bộ nhớ JVM đang sử dụng |
| `payment.authorization` | Hoạt động xác thực thanh toán |
| `orders.queue.depth` | Độ sâu hàng đợi đơn hàng |
| `cache.evictions` | Số lần phần tử bị loại khỏi cache |
| `database.connections.active` | Số kết nối database đang hoạt động |

Một số nguyên tắc nên áp dụng thống nhất trong module:

1. Dùng chữ thường để tên không phụ thuộc cách viết hoa của ngôn ngữ lập trình hoặc backend.
2. Dùng dấu chấm để phân tách các phần của tên, tránh trộn nhiều kiểu phân tách trong cùng một hệ thống.
3. Chọn từ ngữ mô tả đúng đại lượng hoặc thao tác, không đặt tên quá chung như `value`, `count` hay `duration`.
4. Giữ tên ổn định qua các lần triển khai. Đổi tên meter có thể khiến dashboard, cảnh báo và truy vấn hiện có không còn tìm thấy chuỗi thời gian cũ.
5. Không đưa ID, timestamp, tên người dùng hoặc dữ liệu request vào tên meter.
6. Tránh khoảng trắng, ký tự điều khiển và ký tự đặc biệt không cần thiết. Chỉ sử dụng các ký tự mà quy ước chung của hệ thống cho phép.

Không có một khuôn tên duy nhất phù hợp cho mọi domain. Có thể chọn cấu trúc như `<domain>.<component>.<measure>` hoặc `<domain>.<operation>`, sau đó ghi thành quy ước nội bộ. Ví dụ, `orders.queue.depth` mô tả trạng thái của hàng đợi đơn hàng; `payment.authorization` mô tả thao tác xác thực thanh toán. Điều quan trọng là các nhóm cùng dự án dùng cùng một cách tổ chức.

Không nên nhồi loại meter vào tên nếu loại đó đã được thể hiện bởi API. Ví dụ, `payment.authorization.timer` thường không cần thiết khi meter đã là Timer. Cũng không nên thêm hậu tố `_total` vào tên Counter chỉ vì Prometheus thường biểu diễn Counter bằng hậu tố này; registry có thể tự áp dụng quy tắc đó.

## 3. Phân biệt tên meter với tag

Tên meter trả lời câu hỏi: **đại lượng hoặc thao tác nào đang được đo?** Tag trả lời câu hỏi: **đại lượng đó được phân loại theo chiều nào?**

Ví dụ, nếu muốn đo thời lượng xử lý request HTTP, tên có thể là `http.server.requests`. Các chiều như HTTP method, kết quả và mã trạng thái được thể hiện bằng tag:

~~~java
Timer.builder("http.server.requests")
        .description("Time spent handling an HTTP request")
        .tag("method", requestMethod)
        .tag("outcome", outcome)
        .register(meterRegistry)
        .record(requestDuration);
~~~

Với điều kiện các giá trị tag được kiểm soát, một meter logic có thể biểu diễn nhiều nhóm request. Backend sẽ lưu các chuỗi thời gian riêng theo từng tổ hợp tag.

Không nên tạo tên như `http.server.requests.get.success` hoặc `http.server.requests.post.failure` cho từng tổ hợp method và outcome. Cách đó làm tên biến động theo chiều phân loại và khiến việc tổng hợp, so sánh trở nên khó khăn. Dùng một tên ổn định và đưa các chiều phân loại vào tag sẽ rõ ràng hơn.

Tên tag cũng cần có quy ước. Dùng key ngắn, dễ hiểu và ổn định như `method`, `outcome`, `status`, `region` hoặc `provider`. Tránh hai key khác nhau nhưng mang cùng ý nghĩa, ví dụ một nơi dùng `http.method`, nơi khác dùng `method` cho cùng một chiều mà không có lý do.

Giá trị tag cần được chuẩn hóa. Ví dụ, nếu cùng một trạng thái nhưng nơi ghi `success`, nơi ghi `SUCCESS`, nơi ghi `ok`, backend sẽ xem đây là ba giá trị khác nhau. Hãy chọn một tập giá trị ổn định như `success` và `failure`, hoặc dùng enum chuyển đổi sang dạng chuẩn.

## 4. Registry chuyển tên theo NamingConvention

Micrometer tách quy ước tên logic khỏi quy ước của backend bằng `NamingConvention`. Registry sử dụng convention để chuyển đổi định danh khi biểu diễn meter cho hệ thống nhận.

Một số dạng convention thường gặp:

| Kiểu quy ước | Ví dụ chuyển đổi | Trường hợp sử dụng |
|---|---|---|
| Dạng dấu chấm | `http.server.requests` | Hệ thống chấp nhận tên phân đoạn bằng dấu chấm |
| Dạng snake case | `http_server_requests` | Backend yêu cầu chữ thường và dấu gạch dưới |
| Dạng camel case | `httpServerRequests` | Hệ thống nhận dùng quy ước camel case |
| Identity | Giữ nguyên tên | Chỉ dùng khi định dạng tên logic đã hợp lệ với backend |

Các tên trên là ví dụ về cách biến đổi. Registry thực tế có thể bổ sung hậu tố theo loại meter hoặc đơn vị, chuẩn hóa tag key và áp dụng quy tắc riêng cho giá trị tag.

Về mặt API, `NamingConvention` có các điểm mở rộng tương ứng với tên meter, tag key và tag value. Khi cần đọc hoặc kiểm tra cách một convention hoạt động, hãy xem quy tắc của registry đang sử dụng và phiên bản Micrometer tương ứng.

Không nên chủ động đặt convention chung cho mọi registry nếu ứng dụng đang dùng nhiều backend. Một quy tắc phù hợp với Prometheus có thể không phù hợp với Graphite, StatsD hoặc OTLP. Hãy để registry cụ thể giữ convention mặc định của nó, trừ khi dự án có yêu cầu rõ ràng và đã kiểm thử việc thay đổi.

## 5. Tên được chuyển đổi ở một số hệ thống nhận

### Prometheus

Prometheus thường sử dụng tên chuỗi thời gian có chữ cái, chữ số và dấu gạch dưới. Vì vậy, tên logic phân tách bằng dấu chấm thường được chuyển sang dạng snake case.

Ví dụ minh họa:

| Meter logic | Dạng xuất thường gặp |
|---|---|
| Counter `orders.accepted` | `orders_accepted_total` |
| Timer `http.server.requests` | `http_server_requests_seconds_count`, `http_server_requests_seconds_sum` |
| DistributionSummary `http.request.payload.size` có đơn vị bytes | `http_request_payload_size_bytes` cùng các chuỗi thời gian thống kê tương ứng |

Timer có thể tạo ra count, sum, max và các bucket nếu cấu hình histogram. Counter có thể được biểu diễn với hậu tố `_total`. Các hậu tố này thuộc quy ước xuất của Prometheus registry; không nên tự ghép chúng vào tên logic rồi lại để registry tự thêm lần nữa.

Tên label cũng phải tuân theo cú pháp Prometheus. Registry có thể chuyển đổi tag key sang dạng hợp lệ, chẳng hạn `payment.provider` thành `payment_provider`. Hãy kiểm tra output scrape để biết chính xác tên label mà phiên bản registry đang xuất.

### Graphite và hệ thống dùng đường dẫn phân cấp

Một số hệ thống dùng dấu chấm để biểu diễn các phần của đường dẫn metric. Với các hệ thống này, tên logic có thể gần với đường dẫn hiển thị. Tuy nhiên, cách chuyển tag thành path, cách xử lý ký tự đặc biệt và cách phân tách giá trị vẫn phụ thuộc registry hoặc exporter.

Không nên giả định rằng tên từ Prometheus có thể sao chép nguyên văn sang Graphite. Hãy xem convention và định dạng dữ liệu mà exporter của hệ thống nhận yêu cầu.

### StatsD, OTLP và các hệ thống khác

StatsD thường có giới hạn và quy tắc riêng về tên metric, loại số đo và tag. OTLP có mô hình dữ liệu riêng cho metric name, attribute và unit. Các hệ thống nhận phía sau có thể tiếp tục chuyển đổi tên khi lưu trữ hoặc hiển thị.

Do đó, nên coi tên logic Micrometer là hợp đồng ở phía instrumentation, còn tên cuối cùng là hợp đồng giữa registry/exporter và backend. Khi tích hợp một hệ thống mới, cần kiểm tra cả tên, đơn vị, tag và kiểu dữ liệu ở điểm nhận.

## 6. Đơn vị đo và hậu tố tên

Tên meter nên mô tả ý nghĩa đại lượng. Đơn vị nên được khai báo bằng metadata phù hợp để registry có thể chuyển đổi và xuất nhất quán.

Với Timer, Micrometer đo thời lượng và chuẩn hóa khi xuất theo đơn vị cơ sở của registry. Trong Prometheus, thời lượng thường được biểu diễn bằng giây và tên có hậu tố `_seconds`. Vì vậy, một Timer có tên logic `payment.authorization` có thể được xuất thành các chuỗi thời gian bắt đầu bằng `payment_authorization_seconds`.

Với DistributionSummary, nếu đại lượng có đơn vị rõ ràng như byte, hãy khai báo base unit:

~~~java
DistributionSummary payloadSize = DistributionSummary.builder("http.request.payload.size")
        .description("HTTP request payload size")
        .baseUnit("bytes")
        .register(meterRegistry);

payloadSize.record(payloadBytes);
~~~

Registry có thể dùng base unit để thêm hậu tố hoặc chuyển đổi đơn vị khi xuất. Điều này giúp người đọc biết giá trị đang thể hiện byte, giây hay một đơn vị khác.

Tránh đưa đơn vị vào tên theo nhiều cách không thống nhất, chẳng hạn có nơi dùng `response.time.ms`, nơi khác dùng `response.duration.milliseconds`, trong khi registry lại tự thêm hậu tố giây. Chọn tên logic ổn định, khai báo đơn vị bằng API và xác minh đơn vị xuất ra.

Không phải meter nào cũng cần đơn vị vật lý. Counter thường biểu diễn số lần sự kiện xảy ra; Gauge có thể biểu diễn số kết nối hoặc độ sâu hàng đợi; DistributionSummary có thể biểu diễn kích thước, số lượng hoặc một đại lượng khác. Khi không có đơn vị phù hợp, đừng tự tạo hậu tố gây hiểu nhầm.

## 7. Tránh va chạm sau khi chuyển đổi

Một rủi ro quan trọng là hai tên logic khác nhau có thể trở thành cùng một tên sau khi chuẩn hóa.

Ví dụ, nếu convention chuyển dấu chấm thành dấu gạch dưới:

| Tên logic A | Tên logic B | Kết quả sau chuyển đổi |
|---|---|---|
| `cache.gets` | `cache_gets` | Cả hai có thể thành `cache_gets` |
| `payment.method.used` | `payment_method_used` | Cả hai có thể thành `payment_method_used` |

Khi xảy ra va chạm, backend có thể từ chối dữ liệu, gộp nhầm số đo hoặc khiến dashboard truy vấn không phân biệt được. Vì thế, hãy chọn một kiểu phân tách trong tên logic và tránh trộn tên đã chuẩn hóa thủ công với tên dùng dấu chấm.

Tag key cũng có thể va chạm khi convention chuyển đổi ký tự. Nếu hai key `payment.method` và `payment_method` đều được chuẩn hóa thành `payment_method`, thông tin chiều phân loại sẽ trở nên mơ hồ. Quy tắc đặt tên tag cần được kiểm tra cùng quy tắc đặt tên meter.

Ngoài va chạm do chuyển đổi, cần tránh đăng ký cùng một tên và cùng bộ tag cho những meter có ý nghĩa hoặc loại không tương thích. Ví dụ, không nên dùng cùng một tên cho một Counter đếm sự kiện và một Gauge biểu diễn trạng thái hiện tại. Mỗi tên phải có một ý nghĩa nhất quán trong một registry.

## 8. Cardinality: không đưa dữ liệu động vào tên hoặc tag

Cardinality là số lượng chuỗi thời gian khác nhau được tạo ra từ tên meter và các tổ hợp tag. Đưa dữ liệu biến đổi theo từng request vào tên hoặc tag có thể làm số chuỗi thời gian tăng rất nhanh.

Không nên tạo các meter như:

- `orders.100001.duration`
- `orders.100002.duration`
- `orders.100003.duration`

Đây là cách mã hóa ID đơn hàng vào tên meter. Hãy dùng một tên ổn định như `orders.process.duration` và chỉ thêm tag có tập giá trị nhỏ, ví dụ `channel=web` hoặc `outcome=success`.

Không nên dùng user ID, order ID, request ID, trace ID, email, URL đầy đủ hoặc nội dung lỗi làm tag metrics. Nếu cần thông tin chi tiết cho điều tra, cân nhắc đưa nó vào span hoặc log theo chính sách dữ liệu của hệ thống; vẫn phải đánh giá dung lượng, quyền truy cập và dữ liệu nhạy cảm.

Tên ổn định không có nghĩa là mọi tag đều an toàn. Một meter chỉ có một tên nhưng gắn tag `customer.id` với hàng triệu giá trị vẫn tạo cardinality rất cao. Hãy kiểm tra cả tên lẫn tag trong thiết kế instrumentation.

## 9. Tổ chức tên nhất quán trong ứng dụng Spring Boot

Trong ứng dụng Spring Boot, service nên inject `MeterRegistry` do cấu hình ứng dụng cung cấp và đăng ký meter bằng tên logic theo quy ước chung:

~~~java
@Component
final class OrderMetrics {
    private final Counter accepted;
    private final Timer processing;

    OrderMetrics(MeterRegistry registry) {
        this.accepted = Counter.builder("orders.accepted")
                .description("Number of accepted orders")
                .register(registry);

        this.processing = Timer.builder("orders.process")
                .description("Time spent processing an order")
                .register(registry);
    }

    void markAccepted() {
        accepted.increment();
    }

    <T> T recordProcessing(Supplier<T> operation) {
        return processing.record(operation);
    }
}
~~~

Các thành phần trong ứng dụng nên dùng chung từ điển tên và tag. Có thể lưu quy ước trong tài liệu kỹ thuật hoặc hằng số để tránh mỗi nhóm tự tạo một biến thể. Hằng số hữu ích khi tên được dùng ở nhiều nơi, nhưng không nên tạo một lớp trung tâm chứa mọi tên nếu nó khiến module phụ thuộc chặt vào nhau.

Khi cấu hình nhiều registry, mỗi registry có thể có convention riêng. Không nên đổi tên thủ công trước khi đăng ký để phục vụ riêng một backend, vì registry khác sẽ nhận tên đã bị biến đổi. Hãy đăng ký bằng tên logic và để registry đảm nhiệm chuyển đổi.

Nếu thật sự cần convention tùy chỉnh, hãy cấu hình ở đúng registry và kiểm thử ba phần: tên meter, tag key và tag value. Đồng thời kiểm tra xem convention tùy chỉnh có làm mất hậu tố đơn vị hoặc quy tắc riêng của exporter hay không. Việc ghi đè convention mặc định cần có lý do rõ ràng.

## 10. Kiểm tra tên logic và tên xuất ra

Một kiểm thử chỉ dùng SimpleMeterRegistry có thể xác minh meter được đăng ký và có số đo, nhưng không chứng minh tên cuối cùng đúng với backend sản xuất. Cần phân biệt hai lớp kiểm tra.

### Kiểm tra ở lớp Micrometer

Kiểm tra tên logic, loại meter, tag và đơn vị mà ứng dụng đăng ký. Ví dụ:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();

Counter.builder("orders.accepted")
        .tag("channel", "web")
        .register(registry)
        .increment();

Meter meter = registry.find("orders.accepted")
        .tag("channel", "web")
        .counter();

assertThat(meter).isNotNull();
assertThat(meter.getId().getName()).isEqualTo("orders.accepted");
assertThat(meter.getId().getTag("channel")).isEqualTo("web");
~~~

Kiểm tra này xác nhận tên logic và tag được đăng ký đúng. Nó không xác nhận Prometheus hoặc hệ thống khác sẽ hiển thị tên như thế nào.

### Kiểm tra ở lớp exporter

Với Spring Boot và Prometheus, kiểm tra nội dung endpoint scrape, thường là `/actuator/prometheus`. Xác minh:

1. Tên được chuyển sang dạng backend mong đợi.
2. Counter, Timer và DistributionSummary có hậu tố hoặc các chuỗi thời gian phù hợp.
3. Đơn vị của Timer và meter có base unit khớp với ý nghĩa số đo.
4. Tag key và tag value được chuyển đổi đúng.
5. Không xuất hiện hai meter khác nhau nhưng trùng tên sau chuẩn hóa.
6. Không có ID động hoặc dữ liệu không được phép trong label.

Với registry khác, dùng endpoint, giao thức hoặc công cụ kiểm tra tương ứng. Kiểm thử tích hợp nên dùng đúng loại registry và phiên bản exporter mà môi trường triển khai đang chạy.

Khi đổi backend hoặc nâng phiên bản Micrometer, hãy kiểm tra lại tên xuất ra. Quy tắc chuyển đổi có thể thay đổi theo phiên bản hoặc loại registry, ảnh hưởng đến dashboard, alert rule và truy vấn đang sử dụng tên cũ.

## 11. Những lỗi đặt tên thường gặp

**Dùng tên backend làm tên logic.** Ví dụ, đặt sẵn `http_server_requests_seconds_count` cho Timer khiến mã bị gắn với định dạng Prometheus và có thể tạo hậu tố lặp khi registry chuyển đổi.

**Trộn dấu chấm và dấu gạch dưới.** Tên như `http.server_requests` khó phân tích và có thể va chạm sau khi chuẩn hóa. Chọn một quy ước logic nhất quán.

**Đưa chiều phân loại vào tên.** Các biến thể như `requests.get`, `requests.post`, `requests.delete` làm tên tăng theo tổ hợp. Dùng `requests` cùng tag `method`.

**Đưa đơn vị vào tên không thống nhất.** Không trộn `duration.ms`, `duration.seconds` và Timer tự chuẩn hóa sang giây. Khai báo đơn vị bằng API và kiểm tra tên được xuất.

**Cho rằng mọi backend chuyển tên giống nhau.** Mỗi registry có thể có convention, hậu tố và quy tắc tag riêng. Kiểm tra tại điểm nhận thực tế.

**Bỏ qua va chạm sau chuẩn hóa.** Hai tên logic khác nhau có thể thành một tên backend. Kiểm tra danh mục tên trước khi triển khai và trong kiểm thử exporter.

## 12. Checklist thiết kế tên meter

Trước khi đưa meter vào ứng dụng, hãy xác minh:

- [ ] Tên logic viết thường, dùng dấu chấm và có ý nghĩa rõ ràng.
- [ ] Tên mô tả đại lượng hoặc thao tác, không chứa giá trị động.
- [ ] Loại meter phù hợp với ý nghĩa: Counter, Gauge, Timer hoặc DistributionSummary.
- [ ] Tag thể hiện chiều phân loại, có key và tập giá trị được kiểm soát.
- [ ] Đơn vị được khai báo bằng metadata phù hợp thay vì tự thêm hậu tố tùy tiện.
- [ ] Tên không va chạm với meter khác sau khi chuyển sang convention của backend.
- [ ] Tên xuất ra đã được kiểm tra bằng registry/exporter thực tế.
- [ ] Dashboard, alert và truy vấn được cập nhật khi có thay đổi tên có chủ đích.

## 13. Kết luận

Hãy đặt tên meter theo ngữ nghĩa của ứng dụng bằng chữ thường và dấu chấm, giữ tên ổn định, còn tag dùng để biểu diễn các chiều phân loại có cardinality được kiểm soát. NamingConvention của từng registry chuyển tên logic, tag key và tag value sang dạng mà hệ thống nhận hỗ trợ; loại meter và đơn vị có thể làm xuất hiện thêm hậu tố trong dữ liệu cuối cùng.

Khi tích hợp backend mới, hãy xác minh tên và đơn vị tại điểm xuất dữ liệu. Cách làm này giúp mã instrumentation giữ được ngữ nghĩa nhất quán, đồng thời tránh va chạm tên, cardinality ngoài dự kiến và lỗi truy vấn khi chuyển hệ thống giám sát.
