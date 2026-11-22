# Đo lường và telemetry

## Vai trò của telemetry trong Language Server

Language Server là dịch vụ cung cấp khả năng hiểu ngôn ngữ cho trình soạn thảo thông qua Language Server Protocol (LSP) hoặc một giao thức tương tự. Nó có thể phân tích cú pháp, phân giải tên, cung cấp diagnostics, hoàn thành mã, điều hướng đến khai báo, hiển thị thông tin kiểu, hỗ trợ refactoring và cập nhật kết quả khi tài liệu thay đổi.

Các tính năng này được gọi từ nhiều editor và chạy trên những workspace có kích thước, cấu hình và môi trường khác nhau. Một language server có thể hoạt động tốt trên file nhỏ nhưng chậm khi workspace lớn; có thể trả diagnostics chính xác nhưng tiêu thụ nhiều bộ nhớ; hoặc chỉ gặp lỗi khi người dùng hủy request trong lúc parser đang chạy.

**Đo lường và telemetry** giúp nhóm phát triển quan sát hoạt động của language server trong quá trình sử dụng. Mục tiêu là hiểu hệ thống đang làm gì, phản hồi nhanh đến đâu, tài nguyên được sử dụng ra sao, lỗi xuất hiện ở giai đoạn nào và thay đổi trong một phiên bản có cải thiện trải nghiệm hay không.

Telemetry trong language server thường gồm:

- **Metrics:** số liệu tổng hợp như thời gian xử lý request, số diagnostics, tỷ lệ lỗi và mức sử dụng bộ nhớ.
- **Logs:** bản ghi có cấu trúc về sự kiện, lỗi và trạng thái quan trọng.
- **Traces:** dấu vết cho thấy một request đi qua những thành phần nào và mất bao lâu ở mỗi bước.
- **Events:** sự kiện có ý nghĩa vận hành, chẳng hạn workspace đã được index hoặc cache bị invalidation.
- **Profiling:** dữ liệu chi tiết về CPU, allocation, garbage collection, lock contention hoặc call stack khi cần điều tra sâu.

Những dữ liệu này giúp trả lời các câu hỏi thực tế:

- Vì sao completion mất hơn một giây trong workspace lớn?
- Request nào thường bị hủy trước khi hoàn tất?
- Parser hay semantic analysis đang chiếm phần lớn thời gian?
- Một thay đổi grammar có làm tăng số lỗi nội bộ không?
- Cache có thực sự giảm thời gian phản hồi?
- Language server có tăng bộ nhớ theo thời gian mà không giải phóng không?
- Một phiên bản mới có làm tăng tỷ lệ timeout hoặc crash?
- Editor nào, phiên bản giao thức nào hoặc loại project nào gặp vấn đề?

Telemetry không phải là nội dung DSL mà người dùng viết. Nó là dữ liệu về hoạt động của dịch vụ và trải nghiệm tương tác với dịch vụ. Cần thiết kế telemetry để cung cấp thông tin đủ hữu ích nhưng không thu thập source code, tên dự án, đường dẫn riêng tư hoặc dữ liệu nghiệp vụ khi không cần thiết.

## Vì sao language server cần observability?

Language server thường chạy nền và được editor khởi động tự động. Người dùng có thể chỉ nhận thấy editor chậm, gợi ý biến mất hoặc diagnostics cập nhật trễ mà không biết nguyên nhân nằm ở client, giao thức, parser, indexer hay một dịch vụ bên ngoài.

Nếu chỉ có thông báo lỗi cuối cùng, nhóm phát triển khó xác định phần nào gây ra vấn đề. Observability cho phép kết hợp metrics, logs và traces để hiểu hành vi hệ thống từ nhiều góc nhìn.

### Theo dõi độ trễ và độ phản hồi

Các tính năng như completion, hover và signature help thường được gọi khi người dùng đang gõ. Độ trễ của chúng ảnh hưởng trực tiếp đến cảm giác sử dụng.

Một request completion mất 40 ms có thể không đáng chú ý. Nếu thường xuyên mất 700 ms, editor có thể hiển thị kết quả muộn hoặc khiến người dùng phải chờ. Trung bình đơn thuần có thể che giấu vấn đề vì phần lớn request nhanh trong khi một nhóm nhỏ cực kỳ chậm. Do đó, cần xem phân phối thời gian và percentile như p50, p95, p99.

### Phát hiện lỗi trước khi người dùng báo cáo

Metrics có thể cho thấy tỷ lệ request lỗi tăng sau một bản phát hành. Logs giúp xác định exception hoặc trạng thái bất thường. Traces cho biết request lỗi ở bước nào.

Khi có telemetry, nhóm có thể phát hiện regression ở parser hoặc resolver trước khi nó trở thành nhiều ticket hỗ trợ.

### Hiểu hành vi của workspace

Chi phí xử lý phụ thuộc vào số file, số token, số symbol, dependency graph, số module được import và trạng thái cache. Telemetry tổng hợp giúp phân biệt vấn đề ở project lớn với vấn đề xảy ra trên mọi project.

Không cần thu thập nội dung từng file để hiểu những đặc điểm vận hành này. Có thể ghi số lượng file, kích thước theo bucket, số node hoặc thời gian index theo nhóm kích thước.

### Quản lý tài nguyên

Language server có thể chạy nhiều giờ trong một phiên editor. Memory leak, cache tăng không giới hạn, task bị giữ lại hoặc thread pool quá tải có thể chỉ xuất hiện sau thời gian dài.

Theo dõi heap, resident memory, số task đang chạy, hàng đợi, cache size và số worker giúp nhận diện xu hướng bất thường.

### Đánh giá chất lượng phát hành

Khi thay đổi parser, incremental analysis, completion engine hoặc protocol layer, nhóm cần biết thay đổi đó có cải thiện trải nghiệm thật hay không. Metrics trước và sau phát hành hỗ trợ đánh giá thay vì chỉ dựa vào benchmark nhỏ.

## Metrics, logs, traces, events và profiling

Các loại dữ liệu observability bổ sung cho nhau. Không nên cố nhét mọi thông tin vào một loại.

| Loại dữ liệu | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Metrics | Điều gì đang xảy ra ở quy mô tổng thể? | p95 completion latency, request error rate |
| Logs | Sự kiện hoặc lỗi cụ thể đã xảy ra là gì? | Parser thất bại tại một stage |
| Traces | Một request đi qua những bước nào? | completion, document lookup, analysis, filtering |
| Events | Một thay đổi trạng thái quan trọng đã xảy ra? | Workspace indexing completed |
| Profiling | CPU hoặc bộ nhớ được dùng cụ thể ở đâu? | Hot method, allocation hotspot |

### Metrics

Metrics là số liệu được tổng hợp theo thời gian. Chúng phù hợp với dashboard, alert và phân tích xu hướng.

~~~text
language_server_requests_total{
  method="textDocument/completion",
  outcome="success"
}

language_server_request_duration_seconds{
  method="textDocument/completion"
}

language_server_active_documents
language_server_workspace_index_duration_seconds
language_server_memory_bytes
~~~

