# mTLS (Mutual TLS) trong giao tiếp service-to-service

> **Chương:** Service to service  
> **Module:** SECURITY_TOKEN_SECURITY_FUNDAMENTALS  
> **Phạm vi:** Mô hình tin cậy và vòng đời token bảo mật; phân biệt JWT, opaque token, access token, refresh token; xác thực và phân quyền trong OAuth 2.0/OIDC; bảo vệ dữ liệu, chống đánh cắp và phát lại token.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích **mTLS** là gì, khác TLS thông thường ở điểm nào và nó xác thực danh tính của **workload/service** ra sao.
2. Mô tả cách hai service thiết lập phiên TLS, kiểm tra chứng chỉ, chuỗi tin cậy và chứng minh quyền sở hữu khóa riêng.
3. Phân biệt **xác thực kết nối bằng mTLS** với **xác thực và phân quyền API bằng access token**, scope, audience và claims.
4. Cấu hình mô hình mTLS cho Java/Spring Boot, kiểm thử kết nối hợp lệ và các lỗi thường gặp.
5. Nhận diện rủi ro do CA tin cậy quá rộng, cấp phát và luân chuyển chứng chỉ sai, TLS termination tại proxy, bỏ qua service mesh hoặc tin header do client tự đặt.
6. Hiểu khi nào mTLS có thể **ràng buộc access token với chứng chỉ** để giảm rủi ro sử dụng lại token đã bị đánh cắp.

## 1. mTLS là gì?

**TLS (Transport Layer Security)** cung cấp một kết nối được mã hóa, bảo vệ tính toàn vẹn và thông thường xác thực **máy chủ** thông qua chứng chỉ số. Khi client gọi một HTTPS endpoint, client kiểm tra chứng chỉ máy chủ, nhưng máy chủ có thể không yêu cầu chứng chỉ của client.

**Mutual TLS (mTLS)** thêm yêu cầu xác thực **cả hai phía** của kết nối TLS:

- **Service A (client)** kiểm tra chứng chỉ của **Service B (server)** để bảo đảm đang kết nối đúng endpoint được tin cậy.
- **Service B** yêu cầu chứng chỉ của **Service A**, kiểm tra chứng chỉ đó và bằng chứng Service A đang sở hữu khóa riêng tương ứng.
- Sau khi TLS handshake thành công, hai phía trao đổi HTTP/gRPC qua một phiên được mã hóa và bảo vệ tính toàn vẹn.

Ví dụ: dịch vụ **payment** gọi **order** qua kết nối TLS. Order service chỉ chấp nhận các workload mang danh tính đã đăng ký và được phép gọi API thích hợp.

~~~mermaid
flowchart LR
    A["Payment Service<br/>chứng chỉ client<br/>khóa riêng A"] <-->|"TLS handshake hai chiều<br/>xác minh danh tính + mã hóa"| B["Order Service<br/>chứng chỉ server<br/>khóa riêng B"]
    CA["CA / Workload PKI<br/>cấp chứng chỉ"] -.-> A
    CA -.-> B
    B --> P["Authorization policy<br/>payment được phép gọi gì?"]
~~~

mTLS thường dùng trong giao tiếp **service-to-service**, giữa các workload trong Kubernetes, hệ thống microservice, kết nối đến message broker hoặc cơ sở dữ liệu hỗ trợ TLS client certificate. mTLS cũng được dùng tại một số endpoint OAuth 2.0 để xác thực client.

### So sánh nhanh

| Khía cạnh | TLS thông thường (HTTPS) | mTLS |
|---|---|---|
| Server chứng minh danh tính với client | Có, khi client xác thực đúng server certificate | Có |
| Client chứng minh danh tính bằng chứng chỉ TLS | Thông thường không bắt buộc | Có, nếu server yêu cầu client certificate |
| Mã hóa và toàn vẹn kết nối | Có | Có |
| Biết **người dùng cuối** đang thao tác | Không tự động | Không tự động |
| Biết client được phép thực hiện **hành động nghiệp vụ** nào | Không tự động | Không tự động |
| Có thể thay cho scope/audience hoặc kiểm tra quyền đối tượng | Không | Không |

**Điểm cốt lõi:** mTLS có thể xác nhận *workload nào* đang ở phía bên kia một kết nối; nó không mặc nhiên xác nhận *người dùng nào* đã khởi tạo một thao tác, hoặc workload đó có quyền đọc/sửa tài nguyên cụ thể nào.

## 2. mTLS hoạt động như thế nào?

### 2.1. Chứng chỉ, khóa riêng và trust anchor

