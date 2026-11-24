# Partner action audit — Kiểm toán hành động của đối tác

Một đối tác phản ánh rằng tồn kho đã bị thay đổi ngoài ý muốn. Access log chỉ cho biết một credential đã gọi `PATCH /partner/offers/...` và nhận HTTP 200. Chừng đó chưa trả lời được: credential đại diện cho ai, dữ liệu thuộc tenant nào, hành động được cho phép theo quyền nào, giá trị nào thực sự thay đổi, và request là lần đầu hay lần thử lại.

**Partner action audit** là việc ghi nhận có cấu trúc các hành động liên quan đến đối tác để có thể tái dựng quyết định quyền và tác động nghiệp vụ. Nó đặc biệt cần thiết khi điều tra sửa giá, bỏ qua phê duyệt, thao tác sai quyền, chuyển ownership hoặc gửi yêu cầu trùng.

Bài học thuộc chương **Partner Integrations** của module **SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY**. Trọng tâm là thiết kế dấu vết gắn với business invariants, state machine, quyền theo đối tượng, transaction và idempotency.

Sau bài học, người học có thể:

- Thiết kế audit event phân biệt ý định, quyết định quyền và kết quả thực tế.
- Bảo đảm thay đổi quan trọng không commit mà thiếu bản ghi audit tương ứng.
- Theo dõi retry, webhook và tác vụ nền mà không đếm trùng tác động nghiệp vụ.
- Bảo vệ audit khỏi sửa đổi, rò rỉ và dữ liệu giả do bên gọi cung cấp.
- Xác định tình huống kiểm thử để chứng minh audit phản ánh đúng nghiệp vụ.

## 1. Audit phải trả lời câu hỏi nghiệp vụ

Giả sử một nền tảng phục vụ nhiều tenant và tích hợp nhiều nhà cung cấp. Đối tác A được cập nhật tồn kho chào bán của A trong tenant T1. A chỉ được đề xuất giá; nền tảng giữ quyền phê duyệt giá chính thức.

Một bản ghi kiểu sau có giá trị chẩn đoán rất hạn chế:

~~~text
INFO partner update successful
~~~

Ngay cả thông điệp nhiều dữ liệu hơn cũng có thể gây hiểu nhầm:

~~~text
partner=A action=UPDATE status=SUCCESS resource=offer-42
~~~

Nếu được ghi trước commit, `SUCCESS` có thể tồn tại dù transaction rollback. Nếu `partner=A` lấy từ body, bên gửi có thể giả danh A trong audit.

Một audit có ích cần trả lời ít nhất sáu nhóm câu hỏi:

| Nhóm | Câu hỏi |
|---|---|
| Chủ thể | Ai đã được xác thực, bằng credential nào, có đại diện cho bên khác không? |
| Phạm vi | Tenant, tích hợp, đối tác và tài nguyên nào liên quan? |
| Hành động | Muốn thực hiện thao tác nghiệp vụ gì, trên những trường nào? |
| Cơ sở quyền | Policy, scope, ownership hoặc grant nào được kiểm tra? |
| Kết quả | Bị từ chối, bị chặn bởi invariant, đã commit hay còn chưa xác định? |
| Liên kết | Request, operation, lần retry, tác vụ nền và tác dụng phụ liên quan thế nào? |

Audit phản ánh **sự kiện mà hệ thống có bằng chứng xác nhận**. Một ý định gửi tiền không phải bằng chứng tiền đã được chuyển; một lệnh export được nhận không phải bằng chứng tệp đã được tải.

## 2. Phân biệt audit với các loại telemetry khác

| Loại dữ liệu | Mục đích chính | Giới hạn |
|---|---|---|
| Access log | Ghi nhận giao tiếp HTTP | Không tự biết thay đổi nghiệp vụ đã commit hay chưa |
| Application log | Chẩn đoán lỗi và vận hành | Nội dung có thể thay đổi theo mức log và cách triển khai |
| Trace | Theo dõi đường đi và thời gian xử lý | Có thể bị sampling; không tự bảo đảm đầy đủ audit |
| Audit nghiệp vụ | Tái dựng hành động, quyền và tác động | Cần schema, độ bền và quy tắc truy cập riêng |
| Lịch sử phiên bản dữ liệu | Lưu các giá trị qua thời gian | Có thể thiếu chủ thể, quyết định quyền và yêu cầu bị từ chối |

Các loại này có thể chia sẻ `trace_id` hoặc `attempt_id` nhưng không thay thế cho nhau.

Database trigger cũng có thể ghi nhận thay đổi hàng, song trigger không tự biết chủ thể đối tác thực sự, policy nào cho phép hoặc request đã bị từ chối trước khi vào database. Nếu bổ sung context cho trigger, context đó phải do server quản lý và được đặt lại đúng cách trên connection pool.

Audit cũng không tự đồng nghĩa với event sourcing. Không nên mặc định mọi audit event đủ dữ liệu để dựng lại toàn bộ trạng thái ứng dụng hoặc đủ an toàn để phát lại thành lệnh nghiệp vụ.

## 3. Những sự kiện nào cần ghi nhận?

Danh mục audit nên đi theo **hành động nghiệp vụ**, không chỉ theo tên endpoint:

| Nhóm hành động | Ví dụ cần quan sát |
|---|---|
| Thay đổi dữ liệu do đối tác quản lý | Cập nhật tồn kho, thay mã hàng, điều chỉnh thông tin giao nhận |
| Thao tác giá và phê duyệt | Gửi đề xuất giá, phê duyệt, từ chối, áp dụng giá đã duyệt |
| Thay đổi quyền | Cấp hoặc thu hồi grant, đổi scope, đổi ownership |
| Vòng đời tích hợp | Kích hoạt, tạm khóa, thu hồi, xoay credential |
| Dữ liệu nhạy cảm | Tạo export, tải export, truy cập tập dữ liệu được bảo vệ |
| Webhook và đồng bộ | Tiếp nhận, áp dụng, bỏ qua bản cũ, phát hiện trùng hoặc xung đột |
| Thất bại an ninh và nghiệp vụ | Sai đối tượng, sửa trường bị cấm, bỏ qua bước, phiên bản cũ |
| Công việc nền | Nhận lệnh, bắt đầu thực thi, áp dụng, thất bại, hủy vì quyền hết hiệu lực |

