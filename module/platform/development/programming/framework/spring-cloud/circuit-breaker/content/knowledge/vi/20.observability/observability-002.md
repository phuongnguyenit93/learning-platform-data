# Đọc số lời gọi thành công, lỗi và bị từ chối

Khi vận hành circuit breaker trong Spring Cloud, ba nhóm số liệu cần đọc cùng nhau là **lời gọi thành công**, **lời gọi lỗi** và **lời gọi bị từ chối**. Chúng mô tả ba kết quả khác nhau của cơ chế bảo vệ: supplier đã trả kết quả bình thường, supplier đã phát sinh lỗi, hoặc breaker đã chặn lời gọi trước khi supplier được chạy.

Không nên gộp cả ba thành một chỉ số lỗi duy nhất. Số lời gọi lỗi giúp đánh giá chất lượng của phụ thuộc; số lời gọi bị từ chối cho biết breaker đang ngăn bao nhiêu request đi tiếp; số lời gọi thành công cho biết lượng công việc được thực hiện bình thường. Khi đối chiếu các số liệu này với trạng thái `CLOSED`, `OPEN`, `HALF_OPEN`, latency và metric HTTP client, đội vận hành có thể phân biệt backend đang lỗi với breaker đang chủ động bảo vệ hệ thống.

## 1. Ba kết quả chính của một lời gọi

Với Resilience4j, một lời gọi được đưa qua circuit breaker thường kết thúc theo một trong các trường hợp sau:

| Kết quả | Ý nghĩa | Supplier có chạy không? | Ảnh hưởng tới thống kê breaker |
|---|---|---|---|
| Success | Supplier hoàn tất bình thường và trả kết quả | Có | Ghi nhận một lời gọi thành công |
| Error/Failed | Supplier phát sinh exception được phân loại là lỗi | Có | Ghi nhận một lời gọi lỗi |
| Not permitted | Breaker không cấp permission, thường vì đang `OPEN` hoặc hết lượt thăm dò | Không | Ghi nhận một lời gọi bị từ chối; không phải lỗi vừa trả về từ backend |
| Ignored | Exception được cấu hình bỏ qua | Có | Không tính vào success hoặc failure rate; có thể được theo dõi riêng |

Điểm phân biệt quan trọng là `not permitted` không phải một lần gọi HTTP thất bại. Khi breaker từ chối, supplier chưa được thực thi nên backend không nhận request đó qua supplier. Ngược lại, `failed` thường có nghĩa lời gọi đã được thử và supplier phát sinh exception.

Một lời gọi `success` cũng chỉ có nghĩa supplier hoàn tất theo cách breaker xem là thành công. Nó không tự chứng minh dữ liệu nghiệp vụ đúng. Ví dụ, nếu HTTP client được cấu hình để chuyển HTTP 404 thành một đối tượng kết quả, breaker có thể ghi nhận success dù nghiệp vụ không tìm thấy tài nguyên. Cách ánh xạ HTTP status thành exception hoặc kết quả cần nhất quán với chính sách phân loại lỗi.

## 2. Metric calls của Resilience4j

Khi tích hợp Micrometer, Resilience4j có thể xuất metric cho từng circuit breaker. Một meter thường dùng để theo dõi kết quả lời gọi là `resilience4j.circuitbreaker.calls`. Metric này phân loại lời gọi theo `kind`, thường gồm các giá trị như `successful`, `failed`, `not_permitted` và `ignored`, đồng thời gắn với tên breaker.

| Nhóm metric | Thông tin cần đọc | Câu hỏi vận hành |
|---|---|---|
| Calls `successful` | Số lượng và thời gian thực thi của lời gọi thành công | Bao nhiêu lời gọi được thực hiện bình thường? Latency có tăng không? |
| Calls `failed` | Số lượng và thời gian thực thi của lời gọi lỗi | Phụ thuộc đang thất bại bao nhiêu lần? Lỗi tăng từ khi nào? |
| Calls `not_permitted` | Số lời gọi bị breaker từ chối | Breaker đang chặn bao nhiêu request? |
| Calls `ignored` | Số exception được cấu hình bỏ qua | Có loại lỗi nào thường xuất hiện nhưng không tham gia failure rate? |

