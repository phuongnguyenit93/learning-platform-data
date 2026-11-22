# Truyền danh tính người dùng và ngăn lạm dụng quyền trung gian

## 1. Bối cảnh và mục tiêu

Trong microservices, yêu cầu của một người dùng thường đi qua API Gateway, dịch vụ điều phối, dịch vụ nghiệp vụ và các thành phần nội bộ trước khi chạm tới dữ liệu. Mỗi bước có thể chạy bằng danh tính kỹ thuật mạnh hơn quyền của người dùng gốc. Nếu một dịch vụ dùng quyền của chính nó để làm điều mà người dùng không được phép làm, dịch vụ đó đã trở thành **confused deputy** — bên trung gian được tin cậy nhưng bị lợi dụng quyền.

Ví dụ: người dùng chỉ có quyền xem đơn hàng của mình gửi yêu cầu đến Reporting Service. Reporting Service được cấp quyền đọc tất cả hóa đơn để xuất báo cáo. Nếu nó tin tham số `customerId` từ người dùng, rồi dùng tài khoản dịch vụ có quyền rộng để lấy hóa đơn của khách khác, API đã vô tình mở một đường vượt quyền.

Mục tiêu của bài học là hiểu cách truyền **ngữ cảnh danh tính** và **quyền được ủy quyền** qua các lời gọi dịch vụ, trong khi vẫn giữ ranh giới xác thực và phân quyền tại từng tài nguyên.

Sau bài học, bạn có thể:
- Phân biệt danh tính người dùng, danh tính workload và danh tính dịch vụ hành động thay người dùng.
- Nhận diện confused deputy, token forwarding không kiểm soát và việc giả mạo header nội bộ.
- Chọn phương án truyền danh tính bằng access token có audience, token exchange hoặc ngữ cảnh đã xác minh qua hop đáng tin cậy.
- Áp dụng least privilege, kiểm tra quyền tại dịch vụ sở hữu dữ liệu, tenant isolation và kiểm toán chuỗi ủy quyền.
- Thiết kế lời gọi đồng bộ và tác vụ bất đồng bộ không làm mất ranh giới quyền.

## 2. Ba câu hỏi bắt buộc khi một dịch vụ gọi dịch vụ khác

Mọi quyết định truy cập cần biết:

1. **Ai khởi tạo yêu cầu?** Chủ thể người dùng hoặc tác nhân máy được xác thực, ví dụ `user-42`.
2. **Ai đang trực tiếp gọi?** Workload đã xác thực bằng credential riêng, ví dụ `order-service` gọi `billing-service`.
3. **Được phép làm gì với tài nguyên nào?** Hành động, tài nguyên cụ thể, tenant, điều kiện nghiệp vụ và giới hạn ủy quyền.

Ba câu trả lời có thể khác nhau. `order-service` được phép gọi endpoint nội bộ của `billing-service` không có nghĩa `user-42` được đọc mọi hóa đơn.

```text
Người dùng Alice
     |
     | access token dành cho API
     v
API Gateway  --xác thực request-->
     |
     v
Order Service (caller workload = order-service)
     |
     | lời gọi thay Alice, quyền hẹp cho order:read
     v
Billing Service (resource owner)
     |
     | kiểm tra: Alice có quyền đọc hóa đơn này?
     v
Hóa đơn của Alice
```

**Authentication (xác thực)** chứng minh chủ thể là ai. **Authorization (phân quyền)** quyết định chủ thể có được thực hiện hành động cụ thể hay không. **Delegation (ủy quyền)** trao quyền hạn chế cho một bên thực hiện thao tác thay bên khác. **Impersonation (mạo danh theo cơ chế được cho phép)** làm hệ thống nhìn bên trung gian như người dùng; nó cần kiểm soát chặt hơn và không nên là mặc định.

Một token có chữ ký hợp lệ chỉ chứng minh token được cấp theo quy tắc của issuer và không bị sửa. Nó không tự chứng minh người dùng có quyền đọc một bản ghi cụ thể tại thời điểm hiện tại.

## 3. Confused deputy: kịch bản lỗi điển hình

Giả sử kiến trúc:

```text
Browser → Report API → Invoice Service → Database
                    \
                     \- service credential: invoices:read:any
```

Yêu cầu:

```http
GET /reports/invoices?customerId=customer-999
Authorization: Bearer <token-cua-Alice>
```

Một triển khai nguy hiểm:

1. Report API xác thực Alice.
2. Report API lấy `customerId` từ query.
3. Report API dùng service token có quyền `invoices:read:any` để gọi Invoice Service.
4. Invoice Service chỉ kiểm tra service token, rồi trả hóa đơn của `customer-999`.
5. Alice nhận dữ liệu mà mình không sở hữu.

Ở đây Invoice Service thấy một bên gọi có đặc quyền hợp lệ, nhưng **không thấy hoặc không ràng buộc quyền của người khởi tạo**. Report API trở thành deputy bị lợi dụng.

Một hướng sửa phải được triển khai đồng bộ ở cả hai đầu:

- Report API chỉ nhận phạm vi báo cáo mà Alice được phép yêu cầu, không tin `customerId` tự khai.
- Credential được chuyển sang Invoice Service mang thông tin ủy quyền cần thiết hoặc Invoice Service có cơ chế kiểm tra quyền của Alice.
- Invoice Service đối chiếu subject, tenant, resource owner và hành động yêu cầu với dữ liệu đáng tin cậy.
- Quyền hẹp được cấp theo operation, audience và thời hạn; không sử dụng token quản trị toàn cục cho mọi yêu cầu.
- Các truy cập đặc quyền thực sự (batch admin, migration) sử dụng luồng riêng và được kiểm toán.

**Nguyên tắc:** dịch vụ sở hữu tài nguyên phải bảo vệ tài nguyên đó, kể cả khi cuộc gọi đến từ mạng nội bộ.

## 4. Các loại danh tính cần tách biệt

| Loại | Ví dụ | Dùng để chứng minh | Không được hiểu nhầm thành |
| --- | --- | --- | --- |
| End-user identity | `sub=user-42` | Ai là người dùng gốc | Danh tính của workload đang gọi |
| Workload identity | `spiffe://prod/order-service` hoặc identity của service account | Dịch vụ/máy nào tạo kết nối | Quyền của người dùng với dữ liệu |
| Delegated identity/authority | Token có `sub=user-42`, `aud=billing-api`, `scope=invoice:read` | Bên trung gian đang thực hiện quyền được cấp thay người dùng | Quyền vô hạn vì service được tin |
| System actor | `nightly-reconciliation-job` | Tác vụ nền chạy bằng quyền hệ thống xác định | Một người dùng giả |
| Audit identity | `actor=order-service, subject=user-42` | Truy vết ai thực hiện và thay ai | Bằng chứng xác thực độc lập |

Có thể biểu diễn principal trong mô hình nghiệp vụ như sau:

```json
{
  "subject": "user-42",
  "actor": "order-service",
  "tenant": "tenant-a",
  "action": "invoice:read",
  "resourceId": "invoice-731",
  "correlationId": "req-5b20"
}
```

JSON này là **mô hình ngữ cảnh sau khi đã xác minh** hoặc cấu trúc audit, không phải một header mà internet client được phép tự gửi rồi tự động tin. Các trường `subject`, `tenant`, `actor` cần được lấy từ bằng chứng xác thực/ủy quyền hợp lệ.

## 5. Ranh giới tin cậy qua API Gateway

Gateway thường là cổng public đầu tiên: xác thực token, kiểm soát lưu lượng, lọc header không tin cậy và định tuyến. Tuy nhiên “Gateway đã xác thực” không đồng nghĩa các dịch vụ sau có thể bỏ mọi kiểm tra.

Các sai lầm phổ biến:

- Tin `X-User-Id`, `X-Role` hoặc `X-Tenant-Id` do trình duyệt gửi.
- Tin cùng những header đó nếu attacker có thể gọi thẳng service qua đường nội bộ khác.
- Cho rằng mọi container cùng cluster đều đáng tin.
- Dùng header role không được bảo vệ thay cho quyết định chính sách ở dịch vụ sở hữu dữ liệu.
- Để gateway forward token dành cho một dịch vụ sang bất kỳ dịch vụ khác.

Có hai mô hình triển khai hay gặp:

**Mô hình A — Mỗi API xác minh access token:** mỗi service nhận token phù hợp với audience của nó, kiểm tra issuer, thời gian hiệu lực, scope và các policy liên quan. Tính độc lập cao, nhưng cần quy trình phát token phù hợp cho nhiều downstream.

**Mô hình B — Gateway xác minh, mạng nội bộ có danh tính workload và ngữ cảnh đã bảo vệ:** Gateway loại bỏ header giả, tạo ngữ cảnh ở kênh được xác thực và giới hạn, các service xác minh caller/workload và áp dụng policy. Mô hình này yêu cầu ranh giới mạng, mTLS, chính sách nguồn gọi và cơ chế chống giả mạo đủ mạnh; không nên chỉ dựa vào “header có vẻ do gateway tạo”.

Trong cả hai mô hình, **authorization cấp bản ghi và tenant** vẫn phải có nơi chịu trách nhiệm rõ ràng.

## 6. Token forwarding và audience: vì sao không chuyển tiếp mù?

Access token thường được cấp cho một **resource server** hoặc tập tài nguyên cụ thể. Một token có `aud=orders-api` không mặc nhiên được `payments-api` chấp nhận. Nếu dịch vụ B chấp nhận token không đúng audience, token bị đánh cắp hoặc chuyển tiếp sai có thể dùng ở nơi nó không được cấp quyền.

Ví dụ claim mang tính minh họa:

```json
{
  "iss": "https://identity.example.org/",
  "sub": "user-42",
  "aud": "orders-api",
  "exp": 1893456000,
  "scope": "orders:read"
}
```

Orders API cần kiểm tra ít nhất:
- Chữ ký/token validity theo cơ chế phát hành; chỉ nhận thuật toán và key tin cậy.
- `iss` khớp issuer được cấu hình, `aud` dành cho Orders API.
- `exp`, `nbf` nếu có, thời điểm hợp lệ và clock skew có giới hạn.
- Scope/permission phù hợp hành động, cộng thêm quyền trên tài nguyên cụ thể.
- Các ràng buộc tenant, token type và cơ chế revocation/introspection khi hợp đồng đòi hỏi.

