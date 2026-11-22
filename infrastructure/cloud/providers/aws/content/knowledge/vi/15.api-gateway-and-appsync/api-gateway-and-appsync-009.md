# WebSocket route và quản lý kết nối thời gian thực

> **Chương:** API Gateway và AppSync  
> **Học phần:** `CLOUD_PROVIDERS_AWS` — khám phá AWS từ Region/AZ, IAM, VPC đến tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless; luyện chọn dịch vụ, triển khai an toàn, giám sát, phục hồi và tối ưu chi phí.

Thông thường, một ứng dụng web gửi HTTP request rồi nhận HTTP response; nếu muốn biết có tin nhắn mới hay không, client phải gửi thêm request hoặc dùng những cơ chế streaming khác. Với **WebSocket**, client và server thiết lập **một kết nối hai chiều tồn tại trong một khoảng thời gian**, cho phép cả hai phía gửi thông điệp mà không cần mở một HTTP request mới cho mỗi sự kiện.

**Amazon API Gateway WebSocket API** cung cấp một điểm kết nối `wss://...` được quản lý, định tuyến **message** tới tích hợp backend như **AWS Lambda**, và hỗ trợ backend chủ động gửi dữ liệu về các client đang kết nối thông qua **API Gateway Management API** (`@connections`). Đây là lựa chọn hữu ích cho chat, bảng điều khiển cập nhật theo sự kiện, cộng tác trực tuyến, trạng thái thiết bị và thông báo thời gian thực.

Nhưng API Gateway **không lưu mặc định** danh sách “người dùng A đang ở phòng chat B”, không bảo đảm mọi sự kiện nghiệp vụ được giao đúng một lần, và không tự lưu tin nhắn offline. Ứng dụng cần quản lý **connection ID, identity, đăng ký kênh, quyền truy cập, fan-out, retry và trạng thái** trong dịch vụ phía sau như DynamoDB, Lambda, SQS hoặc EventBridge.

Các API IDs, tài khoản, Region, bảng DynamoDB và tên miền trong ví dụ là **placeholder**, không phải tài nguyên đang tồn tại. Mọi thay đổi hạ tầng có thể tạo chi phí; chỉ triển khai vào môi trường thử được phép quản lý.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **API Gateway WebSocket API** với HTTP API/REST API và mô hình AppSync subscriptions khi chọn kênh truyền thời gian thực.
2. Mô tả vòng đời **HTTP Upgrade → `$connect` → messages → `$disconnect`** cùng các giới hạn của sự kiện disconnect.
3. Thiết kế **route selection expression** `$request.body.action`, ba route đặc biệt `$connect`, `$disconnect`, `$default` và custom routes.
4. Giải thích sự khác biệt giữa **response của Lambda integration** và **push tới client** qua `@connections`.
5. Cấu hình quyền ở bước bắt tay WebSocket, phân biệt **IAM `execute-api:Invoke`** và **`execute-api:ManageConnections`**, và bảo vệ dữ liệu theo người dùng/phòng chat.
6. Lưu trạng thái kết nối trong DynamoDB, xử lý **410 Gone**, heartbeat, TTL, reconnect và tin nhắn offline.
7. Đọc ví dụ Lambda/Node.js, client JavaScript, CloudFormation fragment, cùng các lệnh AWS CLI chỉ đọc phục vụ chẩn đoán.
8. Dự toán thông lượng, latency, số kết nối, chi phí và kiểm thử ứng dụng trong tình huống mất kết nối.

## 2. Vì sao cần WebSocket?

### 2.1. HTTP polling, Server-Sent Events và WebSocket

| Cơ chế | Hướng truyền | Đặc tính | Tình huống phù hợp |
| --- | --- | --- | --- |
| **HTTP polling** | Client hỏi, server trả | Đơn giản nhưng có request lặp ngay cả khi không có dữ liệu | Dashboard ít yêu cầu realtime |
| **Long polling** | Client gửi request, server giữ cho đến khi có dữ liệu/timeout | Giảm request vô ích, vẫn cần mở lại | Notification cần hạn chế công nghệ mới |
| **Server-Sent Events (SSE)** | Server → client qua kết nối HTTP dài | Thuận tiện cho luồng sự kiện một chiều | Trạng thái tiến độ, streaming output |
| **WebSocket** | **Client ↔ server** trên một connection | Full-duplex; các message tới cùng endpoint WebSocket | Chat, cộng tác, telemetry, trạng thái realtime |

WebSocket không tự đáng tin cậy ở **tầng nghiệp vụ**. TCP cung cấp thứ tự byte cho một connection còn sống, nhưng **khi rớt mạng**, server/client vẫn cần thỏa thuận về retry, idempotency và phát lại các message chưa được xác nhận.

### 2.2. API Gateway WebSocket khác AppSync ở đâu?

| Nhu cầu | API Gateway WebSocket API | AWS AppSync |
| --- | --- | --- |
| Giao thức và mô hình | Message WebSocket do ứng dụng định nghĩa; route theo trường của payload | GraphQL API với subscriptions hoặc các tính năng realtime/events tùy loại API |
| Định tuyến | `$connect`, `$disconnect`, `$default`, custom route keys | GraphQL schema/resolver/subscription hoặc cơ chế event tương ứng |
| Trạng thái người dùng/phòng | Ứng dụng thiết kế registry/authorization/fan-out | Có các abstraction realtime khác; vẫn cần thiết kế auth và dữ liệu |
| Phù hợp | Muốn kiểm soát protocol, command/room, callback logic | Ứng dụng phù hợp data model GraphQL hoặc realtime/event model AppSync |
| Công quản trị backend | Tự quản nhiều phần của message routing, delivery, registry | Có thể giảm một số công việc nhờ abstraction phù hợp |

**Không mặc định WebSocket là lựa chọn duy nhất cho realtime**. Khi client chỉ cần truy vấn/thay đổi dữ liệu có schema GraphQL và lắng nghe thay đổi, AppSync subscriptions có thể thuận tiện hơn. Khi cần protocol message tùy biến và route độc lập, API Gateway WebSocket API cho phép kiểm soát rõ hơn.

## 3. Kiến trúc tham chiếu: client, API Gateway, Lambda và DynamoDB

~~~mermaid
flowchart TB
    C1["Client A\ntrình duyệt / mobile"] <-->|"WSS: $connect + message"| GW["API Gateway\nWebSocket API + stage"]
    C2["Client B\ntrình duyệt / mobile"] <-->|"WSS"| GW
    GW -->|"Route: $connect / $disconnect"| CONN["Lambda ConnectionHandler"]
    GW -->|"Route: join / sendMessage / $default"| MSG["Lambda MessageHandler"]
    CONN <-->|"Put/Delete trạng thái"| DDB["DynamoDB\nConnections + RoomMembers"]
    MSG <-->|"Query membership / kiểm tra quyền"| DDB
    MSG -->|"POST @connections/{id}"| MGMT["API Gateway Management API\nHTTPS endpoint"]
    MGMT -->|"Push message"| GW
    EVENTS["SQS / EventBridge / workflow\nkhi có sự kiện nghiệp vụ"] -->|"Async trigger"| PUSH["Lambda NotificationWorker"]
    PUSH -->|"Đọc subscriptions"| DDB
    PUSH -->|"POST @connections"| MGMT
~~~

*Sơ đồ mô tả các kết nối logic. API Gateway không yêu cầu mọi message đi qua cùng một Lambda; có thể dùng nhiều Lambda integrations hoặc các backend khác. Traffic từ API Gateway đến Lambda là lời gọi integration, không phải client WebSocket kết nối trực tiếp tới Lambda.*

**Một flow chat mẫu:**

1. Client A mở URL dạng `wss://{api-id}.execute-api.{region}.amazonaws.com/{stage}`.
2. API Gateway xử lý yêu cầu Upgrade và invoke tích hợp route `$connect` để xác thực/khởi tạo state.
3. A gửi JSON `{"action":"join","roomId":"lobby"}`; API Gateway chọn route `join`.
4. Lambda kiểm tra người dùng có quyền vào phòng rồi thêm `connectionId` vào registry.
5. A gửi `{"action":"sendMessage","roomId":"lobby","text":"Xin chào"}`.
6. Lambda đọc các connection IDs đang thuộc phòng và gọi **Management API** để push tới từng kết nối phù hợp.
7. Khi client B nhận message trên connection đang mở, ứng dụng B hiển thị nội dung và xử lý thứ tự/idempotency theo protocol.

**Khác biệt quan trọng:** Lambda không giữ một socket sống trong RAM giữa những lần invoke. API Gateway giữ kết nối WebSocket, còn backend dùng connection ID và callback API để gửi lại dữ liệu.

## 4. Vòng đời của kết nối WebSocket

### 4.1. HTTP Upgrade và route `$connect`

Một client yêu cầu kết nối qua giao thức `wss://` (WebSocket chạy trên TLS). Trước khi WebSocket được chấp nhận, API Gateway xử lý tích hợp của route **`$connect`**.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as API Gateway WebSocket
    participant A as $connect authorizer
    participant L as $connect integration Lambda
    participant D as DynamoDB Connections
    C->>G: HTTPS Upgrade (WSS handshake)
    G->>A: Kiểm tra quyền $connect (nếu cấu hình)
    alt Không được phép
        A-->>G: Deny
        G-->>C: HTTP 401/403; không thiết lập socket
    else Được phép
        A-->>G: Principal/context
        G->>L: Event $connect + connectionId
        L->>D: Lưu connectionId, userId, TTL
        L-->>G: statusCode 200
        G-->>C: WebSocket handshake hoàn tất
    end
~~~

Lưu ý:

- Chỉ khi `$connect` được xử lý thành công thì client mới có một WebSocket connection đã thiết lập. Nếu auth/integration thất bại, handshake có thể bị từ chối.
- `connectionId` được API Gateway gán cho connection và xuất hiện trong `event.requestContext.connectionId`.
- Client không nên tự tạo hoặc giả mạo connection ID để backend sử dụng; server đọc từ request context của API Gateway.
- **Không gửi callback qua `@connections` quá sớm trong chính lúc `$connect` chưa hoàn tất**: connection có thể chưa sẵn sàng và trả **410 GoneException**. Nếu muốn gửi thông báo chào mừng, để client gửi lệnh `join`/`ready` sau sự kiện `open` hoặc dùng workflow bất đồng bộ chỉ gửi khi kết nối thực sự tồn tại.

### 4.2. Nhận một message

Khi connection còn sống, mỗi message được client gửi tới WebSocket API đi qua **route selection expression**. API Gateway chọn custom route theo key hoặc `$default` rồi invoke integration.

Ví dụ request:

~~~json
{
  "action": "sendMessage",
  "roomId": "lobby",
  "messageId": "msg-000123",
  "text": "Tình trạng đơn hàng của tôi?"
}
~~~

Backend nhận event chứa body của message và context của connection. Backend có thể truy vấn dữ liệu hoặc tạo sự kiện async, sau đó gửi kết quả tới người dùng thông qua `@connections`.

### 4.3. Đóng kết nối và `$disconnect`

Kết nối có thể đóng vì client gọi `close()`, mất mạng, hết hạn/idle timeout, API Gateway chấm dứt hoặc backend chủ động disconnect qua Management API.

Route **`$disconnect`** được gọi **sau khi** connection đã đóng và là sự kiện **best effort**: không có bảo đảm rằng nó sẽ luôn được gọi, đến đúng thời điểm hoặc sẽ cho phép dọn sạch mọi bản ghi liên quan.

Vì vậy:

- Dùng `$disconnect` để **cố gắng xóa** connection registry/membership theo connection ID.
- Có **TTL/cleanup** hoặc định kỳ kiểm tra connection IDs không còn hoạt động.
- Khi gọi `postToConnection` nhận **410 Gone**, xóa stale connection có kiểm soát.
- Không cố reply qua WebSocket cho connection đã kết thúc trong `$disconnect`.
- Không suy rằng người dùng offline ngay tức thì khi chỉ nhìn một bản ghi DynamoDB chưa được dọn.

### 4.4. Hạn mức thời lượng

Theo các hạn mức thông dụng của API Gateway WebSocket APIs, connection có **idle timeout khoảng 10 phút** và **thời lượng tối đa khoảng 2 giờ**. Khi tới giới hạn, client phải thiết lập một connection mới và có thể nhận connection ID khác. Các quota/hạn mức có thể thay đổi theo thời điểm và Region; trước triển khai cần kiểm tra trang **API Gateway quotas** hiện hành.

Ứng dụng thường có cơ chế **heartbeat ở tầng application**, ví dụ client gửi JSON `{"action":"ping"}` mỗi khoảng thời gian phù hợp để biểu đạt trạng thái đang hoạt động, và có **reconnect với exponential backoff + jitter** khi connection đóng. Heartbeat không vượt qua giới hạn thời lượng kết nối tối đa của dịch vụ.

## 5. Route selection expression và các loại route

### 5.1. Route key được chọn ra sao?

Khi tạo API Gateway WebSocket API, ta chọn:

~~~text
Route selection expression: $request.body.action
~~~

Nghĩa là với mỗi **JSON text message** có trường `action`, API Gateway dùng giá trị đó để tìm **route key** tương ứng:

| Client gửi | Route được chọn | Ý nghĩa |
| --- | --- | --- |
| `{"action":"join","roomId":"lobby"}` | `join` | Đăng ký tham gia phòng |
| `{"action":"sendMessage","text":"Hi"}` | `sendMessage` | Gửi dữ liệu tới backend |
| `{"action":"ping"}` | `ping` nếu đã định nghĩa | Heartbeat tầng ứng dụng |
| `{"action":"unknown"}` | `$default` | Không tìm thấy custom route tương ứng |
| `{"payload":"x"}` | `$default` | Không chọn được giá trị `action` hợp lệ |
| Text không phải JSON hợp lệ | `$default` trong các trường hợp được Gateway hỗ trợ | Nên xử lý lỗi protocol rõ ràng |

**Không nhầm route selection expression với authorization**. Người dùng có thể gửi `action:"adminDelete"` nếu biết tên route; backend vẫn phải kiểm tra quyền nghiệp vụ và dữ liệu, bất kể route nào được gọi.

### 5.2. Ba route đặc biệt

| Route | Khi nào được dùng? | Trách nhiệm phù hợp |
| --- | --- | --- |
| **`$connect`** | Khi bắt tay mở connection | Xác thực/ủy quyền, khởi tạo connection registry, từ chối handshake không hợp lệ |
| **`$disconnect`** | Sau khi connection đã đóng (best effort) | Dọn connection/membership, ghi log trạng thái |
| **`$default`** | Khi không tìm thấy route hoặc không chọn được route key phù hợp | Thông báo lệnh sai, xử lý fallback, giới hạn payload |

Ba route trên không phải custom action mà client gửi bằng JSON để giả lập lifecycle. Client gửi `{"action":"$disconnect"}` **không tương đương** với việc đóng connection; muốn đóng client gọi WebSocket `close()` hoặc server dùng `deleteConnection` theo quyền.

### 5.3. Custom routes

Ứng dụng thường tạo:

~~~text
join          → kiểm tra và ghi membership
leave         → rời phòng
sendMessage   → xác thực, lưu nội dung và fan-out
typing        → tín hiệu đang nhập (thường không cần lưu lâu)
ping          → heartbeat/application keepalive
$default      → trả lỗi action không hỗ trợ
~~~

Chọn các action names ổn định và xác thực JSON schema ở backend. Với các command nguy hiểm như chuyển quyền, xóa dữ liệu hay gửi thông báo hàng loạt, việc có route **không bao giờ thay thế** IAM/business authorization và validation.

## 6. Integration response khác callback `@connections`

Một sự nhầm lẫn rất phổ biến là cho rằng Lambda trả:

~~~javascript
return { statusCode: 200, body: JSON.stringify({ ok: true }) };
~~~

thì client WebSocket **tự nhận** message `{"ok":true}` như một HTTP API response. Trong WebSocket API Gateway, response của Lambda còn phụ thuộc cấu hình **integration response** và **route response**.

### 6.1. Hai cách gửi dữ liệu cho client

| Cách | Cơ chế | Khi thích hợp |
| --- | --- | --- |
| **Route response / integration response** | API Gateway xử lý phản hồi integration, gửi theo cấu hình route response được hỗ trợ | Phản hồi trực tiếp cho message, nếu API được thiết lập two-way communication |
| **Management API `postToConnection`** | Backend gọi HTTPS `POST /@connections/{connectionId}` | Chủ động gửi tới một hay nhiều clients, kể cả sau khi xử lý bất đồng bộ |

Mặc định có thể tồn tại mô hình **one-way** (client gửi, backend chạy nhưng không có payload trả về tự động). Muốn dùng two-way responses, phải cấu hình đúng route response và integration response; với WebSocket API, **route response key được hỗ trợ là `$default`**. Các lựa chọn mapping khác nhau theo loại integration.

**Thiết kế chat/notification thông thường nên hiểu và sử dụng Management API**, vì backend phải push tới những client khác ngoài người đã gửi message. API Gateway không tự broadcast message đến tất cả những connection cùng API.

### 6.2. Management API dùng HTTPS, không dùng WSS

Client kết nối qua URL:

~~~text
wss://a1b2c3d4.execute-api.ap-southeast-1.amazonaws.com/prod
~~~

Backend gửi callback qua:

~~~text
https://a1b2c3d4.execute-api.ap-southeast-1.amazonaws.com/prod
    └─ POST /@connections/{connectionId}
~~~

Các thao tác `@connections` chính:

- **POST**: gửi bytes của message cho một connection đang tồn tại.
- **GET**: xem metadata/trạng thái được API hỗ trợ của connection.
- **DELETE**: yêu cầu đóng connection.

Chúng **không dùng quyền/endpoint của AWS HTTP API routes thông thường**; backend cần **IAM `execute-api:ManageConnections`** với đúng API ID/stage và resource ARN.

Với **custom domain name/API mapping**, URL callback HTTPS có thể cần **base path mapping** phù hợp; không được tự động nối `/{stage}` vào mọi custom-domain URL. Cách ít gây nhầm lẫn là cấu hình `CALLBACK_ENDPOINT` rõ ràng theo từng môi trường hoặc dùng requestContext domain/stage với logic hiểu custom domain.

### 6.3. Khi nào nhận 410 Gone?

`GoneException` (thường HTTP **410**) xảy ra khi connection ID không còn hoạt động hoặc chưa sẵn sàng ở thời điểm callback. Ví dụ:

- Client đã đóng tab hoặc mất mạng.
- Kết nối hết hạn, API Gateway đã đóng.
- Backend giữ một connection ID cũ trong DynamoDB.
- Gửi callback trong `$connect` trước khi handshake hoàn tất.

Hướng xử lý đúng: **đánh dấu connection stale/xóa registry theo ID** và, nếu sự kiện phải được bảo đảm giao nhận, lưu message ở queue/persistent inbox để client lấy khi reconnect. Không retry vô hạn tới một connection đã Gone.

### 6.4. Các lỗi callback khác

| Tình trạng | Ý nghĩa thường gặp | Hướng xử lý |
| --- | --- | --- |
| **403 Forbidden** | Backend thiếu `ManageConnections`, ARN sai hoặc policy khác chặn | Kiểm tra role, API ID, stage, custom domain |
| **410 Gone** | Connection không tồn tại/đã đóng | Cleanup registry, không retry vô hạn |
| **413 Payload Too Large** | Payload vượt giới hạn API | Giảm kích thước, gửi tham chiếu S3/data URI được bảo vệ |
| **429 / throttling** | Vượt giới hạn request/message | Bounded concurrency, backoff + jitter, queue |
| **5xx / timeout** | Lỗi dịch vụ/tạm thời hoặc mạng | Retry có giới hạn và idempotency ở ứng dụng |