Không ghi tất cả thao tác thành một sự kiện `PARTNER_UPDATE` chung. Tên như `OFFER_STOCK_CHANGE`, `PRICE_PROPOSAL_SUBMIT` hoặc `OWNERSHIP_TRANSFER_APPROVE` giúp phân biệt tác động và invariant liên quan.

Đối tác được đánh dấu “tin cậy” vẫn cần audit. Sự cố credential, cấu hình sai hoặc lạm dụng nội bộ có thể xảy ra cả trong tích hợp lâu dài.

## 4. Mô hình sự kiện: ý định, quyền và kết quả

### 4.1. Chọn trạng thái có ý nghĩa rõ

Ví dụ này dùng các giá trị `outcome` sau:

| Outcome | Ý nghĩa |
|---|---|
| `RECEIVED` | Hệ thống đã ghi nhận một lần yêu cầu, chưa khẳng định được phép hoặc thành công |
| `ACCEPTED` | Lệnh đã được tiếp nhận bền vững để xử lý sau |
| `DENIED` | Kiểm tra quyền hoặc xác thực không cho phép hành động |
| `REJECTED` | Không thỏa validation, trạng thái, phiên bản hoặc invariant nghiệp vụ |
| `COMMITTED` | Tác động trong phạm vi transaction được ghi nhận đã commit |
| `REPLAYED` | Trả lại hoặc tham chiếu kết quả operation cũ; không tạo tác động mới |
| `FAILED` | Có bằng chứng bước xử lý thất bại và phạm vi thất bại đã được xác định |
| `UNKNOWN` | Chưa đủ bằng chứng để kết luận tác động đã commit hay chưa |

`authz_decision` là một trường riêng, có thể là `ALLOW`, `DENY`, `NOT_EVALUATED` hoặc `UNKNOWN`. Không ép mọi request thất bại thành `DENY`: đối tác có quyền nhưng gửi phiên bản cũ là một kết quả khác.

`COMMITTED` phải ghi rõ phạm vi. Database đã commit một yêu cầu gọi hệ thống thanh toán không có nghĩa hệ thống thanh toán đã thực hiện thành công.

### 4.2. HTTP status không phải trạng thái nghiệp vụ

HTTP 202 thể hiện request được chấp nhận để xử lý, trong khi việc xử lý chưa hoàn thành và có thể không được thực hiện về sau. Vì vậy, audit không được suy ra “đã hoàn tất” chỉ từ 202. [RFC 9110, mục 15.3.3](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.3.3).

HTTP 200 cũng có thể là response của lần retry trả kết quả đã lưu. Không tạo thêm một bản ghi “tồn kho thay đổi” cho lần retry đó.

### 4.3. Không ghi đè lịch sử để cập nhật kết quả

Có thể tạo nhiều event liên kết với nhau:

~~~text
partner.action.received
partner.command.accepted
partner.action.committed
partner.external_effect.confirmed
~~~

Nếu cần bảng hiển thị trạng thái operation hiện tại, đó là projection có thể cập nhật. Các audit event gốc vẫn giữ nguyên. Khi phát hiện thông tin sai, thêm sự kiện hiệu chỉnh tham chiếu bản ghi cũ thay vì âm thầm sửa lịch sử.

Không phải mọi hành động đều cần đủ bốn sự kiện. Luồng đồng bộ đơn giản có thể chỉ có sự kiện tiếp nhận và một kết quả cuối; chọn theo nhu cầu chứng minh và chi phí lưu trữ.

## 5. Danh tính và context nào có thể tin cậy?

### 5.1. Phân biệt chủ thể, bên khởi tạo và bên thực thi

Trong một tác vụ nền:

~~~text
Đối tác A gửi yêu cầu
    → API tiếp nhận lệnh
    → worker nội bộ thực thi
    → service khác áp dụng thay đổi
~~~

Nếu chỉ ghi `actor=inventory-worker`, hệ thống mất dấu A. Nếu chỉ ghi `actor=PARTNER_A`, hệ thống mất dấu service thực sự thực thi.

Có thể tách:

- `actor_subject_id`: chủ thể được xác thực ở điểm tiếp nhận.
- `partner_id` và `integration_id`: quan hệ tích hợp đã được server xác nhận.
- `initiator_subject_id`: chủ thể khởi tạo gốc, nếu có bằng chứng truyền context hợp lệ.
- `executor_service`: service hoặc worker đang thực thi bước hiện tại.
- `delegation_ref`: bằng chứng ủy quyền hoặc grant, nếu hành động được thực hiện thay.

Thông tin “on behalf of” phải được kiểm chứng từ cơ chế ủy quyền, không lấy trực tiếp từ header tự khai.

Audit chứng minh credential hoặc session nào được hệ thống chấp nhận. Nó không tự chứng minh con người cụ thể đã sử dụng credential đó; phân tích sự cố cần kết hợp các bằng chứng khác.

### 5.2. Dữ liệu tự khai cần có nhãn riêng

| Trường | Nguồn phù hợp | Cách diễn giải |
|---|---|---|
| `verified_tenant_id` | Ánh xạ và xác nhận của server | Phạm vi đã xác minh |
| `partner_id` | Credential hoặc session đã xác thực | Đối tác đã nhận diện |
| `credential_ref` | Mã tham chiếu credential trong hệ thống | Dùng điều tra xoay hoặc lộ credential |
| `client_correlation_id` | Header hoặc body có giới hạn | Chỉ là dữ liệu đối chiếu do client khai |
| `requested_resource_ref` | Tham số request sau kiểm tra định dạng | Tài nguyên được yêu cầu; chưa chắc được phép truy cập |
| `source_address` | Kết nối mạng hoặc proxy đã cấu hình tin cậy | Dữ liệu hỗ trợ, không phải danh tính |

