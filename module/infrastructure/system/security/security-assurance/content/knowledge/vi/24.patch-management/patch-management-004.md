# Patch Dependency: Quản lý phụ thuộc bản vá trong Patch Management và Security Assurance

## 1. Vấn đề: vì sao “có bản vá” chưa đủ để “đã vá an toàn”?

Một nền tảng SaaS quản lý hóa đơn nhận cảnh báo lỗ hổng nghiêm trọng trong thành phần xử lý HTTP. Đội ứng dụng nâng dependency ở file build và chạy unit test thành công. Tuy nhiên, artifact đang chạy vẫn dùng base image cũ; một module phụ thuộc API đã bị loại bỏ; service khác vẫn giao tiếp bằng protocol cũ; bản vá hệ điều hành chờ reboot; và database migration chưa tương thích worker xử lý nền.

Nếu triển khai ngay, ứng dụng có thể lỗi hoặc mất tính sẵn sàng. Nếu chỉ cập nhật package rồi đóng ticket, lỗ hổng có thể vẫn tồn tại trong production. Cả hai tình huống đều bắt nguồn từ việc **không mô hình hóa các phụ thuộc của việc vá lỗi**.

**Patch dependency (phụ thuộc bản vá)** là quan hệ trong đó việc lựa chọn, cài đặt, kích hoạt, kiểm tra hoặc hoàn tác một bản vá **phụ thuộc vào phiên bản, cấu hình, thành phần, thứ tự thay đổi, trạng thái vận hành hoặc hành động khác**. Phụ thuộc có thể là kỹ thuật (package A cần library B), vận hành (kernel fix cần reboot), kiến trúc (API mới cần consumer tương thích) hoặc an toàn dữ liệu (schema migration phải đi trước release).

Trong module **SECURITY_SECURITY_ASSURANCE**, mục tiêu là đánh giá có bằng chứng rằng hệ thống đáp ứng các mục tiêu bảo mật từ phân tích rủi ro và security controls tới kiểm thử, audit, khắc phục và assurance liên tục. Điều cần chứng minh không chỉ là **patch đã tải xuống hoặc installer báo thành công**, mà là:

**Vulnerability/requirement → affected assets → dependency graph → approved change plan → prerequisites → patch deployment → activation → security/functional verification → residual risk & evidence → ongoing monitoring.**

> Chỉ có thể coi bản vá đã giảm rủi ro trong phạm vi xác định khi phiên bản/biện pháp sửa thực sự có hiệu lực trên tài sản bị ảnh hưởng, các phụ thuộc cần thiết được đáp ứng và bằng chứng kiểm thử phù hợp với threat/requirement.

### Kịch bản xuyên suốt

Bài dùng ví dụ giả lập **Invoice SaaS** chạy Java/Spring, Kubernetes, PostgreSQL, container images, cloud IAM/KMS và background export workers. Tên phiên bản hay lỗ hổng trong ví dụ không đại diện advisory/CVE thật; khi xử lý sản xuất phải kiểm tra advisories chính thức và inventory hệ thống.

## 2. Những khái niệm dễ bị nhầm

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Patch** | Sửa gì ở software/firmware/config? | Security update cho runtime. |
| **Update/upgrade** | Chuyển sang version/release nào? | Framework minor/major release. |
| **Patch prerequisite** | Điều kiện bắt buộc trước khi cài/khởi động? | Package manager, firmware, runtime baseline. |
| **Package dependency** | Artifact cần packages/versions nào để build/run? | Module Spring cần library xử lý JSON. |
| **Transitive dependency** | Thành phần được kéo vào gián tiếp? | A → B → C. |
| **Version constraint** | Phiên bản nào tương thích hoặc bị loại trừ? | B yêu cầu C trong version range. |
| **Patch supersedence** | Patch mới thay thế patch cũ theo vendor? | Cumulative update có thể bao hàm fixes trước. |
| **Patch conflict** | Hai thay đổi gây bất tương thích? | Patch loại API mà plugin cũ dùng. |
| **Operational dependency** | Có cần reboot, restart, drain, migrate? | Kernel update chờ boot kernel mới. |
| **Service dependency** | Consumer nào phụ thuộc contract của provider? | Export worker dùng event schema chung. |
| **Security control dependency** | Control cần identity/key/trust/policy nào? | JWT validation cần signing key trust. |
| **Patch validation** | Fix thực sự có hiệu lực ở đúng runtime? | Digest mới và negative test đều đạt. |
| **Patch exception** | Vì sao chưa vá và ai chấp nhận tạm thời? | Legacy device chưa thể nâng version. |

**Patch dependency không chỉ là package graph.** Maven resolve thành công nhưng production rollout vẫn có thể thất bại vì schema không tương thích old workers. Ngược lại, package graph tương thích không chứng minh vulnerability đã biến mất khỏi image đang chạy.

## 3. Mục tiêu bảo mật và vận hành

Phân tích phụ thuộc hỗ trợ nhiều mục tiêu đồng thời:

- **Confidentiality:** loại vulnerabilities có thể lộ dữ liệu, không mở policy quá rộng để bản vá “chạy được”.
- **Integrity:** không áp bản vá sai nguồn/version, không làm sai nghiệp vụ hoặc phá dữ liệu.
- **Availability:** kiểm soát reboot, downtime, degraded operations, SLO và DR.
- **Provenance:** tin đúng nguồn vendor, repository, signing key và artifact.
- **Recoverability:** rollback/roll-forward, backup restore, contingency plan.
- **Least privilege:** patch pipeline không đòi production admin vô hạn.
- **Auditability:** ghi ai duyệt, patch nào, tài sản nào, thời điểm và evidence.
- **Risk reduction:** verify vulnerable component/path đã được xử lý đúng scope.

Đội security muốn giảm **time exposed**, đội vận hành muốn ổn định, product cần liên tục và data owner cần tránh data corruption. Dependency analysis giúp quyết định một đường thay đổi an toàn thay vì tranh luận “vá ngay mọi thứ” với “hoãn cho chắc”.

## 4. Các loại quan hệ trong dependency model

| Quan hệ | Ví dụ | Nguy cơ khi bỏ sót |
| --- | --- | --- |
| **Prerequisite** | Patch P cần runtime hoặc firmware minimum. | Không cài/không hoạt động. |
| **Supersedes** | Patch Q bao hàm fixes P theo advisory. | Cài thừa hoặc đánh giá nhầm coverage. |
| **Conflicts-with** | Security library mới bỏ API plugin cũ. | Runtime crash/incompatibility. |
| **Requires-version-range** | Service A cần library B v5+. | Load/serialization error. |
| **Must-precede** | Expand DB schema trước writer mới. | Query errors hoặc data loss. |
| **Must-follow** | Xóa old schema sau khi consumers cập nhật. | Old consumers fail. |
| **Requires-restart** | Loaded library/process phải reload. | Patch trên disk, process vẫn cũ. |
| **Requires-reboot** | Kernel/driver patch chưa active. | Vulnerable kernel vẫn chạy. |
| **Requires-coordination** | API producer/consumer đổi cùng kỳ. | Partial rollout không tương thích. |
| **Runtime-linkage** | Image patched phải rollout đúng replicas. | Registry mới nhưng production cũ. |
| **Key/trust dependency** | Library mới cần CA/cert/signature profile. | Kết nối lỗi hoặc fallback yếu. |
| **Recovery dependency** | Data migration cần restore checkpoints. | Rollback binary nhưng DB không lùi được. |
| **Control dependency** | Policy mới cần identity claim từ IdP. | False deny hoặc fail open. |
| **Timing/capacity** | Drain node cần headroom cho pods. | Downtime hoặc rollout stuck. |

Không vẽ mọi quan hệ thành một mũi tên “A phụ thuộc B”. Cần ghi **loại cạnh, điều kiện kiểm chứng và owner**. Hai packages cùng có mặt không nhất thiết tạo thứ tự cài bắt buộc.

## 5. Mô hình dependency graph

**Nodes** có thể là assets, software versions, patch candidates, schema/contracts, deployment tasks, prerequisites, maintenance actions và verification gates. **Edges** có thể là requires, supersedes, conflicts, must-precede, deployed-from, validated-by hoặc runs-on.

~~~mermaid
flowchart LR
    A["Vendor advisory and affected version"] --> B["Select fixed runtime / library"]
    B --> C["Update dependency locks / BOM"]
    C --> D["Build immutable image"]
    D --> E["SBOM, provenance and vulnerability review"]
    E --> F["Integration + security negative tests"]
    F --> G["Canary deployment"]
    G --> H["Progressive production rollout"]
    H --> I["Runtime digest and health verification"]
    I --> J["Close finding with evidence"]
    K["Compatible schema expansion"] --> G
    L["Validated rollback / restore plan"] --> G
    M["Node capacity and readiness"] --> H
~~~

Đây là **workflow DAG minh họa**, không phải thủ tục bắt buộc cho mọi sản phẩm. Mỗi cạnh nên gắn evidence: dependency resolution, schema compatibility, tests, ready nodes hoặc runtime version.

### Topological order và chu trình

Một đồ thị quan hệ **must-precede** không có chu trình có thể được sắp theo thứ tự topology; các nhánh độc lập có thể song song nếu đủ isolation/capacity. Nếu A cần B mới trong khi B mới chỉ chạy được với A mới, có chu trình triển khai và cần **compatibility window, expand-contract, adapter/facade hoặc release trung gian**, không thể chỉ đổi thứ tự.

## 6. Package dependency graph khác installation order

Package manager giải quyết **build/runtime resolution**, còn thứ tự rollout production phải xét:

- Old/new versions có chạy song song an toàn?
- API, DB và event contracts có backward/forward compatibility?
- Service A và B dùng shared state hoặc chung tenant table?
- Cluster có quorum/minimum available replicas khi reboot?
- Trust store/key rotation cần giai đoạn chồng lấn?
- Có thể rollback code sau data migration không?
- Đâu là security test/release gate bắt buộc?

Ví dụ fix một HTTP library cần JDK mới, JDK mới cần base image khác, image mới đi cùng native library khác, và export worker cần schema mới. **Dependency tree là đầu vào, không phải toàn bộ patch plan**.

## 7. Hard prerequisite và operational prerequisite

**Hard prerequisite:** thiếu nó thì patch không cài đúng hoặc ứng dụng không thể vận hành (ví dụ ABI, minimum runtime, schema cần thiết).

**Operational prerequisite:** patch có thể cài nhưng không đạt độ an toàn/tin cậy yêu cầu nếu thiếu (ví dụ tested backup, drain, canary metrics, rollback plan).

| Layer | Hard prerequisite | Operational prerequisite |
| --- | --- | --- |
| OS/kernel | Servicing/package manager hoặc kernel ABI yêu cầu. | Node drain, reboot, image recovery. |
| Firmware/driver | Model/BIOS/firmware compatibility. | Vendor method, power/maintenance controls. |
| App/library | API/SDK/JDK version được hỗ trợ. | Integration, regression, canary. |
| Database | Engine feature/schema version. | Restore drill, replication lag monitor. |
| Kubernetes | Supported version skew/feature gates. | Headroom, PDB, readiness. |
| IAM/crypto | Key/trust/claims được chấp nhận. | Overlap rotation, audit, incident rollback. |

Không đủ ghi “backup exists” hoặc “version supports update”. Acceptance criteria phải có **resource IDs, exact version, readiness, test method, owner, timestamp và evidence**. Backup chưa kiểm tra restore không được mặc nhiên là recovery prerequisite đạt.

## 8. Supersedence, cumulative updates và backports

Một số nhà cung cấp phát hành **cumulative updates** hoặc metadata nêu patch mới có thể thay thế patch cũ. Tuy nhiên, quan hệ supersedence phụ thuộc **vendor, product, edition, build, release channel và applicability rules**.

### Câu hỏi trước khi chọn patch

