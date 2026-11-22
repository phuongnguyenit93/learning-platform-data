# Hệ sinh thái mở rộng

Một nền tảng sử dụng Domain-Specific Language (DSL) thường cần nhiều khả năng hơn những gì runtime lõi cung cấp. Một nhóm có thể muốn thêm type, function, validator, connector, action, syntax module, editor integration hoặc công cụ deploy riêng. Nếu mọi tính năng đều phải sửa và phát hành lại engine lõi, tốc độ phát triển chậm, các nhóm phụ thuộc chặt vào nhau và nền tảng khó phục vụ nhiều domain khác nhau.

**Hệ sinh thái mở rộng** (*extension ecosystem*) là tập hợp các extension, plugin, package, API, công cụ phát triển, registry, quy trình phân phối và cơ chế quản trị cho phép bổ sung năng lực vào nền tảng DSL theo hợp đồng được kiểm soát. Nó bao gồm cả thành phần kỹ thuật lẫn quy trình vòng đời: tạo extension, phát triển, kiểm thử, đóng gói, ký, publish, discover, install, configure, activate, upgrade, disable, revoke và retire.

Ví dụ một workflow DSL platform có thể cung cấp các extension sau:

| Extension | Khả năng bổ sung |
|---|---|
| PostgreSQL connector | Đọc/ghi dữ liệu qua database adapter. |
| Payment action pack | Tích hợp thao tác thanh toán đã được kiểm soát. |
| JSON Schema module | Khai báo và validate schema. |
| Custom function library | Thêm hàm miền nghiệp vụ. |
| Editor plugin | Syntax highlighting, completion và diagnostics. |
| Deployment adapter | Publish definition lên runtime environment. |
| Observability plugin | Xuất trace, metric và audit event. |

Hệ sinh thái mở rộng tốt giúp nền tảng tiến hóa theo module, nhưng mỗi extension cũng làm tăng bề mặt tương thích, bảo mật, vận hành và hỗ trợ. Vì vậy, quản trị vòng đời extension cần xác định rõ API contract, ownership, quyền, dependency, version, trust, resource limits và cách xử lý khi extension lỗi hoặc bị thu hồi.

## 1. Extension ecosystem là gì?

Extension ecosystem là môi trường trong đó bên thứ nhất hoặc bên thứ ba có thể xây dựng và phân phối thành phần mở rộng cho một nền tảng. Nền tảng cung cấp extension points và runtime contract; extension cung cấp implementation hoặc metadata để bổ sung capability.

### Extension

Extension là đơn vị mở rộng có identity, version, manifest, dependency và một hoặc nhiều capability. Nó có thể chứa code, DSL module, schema, configuration, editor assets hoặc một adapter chạy ngoài process.

### Plugin

Plugin thường là extension có code được load hoặc gọi bởi host runtime. Plugin có thể triển khai interface, listener, function provider, task handler hoặc connector.

### Package

Package là đơn vị phân phối. Một package có thể chứa nhiều extension, module hoặc resource. Package manager xử lý version, dependency, signature và installation.

### Extension point

Extension point là vị trí host cho phép extension tham gia, ví dụ:
- Function registry.
- Type provider.
- Parser/grammar module.
- Validator.
- Workflow task handler.
- Connector.
- Serializer.
- Lifecycle listener.
- Diagnostic provider.
- Editor language service.

### Registry/catalog

Registry lưu metadata và artifact; catalog giúp developer tìm, xem documentation, kiểm tra compatibility và cài đặt extension.

### Ecosystem governance

Governance xác định ai được publish, ai review, extension nào được trust, cách xử lý vulnerability, deprecation và support.

## 2. Vì sao nền tảng DSL cần hệ sinh thái mở rộng?

### Mở rộng theo domain

Một DSL engine lõi không thể biết trước mọi domain. Extension cho phép commerce, finance, identity hoặc analytics bổ sung function/type riêng mà không nhồi mọi thứ vào core.

### Tách tốc độ phát hành

Connector có thể release độc lập với engine nếu extension API ổn định. Nhóm tích hợp không phải chờ core release cho mọi thay đổi nhỏ.

### Chia sẻ capability

Một extension được xây tốt có thể dùng lại ở nhiều project hoặc tenant, giảm duplication và tạo chuẩn chung.

### Tạo developer ecosystem

Developer có thể xây connector, tooling và library cho nhu cầu chuyên biệt. Catalog, documentation và compatibility policy giúp extension được khám phá và sử dụng.

### Cô lập trách nhiệm

Core giữ language semantics và lifecycle nền tảng; extension chịu trách nhiệm capability riêng. Ranh giới này giúp ownership và support rõ hơn.

### Hỗ trợ integration

Ứng dụng thường cần database, message broker, cloud storage, identity provider và monitoring. Connector extension giúp DSL tương tác với các hệ thống đó qua contract thống nhất.

### Kiểm soát rủi ro

Khi extension được quản trị bằng manifest, signature, permission và resource quota, nền tảng có thể đánh giá rủi ro trước khi activate.

## 3. Các loại extension trong DSL platform

Không phải mọi extension đều cần chạy code trong process.

