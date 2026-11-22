# Khả năng liên thông

## 1. Khả năng liên thông trong thiết kế DSL là gì?

Một DSL (*Domain-Specific Language*) thường được tạo ra để mô tả một miền nghiệp vụ hoặc một loại công việc cụ thể. Tuy nhiên, DSL hiếm khi hoạt động độc lập. Nó cần trao đổi dữ liệu với service khác, tích hợp vào IDE, sinh client/server code, chuyển mô hình sang công cụ workflow, đọc schema từ registry hoặc xuất tài liệu cho hệ thống quản trị.

**Khả năng liên thông (*interoperability*)** là khả năng một DSL và các thành phần xung quanh trao đổi dữ liệu, mô hình hoặc hành vi với hệ thống khác theo cách có thể hiểu, kiểm chứng và duy trì được.

Liên thông không chỉ là hai hệ thống cùng đọc được JSON hoặc XML. Hai bên còn phải thống nhất:
- Cấu trúc dữ liệu.
- Kiểu và đơn vị của giá trị.
- Identity của entity và operation.
- Semantics của field, event, transition và error.
- Version và compatibility.
- Security context và quyền truy cập.
- Thứ tự, tính nhất quán và delivery guarantees.
- Quy tắc xử lý phần không thể biểu diễn ở hệ thống đích.

Ví dụ, một DSL mô tả quy trình đơn hàng có thể xuất workflow model sang BPMN, cung cấp API contract bằng OpenAPI và phát event theo AsyncAPI. Ba artifact này có thể liên quan cùng một quy trình nhưng phục vụ mục tiêu và semantics khác nhau.

~~~text
                 DSL Source
                     |
                     v
              Canonical Model
                /    |    \
               /     |     \
              v      v      v
           BPMN    OpenAPI  Event Schema
              |       |        |
              v       v        v
          Workflow  API Tools  Message Broker
           Engine    /Clients  /Consumers
~~~

Một thiết kế DSL tốt xác định đâu là source of truth, đâu là representation được chuyển đổi, thông tin nào được giữ nguyên và thông tin nào cần extension hoặc adapter.

## 2. Vì sao DSL cần interoperability?

Interoperability giúp DSL tham gia vào hệ sinh thái kỹ thuật hiện có thay vì buộc mọi team phải sử dụng một công cụ duy nhất.

Các mục tiêu thường gặp:
- Trao đổi schema giữa nhiều service.
- Kết nối DSL với API gateway và service runtime.
- Chuyển workflow sang engine khác.
- Import/export mô hình qua định dạng tiêu chuẩn.
- Sinh SDK cho nhiều ngôn ngữ.
- Tích hợp IDE, debugger và language server.
- Đồng bộ event schema với message broker.
- Kết nối metadata với catalog hoặc registry.
- Hỗ trợ migration khỏi hoặc sang một nền tảng khác.
- Chia sẻ mô hình giữa business analyst và developer.

### 2.1. Tránh vendor lock-in

Một định dạng trao đổi ổn định giúp project chuyển công cụ hoặc runtime dễ hơn. Tuy nhiên, export sang format mở không tự động loại bỏ lock-in nếu semantics quan trọng chỉ tồn tại trong proprietary extension hoặc runtime behavior.

### 2.2. Tái sử dụng hệ sinh thái

Nếu DSL có thể ánh xạ sang chuẩn phổ biến, project có thể dùng sẵn:
- API documentation generators.
- Schema validators.
- Workflow engines.
- Message brokers.
- IDE plugins.
- Diagram editors.
- Code generators.
- Observability platforms.

### 2.3. Chia sẻ trách nhiệm giữa team

Team thiết kế domain model có thể dùng DSL; team API dùng OpenAPI; team event dùng schema registry; team vận hành dùng workflow engine. Interoperability giúp mỗi team dùng công cụ phù hợp nhưng vẫn chia sẻ contract.

### 2.4. Giảm duplicate source of truth

Nếu mỗi hệ thống tự định nghĩa lại schema và mapping, chúng dễ drift. Một canonical model hoặc một contract source có version giúp đồng bộ các representation.

## 3. Các tầng interoperability

Có thể phân chia interoperability thành nhiều tầng. Một hệ thống có thể thành công ở tầng này nhưng thất bại ở tầng khác.