**Không được** sửa thủ công JWT để thay `aud` hoặc `scope`. Chữ ký sẽ mất hiệu lực và cách này phá hỏng mô hình cấp quyền.

**Không nên** chấp nhận một bearer token có audience rộng “all-services” chỉ để tiện forward qua mọi hop. Nó làm tăng thiệt hại nếu token lộ và khiến việc xác định caller, mục đích và quyền của từng hop khó hơn.

## 7. On-behalf-of và OAuth 2.0 Token Exchange

Khi Order Service cần gọi Billing Service thay Alice, một giải pháp là **token exchange**: Order chứng minh mình là client tin cậy, gửi bằng chứng về user token cho Authorization Server và xin một token mới **dành riêng cho Billing** với quyền hạn chế.

```text
Alice --user access token--> Orders API
                               |
                               | yêu cầu token exchange,
                               | xác thực client=orders-service
                               v
                        Authorization Server
                               |
                               | delegated token:
                               | subject=Alice
                               | audience=billing-api
                               | scope=invoice:read
                               v
Orders API ----------------> Billing API
                         (token mới cho Billing)
```

Ví dụ request token exchange theo hướng OAuth 2.0 (chỉ minh họa; tham số thực tế phụ thuộc Identity Provider):

```http
POST /oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:token-exchange&
subject_token=<user-access-token>&
subject_token_type=urn:ietf:params:oauth:token-type:access_token&
audience=billing-api&
scope=invoice:read
```

Client còn phải được xác thực theo phương thức do Authorization Server yêu cầu (ví dụ mTLS, private-key JWT hoặc client credential hợp lệ). Không đưa credential vào ví dụ curl hoặc log. Provider phải **thực sự hỗ trợ** token exchange và chính sách delegation; không phải mọi IdP triển khai chuẩn này theo cùng cách.

Authorization Server nên áp dụng:
1. Kiểm tra caller service có quyền exchange token và user token gốc hợp lệ.
2. Giới hạn audience sang Billing API.
3. Chỉ cấp các scope hợp lệ trong **giao của** quyền người dùng, chính sách dịch vụ trung gian và tài nguyên đích.
4. Giữ thời hạn ngắn, không nới rộng hiệu lực hơn nguồn/ủy quyền cho phép.
5. Cấp thông tin actor/delegation chain khi cần kiểm toán và khi profile token hỗ trợ.

**Billing API vẫn kiểm tra quyền sở hữu hóa đơn.** Token có `invoice:read` không nhất thiết cho phép đọc mọi hóa đơn của tenant.

Nếu tổ chức dùng BFF, edge token translation hoặc một protocol khác, mục tiêu vẫn là phân tách token theo audience và ràng buộc quyền đi qua mỗi hop.

## 8. Ngăn mạo danh qua header và request context

Nhiều ứng dụng tạo context nội bộ bằng header:

```http
X-User-Id: user-42
X-Tenant-Id: tenant-a
X-Caller-Service: orders-service
```

Các header này **có thể bị tự gửi bởi client** nếu đi qua HTTP công khai. Để dùng context dạng header nội bộ một cách an toàn, cần ít nhất:

- Edge/Gateway xóa toàn bộ header ngữ cảnh do bên ngoài cung cấp trước khi gắn giá trị nội bộ.
- Chỉ một tập caller được xác thực mới được gửi context tới downstream; mTLS có thể chứng minh danh tính workload của kênh, kết hợp authorization giữa các service.
- Downstream từ chối lời gọi không đi qua trust boundary hợp lệ hoặc caller không thuộc allowlist cho endpoint.
- Giá trị identity được liên kết với token đã xác minh hoặc được ký/bảo vệ theo cơ chế nội bộ có expiry, audience và chống replay khi cần.
- Không cho service tùy ý nâng quyền bằng cách tự thêm `X-Is-Admin: true` hoặc sửa tenant.
- Qua mỗi ranh giới tin cậy, nhận diện rõ ai được phép assert subject và các claim nào được phép chuyển.

Dùng `ThreadLocal` hoặc request-scoped context chỉ là kỹ thuật truyền dữ liệu **trong cùng tiến trình**. Nó không tự cung cấp bằng chứng xác thực xuyên mạng. Khi xử lý async, thread pool hoặc Reactor, cần propagation phù hợp, nhưng phải giữ giới hạn thời gian và tránh rò dữ liệu request giữa các tác vụ.

## 9. mTLS và workload identity: bảo vệ hop, không thay thế user authorization

**Mutual TLS (mTLS)** cho phép cả hai phía kết nối xác thực chứng chỉ của nhau. Với workload identity (chẳng hạn danh tính do service mesh hoặc hệ thống cấp chứng chỉ quản lý), Billing có thể biết nó đang trao đổi với Orders Service.

Tuy nhiên:

```text
mTLS chứng minh:  caller là orders-service.
User token chứng minh: subject là user-42, token được cấp hợp lệ.
Policy quyết định: user-42 có được đọc invoice-731 không?
```

