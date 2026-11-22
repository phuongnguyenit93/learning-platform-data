# OPA hoặc hệ thống ReBAC: tiêu chí lựa chọn và phạm vi tích hợp với Spring Security

## 1. Bài toán kiến trúc: chính sách động nên ở đâu?

Một ứng dụng Spring Boot phục vụ hàng triệu tài liệu có ba yêu cầu đồng thời:

1. Người dùng chỉ truy cập tài liệu thuộc **tenant** mà họ là thành viên, không phụ thuộc ID hay header tự khai.
2. Alice có thể chia sẻ Document#101 cho Bob, một nhóm review hoặc một project. Quyền có thể được kế thừa theo quan hệ thư mục → tài liệu, nhóm → thành viên, organization → project.
3. Các luật thay đổi theo **ngữ cảnh**: tài liệu CONFIDENTIAL chỉ được đọc khi có clearance, trạng thái ACTIVE; lệnh export lớn đòi MFA; dữ liệu tài chính bị giới hạn theo thời gian, khu vực, risk score hoặc legal hold.

Nếu tất cả logic nằm trong hàng chục `@PreAuthorize` rải rác ở controller/service, việc thay đổi sẽ khó rà soát và các service có thể áp dụng chính sách không đồng đều. Hai hướng được cân nhắc:

- **Open Policy Agent (OPA)**: bộ máy policy-as-code dùng **Rego**, nhận input JSON và dữ liệu tham chiếu, trả quyết định. Mạnh ở luật dựa trên thuộc tính/ngữ cảnh (**ABAC**) và policy cross-cutting; có thể đánh giá nhiều loại rule, không giới hạn riêng authorization.
- **Relationship-Based Access Control (ReBAC)**: suy quyền từ đồ thị quan hệ **user–group–resource**, kiểu Zanzibar. Một hệ thống như **OpenFGA** lưu relationship tuples, định nghĩa authorization model và hỗ trợ các truy vấn `Check`, `ListObjects`, `ListUsers`. Mạnh ở sharing, membership, inheritance, group và phân quyền nhiều cấp.

**Không phải hai lựa chọn loại trừ nhau.** OPA cũng có thể đọc relationship data để ra quyết định, và OpenFGA có conditions cho thuộc tính runtime trong những giới hạn của model. Khác biệt chủ yếu là **abstraction, nơi lưu quyền, API truy vấn, vòng đời dữ liệu và năng lực vận hành**, không phải một bên “biết ABAC” còn bên kia “không thể ABAC”.

### 1.1. Ví dụ phân quyền thực tế

```text
Tenant t1
 ├── Group reviewers
 │    ├── user:bob
 │    └── user:claire
 ├── Folder project-7
 │    └── Document 101 (classification = INTERNAL)
 └── Document 102 (classification = CONFIDENTIAL)

Quan hệ:
  user:alice --owner--> document:101
  group:reviewers --viewer--> document:101
  user:bob --member--> group:reviewers

Ngữ cảnh:
  document:101.state = ACTIVE
  request.action = read
  caller.memberOf(t1) = true
  caller.risk = LOW
```

Để Bob được đọc Document#101, một policy kết hợp có thể yêu cầu:

```text
ALLOW =
    authenticated(Bob)
    AND memberOf(Bob, t1)
    AND canonicalTenant(Document#101) == t1
    AND ReBAC.Check(user:bob, can_read, document:t1-101)
    AND OPA.Allow(
          action="read",
          classification="INTERNAL",
          state="ACTIVE",
          risk="LOW"
        )
```

Điều kiện tenant và trạng thái tài nguyên được đọc từ **nguồn phía server**, không từ `X-Tenant-Id`, body hay quyền do client tự khai. Không bao giờ viết `OPA.allow OR ReBAC.allow` cho mô hình có ý định **cả hai** là điều kiện bắt buộc: nhánh OR có thể biến thành đường bypass.

## 2. PEP, PDP, PIP và điểm lưu quan hệ

Cần tách bốn trách nhiệm:

| Thành phần | Câu hỏi | Ví dụ trong ứng dụng |
|---|---|---|
| **PEP — Policy Enforcement Point** | Chặn hay cho phép request/method? | `SecurityFilterChain`, `AuthorizationManager`, `@PreAuthorize` |
| **PDP — Policy Decision Point** | Với subject/action/resource/context, quyết định thế nào? | OPA Rego engine, OpenFGA `Check` hoặc orchestrator kết hợp |
| **PIP — Policy Information Point** | Lấy thuộc tính nào từ nguồn tin cậy? | DB tenant membership, owner, resource state, clearance, IP đã xác minh |
| **Policy/relationship store** | Luật hay quan hệ được lưu/cập nhật ở đâu? | Git + OPA bundles; OpenFGA model/tuples; business database |

PEP luôn nằm trong ứng dụng Spring hoặc gateway vì OPA/OpenFGA **không tự sửa response HTTP hoặc chặn việc cập nhật database** khi không có integration. PDP chỉ trả thông tin quyết định; code của bạn phải **thực thi deny** tại mọi đường truy cập.

Một reference architecture:

```text
Browser / API client
       |
       v
[Spring Security authentication]
       |
       v
[PEP: AuthorizationManager / @PreAuthorize]
       |                         |
       |                 [PIP: canonical resource]
       |                 [PIP: server membership]
       |                         |
       +----------> Decision Orchestrator
                      /         \
                     v           v
               OPA/Rego        OpenFGA/ReBAC
               attributes      tuples/relations
                     \           /
                      v         v
                 explicit ALLOW/DENY
                           |
             ┌─────────────┴─────────────┐
             v                           v
          DENY 403                   ALLOW + guarded
                                    repository query
```

Đây là sơ đồ **logic**; không có nghĩa mọi request phải gọi **cả hai** dịch vụ. Hãy chọn mức đặt policy phù hợp với từng endpoint/nhóm dữ liệu và SLA.

### 2.1. Các mảnh luôn giữ trong ứng dụng

Ngay cả khi dùng external PDP, Spring Security vẫn nên đảm nhiệm:
- **Authentication**: xác minh JWT/session, issuer, audience và danh tính.
- **Tenant boundary**: kiểm tra principal membership và tenant canonical của resource; không phụ thuộc thông tin từ URL/header do client tự khai.
- **Input validation**: object ID, action, kiểu tài nguyên, parameter type; deny khi unknown.
- **Enforcement và side effects**: từ chối **trước** khi chạy mutation, và dùng WHERE tenant/ownership tại data layer.
- **Failure policy**: timeout, invalid response, HTTP 5xx, circuit breaker; không mặc định allow.
- **Audit**: correlation ID, decision source, model/policy version, resource/action, latency.

OPA/ReBAC không thay thế business transaction, row-level constraints, resource-existence check hoặc authentication.

## 3. OPA: policy-as-code và luật theo ngữ cảnh

**OPA** đánh giá rule viết bằng Rego, dựa trên `input` của lần quyết định và `data` (chính sách/dữ liệu đã được load). Ứng dụng có thể chạy OPA dạng sidecar, shared service hoặc tích hợp khác theo runtime được hỗ trợ. Với Java/Spring, gọi **OPA REST Data API** là mẫu tích hợp đơn giản:

```http
POST /v1/data/documents/allow HTTP/1.1
Content-Type: application/json

{
  "input": {
    "principal": "alice",
    "action": "read",
    "tenantId": "t1",
    "documentId": "101",
    "classification": "INTERNAL",
    "state": "ACTIVE",
    "boundAdmin": false,
    "owner": true
  }
}
```

Đây là ví dụ HTTP dùng **giá trị được backend xác minh**. Nếu có rule `data.documents.allow` trả boolean, OPA Data API trả:

```json
{"result":true}
```

Tuy nhiên **HTTP 200 không đồng nghĩa allow**: nếu query path không định nghĩa, OPA có thể trả `{}`, không có khóa `result`. Adapter phải chỉ cho phép khi `result` là boolean `true` chính xác; missing, null, non-boolean hay lỗi đều deny. Việc gửi input bằng `{"input":...}` và đọc `result` là hợp đồng chính thức của `POST /v1/data/{path}`.

