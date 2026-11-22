# Gateway không thay thế object authorization trong service

API Gateway là lớp kiểm soát quan trọng ở biên hệ thống. Gateway có thể xác thực token, giới hạn tốc độ, lọc request, định tuyến tới service, áp dụng chính sách theo route và ghi nhận metadata vận hành. Tuy nhiên, gateway thường không có đủ ngữ cảnh nghiệp vụ để quyết định người gọi được đọc hoặc thay đổi một object cụ thể hay không.

Object authorization phải được thực thi trong service có trách nhiệm với dữ liệu và nghiệp vụ. Service biết object thuộc tenant nào, ai là owner, caller có quan hệ chia sẻ nào, trạng thái hiện tại có cho phép hành động hay không và thao tác có tạo side effect gì. Nếu chỉ dựa vào gateway, một route có thể được bảo vệ ở mức “được gọi API” nhưng vẫn cho phép người dùng truy cập dữ liệu của người khác bằng cách thay ID.

Trong API Security, gateway và service là hai lớp bổ sung cho nhau. Gateway bảo vệ điểm vào và áp dụng các chính sách chung; service xác minh quyền chức năng, quyền trên object và điều kiện nghiệp vụ trước khi đọc hoặc thay đổi dữ liệu. Không được xem request đã đi qua gateway hoặc token đã hợp lệ là bằng chứng caller có quyền trên mọi object.

## 1. Gateway làm tốt điều gì?

Gateway nằm giữa client và backend, thường xử lý các tác vụ dùng chung cho nhiều API:

- TLS termination hoặc quản lý kết nối TLS/mTLS theo kiến trúc.
- Xác minh token ở mức chữ ký, issuer, audience, expiry và một số claim.
- Kiểm tra API key, client identity hoặc scope chung.
- Route theo host, path, method, version hoặc header được tin cậy.
- Rate limiting, quota, burst control và giới hạn kích thước request.
- WAF, lọc một số dạng payload độc hại và chuẩn hóa request.
- CORS policy, request ID, logging và telemetry ở biên.
- Chặn endpoint không được expose và giới hạn network access tới backend.

Những kiểm soát này giảm tải cho service và tạo một lớp bảo vệ nhất quán. Ví dụ gateway có thể từ chối request thiếu scope `invoices:read` trước khi request đi vào Invoice Service.

Tuy nhiên, scope `invoices:read` chỉ cho biết caller có thể sử dụng chức năng đọc hóa đơn theo phạm vi token. Nó không tự trả lời caller có được đọc hóa đơn `INV-9001` của tenant khác hay không.

## 2. Object authorization giải quyết câu hỏi khác

Object authorization quyết định principal có thể thực hiện action nào trên một tài nguyên cụ thể. Policy thường phụ thuộc vào nhiều dữ kiện:

| Thành phần | Ví dụ |
|---|---|
| Principal/actor | `user-123`, service identity hoặc delegated user |
| Action | `READ`, `UPDATE`, `DELETE`, `EXPORT`, `REFUND` |
| Object | Invoice `INV-9001`, Order `ORD-1002` hoặc file đính kèm |
| Tenant/context | `tenant-A`, workspace, project hoặc account |
| Relationship | Owner, member, assigned agent, explicit share grant |
| Attributes | Mức phân loại dữ liệu, trạng thái object, amount hoặc region |
| Business state | Đơn đã giao, hóa đơn đã khóa, payment đã hoàn tiền |

Ví dụ, Alice có scope `invoices:read` nhưng chỉ được đọc hóa đơn của mình hoặc hóa đơn được chia sẻ hợp lệ. Bob có cùng scope nhưng chỉ được đọc dữ liệu trong tenant của Bob. Cả hai request có thể vượt qua gateway authentication và function-scope check, nhưng service vẫn phải quyết định riêng theo object.

Một biểu thức policy minh họa:

```text
ALLOW khi:
  principal đã được xác thực
  AND principal có permission invoices:read
  AND invoice thuộc tenant đang hoạt động của principal
  AND principal là owner hoặc có grant READ còn hiệu lực
  AND trạng thái invoice cho phép đọc
```

Gateway thường không sở hữu hoặc không truy vấn authoritative data cần cho các điều kiện này. Nếu cố đưa toàn bộ policy nghiệp vụ vào gateway, policy sẽ bị phân tán, trùng lặp và dễ lệch với service/database.

