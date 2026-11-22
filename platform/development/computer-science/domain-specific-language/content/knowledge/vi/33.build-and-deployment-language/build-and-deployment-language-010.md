# Quan sát pipeline

Trong quá trình xây dựng và triển khai một ngôn ngữ chuyên biệt cho lĩnh vực (Domain-Specific Language — DSL), mã nguồn thường đi qua nhiều công đoạn trước khi trở thành một chương trình có thể chạy trong môi trường đích. Một pipeline có thể phân tích cú pháp, kiểm tra kiểu, xác thực quy tắc nghiệp vụ, sinh mã, đóng gói artifact, chạy kiểm thử, phát hành và triển khai. Mỗi công đoạn nhận đầu vào, thực hiện một nhóm công việc và tạo đầu ra cho công đoạn tiếp theo.

**Quan sát pipeline (pipeline observability)** là khả năng hiểu pipeline đang làm gì, đã đi qua những bước nào, mất bao lâu, sử dụng tài nguyên ra sao, tạo ra artifact nào và vì sao một bước thành công hoặc thất bại. Quan sát tốt giúp nhóm phát hiện lỗi, xác định nguyên nhân, tìm điểm nghẽn hiệu năng, theo dõi độ tin cậy của bản phát hành và kiểm tra mối liên hệ giữa source DSL với hệ thống đang chạy.

Quan sát pipeline bao gồm nhiều tín hiệu có quan hệ với nhau: log ghi lại sự kiện và thông tin chi tiết; metric đo số lượng, tỷ lệ và thời gian; trace thể hiện đường đi của một lần thực thi qua nhiều thành phần; trạng thái pipeline cho biết tiến độ; artifact metadata và provenance cho biết kết quả được tạo từ nguồn nào, bằng công cụ và cấu hình nào.

Với DSL, observability cần hiểu các khái niệm của cả quá trình xây dựng ngôn ngữ lẫn quá trình chạy chương trình. Một lỗi parser khác với lỗi type checker, lỗi generator khác với lỗi deploy, còn lỗi workflow runtime có thể liên quan đến một phiên bản DSL đã được biên dịch trước đó. Nếu chỉ có một dòng “build failed”, nhóm phát triển sẽ thiếu thông tin để tìm đúng tầng gây lỗi.

Bài học này trình bày mô hình pipeline, các giai đoạn quan sát, log, metric và trace, correlation ID, dashboard, cảnh báo, chẩn đoán lỗi, hiệu năng, artifact provenance, bảo mật dữ liệu quan sát, triển khai trong CI/CD và cách thiết kế một hệ thống quan sát pipeline cho DSL.

## 1. Pipeline trong hệ sinh thái DSL

Pipeline là chuỗi công đoạn có quan hệ phụ thuộc. Đầu ra của một bước có thể trở thành đầu vào của bước kế tiếp. Một pipeline DSL thường bao gồm các giai đoạn sau:

~~~text
DSL Source
    |
    v
Parse
    |
    v
Semantic Analysis
    |
    v
Validation
    |
    v
Compile / Generate
    |
    v
Package
    |
    v
Test
    |
    v
Publish Artifact
    |
    v
Deploy
    |
    v
Runtime
~~~

Không phải mọi hệ thống đều dùng đúng thứ tự này. Một số bước có thể chạy song song, một số bước được lặp lại khi có thay đổi, và một số pipeline chỉ chạy đến validation mà không tạo artifact.

### 1.1. Pipeline xây dựng DSL

Pipeline xây dựng ngôn ngữ xử lý chính source code và các thành phần của toolchain:

- Đọc và phân tích grammar.
- Sinh parser hoặc cập nhật parser.
- Biên dịch module của compiler.
- Chạy test cho parser, type checker và generator.
- Đóng gói compiler, runtime và plugin.
- Phát hành phiên bản toolchain.

Quan sát pipeline này giúp phát hiện regression của chính nền tảng DSL, ví dụ parser build chậm, test suite tăng thời gian hoặc package thiếu một module.

### 1.2. Pipeline xử lý chương trình DSL

Một dự án dùng DSL có thể đi qua:

- Load workspace và resolve dependency.
- Parse file nguồn.
- Resolve symbol và type.
- Kiểm tra constraint.
- Sinh SQL, JSON Schema, bytecode hoặc mã host.
- Chạy test và static analysis.
- Tạo artifact.
- Triển khai artifact đến môi trường đích.

Mỗi giai đoạn nên có trạng thái và diagnostic riêng để người dùng biết lỗi xuất hiện ở đâu.

### 1.3. Pipeline thực thi workflow

Sau khi deploy, workflow DSL có thể tiếp tục tạo execution pipeline ở runtime:

~~~text
Receive Event
    |
    v
Resolve Workflow Instance
    |
    v
Evaluate Guard
    |
    v
Run Action
    |
    v
Persist State
    |
    v
Publish Result Event
~~~

Pipeline runtime thường có nhiều instance đồng thời. Cần quan sát cả trạng thái từng instance lẫn sức khỏe tổng thể của runtime.

### 1.4. Pipeline không nhất thiết là một đường thẳng

Các bước có thể tạo nhánh:

~~~text
                 +--> Unit Tests -----+
Source -> Build -+                     +--> Package
                 +--> Static Analysis -+
~~~

Một nhánh test có thể chạy song song với static analysis. Package chỉ được tạo khi các nhánh bắt buộc hoàn tất thành công. Observability cần thể hiện dependency graph, trạng thái từng nhánh và điều kiện chờ.

## 2. Mục tiêu của pipeline observability

Quan sát pipeline không chỉ nhằm hiển thị log. Nó cần giúp trả lời những câu hỏi vận hành cụ thể.

### 2.1. Trạng thái hiện tại

- Pipeline đang chờ, đang chạy, thành công hay thất bại?
- Bước nào đang thực thi?
- Có nhánh nào đang chờ dependency?
- Pipeline bị hủy hay timeout?
- Artifact đã được tạo và publish chưa?

### 2.2. Nguyên nhân và tác động

- Bước nào gây lỗi đầu tiên?
- Diagnostic bắt nguồn từ file và vị trí DSL nào?
- Lỗi ảnh hưởng một module hay toàn workspace?
- Một lần deploy thất bại có làm môi trường hiện tại thay đổi không?
- Có artifact hoặc service nào phụ thuộc vào kết quả lỗi?

### 2.3. Thời gian và tài nguyên

- Pipeline mất bao lâu từ đầu đến cuối?
- Bước nào chiếm nhiều thời gian nhất?
- Parser, generator hay test là bottleneck?
- CPU, memory, I/O và network được sử dụng ra sao?
- Thời gian chờ queue chiếm bao nhiêu?

