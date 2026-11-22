# Mở rộng có kiểm soát

Một DSL (Domain-Specific Language) thường bắt đầu với một tập cú pháp và chức năng đủ nhỏ để giải quyết một nhóm bài toán cụ thể. Khi người dùng và hệ thống phát triển, họ có thể cần thêm kiểu dữ liệu, hàm, annotation, directive, backend, validator hoặc tích hợp với nền tảng khác. Nếu mọi nhu cầu đều được giải quyết bằng cách sửa trực tiếp compiler core, ngôn ngữ sẽ nhanh chóng trở nên khó bảo trì. Nếu cho phép mọi thành phần tự ý thêm cú pháp và hành vi, DSL lại dễ mất tính nhất quán, bảo mật và khả năng tương thích.

**Mở rộng có kiểm soát (controlled extensibility)** là cách thiết kế DSL để cho phép bổ sung năng lực qua những extension point được xác định trước, với interface, quyền hạn, quy tắc tương thích và giới hạn rõ ràng. Extension có thể mở rộng ngôn ngữ hoặc toolchain nhưng vẫn phải tuân thủ các nguyên tắc chung về parsing, typing, diagnostics, execution, security và lifecycle.

Ví dụ, một DSL mô tả hạ tầng có thể cho phép backend plugin:

~~~text
target "kubernetes" {
    provider = plugin("company.kubernetes", version = "2.1")
}

service "orders-api" {
    replicas = 3
    expose = http(port = 8080)
}
~~~

Plugin có thể chuyển model service thành resource của Kubernetes. Tuy nhiên, plugin cần tuân theo schema, capability và version contract của DSL. Nó không được tự ý thay đổi semantics của replicas hoặc truy cập secret ngoài phạm vi được cấp.

Trong chương **Mẫu thiết kế DSL**, mở rộng có kiểm soát là một quyết định kiến trúc quan trọng. Nó xác định phần nào là core language, phần nào là extension, ai có thể cài extension, cách extension phối hợp và cách hệ thống bảo vệ người dùng khỏi xung đột hoặc hành vi ngoài dự kiến.

## 1. Vì sao DSL cần khả năng mở rộng?

DSL được thiết kế cho một domain cụ thể, nhưng domain đó có thể thay đổi theo thời gian. Người dùng có thể cần:

- Thêm function hoặc built-in operation.
- Thêm type, literal hoặc annotation.
- Tích hợp provider hoặc backend mới.
- Thêm rule kiểm tra domain.
- Sinh output cho target khác.
- Kết nối với hệ thống build, CI hoặc editor.
- Thêm thư viện domain dùng chung.
- Tùy biến diagnostics hoặc formatting.

Nếu không có extension mechanism, mỗi thay đổi có thể yêu cầu sửa core, release compiler mới và yêu cầu mọi người nâng cấp.

### 1.1. Giảm coupling

Extension point cho phép module bên ngoài cung cấp behavior qua interface ổn định. Compiler core không cần biết chi tiết của từng provider hoặc plugin.

### 1.2. Hỗ trợ domain-specific variation

Một DSL platform có thể phục vụ nhiều tổ chức hoặc nền tảng. Extension cho phép mỗi nhóm thêm integration cần thiết mà không làm ngôn ngữ cơ bản phình to.

### 1.3. Tăng tốc đổi mới

Nhóm phát triển plugin có thể thử nghiệm tính năng độc lập. Nếu tính năng hữu ích và ổn định, nó có thể được đưa vào core ở phiên bản sau.

### 1.4. Giữ core nhỏ

Core nên chứa semantics và abstraction phổ biến. Những tích hợp đặc thù có thể nằm ngoài core để giảm dependency và phạm vi bảo trì.

### 1.5. Nhưng mở rộng không giới hạn gây rủi ro

Nếu extension có thể sửa grammar, ghi đè function hoặc thực thi code tùy ý, người dùng có thể không biết source DSL thực sự có nghĩa gì. Các plugin khác nhau có thể tạo cùng tên nhưng behavior khác, khiến kết quả phụ thuộc thứ tự load.

Mục tiêu là mở rộng năng lực trong một mô hình có thể dự đoán, kiểm tra và quản trị.

## 2. Extension point là gì?

**Extension point** là vị trí được thiết kế trước trong kiến trúc để thành phần bên ngoài có thể bổ sung behavior. Một extension point cần định nghĩa:

- Interface hoặc schema mà extension phải tuân thủ.
- Thời điểm extension được nạp và gọi.
- Dữ liệu đầu vào và đầu ra.
- Capability được cấp.
- Quy tắc lỗi và cancellation.
- Version compatibility.
- Cơ chế đăng ký và discovery.
- Quy tắc conflict resolution.

Một extension point tốt không chỉ là một callback tùy ý. Nó là một phần public contract của toolchain.

### 2.1. Extension API

Extension API định nghĩa các type và operation mà plugin có thể sử dụng. Ví dụ:

~~~typescript
interface DslExtension {
  id: string;
  apiVersion: string;
  initialize(context: ExtensionContext): void;
  dispose(): void;
}
~~~

