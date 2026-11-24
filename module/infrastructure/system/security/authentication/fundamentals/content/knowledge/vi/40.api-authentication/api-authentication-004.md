# Request signing — Ký request để xác thực nguồn gửi và bảo vệ tính toàn vẹn API

> **Chương:** Authentication trong API  
> **Chủ đề:** Request signing  
> **Phạm vi:** Bài học thuộc module SECURITY_AUTHENTICATION_FUNDAMENTALS, tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này trình bày cách ký request HTTP bằng HMAC hoặc chữ ký bất đối xứng để xác minh nguồn gửi và phát hiện nội dung bị thay đổi; đồng thời giải thích canonicalization, body digest, timestamp, nonce, replay protection, quản lý khóa và ranh giới giữa authentication với authorization.

## 1. Request signing là gì?

**Request signing (ký request)** là cơ chế dùng khóa mật mã để tạo bằng chứng gắn với nội dung của một request. Server xác minh chữ ký để kiểm tra request được tạo bởi bên kiểm soát khóa tương ứng và các thành phần đã ký không bị thay đổi trên đường truyền.

Ví dụ, dịch vụ order cần gửi lệnh cập nhật trạng thái đơn hàng tới fulfillment API. Client ký method, đường dẫn, một số header quan trọng, digest của body và thông tin thời gian/nonce. Server tái tạo đúng biểu diễn đã thỏa thuận rồi xác minh chữ ký. Nếu body hoặc path bị thay đổi sau khi ký, chữ ký không còn khớp.

Request signing thường được dùng trong:
- API giữa các service hoặc workload;
- webhook từ nhà cung cấp tới hệ thống nội bộ;
- API tài chính hoặc hệ thống cần bảo vệ tính toàn vẹn request;
- thiết bị hoặc agent gửi dữ liệu tới backend;
- giao thức tích hợp cần xác minh nguồn gửi ngoài TLS.

Ký request không tự mã hóa nội dung. Nó cũng không tự cấp quyền cho mọi hành động. Sau khi chữ ký hợp lệ, server vẫn phải xác định principal, kiểm tra trạng thái key/client, authorization, tenant và business rules.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích mục tiêu và giới hạn của request signing.
2. Phân biệt HMAC với chữ ký số bất đối xứng.
3. Xác định những thành phần HTTP cần được ký.
4. Thiết kế canonical request có biểu diễn byte nhất quán.
5. Ràng buộc body bằng digest và bảo vệ header quan trọng.
6. Chống replay bằng timestamp, nonce và lưu trạng thái đã dùng.
7. Quản lý key ID, secret, public key, rotation và revocation.
8. Xử lý proxy, header trùng, URL normalization và body transformation.
9. Phân biệt request authentication với authorization, TLS và OAuth.
10. Kiểm thử request signing trước sửa đổi, replay và lỗi canonicalization.

## 2. Request signing giải quyết vấn đề gì?

TLS bảo vệ kết nối giữa hai đầu TLS, nhưng request có thể đi qua nhiều proxy, gateway, queue hoặc hệ thống trung gian. Một số API cần bằng chứng mật mã gắn trực tiếp với request để:
- xác minh client đang kiểm soát khóa đã đăng ký;
- phát hiện method, URI, header hoặc body bị thay đổi;
- xác định request thuộc key/client nào;
- phát hiện request cũ bị gửi lại;
- hỗ trợ xác minh webhook mà không cần tin IP nguồn;
- bảo vệ thông điệp khi được lưu chuyển qua hạ tầng trung gian theo protocol.

Ví dụ, webhook provider gửi event tới merchant. Merchant không nên chỉ tin request vì nó đến từ IP đã biết hoặc chứa một header tên X-Provider. Provider có thể ký body và timestamp bằng secret đã chia sẻ. Merchant xác minh chữ ký trên raw body theo quy tắc provider công bố.

Request signing đặc biệt hữu ích khi client và server cần xác minh tính toàn vẹn ở lớp ứng dụng. Tuy nhiên, nó chỉ bảo vệ những thành phần thực sự nằm trong signature input. Nếu client ký body nhưng không ký path hoặc method, attacker có thể thử chuyển request đã ký sang endpoint khác nếu server không có kiểm soát bổ sung.

## 3. Authentication, integrity và authorization

Ba mục tiêu cần tách biệt:

| Mục tiêu | Câu hỏi | Cơ chế |
| --- | --- | --- |
| **Authentication** | Ai đang gửi request hoặc kiểm soát key? | HMAC hoặc chữ ký số hợp lệ gắn với key đã đăng ký |
| **Integrity** | Nội dung đã ký có bị thay đổi không? | Xác minh MAC/chữ ký trên canonical request |
| **Authorization** | Principal có được phép thực hiện action trên resource này không? | Scope, role, policy, tenant và business rules |

Một chữ ký hợp lệ không có nghĩa request được phép. Client có thể sở hữu key hợp lệ nhưng chỉ được đọc inventory; chữ ký trên request xóa inventory vẫn phải bị authorization từ chối.

Tương tự, chữ ký không chứng minh request an toàn về mặt nghiệp vụ. Server vẫn phải kiểm tra số tiền, trạng thái đơn hàng, ownership và các ràng buộc domain.

## 4. HMAC và chữ ký bất đối xứng