HTTP 200 từ `postToConnection` chứng tỏ Gateway chấp nhận thao tác, **không tương đương chứng nhận client đã đọc/hiển thị/xử lý message**. Nếu nghiệp vụ cần delivery guarantee, client phải gửi **application-level acknowledgement** và server quản lý trạng thái cho từng message.

## 7. Xác thực và phân quyền kết nối

### 7.1. Xác thực ở thời điểm `$connect`

API Gateway WebSocket API cho phép kiểm soát quyền trên route **`$connect`**, thường qua cơ chế IAM hoặc **Lambda REQUEST authorizer** theo cấu hình hỗ trợ. Không nên mặc định có một **Cognito User Pools authorizer dạng REST/HTTP** hoạt động y hệt cho WebSocket API; khi dùng Cognito JWT có thể xác minh trong Lambda authorizer và áp dụng chính sách cụ thể.

~~~mermaid
flowchart LR
    B["Client mở WSS"] --> A{"$connect authorizer"}
    A -->|"Deny"| X["Không mở socket"]
    A -->|"Allow + principalId"| C["$connect Lambda"]
    C --> REG["Registry connectionId ↔ userId"]
    REG --> OK["Handshake thành công"]
    OK --> MSG["Custom routes"]
    MSG --> PERM{"Kiểm tra quyền từng action/room"}
    PERM -->|"Allowed"| RUN["Thực hiện nghiệp vụ / push"]
    PERM -->|"Denied"| ERR["Gửi error theo protocol"]
~~~

**Cần phân biệt:**

- `$connect` xác thực **ai đang mở connection**.
- Backend route xác định **người đó có được đọc phòng/gửi message/thao tác dữ liệu hiện tại hay không**.
- Một connection có thể tồn tại lâu; token/JWT có thể hết hạn hoặc bị thu hồi **sau khi handshake thành công**. Nếu cần enforce revocation ngay, thiết kế revalidation theo chu kỳ, TTL phiên, hoặc gọi `deleteConnection` khi tài khoản bị khóa.

### 7.2. Browser WebSocket không tùy ý thêm Authorization header

Trong JavaScript browser chuẩn, `new WebSocket(url)` **không có API để thêm tùy ý header `Authorization`** như `fetch()`. Vì vậy, các lựa chọn thiết kế handshake thường liên quan:

- **Session cookie** có cấu hình bảo mật thích hợp nếu kiến trúc domain/cross-site và authorizer hỗ trợ.
- **Short-lived one-time connection ticket** do backend cấp trước, kiểm tra ở `$connect`; nếu đặt trong query string phải tránh leak qua logs, analytics, proxy và referrer.
- **WebSocket subprotocol** trong trường hợp ứng dụng hỗ trợ và được thiết kế review về bảo mật, không tự dùng nó làm kênh giấu token.
- Client native/server-to-server có thể dùng cơ chế ký request và header khi thư viện hỗ trợ, nhưng phải tương thích với API Gateway authorizer.

Không gửi **access key/secret key AWS**, mật khẩu dài hạn hoặc bearer token bền vững trong URL. Không chỉ vì trang web dùng `wss://` mà coi mọi query param an toàn trước logging.

### 7.3. IAM gọi Management API

Ví dụ identity policy giới hạn role của Lambda chỉ **POST** callback vào connections của một API/stage:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PostToSpecificWebSocketConnections",
      "Effect": "Allow",
      "Action": "execute-api:ManageConnections",
      "Resource": "arn:aws:execute-api:ap-southeast-1:123456789012:a1b2c3d4/prod/POST/@connections/*"
    }
  ]
}
~~~

Đây là **policy minh họa**, không phải role đầy đủ: còn cần `dynamodb:GetItem`, `dynamodb:Query`, `dynamodb:PutItem`, `dynamodb:DeleteItem` và `logs:CreateLogStream`/`logs:PutLogEvents` theo chức năng thực. Nếu ứng dụng dùng `getConnection` hoặc `deleteConnection`, cần cấp action/resource path phù hợp với method `GET`/`DELETE`. Các resource ARNs của `execute-api` khác với ARN DynamoDB hoặc Lambda.

**Không dùng `execute-api:Invoke` thay cho `execute-api:ManageConnections`**; một quyền là truy cập/invoke API routes khi có chính sách tương ứng, quyền kia điều khiển callback API đối với connections.

## 8. Lưu trạng thái kết nối trong DynamoDB

### 8.1. Vì sao cần registry?

API Gateway biết các **connection IDs**, nhưng không tự biết ID nào thuộc user nào, đang ở chat room nào, subscribe order nào hoặc client đã xử lý tới message nào. Những thông tin đó là **application state**, thường đặt trong DynamoDB vì có độ trễ thấp, không cần server giữ RAM sống và có thể mở rộng theo nhu cầu.

Một thiết kế đơn giản có **hai bảng**:

| Bảng | Partition key | Sort key | Thuộc tính |
| --- | --- | --- | --- |
| `Connections` | `connectionId` (String) | Không cần | `userId`, `connectedAt`, `expiresAt` (TTL), thông tin session hạn chế |
| `RoomMembers` | `roomId` (String) | `connectionId` (String) | `userId`, `joinedAt` và metadata subscription |

Ví dụ dữ liệu:

~~~json
{
  "Connections": {
    "connectionId": "ABC123=",
    "userId": "user-42",
    "connectedAt": 1795140000,
    "expiresAt": 1795150800
  },
  "RoomMembers": {
    "roomId": "lobby",
    "connectionId": "ABC123=",
    "userId": "user-42",
    "joinedAt": 1795140015
  }
}
~~~

Hai JSON trên minh họa **Item attributes**, không phải lệnh tạo bảng. Một user có thể mở **nhiều tabs/devices**, nên **userId không thay thế connectionId**. Nếu một người có ba connections, muốn gửi notification tới mọi thiết bị cần có cách tìm ba IDs, ví dụ một GSI theo user hoặc bảng mapping riêng.

### 8.2. Join/leave phòng và truy vấn fan-out

1. Sau `$connect`, lưu `connectionId + userId` đã xác thực.
2. Với `join`, backend kiểm tra user có quyền vào `roomId`, rồi ghi `RoomMembers(roomId, connectionId)`.
3. Với `sendMessage`, backend kiểm tra người gửi là member, **Query** theo `roomId` và gửi tới những connection IDs tương ứng.
4. Với `leave`, xóa membership cụ thể.
5. Với `$disconnect`, xóa trạng thái connection và mọi memberships theo schema/index đã thiết kế.

Với bảng `RoomMembers` ở ví dụ, muốn tìm **tất cả rooms của một connection** khi disconnect có thể phải bổ sung **GSI theo connectionId** hoặc một bảng mapping chiều ngược. Nếu chỉ có một phòng mặc định `lobby`, dọn một Item là đủ; không suy rộng workflow đó cho hệ thống nhiều phòng.

### 8.3. DynamoDB TTL không dọn tức thì

`expiresAt` có thể dùng làm **DynamoDB TTL attribute** ở dạng epoch seconds. DynamoDB TTL xóa các Item hết hạn **bất đồng bộ**, thường không xảy ra chính xác tại giây hết hạn. Vì vậy:

- Trạng thái “online” không nên phụ thuộc duy nhất vào việc Item còn hay mất.
- Khi query membership, có thể lọc `expiresAt` ở ứng dụng nếu schema có trường và bạn cần loại item đã hết hạn.
- `$disconnect`, `GoneException` và background sweeper vẫn hữu ích.
- Dọn bảng `Connections` bằng TTL **không tự động dọn Item ở bảng `RoomMembers`**; cần orchestration/stream/sweeper khác.

### 8.4. Race conditions và trạng thái vừa kết nối

Một Lambda xử lý `join` có thể chạy ngay sau handshake khi bản ghi connection vừa được ghi. Với DynamoDB, dùng **GetItem với `ConsistentRead: true`** khi cần đọc trạng thái ngay sau khi ghi ở **base table**; GSI không cung cấp strong-consistent reads. Tương tự, một thành viên có thể rời phòng ngay sau khi Query; callback sẽ nhận `410 Gone` hoặc message tới connection không còn member nếu thiếu kiểm tra khi gửi.

Muốn hệ thống có ràng buộc mạnh về quyền và thứ tự, cần thiết kế state machine, điều kiện ghi và version/epoch cho membership. Không coi “Query rồi POST” là một transaction atomic giữa DynamoDB và WebSocket callback.

## 9. Thiết kế protocol có thể retry và kiểm toán

### 9.1. Format message rõ ràng

Client gửi:

~~~json
{
  "action": "sendMessage",
  "requestId": "req-0199",
  "roomId": "lobby",
  "payload": {
    "text": "Đã xác nhận đơn hàng!"
  }
}
~~~

Server push:

~~~json
{
  "type": "message.created",
  "eventId": "evt-918273",
  "roomId": "lobby",
  "serverSequence": 27,
  "payload": {
    "senderId": "user-42",
    "text": "Đã xác nhận đơn hàng!"
  }
}
~~~

Những trường `requestId`, `eventId` và `serverSequence` là **mẫu ứng dụng tự thiết kế**, không phải API Gateway tự phát sinh. Server phải bảo đảm việc cấp sequence/ID theo datastore nếu nghiệp vụ yêu cầu, không suy rằng mỗi Lambda invocation toàn cục có thứ tự cố định.

### 9.2. Idempotency và acknowledgements

Để tránh việc người gửi retry làm gửi hai tin:

- Yêu cầu client cấp **requestId** duy nhất và lưu trạng thái xử lý bằng conditional write, TTL/idempotency window phù hợp.
- Đối với message quan trọng, lưu vào DynamoDB hoặc datastore **trước khi** fan-out.
- Server phản hồi event chứa **eventId**; client có thể gửi `ack` sau khi xử lý.
- Khi reconnect, client gửi `lastSeenSequence` hoặc cursor; backend đọc dữ liệu tồn lưu và replay phần thiếu theo chính sách.
- Nếu client đã nhận payload rồi mất mạng trước khi gửi ack, server có thể gửi lại; client cần **deduplicate** theo eventId.

**WebSocket transmission không tự bảo đảm exactly-once delivery ở tầng nghiệp vụ.** Thông thường xây dựng at-least-once delivery với deduplication, hoặc dùng at-most-once cho typing indicators/telemetry ít quan trọng.

### 9.3. Không giữ dữ liệu lớn trong frame

API Gateway WebSocket API có các hạn mức thông dụng như **32 KiB mỗi frame** và **128 KiB tối đa cho message** (cần xác nhận quota hiện hành). Với báo cáo/tệp lớn, thay vì nhét file vào WebSocket:

1. Ghi đối tượng lên S3 theo quyền ứng dụng.
2. Gửi message nhỏ chứa `objectId` hoặc URL tải được ủy quyền có thời hạn.
3. Client lấy file qua HTTPS, có xác thực, kiểm soát expiry và checksum.

Không gửi presigned URL chứa thông tin nhạy cảm vào room mà không kiểm tra quyền của từng recipient.

## 10. Ví dụ Lambda Node.js: kết nối, tham gia phòng và gửi message

Ví dụ bên dưới minh họa một **phòng `lobby` duy nhất**, sử dụng **hai bảng DynamoDB** ở mục 8. Mục tiêu là hiểu luồng message, **không phải** một chat server production cho hàng nghìn kết nối. Ví dụ giả định:

- API Gateway WebSocket API có `$connect` gắn **Lambda REQUEST authorizer** hợp lệ trả `principalId`; nếu không có authorizer, đoạn xử lý sẽ từ chối handshake.
- Các routes `$connect`, `$disconnect`, `$default`, `join`, `sendMessage` được tạo và trỏ tới Lambda integration phù hợp.
- Lambda có environment variables `CONNECTIONS_TABLE`, `ROOM_MEMBERS_TABLE` và `CALLBACK_ENDPOINT`.
- `CALLBACK_ENDPOINT` là **HTTPS Management API endpoint chính xác của stage**, ví dụ `https://a1b2c3d4.execute-api.ap-southeast-1.amazonaws.com/prod`, không phải `wss://...`.
- IAM execution role có DynamoDB permissions cho đúng bảng/keys và `execute-api:ManageConnections` POST trên API/stage phù hợp.
- Lambda deployment package có các dependencies AWS SDK v3 tương ứng; không coi runtime luôn có sẵn mọi package phiên bản.
- DynamoDB `Connections`: partition key `connectionId` (String). `RoomMembers`: partition key `roomId`, sort key `connectionId` (String). Nếu bật DynamoDB TTL, attribute name dùng `expiresAt` ở **cả hai bảng**.

### 10.1. Lambda handler minh họa

~~~javascript
// Node.js 20+ minh họa; chỉ xử lý một phòng "lobby".
// Cài dependencies: @aws-sdk/client-dynamodb,
// @aws-sdk/lib-dynamodb, @aws-sdk/client-apigatewaymanagementapi.
const { DynamoDBClient } = require("@aws-sdk/client-dynamodb");
const {
  DynamoDBDocumentClient,
  PutCommand, GetCommand, DeleteCommand, QueryCommand
} = require("@aws-sdk/lib-dynamodb");
const {
  ApiGatewayManagementApiClient,
  PostToConnectionCommand
} = require("@aws-sdk/client-apigatewaymanagementapi");

const db = DynamoDBDocumentClient.from(new DynamoDBClient({}));
const management = new ApiGatewayManagementApiClient({
  endpoint: process.env.CALLBACK_ENDPOINT
});
const CONNECTIONS = process.env.CONNECTIONS_TABLE;
const MEMBERS = process.env.ROOM_MEMBERS_TABLE;
const ROOM = "lobby";

const ok = () => ({ statusCode: 200 });
const now = () => Math.floor(Date.now() / 1000);

async function removeConnection(connectionId) {
  // Chỉ hợp lệ vì ví dụ có đúng một phòng "lobby".
  await db.send(new DeleteCommand({
    TableName: MEMBERS, Key: { roomId: ROOM, connectionId }
  }));
  await db.send(new DeleteCommand({
    TableName: CONNECTIONS, Key: { connectionId }
  }));
}

async function push(connectionId, message) {
  try {
    await management.send(new PostToConnectionCommand({
      ConnectionId: connectionId,
      Data: Buffer.from(JSON.stringify(message), "utf8")
    }));
    return true;
  } catch (error) {
    if (error.name === "GoneException"
        || error.$metadata?.httpStatusCode === 410) {
      await removeConnection(connectionId);
      return false;
    }
    // 403/429/5xx không phải "gone": cần quan sát/retry theo chính sách.
    throw error;
  }
}

exports.handler = async (event) => {
  const routeKey = event.requestContext?.routeKey;
  const connectionId = event.requestContext?.connectionId;
  if (!connectionId) return { statusCode: 400 };

  if (routeKey === "$connect") {
    // principalId phải đến từ authorizer đáng tin, KHÔNG lấy từ body/query.
    const userId = event.requestContext?.authorizer?.principalId;
    if (!userId) return { statusCode: 401 };

    await db.send(new PutCommand({
      TableName: CONNECTIONS,
      Item: {
        connectionId,
        userId,
        connectedAt: now(),
        expiresAt: now() + 3 * 3600
      },
      ConditionExpression: "attribute_not_exists(connectionId)"
    }));
    return ok(); // Handshake chưa hoàn tất: không push ở đây.
  }

  if (routeKey === "$disconnect") {
    await removeConnection(connectionId);
    return ok(); // Disconnect là best effort; cleanup bổ sung vẫn cần.
  }

  // Đọc ngay sau $connect trên base table; không tin userId từ client.
  const state = await db.send(new GetCommand({
    TableName: CONNECTIONS,
    Key: { connectionId },
    ConsistentRead: true
  }));
  if (!state.Item || state.Item.expiresAt <= now()) {
    await push(connectionId, { type: "error", code: "SESSION_EXPIRED" });
    return ok();
  }

  let body;
  try {
    body = JSON.parse(event.body || "{}");
  } catch {
    await push(connectionId, { type: "error", code: "INVALID_JSON" });
    return ok();
  }

  if (routeKey === "join") {
    // Demo chỉ cho lobby. Production: kiểm tra ACL room hiện tại.
    if (body.roomId !== ROOM) {
      await push(connectionId, { type: "error", code: "ROOM_DENIED" });
      return ok();
    }
    await db.send(new PutCommand({
      TableName: MEMBERS,
      Item: {
        roomId: ROOM,
        connectionId,
        userId: state.Item.userId,
        joinedAt: now(),
        expiresAt: state.Item.expiresAt
      }
    }));
    await push(connectionId, { type: "joined", roomId: ROOM });
    return ok();
  }

  if (routeKey === "sendMessage") {
    const text = body.text;
    if (body.roomId !== ROOM
        || typeof text !== "string"
        || text.length < 1 || text.length > 500) {
      await push(connectionId, { type: "error", code: "INVALID_MESSAGE" });
      return ok();
    }

    const membership = await db.send(new GetCommand({
      TableName: MEMBERS,
      Key: { roomId: ROOM, connectionId },
      ConsistentRead: true
    }));
    if (!membership.Item || membership.Item.expiresAt <= now()) {
      await push(connectionId, { type: "error", code: "NOT_A_MEMBER" });
      return ok();
    }

    const outgoing = {
      type: "message.created",
      roomId: ROOM,
      senderId: state.Item.userId,
      text
    };
    let cursor;
    do {
      const page = await db.send(new QueryCommand({
        TableName: MEMBERS,
        KeyConditionExpression: "roomId = :room",
        ExpressionAttributeValues: { ":room": ROOM },
        ExclusiveStartKey: cursor
      }));

      // Chỉ dành cho phòng lab ít thành viên.
      // Production: tách fan-out qua SQS/worker, giới hạn concurrency.
      for (const member of page.Items || []) {
        if (member.expiresAt > now()) {
          await push(member.connectionId, outgoing);
        }
      }
      cursor = page.LastEvaluatedKey;
    } while (cursor);

    return ok();
  }

  await push(connectionId, {
    type: "error", code: "UNKNOWN_ACTION", routeKey
  });
  return ok();
};
~~~

### 10.2. Đọc ví dụ đúng cách

| Dòng xử lý | Điều muốn minh họa |
| --- | --- |
| `$connect` lấy `authorizer.principalId` | Không tin `userId` do client tự gửi |
| `PutCommand Connections` | Ghi session theo connection ID, có expiry cho cleanup |
| `join` kiểm tra phòng và lưu `RoomMembers` | Registry dùng để quyết định ai nhận message |
| `sendMessage` đọc membership trước khi publish | Gửi message phải được authorize, không chỉ validate JSON |
| `QueryCommand` phân trang theo `roomId` | Một phòng có thể chứa nhiều hơn một trang DynamoDB |
| `PostToConnectionCommand` | Đẩy message tới một connection cụ thể bằng Management API |
| `GoneException` | Dọn connection stale khi đã đóng |
| `$disconnect` | Dọn best effort, không coi là callback chắc chắn đến |

**Những giới hạn cố ý của ví dụ:**