Khi xác thực thất bại, `partner_id` đã xác minh có thể chưa tồn tại. Hãy ghi actor chưa xác định và loại lỗi phù hợp; không biến `partnerId` trong body thành danh tính đã xác thực.

Không dùng `X-Forwarded-For` từ mọi nguồn như địa chỉ đáng tin cậy. Nếu cần trường này, ranh giới proxy tin cậy phải được cấu hình rõ.

## 6. Thiết kế schema đủ để tái dựng quyết định

Một event cập nhật tồn kho thành công có thể có dạng:

~~~json
{
  "schema_version": 1,
  "event_id": "a5f61860-fdc1-4bc8-ad24-52197258a030",
  "event_type": "partner.action.committed",
  "action": "OFFER_STOCK_CHANGE",
  "outcome": "COMMITTED",
  "effect_scope": "LOCAL_DATABASE",
  "occurred_at": "2026-11-22T09:15:00.120Z",
  "recorded_at": "2026-11-22T09:15:00.126Z",
  "attempt_id": "9db35761-41bd-4f49-b9f7-b12b18935032",
  "operation_id": "f14e1dc7-d257-47c6-b91a-24fc9da0c193",
  "business_effect_id": "47c58041-eb42-4f9b-80da-ae547916d431",
  "actor": {
    "kind": "PARTNER_CLIENT",
    "subject_id": "client-17",
    "partner_id": "PARTNER_A",
    "credential_ref": "credential-23",
    "executor_service": "partner-api"
  },
  "scope": {
    "verified_tenant_id": "TENANT_1",
    "integration_id": "integration-8"
  },
  "target": {
    "resource_type": "PARTNER_OFFER",
    "resource_id": "offer-42"
  },
  "authorization": {
    "decision": "ALLOW",
    "policy_version": "partner-policy-12",
    "matched_rule": "OWNER_MAY_UPDATE_ACTIVE_STOCK",
    "basis": "DIRECT_OWNER",
    "required_scope": "offers:inventory:write",
    "authz_epoch": 4,
    "owner_epoch": 2
  },
  "change": {
    "before_version": 7,
    "after_version": 8,
    "fields": {
      "available_quantity": {
        "before": 120,
        "after": 50
      }
    }
  },
  "reason_code": "STOCK_CHANGE_APPLIED",
  "causation_event_id": "27268b84-5ee7-409b-8093-d8954fa7d21a",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
}
~~~

Các ID và giá trị là dữ liệu minh họa, không quy định format bắt buộc của hệ thống.

### 6.1. Ý nghĩa của các loại ID

| ID | Phạm vi nhận diện | Quy tắc |
|---|---|---|
| `event_id` | Một audit event logic | Giữ nguyên khi relay gửi lại cùng event |
| `attempt_id` | Một lần request hoặc một lần thực thi | Retry tạo attempt mới |
| `operation_id` | Một ý định nghiệp vụ đã được hệ thống nhận diện | Các retry của cùng operation liên kết vào đây |
| `business_effect_id` | Một tác động nghiệp vụ cụ thể | Không tạo effect mới khi chỉ trả kết quả cũ |
| `causation_event_id` | Sự kiện trực tiếp dẫn đến sự kiện hiện tại | Dùng nối các bước bất đồng bộ |
| `trace_id` | Đường xử lý kỹ thuật | Không dùng thay khóa idempotency hoặc bằng chứng quyền |

Một operation có thể có nhiều attempt và nhiều effect, chẳng hạn một batch. Không đặt unique constraint một `COMMITTED` duy nhất cho operation nếu thiết kế cho phép nhiều tác động độc lập.

### 6.2. Thời gian không tự chứng minh thứ tự commit

`occurred_at` mô tả thời điểm sự kiện nghiệp vụ được ghi nhận tại nguồn. `recorded_at` mô tả thời điểm nguồn tạo bản ghi. Có thể thêm `observed_at` tại hệ thống thu thập.

OpenTelemetry cũng phân biệt thời điểm sự kiện xảy ra với thời điểm được quan sát; đồng thời có các trường liên kết trace và span. Đây là mô hình tham khảo khi ánh xạ audit sang telemetry. [OpenTelemetry Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/).

Trong ví dụ, event được chuẩn bị trước commit nhưng chỉ trở thành audit bền vững cùng dữ liệu khi commit thành công. `recorded_at` không phải timestamp commit chính xác.

Không sắp thứ tự thay đổi của cùng tài nguyên chỉ bằng đồng hồ giữa các máy. Kết hợp phiên bản tài nguyên, quan hệ nhân quả và thế hệ ownership. UUID hoặc sequence cấp trước commit cũng không tự chứng minh thứ tự commit.

### 6.3. Snapshot quyền cần đủ, nhưng có giới hạn

Ghi `policy_version`, rule khớp, basis ownership hoặc grant và thế hệ quyền giúp trả lời “tại sao lúc đó được phép”.

Để tái dựng chính sách, cần giữ hoặc truy cập được phiên bản policy tương ứng. Chỉ ghi tên `policy-v12` rồi xóa mọi nội dung của v12 sẽ hạn chế khả năng điều tra.

Không cần lưu nguyên token hoặc toàn bộ danh sách claim. Có thể lưu các thuộc tính đã xác minh thực sự tham gia quyết định, với quyền truy cập và thời gian giữ phù hợp.

## 7. Bảo đảm audit thành công đi cùng transaction nghiệp vụ

Invariant quan trọng của ví dụ là:

> Không có thay đổi tồn kho đã commit mà thiếu audit event tương ứng; không có audit event khẳng định thay đổi đã commit khi transaction thực tế rollback.

