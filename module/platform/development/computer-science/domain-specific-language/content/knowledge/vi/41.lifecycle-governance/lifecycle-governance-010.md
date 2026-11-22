# Lưu trữ DSL

## Lưu trữ DSL trong quản trị vòng đời là gì?

Một DSL (domain-specific language) thường được tạo, chỉnh sửa, kiểm tra, phát hành và thực thi trong suốt vòng đời của một ứng dụng. Source DSL có thể mô tả rule nghiệp vụ, query, workflow, cấu hình, policy, template hoặc pipeline. Để quản lý những định nghĩa này lâu dài, hệ thống cần một cơ chế lưu trữ đáng tin cậy, có version, có thể tìm kiếm, phục hồi và kiểm soát quyền truy cập.

**Lưu trữ DSL (DSL storage)** là việc tổ chức và bảo quản các thành phần của DSL qua các giai đoạn tạo, sửa, review, release, runtime execution, archive và retirement. Phạm vi lưu trữ có thể gồm source text, metadata, module dependency, AST hoặc compiled artifact, schema version, execution history, workflow state và các tài liệu liên quan.

Ví dụ, một hệ thống quản lý rule có thể lưu:

~~~text
RuleDefinition
  id: "pricing.vip-discount"
  languageVersion: "2.1"
  source: ...
  revision: 17
  status: PUBLISHED
  owner: "pricing-team"
  updatedAt: ...
  dependencies: [...]
~~~

Source DSL là dữ liệu có thẩm quyền để chỉnh sửa và review. Compiled artifact có thể được tạo từ source để tăng tốc thực thi, nhưng cần có metadata chứng minh nó được tạo từ source revision nào, compiler version nào và dependency nào. Execution history có thể được lưu riêng để phục vụ audit và debugging.

Lưu trữ DSL có vai trò trong các hoạt động:

- Quản lý source và revision của module.
- Phân biệt draft, reviewed, published và retired definition.
- Theo dõi language version và schema version.
- Lưu dependency và import relationship.
- Cung cấp source cho compiler, interpreter hoặc language server.
- Lưu compiled artifact có thể tái tạo.
- Lưu trạng thái workflow hoặc process instance dài hạn.
- Bảo vệ dữ liệu bằng authorization, encryption và audit.
- Backup, restore và disaster recovery.
- Áp dụng retention và archival policy.
- Tìm kiếm, phân loại và quản lý ownership.

Một thiết kế lưu trữ tốt cần phân biệt dữ liệu gốc với dữ liệu dẫn xuất, xác định lifecycle của từng loại, bảo đảm tính nhất quán khi cập nhật và có thể phục hồi khi storage hoặc application gặp sự cố.

## Phân biệt các loại dữ liệu được lưu

Một hệ thống DSL thường lưu nhiều loại dữ liệu có vòng đời khác nhau. Không nên gộp tất cả vào một bảng hoặc một thư mục mà không có phân loại.

| Loại dữ liệu | Nội dung | Vai trò |
|---|---|---|
| Source definition | Văn bản DSL gốc | Nguồn chỉnh sửa và review |
| Metadata | ID, owner, version, trạng thái, tags | Quản trị và discovery |
| Dependency manifest | Import, plugin, schema reference | Resolve và reproducibility |
| AST / syntax cache | Cây cú pháp đã parse | Tăng tốc parse và tooling |
| Compiled artifact | Bytecode, plan hoặc executable form | Tăng tốc runtime |
| Runtime state | Workflow state, variable, checkpoint | Tiếp tục process dài hạn |
| Execution history | Kết quả, diagnostics, transition, audit | Debug và traceability |
| Test fixture | Input, expected output, compatibility corpus | Kiểm thử |
| Documentation | Migration guide, API contract, examples | Hỗ trợ người dùng |
| Secret reference | ID của secret trong secret manager | Resolve credential có kiểm soát |

### Source definition là nguồn có thẩm quyền

Source DSL thường là dữ liệu mà người dùng chỉnh sửa trực tiếp. Nó cần được lưu bền vững, có revision và có thể khôi phục. Nếu source chỉ tồn tại trong cache hoặc compiled artifact, hệ thống sẽ khó review, migrate hoặc rebuild khi toolchain thay đổi.

### Metadata hỗ trợ quản trị

Metadata có thể lưu tên, mô tả, owner, project, tenant, tags, language version, schema version, trạng thái review và thời điểm thay đổi. Metadata cần được version hoặc audit khi thay đổi nếu nó ảnh hưởng đến behavior hoặc quyền.

### Dependency manifest

Một module có thể phụ thuộc module khác, plugin, schema, host API hoặc external resource. Manifest giúp runtime biết dependency cần thiết và cho phép tái lập build. Dependency reference nên được pin theo version hoặc immutable digest khi cần reproducibility.

### AST và compiled artifact là dữ liệu dẫn xuất

AST cache và compiled artifact được tạo từ source cùng parser/compiler configuration. Chúng có thể được tái tạo nếu mất. Cần lưu source digest, toolchain version và artifact format version để tránh load nhầm artifact cũ.

### Runtime state và execution history

Workflow definition khác với process instance. Definition mô tả cách workflow hoạt động; instance lưu state của một lần chạy cụ thể. Execution history lưu sự kiện hoặc kết quả đã xảy ra. Ba loại này có retention, access control và migration requirements khác nhau.

## Nguyên tắc thiết kế lưu trữ DSL

### Single source of truth

Mỗi definition cần có một nơi xác định là nguồn chính thức. Có thể là Git repository, database registry hoặc document store, tùy sản phẩm. Cache, search index và compiled artifact là bản sao hoặc dữ liệu dẫn xuất.