1. Asset đang chạy product/build/architecture/channel nào, evidence từ đâu?
2. Advisory mô tả affected/fixed versions và prerequisites gì?
3. Patch mới có thực sự supersede patch cũ ở đúng profile?
4. Có bắt buộc cài servicing component, firmware hoặc repository metadata trước?
5. Patch chỉ tải/cài hay đã reboot và **activated**?
6. Vendor của bản phân phối có backport fix mà vẫn giữ upstream version string không?
7. Scanner dùng detection logic nào; có sai vì so version text đơn giản?

### Hai sai lầm đối nghịch

**Cài mọi patch cũ theo số thứ tự** dù vendor đã cung cấp cumulative update path có thể gây việc thừa hoặc conflict. Nhưng **cài một cumulative OS patch rồi cho rằng mọi phần mềm, firmware và driver cũng đã được sửa** là sai phạm vi.

**Backport** có thể sửa mã bị ảnh hưởng mà không đổi lên upstream major/minor version. Vì vậy, không tự dismiss scanner finding hay tự xác nhận fixed chỉ dựa vào version string; cần vendor advisory, package build/revision, patch metadata và runtime readback.

## 9. Conflicts, version constraints và API/ABI compatibility

Patch làm thay đổi một thư viện có thể làm hỏng bên phụ thuộc:

- Public API bị bỏ/đổi method signature, khiến plugin hoặc adapter cũ lỗi.
- Serialization schema hoặc default validation bị siết, làm messages cũ bị từ chối.
- JDK nâng lên phiên bản không còn hỗ trợ bytecode/client cũ.
- Base image đổi native library hoặc cryptographic provider.
- TLS defaults mới không tương thích external vendor chưa nâng.
- ORM/DB driver mới thay hành vi transaction, pooling hoặc timeout.
- Framework security update thay endpoint matching hay authorization mặc định.

### Build xanh chưa chắc runtime đúng

Resolver có thể chọn versions hợp lệ theo metadata, nhưng lỗi chỉ xuất hiện khi reflection, dependency injection, class loading, JNI, serialization hoặc đường xử lý ít chạy được thực thi. Do đó cần **unit + integration + contract + compatibility + security regression + performance tests** đúng affected paths.

| Câu hỏi | Evidence phù hợp |
| --- | --- |
| Version nào được resolve? | Dependency graph/lockfile cho runtime configurations. |
| Thành phần nào yêu cầu version khác? | Dependency edge, framework BOM/constraints. |
| Vendor có supported fix khác? | Advisory và supported release line. |
| API/ABI thực tế có tương thích? | Contract/integration tests, startup logs, runtime checks. |
| Có thể coexist old/new không? | Compatibility matrix và canary outcomes. |
| Nếu không thể nâng ngay? | Compensating controls, residual risk, approved exception. |

## 10. Java/Maven/Gradle: direct, transitive và plugin dependencies

Trong Java application, A có thể kéo B→C, trong đó C chứa một vulnerability. Ép C lên một version khác có thể sửa vulnerability nhưng phá A, hoặc nằm ngoài vùng versions mà framework vendor hỗ trợ.

### Graph minh họa

~~~text
invoice-api (logical application)
  +-- web-framework (approved version)
  |     +-- json-library (older resolved version)   [candidate]
  +-- invoice-client-sdk (approved version)
  |     +-- http-client (older resolved version)    [candidate]
  +-- db-driver (approved version)

Proposed patch sequence:
  verify advisory applicability
    -> review framework/BOM compatible fixed versions
    -> upgrade/align dependency versions
    -> rebuild artifact and image
    -> inspect resolved dependency and packaged bytes
    -> run regression/security tests
    -> deploy canary and inspect runtime digest
~~~

Các tên/version ở đây là placeholder, không đại diện lỗ hổng thực tế.

### Maven BOM và dependencyManagement

BOM giúp quản lý version alignment; song phải kiểm tra **resolved dependency tree** và artifact đóng gói thật. Version do dependencyManagement chọn không tự nói version nào nằm trong một shaded/fat JAR đã build.

~~~xml
<!-- Illustrative dependency management; replace with approved coordinates. -->
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>org.example</groupId>
      <artifactId>approved-platform-bom</artifactId>
      <version>APPROVED_TESTED_VERSION</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>
~~~

### Gradle và build-time dependencies

Version catalogs, platforms, constraints và dependency locking có thể giúp tránh drift; phải xem từng configuration liên quan như runtimeClasspath, testRuntimeClasspath, annotation processors và build plugins. Bản vá build tool/plugin có thể cần thay **CI runner JDK, plugin API hoặc artifact provenance**, dù runtime dependency graph của ứng dụng không đổi.

### Những “fix” làm dashboard xanh giả

- Suppress scanner finding vô thời hạn, không owner/expiry/evidence.
- Exclude vulnerable package khỏi scan report mà vẫn chứa nó trong image.
- Ép dependency version chỉ để resolver thành công, bỏ qua test ABI.
- Nâng version trong source nhưng quên rebuild/deploy.
- Đóng ticket lúc PR merged, chưa verify deployed digest và runtime behavior.

## 11. OS/kernel/firmware: prerequisite và kích hoạt bản vá

OS/firmware updates có thể phụ thuộc:

- Package manager/servicing capability phù hợp.
- Kernel ABI, driver và module compatibility.
- Reboot mới kích hoạt kernel/driver/microcode mới.
- Secure Boot, TPM, signing chain và hardware model.
- Vendor update path qua firmware/BIOS release trung gian.
- HA pair, cluster quorum, storage/network driver, DR kế hoạch phục hồi.

| Giai đoạn | Evidence | Điều chưa được chứng minh |
| --- | --- | --- |
| Downloaded | Patch trong cache/repository. | Chưa cài. |
| Install transaction success | Package/update transaction thành công. | Chưa chắc process/kernel đã thay. |
| Reboot scheduled | Change có maintenance plan. | Kernel cũ còn chạy. |
| Reboot completed | Host boot event/uptime. | Cần đọc effective kernel/driver version. |
| Effective fixed state | Version/build và vendor applicability trên runtime. | Cần regression/control health checks. |

**Firmware không phải cập nhật đại trà vô điều kiện.** Sai model hoặc thiếu recovery có thể làm thiết bị không khởi động; cần vendor-supported procedure, maintenance window, power/capacity controls và verified recovery plan.

## 12. Kubernetes patch dependencies: cluster và workloads

Nâng Kubernetes có thể phụ thuộc **version compatibility giữa control plane, kubelets, API clients, admission webhooks, CNI/CSI, controllers, runtime và application workloads**. Không có thứ tự nâng phổ quát cho mọi provider/release; dùng version-skew/support matrix của môi trường cụ thể.

| Layer | Cần xác minh |
| --- | --- |
| Control plane | Supported source/target versions và managed-service prerequisites. |
| Node OS/runtime | Kernel, container runtime, CNI/CSI và node pool compatibility. |
| API/admission | Removed/deprecated APIs, webhook/client compatibility. |
| Operators/add-ons | Supported Kubernetes versions và upgrade procedures. |
| Workload | PodDisruptionBudget, readiness, liveness, termination và replica count. |
| Image | Digest, base image fix, signature/provenance và registry. |
| Storage/network | PersistentVolume, ingress, DNS và network policies sau nâng. |
| Observability | Log/metrics/audit agents còn hoạt động, không tạo evidence gap. |

~~~mermaid
flowchart TD
    A["Vendor-supported upgrade path"] --> B["Version-skew and API deprecation review"]
    B --> C["Test cluster + operators and add-ons"]
    C --> D["Check headroom, PDB, backup and monitoring"]
    D --> E["Controlled control-plane change per platform"]
    E --> F["Node pool canary with drain / reboot"]
    F --> G["Progressive workload rollout"]
    G --> H["Network, storage and security regression"]
    H --> I["Runtime version verification and evidence"]
~~~

Kubernetes **control plane patch** và **application container patch** là những changes khác nhau; thành công của một bên không bảo đảm bên kia đã sửa CVEs. Node drain còn cần xét capacity và workloads không thể gián đoạn, kể cả data stateful.

## 13. Database, API và event contract dependencies

Một patch có thể đổi schema hoặc contract theo cách old/new versions phải coexist trong rolling deploy. Nếu schema migration phá old worker trước khi worker được nâng, application có thể mất availability hoặc integrity.

### Expand–migrate–contract

1. **Expand:** thêm schema/format mới vẫn tương thích old readers/writers.
2. **Migrate:** chuyển data và clients từng bước; dual writes nếu được thiết kế rõ về nguồn sự thật.
3. **Verify:** reconciliations, contract tests, constraint checks và downstream.
4. **Contract:** loại field/format cũ khi hết old consumers và đã có rollback strategy.

~~~mermaid
flowchart LR
    A["Old schema + old clients"] --> B["Compatible schema expansion"]
    B --> C["Roll new API and worker versions"]
    C --> D["Backfill/migrate with data reconciliation"]
    D --> E["Verify no old consumers or messages"]
    E --> F["Contract obsolete schema"]
    E --> G["Recovery and roll-forward checkpoint"]
~~~

### Threat/failure cases

- New writer ghi format old reader không hiểu.
- Old worker xử lý event mới và bỏ security-relevant field.
- Authorization mới dựa tenant column chưa backfill đúng.
- Schema lock làm ngưng truy vấn quan trọng.
- Migration dở dang tạo inconsistent business records.
- Retry/replay gây duplicate side effects.
- Binary rollback sau destructive DB migration không còn khả thi.

**Rollback ứng dụng không đồng nghĩa rollback dữ liệu.** Khi destructive migrations đã chạy, có thể chỉ an toàn bằng **roll forward**, khôi phục từ verified backup hoặc thiết kế compatibility shim đã kiểm thử.

## 14. Security control dependencies khi cập nhật chính sách và thư viện

Một security patch thường thay **hành vi bảo vệ mặc định** chứ không chỉ sửa memory bug. Ví dụ:

- Framework chuyển từ allowlist một nhóm routes sang deny-by-default.
- TLS library loại protocol/cipher yếu khiến legacy partner không kết nối được.
- Token validator yêu cầu issuer/audience hoặc stricter key verification.
- ORM áp dụng escaping/validation nghiêm hơn, ảnh hưởng payload cũ.
- Access-control policy thêm device posture hoặc claim mới.
- Secret manager thay cách phát credentials; workloads chưa hỗ trợ rotation.

### Câu hỏi reviewer cần đặt

1. Control bảo vệ tài sản nào và security requirement ban đầu ra sao?
2. Patch đổi semantics của allow/deny, authentication, serialization hay error handling?
3. Có client/service nào còn phụ thuộc hành vi cũ không?
4. Nếu một dependency chưa nâng, hệ thống sẽ **deny, degrade, retry hay fail open**?
5. Có người dùng hợp lệ bị chặn (false deny), phát sinh workaround hoặc credential sharing?
6. Logs, alerts và evidence có theo được behavior mới không?
7. Đường fallback có vô tình đưa vào một bypass?

### Ví dụ

Một phiên bản JWT validator mới từ chối token sai audience đúng yêu cầu, nhưng export worker trước đây truyền token cấp cho API A sang API B. Thay vì tắt audience validation, cần sửa **token acquisition/binding flow** để mỗi resource server nhận token đúng purpose. Đây là dependency bảo mật giữa patch và identity architecture.

## 15. External vendor và managed-service compatibility

SaaS phụ thuộc IdP, payment API, email vendor, analytics SDK, managed database, cloud KMS và logging service. Một patch ở phía tổ chức hoặc phía provider có thể thay contract.

### Các dependencies cần lưu

