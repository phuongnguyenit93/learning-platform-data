# An toàn

Trong thiết kế một hệ thống dùng ngôn ngữ miền chuyên biệt (Domain-Specific Language, DSL), an toàn là khả năng ngăn chương trình, dữ liệu, người dùng hoặc thành phần tích hợp gây ra tác động không mong muốn vượt quá giới hạn chấp nhận được. Một DSL có thể đọc file, truy vấn database, thực thi rule, gọi API, sinh mã hoặc triển khai tài nguyên. Vì vậy, lỗi trong language design, runtime hoặc configuration có thể làm lộ dữ liệu, ghi sai trạng thái, tiêu tốn tài nguyên, gây gián đoạn dịch vụ hoặc thực hiện hành động ngoài ý muốn.

**An toàn (safety)** trong đánh đổi thiết kế rộng hơn việc ngăn tấn công. Nó bao gồm tính đúng đắn, bảo vệ dữ liệu, giới hạn quyền, kiểm soát side effect, khả năng phục hồi, xử lý lỗi và ngăn hệ thống đi vào trạng thái nguy hiểm. **Bảo mật (security)** tập trung vào việc chống truy cập, thay đổi hoặc phá hoại trái phép. Hai khái niệm giao nhau nhưng không hoàn toàn giống nhau: một hệ thống có thể không bị tấn công nhưng vẫn gây thiệt hại do lỗi logic; ngược lại, một hệ thống có thể đúng về nghiệp vụ nhưng dễ bị khai thác.

An toàn luôn có chi phí và trade-off. Kiểm tra nhiều hơn có thể tăng latency; sandbox chặt có thể hạn chế khả năng mở rộng; immutable data có thể tăng memory; xác nhận trước hành động nhạy cảm có thể làm workflow chậm hơn. Mục tiêu thiết kế là xác định rủi ro, chọn biện pháp tương xứng và làm rõ phần nào được bảo đảm, phần nào còn giới hạn.

## 1. An toàn trong bối cảnh DSL

DSL thường cung cấp abstraction để người dùng mô tả hành vi ở mức miền. Tuy nhiên, abstraction không loại bỏ quyền lực của runtime. Một biểu thức ngắn có thể kích hoạt truy vấn lớn, ghi database, gọi external service hoặc tạo hàng nghìn artifact.

Các tình huống rủi ro:
- Một rule xóa nhầm nhiều bản ghi.
- Query thiếu filter khiến hệ thống quét toàn bộ dữ liệu.
- Generated SQL nối chuỗi input gây injection.
- Plugin truy cập file ngoài workspace.
- Workflow retry tạo giao dịch trùng.
- Expression đệ quy không giới hạn làm cạn stack.
- Regex gây CPU exhaustion.
- Migration thay đổi dữ liệu mà không có backup.
- Runtime dùng timezone mặc định khác môi trường nghiệp vụ.
- Partial failure để lại trạng thái không nhất quán.

An toàn cần được xem xét ở mọi tầng: language syntax, type system, compiler, generator, runtime, API, storage, plugin manager, build system, deployment và operations.

## 2. Safety, security, reliability và correctness

Các khái niệm liên quan nhưng có mục tiêu khác nhau:

| Khái niệm | Mục tiêu | Ví dụ |
|---|---|---|
| Safety | Ngăn tác động gây hại hoặc trạng thái nguy hiểm | Không xóa dữ liệu khi migration thất bại |
| Security | Chống truy cập và hành động trái phép | User không đọc dữ liệu tenant khác |
| Reliability | Duy trì dịch vụ và phục hồi khi lỗi | Runtime restart sau crash |
| Correctness | Kết quả đúng theo semantics | Rule tính phí đúng công thức |
| Privacy | Bảo vệ thông tin cá nhân | Diagnostic bundle che token và PII |
| Resilience | Tiếp tục hoặc phục hồi khi dependency lỗi | Queue retry có giới hạn |

Một thiết kế an toàn cần phối hợp các thuộc tính này. Ví dụ, retry giúp reliability nhưng retry một payment action không idempotent có thể làm giảm safety bằng cách charge hai lần.

## 3. Xác định tài sản và tác động

Trước khi chọn biện pháp, cần xác định hệ thống đang bảo vệ điều gì.

Tài sản có thể gồm:
- DSL source và model.
- Generated code/artifact.
- Business data.
- Credential và secret.
- Plugin package.
- Runtime configuration.
- Database schema và transaction state.
- User identity và authorization policy.
- Audit trail.
- Availability và compute resources.

