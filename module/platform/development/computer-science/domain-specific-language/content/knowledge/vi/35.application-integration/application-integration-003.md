# Vòng đời engine

Khi một ứng dụng tích hợp một ngôn ngữ miền đặc thù (Domain-Specific Language — DSL), engine là thành phần biến định nghĩa của ngôn ngữ thành hành vi có thể thực thi. Tùy loại DSL, engine có thể parse và đánh giá biểu thức, áp dụng rule, điều phối workflow, kiểm tra schema, thực hiện truy vấn hoặc sinh kết quả. Engine thường phải được khởi tạo cùng ứng dụng, nạp cấu hình và module, chuẩn bị definition, phục vụ nhiều lần thực thi, quản lý tài nguyên và kết thúc an toàn khi ứng dụng dừng.

**Vòng đời engine** (*engine lifecycle*) mô tả các giai đoạn từ lúc tạo engine đến khi engine được đóng, cùng những trạng thái, trách nhiệm và điều kiện chuyển tiếp trong từng giai đoạn. Vòng đời có thể gồm bootstrap, cấu hình, nạp language/module/plugin, compile hoặc validate definition, publish/deploy, start, execute, pause hoặc reload, drain và shutdown. Mỗi giai đoạn cần xác định tài nguyên được sở hữu, lỗi được xử lý ra sao, trạng thái nào được phép chuyển tiếp và ứng dụng có thể gọi API nào.

Ví dụ một ứng dụng Java nhúng DSL workflow có thể thực hiện:

~~~java
EngineConfig config = EngineConfig.builder()
    .definitionDirectory(Path.of("workflows"))
    .workerCount(8)
    .build();

try (WorkflowEngine engine = WorkflowEngine.create(config)) {
    engine.loadDefinitions();
    engine.start();

    ProcessInstance instance =
        engine.startProcess("OrderFulfillment", input);

    ProcessResult result = engine.await(instance.id());
}
~~~

Đây là API minh họa. Một engine thực tế có thể dùng dependency injection, service container, asynchronous API hoặc runtime phân tán. Điều quan trọng là ứng dụng hiểu rõ thời điểm engine sẵn sàng, definition nào đã được nạp, instance nào đang chạy, ai sở hữu tài nguyên và cách dừng mà không làm mất công việc đang xử lý.

Vòng đời engine không đồng nghĩa với vòng đời của một process instance. Engine có thể tồn tại nhiều ngày và phục vụ hàng nghìn instance; mỗi instance có thể hoàn thành trong vài mili giây hoặc chờ external event nhiều giờ. Engine lifecycle quản lý runtime service và tài nguyên dùng chung, còn instance lifecycle quản lý một lần thực thi cụ thể. Phân biệt hai cấp này giúp thiết kế tích hợp, shutdown, scaling và recovery chính xác.

## 1. Engine là gì trong kiến trúc tích hợp DSL?

Engine là runtime component hiểu semantics của một DSL và cung cấp các thao tác để ứng dụng sử dụng language đó. Engine có thể chạy trong cùng process với ứng dụng hoặc hoạt động như một service riêng.

Một engine thường chịu trách nhiệm:

- Nạp language definition, schema, rule set, workflow hoặc module.
- Kiểm tra cú pháp, type, reference và constraint.
- Compile hoặc chuẩn bị definition thành dạng có thể thực thi.
- Cung cấp runtime context và API để bắt đầu execution.
- Điều phối task, đánh giá rule hoặc chạy interpreter.
- Quản lý cache, worker, scheduler, connection và resource.
- Ghi nhận execution state, event, diagnostic và metric.
- Hỗ trợ reload, version pinning, pause, resume và recovery nếu được thiết kế.
- Giải phóng tài nguyên khi đóng.

### Engine và DSL definition

DSL definition là mô tả logic hoặc cấu trúc. Engine là thành phần diễn giải hoặc thực thi mô tả đó. Definition có thể tồn tại trong file, database, registry hoặc artifact đã build.

### Engine và application

Application là hệ thống host cung cấp authentication, API, persistence, domain service và giao diện. Engine thường được ứng dụng gọi như một capability. Nó không nhất thiết sở hữu toàn bộ business data hoặc quyết định mọi vấn đề về transaction.

### Engine và runtime instance

Một engine có thể phục vụ nhiều execution context. Ví dụ workflow engine tạo process instance; rule engine tạo decision execution; expression engine tạo evaluation session. Mỗi execution có input, context, state và kết quả riêng.

### Engine và compiler

Compiler biến source DSL thành intermediate representation hoặc executable artifact. Engine có thể chứa compiler hoặc sử dụng compiler ở giai đoạn build/deploy. Không phải engine nào cũng compile; interpreter có thể đánh giá definition trực tiếp. Vòng đời cần mô tả rõ compilation diễn ra khi build, khi startup hay khi request đến.

## 2. Các mô hình triển khai engine

Có nhiều cách đặt engine trong hệ thống. Lựa chọn ảnh hưởng đến latency, isolation, scaling, deployment và ownership.

| Mô hình | Đặc điểm | Phù hợp khi |
|---|---|---|
| Embedded engine | Engine chạy trong process của ứng dụng. | Cần latency thấp và tích hợp trực tiếp với object/service. |
| In-process shared engine | Một engine instance được nhiều component trong ứng dụng dùng chung. | Definition và runtime resource có thể chia sẻ an toàn. |
| Per-tenant engine | Mỗi tenant có engine hoặc runtime partition riêng. | Cần isolation hoặc cấu hình khác biệt mạnh. |
| Sidecar | Engine chạy cạnh ứng dụng trong container/pod riêng. | Muốn tách process nhưng giữ giao tiếp gần. |
| Remote engine service | Engine chạy như service độc lập qua API/message. | Cần scale, deploy và vận hành độc lập. |
| Build-time engine | Compile DSL thành artifact trước khi ứng dụng chạy. | Cần validation sớm và giảm runtime compilation. |
| Hybrid | Compile trước, runtime engine thực thi artifact và quản lý state. | Cần kết hợp hiệu năng và tính linh hoạt. |

### Embedded engine

Embedded engine giúp gọi trực tiếp bằng method API, chia sẻ transaction hoặc domain object khi framework hỗ trợ. Tuy nhiên, engine có thể ảnh hưởng memory, thread và shutdown của ứng dụng. Lỗi hoặc memory leak trong engine cũng nằm cùng process boundary.

### Remote engine

Remote engine tạo ranh giới dịch vụ rõ hơn. Application gửi command hoặc request và nhận result/event. Đổi lại cần xử lý network failure, timeout, authentication, serialization, retry và distributed tracing.

### Build-time và runtime

Một số DSL có thể được compile trong CI thành artifact đã kiểm tra. Runtime chỉ load artifact đã publish. Cách này giảm chi phí compile khi startup và tránh để source DSL chưa tin cậy đi thẳng vào production. Một số use case vẫn cần dynamic definition và runtime compilation, nhưng cần kiểm soát rõ quyền và giới hạn.

### Không có một mô hình phù hợp cho mọi DSL

Expression evaluator đơn giản có thể nhúng trong ứng dụng; workflow engine có persistence và scheduler lớn có thể phù hợp chạy như service; schema validator có thể được sinh thành code và chạy ngay tại API boundary. Nên chọn theo yêu cầu lifecycle, isolation, availability và scale.

## 3. Vòng đời tổng thể

Một vòng đời engine tổng quát có thể được mô tả như sau:

~~~mermaid
stateDiagram-v2
    [*] --> NEW
    NEW --> INITIALIZING
    INITIALIZING --> CONFIGURED
    CONFIGURED --> LOADING
    LOADING --> READY
    READY --> STARTING
    STARTING --> RUNNING
    RUNNING --> RELOADING
    RELOADING --> RUNNING
    RUNNING --> DRAINING
    DRAINING --> STOPPING
    STOPPING --> TERMINATED
    INITIALIZING --> FAILED
    LOADING --> FAILED
    STARTING --> FAILED
    RUNNING --> FAILED
    FAILED --> STOPPING
    TERMINATED --> [*]
~~~

Các trạng thái có thể khác nhau theo implementation, nhưng cần xác định ý nghĩa và API hợp lệ ở từng trạng thái.

| Trạng thái | Ý nghĩa |
|---|---|
| NEW | Object engine được tạo nhưng chưa khởi tạo. |
| INITIALIZING | Đang chuẩn bị dependency và resource cơ bản. |
| CONFIGURED | Cấu hình đã được kiểm tra và chấp nhận. |
| LOADING | Đang nạp definition, module, plugin hoặc artifact. |
| READY | Engine đã chuẩn bị xong nhưng chưa nhận execution mới. |
| STARTING | Đang bật worker, scheduler, listener hoặc service. |
| RUNNING | Engine sẵn sàng phục vụ operation. |
| RELOADING | Đang thay đổi cấu hình hoặc definition theo policy. |
| DRAINING | Ngừng nhận công việc mới và chờ công việc đang chạy. |
| STOPPING | Đang đóng worker và giải phóng resource. |
| TERMINATED | Engine đã đóng và không thể sử dụng lại. |
| FAILED | Một lỗi lifecycle khiến engine không thể tiếp tục hoạt động bình thường. |

### Trạng thái engine khác trạng thái instance

Engine RUNNING có thể phục vụ instance đang WAITING, RUNNING, COMPLETED hoặc FAILED. Engine DRAINING có thể còn instance chạy nhưng không nhận instance mới. Không nên gộp các trạng thái này thành một cờ active.

### Terminal state

TERMINATED thường là trạng thái cuối. Nếu cần tạo engine mới, ứng dụng nên tạo instance engine mới thay vì tái sử dụng object đã đóng, trừ khi API công bố rõ khả năng restart.

### Failed initialization

Nếu initialization thất bại giữa chừng, engine cần rollback những resource đã tạo. Một engine ở FAILED không nên trả về như thể đã sẵn sàng.

## 4. Bootstrap và khởi tạo

Bootstrap là giai đoạn ứng dụng tạo engine và cung cấp các dependency cần thiết.

Các công việc thường gồm:

1. Đọc cấu hình ứng dụng hoặc environment.
2. Tạo engine builder/factory.
3. Kiểm tra phiên bản runtime và compatibility.
4. Chuẩn bị classloader hoặc module resolver.
5. Khởi tạo dependency injection và service registry.
6. Tạo cache, executor, scheduler hoặc connection provider nếu engine sở hữu chúng.
7. Nạp secret/config reference cần thiết.
8. Đăng ký listener, metrics và tracing integration.
9. Chuyển engine sang trạng thái configured/ready theo lifecycle contract.

### Factory và builder

Factory hoặc builder giúp gom các lựa chọn cấu hình và xác thực trước khi tạo engine.

~~~java
EngineConfig config = EngineConfig.builder()
    .engineName("orders")
    .workerCount(8)
    .maxConcurrentExecutions(200)
    .definitionSource(new FileDefinitionSource(Path.of("dsl")))
    .build();

RuleEngine engine = RuleEngine.create(config);
~~~

API trên minh họa. Builder nên trả lỗi cấu hình có cấu trúc, ví dụ worker count âm hoặc definition source thiếu, thay vì để lỗi xuất hiện ngẫu nhiên trong lần execution đầu tiên.

### Constructor có nên làm toàn bộ startup?

Constructor nên tạo object ở trạng thái dễ hiểu. Nếu khởi tạo cần I/O, network hoặc load nhiều artifact, một factory hoặc lifecycle method tường minh thường giúp xử lý lỗi và quan sát startup tốt hơn.

### Idempotent initialization

Nếu framework có thể gọi lifecycle callback nhiều lần, initialization cần được bảo vệ để không tạo hai scheduler, hai listener hoặc hai connection pool. Có thể dùng state transition có đồng bộ và kiểm tra trạng thái trước khi thực hiện.

### Partial initialization cleanup

Nếu bước thứ tư thất bại sau khi đã tạo executor và cache, engine cần đóng những resource đã tạo. Cleanup phải chạy theo thứ tự ngược với thứ tự acquisition khi dependency yêu cầu.

## 5. Cấu hình engine

Engine config xác định cách engine hoạt động trong môi trường cụ thể.

Các nhóm cấu hình thường gặp:

- Engine identity và environment.
- Nguồn definition và registry.
- Worker count, queue size và concurrency limit.
- Timeout, retry và backoff policy.
- Cache size, TTL và invalidation policy.
- Persistence provider và transaction boundary.
- Classloader/module/plugin policy.
- Security principal và authorization provider.
- Metrics, logging và tracing.
- Shutdown timeout và drain behavior.
- Resource quotas và tenant isolation.

### Phân biệt config tĩnh và config động

Config tĩnh thường chỉ đọc lúc startup, ví dụ thread pool topology hoặc storage provider. Config động có thể reload khi engine đang chạy, ví dụ một số threshold hoặc feature flag. Mỗi field cần được phân loại rõ.

### Validation cấu hình

Kiểm tra kiểu, miền giá trị, dependency và xung đột. Ví dụ maxConcurrentExecutions không thể nhỏ hơn 1; retry max attempts phải hợp lệ; timeout cần đơn vị; definition source phải có quyền đọc.

### Defaults

Default giúp giảm boilerplate nhưng cần được ghi rõ. Một thay đổi default giữa các phiên bản engine có thể làm runtime behavior đổi dù ứng dụng không sửa config.

### Externalized configuration

Không hard-code credential hoặc endpoint nhạy cảm. Dùng secret manager/config provider, và chỉ giữ secret trong memory trong thời gian cần thiết.

### Configuration snapshot

Ghi config version hoặc fingerprint đã được áp dụng để có thể giải thích engine chạy với cấu hình nào. Không log secret trong snapshot.

## 6. Nạp language, module, plugin và extension

Engine có thể cần nạp các thành phần mở rộng trước khi dùng DSL.

Ví dụ module có thể cung cấp:
- Grammar/parser hoặc schema definition.
- Type và function.
- Rule/action implementation.
- Workflow task handler.
- Serializer/deserializer.
- Custom validator.
- Plugin tích hợp database hoặc message broker.

### Module registry

Registry ánh xạ module identity/version đến artifact hoặc implementation. Resolver cần xác định dependency và thứ tự nạp.

### Dependency graph

Nếu module A phụ thuộc B, B phải được resolve trước khi A được khởi tạo. Resolver cần phát hiện missing dependency, version conflict và cycle không được hỗ trợ.

### Plugin lifecycle

Plugin có thể có các hook initialize, start, stop hoặc close. Engine phải định nghĩa plugin được khởi tạo theo thứ tự nào, plugin nào phụ thuộc plugin nào và xử lý ra sao nếu một plugin lỗi.

### Classloader isolation

