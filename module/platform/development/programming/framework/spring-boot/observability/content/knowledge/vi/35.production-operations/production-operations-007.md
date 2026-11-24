# Kiểm soát chi phí lưu trữ

Observability giúp đội phát triển hiểu điều gì đang xảy ra trong ứng dụng, nhưng mỗi metric sample, log event và trace span đều tạo ra dữ liệu cần truyền, xử lý, lập chỉ mục và lưu giữ. Khi lưu lượng tăng, một metric có quá nhiều tag hoặc một log được ghi ở mọi request có thể làm chi phí tăng nhanh hơn nhiều so với dự kiến.

Kiểm soát chi phí lưu trữ là một phần của vận hành Spring Boot. Mục tiêu là giữ lại dữ liệu đủ để phát hiện vấn đề, điều tra lỗi và đáp ứng yêu cầu vận hành, đồng thời giới hạn dữ liệu trùng lặp, cardinality, sampling, retention và dung lượng index. Cần nhìn toàn bộ vòng đời từ Micrometer Observation và instrumentation trong ứng dụng, qua Collector/exporter, đến backend lưu trữ.

## 1. Hiểu các thành phần tạo ra chi phí

Không nên chỉ nhìn dung lượng file cuối cùng. Một nền tảng observability thường tính phí theo một hoặc nhiều yếu tố sau:

- **Ingestion:** số byte hoặc số event được gửi vào backend mỗi ngày.
- **Số time series đang hoạt động:** metric có nhiều tổ hợp label khác nhau tạo ra nhiều series, làm tăng chi phí ingest, bộ nhớ và truy vấn.
- **Index và metadata:** logs, traces và thuộc tính được lập chỉ mục có thể tốn thêm dung lượng và tài nguyên xử lý.
- **Retention:** dữ liệu được giữ càng lâu thì tổng dung lượng lưu trữ càng lớn.
- **Replication và high availability:** bản sao dữ liệu giúp tăng độ bền và khả năng sẵn sàng nhưng làm tăng tài nguyên cần dùng.
- **Query và compute:** truy vấn rộng, dashboard refresh quá thường xuyên, alert rule nặng hoặc truy vấn trên dữ liệu dài hạn có thể tiêu tốn CPU và bộ nhớ.
- **Network và processing:** truyền dữ liệu liên vùng, transform, enrichment, compression và xử lý ở Collector cũng có chi phí.

Ba tín hiệu có cách tăng trưởng khác nhau:

| Tín hiệu | Đơn vị dữ liệu chính | Yếu tố làm tăng nhanh |
| --- | --- | --- |
| Metrics | Time series và sample theo thời gian | Nhiều metric name, label cardinality cao, histogram có nhiều bucket, scrape interval ngắn |
| Traces | Trace và span | Request rate cao, nhiều span mỗi request, sampling cao, span chứa nhiều attribute |
| Logs | Log event và byte | Ghi log ở mức quá chi tiết, event lặp lại, payload lớn, index nhiều field |

Một quyết định giảm dữ liệu ở ứng dụng có thể giảm chi phí ở mọi tầng phía sau. Ngược lại, chỉ tăng dung lượng backend thường che khuất nguyên nhân gốc như metric tag không giới hạn hoặc debug log bị bật lâu ngày.

## 2. Ước lượng lượng dữ liệu trước khi đặt ngân sách

Ước lượng sơ bộ giúp xác định thành phần nào chiếm phần lớn chi phí. Các công thức dưới đây dùng dữ liệu thô để so sánh các phương án; dung lượng thực tế phụ thuộc encoding, compression, index, replication và cách backend tính phí.

### Metrics

Số sample mỗi ngày có thể ước lượng bằng:

\[
\text{samples/day} \approx \text{active series} \times
\frac{86\,400}{\text{scrape interval (seconds)}}
\]

Ví dụ, 10.000 series được scrape mỗi 15 giây tạo khoảng 57,6 triệu sample mỗi ngày. Nếu cardinality làm số series tăng lên 100.000, số sample tăng lên khoảng 576 triệu mỗi ngày dù scrape interval không đổi.

### Traces

Số span mỗi giây có thể ước lượng bằng:

