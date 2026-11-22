# Phân biệt xác thực HTTP, token ứng dụng và xác thực chứng chỉ TLS

## Mục tiêu bài học

Một hệ thống Java gọi API qua proxy và HTTPS có thể đồng thời gặp **HTTP Basic authentication**, **Bearer access token**, **cookie phiên**, **chứng chỉ TLS của server** và **chứng chỉ TLS của client (mTLS)**. Chúng đều liên quan tới bảo mật, nhưng **không chứng minh cùng một danh tính**, **không được gửi tới cùng một bên**, và **không hoạt động ở cùng một giai đoạn**.

Điểm cốt lõi: **“Xác thực HTTP” là khung cơ chế ở tầng HTTP; Bearer token ứng dụng có thể chính là credential của một cơ chế xác thực HTTP.** Vì thế HTTP authentication và token không phải hai lớp loại trừ nhau. Trong khi đó, xác thực bằng chứng chỉ TLS là một hoạt động của **TLS handshake** (trước khi HTTP application data được trao đổi trên kết nối bảo vệ).

Sau bài, bạn có thể:

- Phân biệt **authentication** (xác định peer/user/service), **authorization** (kiểm tra quyền) và **confidentiality/integrity** (bí mật/toàn vẹn khi truyền).
- Hiểu **401 + WWW-Authenticate + Authorization** dành cho *origin server* và **407 + Proxy-Authenticate + Proxy-Authorization** dành cho *forward proxy*.
- Phân biệt **HTTP Basic** với **HTTP Bearer**; Basic dùng Base64, **không phải mã hóa**; bearer token cho phép người giữ token sử dụng quyền trong phạm vi của nó.
- Hiểu **access token**, **ID token**, **refresh token**, session cookie, token dạng opaque và token dạng JWT; không đánh đồng một JWT có ba phần với một token đã được xác thực.
- Giải thích xác thực chứng chỉ **TLS server** (client kiểm tra CA/truststore + tên/SAN) và **mTLS** (server thêm bước yêu cầu, kiểm tra client certificate).
- Hiểu **proxy CONNECT**, reverse proxy/TLS termination và giới hạn của việc chuyển tiếp danh tính client qua header.
- Cấu hình đúng các API Java 17+: `HttpClient`, `HttpRequest`, `com.sun.net.httpserver.BasicAuthenticator`, `SSLContext`, `KeyManagerFactory`, `TrustManagerFactory` và `SSLSocket`.
- Chạy hai chương trình độc lập: **HTTP Basic/Bearer trên loopback** và **TLS 1.3 mTLS với chứng chỉ thử nghiệm** đã kiểm tra bằng JDK 17-compatible compiler.

**Phạm vi:** HTTP và proxy trong module Java networking. Các ví dụ khóa/password/token là **giả lập dành riêng cho 127.0.0.1**, không được dùng để vận hành một dịch vụ thật. HTTPS/TLS, certificate validation, secret management và phân quyền bắt buộc phải triển khai đúng khi xử lý dữ liệu nhạy cảm.

## 1. Ba câu hỏi bảo mật khác nhau

| Câu hỏi | Thuật ngữ | Ví dụ |
|---|---|---|
| “Bạn là ai, và làm sao chứng minh?” | **Authentication — AuthN** | Password qua Basic, session, Bearer token, certificate client |
| “Danh tính ấy có được gọi API này không?” | **Authorization — AuthZ** | Role, scope `orders:read`, ACL, policy theo tài nguyên |
| “Dữ liệu trên đường truyền có bị đọc/sửa không?” | **Confidentiality / integrity** | HTTPS/TLS bảo vệ application data trong một kênh |

**AuthN không tự tạo AuthZ.** Một chứng chỉ client được CA nội bộ tin cậy có thể xác nhận peer là một service cụ thể, nhưng không có nghĩa service ấy được gọi mọi endpoint. Một access token hợp lệ có thể chỉ cho phép đọc, không cho phép xóa. Ngược lại, chỉ mã hóa TLS thành công tới một server **không** chứng minh token ứng dụng đã được server chấp nhận.

### Tầng giao thức và đích xác thực

~~~text
Java client
   │
   │ 1. Có thể cần xác thực PROXY để được chuyển tiếp kết nối
   ├── HTTP proxy authentication: 407 ↔ Proxy-Authorization
   │
   │ 2. Tạo TLS session tới HTTPS endpoint thực sự
   ├── TLS server certificate validation (client kiểm tra server)
   ├── [tùy cấu hình] mTLS client certificate validation
   │
   │ 3. Trao đổi HTTP requests bên trong TLS tunnel/session
   └── Authorization: Basic ... / Bearer ...
             hoặc Cookie: session=...
                    │
                    ▼
              Origin/API server
              AuthN → AuthZ → xử lý nghiệp vụ
~~~

Các bước trong sơ đồ mang tính mô hình. Khi **reverse proxy chấm dứt TLS**, TLS endpoint có thể là proxy thay vì backend. Khi **forward HTTP proxy thực hiện CONNECT**, phần TLS tới origin thường chạy **bên trong tunnel**; proxy chỉ chuyển bytes TLS mà không phải endpoint giải mã HTTPS thông thường.

**Sự khác biệt về phạm vi:**

- TLS handshake xác thực peer ở **mức kết nối TLS**.
- `Authorization` hoặc `Cookie` gắn với **HTTP request/application session**.
- Proxy credential được trình cho **proxy được chọn**, không phải cho origin.
- HTTP/2 có thể dùng nhiều request/stream trên một TLS connection; một chứng chỉ TLS không biến mọi request thành một quyền ứng dụng duy nhất.

## 2. HTTP authentication framework: challenge và credentials

HTTP định nghĩa khung **challenge–response** giữa client và một server yêu cầu xác thực. Một origin server bảo vệ resource có thể trả:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="private"
Cache-Control: no-store
Content-Length: 0
~~~

Client đã có credentials phù hợp có thể thử lại:

~~~http
GET /private HTTP/1.1
Host: api.example.org
Authorization: Basic ZGVtbzpwb3Nz
~~~

Chuỗi Base64 ở đây chỉ là giá trị **minh họa của credentials giả**, không phải password thật. Một lời thách thức khác có thể dùng `Bearer` hoặc authentication scheme khác.

**`401 Unauthorized` trên thực tế liên quan đến việc thiếu hoặc không chấp nhận thông tin xác thực**, dù chữ “Unauthorized” trong tên có thể gây nhầm. Theo RFC 9110, một origin server gửi `401` **phải** đưa `WWW-Authenticate` với ít nhất một challenge hợp lệ cho resource.

Sau khi client đã được xác thực nhưng **không đủ quyền**, origin server thường trả `403 Forbidden`. Một ứng dụng có thể cố ý dùng `404 Not Found` để tránh tiết lộ sự tồn tại resource trong một số trường hợp.

### Trường hợp HTTP auth có thực sự là “đăng nhập”?

HTTP authentication framework giúp server yêu cầu chứng thực qua scheme và header, nhưng **không ép mọi ứng dụng phải dùng Basic**. Có thể dùng:
- `Basic` với username/password.
- `Bearer` với một access token do hệ thống ứng dụng/OAuth cung cấp.
- Những scheme khác được HTTP client/server hỗ trợ theo cấu hình.
- Cookie/session hoặc các cơ chế xác thực ứng dụng **ngoài** khung challenge header truyền thống.

Một ứng dụng web hiển thị form login rồi tạo session cookie có thể không dùng header `Authorization` cho mỗi request. Điều đó không làm cookie “trở thành chứng chỉ TLS”. Nó là một cơ chế **duy trì phiên ứng dụng**.

### Header names không phân biệt hoa/thường

`Authorization` và `authorization` chỉ cùng HTTP field name. Nhưng tên **authentication scheme**, cú pháp credential, realm, token và chính sách dùng chúng thuộc từng scheme. Không tự parse các challenge phức tạp bằng tách dấu phẩy đơn giản: nhiều scheme có tham số hoặc nhiều challenge trong một field.

## 3. HTTP Basic: credential username/password, Base64 không mã hóa