Trong môi trường Java, classloader riêng có thể giúp cô lập version dependency hoặc unload plugin. Nhưng classloader leak có thể xảy ra nếu thread, static reference hoặc listener vẫn giữ class từ plugin sau khi unload.

### Extension point

Nên công bố extension API ổn định. Plugin không nên phụ thuộc vào internal class hoặc lifecycle implementation không được hỗ trợ vì nâng cấp engine có thể làm hỏng tích hợp.

### Trust boundary

Plugin là code thực thi trong process nếu embedded. Chỉ nạp artifact được tin cậy, có provenance và quyền phù hợp. Một file DSL dữ liệu không giống một plugin chứa code tùy ý.

## 7. Nạp và kiểm tra definition DSL

Sau khi engine có language/runtime module, nó có thể nạp definition.

Definition có thể đến từ:
- File trong package hoặc repository.
- Database hoặc configuration store.
- Schema/rule registry.
- Artifact được build trong CI.
- API quản trị có xác thực.
- Một source provider do ứng dụng triển khai.

### Parse

Parser chuyển source text thành syntax tree hoặc model. Nếu DSL là projectional/model-based, bước load có thể deserialize model thay vì parse văn bản.

### Name resolution

Resolver tìm type, function, symbol, import và reference. Cần pin dependency để cùng definition không resolve thành nội dung khác giữa hai lần chạy.

### Type checking

Type checker kiểm tra biểu thức và quan hệ dữ liệu. Ví dụ phép cộng cần operand tương thích; action cần đúng argument type.

### Semantic validation

Một definition có thể đúng cú pháp nhưng sai semantics: workflow không có terminal path, rule priority mâu thuẫn, schema reference không resolve hoặc action không được phép dùng trong context.

### Static analysis

Engine/tooling có thể phát hiện unreachable step, unused variable, circular dependency, rule overlap hoặc function call không an toàn.

### Diagnostics

Diagnostic nên có code, severity, source location và message. Không nên chỉ trả một exception chung khiến người author không biết sửa ở đâu.

### Không đưa definition lỗi vào active registry

Definition chỉ nên được publish/activate sau khi parse, resolve và validate đạt policy. Có thể giữ version lỗi ở trạng thái draft để người author sửa, nhưng runtime không nên chọn nó làm active version.

## 8. Compile, prepare và cache executable artifact

Sau khi definition hợp lệ, engine có thể chuẩn bị dạng thực thi.

Các lựa chọn:
- Interpreter chạy AST/model trực tiếp.
- Compile sang bytecode hoặc JVM class.
- Compile sang intermediate representation.
- Tạo execution plan.
- Precompute dependency graph hoặc index.
- Sinh validator hoặc code adapter.
- Tối ưu expression và rule network.

### Compile time và startup time

Compile có thể diễn ra trong build pipeline, khi engine startup hoặc lúc definition được publish. Compile-time artifact giảm latency request nhưng cần compatibility giữa compiler và runtime.

### Prepared definition

Engine có thể giữ một immutable prepared definition trong registry. Execution mới lấy reference đến version đó, giúp không phải parse/compile mỗi lần.

### Cache key

Cache key nên bao gồm definition identity/version, compiler version, language version, dependency fingerprint và config ảnh hưởng semantics. Nếu thiếu một thành phần, engine có thể dùng nhầm artifact cũ.

### Cache invalidation

Khi definition mới được publish, cache của version cũ không nhất thiết bị xóa ngay nếu instance đang chạy vẫn cần nó. Cần reference counting, TTL hoặc lifecycle quản lý artifact theo active execution.

### Warm-up

Một số engine cần warm-up JIT, load class, precompute rule network hoặc mở connection. Warm-up có thể giảm latency request đầu nhưng cần giới hạn thời gian và resource.

### Compilation failure

Compile error phải được gắn với definition version và source location. Nếu đang thay version hiện tại, lỗi compile version mới không nên làm mất bản active ổn định trước đó.

## 9. Ready và start engine

READY có thể biểu thị engine đã nạp và chuẩn bị xong definition, còn RUNNING biểu thị engine đã bắt đầu phục vụ operation.

Start có thể:
- Khởi chạy worker pool.
- Bắt đầu scheduler.
- Subscribe message broker.
- Mở HTTP/RPC endpoint.
- Khôi phục persisted instance.
- Kích hoạt timer và subscription.
- Bắt đầu health reporting.

### Startup ordering

Dependency phải sẵn sàng trước thành phần sử dụng nó. Ví dụ persistence provider cần hoạt động trước recovery; recovery cần hoàn tất hoặc đạt readiness policy trước khi nhận request mới.

### Readiness và liveness

Readiness cho biết engine có thể nhận workload hay không. Liveness cho biết process/engine có còn hoạt động. Một engine có thể live nhưng chưa ready vì đang load definition hoặc recover state.

### Startup timeout

Startup cần giới hạn thời gian và báo thành phần nào đang chậm. Nếu application server coi engine chưa ready, traffic mới không nên được gửi vào.

### Startup recovery

Với workflow engine, startup có thể khôi phục instance, timer và pending task. Cần tránh thực thi lại side effect đã hoàn tất trước crash.

## 10. Engine runtime và execution context

Khi engine chạy, ứng dụng gửi yêu cầu thực thi. Mỗi request cần một execution context riêng.

Execution context có thể chứa:
- Execution ID.
- Definition ID và version.
- Input và variable binding.
- Tenant/security principal.
- Correlation và trace context.
- Deadline/cancellation token.
- Transaction hoặc unit-of-work reference.
- Resource quota.
- Output, diagnostic và state reference.

### Context isolation

Không dùng mutable shared context giữa các execution. Một biến của request này không được rò sang request khác khi engine phục vụ đồng thời.

### Context propagation

Khi engine gọi service hoặc tạo child task, cần truyền correlation ID, tenant, security context và cancellation policy theo quy tắc. Không nên truyền toàn bộ thread-local state qua asynchronous boundary mà không kiểm soát.

### Input validation

Validate input trước khi thực thi DSL. Dữ liệu ngoài ứng dụng là untrusted, ngay cả khi caller dùng SDK được sinh từ schema.

### Execution result

Result cần phân biệt business outcome, runtime failure, validation error, timeout, cancellation và pending/waiting state. Không nên biểu diễn mọi trường hợp bằng null hoặc boolean.

### Synchronous và asynchronous API

Synchronous call có thể trả result ngay khi execution hoàn tất. Asynchronous API trả execution handle để caller truy vấn hoặc subscribe. Với workflow dài, asynchronous model thường phù hợp hơn việc giữ HTTP request mở.

## 11. Quản lý worker, scheduler và queue

Engine thực thi công việc qua worker hoặc scheduler cần quản lý tài nguyên có giới hạn.

### Worker pool

Worker pool giới hạn số task chạy đồng thời. Số worker cần dựa trên CPU-bound hay I/O-bound workload, memory và downstream capacity.

### Queue

Queue giữ task đang chờ. Queue phải có giới hạn hoặc backpressure để tránh memory tăng vô hạn khi producer nhanh hơn consumer.

### Scheduler

Scheduler quản lý timer, delayed retry, deadline và task định kỳ. Nó cần lưu timer bền vững nếu process phải sống qua restart.

### Task dispatch

Dispatcher chọn worker hoặc executor phù hợp. Task có thể cần capability, tenant, priority hoặc affinity.

### Queue saturation