Với mỗi tài sản, xác định:
- Tính bí mật cần giữ.
- Tính toàn vẹn cần bảo vệ.
- Tính sẵn sàng cần duy trì.
- Ai được phép đọc/ghi/thực thi.
- Hậu quả khi dữ liệu bị sai hoặc mất.
- Khả năng khôi phục và thời gian cho phép.

Ví dụ, mất một file cache có thể chỉ làm build chậm. Mất audit record của quyết định tài chính có thể gây rủi ro tuân thủ. Hai loại dữ liệu cần mức bảo vệ khác nhau.

## 4. Threat modeling và risk assessment

Threat modeling xác định cách hệ thống có thể bị sử dụng sai hoặc bị tấn công. Risk assessment đánh giá khả năng xảy ra và mức độ tác động.

Một quy trình đơn giản:
1. Vẽ data flow và trust boundary.
2. Xác định actor và quyền của họ.
3. Liệt kê asset và entry point.
4. Xác định threat và failure mode.
5. Đánh giá likelihood và impact.
6. Chọn control.
7. Xác định residual risk.
8. Kiểm tra control bằng test và monitoring.

Ví dụ data flow:

~~~mermaid
flowchart TD
    A[User or CI] --> B[DSL source]
    B --> C[Parser and compiler]
    C --> D[Generated artifact]
    D --> E[Runtime]
    E --> F[Database]
    E --> G[External API]
    H[Plugin] --> C
    H --> E
~~~

Trust boundary có thể nằm giữa user source và compiler, giữa plugin và host, giữa runtime và database, hoặc giữa ứng dụng và external API. Mỗi boundary cần validation, authentication, authorization và error handling phù hợp.

Không nên chỉ lập threat model một lần. Khi thêm plugin API, function mới hoặc deployment capability, attack surface thay đổi và cần xem xét lại.

## 5. Secure by default và least privilege

Secure by default nghĩa là cấu hình mặc định an toàn. Least privilege nghĩa là mỗi thành phần chỉ có quyền cần thiết để thực hiện nhiệm vụ.

Ví dụ:
- Query DSL mặc định chỉ đọc, muốn ghi phải khai báo capability.
- Plugin generator chỉ được ghi vào output directory được cấp.
- Build task compile không có quyền deploy production.
- Runtime function không tự động truy cập filesystem hoặc network.
- User không có quyền admin nếu không được cấp rõ.
- Secret được cung cấp qua credential handle, không nhúng trong source.

Một capability model có thể biểu diễn:

~~~text
task "generateClient" {
    capabilities {
        workspace.read
        generatedOutput.write
    }
    action {
        generateClient()
    }
}
~~~

Capability declaration chỉ hữu ích nếu runtime thực thi nó. Nếu mọi plugin vẫn chạy với quyền process đầy đủ, manifest permission chỉ mang tính mô tả.

## 6. An toàn ở language design

Language design có thể giảm rủi ro bằng cách giới hạn những construct nguy hiểm.

Các lựa chọn:
- Không cho thực thi code tùy ý trong expression.
- Tách pure expression khỏi command có side effect.
- Yêu cầu capability cho file/network/database access.
- Giới hạn recursion hoặc cung cấp iteration có bound.
- Kiểm soát dynamic evaluation.
- Dùng typed identifier và path thay vì raw string.
- Định nghĩa evaluation order.
- Phân biệt null, missing và error.
- Không cho phép implicit conversion mơ hồ.
- Hạn chế reflection hoặc runtime class loading từ source không tin cậy.

Ví dụ, DSL có thể phân biệt:

~~~text
expression {
    total = quantity * unitPrice
}

command {
    reserveInventory(orderId)
}
~~~

Expression có thể được đánh giá an toàn và xác định. Command có side effect cần quyền, audit và transaction policy.

Không phải mọi DSL đều cần sandbox. Một DSL nội bộ chỉ do developer tin cậy viết có threat model khác DSL cho phép khách hàng upload source. Cần thiết kế theo mức độ tin cậy thực tế.

## 7. Type safety và domain types

Type system có thể ngăn một số lỗi trước runtime.

Ví dụ:
- Không trộn CustomerId với OrderId.
- Không cộng Money với Duration.
- Không truyền raw string vào SQL identifier.
- Không dùng nullable value như non-null.
- Không gọi function với kiểu sai.
- Không dùng artifact chưa validated làm input production.

