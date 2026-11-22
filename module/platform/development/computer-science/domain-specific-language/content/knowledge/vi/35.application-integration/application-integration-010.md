# Kiểm thử tích hợp host

## Kiểm thử tích hợp host trong DSL là gì?

Một ngôn ngữ chuyên miền (domain-specific language, DSL) thường không hoạt động độc lập. Nó được nhúng vào một ứng dụng host để mô tả rule nghiệp vụ, truy vấn, workflow, template, policy, cấu hình hoặc thao tác tự động hóa. Ứng dụng host chịu trách nhiệm cung cấp dữ liệu, dịch vụ, quyền truy cập, vòng đời thực thi và cách hiển thị kết quả.

**Kiểm thử tích hợp host (host integration testing)** là hoạt động kiểm tra DSL khi nó được kết nối với ứng dụng host và các thành phần thật mà DSL phụ thuộc. Mục tiêu là xác nhận toàn bộ ranh giới tích hợp hoạt động đúng: DSL được nạp, biên dịch hoặc diễn giải đúng; context được truyền chính xác; host API được gọi đúng; dữ liệu được ánh xạ đúng; lỗi được chuyển thành kết quả phù hợp; và các quy tắc bảo mật, transaction, lifecycle được giữ nguyên.

Ví dụ, một ứng dụng thương mại điện tử nhúng DSL để xác định điều kiện giảm giá:

~~~text
RULE "VIP discount"
WHEN customer.segment == "VIP"
 AND order.total >= 1000000
THEN
  discount = order.total * 0.10
  APPLY discount
~~~

Unit test của interpreter có thể chứng minh phép so sánh và phép nhân hoạt động đúng. Nhưng chỉ host integration test mới xác nhận được những vấn đề như:

- Host có truyền đúng customer và order vào DSL context không?
- Giá trị tiền có được chuyển sang kiểu Decimal với scale phù hợp không?
- DSL có nhìn thấy dữ liệu mới nhất trong transaction hiện tại không?
- Action APPLY có gọi đúng service giảm giá không?
- Host có rollback nếu action thất bại không?
- Người dùng không có quyền có thể chạy rule này hay không?
- Kết quả DSL có được ánh xạ đúng vào response của ứng dụng không?

Một host integration test thường chạy nhiều thành phần thật cùng nhau, nhưng vẫn có thể thay thế một số dependency bên ngoài bằng test double có kiểm soát. Điều quan trọng là kiểm tra đúng hợp đồng giữa DSL runtime và host application.

## Host application và ranh giới tích hợp

Host application là ứng dụng sở hữu hoặc nhúng DSL runtime. Nó có thể là web service, desktop application, backend nghiệp vụ, nền tảng automation, IDE, hệ thống báo cáo hoặc một service điều phối.

Kiến trúc tổng quát:

~~~text
User / External Client
        |
        v
Host Application
  - Request handling
  - Authentication
  - Domain services
  - Persistence
  - Transactions
        |
        v
DSL Integration Layer
  - DSL loader
  - Compiler / Interpreter
  - Context builder
  - Host API bindings
  - Type conversion
  - Result mapping
        |
        v
DSL Runtime
  - Evaluation
  - Rule / Query / Workflow execution
  - Diagnostics
        |
        v
Host adapters and services
  - Repository
  - Domain API
  - Event publisher
  - Clock
  - Authorization service
~~~

Ranh giới tích hợp thường nằm giữa DSL runtime và các khả năng mà host cung cấp. Các điểm cần kiểm tra gồm:

- Nạp source DSL và xác định version.
- Resolve module, import và dependency.
- Biên dịch hoặc tạo execution plan.
- Xây dựng context từ request và domain object.
- Chuyển kiểu giữa host và DSL.
- Đăng ký function, operator, action hoặc plugin.
- Truy cập repository và external service.
- Xử lý transaction và side effect.
- Kiểm soát quyền thực thi.
- Chuyển diagnostics và exception về host.
- Quản lý cache, reload và shutdown.
- Theo dõi metrics, logs và trace.

Không phải mọi test đều cần khởi động toàn bộ ứng dụng. Một test có thể dùng host test harness để khởi tạo đúng integration layer và một số service thật. Phạm vi test nên đủ rộng để kiểm tra hợp đồng đang quan tâm nhưng vẫn có thể chạy lặp lại và chẩn đoán khi thất bại.

## Phân biệt unit test, host integration test, contract test và end-to-end test

Các cấp kiểm thử có mục tiêu khác nhau.

| Loại test | Phạm vi | Ví dụ |
|---|---|---|
| Unit test | Một hàm hoặc thành phần nhỏ | Evaluator xử lý biểu thức AND |
| DSL integration test | Các thành phần nội bộ DSL phối hợp | Parser, resolver và interpreter cùng xử lý một file |
| Host integration test | DSL được nối với host services | Rule gọi repository thật trong host test application |
| Contract test | Hai phía tuân thủ interface đã định nghĩa | Host adapter trả đúng kiểu và lỗi theo contract |
| End-to-end test | Luồng từ client đến hệ thống triển khai | Gửi HTTP request, chạy DSL, ghi DB và nhận response |
| System test | Hệ thống hoàn chỉnh trong môi trường gần production | Kiểm tra ứng dụng cùng broker, database và identity provider |

