# Bảo vệ TLS trên đường truyền

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích vì sao **Transport Layer Security (TLS)** là lớp bảo vệ bắt buộc khi truyền **access token, refresh token, authorization code** và credential của OAuth 2.0.
- Hiểu **confidentiality, integrity, server authentication** mà TLS cung cấp, đồng thời phân biệt chúng với chữ ký JWT, phân quyền API và tính bí mật của token sau khi đã đến đích.
- Mô tả những kết nối cần HTTPS/TLS trong luồng **client – Authorization Server – Resource Server**, kể cả khi có **API gateway, reverse proxy, load balancer** hoặc service mesh.
- Nhận diện lỗi nguy hiểm như gửi Bearer token qua HTTP, bỏ kiểm tra chứng chỉ/hostname, redirect xuống HTTP, lộ token qua URL và cấu hình sai TLS termination.
- Phân biệt **TLS một chiều** với **mutual TLS (mTLS)** và hiểu khi nào certificate-bound access token giúp giảm rủi ro bị sao chép token.
- Thiết kế checklist kiểm thử và vận hành TLS phù hợp với hệ thống Java và API bảo vệ bằng token.

## 1. Vì sao token phải được bảo vệ khi truyền qua mạng?

Một **Bearer access token** thường hoạt động theo nguyên tắc: bên nào đang nắm giữ giá trị token đều có thể thử gửi token đó đến Resource Server. API sẽ kiểm tra issuer, audience, scope, thời hạn, trạng thái và quyền theo tài nguyên, nhưng **bản sao token còn hợp lệ** vẫn có giá trị đối với kẻ tấn công.

Ví dụ một client gửi:

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.test
Authorization: Bearer EXAMPLE_ACCESS_TOKEN
~~~

Nếu request được truyền dưới dạng HTTP không mã hóa trên một mạng mà kẻ tấn công quan sát được, giá trị trong **Authorization header** có thể bị đọc hoặc sao chép. Một bearer token bị đánh cắp có thể bị tái sử dụng cho các request khác cho đến khi token hết hạn, bị thu hồi, hoặc bị cơ chế ràng buộc bên gửi/nghiệp vụ ngăn chặn.

**TLS** tạo một kênh truyền được bảo vệ giữa các đầu mút của kết nối. Với HTTPS, HTTP chạy trên kênh TLS. Khi TLS được thiết lập và xác minh đúng:

- **Confidentiality – tính bí mật:** bên nghe lén mạng không thể đọc nội dung HTTP, bao gồm Bearer token và response, chỉ bằng cách quan sát gói tin.
- **Integrity – tính toàn vẹn:** kẻ tấn công ở giữa không thể âm thầm sửa HTTP request/response trong kênh bảo vệ mà không bị phát hiện theo cơ chế giao thức.
- **Authentication – xác thực đầu mút:** client xác minh mình đang kết nối đến máy chủ có danh tính phù hợp với hostname được yêu cầu và chuỗi tin cậy chứng chỉ.

> **Điểm cốt lõi:** TLS bảo vệ **token đang được truyền qua một kết nối đã xác minh**. TLS không tự kiểm tra quyền nghiệp vụ, không làm token hết hạn và không tự ngăn bản sao token bị đánh cắp từ trình duyệt, log hoặc máy chủ đích.

## 2. TLS ở đâu trong mô hình OAuth 2.0/OIDC?

Một hệ thống thường gồm:

- **Client**: web app, native app, backend service hoặc worker.
- **Authorization Server (AS)**: nơi phát hành token và xử lý authorization code/refresh token.
- **Resource Server (RS)**: nơi nhận access token để bảo vệ API.
- **Identity Provider/OpenID Provider** trong ngữ cảnh OIDC: cung cấp các endpoint và claims xác thực phù hợp.

Các kết nối có thể mang dữ liệu nhạy cảm:

| Luồng | Dữ liệu nhạy cảm có thể đi qua | Yêu cầu bảo vệ |
| --- | --- | --- |
| Trình duyệt ↔ Authorization endpoint | Cookie phiên, trạng thái đăng nhập, authorization code trong redirect, tham số OIDC. | HTTPS/TLS đúng tên host, cookie an toàn, chống nhầm redirect. |
| Client → Token endpoint | Authorization code, PKCE code_verifier, client authentication, refresh token. | **TLS bắt buộc**, kiểm chứng chỉ máy chủ, không ghi request body chứa secret. |
| Client → Resource Server | **Access token** ở Authorization header và dữ liệu nghiệp vụ. | **HTTPS/TLS**, kiểm đúng host/API đích và tránh lộ token ở proxy/log. |
| RS → Introspection endpoint | Token cần tra cứu, credential dùng xác thực RS và kết quả trạng thái. | TLS, xác thực đúng endpoint và chính sách truy cập. |
| Client → Revocation endpoint | Refresh/access token cần thu hồi, thông tin xác thực client nếu có. | TLS và giới hạn dữ liệu log. |
| Service → Service | Access token, user context, kết quả API nhạy cảm. | TLS hoặc mTLS cho hop liên quan, kèm kiểm tra audience và policy. |

Sơ đồ đơn giản:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant AS as Authorization Server
    participant RS as Resource Server
    C->>AS: HTTPS /authorize và /token
    Note over C,AS: TLS bảo vệ code, verifier, client credential, RT
    AS-->>C: Access token / refresh token theo chính sách
    C->>RS: HTTPS + Authorization: Bearer AT
    Note over C,RS: TLS bảo vệ AT trong kết nối
    RS->>RS: Kiểm token, audience, scope, quyền tài nguyên
    RS-->>C: HTTPS + phản hồi nghiệp vụ
~~~

**Authorization code không phải access token** và **refresh token không được gửi đến API nghiệp vụ**. Tuy khác mục đích, cả hai vẫn là credential nhạy cảm trên đường truyền và cần bảo vệ TLS.

Việc triển khai có thể thêm proxy, CDN hoặc gateway. Khi đó sơ đồ một kết nối cần được mở rộng thành **nhiều hop TLS**.

## 3. Một kết nối HTTPS thực sự an toàn cần những gì?

Khi client kết nối tới:

~~~text
https://identity.example.test/oauth2/token
~~~

