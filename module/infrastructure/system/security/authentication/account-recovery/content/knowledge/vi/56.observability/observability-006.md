# Provider dependency monitoring — Theo dõi phụ thuộc nhà cung cấp trong khôi phục tài khoản

Luồng khôi phục tài khoản có thể phụ thuộc vào dịch vụ email, SMS, xác minh danh tính, đánh giá rủi ro, quản lý khóa hoặc thu hồi session. API recovery vẫn trả phản hồi nhanh trong khi SMS không đến, hồ sơ xác minh không hoàn tất hoặc yêu cầu thu hồi phiên bị tồn đọng.

**Provider dependency monitoring là quan sát từng phụ thuộc từ phía hệ thống sử dụng nó, liên kết tình trạng kỹ thuật với ảnh hưởng lên recovery và cung cấp đủ bằng chứng để xử lý sự cố.** Một trang trạng thái màu xanh hoặc một HTTP 200 chưa đủ chứng minh người dùng có thể khôi phục tài khoản an toàn.

Bài học mô tả thiết kế minh họa. Tên metric, nhóm lỗi, ngưỡng và truy vấn bên dưới phải được điều chỉnh theo hợp đồng provider, đặc tính lưu lượng và ngân sách thời gian của từng thao tác.

## 1. Bắt đầu từ bản đồ phụ thuộc và hậu quả khi lỗi

Không chỉ lập danh sách tên nhà cung cấp. Cần biết phụ thuộc nào nằm trên đường xử lý nào, ở bước nào và có ảnh hưởng gì.

| Phụ thuộc | Thao tác recovery liên quan | Khi phụ thuộc gặp vấn đề |
| --- | --- | --- |
| Email | Gửi liên kết và cảnh báo an ninh | Người dùng không nhận được thông báo hoặc nhận quá trễ |
| SMS | Gửi mã hoặc nhận kết quả giao tin | Mã đến khi đã hết hạn, yêu cầu gửi lại tăng |
| Xác minh danh tính | Nộp hồ sơ, lấy kết quả xác minh | Quy trình bị kẹt hoặc kết quả chưa rõ |
| Risk engine | Đánh giá yêu cầu bất thường | Thiếu dữ kiện cho quyết định rủi ro |
| Kho khóa/KMS | Bảo vệ hoặc đọc dữ liệu recovery cần thiết | Không thể thực hiện thao tác mật mã được yêu cầu |
| Hệ thống session | Thu hồi phiên sau thay đổi credential | Phiên cũ có thể chưa bị vô hiệu hóa theo yêu cầu |
| Directory/identity service | Đọc hoặc ghi trạng thái tài khoản | Thay đổi recovery chưa được áp dụng nhất quán |

Với mỗi thao tác, ghi rõ:

- Chủ sở hữu tích hợp và người xử lý sự cố.
- Endpoint hoặc route được cấu hình, vùng triển khai và tài khoản dịch vụ.
- Quyền, quota, chứng chỉ và cấu hình sender cần thiết.
- Timeout, retry, cơ chế idempotency và loại kết quả chưa rõ.
- Callback, polling hoặc nguồn đối soát kết quả bất đồng bộ.
- Phương án xử lý khi không dùng được phụ thuộc.
- Các ràng buộc bảo mật khi chuyển tuyến hoặc chuyển nhà cung cấp.

Hai tên thương mại khác nhau không bảo đảm hai tuyến độc lập. Chúng có thể cùng dùng một hạ tầng mạng, aggregator SMS hoặc vùng cloud. Bản đồ phụ thuộc cần thể hiện những điểm lỗi chung quan trọng.

## 2. Theo dõi ba tầng kết quả

### 2.1. Tầng kết nối

Hệ thống có thực hiện được lời gọi từ môi trường đang chạy hay không?

Ví dụ:

```text
DNS resolution
→ kết nối TCP
→ TLS handshake
→ gửi request
→ nhận response
```

DNS lỗi, egress bị chặn, hết connection pool và chứng chỉ không hợp lệ có thể làm dependency không dùng được dù provider vẫn hoạt động bình thường.

