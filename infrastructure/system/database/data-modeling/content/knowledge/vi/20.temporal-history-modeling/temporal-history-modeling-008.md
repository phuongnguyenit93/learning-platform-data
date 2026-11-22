# Phân biệt bảng ghi dấu thao tác, lịch sử nghiệp vụ và nhật ký sự kiện

## 1. Ba loại dữ liệu “lịch sử” giải quyết ba câu hỏi khác nhau

Trong module **DATABASE_DATA_MODELING**, mô hình hóa lịch sử không chỉ là thêm một bảng có tên kết thúc bằng **_history**. Khi chuyển yêu cầu nghiệp vụ thành thực thể, quan hệ, khóa, ràng buộc, chỉ mục và lược đồ vật lý, trước hết phải biết **loại câu hỏi quá khứ nào hệ thống cần trả lời**.

Giả sử một khách hàng chuyển gói dịch vụ từ **BASIC** sang **PRO**. Cùng một thay đổi có thể dẫn đến ba câu hỏi:

1. **Ai đã thao tác đổi gói, gọi API nào, lúc nào, kết quả ra sao?** Đây là câu hỏi về **bảng ghi dấu thao tác** (*audit trail*).
2. **Khách có quyền PRO vào ngày 05/03 theo quy tắc nghiệp vụ không?** Đây là câu hỏi về **lịch sử nghiệp vụ** (*business/valid-time history*).
3. **Những sự kiện nghiệp vụ nào đã xảy ra theo trình tự để dẫn đến trạng thái hiện nay?** Đây là câu hỏi về **nhật ký sự kiện** (*domain event log*, có thể làm nguồn cho event sourcing).

Ba loại dữ liệu có thể cùng tồn tại, nhưng **không thể thay thế cho nhau một cách mặc định**.

Ví dụ một bản ghi audit nói “quản trị viên sửa cột plan_code từ BASIC sang PRO vào 10/03” **không cho biết PRO có hiệu lực từ 01/03 hay 10/03** nếu không lưu riêng quy tắc hiệu lực. Một hàng lịch sử ghi **PRO có hiệu lực từ 01/03** không nhất thiết cho biết thao tác đó do quản trị viên nào, qua API nào. Một event **PlanChangeApproved** có thể nói quyết định nâng cấp đã được duyệt, nhưng chưa chắc đã chứng minh dịch vụ cấp quyền thực sự áp dụng quyết định đó thành công.

Bài học thuộc chương **Thời gian và lịch sử**, tập trung vào việc tách rõ mục đích, ngữ nghĩa và trách nhiệm của ba nhóm dữ liệu, rồi chọn cách phối hợp chúng mà không tạo ba “nguồn sự thật” mâu thuẫn.

**Mục tiêu học tập:** người học phân biệt được audit, history và domain events; thiết kế lược đồ và ràng buộc đúng cho từng loại; xử lý tính nguyên tử giữa thay đổi nghiệp vụ với ghi lịch sử; viết truy vấn tương ứng; và nhận ra khi cần bitemporal, CDC, outbox hoặc event sourcing.

## 2. Khái niệm cốt lõi và phạm vi của từng loại

### 2.1. Bảng ghi dấu thao tác — audit trail

**Audit trail** ghi **dấu vết hoạt động hoặc quyết định đã thực hiện trên hệ thống**. Đối tượng cần truy vết thường là **hành động của người dùng, dịch vụ, tiến trình hoặc tài khoản quản trị**.

Một audit record có thể chứa:

- **Ai**: actor_id, actor_type, tài khoản dịch vụ hoặc chủ thể đã được xác thực.
- **Làm gì**: action, operation, command hoặc thay đổi trạng thái.
- **Trên đối tượng nào**: entity_type, entity_id.
- **Khi nào**: accepted_at hoặc recorded_at với nguồn thời gian được định nghĩa.
- **Từ đâu và bằng cách nào**: request_id, trace_id, client_application, nguồn kết nối khi phù hợp chính sách.
- **Trước/sau ra sao**: before/after của các trường được phép ghi hoặc một bản diff có cấu trúc.
- **Vì sao**: reason_code, ticket_id, approval_ref.
- **Kết quả**: thành công, bị từ chối, thất bại, hoặc trạng thái cuối của một tác vụ bất đồng bộ.

Audit phục vụ điều tra, giải trình, phát hiện thao tác không hợp lệ, đối soát quyền và kiểm soát quy trình. Nó có thể là **append-only về mặt nghiệp vụ**, được bảo vệ khỏi sửa/xóa tùy tiện. Tuy nhiên, việc có bảng audit **không tự chứng minh rằng log không thể bị giả mạo**: yêu cầu chống giả mạo phải được triển khai bằng quyền truy cập, tách vai trò, lưu trữ bảo vệ, checksum/chữ ký hoặc cơ chế tương đương tùy mức độ rủi ro.

### 2.2. Lịch sử nghiệp vụ — business history

**Business history** ghi **trạng thái, giá trị thuộc tính hoặc quan hệ được coi là đúng trong một giai đoạn nghiệp vụ**.

Ví dụ:

~~~text
Customer 501, subscription plan:

[2026-01-01, 2026-03-01)  BASIC
[2026-03-01, vô hạn)      PRO
~~~

Nó cho phép truy vấn: **“Ngày 05/03 gói nào có hiệu lực?”** Câu trả lời là PRO, miễn dữ liệu lịch sử phản ánh thông tin đã được xác nhận.

Lịch sử có thể lưu:

- Phiên bản thuộc tính của thực thể, như gói, giá, ngạch nhân sự, trạng thái hợp đồng.
- Phiên bản quan hệ, như nhân viên thuộc phòng nào, người dùng thuộc nhóm quyền nào.
- Khoảng hiệu lực **[valid_from, valid_to)**.
- Nguồn quyết định, phiên bản và các ràng buộc chống chồng lấn.

Nếu cần trả lời thêm **“vào 08/03 hệ thống đã ghi nhận điều gì về ngày 05/03?”**, một trục valid time chưa đủ. Khi ấy cần **lịch sử hai chiều thời gian (bitemporal)** hoặc nguồn sự kiện đầy đủ có thể tái dựng kiến thức hệ thống theo thời điểm.

### 2.3. Nhật ký sự kiện — domain event log

**Domain event log** ghi các **sự kiện có ý nghĩa trong nghiệp vụ**, ví dụ:

- **SubscriptionActivated** — gói dịch vụ được kích hoạt.
- **PlanChangeApproved** — quyết định chuyển gói được phê duyệt.
- **InvoiceIssued** — hóa đơn được phát hành.
- **PaymentCaptured** — khoản thanh toán được ghi nhận thành công.
- **RefundAuthorized** — khoản hoàn tiền đã được chấp thuận.

Một event thường là **sự thật về điều đã xảy ra**, được đặt tên ở thì quá khứ, có danh tính sự kiện, loại sự kiện, phiên bản schema, đối tượng liên quan, thứ tự hoặc version, dữ liệu nghiệp vụ và nguồn phát.

Đối với event sourcing, nhật ký sự kiện là **nguồn sự thật** và trạng thái hiện tại được tính bằng cách replay các event có thứ tự. Nhưng **không phải hệ thống có bảng event nào cũng đang làm event sourcing**. Nếu bảng subscription vẫn là nguồn sự thật và event chỉ được phát để thông báo tới dịch vụ khác, event log đóng vai trò tích hợp hoặc truyền thông nghiệp vụ, không phải nhất thiết là nguồn tái dựng đầy đủ.

### 2.4. Phân biệt thêm với technical log và CDC

Hai cơ chế khác thường bị gọi chung là “lịch sử”:

- **Application/technical log**: ghi stack trace, latency, request, health, lỗi kết nối, metric. Nó giúp vận hành, nhưng thường thiếu ràng buộc đầy đủ và tính bền vững để trả lời lịch sử nghiệp vụ.
- **CDC — Change Data Capture**: ghi nhận thay đổi ở database theo cách hệ quản trị/công cụ cung cấp, thường dựa trên log giao dịch. CDC biết hàng/cột đã đổi, nhưng **không tự biết ý nghĩa nghiệp vụ** của việc đổi đó nếu dữ liệu nguồn không biểu diễn quyết định và ngày hiệu lực.