1. Chỉ có **một room `lobby`**; production nhiều phòng cần GSI hoặc bảng membership chiều ngược để dọn mọi room khi disconnect.
2. Fan-out thực hiện **tuần tự trong Lambda route integration**, nên phòng đông có thể vượt timeout và chi phí tăng. Production nên ghi event vào SQS/stream và dùng worker xử lý theo shard/batch có throttling/backoff.
3. `sendMessage` trong ví dụ **chưa persist nội dung tin**, chưa sinh eventId, chưa deduplicate requestId và chưa có offline inbox. Không dùng nó cho thông báo giao dịch cần giao đáng tin.
4. Gọi `push` rồi nhận 200 **không chứng minh client đã xử lý message**.
5. Ví dụ chỉ giới hạn text bằng `length` JavaScript (số đơn vị mã UTF-16), **chưa kiểm tra kích thước UTF-8 bytes**, schema, rate limit và nội dung có hại ở chuẩn production.
6. `removeConnection` dọn hai bản ghi trên hai bảng **không phải transaction**. Nếu một thao tác lỗi, sweeper/TTL phải sửa trạng thái còn sót.
7. Quyền riêng tư/tenancy phải được bổ sung nếu lobby không phải phòng công cộng; ACL phải dựa trên identity server-side và datastore được tin cậy.

### 10.3. Tách fan-out ra khỏi route integration

Khi nhóm có hàng nghìn subscribers, API route không nên cố gửi toàn bộ message đồng bộ:

~~~mermaid
flowchart LR
    SEND["Client gửi sendMessage"] --> GW["API Gateway WebSocket"]
    GW --> HANDLER["Lambda Validate + Persist"]
    HANDLER --> DB["DynamoDB: Messages/Idempotency"]
    HANDLER --> QUEUE["SQS / EventBridge / stream"]
    QUEUE --> WORKER["Fan-out workers\nbounded concurrency"]
    WORKER --> REG["DynamoDB: memberships"]
    WORKER --> MGMT["Management API @connections"]
    MGMT --> CLIENTS["Clients đang kết nối"]
    WORKER --> DLQ["DLQ / failed delivery tracking"]
~~~

Ở mô hình này, route integration có thể nhanh chóng xác nhận **đã chấp nhận yêu cầu** theo protocol ứng dụng (ví dụ callback `accepted`) sau khi persist/queue thành công. Người nhận có thể đến chậm hơn; quan sát **queue age, số worker failures và tốc độ fan-out** để đánh giá realtime SLO.

## 11. JavaScript client: gửi action và xử lý reconnect

Ví dụ browser:

~~~javascript
// Giả sử $connect handshake đã có cơ chế auth hợp lệ.
// Không nhúng token dài hạn vào URL trong ví dụ.
const url = "wss://a1b2c3d4.execute-api.ap-southeast-1.amazonaws.com/prod";
let socket;
let retry = 0;
let reconnectTimer;

function openSocket() {
  socket = new WebSocket(url);

  socket.addEventListener("open", () => {
    retry = 0;
    socket.send(JSON.stringify({
      action: "join",
      roomId: "lobby"
    }));
  });

  socket.addEventListener("message", (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === "message.created") {
        console.log("Tin nhắn:", data.senderId, data.text);
      } else {
        console.log("Server:", data);
      }
    } catch {
      console.warn("Không đọc được server message");
    }
  });

  socket.addEventListener("close", () => {
    // Exponential backoff + jitter, giới hạn 30 giây.
    const base = Math.min(30000, 1000 * Math.pow(2, retry++));
    const jitter = Math.random() * 1000;
    reconnectTimer = setTimeout(openSocket, base + jitter);
  });

  socket.addEventListener("error", () => {
    // Browser không cung cấp mọi nguyên nhân lỗi handshake chi tiết.
    console.warn("WebSocket gặp lỗi, chờ close/reconnect");
  });
}

function sendText(text) {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    throw new Error("Chưa kết nối; cần queue/retry tầng ứng dụng");
  }
  socket.send(JSON.stringify({
    action: "sendMessage",
    roomId: "lobby",
    requestId: crypto.randomUUID(),
    text
  }));
}

openSocket();
~~~

**Không copy nguyên mã vào production:** sample chưa xử lý refresh auth ticket/cookie, page unload, offline status, duplicate messages, kiểm soát retry khi API bị tắt vĩnh viễn hoặc **reconnect storm** sau sự cố khu vực. Cần dừng reconnect khi app logout, chờ network online và áp giới hạn tổng số lần/thời gian retry.

### 11.1. Vì sao reconnect tạo connection ID khác?

Một WebSocket connection mới là một phiên kết nối mới trong API Gateway, có **connection ID mới**. Do đó client cần:

1. Xác thực handshake lại.
2. Gửi `join`/`subscribe` lại sau sự kiện `open`.
3. Gửi cursor `lastSeenEventId` hoặc `lastSeenSequence` nếu ứng dụng hỗ trợ replay.
4. Xử lý kết quả trùng lặp khi một message được xử lý trước khi connection cũ đứt.

Không lưu connection ID làm định danh duy nhất của **user**. Dùng user ID ổn định từ hệ thống xác thực, còn connection ID là thông tin phiên mạng tạm thời.

### 11.2. Heartbeat và presence

Với nhiều client, bạn có thể tạo route `ping` nhận:

~~~json
{
  "action": "ping",
  "clientTime": "2026-11-20T03:00:00Z"
}
~~~

Backend cập nhật `lastSeenAt` hoặc gửi `pong`. Tuy nhiên:

- Một dấu `online` gần đây là **ước lượng**, không phải bảo đảm client vẫn nhận message.
- Không spam heartbeat mỗi giây; cân nhắc số connections, message billing và chi phí.
- Client có thể bị background throttling ở browser/mobile, ngủ máy hoặc mất sóng.
- `$disconnect` có thể đến chậm hoặc không đến; kết hợp TTL, heartbeat và GoneException.

## 12. Cấu hình WebSocket API theo CloudFormation

Đoạn dưới chỉ là **fragment giải thích** cấu trúc API Gateway WebSocket và routing, **không phải stack triển khai hoàn chỉnh**. Các Lambda/authorizer IAM role, authorizer resource, invoke permission, logging, stage, custom-domain mapping và DynamoDB cần được khai báo đầy đủ ở một template thực tế.

~~~yaml
Resources:
  ChatWebSocketApi:
    Type: AWS::ApiGatewayV2::Api
    Properties:
      Name: chat-ws-example
      ProtocolType: WEBSOCKET
      RouteSelectionExpression: "$request.body.action"

  ChatIntegration:
    Type: AWS::ApiGatewayV2::Integration
    Properties:
      ApiId: !Ref ChatWebSocketApi
      IntegrationType: AWS_PROXY
      IntegrationUri: "LAMBDA_INVOKE_ARN_PLACEHOLDER"

  ConnectRoute:
    Type: AWS::ApiGatewayV2::Route
    Properties:
      ApiId: !Ref ChatWebSocketApi
      RouteKey: "$connect"
      AuthorizationType: CUSTOM
      AuthorizerId: "AUTHORIZER_ID_PLACEHOLDER"
      Target: !Join ["", ["integrations/", !Ref ChatIntegration]]

  DisconnectRoute:
    Type: AWS::ApiGatewayV2::Route
    Properties:
      ApiId: !Ref ChatWebSocketApi
      RouteKey: "$disconnect"
      Target: !Join ["", ["integrations/", !Ref ChatIntegration]]

  JoinRoute:
    Type: AWS::ApiGatewayV2::Route
    Properties:
      ApiId: !Ref ChatWebSocketApi
      RouteKey: "join"
      Target: !Join ["", ["integrations/", !Ref ChatIntegration]]

  MessageRoute:
    Type: AWS::ApiGatewayV2::Route
    Properties:
      ApiId: !Ref ChatWebSocketApi
      RouteKey: "sendMessage"
      Target: !Join ["", ["integrations/", !Ref ChatIntegration]]

  DefaultRoute:
    Type: AWS::ApiGatewayV2::Route
    Properties:
      ApiId: !Ref ChatWebSocketApi
      RouteKey: "$default"
      Target: !Join ["", ["integrations/", !Ref ChatIntegration]]

  ProdStage:
    Type: AWS::ApiGatewayV2::Stage
    Properties:
      ApiId: !Ref ChatWebSocketApi
      StageName: prod
      AutoDeploy: true
~~~

**Để hoàn thiện thành stack thực:**

- Thay `LAMBDA_INVOKE_ARN_PLACEHOLDER` bằng AWS_PROXY Lambda integration URI đúng dạng API Gateway Lambda path và Region/account/function tương ứng.
- Tạo `AWS::ApiGatewayV2::Authorizer` cho WebSocket API và tham chiếu `AuthorizerId` thật trên `$connect`; cấu hình identity sources/trust và Lambda authorizer invoke permission.
- Cấp `AWS::Lambda::Permission` để API Gateway được invoke route Lambda với source ARN giới hạn.
- Tạo Lambda execution role có DynamoDB, CloudWatch Logs và `execute-api:ManageConnections` theo stage/API ID được tạo.
- Tạo DynamoDB tables và TTL settings, log groups, stage logging và CloudWatch alarms.
- Với `AutoDeploy: true`, thay đổi routes/integrations có thể được phát hành tự động lên stage; production cần quy trình review/canary/rollback hợp lý.
- Cấu hình custom domain, Route 53 và certificates nếu sử dụng; endpoint callback phải phản ánh API mapping thực tế.

**Không áp dụng nguyên đoạn fragment** và hy vọng deploy thành công: placeholders chưa được thay, không có Lambda/authorizer thực và thiếu những quyền cần thiết. Đây là tài liệu để nhìn cấu trúc **API → Integration → Routes → Stage**.

## 13. Kiểm tra tài nguyên bằng AWS CLI (chỉ đọc)