việc URL bắt đầu bằng **https://** chỉ là bước đầu. Client và server phải hoàn tất một TLS handshake hợp lệ, bao gồm kiểm tra những thuộc tính quan trọng.

### 3.1 Xác minh chuỗi chứng chỉ

Máy chủ xuất trình chứng chỉ và bằng chứng về quyền sở hữu khóa tương ứng. Client xác minh chuỗi chứng chỉ theo **trust store** hoặc chính sách tin cậy được cấu hình.

Nếu chứng chỉ tự ký, không thuộc CA tin cậy hoặc chain thiếu/cấu hình sai, client nên **từ chối kết nối** trừ khi một trust anchor đã được cài đặt an toàn theo quy trình quản trị riêng.

Không tạo một **TrustManager chấp nhận mọi chứng chỉ** chỉ để “fix lỗi SSL”. Khi đó client không còn xác nhận thực sự đã kết nối đến Authorization Server hay máy chủ của kẻ tấn công.

### 3.2 Xác minh hostname của server

Ngay cả khi một chứng chỉ thuộc CA đáng tin, nó vẫn phải phù hợp với **hostname đích** theo quy tắc xác minh tên.

Ví dụ:

~~~text
Endpoint định gọi: identity.example.test
Chứng chỉ chỉ hợp lệ cho: unrelated.example.test
Kết luận: từ chối vì hostname không khớp
~~~

Bỏ kiểm tra hostname làm tăng khả năng kẻ tấn công dùng chứng chỉ hợp lệ cho **tên miền khác** để đánh lừa client.

### 3.3 Giao thức và bộ mã hóa phù hợp

Hệ thống nên dùng phiên bản TLS và cấu hình thuật toán hiện đại được nền tảng hỗ trợ. Trong các hệ thống mới, **TLS 1.3** thường là lựa chọn ưu tiên; **TLS 1.2** vẫn có thể sử dụng khi cấu hình phù hợp. Không nên dựa vào SSL lỗi thời hay phiên bản TLS cũ không đáp ứng baseline bảo mật của tổ chức.

Điều quan trọng không phải chỉ là ghi “hỗ trợ TLS 1.3” trong tài liệu, mà là:

- Dịch vụ thực tế không đàm phán xuống giao thức/cipher bị cấm.
- Chứng chỉ và khóa riêng được quản lý đúng.
- Client và server xác minh các đặc tính phiên TLS cần thiết.
- Các thư viện TLS/runtime được cập nhật để nhận bản vá bảo mật.

### 3.4 Đúng điểm cuối đáng tin

TLS có thể bảo vệ kết nối đến **một host do kẻ tấn công kiểm soát** nếu host đó có chứng chỉ hợp lệ cho tên miền của chính nó. Vì vậy, ngoài kiểm certificate, client còn phải đảm bảo **token endpoint và Resource Server URL đến từ cấu hình/metadata issuer đáng tin**, không phải một tham số URL tùy ý mà người dùng hoặc dữ liệu bên ngoài cung cấp.

TLS xác minh **“đã kết nối đúng tên host này”**; logic ứng dụng phải xác minh **“host này có đúng là AS/RS được phép nhận credential hay không”**.

## 4. Các kiểu thất bại thường gặp ở HTTPS/TLS

| Lỗi | Diễn biến nguy hiểm | Cách xử lý |
| --- | --- | --- |
| Gửi access token qua **http://**. | Người quan sát mạng có thể đọc token và dữ liệu. | Chỉ gửi bearer token tới HTTPS URL đã tin cậy. |
| Tắt certificate validation. | Client có thể kết nối tới máy chủ giả mạo trong tấn công MITM. | Dùng trust store an toàn, không “trust all”. |
| Tắt hostname verification. | Chứng chỉ cho host khác vẫn được chấp nhận. | Bật và giữ xác minh hostname/SAN. |
| Redirect từ HTTPS xuống HTTP kèm Authorization header. | Credential có thể bị gửi qua kênh không mã hóa. | Cấm downgrade và kiểm redirect trước khi chuyển credential. |
| Token trong URL query. | Token có thể vào lịch sử duyệt web, access log, Referer hoặc công cụ analytics. | Ưu tiên Authorization header; không đưa token vào URL. |
| TLS chỉ ở public gateway, hop nội bộ qua HTTP không bảo vệ. | Token có thể bị đọc trên mạng giữa gateway và backend nếu mạng không được tin cậy. | Bảo vệ từng hop cần thiết bằng TLS/mTLS hoặc kênh bảo mật tương đương đã đánh giá. |
| Xác minh server đúng nhưng gửi tới nhầm AS. | Secret/RT được gửi tới endpoint không thuộc issuer mong muốn. | Kiểm issuer, discovery metadata và danh sách URL đích đáng tin. |
| Chứng chỉ hết hạn nhưng client “bỏ qua tạm”. | Việc tắt kiểm có thể kéo dài và phá vỡ mô hình tin cậy. | Sửa vòng đời chứng chỉ và cảnh báo trước hạn. |

**Không có việc “đã dùng HTTPS một lần nên các bước tiếp theo đều an toàn”.** Mỗi kết nối độc lập đến API, proxy hoặc dịch vụ cần bảo đảm ranh giới tin cậy tương ứng.

## 5. HTTP không mã hóa: ví dụ một sự cố bearer token

Giả sử một ứng dụng mobile gọi Orders API như sau:

~~~http
GET http://orders.example.test/api/orders/123 HTTP/1.1
Host: orders.example.test
Authorization: Bearer EXAMPLE_AT
~~~

Đây là **ví dụ lỗi để phân tích**, không phải request nên triển khai.

Trong cùng mạng Wi-Fi công cộng, một kẻ tấn công có khả năng quan sát lưu lượng có thể nhìn thấy bearer token trong HTTP và thử sử dụng nó từ thiết bị khác.

Ngay cả khi access token là JWT có chữ ký hợp lệ, chữ ký **không bảo vệ tính bí mật của token**. Nó giúp RS phát hiện JWT bị sửa trái phép; nó không ngăn kẻ tấn công **sao chép nguyên token hợp lệ**.

