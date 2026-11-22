# Audit, truy vết thay đổi và phát hiện thao tác bất thường

Một quản trị viên mở dashboard của hệ thống bán hàng rồi sửa hạn mức giảm giá cho một nhà cung cấp. Một lúc sau, nhiều đơn hàng được tạo với mức giảm giá không hợp lệ. Trong MongoDB, bản ghi cấu hình chỉ cho thấy `maxDiscountPercent = 90`. Trong Change Stream, hệ thống thấy một thao tác UPDATE. Nhưng nhóm bảo mật cần trả lời sâu hơn: **ai** đổi giá trị, **đăng nhập qua cách nào**, **đã được cấp quyền hay không**, **thao tác có thành công thật không**, **giá trị trước/sau**, **có xảy ra truy cập hàng loạt bất thường khác không**, và **bằng chứng có đáng tin cậy nếu tài khoản quản trị bị chiếm quyền không?**

Những câu hỏi đó thuộc phạm vi **audit và phát hiện bất thường**. Hệ thống log đơn thuần hoặc CDC không tự trả lời trọn vẹn chúng. Audit cần mô tả cả hành động, danh tính và quyết định phân quyền; theo dõi thay đổi cần liên kết thao tác với phiên bản dữ liệu đã commit; phát hiện bất thường cần biến chuỗi sự kiện thành tín hiệu rủi ro có thể điều tra.

Bài học thuộc chương **Bảo mật dữ liệu**, module **Database No SQL**. Mục tiêu là thiết kế audit trail phù hợp document/key-value/wide-column/graph stores, phân biệt audit với log/trace/CDC, gắn actor và operation tới mutation, bảo vệ tính toàn vẹn của bằng chứng, xây chính sách truy cập và lưu giữ, phát hiện những thao tác bất thường mà không xâm phạm quyền riêng tư hoặc làm chậm hệ thống quá mức.

> **Nguyên tắc xuyên suốt:** Một bản ghi thay đổi cho biết điều gì được viết; một audit event đáng tin cần cho biết ai hoặc hệ thống nào khởi xướng hành động, hành động được đánh giá và thực hiện trong bối cảnh nào, và outcome đã được xác minh đến mức nào.

Các thời hạn lưu, ngưỡng cảnh báo, tên schema và mã lỗi sau đây là **ví dụ thiết kế**, không phải tiêu chuẩn bắt buộc hoặc hướng dẫn pháp lý cho mọi hệ thống. Cấu hình và khả năng audit của mỗi engine còn phụ thuộc phiên bản, bản phân phối, dịch vụ managed và cấu hình thực tế.

## 1. Ba mục tiêu bảo mật của audit

Một hệ audit hữu ích cần:

1. **Accountability — quy trách nhiệm:** Có thể liên kết một hành động với principal đã được xác thực hoặc một service identity đáng tin, trong phạm vi tin cậy đã nêu.
2. **Traceability — truy vết:** Có thể đi từ request/command đến quyết định phân quyền, thao tác ghi, phiên bản dữ liệu và tác động downstream.
3. **Detectability — phát hiện:** Có thể nhận ra một chuỗi truy cập hoặc thay đổi lệch khỏi hành vi được cho phép/bình thường và đưa ra cảnh báo hữu ích.

Còn một mục tiêu bổ sung cực kỳ quan trọng: **evidence integrity**. Nếu kẻ có quyền sửa dữ liệu cũng có quyền xóa mọi audit records, điều tra về thao tác của chính kẻ đó dễ bị phá hủy.

Audit không làm cho hệ thống tự động an toàn. Nó hỗ trợ **ngăn chặn, điều tra, khôi phục và cải thiện kiểm soát**; các biện pháp xác thực, phân quyền, mã hóa, kiểm soát transaction và data minimization vẫn phải có riêng.

## 2. Phân biệt audit, application log, trace, CDC và sự kiện nghiệp vụ

| Nguồn | Câu hỏi chính | Ví dụ | Không tự bảo đảm |
|---|---|---|---|
| **Security audit** | Ai làm gì, trong phạm vi nào, được phép không, outcome gì? | `role.grant.denied`, `order.export.allowed` | Toàn bộ state trước/sau nếu không thiết kế |
| **Application log** | Service gặp lỗi/tình huống nào? | `db.timeout`, `cache.miss` | Actor/action có giá trị làm bằng chứng |
| **Distributed trace** | Request chậm/hỏng ở bước nào? | API → Redis → MongoDB | Log bất biến và đầy đủ mọi thao tác |
| **CDC/change stream** | Storage đã có mutation nào? | UPDATE orders/101 | Ý nghĩa nghiệp vụ và actor thực sự |
| **Business/domain event** | Fact nghiệp vụ nào đã được công nhận? | `OrderCancelled` | Identity, lý do phân quyền, nguồn đăng nhập |
| **Version history** | Dữ liệu đổi qua những phiên bản nào? | v8 → v9 | Ai đã đổi nếu không có trusted attribution |

Một hành động có thể tạo nhiều tín hiệu. Không đồng nhất **một CDC record = một audit event = một business event**.

## 3. Câu hỏi điển hình khi điều tra

Với một lần đổi cấu hình quyền giảm giá, điều tra viên có thể hỏi:

- User hoặc service account nào khởi xướng?
- Identity đến từ session, access token hay vai trò được ủy quyền?
- Nếu admin thao tác thay người khác, ai là người gốc, ai là người được đại diện?
- Tài nguyên thuộc tenant nào? Phạm vi quyền lúc đó?
- Phương thức/API/action nào đã được gọi?
- Quyết định authorization là allow hay deny, dựa trên policy/version nào?
- Request có qua validation không?
- Mutation có commit thành công không, hay client chỉ gửi request?
- Giá trị/phiên bản trước và sau là gì, trong phạm vi dữ liệu được phép giữ?
- Có request liên quan cùng correlation ID hay trace ID?
- Có thay đổi cấu hình, đăng nhập mới, export hàng loạt trước đó không?
- Audit record có bị sửa, mất, đến muộn hoặc lưu sang nơi không được phép không?

Câu trả lời đầy đủ cần **nhiều lớp dữ liệu có liên kết**, không chỉ một dòng text.

## 4. Lớp audit nào ghi hành động nào?

Có thể chia thành:

| Lớp | Nguồn sự kiện | Ví dụ |
|---|---|---|
| Identity/authentication | Identity provider, gateway | Login success/failure, MFA change |
| Authorization | API/policy engine | Allow/deny read, role grant |
| Application/domain | Business handler | Order cancelled, price override |
| Data access | API/repository, database audit nếu có | Sensitive document read/export |
| Storage mutation | Database CDC, write history | UPDATE/DELETE commit |
| Administration/operations | Control plane, cloud/IAM | Backup export, audit policy disabled |
| Telemetry integrity | Collector, audit backend | Queue gap, integrity verification failure |

Không nhất thiết log tất cả GET theo từng document nếu quá lớn; phải phân loại **đọc dữ liệu nhạy cảm, download/export, thay đổi quyền, truy cập đặc quyền** và nghĩa vụ của từng loại. Ngược lại, một DELETE tài khoản không nên chỉ được ghi vào INFO log rồi có thể bị sampling bỏ mất.

## 5. Một chuỗi request có nhiều kết quả khác nhau

~~~text
1. API nhận DELETE /documents/{id}.
2. Xác thực token.
3. Đánh giá quyền DELETE.
4. Kiểm tra document version và business invariants.
5. Ghi mutation vào database.
6. Database commit hoặc trả lỗi/timeout.
7. Trả response.
8. CDC phát thay đổi ra stream sau commit.
~~~

Những trường hợp phải phân biệt:

- **Authentication denied:** principal chưa được xác thực.
- **Authorization denied:** principal có identity nhưng không có quyền.
- **Validation rejected:** có quyền gọi action nhưng business rule không cho phép.
- **Write conflict:** expected version không còn đúng.
- **Commit success:** mutation được xác nhận bền theo consistency/durability contract.
- **Outcome unknown:** request timeout và client chưa biết commit xảy ra hay chưa.
- **Downstream propagation pending:** state đã commit nhưng search/cache chưa nhận change.

Một audit `document.deleted` không nên xuất hiện chỉ vì server **nhận được** DELETE command. Nếu không biết kết quả commit, ghi `outcome=UNKNOWN` rồi đối soát, không tự gọi thành công/thất bại.

## 6. Sơ đồ kiến trúc nhiều nguồn bằng chứng

~~~mermaid
flowchart TD
    CLIENT["Client / service"] --> AUTH["Authentication"]
    AUTH --> AZ["Authorization policy"]
    AZ --> HANDLER["Command handler"]
    HANDLER --> DB["NoSQL authoritative state"]
    HANDLER --> OUTBOX["Committed audit/outbox record"]
    AUTH --> SEC["Security audit events"]
    AZ --> SEC
    DB --> CDC["Change Stream / CDC"]
    OUTBOX --> RELAY["Audit relay / broker"]
    SEC --> COL["Secure collector"]
    RELAY --> COL
    CDC --> CORR["Correlate source changes"]
    COL --> STORE["Restricted audit store"]
    CORR --> STORE
    STORE --> RULES["Anomaly detection"]
    RULES --> CASE["SOC / incident case"]