| External dependency | Rủi ro | Cách kiểm chứng |
| --- | --- | --- |
| **Partner API** | Protocol/field/signature thay hoặc client SDK không còn hỗ trợ. | Contract tests, compatibility/certification của partner. |
| **IdP/federation** | Signing key/claim/metadata đổi, auth thất bại. | Controlled OIDC/SAML tests, key rotation overlap. |
| **Managed DB** | Engine patch thay SQL/driver, failover hoặc compatibility. | Vendor maintenance notice, query/replication tests. |
| **KMS/HSM** | TLS/key API/protocol/client restrictions mới. | Encrypt/decrypt/sign tests, key recovery validation. |
| **Service mesh/ingress** | Proxy policy/hop headers khác, route/authz mismatch. | Direct-path/negative authz tests, traffic shift. |
| **Monitoring agent** | Agent không hỗ trợ kernel/runtime mới. | Audit/metrics canary và source-health checks. |
| **License/vendor support** | Fixed version nằm ngoài contract/support lifecycle. | Support matrix, terms và remediation strategy. |

### Phân biệt phần tổ chức và provider sở hữu

Một managed service được provider vá infrastructure có thể không giải quyết lỗ hổng **customer-side client library, configuration, IAM hoặc database schema**. Ghi rõ owner và shared-responsibility boundary, không đóng risk khi chỉ nhận thông báo “maintenance complete” mà thiếu evidence đối với phần mình kiểm soát.

## 16. Asset inventory và software composition là điều kiện đầu tiên

Muốn đánh giá phụ thuộc, phải biết chính xác **affected population**, không chỉ các VMs scanner nhìn thấy.

### Các phép liên kết quan trọng

**Business service → deployed asset → runtime/image digest → software packages/SBOM → advisory/fixed version → required rollout actions → owner.**

| Asset class | Discovery/provenance | Patch dependency cần xét |
| --- | --- | --- |
| VM/server | Cloud/EDR IDs, OS build, installed/running packages. | OS/kernel/driver/reboot, application agent. |
| Container | Deployment, pod UID, immutable image digest, SBOM. | Base image, app libraries, registry/rollout, node runtime. |
| Serverless | Function version, runtime, layer/dependency artifacts. | Provider runtime upgrades, layers, redeploy và invocation behavior. |
| Managed DB | Engine version, config, replicas, clients. | Supported upgrade path, driver compatibility, failover/schema. |
| API/app | Route, service version, connected clients. | AuthN/AuthZ, contract, gateway and upstream/downstream. |
| CI/CD artifact | Repository/commit, dependency graph, digest, signing provenance. | Toolchain/plugin updates, build runner và deploy gate. |
| Endpoint/OT | Firmware/driver/model, patchability, business owner. | Vendor prerequisites, maintenance/safety/availability. |

### Một lỗi dễ tạo kết luận sai

Container image tag đã trỏ sang digest mới, nhưng Kubernetes pods vẫn chạy digest cũ. Kết luận “fixed” dựa vào **registry tag** mà không đọc **actual pod imageID/digest** là không đủ. Tương tự, patch được cài trên disk nhưng process chưa restart có thể còn loaded vulnerable code.

## 17. Vulnerability intelligence và dependency applicability

Patch plan cần ghép đúng lỗ hổng với **tài sản cụ thể**, không áp blind upgrade cho tất cả.

| Dữ liệu | Vai trò | Cảnh báo |
| --- | --- | --- |
| **CVE/vendor advisory** | Định danh vấn đề và affected/fixed versions. | Không phải bằng chứng asset của mình bị ảnh hưởng. |
| **CVSS** | Mô tả severity characteristics theo rubric/version. | Không tự mô tả toàn bộ risk từng asset. |
| **CISA KEV** | Signal về known exploited vulnerability theo tiêu chí danh mục. | Không chứng minh asset bị khai thác hay patch order tương thích. |
| **EPSS** | Ước lượng khả năng khai thác theo mô hình/thời điểm. | Không là xác suất breach riêng tổ chức. |
| **VEX/advisory applicability** | Cung cấp thông tin sản phẩm có bị ảnh hưởng hay không. | Cần kiểm chứng tính đúng phạm vi, nguồn và trạng thái. |
| **SBOM/package inventory** | Xác định component/package, artifact. | Dependency tồn tại trong source chưa chắc deployed/reachable. |
| **Runtime/reachability** | Tìm asset, endpoint, privileges và attacker path. | Không phủ định risk chỉ vì một lần test chưa chạm code path. |

### Không dùng CVSS làm danh sách thứ tự duy nhất

Một security fix cho public Internet API đang bị khai thác có thể đáng ưu tiên hơn patch dependency ít exposure, nhưng **nếu đường patch đầu tiên bắt buộc nâng DB và có nguy cơ hỏng dữ liệu**, kế hoạch phải tách containment ngắn hạn khỏi remediation lâu dài. **Risk priority** và **implementation order** là hai biến khác nhau.

### Bản vá đúng vulnerability nhưng sai component

Nếu advisory nói runtime vulnerability ở TLS library, nâng một Java HTTP client không khắc phục base image TLS native provider. Phải xác định **affected package/engine/component, deployment path và active process**, không chỉ từ khoá “TLS”.

## 18. Lập đồ thị phụ thuộc từ nhiều nguồn và xác minh tính đúng

Nguồn dữ liệu có thể gồm:

- Vendor advisories, release notes, supported upgrade paths và prerequisites.
- Maven/Gradle resolved graph, SBOM và dependency lock state.
- OS package manager metadata, kernel/module inventory, firmware compatibility matrix.
- Kubernetes/control-plane/node/rollout history.
- IaC, deployment pipeline, registry digest và release manifests.
- API/event/data contract tests, schema migration records.
- Service catalog/dependency tracing, runtime telemetry và owner walkthrough.
- Change tickets, backup/DR tests, incident and rollback history.

### Không coi các nguồn tương đương

**Vendor advisory** có thể nói product version nào fixed; **runtime inventory** nói asset nào đang chạy version gì; **integration test** nói chức năng tương thích hay không; **production monitoring** nói sự thay đổi trong scope vận hành thế nào. Chúng chứng minh các phần khác nhau trong assurance argument.

### Cần version hóa graph

Graph cần **as-of timestamp, environment, release, source provenance, confidence và các edges unresolved**. Một graph xây từ source files của release R1 không tự chứng minh R2 production còn giống.

## 19. Critical path, blockers và song song hóa

Kế hoạch patch có thể có nhiều việc song song nhưng một vài prerequisite quyết định sớm nhất khi nào fix thật sự có hiệu lực.

### Ví dụ công việc giả định

| Task | Dependency | Duration dự kiến cho lập kế hoạch | Điều kiện hoàn tất |
| --- | --- | --- | --- |
| P1: Select supported fixed version | Advisory và inventory | 1 đơn vị thời gian | Version applicability reviewed. |
| P2: Build artifact/SBOM | P1 | 2 | Reproducible/approved artifact. |
| P3: Expand DB schema | Design review | 3 | Backward compatibility tests. |
| P4: Integration/security tests | P2, P3 | 2 | Critical cases PASS. |
| P5: Canary | P4 | 1 | Security/health metrics PASS. |
| P6: Progressive rollout | P5, capacity ready | 2 | Target pods/assets upgraded. |
| P7: Runtime verification | P6 | 1 | Fixed state, no critical regressions. |

**Critical path** là đường công việc có tổng thời gian quyết định mốc hoàn tất trong các assumptions của graph. Dữ liệu duration trên chỉ để giải thích logic; không dùng làm dự đoán lịch thực tế. Chỉ kết luận patch completed khi **P7 evidence** đạt, không khi P1 đã xong.

### Những blocker không nhất thiết là code

Thiếu owner, maintenance window, vendor approval, quyền CI/KMS, rollback capability, stable backup, data migration plan hoặc capacity cũng có thể là dependency. Quản trị blocker theo risk tier; không để ticket chờ vô thời hạn mà không có interim treatment.

## 20. Dependency cycles và cách tháo gỡ

Một chu trình có thể xuất hiện:

- API v2 yêu cầu worker v2 để xử lý format mới.
- Worker v2 chỉ chạy khi schema v2 đã có.
- Schema v2 được phép contract sau khi mọi API v1 đã rời hệ thống.
- Nhưng API v1 còn tồn tại cho tenant cũ.

Nếu nâng đồng loạt không có compatibility window, downtime và data corruption có thể lớn.

### Các chiến lược

1. **Expand–contract** cho schema và event.
2. **Bridge/adapter** hiểu được old/new protocols.
3. **Versioned endpoint/event** có lifecycle được phê duyệt.
4. **Feature flags** để kiểm soát behavior, nhưng không được tạo security bypass vĩnh viễn.
5. **Parallel deployments** với traffic segmentation nếu data consistency cho phép.
6. **Separate migration phase** trước khi xóa old behavior.
7. **Risk reduction interim controls** (hạn exposure, IAM, WAF virtual patch theo scope) trong giai đoạn chờ.

### Tiêu chí kết thúc cycle

Không đủ “mọi services đã bật v2”. Cần chứng minh **old clients không còn được dùng, events tồn đọng đã được xử lý, schema/data reconciled và controls vẫn đúng**. Một feature flag bị tắt không làm vulnerability biến mất nếu endpoint cũ vẫn reachable.

## 21. Rollout strategies và rủi ro phụ thuộc dùng chung

Các cách rollout:

| Chiến lược | Ưu điểm | Rủi ro / dependency |
| --- | --- | --- |
| **All-at-once** | Thời gian mixed-version ngắn. | Blast radius cao, khó rollback nếu DB state thay. |
| **Rolling** | Duy trì availability nếu tương thích. | Old/new coexist, schema/contract consistency. |
| **Canary** | Có thể phát hiện lỗi trên phần nhỏ traffic. | Canary có đại diện critical paths/tenant tiers? |
| **Blue/green** | Chuyển traffic giữa hai môi trường. | Shared DB và side effects có thể không rollback được. |
| **Ring deployment** | Thử theo nhóm có profile rủi ro khác nhau. | Ring ordering, không bỏ nhóm high-impact. |
| **Immutable replacement** | Rebuild image/instance thay vì sửa runtime in-place. | Drift, session/job lifecycle, persistent storage. |
| **In-place patch** | Phù hợp một số hệ thống/thiết bị. | Reboot, rollback snapshots, configuration drift. |

### Shared dependency nguy hiểm

Hai services có thể deploy độc lập nhưng cùng dùng **database, queue schema, Redis cache key, identity provider hoặc KMS**. Đổi một shared component có thể ảnh hưởng mọi rings; canary không cô lập nếu tất cả đều dùng DB schema mới. Reviewer phải xác định **common-mode failure**.

## 22. Rollback, roll-forward và kế hoạch phục hồi

**Rollback** trả một hoặc nhiều thành phần về trạng thái trước thay đổi, nhưng không luôn khả thi hoặc an toàn. **Roll-forward** dùng một thay đổi tiếp theo để sửa trạng thái hiện tại mà không đảo migration đã chạy.

### Phải ghi rõ mức độ đảo ngược

| Thành phần | Rollback điển hình | Khó khăn |
| --- | --- | --- |
| Stateless app | Deploy image digest cũ. | Token/schema/feature flags có thể khác. |
| Database schema | Reverse migration hoặc restore. | Dữ liệu mới/mất dữ liệu, replication, irreversible DDL. |
| Firmware/kernel | Vendor-supported rollback/alternate boot. | Không phải mọi thiết bị hỗ trợ. |
| Key/cert rotation | Temporary overlapping trust hoặc quay lại key theo policy. | Revoked/compromised key không được đưa lại chỉ để hết lỗi. |
| Cloud managed service | Provider-supported downgrade/restore. | Không phải lúc nào có downgrade in-place. |
| Queue/event schema | Dual consumers, versioned messages. | Backlog old/new events và replay ordering. |

### Recovery plan tối thiểu