Có hai nhóm cơ chế phổ biến.

| Cơ chế | Khóa ký | Khóa xác minh | Đặc điểm |
| --- | --- | --- | --- |
| **HMAC** | Shared secret | Cùng shared secret | Hai bên có cùng khả năng tạo và xác minh MAC |
| **Digital signature** | Private key | Public key | Chỉ bên giữ private key ký; nhiều verifier có thể xác minh bằng public key |

### HMAC

HMAC kết hợp secret key với hash function để tạo message authentication code. Ví dụ:

~~~text
signature = HMAC-SHA-256(secretKey, canonicalRequest)
~~~

Server tính lại HMAC với cùng secret rồi so sánh bằng phép so sánh constant-time phù hợp. Không dùng hash thuần như SHA-256(secret || message) thay cho HMAC; HMAC được thiết kế cho mục đích message authentication.

Ưu điểm:
- nhanh và dễ triển khai;
- phù hợp giữa hai hệ thống có kênh phân phối secret an toàn;
- không cần PKI hoặc certificate cho từng client.

Giới hạn:
- cả signer và verifier đều giữ secret có khả năng tạo chữ ký;
- nếu nhiều service cùng biết một secret, không thể phân biệt service nào đã tạo một MAC;
- secret bị lộ có thể cho phép giả mạo request cho tới khi key bị revoke/rotate.

### Chữ ký bất đối xứng

Client ký bằng private key; server xác minh bằng public key. Ví dụ có thể dùng Ed25519 hoặc thuật toán chữ ký được hệ thống và tiêu chuẩn chấp nhận.

Ưu điểm:
- verifier không cần giữ private signing key;
- có thể phân phối public key tới nhiều resource server;
- dễ tách vai trò phát hành và xác minh.

Giới hạn:
- cần quản trị private key, public key, algorithm và key rotation;
- chi phí tính toán và kích thước chữ ký có thể cao hơn HMAC;
- chữ ký hợp lệ vẫn không chứng minh private key chưa bị lạm dụng bởi malware trong workload.

Chọn thuật toán theo profile được hỗ trợ và thư viện đã được kiểm chứng. Không cho client tự chọn thuật toán tùy ý trong mỗi request.

## 5. Chọn mô hình khóa theo trust boundary

HMAC phù hợp khi hai bên có thể bảo vệ shared secret và việc cả hai bên đều có khả năng ký là chấp nhận được. Chữ ký bất đối xứng phù hợp khi nhiều server cần xác minh nhưng không nên có quyền tạo chữ ký.

Ví dụ:

| Mô hình | Gợi ý |
| --- | --- |
| Một client gọi một API nội bộ | HMAC với secret riêng cho client, nếu secret storage được bảo vệ |
| Nhiều API gateway cần xác minh cùng signer | Chữ ký bất đối xứng có thể giảm phân phối private key |
| Webhook provider gửi event | Theo cơ chế signing chính thức của provider; thường HMAC hoặc public-key signature |
| Nhiều tenant/client độc lập | Key riêng cho từng client/tenant, mapping rõ trong registry |
| Workload trên cloud | Cân nhắc workload identity và key ngắn hạn/thay vì secret tĩnh |

Không dùng chung một HMAC secret cho mọi client. Nếu key dùng chung, một client bị compromise có thể ký request dưới danh tính của client khác nếu server không có binding riêng.

## 6. Xác định signature input

Chữ ký chỉ bảo vệ các thành phần nằm trong dữ liệu được ký. Một request signing contract cần định nghĩa rõ:
- HTTP method;
- authority/host;
- path và query;
- body digest;
- các header có ý nghĩa bảo mật hoặc nghiệp vụ;
- thời điểm tạo và thời điểm hết hạn;
- nonce hoặc request identifier;
- key identifier;
- algorithm/profile được cấu hình.

Không cần ký mọi header. Hãy chọn các thành phần có ảnh hưởng tới cách server định tuyến, diễn giải hoặc thực thi request. Nhưng các thành phần quan trọng như method, target URI và body thường phải được ràng buộc.

Ví dụ, nếu chữ ký chỉ bao gồm body, attacker có thể thử gửi body đó tới endpoint khác. Nếu chỉ ký path mà không ký query, các tham số lọc, tenant hoặc transaction có thể bị thay đổi. Nếu không ký Content-Type, cùng bytes có thể bị diễn giải khác bởi middleware.

## 7. Canonical request: biểu diễn duy nhất để ký

**Canonical request** là biểu diễn chuẩn hóa của các thành phần request mà client và server cùng dùng để tạo và xác minh chữ ký. Hai bên phải tạo ra cùng một chuỗi byte cho cùng request hợp lệ.

Ví dụ cấu trúc khái niệm:

~~~text
HTTP-METHOD
CANONICAL-AUTHORITY
CANONICAL-PATH
CANONICAL-QUERY
CONTENT-DIGEST
CONTENT-TYPE
SIGNED-HEADERS
CREATED
EXPIRES
NONCE
KEY-ID
~~~