Không được suy luận từ “Orders Service có mTLS” thành “Orders Service được đọc mọi hóa đơn”. Chính sách service-to-service nên giới hạn ai được gọi endpoint nào, còn nghiệp vụ kiểm tra resource-level authorization.

Khi kết hợp mTLS với delegated token, hệ thống có thể ràng buộc token vào client (sender-constrained token) nếu IdP và resource server hỗ trợ. Đây là lớp bảo vệ cao hơn bearer token thuần, nhưng cần cấu hình đồng bộ từ issuer tới consumer.

Tránh quy tắc “nội bộ thì bỏ auth” vì kết nối nội bộ có thể xuất phát từ service bị xâm nhập, SSRF hoặc một workload có cấu hình sai.

## 10. Authorization tại dịch vụ sở hữu dữ liệu

Phân quyền thường gồm nhiều tầng:

| Tầng | Quyết định điển hình |
| --- | --- |
| Gateway | Token hợp lệ? Tốc độ truy cập? Route công khai? |
| Service ingress | Caller workload được gọi endpoint không? Token có audience và scope đúng không? |
| Domain/application | Người dùng có quyền thực hiện thao tác trong trạng thái nghiệp vụ hiện tại không? |
| Data access | Query có ràng buộc tenant, owner hoặc policy bắt buộc không? |

Ví dụ sai:

```sql
SELECT * FROM invoices
WHERE invoice_id = :invoiceId;
```

Nếu `invoiceId` do Alice gửi và service có credential đọc toàn bộ bảng, query này có thể rò dữ liệu (IDOR/BOLA).

Ví dụ an toàn hơn khi quyền chỉ cho phép người dùng đọc hóa đơn của chính họ:

```sql
SELECT invoice_id, total_amount, status
FROM invoices
WHERE invoice_id = :invoiceId
  AND tenant_id = :verifiedTenantId
  AND owner_user_id = :verifiedUserId;
```

`verifiedTenantId` và `verifiedUserId` phải đến từ context đã xác minh, **không lấy trực tiếp** từ query/body untrusted. Nếu quy tắc cho phép kế toán xem hóa đơn của đơn vị, hãy xây chính sách rõ ràng cho role và phạm vi tổ chức, không vá bằng cách bỏ điều kiện owner cho mọi request mang role “admin”.

Đối với quyền phức tạp, một Policy Decision Point (PDP) hoặc thư viện phân quyền tập trung có thể đưa ra quyết định; tuy nhiên dịch vụ sở hữu dữ liệu vẫn phải truyền đủ thuộc tính, áp dụng kết quả và tránh bypass qua đường dữ liệu khác.

## 11. Bài toán đa tenant và quyền trung gian

**Tenant isolation** là ranh giới đặc biệt quan trọng. Một service có credential đọc toàn bộ cơ sở dữ liệu không được cho phép caller lựa chọn tenant bất kỳ mà thiếu ủy quyền.

Tình huống:
- Alice thuộc `tenant-a`.
- URL có `/tenants/tenant-b/invoices`.
- Report Service thay Alice gọi Invoice Service với service token mạnh.
- Invoice Service tin tenant ở URL và trả dữ liệu tenant-b.

Chặn lỗi này bằng cách:

1. Lấy tenant đã xác minh từ identity/session hoặc nguồn membership đáng tin.
2. Kiểm tra Alice có thuộc tenant được yêu cầu và có quyền ở tenant đó không.
3. Truyền tenant trong delegated context được bảo vệ hoặc để resource service tự tra cứu mapping.
4. Khi query DB, áp dụng predicate tenant bắt buộc; nếu có Row-Level Security (RLS), coi đó là defense in depth.
5. Kiểm tra lại quyền với thao tác nhạy cảm khi membership hoặc role có thể thay đổi trong lúc token còn hiệu lực.

Đừng dùng `tenantId` làm khóa cache mà bỏ `subject`, role, policy version hoặc phạm vi có liên quan, vì kết quả cho một user có thể bị trả sai cho user khác.

## 12. Dịch vụ nền và luồng bất đồng bộ: không giả làm người dùng

Message broker, batch job và event handler thường chạy sau khi request HTTP đã kết thúc. Access token của người dùng có thể hết hạn trước khi consumer xử lý; ghi nguyên token vào queue cũng tạo nguy cơ lộ credential và replay.

Thay vào đó, sự kiện nên chứa **dữ liệu nghiệp vụ tối thiểu và metadata đã kiểm chứng**, ví dụ:

```json
{
  "eventType": "InvoiceRequested",
  "operationId": "op-721",
  "tenantId": "tenant-a",
  "requestedBy": "user-42",
  "authorizationDecisionId": "authz-993",
  "requestedAt": "2026-11-12T00:00:00Z"
}
```

Producer phải xác thực và phân quyền trước khi phát event. Consumer xác thực nguồn sự kiện theo cơ chế broker, kiểm tra schema, tenant và quyền **phù hợp với thời điểm thực thi** nếu thao tác đòi hỏi quyền còn hiệu lực. Một quyết định cho phép tại thời điểm enqueue không mặc nhiên cho phép mọi thao tác nhiều giờ sau.