\[
\text{spans/sec} \approx \text{requests/sec} \times
\text{spans/request} \times \text{sampling probability}
\]

Dung lượng thô mỗi ngày tiếp tục được ước lượng bằng số span mỗi giây nhân kích thước trung bình một span và 86.400 giây. Ví dụ, service xử lý 300 request/giây, trung bình 20 span/request và sampling 10% tạo khoảng 600 span/giây. Nếu mỗi span trung bình 700 byte, lượng dữ liệu span thô xấp xỉ 36,3 GB/ngày trước compression, index và replication.

### Logs

\[
\text{bytes/day} \approx \text{events/sec} \times
\text{average event size} \times 86\,400
\]

Ví dụ, 200 log event/giây với kích thước trung bình 500 byte tương đương khoảng 8,64 GB/ngày dữ liệu thô. Một stack trace dài hoặc payload JSON lớn có thể khiến kích thước trung bình tăng đáng kể.

Các phép tính trên là mô hình để lập ngân sách, không phải hóa đơn dự báo chính xác. Khi đo thực tế, hãy lấy số liệu ingestion, active series, span/event size, index size và compression ratio từ backend. Đo trong cả giờ cao điểm và thấp điểm để tránh dùng một thời điểm đại diện cho cả ngày.

## 3. Giảm cardinality của metrics ngay tại instrumentation

Cardinality là số tổ hợp giá trị khác nhau của các label trên một metric. Nếu metric `http.server.requests` có các chiều `method`, `route`, `status` và `region`, số series có thể tăng theo tích số lượng giá trị của từng chiều. Thêm một label có giá trị gần như khác nhau trên mỗi request có thể khiến số series tăng đột biến.

Các thuộc tính phù hợp cho metric thường có miền giá trị hữu hạn:

| Nên dùng | Tránh dùng làm metric tag |
| --- | --- |
| HTTP method như `GET`, `POST` | URL đầy đủ có query string tự do |
| Route template như `/orders/{id}` | Path thực tế chứa order ID |
| Status class như `2xx`, `4xx`, `5xx` | Exception message hoặc stack trace |
| Region hoặc environment có danh sách hữu hạn | User ID, email, session ID, request ID |
| Operation name ổn định | Tên operation ghép từ dữ liệu đầu vào |

Không dùng trace ID, span ID, user ID, order ID hoặc token làm metric tag. Những giá trị này tạo cardinality cao và có thể chứa dữ liệu nhạy cảm. Nếu cần truy vết một request, dùng trace ID trong logs/traces hoặc exemplar được backend hỗ trợ.

### Phân biệt low-cardinality và high-cardinality trong Micrometer Observation

Micrometer Observation cho phép gắn key-value vào Observation. Low-cardinality key-value có thể được chuyển thành tag cho metrics, vì vậy chỉ nên chứa giá trị có tập hữu hạn và ổn định. High-cardinality key-value dành cho dữ liệu chi tiết ở trace hoặc handler phù hợp; chúng không nên trở thành metric tag.

Ví dụ, operation nghiệp vụ có thể gắn tên ổn định và loại kết quả:

```java
Observation.createNotStarted("order.submit", observationRegistry)
        .lowCardinalityKeyValue("channel", "web")
        .lowCardinalityKeyValue("result", "accepted")
        .observe(() -> orderService.submit(command));
```

`channel` và `result` chỉ nên dùng theo cách này nếu tập giá trị được kiểm soát. Không thêm `command.getOrderId()` hoặc `command.getCustomerId()` làm low-cardinality key-value. Nếu một định danh cần thiết cho điều tra và được phép ghi nhận, hãy đánh giá việc đưa nó vào span dưới dạng high-cardinality attribute, giới hạn quyền truy cập và thời hạn lưu trữ. High-cardinality vẫn làm tăng kích thước trace và chi phí index.

Tên metric và tên Observation phải ổn định. Không tạo metric name động từ tên khách hàng, endpoint cụ thể hoặc exception. Với HTTP server, ưu tiên route template thay vì raw path; xác minh convention và filter của framework đang dùng để tránh các route có ID tạo thành hàng nghìn giá trị riêng.

### Đặt giới hạn cardinality và theo dõi thay đổi