Domain type:

~~~text
type CustomerId = UUID
type OrderId = UUID
type Money<VND> = Decimal
type Percentage = Decimal
~~~

Dù CustomerId và OrderId cùng biểu diễn bằng UUID, type system có thể ngăn nhầm lẫn. Unit-aware types cũng giúp tránh lỗi chuyển đổi tiền tệ hoặc thời lượng.

Type safety không thay thế runtime validation. Input ngoài hệ thống vẫn cần kiểm tra, và type assertion sai vẫn có thể gây lỗi.

## 8. Validation đầu vào và trust boundary

Dữ liệu từ user, file, network, plugin hoặc external service cần được xem là không đáng tin cậy cho đến khi được xác thực.

Các lớp validation:
- Transport size và content type.
- Syntax/schema.
- Type và nullability.
- Range/length/cardinality.
- Cross-field constraints.
- Domain invariant.
- Authorization và ownership.
- Resource quota.

Ví dụ:

~~~text
input QueryRequest {
    pageSize: Integer min 1 max 100
    sortBy: SortField
    filter: FilterExpression maxDepth 8
}
~~~

Giới hạn pageSize và filter depth giúp tránh query quá lớn. SortField nên là enum/allowlist thay vì chuỗi tùy ý được ghép vào SQL.

Validation cần chạy sớm trước khi dữ liệu gây side effect. Tuy nhiên, domain invariant phụ thuộc trạng thái hiện tại cần được kiểm tra lại trong transaction để tránh race condition.

## 9. Ngăn injection và unsafe interpretation

Injection xảy ra khi dữ liệu được diễn giải như code hoặc command ngoài ý muốn.

Các bề mặt phổ biến:
- SQL injection.
- Shell command injection.
- Template injection.
- Expression injection.
- Path traversal.
- LDAP/query injection.
- HTML/JavaScript injection.
- Unsafe deserialization.

Biện pháp:
- Dùng parameterized query.
- Dùng typed API thay vì nối chuỗi shell.
- Allowlist identifier và operator.
- Escape output theo context.
- Không evaluate source được nối từ input không tin cậy.
- Giới hạn file path trong workspace.
- Dùng parser/schema thay vì regex cho cấu trúc phức tạp.
- Kiểm tra type và origin của deserialized object.

Ví dụ query DSL nên biểu diễn:

~~~text
query orders {
    where customerId == input.customerId
}
~~~

Compiler tạo parameter binding thay vì nối customerId vào SQL text. Nếu cần chọn cột sort, compiler resolve SortField sang identifier đã được whitelist.

## 10. Safe evaluation và resource limits

Một expression có thể đúng cú pháp nhưng tốn tài nguyên không giới hạn. Ví dụ recursion, regex, nested query hoặc collection operation trên dữ liệu lớn.

Runtime có thể áp dụng:
- Maximum evaluation steps.
- Execution timeout.
- Maximum recursion depth.
- Maximum collection size.
- Maximum query rows.
- Regex timeout hoặc engine an toàn.
- Memory budget.
- Network request budget.
- Maximum generated artifact size.
- Cancellation token.

Ví dụ:

~~~text
runtimePolicy {
    maxSteps = 100000
    maxDepth = 64
    timeout = 2s
    maxCollectionItems = 10000
}
~~~

Giới hạn cần có diagnostics rõ khi bị vượt. Không nên để một expression tiêu thụ CPU vô hạn hoặc làm cạn heap của host.

Resource limit có thể ảnh hưởng legitimate workload. Cần cho phép cấu hình theo tenant/task có quota rõ, có metric và không cho phép một user tự nâng quota vượt quyền.

## 11. Sandbox và isolation

Sandbox giới hạn những gì code hoặc plugin có thể làm. Các mức isolation:

- Language-level sandbox: chỉ cho phép một tập expression/function.
- Capability sandbox: cấp quyền theo operation.
- Filesystem sandbox: giới hạn path.
- Process/container isolation: giới hạn CPU, memory, network và filesystem.
- VM/process isolation: tách crash và runtime.
- Network policy: chỉ cho phép endpoint được phê duyệt.

In-process plugin chạy nhanh và dễ chia sẻ object, nhưng có thể truy cập quyền process. Classloader riêng giảm xung đột dependency nhưng không phải sandbox bảo mật hoàn chỉnh.

