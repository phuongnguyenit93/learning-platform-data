# Không dùng raw URL làm metric tag trong Spring Boot

Trong chương **HTTP server observability** của module **SPRING_BOOT_OBSERVABILITY**, một nguyên tắc quan trọng là không đưa raw URL hoặc raw request path vào metric tags. URL thực tế thường chứa identifier như order ID, user ID, token, search term hoặc query string. Nếu mỗi request tạo một giá trị tag khác nhau, số time series có thể tăng theo lưu lượng thay vì theo số loại hoạt động của ứng dụng.

Spring Boot Actuator và Micrometer có thể tự động thu thập HTTP server metrics như http.server.requests. Các dimension phù hợp để tổng hợp thường là HTTP method, status, outcome và **route template**. Route template biểu diễn mẫu đường dẫn như /orders/{orderId}, trong khi raw path là /orders/ORD-98431. Hai request tới hai order khác nhau nên được tổng hợp vào cùng một nhóm route khi mục tiêu đo là hiệu năng endpoint.

Trong module **SPRING_BOOT_OBSERVABILITY**, HTTP server metrics cần bổ sung cho logs và distributed tracing. Metrics giúp nhìn xu hướng request rate, error rate và latency; logs/traces cung cấp chi tiết để điều tra request cụ thể. Không dùng metric tags để cố lưu mọi thông tin của từng request. Bài này giải thích cardinality, route normalization, cấu hình Spring Boot/Micrometer, ranh giới low/high-cardinality và cách kiểm tra thực tế.

## 1. Raw URL làm metric tag gây vấn đề gì?

Giả sử API có endpoint:

```text
GET /orders/ORD-10001
GET /orders/ORD-10002
GET /orders/ORD-10003
...
```

Nếu metric tag uri chứa raw path, mỗi order ID tạo một giá trị tag khác nhau:

```text
http.server.requests{method="GET", uri="/orders/ORD-10001", status="200"}
http.server.requests{method="GET", uri="/orders/ORD-10002", status="200"}
http.server.requests{method="GET", uri="/orders/ORD-10003", status="200"}
```

Một metric series thường được nhận diện bởi tên metric và tập tags. Chỉ cần một tag có vô số giá trị, mỗi tổ hợp tag mới có thể tạo thêm một time series. Với request ID, order ID hoặc query string khác nhau liên tục, cardinality tăng gần theo số request.

Hậu quả:

- **Bộ nhớ tăng:** registry, exporter và backend phải quản lý nhiều series hơn.
- **Chi phí ingest/index tăng:** backend cần lưu metadata và điểm dữ liệu cho từng series.
- **Query chậm:** truy vấn phải xử lý nhiều series và label combinations.
- **Dashboard kém hữu ích:** biểu đồ bị phân mảnh thành hàng nghìn đường riêng cho từng request.
- **Nguy cơ cạn tài nguyên:** registry/backend có thể đạt giới hạn cardinality, từ chối hoặc làm giảm chất lượng telemetry.
- **Rò rỉ dữ liệu:** URL có thể chứa email, access token, search term hoặc dữ liệu nghiệp vụ.

Metric tag nên trả lời câu hỏi tổng hợp như “route nào chậm?”, “method nào lỗi?”, “status class nào tăng?”. Nó không nên trở thành bản ghi chi tiết của từng request.

## 2. Phân biệt raw URL, raw path và route template

| Giá trị | Ví dụ | Đặc tính |
| --- | --- | --- |
| Full URL | https://api.example.com/orders/ORD-10001?expand=items | Gồm scheme, host, path và query |
| Raw path | /orders/ORD-10001 | Có thể chứa ID hoặc slug riêng cho từng request |
| Route template | /orders/{orderId} | Biểu diễn mẫu route có số giá trị hữu hạn |

Route template phù hợp hơn cho HTTP metric tags vì nhiều request được gộp vào cùng một endpoint logic.

| Request thực tế | Route template |
| --- | --- |
| /orders/ORD-10001 | /orders/{orderId} |
| /orders/ORD-10002 | /orders/{orderId} |
| /customers/C-301/orders | /customers/{customerId}/orders |
| /customers/C-988/orders | /customers/{customerId}/orders |
| /health/readiness | /health/readiness |

