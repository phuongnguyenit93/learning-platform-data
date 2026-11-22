# Authentication và authorization của producer

## 1. Vì sao producer phải được xác thực và phân quyền?

Trong hệ thống bất đồng bộ, producer là thành phần tạo và gửi message/event tới broker, queue, topic, exchange hoặc một API nhận sự kiện. Message có thể được xử lý sau vài mili giây hoặc vài giờ, qua nhiều worker và service. Khi message đã được broker chấp nhận, consumer thường xem nó như đầu vào để thực hiện nghiệp vụ.

Nếu producer bị giả mạo hoặc có quyền publish quá rộng, kẻ tấn công có thể tạo sự kiện giả, kích hoạt thanh toán/gửi thông báo, thay đổi trạng thái dữ liệu, làm nhiễu event stream hoặc đưa dữ liệu của tenant này sang tenant khác. Vì xử lý bất đồng bộ tách khỏi request ban đầu, việc truy ngược ai đã tạo message và vì sao message được chấp nhận cũng khó hơn nếu không lưu provenance ngay từ đầu.

Các rủi ro thường gặp:

- Một service không liên quan có thể publish vào topic chứa lệnh thanh toán hoặc thay đổi quyền.
- Client gửi trường producerId, tenantId hoặc eventType tùy ý trong payload và server tin các trường đó.
- Producer được phép ghi vào mọi topic hoặc exchange vì dùng chung một broker credential.
- API xác thực người gọi nhưng không kiểm tra người đó có quyền phát sinh sự kiện cho object cụ thể.
- Relay/outbox worker dùng credential quá rộng, khiến lỗi ở một luồng có thể phát message tới nhiều domain.
- Consumer tin rằng message đến từ broker đồng nghĩa với việc producer đã được cấp quyền nghiệp vụ.
- Message hợp lệ về schema nhưng giả mạo actor, tenant hoặc trạng thái nghiệp vụ.

Thiết kế đúng phải trả lời riêng bốn câu hỏi:

1. Ai đang gọi API hoặc mở kết nối broker?
2. Principal/workload đó có quyền publish loại message nào, tới resource nào?
3. Message đại diện cho hành động của actor hoặc tenant nào, và thông tin đó được xác minh ra sao?
4. Consumer có thể xác minh nguồn gốc và tính toàn vẹn của message đến mức nào?

Authentication xác định danh tính. Authorization quyết định danh tính đó được publish gì, ở đâu và trong ngữ cảnh nào. Kiểm tra schema và business rule xác định message có hợp lệ về dữ liệu và trạng thái hay không. Các lớp này bổ sung cho nhau.

## 2. Phân biệt caller, producer workload và actor nghiệp vụ

Một luồng publish có thể có nhiều danh tính khác nhau:

| Danh tính | Ý nghĩa | Ví dụ |
|---|---|---|
| Caller / client principal | Người hoặc ứng dụng gọi API | User, mobile app, partner client |
| Producer workload | Service hoặc process thực sự gửi message | order-service, outbox-relay |
| Business actor / subject | Người hoặc đối tượng mà hành động nghiệp vụ đại diện | User tạo đơn, merchant, hệ thống tự động |
| Tenant context | Tổ chức sở hữu dữ liệu hoặc nghiệp vụ | tenant đã được xác minh |
| Broker principal | Danh tính được broker xác thực cho kết nối publish | Service account hoặc workload identity |

Các danh tính này không nhất thiết giống nhau. Ví dụ, user Alice gọi API tạo đơn; order-service xác thực Alice, kiểm tra Alice có quyền tạo đơn trong tenant A, sau đó outbox relay dùng workload identity riêng để publish OrderCreated. Actor nghiệp vụ vẫn là Alice, producer workload là order-service/relay, tenant là A.

Không gộp tất cả thành một trường producerId. Nếu consumer cần biết ai khởi tạo hành động, lưu actor đã được xác minh. Nếu cần biết service nào phát message, lưu producer workload. Nếu cần biết broker principal nào publish, lấy từ broker audit/connection identity. Không lấy các giá trị này từ payload do caller tự khai báo.

## 3. Hai mô hình publish phổ biến

### 3.1 Client gọi API, service publish message

