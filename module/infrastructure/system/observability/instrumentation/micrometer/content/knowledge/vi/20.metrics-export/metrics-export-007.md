# Giới hạn lô, thời gian chờ và hành vi lỗi phụ thuộc từng registry

Micrometer cung cấp API chung để ghi nhận metrics, nhưng mỗi registry có cách chuyển dữ liệu đến backend khác nhau. Prometheus thường đọc dữ liệu từ endpoint của ứng dụng theo mô hình pull; các registry push như OTLP hoặc dịch vụ giám sát có thể gom dữ liệu theo chu kỳ rồi gửi qua HTTP hoặc giao thức riêng. Vì thế, giới hạn lô, timeout, retry, buffer và cách xử lý lỗi phải được hiểu theo registry và transport đang dùng.

Trong module **OBSERVABILITY_INSTRUMENTATION_MICROMETER**, cấu hình export ảnh hưởng trực tiếp đến độ trễ dữ liệu, bộ nhớ ứng dụng, tải mạng và khả năng mất mẫu khi backend gặp sự cố. Bài này phân biệt các loại giới hạn thường gặp, giải thích cách đọc cấu hình theo từng registry, đưa ví dụ Prometheus và OTLP, đồng thời trình bày cách kiểm tra timeout và lỗi export trong môi trường tích hợp.

## 1. Không có một bộ giới hạn export chung cho mọi MeterRegistry

MeterRegistry thống nhất cách tạo Counter, Gauge, Timer và DistributionSummary. Registry cụ thể quyết định cách những meter đó được xuất.

| Kiểu registry | Ai khởi tạo lần truyền dữ liệu? | Chu kỳ/lô được quản lý ở đâu? | Timeout thuộc về đâu? |
|---|---|---|---|
| Prometheus pull | Prometheus server gọi endpoint ứng dụng | Scrape interval, scrape timeout và giới hạn scrape do Prometheus cấu hình | Chủ yếu ở phía Prometheus scrape; ứng dụng cũng cần xử lý request HTTP |
| Push/step registry | Ứng dụng gửi dữ liệu đến backend | Step và cách đóng gói payload do registry hoặc exporter quy định | HTTP client, transport hoặc cấu hình riêng của registry |
| OTLP metrics export | Ứng dụng gửi metrics đến OTLP receiver | Step, batch size và cấu hình export theo phiên bản registry/Spring Boot | Connect/read timeout và hành vi lỗi của OTLP exporter |
| StatsD hoặc agent-based registry | Ứng dụng gửi packet hoặc agent đọc dữ liệu | Kích thước packet, buffer và flush phụ thuộc giao thức/agent | Socket, packet delivery hoặc agent; có thể không có phản hồi xác nhận |

Do đó, không nên tìm một thuộc tính batch-size hay timeout chung trong MeterRegistry rồi áp dụng cho mọi backend. Hãy xác định registry thực tế, phiên bản Micrometer/Spring Boot và tài liệu cấu hình của chính registry đó.

Cùng một khái niệm có thể mang ý nghĩa khác nhau. Step thường là khoảng thời gian gom số liệu trước khi xuất; batch-size thường giới hạn số meter hoặc điểm dữ liệu trong một lần gửi; scrape_timeout là thời gian Prometheus chờ ứng dụng trả lời. Chúng không thể thay thế cho nhau.

## 2. Phân biệt step, batch size, payload limit và buffer

Các giới hạn export thường bị nhầm lẫn vì đều có thể ảnh hưởng đến lượng dữ liệu gửi trong một lần.

| Khái niệm | Ý nghĩa | Điều nó không có nghĩa |
|---|---|---|
| Step | Khoảng thời gian registry gom hoặc luân chuyển số liệu trước lần export | Không nhất thiết là số meter tối đa trong một request |
| Batch size | Số meter/điểm dữ liệu tối đa được gom vào một batch, nếu registry hỗ trợ | Không phải số request nghiệp vụ được xử lý |
| Payload/body limit | Kích thước dữ liệu tối đa mà transport hoặc backend chấp nhận | Không nhất thiết bằng batch size cố định |
| Buffer/queue capacity | Số lượng phần tử hoặc payload có thể chờ gửi | Không bảo đảm dữ liệu được lưu bền vững khi tiến trình dừng |
| Scrape interval | Tần suất Prometheus đọc endpoint | Không phải chu kỳ push của ứng dụng |
| Timeout | Thời gian chờ một giai đoạn của thao tác mạng hoặc export | Không nhất thiết hủy được thao tác ở phía backend |

