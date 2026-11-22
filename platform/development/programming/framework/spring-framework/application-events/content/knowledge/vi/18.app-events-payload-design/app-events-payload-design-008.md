# Actor, tenant và thông tin ngữ cảnh trong payload của Spring Application Events

## 1. Mục tiêu của bài

Một domain event không chỉ cần nói **điều gì đã xảy ra** mà thường còn cần trả lời **ai thực hiện**, **sự thật thuộc tenant nào**, **từ thao tác hay luồng xử lý nào** và **sự kiện xảy ra vào thời điểm nào**. Những thông tin này giúp consumer xử lý đúng dữ liệu, phân tích sự cố, tạo audit trail và giữ ranh giới cô lập trong hệ thống đa tenant.

Ví dụ về một sự thật nghiệp vụ:

```text
InvoiceApproved
  invoiceId      = INV-7
  tenantId       = tenant-blue
  actor          = HUMAN:user-42
  correlationId  = REQ-9
  eventId        = <UUID riêng của occurrence>
  occurredAt     = <thời điểm phê duyệt>
```

**Ý nghĩa:** hóa đơn `INV-7` của `tenant-blue` đã được phê duyệt bởi danh tính người dùng `user-42` trong luồng xử lý `REQ-9`. `tenantId` và `actor` không phải thuộc tính thay thế cho hành vi kiểm tra quyền: chúng là metadata mô tả sự thật **sau** khi hệ thống đã xác thực và cho phép thao tác.

Bài này tập trung vào thiết kế **payload của domain event**, đặc biệt khi Spring Framework phân phối sự kiện qua `ApplicationEventPublisher` và `@EventListener`. Các nguyên tắc cũng hữu ích khi một domain event được chuyển thành integration event, nhưng việc gửi qua broker cần thêm hợp đồng tin cậy và bảo mật riêng.

**Nguyên tắc quan trọng:** dữ liệu ngữ cảnh trong event phải là **ảnh chụp tối thiểu, đã được xác thực và phù hợp với nghiệp vụ tại thời điểm sự thật xảy ra**. Không đặt nguyên HTTP request, SecurityContext, access token, session hoặc entity mutable vào event.

## 2. Phân biệt bốn câu hỏi dễ trộn lẫn

| Thuộc tính | Câu hỏi | Ví dụ | Điều nó không bảo đảm |
| --- | --- | --- | --- |
| `actor` | Ai/cái gì thực hiện hoặc khởi xướng hành động? | `HUMAN:user-42` | Không tự chứng minh người đó đã được cấp quyền |
| `tenantId` | Dữ liệu/sự thật này thuộc phạm vi tenant nào? | `tenant-blue` | Không thay thế điều kiện lọc tenant khi đọc/ghi DB |
| `correlationId` | Các bước nào thuộc cùng một luồng xử lý logic? | `REQ-9` | Không phải thông tin xác thực hay ràng buộc quyền |
| `eventId` | Đây là occurrence cụ thể nào của event? | UUID | Không tự tạo exactly-once delivery |
| `causationId` | Lệnh/event nào trực tiếp dẫn đến fact này? | `CMD-123` hoặc event ID | Không tự tạo thứ tự xử lý được bảo đảm |
| `occurredAt` | Sự thật nghiệp vụ xảy ra khi nào? | UTC Instant | Không nhất thiết bằng lúc listener xử lý |

Không nhất thiết mỗi event phải có **mọi** trường; cần chọn một contract rõ ràng theo yêu cầu. Tuy nhiên, với event của hệ thống multi-tenant, việc thiếu tenant identity khi tenant là bắt buộc có thể dẫn đến xử lý nhầm dữ liệu. Ngược lại, với sự kiện thật sự toàn hệ thống, không được bịa `tenantId="default"` chỉ để đủ schema.

### Actor khác chủ sở hữu đối tượng

Trong thao tác “nhân viên hỗ trợ khóa tài khoản khách hàng”:

- `actor`: nhân viên hỗ trợ đã thực hiện hành động.
- `subject` hoặc `targetUserId`: khách hàng bị khóa tài khoản.
- `tenantId`: tenant sở hữu tài khoản, hoặc tenant được tác động theo policy.
- `initiator`/`onBehalfOf`: có thể cần nếu thao tác được ủy quyền hoặc một service hành động thay người dùng.

Đừng đặt `actorId = targetUserId` chỉ vì cả hai là ID người dùng. Với sự kiện audit nhạy cảm, nhầm actor và subject có thể tạo lịch sử hành động sai.

## 3. Actor: thiết kế danh tính thực hiện hành động

Actor là danh tính mà domain sử dụng để quy trách nhiệm hoặc mô tả nguồn tác động. Actor không nhất thiết luôn là một người đăng nhập.

Các loại hay gặp:

| Loại actor | Ví dụ | Cách thể hiện |
| --- | --- | --- |
| Người dùng đã xác thực | Nhân viên `user-42` phê duyệt hóa đơn | `HUMAN:user-42` |
| Service nội bộ | Dịch vụ billing tự đối soát | `SERVICE:billing-service` |
| Scheduled/system process | Job hết hạn subscription | `SYSTEM:renewal-scheduler` |
| Đối tác đã xác thực | Webhook từ payment provider | `SERVICE:payment-provider-a` hoặc loại actor riêng theo domain |
| Hành động ủy quyền | Agent thực hiện theo ủy quyền của người dùng | `actor` và `onBehalfOf` được phân biệt rõ |

Không mặc định mọi công việc không có HTTP request đều là “anonymous”. Một scheduled job có identity hệ thống; một service-to-service call cần định danh service đã được kiểm chứng. Nếu domain có actor vô danh thực sự, nên mô hình hóa một loại riêng theo policy, thay vì dùng chuỗi rỗng hoặc `null` rồi để consumer tự đoán.

### 3.1. Dùng kiểu có ý nghĩa, không dùng chuỗi mơ hồ

Một mẫu Java 17:

```java
public enum ActorKind {
    HUMAN, SERVICE, SYSTEM
}

public record ActorRef(ActorKind kind, String id) {
    public ActorRef {
        Objects.requireNonNull(kind, "kind");
        Objects.requireNonNull(id, "id");
        if (id.isBlank()) {
            throw new IllegalArgumentException("actor id is blank");
        }
    }
}
```

Đây là đoạn khai báo minh họa; cần import `java.util.Objects`. Cặp `kind/id` giúp tránh nhầm `user-42` và một service có ID tình cờ trùng giá trị.

Nếu dùng hệ thống quản lý danh tính có nhiều miền (realm), cần cân nhắc thêm `issuer` hoặc `identityProviderId`. Ví dụ hai tenant dùng cùng local username `alice` không có nghĩa đó là một người. Trong hệ thống tích hợp, định danh nên là **stable ID**, không phải email hiển thị hoặc tên có thể đổi.

### 3.2. Actor nên được xác định ở ranh giới tin cậy

Trong ứng dụng dùng Spring Security, thông tin người dùng đã xác thực thường được truy cập qua `SecurityContextHolder` hoặc principal do controller nhận từ security integration. Tuy nhiên:

- Không lấy `actorId` trực tiếp từ HTTP body nếu đây là hành động cần xác thực.
- Không coi một header tùy ý `X-Actor-Id` là sự thật chỉ vì client gửi nó.
- Không chép toàn bộ `Authentication`/`principal` vào event: đối tượng này có thể chứa credentials, authorities, session và cấu trúc khó serialize.
- Không dùng `authentication.getName()` như ID bền vững khi tên đó chỉ là username/email có thể thay đổi.
- Phải phân biệt **authentication** (người gọi là ai) và **authorization** (có được hành động trên tài nguyên này không).

Ví dụ minh họa tại lớp web/security **có Spring Security**, không thuộc dự án chạy độc lập ở phần 9:

```java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

if (authentication == null || !authentication.isAuthenticated()
        || authentication instanceof AnonymousAuthenticationToken) {
    throw new AccessDeniedException("Authentication required");
}

// Resolve stable actor identity via trusted principal mapping.
// Verify authorization for the target resource before publishing.
// Do not put Authentication or credentials into the event.
```

Các loại trên thuộc Spring Security và cần các import/dependency tương ứng. Tên người dùng, principal type và cách kiểm tra anonymous phụ thuộc authentication mechanism; snippet trên chỉ minh họa **ranh giới xác thực**, không áp dụng nguyên xi cho mọi cấu hình bảo mật.

### 3.3. Quy trách nhiệm cho hành động tự động

Giả sử người dùng tạo một job định kỳ, đến hôm sau job tự phát `SubscriptionRenewed`. Actor trực tiếp của lần gia hạn có thể là `SYSTEM:renewal-scheduler`, trong khi người dùng đã cấu hình job là `initiatedByUserId` hoặc `onBehalfOf` theo contract. Chỉ dùng `userId` làm actor có thể che mất việc chính hệ thống thực thi.

Khi audit cần phân biệt:

```text
actor: SYSTEM:renewal-scheduler
onBehalfOf: HUMAN:user-42
causedBy: recurring-plan-7
```

Các field này chỉ nên có nếu domain có quy tắc ý nghĩa rõ ràng. Không tự suy ra người dùng đã bấm nút ở đúng thời điểm scheduler chạy.

## 4. Tenant: sở hữu dữ liệu và cô lập nhiều khách hàng

Trong kiến trúc multi-tenant, `tenantId` thường biểu diễn **ranh giới sở hữu dữ liệu** hoặc phạm vi nghiệp vụ mà event thuộc về. Đây là thông tin quan trọng cho:

- Partitioning dữ liệu và lựa chọn namespace/schema.
- Xác định consumer có quyền xử lý hay lưu trữ event hay không.
- Audit, metrics và hỗ trợ sự cố **theo tenant**.
- Idempotency, correlation và routing nếu nhiều tenant dùng chung hạ tầng.
- Bảo đảm dữ liệu của tenant A không bị gửi vào sink của tenant B.

**Không dùng `tenantId` trong event như bằng chứng rằng consumer đã được phép truy cập dữ liệu tenant đó.** Producer có thể bị lỗi, event có thể bị giả mạo ở ranh giới ngoài, hoặc một listener chung có thể đang xử lý nhầm nguồn.

### 4.1. Tenant của tài nguyên khác “tenant hiện tại của request”

Giả sử UI cho phép người dùng chuyển tenant đang chọn, nhưng thao tác hướng đến hóa đơn `INV-7`. Tenant đúng phải được **đối chiếu với hóa đơn** và quyền của actor, không chỉ sao chép `X-Tenant-Id` do trình duyệt gửi.

Luồng đúng:

```text
Authenticated principal
    + requested invoice ID
           |
           v
  Resolve invoice -> canonical tenant owner
           |
           v
  Check actor permission inside that tenant
           |
           +-- DENIED --> Không phát InvoiceApproved
           |
           +-- ALLOWED --> Thực hiện approval
                             |
                             v
                   Phát InvoiceApproved {
                     tenantId = canonical owner,
                     actor = authenticated identity,
                     ...
                   }
```

Một hệ thống dùng tenant trong token đã được xác minh vẫn cần đối chiếu target resource và role/permission cần thiết. “Đã đăng nhập vào tenant-blue” không tự chứng minh actor được phê duyệt **mọi** hóa đơn của tenant-blue.

### 4.2. Tenant ID phải có phạm vi và format rõ ràng

Có thể dùng UUID hoặc một stable opaque ID, nhưng nhất quán toàn hệ thống. Cần xác định:

- Tenant ID có duy nhất trên toàn hệ thống hay chỉ trong một region?
- Có namespace/issuer riêng cho từng tenant provider không?
- Có thể gộp/tách/di chuyển tenant giữa các cluster không?
- Một entity có được sở hữu bởi nhiều tenant không?
- Có sự kiện toàn hệ thống không cần tenant không?

Nếu có global events, cân nhắc một loại event/metadata khác, ví dụ `GlobalTaxPolicyPublished` không có tenant. **Đừng** sử dụng tenant giả để qua validation, vì consumer có thể định tuyến vào nhầm partition.

### 4.3. Đừng dựa vào ThreadLocal làm nguồn chính của tenant trong listener

Một số ứng dụng dùng `TenantContextHolder` dựa trên `ThreadLocal` cho việc chọn datasource. Khi event listener được xử lý bất đồng bộ, thread xử lý **không mặc nhiên kế thừa** tenant context của thread publisher.

Nguy hiểm hơn, thread pool tái sử dụng worker. Nếu code tự đặt tenant vào ThreadLocal rồi không dọn bằng `finally`, tác vụ tiếp theo có thể thấy tenant cũ:

```java
// Mẫu minh họa trong ứng dụng có TenantContextHolder.
String previous = TenantContextHolder.getTenantId();
try {
    TenantContextHolder.setTenantId(event.context().tenantId());
    processInTenantScope(event);
} finally {
    if (previous == null) {
        TenantContextHolder.clear();
    } else {
        TenantContextHolder.setTenantId(previous);
    }
}
```

Đoạn này **không phải code tự chạy**: `TenantContextHolder` và `processInTenantScope` do ứng dụng định nghĩa. Nếu cho phép đặt tenant context từ event, trước hết phải **kiểm tra nguồn event và quyền tenant** theo trust boundary. Khôi phục previous context chỉ là bước vệ sinh luồng, **không** thay thế authorization và không cho phép một event không đáng tin tự lựa tenant.

Ưu tiên truyền tenant tường minh trong phương thức xử lý hoặc query, chẳng hạn:

```java
invoiceRepository.findByIdAndTenantId(invoiceId, tenantId);
```

Phương thức trên là **API repository minh họa**, không mặc định tồn tại trong Spring. Truy vấn được tenant-scoped giúp giảm nhầm lẫn khi chuyển luồng. Với hệ thống có Row Level Security, vẫn cần thiết lập session/database role đúng và kiểm thử không rò dữ liệu xuyên tenant.

## 5. Context: correlation, causation, trace và thời điểm

Không phải mọi metadata đều cùng một loại “context”. Nên định nghĩa từng trường bằng câu hỏi riêng, tránh cho consumer phụ thuộc vào một object hỗn độn `Map<String, Object>`.

### 5.1. Event ID

`eventId` định danh **một occurrence** cụ thể của fact. Hai hóa đơn được phê duyệt cùng lúc phải có event ID khác nhau; cùng một event được retry/phát lại qua broker **nên giữ nguyên ID gốc** để consumer có thể dedupe, tùy delivery protocol.

