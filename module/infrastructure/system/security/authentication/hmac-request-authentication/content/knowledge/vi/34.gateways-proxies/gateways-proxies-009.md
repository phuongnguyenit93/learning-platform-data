# Trust gateway trong xác thực HMAC request qua gateway và proxy

## 1. Trust gateway là gì và vì sao cần thiết?

Trong một hệ thống API thực tế, request hiếm khi đi thẳng từ client đến Spring Boot service. Nó thường đi qua CDN, WAF, load balancer, API gateway, ingress hoặc reverse proxy. Những thành phần này có thể kết thúc TLS, định tuyến, viết lại path, thay Host, chuẩn hóa header, giải nén payload hoặc gắn thêm thông tin về người gọi.

Trong module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**, client ký HTTP request bằng HMAC với shared secret. Phía xác minh dựng lại **canonical request** từ method, URI, header và/hoặc body theo hợp đồng, kiểm tra chữ ký, timestamp/nonce chống replay và trạng thái credential. Khi đặt proxy/gateway vào giữa, xuất hiện câu hỏi quan trọng:

> Backend nên tin thông tin nào do gateway cung cấp, và làm sao chứng minh thông tin đó thật sự đến từ một gateway được phép?

**Trust gateway** là thiết kế và thực thi *ranh giới tin cậy* giữa các lớp mạng, gateway và ứng dụng. Không phải cứ request đi từ một IP nội bộ, có header `X-Authenticated-Client` hoặc qua một load balancer là request đã xác thực.

Một thiết kế đúng cần chứng minh:

1. Request ở lớp ngoài được xác thực bằng đúng HMAC/secret theo **canonical contract**.
2. Chỉ một **gateway được xác thực và được ủy quyền** mới có quyền đưa thông tin danh tính vào backend.
3. Header, URI, body và tenant context không thể bị client trực tiếp giả mạo hoặc bị proxy thay đổi mà không được phát hiện.
4. Backend không có đường bypass, direct ingress, worker route hoặc fallback nào tự động tin thông tin chưa được xác minh.
5. HMAC thành công chứng minh danh tính client, nhưng **phân quyền** với tenant/action/resource vẫn được đánh giá độc lập.
6. Thu hồi key, key rotation, nonce chống replay và các chính sách trust được thực thi nhất quán trên mọi gateway.

Chủ đề thuộc chương **Gateway và proxy**. Trọng tâm bài là *một gateway được tin theo điều kiện nào*, không đơn giản là cách thêm header forward.

## 2. Mô hình đe dọa: “header nội bộ” không tự mang tính tin cậy

Giả sử mạng có một API gateway và dịch vụ thanh toán:

~~~mermaid
flowchart LR
    C["Partner Client"] --> G["Public API Gateway"]
    G --> B["Payment Service"]
    B --> D[("Tenant-scoped Database")]
    A["Attacker hoặc workload nội bộ sai quyền"] -.-> B
    X["Client tự gắn X-Authenticated-Client"] -.-> G
~~~

Client hợp lệ `partner-a` ký request:

~~~http
POST /api/payments HTTP/1.1
Host: api.example.test
X-Key-Id: partner-a-k4
X-Tenant-Id: tenant-a
X-Timestamp: 2026-11-28T04:00:00Z
X-Nonce: 4f92a4c8-f06a-4edb-8d8c-d35df88403cb
X-Signature: <base64-hmac-sha256>
X-Authenticated-Client: platform-admin

{"paymentId":"pay-101","amount":250000}
~~~

`X-Authenticated-Client: platform-admin` là **dữ liệu không đáng tin** vì client tự gửi. Nếu gateway chuyển nguyên header đó xuống service, service có thể hiểu sai thành danh tính được xác thực, dù HMAC hoàn toàn không chứng minh `platform-admin`.

Một đường tấn công khác: service có thể bị gọi trực tiếp từ một pod, VM hoặc internal load balancer không đi qua gateway. Nếu backend chỉ kiểm tra “header `X-Authenticated-Client` có tồn tại”, kẻ tấn công không cần sở hữu bất kỳ shared secret HMAC nào.

Các tình huống phải nằm trong threat model:

| Đường tấn công | Nguyên nhân |
| --- | --- |
| Client tự gửi header dành cho gateway | Gateway không xóa trước khi tự thêm header |
| Gọi trực tiếp backend | Network policy/ingress cho phép bypass gateway |
| Pod nội bộ gửi header giả | Tin mạng nội bộ/IP mà không xác thực workload |
| Gateway A được phép gọi một service, nhưng gọi service B | Không ràng buộc identity với audience/đích được phép |
| Proxy rewrite path/Host/body | Canonical bytes tại verifier khác bytes client ký |
| Gateway xác thực nhưng backend chọn tenant từ header client | Confused deputy, thiếu phân quyền tenant |
| Gateway dùng cache trạng thái credential cũ | Key đã revoke nhưng vẫn được chấp nhận |
| Request replay qua gateway/region khác | Nonce store phân tán không nhất quán |
| Header duplicate, HTTP/2 → HTTP/1.1 | Các tầng parse khác nhau, có thể chọn giá trị trái ngược |
| Gateway nội bộ bị compromise | Attacker có khả năng tạo assertion hợp lệ của gateway |

Cần phân biệt hai chiều: **gateway xác minh client**, và **backend xác minh gateway**. Hai phép xác minh này dùng hai trust relationship khác nhau.

## 3. Phân chia trách nhiệm: client, gateway, service

| Thành phần | Thông tin nắm giữ | Trách nhiệm |
| --- | --- | --- |
| HMAC client | Key ID và shared secret của chính client | Tạo signature theo canonical contract, timestamp/nonce mới |
| API gateway | Chính sách route, verifier, credential registry access hoặc HMAC verification service | Từ chối request không hợp lệ, tạo danh tính đã xác thực, xóa header spoofed |
| Service/backend | Chính sách endpoint, tenant/resource/action; trust config cho gateway | Xác thực bằng chứng từ gateway hoặc tự verify HMAC; áp authorization |
| Credential registry | Key → principal/client/tenant, trạng thái, version, hiệu lực | Nguồn sự thật để xác định secret và vòng đời key |
| Replay store | Nonce đã dùng, namespace, TTL | Atomic insert-if-absent xuyên mọi verifier được phép nhận cùng key |
| Secret manager | Shared secret HMAC; có thể còn giữ key ký assertion nội bộ | Cấp quyền đọc/key riêng biệt, giám sát, thu hồi |
| Service mesh/mTLS | Workload identity giữa các hop | Xác thực kênh/peer, không tự cấp quyền nghiệp vụ |
| Policy/authorization service | Quyền theo principal, tenant, action, resource | Quyết định quyền tách biệt với kết quả HMAC |

Không nên trao cho gateway toàn bộ khả năng quyết định quyền nghiệp vụ chỉ vì nó là điểm xác thực. Gateway có thể kiểm tra policy cấp coarse-grained (endpoint/method/scope), còn service kiểm tra **resource-level authorization** và bảo vệ dữ liệu tenant ở storage.