### 3.1. Ví dụ policy Rego tương thích OPA v1

**`policy/documents.rego`**

```rego
package documents

default allow := false

# Một tài liệu INTERNAL ACTIVE được OPA chấp nhận
# nếu caller đã vượt tenant boundary ở Spring.
allow if {
    input.action == "read"
    input.state == "ACTIVE"
    input.classification == "INTERNAL"
}

# CONFIDENTIAL chỉ chấp nhận owner hoặc scoped admin.
allow if {
    input.action == "read"
    input.state == "ACTIVE"
    input.classification == "CONFIDENTIAL"
    input.owner == true
}

allow if {
    input.action == "read"
    input.state == "ACTIVE"
    input.classification == "CONFIDENTIAL"
    input.boundAdmin == true
}
```

Đây là một **policy minh họa**, chủ ý không có luật WRITE/DELETE. `default allow := false` đóng mọi hành động không định nghĩa. OPA 1.x dùng cú pháp Rego v1 với từ khóa `if`; trong OPA trước 1.0 có thể cần `import rego.v1` theo version.

Chạy với OPA CLI đã cài:

```bash
opa fmt policy/documents.rego
opa test policy/
opa run --server policy/documents.rego
```

`opa fmt` kiểm tra/format Rego; `opa test` chạy các test Rego **nếu có file test**; `opa run --server` chạy OPA server (thường tại `localhost:8181`). Dữ liệu input và Rego nằm ở hai lớp khác nhau: Rego **không tự truy cập** database Spring để đọc owner/tenant khi rule chạy; PIP phải truyền dữ liệu vào hoặc OPA được cung cấp dữ liệu theo một cơ chế đồng bộ được thiết kế.

### 3.2. Unit test Rego (policy regression)

**`policy/documents_test.rego`**

```rego
package documents

test_internal_active_allowed if {
    allow with input as {
        "action": "read",
        "state": "ACTIVE",
        "classification": "INTERNAL",
        "owner": false,
        "boundAdmin": false
    }
}

test_confidential_nonowner_denied if {
    not allow with input as {
        "action": "read",
        "state": "ACTIVE",
        "classification": "CONFIDENTIAL",
        "owner": false,
        "boundAdmin": false
    }
}

test_inactive_denied if {
    not allow with input as {
        "action": "read",
        "state": "ARCHIVED",
        "classification": "INTERNAL",
        "owner": true,
        "boundAdmin": true
    }
}

test_unknown_action_denied if {
    not allow with input as {
        "action": "delete",
        "state": "ACTIVE",
        "classification": "INTERNAL",
        "owner": true,
        "boundAdmin": true
    }
}
```

Với hai file `policy/documents.rego` và `policy/documents_test.rego`, lệnh:

```bash
opa test policy/ -v
```

kỳ vọng chạy bốn test đã định nghĩa. Đây là **kết quả kỳ vọng**, không phải log được thực thi. Test thêm tình huống thiếu field, kiểu dữ liệu sai, không có classification, revoke clearance, old/new policy versions và request risk cụ thể trong production.

### 3.3. Lợi thế và giới hạn thực tế của OPA

OPA hợp lý khi luật có nhiều thuộc tính: classification, action, risk, IP đã chuẩn hóa, thời gian, authentication assurance, trạng thái approval, hạn mức, region hoặc thuộc tính dịch vụ. Rego có policy-as-code, unit test, review, bundle distribution, decision logging và khả năng đánh giá gần ứng dụng giúp giảm network hop nếu đặt sidecar/embedded phù hợp.

Đổi lại:
- **Data synchronization**: OPA không biết membership hoặc resource graph mới nhất nếu bạn chưa cấp dữ liệu; cần chiến lược load, TTL, data ownership và refresh.
- **Graph quan hệ quy mô lớn**: có thể mã hóa bằng Rego/data, nhưng OPA **không mặc nhiên cung cấp** graph tuple storage, write/revoke relationship API và list authorized objects giống ReBAC service.
- **Policy governance**: quản lý branch, review, test, bundle signing/version, rollout/canary và rollback.
- **Hợp đồng input**: trường input do caller gửi phải được xác minh; policy đúng trên input giả vẫn có thể cho kết quả sai.
- **Decision semantics**: OPA có thể trả bất kỳ JSON document, không chỉ boolean; adapter phải tuân hợp đồng cố định.

Dùng OPA sidecar hay central PDP cần benchmark latency, throughput, resource budget, update propagation và fail-closed policy theo thực tế.

## 4. ReBAC: quan hệ, tuple và mô hình kiểu Zanzibar

Trong **ReBAC**, quyết định dựa trên mối quan hệ giữa subject và object, có thể thông qua nhóm hoặc đối tượng cha.

Một tuple thường mô tả:

```text
user:alice     owner   document:t1-101
user:bob       viewer  document:t1-101
group:reviewers#member viewer document:t1-102
document:t1-101 parent folder:t1-project-7
```

Các hàng trên chỉ là **minh họa ý nghĩa**; cần tạo authorization model cho type/relation trước khi write tuple vào OpenFGA. Với `group:reviewers#member`, OpenFGA có khả năng userset, cho phép quan hệ nhóm suy ra quyền người dùng.

### 4.1. Ví dụ authorization model OpenFGA

**`model.fga`**

```fga
model
  schema 1.1

type user

type group
  relations
    define member: [user]

type folder
  relations
    define viewer: [user, group#member]

type document
  relations
    define parent: [folder]
    define owner: [user]
    define viewer: [user, group#member] or viewer from parent or owner
    define editor: [user, group#member] or owner
    define can_read: viewer or editor
    define can_write: editor
```

Ở model này, `viewer from parent` có nghĩa một user được xem folder cha sẽ được tính là viewer của document có quan hệ `parent` đến folder đó. Điều này là **lựa chọn nghiệp vụ**, không phải hành vi tự động của mọi hệ thống ReBAC. Nếu tài liệu PRIVATE không được kế thừa, bạn phải sửa model theo đúng điều kiện và kiểm thử.

Trong thực tế, muốn dùng mô hình trên phải **tạo store, write authorization model**, lấy `store_id` và `authorization_model_id`, sau đó write tuples tương ứng. Không coi file FGA là một Spring Boot configuration tự được load khi ứng dụng khởi động.

### 4.2. OpenFGA Check API

```http
POST /stores/<store-id>/check HTTP/1.1
Content-Type: application/json

{
  "authorization_model_id": "<model-id>",
  "tuple_key": {
    "user": "user:bob",
    "relation": "can_read",
    "object": "document:t1-101"
  }
}
```

Phản hồi khi có quyền:

```json
{"allowed":true}
```

Hợp đồng này dựa trên `POST /stores/{store_id}/check` của OpenFGA. Trường `allowed` phải đúng boolean `true`; `false` là deny. **Không coi HTTP 200 là allow**. Nếu relation không tồn tại trong model, API có thể trả lỗi 400, không phải false; adapter phải fail-closed và ghi metrics phân loại lỗi cấu hình.

**Quan trọng:** OpenFGA là **một triển khai ReBAC cụ thể**, không phải đồng nghĩa với toàn bộ ReBAC. Những triển khai khác có model, consistency contract, APIs và chi phí vận hành khác. Chọn model/phiên bản/SDK đúng với nhà cung cấp đang dùng.

### 4.3. Vì sao ReBAC mạnh ở chia sẻ và phân cấp?

ReBAC trả lời tự nhiên các câu hỏi:
- Bob được share trực tiếp Document#101 hay chỉ thừa hưởng từ Group reviewers?
- Editor của Folder X có thể edit các documents con không?
- Alice là owner của project; ai có thể view/edit các issue bên trong?
- User nằm trong team mà team nằm trong organization nào?
- Làm sao lấy danh sách object mà user có `can_read`?