### 2.4. So sánh và xu hướng

- Build hiện tại có chậm hơn các build trước không?
- Tỷ lệ pipeline thành công thay đổi thế nào?
- Số diagnostic mới tăng hay giảm?
- Thời gian deploy giữa các môi trường có khác biệt không?
- Phiên bản compiler nào thường gây lỗi?

### 2.5. Truy nguyên kết quả

- Artifact được tạo từ commit, source revision và DSL version nào?
- Compiler và generator phiên bản nào đã chạy?
- Cấu hình build và dependency lockfile nào được dùng?
- Artifact nào đã được deploy vào môi trường nào?
- Một runtime execution sử dụng artifact nào?

## 3. Ba tín hiệu chính: log, metric và trace

Ba loại telemetry bổ sung cho nhau. Không loại nào thay thế hoàn toàn hai loại còn lại.

| Tín hiệu | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| Log | Điều gì đã xảy ra và chi tiết là gì? | Parser phát diagnostic tại file order.dsl |
| Metric | Sự việc xảy ra bao nhiêu lần, trong bao lâu? | Thời gian compile p95 tăng lên |
| Trace | Một lần xử lý đi qua những thành phần nào? | Build đi từ queue đến compiler, test và registry |

### 3.1. Log

Log là bản ghi sự kiện tại một thời điểm. Log có thể chứa mức độ, thời gian, component, pipeline ID, step ID và dữ liệu ngữ cảnh.

Log tốt nên có cấu trúc để có thể lọc và truy vấn. Thông điệp text tự do vẫn hữu ích cho con người, nhưng các trường có cấu trúc giúp tổng hợp và liên kết dữ liệu.

### 3.2. Metric

Metric là số đo được tổng hợp theo thời gian. Ví dụ:
- Số pipeline bắt đầu.
- Số pipeline thành công và thất bại.
- Thời gian từng stage.
- Số diagnostic theo severity.
- Số artifact được tạo.
- Queue depth.
- Memory sử dụng.
- Số lần retry.

Metric cần có tên, loại, đơn vị và nhãn được kiểm soát.

### 3.3. Trace

Trace thể hiện một lần xử lý xuyên qua nhiều component. Mỗi trace có thể gồm nhiều span, mỗi span đại diện một công đoạn hoặc lời gọi.

Ví dụ:

~~~text
Trace: build-8f21
  queue.wait                  120 ms
  workspace.resolve           85 ms
  parser.run                 340 ms
  semantic.analysis          510 ms
  generator.run              760 ms
  tests.run                 2400 ms
  artifact.package           190 ms
  registry.publish           230 ms
~~~

Trace giúp nhìn thấy thời gian nằm ở bước nào và quan hệ cha-con giữa các hoạt động.

### 3.4. Kết hợp ba tín hiệu

Một alert metric có thể báo tỷ lệ build thất bại tăng. Người vận hành mở trace để tìm stage có lỗi, rồi mở log của span đó để đọc diagnostic cụ thể. Cả ba tín hiệu nên chia sẻ trace ID, pipeline ID hoặc các trường liên kết tương ứng.

## 4. Mô hình dữ liệu quan sát

Một hệ thống observability cần schema thống nhất cho pipeline, stage, task, artifact và runtime execution.

### 4.1. Pipeline run

Một pipeline run có thể lưu:

~~~text
PipelineRun
  pipelineId
  runId
  projectId
  sourceRevision
  definitionVersion
  trigger
  environment
  startedAt
  finishedAt
  status
  actor
  correlationId
~~~

Run ID định danh một lần chạy. Pipeline ID định danh định nghĩa hoặc loại pipeline. Không nên dùng một ID cho cả hai khái niệm.

### 4.2. Stage và task

~~~text
StageRun
  stageId
  runId
  name
  status
  startedAt
  finishedAt
  attempt
  parentStageId
  inputReferences
  outputReferences
~~~

Một stage có thể chứa nhiều task hoặc substage. Parent ID giúp tái dựng cây thực thi.

### 4.3. Trạng thái chuẩn hóa

Có thể dùng các trạng thái:

- QUEUED: đang chờ worker.
- RUNNING: đang thực thi.
- SUCCEEDED: hoàn tất thành công.
- FAILED: thất bại.
- CANCELLED: bị hủy.
- SKIPPED: bị bỏ qua theo điều kiện.
- TIMED_OUT: vượt quá giới hạn thời gian.
- BLOCKED: chưa thể chạy do dependency.
- RETRYING: đang chờ lần thử tiếp theo.

Cần phân biệt SKIPPED với SUCCEEDED. Một stage không chạy vì điều kiện không thỏa không giống stage đã chạy thành công.

### 4.4. Thời điểm và duration

Nên lưu timestamp bắt đầu và kết thúc theo chuẩn thống nhất, thường là UTC. Duration được tính từ hai thời điểm hoặc đo bằng monotonic clock trong process để tránh sai lệch do đồng hồ hệ thống thay đổi.

### 4.5. Resource identity

Mọi log và diagnostic gắn với file hoặc artifact cần dùng URI hoặc resource ID ổn định. Không nên chỉ lưu đường dẫn tuyệt đối của máy worker vì đường dẫn đó không có ý nghĩa với người xem ở máy khác.

## 5. Correlation ID và truy vết xuyên suốt

Một pipeline có thể đi qua editor, API, queue, worker, compiler, artifact registry, deployment controller và runtime. Cần một cách liên kết các sự kiện đó.

### 5.1. Các loại định danh

- Pipeline ID: loại pipeline hoặc định nghĩa.
- Run ID: một lần chạy cụ thể.
- Stage ID: một stage trong pipeline.
- Task ID: một công việc nhỏ.
- Trace ID: một trace phân tán.
- Span ID: một span trong trace.
- Correlation ID: liên kết các hoạt động nghiệp vụ.
- Artifact ID: định danh đầu ra.
- Deployment ID: một lần triển khai.

Các ID có thể được liên kết nhưng không nên bị dùng thay thế cho nhau.

### 5.2. Truyền correlation context

Khi một stage tạo task tiếp theo, nó truyền context phù hợp:

~~~text
Pipeline Run
  runId = run-123
  traceId = trace-abc
  correlationId = order-domain-build-7

Compile Task
  runId = run-123
  traceId = trace-abc
  parentSpan = compile-stage
~~~

Khi gọi API hoặc gửi message, context cần được truyền qua header hoặc metadata theo giao thức.

### 5.3. Async boundary

