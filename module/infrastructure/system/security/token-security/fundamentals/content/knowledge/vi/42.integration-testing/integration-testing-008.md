# Test TLS

TLS bảo vệ đường truyền giữa client, Authorization Server, Resource Server và các dịch vụ nội bộ. Trong hệ thống token security, một access token có thể được ký và kiểm tra đúng nhưng vẫn bị lộ nếu client gửi nó qua kết nối không an toàn, hoặc bị kẻ trung gian giả mạo máy chủ để đánh cắp. Vì vậy, kiểm thử tích hợp cần xác minh cả **kênh TLS** lẫn **hành vi xác thực token ở tầng HTTP**.

Bài học thuộc chương **Integration testing** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung tập trung vào cách dựng môi trường TLS kiểm thử, xác minh chứng thư máy chủ, hostname, phiên bản TLS, mutual TLS (mTLS), OAuth 2.0 Token Endpoint, Resource Server và access token được ràng buộc với chứng thư client.

## 1. TLS bảo vệ điều gì trong luồng token?

TLS thiết lập một kênh mã hóa và xác thực peer theo cấu hình tin cậy. Với HTTPS thông thường, client xác minh chứng thư máy chủ và hostname; server chứng minh mình nắm private key tương ứng. Với mTLS, server cũng yêu cầu và xác minh chứng thư client trong quá trình bắt tay TLS.

Một luồng OAuth/OIDC thường có nhiều kết nối độc lập:

~~~mermaid
flowchart LR
    C["Web / Mobile Client"] -->|"HTTPS + TLS"| AS["Authorization Server"]
    C -->|"HTTPS + Bearer Access Token"| RS["Resource Server"]
    RS -->|"HTTPS + client authentication"| AS
    RS -->|"TLS hoặc mTLS"| DB["Internal Service / Data API"]
    AS -->|"TLS hoặc mTLS"| KMS["Key / Certificate Service"]
~~~

Mỗi kết nối cần được kiểm thử theo vai trò riêng:

| Kết nối | Điều cần xác minh |
| --- | --- |
| Client → Token Endpoint | Client xác minh đúng chứng thư máy chủ và hostname; token, authorization code, client secret không đi qua HTTP |
| Client → Resource Server | Access token chỉ được gửi qua HTTPS; API không chấp nhận request nhạy cảm qua kênh plaintext |
| Resource Server → Introspection Endpoint | Kết nối TLS được xác minh; thông tin xác thực của Resource Server được bảo vệ |
| Service → Service | Chứng thư peer, trust chain và quyền của workload được kiểm tra; nếu dùng mTLS thì client certificate được xác minh |
| Resource Server → JWKS/metadata endpoint của Authorization Server | Kết nối đến đúng issuer đã cấu hình; không tin URL hoặc khóa do token không đáng tin tự chỉ định |

TLS **không thay thế** xác minh access token. TLS xác thực và bảo vệ kênh; Resource Server vẫn phải kiểm tra chữ ký hoặc introspection, issuer, audience, thời hạn, loại token, scope và quyền truy cập tài nguyên.

## 2. Các thành phần của một bài kiểm thử TLS

Một bộ test hữu ích nên tạo được các chứng thư có đặc tính khác nhau:

- **Root CA test:** CA gốc riêng cho môi trường test, được import có chủ đích vào trust store của client.
- **Intermediate CA:** dùng để kiểm tra server gửi đủ certificate chain và client xây dựng được chuỗi tin cậy.
- **Server certificate:** có SAN đúng hostname mà test client sử dụng, thời hạn còn hiệu lực và Extended Key Usage phù hợp cho server authentication.
- **Client certificate:** dùng trong mTLS, có EKU phù hợp cho client authentication và được CA mà server tin cậy ký.
- **Untrusted certificate:** chứng thư được ký bởi CA khác để kiểm tra trường hợp không tin cậy.
- **Expired certificate:** chứng thư hết hạn để xác minh quá trình bắt tay bị từ chối.
- **Wrong-hostname certificate:** chứng thư có SAN không khớp hostname của request.

Không dùng chứng thư production, private key thật hoặc token người dùng thật trong test. Nên tạo CA và key pair dùng riêng cho test, có thể dựng bằng fixture của build hoặc test PKI nội bộ. Private key test phải được giới hạn quyền truy cập và không commit nhầm vào artifact phát hành.