Một triển khai mTLS thường dùng các thành phần sau:

- **Chứng chỉ X.509:** chứa khóa công khai và các thông tin danh tính, thời hạn, issuer, thông tin mở rộng, chữ ký của CA.
- **Khóa riêng:** chỉ workload sở hữu được dùng để chứng minh quyền sở hữu chứng chỉ. Không truyền khóa riêng cho peer.
- **CA (Certificate Authority):** cấp chứng chỉ và tạo nền tảng xác minh chuỗi chữ ký. Hệ thống có thể dùng CA nội bộ dành cho workload.
- **Trust store / trust bundle:** danh sách chứng chỉ CA được phép tin cậy khi xác minh peer.
- **Danh tính trong SAN (Subject Alternative Name):** DNS SAN cho định danh hostname; URI SAN có thể dùng danh tính workload, ví dụ SPIFFE ID.
- **Chính sách phân quyền:** ánh xạ danh tính chứng chỉ đã xác thực thành danh sách service và thao tác được phép.

Ví dụ danh tính workload dưới dạng URI SAN:

~~~text
spiffe://prod.example/ns/payments/sa/payment-api
spiffe://prod.example/ns/orders/sa/order-api
~~~

Trong ví dụ, phía server có thể yêu cầu caller thuộc chính xác danh tính **payment-api**, thay vì chấp nhận mọi client có chứng chỉ do cùng CA cấp. Giá trị URI phải được cấp và xác minh theo quy tắc của hệ thống; chỉ đọc chuỗi URI mà không xác minh chứng chỉ là không đủ.

### 2.2. Trình tự TLS handshake

Luồng đơn giản hóa với **TLS 1.3**:

1. Client gửi **ClientHello** và đề xuất các thông số TLS. Server phản hồi **ServerHello**; hai bên thiết lập vật liệu khóa cho phiên.
2. Server gửi chứng chỉ của mình và bằng chứng sở hữu khóa riêng; nếu yêu cầu mTLS, server gửi **CertificateRequest**.
3. Client kiểm tra chuỗi chứng chỉ, danh tính server trong SAN, thời hạn, mục đích sử dụng khóa và các ràng buộc theo chính sách.
4. Client gửi chứng chỉ của mình và bản tin **CertificateVerify** chứng minh quyền sở hữu khóa riêng; server kiểm tra chứng chỉ cùng bằng chứng đó.
5. Hai phía hoàn tất handshake bằng các thông điệp **Finished**; chỉ sau khi có phiên được chấp nhận, ứng dụng mới tiếp tục trao đổi dữ liệu.

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Payment Service (client)
    participant B as Order Service (server)
    A->>B: ClientHello
    B-->>A: ServerHello, CertificateRequest,<br/>Server Certificate + proof, Finished
    Note over A: Xác minh chứng chỉ server<br/>và đúng danh tính đích
    A->>B: Client Certificate + proof, Finished
    Note over B: Xác minh client certificate<br/>và danh tính caller
    A->>B: HTTPS/gRPC request trên phiên đã xác thực
    B-->>A: Response được bảo vệ bởi TLS
~~~

Sơ đồ mang tính khái niệm, không mô tả đầy đủ mọi bản tin TLS 1.3. Thứ tự chi tiết còn phụ thuộc phiên bản TLS và chế độ handshake.

**Handshake thành công** chứng minh việc xác thực kết nối theo cấu hình TLS hiện tại. Một chứng chỉ hợp lệ về mặt mật mã **chưa phải** quyết định phân quyền ứng dụng. Ví dụ: service báo cáo tài chính và payment service đều có chứng chỉ hợp lệ cùng CA, nhưng chỉ payment service được gọi endpoint tạo thanh toán.

### 2.3. Kiểm tra chứng chỉ gồm những gì?

Tối thiểu phải quan tâm:

- **Chain validation:** chứng chỉ được ký bởi chuỗi hợp lệ đến trust anchor do hệ thống tin cậy; không dùng tùy chọn bỏ qua certificate verification.
- **Thời gian:** chứng chỉ có hiệu lực tại thời điểm xác minh, với đồng hồ hệ thống được đồng bộ.
- **Mục đích sử dụng:** kiểm tra **Key Usage**, **Extended Key Usage** phù hợp như **serverAuth** hoặc **clientAuth** theo vai trò; không tự ý bỏ qua policy.
- **Danh tính peer:** client phải kiểm tra DNS/IP SAN phù hợp với hostname được gọi; server cần kiểm tra workload identity được CA cấp theo policy, thường dựa vào URI SAN hoặc DNS SAN cụ thể.
- **Thu hồi / vòng đời:** áp dụng cơ chế thu hồi khi có, hoặc chứng chỉ ngắn hạn với thay mới tự động và cơ chế cắt quyền nhanh; cần hiểu công nghệ TLS không tự thực thi mọi chính sách thu hồi.
- **Cấu hình mật mã:** dùng phiên bản TLS, cipher suite, kích thước khóa và trust store được tổ chức chấp thuận.