Queue và message broker làm đứt luồng gọi đồng bộ. Producer cần gắn trace context vào message; consumer khôi phục context khi xử lý. Nếu không, trace sẽ kết thúc ở lúc publish và bắt đầu một trace không liên quan ở consumer.

### 5.4. Fan-out và fan-in

Khi một stage tạo nhiều nhánh song song, mỗi nhánh có span con hoặc trace link. Khi các nhánh hợp nhất, parent stage chờ các kết quả cần thiết và ghi nhận trạng thái tổng hợp.

### 5.5. Tránh định danh không ổn định

Không dùng email, tên người dùng hoặc nội dung source làm correlation ID. ID nên không mang dữ liệu cá nhân, khó đoán khi cần và có vòng đời phù hợp.

## 6. Quan sát từng giai đoạn của DSL pipeline

Mỗi stage có các chỉ số và diagnostic đặc trưng. Việc quan sát theo stage giúp phân biệt lỗi của ngôn ngữ, toolchain và môi trường triển khai.

### 6.1. Load workspace và dependency resolution

Theo dõi:
- Số file và module được phát hiện.
- Thời gian resolve dependency.
- Dependency không tìm thấy hoặc sai version.
- Cache hit/miss.
- Kích thước workspace.
- File bị bỏ qua theo cấu hình.

Một lỗi ở đây có thể khiến parser không bao giờ chạy. Log nên nêu dependency hoặc resource không resolve được.

### 6.2. Parsing

Theo dõi:
- Số file parse.
- Thời gian parse theo file và tổng.
- Số syntax error.
- Số warning.
- Kích thước source.
- Tỷ lệ parser cache hit.
- File parse chậm bất thường.

Diagnostic nên chứa source URI, range, error code và thông điệp dễ hiểu. Không cần gửi toàn bộ source text vào telemetry.

### 6.3. Semantic analysis

Theo dõi:
- Thời gian symbol resolution.
- Thời gian type checking.
- Số unresolved reference.
- Số type mismatch.
- Số dependency cycle.
- Kích thước symbol index.
- Cache invalidation và rebuild.

Phân biệt lỗi semantic với lỗi syntax để người dùng biết parser đã thành công nhưng chương trình chưa hợp lệ về ngữ nghĩa.

### 6.4. Validation

Validator có thể kiểm tra constraint nghiệp vụ, security policy, schema compatibility và quy ước dự án.

Theo dõi:
- Số rule đã chạy.
- Số rule pass/fail.
- Thời gian theo validator.
- Rule timeout.
- Severity và category của diagnostic.
- Phiên bản bộ rule.

Một validation rule chậm có thể là bottleneck dù parsing và compilation nhanh.

### 6.5. Compilation và code generation

Theo dõi:
- Thời gian compile.
- Số AST node hoặc IR instruction.
- Số file generated.
- Kích thước output.
- Warning từ generator.
- Target profile.
- Cache hit.
- Phiên bản compiler và generator.

Generated code cần được liên kết với source revision và mapping metadata.

### 6.6. Packaging

Theo dõi:
- Số file trong package.
- Tổng kích thước artifact.
- Thời gian đóng gói.
- Dependency được đưa vào.
- Checksum.
- Signing result.
- Manifest validation.

Nếu package thiếu module hoặc chứa phiên bản dependency sai, cần biết danh sách thành phần và manifest đã dùng.

### 6.7. Testing

Theo dõi:
- Số test được phát hiện.
- Pass, fail, skipped.
- Thời gian từng suite.
- Flaky test.
- Coverage nếu có.
- Test environment.
- Log và report tham chiếu.

Không nên chỉ lưu tổng số test thất bại. Cần liên kết từng failure với test case và artifact được kiểm tra.

### 6.8. Publish và deploy

Theo dõi:
- Registry hoặc target environment.
- Artifact ID và checksum.
- Thời gian upload.
- Deployment strategy.
- Rollout progress.
- Health check.
- Rollback.
- Kết quả sau triển khai.

Phân biệt publish thành công với deploy thành công. Artifact có thể đã được lưu trong registry dù deployment thất bại.

### 6.9. Runtime

Sau deploy, theo dõi:
- Số execution.
- Tỷ lệ thành công và lỗi.
- Thời gian xử lý.
- Queue lag.
- Retry và timeout.
- State transition.
- Resource consumption.
- Dependency call.
- Phiên bản artifact đang chạy.

Runtime telemetry cần liên kết về artifact và DSL definition version để có thể truy nguyên.

## 7. Structured logging

Structured logging ghi log dưới dạng các trường có schema, thường được serialize thành JSON hoặc định dạng tương đương.

Ví dụ:

~~~json
{
  "timestamp": "2026-11-15T08:30:00Z",
  "level": "ERROR",
  "service": "dsl-compiler",
  "event": "semantic_validation_failed",
  "runId": "run-123",
  "stage": "semantic-analysis",
  "traceId": "trace-abc",
  "sourceUri": "workspace://sales/order.dsl",
  "diagnosticCode": "DSL-TYPE-014",
  "message": "Expected Decimal but found String"
}
~~~

### 7.1. Trường chung

Có thể chuẩn hóa:
- timestamp.
- severity.
- service/component.
- environment.
- event name.
- run ID.
- stage ID.
- trace ID.
- resource URI.
- error code.
- duration.
- outcome.

### 7.2. Severity

Các mức thường gặp:
- TRACE: chi tiết rất thấp, dùng khi điều tra.
- DEBUG: thông tin phát triển.
- INFO: tiến trình bình thường.
- WARN: tình trạng bất thường nhưng có thể tiếp tục.
- ERROR: một thao tác thất bại.
- FATAL: thành phần không thể tiếp tục.

Mức severity cần được dùng nhất quán. Không nên ghi mọi diagnostic thành ERROR nếu pipeline vẫn có thể tiếp tục theo policy.

### 7.3. Event name ổn định

Dùng event name có cấu trúc như compile.started, compile.completed hoặc deploy.failed. Tránh dùng toàn bộ câu tự do làm event key vì khó tổng hợp.

### 7.4. Diagnostic code

Mã lỗi ổn định giúp liên kết log, tài liệu và quick fix. Message có thể được dịch hoặc cải thiện mà code vẫn giữ nguyên.

### 7.5. Log volume

Không ghi một log cho mỗi node AST trong build thông thường nếu không cần. Có thể dùng sampling, mức log và instrumentation chi tiết theo cấu hình để tránh log quá nhiều.

## 8. Metrics và cách chọn chỉ số