Host integration test thường tập trung vào boundary giữa DSL và host. Nó có thể khởi động một phần host application, nhưng không nhất thiết phải triển khai mọi thành phần bên ngoài như một end-to-end test.

### Khi nào cần host integration test?

Nên có host integration test khi:
- DSL được nhúng trong ứng dụng và phụ thuộc vào domain services.
- Host tự xây context hoặc bind function vào runtime.
- Có chuyển đổi kiểu giữa DSL và host language.
- DSL có thể đọc hoặc ghi dữ liệu qua repository.
- Action của DSL tạo side effect trong ứng dụng.
- Quyền truy cập phụ thuộc user, tenant hoặc request.
- Host hỗ trợ hot reload hoặc cache compiled module.
- Lỗi DSL cần được ánh xạ sang API error hoặc domain error.
- Version của DSL runtime có thể khác version host adapter.

Nếu một lỗi chỉ có thể xuất hiện khi hai thành phần giao tiếp, unit test riêng từng thành phần có thể không phát hiện được.

## Xác định test boundary và mục tiêu

Trước khi viết test, cần xác định boundary nào đang được kiểm tra và điều gì được xem là hành vi đúng.

Ví dụ, với một DSL rule engine:
- Input boundary: source text, rule ID và domain context.
- Compilation boundary: parser/compiler nhận source và trả compiled artifact hoặc diagnostics.
- Runtime boundary: host gọi evaluate với context và execution options.
- Service boundary: DSL gọi function hoặc action do host đăng ký.
- Data boundary: host repository đọc hoặc ghi dữ liệu.
- Output boundary: runtime result được host chuyển thành domain response.
- Security boundary: authorization và capability được áp dụng.

Một test case tốt nêu rõ:
1. Host state ban đầu.
2. DSL source hoặc compiled definition.
3. Principal và execution context.
4. Các service hoặc adapter tham gia.
5. Hành động được thực hiện.
6. Kết quả mong đợi trong DSL runtime.
7. Kết quả mong đợi ở host, database hoặc message boundary.

Không nên chỉ assert rằng một method đã được gọi. Cần kiểm tra kết quả quan sát được tại boundary có ý nghĩa: dữ liệu được lưu đúng, event được phát đúng, quyền được áp dụng và trạng thái host nhất quán.

## Thiết kế host test harness

Test harness là thành phần khởi tạo môi trường cần thiết để chạy host integration test. Nó giúp các test dùng cùng cách cấu hình và giảm lỗi do setup không nhất quán.

Một harness có thể cung cấp:

~~~text
HostTestHarness
  startHost()
  configureDslRuntime()
  registerHostBindings()
  createTestPrincipal()
  createTenantContext()
  seedDomainData()
  executeDsl()
  inspectHostState()
  captureEvents()
  stopHost()
~~~

Các method chỉ là mô hình khái niệm. API thực tế phụ thuộc framework của host.

### Khởi tạo host thật ở mức cần thiết

Nếu mục tiêu là kiểm tra dependency injection, configuration binding hoặc application lifecycle, nên khởi tạo application context thật trong test. Nếu chỉ cần kiểm tra một adapter, có thể tạo adapter qua test fixture và dùng repository test.

Tránh tạo một harness quá giả lập đến mức bỏ qua chính integration layer cần kiểm tra.

### Test configuration

Host có thể đăng ký DSL runtime bằng configuration file, dependency injection module hoặc plugin registry. Test cần dùng cấu hình tương đương production ở những điểm quan trọng:
- Runtime version.
- Module search path.
- Function registry.
- Type mapping.
- Security policy.
- Cache options.
- Transaction manager.
- Serialization settings.

Có thể thay endpoint bên ngoài bằng test endpoint, nhưng không nên thay cấu hình binding bằng một implementation khác với production nếu mục tiêu là kiểm tra binding.

### Lifecycle

Harness cần đóng host context, thread pool, database connection, file watcher và executor sau test. Nếu không, test có thể rò rỉ thread hoặc giữ port khiến các lần chạy sau thất bại.

### Cô lập test

Mỗi test nên có dữ liệu và namespace riêng. Có thể dùng transaction rollback, database schema riêng, tenant riêng hoặc unique test ID. Cách cô lập cần phù hợp với hành vi cần kiểm tra; rollback không thể thay thế nếu test cần quan sát commit thật hoặc event được phát sau commit.

## Kiểm thử nạp và biên dịch DSL trong host

Host thường chịu trách nhiệm tìm source DSL, chọn version, nạp module và gọi compiler hoặc interpreter.

Các trường hợp cần kiểm tra:

- Source được tìm đúng theo module ID.
- Include/import được resolve trong module namespace.
- Encoding và newline được xử lý nhất quán.
- Compiler nhận đúng language version.
- Schema và symbol registry của host được cung cấp.
- Compile error được chuyển thành diagnostics.
- Compiled artifact được cache theo đúng dependency.
- Source thay đổi làm cache invalidation.
- Module không hợp lệ không được đưa vào runtime registry.
- Host shutdown không để compiler task chạy nền.

