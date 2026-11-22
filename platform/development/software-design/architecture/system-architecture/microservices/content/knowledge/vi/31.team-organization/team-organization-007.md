# Phối hợp thay đổi hợp đồng giữa các nhóm trong Microservices

## Mục tiêu học tập

Sau bài này, người học có thể hiểu hợp đồng tích hợp (integration contract) giữa các nhóm sở hữu microservice; nhận diện thay đổi tương thích và thay đổi phá vỡ hành vi; phân chia trách nhiệm producer, consumer, platform, SRE và product owner; lập kế hoạch thay đổi theo các pha expand–migrate–contract; dùng OpenAPI, AsyncAPI, Protobuf và contract testing để phát hiện lỗi; đồng thời triển khai deprecation, quan sát adoption, xử lý version cũ, replay và rollback theo quy trình có bằng chứng.

Trong microservices, mỗi nhóm có thể triển khai độc lập nhưng không có nghĩa các nhóm phát triển trong trạng thái cô lập. API, event, dữ liệu công bố và những cam kết hành vi là các đường nối giữa ranh giới tổ chức. **Quản lý thay đổi hợp đồng tốt là điều kiện để độc lập phát hành mà vẫn bảo đảm luồng nghiệp vụ xuyên dịch vụ.**

## 1. Hợp đồng giữa các nhóm là gì?

Giả sử một nền tảng đặt hàng có kiến trúc:

~~~text
Client / Mobile
      |
      v
  API Gateway
      |
      v
Order Service (Team Order)
      |
      +---- HTTP/gRPC ----> Payment Service (Team Payment)
      |
      +---- Events ------> Inventory Service (Team Inventory)
      |
      +---- Events ------> Notification (Team Communication)
      |
      +---- CDC/Events --> Data Platform (Team Analytics)
~~~

Team Order định thay tên trường deliveryNote trong Order API thành shippingInstruction. Team Mobile chưa nâng cấp được ngay, Team Support có một dashboard cũ, Team Billing dùng schema strict, còn Team Data vẫn có job replay các event lịch sử. Thay đổi một field nhỏ trong repository Team Order có thể làm nhiều team gặp lỗi nếu hợp đồng cũ bị loại bỏ ngay.

Một hợp đồng bao gồm **cấu trúc và hành vi**, ví dụ:
- Endpoint HTTP, method, path, status code, headers và request/response body.
- gRPC service/method, Protobuf message và field numbers.
- Event type, topic/channel, partition key, schema, metadata và thời điểm phát.
- Ý nghĩa nghiệp vụ của field, đơn vị tiền tệ, timezone, thứ tự trạng thái và invariant.
- Security scopes, quyền tenant, mTLS, rate limit và độ trễ dự kiến.
- Cơ chế delivery, retry, idempotency, ordering, replay và retention.
- Chính sách version, deprecation, support window và xử lý sự cố.

Một hợp đồng chỉ gồm JSON Schema là chưa đủ nếu hai nhóm hiểu khác nhau về semantics của totalAmount hoặc ý nghĩa trạng thái CONFIRMED.

## 2. Producer, consumer và trách nhiệm sở hữu

**Producer/provider** là service công bố hợp đồng, phát event hoặc cung cấp API. **Consumer/client** là service, ứng dụng hoặc pipeline phụ thuộc hợp đồng đó. Một microservice có thể làm producer đối với nhóm này và consumer đối với nhóm khác.

| Vai trò | Trách nhiệm cốt lõi |
| --- | --- |
| Producer owner | Duy trì spec, changelog, compatibility, môi trường test và kế hoạch deprecation |
| Consumer owner | Khai báo những gì mình dùng, giữ contract tests, chuyển version theo kế hoạch |
| Domain/Product owner | Xác nhận ngữ nghĩa dữ liệu, mức rủi ro và ưu tiên nghiệp vụ |
| Platform/API enablement | Cung cấp registry, lint, test broker, observability và quy ước |
| SRE/Operations | Đánh giá rollout, SLO, lỗi runtime, rollback và runbook |
| Security/Privacy | Đánh giá auth, scope, phân loại dữ liệu và nghĩa vụ lưu giữ |
| Architecture lead (khi cần) | Giúp giải quyết thay đổi ảnh hưởng nhiều domain hoặc gây xung đột |

Producer có quyền quyết định cấu trúc do mình cung cấp trong phạm vi ownership, nhưng không thể tự coi mọi consumer đã sẵn sàng. Consumer không được yêu cầu producer giữ mã cũ vô thời hạn chỉ vì không có kế hoạch nâng cấp. Hai bên cần một **working agreement** với quyền quyết định, deadline và bằng chứng rõ.

### Đường phụ thuộc không được quản lý

Nếu Team Payment đọc trực tiếp bảng nội bộ của Order DB, schema DB bỗng biến thành hợp đồng ngầm. Khi Order thay cột, Payment lỗi dù API công khai không đổi. Cần đưa các truy vấn direct database, scheduled exports và read model chia sẻ vào inventory, sau đó chuyển dần sang API/event hoặc một data product có hợp đồng chính thức.

## 3. Những thay đổi nào có thể phá hợp đồng?