Các điều kiện nên được kiểm tra riêng:

| Điều kiện | Kết quả mong đợi |
| --- | --- |
| Chứng thư máy chủ hợp lệ, chain tin cậy, SAN khớp | TLS handshake thành công |
| CA ký chứng thư không nằm trong trust store | Client từ chối handshake |
| SAN không khớp hostname | Client từ chối handshake |
| Chứng thư hết hạn hoặc chưa đến thời điểm hiệu lực | Handshake bị từ chối |
| Server thiếu intermediate certificate cần thiết | Client không xây dựng được trust chain và từ chối |
| Chứng thư thiếu EKU phù hợp | Bị từ chối theo chính sách xác minh |
| Chứng thư được xoay vòng sang CA mới đã được tin cậy | Kết nối thành công trong giai đoạn chuyển đổi |

## 3. Kiểm thử HTTPS server certificate và hostname

Client phải xác minh được hai điều khác nhau: chứng thư được ký bởi CA tin cậy và chứng thư đại diện cho đúng hostname trong URL. Chỉ kiểm tra chữ ký chứng thư mà bỏ qua hostname vẫn có thể cho phép kết nối đến một máy chủ giả mạo.

Ví dụ, test gọi `https://localhost:8443` thì chứng thư server cần có SAN `DNS:localhost`. Nếu gọi bằng địa chỉ IP `https://127.0.0.1:8443` thì chứng thư phải có SAN kiểu IP tương ứng; SAN DNS không tự khớp với địa chỉ IP.

### Tạo HttpClient dùng trust store kiểm thử

Ví dụ Java dưới đây tạo client tin cậy CA test. Test có thể truyền thêm client key store khi cần mTLS:

~~~java
static SSLContext createSslContext(
        KeyStore trustStore,
        KeyStore clientKeyStore,
        char[] clientKeyPassword
) throws GeneralSecurityException {
    TrustManagerFactory trustManagers =
            TrustManagerFactory.getInstance(
                    TrustManagerFactory.getDefaultAlgorithm()
            );
    trustManagers.init(trustStore);

    KeyManager[] keyManagers = null;
    if (clientKeyStore != null) {
        KeyManagerFactory clientKeys =
                KeyManagerFactory.getInstance(
                        KeyManagerFactory.getDefaultAlgorithm()
                );
        clientKeys.init(clientKeyStore, clientKeyPassword);
        keyManagers = clientKeys.getKeyManagers();
    }

    SSLContext context = SSLContext.getInstance("TLS");
    context.init(
            keyManagers,
            trustManagers.getTrustManagers(),
            new SecureRandom()
    );
    return context;
}

static HttpClient httpsClient(SSLContext sslContext) {
    return HttpClient.newBuilder()
            .sslContext(sslContext)
            .connectTimeout(Duration.ofSeconds(3))
            .build();
}
~~~

Các import cần thiết gồm `javax.net.ssl.*`, `java.security.*`, `java.security.KeyStore` và `java.net.http.*`. Trong test thực tế, đọc trust store và key store từ fixture được tạo riêng cho test, kiểm soát mật khẩu và đóng stream sau khi đọc.

Java HttpClient thực hiện hostname verification theo mặc định. Giữ nguyên hành vi đó; không cấu hình trust manager chấp nhận mọi chứng thư, không tắt endpoint identification và không dùng hostname verifier luôn trả về `true`. Một test cần kiểm tra hostname sai phải tạo chứng thư sai SAN và dùng URL có hostname tương ứng, rồi xác nhận handshake thất bại.

### Ví dụ test chứng thư không được tin cậy

~~~java
@Test
void rejectsServerCertificateSignedByUnknownCa() throws Exception {
    SSLContext context = createSslContext(
            trustStoreContainingOnlyExpectedTestCa(),
            null,
            null
    );
    HttpClient client = httpsClient(context);
    HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://localhost:8443/health"))
            .GET()
            .build();

    IOException error = assertThrows(
            IOException.class,
            () -> client.send(
                    request,
                    HttpResponse.BodyHandlers.discarding()
            )
    );

    assertTrue(hasCause(error, SSLHandshakeException.class));
}
~~~

`trustStoreContainingOnlyExpectedTestCa()` là fixture chứa đúng CA mà test cho phép. Server trong trường hợp này phải dùng chứng thư được ký bởi CA khác. Helper `hasCause` duyệt chuỗi cause vì JDK có thể bọc lỗi handshake bên trong `IOException`. Test hostname sai và chứng thư hết hạn cũng nên được kiểm tra tương tự bằng fixture tương ứng.