## 3. Ví dụ BOLA khi gateway đã xác thực thành công

Giả sử API Gateway xác minh JWT và yêu cầu scope `invoices:read`. Alice gửi:

```http
GET /api/invoices/INV-1001 HTTP/1.1
Authorization: Bearer <alice-access-token>
```

Gateway xác nhận token hợp lệ và scope đúng, sau đó chuyển request tới Invoice Service. Alice thay ID thành hóa đơn của Bob:

```http
GET /api/invoices/INV-9001 HTTP/1.1
Authorization: Bearer <alice-access-token>
```

Nếu service chỉ truy vấn `findById("INV-9001")` và trả dữ liệu, hệ thống có lỗi Broken Object Level Authorization (BOLA), dù gateway đã xác thực token hoàn toàn đúng.

Điều kiện tối thiểu trong service phải ràng buộc truy vấn với principal/tenant hoặc kiểm tra policy tương đương trước khi trả dữ liệu. Không thể sửa lỗi này chỉ bằng cách bật thêm JWT validation ở gateway.

## 4. Phân chia trách nhiệm giữa gateway và service

Một cách phân chia thực tế:

| Kiểm soát | Gateway/edge | Service/domain |
|---|---|---|
| TLS, kết nối, host và route | Chính | Có thể xác minh mTLS/service identity ở hop nội bộ |
| Token signature/issuer/audience/expiry | Có thể xác minh sớm | Xác minh lại khi service là resource server độc lập hoặc cần trust boundary riêng |
| Scope/permission ở mức API/route | Có thể áp dụng lớp coarse-grained | Thực thi quyền chức năng authoritative cho nghiệp vụ |
| Object ownership/ACL/relationship | Thường không đủ dữ liệu | Bắt buộc kiểm tra |
| Tenant/object query filter | Không nên dựa vào gateway | Bắt buộc áp dụng trong truy vấn/service/data layer |
| Business state và workflow | Không phải trách nhiệm chính | Bắt buộc kiểm tra trước side effect |
| Rate limit/body size/IP policy | Lớp biên rất phù hợp | Bổ sung quota theo tenant/operation/cost |
| Data masking/field-level response | Có thể hỗ trợ một số quy tắc chung | Service biết schema và dữ liệu nên quyết định authoritative |
| Audit | Ghi nhận edge request | Ghi quyết định object/action và side effect nghiệp vụ |
| Async job/queue | Không kiểm soát đầy đủ sau khi request rời gateway | Worker phải xác minh identity, tenant, object và quyền thực thi |

Gateway có thể từ chối sớm để tiết kiệm tài nguyên. Service vẫn phải bảo đảm an toàn nếu request tới từ một đường vào khác, một service nội bộ hoặc một gateway policy bị cấu hình sai.

## 5. Vì sao gateway không có đủ ngữ cảnh object?

Có một số lý do kiến trúc khiến gateway không nên là nơi duy nhất thực thi object authorization:

1. **Dữ liệu thay đổi liên tục:** owner, ACL, membership, tenant state và business state có thể thay đổi sau khi gateway đã cache token hoặc claim.
2. **Object nằm trong domain service:** Invoice Service biết hóa đơn thuộc khách hàng nào; gateway không nên phải hiểu schema và quan hệ của từng domain.
3. **Policy phụ thuộc nhiều quan hệ:** một người có thể được chia sẻ file, được giao ticket hoặc có quyền tạm thời trên project.
4. **Một endpoint có nhiều object:** bulk request, nested resource, export và search cần kiểm tra từng object hoặc giới hạn tập kết quả.
5. **Nhiều entry point:** REST, GraphQL, gRPC, queue consumer, scheduled job và service-to-service call có thể cùng truy cập dữ liệu.
6. **Gateway không phải ranh giới duy nhất:** backend có thể bị gọi trực tiếp do cấu hình mạng, ingress, port-forward hoặc đường nội bộ.

Nếu gateway gọi thêm service để truy vấn quyền trên mỗi request, nó sẽ trở thành một điểm phụ thuộc nghiệp vụ lớn, có nguy cơ tăng latency, tạo coupling và vẫn không thể thay thế kiểm tra gần nơi dữ liệu được đọc/ghi. Service sở hữu dữ liệu là nơi thích hợp để thực thi policy cuối cùng.