Các mô hình thường dùng:
- **Service authority:** job thực hiện một nghiệp vụ hệ thống có quyền riêng, phạm vi hẹp và audit subject là system actor; `requestedBy` chỉ là metadata.
- **Delegated authorization:** job có grant/capability thích hợp, có thời hạn và phạm vi hạn chế, được xác minh lúc tiêu thụ.
- **Re-authorization:** consumer truy vấn hệ thống chính sách khi chạy nếu membership, trạng thái hoặc rủi ro đã thay đổi.

Không phát bearer token gốc vào event, log, trace hoặc dead-letter queue. Khi retry event, giữ nguyên operation ID/idempotency key để chống xử lý trùng và bảo đảm kết quả gắn với cùng nghiệp vụ.

## 13. Quyết định thiết kế: context propagation, authorization và audit

Một giao kèo cho lời gọi từ Order tới Billing có thể định nghĩa:

```text
Operation: GET /internal/invoices/{id}
Caller service: order-service (được xác thực workload)
Delegated subject: user có quyền invoice:read
Token audience: billing-api
Scope: invoice:read
Resource check: invoice.tenant == subject.tenant
                và subject có quyền trên invoice.id
Deadline: từ request gốc
Audit: actor, subject, tenant, invoiceId, decision, traceId
```

Đây là hợp đồng tổng thể; các lớp thực thi phải thống nhất. Đừng để team Gateway nghĩ rằng Billing tự kiểm tra owner, trong khi team Billing lại tin rằng Gateway đã kiểm tra owner.

Cần phân biệt:
- **Audit trail:** ai yêu cầu, ai gọi thay, quyền nào được sử dụng, tài nguyên nào được chạm tới, kết quả allow/deny.
- **Distributed tracing:** request đi qua service nào, latency/errors, correlation ID; có thể liên kết audit nhưng không nên chứa token hoặc dữ liệu cá nhân không cần thiết.
- **Business log:** trạng thái đơn hàng/hóa đơn; không dùng nó làm bằng chứng duy nhất cho authorization.

Với quyền quản trị có khả năng hành động thay người khác, chính sách nên có scope cụ thể, mục đích, thời hạn ngắn, quy trình phê duyệt nếu cần, và audit tách biệt user/actor.

## 14. Ví dụ triển khai kiểm tra qua nhiều tầng

Giả sử Alice gọi:

```http
GET /orders/order-83/receipt
Authorization: Bearer <access-token-for-orders-api>
```

Luồng đúng có thể là:

1. Gateway chuyển tới Orders API; Orders xác thực token có `aud=orders-api`, subject Alice và permission đọc đơn hàng.
2. Orders truy vấn quyền sở hữu `order-83` và tenant của Alice; nếu không đủ quyền thì từ chối ngay.
3. Orders cần hóa đơn từ Billing; Orders xin delegated token cho `billing-api`, scope `invoice:read`, subject Alice.
4. Billing xác thực cả workload caller là Orders và delegated token, kiểm tra audience/scope rồi soát quyền Alice trên invoice thuộc `order-83`.
5. Billing chỉ trả dữ liệu cần cho receipt (data minimization), Orders trả kết quả.
6. Cả hai dịch vụ ghi audit với cùng correlation ID nhưng không log bearer token.

Mã giả tại Billing minh họa thứ tự kiểm tra:

```java
ReceiptData readInvoice(String invoiceId, AuthContext context) {
    requireTrustedCaller(context.workload(), "orders-service");
    requireAudience(context.token(), "billing-api");
    requireScope(context.token(), "invoice:read");

    Invoice invoice = repository.findById(invoiceId)
        .orElseThrow(NotFoundException::new);

    if (!policy.canReadInvoice(
            context.subject(),
            context.verifiedTenant(),
            invoice)) {
        throw new AccessDeniedException("Not authorized");
    }
    return ReceiptData.from(invoice);
}
```

Đây là **pseudocode thiết kế**, không phải API trực tiếp của một framework. `AuthContext` chỉ được tạo bởi middleware xác thực đáng tin. Nếu muốn tránh lộ sự tồn tại bản ghi cho user khác, API có thể trả `404` thay `403` theo hợp đồng đã chọn; không được vì vậy bỏ kiểm tra quyền.

## 15. Failure mode và cách khắc phục

| Failure mode | Vì sao nguy hiểm | Cách chặn |
| --- | --- | --- |
| Bỏ kiểm tra `aud` | Token dành cho API khác được dùng sai nơi. | Mỗi resource server kiểm tra audience, issuer và scope. |
| Chuyển tiếp raw user token qua mọi hop | Tăng bề mặt lộ credential và quyền quá rộng. | Exchange hoặc cấp token đích có phạm vi hẹp. |
| Chỉ tin `X-User-Id` | Client hoặc workload giả header. | Strip header ở edge; ngữ cảnh có xác thực, mạng/kênh được bảo vệ. |
| Service account toàn quyền dùng cho truy cập người dùng | Confused deputy đọc/ghi dữ liệu user khác. | Ràng buộc subject, tenant, resource và action; tách luồng system. |
| Quyền chỉ kiểm tra ở Gateway | Internal endpoint và data layer có thể bypass. | Kiểm tra tại dịch vụ sở hữu tài nguyên. |
| Tin tenant từ URL/body | Cross-tenant data leak. | So khớp với membership đã xác minh; query tenant-scoped. |
| Đưa access token vào message | Token hết hạn, lộ qua broker/DLQ, replay. | Event metadata tối thiểu, capability hoặc re-authorization. |
| Cache quyết định thiếu resource/tenant | Dùng kết quả allow sai đối tượng. | Cache key đúng context, TTL/invalidation thích hợp. |
| Chỉ log user, không log actor | Không truy ra service đã thực hiện hành động. | Audit cả subject, actor và decision. |
| Truyền full JWT vào telemetry | Lộ bearer token qua log/trace. | Redaction; chỉ log identifier không nhạy cảm. |

