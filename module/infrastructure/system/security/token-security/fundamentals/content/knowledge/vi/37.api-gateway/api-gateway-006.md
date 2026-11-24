# Header stripping tại API Gateway

## 1. Header stripping là gì và vì sao liên quan đến bảo mật token?

Trong một hệ thống dùng **API Gateway**, client gửi HTTP request đến Gateway trước khi request được chuyển tới service nội bộ. Gateway có thể xác thực access token, kiểm tra quyền truy cập, định tuyến và điều chỉnh HTTP headers. **Header stripping** là thao tác **loại bỏ một hoặc nhiều header** khỏi request trước khi chuyển đến upstream service, hoặc khỏi response trước khi trả về client.

Header stripping không đồng nghĩa với xác thực token. Nó là một phần của việc **kiểm soát ranh giới tin cậy**: dữ liệu do client tự gửi không được mặc nhiên trở thành danh tính, vai trò hay đặc quyền đã được hệ thống xác nhận.

Ví dụ một client gửi:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token-cua-alice>
X-Authenticated-User: admin
X-User-Roles: ADMIN
```

Hai header `X-Authenticated-User` và `X-User-Roles` chỉ là chuỗi do client tự khai. Nếu order-service tin chúng mà không xác minh, người dùng bình thường có thể giả làm quản trị viên. Gateway phải loại bỏ các header danh tính không đáng tin trước khi gửi request tới service; nếu kiến trúc cần truyền danh tính, Gateway chỉ được tạo dữ liệu thay thế **sau khi** đã xác thực token và xác định quyền.

Cần phân biệt ba thao tác thường gặp:

| Thao tác | Ý nghĩa | Ví dụ |
|---|---|---|
| **Strip / remove** | Xóa header khỏi request/response đi tiếp | Xóa `X-User-Roles` do client gửi |
| **Overwrite / set** | Ghi lại header bằng giá trị do thành phần đáng tin tạo | Đặt `X-Verified-Subject` bằng `sub` đã được xác minh |
| **Filter / validate** | Kiểm tra và từ chối giá trị không hợp lệ | Từ chối header danh tính trùng lặp hoặc token sai audience |

**Xóa header giả mạo và thêm lại giá trị đáng tin là hai bước khác nhau.** Nếu chỉ xóa, service không nhận danh tính. Nếu chỉ thêm mà không xử lý header cũ và các biến thể của nó, request có thể chứa giá trị mâu thuẫn.

## 2. Ranh giới tin cậy: ai được quyền khẳng định danh tính?

Xét luồng request đi qua Gateway đến một service xử lý thanh toán:

```mermaid
flowchart LR
    C["Client không tin cậy"] -->|"Bearer token + header tự khai"| G["API Gateway"]
    G -->|"Xác thực token, phân quyền"| D{"Hợp lệ?"}
    D -->|"Không"| R["401 / 403"]
    D -->|"Có"| S["Loại header giả mạo"]
    S --> T["Chuyển tiếp token phù hợp hoặc tạo danh tính đáng tin"]
    T --> B["Payment Service"]
