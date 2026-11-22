# Chọn REST cho browser và hệ sinh thái HTTP rộng

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Nhận diện khi REST/HTTP là lựa chọn phù hợp cho browser, mobile app và đối tác bên ngoài.
- Giải thích lợi thế của HTTP semantics, JSON, URL và tooling phổ biến.
- Phân biệt REST API với gRPC native và gRPC-Web trong môi trường browser.
- Thiết kế endpoint, method, status code, pagination và cache theo ngữ nghĩa HTTP.
- Tích hợp REST edge với Spring service và gRPC nội bộ.
- Đánh giá trade-off về latency, payload, contract, bảo mật và khả năng vận hành.

## 1. Bài toán giao tiếp với browser và hệ sinh thái HTTP rộng

Một hệ thống có thể phục vụ nhiều loại client: browser chạy JavaScript, ứng dụng mobile, đối tác tích hợp, script tự động hóa và service backend. Những client này thường đã có sẵn HTTP stack, hỗ trợ request/response, JSON, TLS, cookie, OAuth/OIDC, proxy và công cụ debug HTTP.

Khi API được gọi trực tiếp từ browser hoặc cần tích hợp rộng, REST trên HTTP thường giảm chi phí tiếp cận. Browser có thể dùng Fetch API, thư viện HTTP hoặc framework frontend mà không cần runtime gRPC đặc thù. Đối tác có thể thử endpoint bằng curl, Postman hoặc công cụ HTTP tương tự.

Trong phạm vi **SPRING_GRPC**, việc chọn REST cho browser và hệ sinh thái HTTP rộng không phủ nhận vai trò của gRPC. Một kiến trúc có thể dùng REST ở biên hệ thống, nơi client đa dạng, rồi dùng gRPC giữa các service nội bộ cần contract Protobuf, typed stub, deadline và streaming.

## 2. REST và HTTP mang lại lợi thế gì?

REST là phong cách kiến trúc dựa trên resource và các ràng buộc tương tác. API REST thường biểu diễn tài nguyên bằng URI, dùng HTTP method theo ngữ nghĩa và trả representation như JSON.

Các lợi thế quan trọng:

- **Tính phổ biến:** browser, mobile, proxy, API gateway và đối tác đều có HTTP client sẵn.
- **Ngữ nghĩa chuẩn:** method, status code, header, conditional request và cache có quy tắc phổ biến.
- **Khả năng quan sát:** request/response dễ kiểm tra bằng devtools, curl, log và API gateway.
- **Tích hợp hệ sinh thái:** OpenAPI, OAuth/OIDC, CDN, WAF, rate limiting và API management có hỗ trợ rộng.
- **Tiến hóa contract:** JSON thường cho phép client và server phát triển độc lập nếu giữ compatibility và quy tắc field rõ ràng.

REST không đồng nghĩa với API thiết kế tùy tiện theo URL. API cần dùng đúng method/status semantics, có contract và chính sách tương thích rõ ràng.

## 3. Vì sao browser thường dùng REST thay vì gRPC native?

Browser hỗ trợ HTTP/2 và có thể gửi request HTTP bằng Fetch API, nhưng browser API không cho ứng dụng JavaScript điều khiển trực tiếp mọi chi tiết transport mà gRPC native cần, chẳng hạn framing HTTP/2 và trailer semantics theo cách client gRPC thông thường sử dụng.

Vì vậy, gRPC native client thường không chạy trực tiếp trong browser như một HTTP JSON client. Có hai hướng phổ biến:

- **REST/JSON API:** browser gọi endpoint HTTP thông thường, nhận JSON và status/header chuẩn.
- **gRPC-Web:** browser dùng client/runtime gRPC-Web và server-side proxy hoặc gateway chuyển tiếp sang gRPC backend.

gRPC-Web hữu ích khi muốn giữ contract **Protocol Buffers (Protobuf)** và một phần semantics RPC trong browser. Tuy nhiên, nó cần tooling, proxy và cấu hình tương thích; khả năng streaming phụ thuộc implementation. Nếu browser chỉ cần CRUD/query thông thường, REST thường đơn giản hơn.