Out-of-process plugin có ranh giới tốt hơn nhưng cần protocol, serialization, timeout, retry và process management. Chọn theo trust level và mức thiệt hại nếu plugin lỗi hoặc độc hại.

## 12. An toàn của plugin và extension

Plugin là code thực thi được nạp vào host hoặc process phụ. Cần kiểm soát:
- Publisher identity.
- Package checksum/signature.
- Host API compatibility.
- Dependency provenance.
- Permission.
- Resource usage.
- Lifecycle.
- Extension registration.
- Upgrade/rollback.
- Unload/cleanup.

Một plugin manifest có thể khai báo:

~~~yaml
plugin:
  id: com.example.dsl.report
  version: 2.0.0
permissions:
  - workspace.read
  - generatedOutput.write
  - network.connect: reports.example.com
~~~

Host phải enforce quyền và xác minh package. Không nên tự động cài plugin từ nguồn không tin cậy hoặc cập nhật production lên latest mà không qua review.

Plugin failure cần được cô lập theo policy. Một formatter plugin lỗi không nhất thiết phải làm crash toàn bộ workbench; nhưng nếu plugin là thành phần bắt buộc cho quyết định production, host phải fail closed thay vì âm thầm bỏ qua.

## 13. Authentication và authorization

Authentication xác định ai đang gọi. Authorization xác định caller được phép làm gì trên tài nguyên nào.

Một DSL API cần xác định:
- Identity được lấy từ đâu.
- Role và permission.
- Tenant scope.
- Resource ownership.
- Function/action nào cần capability.
- Có delegated access hay không.
- Quyền được kiểm tra ở gateway, service hay cả hai.
- Policy thay đổi có hiệu lực khi nào.

Không nên tin role hoặc tenant ID do client gửi trong request body. Context bảo mật cần được tạo từ identity đã xác thực và truyền xuyên các tầng.

Authorization cần được áp dụng cả khi query, export, diagnostics và support bundle tạo dữ liệu. Một endpoint đọc model có thể vô tình lộ source của project khác nếu chỉ kiểm tra authentication.

## 14. Data safety và integrity

An toàn dữ liệu bao gồm:
- Không ghi sai dữ liệu.
- Không mất dữ liệu khi failure.
- Không tạo duplicate side effect.
- Có transaction boundary.
- Có backup và restore.
- Có migration plan.
- Có audit trail.
- Có checksum/provenance cho artifact.
- Có retention và deletion policy.

Database constraints là hàng rào cuối:
- NOT NULL.
- CHECK.
- UNIQUE.
- FOREIGN KEY.
- Transaction isolation.
- Optimistic/pessimistic locking.

API validation giúp phát hiện lỗi sớm nhưng không thay database constraint. Hai request đồng thời có thể cùng vượt qua validation trước khi insert; unique constraint cần bảo vệ tính toàn vẹn cuối cùng.

## 15. Transaction, rollback và compensation

Một workflow DSL có thể thực hiện nhiều bước. Nếu bước sau thất bại, cần xác định trạng thái trước đó có được rollback hay phải compensation.

Ví dụ:

~~~text
workflow "purchase" {
    reserveInventory()
    chargePayment()
    createShipment()
}
~~~

Nếu chargePayment thành công nhưng createShipment thất bại, transaction database đơn giản không thể hoàn tác payment ở hệ thống bên ngoài. Cần compensation như refund hoặc cancel reservation.

Thiết kế an toàn cần:
- Xác định transaction boundary.
- Phân biệt local transaction và distributed workflow.
- Dùng idempotency key.
- Ghi trạng thái bước.
- Có retry policy.
- Có compensation action.
- Có timeout/cancellation.
- Có manual recovery path.

Không nên giả định mọi side effect có thể rollback tự động.

## 16. Idempotency và retry safety

Idempotent operation có thể được lặp lại mà không tạo thêm tác động ngoài ý muốn.

Ví dụ, PUT một cấu hình đến cùng giá trị có thể idempotent. POST tạo payment thường không idempotent nếu không có idempotency key.

Khi retry:
- Phân biệt lỗi transient và permanent.
- Dùng bounded attempts.
- Backoff và jitter.
- Lưu operation ID.
- Deduplicate event/command.
- Kiểm tra trạng thái trước khi retry side effect.
- Ghi audit.
- Có dead-letter/manual recovery.

Một workflow DSL nên khai báo operation có retry được không và điều kiện retry. Retry mặc định mọi lỗi có thể gây duplicate charge, duplicate email hoặc ghi dữ liệu lặp.