## 6. Không tin header định danh do client tự gửi

Một số gateway truyền context cho backend bằng header như:

```http
X-Authenticated-User: user-123
X-Tenant-Id: tenant-A
X-User-Roles: FINANCE
```

Các header này chỉ đáng tin nếu gateway xóa giá trị cùng tên do client gửi và tự tạo lại từ identity đã xác minh, đồng thời backend chỉ nhận traffic qua kênh/gateway tin cậy. Nếu backend có thể truy cập trực tiếp hoặc header client được giữ nguyên, attacker có thể tự gửi:

```http
X-Authenticated-User: admin
X-Tenant-Id: tenant-B
X-User-Roles: SUPER_ADMIN
```

Service không được dùng các header do internet client tự khai làm nguồn authorization. Có thể chọn một trong các mô hình:

- Service tự xác minh access token đã ký và kiểm tra issuer/audience/expiry.
- Gateway truyền một token nội bộ có audience riêng, thời hạn ngắn và được ký bởi issuer tin cậy.
- Dùng mTLS/workload identity giữa gateway và service, kèm identity propagation được xác thực.
- Dùng signed context có chữ ký, audience, expiry và ràng buộc request; không dùng header thuần văn bản.

Ở gateway, phải strip các header định danh/authorization do client cung cấp trước khi gắn context tin cậy. Ở service, kiểm tra nguồn gọi và token/context. Network allowlist chỉ là lớp bổ sung; không biến header không ký thành credential.

## 7. Gateway xác thực JWT không có nghĩa service phải tin mọi claim

JWT là dữ liệu được ký, nhưng claim chỉ đáng tin khi token được xác minh theo đúng trust configuration. Service cần hiểu token được phát hành cho ai và mục đích gì.

Các kiểm tra quan trọng:

- Chữ ký hợp lệ với key/algorithm được cho phép.
- `iss` đúng issuer tin cậy.
- `aud` chứa audience của service nhận.
- `exp`, `nbf` và các time claim hợp lệ.
- Token type và client phù hợp với loại API.
- Scope/role được ánh xạ theo contract; không nhầm `SCOPE_` với `ROLE_`.
- Tenant claim hoặc membership được xác minh theo chính sách và không bị client ghi đè.

Nếu gateway xác minh token rồi chuyển nguyên bearer token tới service, service có thể xác minh lại để bảo vệ trust boundary. Nếu gateway đổi token sang một internal token, token đó cần audience riêng và không được có quyền rộng hơn mức cần thiết. Không truyền token của user tới mọi downstream service một cách mặc định.

Với service-to-service, dùng workload identity và permission riêng cho service caller. Không đồng nhất quyền của service account với quyền của người dùng cuối. Nếu service đang thực hiện hành động thay user, phải truyền/kiểm tra delegation context có kiểm soát.

## 8. Ví dụ Spring: kiểm tra object trong service

Gateway có thể kiểm tra scope ở route level:

```text
GET /api/invoices/** requires scope invoices:read
```

Invoice Service tiếp tục kiểm tra permission và giới hạn truy vấn theo principal/tenant. Ví dụ:

```java
@RestController
@RequestMapping("/api/invoices")
@RequiredArgsConstructor
class InvoiceController {
    private final InvoiceService invoiceService;

    @GetMapping("/{invoiceId}")
    @PreAuthorize("hasAuthority('SCOPE_invoices:read')")
    InvoiceResponse getInvoice(
            @PathVariable UUID invoiceId,
            @AuthenticationPrincipal Jwt jwt) {
        UUID tenantId = UUID.fromString(
                jwt.getClaimAsString("tenant_id"));
        String subject = jwt.getSubject();
        return invoiceService.getVisibleInvoice(
                tenantId, subject, invoiceId);
    }
}
```

Service dùng tenant và subject từ principal đã được xác minh:

```java
@Service
@RequiredArgsConstructor
class InvoiceService {
    private final InvoiceRepository invoiceRepository;
    private final InvoiceMapper invoiceMapper;

    @Transactional(readOnly = true)
    InvoiceResponse getVisibleInvoice(
            UUID tenantId, String subject, UUID invoiceId) {

        Invoice invoice = invoiceRepository
                .findVisibleTo(tenantId, subject, invoiceId)
                .orElseThrow(InvoiceNotFoundException::new);

        return invoiceMapper.toResponse(invoice);
    }
}
```