CDC có thể **vận chuyển** thay đổi để xây lịch sử, đồng bộ kho dữ liệu hoặc tạo event tích hợp. Không nên mặc nhiên gọi mọi bản ghi CDC là domain event: **UPDATE plan_code** khác về ngữ nghĩa với **PlanChangeApproved**.

## 3. Bảng so sánh theo câu hỏi và cam kết dữ liệu

| Tiêu chí | Audit trail | Business history | Domain event log |
|---|---|---|---|
| **Câu hỏi chính** | Ai thao tác gì, khi nào, kết quả? | Giá trị/quan hệ nào đúng vào thời điểm nghiệp vụ B? | Những sự kiện nghiệp vụ nào đã xảy ra, theo thứ tự nào? |
| **Đơn vị dữ liệu** | Một thao tác, quyết định, lần thử hoặc hành vi được quan sát | Một phiên bản giá trị/quan hệ với khoảng hiệu lực | Một sự kiện miền đã được chấp nhận |
| **Trục thời gian thường cần** | Thời gian ghi nhận/thực hiện | Valid time; có thể thêm known time | Thời gian sự kiện, thời gian ghi nhận, stream order |
| **Danh tính/khóa** | audit_id, actor, request/transaction ID | entity_id, version_id, valid_period | event_id, aggregate_id, aggregate_version |
| **Cập nhật/đính chính** | Thường thêm dấu vết mới, không xóa dấu vết cũ | Đóng/chia khoảng; bitemporal nếu phải giữ lịch sử kiến thức | Thêm event sửa/huỷ/bù trừ; replay hoặc projection đổi |
| **Truy vấn điển hình** | Theo actor, action, entity, request, khoảng ghi nhận | As-of B, timeline, temporal join | Theo aggregate, event version, event type |
| **Tự tái dựng trạng thái?** | Không được bảo đảm | Trả trạng thái trong phạm vi được thiết kế | Có thể, **chỉ khi** event đầy đủ và replay deterministic |
| **Chứng minh hành động thực hiện?** | Mục tiêu chính nếu thiết kế đáng tin | Chỉ phản ánh giá trị có hiệu lực | Chứng minh event được chấp nhận; không nhất thiết chứng minh mọi lần thử |
| **Rủi ro điển hình** | Log thiếu, lộ PII/bí mật, kết quả không rõ, bị sửa | Overlap/gap, hiệu lực hồi tố, mất lịch sử cũ | Mất thứ tự, phát lặp, event không đủ payload, replay đổi nghĩa |

**Một thao tác có thể tạo cả ba bản ghi**, nhưng mỗi bản ghi mô hình hóa một khía cạnh khác nhau. Không cần lưu ba bản sao dữ liệu hoàn toàn giống nhau chỉ để “an toàn”. Trái lại, nên xác định **nguồn có thẩm quyền**, trách nhiệm mỗi bảng và cơ chế đối soát.

## 4. Ví dụ xuyên suốt: một quyết định có hiệu lực hồi tố

Giả sử khách hàng **501** đang dùng gói BASIC từ 01/01/2026. Hệ thống phát hành hóa đơn dựa trên quyền lợi gói. Ngày **10/03/2026 lúc 09:00 UTC**, nhân viên CS-17 nhập một quyết định đã được phê duyệt: khách chuyển sang PRO **có hiệu lực từ ngày 01/03**.

Sau đó, ngày 12/03, nhân viên nghiệp vụ phát hiện lý do chuyển gói bị nhập thiếu thông tin và thêm quyết định đính chính phần ghi chú. Ngày hiệu lực của PRO **không đổi**.

### 4.1. Audit ghi dấu thao tác

Một audit record có thể là:

~~~json
{
  "auditId": "audit-001",
  "actorType": "USER",
  "actorId": "CS-17",
  "action": "CHANGE_SUBSCRIPTION_PLAN",
  "entityType": "CUSTOMER_SUBSCRIPTION",
  "entityId": "501",
  "requestId": "req-710",
  "decisionRef": "APPROVAL-77",
  "recordedAt": "2026-03-10T09:00:00Z",
  "outcome": "SUCCEEDED",
  "change": {
    "fromPlan": "BASIC",
    "toPlan": "PRO",
    "effectiveFrom": "2026-03-01"
  }
}
~~~

Audit trả lời **ai thực hiện thao tác**, **đã thao tác gì**, **đối tượng nào**, **căn cứ nào**. Nó không tự định nghĩa toàn bộ timeline gói trong quá khứ nếu trước/sau và khoảng hiệu lực không đầy đủ.

### 4.2. Business history biểu diễn quyền có hiệu lực

Sau thao tác, lịch sử gói theo thông tin mới nhất:

~~~text
Customer 501:
  BASIC: [2026-01-01, 2026-03-01)
  PRO:   [2026-03-01, +∞)
~~~

Với **B = 05/03/2026**, kết quả là **PRO**. Nếu hỏi **“hệ thống đã biết gì vào 08/03 về ngày 05/03?”**, câu trả lời trước thay đổi là **BASIC**, giả sử trước 10/03 hệ thống vẫn ghi nhận BASIC có hiệu lực từ đầu năm. Muốn chứng minh cả hai lát cắt phải lưu **known/system time** hoặc event history đủ để tái dựng.

### 4.3. Event log ghi nhận sự kiện miền

Một domain event:

~~~json
{
  "eventId": "evt-501-2",
  "aggregateType": "SUBSCRIPTION",
  "aggregateId": "501",
  "aggregateVersion": 2,
  "eventType": "PlanChangeApproved",
  "schemaVersion": 1,
  "recordedAt": "2026-03-10T09:00:00Z",
  "decisionRef": "APPROVAL-77",
  "payload": {
    "newPlan": "PRO",
    "validFrom": "2026-03-01"
  }
}
~~~

Event ghi **một sự kiện nghiệp vụ được chấp nhận**, có đủ ngày hiệu lực để bộ dựng projection hiểu quyết định. Nó không nhất thiết chứa actor và toàn bộ ngữ cảnh bảo mật như audit; nếu cần có thể liên kết qua **decisionRef/correlationId**.

### 4.4. Một câu hỏi, ba nơi truy vấn khác nhau

| Người hỏi | Câu hỏi | Nguồn được ưu tiên |
|---|---|---|
| Nhóm tuân thủ | Ai đổi gói lúc 09:00 ngày 10/03, qua yêu cầu nào? | Audit |
| Nhóm tính phí | Gói nào có hiệu lực vào ngày 05/03 theo quyết định hiện được chấp nhận? | Business history |
| Nhóm nền tảng | Những event nào làm trạng thái thuê bao thay đổi theo stream? | Event log |
| Nhóm chăm sóc khách hàng | Khi hóa đơn 08/03 được tạo, hệ thống lúc đó biết gói gì? | Bitemporal/known-time history hoặc replay đáng tin |
| Nhóm điều tra truy cập | Khách có thực sự mở nội dung PRO ngày 06/03 không? | Access log hoặc bằng chứng hành vi riêng |

Dòng cuối đặc biệt quan trọng: **quyền đáng lẽ có hiệu lực** không chứng minh quyền đã được ứng dụng thực sự cấp hoặc khách đã sử dụng dịch vụ. Mỗi câu hỏi cần đúng loại chứng cứ.

## 5. Mô hình audit trail: ghi dấu một hoạt động có thể kiểm chứng

Một audit trail tốt có thể hỗ trợ những truy vấn như:

- “Trong 30 ngày qua, những ai thay đổi giá của sản phẩm 900?”
- “Yêu cầu req-710 đã làm gì và có được chấp nhận không?”
- “Ai cấp quyền ADMIN cho tài khoản X, dựa vào quyết định nào?”
- “Có thao tác xóa hoặc truy cập trái phép nào bị từ chối?”
- “Thay đổi này đã bị hoàn tác bằng thao tác nào?”

Để trả lời, cần **nhật ký có cấu trúc** thay vì chỉ dòng text tự do như “user updated customer”.

### 5.1. Các trường cần cân nhắc

