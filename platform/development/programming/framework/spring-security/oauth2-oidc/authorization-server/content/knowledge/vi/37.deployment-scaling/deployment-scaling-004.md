# HTTPS termination, mTLS và cấu hình chứng thư

Authorization Server là điểm tin cậy của hệ thống OAuth 2.0 và OpenID Connect. Client và người dùng dựa vào máy chủ này để xác thực endpoint, nhận authorization code, token và khóa công khai. Vì vậy, HTTPS phải được thiết kế xuyên suốt từ điểm truy cập bên ngoài đến ứng dụng; chứng thư và khóa riêng phải được quản lý như tài sản bảo mật của hệ thống.

Trong bài này, ta xem xét ba phần liên quan chặt chẽ với nhau:

- **HTTPS termination**: nơi kết thúc kết nối TLS, thường là load balancer, ingress hoặc chính Spring Boot.
- **mTLS (mutual TLS)**: cơ chế hai phía cùng xác thực chứng thư trong quá trình bắt tay TLS.
- **Quản lý chứng thư**: cách cấp phát, lưu trữ, tin cậy, luân chuyển và thu hồi chứng thư cho từng kết nối.

Sau khi hoàn thành, bạn có thể chọn kiến trúc TLS phù hợp, cấu hình URL công khai của Authorization Server sau reverse proxy, triển khai mTLS đúng phạm vi và kiểm tra chuỗi chứng thư trước khi đưa dịch vụ vào vận hành.

## 1. Vì sao Authorization Server cần cấu hình TLS chính xác?

TLS cung cấp ba thuộc tính nền tảng:

1. **Bí mật**: dữ liệu trao đổi như authorization code, access token, refresh token và cookie phiên không bị đọc trộm trên đường truyền.
2. **Toàn vẹn**: dữ liệu không bị sửa đổi âm thầm khi truyền qua mạng.
3. **Xác thực máy chủ**: client kiểm tra chứng thư để biết mình đang kết nối đúng tên miền của Authorization Server.

Nếu dùng mTLS, máy chủ còn xác thực danh tính của client ở tầng kết nối bằng chứng thư client. Cơ chế này hữu ích cho kết nối service-to-service hoặc một số profile OAuth yêu cầu chứng thư client.

TLS không thay thế xác thực OAuth. Một kết nối HTTPS hợp lệ chỉ chứng minh các bên đã thiết lập kênh truyền được bảo vệ theo cấu hình TLS; nó không tự cấp quyền truy cập API, không thay thế access token và cũng không chứng minh người dùng đã đăng nhập.

Với OpenID Connect, địa chỉ issuer phải ổn định và khớp chính xác với issuer trong metadata, ID Token và cấu hình client. Nếu reverse proxy kết thúc TLS nhưng ứng dụng lại nhận request HTTP và sinh URL dựa trên request nội bộ, metadata có thể công bố URL http hoặc sai host. Khi đó discovery, redirect URI, kiểm tra issuer và các luồng đăng nhập có thể thất bại dù người dùng truy cập trang ngoài bằng HTTPS.

## 2. Chọn nơi kết thúc TLS

TLS termination là điểm giải mã lưu lượng HTTPS. Có ba kiến trúc phổ biến:

| Kiến trúc | Kết nối | Ứng dụng nhìn thấy | Khi nên dùng |
|---|---|---|---|
| TLS trực tiếp tại Spring Boot | Client → HTTPS → Authorization Server | Request được xử lý trên connector TLS; nếu bật mTLS, connector nhận chứng thư client | Dịch vụ nhỏ, ít lớp mạng hoặc cần ứng dụng trực tiếp kiểm tra chứng thư client |
| TLS kết thúc tại proxy | Client → HTTPS → proxy → HTTP → Authorization Server | Request HTTP nội bộ | Chỉ phù hợp khi mạng nội bộ được bảo vệ, backend chỉ nhận kết nối từ proxy và header chuyển tiếp được kiểm soát |
| TLS kết thúc rồi mã hóa lại | Client → HTTPS → proxy → HTTPS → Authorization Server | Kết nối TLS từ proxy đến ứng dụng | Phù hợp khi cần mã hóa cả chặng nội bộ qua nhiều node, subnet hoặc mạng dùng chung |