| Tầng | Điều cần tương thích | Ví dụ |
|---|---|---|
| Syntax | Cách biểu diễn và parse | DSL source, JSON, YAML |
| Data | Field, type, encoding, units | JSON Schema, Avro |
| Model | Quan hệ và cấu trúc domain | BPMN, UML, graph model |
| Semantic | Ý nghĩa của construct | Retry, transaction, state transition |
| Protocol | Cách trao đổi message | HTTP, gRPC, AMQP |
| Runtime | Execution behavior | Workflow engine, function runtime |
| Tooling | Editor, diagnostics, navigation | LSP, debugger |
| Operational | Identity, tracing, security, lifecycle | OAuth, trace context, audit |

### 3.1. Syntactic interoperability

Hai hệ thống có thể đọc cùng định dạng hoặc parse được cùng grammar. Điều này chỉ xác nhận cấu trúc được hiểu, chưa xác nhận ý nghĩa giống nhau.

### 3.2. Data interoperability

Hai bên hiểu field, type, encoding, nullability, precision và units giống nhau. Ví dụ Integer và Decimal không thể hoán đổi tùy tiện nếu một bên làm tròn dữ liệu.

### 3.3. Model interoperability

Hai hệ thống hiểu các entity và quan hệ ở mức mô hình. Ví dụ một BPMN task có thể map sang một DSL activity, nhưng cần xác định loại task và participant.

### 3.4. Semantic interoperability

Đây là tầng khó nhất. Hai hệ thống phải hiểu cùng hành vi. Ví dụ retry count 3 có thể nghĩa là ba lần tổng cộng hoặc ba lần retry sau lần đầu; nếu không định nghĩa, hai runtime có thể thực thi khác nhau.

### 3.5. Protocol interoperability

Hai hệ thống phải thống nhất framing, authentication, request/response, ordering, timeout, error và delivery behavior.

### 3.6. Operational interoperability

Một hệ thống cần giữ correlation ID, trace context, principal, tenant, policy version và audit metadata khi chuyển qua nhiều service.

## 4. Chọn canonical model và source of truth

Một trong những quyết định quan trọng nhất là chọn representation nào làm nguồn dữ liệu chuẩn.

### 4.1. DSL source là source of truth

Trong mô hình text-first, DSL source là nguồn chính. Compiler parse source thành canonical model rồi sinh OpenAPI, BPMN hoặc code.

Ưu điểm:
- Dễ review bằng version control.
- Có thể dùng text diff.
- Grammar và semantics được quản lý cùng nhau.
- Generated artifacts có thể tái tạo.

Giới hạn:
- Một số người dùng thích chỉnh sửa diagram hoặc schema trực quan.
- Presentation metadata có thể cần lưu riêng.

### 4.2. Canonical model là source of truth

Một số hệ thống lưu một model trung gian có schema rõ ràng. DSL source và các format khác đều là view hoặc serialization của model.

Ưu điểm:
- Nhiều frontend có thể cùng chỉnh sửa.
- Mapping sang nhiều target dễ tổ chức.
- Identity và metadata có thể dùng chung.

Giới hạn:
- Cần quản lý model schema và migration.
- Text representation có thể không round-trip lossless.
- Tooling phải xử lý concurrent edits và merge.

### 4.3. External standard là source of truth

Một project có thể dùng OpenAPI, BPMN XML hoặc protobuf làm nguồn chính rồi import vào DSL để viết extension hoặc business logic.

Trong trường hợp này, DSL cần giữ reference đến artifact gốc và không âm thầm ghi đè phần mà format chuẩn quản lý.

### 4.4. Multiple authoritative sources

Một hệ thống lớn có thể có nhiều source of truth theo domain:
- API contract do API team quản lý.
- Event schema do event platform quản lý.
- Workflow model do process team quản lý.
- Identity policy do security platform quản lý.

Cần định nghĩa ownership theo từng field hoặc artifact, tránh hai hệ thống cùng authoritative cho một thuộc tính.

### 4.5. Canonical model boundaries

Canonical model không nên trở thành bản sao mọi chi tiết của mọi target format. Chỉ đưa vào model những khái niệm thực sự dùng chung; phần đặc thù có thể nằm trong extension metadata.

## 5. Import, export và transformation

Interoperability thường cần các phép biến đổi giữa DSL và format khác.

### 5.1. Import

Import chuyển artifact bên ngoài thành model mà DSL có thể hiểu.

Một pipeline có thể gồm:
1. Đọc artifact.
2. Kiểm tra encoding và format version.
3. Parse thành syntax tree của format nguồn.
4. Resolve references.
5. Map sang canonical model.
6. Gắn source provenance.
7. Validate semantics.
8. Tạo DSL representation hoặc model artifact.

### 5.2. Export

Export chuyển canonical model sang target format:
1. Chọn target version.
2. Kiểm tra feature compatibility.
3. Map constructs.
4. Serialize.
5. Validate bằng target schema/parser.
6. Tạo loss report.
7. Lưu provenance và source version.