Theo dõi số active series theo metric name, job, service và environment. Đặt cảnh báo khi một metric tăng nhanh hoặc vượt ngân sách. Khi thêm label mới, ước lượng số tổ hợp tối đa trước khi triển khai. Một tag có 20 giá trị thêm vào metric đang có 50.000 series có thể làm số series tăng theo bội số lớn tùy phân bố tổ hợp.

Không xóa label chỉ vì cardinality cao nếu nó đang cần thiết cho cảnh báo hoặc SLO. Hãy xác định truy vấn nào dùng label đó, tìm dimension thay thế có miền hữu hạn, hoặc chuyển dữ liệu chi tiết sang trace/log. Thay đổi label cũng có thể tạo series mới và làm dashboard lịch sử bị chia thành hai tập; cần cập nhật truy vấn và alert rule đồng thời.

## 4. Kiểm soát histogram và độ phân giải của metrics

Histogram hữu ích cho latency vì cho phép tính percentile tổng hợp qua nhiều instance. Tuy nhiên, histogram dạng bucket cổ điển tạo thêm series cho từng bucket, cộng với `_sum` và `_count`. Nếu một histogram có nhiều bucket và nhiều tổ hợp tag, số series có thể tăng rất nhanh.

Chọn bucket theo mục tiêu đo lường:

- Xác định SLO hoặc ngưỡng latency cần cảnh báo trước khi thêm bucket.
- Đặt nhiều độ phân giải hơn quanh vùng ngưỡng quan trọng; không cần dày đặc ở mọi miền giá trị.
- Giữ cùng cấu hình bucket giữa các instance để tổng hợp phân bố có ý nghĩa.
- Chỉ bật histogram cho metric thực sự cần phân bố latency; không bật đại trà cho mọi timer hoặc operation.
- Đánh giá số bucket cùng số tag combination để ước lượng active series.

Ví dụ cấu hình Spring Boot có thể bật histogram cho HTTP server request duration:

```yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
```

Tên metric phụ thuộc convention và instrumentation đang dùng; hãy xác minh tên thực tế trong endpoint metrics hoặc backend trước khi áp dụng. Cấu hình này có thể làm tăng số series, do đó cần tính cả bucket và tag combinations. Nếu backend hỗ trợ native histogram hoặc cơ chế histogram khác, đánh giá chi phí và khả năng tương thích của toàn bộ pipeline trước khi chọn.

Micrometer cũng có thể tính percentile tại phía ứng dụng cho một số meter. Percentile đã tính ở client không có cùng khả năng tổng hợp như histogram bucket qua nhiều instance. Chọn loại phân bố dựa trên cách truy vấn và SLO, thay vì bật đồng thời nhiều biểu diễn chỉ để có thêm biểu đồ.

### Dùng exemplar để liên kết metric với trace

Exemplar có thể lưu một tham chiếu trace ID cùng một quan sát histogram để người vận hành chuyển từ metric latency đến trace mẫu. Cách này giúp điều tra một request cụ thể mà không cần thêm trace ID làm label cho mọi metric sample. Exemplar cần hỗ trợ từ instrumentation, registry/exporter và backend; hãy xác minh pipeline đang sử dụng trước khi dựa vào nó.

## 5. Chọn sampling cho distributed tracing

Chi phí trace phụ thuộc số request được giữ, số span mỗi request và kích thước span. Sampling là một trong những đòn bẩy trực tiếp nhất để điều chỉnh volume, nhưng giảm sampling quá mạnh có thể khiến mất trace hiếm hoặc trace lỗi.

### Head-based sampling

Head-based sampling quyết định giữ trace tại thời điểm bắt đầu. Trong cấu hình Spring Boot hỗ trợ Micrometer Tracing, có thể đặt xác suất sampling bằng thuộc tính:

```yaml
management:
  tracing:
    sampling:
      probability: 0.10
```

Giá trị `0.10` minh họa tỷ lệ 10%. Xác minh phiên bản Spring Boot, tracing bridge và cấu hình sampler thực tế; sampling probability không phải chính sách bảo đảm giữ mọi trace lỗi hoặc trace chậm. Nếu request được lấy mẫu ở đầu trace, các service downstream cần tiếp tục cùng trace context và tôn trọng quyết định sampling để dữ liệu không bị chia cắt.

