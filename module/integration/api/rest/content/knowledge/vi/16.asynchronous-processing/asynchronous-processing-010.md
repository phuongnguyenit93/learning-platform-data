# Thông báo hoàn tất bằng webhook hoặc SSE theo hợp đồng riêng

## 1. Bài toán: công việc đã được nhận, nhưng khi nào hoàn tất?

Một REST API nhận yêu cầu tạo báo cáo lớn:

~~~http
POST /api/v1/reports HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
Content-Type: application/json
Idempotency-Key: report-intent-729

{"reportType":"SALES","from":"2026-11-01","to":"2026-11-17"}
~~~

Việc kết xuất cần vài phút. Nếu giữ HTTP request mở đến lúc xong, client dễ gặp timeout, proxy giữ kết nối lâu và hệ thống khó điều phối retry. Thiết kế phù hợp là **nhận yêu cầu, tạo tài nguyên tác vụ và trả 202 Accepted**, sau đó xử lý nền.

~~~http
HTTP/1.1 202 Accepted
Location: /api/v1/operations/op-729
Content-Type: application/json
Cache-Control: no-store

{
  "operationId": "op-729",
  "status": "PENDING",
  "statusUrl": "/api/v1/operations/op-729"
}
~~~

Nhưng một câu hỏi mới xuất hiện: **client biết lúc nào tác vụ hoàn tất mà không phải hỏi liên tục?** Hai cơ chế phổ biến là:

- **Webhook:** server chủ động gửi một HTTP POST tới endpoint của hệ thống nhận khi có sự kiện hoàn tất; phù hợp **server-to-server**.
- **Server-Sent Events (SSE):** client giữ một kết nối HTTP nhận các thông điệp **text/event-stream** từ server; phù hợp giao diện web đang mở.

Bài học **“Thông báo hoàn tất bằng webhook hoặc SSE theo hợp đồng riêng”** thuộc chương **Xử lý bất đồng bộ** của module **INTEGRATION_API_REST**. Bài tập trung vào thiết kế hợp đồng REST có trạng thái rõ ràng, thông báo không làm mất tính đúng đắn, xác thực/phân quyền, retry và kiểm thử với Java/Spring.

Sau bài, bạn sẽ biết thiết kế **operation resource**, xác định ranh giới **202 → trạng thái kết thúc**, chọn webhook/SSE, mô tả event envelope và bảo đảm nhận sự kiện an toàn, thực hiện retry/deduplication, triển khai Spring MVC và kiểm thử các tình huống mất kết nối hoặc giao sự kiện lặp.

## 2. Operation resource là nguồn sự thật, thông báo chỉ là tín hiệu

Dù dùng webhook hay SSE, nên có một **tài nguyên trạng thái** đọc được:

~~~http
GET /api/v1/operations/op-729 HTTP/1.1
Accept: application/json
Authorization: Bearer <access-token>
~~~

Khi đang chạy:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "id": "op-729",
  "status": "RUNNING",
  "createdAt": "2026-11-18T09:00:00Z",
  "updatedAt": "2026-11-18T09:01:00Z"
}
~~~

Khi hoàn tất thành công:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "id": "op-729",
  "status": "SUCCEEDED",
  "completedAt": "2026-11-18T09:03:20Z",
  "result": {"href":"/api/v1/reports/r-482"}
}
~~~

Nếu thất bại, dùng **status=FAILED** cùng mã lỗi nghiệp vụ an toàn; khi bị hủy theo chính sách có thể dùng **CANCELLED**. Một tập trạng thái gọn:

~~~text
PENDING -> RUNNING -> SUCCEEDED
                   -> FAILED
PENDING/RUNNING    -> CANCELLED (nếu có hỗ trợ hủy)
~~~

**202 không hứa rằng công việc cuối cùng sẽ thành công**. Nó xác nhận request đã được chấp nhận để xử lý; cần cách truy vấn kết quả cuối, điều kiện lỗi, hạn lưu operation và phương án retry. Khi GET một operation đang thất bại về nghiệp vụ, server vẫn có thể trả **200 OK** vì đã đọc tài nguyên trạng thái thành công; trạng thái **FAILED** nằm trong JSON chứ không nhất thiết biến GET thành HTTP 500.