### 2.1. TLS trực tiếp tại ứng dụng

Spring Boot embedded server giữ chứng thư máy chủ và xử lý TLS. Mô hình này đơn giản vì ứng dụng nhận trực tiếp thông tin kết nối bảo mật. Nếu bật yêu cầu chứng thư client ở connector, ứng dụng cũng có thể nhận kết quả xác thực client certificate từ TLS handshake.

Điểm cần cân nhắc là việc quản lý chứng thư, gia hạn và cấu hình TLS gắn với từng instance ứng dụng. Khi chạy nhiều replica, mọi instance phải dùng chứng thư phù hợp và được cập nhật đồng bộ.

### 2.2. TLS kết thúc tại load balancer hoặc ingress

Proxy nhận HTTPS từ Internet, kiểm tra chứng thư máy chủ và chuyển request đến ứng dụng. Nếu chặng proxy đến ứng dụng dùng HTTP, request đã được giải mã trên proxy. Vì vậy:

- Backend phải nằm trong mạng riêng và không có đường truy cập trực tiếp từ Internet.
- Firewall hoặc network policy chỉ cho phép proxy được kết nối đến backend.
- Proxy phải xóa header chuyển tiếp do client gửi vào rồi tự tạo giá trị đáng tin cậy.
- Không dùng HTTP cho chặng nội bộ đi qua mạng không tin cậy hoặc có khả năng bị quan sát.

Nếu các điều kiện trên không được bảo đảm, nên mã hóa lại chặng proxy đến ứng dụng bằng HTTPS hoặc dùng TLS passthrough tùy yêu cầu xác thực client.

### 2.3. TLS kết thúc rồi mã hóa lại

Proxy có hai phiên TLS độc lập: một phiên với client và một phiên với Authorization Server. Proxy xác thực chứng thư máy chủ ở chặng backend; ứng dụng xác thực chứng thư của proxy nếu bật mTLS nội bộ.

Trong mô hình này, chứng thư client mà ứng dụng nhìn thấy ở chặng backend thường là chứng thư của proxy. Chứng thư của người dùng hoặc OAuth client ở chặng bên ngoài không tự động được chuyển qua phiên TLS thứ hai. Nếu ứng dụng cần danh tính chứng thư gốc, phải thiết kế một cơ chế chuyển danh tính có xác thực và chỉ tin proxy được chỉ định, hoặc chọn mô hình TLS passthrough phù hợp.

## 3. Cấu hình URL công khai sau reverse proxy

Giả sử người dùng truy cập Authorization Server tại https://auth.example.com, trong khi ứng dụng chạy nội bộ ở http://authorization-server:8080. Proxy cần truyền đúng thông tin URL bên ngoài để Spring xử lý redirect, cookie và endpoint.

Các header thường gặp:

| Header | Ý nghĩa |
|---|---|
| Forwarded | Header chuẩn hóa thông tin host, protocol và địa chỉ proxy |
| X-Forwarded-Proto | Giao thức bên ngoài, ví dụ https |
| X-Forwarded-Host | Host bên ngoài, ví dụ auth.example.com |
| X-Forwarded-Port | Port bên ngoài, thường là 443 |
| X-Forwarded-For | Chuỗi địa chỉ client và proxy theo quy ước của hạ tầng |
| X-Forwarded-Prefix | Prefix bên ngoài nếu proxy công bố ứng dụng dưới một path prefix |

Ứng dụng chỉ được tin các header này khi request đến từ proxy đáng tin cậy. Nếu client có thể tự gửi X-Forwarded-Proto: https hoặc X-Forwarded-Host và proxy chuyển nguyên trạng, client có thể làm sai URL được sinh ra, ảnh hưởng đến redirect, cookie và các kiểm tra bảo mật.

Một ví dụ Nginx tối giản cho trường hợp Nginx là edge proxy trực tiếp:

~~~nginx
server {
    listen 443 ssl;
    server_name auth.example.com;

    ssl_certificate     /etc/nginx/tls/fullchain.pem;
    ssl_certificate_key /etc/nginx/tls/private.key;
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        proxy_pass http://authorization-server:8080;

        proxy_set_header Host $host;
        proxy_set_header Forwarded "";
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
~~~

Ví dụ trên giả định Nginx là proxy biên và $remote_addr đã phản ánh địa chỉ client theo cấu hình mạng. Nếu có load balancer khác đứng trước Nginx, cần cấu hình danh sách proxy tin cậy và chuẩn hóa địa chỉ client trước khi chuyển tiếp. Không lấy nguyên chuỗi header do Internet gửi vào làm dữ liệu tin cậy.

Trong Spring Boot, có thể bật xử lý forwarded header ở tầng framework:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

framework sử dụng cơ chế forwarded header của Spring. Một số runtime có thể dùng xử lý native của container; chọn một chiến lược phù hợp với môi trường và kiểm thử trên đúng container đang chạy. Không bật xử lý forwarded header một cách mù quáng nếu ứng dụng có thể được gọi trực tiếp từ mạng không tin cậy.

### 3.1. Khai báo issuer công khai

Nên cấu hình issuer rõ ràng theo địa chỉ HTTPS công khai:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .build();
}
~~~

Issuer phải khớp chính xác với giá trị mà client dùng để nhận diện Authorization Server, bao gồm scheme, hostname, port nếu có và path nếu có. Không để mỗi replica tự suy ra issuer từ hostname nội bộ hoặc địa chỉ IP của container.

Sau khi triển khai, kiểm tra metadata discovery tại endpoint tương ứng với issuer đã cấu hình. Với issuer đặt ở root domain, URL thường là:

~~~bash
curl --fail --show-error https://auth.example.com/.well-known/openid-configuration
~~~

Đối chiếu trường issuer, authorization_endpoint, token_endpoint, jwks_uri và các endpoint được công bố. Các URL công khai phải dùng đúng scheme, host và path. Nếu hệ thống dùng issuer có path prefix hoặc cấu hình endpoint tùy chỉnh, hãy kiểm tra URL discovery theo cấu hình thực tế.

Đồng thời, cấu hình redirect URI của client phải khớp chính xác URI callback đã đăng ký. Dùng HTTPS cho môi trường triển khai; các ngoại lệ loopback dành cho một số ứng dụng native phải tuân theo quy tắc OAuth tương ứng. Kiểm tra cả URL logout và các URL được nhúng trong ứng dụng frontend.

## 4. Cấu hình chứng thư máy chủ trong Spring Boot

Chứng thư máy chủ thường gồm:

- **Leaf/server certificate**: chứng thư cấp cho hostname công khai hoặc hostname backend.
- **Private key**: khóa riêng tương ứng với chứng thư; phải được giữ bí mật.
- **Intermediate CA certificates**: chứng thư trung gian để client xây dựng chuỗi tin cậy.
- **Root CA**: điểm tin cậy thường đã được cài trong trust store của client.

Trường Subject Alternative Name (SAN) phải chứa hostname mà client sử dụng. Việc chỉ đặt Common Name đúng không thay thế kiểm tra SAN của các client TLS hiện đại. Chứng thư server cần có mục đích sử dụng phù hợp, thường là serverAuth.

### 4.1. Cấu hình embedded server

Khi Spring Boot trực tiếp kết thúc TLS, có thể cấu hình keystore như sau:

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: file:/run/secrets/authorization-server.p12
    key-store-type: PKCS12
    key-store-password: ${SERVER_KEYSTORE_PASSWORD}
    key-alias: authorization-server
    enabled-protocols: TLSv1.2,TLSv1.3
~~~

Các giá trị bí mật phải được cấp từ secret manager hoặc cơ chế secret của nền tảng triển khai. Không commit mật khẩu, private key hay keystore thật vào Git. Đường dẫn file trong ví dụ trỏ đến file được mount vào container; cần bảo đảm tiến trình ứng dụng có quyền đọc file nhưng người dùng và container không liên quan không thể truy cập.

