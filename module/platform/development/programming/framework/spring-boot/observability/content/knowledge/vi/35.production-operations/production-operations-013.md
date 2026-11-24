# Postmortem dùng telemetry

Postmortem là quá trình tái dựng một sự cố đã xảy ra, giải thích vì sao hệ thống phản ứng như vậy và xác định thay đổi giúp giảm khả năng tái diễn. Một postmortem tốt dựa trên bằng chứng, mô tả tác động đến người dùng và tập trung cải thiện hệ thống thay vì quy lỗi cho cá nhân.

Trong module `SPRING_BOOT_OBSERVABILITY`, bài học này kết nối các tín hiệu được tạo bởi Micrometer Observation, metrics, logs và distributed tracing thành một câu chuyện có thể kiểm chứng. Bạn sẽ dùng telemetry để xác định thời điểm sự cố bắt đầu, tìm đường đi gây lỗi, đo phạm vi ảnh hưởng và biến phát hiện thành hành động vận hành cụ thể.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt vai trò của metrics, logs và traces khi điều tra incident.
- Dựng timeline từ cảnh báo, thay đổi triển khai và dữ liệu telemetry.
- Liên kết request, trace, span và log để lần theo một lỗi xuyên qua nhiều thành phần.
- Đánh giá tác động bằng số liệu tổng hợp, đồng thời nhận biết giới hạn của sampling và dữ liệu thiếu.
- Viết postmortem có nguyên nhân, yếu tố góp phần và action item đo được.

## Telemetry cung cấp bằng chứng gì?

Ba tín hiệu trả lời ba nhóm câu hỏi khác nhau. Khi điều tra, hãy dùng chúng bổ trợ cho nhau:

| Tín hiệu | Câu hỏi chính | Bằng chứng thường dùng |
|---|---|---|
| Metrics | Điều gì thay đổi, bắt đầu khi nào và ảnh hưởng rộng đến đâu? | Tỷ lệ lỗi, lưu lượng, p95/p99 latency, mức sử dụng CPU, heap, connection pool, queue depth |
| Logs | Ứng dụng đã ghi nhận sự kiện hoặc quyết định nào? | Exception, timeout, validation failure, trạng thái nghiệp vụ, thông tin cấu hình và phiên bản |
| Traces | Một request đi qua những thành phần nào và chậm hoặc lỗi ở đâu? | Root span, child span, thời lượng từng bước, lỗi tại client/server span, quan hệ giữa các service |

Ví dụ, metric cho thấy tỷ lệ HTTP 5xx tăng sau một lần triển khai. Trace cho thấy thời gian của span gọi cơ sở dữ liệu tăng mạnh. Log tại cùng trace ghi nhận timeout trong lúc gọi database. Khi ba bằng chứng khớp nhau, giả thuyết connection pool bị cạn có cơ sở hơn nhiều so với việc chỉ nhìn một dòng exception.

Metrics phù hợp để đánh giá xu hướng và quy mô vì chúng tổng hợp nhiều request. Logs cung cấp chi tiết của sự kiện cụ thể. Traces mô tả đường đi và quan hệ thời gian giữa các thao tác. Một trace được lấy mẫu không đại diện cho toàn bộ traffic; vì vậy không dùng số trace tìm thấy để thay thế số liệu tổng hợp từ metrics.

## Chuẩn bị telemetry trước khi có sự cố

Postmortem chỉ tốt khi hệ thống đã phát ra dữ liệu đủ để điều tra. Với ứng dụng Spring Boot, cần thống nhất cách đặt tên và gắn ngữ cảnh trên toàn bộ luồng xử lý.

### Dùng các thuộc tính định danh nhất quán

Mỗi tín hiệu nên mang đủ thông tin để xác định môi trường và phiên bản đang chạy, chẳng hạn:

- `service.name`: tên service ổn định, ví dụ `order-service`.
- `deployment.environment`: môi trường như `production` hoặc `staging`.
- `service.version`: phiên bản hoặc commit được triển khai.
- `traceId` và `spanId`: liên kết log với trace tương ứng.
- Route template, HTTP method, status code và tên operation: giúp phân nhóm request.

Không gắn user ID, email, order ID, request URL chứa mã định danh hoặc giá trị tùy ý vào label metric. Những giá trị có quá nhiều biến thể làm tăng cardinality, tiêu thụ bộ nhớ và khiến truy vấn khó vận hành. Với metric HTTP, ưu tiên route template như `/orders/{id}` thay vì đường dẫn thực tế như `/orders/847291`.