Ví dụ, một registry có step 30 giây và batch size 1.000. Mỗi 30 giây, exporter thu thập số liệu của interval rồi có thể chia chúng thành các batch không vượt quá giới hạn cấu hình. Nếu payload có histogram với nhiều bucket và tag, số chuỗi được xuất có thể lớn hơn nhiều so với số meter logic trong ứng dụng.

Batch size cũng không đồng nghĩa với số time series cuối cùng. Một Timer hoặc DistributionSummary có histogram có thể tạo nhiều series như bucket, count và sum; registry có thể đóng gói những phần đó theo quy tắc riêng. Hãy xem tài liệu exporter để biết batch size đếm meter, data point, metric family hay request payload.

## 3. Batch lớn và batch nhỏ có trade-off khác nhau

Batch lớn làm giảm số lần gọi mạng và chi phí xử lý cố định ở mỗi request. Tuy nhiên, payload lớn hơn cần nhiều bộ nhớ để tạo và serialize, tốn thời gian truyền, dễ vượt giới hạn body của backend và có thể hết timeout trước khi gửi xong.

Batch nhỏ giảm kích thước mỗi request và giúp backend xử lý từng phần dễ hơn. Đổi lại, số lần gọi mạng tăng, tạo thêm overhead TLS/HTTP, header, scheduling và logging. Nếu backend bị chậm, nhiều batch nhỏ vẫn có thể tạo hàng đợi lớn.

Có thể dùng bảng sau để định hướng:

| Tình huống | Hướng cân nhắc |
|---|---|
| Số meter ít, payload nhỏ | Batch mặc định của registry thường đủ |
| Nhiều histogram và nhiều tag | Theo dõi kích thước payload; giảm cardinality trước khi tăng batch |
| Backend giới hạn request body | Chia batch theo giới hạn được tài liệu backend công bố |
| Backend xử lý chậm | Kiểm tra timeout, queue và backpressure trước khi tăng batch |
| Nhiều request nhỏ gây overhead | Có thể tăng batch nếu bộ nhớ và latency cho phép |
| Export tạo áp lực heap | Giảm batch, giảm histogram/bucket hoặc giảm số meter cần xuất |

Không nên tăng batch size chỉ để che giấu cardinality quá cao. Nếu hàng nghìn chuỗi thời gian phát sinh từ tag có ID duy nhất, cần sửa thiết kế tag trước; batch lớn chỉ gom một lượng dữ liệu không cần thiết vào payload lớn hơn.

## 4. Timeout có thể áp dụng ở nhiều giai đoạn

Một lần export qua HTTP có thể bao gồm nhiều giai đoạn:

1. Chờ lấy kết nối hoặc tạo socket.
2. Kết nối đến host và hoàn tất TLS handshake.
3. Gửi request body.
4. Chờ backend phản hồi.
5. Đọc và xử lý response.

Các thư viện có thể cung cấp connect timeout, read/response timeout hoặc request timeout. Không phải registry nào cũng expose tất cả các tham số này; tên thuộc tính và giá trị mặc định phụ thuộc phiên bản.

Timeout quá ngắn có thể khiến export thất bại khi backend có tải cao hoặc mạng có độ trễ. Timeout quá dài có thể khiến thread export bị giữ lâu, buffer tăng và các lần export sau bị chậm hoặc chồng lấn. Cần chọn timeout dựa trên kích thước payload, latency backend, step và ngân sách độ trễ chấp nhận được.

Một điều quan trọng: client hết thời gian chờ không chứng minh backend chưa nhận dữ liệu. Backend có thể đã nhận và xử lý request nhưng response bị trễ hoặc thất lạc. Nếu exporter retry, dữ liệu có thể được gửi lại. Hành vi trùng lặp hoặc khả năng khử trùng lặp phụ thuộc giao thức, temporality và backend.

## 5. Prometheus pull: timeout và giới hạn nằm ở phía scrape