| Loại | Ví dụ | Runtime behavior |
|---|---|---|
| Language module | Type, keyword, grammar production. | Tham gia parse/type-check. |
| Function library | Hàm tính toán hoặc domain function. | Được evaluator gọi. |
| Action/task handler | Workflow task hoặc rule action. | Thực hiện operation. |
| Data connector | Database, object storage, API. | Giao tiếp external system. |
| Schema/validator pack | Schema type và validation rule. | Kiểm tra dữ liệu. |
| Serializer/codec | JSON, Avro, custom binary. | Encode/decode data. |
| Policy pack | Security, governance, decision policy. | Áp dụng policy. |
| Editor extension | Completion, syntax highlight, diagnostics. | Tích hợp IDE. |
| Build/deploy tool | Compiler adapter, deployment target. | Tham gia build/release. |
| Observability integration | Metrics, tracing, audit sink. | Thu thập telemetry. |

### Code extension

Code extension có thể chạy trong cùng JVM hoặc process khác. Cần quản lý ABI/API compatibility, classloader, resource và trust.

### Declarative extension

Một extension có thể chỉ chứa schema, metadata hoặc DSL definitions. Nó vẫn cần version/dependency management nhưng không nhất thiết thực thi code tùy ý.

### Remote extension

Một capability có thể được cung cấp qua RPC/service. Host gọi qua protocol contract; isolation tốt hơn nhưng cần xử lý network, timeout, authentication và availability.

### Editor extension

Editor plugin có lifecycle riêng với host IDE/editor, có thể chạy trên máy developer hoặc language server. Không nên giả định editor extension được phép truy cập runtime production.

## 4. Kiến trúc tổng thể của extension ecosystem

Một kiến trúc phổ biến có thể gồm developer workflow, registry, package manager, runtime host và governance plane.

~~~mermaid
flowchart TD
    A[Extension developer] --> B[SDK and templates]
    B --> C[Build and test]
    C --> D[Package and sign]
    D --> E[Extension registry]
    E --> F[Catalog and resolver]
    F --> G[Install / approve]
    G --> H[Runtime extension host]
    H --> I[DSL engine capabilities]
    H --> J[Policy and permissions]
    K[Governance and security] --> E
    K --> H
    L[Telemetry and support] --> H
~~~

### Developer plane

Cung cấp SDK, template, local test harness, documentation và publishing workflow.

### Registry plane

Lưu package artifact, manifest, version, signature, compatibility metadata và lifecycle status.

### Runtime plane

Resolve dependency, load extension, register capability, invoke implementation và theo dõi health.

### Governance plane

Quản lý publisher identity, review, policy, permission, vulnerability, revocation và audit.

### Observability plane

Thu thập activation, execution, latency, failure, resource consumption và version adoption.

### Control plane và data plane

Control plane quản lý install/activate/configure/revoke. Data plane thực thi capability khi DSL chạy. Tách hai plane giúp runtime operation không phải truy cập registry ở mỗi function call.

## 5. Thiết kế extension point và contract

Extension point là ranh giới quan trọng nhất của ecosystem. Contract không rõ sẽ khiến plugin phụ thuộc vào internal implementation.

### Public API

Chỉ công bố interface cần thiết để extension hoạt động. Tránh expose internal class, mutable engine state hoặc implementation detail không ổn định.

### Capability interface

Mỗi extension point nên mô tả input, output, error, lifecycle và concurrency contract.

Ví dụ interface minh họa:

~~~java
public interface DslFunctionProvider {
    String namespace();

    Collection<FunctionDescriptor> functions();

    FunctionResult invoke(
        FunctionCall call,
        EvaluationContext context
    );
}
~~~

### Stable contract

Contract cần xác định:
- Method signatures và type mapping.
- Thread-safety.
- Reentrancy.
- Timeout/cancellation.
- Error model.
- Resource ownership.
- Version compatibility.
- Security principal/context propagation.

### Host-owned abstractions

Nên truyền abstraction như EvaluationContext, ResourceResolver hoặc SecretProvider thay vì cho plugin truy cập toàn bộ ApplicationContext hoặc engine internals.

### Capability discovery

Extension có thể khai báo capabilities trong manifest. Host xác định extension nào đáp ứng extension point mà DSL definition cần.

### Optional capability

Nếu capability không bắt buộc, runtime có thể disable feature hoặc trả diagnostic. Không nên để missing optional capability gây crash ở startup mà không nêu rõ.

### Contract tests

Host có thể cung cấp test suite chung để publisher xác nhận extension tuân thủ interface, lifecycle và error behavior.

## 6. Extension manifest

Manifest mô tả extension và điều kiện để host cài đặt/activate.

Ví dụ manifest minh họa:

~~~yaml
extension:
  id: com.example.payments.actions
  name: Payment Actions
  version: 2.3.1
  publisher: Example Integrations
  description: Workflow actions for payment operations

compatibility:
  engine: ">=5.4.0 <6.0.0"
  extensionApi: "4"
  language: ">=2.0 <3.0"

capabilities:
  - workflow.action
  - function.provider

dependencies:
  - id: com.example.core.money
    version: "3.2.0"

permissions:
  - network:payments.example.test
  - secret:payments-api-key

entrypoint:
  type: java-service
  class: com.example.payments.PaymentExtension