~~~

Điểm quan trọng:

- **Phát audit ở lớp hiểu identity/authorization** nếu cần quy trách nhiệm.
- **Ghi bằng chứng commit gắn mutation** nếu cần chứng minh thay đổi đã được áp dụng.
- **Dùng CDC kiểm tra mutation/source version** nhưng không tự suy actor.
- **Tách nơi lưu audit khỏi quyền sửa dữ liệu nghiệp vụ**.

## 7. Actor phải đến từ nguồn đã xác minh

Một trường nguy hiểm:

~~~json
{
  "actorId": "admin-1",
  "source": "HTTP header X-User-Id from client"
}
~~~

Client có thể tự gửi header khác. Audit không được coi nó là identity đáng tin.

Thay vào đó:

~~~text
Gateway/IdP xác thực token hoặc mTLS principal.
API xác minh issuer, audience, signature, expiry và policy.
Handler nhận trusted principal trong server-side security context.
Audit builder lấy actor từ context đó.
```

Không phải mọi hệ dùng JWT; có thể dùng session, service identity, workload identity, IAM hoặc certificate. Điểm chung là **actor attribution phải dựa trên identity đã được kiểm chứng tại trust boundary phù hợp**, không dựa vào tham số người dùng tự khai.

## 8. Human actor, service actor và delegated action

Một operation có thể có:

~~~json
{
  "actor": {
    "type": "SERVICE",
    "id": "billing-reconciler"
  },
  "onBehalfOf": {
    "type": "USER",
    "id": "operator-17"
  },
  "delegationReason": "approved-support-ticket"
}
~~~

Các khái niệm:

- **Initiating principal:** người/service khởi phát chuỗi.
- **Executing principal:** danh tính thực hiện thao tác tại DB/API.
- **Delegated principal:** được ủy quyền hợp lệ trong phạm vi cho phép.
- **Impersonation/break-glass:** tình huống đặc biệt phải có audit riêng.

Nếu backend kết nối MongoDB qua một service account chung, database chỉ thấy `order-service`, không tự biết người dùng cuối. Muốn biết người dùng, ứng dụng phải **ghi attribution đã xác thực** và bảo vệ mối liên kết với DB mutation.

## 9. Tenant và authorization scope là dữ liệu quan trọng

Audit event có thể ghi:

~~~json
{
  "tenantScope": "tenant-42",
  "resourceType": "Order",
  "action": "order.refund",
  "decision": "DENY",
  "policyId": "refund-policy",
  "policyVersion": "2026-11"
}
~~~

Nhưng tenant ID cũng có thể là thông tin khách hàng/định danh doanh nghiệp. Phải hạn chế quyền xem, phân vùng audit theo tenant hoặc token hóa nếu phù hợp.

Không dùng `tenantId` từ HTTP body làm căn cứ duy nhất. Quyết định authorization phải ràng buộc **principal, allowed tenant scope và resource owner** một cách đáng tin.

## 10. Event audit dạng cấu trúc

Một envelope minh họa:

~~~json
{
  "auditEventId": "aud-2f8c...",
  "schemaVersion": 2,
  "eventType": "data.update.committed",
  "occurredAt": "2026-11-14T10:03:00Z",
  "recordedAt": "2026-11-14T10:03:01Z",
  "actor": {
    "type": "USER",
    "subjectToken": "sub-tok-17",
    "authnMethod": "MFA"
  },
  "tenantScope": "tenant-42",
  "service": "order-api",
  "action": "order.discount.override",
  "resource": {
    "type": "DiscountPolicy",
    "idToken": "resource-tok-3"
  },
  "authorization": {
    "decision": "ALLOW",
    "policyId": "discount-override",
    "policyVersion": "v12"
  },
  "outcome": "COMMITTED",
  "change": {
    "beforeVersion": 7,
    "afterVersion": 8,
    "changedFieldPaths": ["maxDiscountPercent"]
  },
  "correlationId": "checkout-control-551",
  "traceId": "9b0f...",
  "sourceCommitRef": "source-opaque-834"
}
~~~

Đây là **schema ứng dụng tự thiết kế**, không phải format chuẩn của MongoDB, DynamoDB hay OpenTelemetry.

## 11. Audit field nào bắt buộc?

| Field | Vai trò | Lưu ý |
|---|---|---|
| auditEventId | Identity ổn định khi relay/replay | Dedup |
| schemaVersion | Giải mã lâu dài | Khác data version |
| eventType/action | Phân loại hành động | Danh mục được kiểm soát |
| actor/source | Quy trách nhiệm | Phải có trust level/provenance |
| tenant/resource scope | Xác định đối tượng | Có thể nhạy |
| outcome | Allowed, denied, committed, failed, unknown | Không suy từ request được gửi |
| occurredAt/recordedAt | Timeline | Clock skew |
| authorization context | Policy decision | Không lưu raw token |
| before/after version | Mutation ordering | Trong scope aggregate |
| changed field paths | Tìm vùng tác động | Cân nhắc dữ liệu nhạy |
| correlation/trace ID | Ghép chuỗi dịch vụ | Không phải proof of actor |
| source commit ref | Ghép với dữ liệu | Opaque, phụ thuộc engine |

Không nhất thiết mọi event đều phải có tất cả fields. Ví dụ authentication denial chưa có resource version; hãy dùng schema theo event class và đánh dấu trường không có/không biết thay vì bịa dữ liệu.

## 12. Truy vết một thay đổi cần nhiều lớp ID

Một luồng:

~~~text
Request ID: req-551
Command ID: cmd-551
Audit Event ID: aud-551
Aggregate: order-101
Aggregate version: 12 -> 13
Database transaction reference: tx-opaque-A
CDC position: resume-token-B
Trace ID: trace-551
~~~

Những IDs này có mục đích khác nhau:

- Request ID định danh HTTP attempt, có thể đổi khi retry.
- Command/idempotency ID định danh ý định logic.
- Audit event ID định danh bằng chứng cụ thể.
- Aggregate version cho ordering cùng entity.
- CDC cursor giúp resume stream.
- Trace ID giúp quan sát request path.

**Không lấy broker offset hoặc request ID làm business operation ID** nếu một logical action có thể retry và tạo nhiều attempts.

## 13. Hai loại audit event: attempted và committed

Một thiết kế thực tế thường tách:

**Audit attempt/decision:**

~~~json
{
  "eventType": "data.delete.attempted",
  "outcome": "AUTHORIZATION_DENIED",
  "actor": {"type": "USER", "subjectToken": "sub-17"},
  "resourceType": "Order",
  "recordedAt": "2026-11-14T10:00:00Z"
}
~~~

**Audit mutation commit:**

~~~json
{
  "eventType": "data.delete.committed",
  "outcome": "COMMITTED",
  "actor": {"type": "USER", "subjectToken": "sub-21"},
  "resourceType": "Order",
  "resourceVersion": 8,
  "recordedAt": "2026-11-14T10:00:01Z"
}
~~~

Attempt event cho biết hành động được yêu cầu/đánh giá; committed event cho biết source đã công nhận mutation. Nếu luôn chỉ ghi successful events, ta sẽ bỏ mất dấu hiệu enumeration hoặc privilege probing.

## 14. Truy vết trước/sau không nhất thiết cần lưu cả document

Một audit change:

~~~json
{
  "resourceType": "DiscountPolicy",
  "beforeVersion": 7,
  "afterVersion": 8,
  "changes": [
    {
      "path": "maxDiscountPercent",
      "oldValue": 15,
      "newValue": 90
    }
  ]
}
~~~

Có thể hữu ích khi field không nhạy và cần điều tra giá trị cụ thể.

Nhưng với:

~~~text
users.email
users.passwordHash
payments.cardMetadata
documents.privateNote
```

không nên lưu nguyên values theo mặc định. Có thể giữ **field path, change type, safe value bucket, source version, classification, hash/token** hoặc một restricted evidence store riêng nếu thực sự cần.

**Không để audit trở thành bản sao đầy đủ của dữ liệu khách hàng với retention dài hơn database chính.**

## 15. Phân biệt PATCH, state snapshot và business history

Một change record có thể là:

~~~text
PATCH: status -> CANCELLED
~~~

Nhưng để tái dựng state, ta cần biết:
- State khởi đầu.
- Đủ mọi changes.
- Thứ tự trong cùng aggregate.
- Semantics của DELETE/replace.
- Schema evolution.
- Các bước manual repair.

Audit stream chỉ ghi một số hành động nhạy cảm có thể **không đủ** làm event sourcing history. Ngược lại business event history có thể **thiếu thông tin authorization**.