Một store như OpenFGA cung cấp `Check`, `ListObjects`, `ListUsers` và `BatchCheck` cho các dạng truy vấn này. Nhưng **không tự có** tenant boundary của database ứng dụng: mapping ID, ownership, tenant change và lifecycle tuple phải được đồng bộ từ nguồn tin cậy.

### 4.4. Điều kiện runtime không biến mất khỏi ReBAC

OpenFGA hỗ trợ **conditional tuples** và các hình thức condition khi model cho phép, nên không đúng khi nói “ReBAC không xét thời gian/IP”. Tuy nhiên policy có nhiều luật risk, số tiền, clearance, địa lý, rule phủ định hoặc logic nghiệp vụ thay đổi nhanh có thể dễ quản lý hơn bằng OPA/Rego ở PDP chuyên về luật. Hãy xét **độ biểu đạt cần thiết và cách phân phối dữ liệu**, thay vì so sánh theo tên ABAC/ReBAC một cách tuyệt đối.

## 5. Ma trận lựa chọn: khi nào OPA, ReBAC hoặc kết hợp?

| Tiêu chí | OPA / Rego | ReBAC / OpenFGA | Hướng dẫn lựa chọn |
|---|---|---|---|
| Policy dựa trên nhiều thuộc tính và rủi ro | Rất phù hợp | Có conditions nhưng model-centric | OPA nếu ngữ cảnh chiếm ưu thế |
| Quan hệ user–group–folder–resource | Có thể biểu diễn bằng `data` | Là abstraction cốt lõi | ReBAC khi graph/share là nghiệp vụ trung tâm |
| Cấp/revoke grant bởi người dùng | Cần thiết kế data/CRUD riêng | Tuple write/delete rõ ràng | ReBAC nếu share UI thường xuyên |
| Group membership, inheritance | Tự tổ chức data/policy | Graph relations, usersets | ReBAC |
| Luật điều kiện phức tạp | Rego dễ đóng gói/test | Conditions phù hợp một số trường hợp | OPA hoặc hybrid |
| List objects được phép | Compile/partial evaluation, data filtering tích hợp | `ListObjects`/batch checks | Xét tính đúng của paging và performance |
| Policy-as-code review | Rego trong Git/bundles | Model version + tests, tuples là data runtime | Phụ thuộc governance |
| Thay đổi policy nhỏ, gần app | Sidecar/local runtime có thể hợp lý | Remote service thường cần topology riêng | Benchmark deployment |
| Kiểm tra theo model & tuple version | Version policy/bundle; data sync riêng | Model ID + tuple state/consistency | Xét tính nhất quán revoke |
| Latency và chi phí request | Phụ thuộc placement/data size | Phụ thuộc graph query/cache/storage | P95/P99 + load test thực tế |
| Multi-tenant data boundary | Cần local PIP/guard | Cần tenant-aware model/object IDs/guard | Cả hai **không thay** tenant authorization |
| Độ phức tạp vận hành | OPA rollout, bundles, logs, data sync | Model/tuple writes, graph DB, query service | Chọn theo năng lực team |
| Security review | Rego policy diff, tests | Model diff + tuple audit/write policy | Cả hai cần threat modeling |

**Quy tắc chọn nhanh:**

1. Nếu bài toán chủ yếu là **classification, risk, thời gian, môi trường, compliance** và tập quan hệ đơn giản: ưu tiên **OPA** hoặc policy engine tương đương.
2. Nếu bài toán chủ yếu là **chia sẻ tài liệu, nhóm, project, inheritance, owner/editor/viewer, ListObjects**: ưu tiên **ReBAC** như OpenFGA.
3. Nếu cần **quan hệ động + luật bảo mật ngữ cảnh bắt buộc**: chọn **hybrid**, thường với phép **AND** cho những điều kiện bắt buộc, hoặc định nghĩa policy kết hợp có chứng minh.
4. Nếu chỉ có vài role cố định và không có nhu cầu thay đổi policy độc lập, **Spring Security tại chỗ** có thể đủ; không đưa distributed PDP vào hệ thống chỉ vì xu hướng.

Không có “độ trễ mặc định X ms” hay “giá tốt nhất” đúng cho mọi cài đặt. Đo trên hạ tầng, dữ liệu, graph và traffic thật.

### 5.1. Tính thử tổng chi phí

Tính:
- `N_checks/sec` cho read, write, API list và background jobs.
- P50/P95/P99 của decision, queueing, retry và TLS overhead.
- Độ lớn request context, số quan hệ trung bình mỗi object, group depth.
- Memory/CPU của sidecar OPA và storage/CPU của ReBAC.
- Chi phí model/tuple migration, event ingestion, cache invalidation, on-call.
- Thời gian chấp nhận revoke: vài giây, phút hay cần gần realtime.
- Log throughput, retention và redaction dữ liệu nhạy cảm.

Đưa cả **cost of correctness** vào quyết định: một hệ thống rẻ nhưng mô hình quyền khó kiểm toán hoặc dễ fail-open có thể tốn kém hơn nhiều khi xảy ra sự cố.

## 6. Phạm vi tích hợp Spring Security: lựa chọn PEP

Có hai điểm đặt PEP thông dụng.

### 6.1. HTTP-level AuthorizationManager

Spring Security 6.5 cho phép dùng custom `AuthorizationManager<RequestAuthorizationContext>` với `authorizeHttpRequests(...).anyRequest().access(manager)`.

```java
@Component
final class RemoteAuthorizationManager
        implements AuthorizationManager<RequestAuthorizationContext> {

    @Override
    public AuthorizationDecision check(
            Supplier<Authentication> authentication,
            RequestAuthorizationContext context) {
        // Đưa authenticated principal + canonical resource/context
        // tới PDP; thiếu kết quả hoặc lỗi => deny.
        return new AuthorizationDecision(false);
    }
}
```

Đây là **khung API minh họa**, chưa bao gồm imports/constructor/lookup. Đặt PEP ở HTTP layer hợp lý cho một gateway, route-level scopes hoặc API không có logic service riêng. Nhưng chỉ dựa vào URL không đủ bảo đảm `documentId` thuộc tenant hoặc người dùng được phép trên object; muốn an toàn cần canonical lookup và protected DB query. Với các lời gọi từ job/batch/event consumer, HTTP PEP có thể bị bypass.

### 6.2. Method-level @PreAuthorize (đề xuất mặc định cho domain)

```java
@PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")
public DocumentView read(@P("documentId") Long documentId) {
    // Chỉ chạy nếu policy cho phép.
}
```

Đây là cấu trúc minh họa; `@EnableMethodSecurity` phải được bật và method phải gọi qua **Spring-managed proxy**. Đặt policy ở service boundary giúp tái sử dụng giữa HTTP, scheduler và service khác; repository vẫn phải áp `tenant_id` và guarded predicates.

Không dùng `@PostAuthorize` để đánh giá quyền sau khi method đã ghi DB, gửi email hoặc gọi webhook; side effect có thể đã xảy ra trước deny. Với mutation, xét quyền **trước** tác động, kèm transaction/conditional update để giảm TOCTOU.

### 6.3. Không cho client định nghĩa PDP input tin cậy

Trong ví dụ sau, controller chỉ nhận `documentId`; Java policy lấy:
- `principal` từ Spring Security `Authentication`.
- `tenantId` và `classification` từ canonical document repository.
- membership và admin binding từ nguồn phía server.
- `action="read"` từ method đang được gọi, không nhận từ JSON tùy ý.

Nếu đầu vào OPA/ReBAC chứa `isAdmin=true` được lắp từ body, policy có thể “đúng với input” nhưng sai về bảo mật. Tính tin cậy của **PIP** quan trọng không kém biểu thức Rego hay FGA model.

## 7. Demo Java 17: một PEP, hai PDP adapter, lựa chọn qua cấu hình

Ví dụ dùng Spring Boot **3.5.6** (Spring Security **6.5.x** do Boot quản lý). Endpoint GET đọc document qua `@PreAuthorize`. `DocumentPolicy` luôn kiểm tra Authentication + tenant membership + canonical document state; sau đó:

- `app.authz.mode=opa`: yêu cầu OPA cho phép.
- `app.authz.mode=rebac`: yêu cầu OpenFGA cho phép.
- `app.authz.mode=hybrid`: **cả hai** phải cho phép.

Trong test, hai adapter được mock, không cần chạy OPA/OpenFGA thật. Trong vận hành, cấu hình URL, store/model ID và triển khai PDP tương ứng. Phải kiểm thử contract HTTP và policy/model thật riêng trước khi đưa vào production.

### 7.1. Cây dự án

```text
policy-pdp-demo/
  pom.xml
  src/main/java/com/example/pdp/
    PdpApplication.java
    SecurityConfig.java
    Document.java
    DocumentCatalog.java
    TenantDirectory.java
    DecisionInput.java
    OpaDecisionPort.java
    RebacDecisionPort.java
    OpaHttpDecisionPort.java
    OpenFgaHttpDecisionPort.java
    DocumentPolicy.java
    DocumentService.java
    DocumentController.java
  src/main/resources/
    application.properties
  src/test/java/com/example/pdp/
    DocumentPolicyIntegrationTest.java

# Tùy chọn, chạy OPA/OpenFGA độc lập:
  policy/documents.rego
  policy/documents_test.rego
  model.fga
```

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.6</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>policy-pdp-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build><plugins><plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
  </plugin></plugins></build>
</project>
```

Không ép version Spring Security riêng. `RestClient` có trong Spring Framework được Boot quản lý; test annotation `@MockitoBean` có trong Spring Framework 6.2. Không cần dependency OpenFGA SDK khi dùng REST API bằng `RestClient`; SDK chính thức là lựa chọn khác nếu muốn quản lý auth/retry/model IDs và tracing thuận tiện.

### 7.3. Boot application và SecurityConfig

**`src/main/java/com/example/pdp/PdpApplication.java`**

```java
package com.example.pdp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PdpApplication {
    public static void main(String[] args) {
        SpringApplication.run(PdpApplication.class, args);
    }
}
```

**`src/main/java/com/example/pdp/SecurityConfig.java`**

```java
package com.example.pdp;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/documents/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

`@EnableMethodSecurity` kích hoạt `@PreAuthorize`. HTTP layer chỉ đòi Authentication, còn object-level decision nằm trong service. Khi chạy không có configured credentials, endpoint GET vẫn yêu cầu đăng nhập; integration tests dùng `@WithMockUser`. Dùng resource server JWT ở production phải verify issuer/audience/signature và tenant mappings.

### 7.4. Document và dữ liệu canonical

**`src/main/java/com/example/pdp/Document.java`**

```java
package com.example.pdp;

public record Document(
        Long id,
        String tenantId,
        String owner,
        String classification,
        String state,
        String title) {}
```

**`src/main/java/com/example/pdp/DocumentCatalog.java`**

```java
package com.example.pdp;

import java.util.Map;
import org.springframework.stereotype.Repository;

@Repository
public class DocumentCatalog {
    private final Map<Long, Document> docs = Map.of(
        101L, new Document(
            101L, "t1", "alice",
            "INTERNAL", "ACTIVE", "Quarterly report"),
        102L, new Document(
            102L, "t1", "alice",
            "CONFIDENTIAL", "ACTIVE", "Strategy"),
        103L, new Document(
            103L, "t1", "manager",
            "INTERNAL", "ARCHIVED", "Old notes"),
        201L, new Document(
            201L, "t2", "carol",
            "INTERNAL", "ACTIVE", "South report")
    );

    public Document find(Long id) {
        return id == null ? null : docs.get(id);
    }
}
```

**`src/main/java/com/example/pdp/TenantDirectory.java`**

```java
package com.example.pdp;

import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Component;

@Component
public class TenantDirectory {
    private final Map<String, Set<String>> members = Map.of(
        "t1", Set.of("alice", "bob", "manager"),
        "t2", Set.of("carol", "dave")
    );

    private final Set<String> admins = Set.of("t1:manager");

    public boolean isMember(String tenant, String user) {
        Set<String> users = members.get(tenant);
        return users != null && user != null
            && users.contains(user);
    }

    public boolean isBoundAdmin(String tenant, String user) {
        return tenant != null && user != null
            && admins.contains(tenant + ":" + user);
    }
}
```

Catalog và directory chứa dữ liệu tin cậy **trong demo**. Production thay bằng repository hoặc IAM đồng bộ; không cho caller tự truyền `owner`, `tenantId` hay `isBoundAdmin` để bypass policy.

### 7.5. DecisionInput và hai port

**`src/main/java/com/example/pdp/DecisionInput.java`**

```java
package com.example.pdp;

public record DecisionInput(
        String principal,
        String tenantId,
        String documentId,
        String action,
        String classification,
        String state,
        boolean owner,
        boolean boundAdmin) {}
```

**`src/main/java/com/example/pdp/OpaDecisionPort.java`**

```java
package com.example.pdp;

public interface OpaDecisionPort {
    boolean allowed(DecisionInput input);
}
```

**`src/main/java/com/example/pdp/RebacDecisionPort.java`**

```java
package com.example.pdp;

public interface RebacDecisionPort {
    boolean allowed(DecisionInput input);
}
```

Ports tạo ranh giới rõ giữa Spring PEP/PIP và remote PDP. Test có thể thay port bằng mock; đổi OpenFGA sang ReBAC khác không buộc sửa business service. Trong production, thường bổ sung structured decision, policy/model version, reason code, correlation ID và latency metrics thay vì chỉ boolean.

### 7.6. OPA HTTP adapter

**`src/main/java/com/example/pdp/OpaHttpDecisionPort.java`**

```java
package com.example.pdp;

import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class OpaHttpDecisionPort implements OpaDecisionPort {
    private final RestClient rest;

    public OpaHttpDecisionPort(
            RestClient.Builder builder,
            @Value("`${app.authz.opa.url:http://localhost:8181}`")
            String opaUrl) {
        this.rest = builder.baseUrl(opaUrl).build();
    }

    @Override
    public boolean allowed(DecisionInput input) {
        Map<?, ?> reply = rest.post()
            .uri("/v1/data/documents/allow")
            .body(Map.of("input", input))
            .retrieve()
            .body(Map.class);

        // OPA 200 với {} hoặc result không phải true = DENY.
        return reply != null
            && Boolean.TRUE.equals(reply.get("result"));
    }
}
```

**Giải thích:** OPA nhận JSON body `{"input":{...}}`; adapter chỉ chấp nhận response `result === true`. Nếu HTTP 4xx/5xx, timeout hoặc JSON sai, `RestClient` sẽ ném exception hoặc trả giá trị không hợp lệ, và orchestrator phải **fail-closed**. Không bỏ qua lỗi để trả allow.

### 7.7. OpenFGA HTTP adapter

**`src/main/java/com/example/pdp/OpenFgaHttpDecisionPort.java`**

```java
package com.example.pdp;