Nếu cho phép chỉnh sửa ở nhiều nơi, cần quy tắc đồng bộ và conflict resolution. Không nên để file trong repository và bản ghi trong database cùng được coi là source of truth mà không có owner rõ.

### Stable identity

Mỗi module hoặc definition nên có ID ổn định, không phụ thuộc tên file hoặc vị trí thư mục. Tên có thể đổi; ID giúp giữ liên kết từ execution history, dependency, audit và API.

### Versioned content

Source đã publish nên có revision bất biến. Thay đổi tạo revision mới, không ghi đè lịch sử đã được dùng để chạy production.

### Atomic update

Một lần lưu cần tạo ra một revision hoàn chỉnh. Người đọc không nên thấy file hoặc record ở trạng thái chỉ được ghi một nửa.

### Reproducibility

Cần biết source revision, language version, compiler version, dependency và configuration nào đã tạo artifact hoặc execution. Nếu thiếu các đầu vào này, khó tái tạo behavior cũ.

### Separation of concerns

Source, metadata, artifact, runtime state và logs có thể dùng storage khác nhau. Chọn storage theo yêu cầu về query, consistency, size, latency, retention và security.

### Security by default

Lưu trữ DSL có thể chứa business rule, internal endpoint hoặc secret reference. Cần kiểm soát access theo tenant, project và role; mã hóa khi phù hợp; audit các thao tác nhạy cảm.

### Recoverability

Cần xác định backup, restore, replication, retention và disaster recovery. Một hệ thống lưu source nhưng không thể khôi phục metadata hoặc dependency vẫn có thể mất khả năng chạy definition.

## Các mô hình lưu trữ phổ biến

### Git repository

Git phù hợp với DSL được quản lý như source code:
- Revision history và diff.
- Branch, tag và merge.
- Code review.
- Signed commit hoặc tag.
- Pull request workflow.
- Dễ tích hợp CI/CD.

Ví dụ cấu trúc:

~~~text
dsl-project/
  modules/
    pricing/
      rules.dsl
      module.yml
    checkout/
      workflow.dsl
      module.yml
  schemas/
  tests/
  migrations/
~~~

Git thuận lợi cho review và reproducibility, nhưng có thể không phù hợp với các rule được người dùng cuối chỉnh sửa thường xuyên trong UI hoặc cần query theo tenant ở quy mô lớn.

### Relational database

Database phù hợp khi ứng dụng cần CRUD qua API, transaction, authorization theo record và truy vấn metadata.

Một schema minh họa:

~~~sql
CREATE TABLE dsl_definition (
  id              VARCHAR(128) PRIMARY KEY,
  project_id      VARCHAR(128) NOT NULL,
  current_revision BIGINT NOT NULL,
  language_version VARCHAR(32) NOT NULL,
  status          VARCHAR(24) NOT NULL
);

CREATE TABLE dsl_revision (
  definition_id   VARCHAR(128) NOT NULL,
  revision        BIGINT NOT NULL,
  source_text     TEXT NOT NULL,
  content_hash    VARCHAR(128) NOT NULL,
  created_by      VARCHAR(128) NOT NULL,
  created_at      TIMESTAMP NOT NULL,
  PRIMARY KEY (definition_id, revision)
);
~~~

Revision table có thể append-only. Current revision trong definition record trỏ đến revision đang được chọn hoặc published.

### Document database

Document store có thể lưu một definition cùng metadata và nested structures trong một document. Nó phù hợp khi schema linh hoạt hoặc cần đọc toàn bộ definition cùng một lần.

Cần cân nhắc kích thước document, giới hạn atomic update, query theo nested field và cách version hóa toàn bộ document.

### Object storage

Object storage phù hợp với source bundle, compiled artifact, package, test corpus, execution snapshot hoặc archive lớn. Nó có chi phí lưu trữ thấp và hỗ trợ versioning/lifecycle ở nhiều dịch vụ.

Metadata và index thường được lưu ở database riêng để tìm kiếm và quản lý ownership.

### Filesystem

Filesystem phù hợp với DSL local, workspace của IDE, development project hoặc self-hosted installation. Cần xử lý path canonicalization, atomic write, file lock, permission, symlink và concurrent edit.

### Hybrid storage

Một kiến trúc phổ biến:
- Git lưu source được review.
- Database lưu catalog, ownership, status và revision pointer.
- Object storage lưu artifact và archive.
- Cache lưu AST hoặc compiled plan.
- Event store hoặc database lưu workflow state và history.
- Search index phục vụ tìm kiếm.

Hybrid storage cần một contract rõ về nguồn chính thức và quy trình đồng bộ. Nếu không, dữ liệu có thể lệch giữa repository, catalog và artifact store.

## Thiết kế data model và identity

Một DSL registry cần mô hình hóa definition, revision, dependency và artifact.

### Definition

Definition đại diện cho một module hoặc đơn vị có thể được quản lý:

~~~text
DslDefinition
  id
  name
  projectId
  tenantId
  ownerId
  description
  currentRevision
  publishedRevision
  lifecycleStatus
  createdAt
  updatedAt
~~~

ID nên ổn định và không tái sử dụng sau khi definition bị xóa hoặc retired. Có thể dùng UUID, ULID hoặc ID có namespace.

### Revision

Revision là một snapshot nội dung bất biến:

~~~text
DslRevision
  definitionId
  revision
  source
  contentDigest
  languageVersion
  schemaVersion
  author
  createdAt
  changeSummary
  parentRevision