Không thiết kế một log duy nhất làm mọi vai trò nếu contract không thực sự đáp ứng.

## 16. Ghi audit cùng mutation bằng atomic boundary

Hai API calls liên tiếp:

~~~text
UPDATE order state -> DB COMMIT.
INSERT audit log -> một storage khác.
~~~

Nếu process crash giữa hai bước, dữ liệu thay đổi mà audit mất.

Đảo thứ tự cũng có vấn đề: audit ghi đã thành công trong khi state rollback.

Một pattern tốt cho sự kiện **mutation committed** là:

~~~text
Một transaction hoặc atomic unit:
  update authoritative state
  insert committed audit/outbox record
commit
```

Sau đó relay chuyển audit record tới kho bảo mật. Điều kiện: engine và data model **thực sự cho phép atomic unit này**. Nếu không, phải có protocol reconcile/verify thay vì giả định hai writes ở hai hệ tự atomic.

## 17. Ví dụ MongoDB transaction và audit outbox

Ví dụ minh họa Node.js:

~~~javascript
async function changeDiscount(db, client, input, principal) {
  const session = client.startSession();
  const eventId = input.stableAuditEventId;

  try {
    await session.withTransaction(async () => {
      const result = await db.collection("discountPolicies").updateOne(
        {
          _id: input.policyId,
          tenantId: principal.authorizedTenantId,
          version: input.expectedVersion
        },
        {
          $set: { maxDiscountPercent: input.newPercent },
          $inc: { version: 1 }
        },
        { session }
      );

      if (result.matchedCount !== 1) {
        throw new Error("VERSION_OR_SCOPE_CONFLICT");
      }

      await db.collection("auditOutbox").insertOne(
        {
          _id: eventId,
          schemaVersion: 1,
          eventType: "discountPolicy.updated.committed",
          actorToken: principal.serverVerifiedSubjectToken,
          tenantScope: principal.authorizedTenantId,
          resourceId: input.policyId,
          oldVersion: input.expectedVersion,
          newVersion: input.expectedVersion + 1,
          changedFields: ["maxDiscountPercent"],
          outcome: "COMMITTED"
        },
        { session }
      );
    });
  } finally {
    await session.endSession();
  }
}
~~~

Đây là **khung minh họa**, chưa bao gồm toàn bộ authentication/authorization/validation. Cần:
- Kiểm quyền bằng trusted principal **trước** transaction.
- Kiểm giới hạn giá trị và business rules.
- Stable event ID/idempotency key, uniqueness.
- Xử lý commit outcome UNKNOWN và retry.
- Không gửi email hoặc tác động ngoài DB trong retryable callback.
- Dùng topology/driver/write concern phù hợp transaction.
- Cân nhắc sự khác biệt `matchedCount` và `modifiedCount`.

Nếu cần log authorization denial, sự kiện **denied attempt** phải được ghi qua đường audit thích hợp ngay cả khi business transaction không bắt đầu.

## 18. Idempotency của audit relay

Timeline:

~~~text
1. DB commit state + auditOutbox aud-900.
2. Relay publish aud-900.
3. Broker ACK mất.
4. Relay publish lại aud-900.
5. Consumer nhận hai copies.
~~~

Consumer nên có inbox/dedup theo logical `auditEventId` cùng scope, hoặc storage constraint idempotent. Nếu lưu hai bản giao lại mà không đánh dấu duplicate, report có thể đếm thành hai hành động.

Cần phân biệt:
- **Hai attempts khác nhau** của cùng một command: có thể là hai attempt audit facts.
- **Một committed mutation event bị truyền hai lần:** vẫn là một fact.
- **Hai mutations có commit riêng:** phải có hai facts, không gộp nhầm chỉ vì cùng actor.

Không tự hứa exactly-once delivery xuyên database, broker và audit backend.

## 19. Điều gì xảy ra nếu commit outcome UNKNOWN?

Giả sử client nhận timeout khi commit:

~~~text
Command sent.
Network timeout.
Không biết DB đã commit chưa.
```

Audit attempt có thể ghi `outcome=UNKNOWN` hoặc `COMMIT_UNCONFIRMED`. Sau đó dùng operationId/version/outbox ID để đối soát.

Nếu chỉ retry với event ID mới và giả định lần trước thất bại, có thể tạo nhiều mutations hoặc nhiều audit facts sai.

Phải xác định:
- Idempotency key có ổn định không?
- Mutation có kiểm expected version không?
- Outbox record có unique ID không?
- Có thể query operation outcome sau timeout?
- Ai chịu trách nhiệm reconcile unknown records?

## 20. CDC bổ sung nhưng không thay audit actor

Ví dụ CDC:

~~~json
{
  "operation": "UPDATE",
  "collection": "discountPolicies",
  "documentKey": {"_id": "policy-7"},
  "updatedFields": {"maxDiscountPercent": 90}
}
~~~

CDC biết document thay đổi. Nó không biết **human user** nếu nguồn chỉ thấy service credential, cũng không biết một thay đổi có được phê duyệt trong workflow hay không.

Tránh ghép actor vào CDC bằng cách “lấy HTTP request gần timestamp nhất”: hai requests có thể đồng thời, clock lệch và background job có thể sửa cùng document.

Nếu cần correlation chắc chắn, producer phải lưu **operationId, trusted actor context và version** theo một protocol có ranh giới xác nhận rõ.

## 21. MongoDB audit và Change Streams không phải cùng sản phẩm

MongoDB có cơ chế audit cho một số bản phân phối/phiên bản/cấu hình, hỗ trợ theo dõi các loại hoạt động/authorization theo phạm vi của feature. MongoDB Change Streams lại phản ánh **data changes** theo semantics của stream.

Cần kiểm:
- Edition/deployment hỗ trợ audit tính năng nào.
- Event types, cấu hình filter và quyền truy cập.
- Có ghi authentication, authorization, DDL/admin activities không.
- Metadata source thực sự có fields nào.
- Độ đầy đủ của audit khi crash/restart.
- Overhead và storage retention.
- Change Streams có updateDescription/full document/pre-image theo option nào.

**Không khẳng định bật Change Streams là đã bật security audit** hoặc rằng audit log mặc nhiên chứa before/after đầy đủ của mọi document.

## 22. DynamoDB Streams và IAM audit context

DynamoDB Streams có thể cung cấp item changes với key và old/new images theo stream view type.

Nhưng stream record về UpdateItem không tự chứa human identity và quyết định IAM của caller theo contract ứng dụng.

Trong kiến trúc AWS, các control-plane/data-plane audit capabilities như CloudTrail có scope và cấu hình riêng cần kiểm theo loại event, region, policy và dịch vụ. Không tự suy tất cả data operations luôn được thu không cần bật cấu hình.

Để có truy vết domain:
- Dùng stable operationId và verified principal ở API.
- Ghi audit intent/record trong transaction scope nếu được engine hỗ trợ.
- Dùng Streams chuyển changes hoặc outbox items.
- Phân biệt TTL deletions và customer-initiated deletions theo metadata/contract, không tự suy chỉ từ DELETE.
- Bảo vệ IAM, stream consumer và audit sink riêng.

## 23. Cassandra audit logging và giới hạn phân vùng

Apache Cassandra có khả năng audit logging tùy phiên bản/cấu hình và công cụ đi kèm; các hệ phân phối có thể khác nhau. Cần kiểm loại request được ghi, username/roles, truy vấn và thông tin parameters có thể nhạy.

Điểm cần nhớ:
- Ứng dụng có thể dùng service account chung, nên DB không biết actor cuối.
- Một nghiệp vụ denormalize dữ liệu vào nhiều tables/partitions.
- Audit query không tự là business commit event xuyên nhiều partition nếu transaction boundary không hỗ trợ.
- Truy vấn/partition keys có thể chứa PII.
- Retention và hiệu năng audit logging cần được đo.
- Các operations mang tính repair/maintenance có thể tạo I/O không phải business actions.

Nếu muốn audit nghiệp vụ, ghi actor/tenant/operation tại lớp service đáng tin với cơ chế persist/recovery phù hợp.

## 24. Redis: ACL, Slow Log và MONITOR

Redis có các cơ chế khác nhau:
- ACL/configuration kiểm soát quyền các commands.
- ACL-related logs có thể hỗ trợ phát hiện một số authentication/authorization failures.
- Slow Log giúp phân tích commands chậm.
- MONITOR hỗ trợ quan sát commands nhưng có overhead/rủi ro dữ liệu.
- Keyspace notifications thông báo thay đổi key theo semantics riêng, không phải durable audit trail.

Không coi Redis MONITOR, Slow Log hoặc keyspace notifications là nguồn chứng minh đầy đủ ai đã thay đổi giá trị nghiệp vụ. Tên keys/arguments có thể chứa user identifiers hoặc tokens, nên cần tối thiểu hóa và giới hạn quyền.