Ví dụ test:

~~~text
Given:
  Host application đã khởi tạo DSL runtime
  Module "pricing" được đăng ký trong test workspace
  Rule "vip-discount" có source hợp lệ

When:
  Host load module "pricing"

Then:
  Module được compile thành công
  Rule có thể được resolve theo ID
  Runtime registry chứa đúng version
  Không có diagnostic error
~~~

### Compile tại startup và compile khi cần

Một số host compile toàn bộ DSL khi khởi động. Một số khác compile lazy khi rule được gọi lần đầu. Test cần xác nhận đúng policy:

- Lỗi compile có làm host startup thất bại không?
- Module lỗi có làm các module khác không dùng được không?
- Lazy compilation có được đồng bộ khi nhiều request gọi cùng lúc không?
- Compiled artifact có được tái sử dụng không?
- Khi source đổi, request đang chạy dùng version cũ hay mới?

### Dependency và module resolution

Một module có thể import function, type hoặc module khác. Host cần đăng ký đúng dependency graph và version. Test nên có trường hợp dependency không tồn tại, version không tương thích và cycle import nếu DSL có quy tắc cấm cycle.

### Cache invalidation

Nếu cache chỉ dựa trên tên file, thay đổi schema hoặc host function registry có thể không làm compiled artifact được tạo lại. Test nên thay đổi từng dependency có ảnh hưởng rồi xác nhận cache key hoặc invalidation hoạt động đúng.

## Kiểm thử context giữa host và DSL

Context là dữ liệu và khả năng mà host cung cấp cho một lần thực thi DSL. Đây là một trong những boundary quan trọng nhất.

Ví dụ context:

~~~text
ExecutionContext
  principal
  tenant
  request
  domainObjects
  services
  clock
  locale
  cancellationToken
  executionLimits
~~~

### Đúng dữ liệu và đúng scope

Test cần xác nhận context chứa đúng object và đúng scope:
- User hiện tại.
- Tenant hiện tại.
- Request hoặc correlation ID.
- Entity được yêu cầu.
- Các service được phép truy cập.
- Locale và timezone.
- Clock hoặc timestamp.
- Cancellation và resource limits.

Không nên đưa toàn bộ application container vào DSL context nếu DSL chỉ cần một số interface cụ thể. Context quá rộng làm tăng coupling và mở rộng quyền ngoài ý muốn.

### Tenant isolation

Với host đa tenant, test phải xác nhận rule của tenant A không đọc hoặc sửa dữ liệu tenant B. Tenant identity nên được lấy từ authenticated host context, không lấy từ một field tự khai báo trong DSL source.

Có thể tạo hai tenant có dữ liệu tương tự nhưng khác ID, chạy cùng rule với từng context và xác nhận kết quả không lẫn dữ liệu.

### Context snapshot

Nếu dữ liệu thay đổi trong lúc DSL đang chạy, cần biết evaluation dùng snapshot nào. Có thể dùng immutable context snapshot hoặc transaction-bound context. Test nên xác nhận một lần evaluation không đọc nửa dữ liệu trước và nửa dữ liệu sau khi host cập nhật.

### Context propagation bất đồng bộ

Nếu DSL action tạo task nền hoặc gọi async service, context như trace ID, tenant, principal và cancellation cần được truyền theo contract. Không nên truyền toàn bộ security token vào task nền nếu task chỉ cần một capability hẹp.

## Kiểm thử host API bindings và function registry

Host thường cung cấp function hoặc action để DSL tương tác với miền ứng dụng.

Ví dụ:

~~~text
HOST_FUNCTION customer.isActive(customerId)
HOST_FUNCTION inventory.available(productId)
HOST_ACTION order.reserve(productId, quantity)
~~~

Function thường trả dữ liệu và nên có semantics rõ về purity. Action tạo side effect cần có contract về quyền, transaction và idempotency.

### Function resolution

Test cần xác nhận:
- Function name được resolve đúng.
- Overload được chọn theo kiểu tham số.
- Return type được ánh xạ đúng.
- Optional hoặc nullable value được biểu diễn đúng.
- Function không được đăng ký thì tạo diagnostic hoặc runtime error theo policy.
- Function cùng tên từ module khác không va chạm ngoài ý muốn.

### Type conversion

Host language và DSL có thể dùng mô hình kiểu khác nhau. Ví dụ:
- Integer rộng và integer hẹp.
- Decimal và floating point.
- Timestamp có timezone và timestamp không timezone.
- Enum và string.
- Optional, nullable và missing.
- Collection mutable và immutable.
- Domain object và DSL record.

Test nên kiểm tra boundary values, overflow, precision, null, Unicode và serialization round trip khi có liên quan.

Đặc biệt với tiền tệ, không nên chuyển Decimal sang floating point nếu điều đó làm mất precision. Với thời gian, cần xác định timezone và cách xử lý daylight saving.

### Exception mapping

Host function có thể ném exception. Runtime cần chuyển exception thành lỗi DSL có cấu trúc, đồng thời giữ nguyên cause để log hoặc debug.

Không nên trả stack trace hoặc internal class name cho end user nếu đó là thông tin nội bộ. Host có thể cung cấp error code, message an toàn và correlation ID.