Một metric thường có tên, kiểu, giá trị, thời điểm và một số label có giới hạn.

### Logs

Logs ghi sự kiện có ngữ cảnh. Một log có cấu trúc có thể chứa timestamp, severity, component, method, error code và request correlation ID.

~~~json
{
  "timestamp": "2026-11-15T03:40:00Z",
  "level": "WARN",
  "component": "semantic-analysis",
  "event": "analysis-deferred",
  "reason": "document-version-changed",
  "requestId": "req-82"
}
~~~

Log nên mô tả sự kiện vận hành, không ghi toàn bộ source text hoặc nội dung nhạy cảm theo mặc định.

### Traces

Trace biểu diễn một hoạt động qua nhiều thành phần. Một request completion có thể tạo span cho protocol dispatch, document snapshot lookup, parse, name resolution, completion provider và response serialization.

~~~text
textDocument/completion
  |
  +-- validate request
  |
  +-- obtain document snapshot
  |
  +-- resolve cursor context
  |
  +-- semantic analysis
  |
  +-- collect completion candidates
  |
  +-- rank and filter
  |
  +-- serialize response
~~~

Trace cho biết thời gian của từng bước và mối quan hệ giữa các hoạt động. Nó đặc biệt hữu ích khi tổng latency cao nhưng chưa rõ stage nào là nguyên nhân.

### Events

Event ghi nhận một sự kiện có ý nghĩa, ví dụ:

- Workspace initialization completed.
- Background index refresh completed.
- Cache invalidated.
- Configuration reloaded.
- Language server entered degraded mode.
- A project module failed to load.

Event không nên thay thế metric. Nếu cần biết số lần cache invalidation theo giờ, hãy tạo counter; nếu cần điều tra một lần invalidation cụ thể, hãy ghi event có ngữ cảnh phù hợp.

### Profiling

Profiling thu thập dữ liệu sâu hơn về CPU, memory allocation, garbage collection, lock contention hoặc call stack. Đây thường là công cụ điều tra khi metrics và traces đã chỉ ra vùng nghi vấn.

Không nên bật profiling nặng liên tục trên mọi phiên làm việc nếu chi phí ảnh hưởng đến trải nghiệm hoặc tạo dữ liệu quá lớn. Có thể dùng sampling hoặc bật theo yêu cầu trong môi trường debug.

## Kiến trúc telemetry cho language server

Telemetry thường đi qua nhiều lớp: client, protocol transport, language server, instrumentation library và telemetry backend.

~~~text
Editor / LSP Client
        |
        | LSP requests and notifications
        v
Language Server Protocol Layer
        |
        v
Request Dispatcher
        |
        +-------------------------------+
        |                               |
        v                               v
Language Services                 Telemetry Instrumentation
  - Parser                            - Metrics
  - Indexer                           - Logs
  - Resolver                          - Traces
  - Completion                        - Events
  - Diagnostics                       |
        |                              v
        +----------------------> Telemetry SDK / Collector
                                       |
                                       v
                                Observability Backend
                                  - Dashboards
                                  - Alerts
                                  - Trace search
                                  - Log search
~~~

Instrumentation nên nằm ở ranh giới phù hợp để đo được cả tổng thời gian request lẫn thời gian từng stage. Nếu chỉ đo bên trong parser, nhóm sẽ không biết thời gian chờ hàng đợi hoặc serialize response. Nếu chỉ đo toàn request, sẽ không biết parser hay resolver là bottleneck.

### Client-side và server-side telemetry

Client có thể đo thời gian từ lúc người dùng thực hiện thao tác đến khi giao diện nhận và hiển thị kết quả. Server đo thời gian xử lý request và các stage nội bộ.

Hai số liệu có thể khác nhau:

- Client latency bao gồm thời gian gửi request, transport, chờ server, nhận response và xử lý ở UI.
- Server duration chỉ bao gồm khoảng thời gian server ghi nhận request đang xử lý.
- End-to-end interaction latency có thể bao gồm debounce trước khi gửi request và thời gian render kết quả.

Cần ghi rõ định nghĩa mỗi metric. Nếu so sánh client và server mà không thống nhất điểm bắt đầu/kết thúc, nhóm có thể kết luận sai về bottleneck.

### Telemetry nội bộ và telemetry gửi đi

Language server có thể ghi metrics/logs cục bộ để phục vụ debug. Việc gửi telemetry ra ngoài là một quyết định riêng, liên quan đến consent, privacy, retention và chính sách sản phẩm.

Có thể hỗ trợ nhiều chế độ:

- Disabled: không gửi telemetry từ người dùng.
- Local diagnostics: chỉ lưu dữ liệu cục bộ theo cấu hình.
- Anonymous operational telemetry: gửi số liệu tổng hợp đã loại bỏ nội dung và định danh trực tiếp.
- Debug mode: thu thập chi tiết hơn theo lựa chọn rõ ràng và thời hạn giới hạn.

Không nên coi việc bật logging để debug là đồng nghĩa với cho phép gửi dữ liệu ra dịch vụ bên ngoài.

## Đo lường vòng đời request và notification

LSP có request và notification. Request có response tương ứng; notification không yêu cầu response. Hai loại cần được đo theo cách phù hợp.

### Request lifecycle

Một request thường đi qua các trạng thái:

~~~text
Received
   |
   v
Validated
   |
   v
Queued
   |
   v
Running
   |
   +----> Completed
   |
   +----> Failed
   |
   +----> Cancelled
   |
   +----> Timed out
~~~

Metrics cơ bản:

- Số request nhận được.
- Số request hoàn tất.
- Số request thất bại.
- Số request bị hủy.
- Số request timeout.
- Thời gian chờ hàng đợi.
- Thời gian thực thi.
- Tổng thời gian từ nhận đến response.
- Số request đang chạy và đang chờ.

Cancellation không nên mặc định được tính là lỗi. Người dùng thường tiếp tục gõ khiến completion request cũ không còn cần thiết. Hủy đúng cách là một phần của hành vi bình thường.

### Notification lifecycle

Notification như didOpen, didChange, didClose hoặc workspace configuration update có thể kích hoạt công việc nền. Vì không có response trực tiếp, cần đo:

- Số notification theo method.
- Thời gian dispatch.
- Số task nền được tạo.
- Số task bị thay thế hoặc hủy.
- Thời gian xử lý cập nhật document.
- Độ trễ đến khi diagnostics mới được publish.

Ví dụ, didChange có thể được xử lý nhanh để cập nhật text snapshot, trong khi parse và indexing tiếp tục ở background. Cần phân biệt thời gian xử lý notification với thời gian hoàn tất công việc phát sinh từ notification.

### Method và outcome

Có thể phân loại theo LSP method và outcome:

| Nhóm | Ví dụ method |
|---|---|
| Lifecycle | initialize, initialized, shutdown, exit |
| Document sync | didOpen, didChange, didClose |
| Completion | textDocument/completion |
| Navigation | definition, references, implementation |
| Information | hover, signatureHelp, documentSymbol |
| Diagnostics | publishDiagnostics, documentDiagnostic |
| Editing | codeAction, rename, formatting |
| Workspace | workspace/symbol, executeCommand |