Khi queue đầy, engine cần policy rõ: reject, block, persist, shed low-priority work hoặc scale consumer. Không nên âm thầm nhận vô hạn.

### Worker failure

Nếu worker chết giữa task, lease/heartbeat hoặc visibility timeout có thể giúp phát hiện và reassign. Task có side effect cần idempotency hoặc recovery contract.

### Executor ownership

Nếu ứng dụng truyền executor vào engine, cần xác định engine có quyền shutdown executor đó không. Thông thường resource do caller cung cấp vẫn thuộc caller, trừ khi ownership được chuyển giao rõ ràng.

## 12. Tạo và quản lý execution instance

Engine runtime có thể tạo nhiều instance từ một definition.

### Start operation

Start operation thường cần:
- Definition ID/version hoặc policy chọn version.
- Input payload.
- Caller identity.
- Business key/idempotency key nếu cần.
- Correlation metadata.
- Deadline hoặc execution options.

### Idempotent start

Client có thể retry request khi timeout nhưng không biết engine đã tạo instance chưa. Idempotency key giúp tránh tạo duplicate instance cho cùng một yêu cầu logic.

### Instance state

Engine lưu current state, current step/scope, variable hoặc reference, pending wait và execution history.

### Instance isolation

Một lỗi trong instance không nên làm engine hoặc instance khác crash nếu execution boundary được thiết kế đúng. Resource quota giúp giới hạn một tenant hoặc process tiêu thụ quá nhiều.

### Long-running instance

Instance có thể chờ nhiều ngày. Không nên giữ một Java thread hoặc HTTP connection suốt thời gian chờ. Persist state rồi resume khi event/timer đến.

### Instance termination

Instance có thể complete, fail, cancel hoặc timeout. Engine cần lưu kết quả và giải phóng resource liên quan mà vẫn giữ history theo retention policy.

## 13. Definition versioning và pinning

Engine đang chạy có thể đồng thời phục vụ nhiều version definition.

Ví dụ:
- Instance A bắt đầu với Workflow v4.
- Version v5 được publish.
- Instance B bắt đầu với Workflow v5.
- Instance A tiếp tục theo v4 trừ khi có migration được hỗ trợ.

### Pin version lúc start

Mỗi instance nên lưu definition version cụ thể. Nếu chỉ lưu tên definition và luôn lấy latest, một instance có thể thay đổi semantics giữa chừng.

### Active version

Registry có thể có một version được đánh dấu active cho các execution mới. Active version là metadata chọn version; nó không nhất thiết xóa version cũ.

### Retention version

Chỉ được xóa artifact version cũ khi không còn instance, replay, audit hoặc consumer nào cần nó theo policy. Cần theo dõi reference và retention.

### Migration instance

Migration một instance đang chạy sang version mới là thao tác phức tạp. Nó có thể cần map step cũ sang step mới, chuyển variable, xử lý task đang chờ và xác định compensation. Không nên xem migration chỉ là thay con trỏ definition version.

### Reproducibility

Cần lưu engine version, language version, plugin/dependency fingerprint và config semantics liên quan để giải thích hoặc replay execution lịch sử.

## 14. Reload và hot deployment

Một ứng dụng có thể cần cập nhật DSL definition mà không restart toàn engine.

### Reload strategy

Có thể:
- Stop-the-world: ngừng nhận execution, nạp version mới rồi tiếp tục.
- Rolling replacement: tạo runtime generation mới và chuyển traffic.
- Versioned registry: publish version mới, execution mới dùng version đó; execution cũ giữ version cũ.
- Dynamic interpreter: cập nhật definition registry mà không compile lại toàn bộ runtime.

### Atomic switch

Nếu publish một nhóm definition phụ thuộc nhau, cần kích hoạt nguyên tử hoặc qua một release manifest. Tránh trạng thái một module đã mới nhưng module phụ thuộc vẫn cũ.

### In-flight execution

Cần chọn policy:
- Instance hiện tại tiếp tục version cũ.
- Instance được yêu cầu resume theo version mới nếu tương thích.
- Drain instance trước khi switch.
- Chỉ migrate các instance đủ điều kiện.

### Cache generation

Cache mới cần tách generation hoặc version key để execution cũ không vô tình lấy artifact mới. Cache cũ chỉ được giải phóng khi không còn reference.

### Rollback

Rollback active definition version có thể đơn giản nếu version cũ còn lưu và runtime tương thích. Nhưng rollback code hoặc schema database có thể phức tạp hơn; cần kiểm tra compatibility và state migration.

### Reload failure

Nếu version mới lỗi validation hoặc compile, engine nên giữ active version cũ và báo deployment failure. Không nên để registry ở trạng thái nửa cập nhật.

## 15. Pause, resume và maintenance mode

Một engine có thể cần tạm dừng nhận hoặc thực thi workload.

### Pause intake

Ngừng nhận execution mới nhưng tiếp tục công việc đang chạy. Hữu ích trước deploy hoặc bảo trì.

### Pause scheduling

Giữ task ở queue và không dispatch task mới. Task đang chạy có thể tiếp tục hoặc bị cancel tùy policy.

### Suspend instance

Một instance cụ thể được lưu state và dừng cho đến khi resume. Đây là hành động ở instance lifecycle, không phải engine lifecycle.

### Maintenance mode

Engine có thể vào maintenance mode để từ chối một số operation hoặc chỉ cho phép read/health endpoint.

### Resume

Resume cần kiểm tra dependency, definition version, timer và lease trước khi tiếp tục. Không nên resume một instance khi runtime artifact hoặc external operation state chưa sẵn sàng.

### Pause không phải shutdown

Pause giữ resource và state để tiếp tục; shutdown giải phóng resource và kết thúc lifecycle. API nên thể hiện rõ khác biệt.

## 16. Graceful shutdown và drain

Shutdown là giai đoạn engine ngừng hoạt động. Với engine phục vụ workload, đóng ngay có thể làm mất task hoặc để side effect ở trạng thái không rõ.

Một shutdown an toàn thường gồm:

1. Chuyển engine sang DRAINING.
2. Từ chối hoặc chuyển hướng execution mới.
3. Dừng nhận message mới hoặc ngừng pull task.
4. Chờ task đang chạy trong thời hạn.
5. Persist state/checkpoint của execution có thể tiếp tục.
6. Cancel hoặc timeout task vượt grace period theo policy.
7. Flush event, log và telemetry quan trọng.
8. Đóng listener, scheduler, worker và connection do engine sở hữu.
9. Chuyển engine sang TERMINATED.

### Drain timeout

Grace period cần giới hạn. Nếu không có timeout, shutdown có thể treo vô hạn vì một task không kết thúc.

### Forced shutdown

Khi hết thời gian, engine có thể interrupt worker hoặc đóng process. Task cần idempotency/recovery để lần chạy sau xử lý an toàn.

### Stop accepting work

Đầu tiên cần ngừng nhận work mới. Nếu vẫn nhận trong khi drain, engine có thể không bao giờ rỗng.

### Persist pending work

Pending task cần được giữ bền vững. Nếu task chỉ tồn tại trong in-memory queue, shutdown có thể làm mất chúng.

### Resource cleanup

Đóng resource theo ownership: engine đóng pool do nó tạo; không tự đóng database connection hoặc executor do application truyền vào nếu ownership chưa được chuyển.

### Shutdown hook

Application framework có thể gọi lifecycle callback khi context đóng. Shutdown hook nên ngắn, idempotent và có timeout; không dựa vào hook như cơ chế duy nhất bảo đảm dữ liệu bền vững.