Interface trên chỉ minh họa. API thật cần quy định thread safety, lifecycle, exception và quyền.

### 2.2. Extension manifest

Manifest mô tả metadata của plugin:

~~~yaml
id: company.kubernetes
version: 2.1.0
extensionApi: "3"
entrypoint: com.company.dsl.KubernetesExtension
capabilities:
  - emit-artifacts
  - read-semantic-model
~~~

Tool có thể kiểm tra manifest trước khi load plugin.

### 2.3. Extension registry

Registry lưu thông tin extension đã được phê duyệt, version, source và checksum. Registry có thể là local catalog hoặc service nội bộ.

### 2.4. Extension lifecycle

Một extension có thể trải qua các giai đoạn:

~~~mermaid
flowchart LR
    A[Discover] --> B[Validate manifest]
    B --> C[Resolve dependencies]
    C --> D[Check permissions]
    D --> E[Load]
    E --> F[Initialize]
    F --> G[Invoke]
    G --> H[Dispose]
~~~

Mỗi bước cần behavior rõ nếu thất bại. Ví dụ, extension không tương thích API phải bị từ chối trước khi được gọi.

## 3. Các lớp có thể mở rộng trong DSL

Không phải mọi extension đều thay đổi grammar. Có thể mở rộng ở nhiều lớp khác nhau.

| Lớp | Extension điển hình | Tác động |
|---|---|---|
| Syntax | Grammar plugin, annotation | Source language |
| Semantic | Type, validator, resolver | Ý nghĩa chương trình |
| Standard library | Function, module | Năng lực biểu thức |
| Runtime | Host function, adapter | Hành vi thực thi |
| Backend | Code generator, target | Artifact đầu ra |
| Tooling | Formatter, linter, language server | Trải nghiệm phát triển |
| Integration | Registry, cloud provider, CI | Kết nối hệ thống |

### 3.1. Syntax extension

Syntax extension thêm construct mới hoặc mở rộng grammar. Đây là loại có tác động lớn vì có thể thay đổi cách parser hiểu source.

### 3.2. Semantic extension

Semantic extension bổ sung type, rule, annotation hoặc name resolver mà không nhất thiết thay grammar.

### 3.3. Library extension

Library extension thêm function hoặc module có thể gọi từ source DSL. Cần định nghĩa type signature và side effect.

### 3.4. Runtime extension

Runtime extension cung cấp host function hoặc adapter để DSL tương tác với hệ thống bên ngoài.

### 3.5. Backend extension

Backend extension chuyển IR hoặc semantic model thành output cho target cụ thể.

### 3.6. Tooling extension

Tooling extension có thể thêm formatter, linter, code action, documentation generator hoặc test reporter.

### 3.7. Integration extension

Integration extension kết nối package registry, cloud platform, database, build system hoặc observability service.

## 4. Thiết kế core language và extension boundary

Core language nên giữ những khái niệm ổn định, phổ biến và cần semantics thống nhất. Extension nên chứa phần thay đổi theo nền tảng hoặc nhu cầu riêng.

Ví dụ:

~~~text
Core:
    service
    variable
    expression
    type
    dependency
    resource

Extensions:
    kubernetes deployment
    cloud database
    organization policy
    custom validation
~~~

### 4.1. Core contract

Core cần định nghĩa:

- Grammar cơ bản.
- AST/IR public.
- Type system.
- Name resolution rules.
- Diagnostic model.
- Extension lifecycle.
- Capability model.

### 4.2. Stable abstractions

Extension nên phụ thuộc abstraction ổn định như Resource, TypeRef, Diagnostic và ArtifactWriter, không phụ thuộc private class hoặc internal compiler pass.

### 4.3. Keep implementation private

Không expose toàn bộ compiler internals chỉ để plugin tiện sử dụng. Mỗi API được expose sẽ trở thành một phần compatibility surface cần duy trì.

### 4.4. Extension boundary cần rõ

Nếu plugin được phép sửa AST sau type checking, nó có thể làm mất invariant mà code generator dựa vào. Tốt hơn nên quy định plugin chạy ở phase cụ thể và chỉ được thay đổi loại dữ liệu được phép.

### 4.5. Fail closed

Nếu extension không được tìm thấy, sai version hoặc thiếu capability, tool nên báo lỗi rõ. Không âm thầm bỏ qua extension nếu điều đó làm thay đổi semantics hoặc output.

## 5. Mở rộng syntax có kiểm soát

Cho phép plugin thêm syntax rất linh hoạt nhưng cũng dễ gây ambiguity.

### 5.1. Syntax namespace

Có thể yêu cầu extension syntax nằm trong namespace:

~~~text
@kubernetes.deployment {
    replicas = 3
}
~~~

Namespace giúp tránh va chạm keyword giữa plugin.

### 5.2. Annotation thay vì grammar mới

Nếu mục tiêu chỉ là gắn metadata vào declaration, annotation có thể đủ:

~~~text
@cloud.region("asia")
service "orders" {
    replicas = 3
}
~~~

Annotation thường ít tác động grammar hơn so với việc cho plugin định nghĩa production rule mới.

### 5.3. Extension block