| Thay đổi | Rủi ro |
| --- | --- |
| Thêm field response tùy chọn | Thường tương thích nếu client bỏ qua field lạ; strict decoder có thể lỗi |
| Xóa hoặc đổi tên field response | Consumer cũ có thể không parse/không tìm được dữ liệu |
| Thêm request field bắt buộc | Client cũ không gửi và nhận 400/422 |
| Thay optional thành required | Dữ liệu cũ và client cũ có thể thiếu giá trị |
| Đổi string thành object, integer thành string | Thường không tương thích kiểu |
| Thêm enum value | Exhaustive switch không xử lý giá trị lạ |
| Đổi nghĩa của field giữ nguyên kiểu | Có thể gây sai nghiệp vụ dù schema check đạt |
| Đổi status/error code | Client retry, fallback hoặc thông báo sai |
| Đổi scope/permission | Consumer nhận 401/403 |
| Giảm quota hoặc đổi latency SLO | Client timeout/429 hoặc cần thay concurrency |
| Đổi event name/topic | Subscriber cũ không nhận message |
| Đổi partition key/ordering | Consumer có thể xử lý sai thứ tự |
| Đổi thời điểm phát event | Event cùng tên nhưng ý nghĩa business khác |
| Xóa version cũ | Những client chưa nâng cấp bị phá |

Tính tương thích phụ thuộc format, serializer, cấu hình validator và cách viết consumer. Không có quy tắc “thêm field luôn an toàn” đúng trong mọi môi trường.

### Breaking change về semantics

Event vẫn có field total kiểu number, nhưng trước đây total là số tiền theo **đơn vị nhỏ nhất**, bản mới chuyển thành đơn vị tiền chính. Schema có thể không đổi, trong khi Team Billing tính sai số tiền rất lớn. Vì vậy contract review phải ghi cả **đơn vị, precision, rounding, currency, timezone, source of truth, thời điểm hiệu lực, invariant và error behavior**.

## 4. Tương thích nhiều chiều thời gian

Cần xem bốn tình huống:

1. Consumer cũ đọc response/event từ producer mới.
2. Consumer mới đọc response/event từ producer cũ.
3. Consumer mới xử lý dữ liệu/event lịch sử do producer cũ ghi.
4. Producer rollback sau khi consumer mới đã triển khai.

Ví dụ với một field:
- P1 chỉ trả oldField.
- P2 trả oldField và newField.
- P3 chỉ trả newField.
- C1 chỉ đọc oldField.
- C2 ưu tiên newField nhưng fallback oldField theo quy tắc hợp lệ.
- C3 bắt buộc newField.

| Kết hợp | Khả năng tương thích |
| --- | --- |
| P1 + C1 | Có |
| P2 + C1 | Có nếu oldField giữ nguyên semantics |
| P1 + C2 | Có nếu fallback đúng |
| P2 + C2 | Có |
| P1 + C3 | Không |
| P2 + C3 | Có |
| P3 + C1 | Không |
| P3 + C2 | Có nếu C2 xử lý newField |
| P3 + C3 | Có |

Thứ tự triển khai an toàn thường là: **producer bridge P2 → consumer dual-read C2 → consumer new-only C3 → producer contract P3**. Nếu có mobile client hoặc partner khó nâng cấp, thời gian hỗ trợ P2 có thể dài hơn dự kiến.

## 5. Lập danh mục hợp đồng và consumer

Không thể xóa hợp đồng an toàn khi không biết ai đang sử dụng. Một contract catalog tối thiểu nên lưu:

~~~text
contract_id: order-api.order-detail
owner_team: Team Order
protocol: HTTPS/JSON
spec_location: repo/contract/openapi.yaml
active_versions: v1, v2
lifecycle_state: v1=DEPRECATED, v2=ACTIVE
known_consumers:
  - Web checkout
  - Mobile app
  - Customer Support dashboard
  - Billing integration
criticality: checkout path
support_channel: Team Order
last_reviewed_at: ...
migration_tracking: ...
~~~

Đối với event, cần thêm topic, schema registry subject, retention, replay, partition semantics và consumer group. Consumer group từ broker không phải danh sách đầy đủ: có thể còn batch job, event export, mobile client, partner, fraud vendor hoặc workflow cũ.

Có thể kết hợp ba nguồn để khám phá dependency:
- **Khai báo ownership** của các team trong service catalog.
- **Telemetry production** theo API version, token/client identity hoặc consumer group.
- **Phỏng vấn/đối chiếu** với nhóm product, dữ liệu, hỗ trợ và đối tác.

Khi một consumer mới tích hợp, họ cần đăng ký owner, contact, môi trường và contract tests; tránh hình thành consumer ẩn không ai biết.

## 6. Thay đổi hợp đồng phải bắt đầu bằng một đề xuất rõ ràng

Đề xuất thay đổi nên trả lời:
- Business problem nào cần giải quyết?
- Contract ID và phiên bản nào bị ảnh hưởng?
- Old/new schema, examples và semantics khác nhau ra sao?
- Thay đổi additive, breaking, security-sensitive hay operational?
- Những consumer nào được hỗ trợ và sẽ chịu tác động?
- Có thể dùng adapter/field alias/feature flag/version mới không?
- Thứ tự phát hành giữa các team thế nào?
- Ai viết producer/consumer contract tests?
- Khi nào chấm dứt version cũ và dựa vào bằng chứng nào?
- Có kịch bản rollback/forward-fix nào?
- Mức rủi ro với dữ liệu lịch sử, replay và bên thứ ba là gì?

Một RFC ngắn cho thay đổi lớn thường hiệu quả hơn họp nhiều lần nhưng không có ghi chép. Với field bổ sung thật sự optional và mọi test qua, có thể dùng quy trình rút gọn. **Governance nên tỷ lệ với rủi ro**, không phải tạo phê duyệt nặng cho mọi PR.

## 7. Chu trình đổi hợp đồng: Expand → Migrate → Contract