RFC 7617 định nghĩa HTTP Basic. Client gửi một giá trị gần dạng:

~~~http
Authorization: Basic ZGVtby11c2VyOmRlbW8tcGFzcw==
~~~

Với ví dụ `demo-user:demo-pass`, phần sau `Basic` là Base64 của chuỗi `username:password`. **Base64 là phép mã hóa biểu diễn để chuyển bytes thành ký tự ASCII, không phải encryption.** Người chặn được header có thể decode ra credentials.

**Vì sao Basic cần TLS?** Nếu gửi Basic qua HTTP plaintext trên mạng thật, kẻ nghe lén có thể lấy password; ngay cả qua HTTPS, password còn có thể bị lộ qua logs, reverse proxies đã giải mã, client memory, dumps hoặc code xử lý sai. Basic không cung cấp bảo vệ replay của credential qua mỗi request khi header bị đánh cắp.

Quy tắc:
1. Chỉ dùng Basic qua kết nối bảo vệ (HTTPS/TLS đúng certificate/hostname verification), ngoại trừ demo trên **loopback**.
2. Không đưa credentials thật vào repository, command-line history, log hoặc URL.
3. Không mặc định mọi request sau đăng nhập mang một `Basic` header; tùy client và chính sách realm/credential reuse.
4. Server cần chính sách lưu password thích hợp (password hash + salt và cơ chế bảo vệ), không lưu literal password như chương trình minh họa.
5. Nếu quyền thay đổi, server vẫn phải đánh giá **authorization** cho mỗi resource; password hợp lệ không có nghĩa mọi resource đều được truy cập.

Trong Java `HttpClient`, `HttpClient.Builder.authenticator(Authenticator)` có thể hỗ trợ quá trình authentication cho các scheme được implementation hỗ trợ, bao gồm các trường hợp origin/proxy thích hợp. **Không** suy ra mọi proxy scheme và mọi phiên bản JDK đều tự hỗ trợ; policy/security properties có thể hạn chế Basic trên HTTPS proxy tunneling. Ví dụ Java hoàn chỉnh ở phần 11 dùng **header giả trên loopback** để người học nhìn rõ ranh giới dữ liệu thay vì phụ thuộc vào quá trình prompt credentials.

### Basic Auth không phải một session token

Một Basic header mô tả **credential username/password** gửi cho HTTP resource/protection space. Trong khi đó session cookie thường chứa một **session identifier** ngẫu nhiên (không chứa password gốc), còn Bearer token là **credential đã được cấp phát** với vòng đời/quyền riêng. Tuy cả ba có thể dùng xác thực application, vòng đời, nguy cơ lộ và cách thu hồi khác nhau.

## 4. Proxy auth: 407 không phải 401

Một forward proxy có thể yêu cầu client xác thực **trước khi cho phép chuyển tiếp**. Khi thiếu proxy credential:

~~~http
HTTP/1.1 407 Proxy Authentication Required
Proxy-Authenticate: Basic realm="office-proxy"
Content-Length: 0
~~~

Client có thể gửi lại request thích hợp với:

~~~http
Proxy-Authorization: Basic ZGVtbzpwcm94eQ==
~~~

Các bytes `Basic` ở đây chỉ minh họa và không phải password/host thật.

| Thuộc tính | Origin authentication | Forward-proxy authentication |
|---|---|---|
| Bên yêu cầu chứng thực | Origin/API server | Forward proxy |
| Response challenge | `401 Unauthorized` | `407 Proxy Authentication Required` |
| Header challenge | `WWW-Authenticate` | `Proxy-Authenticate` |
| Header credentials | `Authorization` | `Proxy-Authorization` |
| Mục tiêu | Chứng thực với tài nguyên/API đích | Chứng thực quyền **dùng proxy** |
| Phạm vi tin cậy | Origin, realm, ứng dụng | Proxy cụ thể / chuỗi proxy được quản lý |
| Có đủ để truy cập API? | Còn tùy AuthZ | **Không**; proxy chấp nhận không có nghĩa origin chấp nhận |

**Lưu ý:** proxy không được thay đổi tùy tiện `Authorization` của request origin. Header `Proxy-Authorization` dành cho proxy, còn `Authorization` dành cho origin. Không gửi cùng bearer access token tới cả hai bên chỉ để “thử cho qua”.

### HTTPS qua forward HTTP proxy và CONNECT

Một chuỗi điển hình khi client kết nối `https://api.example.org` qua một forward HTTP proxy:

~~~text
Java HttpClient             Forward proxy                  Origin
      │                          │                            │
      ├─ CONNECT api.example.org:443 ─────►│                     │
      │  (có thể nhận 407 và xác thực proxy)                     │
      │◄──────── 200 Connection Established ───┤                 │
      │                          │                            │
      ├══════════ TLS ClientHello ════════►│═══════════════►│
      │◄═════════ TLS server certificate ═│════════════════┤
      │  client kiểm tra cert/hostname của origin              │
      ├══════ HTTP Authorization (mã hóa TLS) ═══════════════►│
      │◄══════ HTTP response bên trong TLS ══════════════════┤
~~~

Sơ đồ này mô tả **forward proxy chuyển tiếp tunnel**, không phải một proxy giải mã TLS. Proxy có thể biết mục tiêu `CONNECT`, IP/port và metadata thời gian/lưu lượng; phần body/header HTTP origin sau khi TLS được thiết lập không hiển thị cho proxy tunnel thông thường.

Nếu proxy triển khai **TLS interception** và client tin CA mà proxy dùng để phát hành certificate thay origin, proxy **trở thành TLS endpoint** và có thể nhìn thấy HTTP plaintext. Đây là một trust boundary **khác**, cần chính sách tổ chức rõ ràng; không gọi nó là tunnel TLS end-to-end tới origin.

**Nhầm lẫn hay gặp:** request tới proxy bị `407` không giải quyết được bằng cách thêm `Authorization: Bearer <origin-token>`. Phải dùng đúng proxy credentials/policy; nếu origin sau đó trả `401` thì lại là một vấn đề **khác**.

## 5. Bearer access token: một credential HTTP do ứng dụng cấp

Bearer token thường xuất hiện dưới dạng:

~~~http
GET /orders HTTP/1.1
Host: api.example.org
Authorization: Bearer eyJ...<redacted>
~~~

`<redacted>` ở đây là ký hiệu cho **giá trị đã ẩn**, không phải token thực và không dùng làm ví dụ runnable. RFC 6750 quy định **Bearer authentication scheme** trong HTTP. Bearer nghĩa là **bất kỳ ai sở hữu token hợp lệ** có thể trình nó để sử dụng quyền mà token cấp, trừ khi có thêm ràng buộc (proof-of-possession hoặc policy khác).

Điều quan trọng là **Bearer token chính là một hình thức HTTP authentication** khi truyền qua `Authorization: Bearer ...`. “Token ứng dụng” mô tả **loại credential và cách cấp/quản trị**, còn “HTTP authentication” mô tả **cách credential đi vào request/challenge**. Đây là hai góc nhìn, không phải hai lựa chọn loại trừ.

### Access token khác password và session cookie

| Credential | Ai cấp? | Thường được truyền bằng gì? | Điều cần kiểm tra |
|---|---|---|---|
| Username/password Basic | Tài khoản/identity system | `Authorization: Basic ...` | Credentials, realm, chính sách password |
| Bearer access token | Authorization server / ứng dụng | `Authorization: Bearer ...` | Validity, issuer/audience, expiry, scope/policy |
| Opaque session ID | Application session service | Cookie `session=...` hoặc header riêng | Session đang tồn tại, user, expiry, CSRF nếu cookie browser |
| Client TLS certificate | PKI / CA quản lý | Trong **TLS handshake**, không phải HTTP body | Chain, possession private key, policy mapping |
| Proxy credential | Proxy/identity system | `Proxy-Authorization` | Quyền sử dụng proxy, không phải quyền API origin |