**Bất biến quan trọng:** webhook/SSE không phải nguồn dữ liệu có thẩm quyền duy nhất. Client có thể mất thông báo; sau khi nhận thông báo, client vẫn có thể **GET operation** để đồng bộ trạng thái hoặc lấy liên kết kết quả đúng phiên bản. Nếu kênh thông báo hỏng, operation resource vẫn phải truy vấn được trong thời gian đã công bố.

## 3. Hợp đồng sự kiện hoàn tất chung cho cả hai kênh

Không nên để webhook có một ngữ nghĩa sự kiện còn SSE có ngữ nghĩa khác. Cả hai có thể sử dụng một **event envelope** nhất quán:

~~~json
{
  "eventId": "evt-9472",
  "type": "operation.finished",
  "schemaVersion": 1,
  "operationId": "op-729",
  "sequence": 4,
  "status": "SUCCEEDED",
  "occurredAt": "2026-11-18T09:03:20Z",
  "operationUrl": "/api/v1/operations/op-729",
  "result": {
    "href": "/api/v1/reports/r-482"
  }
}
~~~

| Trường | Quy tắc đề xuất |
| --- | --- |
| **eventId** | ID ổn định cho một **sự kiện logic**, dùng để chống xử lý lặp. |
| **type** | Tên loại sự kiện ổn định; **operation.finished** áp dụng cho trạng thái kết thúc. |
| **schemaVersion** | Phiên bản hợp đồng payload, hỗ trợ thay đổi tương thích. |
| **operationId** | Liên kết với tác vụ được trả từ 202. |
| **sequence** | Thứ tự tăng theo **một operation**, giúp phát hiện sự kiện cũ và lỗ hổng. |
| **status** | Một trong **SUCCEEDED**, **FAILED**, **CANCELLED** theo trạng thái cuối. |
| **occurredAt** | Thời điểm sự kiện phát sinh do server ghi nhận, biểu diễn UTC/offset rõ. |
| **operationUrl** | Nơi truy vấn nguồn sự thật; phải kiểm tra quyền khi gọi. |
| **result** | Chỉ có khi kết quả phù hợp và được phép công bố. |

Với FAILED, có thể trả **errorCode** ổn định thay vì stack trace hay thông tin từ hệ thống nội bộ. Không đưa token tải file, thông tin khách hàng hoặc bí mật vào event chỉ để tiết kiệm một lần GET.

**Event ID khác delivery attempt ID.** Cùng một sự kiện có thể được gửi tới webhook ba lần; cả ba lần **giữ nguyên eventId**, dù có thời điểm gửi và chữ ký khác nhau. Với SSE, cùng event được replay sau reconnect cũng giữ **id** ổn định để client phát hiện trùng.

Nếu operation có nhiều event tiến trình, quy định riêng **operation.progress** và số thứ tự; bài này tập trung vào **operation.finished** để tránh hứa một luồng progress thời gian thực khi không có nhu cầu.

## 4. Chọn webhook, SSE hay polling?

| | Webhook | SSE | GET polling |
| --- | --- | --- | --- |
| Ai mở kết nối? | API gửi POST tới receiver | Client mở GET giữ kết nối | Client gọi GET định kỳ |
| Phù hợp | Tích hợp backend-to-backend | Giao diện web đang mở | Fallback hoặc ứng dụng đơn giản |
| Khi mất kết nối | Sender retry có giới hạn, receiver dedup | Reconnect và replay nếu có event store | Đọc trạng thái khi online trở lại |
| Rủi ro chính | HMAC, SSRF, retry và secret | Authz, CORS, proxy timeout, giữ connection | Rate limit, polling interval |

Có thể dùng **cả webhook lẫn SSE** cho cùng operation, nhưng **GET operation** vẫn là đường kiểm tra trạng thái cuối. Không kênh nào tự bảo đảm exactly-once; chính sách retry/replay và xử lý idempotent phải được công bố.

## 5. Webhook: hợp đồng đăng ký tách khỏi thao tác bất đồng bộ

Không nên cho mọi POST tạo báo cáo tự chỉ định một **callbackUrl** tùy ý rồi bắt server gọi đến đó. Điều này mở rộng bề mặt **SSRF**, gây khó kiểm soát quyền, bí mật ký và chính sách retry.

Một hợp đồng rõ hơn có resource đăng ký riêng:

~~~http
POST /api/v1/webhook-subscriptions HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json

{
  "endpointUrl": "https://partner.example/hooks/operations",
  "eventTypes": ["operation.finished"]
}
~~~