~~~

Nếu dùng Git commit hash, vẫn cần liên kết commit với logical definition ID và metadata của registry.

### Dependency

Dependency record có thể gồm:
- Source definition ID.
- Target definition ID hoặc package coordinate.
- Version constraint.
- Resolved immutable version.
- Dependency type.
- Optional/required.
- Content digest.

Manifest cần hỗ trợ cả dependency trực tiếp và dependency bắc cầu nếu compiler/runtime cần resolve graph.

### Artifact

Artifact nên liên kết với source revision và toolchain:

~~~text
DslArtifact
  artifactId
  definitionId
  sourceRevision
  sourceDigest
  compilerVersion
  artifactFormatVersion
  dependencyFingerprint
  targetRuntime
  artifactDigest
  storageUri
  createdAt
~~~

Nếu source hoặc compiler dependency thay đổi, artifact cũ không nên được coi là artifact của revision mới.

### Lifecycle status

Một definition có thể có trạng thái:
- Draft.
- InReview.
- Approved.
- Published.
- Deprecated.
- Retired.
- Archived.

Cần định nghĩa transition hợp lệ và quyền thay đổi status. Status không nên được suy ra chỉ từ tên branch hoặc folder.

## Lưu source DSL và quy tắc encoding

Source text cần được lưu theo một quy ước nhất quán để parser, editor và runtime đọc cùng nội dung.

### Encoding

UTF-8 là lựa chọn phổ biến cho DSL text. Cần quy định:
- Có cho phép BOM không.
- Cách xử lý invalid byte sequence.
- Unicode normalization có được áp dụng không.
- Source span tính theo byte, Unicode code point hay UTF-16 code unit.
- Cách xử lý newline.

Không nên âm thầm thay đổi Unicode normalization nếu identifier hoặc string literal có semantics phụ thuộc chuỗi gốc.

### Line ending

Repository có thể dùng LF, trong khi editor trên Windows tạo CRLF. Nếu hash source dựa trên raw bytes, line ending khác nhau tạo digest khác dù parser có thể xem nội dung tương đương.

Cần quyết định hash trên raw bytes hay canonical text. Nếu canonicalize, quy tắc phải được áp dụng nhất quán và không làm thay đổi string literal hoặc multiline value.

### Whitespace và comments

Formatter có thể chuẩn hóa whitespace, nhưng source storage nên giữ nội dung mà người dùng đã lưu nếu không có thao tác format. Nếu cần canonical source, phải phân biệt thao tác save và format.

Comment có thể chứa documentation hoặc suppression directive. Không được loại bỏ comment nếu nó mang metadata mà compiler/tooling cần.

### File size và limits

Cần giới hạn:
- Maximum source size.
- Maximum module count.
- Maximum include depth.
- Maximum dependency count.
- Maximum AST node count.
- Maximum upload size.

Giới hạn giúp bảo vệ storage và parser khỏi input quá lớn hoặc cấu trúc bất thường.

### Source validation

Có thể kiểm tra encoding, size và basic metadata khi lưu. Parse/semantic validation có thể chạy ở bước draft validation hoặc publication. Không nên ghi đè revision hợp lệ bằng source mới không hợp lệ nếu sản phẩm cần giữ bản đã publish.

## Lưu revision, history và immutable release

Versioning là một phần thiết yếu của DSL storage.

### Append-only revision

Mỗi lần save có thể tạo revision mới, hoặc hệ thống có thể lưu draft mutable riêng và chỉ tạo immutable revision khi commit. Cần xác định revision nào được tham chiếu bởi execution.

### Draft và published revision

Draft có thể thay đổi liên tục. Published revision cần bất biến để production runtime biết chính xác source đang chạy.

Ví dụ:

~~~text
Definition: pricing.vip-discount
  Draft revision: 21
  Published revision: 18
  Latest reviewed revision: 20
~~~

Một request production nên resolve published revision theo policy, không tự động dùng draft mới nhất.

### Branch và merge

Nếu DSL được quản lý qua Git hoặc registry có branching, cần xử lý:
- Concurrent edit.
- Merge conflict.
- Rename.
- Delete.
- Dependency conflict.
- Version bump.
- Approval state sau merge.

Merge source thành công không đồng nghĩa definition đã được publish. Cần pipeline validate và release riêng.

### Release tag

Release có thể gắn version semantic hoặc immutable release ID. Tag không nên được phép di chuyển âm thầm sau khi đã deploy. Nếu phải sửa release, tạo release mới.

### Audit history

Lưu:
- Ai tạo revision.
- Ai review.
- Ai approve.
- Ai publish.
- Source digest.
- Change summary.
- Toolchain version.
- Timestamp.
- Related ticket hoặc change request.

Audit không nhất thiết lưu toàn bộ source lần nữa nếu revision store đã bất biến; có thể tham chiếu revision ID và digest.

## Lưu AST, compiled artifact và cache

Source DSL được parse hoặc compile thành dữ liệu dẫn xuất.

### AST cache

AST cache giúp tránh parse lại. Cache key cần bao gồm source digest, language/grammar version và parser options. AST thường immutable và có thể bị invalidation khi source hoặc grammar thay đổi.

### Compiled artifact

Compiled artifact có thể là:
- Bytecode.
- Intermediate representation.
- Query plan.
- Workflow execution graph.
- Rule package.
- Native binary hoặc container image.

Artifact cần metadata về source revision, compiler, target runtime và dependencies.

### Build reproducibility