### 5.3. Transformation pipeline

~~~text
External Artifact
       |
       v
Format Parser
       |
       v
Source Model
       |
       v
Mapping / Normalization
       |
       v
Canonical DSL Model
       |
       +----> Validation
       |
       v
Target Projection
       |
       v
Target Serializer
       |
       v
External Artifact
~~~

### 5.4. One-way và two-way transformation

One-way export phù hợp khi DSL là source of truth và target chỉ là generated artifact.

Two-way transformation cần round-trip rules. Nếu người dùng sửa target artifact, hệ thống phải biết cách đưa thay đổi về DSL mà không mất semantics.

### 5.5. Lossless và lossy conversion

- Lossless: mọi thông tin cần bảo toàn đều được giữ.
- Lossy: một số construct không có representation tương đương.
- Partially lossless: core semantics được giữ nhưng metadata hoặc presentation bị mất.

Export tool cần nói rõ mức fidelity và liệt kê phần không được chuyển.

## 6. Mapping semantics giữa các hệ thống

Không nên chỉ map tên field hoặc node type. Cần map ý nghĩa.

### 6.1. Structural mapping

Structural mapping chuyển:
- Object thành record.
- Array thành collection.
- Field thành property.
- Reference thành link.
- Node thành activity.
- Edge thành transition.

### 6.2. Semantic mapping

Semantic mapping cần xét:
- Required và optional.
- Null và absent.
- Default behavior.
- Evaluation order.
- Transaction boundaries.
- Retry and timeout.
- Error propagation.
- Concurrency.
- Authorization.
- Idempotency.

### 6.3. Mapping table

Ví dụ một số construct:

| DSL concept | Target concept | Điều cần kiểm tra |
|---|---|---|
| Entity | Schema/record | Identity, key, nullability |
| Operation | API operation | Method, route, security |
| Event | Message schema | Delivery, ordering, version |
| Workflow | Process model | Transition and gateway semantics |
| Rule | Decision/policy | Evaluation and priority |
| Type | Target type | Precision, format, constraints |
| Reference | Foreign reference | Identity and lifecycle |

### 6.4. Unsupported constructs

Nếu target không hỗ trợ construct:
- Reject export.
- Sinh extension.
- Giữ opaque metadata.
- Bỏ qua có cảnh báo nếu thông tin không thiết yếu.
- Yêu cầu user cung cấp mapping.

Không nên silently drop construct có ảnh hưởng execution hoặc security.

### 6.5. Semantic equivalence

Hai representation tương đương khi mọi behavior quan trọng theo contract đều giống nhau trong phạm vi xác định. Chỉ so sánh JSON structure hoặc graph shape là chưa đủ.

## 7. Interoperability với data formats

DSL có thể import/export nhiều định dạng dữ liệu.

### 7.1. JSON

JSON phổ biến cho API và configuration. Cần xác định:
- Number precision.
- Null semantics.
- Unknown fields.
- Object property ordering nếu có ý nghĩa.
- Unicode escaping.
- Duplicate keys.
- Date/time representation.

JSON number không tự mang decimal precision hoặc integer width. Mapping sang typed DSL cần schema.

### 7.2. YAML

YAML tiện cho configuration nhưng có các tính năng như implicit scalar typing, aliases và tags. Importer cần giới hạn hoặc quy định rõ behavior để tránh parser khác nhau hiểu khác nhau.

### 7.3. XML

XML có namespaces, attributes, mixed content và schema mechanisms. Mapping XML sang object model có thể mất thứ tự, namespace identity hoặc distinction giữa attribute và element nếu model quá đơn giản.

### 7.4. CSV

CSV thường thiếu type metadata và nesting. Cần quy định:
- Delimiter.
- Quote/escape.
- Header mapping.
- Encoding.
- Null marker.
- Decimal/date format.
- Duplicate column names.

### 7.5. Protocol Buffers

Protobuf dùng field numbers và typed messages. Khi map DSL schema:
- Field number phải ổn định.
- Reserved fields không được tái sử dụng.
- Optional/presence semantics cần giữ.
- Enum evolution phải tương thích.
- Unknown fields cần được xử lý đúng.

### 7.6. Avro và schema registry

Avro hỗ trợ writer/reader schema resolution. DSL cần xác định schema compatibility policy, default values và logical types khi import/export.

### 7.7. Database schema

Mapping DSL entity sang relational schema cần xử lý:
- Primary/foreign keys.
- Nullability.
- Precision/scale.
- Indexes.
- Unique constraints.
- Transactions.
- Migration.
- Referential actions.