| Nhóm | Trường ví dụ | Lưu ý |
|---|---|---|
| Danh tính thao tác | audit_id, actor_id, actor_type | Người, service account và job có ngữ nghĩa khác nhau |
| Đối tượng | entity_type, entity_id, tenant_id | Bảo vệ truy vấn đa tenant |
| Hành động | action, command_type, outcome | Không dùng một action mơ hồ cho nhiều thao tác |
| Tương quan | request_id, correlation_id, trace_id | Một request có thể sinh nhiều audit record |
| Thời gian | recorded_at, attempted_at | Mốc ghi log khác mốc có hiệu lực nghiệp vụ |
| Nguồn | client_app, operation_source | Tránh lưu bí mật, địa chỉ mạng khi không cần thiết |
| Bằng chứng | before_data, after_data, diff, decision_ref | Chỉ lưu dữ liệu tối thiểu được phép |
| Trạng thái | SUCCEEDED, REJECTED, FAILED | Phải định nghĩa lúc nào trạng thái trở nên cuối cùng |

**Một lần thử thất bại** và **một thay đổi đã commit** là hai đối tượng khác nhau. Nếu ghi audit thành công trong cùng transaction với thay đổi nghiệp vụ, cả hai cùng commit hoặc cùng rollback. Nhưng nếu câu lệnh bị từ chối trước transaction, audit trong transaction bị rollback cũng mất. Để ghi dấu truy cập bị từ chối, có thể cần **security audit stream riêng** ngoài giao dịch nghiệp vụ.

### 5.2. Lược đồ audit minh họa trong PostgreSQL

~~~sql
CREATE TABLE audit_activity (
    audit_id         uuid PRIMARY KEY,
    tenant_id        bigint NOT NULL,
    actor_type       text NOT NULL,
    actor_id         text,
    action_code      text NOT NULL,
    entity_type      text NOT NULL,
    entity_id        text NOT NULL,
    outcome          text NOT NULL
                     CHECK (outcome IN ('SUCCEEDED', 'REJECTED', 'FAILED')),
    request_id       text NOT NULL,
    decision_ref     text,
    diff_data        jsonb,
    recorded_at      timestamptz NOT NULL DEFAULT statement_timestamp()
);

CREATE INDEX ix_audit_entity_time
    ON audit_activity (
        tenant_id, entity_type, entity_id, recorded_at DESC
    );

CREATE INDEX ix_audit_actor_time
    ON audit_activity (
        tenant_id, actor_type, actor_id, recorded_at DESC
    );
~~~

**audit_id** là danh tính record. **request_id** không được áp UNIQUE một cách máy móc: một request có thể gây nhiều thao tác cần audit. **diff_data** chỉ chứa các trường được phép ghi. Không đưa password, access token, khóa bí mật, dữ liệu thẻ thanh toán hoặc thông tin cá nhân vượt mức cần thiết vào audit.

Bảng này thể hiện **cấu trúc dữ liệu**, không tự giải quyết mọi yêu cầu kiểm toán. Nếu đội vận hành có quyền sửa trực tiếp database, cần kiểm soát quyền ghi/xóa, phát audit tới vùng lưu trữ độc lập hoặc cơ chế chống giả mạo phù hợp. Cũng cần xác định liệu **recorded_at** lấy bằng statement_timestamp có đáp ứng yêu cầu phân tích thời gian hay không; nó không phải mốc commit chính xác.

### 5.3. Audit dưới dạng diff phải có ngữ nghĩa

Một diff **fromPlan = BASIC, toPlan = PRO** có thể đúng về thay đổi của cột, nhưng nếu bản ghi gốc được **tái chuẩn hóa**, hai bản cùng giá trị lại có thể đại diện cho hai quyết định khác nhau.

Ví dụ quyết định PRO hồi tố từ 01/03 bị sửa thành PRO từ 05/03; **plan_code không đổi**, chỉ **valid_from** đổi. Audit chỉ so sánh plan_code sẽ bỏ sót một thay đổi quan trọng.

Vì vậy audit phải theo dõi **trường và quyết định mà nghiệp vụ coi là có ý nghĩa**, không chỉ những cột tiện lấy ở DTO. Đối với xóa mềm, nên ghi rõ thực thể chuyển trạng thái DELETED, không đánh đồng với thao tác xóa vật lý.

## 6. Mô hình business history: lưu giá trị đúng theo khoảng hiệu lực

Business history trả lời những câu hỏi khác audit:

- “Ngày 05/03 khách 501 thuộc gói nào?”
- “Giá đã được áp dụng trong kỳ 01/03–31/03 là bao nhiêu?”
- “Ngày 15/02 nhân viên thuộc bộ phận nào?”
- “Hai giá trị có cùng hiệu lực tại một thời điểm hay không?”

Bản ghi cần có **khóa thực thể**, **giá trị phiên bản**, **khoảng hiệu lực**, **nguồn quyết định** và **bất biến chống chồng lấn** theo phạm vi nghiệp vụ.

### 6.1. Dùng khoảng nửa mở

~~~text
[valid_from, valid_to)

BASIC: [2026-01-01, 2026-03-01)
PRO:   [2026-03-01, +∞)
~~~

Ngày 01/03 thuộc PRO, không thuộc BASIC. Khoảng nửa mở tránh phải “trừ một giây” tại biên chuyển đổi và nhất quán cho cả ngày lẫn timestamp nếu kiểu dữ liệu được chọn phù hợp.

Nếu gói được áp dụng theo **ngày tại một thị trường**, **date/daterange** có thể phù hợp. Nếu hiệu lực đến từng thời điểm, cân nhắc **timestamptz/tstzrange** với quy tắc múi giờ rõ.

### 6.2. Lược đồ history với một trục valid time

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE subscription_plan_history (
    plan_version_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id     bigint NOT NULL,
    plan_code       text NOT NULL,
    valid_period    daterange NOT NULL,
    decision_ref    text NOT NULL,

    CONSTRAINT ck_subscription_valid_interval
        CHECK (
            NOT isempty(valid_period)
            AND NOT lower_inf(valid_period)
            AND lower_inc(valid_period)
            AND NOT upper_inc(valid_period)
        ),

    CONSTRAINT ex_subscription_one_plan_at_a_time
        EXCLUDE USING gist (
            customer_id WITH =,
            valid_period WITH &&
        )
);
~~~

Ràng buộc **EXCLUDE** cấm hai phiên bản cùng khách có khoảng valid time giao nhau, vì giả định mỗi khách có tối đa một gói chính vào một ngày. Nếu khách được phép có nhiều loại gói song song (ví dụ BASE và ADDON), phải thêm **plan_kind** hoặc khóa phạm vi thích hợp, thay vì cấm dữ liệu hợp lệ.

**Exclusion constraint bảo đảm tối đa một**, không tự bảo đảm **luôn có một** gói. Nếu lịch thuê bao phải liên tục trong kỳ hợp đồng, cần kiểm tra **gap** so với kỳ hoạt động.

### 6.3. Dữ liệu và truy vấn as-of

~~~sql
INSERT INTO subscription_plan_history (
    customer_id, plan_code, valid_period, decision_ref
)
VALUES
(
    501, 'BASIC',
    daterange(DATE '2026-01-01', DATE '2026-03-01', '[)'),
    'REGISTRATION-501'
),
(
    501, 'PRO',
    daterange(DATE '2026-03-01', NULL, '[)'),
    'APPROVAL-77'
);

SELECT plan_code, decision_ref
FROM subscription_plan_history
WHERE customer_id = 501
  AND valid_period @> DATE '2026-03-05';
-- PRO
~~~

Đây là truy vấn **as-of theo ngày nghiệp vụ B**. Bảng không giữ được câu trả lời “trước lúc quyết định được nhập, hệ thống từng tin gì về ngày B” nếu nó chỉ lưu timeline hiệu lực được chấp nhận mới nhất và không có lớp lịch sử kiến thức.

### 6.4. History của quan hệ cũng cần phiên bản

Nếu một nhân viên được phân công:

~~~text
Employee 42 -- Department A: [01/01, 01/04)
Employee 42 -- Department B: [01/04, +∞)
~~~

thì lịch sử nằm trên **quan hệ Employee–Department**, không chỉ trên cột tên nhân viên. Một nhân viên có thể tham gia nhiều dự án song song, nên ràng buộc chồng lấn phải dựa vào **employee_id + project_id + loại quan hệ** khi phù hợp, thay vì cấm mọi quan hệ đồng thời.

