# Metadata bị mất qua proxy

Khi client gửi gRPC metadata nhưng server không nhận được, nguyên nhân có thể nằm ở gateway, reverse proxy, load balancer hoặc lớp chuyển đổi giao thức giữa hai đầu. Client interceptor có thể đã thêm header đúng, nhưng điều đó chưa chứng minh header đã tới server. Với Spring gRPC, cần hiểu metadata được vận chuyển trong HTTP/2 headers/trailers, xác định proxy đang hoạt động ở tầng nào và kiểm tra từng ranh giới mà không làm lộ credentials.

Bài này tập trung vào cách chẩn đoán và xử lý metadata bị loại bỏ, đổi tên, gộp, vượt giới hạn hoặc không được chuyển tiếp qua proxy.

## 1. Đường đi của metadata qua proxy

Trong gRPC native, request metadata được biểu diễn bằng HTTP/2 request headers; response metadata nằm trong initial response headers và trailing headers. Proxy có thể chỉ chuyển tiếp luồng TCP hoặc kết thúc HTTP/2, phân tích headers rồi tạo một kết nối upstream mới.

```text
gRPC client             Proxy / gateway                    gRPC server
    |                          |                                  |
    |-- HTTP/2 headers ------->|                                  |
    |   x-request-id           |                                  |
    |   authorization          |-- upstream HTTP/2 headers ------>|
    |                          |   x-request-id?                   |
    |                          |   authorization?                 |
    |                          |                                  |
    |-- Protobuf messages ---->|-- HTTP/2 DATA frames ------------>|
    |                          |                                  |
    |<-- response headers -----|<-- response headers --------------|
    |<-- messages -------------|<-- DATA frames -------------------|
    |<-- trailers/status ------|<-- trailers/status ---------------|
```

Proxy có thể thay đổi headers hoặc trailers tùy cấu hình. Việc client interceptor nhìn thấy key trước khi gửi chỉ chứng minh ứng dụng đã chuẩn bị metadata. Server interceptor mới xác nhận được key đã tới server.

## 2. Phân biệt proxy L4 và L7

| Kiểu proxy | Cách hoạt động | Ảnh hưởng thường gặp đến metadata |
| --- | --- | --- |
| L4 TCP pass-through | Chuyển tiếp kết nối TCP, không phân tích HTTP/2 headers | Thường giữ nguyên byte stream; metadata ít bị sửa trực tiếp |
| L4 TLS pass-through | Chuyển tiếp kết nối TLS tới upstream | Proxy không đọc được metadata bên trong TLS |
| L7 HTTP/2-aware | Kết thúc HTTP/2, đọc headers/trailers rồi tạo upstream request | Có thể áp dụng allowlist, remove, rewrite, giới hạn kích thước hoặc thay đổi trailers |
| Gateway chuyển đổi giao thức | Chuyển gRPC sang giao thức khác hoặc gRPC-Web | Có thể ánh xạ, lọc hoặc không hỗ trợ đầy đủ custom metadata/trailers |

**Native gRPC cần HTTP/2 ở đường kết nối gRPC.** Nếu proxy nhận HTTP/2 từ client nhưng kết nối upstream bằng HTTP/1.1 thông thường, nó không còn là đường chuyển tiếp native gRPC trong suốt. Hãy cấu hình upstream HTTP/2 phù hợp hoặc dùng gateway chuyển đổi gRPC-Web được thiết kế cho mục đích đó.

Nếu TLS được kết thúc tại proxy, cần kiểm tra cả hai chặng: client → proxy và proxy → server. Một kết nối TLS thành công ở phía client không chứng minh upstream đang dùng HTTP/2 hoặc đang giữ metadata.

## 3. Những nguyên nhân phổ biến khiến metadata biến mất

### Header allowlist hoặc remove rule

Gateway có thể chỉ chuyển tiếp những header nằm trong allowlist, hoặc cấu hình loại bỏ các key không mong muốn. Các custom key như `x-request-id`, `x-tenant-id` hay `x-client-version` có thể không được chuyển nếu proxy chỉ cho phép một tập header xác định.

Kiểm tra:

- Danh sách header được phép từ downstream sang upstream.
- Cấu hình loại bỏ header theo tên, prefix hoặc route.
- Quy tắc rewrite/rename header và thứ tự áp dụng.
- Chính sách riêng cho route gRPC, virtual host hoặc từng service.

Không cho phép chuyển tiếp mọi header một cách vô điều kiện. Đặc biệt, `authorization`, cookie và các custom credential header cần quy tắc bảo mật riêng.

### Không tương thích HTTP/2 hoặc gRPC

Một proxy có thể nhận request nhưng chuyển upstream bằng giao thức hoặc chế độ không hỗ trợ gRPC native. Kiểm tra:

- Downstream và upstream có dùng HTTP/2 theo yêu cầu của gRPC không?
- Proxy có giữ content type `application/grpc` và các thuộc tính điều khiển gRPC cần thiết không?
- Các thuộc tính như `te: trailers` và trạng thái/trailers có được xử lý đúng không?
- Có lớp gRPC-Web transcoding hoặc HTTP/JSON transcoding nào đang tham gia không?

Đừng chỉ nhìn vào mã HTTP thành công của proxy. Một request có thể tới được gateway nhưng metadata hoặc gRPC trailers không được chuyển đúng tới service.

### Giới hạn kích thước headers

Tổng kích thước header list có thể bị giới hạn tại client, proxy hoặc server. Khi thêm nhiều metadata, request có thể vượt ngưỡng và bị từ chối trước khi server interceptor chạy. Binary metadata dùng biểu diễn Base64 trên đường truyền nên kích thước vận chuyển có thể lớn hơn dữ liệu byte ban đầu.

Giới hạn ở proxy và giới hạn metadata của gRPC là hai lớp cấu hình khác nhau. Tăng giới hạn message Protobuf không giải quyết giới hạn header; tăng giới hạn header cũng không phải cách truyền payload lớn.

### Chuẩn hóa và xử lý key/value

Tên metadata key gRPC được chuẩn hóa theo quy tắc chữ thường. Proxy có thể chuẩn hóa tên header, gộp các value trùng tên hoặc áp dụng parser riêng. Các lỗi thường gặp:

- Client và server dùng tên key khác nhau, ví dụ `x-request-id` và `x-requestid`.
- Key binary thiếu hậu tố `-bin` hoặc bị proxy xử lý như text tùy ý.
- Nhiều value cho một key bị gộp hoặc chỉ giữ một value.
- Custom key bắt đầu bằng `grpc-`, vốn dành riêng cho giao thức.
- Value quá dài hoặc chứa ký tự không hợp lệ với ASCII metadata.

Không giả định mọi proxy xử lý duplicate headers giống nhau. Với key cần duy nhất như request ID hoặc tenant selection, nên quy định một value và kiểm tra điều đó ở server.

### Response trailers bị mất

Metadata từ server về client có thể bị ảnh hưởng riêng với request headers. Một proxy/gateway có thể chuyển initial response headers và message nhưng không giữ trailers hoặc gRPC status theo đúng cách. Khi đó client có thể thấy status không như mong đợi hoặc không nhận custom trailer.

Kiểm tra cấu hình gRPC của proxy, hỗ trợ HTTP/2 trailers và cách gateway ánh xạ lỗi. Không kết luận rằng request metadata bị mất chỉ vì response trailers không xuất hiện; đó là hai hướng truyền khác nhau.

## 4. Chẩn đoán theo từng ranh giới

Thay vì chỉ log toàn bộ metadata, hãy kiểm tra **sự hiện diện của một allowlist key** tại từng chặng:

| Điểm quan sát | Cần xác minh | Cách thu thập |
| --- | --- | --- |
| Client trước transport | Interceptor đã thêm key chưa? | Kiểm tra `headers.containsKey(...)` trong client interceptor |
| Proxy nhận request | Key có tới listener/downstream không? | Access log hoặc telemetry chỉ ghi tên key được phép |
| Proxy gửi upstream | Key có bị remove/rewrite không? | So sánh header names ở upstream request theo cấu hình proxy |
| Server interceptor | Key có thực sự tới gRPC server không? | Kiểm tra `headers.containsKey(...)` hoặc đọc value đã được cho phép |
| Server gửi response | Headers/trailers có được tạo không? | Quan sát `sendHeaders(...)` và `close(status, trailers)` |
| Client nhận response | Callback nào được gọi, key nào có mặt? | Kiểm tra `onHeaders(...)` và `onClose(...)` |

### Ví dụ kiểm tra ở server mà không log value

Interceptor có thể ghi nhận sự hiện diện của key và tên RPC, không dump toàn bộ `Metadata`:

```java
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class MetadataPresenceInterceptor implements ServerInterceptor {
    private static final Logger log =
        LoggerFactory.getLogger(MetadataPresenceInterceptor.class);

    private static final Metadata.Key<String> REQUEST_ID =
        Metadata.Key.of(
            "x-request-id", Metadata.ASCII_STRING_MARSHALLER);
    private static final Metadata.Key<String> CLIENT_VERSION =
        Metadata.Key.of(
            "x-client-version", Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        log.debug(
            "grpc_metadata_presence method={} request_id={} client_version={}",
            call.getMethodDescriptor().getFullMethodName(),
            headers.containsKey(REQUEST_ID),
            headers.containsKey(CLIENT_VERSION));

        return next.startCall(call, headers);
    }
}
```