```

Gateway cần xử lý ba loại thông tin riêng biệt:

1. **Bằng chứng xác thực:** access token hoặc cơ chế đăng nhập khác; phải được kiểm tra theo giao thức, không dựa vào tên header.
2. **Thông tin danh tính đã xác minh:** chủ thể (`sub`), client, tenant, scope/role được suy ra từ token hoặc hệ thống phân quyền đáng tin.
3. **Metadata vận chuyển:** IP gốc, giao thức, host, trace ID, đường đi qua proxy; có thể hữu ích nhưng vẫn có khả năng bị giả mạo ở biên mạng.

Ví dụ, `X-Forwarded-For: 127.0.0.1` từ Internet không chứng minh request phát sinh từ máy local. Chỉ một reverse proxy đáng tin mới được chuẩn hóa chuỗi `Forwarded`/`X-Forwarded-*` dựa trên kết nối thực và các proxy đã được tin cậy. Khi có nhiều proxy, cần xác định chính xác hop nào được phép ghi và hop nào được phép đọc.

**Điều kiện tin cậy end-to-end:** service nội bộ cũng phải được bảo vệ khỏi truy cập trực tiếp từ client. Nếu attacker bỏ qua Gateway và gọi thẳng service, mọi quy tắc strip tại Gateway đều vô hiệu. Có thể dùng private network, firewall, mTLS và cơ chế xác thực service-to-service; service vẫn cần kiểm tra quyền phù hợp với vai trò của nó.

## 3. Những header thường cần loại bỏ hoặc kiểm soát

Không có một danh sách header phải xóa chung cho mọi ứng dụng. Hãy bắt đầu từ **hợp đồng giữa Gateway và upstream**: upstream cần dữ liệu nào, dữ liệu đó do ai tạo, và cơ sở tin cậy là gì?

| Header / nhóm header | Chính sách gợi ý ở Gateway | Lý do |
|---|---|---|
| `X-Authenticated-User`, `X-User-Id`, `X-User-Roles`, `X-Tenant-Id` nếu được dùng làm danh tính nội bộ | **Xóa bản client gửi**; chỉ tạo lại từ nguồn đã xác thực nếu thật sự cần | Ngăn giả mạo danh tính, vai trò, tenant |
| `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Host`, `X-Forwarded-Proto` | Chuẩn hóa tại proxy đáng tin; từ chối hoặc bỏ metadata không tin cậy | Ngăn giả mạo IP, host, scheme |
| `Authorization` | **Giữ, thay hoặc xóa có điều kiện** theo cơ chế xác thực upstream | Tránh rò token hoặc làm hỏng xác thực downstream |
| `Cookie` | Chỉ chuyển cookie mà upstream thực sự sử dụng; bỏ session cookie không liên quan | Giảm lộ phiên và phạm vi cookie |
| `Proxy-Authorization` và các header dành cho proxy | Xử lý tại proxy tương ứng, không coi là quyền truy cập API | Tách xác thực proxy và xác thực resource |
| `Connection` và các header hop-by-hop được nó liệt kê | Proxy HTTP phải xử lý đúng semantics hop-by-hop | Tránh chuyển tiếp sai metadata chỉ dành cho một kết nối |
| `X-Internal-Debug`, `X-Backend-Token` ở response | Xóa nếu là metadata hoặc bí mật chỉ dùng nội bộ | Hạn chế rò thông tin hệ thống |
| `WWW-Authenticate` ở response 401 | Thường **giữ** theo hợp đồng xác thực | Client cần biết cách xử lý challenge |
| `Cache-Control`, `Vary`, các header CORS/security | Quản lý theo chính sách rõ ràng, không xóa hàng loạt | Tránh thay đổi hành vi cache, trình duyệt và bảo mật |

Tên header HTTP **không phân biệt chữ hoa/chữ thường**. Vì vậy `X-User-Id` và `x-user-id` phải chịu cùng một quy tắc. Ngoài ra, Gateway cần kiểm soát trường hợp header lặp lại, dấu gạch dưới/dấu gạch ngang được các proxy xử lý khác nhau và request có nhiều proxy hop. Đừng xây bộ lọc chỉ dựa trên so khớp chuỗi phân biệt hoa/thường.

Các header như `Server` hay `X-Powered-By` có thể tiết lộ công nghệ đang dùng; xóa chúng chỉ là giảm bề mặt thông tin, không thay thế việc vá lỗi, giới hạn truy cập hoặc cấu hình bảo mật.

## 4. Đối xử đúng với từng loại token

Header stripping phụ thuộc vào **loại token** và thành phần nào có trách nhiệm kiểm tra nó.

| Loại token | Nơi thường xuất hiện | Quy tắc xử lý quan trọng |
|---|---|---|
| **JWT access token** | `Authorization: Bearer …` | Kiểm tra chữ ký, thuật toán được cho phép, `iss`, `aud`, thời hạn và quyền; chỉ relay nếu upstream chấp nhận audience và chính sách đó |
| **Opaque access token** | `Authorization: Bearer …` | Xác minh qua introspection hoặc cơ chế đã thiết kế; không đoán nội dung từ chuỗi token |
| **Refresh token** | Kênh đổi token của Authorization Server | Không đưa qua các API nghiệp vụ như một access token; giảm tối đa nơi lưu và truyền |
| **OIDC ID token** | Luồng đăng nhập tại client/RP | Chứng minh sự kiện xác thực cho đúng đối tượng nhận; không tự coi là access token của API |
| **Internal service token / token exchange** | Gateway gọi upstream | Token có audience, scope và thời hạn phù hợp service đích; tránh chuyển thẳng token rộng quyền khi không cần |

Ví dụ: JWT có `sub=alice` nhưng `aud=mobile-app` **không tự nhiên** hợp lệ đối với payment-service. Nếu Gateway không xác minh `aud` hoặc upstream chấp nhận nhầm ID token làm access token, việc strip vài header khác không chữa được lỗi xác thực này.

Với JWT, tối thiểu cần xác minh chữ ký bằng khóa hợp lệ, thuật toán phù hợp chính sách (không chấp nhận thuật toán do header token tự quyết định), `iss`, `aud`, `exp`, `nbf` nếu có, cùng scope/quyền cho API. Với opaque token, Gateway hoặc service thực hiện cơ chế xác minh hợp lệ (ví dụ introspection tới Authorization Server), đồng thời xác định cách xử lý lỗi và độ trễ của dịch vụ introspection. Giá trị scope không đồng nghĩa mọi quyền truy cập tài nguyên: quyền trên từng đơn hàng vẫn cần kiểm tra chủ sở hữu/tenant khi áp dụng.

Bearer token bị đánh cắp có thể bị phát lại trong thời gian còn hiệu lực. Strip `Authorization` trước khi chuyển tới service không loại trừ rủi ro ở Gateway hay trong log. Cần bổ sung HTTPS, thời hạn ngắn, kiểm soát log và khi cần dùng sender-constrained token như mTLS-bound access token hoặc DPoP, đồng thời kiểm tra bằng chứng tương ứng ở đúng điểm xác thực.

## 5. Chọn một trong ba mô hình truyền thông tin xác thực xuống upstream

### Mô hình A — Upstream tự xác thực access token

Gateway lọc các header danh tính có thể giả mạo nhưng **giữ `Authorization`** để service tự xác minh token:

```text
Client --(access token)--> Gateway
Gateway --(access token, đã bỏ X-User-Roles client gửi)--> Service
Service --(validate token + resource authorization)--> Business logic
```

Ưu điểm: service không phải tin vào `X-User-Id`; mỗi service tự bảo vệ khi có nhiều đường truy cập. Đổi lại, phải cấu hình đúng issuer/audience/khóa và phân quyền cho từng service; cần tránh nhân bản logic lỗi.

### Mô hình B — Gateway kết thúc xác thực, dùng token nội bộ

Gateway xác thực access token bên ngoài, sau đó **bỏ token bên ngoài** và cấp/lấy một token có scope, audience dành riêng cho upstream:

```text
Client --(external access token)--> Gateway
Gateway --(internal access token: aud=payment-service)--> Payment Service
Payment Service --(validate internal token)--> Business logic
```

Việc đổi token phải dùng cơ chế được hệ thống tin cậy và cấp phát cho mục đích cụ thể; không chỉ sửa payload JWT rồi ký lại tùy tiện. Khi cấu hình Gateway, thứ tự `RemoveRequestHeader=Authorization` và thao tác gắn token nội bộ là yếu tố quyết định kết quả: nếu xóa sau cùng, service sẽ không nhận token.

### Mô hình C — Gateway truyền danh tính đã xác minh qua header nội bộ

Gateway xóa mọi header danh tính do client gửi, xác thực token, rồi tạo `X-Verified-Subject` và có thể thêm scope/tenant **từ dữ liệu đã xác minh**. Service chỉ tin các header đó nếu có đường truyền an toàn và quy tắc ngăn gọi trực tiếp/giả mạo Gateway; với tác vụ nhạy cảm, nên dùng assertion được ký hoặc token nội bộ có audience rõ ràng.

```http
GET /api/orders/42 HTTP/1.1
Host: orders.internal
X-Verified-Subject: alice
X-Verified-Tenant: tenant-7
```

Hai giá trị trên phải do Gateway tạo sau xác thực. Không được copy từ `X-Authenticated-User` do client gửi hoặc lấy `sub` từ JWT mới chỉ decode mà chưa xác minh chữ ký và claims.

**Quyết định xóa `Authorization` phải đi theo mô hình đã chọn.** Xóa nó ở mọi route có thể gây `401` khi service đang đòi token; giữ nó ở mọi route có thể chuyển token đến service không cần biết và tăng phạm vi lộ bí mật.

## 6. Thứ tự xử lý request an toàn

Một pipeline khả thi:

1. **Nhận kết nối tại biên đáng tin:** dùng HTTPS; xác định proxy/hop nào có quyền đặt metadata kết nối. Chặn truy cập trực tiếp các upstream chỉ dựa vào Gateway.
2. **Chuẩn hóa và kiểm tra request:** xử lý header bất hợp lệ, trùng lặp nguy hiểm, `Forwarded`/`X-Forwarded-*` theo cấu hình tin cậy. Không lấy một giá trị header tùy ý làm bằng chứng.
3. **Xóa dữ liệu đặc quyền do client tự khai:** chẳng hạn `X-Authenticated-User`, `X-User-Roles`, `X-Tenant-Id` nếu đây là các header nội bộ. Bước này phải xảy ra **trước khi** gắn dữ liệu danh tính đã xác thực.
4. **Xác thực token:** trích Bearer access token, xác minh signature/introspection, issuer, audience, expiry và trạng thái token theo chính sách; phân biệt ID token, refresh token và access token.
5. **Phân quyền:** kiểm tra scope, route, tenant và quyền trên tài nguyên nếu Gateway đủ dữ liệu. Để service kiểm tra thêm điều kiện nghiệp vụ mà Gateway không thể biết.
6. **Chuẩn bị upstream request:** chọn relay external token, token nội bộ, hoặc identity assertion; xóa bí mật/header không cần dùng; áp dụng cấu hình riêng cho route.
7. **Gọi upstream an toàn:** chỉ kết nối service được định danh; dùng mTLS hoặc biện pháp bảo vệ tương đương theo độ nhạy.
8. **Lọc response trước khi trả client:** xóa header/debug/secret nội bộ theo allowlist hoặc denylist được kiểm soát, giữ những header giao thức cần thiết.

Thứ tự thực thi thực tế của **security filter**, **route filter**, **global filter** và reverse proxy phía trước Gateway phải được kiểm chứng bằng request end-to-end. Ví dụ một filter xóa `Authorization` **trước khi** bộ xác thực đọc token sẽ khiến xác thực thất bại; filter tạo `X-Verified-Subject` **trước khi** bộ lọc xóa header đó sẽ khiến upstream không nhận danh tính.

## 7. Ví dụ Spring Cloud Gateway

Giả sử Gateway dùng Spring Cloud Gateway và có route tới order-service. Route dưới đây loại các header danh tính client có thể tự đặt; access token **vẫn được chuyển tiếp**, phù hợp mô hình A (upstream xác thực token):

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders
          uri: http://order-service:8080
          predicates:
            - Path=/api/orders/**
          filters:
            - RemoveRequestHeader=X-Authenticated-User
            - RemoveRequestHeader=X-User-Id
            - RemoveRequestHeader=X-User-Roles
            - RemoveRequestHeader=X-Verified-Subject
            - RemoveResponseHeader=X-Internal-Debug
            - RemoveResponseHeader=X-Backend-Token
```

