# Truyền danh tính chứng thư qua reverse proxy theo mô hình tin cậy

## 1. Bài toán: TLS kết thúc ở reverse proxy nhưng ứng dụng vẫn cần biết client certificate

Trong triển khai OAuth 2.0/OpenID Connect (OIDC), một reverse proxy, API gateway hoặc load balancer thường đứng trước ứng dụng Spring Boot. Proxy nhận kết nối HTTPS từ client, kết thúc TLS, kiểm tra client certificate nếu bật **mutual TLS (mTLS)**, rồi chuyển HTTP request tới Authorization Server hoặc Resource Server phía sau.

Khi TLS kết thúc tại proxy, backend không trực tiếp tham gia TLS handshake ban đầu. Vì vậy, Servlet container ở backend không nhìn thấy certificate của client gốc trong thuộc tính `jakarta.servlet.request.X509Certificate`. Nếu ứng dụng cần dùng danh tính certificate để xác thực, ánh xạ principal, kiểm tra token binding hoặc phân quyền, proxy phải truyền thông tin certificate qua một kênh tin cậy.

Đây là một bài toán **ủy thác danh tính qua ranh giới mạng**. Header có nội dung certificate không tự chứng minh client đã thực hiện mTLS. Backend chỉ được tin header khi đồng thời xác minh được:
- Kết nối tới backend đến từ reverse proxy đã được cho phép.
- Proxy đã xác thực certificate của client trên kết nối TLS phía ngoài.
- Proxy xóa hoặc ghi đè mọi header certificate do caller tự gửi.
- Proxy truyền certificate qua kết nối backend được bảo vệ, tốt nhất là mTLS.
- Backend chỉ chấp nhận header từ proxy tin cậy và thực hiện mapping/authorization theo policy rõ ràng.

**RFC 9440** định nghĩa hai HTTP header chuẩn để chuyển certificate qua TLS-terminating reverse proxy: `Client-Cert` và `Client-Cert-Chain`. Bài này trình bày mô hình đó, đối chiếu với `X-Forwarded-Client-Cert` (XFCC) của Envoy và cách tích hợp với Spring Security.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant P as Reverse Proxy
    participant A as Spring Boot Application
    C->>P: TLS handshake + client certificate
    P->>P: Verify certificate chain, policy and revocation
    C->>P: HTTPS request
    P->>P: Remove untrusted Client-Cert headers
    P->>P: Set Client-Cert from verified TLS session
    P->>A: Backend mTLS + forwarded certificate header
    A->>A: Authenticate proxy peer
    A->>A: Parse and map original client certificate
    A->>A: Apply authorization policy
    A-->>C: Response through proxy
~~~

## 2. Phân biệt ba danh tính trong mô hình proxy

Khi triển khai mTLS qua reverse proxy, ít nhất ba danh tính có thể xuất hiện trong cùng một request:

| Danh tính | Được xác minh ở đâu? | Ý nghĩa |
| --- | --- | --- |
| **Client gốc** | TLS handshake giữa client và reverse proxy | Certificate của người dùng, thiết bị hoặc OAuth client đã kết nối tới edge |
| **Reverse proxy** | TLS handshake giữa proxy và backend | Workload/service được backend cho phép chuyển tiếp request |
| **Principal trong ứng dụng** | Spring Security sau khi ánh xạ certificate | Danh tính nội bộ dùng cho authorization, audit và nghiệp vụ |

Không được gộp ba danh tính này thành một. Ví dụ, nếu backend nhận kết nối mTLS từ Envoy, certificate mà Servlet container nhìn thấy là certificate **của Envoy**. Certificate của thiết bị người dùng nằm trong header được Envoy chuyển tiếp. Hai certificate có nguồn gốc và mục đích khác nhau.

### 2.1. Hai kết nối TLS, hai quyết định xác thực

~~~text
Client  -- TLS A (mTLS) --> Reverse Proxy -- TLS B (mTLS) --> Backend

TLS A:
  Peer certificate tại proxy = certificate của client gốc

TLS B:
  Peer certificate tại backend = certificate của reverse proxy

HTTP request được proxy chuyển tiếp:
  Client-Cert = certificate client gốc (theo RFC 9440)
  Client-Cert-Chain = chuỗi issuer của certificate client (nếu có)
~~~

Proxy xác thực client trên TLS A. Backend xác thực proxy trên TLS B. Backend chỉ được xem certificate trong header là dữ liệu do proxy tin cậy xác nhận sau khi đã chứng minh TLS B thuộc đúng proxy.

### 2.2. Certificate identity không đồng nghĩa application identity

Một certificate hợp lệ có thể đại diện:
- Một OAuth confidential client.
- Một service-to-service workload.
- Một thiết bị đã đăng ký.
- Một người dùng có smart card hoặc certificate doanh nghiệp.

Ứng dụng phải xác định certificate thuộc loại nào trước khi ánh xạ thành principal. Không mặc định mọi certificate có `CN=Alice` đều là end-user Alice, cũng không mặc định certificate có `CN=orders-service` là OAuth client có quyền gọi mọi API.

## 3. RFC 9440: Client-Cert và Client-Cert-Chain

RFC 9440 chuẩn hóa cách TLS-terminating reverse proxy truyền certificate của client tới origin server qua HTTP. Hai header có semantics cụ thể:

| Header | Nội dung | Quy tắc |
| --- | --- | --- |
| `Client-Cert` | End-entity/leaf certificate mà client dùng trong TLS handshake với proxy | Structured Field Byte Sequence; là singleton, không được lặp hoặc chứa list |
| `Client-Cert-Chain` | Các certificate trong chain được dùng để xác thực leaf certificate | Structured Field List; không bao gồm leaf certificate đã có trong `Client-Cert` |

Các header này chỉ dùng trong HTTP request, không dùng trong HTTP response. `Client-Cert-Chain` không được xuất hiện nếu thiếu `Client-Cert`. Chain được giữ theo thứ tự certificate trong TLS; root có thể bị lược bỏ nếu origin server đã có trust anchor tương ứng.

### 3.1. Encoding: DER certificate dưới dạng Structured Field Byte Sequence

RFC 9440 không định nghĩa giá trị header là subject DN, PEM text hoặc một chuỗi CN tự đặt. Certificate được mã hóa:
1. Lấy certificate ở dạng DER theo ASN.1.
2. Base64 encode, không xuống dòng.
3. Bao giá trị bằng dấu hai chấm theo Structured Fields Byte Sequence.

Ví dụ minh họa:

~~~http
Client-Cert: :MIID...BASE64_DER_LEAF_CERT...:
Client-Cert-Chain: :MIIC...BASE64_DER_INTERMEDIATE_1...:, :MIIC...BASE64_DER_INTERMEDIATE_2...:
~~~

Dữ liệu ở đây là placeholder. Với `Client-Cert-Chain`, mỗi item trong list là một byte sequence. Leaf certificate đã được truyền trong `Client-Cert` nên không lặp lại trong chain.

**Không parse header bằng cách lấy chuỗi CN hoặc split tùy tiện theo dấu phẩy.** Đây là Structured Fields; production parser phải hiểu đúng cú pháp byte sequence/list, duplicate field, whitespace và giới hạn kích thước. Một parser chỉ nhận dạng chuỗi `:base64:` có thể hữu ích cho ví dụ tối giản, nhưng không thay thế Structured Fields parser hoàn chỉnh.

### 3.2. Quy tắc proxy bắt buộc phải thực hiện

RFC 9440 đặt trách nhiệm bảo vệ header ở TLS-terminating reverse proxy:

- Proxy **MUST remove or overwrite** mọi `Client-Cert` và `Client-Cert-Chain` có sẵn trong request gốc trước khi forward.
- Proxy có thể từ chối HTTP 400 nếu request client đã tự gửi một trong hai header.
- Nếu kết nối client tới proxy **không thương lượng mTLS**, proxy phải sanitize bằng cách loại bỏ mọi occurrence của cả hai header.
- Proxy ghi `Client-Cert` từ certificate leaf thực tế trong TLS session.
- Proxy có thể gửi `Client-Cert-Chain` nếu được cấu hình.
- Forward proxy và intermediary khác không được tự thêm hoặc sửa các header RFC 9440.
- Client không được tự gửi hai header này như một cách khai báo danh tính certificate.

Quy tắc này ngăn client tự gửi `Client-Cert: :...:` để giả danh certificate khác. Backend không được chấp nhận header do browser, mobile app hoặc internet caller tự khai.

### 3.3. Header certificate và HTTP cache

Nếu response được chọn dựa trên `Client-Cert` (ví dụ API trả dữ liệu theo certificate identity), RFC 9440 yêu cầu response:
- Không cache được, ví dụ `Cache-Control: no-store`; hoặc
- Có `Vary: Client-Cert` để cache phân biệt request theo certificate.

Cần đánh giá cache ở cả CDN, reverse proxy và browser. Cache response theo URL mà bỏ qua client certificate có thể làm dữ liệu của principal này xuất hiện trong session của principal khác.

## 4. Mô hình trust: backend tin proxy nào và tin điều gì?

Một kiến trúc an toàn có các lớp tin cậy riêng:

~~~mermaid
flowchart TD
    C[Client certificate] --> T[TLS mTLS tại edge]
    T --> V[Proxy kiểm tra CA, validity, EKU, revocation]
    V --> H[Proxy xóa header do caller gửi]
    H --> F[Proxy tạo Client-Cert / Client-Cert-Chain]
    F --> M[Backend mTLS: xác thực certificate của proxy]
    M --> G[Backend chỉ nhận header từ proxy tin cậy]
    G --> P[Parse certificate và kiểm tra policy]
    P --> I[Map certificate sang principal]
    I --> Z[Authorization theo API/resource]
    V -->|Không hợp lệ| X[Từ chối TLS/request]
    M -->|Proxy không tin cậy| X
~~~

### 4.1. Lớp 1 — xác thực client tại edge

Reverse proxy phải:
- Yêu cầu client certificate ở listener/route áp dụng mTLS.
- Xác minh certificate path tới CA/trust anchor được cấu hình.
- Kiểm tra validity period và các extension cần thiết.
- Áp dụng policy Key Usage/Extended Key Usage phù hợp, thường có `id-kp-clientAuth` khi profile certificate yêu cầu.
- Có chính sách kiểm tra thu hồi qua CRL/OCSP hoặc cơ chế PKI doanh nghiệp.
- Ánh xạ issuer, SAN, serial hoặc fingerprint vào danh tính được cấp quyền.
- Từ chối handshake hoặc request khi certificate không đáp ứng policy.