~~~text
Change proposal
      |
      v
Discover consumers / risk assessment
      |
      v
Expand producer contract
(old + new supported)
      |
      v
Migrate consumers independently
(dual-read / adapter / version switch)
      |
      v
Observe adoption, tests and production metrics
      |
      v
Check deprecation / sunset criteria
      |
      v
Contract old field or old endpoint
      |
      v
Changelog / catalog update / close change record
~~~

**Expand:** bổ sung cách mới mà không phá cách cũ. Có thể là field mới, endpoint v2, schema mới, dual-publish có bảo vệ idempotency hoặc server chấp nhận cả hai request format.

**Migrate:** từng nhóm consumer đổi theo nhịp release riêng. Trong giai đoạn này phải có compatibility matrix, dual-read/feature flag và telemetry.

**Contract:** loại bỏ đường cũ sau khi tất cả consumer hợp lệ đã chuyển hoặc điều kiện sunset theo chính sách được đáp ứng. Cần xét cả replay và DLQ, không chỉ live traffic.

Mỗi pha cần có gate, rollback path và owner chịu trách nhiệm. Một thay đổi breaking thực hiện trong một deploy duy nhất chỉ phù hợp nếu toàn bộ producer/consumer và lifecycle được kiểm soát thực sự; không nên mặc định điều này trong microservices.

## 8. OpenAPI cho REST/HTTP contract

OpenAPI giúp các team mô tả endpoint, request/response, schema và một phần behavior bằng đặc tả máy đọc được.

Ví dụ rút gọn:

~~~yaml
openapi: 3.0.3
info:
  title: Order API
  version: 2.1.0
paths:
  /orders/{orderId}:
    get:
      operationId: getOrder
      parameters:
        - in: path
          name: orderId
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Order details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderView'
        '404':
          description: Order not found
components:
  schemas:
    OrderView:
      type: object
      required: [id, status]
      properties:
        id:
          type: string
        status:
          type: string
          enum: [CREATED, CONFIRMED, CANCELED]
        shippingInstruction:
          type: string
          nullable: true
~~~

Đây là contract minh họa, chưa bao gồm đầy đủ auth, error responses, paging, rate limit và domain rules. OpenAPI có thể được lint, dùng tạo docs và codegen, hoặc so sánh diff trong CI.

**Diff tự động** thường phát hiện endpoint bị xóa, field đổi type, required/nullable thay đổi hoặc security scheme biến đổi. Nó thường không biết một field đã đổi nghĩa hoặc event được phát sớm hơn trước; domain owner và consumer tests phải kiểm chứng phần này.

Không nhầm version của ứng dụng deploy với API version: một API v1 có thể sống qua hàng trăm bản release và vẫn giữ hợp đồng v1.

## 9. Ví dụ đổi tên field trong REST API

Team Order muốn thay deliveryNote bằng shippingInstruction. Response cũ:

~~~json
{
  "id": "ord-42",
  "status": "CONFIRMED",
  "deliveryNote": "Leave at reception"
}
~~~

Nếu đổi trực tiếp, mobile/client cũ có thể không còn field để hiển thị. Pha expand nên trả cả hai:

~~~json
{
  "id": "ord-42",
  "status": "CONFIRMED",
  "deliveryNote": "Leave at reception",
  "shippingInstruction": "Leave at reception"
}
~~~

Hai field phải lấy từ cùng dữ liệu chuẩn và có cùng semantics trong giai đoạn bridge. Nếu có sự khác nhau về định nghĩa, không thể chỉ thêm alias cho xong.

Ví dụ DTO Java/Spring Boot:

~~~java
public record OrderView(
    String id,
    String status,
    String deliveryNote,
    String shippingInstruction
) {
    public static OrderView from(Order order) {
        String instruction = order.getShippingInstruction();
        return new OrderView(
            order.getId(),
            order.getStatus().name(),
            instruction,
            instruction
        );
    }
}
~~~

Mẫu trên chỉ mô tả mapping; các lớp, validation và authorization thực tế cần triển khai riêng.

### Điểm khó: biết client đã ngừng đọc field cũ khi nào?

Nếu backend trả oldField và newField trong cùng response, log của backend thường **không thể biết** client đã đọc thuộc tính nào. Phải có bằng chứng bổ sung:
- Consumer team xác nhận đã triển khai code mới.
- Consumer-driven contract tests không còn yêu cầu oldField.
- Client/app version telemetry nếu có.
- Thống kê API version hoặc feature capability khi hợp đồng hỗ trợ.
- Danh sách partner và client offline được xử lý theo chính sách hỗ trợ.

Không thể suy luận “không còn ai dùng field cũ” chỉ vì server không thấy chuỗi oldField trong request logs.

## 10. Event contract khác HTTP contract ở chỗ nào?

Event được lưu và chuyển bất đồng bộ; producer có thể đổi schema trong khi message cũ vẫn ở broker, dead-letter queue, replay log hoặc data warehouse.

Một event contract nên nêu:
- Event name/type, schema version và cấu trúc payload.
- Business meaning và thời điểm phát, ví dụ sau khi transaction commit.
- Event ID, entity/business key, correlation ID, causation ID.
- Partition key và bảo đảm thứ tự theo key.
- Delivery semantics, duplicate handling và idempotency.
- Retention, replay, DLQ, retry và schema history.
- PII classification và nguyên tắc tối thiểu hóa payload.

Nếu OrderConfirmed trước có nghĩa thanh toán đã hoàn tất nhưng sau này chỉ có nghĩa đơn đã tiếp nhận, đó là **breaking semantic change** dù tên và schema không đổi.

