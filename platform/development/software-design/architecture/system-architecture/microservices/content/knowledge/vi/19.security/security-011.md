# Nhật ký kiểm toán và phản ứng khi thông tin xác thực bị lộ trong Microservices

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices → Bảo mật.
>
> **Bài học:** Thiết kế nhật ký kiểm toán (audit log) đáng tin cậy để biết **ai làm gì, với tài nguyên nào, lúc nào, kết quả ra sao**, đồng thời chuẩn bị quy trình **phát hiện, thu hồi, thay thế, điều tra và phục hồi** khi mật khẩu, API key, access token, khóa ký hoặc thông tin xác thực khác bị lộ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt nhật ký kiểm toán, application log, distributed trace và metric; chọn sự kiện bảo mật cần ghi ở từng ranh giới microservice.
2. Thiết kế cấu trúc audit event nhất quán, có actor, action, target, outcome, thời gian, nguồn gốc và correlation ID mà không làm lộ secret.
3. Giải thích yêu cầu về tính toàn vẹn, khả năng tìm kiếm, kiểm soát truy cập, thời gian lưu và xử lý sự cố của hệ thống log.
4. Nhận diện những con đường phổ biến làm lộ thông tin xác thực: mã nguồn, CI/CD, cấu hình, log, request, hình ảnh container và máy trạm.
5. Xây dựng runbook thu hồi/rotate credential, đánh giá phạm vi tác động, điều tra hoạt động đáng ngờ và xác nhận hệ thống phục hồi an toàn.
6. Kiểm thử cả **audit trail** lẫn **quy trình phản ứng**, kể cả khi kẻ tấn công cố dùng credential trước lúc bị thu hồi.

Các ví dụ giả định hệ thống gồm API Gateway, Identity Provider (IdP), các service nghiệp vụ, message broker, database, secrets manager và nền tảng quan sát tập trung. Không có một cấu hình áp dụng cho mọi tổ chức: quyền hạn credential, công nghệ token, yêu cầu thời gian lưu và chính sách xử lý dữ liệu cần được xác định theo hệ thống thực tế.

## 2. Vì sao microservices cần nhật ký kiểm toán?

Xét luồng đặt hàng:

~~~text
Web/Mobile
    │
    ▼
API Gateway ── xác thực bearer token ──► Identity Provider / JWKS
    │
    ├──► Order Service ──► Inventory Service ──► Inventory DB
    │         │
    │         └──────────► Payment Service ──► Payment Provider
    │
    └──► Admin Service ───► IAM / Secrets Manager

Audit events từ Gateway, IdP và từng service
              │
              ▼
          Audit Pipeline
              │
              ▼
      Bảo vệ/giám sát/tìm kiếm
~~~

Một yêu cầu của người dùng có thể được xử lý bởi năm service và ba hệ thống lưu trữ. Nếu có giao dịch thanh toán bị thay đổi trái phép, chỉ xem log của Gateway chưa đủ:

- Gateway có thể biết request đến từ account nào và có token hợp lệ hay không.
- Order Service biết ai yêu cầu thay đổi đơn nào, quyền gì đã được kiểm tra và kết quả thay đổi.
- Payment Service biết yêu cầu hoàn tiền đã thực hiện hay bị từ chối.
- IAM/IdP biết token/credential nào được tạo, làm mới, thu hồi hoặc dùng ở một vị trí bất thường.
- Secrets Manager biết workload nào truy cập vào secret nào.

**Audit trail** là chuỗi bằng chứng có thể nối các sự kiện liên quan nhằm trả lời một câu hỏi điều tra. Nó hỗ trợ điều tra sự cố, truy trách nhiệm, phát hiện hành vi bất thường và chứng minh rằng những kiểm soát quan trọng đã được thực thi.

Nếu mỗi service chỉ ghi dòng “request completed” mà không lưu actor, target và quyết định cấp quyền, tổ chức khó tái dựng điều gì đã xảy ra khi một credential bị đánh cắp.

## 3. Phân biệt các loại dữ liệu quan sát

| Loại | Câu hỏi chính | Ví dụ | Giới hạn |
| --- | --- | --- | --- |
| **Application log** | Code đang thực thi hoặc gặp lỗi gì? | “Inventory HTTP 503”, stack trace | Không nhất thiết có actor hoặc quyết định bảo mật |
| **Distributed trace** | Request đi qua service nào, tốn bao lâu? | traceId, spanId, latency | Có thể bị sampling, không phải hồ sơ kiểm toán đầy đủ |
| **Metric** | Tần suất, tỷ lệ, độ trễ có bất thường không? | auth failures/min, revoke count | Dữ liệu tổng hợp không đủ truy một hành động cụ thể |
| **Audit log** | Chủ thể nào tác động lên tài nguyên nào, được cho phép hay bị từ chối, kết quả gì? | admin đổi role người dùng | Cần bảo vệ tính đầy đủ, toàn vẹn và hạn chế truy cập |
| **Security alert** | Khi nào cần người hoặc automation phản ứng? | một token dùng từ hai khu vực lạ | Là suy luận từ bằng chứng; có thể có false positive |

Không dùng distributed tracing làm hệ thống audit duy nhất: sampling có thể bỏ mất đúng request quan trọng. Tương tự, dashboard tổng số lỗi đăng nhập không thay thế bằng chứng user nào bị thử đăng nhập, trên tenant nào và vào lúc nào.

**Hai nhóm sự kiện cần tách nghĩa:**

- **Intent/decision:** ai yêu cầu thao tác, hệ thống chấp nhận hay từ chối quyền.
- **Outcome/effect:** thao tác thực tế thành công, thất bại hoặc có trạng thái chưa xác định.

Ví dụ “refund requested” khác với “refund settled”. Ghi một sự kiện khi bắt đầu tác vụ rồi coi như hoàn tất sẽ tạo dấu vết sai lệch.

## 4. Mô hình đe dọa: credential bị lộ dẫn tới điều gì?

**Credential** là bí mật hoặc bằng chứng được hệ thống dùng để chứng minh danh tính/quyền truy cập. Các loại thường gặp:

| Credential | Ví dụ | Nguy cơ khi lộ |
| --- | --- | --- |
| API key | Key gọi Payment Provider | Lạm dụng quota, truy cập API hoặc phát sinh giao dịch trong phạm vi key |
| Service account key | Cloud access key, JSON private key | Truy cập tài nguyên cloud theo quyền IAM của account |
| Mật khẩu DB | Username/password JDBC | Đọc, sửa, xóa dữ liệu hoặc dùng DB làm bàn đạp |
| OAuth access token | Bearer token ngắn hạn | Gọi API thay chủ thể tới khi token hết hạn hoặc bị vô hiệu |
| OAuth refresh token | Token lấy access token mới | Duy trì truy cập lâu hơn nếu không thu hồi đúng cách |
| Session cookie | Cookie phiên web | Chiếm phiên nếu vẫn hợp lệ và không có ràng buộc bảo vệ bổ sung |
| Khóa ký JWT | Private key hoặc HMAC secret của issuer | Có thể giả mạo token trong phạm vi trust và thuật toán tương ứng |
| mTLS client private key | Khóa riêng của workload | Giả danh client mTLS nếu certificate và trust chain còn hợp lệ |
| SSH key | Private key để truy cập máy/bastion | Truy cập host hoặc repository trong phạm vi quyền |
| CI/CD deploy token | Token triển khai artifact | Thay đổi phần mềm, image hoặc hạ tầng nếu quyền cho phép |

Tác động thực tế phụ thuộc **scope, quyền, điều kiện dùng, hạn dùng, khả năng thu hồi và hệ thống đã tin credential đó**. Không nên đánh đồng một access token chỉ đọc đã hết hạn với private key ký token cho toàn bộ hệ thống.

Các đường lộ thường gặp: commit lên repository, pull request, build log, biến môi trường in ra stdout, message queue payload, HTTP header/query string được ghi log, stack trace, bản sao cấu hình, ticket hỗ trợ, ảnh chụp màn hình, máy tính bị chiếm quyền và artifact đã phát hành.

### 4.1. Ranh giới tin cậy trong microservices

**External → Gateway:** kiểm tra TLS, authn, token, rate limit. Không ghi nguyên Authorization header.

**Gateway → Service:** service phải xác thực nguồn danh tính hoặc token/identity context được bảo vệ. Header do client tự đặt như `X-User-Id` không phải bằng chứng danh tính nếu chưa được gateway kiểm soát và đường truyền bảo vệ.

**Service → Service:** thường dùng workload identity, mTLS hoặc token có audience/scope riêng. Không mặc định mọi service nội bộ được tin cậy toàn phần.