~~~

Manifest thực tế phụ thuộc registry và packaging format, nhưng nên có các nhóm metadata sau:

- Extension ID và version.
- Publisher/owner.
- Description, docs và support URL.
- Engine/API/language compatibility.
- Capability/extension point.
- Dependencies.
- Permissions.
- Entrypoint hoặc artifact type.
- Signature/provenance.
- Resource requirements.
- Lifecycle status.
- License và support policy.

### Stable extension ID

ID nên có namespace do publisher sở hữu. Không tái sử dụng ID cho package không liên quan.

### Manifest schema version

Manifest format cũng cần version riêng để package manager biết cách parse. Không nhầm manifest schema version với extension package version.

### Manifest validation

Kiểm tra required field, version syntax, dependency range, permission declaration và entrypoint trước khi publish/install.

### Metadata trust

Description hoặc URL từ publisher là dữ liệu không tin cậy. Không thực thi nội dung manifest như code; mọi permission phải được kiểm tra qua policy.

## 7. Extension discovery và registry

Registry là nguồn phân phối artifact và metadata.

### Private registry

Tổ chức có thể host registry nội bộ để kiểm soát extension được phép dùng.

### Public registry

Public catalog có thể cho publisher bên ngoài đăng ký và phân phối extension. Cần review, moderation, signature và vulnerability policy.

### Federated registry

Một package manager có thể resolve từ nhiều registry theo priority/trust domain. Cần chống dependency confusion và namespace collision.

### Search/catalog

Catalog nên hỗ trợ search theo capability, DSL version, engine compatibility, publisher, category, license và support status.

### Artifact storage

Artifact nên immutable, có content hash, signature và metadata provenance. Không overwrite cùng version.

### Registry availability

Runtime đã cài extension không nên phụ thuộc registry online cho mọi invocation. Registry thường chỉ cần ở install/upgrade/refresh metadata; artifact đã cache được xác minh và pin.

### Revocation feed

Registry có thể phát thông tin package bị thu hồi do compromise hoặc policy violation. Host cần nhận và áp dụng theo policy.

## 8. Dependency resolution

Extension có thể phụ thuộc extension/module khác.

Ví dụ:
- Payment Actions cần Money Types.
- Money Types cần Decimal Utilities.
- Editor Extension cần Language Server API.

### Dependency graph

Resolver tạo graph và xác định thứ tự install/initialize. Cần phát hiện cycle, missing package và version conflict.

### Version range

Dependency có thể yêu cầu exact version hoặc range. Exact pin tăng reproducibility; range hỗ trợ update nhưng cần lockfile.

### Lockfile

Lockfile lưu version và hash đã resolve. Dev, CI và production nên dùng cùng resolved graph.

### Transitive dependency

Nếu A phụ thuộc B và B phụ thuộc C, resolver phải kiểm tra C tương thích với cả host và những extension khác.

### Optional dependency

Một extension có thể hỗ trợ capability tùy chọn. Manifest cần đánh dấu rõ và runtime cần degrade có kiểm soát khi package không có.

### Dependency isolation

Một số host cho phép nhiều version của cùng library trong classloader riêng. Nếu không, resolver cần chọn một version chung hoặc từ chối conflict.

### Deterministic resolution

Cùng manifest/lockfile/registry snapshot phải tạo cùng dependency graph. Không để thứ tự registry response quyết định package được chọn.

## 9. Packaging và phân phối extension

Package cần có cấu trúc và quy tắc cài đặt nhất quán.

### Package contents

Một package có thể chứa:
- Manifest.
- JAR/WASM/container artifact hoặc remote endpoint descriptor.
- DSL module/grammar.
- Schema và metadata.
- Documentation và examples.
- License/notice.
- Signature và checksum.
- Contract test report.

### Reproducible package

Cùng source, dependency lock và build tool version nên tạo artifact có hash ổn định nếu reproducible build là requirement.

### Artifact signing

Publisher ký artifact/manifest. Host xác minh signature theo trust store trước khi install hoặc activate.

### Checksum

Checksum phát hiện artifact bị thay đổi khi truyền tải. Nó không thay thế signature vì checksum tự thân không xác minh publisher identity.

### Package layout

Định dạng package nên versioned và có giới hạn path để tránh zip-slip hoặc file ghi ra ngoài installation directory.

### Installation staging

Giải nén vào staging area, validate manifest/dependency/signature, sau đó atomic promote sang installed state. Không load package đang được ghi dở.

### Offline installation

Tổ chức có thể mirror artifact và signature để cài đặt trong môi trường không có internet. Cần kiểm tra mirror provenance.

## 10. Extension lifecycle

Extension có lifecycle riêng và phải được phối hợp với engine lifecycle.

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> BUILT
    BUILT --> VALIDATED
    VALIDATED --> PUBLISHED
    PUBLISHED --> INSTALLED
    INSTALLED --> CONFIGURED
    CONFIGURED --> ACTIVE
    ACTIVE --> DISABLED
    DISABLED --> ACTIVE
    ACTIVE --> DEPRECATED
    DEPRECATED --> RETIRED
    INSTALLED --> UNINSTALLED
    DISABLED --> UNINSTALLED
    ACTIVE --> REVOKED
    REVOKED --> UNINSTALLED