Meter `calls` thường cung cấp thông tin thời gian thực thi cùng số lần ghi nhận; backend Micrometer có thể biểu diễn dữ liệu dưới dạng Timer và chuyển thành chuỗi thời gian tương ứng. Tên meter, tag và cách exporter hiển thị có thể khác theo phiên bản Resilience4j, Micrometer và registry. Khi triển khai, hãy kiểm tra meter thực tế trong ứng dụng thay vì giả định tên Prometheus cuối cùng luôn giống nhau.

Ngoài calls, nên quan sát trạng thái breaker và thống kê sliding window. Các metric thường có thể tìm thấy trong nhóm `resilience4j.circuitbreaker`, chẳng hạn state, failure rate, slow call rate và số mẫu đã ghi nhận. Tên cụ thể và tập tag cần xác nhận trên endpoint metrics của phiên bản đang dùng.

## 3. Success không đồng nghĩa với toàn bộ request của người dùng thành công

Metric success của circuit breaker phản ánh kết quả supplier được bảo vệ. Nếu supplier trả về một giá trị bình thường, breaker có thể ghi nhận success ngay cả khi giá trị đó thể hiện một tình huống nghiệp vụ như không tìm thấy dữ liệu, từ chối đơn hàng hoặc tồn kho bằng 0.

Ví dụ:

```java
InventoryView view = circuitBreaker.run(
        () -> inventoryClient.find(sku),
        error -> InventoryView.unavailable(sku)
);
```

Nếu `inventoryClient.find(sku)` trả về `InventoryView.notFound()` như một kết quả bình thường, breaker có thể ghi nhận success. Nếu supplier ném exception, breaker ghi nhận lỗi theo cấu hình và fallback có thể trả `InventoryView.unavailable(sku)`. Giá trị fallback trả về cho caller không biến lần supplier thất bại thành success trong thống kê breaker.

Do đó, cần phân biệt:

- **Circuit breaker success:** supplier được thực thi và hoàn tất bình thường theo quy tắc phân loại.
- **HTTP success:** HTTP client nhận status được xem là thành công theo cấu hình của client.
- **Business success:** nghiệp vụ hoàn tất đúng yêu cầu của người dùng.

Ba khái niệm có thể tương quan nhưng không đồng nhất. Dashboard cần metric nghiệp vụ riêng nếu đội vận hành muốn biết tỷ lệ đơn hàng tạo thành công, số lượng SKU không tồn tại hoặc số giao dịch bị từ chối.

## 4. Đọc số lời gọi lỗi đúng ngữ cảnh

Một lời gọi được ghi nhận là failure khi supplier phát exception và exception đó được chính sách circuit breaker xem là lỗi. Các nguyên nhân thường gặp gồm:

- Connect timeout hoặc read/response timeout.
- Connection refused, DNS failure hoặc lỗi định tuyến mạng.
- HTTP 5xx được HTTP client chuyển thành exception.
- Exception từ dịch vụ phụ thuộc hoặc lỗi giải mã response.
- Lỗi lập trình bên trong supplier, nếu không được phân loại hoặc bỏ qua.

Không phải mọi exception đều nên góp vào failure rate. Resilience4j hỗ trợ `recordExceptions`, `ignoreExceptions` và predicate để phân loại kết quả. Exception bị ignore không được tính là success hoặc failure trong sliding window. Vì vậy, số `failed` trên dashboard cần được đọc cùng cấu hình phân loại lỗi.

Ví dụ cấu hình:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        recordExceptions:
          - java.net.SocketTimeoutException
          - java.net.ConnectException
          - java.net.UnknownHostException
        ignoreExceptions:
          - com.example.inventory.InvalidSkuException