Cùng source và cùng toolchain inputs nên tạo artifact có thể xác định hoặc ít nhất có provenance đủ để giải thích khác biệt. Cần pin dependency và compiler version.

### Artifact integrity

Có thể lưu checksum hoặc signature. Khi load artifact, runtime xác minh digest và signature trước khi deserialize hoặc execute.

### Cache không phải source of truth

Nếu cache mất, hệ thống cần rebuild từ source. Không nên chỉnh sửa artifact binary như cách sửa source chính thức.

### Retention của artifact

Artifact đang được deploy hoặc được release tham chiếu cần được giữ. Artifact cũ không còn được dùng có thể archive hoặc xóa theo policy, nhưng cần xét rollback window và audit requirements.

## Lưu dependency và package registry

DSL module có thể import module nội bộ hoặc package từ registry.

### Dependency declaration

Manifest có thể khai báo:

~~~text
MODULE checkout {
  DEPENDS pricing = "2.4.1"
  DEPENDS common-types = "1.8.0"
}
~~~

Version range rộng như >=1.0 có thể làm build hôm nay resolve dependency khác build ngày mai. Với production, nên lưu resolved lockfile hoặc immutable digest.

### Lockfile

Lockfile ghi phiên bản dependency thực tế được dùng:
- Package coordinate.
- Version.
- Digest.
- Source registry.
- Transitive dependency.
- Toolchain metadata.

Lockfile giúp build tái lập và hỗ trợ security scan.

### Registry

Package registry cần:
- Namespace.
- Version immutability.
- Access control.
- Signature/checksum.
- Retention.
- Provenance.
- Deprecation metadata.
- Download audit.

### Dependency caching

Local cache giúp giảm network và tăng tốc. Nhưng cần verify digest và signature, tránh cache poisoning hoặc reuse package từ namespace không tin cậy.

### Dependency retirement

Package đã deprecated có thể phát warning. Package bị thu hồi vì lỗ hổng có thể cần policy chặn resolution hoặc yêu cầu pin sang version an toàn.

## Lưu runtime state và workflow instance

Định nghĩa workflow và state của một lần chạy là hai loại dữ liệu khác nhau.

### Workflow definition

Definition mô tả:
- State.
- Transition.
- Guard.
- Action.
- Timer.
- Compensation.
- Version.

Definition nên được lưu bất biến theo revision khi process instance được tạo.

### Process instance state

Instance có thể lưu:

~~~text
WorkflowInstance
  instanceId
  definitionId
  definitionRevision
  currentState
  variables
  activeTasks
  pendingTimers
  version
  startedAt
  updatedAt
~~~

### Event history

Event history có thể lưu:
- Event received.
- Transition selected.
- Action started/completed.
- Retry.
- Compensation.
- State change.
- Error.
- Manual intervention.

History giúp audit và phục hồi, nhưng có thể tăng nhanh. Cần partition, retention và archive.

### Checkpoint và snapshot

Với workflow dài, có thể lưu snapshot định kỳ để phục hồi nhanh thay vì replay toàn bộ event history. Snapshot cần có schema version và definition revision.

### Active instance và definition update

Khi definition mới được publish, instance đang chạy có thể:
- Tiếp tục pin revision cũ.
- Migrate ở checkpoint an toàn.
- Chỉ áp dụng definition mới cho instance mới.

Policy cần rõ. Không nên tự động thay definition của instance đang chạy mà không migration plan.

## Atomic write và consistency khi lưu

Một lần save DSL có thể bao gồm source, metadata, revision pointer và dependency manifest. Nếu chỉ một phần được ghi, registry có thể trỏ đến revision không tồn tại hoặc artifact không khớp source.

### Atomic database transaction

Nếu metadata và revision cùng database, có thể ghi trong một transaction:

~~~text
BEGIN
  INSERT dsl_revision(...)
  UPDATE dsl_definition
    SET current_revision = :newRevision
  INSERT audit_record(...)
COMMIT
~~~

Nếu insert revision thất bại, pointer không được cập nhật. Nếu commit thành công, người đọc thấy revision hoàn chỉnh.

### Object storage và database

Nếu source hoặc artifact nằm trong object storage còn metadata ở database, hai hệ thống không có transaction chung. Một pattern:
1. Upload object vào key immutable/staging.
2. Xác minh checksum.
3. Commit metadata record trỏ đến object.
4. Dọn staging object nếu bước metadata thất bại.

Nếu database commit thất bại sau upload, có thể tồn tại orphan object; cleanup job cần tìm object chưa được tham chiếu.

### Atomic file write

Với filesystem:
1. Ghi file tạm cùng filesystem.
2. Flush và đóng file.
3. Kiểm tra checksum hoặc parse nếu policy yêu cầu.
4. Atomic rename sang path đích nếu filesystem hỗ trợ.

Không nên truncate file hiện tại rồi ghi nội dung mới trực tiếp nếu process crash có thể làm mất cả bản cũ.

### Concurrent save

Hai người có thể cùng sửa một definition. Cần optimistic concurrency:
- Client gửi expected revision.
- Storage kiểm tra current revision.
- Nếu khác, trả conflict.
- Người dùng merge hoặc reload trước khi save.

Không nên last-write-wins cho source quan trọng nếu nó có thể âm thầm xóa thay đổi của người khác.

### Read consistency

Sau khi publish, runtime cần đọc đúng revision đã được commit. Nếu metadata và object storage có replication delay, có thể cần read-after-write guarantee hoặc kiểm tra object existence/digest trước khi expose release.

## Tìm kiếm và indexing DSL

Khi số lượng definition lớn, cần khả năng tìm kiếm theo metadata và nội dung.