Một access token ngắn hạn giảm thời gian token bị lạm dụng, nhưng không biến HTTP thành an toàn. Việc thiết lập transport TLS là **biện pháp phòng ngừa trước khi token được gửi**, chứ không phải phương án khắc phục sau khi lộ.

### Vì sao redirect HTTP → HTTPS không đủ?

Giả sử client gửi Bearer token ngay trong request đầu tiên đến **http://** và server trả:

~~~http
HTTP/1.1 301 Moved Permanently
Location: https://orders.example.test/api/orders/123
~~~

Credential **đã đi qua HTTP ở request đầu tiên**, trước khi client nhận được redirect. Do đó, server redirect sang HTTPS **không sửa được việc token bị lộ trên hop đầu tiên**.

Client nên được cấu hình dùng HTTPS **ngay từ đầu**, tuyệt đối không gửi bearer token đến địa chỉ HTTP với hy vọng redirect sẽ xử lý an toàn.

## 6. Đặt Bearer token đúng chỗ trong HTTP request

Theo RFC 6750, Bearer access token thường được gửi qua **Authorization request header**:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.test
Authorization: Bearer EXAMPLE_ACCESS_TOKEN
Accept: application/json
~~~

Khi URL tương ứng là **https://orders.example.test/api/orders/123**, header và nội dung HTTP được bảo vệ trong kênh TLS giữa các đầu mút TLS.

### Không đặt token trong URL

Một cách truyền token qua query parameter có tồn tại trong RFC 6750 cho các tình huống đặc thù, nhưng **không được khuyến nghị** vì rủi ro rò rỉ. Đối với thiết kế hiện đại, nên tránh:

~~~text
KHÔNG KHUYẾN NGHỊ:
https://orders.example.test/api/orders?access_token=EXAMPLE_ACCESS_TOKEN
~~~

Dù URL trên dùng HTTPS, chuỗi query vẫn có thể xuất hiện trong:

- Lịch sử hoặc bộ nhớ của trình duyệt.
- Log của reverse proxy, gateway, load balancer hoặc công cụ APM.
- Báo cáo analytics và hệ thống theo dõi lỗi.
- URL được người dùng sao chép, chia sẻ hoặc lưu bookmark.
- Một số ngữ cảnh Referer hoặc hệ thống chuyển tiếp URL.

**TLS bảo vệ đường truyền, không xóa token khỏi URL đã được lưu trong hệ thống nhận request.**

### Không dùng Referer, cookie hoặc custom header tùy tiện

Nếu ứng dụng dùng cookie phiên thay vì tự gửi Authorization header, cookie phải có cấu hình phù hợp như **Secure, HttpOnly, SameSite** và chống CSRF/XSS theo mô hình session. **Secure cookie** nhằm tránh gửi cookie qua HTTP không bảo vệ trong điều kiện áp dụng, nhưng không thay thế toàn bộ xác thực và phân quyền.

Nếu API dùng Authorization header, nên dựa vào profile Bearer chuẩn; tránh tạo quy tắc token qua nhiều header khác nhau mà gateway không kiểm soát nhất quán.

## 7. HTTPS/TLS bảo vệ những gì và không bảo vệ những gì?

| Nguy cơ | TLS xử lý được phần nào? | Biện pháp bổ sung |
| --- | --- | --- |
| Nghe lén Bearer token trên đường truyền | **Có**, khi dùng kết nối TLS đúng và được xác minh. | Cấm HTTP; bảo vệ mọi hop. |
| Sửa response/API request bởi MITM trên cùng kênh | **Có**, integrity của TLS ngăn sửa âm thầm. | Xác minh endpoint đúng, cập nhật TLS stack. |
| Gửi token tới server giả có hostname/chứng chỉ không phù hợp | **Có**, nếu certificate/hostname verification hoạt động. | Danh sách endpoint được tin cậy, chống phishing/discovery sai. |
| Token bị đọc từ localStorage bởi XSS | **Không**. | Phòng XSS, CSP, BFF khi phù hợp, giảm quyền token. |
| Token bị ghi nguyên vào access log ở gateway | **Không**. | Redaction, hạn quyền log, không lưu bearer token. |
| Máy chủ TLS đích đã bị chiếm quyền | **Không**. | Hạn quyền, secret management, phát hiện xâm nhập, thu hồi. |
| JWT có chữ ký sai hoặc issuer sai | **Không**. | RS xác minh chữ ký, issuer, audience, profile. |
| Token đúng chữ ký nhưng scope quá rộng | **Không**. | Least privilege và policy theo tài nguyên. |
| Access token đã hết hạn hoặc RT bị thu hồi | **Không**. | Kiểm exp/nbf, introspection, revocation, trạng thái phiên. |
| Bản sao bearer token được dùng từ một kết nối HTTPS khác | **Không tự ngăn**. | Sender-constrained token, TTL, thu hồi, giám sát. |

### TLS và chữ ký JWT là hai lớp khác nhau

- **TLS** bảo vệ request/response **trong lúc di chuyển qua kết nối**.
- **JWS/JWT signature** bảo vệ tính toàn vẹn/xác thực của **nội dung token** theo khóa của issuer; payload JWS thường có thể đọc được.
- **JWE** có thể mã hóa nội dung token trong những mô hình/profile phù hợp, nhưng không thay thế HTTPS.
- **Authorization policy** quyết định quyền thao tác cụ thể; không thể suy từ TLS hoặc chữ ký JWT.

Khi một JWT được bảo vệ bằng TLS, cả hai biện pháp phối hợp: TLS hạn chế sao chép token trên mạng, chữ ký JWT giúp RS kiểm nguồn phát hành và nội dung không bị sửa. Tuy vậy, token vẫn cần **audience, scope, thời hạn và quyền hiện hành**.

## 8. TLS termination ở API Gateway: ranh giới tin cậy di chuyển

Nhiều hệ thống không cho client kết nối TLS trực tiếp tới service Java. TLS có thể kết thúc tại **CDN, ingress controller, reverse proxy hoặc API gateway**, sau đó gateway chuyển request đến backend.

Ví dụ:

~~~mermaid
flowchart LR
    C["Client"] -->|"HTTPS / TLS A"| G["API Gateway"]
    G -->|"HTTPS hoặc mTLS / TLS B"| S["Orders Service"]
    S -->|"mTLS / TLS C nếu cần"| DB["Dịch vụ nội bộ"]