`RemoveRequestHeader` xử lý **request trên đường tới upstream**. `RemoveResponseHeader` xử lý **response gửi về client**. Cấu hình trên **không tự xác thực JWT**, không tự kiểm tra scope và không tự tạo lại `X-Verified-Subject`. Những việc đó phải được thực hiện bởi cấu hình bảo mật và các bộ lọc thích hợp.

Nếu route áp dụng mô hình B hoặc C, sau khi token bên ngoài đã được kiểm tra có thể xóa:

```yaml
# Chỉ dùng khi upstream KHÔNG cần external bearer token.
filters:
  - RemoveRequestHeader=Authorization
  - RemoveRequestHeader=Cookie
```

Đây là **đoạn minh họa cho một route khác**, không phải yêu cầu thêm vô điều kiện vào route đầu tiên. Nếu Gateway cần truyền internal access token, phải bảo đảm token đó được gắn vào request **sau khi** bỏ external token, và Gateway/Service đều xác minh đúng audience. Nếu dùng signed assertion/header danh tính, service phải được bảo vệ khỏi đường truy cập không đi qua Gateway.

Ở môi trường production, cần rà soát cả cấu hình global/default filters, thứ tự filter, đường đi qua load balancer/proxy, và phiên bản Spring Cloud Gateway đang chạy. Mọi rule liên quan đến headers cần được kiểm tra trên request thực tế đã tới upstream.