### Hai câu hỏi kiểm toán

- **Ai được quyền tuyên bố principal này là `partner-a`?** Chỉ verifier tin cậy, sau khi HMAC và credential state hợp lệ.
- **Ai được quyền tuyên bố `partner-a` có quyền tạo payment trong `tenant-b`?** Policy/authorization có dữ liệu grant và ownership; một HMAC hợp lệ hoặc header từ gateway không tự chứng minh được quyền này.

## 4. Hai kiến trúc xác minh HMAC qua gateway

Có hai mô hình chính, mỗi mô hình có hợp đồng trust khác nhau.

### Phương án A — Backend tự xác minh HMAC

Gateway là thành phần định tuyến và bảo vệ lưu lượng, nhưng **service sở hữu quyết định HMAC cuối cùng**.

~~~mermaid
sequenceDiagram
    participant C as HMAC Client
    participant G as Gateway
    participant S as Backend Service
    participant R as Credential Registry
    participant N as Shared Nonce Store
    C->>G: Signed HTTP request
    G->>S: Forward signed request theo hợp đồng
    S->>R: Lookup đúng key ID, owner, state
    R-->>S: Credential + secret reference
    S->>S: Canonicalize request và verify HMAC
    S->>N: Check+set nonce nguyên tử
    N-->>S: Nonce mới
    S->>S: Authentication rồi authorization
    S-->>C: Response
~~~

**Ưu điểm:** backend không cần tin header `X-Authenticated-Client` như bằng chứng xác thực; mỗi service có thể chứng minh trực tiếp signature. **Đánh đổi:** gateway phải bảo toàn thông tin ký qua route rewrite, hệ thống có nhiều verifier và cần kiểm soát truy cập shared secret/nonce store cho nhiều service.

Điều kiện cần có:

- Hợp đồng quyết định **URI trước hay sau proxy rewrite** được ký.
- Server nhìn thấy đúng signed header và body bytes.
- Nếu cần original target, giá trị đó đến từ proxy tin cậy và không thể do client giả mạo.
- Nếu service có thể bị gọi trực tiếp, vẫn phải có kiểm soát mạng và authentication ở backend; HMAC không thay thế TLS.

### Phương án B — Gateway xác minh HMAC, backend tin assertion đã được chứng thực

Gateway xác minh HMAC rồi tạo **authentication assertion nội bộ** để service kiểm tra.

~~~mermaid
sequenceDiagram
    participant C as HMAC Client
    participant G as Gateway
    participant S as Backend Service
    participant P as Authorization Policy
    C->>G: HMAC signed request
    G->>G: Verify secret/state/signature/timestamp/nonce
    alt HMAC không hợp lệ
        G-->>C: 401 / theo hợp đồng
    else HMAC hợp lệ
        G->>G: Xóa header nội bộ giả mạo
        G->>G: Tạo assertion ký: principal, key, audience, target
        G->>S: mTLS + assertion + body được ràng buộc
        S->>S: Verify gateway identity + assertion
        S->>P: Check tenant/action/resource authorization
        P-->>S: Allow / deny
        S-->>C: Response theo policy
    end
~~~

**Ưu điểm:** tập trung quản trị HMAC, secret, replay và rotation tại gateway; service ít phụ thuộc vào canonicalization của client. **Đánh đổi:** gateway trở thành thành phần bảo mật đặc quyền. Backend phải kiểm tra **nguồn và tính toàn vẹn của assertion**, giới hạn đặc quyền của từng gateway và không tin bất kỳ header thuần văn bản nào từ client.

Cả hai phương án đều hợp lệ nếu threat model, trust configuration và kiểm thử tương ứng đầy đủ. **Không được trộn ngầm**: một số route tự verify HMAC, một số route chỉ đọc header gateway, trong khi người triển khai không biết route nào thuộc mô hình nào.

### Ma trận lựa chọn

| Câu hỏi | Verify tại backend | Verify tại gateway |
| --- | --- | --- |
| Ai giữ shared secret của client? | Backend/verifier hoặc secret service | Gateway/verifier trung tâm |
| Ai kiểm tra nonce? | Backend, store chung | Gateway, store chung |
| Backend có cần biết canonical request ngoài? | Có | Không nhất thiết, nếu assertion ràng buộc request đúng |
| Backend nhận danh tính bằng gì? | Authentication do backend tạo | mTLS peer + assertion nội bộ đã verify |
| Tấn công giả header nội bộ có nguy hiểm? | Không nếu backend bỏ qua header đó | Có nếu gateway/backend không bảo vệ trust boundary |
| Proxy rewrite ảnh hưởng thế nào? | Phải bảo toàn canonical bytes được ký | Gateway verify trước rewrite; backend phải biết request đã được ràng buộc vào assertion |
| Tránh bypass gateway | Backend vẫn tự verify HMAC, nhưng cần network control | **Bắt buộc**, backend không được chấp nhận assertion tự khai |

## 5. Định nghĩa trust boundary, không chỉ “mạng private”

Mạng private, VPC, Kubernetes cluster hoặc một CIDR allowlist **không tự chứng minh** peer là gateway được ủy quyền. Bên trong mạng còn có các workload khác, container bị xâm nhập, SSRF, endpoint debug hoặc đường tunnel.

Một trust boundary vững hơn có nhiều lớp:

1. **Network boundary:** service backend không có public ingress; hạn chế inbound bằng network policy/firewall tới gateway hoặc service mesh ingress đã phê duyệt.
2. **Transport identity:** gateway kết nối backend bằng **mTLS** hoặc kênh xác thực tương đương; backend xác minh chain chứng chỉ và workload identity cụ thể.
3. **Caller authorization:** backend kiểm tra gateway A được phép gọi service/route này hay không; cùng CA tin cậy chưa đủ.
4. **Application assertion:** principal, tenant, key ID và quyền mà gateway chuyển tiếp được bảo vệ bằng chữ ký/MAC hoặc kênh đã kiểm soát và có ngữ nghĩa chặt chẽ.
5. **Request binding:** assertion liên quan đến method, target, body digest và audience phù hợp với request mà service thực sự xử lý.
6. **Defense in depth:** backend áp authorization với action/resource/tenant, không chỉ `isAuthenticated`.

Lấy ví dụ một service mesh dùng workload identity `spiffe://example.internal/ns/edge/sa/api-gateway`. Backend có thể cho phép danh tính này thực hiện `POST /internal/payments` nhưng không cho phép workload của namespace khác tự truyền assertion. SPIFFE là một **ví dụ hình thức identity**, không phải giá trị mặc định của mọi hệ thống.

Nếu dùng mTLS tại sidecar, phải xác định **service có tin kết luận xác thực của sidecar không**, kết luận đó được chuyển tiếp qua kênh nào, và có đường truy cập bypass sidecar không. Một header do sidecar thiết lập chỉ đáng tin sau khi tất cả đường ingress không tin cậy bị chặn hoặc được làm sạch.

## 6. Header forwarded và header danh tính: tin theo nguồn, không tin theo tên

Những header sau thường xuất hiện trong môi trường proxy:

| Header | Ý nghĩa thường gặp | Độ tin cậy mặc định |
| --- | --- | --- |
| `Forwarded` | Thông tin `for`, `by`, `host`, `proto` | Không tin khi đến trực tiếp từ client |
| `X-Forwarded-For` | Chuỗi hop/client IP | Không dùng làm bằng chứng authentication |
| `X-Forwarded-Proto` | Scheme mà proxy thấy | Chỉ tin sau khi proxy đã xác thực và làm sạch |
| `X-Forwarded-Host` | Host bên ngoài | Chỉ dùng theo trust configuration |
| `X-Original-URI`, `X-Rewrite-URL` | URI trước rewrite | Có thể bị giả mạo; không tin trừ khi gateway tạo an toàn |
| `X-Authenticated-Client` | Identity do gateway tuyên bố | **Không** đáng tin nếu chỉ là header plaintext |
| `X-Authenticated-Tenant` | Tenant do gateway tuyên bố | Cần chứng cứ đã xác thực/được ủy quyền |
| `X-Gateway-Assertion` | Assertion nội bộ | Cần xác minh signature, issuer, audience, thời hạn, request binding |

**Tên header không tạo quyền.** Client có thể tự thêm các header mang tên “internal”, “trusted”, “authenticated”, “original”. Gateway phải **xóa toàn bộ header có thể dùng để giả mạo danh tính** do client gửi trước khi tự đặt giá trị mới.

Quy tắc ở ingress:

~~~text
1. Nhận request từ client như dữ liệu không tin cậy.
2. Từ chối header mơ hồ/trùng theo hợp đồng HMAC.
3. Xóa Forwarded/X-Forwarded-* không đáng tin theo trust policy.
4. Xóa X-Authenticated-*, X-Internal-*, X-Gateway-Assertion đầu vào.
5. Verify HMAC trên canonical bytes theo contract.
6. Chỉ sau VERIFY PASS mới tạo request context/assertion nội bộ.
7. Gửi qua mTLS hoặc kênh đã xác thực tới backend được phép.
~~~

Các bước trên là **pseudocode chính sách**, không phải cú pháp cấu hình cho một gateway cụ thể. Tùy sản phẩm, gateway có thể dùng danh sách header chính xác thay vì wildcard; điều quan trọng là tất cả tên có ý nghĩa bảo mật phải nằm trong **allowlist và test spoofing**.

### Duplicate header và khác biệt chuẩn hóa

Khi nhận hai header `X-Tenant-Id`, một proxy có thể ghép thành `tenant-a,tenant-b`, trong khi backend lấy giá trị đầu hoặc cuối. HTTP/2 yêu cầu tên header lowercase, còn HTTP/1.1 có thể viết hoa/thường; những cách parse không đồng nhất tạo rủi ro signature confusion.

Hợp đồng ký cần xác định cách xử lý **duplicate signed headers**; với header định danh như `X-Key-Id`, `X-Tenant-Id`, `X-Signature`, cách an toàn là **chỉ chấp nhận đúng một giá trị chuẩn**. Cần kiểm soát ambiguous `Content-Length`/`Transfer-Encoding` và các dạng request smuggling tại proxy, vì hai tầng không được phép hiểu ranh giới request khác nhau.

## 7. Client IP, Forwarded chain và X-Forwarded-For không phải credential

Có hệ thống dùng `X-Forwarded-For` để chọn tenant hoặc cấp quyền. Đây là sai lầm.

Ví dụ:

~~~http
X-Forwarded-For: 203.0.113.123, 10.10.0.8
~~~

Chuỗi này có thể chứa IP do client tự khai từ trước gateway, địa chỉ proxy hoặc nhiều hop. Không có quy tắc chung nào cho phép “lấy IP bên trái nhất” rồi coi đó là danh tính xác thực.

Nếu cần client IP để **rate limit, audit hoặc fraud detection**, hãy:

- Chỉ lấy từ cơ chế forwarded header của **proxy/hop đã được nhận diện là tin cậy**;
- Cấu hình danh sách trusted proxy theo địa chỉ/workload identity phù hợp, số hop và cách sanitize;
- Không để `ForwardedHeaderFilter` hoặc cấu hình forward-headers tự biến một header client gửi thành canonical host/scheme đáng tin;
- Phân biệt client IP suy luận từ proxy với **principal đã xác thực HMAC**.

Địa chỉ IP không thay thế key ID, HMAC signature hoặc authorization. Với NAT/mobile networks, cùng IP có thể chứa nhiều client; với SSRF hoặc proxy bị compromise, IP có thể đánh lừa chính sách đơn giản.

## 8. Canonical request qua gateway: điều gì phải giữ nguyên?

Giả sử client ký:

~~~http
POST /public/v1/payments?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-a
X-Key-Id: partner-a-k4
X-Tenant-Id: tenant-a
X-Timestamp: 2026-11-28T04:00:00Z
X-Nonce: 9b74b76a-ae6b-4514-a65f-1fd9cb174dcb
X-Signature: <base64-hmac-sha256>

{"paymentId":"pay-101","amount":250000}
~~~

Một **hợp đồng minh họa** `HMAC-REQUEST-V1` dùng các dòng UTF-8:

~~~text
HMAC-REQUEST-V1
POST
/public/v1/payments?currency=VND
application/json
partner-a
partner-a-k4
tenant-a
2026-11-28T04:00:00Z
9b74b76a-ae6b-4514-a65f-1fd9cb174dcb
<sha256-hex-cua-raw-body-bytes>
~~~

Đây chỉ là cấu trúc, **không** phải vector chữ ký thật. Phần digest phải là SHA-256 thực của body bytes; thứ tự trường, ký tự `LF` và có/không có newline cuối phải được đặc tả chính xác.

Gateway có thể đổi path:

~~~text
External target: /public/v1/payments?currency=VND
Internal target: /internal/payments?currency=VND
~~~

Nếu backend tự verify HMAC nhưng dựng chuỗi ký từ internal target, signature sẽ sai. Đừng “chữa” bằng cách tin header `X-Original-URI` do client gửi.

### Cách xử lý hợp lệ

**Trường hợp gateway verify trước rewrite:** gateway xác minh external target với HMAC client; sau đó tạo assertion nội bộ có binding với internal request. Backend không cần tái xác minh HMAC client, nhưng phải xác minh assertion và đường truyền.

**Trường hợp backend verify:** gateway cần bảo toàn đủ thông tin external target theo trust contract; backend lấy external target từ metadata **chỉ do gateway tạo, qua kênh đã xác thực**, hoặc hợp đồng định nghĩa request mà backend nhận là canonical target. Điều này bắt buộc kiểm thử toàn tuyến.

Các dạng transformation ảnh hưởng chữ ký:

| Transformation | Điều kiện an toàn |
| --- | --- |
| Rewrite path/context path | Điểm verify biết chính xác target của hợp đồng |
| Sắp xếp lại query string | Quy tắc canonical query định nghĩa rõ; không dựa ngẫu nhiên proxy |
| Percent decode / normalize dot segments | Không gây signature confusion hoặc route sai |
| Đổi Host, scheme, port | Nếu được ký, phải bảo toàn giá trị gốc tin cậy hoặc verify trước rewrite |
| Chuyển HTTP/1.1 ↔ HTTP/2 | Signed header canonicalization nhất quán, từ chối ambiguity |
| Giải nén/nén body | Xác định ký bytes nào; không tự biến đổi sau verify mà không ràng buộc |
| Chỉnh JSON whitespace/field order | Body digest sẽ thay đổi nếu ký raw bytes |
| Thêm/xóa Content-Type | Nếu Content-Type được ký, không thay đổi sau verify |
| Duplicate headers | Từ chối hoặc xử lý theo hợp đồng duy nhất |

Đừng dùng việc xác minh HMAC bằng client secret tại gateway làm lý do để **bỏ qua tính toàn vẹn phần dữ liệu truyền xuống backend**. Kênh nội bộ cần bảo vệ, và assertion phải gắn với request mà backend xử lý.

## 9. Thiết kế authentication assertion nội bộ

Nếu chọn mô hình gateway xác minh HMAC, backend có thể nhận một assertion được ký theo JWS/JWT, hoặc một **giao thức nội bộ khác có xác thực và chống phát lại**. Không nhất thiết mọi hệ thống phải dùng JWT; điều quan trọng là tiêu chí kiểm tra.

Một payload minh họa:

~~~json
{
  "iss": "trusted-api-gateway",
  "sub": "partner-a",
  "aud": "payment-service",
  "iat": 1795838400,
  "nbf": 1795838400,
  "exp": 1795838430,
  "jti": "gw-assertion-6ae3b7",
  "client_id": "partner-a",
  "credential_id": "partner-a-k4",
  "owner_tenant": "tenant-a",
  "target_tenant": "tenant-a",
  "original_method": "POST",
  "original_target": "/public/v1/payments?currency=VND",
  "internal_method": "POST",
  "internal_target": "/internal/payments?currency=VND",
  "body_sha256": "<sha256-hex>",
  "authentication_method": "HMAC-SHA256",
  "contract": "HMAC-REQUEST-V1"
}
~~~

**Các timestamp Unix và ID trên chỉ minh họa cấu trúc**, không được sử dụng như assertion hợp lệ ngoài một test vector có chữ ký và thời gian được dựng phù hợp. Những trường đã liệt kê là gợi ý kiến trúc, không phải claim chuẩn bắt buộc của JWT hay Spring Security.

### Các kiểm tra bắt buộc ở backend

1. Assertion có **chữ ký hợp lệ** hoặc được truyền bằng một kênh có ngữ nghĩa xác thực tương đương; chỉ tin thuật toán và key từ cấu hình cho phép, không tin `alg` do token tự chỉ định tùy ý.
2. `iss` khớp **gateway được phép**, `aud` khớp chính xác service/route tiêu thụ.
3. `exp`, `nbf`, `iat` hợp lý theo đồng hồ server và clock skew được định nghĩa; assertion có TTL ngắn.
4. `jti` được chống phát lại nếu assertion có thể bị lấy lại/phát lại trong mô hình đe dọa (hoặc dùng cơ chế ràng buộc channel/request tương đương).
5. Peer gửi thực sự là **gateway có quyền**, ví dụ mTLS identity nằm trong allowlist; possession một bearer assertion không tự chứng minh workload gửi là gateway.
6. Method/internal target được ràng buộc với HTTP request **backend nhận**; external target/body digest khớp quyết định gateway đã verify.
7. Principal/tenant/credential được lấy từ claim đã được verify, **không** từ header request gốc.
8. Service kiểm tra quyền theo target tenant, action và resource; assertion xác thực không biến thành một role toàn quyền.
9. Ký/thu hồi key assertion của gateway được quản lý **tách biệt** khỏi shared secret HMAC của client.
10. Không log token assertion nguyên vẹn; token có thể chứa định danh và bằng chứng bearer nhạy cảm.

Nếu body được phép thay đổi ở gateway sau khi verify HMAC, phải định nghĩa một **bằng chứng toàn vẹn mới cho body downstream** (ví dụ digest body trong assertion hoặc chữ ký request nội bộ). Backend tính digest trên bytes thực nhận rồi so với claim đã xác minh. Nếu assertion chỉ có principal mà không ràng buộc request, một assertion bị đánh cắp hoặc bị tráo có thể được dùng cho target khác.

## 10. Ví dụ Java 17: xác minh ràng buộc request ở backend

Đoạn sau minh họa bước **đối chiếu claims đã được xác thực** với request thực tế trong một ứng dụng Spring MVC hoặc service nội bộ. Nó giả định **bước xác minh chữ ký assertion, issuer, audience, key, thời hạn, mTLS peer và replay đã hoàn tất trước đó**. Không được tạo object `VerifiedGatewayAssertion` trực tiếp từ header JSON do client gửi.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Objects;

record VerifiedGatewayAssertion(
    String issuer,
    String audience,
    String principalId,
    String ownerTenant,
    String targetTenant,
    String credentialId,
    String method,
    String internalTarget,
    String bodySha256
) {}

record InternalHttpRequest(
    String method,
    String canonicalInternalTarget,
    byte[] bodyBytes
) {}

final class GatewayRequestBinding {

    static void verify(
            VerifiedGatewayAssertion assertion,
            InternalHttpRequest request,
            String expectedIssuer,
            String expectedAudience) {

        if (!Objects.equals(assertion.issuer(), expectedIssuer)
                || !Objects.equals(assertion.audience(), expectedAudience)
                || !Objects.equals(assertion.method(), request.method())
                || !Objects.equals(
                    assertion.internalTarget(),
                    request.canonicalInternalTarget())) {
            throw new SecurityException("gateway_assertion_invalid");
        }

        String actualBodyHash = sha256Hex(request.bodyBytes());
        if (!MessageDigest.isEqual(
                assertion.bodySha256()
                    .getBytes(StandardCharsets.US_ASCII),
                actualBodyHash.getBytes(StandardCharsets.US_ASCII))) {
            throw new SecurityException("gateway_assertion_invalid");
        }

        if (assertion.principalId() == null
                || assertion.principalId().isBlank()
                || assertion.targetTenant() == null
                || assertion.targetTenant().isBlank()) {
            throw new SecurityException("gateway_assertion_invalid");
        }
    }

    private static String sha256Hex(byte[] input) {
        try {
            return HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(input));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(
                "SHA-256 unavailable", ex);
        }
    }
}
~~~

Đây là **điều kiện bổ sung sau cryptographic verification**, không phải verifier JWT/HMAC assertion độc lập. Một object record Java có constructor từ bên ngoài không tự được bảo vệ; ứng dụng phải chỉ tạo `VerifiedGatewayAssertion` trong **thành phần verifier được kiểm soát**, sau khi đã xác minh chữ ký và các tiêu chí ở phần trước.

Trong production, việc xác minh phải thực hiện trên **bytes thực tế** và canonical internal target theo hợp đồng đã phê duyệt; không cho người gọi chọn tùy ý `canonicalInternalTarget`. Nếu backend xử lý streaming body, cần cơ chế stage/verify trước side effect tương đương, không vội cho controller ghi dữ liệu khi chưa đối chiếu digest.