Chỉ chuyển tiếp một certificate mà proxy **đã thực sự nhận và xác minh** từ TLS session. Không tạo header từ query parameter, cookie hoặc header khác do caller kiểm soát.

### 4.2. Lớp 2 — xác thực proxy tại backend

Backend nên chỉ nhận traffic từ proxy qua mạng private và kết nối TLS có xác thực hai chiều:
- Backend có server certificate để proxy xác minh.
- Proxy có client certificate để backend xác minh.
- Trust store backend chỉ chứa CA/certificate được phép cấp identity cho proxy.
- Firewall/security group chỉ mở backend listener cho proxy/workload được phép.
- Certificate proxy có SAN/identity rõ ràng để backend kiểm tra.

Nếu chỉ dùng private network nhưng không xác thực peer, một workload khác trong mạng có thể gửi `Client-Cert` giả mạo. Private network giảm bề mặt truy cập nhưng không tự tạo ra danh tính proxy.

### 4.3. Lớp 3 — xác thực header và ánh xạ danh tính

Sau khi biết peer là proxy được tin cậy, backend mới được phép sử dụng header RFC 9440. Tiếp theo:
- Parse đúng certificate DER.
- Kiểm tra certificate phù hợp profile và trust policy của ứng dụng.
- Xác định có tin quyết định xác thực tại proxy hay backend phải tự dựng/validate certificate path.
- Map identity bằng SAN hoặc thuộc tính định danh ổn định.
- Kiểm tra certificate còn được phép truy cập resource/tenant/client tương ứng.
- Ghi audit bằng fingerprint/issuer/serial phù hợp, không log private material.

**TLS proxy-to-backend chứng minh request đến từ proxy.** Nó không tự chứng minh certificate trong header là hợp lệ nếu proxy không thực hiện đúng bước xác minh TLS phía ngoài hoặc header có thể bị sửa trước khi tới proxy.

## 5. XFCC của Envoy khác RFC 9440 thế nào?

`X-Forwarded-Client-Cert` (XFCC) là header do Envoy sử dụng để mang thông tin certificate qua chuỗi proxy. Đây là định dạng triển khai riêng, không đồng nghĩa với hai header chuẩn RFC 9440.

Envoy có thể biểu diễn một hoặc nhiều phần tử XFCC, mỗi phần tử mô tả certificate/proxy trong hành trình request. Dạng text thường dùng các thuộc tính như `By`, `Hash`, `Subject`, `URI`, `DNS` và `Cert`; phần tử phân tách bằng dấu phẩy, các thuộc tính phân tách bằng dấu chấm phẩy. Giá trị có ký tự phân tách phải được escape/quote theo định dạng XFCC.

| Tiêu chí | RFC 9440 | Envoy XFCC |
| --- | --- | --- |
| Header | `Client-Cert`, `Client-Cert-Chain` | `X-Forwarded-Client-Cert` |
| Cú pháp | Structured Fields; DER byte sequence | Định dạng XFCC do Envoy định nghĩa, text hoặc JSON |
| Certificate leaf | `Client-Cert` | Có thể nằm trong thuộc tính `Cert` nếu được cấu hình |
| Chain/proxy hops | `Client-Cert-Chain` chứa issuer chain | Có thể biểu diễn nhiều XFCC element/hop |
| Tính liên thông | Chuẩn IETF | Đặc thù Envoy và hệ sinh thái hỗ trợ |

Không parse XFCC bằng parser RFC 9440 và cũng không coi `Client-Cert` là một biến thể tên khác của XFCC. Chọn một contract rõ ràng giữa proxy và backend; nếu cần tương thích nhiều gateway, cân nhắc chuẩn hóa tại adapter ở trust boundary.

### 5.1. Các chế độ forward XFCC của Envoy

Envoy cung cấp `forward_client_cert_details` với các chế độ có semantics khác nhau:

| Chế độ | Hành vi |
| --- | --- |
| `SANITIZE` | Mặc định; không gửi XFCC tới next hop |
| `FORWARD_ONLY` | Khi client connection là mTLS, forward XFCC hiện có |
| `APPEND_FORWARD` | Khi client connection là mTLS, append thông tin certificate hiện tại vào XFCC hiện có |
| `SANITIZE_SET` | Khi client connection là mTLS, reset XFCC bằng thông tin certificate hiện tại rồi gửi tiếp |
| `ALWAYS_FORWARD_ONLY` | Luôn forward XFCC, bất kể kết nối client có mTLS hay không |

Với trust boundary nhận certificate từ client internet, cần hiểu rõ sự khác biệt giữa **forward giá trị đã tồn tại** và **sanitize rồi đặt giá trị từ TLS session hiện tại**. Nếu giữ nguyên header client gửi vào, attacker có thể chèn một XFCC element giả. Không chọn `FORWARD_ONLY` hoặc `APPEND_FORWARD` một cách máy móc nếu upstream header chưa được sanitize tại hop đáng tin cậy.

`SANITIZE_SET` thường phù hợp khi proxy này là nơi xác thực client certificate gốc và muốn tạo lại XFCC từ TLS connection hiện tại. Với nhiều hop, phải thiết kế chuỗi tin cậy và chính sách append/sanitize ở từng hop; backend chỉ tin các proxy đã xác thực.

## 6. Chọn danh tính certificate: SAN, issuer và fingerprint

### 6.1. Không dựa duy nhất vào CN