### Function purity và side effects

Nếu function được khai báo pure, test cần xác nhận nó không thay đổi host state. Nếu function đọc dữ liệu ngoài, metadata có thể đánh dấu non-deterministic hoặc external dependency để optimizer/cache không sử dụng sai.

Action có side effect cần được kiểm tra riêng về retry, duplicate invocation và rollback.

## Kiểm thử truy cập dữ liệu và transaction

DSL thường đọc hoặc ghi dữ liệu qua repository hoặc host service. Test cần xác nhận dữ liệu được nhìn thấy và thay đổi theo transaction model của host.

### Read path

Kiểm tra:
- Query dùng đúng tenant và authorization filter.
- Mapping field đúng.
- Null và missing được phân biệt.
- Lazy-loaded data không gây lỗi sau khi transaction đóng.
- Pagination hoặc streaming không làm mất record.
- Kết quả có ordering đúng khi contract yêu cầu.

### Write path

Kiểm tra:
- Validation trước khi ghi.
- Field được phép sửa.
- Entity version và optimistic locking.
- Constraint violation.
- Duplicate request.
- Rollback khi action thất bại.
- Audit metadata.
- Event được phát theo commit semantics.

### Transaction boundary

Một execution có thể chạy trong transaction host hoặc tự quản lý transaction. Contract cần xác định:
- Một DSL invocation có transaction riêng không?
- Nhiều action dùng cùng transaction không?
- Có nested transaction hoặc savepoint không?
- Action gọi external API có nằm trong transaction không?
- Khi evaluation fail, host rollback phần nào?
- Event được publish trước hay sau commit?

Ví dụ test:

~~~text
Given:
  Order có trạng thái Draft
  Host transaction đang hoạt động

When:
  DSL reserve inventory rồi cập nhật order
  Action thứ hai thất bại

Then:
  Order vẫn ở trạng thái Draft
  Inventory reservation được rollback
  Không có OrderConfirmed event được publish
~~~

Nếu external service không hỗ trợ transaction chung, cần kiểm tra compensation hoặc outbox pattern thay vì giả định database rollback sẽ đảo ngược side effect bên ngoài.

### Isolation level và concurrency

Hai DSL execution có thể cùng cập nhật một entity. Test cần mô phỏng concurrent invocation và xác nhận:
- Optimistic locking phát hiện conflict.
- Không mất update.
- Invariant domain được giữ.
- Retry không tạo side effect lặp.
- Result của mỗi invocation phản ánh đúng version dữ liệu.

## Kiểm thử event, message và callback

DSL có thể phát event hoặc nhận message từ host. Event integration cần xác định delivery semantics, ordering, correlation và duplicate handling.

### Outgoing event

Khi DSL hoàn tất một hành động, host có thể publish event:

~~~text
ON OrderApproved
  PUBLISH "order.approved" {
    orderId = order.id
    approvedBy = actor.id
  }
~~~

Test cần xác nhận:
- Đúng event type.
- Payload đúng schema.
- Tenant và correlation metadata được gắn đúng.
- Event chỉ được publish theo commit policy.
- Không publish khi transaction rollback.
- Duplicate event được xử lý theo idempotency contract.

### Incoming event

Host có thể nhận message rồi kích hoạt DSL. Test cần kiểm tra:
- Message được validate.
- Event được correlate đúng process hoặc entity.
- Message từ tenant khác bị từ chối.
- Duplicate và out-of-order event được xử lý theo policy.
- Poison message không làm worker lặp vô hạn.
- Retry và dead-letter behavior đúng.

### Callback và async completion

Nếu DSL gọi host API bất đồng bộ, test cần chờ completion bằng cơ chế deterministic như future, latch hoặc test scheduler. Tránh dùng sleep cố định vì làm test chậm và không ổn định.

## Kiểm thử lifecycle và concurrency của DSL runtime

Host có thể quản lý một runtime dùng chung cho nhiều request. Cần xác nhận lifecycle và concurrency không làm rò rỉ state giữa các lần chạy.

### Runtime startup và shutdown

Kiểm tra:
- Registry được khởi tạo trước khi nhận request.
- Plugin và host binding được đăng ký đúng thứ tự.
- Shutdown ngừng nhận execution mới.
- Execution đang chạy được chờ hoặc hủy theo policy.
- Cache và resource được giải phóng.
- Thread pool và scheduler được đóng.
- Không còn task hoặc file watcher sau shutdown.

### Shared runtime và per-execution state

Runtime có thể được chia sẻ, nhưng context và mutable state của từng execution phải được cô lập. Test nên chạy nhiều invocation đồng thời với user, tenant và input khác nhau rồi xác nhận không có data leakage.

### Thread safety

Nếu function registry, module cache hoặc compiled plan được cập nhật đồng thời, cần kiểm tra race condition. Một module đang reload không được làm request đọc trạng thái nửa cũ nửa mới.

### Cancellation và timeout

Khi host request bị hủy hoặc quá thời gian, cancellation cần truyền xuống interpreter, host function và task nền theo contract. Test cần xác nhận:
- Execution dừng trong giới hạn hợp lý.
- Không tiếp tục side effect sau cancellation nếu policy không cho phép.
- Resource được giải phóng.
- Kết quả trả về đúng cancellation/timeout status.
- Host thread không bị giữ vô hạn.