`UUID.randomUUID()` là một lựa chọn cho ID, nhưng hệ thống có thể chọn ULID, UUIDv7 hoặc định danh khác. Điều quan trọng là quy ước uniqueness và cách sử dụng ID nhất quán.

Lưu ý: cùng một actor, tenant và correlation ID **không đồng nghĩa** cùng một event. Một request có thể tạo nhiều sự thật riêng.

### 5.2. Correlation ID

`correlationId` nối các bước thuộc một hành trình logic:

```text
HTTP request (correlationId=REQ-9)
      |
      +--> InvoiceApproved (eventId=E1, correlationId=REQ-9)
      |
      +--> AuditRecorded (eventId=E2, correlationId=REQ-9)
      |
      +--> NotificationRequested (eventId=E3, correlationId=REQ-9)
```

Correlation ID là một **khóa quan sát**. Không dùng nó làm auth token, session ID hoặc tenant boundary. Nếu client gửi một correlation ID, cần validate định dạng/độ dài hoặc phát ID tin cậy tại ingress; không cho chuỗi bất kỳ phá log, header hoặc metric labels.

### 5.3. Causation ID

`causationId` ghi lại **nguyên nhân trực tiếp**, chẳng hạn một command ID hoặc event trước đó:

```text
ApproveInvoiceCommand CMD-17
         |
         v
InvoiceApproved E-18 (causationId=CMD-17)
         |
         v
AuditRecorded E-19 (causationId=E-18)
```

Không phải mọi event đều cần causation ID, ví dụ một hành động nội bộ đơn giản không có message envelope. Nếu có, định nghĩa thống nhất nguồn ID (command, event, job) để không tạo một chuỗi thiếu ý nghĩa.

### 5.4. Trace ID / span ID khác correlation ID

Trong observability, `traceId` và `spanId` thường do tracing framework (ví dụ OpenTelemetry) quản lý. Chúng có định dạng và quy tắc propagation riêng. `correlationId` có thể là ID nghiệp vụ sống lâu hơn một trace, nên không nên coi hai khái niệm hoàn toàn tương đương.

- Có thể lưu `traceId` trong event metadata nếu có nhu cầu và quyền truy cập phù hợp.
- Không cố dựng span ID tùy ý nếu muốn tương thích distributed tracing.
- Không dùng tracing baggage chứa PII, tokens hoặc tenant secrets.
- Không cho raw tenant ID có cardinality quá lớn làm label metric mặc định ở mọi sự kiện.

### 5.5. Occurred time, published time và processed time

| Timestamp | Ý nghĩa | Ai kiểm soát? |
| --- | --- | --- |
| `occurredAt` | Thời điểm fact được domain xác nhận xảy ra | Producer/domain |
| `publishedAt` | Thời điểm thông điệp được gửi ra transport, nếu có | Publisher/relay |
| `receivedAt` | Consumer nhận được event | Consumer |
| `processedAt` | Consumer hoàn thành xử lý | Consumer |

Trong Spring Application Events nội bộ, một timestamp lúc tạo object không nhất thiết là timestamp lúc commit transaction; cũng không bằng thời điểm listener chạy khi async.

Dùng `Instant` UTC hoặc format chuẩn khi lưu qua hệ thống, không ghi thời gian dựa trên timezone hiển thị rồi để consumer tự đoán. Nếu miền nghiệp vụ cần “ngày kinh doanh” theo múi giờ tenant, hãy mô hình hóa riêng business date/time zone, **không** thay `occurredAt` toàn cục bằng giờ địa phương mơ hồ.

## 6. Phân biệt event metadata và dữ liệu business

Một event thường có hai nhóm:

```text
InvoiceApproved {
  business:
    invoiceId
    approvalLevel
  metadata:
    eventId
    occurredAt
    tenantId
    actor
    correlationId
    causationId?      // nếu được định nghĩa
}
```

Điều này **không bắt buộc** mọi event dùng đúng một base class hay một envelope. Có thể dùng:

1. Record event chứa metadata record, như ví dụ chạy được ở phần 9.
2. Envelope `EventEnvelope<T>` khi thật sự có nhu cầu vận chuyển hoặc hạ tầng chung.
3. Các trường tường minh trên từng event nếu số lượng event ít và dễ hiểu hơn.

Một base class tổng quát quá mức có thể khiến mọi event có `tenantId` ngay cả các event toàn hệ thống, hoặc cho phép cả đống field optional. Nên chọn abstraction dựa trên các bất biến **thực sự chung**.

### Đừng lưu runtime objects vào payload

Các field **nên tránh**:

- `HttpServletRequest`, `HttpSession`, Servlet context.
- `Authentication`, `SecurityContext`, access token, refresh token, cookie.
- `Thread`, `Executor`, `TransactionStatus`, JDBC connection.
- JPA entity đang còn lazy-loaded, Hibernate session hoặc mutable domain aggregate.
- Mọi request headers, toàn bộ MDC hoặc arbitrary map chưa lọc.
- Password, OTP, API key, secrets, raw payment card information.

Lý do không chỉ là serialize khó: dữ liệu có thể lỗi thời ở thời điểm consumer chạy, chứa thông tin vượt quyền, giữ tham chiếu đến tài nguyên sống quá lâu và tạo rủi ro rò rỉ thông tin.

Thay vào đó hãy mang **ID ổn định và snapshot tối thiểu** phù hợp với contract. Ví dụ `ActorRef(HUMAN,"user-42")`, không đưa object `UserDetails` đầy authorities và credentials.

## 7. Thiết kế Java record bất biến cho actor và metadata

Trong Java 17, record hỗ trợ payload rõ ràng và tự sinh các accessor. Một mẫu:

```java
public enum ActorKind { HUMAN, SERVICE, SYSTEM }

public record ActorRef(ActorKind kind, String id) {
    public ActorRef {
        Objects.requireNonNull(kind);
        Objects.requireNonNull(id);
        if (id.isBlank()) throw new IllegalArgumentException("blank actor id");
    }
}

public record EventMetadata(
        UUID eventId,
        Instant occurredAt,
        String tenantId,
        ActorRef actor,
        String correlationId) {
    public EventMetadata {
        Objects.requireNonNull(eventId);
        Objects.requireNonNull(occurredAt);
        Objects.requireNonNull(actor);
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(correlationId);
        if (tenantId.isBlank() || correlationId.isBlank()) {
            throw new IllegalArgumentException("blank context field");
        }
    }
}

public record InvoiceApproved(String invoiceId, EventMetadata metadata) {
    public InvoiceApproved {
        Objects.requireNonNull(invoiceId);
        Objects.requireNonNull(metadata);
        if (invoiceId.isBlank()) throw new IllegalArgumentException("blank id");
    }
}
```

Đây là đoạn **khai báo minh họa**; cần import `java.util.Objects`, `java.util.UUID`, `java.time.Instant`. Ví dụ ứng dụng đầy đủ ở phần 9 có thể chạy trực tiếp.

Các bất biến cần đặt đúng tầng:

- Kiểm tra `null`/blank, định dạng ID và kích thước chuỗi có thể ở constructor/validator của metadata.
- Kiểm tra **actor có quyền** phê duyệt hóa đơn của tenant không thuộc application/domain service, nơi có dữ liệu và chính sách quyền.
- Việc tạo `EventMetadata` không chứng minh payload đến từ nguồn tin cậy. Bất kỳ code nào được cấp constructor đều có thể tự tạo một record hợp lệ về **cấu trúc**, nhưng giả về **quyền**.
- Record là *shallowly immutable*. Nếu metadata có `Set`/`List`/`Map`, cần defensive copy (ví dụ `Set.copyOf`), và tránh lưu mutable object mà accessor trả lại.