~~~

Các trạng thái có thể gồm:

| Trạng thái | Ý nghĩa |
|---|---|
| Draft | Đang phát triển. |
| Built | Artifact đã được tạo. |
| Validated | Đã qua manifest/contract/security checks. |
| Published | Có trong registry/catalog. |
| Installed | Artifact đã có trên host. |
| Configured | Đã cung cấp cấu hình/secret cần thiết. |
| Active | Capability đã được đăng ký và có thể được gọi. |
| Disabled | Tạm ngừng activation. |
| Deprecated | Không khuyến nghị dùng cho triển khai mới. |
| Revoked | Bị thu hồi do security/policy. |
| Retired | Đã ngừng hỗ trợ. |
| Uninstalled | Artifact đã được gỡ khỏi host. |

### Publish không đồng nghĩa active

Extension có thể publish nhưng chưa được cài đặt hoặc phê duyệt cho một environment. Tách trạng thái giúp tránh tự động chạy mọi package có trong registry.

### Activation

Activation cần resolve dependency, verify permission, initialize resource và register capability. Nếu một bước lỗi, activation cần rollback.

### Disable

Disable ngừng nhận invocation mới. Invocation đang chạy cần được drain hoặc cancel theo policy.

### Uninstall

Chỉ uninstall khi không còn active execution hoặc dependency nào cần extension. Có thể cần giữ artifact cho replay hoặc audit.

### Revocation

Revocation có thể khẩn cấp. Host cần chặn invocation mới ngay, xử lý in-flight operation theo severity và ghi audit.

## 11. Plugin initialization và shutdown

Plugin có thể cần khởi tạo resource khi host start.

### Lifecycle hooks

Một plugin API có thể định nghĩa:
- validateConfiguration
- initialize
- start
- health
- stop
- close

### Initialization ordering

Dependency plugin phải sẵn sàng trước consumer plugin. Resolver tạo topological order nếu dependency graph acyclic.

### Partial failure

Nếu plugin initialize thất bại sau khi đã tạo connection, host cần gọi cleanup cho phần đã khởi tạo. Plugin nên implement idempotent close.

### Shutdown ordering

Đóng theo thứ tự ngược dependency: consumer dừng trước provider. Host ngừng dispatch mới, drain invocation rồi mới close resource.

### Hot reload

Nếu hỗ trợ reload plugin, host cần tạo generation mới, kiểm tra health, atomic switch rồi drain generation cũ. Không unload classloader khi thread/listener còn giữ reference.

### Thread ownership

Plugin không nên tạo background thread không được quản lý. Nếu tạo, phải đăng ký lifecycle và dừng thread trong stop/close.

### Resource ownership

Host cần xác định resource nào plugin sở hữu, resource nào được inject từ host và ai chịu trách nhiệm đóng.

## 12. Permission model và capability security

Extension cần quyền để thực hiện chức năng. Không nên mặc định plugin được toàn quyền truy cập process.

### Least privilege

Chỉ cấp quyền tối thiểu cần thiết. Ví dụ connector chỉ được truy cập một database schema hoặc một network host.

### Capability declaration

Manifest khai báo capability và permission cần. Admin hoặc policy engine quyết định có chấp thuận không.

### Runtime enforcement

Permission phải được thực thi ở runtime. Metadata trong manifest chỉ là yêu cầu, không tự tạo security boundary.

### Secret access

Plugin nhận secret qua SecretProvider scoped, không đọc toàn bộ environment hoặc config store. Secret không nên xuất hiện trong logs, diagnostics hoặc package.

### Network egress

Có thể giới hạn host/port hoặc service identity mà plugin được kết nối.

### File system

Nếu plugin cần file, cấp path/volume cụ thể và giới hạn read/write. Tránh quyền truy cập toàn filesystem.

### Tenant context

Extension chạy cho tenant nào cần nhận tenant context đã được xác thực. Không tin tenant ID tùy ý trong payload.

### Admin capabilities

Permission publish, install, activate, disable và revoke phải tách khỏi permission invoke. Developer không nhất thiết được phép activate package ở production.

## 13. Sandboxing và isolation

Nếu extension đến từ nhiều publisher, isolation trở thành yêu cầu quan trọng.

### In-process plugin

Plugin chạy trong cùng process với engine, gọi nhanh và tích hợp trực tiếp. Tuy nhiên, plugin có thể truy cập JVM/process resource và crash host nếu không được kiểm soát.

### Classloader isolation

Classloader riêng giúp tách dependency version và có thể hỗ trợ unload. Nó không phải sandbox security hoàn chỉnh vì plugin vẫn chạy cùng process và có thể gọi API nguy hiểm nếu được cấp.

### Separate process

Chạy extension trong process riêng tăng isolation. Host giao tiếp qua RPC/IPC và có thể áp CPU/memory limit ở process/container level.

### WASM/runtime sandbox

Một runtime sandbox có thể giới hạn imports, memory và execution fuel. Cần kiểm tra capability host functions được expose.

### Container isolation

Container giúp giới hạn filesystem, network, CPU và memory ở mức OS/orchestrator. Container không tự động giải quyết mọi rủi ro supply chain hoặc kernel escape.