**Service → Secrets Manager / DB:** cấp quyền tối thiểu, ghi audit việc lấy/đổi secret. Không để service tùy ý đọc tất cả credential.

**Service → Audit Pipeline:** bảo vệ đường gửi, danh tính publisher, độ bền và giới hạn quyền đọc. Kẻ tấn công chiếm service không được có quyền sửa hoặc xóa lịch sử audit đã lưu.

## 5. Những sự kiện nào phải được kiểm toán?

Cần xây dựng **catalog sự kiện** theo rủi ro, không ghi mọi dòng debug thành audit.

### 5.1. Xác thực và phiên

- Đăng nhập thành công/thất bại, khóa/mở tài khoản, MFA thành công/thất bại, thay đổi hoặc vô hiệu hóa MFA.
- Tạo, làm mới, thu hồi token/phiên; đăng xuất; reset mật khẩu; đổi thông tin khôi phục tài khoản.
- Tạo hoặc xoay API key, yêu cầu cấp quyền mới cho client.
- Đăng nhập bằng workload identity, dùng service account đặc quyền, sử dụng “break-glass” account.

Không ghi mật khẩu, OTP, access token, refresh token, session cookie hoặc mã khôi phục; log chỉ lưu định danh sự kiện và **ID/fingerprint không có khả năng đăng nhập**.

### 5.2. Phân quyền và thay đổi quyền

- Truy cập bị từ chối đối với tài nguyên nhạy cảm; hành động đặc quyền thành công.
- Tạo, sửa, xóa role, policy, group membership, service-account permissions.
- Gán hoặc bỏ quyền admin, thay đổi quyền cross-tenant, cấu hình ủy quyền.
- Tạo, cập nhật hoặc vô hiệu hóa secret/credential; thay trust policy, signing key và cấu hình bảo mật.

Một quyết định authz nên cho biết **actor**, **action**, **target**, **decision** và **policy/rule liên quan**. Không nhất thiết ghi toàn bộ nội dung policy hoặc tài nguyên nếu chứa dữ liệu cá nhân.

### 5.3. Sự kiện nghiệp vụ nhạy cảm

- Phê duyệt hoàn tiền, chuyển tiền, thay đổi hạn mức, cập nhật người thụ hưởng.
- Thay đổi thông tin thanh toán, thay đổi chủ sở hữu hoặc trạng thái đơn hàng quan trọng.
- Xuất dữ liệu số lượng lớn, tải báo cáo nhạy cảm, thay đổi giới hạn lưu giữ.
- Đọc hoặc thay đổi tài nguyên có yêu cầu truy vết đặc biệt.

Khi một thao tác bất đồng bộ chạy qua queue, cần audit lúc **nhận yêu cầu**, lúc **thực thi** và **kết quả cuối cùng** bằng các event khác nhau có cùng correlation/operation ID.

### 5.4. Sự kiện hạ tầng và quản trị

- Secret được truy cập, thay phiên bản, vô hiệu hóa hoặc xóa.
- Deployment thay đổi identity/role, đổi cấu hình logging, tắt tính năng audit.
- Quyền truy cập log và thao tác xuất log; thay retention hoặc xóa archive.
- Phát hiện truy cập bất thường, thay policy network, phát sinh emergency access.

Mục tiêu không phải số dòng càng nhiều càng tốt. Mục tiêu là **các hành vi làm thay đổi rủi ro và quyền hạn phải tạo bằng chứng đáng tin**.

## 6. Thiết kế audit event có cấu trúc

Một event mẫu ở mức nghiệp vụ:

~~~json
{
  "schemaVersion": "1.0",
  "eventId": "8b1e8da0-62f3-4d5b-b979-bacec47235bf",
  "occurredAt": "2026-11-12T02:04:05.123Z",
  "recordedAt": "2026-11-12T02:04:05.150Z",
  "service": "order-service",
  "environment": "production",
  "tenantId": "tenant-42",
  "eventType": "order.approve",
  "actor": {
    "type": "USER",
    "id": "user-173",
    "authenticationMethod": "OIDC",
    "clientId": "web-portal"
  },
  "target": {
    "type": "ORDER",
    "id": "order-987"
  },
  "action": "APPROVE",
  "decision": "ALLOW",
  "outcome": "SUCCESS",
  "reasonCode": "ORDER_POLICY_ALLOWED",
  "traceId": "e7f04a9edfe0193b2aa86e610ad0c948",
  "requestId": "req-1042",
  "operationId": "op-930",
  "source": {
    "ip": "198.51.100.24",
    "userAgentClass": "WEB"
  }
}
~~~

Dữ liệu chỉ mang tính minh họa. IP trên thuộc dải tài liệu; trong hệ thống thực, việc lưu IP, user agent hoặc subject ID phải phù hợp mục đích, chính sách dữ liệu và thời gian lưu đã xác định.

**Ý nghĩa các trường quan trọng:**

| Trường | Vai trò |
| --- | --- |
| `schemaVersion` | Cho phép thay đổi cấu trúc event có kiểm soát |
| `eventId` | Định danh duy nhất phục vụ dedup và kiểm tra thiếu sự kiện |
| `occurredAt` / `recordedAt` | Phân biệt thời điểm hành động và thời điểm hệ thống nhận log |
| `service`, `environment`, `tenantId` | Giải thích phạm vi và nguồn phát sự kiện |
| `eventType`, `action` | Định danh hành vi có cấu trúc, nhất quán giữa các service |
| `actor` | Chủ thể thực hiện; phân biệt USER, SERVICE, SYSTEM, ADMIN |
| `target` | Tài nguyên bị tác động, ở mức tối thiểu cần điều tra |
| `decision` | Kết quả đánh giá quyền: ALLOW/DENY/NOT_EVALUATED |
| `outcome` | Kết quả xử lý: SUCCESS/FAILURE/PENDING/UNKNOWN |
| `reasonCode` | Mã lý do ổn định, thuận lợi cho truy vấn và cảnh báo |
| `traceId`, `requestId`, `operationId` | Nối chuỗi sự kiện đồng bộ, bất đồng bộ và nghiệp vụ |
| `source` | Ngữ cảnh nguồn request đã qua bước xác thực/chuẩn hóa |

**Không phải trường nào cũng luôn có giá trị.** Một job tự chạy không có user; một request bị chặn trước authentication chưa có actor xác thực. Dùng `actor.type=ANONYMOUS` và thông tin nguồn đã tin cậy thay vì gán một user tùy ý.

**Đừng đồng nhất `decision=ALLOW` với `outcome=SUCCESS`.** Một request có quyền thực hiện nhưng vẫn thất bại do DB timeout. Tách hai trục giúp điều tra chính xác hơn.

### 6.1. Subject, initiator và service identity

Khi Admin dùng Gateway gọi Order rồi Order gọi Inventory, có thể tồn tại nhiều danh tính:

- **Initiator:** người quản trị thực hiện hành động.
- **Authenticated caller:** workload `order-service` đang gọi Inventory.
- **Delegated subject:** người dùng mà Order đại diện khi được ủy quyền hợp lệ.

Audit event ở Inventory nên ghi đủ quan hệ được xác minh nếu thực sự cần: `actor.type=SERVICE`, `actor.id=order-service`, `onBehalfOf=user-173`. Không chỉ sao chép một header user mà không kiểm chứng tính xác thực và quyền ủy quyền.

### 6.2. Thời gian và thứ tự

Dùng timestamp chuẩn UTC, ví dụ ISO 8601 có `Z`. Đồng bộ đồng hồ trên host và container; giữ cả thời điểm event phát sinh và thời điểm được nhận. Hệ thống phân tán **không bảo đảm** event đến nơi theo đúng thứ tự thời gian.

Nếu cần tái dựng thứ tự của một thực thể, kết hợp `operationId`, sequence/version từ transaction hoặc event stream, timestamp và causal context. Đừng chỉ dựa vào mili giây của các node khác nhau.

## 7. Correlation xuyên service

Ví dụ một admin thay role rồi hệ thống phát event và cập nhật cache:

~~~text
Gateway          IAM Service              Event Bus            Audit Sink
   │ POST role      │                         │                      │
   ├────────────────►│                         │                      │
   │ req-77         │                         │                      │
   │ trace-abc      ├─ audit: role.change     │                      │
   │                ├─────────────────────────►│                      │
   │                │                         ├─────────────────────►│
   │                │                         │                      │
   │                └─ domain: role.updated ──►│                      │
   │◄─ 200/202      │                         │                      │
~~~

Mỗi service tạo `eventId` độc lập nhưng mang `traceId` hoặc `operationId` phù hợp để nối lại. Với message queue, nên propagate correlation ID trong header có schema thống nhất; consumer tạo span mới nhưng giữ quan hệ nhân quả.