### 7.1. Ba cách dễ tạo khoảng trống

**Ghi log “thành công” trước commit:**

~~~text
UPDATE tồn kho
logger.info("committed")
COMMIT bị lỗi
~~~

Thông điệp sai vẫn còn trong hệ thống log.

**Commit rồi gọi dịch vụ audit qua HTTP:**

~~~text
COMMIT tồn kho
process bị dừng
chưa gửi audit
~~~

Thay đổi đã xảy ra nhưng dấu vết thành công bị thiếu.

**Dùng transaction độc lập cho audit thành công:**

~~~text
COMMIT audit thành công ở transaction riêng
ROLLBACK transaction nghiệp vụ
~~~

Bản ghi thành công tồn tại mà không có tác động nghiệp vụ tương ứng.

### 7.2. Ghi audit và outbox cùng database transaction

~~~mermaid
flowchart TD
    A[Nhận request và tạo attempt] --> B[Ghi nhận attempt theo kênh độc lập]
    B --> C[Bắt đầu transaction nghiệp vụ]
    C --> D[Khóa và kiểm tra quyền, trạng thái, phiên bản]
    D --> E[Ghi thay đổi nghiệp vụ]
    E --> F[INSERT audit event]
    F --> G[INSERT outbox]
    G --> H{Commit thành công?}
    H -->|Có| I[Relay đọc outbox đã commit]
    I --> J[Kho audit trung tâm]
    H -->|Không hoặc chưa rõ| K[Rollback hoặc đối soát kết quả]
    D -->|Từ chối| L[Rollback và ghi kết quả từ chối độc lập]
~~~

Điều kiện để mô hình này giữ invariant:

- Dữ liệu nghiệp vụ, audit nguồn và outbox tham gia cùng transaction thực.
- Lỗi ghi audit bắt buộc làm transaction thay đổi quan trọng rollback.
- Relay chỉ đọc dữ liệu đã commit.
- Event xuất ra có `event_id` ổn định để bên nhận khử trùng.
- Outbox không bị xóa trước khi có xác nhận lưu bền theo hợp đồng của hệ thống nhận.

Nếu audit thuộc database khác, một transaction cục bộ không tự bao phủ cả hai nơi. Outbox đóng vai trò cầu nối từ bản ghi bền vững tại nguồn đến kho trung tâm.

Trong Spring, `@TransactionalEventListener` mặc định gắn với pha `AFTER_COMMIT`. Pha callback không tự tạo ra hàng đợi bền vững: nếu cần bảo đảm gửi lại khi process dừng, vẫn cần cơ chế lưu như outbox. [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html).

## 8. Minh họa Java và cấu trúc lưu audit

### 8.1. Bảng nguồn và outbox

Ví dụ PostgreSQL dưới đây là mô hình rút gọn:

~~~sql
CREATE TABLE partner_action_audit (
    event_id              UUID PRIMARY KEY,
    schema_version        INTEGER NOT NULL,
    event_type            VARCHAR(80) NOT NULL,
    action                VARCHAR(80) NOT NULL,
    outcome               VARCHAR(24) NOT NULL,
    recorded_at           TIMESTAMPTZ NOT NULL,

    verified_tenant_id    UUID,
    partner_id            UUID,
    actor_subject_id      VARCHAR(128),
    credential_ref        VARCHAR(128),

    attempt_id            UUID NOT NULL,
    operation_id          UUID,
    business_effect_id    UUID,

    resource_type         VARCHAR(80),
    resource_id           UUID,
    authz_decision        VARCHAR(24) NOT NULL,
    reason_code           VARCHAR(80) NOT NULL,
    details               JSONB NOT NULL,

    CHECK (schema_version > 0)
);

CREATE INDEX partner_audit_tenant_time_idx
ON partner_action_audit (verified_tenant_id, recorded_at);

CREATE INDEX partner_audit_operation_idx
ON partner_action_audit (operation_id);

CREATE TABLE partner_audit_outbox (
    event_id              UUID PRIMARY KEY
        REFERENCES partner_action_audit (event_id),
    payload               JSONB NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL,
    published_at          TIMESTAMPTZ,
    delivery_attempts     INTEGER NOT NULL DEFAULT 0,
    CHECK (delivery_attempts >= 0)
);
~~~

`details` không phải chỗ chứa tùy ý toàn bộ body. Nó được tạo từ schema và allowlist của từng loại event, có giới hạn kích thước và phiên bản.

Các trường tenant và actor có thể rỗng vì một số sự kiện xảy ra trước khi xác thực thành công. Đối với `COMMITTED` trong luồng đối tác đã xác thực, ứng dụng phải yêu cầu đủ context; có thể bổ sung constraint phù hợp với schema sự kiện đã chốt.

Ứng dụng không dùng quyền `UPDATE` hoặc `DELETE` trên audit nguồn để sửa nội dung lịch sử. Outbox có vòng đời vận chuyển riêng nên một số cột có thể cập nhật bởi relay.

Bảng mẫu chưa triển khai phân vùng, chính sách lưu giữ, hệ thống IAM, ràng buộc từng loại event hoặc kho bảo quản độc lập.

### 8.2. Service minh họa ranh giới transaction

Đây là mã minh họa cấu trúc, không phải chương trình độc lập. Các thành phần được giả định như sau:

- `businessTx` quản lý transaction mới của một DataSource; các repository nghiệp vụ, audit và outbox dùng chính transaction đó.
- `attemptJournal` ghi bền độc lập, không tham gia transaction nghiệp vụ đang rollback.
- `lockAndAuthorizeStockChange` khóa theo thứ tự đã thống nhất và kiểm tra tenant, tích hợp, scope, ownership cùng thế hệ quyền.
- `OfferSnapshot` là snapshot bất biến, được chụp trước khi entity bị thay đổi.
- Các exception từ chối và vi phạm nghiệp vụ là runtime exception, xảy ra trước commit.