Ví dụ này kiểm tra body digest sau assertion; nó không tự xác nhận quyền tenant. Phần authorization phải được chạy riêng sau đó.

## 11. Spring Security: không biến header vào SecurityContext quá sớm

Một lỗi phổ biến:

~~~java
// SAI: chưa xác minh nguồn header và assertion.
String clientId = request.getHeader("X-Authenticated-Client");
Authentication auth =
    UsernamePasswordAuthenticationToken.authenticated(
        clientId, null, List.of());
SecurityContextHolder.getContext().setAuthentication(auth);
~~~

Nếu client có thể gọi backend hoặc làm gateway chuyển tiếp header giả, code này tự tạo principal tin cậy từ dữ liệu không đáng tin.

Với Spring Security 6 theo Servlet, nên dùng một `AuthenticationProvider`/service riêng để xác minh **gateway identity và assertion**. Một adapter/filter chỉ xây token *chưa xác thực*, đưa vào `AuthenticationManager` rồi mới gắn kết quả tin cậy vào `SecurityContext`. Với WebFlux, sử dụng `ReactiveAuthenticationManager`, `SecurityWebFilterChain` và Reactor Context thay vì thread-local Servlet.

Ví dụ điều kiện đặt vào filter hoặc provider:

~~~text
if request bypasses approved gateway:
    reject
if mTLS peer identity not authorized for this backend:
    reject
if internal assertion is missing/duplicated/malformed:
    reject
if assertion signature, issuer, audience, time or replay invalid:
    reject
if method, route or body binding mismatches:
    reject
authentication = trusted principal from validated assertion
continue to tenant/resource authorization
~~~

Không gán `ROLE_ADMIN` hoặc `ROLE_SUPERUSER` cho mọi principal từ gateway. Authority phải đến từ chính sách server có kiểm soát. Nếu backend nhận role/scope từ assertion, cần xác minh gateway đó có quyền cấp **chính xác loại scope/role đó**, không chỉ chữ ký token.

### Cần một chain riêng cho hop nội bộ?

Có thể tách đường `/internal/**` thành chain yêu cầu gateway identity/assertion, trong khi `/public/**` sử dụng HMAC trực tiếp hoặc từ chối. Tuy nhiên, các đường match/ưu tiên của `SecurityFilterChain` phải được kiểm thử; chain matcher rộng hơn không được đứng trước chain nội bộ rồi cho bypass xác thực.

Một endpoint health check được mở công khai không có nghĩa toàn bộ `/internal/**` được mở. Các lối gọi trực tiếp bởi job, debug route, actuator, sidecar hoặc test harness phải được liệt kê riêng trong threat model.

## 12. Quy tắc gateway thực thi trước khi phát hành assertion

Một thuật toán kiểm soát có thể viết dưới dạng:

~~~text
RECEIVE request
  |
  +-- validate transport, route, body size, header shape
  |
  +-- strip untrusted identity/forwarded/assertion headers
  |
  +-- find credential by exact keyId; verify client/key/tenant state
  |
  +-- canonicalize original request under HMAC-REQUEST-V1
  |
  +-- verify HMAC using exact key secret
  |
  +-- check server timestamp window
  |
  +-- atomic register nonce in shared replay store
  |
  +-- determine authenticated client + owner tenant
  |
  +-- bind requested target tenant to signed request
  |
  +-- construct trusted internal route and digest of forwarded body
  |
  +-- mint short-lived assertion with issuer, aud, method,
  |   internal target, body hash, identity, jti, time
  |
  +-- connect to authorized backend over mTLS
  |
  +-- send body and assertion; backend revalidates claims + rights
~~~

Thứ tự có thể được điều chỉnh để tối ưu loại bỏ request lỗi, nhưng **không có đường trả thành công trước khi toàn bộ điều kiện bảo mật tương ứng hoàn tất**. Đặc biệt không “chấp nhận tạm” khi registry, secret manager hoặc replay store không khả dụng.

Nếu gateway đã ghi nonce nhưng backend lỗi trước khi xử lý nghiệp vụ, client retry **y nguyên HMAC/timestamp/nonce** có thể bị xem là replay. Hệ thống cần thiết kế **idempotency** và chính sách retry riêng; không bỏ chống replay để xử lý lỗi mạng. Một request tạo thanh toán cần idempotency key và nghiệp vụ giao dịch rõ ràng.

## 13. Chống replay ở cả hai ranh giới

Có ít nhất hai lớp cần đánh giá replay:

**Lớp client → gateway:** HMAC signature có thể được phát lại trong cửa sổ timestamp nếu không lưu nonce. Dùng replay store nguyên tử, ví dụ khóa `(credentialId, nonce)`, TTL bao phủ toàn bộ khoảng thời gian timestamp còn được phép. Store phải chia sẻ trên mọi gateway/region nhận request cùng credential hoặc phân vùng theo quy tắc rõ ràng mà không cho cùng chữ ký được phát lại qua vùng khác.

**Lớp gateway → backend:** một assertion dạng bearer có thể bị lấy lại từ log hoặc một workload bị xâm nhập. Chữ ký và `exp` chưa tự chặn phát lại trong TTL. Theo threat model, cần `jti` replay protection, ràng buộc token với kênh/mTLS peer, method/target/body digest và audience, hoặc giải pháp tương đương.

| Trường hợp | Cách kiểm soát |
| --- | --- |
| Request HMAC gửi lại tới gateway khác | Shared nonce store + atomic check |
| Header assertion bị copy sang một request khác | Method/target/body binding và audience |
| Assertion bị gửi đến service khác | `aud` và gateway route permission |
| Assertion cũ sau rotation key nội bộ | Kiểm tra key version, trusted signing keys, expiry |
| Assertion từ workload không phải gateway | mTLS identity/service authorization |
| Assertion thiếu `jti` khi hợp đồng yêu cầu replay protection | Từ chối |
| Replay store không đọc/ghi được | Fail closed theo mức bảo đảm đã công bố |

Hai lớp replay có **namespace và đối tượng khác nhau**. Không dùng nonce HMAC client thay thế cho `jti` assertion nội bộ trừ khi giao thức định nghĩa rõ cách liên kết và tính duy nhất; mỗi lớp phải bảo vệ đúng trust boundary của mình.

## 14. Key rotation: secret của client khác key của gateway

Một hệ thống có **ít nhất hai vòng đời khóa**:

| Nhóm key | Bên sở hữu | Dùng để làm gì? | Rotation |
| --- | --- | --- | --- |
| HMAC shared secret của client | Client và verifier/gateway | Xác minh request từ client | Key ID/version, ACTIVE/REVOKED, thời hạn, overlap có kiểm soát |
| Gateway assertion signing key | Gateway/identity platform | Chứng thực assertion nội bộ | `kid`, trust store/JWKS hoặc distribution tương đương, rollover/revoke |
| mTLS certificate/private key | Gateway/workload identity | Chứng thực peer/kênh | Certificate lifecycle, CA/trust roots, CRL/OCSP theo mô hình hoặc lifetime ngắn |
| Service authorization policy key/config | Policy platform | Giới hạn authority, tenant, service audience | Version/publish/invalidate, audit |