Đây là interceptor chẩn đoán, không thay thế interceptor kiểm tra request ID hoặc authentication. Không ghi giá trị authorization, cookie, API key hay toàn bộ metadata. Nếu cần đối chiếu request ID, chỉ ghi ID đã được kiểm tra định dạng hoặc dùng correlation ID do hệ thống tin cậy tạo.

### Cách đọc kết quả

- Client có key, server không có key: kiểm tra proxy, route, protocol upstream và header size.
- Proxy ingress có key nhưng egress không có: tập trung vào allowlist/remove/rewrite và cấu hình route.
- Server có request header nhưng client thiếu response trailer: điều tra response path, trailer forwarding và đường kết thúc lỗi.
- Cả proxy và server đều không thấy key: xác minh client interceptor có được gắn vào stub/channel thực sự đang gọi.
- Chỉ một số route bị lỗi: so sánh cấu hình route, virtual host, gateway policy và upstream cluster giữa route hoạt động và route lỗi.

## 5. Khắc phục theo nguyên nhân

1. **Header bị lọc:** thêm chính xác custom key cần thiết vào allowlist của route; bỏ rule remove/rewrite không phù hợp. Không mở toàn bộ headers nếu chỉ cần hai hoặc ba key.
2. **Upstream sai giao thức:** cấu hình proxy dùng HTTP/2 tới gRPC server; nếu cần HTTP/1.1 hoặc browser client, dùng gateway gRPC-Web/transcoding có hỗ trợ tương ứng.
3. **Vượt giới hạn:** giảm số lượng và kích thước metadata, bỏ value dư thừa; chỉ điều chỉnh giới hạn header ở những hop cần thiết và giữ ngưỡng hữu hạn.
4. **Binary metadata bị xử lý sai:** dùng key có hậu tố `-bin`, đúng binary marshaller và kiểm tra khả năng hỗ trợ của proxy. Không tự Base64 thêm lần nữa.
5. **Duplicate key bị thay đổi:** thiết kế key cần duy nhất, gửi một value và xác minh server từ chối hoặc xử lý duplicate theo hợp đồng.
6. **Trailers không được chuyển:** bật chế độ gRPC/HTTP2 phù hợp, kiểm tra trailer handling và test cả success lẫn lỗi trailers-only.
7. **TLS termination gây khác biệt:** kiểm tra protocol và TLS trên từng chặng; cấu hình upstream transport phù hợp và xác thực proxy/service theo mô hình tin cậy.

Sau khi sửa proxy, cần kiểm tra cả request metadata và response metadata. Một cấu hình chỉ khắc phục request headers có thể vẫn làm mất trailers.

## 6. Rà soát cấu hình proxy

Không có một đoạn cấu hình chung dùng được cho mọi proxy. Tên directive và mặc định khác nhau giữa Envoy, NGINX, ingress controller, service mesh và cloud load balancer. Khi rà soát cấu hình, hãy tìm đúng các nhóm thiết lập:

| Nhóm cấu hình | Điều cần xác nhận |
| --- | --- |
| Listener/downstream protocol | Nhận gRPC qua HTTP/2; TLS/ALPN nếu dùng TLS |
| Route/virtual host | Route đúng gRPC service/method, không áp dụng policy HTTP thường không phù hợp |
| Header mutation | Custom metadata cần thiết không bị remove hoặc rewrite |
| Header allowlist | `x-request-id`, `x-client-version` và key ứng dụng được cho phép cụ thể |
| Upstream cluster | Kết nối HTTP/2 tới gRPC server hoặc dùng bridge được hỗ trợ |
| Header size limits | Giới hạn đủ cho metadata hợp lệ nhưng vẫn hữu hạn |
| Response handling | Giữ initial headers, trailers và gRPC status |
| Access logging | Không ghi credential hoặc token; chỉ ghi trường allowlist |

Ví dụ, nếu route có policy chỉ cho phép một số request headers, hãy thêm custom key vào danh sách được chuyển tiếp tại **đúng route** thay vì thay đổi global policy cho mọi service. Nếu proxy hỗ trợ request/response header removal, xác minh không có rule trùng lặp ở listener, route và upstream.

Đối với service mesh, kiểm tra cả cấu hình sidecar inbound và outbound. Header có thể được giữ ở ingress gateway nhưng bị loại tại sidecar của service hoặc egress gateway ở một chặng tiếp theo.

## 7. Kiểm thử qua proxy

In-process gRPC test hữu ích để kiểm tra interceptor và `Metadata` trong Java, nhưng nó không đi qua proxy, HTTP/2 termination hoặc header mutation. Muốn xác minh lỗi này phải có integration test chạy qua **đúng loại proxy và cấu hình gần với môi trường triển khai**.