Server kiểm tra quyền tạo subscription, URL đích và cơ chế xác nhận ownership, rồi trả:

~~~http
HTTP/1.1 201 Created
Location: /api/v1/webhook-subscriptions/sub-27
Content-Type: application/json

{
  "id": "sub-27",
  "status": "PENDING_VERIFICATION",
  "eventTypes": ["operation.finished"]
}
~~~

Sau khi endpoint được xác minh, subscription có thể chuyển sang **ACTIVE**. Bí mật ký webhook cần được cấp/luân chuyển qua kênh bảo mật, chỉ hiển thị theo chính sách một lần và không bao giờ được gửi trong event payload.

**Một subscription thuộc tenant/account đã xác thực.** Không cho người dùng thuộc T1 đăng ký nhận sự kiện operation của T2. Khi quyền hoặc subscription bị thu hồi, worker gửi webhook phải ngừng giao theo chính sách; event đã xếp hàng cũng cần được kiểm tra phạm vi trước khi gửi.

### URL callback và SSRF

Chỉ cho phép **HTTPS**, xác minh quyền sở hữu endpoint, chặn IP loopback/private/link-local/metadata và đích nội bộ cả khi **đăng ký lẫn kết nối thực** (DNS rebinding). Giới hạn DNS, redirect, IPv4/IPv6, timeout, response size và outbound egress. Không dùng callbackUrl tùy ý của mỗi request làm đích POST không kiểm soát.

## 6. Giao một webhook hoàn tất

Sau khi operation chuyển sang **SUCCEEDED** và event đã được lưu bền vững, delivery worker gửi HTTP POST:

~~~http
POST /hooks/operations HTTP/1.1
Host: partner.example
Content-Type: application/json
X-Webhook-Id: evt-9472
X-Webhook-Timestamp: 2026-11-18T09:03:21Z
X-Webhook-Subscription: sub-27
X-Webhook-Signature: sha256=<base64-hmac>

{
  "eventId": "evt-9472",
  "type": "operation.finished",
  "schemaVersion": 1,
  "operationId": "op-729",
  "sequence": 4,
  "status": "SUCCEEDED",
  "occurredAt": "2026-11-18T09:03:20Z",
  "operationUrl": "/api/v1/operations/op-729",
  "result": {"href":"/api/v1/reports/r-482"}
}
~~~

Tên header và thuật toán chữ ký trên đây là **hợp đồng riêng của API ví dụ**, không phải chuẩn bắt buộc mọi webhook provider sử dụng.

Receiver nên **xác minh chữ ký, kiểm tra event và lưu bền vững vào inbox/queue**, rồi ACK nhanh:

~~~http
HTTP/1.1 204 No Content
~~~

Một response 2xx ở receiver nghĩa là **sự kiện đã được tiếp nhận theo hợp đồng giao webhook**, **không có nghĩa job gốc mới vừa thành công**. Thành công/thất bại của job được diễn đạt trong **status** của event/operation resource.

### Retry và timeout

Mẫu chính sách có thể là:

| Tình huống giao webhook | Hành vi sender |
| --- | --- |
| Receiver trả **2xx** | Đánh dấu delivery thành công; không cần gửi lại chủ động |
| Timeout/connection reset | Kết quả **không rõ**; retry với **cùng eventId** |
| Receiver trả **429** hoặc **5xx** | Retry có giới hạn, backoff + jitter; tôn trọng Retry-After khi áp dụng |
| Receiver trả **400/401/403/404** | Thường coi là lỗi cấu hình/payload/quyền, không retry mù; phân loại theo contract |
| Vượt giới hạn lần thử hoặc retention | Đưa tới dead-letter/failed-delivery, có cảnh báo và cơ chế replay có kiểm soát |

Dù receiver đã **commit event** và trả 204, response có thể mất trên mạng, nên sender sẽ retry. Vì vậy receiver phải **deduplicate theo subscriptionId + eventId** hoặc khóa tương đương. Không thể hứa “giao đúng một lần” chỉ từ HTTP POST.

**Không retry vô hạn.** Hợp đồng phải công bố cửa sổ giao, số lần thử, backoff, ngưỡng timeout, hạn lưu, khả năng replay thủ công và cách quan sát dead-letter. Lần retry giữ **eventId và payload nghiệp vụ**, nhưng nên tạo **timestamp/chữ ký mới cho mỗi delivery attempt** nếu receiver có replay window ngắn.