### Giữ context propagation xuyên suốt request

Trace chỉ hữu ích khi context được truyền qua các ranh giới: HTTP client, message broker, executor bất đồng bộ và các service phía sau. Nếu một đoạn xử lý tạo span mới mà không giữ quan hệ với trace cha, postmortem sẽ thấy nhiều trace rời rạc và khó xác định request ban đầu.

Dùng instrumentation và Observation phù hợp với stack Spring Boot; kiểm tra cả luồng đồng bộ lẫn bất đồng bộ. Với message queue, cần truyền trace context qua message headers và tạo quan hệ span phù hợp khi consumer xử lý message. Không tự tạo trace ID mới cho từng log hoặc từng tầng xử lý.

### Ghi log có cấu trúc và có thể liên kết

Log nên ghi thời điểm, mức độ, tên logger, thông điệp, service, phiên bản và trace context khi có. Với sự kiện quan trọng, ghi thêm operation hoặc mã lỗi ổn định. Tránh ghi token, mật khẩu, dữ liệu cá nhân hoặc payload nhạy cảm.

Ví dụ một log JSON đã được rút gọn:

```json
{
  "timestamp": "2026-11-22T09:05:14.218Z",
  "level": "ERROR",
  "service.name": "order-service",
  "service.version": "2026.11.22.1",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "operation": "inventory.reserve",
  "error.code": "DEPENDENCY_TIMEOUT",
  "message": "Inventory reservation timed out"
}
```

Tên field thực tế phụ thuộc encoder và cấu hình logging. Điều quan trọng là trace ID trong log phải khớp với trace được exporter gửi đi. Nếu ứng dụng chỉ ghi log văn bản, vẫn có thể đưa trace ID và span ID vào MDC để hệ thống log tìm kiếm được.

### Hiểu sampling và thời gian lưu dữ liệu

Sampling giảm chi phí thu thập trace, nhưng cũng có thể làm mất trace của một request lỗi. Nếu cấu hình chỉ lấy mẫu theo tỷ lệ cố định, một số lỗi hiếm hoặc request có độ trễ cao có thể không được giữ lại. Hãy cân nhắc tail sampling hoặc chính sách ưu tiên giữ trace lỗi và trace chậm ở tầng collector nếu kiến trúc hỗ trợ.

Metrics, logs và traces có thể có thời gian lưu khác nhau. Trước khi cần postmortem, hãy biết dữ liệu nào còn tồn tại, độ trễ ingest là bao lâu và đồng hồ của các máy có được đồng bộ hay không. Khi điều tra, ghi rõ nguồn dữ liệu và khoảng thời gian truy vấn để người khác có thể tái lập kết quả.

## Quy trình điều tra bằng telemetry

### 1. Xác định incident và bảo toàn bằng chứng

Ghi lại thời điểm phát hiện, người hoặc hệ thống phát hiện, service bị ảnh hưởng, triệu chứng quan sát được và trạng thái hiện tại. Chọn một khoảng thời gian bao gồm cả giai đoạn bình thường trước sự cố, thời điểm bắt đầu, thời gian xử lý và giai đoạn phục hồi.

Lưu các dashboard, truy vấn, trace ID đại diện, log liên quan và sự kiện triển khai. Ghi lại múi giờ; nên chuẩn hóa timeline về UTC để so sánh dữ liệu từ nhiều service. Không sửa hoặc xóa dữ liệu gốc trong lúc điều tra.

### 2. Dựng timeline từ nhiều nguồn

Bắt đầu từ metric hoặc cảnh báo để xác định thời điểm thay đổi. Sau đó đối chiếu với:

- Lần triển khai phiên bản mới, rollback hoặc thay đổi feature flag.
- Thay đổi cấu hình, secret, quota hoặc giới hạn tài nguyên.
- Sự kiện từ database, cache, message broker và dịch vụ phụ thuộc.
- Thay đổi lưu lượng, lịch chạy batch hoặc hoạt động vận hành định kỳ.

Không kết luận rằng một lần deploy là nguyên nhân chỉ vì hai sự kiện xảy ra gần nhau. Hãy xem dữ liệu trước và sau deploy, kiểm tra service không được deploy cùng thời điểm, và tìm bằng chứng nối thay đổi đó với triệu chứng.