~~~

Mỗi kết nối A, B và C cần được đánh giá độc lập.

### 8.1 Kết thúc TLS không đồng nghĩa mã hóa end-to-end

Ở gateway, request HTTP có thể được giải mã để định tuyến, áp rate limit, xác minh access token hoặc gắn tracing header. Vì vậy:

1. Gateway có thể **nhìn thấy Bearer token ở dạng rõ** sau khi TLS A kết thúc.
2. Nếu gateway chuyển request đến backend qua HTTP không mã hóa, Bearer token có thể được truyền dưới dạng rõ trên mạng nội bộ.
3. Nếu gateway ghi log toàn bộ header, token vẫn bị lộ trong log mặc dù mọi kết nối bên ngoài đều dùng HTTPS.

Cần coi gateway là một **thành phần nằm trong ranh giới tin cậy**, giới hạn quyền vận hành/log và bảo vệ hop nội bộ.

### 8.2 Mạng nội bộ không mặc nhiên đáng tin

“Backend chạy trong VPC/Kubernetes nên HTTP nội bộ đủ an toàn” là một giả định cần được phân tích theo mô hình đe dọa, không phải kết luận mặc định.

Trong môi trường có workload đa nhóm, node bị chiếm quyền, proxy trung gian, overlay network hoặc nhiều tenant, kẻ tấn công có thể có vị trí quan sát lưu lượng nội bộ. Nếu hop mang token/credential, **TLS/mTLS giữa gateway và backend** thường là biện pháp phù hợp.

Ngay cả khi có network policy/firewall, TLS vẫn bổ sung tính bí mật và xác thực endpoint trên mạng. Network segmentation và TLS giải quyết các lớp khác nhau.

### 8.3 Tin header từ gateway như thế nào?

Một gateway có thể gắn header nội bộ như:

~~~text
X-Authenticated-Subject: user-42
X-Forwarded-Proto: https
~~~

Backend **không nên tin các header đó từ request Internet trực tiếp**. Nếu backend dựa vào ngữ cảnh gateway:

- Chặn client ngoài truy cập thẳng backend.
- Gateway phải xóa/ghi đè các header có thể bị client tự đặt.
- Kênh gateway → backend phải được xác thực/bảo vệ theo kiến trúc.
- Có hợp đồng rõ header nào là metadata định tuyến và header nào mang danh tính đã xác minh.
- Nếu backend tự xác minh access token, vẫn phải kiểm issuer, audience, scope và quyền tài nguyên.

Đặc biệt, **X-Forwarded-Proto: https không chứng minh kết nối từ client thực sự an toàn** khi header có thể bị giả mạo. Ứng dụng chỉ nên dùng thông tin forwarded từ proxy tin cậy đã cấu hình rõ.

## 9. mTLS: xác thực hai đầu của kết nối

**TLS một chiều** thường cho phép client xác thực danh tính máy chủ. **Mutual TLS (mTLS)** bổ sung việc server yêu cầu và xác minh chứng chỉ của client trong TLS handshake.

Trong service-to-service, mTLS có thể giúp:

- Xác minh một workload hoặc service đang kết nối tới workload/service khác theo định danh chứng chỉ.
- Bảo vệ dữ liệu trên đường truyền giữa các dịch vụ.
- Giảm nguy cơ service giả mạo trong mạng nội bộ khi chính sách chứng chỉ được vận hành đúng.

Tuy nhiên, **mTLS kết nối** và **mTLS-bound access token** không hoàn toàn đồng nghĩa.

### mTLS-bound access token trong OAuth 2.0

RFC 8705 mô tả những cơ chế mTLS trong OAuth 2.0, gồm xác thực client tại AS và **certificate-bound access token** trong profile phù hợp.

Ví dụ về mục đích:

~~~text
AS cấp access token cho client A, ràng buộc với chứng chỉ C_A.

Yêu cầu API:
    Access token = AT_A
    TLS client certificate = C_A
    => RS kiểm ràng buộc token-chứng chỉ thành công (nếu các điều kiện khác đạt).

Kẻ tấn công chỉ sao chép AT_A, không có khóa của C_A:
    TLS client certificate không khớp / không chứng minh được khóa.
    => RS từ chối nếu sender binding được thực thi đúng.
~~~

Điều quan trọng là **Resource Server thực sự xác minh ràng buộc token với chứng chỉ client**, không chỉ bật TLS. Có mTLS ở một đoạn kết nối nhưng không kiểm binding của token thì bản sao bearer token có thể vẫn được dùng qua một kênh khác.

Trong hệ thống qua gateway, cần thiết kế ai thấy client certificate, ai xác minh binding và ngữ cảnh xác thực truyền tới backend có đáng tin không. Không tự suy rằng backend có thể dùng một header client certificate từ Internet làm bằng chứng mTLS.

### DPoP có thay TLS không?

**DPoP** (RFC 9449) là một cơ chế proof-of-possession ở lớp ứng dụng, có thể ràng buộc token với khóa của client và request khi đúng profile. DPoP **không thay thế TLS**: proof và token vẫn cần được truyền qua kênh HTTPS an toàn, và RS phải kiểm proof, thời gian, phương thức/URI, ràng buộc token cùng chống phát lại theo quy định.

Cả mTLS và DPoP đều có giới hạn nếu chính **môi trường sở hữu khóa** bị xâm nhập. Chúng giảm nguy cơ lạm dụng **bản sao token đơn thuần**, không thể bảo đảm không có tấn công nào xảy ra.

## 10. HTTPS và đăng nhập OIDC: tránh lộ credential ở các redirect

Luồng Authorization Code + PKCE sử dụng nhiều loại dữ liệu khác nhau:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant A as Authorization Server
    participant C as Client backend
    participant R as Resource Server

    B->>A: HTTPS /authorize
    A-->>B: HTTPS redirect với authorization code và state
    B->>C: HTTPS /callback?code=...&state=...
    C->>A: HTTPS POST /token với code, verifier và client auth phù hợp
    A-->>C: Access token (+ refresh/ID token khi được cấp)
    C->>R: HTTPS API call với access token
    R-->>C: HTTPS response