## 17. Close, dispose và ownership tài nguyên

Engine thường sở hữu nhiều resource có lifecycle khác nhau.

| Resource | Có thể do engine sở hữu? | Cách đóng |
|---|---|---|
| Worker executor | Có | Shutdown, await termination, interrupt nếu cần. |
| Scheduler | Có | Hủy timer mới, flush/persist schedule, shutdown. |
| HTTP/message listener | Có | Ngừng nhận request/message và close. |
| Connection pool | Tùy cấu hình | Close nếu engine tạo hoặc được giao ownership. |
| Cache | Có | Ngừng load mới, giải phóng reference. |
| Classloader/plugin | Có | Unregister listener, stop thread, clear references. |
| Application service | Thường không | Để application/container quản lý. |
| External client do caller truyền | Theo ownership contract | Không tự đóng nếu caller còn dùng. |

### AutoCloseable

Trong Java, implement AutoCloseable giúp dùng try-with-resources và làm ownership rõ ràng.

~~~java
try (RuleEngine engine = RuleEngine.create(config)) {
    engine.start();
    engine.evaluate("Eligibility", input);
}
~~~

### Idempotent close

Gọi close nhiều lần nên không gây lỗi hoặc giải phóng resource hai lần. State transition cần đồng bộ khi nhiều thread cùng gọi shutdown.

### Close timeout

Có thể cung cấp close(Duration timeout) hoặc shutdownGracefully(timeout) để application kiểm soát thời gian dừng.

### Leak detection

Có thể ghi warning nếu engine bị bỏ quên chưa close hoặc plugin thread còn sống sau shutdown. Tuy nhiên, warning không thay thế ownership rõ ràng.

## 18. Error handling trong lifecycle

Lỗi có thể xảy ra ở từng giai đoạn và cần cách xử lý phù hợp.

| Giai đoạn | Ví dụ lỗi | Hành vi cần xác định |
|---|---|---|
| Bootstrap | Thiếu config | Fail fast, báo field/path lỗi. |
| Module loading | Dependency không resolve | Không publish definition lỗi. |
| Parse/compile | Syntax/type error | Trả diagnostic theo source location. |
| Start | Broker/storage unavailable | Retry có giới hạn hoặc fail readiness. |
| Execute | Business/runtime error | Gắn lỗi với execution và policy retry. |
| Reload | Artifact không hợp lệ | Giữ active version ổn định. |
| Drain | Task không kết thúc | Áp grace timeout và recovery policy. |
| Close | Resource cleanup lỗi | Tiếp tục đóng resource khác, tổng hợp lỗi. |

### Fail fast và retry

Lỗi cấu hình hoặc dependency không tồn tại thường không tự hết; fail fast giúp phát hiện sớm. Lỗi transient như network timeout có thể retry với backoff và jitter.

### Exception boundary

Không để exception của một execution làm hỏng worker pool hoặc engine process. Worker cần bắt và phân loại lỗi tại boundary phù hợp, đồng thời bảo toàn diagnostic.

### Partial failure

Engine phân tán có thể có một số partition hoặc worker lỗi trong khi phần khác còn hoạt động. Health model nên thể hiện degraded state thay vì chỉ RUNNING/FAILED.

### Startup rollback

Nếu startup thất bại, đóng resource đã tạo và giữ lỗi gốc cùng suppressed cleanup exceptions. Không che lỗi ban đầu bằng exception cleanup cuối cùng.

### Close failures

Shutdown nên cố gắng đóng mọi resource dù một close operation lỗi. Cuối cùng có thể trả aggregate exception hoặc ghi report để operator xử lý.

## 19. Tích hợp lifecycle với dependency injection và application framework

Trong ứng dụng enterprise, engine thường được quản lý bởi container.

### Dependency injection

Engine có thể được đăng ký như singleton bean/service. Các component khác nhận engine qua constructor injection, giúp dependency rõ và dễ test.

~~~java
@Component
final class OrderService {
    private final WorkflowEngine workflowEngine;

    OrderService(WorkflowEngine workflowEngine) {
        this.workflowEngine = workflowEngine;
    }
}
~~~

### Singleton hay prototype

Một engine chia sẻ thường là singleton vì nó chứa worker pool và registry dùng chung. Một execution context hoặc session thường là per-request/per-execution. Không nên tạo engine mới cho mỗi request nếu startup tốn kém và resource cần chia sẻ.

### Lifecycle callback

Framework có thể gọi initialize, start, stop hoặc destroy. Cần map rõ callback của framework với engine lifecycle và tránh start hai lần.

### Configuration properties

Bind config có kiểu vào EngineConfig và validate lúc startup. Không truyền một map tùy ý xuống mọi thành phần nếu có thể định nghĩa typed configuration.

### Circular dependency

Nếu engine cần application service, còn application service lại cần engine, có thể tạo vòng dependency. Có thể dùng port/interface, lazy provider hoặc event boundary để tách.

### Application readiness

Readiness của ứng dụng có thể phụ thuộc engine đã ready và definition cần thiết đã được nạp. Health endpoint nên phân biệt liveness với readiness.

## 20. Tích hợp engine qua API hoặc remote service

Khi engine chạy riêng, application tương tác qua network contract.

### Client lifecycle

Client SDK cũng có lifecycle: tạo connection pool, configure timeout, authentication, retry, start background refresh và close. Client close không đồng nghĩa remote engine bị shutdown.

### Request timeout

Timeout phía client không chứng minh remote execution đã dừng. Với operation tạo instance, client có thể không biết request đã được xử lý hay chưa; idempotency key và query theo operation ID giúp giải quyết.

### Retry policy

Retry chỉ an toàn khi operation idempotent hoặc có idempotency key. Không retry mù quáng một lệnh gây side effect như charge payment.

### Connection management

HTTP/gRPC client nên reuse connection và giới hạn pool. Không tạo client mới cho mỗi request nếu library yêu cầu close hoặc quản lý thread.

### Remote engine shutdown

Application client thường không có quyền shutdown remote engine. Việc đó thuộc deployment/orchestration plane hoặc admin API được bảo vệ riêng.

### Contract versioning

Client và server có thể nâng cấp độc lập. Cần version API, schema compatibility và capability negotiation nếu client có thể kết nối nhiều engine version.

## 21. Multi-tenancy và engine lifecycle

Một engine dùng chung có thể phục vụ nhiều tenant. Lifecycle và resource cần được quản lý theo isolation boundary.

### Shared engine, isolated context

Engine dùng chung code và worker nhưng mỗi execution có tenant context, quota và data scope riêng. Mọi cache key, query và event cần chứa tenant identity phù hợp.

### Per-tenant configuration

Tenant có thể dùng rule/schema version hoặc feature khác nhau. Cần policy xác định tenant được chọn version nào và ai có quyền thay đổi.

### Per-tenant engine

Một số trường hợp yêu cầu engine riêng cho từng tenant. Cách này tăng isolation nhưng tốn memory, worker và startup overhead.

### Fairness

Một tenant không nên chiếm hết worker hoặc queue. Có thể áp quota, concurrency limit và weighted scheduling.

### Tenant offboarding

Khi tenant bị xóa, cần xác định xử lý active instance, definition, cache, event history và retention. Không nên close shared engine chỉ vì một tenant ngừng sử dụng.

## 22. Security trong engine lifecycle