### 3. Đo phạm vi ảnh hưởng

Dùng metrics để trả lời các câu hỏi định lượng:

- Bao nhiêu request bị lỗi hoặc chậm?
- Ảnh hưởng đến route, tenant, vùng triển khai hay dependency nào?
- Tỷ lệ lỗi và latency tăng trong bao lâu?
- Có request thành công nào bị ảnh hưởng gián tiếp, chẳng hạn xử lý trễ hoặc message tồn đọng?
- Khi nào hệ thống trở lại mức bình thường?

Phân biệt số lượng tuyệt đối và tỷ lệ. Mười lỗi trong một phút có ý nghĩa khác nhau khi service nhận một trăm request so với một triệu request. Nếu có thể, so sánh với baseline cùng khung giờ hoặc cùng kiểu traffic. Nêu rõ cách tính và khoảng thời gian đo trong báo cáo.

### 4. Lần theo trace để tìm đoạn xử lý bất thường

Chọn một số trace đại diện cho request lỗi và request thành công trong cùng khoảng thời gian. So sánh root span và các child span để xác định:

- Span nào chiếm phần lớn thời gian?
- Lỗi phát sinh ở service nhận request hay ở dependency?
- Có retry, timeout, queue wait hoặc thao tác tuần tự bất thường không?
- Context có bị đứt khi qua HTTP, message broker hoặc executor không?

Một span kéo dài chưa đủ chứng minh thành phần đó là nguyên nhân gốc. Ví dụ, span HTTP client có thể dài vì service đích chậm, vì kết nối không được cấp phát, hoặc vì request đang chờ retry. Mở rộng điều tra sang span phía server, metrics connection pool và log cùng trace ID.

### 5. Dùng log để xác nhận cơ chế lỗi

Sau khi đã khoanh vùng bằng metrics và traces, tìm log theo trace ID, span ID, operation, error code và khoảng thời gian. Tìm sự kiện đầu tiên trong chuỗi gây lỗi thay vì chỉ đọc exception cuối cùng ở tầng API.

Kiểm tra log của cả caller và callee. Một service có thể ghi timeout trong khi service đích ghi nhận request bị từ chối do hết tài nguyên. Đối chiếu timestamp và trace context để tránh ghép nhầm các request xảy ra gần nhau.

### 6. Xác định nguyên nhân và yếu tố góp phần

Nguyên nhân cần giải thích được chuỗi sự kiện và có bằng chứng. Tách biệt:

- **Nguyên nhân trực tiếp:** điều kiện làm phát sinh lỗi, ví dụ truy vấn mới khiến thời gian giữ connection tăng.
- **Yếu tố góp phần:** điều kiện khiến lỗi nghiêm trọng hơn, ví dụ pool nhỏ, retry đồng thời hoặc thiếu giới hạn thời gian.
- **Lỗ hổng phát hiện:** lý do cảnh báo không phát hiện sớm hoặc dashboard không chỉ ra đúng thành phần.
- **Lỗ hổng phục hồi:** lý do rollback, giảm tải hoặc chuyển traffic mất nhiều thời gian.

Có thể dùng chuỗi câu hỏi “vì sao” để mở rộng phân tích, nhưng dừng ở các điều kiện hệ thống có thể thay đổi. Tránh kết luận kiểu “do người vận hành bất cẩn”. Nếu dữ liệu chưa đủ để khẳng định, ghi giả thuyết và mức độ tin cậy, đồng thời tạo action item để thu thập bằng chứng còn thiếu.

### 7. Chốt hành động và kiểm tra hiệu quả

Mỗi action item nên mô tả thay đổi có thể kiểm chứng, người phụ trách, thời hạn và điều kiện hoàn tất. Ưu tiên biện pháp giảm tác động hoặc ngăn tái diễn, sau đó cải thiện phát hiện và khả năng điều tra.

Ví dụ:

| Hành động | Tiêu chí hoàn tất |
|---|---|
| Thêm cảnh báo khi tỷ lệ HTTP 5xx vượt ngưỡng trong 5 phút | Alert được kiểm thử bằng dữ liệu mô phỏng và có runbook |
| Theo dõi thời gian chờ connection pool | Dashboard hiển thị active, idle, pending và timeout |
| Giới hạn retry và đặt timeout cho lời gọi dependency | Có kiểm thử tải chứng minh retry không khuếch đại sự cố |
| Thêm trace context vào log của consumer | Có thể tìm log consumer từ trace của message |
| Bổ sung kiểm tra hiệu năng cho truy vấn thay đổi | Pipeline có ngưỡng regression và kết quả được lưu |