Một type DSL không nhất thiết map một-một sang SQL type trên mọi database.

## 8. Interoperability với API và service protocols

DSL có thể mô tả hoặc sinh contract cho service.

### 8.1. OpenAPI

OpenAPI mô tả HTTP API: paths, methods, parameters, request body, responses, schemas và security schemes.

DSL cần mapping rõ:
- Operation ID.
- HTTP method/path.
- Parameter location.
- Request/response schema.
- Status codes.
- Security requirements.
- Examples.
- Deprecation.

Nếu DSL có runtime policy hoặc business semantics không biểu diễn được trong OpenAPI, cần extension hoặc tài liệu bổ sung.

### 8.2. gRPC và Protocol Buffers

gRPC mô tả service methods và typed messages. Mapping cần xét:
- Unary RPC.
- Client/server streaming.
- Bidirectional streaming.
- Deadline.
- Metadata.
- Status codes.
- Cancellation.
- Authentication.

HTTP request/response semantics không hoàn toàn tương đương gRPC stream semantics.

### 8.3. GraphQL

GraphQL có schema, object types, queries, mutations và subscriptions. Mapping từ DSL cần xác định:
- Field resolver.
- Null propagation.
- Input types.
- Enum behavior.
- Authorization per field.
- Pagination convention.
- Subscription delivery.

Không nên map mọi REST endpoint thành GraphQL field mà không xét resource model và query semantics.

### 8.4. AsyncAPI và messaging

AsyncAPI mô tả message-driven interfaces. Cần map:
- Channel/topic.
- Publisher/subscriber.
- Message schema.
- Protocol binding.
- Correlation ID.
- Delivery guarantees.
- Retry/dead-letter behavior.

### 8.5. HTTP, AMQP và message brokers

Protocol adapter cần xử lý framing, acknowledgements, redelivery, ordering, backpressure và connection lifecycle. Một event được gửi thành công tới broker không đồng nghĩa consumer đã xử lý thành công.

## 9. Interoperability với workflow và modeling standards

DSL có thể mô tả quy trình rồi chuyển sang notation hoặc engine khác.

### 9.1. BPMN

BPMN có event, activity, gateway, pool, lane, sequence flow và message flow. Mapping cần phân biệt:
- Exclusive/inclusive/parallel gateway.
- Boundary events.
- Timer.
- Compensation.
- Subprocess.
- Message flow.
- Transaction behavior.

Một flowchart node không tự động tương đương một BPMN activity nếu semantics khác.

### 9.2. UML

UML có class, activity, state machine, sequence và component diagrams. Mỗi diagram type biểu diễn một góc nhìn. Không nên xuất cùng một model thành class diagram rồi giả định đã bảo toàn process execution.

### 9.3. State machine formats

State machine mapping cần giữ:
- State identity.
- Transition trigger.
- Guard.
- Entry/exit action.
- Initial/final state.
- Composite state.
- History semantics nếu có.

### 9.4. Petri nets

Nếu DSL có parallelism hoặc resource synchronization, Petri net có thể biểu diễn token flow. Mapping cần bảo toàn concurrency và synchronization rules.

### 9.5. Target engine differences

Hai workflow engine có thể hỗ trợ cùng BPMN version nhưng khác runtime extensions, transaction, retry hoặc compensation behavior. Export sang standard format không bảo đảm execution tương đương trên mọi engine.

## 10. Interoperability với programming languages và runtime

DSL có thể gọi code được viết bằng ngôn ngữ khác hoặc sinh code sang target language.

### 10.1. Foreign function interface

Một FFI hoặc host binding cần xác định:
- Function identity.
- Parameter types.
- Return type.
- Calling convention.
- Ownership/lifetime.
- Error mapping.
- Threading behavior.
- Cancellation.
- Security capability.

### 10.2. Type mapping

Một số type không map trực tiếp:
- BigInteger.
- Decimal.
- DateTime with timezone.
- Duration.
- Binary.
- Optional.
- Union.
- Generic collection.
- Domain-specific value object.

Cần adapter hoặc wrapper type có semantics được công bố.

### 10.3. Nullability và optionality

Một language có null reference, language khác có Option/Maybe, language khác dùng field presence. Mapping phải giữ distinction giữa missing, null và value.

### 10.4. Error mapping

Exception, error result, status code và DSL diagnostic có thể khác nhau. Adapter cần chuyển:
- Error category.
- Stable code.
- Safe message.
- Retryability.
- Cause chain.
- Correlation ID.

Không nên truyền stack trace hoặc secret qua boundary công khai.

### 10.5. Memory ownership