Nếu TLS đã kết thúc tại ingress và backend dùng HTTP, cấu hình server.ssl ở ứng dụng không thay thế chứng thư trên ingress. Nếu backend dùng HTTPS, cấu hình server.ssl cho chứng thư backend và cấu hình proxy xác thực chứng thư đó. Cần phân biệt rõ chứng thư public edge và chứng thư cho chặng nội bộ.

### 4.2. Keystore và truststore

| Thành phần | Chứa gì | Dùng để làm gì |
|---|---|---|
| Keystore | Chứng thư của chính máy chủ và private key tương ứng | Chứng minh danh tính máy chủ trong TLS handshake |
| Truststore | CA hoặc chứng thư được tin cậy | Xác minh chứng thư peer, ví dụ chứng thư client hoặc chứng thư proxy |

Không đưa private key của client vào truststore của máy chủ. Truststore thường chứa CA được phép cấp chứng thư client, thay vì thêm tùy tiện mọi chứng thư cá nhân. Nếu chỉ thêm CA gốc, cần kiểm tra chính sách cấp phát để tránh chấp nhận mọi chứng thư do CA đó cấp ngoài phạm vi mong muốn.

## 5. Triển khai mTLS

Trong TLS một chiều, client xác thực chứng thư máy chủ. Trong mTLS, máy chủ cũng yêu cầu client gửi chứng thư trong handshake và xác minh chuỗi tin cậy của chứng thư đó.

Quá trình xác thực client certificate nên kiểm tra tối thiểu:

1. Chữ ký và chuỗi chứng thư dẫn đến CA được tin cậy.
2. Thời hạn hiệu lực và trạng thái thu hồi theo chính sách.
3. SAN hoặc định danh chứng thư được phép.
4. Extended Key Usage phù hợp với clientAuth.
5. Quy tắc ánh xạ chứng thư sang danh tính client cụ thể.

Chỉ xác thực được chứng thư chưa có nghĩa client được phép gọi mọi endpoint. Sau bước TLS, ứng dụng hoặc gateway vẫn cần ánh xạ danh tính vào client registration, kiểm tra quyền và giới hạn phạm vi truy cập.

### 5.1. Yêu cầu chứng thư tại embedded server

Nếu toàn bộ request đi vào một connector đều phải có client certificate, Spring Boot có thể dùng truststore và client-auth: need:

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: file:/run/secrets/authorization-server.p12
    key-store-type: PKCS12
    key-store-password: ${SERVER_KEYSTORE_PASSWORD}
    key-alias: authorization-server
    trust-store: file:/run/secrets/client-ca.p12
    trust-store-type: PKCS12
    trust-store-password: ${CLIENT_TRUSTSTORE_PASSWORD}
    client-auth: need
    enabled-protocols: TLSv1.2,TLSv1.3
~~~

client-auth: need yêu cầu client gửi chứng thư hợp lệ trên mọi request đi vào connector này. want yêu cầu client gửi chứng thư nhưng cho phép handshake tiếp tục nếu không có chứng thư; ứng dụng phải tự quyết định cách xử lý request thiếu danh tính. Cấu hình này áp dụng ở tầng connector, không tự giới hạn vào riêng token endpoint.

Vì trình duyệt của người dùng thông thường không có client certificate, bật need trên connector phục vụ cả authorization endpoint, trang đăng nhập và consent có thể khiến luồng tương tác không hoạt động. Nếu chỉ một nhóm API hoặc token endpoint cần mTLS, hãy cân nhắc hostname, listener hoặc gateway riêng có chính sách mTLS phù hợp. Phải kiểm tra kỹ phạm vi endpoint và luồng trình duyệt trước khi áp dụng.

Nếu ingress đã kết thúc TLS bên ngoài, cấu hình trên chỉ yêu cầu chứng thư của peer ở chặng ingress đến ứng dụng. Peer đó thường là ingress, không phải chứng thư của OAuth client bên ngoài. Muốn ứng dụng xác thực OAuth client bằng chứng thư gốc, phải bảo đảm danh tính đó được truyền qua một kênh đáng tin cậy hoặc để TLS handshake của client đi đến đúng thành phần thực hiện xác thực.