Tránh action item mơ hồ như “cải thiện monitoring” hoặc “cẩn thận hơn khi deploy”. Chia việc lớn thành bước nhỏ có thể xác minh, đồng thời theo dõi action item sau khi postmortem kết thúc.

## Thực hành với Spring Boot và Micrometer

Spring Boot Actuator cung cấp endpoint để kiểm tra trạng thái và metric của ứng dụng. Trong môi trường production, chỉ expose endpoint cần thiết và bảo vệ chúng bằng cơ chế xác thực, phân quyền và network policy phù hợp.

Ví dụ kiểm tra metric HTTP bằng Actuator:

```bash
curl -s http://localhost:8080/actuator/metrics/http.server.requests
```

Endpoint này cho biết metric có được ghi nhận và có những tag nào. Khi dùng registry Prometheus, tên metric thường được chuyển thành dạng như `http_server_requests_seconds_count` và `http_server_requests_seconds_bucket`. Tên chính xác và tập label phụ thuộc phiên bản, registry và cấu hình instrumentation; hãy kiểm tra dữ liệu thực tế tại endpoint `/actuator/prometheus` trước khi viết truy vấn.

Ví dụ các truy vấn PromQL thường dùng trong điều tra:

**Tốc độ request lỗi 5xx theo route và method:**

```promql
sum by (uri, method) (
  rate(http_server_requests_seconds_count{status=~"5.."}[5m])
)
```

**Tỷ lệ request lỗi 5xx trên tổng request:**

```promql
sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
/
clamp_min(sum(rate(http_server_requests_seconds_count[5m])), 1e-9)
```

**p95 latency theo route từ histogram:**

```promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
```

Các truy vấn trên giả định metric có những tên và label tương ứng. Nếu hệ thống xuất metric với tên hoặc label khác, điều chỉnh theo dữ liệu thực tế. Không thêm label có cardinality cao chỉ để làm truy vấn chi tiết hơn. Khi cần phân tích một request cụ thể, dùng trace và log.

Trong hệ thống có Micrometer Tracing, trace có thể được gửi qua OTLP hoặc một exporter được cấu hình trong ứng dụng. Khi xem trace, kiểm tra service name, operation, parent-child relationship, thời lượng, status và exception event. Đối chiếu trace với log bằng trace ID. Nếu trace thiếu span ở một đoạn, kiểm tra instrumentation, context propagation, sampling và trạng thái exporter trước khi kết luận rằng đoạn xử lý không chạy.

Micrometer Observation cung cấp một điểm instrument cho operation; các handler tương ứng có thể xuất metrics và trace. Metrics giúp quan sát hoạt động ở mức tổng hợp, còn trace theo dõi một lần thực thi cụ thể. Khi tạo Observation tùy chỉnh, chọn tên operation ổn định và chỉ thêm low-cardinality key-value có tập giá trị hữu hạn. Giá trị định danh từng request phù hợp với trace hoặc log, không phù hợp làm tag metric.

## Ví dụ: API đặt hàng tăng latency sau khi triển khai

Giả sử service `order-service` triển khai phiên bản `2026.11.22.1`. Vài phút sau, p95 của API `POST /orders` tăng từ khoảng 180 ms lên 1,8 giây và tỷ lệ 5xx tăng từ 0,2% lên 6%.

| Thời điểm UTC | Quan sát | Nguồn bằng chứng |
|---|---|---|
| 09:00 | Triển khai phiên bản mới | Deployment event |
| 09:04 | p95 tăng và 5xx bắt đầu tăng | HTTP metrics |
| 09:05 | Trace cho thấy span gọi database chiếm phần lớn thời gian | Distributed traces |
| 09:06 | Connection pool có nhiều request chờ; log xuất hiện timeout | Pool metrics và logs |
| 09:18 | Rollback phiên bản mới | Deployment event |
| 09:22 | p95 và tỷ lệ lỗi trở về gần baseline | HTTP metrics |