Không lấy danh tính từ HTTP header như **X-Service-Name** hoặc **X-Client-Cert** mà client Internet có thể tự gửi. Nếu TLS terminate ở proxy và proxy cần chuyển thông tin client certificate xuống backend, phải xóa header inbound tương ứng, kiểm tra peer tại proxy và bảo vệ kênh cùng danh tính proxy khi chuyển tiếp.

## 3. mTLS tạo ra ranh giới tin cậy nào?

Giả sử có ba service: **frontend**, **payment** và **order**.

~~~mermaid
flowchart LR
    F["Frontend<br/>user session/access token"] -->|HTTPS| P["Payment Service"]
    P -->|"mTLS: payment → order<br/>OAuth access token tùy thiết kế"| O["Order Service"]
    X["Unknown Service<br/>chứng chỉ không được tin"] -.->|"Không được xác thực"| O
    L["Other internal Service<br/>chứng chỉ hợp lệ, sai quyền"] -.->|"403 / policy deny"| O
~~~

Phân biệt ba câu hỏi an ninh:

1. **Có đúng peer không?** TLS xác minh endpoint dựa trên chứng chỉ, chain, SAN và bằng chứng khóa riêng.
2. **Peer là workload nào?** Hệ thống ánh xạ danh tính chứng chỉ đã xác minh sang service hoặc service account đáng tin cậy.
3. **Peer được phép làm gì?** Authorization policy đánh giá danh tính workload, method, route, resource, scope, tenant và ngữ cảnh người dùng (nếu có).

Ví dụ Order Service có thể chấp nhận kết nối mTLS từ Payment Service nhưng chỉ cho phép **POST /orders/{id}/capture**, không cho phép xóa dữ liệu đơn hàng. Nếu cùng một API có yêu cầu thay mặt người dùng, ứng dụng còn cần kiểm tra quyền của người dùng đó.

### Workload identity khác user identity

| Thành phần | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Chứng chỉ mTLS của workload | Kết nối đến từ service/workload nào? | payment-api tại môi trường production |
| OAuth 2.0 **access token** | Ai hoặc client nào được cấp quyền gọi resource nào? | **aud=orders-api**, **scope=orders.capture** |
| Claim **sub** sau xác thực token | Chủ thể của token là ai? | user-123 hoặc payments-service |
| **ID token** của OIDC | Client OIDC biết gì về sự kiện đăng nhập người dùng? | Xác thực người dùng tại ứng dụng |
| **Refresh token** | Client có thể xin access token mới theo chính sách nào? | Dùng tại token endpoint; không gửi như credential nghiệp vụ |
| Authorization ở Order Service | Có được thay đổi đơn hàng cụ thể này? | Kiểm tra owner/tenant/trạng thái đơn |

mTLS và access token bổ sung cho nhau. Với **client credentials grant**, token có thể đại diện cho chính service. Với luồng **on-behalf-of / token exchange** hoặc luồng ủy quyền khác, token có thể mang ngữ cảnh người dùng; backend phải hiểu rõ loại chủ thể và quyền được cấp.

## 4. mTLS kết hợp OAuth 2.0 và token security

Có ba cách dùng thường bị đánh đồng:

### 4.1. mTLS để bảo vệ kênh giữa service

Service A gọi Service B qua mTLS. Điều này giúp hai peer xác thực nhau và bảo vệ dữ liệu trên kết nối.

Nếu Service A gửi thêm **Bearer access token**, token đó vẫn là credential thuộc tầng ứng dụng. Resource server phải xác thực token, kiểm tra **iss**, **aud**, thời hạn, scope, ràng buộc tenant và các yêu cầu authorization. Kết nối mTLS tự nó không xác minh các claim của JWT.

### 4.2. mTLS để xác thực OAuth client tại authorization server

Theo **OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens (RFC 8705)**, authorization server có thể xác thực một OAuth client qua chứng chỉ mTLS khi client gọi các endpoint phù hợp, chẳng hạn token endpoint. Đây là một lựa chọn **client authentication**, tách biệt với việc dùng client secret.