Repository có thể giới hạn dữ liệu ngay trong query:

```sql
SELECT i.*
FROM invoice i
WHERE i.tenant_id = :tenant_id
  AND i.public_id = :invoice_id
  AND (
      i.owner_subject = :subject
      OR EXISTS (
          SELECT 1
          FROM invoice_access_grant g
          WHERE g.invoice_id = i.id
            AND g.tenant_id = i.tenant_id
            AND g.subject = :subject
            AND g.permission = 'READ'
            AND g.revoked_at IS NULL
            AND g.expires_at > CURRENT_TIMESTAMP
      )
  );
```

Ví dụ minh họa cần điều chỉnh theo schema và policy thật. Không nhận `tenantId` hoặc `subject` từ request body/query. Nếu JWT claim tenant có thể cũ hoặc người dùng có nhiều tenant, cần kiểm tra membership/active tenant context theo thiết kế của hệ thống. `@PreAuthorize` kiểm tra function permission; query/service mới thực thi object permission.

## 9. Kiểm tra quyền trước khi trả dữ liệu hoặc tạo side effect

Service phải hoàn tất authorization trước khi:

- Serialize object hoặc đưa dữ liệu vào response.
- Cập nhật database, xóa object hoặc thay đổi owner.
- Phát event, ghi outbox hoặc enqueue background job.
- Gọi payment, email, notification hoặc dịch vụ downstream.
- Tạo signed URL, export file hoặc cấp share token.
- Cập nhật cache chứa dữ liệu phụ thuộc principal/tenant.

Ví dụ endpoint hủy đơn hàng không nên gọi Order Service hoặc Payment Provider chỉ vì gateway đã xác minh scope `orders:cancel`. Service cần kiểm tra caller có quyền trên order cụ thể, order thuộc tenant hợp lệ, trạng thái cho phép hủy và có đủ điều kiện hoàn tiền hay không.

Nếu policy phụ thuộc trạng thái có thể thay đổi đồng thời, thực hiện kiểm tra và cập nhật trong transaction/optimistic locking phù hợp. Tránh kiểm tra quyền rồi chờ lâu trước side effect khiến quan hệ hoặc trạng thái đã thay đổi.

## 10. List, search, export và bulk cần policy ở service

Object authorization không chỉ áp dụng cho endpoint dạng `GET /resource/{id}`. Những endpoint trả nhiều object cần giới hạn tập kết quả ngay ở tầng truy vấn.

Ví dụ:

```http
GET /api/invoices?customerId=customer-B
POST /api/invoices/bulk-export
POST /api/reports/generate
```

Service cần bảo đảm:

- Filter tenant/owner/ACL được áp dụng phía server trước pagination.
- `totalCount`, facet, aggregate và autocomplete không tiết lộ object ngoài phạm vi.
- Client không thể đổi `tenantId`, `ownerId` hoặc `customerId` để mở rộng quyền.
- Bulk operation kiểm tra quyền trên từng object hoặc dùng truy vấn chỉ trả tập object được phép.
- Contract quy định rõ all-or-nothing hay partial result.
- Export chỉ chứa dữ liệu caller được phép xem tại thời điểm tạo và/hoặc thời điểm tải theo policy.
- Signed URL được cấp sau authorization, có object scope hẹp và TTL ngắn.

Gateway có thể giới hạn số ID hoặc body size, nhưng không biết ID nào thuộc quyền của caller. Việc đó phải do service/domain/data layer thực hiện.

## 11. Direct backend access và gateway bypass

Một giả định nguy hiểm là “mọi request đều đi qua gateway”. Trong thực tế, backend có thể bị truy cập trực tiếp qua:

- Public load balancer hoặc ingress phụ.
- Kubernetes NodePort/LoadBalancer service hoặc port-forward.
- Internal DNS, service mesh route hoặc network peering.
- Hostname cũ, IP trực tiếp hoặc môi trường staging bị expose.
- Một service khác gọi backend bằng HTTP client riêng.
- Endpoint management/debug có listener khác.

Giảm rủi ro bằng cách:

- Không public trực tiếp application service nếu không cần.
- Dùng private network, firewall/security group và service mesh policy để giới hạn đường gọi.
- Xác thực workload identity/mTLS giữa gateway và service.
- Bảo đảm service vẫn có authentication/authorization nếu bị gọi trực tiếp.
- Không coi source IP nội bộ là bằng chứng duy nhất về danh tính.
- Kiểm thử truy cập trực tiếp backend và các hostname/port phụ.

Network architecture có thể làm gateway bypass khó xảy ra hơn, nhưng service-level authorization vẫn cần tồn tại như ranh giới bảo vệ dữ liệu.

## 12. Nhiều gateway và nhiều entry point không làm mất yêu cầu object authorization

Một hệ thống có thể có public gateway, partner gateway, internal gateway, BFF và gateway riêng cho mobile. Mỗi gateway có thể áp dụng policy khác nhau. Nếu object authorization chỉ được cấu hình ở một gateway, các entry point khác có thể bỏ sót.

Service là nơi hợp nhất policy cho object thuộc domain của nó. Tất cả entry point phải tạo ra identity context đáng tin cậy và gọi cùng service policy. Cần tránh copy-paste logic owner/tenant ở từng gateway hoặc controller vì các bản sao có thể lệch nhau.

Với GraphQL, gateway có thể xác thực endpoint `/graphql`, nhưng resolver/service phải kiểm tra quyền cho từng field, object và mutation. Với gRPC, interceptor có thể kiểm tra identity/scope, còn method/domain service vẫn cần object policy. Với WebSocket, xác thực handshake không cấp quyền vĩnh viễn cho mọi message; quyền cần được kiểm tra theo action và resource.

## 13. Service-to-service authorization và quyền thay mặt người dùng

Khi Service A gọi Service B, cần xác định rõ ai là actor:

- Service A đang thực hiện tác vụ hệ thống bằng workload identity của chính nó?
- Service A đang thay mặt Alice thực hiện một hành động mà Alice khởi tạo?
- Service A có delegation grant để thao tác trên object của Bob không?

Không mặc định service identity có quyền đọc mọi object mà downstream service lưu trữ. Quyền của service cần giới hạn theo operation, tenant hoặc resource scope.

Nếu cần giữ ngữ cảnh người dùng cuối, có thể dùng token exchange/on-behalf-of flow hoặc delegation token có audience và scope riêng. Service B cần xác minh cả caller service lẫn actor/delegation context, sau đó áp dụng object authorization. Không tin header `X-User-Id` do service A tự gửi nếu không có cơ chế xác thực và ràng buộc.

Với background job, message queue hoặc scheduled task, gateway thường không tham gia lúc worker thực thi. Worker phải xác minh workload identity, tenant/job scope, actor/delegation và trạng thái quyền theo policy. Việc request ban đầu đã qua gateway không tự cấp quyền vĩnh viễn cho job.

## 14. Cache không được biến gateway authorization thành quyền dùng chung

Một route có thể được gateway cho phép, nhưng response cache dùng chung theo URL sẽ làm lộ dữ liệu nếu response phụ thuộc principal hoặc tenant.

Ví dụ hai người cùng gọi:

```http
GET /api/invoices/INV-9001
```

Nếu cache key chỉ là path và response của Bob được lưu trước, Alice có thể nhận dữ liệu của Bob khi gateway cho phép route chung. Service hoặc cache layer phải:

- Thực hiện authorization trước khi trả response cache.
- Partition cache theo tenant/principal/permission context khi dữ liệu phụ thuộc vào các yếu tố đó.
- Không dùng public/shared cache cho response riêng tư.
- Invalidate khi owner, grant, tenant state hoặc object data thay đổi.
- Kiểm thử cùng URL bằng nhiều principal và tenant.

Gateway cache chỉ phù hợp với dữ liệu public hoặc dữ liệu có cache policy rõ ràng. Không coi việc gateway đã xác thực request ở lần đầu là đủ để chia sẻ response cho mọi caller sau đó.

## 15. Defense in depth: gateway vẫn nên áp dụng coarse-grained policy

Nói gateway không thay thế object authorization không có nghĩa gateway không cần kiểm soát quyền. Gateway vẫn nên áp dụng các policy chung để giảm request không hợp lệ trước khi tới service:

- Chặn route không tồn tại hoặc không được public.
- Xác minh token và client identity theo trust configuration.
- Kiểm tra scope/permission coarse-grained nếu có thể làm nhất quán.
- Rate limit theo client, tenant và route.
- Giới hạn payload, method, timeout và concurrency.
- Chặn protocol downgrade, TLS yếu và một số request bất thường.
- Strip header định danh do client tự gửi; tạo context tin cậy.
- Ghi edge audit và correlation ID.

Service vẫn thực thi policy domain/object. Nếu gateway từ chối request, service không cần nhận request đó. Nếu gateway cho qua, service không được hiểu đó là quyết định allow trên object.

## 16. Xử lý 401, 403 và 404 theo đúng lớp

Thông thường:

- Gateway có thể trả `401` khi credential thiếu hoặc không hợp lệ theo cơ chế xác thực ở biên.
- Gateway có thể trả `403` khi caller thiếu scope/permission coarse-grained của route.
- Service có thể trả `403` khi principal không được phép thực hiện action trên object.
- Service có thể dùng `404` cho object không tồn tại hoặc ngoài phạm vi caller nếu policy yêu cầu che giấu sự tồn tại.

Status code cụ thể cần nhất quán với API contract. Không để gateway biến mọi lỗi service thành `401` hoặc `403` khiến client không phân biệt được authentication failure, function authorization và object authorization.

Response không nên tiết lộ object tồn tại hay không nếu chính sách yêu cầu che giấu. Log nội bộ có thể ghi decision layer, permission, policy ID và correlation ID mà không trả chi tiết đó cho client. Không ghi token hoặc payload nhạy cảm.

## 17. Kiểm thử để chứng minh service không phụ thuộc gateway

Kiểm thử cần đi qua gateway và gọi trực tiếp service trong môi trường test để xác minh cả hai đường. Dùng ít nhất Alice/Bob trong cùng tenant và Carol ở tenant khác.

| Tình huống | Kết quả mong đợi |
|---|---|
| Token hợp lệ, scope đúng, object thuộc caller | Cho phép nếu business state hợp lệ |
| Token hợp lệ, scope đúng, object thuộc user khác cùng tenant | Service từ chối |
| Token hợp lệ, scope đúng, object thuộc tenant khác | Service từ chối và không trả dữ liệu |
| Gateway cho qua nhưng service không tìm được grant/owner | Service từ chối |
| Gọi trực tiếp backend không qua gateway | Vẫn yêu cầu identity tin cậy và object authorization |
| Client giả mạo `X-User-Id` hoặc `X-Tenant-Id` | Không thay đổi principal/tenant context |
| Gateway token hợp lệ nhưng audience sai với service | Service từ chối nếu service xác minh token độc lập |
| Service account gọi object ngoài scope | Service từ chối |
| Bulk request chứa ID của nhiều tenant | Chỉ xử lý object được phép theo contract; không rò rỉ object bị cấm |
| Cache cùng URL giữa Alice và Bob | Không trả response của người này cho người kia |
| Queue job chạy sau khi quyền bị thu hồi | Worker xử lý theo policy quyền hiện tại/snapshot đã phê duyệt |
| Object state thay đổi trước side effect | Service kiểm tra lại state và từ chối hành động không còn hợp lệ |
| Gateway policy bị tắt trong test | Service vẫn bảo vệ dữ liệu object |

Ví dụ integration test với Spring Security Test:

```java
@Test
void validScopeDoesNotAllowReadingAnotherUsersInvoice()
        throws Exception {
    Invoice invoiceOfBob = testData.createInvoice(
            "bob", "tenant-A");

    mockMvc.perform(get("/api/invoices/{id}", invoiceOfBob.publicId())
                    .with(jwt().jwt(token -> token
                            .subject("alice")
                            .claim("tenant_id", "tenant-A"))
                            .authorities(new SimpleGrantedAuthority(
                                    "SCOPE_invoices:read"))))
            .andExpect(status().isNotFound());
}
```

Ví dụ trên kiểm tra service/controller security path trong ứng dụng Spring; nó không chứng minh network path trực tiếp đã bị chặn. Cần có test riêng gọi service qua ingress/port nội bộ được phép trong môi trường test và xác minh header giả mạo không được tin. `jwt()` tạo principal giả lập, không kiểm tra chữ ký JWT thật.