Muốn quy trách nhiệm một cache invalidation nhạy cảm, ứng dụng có thể ghi audit theo **loại thao tác và verified actor/service**, thay vì log raw Redis key.

## 25. CouchDB revisions và _changes

CouchDB có document revisions và `_changes` feed hỗ trợ đồng bộ dữ liệu, nhận biết updates/deletions theo semantics của engine.

Nhưng:
- Một revision ID không tự cho biết user cuối.
- `_changes` không tự chứng minh authorization decision.
- Concurrent revisions/conflicts có thể cần policy ứng dụng.
- Purge khác logical document deletion.
- Cursor/sequence không phải business timestamp toàn cục.

Để theo dõi chỉnh sửa tài liệu có trách nhiệm, cần **trusted actor attribution ở lớp API**, operation/version context và quyền truy cập vào audit evidence, không chỉ dựa vào `_rev`.

## 26. Audit trong graph/document/key-value khác nhau về granularity

Ví dụ:
- Document DB: thay một document gồm nhiều fields.
- Key-value: overwrite một value dạng byte array.
- Wide-column: ghi vào partition/rows denormalized.
- Graph: thêm/xóa edge quan hệ giữa hai entities.

Một business fact như “thu hồi quyền truy cập” có thể:
- UPDATE ACL document.
- DELETE edge user→resource.
- DELETE cache key.
- Gửi invalidation event.

**Đừng đếm bốn mutations làm bốn lần thu hồi quyền.** Audit theo business action và lưu các source change refs cần thiết để đối soát.

## 27. Data version và ordering giúp dựng timeline

Một aggregate:

~~~text
Policy p-7:
  v7 maxDiscountPercent=15
  v8 maxDiscountPercent=90
  v9 maxDiscountPercent=20
~~~

Audit nên gắn version 7→8 và 8→9 thay vì chỉ dựa trên timestamp.

Khi events đến muộn:
- Event v9 tới trước v8 ở consumer.
- Có thể sắp xếp lại trong cùng aggregate nếu sequence/version đáng tin.
- Không tự suy total order trên mọi tenants và regions.
- Missing version có thể là dấu hiệu audit gap hoặc event chưa giao, cần reconcile.

Dùng per-aggregate monotonic version hoặc một nguồn thứ tự có contract rõ. Không dùng wall-clock time làm bằng chứng thứ tự tuyệt đối khi có clock skew.

## 28. Các mốc thời gian không đồng nhất

~~~text
requestReceivedAt
authorizationDecidedAt
sourceCommittedAt
auditRecordedAt
collectorReceivedAt
auditPersistedAt
anomalyAlertedAt
~~~

Các timestamp khác nhau vì queue, retry, network lag và scheduler.

Nếu principal ở region A thao tác lúc 10:00:01 và region B lúc 10:00:00 theo clock khác, không thể tự khẳng định thứ tự bằng timestamp.

Cần:
- Clock synchronization và theo dõi drift.
- Store source version/transaction ref.
- Record ingest lag.
- Phân biệt event time và processing time.
- Nêu độ tin cậy thời gian trong báo cáo điều tra.

## 29. Audit completeness: có bằng chứng rằng không bị thiếu không?

Các lỗ hổng:
- Application crash trước khi gửi audit.
- DB commit nhưng outbox write không atomic.
- Collector drop khi queue đầy.
- Broker retention hết trước consumer catch-up.
- Audit sink reject ingest.
- Admin tắt logging.
- Direct DB access bypass application.
- Một replica bị mất hoặc stream cursor hết hạn.

Một hệ không thể chứng minh “mọi thao tác đã được ghi” chỉ bằng cách nhìn có một số events.

Cần **coverage inventory**, checkpoint/sequence, gap detection, reconciliation với state/CDC/admin logs, health monitoring và kiểm tra cấu hình audit.

## 30. Tamper resistance khác tamper evidence

**Tamper resistance:** làm khó sửa/xóa dữ liệu audit trái phép:
- Write-only/append-only ingestion.
- Separate IAM roles.
- Immutable/WORM storage khi phù hợp.
- Retention lock/versioning và access audit.
- Network isolation, encryption.

**Tamper evidence:** nếu records bị sửa hoặc xóa, có thể phát hiện:
- Hash chaining.
- Signed batches/checkpoints.
- Externally anchored digests.
- Integrity verification và alert.

Một hệ có thể dùng cả hai. **Append-only ở application API chưa đủ** nếu cùng admin có quyền xóa underlying files hoặc thay retention policy.

## 31. Hash chain khái niệm

Cho mỗi partition được định nghĩa có event sequence \(e_i\):

\[
h_i=H(h_{i-1}\,\Vert\,\operatorname{Canonical}(e_i))
\]

Trong đó:
- \(H\): hàm băm mật mã phù hợp.
- \(h_{i-1}\): hash trước trong chain.
- Canonical: serialization ổn định, không phụ thuộc thứ tự JSON keys.
- \(\Vert\): phép nối byte.

Nếu đổi nội dung một event, chain hashes sau đó sẽ không khớp nếu verifier giữ được reference root đáng tin.

Nhưng một attacker có toàn quyền sửa toàn bộ store có thể **tính lại toàn chain**. Vì vậy cần anchor/hash root trong hệ độc lập, chữ ký với keys được bảo vệ hoặc immutable checkpoints theo threat model.

## 32. Hash chaining không bảo đảm bí mật hoặc completeness tuyệt đối

Hash chain cho thấy sự thay đổi sau khi ký/anchor nếu verification đúng; nó **không tự**:
- Mã hóa dữ liệu.
- Chứng minh actor đúng nếu event ban đầu là giả.
- Chứng minh không có operation nào bị bỏ qua trước khi ghi.
- Giải quyết clock skew.
- Tạo global total order giữa partitions.
- Thay authorization và audit access controls.

Nếu nhiều ingest partitions chạy song song, có thể cần hash chains theo partition và periodic signed manifest roots. Nên ghi rõ sequence scope, canonical format và anchor cadence.

## 33. Chữ ký và chứng cứ độc lập

Một batch audit có thể:
1. Đóng sequence range và content hash.
2. Tạo Merkle root hoặc chained digest.
3. Ký bằng key nằm ngoài quyền của application data admin.
4. Ghi signed manifest vào immutable store khác.
5. Định kỳ verify manifests và phát alert nếu thiếu/sai.

Khóa ký phải được quản lý vòng đời, rotation, quyền sử dụng và audit. Không đưa private signing key vào app log hoặc source repository.

**Bằng chứng tốt phải chịu được giả định một phần hệ đã bị compromise**, không chỉ chạy đúng khi mọi thành phần trung thực.

## 34. Bảo vệ audit store khỏi quyền sửa business data

Quy tắc phân quyền ví dụ:

| Principal | Business DB | Audit store |
|---|---|---|
| Order service | Read/write scope cho orders | Append vào ingest channel |
| Business DB admin | Maintenance có giới hạn | Không có delete/alter audit |
| Audit relay | Read outbox + publish | Append-only, không xóa |
| SOC investigator | Read audit theo case/scope | Không sửa/xóa |
| Audit administrator | Quản lý pipeline lifecycle | Thay policy qua approval/audit |
| Privacy team | Thực thi deletion theo policy | Có workflow kiểm soát |

Phân tách nhiệm vụ (separation of duties) làm giảm nguy cơ một tài khoản có thể **vừa sửa dữ liệu, vừa xóa bằng chứng**. Audit về thay quyền audit store cần gửi thêm tới nơi độc lập.

## 35. Fail-open, fail-closed và audit criticality

Một bài toán:
> Nếu audit sink unavailable, có nên từ chối cập nhật hạn mức chuyển tiền?

Phải phân loại:
- **Telemetry thông thường:** thường fail-open với bounded queue nếu không ảnh hưởng business invariant.
- **Audit bắt buộc của thao tác nhạy cảm:** có thể cần fail-closed hoặc durable local/transactional record trước khi xác nhận operation.
- **Emergency break-glass:** có thể cần workflow thay thế được phê duyệt, ghi evidence và review.

Không chọn một policy chung cho mọi log. Một ứng dụng không nên block mọi GET chỉ vì DEBUG exporter gặp lỗi. Ngược lại, một operation được quy định bắt buộc có audit evidence không thể âm thầm thành công nếu không ghi được evidence.

## 36. Kênh ghi audit phải kiểm soát tải và sự cố

Các rủi ro:
- Too many audit events gây bão ingest.
- Broker queue đầy hoặc retry kéo dài.
- Disk spool giữ PII không mã hóa.
- Collector crash tạo gaps.
- Synchronous logging chặn thread phục vụ traffic.

Cơ chế:
- Classify priority/criticality.
- Bounded queues và retry budgets.
- Durable storage cho mandatory audit.
- Metrics generated/accepted/persisted/dropped.
- Encryption và retention cho local spool.
- Circuit breaker/controlled degraded modes theo policy.
- Alert khi backlog age vượt SLA.
- Không sample/drop audit critical tùy tiện.