### Metadata index

Các field thường được index:
- Definition ID.
- Name.
- Project/tenant.
- Owner.
- Tags.
- Language version.
- Status.
- Updated time.
- Published revision.
- Dependency.
- Category.

### Full-text search

Có thể index source DSL để tìm keyword, function, symbol hoặc pattern. Search index là dữ liệu dẫn xuất; cần cập nhật sau commit và có thể rebuild từ source.

### Symbol index

IDE hoặc registry có thể index:
- Definition.
- Function.
- Type.
- Rule.
- Workflow state.
- Reference.
- Import.
- Deprecated symbol.

Index cần gắn source revision để navigation không trỏ đến location cũ.

### Incremental indexing

Sau revision mới, chỉ index module thay đổi và dependency bị ảnh hưởng nếu có thể. Tuy nhiên, search index phải có version hoặc watermark để client biết kết quả có stale không.

### Authorization-aware search

Search result phải tuân theo quyền đọc source. Không được trả snippet hoặc symbol name từ definition mà user không có quyền truy cập.

## Security và quyền truy cập storage

Source DSL có thể chứa logic kinh doanh, endpoint nội bộ, tên database, secret reference và thông tin kiến trúc. Storage cần bảo vệ cả nội dung lẫn metadata.

### Authorization theo scope

Quyền có thể được áp dụng ở:
- Organization.
- Project.
- Repository.
- Module.
- Revision.
- Artifact.
- Workflow instance.
- Execution history.

Một user có thể đọc source nhưng không được publish. Một operator có thể đọc execution history nhưng không được sửa definition.

### Tenant isolation

Tenant ID cần được gắn vào resource identity và query filter. Không tin tenant ID do client gửi nếu chưa xác minh. Cache, search index và object key cần phân vùng theo tenant policy.

### Encryption at rest

Database, object storage, backup và archive có thể cần encryption at rest. Key management cần tách quyền đọc key khỏi quyền truy cập source.

### Encryption in transit

API, registry và storage connector cần TLS theo policy. Không truyền credential trong URL hoặc log.

### Secret reference

DSL nên lưu reference đến secret manager thay vì secret value:

~~~text
database.password = SECRET_REF("checkout/database/password")
~~~

Secret value được resolve lúc runtime theo workload identity. Không ghi secret vào source history, compiled artifact, cache hoặc diagnostic.

### Audit

Các thao tác cần audit:
- Read/export source nhạy cảm.
- Create/update revision.
- Approve/publish.
- Change permission.
- Download artifact.
- Restore backup.
- Delete/archive.
- Access workflow state.
- Change retention policy.

Audit log cần được bảo vệ khỏi người dùng có quyền sửa definition.

### Data classification

Có thể phân loại:
- Public.
- Internal.
- Confidential.
- Restricted.

Retention, encryption, export và access policy có thể phụ thuộc classification.

## Backup, restore và disaster recovery

Storage DSL là một phần của khả năng vận hành ứng dụng. Backup cần bao gồm các dữ liệu liên quan, không chỉ source file.

### Thành phần cần backup

- Source definitions và revisions.
- Metadata và ownership.
- Dependency lockfiles hoặc manifests.
- Published artifact và signature.
- Schema/version registry.
- Workflow instance state.
- Event history cần retention.
- Audit records.
- Encryption key metadata hoặc key recovery procedure.
- Storage configuration và catalog.

Không nhất thiết mọi cache cần backup vì có thể tái tạo. Cần phân biệt dữ liệu authoritative và dữ liệu dẫn xuất.

### Backup consistency

Nếu source ở Git, metadata ở database và artifact ở object storage, backup ở các thời điểm khác nhau có thể tạo snapshot không đồng nhất.

Có thể:
- Ghi một catalog checkpoint/version.
- Chụp snapshot database.
- Lưu immutable object version.
- Ghi manifest backup gồm revision và object digest.
- Chặn hoặc phối hợp các publication quan trọng trong snapshot window nếu cần.

### Full và incremental backup

Full backup lưu toàn bộ dữ liệu trong phạm vi. Incremental backup lưu thay đổi kể từ checkpoint. Cần test chain restore vì incremental backup vô ích nếu base backup hoặc log segment bị thiếu.

### Point-in-time recovery

Database có thể hỗ trợ point-in-time recovery. Cần xác định object storage và Git revision tương ứng với thời điểm phục hồi. Một restore không đồng bộ có thể làm metadata trỏ đến artifact chưa tồn tại.

### Restore test

Backup chỉ đáng tin khi restore được kiểm chứng. Test định kỳ:
1. Khôi phục database vào môi trường cô lập.
2. Khôi phục source/object version tương ứng.
3. Kiểm tra checksum và revision references.
4. Load module bằng runtime được hỗ trợ.
5. Kiểm tra workflow state có thể tiếp tục hoặc migrate.
6. Xác nhận permission và encryption.
7. Ghi thời gian phục hồi thực tế.

### RPO và RTO

- Recovery Point Objective (RPO): lượng dữ liệu tối đa có thể mất theo thời gian.
- Recovery Time Objective (RTO): thời gian mục tiêu để khôi phục dịch vụ.

Source registry có thể yêu cầu RPO rất thấp, trong khi cache có thể tái tạo. Workflow state hoặc audit có yêu cầu riêng. Không nên áp dụng cùng một backup policy cho mọi loại dữ liệu.

## Retention, archival và deletion

Không phải dữ liệu DSL nào cũng cần giữ mãi. Retention cần cân bằng audit, compliance, storage cost và privacy.