## 8. Ví dụ NGINX làm reverse proxy

NGINX có thể bỏ những header do client gửi trước khi gọi upstream. Trong `proxy_set_header`, giá trị rỗng làm header đó **không được gửi tới upstream**:

```nginx
location /api/ {
    proxy_pass http://orders_backend;

    proxy_set_header X-Authenticated-User "";
    proxy_set_header X-User-Id "";
    proxy_set_header X-User-Roles "";
    proxy_set_header X-Verified-Subject "";

    proxy_set_header Host $host;
}
```

Cấu hình này chỉ minh họa việc lọc header. **NGINX không tự xác minh access token chỉ vì có các dòng này.** Nếu dùng NGINX làm điểm xác thực, cần cấu hình bộ xác thực thực sự (hoặc dịch vụ xác thực bên ngoài); sau đó mới có thể truyền assertion được kiểm soát. Nếu muốn xóa `Authorization` khi gọi upstream, phải chủ động thêm `proxy_set_header Authorization "";` trong route phù hợp, sau khi bảo đảm upstream không dùng bearer token ngoài.

Khi triển khai reverse proxy trước một Gateway khác, cần thống nhất thành phần nào làm chủ `X-Forwarded-For`, `Host`, `Forwarded` và header chứng thực nội bộ. Không để hai tầng proxy lần lượt nối thêm các giá trị client tự khai rồi service tưởng toàn bộ chuỗi đó đáng tin.