## 16. Kiểm thử bảo mật theo kịch bản

**Kịch bản A — Giả mạo header:** gọi public Gateway kèm `X-User-Id: admin` và token của Alice. Xác nhận backend chỉ thấy Alice từ nguồn đã xác minh. Thử gọi trực tiếp internal endpoint bằng một workload chưa được phép; phải từ chối.

**Kịch bản B — Nhầm audience:** gửi token hợp lệ nhưng có `aud=orders-api` đến Billing API. Kết quả phải bị từ chối dù chữ ký đúng.

**Kịch bản C — IDOR:** Alice sửa `invoiceId` thành hóa đơn của Bob trong cùng tenant. Billing vẫn từ chối hoặc trả not found theo chính sách chống lộ tồn tại.

**Kịch bản D — Cross-tenant:** Alice dùng token của tenant-a truy cập URL tenant-b. Đảm bảo predicate và policy chặn ở cả service nghiệp vụ và đường truy xuất dữ liệu.

**Kịch bản E — Confused deputy:** Reports Service có service credential mạnh; yêu cầu report của Alice nhắm tài nguyên khách khác. Kiểm tra quyền user gốc được cưỡng chế, không thể lợi dụng credential dịch vụ.

**Kịch bản F — Token exchange:** thử xin audience/scope lớn hơn mức người dùng và caller được cho phép; Authorization Server không cấp. Token dành Billing không được Orders API/Payments API khác chấp nhận nếu audience không phù hợp.

**Kịch bản G — Bất đồng bộ:** user bị thu hồi quyền sau khi enqueue nhưng trước khi xử lý. Xác minh job thực thi theo chính sách đã chọn: re-authorization hoặc capability có thời hạn, không vô tình chạy với token user hết hạn.

Mỗi phép thử cần kiểm tra **kết quả truy cập**, **số lần thao tác có tác dụng phụ**, **decision audit** và **log không chứa token**. Unit test policy là cần thiết nhưng không thay integration test qua Gateway, service và data layer.

## 17. Bài tập

**Bài 1 — Vẽ chuỗi danh tính.** Xây luồng `Client → Gateway → Checkout → Payment`. Ở mỗi hop, ghi rõ subject, workload caller, token audience, scope và nơi kiểm tra quyền trên payment. Tìm một điểm có khả năng xuất hiện confused deputy.

**Bài 2 — Chặn BOLA.** Một endpoint `GET /documents/{id}` dùng service account có quyền đọc toàn bảng. Hãy viết điều kiện truy cập theo `verifiedUserId`, `verifiedTenantId`, resource owner và policy cộng tác nhóm.

**Bài 3 — Chọn cơ chế delegation.** Orders cần gọi Shipping thay user nhưng Shipping không chấp nhận token của Orders. Giải thích cách token exchange giúp giới hạn audience và scope; nêu yêu cầu đối với Authorization Server, caller authentication và audit chain.

**Bài 4 — Thiết kế worker.** User yêu cầu xuất dữ liệu, kết quả trả sau vài phút. Hãy xác định những thông tin được đưa vào event, quyền nào kiểm tra lúc enqueue và lúc consume, chính sách khi user bị thu hồi quyền và cách tránh lưu bearer token.

**Bài 5 — Threat modeling.** Liệt kê các đường bypass: direct pod access, giả mạo header, service token lộ, SSRF, cache sai tenant và token nhầm audience. Với mỗi đường, xác định kiểm soát ở edge, network, resource service và data layer.

## 18. Ghi nhớ

- **Danh tính người dùng, workload caller và quyền được ủy quyền là ba khái niệm khác nhau.** Đừng gộp chúng thành một header “user”.
- **Confused deputy xảy ra khi một dịch vụ dùng quyền mạnh của nó để đáp ứng yêu cầu mà người khởi tạo không được phép thực hiện.**
- Token phải có **issuer, audience, scope, hạn dùng** và chính sách phù hợp; delegated token nên hẹp hơn quyền gốc.
- **mTLS xác thực service-to-service**, không thay kiểm tra quyền người dùng trên tài nguyên.
- **Service sở hữu dữ liệu phải kiểm tra subject, tenant, resource và action**; Gateway không phải điểm bảo vệ duy nhất.
- Với event và job nền, truyền **ngữ cảnh đã xác minh và operation ID**, tránh lưu hoặc chuyển tiếp raw bearer token.
- Audit phải cho biết **ai khởi tạo, service nào hành động thay, quyết định nào được áp dụng và tài nguyên nào bị tác động**.

