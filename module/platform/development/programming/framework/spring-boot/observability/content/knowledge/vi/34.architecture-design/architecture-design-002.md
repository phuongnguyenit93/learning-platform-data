# Chọn trace cho điều tra latency

Trong một hệ thống Spring Boot gồm nhiều service, một request chậm có thể đi qua nhiều tầng: HTTP server, tầng nghiệp vụ, database, message broker và các service bên ngoài. Metrics cho biết độ trễ đang tăng ở đâu và ảnh hưởng đến bao nhiêu request; distributed tracing giúp lần theo một request cụ thể để tìm đoạn xử lý đóng góp nhiều nhất vào thời gian chờ. Logs bổ sung chi tiết sự kiện tại thời điểm đó.

Chọn trace là một quyết định điều tra. Trace cần đại diện cho triệu chứng đang quan sát, có đủ ngữ cảnh để giải thích đường đi của request và có thể đối chiếu với một trường hợp bình thường. Chỉ mở trace chậm nhất trong hệ thống thường không đủ: đó có thể là một request bất thường, một trace thiếu span hoặc một trường hợp không thuộc nhóm người dùng đang gặp vấn đề.

## 1. Bắt đầu từ tín hiệu latency trên metrics

Trước khi tìm trace, hãy xác định chính xác latency nào đang tăng. Một metric tổng hợp toàn service có thể che khuất vấn đề chỉ xảy ra ở một endpoint, một phiên bản ứng dụng hoặc một vùng triển khai.

Với HTTP server, nên bắt đầu từ histogram duration và các percentile như p50, p95, p99. Trung bình có thể vẫn ổn trong khi một tỷ lệ nhỏ request bị chậm nghiêm trọng. Đồng thời kiểm tra request rate, error rate và saturation của tài nguyên như CPU, bộ nhớ, connection pool hoặc thread pool. Những tín hiệu này giúp phân biệt một request chậm đơn lẻ với một vấn đề đang ảnh hưởng đến cả nhóm request.

Ghi lại các chiều lọc có ý nghĩa trước khi mở tracing backend:

| Chiều lọc | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Service và operation | Thành phần nào đang có latency bất thường? | `checkout`, `POST /checkout` |
| Thời gian | Vấn đề bắt đầu và kéo dài khi nào? | 14:00–14:15, cùng múi giờ với dashboard |
| Phiên bản triển khai | Vấn đề có xuất hiện sau một lần release không? | `service.version=2026.11.22` |
| Vùng hoặc cluster | Vấn đề xảy ra ở một nơi hay trên toàn hệ thống? | `region=ap-southeast-1` |
| Kết quả | Request chậm có đồng thời thất bại không? | HTTP 5xx, exception, timeout |

Ưu tiên các chiều có miền giá trị hữu hạn và có thể so sánh. Không cần đưa mọi thuộc tính của request vào metric; các giá trị có cardinality cao có thể làm tăng số time series và chi phí lưu trữ.

## 2. Hiểu trace và span trước khi chọn mẫu

Một **trace** biểu diễn hành trình của một request qua một hoặc nhiều thành phần. Trace có một trace ID để liên kết các span thuộc cùng hành trình. **Span** biểu diễn một đơn vị công việc có thời điểm bắt đầu, thời lượng, tên operation, loại span, trạng thái và các thuộc tính mô tả.

Ví dụ, request `POST /checkout` có thể tạo ra cây span như sau:

```text
checkout-api  [SERVER]
├── validate-cart
├── inventory.reserve  [CLIENT]
│   └── inventory-service  [SERVER]
│       └── inventory-db.query  [CLIENT]
├── payment.authorize  [CLIENT]
│   └── payment-service  [SERVER]
└── checkout-db.update  [CLIENT]
```

Tên và cách nhóm span phụ thuộc instrumentation đang dùng. Sơ đồ trên minh họa quan hệ cha-con; không phải mọi thư viện đều tạo đúng các span có tên như ví dụ.

Khi điều tra latency, cần phân biệt:

- **Thời lượng trace hoặc root span** cho biết tổng thời gian được đo tại điểm bắt đầu và kết thúc của operation gốc. Với HTTP server span, đây thường là thời gian xử lý request ở phía server.
- **Thời lượng từng span con** cho biết một operation cụ thể mất bao lâu, chẳng hạn gọi database hoặc gọi service khác.
- **Khoảng chờ giữa các span** có thể gợi ý thời gian xếp hàng, lập lịch, xử lý trong code chưa được instrument hoặc một đoạn context bị thiếu.
- **Quan hệ cha-con và thời điểm bắt đầu** cho biết các operation chạy tuần tự hay song song.