## 9. Ví dụ tấn công và cách Gateway chặn

### Tình huống: privilege escalation qua header giả mạo

Một người dùng có access token hợp lệ với `sub=alice` và `scope=orders:read`. Client gửi:

```http
GET /api/orders/42 HTTP/1.1
Authorization: Bearer <access-token-cua-alice>
X-Authenticated-User: admin
X-User-Roles: ADMIN
X-Tenant-Id: tenant-cua-nguoi-khac
```

**Sai:** Gateway chỉ chuyển tiếp request, còn order-service lấy trực tiếp `X-User-Roles=ADMIN` để cho phép xem đơn hàng của tenant khác.

**Đúng:** Gateway bỏ các header tự khai. Nếu dùng mô hình A, order-service tự kiểm tra token và đối chiếu `sub`, tenant và quyền trên đơn hàng 42. Nếu dùng mô hình C, Gateway tạo giá trị danh tính đáng tin (chẳng hạn `alice`), và service chỉ nhận thông tin đó qua kênh an toàn được phép.

Ngay cả khi `scope=orders:read` hợp lệ, request vẫn phải bị từ chối nếu Alice không có quyền đọc đơn hàng 42. **Header stripping ngăn giả mạo ở HTTP boundary; nó không thay cho kiểm tra quyền đối tượng (object-level authorization).**