### Ví dụ thêm currency vào OrderConfirmed

Event cũ:

~~~json
{
  "eventType": "OrderConfirmed",
  "eventVersion": 1,
  "eventId": "evt-123",
  "orderId": "ord-42",
  "totalAmountMinor": 125000
}
~~~

Event mới:

~~~json
{
  "eventType": "OrderConfirmed",
  "eventVersion": 2,
  "eventId": "evt-124",
  "orderId": "ord-43",
  "totalAmountMinor": 125000,
  "currencyCode": "VND"
}
~~~

Team Billing mới phải xử lý được event v1 thiếu currency. Nếu lịch sử thật sự chỉ có một currency, có thể áp dụng mapping đã được domain owner xác nhận. Nếu không đủ thông tin để xác định, **không tự mặc định một currency**; phải backfill, đối soát nguồn chuẩn hoặc đưa message vào trạng thái cần xử lý có kiểm soát.

Consumer cũ dùng strict JSON decoder có thể lỗi dù chỉ thêm currencyCode. Schema registry và tests phải xác nhận tình huống này.

## 11. AsyncAPI, schema registry và compatibility modes

AsyncAPI giúp mô tả channel/topic, operation, message, headers và security. Avro/JSON Schema/Protobuf là những schema format được dùng để serialize hoặc validate message; registry có thể quản lý các bản schema và compatibility checks.

Những chế độ như BACKWARD, FORWARD, FULL hoặc TRANSITIVE có **ngữ nghĩa cụ thể theo registry/schema format**. Chúng không đồng nghĩa tất cả consumer runtime đều an toàn.

Cần kiểm tra:
1. Consumer mới có đọc được message được ghi bằng schema cũ không?
2. Consumer cũ có đọc được message mới không?
3. Tương thích được kiểm tra với bản trước đó hay mọi bản lịch sử?
4. Field mới có default/nullable hợp lệ không?
5. Schema liên quan enum, union, optional và type promotion như thế nào?
6. Consumer có thay đổi semantics hoặc xử lý unknown fields không?

Schema compatible là điều kiện cần trong nhiều luồng, nhưng **không đủ** để bảo đảm business-compatible. Một consumer có thể parse đúng amount nhưng diễn giải sai đơn vị hoặc time zone.

## 12. Protobuf/gRPC: đừng tái sử dụng field number

Với Protobuf, số field dùng trong wire format rất quan trọng:

~~~proto
syntax = "proto3";
package order.v1;

message OrderSummary {
  string order_id = 1;
  string status = 2;
  string delivery_note = 3;
}
~~~

Khi thay thế field, nên dùng tag mới, và nếu field cũ bị xóa trong cùng message lineage thì reserve tag/name tương ứng theo quy tắc Protobuf:

~~~proto
syntax = "proto3";
package order.v2;

message OrderSummary {
  string order_id = 1;
  string status = 2;
  reserved 3;
  reserved "delivery_note";
  string shipping_instruction = 4;
}
~~~

Ví dụ này minh họa tránh tái sử dụng tag; không tự làm v1 client tương thích với v2 package/service. Cần kiểm tra đường RPC, codegen, presence/default behavior, enum handling và các trường hợp client đang chạy.

Một field number cũ được gán cho ý nghĩa mới có thể khiến client cũ đọc đúng kiểu nhưng hiểu sai dữ liệu, rất khó phát hiện bằng lỗi parse thông thường.

## 13. Consumer-driven contract testing

Trong **consumer-driven contract testing**, consumer định nghĩa phần tương tác họ thực sự cần; provider chạy verification chứng minh phiên bản định phát hành đáp ứng kỳ vọng đó.

~~~text
Consumer team:
  define interaction tests
       |
       v
  publish contract
       |
       v
Contract broker / registry
       |
       v
Provider team:
  verify implementation against supported contracts
       |
       v
  release gate + deployment result
~~~

Ví dụ Team Notification chỉ cần orderId và status. Contract test của Notification nên kiểm tra đúng hai trường và semantics cần thiết, không snapshot mọi trường giá, thuế, địa chỉ mà họ không dùng. Một test snapshot toàn response quá chặt có thể khiến producer không thêm được field vô hại.

Những công cụ như Pact có thể giúp chia sẻ contract theo consumer version và provider verification, nhưng cần quản lý **những consumer versions đang chạy và cần hỗ trợ**, không chỉ phiên bản main branch mới nhất.

### Contract tests làm được gì?

- Phát hiện provider xóa/đổi field consumer đang dùng.
- Kiểm tra request path, body, headers, status và một số giá trị mẫu.
- Giúp producer biết thay đổi có phá bản client nào.
- Giảm nhu cầu chạy một bộ E2E lớn, chậm và flaky chỉ để kiểm tra cấu trúc tích hợp.

### Contract tests không tự làm được gì?

- Chứng minh toàn bộ business workflow nhiều bước là đúng.
- Đo hiệu năng, quota và security trong mọi tình huống.
- Bảo đảm event ordering, exactly-once side effects hoặc replay.
- Phát hiện mọi consumer không đăng ký contract.
- Thay thế kiểm thử integration với database/broker thật.
- Thay thế domain invariant hoặc review ngữ nghĩa.

Tốt nhất dùng **schema lint + compatibility diff + consumer/provider contract tests + integration tests + E2E chọn lọc**.

## 14. Kiểm soát tương thích bằng CI/CD