Lỗi TLS xảy ra trước khi HTTP request được xử lý. Vì vậy, test negative TLS nên kiểm tra lỗi kết nối/handshake, không mong đợi HTTP `401` hay `403` từ ứng dụng.

## 4. Kiểm thử phiên bản TLS và cấu hình cipher

Chính sách triển khai nên ưu tiên TLS 1.3 và chỉ cho phép TLS 1.2 khi còn nhu cầu tương thích với cấu hình cipher an toàn. TLS 1.0 và TLS 1.1 đã lỗi thời và không nên được chấp nhận. Cần kiểm tra cấu hình thực tế của server và các client quan trọng thay vì chỉ nhìn file cấu hình.

Với Java HttpClient, có thể giới hạn protocol của client trong một test:

~~~java
static HttpClient clientWithProtocols(
        SSLContext context,
        String... protocols
) {
    SSLParameters parameters = new SSLParameters();
    parameters.setProtocols(protocols);

    return HttpClient.newBuilder()
            .sslContext(context)
            .sslParameters(parameters)
            .build();
}
~~~

Sau request HTTPS thành công, kiểm tra protocol đã thương lượng:

~~~java
HttpResponse<Void> response = client.send(
        request,
        HttpResponse.BodyHandlers.discarding()
);

String negotiatedProtocol = response.sslSession()
        .orElseThrow()
        .getProtocol();

assertTrue(
        negotiatedProtocol.equals("TLSv1.3")
        || negotiatedProtocol.equals("TLSv1.2")
);
~~~

Test trên xác minh kết nối đã thương lượng một trong các phiên bản được cho phép. Để kiểm tra server từ chối protocol cũ, dùng client test được cấu hình chỉ hỗ trợ protocol đó và xác nhận handshake thất bại. Tuy nhiên, một số JDK vô hiệu hóa protocol cũ ở cấp runtime trước khi request được gửi; khi đó cần ghi nhận đây là giới hạn của client test và kiểm tra policy server bằng một TLS test client phù hợp trong môi trường tích hợp.

Không nên hard-code một danh sách cipher chung cho mọi JDK và mọi phiên bản TLS. Danh sách cipher hợp lệ phụ thuộc runtime, provider, TLS version và chính sách triển khai. Hãy xác minh cấu hình được triển khai, loại bỏ cipher yếu theo baseline bảo mật đang áp dụng và kiểm thử handshake với các cipher được phép.

## 5. Kiểm thử mutual TLS (mTLS)

Trong mTLS, client gửi chứng thư của mình trong TLS handshake và server xác minh chain, thời hạn, EKU, chính sách thu hồi và danh tính theo cấu hình. mTLS thường được dùng cho service-to-service hoặc client authentication tại OAuth Token Endpoint.

Ba tình huống tối thiểu:

1. Client có chứng thư được CA tin cậy ký và còn hiệu lực: handshake thành công.
2. Client không gửi chứng thư trong khi server yêu cầu mTLS: handshake bị từ chối.
3. Client gửi chứng thư không tin cậy, hết hạn hoặc sai EKU: handshake bị từ chối.

Với server test yêu cầu client certificate, cấu hình tương đương `need client authentication` phải được bật trong listener TLS. Tùy server framework, tên cấu hình có thể là `needClientAuth` hoặc `client-auth=need`. Hãy xác nhận đúng listener/port được bảo vệ, vì một server có thể vô tình chỉ bật mTLS trên một connector mà endpoint nhạy cảm lại chạy trên connector khác.

Test mTLS cần bao gồm cả request hợp lệ và các trường hợp không có client cert:

| Client certificate | TLS handshake | Kết quả ở tầng ứng dụng |
| --- | --- | --- |
| Chứng thư tin cậy, còn hạn | Thành công | Tiếp tục xác minh token và authorization |
| Không gửi chứng thư, server yêu cầu mTLS | Thất bại | Không có HTTP response từ ứng dụng |
| Chứng thư do CA lạ ký | Thất bại | Không có HTTP response từ ứng dụng |
| Chứng thư hết hạn | Thất bại | Không có HTTP response từ ứng dụng |
| Chứng thư hợp lệ nhưng client không có quyền nghiệp vụ | Thành công | Bị từ chối theo chính sách authorization |