import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class OpenFgaHttpDecisionPort implements RebacDecisionPort {
    private final RestClient rest;
    private final String storeId;
    private final String modelId;

    public OpenFgaHttpDecisionPort(
            RestClient.Builder builder,
            @Value("`${app.authz.fga.url:http://localhost:8080}`")
            String url,
            @Value("`${app.authz.fga.store-id:demo-store}`")
            String storeId,
            @Value("`${app.authz.fga.model-id:demo-model}`")
            String modelId) {
        this.rest = builder.baseUrl(url).build();
        this.storeId = storeId;
        this.modelId = modelId;
    }

    @Override
    public boolean allowed(DecisionInput input) {
        // Ánh xạ action nghiệp vụ sang relation có trong FGA model.
        String relation = switch (input.action()) {
            case "read" -> "can_read";
            default -> throw new IllegalArgumentException(
                "Action not modeled");
        };

        // Tên object phải khớp tuple đã write;
        // tenant-qualified ID ngăn trùng khóa giữa tenants.
        String objectId = "document:"
            + input.tenantId() + "-" + input.documentId();

        Map<String, Object> tuple = Map.of(
            "user", "user:" + input.principal(),
            "relation", relation,
            "object", objectId
        );
        Map<String, Object> body = Map.of(
            "authorization_model_id", modelId,
            "tuple_key", tuple
        );

        Map<?, ?> reply = rest.post()
            .uri("/stores/{storeId}/check", storeId)
            .body(body)
            .retrieve()
            .body(Map.class);

        return reply != null
            && Boolean.TRUE.equals(reply.get("allowed"));
    }
}
```

**Cảnh báo về cấu hình:** `demo-store` và `demo-model` chỉ là giá trị local mặc định; để gọi **OpenFGA thật**, phải tạo store, publish model, write các tuples và điền ID thật. Nếu OpenFGA yêu cầu authentication, cấu hình `RestClient` với bearer token/mTLS từ secret store; không hardcode secret hoặc cho client truyền token PDP. Trong production nên giới hạn connect/read timeout, thêm retry budget/circuit breaker phù hợp và metric khi PDP lỗi.

Không dùng username cục bộ như `user:alice` nếu nó không globally unique trong nhiều IdP/tenant. Với nhiều issuer, chọn một subject identifier canonical như `issuer+subject` hoặc internal user ID, rồi đảm bảo chính ID đó được write vào tuples.

### 7.8. Orchestrator: tenant boundary AND quyết định bên ngoài

**`src/main/java/com/example/pdp/DocumentPolicy.java`**

```java
package com.example.pdp;

import java.util.Locale;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {
    public enum Mode { OPA, REBAC, HYBRID }

    private final DocumentCatalog docs;
    private final TenantDirectory tenants;
    private final OpaDecisionPort opa;
    private final RebacDecisionPort rebac;
    private final Mode mode;
    private final AuthenticationTrustResolver trust =
        new AuthenticationTrustResolverImpl();

    public DocumentPolicy(
            DocumentCatalog docs,
            TenantDirectory tenants,
            OpaDecisionPort opa,
            RebacDecisionPort rebac,
            @Value("`${app.authz.mode:hybrid}`")
            String mode) {
        this.docs = docs;
        this.tenants = tenants;
        this.opa = opa;
        this.rebac = rebac;
        this.mode = Mode.valueOf(mode.toUpperCase(Locale.ROOT));
    }

    private static boolean hasAuthority(
            Authentication auth, String name) {
        for (GrantedAuthority authority : auth.getAuthorities()) {
            if (name.equals(authority.getAuthority())) {
                return true;
            }
        }
        return false;
    }

    public boolean canRead(Authentication auth, Long documentId) {
        if (auth == null || !auth.isAuthenticated()
                || trust.isAnonymous(auth)) {
            return false;
        }

        Document doc = docs.find(documentId);
        if (doc == null
                || !tenants.isMember(doc.tenantId(), auth.getName())) {
            return false;
        }

        // Baseline bất biến cho TẤT CẢ mode: deny archived.
        if (!"ACTIVE".equals(doc.state())) {
            return false;
        }

        boolean admin = hasAuthority(
            auth, "ROLE_TENANT_ADMIN")
            && tenants.isBoundAdmin(doc.tenantId(), auth.getName());

        DecisionInput input = new DecisionInput(
            auth.getName(), doc.tenantId(),
            String.valueOf(doc.id()), "read",
            doc.classification(), doc.state(),
            auth.getName().equals(doc.owner()),
            admin
        );

        // Lỗi, timeout, missing result, wrong model => DENY.
        try {
            return switch (mode) {
                case OPA -> opa.allowed(input);
                case REBAC -> rebac.allowed(input);
                case HYBRID ->
                    opa.allowed(input) && rebac.allowed(input);
            };
        }
        catch (RuntimeException ex) {
            // Production: log/metric theo mã lỗi, không lộ secret.
            return false;
        }
    }
}
```

**Lưu ý ý nghĩa:** Các mode khác nhau dùng các chính sách khác nhau. Trong demo, `REBAC` vẫn có baseline “ACTIVE + tenant membership”, nhưng **không mặc nhiên áp mọi luật classification của OPA**. Vì vậy không nên bật mode REBAC-only cho dữ liệu mà luật classification là ràng buộc bắt buộc, trừ khi đã chuyển luật đó sang một guard đáng tin hoặc FGA condition. Đừng coi chuyển mode là thao tác performance vô hại; đó là thay đổi security policy, cần review, migration và tests.

Khi `mode=HYBRID`, toán tử `&&` short-circuit: OPA trả deny thì ReBAC không được gọi. Nếu OPA cho phép nhưng ReBAC từ chối, kết quả vẫn deny. Nếu bất kỳ adapter ném exception, kết quả deny. Cách này minh họa **intersection policy**; một hệ thống khác có thể có tập luật OR có chủ ý, nhưng phải chứng minh rằng OR đó không bypass tenant, data classification hoặc điều kiện bảo mật bắt buộc.

### 7.9. Domain service và controller

**`src/main/java/com/example/pdp/DocumentService.java`**

```java
package com.example.pdp;