## 17. Failure modes và fail-safe behavior

Fail-safe behavior xác định hệ thống phản ứng thế nào khi không thể tiếp tục an toàn.

Ví dụ:
- Authorization service không sẵn sàng: từ chối thao tác nhạy cảm thay vì cho phép.
- Policy engine lỗi: không tự động approve nếu approval là bắt buộc.
- Database transaction thất bại: rollback.
- Cache lỗi: có thể fallback sang source of truth nếu an toàn.
- Plugin bắt buộc không load: fail build rõ ràng.
- Optional formatter lỗi: có thể tiếp tục với warning nếu contract cho phép.

Cần phân biệt fail-open và fail-closed:
- Fail-open ưu tiên availability nhưng có thể cho phép hành động khi không xác minh được.
- Fail-closed ưu tiên an toàn nhưng có thể làm gián đoạn dịch vụ.

Lựa chọn phụ thuộc hậu quả. Một trang docs có thể fail-open; một quyết định phân quyền hoặc thanh toán thường cần fail-closed.

## 18. Error handling và thông tin an toàn

Lỗi cần đủ thông tin để chẩn đoán nhưng không tiết lộ chi tiết nhạy cảm.

Một error model có thể chứa:
- Stable error code.
- Safe message.
- Source location.
- Correlation ID.
- Retryability.
- Expected input shape.
- Redacted context.

Không nên trả:
- Stack trace nội bộ.
- SQL query có secret.
- File path nhạy cảm.
- Access token.
- Connection string.
- User data không liên quan.

Log nội bộ có thể chi tiết hơn nhưng vẫn phải redaction và access control. Error response và support bundle nên có chính sách riêng.

## 19. Concurrency và race conditions

Hai task hoặc request có thể cùng đọc/ghi một resource. Race condition có thể gây:
- Lost update.
- Duplicate record.
- Inconsistent cache.
- Output file bị ghi đè.
- Plugin registry thay đổi giữa lúc lookup.
- Workflow chạy side effect hai lần.

Biện pháp:
- Transaction isolation.
- Optimistic locking/version field.
- Pessimistic lock khi cần.
- Atomic file replacement.
- Unique constraints.
- Idempotency.
- Immutable snapshot.
- Thread-safe registry.
- Resource lock.
- Deterministic task graph.

Không nên dùng global lock cho mọi thao tác nếu làm giảm throughput nghiêm trọng. Lock nên có scope hẹp và timeout, có diagnostics khi contention.

## 20. Safe file and artifact handling

DSL compiler và build system thường đọc source và ghi generated artifact.

Cần:
- Giới hạn workspace root.
- Chống path traversal.
- Không theo symbolic link ra ngoài vùng được cấp nếu policy cấm.
- Kiểm tra output ownership.
- Ghi vào staging rồi atomic move.
- Không overwrite file người dùng nếu chưa có ownership.
- Xác minh checksum.
- Giới hạn archive expansion.
- Tránh symlink trong package.
- Không đưa secret vào artifact.

Ví dụ path an toàn cần resolve canonical path và xác nhận vẫn nằm trong output root. Chỉ kiểm tra chuỗi bắt đầu bằng prefix có thể sai nếu path chứa parent traversal hoặc symlink.

## 21. Supply chain và dependency safety

Build DSL có thể tải plugin, library, generator hoặc compiler extension. Rủi ro:
- Dependency bị thay thế.
- Version không pin.
- Package giả mạo.
- Typosquatting.
- Vulnerable transitive dependency.
- Build script tải và chạy code ngoài ý muốn.

Biện pháp:
- Pin version hoặc lockfile.
- Verify checksum/signature.
- Dùng trusted repository.
- Review plugin permissions.
- Quét vulnerability.
- Theo dõi provenance.
- Reproducible build khi phù hợp.
- Hạn chế network trong build.
- Lưu dependency inventory/SBOM.

Không nên chỉ tin tên package hoặc TLS. Integrity và publisher identity cần được xác minh theo policy.

## 22. Privacy và data minimization

Một DSL platform có thể xử lý dữ liệu cá nhân hoặc dữ liệu nghiệp vụ nhạy cảm. An toàn cần xét:
- Thu thập dữ liệu nào.
- Dữ liệu được dùng vào mục đích gì.
- Ai có quyền truy cập.
- Log có chứa payload không.
- Cache có chứa dữ liệu nhạy cảm không.
- Data export có được giới hạn không.
- Retention và deletion.
- Backup và encryption.
- Data residency nếu có yêu cầu.