### Trust tiers

Có thể chia extension:
- First-party reviewed.
- Organization-approved.
- Verified publisher.
- Untrusted/experimental.

Trust tier quyết định deployment model, permission và approval.

### Failure isolation

Một extension timeout hoặc crash không nên làm sập toàn engine. Host cần timeout, circuit breaker, bulkhead và health state.

## 14. Runtime invocation contract

Khi DSL gọi extension, host cần một invocation contract thống nhất.

Invocation context có thể chứa:
- Extension ID/version.
- Capability/function name.
- Execution/trace/correlation ID.
- Tenant và security principal.
- Input schema/version.
- Deadline và cancellation token.
- Resource budget.
- Locale/timezone nếu cần.
- Transaction context theo policy.

### Input validation

Host validate argument theo function descriptor trước khi gọi plugin. Plugin cũng nên validate boundary nếu có thể được gọi trực tiếp từ nhiều host.

### Output contract

Output cần type/schema rõ và có giới hạn kích thước. Không trả arbitrary object không serialize được qua boundary.

### Error model

Phân biệt validation error, business error, transient dependency error, timeout, cancellation và plugin defect. Error code ổn định giúp retry policy quyết định đúng.

### Idempotency

Operation gây side effect có thể nhận idempotency key. Retry không được tạo duplicate payment/order/message.

### Timeout

Host truyền deadline và enforce timeout. Plugin cần tôn trọng cancellation; host vẫn phải xử lý trường hợp plugin không phản hồi.

### Retry

Chỉ retry lỗi được phân loại transient và operation idempotent hoặc có idempotency contract. Không retry tất cả exception.

### Observability

Ghi invocation count, duration, result category, extension version và resource usage. Tránh log input chứa secret/PII.

## 15. Extension và DSL language integration

Một extension có thể bổ sung syntax hoặc semantics cho DSL.

### Function provider

Extension đăng ký function name, parameter types, return type, purity, side effect classification và documentation.

### Type provider

Extension đăng ký custom type hoặc type alias. Type identity phải namespace để tránh collision.

### Grammar module

Nếu extension thêm syntax, cần kiểm tra grammar conflict, language version và parser compatibility.

### Validator provider

Extension có thể cung cấp validation rule cho domain-specific schema. Validation nên deterministic và có diagnostic contract.

### Workflow action

Action handler có thể thực thi một task. Cần xác định retry, timeout, compensation, idempotency và result schema.

### Import/dependency

Definition cần khai báo module dependency hoặc version range. Runtime không nên tự tìm function bất kỳ theo tên mà không có dependency declaration.

### Static analysis

Compiler cần biết function metadata để kiểm tra side effect, async behavior, allowed context và type compatibility.

### Documentation metadata

Function/type nên có description, example, parameter docs và deprecation metadata để IDE/editor hiển thị.

## 16. Versioning và compatibility cho extension

Extension phải tương thích với host API và language version.

### Extension version

Package version định danh nội dung extension. Publish version mới không được overwrite artifact cũ.

### Extension API version

Host có thể expose API version riêng. Extension manifest khai báo version/range hỗ trợ.

### Engine compatibility range

Manifest khai báo engine versions được hỗ trợ. Resolver kiểm tra trước install/activation.

### Language compatibility

Nếu extension đăng ký syntax/function, cần khai báo language version/profile tương thích.

### Dependency lock

Một extension package nên pin hoặc lock dependency graph để activation reproducible.

### API evolution

Thêm optional method có thể vẫn gây breaking nếu interface implementation bắt buộc override. Có thể dùng default method, capability interface hoặc versioned SPI.

### Deprecation

Host thông báo extension API cũ deprecated, cung cấp replacement và timeline removal.

### Compatibility test matrix

CI nên test extension với các host version được hỗ trợ, không chỉ compile với một version hiện tại.

## 17. Security và supply chain

Extension có thể mang code hoặc dependency bên thứ ba, vì vậy supply chain cần được quản trị.

### Publisher identity

Publisher phải có identity xác thực và quyền publish trong namespace được cấp.

### Artifact signature

Ký package và xác minh signature trước khi install. Key rotation/revocation cần được hỗ trợ.

### SBOM

Software Bill of Materials liệt kê dependency để đánh giá vulnerability và license.

### Vulnerability scanning

Quét package/dependency, secret, malware pattern và known CVE. Kết quả scan cần gắn với artifact hash.

### Provenance

Ghi source repository, commit, build system, workflow và signer. Có thể yêu cầu build từ pipeline được tin cậy.

### Dependency confusion

Private package name không được resolve nhầm từ public registry. Registry priority và namespace ownership cần rõ.

### Typosquatting

Catalog có thể cảnh báo package có tên gần giống extension phổ biến hoặc publisher chưa xác minh.

### Revocation response

Khi artifact bị compromise, host cần block install/activation, phát cảnh báo, xác định instance đang dùng và audit action.

### License compliance

Package manifest cần license metadata và policy kiểm tra license trước khi publish/deploy.

## 18. Extension governance và approval workflow

Không phải extension nào cũng được tự động chạy ở mọi environment.

### Publisher onboarding

Xác minh publisher, namespace, contact, signing key và support commitment.