Nhóm điều tra chọn trace của request thành công và thất bại trong cùng khoảng thời gian. Các trace lỗi đều có span truy vấn database dài hơn rõ rệt. Log gắn cùng trace ID ghi nhận timeout khi chờ kết quả truy vấn; metric database cho thấy thời gian truy vấn tăng sau deploy. Sau rollback, các chỉ số dần trở về baseline.

Bằng chứng này hỗ trợ kết luận rằng thay đổi trong đường truy vấn của phiên bản mới làm tăng thời gian xử lý database, kéo dài thời gian giữ connection và khiến request chờ đến timeout. Giới hạn của connection pool khiến nhiều request đồng thời phải chờ, làm tác động lan rộng hơn nhưng không phải điểm khởi đầu của sự cố.

Postmortem nên ghi rõ cách kiểm chứng giả thuyết, chẳng hạn so sánh truy vấn hoặc query plan giữa hai phiên bản, tái hiện trên dữ liệu thử nghiệm và kiểm tra lại sau khi sửa. Action item có thể gồm tối ưu truy vấn, thêm kiểm thử hiệu năng cho đường truy vấn, theo dõi pool wait và đặt cảnh báo theo latency cùng tỷ lệ lỗi. Nếu chưa có bằng chứng về query plan, hãy ghi đây là giả thuyết đang xác minh thay vì trình bày như sự thật đã được chứng minh.

## Mẫu postmortem có thể tái sử dụng

```markdown
# Postmortem: <tên incident>

## Thông tin chung
- Thời gian bắt đầu/kết thúc (UTC):
- Service và phiên bản:
- Người điều phối:
- Mức độ ảnh hưởng:

## Tóm tắt
- Điều gì đã xảy ra?
- Người dùng bị ảnh hưởng như thế nào?
- Hệ thống đã phục hồi bằng cách nào?

## Tác động
- Số lượng và tỷ lệ request lỗi:
- Latency trước, trong và sau incident:
- Route, dependency hoặc vùng bị ảnh hưởng:
- Dữ liệu và cách tính:

## Timeline
| Thời điểm UTC | Sự kiện | Bằng chứng |
|---|---|---|

## Phân tích kỹ thuật
- Metrics và dashboard:
- Trace ID/span đại diện:
- Log và error code liên quan:
- Thay đổi triển khai/cấu hình:
- Nguyên nhân trực tiếp:
- Yếu tố góp phần:
- Điều chưa thể xác nhận:

## Phản ứng và phục hồi
- Biện pháp giảm tác động:
- Thời điểm phục hồi:
- Điều gì hiệu quả/chưa hiệu quả?

## Action items
| Hành động | Người phụ trách | Hạn | Tiêu chí hoàn tất |
|---|---|---|---|

## Bài học
- Điều gì giúp phát hiện hoặc xử lý nhanh?
- Bằng chứng nào còn thiếu?
- Thay đổi nào cần kiểm tra lại sau khi hoàn thành?
```

## Những sai lầm thường gặp

- **Chỉ nhìn log lỗi cuối cùng:** exception ở API có thể là hậu quả của timeout ở dependency. Lần theo trace và log ở các tầng liên quan.
- **Dùng trace để suy ra tỷ lệ lỗi:** sampling có thể bỏ sót request. Dùng metrics để đo tỷ lệ và trace để hiểu từng luồng.
- **Coi tương quan là nguyên nhân:** deploy gần thời điểm incident chỉ là đầu mối. Cần chứng minh thay đổi tạo ra triệu chứng.
- **Dùng label có cardinality cao:** đưa user ID hoặc ID giao dịch vào metric có thể làm hệ thống metrics quá tải. Giữ giá trị đó trong log hoặc trace nếu chính sách dữ liệu cho phép.
- **Bỏ qua đồng hồ và độ trễ ingest:** timestamp không đồng bộ có thể làm timeline sai thứ tự. Kiểm tra UTC, clock synchronization và thời gian dữ liệu đến backend.
- **Ghi action item không đo được:** mỗi việc cần người phụ trách và tiêu chí xác nhận kết quả.

Một postmortem đáng tin cậy cho phép một kỹ sư khác lần lại bằng chứng, hiểu vì sao sự cố xảy ra và kiểm tra được các biện pháp khắc phục. Khi metrics cho biết phạm vi, traces chỉ ra đường đi và logs giải thích sự kiện, telemetry trở thành nền tảng để cải thiện độ tin cậy của ứng dụng Spring Boot qua từng incident.