Diagnostic bundle nên redact token, password, key và PII. Support không nên yêu cầu production dump nếu một fixture synthetic đủ để tái hiện.

Data minimization giảm cả tác động khi rò rỉ lẫn chi phí bảo vệ.

## 23. Observability và audit

An toàn cần có khả năng quan sát để phát hiện hành vi bất thường và tái hiện sự cố.

Các tín hiệu:
- Structured logs.
- Metrics.
- Distributed traces.
- Audit events.
- Build/task reports.
- Plugin lifecycle events.
- Decision trace.
- Data migration report.
- Access denial events.

Audit cần ghi actor, action, target, timestamp, result và correlation ID. Không nên ghi secret hoặc toàn bộ payload nhạy cảm.

Một decision record có thể lưu ruleset version, runtime version, input reference/hash và result để giải thích quyết định. Cần kiểm soát quyền đọc record vì provenance có thể chứa metadata nhạy cảm.

## 24. Safe defaults và usability trade-off

Biện pháp an toàn quá khó sử dụng có thể khiến người dùng tìm cách vô hiệu hóa. Vì vậy, usability cũng là một phần của safety.

Ví dụ:
- Default read-only an toàn nhưng có đường nâng quyền rõ ràng.
- Confirmation cho hành động destructive, không hỏi cho mọi thao tác nhỏ.
- Diagnostics giải thích cách khắc phục thay vì chỉ chặn.
- Quota có thông báo và cách xin tăng hạn mức.
- Migration tool có preview và backup.
- Permission request chỉ yêu cầu capability cần thiết.
- Sandbox có profile theo workload.

Cần tránh cảnh báo quá nhiều. Nếu mọi thao tác đều hiện warning, người dùng sẽ bỏ qua cả cảnh báo quan trọng. Cảnh báo nên dựa trên risk và cung cấp hành động cụ thể.

## 25. Performance và safety trade-offs

Một số kiểm soát có chi phí:
- Validation sâu tăng CPU.
- Encryption tăng latency.
- Audit logging tăng I/O.
- Sandbox tăng overhead.
- Transaction dài làm tăng lock contention.
- Immutable snapshot tăng memory nếu giữ quá lâu.
- Signature verification tăng thời gian cài plugin.

Có thể tối ưu mà vẫn giữ bảo đảm:
- Validate sớm và reuse kết quả theo fingerprint.
- Dùng streaming thay vì materialize payload lớn.
- Batch audit writes nhưng không mất durability cần thiết.
- Giới hạn transaction scope.
- Cache public metadata, không cache quyền đã hết hạn.
- Tách low-risk và high-risk operation.
- Dùng incremental verification khi contract cho phép.

Không nên bỏ control cốt lõi chỉ để cải thiện benchmark. Cần định lượng chi phí, xác định risk acceptance và ghi lại trade-off.

## 26. Functional safety và critical workflows

Một số DSL điều khiển quy trình có tác động vật lý, tài chính hoặc vận hành quan trọng. Với các trường hợp này, cần đánh giá hazard và safety requirement.

Ví dụ:
- Workflow vận hành thiết bị.
- Hệ thống điều khiển công nghiệp.
- Quyết định phân bổ tài chính.
- Hệ thống y tế.
- Quy trình xử lý dữ liệu không thể tái tạo.

Biện pháp có thể gồm:
- Explicit state machine.
- Invariant và precondition.
- Range checking.
- Interlock.
- Approval gate.
- Simulation trước execution.
- Fail-safe state.
- Independent verification.
- Audit và trace.
- Manual override được kiểm soát.

Không nên coi unit/integration test thông thường là bằng chứng đủ cho functional safety của hệ thống critical. Cần áp dụng tiêu chuẩn, hazard analysis và review chuyên môn phù hợp với lĩnh vực.

## 27. Testing cho safety properties

An toàn cần được kiểm chứng bằng test và analysis:

- Input fuzzing.
- Property-based testing.
- Static analysis.
- Dependency/security scanning.
- Permission tests.
- Sandbox escape tests.
- Resource exhaustion tests.
- Concurrency tests.
- Failure injection.
- Transaction rollback tests.
- Backup/restore drills.
- Migration dry-run.
- Plugin tampering tests.
- Authorization/tenant isolation tests.