DN Subject có thể chứa `CN`, `OU`, `O`, `C` hoặc email. Việc lấy `CN` bằng regex dễ tạo xung đột:
- Hai CA khác nhau có thể cấp cùng CN.
- CN có thể không duy nhất trong một tenant.
- DN string có thể có escaping, thứ tự thuộc tính và encoding khác nhau.
- CN thường là tên hiển thị, không phải khóa định danh ổn định.

Ưu tiên SAN theo profile đã thống nhất, ví dụ URI SAN cho workload identity, DNS SAN cho service identity hoặc một identifier doanh nghiệp được CA quản lý. Kết hợp issuer/trust domain với SAN để tránh hai CA cùng cấp một URI/name.

### 6.2. Certificate fingerprint và issuer/serial

Có thể định danh certificate bằng SHA-256 fingerprint của DER leaf certificate:

~~~text
fingerprint = BASE64URL_NO_PADDING(
    SHA-256(leaf_certificate_DER)
)
~~~

Fingerprint định danh **một certificate cụ thể**, không nhất thiết là một người dùng/service xuyên suốt nhiều lần cấp lại certificate. Khi certificate renew, fingerprint thay đổi. Có thể dùng issuer + serial hoặc SAN + issuer theo identity lifecycle, nhưng phải xử lý serial chỉ duy nhất trong phạm vi issuer.

Một bảng ánh xạ có thể gồm:

| Thuộc tính | Mục đích |
| --- | --- |
| Trust domain / issuer | Xác định CA hoặc PKI đã cấp certificate |
| SAN URI/DNS/otherName | Định danh workload, client hoặc thiết bị |
| Serial number | Tra cứu certificate trong issuer |
| SHA-256 fingerprint | Nhận diện chính xác certificate đã trình |
| Status / validity | Active, revoked, expired hoặc suspended |
| Tenant / application roles | Ánh xạ sang quyền nội bộ |

Không cấp role chỉ vì certificate có một chuỗi CN giống tên role. Việc cấp quyền phải dựa trên registry/policy do tổ chức kiểm soát.

## 7. Spring Security nhìn thấy certificate nào?

Spring Security Servlet X.509 tích hợp qua `X509AuthenticationFilter`. Filter này lấy certificate từ thuộc tính Servlet:

~~~text
jakarta.servlet.request.X509Certificate
~~~

Sau đó `X509PrincipalExtractor` trích principal từ `X509Certificate` và `PreAuthenticatedAuthenticationProvider`/`AuthenticationUserDetailsService` có thể tải authorities cho principal đó.

Khi backend dùng mTLS với reverse proxy, Servlet container thường expose certificate của **proxy** trong thuộc tính trên. Nó không tự đọc header `Client-Cert` và không tự biết certificate client gốc. Đây là điểm rất quan trọng khi dùng Spring Security phía sau TLS termination.

### 7.1. Khi nào dùng http.x509()?

Dùng cấu hình:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http
        .x509(Customizer.withDefaults())
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        );
    return http.build();
}
~~~

khi Servlet container thực sự nhận và xác minh certificate của peer TLS trên kết nối tới ứng dụng. Trong mô hình proxy-to-backend mTLS, `x509()` thường xác thực **reverse proxy**, không phải end-user/client gốc.

Tài liệu Spring Security mô tả X.509 authentication như pre-authentication: việc yêu cầu và validate certificate xảy ra ở container/TLS layer, Spring Security dùng certificate đó để tìm Authentication và authorities. `x509PrincipalExtractor` tùy chỉnh cách lấy principal, nhưng bản thân extractor không biến một HTTP header tùy ý thành certificate.

### 7.2. Header forwarding cần adapter riêng

Nếu ứng dụng cần principal từ certificate gốc trong `Client-Cert`, có thể xây một integration theo các bước:
1. Một filter chạy sau khi request đã qua trust gate của proxy.
2. Kiểm tra backend peer certificate là proxy đã được chấp nhận.
3. Đọc đúng một `Client-Cert` và parse Structured Field Byte Sequence.
4. Tạo `X509Certificate` từ DER.
5. Áp dụng certificate trust/identity policy đã chọn.
6. Tạo pre-authentication token hoặc cung cấp certificate cho authentication provider.
7. Để Spring Security tạo SecurityContext và tiếp tục authorization.

Không thêm một filter đọc `Client-Cert` ở mọi request mà không xác thực proxy. Không dùng `X509PrincipalExtractor` làm bằng chứng rằng header do proxy tin cậy tạo ra.

Một cách bố trí minh họa trong Servlet filter chain là xác thực proxy bằng `x509()` trước, rồi mới chạy filter xử lý certificate gốc:

~~~java
http
    .x509(x509 -> x509
        .x509PrincipalExtractor(proxyPrincipalExtractor)
        .userDetailsService(proxyUserDetailsService)
    )
    .addFilterAfter(
        forwardedClientCertificateFilter,
        X509AuthenticationFilter.class
    );
~~~

TLS container xác minh chain của **proxy peer** theo trust store; `proxyPrincipalExtractor` trích principal và `proxyUserDetailsService` tải authorities cho proxy đó. `forwardedClientCertificateFilter` là filter ứng dụng tự xây; nó phải kiểm tra Authentication của proxy đã được chấp nhận trước khi đọc header, sau đó tạo Authentication cho certificate client gốc. Chỉ áp dụng filter ở endpoint thực sự cần forwarded client identity. Nếu endpoint không có certificate header theo policy, không tự tạo một principal mặc định.