### Đọc thêm

- OAuth 2.0 Framework — RFC 6749: https://www.rfc-editor.org/rfc/rfc6749
- OAuth 2.0 Token Exchange — RFC 8693: https://www.rfc-editor.org/rfc/rfc8693
- OAuth 2.0 Bearer Token Usage — RFC 6750: https://www.rfc-editor.org/rfc/rfc6750
- JSON Web Token Best Current Practices — RFC 8725: https://www.rfc-editor.org/rfc/rfc8725
- OAuth 2.0 Token Introspection — RFC 7662: https://www.rfc-editor.org/rfc/rfc7662
- OWASP API Security Top 10: https://owasp.org/API-Security/

Các RFC và hướng dẫn nêu trên cung cấp khung thuật ngữ. Khả năng hỗ trợ token exchange, cách phát claim và chính sách ở từng Identity Provider vẫn cần đối chiếu với triển khai cụ thể.
tạo thanh toán cho đơn của U với delegated token hợp lệ | Cho phép theo nghiệp vụ, audit lưu subject U và actor Order Service. |
| User U đổi `orderId` thành đơn của V cùng tenant | Từ chối do resource ownership, dù scope có `payments.charge`. |
| User U gửi `tenantId` của tenant khác | Từ chối, không coi body/route là nguồn cấp quyền. |
| Client thêm `X-User-Id: admin`, `X-Roles: ADMIN` | Bị loại bỏ/không được tin; request không được nâng quyền. |
| Token hợp lệ chữ ký nhưng `aud` dành cho Orders gửi tới Payments | Payments từ chối. |
| Token sai issuer, hết hạn, chưa có hiệu lực hoặc chữ ký sai | Từ chối trước business operation. |
| Inventory Service dùng service credential gọi Payments Refund | Từ chối do workload không có quyền. |
| Order Service xin exchange token scope `payments.admin` ngoài phạm vi | Authorization Server từ chối; không tự tăng scope. |
| User đã mất quyền trước khi consumer chạy job nhạy cảm | Áp dụng đúng policy revalidation/snapshot đã chọn, không tự cho phép. |
| Hai message cùng operation được redeliver | Idempotency bảo vệ side effect và audit phản ánh việc lặp. |
| Token/JWKS/introspection/PDP không khả dụng | Hành vi fail-closed theo policy, không fallback sang tin header giả. |
| Caller gọi thẳng nội bộ bỏ qua Gateway | Yêu cầu vẫn bị kiểm tra bằng cơ chế service AuthN/AuthZ. |

Cần kiểm tra ở **đường dẫn thật**: Gateway, service method, gRPC method, background consumer và data-access policy. Unit test cho validator hữu ích nhưng chưa chứng minh proxy/sidecar bỏ header giả, credential có đúng audience hay mọi route đều bị chặn.

Khi dùng test token, ký bằng test issuer/key riêng và cấu hình trust tách môi trường; không hardcode production token/secret vào repository hoặc CI logs.

## 17. Case study: Checkout bị lợi dụng làm “người gọi thay mặt” quá quyền

### Thiết kế yếu

```text
User U → POST /checkout?orderId=O-of-V → Checkout
                                           |
                                           | service key có payments:admin
                                           ▼
                                         Payment
                                           |
                                     charge order O-of-V
```

Checkout xác thực U nhưng không kiểm tra owner của `orderId`. Payment thấy service key hợp lệ và thực hiện thao tác. Đây là confused deputy: caller U điều khiển đầu vào khiến Checkout sử dụng quyền cao của mình để làm điều U không có quyền.

### Thiết kế cải tiến

1. Checkout xác minh access token của U, scope thao tác checkout và tenant hợp lệ.
2. Checkout tra cứu đơn trên backend, xác nhận quan hệ U–Order, trạng thái, số tiền và các điều kiện nghiệp vụ trước khi phát lệnh.
3. Khi gọi Payment, Checkout dùng delegated token `aud=payments-api`, scope tối thiểu `payments.charge`, subject U và workload identity Checkout được chứng thực.
4. Payment xác thực token, caller, delegation và tự kiểm tra `orderId`, số tiền, tenant, điều kiện nghiệp vụ theo nguồn tin cậy.
5. Payment dùng idempotency key ổn định cho operation thanh toán, tránh retry gây nhân đôi giao dịch.
6. Cả hai service audit subject U, actor Checkout, action, resource và quyết định; không ghi bearer token.

```text
Client(U)
  │ user token
  ▼
Checkout
  ├── AuthN token + AuthZ owner/order/tenant
  ├── Token Exchange (subject U, audience Payment, scope charge)
  └── HTTPS/mTLS + delegated access token ──────> Payment
                                                    ├── validate issuer/audience/scope
                                                    ├── authenticate caller/workload
                                                    ├── authorize U + resource + tenant
                                                    ├── enforce idempotency
                                                    └── commit + audit
```

Để tránh double charge khi timeout, trạng thái thanh toán không rõ phải được xác minh theo operation ID thay vì tự tạo giao dịch mới với idempotency key khác. Đây là yêu cầu tính đúng đắn nghiệp vụ đi kèm bảo mật.