Head-based sampling đơn giản và chi phí dễ dự đoán, phù hợp khi lưu lượng lớn và cần một mẫu đại diện. Hạn chế là tại thời điểm quyết định, hệ thống chưa biết request sẽ chậm hay lỗi; một trace lỗi hiếm vẫn có thể không được giữ.

### Tail-based sampling

Tail-based sampling đánh giá trace sau khi Collector nhận đủ các span cần thiết. Chính sách có thể giữ trace có lỗi, duration vượt ngưỡng hoặc thuộc operation quan trọng, đồng thời loại một phần trace thành công thông thường.

Tail sampling phù hợp khi cần ưu tiên các trường hợp hiếm nhưng có giá trị điều tra. Nó cần Collector giữ trạng thái trong thời gian chờ, định tuyến các span của cùng trace đến cùng nơi xử lý và giới hạn bộ nhớ. Nếu cấu hình không đủ tài nguyên hoặc span bị phân tán giữa các collector, quyết định tail sampling có thể sai hoặc làm mất trace.

### Kết hợp chính sách sampling

Một chiến lược production có thể giữ một tỷ lệ nền cho trace thành công, ưu tiên giữ trace lỗi và trace chậm bằng tail sampling, đồng thời có chính sách riêng cho operation quan trọng. Cần tránh cấu hình sampling chồng chéo không rõ thứ tự khiến dữ liệu bị giữ nhiều hơn dự kiến.

Khi giảm sampling, hãy kiểm tra các câu hỏi sau:

- Có đủ trace để điều tra p95/p99 và các lỗi hiếm không?
- Có giữ được trace của luồng thanh toán, đăng nhập hoặc operation có tác động lớn không?
- Sampling có nhất quán giữa các service và ranh giới bất đồng bộ không?
- Collector có đủ bộ nhớ, CPU và khả năng định tuyến cho tail sampling không?
- Số span thực tế sau sampling có khớp với ngân sách đã dự báo không?

Không nên chỉ giảm xác suất sampling để xử lý hóa đơn tăng mà chưa tìm nguyên nhân. Một instrumentation tạo 200 span cho mỗi request hoặc một span chứa payload lớn có thể cần tối ưu trước.

## 6. Giảm volume và kích thước của traces

Một trace nên mô tả ranh giới operation có giá trị điều tra. Instrument mọi method nhỏ hoặc tạo span lồng nhau không cần thiết có thể tăng số span mà không làm rõ nguyên nhân.

Các cách kiểm soát:

- Instrument các ranh giới có ý nghĩa như HTTP server/client, database call, message publish/consume và operation nghiệp vụ quan trọng.
- Tránh tạo span cho getter, helper hoặc vòng lặp nhỏ nếu chúng không giúp xác định bottleneck.
- Dùng tên span ổn định; không đưa ID đơn hàng, user ID hoặc giá trị động vào tên span.
- Chỉ ghi attribute phục vụ lọc hoặc giải thích hành vi; tránh gắn toàn bộ request/response payload.
- Không ghi stack trace hay exception message lặp lại vào nhiều span nếu trạng thái và event hiện có đã đủ thông tin.
- Tránh duplicate instrumentation khiến một lời gọi tạo hai span tương đương.
- Kiểm tra propagation qua executor và message broker để không tạo trace mới không cần thiết hoặc span trùng do instrument hai lần.

Trong Micrometer Observation, chỉ tạo Observation cho operation cần quan sát. Dùng low-cardinality key-value cho dimension metric có miền hữu hạn; high-cardinality key-value chỉ thêm vào trace khi thực sự cần và được chính sách dữ liệu cho phép.

## 7. Kiểm soát log volume và chi phí index

Logs thường tăng nhanh khi debug được bật trên production, khi mỗi request ghi nhiều dòng hoặc khi ứng dụng log cả payload. Hãy xác định log nào giúp vận hành và log nào chỉ lặp lại thông tin đã có trong metrics hoặc traces.

### Chọn log level theo mục đích