Khi dữ liệu đi qua FFI, cần quy định ai sở hữu buffer, ai giải phóng và object có được giữ sau callback không. Sai ownership có thể gây leak hoặc use-after-free.

### 10.6. Threading và async

Một runtime có thể synchronous, một runtime khác asynchronous. Adapter cần xử lý scheduler, callback, cancellation và context propagation.

## 11. Identity, references và entity resolution

Interoperability đòi hỏi hai hệ thống biết một đối tượng ở bên này tương ứng với đối tượng nào bên kia.

### 11.1. Stable IDs

Nên dùng stable IDs cho:
- Entity.
- Schema.
- Operation.
- Event.
- Workflow.
- Module.
- Rule.
- Field nếu cần compatibility tracking.

Tên hiển thị có thể đổi; identity nên ổn định nếu semantics vẫn là cùng một element.

### 11.2. Natural key và surrogate key

Natural key đến từ domain, như country code. Surrogate key được tạo riêng như UUID. Mapping cần xác định key nào dùng để join hoặc resolve reference.

### 11.3. External references

Một DSL model có thể tham chiếu resource bên ngoài qua URI hoặc registry ID. Cần xác định:
- Namespace.
- Authority.
- Version.
- Resolution endpoint.
- Cache.
- Expiry.
- Access policy.

### 11.4. Duplicate identity

Khi import hai artifact có cùng ID nhưng nội dung khác, cần conflict policy. Không nên tự merge chỉ vì ID trùng.

### 11.5. Identity migration

Khi đổi ID scheme, cần alias hoặc migration mapping để consumer cũ tiếp tục resolve trong thời gian chuyển đổi.

## 12. Versioning và compatibility

Một interface có thể thay đổi độc lập với DSL source. Cần versioning ở nhiều lớp.

### 12.1. Format version

Format version xác định cấu trúc serialization. Ví dụ JSON document schema version 2.

### 12.2. Contract version

Contract version xác định public API/event interface và compatibility promises.

### 12.3. DSL language version

DSL language version xác định grammar và language semantics.

### 12.4. Runtime version

Runtime version có thể thay đổi operation behavior, scheduling hoặc error mapping dù source không đổi.

### 12.5. Backward compatibility

Một thay đổi backward-compatible khi consumer cũ vẫn hoạt động theo contract được bảo đảm. Ví dụ thêm optional response field thường ít rủi ro hơn xóa field, nhưng strict decoders có thể không chấp nhận field mới.

### 12.6. Forward compatibility

Consumer cũ có thể xử lý artifact mới trong phạm vi thiết kế, ví dụ bỏ qua unknown fields hoặc giữ unknown enum values. Cần ghi rõ policy.

### 12.7. Compatibility matrix

Một matrix có thể mô tả:

| Producer | Consumer | Compatibility |
|---|---|---|
| Schema v1 | Reader v1 | Native |
| Schema v2 | Reader v1 | Chỉ nếu thay đổi additive |
| Schema v1 | Reader v2 | Cần default/migration rules |
| Schema v2 | Reader v2 | Native |

Ma trận thực tế phụ thuộc schema format và policy của dự án.

### 12.8. Deprecation và sunset

Một field, operation hoặc format có thể được deprecated trước khi loại bỏ. Cần thông báo:
- Replacement.
- Thời điểm bắt đầu deprecation.
- Sunset date.
- Migration guide.
- Usage telemetry nếu có.
- Owner hỗ trợ.

## 13. Schema evolution và contract governance

Schema thường được nhiều service cùng sử dụng. Thay đổi schema cần quy trình governance.

### 13.1. Compatibility rules

Có thể phân loại thay đổi:
- Additive.
- Breaking.
- Behavior-changing.
- Security-impacting.
- Documentation-only.

### 13.2. Schema registry

Registry có thể lưu schema versions, compatibility policy, owner và references. DSL tooling có thể resolve schema theo immutable ID hoặc version.

### 13.3. Contract review

Review cần xét consumer impact, field semantics, privacy, retention và migration path. Chỉ compile thành công không chứng minh contract an toàn để phát hành.

### 13.4. Consumer-driven contracts

Consumer có thể công bố assumptions mà họ cần từ provider. Contract tests xác nhận provider vẫn đáp ứng các expectations đó.

### 13.5. Dependent artifact graph

Một schema có thể được dùng bởi nhiều endpoint, event và workflow. Tooling nên hiển thị dependency graph để xác định blast radius khi thay đổi.

## 14. Security và trust boundaries khi liên thông

Mỗi integration tạo thêm một boundary nơi dữ liệu và identity đi qua hệ thống khác.

### 14.1. Authentication across systems