Khi JOIN lịch sử thuộc tính và lịch sử quan hệ, phải kiểm tra cả hai phiên bản **cùng chứa ngày B**. Chỉ JOIN theo ID mà không lọc thời gian có thể ghép những giá trị chưa từng cùng đúng.

## 7. Business history và bitemporal: điều gì đã đúng, điều gì đã được biết?

Một trường hợp dễ nhầm:

- Trước 10/03, hệ thống ghi nhận khách 501 dùng BASIC từ 01/01 đến vô hạn.
- Ngày 10/03, hệ thống nhận quyết định PRO có hiệu lực hồi tố từ 01/03.

Có hai câu trả lời cho **B = 05/03**:

| Thời điểm đánh giá kiến thức K | Kết quả hệ thống từng biết về B = 05/03 |
|---|---|
| K = 08/03 | BASIC |
| K = 12/03 | PRO |

Lịch sử chỉ có **valid_period** theo hiểu biết mới nhất sẽ trả PRO, không còn mô tả đủ rằng hệ thống từng tin BASIC khi 08/03.

**Bitemporal** thêm trục thứ hai **known_period = [known_from, known_to)**:

~~~text
BASIC: valid [01/01, +∞)
       known [01/01 08:00, 10/03 09:00)

BASIC: valid [01/01, 01/03)
       known [10/03 09:00, +∞)

PRO:   valid [01/03, +∞)
       known [10/03 09:00, +∞)
~~~

Hai phiên bản có thể giao nhau theo **valid time** nhưng không giao nhau theo **known time**, vì chúng thuộc hai thời kỳ kiến thức khác nhau.

Phác thảo ràng buộc PostgreSQL đúng về ý tưởng là:

~~~sql
EXCLUDE USING gist (
    customer_id WITH =,
    valid_period WITH &&,
    known_period WITH &&
)
~~~

Nó chỉ từ chối khi hai hàng cùng customer_id chồng nhau ở **cả valid và known period**. Đây là quy tắc khác với một bảng valid-time-only.

**Known time không tự là commit time** nếu ứng dụng quản lý timestamp. Phải định nghĩa mốc ghi nhận và bảo đảm mọi bước đóng/mở khoảng dùng một điểm cắt logic trong cùng transaction. Khi cần chứng minh trạng thái transaction đã commit tại từng thời điểm, yêu cầu cơ chế thời gian hệ thống chặt chẽ hơn.

## 8. Domain event log: mô hình hóa điều xảy ra thay vì thao tác trên cột

Một event tốt có tên diễn đạt **sự kiện miền**:

~~~text
SubscriptionActivated
PlanChangeRequested
PlanChangeApproved
PlanChangeRejected
InvoiceIssued
RefundApproved
~~~

Các sự kiện có ý nghĩa khác nhau:

- **PlanChangeRequested**: khách đã đưa ra yêu cầu, chưa chắc được phê duyệt.
- **PlanChangeApproved**: quyết định được chấp thuận, có thể có ngày hiệu lực tương lai hoặc hồi tố.
- **SubscriptionPlanBecameEffective**: một projection hoặc workflow xác nhận gói đã chuyển trạng thái hiệu lực, nếu đó là sự kiện nghiệp vụ riêng theo mô hình.
- **InvoiceIssued**: chứng từ đã được phát hành, khác với “API gửi yêu cầu tạo hóa đơn”.

Chỉ có tên event không đủ: phải định nghĩa **điều kiện phát**, **payload**, **nguồn thẩm quyền**, **thứ tự**, **idempotency** và **ngữ nghĩa trong trường hợp retry**.

### 8.1. Lược đồ event store minh họa

~~~sql
CREATE TABLE subscription_domain_event (
    event_id          uuid PRIMARY KEY,
    aggregate_id      bigint NOT NULL,
    aggregate_version bigint NOT NULL CHECK (aggregate_version >= 1),
    event_type        text NOT NULL,
    schema_version    integer NOT NULL CHECK (schema_version >= 1),
    event_payload     jsonb NOT NULL,
    decision_ref      text,
    occurred_at       timestamptz,
    recorded_at       timestamptz NOT NULL DEFAULT statement_timestamp(),

    CONSTRAINT uq_subscription_aggregate_version
        UNIQUE (aggregate_id, aggregate_version)
);

CREATE INDEX ix_subscription_event_type_time
    ON subscription_domain_event (event_type, recorded_at);
~~~

**aggregate_version** là thứ tự được xác nhận trong một luồng **aggregate_id**. Nó giúp phát hiện hai writer cùng cố ghi event tiếp theo. **event_id** là định danh sự kiện và có thể dùng cho deduplication. **schema_version** phục vụ tiến hóa payload.

Không gộp **event_id** với **request_id**: một request có thể sinh nhiều sự kiện; ngược lại, một event có thể được gửi qua broker nhiều lần nhưng giữ nguyên event_id. Định nghĩa rõ **occurred_at** và **recorded_at** vì chúng không nhất thiết là cùng mốc hoặc được bảo đảm là commit time.

### 8.2. Ví dụ một chuỗi sự kiện thuê bao

~~~json
[
  {
    "aggregateId": 501,
    "aggregateVersion": 1,
    "eventType": "SubscriptionActivated",
    "schemaVersion": 1,
    "payload": {"plan": "BASIC", "validFrom": "2026-01-01"}
  },
  {
    "aggregateId": 501,
    "aggregateVersion": 2,
    "eventType": "PlanChangeApproved",
    "schemaVersion": 1,
    "payload": {"plan": "PRO", "validFrom": "2026-03-01",
                "decisionRef": "APPROVAL-77"}
  }
]
~~~

Hai event mô tả **điều xảy ra theo stream**, nhưng để dựng đúng lịch sử hiệu lực phải áp dụng quy tắc: khi sự kiện chuyển gói được phê duyệt, giữ BASIC đến trước 01/03 và bắt đầu PRO tại 01/03. Nếu event đến muộn với hiệu lực hồi tố, projection cần chia lại khoảng.

**Event stream và business history là hai biểu diễn khác nhau của tri thức nghiệp vụ**. Stream có thể là nguồn, còn history là projection tối ưu cho truy vấn as-of. Nếu lấy history làm nguồn và event chỉ thông báo, chiều trách nhiệm ngược lại. Phải chọn rõ.

## 9. Khi nào nhật ký sự kiện đủ để tái dựng trạng thái?

**Event sourcing** lưu những event được chấp nhận làm nguồn có thẩm quyền để dựng lại trạng thái. Công thức khái niệm:

~~~text
state_0 = trạng thái khởi tạo đã xác minh

state_1 = apply(state_0, event_1)
state_2 = apply(state_1, event_2)
...
state_N = apply(state_(N-1), event_N)
~~~

Để kết quả đúng, cần đồng thời:

1. **Đầy đủ event** từ một trạng thái nền xác minh tới phiên bản đích.
2. **Thứ tự ổn định** trong phạm vi aggregate hoặc các mối quan hệ cần thiết.
3. **Replay deterministic**: cùng event và cùng version quy tắc tạo cùng kết quả.
4. **Payload có đủ ngữ nghĩa** để tái dựng, không phụ thuộc dữ liệu hiện tại đã thay đổi.
5. **Schema evolution** tương thích với event cũ.
6. **Idempotency** khi event được phát hoặc áp dụng lại.
7. **Cơ chế xử lý correction**: thêm event mới và tái tính projection, không xóa quá khứ không có chứng cứ.

Nếu chỉ ghi các event “PlanChangeApproved” nhưng thiếu event khởi tạo gói, hoặc bỏ event khi hệ thống vận hành lỗi, không thể replay đầy đủ.

### 9.1. Event log khác change-log kỹ thuật

Một change-log nói:

~~~text
UPDATE subscription SET plan = 'PRO' WHERE customer_id = 501
~~~

Câu này không trả lời **vì sao** được đổi và **PRO hiệu lực từ khi nào** nếu thiếu thông tin quyết định. Domain event:

~~~text
PlanChangeApproved(
    customerId=501,
    newPlan=PRO,
    validFrom=2026-03-01,
    decisionRef=APPROVAL-77
)
~~~

có ngữ nghĩa nghiệp vụ rõ hơn. Cũng cần lưu ý **một event đã xảy ra** không tự đảm bảo mọi tác dụng phụ đã thành công: ví dụ PlanChangeApproved không chứng minh email thông báo đã được giao thành công. Muốn biết kết quả gửi email, cần event/trạng thái của quá trình gửi riêng.