Method name nên là label có tập giá trị hữu hạn. Không đưa request ID, URI, symbol name hoặc chuỗi tùy ý từ client vào metric label vì làm cardinality tăng không kiểm soát.

## Bộ metrics cốt lõi

Một language server không cần hàng trăm metrics ngay từ đầu. Nên bắt đầu với bộ số liệu phản ánh latency, throughput, reliability và resource usage.

### Request count và throughput

Counter đếm tổng số request theo method và outcome:

~~~text
language_server_requests_total
~~~

Từ counter có thể tính request rate trong một khoảng thời gian. Cần phân biệt request nhận được với request hoàn tất; nếu chỉ đếm response thành công, các request đang chờ hoặc bị hủy sẽ không được thể hiện đầy đủ.

### Request duration

Histogram đo thời gian request:

~~~text
language_server_request_duration_seconds
~~~

Có thể phân tích p50, p90, p95 và p99. Với các thao tác tương tác, percentile cao thường quan trọng hơn average vì một số request chậm có thể khiến editor bị giật.

Nên có metric riêng cho queue wait và execution duration nếu hệ thống dùng scheduler hoặc worker pool:

~~~text
language_server_queue_wait_seconds
language_server_execution_duration_seconds
~~~

### Error rate

Counter lỗi nên phân loại theo nhóm ổn định:

- Internal exception.
- Invalid request.
- Unsupported method.
- Dependency unavailable.
- Resource limit exceeded.
- Serialization failure.
- Background task failure.

Không nên đưa error message tùy ý làm label. Error code hoặc error category ổn định giúp nhóm tổng hợp và alert.

### Cancellation và timeout

~~~text
language_server_requests_cancelled_total
language_server_requests_timed_out_total
~~~

Cancellation rate cao có thể phản ánh người dùng gõ nhanh, debounce chưa phù hợp, server xử lý quá chậm hoặc client gửi nhiều request trùng. Cần kết hợp với method và duration để hiểu nguyên nhân.

### Concurrency và queue

~~~text
language_server_requests_in_flight
language_server_worker_queue_depth
language_server_background_tasks
~~~

Queue depth tăng liên tục trong khi throughput không tăng có thể là dấu hiệu worker pool bão hòa. Số request đang chạy cần được đo bằng gauge, không phải counter.

### Workspace và document

Các metrics hữu ích:

~~~text
language_server_workspace_files
language_server_workspace_symbols
language_server_open_documents
language_server_document_bytes
language_server_index_duration_seconds
language_server_parse_duration_seconds
~~~

Kích thước document nên có thể được bucket hoặc histogram. Tránh dùng path làm label. Nếu cần phân nhóm, dùng các bucket kích thước như small, medium, large thay vì URI cụ thể.

### Diagnostics

~~~text
language_server_diagnostics_published_total
language_server_diagnostics_per_document
language_server_diagnostic_compute_duration_seconds
language_server_diagnostic_publish_delay_seconds
~~~

Số diagnostics tăng có thể do source thay đổi, schema thay đổi hoặc bug tạo lỗi lặp. Metric cần được hiểu trong ngữ cảnh, không coi nhiều diagnostics luôn là chất lượng thấp.

### Cache

~~~text
language_server_cache_hits_total
language_server_cache_misses_total
language_server_cache_evictions_total
language_server_cache_entries
language_server_cache_memory_bytes
~~~

Hit ratio giúp đánh giá cache có hiệu quả không. Tuy nhiên, hit ratio cao không đảm bảo latency thấp nếu cache lookup tốn thời gian hoặc dữ liệu cache quá lớn.

### Resource usage

Tùy runtime, có thể đo:

- Heap used và committed.
- Resident memory.
- CPU utilization hoặc CPU time.
- Garbage collection count và pause duration.
- Thread/worker count.
- File descriptor hoặc handle count.
- Network request và bytes nếu có dependency bên ngoài.
- Disk cache size.

Không phải runtime nào cũng cung cấp mọi metric. Cần chọn số liệu có định nghĩa rõ và tránh suy diễn từ một chỉ số không tương đương.

## Đo latency theo từng tính năng language server

Một request completion và một request workspace symbol có workload khác nhau. Không nên gộp mọi request thành một metric duy nhất rồi kết luận server nhanh hay chậm.

### Completion

Completion thường được gọi nhiều lần khi người dùng gõ. Các giai đoạn có thể đo:

1. Nhận request và kiểm tra position.
2. Lấy document snapshot đúng version.
3. Xác định cú pháp tại cursor.
4. Lấy scope và symbol index.
5. Tạo candidate.
6. Tính relevance hoặc ranking.
7. Lọc theo context và client capability.
8. Serialize CompletionList.

Metrics riêng có thể gồm candidate count, thời gian semantic lookup, thời gian ranking, cache hit và số request bị hủy.

Một completion request nhanh nhưng trả hàng nghìn candidate cũng có thể gây chậm ở client. Nếu cần đo response size, nên ghi số lượng item hoặc byte size theo bucket, không ghi label có giá trị tùy ý.

### Hover và signature help

Hover thường cần resolve symbol và lấy documentation. Signature help cần xác định function call, argument index và overload phù hợp.

Có thể đo:

- Thời gian resolve symbol.
- Số overload được xét.
- Thời gian lấy documentation.
- Số lần không tìm thấy symbol.
- Số response rỗng.
- Response serialization time.

Không nên ghi nội dung documentation hoặc biểu thức người dùng đang hover vào telemetry mặc định.

### Go to definition và references

Definition thường cần tra symbol index và map đến source location. References có thể cần duyệt index hoặc nhiều module.

Metrics có thể gồm:

- Số symbol lookup.
- Số file được tìm.
- Số reference trả về.
- Index lookup duration.
- Fallback full-scan count.
- Số kết quả bị giới hạn theo policy.

Nếu references chậm, trace có thể cho thấy index chưa sẵn sàng, query không được cache hoặc fallback scan đang chạy.

### Diagnostics

Diagnostics thường được tính sau document change, save hoặc workspace update. Đo thời gian parse, semantic analysis, validation, diagnostic aggregation và publish.

Cần đo cả publish delay: khoảng thời gian từ khi document version mới được nhận đến khi diagnostics tương ứng được gửi. Đây thường là chỉ số gần với trải nghiệm người dùng hơn thời gian của riêng validator.

### Rename và code action

Rename và code action có thể cần kiểm tra nhiều reference, xây workspace edit và xác nhận không có xung đột.

Metrics hữu ích:

- Số file bị ảnh hưởng.
- Số edit được tạo.
- Thời gian tìm references.
- Thời gian xây WorkspaceEdit.
- Số request bị từ chối vì ambiguity hoặc validation.
- Số lỗi khi client áp dụng edit nếu có phản hồi quan sát được.

Không nên gửi tên symbol hoặc nội dung edit ra telemetry. Có thể ghi số lượng và loại thao tác.