Ví dụ property:
- Một user không thể đọc resource của tenant khác.
- Một command bị từ chối không tạo side effect.
- Một retry với cùng idempotency key không tạo duplicate.
- Một migration thất bại không để schema ở trạng thái nửa hoàn tất.
- Một task không ghi ra ngoài output root.
- Một evaluation vượt budget kết thúc bằng controlled error.

Test cần chạy trong CI hoặc security pipeline phù hợp và có owner xử lý failure.

## 28. Safe rollout và rollback

Thay đổi có rủi ro nên được triển khai từng bước:
1. Validate và test trên staging.
2. Tạo backup hoặc snapshot phù hợp.
3. Dry-run/plan.
4. Canary cho phạm vi nhỏ.
5. Theo dõi error, latency và side effect.
6. Mở rộng rollout.
7. Xác minh invariants.
8. Rollback hoặc compensation nếu có vấn đề.

Rollback code không tự hoàn tác dữ liệu đã ghi. Nếu version mới thay đổi schema hoặc side effect, cần data migration ngược hoặc compensating action riêng.

Một deployment plan an toàn phải xác định:
- Trigger rollback.
- Người có quyền rollback.
- State cần giữ.
- Cách kiểm tra sau rollback.
- Cách xử lý request đang chạy.
- Cách tránh replay side effect.

## 29. Ví dụ: đánh giá an toàn của một DSL action

Giả sử DSL cho phép xóa dữ liệu cũ:

~~~text
action "purgeArchivedOrders" {
    input olderThan: LocalDate required
    capability database.orders.delete
    requireApproval
    dryRunSupported

    execute {
        delete orders
        where status == ARCHIVED
          and archivedAt < olderThan
    }
}
~~~

Một thiết kế an toàn có thể yêu cầu:
- Input date hợp lệ và không vượt giới hạn policy.
- Capability chỉ cấp cho role được phép.
- Dry-run hiển thị số record dự kiến.
- Approval gắn với execution plan.
- Transaction hoặc batch delete có checkpoint.
- Audit ghi actor và số record.
- Timeout và cancellation.
- Backup/restore hoặc retention policy.
- Không cho phép query bỏ điều kiện status.

Nếu action có thể xóa hàng triệu bản ghi, cần batch size và rate limit. Nếu dry-run và execution dùng hai query khác nhau, preview có thể không phản ánh tác động thật; cả hai nên dựa trên cùng execution plan hoặc snapshot.

## 30. Ví dụ Java: capability check

Một API runtime có thể kiểm tra capability trước khi gọi action:

~~~java
record Capability(String name) {}

interface ExecutionContext {
    boolean hasCapability(Capability capability);
    AuditSink audit();
}

void executeDelete(
        ExecutionContext context,
        DeletePlan plan) {

    Capability required =
        new Capability("database.orders.delete");

    if (!context.hasCapability(required)) {
        context.audit().denied(
            "purgeArchivedOrders",
            "MISSING_CAPABILITY"
        );
        throw new SecurityException("Permission denied");
    }

    context.audit().started(
        "purgeArchivedOrders",
        plan.id()
    );

    performDelete(plan);
}
~~~

Ví dụ chỉ minh họa một lớp kiểm tra. Hệ thống thực tế cần đảm bảo capability được tạo từ identity đã xác thực, không nhận trực tiếp từ request body. Authorization có thể cần kiểm tra tenant, resource scope và approval token ngoài capability name.

## 31. Safety case và bằng chứng

Với hệ thống rủi ro cao, có thể xây safety case: tập lập luận và bằng chứng cho thấy hệ thống đáp ứng safety requirements.

Một cấu trúc đơn giản:
- **Claim:** action destructive không thể chạy nếu thiếu quyền và approval.
- **Argument:** mọi execution đi qua policy enforcement point; không có bypass public.
- **Evidence:** authorization tests, architecture review, audit records, penetration test và deployment control.

Một safety case cần nêu assumptions và limitations. Ví dụ, claim chỉ đúng nếu plugin không được phép chạy code ngoài sandbox. Nếu assumption đó không được enforce, claim không vững.

Không nên dùng một checklist chung để tuyên bố hệ thống “an toàn tuyệt đối”. An toàn luôn gắn với threat model, environment và residual risk.

## 32. Quy trình thiết kế an toàn cho DSL

Có thể áp dụng các bước:

1. **Xác định use case và tác động:** dữ liệu, tài sản, người dùng và hậu quả.
2. **Vẽ trust boundary:** user, compiler, plugin, runtime, database và external services.
3. **Threat/risk modeling:** abuse case, failure mode, likelihood và impact.
4. **Định nghĩa safety properties:** invariants, permission, resource budget và recovery behavior.
5. **Thiết kế language constraints:** type safety, pure/impure separation và explicit capability.
6. **Thiết kế runtime enforcement:** sandbox, quota, timeout và cancellation.
7. **Bảo vệ dữ liệu:** transaction, validation, encryption, audit và backup.
8. **Kiểm soát plugin/dependency:** provenance, signature, compatibility và isolation.
9. **Thiết kế failure behavior:** fail-open/closed, retry, compensation và rollback.
10. **Viết safety tests:** authorization, fuzz, concurrency, failure injection và resource limits.
11. **Triển khai theo giai đoạn:** staging, dry-run, canary và monitoring.
12. **Review residual risk:** xác định giới hạn còn lại và owner chấp nhận.
13. **Theo dõi vận hành:** logs, metrics, audit và incident review.
14. **Cập nhật theo thay đổi:** mỗi extension, capability hoặc integration mới cần review lại threat model.

## 33. Những lỗi thiết kế thường gặp

- Chỉ xem an toàn là chống SQL injection.
- Tin input vì nó đã parse thành object.
- Coi classloader isolation là sandbox.
- Cho plugin quyền rộng mặc định.
- Cho DSL gọi network/filesystem không có capability.
- Không giới hạn recursion, regex hoặc query cost.
- Retry side effect mà không có idempotency.
- Dùng fail-open cho quyết định nhạy cảm.
- Trả stack trace hoặc secret trong error response.
- Chỉ validate ở API mà không có database constraints.
- Không kiểm tra tenant/resource ownership.
- Ghi file output trực tiếp vào vị trí cuối khi generation chưa hoàn tất.
- Shadow evaluation vẫn thực hiện side effect.
- Rollback code nhưng bỏ qua dữ liệu đã thay đổi.
- Cảnh báo quá nhiều khiến user bỏ qua cảnh báo quan trọng.
- Không có backup/restore drill.
- Không xem lại threat model khi thêm plugin hoặc extension point.

## 34. Nguyên tắc thiết kế

- **Định nghĩa an toàn theo tác động:** biết điều gì có thể bị hỏng, lộ hoặc thay đổi.
- **Phân biệt safety và security:** correctness, reliability và privacy cũng góp phần tạo an toàn.
- **Secure by default:** quyền và khả năng nguy hiểm cần được bật có chủ đích.
- **Least privilege:** mỗi task, plugin và user chỉ có quyền cần thiết.
- **Validate ở trust boundary:** kiểm tra shape, type, range, ownership và authorization.
- **Dùng typed API:** tránh nối chuỗi input thành query hoặc command.
- **Tách pure computation khỏi side effect:** giúp test, replay và kiểm soát action.
- **Giới hạn tài nguyên:** timeout, step budget, memory, query size và concurrency.
- **Chọn isolation theo threat model:** in-process, sandbox hoặc process riêng có trade-off khác nhau.
- **Bảo vệ integrity:** transaction, constraint, idempotency, checksum và backup.
- **Fail-safe theo hậu quả:** chọn fail-open hoặc fail-closed có lý do.
- **Không retry mù:** side effect cần idempotency và compensation.
- **Không để error làm lộ dữ liệu:** structured code, redaction và access control.
- **Thiết kế rollback cùng migration:** code rollback không tự hoàn tác data.
- **Đánh giá usability:** control an toàn cần thông báo rõ và có đường thao tác hợp lệ.
- **Đo chi phí của control:** tối ưu implementation mà không bỏ bảo đảm cốt lõi.
- **Kiểm chứng bằng evidence:** test, audit, review và failure drills.
- **Cập nhật risk model:** thay đổi plugin, runtime hoặc capability làm thay đổi attack surface.

An toàn là thuộc tính xuyên suốt của DSL, từ cách ngôn ngữ biểu diễn hành vi đến cách runtime thực thi và tổ chức vận hành hệ thống. Khi rủi ro được xác định, quyền được giới hạn, input được kiểm tra, resource có budget, side effect có transaction/idempotency, plugin được cô lập phù hợp và failure có đường phục hồi, hệ thống có thể cân bằng hiệu năng, khả năng mở rộng và trải nghiệm người dùng mà vẫn giữ được các giới hạn an toàn có thể kiểm chứng.