Ví dụ: service payment yêu cầu access token tại token endpoint qua mTLS. Authorization server ánh xạ chứng chỉ đã kiểm tra với OAuth client đã đăng ký. Cách này chứng minh danh tính client đăng ký, nhưng **không tự động** làm access token trở thành token ràng buộc với chứng chỉ ở resource server.

### 4.3. Certificate-bound access token chống sử dụng lại token bị đánh cắp

Trong mô hình **certificate-bound access token**, authorization server ràng buộc access token với một chứng chỉ client cụ thể. Resource server chỉ chấp nhận token khi caller chứng minh sở hữu khóa riêng của **đúng chứng chỉ** đó qua mTLS.

Ví dụ claim **cnf** (confirmation) trong một JWT access token minh họa:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "payment-service",
  "aud": "orders-api",
  "scope": "orders.capture",
  "exp": 1893456000,
  "cnf": {
    "x5t#S256": "<base64url-SHA256-thumbprint-of-client-certificate>"
  }
}
~~~

Trong thực tế, JWT phải được ký hợp lệ và kiểm tra đầy đủ theo chính sách; JSON trên chỉ để minh họa. Với opaque token, thông tin ràng buộc có thể được cung cấp qua **token introspection**.

Resource server thực hiện cả hai nhóm kiểm tra:

1. **Token validation:** token active/hợp lệ, đúng issuer, audience, thời hạn, scope, subject và policy.
2. **Certificate binding:** tính dấu vân tay SHA-256 của chứng chỉ client được xác thực trên kết nối mTLS; so sánh chính xác với giá trị **cnf.x5t#S256** của token.

~~~mermaid
sequenceDiagram
    participant P as Payment Service
    participant AS as Authorization Server
    participant O as Order Service
    P->>AS: mTLS + client authentication + token request
    AS-->>P: Access token gắn với chứng chỉ P
    P->>O: mTLS + Authorization: Bearer token
    Note over O: Xác thực token và scope/audience<br/>So cnf với chứng chỉ P trên TLS
    O-->>P: Chấp nhận khi cả hai hợp lệ
~~~

Nếu kẻ tấn công chỉ lấy được token và gọi từ một kết nối không sở hữu khóa riêng tương ứng, resource server phải từ chối. Tuy nhiên, nếu **khóa riêng** cùng token bị lộ, hoặc resource server không thực hiện binding check, lớp bảo vệ này không còn tác dụng như mong đợi.

**Lưu ý:** Dùng HTTPS/mTLS cho transport **không đồng nghĩa** access token đã được sender-constrained. Cần chủ động cấu hình phát hành token có ràng buộc và kiểm tra ràng buộc ở resource server.

## 5. Lựa chọn kiến trúc khi triển khai mTLS

| Kiến trúc | Nơi xác thực client certificate | Điều cần kiểm tra |
|---|---|---|
| **mTLS trực tiếp giữa ứng dụng A và B** | TLS stack của ứng dụng B | Certificate chain, danh tính SAN, chính sách gọi API |
| **Ingress / reverse proxy terminate mTLS** | Proxy ở rìa | Backend phải chỉ tin proxy hợp lệ, kênh proxy→backend được bảo vệ, header đã vệ sinh |
| **Service mesh (sidecar/proxy)** | Proxy của service mesh | Chế độ mTLS bắt buộc, identity workload, authorization policy và đường bypass |
| **API gateway xác thực mTLS và bearer token** | Gateway hoặc lớp auth chuyên trách | Backend có thể tự xác thực token hoặc nhận ngữ cảnh đã kiểm chứng qua kênh tin cậy |

Ở mô hình service mesh, ứng dụng A có thể kết nối tới proxy cục bộ bằng một giao thức khác, còn **mTLS xảy ra giữa các proxy**. Lúc đó phải phân biệt danh tính cryptographic peer của proxy và danh tính workload mà mesh cấp/đại diện. Không nên mô tả tùy tiện rằng mỗi process ứng dụng đang giữ trực tiếp private key mTLS.

Nếu proxy terminate TLS rồi dùng HTTP plaintext để gọi backend, tính bảo mật của đoạn sau phụ thuộc vào mạng và chính sách nội bộ. Khi yêu cầu end-to-end hoặc giữa các miền tin cậy, phải có xác thực và bảo vệ tương ứng trên từng hop.

### Một trust bundle rộng không phải authorization policy

Giả sử CA nội bộ cấp chứng chỉ cho 50 service. Nếu Order Service chỉ xác minh chứng chỉ “được CA ký”, cả 50 service có thể qua bước TLS client authentication. Chính sách còn phải giới hạn **URI SAN / service account / trust domain** được phép gọi từng API.