Các lệnh sau không sửa tài nguyên. Người học cần quyền read-only trên API Gateway API IDs, stages, routes, authorizers và integrations trong Region đúng.

### 13.1. Liệt kê WebSocket APIs

~~~bash
aws apigatewayv2 get-apis \
  --region ap-southeast-1 \
  --query "Items[?ProtocolType=='WEBSOCKET'].{Name:Name,Id:ApiId,Selection:RouteSelectionExpression,Endpoint:ApiEndpoint}" \
  --output table
~~~

Đọc cột `RouteSelectionExpression` và đối chiếu message contract, không mặc định mọi API chọn `$request.body.action`.

### 13.2. Xem routes và integrations

~~~bash
aws apigatewayv2 get-routes \
  --region ap-southeast-1 \
  --api-id a1b2c3d4 \
  --query "Items[].{Key:RouteKey,Target:Target,Auth:AuthorizationType,Authorizer:AuthorizerId}" \
  --output table

aws apigatewayv2 get-integrations \
  --region ap-southeast-1 \
  --api-id a1b2c3d4 \
  --query "Items[].{Id:IntegrationId,Type:IntegrationType,Uri:IntegrationUri,Timeout:TimeoutInMillis}" \
  --output table
~~~

Khi thấy route `join` nhưng client gửi `{"action":"enterRoom"}`, route không khớp và có thể rơi vào `$default`. Kiểm tra `RouteKey`, route selection expression và integration target trước khi tìm lỗi DynamoDB.

### 13.3. Xem authorizers và stage

~~~bash
aws apigatewayv2 get-authorizers \
  --region ap-southeast-1 \
  --api-id a1b2c3d4 \
  --output json

aws apigatewayv2 get-stages \
  --region ap-southeast-1 \
  --api-id a1b2c3d4 \
  --query "Items[].{Name:StageName,AutoDeploy:AutoDeploy,AccessLog:AccessLogSettings}" \
  --output json
~~~

`get-authorizers` cho thấy cấu hình authorizer, nhưng không trả secret hay xác nhận token của client cụ thể hợp lệ. `get-stages` giúp xác nhận client thật sự kết nối tới stage mà mình đang kiểm tra.

### 13.4. Xem metadata connection đang tồn tại

~~~bash
aws apigatewaymanagementapi get-connection \
  --region ap-southeast-1 \
  --endpoint-url https://a1b2c3d4.execute-api.ap-southeast-1.amazonaws.com/prod \
  --connection-id "EXAMPLE_CONNECTION_ID"
~~~

Đây là lời gọi **GET read-only** tới Management API, cần quyền `execute-api:ManageConnections` cho phương thức tương ứng. Nếu trả **410 Gone**, connection không còn tồn tại (hoặc không sẵn sàng); nếu **403**, xem IAM/ARN và URL endpoint. Không chọn đại connection ID của user production mà không có quyền điều tra.

### 13.5. Kiểm tra DynamoDB schema, không đọc dữ liệu khách hàng

~~~bash
aws dynamodb describe-table \
  --region ap-southeast-1 \
  --table-name Connections

aws dynamodb describe-time-to-live \
  --region ap-southeast-1 \
  --table-name Connections

aws dynamodb describe-table \
  --region ap-southeast-1 \
  --table-name RoomMembers
~~~

Kiểm tra key schema và TTL attribute thật. Không mặc định bảng `RoomMembers` tự dọn mọi Item khi `Connections` hết hạn; hai bảng độc lập.

## 14. Quan sát: metrics, logs và tracing

Hệ thống realtime cần phân biệt **connection health**, **message delivery**, **backend correctness** và **chi phí**.

| Tầng | Nên đo | Gợi ý điều tra |
| --- | --- | --- |
| **API Gateway** | Connect attempts/count, message count, API errors, integration latency và throttling theo metric được hỗ trợ | Client có handshake/route được không? |
| **Lambda integrations** | Invocations, errors, duration, concurrency, throttles | Route handler có chạy và hoàn tất đúng không? |
| **DynamoDB** | RCU/WCU, throttled requests, Query latency, hot partition | Registry room lớn có nghẽn partition không? |
| **Management API** | Số POST thành công, 403/410/429/5xx, callback latency | Có lỗi IAM, stale connections hay throttling? |
| **SQS/worker** | Queue depth, oldest message age, DLQ, delivery retries | Fan-out có theo kịp tốc độ publish không? |
| **Client** | Reconnects, time-to-first-message, lastSeen sequence, app ack latency | Người dùng có thật sự nhận sự kiện? |
| **Chi phí** | Connection minutes, message counts/sizes, Lambda/DynamoDB/Logs/network | Realtime traffic có vượt ngân sách? |

**Log theo `connectionId`, `userId` dạng được bảo vệ, `requestId` và `eventId`** giúp nối các bước gửi/nhận. Tuy nhiên, không đưa token, mật khẩu, toàn bộ query URL chứa credentials hay nội dung tin nhắn nhạy cảm vào log ngoài chính sách bảo mật.

### 14.1. Access logs và execution logs

API Gateway WebSocket API hỗ trợ logging/metrics theo khả năng của stage và cấu hình account. Cần:

- Cho API Gateway quyền ghi CloudWatch Logs theo quy trình chính thức.
- Cấu hình **access log format** chứa request ID, routeKey, connectionId, status và integration status khi được hỗ trợ.
- Bật execution logging có chủ đích và **không log payload chứa dữ liệu nhạy cảm** nếu không được phép.
- Đặt retention và quyền đọc logs, lọc bớt noise từ ping/typing.

Không suy rằng một 200 ở log `$connect` là bằng chứng client sẽ còn online sau một giờ; connection có vòng đời và giới hạn riêng.

### 14.2. Xây dựng SLO thực tế

Ví dụ SLO ứng dụng chat:

~~~text
99% message được server chấp nhận và lưu bền vững
trong 500 ms khi backend khỏe.

99% message thông báo tới các connection hiện còn hoạt động
trong 3 giây, không tính client offline hoặc mất Internet.

Mỗi event có eventId và client có thể replay các sự kiện
chưa ack sau reconnect theo cửa sổ retention.
~~~

Các con số chỉ là **mục tiêu giả định**. Cần xác định “gửi thành công” là Gateway chấp nhận POST, WebSocket client nhận bytes hay client **xác nhận đã xử lý**. Không thể đo đúng SLO nếu ba khái niệm này bị gộp làm một.

## 15. Chi phí, quota và capacity planning

### 15.1. Các nguồn chi phí chính

| Thành phần | Chi phí phải tính |
| --- | --- |
| **API Gateway WebSocket** | Số message gửi/nhận, kích thước message theo đơn vị tính phí và **connection minutes** |
| **Lambda** | Invocations, duration, memory/concurrency; route và worker fan-out |
| **DynamoDB** | Request capacity hoặc provisioned throughput, storage, indexes, streams, backup |
| **SQS/EventBridge** | Publish/consume events, retry, DLQ và dung lượng/requests theo mô hình |
| **CloudWatch** | Log ingest, storage, metrics, alarms |
| **Network/khác** | Data transfer out, KMS, VPC endpoints/NAT khi kiến trúc cần |

Giả sử **10.000 kết nối đang mở trung bình 30 phút/ngày**:

~~~text
Connection-minutes/ngày = 10.000 × 30 = 300.000
Connection-minutes/30 ngày = 9.000.000
~~~

Đây mới là đơn vị lưu lượng connection, **không phải tổng tiền**. Ngoài ra, cứ mỗi client gửi heartbeat/typing message, message count có thể tăng nhanh. Ví dụ 10.000 clients × 1 heartbeat/phút × 30 phút = **300.000 heartbeat messages/ngày**, chưa tính callback pong hoặc nghiệp vụ.

Đối với fan-out:

~~~text
Một room có 1.000 recipients đang kết nối.
Một sự kiện được push tới toàn bộ recipients.
→ Có thể phát sinh khoảng 1.000 outgoing messages
  (chưa tính retries, errors và các message phân mảnh).
~~~

Một sự kiện đầu vào không đồng nghĩa một message được tính phí. Nên có dashboard **fan-out multiplier** và quota bảo vệ khi một user gửi hàng trăm message/phút.

### 15.2. Các giới hạn kỹ thuật cần biết

Theo tài liệu API Gateway WebSocket quotas, những giới hạn phổ biến gồm:

- Connection idle timeout khoảng **10 phút**, maximum connection lifetime **2 giờ**.
- Message tối đa **128 KiB**, frame tối đa **32 KiB**.
- Giới hạn tạo connection mới/giây, callback throughput, route integration timeout và throttling theo account/Region; giá trị mặc định có thể thay đổi và một số quota có thể điều chỉnh.
- WebSocket API không dành cho tải binary streaming/tệp lớn như một server WebSocket tự quản lý.

**Không hardcode những giá trị quota vừa kể thành một SLA vĩnh viễn.** Đối với production, tra cứu quota hiện hành, Service Quotas nếu có, tải dự kiến, vùng AWS và cách API Gateway tính kích thước message. Thiết kế **chunking hoặc S3 transfer** cho payload lớn.

### 15.3. Reconnect storm và hot partition

Nếu 50.000 clients bị ngắt cùng lúc rồi reconnect:

1. Tăng vọt handshake `$connect`, authorizer và Lambda concurrency.
2. Dồn ghi DynamoDB vào registry.
3. Cùng lúc gọi `join` và query membership.
4. Đẩy token verification, database và downstream services vào tải bất thường.

Mitigation: exponential backoff **có jitter**, admission control/throttling, capacity planning DynamoDB, cache token hợp lệ khi an toàn, retry budgets và fallback UX. Đối với room rất đông, một partition key `roomId=lobby` có thể trở thành **hot partition**; cần cân nhắc **sharding membership** và fan-out theo worker partitions, không chỉ tăng Lambda memory.

## 16. Bảo mật dữ liệu và quyền của người nhận