**Token không mặc nhiên là JWT.** Bearer access token có thể là:
- **Opaque token:** một chuỗi không có ý nghĩa tự giải thích; resource server xác minh qua session store/introspection/authorization service.
- **JWT signed token (JWS):** token có cấu trúc claims được ký, resource server có thể xác minh signature và các claims theo chính sách; JWT thường **chỉ được ký chứ không mã hóa**, payload có thể decode được bởi người nhìn thấy token.
- Một dạng khác do authorization system định nghĩa, miễn tương thích cơ chế bảo vệ/kiểm tra của hệ thống.

**ID token không thay access token:** trong OpenID Connect, ID token cung cấp thông tin **xác thực user cho client**; không tự được dùng thay access token để gọi một API tùy ý. **Refresh token** được dùng theo cơ chế được cấp để xin access token mới và thường có bảo vệ nghiêm hơn; không gửi refresh token vào `Authorization: Bearer` tới resource server nếu API không chỉ rõ điều đó.

### Ví dụ challenge Bearer

Không có token:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders"
Cache-Control: no-store
~~~

Token đã gửi nhưng hết hạn/không hợp lệ có thể được phản hồi:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders", error="invalid_token"
Cache-Control: no-store
~~~

Token hợp lệ nhưng scope không đủ thường có thể là:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders", error="insufficient_scope", scope="orders:write"
Cache-Control: no-store
~~~

Đây là **các ví dụ cú pháp**, không phải lời hứa mọi API đều trả đúng error description như vậy. Status và challenge phải theo hợp đồng API, các yêu cầu RFC 9110 và RFC 6750 khi áp dụng.

**Không dùng query parameter để mang access token** trên hệ thống mới: URL có thể lưu vào browser history, server/proxy logs và analytics. Chọn HTTPS, `Authorization` đúng phạm vi, redaction log, token lifetime ngắn và phương án rotate/revoke. Nếu dùng cookie browser, cần đánh giá thêm `Secure`, `HttpOnly`, `SameSite`, CSRF và session fixation.

## 6. Xác minh token và phân quyền tại resource server

**Nhận thấy một header Bearer không chứng minh token hợp lệ.** Resource server phải validate credential và tạo security principal theo policy của mình, rồi **authorization** mới quyết định hành động được phép.

### Với JWT signed token

Một JWT dạng thường gặp có ba phần được ngăn bởi dấu chấm:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Đây là **dạng biểu diễn phổ biến của JWS Compact**, không phải mọi token đều là JWT và không có nghĩa payload được mã hóa.

Các kiểm tra quan trọng:
1. **Chữ ký hợp lệ** với key đáng tin và thuật toán **allowlisted** theo cấu hình; không chấp nhận thuật toán `none` hoặc biến thể không được phép chỉ vì token khai báo.
2. **Issuer (`iss`)** đúng authorization server kỳ vọng; không tải khóa từ URL bất kỳ trong token mà không có trust policy.
3. **Audience (`aud`)** có resource server/API này — token dành cho API A không được tự chấp nhận ở API B.
4. **Expiry (`exp`)**, **not-before (`nbf`)**, thời gian hệ thống và clock skew chính sách; token quá hạn phải bị loại.
5. **Subject/client identity**, scopes/roles/permissions và constraints theo route/resource.
6. **Key rotation**, giới hạn token lifetime, cách xử lý revocation hoặc claims thay đổi khi cần.
7. **Không nhầm hợp lệ chữ ký với quyền:** một token được ký đúng nhưng chỉ có scope `orders:read` không được dùng xóa đơn hàng.

Dùng **thư viện JWT/OAuth được bảo trì** theo giao thức và policy của tổ chức; không tự viết parser/cryptographic verification bằng split chuỗi đơn giản và `Base64.getDecoder()`. JWT có thể chứa dữ liệu nhạy cảm trong payload đọc được; đừng ghi token gốc vào log.

### Với opaque token

Resource server có thể gọi **token introspection endpoint** hoặc kiểm tra token/session store nội bộ, nhận trạng thái active, subject, audience/scope, expiry. Cần bảo vệ đường kết nối/resource server credentials khi introspection, cache kết quả có thời hạn hợp lý và xử lý revocation theo yêu cầu.

**Bearer token bị đánh cắp** thường có thể được dùng lại bởi một bên khác trong thời hạn hiệu lực. Có những cơ chế **token binding** như OAuth mTLS certificate-bound access token (RFC 8705) hoặc DPoP để giảm khả năng replay token bị lộ. Nhưng **mTLS thuần túy không tự động ràng buộc mọi Bearer token vào client certificate**; cần thiết kế/kiểm tra ràng buộc đó ở tầng authorization.

## 7. TLS server certificate: client xác thực HTTPS endpoint

Khi Java gọi `https://api.example.org`, TLS handshake diễn ra **trước** lúc giao HTTP application request trong kênh. Trong mô hình xác thực server thông thường:
1. Server trình certificate chain (thường X.509) và chứng minh sở hữu private key phù hợp trong handshake.
2. Client xác minh **certificate path/trust anchor**, thời hạn và chính sách cryptography.
3. Client kiểm tra certificate có đại diện cho **hostname kỳ vọng** (thông thường qua SAN DNS/IP phù hợp) hay không.
4. Nếu thành công, client thiết lập traffic keys, bắt đầu trao đổi dữ liệu qua TLS records được mã hóa/xác thực.
5. **Ở thời điểm này, server vẫn chưa nhất thiết biết danh tính user/client ứng dụng**.

Ví dụ:
- Certificate hợp lệ cho `shop.example.org` **không** tự phù hợp khi client kỳ vọng `api.example.org`.
- Kết nối tới IP literal cần kiểm tra identity đúng với IP trong SAN, không chấp nhận DNS name ngẫu nhiên.
- `SNI` giúp server chọn certificate theo tên host trong các triển khai virtual hosting; SNI **không thay thế** hostname validation.
- Certificate trust đúng không có nghĩa server là một dịch vụ “đáng tin về kinh doanh”, hoặc response JSON chắc chắn đúng.

**Java raw SSLSocket:** khi tự tạo client `SSLSocket` thay vì dùng HTTPS-aware `HttpClient`, phải cấu hình endpoint identification (ví dụ `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` cho tên kỳ vọng) cùng TrustManager hợp lệ. HTTPS `HttpClient` bình thường sử dụng xác minh server identity theo TLS/HTTPS policy; **đừng tắt validation** chỉ vì chứng chỉ thử nghiệm không hợp lệ.

Không tạo `X509TrustManager` tin tất cả certificate hoặc `HostnameVerifier` luôn trả true để “sửa lỗi”. Khi certificate mismatch/expired, sửa hostname/SAN, trust anchor, chain hoặc cấu hình PKI đúng.

## 8. TLS client certificate và mTLS: server xác thực peer ở handshake

**Mutual TLS (mTLS)** yêu cầu **cả hai phía** xác thực certificate theo policy:
- Client kiểm tra **server certificate** như ở HTTPS thông thường.
- Server cấu hình yêu cầu **client certificate**, kiểm tra certificate chain/key possession và các ràng buộc cần thiết.
- TLS handshake thất bại nếu certificate bắt buộc không được cung cấp/không được tin cậy, **trước khi có một HTTP 401/403 thông thường ở tầng ứng dụng**.

Ví dụ JSSE:
- Server dùng `KeyManagerFactory` với **private key + server certificate** của mình.
- Server dùng `TrustManagerFactory` với CA/certificate của các **client được tin**.
- Server đặt `SSLServerSocket.setNeedClientAuth(true)` để bắt buộc client certificate.
- Client dùng `KeyManagerFactory` với **private key + client certificate** của mình.
- Client dùng `TrustManagerFactory` với CA/certificate của **server được tin**.
- Client vẫn kiểm tra **hostname/SAN** của server (chứng chỉ server CN/SAN có vai trò khác chứng chỉ client).
- Sau handshake, application lấy peer identity đã được validate rồi **ánh xạ sang principal/permissions** riêng.

**mTLS không mặc định là “đăng nhập người dùng”.** Trong kiến trúc service-to-service, certificate có thể định danh một workload/service/machine; user-facing identity vẫn có thể nằm trong một access token hoặc session. Server có thể chấp nhận certificate của `billing-service` nhưng chỉ cho service ấy gọi `/billing`, không cho gọi `/admin`.