Một hợp đồng canonicalization phải quy định:
- encoding, thường là UTF-8 cho các trường văn bản;
- cách viết method;
- cách parse và chuẩn hóa authority/port;
- path có percent-encoding được xử lý ra sao;
- query parameter được sắp xếp hay giữ nguyên thứ tự;
- duplicate parameter/header bị từ chối hay có quy tắc cụ thể;
- whitespace được chuẩn hóa như thế nào;
- header name có được lowercase không;
- body digest tính trên bytes nào;
- newline và dấu phân cách;
- giá trị rỗng và trường thiếu được biểu diễn ra sao.

Không tự nghĩ ra canonicalization riêng một cách tùy tiện. Nếu client và server xử lý URI khác nhau, cùng một request có thể tạo canonical request khác nhau hoặc attacker khai thác parser discrepancy.

## 8. Method, authority, path và query

### Method

HTTP method cần được ký vì GET, POST, PUT, PATCH và DELETE có semantics khác nhau. Không để proxy hoặc middleware đổi method sau khi signature được xác minh mà không có cơ chế bảo toàn binding.

### Authority/Host

Ký authority giúp ràng buộc request với host/resource server dự kiến. Phải xác định authority được lấy từ request line, HTTP/2 :authority, Host header hay external host đã cấu hình sau proxy. Client không được tự khai một giá trị rồi server tin mà không kiểm tra.

### Path và query

Path/query có thể bị biến đổi bởi:
- percent-encoding;
- slash lặp;
- dot-segment;
- Unicode;
- query parameter trùng;
- thứ tự parameter;
- dấu + và %20;
- proxy rewrite;
- trailing slash.

Contract cần chọn một biểu diễn duy nhất. Cách an toàn thường là dùng URL parser và quy tắc canonicalization đã được chuẩn hóa, từ chối dạng mơ hồ và xác minh trên cùng representation mà router thực sự dùng.

## 9. Ký body bằng content digest

Body có thể chứa dữ liệu quyết định như số tiền, người nhận, trạng thái đơn hàng hoặc payload webhook. Nếu body không được ràng buộc, attacker có thể thay đổi dữ liệu sau khi client ký các header khác.

Một cách phổ biến là tính digest của raw body bytes:

~~~text
contentDigest = SHA-256(rawBodyBytes)
~~~

Digest được đưa vào canonical request hoặc được ký như một component riêng. Server tính lại digest từ body nhận được và so sánh.

Cần xác định:
- digest tính trước hay sau content decoding;
- có ký compressed bytes hay decoded representation;
- charset và serialization;
- streaming/chunked request được xử lý ra sao;
- body rỗng được biểu diễn như thế nào;
- giới hạn kích thước và xử lý request quá lớn.

Nếu proxy giải nén hoặc biến đổi body trước khi verifier chạy, digest có thể không khớp. Cần đặt verification tại boundary phù hợp hoặc thiết kế contract để cả hai phía dùng cùng bytes.

## 10. Ký các header quan trọng

Một số header có thể ảnh hưởng đến cách request được xử lý:
- Content-Type;
- Content-Digest;
- Idempotency-Key;
- X-Tenant-ID nếu được dùng trong routing và authorization;
- header version hoặc transaction identifier;
- các header ứng dụng có ý nghĩa bảo mật.

Không ký header chỉ vì nó tồn tại. Chọn component theo threat model và đảm bảo server dùng chính giá trị đã ký khi thực thi.

Nếu tenant được lấy từ header, header đó cần được ký và vẫn phải được kiểm tra với membership/resource ownership. Chữ ký chỉ chứng minh client đã gửi giá trị đó; nó không chứng minh client được phép truy cập tenant đó.

### Duplicate header

HTTP có thể có nhiều cách xử lý header trùng tùy server/proxy. Nếu signer ký một giá trị nhưng gateway gộp hoặc backend chọn giá trị khác, signature verification và business logic có thể nhìn thấy dữ liệu khác nhau.

Đối với header nhạy cảm:
- từ chối duplicate nếu contract không định nghĩa cách xử lý;
- chuẩn hóa một lần tại ingress;
- dùng cùng representation cho verifier và application;
- kiểm thử qua toàn bộ proxy chain.

## 11. Timestamp và giới hạn tuổi request

Timestamp giúp giới hạn thời gian một chữ ký có thể được replay. Client ký thời điểm tạo request; server kiểm tra request nằm trong cửa sổ thời gian được phép.

Ví dụ:
- created: thời điểm tạo request;
- expires: thời điểm request signature hết hiệu lực;
- max age: giới hạn do server cấu hình.

Server cần:
- dùng clock đồng bộ và xử lý clock skew có giới hạn;
- từ chối timestamp quá cũ;
- từ chối expiry đã qua;
- giới hạn maximum lifetime;
- không tin thời gian do client gửi ngoài phạm vi policy;
- ghi nhận drift để vận hành.

Timestamp một mình không chống replay. Attacker có thể gửi lại cùng request nhiều lần trong cửa sổ timestamp còn hợp lệ. Cần nonce hoặc cơ chế chống xử lý trùng.

## 12. Nonce và replay protection

**Replay attack** là việc attacker gửi lại một request đã ký hợp lệ. Chữ ký vẫn đúng vì nội dung không đổi; do đó verifier cần biết request đã được chấp nhận trước đó hay chưa.

Nonce là giá trị duy nhất cho từng request hoặc signing attempt. Client tạo nonce đủ ngẫu nhiên hoặc dùng request identifier duy nhất theo protocol, rồi đưa nonce vào signature input.