## 8. Ví dụ triển khai: backend chỉ tin reverse proxy qua mTLS

### 8.1. Cấu hình TLS cho Spring Boot backend

Ví dụ backend yêu cầu certificate từ proxy:

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: classpath:backend-server.p12
    key-store-type: PKCS12
    key-store-password: ${BACKEND_KEYSTORE_PASSWORD}
    trust-store: classpath:trusted-proxy-clients.p12
    trust-store-type: PKCS12
    trust-store-password: ${PROXY_TRUSTSTORE_PASSWORD}
    client-auth: need
~~~

`client-auth: need` yêu cầu peer gửi certificate và container xác minh nó theo trust store. Ở kết nối này, peer là reverse proxy. Chứng thư trong `trusted-proxy-clients.p12` phải chỉ chứa CA/certificate được phép xác thực proxy. Không đưa CA client doanh nghiệp rộng hơn vào trust store proxy nếu không cần.

Cần cấu hình proxy xác minh server certificate của backend và dùng client certificate riêng của workload proxy. Secret/password lấy từ secret manager hoặc cơ chế deployment an toàn; không commit literal vào repository.

### 8.2. Proxy xóa header giả và ghi lại certificate đã xác minh

Một proxy RFC 9440 cần thực hiện logic tương đương:

~~~text
on incoming request:
    if client TLS session has verified client certificate:
        remove all incoming Client-Cert headers
        remove all incoming Client-Cert-Chain headers
        set Client-Cert = RFC9440(DER(verified_leaf_certificate))
        optionally set Client-Cert-Chain = RFC9440_LIST(verified_chain_without_leaf)
    else:
        remove all incoming Client-Cert headers
        remove all incoming Client-Cert-Chain headers

forward request to backend over authenticated mTLS
~~~

Đây là pseudocode mô tả hành vi, không phải cấu hình NGINX/Envoy có thể copy trực tiếp. Tên directive và cách serialize certificate khác nhau theo proxy. Hãy xác minh sản phẩm proxy tạo đúng encoding RFC 9440 hoặc dùng XFCC adapter riêng.

### 8.3. Parse certificate sau trust gate

Đoạn Java dưới đây chỉ nhận byte[] DER **đã được Structured Fields parser đọc ra** từ `Client-Cert`. Nó không phải parser hoàn chỉnh cho header:

~~~java
static X509Certificate toX509Certificate(byte[] der) {
    try {
        CertificateFactory factory = CertificateFactory.getInstance("X.509");
        return (X509Certificate) factory.generateCertificate(
                new ByteArrayInputStream(der));
    }
    catch (CertificateException ex) {
        throw new IllegalArgumentException("Invalid forwarded client certificate", ex);
    }
}
~~~

Trong production:
- Structured Fields parser phải từ chối duplicate `Client-Cert`, list thay vì byte sequence và giá trị vượt giới hạn.
- Chỉ gọi parser sau khi request đã được xác định đến từ proxy tin cậy.
- Nếu cần kiểm tra chain tại backend, parse `Client-Cert-Chain` theo Structured Field List và xây PKIX path với trust anchors cục bộ.
- Nếu tin kết quả validation của proxy, phải xác thực proxy peer bằng mTLS và giới hạn quyền của proxy đó.
- Không log DER certificate hoặc raw header ở mức thông thường.

### 8.4. Tạo principal pre-authenticated

Sau khi certificate được chấp nhận, ứng dụng có thể ánh xạ sang identity và dùng pre-authentication provider:

~~~java
X509Certificate certificate = forwardedCertificateResolver.resolve(request);
String principal = certificateIdentityMapper.map(certificate);

PreAuthenticatedAuthenticationToken authenticationRequest =
        new PreAuthenticatedAuthenticationToken(principal, "N/A");

Authentication authenticated =
        authenticationManager.authenticate(authenticationRequest);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticated);
SecurityContextHolder.setContext(context);
~~~

Đây là đoạn minh họa đặt trong custom filter/provider phù hợp với filter chain; cần xử lý `AuthenticationException`, lưu SecurityContext theo cơ chế Spring đang dùng và không gọi mapper trước trust gate. `forwardedCertificateResolver`, `certificateIdentityMapper` và `authenticationManager` là dependency ứng dụng tự xây.

Nếu cần giữ certificate làm authentication details, provider có thể nhận một principal object giàu thông tin thay vì chỉ chuỗi username. Tuy vậy, authorization nên dùng identity ổn định đã được ánh xạ và authorities được cấp từ nguồn tin cậy.

## 9. Dùng certificate forwarding với OAuth 2.0 mTLS

RFC 8705 mô tả hai khả năng liên quan nhưng khác nhau:

1. **OAuth client authentication bằng mTLS:** client xác thực với Authorization Server bằng certificate ở TLS connection tới token endpoint.
2. **Certificate-bound access token:** access token được ràng buộc với certificate; Resource Server xác minh certificate client trình có đúng certificate mà token đã bind.

Trong mô hình TLS termination, nếu Authorization Server hoặc Resource Server ở sau reverse proxy, cần phân biệt certificate của client gốc với certificate của proxy. Nếu token được bind với certificate client gốc, backend phải nhận diện đúng certificate đó qua một kênh proxy tin cậy hoặc duy trì mTLS end-to-end.

### 9.1. cnf.x5t#S256