Với Prometheus registry, ứng dụng expose endpoint metrics; Prometheus chủ động gọi endpoint theo scrape interval. Ứng dụng không push một batch theo step đến Prometheus server.

Ví dụ prometheus.yml:

~~~yaml
global:
  scrape_interval: 15s
  scrape_timeout: 10s

scrape_configs:
  - job_name: checkout-service
    metrics_path: /actuator/prometheus
    scrape_interval: 15s
    scrape_timeout: 8s
    sample_limit: 50000
    static_configs:
      - targets:
          - checkout-service:8080
~~~

Trong ví dụ:

- scrape_interval là khoảng cách giữa các lần scrape.
- scrape_timeout là thời gian Prometheus chờ lần scrape hoàn tất; nó không được lớn hơn scrape interval.
- sample_limit giới hạn số sample của một lần scrape theo khả năng và phiên bản Prometheus.
- metrics_path xác định endpoint ứng dụng cần đọc.

Nếu endpoint mất 12 giây để tạo response nhưng scrape timeout là 8 giây, Prometheus đánh dấu lần scrape thất bại. Có thể kiểm tra up{job="checkout-service"} và trang Targets để xem lỗi. up=0 cho biết lần scrape gần nhất không thành công; nó không chứng minh ứng dụng không tạo meter.

Ứng dụng cũng nên giữ endpoint scrape đủ nhanh. Các thao tác tốn thời gian như truy vấn database không nên chạy lại cho từng lần scrape nếu có thể lấy snapshot theo lịch và expose giá trị đã cập nhật. Kiểm soát số meter, histogram bucket và tag cardinality giúp giảm thời gian tạo response.

Với pull model, lỗi scrape thường dẫn đến thiếu mẫu ở lần đó. Prometheus có thể lưu trạng thái scrape và báo up=0; ứng dụng không nhất thiết nhận được thông báo lỗi từ Prometheus. Không áp dụng retry push ở phía ứng dụng cho một scrape mà ứng dụng không khởi tạo.

## 6. OTLP push: step, batch size và timeout theo cấu hình exporter

Với OTLP metrics registry, ứng dụng gửi dữ liệu đến OTLP receiver, thường là OpenTelemetry Collector hoặc backend tương thích. Spring Boot có thể cung cấp các thuộc tính export trong namespace management.otlp.metrics.export.

Ví dụ cấu hình minh họa:

~~~yaml
management:
  otlp:
    metrics:
      export:
        url: http://otel-collector:4318/v1/metrics
        step: 30s
        batch-size: 1000
        connect-timeout: 2s
        read-timeout: 10s
~~~

Các thuộc tính batch-size, connect-timeout và read-timeout phụ thuộc phiên bản Spring Boot và OTLP registry được sử dụng. Trước khi áp dụng, đối chiếu metadata configuration của đúng phiên bản dự án; nếu phiên bản không hỗ trợ một thuộc tính, không tự giả định nó có hiệu lực. Giá trị trên chỉ là ví dụ để minh họa các loại giới hạn.

- url trỏ đến endpoint nhận OTLP metrics; giao thức HTTP/gRPC và đường dẫn phải khớp receiver.
- step xác định chu kỳ export hoặc khoảng gom số liệu theo semantics của registry.
- batch-size giới hạn số phần tử trong một batch nếu exporter hỗ trợ thuộc tính đó.
- connect-timeout giới hạn thời gian thiết lập kết nối.
- read-timeout giới hạn thời gian chờ phản hồi/đọc dữ liệu từ endpoint theo transport.

Không đưa token thật vào file cấu hình được commit. Dùng biến môi trường hoặc secret manager để cấp headers, credential và chứng thư TLS. Với HTTPS, xác minh trust chain và hostname.

Nếu backend là Collector, cần kiểm tra receiver OTLP có bật đúng giao thức và cổng, pipeline metrics có exporter đến backend đích và Collector không từ chối payload vì kích thước hoặc giới hạn tài nguyên. Việc ứng dụng gửi thành công đến Collector mới chỉ xác nhận hop đầu tiên; cần theo dõi tiếp Collector export đến backend cuối.

## 7. Push registry và step: điều gì xảy ra khi export lỗi?