~~~text
Client
  |
  | HTTPS + access token
  v
API Gateway / Application
  |  authenticate caller
  |  authorize action + object + tenant
  |  validate command
  v
Database transaction + Outbox
  |
  v
Outbox Relay (workload identity)
  |  authenticate to broker
  |  authorize publish to approved topic
  v
Message Broker
  |
  v
Consumer
~~~

Đây là mô hình phù hợp khi client bên ngoài không cần truy cập broker trực tiếp. API kiểm tra quyền nghiệp vụ; relay chỉ có quyền publish các event đã được ứng dụng tạo trong outbox. Client không được chọn broker topic tùy ý hoặc tự đặt producer identity.

### 3.2 Service nội bộ publish trực tiếp vào broker

~~~text
Producer service
  |  workload identity / mTLS / broker credential
  v
Broker authentication
  |
  v
Broker ACL: principal -> topic/exchange + publish
  |
  v
Message Broker
~~~

Trong mô hình này, broker xác thực workload và kiểm tra quyền truy cập resource. Ứng dụng vẫn phải thực hiện business authorization trước khi tạo message. Broker ACL chứng minh service được phép publish vào topic, không chứng minh service được phép thực hiện mọi hành động nghiệp vụ nằm trong message.

## 4. Xác thực caller tại API nhận command

Nếu producer bắt đầu từ một API HTTP, API phải xác thực caller theo cơ chế phù hợp:

- OAuth 2.0 access token với issuer, audience, expiry và scope rõ ràng.
- OIDC identity cho user, kết hợp session/token verification.
- API key cho partner hoặc application identity, có lifecycle, scope và quota.
- mTLS hoặc workload identity cho service-to-service.
- Chữ ký webhook/request nếu giao thức tích hợp yêu cầu xác minh nguồn gửi.

Không xem API key hoặc client ID là danh tính user cuối. Một partner client có thể đại diện cho nhiều người dùng hoặc tổ chức; cần xác định actor và tenant theo hợp đồng tích hợp.

Với JWT, xác minh chữ ký bằng key tin cậy, issuer, audience, expiration, not-before và thuật toán được cho phép. Không chọn thuật toán từ token một cách mù quáng, không tin claim chưa được xác minh và không dùng token dành cho service khác.

Scope như events:publish có thể cho phép gọi chức năng publish nói chung. Scope đó chưa đủ để cấp quyền phát mọi event hoặc thao tác trên mọi object. API vẫn phải kiểm tra resource và business action.

## 5. Xác thực producer workload với broker

Broker cần biết workload nào đang mở kết nối và gửi message. Chọn cơ chế theo broker, môi trường và khả năng quản lý identity:

| Cơ chế | Cách hoạt động | Lưu ý |
|---|---|---|
| mTLS | Broker xác minh client certificate và ánh xạ certificate identity tới principal | Quản lý CA, SAN, expiry, rotation và thu hồi |
| SASL/SCRAM | Client chứng minh biết secret đã đăng ký | Secret cần lưu an toàn, rotation và giới hạn principal |
| OAuth/OIDC token | Producer gửi access token có audience dành cho broker | Token ngắn hạn, refresh an toàn và kiểm tra scope/claims |
| Cloud workload identity/IAM | Runtime cấp danh tính workload cho broker hoặc managed messaging service | Gắn role theo service account, không dùng role chung |
| Username/password | Broker xác thực credential | Chỉ dùng khi cần, không hardcode hoặc chia sẻ giữa service |

Không để broker public với anonymous publish nếu use case không yêu cầu. Nếu có endpoint public nhận message, phải có cơ chế xác thực và quota riêng; không suy ra rằng message có schema hợp lệ thì được phép gửi.

Credential của producer phải gắn với một workload cụ thể, có owner và có khả năng revoke. Tránh dùng một broker account chung cho mọi service vì audit sẽ không xác định được nguồn và khi một service bị xâm nhập, toàn bộ producer đều bị ảnh hưởng.

## 6. Authorization ở broker: quyền publish theo resource

Sau authentication, broker cần kiểm tra principal được phép thực hiện operation nào trên resource nào. Resource có thể là topic, queue, exchange, routing key, namespace, stream hoặc subscription.