Cần xác định identity được xác minh bằng:
- OAuth/OIDC.
- Mutual TLS.
- Signed messages.
- Workload identity.
- API keys nếu policy cho phép.

Không nên chuyển một user token sang audience không phù hợp.

### 14.2. Authorization propagation

Khi service A gọi service B thay mặt user, cần giữ actor/subject/delegation context theo policy. Service B phải quyết định quyền của request theo trust model của nó.

### 14.3. Tenant context

Tenant ID cần được xác minh từ trusted identity hoặc routing context. Không tin tenant field chỉ vì nó xuất hiện trong payload.

### 14.4. Data classification

Schema có thể đánh dấu:
- Public.
- Internal.
- Confidential.
- Restricted.
- Personal data.
- Secret.

Adapter và export tool phải giữ classification hoặc áp dụng redaction theo policy.

### 14.5. Secret handling

Không serialize credential vào artifact chia sẻ hoặc log. Secret reference có thể được truyền qua secret manager identifier, không phải secret value.

### 14.6. Untrusted schemas and documents

Parser cần giới hạn payload size, nesting và external references. Với XML, JSON hoặc YAML import, cần bảo vệ khỏi entity expansion, path traversal, unsafe tags và parser resource exhaustion.

### 14.7. Supply chain

External schema, plugin và generator cần version pinning, integrity verification và trusted source policy.

## 15. Reliability, transactions và delivery semantics

Liên thông qua network thường không có một transaction đơn giản bao trùm mọi service.

### 15.1. At-most-once, at-least-once và effectively-once

Message delivery có thể:
- At-most-once: có thể mất nhưng không giao lặp theo contract.
- At-least-once: có thể giao lặp.
- Exactly-once claim: thường chỉ đúng trong một phạm vi kỹ thuật nhất định.
- Effectively-once: đạt kết quả không trùng nhờ idempotency/deduplication.

DSL cần mô tả delivery guarantee thực tế thay vì dùng từ exactly-once chung chung.

### 15.2. Idempotency

Operation có side effect cần idempotency key hoặc deduplication strategy nếu có retry. Key phải có scope, retention và behavior khi payload khác nhau.

### 15.3. Ordering

Event có thể được sắp thứ tự theo partition, entity hoặc global stream. Consumer không nên giả định global ordering nếu protocol không bảo đảm.

### 15.4. Transaction boundary

Một transaction database không tự bao trùm HTTP call hoặc message publish. Có thể cần outbox, saga hoặc compensation.

### 15.5. Saga và compensation

Khi workflow gồm nhiều service, lỗi ở bước sau có thể cần action bù. Compensation là business operation riêng, không phải rollback distributed transaction tự động.

### 15.6. Timeout và retry

Timeout cần được propagate; retry cần backoff, jitter, retryable error classification và total deadline. Retry không có giới hạn có thể khuếch đại outage.

## 16. Adapters, connectors và anti-corruption layer

Adapter chuyển đổi giữa model của DSL và model của hệ thống đích.

### 16.1. Adapter responsibilities

Một adapter có thể đảm nhiệm:
- Protocol conversion.
- Data mapping.
- Type conversion.
- Identity resolution.
- Error translation.
- Authentication.
- Retry/timeout.
- Observability propagation.

### 16.2. Anti-corruption layer

Anti-corruption layer bảo vệ domain model của DSL khỏi việc rò rỉ khái niệm hoặc quirks của hệ thống bên ngoài.

Ví dụ external CRM dùng status codes 1, 2, 9. Domain DSL có thể map thành Active, Suspended và Archived thay vì để numeric codes lan khắp source.

### 16.3. Adapter contract

Adapter cần khai báo:
- Input/output schema.
- Supported versions.
- Mapping rules.
- Loss behavior.
- Timeout/retry.
- Error model.
- Security requirements.
- Resource limits.

### 16.4. Connector lifecycle

Connector cần:
- Configuration.
- Credential acquisition.
- Health check.
- Connection pool.
- Reconnect.
- Shutdown.
- Version upgrade.
- Revocation.

### 16.5. Avoid leaking vendor-specific types

Domain model không nên phụ thuộc trực tiếp vào proprietary SDK types nếu muốn giữ portability. Adapter nên chuyển sang type trung lập hoặc domain type.

## 17. Interoperability với IDE và developer tools

DSL có thể tích hợp với editor, language server, debugger và build tools.

### 17.1. Language Server Protocol

LSP cung cấp giao thức chung cho:
- Diagnostics.
- Completion.
- Hover.
- Definition.
- References.
- Rename.
- Formatting.
- Code actions.
- Semantic tokens.