### 5.2. mTLS tại ingress

Ingress hoặc API gateway có thể yêu cầu chứng thư client ngay tại điểm vào. Cách này tập trung quản lý CA, chính sách chứng thư và giới hạn truy cập ở biên mạng.

Nếu gateway chuyển kết quả xác thực vào ứng dụng qua header, cần áp dụng đầy đủ các điều kiện sau:

- Gateway xóa mọi header cùng tên do client gửi đến trước khi tạo header xác thực.
- Gateway chỉ ghi danh tính sau khi tự xác minh chứng thư và chính sách CA.
- Backend chỉ nhận kết nối từ gateway, qua mạng riêng và policy rõ ràng.
- Header có định dạng chuẩn, giới hạn kích thước và được bảo vệ trên chặng gateway đến backend.
- Ứng dụng chỉ tin header từ gateway đã xác thực; không chấp nhận giá trị do request trực tiếp cung cấp.

Không chuyển nguyên chuỗi PEM hoặc một header như X-Forwarded-Client-Cert rồi mặc định xem đó là bằng chứng hợp lệ. Ứng dụng cần biết gateway nào đã xác minh chứng thư, gateway đã kiểm tra điều kiện nào và dữ liệu định danh có bị sửa trên đường truyền hay không.

## 6. Phân biệt mTLS ở tầng TLS với OAuth 2.0 mTLS

OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens được đặc tả trong RFC 8705. Có hai khả năng riêng:

- **mTLS client authentication**: Authorization Server dùng chứng thư TLS để xác thực OAuth client tại token endpoint.
- **Certificate-bound access token**: access token được ràng buộc với chứng thư client; Resource Server kiểm tra client trình token cũng sở hữu chứng thư tương ứng.

Hai khả năng này có thể được triển khai cùng nhau hoặc độc lập theo profile và chính sách hệ thống. Một cấu hình TLS như server.ssl.client-auth: need chỉ yêu cầu chứng thư ở tầng kết nối. Nó không tự động:

- ánh xạ chứng thư sang một OAuth client registration;
- xác nhận phương thức client authentication tls_client_auth hoặc self_signed_tls_client_auth;
- thêm thumbprint chứng thư vào confirmation claim của access token;
- khiến Resource Server kiểm tra chứng thư khi nhận access token.

Khi triển khai RFC 8705, cần xác nhận phiên bản Spring Authorization Server và các thành phần tích hợp đang dùng hỗ trợ những phần nào. Nếu cần mở rộng, phải thiết kế rõ authentication provider/converter, cách tra cứu chứng thư được đăng ký, quy tắc ánh xạ client, phát hành token có ràng buộc chứng thư và bước xác minh tại Resource Server. Không coi việc bật mTLS ở ingress là đã hoàn tất toàn bộ RFC 8705.

## 7. Vòng đời và bảo vệ chứng thư

### 7.1. Cấp phát và kiểm tra

Trước khi đưa chứng thư vào môi trường triển khai, kiểm tra:

- SAN chứa đúng DNS name mà client truy cập.
- Thời hạn Not Before và Not After phù hợp với thời điểm phát hành.
- Issuer và chuỗi intermediate đúng với CA dự kiến.
- Key Usage và Extended Key Usage phù hợp với vai trò server hoặc client.
- Thuật toán chữ ký và kích thước khóa đáp ứng chính sách bảo mật hiện hành.
- Private key thực sự khớp với public key trong leaf certificate.

Không dùng cùng một chứng thư và private key cho mọi vai trò chỉ để giảm thao tác. Tách chứng thư public edge, backend service và client certificate giúp thu hồi hoặc luân chuyển từng phạm vi mà không ảnh hưởng toàn hệ thống.

### 7.2. Lưu trữ khóa riêng

Đặt private key và keystore trong secret manager, HSM/KMS hoặc secret store do nền tảng quản lý. Với Kubernetes, có thể mount secret thành file chỉ đọc và giới hạn quyền truy cập theo service account. Bảo đảm bản sao lưu, log, artifact build và crash dump không vô tình chứa private key hoặc mật khẩu keystore.