**mTLS xác thực client ở tầng kết nối, không tự cấp mọi quyền nghiệp vụ.** Một service có chứng thư hợp lệ vẫn cần được phân quyền để gọi API, tenant và hành động tương ứng.

## 6. Kiểm thử OAuth 2.0 với certificate-bound access token

RFC 8705 mô tả OAuth 2.0 Mutual-TLS Client Authentication và certificate-bound access token. Với access token được ràng buộc chứng thư, Authorization Server đưa thumbprint của client certificate vào claim `cnf.x5t#S256`. Resource Server phải xác minh chứng thư client thực sự dùng trên kết nối TLS tương ứng khớp thumbprint đó.

Đây là khác biệt quan trọng:

- **Chỉ dùng mTLS:** kết nối được xác thực bằng client certificate; access token vẫn có thể là bearer token thông thường nếu không được ràng buộc.
- **Certificate-bound access token:** token còn gắn với chứng thư cụ thể. Kẻ lấy được token nhưng không có private key tương ứng không thể sử dụng token thành công qua kết nối khác.

Test matrix:

| Access token | Chứng thư client của kết nối | Kết quả mong đợi |
| --- | --- | --- |
| Token ràng buộc cert A | Cert A hợp lệ | Có thể tiếp tục kiểm tra scope/authorization |
| Token ràng buộc cert A | Cert B hợp lệ nhưng khác thumbprint | Từ chối token |
| Token ràng buộc cert A | Không có client certificate | Handshake bị từ chối nếu listener yêu cầu mTLS; nếu không, token binding vẫn phải thất bại |
| Token không có ràng buộc cert | Cert A hợp lệ | Áp dụng chính sách bearer token thông thường |
| Token ràng buộc cert A | Cert A hết hạn/không tin cậy | TLS handshake thất bại |

Không chỉ so sánh subject hoặc serial number của certificate; cần tính thumbprint theo thuật toán và encoding mà RFC 8705 quy định. Kiểm tra phải gắn với chứng thư đã được xác minh trong chính kết nối TLS xử lý request.

Nếu TLS kết thúc tại reverse proxy hoặc load balancer, Resource Server có thể không trực tiếp nhìn thấy TLS client certificate. Khi đó phải thiết kế cơ chế truyền danh tính certificate từ proxy đến ứng dụng một cách tin cậy: proxy xóa mọi header client tự gửi có thể giả mạo thông tin certificate, chỉ proxy được phép mới thêm metadata đã xác minh, và đường proxy → ứng dụng cũng phải được bảo vệ. Integration test phải gửi header giả từ client để chứng minh ứng dụng không tin dữ liệu đó.

## 7. Tích hợp TLS với Token Endpoint và Resource Server

Một bài test end-to-end nên xác minh client có thể lấy token qua HTTPS và dùng access token trên HTTPS API:

~~~mermaid
sequenceDiagram
    participant Client
    participant AS as Authorization Server
    participant API as Resource Server
    Client->>AS: HTTPS /oauth/token
    AS-->>Client: access_token + expires_in
    Client->>API: HTTPS + Authorization: Bearer
    API->>API: TLS đã bảo vệ kênh; xác minh token và quyền
    API-->>Client: 200 hoặc lỗi authorization
~~~

Các trường hợp cần kiểm thử:

- Token Endpoint chỉ phục vụ qua HTTPS trên môi trường production-like; request plaintext không được xử lý như một luồng cấp token bình thường.
- Client xác minh CA và hostname của Authorization Server trước khi gửi client secret, authorization code hoặc refresh token.
- Resource Server chỉ nhận access token trên kết nối TLS theo chính sách triển khai.
- Resource Server gọi introspection/JWKS/metadata qua endpoint tin cậy và kiểm tra TLS của peer.
- Redirect, proxy hoặc gateway không làm lộ Authorization header, token body, client secret hay authorization code sang origin khác.
- Khi chứng thư server hết hạn hoặc CA bị loại khỏi trust store, request thất bại ở tầng TLS và không có token được phát hành/trả về.

Không dựa vào redirect từ HTTP sang HTTPS để bảo vệ thông tin xác thực. Client có thể đã gửi dữ liệu nhạy cảm qua HTTP trước khi nhận redirect; một số client còn xử lý redirect theo cách làm mất hoặc chuyển header. Hãy cấu hình endpoint nhạy cảm chỉ nhận HTTPS và kiểm tra hành vi plaintext rõ ràng.