## 37. Dữ liệu nhạy cảm trong audit

Audit có thể chứa:
- User ID, email, IP, device info.
- Tenant/resource ID.
- Old/new field values.
- Permission and role assignments.
- Query/search patterns.
- Attachment/document metadata.

Thiết kế data minimization:
- Không ghi password/token/private key.
- Ghi subject token hoặc identity reference có quyền thay vì raw PII khi đủ.
- Ghi changed field paths/versions hơn full document.
- Chỉ ghi trước/sau cho fields thật sự cần điều tra.
- Dùng restricted evidence store cho dữ liệu nhạy phải giữ.
- Tránh dán raw audit JSON vào tickets/chat công khai.

**Audit có retention dài phải cẩn trọng hơn log ngắn**, không ít hơn.

## 38. Pseudonymization không mặc nhiên là anonymization

Có thể dùng token do mapping service phát hoặc HMAC:

~~~text
subjectToken = HMAC(secretKey, tenantScope || ":" || principalId)
```

Lợi ích: correlation theo một principal mà không lộ ID gốc trực tiếp.

Giới hạn:
- Token ổn định vẫn cho phép liên kết hành vi.
- Plain hash email/phone dễ bị dictionary attack.
- Mapping/secret key cần được bảo vệ.
- Token rotation có thể ảnh hưởng khả năng truy vết nhiều năm.
- Quy định privacy có thể vẫn coi đó là dữ liệu cá nhân.

Không lưu secret key hoặc token mapping trong cùng hệ người điều tra có quyền xem rộng.

## 39. Audit retention theo data class

Ví dụ minh họa:

| Audit class | Mục đích | Hướng retention |
|---|---|---|
| Auth failures | Phát hiện probing/credential misuse | Theo threat window/policy |
| Privileged role changes | Quy trách nhiệm thay quyền | Lâu hơn nếu có compliance obligation |
| Data changes | Đối soát thay đổi nhạy cảm | Theo business/legal requirement |
| Sensitive reads/exports | Điều tra truy cập trái phép | Theo risk classification |
| Low-risk operational logs | Debug và SLO | Ngắn hơn audit records |
| Incident evidence | Lưu chứng cứ liên quan vụ việc | Case-based hold và review |

Không có một số ngày “đúng cho tất cả”. Retention phải xét luật/khu vực, data class, khả năng điều tra, chi phí, legal hold, cách xóa và quyền chủ thể dữ liệu.

## 40. Retention thật bao gồm nhiều bản sao

~~~text
Audit hot search index.
Immutable archive.
Collector disk spool.
Broker topic.
Backup/snapshot.
Incident case export.
SIEM copy.
DR replica.
```

Xóa khỏi dashboard **không có nghĩa đã xóa toàn bộ**. Legal hold có thể có nghĩa phải giữ một số bằng chứng; privacy requirements có thể yêu cầu xóa/hạn chế những fields khác. Cần owner và quy trình được phê duyệt.

Để giảm xung đột, ngay từ đầu tránh đưa PII không cần thiết vào audit long-term store.

## 41. Phát hiện bất thường là bài toán dữ liệu theo chuỗi

Một action đơn lẻ có thể hợp lệ:
- Admin đọc 20 đơn hàng.
- Một role được cấp quyền.
- User đăng nhập ở thiết bị mới.
- Service account truy cập bảng nhiều lần.

Nhưng chuỗi:
~~~text
1. Đăng nhập từ bối cảnh chưa từng thấy.
2. Cấp quyền export cho tài khoản mới.
3. Truy cập số lượng lớn documents.
4. Tạo nhiều downloads trong vài phút.
~~~

có thể đáng điều tra.

**Anomaly detection không tự kết luận có tấn công.** Nó tạo **tín hiệu rủi ro cần xác minh** theo context nghiệp vụ và quyền đã được cấp.

## 42. Các nhóm hành vi cần quan sát

| Nhóm | Dấu hiệu |
|---|---|
| Authentication | Nhiều failures, MFA reset bất thường, session reuse không phù hợp |
| Authorization probing | Nhiều DENY trên resources ngoài scope |
| Privilege escalation | Role grant/policy change ngoài quy trình |
| Data exfiltration risk | Truy cập/export nhiều records nhạy trong thời gian ngắn |
| Unusual mutation | Bulk DELETE/UPDATE trên nhiều tenants, thay policy nhạy |
| Credential/service misuse | Service account gọi API không thuộc chức năng |
| Data integrity risk | Thay đổi tài chính/quyền bất thường hoặc rollback ngoài workflow |
| Audit evasion | Logging disabled, retention shortened, integrity mismatch |
| API abuse | Rapid enumeration, repeated invalid resource access |
| Operational misuse | Backup export hoặc restore ngoài lịch/phê duyệt |

Không mặc nhiên coi mọi hoạt động khối lượng cao là xấu. Import/migration hợp lệ cũng có thể tạo cùng dấu hiệu. Nên liên kết **change ticket, maintenance window, owner và approval**.

## 43. Phát hiện dựa trên quy tắc

Ví dụ yêu cầu:
> Alert nếu một principal bị từ chối truy cập hơn 20 resources khác nhau trong 5 phút.

Pseudocode khái niệm:

~~~text
for each audit event:
  if action = sensitive_read and outcome = AUTHORIZATION_DENIED:
    add (principalToken, resourceToken, timestamp) to bounded window

every minute:
  for each principalToken:
    distinctDeniedResources = count_distinct(last 5 minutes)
    if distinctDeniedResources >= configuredThreshold:
       raise candidate alert with safe metadata
```

Quy tắc cần:
- Event time vs ingest time.
- Late arrivals/retries/dedup.
- Per-tenant scope.
- TTL của cửa sổ.
- Tránh cardinality/memory không giới hạn.
- Suppression khi principal đã được xác nhận trong test/incident diễn tập.
- Xử lý service accounts có lưu lượng khác humans.

Ngưỡng 20/5 phút **chỉ là ví dụ**, phải hiệu chỉnh bằng baseline thực.

## 44. Tính distinct resources quan trọng hơn đếm log thô

Một API retry cùng request 50 lần có thể tạo 50 DENY events, không nhất thiết là 50 resource enumeration attempts.

Nên phân biệt:
- Unique logical commands.
- Unique resources.
- Unique tenants.
- Distinct endpoints.
- Authenticated principals vs untrusted network sources.
- Retry attempts được xác định.

Nếu cần đếm unique resources, nguồn phải cung cấp **stable resource token** trong phạm vi truy vấn an toàn; không gắn raw resource ID thành metric label cho mọi request.

## 45. Bulk export và đọc bất thường

Ví dụ:
~~~text
Actor bình thường đọc 50 records/ngày.
Hôm nay actor đọc 10.000 sensitive records trong 10 phút.
```

Cần lưu:
- Export action, dataset/tenant scope.
- Number of records/bytes **theo bucket hoặc aggregate**.
- Policy decision.
- Actor classification và device/session context an toàn.
- Approval/ticket nếu có.
- Baseline theo role/service/time window.

Không nhất thiết ghi toàn bộ 10.000 record IDs vào audit event; có thể dùng manifest được lưu trong restricted evidence store khi cần, với retention/authorization phù hợp.

## 46. Privilege changes là dấu hiệu rủi ro cao

Các action nên có audit riêng:
- Assign/revoke roles.
- Grant admin/export/backup permissions.
- Modify access policy.
- Disable MFA/rotate credentials.
- Create service account/token.
- Modify audit logging configuration.
- Change tenant ownership.

Một policy hợp lý có thể gửi cảnh báo nhanh khi:
- Actor cấp quyền mà không có approval.
- Role change trùng với login bất thường.
- Tài khoản đặc quyền vừa tạo đã export dữ liệu.
- Nhiều grant/revoke liên tiếp.

Cần có allowlist cho maintenance hợp lệ nhưng không **lặng lẽ loại bỏ mọi admin events**.

## 47. Baseline theo actor, role, tenant và thời gian

Một ngưỡng “>1000 reads/phút” chung có thể:
- Báo giả cho batch ETL hợp lệ.
- Bỏ sót người dùng vốn chỉ đọc 1 document/tuần nhưng đột ngột đọc 500.
- Che một service account khác biệt.

Baseline có thể dùng:
- Role/actor type: user, admin, service.
- Tenant workload size.
- Giờ hoạt động bình thường.
- Endpoint sensitivity.
- Historical distinct resource count.
- Allowed business workflow.
- Approved maintenance window.

Nhưng baseline có thể bị nhiễm bởi hành vi xấu kéo dài hoặc seasonality. Quy tắc detection phải có **phương án giám sát drift và review**, không tự động tin mọi thống kê quá khứ là an toàn.

## 48. Risk scoring không thay analyst judgment