Không dựa duy nhất vào **Common Name (CN)** tự khai hoặc nhãn tùy ý để quyết định quyền; định danh hiện đại nên đặt trong SAN phù hợp và được CA kiểm soát. Ngay cả chứng chỉ hợp lệ, danh tính đúng cũng không bảo đảm người gọi được phép thao tác trên mọi dữ liệu.

## 6. Ví dụ triển khai với Java / Spring Boot

Ví dụ minh họa một **Order Service** dùng TLS endpoint cổng **8443** và yêu cầu chứng chỉ client. Giả định đã được cấp:

- **order-server.p12:** PKCS#12 chứa chứng chỉ và khóa riêng của Order Service.
- **trusted-client-ca.p12:** trust store chứa CA được phép dùng để xác minh client.
- Payment Service có **payment-client.p12**, khóa riêng riêng biệt, và trust store để kiểm tra chứng chỉ server.
- SAN của server khớp hostname **orders.internal.example**; chứng chỉ client có workload identity được đăng ký.

### 6.1. Cấu hình server yêu cầu client certificate

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: file:/etc/security/tls/order-server.p12
    key-store-type: PKCS12
    trust-store: file:/etc/security/tls/trusted-client-ca.p12
    trust-store-type: PKCS12
    client-auth: need
~~~

**client-auth: need** yêu cầu client gửi chứng chỉ được TLS stack chấp nhận; request không có chứng chỉ phù hợp thường bị từ chối ngay ở TLS handshake và không tới controller.

Với Spring Boot, mật khẩu key store/trust store phải được cung cấp qua cơ chế cấu hình bí mật như các biến môi trường **SERVER_SSL_KEY_STORE_PASSWORD**, **SERVER_SSL_TRUST_STORE_PASSWORD** hoặc secret mount phù hợp; không đưa mật khẩu thật vào Git. Tên biến/mapping cần xác minh theo phiên bản Spring Boot và cơ chế cấu hình đang triển khai.

**Cấu hình TLS trên chỉ giải quyết xác thực bằng chứng chỉ tại tầng transport.** Để thực thi chính sách “chỉ payment-api được gọi capture”, ứng dụng hoặc gateway/service mesh vẫn phải lấy danh tính đã xác thực từ chứng chỉ và áp dụng authorization. Không coi tất cả certificate được CA tin cậy là có quyền như nhau.

Ví dụ logic authorization ở mức khái niệm:

~~~text
authorize(request, verifiedTlsPeer):
    if verifiedTlsPeer has no validated client certificate:
        deny connection

    workloadId = identityFromVerifiedSan(verifiedTlsPeer.certificate)
    if workloadId != "spiffe://prod.example/ns/payments/sa/payment-api":
        deny request

    if request.method == "POST" and request.path matches "/orders/*/capture":
        allow only after business authorization checks
    else:
        deny request
~~~

Đoạn mã trên là **pseudocode**: hàm **identityFromVerifiedSan** phải lấy chứng chỉ từ kết quả TLS handshake đã xác thực, không được nhận SAN từ header do bên gọi tự gửi. Mọi endpoint có thể yêu cầu thêm access token, scope và kiểm tra quyền đối tượng.

### 6.2. Java HTTP client gửi chứng chỉ mTLS

Ứng dụng Java có thể nạp **KeyStore** chứa client private key và **TrustStore** chứa CA tin cậy của server, rồi tạo **SSLContext** cho HTTP client:

~~~java
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

class MtlsClientExample {
    static KeyStore loadStore(Path file, char[] password) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(file)) {
            store.load(in, password);
        }
        return store;
    }

    static HttpClient newMtlsHttpClient(
            Path clientKeystore, char[] clientPassword,
            Path serverTruststore, char[] trustPassword
    ) throws Exception {
        KeyManagerFactory keyManagers =
                KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm());
        keyManagers.init(loadStore(clientKeystore, clientPassword), clientPassword);

        TrustManagerFactory trustManagers =
                TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm());
        trustManagers.init(loadStore(serverTruststore, trustPassword));

        SSLContext sslContext = SSLContext.getInstance("TLS");
        sslContext.init(
                keyManagers.getKeyManagers(),
                trustManagers.getTrustManagers(),
                new SecureRandom()
        );
        return HttpClient.newBuilder()
                .sslContext(sslContext)
                .build();
    }

    static String fetch(HttpClient client) throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://orders.internal.example:8443/api/health"))
                .GET()
                .build();
        return client.send(request, HttpResponse.BodyHandlers.ofString()).body();
    }
}
~~~