**Server-auth TLS khác mTLS:** HTTPS bình thường có thể chỉ xác thực server; client không cần đưa certificate. Nếu thấy kết nối HTTPS thành công, không thể suy ra server đã xác thực client bằng certificate.

**`setWantClientAuth(true)` khác `setNeedClientAuth(true)`:** “want” chỉ **yêu cầu nếu client có**; “need” yêu cầu bắt buộc, handshake sẽ thất bại nếu client không cung cấp authentication phù hợp. Với API bắt buộc mTLS, dùng need và trust policy đúng.

## 9. Bảng so sánh nhanh theo tầng, credential và thời điểm

| Tiêu chí | HTTP Basic tới origin | Bearer token ứng dụng | TLS server certificate | mTLS client certificate | HTTP proxy authentication |
|---|---|---|---|---|---|
| Tầng chính | HTTP request/challenge | HTTP request/application | TLS handshake | TLS handshake | HTTP proxy exchange |
| Ai chứng thực với ai? | Client/user tới origin | Client/user/service tới API | Server tới client | Client tới server (và server tới client) | Client tới forward proxy |
| Credential | Username/password Base64 | Access token opaque/JWT... | Certificate + bằng chứng private key của server | Certificate + private key client | Proxy credential |
| Header/đường đi | `Authorization: Basic` | `Authorization: Bearer` hoặc cơ chế app khác | TLS handshake, **không** phải `Authorization` | TLS handshake, **không** phải `Authorization` | `Proxy-Authorization` |
| Challenge/lỗi điển hình | `401 + WWW-Authenticate` | `401` / `403` tùy validity/scope | `SSLHandshakeException` khi xác thực TLS sai | TLS handshake failure khi thiếu/bị từ chối cert | `407 + Proxy-Authenticate` |
| Phạm vi | HTTP protection space / account | Audience/scope/expiry/resource | Hostname + trust anchor của TLS endpoint | Client principal/trust policy của server | Proxy/realm, không phải origin |
| Có quyền nghiệp vụ tự động? | **Không** | Chỉ các quyền được cấp và policy chấp nhận | **Không** | **Không** | **Không** |
| Phải bảo vệ trên mạng? | **Có**, bằng HTTPS | **Có**, bằng HTTPS; tránh rò token | Bản thân TLS tạo kênh bảo vệ | Bản thân TLS; private key cần bảo vệ | Cần chính sách bảo vệ kết nối đến proxy |

**Đáng nhớ:**
- Basic và Bearer đều là **HTTP authentication schemes**, nhưng credential khác bản chất.
- TLS server certificate kiểm tra **server endpoint**; mTLS thêm kiểm tra **client certificate**.
- `401` không phải `407`, `Authorization` không phải `Proxy-Authorization`.
- Một server có thể đòi **cả mTLS và Bearer token**: certificate xác thực workload, token mô tả user/scopes. Chính sách hợp nhất hai danh tính phải được định nghĩa rõ.
- Chứng chỉ hợp lệ, token hợp lệ và quyền cho một thao tác là **ba câu hỏi khác nhau**.

## 10. Proxy, TLS termination và phiên HTTP: các trust boundary

### Forward proxy thông thường

Client đăng nhập proxy bằng proxy credential; sau đó (với HTTPS CONNECT tunnel) thực hiện TLS tới origin. Ở đây proxy credential và origin Bearer token có **người nhận khác nhau**. Một lỗi cấu hình khiến Bearer token của origin bị gửi tới proxy hoặc host không đúng có thể làm lộ token.

### Reverse proxy chấm dứt TLS

~~~text
Client -- TLS --► Gateway / Reverse Proxy -- HTTP hoặc TLS mới --► Backend
             (TLS handshake và giải mã tại gateway)
~~~

Nếu gateway chấm dứt TLS:
- Certificate mà **client thấy** là certificate của gateway đại diện hostname bên ngoài.
- Nếu có mTLS ở cạnh ngoài, gateway có thể kiểm tra **client certificate** và nhìn thấy peer principal.
- Backend **không tự nhìn thấy cùng TLS client certificate handshake** chỉ vì gateway chuyển tiếp HTTP; cần cơ chế truyền identity đã được xác thực và bảo vệ theo hợp đồng tin cậy.
- Nếu chặng gateway → backend là HTTP plaintext, TLS ngoài **không** bảo vệ chặng nội bộ. Nếu cần bảo vệ hop ấy, lập TLS/mTLS **riêng** cho chặng sau.
- Header như `X-Forwarded-Client-Cert`, `X-Client-Cert` hoặc `Forwarded` **không tự chứng minh danh tính**; client công khai có thể tự gửi các header này. Gateway phải **xóa/ghi đè** header không tin cậy; backend chỉ nhận identity do gateway tin cậy xác thực và truyền trên kênh có kiểm soát.

### Session cookie sau login

Một luồng ứng dụng khác:

~~~text
Browser -- TLS --> POST /login  → app kiểm tra credential
Browser <-- TLS -- Set-Cookie: session=...; Secure; HttpOnly; SameSite=...
Browser -- TLS --> Cookie: session=... → app kiểm tra session store
~~~

Đây là **session authentication ở tầng ứng dụng**: cookie thường chứa session ID, không phải chứng chỉ TLS. Session có thời hạn, logout/revocation và permission policy. Cookie dễ bị CSRF theo ngữ cảnh browser nếu thiết kế sai; `SameSite` là một cơ chế hỗ trợ nhưng không thay thế mọi CSRF protection. Không coi TLS là giải pháp cho XSS, session fixation hoặc quyền nghiệp vụ.

### Một request có thể qua nhiều lớp xác thực

Ví dụ thiết kế hợp lý cho API doanh nghiệp:

1. Proxy yêu cầu credential riêng để truy cập mạng nội bộ.
2. TLS client xác thực HTTPS server/gateway.
3. Gateway yêu cầu mTLS và xác thực certificate của calling service.
4. HTTP request mang access token được audience-bounded cho API.
5. Gateway/backend validate token, kiểm tra scope và policy đối với route/resource.
6. Chỉ sau đó mới xử lý thao tác nghiệp vụ.

**Mỗi lớp giải quyết vấn đề riêng.** Thiếu một bước có thể tạo nguy cơ dù các bước khác hoạt động. Ngược lại, không phải mọi hệ thống đều cần đủ năm lớp — yêu cầu tùy threat model và kiến trúc.

## 11. Ví dụ Java 17 A: HTTP Basic và Bearer trên loopback

Đây là một **chương trình hoàn chỉnh** để quan sát HTTP authentication. Server và client chạy trên `127.0.0.1`, cổng động; không kết nối mạng ngoài. Dùng **giá trị giả** `demo-user`, `demo-pass` và `demo-only-token`. HTTP plaintext chỉ chấp nhận cho thử nghiệm **nội bộ trên loopback**; không gửi credential thật theo cách này qua mạng.

Mục đích:
- `GET /basic` không có credential → `401` kèm `WWW-Authenticate: Basic ...`.
- Có `Authorization: Basic ...` đúng → `200`.
- `GET /bearer` không có token → `401` kèm `WWW-Authenticate: Bearer ...`.
- Có `Authorization: Bearer ...` đúng → `200`.

File đầy đủ **`AuthLayersHttpDemo.java`**:

~~~java
import com.sun.net.httpserver.BasicAuthenticator;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;