## Tracing request qua các thành phần nội bộ

Trace giúp xác định stage nào chiếm thời gian và request nào gây ra công việc nền.

Một trace cho completion có thể có cấu trúc:

~~~text
Span: lsp.request completion
  Span: request validation
  Span: document snapshot lookup
  Span: syntax context lookup
  Span: semantic resolution
    Span: symbol index query
  Span: candidate generation
  Span: ranking
  Span: response serialization
~~~

Mỗi span có start time, duration, status và một số attribute có giới hạn.

### Correlation ID

Request ID của giao thức có thể giúp ghép request với response trong một connection. Tuy nhiên, request ID không nên dùng làm metric label. Trong logs và traces, có thể dùng correlation ID hoặc trace ID để liên kết các sự kiện của cùng một request.

Với công việc nền phát sinh từ didChange, có thể gắn document version và một operation ID nội bộ. Nếu một request bị thay thế bởi request mới, trace cần cho thấy quan hệ parent/child hoặc nguyên nhân cancellation.

### Context propagation

Khi request gọi parser, resolver và completion provider, trace context cần được truyền qua các thành phần. Nếu mỗi thành phần tự tạo trace độc lập, rất khó nối chúng lại.

Có thể dùng OpenTelemetry hoặc một abstraction nội bộ để tạo span và propagate context. Instrumentation nên tránh tạo span cho từng node AST nếu chi phí quá lớn; có thể tạo span theo stage hoặc sampling.

### Tracing công việc bất đồng bộ

Language server thường dùng background worker. Request có thể kết thúc trước khi task indexing hoàn tất hoặc một task có thể phục vụ nhiều request.

Cần mô hình hóa quan hệ:

- Request khởi tạo task.
- Task được queue.
- Task bị hủy hoặc superseded.
- Task cập nhật index.
- Request khác sử dụng kết quả index.

Không phải task nền nào cũng là child span đồng bộ của request ban đầu. Có thể dùng link giữa trace hoặc operation context riêng để biểu diễn mối liên hệ mà không kéo dài sai thời gian request.

## Logs có cấu trúc cho language server

Logs hữu ích khi cần điều tra một sự kiện cụ thể hoặc một lỗi hiếm. Log nên có schema ổn định để có thể lọc và phân tích tự động.

Một log record có thể chứa:

~~~json
{
  "timestamp": "2026-11-15T03:40:00Z",
  "severity": "INFO",
  "service": "dsl-language-server",
  "component": "workspace-indexer",
  "event": "index-refresh-completed",
  "durationMs": 184,
  "fileCountBucket": "100-500",
  "result": "success",
  "traceId": "trace-abc"
}
~~~

### Severity

Có thể dùng các mức:

- TRACE: thông tin cực kỳ chi tiết, thường chỉ bật trong debug.
- DEBUG: chi tiết phục vụ phát triển và điều tra.
- INFO: trạng thái bình thường có ý nghĩa vận hành.
- WARN: tình trạng bất thường nhưng dịch vụ vẫn tiếp tục.
- ERROR: thao tác thất bại hoặc một chức năng không thể hoàn thành.
- FATAL: lỗi khiến tiến trình không thể tiếp tục.

Tên mức cụ thể phụ thuộc logging framework. Điều quan trọng là dùng nhất quán. Không nên ghi mọi request completion thành INFO nếu tần suất rất cao; điều đó có thể tạo lượng log lớn mà ít giá trị.

### Log event thay vì log câu văn tùy ý

Log có cấu trúc nên có event name và field ổn định. Ví dụ event analysis-deferred với reason document-version-changed dễ tổng hợp hơn câu văn tự do thay đổi theo từng phiên bản.

Message vẫn có thể được tạo cho người đọc, nhưng dữ liệu phân tích nên dựa trên field có kiểu.

### Tránh log quá nhiều

Một language server có thể nhận hàng chục request mỗi giây. Ghi một log cho từng bước nhỏ sẽ làm tăng I/O, kích thước log và chi phí xử lý.

Có thể:

- Dùng DEBUG cho sự kiện chi tiết.
- Ghi một summary cho request chậm.
- Sampling log thành công.
- Luôn giữ error và một số warning quan trọng.
- Giới hạn kích thước field.
- Dùng rate limit cho lỗi lặp.
- Gộp sự kiện nền tương tự trong một khoảng thời gian.

### Không dùng log làm database

Logs có thể bị rotate, sampling hoặc expire. Nếu cần số liệu tổng hợp chính xác, hãy dùng metrics. Nếu cần trạng thái hiện tại như số worker đang chạy, hãy dùng gauge hoặc endpoint trạng thái được kiểm soát.

## Đo lường hoạt động parser, indexer và semantic engine

Language server phụ thuộc vào các thành phần xử lý ngôn ngữ. Đo ở cấp request là chưa đủ nếu muốn biết nguyên nhân bên trong.

### Parser

Metrics có thể gồm:

- Parse duration.
- Số token.
- Số AST node.
- Parse error count.
- Partial parse count.
- Incremental parse reuse ratio.
- Full reparse count.
- Parse depth hoặc nesting bucket.
- Parser recovery count.

Nếu số lần full reparse tăng sau một thay đổi, incremental parser có thể không nhận được edit range đúng hoặc grammar mới làm invalidation quá rộng.

Không nên ghi token text hoặc AST content vào telemetry. Các số đếm tổng hợp thường đủ để nhận biết workload và hiệu năng.

### Workspace indexer

Indexer có thể đo:

- File discovery duration.
- Files scanned.
- Files skipped.
- Parse jobs queued/completed.
- Symbol count.
- Index build duration.
- Index update duration.
- Failed file count.
- Index memory size.
- Dependency graph size.

Cần phân biệt cold indexing lần đầu với incremental update sau khi thay đổi một file. Hai workload có chi phí khác nhau và cần được quan sát riêng.

### Name resolver và type checker

Các metrics hữu ích:

- Symbol lookup duration.
- Unresolved reference count.
- Type check duration.
- Number of constraints evaluated.
- Dependency traversal count.
- Resolution cache hit/miss.
- Ambiguous reference count.

Một resolver chậm có thể do scope chain sâu, import graph lớn, cache miss hoặc query index không hiệu quả. Trace stage và counter giúp phân biệt các trường hợp.

### Diagnostics engine

Đo thời gian theo nhóm validator hoặc diagnostic category, số diagnostics tạo ra, số diagnostics bị loại do document version cũ và số lần publish. Cần tránh đưa message hoặc source range cụ thể vào metric label.

## Telemetry cho document synchronization và incremental analysis

Một language server thường nhận document change liên tục. Mỗi edit có thể làm thay đổi parse tree, symbol table, diagnostics và completion context.

### Độ trễ từ edit đến kết quả

Một metric có giá trị là thời gian từ khi nhận document version mới đến khi kết quả phân tích tương ứng được publish.

~~~text
didChange received
       |
       v
Text snapshot updated
       |
       v
Incremental parse
       |
       v