Certificate-bound access token có thể chứa confirmation claim:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "service-client",
  "aud": ["orders-api"],
  "cnf": {
    "x5t#S256": "BASE64URL_SHA256_OF_LEAF_CERT_DER"
  }
}
~~~

Giá trị `x5t#S256` là SHA-256 thumbprint của **DER-encoded end-entity certificate** được dùng trong mTLS, mã hóa Base64URL không padding. Không hash PEM text, Subject DN hoặc toàn bộ certificate chain.

Khi Resource Server nhận token, nó phải xác minh access token trước, lấy thumbprint trong `cnf.x5t#S256`, tính thumbprint từ certificate đã được xác minh qua trust boundary và so sánh. Nếu certificate trong header chỉ được tin do proxy chuyển tiếp, backend phải xác minh peer proxy và đảm bảo proxy đã xác thực đúng certificate client gốc.

### 9.2. Không nhầm client authentication với end-user identity

| Câu hỏi | OAuth client authentication | Certificate-bound access token | Forwarded certificate identity |
| --- | --- | --- | --- |
| Certificate đại diện ai? | OAuth client | Key/certificate holder dùng token | Client TLS peer tại edge |
| Mục đích | Xác thực client với AS | Ràng buộc token với certificate | Chuyển certificate qua TLS termination |
| Nơi kiểm tra | Token endpoint TLS/client auth | Resource Server | Proxy và backend trust boundary |
| Claim/header | Client auth method mTLS | `cnf.x5t#S256` | `Client-Cert`/`Client-Cert-Chain` hoặc XFCC |

Một certificate của người dùng được forward qua proxy không tự trở thành OAuth client authentication của client application. Cũng không phải cứ có `Client-Cert` là access token đã certificate-bound.

### 9.3. TLS termination không tự chuyển mTLS client authentication vào backend

RFC 8705 client authentication yêu cầu Authorization Server xác thực certificate của OAuth client theo phương thức mTLS đã đăng ký. Nếu TLS kết thúc ở proxy, kết nối TLS từ proxy tới AS mang certificate của **proxy**. Việc backend nhận thêm `Client-Cert` không tự làm Servlet container coi certificate client gốc là peer TLS của kết nối backend.

Có hai hướng kiến trúc:
- **TLS passthrough/end-to-end:** giữ TLS handshake của client tới chính AS/Resource Server; ứng dụng/container nhìn thấy certificate gốc và có thể dùng cơ chế mTLS chuẩn trực tiếp. Proxy ở L4 không thể thực hiện đầy đủ HTTP routing/inspection trên TLS đã mã hóa.
- **Trusted certificate forwarding:** proxy xác thực client ở edge, strip/overwrite header và chuyển certificate qua backend mTLS. AS phải có integration được thiết kế rõ để dùng certificate đã được proxy xác nhận cho client authentication hoặc token binding. Integration phải ràng buộc danh tính proxy, certificate client, client registration và trust policy; không chỉ lấy header rồi tin.

Tương tự, khi phát hành certificate-bound access token, `cnf.x5t#S256` phải được tính từ **certificate client đã xác thực và được bind**, không phải certificate của proxy ở TLS backend. Resource Server cũng phải so với certificate client gốc đã được forward qua trust boundary. Nếu không thể bảo đảm đường đi đó, không tuyên bố token đang được ràng buộc với certificate client gốc.

## 10. Mô hình nhiều proxy và chuỗi tin cậy

Có thể có nhiều hop:

~~~text
Browser / Device
   |
   | mTLS: certificate của client
   v
Edge Gateway
   |
   | mTLS: identity của Edge Gateway
   v
Internal Ingress
   |
   | mTLS: identity của Internal Ingress
   v
Spring Boot Backend
~~~

Mỗi hop phải có một contract rõ:
- Hop nào thực sự terminate TLS từ client gốc?
- Hop nào xác minh certificate chain và revocation?
- Hop nào được phép ghi hoặc append forwarded certificate header?
- Backend tin proxy cuối cùng hay một chuỗi proxy cụ thể?
- Certificate chain của client gốc được giữ nguyên hay chỉ có leaf?
- Các header nào bị strip ở từng hop?

**Không tin mọi phần tử trong header chỉ vì header được gọi là X-Forwarded.** Nếu nhiều proxy append dữ liệu, một proxy cuối phải xác thực proxy trước đó và chuẩn hóa chuỗi. Backend nên xác minh mTLS peer là proxy ingress được chỉ định, rồi áp dụng quy tắc parse/trust đã thống nhất.

### 10.1. Certificate chain và trust anchor

`Client-Cert-Chain` có thể truyền intermediate certificates nhưng root trust anchor có thể bị lược bỏ nếu backend đã biết trust anchor đó. Backend không được lấy root từ header làm trust anchor tự động. Trust anchors phải được cấu hình độc lập và quản lý theo PKI policy.

Nếu proxy đã validate chain và backend chỉ tin kết quả của proxy, backend cần bảo vệ proxy như một authentication authority. Nếu backend tự validate lại, nó phải có trust anchors, thuật toán, revocation policy và path validation đầy đủ. Không chỉ gọi `certificate.checkValidity()` rồi kết luận certificate đáng tin: hàm đó chủ yếu kiểm tra thời hạn, không xác minh chain hoặc trạng thái thu hồi.

## 11. Rủi ro, lỗi cấu hình và biện pháp giảm thiểu