## 7. Ký webhook bằng HMAC và chống replay

Một webhook endpoint thường công khai ra Internet. Chỉ biết URL không chứng minh request đến từ nhà cung cấp. Hợp đồng mẫu sử dụng:

~~~text
messageToSign = UTF8(timestamp + ".") || rawBodyBytes
signature = Base64(HMAC-SHA256(subscriptionSecret, messageToSign))
header = "sha256=" + signature
~~~

Receiver thực hiện:

1. Xác định **subscriptionId** và bí mật đang hoạt động qua cấu hình đáng tin, không tin tenantId trong JSON để chọn quyền.
2. Kiểm tra timestamp trong cửa sổ chấp nhận, ví dụ **±5 phút** với clock skew được kiểm soát.
3. Tính HMAC trên **raw request bytes**, không parse JSON rồi serialize lại trước khi xác minh.
4. So chữ ký bằng phép so sánh **constant-time** trên bytes.
5. Parse và validate schema/version, kiểm tra event thuộc subscription/event type được phép.
6. Ghi inbox có **unique (subscription_id, event_id)** và enqueue công việc **trong cùng transaction**, sau đó mới ACK.

### Spring: verifier tối giản

~~~java
public final class WebhookSigner {
    private WebhookSigner() {}

    public static boolean verify(
            byte[] body,
            String timestamp,
            String signatureHeader,
            byte[] secret) {

        Instant sentAt;
        try {
            sentAt = Instant.parse(timestamp);
        } catch (DateTimeParseException ex) {
            return false;
        }

        if (Math.abs(Duration.between(sentAt, Instant.now())
                .getSeconds()) > 300) {
            return false;
        }

        if (signatureHeader == null
                || !signatureHeader.startsWith("sha256=")) {
            return false;
        }

        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret, "HmacSHA256"));
            mac.update((timestamp + ".").getBytes(StandardCharsets.UTF_8));
            byte[] expected = mac.doFinal(body);
            byte[] supplied = Base64.getDecoder()
                .decode(signatureHeader.substring("sha256=".length()));
            return MessageDigest.isEqual(expected, supplied);
        } catch (GeneralSecurityException
                 | IllegalArgumentException ex) {
            return false;
        }
    }
}
~~~

Ví dụ cần import **Instant**, **Duration**, **DateTimeParseException**, **Mac**, **SecretKeySpec**, **Base64**, **StandardCharsets**, **MessageDigest**, **GeneralSecurityException**. Mã minh họa chỉ xác thực chữ ký/thời gian; **chưa kiểm tra replay eventId, authorization theo subscription và transaction inbox**. Những bước đó là bắt buộc ở tầng xử lý.

**HMAC không thay thế TLS** và không tự chống lặp. Một request hợp lệ bị gửi lại trong cửa sổ thời gian vẫn có chữ ký đúng; unique inbox là lớp ngăn tác dụng phụ trùng. Cần chính sách xoay khóa (key ID, thời gian chấp nhận khóa cũ ngắn), giới hạn kích thước body trước khi xác minh và bảo vệ secret ở secret manager.

### Spring: receiver ACK sau khi lưu bền vững

Sau khi xác minh HMAC, controller parse JSON thành **OperationEvent**, kiểm tra eventType/tenant/subscription và gọi một transaction ghi **inbox với unique (subscriptionId, eventId)** kèm outbox/queue nội bộ. Trả **204** sau khi commit; nếu eventId đã được nhận, ACK nhưng **không xử lý tác dụng phụ lần hai**. Nếu không lưu được, trả lỗi để sender retry.

Secret HMAC cần được luân chuyển, giới hạn quyền truy cập và lưu tại secret manager. TLS, giới hạn body size và authorization theo subscription vẫn bắt buộc: chữ ký hợp lệ không thay thế kiểm tra quyền.

## 8. Sender: chỉ phát event sau khi operation đã commit

Một cách triển khai an toàn cho API gốc:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant API as Spring API
    participant DB as DB + Outbox
    participant W as Worker
    participant D as Webhook delivery
    participant R as Receiver
    C->>API: POST /reports
    API->>DB: Tạo operation PENDING
    API-->>C: 202 + Location /operations/op-729
    W->>DB: Claim operation + xử lý
    W->>DB: Transaction: SUCCEEDED + result + outbox event
    D->>DB: Đọc outbox event đã commit
    D->>R: POST eventId evt-9472 + HMAC
    R-->>D: 204 sau khi lưu inbox
    Note over C,API: GET operation vẫn là nguồn sự thật