### Retention theo loại dữ liệu

| Dữ liệu | Chính sách có thể áp dụng |
|---|---|
| Published source revision | Giữ theo release/support policy |
| Draft revision | Giới hạn theo thời gian hoặc số revision |
| Compiled artifact | Giữ theo deployment và rollback window |
| AST cache | Evict hoặc tái tạo |
| Workflow state | Giữ đến khi hoàn tất và hết retention |
| Execution logs | Theo observability policy |
| Audit records | Theo compliance requirement |
| Temporary upload | TTL ngắn |
| Orphan artifact | Cleanup sau grace period |

### Archive

Archive có thể chuyển dữ liệu ít truy cập sang storage rẻ hơn. Cần giữ metadata để tìm và restore. Archive không nên làm mất integrity hoặc version identity.

### Delete và tombstone

Xóa definition có thể cần soft delete hoặc tombstone để:
- Ngăn ID được tái sử dụng.
- Giữ reference từ execution history.
- Hỗ trợ audit.
- Phân biệt resource không tồn tại với resource đã retired.

Physical deletion có thể diễn ra sau retention period nếu policy cho phép.

### Legal hold và retention exception

Một số source hoặc audit record có thể phải giữ do legal hold. Retention engine cần hỗ trợ hold có scope và audit, không xóa dữ liệu đang bị hold.

### Data subject deletion

Nếu source hoặc execution history chứa dữ liệu cá nhân, cần policy xóa hoặc pseudonymize theo yêu cầu áp dụng. Không nên xóa source revision một cách mù quáng nếu nó cần cho audit; có thể cần tách personal data khỏi source và lưu reference an toàn.

### Cascade delete

Xóa module có thể ảnh hưởng dependency, artifact, workflow instance và execution history. Cần xác định delete cascade hay restrict. Không nên tự động xóa artifact đang được deployment hoặc instance active tham chiếu.

## Migration của storage schema và dữ liệu DSL

Storage schema cũng thay đổi theo phiên bản ứng dụng.

### Schema migration

Database có thể cần thêm field, đổi type, tạo index hoặc tách bảng. Migration cần có version và chạy theo thứ tự xác định.

### Expand-and-contract

Một chiến lược an toàn:
1. Thêm field/table mới mà code cũ vẫn hoạt động.
2. Deploy code đọc/ghi được cả schema cũ và mới.
3. Backfill dữ liệu.
4. Chuyển reader/writer sang schema mới.
5. Xác nhận dữ liệu.
6. Xóa field cũ ở release sau khi rollback window kết thúc.

### Source format migration

Source DSL có thể được chuyển đổi bằng migration tool. Nên lưu revision gốc và tạo revision mới; không ghi đè lịch sử đã publish.

### Artifact migration

Compiled artifact thường dễ rebuild hơn migrate. Nếu format không tương thích, có thể invalidate và compile lại từ source. Nếu source không còn, cần archive artifact cùng runtime/toolchain tương thích hoặc cung cấp converter.

### Workflow state migration

Process instance đang chạy cần mapping state, variable, timer và pending task. Migration cần validate invariant và có rollback/recovery plan.

### Idempotent migration

Chạy migration nhiều lần không được làm dữ liệu thay đổi lặp hoặc mất mát. Lưu migration version và transaction boundary phù hợp.

## Lifecycle và publication flow

Lưu trữ DSL cần hỗ trợ các trạng thái từ draft đến retirement.

Một flow minh họa:

~~~text
Create draft
    |
    v
Save revision
    |
    v
Validate source
    |
    v
Review
    |
    v
Approve
    |
    v
Publish immutable revision
    |
    v
Build / compile artifact
    |
    v
Deploy or activate
    |
    v
Monitor usage
    |
    v
Deprecate
    |
    v
Archive / retire
~~~

### Draft save

Draft có thể thay đổi nhiều lần. Hệ thống có thể lưu autosave revision hoặc chỉ lưu revision khi user commit. Cần phân biệt autosave snapshot với revision có thể review/publish.

### Review và approval

Review record nên gắn với exact source digest. Nếu source thay đổi sau review, approval cũ không còn áp dụng cho revision mới.

### Publish

Publish tạo immutable release hoặc cập nhật published pointer một cách atomic. Runtime cần resolve revision đã publish, không đọc file draft đang thay đổi.

### Deploy và activation

Artifact được deploy cần gắn source revision và build provenance. Có thể deploy nhiều version song song trong rollout. Storage phải giữ artifact đủ lâu cho rollback.

### Deprecate và retire

Definition có thể được đánh dấu deprecated để ngăn tạo instance mới nhưng vẫn cho instance cũ hoàn tất. Retire cần kiểm tra dependency và active usage trước khi xóa.

## Concurrency, locking và conflict resolution

Nhiều người hoặc service có thể đọc/ghi cùng một definition.

### Optimistic concurrency

Client đọc revision 12 rồi gửi update với expectedRevision 12. Nếu current revision đã là 13, server trả conflict thay vì ghi đè.

### Pessimistic lock

Lock có thể hữu ích trong thao tác migration dài hoặc exclusive publish, nhưng cần lease và timeout để tránh lock treo khi client mất kết nối.

### Merge conflict

Với source DSL, merge text có thể tạo source parse được nhưng semantics sai. Sau merge cần parse, type check và test. Semantic merge có thể giúp với cấu trúc rule hoặc workflow, nhưng không thay thế review.

### Concurrent publish

Hai revision có thể cùng được approve. Cần atomic compare-and-swap trên published pointer hoặc release sequence. Một release không được vô tình trỏ về revision cũ do race.