## Kiểm thử security và authorization tại host boundary

DSL có thể được author bởi developer, operator hoặc người dùng cuối. Không nên giả định mọi source DSL đều đáng tin.

### Principal propagation

Host cần truyền identity đã xác thực vào execution context. Test nên thử sửa field principal trong DSL input và xác nhận runtime không chấp nhận identity giả.

### Permission theo function/action

Một host function có thể yêu cầu permission cụ thể. Test cần xác nhận:
- Principal được phép gọi function.
- Principal không có quyền bị từ chối.
- Resource scope được kiểm tra.
- Tenant boundary được giữ.
- Permission bị thu hồi có hiệu lực theo policy.
- Error không tiết lộ dữ liệu nhạy cảm.

### Sandbox

Nếu DSL có thể gọi command, plugin hoặc script, test cần xác nhận sandbox giới hạn filesystem, network, process và resource. Test path traversal, symbolic link, network egress và access đến host credentials trong môi trường an toàn chuyên dụng.

### Secret handling

Kiểm tra secret chỉ được inject vào execution được cấp quyền, không xuất hiện trong source snapshot, result, diagnostic, logs hoặc cache không bảo vệ. Có thể dùng secret giả lập có marker dễ nhận diện để kiểm tra redaction.

### Policy failure

Nếu authorization service không khả dụng, host cần có hành vi fail-closed cho action nhạy cảm. Test phải phân biệt deny có chủ đích với indeterminate do dependency failure.

## Kiểm thử kết quả và error mapping

DSL runtime có thể trả result, diagnostic, warning hoặc exception. Host phải ánh xạ các trạng thái này thành response phù hợp.

Một result model có thể gồm:

~~~text
HostDslResult
  status
  value
  diagnostics
  executionId
  duration
  sourceVersion
  correlationId
~~~

Các trường hợp cần kiểm tra:
- Evaluation thành công.
- Result null hoặc empty.
- Compile error.
- Type error.
- Runtime exception.
- Host service unavailable.
- Authorization denied.
- Timeout.
- Cancellation.
- Resource limit exceeded.
- Partial result nếu DSL hỗ trợ.
- Warning không làm thất bại execution.

### Error taxonomy

Nên phân loại lỗi theo nguồn:
- DSL syntax/semantic error.
- Host integration error.
- Domain validation error.
- External dependency error.
- Security error.
- Runtime infrastructure error.

Host có thể chuyển nhóm lỗi thành HTTP status, domain error code hoặc workflow state. Không nên ánh xạ mọi lỗi thành 500 hoặc trả raw exception message.

### Source location

Nếu lỗi phát sinh trong function binding hoặc action, runtime nên giữ source span của call site. Host có thể trả diagnostic trỏ về dòng DSL gây lỗi, kèm execution ID để điều tra.

### Partial side effects

Một DSL execution có thể hoàn tất một số action trước khi lỗi xảy ra. Host cần biết execution có atomic hay không và result phải thể hiện trạng thái partial/compensated nếu contract hỗ trợ. Không nên báo success chỉ vì interpreter trả được một value cuối cùng khi side effect bắt buộc đã thất bại.

## Kiểm thử serialization và boundary data

DSL thường nhận input từ JSON, database record, API request hoặc message. Dữ liệu phải được chuyển qua các boundary mà không mất thông tin.

### Serialization format

Kiểm tra:
- Field name mapping.
- Nested object.
- Array và map.
- Enum.
- Date/time.
- Decimal.
- Binary data.
- Unicode.
- Null và missing.
- Unknown field policy.

### Round-trip

Nếu host serialize domain object sang DSL value rồi chuyển kết quả trở lại host object, test round-trip có thể phát hiện mất precision, field bị bỏ qua hoặc default không mong muốn.

Không phải mọi domain object đều cần round-trip hoàn toàn. Contract có thể chỉ cho phép một subset field hoặc immutable projection.

### Version compatibility

Source DSL, host API schema và serialized payload có thể được version độc lập. Test nên bao phủ:
- DSL cũ với host API mới.
- DSL mới với schema tương thích.
- Payload cũ được migrate.
- Unknown field hoặc deprecated field.
- Runtime từ chối version không tương thích với diagnostic rõ.

### Boundary values

Các giá trị như số âm, số cực lớn, chuỗi rỗng, Unicode supplementary character, timestamp ở ranh giới timezone và collection rỗng thường làm lộ lỗi mapping.

## Kiểm thử plugin và extension của host

Một số DSL cho phép host đăng ký plugin, custom function, type provider hoặc connector.

### Plugin discovery

Kiểm tra:
- Plugin được tìm đúng.
- Version và dependency được resolve.
- Plugin lỗi không làm registry ở trạng thái nửa khởi tạo.
- Plugin bị disable không được load.
- Plugin cùng ID nhưng khác version được xử lý theo policy.

### Registration contract

Plugin có thể khai báo:
- Function name và signature.
- Input/output type.
- Permission cần thiết.
- Side-effect metadata.
- Version compatibility.
- Lifecycle callback.
- Configuration schema.