Không nên nói rằng browser không hỗ trợ HTTP/2. Giới hạn nằm ở khả năng sử dụng trực tiếp giao thức gRPC native qua API browser, không phải ở việc browser thiếu HTTP/2.

## 4. So sánh REST, gRPC và gRPC-Web

| Tiêu chí | REST/JSON | gRPC native | gRPC-Web |
| --- | --- | --- | --- |
| Client browser | Hỗ trợ trực tiếp qua Fetch/XHR | Thường cần client runtime và transport không có sẵn trong browser API | Có client/runtime dành cho browser |
| Contract | OpenAPI, JSON Schema hoặc tài liệu tương đương | Protobuf service/message | Thường dùng Protobuf |
| Transport | HTTP semantics, HTTP/1.1 hoặc HTTP/2 | HTTP/2 với gRPC framing | HTTP qua proxy/gateway theo gRPC-Web protocol |
| Debug | DevTools, curl, Postman | Công cụ gRPC như grpcurl/GUI chuyên dụng | Công cụ và runtime hỗ trợ gRPC-Web |
| Payload | JSON văn bản, dễ đọc | Protobuf nhị phân, thường gọn | Protobuf theo protocol gRPC-Web |
| Streaming | SSE/WebSocket hoặc cơ chế HTTP phù hợp | Unary và các kiểu streaming gRPC | Hỗ trợ phụ thuộc client/proxy/implementation |
| Cache HTTP | Có thể dùng cache semantics chuẩn | Không phải mô hình cache HTTP resource thông thường | Hạn chế hơn REST resource caching |
| Tích hợp đối tác | Rộng và quen thuộc | Đối tác cần hỗ trợ gRPC/Protobuf | Cần đối tác hỗ trợ gRPC-Web |

Chọn theo client và semantics cần thiết. Nếu browser và đối tác HTTP là nhóm client chính, REST giảm friction. Nếu browser cần contract Protobuf hoặc streaming RPC, đánh giá gRPC-Web thay vì cố dùng gRPC native trực tiếp.

## 5. Thiết kế resource và HTTP method

REST API nên mô hình hóa tài nguyên thay vì biến mọi hành động thành một RPC name trong URL. Ví dụ với đơn hàng:

| Nhu cầu | Method và URI gợi ý | Ý nghĩa |
| --- | --- | --- |
| Liệt kê đơn hàng | GET /api/v1/orders | Đọc collection, thường hỗ trợ filter/pagination. |
| Đọc một đơn | GET /api/v1/orders/{orderId} | Đọc resource cụ thể. |
| Tạo đơn | POST /api/v1/orders | Tạo resource hoặc khởi tạo operation. |
| Thay thế toàn bộ biểu diễn | PUT /api/v1/orders/{orderId} | Thực hiện thay thế theo semantics PUT. |
| Cập nhật một phần | PATCH /api/v1/orders/{orderId} | Thay đổi một phần resource theo patch format đã công bố. |
| Xóa đơn | DELETE /api/v1/orders/{orderId} | Yêu cầu xóa resource theo policy. |

Không dùng GET để tạo side effect. GET được kỳ vọng safe và có thể được cache hoặc prefetch. PUT và DELETE có semantics idempotent theo HTTP; POST không mặc nhiên idempotent. Nếu client cần retry thao tác tạo, API có thể hỗ trợ idempotency key và quy định rõ cách server xử lý request trùng.

## 6. Ví dụ REST controller trong Spring

Một endpoint Spring MVC/WebFlux có thể trả JSON representation cho browser:

~~~java
@RestController
@RequestMapping("/api/v1/orders")
final class OrderController {
    private final OrderApplicationService orders;

    OrderController(OrderApplicationService orders) {
        this.orders = orders;
    }