~~~

Nếu worker chỉ **đổi status trong DB** rồi phát webhook trực tiếp, quá trình có thể crash giữa commit và gửi: operation đã xong nhưng không có notification. **Transactional outbox** giúp lưu **chuyển trạng thái + event cần phát** trong cùng transaction. Delivery worker retry từ outbox; receiver idempotent vì event vẫn có thể được gửi nhiều lần.

Trạng thái **SUCCEEDED** phải có nghĩa là kết quả cốt lõi đã sẵn sàng theo contract. Không phát operation.finished khi mới chỉ đưa lệnh tiếp theo vào queue mà nghiệp vụ vẫn chưa hoàn thành.

Với một operation đã ở trạng thái terminal, worker retry không được tạo nhiều **sự kiện hoàn tất logic** khác nhau. Có thể dùng unique constraint theo operationId + eventType + terminalVersion, đồng thời giữ eventId ổn định qua các delivery attempt.

## 9. SSE: client mở GET và nhận sự kiện từ server

SSE sử dụng HTTP **GET**, response **200 OK** với media type **text/event-stream**. Khác webhook, client chủ động mở kết nối tới API và đọc các sự kiện một chiều.

~~~http
GET /api/v1/operations/op-729/events HTTP/1.1
Host: api.example.com
Accept: text/event-stream
Authorization: Bearer <access-token>
~~~

Server giữ kết nối mở và gửi các frame ngăn bằng **dòng trống**:

~~~http
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache

: connected

id: op-729:4
event: operation.finished
data: {"eventId":"evt-9472","operationId":"op-729","sequence":4,"status":"SUCCEEDED","operationUrl":"/api/v1/operations/op-729"}

~~~

Ý nghĩa các dòng:

- **id:** cursor của sự kiện trong luồng; trình duyệt có thể gửi lại qua **Last-Event-ID** khi reconnect.
- **event:** tên loại, ví dụ **operation.finished**.
- **data:** nội dung UTF-8; có thể là một JSON object đã serialize.
- **retry:** có thể xuất hiện dưới dạng **retry: 5000** để gợi ý thời gian reconnect (mili giây) cho EventSource; không phải cam kết event sẽ được giữ mãi.
- Dòng bắt đầu bằng **:** là comment/heartbeat, không tạo event ứng dụng.
- **Dòng trống** kết thúc một event frame.

SSE không cho client gửi lệnh nghiệp vụ ngược lên trong cùng stream. Muốn hủy operation, client vẫn gọi một endpoint HTTP riêng như POST tới cancel action hoặc resource tương ứng nếu API hỗ trợ.

### Client EventSource

~~~javascript
const operationId = "op-729";
const stream = new EventSource(
  "/api/v1/operations/" + operationId + "/events",
  { withCredentials: true }
);

stream.addEventListener("operation.finished", async (message) => {
  const event = JSON.parse(message.data);
  // Event là tín hiệu: đọc trạng thái thật và cập nhật UI.
  await refreshOperationFromApi(event.operationId);
  stream.close();
});

stream.onerror = () => {
  // EventSource thường thử reconnect.
  // UI cũng cần polling/fallback nếu stream không sử dụng được.
};
~~~

**Giới hạn của EventSource trình duyệt:** API chuẩn không cho tùy ý đặt header **Authorization: Bearer ...**. Với browser có thể dùng cookie phiên phù hợp **SameSite/Secure/HttpOnly**, origin và CORS được cấu hình đúng, hoặc dùng client SSE dựa trên fetch hỗ trợ header nếu kiến trúc token cần nó. **Không đưa access token vào query string** để vượt giới hạn này, vì URL dễ đi vào log, lịch sử và telemetry.

## 10. Spring MVC: SSE với SseEmitter

Một controller minh họa:

~~~java
@RestController
@RequestMapping("/api/v1/operations")
public class OperationStreamController {

    private final OperationAccess access;
    private final DurableEventStream streamService;

    // Constructor injection được lược bỏ.