Server:
1. xác minh chữ ký;
2. kiểm tra timestamp/expiry;
3. kiểm tra nonce chưa được sử dụng;
4. ghi nhận nonce bằng thao tác atomic;
5. chỉ tiếp tục xử lý khi nonce được tiêu thụ thành công.

Nonce store cần có TTL tương ứng với cửa sổ chấp nhận request. Trong hệ thống nhiều instance, store phải dùng chung hoặc có cơ chế chống replay phân tán. Nếu mỗi instance có cache riêng, attacker có thể gửi cùng request tới hai instance khác nhau.

Không lưu nonce trước khi xác minh chữ ký nếu điều đó cho phép attacker gửi request giả để làm đầy cache hoặc chiếm nonce hợp lệ. Tuy nhiên, bước consume phải nguyên tử để hai request đồng thời không cùng vượt qua.

## 13. Nonce, idempotency key và request ID khác nhau

| Giá trị | Mục đích | Hành vi khi retry |
| --- | --- | --- |
| **Nonce** | Chống replay của cùng một signed request | Nonce đã dùng bị từ chối |
| **Idempotency key** | Nhận diện cùng một thao tác nghiệp vụ khi client retry | Có thể trả lại kết quả đã lưu |
| **Request ID** | Correlation/trace một lần gửi | Có thể dùng cho logging; không tự chống replay |
| **Transaction ID** | Định danh đối tượng nghiệp vụ | Có thể tồn tại lâu và có nhiều request hợp lệ |

Một retry hợp lệ có thể cần nonce mới nhưng giữ nguyên idempotency key. Server nhận nonce mới, xác minh chữ ký, rồi dùng idempotency key để trả kết quả nghiệp vụ đã lưu thay vì thực hiện side effect lần hai.

Không dùng idempotency key thay nonce nếu protocol yêu cầu mỗi request signature chỉ được chấp nhận một lần. Cũng không dùng timestamp làm request ID.

## 14. HMAC request signing flow

Một flow HMAC khái niệm:

~~~mermaid
sequenceDiagram
    participant C as API Client
    participant S as API Server
    participant K as Key Registry
    participant N as Nonce Store
    C->>C: Build canonical request
    C->>C: HMAC-SHA-256(secret, canonical request)
    C->>S: HTTP request + keyId + timestamp + nonce + signature
    S->>K: Resolve active key by keyId
    K-->>S: Client identity + secret reference + policy
    S->>S: Rebuild canonical request and body digest
    S->>S: Verify HMAC using constant-time comparison
    S->>S: Check timestamp and expiry
    S->>N: Atomically consume nonce
    N-->>S: First use
    S->>S: Authorize principal, action, resource and tenant
    S-->>C: API response
~~~

Client và server phải dùng cùng canonicalization contract, key version, hash algorithm và encoding. Server cần lấy key từ registry theo key ID; không để client gửi secret hoặc public key tùy ý rồi verifier tin nó.

## 15. Header signing minh họa

Một custom protocol có thể truyền thông tin như sau:

~~~http
POST /v1/orders/ord-42/confirm?source=mobile HTTP/1.1
Host: api.example.internal
Content-Type: application/json
Content-Digest: sha-256=:<base64-digest>:
X-Key-Id: order-service-prod-v3
X-Created: 1795340400
X-Expires: 1795340460
X-Nonce: 8f1a2c...unique...
X-Signature: <base64url-signature>

{"orderId":"ord-42","decision":"confirm"}
~~~

Đây là ví dụ minh họa một protocol riêng, không phải cú pháp chuẩn bắt buộc. Contract phải định nghĩa chính xác:
- trường nào được ký;
- cách tính Content-Digest;
- canonical request bytes;
- algorithm và key ID;
- timestamp window;
- nonce store và replay behavior;
- response/error semantics;
- key rotation và revocation.

Không chỉ thêm một header X-Signature rồi coi request đã an toàn. Nếu verifier và client không có specification đầy đủ, mỗi implementation có thể hiểu khác nhau.

## 16. HTTP Message Signatures và chuẩn hóa giao thức

Nếu cần interoperable HTTP signing, cân nhắc dùng chuẩn **HTTP Message Signatures (RFC 9421)** cùng thư viện phù hợp. Chuẩn này định nghĩa cách chọn và biểu diễn các message component được ký, cùng signature parameters như key identifier, creation/expiry và nonce.

Body digest có thể được biểu diễn bằng cơ chế digest riêng theo chuẩn tương ứng; cần kiểm tra đúng profile đang triển khai và thứ tự xử lý. Không tự giả định rằng ký một số header đã tự động bảo vệ body.

Lợi ích của chuẩn:
- giảm khác biệt canonicalization giữa client và server;
- có mô hình component/parameter rõ;
- dễ tích hợp nhiều implementation hơn;
- có cơ sở để review và kiểm thử.

Dù dùng chuẩn, triển khai vẫn phải chọn component đúng, quản lý key, chống replay, xác minh identity và authorization. Chuẩn hóa chữ ký không thay thế threat model.

## 17. HMAC verification an toàn

Khi server xác minh HMAC:
- resolve key ID từ registry tin cậy;
- kiểm tra key active, đúng client và đúng environment;
- dựng canonical request từ request thực tế;
- tính lại body digest;
- tính HMAC với thuật toán được cấu hình;
- so sánh bằng constant-time comparison;
- kiểm tra timestamp, expiry và nonce;
- chỉ sau đó gắn request với principal và chạy authorization.