### 16.1. Không chỉ dựa vào connection ID

Connection ID là địa chỉ để gọi callback, **không phải chứng nhận người đó được phép xem mọi message**. Trước khi push nội dung nhạy cảm:

- Xác định connection thuộc user nào từ trạng thái server-side đã được xác thực.
- Xác nhận user hiện có quyền xem resource/topic/room.
- Tránh lấy room ID hoặc recipient IDs trực tiếp từ payload mà không kiểm tra.
- Khi user bị logout/thu hồi quyền, cân nhắc gỡ membership và đóng connections tương ứng.
- Tách môi trường/stage/account và IAM roles; role được `ManageConnections` trong một API không cần quyền điều khiển API khác.

### 16.2. Bảo vệ tenant và phòng chat

Trong hệ thống SaaS, không nên chỉ có partition key `roomId` nếu giá trị có thể trùng giữa hai tenants. Có thể dùng:

~~~text
PK = TENANT#tenant-17#ROOM#room-123
SK = CONN#connection-ABC
~~~

Và kiểm tra tenant ID từ **authorization context đáng tin**. Không lấy tenantId client gửi như một quyền truy cập tự hợp lệ. Đối với fan-out theo tenant, dùng condition key/policy dữ liệu và audit có khả năng truy nguyên.

### 16.3. Bảo vệ message payload

- Giới hạn kích thước, định dạng, ký tự và rate limit theo user/IP/connection.
- Không cho phép payload thao túng backend command, IAM action hoặc DynamoDB key không kiểm soát.
- Mã hóa dữ liệu lưu trữ và quản lý KMS key policies khi cần.
- Tránh broadcast dữ liệu bí mật qua room công cộng.
- Thiết kế retention/điều kiện xóa message và đáp ứng yêu cầu riêng tư.
- Cân nhắc replay attack, CSRF-like cross-site WebSocket hijacking nếu handshake dùng cookies: kiểm tra `Origin` và auth/session binding theo chính sách.

**WSS dùng TLS bảo vệ dữ liệu trên đường truyền client ↔ Gateway**, nhưng không thay thế IAM, authorization ở backend hoặc encryption-at-rest trong DynamoDB/S3.

## 17. Bảng sự cố thường gặp

| Hiện tượng | Nguyên nhân có thể | Kiểm tra ưu tiên |
| --- | --- | --- |
| **Browser không kết nối được WebSocket** | URL `wss://`/stage sai, TLS/custom domain, auth `$connect` từ chối | Browser console/network, stage, $connect authorizer logs |
| **Handshake trả 403** | IAM SigV4 không hợp lệ, Lambda authorizer Deny, resource policy | Authorizer, $connect integration và API permissions |
| **Client `open` được nhưng gửi action không có phản hồi** | Chưa có custom route, route selection expression sai; one-way route response | `get-routes`, `$default` logs, gọi `postToConnection` |
| **Backend return 200 nhưng client không thấy body** | Chưa cấu hình route response/integration response | Kiểm tra two-way route response hoặc gửi qua Management API |
| **postToConnection trả 403** | Lambda execution role thiếu `ManageConnections`, ARN sai, endpoint/stage sai | Policy, resource ARN, callback endpoint |
| **postToConnection trả 410** | Client đã đóng, ID cũ, handshake chưa hoàn tất | Cleanup connection; gửi lại sau reconnect nếu nghiệp vụ cần |
| **429 nhiều khi publish** | Fan-out không giới hạn, vượt message/callback throttles | SQS worker, concurrency caps, retry/backoff |
| **Connection đóng sau một thời gian rảnh** | Idle timeout hoặc mạng/client ngắt | Heartbeat phù hợp, reconnect, resume |
| **Connection cứ đóng sau vài giờ** | Maximum connection duration của Gateway | Reconnect dự kiến và resubscribe |
| **User reconnect không thấy tin** | Không có lưu trữ offline/replay hoặc chưa join lại | Message persistence, cursors, acks, subscriptions |
| **Room có nhiều connection IDs đã chết** | `$disconnect` best effort, TTL chậm, chưa dọn 410 | Sweeper/TTL, GoneException, cleanup membership |
| **Một message xuất hiện 2 lần** | Retry, Lambda async redelivery, client reconnect/replay | Idempotency theo requestId/eventId |
| **Hai user nhận message không cùng thứ tự** | Nhiều route/Lambda/workers xử lý cạnh tranh | Sequence/order per room trong datastore, client reorder |
| **DynamoDB throttling dù room chỉ có một key** | Hot partition theo roomId, fan-out query cùng PK | Sharding, worker partitions, capacity |
| **Lambda timeout trên sendMessage** | Sync fan-out quá nhiều connections, API/DB chậm | Persist/queue + async workers, bounded concurrency |
| **Cấp auth tại connect nhưng user bị khóa vẫn nhận** | Connection cũ còn sống, chưa revocation/revalidation | Gỡ membership, kiểm quyền tại publish, delete connection |

### 17.1. Chẩn đoán theo bốn bước

1. **Handshake:** tìm `$connect` event, authorizer result, HTTP upgrade thành công hay không.
2. **Route:** message body đúng JSON/action? `$default` có chạy? Integration được gọi?
3. **State:** registry có connectionId và membership hợp lệ không, TTL/authorization ra sao?
4. **Callback:** `postToConnection` đã được gọi ở endpoint/stage đúng, HTTP status là gì, client có ack không?

Đừng “sửa thử” bằng cách bỏ authorizer hoặc cấp `AdministratorAccess` cho Lambda. Đó thường là cách che lỗi IAM/stage và tạo lỗ hổng lớn hơn.

## 18. Kiểm thử trong môi trường lab

Mục tiêu lab: hai client được **xác thực** cùng vào `lobby`, gửi message, đóng một connection, quan sát cleanup và reconnect.

### 18.1. Chuẩn bị

1. Có API Gateway **WebSocket API** trong tài khoản lab, cấu hình route expression `$request.body.action`.
2. Tạo `$connect`, `$disconnect`, `$default`, `join`, `sendMessage`, authorizer `$connect` và Lambda integrations tương ứng.
3. Dựng DynamoDB `Connections` và `RoomMembers`; TTL (nếu bật) theo thuộc tính `expiresAt`.
4. Cấp IAM least privilege và cấu hình đúng `CALLBACK_ENDPOINT` của stage.
5. Bật CloudWatch Logs/metrics với retention phù hợp; không dùng credentials thật trong screenshot.
6. Chuẩn bị hai browsers hoặc hai client WebSocket được phép truy cập, với cơ chế handshake auth hợp lệ.

### 18.2. Các bước thực nghiệm

| Bước | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| 1 | Client A/B kết nối bằng `wss://.../lab` | Cả hai nhận WebSocket `open`; `$connect` ghi hai connection IDs |
| 2 | A/B gửi `{"action":"join","roomId":"lobby"}` | Hai memberships xuất hiện; cả hai nhận callback `joined` |
| 3 | A gửi `sendMessage` | A/B nhận message trên connections đang mở |
| 4 | Gửi `{"action":"unknown"}` | `$default` xử lý, push lỗi protocol thích hợp |
| 5 | B gọi `close()` | Có thể nhận `$disconnect`; backend dọn registry best effort |
| 6 | A gửi tiếp message sau B đóng | B không nhận; callback stale B nếu còn trong registry có thể trả 410 |
| 7 | B reconnect và join lại | B có connection ID mới; cần resubscribe |
| 8 | Kiểm tra CloudWatch/DynamoDB | Có logs và trạng thái kết nối/cleanup, không lưu token nhạy cảm |

Không dùng load test nặng hoặc chủ động đóng nhiều connections trên stage production. Lab tạo resources tính phí: phải dọn **WebSocket API, Lambda, DynamoDB, logs và các tài nguyên phụ trợ** theo chính sách, tránh xóa nhầm dữ liệu thật.

### 18.3. Kiểm thử thất bại có chủ đích

- Gửi invalid JSON để xem `$default` và thông điệp lỗi.
- Gửi `join` vào một phòng không được phép để chắc chắn server không đăng ký membership.
- Thử một callback bằng ID đã disconnect trong môi trường lab để kiểm tra dọn `410 Gone`.
- Giới hạn tốc độ gửi message ở client rồi quan sát connection throttling/application rate limiting.
- Giả lập mạng mất kết nối, đo backoff/reconnect, số message bị trùng/mất và thời gian resume.
- Thử dùng một token bị thu hồi để chắc chắn `$connect` từ chối và connection đang mở được xử lý theo chính sách revoke.

## 19. Bài toán kiến trúc: thông báo trạng thái đơn hàng

### 19.1. Yêu cầu

Ứng dụng thương mại điện tử có người mua đang theo dõi đơn hàng. Khi backend đổi `orderStatus` sang `SHIPPED`, client cần nhận event thời gian thực. Nếu client offline, trạng thái vẫn phải đọc lại được khi mở ứng dụng.

### 19.2. Kiến trúc đề xuất

~~~mermaid
flowchart LR
    ORDER["Order Service\nRDS/DynamoDB"] -->|"Ghi trạng thái + outbox/event"| BUS["EventBridge / SQS"]
    BUS --> WORK["Notification Worker Lambda"]
    WORK --> LOOK["Connection Registry\ntheo userId"]
    WORK -->|"POST @connections"| GW["API Gateway WebSocket"]
    GW --> CLIENT["Web/mobile client"]
    CLIENT -->|"GET trạng thái hiện hành"| API["HTTP API"]
    API --> ORDER
~~~

**Điểm cốt lõi:** **source of truth** là Order Service/database, không phải connection registry. Event realtime giúp UI cập nhật nhanh, nhưng khi reconnect, client vẫn đọc `GET /orders/{id}` hoặc API phù hợp để đồng bộ trạng thái mới nhất.