| Rủi ro | Nguyên nhân | Biện pháp |
| --- | --- | --- |
| Header spoofing | Proxy giữ nguyên `Client-Cert` do client gửi | Strip/overwrite tại edge; backend chỉ tin proxy mTLS |
| Direct backend bypass | Backend public hoặc workload lạ có thể gọi thẳng | Private listener, firewall, mTLS peer allowlist |
| Proxy identity confusion | Dùng certificate proxy làm identity người dùng | Tách proxy principal và original client certificate |
| CN collision | Chỉ map theo CN | Dùng SAN + issuer/trust domain hoặc fingerprint |
| Chain injection | Tin chain do caller cung cấp | Chain chỉ do proxy tạo; backend kiểm tra với trust anchor cục bộ |
| Certificate expired/revoked | Không có revocation policy | CRL/OCSP hoặc cơ chế PKI; xử lý cache/latency rõ |
| XFCC parsing bug | Split dấu phẩy/chấm phẩy không xử lý quote/escape | Dùng parser đúng định dạng XFCC |
| RFC 9440 parsing bug | Coi header là PEM hoặc Base64 thuần | Structured Fields parser, giới hạn kích thước và duplicate |
| Multi-hop spoofing | Proxy sau append dữ liệu từ hop không tin | Xác thực từng hop, sanitize và xác định trust chain |
| Cache data leak | Response phụ thuộc certificate nhưng cache bỏ qua identity | `Cache-Control: no-store` hoặc `Vary: Client-Cert` |
| Stale certificate mapping | Certificate renew/revoke nhưng cache principal cũ | TTL cache ngắn, invalidate theo fingerprint/status |
| Authorization bypass | Certificate hợp lệ được xem là đủ quyền mọi API | Tiếp tục kiểm tra scope, audience, tenant và business authorization |

## 12. Ma trận kiểm thử

### 12.1. Kiểm thử proxy và trust boundary

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Client gửi mTLS certificate hợp lệ | Proxy xác minh và forward leaf theo contract |
| Client không có certificate trên route yêu cầu mTLS | TLS/request bị từ chối theo policy |
| Client gửi header `Client-Cert` giả | Proxy loại bỏ/ghi đè hoặc trả 400 |
| Client gửi nhiều `Client-Cert` | Proxy sanitize hoặc reject; backend không nhận giá trị mơ hồ |
| Client gửi `Client-Cert-Chain` nhưng không có leaf | Proxy loại bỏ/reject |
| Kết nối client không thương lượng mTLS | Cả hai header RFC 9440 bị xóa |
| Backend nhận request từ workload không phải proxy | TLS mTLS hoặc network policy từ chối |
| Proxy certificate hết hạn/không được trust | Backend từ chối TLS |
| Header certificate bị sửa giữa proxy và backend | Backend transport/authentication phát hiện hoặc request bị từ chối |
| Proxy chuyển request qua nhiều hop | Chỉ hop được trust có thể tạo/append metadata theo policy |

### 12.2. Kiểm thử certificate và ứng dụng

| Tình huống | Kết quả mong đợi |
| --- | --- |
| RFC 9440 header hợp lệ | Parse đúng leaf DER |
| Header sai Structured Field syntax | Từ chối, không fallback sang CN header |
| Leaf certificate hết hạn | Từ chối theo trust policy |
| Certificate sai EKU/Key Usage | Từ chối nếu profile yêu cầu clientAuth |
| Issuer không nằm trong trust domain | Từ chối |
| Certificate revoked | Từ chối theo revocation policy |
| Hai certificate cùng CN nhưng issuer khác | Không map nhầm principal |
| SAN không có trong registry | Không cấp identity/authority |
| Certificate renew | Identity lifecycle cập nhật theo mapping mới |
| Token có cnf.x5t#S256 sai | Từ chối token/certificate binding |
| Certificate client khác certificate proxy | Mỗi danh tính được xử lý đúng vai trò |
| Response phụ thuộc certificate | Cache không làm lộ dữ liệu giữa identity |

### 12.3. Kiểm thử Spring Security

- Xác minh `x509()` mặc định lấy certificate từ Servlet attribute và trong backend mTLS nó nhận certificate proxy.
- Xác minh custom forwarded-certificate filter không chạy khi request không đến từ proxy tin cậy.
- Xác minh không có `Client-Cert` thì không tạo principal certificate giả.
- Xác minh certificate header không tự cấp authorities; authorities phải đến từ user/identity service hoặc policy đáng tin.
- Xác minh OAuth2 Resource Server vẫn kiểm tra issuer, signature, audience, expiry, scope và confirmation claim.
- Xác minh request có Bearer token nhưng thiếu certificate proof không thể dùng access token đã certificate-bound.
- Xác minh log không ghi raw certificate, header hoặc secret không cần thiết.

## 13. Bài tập tình huống

Một hệ thống có Edge Gateway và Spring Boot Authorization Server:

~~~text
Client A:
  kết nối HTTPS + mTLS tới Edge Gateway
  certificate subject CN=payments-client
  SAN URI=spiffe://corp.example/workload/payments

Edge Gateway:
  validate certificate theo Corp-Client-CA
  forward request tới backend bằng mTLS
  client certificate của gateway do Platform-CA cấp

Spring Boot:
  server.ssl.client-auth=need
  trust store chỉ tin Platform-CA
~~~