### Tình huống: access token được relay sai service

Một access token được cấp cho catalog-service có thể có chữ ký hợp lệ nhưng `aud=catalog-service`. Nếu Gateway chuyển token đó tới payment-service và payment-service chỉ kiểm tra chữ ký mà bỏ qua audience, token có nguy cơ bị chấp nhận sai phạm vi. Khắc phục bằng kiểm tra audience tại resource server và, khi cần, token exchange để có token đúng service đích.

### Tình huống: rò thông tin qua response

Upstream trả:

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Internal-Debug: node=payment-3; trace=abc123
X-Backend-Token: internal-secret
Cache-Control: no-store
```

Gateway cần bỏ `X-Internal-Debug` và `X-Backend-Token`; giữ `Cache-Control: no-store` và các header giao thức cần thiết. Nếu response có `Set-Cookie` hoặc `WWW-Authenticate`, phải áp dụng chính sách cụ thể thay vì xóa theo cảm tính: chúng có thể là một phần hợp lệ của cơ chế đăng nhập hoặc HTTP authentication.

## 10. Kiểm thử header stripping như một ranh giới bảo mật

Không dừng ở việc đọc cấu hình. Cần **quan sát headers thực tế mà upstream nhận được** và xác nhận hành vi xác thực/phân quyền. Với môi trường thử nghiệm, có thể đặt một echo service nội bộ tạm thời hoặc ghi log tên header đã được che giá trị bí mật.

Ví dụ gửi header giả mạo (token thử nghiệm phải hợp lệ và có quyền hạn thấp):

```bash
curl -i "https://api.example.com/api/orders/42" \
  -H "Authorization: Bearer ACCESS_TOKEN_FOR_ALICE" \
  -H "X-Authenticated-User: admin" \
  -H "X-User-Roles: ADMIN" \
  -H "X-Tenant-Id: other-tenant"