~~~

Ví dụ trên minh họa **confidential client/BFF** có backend đổi code. Với SPA/native public client, cách nhận/đổi code khác đôi chút nhưng vẫn cần HTTPS/TLS ở các endpoint phù hợp.

### Không đưa access token vào fragment hoặc URL tùy tiện

Trong thiết kế hiện đại, **Authorization Code flow** thường được ưu tiên hơn các luồng trả access token trực tiếp qua user agent. Authorization code cũng nhạy cảm và cần:

- Redirect URI được đăng ký và so khớp chính xác theo yêu cầu giao thức.
- PKCE (thường dùng S256) để ràng buộc việc đổi code.
- Kiểm **state** để liên kết response với yêu cầu ban đầu, chống nhầm phiên/CSRF theo ngữ cảnh.
- HTTPS ở các callback web được áp dụng theo profile; các ngoại lệ loopback redirect cho native app cần tuân thủ tiêu chuẩn riêng, không suy rộng thành cho phép HTTP trên Internet.
- Loại bỏ hoặc giảm lưu trữ code trong logs, Referer và telemetry.

Nếu nhận được **ID token OIDC**, client cần xác minh ID token theo OIDC; nó không thể dùng làm access token cho Resource Server. TLS bảo vệ quá trình truyền ID token nhưng không thay kiểm **iss, aud, exp, nonce** và các điều kiện liên quan.

### HSTS và HTTPS-only

**HTTP Strict Transport Security (HSTS)** giúp trình duyệt đã biết chính sách chỉ truy cập một host bằng HTTPS trong phạm vi hiệu lực. HSTS hỗ trợ chống downgrade ở web, nhưng:

- Không thay certificate validation.
- Không làm client API tùy ý tự động tuân thủ nếu client không thực thi HSTS.
- Không khắc phục request chứa token đã từng đi qua HTTP trước khi trình duyệt biết chính sách, nếu không có cơ chế bootstrap như preload phù hợp.
- Không thay thế cấu hình endpoint URL là HTTPS ngay từ đầu.

Với client backend/mobile, nên thực thi chính sách **HTTPS-only ngay ở code/cấu hình**, không chỉ trông đợi trình duyệt hoặc redirect.

## 11. Java: gọi token endpoint và API qua HTTPS

Đối với ứng dụng Java, **java.net.http.HttpClient** có khả năng dùng HTTPS với cấu hình TLS của Java runtime. Ví dụ dưới đây minh họa client gửi yêu cầu refresh qua HTTPS. Đoạn mã **không tự triển khai OAuth**, không có credential thật và chỉ trình bày xử lý kết nối cơ bản.

~~~java
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public final class SafeTokenTransportExample {

    static String encode(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }

    static HttpResponse<String> refreshAccessToken(
            URI tokenEndpoint,
            String refreshToken) throws Exception {

        if (!"https".equalsIgnoreCase(tokenEndpoint.getScheme())) {
            throw new IllegalArgumentException("Token endpoint must use HTTPS");
        }
        if (!"identity.example.test".equalsIgnoreCase(tokenEndpoint.getHost())) {
            throw new IllegalArgumentException("Unexpected token endpoint host");
        }

        String body =
                "grant_type=refresh_token&refresh_token=" + encode(refreshToken);

        HttpRequest request = HttpRequest.newBuilder(tokenEndpoint)
                .header("Content-Type", "application/x-www-form-urlencoded")
                .header("Accept", "application/json")
                .timeout(Duration.ofSeconds(10))
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();

        return client.send(request, HttpResponse.BodyHandlers.ofString());
    }

    private SafeTokenTransportExample() {}
}
~~~

**Giới hạn và hướng áp dụng:**

- Host **identity.example.test** là host giả, đóng vai trò **allowlist minh họa**. Trong triển khai thật, so khớp URL/issuer/token endpoint theo metadata đáng tin, không chỉ so domain một cách tùy tiện.
- Ví dụ **không triển khai client authentication**, DPoP proof, rotation, xử lý response nhạy cảm hoặc secret store. Các thành phần này phải được bổ sung tùy loại client và profile AS.
- Mặc định Java HTTPS phải được để **xác minh trust chain và hostname**; không tạo SSLContext/TrustManager bỏ qua chứng chỉ để vượt lỗi kết nối.
- **followRedirects(NEVER)** là một lựa chọn phòng ngừa để không tự chuyển credential sang endpoint khác. Nếu quy trình có redirect hợp lệ, phải đánh giá và xử lý rõ, không tự chuyển tiếp request chứa token.
- **Không log body**, giá trị refreshToken hoặc nội dung token response. Trong ứng dụng thật, cần parse response, cập nhật RT một cách nhất quán và giữ credential trong nơi lưu bảo vệ.
- Nếu client dùng mTLS, private_key_jwt hoặc client_secret_basic, cần thêm cấu hình xác thực client đúng profile và bảo vệ khóa/secret.
- Những giá trị timeout chỉ là ví dụ vận hành, không phải giá trị chuẩn của OAuth.

### Một request API cũng phải dùng HTTPS

~~~java
import java.net.URI;
import java.net.http.HttpRequest;

static HttpRequest buildApiRequest(URI apiUri, String accessToken) {
    if (!"https".equalsIgnoreCase(apiUri.getScheme())) {
        throw new IllegalArgumentException("API URI must use HTTPS");
    }
    if (!"orders.example.test".equalsIgnoreCase(apiUri.getHost())) {
        throw new IllegalArgumentException("Unexpected API host");
    }

    return HttpRequest.newBuilder(apiUri)
            .header("Authorization", "Bearer " + accessToken)
            .GET()
            .build();
}
~~~

Đây là minh họa **chặn HTTP và nhầm host trước khi gửi token**. Triển khai thật phải bảo đảm không ghi toàn bộ HttpRequest/Authorization header vào debug log, và HttpClient sử dụng TLS validator mặc định/được cấu hình an toàn.

## 12. Certificate pinning: có nên áp dụng cho mobile app?

**Certificate/public-key pinning** là cơ chế thêm điều kiện tin cậy cho một server hoặc tập khóa/chứng chỉ cụ thể, nhằm giảm rủi ro khi một CA tin cậy bị cấp sai. Tuy nhiên, nó tạo chi phí vận hành:

- Server đổi chứng chỉ hoặc khóa có thể làm ứng dụng cũ mất kết nối.
- Cần chiến lược backup pin, xoay vòng, giám sát và phục hồi.
- Pinning không chữa được XSS, malware hay token bị lấy ở client.
- Nếu triển khai sai, pinning có thể khiến người dùng mất khả năng đăng nhập hoặc refresh token trong sự cố chứng chỉ.

Vì vậy, pinning không phải yêu cầu mặc định cho mọi ứng dụng. Chỉ nên xem xét theo mô hình rủi ro, khả năng cập nhật app và quy trình quản trị khóa. **Không dùng pinning để thay certificate/hostname validation chuẩn**.

## 13. Vấn đề vòng đời chứng chỉ và khóa

TLS sẽ không ổn định nếu certificate/secret chỉ được cấu hình một lần rồi bỏ mặc.

Các trách nhiệm cần vận hành:

| Hạng mục | Yêu cầu |
| --- | --- |
| **Cấp phát chứng chỉ** | Tên host/SAN đúng, CA hoặc trust anchor đúng, chứng chỉ không nằm trong danh sách bị cấm theo chính sách. |
| **Thời hạn** | Theo dõi ngày hết hạn, tự động gia hạn khi khả thi, có cảnh báo trước hạn. |
| **Khóa riêng TLS** | Giới hạn truy cập, bảo vệ tại gateway/server, tránh đưa vào image hoặc repo. |
| **Gia hạn/rotation** | Có kiểm thử và giai đoạn chuyển đổi an toàn, tránh downtime do client không tin khóa/chứng chỉ mới. |
| **Trust store client** | Cập nhật danh sách CA tin cậy; không thêm trust anchor tùy ý từ dữ liệu ngoài. |
| **Môi trường thử nghiệm** | Dùng CA nội bộ đáng tin đúng cách, không “trust all” rồi để cấu hình lọt sang production. |
| **TLS library/runtime** | Cập nhật bản vá, loại bỏ TLS/cipher yếu và phát hiện lỗi bắt tay TLS. |
| **mTLS identity** | Quản lý vòng đời chứng chỉ client, chính sách phân quyền theo identity và xác minh certificate-bound token nếu dùng. |

**Chứng chỉ TLS và khóa ký JWT có thể là hai bộ khóa khác nhau.** Chứng chỉ TLS xác thực server ở tầng transport; khóa ký JWT xác minh issuer của token. Không được coi việc xoay khóa TLS tự động thu hồi JWT, hay việc xoay khóa JWT tự sửa cấu hình TLS.

## 14. Mô hình rủi ro: đánh cắp, phát lại và bảo vệ nhiều lớp

Một bearer token bị lộ vẫn có thể được sử dụng trên **một kết nối HTTPS khác**, vì HTTPS chỉ bảo vệ kênh truyền của mỗi request.

~~~text
10:00  AS cấp AT còn hạn 15 phút.
10:01  Client gửi AT qua HTTPS hợp lệ tới Orders API.
10:02  Một debug log tại gateway ghi nguyên Authorization header.
10:03  Người có quyền đọc log lấy AT.
10:04  Kẻ tấn công dùng AT qua HTTPS từ máy riêng.
10:05  RS xác minh chữ ký/exp và có thể chấp nhận nếu không có giới hạn khác.
~~~

Ở ví dụ này, **TLS đã hoạt động đúng trên đường truyền** nhưng token vẫn bị đánh cắp từ log. Các biện pháp bổ sung cần đánh giá:

1. **Không log token:** redact Authorization header, refresh token, authorization code, client secret và token response.
2. **Audience và scope hẹp:** token bị lộ chỉ có thể thử tác động phạm vi nhỏ nhất.
3. **Thời hạn thích hợp:** access token sống ngắn giảm cửa sổ lạm dụng.
4. **Revocation/kiểm trạng thái:** có cách chặn token trước exp theo yêu cầu rủi ro.
5. **Sender-constrained access token:** DPoP/mTLS-bound token khi phù hợp với mô hình client.
6. **Permission hiện hành:** RS vẫn kiểm quyền trên từng tài nguyên và tenant.
7. **Giám sát bất thường:** token sử dụng sai audience, hành vi API bất thường, nhiều lỗi xác thực, dấu hiệu sử dụng trên các thiết bị/phiên bất thường theo chính sách riêng tư.
8. **Phản ứng sự cố:** thu hồi token/phiên, khóa client bị ảnh hưởng, xoay secret và điều tra nguồn rò rỉ.

**TLS làm giảm khả năng token bị lấy trên đường truyền; nó không biến bearer token thành proof-of-possession token.**

## 15. Kiểm thử TLS cho hệ thống dùng token

Cần kiểm tra cả **positive** (kết nối hợp lệ hoạt động) và **negative** (kết nối không an toàn bị từ chối).

| Tình huống | Kết quả kỳ vọng |
| --- | --- |
| Client gọi AS token endpoint qua HTTPS với chứng chỉ và hostname đúng. | TLS handshake thành công; grant tiếp tục được đánh giá theo OAuth. |
| Client cấu hình **http://** cho token endpoint. | Bị chặn **trước khi gửi** refresh token/client credential. |
| Client cấu hình **http://** cho Orders API. | Bị chặn trước khi thêm/sử dụng Authorization header. |
| Chứng chỉ máy chủ không thuộc trust store đáng tin. | Client từ chối TLS handshake, không gửi token. |
| Chứng chỉ thuộc CA đáng tin nhưng hostname không khớp. | Client từ chối, không tắt hostname verification. |
| Chứng chỉ hết hạn. | Client từ chối và báo lỗi vận hành; không bật trust-all. |
| Proxy trả redirect xuống HTTP hoặc sang host khác. | Client không tự chuyển tiếp Authorization header/refresh token. |
| TLS chỉ kết thúc ở gateway, backend hop không mã hóa. | Báo rủi ro và áp kênh bảo vệ theo mô hình đe dọa; không mặc nhiên coi mạng nội bộ an toàn. |
| Client Internet tự gửi **X-Forwarded-Proto: https**. | Gateway/backend không dùng header giả này làm bằng chứng bảo mật. |
| Access token được đặt vào query string. | Kiểm tra/lint/test cảnh báo hoặc chặn theo policy; không đưa token vào URL. |
| Gateway access log chứa request Authorization. | Token được redact; không có chuỗi bearer thật trong logs/telemetry. |
| Public client lưu secret cố định và dùng HTTPS. | HTTPS không biến secret nhúng thành bí mật đáng tin; áp đúng mô hình public client. |
| mTLS-bound access token đi kèm chứng chỉ sai. | RS từ chối theo certificate binding. |
| DPoP-bound access token thiếu proof hoặc proof sai. | RS từ chối theo DPoP profile. |
| JWT ký hợp lệ nhưng **aud** khác API. | RS từ chối dù TLS và chữ ký đều hợp lệ. |
| Access token đã exp hoặc bị thu hồi theo policy. | RS từ chối theo quy tắc thời gian/trạng thái; TLS không làm token còn hạn. |