Metric cần phản ánh một câu hỏi vận hành. Một tập metric quá lớn hoặc không có mục đích sẽ làm dashboard khó hiểu.

### 8.1. Counter

Counter tăng theo sự kiện và không giảm trong vòng đời metric:

~~~text
dsl_pipeline_runs_total
dsl_pipeline_failures_total
dsl_diagnostics_total
dsl_artifacts_published_total
~~~

Có thể phân loại bằng nhãn như pipeline type, stage hoặc result.

### 8.2. Gauge

Gauge thể hiện giá trị hiện tại, có thể tăng hoặc giảm:

~~~text
dsl_pipeline_queue_depth
dsl_active_build_workers
dsl_active_workflow_instances
dsl_runtime_memory_bytes
~~~

### 8.3. Histogram

Histogram ghi phân bố giá trị, thường dùng cho duration hoặc payload size:

~~~text
dsl_stage_duration_seconds
dsl_compile_duration_seconds
dsl_deploy_duration_seconds
dsl_runtime_execution_duration_seconds
~~~

Từ histogram có thể tính percentile như p50, p95 và p99 tùy hệ thống metrics.

### 8.4. Tỷ lệ thành công

Tỷ lệ thành công nên có mẫu số rõ ràng:

~~~text
successful_runs / completed_runs
~~~

Không nên tính run đang chạy hoặc bị hủy vào mẫu số nếu mục tiêu là tỷ lệ thành công của các run đã kết thúc. Cần công bố định nghĩa để dashboard nhất quán.

### 8.5. Throughput

Throughput có thể đo số pipeline hoặc artifact hoàn thành trong một khoảng thời gian. Với runtime, có thể đo số event hoặc workflow transition mỗi giây.

### 8.6. Queue metrics

Queue depth, oldest message age và processing lag giúp phân biệt worker chậm với pipeline thực sự đang thực thi lâu.

### 8.7. Resource metrics

Theo dõi CPU, memory, disk, network, file descriptor và worker utilization. Khi compiler xử lý workspace lớn, memory pressure có thể gây GC pause hoặc OOM.

### 8.8. Cardinality

Không đưa run ID, file path đầy đủ, user ID hoặc commit SHA làm label metric có cardinality cao. Những giá trị này phù hợp với log và trace. Metric label nên có tập giá trị giới hạn như stage, result, target và compiler version đã kiểm soát.

## 9. Distributed tracing

Distributed tracing giúp theo dõi một pipeline qua nhiều process và service.

### 9.1. Trace và span

Trace là một cây hoặc đồ thị các span có quan hệ nhân quả. Span có thể ghi:
- Tên operation.
- Start/end time.
- Parent span.
- Attributes.
- Status.
- Events.
- Links đến span khác.

### 9.2. Span theo stage

Ví dụ:

~~~text
pipeline.run
  workspace.resolve
  parser.parse
  semantic.check
  validator.execute
  generator.compile
  tests.execute
  artifact.package
  registry.publish
  deployment.rollout
~~~

Span giúp xác định stage nào chiếm phần lớn thời gian.

### 9.3. Span event

Một span dài có thể có event như cache miss, retry, diagnostic emitted hoặc worker reassigned. Không cần tạo span riêng cho mọi thao tác nhỏ.

### 9.4. Error status

Khi span thất bại, ghi status và error type. Không nên chỉ đặt status ERROR mà không có error code hoặc liên kết đến diagnostic cụ thể.

### 9.5. Retry span

Mỗi attempt có thể là span con riêng hoặc event trong span của operation. Cách biểu diễn cần nhất quán để nhìn thấy số lần retry và thời gian chờ.

### 9.6. Sampling

Không phải trace nào cũng cần lưu đầy đủ. Có thể sampling theo tỷ lệ, theo lỗi hoặc theo thời gian vượt ngưỡng. Tail-based sampling giữ lại trace có lỗi hoặc latency cao nhưng cần collector hỗ trợ và tài nguyên phù hợp.

### 9.7. Trace context propagation

Khi gọi service hoặc gửi message, truyền trace context theo chuẩn tương thích như W3C Trace Context nếu hệ sinh thái sử dụng. Không tự tạo header không có quy ước chung nếu cần tích hợp nhiều công cụ.

## 10. Pipeline state và tiến độ

Ngoài log và telemetry, người dùng cần một mô hình trạng thái dễ hiểu để theo dõi tiến độ.

### 10.1. Trạng thái pipeline

~~~text
QUEUED
  |
  v
RUNNING
  |
  +--> SUCCEEDED
  |
  +--> FAILED
  |
  +--> CANCELLED
  |
  +--> TIMED_OUT
~~~

Một pipeline có thể có trạng thái BLOCKED nếu chưa đủ điều kiện chạy.

### 10.2. Trạng thái stage

Stage có thể:
- Chờ dependency.
- Đang chạy.
- Thành công.
- Thất bại.
- Bị bỏ qua.
- Đang retry.
- Bị hủy.

UI nên hiển thị trạng thái từng stage thay vì chỉ một spinner tổng thể.

### 10.3. Progress percentage

Phần trăm tiến độ chỉ có ý nghĩa khi trọng số và tổng công việc có thể ước lượng. Với pipeline có nhánh động hoặc số task không biết trước, phần trăm có thể gây hiểu nhầm.

Có thể hiển thị stage hiện tại, số task hoàn thành và số task còn lại thay vì phần trăm giả chính xác.

### 10.4. Dependency graph

UI có thể thể hiện DAG pipeline và highlight node đang chạy, node thành công và node lỗi. Với graph lớn, cần nhóm stage hoặc thu gọn subgraph.

### 10.5. Thời gian chờ và thời gian chạy

Một stage có thể mất nhiều thời gian vì chờ worker hoặc chờ dependency. Tách queue wait time khỏi execution time giúp xác định nguyên nhân.

## 11. Diagnostic và liên kết về mã nguồn DSL

Một giá trị quan trọng của observability trong DSL là đưa lỗi runtime hoặc build trở lại đúng vị trí source.

### 11.1. Diagnostic schema

Một diagnostic có thể gồm:

~~~text
Diagnostic
  code
  severity
  message
  sourceUri
  sourceRange
  stage
  runId
  relatedLocations
  documentationUri
~~~

### 11.2. Source mapping

Nếu DSL được biên dịch thành mã host hoặc bytecode, compiler cần lưu source map từ generated location về DSL source. Runtime exception có thể dùng mapping này để hiển thị file và dòng nguồn.

### 11.3. Diagnostic xuyên stage