~~~java
public StockResult changeStock(
        TrustedPartnerContext context,
        UUID offerId,
        StockCommand command
) {
    AttemptContext attempt = attempts.create(context, offerId);

    attemptJournal.appendReceived(
            attempt, "OFFER_STOCK_CHANGE"
    );

    try {
        return businessTx.execute(txStatus -> {
            AuthorizedOffer authorized =
                    policy.lockAndAuthorizeStockChange(
                            context, offerId
                    );

            Offer offer = authorized.offer();
            OfferSnapshot before = offer.snapshot();

            offer.requireActive();
            offer.requireVersion(command.expectedVersion());
            offer.changeStock(command.availableQuantity());

            OfferSnapshot after = offers.saveAndSnapshot(
                    offer, before.version()
            );

            UUID effectId = UUID.randomUUID();

            AuditEvent event = auditFactory.stockCommitted(
                    attempt,
                    authorized.decisionSnapshot(),
                    before,
                    after,
                    effectId
            );

            auditRepository.insert(event);
            auditOutbox.insert(
                    event.eventId(), event.exportPayload()
            );

            return new StockResult(
                    offer.id(), after.version(), effectId
            );
        });
    } catch (PartnerAccessDeniedException ex) {
        attemptJournal.appendDenied(
                attempt, ex.safeReasonCode()
        );
        throw ex;
    } catch (BusinessRuleRejectedException ex) {
        attemptJournal.appendRejected(
                attempt, ex.safeReasonCode()
        );
        throw ex;
    } catch (RuntimeException ex) {
        attemptJournal.appendOutcomeUnknown(
                attempt, "RECONCILIATION_REQUIRED"
        );
        throw ex;
    }
}
~~~

Điểm cần đọc đúng:

1. `stockCommitted` tạo bản ghi dự kiến nằm trong transaction. Bản ghi này chỉ tồn tại bền vững khi transaction cùng commit.
2. Nếu insert audit hoặc outbox lỗi, transaction không được commit thay đổi tồn kho.
3. Lỗi ngoài hai loại từ chối đã biết được ghi `UNKNOWN` một cách thận trọng. Không phải mọi lỗi kết nối lúc commit đều chứng minh được transaction đã rollback.
4. Journal độc lập phải có chính sách lỗi rõ; không âm thầm nuốt lỗi rồi coi độ đầy đủ audit vẫn được bảo đảm.
5. Mã chưa triển khai idempotency. Khi bổ sung retry theo idempotency key, nhánh replay phải đi theo quy tắc ở phần 10.

Không đặt `REQUIRES_NEW` cho bản ghi thành công để “tránh mất log khi rollback”. Đối với audit khẳng định một thay đổi đã commit, việc cùng rollback với thay đổi là hành vi cần thiết.

### 8.3. Vì sao kết quả từ chối cần kênh độc lập?

Request bị từ chối không tạo thay đổi nghiệp vụ, nhưng có thể là bằng chứng của tấn công logic. Nếu ghi sự kiện `DENIED` vào transaction sắp rollback rồi ném exception, bản ghi đó cũng mất.

Các phương án gồm journal bền riêng, transaction độc lập có kiểm soát hoặc hàng đợi bền đáp ứng yêu cầu tiếp nhận. Trong Java/Spring, nếu chọn transaction độc lập, phải bảo đảm cách gọi thực sự đi qua cơ chế transaction; chỉ thêm annotation vào một lời gọi nội bộ không đủ để chứng minh điều đó.

Khi journal không hoạt động, request vốn trái quyền vẫn phải bị từ chối. Không được biến việc thiếu audit thành lý do cho phép hành động.

## 9. Xử lý sự cố audit theo tác động nghiệp vụ

Cần phân biệt **nguồn audit không ghi được** và **kho trung tâm tạm thời chưa nhận được**.

| Sự cố | Chính sách minh họa |
|---|---|
| Không insert được audit nguồn cho thao tác đổi giá, quyền hoặc tồn kho quan trọng | Rollback thay đổi, trả lỗi có thể xử lý lại theo hợp đồng |
| Nguồn và outbox đã commit, collector tạm ngừng | Giữ backlog bền, retry có kiểm soát, cảnh báo độ trễ |
| Không ghi được sự kiện cho request bị từ chối | Vẫn từ chối; phát tín hiệu sự cố qua kênh độc lập nếu có |
| Lỗi event do schema không hợp lệ | Cách ly event, giữ bản gốc an toàn và cảnh báo; không âm thầm bỏ |
| Outbox gần hết dung lượng | Hạn chế tiếp nhận thao tác theo chính sách trước khi mất khả năng bảo đảm audit |
| Client mất kết nối sau commit | Không suy ra nghiệp vụ thất bại; tra operation và idempotency record |

Chính sách “không audit được thì không thực hiện” phải được xác định theo loại hành động và có khả năng vận hành thực tế. Không áp dụng một cách vô thức cho mọi log debug hoặc mọi truy vấn đọc thông thường.

Với kết quả commit chưa xác định, dùng `operation_id`, dấu vết tác động và dữ liệu nguồn để đối soát. Thêm sự kiện xác nhận sau đối soát, liên kết với event `UNKNOWN`; không ghi đè sự kiện cũ.

Không tự phát lại thao tác không idempotent chỉ vì lần gọi trước bị timeout.

## 10. Retry và webhook: nhiều attempt không có nghĩa nhiều tác động

Giả sử đối tác gửi lệnh trừ một đơn vị hàng, server commit nhưng response bị mất. Đối tác gửi lại cùng idempotency key.

Audit mong muốn:

~~~text
attempt-1 → operation-X → effect-E → COMMITTED
attempt-2 → operation-X → tham chiếu effect-E → REPLAYED
~~~

Audit sai:

~~~text
attempt-1 → STOCK_DECREMENTED
attempt-2 → STOCK_DECREMENTED
~~~

Ngay cả khi database không trừ hai lần, audit sai vẫn làm đối soát hiểu nhầm rằng đã có hai tác động.