public class AuthLayersHttpDemo {
    static void reply(HttpExchange exchange, int status, String message)
            throws IOException {
        byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
            "Content-Type", "text/plain; charset=utf-8");
        exchange.getResponseHeaders().set("Cache-Control", "no-store");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        } finally {
            exchange.close();
        }
    }

    static void bearer(HttpExchange exchange) throws IOException {
        String header = exchange.getRequestHeaders()
            .getFirst("Authorization");
        String expected = "Bearer demo-only-token";
        boolean valid = header != null
            && MessageDigest.isEqual(
                header.getBytes(StandardCharsets.US_ASCII),
                expected.getBytes(StandardCharsets.US_ASCII));
        if (!valid) {
            exchange.getResponseHeaders().set("WWW-Authenticate",
                "Bearer realm=\"demo\", error=\"invalid_token\"");
            reply(exchange, 401, "bearer: unauthorized");
            return;
        }
        reply(exchange, 200, "bearer: accepted");
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
            new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 0);
        var basic = server.createContext("/basic", exchange -> {
            reply(exchange, 200, "basic: accepted");
        });
        basic.setAuthenticator(new BasicAuthenticator("demo") {
            @Override public boolean checkCredentials(
                    String username, String password) {
                return "demo-user".equals(username)
                    && "demo-pass".equals(password);
            }
        });
        server.createContext("/bearer", AuthLayersHttpDemo::bearer);
        server.start();
        try {
            URI base = URI.create("http://127.0.0.1:"
                + server.getAddress().getPort());
            HttpClient client = HttpClient.newHttpClient();
            HttpRequest basicWithout = HttpRequest.newBuilder(
                base.resolve("/basic")).GET().build();
            HttpResponse<String> noBasic = client.send(
                basicWithout, HttpResponse.BodyHandlers.ofString());
            System.out.println("Basic without: " + noBasic.statusCode());

            String encoded = Base64.getEncoder().encodeToString(
                "demo-user:demo-pass".getBytes(StandardCharsets.UTF_8));
            HttpRequest basicWith = HttpRequest.newBuilder(
                base.resolve("/basic"))
                .header("Authorization", "Basic " + encoded)
                .GET().build();
            HttpResponse<String> yesBasic = client.send(
                basicWith, HttpResponse.BodyHandlers.ofString());
            System.out.println("Basic with: " + yesBasic.statusCode()
                + " " + yesBasic.body());

            HttpRequest bearerWithout = HttpRequest.newBuilder(
                base.resolve("/bearer")).GET().build();
            HttpResponse<String> noBearer = client.send(
                bearerWithout, HttpResponse.BodyHandlers.ofString());
            System.out.println("Bearer without: " + noBearer.statusCode());

            HttpRequest bearerWith = HttpRequest.newBuilder(
                base.resolve("/bearer"))
                .header("Authorization", "Bearer demo-only-token")
                .GET().build();
            HttpResponse<String> yesBearer = client.send(
                bearerWith, HttpResponse.BodyHandlers.ofString());
            System.out.println("Bearer with: " + yesBearer.statusCode()
                + " " + yesBearer.body());

            System.out.println("Basic challenge: "
                + noBasic.headers().firstValue("WWW-Authenticate")
                    .map(h -> h.split(" ", 2)[0]).orElse("missing"));
            System.out.println("Bearer challenge: "
                + noBearer.headers().firstValue("WWW-Authenticate")
                    .map(h -> h.split(" ", 2)[0]).orElse("missing"));
        } finally {
            server.stop(0);
        }
    }
}
~~~

### Biên dịch và chạy

Trong thư mục chứa file Java, dùng **JDK 17+**:

~~~bash
javac --release 17 -encoding UTF-8 AuthLayersHttpDemo.java
java AuthLayersHttpDemo
~~~

Stdout đã kiểm chứng qua thực nghiệm:

~~~text
Basic without: 401
Basic with: 200 basic: accepted
Bearer without: 401
Bearer with: 200 bearer: accepted
Basic challenge: Basic
Bearer challenge: Bearer
~~~

### Đọc code cho đúng

1. `BasicAuthenticator` là thành phần của `com.sun.net.httpserver`, tự xử lý HTTP Basic challenge/credential cho context `/basic`. `checkCredentials` trong demo chỉ so sánh hai literal giả, **không** đại diện hệ thống quản lý password thật.
2. `Base64.getEncoder()` chỉ tạo biểu diễn của `username:password`, không mã hóa bảo mật; vì thế demo cố ý bind **loopback**.
3. `/bearer` đọc đúng header `Authorization` rồi so với **một token giả**. `MessageDigest.isEqual` tránh so sánh byte arrays theo cách thông thường trong ví dụ, nhưng **không làm phép kiểm tra JWT signature, audience, expiry, scopes hay revocation**. Hệ thống thật cần authentication provider/token validator.
4. `401` được trả cùng `WWW-Authenticate` trong cả hai scheme. Code in **tên challenge** thay vì in Base64 password/token để tránh tạo thói quen log secrets.
5. Dù `GET /basic` và `GET /bearer` là hai endpoints khác nhau, chúng đều sử dụng **HTTP authentication**, nhưng credential định dạng và cách validate hoàn toàn khác.
6. Demo **không mô phỏng forward proxy** và không gửi `Proxy-Authorization`. `407` là phần kiến thức giao thức ở mục 4; không được hiểu `401` từ server cục bộ là proxy error.
7. Dùng `HttpResponse.statusCode()` để phân biệt successful/unauthorized, không suy diễn HTTP `401` tự biến thành network exception. `HttpClient.send(...)` thường trả response bình thường với status 401.
8. `server.stop(0)` dừng HTTP listener dùng cho bài test; nó không liên quan tới việc xác thực hay vòng đời các access tokens thật.

**Vì sao không tạo token JWT trong demo?** Mục tiêu của bài là phân biệt tầng và loại credential; tạo JWT giả bằng Base64 không có chữ ký hợp lệ dễ gieo ấn tượng sai rằng token đã được validate. Demo giả lập phép so khớp token để nhìn rõ header semantics, đồng thời nhấn mạnh cần dùng identity provider/validator thật khi triển khai production.

## 12. Ví dụ Java 17 B: TLS 1.3 mTLS và identity chứng chỉ

Để thấy **chứng chỉ TLS không phải HTTP Authorization header**, ví dụ thứ hai **không dùng HTTP** mà dùng `SSLSocket` truyền hai dòng `PING` / `PONG` qua TLS 1.3 trên TCP loopback. Cả hai đầu có keystore riêng, truststore riêng:

~~~text
server.p12                  server-trust.p12
(private key + cert server) (trust cert client)
        │                         │
        ▼                         ▼
   SSLServerSocket ------ TLS 1.3 mTLS ------ SSLSocket
        ▲                                             ▲
        │                                             │
server cần client cert                  client.p12 + client-trust.p12
                                      (private key + cert client; trust server)
~~~

**Mô hình trust:**
- Client xác thực certificate của **server `localhost`** và hostname `localhost` (SAN DNS).
- Server dùng `setNeedClientAuth(true)` và truststore chỉ tin certificate thử nghiệm `demo-client`.
- Sau handshake, mỗi bên có thể đọc `SSLSession.getPeerPrincipal()`; chúng hiển thị certificate identity trong demo, nhưng **không có bước application authorization** nào được viết.
- `PING/PONG` là **payload TCP qua TLS**, không phải HTTP request, không có `Authorization` hoặc `Proxy-Authorization`.

### 12.1. Tạo hai certificate và hai truststores bằng keytool

Chạy trong **thư mục thực hành tạm, không commit lên Git**. Các lệnh dùng JDK `keytool`, password `changeit` chỉ để test. Certificate tự ký có hiệu lực 2 ngày và không phù hợp production.

~~~bash
keytool -genkeypair -alias server -keyalg RSA -keysize 2048 -keystore server.p12 -storetype PKCS12 -storepass changeit -keypass changeit -validity 2 -dname "CN=localhost" -ext "SAN=DNS:localhost,IP:127.0.0.1" -ext "EKU=serverAuth" -noprompt
keytool -genkeypair -alias client -keyalg RSA -keysize 2048 -keystore client.p12 -storetype PKCS12 -storepass changeit -keypass changeit -validity 2 -dname "CN=demo-client" -ext "EKU=clientAuth" -noprompt
keytool -exportcert -alias server -rfc -keystore server.p12 -storepass changeit -file server.crt
keytool -exportcert -alias client -rfc -keystore client.p12 -storepass changeit -file client.crt
keytool -importcert -noprompt -alias server -file server.crt -keystore client-trust.p12 -storetype PKCS12 -storepass changeit
keytool -importcert -noprompt -alias client -file client.crt -keystore server-trust.p12 -storetype PKCS12 -storepass changeit
~~~