Không dùng string equality thông thường nếu nó có thể tạo timing leak về MAC. Dùng primitive constant-time của thư viện mật mã.

Không chấp nhận algorithm do request tự khai mà không kiểm tra allowlist. Key ID chỉ là selector, không phải bằng chứng xác thực; server phải map nó tới key đã đăng ký và policy.

## 18. Chữ ký bất đối xứng và public-key verification

Với chữ ký số:
- client tạo canonical request;
- ký bằng private key;
- gửi key ID và signature;
- server lấy public key từ registry/JWKS/PKI tin cậy;
- xác minh chữ ký và các request constraints.

Public key không cần bí mật, nhưng nguồn và mapping của nó phải tin cậy. Không tải public key từ URL do request cung cấp. Khi key rotate, server có thể chấp nhận public key cũ trong overlap window ngắn để không làm gián đoạn request hợp lệ, rồi thu hồi theo lịch.

Chữ ký bất đối xứng giúp verifier không thể tự tạo chữ ký client. Nhưng nếu server có thể sửa request trước khi xác minh hoặc application dùng giá trị khác với giá trị đã ký, integrity vẫn bị phá vỡ ở tầng xử lý.

## 19. Key ID, key registry và vòng đời khóa

Key ID là định danh công khai dùng để tìm key record. Nó không phải secret.

Key registry nên lưu:
- key ID và client/principal;
- loại key (HMAC, public key, certificate);
- algorithm được phép;
- môi trường, tenant và audience/scope liên quan;
- thời điểm tạo, activate, expiry và revoke;
- trạng thái active/disabled/compromised;
- owner và contact;
- version và rotation metadata.

Key lifecycle:
1. tạo key bằng CSPRNG hoặc hệ thống key management;
2. đăng ký public key hoặc phân phối secret qua secure channel;
3. xác minh client possession khi enrollment nếu cần;
4. activate sau approval;
5. monitor usage và expiry;
6. rotate theo lịch hoặc khi có dấu hiệu compromise;
7. revoke key cũ;
8. lưu audit metadata theo retention, không lưu secret plaintext trong log.

Mỗi client nên có key riêng. Không dùng một key chung cho nhiều tenant, service hoặc môi trường có trust boundary khác nhau.

## 20. Secret storage và private-key protection

Với HMAC:
- lưu secret trong secret manager/HSM hoặc hệ thống quản lý secret phù hợp;
- chỉ workload cần thiết mới được đọc;
- không bake secret vào image, source, CI log hoặc config public;
- không gửi secret qua query string;
- giới hạn memory lifetime và access;
- rotate và revoke có kế hoạch.

Với private key:
- ưu tiên HSM, KMS hoặc key store có access control;
- nếu có thể, dùng non-exportable key;
- phân quyền ký riêng với quyền quản trị key;
- audit signing operations;
- bảo vệ backup và recovery;
- rotate khi key có nguy cơ bị lộ.

Nếu attacker chiếm được process đang có quyền gọi HSM/KMS, họ có thể yêu cầu ký dù private key không export được. Non-exportable key giảm một số rủi ro nhưng không thay thế bảo vệ workload.

## 21. Rotation, overlap và revocation

Key rotation cần tránh cả gián đoạn và cửa sổ dùng key cũ quá dài.

Một quy trình:
1. tạo key version mới;
2. đăng ký key mới ở verifier;
3. phân phối/cho phép signer dùng key mới;
4. xác minh request mới dùng key mới;
5. theo dõi key cũ còn traffic hay không;
6. ngừng signer dùng key cũ;
7. revoke key cũ sau overlap window;
8. xử lý cache và replica;
9. audit kết quả.

Nếu key bị compromise, không nhất thiết chờ overlap window. Cần revoke khẩn cấp, vô hiệu request mới dùng key đó, xác định request đã được ký trong khoảng rủi ro và rotate credential phụ thuộc.

Server phải kiểm tra trạng thái key ở nguồn authoritative hoặc cache có freshness phù hợp. Nếu key đã revoke nhưng instance khác còn cache active quá lâu, attacker vẫn có thể ký request tới instance đó.

## 22. Proxy, gateway và canonicalization boundary

Request thường đi qua CDN, load balancer, API gateway, service mesh hoặc reverse proxy. Các thành phần có thể:
- rewrite path;
- thay Host/authority;
- thêm hoặc gộp header;
- giải nén body;
- chuẩn hóa query;
- chuyển HTTP/2 sang HTTP/1.1;
- loại bỏ header không nhận diện.

Cần quyết định nơi verify:
- **At edge:** verifier nhìn thấy request gần với request client gửi, nhưng cần tin cậy ingress và truyền identity đã xác minh downstream.
- **At application:** app có thể kiểm tra đúng logic nghiệp vụ, nhưng phải biết proxy đã biến đổi request ra sao.
- **At both:** edge xác minh signature; app nhận assertion nội bộ được bảo vệ và vẫn thực hiện authorization.

Không để gateway xác minh canonical request theo một representation rồi backend thực thi representation khác. Đây là nguồn gốc của signature bypass và request smuggling/canonicalization mismatch.