| Level | Cách dùng trong production | Ví dụ |
| --- | --- | --- |
| ERROR | Lỗi cần xử lý hoặc làm operation thất bại | Dependency timeout khiến request không hoàn thành |
| WARN | Tình huống bất thường cần theo dõi nhưng vẫn phục hồi | Retry đã thành công sau một lần lỗi tạm thời |
| INFO | Sự kiện vòng đời hoặc nghiệp vụ quan trọng, có tần suất kiểm soát | Service khởi động, cấu hình triển khai được áp dụng |
| DEBUG | Chi tiết phục vụ chẩn đoán trong khoảng thời gian ngắn | Giá trị nhánh xử lý nội bộ không nhạy cảm |
| TRACE | Chi tiết rất nhỏ, chỉ bật có kiểm soát khi cần | Dòng điều khiển chi tiết của thư viện |

Không ghi một INFO log cho mọi lần gọi hàm nếu metric và trace đã thể hiện số lần gọi cùng duration. Dùng WARN cho lỗi đã retry thành công một cách có chọn lọc; nếu một dependency lỗi liên tục, một WARN cho mỗi retry có thể tạo log storm. Cần có cơ chế rate limit hoặc tổng hợp sự kiện khi lỗi lặp lại.

### Ghi log có cấu trúc và tránh payload lớn

Ưu tiên JSON hoặc structured logging với các trường ổn định như timestamp, level, service, environment, operation, trace ID và span ID. Tránh log toàn bộ object request, response, header hoặc dữ liệu cá nhân. Ghi mã lỗi, loại lỗi và một số thuộc tính đã được cho phép thường hữu ích hơn payload đầy đủ.

Giữ field index ở mức cần thiết. Index mọi trường JSON có thể làm tăng chi phí lưu trữ và truy vấn; những field ít khi lọc có thể chỉ giữ trong nội dung log không index nếu backend hỗ trợ. Dùng parsing và schema ổn định để tránh cùng một ý nghĩa được lưu dưới nhiều tên field.

### Sampling và rate limiting cho logs

Sampling phù hợp với log lặp lại có tần suất cao, chẳng hạn một thông báo debug giống nhau trên mọi request thành công. Không sampling mù các log bảo mật, audit, lỗi nghiêm trọng hoặc sự kiện bắt buộc theo chính sách. Với log lặp lại, có thể ghi một mẫu kèm bộ đếm tổng hợp để vẫn biết tần suất xảy ra.

Nếu áp dụng sampling, ghi rõ tỷ lệ hoặc phương pháp lấy mẫu ở metadata vận hành để người điều tra hiểu rằng log không đầy đủ. Không dùng sampling để che giấu lỗi hoặc làm sai số liệu audit. Các log cần phục vụ compliance phải tuân theo chính sách lưu giữ và tính toàn vẹn riêng.

## 8. Lọc và xử lý dữ liệu tại OpenTelemetry Collector

Collector là điểm thích hợp để áp dụng một số chính sách chung trước khi gửi dữ liệu đến backend. Các processor thường dùng gồm:

- **Memory limiter:** giới hạn bộ nhớ và tạo backpressure phù hợp khi Collector gần quá tải.
- **Batch:** gom dữ liệu thành batch để giảm overhead truyền tải và tăng hiệu quả export.
- **Filter:** loại signal, span, metric hoặc log không cần thiết theo điều kiện đã xác định.
- **Attributes/resource processor:** chuẩn hóa hoặc xóa attribute không cần thiết, đồng thời bảo đảm resource metadata nhất quán.
- **Tail sampling:** giữ hoặc loại trace dựa trên trạng thái, duration và thuộc tính sau khi nhận span.
- **Transform:** chuẩn hóa dữ liệu, bỏ field không được phép hoặc giảm payload trước khi export.

Collector không thay thế kiểm soát ở ứng dụng. Nếu ứng dụng tạo quá nhiều series hoặc span, dữ liệu vẫn tiêu tốn tài nguyên trên đường truyền và tại Collector trước khi bị loại. Hãy giảm cardinality và instrumentation dư thừa tại nguồn, sau đó dùng Collector để thực thi chính sách tập trung.

Khi cấu hình processor, cần kiểm tra thứ tự xử lý. Ví dụ, filter đặt trước tail sampling có thể loại span cần thiết để nhận biết trace lỗi; transform xóa thuộc tính trước khi sampling có thể làm chính sách không còn điều kiện đánh giá. Bảo đảm các span cùng trace được định tuyến đến cùng nhóm tail sampler và có giới hạn thời gian chờ hợp lý.