1. **Trigger:** điều gì khiến dừng/cancel/rollback/contain?
2. **Authority:** ai quyết định, ai thực hiện, liên hệ security/data/product?
3. **Scope:** regions, nodes, tenants, services và data state bị ảnh hưởng.
4. **Safe checkpoint:** backup/snapshot/artifact/manifest, đã test restore đến đâu?
5. **Procedure:** documented actions theo vendor/architecture, không giả định script có thể undo dữ liệu.
6. **Security risk of rollback:** quay về vulnerable version tăng exposure; cần compensating controls.
7. **Post-recovery verification:** data integrity, availability, security controls, audit và effective state.
8. **Follow-up:** root cause, revised dependency graph, exception/risk, next patch path.

**Rollback có thể phục hồi availability nhưng đưa vulnerability quay lại.** Báo cáo phải phân biệt *service recovered* với *security requirement satisfied*.

## 23. Risk-based prioritization vs change sequencing

Khi có nhiều vulnerabilities, cần hai trục quyết định độc lập:

1. **Risk priority:** lỗ hổng nào gây nguy cơ lớn nhất nếu tiếp tục phơi lộ?
2. **Execution dependency order:** thứ tự nào bảo đảm patch đúng và an toàn?

| Patch case | Risk priority | Sequence considerations |
| --- | --- | --- |
| Known exploited Internet-facing API component | Có thể rất cao theo scope/context. | Interim containment ngay, đồng thời mở prerequisite workstream. |
| Low-exposure library cần major framework upgrade | Tùy impact/exploitability. | Contract tests, supported version và migration. |
| Cluster OS patch phải reboot nhiều nodes | Tùy vulnerability/exposure. | Quorum/capacity, drain, maintenance, monitoring. |
| Database patch ảnh hưởng authz query | Có thể cao do multi-tenant risk. | Schema/data tests, release co-existence, rollback. |
| Patch cho deprecated legacy device | Cần đánh giá availability/safety. | Vendor support, isolation/replacement hoặc exception. |

### Không lấy độ khó làm lý do hoãn risk cao vô hạn

Nếu một critical issue có dependencies kéo dài, có thể thực hiện biện pháp giảm phơi lộ tạm như **restrict ingress/egress, segmentation, credential rotation, feature disable theo approval, additional monitoring, rate controls** hoặc vendor mitigations. Nhưng phải đo hiệu lực và residual risk; không gọi interim control là permanent patch.

## 24. Patch windows, capacity và coordinated downtime

Một change có thể đúng về code nhưng thất bại do capacity:

- Rolling reboot tất cả nodes cùng availability zone làm mất quorum.
- PodDisruptionBudget không đủ và upgrade không thể tiến.
- DB failover chưa được thử, replica lag lớn.
- Long-running exports bị terminate giữa migration.
- Worker queue backlog quá lớn sau startup.
- Cache warmup tạo spike lên database.
- Authentication/monitoring services cùng lúc bảo trì.

### Review readiness trước patch

**Service topology, redundancy, fault domains, free capacity, data replication, queue depth, peak traffic, dependency maintenance, backup restore readiness, on-call staffing và change freeze** cần đủ theo risk.

Không mặc định tắt PodDisruptionBudget hoặc tăng admin privileges để đẩy rollout qua. Nếu phải đổi guardrail, cần explicit risk/change approval và verification.

## 25. Security testing dependencies: tests cũng có prerequisites

Muốn kết luận fix có hiệu quả, tests phải chạy trên **đúng artifact, environment, data contracts, policies và runtime state**.

| Test type | Dependency cần có | Ví dụ sai sót |
| --- | --- | --- |
| Unit | Source/compiled dependency graph đúng. | Test với mocked library cũ. |
| SCA/SBOM | Build artifact/digest đã deploy. | Scan lockfile mà thiếu shaded JAR. |
| Compatibility | Old/new client/provider versions và schema. | Chỉ test v2↔v2, quên v1↔v2. |
| Integration | Realistic DB, IdP, queue, KMS, network. | Test mocks không phản ánh token policy. |
| Security negative | Threat/requirement, synthetic principals/resources. | Chỉ login/export happy path. |
| Performance/load | Realistic workloads, capacity, baseline. | Canary quá nhỏ che memory/latency regression. |
| Resilience | Authorized failure injection và recovery path. | Không test restart/reboot hoặc collector outage. |
| Production readback | Asset version, digest, policy, health. | Dựa CI green dù runtime cũ. |

### Regression strategy

Patch đôi khi thay chính control cần bảo vệ. Ví dụ fix authentication parser cần tests **wrong issuer/audience, replay, stale token, recovery path**; không chỉ test “valid user login succeeds”. Với DB patch, cần kiểm tra **transaction integrity, tenant-scoped access và rollback/restore**.

## 26. Patch lifecycle: planned, installed, activated, verified

Một patch record nên tách các trạng thái để tránh kết luận sai:

| State | Ý nghĩa | Evidence | Được gọi “fixed” chưa? |
| --- | --- | --- | --- |
| **Detected/affected** | Asset/component nằm trong tập có khả năng bị ảnh hưởng. | Inventory, advisory mapping. | Chưa. |
| **Candidate selected** | Đã chọn một fixed version/mitigation. | Advisory, compatibility review. | Chưa. |
| **Prerequisites pending** | Cần sửa dependencies/migration/backup. | Dependency register, blockers. | Chưa. |
| **Approved/planned** | Change risk và rollout plan được duyệt. | Approval/maintenance record. | Chưa. |
| **Built/downloaded** | Artifact hoặc installer sẵn sàng. | Build digest/package manifest. | Chưa. |
| **Installed/deployed** | Patch applied vào một phần/đầy đủ assets. | Deployment/install records. | Chưa chắc. |
| **Activated** | Runtime/process/kernel thực dùng fixed code. | Runtime readback, reboot/restart, digest. | Chưa đủ nếu test chưa đạt. |
| **Verified** | Security fix và compatibility/health gates đạt trên scope. | Negative tests, scan applicability, monitoring. | Có thể kết luận có giới hạn. |
| **Partial/failed** | Có asset cũ, regression hoặc prerequisite chưa đạt. | Observed failures và inventory gaps. | Không. |
| **Exception/accepted risk** | Chưa đạt; risk owner chấp nhận tạm theo chính sách. | Risk record, expiry, interim controls. | Không. |

### Đừng tự chuyển trạng thái

Một agent báo “installed” không chứng minh **kernel mới đã boot**. CI pipeline phát hành image mới không chứng minh Kubernetes Deployment đã rollout. Scanner không còn thấy CVE sau khi asset biến mất cũng không chứng minh lỗ hổng đã được vá.

### Cửa sổ đánh giá

Nêu environment, release, account/cluster, asset population, timestamp và **effective version**. Một version đã được vá ở canary không tự áp dụng cho mọi replicas/regions.

## 27. Chuỗi evidence từ advisory tới runtime

Vulnerability closure cần có sự nối kết đủ mạnh giữa:

1. **Advisory:** phần mềm/versions nào bị ảnh hưởng, fixed state là gì?
2. **Asset:** service, tenant tier, deployment và principal nào có thể bị tác động?
3. **Package graph:** dependent libraries/runtime/plugins, constraints và conflicts.
4. **Change plan:** prerequisites, approvals, risk acceptance và rollback.
5. **Source/build:** dependency resolution, commit, SBOM, artifact digest.
6. **Deployment:** release manifest, image digest/package version và rollout history.
7. **Runtime:** actual loaded version/OS kernel/build, restart/reboot, policy/config.
8. **Tests:** vulnerability/negative tests, integration/contracts, resilience, data reconciliation.
9. **Observation:** production canary metrics, error rates, authz/audit health.
10. **Decision:** PASS/FAIL/PARTIAL/UNKNOWN, finding/exception và retest conditions.

### Claim–Argument–Evidence

**Claim:** “Trong production release R, các workloads Invoice API thuộc population P đã nâng thành phần xử lý HTTP lên một fixed version phù hợp advisory A, các prerequisites đáp ứng, runtime dùng artifact đã xác minh và những security/compatibility tests trọng yếu đạt.”

**Argument:** vendor advisory đúng asset/version; patch candidate giải quyết affected state; dependency graph không còn unresolved blockers; runtime đã nhận fix; tests chứng minh vulnerability path và business functions; observability không có critical regression trong window.

**Evidence:** advisory ref, package graph/lock state, signed build digest/SBOM, deployment readback, negative test results, canary data, source health, risk decision.

### Không phát biểu vượt quá bằng chứng

Không khẳng định “all services secure” nếu chỉ test Invoice API ở region A. Nếu worker chưa nâng, claim phải nêu **partial** và risk tới khi worker fixed. Nếu scan không thể xác minh vendor backport, có thể ghi **pending applicability confirmation** thay vì tự cho PASS hoặc tự công bố vulnerable.

## 28. Mẫu YAML patch dependency record

Mẫu này là **tài liệu học tập**, không phải patch manifest tự chạy. Version, IDs và thời gian đều giả định, phải thay bằng advisory, owners và evidence thật nếu áp dụng.

~~~yaml
schema_version: "1.0"
record_type: "patch_dependency_plan"
plan_id: "PATCH-INV-EXAMPLE-004"
module: "SECURITY_SECURITY_ASSURANCE"
service: "invoice-saas"
environment: "production"
status: "ILLUSTRATIVE_NOT_EXECUTED"
security_objective: >
  Remediate an affected HTTP processing component without
  breaking tenant authorization, export jobs or availability.
advisory:
  reference: "VENDOR-ADVISORY-PLACEHOLDER"
  affected_component: "http-processing-library"
  affected_range: "TO_BE_VALIDATED"
  fixed_version: "APPROVED_FIXED_VERSION"
  applicability: "PENDING_VERIFICATION"
assets:
  - asset_id: "invoice-api-prod"
    current_artifact_digest: "TO_BE_OBSERVED"
  - asset_id: "invoice-export-worker-prod"
    current_artifact_digest: "TO_BE_OBSERVED"
dependencies:
  - id: "D-01"
    type: "requires"
    from: "fixed-http-library"
    to: "supported-framework-bom"
    validation: "resolved-runtime-graph-review"
  - id: "D-02"
    type: "must_precede"
    from: "compatible-schema-expansion"
    to: "deploy-new-worker"
    validation: "mixed-version-contract-tests"
  - id: "D-03"
    type: "requires"
    from: "production-rollout"
    to: "tested-backup-and-recovery"
    validation: "restore-drill-reference"
  - id: "D-04"
    type: "requires"
    from: "close-vulnerability-finding"
    to: "runtime-digest-and-security-verification"
    validation: "observed-results-by-asset"
conflicts:
  - id: "C-01"
    with: "legacy-export-plugin"
    expected_resolution: "upgrade-or-isolate-and-test"
    state: "OPEN"
rollout:
  method: "canary-then-progressive"
  required_gates:
    - "resolved-graph-reviewed"
    - "SBOM-and-provenance-validated"
    - "security-negative-tests-pass"
    - "old-new-contract-tests-pass"
    - "backup-restore-tested"
    - "canary-health-and-audit-pass"
  rollback:
    application: "previous-approved-image-digest"
    database: "NO_AUTOMATIC_SCHEMA_DOWNGRADE"
    authority: "Release-and-risk-owners"
validation:
  status: "NOT_TESTED"
  evidence_refs: []
  residual_risk: "NOT_ASSESSED"
  unknowns:
    - "Vendor applicability not confirmed"
    - "Legacy plugin compatibility unresolved"
owners:
  service: "Invoice Application Team"
  platform: "Platform Operations"
  database: "Data Platform Team"
  assessor: "Security Assurance"
  risk: "Invoice Security Risk Owner"
reassessment_triggers:
  - "new-advisory"
  - "dependency-or-schema-change"
  - "rollout-failure"
  - "new-affected-asset-found"
~~~

### Ý nghĩa của record

Vì C-01 còn OPEN và tests còn NOT_TESTED, record này **chưa chứng minh patch đã an toàn hoặc rủi ro đã giảm**. Dependency edges thể hiện những điều kiện cần; phải có source và observed test result để chuyển sang verified state.