### Không nên tái sử dụng cùng một ID cho event và correlation

Một correlation có thể chứa hàng chục event, còn mỗi event phải có ID riêng. Đừng đặt `eventId=correlationId` vì tiện test. Nếu producer nhận lại command trùng và không được tạo thêm fact, idempotency phải được xử lý ở nghiệp vụ chứ không phải bằng việc “đổi UUID” mỗi lần.

## 8. Nguồn dữ liệu cho actor/tenant phải đến từ đâu?

Một quy trình tin cậy:

1. **Ingress**: xác minh danh tính người gọi, chữ ký/token hoặc service identity qua hạ tầng bảo mật.
2. **Application service**: xác định hành động và tài nguyên đích; tìm tenant sở hữu tài nguyên từ nguồn dữ liệu có thẩm quyền.
3. **Authorization**: kiểm tra quyền của actor **trên chính tài nguyên/tenant đó**, không chỉ kiểm tra đã xác thực.
4. **Domain operation**: thay đổi trạng thái khi điều kiện nghiệp vụ được đáp ứng.
5. **Event factory**: tạo snapshot actor, tenant, occurredAt, correlation và eventId; không tự chép secrets.
6. **Publish/commit**: phát event tại ranh giới transaction phù hợp và xác định rõ điều gì là durable.
7. **Consumer**: kiểm tra trust boundary theo cách nhận event, xử lý trong tenant scope đúng và theo idempotency policy.

Có thể hình dung:

```text
Untrusted request:
  invoiceId, optional request correlation
           |
           v
Authentication -> TrustedIdentity(userId, memberships)
           |
           v
Load Invoice(id) -> canonical tenantId
           |
           v
Authorize actor for invoice + tenant
           |
           +--> Reject: no InvoiceApproved event
           |
           v
Apply approved state
           |
           v
InvoiceApproved {
  invoiceId,
  metadata(tenantId, ActorRef, correlationId, eventId, occurredAt)
}
           |
           v
@EventListener -> tenant-scoped consumer/audit
```

Điều này ngăn kiểu lỗi: actor của tenant A gửi request với `tenantId=B` và hệ thống phát event có tenant B mà không kiểm tra tài nguyên. Nếu event được truyền qua broker ngoài hệ thống tin cậy, consumer cũng phải xác thực transport/provenance theo policy trước khi dùng tenant từ payload làm căn cứ routing.

## 9. Ví dụ chạy được: actor/tenant được xác định trước khi publish event

Ví dụ này dùng **Java 17+**, **Spring Framework 6.2.12** và Maven. Nó cố ý không thêm Spring Security, HTTP hoặc database để tập trung vào hợp đồng payload và minh họa việc **authorization trước publish**:

- `TrustedIdentity` tượng trưng cho danh tính **đã được xác thực** ở một boundary phía trước (đây chỉ là mô phỏng, không phải một hệ thống authentication hoàn chỉnh).
- `InvoiceStore` chứa ánh xạ invoice → tenant có thẩm quyền trong dữ liệu của ứng dụng.
- `InvoiceService` kiểm tra actor có nằm trong tenant sở hữu hóa đơn rồi mới phê duyệt và phát `InvoiceApproved`.
- Listener nhận metadata bất biến, không cần đọc `ThreadLocal` hay `SecurityContext`.
- Thử phê duyệt cùng hóa đơn từ người thuộc tenant khác bị từ chối trước khi phát event.

### Cấu trúc

```text
event-context-demo/
├── pom.xml
└── src/main/java/demo/EventContextDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>event-context-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.EventContextDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/EventContextDemo.java`:

```java
package demo;

import java.time.Instant;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class EventContextDemo {

    public enum ActorKind { HUMAN, SERVICE, SYSTEM }

    public record ActorRef(ActorKind kind, String id) {
        public ActorRef {
            Objects.requireNonNull(kind, "kind");
            Objects.requireNonNull(id, "id");
            if (id.isBlank()) throw new IllegalArgumentException("blank actor id");
        }
    }

    public record TrustedIdentity(String userId, Set<String> tenantIds) {
        public TrustedIdentity {
            Objects.requireNonNull(userId, "userId");
            Objects.requireNonNull(tenantIds, "tenantIds");
            if (userId.isBlank()) throw new IllegalArgumentException("blank user");
            tenantIds = Set.copyOf(tenantIds);
        }
    }

    public record EventMetadata(
            UUID eventId,
            Instant occurredAt,
            String tenantId,
            ActorRef actor,
            String correlationId) {
        public EventMetadata {
            Objects.requireNonNull(eventId, "eventId");
            Objects.requireNonNull(occurredAt, "occurredAt");
            Objects.requireNonNull(tenantId, "tenantId");
            Objects.requireNonNull(actor, "actor");
            Objects.requireNonNull(correlationId, "correlationId");
            if (tenantId.isBlank() || correlationId.isBlank()) {
                throw new IllegalArgumentException("blank event metadata");
            }
        }
    }

    public record InvoiceApproved(String invoiceId, EventMetadata metadata) {
        public InvoiceApproved {
            Objects.requireNonNull(invoiceId, "invoiceId");
            Objects.requireNonNull(metadata, "metadata");
            if (invoiceId.isBlank()) {
                throw new IllegalArgumentException("blank invoice id");
            }
        }
    }

    public static final class InvoiceStore {
        private static final class Invoice {
            final String tenantId;
            boolean approved;

            Invoice(String tenantId) {
                this.tenantId = tenantId;
            }
        }

        private final Map<String, Invoice> invoices = new HashMap<>();

        public InvoiceStore() {
            invoices.put("INV-7", new Invoice("tenant-blue"));
        }

        public synchronized String approve(
                String invoiceId, TrustedIdentity identity) {
            Invoice invoice = invoices.get(invoiceId);

            // Dùng thông báo lỗi chung để không lộ tài nguyên của tenant khác.
            if (invoice == null
                    || !identity.tenantIds().contains(invoice.tenantId)) {
                throw new SecurityException("access denied");
            }
            if (invoice.approved) {
                throw new IllegalStateException("already approved");
            }

            invoice.approved = true;
            return invoice.tenantId;
        }
    }

    public static final class InvoiceService {
        private final InvoiceStore store;
        private final ApplicationEventPublisher publisher;

        public InvoiceService(
                InvoiceStore store, ApplicationEventPublisher publisher) {
            this.store = store;
            this.publisher = publisher;
        }

        public void approve(
                String invoiceId,
                TrustedIdentity identity,
                String correlationId) {

            // Tenant lấy từ invoice được truy xuất và kiểm tra quyền.
            String tenantId = store.approve(invoiceId, identity);

            EventMetadata metadata = new EventMetadata(
                    UUID.randomUUID(),
                    Instant.now(),
                    tenantId,
                    new ActorRef(ActorKind.HUMAN, identity.userId()),
                    correlationId);

            publisher.publishEvent(new InvoiceApproved(invoiceId, metadata));
        }
    }

    public static final class AuditListener {
        @EventListener
        public void onInvoiceApproved(InvoiceApproved event) {
            EventMetadata m = event.metadata();
            System.out.println(
                    "APPROVED invoice=" + event.invoiceId()
                    + " tenant=" + m.tenantId()
                    + " actor=" + m.actor().id()
                    + " kind=" + m.actor().kind()
                    + " correlation=" + m.correlationId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        InvoiceStore invoiceStore() {
            return new InvoiceStore();
        }

        @Bean
        InvoiceService invoiceService(
                InvoiceStore store, ApplicationEventPublisher publisher) {
            return new InvoiceService(store, publisher);
        }

        @Bean
        AuditListener auditListener() {
            return new AuditListener();
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            InvoiceService service = context.getBean(InvoiceService.class);

            service.approve(
                    "INV-7",
                    new TrustedIdentity("user-42", Set.of("tenant-blue")),
                    "REQ-9");

            try {
                service.approve(
                        "INV-7",
                        new TrustedIdentity("user-99", Set.of("tenant-red")),
                        "REQ-10");
            } catch (SecurityException denied) {
                System.out.println("DENIED " + denied.getMessage());
            }
        }
    }
}
```