    @GetMapping("/{orderId}")
    ResponseEntity<OrderResponse> getOrder(
            @PathVariable String orderId) {
        return orders.find(orderId)
            .map(order -> ResponseEntity.ok(
                OrderResponse.from(order)))
            .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PostMapping
    ResponseEntity<OrderResponse> createOrder(
            @RequestBody CreateOrderRequest request) {
        Order created = orders.create(request);
        URI location = URI.create(
            "/api/v1/orders/" + created.id());

        return ResponseEntity
            .created(location)
            .body(OrderResponse.from(created));
    }
}
~~~

OrderApplicationService chứa use case nghiệp vụ. Controller chịu trách nhiệm chuyển HTTP request/response sang application API. Với kiến trúc có gRPC nội bộ, application service hoặc adapter phía sau controller có thể gọi generated gRPC client để giao tiếp với service khác.

Ví dụ minh họa cần các DTO và service tương ứng trong dự án. Không expose trực tiếp Protobuf generated message làm JSON public contract nếu điều đó khiến API browser bị ràng buộc vào chi tiết nội bộ của gRPC schema.

## 7. HTTP status code là một phần của contract

Status code cho client biết kết quả ở mức HTTP:

| Status | Ý nghĩa thường dùng |
| --- | --- |
| 200 OK | Request thành công và có response representation. |
| 201 Created | Resource mới được tạo; thường kèm Location. |
| 202 Accepted | Đã nhận request nhưng xử lý bất đồng bộ chưa hoàn tất. |
| 204 No Content | Thành công nhưng không có response body. |
| 400 Bad Request | Request sai cú pháp hoặc không hợp lệ ở mức đầu vào. |
| 401 Unauthorized | Thiếu hoặc credential không hợp lệ; cần authentication. |
| 403 Forbidden | Đã xác thực nhưng không đủ quyền. |
| 404 Not Found | Resource/route không tồn tại hoặc không được công khai. |
| 409 Conflict | Xung đột với trạng thái hiện tại của resource. |
| 422 Unprocessable Content | Nội dung hiểu được nhưng không thỏa quy tắc xử lý/nghiệp vụ theo API policy. |
| 429 Too Many Requests | Bị giới hạn tốc độ hoặc quota. |
| 500 Internal Server Error | Lỗi server không được phân loại cụ thể hơn. |
| 502/503/504 | Gateway/upstream lỗi, service tạm thời không khả dụng hoặc timeout. |

Không trả 200 OK cho mọi kết quả rồi đặt mã lỗi riêng trong JSON nếu không có lý do tương thích rõ. Client, proxy, cache và monitoring dựa vào HTTP status để xử lý đúng.

## 8. JSON contract và tiến hóa API

JSON dễ đọc và được hỗ trợ rộng, nhưng tính linh hoạt cũng có thể tạo contract lỏng nếu server đổi kiểu hoặc ý nghĩa field tùy tiện.

Các quy tắc nên áp dụng:

- Công bố OpenAPI hoặc contract tương đương cho endpoint, request, response và error model.
- Thêm field mới theo hướng backward-compatible; client cũ cần bỏ qua field chưa biết.
- Không đổi kiểu hoặc tái sử dụng ý nghĩa field đã phát hành.
- Quy định field required/optional và default semantics rõ ràng.
- Chuẩn hóa format timestamp, decimal, enum và identifier.
- Dùng version trong URI hoặc cơ chế versioning đã thống nhất khi có breaking change.

JSON number có thể gây mất chính xác với integer lớn khi đi qua JavaScript Number. Với identifier hoặc số nguyên vượt safe integer range, cân nhắc biểu diễn dưới dạng string và mô tả trong contract.

Không giả định JSON tự tương thích. Compatibility phải được kiểm tra bằng contract test và quá trình rollout client/server có overlap phiên bản.

## 9. Pagination, filtering và cache

Browser thường cần tải collection theo từng trang thay vì lấy toàn bộ dữ liệu:

~~~http
GET /api/v1/orders?status=OPEN&pageSize=25&pageToken=eyJvZmZzZXQiOjI1fQ
Accept: application/json
~~~

Response có thể gồm items và nextPageToken. Cursor token nên được server quản lý hoặc ký để client không thể tùy ý thay đổi vị trí truy vấn. Tránh dùng offset pagination cho collection thay đổi nhanh nếu nó tạo duplicate/missing item giữa các trang.

HTTP hỗ trợ cache semantics:

- Cache-Control điều khiển khả năng và thời hạn cache.
- ETag đại diện phiên bản representation.
- If-None-Match cho phép client hỏi representation có thay đổi không.
- 304 Not Modified giúp client dùng bản cache hiện có.

Chỉ cache response khi policy dữ liệu cho phép. Response cá nhân hóa hoặc chứa dữ liệu nhạy cảm cần cache policy phù hợp, ví dụ private hoặc no-store. Không đặt public cache cho response phụ thuộc identity.

## 10. CORS và authentication cho browser

Browser áp dụng same-origin policy. Khi frontend gọi API khác origin, server cần cấu hình Cross-Origin Resource Sharing (CORS) phù hợp:

- Chỉ allow origin cần thiết thay vì wildcard tùy tiện.
- Chỉ allow HTTP methods và headers mà frontend thực sự dùng.
- Cho phép credentials chỉ khi có nhu cầu và cấu hình origin cụ thể.
- Xử lý preflight OPTIONS.
- Không coi CORS là cơ chế authentication hoặc authorization.

Với OAuth 2.0/OIDC, browser thường lấy access token qua flow phù hợp rồi gửi bearer token trong Authorization header. Nếu dùng cookie phiên, cần cân nhắc CSRF protection và cookie attributes (Secure, HttpOnly, SameSite) theo mô hình triển khai.

TLS bảo vệ credential trên đường truyền. Backend vẫn phải xác minh token, issuer, audience, expiry và quyền truy cập. Không tin user ID hoặc tenant ID do frontend tự gửi nếu chưa đối chiếu với principal đã xác thực.

## 11. Streaming và cập nhật dữ liệu cho browser

REST request/response phù hợp với thao tác ngắn và resource representation. Khi browser cần nhận cập nhật liên tục, có thể dùng:

- **Server-Sent Events (SSE):** server đẩy event một chiều qua HTTP; browser có EventSource API.
- **WebSocket:** kết nối hai chiều cho tương tác realtime.
- **Polling/long polling:** lựa chọn đơn giản khi tần suất cập nhật thấp hoặc hạ tầng không hỗ trợ stream lâu dài.
- **gRPC-Web:** khi cần giữ Protobuf contract và RPC model trong browser, với proxy/runtime tương thích.

Chọn theo hướng dữ liệu, reconnect semantics, proxy timeout, auth và browser support. SSE không thay thế bidirectional stream; WebSocket không tự cung cấp contract Protobuf hay status/deadline semantics của gRPC.

## 12. REST edge kết hợp gRPC nội bộ

Một kiến trúc thực tế có thể để browser gọi REST API tại edge. Controller xác thực request, kiểm tra input và gọi application service; application service dùng gRPC client để gọi các backend nội bộ.

~~~mermaid
flowchart LR
  B["Browser / Mobile / Partner"] -->|"HTTPS + JSON"| A["Spring REST API / Edge"]
  A -->|"gRPC + Protobuf"| O["Order Service"]
  O -->|"gRPC + Protobuf"| I["Inventory Service"]
  O -->|"gRPC + Protobuf"| P["Payment Service"]
  O -->|"Event"| Q["Message Broker"]
~~~

Lợi ích:

- Client bên ngoài dùng HTTP/JSON dễ tiếp cận.
- Backend nội bộ giữ typed Protobuf contract và RPC semantics.
- Edge có thể áp dụng API versioning, rate limit, CORS và public auth policy.
- Backend có thể dùng channel reuse, deadline và load balancing.

Rủi ro là gateway/controller có thể trở thành nơi chứa quá nhiều orchestration. Giữ business use case ở application/service layer, truyền deadline/correlation context xuống gRPC call và ánh xạ lỗi backend thành HTTP status có ý nghĩa.

## 13. Ánh xạ lỗi gRPC sang HTTP

Khi REST edge gọi gRPC backend, không nên trả nguyên status text nội bộ hoặc stack trace cho browser. Cần ánh xạ có chủ đích:

| gRPC status | HTTP mapping thường gặp | Lưu ý |
| --- | --- | --- |
| INVALID_ARGUMENT | 400 Bad Request | Validation đầu vào. |
| UNAUTHENTICATED | 401 Unauthorized | Client cần credential hợp lệ. |
| PERMISSION_DENIED | 403 Forbidden | Đã xác thực nhưng thiếu quyền. |
| NOT_FOUND | 404 Not Found | Resource không tồn tại. |
| ALREADY_EXISTS | 409 Conflict | Trùng resource/key. |
| FAILED_PRECONDITION | 409 hoặc 422 | Chọn theo contract public. |
| RESOURCE_EXHAUSTED | 429 hoặc 503 | Phân biệt quota caller với quá tải server. |
| UNAVAILABLE | 503 Service Unavailable | Có thể tạm thời; không lộ topology nội bộ. |
| DEADLINE_EXCEEDED | 504 Gateway Timeout | Backend vượt ngân sách thời gian. |
| INTERNAL / UNKNOWN | 500 Internal Server Error | Trả lỗi chung và correlation ID. |

Mapping không phải bảng chuyển đổi bắt buộc cho mọi hệ thống. Public API phải định nghĩa semantics ổn định, tránh để implementation status của backend vô tình trở thành contract bên ngoài.

## 14. Bảo vệ latency xuyên qua REST edge

Khi REST controller gọi gRPC backend, tổng latency gồm thời gian parse HTTP/JSON, logic edge, gRPC network, backend processing và response mapping. Đặt deadline gRPC theo ngân sách còn lại của HTTP request, không cấp cho mỗi backend toàn bộ timeout của caller.

Nếu một request gọi tuần tự nhiều backend, chia latency budget có chủ đích. Nếu gọi song song, giới hạn concurrency và hủy các call không còn cần khi request tổng đã timeout. Tránh retry không giới hạn vì có thể khuếch đại tải lúc backend đang lỗi.

Propagate correlation/trace context qua HTTP header và gRPC metadata để quan sát toàn bộ đường đi. Không ghi bearer token hoặc dữ liệu cá nhân vào log/trace.

## 15. Khi nào REST không phải lựa chọn tốt nhất?

REST có thể không phù hợp nhất khi:

- Service nội bộ có tần suất RPC rất cao và cần contract Protobuf/type-safe giữa các JVM.
- Cần client/server/bidirectional streaming với flow control và semantics gRPC.
- Payload có cấu trúc lớn, lặp lại nhiều và lợi ích serialization nhị phân đã được benchmark xác nhận.
- Caller cần deadline, cancellation và status semantics theo RPC một cách nhất quán.
- Các client đều kiểm soát được runtime gRPC và hạ tầng hỗ trợ HTTP/2 end-to-end.

Ngay cả trong trường hợp này, REST vẫn có thể là public edge. Quyết định không cần đồng nhất giữa API ngoài và giao tiếp giữa backend.

## 16. Lỗi thường gặp khi chọn REST cho browser

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng gRPC native trực tiếp từ Fetch như HTTP JSON | Browser không thực hiện gRPC framing/trailer semantics như client native | Dùng REST hoặc gRPC-Web/proxy. |
| Cho rằng browser không hỗ trợ HTTP/2 | Hiểu sai giới hạn giao thức | Phân biệt HTTP/2 support với gRPC native client API. |
| Dùng POST cho mọi thao tác | Mất HTTP method/cache/idempotency semantics | Mô hình hóa resource và method phù hợp. |
| Trả 200 cho mọi lỗi | Client/proxy/monitoring khó phân loại lỗi | Dùng status code đúng contract. |
| Không có OpenAPI/schema | Client tích hợp dựa vào suy đoán | Công bố và kiểm thử contract. |
| Trả collection không pagination | Payload lớn, latency và memory tăng | Dùng cursor/page token và giới hạn page size. |
| Cache dữ liệu cá nhân như public | Rò dữ liệu giữa người dùng | Dùng private/no-store theo policy. |
| Coi CORS là bảo mật API | Client không bị chặn bởi CORS vẫn có thể gọi từ nơi khác | Xác thực và authorization ở server. |
| Expose Protobuf nội bộ thành public JSON không kiểm soát | Public API bị khóa vào schema backend | Tạo DTO/public contract độc lập khi cần. |
| REST edge không truyền deadline xuống backend | Request HTTP timeout nhưng RPC vẫn chiếm tài nguyên | Propagate ngân sách và cancellation. |

## 17. Ma trận quyết định

| Câu hỏi | Nếu câu trả lời là “có” | Hướng cân nhắc |
| --- | --- | --- |
| Browser/đối tác cần gọi trực tiếp bằng HTTP client phổ biến? | Có | REST/JSON thường phù hợp. |
| Cần cache resource bằng HTTP semantics? | Có | REST có lợi thế rõ. |
| Cần API dễ thử bằng DevTools, curl và Postman? | Có | REST giảm friction. |
| Client browser cần Protobuf/RPC semantics? | Có | Đánh giá gRPC-Web và proxy. |
| Backend-to-backend cần typed contract, latency và streaming? | Có | gRPC native là ứng viên tốt. |
| Cần durable event và consumer xử lý độc lập? | Có | Message broker phù hợp hơn. |
| Hệ thống cần public API ổn định nhưng backend dùng gRPC? | Có | Dùng REST edge và gRPC nội bộ. |

Đánh giá cả client ecosystem, latency, contract, cache, security, observability và năng lực vận hành. Không chọn giao thức chỉ vì một chỉ số serialization.

## 18. Bài tập thực hành

Thiết kế API cho ứng dụng đặt hàng có browser frontend và các backend Spring:

1. Định nghĩa REST endpoint để browser tạo đơn, đọc đơn và liệt kê đơn có pagination.
2. Chọn HTTP method/status code và quy tắc idempotency cho thao tác tạo.
3. Viết OpenAPI contract và JSON DTO độc lập với Protobuf nội bộ.
4. Thiết kế Spring controller gọi OrderService qua gRPC client.
5. Đặt deadline theo ngân sách HTTP request và ánh xạ gRPC status sang HTTP status.
6. Cấu hình CORS, TLS, OAuth/OIDC và policy cache cho dữ liệu cá nhân.
7. Thêm trace/correlation propagation từ HTTP header sang gRPC metadata.
8. Đánh giá trường hợp browser cần realtime: chọn SSE, WebSocket hay gRPC-Web và nêu lý do.
9. Đo p50/p95/p99, payload size và throughput cho REST edge cùng backend gRPC.

**Tiêu chí hoàn thành:** browser dùng API HTTP dễ tích hợp, backend giữ contract gRPC khi phù hợp, public contract ổn định và ngân sách latency/bảo mật được truyền qua các hop.

## 19. Ghi nhớ

- REST/HTTP phù hợp browser và hệ sinh thái tích hợp rộng nhờ Fetch, JSON, status/header, cache và tooling phổ biến.
- Browser hỗ trợ HTTP/2 nhưng không cung cấp native gRPC client API tương đương runtime gRPC; dùng REST hoặc gRPC-Web theo nhu cầu.
- Thiết kế resource, HTTP method, status code, pagination và cache theo semantics chuẩn.
- Công bố OpenAPI/JSON contract và quản lý compatibility; JSON không tự động bảo đảm backward compatibility.
- CORS không thay authentication/authorization; TLS và kiểm tra token vẫn bắt buộc theo threat model.
- REST edge có thể gọi gRPC nội bộ để giữ typed Protobuf contract và deadline.
- Ánh xạ lỗi gRPC sang HTTP theo public API semantics, không phơi bày chi tiết backend.
- Chọn SSE, WebSocket hoặc gRPC-Web khi browser cần cập nhật/streaming, tùy hướng dữ liệu và hạ tầng.
- Đo latency end-to-end và tail latency trước khi kết luận REST hay gRPC phù hợp hơn.

Chọn REST cho browser và hệ sinh thái HTTP rộng khi khả năng tiếp cận, cache, tooling và tương thích client là ưu tiên; vẫn có thể dùng gRPC bên trong để tối ưu giao tiếp service-to-service.