Không cộng tất cả duration của span con để suy ra latency của request. Các span lồng nhau có thể tính trùng thời gian; các nhánh song song cũng có thể chạy đồng thời. Khi cần xác định nguyên nhân, hãy xem critical path: chuỗi operation quyết định thời điểm request có thể hoàn tất.

## 3. Quy trình chọn trace có giá trị

### Bước 1: Chuyển triệu chứng thành bộ lọc cụ thể

Từ dashboard, xác định service, operation, khoảng thời gian, phiên bản và vùng đang có vấn đề. Ví dụ: p95 của `POST /checkout` tăng trong 15 phút sau khi triển khai phiên bản mới tại một vùng. Bộ lọc này giới hạn tập trace cần xem và giúp tránh trộn các request có đặc tính khác nhau.

Chọn khoảng thời gian đủ gần với lúc metric phát sinh. Nếu sự cố chỉ kéo dài vài phút, một khoảng tìm kiếm kéo dài nhiều ngày có thể đưa vào các trace không liên quan.

### Bước 2: Lấy trace từ đúng nhóm request

Trong tracing backend, lọc theo các thuộc tính đã xác định. Tùy hệ thống lưu trữ, tên trường có thể khác nhau; về mặt ý nghĩa, bộ lọc thường gồm:

```text
service.name = "checkout"
span.kind = SERVER
http.request.method = "POST"
http.route = "/checkout"
deployment.version = "2026.11.22"
start_time nằm trong khoảng điều tra
```

Sau đó sắp xếp theo duration và xem phân bố. Không dùng URL thô chứa ID đơn hàng hoặc ID người dùng làm bộ lọc chính nếu route template đã đủ phân biệt operation. Các tracing backend có cú pháp truy vấn khác nhau; đoạn trên là bộ thuộc tính minh họa, không phải câu lệnh truy vấn dùng chung cho mọi sản phẩm.

### Bước 3: Chọn cả trace chậm và trace đối chứng

Một tập mẫu tốt thường có nhiều loại trace:

1. **Trace gần p95 hoặc p99** để đại diện cho nhóm request đang tạo ra phần đuôi latency.
2. **Một vài trace chậm hơn rõ rệt** để tìm các outlier và nguyên nhân hiếm.
3. **Trace đối chứng bình thường** của cùng operation, cùng phiên bản và cùng vùng, có duration gần p50 hoặc mức thông thường.
4. **Trace lỗi hoặc timeout**, nếu error rate tăng cùng thời điểm hoặc lỗi có thể làm request kéo dài.

Trace gần percentile giúp hiểu trải nghiệm của nhóm request bị ảnh hưởng. Outlier có thể phát hiện tình huống đặc biệt, nhưng không nên để một outlier duy nhất đại diện cho toàn bộ sự cố. Trace đối chứng giúp xác định span nào chỉ xuất hiện hoặc kéo dài ở nhóm chậm.

Nếu tracing backend hỗ trợ tìm trace theo exemplar từ metric, hãy bắt đầu từ exemplar của histogram latency. Exemplar liên kết một quan sát metric với trace ID, giúp chuyển từ tín hiệu tổng hợp sang một request cụ thể. Khả năng này phụ thuộc cấu hình instrumentation, exporter và backend.

### Bước 4: Kiểm tra trace có đủ ngữ cảnh

Trước khi kết luận, xác nhận trace có root span phù hợp, các span con quan trọng và trace context xuyên qua các service. Một trace chỉ có span HTTP đầu tiên có thể phản ánh việc thiếu instrumentation hoặc propagation, chứ không chứng minh request không gọi dependency nào.

Kiểm tra thêm trạng thái span, exception, timeout, thuộc tính service, phiên bản và thời điểm. Nếu các span đến trễ hoặc bị mất khi export, trace có thể chưa hoàn chỉnh. Khi trace thiếu dữ liệu, đối chiếu với logs và metrics của cùng khoảng thời gian.

### Bước 5: Đọc critical path để tìm đoạn đóng góp vào latency