DSL có thể cung cấp block có namespace:

~~~text
service "orders" {
    replicas = 3

    extension "company.observability" {
        metrics = true
        tracing = true
    }
}
~~~

Parser core chỉ cần hiểu cấu trúc extension block; plugin chịu trách nhiệm validate nội dung theo schema của nó.

### 5.4. Grammar fragment

Nếu thật sự cần grammar fragment, cần quy định:

- Plugin đăng ký production ở đâu.
- Token hoặc keyword được namespace thế nào.
- Precedence và associativity.
- Ambiguity detection.
- Parser generation hoặc dynamic parsing.
- Language version và extension version.

### 5.5. Không để plugin ghi đè grammar core

Một plugin không nên thay đổi ý nghĩa keyword hoặc production cốt lõi. Nếu cần thay đổi language semantics, đó là language evolution và cần proposal/versioning riêng.

### 5.6. Syntax compatibility

Syntax extension cần có declaration rõ trong project manifest. Khi mở source, tool phải biết extension nào được bật và version nào được dùng để parse.

## 6. Mở rộng semantic model

Semantic extension bổ sung quy tắc kiểm tra hoặc khái niệm domain sau khi source đã parse.

Ví dụ một policy extension kiểm tra:

~~~text
service "orders" {
    replicas = 3
    network = network.public
}
~~~

Extension có thể phát diagnostic nếu service xử lý dữ liệu nhạy cảm nhưng dùng network public.

### 6.1. Validator extension

Validator nhận semantic model và trả diagnostics. Nó không nên tự sửa source hoặc tạo side effect nếu contract chỉ cho phép kiểm tra.

### 6.2. Type extension

Plugin có thể đăng ký type domain như Money, Duration hoặc CloudRegion. Cần định nghĩa literal, equality, serialization và operator hợp lệ.

### 6.3. Resolver extension

Resolver có thể tìm resource hoặc symbol từ registry bên ngoài. Cần timeout, cache, credential scope và deterministic behavior.

### 6.4. Constraint extension

Constraint extension bổ sung rule như min/max, naming policy hoặc dependency requirement. Rule cần có code ổn định và source location.

### 6.5. Semantic invariants

Sau mỗi phase, compiler nên xác định invariant. Extension chỉ được chạy ở phase có dữ liệu phù hợp và không được phá invariant đã được bảo đảm.

## 7. Mở rộng standard library và built-in function

Standard library cung cấp function và module dùng trong DSL.

Ví dụ:

~~~text
region = cloud.currentRegion()
image = registry.resolve("orders-api", tag = "4.2")
~~~

### 7.1. Function signature

Mỗi function cần có:

- Tên và namespace.
- Parameter type.
- Return type.
- Optional/default argument.
- Error behavior.
- Side effect.
- Resource cost.

### 7.2. Pure function

Pure function không thay đổi trạng thái bên ngoài và cùng input luôn cho cùng output. Loại function này dễ test, cache và evaluate an toàn.

### 7.3. Effectful function

Function gọi network, đọc environment hoặc ghi resource có side effect. Cần khai báo effect và capability, không nên làm nó trông giống arithmetic function thuần.

### 7.4. Namespace

Đặt function trong namespace plugin để tránh tên chung:

~~~text
company.registry.resolve(...)
~~~

### 7.5. Overload

Nếu cho phép overload, cần quy tắc resolution rõ. Extension không nên đăng ký overload mơ hồ khiến cùng source chọn function khác theo thứ tự load.

### 7.6. Cost metadata

Function có thể khai báo cost class hoặc resource budget. External call, regex và large collection operation cần được tính khác function arithmetic nhỏ.

## 8. Runtime extension và host function

Runtime extension cho phép DSL gọi chức năng do host application cung cấp.

Ví dụ:

~~~text
result = host.inventory.lookup(itemId)
~~~

### 8.1. Host API contract

Host function cần có signature, type mapping, error mapping, timeout và cancellation behavior.

### 8.2. Capability

Thay vì expose toàn bộ host application, chỉ cấp capability cần thiết:

~~~text
capabilities:
    - inventory.read
    - metrics.emit
~~~

### 8.3. Effect declaration

Có thể phân loại function:

- Pure: không side effect.
- Read-only: đọc dữ liệu bên ngoài.
- Mutating: thay đổi trạng thái.
- Privileged: thao tác nhạy cảm cần permission riêng.

### 8.4. Determinism

Nếu function đọc thời gian hoặc trạng thái bên ngoài, evaluation không còn deterministic. Cần ghi rõ để cache, replay và test không giả định kết quả cố định.

### 8.5. Cancellation

Host function cần nhận cancellation token hoặc deadline để runtime có thể dừng operation khi request bị hủy.

### 8.6. Error translation

Không để exception nội bộ của host lộ stack trace hoặc secret vào DSL diagnostic. Chuyển thành error code và context đã được redacted.

## 9. Backend extension và target plugin

Backend chuyển semantic model hoặc IR thành artifact cho một target.

Ví dụ:

~~~text
compile project {
    target = "kubernetes"
    output = "./generated"
}
~~~

### 9.1. Backend interface