### 2.2. Tầng API hoặc giao thức

Provider đã trả kết quả gì cho thao tác?

Cần phân biệt chấp nhận yêu cầu, giới hạn tần suất, sai credential, dữ liệu không hợp lệ, quota cạn và lỗi tạm thời. HTTP status chỉ là một đầu vào; một số API thể hiện lỗi nghiệp vụ bên trong response thành công ở tầng HTTP.

### 2.3. Tầng kết quả nghiệp vụ

Công việc cần thiết cho recovery đã đạt trạng thái nào?

```text
Gửi email: provider chấp nhận → máy chủ nhận thư chấp nhận → người dùng sử dụng token
Xác minh: hồ sơ được nhận → quá trình xử lý kết thúc → kết quả được áp dụng
Thu hồi: yêu cầu được nhận → phiên thực sự bị vô hiệu hóa theo mô hình hệ thống
```

Trong Amazon SES, sự kiện Send biểu thị yêu cầu gửi thành công và dịch vụ sẽ thử chuyển thư; Delivery biểu thị thư đã được giao tới mail server của người nhận. Đây là các mốc khác nhau, và Delivery cũng chưa chứng minh người dùng đã đọc thư hay kiểm soát tài khoản. [Amazon SES: Event publishing terminology](https://docs.aws.amazon.com/ses/latest/dg/monitor-using-event-publishing.html)

Dashboard cần giữ các tầng này riêng để tránh biến “đã nhận công việc” thành “đã hoàn tất recovery”.

## 3. Định nghĩa thành công theo từng operation

Một kết quả từ chối xác minh có thể là phản hồi đúng của provider. Đó không tự động là lỗi availability.

| Kết quả quan sát | Diễn giải cần kiểm tra |
| --- | --- |
| Risk engine trả quyết định DENY hợp lệ | Lời gọi kỹ thuật thành công; yêu cầu bị từ chối theo nghiệp vụ |
| Provider xác minh trả hồ sơ không đạt | Có kết quả nghiệp vụ; chưa có bằng chứng provider bị lỗi |
| API trả sai credential | Tích hợp không dùng được; cần xử lý credential/quyền |
| Provider trả giới hạn tần suất | Có thể vượt quota hoặc nhịp gửi; cần phân tích tải và hợp đồng |
| HTTP 200 nhưng thiếu trường bắt buộc | Lỗi giao thức/schema hoặc thay đổi hợp đồng |
| Client timeout sau khi gửi request | Có thể chưa biết provider đã tạo tác dụng hay chưa |
| Không có callback sau thời gian dự kiến | Công việc chưa rõ kết quả; cũng có thể pipeline callback đang lỗi |
| Session revoke nhận ACCEPTED | Chưa đủ để kết luận mọi phiên đã bị thu hồi |

Một bộ phân loại minh họa:

```text
accepted
business_denied
invalid_request
auth_error
rate_limited
quota_exhausted
unavailable
network_error
timeout
protocol_error
cancelled
```

Mỗi lần thử có một kết quả cuối theo định nghĩa của lớp đo. Nếu response chứa nhiều thông tin, giữ thêm dữ liệu phân tích trong log được giới hạn, thay vì tăng vô hạn số giá trị label.

Nhóm lỗi giúp tìm đúng chủ xử lý. Nó không phải cơ chế miễn trừ ảnh hưởng: lỗi credential do cấu hình nội bộ vẫn có thể làm toàn bộ tuyến recovery không sử dụng được.

## 4. Phân biệt lời gọi logic và lần thử vật lý

Một yêu cầu gửi SMS có thể tạo ba lần gọi HTTP do SDK tự retry. Nếu chỉ đo kết quả cuối cùng, dashboard có thể báo thành công cao trong khi quota và chi phí đã tăng mạnh.

```text
Logical request L1
    attempt A1: timeout
    attempt A2: unavailable
    attempt A3: accepted
```

Cần biết lớp instrumentation quan sát được gì:

- **Logical operation**: từ lúc adapter nhận công việc đến khi trả kết quả cuối.
- **Physical attempt**: từng lần truyền request ra dependency.
- **Workflow outcome**: kết quả cuối cùng của bước recovery liên quan.

Nếu SDK giấu retry bên trong, một span quanh phương thức SDK chỉ phản ánh logical operation của SDK. Không gọi nó là “mọi lần thử mạng” nếu chưa có dữ liệu ở ranh giới tương ứng.

Cũng tránh đếm đôi một lần gửi qua cả instrumentation HTTP tự động và wrapper tự viết, rồi cộng hai nguồn như cùng một tập attempt.

Tỷ lệ khuếch đại retry có thể được theo dõi bằng:

```text
số physical attempts / số logical operations
```

Hai tập đo phải có cùng phạm vi operation và cửa sổ phù hợp. Những công việc kéo dài qua ranh giới thời gian có thể làm tỷ lệ trong cửa sổ ngắn bị méo; xem thêm cohort hoặc xu hướng dài hơn khi cần.

## 5. Bộ metric tối thiểu có ngữ nghĩa rõ ràng

Các tên dưới đây là metric tùy biến của ví dụ, không phải tên chuẩn bắt buộc của một thư viện.

| Metric | Loại | Ý nghĩa |
| --- | --- | --- |
| recovery_provider_attempts_total | Counter | Số lần thử đã kết thúc, phân loại theo result |
| recovery_provider_request_duration_seconds | Histogram | Thời gian một lần thử quan sát được, tính bằng giây |
| recovery_provider_operations_total | Counter | Số thao tác logic đã kết thúc |
| recovery_provider_in_flight | Gauge | Lời gọi đang thực hiện tại nơi đo |
| recovery_provider_blocked_total | Counter | Công việc bị chặn trước khi gọi do circuit/bulkhead |
| recovery_provider_pending | Gauge | Công việc đang chờ kết quả theo catalog bền vững |
| recovery_provider_oldest_pending_age_seconds | Gauge | Độ tuổi công việc chưa kết thúc lâu nhất |
| recovery_provider_callbacks_total | Counter | Callback đã nhận và xử lý theo loại kết quả |
| recovery_provider_reconciliation_total | Counter | Kết quả đối soát các thao tác chưa rõ |

Histogram phải bao gồm cả lần thành công và thất bại theo định nghĩa đo, không chỉ những lời gọi hoàn tất thành công. Nếu timeout bị loại khỏi histogram, độ trễ hiển thị có thể đẹp lên đúng lúc dependency đang xấu đi.

OpenTelemetry định nghĩa `http.client.request.duration` là histogram thời gian HTTP client request với đơn vị giây; các thuộc tính như `error.type` giúp phân loại lỗi khi phù hợp. Khi kết hợp telemetry chuẩn và metric nghiệp vụ, cần đối chiếu phạm vi và đơn vị, không giả định chúng hoàn toàn giống nhau. [OpenTelemetry: HTTP metrics](https://opentelemetry.io/docs/specs/semconv/http/http-metrics/)

Các label có thể gồm tập hữu hạn:

```text
environment
region
provider
provider_route
operation
result
```

Trong bài, `region` là vùng chạy của caller; vùng đích có thể được biểu diễn trong route đã cấu hình. Không trộn hai khái niệm này trên cùng một biểu đồ.

Không dùng email, số điện thoại, account ID, token, provider message ID hoặc URL đầy đủ làm label metric. Với nhiều tenant, dùng cơ chế phân tích được kiểm soát thay vì tự đưa mọi tenant ID vào tất cả chuỗi thời gian.

## 6. Đo đúng thời gian chờ, gọi và hoàn tất

Một lời gọi provider nhanh không có nghĩa mã recovery đến kịp.

```text
t0: notification được xếp hàng
t1: worker nhận công việc
t2: bắt đầu gọi provider
t3: provider phản hồi chấp nhận
t4: hệ thống nhận kết quả giao nhận
```

Các khoảng thời gian trả lời những câu hỏi khác nhau:

| Khoảng | Ý nghĩa |
| --- | --- |
| t1 − t0 | Chờ trong queue |
| t2 − t1 | Chuẩn bị, lấy tài nguyên hoặc kiểm tra điều kiện trước khi gọi |
| t3 − t2 | Thời gian lời gọi quan sát từ client |
| t3 − t0 | Độ trễ từ xếp hàng đến provider chấp nhận |
| t4 − t3 | Độ trễ kết quả quan sát được, có thể gồm xử lý và chuyển callback |

Không gọi `t4 − t3` là “thời gian giao đến người dùng” khi nguồn dữ liệu chỉ cho biết callback đã đến hệ thống.

Thời gian đo latency trong một tiến trình nên dùng đồng hồ đơn điệu phù hợp. Khi so sánh timestamp giữa các hệ thống, cần xét lệch đồng hồ, ý nghĩa timestamp và độ trễ tiếp nhận.

Với token hết hạn sau một khoảng cố định, phần thời gian còn lại khi gửi cần được theo dõi. Nếu queue đã tiêu tốn gần hết thời hạn, việc provider nhanh trở lại không tự làm email cũ còn hữu ích. Worker phải xử lý theo trạng thái và generation của challenge, không gia hạn token để cải thiện số liệu thành công.

## 7. Ví dụ truy vấn cho Prometheus

Các truy vấn sau giả định metric đã được triển khai đúng như mô tả và có label tương ứng. Đây là ví dụ đọc số liệu, không phải cấu hình cảnh báo hoàn chỉnh.

### 7.1. Tỷ lệ lỗi timeout, mạng và không khả dụng theo attempt

```promql
sum by (provider, operation, region) (
  rate(recovery_provider_attempts_total{
    environment="production",
    result=~"timeout|network_error|unavailable"
  }[5m])
)
/
sum by (provider, operation, region) (
  rate(recovery_provider_attempts_total{
    environment="production"
  }[5m])
)
```

Tỷ lệ này có chủ đích không gộp `business_denied`, `auth_error` hoặc `rate_limited` vào tử số. Những nhóm đó cần biểu đồ riêng và có thể vẫn gây gián đoạn recovery.

Mẫu số là attempt đã kết thúc, không phải số người dùng hoặc số yêu cầu recovery. Đây chưa phải SLI thành công của cả luồng.

Cần xử lý việc khởi tạo series, mẫu số bằng 0 và dữ liệu thiếu trong thiết kế dashboard. “Không có lưu lượng”, “không có series” và “0% lỗi” là ba trạng thái khác nhau. Không lấp mọi khoảng mất dữ liệu bằng giá trị thành công.

### 7.2. p95 latency với classic histogram

```promql
histogram_quantile(
  0.95,
  sum by (provider, operation, region, le) (
    rate(recovery_provider_request_duration_seconds_bucket{
      environment="production"
    }[5m])
  )
)
```

Với classic histogram, cần giữ label `le` khi gộp bucket. Quantile được ước lượng từ các bucket, nên chọn bucket phù hợp vùng latency cần quan sát. Không lấy trung bình p95 của các instance để coi đó là p95 chung. [Prometheus: Histograms and summaries](https://prometheus.io/docs/practices/histograms/)

Biểu đồ phải kèm số mẫu. Một quantile từ vài lời gọi không có độ ổn định như từ hàng nghìn lời gọi.

### 7.3. Quan sát circuit breaker và pending

Khi circuit mở, số lời gọi thực tế có thể giảm mạnh. Vì thế tỷ lệ lỗi HTTP giảm không đủ chứng minh đã phục hồi.

Theo dõi song song:

```text
blocked vì circuit_open
số logical operations chưa hoàn tất
tuổi pending lớn nhất
lưu lượng đang được chuyển sang route khác
kết quả probe hoặc half-open theo chính sách
```

Các gauge pending cần có chủ thể sở hữu dữ liệu rõ ràng. Không cộng nhiều bản sao của cùng một phép quét catalog như thể đó là các công việc khác nhau.

## 8. Giám sát kết quả bất đồng bộ theo cohort

Không lấy số delivery callback nhận trong phút hiện tại chia cho số request gửi trong cùng phút rồi gọi đó là tỷ lệ giao thành công.

Ví dụ, một đợt callback đến chậm từ giờ trước có thể làm tỷ lệ vượt 100%; còn một đợt gửi mới chưa đủ thời gian nhận kết quả có thể bị coi nhầm là thất bại.

Một cách tổ chức là theo cohort:

```text
Cohort: các logical notifications được chấp nhận trong một khoảng xác định
Sau thời gian quan sát được quy định:
    delivered theo định nghĩa provider
    failed theo định nghĩa provider
    chưa có kết quả / unknown
```

Cần xác định:

- Đơn vị là notification logic hay từng recipient; một request batch có thể chứa nhiều đích.
- Callback nào được coi là kết quả kết thúc.
- Thời gian chờ quan sát trước khi đánh giá cohort.
- Cách dedup callback và xử lý sự kiện đến sai thứ tự.
- Cách đối soát trường hợp không nhận được callback.
- Loại kết quả provider thực sự có khả năng xác nhận.

Với SMS, semantics delivery receipt có thể khác giữa tuyến và nhà mạng. Không tự suy một giá trị “delivered” thành bằng chứng người dùng đã đọc OTP hoặc có quyền đối với tài khoản.

Với xác minh danh tính, theo dõi tuổi hồ sơ pending, tỷ lệ polling lỗi và độ trễ callback. Một tỷ lệ API 200 cao có thể cùng tồn tại với hàng nghìn hồ sơ không chuyển trạng thái.

## 9. Đo quota, credential và điểm nghẽn cục bộ

Một dependency có thể không sử dụng được vì những điều kiện không thể hiện trong availability công bố.

| Nhóm tín hiệu | Ví dụ cần theo dõi | Hướng khoanh vùng |
| --- | --- | --- |
| Credential/quyền | auth_error tăng sau deploy hoặc rotate | Secret version, phạm vi quyền, tài khoản dịch vụ |
| Quota | Giới hạn số lượng hoặc tốc độ gần cạn | Lưu lượng hợp lệ, retry, lạm dụng và hạn mức |
| Sender/tuyến | Lỗi chỉ ở một sender hoặc route | Cấu hình, đăng ký, chính sách provider |
| Mạng | DNS, TLS, connect timeout | Resolver, chứng chỉ, egress, proxy |
| Tài nguyên caller | Pool chờ, thread bận, in-flight tăng | Connection pool, bulkhead, worker capacity |
| Giao thức | protocol_error sau nâng phiên bản | Schema, phiên bản SDK, response mapping |
| Callback | Nhận thưa, xác minh chữ ký lỗi, backlog tăng | Endpoint, secret webhook, pipeline ingest |

Không đưa giá trị API key, secret hoặc certificate private key vào log để chẩn đoán. Có thể dùng định danh phiên bản cấu hình đã được phép công bố trong nội bộ.

Các chỉ số quota có độ trễ hoặc phạm vi tài khoản riêng. Nếu một tài khoản provider phục vụ nhiều sản phẩm, quota còn lại không chỉ phụ thuộc vào module recovery. Cần biết nguồn tiêu thụ chung trước khi quy lỗi cho một luồng.

## 10. Trace và log đủ để đối soát, không lộ quyền recovery

Trace giúp liên kết bước recovery, công việc bất đồng bộ và lời gọi dependency. Với công việc chạy sau queue, có thể dùng cơ chế propagation hoặc link phù hợp mô hình tracing, thay vì giữ một request HTTP mở trong nhiều giờ.

Một log kết thúc lời gọi minh họa:

```json
{
  "event": "recovery.provider_call.completed",
  "provider": "sms_primary",
  "provider_route": "route_a",
  "operation": "send_otp",
  "result": "timeout",
  "timeout_phase": "response",
  "duration_ms": 1450,
  "attempt_no": 2,
  "outcome_known": false,
  "notification_ref": "notification-217",
  "trace_ref": "trace-example-42",
  "config_version": "provider-config-12"
}
```

Các định danh là ví dụ. `outcome_known=false` thể hiện chưa rõ tác dụng bên ngoài, không phải kết luận OTP chưa được gửi.

Nguyên tắc chọn dữ liệu:

- Không ghi token, OTP, ảnh giấy tờ, authorization header hoặc URL recovery nguyên vẹn.
- Không tự thu request/response body của provider nếu chúng chứa dữ liệu nhạy cảm.
- Chỉ giữ mã lỗi đã chuẩn hóa; thông báo lỗi gốc có thể chứa đích nhận hoặc dữ liệu nhập.
- Định danh dùng đối soát chỉ nằm trong kho log/trace có quyền và thời hạn lưu phù hợp.
- Không gửi baggage chứa danh tính hay trạng thái recovery sang bên ngoài một cách tùy tiện.
- Kiểm soát cả instrumentation tự động, exporter và nơi lưu; redaction ở một lớp không bảo vệ những bản sao đã được ghi ở lớp khác.

Trace thường có sampling, nên số span không mặc định là tổng số lời gọi. Metric tổng hợp cần được thu tại ranh giới đo phù hợp nếu dùng để tính tỷ lệ.

## 11. Kết hợp lưu lượng thực, probe và trạng thái công bố

Ba nguồn quan sát bổ sung cho nhau:

| Nguồn | Điểm mạnh | Giới hạn |
| --- | --- | --- |
| Lời gọi thực từ ứng dụng | Phản ánh credential, route, mạng và tải đang sử dụng | Ít dữ liệu khi lưu lượng thấp hoặc circuit đã mở |
| Probe/synthetic được kiểm soát | Phát hiện lỗi khi không có lưu lượng thật | Có thể không đi qua toàn bộ đường gửi và quota thực |
| Trang trạng thái hoặc thông báo provider | Bổ sung bối cảnh sự cố đã công bố | Không chứng minh tích hợp riêng của mình đang dùng được |

Probe cần có phạm vi rõ: kiểm tra DNS/TLS, API ít tác dụng phụ hoặc một quy trình synthetic có tài khoản và đích nhận chuyên biệt.

Không gửi OTP đến số điện thoại người dùng thật chỉ để kiểm tra hệ thống. Nếu cần probe thực hiện gửi, phải giới hạn chi phí, tần suất và dữ liệu; dùng đích được quản lý riêng. Sandbox không bảo đảm mô phỏng đầy đủ đường gửi production.

Tránh probe tự kích hoạt thay MFA, thu hồi session thật hoặc cấp bằng chứng recovery ngoài quy trình. Cơ chế giám sát không được tạo thêm đường tắt để thay đổi tài khoản.

Theo dõi sức khỏe của chính pipeline telemetry: scrape/exporter lỗi, dữ liệu cũ và collector backlog. Nếu mất metric, dashboard phải thể hiện trạng thái chưa rõ, không tiếp tục hiển thị sức khỏe tốt từ mẫu cũ.

## 12. Cảnh báo phải gắn với ảnh hưởng và khả năng hành động

Một cảnh báo tốt trả lời:

```text
Tuyến nào đang ảnh hưởng operation nào?
Ở môi trường/vùng nào?
Từ khi nào, có bao nhiêu lưu lượng?
Người dùng hoặc bước recovery nào bị ảnh hưởng ở mức tổng hợp?
Chủ xử lý cần kiểm tra và làm gì tiếp?
```

Các nhóm cảnh báo có thể gồm:

- Lỗi kết nối/timeout tăng kéo dài trên một route.
- auth_error xuất hiện hàng loạt sau thay đổi cấu hình.
- Rate limit tăng cùng retry amplification và quota giảm.
- Pending hoặc tuổi công việc vượt ngân sách cho phép.
- Kết quả callback bị gián đoạn dù API vẫn chấp nhận công việc.
- Tỷ lệ thông báo hết hạn trước khi gửi tăng.
- Yêu cầu thu hồi session không đạt trạng thái hoàn tất theo mô hình được định nghĩa.
- Telemetry ngừng cập nhật.

Ngưỡng như “lỗi hơn 5% trong nhiều cửa sổ với tối thiểu 100 attempt” chỉ là ví dụ về cách kết hợp tỷ lệ và số mẫu. Không áp số đó mặc định cho mọi provider. Một lỗi auth ở tuyến ít lưu lượng cũng có thể cần xử lý ngay.

SLO cho dependency và SLO cho recovery có mẫu số khác nhau. Theo dõi cả route chính lẫn kết quả người dùng: failover có thể giữ recovery hoạt động nhưng route chính vẫn đang hỏng và làm giảm dự phòng.

Khi nhiều cảnh báo cùng phản ánh một sự cố, nhóm theo provider/route/operation và vùng phù hợp. Không gửi một cảnh báo vận hành riêng cho từng tài khoản hoặc từng OTP.

## 13. Quan sát retry, timeout và circuit breaker

Retry giúp vượt qua lỗi tạm thời nhưng có thể làm tăng tải lên dependency đang quá tải. Timeout cũng không chứng minh thao tác phía bên ngoài chưa xảy ra. AWS mô tả việc dùng timeout, backoff và jitter cùng cân nhắc idempotency để hạn chế các tác dụng này. [AWS: Timeouts, retries, and backoff with jitter](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/)

Những tín hiệu cần đặt cạnh nhau:

```text
logical operations
physical attempts
retry delay
in-flight
pool waiting
timeout theo phase
circuit state / blocked operations
pending age
unknown outcomes
```

Nếu retry tăng nhưng số operation hoàn tất không cải thiện, cơ chế phục hồi có thể đang tiêu thụ thêm quota mà không tạo giá trị.

Đặt ngân sách tổng cho thao tác, không chỉ timeout riêng từng attempt. Phải xét thời gian chờ queue, backoff và thời hạn challenge. Retry ở nhiều lớp có thể khuếch đại số lời gọi; cần biết SDK và ứng dụng đang làm gì.

Khi circuit mở, hệ thống vẫn cần lưu dấu vết công việc bị ảnh hưởng và cách xử lý tiếp theo. Không xóa pending chỉ để biểu đồ lỗi giảm. Khi phục hồi, xả backlog có kiểm soát, giữ idempotency và bỏ qua bằng chứng recovery đã không còn hợp lệ theo chính sách.

## 14. Xử lý sự cố mà không hạ yêu cầu xác minh

Một runbook minh họa:

1. Xác định operation, route, vùng và thời điểm bắt đầu ảnh hưởng từ số liệu phía caller.
2. Kiểm tra telemetry có đầy đủ hay không; đối chiếu attempt, logical outcome và pending.
3. So sánh thay đổi cấu hình gần đây, credential, mạng, quota và pipeline callback.
4. Thu thập mã lỗi cùng định danh đối soát tối thiểu trong kho được bảo vệ.
5. Đối chiếu nguồn thông tin provider; chưa vội quy mọi timeout là outage toàn dịch vụ.
6. Áp biện pháp đã định: giảm tải, retry có giới hạn, chuyển tuyến hợp lệ hoặc tạm dừng bước phụ thuộc.
7. Theo dõi backlog, kết quả chưa rõ và ảnh hưởng sau khi tuyến bắt đầu hoạt động lại.

Các giới hạn bảo mật cần được giữ:

- Risk engine không dùng được không tự động biến quyết định rủi ro thành ALLOW.
- Dịch vụ xác minh danh tính lỗi không cho phép đánh dấu hồ sơ đã xác minh.
- Email chậm không cho phép chấp nhận token đã hết hạn.
- SMS lỗi không cho phép chuyển sang một số điện thoại chưa được tin cậy chỉ vì người yêu cầu cung cấp.
- Session revoke chưa hoàn tất không được ghi nhận như đã thu hồi toàn bộ phiên.
- Nhà cung cấp mới phải đáp ứng chính sách về dữ liệu và mức xác minh của operation.

Các phương thức recovery khác chỉ được sử dụng nếu đã có trong chính sách và người dùng đáp ứng bằng chứng tương ứng. Trạng thái của provider không phải một bằng chứng danh tính.

Với lần gửi timeout chưa rõ kết quả, việc chuyển provider hoặc route có thể gửi trùng. Runbook cần thể hiện giới hạn đó và cơ chế đối soát, không làm mới khóa idempotency để che đi attempt cũ.

## 15. Tình huống phân tích tổng hợp

Giả sử dashboard ghi nhận:

```text
API recovery: vẫn phản hồi nhanh
SMS provider accepted: chưa giảm rõ
physical attempts / logical operations: tăng
queue oldest age: tăng
callback completion: giảm
timeout ở một vùng caller: tăng
```

Không đủ căn cứ để kết luận provider toàn cầu ngừng hoạt động.

Một hướng phân tích:

| Quan sát bổ sung | Giả thuyết được củng cố |
| --- | --- |
| Chỉ một vùng caller có connect timeout | Egress, DNS hoặc đường mạng theo vùng |
| Mọi vùng đều có rate_limited, quota gần cạn | Quota dùng chung hoặc retry gây quá tải |
| Gửi được nhưng endpoint callback trả lỗi | Kết quả bị kẹt ở pipeline callback |
| Lỗi bắt đầu ngay sau rotate secret | Sai credential/quyền hoặc rollout cấu hình |
| Chỉ một route SMS có kết quả giao nhận xấu | Sự cố tuyến/nhà mạng hoặc cấu hình route |
| Circuit mở làm attempt giảm nhưng pending tiếp tục tăng | Dependency chưa phục hồi dù tỷ lệ lỗi HTTP giảm |

Nếu mã có thời hạn 10 phút và việc xếp hàng, xử lý, vận chuyển đã dùng hết phần lớn khoảng đó, trải nghiệm recovery vẫn suy giảm ngay cả khi request provider cuối cùng thành công. Cần đánh giá phần thời gian còn lại theo policy, không kéo dài token để làm giảm số trường hợp hết hạn.

Sau khi khắc phục, xác nhận cả ba tầng: kết nối ổn định, API dùng được và công việc nghiệp vụ tồn đọng được xử lý đúng. Những kết quả UNKNOWN cần được đối soát riêng.

## 16. Những cách đo dễ gây kết luận sai

| Cách đo | Điều có thể bị che khuất |
| --- | --- |
| Chỉ xem HTTP 200 | Lỗi nghiệp vụ, schema và công việc bất đồng bộ chưa hoàn tất |
| Chỉ xem latency thành công | Timeout và lời gọi bị hủy |
| Chỉ xem trung bình toàn hệ thống | Lỗi theo vùng, route và đuôi latency |
| Trung bình p95 của nhiều instance | Không cho ra p95 chung có ý nghĩa |
| Đếm mỗi lần SDK gọi là mọi attempt vật lý | Retry ẩn và chi phí thật |
| Lấy callback phút này chia request phút này | Sai lệch do độ trễ và cohort khác nhau |
| Coi không có metric là không có lỗi | Mất telemetry hoặc không có lưu lượng |
| Chỉ xem trang trạng thái provider | Lỗi credential, quota, mạng hoặc tích hợp riêng |
| Coi failover thành công là route chính khỏe | Mất dự phòng và tác động còn tồn tại |
| Xem delivered là chứng minh danh tính | Bỏ qua bước kiểm tra bằng chứng recovery |
| Thêm account ID/token vào label | Lộ dữ liệu và bùng nổ số chuỗi thời gian |

Giám sát phụ thuộc có giá trị khi làm rõ được điều hệ thống đang biết, điều chưa biết và bước recovery nào chịu ảnh hưởng. Telemetry cần dẫn đến hành động có kiểm soát, đồng thời giữ nguyên các ranh giới xác minh, thời hạn bằng chứng và trạng thái session mà luồng khôi phục yêu cầu.