Một mô hình điểm minh họa:

~~~text
+40: unauthorized export attempt.
+30: privilege grant without ticket.
+20: access from previously unseen device.
+20: bulk read exceeds baseline.
-30: approved maintenance workflow.
```

Cộng điểm có thể ưu tiên điều tra, nhưng:
- Trọng số không phải xác suất bị compromise.
- Một dấu hiệu có thể bị lặp/double-count.
- Thiếu dữ liệu có thể làm điểm thấp sai.
- Baseline có thể thiên lệch với các nhóm nhỏ.
- Một legitimate action có risk score cao vẫn cần xác minh.

Đừng tự động khóa toàn bộ khách hàng chỉ vì điểm máy học/tổng số vượt ngưỡng; quyết định tự động phải theo policy và có cơ chế review phù hợp.

## 49. Detection rule theo chuỗi sự kiện

~~~mermaid
flowchart LR
    LOGIN["Unusual login context"] --> PRIV["Privilege changed"]
    PRIV --> EXPORT["Sensitive export"]
    EXPORT --> ALERT["Risk alert / investigation"]
    APPROVAL["Change ticket / approval"] --> ALERT
~~~

Những sự kiện có thể đến ở thứ tự khác nhau do ingest lag. Hãy dựa vào event time, correlation/identity tokens và quan hệ causality đáng tin; không ghép hai actor chỉ vì cùng IP nếu NAT/shared network.

Một trace ID có thể giúp ghép request path, nhưng **không phải identity token** và không chứng minh quyền.

## 50. False positive, false negative và alert fatigue

**False positive:** Cảnh báo hoạt động hợp lệ, ví dụ data migration đã duyệt.

**False negative:** Không cảnh báo hoạt động thực sự trái phép, ví dụ kẻ xấu đọc chậm dưới ngưỡng mỗi phút.

Theo dõi:
- Precision của alerts được điều tra.
- Detection coverage theo attack/abuse scenarios.
- Time-to-detect/time-to-triage.
- Số alerts trùng/dedup.
- Suppression rules và expiration.
- Rule version và reasons.
- Cases không có đủ context để kết luận.

Không giảm alert noise bằng cách xóa toàn bộ loại sự kiện nhạy cảm khỏi audit source. Cần **tuning detection layer** đồng thời giữ evidence theo policy.

## 51. Alert phải tránh lan dữ liệu nhạy cảm

Không gửi:
~~~text
USER person@example.com exported rows:
full names, addresses, payment identifiers...
```

Nên:
~~~json
{
  "alertType": "sensitive_export_spike",
  "severity": "HIGH",
  "actorToken": "sub-tok-17",
  "tenantScopeToken": "tenant-tok-9",
  "datasetClass": "customer-profiles",
  "recordCountBucket": "10k-50k",
  "windowMinutes": 10,
  "caseLink": "restricted-investigation-link"
}
~~~

Đường link phải kiểm quyền. Email/chat/alert platform cũng là bản sao dữ liệu có retention riêng.

## 52. Chống chính hành vi tắt audit

Một administrator hoặc attacker có thể thử:
- Disable audit pipeline.
- Thay config lọc để bỏ admin events.
- Rút ngắn retention.
- Xóa broker topic/archive.
- Sửa clock.
- Tạo service principal bypass gateway.
- Tăng sample/drop rate.
- Gỡ integrity checks.

Các thay đổi này phải được ghi **qua đường audit độc lập hoặc điều khiển có phân quyền**, cùng health monitoring:
- Config change attestation.
- Dual approval cho thao tác quan trọng.
- Immutable copy/signed checkpoints.
- Alert khi event rate đột ngột về 0.
- Periodic coverage test.

Sự vắng mặt của log **không chứng minh hệ thống không có thao tác**.

## 53. Audit coverage và event loss metrics

| Metric | Câu hỏi |
|---|---|
| audit_events_generated | Service sinh bao nhiêu event? |
| audit_events_committed | Bao nhiêu event bền ở source/outbox? |
| audit_events_exported | Relay xuất bao nhiêu? |
| audit_events_persisted | Backend nhận bền bao nhiêu? |
| audit_gap_count | Có thiếu sequence/operation ref? |
| audit_delivery_lag | Event mất bao lâu tới sink? |
| audit_queue_oldest_age | Backlog đang già tới đâu? |
| audit_integrity_failures | Hash/signature verify có lỗi? |
| authz_deny_rate | Có probing bất thường? |
| privileged_action_rate | Nhóm hành động nguy cơ cao thay đổi? |
| sensitive_export_bytes | Khối lượng dữ liệu nhạy được xuất? |
| detector_alerts_by_rule | Quy tắc nào quá nhiễu? |
| detector_false_positive_reviews | Tuning có hiệu quả? |
| audit_config_changes | Có thay đổi coverage/retention? |

Metrics không được gắn actorId/orderId/traceId thành label vô hạn; dùng các dimensions đã kiểm soát hoặc truy vấn ở hệ audit có quyền.

## 54. Số liệu ingest, storage và chi phí audit

Nếu hệ tạo 1.000 audit events/giây, mỗi event 1 KB thập phân:

\[
1.000\times1\ \mathrm{KB/s}=1\ \mathrm{MB/s}
\]

Một ngày không đổi tải:

\[
1\times86.400=86.400\ \mathrm{MB}\approx86{,}4\ \mathrm{GB/day}
\]

Giữ 90 ngày raw tương đương khoảng:

\[
86{,}4\times90=7.776\ \mathrm{GB}
\]

chưa tính index, compression, replicas, archive, snapshots, ingress/egress và query cost.

**Không giảm toàn bộ audit critical bằng sampling ngẫu nhiên chỉ để giảm phí.** Trước tiên hãy giảm payload không cần thiết, thiết kế retention tiers, loại bỏ duplicate transport và kiểm high-cardinality indexes.

## 55. Audit event classification và retention

Một policy ví dụ:

~~~yaml
dataset: privileged-data-audit
owner: security-platform
classification: restricted
requiredEvents:
  - role.grant
  - role.revoke
  - sensitive.export
  - policy.update
  - audit.config.change
allowedFields:
  - eventType
  - actorToken
  - resourceType
  - tenantScopeToken
  - decision
  - outcome
  - sourceVersion
  - occurredAt
  - recordedAt
  - correlationId
integrity: "append-only plus signed checkpoints"
retention: "approved security/legal schedule"
accessRole: "authorized-investigator"
deletion: "case/legal-hold-aware lifecycle"
~~~

Đây là cấu trúc mô tả minh họa; không phải cấu hình thẳng cho mọi cloud/database. Chính sách cần owner, approver, exception, review date và quy trình kiểm chứng.

## 56. Truy xuất bằng chứng và chain of custody

Khi điều tra, có thể cần:
1. Ghi case ID, investigator, thời điểm và phạm vi thu thập.
2. Xác định các sources: IdP, API audit, DB audit/CDC, control plane, broker.
3. Xuất dữ liệu qua đường được phân quyền, tránh copy tùy tiện.
4. Ghi content digest, file metadata và người nhận.
5. Giữ bản gốc read-only, thao tác trên bản sao phân tích.
6. Ghi mọi lần truy cập/chuyển giao.
7. Xác minh signature/hash checkpoints nếu có.
8. Nêu các gaps, late events, clock uncertainties.
9. Chỉ đưa nhận định phù hợp mức bằng chứng.
10. Hủy/giữ evidence theo retention/legal hold được phê duyệt.

Không có log nào tự “chứng minh pháp lý” nếu nguồn, tính toàn vẹn và quá trình bảo quản không đáng tin.

## 57. Phản ứng sự cố: export bất thường

Tình huống: một service account vừa được cấp quyền export, sau đó đọc hàng trăm nghìn records.

Runbook:
1. Xác minh alert rule/khả năng false positive và change tickets.
2. Bảo toàn audit/context, kiểm gap/integrity.
3. Xác minh principal, session, device/network và IAM changes.
4. Đối chiếu scope dữ liệu đã truy cập/xuất và quyền lúc đó.
5. Cô lập/revoke credentials hoặc tạm ngừng quyền theo chính sách incident response nếu cần.
6. Kiểm các downstream exports, object stores, logs và network egress theo quyền.
7. Đối chiếu source data versions và audit records.
8. Phân loại ảnh hưởng/đối tượng, thực hiện thông báo theo chính sách và pháp luật khi áp dụng.
9. Khôi phục hệ thống an toàn, sửa kiểm soát, rotate keys, tăng detection.
10. Viết báo cáo có timeline, mức độ chắc chắn và bằng chứng.

Không gửi toàn bộ dữ liệu bị truy cập vào alert hoặc ticket để “điều tra nhanh”.

## 58. Phản ứng sự cố: sửa dữ liệu không được phê duyệt