Engine có thể nạp definition, plugin và thực thi logic. Vì vậy, lifecycle là một phần của security boundary.

### Authentication và authorization

Chỉ principal có quyền mới được load/publish definition, start execution, xem result hoặc điều khiển engine. Quyền admin lifecycle như reload, drain và shutdown nên tách khỏi quyền execute.

### Definition trust

DSL có thể chỉ là data, nhưng một số DSL cho phép gọi function, plugin hoặc script. Cần xác định khả năng thực thi và trust level. Không chạy source không tin cậy với quyền process đầy đủ.

### Sandboxing

Nếu cho phép user-authored logic, cân nhắc giới hạn function, resource, time, memory và network access. Sandbox cần dựa trên cơ chế thực thi có bảo đảm; chỉ kiểm tra tên function không đủ.

### Resource exhaustion

Definition có thể tạo recursion sâu, regex tốn kém, query phức tạp hoặc vòng lặp dài. Engine cần execution budget, timeout, memory/resource quota và cancellation.

### Secret lifecycle

Secret chỉ được lấy khi cần, giới hạn scope, không đưa vào compiled artifact hoặc diagnostic nếu không cần. Khi rotate secret, cần biết execution hiện tại dùng version nào.

### Audit

Ghi ai tạo engine configuration, ai publish definition, ai reload, ai start/cancel execution và ai shutdown. Audit event cần identity, timestamp và target version.

### Plugin permissions

Plugin có thể truy cập file, network hoặc database. Cần allowlist và phân quyền rõ; plugin không nên tự động thừa hưởng mọi quyền của application nếu không cần.

## 23. Performance và capacity planning

Lifecycle decisions ảnh hưởng throughput và latency.

### Startup time

Đo thời gian bootstrap, module load, parse, compile, warm-up và recovery. Startup chậm có thể ảnh hưởng autoscaling và rolling deployment.

### Execution latency

Tách queue wait, dispatch, DSL evaluation, external service call và persistence. Nếu chỉ đo tổng latency, khó xác định bottleneck.

### Throughput

Đo số execution/second, task/second và event/second. Cần gắn với workload mix và definition complexity.

### Memory

Theo dõi prepared definitions, cache, execution context, queue, event buffers và classloader. Definition version cũ có thể chiếm memory nếu instance dài hạn còn tham chiếu.

### Concurrency limit

Tăng worker count không luôn tăng throughput; downstream service hoặc database có thể trở thành bottleneck. Cần capacity limit theo dependency.

### Backpressure

Khi producer nhanh hơn consumer, engine cần giảm nhận work, queue bền vững hoặc reject có kiểm soát. Backpressure tốt giúp bảo vệ hệ thống khỏi memory exhaustion.

### Cache policy

Cache definition và compiled artifact có thể cải thiện latency nhưng cần bounded size, eviction và invalidation rõ ràng.

### Warm-up và readiness

Không nên đánh dấu ready trước khi engine hoàn thành những bước bắt buộc. Nếu warm-up optional, có thể nhận traffic ở chế độ degraded và theo dõi latency đầu tiên.

## 24. Health check và readiness

Health endpoint giúp orchestrator và operator biết engine có thể phục vụ hay không.

### Liveness

Liveness trả lời process còn sống và event loop/critical thread có hoạt động không. Liveness check quá sâu có thể gây restart liên tục khi một dependency tạm thời chậm.

### Readiness

Readiness xác nhận engine đã load definition cần thiết, kết nối dependency bắt buộc và có khả năng nhận workload.

### Startup probe

Startup probe cho phép engine có thời gian khởi tạo lâu trước khi liveness check bắt đầu áp dụng.

### Dependency health

Một dependency optional bị lỗi có thể làm một capability degraded nhưng không nhất thiết làm toàn engine unready. Health model nên theo capability.

### Health không phải execution progress

Health báo trạng thái dịch vụ; progress báo trạng thái instance. Một engine healthy có thể có instance stuck do business wait; một engine degraded có thể vẫn hoàn thành một số execution.

## 25. Observability cho lifecycle

Cần quan sát lifecycle transition, không chỉ request cuối.

### Structured logs

Log nên có engine ID, runtime generation, definition version, instance ID, lifecycle state và correlation ID. Tránh ghi payload/secret nhạy cảm.

### Metrics

Các metrics hữu ích:
- Engine startup duration.
- Time spent in each lifecycle state.
- Active execution count.
- Worker utilization.
- Queue depth và wait time.
- Definition load/compile failures.
- Reload success/failure.
- Drain duration và forced termination count.
- Resource pool usage.
- Execution success/failure/timeout rate.
- Event processing lag.

### Distributed tracing

Trace nối application request, engine API, execution, task dispatch và external service. Cần propagation context qua thread pool và message queue.

### Lifecycle events

Có thể phát event EngineReady, DefinitionPublished, EngineDraining hoặc EngineTerminated để control plane và monitoring phản ứng.

### Correlation

Một request start có thể dẫn đến nhiều task và external call. Correlation ID giúp tìm toàn bộ trace mà không dựa vào message text.

### Alerting

Alert có thể dựa trên engine không ready, startup failure, reload failure, queue saturation, drain quá lâu hoặc worker heartbeat mất. Tránh alert chỉ vì engine đang WAITING hợp lệ.

## 26. Nâng cấp engine và compatibility

Nâng engine version có thể thay đổi parser, interpreter, scheduler, persistence format hoặc plugin API.

### Engine version

Mỗi deployment nên ghi engine build/version. Execution history cần tham chiếu engine version đã thực thi nếu cần replay hoặc audit.

### Language version

Language version xác định semantics của DSL. Engine version mới có thể hỗ trợ nhiều language version; cần compatibility matrix.

### Persistence format

Nếu runtime state serialization thay đổi, engine mới cần đọc được state cũ hoặc có migration. Không nên deploy version mới trước khi xác nhận compatibility với persisted instance.

### Plugin compatibility

Plugin cần khai báo API version hoặc range tương thích. Load-time check nên từ chối plugin không tương thích với diagnostic rõ.

### Rolling upgrade

Trong rolling upgrade, nhiều engine version có thể chạy đồng thời. Message/event contract và persisted state phải tương thích trong thời gian overlap.

### Blue-green deployment

Có thể dựng engine generation mới, kiểm tra readiness, chuyển traffic rồi drain generation cũ. Cần kiểm soát instance ownership để không có hai engine cùng thực thi một task.

### Rollback

Rollback binary không tự động rollback state hoặc schema đã ghi. Cần kiểm tra database migration, event format và execution state compatibility.

## 27. Engine lifecycle và transaction boundary

Engine có thể thực thi DSL tương tác với transaction của application.

### Shared transaction

Nếu engine và application dùng chung transaction manager, một số operation có thể commit cùng nhau. Điều này phù hợp với xử lý ngắn trong cùng database nhưng cần hiểu giới hạn khi có external side effect.

### Engine-managed transaction

Engine có thể mở transaction riêng cho state update, event log hoặc task claim. Cần xác định commit boundary và isolation level.

### Long-running workflow

Không giữ database transaction mở suốt một workflow kéo dài. Mỗi step hoặc state transition thường cần transaction ngắn và checkpoint bền vững.

### Outbox/inbox

Khi cập nhật state và phát event, transactional outbox giúp tránh trạng thái database commit nhưng event không được publish. Consumer inbox/deduplication giúp xử lý event lặp.

### Compensation thay rollback transaction