### Kiểm tra kết nối từ command line

Ví dụ dùng curl để quan sát TLS với endpoint **không chứa credential**:

~~~bash
curl --verbose https://identity.example.test/.well-known/openid-configuration
~~~

Tùy hạ tầng, URL discovery khác nhau. Cách kiểm tra này có thể cho biết kết nối có thiết lập HTTPS và chứng chỉ được xác minh bởi môi trường công cụ hay không.

**Không dùng tùy chọn bỏ xác minh chứng chỉ như cách khắc phục lâu dài.** Không đặt refresh token/client secret trực tiếp vào tham số dòng lệnh khi có nguy cơ bị lưu vào shell history hoặc lộ qua danh sách tiến trình. Với kiểm thử credential thực, dùng công cụ/quy trình bảo mật và tránh lưu token trong log test.

## 16. Một kịch bản end-to-end: Gateway và Orders Service

Giả sử ứng dụng Java có:

~~~text
Browser / SPA
    |
    | HTTPS
    v
API Gateway (TLS termination, JWT validation)
    |
    | mTLS
    v
Orders Service (Java)
    |
    | TLS/mTLS theo profile
    v
Policy/Identity Service
~~~

Hệ thống có các yêu cầu:

- Người dùng đăng nhập qua Authorization Server bằng Authorization Code + PKCE.
- Client chỉ gửi Bearer access token đến URL HTTPS của gateway.
- Gateway kiểm tra token và có thể chuyển ngữ cảnh xác thực đến Orders Service qua hop được bảo vệ, hoặc Orders Service tự kiểm token theo hợp đồng.
- Orders Service kiểm quyền **orders:read** trên đơn hàng và tenant cụ thể.
- Nếu cần introspection, đường RS → AS cũng sử dụng TLS và xác thực endpoint.
- Refresh token chỉ được gửi tới **token endpoint** của AS, không đi vào Orders API.

### Một sự cố cấu hình

Nhóm vận hành vô tình đổi gateway → Orders Service từ **mTLS** sang **HTTP** để giảm chi phí CPU. Trong khi đó gateway chuyển tiếp nguyên header Authorization và Orders Service chạy trên mạng chung với nhiều workload.

Dù client → gateway dùng HTTPS hoàn chỉnh, **hop nội bộ giờ không được mã hóa**. Nếu một workload bị xâm nhập có thể quan sát lưu lượng nội bộ, bearer token và dữ liệu nhạy cảm có nguy cơ bị đọc.

Hướng xử lý:

1. Khôi phục kênh TLS/mTLS hoặc kiểm soát transport tương đương đã được đánh giá và phê duyệt theo threat model.
2. Rà soát cấu hình ingress/egress để không có đường đi bypass gateway.
3. Kiểm tra log, telemetry, packet capture hoặc công cụ debug để đảm bảo không lưu token.
4. Xem xét token nào có thể đã bị lộ; thu hồi/giới hạn theo quy trình sự cố.
5. Kiểm tra audience, scope và quyền tại Orders Service để giảm thiệt hại nếu token đã bị sao chép.
6. Thiết lập test/cảnh báo ngăn cấu hình hop nội bộ không an toàn quay trở lại.

**Bài học:** Đường truyền an toàn là một **chuỗi các kết nối tin cậy**; bảo vệ chỉ ở điểm vào public không tự tạo ra bảo mật cho mọi hop phía sau.

## 17. Những ngộ nhận thường gặp

**“JWT đã ký nên không cần HTTPS.”** Sai. Chữ ký JWT không che payload và không ngăn người khác sao chép Bearer token; HTTPS bảo vệ token khi truyền.

**“Token ở Authorization header thì tự được mã hóa.”** Sai nếu kết nối là HTTP. Header chỉ được bảo vệ khi đi qua kênh TLS đã thiết lập đúng.

**“Có chứng chỉ HTTPS là đủ.”** Chưa đủ. Client phải xác minh trust chain/hostname và tin đúng endpoint. TLS không ngăn rò rỉ ở log và server đích.

**“Mạng nội bộ an toàn nên gateway → backend không cần bảo vệ.”** Không phải mặc định. Cần threat model và phân tích mọi hop mang credential.

**“HTTP redirect sang HTTPS sẽ bảo vệ token.”** Không nếu token đã xuất hiện trong request HTTP đầu tiên.

**“mTLS ở gateway nghĩa là access token đã sender-constrained.”** Không tự động. Resource Server phải kiểm chứng ràng buộc token với client certificate theo profile nếu đó là mục tiêu.

**“DPoP cho phép bỏ HTTPS.”** Không. Proof-of-possession ở lớp ứng dụng không thay thế kênh TLS an toàn.

**“CORS/HSTS/cookie Secure tự giải quyết toàn bộ bảo mật token.”** Các cơ chế này giải quyết các vấn đề khác nhau; vẫn cần xác minh token, session, CSRF/XSS, audience, scope và permission.

**“Token bị đánh cắp không dùng được vì kẻ tấn công sẽ phải kết nối HTTPS.”** HTTPS không biết người gửi có phải chủ sở hữu hợp pháp của Bearer token hay không. Cần sender-constraining hoặc biện pháp kiểm soát khác nếu muốn giới hạn việc sử dụng bản sao.