### Forwarded headers

Chỉ tin Forwarded, X-Forwarded-Host, X-Forwarded-Proto hoặc client certificate metadata từ proxy được cấu hình tin cậy. Proxy phải xóa giá trị do client gửi trước khi thêm giá trị của nó. Nếu không, attacker có thể tác động authority hoặc external URI mà server đưa vào canonical request.

## 23. Replay, duplicate delivery và xử lý nghiệp vụ

Chữ ký hợp lệ có thể được replay nếu attacker lấy được request trước khi hết hạn. Ngoài timestamp/nonce, các thao tác có side effect cần idempotency và state transition.

Ví dụ:
- nonce N1 được dùng cho lần gửi đầu;
- server xác minh và consume N1;
- response bị mất;
- client retry cùng nghiệp vụ với nonce N2 mới nhưng cùng idempotency key K;
- server xác minh N2 rồi trả lại kết quả đã lưu cho K, không thực hiện thanh toán lần hai.

Với request đọc không có side effect, replay vẫn có thể gây lộ dữ liệu hoặc tải hệ thống; vẫn cần timestamp/nonce và authorization.

Nonce consume và idempotency record cần atomic hoặc có workflow reconciliation. Nếu hai instance cùng nhận một nonce, chỉ một instance được chấp nhận. Nếu idempotency key được dùng ở nhiều endpoint hoặc principal, scope key cần bao gồm principal, operation và resource.

## 24. Request signing không thay thế TLS, OAuth hoặc mTLS

| Cơ chế | Bảo vệ chính | Giới hạn |
| --- | --- | --- |
| TLS | Confidentiality và integrity của kết nối; xác thực server | Không tự gắn application request với client key ở mọi hop |
| mTLS | Xác thực peer bằng certificate trong TLS | Không tự mô tả quyền action/resource |
| OAuth access token | Quyền được AS cấp cho client/user và resource | Bearer token có thể bị replay nếu bị đánh cắp |
| HMAC request signing | Xác minh bên kiểm soát shared secret và integrity của component đã ký | Verifier cũng có thể ký; không mã hóa; cần chống replay |
| Asymmetric request signature | Xác minh signer bằng public key và integrity của component đã ký | Cần quản lý private key, freshness và authorization |

Có thể kết hợp:
- TLS để bảo vệ kênh;
- OAuth để cấp scope/audience;
- request signing để ràng buộc nội dung request;
- mTLS để xác thực workload peer;
- authorization ở resource server để kiểm tra action/resource.

Tránh chồng nhiều cơ chế mà không xác định trách nhiệm. Mỗi lớp cần có threat model và failure behavior rõ.

## 25. Webhook signing

Webhook là một trường hợp request signing phổ biến. Provider gửi HTTP request tới endpoint subscriber khi có event.

Subscriber nên:
- lấy raw body bytes đúng như provider ký;
- xác minh signature theo tài liệu provider;
- kiểm tra timestamp và replay window nếu provider hỗ trợ;
- kiểm tra event ID đã xử lý để chống duplicate;
- xác minh event type và account/tenant binding;
- xử lý event bất đồng bộ sau khi xác minh;
- không tin payload chỉ vì TLS thành công hoặc source IP khớp.

Không parse JSON rồi serialize lại trước khi xác minh nếu provider ký raw body. Whitespace, thứ tự field và encoding có thể khác dù JSON semantics giống nhau.

Webhook delivery thường retry. Một event hợp lệ có thể được gửi nhiều lần; subscriber cần idempotent processing. Chống replay ở lớp signature và chống xử lý nghiệp vụ trùng là hai việc khác nhau.

## 26. Pseudocode tạo và xác minh HMAC signature

Client pseudocode:

~~~java
SignedRequest sign(
        HttpMethod method,
        CanonicalTarget target,
        byte[] rawBody,
        SigningKey key,
        Instant now,
        String nonce) {

    byte[] bodyDigest = sha256(rawBody);

    CanonicalRequest canonical = canonicalizer.build(
        method,
        target,
        bodyDigest,
        now,
        now.plusSeconds(60),
        nonce,
        key.keyId());

    byte[] mac = hmacSha256(key.secret(), canonical.bytes());

    return SignedRequest.withHeaders(
        method, target, rawBody,
        key.keyId(), now, now.plusSeconds(60),
        nonce, base64Url(mac));
}
~~~

Server pseudocode:

~~~java
VerifiedRequest verify(HttpRequest request) {
    KeyRecord key = keyRegistry.requireActive(request.keyId());

    require(key.allowedAlgorithm() == HMAC_SHA_256);
    require(clockPolicy.isWithinWindow(
        request.createdAt(), request.expiresAt()));

    byte[] rawBody = request.rawBodyBytes();
    byte[] bodyDigest = sha256(rawBody);

    CanonicalRequest canonical = canonicalizer.buildFromReceived(
        request, bodyDigest, key.keyId());

    byte[] expected = hmacSha256(key.secret(), canonical.bytes());
    byte[] supplied = base64UrlDecode(request.signature());

    require(constantTimeEquals(expected, supplied));
    nonceStore.consumeAtomically(
        key.keyId(), request.nonce(), request.expiresAt());

    return VerifiedRequest.forPrincipal(
        key.clientIdentity(), request);
}
~~~