Một backend API có thể nhận:

- Typed IR.
- Target configuration.
- Artifact writer.
- Diagnostics sink.
- Resource budget.
- Cancellation context.

và trả:

- Generated artifacts.
- Diagnostics.
- Metadata.
- Status.

### 9.2. IR stability

Backend nên phụ thuộc IR có version. Thay đổi IR cần compatibility policy hoặc adapter.

### 9.3. Capability negotiation

Backend có thể công bố capability như support autoscaling, secrets, network policy hoặc multi-region. Compiler kiểm tra source có dùng tính năng mà target không hỗ trợ không.

### 9.4. Deterministic generation

Cùng IR và configuration nên tạo output ổn định nếu backend tuyên bố deterministic. Tránh timestamp hoặc random ordering không cần thiết.

### 9.5. Artifact ownership

Backend chỉ nên ghi vào output location được cấp. Không ghi đè file source hoặc đường dẫn ngoài workspace.

### 9.6. Unsupported feature

Nếu backend không hỗ trợ một construct, phát diagnostic rõ. Không âm thầm bỏ qua thuộc tính có ảnh hưởng tới behavior.

## 10. Extension registry và discovery

Extension cần được tìm thấy và resolve theo cách có thể tái lập.

### 10.1. Registry

Registry có thể lưu:

- Extension ID.
- Version.
- Publisher.
- Artifact location.
- Checksum/signature.
- API compatibility range.
- Required capability.
- Dependency.
- Deprecation status.

### 10.2. Discovery

Tool có thể tìm extension từ:

- Project manifest.
- Local plugin directory.
- Configured registry.
- Built-in catalog.

Không nên tự động load mọi binary trong một thư mục không tin cậy.

### 10.3. Explicit dependency

Project nên khai báo extension cần dùng thay vì dựa vào plugin tình cờ đã cài trên máy developer.

### 10.4. Lockfile

Lockfile có thể pin plugin version và checksum để build ở CI và developer dùng cùng extension.

### 10.5. Offline behavior

Tài liệu cần nêu extension được cache thế nào và build offline có thể resolve dependency ra sao.

## 11. Namespace và conflict resolution

Khi nhiều extension được cài, xung đột tên và behavior có thể xảy ra.

### 11.1. Unique extension ID

Dùng ID có namespace rõ, thường gắn với publisher hoặc organization.

### 11.2. Symbol namespace

Tên function, type, annotation và block nên được namespace hoặc đăng ký trong catalog có collision detection.

### 11.3. Duplicate registration

Nếu hai plugin đăng ký cùng tên và cùng scope, tool nên báo conflict trừ khi có quy tắc override rõ ràng.

### 11.4. Không phụ thuộc load order

Kết quả compile không nên thay đổi chỉ vì thứ tự plugin được load, trừ khi order là một phần contract được khai báo rõ.

### 11.5. Explicit override

Nếu cho phép override, cần syntax và policy tường minh:

~~~text
extension "company.custom-policy" {
    overrides = "standard.naming-policy"
}
~~~

Override cần được review và ghi vào diagnostic hoặc build metadata để truy vết.

### 11.6. Version conflict

Hai extension có thể yêu cầu hai version không tương thích của cùng dependency. Resolver cần phát hiện conflict trước khi load.

## 12. Dependency giữa các extension

Extension có thể phụ thuộc extension khác hoặc core capability.

Ví dụ:

~~~yaml
id: company.cloud-policy
version: 1.4.0
dependencies:
  - id: company.cloud-model
    version: ">=2.0 <3.0"
~~~

### 12.1. Dependency graph

Resolver xây graph và kiểm tra cycle, version constraint và dependency availability.

### 12.2. Optional dependency

Nếu dependency optional, extension cần xác định behavior khi dependency vắng mặt. Không nên tạo output một phần mà không báo.

### 12.3. Transitive dependency

Dependency gián tiếp cần được pin và kiểm tra license/security như dependency trực tiếp.

### 12.4. Isolation

Hai plugin có thể cần version library khác nhau. Classloader hoặc process isolation có thể giảm xung đột runtime.

### 12.5. Reproducible resolution

Lockfile ghi lại dependency graph thực tế. Cùng manifest và lockfile nên resolve cùng artifact.

## 13. Versioning và compatibility của extension API

Extension API là contract lâu dài giữa host và plugin.

### 13.1. API version

Phân biệt:

- DSL language version.
- Compiler version.
- Extension API version.
- Plugin version.
- Backend target version.

Chúng có thể có chu kỳ release khác nhau.

### 13.2. Compatibility range

Plugin manifest có thể khai báo range compiler API được hỗ trợ. Host kiểm tra trước khi initialize.

### 13.3. Semantic versioning

Nếu extension API dùng SemVer, cần định nghĩa rõ thay đổi nào được coi là breaking, kể cả behavior và lifecycle.

### 13.4. Deprecation

API cũ cần thời gian cảnh báo, replacement và migration guide. Không xóa callback hoặc field ngay khi plugin còn được hỗ trợ.

### 13.5. Capability negotiation

Host và plugin có thể thương lượng capability trước khi hoạt động. Plugin chỉ dùng tính năng host công bố hỗ trợ.