| Ca kiểm thử | Cách thực hiện | Kết quả cần xác minh |
| --- | --- | --- |
| Metadata ASCII cơ bản | Gửi `x-request-id` qua proxy | Server interceptor nhận đúng key/value |
| Custom header allowlist | Gửi key được phép và key không được phép | Key được phép tới server; key bị chặn có hành vi đã định nghĩa |
| Header bị remove | Thử route có rule remove | Test phát hiện key không tới server |
| Header size boundary | Tăng tổng metadata tới và vượt ngưỡng test | Lỗi được xác định ở đúng hop; server không bị giả định đã nhận call |
| Binary metadata | Gửi key `-bin` với `byte[]` | Server nhận lại đúng byte |
| Duplicate metadata | Gửi nhiều value cùng key | Hành vi proxy/server khớp hợp đồng |
| Response headers | Server gửi initial metadata | Client nhận trong `onHeaders(...)` |
| Response trailers | Server đóng call với custom trailer và status | Client nhận trailer trong `onClose(...)` |
| Error/trailers-only | Server hoặc gateway từ chối trước message | Client xử lý status dù không có initial headers |
| TLS và HTTP/2 upstream | Gọi qua listener và upstream production-like | ALPN/protocol và metadata được giữ đúng |

Khi kiểm thử giới hạn header, không dùng token hoặc dữ liệu nhạy cảm làm payload thử. Dùng chuỗi giả và chỉ ghi kích thước hoặc trạng thái. Thu thập bằng chứng từ client, proxy ingress/egress và server để xác định chính xác chặng làm mất metadata.

## 8. Checklist điều tra sự cố

- [ ] Xác nhận interceptor client được gắn vào đúng stub/channel.
- [ ] Ghi nhận tên các metadata key cần theo dõi, không ghi secret value.
- [ ] Xác định proxy là L4 pass-through, L7 HTTP/2-aware hay gateway chuyển đổi giao thức.
- [ ] Kiểm tra HTTP/2 từ client tới proxy và từ proxy tới gRPC server.
- [ ] Kiểm tra header allowlist, remove rule, rewrite và phạm vi route.
- [ ] Kiểm tra header size limit tại client, proxy, server và load balancer.
- [ ] Kiểm tra quy tắc ASCII/binary, hậu tố `-bin` và duplicate key.
- [ ] Quan sát server interceptor để xác nhận request metadata thực nhận.
- [ ] Nếu lỗi ở chiều về, kiểm tra `onHeaders(...)`, `onClose(...)`, trailers và status.
- [ ] Chạy integration test qua proxy sau khi thay đổi cấu hình.
- [ ] Xác minh access log, tracing và debug log không ghi credentials/token.

## 9. Bài tập vận dụng

Một client Spring gRPC gửi `x-tenant-id` và `x-request-id` qua API gateway tới `OrderService`. Gọi trực tiếp service thì server nhận đủ metadata; đi qua gateway thì `x-tenant-id` biến mất. Trong một số trường hợp, client cũng không nhận custom response trailer `x-response-request-id`.

**Yêu cầu:**

1. Vẽ hai đường đi direct và qua gateway, xác định nơi cần quan sát header names.
2. Kiểm tra gateway là L4 hay L7, protocol upstream và policy allowlist/remove cho route gRPC.
3. Xác minh `x-tenant-id` chỉ được dùng sau khi đối chiếu với principal đã xác thực; không coi việc header được chuyển tiếp là bằng chứng quyền.
4. Kiểm tra riêng response trailers và status ở chiều server → client.
5. Thiết kế integration test qua gateway cho metadata ASCII, duplicate key, header size và trailers.
6. Đề xuất cách ghi log sự hiện diện của key mà không ghi token hoặc toàn bộ metadata.

**Câu hỏi tự kiểm tra:**

- Vì sao client interceptor thấy metadata không có nghĩa server đã nhận metadata?
- L4 pass-through khác L7 HTTP/2 proxy ở điểm nào?
- Vì sao upstream HTTP/1.1 thông thường không phải đường chuyển tiếp native gRPC trong suốt?
- Header allowlist và header removal có thể làm mất custom metadata ra sao?
- Giới hạn header khác giới hạn Protobuf message như thế nào?
- Vì sao request headers và response trailers phải được điều tra riêng?
- In-process test chứng minh được điều gì và không chứng minh được điều gì khi sự cố nằm ở proxy?

**Ghi nhớ:** Khi metadata bị mất qua proxy, hãy xác định đúng loại proxy và kiểm tra từng chặng client → proxy → server. Tập trung vào HTTP/2/gRPC upstream, allowlist/remove/rewrite, kích thước header, binary key và trailers. Dùng integration test qua proxy thật để xác nhận kết quả; chỉ log sự hiện diện của key được phép và không bao giờ dump credentials hoặc token.