Không loại dữ liệu chỉ vì tên metric hoặc span lạ mà chưa kiểm tra dashboard, alert, SLO và use case điều tra. Mọi rule filter cần có owner, lý do, phạm vi áp dụng và cách rollback.

## 9. Thiết kế retention theo giá trị vận hành

Giữ tất cả dữ liệu ở mức chi tiết trong thời gian dài thường không cần thiết. Retention nên phụ thuộc vào tốc độ điều tra, yêu cầu audit, SLO, chính sách pháp lý và khả năng truy vấn dữ liệu cũ.

Một mô hình nhiều tầng có thể gồm:

| Tầng lưu trữ | Loại dữ liệu phù hợp | Mục đích |
| --- | --- | --- |
| Hot | Metrics chi tiết gần thời gian thực, logs/traces mới | Dashboard, alert và điều tra sự cố đang diễn ra |
| Warm | Metrics đã tổng hợp, logs/traces cần tra cứu trong thời gian ngắn hơn | Phân tích xu hướng và điều tra sau sự cố |
| Cold/archive | Dữ liệu audit hoặc bản ghi cần giữ lâu theo chính sách | Tra cứu hiếm, phục vụ yêu cầu lưu giữ |

Không có một số ngày retention phù hợp cho mọi hệ thống. Đặt thời hạn cụ thể theo từng signal và môi trường. Traces có thể cần thời gian hot ngắn hơn metrics tổng hợp; logs audit có thể cần thời hạn dài hơn logs debug. Môi trường development thường không cần giữ dữ liệu chi tiết lâu như production.

### Metrics: downsampling và recording rules

Giữ metrics chi tiết ở độ phân giải cao trong khoảng thời gian cần cho điều tra gần thời gian thực. Sau đó có thể dùng recording rules hoặc tính năng downsampling của backend để lưu chuỗi đã tổng hợp với bước thời gian dài hơn. Ví dụ, dữ liệu 15 giây có thể được tổng hợp thành cửa sổ 5 phút cho báo cáo xu hướng dài hạn.

Downsampling làm mất chi tiết ngắn hạn. Không dùng chuỗi đã tổng hợp để trả lời câu hỏi cần spike vài giây hoặc percentile gốc nếu phép tổng hợp không bảo toàn phân bố. Giữ các series phục vụ SLO, capacity planning và báo cáo cần thiết theo độ phân giải phù hợp.

### Logs và traces: retention theo loại sự kiện

Có thể áp dụng retention khác nhau cho application logs, audit logs, security events và debug logs. Với traces, có thể giữ trace lỗi hoặc trace được chọn bởi tail sampling lâu hơn trace thành công thông thường nếu backend hỗ trợ policy theo thuộc tính. Cần kiểm tra rằng chính sách không vô tình làm mất trace cần thiết để tái hiện sự cố.

Trước khi xóa hoặc chuyển tier, xác nhận yêu cầu pháp lý, hợp đồng, bảo mật và khả năng khôi phục. Dữ liệu archive có thể rẻ hơn nhưng truy vấn chậm hơn hoặc cần quy trình restore; phải ghi rõ giới hạn đó cho đội vận hành.

## 10. Kiểm soát truy vấn, dashboard và export pipeline

Chi phí không chỉ nằm ở dung lượng ingest. Dashboard refresh quá thường xuyên, truy vấn không giới hạn thời gian hoặc alert rule chạy trên toàn bộ label combinations có thể tiêu tốn compute đáng kể.

Một số nguyên tắc:

- Đặt time range mặc định hợp lý; không truy vấn toàn bộ lịch sử khi dashboard chỉ cần một giờ gần nhất.
- Tránh truy vấn regex rộng hoặc join nhiều chiều cardinality cao nếu không cần thiết.
- Dùng recording rules cho truy vấn tổng hợp được dùng lặp lại.
- Giãn chu kỳ refresh của dashboard ít được theo dõi; không cần mọi biểu đồ tự làm mới mỗi vài giây.
- Đặt giới hạn concurrency, timeout và query range cho người dùng hoặc workspace khi backend hỗ trợ.
- Theo dõi alert rule tốn tài nguyên, lỗi timeout và truy vấn có scan volume lớn.
- Tối ưu batch và compression trên exporter/Collector theo giới hạn của backend; không tăng batch vô hạn vì có thể làm tăng bộ nhớ và độ trễ.