Các quyền nên được tách:

- Connect/authenticate.
- Publish/write message.
- Consume/read message.
- Create/delete topic, queue, exchange hoặc subscription.
- Bind/unbind queue hoặc thay đổi routing.
- Configure retention, partition, policy hoặc schema.
- Admin/describe resource.

Producer thông thường chỉ cần publish/write vào một tập resource cụ thể. Không cấp quyền consume, delete, create hoặc admin nếu service không cần. Quyền quản trị broker nên thuộc nhóm vận hành riêng, được audit và dùng credential riêng.

Ví dụ policy khái niệm:

~~~text
principal: service:order-service
allow:
  publish:
    - topic: orders.created.v1
    - topic: orders.cancelled.v1
deny:
  consume: *
  create-topic: *
  delete-topic: *
  admin: *
~~~

Đây là minh họa độc lập với cú pháp của Kafka, RabbitMQ hay cloud broker. Cần cấu hình bằng ACL/IAM thực tế của nền tảng.

Không cấp quyền publish theo wildcard rộng như events.* nếu service chỉ cần hai topic. Nếu dùng topic prefix theo tenant, phải kiểm tra broker hỗ trợ authorization theo prefix và không để producer tự chọn tenant prefix ngoài phạm vi.

## 7. Quyền publish không đồng nghĩa quyền tạo mọi event

Một service có thể được phép publish vào topic nhưng chỉ được phát một số event type. Ví dụ order-service được publish OrderCreated và OrderCancelled, không được giả mạo PaymentCaptured hoặc UserRoleChanged.

Kiểm tra ở application:

- Allowlist event type theo producer/service.
- Map command nghiệp vụ tới event do server tạo.
- Không nhận eventType tùy ý từ client rồi forward nguyên trạng.
- Xác định schema/version được phép cho producer.
- Kiểm tra actor, object, tenant và trạng thái nghiệp vụ.
- Không cho producer tự chọn routing key hoặc partition key có thể vượt isolation boundary.

Broker ACL thường giới hạn resource, không nhất thiết hiểu event type bên trong payload. Nếu nhiều loại event dùng chung topic, consumer và schema registry cần kiểm soát event type; producer service cũng phải giới hạn loại event nó tạo.

## 8. Object-level và business authorization trước khi publish

Một access token hợp lệ và scope events:publish không chứng minh caller có quyền thực hiện hành động cụ thể. Trước khi tạo message, API cần kiểm tra:

1. Principal đã xác thực và còn hiệu lực.
2. Principal có chức năng thực hiện command, ví dụ orders:create hoặc payments:refund.
3. Object thuộc tenant/context phù hợp.
4. Principal có quan hệ hoặc delegated permission trên object đó.
5. Trạng thái nghiệp vụ cho phép chuyển đổi.
6. Các field nhạy cảm được tính hoặc lấy từ server, không tin giá trị caller tự gửi.

Ví dụ, user có thể có quyền tạo đơn trong tenant A nhưng không được hủy đơn thuộc tenant B. Việc publish OrderCancelled phải xảy ra sau khi service tải đơn theo tenant scope và xác minh user có quyền hủy ở trạng thái hiện tại.

Không tạo event trước rồi hy vọng consumer kiểm tra quyền thay cho API. Consumer cần bảo vệ nghiệp vụ riêng, nhưng authorization ở producer giúp ngăn message trái phép ngay từ nguồn.

## 9. Không tin producerId, tenantId và actor trong payload

Một message envelope có thể chứa:

~~~json
{
  "eventId": "evt-01J...",
  "eventType": "OrderCreated",
  "producerId": "order-service",
  "tenantId": "tenant-a",
  "actor": {
    "type": "user",
    "id": "user-42"
  },
  "occurredAt": "2026-11-18T10:00:00Z",
  "data": {
    "orderId": "order-123"
  }
}
~~~

Envelope là ví dụ về cấu trúc dữ liệu, không phải bằng chứng xác thực. Producer phải dựng producerId từ workload identity, tenantId từ tenant context đã xác minh, actor từ principal/business context đã xác minh và occurredAt từ clock server. Không copy các giá trị tương ứng từ raw request.