### 13.6. Unknown fields và forward compatibility

Manifest parser có thể bỏ qua metadata chưa biết nếu schema cho phép. Nhưng field ảnh hưởng semantics không được bỏ qua âm thầm.

## 14. Bảo mật extension

Extension có thể chạy code bên ngoài compiler core, do đó cần một mô hình quyền rõ.

### 14.1. Trust levels

Có thể phân loại:

- Built-in extension do dự án kiểm soát.
- Verified extension từ publisher tin cậy.
- Internal extension được quản lý trong tổ chức.
- Third-party extension.
- Untrusted extension.

Trust level cần ảnh hưởng đến quyền và cách chạy, không chỉ là nhãn hiển thị.

### 14.2. Least privilege

Chỉ cấp capability cần thiết. Plugin tạo manifest có thể không cần network hoặc quyền đọc toàn bộ repository.

### 14.3. Signature và provenance

Xác minh chữ ký artifact và publisher giúp phát hiện extension bị thay đổi. Checksum đơn thuần xác nhận nội dung khớp giá trị đã biết, nhưng không tự xác minh ai phát hành.

### 14.4. Sandbox

Plugin không tin cậy nên chạy trong process, container hoặc runtime sandbox phù hợp. Giới hạn filesystem, network, CPU, memory và child process.

### 14.5. Secret isolation

Không truyền secret vào plugin trừ khi capability cụ thể yêu cầu. Nếu cần, cấp secret theo scope và thời hạn ngắn.

### 14.6. Supply chain

Kiểm tra dependency, license, provenance và security advisory của plugin. Registry cần có cơ chế revoke hoặc quarantine extension bị xâm phạm.

### 14.7. Audit

Ghi nhận plugin nào được load, version, checksum, capability và hành động quan trọng. Không log secret hoặc payload nhạy cảm.

## 15. Resource limits và reliability

Extension có thể gây cạn tài nguyên hoặc làm host mất ổn định.

Giới hạn nên bao gồm:

- Initialization timeout.
- Callback timeout.
- CPU và memory.
- Số thread/process.
- Số external calls.
- Output bytes và generated files.
- Diagnostic count.
- Concurrency.
- Queue depth.

### 15.1. Per-plugin budget

Mỗi plugin nhận budget riêng trong tổng execution budget. Một plugin không được tiêu thụ toàn bộ tài nguyên khiến extension khác không chạy.

### 15.2. Cancellation

Host truyền cancellation token và deadline. Plugin cần dừng operation và cleanup khi bị hủy.

### 15.3. Circuit breaker

Nếu plugin liên tục lỗi hoặc timeout, host có thể tạm ngừng gọi nó và báo trạng thái degraded. Circuit breaker cần policy rõ và không che giấu lỗi semantics.

### 15.4. Failure isolation

Lỗi plugin nên được cô lập trong phạm vi được thiết kế. Nếu plugin bắt buộc để tạo output chính xác, không được âm thầm tiếp tục như thể build thành công.

### 15.5. Retry

Chỉ retry operation idempotent hoặc có cơ chế chống lặp. Plugin callback tạo resource không được retry mù quáng.

## 16. Determinism và reproducibility

Controlled extensibility cần bảo đảm cùng input và cùng extension set tạo kết quả có thể dự đoán.

### 16.1. Deterministic registration

Extension registry và dependency resolution phải có thứ tự hoặc semantics ổn định.

### 16.2. Pure extension phase

Validator hoặc transformation phase nên tránh đọc thời gian, random hoặc network nếu không cần.

### 16.3. External state

Nếu extension truy vấn registry hoặc cloud API, kết quả phụ thuộc trạng thái bên ngoài. Có thể snapshot dữ liệu hoặc ghi metadata vào build record.

### 16.4. Stable output ordering

Map, symbol hoặc resource collection cần có ordering deterministic nếu output được version control hoặc so sánh golden.

### 16.5. Cache correctness

Cache key cần chứa extension version, configuration và dependency state ảnh hưởng kết quả. Nếu bỏ sót, cache có thể trả output từ plugin version cũ.

### 16.6. Build provenance

Ghi lại extension set và digest trong artifact metadata để tái tạo build.

## 17. Extension lifecycle và state management

Plugin lifecycle cần được định nghĩa từ lúc discovery tới shutdown.

### 17.1. Initialization

Initialize nên kiểm tra configuration, capability và dependency. Tránh thực hiện side effect lớn khi load nếu chưa có execution context.

### 17.2. Stateless extension

Extension stateless dễ chạy song song, cache và test. Nếu có thể, ưu tiên state nằm trong request context.

### 17.3. Stateful extension

Nếu plugin giữ cache hoặc session, cần xác định lifetime, concurrency, cleanup và tenant isolation.

### 17.4. Thread safety

Host cần biết callback có thể được gọi đồng thời hay không. Nếu plugin không thread-safe, host có thể serialize call nhưng cần tính tới throughput.

### 17.5. Hot reload

Hot reload cần xử lý classloader, state migration và resource cleanup. Không unload plugin nếu thread hoặc resource của nó vẫn còn hoạt động.