Semantic analysis
       |
       v
Diagnostics published
~~~

Nếu chỉ đo thời gian parse, nhóm có thể bỏ qua thời gian queue, semantic analysis hoặc chờ worker.

### Superseded work

Người dùng gõ liên tục có thể tạo nhiều version. Một task cho version cũ có thể bị hủy vì version mới đã đến.

Đo:

- Số task được supersede.
- Số task bị hủy.
- Thời gian đã tiêu tốn trước khi bị hủy.
- Số task hoàn tất nhưng kết quả đã stale.
- Số lần full recompute do edit pattern.

Cancellation là bình thường, nhưng nếu nhiều công việc bị hủy sau khi đã tiêu tốn phần lớn CPU, debounce, scheduling hoặc incremental algorithm có thể cần cải thiện.

### Document version correctness

Kết quả diagnostics hoặc completion phải gắn với đúng document snapshot. Telemetry có thể ghi số lần kết quả stale bị loại bỏ và số lần version mismatch xảy ra.

Không ghi URI hoặc source content vào metric. Có thể dùng document type hoặc size bucket nếu được định nghĩa và không tạo định danh ngược.

## Đo resource usage và sức khỏe tiến trình

Language server thường chạy cùng editor trên máy người dùng. Một memory leak hoặc CPU spike có thể ảnh hưởng toàn bộ trải nghiệm desktop.

### Memory

Các chỉ số có thể gồm:

- Heap used.
- Heap committed.
- Resident set size.
- Allocation rate.
- Garbage collection count.
- GC pause duration.
- Cache memory.
- Số object hoặc node được giữ nếu runtime cung cấp.

Một snapshot đơn lẻ không đủ để kết luận leak. Cần theo dõi xu hướng qua thời gian hoặc qua chu kỳ mở/đóng workspace và document.

### CPU và scheduling

Theo dõi CPU time, worker utilization, queue depth, task duration và số thread. Nếu worker pool luôn đầy và queue tăng, server có thể đang quá tải.

### File và network resources

Nếu language server truy cập filesystem hoặc service ngoài, có thể đo:

- File read/write count.
- File watch event rate.
- File descriptor usage.
- Network request duration.
- Retry count.
- Dependency failure count.

Không nên ghi đường dẫn hoặc endpoint có chứa thông tin riêng tư vào telemetry mặc định. Có thể ghi loại resource và outcome.

### Health state

Một health state có thể phân biệt:

- Starting.
- Initializing.
- Ready.
- Indexing.
- Degraded.
- Shutting down.
- Failed.

Health state hữu ích cho log và status command. Không nên gửi notification liên tục mỗi khi state chuyển đổi nhỏ; có thể ghi event khi vào trạng thái degraded hoặc khi recovery hoàn tất.

## Thiết kế metric: counter, gauge, histogram và summary

Chọn đúng kiểu metric rất quan trọng để số liệu có ý nghĩa.

### Counter

Counter chỉ tăng hoặc reset khi tiến trình khởi động lại. Dùng cho tổng request, lỗi, cancellation, cache hit và event count.

Ví dụ:

~~~text
requests_total{method="hover", outcome="success"} 12450
~~~

Tốc độ tăng của counter có thể được tính trong một khoảng thời gian. Không nên dùng counter cho giá trị hiện tại như số request đang chạy.

### Gauge

Gauge có thể tăng hoặc giảm. Dùng cho open documents, active workers, queue depth, memory hiện tại hoặc cache entries.

~~~text
active_documents 8
worker_queue_depth 3
~~~

### Histogram

Histogram chia giá trị quan sát thành các bucket, thường dùng cho latency, payload size hoặc số candidate. Nó hỗ trợ tính percentile và phân phối.

~~~text
request_duration_seconds_bucket{
  method="completion",
  le="0.1"
} 820
~~~

Bucket cần được chọn theo ngưỡng phù hợp với use case. Nếu completion mục tiêu dưới 100 ms, bucket chỉ có 1, 5 và 30 giây sẽ không đủ chi tiết.

### Summary

Một số hệ thống hỗ trợ summary tính quantile tại client hoặc process. Summary có trade-off về khả năng tổng hợp giữa nhiều instance. Nếu cần tổng hợp percentile qua nhiều language server, histogram thường phù hợp hơn trong hệ thống metrics tập trung.

### Đơn vị và tên metric

Tên metric nên dùng đơn vị rõ, thường là seconds cho thời gian và bytes cho dung lượng. Không nên dùng một metric duration mà không nói rõ đơn vị hoặc một field size có thể là byte, token hay node count.

## Cardinality và thiết kế labels

Metric label cho phép phân nhóm, nhưng mỗi tổ hợp label tạo một time series. Nếu label có vô số giá trị khác nhau, cardinality có thể tăng rất lớn.

Các giá trị nên tránh làm label:

- File URI hoặc absolute path.
- Project name.
- User ID hoặc machine ID.
- Request ID hoặc trace ID.
- Symbol name.
- Nội dung error message.
- Arbitrary configuration value.
- Tên module do người dùng tự đặt.

Các label có tập giá trị hữu hạn thường an toàn hơn:

- LSP method từ danh sách được hỗ trợ.
- Outcome: success, error, cancelled, timeout.
- Component: parser, resolver, indexer.
- Severity: error, warning, info.
- Document size bucket.
- Runtime version hoặc server release.
- Transport type nếu tập giá trị được kiểm soát.

Nếu cần điều tra một file cụ thể, hãy dùng local log hoặc trace có policy riêng thay vì tạo metric series cho từng URI.

## Tích hợp OpenTelemetry và hệ thống thu thập

OpenTelemetry cung cấp API và SDK để instrument traces, metrics và logs theo một mô hình chung. Language server có thể dùng OpenTelemetry SDK hoặc abstraction tương đương rồi export dữ liệu đến collector.

Một kiến trúc ví dụ:

~~~text
Language Server
   |
   v
Instrumentation API
   |
   v
OpenTelemetry SDK
   |
   v
OTLP Exporter
   |
   v
Collector
   |
   +--> Metrics backend
   +--> Trace backend
   +--> Log backend
~~~

Collector có thể xử lý batching, filtering, sampling, attribute processing và routing trước khi gửi đến backend.

### Resource attributes

Resource attributes mô tả service tạo telemetry, ví dụ:

- service.name.
- service.version.
- deployment.environment.
- telemetry.sdk.name.
- runtime.name.
- operating system family.

Không nên đưa user name, home directory, workspace path hoặc machine identifier vào resource attributes nếu không có lý do và consent phù hợp.

### Span attributes

Span attributes nên tập trung vào thông tin có ích như LSP method, component, outcome, document size bucket, cache result và server version.

Tránh ghi source text, completion candidate, symbol name hoặc URI. Nếu một thuộc tính có thể chứa dữ liệu người dùng, hãy xem xét kỹ trước khi export.

### Export không chặn request

Exporter không nên làm request completion phải chờ network telemetry. Dùng batch hoặc asynchronous export với bounded queue và timeout.