Một request tới backend mang:
- TLS peer certificate: Edge Gateway.
- Header `Client-Cert`: certificate của payments-client.
- Header `Client-Cert-Chain`: intermediate chain của Corp-Client-CA.

Hãy trả lời:

1. Vì sao `http.x509()` trên backend có thể xác thực Edge Gateway thay vì payments-client?
2. Những điều kiện nào phải đúng trước khi backend tin `Client-Cert`?
3. Nếu Client A tự gửi một header `Client-Cert` khác, Edge Gateway phải làm gì?
4. Nếu một pod khác trong cluster gọi trực tiếp backend và gửi header giả, cơ chế nào ngăn request?
5. Vì sao map theo SAN URI + trust domain thường an toàn hơn chỉ map CN?
6. Nếu backend cần tự validate chain, nó phải có gì ngoài `Client-Cert-Chain`?
7. Nếu access token có `cnf.x5t#S256`, thumbprint được tính từ certificate nào?
8. Khi response khác nhau theo client certificate, cần xử lý cache ra sao?

**Gợi ý:** TLS peer tại backend là gateway, còn certificate client gốc ở header. Chỉ tin header sau khi xác minh gateway peer, giới hạn mạng, bảo đảm gateway strip/overwrite header và kiểm tra leaf certificate theo trust policy. Thumbprint của RFC 8705 tính trên DER leaf certificate client được token bind, không phải certificate gateway hoặc toàn chain.

## 14. Checklist triển khai production

1. **TLS edge:** bật mTLS đúng listener/route và xác minh certificate chain, validity, EKU/Key Usage, revocation.
2. **Header contract:** chọn RFC 9440 hoặc XFCC; tài liệu hóa encoding, chain order, duplicate và multi-hop.
3. **Sanitization:** strip/overwrite header từ client; khi không có mTLS, xóa mọi forwarded certificate header.
4. **Backend transport:** chỉ cho phép proxy truy cập backend; ưu tiên mTLS proxy-to-app với trust store riêng.
5. **Proxy identity:** backend xác minh certificate của proxy, tách khỏi original client certificate.
6. **Certificate parsing:** Structured Fields/XFCC parser phù hợp, giới hạn size và từ chối dữ liệu mơ hồ.
7. **Trust policy:** xác định tin proxy validation hay backend validate lại chain; trust anchors độc lập và revocation policy rõ.
8. **Identity mapping:** SAN + issuer/trust domain, fingerprint/serial và lifecycle; không dựa CN đơn lẻ.
9. **Spring Security:** hiểu `X509AuthenticationFilter` đọc Servlet certificate attribute; forwarded header cần adapter/custom authentication integration.
10. **OAuth mTLS:** phân biệt client authentication, certificate-bound token và forwarded end-user/workload identity.
11. **Caching:** response phụ thuộc `Client-Cert` phải no-store hoặc Vary đúng theo RFC 9440.
12. **Observability:** audit proxy identity, certificate fingerprint, issuer và reason code; hạn chế log dữ liệu certificate.
13. **Testing:** spoof header, direct backend, wrong proxy cert, chain tampering, expiry/revocation, multi-hop và cache isolation.
14. **Incident response:** có quy trình thu hồi certificate, cập nhật trust store, revoke token và xử lý key/CA compromise.

## 15. Tài liệu chuẩn và Spring cần đối chiếu

- [RFC 9440 — Client-Cert HTTP Header Field](https://www.rfc-editor.org/rfc/rfc9440.html): `Client-Cert`, `Client-Cert-Chain`, DER/Structured Fields, proxy sanitization và cache behavior.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705.html): OAuth client mTLS authentication và `cnf.x5t#S256`.
- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280.html): certificate path, extensions, key usage và revocation lists.
- [RFC 8941 — Structured Field Values for HTTP](https://www.rfc-editor.org/rfc/rfc8941.html): Byte Sequence và List serialization được RFC 9440 sử dụng.
- [Spring Security 7.0 — X.509 Authentication](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/x509.html): X.509 pre-authentication, Servlet certificate attribute và principal extraction.
- [Spring Security 7.1 — X509Configurer Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/X509Configurer.html): cấu hình X509AuthenticationFilter và principal extractor.
- [Envoy — HTTP Header Manipulation: XFCC](https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_conn_man/headers): cú pháp XFCC và cách forward/sanitize certificate.
- [Envoy — HttpConnectionManager ForwardClientCertDetails](https://www.envoyproxy.io/docs/envoy/latest/api-v3/extensions/filters/network/http_connection_manager/v3/http_connection_manager.proto): các chế độ SANITIZE, FORWARD_ONLY, APPEND_FORWARD, SANITIZE_SET và ALWAYS_FORWARD_ONLY.

**Ghi nhớ:** Khi TLS kết thúc tại reverse proxy, certificate client gốc không tự xuất hiện trong Servlet container ở backend. Proxy phải xác minh client ở TLS phía ngoài, loại bỏ header do caller tự gửi, rồi chuyển certificate qua contract rõ ràng như RFC 9440. Backend phải xác thực proxy trên kết nối riêng, chỉ sau đó mới tin và ánh xạ certificate trong header. Trong Spring Security, `x509()` mặc định đọc certificate của TLS peer do Servlet container cung cấp; phía sau proxy mTLS, đó thường là certificate proxy. Hãy tách proxy identity, original client certificate và application principal trong toàn bộ authentication/authorization flow.