    @GetMapping(value = "/{id}/events",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public ResponseEntity<SseEmitter> subscribe(
            @PathVariable String id,
            @RequestHeader(value = "Last-Event-ID",
                           required = false) String lastEventId,
            Authentication principal) {

        access.requireReadPermission(principal, id);

        SseEmitter emitter = new SseEmitter(15 * 60 * 1000L);
        streamService.subscribeAndReplay(id, lastEventId, emitter);

        emitter.onCompletion(
            () -> streamService.unsubscribe(id, emitter));
        emitter.onTimeout(() -> {
            streamService.unsubscribe(id, emitter);
            emitter.complete();
        });
        emitter.onError(error ->
            streamService.unsubscribe(id, emitter));

        return ResponseEntity.ok()
            .contentType(MediaType.TEXT_EVENT_STREAM)
            .cacheControl(CacheControl.noCache())
            .body(emitter);
    }
}
~~~

Service gửi một event bằng:

~~~java
emitter.send(SseEmitter.event()
    .id("op-729:4")
    .name("operation.finished")
    .data(eventPayload, MediaType.APPLICATION_JSON));
~~~

Đây là **mẫu wiring**, không phải implementation hoàn chỉnh của **DurableEventStream**. Để không mất event trong khe thời gian giữa replay và đăng ký live, service cần cơ chế **đọc backlog + đăng ký nhận event mới** với ranh giới thứ tự rõ ràng. Một registry **SseEmitter lưu trong memory của một pod** sẽ mất connection/event khi pod restart và không tự nhận event do worker ở pod khác tạo. Hệ thống nhiều instance cần durable event log/outbox và message broker hoặc bus phù hợp để phân phối, hoặc một cơ chế polling nội bộ theo sequence.

Cần quản lý **timeout, hoàn tất, lỗi, close/disconnect và dọn emitter** để tránh rò bộ nhớ. Bảo vệ số lượng kết nối đồng thời, tốc độ event và giới hạn một tenant. Heartbeat comment định kỳ có thể giúp giảm khả năng proxy đóng kết nối idle, nhưng không vượt qua mọi timeout của load balancer.

## 11. Last-Event-ID và khả năng khôi phục sau mất kết nối

SSE qua mạng không bảo đảm client luôn nhận được event kết thúc. Ví dụ:

~~~text
T1: Client kết nối, nhận id op-729:2.
T2: Mạng ngắt.
T3: Worker hoàn thành operation, sinh event sequence=4.
T4: Client reconnect, gửi Last-Event-ID: op-729:2.
T5: Server replay sequence > 2 còn trong retention.
~~~

Request reconnect có thể là:

~~~http
GET /api/v1/operations/op-729/events HTTP/1.1
Accept: text/event-stream
Last-Event-ID: op-729:2
~~~

**Last-Event-ID là cơ chế định vị lại, không tự bảo đảm replay.** Server phải có **event store bền vững**, thứ tự/cursor rõ và retention đủ dài. Nếu chỉ giữ sự kiện trong memory, có thể không còn gì để phát lại sau restart.

Một contract thực tế nên quy định:

1. Cursor là **sequence theo operation**, không lấy timestamp client làm thứ tự duy nhất.
2. Chỉ chấp nhận cursor hợp lệ cho operation/tenant hiện tại; không dùng cursor để đọc dữ liệu operation khác.
3. Replay những event sau cursor, sau đó chuyển sang live **không có khe hở**.
4. Event đã nhận lại có thể trùng; client xử lý idempotent theo eventId/sequence.
5. Khi cursor **quá hạn hoặc không còn trong retention**, server báo một cách có hợp đồng (ví dụ lỗi 409 hoặc thông điệp reset theo thiết kế), rồi client **GET operation** để phục hồi trạng thái cuối.
6. Nếu nhận **operation.finished** rồi ngắt, client có thể đóng stream và đọc lại trạng thái canonical; không cần giữ SSE mãi.

**Đừng tự tuyên bố exactly-once delivery.** Ngay cả với replay, client có thể nhận trùng event nếu kết nối hỏng tại ranh giới ACK không tồn tại trong SSE. Cách đúng là **at-least-once trong cửa sổ replay được hỗ trợ + idempotent handling + GET fallback**.

## 12. Bảo mật SSE và quyền xem operation

SSE có thể giữ kết nối lâu, nhưng **quyền không được chỉ kiểm tra một lần rồi mặc định vĩnh viễn**.

- Kiểm tra caller có quyền đọc operation khi **mở stream**; khi reconnect phải xác thực lại.
- Nếu session hoặc quyền bị thu hồi trong lúc stream đang chạy, có chính sách đóng/revalidate theo thời hạn hợp lý.
- Không để người dùng đoán operation ID rồi subscribe vào kết quả của tenant khác.
- Với cookie authentication, cấu hình **SameSite, Secure, CORS allowlist** và chính sách cross-origin credentials; không đặt wildcard CORS cho stream nhạy cảm.
- Giới hạn số kết nối mở mỗi account/IP và tổng memory/file descriptor; stream không có giới hạn có thể gây DoS.

**SSE vẫn dùng HTTP GET** và không nên có tác dụng ghi nghiệp vụ. Client muốn xác nhận, hủy hoặc thay đổi job phải gọi method/resource được thiết kế riêng, với quyền và precondition phù hợp.

## 13. OpenAPI: ba hợp đồng riêng

OpenAPI mô tả **202 nhận job**, **GET operation status** và **200 text/event-stream**. Webhook outbound có thể mô tả qua **webhooks** trong OpenAPI 3.1 hoặc hợp đồng delivery riêng.

~~~yaml
openapi: 3.1.0
info: { title: Async Reports API, version: 1.0.0 }
paths:
  /api/v1/reports:
    post:
      summary: Yêu cầu tạo báo cáo bất đồng bộ
      parameters:
        - in: header
          name: Idempotency-Key
          required: true
          schema: { type: string }
      responses:
        '202':
          description: Đã nhận job, chưa hứa hoàn tất
          headers:
            Location:
              schema: { type: string, format: uri-reference }
          content:
            application/json:
              schema:
                type: object
                required: [operationId, status, statusUrl]
                properties:
                  operationId: { type: string }
                  status: { type: string }
                  statusUrl: { type: string, format: uri-reference }
  /api/v1/operations/{id}:
    get:
      parameters:
        - in: path
          name: id
          required: true
          schema: { type: string }
      responses:
        '200':
          description: Trạng thái nguồn sự thật
          content:
            application/json:
              schema: { $ref: '#/components/schemas/Operation' }
  /api/v1/operations/{id}/events:
    get:
      parameters:
        - in: path
          name: id
          required: true
          schema: { type: string }
        - in: header
          name: Last-Event-ID
          schema: { type: string }
      responses:
        '200':
          description: SSE với event operation.finished
          content:
            text/event-stream:
              schema: { type: string }
components:
  schemas:
    Operation:
      type: object
      required: [id, status]
      properties:
        id: { type: string }
        status:
          type: string
          enum: [PENDING, RUNNING, SUCCEEDED, FAILED, CANCELLED]
        result:
          type: object
          properties:
            href: { type: string, format: uri-reference }
~~~

Triển khai thật cần bổ sung request body, security scheme, lỗi 400/401/403/404, schema webhook/event, retention và replay. Các status/event name phải nhất quán giữa tài liệu và code.

## 14. Kiểm thử HTTP, giao lại và phục hồi

### 14.1. Test HTTP cho việc tiếp nhận

~~~java
@Test
void returnsAcceptedWithOperationLocation() throws Exception {
    mockMvc.perform(post("/api/v1/reports")
            .header("Idempotency-Key", "report-intent-729")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {"reportType":"SALES",
                 "from":"2026-11-01","to":"2026-11-17"}
                """))
        .andExpect(status().isAccepted())
        .andExpect(header().string("Location",
                                   startsWith("/api/v1/operations/")))
        .andExpect(jsonPath("$.status").value("PENDING"))
        .andExpect(jsonPath("$.operationId").isNotEmpty());
}
~~~

Test giả định controller tạo operation đã được cài đặt và người gọi có quyền. **MockMvc không chứng minh worker đã xử lý hoàn tất**; cần integration test gửi job qua queue/worker và GET operation để kiểm tra trạng thái.

### Ma trận test tích hợp

| Tình huống | Bằng chứng |
| --- | --- |
| Worker chạy lại cùng job | Một terminal transition và một event logic trong outbox |
| Receiver commit nhưng ACK webhook mất | Sender retry; inbox chỉ áp dụng eventId một lần |
| HMAC sai/timestamp quá hạn | Từ chối trước khi ghi inbox |
| Webhook 429/5xx | Backoff, Retry-After và dead-letter đúng |
| URL callback nội bộ hoặc redirect nguy hiểm | Bị chặn theo chính sách SSRF |
| SSE kết nối đúng quyền | 200 text/event-stream, id/event/data và dòng trống đúng |
| SSE ngắt rồi reconnect | Last-Event-ID replay từ durable store, không mất event |
| Cursor quá hạn | Client GET operation để phục hồi |
| Tenant khác hoặc bị thu hồi quyền | Không đọc/nhận event trái quyền |
| Proxy timeout, nhiều kết nối | Heartbeat, cleanup và connection limit |
| Không nhận notification | GET operation vẫn có trạng thái cuối |

Integration test cần database/queue và HTTP client streaming thật: **MockMvc 202 không chứng minh** webhook delivery, atomic outbox hoặc SSE replay. Dùng hai worker cùng operation và giả lập commit rồi mất ACK để kiểm chứng chống lặp.

## 15. Bài tập: xuất báo cáo và thông báo đa kênh

Một hệ thống quản trị cho phép xuất báo cáo doanh số cho từng tenant. Tạo báo cáo mất 30 giây đến 5 phút. Người dùng theo dõi trên web qua SSE; hệ thống đối tác nhận webhook khi hoàn tất. Kết quả là tài nguyên **/api/v1/reports/{reportId}**; báo cáo chỉ được tải bởi người có quyền.

Thiết kế một API đáp ứng yêu cầu:

1. **POST /reports:** trả 202 + Location operation, có Idempotency-Key để retry sau timeout không tạo nhiều job.
2. **GET /operations/{id}:** trạng thái PENDING/RUNNING/SUCCEEDED/FAILED, metadata, result/error an toàn, retention.
3. **Webhook subscription:** đăng ký và xác minh HTTPS callback, quản lý secret, kiểm tra tenant, tránh SSRF.
4. **Webhook event:** định nghĩa eventId, operationId, status, schemaVersion, occurredAt; ký HMAC raw body + timestamp, 2xx ACK, retry/backoff/dead-letter và receiver inbox dedup.
5. **SSE:** GET /operations/{id}/events với frame id/event/data, Last-Event-ID, replay window và xử lý khi browser mất mạng.
6. **Security:** xác thực, quyền operation/report, CORS/cookie hoặc cơ chế bearer phù hợp, tránh URL token, giới hạn kết nối.
7. **Java/Spring:** controller nhận job, worker/outbox, webhook receiver và SseEmitter hoặc công nghệ streaming tương đương.
8. **Testing:** ít nhất 10 test bao gồm 202, terminal transition, lost ACK, webhook giả mạo, event trùng, tenant isolation, SSE reconnect, cursor hết hạn, proxy timeout và fallback GET.
9. **ADR:** giải thích khi nào dùng webhook, SSE hoặc cả hai; định nghĩa mục tiêu độ trễ thông báo và giới hạn bảo đảm giao sự kiện.

**Tiêu chí đạt:** không tạo hai report do retry; operation terminal là nguồn sự thật; không mất sự kiện trong khoảng commit–publish; các bản giao lặp không gây tác dụng phụ; mất kết nối không làm client không thể biết kết quả; không lộ dữ liệu khác tenant.

## 16. Kết luận

**Webhook và SSE giải quyết bài toán thông báo, không thay thế nguồn sự thật của thao tác bất đồng bộ.** Hợp đồng đáng tin bắt đầu từ **202 Accepted + operation resource**, sau đó phát event có **ID ổn định, trạng thái rõ ràng và quyền truy cập đúng**.

**Webhook** phù hợp giao tiếp server-to-server nhưng cần xác minh chữ ký, giới hạn retry, inbox và chống SSRF. **SSE** phù hợp giao diện đang mở nhưng cần kiểm soát kết nối, quyền truy cập, Last-Event-ID, replay và polling fallback. Trong cả hai, phải chấp nhận khả năng sự kiện được giao lại hoặc bị bỏ lỡ trong giới hạn retention đã công bố, rồi thiết kế **idempotent handling và GET reconciliation**.

Câu hỏi thiết kế quan trọng nhất là: **“Nếu job đã hoàn tất nhưng mọi kênh thông báo đều lỗi, client vẫn có cách xác định đúng kết quả mà không chạy lại công việc hay không?”**