### Không lưu secret

Không đưa production credentials, private keys, bearer tokens hay dữ liệu invoice thật vào patch plan. Evidence URLs/repository refs nên được kiểm soát và log/tracing cần redaction phù hợp.

## 29. Mẫu SQL tìm target deployments chưa đạt fixed state

Ví dụ minh họa trên SQL có common table expressions. Giả định hệ thống có:

- **eligible_deployments**: population deployment đúng environment, snapshot thời điểm đánh giá.
- **deployed_components**: inventory thành phần theo exact artifact digest/package key.
- **patch_applicability**: phiên bản fixed đã được phê duyệt theo advisory và mapping đúng vendor/ecosystem.
- **patch_verifications**: kết quả test cho từng deployment/artifact và kỳ.

~~~sql
-- Illustrative normalized assessment; version comparison is
-- performed upstream by ecosystem/vendor-aware applicability.
WITH eligible AS (
    SELECT deployment_id, environment, artifact_digest
    FROM eligible_deployments
    WHERE environment = 'production'
      AND in_scope = TRUE
      AND active_at_assessment = TRUE
),
applicability AS (
    SELECT
        c.deployment_id,
        c.artifact_digest,
        a.advisory_id,
        a.applicability_state,
        a.fixed_state
    FROM deployed_components c
    JOIN patch_applicability a
      ON a.component_identity = c.component_identity
     AND a.component_version = c.component_version
    WHERE a.advisory_id = :advisory_id
),
evaluated AS (
    SELECT
        e.deployment_id,
        e.artifact_digest,
        a.applicability_state,
        a.fixed_state,
        v.verification_status,
        v.tested_artifact_digest
    FROM eligible e
    LEFT JOIN applicability a
      ON a.deployment_id = e.deployment_id
     AND a.artifact_digest = e.artifact_digest
    LEFT JOIN patch_verifications v
      ON v.deployment_id = e.deployment_id
     AND v.advisory_id = :advisory_id
)
SELECT
    deployment_id,
    artifact_digest,
    applicability_state,
    fixed_state,
    verification_status,
    CASE
      WHEN applicability_state IS NULL
        THEN 'UNKNOWN_APPLICABILITY'
      WHEN applicability_state = 'NOT_AFFECTED'
        THEN 'NOT_AFFECTED_REVIEW'
      WHEN fixed_state = 'FIXED'
       AND verification_status = 'PASS'
       AND tested_artifact_digest = artifact_digest
        THEN 'VERIFIED_FIXED'
      ELSE 'NEEDS_ACTION_OR_EVIDENCE'
    END AS assessment_outcome
FROM evaluated;
~~~

### Điều kiện quan trọng trước khi dùng query

1. **Version ordering** phải được quyết định theo package ecosystem/vendor, không dùng so sánh chuỗi SQL như '2.10' và '2.9'.
2. Join tables cần unique constraints hoặc deduplication để không nhân số deployments.
3. LEFT JOIN không thấy component có thể là **inventory gap**, không mặc định NOT_AFFECTED.
4. Scanning findings nên có trạng thái false positive/backport review riêng, gắn evidence.
5. Tests phải gắn đúng **artifact_digest**, không chỉ deployment name.
6. “Active at assessment” cần time window và snapshots đáng tin; ephemeral workloads cũng có historical exposure.
7. Trạng thái FIXED trong table phải đến từ advisory applicability, còn verification PASS là **bằng chứng độc lập bổ sung**.
8. Một deployment có nhiều affected components cần đánh giá theo từng advisory/component, không gộp ngẫu nhiên.

## 30. Measurement: những chỉ số phải đi cùng mẫu số

Một patch dashboard “98% compliant” có thể bỏ sót assets chưa được discover hoặc chỉ đo patches installed chứ không đo runtime activated.

| Metric ID | Định nghĩa và đơn vị | Caveat |
| --- | --- | --- |
| **PD-01** | **Affected-asset discovery coverage** = affected assets đã đối chiếu / independently known eligible assets. | Unknown assets không tự nằm ngoài scope. |
| **PD-02** | **Dependency mapping coverage** = material patches có prerequisite/conflict graph được review / material patches cần review. | Graph tồn tại không có nghĩa đúng. |
| **PD-03** | **Unresolved prerequisite count** theo criticality, owner và tuổi. | Không cộng mọi blocker ngang trọng số. |
| **PD-04** | **Dependency conflict resolution latency** từ phát hiện tới decision/tested solution. | Ticket resolved có thể chưa deploy. |
| **PD-05** | **Verified fixed runtime coverage** = eligible affected deployments với fixed active artifact và tests đạt / eligible affected deployments. | Phải tách evidence unknown. |
| **PD-06** | **Patch activation gap** = installed assets chưa reboot/restart/activated / installed assets cần activation. | Một số fixes không cần reboot. |
| **PD-07** | **Rollback readiness** = planned changes có recovery procedure tested phù hợp / changes cần recovery gate. | Backup exists khác restore works. |
| **PD-08** | **Mixed-version contract test coverage** = required old/new combinations đã test / combinations được xác định trong support plan. | Suite không đại diện mọi clients. |
| **PD-09** | **Risk-weighted exposure time** = phân phối thời gian asset vulnerable trong affected window, có criticality segmentation. | Không thay bằng average đơn giản. |
| **PD-10** | **Patch regression escape** = confirmed critical regressions sau patch trong kỳ, theo population/volume. | Số ít có thể do monitoring thiếu. |
| **PD-11** | **Patch deployment lead time** từ approved candidate tới verified fixed state; p50/p95 và blocked cases. | Nhanh không đồng nghĩa an toàn. |
| **PD-12** | **Patch dependency evidence freshness** = plans có version/asset/runtime evidence còn hợp lệ / in-scope plans. | Snapshot R1 không chứng minh R2. |
| **PD-13** | **Overdue temporary mitigations** = exceptions/virtual patches quá hạn, theo impact. | Compensating control không phải actual patch. |
| **PD-14** | **Runtime artifact alignment** = instances dùng approved digest/build / production instance population. | Hệ thống ephemeral cần event history. |
| **PD-15** | **Reboot/restart effectiveness** = required activations có effective runtime readback / planned required activations. | Reboot log chỉ là một nguồn. |
| **PD-16** | **Dependency-induced patch failures** = rollout failures được xác minh do prerequisite/conflict, theo release/change population. | Có thể false attribution; cần root-cause review. |
| **PD-17** | **Finding closure verification** = findings retest đạt đúng asset/digest / findings đến hạn đóng. | Không dùng scanner disappearance làm PASS. |
| **PD-18** | **Telemetry/source health** = required sources đạt freshness/completeness / sources thuộc evidence inventory. | Heartbeat không chứng minh mọi events. |

### Một kết luận có giới hạn

“Trong 100 eligible production deployments thuộc inventory đối chiếu, 94 có fixed artifact đã active và đủ tests; 3 chưa rollout, 2 thiếu runtime evidence, 1 có conflict chưa giải quyết.” Không được viết “94% risk đã loại bỏ” vì impact và severity có thể khác nhau.

### Critical gates

Những critical/public-facing assets hoặc vulnerabilities đang bị khai thác có thể có **mandatory risk gates**; một tỷ lệ trung bình tốt không bù một critical asset còn exposed. Ngưỡng, SLA và exception authority phải từ approved risk policy, không tự đặt số toàn cục.

## 31. Bộ kiểm thử patch dependency: positive, negative và failure-mode

Các tests nên dùng **synthetic tenants/test workloads, staging và controlled canary**; không gây outage hoặc truy cập trái phép dữ liệu thật.

| Test ID | Scenario | Expected evidence/outcome |
| --- | --- | --- |
| **PD-T01** | Patch candidate thiếu hard prerequisite. | Gate phát hiện và chặn rollout/cài sai. |
| **PD-T02** | Superseded update được chọn nhầm. | Vendor metadata xác minh correct patch chain. |
| **PD-T03** | Conflict giữa framework patch và old plugin. | Compatibility test FAIL, có treatment trước deploy. |
| **PD-T04** | Transitive dependency cũ trong resolved graph. | Scan/lock validation báo affected component. |
| **PD-T05** | Source dependency fixed nhưng fat JAR chứa old version. | Artifact inspection phát hiện, không đóng ticket. |
| **PD-T06** | Registry tag mới nhưng pod chạy old digest. | Runtime verification FAIL/PARTIAL. |
| **PD-T07** | OS patch installed nhưng chưa reboot. | Activation metric không PASS. |
| **PD-T08** | Reboot nhưng loaded kernel/driver không đổi. | Effective version readback phát hiện. |
| **PD-T09** | Firmware patch không khớp model/prerequisite. | Vendor compatibility gate chặn. |
| **PD-T10** | Control plane nâng nhưng add-on cũ không hỗ trợ. | Preflight compatibility review/test fail. |
| **PD-T11** | Node pool drain với thiếu capacity/PDB. | Rollout tạm dừng an toàn, không phá quorum. |
| **PD-T12** | New app đọc old DB schema. | Defined compatible behavior hoặc gate fail. |
| **PD-T13** | Old worker xử lý new event schema. | Contract test xác minh backward compatibility. |
| **PD-T14** | DB migration thất bại giữa chừng. | Retry/rollback/roll-forward strategy và data integrity. |
| **PD-T15** | Binary rollback sau contract schema. | Plan nhận biết không tương thích, không tự chạy unsafe down migration. |
| **PD-T16** | Patch đổi JWT audience validation. | Wrong-audience negative tests PASS, valid flow sửa đúng. |
| **PD-T17** | TLS patch ngừng hỗ trợ cipher yếu của partner. | Controlled partner test và approved transition, không tắt validation. |
| **PD-T18** | KMS/signing key rotation giữa rollout. | New/old trust đúng window, no unauthorized fallback. |
| **PD-T19** | IdP/DB/vendor dependency timeout trong canary. | Failure behavior và rollback/containment theo policy. |
| **PD-T20** | Canary không có critical export traffic. | Evidence gap được phát hiện, không kết luận đủ scope. |
| **PD-T21** | Một availability zone upgrade đồng thời. | Capacity/anti-affinity/quorum guardrails ngăn outage. |
| **PD-T22** | Một CI runner tạo artifact không có SBOM/provenance. | Deploy gate chặn theo baseline. |
| **PD-T23** | Vulnerability scanner false positive do vendor backport. | Applicability review với advisory evidence, không tự dismiss. |
| **PD-T24** | Một asset mới được phát hiện sau close ticket. | Reopen/reassess population và residual risk. |
| **PD-T25** | Collector/audit source im lặng trong rollout. | UNKNOWN/PAUSE theo policy, không tự xanh dashboard. |
| **PD-T26** | New container image có behavior security regression. | Negative tests phát hiện bypass, rollback/containment. |
| **PD-T27** | Patch rollback đưa lại old vulnerable binary. | Risk exception/containment và new patch plan, không ghi fixed. |
| **PD-T28** | Long-running export job bị terminate giữa upgrade. | Idempotency/restart/reconciliation đúng contract. |
| **PD-T29** | Signed export URL sau role revoke vẫn hoạt động. | Kết quả phù hợp policy, nêu gap/threat nếu ngoài cửa sổ. |
| **PD-T30** | Patch trên 99 pods, còn 1 old pod. | Coverage chính xác 99/100, không tự PASS all. |
| **PD-T31** | Production deploy fixed image nhưng wrong release manifest. | Provenance/approved digest gate phát hiện. |
| **PD-T32** | Backup tồn tại nhưng restore với key cũ thất bại. | Recovery prerequisite FAIL, chưa cho destructive change. |

### Test artifact đầy đủ

Mỗi test record gồm **requirement/threat ID, patch plan/dependency edge, asset, old/target versions, preconditions, expected, observed, evidence source/time, status (PASS/FAIL/INCONCLUSIVE), owner và retest**. Test run trên synthetic environment không tự chứng minh production readiness trừ khi **scope equivalence** được đánh giá.