Push registry thường chạy tác vụ export theo step. Trong step hiện tại, số liệu được tích lũy; khi đến chu kỳ, registry chuẩn bị dữ liệu và gửi đến backend.

Khi export thất bại, kết quả phụ thuộc cách registry quản lý dữ liệu:

- Có registry chỉ log lỗi và tiếp tục chu kỳ tiếp theo.
- Có registry giữ hoặc retry payload theo cơ chế riêng.
- Có exporter dùng queue/buffer và có thể làm đầy queue khi backend chậm.
- Có giao thức chỉ gửi datagram hoặc packet không có xác nhận từ server, nên ứng dụng không biết backend đã nhận hay chưa.

Không được suy ra mọi PushMeterRegistry đều retry, giữ payload hoặc bảo đảm giao hàng ít nhất một lần. Hãy kiểm tra tài liệu registry và transport. Nếu registry poll dữ liệu của step rồi export thất bại mà không có buffer/replay, dữ liệu của interval đó có thể không được gửi lại. Nếu exporter retry sau timeout, backend có thể nhận dữ liệu lặp trong trường hợp response bị mất sau khi đã xử lý.

Đặc biệt, cần phân biệt:

- Lỗi trước khi gửi: DNS, connection refused hoặc TLS handshake thất bại; request có thể chưa đến backend.
- Lỗi trong khi gửi: socket bị đóng hoặc write timeout; backend có thể đã nhận một phần payload.
- Timeout khi chờ response: backend có thể đã xử lý xong nhưng client không nhận được phản hồi.
- HTTP 4xx: thường là cấu hình, schema, xác thực hoặc payload không hợp lệ; retry cùng request không sửa được nguyên nhân.
- HTTP 429/5xx: có thể do throttling hoặc backend tạm thời lỗi; cần theo chính sách retry/backoff của exporter.

## 8. Retry, backoff và nguy cơ gửi trùng

Retry giúp phục hồi lỗi tạm thời, nhưng cũng làm thay đổi semantics giao nhận. Khi client timeout sau khi backend đã nhận payload, lần retry có thể gửi cùng dữ liệu lần nữa.

Các câu hỏi cần xác minh với registry:

1. Registry có retry tự động không?
2. Retry cho mọi lỗi hay chỉ lỗi tạm thời như timeout, 429 và 5xx?
3. Có exponential backoff và jitter không?
4. Có giới hạn số lần retry hoặc tổng thời gian retry không?
5. Payload được giữ trong memory queue, persistent queue hay được tạo lại từ meter?
6. Khi queue đầy, exporter block thread, drop payload hay từ chối ghi nhận?
7. Giao thức/backend có cơ chế nhận diện hoặc khử trùng lặp không?

Không tự thêm vòng retry quanh thao tác ghi Counter hoặc Timer nếu exporter đã có retry. Retry ở tầng instrumentation có thể ghi nhận cùng một sự kiện hai lần. Retry gửi payload phải được quản lý ở tầng exporter/transport và phải hiểu rõ tính idempotent của giao thức.

Với metrics, nhiều backend sử dụng timestamp, temporality và quy tắc ingest để xử lý dữ liệu lặp hoặc out-of-order. Không mặc định rằng mọi backend đều khử trùng lặp giống nhau.

## 9. Buffer, backpressure và nguy cơ tăng bộ nhớ

Nếu tốc độ tạo metrics cao hơn tốc độ exporter gửi, hàng đợi export có thể tăng. Tác động gồm:

- Heap tăng do payload hoặc batch đang chờ.
- Garbage collection thường xuyên hơn khi serialize nhiều object.
- Độ trễ export tăng, dữ liệu đến dashboard muộn.
- Queue đầy khiến exporter phải block hoặc drop theo chính sách triển khai.
- Một backend chậm có thể ảnh hưởng thread hoặc tài nguyên ứng dụng nếu export đồng bộ.

Không phải registry nào cũng có queue có thể cấu hình. Một số registry chỉ giữ accumulator cho step hiện tại và xuất theo lịch; một số exporter có buffer riêng. Hãy kiểm tra cụ thể trước khi điều chỉnh queue capacity.

Nếu có backpressure, xử lý theo thứ tự:

1. Xác định backend chậm hay ứng dụng tạo quá nhiều metric.
2. Kiểm tra batch size, payload size và thời gian serialize.
3. Giảm cardinality, tag động và số histogram bucket không cần thiết.
4. Kiểm tra step và tốc độ export.
5. Kiểm tra queue capacity, drop policy và retry nếu exporter hỗ trợ.
6. Chỉ tăng buffer khi đã hiểu mức bộ nhớ tối đa và thời gian backend có thể gián đoạn.

Tăng buffer chỉ trì hoãn thời điểm đầy queue nếu tốc độ gửi vẫn thấp hơn tốc độ tạo dữ liệu. Buffer lớn hơn cũng làm tăng lượng dữ liệu có thể mất khi tiến trình dừng đột ngột nếu buffer chỉ nằm trong memory.

## 10. Giới hạn payload và phản ứng của backend

Backend hoặc proxy có thể giới hạn kích thước HTTP request, số data point, số metric trong batch hoặc thời gian xử lý. Khi payload vượt ngưỡng, server có thể trả 413 Payload Too Large, 400 Bad Request, 429 Too Many Requests hoặc 5xx tùy nguyên nhân.

Các bước xử lý:

- Xem HTTP status và response body trong log exporter.
- Kiểm tra giới hạn body của Collector, reverse proxy và backend cuối.
- Xác minh batch-size được tính theo metric, data point hay request.
- Kiểm tra histogram bucket và tag có làm payload phình lớn.
- Giảm batch hoặc chia lô nếu exporter hỗ trợ.
- Không bỏ metric quan trọng chỉ để làm request nhỏ; hãy loại meter debug và tag cardinality cao trước.

Nếu Collector nhận payload nhưng backend cuối từ chối, kiểm tra log và metrics của Collector. Thành công ở tầng HTTP đầu tiên không đồng nghĩa dữ liệu đã được lưu ở hệ thống truy vấn cuối.

## 11. Đóng ứng dụng và flush dữ liệu cuối

Khi ứng dụng shutdown, push registry có thể cần dừng scheduler và gửi dữ liệu còn lại. Hành vi đóng registry, flush cuối cùng hoặc chờ export hoàn tất phụ thuộc implementation và phiên bản.

Không giả định mọi close() đều bảo đảm gửi thành công toàn bộ dữ liệu cuối. Hãy kiểm tra:

- Registry có flush hoặc publish cuối khi close không?
- Shutdown timeout của ứng dụng có đủ cho thao tác đó không?
- Export đang chạy có bị interrupt khi JVM dừng không?
- Buffer có persistent hay chỉ nằm trong heap?
- Backend có thể truy cập được trong giai đoạn shutdown không?

Nếu metrics cuối cùng rất quan trọng, hãy thiết kế shutdown hook/lifecycle theo API được registry hỗ trợ và đặt thời gian dừng phù hợp. Metrics thường phục vụ quan sát vận hành, không nên được dùng làm kho dữ liệu giao dịch cần bảo đảm không mất bản ghi.

## 12. Theo dõi chính đường export

Không thể vận hành exporter tốt nếu chỉ quan sát metric nghiệp vụ. Cần theo dõi cả đường truyền metrics:

- Thời gian một lần export và phân vị latency của export nếu có.
- Số lần export thành công/thất bại.
- Số timeout, lỗi kết nối, HTTP 4xx/5xx và 429.
- Kích thước payload hoặc số data point trong batch nếu exporter cung cấp.
- Queue depth, số payload bị drop và số lần retry nếu có.
- Thời điểm export thành công gần nhất.
- Trạng thái Prometheus target đối với pull registry.
- Log từ Collector và backend cuối.

Tên metric nội bộ để theo dõi exporter thay đổi theo registry và phiên bản; không giả định một tên chung. Nếu registry không expose số đo tự giám sát, dùng log, HTTP client instrumentation, Collector telemetry hoặc health check của backend.

## 13. Kiểm thử batch, timeout và lỗi theo registry

SimpleMeterRegistry phù hợp để kiểm tra logic ghi meter trong bộ nhớ, nhưng nó không kiểm tra hành vi export, batch, timeout hay retry. Các kiểm thử đó cần registry/exporter thật hoặc test double đúng giao thức.

### Kiểm thử push/HTTP registry

Dùng mock HTTP server hoặc một endpoint test để:

1. Nhận request export và ghi lại headers, body, số data point.
2. Xác nhận payload được chia theo batch-size nếu registry hỗ trợ.
3. Trả response thành công và xác nhận exporter tiếp tục chu kỳ sau.
4. Trả 401/400 để kiểm tra lỗi cấu hình/payload.
5. Trả 429 hoặc 503 để quan sát retry/backoff thực tế.
6. Giữ response lâu hơn read timeout để kiểm tra timeout.
7. Ngắt kết nối trong lúc gửi để quan sát log và hành vi buffer.
8. Đếm request lặp để phát hiện retry có thể gửi trùng.

Không dùng Thread.sleep() tùy tiện để chờ step trong unit test. Ưu tiên clock giả, scheduler có thể điều khiển hoặc cấu hình step ngắn trong integration test.

### Kiểm thử Prometheus pull

Với Prometheus, kiểm tra theo phía scrape:

1. Xác nhận endpoint metrics trả response hợp lệ.
2. Tạo response chậm hơn scrape timeout để xác nhận target chuyển DOWN.
3. Xác nhận up và scrape error phản ánh đúng lỗi.
4. Tạo nhiều meter/histogram để kiểm tra sample_limit hoặc giới hạn scrape đã cấu hình.
5. Khôi phục endpoint và xác nhận scrape thành công trở lại.

### Kiểm thử phục hồi

Ngoài lỗi đơn lẻ, hãy kiểm tra chuỗi tình huống: backend dừng một khoảng thời gian, ứng dụng tiếp tục tạo metrics, backend hoạt động lại và exporter tiếp tục gửi. Ghi nhận liệu dữ liệu trong thời gian gián đoạn được giữ, mất, gửi bù hay gửi lặp. Đây là hành vi quan trọng nhất để biết registry có đáp ứng kỳ vọng vận hành hay không.

## 14. Quy trình chọn cấu hình an toàn

Khi triển khai một registry mới, thực hiện lần lượt:

1. Xác định pull hay push và thành phần nào khởi tạo request.
2. Xác định step, batch-size, payload limit và queue có tồn tại hay không.
3. Xác định connect/read/request timeout và giá trị mặc định theo phiên bản.
4. Xác định lỗi nào được retry, retry bao nhiêu lần và có backoff không.
5. Xác định dữ liệu được giữ, drop hay replay khi export thất bại.
6. Đo payload thực tế với histogram và cardinality production-like.
7. Kiểm thử timeout, 4xx, 429, 5xx, mất kết nối và backend phục hồi.
8. Theo dõi export latency, failure, queue và dropped data sau triển khai.

Không sao chép nguyên cấu hình timeout hoặc batch size từ registry này sang registry khác. Cùng một giá trị có thể có semantics khác nhau, và backend khác nhau có giới hạn payload cũng như chính sách retry khác nhau.

## 15. Checklist vận hành

Trước khi đưa metrics export vào production, xác nhận:

- Đã biết registry và phiên bản chính xác.
- Đã phân biệt step với batch-size.
- Đã biết giới hạn payload và nơi áp dụng giới hạn đó.
- Đã xác định connect timeout, read timeout và request timeout nếu có.
- Đã kiểm tra retry, backoff, queue và hành vi khi queue đầy.
- Đã hiểu dữ liệu step bị mất, giữ hay replay khi export thất bại.
- Đã kiểm tra khả năng gửi trùng sau timeout.
- Đã cấu hình Prometheus scrape timeout phù hợp với endpoint nếu dùng pull.
- Đã đánh giá tác động histogram và cardinality đến kích thước payload.
- Có kiểm thử lỗi và phục hồi bằng registry/exporter thực tế.
- Có giám sát exporter, Collector và backend nhận dữ liệu.

Giới hạn lô, timeout và hành vi lỗi là thuộc tính của đường export cụ thể. Micrometer cung cấp mô hình meter thống nhất, còn registry và transport quyết định cách gom, gửi, retry và xử lý thất bại. Khi xác định đúng từng giới hạn, kiểm thử tình huống lỗi và theo dõi chính đường export, ứng dụng có thể gửi metrics ổn định mà vẫn kiểm soát được độ trễ, bộ nhớ và nguy cơ mất hoặc lặp dữ liệu.