Không phải mọi path đều tự động chuyển thành template. Nếu route được dựng động, request đi vào fallback mapping hoặc framework không xác định được handler pattern, metric có thể hiển thị UNKNOWN hoặc một route fallback theo integration/version. Cần kiểm tra dữ liệu thực tế thay vì giả định framework luôn tìm được template.

### Query string cũng là một nguồn cardinality

Hai request có thể cùng path nhưng query khác nhau:

```text
GET /search?q=micrometer
GET /search?q=spring-boot
GET /search?q=distributed-tracing
```

Nếu full URL được ghi vào tag, từng search term sẽ tạo dimension khác nhau. Query string còn có thể chứa email, token, filter riêng của người dùng hoặc dữ liệu nhạy cảm. Xóa query string khỏi URL tag vẫn chưa đủ nếu raw path còn chứa ID; cần route template.

### Host và port cũng cần được kiểm soát

Nếu một service nhận traffic qua nhiều hostname hoặc tenant-specific subdomain, tag host có thể có rất nhiều giá trị. Đưa hostname đầy đủ hoặc port động vào metrics cần có lý do rõ ràng. Nếu mục tiêu là phân biệt deployment, nên dùng resource/service metadata ổn định hoặc dimension đã chuẩn hóa, không dùng host header tùy ý từ client.

## 3. Cardinality tăng theo tổ hợp tags

Số series tối đa theo phép nhân đơn giản:

\[
\text{Series} \approx \prod_{i=1}^{n} \text{Số giá trị của tag}_i
\]

Giả sử một HTTP timer có:

| Tag | Số giá trị giả định |
| --- | ---: |
| method | 5 |
| uri là route template | 30 |
| status | 6 |
| outcome | 4 |
| region | 3 |
| **Tích tối đa lý thuyết** | **10.800** |

Với raw path, nếu trong ngày có 500.000 order ID khác nhau, tổ hợp series có thể tăng từ vài nghìn lên hàng trăm triệu theo mô hình đơn giản. Thực tế registry/backend có thể áp giới hạn hoặc aggregation khác, nhưng cardinality lớn vẫn gây chi phí và áp lực tài nguyên đáng kể.

Với histogram, mỗi series còn có các bucket/time series liên quan tùy backend representation. Số series được nhân với số route, method, status combinations, region và instance. Không chỉ số request mới quan trọng; số tổ hợp tag và cách histogram được xuất cũng quan trọng.

**Cardinality không chỉ là một tag đơn lẻ.** Nhiều tag có tập giá trị vừa phải vẫn có thể nhân lên thành số series rất lớn.

## 4. HTTP server metrics trong Spring Boot/Micrometer

Với Spring Boot Actuator và web stack được hỗ trợ, Micrometer có thể tự instrument HTTP server requests. Metric thường gặp là http.server.requests. Đây là timer cho request, thường cung cấp count, total time và histogram/distribution nếu được cấu hình.

Các tags thường gặp tùy stack/version:

| Tag | Ví dụ | Lý do phù hợp |
| --- | --- | --- |
| method | GET, POST | Tập phương thức hữu hạn |
| uri | /orders/{orderId} | Route template, không phải raw path |
| status | 200, 404, 500 | Tập status hữu hạn |
| outcome | SUCCESS, CLIENT_ERROR, SERVER_ERROR | Nhóm kết quả hữu hạn |
| exception | Tên lớp exception hoặc None | Cần kiểm soát tập giá trị và semantics |

Tags chính xác và cách xử lý route phụ thuộc Spring Boot, Spring Framework, servlet/reactive stack và convention đang dùng. Kiểm tra metric endpoint hoặc registry output để xem giá trị thực tế. Không hardcode dashboard dựa trên tag chưa được xác minh.

Ví dụ cấu hình ứng dụng:

```yaml
spring:
  application:
    name: orders-service

management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
```