## 32. Case study: vá một thư viện trên Invoice SaaS có nhiều phụ thuộc

### 32.1. Bối cảnh giả định

Invoice SaaS phục vụ nhiều khách hàng doanh nghiệp, có:

- **Invoice API:** Java/Spring xử lý authentication, business authorization, tạo export jobs.
- **Export worker:** Java service nhận queue messages, đọc tenant-scoped data và tạo CSV/PDF.
- **Shared database:** PostgreSQL với schema phục vụ APIs và workers.
- **Event consumers:** analytics và notification services.
- **Kubernetes:** deployments trải trên nhiều node pools và hai vùng lỗi.
- **CI/CD:** artifact build, SBOM, registry, deployment manifests.
- **Cloud platform:** KMS, object storage, managed ingress và IdP.

Một vendor advisory giả định thông báo vulnerability trong HTTP serialization component. Team xác định Invoice API và Export worker có thể dùng thành phần bị ảnh hưởng theo các version khác nhau.

**Business requirement:** khắc phục exposure trong thời hạn đã duyệt, không làm cross-tenant authorization sai và không mất các export jobs đang chạy.

### 32.2. Graph phụ thuộc sau inventory

~~~mermaid
flowchart TD
    V["Advisory A: affected component"] --> API["Invoice API dependency graph"]
    V --> WORK["Export worker dependency graph"]
    API --> BOM["Framework BOM / JDK compatibility"]
    WORK --> SDK["Legacy export SDK conflict"]
    BOM --> IMG["Updated base image and build"]
    SDK --> ADAPT["Adapt SDK or select supported patch path"]
    IMG --> CT["Mixed-version API + event contract tests"]
    ADAPT --> CT
    DB["Compatible database schema"] --> CT
    CT --> CAN["Canary rollout"]
    REC["Backup restore + rollback/roll-forward plan"] --> CAN
    CAN --> PROD["Production rings / node capacity"]
    PROD --> VERIFY["Runtime digest + authz + export verification"]
    VERIFY --> CLOSE["Time-scoped security assurance conclusion"]
~~~

### 32.3. Phát hiện ban đầu

| Finding ID | Quan sát | Rủi ro |
| --- | --- | --- |
| **F-PD-01** | API fixed dependency được khai trong source nhưng image chưa rebuild. | “Patched” trên repository nhưng runtime vulnerable. |
| **F-PD-02** | Worker SDK cũ không tương thích candidate fixed version. | Nâng cưỡng bức có thể crash hoặc deserialization errors. |
| **F-PD-03** | Client v2 thay event field tenantScope thành object mới. | Old worker bỏ qua context hoặc fail event parsing. |
| **F-PD-04** | Schema migration planned có bước xóa cột tenant_id sớm. | Old worker/queries có thể đọc sai hoặc mất dữ liệu. |
| **F-PD-05** | Cluster chỉ đủ capacity khi không có maintenance khác. | Rolling node patch có thể giảm availability dưới SLO. |
| **F-PD-06** | Base image được sửa nhưng runtime digest còn cũ trên một node pool. | Một phần affected population vẫn exposed. |
| **F-PD-07** | Backup đã tạo nhưng chưa thử restore cùng key version hiện hành. | Không đủ recovery assurance cho migration. |
| **F-PD-08** | Audit collector chưa xác minh với runtime mới. | Có thể mất evidence về export/authorization. |
| **F-PD-09** | Ticket đóng khi canary PASS nhưng region B chưa nâng. | Closure claim rộng hơn evidence. |
| **F-PD-10** | Old vendor SDK không còn supported fix. | Cần migration/containment/risk handling. |

### 32.4. Risk treatment phân biệt tức thời và lâu dài

**Đường khắc phục chính:** chọn supported fixed version; kiểm tra framework/JDK compatibility; sửa SDK; mở rộng schema không phá old workers; xây image; chạy mixed-version/security tests; canary; progressive rollout; runtime verification.

**Trong lúc dependency chưa được giải quyết:** risk owner có thể phê duyệt **giới hạn exposure/endpoint, rate controls, segmentation, tạm giảm quyền workload hoặc monitor/containment tăng cường** nếu phù hợp threat và vận hành. Những biện pháp này phải được thử hiệu lực và không tự được gọi là “patch installed”.

### 32.5. Kế hoạch rollout đề xuất

| Phase | Điều kiện đầu vào | Công việc | Evidence để qua gate |
| --- | --- | --- | --- |
| **Discover** | Advisory có phạm vi rõ. | Link affected component→assets/digests. | Asset/scan/SBOM mapping reviewed. |
| **Prepare** | Owners/criticality/risk được xác minh. | Resolve SDK conflict, design compatible schema. | Dependency matrix, ADR/approval. |
| **Build** | Candidate versions được duyệt. | Rebuild images, SBOM và provenance. | Immutable digest, approved graph. |
| **Preproduction** | Test environment tương đương đủ. | Positive/negative, old/new contract, data restore. | Test evidence và known gaps. |
| **Canary** | Recovery và monitoring đạt. | Deploy subset theo traffic/risk, test export. | Health, authz, audit, data integrity. |
| **Progressive** | Canary gate PASS. | Rollout theo vùng/nhóm, hạn concurrent disruption. | Deployment graph và per-ring results. |
| **Verify** | Target population rollout hoàn tất. | Read active versions/digests, assessment lại. | Runtime, security test, residual gap. |
| **Close** | No unapproved blockers. | Update findings/exception, archive evidence. | Assessor/risk authority decision. |

### 32.6. Negative tests quan trọng hơn “application starts”

**Cross-tenant scenario:** user tenant A gửi export request chứa invoice thuộc B. Sau nâng HTTP serialization component, API/worker vẫn phải **DENY và không tạo file chứa B**, kể cả khi message đi qua version adapters.

**Replay scenario:** cùng job event được gửi hai lần trong mixed-version window; worker phải xử lý idempotent/reconcile theo business contract.

**Revocation scenario:** account hoặc permission thay đổi trong khi export queued; expected behavior phải được business/security policy xác định và kiểm tra.

**Failure scenario:** KMS/IdP tạm không khả dụng hoặc audit source hỏng; không để patches tự tạo insecure fallback mà monitoring vẫn xanh.

### 32.7. Assessed outcome mẫu

Trong ví dụ này chưa có test runtime thực. Vì vậy bảng kết quả phải được giữ:

| Requirement | Evidence cần | Trạng thái |
| --- | --- | --- |
| All affected artifacts identified. | Inventory + SBOM + runtime digest. | PENDING |
| Legacy SDK conflict resolved. | Supported version + integration tests. | PENDING |
| Old/new events remain safe. | Contract & negative authorization tests. | PENDING |
| Schema migrations reversible/managed. | Data reconciliation, restore or roll-forward drill. | PENDING |
| Runtime assets fixed. | Per-region/pod exact digest/version. | PENDING |
| Security/availability unaffected. | Production-like + canary evidence. | PENDING |

**Không tự chuyển PENDING thành PASS** chỉ vì roadmap đã ghi. Nếu region B chưa nâng, phải báo partial coverage và risk exposure; nếu một critical authz test fail, phải dừng/reassess theo policy dù các metrics latency đẹp.

### 32.8. Kết luận có thể chấp nhận

> “Đối với Invoice API và Export worker thuộc scope release R, quá trình patch dependency đã được review trên framework, SDK, image, DB schema, queue contracts và Kubernetes rollout. Việc kết luận fixed phải chờ effective runtime version, contract/negative tests và deployment readback cho từng production region; các controls tạm thời và residual risks được theo dõi riêng.”

Câu này **không giả vờ công việc đã hoàn tất** và có thể biến thành assurance claim khi evidence thực có đủ.

## 33. Ví dụ Java/JUnit: contract test bảo vệ mixed-version rollout

Một patch cho thư viện serialization có thể khiến old export workers và new API không tương thích. Ví dụ sau kiểm tra rằng **message có field bổ sung không làm mất trusted tenant binding** ở một consumer được thiết kế tương thích. Nó minh họa một test liên kết **dependency constraint với security requirement**.

~~~java
// Illustrative JUnit 5 + Jackson test. It is not production code.
// An actual project must provide approved dependencies and schemas.
import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class ExportEventCompatibilityTest {
    record ExportJobV1(
        String jobId,
        String verifiedTenantId,
        String resourceId
    ) {}

    // Permissive parsing of unknown fields is allowed ONLY if the
    // contract explicitly permits it. Authentication and integrity
    // of the message must be verified outside this parsing test.
    private final ObjectMapper mapper = new ObjectMapper()
        .configure(
            DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES,
            false);

    @Test
    void oldConsumerPreservesMandatoryTrustedTenantField()
            throws Exception {
        String event = """
            {
              "jobId": "canary-job-01",
              "verifiedTenantId": "tenant-a",
              "resourceId": "invoice-a",
              "schemaVersion": 2,
              "traceRef": "example-trace"
            }
            """;

        ExportJobV1 decoded =
            mapper.readValue(event, ExportJobV1.class);

        assertEquals("tenant-a", decoded.verifiedTenantId());
        assertEquals("invoice-a", decoded.resourceId());
    }

    @Test
    void missingTenantBindingIsNotAcceptedByBusinessLayer()
            throws Exception {
        String event = """
            {
              "jobId": "canary-job-02",
              "resourceId": "invoice-a"
            }
            """;

        ExportJobV1 decoded =
            mapper.readValue(event, ExportJobV1.class);

        // This simulates a domain validator. Real consumers must
        // also verify message provenance and server-owned job state.
        assertThrows(IllegalArgumentException.class, () -> {
            if (decoded.verifiedTenantId() == null
                    || decoded.verifiedTenantId().isBlank()) {
                throw new IllegalArgumentException(
                    "Missing verified tenant binding");
            }
        });
    }
}
~~~

### Test này chứng minh gì?

- Consumer deserializes được một event có field bổ sung nếu contract cho phép.
- Validation minh họa từ chối thiếu một field trusted-tenant bắt buộc.

### Nó **chưa** chứng minh gì?

1. **verifiedTenantId thực sự trusted:** dữ liệu trong event vẫn có thể bị producer độc hại giả mạo; cần server-owned job lookup, broker ACL, signature/provenance nếu cần.
2. **Authorization đúng:** worker vẫn cần kiểm tra job ID, actor, resource và effective data permissions.
3. **All schemas compatible:** test chỉ bao phủ hai JSON strings, chưa có đầy đủ schema evolution/mixed versions.
4. **No side effects:** idempotency, DB transaction, retries và output file phải được kiểm riêng.
5. **Correct patch deployed:** test chạy trong CI không chứng minh runtime image đã fixed.

### Vì sao không chỉ test JSON parse?

Một contract mới bỏ field security-critical có thể **parse thành công nhưng làm mất căn cứ phân quyền**. Test phải nối schema compatibility với **security invariants**, không chỉ “không throw exception”.

## 34. Failure injection và kiểm tra rollback dependencies

Trước các changes high-impact, có thể diễn tập trong môi trường được phép:

- Restart/reboot một canary node, kiểm tra queue draining và pod scheduling.
- Làm fail một dependency như DB replica/IdP/KMS trong sandbox với guardrails.
- Tạm gây delay event delivery để kiểm tra dual-version consumers.
- Revoke một test credential sau patch, xác minh effective deny.
- Triển khai một canary image sai digest để test admission/deployment gate.
- Thử restore snapshot test với key/version mà production đang dựa vào.
- Simulate audit collector outage để xác minh dashboard chuyển UNKNOWN.
- Trigger controlled rollback tới approved previous image, rồi chạy security regression.

### Bốn mốc cần tách

**T0 – Change initiated:** deployment/installer bắt đầu.