**Quy tắc:**

1. Tạo request ID ở ingress nếu chưa có, nhưng kiểm soát độ dài/ký tự và không mặc định tin ID do client cung cấp.
2. Không đặt token, email đầy đủ hoặc thông tin riêng tư vào correlation ID.
3. Hạn chế lấy actor từ message payload mà không có chữ ký, quyền và nguồn phát xác thực.
4. Mọi event thể hiện **kết quả cục bộ** của service phát, không tự tuyên bố trạng thái ở service khác đã hoàn tất.
5. Với retry, mỗi lần thử có thể có event riêng; dùng idempotency key/operation ID để tránh tưởng một hành động thành nhiều giao dịch độc lập.

## 8. Kiến trúc thu thập và lưu trữ audit

Một kiến trúc điển hình:

~~~text
Gateway / IdP / Order / Payment / IAM / Secrets Manager
                  │ structured events
                  ▼
          Local queue / outbox
                  │
                  ▼
     Event streaming / log collector
                  │ validation + redaction
                  ▼
        Immutable / tamper-evident store
                  │
         ┌────────┴────────┐
         ▼                 ▼
     Search index       SIEM / Alerts
         │                 │
         ▼                 ▼
   Audit investigator   Incident response
~~~

Có thể dùng nhiều nhà cung cấp công nghệ khác nhau. Chức năng quan trọng là độ bền dữ liệu, nguồn gốc đáng tin, quyền truy cập và khả năng phát hiện bất thường.

### 8.1. Ghi event tại đúng điểm quyết định

Gateway phù hợp để ghi kết quả authn, chặn request, source IP và rate limit. Nhưng **service nghiệp vụ** mới biết đúng hành động có thực sự thay đổi dữ liệu và vượt qua điều kiện nghiệp vụ hay không. Vì vậy audit cần đặt ở nơi quyết định hoặc commit được thực hiện.

Ví dụ, Admin Service trả 202 Accepted cho một yêu cầu vô hiệu hóa API key. Đó mới là **REQUEST_ACCEPTED**. Sau khi IAM xác nhận revoke thành công, phát **CREDENTIAL_REVOKED**. Nếu job thất bại, phát **REVOCATION_FAILED**, không sửa đè event trước đó.

### 8.2. Tránh “transaction thành công nhưng thiếu audit”

Một service ghi database rồi mới đẩy event qua HTTP có khoảng hở:

~~~text
DB commit thành công → process crash → chưa gửi audit event
~~~

Đối với hành động quan trọng, **transactional outbox** có thể ghi dữ liệu nghiệp vụ và hàng outbox trong **cùng transaction**:

~~~sql
BEGIN;

UPDATE account_role
SET role = 'REVIEWER', version = version + 1
WHERE account_id = :account_id;

INSERT INTO audit_outbox (
    event_id, event_type, payload_json, created_at
) VALUES (
    :event_id, 'account.role_changed', :sanitized_event, CURRENT_TIMESTAMP
);

COMMIT;
~~~

Worker khác đọc outbox và chuyển event đến audit pipeline, có retry và dedup theo `event_id`. Cơ chế này giảm nguy cơ **data commit nhưng không có record audit**, nhưng không tự tạo exactly-once delivery end-to-end. Consumer cần chấp nhận phát lại và dedup.

Đối với thao tác yêu cầu audit thành điều kiện bắt buộc, có thể phải **fail closed** nếu không thể ghi bằng chứng bền vững. Với chức năng ít rủi ro hơn, có thể cho phép tiếp tục khi collector tạm mất kết nối và dùng buffer bền vững. Quyết định phải được ghi thành policy nghiệp vụ, cân bằng giữa sẵn sàng và yêu cầu kiểm toán.

### 8.3. Phân biệt audit store và search index

Search index giúp truy vấn nhanh nhưng có thể xóa/sửa hoặc tái xây dựng. Cần một nguồn lưu bằng chứng bền vững, hạn chế sửa/xóa (ví dụ object storage có retention/immutability controls, append-only pipeline hoặc cơ chế tương ứng).

Không coi việc bật TLS hoặc mã hóa at rest là đủ cho **chống sửa log**: cả hai giúp bảo mật dữ liệu, nhưng actor có quyền write/delete vẫn có thể sửa bản ghi nếu chính sách lưu trữ cho phép.

## 9. Tính toàn vẹn và chuỗi bằng chứng

Audit log chỉ hữu ích nếu người điều tra có cơ sở tin vào nguồn và sự nguyên vẹn:

- **Nguồn phát có danh tính:** publisher dùng workload identity hoặc cơ chế xác thực riêng; không để client giả service name tùy ý.
- **Chống mất event:** buffer, retry, dead-letter queue, metric event lag, số event bị từ chối và quy trình khôi phục.
- **Bảo vệ dữ liệu lưu:** tách quyền ghi thêm, quyền tìm kiếm, quyền export và quyền quản trị/xóa.
- **Chống sửa:** lưu trên hệ thống hỗ trợ append-only/immutable retention khi phù hợp.
- **Dấu vết truy cập:** ghi lại cả việc người điều tra xem, truy vấn hoặc xuất dữ liệu nhạy cảm.
- **Kiểm tra toàn vẹn:** dùng digest, chữ ký, HMAC hoặc chuỗi hash để phát hiện thay đổi trong phạm vi thiết kế.
- **Thời gian đáng tin:** đồng bộ đồng hồ, ghi nhận trễ ingest và đánh dấu nguồn không xác minh được.

Ví dụ một chuỗi băm:

~~~text
h(1) = H(event-1 || trusted-anchor)
h(2) = H(event-2 || h(1))
h(3) = H(event-3 || h(2))
~~~

Nếu thay event-2 mà không cập nhật phần còn lại, xác minh chuỗi có thể phát hiện thay đổi. Nhưng **hash chain tự nó không đủ** nếu kẻ tấn công có quyền viết lại cả lịch sử, giá trị hash và anchor. Cần bảo vệ hoặc ký anchor ở hệ thống/khóa tách quyền, lưu giữ bản đối chiếu ngoài đường dữ liệu bị chiếm.

Ghi nhận **chain of custody** cho bằng chứng sự cố: ai xuất dữ liệu, lúc nào, truy vấn nào, phạm vi nào, nơi lưu, checksum, ai đã tiếp nhận. Giữ bản gốc hoặc bản xuất được xác minh; dùng bản sao trong quá trình phân tích.

## 10. Bảo vệ dữ liệu trong audit log

Một lỗi phổ biến: triển khai audit “để phục vụ bảo mật” nhưng lại ghi nguyên `Authorization: Bearer ...` hoặc mật khẩu vào log, khiến hệ thống log trở thành kho credential.

**Danh mục phải tuyệt đối tránh ghi trực tiếp:**

- Mật khẩu, OTP, reset token, refresh token, access token, session cookie, CSRF token.
- Private key, client secret, API key, database password, secret manager response.
- Full request/response bodies của login, payment, token exchange, password reset.
- Connection URL kèm password; URL query chứa credential.
- Stack trace, debug dump, env dump chứa bí mật hoặc dữ liệu nhạy cảm.

**Nên ghi gì thay thế?**

- Credential **identifier** do issuer cấp, nếu identifier này không dùng để đăng nhập.
- Một fingerprint dẫn xuất một chiều có kiểm soát, ví dụ HMAC keyed trên token/credential cho mục đích điều tra trùng lặp; không đưa key HMAC vào cùng nơi log.
- ID tài nguyên; loại event; outcome; reason code; token issuer/audience hoặc scope **đã chuẩn hóa** nếu cần và được cho phép.
- Claim hoặc metadata sau khi **xác minh chữ ký, audience, issuer, expiry**. Đừng tin payload JWT được decode nếu chưa xác thực.

**Lưu ý bảo vệ fingerprint:** Hash SHA-256 của một secret có entropy thấp, ví dụ mật khẩu dễ đoán, có thể bị kiểm tra brute force. Dùng HMAC với khóa riêng cho pseudonymous correlation khi cần; đừng coi hash trần là biện pháp bảo vệ mọi secret. Không dùng fingerprint như credential thay thế.

### 10.1. Redaction theo allowlist

Ưu tiên **chỉ ghi các field đã cho phép** và schema được kiểm soát. Dùng blacklist mask trên toàn bộ object request dễ bỏ sót field mới, key lồng nhau hoặc tên khác.

Khi buộc log HTTP metadata:

~~~text
CHO PHÉP: method, route template, status, latency, traceId
CÂN NHẮC: source IP đã qua policy dữ liệu, user agent đã phân loại
CẤM: Authorization, Cookie, Set-Cookie, X-API-Key,
     raw query string, body đăng nhập, headers tự do