Đoạn cấu hình minh họa việc expose endpoint phù hợp và bật histogram cho HTTP timer trong các phiên bản Spring Boot hỗ trợ property này. Chỉ expose endpoint theo chính sách quản trị; không mở metrics endpoint công khai không kiểm soát. Histogram cần được bật theo nhu cầu và ngân sách cardinality/storage.

Có thể kiểm tra một metric qua Actuator metrics endpoint:

```http
GET /actuator/metrics/http.server.requests
```

Actuator metrics endpoint giúp xem dữ liệu metric trong registry; nó không nhất thiết là định dạng scrape Prometheus. Nếu dùng Prometheus registry, kiểm tra /actuator/prometheus để xem tên và labels exposition thực tế. Chỉ dùng thông tin từ response thực tế để xác nhận tags.

## 5. Spring MVC: route template đến từ mapping

Trong Spring MVC, framework biết handler mapping như:

```java
@RestController
@RequestMapping("/orders")
class OrderController {

    @GetMapping("/{orderId}")
    OrderResponse getOrder(@PathVariable String orderId) {
        return orderService.find(orderId);
    }
}
```

Hai request /orders/ORD-10001 và /orders/ORD-10002 cùng khớp một mapping là /orders/{orderId}. HTTP server observation có thể dùng pattern đó làm uri tag.

Đừng tự thêm raw request.getRequestURI() vào http.server.requests qua customizer hoặc filter. Nếu cần dimension bổ sung, hãy dùng route template đã được framework resolve hoặc route name ổn định do ứng dụng định nghĩa.

Khi route không được mapping rõ, có thể dùng giá trị fallback như NOT_FOUND hoặc UNKNOWN tùy convention, thay vì raw path. Đây là lựa chọn an toàn hơn vì mọi URL không khớp không tạo một giá trị tag riêng.

## 6. Spring WebFlux: giữ route cardinality ổn định

Với WebFlux, handler mapping cũng có thể cung cấp route pattern. Ví dụ:

```java
@RestController
@RequestMapping("/payments")
class PaymentController {

    @GetMapping("/{paymentId}")
    Mono<PaymentResponse> getPayment(
            @PathVariable String paymentId) {
        return paymentService.find(paymentId);
    }
}
```

Route template /payments/{paymentId} giúp gom các request có payment ID khác nhau. Trong reactive stack, không tự lấy raw path và gắn vào metric tag trong WebFilter; hãy dùng observation/convention được tích hợp với framework để lấy route pattern sau khi mapping được xác định.

Nếu custom WebFilter tạo observation quá sớm, handler mapping có thể chưa chạy và route template chưa có. Trong trường hợp đó, giá trị uri có thể chưa được biết. Tránh lấp chỗ trống bằng raw path; để convention/framework hoàn tất sau mapping hoặc dùng fallback có cardinality thấp.

## 7. Low-cardinality và high-cardinality trong Micrometer Observation

Micrometer Observation phân biệt key-value có cardinality thấp và cao:

- **Low-cardinality key-values:** thích hợp cho metrics vì số giá trị dự kiến được giới hạn.
- **High-cardinality key-values:** có thể hữu ích cho tracing/log context để điều tra từng operation, nhưng không nên trở thành metric labels.

Ví dụ với một business observation:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
class OrderService {
    private final ObservationRegistry observationRegistry;