```

Danh sách trên chỉ minh họa. Nếu HTTP client bọc exception trong `ResourceAccessException` hoặc `WebClientRequestException`, cần cấu hình đúng lớp exception mà breaker nhận được hoặc dùng predicate kiểm tra cause chain. Nếu phân loại sai, lỗi hạ tầng có thể không được tính vào failure rate hoặc lỗi nghiệp vụ có thể làm breaker mở không cần thiết.

## 5. Đọc số lời gọi bị từ chối

Metric `not_permitted` phản ánh số lần breaker không cấp quyền thực thi. Trường hợp phổ biến là breaker đang `OPEN`. Khi hết thời gian chờ và chuyển sang `HALF_OPEN`, số lượt gọi thăm dò được giới hạn bởi `permittedNumberOfCallsInHalfOpenState`; lời gọi bổ sung khi không còn permission cũng có thể bị từ chối.

Số lời gọi bị từ chối tăng không nhất thiết là dấu hiệu xấu của chính breaker. Nó có thể cho thấy cơ chế đang làm đúng nhiệm vụ: chặn request để tránh tiếp tục gây tải lên một phụ thuộc đang lỗi hoặc quá chậm.

Ví dụ:

- Dịch vụ tồn kho bắt đầu timeout và breaker chuyển sang `OPEN`.
- Trong 10 giây tiếp theo, 500 request đến gateway.
- Breaker từ chối các lời gọi đến tồn kho và gateway trả fallback trạng thái không sẵn có.
- Metric `not_permitted` tăng, trong khi metric HTTP client của gateway không tăng tương ứng vì supplier không chạy.

Nếu chỉ nhìn số `not_permitted`, dashboard có thể trông như lỗi tăng mạnh. Nhưng khi đối chiếu trạng thái breaker và HTTP client, có thể thấy hệ thống đang ngăn 500 request tiếp tục đi vào backend. Đây là chỉ số về tác động của chính sách bảo vệ, không phải số lỗi backend vừa trả.

## 6. Tính failure rate và chọn mẫu số phù hợp

Về mặt thống kê, failure rate của circuit breaker dựa trên các lời gọi được ghi nhận là success hoặc failure trong sliding window; exception bị ignore không tham gia phép tính. Lời gọi bị từ chối cũng không phải một kết quả supplier success/failure.

Một cách diễn giải phổ biến là:

\[
\text{Failure rate} = \frac{\text{Failed calls}}{\text{Successful calls} + \text{Failed calls}} \times 100\%
\]

Không cộng `not_permitted` vào mẫu số khi tính tỷ lệ lỗi của supplier. Nếu thêm các request bị từ chối vào mẫu số, tỷ lệ lỗi backend có thể bị giảm giả tạo đúng lúc breaker đang chặn nhiều traffic.

Ví dụ trong một khoảng quan sát:

| Kết quả | Số lượng |
|---|---:|
| Successful | 700 |
| Failed | 100 |
| Not permitted | 400 |
| Ignored | 20 |

Failure rate theo kết quả supplier là (100 / (700 + 100) = 12.5\%\). 400 lời gọi bị từ chối không được đưa vào mẫu số này vì supplier không chạy. 20 ignored cũng không được tính vào success hoặc failure.

Nếu câu hỏi vận hành là “bao nhiêu request người dùng không nhận được dữ liệu từ phụ thuộc?”, cần định nghĩa một chỉ số khác có thể bao gồm cả lỗi supplier lẫn từ chối bởi breaker. Không nên gọi chỉ số đó là failure rate của circuit breaker nếu mẫu số và ý nghĩa khác với thống kê nội bộ của breaker.

## 7. Đối chiếu counters với trạng thái breaker

Các counters có ý nghĩa hơn khi được đọc cùng trạng thái hiện tại và sự kiện chuyển trạng thái.

| Quan sát | Diễn giải có thể có | Cần kiểm tra thêm |
|---|---|---|
| Failed tăng, state vẫn `CLOSED` | Đang có lỗi nhưng chưa đủ mẫu hoặc chưa vượt ngưỡng | `minimumNumberOfCalls`, failure rate, sliding window |
| Failed tăng rồi state chuyển `OPEN` | Breaker đã phát hiện phụ thuộc lỗi theo ngưỡng | Exception class, thời điểm chuyển trạng thái, fallback |
| Not permitted tăng, state `OPEN` | Breaker đang chặn lời gọi | Thời gian ở `OPEN`, tỷ lệ lỗi/slow call trước đó |
| Not permitted tăng trong `HALF_OPEN` | Permission thăm dò đã được cấp hết hoặc request đến vượt giới hạn | `permittedNumberOfCallsInHalfOpenState`, kết quả probe |
| Successful tăng sau khi `HALF_OPEN` về `CLOSED` | Các lời gọi thăm dò cho thấy phụ thuộc có thể phục hồi | Latency và tỷ lệ lỗi sau khi lưu lượng bình thường trở lại |
| Successful tăng nhưng slow call rate cũng tăng | Phụ thuộc trả kết quả nhưng đang chậm | Latency percentile, queue, connection pool, thread pool |
| Failed thấp nhưng fallback cao | Có thể nhiều lời gọi bị từ chối hoặc fallback ở tầng khác | Not permitted, fallback counter riêng và lỗi client |

Metric state thường được biểu diễn bằng gauge theo tên breaker và trạng thái. Tùy phiên bản, trạng thái có thể được mã hóa bằng tag hoặc giá trị số. Hãy dùng meter và tag được exporter thực tế cung cấp, không giả định một encoding cố định.

## 8. Phân biệt counters của CircuitBreaker với HTTP client metrics

Circuit breaker đo kết quả của supplier được đưa qua breaker. HTTP client đo hoạt động trao đổi mạng thực tế. Hai nguồn dữ liệu bổ sung cho nhau.

| Câu hỏi | Metric phù hợp |
|---|---|
| Supplier qua breaker thành công bao nhiêu lần? | Circuit breaker calls `successful` |
| Supplier phát exception bao nhiêu lần? | Circuit breaker calls `failed` và phân loại exception |
| Breaker đã chặn bao nhiêu request? | Circuit breaker calls `not_permitted` |
| Backend nhận bao nhiêu request HTTP? | HTTP client/server request counters |
| Backend trả bao nhiêu HTTP 5xx? | HTTP client response status hoặc server HTTP metrics |
| Kết nối và response mất bao lâu? | HTTP client latency, connect time và trace span |
| Người dùng nhận fallback bao nhiêu lần? | Metric fallback riêng của ứng dụng |

Một request bị `not_permitted` không tạo HTTP exchange mới qua supplier được bảo vệ. Vì vậy, nếu not-permitted tăng trong khi HTTP request count không tăng, đó có thể là hành vi mong đợi. Nếu failed tăng cùng HTTP 5xx, cần xem lỗi backend. Nếu failed tăng nhưng HTTP client không ghi nhận response, nguyên nhân có thể là DNS, connect timeout hoặc lỗi trước khi có response.

## 9. Retry làm thay đổi cách diễn giải số lần gọi

Khi kết hợp Retry và CircuitBreaker, vị trí lồng ghép quyết định breaker đếm kết quả của một lần thử hay kết quả cuối cùng của nhiều lần thử.

- **Retry nằm bên trong CircuitBreaker:** breaker bao quanh toàn bộ chuỗi retry. Một lần thực thi supplier của breaker có thể tạo nhiều HTTP attempt nhưng breaker thường ghi nhận kết quả cuối cùng của chuỗi retry.
- **CircuitBreaker nằm bên trong Retry:** mỗi lần thử có thể đi qua breaker riêng. Khi đó, breaker có thể ghi nhận nhiều kết quả success/failure hoặc từ chối trong một request nghiệp vụ.

Ví dụ, một request nghiệp vụ thử HTTP ba lần trước khi thành công. HTTP client có thể ghi nhận ba request attempt, trong khi circuit breaker chỉ ghi nhận một success nếu breaker bao ngoài retry. Do đó, không nên kỳ vọng tổng số circuit breaker calls luôn bằng tổng số HTTP request.

Khi đọc dashboard, hãy xác định thứ tự decorator/aspect và đo cả số lần thử mạng. Nếu Retry nằm ngoài breaker, một breaker đang `OPEN` có thể tạo nhiều lần từ chối trong cùng một request tùy retry policy; retry liên tục trong trạng thái `OPEN` thường chỉ làm tăng not-permitted và tải xử lý ở phía gọi.

## 10. Thiết lập endpoint metrics trong Spring Boot

Để quan sát metric qua Actuator, ứng dụng cần dependency Actuator và registry Micrometer phù hợp. Với Prometheus, có thể thêm registry tương ứng và expose endpoint metrics theo chính sách bảo mật của ứng dụng.

Ví dụ cấu hình:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when_authorized
  metrics:
    tags:
      application: order-service

resilience4j:
  circuitbreaker:
    instances:
      inventory:
        registerHealthIndicator: true
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
```