### 9.2. Snapshot chỉ tăng tốc replay

Nếu event stream có hàng triệu event, có thể lưu **snapshot sau version N** để dựng nhanh trạng thái N+K. Snapshot không thay thế phần event sau N và không tự đảm bảo trạng thái tại một timestamp tùy ý nếu không có ánh xạ thời gian sang phiên bản.

Cần định nghĩa **snapshot_version**, chọn bản nền **<= target_version**, replay các event trong khoảng **(base_version, target_version]** và kiểm tra event không thiếu.

## 10. Cùng một quyết định nên ghi những gì ở đâu?

Với thao tác nâng gói của khách 501, dữ liệu có thể đi qua các thành phần:

~~~mermaid
flowchart TD
    A["Lệnh đổi gói + quyết định đã duyệt"] --> B["Transaction nghiệp vụ"]
    B --> C["Trạng thái/lịch sử gói có hiệu lực"]
    B --> D["Audit thao tác thành công"]
    B --> E["Outbox event cần phát"]
    E --> F["Worker/broker phát sự kiện"]
    F --> G["Projection, email, báo cáo"]
~~~

Mũi tên biểu diễn luồng logic; **transaction** phải có phạm vi thực tế rõ. Ví dụ nếu cả history, audit thành công và outbox nằm cùng PostgreSQL database, có thể ghi chúng **nguyên tử trong một transaction**. Email hoặc một database dịch vụ khác thường không nằm trong cùng transaction đó; cần giao thức gửi lại, idempotency và đối soát.

### 10.1. Giao dịch chuẩn với history làm nguồn sự thật

Một phương án phổ biến:

1. Nhận lệnh **ChangePlan** với **command_id** và thông tin phê duyệt.
2. Xác thực quyền, phiên bản hiện tại và ngày hiệu lực.
3. Khóa phạm vi khách/gói để tránh hai lệnh cạnh tranh ghi timeline.
4. Đóng/chia khoảng valid-time history và chèn các phiên bản phù hợp.
5. Chèn audit record **SUCCEEDED** cùng định danh request/decision.
6. Chèn **outbox event** với payload đã kiểm chứng.
7. Commit chung.
8. Outbox publisher phát event, đánh dấu tiến trình và retry khi cần.
9. Consumer xử lý idempotent; đối soát projection nếu phát bị chậm.

Mọi lần thử bị từ chối do chưa có quyền có thể được ghi sang **security audit** ngoài transaction thay đổi trạng thái, nếu yêu cầu bảo mật cần giữ cả các attempt thất bại.

**Cần tránh double write:** không commit history ở database A rồi gửi trực tiếp event tới broker B với giả định “chắc chắn cả hai cùng thành công”. Có thể database commit nhưng broker không nhận; hoặc broker nhận rồi transaction rollback. Transactional outbox giúp giải quyết khoảng hở giữa commit DB và phát thông điệp, nhưng consumer vẫn cần xử lý trùng.

### 10.2. Lược đồ outbox tối thiểu

~~~sql
CREATE TABLE domain_outbox (
    outbox_id    uuid PRIMARY KEY,
    aggregate_id bigint NOT NULL,
    event_type   text NOT NULL,
    payload      jsonb NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT statement_timestamp(),
    published_at timestamptz,
    attempts     integer NOT NULL DEFAULT 0 CHECK (attempts >= 0)
);

CREATE INDEX ix_domain_outbox_pending
    ON domain_outbox (created_at)
    WHERE published_at IS NULL;
~~~

Một event có thể được broker nhận thành công nhưng worker mất kết nối trước khi cập nhật **published_at**; nó sẽ bị phát lại. Đây là lý do consumer cần deduplicate theo event_id/outbox_id. Không mặc định có **exactly-once end-to-end** chỉ vì bảng outbox tồn tại.

Khi hệ thống chọn **event store là nguồn sự thật**, transaction có thể lưu event và audit tương ứng, rồi các projection business history được dựng bất đồng bộ. Khi đó API phải công bố **độ trễ projection** và có cơ chế rebuild; không nên coi bảng projection là một nguồn thẩm quyền thứ hai cạnh tranh với event store.

## 11. Những lần thao tác thất bại có cần ghi lại không?

Đây là chỗ audit và event log khác nhau rõ rệt.

Giả sử người dùng không có quyền gửi lệnh chuyển gói:

- **Audit bảo mật** có thể ghi **attempted action**, actor, đối tượng, request, lý do bị từ chối và thời điểm, theo chính sách bảo mật.
- **Business history** không có phiên bản gói mới, vì quyết định không được chấp nhận.
- **Domain event log** thường **không có PlanChangeApproved**. Có thể có một event riêng **PlanChangeRejected** nếu việc từ chối là sự kiện miền cần xử lý và đã được nghiệp vụ chấp nhận, nhưng không phải mọi lỗi xác thực đều là domain event.

Khi một tác vụ bất đồng bộ kéo dài nhiều phút, trạng thái **SUBMITTED**, **APPROVED**, **APPLIED**, **FAILED** có thể là các giai đoạn khác nhau. Audit không nên ghi **SUCCEEDED** ngay khi mới nhận lệnh nếu tác dụng nghiệp vụ còn chưa hoàn tất. Cần định nghĩa rõ kết quả audit đang nói về **lệnh được chấp nhận** hay **workflow hoàn tất**.

Một request có thể tạo nhiều record audit theo từng giai đoạn và một số domain event tương ứng. Dùng **correlation_id** hoặc **workflow_id** để ghép chúng; không ép một request chỉ có một hành động.

## 12. Thứ tự, đồng thời và các nguồn thời gian

Để giải thích lịch sử phải phân biệt:

- **event/occurred time**: hành động thực tế diễn ra lúc nào.
- **valid time**: giá trị có hiệu lực nghiệp vụ khi nào.
- **recorded/accepted time**: hệ thống chấp nhận thông tin từ lúc nào.
- **commit time/order**: transaction có thứ tự và trở nên khả kiến như thế nào trong nguồn có thẩm quyền.
- **processing/published time**: hệ thống downstream xử lý hoặc phát dữ liệu lúc nào.

Một event có **occurred_at** sớm hơn event khác nhưng **được chấp nhận** sau nó. Dựa vào timestamp đơn thuần để sắp xếp có thể sai vì đồng hồ lệch, timestamp trùng nhau, sự kiện đến muộn hoặc thay đổi hồi tố.

### 12.1. Version và concurrency của một aggregate

Nếu event store là nguồn sự thật, nên dùng khóa:

~~~text
(aggregate_id, aggregate_version)
~~~

và ghi event mới với **expected_version**. Hai writer cùng đọc version 2 và cố chèn version 3 cho cùng aggregate; khóa UNIQUE buộc một lệnh thất bại hoặc phải retry sau khi đọc lại trạng thái. **event_id** giúp deduplicate khi request lặp.

Trong mô hình history làm nguồn, khóa theo thực thể hoặc optimistic revision bảo vệ việc chia khoảng. Ràng buộc loại trừ bảo vệ kết quả không chồng lấn, nhưng không giải quyết chính sách chọn quyết định có thẩm quyền.

### 12.2. Bitemporal và thứ tự sự kiện

Nếu một correction ngày 20/03 sửa ngày hiệu lực của quyết định 10/03, event store có thể ghi:

~~~text
v1 SubscriptionActivated(...)
v2 PlanChangeApproved(validFrom=2026-03-01)
v3 PlanEffectiveDateCorrected(validFrom=2026-03-05)
~~~

Projection có thể dựng lịch sử **theo hiểu biết mới nhất** sau v3. Muốn biết hệ thống từng hiểu gì sau v2, có thể replay tới v2 nếu event log đầy đủ, giữ quy tắc diễn giải cũ và mapping version → mốc hệ thống đáng tin. Với truy vấn as-of dày đặc trên hai thời gian, lưu **bảng bitemporal materialized** thường hiệu quả hơn replay mọi lần.

Như vậy **event sourcing có thể là nền để dựng bitemporal**, nhưng không tự có API bitemporal, không giải quyết commit time tuyệt đối, không bỏ nhu cầu khóa và schema evolution.

## 13. Ràng buộc toàn vẹn khác nhau theo loại dữ liệu