### Review

Review có thể gồm code/security review, API contract, permission, dependency, license và documentation.

### Environment policy

Dev có thể cho phép extension experimental; staging yêu cầu verified; production chỉ cho approved publisher hoặc package cụ thể.

### Approval separation

Người viết extension không nhất thiết là người approve hoặc activate nó ở production. Tách duties giảm rủi ro.

### Policy-as-code

Có thể khai báo policy như: chỉ cho phép extension có signature hợp lệ, không có critical vulnerability, engine-compatible và không yêu cầu permission vượt mức.

### Audit trail

Ghi publisher, reviewer, approver, package hash, install/activation time, permission grant và revocation.

### Emergency disable

Operator cần có cách disable/revoke extension nhanh khi có incident. Thao tác này cần audit và có thể có impact lên execution đang chạy.

## 19. Developer experience và SDK

Ecosystem mạnh cần giúp developer xây extension đúng chuẩn.

### SDK

SDK cung cấp:
- Extension interfaces.
- Manifest model/schema.
- Local runtime harness.
- Test utilities.
- Logging/metrics/tracing adapters.
- Secret/resource abstractions.
- Compatibility helpers.
- Packaging/publishing command.

### Templates

Template giúp tạo extension mới với cấu trúc chuẩn, sample capability, test và documentation.

### Local development

Developer có thể load extension vào local engine, test DSL sample và inspect diagnostic trước publish.

### Hot reload in development

Có thể hỗ trợ reload trong môi trường dev để rút ngắn feedback loop. Production activation vẫn cần version/approval contract riêng.

### Documentation

Mỗi extension cần mô tả purpose, supported versions, permissions, configuration, examples, error behavior, limits và support policy.

### Samples

Sample phải dùng dữ liệu giả, không chứa credential hoặc production endpoint.

### Debugging

SDK có thể cung cấp trace context, local invocation inspector và structured error report. Không log payload nhạy cảm mặc định.

### Compatibility tooling

CLI có thể kiểm tra manifest, dependency, API compatibility và package signature trước publish.

## 20. Testing và certification cho extension

Host nên có contract test suite để giảm lỗi do plugin.

### Manifest validation

Kiểm tra ID, version, entrypoint, dependency range, capability và permission declaration.

### Contract tests

Xác nhận plugin triển khai đúng interface, input/output schema, lifecycle và error contract.

### Lifecycle tests

Kiểm tra initialize/start/stop/close, partial failure và idempotent cleanup.

### Concurrency tests

Chạy nhiều invocation song song để xác định thread-safety, shared state và race.

### Timeout/cancellation tests

Xác nhận plugin phản hồi cancellation và không giữ resource vô hạn.

### Resource tests

Đo CPU, memory, thread, connection và output size theo quota.

### Security tests

Kiểm tra permission enforcement, secret redaction, tenant isolation, path/network restrictions và untrusted input.

### Compatibility tests

Chạy extension trên mọi host/API version được công bố hỗ trợ.

### Failure injection

Giả lập dependency unavailable, timeout, malformed response và plugin crash để kiểm tra host isolation.

### Certification status

Registry có thể lưu kết quả certification gắn với artifact hash. Khi artifact thay đổi, certification cũ không tự động áp dụng.

## 21. Observability và vận hành ecosystem

Quản trị ecosystem cần biết extension nào đang được sử dụng và ảnh hưởng ra sao.

### Registry metrics

Theo dõi publish count, download/install count, version adoption và revoked artifact.

### Runtime metrics

Theo dõi invocation count, latency, error rate, timeout, resource consumption và active instance theo extension version.

### Health

Extension có thể expose health status. Host tổng hợp thành capability health, không nhất thiết làm toàn engine unhealthy khi extension optional bị lỗi.

### Dependency visibility

Dashboard có thể hiển thị dependency graph và blast radius khi một package bị thu hồi hoặc nâng cấp.

### Usage inventory

Liệt kê definition nào import extension, tenant/environment nào active và version nào được pin.

### Support telemetry

Thu thập lỗi có correlation ID và extension version để publisher/operator điều tra. Cần redaction dữ liệu nhạy cảm.

### Alerting

Alert khi extension crash loop, timeout tăng, queue backlog, revoked package còn được invoke hoặc version hết support vẫn hoạt động.

## 22. Upgrade, disable, uninstall và retirement

Extension lifecycle tiếp tục sau activation.

### Upgrade

Upgrade cần resolve version mới, kiểm tra compatibility, dependency và permission diff. Có thể stage, validate rồi atomic activate.

### Side-by-side versions

Có thể cài nhiều version song song nếu classloader/runtime isolation cho phép. Definition cần pin version cụ thể để tránh version selection mơ hồ.

### In-flight invocation

Khi upgrade, invocation đang chạy có thể hoàn tất bằng generation cũ; invocation mới dùng generation mới. Drain generation cũ trước khi giải phóng resource.

### Disable

Disable chặn invocation mới và giữ package đã cài để có thể enable lại. Có thể cần pause dependent definition.

### Uninstall

Uninstall cần kiểm tra dependent package, active definition và persisted execution. Không xóa artifact cần cho replay hoặc audit.

### Retirement