Chạy tại thư mục có `pom.xml`:

```bash
mvn -q compile exec:java
```

Các dòng do chương trình chủ động in ra (không tính log phụ thuộc môi trường):

```text
APPROVED invoice=INV-7 tenant=tenant-blue actor=user-42 kind=HUMAN correlation=REQ-9
DENIED access denied
```

**Diễn giải chính xác:**

1. Spring tạo `AnnotationConfigApplicationContext` và đăng ký `AuditListener.onInvoiceApproved` qua `@EventListener`.
2. Người dùng giả lập `user-42` có membership ở `tenant-blue`. `InvoiceStore` xác định `INV-7` thuộc `tenant-blue`, cho phép đổi trạng thái, trả tenant chính thức về service.
3. Service chụp metadata gồm event UUID, thời điểm, actor reference và correlation; listener nhận event rồi in ID và kind. Do code không in `eventId` và `occurredAt`, stdout ổn định dù hai giá trị được tạo trong runtime.
4. Người dùng giả lập `user-99` chỉ có membership ở `tenant-red`. Store trả lỗi chung `access denied` **trước khi phát event**, vì thế không có dòng `APPROVED` thứ hai.
5. `TrustedIdentity` được khởi tạo trong `main` chỉ nhằm minh họa dữ liệu đã qua xác thực. Trong ứng dụng thực, nó phải được tạo từ một authentication boundary **đáng tin cậy**, không từ object do client tự truyền.
6. Ví dụ chỉ dùng `HashMap` trong bộ nhớ và không có transaction/durable storage. Nếu listener ném exception sau khi trạng thái đổi, ví dụ **không tự rollback**. Trong production phải thiết kế transaction + outbox hoặc chính sách publish tương ứng.

**Lưu ý kiểm tra quyền:** vì ví dụ chỉ dùng membership để đơn giản hóa, nó chưa mô hình hóa role hoặc quyền `APPROVE_INVOICE`. Hệ thống thật cần kiểm tra cả membership, role/permission trên resource, trạng thái hóa đơn và các chính sách phê duyệt (chẳng hạn không tự phê duyệt hóa đơn do mình tạo) trước khi tạo fact.

## 10. Khi có @Async hoặc TaskExecutor: context nào còn tồn tại?

Theo cơ chế `ApplicationEventPublisher`, Spring event thường được phân phối đồng bộ qua multicaster mặc định. Nhưng khi listener chạy async bằng `@Async` hoặc executor được cấu hình trên multicaster, thread xử lý có thể khác thread phát.

Với Spring Framework, **ThreadLocal và logging context không tự được truyền vào async listener**. Spring Security cũng thường giữ `SecurityContextHolder` trên ThreadLocal theo mặc định. Do vậy:

```java
@Async
@EventListener
public void onInvoiceApproved(InvoiceApproved event) {
    // KHÔNG dựa vào SecurityContextHolder của thread request cũ.
    // Dùng snapshot actor + tenant trong event sau khi xác minh provenance.
    var actorId = event.metadata().actor().id();
    var tenantId = event.metadata().tenantId();
    processApprovedInvoice(tenantId, event.invoiceId(), actorId);
}
```

Đây là **đoạn minh họa**: cần bean listener có `@EnableAsync`/executor phù hợp và `processApprovedInvoice` do ứng dụng định nghĩa. Không phải chương trình độc lập của phần 9.

### 10.1. Chụp context không đồng nghĩa chuyển toàn bộ quyền

Việc event lưu actor/tenant cho phép consumer **biết sự thật có ngữ cảnh gì**, nhưng không cho consumer tự ý thực hiện mọi thao tác thay actor đó. Nếu một hành động ở consumer cần quyền hiện thời, phải áp dụng trust và authorization phù hợp với quyền của consumer; quyền của người dùng có thể đã bị thu hồi sau thời điểm xảy ra fact.

Một consumer xử lý audit có thể cần lưu actor lịch sử **đúng như lúc event phát**. Một consumer gửi dữ liệu ra bên ngoài lại phải kiểm tra chính sách hiện tại và sự cho phép của tenant. Hai nhu cầu này khác nhau.

### 10.2. TaskDecorator và context propagation

Một số hệ thống cần truyền MDC/tracing/security context qua executor bằng `TaskDecorator` hoặc công cụ tương đương. Đây là tiện ích cho runtime observation, không phải lý do đưa đối tượng security mutable vào event.

Khi dùng propagation:

- Chỉ truyền context thật sự cần thiết.
- Tuân thủ cơ chế Spring Security (ví dụ executor wrapping/delegation) nếu truyền authentication.
- Khôi phục/clear context trong `finally` để không lộ sang task tiếp theo.
- Tránh lấy actor ở **thời điểm listener chạy** để thay actor tại **thời điểm fact xảy ra**.
- Xác định retention/sensitivity: trace baggage và MDC có thể được xuất ra log.

### 10.3. Thread-local tenant dễ gây cross-tenant contamination

Nếu luồng worker từng xử lý tenant A và không clear tenant context, event tiếp theo của tenant B có thể chạy với tenant A. Bài test quan trọng không chỉ là “listener có nhận tenantId đúng trong payload”, mà còn là “repository, datasource và logs đang thực sự ở tenant scope nào”.

Ưu tiên thông tin tenant trong event là bất biến, và thực thi trong boundary rõ ràng, có cleanup. Nếu việc chọn tenant cần async/scheduling, hãy dùng context snapshot hoặc explicit parameter, không suy ra từ ambient ThreadLocal có thể vắng mặt.

## 11. Transaction: thời điểm chụp actor/tenant và ý nghĩa của “đã xảy ra”

Nếu service có `@Transactional`:

```java
@Transactional
public void approveInvoice(...) {
    // 1. Authenticate + authorize actor for invoice tenant.
    // 2. Change invoice state in the transaction.
    // 3. Construct and publish InvoiceApproved.
}
```

Đây là mã pseudocode. Nếu gọi `publishEvent` khi transaction **chưa commit**, listener `@EventListener` đồng bộ thường được gọi ngay trong thread giao dịch. Sự kiện có thể đến consumer trong khi DB transaction sau đó vẫn có khả năng rollback.