Đây là đoạn ví dụ minh họa **tạo và sử dụng** một HTTP client mTLS, chưa bao gồm luồng cấp bí mật, timeout/retry, metric và quản lý vòng đời HTTP client khi sử dụng lâu dài. Không tắt **hostname verification**, không tạo **TrustManager** chấp nhận mọi chứng chỉ và không hard-code private key/password. Trong triển khai production, quản lý chứng chỉ và bí mật qua nền tảng được phê duyệt.

### 6.3. Kiểm tra thủ công bằng curl

~~~bash
# Hợp lệ: có server CA để xác minh server và client cert/key để xác thực client.
curl -v \
  --cacert ./server-ca.pem \
  --cert ./payment-client.crt \
  --key ./payment-client.key \
  https://orders.internal.example:8443/api/health

# Không có client certificate: phải thất bại ở mTLS handshake nếu server client-auth=need.
curl -v --cacert ./server-ca.pem \
  https://orders.internal.example:8443/api/health

# Giả tên service bằng HTTP header không được cấp thêm quyền.
curl -v \
  --cacert ./server-ca.pem \
  --cert ./other-service.crt \
  --key ./other-service.key \
  -H "X-Service-Name: payment-api" \
  https://orders.internal.example:8443/api/health
~~~

Nếu chứng chỉ **other-service** cũng được cùng CA tin cậy ký, TLS handshake **có thể thành công**; lúc đó lớp authorization phải nhận ra danh tính service không được phép và từ chối request. Nếu server chỉ triển khai xác thực TLS mà không áp policy identity, test thứ ba có thể phơi bày thiếu sót đó.

Không thêm tùy chọn **-k / --insecure** vào lệnh thử nghiệm chuẩn vì nó bỏ qua xác minh chứng chỉ server, làm sai lệch kết luận về xác thực hai chiều.

## 7. Vòng đời chứng chỉ và vận hành an toàn

mTLS phụ thuộc nhiều vào quy trình PKI. Một môi trường dùng chứng chỉ đúng trong ngày đầu nhưng hết hạn đồng loạt, chia sẻ khóa riêng hoặc thất bại khi rotate vẫn có thể gây gián đoạn hoặc tạo rủi ro.

### 7.1. Cấp phát

1. Xác thực danh tính workload đang xin chứng chỉ, ví dụ qua workload attestation, Kubernetes service account hoặc một cơ chế cấp danh tính tin cậy tương đương.
2. Sinh khóa riêng ở nơi được quản lý, hạn chế người và tiến trình có thể truy cập.
3. CA cấp chứng chỉ có **SAN** đúng và mục đích sử dụng thích hợp, thời hạn đủ ngắn theo chính sách.
4. Phân phối chứng chỉ, private key và trust bundle qua secret management hoặc workload identity system.
5. Service dùng chứng chỉ để thiết lập mTLS; bên nhận đánh giá danh tính đã xác minh cùng authorization policy.

### 7.2. Gia hạn và rotation

- **Tự động gia hạn trước khi hết hạn** để tránh gián đoạn; dùng cert ngắn hạn khi hạ tầng đủ khả năng tự động hóa.
- Hỗ trợ **chồng lấn trust bundle** khi thay CA, cho phép service A/B chuyển đổi trong cửa sổ kiểm soát.
- Khởi tạo lại TLS connection hoặc cơ chế reload certificate theo runtime để cert mới thật sự được dùng; với connection pool lâu dài, cần hiểu vòng đời connection.
- Giám sát thời hạn chứng chỉ, lỗi handshake, độ phủ rotation và danh tính bị từ chối.
- Phân tách chứng chỉ/khóa riêng theo workload và môi trường; tránh tái sử dụng một client cert cho mọi service.

### 7.3. Thu hồi và xử lý sự cố khóa riêng

Nếu khóa riêng của Payment Service bị lộ, người giữ khóa có thể giả làm workload trên mTLS đến khi biện pháp ứng phó được thực thi. Các biện pháp thường gồm **thay khóa/chứng chỉ**, cập nhật quyền/trust, cô lập workload, thu hồi khi cơ chế thực tế hỗ trợ và điều tra truy cập. **CRL/OCSP** có thể hữu ích trong một số hệ sinh thái, nhưng không mặc định được mọi ứng dụng và proxy mTLS bật hoặc kiểm tra. Chứng chỉ ngắn hạn làm giảm thời gian lạm dụng nhưng không thay thế khả năng cắt quyền khẩn cấp.