### Read/write isolation

Runtime có thể đang thực thi revision cũ trong khi admin publish revision mới. Mỗi execution nên pin revision ID để không đọc source hoặc dependency thay đổi giữa chừng.

## Hiệu năng và khả năng mở rộng storage

Storage cần đáp ứng cả số lượng definition và tần suất đọc.

### Read-heavy workload

Runtime thường đọc nhiều và ghi ít. Có thể dùng:
- Local cache.
- Immutable revision.
- CDN hoặc object cache cho artifact.
- Read replica cho catalog.
- Preload module phổ biến.

Cache phải có version key và invalidation rõ.

### Write workload

IDE autosave hoặc UI editor có thể tạo nhiều write nhỏ. Có thể debounce autosave, nhưng cần bảo đảm người dùng không mất thay đổi và revision quan trọng được commit.

### Partitioning

Database có thể partition theo tenant, project hoặc time. Execution history có thể partition theo ngày hoặc workflow type. Cần tránh partition strategy làm query theo definition ID quá chậm.

### Large module và streaming

Module lớn có thể được đọc streaming để tránh load toàn bộ vào memory. Object storage có thể dùng multipart upload cho bundle lớn. Parser vẫn cần source snapshot nhất quán.

### Connection pool và backpressure

Storage service cần giới hạn concurrent request. Khi database hoặc object store quá tải, host có thể queue hoặc reject theo policy. Không nên để hàng nghìn parser worker đồng loạt đọc cùng module sau cache invalidation.

### Capacity planning

Theo dõi:
- Source bytes.
- Revision growth.
- Artifact bytes.
- Workflow state count.
- History volume.
- Read/write rate.
- Cache hit ratio.
- Backup size.
- Restore time.
- Storage latency.
- Orphan object count.

## Portability và export/import DSL

Người dùng có thể cần chuyển DSL giữa workspace, environment hoặc platform.

### Export bundle

Một bundle có thể gồm:
- Source revision.
- Manifest.
- Dependency lockfile.
- Schema references.
- Signature/checksum.
- Documentation.
- Migration metadata.

Không nên export secret value; chỉ export secret reference hoặc placeholder có hướng dẫn cấu hình lại.

### Import validation

Khi import, kiểm tra:
- Bundle integrity.
- Language version.
- Dependency availability.
- Namespace conflict.
- Permission.
- Schema compatibility.
- Unsupported plugin.
- Artifact format.
- Tenant ownership.

### Import preview

Preview có thể hiển thị definition mới, revision conflict, dependency thiếu và resource sẽ được tạo. Không ghi dữ liệu cho đến khi người dùng xác nhận nếu import có tác động.

### Cross-environment promotion

Promotion từ dev sang staging rồi production nên giữ nguyên source digest hoặc release ID. Environment-specific configuration được lưu riêng và tham chiếu qua parameter/secret reference.

### Portability limits

Một DSL có thể phụ thuộc host function hoặc plugin riêng của platform. Bundle cần khai báo requirement và import tool phải báo rõ phần không portable.

## Observability và audit cho storage

Storage cần cung cấp khả năng theo dõi thao tác và phát hiện bất thường.

### Audit events

Có thể ghi:
- DefinitionCreated.
- RevisionSaved.
- RevisionReviewed.
- RevisionApproved.
- RevisionPublished.
- ArtifactBuilt.
- ArtifactDownloaded.
- DefinitionDeprecated.
- DefinitionArchived.
- DefinitionDeleted.
- PermissionChanged.
- BackupRestored.

Mỗi event nên có actor, resource, revision, timestamp, outcome và correlation ID.

### Metrics

Metrics có thể gồm:
- Definition count theo status.
- Revision creation rate.
- Source/artifact storage bytes.
- Read/write latency.
- Conflict rate.
- Failed upload.
- Orphan object count.
- Cache hit/miss.
- Backup success/failure.
- Restore duration.
- Retention deletion count.
- Search index lag.

### Logs

Log cần tránh source text hoặc secret value. Có thể ghi definition ID, revision, digest prefix, operation và reason code.

### Integrity check

Job định kỳ có thể kiểm tra:
- Object digest khớp metadata.
- Artifact trỏ đến source revision tồn tại.
- Dependency reference còn hợp lệ.
- Published pointer không trỏ đến revision thiếu.
- Signature còn xác minh được.
- Workflow state có definition version tương ứng.

## Kiểm thử lưu trữ DSL

Storage testing cần bao phủ correctness, atomicity, concurrency, recovery, security và retention.

### CRUD và revision test

Kiểm tra create, read, update, publish, archive và delete theo lifecycle. Xác nhận revision immutable và published pointer đúng.

### Atomic write test

Giả lập process crash hoặc storage failure giữa các bước upload, metadata commit và pointer update. Không để registry trỏ đến object chưa hoàn chỉnh.

### Concurrent update test

Hai client cùng cập nhật một revision. Xác nhận optimistic conflict hoặc lock behavior đúng, không mất dữ liệu.

### Dependency test

Thay đổi module dependency và xác nhận manifest, artifact fingerprint và invalidation được cập nhật.

### Serialization test

Round-trip source, metadata và artifact qua storage. Kiểm tra UTF-8, newline, Unicode, null, large source và schema version.

### Backup/restore test

Restore vào môi trường cô lập, xác minh digest, revision, metadata, dependency và runtime load. Đo RPO/RTO thực tế.

### Security test