Consumer không nên tin producerId trong body chỉ vì broker principal có quyền publish. Khi cần audit mạnh, đối chiếu broker principal/connection identity với producer identity trong envelope hoặc dùng message signature có key riêng của producer.

Nếu message được relay qua nhiều tầng, phân biệt original producer, current publisher/relay và actor. Relay không nên ghi đè original producer thành chính nó mà làm mất provenance.

## 10. Tenant isolation trong producer authorization

Với multi-tenant system, tenant context phải được xác minh trước khi publish:

- Lấy tenant từ membership/delegated grant đã xác minh hoặc resource được tải trong tenant scope.
- Không tin tenantId trong body, query hoặc header nếu chưa kiểm tra quyền.
- Giới hạn producer được publish vào tenant-specific topic/partition theo policy.
- Không để tenant tự chọn topic, routing key hoặc namespace tùy ý.
- Gắn tenant context vào outbox row và message envelope từ nguồn server-side.
- Kiểm tra tenant context ở consumer trước khi đọc/ghi dữ liệu.
- Đặt quota và rate limit theo tenant để tránh noisy neighbor.

Nếu dùng topic riêng theo tenant, cần kiểm soát việc tạo topic và ánh xạ tenant-to-topic ở server. Nếu dùng topic chung, consumer phải áp dụng tenant filter và storage isolation; không dùng tenantId trong message làm điều kiện duy nhất để truy cập dữ liệu.

Tenant ID không phải secret. Bảo vệ đến từ việc xác minh membership và enforce isolation, không phải che giấu chuỗi tenant.

## 11. Delegation và publish thay mặt principal khác

Một số hệ thống cho phép service publish thay mặt user, partner hoặc service khác. Đây là delegated publishing và cần thể hiện rõ:

- Subject: danh tính mà hành động đại diện.
- Actor: principal thực hiện hoặc khởi tạo hành động.
- Producer: workload trực tiếp gửi message.
- Delegation grant: ai đã cấp quyền, phạm vi nào, thời hạn bao lâu.
- Audience: service/broker/consumer được phép nhận assertion.

Không cho client gửi actorId hoặc subjectId tùy ý rồi đưa vào event. Service phải kiểm tra delegated grant, tenant membership và phạm vi action. Nếu dùng token exchange/on-behalf-of, token mới phải có audience, scope và lifetime phù hợp; không chuyển access token của user sang mọi service.

Consumer cần phân biệt service tự động thực hiện tác vụ với service thay mặt user. Audit trail nên giữ cả actor và producer để điều tra.

## 12. Schema validation và kiểm soát message trước publish

Authorization không thay thế validation. Trước khi publish:

- Kiểm tra event type nằm trong allowlist.
- Kiểm tra schema/version tương thích với topic.
- Giới hạn message size, nesting depth, số phần tử và độ dài field.
- Validate kiểu dữ liệu, enum, timestamp và identifier.
- Từ chối field server-controlled mà caller cố ghi đè.
- Không đưa credential, access token, password hoặc dữ liệu nhạy cảm không cần thiết vào event.
- Dùng allowlist field hoặc mapping DTO để tránh mass assignment.
- Kiểm tra reference tới object tồn tại và thuộc tenant hợp lệ.

Schema registry có thể kiểm soát compatibility và schema ID, nhưng schema hợp lệ không chứng minh producer có quyền phát event. Một payload PaymentCaptured đúng schema vẫn trái phép nếu producer không được phát event đó.

Nếu broker hoặc registry hỗ trợ subject-level permissions, chỉ cấp producer quyền đăng ký/ghi schema trong namespace cần thiết. Không cho mọi producer sửa schema dùng chung hoặc đổi compatibility policy.

## 13. Message integrity và provenance end-to-end

TLS/mTLS bảo vệ kênh giữa producer và broker. Broker authentication/ACL kiểm soát ai có thể publish. Tuy nhiên, nếu message đi qua relay, mirror, export/import hoặc nhiều broker, consumer có thể cần bằng chứng nguồn gốc ở cấp message.

Khi threat model yêu cầu, có thể ký envelope:

- Canonical serialization được định nghĩa rõ.
- Signature bao phủ event ID, event type, producer identity, tenant, timestamp và payload hash.
- Key ID cho phép chọn public key đúng.
- Consumer xác minh chữ ký và trạng thái key.
- Key rotation có giai đoạn overlap và thu hồi.
- Signature version được ghi rõ để hỗ trợ migration.

Không tự thiết kế thuật toán chữ ký hoặc canonicalization. Dùng chuẩn/library đã được kiểm chứng và tránh ký một representation nhưng consumer lại diễn giải representation khác.

Message signature không thay thế broker ACL. Một producer bị cấp quyền sai vẫn có thể ký message giả bằng key hợp lệ của chính nó. Chữ ký chủ yếu chứng minh message không bị sửa và được tạo bởi holder của key tương ứng.

## 14. Replay, duplicate và idempotency

Một message hợp lệ có thể bị gửi lại do retry, redelivery, replay hoặc credential bị lạm dụng. Authentication không tự ngăn replay.

Producer nên:

- Gán event ID duy nhất và ổn định cho một event logic.
- Dùng idempotency key cho command/API có thể được client retry.
- Không tạo event mới mỗi lần retry cùng một command nếu nghiệp vụ yêu cầu một kết quả duy nhất.
- Ghi timestamp/sequence/version phù hợp với domain.
- Dùng transactional outbox để tránh database commit thành công nhưng publish bị mất, hoặc publish trước khi transaction rollback.

Consumer cần idempotent handling hoặc deduplication theo event ID/aggregate version. Timestamp đơn lẻ không đủ chống replay vì message có thể được gửi lại trong thời hạn hợp lệ hoặc clock giữa các node lệch nhau.

Nếu chữ ký có timestamp/nonce, xác minh replay window và lưu nonce/idempotency state theo chính sách. Không nhầm broker exactly-once semantics với authorization hoặc bảo đảm một business side effect chỉ xảy ra một lần trong mọi hệ thống ngoài broker.

## 15. Transactional outbox và identity của relay

Với API cập nhật database rồi publish event, dual write có thể gây inconsistency:

- Database commit nhưng broker publish thất bại.
- Broker publish thành công nhưng database transaction rollback.

Transactional outbox ghi business change và event record trong cùng database transaction. Relay đọc outbox và publish tới broker.

Phân quyền nên tách:

| Thành phần | Quyền cần có |
|---|---|
| API/application | Xác thực caller, authorize command, ghi business data và outbox |
| Outbox relay | Đọc/claim outbox cần thiết, publish tới tập topic đã duyệt |
| Broker | Xác thực relay và enforce write ACL |
| Consumer | Chỉ consume topic/subscription được cấp |
| Schema registry | Producer chỉ đọc hoặc đăng ký schema trong namespace được phép |

Relay không cần quyền cập nhật business table tùy ý hoặc quyền admin broker. Nếu relay dùng chung cho nhiều domain, cân nhắc tách identity hoặc policy theo topic/domain để giảm blast radius.

Outbox row phải chứa tenant, event type và producer context được tạo trong transaction từ dữ liệu đã xác minh. Không cho caller ghi trực tiếp outbox table hoặc chỉ định topic tùy ý.

## 16. Phân quyền producer trên các loại broker

Tên ACL và semantics khác nhau theo nền tảng. Hãy ánh xạ quyền theo resource và operation thực tế:

| Broker model | Resource/operation cần xem xét |
|---|---|
| Kafka-like log broker | Principal, cluster, topic, WRITE/READ/CREATE/DESCRIBE, transactional ID, consumer group |
| RabbitMQ-like broker | User, vhost, exchange write, queue read, configure, routing/binding permissions |
| Cloud pub/sub | Project/namespace, topic publish, subscription consume, service account/IAM role |
| AMQP/message service | Namespace, entity/topic/queue, send/listen/manage |

Không sao chép một policy giữa broker khác nhau chỉ vì chúng đều gọi resource là topic. Ví dụ quyền publish vào exchange có thể khác quyền gửi vào queue; routing key và binding có thể ảnh hưởng đường message.

Đặt quyền cụ thể:

- Producer chỉ publish vào topic/exchange đã định.
- Không cấp consume nếu producer không cần đọc.
- Không cấp create/delete/configure cho runtime producer.
- Giới hạn transactional ID hoặc producer identity nếu broker hỗ trợ.
- Giới hạn consumer group ở role consumer, không gộp vào producer.
- Tách quyền schema registry khỏi quyền publish nếu nền tảng cho phép.

## 17. Ví dụ Java: kiểm tra quyền trước khi tạo event

Ví dụ pseudo-code:

~~~java
public OrderResponse createOrder(
    Principal principal,
    TenantId requestedTenant,
    CreateOrderRequest request
) {
    TenantContext tenant = tenantAccess.requireMembership(
        principal,
        requestedTenant
    );

    policy.require(principal, "orders:create", tenant);

    Customer customer = customerRepository
        .findByIdAndTenantId(request.customerId(), tenant.id())
        .orElseThrow(NotFoundException::new);

    orderPolicy.requireCanCreateFor(principal, customer);
    orderPolicy.validateItems(request.items(), tenant);

    return transactionTemplate.execute(status -> {
        Order order = orderRepository.save(
            Order.create(tenant.id(), customer.id(), request.items())
        );

        OutboxEvent event = OutboxEvent.create(
            eventIdGenerator.next(),
            "OrderCreated",
            tenant.id(),
            principal.subjectId(),
            order.id(),
            "order-service"
        );

        outboxRepository.save(event);
        return mapper.toResponse(order);
    });
}
~~~

Ví dụ minh họa luồng, các API repository/policy phụ thuộc framework. Điểm quan trọng:

- requestedTenant chỉ là tenant user chọn; membership được xác minh.
- Customer được tải trong tenant scope.
- Quyền nghiệp vụ được kiểm tra trước khi tạo event.
- Event type, producer và actor do server gán.
- Outbox được ghi cùng transaction với business change.
- Relay dùng identity riêng để publish.

Không tạo message từ raw request DTO rồi gửi nguyên payload sang broker.

## 18. Ví dụ policy phân quyền producer

Một policy registry có thể mô tả quyền ở nhiều lớp:

~~~yaml
producer:
  workload: order-service
  brokerPrincipal: svc-order-publisher
  allowedResources:
    - topic: orders.created.v1
      operations: [publish]
    - topic: orders.cancelled.v1
      operations: [publish]
  allowedEventTypes:
    - OrderCreated
    - OrderCancelled
  allowedTenantScope: verified-request-context
  maxMessageBytes: 262144
  credentialAudience: messaging-broker
~~~

Đây là cấu trúc policy minh họa, không phải schema chuẩn của broker. Cần triển khai bằng ACL/IAM và application policy phù hợp.

Policy phải được review như code: có owner, version, approval, test deny-by-default và audit thay đổi. Tránh quyền wildcard cho toàn namespace chỉ để một service mới hoạt động nhanh.

## 19. Xử lý lỗi authentication và authorization

Phân biệt lỗi ở API và broker:

| Tình huống | Xử lý |
|---|---|
| Caller không có credential hoặc token sai | API trả 401 theo contract |
| Caller hợp lệ nhưng không có quyền command/object | API trả 403 hoặc 404 theo chính sách che giấu resource |
| Tenant membership không hợp lệ | Từ chối trước khi ghi business change/outbox |
| Producer workload không xác thực được broker | Relay ghi lỗi vận hành, retry có giới hạn và cảnh báo |
| Broker xác thực thành công nhưng ACL từ chối topic | Không retry vô hạn; báo cấu hình/quyền sai |
| Schema/event type không hợp lệ | Từ chối trước publish hoặc đưa vào quarantine theo policy |
| Broker tạm unavailable | Retry/backoff qua outbox; không báo publish thành công khi chưa được broker xác nhận |

Không trả thông tin credential, ACL chi tiết, topic nội bộ hoặc broker endpoint trong lỗi gửi cho caller. API có thể trả operation ID nếu command đã được chấp nhận bền vững, nhưng phải phân biệt rõ command đã commit với event đã được broker publish.

## 20. Audit và quan sát producer

Audit cần trả lời được ai đã khởi tạo command, service nào publish, message nào được gửi, tenant nào liên quan và policy nào đã áp dụng.

Các trường nên có:

- Request/correlation ID.
- Principal subject/client ID đã xác minh.
- Producer workload identity và broker principal.
- Tenant context đã xác minh.
- Event ID, event type, schema version và topic/resource.
- Object/aggregate ID ở dạng phù hợp.
- Authorization decision và policy version.
- Publish attempt, broker acknowledgement, retry count và kết quả cuối.
- Actor/delegation context nếu message được phát thay mặt user/service khác.

Không log access token, API key, password, private key hoặc toàn bộ payload nhạy cảm. Nếu cần forensic payload, dùng storage/audit riêng với encryption, access control và retention rõ ràng.

Theo dõi:

- Principal lạ hoặc producer mới kết nối broker.
- Producer publish vào topic ngoài allowlist.
- ACL deny tăng hoặc thay đổi quyền bất thường.
- Event type/tenant không khớp producer policy.
- Publish rate/byte vượt quota.
- Message signature/schema validation failure.
- Outbox backlog, retry và dead-letter tăng đột biến.
- Một producer phát nhiều event cho object/tenant không thuộc phạm vi.

## 21. Kiểm thử authentication và authorization của producer

Kiểm thử phải bao gồm cả API boundary, broker ACL và consumer behavior:

| Test | Tình huống | Kết quả mong đợi |
|---|---|---|
| Missing credential | Gọi API không token hoặc mở broker connection anonymous | Bị từ chối |
| Invalid token | Sai chữ ký, issuer, audience hoặc expiry | Bị từ chối |
| Wrong workload identity | Service A dùng credential của service B | Không xác thực được hoặc bị policy từ chối |
| Topic boundary | Producer publish vào topic ngoài allowlist | Broker từ chối |
| Wildcard privilege | Producer thử create/delete/admin | Bị từ chối |
| Event type spoofing | Producer/API client tự đặt eventType trái policy | API không tạo event hoặc consumer reject |
| Producer ID spoofing | Payload khai báo producer khác | Producer identity lấy từ workload, không từ payload |
| Tenant spoofing | Payload/header chọn tenant không có membership | Không ghi outbox/publish |
| Object authorization | Caller có scope nhưng không có quyền object | Bị từ chối trước side effect |
| State transition | Publish event cho object sai trạng thái | Business policy từ chối |
| Schema mismatch | Field/size/version sai | Bị từ chối hoặc quarantine |
| Delegation | Actor/subject ngoài grant hoặc grant hết hạn | Bị từ chối |
| Credential rotation | Xoay key/certificate/token | Producer chuyển đổi không gián đoạn ngoài kế hoạch |
| Revocation | Revoke producer principal | Kết nối/publish mới bị chặn trong thời gian kỳ vọng |
| Relay identity | Relay thử publish topic domain khác | ACL từ chối |
| Replay/duplicate | Retry cùng command/event ID | Không tạo business side effect trùng |
| Outbox failure | DB commit/broker publish lỗi ở các thời điểm khác nhau | Không mất hoặc nhân đôi event logic |
| Direct broker access | Client bên ngoài thử kết nối broker | Network/auth policy chặn |

### 21.1 Kiểm thử negative permission

Không chỉ kiểm tra producer hợp lệ publish thành công. Với mỗi quyền được cấp, thử các quyền lân cận không được cấp: topic khác, consume, create, delete, configure, admin và tenant khác. Đây là cách phát hiện ACL wildcard hoặc role thừa.

### 21.2 Kiểm thử rotation và outage

Mô phỏng certificate/token hết hạn, secret bị revoke, broker unavailable và schema registry unavailable. Xác nhận producer refresh credential an toàn, không log secret, retry có backoff, không đánh dấu publish thành công trước acknowledgement và có thể phục hồi từ outbox.

## 22. Các lỗi thiết kế thường gặp