DSL language server cần mapping source locations và semantic model sang LSP structures.

### 17.2. Debug Adapter Protocol

DAP cho phép IDE giao tiếp với debugger. Adapter cần map:
- Breakpoints.
- Stack frames.
- Variables.
- Step operations.
- Exception events.
- Runtime source locations.

### 17.3. Source maps

Khi DSL sinh code sang Java, Kotlin, JavaScript hoặc bytecode, source map giúp runtime error và debugger quay về DSL source.

### 17.4. Build integration

Build tool cần biết:
- DSL source files.
- Dependencies.
- Generated outputs.
- Incremental invalidation.
- Compiler version.
- Diagnostics format.
- Cache identity.

### 17.5. Formatter và linter

Formatter/linter có thể dùng AST hoặc canonical model. Cần bảo đảm formatter không đổi semantics và linter diagnostics có source mapping đúng.

## 18. Performance và scalability của integration

Interoperability thêm serialization, network và transformation cost.

### 18.1. Serialization cost

Object graph lớn có thể tốn CPU và memory khi chuyển thành JSON/XML/protobuf. Có thể dùng streaming hoặc zero-copy techniques nếu phù hợp.

### 18.2. Batching

Batch request giảm round trips nhưng có thể tăng payload và latency. Cần giới hạn batch size và hỗ trợ partial failures.

### 18.3. Caching

Schema và metadata có thể cache theo immutable version. Cache key cần có format version, tenant/namespace và authorization context khi dữ liệu bị giới hạn quyền.

### 18.4. Backpressure

Producer cần tôn trọng consumer capacity. Streaming adapter nên propagate backpressure và giới hạn buffer.

### 18.5. Connection pools

Connection pool cần bounded size, timeout và isolation theo dependency. Một integration bị chậm không nên chiếm toàn bộ pool của runtime.

### 18.6. Bulkhead

Bulkhead tách resource pool theo integration hoặc workload để lỗi một dependency không làm sập mọi connector.

## 19. Observability và traceability xuyên hệ thống

Một request có thể đi qua DSL runtime, API gateway, nhiều service và message broker. Cần khả năng nối các bước lại.

### 19.1. Correlation ID

Correlation ID giúp tìm các log liên quan cùng một business operation. Cần giữ ID qua HTTP headers, message metadata và workflow context.

### 19.2. Distributed tracing

Trace context giúp nối spans giữa service. Adapter phải propagate context đúng chuẩn và không tự tạo trace mới làm mất parent relationship.

### 19.3. Semantic attributes

Trace có thể ghi:
- DSL operation ID.
- Workflow ID.
- Schema version.
- Adapter name/version.
- External service.
- Retry attempt.
- Tenant class nếu policy cho phép.

### 19.4. Error mapping

Khi downstream trả lỗi, adapter nên ghi error category và source system. Không nên biến mọi lỗi thành một generic integration error.

### 19.5. Data privacy

Trace/log không nên chứa payload nhạy cảm hoặc secret. Có thể ghi payload size, schema ID và redacted fields thay vì raw body.

## 20. Testing interoperability

Một adapter có thể pass unit tests nhưng vẫn không tương thích với hệ thống thực tế.

### 20.1. Mapping tests

Kiểm tra field, type, enum, nullability, identity và semantics mapping.

### 20.2. Round-trip tests

Export rồi import lại artifact và so sánh canonical model trong phạm vi được cam kết. Với lossy conversion, test cần xác nhận loss report.

### 20.3. Contract tests

Consumer/provider contract tests xác nhận hai phía thống nhất schema và behavior.

### 20.4. Protocol integration tests

Test với broker, gateway hoặc service thật/compatible test environment để xác nhận framing, authentication, retry, ordering và timeout.

### 20.5. Compatibility matrix tests

Test producer/consumer versions theo matrix được hỗ trợ, gồm old reader/new writer và new reader/old writer khi cần.

### 20.6. Negative tests

Test:
- Unknown field.
- Unknown enum.
- Missing required field.
- Invalid schema version.
- Unsupported feature.
- Duplicate identity.
- Unauthorized reference.
- Timeout.
- Partial failure.
- Malformed payload.

### 20.7. Fault injection

Mô phỏng network partition, slow response, duplicate delivery, out-of-order event, broker outage và connector restart.

### 20.8. Golden artifacts

Lưu sample artifact và expected canonical model để phát hiện mapping drift khi compiler hoặc adapter đổi version.

## 21. Governance và quản lý integration contracts

Interoperability cần ownership và quy trình thay đổi.

### 21.1. Contract ownership

Mỗi API, event schema hoặc external mapping cần owner rõ. Owner chịu trách nhiệm compatibility, documentation và deprecation.