Một warning từ validator có thể được tạo ở stage validation nhưng liên quan đến declaration trong source. Một runtime error có thể phát sinh sau deploy nhưng trỏ về expression trong DSL. Diagnostic nên giữ cả nơi phát hiện lẫn nơi nguồn.

### 11.4. Related location

Một lỗi type có thể liên quan đến cả nơi khai báo biến và nơi sử dụng. UI nên hiển thị các location liên quan thay vì chỉ một dòng.

### 11.5. Diagnostic deduplication

Một lỗi có thể được phát hiện ở nhiều stage hoặc lặp lại qua nhiều file phụ thuộc. Cần có quy tắc gộp dựa trên code, resource, range và context phù hợp, đồng thời không xóa mất thông tin số lần xảy ra.

### 11.6. Build failure summary

Summary nên cho biết:
- Stage thất bại đầu tiên.
- Error code.
- Số lỗi và warning.
- File hoặc module liên quan.
- Link tới log/trace.
- Hành động tiếp theo có thể thực hiện.

## 12. Dashboard cho pipeline

Dashboard tổng hợp trạng thái và xu hướng để người dùng và vận hành nhanh chóng đánh giá sức khỏe hệ thống.

### 12.1. Dashboard tổng quan

Có thể gồm:
- Pipeline runs theo thời gian.
- Success rate.
- Failure rate.
- Median và p95 duration.
- Queue depth.
- Active workers.
- Artifact publication rate.
- Deployment health.

### 12.2. Dashboard theo stage

Hiển thị thời gian trung bình và percentile của parser, semantic analysis, validation, generator, test, package và deploy. Có thể so sánh giữa compiler version hoặc project group.

### 12.3. Dashboard theo dự án

Cho phép lọc theo:
- Project.
- Branch hoặc source revision.
- DSL version.
- Compiler version.
- Target environment.
- Trigger type.
- Outcome.

### 12.4. Dashboard runtime

Theo dõi execution count, state distribution, error rate, latency, retries, timeout và queue lag. Với workflow, có thể phân tích số instance đang ở từng state và thời gian ở state đó.

### 12.5. Dashboard cần có ngữ cảnh

Một biểu đồ failure rate tăng cần có bộ lọc và link đến danh sách run thất bại. Một con số tổng hợp mà không thể drill down sẽ khó dùng để điều tra.

## 13. Alerting và SLO

Alert giúp phát hiện tình trạng cần hành động. Không nên tạo alert cho mọi warning vì sẽ gây nhiễu và khiến người vận hành bỏ qua cảnh báo quan trọng.

### 13.1. Alert theo triệu chứng

Ví dụ:
- Tỷ lệ build thất bại vượt ngưỡng.
- p95 compile duration tăng kéo dài.
- Queue oldest message age vượt giới hạn.
- Deployment health check thất bại.
- Runtime error rate tăng.
- Worker memory liên tục gần giới hạn.

### 13.2. Alert theo nguyên nhân

Có thể cảnh báo:
- Dependency registry không truy cập được.
- Compiler worker OOM.
- Schema validation service timeout.
- Artifact signing thất bại.

Alert theo nguyên nhân hữu ích khi tín hiệu rõ, nhưng không nên thay thế alert theo ảnh hưởng người dùng.

### 13.3. SLI

Service Level Indicator là chỉ số phản ánh chất lượng dịch vụ. Ví dụ:
- Tỷ lệ build hợp lệ hoàn tất trong thời gian mục tiêu.
- Tỷ lệ deployment thành công.
- Thời gian từ commit đến artifact sẵn sàng.
- Tỷ lệ workflow execution hoàn tất không có lỗi kỹ thuật.

### 13.4. SLO

Service Level Objective là mục tiêu cho SLI trong một cửa sổ thời gian. Ví dụ, 95% pipeline build tiêu chuẩn hoàn tất trong 10 phút trong một tháng. Con số thực tế cần dựa trên nhu cầu và dữ liệu vận hành.

### 13.5. Error budget

Error budget thể hiện mức thất bại hoặc vi phạm mục tiêu được chấp nhận trong kỳ. Khi ngân sách gần cạn, nhóm có thể ưu tiên reliability work thay vì tăng tốc phát hành tính năng.

### 13.6. Alert fatigue

Alert cần có owner, mức độ, điều kiện clear và runbook. Tránh alert lặp cho cùng một nguyên nhân hoặc alert không dẫn đến hành động.

## 14. Phân tích lỗi và troubleshooting

Một quy trình điều tra tốt đi từ triệu chứng đến phạm vi ảnh hưởng, sau đó theo trace và log để xác định nguyên nhân.

### 14.1. Bắt đầu từ run ID

Tìm pipeline run bị lỗi bằng run ID hoặc project và thời gian. Xác nhận source revision, compiler version, trigger và environment.

### 14.2. Tìm stage thất bại

Xem stage nào thất bại đầu tiên. Các stage phía sau có thể bị SKIPPED vì dependency, không phải lỗi độc lập.

### 14.3. Mở trace

Kiểm tra thời gian từng span, retry, queue wait và lời gọi service. Tìm span có error status hoặc duration bất thường.

### 14.4. Đọc log liên quan

Lọc log theo run ID, trace ID, stage ID và diagnostic code. Đọc thông điệp đầu tiên gây lỗi và các lỗi tiếp theo có thể chỉ là hậu quả.

### 14.5. Kiểm tra artifact và cấu hình

Xác nhận compiler, generator, dependency, target profile, environment variable và artifact checksum. Một build có thể thành công nhưng deploy sai artifact.

### 14.6. So sánh run tốt và run lỗi

So sánh source revision, config, dependency lock, toolchain version, cache state và environment. Điều này giúp xác định thay đổi gây regression.

### 14.7. Xác minh sau khắc phục

Chạy lại pipeline với cùng input nếu có thể tái lập. Sau đó kiểm tra stage từng lỗi, artifact mới và deployment health. Không chỉ dựa vào trạng thái tổng thể SUCCEEDED nếu stage quan trọng bị SKIPPED ngoài ý muốn.

## 15. Quan sát hiệu năng và bottleneck

Pipeline chậm có thể do xử lý CPU, I/O, queue, network hoặc một stage phụ thuộc bên ngoài.

### 15.1. Critical path

Trong DAG, critical path là chuỗi stage quyết định thời gian hoàn tất sớm nhất của toàn pipeline. Tối ưu stage không nằm trên critical path có thể không cải thiện tổng duration.

### 15.2. Queue wait

Nếu worker ít hoặc tải tăng, pipeline có thể chờ lâu trước khi chạy. Queue wait cần được đo riêng với stage duration.

### 15.3. Cache observability