Retired version không nhận install mới nhưng có thể còn trong archive để đọc lịch sử. Cần retention policy.

### Rollback

Rollback chuyển active pointer về version trước nếu dependency/host tương thích. Nếu migration đã thay đổi persisted state, cần compatibility hoặc reverse migration.

## 23. Multi-tenancy và extension ecosystem

Một platform multi-tenant cần kiểm soát extension theo tenant và environment.

### Shared extension

Một extension dùng chung code/runtime nhưng execution context và data access được scope theo tenant.

### Tenant allowlist

Tenant có thể chỉ được phép dùng extension đã được admin approve. Không để tenant tự cài package có quyền rộng.

### Tenant configuration

Cấu hình/secret có thể khác theo tenant. Secret provider cần scope và audit riêng.

### Resource quota

Áp CPU/memory/invocation/concurrency quota theo extension và tenant để ngăn noisy neighbor.

### Version pinning

Tenant A có thể dùng extension v2, tenant B dùng v3 trong thời gian migration nếu host hỗ trợ side-by-side.

### Offboarding

Khi tenant rời hệ thống, xử lý secret, config, execution history, package activation và data retention theo policy.

### Cross-tenant isolation

Extension không được dùng cache key hoặc shared mutable state khiến dữ liệu tenant này lộ sang tenant khác.

## 24. Ecosystem catalog và trải nghiệm chọn extension

Catalog giúp người dùng chọn đúng extension.

Một trang extension nên hiển thị:
- Tên, ID, publisher và description.
- Capability được cung cấp.
- Supported engine/language/API versions.
- Dependency và permission yêu cầu.
- Version hiện tại, release history và changelog.
- License, support level và maintenance status.
- Signature/verification status.
- Security scan/certification status.
- Documentation, examples và known limitations.
- Usage/deprecation information nếu người xem có quyền.

### Search theo capability

Người dùng thường tìm “database connector” hoặc “schema validator” thay vì biết package ID. Catalog nên hỗ trợ category/tag.

### Compatibility filter

Chỉ hiển thị hoặc đánh dấu extension tương thích với project/engine hiện tại.

### Permission review

Trước install, hiển thị quyền mà extension yêu cầu và lý do. Admin có thể approve/reject.

### Publisher trust

Verified publisher, first-party và community extension cần được phân biệt rõ. Trust badge phải dựa trên quy trình kiểm chứng.

### Install preview

Cho biết dependency sẽ được cài, version sẽ thay đổi và capability nào sẽ được register.

## 25. Ví dụ: đăng ký function extension cho DSL

Một extension có thể cung cấp function cho expression language.

Descriptor:

~~~java
public record FunctionDescriptor(
    String qualifiedName,
    List<TypeRef> parameters,
    TypeRef returnType,
    boolean pure,
    String description
) {}
~~~

Provider:

~~~java
public final class MoneyFunctions implements DslFunctionProvider {

    @Override
    public String namespace() {
        return "money";
    }

    @Override
    public Collection<FunctionDescriptor> functions() {
        return List.of(
            new FunctionDescriptor(
                "money.round",
                List.of(TypeRef.decimal(), TypeRef.integer()),
                TypeRef.decimal(),
                true,
                "Round a decimal amount to the requested scale"
            )
        );
    }

    @Override
    public FunctionResult invoke(
            FunctionCall call,
            EvaluationContext context) {
        // Validate arguments and return a typed result.
        throw new UnsupportedOperationException("Illustrative API");
    }
}
~~~

### Registration

Host đọc manifest, kiểm tra API compatibility, tạo provider, validate descriptor và đăng ký function trong namespace.

### Static type checking

Compiler dùng descriptor để kiểm tra số lượng/type argument và return type trước runtime.

### Runtime invocation

Evaluator gọi function với context có deadline, principal và resource budget. Provider không nên tự lấy global application state.

### Purity metadata

Function pure có thể được cache/fold nếu semantics cho phép. Function có side effect phải khai báo rõ để optimizer không thay đổi evaluation order.

### Error behavior

Function cần trả error code ổn định cho invalid input, dependency failure và timeout. Không đưa stack trace hoặc secret vào user-facing diagnostic.

## 26. Những lỗi thường gặp khi quản trị ecosystem

**Expose quá nhiều internal API.** Plugin phụ thuộc vào implementation detail và dễ vỡ khi engine nâng cấp. Chỉ công bố SPI/API có compatibility policy.

**Không có manifest chuẩn.** Host không biết dependency, permission hoặc version range. Dùng manifest schema có version.

**Load mọi plugin tự động.** Một package có trong registry không đồng nghĩa được tin cậy. Cần approval, signature và activation policy.

**Coi classloader là sandbox.** Classloader cô lập dependency nhưng không giới hạn quyền process. Dùng process/WASM/container isolation khi threat model yêu cầu.

**Không quản lý resource ownership.** Plugin để lại thread/connection sau shutdown. Lifecycle contract cần cleanup và resource registration.

**Cho extension truy cập toàn bộ application context.** Tạo coupling và quyền quá rộng. Inject capability abstraction theo least privilege.

**Không pin dependency.** Runtime resolve package khác theo thời gian. Dùng lockfile và immutable artifact.