~~~

Với đường dẫn `/users/12345/reset?token=...`, log route template `/users/{id}/reset`, không ghi nguyên URL. Không tin rằng log collector sẽ kịp xóa secret đã in ra stdout vì một hệ thống trung gian có thể đã nhận dữ liệu thô.

### 10.2. Retention và quyền truy cập

Xác định rõ:

1. Loại event nào cần lưu, dùng cho mục đích gì.
2. Thời gian lưu **active searchable** và **archive** là bao lâu.
3. Ai có quyền query, ai được export, ai có quyền quản trị retention và ai được thực hiện legal hold theo quy trình phù hợp.
4. Dữ liệu cần pseudonymize, minimize, redact hoặc xóa theo chính sách pháp lý áp dụng.
5. Sau thời gian retention, xóa theo lịch có kiểm soát và ghi dấu thao tác quản trị.

Không tự chọn một con số retention cho mọi ngành và vùng pháp lý. Bản lưu “immutable” phải thiết kế tương thích nghĩa vụ bảo vệ dữ liệu và yêu cầu xóa hợp lệ.

## 11. Khi nào được coi là thông tin xác thực đã bị lộ?

**Exposure** không đồng nghĩa đã có bằng chứng bị lạm dụng. Nếu một credential còn hiệu lực xuất hiện ở nơi người không được cấp quyền có thể đọc, cần xử lý như **potential compromise** dù chưa thấy request bất thường.

Nguồn phát hiện:

- Secret scanning trong repository, pull request, branch, tag, artifact, image.
- CI/CD phát hiện biến môi trường/credential bị echo ra console.
- Hệ thống log thấy pattern Bearer/API key hoặc nội dung nhạy cảm.
- Dịch vụ cung cấp credential cảnh báo key có khả năng lộ.
- SIEM phát hiện truy cập từ client/IP không quen, bất thường về địa lý/tần suất.
- Tăng đột biến lỗi 401/403 rồi có chuỗi request thành công.
- Người dùng báo tài khoản/phiên có hành động lạ.
- Điều tra máy trạm hoặc workload bị xâm nhập.

Hệ thống phát hiện secret cần hạn chế lưu lại **toàn bộ secret trong alert**. Gửi thông báo dạng `credentialType`, fingerprint/ID, nguồn phát hiện, đường dẫn/line tham chiếu đã làm sạch, mức độ nhạy cảm và người chịu trách nhiệm.

### 11.1. Câu hỏi triage đầu tiên

- Credential loại gì? Còn hiệu lực không? Có scope và quyền nào?
- Secret thuộc **production**, staging, test hay tài khoản cá nhân?
- Bị lộ ở đâu? Public repo, internal repo, log collector, ticket, chat, máy trạm hay nơi chưa rõ?
- Ai có khả năng đọc hoặc sao chép? Có thể xác minh thời điểm bắt đầu lộ không?
- Có bằng chứng sử dụng lạ sau thời điểm đó?
- Có thể **revoke ngay** không? Dịch vụ nào sẽ dừng nếu revoke?
- Cần bảo toàn bằng chứng gì trước khi thay đổi trạng thái hoặc dọn dữ liệu công khai?
- Có dấu hiệu **issuer/signing key** hoặc pipeline cấp credential bị xâm nhập, làm nguy cơ lan rộng hơn một key đơn lẻ không?

Trong tình huống khẩn cấp, **không trì hoãn vô hiệu hóa credential nguy hiểm** chỉ để hoàn thành triage. Có thể chụp metadata, event ID và bằng chứng tối thiểu trong khi người khác thực hiện containment.

## 12. Phân loại mức độ nghiêm trọng theo quyền và phạm vi

| Tình huống | Đánh giá ban đầu | Ưu tiên phản ứng |
| --- | --- | --- |
| Secret giả/dummy không từng hợp lệ | Thấp, nếu đã xác minh | Xác nhận tính giả và sửa đường rò |
| Key sandbox chỉ đọc, đã hết hạn | Thường thấp hơn | Kiểm tra quyền và log, dọn nơi lộ |
| API key production chỉ đọc dữ liệu nhạy cảm | Cao tùy tập dữ liệu | Revoke/rotate, điều tra truy xuất dữ liệu |
| Service account production có quyền ghi hoặc xóa | Cao | Thu hồi ngay, giảm quyền, điều tra thay đổi |
| Refresh token/session đặc quyền | Cao | Thu hồi toàn bộ phiên/phạm vi liên quan |
| Khóa ký token của IdP, cloud root/admin key | Rất cao hoặc nghiêm trọng | Điều phối incident nhiều hệ thống, đánh giá phạm vi trust |

Bảng chỉ là hướng dẫn. Severity cuối phải dựa trên **khả năng khai thác, tác động, thời gian tồn tại, phạm vi truy cập và bằng chứng hành vi**. Không tự hạ mức nghiêm trọng chỉ vì “không thấy truy cập bất thường”: log có thể thiếu, bị chậm hoặc có blind spot.

## 13. Runbook 7 giai đoạn khi credential bị lộ

### Giai đoạn 1 — Phát hiện và kích hoạt sự cố

Ghi nhận incident ID, thời điểm phát hiện, nguồn báo, chủ sở hữu credential, môi trường, service bị ảnh hưởng, mức độ ưu tiên ban đầu và người điều phối.

Tạo kênh phối hợp có kiểm soát quyền truy cập. **Không dán credential thật vào chat/ticket**. Nếu cần minh chứng, dùng ID, fingerprint và reference tới kho bằng chứng hạn chế quyền.

Phân công tối thiểu: incident commander/điều phối, người xử lý IAM/secrets, người phụ trách hệ thống, người điều tra bằng chứng và đầu mối truyền thông khi cần.

### Giai đoạn 2 — Khoanh vùng ảnh hưởng và lưu bằng chứng

Thu thập an toàn:

- Nguồn lộ: commit hash, PR, build/job ID, log stream, object/artifact ID hoặc ticket reference.
- Credential ID, issuer, principal, scope, permissions, ngày tạo/hạn dùng và tài nguyên liên quan.
- Audit events từ lần sử dụng hợp lệ cuối cùng đến hiện tại và khoảng thời gian trước đó thích hợp.
- IP/source, workload, user-agent class, request IDs, operation IDs, tài nguyên đã đọc/ghi.
- Các event tạo mới credential, thay IAM, tăng quyền, disable logging, export dữ liệu hoặc triển khai bất thường.

Chỉ cho điều tra viên phù hợp quyền xem bằng chứng nhạy cảm. Ghi hash/checksum của bản xuất, thời điểm và nguồn. Dữ liệu log thiếu trường hoặc không có log phải được **ghi rõ là hạn chế chứng cứ**.

### Giai đoạn 3 — Chặn khả năng dùng credential

Ưu tiên thao tác có hiệu lực nhanh nhất:

1. Vô hiệu hóa hoặc revoke key/token/phiên tại **issuer/provider** nếu có chức năng.
2. Nếu không revoke tức thì được, giảm quyền, khóa principal, thu hồi session hoặc chặn luồng truy cập ở lớp phù hợp.
3. Với token bearer không thể thu hồi theo từng token, dùng denylist, giảm hiệu lực qua session/token epoch, thay signing key hoặc đợi TTL **chỉ khi rủi ro còn lại được chấp nhận có chủ đích**.
4. Với key ở nhiều nơi, kiểm tra mọi bản sao, alias, version và consumer.
5. Nếu nghi issuer bị chiếm quyền, ngừng tin hoặc thay cấu hình trust liên quan; không chỉ đổi credential của một client.

**Không đợi sửa repository rồi mới revoke.** Xóa file/commit hoặc tắt đường link chỉ hạn chế phát tán thêm; người khác có thể đã sao chép secret.

### Giai đoạn 4 — Thay thế và phân phối credential mới

Tạo credential mới bằng issuer/secrets manager, cấp **quyền tối thiểu**, TTL phù hợp và gắn owner cụ thể. Phân phối qua secret manager, workload identity hoặc quy trình quản lý bí mật; không commit secret mới vào repository.

Xác định consumer thật:

- Deployment, service replica, job chạy nền, cron, queue worker.
- CI/CD runner, workflow, integration test, external vendor.
- Connection pool và ứng dụng giữ secret trong bộ nhớ.
- Các vùng/cluster/environment sử dụng cùng credential.

Thực hiện rollout theo dependency graph để giảm gián đoạn; nhưng khi credential nguy hiểm đang bị lạm dụng, **vô hiệu hóa sớm** có thể quan trọng hơn duy trì tương thích. Cần có người phê duyệt quyết định cân bằng rủi ro nếu mở thời gian dùng song song old/new key.