## 18. Mô hình đe dọa và checklist thiết kế

Khi thêm một API nội bộ, hãy trả lời:

1. **Caller nào có thể đến API này?** Công khai, Gateway, service, job hay message consumer? Mỗi đường vào được xác thực bằng gì?
2. **Subject và actor là ai?** Lời gọi đại diện cho user hay workload? Dấu vết delegation có thể được chứng minh không?
3. **Token được cấp cho audience nào?** Service có xác minh issuer, signature, time và audience không?
4. **Scope/permission nào được cấp?** Có thể trao token quyền nhỏ hơn cho downstream thay vì forward quyền rộng không?
5. **Ai kiểm tra resource-level policy?** Owner, tenant, trạng thái, thuộc tính của object và quyền thao tác lấy từ nguồn nào?
6. **Service có quyền rộng ở tầng dưới không?** Caller có thể điều khiển ID, đường dẫn, query, amount, tenant để lợi dụng quyền đó không?
7. **Đường đi bất đồng bộ có thay đổi ý nghĩa ủy nhiệm không?** Token hết hạn, quyền thu hồi, redelivery, provenance và idempotency được xử lý thế nào?
8. **Khi không xác minh được policy thì sao?** Có fail closed, phân loại lỗi, log đúng mức và giới hạn số lần retry không?
9. **Credential có thể rò sang hệ thống không liên quan không?** Xem proxy, redirect, outbound HTTP client, event payload, baggage và log.
10. **Đã thử tấn công âm tính chưa?** Header spoofing, cross-tenant, cross-user, wrong audience, service lateral movement, direct internal call.

Đánh dấu “đã xác thực” tại Gateway chỉ hoàn thành một phần câu hỏi 1 và 3. Quyền trên tài nguyên và quyền của service trung gian vẫn là trách nhiệm ở mỗi ranh giới.

## 19. Bài tập áp dụng

### Bài 1 — Nhận diện confused deputy

Admin Report Service có service account đọc mọi invoice. Endpoint `GET /invoices/{invoiceId}` chỉ kiểm tra user đã đăng nhập và sau đó truy vấn invoice theo ID. Hãy:
- Chỉ ra quyền nào bị lạm dụng và đầu vào nào attacker điều khiển.
- Đề xuất phép kiểm tra subject–tenant–invoice–action.
- Chỉ ra những nơi cần AuthN/AuthZ: Gateway, Report Service và data access.
- Viết một test người dùng tenant A yêu cầu hóa đơn tenant B.

### Bài 2 — So sánh hai đường truyền token

Cho chuỗi Gateway → Cart → Pricing → Payment. Client token có `aud=public-api` và `scope=checkout.start`. Hãy mô tả vì sao forward cùng token tới Payment là sai nếu Payment chỉ chấp nhận `aud=payments-api`; đề xuất chuỗi token exchange, các scope nhỏ nhất và nơi ghi actor.

### Bài 3 — Review trust boundary

Một team chuyển `X-User-Id` và `X-Roles` từ Gateway đến mọi service vì “traffic đều ở VPC”. Hãy xác định ít nhất ba cách vượt quyền, quy tắc strip/rewrite header và cơ chế để downstream xác minh caller. Giải thích tại sao mTLS đơn thuần không tự chứng minh quyền user trên một resource.

### Bài 4 — Quyền trong message queue

Order Service phát `OrderPaymentRequested`, Worker xử lý sau 30 phút. Thiết kế payload tối thiểu, provenance, authorization decision tại lúc phát và/hoặc lúc xử lý, quyền của worker, idempotency và hành vi khi user bị thu hồi quyền trong khoảng chờ.

## 20. Ghi nhớ

- **Luôn phân biệt người dùng (subject) với service thực gọi (actor).** Hai bên có thể phải được cho phép độc lập.
- **Một token hợp lệ chưa đồng nghĩa được quyền trên mọi tài nguyên.** Audience, scope, tenant, ownership và trạng thái nghiệp vụ có vai trò khác nhau.
- **Service trung gian có quyền mạnh là điểm dễ bị confused deputy.** Không cho caller điều khiển resource hoặc quyền sử dụng của service mà thiếu kiểm tra.
- **Không tin user/role/tenant header từ client.** Header chỉ có giá trị bảo mật trong một trust boundary được xác thực và bảo vệ rõ ràng.
- **Giới hạn delegation theo audience, scope, thời gian và caller.** Token exchange là một cách triển khai khi IdP hỗ trợ, không phải lý do để mở rộng quyền.
- **Mỗi service bảo vệ operation và resource của chính mình.** Gateway, mTLS và service credential là lớp bổ sung, không thay thế authorization nghiệp vụ.
- **Giữ đầy đủ subject, actor, action, resource, tenant trong audit,** nhưng không ghi token/secret vào log.

Truyền danh tính đúng nghĩa là mang theo **bằng chứng và phạm vi ủy quyền có thể kiểm tra**, để mỗi service tự bảo vệ tài nguyên của mình. Khi mọi chặng đều xác thực caller, giới hạn quyền được chuyển giao và xét quyền của người dùng trên tài nguyên thật, service trung gian sẽ không trở thành con đường leo thang đặc quyền.