| Gate | Mục tiêu | Người chịu trách nhiệm |
| --- | --- | --- |
| Spec lint | OpenAPI/AsyncAPI/schema hợp lệ và đúng convention | Producer, platform |
| Breaking-change diff | Phát hiện thay đổi cấu trúc có rủi ro | Producer |
| Consumer contract verification | Các consumer version được hỗ trợ không bị phá | Producer |
| Consumer unit/component tests | Client xử lý đúng old/new response/event | Consumer |
| Registry compatibility check | Format evolution phù hợp policy | Event owner |
| Integration tests | Serialization, broker, auth, DB và retry | Các nhóm liên quan |
| Rollout matrix | Old/new versions cùng sống an toàn | Producer, consumer, SRE |
| Canary monitoring | Lỗi runtime, 4xx/5xx, DLQ, lag, business mismatch | Nhóm deploy |
| Sunset gate | Đủ điều kiện bỏ hợp đồng cũ | Producer và các consumer |

Một pipeline chỉ báo “OpenAPI valid” chưa nói lên hợp đồng tương thích. Các gate phải xét **phiên bản đang deploy ở môi trường đích**, đặc biệt khi production còn partner/mobile/region chạy release cũ.

Không cần mọi contract test phụ thuộc một staging environment dùng chung. Phần lớn kiểm tra provider/consumer có thể chạy độc lập, còn E2E dành cho luồng quan trọng thực sự cần nhiều dịch vụ cùng hoạt động.

## 15. Một lịch phát hành an toàn giữa nhiều team

Giả sử Producer P1 chỉ biết oldField, P2 hỗ trợ old+new, P3 bỏ old; Consumer C1 chỉ biết old, C2 dual-read, C3 new-only.

Lộ trình:
1. Team producer phát hành **P2** sau khi xác minh P1 consumers vẫn hoạt động.
2. Đợi P2 được rollout đầy đủ ở những region/cluster phục vụ consumer liên quan.
3. Team consumer phát hành **C2** để đọc old và new đúng semantics.
4. Theo dõi canary, error, metrics và fallback usage.
5. Chuyển dần sang **C3** khi P2 luôn sẵn sàng và dữ liệu đủ mới.
6. Theo dõi các consumer chưa chuyển, partner hoặc mobile cũ.
7. Thực hiện deprecation review và chỉ phát hành **P3** khi mọi gate được đáp ứng.

Trong rolling deployment có thể có old pod chưa dừng, job chạy lâu hoặc consumer mới nhận message do producer cũ gửi. **Không xem một nút deploy thành công là bằng chứng tất cả process đã đổi version.**

## 16. Versioning có mục đích

Các cách quản lý version thường gặp:
- HTTP URI: /api/v1/orders, /api/v2/orders.
- Header/media type: client gửi version/capability trong request.
- gRPC package/service: order.v1, order.v2.
- Event type/channel: OrderConfirmedV1, OrderConfirmedV2.
- Event envelope hoặc schema registry version.
- Versioned data product hoặc warehouse schema.

Không phải mọi thay đổi đều cần tăng major version. Thêm field thực sự optional có thể là thay đổi trong cùng version; đổi schema hoặc semantics phá client có thể cần endpoint/event mới.

**Versioning không thay thế deprecation.** Tạo /v2 không khiến mobile app /v1 ngừng sử dụng. Cần thời gian hỗ trợ, migration guide, owner và điều kiện loại bỏ /v1.

### Dual publishing event có rủi ro riêng

Nếu producer phát OrderConfirmedV1 và OrderConfirmedV2 cho cùng nghiệp vụ, một consumer subscribe cả hai có thể ghi nhận hai giao dịch. Cần định danh nghiệp vụ ổn định, idempotency key và quy tắc xử lý để hai representation của cùng event không được diễn giải thành hai sự kiện độc lập. Với thanh toán/tồn kho, bảo vệ side effect ở điểm ghi.

## 17. Dữ liệu lịch sử, replay và dead-letter queue

HTTP thường nhận request ở thời điểm hiện tại; event có thể còn trong broker hoặc DLQ và được replay nhiều ngày/tháng sau đó.

Ví dụ Team Data muốn rebuild read model từ event 180 ngày. Nếu consumer mới chỉ biết event v2, các event v1 cũ có thể lỗi hoặc tạo sai dữ liệu. Cần:
- Giữ parser/adapter cũ trong thời hạn phù hợp.
- Áp dụng schema evolution và default có nghĩa hợp lệ.
- Backfill/reconcile dữ liệu lịch sử nếu thiếu thông tin.
- Thử replay một tập dữ liệu cũ đủ đại diện.
- Tính đến retention, backup, DLQ và offset reset.
- Ngăn duplicate side effects khi replay.
- Theo dõi lag, error, dead-letter và audit.

Không sunset event format v1 chỉ vì producer live đã ngừng phát v1. Nếu consumer hoặc data pipeline vẫn có thể đọc event cũ theo chính sách đã cam kết, hỗ trợ cũ chưa thật sự hết.

### Event ordering và semantic version

Đổi partition key có thể thay đổi thứ tự xử lý theo business key. Thêm eventType mới mà không thống nhất ordering cũng có thể làm một consumer áp dụng cập nhật sai. Hợp đồng cần nêu version, producer timestamp, event ID, entity generation, partition key và idempotency; khi cần nhất quán có thứ tự, phải đánh giá khả năng xử lý out-of-order.

## 18. Feature flag và capability negotiation

Feature flag có thể giúp chuyển behavior cho một phần consumer/tenant và rollback ở cấp chức năng. Capability negotiation cho phép client khai báo format hoặc features họ hỗ trợ, server chọn response tương ứng.