Một policy bị nâng max discount từ 15 lên 90:
1. Kiểm current state và version.
2. Truy ngược audit event v7→v8.
3. Xác nhận actor attribution và policy decision.
4. Kiểm phiên đăng nhập/role change/correlation.
5. Xem CDC và outbox có cùng operation/version không.
6. Kiểm tính toàn vẹn audit store và gaps.
7. Xác định những đơn hàng/side effects bị ảnh hưởng.
8. Phê duyệt correction/rollback theo nghiệp vụ, không viết trực tiếp history giả.
9. Theo dõi consumer/cache/search propagation sau correction.
10. Bổ sung guard/approval cho trường cấu hình nhạy.

**Rollback state không xóa dấu vết thao tác đã xảy ra**; correction nên có event và audit riêng.

## 59. Phản ứng sự cố: audit trail bị thiếu

Ví dụ source có version 11 và 13 nhưng audit committed mutation v12 không được tìm thấy.

Kiểm:
- App có sinh outbox event v12 không?
- Source transaction có dùng chung atomic scope?
- Relay có checkpoint/offset skip không?
- Broker retention có làm mất message?
- Collector có drop/reject không?
- Sink có quá retention hoặc xóa nhầm không?
- Event ID có bị dedup sai không?
- Có direct DB write bypass application không?
- Database repair/migration có thay version không?
- Có audit configuration changes không?

Không tự tạo một “v12 committed by admin” nếu không có bằng chứng. Có thể ghi **reconstruction finding** riêng với provenance và confidence, đồng thời giữ nguyên sự thật rằng audit gốc bị thiếu.

## 60. Truy vết truy cập đọc cũng có giới hạn

Truy cập một document có thể không tạo CDC record vì không có write.

Do đó nếu cần điều tra:
- Ai đọc hồ sơ người dùng?
- Ai xuất báo cáo?
- Ai mở dữ liệu tài chính?
- Ai đã bị từ chối quyền đọc?

cần **data access audit** ở API/query gateway hoặc database feature phù hợp, không thể chỉ đọc CDC.

Nhưng log mọi GET với full resource identifier có thể cực đắt và xâm phạm quyền riêng tư. Nên phân nhóm:
- Sensitive read: event theo yêu cầu.
- Bulk export: audit transaction và aggregate count.
- Ordinary low-risk read: metrics/sampled diagnostics tùy policy.
- Denied access: security event có rate guard và logging contract.

## 61. Direct DB access có thể bypass audit ứng dụng

Một admin hoặc job dùng kết nối trực tiếp tới database thay vì đi qua API:
- API audit không thấy.
- CDC có thể thấy mutation.
- Database audit nếu được bật có thể ghi service/database principal và operation.
- Control plane/IAM logs có thể thấy credential/API usage.

Hệ cần:
- Network/IAM controls ngăn direct access không được phép.
- DB-native audit ở phạm vi khả dụng.
- Service account/privileged identity tách riêng.
- Correlation operation tags nếu có và đáng tin.
- Reconciliation CDC vs application audit.
- Alert khi xuất hiện mutation không có expected audit record.

Không khẳng định mọi mutation không có application audit đều là tấn công: migration/repair được phê duyệt có thể là ngoại lệ, nhưng ngoại lệ phải có dấu vết và ownership.

## 62. Thiết kế test audit cho lỗi và gian lận

| Tình huống | Điều cần chứng minh |
|---|---|
| Unauthorized read/write | Deny event có principal/provenance đáng tin |
| Authorized write commit | Committed audit cùng scope/version |
| Commit rollback | Không phát committed-success giả |
| Commit outcome unknown | Audit unknown và reconcile |
| Crash sau DB commit trước relay | Outbox vẫn có event |
| Relay publish trùng do ACK loss | Không nhân logical audit fact |
| CDC cursor hết hạn | Có rebuild/gap alarm, không skip âm thầm |
| Direct DB admin mutation | DB-native/control-plane audit hoặc gap detection |
| Actor impersonation | Server-side identity, audit delegated context |
| Cross-tenant attempt | Tenant scope/authorization đầy đủ |
| Bulk export spike | Detector alert có context và false positive review |
| Role granted without approval | Alert và audit change ticket |
| Log pipeline down | Failure policy cho critical events |
| Audit admin xóa store | IAM/WORM/signature detect/control |
| Clock skew và out-of-order | Version/sequence thay vì timestamp đơn thuần |
| PII trong payload | Data minimization/redaction test |
| Legal hold/deletion | Retention lifecycle có evidence |
| Replay/retry | Deterministic ID và inbox dedup |

Test kỹ thuật này thuộc bản thiết kế bài học; quá trình QA nội dung file được thực hiện ở bước riêng của workflow sản xuất tài liệu.

## 63. Checklist thiết kế audit theo nhu cầu nghiệp vụ

1. Xác định tài nguyên và thao tác nhạy cảm.
2. Phân loại reads, writes, role/admin actions và failed attempts.
3. Chỉ rõ actor ở trust boundary nào được xác thực.
4. Tách human, service, delegated và break-glass identities.
5. Ghi authorization decision cùng policy/version.
6. Phân biệt attempted, denied, committed, failed, unknown.
7. Dùng version/operationId để liên kết data mutations.
8. Dùng transaction/outbox hoặc recoverable protocol cho committed audit.
9. Dùng CDC để kiểm trạng thái nguồn, không suy identity mù quáng.
10. Thiết kế event ID, dedup, ordering scope và gap detection.
11. Thu changed field paths và safe before/after theo data class.
12. Bảo vệ audit store bằng separation of duties/append-only.
13. Có signed checkpoints/integrity verification theo threat model.
14. Dùng RBAC, encryption, tenant isolation và access audit.
15. Chọn retention/legal hold/deletion policy có owner.
16. Theo dõi audit delivery lag, backlog, drop và policy changes.
17. Xây detection rules, baseline, tuning và alert triage.
18. Diễn tập mất event, compromise admin, export bất thường.
19. Ghi chi phí ingest/index/storage và capacity.
20. Review coverage khi code, schema, RBAC hoặc topology thay đổi.

## 64. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai | Cách hiểu đúng |
|---|---|---|
| CDC là audit | CDC thường thiếu actor/authz context | Kết hợp nguồn có trust |
| Log INFO là bằng chứng bất biến | Có thể drop/xóa/sửa | Tính toàn vẹn và quy trình lưu |
| Request đến là mutation thành công | Validation/commit có thể fail | Phân biệt outcomes |
| Timeout nghĩa DB rollback | Commit outcome có thể unknown | Reconcile |
| Actor ID lấy từ header là đáng tin | Client giả mạo được | Server-verified identity |
| DB service account chứng minh user cuối | Nhiều users dùng chung connection | App-level actor context |
| Một mutation = một business event | Multi-write/denormalization | Audit đúng granularity |
| Timestamp đủ sắp xếp mọi regions | Clock skew/concurrency | Source version/sequence |
| Mọi GET nằm trong CDC | GET không tạo mutation | Data access audit |
| Hash chain ngăn mọi sửa dữ liệu | Attacker có thể tính lại chain | External anchors/signatures |
| Immutable nghĩa dữ liệu bí mật | Integrity khác confidentiality | Encryption/RBAC |
| Append-only API đủ chống DBA | DBA có thể sửa storage | Separation of duties |
| Audit cần full before/after PII | Tăng rò rỉ, khó retention | Data minimization |
| Hash email là ẩn danh tuyệt đối | Dictionary/linkage | Pseudonymization policy |
| Trace ID là principal | Chỉ giúp correlation | Authn/authz riêng |
| Broker offset là audit event ID | Republish đổi offset | Stable logical eventId |
| Publish thành công là consumer đã lưu | Ack/loss/retry | End-to-end confirmation |
| Chỉ ghi thao tác thành công | Mất dấu hiệu probing | Ghi denied attempts quan trọng |
| Audit đầy đủ cho mọi GET là rẻ | Volume cực lớn | Risk-based classification |
| Một ngưỡng chung phát hiện mọi xấu | Baseline khác vai trò | Context/risk scoring |
| Alert chứng minh có tấn công | Có false positives | Investigation workflow |
| Role changes ban đêm luôn xấu | Có maintenance hợp lệ | Approval correlation |
| Im lặng nghĩa không có thao tác | Audit pipeline có thể mất | Coverage/health checks |
| Retention UI là retention toàn hệ | Archive/backup/spool tồn tại | Full lifecycle |
| WORM giữ PII mãi là tốt | Privacy/legal conflicts | Minimize & govern |
| Sample mọi audit 1% để tiết kiệm | Mất sự kiện critical | Priority/retention tiers |
| Một case chỉ cần audit store | IdP/DB/control-plane có bằng chứng khác | Multi-source timeline |
| Rollback xóa được hành vi cũ | Hành động vẫn đã xảy ra | Correction audit |
| Direct DB mutation luôn có API audit | Bypass service | DB/control-plane audit |
| Audit storage down thì mọi API phải chặn | Signal criticality khác nhau | Per-operation failure policy |