### 13.1. Audit

- **audit_id duy nhất**; actor, action, entity và outcome có ngữ nghĩa.
- Trường dữ liệu nhạy cảm được **lọc/che**.
- Cần biết log nào thuộc **thao tác đã commit** và log nào là **attempt bị từ chối**.
- Có cơ chế hạn chế sửa/xóa và đối soát việc mất bản ghi nếu yêu cầu kiểm toán.
- Tránh ép UNIQUE theo request_id khi một request tạo nhiều thao tác.

### 13.2. Business history

- Có **entity_id** ổn định và **version_id** riêng.
- Khoảng hiệu lực không rỗng, biên có quy tắc **[from, to)**.
- Không chồng lấn theo đúng khóa nghiệp vụ nếu tại một thời điểm chỉ được có tối đa một giá trị.
- Nếu bắt buộc có giá trị liên tục, kiểm tra thêm **gap**.
- Mỗi phiên bản tham chiếu nguồn quyết định.
- Thao tác cập nhật nhiều khoảng phải **nguyên tử** và xử lý đồng thời.

### 13.3. Event log

- **event_id** duy nhất; **aggregate_version** độc nhất trong aggregate.
- Định nghĩa event schema/version và payload cần thiết.
- Bảo vệ nguồn phát, điều kiện sự kiện thực sự được chấp nhận.
- Ghi theo thứ tự logic đủ để replay; kiểm tra **không thiếu version** khi cần tái dựng.
- Phát lại không nhân đôi tác dụng; consumer idempotent.
- Có chính sách correction, replay và migration rõ ràng.

### 13.4. Ràng buộc liên kết giữa các loại

Nếu một quyết định tạo history version và event:

- **decision_ref** nên trỏ về cùng một quyết định phê duyệt, giúp đối soát.
- **event_id** hoặc **outbox_id** phải duy trì danh tính khi gửi lại.
- Audit record thành công chỉ nên được ghi khi hành động đã thành công ở cấp mà outcome mô tả.
- Đường ghi phải không thể cập nhật nguồn sự thật mà bỏ qua việc ghi chứng cứ bắt buộc.

Không mặc định khóa ngoại trực tiếp giữa mọi hàng history, audit và event: một quyết định có thể tạo nhiều phiên bản hiệu lực, nhiều audit hoạt động và nhiều event. Liên kết nên phản ánh **cardinality** thực tế, không xây một quan hệ một-một sai.

## 14. Truy vấn điển hình và chỉ mục

### 14.1. “Ai đổi gói của khách 501?”

~~~sql
SELECT
    audit_id,
    actor_type,
    actor_id,
    action_code,
    outcome,
    request_id,
    decision_ref,
    recorded_at
FROM audit_activity
WHERE tenant_id = 1
  AND entity_type = 'CUSTOMER_SUBSCRIPTION'
  AND entity_id = '501'
ORDER BY recorded_at, audit_id;
~~~

Đây là truy vấn **audit**. Nếu có nhiều thao tác cùng timestamp, **audit_id** chỉ giúp sắp xếp ổn định về mặt trình bày, không nhất thiết là thứ tự commit. Khi cần thứ tự chính xác, phải dùng sequence/transaction metadata thích hợp.

### 14.2. “Khách dùng gói nào vào ngày 05/03?”

~~~sql
SELECT plan_code, decision_ref
FROM subscription_plan_history
WHERE customer_id = 501
  AND valid_period @> DATE '2026-03-05';
~~~

Đây là truy vấn **business history** tại ngày hiệu lực nghiệp vụ B. Ràng buộc chống overlap trong bảng history giúp tối đa một hàng khớp nếu nghiệp vụ yêu cầu một gói chính.

### 14.3. “Những sự kiện nào của khách 501 dẫn đến trạng thái này?”

~~~sql
SELECT
    aggregate_version,
    event_id,
    event_type,
    schema_version,
    event_payload,
    recorded_at
FROM subscription_domain_event
WHERE aggregate_id = 501
ORDER BY aggregate_version;
~~~

Đây là truy vấn **event stream**. Nếu nguồn sự thật là event store, thứ tự aggregate_version là thứ tự logic dựng trạng thái của aggregate. Nó không tự mô tả thứ tự nhân quả giữa **nhiều aggregate** nếu không có thêm quy ước.

### 14.4. Các chỉ mục phục vụ ba kiểu truy vấn khác nhau

| Nhu cầu | Hướng chỉ mục |
|---|---|
| Audit theo actor/thời điểm | tenant, actor, recorded_at |
| Audit theo thực thể | tenant, entity_type, entity_id, recorded_at |
| History as-of | entity_id + range/biên thời gian, GiST khi phù hợp |
| History timeline | entity_id + valid_from |
| Event replay | aggregate_id + aggregate_version |
| Event tìm theo loại/kỳ | event_type + recorded_at hoặc projection phân tích |
| Outbox chưa phát | Partial index theo trạng thái pending |

Chỉ mục tăng chi phí ghi và lưu trữ. Với hệ thống audit/event có lưu lượng lớn, cần đo **EXPLAIN (ANALYZE, BUFFERS)**, quy tắc partitioning và retention trước khi tạo nhiều chỉ mục. Không chọn khóa phân vùng khiến ràng buộc uniqueness/order không còn được bảo vệ ở phạm vi cần thiết.

## 15. Dữ liệu chốt và bằng chứng không được tự viết lại

Lịch sử hiệu lực có thể thay đổi khi có quyết định hồi tố, nhưng một hóa đơn đã phát hành hoặc một giao dịch đã ghi sổ cần giữ bằng chứng về **giá trị thực sự được sử dụng**.

Ví dụ:

- Ngày 08/03, hóa đơn đã tính gói BASIC vì hệ thống chưa nhận quyết định đổi sang PRO.
- Ngày 10/03, quyết định PRO có hiệu lực từ 01/03 được chấp nhận.
- Theo lịch sử nghiệp vụ hiện nay, quyền PRO có hiệu lực ở ngày 08/03.
- Nhưng hóa đơn phát hành ngày 08/03 **đã được tính theo BASIC**; không thể chỉ JOIN lịch sử hiện nay rồi giả định hóa đơn khi ấy đã dùng PRO.

Một dòng hóa đơn nên lưu **giá/thuế/giảm giá/kỳ tính thực dùng**, phiên bản hoặc nguồn quyết định, thời điểm chốt và mã chứng từ. Bitemporal hoặc replay event giúp **giải thích** khác biệt, không thay thế bản ghi tài chính đã chốt.

Nếu cần hoàn tiền hoặc điều chỉnh doanh thu, hệ thống tạo **chứng từ điều chỉnh** và event nghiệp vụ tương ứng, kèm audit người phê duyệt. Không tự ghi đè giá trị của giao dịch đã chốt bằng một lệnh sửa history.

## 16. Bảo mật, quyền riêng tư và lưu giữ lịch sử

Audit và event log có nguy cơ lưu quá nhiều dữ liệu nhạy cảm: token, thông tin xác thực, payload thanh toán, dữ liệu nhân sự, địa chỉ, thông tin sức khỏe hoặc dữ liệu khách hàng. Khả năng “truy vết càng chi tiết càng tốt” phải cân bằng với **nguyên tắc tối thiểu hóa dữ liệu**.

### 16.1. Quy tắc bảo vệ

- Ghi **danh tính hoặc tham chiếu cần thiết**, không sao chép toàn bộ hồ sơ vào mỗi event/audit.
- Che dữ liệu nhạy cảm trong **diff_data** và **event_payload** theo allowlist, không chỉ blacklist một vài tên trường.
- Phân quyền đọc lịch sử riêng; người được quyền xem thông tin hiện tại không mặc nhiên được xem mọi dữ liệu quá khứ.
- Giới hạn quyền sửa/xóa và quản trị riêng cho audit hoặc event store khi cần bảo đảm khả năng giải trình.
- Dùng mã hóa, retention và cơ chế xoá/ẩn danh theo chính sách áp dụng.
- Kiểm soát export audit và log truy cập chính audit nếu yêu cầu giám sát.
- Khi tài khoản bị xóa, tách định danh cần giữ làm chứng cứ khỏi payload cá nhân có thể cần ẩn danh.