Host cần validate manifest trước khi cho plugin tham gia runtime.

### Plugin isolation

Nếu plugin không đáng tin, có thể cần process isolation hoặc sandbox. Test cần xác nhận plugin không truy cập API hoặc resource ngoài capability được cấp.

### Extension lifecycle

Kiểm tra register, activate, deactivate, reload và shutdown. Một plugin bị unload không được tiếp tục nhận request hoặc giữ thread/resource ngoài ý muốn.

### Backward compatibility

Thay đổi host API có thể làm plugin cũ lỗi. Contract test hoặc compatibility suite giúp xác nhận extension API giữ cam kết đã công bố.

## Kiểm thử tích hợp với database và service thật

Host integration test có thể dùng database thật trong container hoặc test instance để xác nhận driver, transaction và mapping. External service có thể được thay bằng test server nếu mục tiêu là kiểm tra protocol và adapter.

### Khi nên dùng database thật?

Nên dùng database engine thật khi cần kiểm tra:
- SQL dialect hoặc query mapping.
- Constraint và index behavior.
- Transaction isolation.
- Locking.
- Type mapping.
- Migration.
- Driver-specific behavior.

In-memory database có thể không tương đương engine production, đặc biệt về SQL dialect, collation, locking và transaction. Nếu test chỉ cần repository contract, test double có thể đủ.

### External service test double

Một test server có thể mô phỏng response success, timeout, retryable error và malformed payload. Nó giúp test adapter thật mà không phụ thuộc dịch vụ production.

Test double nên mô phỏng contract, không tạo một protocol khác với service thật.

### Containerized dependencies

Database, broker hoặc service phụ trợ có thể chạy bằng container trong CI. Cần pin version, health check, port isolation và cleanup. Không nên dùng một container dùng chung cho nhiều test song song nếu dữ liệu có thể va chạm.

### Test data

Fixture nên tạo dữ liệu qua API hoặc builder có kiểm soát. Tránh phụ thuộc ID tự tăng cố định hoặc thứ tự trả về không có contract.

## Kiểm thử hiệu năng và resource usage tại host boundary

Host integration test không thay thế benchmark chuyên sâu, nhưng có thể phát hiện regression rõ ràng trong lifecycle và adapter.

Các điểm có thể đo:
- Host startup time với DSL registry.
- Module load/compile time.
- Context construction time.
- Host function invocation latency.
- Database query count.
- Number of remote calls.
- Memory allocation theo execution.
- Cache hit/miss.
- Concurrent execution throughput.
- Cancellation completion time.

### Tránh assertion thời gian quá chặt

Test CI chạy trên máy có tải khác nhau. Thay vì yêu cầu một execution luôn dưới vài millisecond, có thể kiểm tra không có N+1 query, số remote call không vượt ngưỡng hoặc benchmark riêng với môi trường ổn định.

### Kiểm tra resource leak

Sau nhiều execution, xác nhận số thread, connection, file handle và cache entry không tăng vô hạn. Có thể dùng nhiều vòng chạy và kiểm tra xu hướng thay vì chỉ một lần invocation.

### Load và stress test

Stress test cần tách khỏi test suite nhanh nếu thời gian và tài nguyên lớn. Nó có thể chạy nhiều host request đồng thời, mixed tenant, module reload và external dependency failure để quan sát hệ thống.

## Fixtures, test data và deterministic execution

Một test integration tốt phải tái lập được. Kết quả không nên phụ thuộc thời gian thật, thứ tự test hoặc dữ liệu còn sót từ lần chạy trước.

### Fixture builder

Có thể tạo builder cho domain object:

~~~text
order = OrderFixture()
  .withCustomer(activeCustomer)
  .withItems(itemA, itemB)
  .withTotal(1500000)
  .build()
~~~

Fixture nên tạo object hợp lệ theo domain invariant, tránh dùng dữ liệu tùy tiện khiến test thất bại trước khi DSL được gọi.

### Fake clock

Guard hoặc function phụ thuộc thời gian nên dùng clock có thể điều khiển. Test có thể đặt thời gian cố định, tiến đồng hồ và kiểm tra deadline mà không sleep.

### Deterministic ID và random source

Nếu DSL tạo ID hoặc dùng random, inject generator để test kiểm soát kết quả. Không nên dựa vào giá trị random cố định từ môi trường.

### Test isolation

Các test song song cần namespace riêng cho database, file, queue và cache. Dùng unique execution ID hoặc tenant fixture để tránh đụng dữ liệu.

### Cleanup

Cleanup nên chạy cả khi assertion thất bại. Test harness có thể dùng lifecycle hook hoặc resource scope để đóng context và xóa fixture.

## Kiểm thử reload và thay đổi DSL khi host đang chạy

Host có thể hỗ trợ chỉnh sửa rule hoặc workflow mà không restart ứng dụng. Đây là một boundary có nhiều trạng thái cạnh tranh.

### Reload behavior