**T1 – Component activated:** process/host/pod đang chạy fixed state.

**T2 – Security invariant verified:** negative/regression test cho outcome đúng.

**T3 – Operationally stable:** monitoring đạt trong observation window đã phê duyệt.

Tùy requirement, patch state có thể yêu cầu đủ T2/T3. Không dùng **T0 hoặc successful installer return** làm effective remediation time.

### Safety

Các thử nghiệm phải có owner, targets, stop condition, SLO guardrails và data protection. Không tắt hệ thống quan trọng, phá production databases hoặc làm rò dữ liệu khách hàng để “chứng minh recovery” mà không có quyền, kế hoạch và môi trường phù hợp.

## 35. Patch dependency evidence quality

Evidence không có provenance/time/version có thể dẫn đến kết luận sai. Ví dụ screenshot cho thấy một package fixed trên test node, nhưng assessor không biết node nào hoặc thời điểm.

| Quality | Câu hỏi kiểm chứng |
| --- | --- |
| **Relevance** | Evidence chứng minh đúng prerequisite, asset, version và requirement? |
| **Completeness** | Bao phủ mọi regions, replicas, node pools, tenants và affected artifacts? |
| **Accuracy** | Scanner/version mapper có xử lý backport, duplicate và ecosystem semantics? |
| **Freshness** | Evidence có thu sau deploy/reboot/last relevant change không? |
| **Integrity** | Source report có thể bị sửa trái phép, logs có trace hoặc checksum khi phù hợp? |
| **Provenance** | Ai/công cụ nào thu, policy/config/version nào, lúc nào? |
| **Repeatability** | Test method, inputs và observed outcomes có tái tạo được? |
| **Independence** | Có source nào ngoài tool/actor thực hiện patch kiểm tra trạng thái? |
| **Availability** | Telemetry/scanner/collector có healthy trong evaluation window? |
| **Limitations** | Unassessed clients, artifacts, shared dependencies hoặc exceptions có rõ? |

### Bảo vệ kho evidence

Patch evidence có thể lộ hostnames, versions, CVEs, admin routes, deployment topology, privileges và thông tin nhân sự. Cần access controls, redaction, retention, integrity và audit phù hợp; tránh lưu production secrets và customer data trong test logs.

### Claim có thể bị bác bỏ

Nếu build pipeline báo image D fixed nhưng runtime evidence ở production cho thấy image C, không thể chọn riêng CI screenshot để ghi PASS. Ghi **evidence conflict**, giải quyết nguyên nhân và kết luận PARTIAL/FAIL/UNKNOWN đúng context.

## 36. Continuous patch dependency assurance

Patch dependency graph nhanh chóng cũ khi:

- Asset mới được tạo/khai báo, node pool scale hoặc workload đổi digest.
- Security advisory mới ảnh hưởng một transitive dependency.
- Framework/JDK/base image hoặc managed service phiên bản mới.
- Database schema/event contract thay, old consumers vẫn chạy.
- Vendor yêu cầu prerequisite hoặc có advisory correction.
- Runtime config/IAM/trust/crypto policy thay.
- Key rotation/IdP/vendor API behavior thay.
- Incident, penetration test hoặc monitoring phát hiện regression.

### Continuous loop

~~~mermaid
flowchart TD
    A["Asset and vulnerability inventory"] --> B["Candidate fixes and dependency graph"]
    B --> C["Risk, prerequisite and compatibility review"]
    C --> D["Build / test / release gate"]
    D --> E["Canary / progressive rollout"]
    E --> F["Runtime verification and security tests"]
    F --> G{"Fixed and acceptable residual risk?"}
    G -- "No / unknown" --> H["Finding, rollback/containment or rework"]
    H --> C
    G -- "Yes within scope" --> I["Versioned assurance evidence"]
    I --> J["Monitor drift, assets, advisories and service changes"]
    J --> A
~~~

### Automation hữu ích

- Detect new CVE/advisory candidates and affected packages.
- Compare SBOM/runtime digest với approved fixed state.
- Validate prerequisite graph, cycles và unsupported versions.
- Gate changes khi thiếu owners, provenance, tests hoặc rollback readiness.
- Detect mixed-version conflicts/old replicas, missing reboots, stale kernels.
- Trigger reassessment khi schema/event/API dependency hoặc cloud resources thay.
- Alert nếu scanner/telemetry bị mất trong window và gắn **UNKNOWN**.

### Automation không thay mọi phán đoán

Một version graph hợp lệ không chứng minh business transaction đúng, và scanner xanh không thay data-integrity test. Assurance còn cần reviewers/owners kiểm tra **threat model, cross-tenant behavior, recovery capability và residual risk**.

## 37. RACI và trách nhiệm cho chuỗi phụ thuộc bản vá

Patch dependency thường vượt qua nhiều nhóm: vendor advisory ở Security, package graph ở Dev, image ở CI, nodes ở Platform, schema ở Data, SLA ở Product. Nếu không có owner rõ, một prerequisite bị bỏ lại có thể kéo dài exposure.

| Vai trò | Trách nhiệm |
| --- | --- |
| **Vulnerability management lead** | Xác định affected scope, ưu tiên risk, remediation/exception tracking. |
| **Application/service owner** | Code/runtime dependencies, API/event compatibility, functional/security tests. |
| **Platform/OS owner** | Node/kernel/firmware, Kubernetes, infrastructure prerequisites, reboot/capacity. |
| **DB/data owner** | Schema migration, backup/restore, data integrity, retention và transaction semantics. |
| **Identity/crypto owner** | Trust store, keys/certificates, token policy, auth dependencies. |
| **CI/CD/supply-chain owner** | Artifact provenance, SBOM, dependency locks, signed deployments. |
| **Release/change manager** | Plan/gates, scheduling, rings, rollback and production change coordination. |
| **SOC/incident response** | Exposure monitoring, detections và interim containment. |
| **Security assurance reviewer** | Challenge dependency assumptions, test evidence, effective state và conclusions. |
| **Business/risk owner** | Risk appetite, downtime/impact trade-offs, residual risk acceptance. |

### RACI minh họa

**R** là người thực hiện; **A** chịu trách nhiệm cuối cùng; **C** được tham vấn; **I** được thông báo.

| Hoạt động | Security/VM | App | Platform | Data | Assurance | Risk owner |
| --- | :---: | :---: | :---: | :---: | :---: | :---: |
| Advisory applicability và affected assets | **A/R** | C | C | C | C | I |
| Dependency graph và supported fix | C | **A/R** | R | C | C | I |
| DB schema compatibility/restore | C | C | C | **A/R** | C | I |
| Deployment/reboot readiness | C | R | **A/R** | C | C | I |
| Security and regression tests | R | **A/R** | R | R | C | I |
| Independent evidence/retest review | C | C | C | C | **A/R** | I |
| Unresolved residual risk decision | C | C | C | C | C | **A/R** |

Trong nhóm nhỏ có thể gộp vai, nhưng nên tránh để người duy nhất thực hiện patch **tự xác nhận mọi critical control hiệu lực và tự chấp nhận rủi ro còn lại**.

## 38. Exception và residual risk khi prerequisite chưa đạt

Không phải patch nào cũng cài ngay được: legacy SDK, thiết bị không còn vendor support, DB migration không thể đảo, cloud region có uptime requirement hoặc phần cứng không hỗ trợ.

### Một exception phải có

1. **Affected asset/deployment/tenant scope:** cụ thể, không chỉ “legacy systems”.
2. **Vulnerability/advisory ID:** phiên bản, applicability, risk impact.
3. **Blocked dependency:** prerequisite/conflict nào chưa xử lý, evidence trạng thái.
4. **Existing controls và limits:** có điều gì đã được chứng minh vận hành?
5. **Temporary mitigations:** segment, disable affected route, narrow privilege, monitoring, vendor workaround.
6. **Security verification:** test cho mitigation và threat path, không chỉ config screenshot.
7. **Owner/approver:** remediation owner và risk acceptance authority.
8. **Expiry/review trigger:** ngày hoặc điều kiện đánh giá lại.
9. **Remediation roadmap:** resolve dependency, upgrade/replace, planned milestones.
10. **Current vs target residual risk:** không hạ current risk bằng work chưa triển khai.
11. **Contract/compliance obligations:** không tự miễn trừ điều khoản bắt buộc bằng ký duyệt nội bộ.
12. **Exit/closure conditions:** patch active và tested, hoặc decision được thay đổi hợp lệ.

### Virtual patch không phải software patch

Một WAF rule hoặc network restriction có thể giảm attack surface trong thời gian chờ, nhưng không sửa code/package đang lỗi và có thể bypass từ internal paths. Ghi đúng bản chất **compensating mitigation**, kiểm thử hiệu quả, theo dõi drift/expiry.

### Quyết định trì hoãn cần xem lại theo thời gian

Nếu vulnerability xuất hiện trong known exploited list hoặc phát hiện Internet-facing route mới, risk thay đổi. Một exception từng phù hợp có thể phải được escalated ngay; không đợi expiry nếu threat/impact thay đáng kể.

## 39. Design review và release decision cho patch dependency

Một patch review có thể kết thúc bằng:

- **Ready to deploy:** prerequisites, compatibility, tests, recovery và change controls đạt cho scope.
- **Ready with conditions:** còn yêu cầu trước production/full rollout, owners/gates rõ.
- **Needs rework:** unsupported target, conflict hoặc unsafe migration.
- **Pending evidence:** design có thể phù hợp nhưng thiếu tests/runtime/restore proof.
- **Emergency mitigation authorized:** áp dụng interim containment theo incident process trong khi fix dài hạn chưa xong.
- **Partial rollout:** một số assets/regions fixed; phần còn lại có finding/exception.
- **Verified fixed (scope-limited):** runtime/version và tests đạt trên defined population/time window.

### Một bảng decision ngắn

| Decision dimension | Câu hỏi đánh giá | Ví dụ điều kiện không đạt |
| --- | --- | --- |
| Vulnerability applicability | Fix có xử lý đúng affected version/asset? | Wrong package hoặc backport chưa xác minh. |
| Dependency completeness | Hard prerequisites/conflicts có đủ? | SDK legacy incompatible, no migration. |
| Operational readiness | Capacity, backup/restore và monitoring sẵn sàng? | PDB unsatisfied hoặc restore failed. |
| Security tests | Negative paths và control invariants đạt? | Cross-tenant export unexpectedly ALLOW. |
| Runtime verification | Artifact/OS kernel active đúng version? | Một node pool chạy old digest. |
| Risk & change authority | Exceptions và release decisions đúng thẩm quyền? | Critical risk tự ký mà không risk owner. |
| Evidence quality | Observations có provenance/time/scope? | Chỉ dùng CI screenshot không có deploy evidence. |

### Mẫu quyết định trung thực

> “Security advisory A và dependency graph của Invoice API release R đã được review. Candidate fix được xác nhận tương thích trong staging, nhưng export worker SDK conflict C-01 và DB restore test chưa đạt. Không đưa vào full production rollout theo kế hoạch hiện tại; owner xử lý blockers, áp interim controls đã thử theo risk decision, rồi chạy lại contract/security/recovery gates. Chưa có cơ sở gọi production vulnerability fixed.”

Một statement như vậy hữu ích hơn “Patch blocked” vì nêu **cụ thể nguyên nhân, risk, bước tiếp theo và scope**.

## 40. Anti-patterns thường gặp