### 19.3. Quyền và cách gửi

1. `$connect` authorizer xác định user ID.
2. Registry ánh xạ user ID tới nhiều connection IDs (tabs/devices).
3. Worker nhận sự kiện order, xác định **chủ sở hữu được phép** xem order từ dữ liệu server-side.
4. Worker fan-out `order.updated` tới tất cả connections hợp lệ của user.
5. Client có thể ack eventId, sau đó query lại source-of-truth để tránh trạng thái UI sai.
6. Nếu 410 Gone hoặc client offline, backend **không làm mất dữ liệu đơn hàng**; event có thể được replay tùy mục tiêu, và client vẫn fetch trạng thái khi vào lại.

**Không gửi cả thông tin thanh toán/PII trong payload** nếu client chỉ cần ID và trạng thái. Giảm payload còn `orderId`/`status` và dùng API có auth để lấy chi tiết.

### 19.4. RTO, RPO và tính sẵn sàng

Nếu realtime channel bị lỗi nhưng HTTP API/database vẫn hoạt động, người dùng có thể **tạm không nhận push** nhưng vẫn xem trạng thái hiện hành qua polling. Đây là một **degraded mode** hữu ích. Việc chọn DynamoDB multi-Region, SQS replay, cross-Region failover hoặc backup phải dựa theo RTO/RPO của ứng dụng, không tự có chỉ vì WebSocket đang chạy.

## 20. Bài tập củng cố

### Bài tập 1 — route nào được gọi?

API dùng `$request.body.action`, có custom routes `join` và `sendMessage`, cộng `$default`.

~~~json
{"action":"join","roomId":"lobby"}
~~~

**Gợi ý:** gọi `join`. Nếu gửi `{"action":"deleteEverything"}` mà không có route đó, đi vào `$default`. Backend vẫn phải validate schema và authorization.

### Bài tập 2 — response trả về client

Một route Lambda trả `{statusCode:200,body:"done"}` nhưng browser không nhận message mới. Vì sao?

**Gợi ý:** WebSocket integration return không tự luôn thành push message. Kiểm tra route response/integration response cho two-way communication hoặc dùng `postToConnection`.

### Bài tập 3 — 410 Gone

Trong `$connect` Lambda, dev gọi `postToConnection` để gửi lời chào, nhận 410. Sau khi đổi sang gửi khi client gửi `join`, callback thành công. Giải thích.

**Gợi ý:** handshake chưa hoàn tất khi `$connect` integration chạy; connection có thể chưa sẵn sàng với Management API. Gửi khi connection đã `open` và client gửi message tiếp theo sẽ tránh race này.

### Bài tập 4 — dọn connection sau mất mạng

Client rút mạng đột ngột, `$disconnect` không gọi được. Sau một ngày `RoomMembers` vẫn còn connection ID cũ. Đề xuất thiết kế cleanup.

**Gợi ý:** `$disconnect` best effort, TTL theo bảng, sweeper và cleanup khi callback trả 410. TTL DynamoDB bất đồng bộ và không tự xóa bảng membership khác.

### Bài tập 5 — bảo mật phòng chat

Client chưa được cấp quyền vào `room-private-1` nhưng gửi `{"action":"join","roomId":"room-private-1"}`. Vì API Gateway route `join` đã tồn tại, server có được phép ghi membership không?

**Gợi ý:** không. Route selection chỉ chọn backend; backend phải kiểm tra ACL theo userId đã xác thực, roomId và tenant trước khi ghi.

### Bài tập 6 — tính message count

Một phòng có 100 người đang online. Mỗi người gửi hai message/phút, backend broadcast tới tất cả members. Trong một phút, có khoảng bao nhiêu incoming và outgoing messages, bỏ qua retries?

**Gợi ý:** incoming = `100 × 2 = 200`. Nếu mỗi message broadcast tới cả 100 members, outgoing khoảng `200 × 100 = 20.000`. Đây là bài toán **fan-out** và chi phí, không phải 200 outgoing.

### Bài tập 7 — token hết hạn khi socket còn sống

Một JWT có hạn 15 phút; connection có thể sống lâu hơn. Sau 20 phút, user bị revoke quyền xem room. Tại sao chỉ xác thực tại `$connect` không đủ?

**Gợi ý:** connection tiếp tục tồn tại sau handshake; cần kiểm quyền tại các hành động/room, revalidate auth/session hoặc chủ động đóng/gỡ membership khi revoke.

### Bài tập 8 — chọn AppSync hay API Gateway WebSocket

Đội A xây app GraphQL với subscriptions theo dữ liệu. Đội B có protocol JSON messages `join`, `typing`, `sendMessage` và workers tự push từ SQS. Mỗi đội nên cân nhắc công nghệ nào?

**Gợi ý:** đội A đánh giá **AppSync** theo abstraction GraphQL/realtime phù hợp; đội B đánh giá **API Gateway WebSocket** để tự kiểm soát route, registry, callback và fan-out. Vẫn so sánh chi phí, auth, quota và vận hành.

### Bài tập 9 — bảo đảm không mất notification

Order Service phát event `SHIPPED`, nhưng mọi WebSocket connections của user đều offline. Làm sao bảo đảm trạng thái đơn vẫn đúng khi user mở lại app?

**Gợi ý:** lưu state trong database và có API fetch theo quyền. WebSocket là kênh **thông báo nhanh**; nếu cần delivery guarantee còn phải lưu event/inbox, quản lý cursor và ack/replay.

## 21. Checklist triển khai production

- [ ] API Gateway có đúng `ProtocolType=WEBSOCKET`, route expression và stage.
- [ ] Đã định nghĩa `$connect`, `$disconnect`, `$default` và custom routes cần thiết.
- [ ] Có `$connect` authentication hợp lệ, giới hạn token exposure và chính sách revoke/revalidate.
- [ ] Backend kiểm tra quyền theo user/tenant/resource cho **từng action**, không chỉ handshake.
- [ ] Lambda role có DynamoDB và `execute-api:ManageConnections` đúng API/stage/method, không wildcard quá rộng.
- [ ] Callback HTTPS endpoint đúng stage hoặc custom domain API mapping.
- [ ] Registry/room schema đáp ứng user nhiều devices và nhiều rooms, có cleanup khi disconnect/410 và TTL/sweeper.
- [ ] Tin quan trọng được persist, có eventId/idempotency, client acknowledgement và resume strategy.
- [ ] Fan-out có queue, bounded concurrency, retry/backoff, DLQ và observability, không đồng bộ khối lượng lớn trong route Lambda.
- [ ] Message size, frame limits, timeout, heartbeat/reconnect và browser auth constraints đã kiểm thử.
- [ ] API Gateway/Lambda/DynamoDB/worker metrics, access logs, CloudWatch alarms và chi phí được theo dõi.
- [ ] Payload/logs được bảo vệ; WSS, encryption-at-rest và tenant-level authorization được thiết kế.
- [ ] Có kiểm thử 410 Gone, 403, throttling, invalid action, mất mạng, reconnect storm và cold start.
- [ ] Có kế hoạch dọn tài nguyên lab, môi trường staging/production tách biệt và quy trình rollback.

## 22. Ghi nhớ

**API Gateway WebSocket API** cung cấp một endpoint hai chiều được quản lý nhưng **không tự trở thành chat server đầy đủ**. Bạn phải hiểu:

1. **`$connect`** xác thực và ghi connection state trước khi handshake hoàn tất; **`$disconnect`** là sự kiện dọn dẹp *best effort*.
2. **Route selection expression** như `$request.body.action` giúp định tuyến message tới `join`, `sendMessage` hoặc `$default`.
3. Backend push tới client bằng **Management API `@connections`**, cần **`execute-api:ManageConnections`**; status code từ Lambda không mặc nhiên là WebSocket response.
4. **Connection registry, room membership, auth, offline state và delivery semantics** là trách nhiệm ứng dụng; nên dùng DynamoDB và event queue theo nhu cầu.
5. **410 Gone, reconnect, TTL, heartbeat, throttling, message limits và chi phí fan-out** là tình huống bình thường cần thiết kế từ đầu.

Kênh realtime tốt không chỉ có độ trễ thấp, mà còn phải **không làm sai dữ liệu nghiệp vụ khi client offline, retry hoặc mất kết nối**. Thiết kế phù hợp là tách **source of truth**, **event distribution** và **WebSocket delivery**, rồi đo từng lớp theo SLO và ngân sách.

### Tài liệu AWS chính thức

- [API Gateway WebSocket API overview](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-websocket-api-overview.html) — kiến trúc, routing và WebSocket connections.
- [WebSocket route keys: connect, disconnect, default](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-websocket-api-route-keys-connect-disconnect.html) — vòng đời connection và các special routes.
- [WebSocket route selection expressions](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-websocket-api-route-selection-expressions.html) — route theo `$request.body.action`.
- [WebSocket route responses](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-websocket-api-route-response.html) — one-way/two-way integration responses.
- [Use the @connections commands in your backend service](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-how-to-call-websocket-api-connections.html) — Post/Get/Delete connections, callback URL, IAM.
- [Control access to WebSocket APIs](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-websocket-api-control-access.html) — IAM và Lambda authorizer ở `$connect`.
- [API Gateway quotas](https://docs.aws.amazon.com/apigateway/latest/developerguide/limits.html) — message/frame, connection duration, throughput và timeout.
- [Logging and monitoring in API Gateway](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-websocket-api-logging.html) — access/execution logs.
- [DynamoDB Time to Live](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/TTL.html) — TTL và dọn Item bất đồng bộ.
- [AWS API Gateway pricing](https://aws.amazon.com/api-gateway/pricing/) — WebSocket connections/messages và đơn vị tính phí.
- [AWS AppSync Developer Guide](https://docs.aws.amazon.com/appsync/latest/devguide/what-is-appsync.html) — phương án GraphQL và realtime khác.