Đây là pseudocode khái niệm, không phải thư viện production. Thứ tự kiểm tra, exception, body streaming, nonce atomicity, algorithm/key binding và authorization cần được thiết kế theo protocol cụ thể. Sau verify, server vẫn phải kiểm tra quyền trên resource/action.

## 27. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Kiểm soát |
| --- | --- | --- |
| Chỉ ký body | Request có thể bị chuyển sang method/path khác | Ký method, target và body digest |
| Không ký query | Tham số tenant/filter/transaction bị đổi | Canonicalize và ký query theo contract |
| Không ký Content-Type | Cùng body có thể bị diễn giải khác | Ký Content-Type khi ảnh hưởng semantics |
| Canonicalization khác nhau | Client ký một representation, server xác minh representation khác | Specification và test vector chung |
| Hash JSON đã parse/serialize lại | Digest thay đổi do whitespace/order/encoding | Ký raw bytes hoặc canonical payload được đặc tả |
| Timestamp không có nonce | Request có thể replay trong cửa sổ timestamp | Nonce store hoặc replay-resistant protocol |
| Nonce cache local từng instance | Replay tới instance khác có thể thành công | Shared atomic nonce store |
| So sánh MAC không constant-time | Có thể lộ thông tin qua timing | Constant-time comparison |
| Client tự chọn algorithm | Algorithm confusion/downgrade | Algorithm allowlist gắn với key record |
| Key dùng chung nhiều client | Compromise lan sang nhiều identity | Key riêng cho từng client/tenant |
| Key ID bị coi là secret | Thiết kế sai và lộ metadata không cần thiết | Key ID chỉ là selector, secret/key mới cần bảo vệ |
| Proxy rewrite sau verify | Backend thực thi request khác request đã ký | Verify đúng boundary hoặc giữ signed representation |
| Duplicate header không được xử lý | Gateway/backend hiểu giá trị khác nhau | Reject ambiguity và test proxy chain |
| Không kiểm tra key status | Key revoked vẫn được chấp nhận ở cache cũ | Authoritative status/freshness SLA |
| Signature hợp lệ được coi là authorization | Client ký được action ngoài quyền | PDP/PEP kiểm tra scope và resource |
| Không có idempotency | Retry có thể tạo side effect trùng | Idempotency key và kết quả lưu bền vững |

## 28. Logging, monitoring và incident response

Có thể ghi:
- key ID và client identity reference;
- thuật toán/profile;
- kết quả signature verification;
- timestamp age và clock skew;
- replay/nonce rejection;
- body digest mismatch;
- canonicalization failure reason;
- request/correlation ID;
- resource/action/tenant và authorization result;
- key rotation/revocation event.

Không log:
- HMAC secret;
- private key;
- raw bearer token;
- raw signed request nếu chứa dữ liệu nhạy cảm;
- secret trong header/body;
- full signature nếu không cần và có thể tạo rủi ro correlation.

Metrics:
- signature valid/invalid;
- unknown/revoked key;
- timestamp expired/future;
- nonce replay;
- body digest mismatch;
- per-client request rate;
- key rotation lag;
- verification latency;
- authorization denial sau signature valid.

Khi nghi key compromise:
1. disable/revoke key;
2. ngăn verifier cache key cũ quá SLA;
3. phát hành key mới qua kênh an toàn;
4. xác định request đã được ký trong cửa sổ compromise;
5. kiểm tra action/resource và side effect;
6. revoke session/token liên quan nếu có;
7. thông báo owner và lưu evidence;
8. kiểm tra secret manager, CI/CD, logs và workload runtime.

Không rotate key mà không điều tra phạm vi truy cập của key cũ.

## 29. Kiểm thử request signing

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Request đúng method/path/body/key | Signature hợp lệ; tiếp tục authorization. |
| Method thay đổi sau khi ký | Từ chối. |
| Path thay đổi | Từ chối. |
| Query parameter thay đổi | Từ chối nếu query nằm trong signature input. |
| Authority/host thay đổi | Từ chối theo contract. |
| Body byte thay đổi một ký tự | Digest/signature mismatch. |
| Content-Type thay đổi | Từ chối nếu header được ký. |
| Header tenant hoặc idempotency bị thay đổi | Từ chối nếu component được ký. |
| Signature bị sửa | Từ chối. |
| Key ID không tồn tại | Từ chối. |
| Key đã revoked | Từ chối trên mọi instance theo SLA. |
| Algorithm không nằm trong allowlist | Từ chối. |
| Timestamp quá cũ | Từ chối. |
| Timestamp ở tương lai vượt skew | Từ chối. |
| Expiry đã qua hoặc lifetime quá dài | Từ chối. |
| Nonce đã dùng | Từ chối replay. |
| Hai request cùng nonce tới hai instance | Chỉ một request được chấp nhận. |
| Retry nghiệp vụ với nonce mới và idempotency key cũ | Trả kết quả đã lưu, không lặp side effect. |
| Raw body khác do whitespace | Xử lý theo contract raw bytes/canonical payload đã định nghĩa. |
| Duplicate security header | Từ chối nếu protocol không cho phép. |
| Proxy rewrite path/host | Không làm verifier và backend hiểu hai request khác nhau. |
| HTTP/2 chuyển HTTP/1.1 | Canonicalization vẫn nhất quán theo contract. |
| Compressed body | Digest tính đúng ở representation đã quy định. |
| HMAC comparison | Dùng constant-time primitive. |
| Client có key hợp lệ nhưng scope thiếu | Signature pass, authorization deny. |
| Token hợp lệ nhưng request signature sai | Từ chối nếu endpoint yêu cầu cả hai. |
| Webhook event được gửi lặp | Signature hợp lệ nhưng business processing idempotent. |
| Log review | Không có secret/private key/token hoặc dữ liệu nhạy cảm không cần thiết. |