### 21.2. Registry và catalog

Registry có thể lưu:
- Schema IDs.
- Versions.
- Owners.
- Compatibility policy.
- References.
- Deprecation status.
- Security classification.

### 21.3. Change review

Thay đổi cần đánh giá:
- Consumer impact.
- Semantic drift.
- Security impact.
- Migration cost.
- Runtime support.
- Rollback plan.

### 21.4. Deprecation process

Cần thông báo trước, theo dõi usage, cung cấp replacement và thời gian migration. Không xóa interface chỉ vì producer đã đổi.

### 21.5. Documentation

Integration docs nên ghi supported versions, mapping limitations, examples, error behavior, auth requirements và operational ownership.

## 22. Những sai lầm thường gặp

1. **Chỉ chuyển đổi được syntax:** dữ liệu parse được nhưng semantics khác.
2. **Không có source of truth:** DSL và external schema drift.
3. **Mapping dựa vào tên:** hai field cùng tên bị coi là cùng meaning.
4. **Bỏ qua nullability:** absent và null bị nhập làm một.
5. **Không giữ stable identity:** references hỏng khi rename hoặc re-import.
6. **Silent data loss:** target format không hỗ trợ construct nhưng exporter bỏ qua.
7. **Không version mapping:** cùng artifact tạo kết quả khác sau upgrade.
8. **Giả định exactly-once:** duplicate message tạo side effect trùng.
9. **Không truyền deadline:** downstream tiếp tục xử lý sau timeout.
10. **Không propagate security context:** service nhận request không biết actor thực tế.
11. **Dùng vendor-specific types trong domain model:** giảm portability.
12. **Không có anti-corruption layer:** external quirks lan vào DSL.
13. **Không test compatibility matrix:** old/new clients không hoạt động cùng nhau.
14. **Cache thiếu tenant/version:** dữ liệu hoặc schema sai context được tái sử dụng.
15. **Không có ownership:** không ai chịu trách nhiệm khi contract thay đổi.
16. **Không ghi loss report:** người dùng tưởng export giữ nguyên mọi semantics.

## 23. Quy trình thiết kế interoperability cho DSL

Một quy trình thực tế:

1. **Xác định hệ thống cần kết nối:** API, database, workflow engine, broker, IDE hoặc code generator.
2. **Xác định use case:** import, export, runtime invocation, event exchange hay two-way editing.
3. **Chọn source of truth:** DSL source, canonical model hoặc external contract.
4. **Định nghĩa canonical concepts:** identity, type, operation, event, resource và relation.
5. **Chọn target standards:** OpenAPI, AsyncAPI, JSON Schema, Protobuf, BPMN, UML hoặc format phù hợp.
6. **Viết semantic mapping:** type, nullability, error, transaction, retry, ordering và security.
7. **Xác định fidelity:** lossless, partially lossless hay lossy; tạo report cho unsupported constructs.
8. **Thiết kế adapter boundary:** protocol, credentials, timeouts, retries, cancellation và resource limits.
9. **Quản lý identity và references:** stable IDs, namespaces, version và resolution.
10. **Thiết kế compatibility policy:** backward/forward compatibility, deprecation và migration.
11. **Bảo vệ trust boundaries:** authentication, authorization, tenant, classification và secret handling.
12. **Tích hợp tooling:** LSP, DAP, source maps, build và documentation.
13. **Thêm observability:** correlation, tracing, metrics và safe logging.
14. **Kiểm thử:** mapping, round-trip, contract, protocol, compatibility và fault injection.
15. **Thiết lập governance:** owner, registry, review và deprecation lifecycle.
16. **Triển khai từng integration:** đo hiệu năng, theo dõi error và mở rộng khi contract ổn định.

## 24. Kết luận

Khả năng liên thông giúp DSL trao đổi dữ liệu, mô hình và hành vi với các hệ thống khác. Một integration thực sự tương thích cần nhiều hơn định dạng chung: nó phải thống nhất type, identity, semantics, protocol, version, security và operational behavior.

Thiết kế nên xác định source of truth, canonical model, mapping rules và fidelity của import/export. Adapter cần giữ trust boundary, xử lý timeout/retry/cancellation, truyền identity và trace context, đồng thời báo rõ phần không thể biểu diễn. Schema governance, compatibility tests, round-trip tests và ownership giúp integration bền vững khi hệ thống phát triển. Khi các tầng syntax, data, model, semantic, protocol và runtime được thiết kế có chủ đích, DSL có thể kết nối với hệ sinh thái công cụ mà không làm mất ý nghĩa của domain model.