Theo dõi:
- Cache hit rate.
- Cache miss rate.
- Cache lookup duration.
- Cache invalidation.
- Cache size.
- Key/version của cache.

Cache hit cao chưa chắc tốt nếu cache stale hoặc làm sai kết quả. Cần ghi nhận tính đúng đắn của cache key.

### 15.4. Resource profiling

Metric CPU và memory cho biết mức tổng quan. Khi cần tìm nguyên nhân chi tiết, có thể dùng profiler hoặc runtime diagnostics riêng. Không nên gửi profile nặng trong mọi build.

### 15.5. Parallelism

Theo dõi số worker hoạt động, số task chờ, thời gian đồng bộ và mức độ tranh chấp tài nguyên. Tăng số worker có thể tăng throughput nhưng cũng làm tăng memory và contention.

### 15.6. Dependency latency

Compiler có thể phụ thuộc registry, schema service hoặc remote API. Span riêng cho từng lời gọi giúp phân biệt compiler chậm với dependency chậm.

### 15.7. Regression detection

So sánh duration theo compiler version, project size và stage. Cần kiểm soát các yếu tố gây nhiễu như cache warm/cold, worker type và mức tải.

## 16. Artifact provenance và build reproducibility

Observability cần trả lời artifact được tạo ra từ những đầu vào nào.

### 16.1. Artifact metadata

Một artifact manifest có thể ghi:

~~~yaml
artifactId: sales-domain-2026.11.15.42
sourceRevision: 7f31c2a
dslVersion: 3.4.0
compilerVersion: 2.8.1
generatorVersion: 1.6.2
target: production-runtime
createdAt: 2026-11-15T08:30:00Z
checksum: sha256:...
~~~

Thông tin này giúp truy nguyên và xác minh artifact.

### 16.2. Build provenance

Provenance mô tả:
- Source revision.
- Build definition.
- Toolchain.
- Dependencies.
- Build parameters.
- Worker environment.
- Artifact digest.
- Người hoặc hệ thống kích hoạt.

### 16.3. Reproducible build

Một build có thể tái lập nếu cùng source, dependency và cấu hình tạo ra artifact tương đương theo định nghĩa của hệ thống.

Để hỗ trợ:
- Pin dependency version.
- Lưu toolchain version.
- Chuẩn hóa timestamp hoặc metadata không ổn định khi phù hợp.
- Ghi generator configuration.
- Kiểm soát environment input.
- Dùng artifact checksum.

### 16.4. Artifact lineage

Một artifact có thể tạo ra artifact khác, ví dụ DSL source sinh SQL migration hoặc API schema. Lineage giúp biết output nào phụ thuộc vào input nào.

### 16.5. Deployment mapping

Deployment record cần liên kết artifact digest, environment, rollout và thời điểm. Khi runtime phát lỗi, có thể truy ngược về artifact và source revision tương ứng.

## 17. Quan sát CI/CD

CI/CD thường chạy pipeline tự động khi có commit, pull request, tag hoặc lịch.

### 17.1. Trigger metadata

Ghi loại trigger, branch, revision, pull request hoặc scheduled run. Không dùng thông tin từ branch name như dữ liệu bảo mật.

### 17.2. CI stage

CI có thể bao gồm:
- Checkout.
- Dependency restore.
- Parse và validation.
- Compile.
- Unit test.
- Integration test.
- Static analysis.
- Package.

Mỗi stage cần trạng thái và log riêng.

### 17.3. CD stage

CD có thể gồm:
- Artifact verification.
- Approval.
- Deploy.
- Health check.
- Traffic shift.
- Rollback.

Quan sát cần cho biết deployment đang ở rollout phase nào và phiên bản nào đang nhận traffic.

### 17.4. Approval và manual gate

Nếu pipeline chờ phê duyệt, trạng thái nên là BLOCKED hoặc WAITING_APPROVAL thay vì RUNNING vô hạn. Ghi actor, thời điểm và kết quả quyết định.

### 17.5. Rollback

Rollback là một hoạt động pipeline riêng. Ghi artifact trước và sau, lý do, health check và kết quả. Không xóa lịch sử deployment thất bại.

### 17.6. Environment parity

Khác biệt cấu hình giữa dev, staging và production có thể gây lỗi. Lưu config fingerprint hoặc version reference để so sánh mà không đưa secret vào telemetry.

## 18. Observability cho runtime DSL

Sau khi artifact được triển khai, runtime tiếp tục phát sinh telemetry.

### 18.1. Execution identity

Mỗi workflow execution hoặc DSL request cần execution ID. ID liên kết với artifact version, tenant hoặc business key theo chính sách bảo mật.

### 18.2. Runtime event

Các event có thể gồm:
- ProgramStarted.
- WorkflowStarted.
- StateTransitioned.
- ActionStarted.
- ActionCompleted.
- RetryScheduled.
- TimeoutTriggered.
- WorkflowCompleted.
- WorkflowFailed.

### 18.3. State transition trace

Mỗi transition nên ghi state trước, event, guard outcome, state sau, action result và duration. Guard expression có thể chứa dữ liệu nhạy cảm nên log kết quả hoặc code thay vì toàn bộ payload.

### 18.4. Dependency calls

Nếu DSL action gọi database, API hoặc message broker, tạo span con cho các dependency call. Có thể ghi operation name, duration, outcome và retry count.

### 18.5. Runtime health

Theo dõi:
- Active workflow instances.
- Event queue lag.
- Action execution duration.
- Worker saturation.
- Timeout rate.
- Retry rate.
- State duration.
- Unhandled event count.

### 18.6. Business metrics

Có thể đo số đơn hoàn tất hoặc tỷ lệ phê duyệt, nhưng cần tách business metric khỏi technical metric. Business metric cần định nghĩa rõ và tuân thủ quyền truy cập dữ liệu.

## 19. Bảo mật và quyền riêng tư của telemetry

Log, trace và metric có thể tiết lộ source code, cấu hình, thông tin khách hàng hoặc bí mật vận hành. Observability cần có chính sách dữ liệu.

### 19.1. Data minimization

Chỉ ghi những trường cần để vận hành. Không log toàn bộ DSL source, request payload hoặc context object mặc định.

### 19.2. Redaction

Mask hoặc loại bỏ:
- Access token.
- Password.
- API key.
- Connection string.
- Personal data.
- Payment data.
- Secret trong environment.

Redaction nên được áp dụng trước khi telemetry rời khỏi process có dữ liệu.

### 19.3. Access control

Quyền xem log, trace và artifact provenance có thể khác quyền xem source hoặc production data. Hãy áp dụng authorization theo project, tenant, environment và mức độ nhạy cảm.