| Anti-pattern | Vì sao sai | Cách cải thiện |
| --- | --- | --- |
| **Installed = fixed** | Package trên disk có thể chưa active. | Runtime version, restart/reboot, negative tests. |
| **PR merged = remediated** | Image chưa build/deploy hoặc pod dùng digest cũ. | Build→digest→deployment→runtime trace. |
| **Dependency tree = rollout order** | Bỏ schema, contracts, capacity, reboot. | Layered dependency graph và release gates. |
| **Newest always safest** | Release channel hoặc compatibility không phù hợp. | Vendor supported fixed version + security review. |
| **Always upgrade every transitive library** | Ép version phá framework/library compatibility. | Align BOM, resolved graph và tests. |
| **Suppress until green** | Gỡ findings mà runtime chưa sửa. | Time-bound exception hoặc applicability evidence. |
| **One test happy path** | Không bắt security regression/replay/BOLA. | Threat-driven negative tests. |
| **Cumulative patch fixes all** | Third-party, firmware, native/runtime layers còn lỗi. | Product-specific advisory mapping. |
| **Reboot scheduled = activated** | Hệ thống vẫn chạy vulnerable kernel. | Effective version readback. |
| **Rollback is always easy** | Schema/data/keys không phải lúc nào reversible. | Verified restore/roll-forward strategy. |
| **Canary uses shared DB so fully isolated** | Shared state thay đổi ảnh hưởng toàn hệ thống. | Identify common-mode failure và safe migration. |
| **Security priority = execution order** | Hard prerequisites bị bỏ qua. | Interim mitigation + dependency sequencing. |
| **Patch all nodes at once** | Có thể mất quorum/capacity. | Progressive/ring strategy theo topology. |
| **Cloud provider patched, so we are patched** | Client libraries/config/IAM thuộc phía tổ chức. | Shared responsibility mapping. |
| **Package version string is enough** | Backports và distro packaging làm sai detection. | Vendor advisory/package build + runtime proof. |
| **Unknown assets count as no vulnerability** | Mẫu số bị làm đẹp. | Inventory confidence và gaps riêng. |
| **No alerts after patch = no regressions** | Sensor/log collector có thể hỏng. | Source health, synthetic checks, data reconciliation. |
| **Old version after rollback still fixed** | Quay lại lỗ hổng trước đó. | Reclassify current residual risk ngay. |
| **Approved exception = security PASS** | Risk acceptance không thay implementation. | Report EXCEPTION và retest conditions riêng. |
| **One green dashboard score** | Che critical service còn vulnerable. | Stratified coverage và criticality gates. |

## 41. Checklist đánh giá Patch Dependency

1. **Advisory:** xác nhận publisher, affected/fixed versions, scope, prerequisites?
2. **Asset inventory:** biết chính xác affected services, versions, images, firmware và regions?
3. **Runtime mapping:** package/source/advisory nối tới actual deployed digests/processes?
4. **Dependency graph:** ghi hard/soft prerequisites, conflicts, supersedence, edge types và owners?
5. **Transitives:** kiểm tra resolved dependencies, build plugins, base images, native libraries?
6. **Vendor support:** target nằm trong supported release line/channel?
7. **Cycles:** old/new coexist hoặc bridge được thiết kế?
8. **Schema:** API/event/database contracts có backward/forward compatibility?
9. **Security semantics:** MFA/authz/TLS/token/secret requirements có thay sau patch?
10. **Cloud/cluster:** Kubernetes/node/control plane/add-ons version skew được review?
11. **Restart/reboot:** activation dependency và method xác minh đã rõ?
12. **External integrations:** IdP/KMS/vendor/managed services có contract tests?
13. **Risk priority:** exploit intel, criticality, exposure và business impact được đánh giá?
14. **Execution order:** priority và prerequisite order được phân biệt?
15. **Capacity:** quorum, availability zones, PDB, headroom, long-running jobs?
16. **Recovery:** rollback/roll-forward phù hợp và backup restore đã thử?
17. **Provenance:** artifact signing/digest, SBOM, build identity và deploy authorization?
18. **Tests:** positive/negative/mixed-version/failure/load/security regression?
19. **Canary:** population có bao phủ critical business paths/tenant tiers?
20. **Operational monitoring:** alerts, logs, audit và source health có baseline?
21. **Runtime effective state:** từng asset/region/replica chạy fixed version?
22. **Coverage:** numerator, denominator, exclusions, partial/unknown cases rõ?
23. **Exceptions:** temporary mitigations, current residual risk, owner/expiry?
24. **Findings:** blocker, root cause, due date, retest, artifact linkage?
25. **Change approval:** đúng authority, maintenance window và release gate?
26. **Post-patch:** data integrity, security invariants, availability và rollback risk?
27. **Evidence quality:** source/time/version/scope/repeatability/limitations?
28. **Reassessment:** new asset/advisory/SDK/dependency/runtime change triggers?

### Cách ghi kết quả checklist

Mỗi câu cần **PASS, FAIL, PARTIAL, UNKNOWN hoặc NOT APPLICABLE kèm rationale**, evidence ID, owner và next action. Không gán PASS cho “có một kế hoạch”, “có một tool” hoặc “một test trong staging xanh” khi claim liên quan full production.

## 42. Bài tập tình huống và gợi ý giải

### Bài tập A — Patch đã installed nhưng kernel cũ vẫn chạy

Scanner báo OS package fixed, change ticket đã đóng; host chưa reboot do phục vụ batch processing quan trọng.

**Gợi ý:** Tách installed và activated. Kiểm tra effective kernel/build, scheduled maintenance, risk interim controls; chỉ kết luận fixed sau reboot hợp lệ và verification. Không reboot tùy ý nếu có safety/availability constraints.

### Bài tập B — Transitive dependency có CVE

Ứng dụng không khai library Z trực tiếp nhưng framework kéo Z phiên bản có advisory. Developer ép Z version mới, unit tests PASS, integration lỗi khi export invoice.

**Gợi ý:** Xem resolved dependency/BOM và supported fixed path; đánh giá API/ABI. Patch plan có thể cần framework upgrade hoặc adapter. Tạo contract/integration/security tests trước production.

### Bài tập C — Image trong registry đã sửa nhưng pod chưa nâng

CI build image mới và tag stable trỏ sang digest mới; các pods đang chạy vẫn dùng old digest.

**Gợi ý:** Link registry digest→deployment→pod runtime imageID. Trạng thái nên PARTIAL/NOT FIXED cho pods cũ; plan progressive rollout, verify tất cả replicas rồi retest vulnerability.

### Bài tập D — Database migration phá old workers

New API ghi event/schema v2, old worker vẫn chờ v1 và bỏ qua tenant context.

**Gợi ý:** Xây old/new compatibility matrix, expand–migrate–contract, schema versioning, server-owned trusted context, queue replay/authorization tests. Không bỏ qua field bảo mật chỉ để deserializer chạy.

### Bài tập E — Cumulative update được coi là mọi thứ đã fixed

Node cài một OS cumulative update nhưng container image vẫn chứa vulnerable user-space library.

**Gợi ý:** Cumulative supersedence chỉ trong phạm vi product/update. Kiểm tra container SBOM và actual runtime artifact, không suy từ OS patch ra application packages.

### Bài tập F — Hotfix có rủi ro rollback dữ liệu

DB schema migration xóa một cột đã chứa dữ liệu lịch sử; team định rollback binary nếu có lỗi.

**Gợi ý:** Rollback binary có thể không phục hồi cột/dữ liệu. Yêu cầu expand–contract, tested restore/roll-forward, data reconciliation, risk approval, no destructive step khi chưa đạt gate.

### Bài tập G — Patch có known exploitation nhưng cần upgrade dài

Internet-facing service bị ảnh hưởng bởi vulnerability ưu tiên rất cao; fixed library cần nâng JDK/OS và thay plugin cũ.

**Gợi ý:** Phân tách **immediate containment** và **permanent patch path**. Thực thi mitigation được phê duyệt/test (hạn route, IAM, segmentation, monitoring), theo dõi residual risk, song song giải quyết dependencies, không bỏ qua vulnerability vô thời hạn.

### Bài tập H — Nâng TLS làm hỏng partner

Security update ngừng cho một cipher cũ; một vendor integration fail. Ops đề nghị bật lại cipher yếu cho mọi tenants.

**Gợi ý:** Không mở lại weak configuration toàn hệ thống. Xem vendor upgrade, isolated gateway/migration path, bounded exception nếu policy cho phép, risk & compatibility test, deadline và monitoring.

### Bài tập I — Kubernetes node patch gây mất quorum

Hệ thống có ba replicas nhưng scheduling/anti-affinity sai, khi drain node đầu thì hai pods còn lại cùng mất storage path.

**Gợi ý:** Dependency gồm topology, PDB, storage, capacity, failure domain. Thử drain trong staging/canary, sửa resilience, kiểm tra data consistency và rollback trước khi patch toàn cluster.

### Bài tập J — Scanner vẫn báo CVE sau vendor backport

OS distro báo đã backport fix vào package revision; scanner chỉ so upstream version.

**Gợi ý:** Kiểm tra vendor advisory, package build/revision, affected code path, runtime effective state. Ghi applicability evidence và cập nhật scanner exception có owner/expiry; không tự mặc định scanner luôn sai.

### Bài tập K — Patching làm mất audit

Sau update logging agent, application vẫn chạy nhưng các authz failure events không xuất hiện trong SIEM.

**Gợi ý:** Security control regression và evidence gap. Kiểm tra telemetry heartbeat, event canaries, schema, collector/agent compatibility; không kết luận operating effectiveness chỉ vì app latency tốt.

### Bài tập L — Rollback đã phục hồi service nhưng lại lộ vulnerability

Canary fail, team rollback image cũ. Ứng dụng hoạt động trở lại và ticket được đổi thành Fixed.

**Gợi ý:** Đổi trạng thái về vulnerability vẫn affected theo actual digest, đánh giá exposure/mitigation, lập lại patch plan và retest. Service recovery không đồng nghĩa security fix.

### Bài tập M — Hai nhóm chờ nhau tạo dependency cycle

API v2 đòi worker v2; worker v2 đòi schema v2; schema v2 bị chặn vì old API v1 còn dùng.

**Gợi ý:** Thiết kế intermediate release và expand–contract, kiểm tra support old/new combinations, tách destructive contract phase khỏi functional rollout; có deadline loại clients cũ.

### Bài tập N — 99% rollout được tính là hoàn tất

99 trong 100 pods chạy patched image; pod còn lại chạy ở tenant tier nhạy cảm và có public data path.

**Gợi ý:** Verified runtime coverage là 99/100 nhưng không có quyền tuyên bố 100% critical paths fixed. Dùng risk-stratified gate, phát hiện pod cũ, khắc phục và retest theo actual scope.

## 43. Kết luận

**Patch dependency** trong **Patch management** là nghệ thuật và kỷ luật kỹ thuật của việc xử lý **những điều kiện khiến một bản vá có thể được chọn, triển khai, kích hoạt, xác minh và phục hồi đúng cách**. Những điều kiện đó không chỉ là dependency packages hay prerequisite updates; chúng còn gồm **OS/kernel/firmware, container image, Kubernetes control plane, schema và API/event contracts, identities/keys, vendor services, reboot, capacity, recovery và security tests**.

Trong **SECURITY_SECURITY_ASSURANCE**, patching chỉ trở thành bằng chứng giảm rủi ro khi tổ chức nối được **advisory → affected asset → dependency graph → planned changes → effective runtime state → negative/functional/failure tests → remediation evidence**, đồng thời minh bạch về **partial deployments, unknowns, blockers, exceptions và residual risk**. Thứ tự giải quyết theo **mức ưu tiên rủi ro** và thứ tự theo **prerequisite DAG** là hai quyết định liên quan nhưng không đồng nhất; khi chưa vá được ngay cần biện pháp giảm rủi ro tạm thời có kiểm chứng.

Một báo cáo “bản vá đã cài” hoặc “CI xanh” không thay được kiểm tra phiên bản hoạt động, data integrity, khả năng phục hồi và security invariants. **Chỉ kết luận yêu cầu vá đã đạt trong tài sản, phiên bản, môi trường và thời kỳ được chứng minh bằng bằng chứng đủ tin cậy; đồng thời tiếp tục đánh giá lại khi dependencies, artifacts, service contracts và threat landscape thay đổi.**