**Append-only không đồng nghĩa giữ mãi mọi dữ liệu cá nhân.** Nếu pháp luật/chính sách yêu cầu xóa hoặc giới hạn lưu, có thể cần thiết kế event chứa tham chiếu, mã định danh thay thế, mã hóa có vòng đời hoặc quy trình redaction được kiểm toán. Không để nhu cầu replay trở thành lý do mặc định để giữ mọi bí mật vĩnh viễn.

### 16.2. Retention phải phù hợp câu hỏi lịch sử

| Loại dữ liệu | Nếu xóa quá sớm, mất khả năng gì? |
|---|---|
| Audit | Không điều tra được hành động, actor hoặc nguyên nhân thao tác cũ |
| Business history | Không xác định được giá trị có hiệu lực trước mốc giữ dữ liệu |
| Event log | Không replay được từ đầu hoặc giải thích chuỗi sự kiện cũ |
| Snapshot | Replay từ event có thể chậm hơn; nếu event cũng đã bị xóa, mất nền |
| Bitemporal history | Không tái dựng được “hệ thống đã biết gì tại K” trong kỳ đã xóa |

Hãy định nghĩa **cửa sổ truy vấn được bảo đảm**. Nếu retention không còn hỗ trợ một ngày cũ, API cần trả “ngoài phạm vi lịch sử được giữ”, không suy ra “không tồn tại” hoặc “giá trị bằng 0”.

## 17. Lựa chọn mô hình trên relational, document, graph và analytical systems

Một mục tiêu của **DATABASE_DATA_MODELING** là biết cách so sánh các mô hình lưu trữ khác nhau trước khi chọn công nghệ. Ba loại lịch sử có thể xuất hiện trên mọi loại database; thách thức chính là **ngữ nghĩa và ràng buộc**, không chỉ định dạng.

| Mô hình | Audit trail | Business history | Domain event log |
|---|---|---|---|
| **Quan hệ** | Bảng audit, chỉ mục theo actor/entity/time | Bảng phiên bản với range/FK/exclusion | Bảng event theo aggregate/version, outbox |
| **Document** | Collection hoạt động có metadata và diff | Collection phiên bản với validFrom/To | Event document với schemaVersion và sequence |
| **Graph** | Log thao tác node/edge | Node/edge có khoảng hiệu lực | Event thay đổi quan hệ/node, projection đồ thị |
| **Kho phân tích** | Bảng fact thao tác phục vụ điều tra xu hướng | Dimension SCD Type 2, fact snapshot, temporal join | Event fact dùng phân tích dòng hành vi và chuyển trạng thái |

### 17.1. Relational: ràng buộc cơ sở dữ liệu mạnh nhưng vẫn cần nghiệp vụ

PostgreSQL hỗ trợ **CHECK**, **UNIQUE**, **FOREIGN KEY**, **GiST exclusion** và transaction, nên thuận lợi để mô hình history có ràng buộc. Tuy nhiên cơ sở dữ liệu không biết một quyết định nâng gói có được phê duyệt đúng hay không; quyền và workflow phải được xác định ở lớp nghiệp vụ.

### 17.2. Document: linh hoạt payload nhưng chống overlap khó hơn

Document event có thể dễ mở rộng khi thêm trường, nhưng **schema linh hoạt** không có nghĩa không cần schema. Cần schemaVersion, validation, định danh sự kiện và khóa logic. Với history, một unique index theo **validFrom** không cấm hai khoảng bắt đầu khác nhau nhưng chồng lấn; phải dùng cơ chế transaction/locking phù hợp.

### 17.3. Graph: quan hệ có lịch sử riêng

Với graph tổ chức, một cạnh **EMPLOYEE MEMBER_OF DEPARTMENT** có thể có valid_period; audit ghi ai sửa cạnh; event **EmployeeTransferred** biểu diễn quyết định chuyển. Ba đối tượng đó không đồng nghĩa. Khi truy vấn đường đi tại ngày D, phải lọc **tất cả cạnh liên quan theo cùng ngày D**.

### 17.4. Kho phân tích: không lẫn “sự kiện” với “trạng thái cuối kỳ”

Một **transaction fact** lưu hành động/sự kiện; **periodic snapshot fact** lưu trạng thái cuối kỳ; **SCD Type 2 dimension** lưu các phiên bản thuộc tính theo thời gian. Các bảng này bổ sung nhau. Nếu dùng audit fact để tính gói khách tại ngày D, cần chắc rằng audit có đủ trạng thái khởi tạo, đủ tất cả thay đổi và ngữ nghĩa hiệu lực; nếu không, hãy JOIN business history hoặc dimension tương ứng.

## 18. Lựa chọn chiến lược: không nhất thiết triển khai cả ba ở cùng độ chi tiết

Các hệ thống khác nhau có yêu cầu khác nhau.

### 18.1. Chỉ trạng thái hiện tại + audit tối thiểu

Phù hợp khi ứng dụng cần biết **cấu hình hiện tại** và điều tra người đã đổi, nhưng **không** cần truy vấn giá trị hiệu lực ở mọi ngày. Ví dụ tùy chỉnh giao diện người dùng được phép ghi đè, có audit thao tác quản trị.

Rủi ro: nếu sau này cần “giá trị ngày X”, một audit thiếu before/after hoặc dữ liệu đến muộn có thể không đủ.

### 18.2. Trạng thái hiện tại + business history

Phù hợp khi cần tra lịch hiệu lực, ví dụ bảng giá, hợp đồng, tư cách thành viên, phân công nhân sự. Có thể thêm audit cho các thao tác có yêu cầu trách nhiệm cao.

Rủi ro: nếu business history bị UPDATE mà không giữ known-time hoặc audit đầy đủ, khó giải thích trạng thái hệ thống từng ghi nhận trước một correction.

### 18.3. Event sourcing + projections + audit có chọn lọc

Phù hợp khi **chuỗi quyết định/sự kiện là nguồn sự thật**, nhiều projection cần dựng lại và logic nghiệp vụ có thể diễn giải deterministic.

Rủi ro: event schema khó tiến hóa nếu thiết kế sơ sài; replay tốn tài nguyên; audit bảo mật của các thao tác thất bại không tự xuất hiện; cần chiến lược versioning, snapshots, concurrency và idempotency.

### 18.4. Bitemporal history + audit + domain events

Phù hợp với nghiệp vụ thường xuyên có **điều chỉnh hồi tố**, cần giải thích cả **hiệu lực** lẫn **hệ thống đã biết gì**, đồng thời có trách nhiệm giải trình thao tác và thông báo downstream.

Rủi ro: chi phí lưu trữ, tính phức tạp của cập nhật, ràng buộc hai chiều, đồng bộ projection và các giới hạn commit-time.

**Nguyên tắc chọn:** bắt đầu từ những câu hỏi phải trả lời, nghĩa vụ bằng chứng và bất biến dữ liệu, không bắt đầu bằng tên công nghệ hoặc một “mẫu history dùng chung” cho mọi thực thể.

## 19. Kiểm thử sự khác biệt giữa audit, history và event

Với khách 501 và quyết định APPROVAL-77, nên kiểm thử:

| Kịch bản | Audit | Business history | Event log |
|---|---|---|---|
| Đổi BASIC → PRO có hiệu lực 01/03 và commit thành công ngày 10/03 | Ghi ai thao tác, request, outcome thành công | BASIC kết thúc trước 01/03; PRO từ 01/03 | PlanChangeApproved đã được chấp nhận |
| Người không có quyền cố đổi gói | Ghi attempted/rejected nếu chính sách yêu cầu | Không thay đổi | Không có PlanChangeApproved |
| Gửi lại cùng request đã được xử lý | Không được ghi như một quyết định mới thành công ngoài ý định | Không tạo phiên bản trùng | Không tạo event nghiệp vụ trùng; phát lại giữ event_id |
| Quyết định đính chính ngày hiệu lực | Ghi người sửa, lý do và quyết định liên quan | Chia lại khoảng, giữ history theo yêu cầu | Event correction mới; projection được dựng lại |
| Phát broker thất bại sau DB commit | Audit thay đổi vẫn tồn tại | History vẫn đúng | Outbox chưa phát, có cơ chế retry |
| Consumer nhận event hai lần | Không làm nhân đôi thao tác nghiệp vụ | Projection vẫn đúng | Idempotency theo event_id/version |
| Có invoice đã chốt theo BASIC ngày 08/03 | Audit chứng minh quyết định/ghi nhận | History hiện tại có thể nói PRO đúng ngày 08/03 | Event có thể giải thích quyết định; invoice giữ snapshot riêng |
| Query B = 05/03, K = 08/03 | Audit đơn thuần không bảo đảm trả lời | Bitemporal/replay đáng tin trả BASIC | Replay tới version tương ứng nếu đủ dữ liệu |
| Query B = 05/03 theo thông tin ngày 12/03 | Audit chỉ giúp điều tra thao tác | PRO | Projection sau PlanChangeApproved cho PRO |