Với các side effect chỉ hợp lệ **sau commit**, có thể dùng:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onInvoiceApproved(InvoiceApproved event) {
    // Callback sau commit thành công.
}
```

Đây là đoạn minh họa trong một Spring bean có transaction manager, cần import `TransactionalEventListener`/`TransactionPhase`. Theo mặc định, nếu không có transaction hoạt động, transactional event listener không xử lý event trừ khi bật `fallbackExecution = true`.

**Các giới hạn cần nhớ:**

- `AFTER_COMMIT` ràng buộc **thời điểm callback**, không tự lưu event bền vững.
- Process crash sau DB commit nhưng trước khi gửi đi có thể làm mất việc xử lý nếu chỉ dùng event in-memory.
- Muốn bảo đảm event có thể được gửi lại sau crash, cân nhắc transactional outbox ghi chung transaction với dữ liệu nghiệp vụ.
- Thời điểm `occurredAt` phải được domain định nghĩa chính xác: thời điểm quyết định approval hay thời điểm commit? Không tự coi timestamp lúc tạo object là commit timestamp.
- Actor/tenant phải được xác định ở nơi ra quyết định nghiệp vụ; đừng đợi đến `AFTER_COMMIT` mới đọc lại ThreadLocal của request.

### Trường hợp consumer viết DB sau commit

Một listener `AFTER_COMMIT` có thể vẫn thấy tài nguyên transaction cũ đang gắn với thread trong một khoảng ngắn theo cơ chế Spring. Nếu cần ghi DB như một transaction mới, phải thiết kế transaction riêng (ví dụ `REQUIRES_NEW` ở một service được proxy phù hợp). Không nghĩ rằng chỉ có annotation listener sau commit là đã có transaction mới tự động.

## 12. Phân biệt domain event và integration event khi vượt hệ thống

Với Spring Application Events nội bộ:

```text
InvoiceService
     |
     v
ApplicationEventPublisher
     |
     v
@EventListener trong cùng context/JVM
```

Event object có thể là record Java bình thường; Spring không yêu cầu kế thừa `ApplicationEvent`. Nếu cần chuyển ra broker:

```text
Domain event (in-process)
    |
    v
Outbox / secure publisher
    |
    v
Integration message (schema version, tenant, actor, IDs)
    |
    v
Authenticated consumer
    |
    v