Với side effect ở nhiều hệ thống, không thể rollback một transaction phân tán tùy ý. Workflow có thể dùng saga/compensation để tạo hành động bù.

### Transaction ownership

Application và engine cần thống nhất ai mở, commit và rollback transaction. Không nên để cả hai cùng quản lý cùng một transaction một cách mơ hồ.

## 28. DSL có thể khai báo lifecycle policy

Một DSL tích hợp ứng dụng có thể mô tả một số chính sách vòng đời, nhưng cần phân biệt declaration với runtime control.

Ví dụ cú pháp minh họa:

~~~text
engine OrdersEngine {
    definitions from registry "commerce-workflows";
    workerPool {
        minWorkers = 4;
        maxWorkers = 16;
        queueCapacity = 500;
    }

    execution {
        defaultTimeout = 30 minutes;
        maxConcurrent = 200;
        retryPolicy = transientFailures;
    }

    lifecycle {
        startup = validateAndWarm;
        reload = versioned;
        shutdown = drain;
        drainTimeout = 45 seconds;
    }
}
~~~

Khai báo này có thể được compile thành EngineConfig hoặc deployment descriptor. Một số thuộc tính như worker count là runtime config; một số như definition source là deployment config; một số như shutdown policy được áp dụng khi ứng dụng đóng.

### Tách lifecycle policy và process logic

Process DSL mô tả workflow nghiệp vụ. Engine DSL hoặc application config mô tả cách runtime được triển khai. Không nên trộn các chi tiết như pool size vào từng workflow nếu chúng thuộc vận hành chung.

### Policy precedence

Có thể có global default, environment override và per-engine override. Cần xác định precedence và giới hạn việc tenant/user ghi đè cấu hình bảo mật hoặc resource quota.

### Config schema

Lifecycle config nên có schema riêng, typed field, default, unit, validation và version. Điều này giúp lỗi cấu hình được phát hiện trước khi engine start.

## 29. Thiết kế API lifecycle cho engine

API lifecycle nên thể hiện state transition và ownership rõ ràng.

Một interface Java minh họa:

~~~java
public interface ManagedEngine extends AutoCloseable {
    EngineState state();

    void initialize();

    void loadDefinitions();

    void start();

    CompletionStage<Void> drain(Duration timeout);

    void reload(DefinitionBundle bundle);

    @Override
    void close();
}
~~~

Interface trên chỉ minh họa ý tưởng; một engine có thể gộp initialize/load hoặc dùng asynchronous methods.

### State query

state() cho biết trạng thái hiện tại. Có thể cung cấp state details như startup phase, active generation và readiness reason.

### Start

Start cần có semantics rõ nếu gọi nhiều lần: no-op, return error hoặc chờ lần start đang chạy. Không để behavior tùy thuộc race.

### Reload

Reload nên trả version/generation mới và diagnostic nếu thất bại. Caller cần biết reload đã activate hay chỉ load thành công.

### Drain

Drain có thể trả completion stage cho biết khi nào engine đã ngừng nhận việc mới và xử lý xong work đang chạy.

### Close

Close là terminal operation và nên idempotent. Nếu cần chờ, có thể có async close hoặc awaitTermination API.

### Capability discovery

Engine có thể công bố capabilities như hot reload, pause, resume, durable execution, multi-tenancy hoặc dynamic plugin loading. Application không nên giả định mọi implementation đều hỗ trợ mọi tính năng.

## 30. Testing engine lifecycle

Lifecycle cần được kiểm thử như state machine và resource ownership, không chỉ kiểm thử kết quả một execution.

### State transition tests

Kiểm tra transition hợp lệ, từ chối operation ở trạng thái sai và terminal behavior.

### Initialization failure tests

Giả lập lỗi ở từng bước bootstrap và xác nhận resource đã tạo được cleanup.

### Start/stop idempotency tests

Gọi start hoặc close nhiều lần, kiểm tra không tạo duplicate worker hoặc double-close.

### Reload tests

Kiểm tra version mới hợp lệ, version lỗi, dependency conflict, in-flight execution và rollback active pointer.

### Drain tests

Bắt đầu execution dài, gọi drain, xác nhận request mới bị từ chối/chuyển hướng và task hiện tại được hoàn tất hoặc checkpoint theo policy.

### Recovery tests

Restart engine tại các điểm khác nhau: trước side effect, sau side effect nhưng trước event commit, sau checkpoint và khi đang chờ external callback.

### Concurrency tests

Nhiều thread cùng start, reload hoặc close; xác nhận state transition và resource không bị race.

### Resource leak tests

Kiểm tra thread, connection, listener, classloader và temporary file sau close.

### Integration tests

Chạy engine trong application context thật, kiểm tra dependency injection, health/readiness, API và graceful shutdown.

### Compatibility tests

Đọc definition/persisted state được tạo bởi engine version trước và xác nhận migration/compatibility contract.

## 31. Ví dụ tích hợp engine trong Spring-style application

Một ứng dụng có thể đăng ký engine như singleton managed component.

~~~java
@Configuration
class EngineConfiguration {

    @Bean(destroyMethod = "close")
    WorkflowEngine workflowEngine(
            EngineProperties properties,
            DefinitionSource definitionSource) {

        EngineConfig config = EngineConfig.builder()
            .workerCount(properties.workerCount())
            .definitionSource(definitionSource)
            .drainTimeout(properties.drainTimeout())
            .build();

        WorkflowEngine engine = WorkflowEngine.create(config);
        engine.initialize();
        engine.loadDefinitions();
        engine.start();
        return engine;
    }
}
~~~

Ví dụ này minh họa lifecycle. Trong production, có thể cần dùng lifecycle abstraction của framework để startup failure được xử lý và shutdown order được xác định. Nếu method tạo bean ném lỗi sau khi resource đã tạo, cần bảo đảm cleanup được gọi.

Service sử dụng engine:

~~~java
@Service
final class OrderApplicationService {
    private final WorkflowEngine engine;

    OrderApplicationService(WorkflowEngine engine) {
        this.engine = engine;
    }

    ProcessHandle fulfill(Order order) {
        return engine.startProcess(
            "FulfillOrder",
            Map.of("orderId", order.id())
        );
    }
}
~~~

Service không tạo engine cho mỗi request. Nó dùng instance do application container quản lý. Execution handle định danh process instance, còn engine tiếp tục điều phối task bất đồng bộ.

## 32. Ví dụ lifecycle cho remote engine client

Khi engine chạy ở service riêng, application chỉ quản lý client.

~~~java
public final class EngineClient implements AutoCloseable {
    private final HttpClient httpClient;
    private final URI endpoint;

    public EngineClient(URI endpoint) {
        this.endpoint = endpoint;
        this.httpClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .build();
    }

    public ProcessHandle start(
            String definitionId,
            String idempotencyKey,
            byte[] requestBody) {
        // Send authenticated request and map response.
        throw new UnsupportedOperationException("Illustrative API");
    }

    @Override
    public void close() {
        // Release client-owned resources where applicable.
    }
}
~~~

Client lifecycle gồm tạo connection infrastructure, cấu hình auth/timeouts, gọi API, xử lý retry và close. Nó không được phép suy ra remote engine đã shutdown chỉ vì client đóng.

### Client retry

Nếu request start timeout, client cần truy vấn theo idempotency key hoặc operation ID trước khi gửi lại. Nếu không, có thể tạo duplicate process instance.

### Client-side cancellation