**Không đưa private key, nội dung token, refresh token, mật khẩu keystore vào log, metrics, message queue hoặc image container.** Phân quyền truy cập secret ở mức tối thiểu và ưu tiên cơ chế cấp phát tự động có audit.

## 8. Các lỗi cấu hình và hướng khắc phục

| Sai sót | Hậu quả có thể xảy ra | Biện pháp |
|---|---|---|
| Chỉ bật HTTPS, không yêu cầu client cert | Không xác thực được workload caller bằng TLS | Bật **client-auth: need** tại đúng ingress/endpoint mTLS |
| Tin mọi cert của CA mà không có identity policy | Service nội bộ khác được gọi API trái phép | Kiểm tra danh tính SAN cụ thể + authorization |
| Bỏ qua hostname/certificate verification ở client | Có thể kết nối nhầm endpoint hoặc bị MITM | Xác minh server chain và hostname |
| Gửi cùng một client cert/private key cho nhiều service | Không phân biệt caller, tăng phạm vi khi lộ khóa | Cấp identity và key riêng từng workload |
| Tin header **X-Client-Cert** từ bên ngoài | Header giả có thể làm backend nhận sai danh tính | Proxy phải sanitize; backend chỉ tin kênh đã xác thực |
| Proxy terminate mTLS nhưng backend public | Có thể bypass chính sách tại proxy | Giới hạn ingress, xác thực từng hop, chặn đường trực tiếp |
| Service mesh cho phép plaintext fallback | Request có thể đi qua đường không mTLS | Bật chế độ bắt buộc và chặn bypass phù hợp hạ tầng |
| Chỉ kiểm tra mTLS, bỏ qua OAuth token audience/scope | Workload hợp lệ vẫn có thể gọi sai tài nguyên | Kiểm tra token và quyền nghiệp vụ độc lập |
| Không rotate cert hoặc CA | Hết hạn gây outage; khóa lộ kéo dài | Tự động cấp mới, theo dõi, diễn tập thay CA |
| Nghĩ mTLS tự ràng buộc bearer token với cert | Token bị đánh cắp vẫn có thể tái sử dụng ở endpoint khác | Dùng certificate-bound token và kiểm tra **cnf** nếu cần |

### Kịch bản lỗi: TLS termination và header giả

~~~text
Internet client
  |
  | X-Client-Cert: "payment-api"   <-- giá trị do client tự bịa
  v
Gateway (terminate mTLS)
  |
  | proxy giữ nguyên X-Client-Cert do client gửi
  v
Order Service
  |
  +--> tin header, nhận nhầm caller là payment-api
~~~

Để an toàn, gateway phải **xóa toàn bộ phiên bản header caller cung cấp**, lấy danh tính từ TLS peer certificate đã xác minh rồi chỉ tạo ngữ cảnh mới nếu hợp đồng với backend yêu cầu. Backend phải xác thực gateway bằng kênh hoặc workload identity phù hợp; nếu cần chứng minh danh tính đầu cuối, cân nhắc cơ chế assertion có chữ ký, audience và hạn dùng rõ ràng. **Chỉ tin header khi request đến từ địa chỉ IP nội bộ** không đủ khi có nhiều đường mạng hoặc workload bị xâm nhập.

## 9. Kiểm thử bảo mật mTLS và access token

Với mỗi môi trường (local/staging/production), lập ma trận kiểm thử thực tế:

| Trường hợp | Kỳ vọng |
|---|---|
| Client có cert đúng CA, SAN đúng, quyền endpoint hợp lệ | TLS handshake và request thành công |
| Client **không có cert** khi server yêu cầu | TLS handshake thất bại, thường không có HTTP status code |
| Client dùng cert do CA không tin cậy cấp | TLS handshake bị từ chối |
| Cert hết hạn hoặc chưa có hiệu lực | Bị từ chối theo certificate validation policy |
| Server cert có SAN không khớp hostname | Client từ chối kết nối |
| Client có cert CA hợp lệ nhưng **sai workload identity** | Có thể qua TLS, phải bị authorization từ chối |
| Client có cert đúng nhưng request thiếu scope/token cần thiết | API từ chối theo chính sách ứng dụng, thường là 401/403 |
| Token JWT có **aud** khác resource server | Token validation thất bại |
| Token có **cnf** nhưng client dùng chứng chỉ khác | Certificate-binding check thất bại |
| Client giả **X-Client-Cert** / **X-Service-Name** | Danh tính không thay đổi, policy vẫn áp dụng |
| Gọi đường khác bỏ qua gateway/mesh | Không thể tiếp cận hoặc bị lớp xác thực tương đương từ chối |
| Rotation chứng chỉ, CA hoặc restart connection | Chuyển đổi an toàn, không mất kết nối ngoài cửa sổ cho phép |