## 65. Bài tập thực hành

### Bài tập 1 — Phân biệt năm nguồn

Cho application log, trace span, MongoDB CDC UPDATE, domain event `OrderCancelled`, audit `order.cancel.allowed`. Xác định mỗi nguồn trả lời câu hỏi gì và không thể tự chứng minh điều gì.

### Bài tập 2 — Actor đáng tin

Một endpoint lấy `X-User-Id` từ client rồi ghi actorId trong audit. Phân tích lỗi trust boundary và mô tả nguồn identity phù hợp.

### Bài tập 3 — Service account

Tất cả requests MongoDB đều dùng `order-service`. Làm sao truy ra user/admin thực hiện thao tác mà không giả mạo attribution?

### Bài tập 4 — Attempt vs committed

Một user gửi DELETE, authorization allow nhưng DB transaction rollback. Hãy thiết kế audit events/outcomes không nói sai rằng tài liệu đã bị xóa.

### Bài tập 5 — Authorization deny

User truy cập resource ngoài tenant của mình. Audit cần những fields nào và tránh log dữ liệu nào?

### Bài tập 6 — Envelope schema

Thiết kế audit JSON gồm eventId, schemaVersion, actor, tenant, action, resource, policy decision, outcome, source version, trace/correlation ID. Giải thích nguồn tin cậy cho mỗi field.

### Bài tập 7 — Before/after

Cần audit thay đổi `maxDiscountPercent` và `passwordHash`. Với mỗi field, chọn lưu giá trị, bucket, hash, field path hoặc không lưu và giải thích.

### Bài tập 8 — Truy vết version

Một document qua v7→v8→v9 nhưng events tới collector theo v9, v7, v8. Xây cách trình bày timeline và kiểm missing versions.

### Bài tập 9 — Transactional outbox

Tạo pseudocode MongoDB để UPDATE policy bằng expectedVersion và INSERT auditOutbox trong cùng transaction; xử lý matchedCount=0.

### Bài tập 10 — Unknown commit

Client timeout sau commit. Phải ghi outcome và retry thế nào để không tạo hai audit committed facts?

### Bài tập 11 — Broker duplicate

Relay phát cùng aud-900 hai lần. Thiết kế dedup và phân biệt duplicate transport với hai attempts thật.

### Bài tập 12 — CDC không cho actor

MongoDB Change Stream chỉ có documentKey/updateDescription. Vì sao không được ghép user dựa vào HTTP request gần timestamp nhất?

### Bài tập 13 — MongoDB auditing

Lập danh sách cần xác minh với edition/config/version để biết có ghi authn, authz, DDL, changes hay không. Phân biệt Change Streams với audit logging.

### Bài tập 14 — DynamoDB Streams

So sánh item images với IAM/control-plane/data access audit; làm thế nào liên kết mutation với application actor?

### Bài tập 15 — Cassandra

Một operation ghi ba denormalized tables. Vì sao ba query audit/CDC records không phải ba business operations?

### Bài tập 16 — Redis

Một team muốn dùng MONITOR và keyspace notifications làm audit thay quyền. Phân tích durability, actor identity, overhead và key privacy.

### Bài tập 17 — CouchDB

Document revision thay đổi và xuất hiện trong `_changes`. Vì sao chưa đủ chứng minh người sửa và permission tại thời điểm đó?

### Bài tập 18 — Hash chain

Viết công thức \(h_i=H(h_{i-1}\Vert Canonical(e_i))\); giải thích vì sao cần signed checkpoints/anchors độc lập để chống tính lại toàn chain.

### Bài tập 19 — Separation of duties

Một DBA vừa sửa orders vừa xóa audit store. Thiết kế IAM roles, append-only policy, external anchors và access audit để giảm rủi ro.

### Bài tập 20 — Audit outage

Audit broker unavailable. Phân biệt GET ít nhạy và thao tác cấp admin role bắt buộc audit, đề xuất failure policy có căn cứ.

### Bài tập 21 — Detect unauthorized probing

Thiết kế rule theo principal có 20 denied distinct resources trong 5 phút. Xử lý retries, late events, tenant scopes và false positives.

### Bài tập 22 — Bulk export

Một user đọc 10.000 records trong 10 phút, baseline 50/ngày. Chọn context cần điều tra và cách không ghi 10.000 PII IDs vào alert.

### Bài tập 23 — Privilege chain

Vẽ sequence login mới → grant export role → bulk export. Xác định correlation key và khi nào phải báo SOC.

### Bài tập 24 — Baseline service account

Batch ETL đọc nhiều records theo lịch. Làm sao tránh false positive nhưng vẫn phát hiện export trái phép ngoài lịch?

### Bài tập 25 — Risk scoring

Thiết kế risk score với một số signals. Vì sao số điểm không phải xác suất tấn công và không nên tự khóa tenant chỉ theo điểm?

### Bài tập 26 — Audit gap

Source version tăng v11→v13 nhưng thiếu event v12. Viết runbook kiểm outbox, relay, broker, collector, retention và direct DB write.

### Bài tập 27 — Sensitive data retention

Một audit record chứa email và old/new address được giữ nhiều năm. Đề xuất data minimization, privacy review, restricted evidence store và retention controls.

### Bài tập 28 — Legal hold

Một subject yêu cầu xóa khi audit có legal hold. Thiết kế quy trình phân loại trường giữ/xóa, phê duyệt, verification và evidence.

### Bài tập 29 — Chi phí

1.000 audit events/s, mỗi event 1 KB thập phân, retention 90 ngày. Tính raw GB/ngày và tổng GB trước index/replicas.

### Bài tập 30 — Phát hiện audit bị tắt

Thiết kế alert khi config logging đổi, event rate về 0, integrity checkpoint thiếu hoặc retention bị rút ngắn.

### Bài tập 31 — Incident đổi chính sách giá

maxDiscountPercent đổi từ 15 lên 90. Hãy kết hợp actor audit, authorization policy, state versions, CDC, IdP, change ticket và effects downstream để dựng timeline và sửa sai.

### Bài tập 32 — Chứng cứ và chain of custody

Một incident cần xuất audit logs cho người điều tra. Xây quy trình ghi source, digest, quyền đọc, timestamp, transfer và verification mà không tạo bản sao không kiểm soát.

### Bài tập 33 — Kiến trúc tổng hợp

Một nền tảng có Java services, MongoDB orders, DynamoDB preferences, Cassandra activity, Redis cache và một audit/SIEM backend. Hãy thiết kế:

1. Danh mục thao tác nhạy cảm cần audit.
2. Trusted actor/tenant/authorization context.
3. Audit envelope và event ID schema.
4. Atomic mutation audit/outbox khi khả thi.
5. CDC, database-native audit và control-plane evidence.
6. Tamper-resistant/-evident storage và separation of duties.
7. Data minimization, field classification, retention/legal hold.
8. Rules cho role grants, denied access và bulk exports.
9. Gap/delivery/integrity metrics, replay/reconciliation.
10. Runbook và fault tests cho compromise/collector outage.

### Bài tập 34 — Phê bình thiết kế sai

Một nhóm đề xuất:

~~~text
Dùng MongoDB Change Streams làm toàn bộ audit.
actorId lấy từ HTTP X-User-Id.
Ghi data.deleted ngay khi API nhận DELETE.
Chỉ log các thao tác thành công.
Lưu full document before/after và access token.
Cho DBA xóa audit logs theo nhu cầu.
Dựa vào timestamp để gán mutation cho request.
Dùng broker offset làm audit event ID.
Lấy số lần DENY > 10 là đủ kết luận attacker.
Nếu mất audit cursor thì resume từ latest.
~~~

Hãy chỉ ra từng giả định sai, hậu quả, và viết lại thiết kế có trusted actor, commit evidence, audit completeness, integrity controls, detection triage, privacy và recovery.

---

**Kết luận:** Audit cho NoSQL phải ghi đúng **ai hoặc service nào đã thực hiện hành động, trên tài nguyên/phạm vi nào, quyết định quyền gì, kết quả gì và bằng chứng mutation đã commit đến đâu**. **Application log, trace, CDC, business event và audit record có vai trò bổ sung chứ không thay thế tự động cho nhau.** Muốn truy vết đáng tin phải gắn trusted identity, authorization context, operation ID, source version và ranh giới transaction/outbox; bảo vệ audit evidence bằng phân quyền độc lập, append-only/tamper-evident controls, kiểm gap, retention và privacy. Phát hiện bất thường cần đối chiếu chuỗi login, quyền, truy cập, export, mutation và thay đổi cấu hình audit với baseline/approval, đồng thời tính false positives và xác minh trước khi kết luận. Một hệ audit tốt giúp phát hiện và điều tra sự cố mà **không biến chính kho audit thành nơi lộ dữ liệu cá nhân, điểm mất bằng chứng hoặc nguồn tạo cảnh báo vô nghĩa**.