Hủy HTTP request không nhất thiết hủy process đang chạy. Muốn cancel process, client cần gọi control API với quyền phù hợp.

## 33. Những lỗi thiết kế thường gặp

**Khởi tạo engine cho mỗi request.** Điều này lặp startup, tạo nhiều worker/cache và tăng memory. Engine chia sẻ thường nên được quản lý ở application lifecycle nếu implementation cho phép.

**Không phân biệt engine với instance.** Shutdown engine không đồng nghĩa mọi instance đã hoàn tất; instance có thể cần persist và resume.

**Đánh dấu ready quá sớm.** Engine có thể chưa load definition, recover state hoặc kết nối dependency bắt buộc. Readiness cần phản ánh capability thực tế.

**Để constructor làm I/O không kiểm soát.** Lỗi khó quan sát và cleanup khó hơn. Nên có lifecycle/bootstrap contract rõ.

**Không cleanup khi initialization lỗi.** Partial startup để lại thread, listener hoặc connection và làm restart không ổn định.

**Nạp definition mới trực tiếp lên active registry.** Nếu compile thất bại giữa chừng, engine có thể ở trạng thái nửa mới nửa cũ. Cần prepare rồi atomic activate.

**Không pin definition version cho execution.** Instance đang chạy có thể thay semantics sau reload. Cần version pinning hoặc migration có chủ đích.

**Close ngay khi ứng dụng nhận signal.** Task đang chạy hoặc pending work có thể mất. Cần drain, checkpoint và shutdown timeout.

**Không phân biệt resource ownership.** Engine có thể đóng executor hoặc client do application sở hữu, làm hỏng thành phần khác.

**Retry mọi operation.** Retry non-idempotent side effect có thể tạo giao dịch hoặc process duplicate. Cần idempotency và retry classification.

**Dùng một pool không giới hạn.** Queue và memory có thể tăng vô hạn khi downstream chậm. Cần bounded queue và backpressure.

**Không quản lý plugin classloader.** Thread hoặc static reference có thể giữ classloader cũ và gây memory leak sau reload.

**Không kiểm soát dynamic DSL execution.** User-authored definition có thể tiêu thụ CPU/memory hoặc gọi capability không được phép. Cần sandbox và execution budget.

**Dùng liveness thay readiness.** Dependency chưa sẵn sàng có thể làm request thất bại dù process vẫn sống. Cần health probe đúng mục đích.

**Không kiểm thử shutdown/recovery.** Hệ thống có thể chạy tốt khi bình thường nhưng mất task khi deploy hoặc crash. Cần test ở các điểm failure thực tế.

## 34. Quy trình thiết kế vòng đời engine

Một quy trình triển khai có thể gồm:

1. **Xác định engine responsibility:** engine parse, compile, evaluate, orchestrate hay validate loại DSL nào.
2. **Chọn deployment model:** embedded, shared, per-tenant, sidecar, remote hoặc hybrid.
3. **Định nghĩa state machine:** trạng thái engine, transition hợp lệ, failure và terminal state.
4. **Thiết kế bootstrap:** factory, config binding, dependency và partial cleanup.
5. **Thiết kế module loading:** registry, dependency resolution, plugin trust và classloader.
6. **Xác định definition pipeline:** parse, resolve, type-check, semantic validation và compile.
7. **Thiết kế active registry:** immutable version, atomic activation, cache và rollback.
8. **Định nghĩa runtime context:** execution identity, input, tenant, security, deadline và cancellation.
9. **Quản lý worker/resource:** bounded pool, scheduler, queue, backpressure và ownership.
10. **Thiết kế execution persistence:** state, event, checkpoint, idempotency và recovery.
11. **Định nghĩa reload/migration:** in-flight policy, version pinning và compatibility.
12. **Thiết kế shutdown:** drain, grace timeout, persist pending work và close order.
13. **Tích hợp application framework:** DI, readiness, health, transaction và configuration.
14. **Thiết kế security/observability:** permission, sandbox, audit, metrics, logs và trace.
15. **Kiểm thử lifecycle:** startup failure, concurrency, reload, drain, recovery và resource leak.

## 35. Checklist vận hành engine

Trước khi đưa engine vào môi trường production, cần xác nhận:

- Engine có owner và deployment model rõ không?
- State machine có định nghĩa transition và terminal state không?
- Configuration được validate trước khi start không?
- Dependency/module/plugin có version và trust policy không?
- Definition được parse, resolve, type-check và validate trước activation không?
- Compile artifact có cache key chứa đủ version/fingerprint không?
- Active version có thể switch nguyên tử và rollback không?
- Execution có context isolation, tenant và security principal không?
- Worker, queue và scheduler có giới hạn tài nguyên không?
- Retry có phân loại transient/permanent và idempotency không?
- Persisted instance có checkpoint và recovery contract không?
- In-flight execution được xử lý thế nào khi reload?
- Shutdown có ngừng intake, drain và timeout không?
- Resource ownership giữa engine và application có rõ không?
- Readiness và liveness có phân biệt không?
- Logs, metrics và traces có correlation ID không?
- Plugin và DSL user-authored có sandbox/permission phù hợp không?
- API lifecycle có authorization và audit không?
- Startup, reload, shutdown và recovery đã được integration test chưa?
- Có đo startup duration, queue depth, execution latency và drain time không?

## 36. Kết quả cần có sau khi thiết kế vòng đời engine

Một thiết kế engine lifecycle hoàn chỉnh cho tích hợp ứng dụng thường cung cấp:

- **Deployment model:** embedded, remote, sidecar, per-tenant hoặc hybrid.
- **Lifecycle state machine:** bootstrap, configured, loading, ready, running, reloading, draining, stopping và terminated.
- **Bootstrap contract:** factory, configuration validation, dependency initialization và partial cleanup.
- **Module/plugin lifecycle:** registry, dependency graph, trust, classloader và extension API.
- **Definition pipeline:** parse, resolve, validate, compile, prepare và atomic activation.
- **Version/cache policy:** immutable artifact, cache key, invalidation, pinning, rollback và migration.
- **Runtime context:** execution identity, input, tenant, security, deadline và cancellation.
- **Resource management:** worker, scheduler, queue, connection, ownership, backpressure và close.
- **Execution persistence:** instance state, event, checkpoint, idempotency và recovery.
- **Operational lifecycle:** readiness, pause, resume, reload, drain và graceful shutdown.
- **Integration contract:** dependency injection, remote client, transaction boundary và API control.
- **Security/observability:** authorization, sandbox, audit, logs, metrics, tracing và health.
- **Validation strategy:** startup, concurrency, reload, shutdown, recovery, compatibility và resource leak tests.

Vòng đời engine là hợp đồng vận hành giữa DSL runtime và ứng dụng tích hợp nó. Thiết kế tốt xác định rõ engine được tạo, cấu hình, nạp module, kiểm tra definition, chuẩn bị và đưa vào phục vụ như thế nào; đồng thời quản lý execution context, worker, cache, version và tài nguyên theo ownership cụ thể. Khi reload, engine cần giữ tính nhất quán giữa definition đang active và execution đang chạy; khi shutdown, nó phải ngừng nhận việc mới, drain hoặc persist công việc đang xử lý rồi giải phóng resource có kiểm soát. Kết hợp state machine rõ ràng, version pinning, idempotency, recovery, readiness, observability và kiểm thử lifecycle giúp engine tích hợp ổn định trong ứng dụng thay vì chỉ hoạt động trong một lần chạy thử đơn giản.