1. **Chỉ xác thực API caller:** quên xác thực workload thực sự kết nối broker.
2. **Chỉ dựa vào broker ACL:** producer có thể publish event trái business rule dù được ghi vào topic.
3. **Một credential dùng chung:** không xác định được service nguồn và blast radius quá lớn.
4. **Wildcard publish:** service có thể giả mạo event của domain khác.
5. **Tin producerId/tenantId trong payload:** cho phép spoofing.
6. **Scope publish quá rộng:** scope chung bị dùng thay object-level authorization.
7. **Cho client chọn topic/routing key:** client điều khiển đường message.
8. **Không tách producer và consumer role:** một credential vừa ghi vừa đọc dữ liệu không cần thiết.
9. **Relay có quyền admin:** compromise relay ảnh hưởng toàn broker.
10. **Không kiểm tra tenant/object/state trước outbox:** event trái phép đã được tạo.
11. **Schema hợp lệ được xem là message đáng tin:** bỏ qua authentication/provenance.
12. **Exactly-once được xem là chống replay/business duplicate:** side effect ngoài broker vẫn có thể lặp.
13. **Credential không có rotation/revoke:** secret bị lộ nhưng không thể vô hiệu hóa nhanh.
14. **Không audit broker principal:** khó điều tra ai publish message.

## 23. Quy trình thiết kế producer security

Với mỗi producer:

1. Xác định caller, workload producer, actor nghiệp vụ, tenant và broker principal.
2. Chọn authentication phù hợp cho API caller và broker connection.
3. Tạo identity riêng cho từng service/relay; tránh shared credential.
4. Cấp broker ACL theo đúng topic/resource và operation cần thiết.
5. Cấp application permission theo event type, command, object, tenant và state transition.
6. Xác minh delegated actor/subject nếu publish thay mặt principal khác.
7. Dựng event envelope từ server-side context; không tin identity field trong payload.
8. Validate schema, version, event type, size, data classification và routing.
9. Dùng outbox khi cần atomicity giữa business transaction và publish.
10. Thiết kế idempotency, event ID, replay handling và retry budget.
11. Quản lý credential ngắn hạn, rotation, revocation và secret storage.
12. Bảo vệ provenance/integrity end-to-end nếu threat model yêu cầu.
13. Audit producer identity, broker principal, tenant, event và policy decision.
14. Kiểm thử quyền được cấp lẫn quyền bị từ chối, gồm outage/rotation.
15. Review ACL và producer inventory định kỳ khi service hoặc topic thay đổi.

## 24. Checklist rà soát

- [ ] Đã phân biệt caller, producer workload, business actor, tenant và broker principal.
- [ ] API caller được xác thực bằng token/session/API key/mTLS phù hợp.
- [ ] Producer workload có identity riêng; không dùng credential chung cho nhiều service.
- [ ] Broker authentication được bật; anonymous publish bị tắt trừ khi có thiết kế riêng.
- [ ] Broker ACL chỉ cấp publish vào resource/topic/exchange cần thiết.
- [ ] Producer không có quyền consume, create, delete hoặc admin nếu không cần.
- [ ] Application kiểm tra command, event type, object, tenant và trạng thái nghiệp vụ.
- [ ] Producer ID, actor, tenant và timestamp trong envelope được dựng từ context server-side.
- [ ] Client không tự chọn topic, routing key hoặc partition vượt policy.
- [ ] Schema/version/size và data minimization được kiểm tra trước publish.
- [ ] Delegated publishing có actor, subject, grant, audience và expiry rõ ràng.
- [ ] Relay/outbox dùng identity và ACL riêng, không có quyền admin.
- [ ] Event ID/idempotency và retry xử lý duplicate/replay đúng nghiệp vụ.
- [ ] Credential có nơi lưu an toàn, rotation và revocation.
- [ ] Message signature được dùng khi cần provenance/integrity và theo chuẩn đã kiểm chứng.
- [ ] Audit liên kết request, principal, workload, broker principal, tenant và event ID.
- [ ] Có negative tests cho topic khác, tenant khác, event type giả và quyền admin.
- [ ] Có test rotation, revoke, broker outage, outbox recovery và direct broker access.

Producer security cần được thực thi ở cả API/application và broker. API xác minh caller cùng quyền nghiệp vụ trên object/tenant; broker xác minh workload cùng quyền publish trên topic/resource; envelope giữ provenance được dựng từ nguồn tin cậy; relay có identity và quyền tối thiểu. Khi các lớp này nhất quán, message bất đồng bộ có thể được truy nguyên và chỉ được tạo bởi producer được phép trong đúng ngữ cảnh nghiệp vụ.