Những kỹ thuật này hữu ích với client đa phiên bản, nhưng có chi phí:
- Nhiều nhánh code cùng được duy trì.
- Ma trận test phức tạp hơn.
- Phải biết flag gắn với server/client version nào.
- Telemetry phải đủ để biết nhóm nào đang dùng đường cũ.
- Đường rollback cần giữ hợp đồng cũ hoạt động.

Đừng mở cờ new-only cho consumer mới khi một số producer instance vẫn chỉ có oldField. Flag không tự sửa được lỗi parse hoặc thiếu dữ liệu.

## 19. Deprecation, migration notice và sunset

Thông báo loại bỏ contract cần đủ nội dung để consumer hành động:

~~~text
Subject: Deprecating Order API deliveryNote

Producer: Team Order
Affected contract: GET /orders/{id}, deliveryNote
Replacement: shippingInstruction (same meaning)
Bridge release: P2 returns both fields
Consumer action: read new field; fallback old if required
Target migration date: YYYY-MM-DD
Sunset review date: YYYY-MM-DD
Evidence: deployed consumer version + contract verification
Owner/contact: Team Order
Rollback: keep P2 during migration window
~~~

Ngày trong ví dụ là placeholder, không phải cam kết của dự án thật.

**Deprecation** thông báo hợp đồng không còn được ưu tiên và sẽ bị bỏ theo kế hoạch. **Sunset** là thời điểm kết thúc hỗ trợ nếu các điều kiện và nghĩa vụ đã được đáp ứng. Không nên đặt một lịch cứng mà bỏ qua việc vẫn còn client hợp lệ chưa thể cập nhật.

Duy trì bảng theo dõi:
- Consumer owner và contact.
- Mức độ ảnh hưởng, phiên bản đang dùng.
- Target version và ETA di chuyển.
- Contract tests, môi trường đã deploy và bằng chứng sử dụng.
- Blockers, ngoại lệ, kế hoạch hỗ trợ.
- Trạng thái sign-off trước sunset.

Một email gửi rồi không ai xác nhận **không phải bằng chứng** hợp đồng cũ đã an toàn để xóa.

## 20. Nhịp release khác nhau: backend, mobile, partner, data

Các nhóm có khả năng phát hành không giống nhau:
- Backend nội bộ có thể deploy nhiều lần mỗi ngày.
- Mobile qua app store, có bản client tồn tại trong thời gian dài.
- Partner B2B có lịch bảo trì theo tháng/quý.
- Data pipeline chạy batch và có lịch replay.
- Worker có message tồn lâu trong queue.
- Multi-region triển khai theo đợt, một region vẫn ở version cũ.

Phải thỏa thuận compatibility window dựa trên tình huống thật. Với public/mobile API, giữ nhiều version có thể hợp lý. Với hai internal service được kiểm soát chặt, bridge ngắn cùng contract tests có thể đủ.

Không nên áp một deadline deprecation duy nhất cho tất cả loại consumer. Mỗi nhóm có ràng buộc phát hành, độ ưu tiên và nghĩa vụ hỗ trợ khác nhau; producer cần làm việc với từng nhóm theo mức độ rủi ro.

## 21. Security và SLO cũng là hợp đồng

Đổi API từ OAuth scope order.read sang order.read.v2 có thể khiến client cũ bị 403. Đổi token audience hoặc cơ chế mTLS cũng có thể gây breaking change dù JSON vẫn giống.

Một thay đổi đáng chú ý cần xét:
- Credential rotation và thời gian overlap nếu an toàn.
- Phân quyền theo tenant/role và điều kiện truy cập mới.
- Error code và retry behavior.
- Rate limit/quota và concurrency.
- Timeout, p95 latency và độ ổn định của dependency.
- Data classification, dữ liệu cá nhân và retention.

Nếu một service tăng thời gian xử lý từ 100 ms lên 1 giây, consumer đang timeout ở 500 ms có thể lỗi hàng loạt dù contract schema không đổi. Khi thay đổi operational contract, cần phối hợp timeout budgets, retries, backpressure, rate limiting và rollback.

Không kéo dài việc bỏ qua auth để giữ “tương thích” ngoài chính sách bảo mật. Những thay đổi an ninh khẩn cấp cần lộ trình thông báo và giảm rủi ro riêng, với người có thẩm quyền ra quyết định.

## 22. RACI và cơ chế ra quyết định

Một ma trận đơn giản:

| Việc | Producer | Consumer | Platform | SRE/Security |
| --- | --- | --- | --- | --- |
| Đề xuất contract mới | R/A | C | C | C nếu rủi ro |
| Mô tả schema/semantics | R/A | C | C | I |
| Liệt kê consumer | R | R | C | I |
| Viết consumer contracts | C | R/A | C | I |
| Provider verification | R/A | C | C | I |
| Consumer migration | I | R/A mỗi team | C | I |
| Canary/rollout | R | R ở consumer | C | C |
| Quyết định sunset | A | C | C | C |
| Ứng phó incident | R | R | C | R khi liên quan |

R = thực hiện, A = chịu trách nhiệm cuối, C = tham vấn, I = được thông báo. Ma trận minh họa; tổ chức cần điều chỉnh theo quyền sở hữu và độ quan trọng của hệ thống.

**Một thay đổi phải có owner cuối cùng rõ ràng**, nhưng owner đó không được bỏ qua ý kiến consumer khi bằng chứng cho thấy còn phụ thuộc hoặc rủi ro nghiệp vụ.