```

Các ca kiểm tra chính:

| Ca thử | Điều cần xác minh |
|---|---|
| Token hợp lệ + header vai trò giả mạo | Upstream không nhận giá trị client tự khai như danh tính đáng tin; quyền không tăng |
| Header cùng tên với cách viết hoa/thường khác nhau hoặc lặp lại | Quy tắc strip/validate vẫn có hiệu lực nhất quán |
| Access token sai `aud`/`iss`, hết hạn hoặc chữ ký sai | Từ chối xác thực theo chính sách, không gửi request như người dùng hợp lệ |
| ID token hoặc refresh token bị dùng thay access token | Không được chấp nhận làm access token của API |
| Mô hình A: bỏ nhầm `Authorization` | Kiểm thử phát hiện service bị `401`; sửa hợp đồng route |
| Mô hình B: thay external token bằng internal token | Upstream chỉ nhận token đúng audience/scope; không nhận token ngoài |
| Request thử truy cập trực tiếp upstream | Không thể bỏ qua Gateway để tự đặt header đặc quyền |
| Response có header debug/secret | Header bị loại trước khi rời Gateway, các header hợp lệ khác còn nguyên |
| Chuỗi `X-Forwarded-For` do client tự gắn | IP/scheme/host dùng cho quyết định an ninh chỉ lấy từ proxy tin cậy |

Phân biệt kết quả HTTP: `401 Unauthorized` thường biểu thị thiếu hoặc không chấp nhận thông tin xác thực; `403 Forbidden` thường biểu thị principal đã được xác thực nhưng không đủ quyền. Đừng tự động biến mọi lỗi upstream thành `401`: lỗi routing, DNS, service discovery hay mất kết nối cần được chẩn đoán riêng.

**Quan sát an toàn:** không log nguyên bearer token, cookie phiên hoặc assertion có thể dùng lại. Có thể log route ID, tên header bị strip, mã lý do từ chối và trace ID đã được kiểm soát. Nếu dùng echo service, chỉ triển khai trong môi trường kiểm thử được bảo vệ.

## 11. Các sai lầm thường gặp

- **Tin header tên có vẻ “internal”:** prefix `X-Internal-*` hay `X-Verified-*` không cung cấp tính xác thực. Nguồn tạo, đường truyền và cơ chế chống giả mạo mới quyết định độ tin cậy.
- **Xóa `Authorization` trên mọi route:** khiến downstream thiếu token hoặc phá vỡ flow token relay. Phải quyết định theo từng route và loại upstream.
- **Chỉ decode JWT rồi ghi `sub` xuống header:** payload JWT có thể đọc được trước khi xác minh; phải xác thực chữ ký, thuật toán, issuer, audience và thời hạn.
- **Strip ở sai vị trí:** filter xác thực không đọc được token, hoặc filter stripping xóa luôn header đã được Gateway tạo lại.
- **Quên đường đi tắt vào service:** attacker truy cập trực tiếp service và tự gửi header tin cậy; cần chặn bypass ở mạng và xác thực service.
- **Tin `X-Forwarded-For` từ Internet:** sai lệch client IP, audit log và chính sách rate limit/IP allowlist.
- **Xóa response header theo wildcard thiếu đánh giá:** có thể làm mất `Set-Cookie` hợp lệ, challenge `WWW-Authenticate` hoặc chính sách cache và bảo mật.
- **Chỉ kiểm tra scope mà bỏ quyền trên tài nguyên:** `orders:read` không có nghĩa được đọc đơn hàng của bất kỳ tenant nào.

## 12. Checklist trước khi triển khai

1. Xác định rõ **trust boundary**: client, proxy, Gateway, Authorization Server và từng upstream.
2. Liệt kê header nào **chỉ Gateway được phép đặt**, xóa mọi bản tương ứng từ phía không đáng tin.
3. Chọn mô hình **pass-through token**, **token exchange/internal token** hoặc **identity assertion**, mô tả audience/scope và trách nhiệm xác minh.
4. Rà soát thứ tự authentication, stripping, stamping và routing trên cấu hình thực tế.
5. Xử lý header trùng lặp, chữ hoa/thường, `Forwarded`/`X-Forwarded-*` và các proxy hop theo chính sách nhất quán.
6. Bảo vệ đường Gateway → service, ngăn bypass và không log token.
7. Thử request giả mạo và kiểm tra **headers upstream nhận** cùng kết quả `401`/`403`.
8. Lọc response chứa secret/debug theo hợp đồng; giữ những header cần cho giao thức.

**Nguyên tắc cốt lõi:** mọi header do client gửi đều là đầu vào chưa được tin cậy. Header stripping làm sạch đường truyền; danh tính và quyền chỉ được công nhận khi có bằng chứng xác thực hợp lệ, chính sách phân quyền đúng và ranh giới hệ thống được bảo vệ.

### Tài liệu chuẩn để đọc thêm

- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): ngữ nghĩa HTTP, field names và các thành phần giao thức.
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239): metadata chuyển tiếp qua proxy và ranh giới tin cậy.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): cách truyền bearer token và phản hồi xác thực.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): kiểm tra JWT và các dạng nhầm lẫn token.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): các thực hành giảm rủi ro trong OAuth 2.0.