Mật khẩu trong biến môi trường chỉ là một cách truyền cấu hình; nó không thay thế secret manager. Giới hạn quyền đọc môi trường tiến trình, tránh ghi giá trị bí mật vào log và không đưa nội dung secret vào exception hoặc diagnostic report.

### 7.3. Luân chuyển và thu hồi

Quy trình rotation nên có khoảng thời gian chồng lấn:

1. Cấp chứng thư mới và xác minh chuỗi tin cậy, SAN, EKU cùng thời hạn.
2. Cập nhật truststore hoặc CA bundle ở các bên cần xác minh chứng thư mới.
3. Triển khai chứng thư mới lên proxy hoặc ứng dụng; kiểm tra mọi replica đã nhận cấu hình.
4. Kiểm tra handshake, discovery, token endpoint và các kết nối mTLS thực tế.
5. Sau khi không còn client dùng chứng thư cũ, gỡ chứng thư hoặc CA cũ theo chính sách.

Một số runtime không tự reload keystore khi file được thay thế. Cần xác nhận khả năng reload của container/proxy; nếu không hỗ trợ, thực hiện rolling restart có kiểm soát. Tránh thay chứng thư ở mọi replica cùng lúc khi chưa có phương án rollback.

Khi private key bị lộ hoặc client certificate không còn được phép sử dụng, thu hồi chứng thư và cập nhật CRL/OCSP hoặc trust policy theo khả năng của hạ tầng. Đồng thời đánh giá token đã phát hành: thu hồi chứng thư không tự động thu hồi mọi access token còn hiệu lực, trừ khi Resource Server có cơ chế kiểm tra ràng buộc chứng thư hoặc chính sách thu hồi tương ứng.

## 8. Kiểm tra cấu hình sau triển khai

### 8.1. Kiểm tra chứng thư server

Xem chứng thư mà endpoint công khai trình bày:

~~~bash
openssl s_client \
  -connect auth.example.com:443 \
  -servername auth.example.com \
  -verify 5 \
  -verify_hostname auth.example.com \
  -showcerts \
  -verify_return_error
~~~

Kiểm tra nội dung chứng thư từ file:

~~~bash
openssl x509 -in fullchain.pem -noout \
  -subject -issuer -dates -ext subjectAltName
~~~

Kết quả cần thể hiện hostname đúng trong SAN, thời hạn còn hiệu lực và chuỗi chứng thư có thể được xác minh. Thử từ mạng hoặc trust store tương tự môi trường client thực tế; một máy quản trị đã cài CA nội bộ có thể cho kết quả khác với client bên ngoài.

### 8.2. Kiểm tra metadata và endpoint

~~~bash
curl --fail --show-error \
  https://auth.example.com/.well-known/openid-configuration
~~~

Đọc metadata và xác nhận issuer, authorization endpoint, token endpoint, JWKS URI cùng các endpoint khác dùng đúng URL công khai. Tiếp tục kiểm thử authorization code flow với PKCE, callback URI, consent và việc đổi code lấy token. Kiểm tra cookie phiên được đặt với thuộc tính phù hợp như Secure, HttpOnly và SameSite theo luồng ứng dụng.

### 8.3. Kiểm tra mTLS

Với endpoint yêu cầu mTLS, thử cả trường hợp có và không có client certificate:

~~~bash
# Kết nối có client certificate
openssl s_client \
  -connect mtls.auth.example.com:443 \
  -servername mtls.auth.example.com \
  -verify 5 \
  -verify_hostname mtls.auth.example.com \
  -cert client.crt \
  -key client.key \
  -CAfile server-ca.pem \
  -verify_return_error
~~~

Kiểm tra thêm chứng thư hết hạn, chứng thư do CA không tin cậy cấp, chứng thư sai mục đích sử dụng và chứng thư không được ánh xạ vào client được phép. Mỗi trường hợp phải thất bại theo chính sách. Nếu gateway xử lý mTLS, cần kiểm thử cả đường truy cập trực tiếp vào backend để bảo đảm không thể giả mạo header danh tính.