    OrderService(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    OrderResponse findOrder(String orderId, String channel) {
        return Observation.createNotStarted(
                    "orders.lookup",
                    observationRegistry)
                .lowCardinalityKeyValue("channel", normalizeChannel(channel))
                .highCardinalityKeyValue("order.id", orderId)
                .observe(() -> loadOrder(orderId));
    }

    private String normalizeChannel(String channel) {
        if ("mobile".equals(channel)) return "mobile";
        if ("partner".equals(channel)) return "partner";
        return "web";
    }

    private OrderResponse loadOrder(String orderId) {
        return orderRepository.findResponse(orderId);
    }
}
```

Đây là ví dụ khái niệm cho custom business observation. channel được chuẩn hóa về tập hữu hạn để có thể dùng trong metrics; order.id là high-cardinality metadata và có thể xuất hiện ở tracing handlers tùy convention/exporter. Việc đặt nó ở high-cardinality không đồng nghĩa nên lưu mọi order ID trong mọi backend; cần cân nhắc dữ liệu nhạy cảm, sampling, access và retention.

**Không đổi high-cardinality thành low-cardinality chỉ để nó xuất hiện trên dashboard.** Nếu cần truy vấn một order cụ thể, dùng logs hoặc trace attributes theo chính sách; metric label không phải kho tra cứu từng giao dịch.

## 8. Customizing server observation mà không dùng raw URL

Khi cần thay đổi tags của HTTP server observations, hãy tìm hiểu convention/context của stack và version đang dùng. Với Spring MVC, framework có thể cung cấp URI pattern sau khi handler đã được chọn; với WebFlux, route pattern có thể xuất hiện ở giai đoạn sau trong pipeline. Custom convention nên dùng metadata đã chuẩn hóa, không lấy raw URL làm uri.

Quy tắc thiết kế:

1. Giữ method từ HTTP method enum/string chuẩn hóa.
2. Dùng route template, route ID hoặc fallback cố định.
3. Dùng status/status class và outcome hữu hạn.
4. Exception tag nên là loại exception đã kiểm soát, không phải message.
5. Không đưa query string, request ID, user ID, IP tùy ý hoặc header value vào metric tags.
6. Nếu cần thông tin chi tiết, đặt ở tracing span attributes hoặc structured logs theo privacy policy.

Một convention tùy biến không nên cố tạo route template từ raw path bằng cách xóa chuỗi số hoặc UUID theo regex tổng quát. URL có thể có slug, mã đơn hàng dạng chữ, nested IDs và segment tùy nghiệp vụ. Regex đơn giản dễ bỏ sót trường hợp và đôi khi gộp nhầm hai endpoint khác nhau. Lấy route template từ framework mapping hoặc khai báo route name ổn định.

## 9. Vì sao không dùng query parameter, host hoặc client IP làm metric tag?

| Candidate tag | Vấn đề | Cách thay thế |
| --- | --- | --- |
| Full URL | Host/path/query tạo nhiều combinations | Route template và service/resource metadata |
| Raw path | Path segment có ID/slug riêng | URI template hoặc route name |
| Query string | Search term/filter/token thay đổi liên tục | Category hữu hạn nếu thật sự cần |
| Host header | Caller có thể gửi giá trị tùy ý | Deployment/service identity đã chuẩn hóa |
| Client IP | Rất nhiều địa chỉ và có thể là dữ liệu cá nhân | Nhóm theo network class/region nếu có căn cứ |
| User-Agent | Chuỗi tự do, nhiều version/device | Nhóm client family đã chuẩn hóa |
| Correlation ID/Trace ID | Gần như duy nhất mỗi request | Dùng logs/traces và exemplars |
| Exception message | Nội dung tùy biến, có thể chứa dữ liệu nhạy cảm | Exception class hoặc outcome đã kiểm soát |

Không phải mọi dimension có cardinality vừa phải đều mặc nhiên an toàn. Client IP hoặc tenant ID có thể nhạy cảm theo chính sách tổ chức; ngoài cardinality còn phải đánh giá privacy, access và purpose.

## 10. Liên kết metrics với logs và traces

Metrics cần cardinality thấp để thể hiện xu hướng; logs/traces có thể giữ chi tiết theo phạm vi kiểm soát:

```text
Metric:
http.server.requests{
  method="GET",
  uri="/orders/{orderId}",
  status="500"
}
      |
      v
Dashboard phát hiện route có error rate tăng
      |
      +--> Logs: tìm theo correlationId / traceId
      |
      +--> Trace: xem spans nếu trace được sampled và export
```

Ví dụ log:

```json
{
  "service.name": "orders-service",
  "event": "order.lookup.failed",
  "route": "/orders/{orderId}",
  "correlationId": "req-7f31c8a2",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "error.type": "OrderNotFoundException"
}
```

Log có thể chứa Correlation ID/Trace ID để tìm request cụ thể. Trace có thể được sampling nên không đảm bảo mọi log đều mở được trace. Metrics vẫn tổng hợp toàn bộ request theo dimension đã chọn và không cần chứa IDs.

Một số metrics backend hỗ trợ **exemplars**, cho phép một sample histogram/counter liên kết tới trace context mà không thêm Trace ID làm label cho toàn bộ series. Exemplar cần hỗ trợ tương thích từ registry/exporter tới backend/UI; nó không đảm bảo trace được giữ nếu sampling đã loại trace đó.

## 11. Kiểm tra raw URL đã lọt vào metrics hay chưa

Không chỉ xem code, hãy kiểm tra registry output thực tế:

1. Gửi nhiều request tới cùng route template nhưng khác path variable.
2. Gửi request với query parameter khác nhau.
3. Xem metric http.server.requests ở Actuator hoặc Prometheus exposition.
4. Xác nhận uri là route template/fallback giống nhau, không chứa từng ID hoặc query.
5. Gọi endpoint không tồn tại với nhiều raw path; xác nhận fallback không tạo mỗi path một tag value.
6. Kiểm tra custom metrics và custom observations do ứng dụng thêm.
7. Quan sát số active series/cardinality ở backend trước và sau test.

Ví dụ test:

```bash
curl -i http://localhost:8080/orders/ORD-10001
curl -i http://localhost:8080/orders/ORD-10002
curl -i "http://localhost:8080/search?q=micrometer"
curl -i "http://localhost:8080/search?q=spring-boot"
```

Sau khi các request hoàn tất, metric output nên có route templates ổn định như /orders/{orderId} và /search. Nếu output có /orders/ORD-10001 hoặc query string, cần tìm convention/filter/customizer đã thêm giá trị raw.

Actuator metrics endpoint có thể hiển thị tag values theo từng metric. Với Prometheus, xem exposition thực tế và đối chiếu series labels sau khi scrape. Backend có thể chuẩn hóa tên metric, nên xác định metric tương ứng thay vì chỉ tìm một chuỗi tên đoán trước.

### Một kiểm tra tự động ở mức integration test

Có thể kiểm tra response của metrics endpoint sau khi tạo request:

```java
mockMvc.perform(get("/orders/ORD-10001")).andExpect(status().isOk());
mockMvc.perform(get("/orders/ORD-10002")).andExpect(status().isOk());

MvcResult metrics = mockMvc.perform(
        get("/actuator/metrics/http.server.requests"))
    .andExpect(status().isOk())
    .andReturn();

String body = metrics.getResponse().getContentAsString();
assertThat(body).contains("/orders/{orderId}");
assertThat(body).doesNotContain("ORD-10001");
assertThat(body).doesNotContain("ORD-10002");
```

Đây là pseudocode kiểm thử dựa trên MockMvc/AssertJ; cú pháp chính xác phụ thuộc test setup, path mapping và metric endpoint được expose. Khi Actuator response phân trang/format khác hoặc metric tag key khác, điều chỉnh assertion theo output thật. Kiểm tra nhiều requests trong cùng test để chứng minh hai ID khác nhau được gom vào cùng route tag.

Không chỉ kiểm tra uri. Raw value có thể bị gắn dưới tag custom như path, url, request, endpoint, tenant, client hoặc query. Nên kiểm tra danh sách tag keys và kiểm soát custom MeterFilters/ObservationConventions toàn cục.

## 12. Hạn chế và xử lý route không xác định

Một số request không khớp route:

- Static resource hoặc error dispatch.
- Request malformed bị từ chối trước khi mapping.
- Gateway rewrite path không như dự kiến.
- Custom servlet filter tạo observation trước handler mapping.
- Reactive route chưa được resolve tại thời điểm tag được tạo.

Không dùng raw request path làm fallback. Có thể dùng giá trị cố định như UNKNOWN hoặc NOT_FOUND nếu semantics phù hợp. Đồng thời theo dõi tỷ lệ UNKNOWN như một dimension hữu hạn để phát hiện instrumentation/mapping chưa đầy đủ.

Nếu mọi request bình thường đều ra UNKNOWN, kiểm tra thứ tự tạo observation và convention của framework. Đừng giải quyết bằng cách ghi toàn bộ path; hãy sửa integration để route pattern có mặt ở đúng thời điểm.

## 13. Những sai lầm phổ biến

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Gắn request.getRequestURI() vào metric | Raw path thường chứa ID | Dùng route template |
| Gắn request.getRequestURL() | Gồm scheme/host/path và có thể tạo giá trị riêng | Dùng route + service resource |
| Gắn query string | Mỗi search/filter khác nhau tạo series mới | Bỏ query, dùng category hữu hạn nếu cần |
| Gắn Trace ID vào timer | Gần như một series mỗi request | Dùng exemplar hoặc logs/traces |
| Regex raw path để thay UUID | Bỏ sót ID chữ và dễ gộp route sai | Dùng framework route mapping |
| Gắn exception message | Message không giới hạn, có thể chứa PII | Dùng exception class/outcome |
| Tạo URI tag tùy biến ở filter quá sớm | Chưa có route template | Lấy mapping sau khi resolve |
| Chỉ kiểm tra dashboard | Backend có thể đã áp giới hạn/cardinality cap | Kiểm tra registry và scrape output |

## 14. Bài tập tình huống

Một API có endpoint GET /customers/{customerId}/orders. Team thêm metric tag như sau:

```java
registry.counter(
        "http.server.requests.custom",
        "method", request.getMethod(),
        "path", request.getRequestURI())
    .increment();
```

Sau một ngày, số series tăng lên hàng triệu. Dashboard không thể lọc theo route vì mỗi khách hàng tạo một đường riêng. Trong khi đó, Trace ID đã có trong logs.

**Câu hỏi:**

1. Nguyên nhân trực tiếp làm cardinality tăng là gì?
2. Nên thay raw path bằng giá trị nào?
3. Nếu cần tìm log của một customer request cụ thể, nên dùng signal nào?
4. Có thể thêm Trace ID làm tag để nối metrics với logs không?
5. Nên viết test nào để tránh lỗi quay trở lại?

**Gợi ý phân tích:**

- request.getRequestURI() trả raw path như /customers/C-123/orders; mỗi customer ID có thể tạo một tag value và series mới.
- Dùng route template /customers/{customerId}/orders hoặc route name ổn định được resolve từ framework.
- Dùng structured logs/Correlation ID/Trace ID và tracing backend theo quyền truy cập để điều tra từng request.
- Không. Trace ID là high-cardinality; dùng log/trace correlation hoặc exemplar nếu metrics stack hỗ trợ.
- Gửi nhiều request có customer IDs khác nhau, kiểm tra metric endpoint/Prometheus labels phải chỉ có cùng route template và không có ID raw.

### Checklist hoàn thành

| Nội dung | Có thể giải thích/kiểm tra |
| --- | --- |
| Raw URL và route template | Phân biệt full URL, raw path và mẫu route |
| Cardinality | Tính tác động của tổ hợp tags và histogram |
| HTTP server metrics | Biết vai trò của http.server.requests |
| Spring MVC/WebFlux | Dùng route mapping thay raw request path |
| Micrometer Observation | Phân biệt low- và high-cardinality key-values |
| Query/host/IP | Tránh giá trị tự do làm metric dimensions |
| Logs/traces | Dùng IDs ở logs/traces thay metric tags |
| Exemplars | Biết giới hạn và yêu cầu tương thích |
| Unknown route | Dùng fallback hữu hạn và kiểm tra mapping |
| Integration test | Gửi nhiều IDs khác nhau, xác minh metric tag ổn định |

**Ghi nhớ:** Không dùng raw URL, raw path hoặc query string làm metric tag vì các giá trị này có thể thay đổi theo từng request, làm cardinality tăng đột biến và vô tình lưu dữ liệu nhạy cảm. Với HTTP server metrics trong Spring Boot, hãy dùng route template hoặc route name ổn định, method/status/outcome có tập giá trị hữu hạn. Micrometer Observation phân biệt low-cardinality values dành cho metrics và high-cardinality metadata dành cho tracing/log context. Để điều tra một request cụ thể, dùng Correlation ID, Trace ID, logs và traces theo policy; kiểm tra registry output và backend series để bảo đảm tag thực tế không chứa URL động.