## 23. Thảo luận bất đồng giữa các nhóm như thế nào?

Ví dụ Team Order muốn bỏ v1 để giảm maintenance, Team Data cần replay một năm, Team Mobile chưa thể ép toàn bộ người dùng cập nhật.

Thay vì tranh luận bằng nhận định chủ quan, hãy chuyển thành ràng buộc có thể đo:
- Những consumer nào còn sử dụng v1? Bao nhiêu request/message?
- Giá trị hỗ trợ v1 và chi phí duy trì là bao nhiêu?
- Có thể dùng adapter/projection hoặc replay pipeline riêng không?
- Điều kiện nào khiến phải bỏ v1 vì bảo mật/tuân thủ?
- Lộ trình nào có ít tổng rủi ro và chi phí nhất?
- Ai phê duyệt ngoại lệ? Khi nào xét lại?

Cần ghi quyết định trong ADR/RFC: vấn đề, lựa chọn, lý do, hậu quả, owner, deadline và điều kiện review lại. Im lặng không đồng nghĩa chấp thuận; không biến backlog của một team thành rủi ro âm thầm của team khác.

## 24. Một ADR ngắn minh họa

~~~text
Title: Rename Order API deliveryNote to shippingInstruction

Context:
  deliveryNote gây hiểu nhầm về phạm vi nghiệp vụ.
  Mobile và Support đang phụ thuộc field cũ.

Decision:
  Producer thêm shippingInstruction, giữ alias deliveryNote.
  Không đổi semantics trong pha chuyển.
  Consumer di chuyển theo lộ trình expand-migrate-contract.

Alternatives:
  Rename trực tiếp (từ chối vì breaking).
  Tạo /v2 (cân nhắc nếu semantics đổi).
  Giữ tên cũ vĩnh viễn (chi phí bảo trì và rõ nghĩa kém).

Consequences:
  Tạm duy trì hai field và tests.
  Producer phải quan sát version adoption.
  Sunset yêu cầu consumer evidence.
~~~

ADR không thay changelog hoặc contract tests. Nó giúp các nhóm có cùng cách hiểu khi bước vào nhiều vòng release và khi có người mới tiếp quản.

## 25. Monitoring khi phát hành thay đổi

Các tín hiệu cần quan sát:
- Số request theo API/contract version.
- 4xx/5xx, 401/403, timeout và rate limit theo consumer class.
- Deserialization errors, schema mismatch, DLQ và consumer lag.
- Retry storm và số side effect trùng.
- Số bản client đang chạy cũ/mới.
- Mức sử dụng fallback/compatibility adapter.
- Business reconciliation mismatch (tiền, trạng thái, số lượng).
- Provider/consumer contract verification failures.
- SLO/latency của luồng nghiệp vụ end-to-end.

Không dùng user ID/email/token làm metrics labels; các thuộc tính có cardinality cao hoặc nhạy cảm nên được xử lý ở logs/traces có phân quyền và quy tắc lưu trữ phù hợp.

### Điều kiện trước contract

Một producer chỉ nên loại bỏ đường cũ khi:
1. Mọi consumer thuộc phạm vi hỗ trợ đã chuyển hoặc được xử lý theo chính sách exception.
2. Tất cả test/verification cho version còn hỗ trợ đều đạt.
3. Đã tính khả năng replay dữ liệu cũ, DLQ và data backfill.
4. Thời hạn deprecation và thông báo đã được thực hiện.
5. Có metric chứng minh old path không còn được dùng trong phạm vi cần hỗ trợ, hoặc lý do thực tế vì sao không thể đo và cách bù kiểm chứng.
6. Có kế hoạch rollback/forward fix.
7. SRE/security và owner nghiệp vụ đã được tham vấn đúng mức rủi ro.

Không tuyên bố contract safe chỉ vì code consumer đã được merge hoặc một bảng trạng thái ticket được đánh dấu Done.

## 26. Rollback xuyên phiên bản

Giả sử producer P2 hỗ trợ oldField + newField; consumer C3 đã new-only. Producer muốn rollback P2 về P1 (old-only) do một lỗi không liên quan đến contract. Khi đó C3 lỗi.

Các chiến lược:
- Consumer C2 có dual-read để chịu được P1/P2 trong cửa sổ rollback.
- Giữ một bản producer rollback tương thích với C3.
- Dùng feature flag để tắt behavior mới nhưng vẫn giữ field mới.
- Chọn forward fix trên P2 khi rollback phá hợp đồng.
- Chỉ cho C3 phát hành sau khi P2 ổn định và đường rollback đã được chốt.

Đối với event, rollback code producer không xóa các event v2 đã phát vào broker. Consumer vẫn có thể gặp lại v2 qua replay. Hãy đánh giá rollback ở **tổ hợp producer + consumer + dữ liệu đã sinh**, không chỉ khả năng deploy lại image cũ.

## 27. Kết hợp đổi hợp đồng với migration dữ liệu

Một thay đổi contract có thể cần đổi schema database của producer. Hai quá trình phải được điều phối nhưng vẫn tách gate:

~~~text
Internal DB evolution:
  Add new column/table
       |
  Backfill / dual-write
       |
  Read new internal model
       |
  Drop old column only when safe

External contract evolution:
  Add new response/event field
       |
  Consumers migrate
       |
  Deprecate old representation
       |
  Remove old field/version when safe
~~~

Không drop cột nội bộ trước khi producer cũ ngừng tham chiếu. Không xóa contract cũ trước khi consumer chuyển. Nếu cần backfill lịch sử, không xóa dữ liệu nguồn/replay trước khi job đã hoàn thành và được đối soát.