Không tái sử dụng **shared secret HMAC của client** để ký assertion gateway. Client không được có khả năng tự tạo token nội bộ giả mạo gateway.

Khi `partner-a-k3` bị REVOKED, request khai K3 phải bị chặn dù HMAC tính bằng K3 đúng. Khi ký assertion gateway được rotate, backend chỉ chấp nhận key/issuer được cấu hình và không vô hạn giữ key cũ. **Key overlap** khi rotation cần ranh giới thời gian rõ ràng; `kid` không tự chứng minh key đáng tin.

### Cache trạng thái

Gateway có thể cache credential hoặc client state để giảm latency. Nếu key bị thu hồi ở nguồn nhưng gateway cache ACTIVE thêm 60 giây, trong cửa sổ đó vẫn có nguy cơ chấp nhận request mới. Event bất đồng bộ và TTL đơn thuần **không chứng minh thu hồi tức thì**.

Nếu yêu cầu là “mọi request đến sau commit REVOKED đều bị chặn”, cần cơ chế đọc đủ mới, invalidation mạnh kèm kiểm chứng revision hoặc fail closed khi không thể chứng minh freshness. Tương tự với việc thu hồi gateway assertion signing key hoặc mTLS identity: backend phải cập nhật trust configuration theo cam kết.

## 15. Multi-tenant: trust gateway không đồng nghĩa trust quyền

Giả sử gateway xác minh rằng `partner-a` sở hữu HMAC key K4. Request đã ký có `X-Tenant-Id: tenant-b`. Kể cả gateway tạo assertion mang `target_tenant = tenant-b`, **nó vẫn cần kiểm tra xem partner-a có quyền thao tác tenant-b không**; nếu không, backend phải từ chối theo policy.

Các thông tin cần phân biệt:

- **Credential owner tenant:** tenant đăng ký key; được registry tin cậy xác định.
- **Requested target tenant:** claim trong request client đã được ràng buộc vào HMAC, nhưng không tự mang quyền.
- **Effective tenant:** tenant đã vượt qua authorization; backend dùng nó trong query/database scope.
- **Resource owner tenant:** tenant thật của resource đang được đọc/ghi.

Một query đúng phải scope theo effective tenant đã qua policy:

~~~sql
SELECT payment_id, tenant_id, amount
FROM payments
WHERE tenant_id = :effective_tenant
  AND payment_id = :payment_id;
~~~

Nếu service lấy `tenantId` trực tiếp từ header gốc/JSON body rồi chọn database, gateway xác thực HMAC thành công cũng không ngăn được cross-tenant access. Với delegated grants, authorization phải kiểm tra principal + target tenant + action + resource + hiệu lực grant. Gateway có thể cấp coarse-grained claims, nhưng service vẫn chịu trách nhiệm kiểm soát quyền dữ liệu thực.

## 16. TLS, certificate và các phương án tin gateway

### TLS từ client đến edge

TLS bảo vệ giao tiếp client → edge (tính bí mật, toàn vẹn và chứng thực server khi cấu hình đúng). HMAC chứng minh người gọi sở hữu shared secret và ràng buộc request; hai cơ chế **bổ sung**, không thay thế nhau. HMAC không mã hóa body, nên vẫn cần HTTPS.

### mTLS từ gateway đến backend

mTLS cung cấp xác thực **hai chiều** ở mức kết nối. Backend cần kiểm tra identity của gateway, không chỉ “certificate được CA nào đó ký”. Nếu CA có thể cấp certificate cho nhiều workload, phải kiểm tra SAN/SPIFFE ID hoặc ràng buộc identity cụ thể và policy cho từng service.

Định nghĩa quyền tối thiểu:

~~~text
allow:
  peer_identity: spiffe://example.internal/ns/edge/sa/api-gateway
  destination: payment-service
  methods: [POST, GET]
  paths: [/internal/payments, /internal/payments/*]
  require_assertion: true
deny:
  all_other_peer_identities: true
~~~

Đây là **policy minh họa**, không phải YAML sẵn dùng cho Istio, Envoy hay Spring Security. Nhà cung cấp service mesh có thể sử dụng cú pháp riêng; không được copy policy trên mà cho rằng đã thực thi.

### Chỉ dùng mTLS, có cần JWT assertion không?

Có thể thiết kế một giao thức **chỉ tin vào mTLS và một kênh header đã được khóa chặt** nếu gateway duy nhất, mTLS identity được kiểm tra tại backend, đường bypass bị chặn, không có bên nào khác được phép phát header và header được tạo lại một cách kiểm soát. Tuy nhiên:

- mTLS chứng thực **peer connection**, không tự nói client bên ngoài là ai.
- Header truyền danh tính phải gắn với quyết định HMAC đã được gateway thực hiện.
- Nếu có nhiều hop, forwarding hoặc hàng đợi, signed assertion thường dễ kiểm chứng nguồn gốc/audience/thời hạn hơn header plaintext.
- Với threat model có proxy/gateway bị compromise, cả mTLS lẫn signed assertion do gateway đó tạo không đủ ngăn việc giả danh; cần hạn chế đặc quyền, phân vùng khóa và giám sát.

Không có công nghệ duy nhất bảo đảm “trust gateway” trong mọi kiến trúc; điều quan trọng là **chuỗi chứng cứ từ client đến service** không bị đứt.

## 17. Failure mode: gateway không đáng tin hoặc không thể kiểm tra

Một thành phần bảo mật phải có **quy tắc fail closed**. Một số ví dụ:

| Sự cố | Quy tắc an toàn |
| --- | --- |
| Không có assertion bắt buộc | Từ chối, không tin header client |
| Chữ ký assertion sai | Từ chối, không thử “guest principal” |
| Gateway certificate/identity không được phép | Từ chối ngay ở trust boundary |
| `aud` không khớp service | Từ chối, không tự chuyển aud |
| `exp` hết hạn hoặc `nbf` ở tương lai ngoài skew | Từ chối |
| Body hash khác assertion | Từ chối, không cho controller xử lý |
| Client HMAC signature sai | 401 hoặc lỗi xác thực theo contract |
| Key client đã REVOKED | Từ chối dù chữ ký đúng |
| Nonce client đã dùng | Từ chối replay |
| Auth registry/vault/nonce store không khả dụng | Không chấp nhận request khi thiếu chứng cứ |
| Backend authorization service mất kết nối | Không mặc định allow; fail closed theo policy |
| Gateway bị xâm nhập | Thu hồi gateway identity/key, cô lập, điều tra và rotate |

**HTTP status** nên phản ánh loại lỗi: 401 cho request client không đạt authentication theo API; 403 cho principal hợp lệ nhưng thiếu quyền; 413 cho body lớn; 503 cho phụ trợ xác thực/authorization không khả dụng theo policy. Khi service từ chối assertion nội bộ, backend có thể trả 401/403 cho kết nối gateway rồi gateway ánh xạ an toàn ra public API. Không phơi chi tiết trust-store, certificate SAN hoặc key version nội bộ cho client.

Bất kể status nào, **không thực thi nghiệp vụ** khi chứng cứ xác thực/ủy quyền bắt buộc chưa đủ.

## 18. Kiểm thử Trust gateway từ client đến backend

Một test chỉ gọi `Mac.doFinal(...)` và thấy HMAC đúng **chưa** kiểm tra trust gateway. Phải thực hiện cả unit, contract, integration, E2E và fault injection.

### Ma trận test

| ID | Trường hợp | Kỳ vọng |
| --- | --- | --- |
| GW-01 | Client A ký HMAC đúng, trạng thái ACTIVE, gateway trusted | Request qua gateway; backend xác nhận principal A |
| GW-02 | Client gửi `X-Authenticated-Client: admin` | Gateway xóa giá trị ngoài; backend không nhận admin |
| GW-03 | Client gửi `X-Gateway-Assertion` giả | Gateway xóa; backend không dùng assertion client |
| GW-04 | Gọi trực tiếp backend từ Internet | Không có route hoặc bị từ chối |
| GW-05 | Pod nội bộ không phải gateway gửi header identity | Bị mTLS/policy từ chối |
| GW-06 | mTLS gateway hợp lệ nhưng assertion signature sai | Bị từ chối |
| GW-07 | Assertion ký đúng nhưng `aud` của service khác | Bị từ chối |
| GW-08 | Assertion hết hạn hoặc `nbf` sai | Bị từ chối |
| GW-09 | Tráo body sau khi gateway verify | Backend thấy digest mismatch |
| GW-10 | Đổi method/route nội bộ nhưng giữ assertion | Backend thấy binding mismatch |
| GW-11 | Assertion `jti` phát lại | Bị từ chối nếu policy yêu cầu anti-replay |
| GW-12 | Cùng HMAC nonce tới hai gateway | Chỉ request đầu được nhận ở shared nonce store |
| GW-13 | Key client K3 REVOKED nhưng gateway cache ACTIVE cũ | Bị chặn theo cam kết freshness; không gọi là tức thời nếu TTL chưa đủ |
| GW-14 | Key client K4 ACTIVE, chữ ký tính bằng K3 | Không fallback secret, HMAC sai |
| GW-15 | Client A tự ký request tenant B, không có grant | HMAC có thể đúng; authorization phải từ chối |
| GW-16 | Gateway rewrite `/public` → `/internal` | Canonical contract vẫn đúng, assertion bind target mới |
| GW-17 | Client giả `X-Original-URI` | Không thay đổi canonical target đáng tin |
| GW-18 | Hai `X-Key-Id`/hai `X-Tenant-Id` | Từ chối mơ hồ |
| GW-19 | HTTP/2 → HTTP/1.1 với duplicated signed header | Không có parse disagreement |
| GW-20 | Body gzip bị thay đổi sau verify | Phát hiện mismatch hoặc xử lý theo hợp đồng rõ |
| GW-21 | Registry/secret manager/nonce store lỗi | Fail closed, không trả kết quả nghiệp vụ |
| GW-22 | Gateway signing key rotate | Backend nhận key hợp lệ trong cửa sổ, từ chối key đã revoke |
| GW-23 | Gateway A cố gọi route chỉ gateway B được phép | Service từ chối dù certificate trust CA |
| GW-24 | Backend nhận assertion từ gateway nhưng thiếu quyền resource | Authorization từ chối, không đọc dữ liệu trái phép |
| GW-25 | Cùng resource ID ở hai tenant | Query/backend chỉ dùng effective tenant đã được phép |
| GW-26 | Request body vượt limit | 413 trước khi buffer không giới hạn |
| GW-27 | Response lỗi do gateway tạo | Không lộ secret/canonical bytes; status và headers nhất quán |
| GW-28 | Direct access qua internal load balancer/sidecar/health route | Không bypass trust policy |
| GW-29 | Gateway mất event revocation trong lúc cache stale | Có cơ chế kiểm tra revision/fail closed đúng cam kết |
| GW-30 | Header internal trùng, chữ hoa/thường khác nhau | Không bỏ sót header spoofed |

Với test kiểm soát mạng, không chỉ kiểm tra `403`: xác nhận **backend không có side effect** và không trả dữ liệu tenant khác. Với assertion test, cần thay từng claim một cách độc lập rồi ký lại bằng **key test được cấp đúng phạm vi** hoặc tạo token sai signature để phân biệt lỗi cryptographic và lỗi policy.

### Test kỹ thuật ở backend cho request binding

Ví dụ khung JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;
import java.nio.charset.StandardCharsets;

class GatewayRequestBindingTest {

    @Test
    void rejectsTamperedMethodEvenWithClaimsPreviouslyVerified() {
        byte[] body = "{\"amount\":100}".getBytes(StandardCharsets.UTF_8);

        // Fixture chỉ được tạo từ trusted assertion verifier
        // trong application thực; constructor ở test minh họa.
        VerifiedGatewayAssertion proof = new VerifiedGatewayAssertion(
            "trusted-api-gateway",
            "payment-service",
            "partner-a",
            "tenant-a",
            "tenant-a",
            "partner-a-k4",
            "POST",
            "/internal/payments",
            "sample-digest-to-replace-with-real-sha256"
        );

        InternalHttpRequest request = new InternalHttpRequest(
            "DELETE",
            "/internal/payments",
            body
        );

        assertThrows(SecurityException.class,
            () -> GatewayRequestBinding.verify(
                proof, request, "trusted-api-gateway",
                "payment-service"));
    }
}
~~~

Đây là **test khung minh họa điều kiện method-binding**: digest ở fixture cố ý là placeholder, nhưng assertion sẽ bị từ chối trước khi xét digest do method khác. Để kiểm thử body binding độc lập, phải dùng digest thật của body gốc, giữ method/target trùng và chỉ thay body, rồi assert bị từ chối. Phải có test khác xác minh assertion signature/issuer/audience/time/replay trên **token thực** thay vì mock `VerifiedGatewayAssertion`.

### E2E qua proxy thật

Bộ test quan trọng nhất gọi từ ngoài qua **đúng CDN/ingress/gateway và backend routing** mà production sử dụng. Ghi nhận:

- External method/target/headers/body bytes dùng để ký;
- Điểm gateway thực hiện HMAC verify so với điểm rewrite;
- Peer identity giữa gateway và service;
- Internal method/target/body mà backend thực tế nhận;
- Claims assertion đã verify;
- Principal, owner tenant, effective tenant và authorization outcome;
- Dữ liệu trước/sau test và mã lỗi public.

Không thu thập shared secret hoặc raw production body khi logging E2E; dùng fixture bảo mật/test data và correlation ID.

## 19. Observability, incident response và trách nhiệm vận hành

Một hệ thống tin gateway cần có khả năng trả lời:

- Request nào đã vượt qua HMAC ở gateway nào, với credential version nào?
- Assertion nội bộ do gateway identity nào phát hành, cho audience nào?
- Backend đã xác minh body digest, target và authorization chưa?
- Key client hoặc gateway signing key bị revoke lúc nào; node nào vẫn còn cache phiên bản cũ?
- Có direct-call hoặc workload lạ cố gửi header `X-Authenticated-*` không?
- Có tỷ lệ tăng đột biến của `SIGNATURE_MISMATCH`, `REPLAY_DETECTED`, `ASSERTION_AUDIENCE_MISMATCH`, `BODY_DIGEST_MISMATCH` không?

Tín hiệu nên tách ở từng hop:

| Telemetry | Công dụng |
| --- | --- |
| Gateway HMAC success/failure theo route/region | Nhận biết client sai chữ ký, key rotation hoặc gateway drift |
| Backend assertion verify failure | Phát hiện forged/replayed/internal-token misuse |
| mTLS identity unauthorized | Cảnh báo bypass/misconfigured service routing |
| Canonical path/body binding mismatch | Phát hiện proxy rewrite hoặc request tampering |
| Key/client disabled và revocation lag | Đánh giá hiệu lực thu hồi |
| 401/403/413/503 theo tầng | Phân biệt authentication, authorization, resource, dependency |
| Replay rejection theo credential/gateway | Phát hiện phát lại hoặc retry sai nonce |
| Tenant access denied / IDOR attempt | Phát hiện thiếu quyền chéo tenant |

Không ghi shared secret, toàn bộ HMAC signature, gateway assertion bearer token, raw body nhạy cảm hoặc canonical request chứa dữ liệu cá nhân. Key/tenant ID có thể là dữ liệu nhạy cảm, nên che/giới hạn quyền đọc; tránh biến ID cardinality cao thành metric label phổ biến.

Khi gateway bị compromise, quy trình tối thiểu gồm cô lập workload, thu hồi mTLS/gateway assertion signing keys, đánh giá các assertion có thể đã phát, rotate key liên quan, kiểm tra audit và xác định tenant/resource bị ảnh hưởng. Chỉ rotate client HMAC key là **chưa đủ** nếu kẻ tấn công đang có quyền tạo assertion gateway.

## 20. Bài tập phân tích ranh giới tin cậy

Một công ty vận hành:

~~~text
Client --HTTPS--> CDN --> API Gateway --> Spring Boot Payment Service
~~~

Gateway xác minh HMAC rồi gửi:

~~~http
X-Authenticated-Client: partner-a
X-Authenticated-Tenant: tenant-a
X-Gateway-Verified: true
~~~

Backend chỉ kiểm tra `X-Gateway-Verified=true` và mở toàn bộ endpoint. Mạng nội bộ cho phép nhiều pod gọi trực tiếp Payment Service. Khi CDN thay đổi path `/public/v1/payments` thành `/internal/payments`, nhóm phát triển bật `X-Original-URI` từ request client để “giải quyết lỗi chữ ký”. Nonce được giữ trong RAM của từng gateway; key K3 đã bị revoke ở registry nhưng một region cache ACTIVE trong một phút.

Hãy trả lời:

1. Có bao nhiêu ranh giới tin cậy đang bị giả định thay vì được xác minh?
2. Vì sao header `X-Gateway-Verified=true` không chứng minh request đến từ gateway?
3. Nếu thêm mTLS, backend còn cần kiểm tra điều gì ngoài certificate trust root?
4. Cách bảo toàn canonical request khi CDN/gateway rewrite path là gì?
5. Có nên dùng `X-Original-URI` từ client cho canonical HMAC không?
6. Request signature đúng cho tenant A có nghĩa đối tác được phép đọc data tenant B không?
7. Tại sao nonce store riêng mỗi gateway không chống replay xuyên region?
8. Key K3 bị REVOKED nhưng cache stale: cần biện pháp nào đáp ứng cam kết thu hồi?
9. Nếu gateway tự xác minh HMAC, có thể ràng buộc method, target và body ở backend bằng cách nào?
10. Bộ test tối thiểu cần chứng minh điều gì trước khi triển khai production?

**Định hướng:** tin gateway phải dựa trên peer identity/network boundary, assertion đã kiểm tra issuer–audience–time–signature và request binding; không dựa trên header tự khai. Canonicalization phải được định nghĩa theo trust contract, tránh original URI do client điều khiển. Replay store phải atomic toàn cụm. Key revocation cần freshness/fail closed theo cam kết. Authorization phải kiểm tra tenant/action/resource độc lập. E2E test phải chứng minh cả phản hồi, context và không có side effect chéo tenant.

## 21. Checklist Trust gateway trước khi đưa vào production

- Đã chọn **một mô hình xác minh HMAC rõ ràng**: backend tự verify hoặc gateway verify + assertion tin cậy; các route không được nhập nhằng.
- Trust boundary từ Internet đến edge, từ gateway đến backend, từ backend đến service khác được mô tả và kiểm thử.
- Backend không có ingress/direct route cho caller không được phép; network policy, mTLS và service authorization đã hoạt động.
- Gateway loại bỏ các identity/forwarded/assertion headers do client tự khai trước khi tạo lại thông tin nội bộ.
- Duplicate signed headers, HTTP version conversion, path/query ambiguity và request smuggling được xử lý theo hợp đồng.
- Canonical request xác định method, external/internal target, signed headers và body bytes; proxy rewrite được kiểm thử E2E.
- Credential lookup sử dụng đúng key ID/version, không thử fallback secret; trạng thái key/client/tenant có độ mới được kiểm soát.
- Timestamp/nonce có chống replay với atomic store chung giữa mọi verifier được phép xử lý cùng credential.
- Gateway assertion, nếu dùng, có issuer, audience, thời hạn, ID/replay protection và method/target/body binding.
- Backend xác minh cryptographic assertion và mTLS peer trước khi tạo principal tin cậy; không tin `X-Authenticated-*` thuần văn bản.
- Gateway identity và assertion signing key được giới hạn quyền, rotate/revoke **tách biệt** khỏi client HMAC secrets.
- Authorization theo principal/target tenant/action/resource vẫn thực hiện sau authentication; database query scope theo tenant hiệu lực.
- Error response fail closed khi thiếu registry/vault/replay store hoặc proof; không biến lỗi thành đường bypass.
- Có unit, contract, integration và E2E tests cho forged headers, direct backend, wrong audience, replay, route/body tamper, key revoke và multi-tenant.
- Observability theo từng trust boundary; log/metrics an toàn, không chứa HMAC secrets, assertion bearer tokens hoặc raw payload nhạy cảm.
- Có phương án xử lý sự cố gateway compromise, key revocation, stale cache và certificate compromise.

**Trust gateway không phải việc gắn một header “đã xác thực”.** Đây là chuỗi kiểm tra nguồn gốc request, identity của gateway, tính toàn vẹn của các trường đã ký và quyền được thực thi tại backend. Với HMAC request authentication, gateway chỉ đáng tin khi mọi đường vượt qua ranh giới đó đều được xác minh, không thể bị client giả mạo, có khả năng chống replay/thu hồi và không nhầm xác thực với phân quyền.