### 17.6. Shutdown

Dispose cần có timeout và không được giữ process vô hạn. Host có thể force terminate worker sau deadline.

## 18. Mở rộng mà không phá grammar core

Một mẫu thiết kế hữu ích là giữ grammar nhỏ, ổn định và dùng extension block hoặc annotation cho domain-specific metadata.

Ví dụ:

~~~text
service "orders" {
    replicas = 3

    extension "company.security" {
        dataClassification = "confidential"
        requireEncryption = true
    }
}
~~~

### 18.1. Generic extension node

Parser tạo node generic gồm extension ID và body. Plugin riêng validate body theo schema của nó.

### 18.2. Schema-driven body

Manifest của extension công bố schema để IDE có thể completion và validate mà không cần parser core hiểu mọi field.

### 18.3. Unknown extension

Nếu extension không được cài, compiler có thể phát lỗi rõ hoặc chỉ cho phép pass-through trong mode được xác định. Không bỏ qua extension nếu nó ảnh hưởng output.

### 18.4. IDE support

Language server có thể load schema metadata để cung cấp completion, hover và diagnostics cho extension block.

### 18.5. Extension-specific version

Block có thể chỉ định version hoặc project manifest pin version, giúp cùng source không đổi semantics khi plugin được cập nhật.

## 19. Mở rộng compiler qua phase hook

Compiler có nhiều phase. Extension có thể được gắn vào phase cụ thể:

~~~mermaid
flowchart LR
    A[Source] --> B[Parse]
    B --> C[AST]
    C --> D[Semantic analysis]
    D --> E[Typed IR]
    E --> F[Optimization]
    F --> G[Backend]
    G --> H[Artifact]
    X[Syntax extension] -.-> B
    Y[Validator] -.-> D
    Z[IR transform] -.-> E
    W[Backend plugin] -.-> G
~~~

### 19.1. Parse phase

Syntax extension có thể cung cấp parser rule hoặc custom node, nhưng cần bảo vệ grammar compatibility.

### 19.2. Semantic phase

Validator kiểm tra domain rule trên AST hoặc semantic model.

### 19.3. IR transformation

Plugin có thể biến đổi IR nếu compiler định nghĩa transformation contract. Cần validate IR sau mỗi plugin hoặc sau một nhóm transformation.

### 19.4. Optimization phase

Optimization extension phải bảo toàn semantics. Có thể dùng equivalence test hoặc interpreter/reference evaluator để kiểm tra transformation.

### 19.5. Backend phase

Backend nhận IR đã được kiểm tra và sinh artifact. Nó không nên tự diễn giải lại source text bằng một parser riêng khác semantics.

### 19.6. Phase ordering

Nếu nhiều plugin cùng chạy ở một phase, thứ tự có thể ảnh hưởng kết quả. Nên dùng dependency hoặc priority declaration có giới hạn và phát hiện cycle.

## 20. Extension cho validation và policy

Policy extension giúp tổ chức thêm quy tắc domain mà không thay đổi core grammar.

Ví dụ:

~~~text
policy "production-baseline" {
    requireTLS = true
    requireOwner = true
    forbidPublicDatabase = true
    minimumReplicas = 2
}
~~~

### 20.1. Advisory và blocking rule

Rule có thể phát warning hoặc error. Severity nên được khai báo theo policy và có thể override chỉ bởi role được phép.

### 20.2. Policy scope

Policy có thể áp dụng cho project, module, environment hoặc resource. Scope cần rõ để không có rule vô tình áp dụng toàn hệ thống.

### 20.3. Policy composition

Nhiều policy có thể kết hợp bằng AND, OR hoặc precedence. Cần xác định conflict semantics, nhất là khi một policy cho phép và policy khác cấm.

### 20.4. Policy provenance

Diagnostic nên chỉ ra rule và policy source đã phát sinh nó. Người dùng cần biết có thể sửa source, config hay xin exception.

### 20.5. Exception management

Exception cần owner, lý do, phạm vi và thời hạn. Không nên tạo global ignore không hết hạn.

## 21. Extension cho editor và developer tooling

Extension có thể bổ sung trải nghiệm IDE:

- Completion provider.
- Hover provider.
- Code action.
- Formatter rule.
- Diagnostic rule.
- Semantic token provider.
- Debug adapter.

### 21.1. Capability registration

Tooling host nên biết plugin hỗ trợ feature nào và đăng ký tương ứng.

### 21.2. Latency budget

Editor feature cần phản hồi nhanh. Completion hoặc hover plugin nên có deadline ngắn và hỗ trợ cancellation khi người dùng tiếp tục gõ.

### 21.3. Partial source

Plugin cần xử lý AST chưa hoàn chỉnh hoặc node lỗi mà không crash.

### 21.4. Consistent diagnostics

Diagnostic từ plugin nên dùng cùng severity, source range, code và related location model với compiler core.

### 21.5. Formatting ownership

Nhiều formatter plugin có thể xung đột. Chỉ nên có một formatter authoritative cho cùng file hoặc định nghĩa rõ composition order.

## 22. Testing extension contract