### 19.1. Kiểm thử transaction và quyền

1. Khi transaction cập nhật history lỗi, audit **SUCCEEDED** và outbox event trong transaction đó phải rollback cùng.
2. Nếu ghi audit bảo mật về lần thử thất bại, record ấy phải sống độc lập với transaction nghiệp vụ bị rollback.
3. Hai command cùng sửa timeline phải được serialize hoặc phát hiện conflict bằng optimistic revision và ràng buộc database.
4. Một event phát lại không được gửi hai email, tạo hai hóa đơn hoặc cộng tiền hai lần nếu hành động đó phải có tính idempotent.
5. Không thể truy vấn dữ liệu tenant A chỉ nhờ biết entity_id của tenant B.
6. Dữ liệu được che ở API nghiệp vụ không được vô tình xuất hiện nguyên vẹn trong diff_data hoặc event_payload.

### 19.2. Kiểm thử query lịch sử

- Đúng biên **valid_from** và **valid_to** theo khoảng nửa mở.
- Một ngày có hai phiên bản history chồng lấn phải bị từ chối nếu nghiệp vụ yêu cầu tối đa một.
- Lịch sử quan hệ nhiều-nhiều cho phép các liên kết khác nhau cùng có hiệu lực.
- Event log khuyết aggregate_version cần bị phát hiện trước khi quảng cáo replay chính xác.
- Truy vấn “hệ thống đã biết gì ở K” không được lấy known time từ một cột **updated_at** bị ghi đè.
- Truy vấn ngoài phạm vi retention phải cho biết thiếu lịch sử thay vì trả giá trị hiện tại.

## 20. Bài thực hành: quản lý hoàn tiền cho đơn hàng

Một nền tảng thương mại điện tử có yêu cầu:

> “Khi đơn hàng bị hủy, cần biết ai bấm hủy và ai phê duyệt hoàn tiền; cần biết trạng thái đơn và quyền hoàn tiền có hiệu lực ở mỗi ngày; cần phát sự kiện để dịch vụ thanh toán hoàn tiền nhưng không xử lý hai lần.”

Tình huống:

- **01/08**: đơn hàng 700 được xác nhận, trạng thái **CONFIRMED**.
- **03/08**: khách gửi yêu cầu hủy nhưng chưa được phê duyệt.
- **04/08**: nhân viên vận hành phê duyệt hủy, có hiệu lực từ **04/08**, và cấp quyền hoàn tiền.
- **05/08**: dịch vụ thanh toán ghi nhận hoàn tiền hoàn tất.
- **06/08**: nhân viên nhập một đính chính rằng ngày hủy hợp lệ phải là **03/08** theo chính sách, nhưng hóa đơn/tiền đã chốt không tự thay đổi.

Hãy thiết kế:

1. **Audit trail** cho các hành động REQUEST_CANCEL, APPROVE_CANCEL, APPROVE_REFUND, CORRECT_CANCELLATION_DATE; ghi actor, request, decision_ref, outcome. Một yêu cầu bị từ chối phải ghi thế nào nếu có quy định kiểm toán?
2. **Business history** cho trạng thái đơn và quyền hoàn tiền theo valid_period. Nếu trạng thái chỉ có một giá trị tại một ngày, đặt khóa và ràng buộc chống overlap nào?
3. **Bitemporal** nếu cần giải thích vì sao ngày 05/08 hệ thống cho rằng đơn mới bị hủy từ 04/08, còn sau đính chính ngày 06/08 hệ thống coi hiệu lực từ 03/08.
4. **Event log** với các sự kiện như OrderConfirmed, CancellationRequested, CancellationApproved, RefundAuthorized, RefundCompleted, CancellationEffectiveDateCorrected; xác định sự kiện nào là miền và khi nào được ghi.
5. **Outbox** phát RefundAuthorized sau transaction phê duyệt. Consumer thanh toán dùng event_id/command_id để không hoàn tiền hai lần khi broker gửi lại.
6. **Truy vấn:** “Ai phê duyệt?”, “Đơn có hiệu lực CANCELLED vào ngày 03/08 theo thông tin hiện tại không?”, “Những event nào đã được xử lý trước RefundCompleted?”
7. **Chứng từ:** lưu khoản hoàn tiền thực hiện và mã giao dịch thanh toán; không chỉ tra trạng thái đơn mới nhất để suy ra số tiền đã trả.
8. **Kiểm thử:** yêu cầu hủy trùng, hai người phê duyệt đồng thời, sự kiện phát lại, transaction rollback giữa lúc lưu history và outbox, correction hồi tố.

**Đáp án định hướng:** audit giải trình hành động; history mô tả trạng thái/quyền có hiệu lực; event log thể hiện các sự kiện được chấp nhận và điều phối workflow. Bitemporal cần khi phải tái dựng cả nhận thức của hệ thống trước correction. Không bảng nào thay thế bằng chứng hoàn tiền thực tế của dịch vụ thanh toán.

## 21. Checklist thiết kế và nguyên tắc kết luận

Trước khi phê duyệt một hệ thống lưu lịch sử, nhóm kỹ thuật và nghiệp vụ nên kiểm tra:

- **Câu hỏi chính:** cần biết **ai đã thao tác**, **giá trị có hiệu lực khi nào**, hay **chuỗi sự kiện nào đã xảy ra**?
- **Nguồn sự thật:** bảng trạng thái/history hay event store là nguồn có thẩm quyền? Projection nào chỉ phục vụ đọc?
- **Khóa:** actor/request của audit, entity/version của history, aggregate/event version của event log đã tách bạch chưa?
- **Thời gian:** occurred, valid, known/recorded và commit time có ý nghĩa rõ; ngày nghiệp vụ, timezone và biên [from, to) được thống nhất chưa?
- **Toàn vẹn:** history không overlap sai; event không trùng/mất thứ tự; audit không bỏ sót tác vụ bắt buộc; tất cả đều có tham chiếu nguồn đáng tin chưa?
- **Ghi nguyên tử:** thay đổi trạng thái, audit thành công và outbox có nằm trong cùng transaction khi cần không? Các hành vi thất bại được ghi riêng thế nào?
- **Replay:** event có đủ payload và schemaVersion để dựng trạng thái deterministic, có nền snapshot và cơ chế kiểm tra thiếu event chưa?
- **Hồi tố:** khi có correction, hệ thống giữ được cách hiểu cũ nếu cần, đồng thời không âm thầm sửa chứng từ đã chốt không?
- **Giao tiếp dịch vụ:** outbox, retry, idempotency, watermark/projection lag và đối soát đã được thiết kế chưa?
- **Bảo mật/retention:** log có chứa bí mật hoặc PII không cần thiết; quyền đọc, chống sửa, thời gian giữ và xóa/ẩn danh đã được thống nhất chưa?
- **Khả năng tiến hóa:** khi chuyển sang document/graph/analytics hoặc đổi schema event, các câu trả lời nghiệp vụ còn tương đương và kiểm chứng được không?

**Nguyên tắc cuối cùng:** **audit trail** là chứng cứ về **hoạt động và trách nhiệm**, **business history** là mô hình của **giá trị/quan hệ có hiệu lực**, còn **domain event log** là chuỗi **sự kiện nghiệp vụ được chấp nhận**. Chúng có thể bổ sung cho nhau, nhưng mỗi loại phải có hợp đồng dữ liệu, nguồn thời gian, khóa và ràng buộc riêng. Thiết kế tốt không phải là lưu mọi thứ ba lần, mà là lưu **đúng loại sự thật cho đúng câu hỏi**, phối hợp chúng nhất quán và bảo toàn khả năng kiểm chứng khi hệ thống thay đổi.