Không expose endpoint quản trị hoặc metrics ra mạng công khai nếu chưa có kiểm soát truy cập phù hợp. Trong môi trường production, giới hạn endpoint được expose, đặt xác thực hoặc chỉ cho phép hệ thống giám sát nội bộ truy cập.

Có thể dùng endpoint Actuator metrics để khám phá meter đang có, ví dụ:

```text
GET /actuator/metrics/resilience4j.circuitbreaker.calls
GET /actuator/metrics/resilience4j.circuitbreaker.calls?tag=name:inventory&tag=kind:successful
```

Tên meter và tag có thể thay đổi theo phiên bản. Hãy đọc `availableTags` trong response của endpoint metrics để biết tag nào đang được hỗ trợ và giá trị hợp lệ. Với Prometheus, tên metric được chuyển đổi theo quy tắc của registry; kiểm tra `/actuator/prometheus` trước khi viết query hoặc dashboard.

## 11. Xây dựng dashboard cho từng breaker

Một dashboard hữu ích nên hiển thị các số liệu theo từng breaker ID, ví dụ `inventory`, `pricing` hoặc `recommendation`:

1. **Call rate theo kind:** tốc độ tăng của successful, failed, not_permitted và ignored.
2. **Failure rate:** tỷ lệ failed trên successful + failed trong sliding window hoặc metric tương ứng.
3. **State:** trạng thái hiện tại và thời gian kể từ lần chuyển trạng thái gần nhất.
4. **Latency:** thời gian thực thi, p50/p95/p99 nếu có histogram từ client hoặc tracing.
5. **Fallback:** số lần fallback được gọi và loại fallback được trả về.
6. **Backend health:** HTTP status, connect/read timeout, số request thực tế và mức sử dụng connection pool.