## 8. Phân biệt lỗi TLS, lỗi token và lỗi quyền

Ba lớp lỗi có biểu hiện khác nhau:

| Lớp | Ví dụ | Kết quả thường thấy |
| --- | --- | --- |
| TLS transport | CA không tin cậy, SAN sai, cert hết hạn, mTLS thiếu client cert | Handshake/connect thất bại; không có HTTP status |
| Token authentication | Kết nối TLS hợp lệ nhưng access token sai chữ ký, issuer, audience, hết hạn hoặc bị thu hồi | HTTP `401 Unauthorized` với Bearer challenge phù hợp |
| Authorization | Token hợp lệ nhưng thiếu scope, role hoặc quyền trên tài nguyên | HTTP `403 Forbidden`; có thể kèm `insufficient_scope` |

Một integration test tốt phải chứng minh các lớp này độc lập. Ví dụ:

1. Dùng CA không tin cậy để chứng minh TLS client từ chối trước khi request đến API.
2. Dùng TLS hợp lệ nhưng bearer token giả để chứng minh API trả `401`.
3. Dùng TLS hợp lệ và access token đúng nhưng thiếu scope để chứng minh API trả `403`.
4. Dùng TLS hợp lệ và token đúng scope để chứng minh endpoint thành công.

Không biến mọi lỗi thành `401`. Nếu handshake thất bại thì ứng dụng chưa nhận HTTP request; nếu TLS thành công nhưng token không hợp lệ thì đó mới là lỗi xác thực token.

## 9. Kiểm thử certificate rotation và thu hồi

Chứng thư có vòng đời: phát hành, triển khai, gia hạn, xoay vòng, thu hồi và loại bỏ trust anchor. Test tích hợp nên kiểm tra quá trình chuyển đổi thay vì chỉ kiểm tra một chứng thư cố định:

- **Gia hạn bình thường:** chứng thư mới cùng CA được tin cậy có thể được sử dụng trước khi chứng thư cũ hết hạn.
- **Chuyển CA:** trust store chứa CA cũ và CA mới trong thời gian overlap; server chuyển sang certificate mới; client vẫn kết nối được. Sau khi mọi peer đã chuyển đổi, CA cũ mới được loại bỏ.
- **Chứng thư bị thu hồi:** kiểm tra hành vi theo chính sách CRL/OCSP hoặc cơ chế revocation của platform. Không giả định mọi TLS stack đều tự kiểm tra thu hồi nếu chưa bật và xác minh cấu hình đó.
- **Reload trust store:** thay đổi CA được cập nhật vào process đang chạy theo cơ chế triển khai thực tế; không giả định file trust store đổi là connection pool đã dùng trust store mới.
- **Connection pooling:** kiểm tra kết nối TLS cũ được đóng/refresh đúng thời điểm để chứng thư mới và chính sách mới có hiệu lực.

Với access token certificate-bound, rotation certificate có thể làm token cũ không còn khớp thumbprint. Client cần xin token mới gắn với certificate mới theo chính sách Authorization Server; test không nên mong token cũ tự động chuyển sang certificate mới.

## 10. Thiết kế test suite và quản lý fixture

Nên chia suite theo mục tiêu để dễ tìm nguyên nhân khi thất bại:

| Nhóm | Phạm vi | Ví dụ |
| --- | --- | --- |
| Server TLS tests | CA, chain, SAN, expiry, protocol, cipher | Trust CA đúng, sai hostname, cert hết hạn |
| mTLS tests | Client certificate và yêu cầu xác thực hai chiều | Cert đúng, thiếu cert, CA lạ, cert hết hạn |
| OAuth transport tests | HTTPS Token Endpoint, Resource Server, introspection | Không gửi secret/token qua HTTP |
| Token binding tests | RFC 8705 certificate-bound token | Cert đúng thumbprint và cert khác thumbprint |
| Authorization tests | Scope/role sau TLS và token validation | 401 token invalid, 403 thiếu quyền |
| Rotation tests | Thay cert, CA và trust store | Overlap CA, chuyển certificate, thu hồi |