**Không kiểm thử concurrency.** Plugin có thể pass single-thread test nhưng hỏng khi nhiều execution dùng chung instance. Contract test concurrency.

**Retry side effect vô điều kiện.** Payment/action có thể chạy hai lần. Yêu cầu idempotency key và retry classification.

**Không có revocation.** Package bị compromise vẫn tiếp tục được load. Registry/host cần emergency disable và audit.

**Không theo dõi consumer usage.** Không biết definition nào phụ thuộc extension cũ. Duy trì dependency inventory.

**Uninstall khi còn execution phụ thuộc.** Workflow dài hạn có thể không resume được. Retain artifact và kiểm tra dependency trước uninstall.

**Không tách dev/staging/prod policy.** Extension thử nghiệm có thể được activate ở production. Dùng trust tier và environment approval.

**Catalog chỉ có tên và version.** Người dùng không hiểu quyền, compatibility và support. Cung cấp metadata có ý nghĩa.

## 27. Quy trình xây dựng và quản trị extension

Một quy trình thực tế có thể gồm:

1. **Xác định extension point:** function, type, action, connector, validator, editor hoặc tooling.
2. **Thiết kế contract:** interface, type, lifecycle, error, concurrency và resource ownership.
3. **Tạo SDK/template:** manifest schema, local harness, sample và test utilities.
4. **Phát triển extension:** implementation tách biệt và dependency có version.
5. **Viết contract tests:** behavior, lifecycle, timeout, security và compatibility.
6. **Build package:** reproducible artifact, SBOM, checksum và signature.
7. **Validate package:** manifest, dependency, license, vulnerability và policy.
8. **Publish registry:** immutable version và provenance.
9. **Review/approve:** xác minh publisher, permissions và support.
10. **Install staging:** resolve lockfile, verify artifact và activate trong môi trường test.
11. **Promote production:** approval, canary/rollout và monitoring.
12. **Operate:** theo dõi invocation, health, resource, error và consumer usage.
13. **Upgrade/disable:** version pinning, drain, rollback và migration.
14. **Deprecate/retire:** thông báo, đo usage, giữ artifact cần thiết và uninstall có kiểm soát.

## 28. Checklist trước khi approve extension

Trước khi cho phép extension chạy trong một environment, cần xác nhận:

- Extension ID, publisher và owner có xác thực không?
- Manifest có đúng schema version và đầy đủ metadata không?
- Artifact có signature/hash và provenance hợp lệ không?
- Engine, language và extension API version có tương thích không?
- Dependency graph có resolve deterministic và không có conflict không?
- Permission có theo least privilege và được runtime enforce không?
- Secret có được cấp qua provider scoped không?
- Plugin có contract test, lifecycle test và concurrency test không?
- Timeout, cancellation, retry và idempotency có được định nghĩa không?
- Resource quota và isolation có phù hợp threat model không?
- SBOM, vulnerability scan và license review đã hoàn tất chưa?
- Có owner/support contact và documentation không?
- Upgrade, disable, revoke và rollback có quy trình không?
- Definition/tenant nào đang phụ thuộc extension có thể truy vấn được không?
- Audit, metrics và alerting có gắn extension ID/version không?

## 29. Kết quả cần có sau khi thiết kế hệ sinh thái mở rộng

Một extension ecosystem hoàn chỉnh thường cung cấp:

- **Extension model:** plugin, language module, function library, action, connector, validator và tooling.
- **Extension points:** public API/SPI, capability descriptors, lifecycle hooks và contract tests.
- **Manifest/package format:** identity, version, dependency, permission, entrypoint, signature và support metadata.
- **Registry/catalog:** discovery, immutable artifact, search, compatibility filter và revocation.
- **Dependency management:** graph resolution, version range, lockfile và deterministic install.
- **Lifecycle state machine:** draft, build, validate, publish, install, configure, activate, disable, revoke, retire và uninstall.
- **Runtime invocation contract:** context, input/output schema, error, deadline, cancellation và idempotency.
- **Security/isolation:** least privilege, secret scope, sandbox/process boundary, signature và supply-chain checks.
- **Governance:** publisher onboarding, review, approval, environment policy, audit và emergency response.
- **Developer experience:** SDK, templates, local harness, docs, examples và debugging.
- **Quality certification:** contract, lifecycle, concurrency, resource, security và compatibility tests.
- **Operations:** telemetry, health, usage inventory, upgrade, rollback, deprecation và retention.
- **Multi-tenancy:** tenant allowlist, config/secret isolation, quota và version pinning.

Hệ sinh thái mở rộng biến DSL platform thành nền tảng có thể thích ứng với nhiều domain và hệ thống bên ngoài. Để duy trì tính ổn định, extension phải được xây trên public contract có version, đóng gói thành artifact bất biến, resolve dependency có lock và khai báo capability/permission rõ ràng. Host cần quản lý lifecycle từ publish đến activation, invocation, upgrade, disable và retirement; đồng thời enforce least privilege, isolation, timeout, resource quota và revocation. Khi registry, SDK, contract tests, provenance, governance và observability được thiết kế cùng nhau, developer có thể chia sẻ capability mà platform vẫn kiểm soát được compatibility, security và vận hành trong suốt vòng đời extension.