Tenant-aware processing
```

Trong integration event, cần xác định:

1. **Provenance**: producer nào được quyền phát loại event này? Broker ACL/chữ ký/identity nào bảo vệ transport?
2. **Schema**: field nào bắt buộc, version và compatibility policy là gì?
3. **Tenant routing**: partition key, namespace hoặc queue nào thuộc tenant nào? Metadata tenant không tự bảo đảm broker đã cô lập.
4. **Privacy**: actor ID có được chuyển giữa các hệ thống hay tenant không? Cần pseudonym hoặc mapping nào?
5. **Replay**: actor identity tại lúc event phát có còn giải thích được sau vài năm không? Retention thế nào?
6. **Duplicate/out-of-order**: consumer có idempotency theo `eventId` và thứ tự nghiệp vụ phù hợp không?
7. **Authorization ở đích**: consumer có quyền xử lý thông tin của tenant đó không, không phải chỉ tin một JSON field.

Nếu integration event được sinh ra từ domain event, **đừng vô tình đổi nghĩa actor**: một service relay không nhất thiết trở thành actor của fact. Có thể ghi `publisherService` hoặc `emittedBy` riêng, trong khi `actor` lịch sử vẫn là người/service đã thực hiện hành động nghiệp vụ.

## 13. Bảo mật, quyền riêng tư và audit

Một record metadata tốt có thể giúp điều tra ai làm gì. Nhưng audit đủ tin cậy đòi hỏi nhiều hơn việc record có trường `actorId`.

### 13.1. Không biến event thành bằng chứng xác thực

Event payload có thể được xây dựng bởi code lỗi hoặc bị giả mạo qua transport nếu hạ tầng không bảo vệ. Event chứa `actorId=user-42` **không chứng minh** rằng user-42 thật sự được xác thực khi event được tạo.

Cần có pipeline đáng tin cậy:

- Authentication tại ingress.
- Authorization theo tenant/resource tại nơi quyết định nghiệp vụ.
- Chỉ producer được cấp quyền mới publish event nhạy cảm.
- Có audit hoặc integrity controls phù hợp (append-only storage, kiểm soát truy cập, retention).
- Consumer xác thực nguồn thông điệp trước khi tin metadata phục vụ hành động.

### 13.2. Actor ID không phải token

Một opaque user ID là dữ liệu nhận diện, không phải credential. Không nhét access token vào `actorId` hoặc `correlationId`. Không dùng một email trực tiếp làm stable actor ID nếu có thể dùng internal ID; email thay đổi và có thể là PII.

### 13.3. Phân loại và giảm thiểu dữ liệu

| Trường | Nên chứa | Tránh |
| --- | --- | --- |
| `actor.id` | Stable principal identifier tối thiểu | Raw JWT, password, email khi không cần |
| `actor.kind` | HUMAN/SERVICE/SYSTEM hoặc loại domain rõ ràng | Role list khổng lồ, authorities snapshot toàn bộ |
| `tenantId` | Opaque ID nhất quán | Tên công ty/địa chỉ và secrets thay thế ID |
| `correlationId` | ID có kiểm soát, hữu ích cho tracing | Token, raw header không validate |
| `eventId` | ID của occurrence | Secret dùng làm khóa truy cập |
| `occurredAt` | Instant/UTC theo contract | Giờ địa phương không timezone |
| `business fields` | Dữ kiện cần để hiểu fact | Toàn bộ entity chứa PII ngoài phạm vi |

Retention của event và audit có thể chịu yêu cầu pháp lý, hợp đồng và chính sách tổ chức. Không nên khẳng định mọi event phải được giữ vô hạn; cần thời hạn lưu, quyền truy cập, cơ chế redact hoặc xóa/anonymize theo quy định áp dụng.

### 13.4. Logging có thể tạo rò rỉ thứ hai

Ngay cả khi payload không có token, `log.info("event={}", event)` có thể in toàn bộ metadata và dữ liệu nghiệp vụ nếu record sinh `toString()`. Với event chứa PII, nên log theo allowlist ID trường cần thiết và tránh full object dump.

Nếu tenant/user ID được đưa vào log, cấu hình phân quyền truy cập log cũng phải phù hợp vì log là một nơi dữ liệu được sao chép và có thể được giữ lâu.

## 14. Schema evolution của metadata

Khi thêm `causationId` vào event đang dùng nhiều service, cần nghĩ đến compatibility:

- Consumer cũ không biết field mới có bỏ qua được không?
- Consumer mới có đọc được message cũ không có causation?
- Field có thể optional hay cần tạo contract version mới?
- Khi rename `userId` thành `actor.id`, cách migrate historical data thế nào?
- ActorKind `SYSTEM`/`SERVICE` có được các consumer cũ hiểu không?
- Tenant ID có thay đổi format hoặc namespace không?

**Không đổi nghĩa field âm thầm.** Ví dụ trước đây `actorId` luôn là người bấm nút; giờ lại dùng cùng field cho service relay. Khi downstream dựa vào nó để làm audit hoặc enforce policy, thay đổi này nguy hiểm dù schema chỉ là chuỗi.

Một envelope minh họa:

```json
{
  "schemaVersion": 2,
  "eventType": "InvoiceApproved",
  "eventId": "d15e2182-89e7-4f29-8033-760312e91578",
  "tenantId": "tenant-blue",
  "actor": {
    "kind": "HUMAN",
    "id": "user-42"
  },
  "correlationId": "REQ-9",
  "occurredAt": "2026-01-01T10:00:00Z",
  "data": {
    "invoiceId": "INV-7"
  }
}
```

Đây là JSON **minh họa integration event**, không phải serialized output tự động của Spring Framework. Không có `eventType`, `schemaVersion` hoặc envelope cố định nào Spring Application Events bắt buộc tạo. Khi dùng broker/API, team phải định nghĩa serializer, versioning, schema registry và chính sách kiểm tra trường.

## 15. Idempotency và cô lập tenant khi xử lý lặp

Một event có thể được giao lại qua broker hoặc được publish lại do retry. Metadata giúp nhận diện nhưng **không tự chống duplicate**.

Một thiết kế consumer durable có thể dùng khóa:

```text
PRIMARY KEY (tenant_id, event_id)
```

với một bảng `processed_events` và cập nhật nghiệp vụ **trong cùng transaction**. Nếu event ID đã bảo đảm duy nhất toàn hệ thống, chỉ `event_id` có thể đủ, nhưng việc lưu `tenant_id` vẫn giúp kiểm soát partition và audit. Chính sách dedupe phải dựa vào contract và boundary thực tế, không mặc định một UUID string làm mọi việc trở nên exactly-once.

Quan trọng:

- Kiểm tra tenant của **target resource** trước khi ghi, không chỉ dựa vào tenant của message.
- Nếu tenant scope được mã hóa trong khóa database, query phải bao gồm scope đúng hoặc có Row Level Security được kiểm thử.
- Không dùng `correlationId` làm khóa dedupe: một correlation có thể sinh nhiều event.
- Nếu event được replay, actor lịch sử được giữ nguyên, nhưng quyền chạy lại side effect có thể cần kiểm tra riêng.
- Nếu event không đáng tin, kiểm tra provenance **trước** khi dùng `tenantId` để chọn datasource/partition.

## 16. Các tình huống thiết kế đặc biệt

### 16.1. Thao tác toàn hệ thống

Ví dụ `PricingPolicyPublished` áp dụng cho mọi tenant. Nếu contract thật sự global, hãy dùng event type/global context rõ ràng thay vì tenant giả `all` hoặc `default` có thể làm consumer hiểu như một tenant cụ thể.

Một ứng dụng có thể có hai contract:

```text
TenantScopedEvent { tenantId, ... }
GlobalEvent       { scope = GLOBAL, ... }
```

Đừng cho phép `null` trong mọi tenant-scoped event rồi để consumer tự đoán đó là global hay thiếu dữ liệu do bug.

### 16.2. Một actor tác động nhiều tenant

Một admin vận hành có thể thực hiện tác vụ hàng loạt trên nhiều tenant. Nếu mỗi tenant có thay đổi nghiệp vụ riêng, nên phát các event có tenant scope rõ ràng cho từng fact. Một event duy nhất với `tenantId` tùy tiện khiến audit, idempotency và authorization khó xác định.

Có thể giữ một `correlationId` chung để nối toàn bộ batch và dùng `actor=HUMAN:admin-7` cho người thực hiện; mỗi fact vẫn có event ID và tenant ID riêng.

### 16.3. Xử lý impersonation/delegation

Nếu nhân viên hỗ trợ được phép “thao tác thay khách”, contract audit nên phân biệt:
- Người thật sự thực hiện: `actor`.
- Danh tính được đại diện: `onBehalfOf`.
- Lý do/authorization record cho việc đại diện: `delegationId` khi cần.

Không ghi actor là khách hàng chỉ vì UI đang mở hồ sơ khách; sự kiện phải phản ánh nguồn hành động thực tế.

### 16.4. Sự kiện xuất phát từ webhook

Payment webhook có thể mang một event ID của provider và merchant/tenant mapping riêng. Consumer cần xác minh chữ ký/provider identity và tra ra tenant nội bộ đáng tin. Không lấy tenant ID từ JSON webhook như nguồn có thẩm quyền nếu provider không bảo đảm semantics của field đó hoặc chưa xác thực message.

### 16.5. Service event không có người dùng hiện hành

Job định kỳ, retry hoặc queue consumer có thể không có `SecurityContextHolder`. Mặc định dùng actor loại `SYSTEM`/`SERVICE` có định danh rõ ràng thay vì sinh lỗi vì “thiếu userId”, miễn đó là semantics thực sự của thao tác. Nếu công việc tiếp nối yêu cầu của người dùng trước đó, có thể giữ `originalInitiator` riêng để tra cứu.

### 16.6. Tenant migrate hoặc rename

Tenant display name có thể đổi trong khi stable ID giữ nguyên. Nếu hệ thống sáp nhập hoặc tách tenant, historical events phản ánh owner tại thời điểm fact xảy ra. Đừng sửa ngược tenant ID trong mọi historical event mà chưa có migration/audit policy; có thể cần mapping history để truy vấn qua cấu trúc hiện tại.

## 17. Kiểm thử actor, tenant và context theo bảng quyết định

| Test case | Cần xác minh |
| --- | --- |
| Actor thuộc tenant sở hữu invoice | Event có tenant lấy từ dữ liệu nguồn, actor ID tin cậy và correlation đúng |
| Actor thuộc tenant khác | Bị từ chối; **không publish** event |
| Invoice không tồn tại | Lỗi không lộ thông tin tenant khác; không publish |
| Actor chưa xác thực | Không tạo `TrustedIdentity` hợp lệ từ request giả mạo |
| Membership có nhưng thiếu quyền phê duyệt | Bị từ chối theo policy thật, không chỉ membership |
| Actor là scheduled service | `kind=SYSTEM/SERVICE` và stable ID đúng, không giả mạo người dùng |
| Thao tác ủy quyền | Actor và `onBehalfOf` được phân biệt |
| Một request phát hai facts | Hai `eventId` khác nhau, có thể chung `correlationId` |
| Async listener dùng thread pool | Vẫn đọc được metadata actor/tenant từ payload mà không cần ThreadLocal request |
| Nhiều tenant chạy cùng pool | Không có tenant context từ task trước; cleanup luôn chạy |
| Transaction rollback | Đảm bảo contract không tuyên bố fact committed khi transaction bị rollback |
| Event tới sau khi quyền user đổi | Audit giữ actor lịch sử; hành động mới kiểm tra authorization hiện thời |
| Replayed/duplicate event | Consumer dedupe theo event ID và tenant scope đúng |
| Schema version mới | Consumer cũ/mới tương thích theo contract |
| Payload chứa dữ liệu nhạy cảm | Không log/serialize token, credential, PII ngoài policy |
| Message từ producer không tin cậy | Xác minh provenance trước khi dùng tenant chọn tài nguyên |

### Kiểm thử không chỉ nhìn log

Có thể tạo một listener recorder để thu các event trong test thay vì chỉ so khớp stdout:

```java
public final class InvoiceEventRecorder {
    private final List<InvoiceApproved> events = new ArrayList<>();

    @EventListener
    public void record(InvoiceApproved event) {
        events.add(event);
    }