## 18. Kiểm thử gateway policy và service policy độc lập

Nên có hai nhóm test riêng:

**Gateway tests** xác minh:

- Token thiếu/sai bị chặn.
- Route/method không được public bị từ chối.
- Scope coarse-grained được kiểm tra đúng.
- Rate/body size/timeout và header stripping hoạt động.
- Gateway tạo request ID và identity context tin cậy.

**Service tests** xác minh:

- Token/principal hoặc workload identity được xác minh theo trust boundary.
- Function authorization đúng.
- Object/tenant/relationship policy đúng.
- Không tin header client tự khai.
- Kiểm tra business state trước side effect.
- List, search, file, bulk, cache và async path giữ cùng policy.

Một test end-to-end qua gateway hữu ích nhưng không thay thế test service độc lập. Nếu chỉ test gateway, service có thể bị lỗi khi được gọi từ một entry point khác. Nếu chỉ test service, gateway có thể route nhầm hoặc không strip header giả mạo.

## 19. Monitoring và audit theo từng lớp

Gateway và service có góc nhìn khác nhau, vì vậy telemetry nên bổ sung cho nhau:

| Lớp | Sự kiện nên ghi |
|---|---|
| Gateway | Host/route template/method, client identity, auth result, scope decision, rate-limit decision, request ID |
| Service | Principal/service identity, tenant context, action, object reference an toàn, object authorization decision, policy ID |
| Domain workflow | Business-state decision, approval, side effect, idempotency/job ID |
| Worker | Workload identity, tenant/job scope, authorization result tại thời điểm thực thi, retry/cancel result |

Không ghi bearer token, refresh token, cookie, raw payload hoặc toàn bộ object. Dùng route template và reference phù hợp thay vì dữ liệu nhạy cảm. Alert khi service nhận request từ đường gọi không mong đợi, tenant context không khớp, object authorization denial tăng bất thường hoặc gateway/service có quyết định policy lệch nhau.

Log gateway cho biết request đã qua biên như thế nào. Log service cho biết quyết định truy cập object thực tế. Không thể suy ra quyết định thứ hai chỉ từ log `200` của gateway.

## 20. Checklist thiết kế

- [ ] Gateway thực hiện TLS, route, authentication và coarse-grained scope/rate policy phù hợp.
- [ ] Service sở hữu dữ liệu thực thi function authorization, object authorization và business rules.
- [ ] Không coi token hợp lệ hoặc request qua gateway là quyền trên mọi object.
- [ ] Tenant/subject context đến từ principal hoặc signed delegation đáng tin cậy.
- [ ] Gateway strip header định danh do client tự gửi trước khi thêm context.
- [ ] Backend không public trực tiếp nếu không cần; nếu có nhiều entry point, service vẫn bảo vệ object.
- [ ] JWT được xác minh đúng issuer, audience, signature, expiry và token type tại trust boundary.
- [ ] Truy vấn list/search/bulk/file giới hạn theo tenant và object permission ở service/data layer.
- [ ] Authorization hoàn tất trước khi trả dữ liệu, tạo job, phát event hoặc gọi downstream.
- [ ] Service-to-service và worker có workload identity/delegation scope rõ ràng.
- [ ] Cache key và cache response không chia sẻ dữ liệu giữa principal/tenant.
- [ ] GraphQL, gRPC, WebSocket, webhook và queue path áp dụng cùng domain policy.
- [ ] Có test gateway riêng và service riêng, gồm direct backend, spoofed header và cross-tenant access.
- [ ] Audit/monitoring ghi decision ở gateway và service mà không lưu credential.

## Kết luận

Gateway bảo vệ biên hệ thống bằng authentication, route policy, scope coarse-grained, rate limit và các kiểm soát chung. Nó không thay thế object authorization vì service mới có đủ ngữ cảnh về owner, tenant, quan hệ truy cập, dữ liệu và trạng thái nghiệp vụ. Hãy thực thi object policy gần nơi dữ liệu được truy vấn hoặc thay đổi, giữ identity propagation có xác thực, kiểm tra cả đường gọi trực tiếp và bất đồng bộ, đồng thời test gateway/service độc lập. Khi gateway và service cùng thực hiện đúng vai trò, một token hợp lệ hoặc một route được phép không thể tự biến thành quyền truy cập object ngoài phạm vi.