Kiểm tra:
- Source mới được parse và compile.
- Diagnostics của version mới được công bố.
- Module lỗi không thay thế module đang hoạt động nếu policy yêu cầu atomic reload.
- Cache liên quan được invalidation.
- Request mới dùng version mới sau thời điểm publish.
- Request đang chạy tiếp tục dùng version cũ hoặc được hủy theo contract.

### Atomic registry swap

Một cách triển khai là tạo registry mới hoàn chỉnh rồi thay reference nguyên tử. Không nên cập nhật từng function hoặc rule vào registry đang được request đọc nếu điều đó tạo trạng thái một phần.

### Version pinning

Mỗi execution có thể gắn với DSL definition version. Result và audit cần ghi version đó để tái dựng hành vi.

### Concurrent reload

Chạy nhiều request trong khi reload lặp lại. Kiểm tra không có class cast error, missing binding, mixed schema hoặc kết quả từ version không xác định.

## Observability và chẩn đoán test failure

Khi test thất bại, cần đủ thông tin để xác định lỗi ở DSL, host adapter hay dependency.

Có thể ghi:
- Test case ID.
- Execution ID.
- DSL module/version.
- Host application version.
- Runtime version.
- Correlation ID.
- Source span.
- Authorization decision ID.
- Database transaction ID hoặc test fixture key.
- External request stub history.

### Structured logs

Logs trong test nên có event và field ổn định. Không in secret, credential hoặc toàn bộ domain payload nếu chứa dữ liệu nhạy cảm.

### Trace

Trace có thể nối:
- Host request.
- Context construction.
- DSL compile/evaluate.
- Host function.
- Repository call.
- External service.
- Result mapping.

Trace giúp nhận biết thời gian nằm ở interpreter hay host dependency.

### Assertion messages

Assertion nên mô tả điều kiện mong đợi và trạng thái thực tế, ví dụ expected order state Paid but actual state Approved, kèm execution ID. Tránh assertion chỉ trả về expected true but was false mà không có context.

### Artifact khi thất bại

CI có thể lưu diagnostics, sanitized execution trace và test report. Source DSL hoặc payload chỉ nên được lưu nếu policy cho phép và dữ liệu không nhạy cảm.

## Tổ chức bộ host integration test

Một suite có thể được chia theo boundary để dễ chạy và chẩn đoán:

| Nhóm test | Nội dung |
|---|---|
| Runtime bootstrap | Nạp runtime, đăng ký function và cấu hình |
| Compilation integration | Module resolution, compiler và cache |
| Context mapping | Principal, tenant, domain object và clock |
| Host bindings | Function/action, type conversion và exception |
| Persistence | Repository, transaction, rollback và concurrency |
| Messaging | Event, callback, retry và idempotency |
| Security | Authorization, tenant isolation và sandbox |
| Lifecycle | Startup, shutdown, reload và cancellation |
| Extensions | Plugin discovery, registration và compatibility |
| API mapping | Result, diagnostics và error response |
| Performance smoke | Query count, resource leak và basic latency |

### Test naming

Tên test nên thể hiện hành vi và điều kiện, ví dụ:
- evaluating_rule_uses_authenticated_tenant_context
- host_action_failure_rolls_back_domain_transaction
- reload_keeps_previous_module_when_new_source_is_invalid
- unauthorized_execution_does_not_call_host_service
- duplicate_event_does_not_repeat_external_action

Tên test mô tả kết quả mong đợi giúp người đọc hiểu contract ngay cả khi không xem implementation.

### Chạy theo profile

Có thể có các profile:
- Fast integration: database và host test harness nhẹ.
- Full integration: database/broker thật trong container.
- Security integration: sandbox và permission boundary.
- Compatibility: nhiều runtime/host version.
- Performance smoke: số liệu cơ bản, không phải benchmark đầy đủ.

Mỗi profile cần có dependency và điều kiện chạy rõ ràng.

## Tích hợp host test trong CI

Host integration test cần chạy tự động trong pipeline để phát hiện lỗi binding và behavior trước khi release.

Một pipeline minh họa:

~~~text
Checkout
   |
   v
Compile host application
   |
   v
Run DSL unit tests
   |
   v
Start test dependencies
   |
   v
Run host integration tests
   |
   v
Collect diagnostics and reports
   |
   v
Run security / compatibility suites
   |
   v
Build release artifact
~~~

### Dependency setup

CI cần khởi động database, broker hoặc mock service với version xác định. Có health check và timeout để test không chạy trước khi dependency sẵn sàng.

### Parallel execution

Nếu test chạy song song, mỗi test hoặc worker cần namespace riêng. Tránh dùng chung database row, queue name hoặc fixed port.

### Flaky test

Test flaky thường phụ thuộc sleep, thời gian thật, thứ tự test, shared state hoặc network không ổn định. Có thể giảm bằng fake clock, deterministic scheduler, isolated fixture và test server cục bộ.

Không nên tự động retry mọi test thất bại rồi coi pipeline thành công. Retry có thể che giấu race condition hoặc lỗi thật. Cần ghi nhận retry và điều tra nguyên nhân.

### Test report

Báo cáo nên phân biệt:
- Setup failure.
- Test assertion failure.
- Dependency unavailable.
- Timeout.
- Infrastructure failure.
- Test skipped theo cấu hình.