### Giai đoạn 5 — Điều tra và loại bỏ nguyên nhân rò rỉ

- Truy ra commit, log statement, cấu hình/CI step, công cụ upload hoặc sự kiện khiến secret xuất hiện.
- Kiểm tra các nơi sao chép: Git history, fork, cache, artifact registry, image layer, log sink, backup, ticket và message.
- Sửa mã hoặc pipeline để không ghi secret lần nữa.
- Dọn hoặc hạn chế truy cập tài liệu công khai theo quy trình, nhưng **không coi việc xóa bản hiển thị là thu hồi credential**.
- Nếu log chứa secret, coi chính hệ thống log/bản export/backup liên quan là tài sản phải khoanh vùng, hạn chế quyền và xử lý lưu giữ.
- Rà soát lateral movement: key bị lộ có thể được dùng tạo credential khác, tăng quyền hoặc thay policy.

Việc rewrite Git history có thể ảnh hưởng collaborator và không xóa mọi clone/fork. Chỉ làm theo quyết định vận hành phù hợp sau khi đã revoke, bảo toàn bằng chứng và phối hợp owner.

### Giai đoạn 6 — Xác nhận phục hồi và giám sát tăng cường

Chứng minh bằng hành vi:

- Credential cũ bị từ chối trên **đường gọi thật**; nếu provider hỗ trợ, trạng thái revoked được xác minh độc lập.
- Credential mới chỉ hoạt động với scope tối thiểu cần thiết.
- Các service, queue worker, job nền và integration đã cập nhật; error rate và latency trở về mức chấp nhận.
- Không còn job phát hành hoặc ghi log credential cũ/mới.
- Không còn session/token còn hiệu lực ngoài chính sách đã xác định.
- Đã xem xét thao tác đáng ngờ trong khoảng lộ và có hướng xử lý dữ liệu/tài nguyên bị thay đổi.
- Alert theo dõi sử dụng key cũ, auth failures, privilege changes và data export tiếp tục hoạt động.

**Đổi key thành công về mặt thao tác** chưa đồng nghĩa incident đã được khống chế. Cần kiểm tra quyền truy cập phát sinh và các hành động kẻ tấn công có thể đã thực hiện trong thời gian key còn hiệu lực.

### Giai đoạn 7 — Khép sự cố và cải tiến

Ghi timeline, root cause, blast radius, dữ liệu/tài nguyên bị tác động, biện pháp containment, bằng chứng readback/revocation, hệ thống còn chưa chắc chắn và owner cho các việc tiếp theo.

Cập nhật scanner, policy IAM, logging redaction, rotation automation, secret inventory và bài tập diễn tập. Đưa sự cố vào postmortem tập trung học từ hệ thống, không gán lỗi cá nhân khi thiếu bằng chứng.

**Tiêu chí kết thúc:** credential cũ không còn dùng được, đường rò đã xử lý, consumer hoạt động bằng identity mới, điều tra phạm vi ảnh hưởng đạt yêu cầu tổ chức, giám sát ổn định và các nghĩa vụ thông báo/phê duyệt liên quan đã được xử lý.

## 14. Chiến lược revoke/rotate theo từng loại credential

### 14.1. API key tĩnh

**Vấn đề:** key thường được sao chép vào nhiều app/config, sống lâu và khó biết ai đang dùng.

**Hành động:**

1. Xác định key ID, owner, quyền, môi trường và consumer.
2. Disable/revoke key cũ tại API provider; kiểm tra có API revoke thực sự hay chỉ đổi trạng thái trong UI.
3. Sinh key mới với scope tối thiểu, đặt vào secrets manager và cập nhật consumer.
4. Giám sát request dùng key cũ và trạng thái 401/403 từ ứng dụng hợp lệ.
5. Nếu tồn tại cửa sổ sử dụng song song old/new, ghi rõ thời hạn, điều kiện và rủi ro.

Không chọn cách “sửa một dòng trong source” làm biện pháp duy nhất: các deployment hoặc artifact cũ vẫn có thể mang key.

### 14.2. Access token và refresh token OAuth/OIDC

**Access token** có thể là opaque token tra cứu server hoặc JWT tự xác minh. Cách revoke thực tế khác nhau:

- Opaque token có thể bị chặn tại token store/introspection endpoint.
- JWT tự chứa có thể vẫn được service chấp nhận đến khi `exp`, nếu verifier chỉ kiểm chữ ký và không hỏi trạng thái phiên.
- Refresh token thường cần revoke ở authorization server; kiểm tra token family/rotation và phát hiện reuse nếu triển khai có hỗ trợ.
- Với session compromise, có thể vô hiệu hóa session, token family hoặc subject sessions trong phạm vi rủi ro.
- Sau revoke, kiểm tra **các verifier thực** vì cache, token introspection và policy ở mỗi service có thể khác nhau.

**Không coi việc xóa token khỏi browser là thu hồi tại server.** Không ghi lại access token thô để đối chiếu; dùng token ID/`jti` đã được xác thực hoặc fingerprint không thể đăng nhập.

### 14.3. JWT signing key, JWKS và trust store

Đây là loại sự cố khác với mất một token: nếu private key ký bị lộ, kẻ tấn công có thể ký token giả trong phạm vi issuer/algorithm/audience được tin.

Cần:

1. Đánh giá tất cả ứng dụng tin issuer và `kid` liên quan.
2. Tạo khóa ký mới trong KMS/HSM hoặc key management phù hợp.
3. Thay public key/JWKS/trust cấu hình, kiểm soát cache và thời gian chấp nhận key cũ.
4. Vô hiệu hóa việc tin chữ ký từ khóa đã lộ; nếu phải hỗ trợ token cũ tạm thời, cần cơ chế ngăn token giả và chấp nhận rủi ro bằng quyết định rõ ràng.
5. Đánh giá toàn bộ token được ký trong cửa sổ nghi vấn và hành vi phát sinh.
6. Thử các đường xác minh, clock skew, key ID, algorithm pinning và fallback key behavior.

Không tự động tin một `kid` hay URL JWKS do token không xác thực cung cấp để truy nạp khóa tùy ý. Verifier phải khóa issuer, algorithm và trust policy.

### 14.4. Database password

Khi lộ DB credential, cần xem xét cả dữ liệu và luồng kết nối:

- Rotate account password, certificate hoặc identity DB theo khả năng.
- Cập nhật pool/secret reference, restart hoặc refresh connection pool đúng cơ chế.
- Rà soát truy vấn, thay đổi schema, data export, role và tài khoản mới được tạo.
- Nếu account quá nhiều quyền, thu hẹp quyền sau khi đánh giá các dependency hợp lệ.
- Kiểm tra connection còn tồn tại sau khi đổi mật khẩu: đổi password không nhất thiết cắt tất cả session/kết nối đang mở.

Trường hợp mức độ nguy hiểm cao, phải ngắt session và hạn chế network hoặc khóa account trước khi rollout đầy đủ.

### 14.5. mTLS private key và workload identity

Nếu private key của workload bị lộ:

- Thu hồi certificate khi hạ tầng hỗ trợ và đẩy trust/CRL/OCSP/CA policy phù hợp.
- Cấp cặp khóa/certificate mới bằng cơ chế đáng tin; thay deployment hoặc sidecar.
- Kiểm tra cửa sổ chấp nhận certificate cũ, TTL, connection đang mở và identity mapping.
- Rà soát khả năng giả danh workload để gọi service nhạy cảm.
- Nếu nguyên nhân là CA hoặc issuer của certificate bị xâm nhập, mở rộng phạm vi ứng phó tới trust anchor.

Certificate có thời hạn ngắn giảm thời gian khai thác nhưng không thay thế xử lý sự cố trong khi nó còn hợp lệ.

### 14.6. Cloud IAM/access key

- Disable/delete compromised access key hoặc session theo chức năng provider.
- Kiểm tra cloud audit logs về login, API calls, resource creation, policy changes, access key mới, service account giả và dữ liệu đã export.
- Phân tích quyền thực tế thông qua policy, role assumption, resource policy và điều kiện truy cập.
- Rà soát workload tạm và long-lived resources kẻ tấn công có thể tạo để duy trì quyền.
- Chuyển sang short-lived workload identity/role nếu kiến trúc cho phép, giảm phụ thuộc khóa tĩnh.

Không chỉ kiểm tra account gốc. Một key có quyền tạo principal mới có thể để lại **persistence** sau khi bị revoke.

## 15. Điều tra phạm vi ảnh hưởng bằng audit log

Mục tiêu là trả lời: **credential bị lộ có được dùng trái phép không, để làm gì, trong khoảng thời gian nào, và kết quả thực tế là gì?**