## 28. Một timeline minh họa

~~~text
Week 0:
  Change proposal, consumer inventory, contract matrix, owners

Week 1:
  Producer bridge P2 deploy và verify old consumers

Weeks 2-3:
  Web, Support, internal service consumers migrate
  Contract tests / canary / telemetry

Weeks 3-5:
  Mobile/partner/data jobs migrate theo nhịp riêng
  Theo dõi blockers và fallback

Week 6:
  Review sunset gate, không tự động xóa nếu chưa đạt

After sunset:
  Producer contract P3, monitor và cập nhật catalog
~~~

Lịch là ví dụ, không phải SLA/deadline mặc định. Client không kiểm soát được chu kỳ cập nhật có thể cần hỗ trợ lâu hơn. Quyết định contract phụ thuộc **bằng chứng của các gate**, không chỉ ngày đã qua.

## 29. Mẫu checklist cho producer

- [ ] Hợp đồng có owner, version, spec và contact.
- [ ] Đã mô tả schema lẫn semantics, ví dụ thành công và lỗi.
- [ ] Có danh sách consumer, gồm mobile, partner, data platform và worker.
- [ ] Đã phân loại breaking risk và kiểm tra khả năng additive.
- [ ] RFC/ADR hoặc PR nêu migration plan và release order.
- [ ] Producer bridge giữ được hợp đồng cũ trong support window.
- [ ] CI có spec lint, schema diff và provider verification.
- [ ] Các consumer contracts đang chạy đều được kiểm chứng.
- [ ] Staging/canary theo dõi lỗi, auth, latency và data mismatch.
- [ ] Đã xử lý replay/DLQ, retention, event version và thứ tự.
- [ ] Có deprecation notice và migration guide.
- [ ] Biết cách xác nhận consumer adoption; không dựa hoàn toàn vào giả định.
- [ ] Có rollback/forward-fix path phù hợp với consumer đã nâng cấp.
- [ ] Chỉ loại bỏ field/version cũ sau sunset gate.
- [ ] Catalog/changelog/runbook được cập nhật.

## 30. Mẫu checklist cho consumer

- [ ] Đăng ký consumer owner/contact và hợp đồng đang dùng.
- [ ] Contract tests chỉ khóa những semantics/field cần thiết.
- [ ] Client xử lý unknown field, enum và missing data an toàn.
- [ ] Phân biệt lỗi có thể retry với lỗi không thể retry.
- [ ] Xác định khả năng đọc old/new message và replay.
- [ ] Cập nhật theo release plan; xác nhận production deployed version.
- [ ] Theo dõi 4xx/5xx, serialization errors, lag và fallback.
- [ ] Nếu business key/semantics thay đổi, đã đối soát dữ liệu.
- [ ] Các side effect bất đồng bộ có idempotency.
- [ ] Có người chịu trách nhiệm khi deadline deprecation chưa thể đạt.
- [ ] Không báo hoàn tất migration chỉ vì PR đã merge.

## 31. Tình huống kiểm thử liên nhóm

Hệ thống gồm Team Order, Billing, Notification, Data và Mobile. Team Order muốn:
- Đổi field deliveryNote thành shippingInstruction ở Order API.
- Thêm currencyCode vào OrderConfirmed event.
- Về sau yêu cầu currencyCode bắt buộc.
- Data Platform cần replay event 180 ngày.
- Mobile vẫn có nhiều version cũ.
- Billing dùng strict JSON deserialization.
- Các service deploy rolling độc lập.

Hãy thiết kế và giải thích:
1. Danh sách producer/consumer và mức độ rủi ro của từng tích hợp.
2. Old/new contract và những semantics không được đổi.
3. Ma trận compatibility P1/P2/P3, C1/C2/C3.
4. Lộ trình expand-migrate-contract cho REST và event.
5. Test consumer/provider, schema registry và integration tests cần có.
6. Cách xử lý event cũ thiếu currency không suy đoán sai.
7. Release order cho producer và từng consumer.
8. Chính sách hỗ trợ app mobile cũ và partner.
9. Monitoring để biết migration đã thực sự diễn ra.
10. Điều kiện deprecation/sunset và kế hoạch rollback.
11. Cách xử lý dữ liệu trong DLQ/replay 180 ngày.
12. Quy trình giải quyết khi Team Data chưa kịp chuyển đúng hạn.

Một đáp án đủ tốt phải chứng minh trạng thái trung gian vẫn chạy đúng, không yêu cầu các nhóm deploy cùng một giây, và không coi thông báo email là bằng chứng tất cả consumer đã sẵn sàng.

## Kết luận

Phối hợp thay đổi hợp đồng giữa các nhóm là bài toán quản lý ranh giới **kỹ thuật và trách nhiệm tổ chức** trong microservices. Producer chịu trách nhiệm công bố và tiến hóa hợp đồng; consumer làm rõ phần mình sử dụng và kiểm chứng bằng tests; những thay đổi breaking cần có kế hoạch tương thích theo nhiều phiên bản, migration, deprecation và điều kiện sunset.

Sự phối hợp hiệu quả không phải duy trì quy trình duyệt nặng nề, mà là giữ ownership rõ, spec có máy đọc, consumer catalog đúng thực tế, contract tests trong CI, rollout có observability và các quyết định có bằng chứng. Khi làm được điều đó, các team có thể phát hành độc lập mà không biến mỗi lần đổi API hoặc event thành một sự cố toàn hệ thống.