Với Spring Boot, `step` của metrics exporter quyết định chu kỳ export ở một số registry. Chu kỳ ngắn hơn có thể tăng số lần gửi và chi phí xử lý; chu kỳ dài hơn làm giảm độ phân giải quan sát. Chọn chu kỳ dựa trên yêu cầu alert và backend, không chọn nhỏ nhất chỉ vì muốn dashboard cập nhật nhanh.

## 11. Phân bổ ngân sách và quản trị thay đổi

Chi phí cần được gắn với service, team, environment và signal để xác định nơi phát sinh. Dùng resource attributes ổn định như service name, environment, region và version khi backend hỗ trợ phân bổ chi phí theo metadata. Tránh đưa định danh người dùng hoặc dữ liệu nghiệp vụ nhạy cảm vào nhãn chi phí.

Thiết lập ngân sách theo các chỉ số có thể theo dõi:

- Active metric series và số sample mỗi ngày.
- Ingest bytes hoặc events mỗi ngày theo signal.
- Span per request, trace sampling rate và tổng số span được giữ.
- Log events/second, kích thước event trung bình và tỷ lệ log theo level.
- Retention days, index size, storage bytes và query compute.
- Tỷ lệ dữ liệu bị filter, dropped hoặc export thất bại.

Khi một chỉ số tăng bất thường, truy ngược theo service, metric name, label, logger, operation hoặc Collector pipeline. Đừng chỉ tăng quota hoặc giảm retention toàn cục; thay đổi đó có thể ảnh hưởng đến các service khác đang vận hành đúng ngân sách.

Mọi thay đổi có ảnh hưởng lớn đến dữ liệu nên được review như một thay đổi vận hành:

1. Nêu lý do và tín hiệu đang tạo chi phí.
2. Ước lượng lượng dữ liệu trước và sau thay đổi.
3. Liệt kê dashboard, alert, SLO và use case điều tra bị ảnh hưởng.
4. Thử nghiệm trên một service hoặc môi trường nhỏ.
5. Theo dõi ingestion, dropped data, latency và khả năng điều tra sau triển khai.
6. Ghi nhận owner, thời điểm đánh giá lại và cách rollback.

## 12. Ví dụ: giảm chi phí traces và metrics cho service checkout

Giả sử `checkout` xử lý 300 request/giây, trung bình 20 span/request. Với sampling 100%, hệ thống tạo khoảng 6.000 span/giây. Nếu sampling 10%, còn khoảng 600 span/giây. Với kích thước trung bình 700 byte/span, lượng dữ liệu span thô giảm từ khoảng 362,9 GB/ngày xuống 36,3 GB/ngày trước compression, index và replication.

Tuy nhiên, nếu tất cả span đều có 30 attribute, trong đó nhiều attribute là payload hoặc ID không cần thiết, kích thước trung bình của span vẫn có thể lớn. Vì vậy, đội vận hành đồng thời:

1. Giữ span cho các ranh giới HTTP, database và payment; bỏ instrumentation của helper nhỏ tạo span trùng lặp.
2. Loại payload và attribute không dùng cho lọc hoặc điều tra; giữ trạng thái, duration, service và operation cần thiết.
3. Dùng sampling nền, sau đó cấu hình tail sampling để ưu tiên trace lỗi và trace vượt ngưỡng latency.
4. Giữ route template trong metric tag; chuyển order ID ra khỏi metrics và chỉ giữ tham chiếu được phê duyệt ở trace nếu có nhu cầu.
5. Theo dõi active series, span volume và tỷ lệ trace lỗi được giữ để xác nhận chất lượng điều tra.

Với metrics, giả sử service có 10.000 active series ở scrape interval 15 giây. Số sample khoảng 57,6 triệu/ngày. Nếu thêm tag `orderId`, số series có thể tăng theo số đơn hàng duy nhất; giảm scrape interval xuống 5 giây còn làm số sample tăng gấp ba. Cần giới hạn route, method, status class và các dimension hữu hạn; chỉ bật histogram cho metric latency cần dùng cho SLO.