import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentCatalog docs;

    public DocumentService(DocumentCatalog docs) {
        this.docs = docs;
    }

    @PreAuthorize(
        "@documentPolicy.canRead(authentication, #documentId)"
    )
    public Document read(@P("documentId") Long documentId) {
        return docs.find(documentId);
    }
}
```

**`src/main/java/com/example/pdp/DocumentController.java`**

```java
package com.example.pdp;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/documents")
public class DocumentController {
    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{documentId}")
    public Document read(
            @PathVariable("documentId") Long documentId) {
        return service.read(documentId);
    }
}
```

**`src/main/resources/application.properties`**

```properties
app.authz.mode=hybrid
app.authz.opa.url=http://localhost:8181
app.authz.fga.url=http://localhost:8080
app.authz.fga.store-id=demo-store
app.authz.fga.model-id=demo-model
```

Lựa chọn `app.authz.mode` nên là config của server được bảo vệ, **không lấy từ query/header** để caller tự chuyển sang mode dễ hơn. Dù controller không có tenant ID trên URL, policy vẫn lấy tenant canonical từ document và membership tương ứng. Nếu endpoint thực sự có tenant ID trên path, phải **xác minh pathTenant == doc.tenantId** trước khi gọi PDP.

Đoạn `DocumentService.read` không có mutation nên dễ tập trung vào authorization. Với write/delete, cần `@PreAuthorize` trên action tương ứng, transaction và guarded SQL update có tenant/owner/version predicates.

### 7.10. Integration tests: PEP và fail-closed với mock ports

**`src/test/java/com/example/pdp/DocumentPolicyIntegrationTest.java`**

```java
package com.example.pdp;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentPolicyIntegrationTest {
    @Autowired MockMvc mvc;
    @Autowired DocumentService service;

    @MockitoBean OpaDecisionPort opa;
    @MockitoBean RebacDecisionPort rebac;

    @BeforeEach
    void allowBothByDefault() {
        when(opa.allowed(any())).thenReturn(true);
        when(rebac.allowed(any())).thenReturn(true);
    }

    @Test
    @WithMockUser(username = "alice")
    void ownerWithBothGrantsCanRead() throws Exception {
        mvc.perform(get("/api/documents/101"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Quarterly report"));
    }

    @Test
    @WithMockUser(username = "bob")
    void tenantMemberCanReadWhenBothPdpAllow() throws Exception {
        mvc.perform(get("/api/documents/101"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "carol")
    void otherTenantOwnerCanReadOwnResource() throws Exception {
        mvc.perform(get("/api/documents/201"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "alice")
    void membershipDoesNotCrossTenant() throws Exception {
        mvc.perform(get("/api/documents/201"))
            .andExpect(status().isForbidden());
        verifyNoInteractions(opa, rebac);
    }

    @Test
    @WithMockUser(username = "mallory")
    void unknownMemberCannotReachPdp() throws Exception {
        mvc.perform(get("/api/documents/101"))
            .andExpect(status().isForbidden());
        verifyNoInteractions(opa, rebac);
    }

    @Test
    @WithMockUser(username = "alice")
    void unknownResourceFailsClosed() throws Exception {
        mvc.perform(get("/api/documents/999"))
            .andExpect(status().isForbidden());
        verifyNoInteractions(opa, rebac);
    }

    @Test
    @WithMockUser(username = "manager", roles = "TENANT_ADMIN")
    void archivedResourceDeniedBeforeAnyPdpCall()
            throws Exception {
        mvc.perform(get("/api/documents/103"))
            .andExpect(status().isForbidden());
        verifyNoInteractions(opa, rebac);
    }

    @Test
    @WithMockUser(username = "alice")
    void opaDenyOverridesRebacAllow() throws Exception {
        when(opa.allowed(any())).thenReturn(false);
        mvc.perform(get("/api/documents/101"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice")
    void rebacDenyOverridesOpaAllow() throws Exception {
        when(rebac.allowed(any())).thenReturn(false);
        mvc.perform(get("/api/documents/101"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice")
    void opaTimeoutOrExceptionFailsClosed() throws Exception {
        when(opa.allowed(any())).thenThrow(
            new IllegalStateException("OPA unavailable"));
        mvc.perform(get("/api/documents/101"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice")
    void rebacExceptionFailsClosed() throws Exception {
        when(rebac.allowed(any())).thenThrow(
            new IllegalStateException("ReBAC unavailable"));
        mvc.perform(get("/api/documents/101"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "manager", roles = "TENANT_ADMIN")
    void boundAdminCanReadIfBothPdpApprove() throws Exception {
        mvc.perform(get("/api/documents/102"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "bob", roles = "TENANT_ADMIN")
    void roleStringAloneDoesNotGrantCrossTenant()
            throws Exception {
        mvc.perform(get("/api/documents/201"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob")
    void spoofedRoleAndTenantHeadersDoNotGrantAccess()
            throws Exception {
        mvc.perform(get("/api/documents/201")
                .header("X-Tenant-Id", "t2")
                .header("X-User", "carol")
                .header("X-Role", "ROLE_TENANT_ADMIN"))
            .andExpect(status().isForbidden());
    }

    @Test
    void anonymousRequestIsChallenged() throws Exception {
        mvc.perform(get("/api/documents/101"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "alice")
    void directSpringManagedServiceAlsoEnforcesPolicy() {
        when(rebac.allowed(any())).thenReturn(false);
        assertThrows(AccessDeniedException.class,
            () -> service.read(101L));
    }

    @Test
    @WithMockUser(username = "alice")
    void successfulServiceCallReturnsCanonicalTenant() {
        Document doc = service.read(101L);
        assertEquals("t1", doc.tenantId());
        assertEquals("alice", doc.owner());
    }
}
```

Từ thư mục `policy-pdp-demo`:

```bash
mvn test
```

**Kỳ vọng từ code:** Các JUnit/MockMvc tests pass, minh họa kiểm tra local baseline trước khi gọi PDP, hybrid AND, lỗi PDP fail-closed, spoofed headers không tạo quyền, Method Security chặn cả lời gọi service trực tiếp. Các test **mock OPA/ReBAC ports**; chúng **không** chứng minh:
- REST body/response khớp một OPA/OpenFGA server thật.
- Rego policy/FGA model thực đã được load và tuple đã write.
- Tính đúng của consistency, latency, TLS, bearer tokens hoặc cache.
- Dữ liệu PIP được đồng bộ khi một grant bị revoke.

Do đó phải có **contract tests** và **end-to-end tests** gọi instance OPA/OpenFGA được quản lý, sử dụng chính policy/model thực, bao gồm timeout và model migration. Không coi `@MockitoBean` là bằng chứng hạ tầng authorization đã đạt production readiness.

## 8. Hybrid: cùng một quyết định nhưng hai nguồn quyền

Trong nhiều sản phẩm tài liệu, ReBAC làm **discretionary grants** (ai được share/owner/group), OPA làm **mandatory guard** (mức phân loại, risk, compliance). Một chính sách:

```text
permitRead(user, document, requestContext) =
    isAuthenticated(user)
    AND isTenantMember(user, document.tenantId)
    AND document.state == ACTIVE
    AND OpenFGA.Check(user, "can_read", document)
    AND OPA.Check(classification, clearance, deviceTrust, risk)
```

Với document CONFIDENTIAL, Bob có viewer tuple từ nhóm nhưng OPA deny vì chưa đủ clearance → **DENY**. Khi OPA allow nhưng relationship tuple bị revoke → **DENY**. Hai engine không tự biết về nhau; orchestrator phải chịu trách nhiệm kết hợp bằng chính sách được review.

### 8.1. Quy tắc precedence và deny

| Baseline tenant | ReBAC | OPA | Kết quả hybrid AND |
|---|---|---|---|
| Deny | Allow | Allow | Deny |
| Allow | Deny | Allow | Deny |
| Allow | Allow | Deny | Deny |
| Allow | Allow | Allow | Allow |
| Allow | Timeout/error | Allow | Deny |
| Allow | Allow | Undefined/result missing | Deny |

Có những use case cho OR hoặc override admin; nếu vậy phải xác định rõ “global mandatory denies” **không được** nằm trong nhánh có thể bỏ qua. Một `ROLE_SUPER_ADMIN` không mặc nhiên miễn legal hold hoặc cross-tenant boundary.

### 8.2. Tại sao không gửi toàn bộ document cho PDP?

Chỉ gửi những thuộc tính tối thiểu cần thiết: canonical ID/tenant, classification, status và các điều kiện risk đã chuẩn hóa. Không đẩy nội dung tài liệu, access token, raw cookies hoặc PII thừa vào decision logs. OPA decision logging và tracing rất hữu ích nhưng có thể ghi `input`; cần redaction/masking và retention phù hợp.

### 8.3. Thu hồi quyền và consistency

Một người bị revoke từ OpenFGA nhưng cache vẫn trả allow trong thời gian TTL có thể tạo access window. OpenFGA có các lựa chọn truy vấn **`MINIMIZE_LATENCY`** và **`HIGHER_CONSISTENCY`**: lựa chọn thứ hai bỏ qua cache để đọc data store, đánh đổi latency. Điều đó **không tự bảo đảm** giao dịch nguyên tử xuyên database nghiệp vụ và OpenFGA, cũng không xóa mọi stale information ở tầng khác.

Trong OPA, policy bundle/data update cũng có propagation delay; sidecar từng node có thể nhận version mới khác thời điểm. Có thể:
- Track version của policy/model và relationship write.
- Phát invalidation event khi revoke.
- Dùng higher-consistency check khi một thay đổi mới xảy ra hoặc action nhạy cảm.
- Xác định SLA revoke rồi test cụ thể trên production topology.
- Không cho fallback “allow theo cache cũ” khi PDP unavailable nếu không có security proof.

## 9. Đồng bộ quan hệ và dữ liệu nghiệp vụ: source of truth

Trong ReBAC service, tuple `document:t1-101#viewer@user:bob` có thể tồn tại dù domain Document#101 đã bị xóa nếu lifecycle không được nối. Nếu document được move sang tenant khác, tuple parent cũ có thể vẫn suy quyền từ tenant gốc. Cần thiết kế mutation workflow:

```text
User share Document#101 to Bob
    |
    v
Validate actor canShare + recipient tenant
    |
    v
Persist business share intent / version
    |
    v
Write relationship tuple
    |
    v
Audit + publish/reconcile + test effective Check
```

**Không có transaction JDBC mặc định** bao cả Spring database và OpenFGA/OPA HTTP. Các lựa chọn:
- Business DB là source of truth, transaction ghi share metadata + outbox, worker đồng bộ tuples theo retry/idempotency; trong thời gian chờ, policy phải xác định rõ behavior (có thể deny cho tới khi confirmed).
- ReBAC store là nguồn quyền cho relationship; domain DB giữ resource/tenant metadata, mutation phải bảo đảm idempotency và reconciliation.
- Có event-sourced projection/version cho quan hệ; monitor lag và “stale grant” có cảnh báo.

Với OPA, nếu data membership được đóng trong policy bundle, sự thay đổi quyền ở DB không lập tức có hiệu lực trên mọi sidecar. Nếu truy vấn PIP runtime ở Spring, latency và consistency phụ thuộc nơi kiểm tra. Không vừa cập nhật business record rồi giả định mọi PDP đã nhận dữ liệu.

### 9.1. Rủi ro “quyền trên object ID mới”

Nếu ID tái sử dụng, tuple cấp quyền cho `document:t1-101` có thể áp lên đối tượng mới. Dùng canonical immutable object ID, xóa/reconcile tuples khi delete, và không dùng một raw ID do client chọn làm bằng chứng tenant.

### 9.2. Đối tượng con và list/search

List tài liệu là một luồng đặc biệt:
- ReBAC `ListObjects` có thể tìm object IDs mà user có relation cần thiết.
- OPA có thể hỗ trợ partial evaluation để tạo điều kiện lọc theo dữ liệu nếu integration xây đúng.
- DB query vẫn cần tenant/visibility predicates và áp dụng **permission filter trước pagination/count**.
- Không đơn giản lấy 100 rows rồi gọi 100 lần remote PDP để lọc, vì N+1 latency, page trống và metadata leakage.
- Dùng batch checks, query pushdown, cursor semantics, query cardinality limits và cache khi cần; xác minh thực nghiệm với danh sách lớn.

Một kết quả `ListObjects` **không thay** kiểm tra resource còn tồn tại, chưa soft-delete, thuộc tenant đã xác minh và có action phù hợp tại lúc phục vụ nội dung.

## 10. Vận hành, khả dụng và bảo mật của PDP

### 10.1. Fail-closed theo hành động

Khi OPA/OpenFGA unavailable, response thiếu `result/allowed`, malformed JSON, timeout hoặc model ID sai, quyền nhạy cảm thường phải **DENY**. Không chọn `catch(Exception){return true;}`.

Với endpoint quan trọng, cân nhắc:
- Timeout ngắn và có giới hạn; không để request treo vô hạn.
- Circuit breaker và retry **có ngân sách**; retry storm có thể làm PDP sập thêm.
- Bulkhead/rate limiting, queue và capacity.
- Health/readiness riêng: service không nên chấp nhận traffic nếu không thể enforce policy bắt buộc.
- Fallback chỉ cho **public/read-only** nếu đã chứng minh được quyền offline và không bypass revoke; không áp dụng blanket fallback.
- Metrics phân biệt `DENY_POLICY`, `DENY_UNAVAILABLE`, `DENY_INVALID_RESPONSE` và `DENY_STALE_DATA` để điều hành.

### 10.2. Security của PDP endpoint

OPA HTTP server hoặc OpenFGA API phải nằm trong mạng tin cậy, hạn chế truy cập; sử dụng mTLS/service identity/bearer authentication và least privilege. Đặc biệt, quyền **write policies/tuples** thường nguy hiểm hơn quyền chỉ **query Check**. Không cấp token ghi relationship cho mọi service chỉ để thực hiện read checks.

Store/model IDs của OpenFGA nên được lưu ở cấu hình server có version, không cho client chỉ định một model ID khác để chọn policy dễ hơn. Bundle Rego nên có quy trình ký/xác minh, review và rollback. Secrets không được hardcode trong code/README hoặc quyết định audit logs.

### 10.3. Log quyết định mà không rò dữ liệu

Mỗi decision nên có:
- `correlationId/requestId`, principal ID dạng đã chuẩn hóa.
- tenant và resource canonical IDs, action, policy/model version.
- decision (allow/deny), engine, reason category, latency.
- freshness hoặc consistency preference nếu có.
- Không ghi thẳng JWT, nội dung file, PII nhạy cảm hay raw request body.

OPA có decision logs; ReBAC service cũng có telemetry/tracing tùy triển khai. Kết hợp với application audit để chứng minh **PEP đã thực sự chặn** target method, không chỉ “PDP có trả deny”.

### 10.4. Rollout không đổi quyền bất ngờ

Dùng:
1. Shadow evaluation: PDP mới đánh giá nhưng chưa enforce, so sánh kết quả với policy cũ.
2. Diff phân loại: old allow/new deny, old deny/new allow, lỗi dữ liệu, timeout.
3. Security review **đặc biệt với old deny → new allow**.
4. Canary vài route/tenant; dùng feature flag phía server và pinned model version.
5. Rollback kế hoạch rõ ràng; kiểm tra cache và tuple/model state.
6. Sau khi ổn định mới chuyển đường thực thi, theo dõi deny/error rate và revoke lag.

**Shadow mode không có nghĩa cho phép**: quyết định thực vẫn phải tuân policy cũ đáng tin cho tới khi cutover.

## 11. Bộ tiêu chí đánh giá POC trước khi chọn

Một POC có thể dùng bộ tình huống sau:

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| P01 | Owner đọc tài liệu ACTIVE đúng tenant, quan hệ hợp lệ, OPA allow | Allow |
| P02 | User khác tenant được thử với header giả | Deny |
| P03 | Member cùng tenant nhưng không được share | Deny |
| P04 | Group membership cấp quyền gián tiếp | Allow nếu policy cho phép |
| P05 | Quyền folder thừa xuống tài liệu con | Allow đúng inheritance model |
| P06 | Tài liệu CONFIDENTIAL, relationship allow nhưng OPA deny | Deny |
| P07 | Tài liệu archived/deleted, hai PDP allow | Deny tại baseline |
| P08 | Revoke tuple, kiểm tra lại ngay và sau TTL | Trong SLA revoke |
| P09 | OPA bundle update trên nhiều sidecar | Policy version trong SLA rollout |
| P10 | Sai model ID hoặc relation không tồn tại | Deny + metric lỗi |
| P11 | HTTP timeout/500 từ PDP | Deny, bounded latency |
| P12 | OPA 200 nhưng `result` thiếu | Deny |
| P13 | OpenFGA 200 nhưng `allowed` thiếu hoặc false | Deny |
| P14 | Batch/list 10.000 objects, có pagination/count | Không lộ dữ liệu, đạt P95 |
| P15 | Move object sang tenant khác | Không giữ grant trái phép |
| P16 | Hai service dùng cùng policy version | Quyết định đồng nhất |
| P17 | PDP mất kết nối 5 phút | Không fail-open |
| P18 | Hệ thống ghi tuples/OPA bundles bị từ chối | Chỉ actor được ủy quyền thay policy |

Đặt ngưỡng đo được cho mỗi POC: P95/P99 latency, tỷ lệ lỗi, số queries/query, propagation delay, cache hit/miss, cost, team ownership. Đừng quyết định từ demo “Hello World” chỉ chứa một user và một tuple.

### 11.1. Quy tắc chấm điểm lựa chọn

Một cách làm thực dụng là chấm 1–5 cho:
- Khả năng mô hình hóa use cases hiện tại và dự kiến 12–24 tháng.
- Khả năng chứng minh tenant isolation/revocation.
- Độ tin cậy, latency và resilience khi PDP outage.
- List/search integration và dữ liệu lớn.
- Chi phí triển khai/migration, vận hành và on-call.
- Governance: review, CI tests, policy/model versioning, audit.
- SDK/API/tooling được team hiểu và bảo trì.

Có thể gán trọng số 25% correctness, 20% model fit, 20% operations, 15% performance, 10% integration, 10% cost **như một ví dụ**, nhưng trọng số phải phản ánh rủi ro của tổ chức. Không khẳng định có một bảng điểm “chuẩn” áp dụng mọi sản phẩm.

## 12. Sai lầm phổ biến khi tích hợp

| Sai lầm | Hậu quả | Hướng sửa |
|---|---|---|
| HTTP 200 từ OPA/FGA nghĩa là allow | Missing `result` hoặc `allowed` tạo privilege escalation | Chỉ allow với boolean true chính xác |
| Lấy `tenantId`/`isAdmin` từ body để làm PDP input | Policy đúng trên input giả | PIP phía server, canonical tenant |
| `OPA.allow OR FGA.allow` cho luật bắt buộc | Bypass rule ở một bên | Baseline AND, policy precedence rõ |
| Dùng ReBAC-only cho dữ liệu có mandatory classification | Bỏ qua compliance guard | Hybrid hoặc condition/guard tương đương |
| Đem mọi nhóm/quan hệ vào JSON OPA mỗi request | Context lớn, staleness và performance | Đánh giá graph store hoặc data sync có cấu trúc |
| Dùng FGA nhưng quên xóa tuples khi xóa resource | Orphan grants/reused ID | Lifecycle/outbox/reconciliation |
| Mọi thứ trong `@PostAuthorize` | Side effect chạy trước deny | `@PreAuthorize`, transaction, guarded DML |
| Remote PDP exception rồi fallback allow | Fail-open khi outage | Explicit fail-closed |
| Cho client chọn policy mode/model ID | Chọn policy yếu hơn | Config server pin phiên bản |
| Bỏ tenant scope vì FGA đã có relationship | Cross-tenant leak nếu tuple sai | Canonical DB tenant + membership baseline |
| OPA bundle hoặc FGA model update không được test | Quyền đổi bất ngờ | CI policy/model tests, canary |
| Cache không phân tenant/action/version | Cross-user/tenant stale allow | Cache key chuẩn và revoke invalidation |
| ListObjects trả IDs rồi bỏ qua DB scope | Lộ deleted/foreign-tenant objects | Recheck canonical visibility |
| Một API list gọi PDP cho từng row sau paging | N+1, sai page/total | Batch/query pushdown/filter trước paging |
| Không có test hai PDP xung đột | Không phát hiện hybrid bypass | Matrix allow/deny/error |
| Tự gọi method trong bean (self-invocation) | `@PreAuthorize` bị bỏ qua | Spring proxy/AspectJ phù hợp |
| Quyền write tuple chung với quyền check | Dễ tự cấp quyền khi service bị chiếm | Least privilege tokens |

## 13. Checklist thiết kế và triển khai

- [ ] Định nghĩa subject–action–resource–context; ownership và tenant canonical.
- [ ] Xác định những điều kiện nào là mandatory deny, không thể bypass bằng admin/OR.
- [ ] Đếm thực tế loại quan hệ/group/inheritance so với luật theo thuộc tính/ngữ cảnh.
- [ ] Quyết định OPA, ReBAC hay hybrid dựa trên use case, POC và SLA, không chỉ theo tên công nghệ.
- [ ] PEP tại `SecurityFilterChain` hoặc Spring-managed service; mọi entry point được bảo vệ.
- [ ] Authentication và PIP đáng tin; không cấp permission từ header/body client.
- [ ] Tenant membership và resource tenant được xác minh trước hoặc cùng PDP decision, không chỉ từ client.
- [ ] PDP input/response có schema/version, missing/unknown => deny.
- [ ] OPA dùng `{"input":...}` và đọc `result === true`; test trường hợp undefined.
- [ ] ReBAC dùng user/relation/object có model ID rõ, tuple lifecycle và identity canonical.
- [ ] Hybrid composition có precedence, fail-closed và negative tests chứng minh.
- [ ] Policy/model/tuple update có audit, review, CI, version pinning và rollback.
- [ ] Có giới hạn timeout/retry/circuit breaker, TLS và secrets/least privilege giữa services.
- [ ] Có plan consistency/cache/revoke SLA khi kết quả cần phản ánh tức thì.
- [ ] Có đồng bộ business DB ↔ relationship store (outbox/reconciliation) không giả định distributed transaction.
- [ ] ListObjects, search, count và export có tenant/permission predicates đúng trước paging.
- [ ] Ghi decisions với correlation ID và policy/model version, redact thông tin nhạy cảm.
- [ ] Benchmark P50/P95/P99, error rate, memory, graph depth và cost.
- [ ] Test full matrix allow/deny/mismatch/error, không chỉ mock port.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Ứng dụng cho phép share folder cho nhóm và kế thừa quyền tới hàng nghìn documents. OPA hay ReBAC là lựa chọn ban đầu hợp lý?

**Trả lời:** ReBAC (ví dụ OpenFGA) thường là lựa chọn tự nhiên vì quan hệ/group/inheritance là abstraction lõi. Vẫn phải đo performance, quyền tenant và truy vấn list thực tế.

**Câu 2.** Một hệ thống có nhiều luật clearance, thời gian giao dịch, risk score và compliance; không chia sẻ đối tượng nhiều. Nên bắt đầu ở đâu?

**Trả lời:** OPA/Rego hoặc một policy-as-code engine cùng nhóm thường phù hợp hơn; cân nhắc PIP data freshness, bundle distribution và test.

**Câu 3.** FGA Check trả `allowed=true` nhưng OPA trả `result=false` cho tài liệu CONFIDENTIAL. Hybrid AND ra quyết định gì?

**Trả lời:** Deny. Relationship là điều kiện cần nhưng không vượt mandatory classification rule.

**Câu 4.** OPA Data API trả HTTP 200 với body `{}`. Có nên allow không?

**Trả lời:** Không. `result` không tồn tại có thể do document/rule undefined. Chỉ boolean true chính xác mới cho phép.

**Câu 5.** Revoke một tuple rồi gọi Check với `MINIMIZE_LATENCY`. Tại sao có thể thấy quyền cũ?

**Trả lời:** Nếu cache đang bật và còn TTL, API có thể dùng cached response. Cân nhắc `HIGHER_CONSISTENCY` cho đường cần freshness, nhưng vẫn xem consistency giữa business DB và FGA.

**Câu 6.** Hai port PDP đều trả allow cho document ở t2 nhưng user chỉ thuộc t1. Service có được trả dữ liệu không?

**Trả lời:** Không. Baseline tenant membership và canonical tenant boundary phải deny trước khi PDP trở thành cơ sở cấp quyền.

## 15. Tài liệu chính thức và gợi ý đọc tiếp

- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): custom `AuthorizationManager<RequestAuthorizationContext>`, ví dụ tích hợp Open Policy Agent và thứ tự matchers.
- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, policy bean và giới hạn proxy.
- [OPA — Tổng quan và tích hợp](https://www.openpolicyagent.org/docs): separation of policy decision vs enforcement, Rego và cách gọi OPA.
- [OPA — REST Data API](https://www.openpolicyagent.org/docs/rest-api): `POST /v1/data/{path}`, `{"input":...}`, `result` và undefined result.
- [OPA — Rego v1](https://www.openpolicyagent.org/docs/policy-reference/keywords/import): cú pháp `if` và `import rego.v1` ở các version cũ.
- [OpenFGA — Concepts](https://openfga.dev/docs/concepts): model, type, relation, tuple và Check.
- [OpenFGA — Perform a Check](https://openfga.dev/docs/getting-started/perform-check): `POST /stores/{store_id}/check`, `authorization_model_id` và `allowed`.
- [OpenFGA — Parent-Child Objects](https://openfga.dev/docs/modeling/parent-child): quyền trên folder/project có thể ảnh hưởng quyền trên child tùy model.
- [OpenFGA — Query Consistency Modes](https://openfga.dev/docs/interacting/consistency): `MINIMIZE_LATENCY`, `HIGHER_CONSISTENCY`, cache và latency trade-off.
- [OpenFGA — Conditional Tuples](https://openfga.dev/blog/conditional-tuples-announcement): hỗ trợ điều kiện trên relationship.
- [OWASP API Security Top 10 — BOLA](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): object-level authorization và ID do client lựa chọn.

**Kết luận:** Chọn **OPA** khi trọng tâm là luật theo thuộc tính/ngữ cảnh được quản trị như code; chọn **ReBAC** khi trọng tâm là quan hệ user–group–resource, chia sẻ và kế thừa; chọn **hybrid** khi cần cả discretionary graph grants lẫn mandatory contextual guard. Dù dùng PDP nào, **Spring Security phải enforce**, dữ liệu đầu vào phải đáng tin, tenant/resource phải được xác minh, lỗi phải fail-closed và cần kiểm thử cả policy, model, data sync lẫn tích hợp HTTP thực tế.