Mở root span rồi lần theo các span con theo thời gian bắt đầu và kết thúc. Tập trung vào các span nằm trên critical path và có duration bất thường so với trace đối chứng.

Ví dụ, một trace `POST /checkout` kéo dài 1,4 giây có thể cho thấy:

| Operation | Duration minh họa | Cách diễn giải |
| --- | ---: | --- |
| Root HTTP server span | 1.400 ms | Tổng thời gian xử lý được đo tại server |
| `payment.authorize` | 1.080 ms | Có khả năng là nhánh quyết định thời điểm hoàn tất |
| `inventory.reserve` | 75 ms | Gần mức thông thường |
| `checkout-db.update` | 28 ms | Không phải đoạn chiếm phần lớn thời gian trong trace này |

Các duration span con có thể lồng nhau hoặc chạy song song nên bảng này không phải phép cộng để tính root duration. Hãy xác minh bằng timeline. Nếu `payment.authorize` nằm trên critical path và kéo dài hơn nhiều so với trace đối chứng, kiểm tra tiếp span ở service thanh toán, dependency bên ngoài, retry và timeout.

Nếu không có span con nào giải thích phần lớn thời gian, hãy tìm khoảng trống giữa các span. Khoảng trống có thể đến từ queue, thread pool, lock contention, scheduler, code chưa instrument hoặc việc propagation không đi qua một ranh giới bất đồng bộ. Dùng metrics về pool, queue và tài nguyên cùng logs tại thời điểm đó để kiểm tra giả thuyết.

### Bước 6: Đối chiếu logs, metrics và thay đổi triển khai

Trace cho biết cấu trúc và thời lượng; logs cho biết sự kiện và thông tin lỗi; metrics cho biết mức độ phổ biến và xu hướng. Dùng trace ID hoặc span ID trong log để mở các dòng log tương ứng. Dùng timestamp, service, route và phiên bản để đối chiếu với dashboard.

Kiểm tra xem latency có trùng với thay đổi cấu hình, release, tải tăng, database migration, sự cố dependency hoặc thay đổi giới hạn connection/thread pool hay không. Một trace riêng lẻ giúp hình thành giả thuyết; xu hướng metrics và nhiều trace tương tự giúp xác nhận giả thuyết.

### Bước 7: Xác nhận nguyên nhân bằng một phép so sánh có kiểm soát

Sau khi tìm thấy operation nghi vấn, so sánh nhiều trace chậm với trace bình thường theo cùng chiều lọc. Kiểm tra xem hiện tượng có lặp lại ở cùng dependency, cùng phiên bản hoặc cùng vùng không. Nếu có thể, đối chiếu với một khoảng thời gian trước release hoặc một nhóm instance chưa nhận thay đổi.

Chỉ kết luận khi bằng chứng phù hợp trên nhiều tín hiệu. Ví dụ, span gọi payment tăng duration, metrics của payment service cũng tăng latency và logs ghi nhận retry timeout là bằng chứng mạnh hơn việc một trace có span payment dài.

## 4. Dùng Micrometer Observation để tạo trace hữu ích trong Spring Boot

Trong Spring Boot, Micrometer Observation cung cấp một điểm instrument thống nhất. Observation có thể được xử lý bởi các handler để tạo metrics, tracing hoặc cả hai, tùy cấu hình ứng dụng. Với Spring Boot 3, Micrometer Tracing thường được dùng để nối tracing với bridge và exporter tương ứng.

Các thư viện được instrument tự động có thể tạo span cho HTTP server, HTTP client hoặc một số tích hợp khác khi dependency và cấu hình phù hợp. Hãy xác minh instrumentation thực tế của từng client và framework. Với operation nghiệp vụ quan trọng chưa được quan sát, có thể tạo Observation quanh ranh giới có ý nghĩa thay vì tạo span cho mọi lời gọi hàm.