Ví dụ này minh họa cách kết hợp nhiều đòn bẩy. Không nên giảm sampling đến mức không còn đủ trace lỗi, hoặc bỏ histogram khiến percentile/SLO không còn tính được. Mỗi thay đổi phải được xác nhận bằng số liệu ingestion và khả năng phát hiện, điều tra sự cố.

## 13. Những sai lầm thường gặp

- **Giảm retention trên toàn hệ thống ngay khi chi phí tăng:** có thể làm mất dữ liệu audit hoặc lịch sử cần thiết. Hãy phân loại theo signal và yêu cầu lưu giữ.
- **Sampling trace đồng đều mà không xem loại request:** có thể bỏ lỡ lỗi hiếm và luồng quan trọng. Cân nhắc chính sách tail sampling và trace đối chứng.
- **Đưa ID vào metric tag để tiện debug:** làm cardinality tăng mạnh. Dùng trace/log correlation hoặc exemplar.
- **Bật histogram cho mọi meter:** tạo nhiều bucket series mà không đem lại giá trị cho mọi operation. Chỉ bật ở metric cần phân tích phân bố.
- **Ghi INFO hoặc DEBUG cho mọi request:** tạo log volume lớn và làm khó tìm sự kiện quan trọng. Dùng metrics, traces, log level và rate limit.
- **Filter ở Collector nhưng giữ instrumentation dư thừa ở ứng dụng:** vẫn tiêu tốn CPU, network và bộ nhớ trước khi dữ liệu bị loại. Tối ưu từ nguồn.
- **Xóa attribute trước tail sampling:** có thể làm mất điều kiện cần để giữ trace lỗi hoặc trace chậm. Xác minh thứ tự processor.
- **Chỉ đo dung lượng storage:** bỏ qua active series, index, query compute, replication và network. Theo dõi toàn bộ cost drivers.
- **Thay đổi dữ liệu mà không cập nhật dashboard/alert:** có thể làm cảnh báo sai hoặc mất khả năng phát hiện. Review truy vấn cùng instrumentation.

## 14. Checklist kiểm soát chi phí lưu trữ

- [ ] Đã đo ingestion, active series, span volume, log volume, index size và retention theo từng signal.
- [ ] Đã có ước lượng dữ liệu/ngày và ngân sách theo service, environment hoặc team.
- [ ] Metric tag chỉ dùng dimension có miền giá trị hữu hạn; route dùng template.
- [ ] Không có trace ID, user ID, order ID, token hoặc payload trong metric tag.
- [ ] Histogram chỉ bật ở metric cần thiết; số bucket phù hợp với SLO và chi phí series.
- [ ] Trace sampling có tỷ lệ nền và chính sách giữ trace lỗi/trace chậm khi cần.
- [ ] Span name ổn định, instrumentation không trùng lặp và attribute được giới hạn.
- [ ] Log level, log sampling và rate limiting được kiểm soát; audit/security logs tuân theo retention riêng.
- [ ] Collector có batch, memory limit, filter và tail sampling phù hợp; thứ tự processor đã được kiểm tra.
- [ ] Retention, downsampling và archive phù hợp với yêu cầu điều tra, SLO và chính sách dữ liệu.
- [ ] Dashboard, alert và query có time range, refresh interval và chi phí hợp lý.
- [ ] Có cảnh báo khi cardinality, ingestion hoặc dropped data tăng bất thường.
- [ ] Mọi thay đổi giảm dữ liệu đều được kiểm tra tác động đến alert, SLO và khả năng điều tra.

Kiểm soát chi phí observability hiệu quả bắt đầu từ việc chỉ tạo dữ liệu có giá trị, sau đó giới hạn cách dữ liệu được lấy mẫu, xử lý, lập chỉ mục và lưu giữ. Với Spring Boot, Micrometer Observation giúp kiểm soát nơi tạo metrics và spans; Collector hỗ trợ áp dụng chính sách tập trung; backend quyết định index, retention, downsampling và truy vấn. Theo dõi cả chi phí lẫn chất lượng tín hiệu để hệ thống vẫn phát hiện và giải thích được sự cố khi quy mô tăng.