### 10.1. Phân biệt trùng truyền tải và trùng nghiệp vụ

- Relay gửi lại cùng audit event: giữ nguyên `event_id`; kho trung tâm khử trùng.
- Đối tác thử lại request: tạo `attempt_id` mới, nhưng liên kết cùng `operation_id` khi idempotency hợp lệ.
- Đối tác gửi cùng key nhưng payload khác: ghi xung đột; không gắn nhãn replay thành công.
- Consumer xử lý lại cùng webhook: giữ tham chiếu sự kiện nguồn và operation; không tạo effect nghiệp vụ lần hai.

Khóa idempotency phải có phạm vi, ví dụ `(tenant_id, partner_id, action, idempotency_key)`. Lưu fingerprint của dữ liệu nghiệp vụ đã chuẩn hóa và tài nguyên đích. Nếu mã sự kiện chỉ duy nhất trong từng tài khoản tích hợp, phạm vi còn phải chứa tài khoản đó.

Không đưa nguyên idempotency key vào mọi hệ thống log nếu key có thể chứa dữ liệu nhạy cảm. Có thể dùng mã tham chiếu hoặc digest có khóa phù hợp; vẫn cần quản lý khóa và quyền truy cập.

### 10.2. Replay vẫn phải kiểm tra quyền hiện tại

Kết quả cũ có thể chứa dữ liệu không còn được phép xem sau chuyển giao hoặc thu hồi grant. Idempotency record không được trở thành đường tắt vượt quyền đọc.

Audit lần replay nên nêu:

~~~text
original_operation_id
original_effect_reference
current_authorization_result
replay_attempt_id
replay_reason
~~~

Nếu quyền hiện tại không cho phép trả kết quả, ghi lần từ chối tương ứng; không trả nguyên response cũ chỉ vì key khớp.

### 10.3. Khử trùng audit không tạo ra exactly-once toàn hệ thống

Unique constraint trên `event_id` ở kho nhận giúp tránh lưu lại cùng event vận chuyển. Nó không ngăn hai operation nghiệp vụ khác nhau thực hiện cùng một khoản hoàn tiền.

Bảo vệ tác động nghiệp vụ cần invariant, khóa hoặc unique constraint theo định danh nghiệp vụ thích hợp, kết hợp transaction và idempotency. Audit cung cấp bằng chứng cho cơ chế đó.

## 11. Tác vụ nền, phê duyệt và tác động liên service

### 11.1. Giữ chủ thể gốc, kiểm tra quyền tại nơi thực hiện

Một envelope nội bộ có thể mang:

~~~text
operation_id
initiating_attempt_id
initiator_subject_id
verified_tenant_id
partner_id
integration_id
authorization_epoch_at_acceptance
target_resource_id
owner_epoch_at_acceptance
causation_event_id
~~~

Envelope phải được bảo vệ bởi ranh giới truyền tin nội bộ và kiểm chứng nguồn. Giá trị epoch từ client tự khai không phải bằng chứng quyền.

Worker ghi cả context lúc tiếp nhận và kết quả kiểm tra lại tại lúc thực thi. Nếu tích hợp đã bị thu hồi, có thể xuất hiện:

~~~text
partner.command.accepted
    → partner.execution.denied
       reason=INTEGRATION_REVOKED
~~~

Không tạo sự kiện `COMMITTED` cho nghiệp vụ chưa được áp dụng.

### 11.2. Audit phê duyệt phải chỉ ra đúng đề xuất

Đối với thay đổi giá:

~~~text
Đề xuất giá P ở version 3
    → Người có quyền duyệt version 3
    → Nền tảng áp dụng đúng nội dung version 3
~~~

Audit cần liên kết đề xuất, phiên bản hoặc fingerprint được duyệt, người duyệt, policy và giá trị thực tế được áp dụng.

Một bản ghi “đã có phê duyệt” nhưng không biết phê duyệt nội dung nào không đủ để phát hiện tình huống đối tác sửa đề xuất sau khi duyệt. Audit cũng không sửa được lỗi này; transaction áp dụng phải thực sự ràng buộc với phiên bản đã được duyệt.

### 11.3. Kết quả ở service khác là sự kiện riêng

Có thể mô hình hóa:

~~~text
LOCAL_CHANGE_COMMITTED
    → EXTERNAL_REQUEST_DISPATCHED
    → EXTERNAL_EFFECT_CONFIRMED
~~~

Nếu xác nhận ngoài chưa có, ghi trạng thái đang chờ hoặc chưa xác định theo thiết kế. Nếu sau đó bù trừ, ghi sự kiện bù trừ và liên kết tác động gốc; không xóa lịch sử tác động đã xảy ra.

Không dùng một cờ `success=true` chung cho toàn bộ saga khi mới một bước hoàn tất.

## 12. Bảo vệ audit khỏi trở thành nguồn rủi ro

### 12.1. Chỉ thu thập dữ liệu cần thiết

Không ghi token, mật khẩu, khóa bí mật hoặc connection string vào audit. Với dữ liệu nhạy cảm, chỉ lưu phần cần cho điều tra và bảo vệ quyền đọc tương ứng. OWASP khuyến nghị loại bỏ hoặc xử lý dữ liệu nhạy cảm và làm sạch dữ liệu chống log injection. [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).

Áp dụng vào ví dụ:

- `credential_ref` là ID tham chiếu, không phải giá trị API key.
- `changed_fields` có thể chỉ là tên trường; lưu before/after khi giá trị đó cần thiết và được phép giữ.
- Email hoặc số điện thoại không nên xuất hiện nguyên văn trong mọi event.
- Hash không tự biến dữ liệu ít khả năng thành dữ liệu bí mật; giá trị như số tiền hoặc mã ngắn có thể bị đoán.
- Nếu cần giữ payload gốc để điều tra, dùng kho bằng chứng được bảo vệ riêng, có giới hạn, thay vì sao chép toàn bộ vào log tìm kiếm.