Fixture nên có tên theo mục đích, chẳng hạn `server-valid-localhost.p12`, `server-wrong-san.p12`, `client-valid.p12` và `client-untrusted.p12`. Không đặt password trong repository nếu fixture có thể tạo động; nếu buộc phải dùng fixture đã sinh sẵn, chỉ dùng mật khẩu test không có giá trị ngoài môi trường kiểm thử.

Một số nguyên tắc:

- Không dùng trust-all TrustManager hoặc tắt hostname verification để “cho test chạy”.
- Không dùng chứng thư production hay chia sẻ private key giữa môi trường.
- Không log PEM private key, password, access token hoặc refresh token.
- Kiểm tra đồng hồ test khi tạo certificate và token để tránh lỗi do thời gian.
- Dùng cổng ngẫu nhiên hoặc port được cấp cho test để tránh va chạm.
- Chỉ gọi endpoint local/test; không để test vô tình kết nối issuer hoặc API production.
- Nếu kiểm thử CRL/OCSP, dựng responder test hoặc mock ở tầng được hỗ trợ; ghi rõ test đó xác minh policy nào.

## 11. Checklist kiểm thử TLS cho token security

- [ ] Client xác minh certificate chain và hostname của Authorization Server.
- [ ] Client xác minh certificate chain và hostname của Resource Server.
- [ ] Chứng thư không tin cậy, sai SAN và hết hạn đều làm handshake thất bại.
- [ ] Server gửi đủ intermediate certificate theo cấu hình.
- [ ] Phiên bản TLS được thương lượng nằm trong policy cho phép.
- [ ] Protocol/cipher yếu bị từ chối theo baseline đang triển khai.
- [ ] mTLS yêu cầu client certificate tại đúng listener và endpoint.
- [ ] Chứng thư client sai CA, hết hạn hoặc sai EKU bị từ chối.
- [ ] Service có certificate hợp lệ vẫn phải qua authorization.
- [ ] Certificate-bound access token chỉ dùng được với certificate có thumbprint khớp.
- [ ] Header certificate do client tự gửi không thể giả mạo metadata từ reverse proxy.
- [ ] Token Endpoint, introspection và API không làm lộ credential qua HTTP hoặc redirect.
- [ ] TLS failure được phân biệt với HTTP 401 và 403.
- [ ] Rotation, CA overlap, revocation và reload trust store được kiểm thử theo cơ chế thực tế.
- [ ] Test fixture chỉ chứa dữ liệu và private key dành riêng cho môi trường test.

## 12. Tình huống tổng hợp

Một hệ thống có `auth.example.test` phát hành access token và `orders.example.test` phục vụ API. API yêu cầu mTLS. Client lấy access token qua HTTPS, sau đó gọi `GET /api/orders` với client certificate A. Token chứa `cnf.x5t#S256` khớp thumbprint certificate A.

Hãy kiểm thử lần lượt:

1. CA và SAN của Authorization Server hợp lệ: client lấy được token.
2. Thay chứng thư Authorization Server bằng certificate do CA lạ ký: client không gửi token request và handshake thất bại.
3. Dùng certificate A đã tin cậy để gọi API: TLS thành công, token binding khớp, API tiếp tục kiểm tra scope.
4. Giữ nguyên access token nhưng dùng certificate B: TLS có thể thành công vì B cũng được tin cậy, nhưng Resource Server từ chối token do thumbprint không khớp.
5. Gọi API bằng certificate A nhưng thiếu scope: TLS và token binding thành công, API trả `403`.
6. Bỏ client certificate: listener yêu cầu mTLS từ chối ngay ở TLS handshake.

**Kết luận cần chứng minh bằng test:** TLS xác minh peer và bảo vệ kênh; mTLS xác minh thêm client; certificate-bound token ràng buộc bearer credential với khóa của certificate; Resource Server vẫn phải xác minh token và quyền. Mỗi lớp có điều kiện thành công và thất bại riêng.

## 13. Tài liệu chuẩn tham khảo

- [RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc8446.html): giao thức TLS 1.3 và quy trình handshake.
- [RFC 9325 — Recommendations for Secure Use of TLS and DTLS](https://www.rfc-editor.org/rfc/rfc9325.html): khuyến nghị cấu hình TLS/DTLS an toàn.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705.html): mTLS cho OAuth client authentication và access token ràng buộc chứng thư.
- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): cách sử dụng Bearer access token và yêu cầu bảo vệ token khi truyền.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): xác minh trạng thái token qua introspection endpoint.