Kiểm tra:
- Cross-tenant read/write.
- Unauthorized export.
- Path traversal.
- Object key guessing.
- Secret leakage.
- Audit tampering.
- Signed artifact verification.
- Retention bypass.

### Retention test

Kiểm tra TTL, legal hold, tombstone, archive restore và delete dependency. Không xóa artifact đang được active deployment tham chiếu.

### Performance test

Đo read/write latency, search, concurrent save, large module upload, cache cold start, backup throughput và restore duration.

### Fault injection

Mô phỏng database unavailable, object storage timeout, disk full, checksum mismatch, network interruption và partial upload. Hệ thống cần trả error rõ và giữ dữ liệu nhất quán.

## Những lỗi thiết kế thường gặp

### Lưu source và artifact như một loại dữ liệu

Artifact có thể tái tạo và phụ thuộc toolchain; source là dữ liệu gốc. Cần tách lifecycle và retention.

### Ghi đè revision đã publish

Điều này làm mất khả năng tái dựng behavior production. Published revision nên bất biến.

### Không có stable identity

Dùng file path làm ID khiến rename làm đứt dependency và history. Dùng ID ổn định cùng path/name có thể thay đổi.

### Không lưu dependency fingerprint

Artifact có thể được nạp dù dependency đã thay đổi. Lưu lockfile và resolved digest.

### Cập nhật source và metadata không atomic

Registry có thể trỏ đến revision không tồn tại. Dùng transaction hoặc staged object rồi commit metadata.

### Last-write-wins cho source

Một người có thể xóa thay đổi của người khác. Dùng expected revision và conflict handling.

### Không phân biệt draft và published

Runtime có thể đọc source đang chỉnh sửa. Pin immutable published revision.

### Dùng cache làm nguồn chính

Cache bị mất sẽ làm mất definition nếu không có source store. Cache phải tái tạo được.

### Backup không nhất quán

Database snapshot có thể trỏ đến object chưa được backup. Gắn checkpoint và manifest digest.

### Retention xóa dữ liệu đang được tham chiếu

Artifact hoặc workflow definition có thể bị xóa khi active deployment/instance vẫn cần. Theo dõi reference và lifecycle dependency.

### Không kiểm tra restore

Backup thành công không chứng minh restore thành công. Cần restore drill định kỳ.

### Lưu secret trực tiếp trong source

Secret có thể lan vào revision history, artifact, log và backup. Dùng secret reference và runtime resolution.

### Không có audit

Không biết ai thay đổi hoặc publish definition. Ghi audit bất biến cho thao tác quan trọng.

## Quy trình thiết kế hệ thống lưu trữ DSL

Một quy trình triển khai có thể đi theo các bước:

1. **Phân loại dữ liệu:** source, metadata, dependency, artifact, runtime state, history, cache và documentation.
2. **Chọn source of truth:** xác định Git, database registry hoặc storage service chịu trách nhiệm chính.
3. **Định nghĩa identity:** stable definition ID, revision ID, artifact ID và tenant/project scope.
4. **Thiết kế schema:** revision, manifest, dependency, lifecycle status và audit.
5. **Quy định encoding:** UTF-8, newline, normalization, source span và size limits.
6. **Thiết kế versioning:** immutable revision, draft, review, publish và release tag.
7. **Tách dữ liệu dẫn xuất:** AST cache, compiled artifact và search index có fingerprint riêng.
8. **Thiết kế atomic write:** database transaction, staged object, checksum và atomic pointer update.
9. **Xử lý concurrency:** optimistic version, lock lease, merge conflict và pinned read.
10. **Bảo vệ storage:** authorization, tenant isolation, encryption, secret reference và audit.
11. **Quản lý backup/restore:** consistency checkpoint, retention, RPO/RTO và restore drill.
12. **Thiết kế lifecycle:** archive, tombstone, deletion, legal hold và reference tracking.
13. **Tối ưu discovery:** metadata index, full-text search, symbol index và access-aware results.
14. **Hỗ trợ portability:** export/import bundle, dependency resolution và promotion.
15. **Kiểm thử:** atomicity, concurrency, integrity, security, retention, backup và performance.
16. **Vận hành:** metrics, alert, orphan cleanup, reconciliation và restore procedure.

Mỗi loại dữ liệu nên có một storage contract ghi rõ owner, source of truth, identity, version, consistency, retention, access policy, backup policy và cách phục hồi. Contract giúp compiler, runtime, IDE, registry và deployment service cùng hiểu dữ liệu nào được phép đọc hoặc ghi và ở thời điểm nào.

## Kết luận

Lưu trữ DSL là một phần của quản trị vòng đời, bao gồm source definition, metadata, dependency, artifact, runtime state, execution history và tài liệu hỗ trợ. Một hệ thống cần phân biệt source có thẩm quyền với dữ liệu dẫn xuất, giữ revision đã publish bất biến và gắn artifact với source digest cùng toolchain version.

Git, relational database, document store, object storage và filesystem đều có vai trò riêng; kiến trúc hybrid cần xác định single source of truth và cách đồng bộ. Atomic write, optimistic concurrency, dependency tracking, authorization, tenant isolation, encryption, backup/restore, retention và audit bảo vệ dữ liệu qua toàn bộ vòng đời.

Cache và compiled artifact cần có thể tái tạo, còn workflow state và history cần persistence/versioning phù hợp để process tiếp tục sau restart hoặc migration. Khi storage contract, lifecycle và recovery được đặc tả rõ, DSL có thể được chỉnh sửa, review, phát hành, thực thi và lưu trữ lâu dài mà vẫn giữ được tính nhất quán, bảo mật và khả năng tái lập.