### 19.4. Retention

Đặt thời hạn lưu theo loại dữ liệu:
- Metric tổng hợp có thể giữ lâu hơn.
- Log chi tiết có thể có retention ngắn hơn.
- Trace đầy đủ có thể được sampling và lưu theo chính sách.
- Audit record có thể có yêu cầu lưu riêng.

### 19.5. Tenant isolation

Không để query dashboard hoặc trace search trả dữ liệu tenant khác. Kiểm tra quyền ở backend, không chỉ lọc trên giao diện.

### 19.6. Telemetry integrity

Một client không đáng tin có thể gửi log giả hoặc gắn sai run ID. Service nhận telemetry cần xác thực nguồn và kiểm tra schema. Audit quan trọng cần có bảo vệ chống sửa đổi theo thiết kế hệ thống.

### 19.7. Secret trong error message

Exception có thể chứa URL, query hoặc thông tin kết nối. Trước khi hiển thị hoặc gửi log, cần loại bỏ credential và phần dữ liệu không cần thiết.

## 20. Sampling, retention và chi phí

Telemetry có chi phí lưu trữ, truyền tải, truy vấn và vận hành. Cần chọn mức chi tiết phù hợp với giá trị điều tra.

### 20.1. Log sampling

Có thể lấy mẫu log DEBUG hoặc log thành công có tần suất cao. Log ERROR quan trọng có thể được giữ đầy đủ, nhưng cần tránh lặp hàng triệu lần trong một lỗi dây chuyền.

### 20.2. Trace sampling

Head sampling quyết định lấy trace từ đầu. Tail sampling quyết định sau khi thấy kết quả, ví dụ giữ trace lỗi hoặc vượt latency threshold.

### 20.3. Metric cardinality

Giới hạn nhãn có tập giá trị hữu hạn. Không tạo metric riêng cho mỗi run, user hoặc file.

### 20.4. Retention tiers

Có thể lưu:
- Dữ liệu nóng để truy vấn nhanh trong thời gian ngắn.
- Dữ liệu lạnh để điều tra lịch sử.
- Summary dài hạn để phân tích xu hướng.

### 20.5. Adaptive detail

Khi pipeline lỗi hoặc vượt ngưỡng, có thể bật mức log chi tiết cho một run hoặc một nhóm worker. Cần tránh bật debug toàn hệ thống quá lâu.

### 20.6. Cost attribution

Có thể phân bổ chi phí theo project, stage hoặc environment bằng CPU time, memory usage, storage và network transfer. Không đưa định danh có cardinality cao vào metric nếu hệ thống metrics không phù hợp; dùng billing record hoặc log tổng hợp.

## 21. Công cụ và tiêu chuẩn tích hợp

Hệ sinh thái observability thường gồm instrumentation SDK, collector, storage và UI.

### 21.1. OpenTelemetry

OpenTelemetry cung cấp API, SDK và quy ước để tạo traces, metrics và logs. Dùng chuẩn chung giúp DSL toolchain tích hợp với nhiều backend mà không khóa vào một nhà cung cấp.

### 21.2. Collector

Collector có thể nhận telemetry, enrich resource attributes, batch, filter, redact và export sang backend. Collector giúp tách instrumentation trong compiler khỏi cấu hình lưu trữ.

### 21.3. Backend

Các backend có thể lưu:
- Metrics time series.
- Log events.
- Distributed traces.
- Profiles.
- Deployment events.

Một số nền tảng kết hợp nhiều loại dữ liệu; một số dùng hệ thống riêng.

### 21.4. Instrumentation boundary

Instrument ở ranh giới có ý nghĩa:
- Pipeline run.
- Stage.
- Compiler phase.
- External dependency call.
- Artifact operation.
- Deployment operation.
- Runtime execution.

Tránh instrument quá chi tiết khi chưa có câu hỏi vận hành cụ thể.

### 21.5. Semantic conventions

Tên span, metric và resource attribute nên theo convention chung nếu có. Điều này giúp truy vấn và dashboard tái sử dụng giữa các service.

### 21.6. Không khóa chặt backend

Application nên phát telemetry qua API hoặc protocol ổn định. Backend-specific dashboard và alert có thể được quản lý riêng, nhưng logic nghiệp vụ không nên phụ thuộc trực tiếp vào một công cụ hiển thị.

## 22. Ví dụ thiết kế pipeline observability

Giả sử một dự án DSL có pipeline:

~~~text
Resolve Dependencies
Parse
Semantic Check
Validate
Generate SQL
Run Tests
Package
Publish
Deploy to Staging
Health Check
~~~

### 22.1. Pipeline run record

~~~json
{
  "runId": "run-2026-0042",
  "project": "sales-domain",
  "sourceRevision": "7f31c2a",
  "dslVersion": "3.4.0",
  "compilerVersion": "2.8.1",
  "target": "staging",
  "status": "FAILED",
  "failedStage": "Run Tests"
}
~~~

### 22.2. Trace

~~~text
pipeline.run
  dependency.resolve       180 ms  OK
  parser                   420 ms  OK
  semantic.check           610 ms  OK
  validation               270 ms  OK
  sql.generate             350 ms  OK
  tests                   4.8 s   ERROR
    test.order-total       1.1 s  FAILED
    test.customer-filter   0.4 s  OK
  package                 SKIPPED
  publish                 SKIPPED
  deploy                  SKIPPED
~~~

### 22.3. Diagnostic

Test order-total có thể liên kết về DSL source location và generated SQL. Người phát triển xem assertion failure, trace span và log của test.

### 22.4. Dashboard

Dashboard tổng quan có thể cho thấy:
- 42 run gần nhất.
- 38 success, 4 failed.
- p95 duration là 7.2 giây.
- 3 failure nằm ở test.
- 1 failure do dependency resolution.

### 22.5. Truy nguyên artifact

Vì test thất bại, package không được tạo. Nếu package thành công ở một run khác, artifact manifest lưu source revision, compiler version, target và checksum để deployment có thể xác minh đúng đầu vào.

## 23. Kiểm thử hệ thống observability

Observability cũng cần được kiểm thử. Nếu pipeline chạy nhưng không phát telemetry hoặc phát dữ liệu sai, nhóm có thể mất khả năng điều tra khi có sự cố.

### 23.1. Instrumentation tests

Kiểm tra:
- Stage start và completion event.
- Status đúng.
- Duration không âm.
- Run ID và trace ID được gắn.
- Error status được đặt khi stage thất bại.
- Retry được ghi nhận.

### 23.2. Context propagation tests