## 9. Sự cố thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Metadata công bố URL http | Ứng dụng không nhận hoặc không tin forwarded header | Kiểm tra proxy có ghi X-Forwarded-Proto: https, cấu hình forwarded-header strategy và issuer |
| Redirect quay về hostname nội bộ | Proxy không chuyển Host/X-Forwarded-Host đúng hoặc issuer chưa cố định | Đối chiếu request header, issuer và redirect URI đã đăng ký |
| Client báo hostname mismatch | SAN không có hostname truy cập hoặc proxy trình sai chứng thư | Kiểm tra SAN và SNI bằng openssl s_client |
| TLS handshake thất bại | Thiếu intermediate, CA không tin cậy, protocol/cipher không tương thích hoặc chứng thư hết hạn | Xem chuỗi chứng thư, thời hạn và log handshake ở cả hai đầu |
| mTLS từ chối client hợp lệ | Truststore thiếu CA, client gửi thiếu intermediate hoặc EKU/định danh không đúng | Kiểm tra chain, EKU, SAN và truststore thực tế của connector/gateway |
| Trang đăng nhập không mở khi bật mTLS | Connector yêu cầu client certificate cho cả trình duyệt người dùng | Kiểm tra phạm vi listener và tách endpoint cần mTLS |
| Ứng dụng nhận danh tính proxy thay vì OAuth client | TLS được kết thúc ở ingress rồi tạo phiên TLS mới đến backend | Xác định điểm xác thực client certificate và thiết kế truyền danh tính an toàn |
| Sau rotation chỉ một số replica hoạt động | Keystore/truststore chưa đồng bộ hoặc runtime chưa reload | Kiểm tra phiên bản secret và chứng thư trên từng replica |

## 10. Checklist triển khai

- [ ] Tất cả endpoint công khai của Authorization Server dùng HTTPS và chứng thư có SAN đúng.
- [ ] Chỉ bật TLS 1.2/1.3 theo chính sách tương thích của hệ thống.
- [ ] Đã xác định rõ TLS kết thúc tại edge, tại ứng dụng hay được mã hóa lại trên chặng backend.
- [ ] Backend HTTP chỉ có thể được truy cập từ proxy tin cậy; nếu đi qua mạng không tin cậy thì dùng TLS.
- [ ] Proxy xóa header chuyển tiếp từ client và tự ghi header theo dữ liệu đã xác minh.
- [ ] Spring xử lý forwarded header đúng với loại proxy/container đang chạy.
- [ ] Issuer và metadata công bố URL HTTPS công khai ổn định.
- [ ] Redirect URI, logout URI và callback đã đăng ký khớp chính xác.
- [ ] Keystore và truststore được phân biệt, cấp quyền truy cập tối thiểu và lấy từ secret store.
- [ ] mTLS chỉ được bật trên listener/endpoint có chủ đích; đã kiểm tra ảnh hưởng đến trình duyệt và luồng consent.
- [ ] Nếu dùng RFC 8705, đã kiểm tra riêng xác thực OAuth client và certificate-bound access token ở Resource Server.
- [ ] Có quy trình rotation, thu hồi, rollback và kiểm tra từng replica.
- [ ] Đã kiểm thử handshake, discovery, authorization code với PKCE, token endpoint và các trường hợp chứng thư không hợp lệ.

## Kết luận

Thiết kế HTTPS cho Authorization Server bắt đầu từ việc xác định đúng điểm kết thúc TLS và bảo vệ mọi chặng kết nối. Khi đặt sau reverse proxy, forwarded header phải đến từ proxy đáng tin cậy và issuer phải phản ánh URL HTTPS mà client thực sự sử dụng. mTLS bổ sung xác thực ở tầng chứng thư, nhưng phạm vi áp dụng và cách ánh xạ chứng thư sang OAuth client cần được thiết kế riêng. Quản lý chứng thư tốt đòi hỏi lưu private key an toàn, kiểm tra chuỗi tin cậy và có quy trình rotation, thu hồi được kiểm thử trước khi vận hành.