Nếu host không khởi động do thiếu config, đó là lỗi setup hoặc integration bootstrap, không phải DSL evaluation failure.

## Các lỗi thường gặp khi kiểm thử tích hợp host

### Chỉ test interpreter mà không khởi tạo host adapter

Interpreter có thể chạy đúng trong isolation nhưng host function registry bị thiếu hoặc mapping sai. Cần ít nhất một test đi qua đường khởi tạo thực tế của host.

### Dùng mock cho chính boundary cần kiểm tra

Nếu test thay toàn bộ host repository bằng mock, nó không kiểm tra transaction, query mapping hoặc dependency injection. Chọn test double theo mục tiêu và giữ implementation thật ở boundary đang được xác nhận.

### Dùng context quá rộng

Truyền toàn bộ host container khiến DSL truy cập nhiều khả năng hơn dự kiến. Test nên xác nhận context chỉ expose interface cần thiết và quyền phù hợp.

### Không kiểm tra tenant và principal

Một rule chạy được chưa chứng minh nó chạy trong đúng security context. Cần test user không quyền, tenant khác và context bị giả mạo.

### Không kiểm tra side effect và rollback

Assert result của interpreter mà không kiểm tra database hoặc event có thể bỏ sót việc action đã thực hiện một phần. Kiểm tra cả host state và external boundary.

### Dựa vào sleep trong async test

Sleep tạo race và làm suite chậm. Dùng future, latch, deterministic scheduler hoặc event probe.

### Dùng in-memory database thay cho engine production khi cần

In-memory engine có thể không tái hiện transaction, collation hoặc SQL dialect. Chọn database thật khi behavior đó thuộc contract cần kiểm tra.

### Không cô lập cache và registry

State còn lại từ test trước có thể làm test sau pass giả hoặc fail ngẫu nhiên. Reset hoặc tạo namespace riêng cho module cache, plugin registry và result cache.

### Bỏ qua reload và shutdown

Host có thể chạy tốt lúc startup nhưng lỗi khi reload hoặc đóng ứng dụng. Lifecycle cần có test riêng.

### Log dữ liệu nhạy cảm khi test fail

Test report và CI artifact có thể được lưu lâu hoặc nhiều người truy cập. Cần sanitize payload, secret và token trước khi xuất.

## Quy trình xây dựng host integration test cho DSL

Một quy trình thực tế có thể đi theo các bước:

1. **Xác định host boundary:** liệt kê runtime, context builder, bindings, repository, event, authorization và result mapping.
2. **Viết contract mong đợi:** mô tả input, output, side effect, transaction và lỗi ở mỗi boundary.
3. **Chọn test harness:** khởi tạo đúng host configuration và DSL runtime cần kiểm tra.
4. **Thiết kế fixture:** tạo principal, tenant, domain data, clock và external dependency deterministic.
5. **Kiểm tra bootstrap và compilation:** module loading, registration, version và cache.
6. **Kiểm tra context và type mapping:** identity, scope, null, Decimal, time và collection.
7. **Kiểm tra host API:** function/action, exception mapping, permission và idempotency.
8. **Kiểm tra persistence:** read/write, transaction, rollback, locking và event consistency.
9. **Kiểm tra lifecycle:** concurrent execution, cancellation, reload và shutdown.
10. **Kiểm tra security:** tenant isolation, authorization, sandbox và secret handling.
11. **Kiểm tra output:** result, diagnostics, error taxonomy và source location.
12. **Tích hợp CI:** dependency version, parallel isolation, reports và timeout.
13. **Theo dõi độ ổn định:** loại bỏ sleep, shared state và nondeterminism.
14. **Mở rộng theo rủi ro:** thêm compatibility, stress hoặc security suite khi boundary tương ứng thay đổi.

Mỗi test nên xác định rõ phần nào là implementation thật và phần nào là test double. Điều đó giúp người đọc hiểu test chứng minh điều gì, đồng thời tránh nhầm một test cô lập với bằng chứng cho toàn bộ hệ thống.

## Kết luận

Kiểm thử tích hợp host xác nhận DSL hoạt động đúng khi được nhúng vào ứng dụng thực tế và kết nối với context, domain service, repository, event system, authorization và lifecycle của host. Nó tập trung vào các hợp đồng giữa DSL runtime và host application: nạp module, compile, resolve binding, chuyển kiểu, thực thi action, quản lý transaction và ánh xạ result hoặc error.

Một bộ test có giá trị cần dùng host test harness phù hợp, fixture deterministic và test boundary rõ ràng. Cần kiểm tra cả success path lẫn lỗi, tenant isolation, quyền thực thi, rollback, duplicate event, concurrency, cancellation, reload và shutdown. Database hoặc service thật nên được dùng khi behavior của chúng thuộc contract cần xác nhận; test double phù hợp cho dependency bên ngoài khi cần kiểm soát response.

Khi được tổ chức theo boundary và chạy tự động trong CI, host integration test phát hiện những lỗi mà unit test của DSL hoặc host riêng lẻ không nhìn thấy. Nó giúp bảo đảm một DSL không chỉ diễn giải đúng biểu thức mà còn tương tác đúng, an toàn và nhất quán với ứng dụng sở hữu nó.