Ví dụ giả định có `credentialRef` là ID hoặc fingerprint đã bảo vệ, không phải secret:

~~~sql
SELECT
    occurred_at,
    service,
    actor_id,
    action,
    target_type,
    target_id,
    outcome,
    request_id,
    source_ip
FROM security_audit_events
WHERE credential_ref = :compromised_credential_ref
  AND occurred_at BETWEEN :window_start AND :window_end
ORDER BY occurred_at, event_id;
~~~

Sau đó mở rộng từ request/operation ID sang những service khác và tới **thay đổi dữ liệu** nếu có. Nếu credential dùng qua nhiều client, có thể cần phân đoạn theo identity, environment, source và hành vi.

### 15.1. Checklist câu hỏi điều tra

- **Thời gian:** credential được tạo khi nào, lộ sớm nhất khi nào, lần dùng cuối khi nào, revoke có hiệu lực khi nào?
- **Nguồn:** có IP/region/workload/client bất thường không? Proxy/NAT có làm dữ liệu nguồn thiếu chính xác không?
- **Phân quyền:** có lần bị DENY rồi nhanh chóng có ALLOW? Có thay IAM, role, group, policy không?
- **Tài nguyên:** có export dữ liệu, gọi API đặc quyền, xóa/sửa đối tượng hoặc tạo credential khác?
- **Hậu quả:** thao tác ghi đã commit? Có hàng đợi hoặc job chưa xử lý? Cần rollback/compensating action không?
- **Dấu vết:** có khoảng trống log, dịch vụ mất kết nối audit sink, thay logging config, timestamp lệch hoặc event bị duplicate?
- **Tính hợp lệ của kết luận:** câu nào có bằng chứng trực tiếp; câu nào chỉ là giả thuyết?

### 15.2. Không suy luận quá mức từ IP hoặc vị trí

IP public có thể là VPN, NAT, proxy hoặc địa chỉ egress của cloud. Vị trí địa lý từ IP có sai số; user-agent có thể bị giả. Một source IP lạ chỉ là **tín hiệu**, cần kết hợp với phiên, credential ID, action, tài nguyên và lịch sử hoạt động.

Tương tự, không có request trong một search index **không chứng minh** không bị lạm dụng nếu pipeline thiếu log, retention hết, một API không được instrument hoặc search chưa bao phủ vùng/cluster đúng.

## 16. Ví dụ sự cố: service API key bị commit vào repository

Giả định một developer vô ý commit API key production của Notification Service vào repository có thể được xem công khai. Scanner phát hiện sau 7 phút.

### 16.1. Phát hiện

Event của scanner nên chứa:

~~~json
{
  "eventType": "credential.exposure_detected",
  "incidentId": "INC-2026-104",
  "credentialType": "PROVIDER_API_KEY",
  "credentialRef": "key-fingerprint-7e1",
  "sourceType": "GIT_REPOSITORY",
  "sourceRef": "commit:a1b2c3d",
  "environment": "production",
  "status": "OPEN"
}
~~~

Không gửi API key vào SIEM, email hoặc ticket. Nếu provider có thông tin key ID, dùng ID đó để theo dõi.

### 16.2. Containment và rotation

**T0:** tạo incident, gắn owner, xác minh key còn hiệu lực và quyền gửi thông báo.

**T0 + vài phút (minh họa, không phải SLA):** disable key trên provider; kiểm tra trạng thái từ API/provider; cập nhật secret mới trong secrets manager; triển khai consumer đã điều chỉnh.

**Sau containment:** tìm các request có key ID/fingerprint, số lượng gửi tăng bất thường, nguồn/IP, thông báo gửi ngoài lịch sử hợp lệ và quota bị tiêu thụ. Kiểm tra cloud build logs, image layers, caches, pull request và mọi bản sao.

**Sau remediation:** thêm quy tắc pre-commit/CI secret scan, xóa key khỏi config/mã, hạn chế in secret trong log, chuyển sang cơ chế lấy secret tại runtime và kiểm tra tất cả deployment.

### 16.3. Điều gì được coi là bằng chứng hoàn tất?

- Provider đã vô hiệu hóa key cũ; request dùng key cũ bị từ chối trên đường tích hợp được kiểm soát.
- Consumer mới hoạt động và không còn dùng key cũ.
- Audit cho thấy khoảng phơi lộ được khoanh vùng, các request và hành động đáng ngờ đã được đánh giá.
- Nguyên nhân đưa key vào source và các nơi chứa bản sao đã được xử lý.
- Secret scanning và giám sát hành vi được bổ sung/kiểm chứng.

**Chỉ xóa commit trên nhánh chính không đạt tiêu chí hoàn tất**, vì lịch sử Git, fork và artifact có thể đã chứa key.

## 17. Ví dụ sự cố: access token xuất hiện trong HTTP access log

Giả định frontend gửi `GET /download?access_token=...`; reverse proxy ghi toàn bộ query string rồi chuyển log về một hệ thống nhiều nhân viên có quyền đọc.

**Phản ứng cần thiết:**

1. Tắt ngay việc đưa bearer token vào URL; chuyển sang kênh phù hợp theo thiết kế bảo mật, thường là header được bảo vệ.
2. Thu hồi token/phiên bị ảnh hưởng nếu còn hiệu lực và issuer hỗ trợ; xem xét token family nếu cần.
3. Xác định thời điểm và phạm vi request/log có chứa token, mọi bản export, log mirror, backup và người có quyền truy cập.
4. Hạn chế quyền, cô lập hoặc xử lý bản log nhiễm secret theo quy trình bằng chứng và retention. Không sao chép các dòng token sang công cụ điều tra mới.
5. Kiểm tra truy vấn log, export log, request API trong thời gian token còn hiệu lực.
6. Cập nhật logging middleware để ghi route template và metadata an toàn; kiểm thử tự động xác nhận không xuất token vào log.

**Một secret được ghi vào audit log có thể làm phát sinh incident thứ hai về chính audit log đó.** Vì vậy policy allowlist và kiểm thử redaction phải được thiết kế ngay từ đầu.

## 18. Ví dụ sự cố: khóa ký JWT của Identity Provider bị lộ

Đây thường là trường hợp có blast radius rộng:

- Kẻ tấn công có thể tạo token trông hợp lệ nếu verifier chấp nhận chữ ký bằng khóa bị lộ.
- Việc revoke từng JWT được biết đến **không đủ** nếu attacker có thể ký thêm token mới.
- Phải thay trust key và xem xét tất cả service xác minh token, cache JWKS, issuer configuration và khả năng token tồn tại ngoài danh sách đã phát hành.
- Audit cần so sánh token issuance logs với những request service đã chấp nhận, tìm dấu hiệu token có `jti` không tồn tại hoặc claim bất thường. Tuy nhiên thiếu log phát hành không tự động là kết luận cuối; hệ thống có thể dùng token issuance path khác.
- Cần phối hợp issuer, ứng dụng tiêu thụ, security operations và vận hành để tránh trạng thái một số service tin khóa cũ, số khác đã từ chối.

**Tiêu chí phục hồi:** các verifier đã dùng trust configuration mới, chữ ký từ key cũ không còn được chấp nhận theo chính sách sự cố, legitimate clients hoạt động, và các dấu vết hành vi sử dụng token giả trong khoảng nghi vấn đã được điều tra.

## 19. Triển khai một audit publisher trong Java / Spring Boot

Đối với service Java, nên đặt lớp audit tại **ranh giới ứng dụng và quyết định nghiệp vụ**, thay vì chỉ chèn log trong HTTP filter.

Ví dụ mô hình tối thiểu dùng allowlist field và một publisher chịu trách nhiệm đưa dữ liệu vào kênh audit bền vững:

~~~java
import java.time.Instant;
import java.util.UUID;

public record AuditEvent(
        String schemaVersion,
        UUID eventId,
        Instant occurredAt,
        String service,
        String environment,
        String eventType,
        String actorType,
        String actorId,
        String targetType,
        String targetId,
        String decision,
        String outcome,
        String reasonCode,
        String traceId,
        String operationId) {

    public static AuditEvent create(
            String service,
            String environment,
            String eventType,
            String actorType,
            String actorId,
            String targetType,
            String targetId,
            String decision,
            String outcome,
            String reasonCode,
            String traceId,
            String operationId) {

        return new AuditEvent(
                "1.0",
                UUID.randomUUID(),
                Instant.now(),
                service,
                environment,
                eventType,
                actorType,
                actorId,
                targetType,
                targetId,
                decision,
                outcome,
                reasonCode,
                traceId,
                operationId);
    }
}
~~~

Service nghiệp vụ gọi publisher sau quyết định:

~~~java
public interface AuditPublisher {
    // Với thao tác quan trọng, implementation cần lưu bền vững
    // cùng transaction hoặc theo chính sách durability đã chọn.
    void publish(AuditEvent event);
}

public final class RoleService {
    private final RoleRepository roles;
    private final AuthorizationPolicy policy;
    private final AuditPublisher audit;

    public RoleService(
            RoleRepository roles,
            AuthorizationPolicy policy,
            AuditPublisher audit) {
        this.roles = roles;
        this.policy = policy;
        this.audit = audit;
    }

    public void changeRole(
            String actorId,
            String userId,
            String newRole,
            String traceId,
            String operationId) {

        if (!policy.canChangeRole(actorId, userId, newRole)) {
            audit.publish(AuditEvent.create(
                    "iam-service", "production",
                    "account.role_change",
                    "USER", actorId,
                    "ACCOUNT", userId,
                    "DENY", "FAILURE",
                    "INSUFFICIENT_PERMISSION",
                    traceId, operationId));
            throw new AccessDeniedException("Forbidden");
        }

        roles.changeRole(userId, newRole);

        audit.publish(AuditEvent.create(
                "iam-service", "production",
                "account.role_change",
                "USER", actorId,
                "ACCOUNT", userId,
                "ALLOW", "SUCCESS",
                "ROLE_UPDATED",
                traceId, operationId));
    }
}
~~~

**Đây là đoạn minh họa ranh giới API**, không phải implementation hoàn chỉnh: `RoleRepository`, `AuthorizationPolicy`, `AccessDeniedException` và wiring transaction còn tùy ứng dụng.

Quan trọng hơn: nếu yêu cầu audit không thể thiếu, việc ghi `roles.changeRole` và event **phải cùng transaction** thông qua outbox hoặc cơ chế tương đương. Mẫu trên nếu publisher gửi async sau khi DB commit mà chưa ghi bền vững có thể làm mất audit khi process crash. Với `DENY` không có thay đổi dữ liệu, có thể dùng đường ghi audit độc lập nhưng phải có chính sách khi sink không sẵn sàng.

Không để developer viết `audit.publish(new Event(..., requestHeaders.toString()))`: schema sự kiện không nhận một blob headers/body tùy ý.

### 19.1. Lấy actor từ nguồn đã xác thực

Ở service có Spring Security, actor nên đến từ `SecurityContext` sau xác thực, hoặc từ identity context được xác minh, với xử lý rõ cho principal/service account. Không lấy `actorId` trực tiếp từ payload API nếu client có thể khai báo bất kỳ user nào.

Đối với thay đổi role, cần phân biệt **người thực hiện** và **tài khoản bị thay role**, và ghi cả hành động bị từ chối. Một event chỉ lưu `userId` mà không nói đó là actor hay target rất khó điều tra.

### 19.2. MDC/trace context không phải nguồn sự thật của quyền

`MDC` hoặc OpenTelemetry context thuận tiện cho `traceId`, `spanId` và `requestId`; tuy nhiên MDC là cơ chế truyền ngữ cảnh logging, không phải chỗ xác định quyền.

Với async executor, message consumer hoặc Reactor, ngữ cảnh có thể cần cơ chế propagation riêng. Nếu không, event không có trace ID hoặc gán nhầm request. Thiết kế kiểm thử multi-thread/async và không để request khác ghi đè context.

## 20. Cảnh báo và phát hiện sớm từ audit events

Một số detection rule thực dụng:

| Tín hiệu | Điều kiện gợi ý | Hành động |
| --- | --- | --- |
| Token bị revoke vẫn có yêu cầu sử dụng | Request khớp credentialRef bị vô hiệu | Điều tra client còn dùng bản cũ hoặc cố ý lạm dụng |
| Tăng quyền đột ngột | Service account tạo admin role ngoài lịch | Tạo alert ưu tiên cao và kiểm tra approval |
| Dùng secret từ workload lạ | Secrets Manager ghi actor không thuộc allowlist | Kiểm tra credential của workload |
| Nhiều auth failure rồi một success | Chuỗi hành vi đáng ngờ theo principal/source | Điều tra nguồn và session |
| Cấp key rồi dùng từ vùng/ứng dụng khác thường | Credential mới có hành vi trái baseline | Xác minh người tạo và scope |
| Xuất dữ liệu lớn bất thường | Số request hoặc kích thước vượt mức dự kiến | Kiểm tra quyền và mục đích |
| Audit pipeline im lặng | Không có event từ service đang nhận traffic | Điều tra collector, SDK hoặc cấu hình audit |
| Retention/policy log bị đổi | Thao tác admin tác động audit store | Cảnh báo và kiểm tra thay đổi được phê duyệt |

Cần baseline riêng theo workload và tenant để hạn chế false positive. Một workload chạy đồng thời từ hai region có thể là bình thường; một admin sử dụng VPN cũng vậy. Không tự động khóa rộng mọi account dựa trên một chỉ báo chưa được đánh giá.

Theo dõi **độ phủ audit**: số loại event bắt buộc thực sự được phát, độ trễ từ `occurredAt` đến `recordedAt`, tỷ lệ event schema không hợp lệ, backlog, DLQ và các service ngừng phát event.

## 21. Thiết kế quyền truy cập và quy trình điều tra

Hệ thống audit có thể chứa dữ liệu hành vi nhạy cảm; cần kiểm soát cả hai phía: **bảo vệ người dùng** và **bảo toàn bằng chứng**.

- Chỉ security analyst hoặc owner được phân quyền có thể đọc event liên quan, giới hạn theo tenant/environment/case.
- Khả năng export raw event cần quyền riêng và có audit trail.
- Người vận hành ứng dụng không mặc định có quyền xóa hoặc thay immutable archive.
- Người quản lý khóa mã hóa không đồng thời dễ dàng sửa/xóa tất cả bằng chứng mà không có phê duyệt.
- Truy cập khẩn cấp được cấp có thời hạn, ghi lý do và theo dõi sau khi sử dụng.
- Dashboard hiển thị dữ liệu tối thiểu; truy vấn sâu phải có case/reference và quyền phù hợp.
- Incident report dùng sự kiện đã làm sạch, không kèm secret hoặc tràn lan dữ liệu cá nhân.

Nên có quy trình xử lý yêu cầu xóa/ẩn thông tin hợp lệ mà vẫn bảo đảm nguyên tắc lưu giữ chứng cứ theo chính sách áp dụng. Không tuyên bố “audit log không bao giờ được xóa” nếu tổ chức có nghĩa vụ bảo vệ dữ liệu và giới hạn retention.

## 22. Kiểm thử audit trail và diễn tập incident response

### 22.1. Ma trận kiểm thử kỹ thuật

| Ca thử | Kích thích | Kỳ vọng |
| --- | --- | --- |
| Authentication success | Đăng nhập thành công | Event có actor đúng, issuer/authn method phù hợp, không có token |
| Authentication denied | Request thiếu quyền | Event DENY có reasonCode và target |
| Business action success | Đổi role được cho phép | Event có actor khác target, outcome SUCCESS sau commit |
| Business action failure | DB lỗi khi đổi role | Không ghi SUCCESS giả; có failure/unknown phù hợp |
| Async workflow | Request qua queue và consumer | Event được nối bằng operation ID, phản ánh từng giai đoạn |
| Secret in request | Authorization/API key trong header | Raw credential không xuất hiện ở log, trace, queue audit |
| Outbox retry | Collector down rồi hồi phục | Event được gửi lại, dedup bằng eventId |
| Source identity | Client tự gán `X-User-Id` | Không ghi actor giả nếu chưa xác thực |
| Tampering/retention | Thử sửa/xóa event bằng quyền ứng dụng | Bị chặn hoặc kiểm tra toàn vẹn phát hiện |
| Lost audit pipeline | Sink unavailable | Hành vi fail-open/fail-closed đúng policy, có alert backlog |
| Credential revoke | Revoke key thử nghiệm | Key cũ bị từ chối, key mới hoạt động đúng scope |
| Leak detection | Đưa fake secret vào fixture scanner | Alert chứa fingerprint/reference, không chứa raw secret |

Dùng **secret giả chỉ phục vụ test**. Không cố tình đưa credential production vào repository, log hoặc dịch vụ scan để kiểm tra.

### 22.2. Diễn tập tabletop

Tình huống: phát hiện một refresh token quản trị bị lộ trong build log nội bộ lúc 14:00, nhưng token đã xuất hiện từ 10:00. Đội vận hành cần phối hợp:

1. Ai giữ vai incident commander? Ai có quyền revoke phiên và vô hiệu hóa token family?
2. Những log nào có thể chứa bản sao token, ai được đọc, và có export nào đã diễn ra?
3. Nếu token đã được dùng tạo access token, cần làm gì để vô hiệu hóa access token còn hiệu lực?
4. Những thao tác nào trong 10:00–14:00 cần xem lại: thay quyền, export dữ liệu, tạo key khác?
5. Cần evidence nào để kết luận containment và xác nhận mọi ứng dụng chấp nhận chính sách mới?
6. Nếu IdP/Secrets Manager bị outage, có contingency nào vừa giảm rủi ro vừa bảo vệ dịch vụ quan trọng?

Sau tabletop, cập nhật runbook và owner thật. Một runbook chỉ ghi “rotate key” mà không chỉ rõ **ai có quyền rotate, ở đâu và ứng dụng nào dùng** có thể thất bại trong sự cố thực.

## 23. Những sai lầm thường gặp

**1. Audit toàn bộ request body và header.** Dễ làm lộ secret/PII; chỉ nên ghi field đã xác định và làm sạch.

**2. Chỉ ghi ở Gateway.** Gateway không biết domain transaction đã commit, job async đã hoàn thành hay quyết định nghiệp vụ nào xảy ra.

**3. Tin `X-User-Id` từ client.** Dễ gán danh tính sai; identity phải đi qua xác thực và trust boundary.

**4. Ghi “success” trước khi transaction commit.** Audit nói thay đổi hoàn tất trong khi DB rollback; cần tách ý định, chấp nhận và kết quả.

**5. Gửi log best-effort mà không đo mất event.** Collector có thể down, queue đầy hoặc app crash; cần durability và metric.

**6. Cho operator sửa/xóa audit tùy ý.** Mất khả năng tin vào bằng chứng; dùng tách quyền, immutable retention và kiểm tra toàn vẹn.

**7. Chỉ xóa secret khỏi mã nguồn mà không revoke.** Bản sao đã lộ vẫn có thể dùng được.

**8. Rotate key nhưng không tìm nơi dùng.** Job nền, deployment cũ, image và external integration có thể tiếp tục dùng key cũ hoặc gây outage.

**9. Coi access token và signing key như nhau.** Signing key compromise có thể ảnh hưởng toàn bộ trust domain; revoke một token không xử lý được.

**10. Không điều tra các quyền phát sinh.** Key cũ bị thu hồi nhưng attacker đã tạo key mới, đổi role hoặc xuất dữ liệu.

**11. Tin rằng “không có log bất thường” nghĩa là an toàn.** Phải đánh giá mức độ đầy đủ, độ trễ và blind spot của audit.

**12. Đưa secret nguyên văn vào ticket incident.** Vô tình mở rộng phạm vi rò rỉ qua email, chat, screenshot và hệ thống ticket.

**13. Quá lệ thuộc IP để quyết định lạm dụng.** VPN/proxy/NAT khiến IP không khẳng định được danh tính.

**14. Không diễn tập quyền và thao tác khẩn cấp.** Khi sự cố thực xảy ra mới tìm issuer, provider, owner hoặc quyền revoke thì containment chậm.

## 24. Bài tập tình huống

### Bài A — Chọn field cần ghi

Payment Service xử lý yêu cầu hoàn tiền với `Authorization: Bearer <token>`, `paymentId`, `amount`, `currency`, `reason`. Hãy đề xuất audit event cho hai tình huống: admin được phép hoàn tiền và admin bị từ chối.

**Hướng giải:** có eventId, timestamp, service, actor đã xác thực, target paymentId, action REFUND, decision ALLOW/DENY, outcome, reasonCode, operationId và traceId. Chỉ lưu số tiền/lý do nếu cần cho mục đích kiểm toán và policy dữ liệu cho phép. Tuyệt đối không lưu bearer token.

### Bài B — Phát hiện token lộ trong log

Một access token ngắn hạn xuất hiện trong access log 20 phút trước. Token hiện đã hết hạn. Có thể kết thúc incident ngay vì token hết hạn không?

**Hướng giải:** chưa đủ. Kiểm tra token từng được dùng trong cửa sổ còn hiệu lực, dữ liệu có thể đã truy xuất, vị trí bản log và ai có quyền truy cập, root cause khiến token bị ghi log; xem xét refresh/session liên quan. Hết hạn giúp giảm rủi ro tương lai nhưng không loại bỏ tác động đã xảy ra.

### Bài C — Hành động sau rotate

Cloud access key có quyền tạo IAM principal bị lộ. Đội đã disable key và hệ thống hoạt động bình thường trở lại. Cần kiểm tra gì nữa?

**Hướng giải:** tìm event tạo key/account/role mới, policy changes, resource changes, persistence, network changes và data access trong khoảng nguy cơ. Kiểm tra danh tính được tạo từ key cũ và những quyền còn hiệu lực.

### Bài D — Thiếu audit sau commit

RoleService cập nhật DB thành công rồi publish event đến message broker. Khi broker down, service đã trả HTTP 200 nhưng không có record audit.

**Hướng giải:** với hành động cần audit bền vững, ghi outbox event trong cùng transaction với thay đổi role; dùng publisher retry và consumer dedup. Xác định policy khi không thể ghi outbox, monitor backlog và ingestion lag.

### Bài E — Phân biệt nguồn và subject

Inventory Service nhận request từ Order Service qua mTLS. Order mang header `X-User-Id: admin-1`. Tại sao Inventory không thể đơn giản ghi `actor=admin-1`?

**Hướng giải:** mTLS chỉ xác thực workload Order; không tự chứng minh user admin-1 hay quyền delegation. Inventory cần identity context được ủy quyền/xác minh hoặc ghi caller service cùng subject đáng tin cậy, tránh tin header client giả.

## 25. Checklist triển khai production

### Thiết kế audit

- [ ] Catalog event gồm authn, authz, credential lifecycle, admin action, thay đổi nghiệp vụ nhạy cảm.
- [ ] Schema có eventId, timestamp, actor, action, target, decision, outcome, reason và correlation IDs.
- [ ] Actor lấy từ security context/trust chain; phân biệt caller workload và delegated user.
- [ ] Sự kiện SUCCESS phản ánh kết quả thật; tác vụ async có trạng thái rõ.
- [ ] Audit quan trọng được ghi bền vững, có outbox/retry/dedup khi cần.
- [ ] Audit store có kiểm soát quyền, retention, encryption và cơ chế kiểm tra toàn vẹn.
- [ ] Có metric phát hiện log loss, ingest delay, pipeline outage và thay đổi chính sách audit.
- [ ] Không ghi secret/PII vượt mục đích; có allowlist, masking và test chống rò.

### Ứng phó credential exposure

- [ ] Có inventory credential: owner, issuer, scope, consumer, hạn dùng và cách revoke.
- [ ] Có detector cho source, CI/CD, logs, artifacts và hành vi bất thường.
- [ ] Alert không chứa nguyên văn secret.
- [ ] Runbook có người trực, quyền revoke, kế hoạch rotate và tác động tới consumer.
- [ ] Biết phân biệt API key, access/refresh token, session, DB password, mTLS cert và signing key.
- [ ] Có thủ tục bảo toàn bằng chứng, phân tích thời gian lộ và kiểm tra lateral movement.
- [ ] Kiểm tra credential cũ thật sự bị từ chối, credential mới hoạt động đúng scope.
- [ ] Xác nhận không có secret trong repository, image, CI log, audit export và backup dễ truy cập.
- [ ] Có giám sát tăng cường, truyền thông phù hợp và postmortem sau containment.
- [ ] Đã diễn tập ít nhất một tình huống revoke/rotate cùng kiểm tra log liên service.

## 26. Ghi nhớ

Trong Microservices, **nhật ký kiểm toán là hồ sơ hành vi và quyết định bảo mật xuyên service**, không chỉ là log debug có thêm user ID. Audit hữu ích phải có sự kiện đúng điểm nghiệp vụ, danh tính được xác thực, correlation xuyên luồng, kết quả chính xác và cơ chế chống mất/sửa dữ liệu; đồng thời phải tuyệt đối tránh biến log thành nguồn phát tán credential.

Khi thông tin xác thực bị lộ, quy trình đúng là **phát hiện → xác định phạm vi → chặn/revoke → thay thế/rotate → điều tra hành vi và đường rò → xác nhận phục hồi → cải tiến**. Cắt đường phát tán và thu hồi quyền phải diễn ra kịp thời; xử lý Git history hoặc xóa dòng log chỉ là một phần của remediation. Mục tiêu cuối là chứng minh credential cũ không còn mở cửa, những hành động phát sinh đã được đánh giá, và hệ thống có đủ bằng chứng để tin vào kết luận sự cố.