Extension cần được test như một public integration boundary.

### 22.1. API compatibility tests

Kiểm tra plugin compile/load với các host version được công bố hỗ trợ.

### 22.2. Manifest validation

Test missing field, sai version, duplicate ID, dependency conflict và capability không hợp lệ.

### 22.3. Lifecycle tests

Kiểm tra initialize, invoke, error, cancellation, dispose và repeated load/unload.

### 22.4. Conformance suite

Host có thể cung cấp test suite chung để plugin xác minh:

- Input/output schema.
- Diagnostic contract.
- Thread safety expectations.
- Resource budget.
- Capability enforcement.
- Determinism.

### 22.5. Negative tests

Test plugin cố truy cập file ngoài scope, gọi network khi không được cấp, ghi output vượt giới hạn hoặc đăng ký tên xung đột.

### 22.6. Compatibility matrix

Test nhiều cặp host/plugin version và target backend version.

### 22.7. Integration tests

Chạy project mẫu qua toàn pipeline với plugin thật trong sandbox. Mock không thể xác nhận đầy đủ classloader, IPC, permission và artifact generation.

## 23. Documentation và discoverability của extension

Extension ecosystem cần tài liệu rõ để developer biết plugin làm gì và có an toàn, tương thích hay không.

Một trang extension nên nêu:

- Extension ID và publisher.
- Version và API compatibility.
- Chức năng.
- Installation source.
- Dependency.
- Capability yêu cầu.
- Configuration schema.
- Example.
- Resource limit.
- Security notes.
- Support và deprecation policy.

### 23.1. Registry metadata

Catalog nên hiển thị publisher, version, signature status và capability trước khi người dùng cài.

### 23.2. Quick start

Cung cấp project mẫu nhỏ và lệnh xác minh extension đã load.

### 23.3. Troubleshooting

Nêu lỗi version mismatch, missing capability, dependency resolution và initialization failure.

### 23.4. Support status

Ghi rõ extension còn được duy trì hay đã deprecated/archived.

## 24. Governance và kiểm soát hệ sinh thái extension

Khi extension được nhiều nhóm phát triển, cần chính sách quản trị.

### 24.1. Admission policy

Quy định extension nào được cài trong production hoặc môi trường doanh nghiệp.

### 24.2. Review và approval

Extension có quyền cao hoặc ảnh hưởng output cần security review và owner approval.

### 24.3. Publisher identity

Quản lý publisher ID và signing key. Có quy trình thu hồi khi key bị lộ.

### 24.4. Deprecation và removal

Thông báo thời gian ngừng hỗ trợ, replacement và cách migrate.

### 24.5. Emergency revocation

Host cần khả năng chặn extension bị xâm phạm hoặc có lỗ hổng nghiêm trọng. Policy cần ghi nhận tác động tới project đang phụ thuộc.

### 24.6. Extension tiers

Có thể phân loại stable, preview, experimental và deprecated. Mỗi tier cần định nghĩa mức hỗ trợ và compatibility expectation.

## 25. Resource isolation và quota cho extension

Extension cần được cấp ngân sách để không ảnh hưởng host hoặc plugin khác.

Ví dụ:

~~~yaml
extensionPolicy:
  maxInitializationTime: 2s
  maxCallbackTime: 500ms
  maxMemory: 64Mi
  maxCpuTime: 1s
  maxGeneratedFiles: 100
  maxOutputBytes: 5Mi
  network:
    enabled: false
~~~

Đây là ví dụ minh họa. Giá trị và khả năng enforcement phụ thuộc runtime.

### 25.1. Per-extension quota

Mỗi extension có quota riêng về CPU, memory, output và external calls.

### 25.2. Shared budget

Tổng extension execution vẫn phải nằm trong compilation budget. Per-plugin limit không thay thế global limit.

### 25.3. Worker isolation

Plugin không tin cậy nên chạy trong worker riêng có thể terminate. Host process giữ quyền kiểm soát output và lifecycle.

### 25.4. Resource accounting

Ghi nhận usage theo extension ID/version để phát hiện plugin tiêu thụ bất thường.

## 26. Ví dụ tổng hợp: backend plugin có kiểm soát

Giả sử DSL platform muốn hỗ trợ Kubernetes thông qua backend plugin.

Manifest:

~~~yaml
id: company.kubernetes
version: 2.1.0
extensionApi: "3"
targets:
  - kubernetes
capabilities:
  - read-typed-ir
  - emit-artifacts
dependencies:
  - id: company.cloud-model
    version: ">=2.0 <3.0"
~~~

Project:

~~~text
project "commerce" {
    languageVersion = "2"
    extensions = [
        extension("company.kubernetes", "2.1.0")
    ]

    target "kubernetes" {
        namespace = "commerce"
    }

    service "orders-api" {
        replicas = 3
        port = 8080
    }
}
~~~

### 26.1. Discovery và validation

Tool tìm extension theo ID, kiểm tra checksum/signature, version và dependency. Nếu extension API không tương thích, compile dừng với diagnostic.

### 26.2. Capability check

Host cấp typed IR read access và artifact write access trong output directory. Plugin không nhận network hoặc secret capability vì backend chỉ sinh manifest.