**Phân biệt các file:** `server.p12` và `client.p12` có **private keys**; không chia sẻ cho đối tác hoặc dùng làm tập tin công khai. `server.crt`/`client.crt` là public certificate. `client-trust.p12` chỉ dùng để client tin server; `server-trust.p12` chỉ dùng để server tin client. Không đảo chiều hoặc cài trust-all cho tiện.

Dùng mật khẩu command line như trên **chỉ** cho test cô lập. Trong ứng dụng thực, cần cấp phát PKI phù hợp, bảo vệ private key, hạn chế file permissions, tránh mật khẩu trong terminal history/CI log, quản lý expiry/rotation và revocation.

### 12.2. Source code đầy đủ `MtlsIdentityDemo.java`

~~~java
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.KeyStore;
import java.util.concurrent.*;
import javax.net.ssl.*;

public class MtlsIdentityDemo {
    private static final char[] PASSWORD = "changeit".toCharArray();

    static SSLContext tlsContext(Path keyStorePath, Path trustStorePath)
            throws Exception {
        KeyStore keys = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(keyStorePath)) {
            keys.load(in, PASSWORD);
        }
        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
            KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(keys, PASSWORD);

        KeyStore trusted = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(trustStorePath)) {
            trusted.load(in, PASSWORD);
        }
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
            TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(trusted);

        SSLContext tls = SSLContext.getInstance("TLS");
        tls.init(kmf.getKeyManagers(), tmf.getTrustManagers(), null);
        return tls;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 4) {
            System.out.println(
                "Usage: java MtlsIdentityDemo server.p12 server-trust.p12"
                + " client.p12 client-trust.p12");
            return;
        }
        SSLContext serverTls = tlsContext(
            Path.of(args[0]), Path.of(args[1]));
        SSLContext clientTls = tlsContext(
            Path.of(args[2]), Path.of(args[3]));

        ExecutorService workers = Executors.newSingleThreadExecutor();
        try (SSLServerSocket listener = (SSLServerSocket)
                serverTls.getServerSocketFactory().createServerSocket(
                    0, 8, InetAddress.getByName("127.0.0.1"))) {
            listener.setNeedClientAuth(true);
            listener.setEnabledProtocols(new String[] {"TLSv1.3"});

            Future<String> serverTask = workers.submit(() -> {
                try (SSLSocket peer = (SSLSocket) listener.accept()) {
                    peer.setSoTimeout(5_000);
                    peer.startHandshake();
                    String clientIdentity =
                        peer.getSession().getPeerPrincipal().getName();
                    BufferedReader in = new BufferedReader(
                        new InputStreamReader(peer.getInputStream(),
                            StandardCharsets.UTF_8));
                    if (!"PING".equals(in.readLine())) {
                        throw new IOException("Unexpected request");
                    }
                    peer.getOutputStream().write(
                        "PONG\n".getBytes(StandardCharsets.UTF_8));
                    peer.getOutputStream().flush();
                    return clientIdentity;
                }
            });

            try (SSLSocket client = (SSLSocket)
                    clientTls.getSocketFactory().createSocket(
                        "localhost", listener.getLocalPort())) {
                client.setSoTimeout(5_000);
                client.setEnabledProtocols(new String[] {"TLSv1.3"});
                SSLParameters params = client.getSSLParameters();
                params.setEndpointIdentificationAlgorithm("HTTPS");
                client.setSSLParameters(params);
                client.startHandshake();
                System.out.println("client sees server: "
                    + client.getSession().getPeerPrincipal().getName());

                client.getOutputStream().write(
                    "PING\n".getBytes(StandardCharsets.UTF_8));
                client.getOutputStream().flush();
                BufferedReader in = new BufferedReader(
                    new InputStreamReader(client.getInputStream(),
                        StandardCharsets.UTF_8));
                System.out.println("response: " + in.readLine());
            }
            System.out.println("server sees client: "
                + serverTask.get(5, TimeUnit.SECONDS));
        } finally {
            workers.shutdownNow();
        }
    }
}
~~~

### 12.3. Biên dịch/chạy

Sau khi tạo đủ file PKCS12 theo các lệnh trên:

~~~bash
javac --release 17 -encoding UTF-8 MtlsIdentityDemo.java
java MtlsIdentityDemo server.p12 server-trust.p12 client.p12 client-trust.p12
~~~

Output đã kiểm tra thực tế:

~~~text
client sees server: CN=localhost
response: PONG
server sees client: CN=demo-client
~~~

**Giải thích output:**

1. Client kiểm tra truststore và `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")`, đảm bảo identity của certificate phù hợp tên `localhost` theo quy tắc TLS/HTTPS được áp dụng.
2. Server kiểm tra client certificate vì `setNeedClientAuth(true)`; truststore của server chứa certificate của client thử nghiệm.
3. `getPeerPrincipal().getName()` đọc danh tính đã chứng thực qua TLS session theo thông tin certificate. Trong thử nghiệm CN là `localhost` và `demo-client`.
4. Dòng `response: PONG` chứng minh payload đã trao đổi sau handshake thành công; **không có một HTTP status 200/401 nào** trong chương trình TLS này.
5. Chương trình kiểm tra TLS 1.3 bằng cách bật duy nhất `TLSv1.3` trên cả hai phía; sẽ thất bại nếu nền tảng không hỗ trợ. Output ở trên giả định JDK hỗ trợ và chứng chỉ chưa hết hạn.

**Một bài thử âm tính hữu ích:** nếu client không có `client.p12` hoặc server truststore không tin certificate client, handshake mTLS bắt buộc sẽ thất bại (thường qua `SSLHandshakeException`). Nếu client truststore không tin server hoặc SAN không khớp hostname, client handshake thất bại. Đây là **lỗi TLS trước HTTP**, không dùng `401` để báo cho peer khi TLS handshake không thể hoàn thành.

**Giới hạn demo:** self-signed cert, hard-code password, chỉ dùng một connection, không có application AuthZ, không phải HTTPS REST server và không quản lý CA nội bộ thực. Chương trình cố ý **không** gửi HTTP token để chứng minh tầng TLS khác với cơ chế xác thực HTTP.

## 13. Cách dùng Java HttpClient khi có proxy/token/certificate

### 13.1. Cấu hình HTTPS client đúng tầng

Ví dụ mẫu Java 17:

~~~java
HttpClient client = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(5))
    .followRedirects(HttpClient.Redirect.NEVER)
    .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.org/v1/data"))
    .timeout(Duration.ofSeconds(10))
    .header("Authorization", "Bearer " + accessToken)
    .GET()
    .build();

HttpResponse<String> response = client.send(
    request, HttpResponse.BodyHandlers.ofString());
~~~

Đây là **snippet**, cần import `java.net.URI`, `java.net.http.*`, `java.time.Duration`; `accessToken` là token hợp lệ lấy từ secret/identity service, không hard-code. **Không chạy ví dụ trực tiếp** vì hostname minh họa chưa phải API có thực. Java HTTP client bình thường xử lý TLS certificate/hostname cho HTTPS, còn `Authorization` ở request là **credential ứng dụng**, không thay thế TLS validation.

Tại sao dùng `Redirect.NEVER` trong snippet? Để không tự chuyển request kèm credential sang origin khác khi chưa có chính sách kiểm soát. Client phải chọn policy redirect thích hợp theo trust boundary; không coi mọi redirect là an toàn.

### 13.2. Proxy selector và proxy credentials

Một ví dụ cấu hình vị trí forward proxy (chưa gửi request):

~~~java
ProxySelector proxy = ProxySelector.of(
    new InetSocketAddress("127.0.0.1", 8080));

HttpClient clientViaProxy = HttpClient.newBuilder()
    .proxy(proxy)
    .connectTimeout(Duration.ofSeconds(5))
    .build();
~~~

Đây là **snippet minh họa**, cần import `java.net.ProxySelector`, `java.net.InetSocketAddress`, `java.net.http.HttpClient`, `java.time.Duration`. Không có proxy nào được khởi chạy trên port 8080 trong các chương trình demo; nếu dùng cấu hình này mà không có proxy thật, request sẽ không hoạt động.