Ví dụ bố cục dashboard:

| Panel | Biểu đồ đề xuất | Mục đích |
|---|---|---|
| Calls by kind | Rate theo `successful`, `failed`, `not_permitted`, `ignored` | Thấy rõ lời gọi thành công, lỗi và bị chặn |
| Breaker state | State hiện tại hoặc timeline state transition | Biết breaker đang `CLOSED`, `OPEN` hay `HALF_OPEN` |
| Failure/slow rate | Gauge hoặc timeline theo thời gian | Đối chiếu ngưỡng mở mạch |
| Dependency latency | p50/p95/p99 và timeout count | Phát hiện phụ thuộc chậm trước khi lỗi tăng |
| Fallback count | Counter theo fallback type | Đánh giá tác động lên chức năng người dùng |
| Backend request status | HTTP 2xx/4xx/5xx và request rate | Xác nhận request thực sự đến backend |

Không nên chỉ hiển thị một tổng `failed + not_permitted`. Hai số này dẫn đến hành động khác nhau: failed yêu cầu điều tra phụ thuộc và exception; not_permitted yêu cầu kiểm tra state, thời gian mở và chiến lược fallback.

## 12. Đọc ví dụ dashboard theo thời gian

Giả sử dashboard của breaker `inventory` có ba giai đoạn:

| Giai đoạn | Successful | Failed | Not permitted | State |
|---|---:|---:|---:|---|
| Bình thường | 950 | 10 | 0 | `CLOSED` |
| Phụ thuộc suy giảm | 120 | 80 | 0 | `OPEN` sau khi vượt ngưỡng |
| Đang bảo vệ | 0 | 0 | 600 | `OPEN` |

Ở giai đoạn đầu, đa số lời gọi thành công. Khi phụ thuộc suy giảm, failed tăng và breaker mở sau khi có đủ mẫu. Trong giai đoạn bảo vệ, supplier không chạy nên failed không tiếp tục tăng; thay vào đó not-permitted tăng khi traffic mới bị chặn.

Nếu chỉ xem failed, người vận hành có thể nghĩ sự cố đã kết thúc vì số lỗi mới gần bằng 0. Nhưng not-permitted và state `OPEN` cho thấy chức năng phụ thuộc vẫn đang bị ngắt. Cần kiểm tra backend phục hồi, chờ breaker chuyển `HALF_OPEN` và theo dõi kết quả thăm dò trước khi kết luận hệ thống đã trở lại bình thường.

## 13. Đọc số liệu theo từng replica

Circuit breaker Resilience4j thường giữ trạng thái và thống kê trong từng tiến trình. Nếu ứng dụng chạy nhiều pod, mỗi pod có breaker instance và sliding window riêng. Vì vậy, tổng hợp số liệu toàn service có thể che khuất khác biệt giữa các replica.

Ví dụ:

| Replica | Successful | Failed | Not permitted | State |
|---|---:|---:|---:|---|
| Pod A | 0 | 0 | 300 | `OPEN` |
| Pod B | 180 | 20 | 0 | `CLOSED` |
| Pod C | 40 | 10 | 0 | `HALF_OPEN` |

Pod A đã mở mạch, Pod B vẫn nhận lời gọi và Pod C đang thăm dò. Dashboard chỉ có tổng toàn service có thể cho thấy còn nhiều success, nhưng không thể hiện rằng một phần replica đang từ chối toàn bộ lời gọi.

Nên giữ nhãn instance/pod trong hệ thống metrics khi cần điều tra chi tiết, đồng thời có dashboard tổng hợp ở cấp service. Tránh đưa định danh request hoặc người dùng vào metric label. Với môi trường autoscaling, pod label có thể thay đổi thường xuyên; cần chọn cách tổng hợp phù hợp để không tạo cardinality quá lớn.

Khi một pod restart, counter và sliding window cục bộ có thể bắt đầu lại cùng tiến trình mới. Dùng `rate` hoặc `increase` trên counter thay vì so sánh giá trị thô qua nhiều lần restart. Đối chiếu thời điểm pod khởi động với trạng thái breaker để tránh kết luận sai từ việc counter reset.

## 14. Cảnh báo dựa trên nhiều tín hiệu

Không nên cảnh báo chỉ vì `not_permitted` lớn hơn 0. Một số lần từ chối trong lúc breaker `OPEN` có thể là hành vi bảo vệ đúng. Cảnh báo cần gắn với tác động người dùng, thời gian kéo dài và trạng thái phụ thuộc.

Một số điều kiện cảnh báo có thể cân nhắc:

- Failed rate vượt ngưỡng trong một khoảng thời gian đủ dài và backend có HTTP 5xx hoặc timeout tăng.
- Breaker ở `OPEN` lâu hơn thời gian vận hành chấp nhận được.
- Not-permitted tăng mạnh đồng thời fallback rate cao và chức năng người dùng bị suy giảm.
- Slow call rate cao dù failure rate còn thấp, vì phụ thuộc chậm có thể làm cạn thread hoặc connection.
- Một số replica ở `OPEN` trong khi replica khác `CLOSED`, cho thấy vấn đề có thể cục bộ theo node hoặc network path.
- Fallback tăng nhưng không có event chuyển trạng thái tương ứng, có thể do lỗi ở tầng khác hoặc fallback được gọi ngoài circuit breaker.

Khi tạo alert, cần xác định cửa sổ đánh giá, ngưỡng, mức độ ảnh hưởng và cách khử nhiễu. Dùng metric state transition hoặc log event để giải thích vì sao alert được kích hoạt; không tạo cảnh báo riêng cho mọi lần supplier lỗi đơn lẻ nếu hệ thống đã có cơ chế tổng hợp theo SLO.

## 15. Các lỗi thường gặp khi diễn giải counters

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| Not permitted là backend trả lỗi | Breaker chặn supplier; request đó có thể chưa đi qua mạng |
| Failed bằng số HTTP 5xx | Failed có thể gồm timeout, DNS, connection error và exception khác theo record policy |
| Success là nghiệp vụ thành công | Success chỉ phản ánh supplier hoàn tất bình thường theo cách breaker phân loại |
| Ignored là success | Ignored không tham gia success hoặc failure statistics |
| Not permitted phải cộng vào failure rate | Not permitted không phải kết quả supplier và không nằm trong mẫu số failure rate |
| Counter calls bằng HTTP attempts | Retry, fallback và thứ tự decorator có thể làm hai số khác nhau |
| Failed giảm về 0 nghĩa là backend đã phục hồi | Breaker có thể đang `OPEN` và mọi lời gọi mới đều bị từ chối |
| Metric tổng hợp toàn service đủ để điều tra | Trạng thái và sliding window thường cục bộ theo từng replica |

## 16. Quy trình đọc số liệu trong một sự cố

Khi dashboard báo bất thường ở một circuit breaker, có thể làm theo trình tự sau:

1. Chọn đúng breaker ID và xem state hiện tại của từng replica.
2. Đọc tốc độ tăng `successful`, `failed`, `not_permitted` và `ignored` theo cùng khoảng thời gian.
3. Tính failure rate từ success và failure theo định nghĩa của breaker; không đưa not-permitted hoặc ignored vào mẫu số.
4. Đối chiếu failed với exception class, HTTP status, connect/read timeout và latency của dependency.
5. Nếu not-permitted tăng, kiểm tra thời điểm breaker chuyển `OPEN`, thời gian chờ và số permission `HALF_OPEN`.
6. Đối chiếu fallback count để xác định người dùng nhận kết quả suy giảm bao nhiêu lần.
7. So sánh circuit breaker calls với HTTP client request metrics để biết supplier có thực sự tạo network attempt hay không.
8. Kiểm tra retry/decorator order để giải thích khác biệt giữa số lần gọi logic và số HTTP attempt.
9. Xem từng pod và thời điểm restart trước khi kết luận tình trạng toàn service.
10. Xác nhận phục hồi bằng các lời gọi thăm dò thành công, state trở lại `CLOSED` và latency ổn định.

Đọc riêng số lời gọi thành công, lỗi và bị từ chối giúp tách bạch kết quả của phụ thuộc với quyết định bảo vệ của circuit breaker. Success và failed mô tả kết quả supplier; not-permitted cho biết breaker đã chặn lời gọi; ignored phản ánh exception không tham gia failure rate. Kết hợp các counters với state, latency, fallback, HTTP client metrics và dữ liệu từng replica giúp đội vận hành xác định đúng nơi cần xử lý và đánh giá liệu circuit breaker đang bảo vệ hệ thống hiệu quả hay không.