Nếu telemetry backend không khả dụng, language server vẫn cần phục vụ editor. Có thể drop telemetry khi queue đầy, ghi một local counter về dropped telemetry và tiếp tục xử lý request.

### Flush khi shutdown

Khi server shutdown, có thể flush dữ liệu đang chờ trong một giới hạn thời gian. Không nên trì hoãn shutdown vô thời hạn chỉ để gửi telemetry. Cần xử lý cancellation và lỗi exporter rõ ràng.

## Tích hợp với LSP và editor client

LSP định nghĩa giao thức giữa client và server, nhưng không quy định một hệ thống observability đầy đủ cho mọi triển khai. Server có thể dùng các notification log hoặc telemetry mà client hỗ trợ, đồng thời dùng exporter riêng cho metrics và traces.

### Logging qua client

Một language server có thể gửi log message đến client nếu client hỗ trợ. Điều này hữu ích cho thông báo vận hành hoặc debug mà người dùng cần xem trong editor.

Không nên gửi từng request thành log message hiển thị cho người dùng. Log client-facing cần có mức phù hợp, tần suất giới hạn và nội dung không nhạy cảm.

### Telemetry event

Một số client hỗ trợ nhận telemetry event từ server. Khả năng hỗ trợ và cách lưu dữ liệu phụ thuộc client. Server cần kiểm tra capability hoặc tài liệu tích hợp, không giả định mọi editor đều nhận và lưu cùng cách.

### Client telemetry và server telemetry

Client biết thao tác UI bắt đầu khi nào và kết quả được render khi nào. Server biết nội bộ request mất bao lâu. Nếu sản phẩm cần end-to-end latency, hai phía có thể trao đổi correlation context theo một cơ chế an toàn và được đặc tả.

Không nên phụ thuộc vào telemetry client để vận hành đúng language server. Telemetry là dữ liệu quan sát, không phải kênh điều khiển thiết yếu.

## Privacy và bảo vệ dữ liệu

Language server có thể xử lý source code riêng tư, tên project, đường dẫn người dùng, schema nội bộ và dữ liệu nghiệp vụ. Telemetry cần áp dụng nguyên tắc tối thiểu hóa dữ liệu.

### Không thu thập source code theo mặc định

Các dữ liệu sau thường nhạy cảm:

- Nội dung DSL.
- Identifier hoặc tên symbol.
- Comment và documentation.
- Absolute file path.
- Workspace URI.
- Literal chứa token, secret hoặc dữ liệu khách hàng.
- Completion text và diagnostic message có trích source.
- Environment variable hoặc command line đầy đủ.

Để đo hiệu năng, thường chỉ cần method, duration, outcome, size bucket và component.

### Data minimization

Mỗi field telemetry cần có mục đích rõ. Nếu một field không hỗ trợ metric, debug hoặc quyết định sản phẩm cụ thể, không nên thu thập.

### Consent và cấu hình

Người dùng hoặc tổ chức cần biết telemetry nào được thu thập, gửi đi đâu và cách tắt. Trong môi trường enterprise, policy tổ chức có thể quản lý tập trung.

Tắt telemetry phải thực sự ngăn export tương ứng. Không nên tiếp tục gửi dữ liệu dưới một tên event khác.

### Retention và access control

Dữ liệu telemetry cần có thời hạn lưu giữ phù hợp và quyền truy cập giới hạn. Logs và traces có thể chứa nhiều ngữ cảnh hơn metrics, nên cần policy chặt hơn.

### Pseudonymization không đồng nghĩa anonymization

Hash một workspace path hoặc user identifier vẫn có thể cho phép liên kết nhiều phiên và nhận diện lại nếu miền giá trị nhỏ. Không nên coi việc hash là đủ để loại bỏ rủi ro riêng tư.

### Redaction

Có thể lọc hoặc redact field nhạy cảm trước khi ghi log hoặc export. Redaction nên được kiểm thử để tránh một đường code khác ghi raw data ngoài ý muốn.

## Sampling, rate limiting và chi phí telemetry

Telemetry có thể tạo nhiều dữ liệu, nhất là khi server nhận request liên tục trong lúc gõ. Cần xác định dữ liệu nào luôn giữ và dữ liệu nào có thể sampling.

### Trace sampling

Có thể dùng head sampling để quyết định lấy trace ngay khi bắt đầu request, hoặc tail sampling để quyết định sau khi biết trace chậm hay lỗi.

Một chiến lược có thể:

- Giữ tất cả trace lỗi.
- Giữ trace vượt ngưỡng latency.
- Sampling một tỷ lệ nhỏ trace thành công bình thường.
- Giữ trace cho một số method quan trọng.
- Giới hạn số span tối đa mỗi trace.

Sampling cần nhất quán để trace liên quan không bị tách rời. Với request và task nền, cần có policy rõ cho trace link.

### Log sampling

Log thành công có thể được sampling hoặc tổng hợp. Error log quan trọng có thể được giữ nhưng cần rate limit khi cùng một lỗi lặp hàng nghìn lần.

### Metric aggregation

Metrics thường được tổng hợp tại process hoặc collector. Có thể dùng histogram và counter để tránh gửi một event cho mọi request thành công.

### Bounded queue

Telemetry exporter nên có queue giới hạn. Khi queue đầy, có thể drop dữ liệu theo policy và tăng metric về dropped telemetry. Không được để queue không giới hạn gây tăng memory hoặc làm chậm language server.

## Dashboard và chỉ số vận hành

Dashboard nên giúp trả lời câu hỏi cụ thể, không chỉ hiển thị tất cả metric có sẵn.

Một dashboard tổng quan có thể có:

| Nhóm | Chỉ số |
|---|---|
| Responsiveness | p50/p95/p99 latency theo LSP method |
| Reliability | Error rate, timeout rate, crash count |
| Cancellation | Cancellation rate theo method |
| Throughput | Request rate và completed request rate |
| Queue | Active requests, queue depth |
| Workspace | Files indexed, index duration |
| Analysis | Parse và semantic analysis duration |
| Diagnostics | Publish delay, diagnostic count |
| Cache | Hit ratio, eviction rate, memory |
| Resources | CPU, memory, GC pause, worker count |
| Telemetry health | Export failures, dropped spans/events |

### Phân nhóm hợp lý

Có thể phân nhóm theo server version, runtime version, operating system family, LSP method và document size bucket nếu những giá trị này được kiểm soát.

Không nên tạo dashboard dựa trên project name hoặc file path. Các giá trị đó có cardinality cao và có thể chứa dữ liệu riêng tư.

### Baseline

Cần có baseline theo loại workload. Completion trên file nhỏ và workspace có hàng nghìn module không nên được so sánh trực tiếp mà không phân nhóm.

Có thể dùng benchmark nội bộ và telemetry tổng hợp để xác định phân phối bình thường. Khi thay đổi phiên bản, so sánh cùng nhóm method, size bucket và môi trường tương đương.

## SLO và cảnh báo