Với proxy yêu cầu authentication, có thể cấu hình `HttpClient.Builder.authenticator(Authenticator)` với credential provider/chính sách phù hợp; không lấy origin token gán bừa vào `Proxy-Authorization`. Một số Basic proxy authentication scenarios, nhất là HTTPS tunneling, chịu ảnh hưởng của **JDK security properties về disabled schemes**; không tự sửa chúng để hạ bảo mật chỉ nhằm “vượt 407”.

**Chú ý `Authenticator` dùng lại credentials:** khi dùng client chung cho nhiều destination/realm, phải phân biệt origin và proxy credential, URL, host/port/realm, không trả cùng username/password cho mọi challenge. Bảo vệ secrets trong memory, log và scope.

### 13.3. Client certificate cho Java HttpClient

Nếu muốn Java `HttpClient` xuất trình client certificate trong mTLS, tạo `SSLContext` từ:
- `KeyManagerFactory` có **client private key + certificate**.
- `TrustManagerFactory` có **CA/trust anchor của server**.
- Truyền `sslContext(context)` vào `HttpClient.Builder`.

Ví dụ logic kết nối:

~~~java
SSLContext context = buildApprovedClientTlsContext();

HttpClient client = HttpClient.newBuilder()
    .sslContext(context)
    .build();
~~~

Đây là snippet minh họa; `buildApprovedClientTlsContext()` là **hàm ứng dụng phải triển khai** để load key/trust và policy (không nằm trong JDK). Source `tlsContext` của `MtlsIdentityDemo` cho thấy thao tác KeyManager/TrustManager cơ bản, nhưng production cần quản lý CA, private keys và secret handling chặt hơn. Không dùng custom trust-all.

**Đừng nhầm:** cài `sslContext` có client key để hỗ trợ mTLS **không tự gửi Bearer token ứng dụng**. Muốn gửi Bearer token, cần thêm `Authorization` request (hoặc cơ chế auth của app) và validate token ở origin resource server.

## 14. Cách ghép AuthN và AuthZ trong kiến trúc thực tế

### Tình huống A — browser tới website

- Browser xác thực certificate của HTTPS endpoint.
- User đăng nhập qua form/SSO.
- Website cấp session cookie `Secure`, `HttpOnly`, `SameSite` theo policy.
- Mỗi request đến backend dùng cookie/session để xác định user rồi kiểm tra permissions.
- Không có yêu cầu browser phải trình certificate client, trừ khi sản phẩm cố ý áp mTLS client authentication.

**Kết luận:** HTTPS server certificate không tương đương user login. TLS bảo vệ kênh, session/auth system nhận dạng user.

### Tình huống B — service gọi REST API qua proxy

- Service xác thực với forward proxy qua **proxy credential** nếu cần.
- TLS handshake xác thực `api.example.org`.
- Service gửi `Authorization: Bearer access-token` có audience/scope dành cho API.
- API kiểm tra token rồi authorization route/resource.
- Proxy credentials, TLS truststore và token app **không thể dùng thay nhau**.

**Kết luận:** proxy 407, origin 401 và TLS handshake failure nằm ở ba nơi khác nhau, cần xử lý riêng trong logging/diagnostics.

### Tình huống C — nội bộ yêu cầu mTLS + Bearer

- Gateway yêu cầu client certificate để xác định workload `orders-service`.
- Client gửi access token thể hiện user và scope `orders:read`.
- Policy có thể yêu cầu **workload được phép thay mặt user** gọi route.
- Nếu token bị đánh cắp nhưng hệ thống muốn chống replay ngoài workload, có thể áp dụng **certificate-bound access token** hoặc một cơ chế proof-of-possession phù hợp.
- Backend chỉ nhận identity từ gateway đáng tin hoặc tự xác thực, không tin raw headers do caller public tự thêm.

**Kết luận:** hai cơ chế có thể **bổ sung nhau**, nhưng phải định nghĩa ai xác thực gì, ai cấp quyền gì và ranh giới TLS ở đâu.

### Tình huống D — máy khách nhận 401 nhưng TLS đã thành công

Điều này **không mâu thuẫn**:
- TLS server identity đã được validate.
- Application credential (password/token/session) có thể thiếu, hết hạn hoặc sai.
- Server trả HTTP `401` sau khi đọc request hợp lệ bên trong kênh TLS.
- Không cần “thay certificate” chỉ vì `401`, trừ khi API thật sự có yêu cầu mTLS và lỗi xảy ra ở giai đoạn TLS.

## 15. Chẩn đoán lỗi theo thứ tự đúng

| Triệu chứng | Tầng thường gặp | Việc cần kiểm tra |
|---|---|---|
| `ConnectException` hoặc connect timeout | TCP/proxy/network | Host, port, proxy selector, firewall, routing |
| HTTP `407` + `Proxy-Authenticate` | Forward proxy | Proxy credentials/policy; không dùng origin token |
| `SSLHandshakeException` do trust/cert/hostname | TLS | Truststore, chain, SAN/hostname, expiry, protocol, client cert nếu mTLS |
| HTTP `401` + `WWW-Authenticate: Basic` | Origin HTTP Auth | Có Basic credentials đúng không; TLS đã đúng chưa |
| HTTP `401` + `WWW-Authenticate: Bearer` | Origin/API token | Token có thiếu/hết hạn/sai audience/issuer/chữ ký không |
| HTTP `403`, token hợp lệ | Authorization | Scope/role/resource ACL, policies |
| HTTP `429` | Rate limiting | Retry-After/backoff, không tự động đổi credential |
| HTTP `502`/`504` qua reverse proxy | Gateway/upstream | Trạng thái backend, timeout, network nội bộ |
| mTLS client thiếu certificate | TLS handshake | Client KeyManager, server needClientAuth, trust chain |
| Đã mTLS thành công nhưng vẫn HTTP `403` | Tầng ứng dụng | Identity mapping và permission checks |
| Client có Bearer nhưng proxy vẫn trả 407 | Proxy | Đang nhầm `Authorization` với `Proxy-Authorization` |
| Proxy đã nhận certificate nhưng backend không biết identity | Trust boundary sau TLS termination | Cơ chế truyền identity đáng tin; không tin header client tự gửi |

### Không để logging trở thành rò rỉ credential

**Không in** nguyên văn các header: `Authorization`, `Proxy-Authorization`, `Cookie`, `Set-Cookie`. Không ghi private key, mật khẩu hoặc JWT đầy đủ trong exceptions/trace. Trong demo ở phần 11, chương trình chỉ in **mã trạng thái, tên scheme và body mẫu không nhạy cảm**.

Để quan sát production, hãy dùng request/correlation ID, route name, status class, latency và error category; ẩn query chứa secret, header nhạy cảm và certificate private material. TLS debug trong môi trường thật cũng cần giới hạn người có quyền đọc logs.

### Không cố vượt lỗi bảo mật bằng cách tắt kiểm tra

Các “cách sửa nhanh” nguy hiểm:
- `X509TrustManager.checkServerTrusted` trống để chấp nhận mọi cert.
- Tắt hostname verification.
- Đưa access token vào URL query hoặc gửi token tới bất kỳ redirect host nào.
- Dùng Basic password qua HTTP plaintext ngoài loopback.
- Cho proxy pass raw client-provided `X-Client-Cert` rồi backend tin đó là certificate đã được mTLS xác thực.
- Nhận JWT theo `alg` không allowlisted hoặc bỏ `aud`/`iss`/`exp`.
- Đổi lỗi HTTP `401`/`407` thành “thành công” chỉ để flow không crash.

Cách đúng là xác định **tầng nào đã từ chối**, sửa credential/trust/policy đúng ở tầng ấy, và kiểm tra quyền tại điểm thực thi nghiệp vụ.

## 16. Checklist triển khai an toàn