## 18. Bài tập tự đánh giá

**Tình huống A.** Mobile app gửi Bearer token qua **http://api.example.test**, server trả redirect 301 sang HTTPS. Token đã được bảo vệ chưa?

**Gợi ý:** Chưa. Request đầu tiên chứa token đã đi qua HTTP. Phải dùng HTTPS từ đầu và ngăn mọi request mang credential qua HTTP.

**Tình huống B.** Backend dùng HTTPS với máy chủ nhưng bỏ xác minh hostname để kết nối được với chứng chỉ của môi trường staging. Có an toàn không?

**Gợi ý:** Không. Chứng chỉ hợp lệ cho host khác không chứng minh host đích mong muốn. Phải cấp chứng chỉ đúng hostname hoặc cấu hình trust store/dns đúng cách.

**Tình huống C.** Gateway nhận HTTPS và chuyển access token tới backend qua HTTP nội bộ. Đội kỹ thuật nói toàn bộ luồng là “HTTPS end-to-end”. Có chính xác không?

**Gợi ý:** Không. TLS đã kết thúc tại gateway. Cần xem xét kết nối mới gateway → backend và bảo vệ riêng hop đó.

**Tình huống D.** API chỉ dùng Bearer token, truy cập bằng HTTPS. Kẻ tấn công có được token từ log gateway và gọi API bằng HTTPS trên máy mình. HTTPS sẽ chặn được chứ?

**Gợi ý:** Không tự chặn. Cần không log token, hạn token, thu hồi, scope/audience hẹp và xem xét DPoP/mTLS-bound access token.

**Tình huống E.** Một Resource Server dùng mTLS nhưng không kiểm access token có bị ràng buộc với chứng chỉ client hiện tại hay không. Bản sao token có an toàn tuyệt đối không?

**Gợi ý:** Không. mTLS xác thực kênh/client theo cấu hình; nếu mục tiêu là sender-constrained token, phải thực thi binding giữa token với chứng chỉ.

## 19. Checklist triển khai bảo vệ TLS trên đường truyền

Trước khi triển khai hoặc kiểm toán một hệ thống token security:

1. **Tất cả đường có credential:** Đã lập danh sách kết nối mang access token, refresh token, code, code_verifier, client secret và response nhạy cảm chưa?
2. **HTTPS-only:** Mọi AS/RS/token/introspection/revocation endpoint được gọi qua HTTPS an toàn chưa? Có chặn HTTP trước khi gửi credential không?
3. **Certificate/hostname validation:** Có dùng trust store phù hợp và xác minh tên máy chủ không? Có cấu hình trust-all hoặc bỏ hostname verification nào còn sót không?
4. **TLS baseline:** Có giới hạn giao thức/cipher phù hợp, cập nhật runtime và theo dõi lỗi TLS không?
5. **Endpoint trust:** URL từ cấu hình hoặc discovery issuer đáng tin, thay vì URL do người gửi tùy ý cung cấp chưa?
6. **Redirect:** Có ngăn chuyển Authorization header, refresh token hoặc client secret sang host khác/HTTP khi redirect không?
7. **TLS termination:** Đã xác định rõ proxy/gateway/CDN nào nhìn thấy token ở dạng rõ và ai vận hành các thành phần đó chưa?
8. **Hop nội bộ:** Gateway → backend và service → service có kênh được bảo vệ theo threat model không?
9. **Header tin cậy:** Có loại bỏ header giả từ Internet và chỉ tin proxy đã định danh không?
10. **Lưu/ghi log:** Token không nằm trong URL, access log, tracing, telemetry, crash dump hoặc body log chứ?
11. **Sender binding:** Khi dùng mTLS-bound token/DPoP, AS và RS có kiểm ràng buộc đúng profile không?
12. **Quyền token:** Dù TLS an toàn, RS vẫn kiểm issuer, audience, exp/nbf, scope, trạng thái và permission theo tài nguyên chưa?
13. **Vòng đời chứng chỉ:** Chứng chỉ/khóa có cơ chế gia hạn, xoay vòng, cảnh báo và thử nghiệm trước khi hết hạn không?
14. **Sự cố:** Có thể phát hiện TLS misconfiguration, thu hồi token nghi lộ và kiểm tra blast radius trong thời gian phù hợp không?
15. **Kiểm thử:** Có negative tests cho HTTP, chứng chỉ sai, hostname sai, redirect xuống HTTP, lộ log, sai audience và thiếu sender proof không?

## Kết luận

**TLS là lớp bảo vệ không thể thiếu trên đường truyền khi sử dụng Bearer token**. HTTPS được cấu hình đúng giúp mã hóa nội dung HTTP, kiểm tra tính toàn vẹn và xác minh máy chủ nhận credential. Mọi kết nối có thể mang token — từ client tới AS/RS, qua API gateway và giữa các dịch vụ — cần được đánh giá riêng; TLS ở một hop không tự bảo vệ hop kế tiếp.

Tuy nhiên, **TLS không biến Bearer token thành bằng chứng sở hữu riêng của client**. Token vẫn có thể bị lộ tại đầu cuối, trong log, trình duyệt hoặc môi trường bị xâm nhập. Thiết kế OAuth 2.0/OIDC an toàn cần kết hợp TLS với **client authentication, PKCE, audience và scope hẹp, thời hạn token, thu hồi, lưu trữ an toàn, sender-constraining khi phù hợp** và kiểm tra quyền hiện hành tại Resource Server.

### Tài liệu tham khảo

- [RFC 6750 — OAuth 2.0 Bearer Token Usage, Section 5: Security Considerations](https://www.rfc-editor.org/rfc/rfc6750#section-5)
- [RFC 6749 — The OAuth 2.0 Authorization Framework, Section 1.6: TLS Version](https://www.rfc-editor.org/rfc/rfc6749#section-1.6)
- [RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc8446)
- [RFC 9325 — Recommendations for Secure Use of TLS and DTLS](https://www.rfc-editor.org/rfc/rfc9325)
- [RFC 6797 — HTTP Strict Transport Security (HSTS)](https://www.rfc-editor.org/rfc/rfc6797)
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