Tạo pipeline có queue và service call. Xác minh trace context đi qua producer, message, consumer và dependency call.

### 23.3. Schema tests

Validate log và event theo schema. Thay đổi field cần có versioning hoặc migration phù hợp.

### 23.4. Failure injection

Cố ý tạo:
- Parser error.
- Dependency timeout.
- Worker crash.
- Test failure.
- Registry unavailable.
- Deployment health check failure.

Kiểm tra trạng thái, log, metric, trace và alert có phản ánh đúng tình trạng.

### 23.5. Sampling tests

Xác minh trace lỗi và latency cao được giữ theo policy, trong khi trace thành công có thể được lấy mẫu.

### 23.6. Security tests

Kiểm tra secret không xuất hiện trong log, trace, dashboard hoặc export. Kiểm tra người dùng không thể truy vấn telemetry của tenant khác.

### 23.7. Alert tests

Dùng dữ liệu giả lập để xác minh threshold, notification route, deduplication, recovery và runbook link.

### 23.8. Performance overhead

Đo chi phí instrumentation khi bật và tắt. Telemetry không nên làm pipeline chậm đáng kể hoặc gây memory pressure.

## 24. Quy trình triển khai observability cho DSL pipeline

Có thể triển khai theo các bước:

### Bước 1: Vẽ pipeline và dependency graph

Liệt kê stage, task, queue, service, artifact và runtime boundary. Xác định bước nào chạy tuần tự, song song hoặc bất đồng bộ.

### Bước 2: Định nghĩa câu hỏi vận hành

Chọn các câu hỏi cần trả lời: pipeline thất bại ở đâu, stage nào chậm, artifact từ đâu, deployment nào đang chạy và runtime nào có lỗi.

### Bước 3: Chuẩn hóa identity và schema

Định nghĩa run ID, stage ID, trace context, artifact ID, status và diagnostic schema. Tránh tạo nhiều tên field khác nhau cho cùng ý nghĩa.

### Bước 4: Instrument các ranh giới chính

Tạo span và log cho pipeline, stage, compiler phase, dependency call, package, publish, deploy và runtime execution.

### Bước 5: Chọn metric có mục đích

Bắt đầu với run count, failure count, duration, queue wait, worker saturation, artifact rate và runtime error rate. Kiểm soát cardinality.

### Bước 6: Truyền context qua async boundary

Gắn trace context vào message, job và deployment event. Kiểm thử fan-out và fan-in.

### Bước 7: Liên kết diagnostic về DSL source

Giữ source range và generated mapping. Cung cấp link từ pipeline failure đến file, dòng và diagnostic code.

### Bước 8: Xây dashboard và alert

Tạo dashboard tổng quan, theo stage, theo project và runtime. Alert theo triệu chứng và mức độ ảnh hưởng, gắn owner và runbook.

### Bước 9: Thiết lập security và retention

Mask dữ liệu, phân quyền, cô lập tenant, kiểm soát truy cập và đặt retention theo loại telemetry.

### Bước 10: Kiểm thử và cải tiến

Dùng failure injection, load test và incident review để bổ sung tín hiệu còn thiếu. Loại bỏ metric hoặc log không có người sử dụng.

## 25. Những lỗi thiết kế thường gặp

**Chỉ ghi một dòng build failed.** Người vận hành không biết stage hoặc nguyên nhân. Hãy ghi stage status, error code và link đến trace/log.

**Chỉ có log, không có metric.** Khó nhìn xu hướng và phát hiện sự suy giảm kéo dài. Hãy đo duration, failure rate, queue depth và throughput.

**Có metric nhưng không có drill-down.** Dashboard báo bất thường nhưng không thể tìm run gây ra nó. Hãy liên kết metric với log và trace qua các thuộc tính phù hợp.

**Mỗi service dùng một correlation ID riêng.** Trace bị đứt ở queue hoặc service boundary. Hãy truyền context thống nhất qua request và message.

**Dùng run ID làm metric label.** Cardinality tăng không giới hạn và làm backend metrics quá tải. Hãy giữ ID chi tiết trong log và trace.

**Không phân biệt queue wait với execution time.** Nhóm có thể tối ưu compiler trong khi bottleneck thật là thiếu worker. Hãy đo riêng hai khoảng thời gian.

**Không liên kết generated code với DSL source.** Runtime error chỉ ra file mã sinh. Hãy lưu source map và artifact metadata.

**Không ghi compiler hoặc generator version.** Khó tái hiện regression. Hãy lưu toolchain version trong run và artifact provenance.

**Log toàn bộ payload.** Có thể lộ source, secret hoặc dữ liệu cá nhân. Hãy giảm dữ liệu, mask và phân quyền.

**Alert quá nhiều.** Người vận hành bị quá tải và bỏ qua cảnh báo quan trọng. Hãy đặt alert theo triệu chứng, owner và hành động cụ thể.

**Không quan sát stage bị SKIPPED.** Pipeline có thể trông thành công dù một bước bắt buộc không chạy do cấu hình sai. Hãy ghi lý do skip và kiểm tra dependency.

**Không kiểm thử telemetry.** Instrumentation có thể mất context hoặc phát sai status mà không được phát hiện. Hãy kiểm thử trace propagation, schema và failure scenarios.

## 26. Kết luận

Quan sát pipeline giúp hiểu trạng thái, tiến độ, hiệu năng và nguyên nhân lỗi trong quá trình xây dựng, triển khai và thực thi DSL. Một hệ thống observability hữu ích kết hợp log có cấu trúc, metric, distributed trace, pipeline state, diagnostic, dashboard và alert. Các tín hiệu cần được liên kết bằng run ID, stage ID, trace context và artifact identity.

Với DSL, cần quan sát riêng từng giai đoạn như dependency resolution, parsing, semantic analysis, validation, code generation, testing, packaging, publishing, deployment và runtime. Source mapping cùng artifact provenance giúp truy nguyên lỗi từ môi trường chạy về đúng DSL source và toolchain đã tạo artifact. Security, redaction, access control, retention và cardinality cần được thiết kế ngay từ đầu để telemetry hữu ích mà không gây rò rỉ hoặc chi phí quá lớn.

Hãy bắt đầu bằng cách vẽ pipeline và xác định những câu hỏi vận hành quan trọng, sau đó instrument các ranh giới chính, chuẩn hóa context và xây dashboard có khả năng drill down. Khi mỗi lần chạy có thể được truy vết từ source đến artifact và runtime, nhóm có thể chẩn đoán sự cố nhanh hơn, phát hiện bottleneck sớm và triển khai DSL một cách đáng tin cậy hơn.