1. **Xác định ai là origin và ai là proxy.** Nếu có forward proxy, định nghĩa credential của proxy khác token/password của origin.
2. **HTTPS bắt buộc cho credential thật.** Bật certificate path/hostname validation và TLS hiện đại. Không dùng trust-all.
3. **Xác định identity user/service.** HTTP Basic, Bearer, session cookie và client TLS certificate có nguồn cấp, thời hạn, ranh giới khác nhau.
4. **Phân biệt AuthN với AuthZ.** Token/cert hợp lệ chưa chứng minh được phép gọi endpoint; kiểm tra scopes/roles/ACL.
5. **Token validation đầy đủ.** Key trust, allowed algorithms, issuer, audience, exp/nbf, issuer rotation, replay/revocation policy.
6. **Token ngắn hạn và giới hạn scope.** Tránh chia sẻ token cho nhiều resource servers không cùng audience; không gửi secret qua URL/log.
7. **Cookie session bảo mật.** `Secure`, `HttpOnly`, `SameSite`, CSRF protection và timeout/rotation/logout theo use case.
8. **mTLS đúng vai trò.** Server cần client authentication khi bắt buộc, có server truststore cho client cert; client vẫn validate server hostname/trust.
9. **TLS termination rõ.** Khi gateway giải mã, chặng tới backend cần bảo vệ; sanitize identity headers và trust gateway có kiểm soát.
10. **Proxy CONNECT được quan sát riêng.** `407` trước tunnel khác lỗi `401` bên trong HTTPS origin.
11. **Client redirect có policy.** Không gửi app token/credential cho host khác khi chưa được phép; tránh downgrade.
12. **Không hard-code private key/password/token thật.** Key store/certificate/key rotation, secret manager và access controls rõ.
13. **Test âm tính.** Thiếu password, token hết hạn, wrong audience, missing cert, SAN mismatch, proxy 407, user thiếu scope.
14. **Audit logs tránh secret.** Ghi status/tầng lỗi/trace id thay vì auth header.
15. **Bảo vệ resource.** Đặt timeout, request size limit, rate limiting và input validation; TLS/HTTP auth không thay chống DoS hay bug ứng dụng.

## 17. Bài tập tự kiểm tra

1. HTTP request đi qua forward proxy nhận status **407**. Header challenge và header credential nào thuộc về proxy?
2. Origin API trả **401** cho resource. Header nào phải có theo HTTP authentication framework?
3. HTTP Basic bảo vệ password bằng Base64 có đồng nghĩa mã hóa end-to-end không? Tại sao cần HTTPS?
4. `Authorization: Bearer ...` có phải nằm ngoài HTTP authentication framework không? Giải thích vì sao câu “token ứng dụng khác hoàn toàn xác thực HTTP” dễ gây hiểu nhầm.
5. Server có chứng chỉ HTTPS hợp lệ nhưng request `GET /profile` vẫn trả 401. TLS có bị lỗi không?
6. Một access token ký hợp lệ cho audience `billing-api` được gửi đến `reports-api`. Reports API có nên chấp nhận không?
7. Vì sao JWT payload decode được không đồng nghĩa token đáng tin?
8. Phân biệt **ID token**, **access token** và **refresh token** theo người nhận và mục đích.
9. Server trả HTTP 403 cho token có `orders:read` nhưng route đòi `orders:write`. Đây là AuthN hay AuthZ?
10. Nêu hai cách mà session cookie khác với chứng chỉ TLS client.
11. Server bật `setWantClientAuth(true)` thay vì `setNeedClientAuth(true)`. Nó có bắt buộc client gửi certificate không?
12. Server dùng `setNeedClientAuth(true)` nhưng client không có KeyManager/certificate phù hợp. Lỗi thường xảy ra **trước hay sau** HTTP request?
13. Client raw `SSLSocket` tin một CA hợp lệ nhưng không kiểm tra hostname. Điều gì có thể sai?
14. Một forward proxy chỉ chuyển CONNECT tunnel TLS tới origin. Proxy có đọc được `Authorization: Bearer ...` bên trong HTTPS không, nếu không chấm dứt TLS?
15. Nếu reverse proxy kết thúc TLS và gửi HTTP plaintext vào backend, chặng cuối có còn bảo mật theo TLS phía Internet không?
16. Backend nhận `X-Client-Cert: CN=admin` từ caller public. Có thể coi nó là identity mTLS đã được xác thực không?
17. Mã Java demo Basic/Bearer trả các status gì khi không có credentials và khi có credentials giả đúng? Vì sao không test bằng password/token thật?
18. Mã JSSE demo có `SSLSession.getPeerPrincipal()` sau handshake. Nó chứng minh điều gì và **không** chứng minh điều gì?
19. Có thể dùng một Bearer token và một client TLS certificate đồng thời cho cùng request không? Mỗi cơ chế gắn với loại identity/quyền nào?
20. Nếu API cho phép bearer token bị đánh cắp dùng lại trên máy khác, có cách nào ràng buộc token vào một khóa/certificate để giảm replay không?

**Gợi ý đáp án:**
(1) `Proxy-Authenticate` và `Proxy-Authorization`; (2) `WWW-Authenticate`; (3) không, Base64 giải mã được, cần TLS; (4) Bearer là scheme của HTTP authentication, token mô tả credential/app policy; (5) không nhất thiết, tầng app thiếu credential; (6) không; (7) chưa verify signature/issuer/audience/expiry; (8) xác thực user cho client / gọi resource server / xin token mới; (9) AuthZ; (10) cookie quản lý session tầng HTTP, TLS cert thuộc handshake và khóa/chứng chỉ; (11) không; (12) trong handshake trước HTTP; (13) có thể tin nhầm host; (14) không, trừ khi TLS interception; (15) không; (16) không, phải gateway tin cậy xác thực/sanitize; (17) 401 rồi 200, mọi credentials đều giả; (18) peer TLS identity, không phải quyền nghiệp vụ; (19) có, thường certificate định danh workload, access token thể hiện user/scope; (20) certificate-bound token / proof-of-possession phù hợp.

## 18. Tổng kết

- **HTTP Authentication:** `401 + WWW-Authenticate` và `Authorization` dành cho origin; **proxy authentication:** `407 + Proxy-Authenticate` và `Proxy-Authorization` dành cho forward proxy. Không tráo chúng cho nhau.
- **Bearer token là HTTP auth scheme khi dùng trong `Authorization`.** Nó khác Basic về nguồn credential, vòng đời, quyền, khả năng thu hồi; token có thể opaque hoặc JWT, không tự an toàn chỉ vì có định dạng đặc biệt.
- **TLS server certificate** được client kiểm tra ở handshake để xác thực đúng HTTPS endpoint và lập kênh bí mật/toàn vẹn; nó không thay user/session authentication.
- **mTLS client certificate** được server yêu cầu/kiểm tra ở handshake và thường định danh client workload/service; authentication không tự bằng authorization.
- **Proxy/TLS termination thay đổi trust boundary:** HTTPS CONNECT tunnel, reverse proxy và gateway có khả năng nhìn thấy/không nhìn thấy những credential khác nhau; forwarded identity headers chỉ đáng tin nếu do proxy đã xác thực thiết lập.
- **Java 17 thực hành:** `BasicAuthenticator` minh họa HTTP 401/Basic; `HttpRequest.header` minh họa Bearer; `SSLContext`/`KeyManagerFactory`/`TrustManagerFactory` và `setNeedClientAuth(true)` minh họa TLS mTLS.
- **An toàn:** chỉ dùng HTTPS và validation đúng, không log token/password/key, validate audience/scope/claims, quản lý cookie session và phân quyền riêng, thử các nhánh lỗi trên mỗi tầng.

### Tài liệu tham khảo

- [RFC 9110 — HTTP Semantics, Authentication, 401/403/407](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 7617 — The Basic HTTP Authentication Scheme](https://www.rfc-editor.org/rfc/rfc7617.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html)
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446.html)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705.html)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html)
- [Oracle Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Oracle Java SE 17 — HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html)
- [Oracle Java SE 17 — BasicAuthenticator](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/BasicAuthenticator.html)
- [Oracle Java SE 17 — SSLServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLServerSocket.html)
- [Oracle Java SE 17 — SSLParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html)
- [Oracle Java SE 17 — SSLContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html)