    public List<InvoiceApproved> snapshot() {
        return List.copyOf(events);
    }
}
```

Đây là đoạn minh họa **test helper đồng bộ**, cần import `List`, `ArrayList`, `EventListener` và sử dụng đúng kiểu `InvoiceApproved`. Đăng ký recorder làm Spring bean trước khi publish. Nếu test với multicaster async, dùng thread-safe recorder và cơ chế chờ có thời hạn; `ArrayList` thường không an toàn khi nhiều listener/task cùng ghi.

Các assertion minh họa (trong JUnit test, không thuộc ví dụ Maven độc lập):

```java
assertEquals("tenant-blue", event.metadata().tenantId());
assertEquals("user-42", event.metadata().actor().id());
assertEquals(ActorKind.HUMAN, event.metadata().actor().kind());
assertEquals("REQ-9", event.metadata().correlationId());
assertNotNull(event.metadata().eventId());
```

Ngoài kiểm tra metadata, còn phải xác minh **không có event khi unauthorized**, và truy cập dữ liệu thực trong listener chỉ được phép với đúng tenant. Một test chỉ assert `event.tenantId()` là chính xác chưa đủ để phát hiện query sai tenant.

## 18. Lỗi thường gặp

1. **Nhận `actorId` từ request body và ghi nguyên vào event.** Đây là dữ liệu không đáng tin nếu chưa xác thực; cần lấy từ principal/identity được kiểm chứng.
2. **Sao chép tenant từ HTTP header nhưng không đối chiếu tài nguyên.** User có thể chỉ định tenant khác; lấy canonical owner từ repository và kiểm tra quyền.
3. **Nhầm actor với chủ thể bị tác động.** Lịch sử audit gán sai người thực hiện.
4. **Đọc SecurityContext trong async listener và kỳ vọng còn user cũ.** ThreadLocal không được truyền mặc định.
5. **Đặt tenant vào ThreadLocal mà quên clear.** Worker kế tiếp có thể dùng nhầm tenant.
6. **Lưu nguyên Authentication hoặc JWT vào event.** Rò credentials, khó serialize và chứa thông tin không cần thiết.
7. **Dùng email làm khóa actor vĩnh viễn.** Email đổi và là thông tin cá nhân; ưu tiên stable ID.
8. **Dùng correlation ID thay event ID.** Một request có thể tạo nhiều facts nên dedupe sai.
9. **Dùng tenant ID trong event như bằng chứng authorization.** Cần provenance và policy ở producer/consumer.
10. **Cho rằng ghi actor vào event đủ tạo audit log đáng tin.** Còn cần transaction/durability, kiểm soát producer, retention và integrity.
11. **Đặt mọi event vào cùng metadata với tenant bắt buộc kể cả global.** Thường dẫn đến tenant giả hoặc null khó hiểu.
12. **Coi `@TransactionalEventListener(AFTER_COMMIT)` là outbox.** Callback sau commit không có bảo đảm phát lại khi JVM chết.
13. **Cho rằng record bất biến hoàn toàn mọi object lồng trong.** Cần defensive copy cho mutable references.
14. **Đưa mọi MDC/header vào payload.** Có thể chứa secrets và tăng coupling, rủi ro PII.
15. **Log event bằng toString() không kiểm soát.** Log có thể sao chép dữ liệu nhạy cảm.
16. **Dùng actor lịch sử để tự động authorize hành động ở consumer về sau.** Quyền có thể thay đổi; phải kiểm tra theo nhu cầu.
17. **Không kiểm tra tenant ở database boundary.** Đúng payload nhưng query không tenant-scoped vẫn có thể rò dữ liệu.
18. **Đổi semantics `actorId` giữa người dùng và service mà không version.** Consumer audit có thể diễn giải sai.
19. **Dựa vào thời gian local không có timezone.** Khó truy dấu sự kiện trong hệ thống nhiều region.
20. **Publish event trước khi sự thật được xác nhận.** Metadata đầy đủ không sửa được việc event nói sai về domain.

## 19. Quy trình chọn metadata cho từng event

**Bước 1 — Định nghĩa fact.** Ví dụ “hóa đơn đã được phê duyệt theo chính sách tenant”.

**Bước 2 — Xác định subject/resource.** Hóa đơn thuộc tenant nào? Có nhiều chủ sở hữu hợp lệ không? Canonical owner nằm ở đâu?

**Bước 3 — Xác định actor.** Người dùng, service, system job hay delegated action? ID ổn định lấy từ trust boundary nào?

**Bước 4 — Xác định mức ngữ cảnh cần thiết.** Event ID, thời điểm, correlation, causation, trace, request ID có tác dụng thật không? Trường nào có thể bỏ?

**Bước 5 — Xác định authorization.** Kiểm tra quyền ở nơi ra quyết định nghiệp vụ trước khi phát; metadata không thay policy.

**Bước 6 — Đóng gói snapshot bất biến.** Không đưa request/principal/entity mutable vào payload; dùng kiểu và validation có ý nghĩa.

**Bước 7 — Chọn transaction/delivery.** Nếu fact phải durable hoặc gửi qua service khác, xác định commit, outbox, retry, idempotency, producer provenance.

**Bước 8 — Thiết kế consumer theo tenant scope.** Truy vấn đúng tenant, không để thread context rò, có giới hạn quyền và log.

**Bước 9 — Thử tình huống tấn công và thất bại.** Gửi tenant sai, actor giả, retry, async, tenant chuyển đổi, startup/shutdown và replay.

### Checklist review

- [ ] Actor trả lời “ai/cái gì thực hiện” và khác với subject khi cần.
- [ ] Actor ID ổn định, không phải token, password hay toàn bộ principal.
- [ ] Tenant ID lấy từ nguồn sở hữu tài nguyên đáng tin và đã kiểm tra quyền.
- [ ] Event chỉ chứa metadata cần để hiểu fact; không chép toàn bộ request/MDC.
- [ ] `eventId` định danh occurrence; `correlationId` nối workflow; `causationId` nếu có được định nghĩa rõ.
- [ ] `occurredAt` dùng dạng thời gian nhất quán, không bị nhầm với commit/publish/receive time.
- [ ] Event payload bất biến về dữ liệu cần thiết; không có mutable aggregate/session/connection.
- [ ] Async listener không phụ thuộc SecurityContext/tenant ThreadLocal của publisher.
- [ ] Consumer xác minh nguồn và quyền đúng ranh giới; tenant scope được thực thi khi truy cập dữ liệu.
- [ ] Event chứa PII được quản lý theo chính sách logging, retention và access control.
- [ ] Transaction/outbox và idempotency phù hợp yêu cầu tin cậy.
- [ ] Có test bảo đảm **không** phát fact nếu actor không được phép thao tác tenant/resource đó.

**Kết luận:** Trong domain event, `actor` mô tả danh tính thực hiện, `tenant` mô tả ranh giới sở hữu, còn correlation/causation/event IDs và timestamp mô tả quan hệ và thời điểm. Tất cả phải được tạo từ **nguồn đã xác thực sau kiểm tra quyền**, lưu như snapshot tối thiểu, và được consumer sử dụng trong một boundary có kiểm soát. Metadata tốt giúp chẩn đoán, audit và cô lập tenant, nhưng **không bao giờ thay thế authentication, authorization, transaction hay cơ chế delivery tin cậy**.

## Tài liệu tham khảo

- [Spring Framework Reference — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Security Reference — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [EventListener Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/EventListener.html)