Trong TLS failure, client có thể nhận thông báo như **certificate required**, **bad certificate**, **unknown ca** hoặc **handshake failure**; các thông báo cụ thể khác nhau theo TLS implementation. Không kỳ vọng HTTP **401** cho mọi lỗi chứng chỉ vì ứng dụng có thể chưa nhận được request. **401** và **403** có ý nghĩa ở tầng HTTP sau khi đã thiết lập kết nối.

Một API dùng JWT và mTLS cần kiểm tra độc lập hai hệ thống: **TLS peer identity** ở tầng kết nối và **token principal/scope/audience** ở tầng request. Chỉ vì endpoint trả **200 OK** trong một kiểm thử chưa chứng minh cả hai đường xác thực đã hoạt động: cần thêm ca âm tính cho từng điều kiện.

## 10. Khi nào nên dùng mTLS?

mTLS đặc biệt phù hợp khi:

- Cần **xác thực workload hai chiều** giữa các service mà mạng nội bộ có thể chứa nhiều caller.
- Muốn thiết lập **service identity** chuẩn để áp chính sách giao tiếp east-west, gọi gRPC, HTTP API, broker hoặc dữ liệu nhạy cảm.
- Đã có hệ thống **PKI / certificate rotation** hoặc service mesh đủ tin cậy để vận hành danh tính.
- Cần **OAuth 2.0 mTLS client authentication** hoặc **certificate-bound access token** để giảm rủi ro bearer token bị đánh cắp.

mTLS cần được thiết kế cùng định tuyến mạng, kiểm tra danh tính, lifecycle certificate và chính sách authorization. Nếu chưa thể quản lý khóa/cert hay chưa có ranh giới proxy rõ ràng, việc chỉ “bật mTLS” có thể khiến kết nối lỗi thường xuyên mà chưa xử lý được quyền truy cập.

### Những câu hỏi trước khi đưa mTLS vào production

1. Danh tính workload được cấp và ánh xạ từ SAN như thế nào? Ai có quyền cấp danh tính đó?
2. Trust bundle gồm CA nào? Những service nào cùng tin CA đó và có giới hạn quyền cụ thể không?
3. Client xác thực đúng **hostname/SAN** của server không? Server có policy cho đúng client workload không?
4. mTLS terminate ở app, ingress hay service mesh? Có đường bypass hoặc plaintext hop nào không?
5. Với API dùng OAuth, lớp nào kiểm tra **issuer**, **audience**, **scope**, **exp** và **subject**?
6. Nếu phát **certificate-bound access token**, resource server có so khớp **cnf.x5t#S256** với chứng chỉ TLS thật sự không?
7. Chứng chỉ được gia hạn, thay CA, thu hồi/cắt quyền và giám sát ra sao?
8. Có kiểm thử các trường hợp không cert, sai CA, sai SAN, đúng cert nhưng sai quyền, token bị đánh cắp và token ràng buộc sai cert không?

## 11. Tổng kết kiến thức

**mTLS** cho phép hai phía của một kết nối TLS xác thực lẫn nhau bằng chứng chỉ và chứng minh sở hữu khóa riêng, đồng thời bảo vệ nội dung kết nối. Đây là nền tảng quan trọng cho **service-to-service trust**, nhưng còn cần **authorization theo workload**, kiểm soát đường truy cập và quy trình cấp phát/luân chuyển chứng chỉ.

Trong hệ thống token security, nên tách rõ:

- **mTLS:** xác thực peer ở tầng kết nối.
- **JWT hoặc opaque access token:** mang hoặc dẫn tới các thông tin ủy quyền cần kiểm tra theo issuer, audience, thời hạn và scope.
- **OAuth 2.0 mTLS client authentication:** phương thức xác thực OAuth client tại authorization server.
- **Certificate-bound access token:** ràng buộc việc sử dụng access token vào khóa riêng của client certificate và yêu cầu resource server xác minh ràng buộc.
- **Authorization nghiệp vụ:** quyết định workload hoặc người dùng có thể thực hiện thao tác nào trên tài nguyên cụ thể.

Một kết nối mTLS hợp lệ là **bằng chứng về peer đã được xác thực**, chưa phải giấy phép vô điều kiện để truy cập mọi API hoặc dữ liệu.