Không dùng audit làm kho dự phòng toàn bộ entity.

### 12.2. Chống log injection và dữ liệu quá lớn

Một trường tự do có thể chứa:

~~~text
ghi chu binh thuong\r\nactor=ADMIN outcome=COMMITTED
~~~

Nếu nối chuỗi vào log văn bản, dữ liệu có thể trông như một bản ghi khác. Dùng serializer có cấu trúc, encode đúng định dạng, giới hạn chiều dài và kiểm tra các trường tự do. Structured JSON không tự an toàn nếu ứng dụng vẫn ghép chuỗi JSON thủ công.

UI xem audit phải escape dữ liệu khi hiển thị. Export CSV cần xử lý dữ liệu có thể bị diễn giải thành công thức theo cơ chế của ứng dụng đọc; không mặc định một giá trị đã an toàn trong JSON sẽ an toàn khi xuất sang định dạng khác.

Không cắt cụt JSON ở cấp byte rồi coi đó là event hợp lệ. Giới hạn từng trường hoặc loại chi tiết ngay từ schema, kèm dấu hiệu đã rút gọn nếu cần.

### 12.3. Giới hạn quyền đọc và quyền sửa

Tách các quyền:

- Gửi hoặc insert audit.
- Vận chuyển audit.
- Tra cứu audit theo tenant và nhiệm vụ.
- Export audit.
- Quản lý lưu giữ hoặc kho bảo quản.

Đối tác không được xem toàn bộ audit nội bộ chỉ vì sự kiện có liên quan đến họ. Có thể cung cấp một view lịch sử đã chọn trường và lọc tenant. Lý do từ chối nội bộ, dữ liệu về đối tác khác hoặc rule chống gian lận có thể không được công bố.

Việc đọc và export audit nhạy cảm cũng cần dấu vết. Không cho tài khoản ứng dụng quyền xóa lịch sử chỉ vì nó cần insert.

### 12.4. Hiểu đúng về chống sửa đổi

Append-only ở tầng ứng dụng không ngăn quản trị viên database có đặc quyền sửa dữ liệu. Với yêu cầu mạnh hơn, có thể bổ sung bản sao sang miền quản trị độc lập, cơ chế lưu bất biến, digest hoặc chữ ký kèm quản lý khóa.

Một chuỗi hash có thể giúp phát hiện sửa đoạn giữa, nhưng nếu người tấn công sửa được toàn bộ chuỗi và điểm neo kiểm tra thì họ có thể dựng lại chuỗi. Cần điểm neo hoặc bằng chứng xác minh độc lập và theo dõi cả việc thiếu dữ liệu.

Không tuyên bố “không thể chối bỏ” chỉ vì event có hash hoặc vì request dùng API key. Mỗi cơ chế có giới hạn bằng chứng riêng.

## 13. Độ đầy đủ, độ trễ và khả năng vận hành

Audit có hai thuộc tính khác nhau:

- **Độ đầy đủ:** các sự kiện bắt buộc có được ghi bền hay không.
- **Độ kịp thời:** sự kiện đã có tại nguồn mất bao lâu để có thể tìm kiếm và cảnh báo.

Một collector khỏe không chứng minh không có sự kiện bị bỏ trước khi gửi. Một dashboard chưa thấy event không chứng minh nghiệp vụ chưa xảy ra.

Các chỉ số hữu ích gồm:

| Chỉ số | Dùng để phát hiện |
|---|---|
| Số lần ghi audit nguồn thất bại | Nguy cơ không thể ghi nhận thao tác bắt buộc |
| Số event outbox đang chờ và tuổi event cũ nhất | Collector hoặc relay bị nghẽn |
| Độ trễ từ nguồn đến kho trung tâm | Cảnh báo không còn kịp thời |
| Event bị cách ly vì sai schema | Lỗi triển khai hoặc dữ liệu không tương thích |
| Số lần gửi lại và khử trùng | Trục trặc vận chuyển |
| Chênh lệch tác động nguồn với audit theo định danh nghiệp vụ | Thiếu dấu vết hoặc đối soát chưa xong |
| Số sự kiện bị giảm chi tiết hoặc mất theo chính sách | Giới hạn thực tế của độ đầy đủ |

Audit thành công bắt buộc không nên phụ thuộc sampling trace. Nếu giảm số sự kiện chi tiết cho một đợt request bị từ chối rất lớn, phải có chính sách rõ, số đếm bị lược và cách diễn giải giới hạn; không tiếp tục khẳng định đã lưu đầy đủ từng attempt.

Dùng hạn mức, giới hạn kích thước, phân vùng và kênh phù hợp để giảm khả năng kẻ tấn công làm đầy kho audit bằng request sai. Không để đợt từ chối lớn đẩy mất dấu vết thay đổi quyền hoặc giao dịch quan trọng.

Chính sách lưu giữ phải xác định theo loại dữ liệu và nhu cầu đã thống nhất. Không có một số ngày mặc định phù hợp cho mọi hệ thống. Kiểm tra cả bản sao, index tìm kiếm và export khi thực thi chính sách đó.

## 14. Từ audit đến phát hiện lạm dụng logic

Một truy vấn điều tra cần liên kết chủ thể, hành động và kết quả. Ví dụ tìm các lần thử sửa trường không được cấp:

~~~sql
SELECT
    verified_tenant_id,
    partner_id,
    credential_ref,
    COUNT(*) AS denied_attempts
FROM partner_action_audit
WHERE recorded_at >= :windowStart
  AND recorded_at < :windowEnd
  AND action = 'OFFER_STOCK_CHANGE'
  AND outcome = 'DENIED'
  AND reason_code = 'FORBIDDEN_FIELD_ATTEMPT'
GROUP BY verified_tenant_id, partner_id, credential_ref;
~~~