Ví dụ instrument operation giữ chỗ tồn kho:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class InventoryFacade {
    private final ObservationRegistry observationRegistry;
    private final InventoryService inventoryService;

    public InventoryFacade(
            ObservationRegistry observationRegistry,
            InventoryService inventoryService) {
        this.observationRegistry = observationRegistry;
        this.inventoryService = inventoryService;
    }

    public Reservation reserve(String sku, int quantity) {
        return Observation.createNotStarted(
                        "inventory.reserve", observationRegistry)
                .lowCardinalityKeyValue("operation", "reserve")
                .observe(() -> inventoryService.reserve(sku, quantity));
    }
}
```

Tên Observation nên ổn định và mô tả operation. Các low-cardinality key-value như `operation=reserve` có thể được dùng làm dimension cho metrics và span. Chỉ thêm key-value có giá trị điều tra; tránh đưa dữ liệu thay đổi theo từng request vào low-cardinality tags.

Khi cần gắn một giá trị chỉ có ý nghĩa ở trace, Micrometer Observation hỗ trợ high-cardinality key-value. Tuy nhiên, high-cardinality không có nghĩa là không tốn chi phí: giá trị vẫn được gửi và lưu trong tracing backend. Chỉ đưa vào những thuộc tính cần thiết, không chứa bí mật hoặc dữ liệu cá nhân không được phép ghi nhận.

### Cấu hình sampling cần có chủ đích

Với cấu hình Spring Boot hỗ trợ Micrometer Tracing, có thể đặt xác suất sampling bằng thuộc tính `management.tracing.sampling.probability`. Ví dụ dưới đây chỉ minh họa cách cấu hình; tỷ lệ thực tế phải dựa trên lưu lượng, mục tiêu điều tra, ngân sách lưu trữ và chính sách vận hành:

```yaml
management:
  tracing:
    sampling:
      probability: 0.10