Service Level Objective (SLO) mô tả mục tiêu chất lượng dịch vụ trong một khoảng thời gian. Với language server, mục tiêu thường tập trung vào độ phản hồi và độ tin cậy của các thao tác tương tác.

Ví dụ mục tiêu minh họa:

- 95% completion request hoàn tất trong ngưỡng latency đã chọn.
- 99% hover request không gặp lỗi nội bộ.
- Diagnostics cho document change được publish trong một khoảng thời gian mục tiêu ở workspace thuộc nhóm kích thước xác định.
- Tỷ lệ crash thấp hơn một ngưỡng trong các phiên hoạt động.

Các ngưỡng thực tế cần dựa trên workload, editor, runtime và trải nghiệm sản phẩm. Không nên sao chép một con số chung cho mọi language server.

### Alert theo triệu chứng

Alert tốt thường phản ánh vấn đề người dùng cảm nhận:

- p95 completion latency tăng liên tục.
- Request error rate vượt ngưỡng.
- Worker queue tăng nhưng throughput không theo kịp.
- Memory tăng liên tục qua nhiều chu kỳ workspace.
- Diagnostics publish delay tăng.
- Server crash hoặc restart bất thường.

Một metric đơn lẻ có thể không đủ. Ví dụ memory cao nhưng ổn định chưa chắc là leak; memory tăng liên tục cùng cache entries và số open documents có thể đáng điều tra hơn.

### Burn rate

Nếu có SLO theo tỷ lệ request đáp ứng mục tiêu, error budget burn rate giúp xác định tốc độ tiêu hao ngân sách lỗi. Một đợt latency regression kéo dài có thể cần alert sớm hơn một spike ngắn.

### Tránh alert noise

Dùng cửa sổ thời gian, ngưỡng kéo dài và điều kiện kết hợp để tránh alert từ một spike nhỏ. Alert cần có runbook hoặc hướng dẫn điều tra để người trực biết bắt đầu từ đâu.

## Phân tích telemetry để tìm bottleneck

Telemetry có giá trị khi dẫn đến giả thuyết và hành động cụ thể.

### Ví dụ: completion chậm

Quan sát:

- p95 completion latency tăng.
- Queue wait thấp.
- Parse duration bình thường.
- Semantic resolution duration tăng.
- Cache hit ratio giảm.

Giả thuyết có thể là symbol index bị invalidation quá thường xuyên hoặc resolver không tái sử dụng kết quả. Trace của request chậm và metrics cache giúp kiểm tra giả thuyết.

### Ví dụ: diagnostics đến muộn

Quan sát:

- didChange rate tăng.
- Nhiều analysis task bị supersede.
- Parse task cũ tiêu tốn CPU trước khi bị hủy.
- Publish delay tăng.

Có thể cần điều chỉnh scheduling, cancellation checkpoint hoặc incremental analysis. Chỉ tăng worker count có thể làm CPU cạnh tranh nặng hơn.

### Ví dụ: memory tăng theo thời gian

Quan sát:

- Heap used tăng qua nhiều giờ.
- Open document count ổn định.
- Cache entries tăng liên tục.
- Eviction count thấp.

Có thể cache thiếu giới hạn hoặc invalidation không hoạt động. Cần profiling heap để xác định object retention, sau đó sửa cache policy và kiểm tra lại.

### Ví dụ: error rate tăng sau release

Quan sát theo server version:

- Một nhóm request mới có error rate cao.
- Lỗi tập trung ở document có một construct mới.
- Parser recovery count tăng.
- Semantic analysis nhận AST node chưa được hỗ trợ.

Có thể release đã thay grammar nhưng một provider chưa cập nhật. Correlation theo version và component giúp thu hẹp nguyên nhân.

## Instrumentation trong mã nguồn

Instrumentation nên được triển khai thông qua một abstraction để business logic không phụ thuộc trực tiếp vào backend telemetry.

Ví dụ interface:

~~~text
Telemetry
  incrementCounter(name, attributes)
  recordHistogram(name, value, attributes)
  setGauge(name, value, attributes)
  startSpan(name, context, attributes)
  recordEvent(name, attributes)
~~~

Các thành phần có thể nhận telemetry interface qua dependency injection. Trong test, dùng no-op implementation hoặc in-memory recorder.

### Đo request bằng middleware

Có thể đặt instrumentation tại request dispatcher:

~~~text
handleRequest(request):
    start = clock.monotonicNow()
    method = classifyMethod(request.method)

    metrics.requestsReceived.increment(method)

    try:
        result = dispatch(request)
        metrics.requestsCompleted.increment(method, "success")
        return result

    catch Cancelled:
        metrics.requestsCancelled.increment(method)
        throw

    catch error:
        metrics.requestsFailed.increment(method, classify(error))
        logs.error("request-failed", method, errorCode(error))
        throw

    finally:
        duration = clock.monotonicNow() - start
        metrics.requestDuration.record(duration, method)
~~~

Dùng monotonic clock để đo duration, vì wall clock có thể bị điều chỉnh. Cần phân loại cancellation riêng và tránh double-count một lỗi đã được xử lý ở tầng thấp.

### Đo từng stage

Một stage có thể tạo span hoặc ghi histogram:

~~~text
with span("semantic-analysis"):
    result = semanticAnalyzer.analyze(snapshot)
~~~

Không nên tạo quá nhiều span cho mỗi AST node nếu overhead cao. Có thể đo tổng stage và thêm chi tiết cho các operation đắt tiền.

### Instrumentation không làm thay đổi semantics

Nếu telemetry exporter ném exception hoặc bị lỗi, request ngôn ngữ vẫn phải hoạt động theo chính sách. Instrumentation không được làm thay đổi kết quả parser, completion hoặc diagnostics.

API telemetry nên an toàn khi không được cấu hình, có thể dùng no-op provider và không ném lỗi ra caller vì lỗi export thông thường.

### Tách clock và exporter

Inject clock giúp test duration mà không phụ thuộc thời gian thật. Tách exporter giúp thay backend mà không sửa các language service.

## Kiểm thử telemetry

Telemetry code cũng cần được kiểm tra để số liệu đáng tin cậy và không làm hỏng request.

### Unit test cho metric

Kiểm tra:

- Request success tăng counter đúng một lần.
- Error tăng đúng category.
- Cancellation không bị tính thành internal error.
- Duration được ghi kể cả khi exception xảy ra.
- Gauge tăng và giảm đúng.
- Label chỉ nhận giá trị thuộc tập cho phép.

### Test tracing

Kiểm tra:

- Request tạo root span.
- Stage span có parent hoặc link phù hợp.
- Error status được ghi đúng.
- Cancellation có trạng thái riêng theo policy.
- Context được truyền qua worker.
- Span kết thúc khi task hoàn tất hoặc bị hủy.

### Test privacy

Dùng payload có tên project, path và identifier giả lập rồi xác nhận chúng không xuất hiện trong exported attributes, logs hoặc metrics.

Có thể kiểm tra allowlist field thay vì chỉ tìm một số chuỗi cấm. Test cần bao phủ error path vì exception message đôi khi chứa source snippet hoặc path.