Các mã `reason_code` phải được sinh từ enum hoặc danh mục ổn định, không suy ra bằng tìm chuỗi trong thông báo lỗi tự do.

Mẫu cần điều tra có thể gồm:

- Một credential thử nhiều ID nằm ngoài phạm vi sở hữu.
- Nhiều yêu cầu chèn `approvedUnitPrice` hoặc `ownerPartnerId` vào thao tác tồn kho.
- Một operation xuất hiện nhiều effect cùng loại trong khi invariant chỉ cho phép một.
- Nhiều xung đột idempotency key với fingerprint khác.
- Tác vụ liên tục dùng quyền hoặc ownership epoch cũ sau thu hồi.
- Giá được áp dụng không khớp đề xuất hoặc phiên bản đã được duyệt.
- Export tăng đột biến hoặc tải tiếp sau thời điểm thu hồi theo chính sách hệ thống.

Không kết luận gian lận chỉ từ một lỗi đơn lẻ. Cần phân biệt sai tích hợp, lỗi triển khai và hành vi lạm dụng bằng tần suất, context cùng tác động thực tế.

Không dùng ID tài nguyên hoặc request ID làm nhãn metric không giới hạn. Chúng phù hợp hơn với audit có thể tra cứu; metric cảnh báo nên dùng các chiều có cardinality được kiểm soát.

## 15. Ma trận kiểm thử audit cần xây dựng

Đây là đặc tả kiểm thử cho khi triển khai, không phải xác nhận một ứng dụng cụ thể đã vượt qua các ca này.

| Tình huống | Bằng chứng cần kiểm tra |
|---|---|
| A cập nhật tồn kho của A đúng quyền | Dữ liệu đổi; event COMMITTED có context đúng và đúng phiên bản |
| A gửi partnerId khác trong body | Danh tính đã xác minh không bị thay; dữ liệu tự khai được phân biệt |
| Xác thực thất bại | Không gán nhầm một partner đã xác minh từ dữ liệu client |
| A dùng ID của B | Ghi từ chối phù hợp; không có event thay đổi thành công |
| A thêm trường giá đã duyệt | Có reason code ổn định; giá không đổi |
| Có quyền nhưng trạng thái không cho phép | Phân biệt REJECTED với DENIED theo mô hình đã chốt |
| Transaction nghiệp vụ rollback | Không có audit COMMITTED bền vững hoặc outbox cho thay đổi đó |
| Insert audit nguồn lỗi | Thao tác bắt buộc audit không commit |
| Commit xong, process dừng trước khi relay chạy | Audit và outbox còn; relay có thể tiếp tục |
| Relay gửi hai lần | Kho trung tâm chỉ nhận diện một event logic theo event_id |
| Client retry cùng key và payload | Attempt mới, operation cũ, không có effect mới |
| Cùng key nhưng payload khác | Audit xung đột; không ghi replay thành công |
| Lỗi kết nối đúng lúc commit | Không tự kết luận FAILED; có đường đối soát UNKNOWN |
| Request bị từ chối rồi transaction rollback | Dấu vết từ chối vẫn còn ở kênh độc lập |
| Job được nhận trước nhưng chạy sau thu hồi | Giữ chủ thể gốc; ghi kết quả kiểm tra lại và không áp dụng trái quyền |
| Thay đề xuất sau khi đã duyệt | Không áp dụng nhầm phiên bản; audit thể hiện phiên bản được duyệt |
| Gửi chuỗi CR/LF hoặc HTML vào trường tự do | Không giả được event khác; UI không thực thi nội dung |
| Gửi payload hoặc correlation ID quá dài | Bị giới hạn; event hợp lệ, không có bí mật bị sao chép |
| Người dùng tenant khác tra audit | Không đọc chéo dữ liệu |
| Role ứng dụng thử sửa hoặc xóa audit | Bị chặn theo quyền đã thiết kế |
| Kho trung tâm ngừng hoạt động | Có backlog bền, cảnh báo và chính sách tiếp nhận phù hợp |
| Đồng hồ các máy lệch nhau | Điều tra vẫn dựa được vào version và quan hệ nhân quả |
| Thực hiện bù trừ | Có event bù trừ liên kết effect gốc; lịch sử không bị xóa |

Các ca transaction và crash cần dùng cơ sở dữ liệu thực hoặc môi trường có cùng semantics. Kiểm tra mock “hàm audit đã được gọi” không chứng minh bản ghi sống sót sau commit hoặc biến mất sau rollback.

Để kiểm tra thu hồi và cạnh tranh, điều khiển hai transaction bằng barrier hoặc latch và quan sát thứ tự commit. Không dựa vào khoảng ngủ ngẫu nhiên làm bằng chứng.

## 16. Các quyết định cần chốt trước khi triển khai

Thiết kế cần trả lời rõ:

1. Hành động nào bắt buộc có audit và ý nghĩa chính xác của từng outcome là gì?
2. Trường nào đã xác minh, trường nào do client khai, và ai được xem từng loại?
3. Ranh giới transaction nào bảo đảm tác động và audit cùng tồn tại?
4. Nếu commit chưa xác định hoặc collector ngừng hoạt động, hệ thống đối soát ra sao?
5. Retry liên kết vào operation và effect như thế nào?
6. Quyền có được kiểm tra lại tại worker và tại nơi áp dụng tác động không?
7. Phiên bản policy, đề xuất và dữ liệu có đủ để tái dựng quyết định không?
8. Ai có thể ghi, đọc, export, quản lý lưu giữ và kiểm chứng tính toàn vẹn của audit?

Với luồng cập nhật tồn kho, một dấu vết đạt mục tiêu phải cho phép chỉ ra rằng credential của A trong T1 đã được kiểm tra đúng quyền, thay đổi đúng trường từ phiên bản nào sang phiên bản nào, và thay đổi đó thực sự commit một lần. Lần retry, lần từ chối và bước thực thi về sau phải được ghi nhận theo đúng ý nghĩa riêng của chúng.