```

Giá trị `0.10` có nghĩa là sampling theo xác suất 10% ở cơ chế head-based tương ứng. Hãy kiểm tra phiên bản Spring Boot, tracing bridge và exporter đang dùng để xác nhận cấu hình được áp dụng đúng. Cấu hình sampling chỉ quyết định trace nào được giữ; nó không thay thế việc instrument, propagate context hoặc cấu hình export.

## 5. Chọn sampling strategy theo mục tiêu điều tra

Sampling quyết định trace nào được ghi nhận và gửi đi. Chọn tỷ lệ quá thấp có thể làm mất các tình huống hiếm; giữ mọi trace có thể làm tăng băng thông, CPU, dung lượng lưu trữ và chi phí truy vấn.

| Cơ chế | Thời điểm quyết định | Điểm mạnh | Giới hạn khi điều tra latency |
| --- | --- | --- | --- |
| Head-based sampling | Khi trace bắt đầu | Quyết định sớm, chi phí có thể dự đoán; dễ triển khai ở ứng dụng | Chưa biết request sẽ chậm hay lỗi khi quyết định, nên có thể bỏ lỡ outlier |
| Tail-based sampling | Sau khi collector nhận đủ dữ liệu của trace | Có thể giữ trace chậm, trace lỗi hoặc trace khớp điều kiện sau khi đã biết kết quả | Cần collector có tail-sampling, bộ nhớ và chính sách phù hợp; các span của cùng trace phải được gom về cùng nơi xử lý |
| Sampling theo chính sách | Theo service, operation hoặc điều kiện được định nghĩa | Có thể dành tỷ lệ khác nhau cho luồng quan trọng | Chính sách phức tạp cần được theo dõi để tránh bỏ sót nhóm request |

Với head-based sampling, một trace có xác suất được giữ như các trace khác tại thời điểm bắt đầu, vì vậy một request chỉ trở nên chậm ở cuối hành trình vẫn có thể bị loại. Tăng sampling probability có thể tăng khả năng quan sát nhưng cũng làm tăng lượng dữ liệu trên toàn bộ request phù hợp với chính sách đó.

Tail-based sampling phù hợp khi cần ưu tiên trace có duration cao hoặc trạng thái lỗi. Collector cần chờ đủ span để đánh giá toàn trace. Nếu các span của một trace được phân phối đến nhiều collector độc lập, chính sách tail sampling có thể không có đủ dữ liệu để đưa ra quyết định đúng. Cần cấu hình routing và giới hạn bộ nhớ phù hợp với lưu lượng thực tế.

Trong môi trường production, có thể kết hợp một tỷ lệ sampling nền với chính sách giữ trace lỗi hoặc trace chậm ở tầng collector. Theo dõi số trace được nhận, số trace bị loại, độ trễ export và dung lượng collector sau mỗi lần thay đổi. Đảm bảo chính sách sampling không làm mất dữ liệu cần thiết để đáp ứng mục tiêu vận hành hoặc điều tra sự cố.

## 6. Bảo đảm trace context đi xuyên suốt request

Một trace chỉ hữu ích khi trace context được truyền qua các ranh giới xử lý. Với HTTP, các service cần inject và extract cùng một chuẩn propagation, chẳng hạn W3C Trace Context qua header `traceparent`. Nếu một service tạo trace mới thay vì tiếp tục context hiện tại, hành trình bị tách thành nhiều trace và việc phân tích critical path trở nên khó khăn.

Đặc biệt chú ý các ranh giới bất đồng bộ:

- Khi chuyển công việc sang executor hoặc thread khác, context cần được capture và restore theo cơ chế context propagation phù hợp.
- Với message broker, producer cần gắn context vào message metadata và consumer cần khôi phục context khi xử lý.
- Với scheduled job hoặc tác vụ chạy nền không bắt nguồn từ request, tạo trace mới với quan hệ phù hợp nếu có thông tin về tác vụ đã khởi tạo nó.
- Với HTTP client và database client, xác minh thư viện đang dùng có instrumentation và exporter hoạt động.

Khi kiểm tra một trace bị đứt đoạn, xác minh cả propagation lẫn instrumentation. Thiếu span có thể do thư viện chưa instrument; thiếu liên kết giữa hai service có thể do context không được truyền; span không xuất hiện trong backend cũng có thể do sampling hoặc export bị lỗi.

## 7. Giữ cardinality và thuộc tính span trong giới hạn

Metrics và traces có yêu cầu khác nhau về cardinality. Metric tag tạo ra các time series; một tag có hàng triệu giá trị khác nhau có thể khiến số series tăng rất nhanh. Vì vậy, metric nên dùng route template và các giá trị có miền hữu hạn.

| Nên dùng cho metric | Tránh dùng làm metric tag |
| --- | --- |
| `http.route=/orders/{orderId}` | `/orders/8f3...` với ID thay đổi mỗi request |
| `http.request.method=POST` | URL đầy đủ có query string tự do |
| `region=ap-southeast-1` | `user.id` hoặc `request.id` |
| `result=success` hoặc `result=failure` | Email, token, số điện thoại hoặc dữ liệu cá nhân |

Trace span có thể chứa thêm thuộc tính có cardinality cao để điều tra một request cụ thể, nhưng vẫn phải cân nhắc chi phí, quyền truy cập và thời hạn lưu trữ. Không ghi access token, session cookie, mật khẩu, dữ liệu thanh toán hoặc payload nhạy cảm vào span hay logs. Nếu cần liên kết một bản ghi nghiệp vụ với trace, ưu tiên một mã tham chiếu đã được phê duyệt và kiểm soát quyền truy cập ở hệ thống lưu trữ.

Không dùng trace ID, span ID, user ID hoặc request ID làm metric tag. Các ID này phù hợp để liên kết logs và traces, hoặc được dùng qua exemplar nếu hệ thống metrics hỗ trợ.

## 8. Liên kết metrics, logs và traces trong quy trình điều tra

Ba tín hiệu trả lời ba nhóm câu hỏi khác nhau:

| Tín hiệu | Câu hỏi chính | Cách dùng khi điều tra |
| --- | --- | --- |
| Metrics | Vấn đề phổ biến đến đâu và bắt đầu khi nào? | Xác định percentile, request rate, error rate, saturation và phạm vi ảnh hưởng |
| Traces | Một request đi qua những operation nào và chờ ở đâu? | Chọn trace đại diện, phân tích span và critical path |
| Logs | Sự kiện hoặc lỗi cụ thể nào xảy ra trong operation? | Tìm exception, retry, timeout và thông tin vận hành gắn với trace/span ID |

Một dashboard tốt nên cho phép chuyển từ histogram latency đến trace qua exemplar khi có hỗ trợ. Log của ứng dụng nên mang trace ID và span ID trong MDC hoặc trường cấu trúc tương đương để có thể truy vấn cùng trace. Các thuộc tính service, environment, version và timestamp cần nhất quán giữa ba tín hiệu.

Không nên chỉ dựa vào một trace để kết luận nguyên nhân gốc. Hãy dùng metrics để xác nhận phạm vi và xu hướng, traces để xác định operation nghi vấn, rồi logs để kiểm tra sự kiện xảy ra trong operation đó.

## 9. Ví dụ điều tra: p95 của checkout tăng sau release

Giả sử dashboard cho thấy p95 của `POST /checkout` tăng từ khoảng 450 ms lên 1,4 giây sau khi release phiên bản mới. Request rate gần như không đổi, error rate tăng nhẹ và hiện tượng tập trung ở một vùng.

Quy trình chọn trace có thể thực hiện như sau:

1. Giới hạn truy vấn vào `checkout`, route `POST /checkout`, vùng bị ảnh hưởng, phiên bản mới và khoảng 15 phút xảy ra triệu chứng.
2. Chọn một số trace quanh p95, thêm một vài trace p99 hoặc outlier, rồi chọn trace đối chứng gần p50 của cùng route và phiên bản.
3. Kiểm tra root server span và các span con. Nếu nhiều trace chậm đều có `payment.authorize` kéo dài khoảng một giây, trong khi trace đối chứng chỉ mất vài chục mili giây, đây là operation cần điều tra tiếp.
4. Mở span ở payment service, kiểm tra retry, timeout và dependency bên ngoài. Đối chiếu với metrics latency của payment, connection pool và logs có cùng trace ID.
5. So sánh với phiên bản trước hoặc vùng không bị ảnh hưởng. Nếu latency payment chỉ tăng ở phiên bản mới và logs cho thấy retry do timeout, có cơ sở để kiểm tra thay đổi client timeout, retry policy hoặc endpoint dependency trong release.

Kết luận của ví dụ không phải là mọi latency checkout đều do payment. Nếu các trace chậm có nhiều dạng critical path khác nhau, cần chia thành từng nhóm và điều tra riêng. Nếu trace không có span payment nhưng request vẫn chậm, cần kiểm tra instrumentation, context propagation và khoảng trống giữa các span.

## 10. Những lỗi thường gặp khi chọn trace

- **Chỉ chọn trace chậm nhất:** outlier có thể không đại diện cho nhóm request đang ảnh hưởng. Hãy chọn trace theo percentile và thêm trace đối chứng.
- **Dùng average để định hướng:** average che khuất tail latency. Hãy kiểm tra p95, p99 và phân bố duration.
- **Cộng duration của mọi span con:** span lồng nhau và nhánh song song làm phép cộng sai. Hãy đọc timeline và critical path.
- **Lọc bằng URL hoặc ID tự do:** dễ tạo truy vấn rộng, khó so sánh và có nguy cơ lộ dữ liệu. Dùng route template và thuộc tính đã được kiểm soát.
- **Sampling quá thấp mà không có chính sách giữ outlier:** có thể bỏ lỡ trace chậm hiếm gặp. Đánh giá head sampling hoặc tail sampling theo khả năng của hệ thống.
- **Cho rằng thiếu span nghĩa là không có operation:** kiểm tra instrumentation, propagation, sampling và export trước khi kết luận.
- **Chỉ xem trace mà không đối chiếu tín hiệu khác:** dùng metrics và logs để xác nhận phạm vi, thời điểm và nguyên nhân.

## 11. Checklist trước khi kết luận

- [ ] Đã xác định service, operation, khoảng thời gian và percentile đang bị ảnh hưởng.
- [ ] Trace được lọc theo route template, phiên bản và vùng phù hợp.
- [ ] Có trace gần p95/p99, trace outlier khi cần và trace đối chứng bình thường.
- [ ] Root span, span con quan trọng, trạng thái và trace context đủ để diễn giải.
- [ ] Critical path được xác định bằng timeline; không cộng duration span một cách máy móc.
- [ ] Logs có thể liên kết bằng trace ID/span ID và metrics xác nhận phạm vi ảnh hưởng.
- [ ] Sampling, propagation và exporter không làm mất nhóm trace cần điều tra.
- [ ] Các thuộc tính được ghi nhận không tạo cardinality không kiểm soát hoặc chứa dữ liệu nhạy cảm.
- [ ] Giả thuyết nguyên nhân được kiểm tra trên nhiều trace và nhiều tín hiệu.

Chọn trace tốt giúp thu hẹp điều tra từ một biểu đồ latency thành một operation có bằng chứng cụ thể. Chất lượng kết luận phụ thuộc vào việc chọn đúng nhóm request, giữ được trace context xuyên suốt, đọc đúng critical path và đối chiếu kết quả với metrics cùng logs. Đây là cách dùng distributed tracing như một phần của kiến trúc observability trong Spring Boot, thay vì chỉ thu thập trace để xem khi có sự cố.