### Test exporter failure

Giả lập:

- Collector không phản hồi.
- Queue đầy.
- Export timeout.
- Exporter ném exception.
- Shutdown xảy ra khi batch chưa gửi.

Language server vẫn phải xử lý request bình thường, và dropped telemetry cần được ghi nhận theo policy.

### Test hiệu năng instrumentation

So sánh overhead khi telemetry tắt và bật trong workload tương tự. Đo CPU, allocation và latency. Instrumentation không nên tạo allocation lớn hoặc lock contention trên hot path completion.

### Integration test

Chạy language server với LSP client test harness, gửi initialize, didOpen, completion, didChange và shutdown. Xác nhận metrics và traces phản ánh đúng lifecycle, đồng thời response giao thức vẫn hợp lệ.

## Vận hành telemetry trong môi trường người dùng

Language server có thể chạy trên laptop của developer, trong container, trên remote development host hoặc trong môi trường enterprise. Cấu hình telemetry cần phù hợp từng môi trường.

### Local development

Trong môi trường phát triển, có thể bật DEBUG logs, trace sampling cao và profiler khi điều tra. Dữ liệu nên được lưu cục bộ hoặc gửi đến backend thử nghiệm.

### Production desktop

Ở môi trường desktop, cần chú ý CPU, memory, battery và network. Export nên không chặn UI hoặc request. Người dùng cần biết trạng thái telemetry và có cách tắt theo policy.

### Remote development

Language server có thể chạy trên máy remote, còn editor chạy local. Client latency và server latency có thể khác đáng kể do network. Tracing cần phân biệt transport delay với processing time nếu có khả năng đo ở cả hai phía.

### Enterprise deployment

Tổ chức có thể yêu cầu telemetry bị tắt, được chuyển đến collector nội bộ hoặc chỉ cho phép một tập field. Cần hỗ trợ cấu hình tập trung và không để user-level setting vượt policy tổ chức.

### Version và rollout

Telemetry nên ghi server version và protocol/runtime version để so sánh release. Khi rollout theo nhóm, có thể quan sát latency, error rate và crash rate trước khi mở rộng.

## Những lỗi thường gặp khi thiết kế telemetry

### Chỉ đo thời gian tổng

Một con số tổng không cho biết parser, resolver, queue hay serialization gây chậm. Nên đo cả request boundary và stage quan trọng.

### Chỉ nhìn average

Average có thể che giấu tail latency. Cần xem histogram và percentile theo method.

### Dùng dữ liệu không giới hạn làm metric label

URI, symbol name hoặc request ID tạo cardinality lớn và có thể làm lộ dữ liệu. Dùng label có tập giá trị nhỏ và ổn định.

### Ghi source code vào logs

Source code và literal có thể chứa thông tin nhạy cảm. Ưu tiên metadata tổng hợp; chỉ thu thập nội dung khi có consent rõ ràng trong một quy trình debug riêng.

### Coi cancellation là lỗi

Completion cũ bị hủy khi người dùng gõ tiếp là bình thường. Cần đo cancellation riêng và xem tỷ lệ theo method.

### Export đồng bộ trên request path

Network telemetry chậm có thể làm language server chậm theo. Dùng queue bounded và exporter bất đồng bộ.

### Không kiểm tra telemetry overhead

Instrumentation quá chi tiết có thể tự tạo bottleneck. Đo overhead và sampling trên hot path.

### Không gắn version

Không có server version thì khó xác định regression bắt đầu ở release nào. Ghi version ổn định và runtime metadata cần thiết.

### Không định nghĩa metric

Tên metric không rõ đơn vị hoặc semantics khiến dashboard dễ hiểu sai. Mỗi metric cần có mô tả, đơn vị, type và label contract.

### Không có policy privacy

Nếu chỉ thêm telemetry mà chưa định nghĩa dữ liệu nào được thu thập, ai có quyền truy cập và retention bao lâu, hệ thống có thể tạo rủi ro không cần thiết.

## Quy trình triển khai đo lường và telemetry cho language server

Một quy trình thực tế có thể đi theo các bước:

1. **Xác định câu hỏi vận hành:** cần biết latency, lỗi, tài nguyên, indexing hay chất lượng tính năng nào.
2. **Chọn các điểm đo:** request dispatcher, document sync, parser, resolver, indexer, diagnostics và backend.
3. **Định nghĩa metric contract:** tên, type, unit, labels, bucket và cách diễn giải.
4. **Thiết kế log schema:** event name, severity, component, error code và correlation context.
5. **Thiết kế tracing:** root span, stage span, context propagation và async task links.
6. **Thiết kế privacy policy:** allowlist field, consent, redaction, retention và export destination.
7. **Chọn SDK và collector:** OpenTelemetry hoặc abstraction phù hợp, batching và bounded queue.
8. **Tách instrumentation khỏi business logic:** dùng interface, no-op provider và dependency injection.
9. **Xây dashboard:** latency percentile, error rate, queue, workspace, cache và resource usage.
10. **Đặt SLO và alert:** tập trung vào triệu chứng người dùng cảm nhận, tránh alert noise.
11. **Kiểm thử:** counter, histogram, trace context, privacy, exporter failure và overhead.
12. **Rollout có kiểm soát:** theo dõi version, so sánh baseline và điều chỉnh sampling.
13. **Duy trì tài liệu:** mô tả từng metric, log event, span attribute và policy dữ liệu.

Nên bắt đầu với một bộ metrics nhỏ cho request latency, error, cancellation, queue, indexing và memory. Sau khi dashboard chỉ ra vùng cần điều tra, bổ sung trace hoặc profiling ở đúng stage. Cách làm này giữ chi phí instrumentation ở mức phù hợp và giúp telemetry phục vụ câu hỏi cụ thể.

## Kết luận

Đo lường và telemetry giúp nhóm phát triển hiểu hiệu năng, độ tin cậy và hành vi vận hành của language server trong các môi trường sử dụng thực tế. Metrics cho thấy xu hướng tổng thể; logs ghi sự kiện cụ thể; traces giải thích đường đi và thời gian của request; profiling hỗ trợ điều tra sâu.

Một hệ thống telemetry hữu ích cần đo cả request và công việc nền, phân biệt success, error, cancellation và timeout, theo dõi latency theo method và stage, quan sát parser/indexer/semantic engine, đồng thời quản lý resource, cache và document synchronization. Metric phải có type, unit và label contract rõ ràng; tracing phải truyền context qua các thành phần đồng bộ và bất đồng bộ.

Telemetry cần được thiết kế với privacy và hiệu năng ngay từ đầu. Không thu thập source code hoặc định danh nhạy cảm theo mặc định, tránh label cardinality cao, dùng exporter bất đồng bộ có giới hạn và bảo đảm lỗi telemetry không ảnh hưởng chức năng language server. Khi kết hợp dashboard, SLO, alert và kiểm thử instrumentation, nhóm có thể phát hiện regression sớm, xác định bottleneck và cải thiện trải nghiệm editor dựa trên bằng chứng vận hành.