## 30. Bài tập tình huống

Một đối tác gửi request POST để xác nhận thanh toán. Client ký HMAC trên JSON body nhưng không ký method, path, query hoặc timestamp. API gateway xác minh HMAC rồi chuyển request tới backend. Một middleware có thể rewrite path dựa trên header X-Original-URL. Nonce không được lưu; request timeout thì client gửi lại cùng request. Secret HMAC được dùng chung cho staging và production.

**Yêu cầu phân tích:**

1. Những thành phần nào có thể bị thay đổi mà chữ ký vẫn hợp lệ?
2. Vì sao ký body riêng chưa đủ để ràng buộc request?
3. Cần thiết kế canonical request gồm những component nào?
4. Timestamp và nonce ngăn replay ra sao?
5. Làm thế nào xử lý retry hợp lệ mà không thanh toán hai lần?
6. Vì sao dùng chung secret giữa staging và production nguy hiểm?
7. Gateway và backend cần thống nhất representation như thế nào?
8. Chữ ký hợp lệ có đồng nghĩa thanh toán được phép không?
9. Nếu secret bị lộ, cần revoke và điều tra những gì?

**Hướng phân tích:** Body-only HMAC không ràng buộc method, target URI, authority hoặc các header có ảnh hưởng. Ký method, authority, path/query, content digest, content type, timestamp, expiry, nonce và các component nghiệp vụ quan trọng. Nonce cần được consume atomically trong shared store. Retry dùng nonce mới nhưng idempotency key ổn định; backend trả kết quả đã lưu. Tách key theo environment/client. Gateway và backend phải dùng cùng canonical representation, không để rewrite sau verify làm thay đổi request. Sau signature verification vẫn kiểm tra principal, tenant, scope, trạng thái thanh toán và business rules. Khi key compromise, revoke, rotate, kiểm tra request/side effect và lưu audit.

## 31. Checklist review

- [ ] Request signing có threat model và mục tiêu rõ: authentication, integrity hay cả hai.
- [ ] HMAC và asymmetric signature được chọn theo trust boundary.
- [ ] Key riêng theo client, tenant và environment.
- [ ] Key ID chỉ là selector; key material được bảo vệ riêng.
- [ ] Signature input bao gồm method, authority/target, path/query và body digest phù hợp.
- [ ] Header ảnh hưởng security/business được ký và dùng đúng giá trị đã ký.
- [ ] Canonicalization specification định nghĩa encoding, delimiter, ordering và duplicate handling.
- [ ] Body digest tính trên đúng byte representation đã thỏa thuận.
- [ ] Timestamp, expiry và maximum lifetime được kiểm tra.
- [ ] Nonce được consume atomically và chia sẻ giữa các verifier.
- [ ] Idempotency được tách khỏi nonce/replay protection.
- [ ] HMAC dùng HMAC construction chuẩn, không dùng hash nối secret tự chế.
- [ ] MAC comparison dùng constant-time primitive.
- [ ] Algorithm được allowlist và gắn với key record.
- [ ] Key storage, rotation, overlap và revocation có quy trình.
- [ ] Proxy/gateway không tạo khác biệt giữa signed request và executed request.
- [ ] Duplicate header, path/query normalization và HTTP version translation được kiểm thử.
- [ ] TLS vẫn được dùng để bảo vệ confidentiality và transport.
- [ ] Authorization kiểm tra principal, scope, tenant, resource và business rule sau signature verification.
- [ ] Webhook duplicate delivery được xử lý idempotently.
- [ ] Logs/metrics không chứa secret, private key hoặc token.
- [ ] Có test sửa method/path/query/body/header, replay, race, key revoke và proxy mismatch.

## 32. Ghi nhớ

**Request signing tạo bằng chứng mật mã gắn với những thành phần HTTP đã được ký, giúp server xác minh nguồn gửi kiểm soát key và phát hiện request bị thay đổi.** HMAC dùng shared secret; chữ ký bất đối xứng dùng private key để ký và public key để xác minh. Thiết kế an toàn cần canonical request thống nhất, body digest, key ID và key lifecycle, timestamp/expiry, nonce chống replay, constant-time verification và xử lý proxy nhất quán.

Chữ ký hợp lệ không tự mã hóa request, không ngăn replay nếu thiếu freshness/nonce và không cấp quyền cho action. Sau khi xác minh chữ ký, server vẫn phải kiểm tra authorization trên principal, tenant, resource và business rules.

Khi review, hãy hỏi: **Client đã ký chính xác method, target, header và body nào? Server có dựng cùng byte representation không? Request cũ có thể replay không? Key thuộc client nào và đã bị revoke chưa? Proxy có thay đổi request sau verify không? Chữ ký hợp lệ có đang bị nhầm với quyền thực hiện nghiệp vụ không?**