### 26.3. Compilation

Compiler tạo IR, kiểm tra policy và chuyển IR tới backend. Backend tạo Kubernetes manifests theo schema đã công bố.

### 26.4. Output validation

Host kiểm tra output file count, size, schema và target capability. Plugin không được ghi file ngoài output directory.

### 26.5. Reproducibility

Build record ghi plugin ID, version, digest, compiler version và configuration hash.

### 26.6. Failure handling

Nếu plugin timeout hoặc phát output không hợp lệ, build thất bại và artifact tạm bị loại bỏ. Diagnostic nêu extension, phase và lỗi đã chuẩn hóa.

## 27. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Cho plugin sửa tùy ý grammar core | Ambiguity và source semantics không ổn định | Extension syntax có namespace hoặc annotation |
| Expose toàn bộ compiler internals | Plugin phụ thuộc implementation detail | Public API nhỏ và versioned |
| Không có extension ID duy nhất | Trùng tên và khó truy vết | Namespaced ID và publisher identity |
| Load plugin theo thứ tự ngẫu nhiên | Output thay đổi giữa các máy | Dependency graph và deterministic ordering |
| Plugin ghi đè function không khai báo | Consumer có semantics khác | Conflict detection và explicit override |
| Không kiểm tra API version | Plugin crash hoặc tạo output sai | Compatibility validation trước load |
| Không pin plugin dependency | Build không tái lập | Lockfile và checksum |
| Plugin chạy với quyền host | Mở rộng attack surface | Least privilege và sandbox |
| Không có resource budget | Plugin có thể làm treo compiler | Timeout, memory, CPU và output quota |
| Bỏ qua lỗi plugin | Artifact thiếu thành phần nhưng build vẫn pass | Fail closed khi extension bắt buộc |
| Retry callback không idempotent | Side effect lặp | Retry contract và idempotency |
| Extension không có owner | Không ai bảo trì hoặc xử lý security | Publisher và lifecycle governance |
| Không test compatibility matrix | Nâng compiler làm plugin hỏng | Conformance và version matrix |
| Không có deprecation policy | Plugin ecosystem bị phá đột ngột | Deprecation window và migration guide |
| Cache thiếu plugin version | Dùng output stale | Cache key gồm extension digest |

## 28. Quy trình thiết kế mở rộng có kiểm soát

Một quy trình thiết kế có thể gồm:

1. **Xác định nhu cầu:** extension giải quyết biến thể domain nào?
2. **Chọn extension layer:** syntax, semantic, library, runtime, backend hay tooling.
3. **Giữ core contract nhỏ:** chỉ expose abstraction thực sự cần.
4. **Định nghĩa interface:** input/output, lifecycle, error, concurrency và cancellation.
5. **Định nghĩa namespace:** ID, symbol và conflict resolution.
6. **Định nghĩa manifest:** version, dependency, target và capability.
7. **Đặt trust boundary:** publisher, signature, sandbox và permission.
8. **Đặt resource budget:** CPU, memory, time, I/O và output.
9. **Thiết kế determinism:** ordering, cache key và provenance.
10. **Thiết kế compatibility:** API version, migration và deprecation.
11. **Xây conformance tests:** positive, negative, lifecycle và security.
12. **Tích hợp registry:** discovery, pinning và revocation.
13. **Viết documentation:** install, configuration, capability và troubleshooting.
14. **Theo dõi vận hành:** usage, failure, timeout và security advisory.

## 29. Tiêu chí của một extension system tốt

Một extension system tốt cho phép bổ sung năng lực mà không làm mờ semantics của core DSL. Extension có interface và namespace rõ, được resolve theo version, chạy với capability tối thiểu và chịu resource budget. Host có thể kiểm tra compatibility, phát hiện conflict, cô lập lỗi và truy vết output.

Các câu hỏi quan trọng:

- Extension point nào được hỗ trợ và phase nào có thể tham gia?
- Core language và extension syntax có boundary rõ không?
- Extension có ID, publisher và manifest ổn định không?
- Dependency và version có được pin không?
- Conflict và override có semantics tường minh không?
- Extension API có version và compatibility range không?
- Plugin có capability tối thiểu và sandbox phù hợp không?
- CPU, memory, time, output và external calls có quota không?
- Cancellation, cleanup và failure isolation có được định nghĩa không?
- Output có deterministic và cache key có chứa extension version không?
- Có conformance test và compatibility matrix không?
- Có registry, signature, revocation và deprecation policy không?
- Người dùng có thể biết extension nào đã ảnh hưởng tới build không?

Mở rộng có kiểm soát giúp DSL thích ứng với nhiều domain và nền tảng mà vẫn giữ được tính nhất quán. Khi extension point được thiết kế rõ, plugin được version hóa và kiểm tra, capability được giới hạn, conflict được phát hiện và output có thể tái lập, hệ sinh thái có thể phát triển độc lập mà không làm suy yếu core language. Đây là nền tảng để một DSL vừa đủ ổn định cho người dùng lâu dài vừa đủ linh hoạt để tích hợp những nhu cầu mới.
