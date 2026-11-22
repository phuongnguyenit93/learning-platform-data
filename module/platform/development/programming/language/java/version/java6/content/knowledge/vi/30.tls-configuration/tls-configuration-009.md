# Cấu hình TLS — Kiểm thử handshake, truststore và hostname theo công cụ đang dùng

## Mục tiêu

“SSL handshake failed” là một triệu chứng, không phải một nguyên nhân duy nhất. Để chẩn đoán HTTPS/TLS, phải trả lời ít nhất ba câu hỏi riêng:

1. **TLS handshake có khả thi không?** Hai đầu TCP đã kết nối, có cùng TLS protocol và cipher suites, có key agreement và chứng chỉ phù hợp?
2. **Client đang dùng truststore nào?** Certificate chain server có được TrustManager thực sự tin không; issuer, chain, thời hạn, KeyUsage/EKU và algorithm constraints có hợp lệ không?
3. **Hostname/IP có đúng certificate SAN không?** Chứng chỉ được trust **vẫn phải** được kiểm tra với host của URL hoặc hostname được client trông đợi. Trường hợp server certificate thuộc `localhost` nhưng URL dùng `127.0.0.1` có thể cần **IP SAN** riêng.

Bài học này tập trung vào **công cụ nào thực sự đang gọi kết nối**: Java `HttpClient`, `HttpsURLConnection`, low-level `SSLSocket`, JDK `keytool`, curl, OpenSSL `s_client` và các trình duyệt/GUI. Các công cụ này **không mặc định dùng chung một truststore**. Lệnh kiểm tra certificate có thể thành công trong OpenSSL nhưng fail trong Java vì dùng trust anchors khác, hoặc ngược lại.

Sau khi học, bạn có thể:
- Phân biệt TCP/DNS/proxy error, TLS version/cipher mismatch, certificate trust failure, hostname/SAN mismatch và client certificate thiếu trong mTLS.
- Dùng `keytool` xem SAN, issuer, fingerprint, validity và `PrivateKeyEntry` versus `trustedCertEntry` trong PKCS12 stores.
- Export public certificate bằng `-exportcert -rfc`, tạo hai truststores riêng để test đúng/sai trust, **không xuất private key server**.
- Tạo `SSLContext` bằng `TrustManagerFactory` cho client; phân biệt nó với `KeyManagerFactory` cho endpoint identity.
- Dùng `HttpClient.newBuilder().sslContext(...)` và `HttpResponse.sslSession()` để quan sát TLS protocol/cipher thực tế.
- Dùng `HttpsURLConnection` với instance `setSSLSocketFactory`, giữ hostname verification mặc định.
- Dùng raw `SSLSocket` có `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` trước handshake, không mặc định nghĩ raw TLS socket đã xác minh hostname.
- Dùng curl `--cacert` và `--resolve` mà không tắt certificate/hostname verification; xem TLS backend qua `curl -V`.
- Dùng OpenSSL `s_client -CAfile -verify_return_error -verify_hostname/-verify_ip`, phân biệt `-servername` (SNI) với hostname verification.
- Chạy Java 17+ fixture qua HTTPS loopback kiểm tra **36/36 assertions** về truststore, hostname, mTLS và protocol mismatch đã được thực thi trên OpenJDK 24.

**Special Note:** Chỉ trình bày tri thức hiện hành. Sử dụng TLS 1.2/1.3, JSSE, `SSLContext`, `SSLParameters`, `TrustManagerFactory`, `KeyManagerFactory`, `PKCS12`, SAN và các công cụ còn được hỗ trợ. Không khuyên dùng SSLv3/TLS1.0/TLS1.1, các cipher yếu, trust-all, `curl --insecure` hay sửa `cacerts` của cả máy để che lỗi. Với `HttpsServer`, các setter trực tiếp trên `HttpsParameters` đã deprecated từ JDK 23; cấu hình qua `SSLParameters` rồi `setSSLParameters(...)`.

## 1. Phân tích handshake theo từng lớp

```text
https://127.0.0.1:8443/probe
         |
         +--> DNS/proxy routing và TCP connect
         |       FAIL: refused, timeout, bad host, proxy
         v
       TLS hello / supported versions / cipher suites
         |       FAIL: protocol mismatch, cipher mismatch
         v
       Server certificate chain
         |       FAIL: unknown CA, expiry, certificate constraints
         v
       Endpoint identification: URL hostname/IP vs SAN
         |       FAIL: certificate trusted but wrong server name
         v
       Optional client authentication (mTLS)
         |       FAIL: client cert missing/untrusted
         v
       Verified TLS session
         |       HTTP method / route / auth / response
         v
       HTTP 200 / 401 / 403 / 404 / 5xx
```

Đây là mô hình chẩn đoán, không phải thứ tự chính xác của mọi TLS 1.3 handshake message. TLS 1.3 có thể phát alerts sau một bước mà client coi là kết thúc `startHandshake()`, nên test mTLS chắc chắn phải kiểm tra **cả hai phía trao đổi data ứng dụng** hoặc nhận được HTTPS response hợp lệ.

| Quan sát | Chưa đủ để kết luận | Kiểm tra tiếp |
| --- | --- | --- |
| TCP port mở | TLS hợp lệ | Thực hiện TLS handshake |
| Server trình một certificate | Certificate đáng tin | Validate chain + trust anchors |
| `keytool -printcert` đọc file | Client tin certificate | Xem truststore đang được client dùng |
| Trusted cert | URL hostname đúng | So DNS SAN/IP SAN |
| OpenSSL `s_client` in “CONNECTED” | Certificate đã verify | `-verify_return_error` và name check |
| Curl chạy được | Java phải chạy được | So TLS backend và truststore |
| HTTP 403 | TLS handshake fail | Xem application authorization |
| `SSLSession` có protocol | Permission trên resource đã đúng | Kiểm tra authorization riêng |

### Vì sao hai TLS clients khác nhau có thể khác kết quả?

Java SunJSSE thường có default trust material từ JDK `jssecacerts`/`cacerts` hoặc giá trị `javax.net.ssl.trustStore`. Curl có thể dùng OpenSSL CA bundle hoặc Windows native CA store (Schannel). Trình duyệt có thể dùng OS trust hoặc root program riêng. Một client Java còn có thể tự truyền **custom TrustManagers** vào `SSLContext.init`. Vì vậy “cài SSL certificate vào Java” không tự làm curl hoặc browser tin certificate đó.

## 2. Phân biệt server keystore và client truststore

| File trong bài | Mục đích | Có private key? |
| --- | --- | --- |
| `server.p12` | Server TLS identity (PrivateKeyEntry + certificate) | **Có** |
| `other.p12` | Identity của server thử nghiệm có SAN khác | **Có** |
| `client.p12` | Client identity cho mTLS | **Có** |
| `server.pem` | Public certificate xuất ra bằng keytool | Không |
| `other.pem` | Public certificate khác để tạo negative test | Không |
| `trust-good.p12` | Client tin đúng public certificate server | Không |
| `trust-other.p12` | Client chỉ tin unrelated public certificate | Không |

**KeyManagerFactory** cung cấp private key/certificate chain để endpoint **tự chứng minh danh tính**. **TrustManagerFactory** cung cấp trust anchors và logic để endpoint **xác minh certificate của peer**.

```text
HTTPS một chiều:
server.p12 --> KeyManagerFactory --> server SSLContext
trust-good.p12 --> TrustManagerFactory --> client SSLContext

Mutual TLS:
server.p12 --> server KeyManager
client.p12 --> client KeyManager
trust-good.p12 --> client TrustManager (tin server)
client certificate --> server TrustManager (tin client)
```

Một client HTTPS thông thường **không cần server private key**. Nếu ai đó đề nghị copy `server.p12` chứa private key sang client chỉ để khắc phục PKIX error, đó là sai ranh giới bí mật. Export public certificate bằng `keytool -exportcert -rfc` không xuất key, có thể dùng làm file PEM test cho curl/OpenSSL.

## 3. Kiểm tra certificate bằng JDK keytool

`keytool` là công cụ quản lý certificate/keystore hiện hành của JDK. Dưới đây là fixture **cục bộ**: RSA 2048 và SHA256withRSA, certificate có hiệu lực 2 ngày, dùng **loopback 127.0.0.1**, không cho Internet public. Password `demo-only-331-not-for-production` chỉ để thử; tham số `-storepass` trên dòng lệnh có thể bị lộ trong process listing hoặc history. Đối với production dùng secret manager và chính sách khóa phù hợp.

### 3.1. Tạo ba identity certificates (Windows PowerShell)

Trong thư mục test mới (không chứa keystore thật):

```powershell
$env:TLS_DEMO_PASSWORD = "demo-only-331-not-for-production"

keytool -genkeypair -alias server -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 2 -storetype PKCS12 -keystore server.p12 -storepass $env:TLS_DEMO_PASSWORD -keypass $env:TLS_DEMO_PASSWORD -dname "CN=localhost, OU=Test, O=Demo, L=HCMC, ST=HCMC, C=VN" -ext "SAN=ip:127.0.0.1,dns:localhost" -ext "EKU=serverAuth" -noprompt

keytool -genkeypair -alias other -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 2 -storetype PKCS12 -keystore other.p12 -storepass $env:TLS_DEMO_PASSWORD -keypass $env:TLS_DEMO_PASSWORD -dname "CN=other.test, OU=Test, O=Demo, L=HCMC, ST=HCMC, C=VN" -ext "SAN=dns:other.test" -ext "EKU=serverAuth" -noprompt

keytool -genkeypair -alias client -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 2 -storetype PKCS12 -keystore client.p12 -storepass $env:TLS_DEMO_PASSWORD -keypass $env:TLS_DEMO_PASSWORD -dname "CN=demo-client, OU=Test, O=Demo, L=HCMC, ST=HCMC, C=VN" -ext "EKU=clientAuth" -noprompt
```

`server.p12` có SAN DNS localhost **và** IP 127.0.0.1. `other.p12` cố tình có SAN chỉ DNS other.test; khi HTTPS client gọi URL IP 127.0.0.1, cert này phải bị từ chối **dù được tin**. `client.p12` có EKU clientAuth để thử mTLS. Không dùng các fixtures tự ký test làm public TLS certificates.

### 3.2. Xuất certificate PEM, xem fingerprint và SAN

```powershell
keytool -exportcert -rfc -alias server -keystore server.p12 -storetype PKCS12 -storepass $env:TLS_DEMO_PASSWORD -file server.pem
keytool -exportcert -rfc -alias other -keystore other.p12 -storetype PKCS12 -storepass $env:TLS_DEMO_PASSWORD -file other.pem

keytool -printcert -v -file server.pem
keytool -printcert -v -file other.pem
keytool -list -v -keystore server.p12 -storetype PKCS12 -storepass $env:TLS_DEMO_PASSWORD
```

Trong output `-printcert`, xem subject, issuer, SHA-256 fingerprint, Valid from/until, **SubjectAlternativeName** và ExtendedKeyUsage. Đừng chỉ đọc CN; với URL có IP `127.0.0.1`, certificate phải có **IP address SAN** tương ứng. Với URL `https://localhost` thì DNS SAN localhost phù hợp.

`-printcert` chỉ **in nội dung**, không tự kiểm tra client đang tin cert đó. `-exportcert -rfc` xuất PEM certificate công khai, **không xuất private key**.

### 3.3. Tạo truststore tốt và truststore sai (test)

```powershell
keytool -importcert -alias server -file server.pem -keystore trust-good.p12 -storetype PKCS12 -storepass $env:TLS_DEMO_PASSWORD -noprompt
keytool -importcert -alias other -file other.pem -keystore trust-other.p12 -storetype PKCS12 -storepass $env:TLS_DEMO_PASSWORD -noprompt

keytool -list -v -keystore trust-good.p12 -storetype PKCS12 -storepass $env:TLS_DEMO_PASSWORD
keytool -list -v -keystore trust-other.p12 -storetype PKCS12 -storepass $env:TLS_DEMO_PASSWORD
```

`trust-good` có alias server là `trustedCertEntry`, không có private key; `trust-other` chỉ có certificate không liên quan. `-noprompt` chỉ phù hợp **đúng certificate do bạn tự sinh cho test**, hoặc đã đối chiếu fingerprint qua kênh đáng tin. Không dùng để import một CA không xác thực nguồn vào production truststore.

### 3.4. Shell Linux/macOS

Lệnh `keytool` dùng flags tương đương; cú pháp export env khác. Ví dụ:

```bash
export TLS_DEMO_PASSWORD='demo-only-331-not-for-production'

keytool -exportcert -rfc -alias server -keystore server.p12 -storetype PKCS12 -storepass "$TLS_DEMO_PASSWORD" -file server.pem
keytool -printcert -v -file server.pem
keytool -importcert -alias server -file server.pem -keystore trust-good.p12 -storetype PKCS12 -storepass "$TLS_DEMO_PASSWORD" -noprompt
keytool -list -v -keystore trust-good.p12 -storetype PKCS12 -storepass "$TLS_DEMO_PASSWORD"
```

Để chạy toàn bộ fixture trên POSIX, tạo cả ba `.p12` và export hai `.pem` như Windows nhưng thay `$env:TLS_DEMO_PASSWORD` bằng `"$TLS_DEMO_PASSWORD"`. Không đè lên files của dịch vụ thật.

## 4. Java HttpClient: đúng truststore, đúng SSLContext, đúng hostname

### 4.1. Nạp PKCS12 riêng bằng TrustManagerFactory

```java
KeyStore trust = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(Path.of("trust-good.p12"))) {
    trust.load(in, password);
}
TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trust);

SSLContext tls = SSLContext.getInstance("TLS");
tls.init(null, tmf.getTrustManagers(), new SecureRandom());

HttpClient client = HttpClient.newBuilder()
        .sslContext(tls)
        .connectTimeout(Duration.ofSeconds(3))
        .build();
```

Đây là **snippet** (cần imports và `char[] password` đã có), không phải class chạy độc lập. Khởi tạo `SSLContext` bằng **TrustManagers có trust anchors rõ ràng**; không tạo một `X509TrustManager` luôn chấp nhận certificate.

Khi cần mTLS, client `SSLContext.init(clientKeyManagers, trustServerManagers, ...)`; client key managers phải nạp từ `client.p12` có private key/cert tương ứng.

### 4.2. Gửi HTTPS request và xem TLS session

```java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://127.0.0.1:8443/probe"))
        .timeout(Duration.ofSeconds(6))
        .GET().build();

HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

System.out.println(response.statusCode());
response.sslSession().ifPresent(session -> {
    System.out.println(session.getProtocol());
    System.out.println(session.getCipherSuite());
});
```

Snippet cần server ở port 8443. `HttpResponse.sslSession()` trả `Optional<SSLSession>` cho HTTPS response; phiên bản TLS/cipher không phải chuỗi cố định mọi môi trường. Khi kiểm thử cần ghi nhận kết quả **đã thương lượng**, không chỉ tập protocols yêu cầu.

### 4.3. Bảng positive/negative tests quan trọng

| Server certificate | Client trust | URL host | Kỳ vọng |
| --- | --- | --- | --- |
| `server.p12` IP SAN=127.0.0.1 | `trust-good` | `127.0.0.1` | **PASS** |
| `server.p12` self-signed | JDK default trust không có cert test | `127.0.0.1` | **FAIL trust** |
| `server.p12` | `trust-other` | `127.0.0.1` | **FAIL trust** |
| `other.p12` SAN chỉ `other.test` | `trust-other`, tin đúng other cert | `127.0.0.1` | **FAIL hostname** |
| `server.p12`, server NEED client cert | `trust-good`, client thiếu keypair | `127.0.0.1` | **FAIL mTLS** |
| `server.p12`, server NEED client cert | `trust-good` + `client.p12` identity, server tin client | `127.0.0.1` | **PASS mTLS** |
| Server chỉ `TLSv1.2` | Client chỉ `TLSv1.3` | SAN/trust đúng | **FAIL protocol** |

**Điểm mấu chốt:** Hai hàng trust mismatch và hostname mismatch đều thất bại, **nhưng nguyên nhân khác nhau**. Không sửa SAN lỗi bằng cách thêm CA nữa; không sửa trust lỗi bằng cách đổi hostname cho trùng CN.

### 4.4. `javax.net.ssl.trustStore` có tác dụng ở đâu?

Đối với Java code dùng default JSSE trust context, JVM có thể được cấu hình bằng startup options:

```text
-Djavax.net.ssl.trustStore=trust-good.p12
-Djavax.net.ssl.trustStoreType=PKCS12
-Djavax.net.ssl.trustStorePassword=demo-only-331-not-for-production
```

Đây là **ba startup options minh họa**, không phải ba shell commands độc lập. Mật khẩu ở dòng lệnh có thể bị lộ, chỉ dùng với fixture test. Khi ứng dụng đã truyền `builder.sslContext(customTls)`, những JVM options trên **không tự thay** TrustManagers đã init trong `customTls`. Hãy kiểm tra JVM/process/SSLContext thực sự của client đang lỗi.

**Không tự import leaf test certificate vào `$JAVA_HOME/lib/security/cacerts` hay chạy `keytool -cacerts`** để thay đổi trust của các ứng dụng khác. Hãy dùng truststore riêng với kiểm tra fingerprint.

## 5. HttpsURLConnection và raw SSLSocket có khác nhau

### 5.1. HttpsURLConnection

`HttpsURLConnection` vẫn có trong Java hiện nay. Nó làm HTTPS endpoint verification theo mặc định. Khi cần truststore riêng:

```java
HttpsURLConnection conn = (HttpsURLConnection)
    new URL("https://127.0.0.1:8443/probe").openConnection();
conn.setSSLSocketFactory(tls.getSocketFactory());
conn.setConnectTimeout(3000);
conn.setReadTimeout(6000);
try {
    int status = conn.getResponseCode();
    try (InputStream input = conn.getInputStream()) {
        byte[] payload = input.readAllBytes();
    }
} finally {
    conn.disconnect();
}
```

Đây là snippet, cần `SSLContext tls` và imports; server phải đang phục vụ port 8443. **Không** gọi `conn.setHostnameVerifier((h,s)->true)` hay thay default verifier để bypass lỗi. Bài runnable đã kiểm thử HttpsURLConnection với đúng trust+SAN hoạt động.

### 5.2. Raw SSLSocket

`SSLSocket` và `SSLEngine` là JSSE APIs cấp thấp. Theo JSSE reference, **raw sockets không tự bắt buộc HTTPS hostname identification** như các HTTP clients chuyên dụng. Trước handshake:

```java
try (SSLSocket socket = (SSLSocket) tls.getSocketFactory()
        .createSocket("127.0.0.1", 8443)) {
    socket.setSoTimeout(5000);
    SSLParameters params = socket.getSSLParameters();
    params.setEndpointIdentificationAlgorithm("HTTPS");
    socket.setSSLParameters(params);
    socket.startHandshake();
    SSLSession session = socket.getSession();
    System.out.println(session.getProtocol());
}
```

Snippet này yêu cầu `tls` có trust managers đúng. `setEndpointIdentificationAlgorithm("HTTPS")` khiến trust/hostname kiểm tra ở tầng TLS handshake theo quy tắc HTTPS. Nếu certificate `other.p12` được client tin nhưng không có IP SAN, raw socket có endpoint identification phải **fail**.

### 5.3. SNI không phải hostname verification

SNI giúp server biết tên ảo để chọn certificate, nhưng **không tự chứng minh** certificate chọn được khớp tên URL người dùng muốn gọi. Endpoint identification vẫn cần kiểm tra SAN. Dùng đúng URL hostname/IP, SNI và truststore tương ứng; không bỏ xác minh vì đã gửi SNI.

## 6. Curl: --cacert và --resolve (theo TLS backend)

Trước hết kiểm tra chính binary đang dùng:

```powershell
curl.exe -V
```

Trong Windows PowerShell 5.1, `curl` có thể là alias của `Invoke-WebRequest` nên dùng `curl.exe` để gọi curl CLI. Trên máy đã QA, curl.exe là **8.21.0 với Schannel backend**; OpenSSL không có trên PATH. Điều này không cho phép khẳng định mọi máy đều dùng Schannel: OpenSSL-backed curl và Windows native CA store có policy khác.

### 6.1. Một kết nối CLI mẫu có trust rõ ràng

Các lệnh sau giả định **một HTTPS test server khác đang phục vụ tại 127.0.0.1:8443**, với certificate `server.pem` tương ứng. Chương trình Java chính ở mục 8 chọn port ngẫu nhiên, chạy xong tự đóng; **không thể gọi curl vào nó sau khi chương trình đã thoát**. Muốn dùng CLI thật, giữ server thử riêng đang chạy hoặc chỉnh test harness để server chờ.

```powershell
curl.exe --verbose --cacert server.pem https://127.0.0.1:8443/probe
```

`--cacert` cung cấp PEM certificate/CA data để verify peer. Với IP URL, cert phải có **IP SAN=127.0.0.1**. `--verbose` cung cấp TLS/HTTP traces; không lưu private data. Không dùng `curl -k` hay `curl --insecure`: bỏ xác minh peer khiến positive test mất giá trị.

### 6.2. --resolve thay địa chỉ kết nối, không thay hostname URL

```powershell
curl.exe --verbose --cacert server.pem --resolve localhost:8443:127.0.0.1 https://localhost:8443/probe
```

`--resolve host:port:IP` khiến curl kết nối tới địa chỉ IP đã chỉ định nhưng **giữ host trong URL** để dùng trong HTTPS name checking/HTTP Host semantics. Đây là cách test một virtual host trước khi DNS public được cập nhật mà **không bypass TLS identity**.

Negative case, nếu server chỉ trình cert SAN localhost/127.0.0.1:

```powershell
curl.exe --verbose --cacert server.pem --resolve wrong.test:8443:127.0.0.1 https://wrong.test:8443/probe
```

Tên `wrong.test` không được cấp trong cert, nên verification phải fail, với điều kiện server không đổi sang cert khác theo SNI. Nếu môi trường có proxy variables, `--noproxy "*"` giúp ép loopback test không qua proxy.

### 6.3. curl (60) chưa nói là lỗi protocol

curl code 60 thường chỉ lỗi **certificate verification**, gồm unknown CA hoặc hostname mismatch tùy backend. Kiểm tra cert/chain/SAN/trust source trước; không giải quyết bằng `--insecure`. Schannel curl thường dùng native Windows roots, còn OpenSSL backend thường dùng CA bundle/file; một JDK `trust-good.p12` **không tự trở thành trust của curl**.

### 6.4. mTLS bằng curl

curl có `--cert` và `--key` cho client identity phù hợp backend/format. Không trích xuất private key production chỉ để chạy lệnh debug. Nếu sử dụng PEM key/cert thực sự được cấp quyền cho test, áp file permissions và tránh password/history leakage. Fixture Java bên dưới kiểm tra mTLS bằng KeyManagerFactory từ `client.p12` mà không cần xuất private key.

## 7. OpenSSL s_client: thêm xác minh thực sự, không chỉ CONNECTED

`openssl s_client` là một TLS diagnostic tool, **không phải HTTP client hoàn chỉnh**. Theo OpenSSL 3.5 manual, nó có thể tiếp tục sau verification errors nhằm in đủ dấu vết; **`-verify_return_error`** cần có nếu muốn fail khi certificate verification thất bại. `-servername` chỉ gửi SNI, không thay `-verify_hostname`.

**Các lệnh OpenSSL dưới đây dựa trên tài liệu chính thức, chưa được thực thi trong môi trường QA vì không có openssl executable.** Chúng giả định TLS server test đang nghe port 8443 và gửi cert tương ứng với `server.pem`.

### 7.1. Kiểm tra trusted certificate và IP SAN

```bash
openssl s_client \
  -connect 127.0.0.1:8443 \
  -CAfile server.pem \
  -verify_ip 127.0.0.1 \
  -verify_return_error \
  -brief
```

`-CAfile` nhận PEM CA/trusted cert, không phải PKCS12 chứa server private key. `-verify_ip` bắt buộc certificate match IP. `-verify_return_error` làm lệnh dừng khi verify errors thay vì chỉ in cảnh báo.

### 7.2. Kiểm tra DNS hostname và SNI độc lập

```bash
openssl s_client \
  -connect 127.0.0.1:8443 \
  -servername localhost \
  -CAfile server.pem \
  -verify_hostname localhost \
  -verify_return_error \
  -brief
```

`-servername localhost` = SNI. `-verify_hostname localhost` = kiểm tra certificate SAN. Negative test:

```bash
openssl s_client \
  -connect 127.0.0.1:8443 \
  -servername wrong.test \
  -CAfile server.pem \
  -verify_hostname wrong.test \
  -verify_return_error \
  -brief
```

Khi server vẫn trình cert chỉ cho localhost/127.0.0.1, hostname sai phải fail. Nếu SNI làm virtual host chọn cert khác, xác minh certificate **thực** được trình rồi mới kết luận.

### 7.3. -showcerts không đồng nghĩa chain trusted

`-showcerts` giúp xem certificates do server gửi, không chứng minh những certificates đó đều thuộc trust anchors đáng tin. Đồng thời `s_client` có thể handshake được nhưng chưa gửi HTTP request. Muốn kiểm tra HTTP status/body, dùng curl hoặc HttpClient. Nếu đang debug TLS thuần, OpenSSL giúp tách certificate/handshake khỏi routing layer.

## 8. Chương trình Java 17+ kiểm thử handshake/truststore/hostname thực

### 8.1. Setup và phương pháp

File **`TlsTrustHostnameDemo.java`** bên dưới sử dụng:
- `HttpsServer` (JDK module `jdk.httpserver`) chỉ bind `127.0.0.1`, port 0 cho OS chọn.
- `java.net.http.HttpClient` gửi HTTPS thực, không mock TLS.
- `HttpsURLConnection` dùng SSLContext custom.
- `SSLSocket` với HTTPS endpoint identification.
- Ba certificates `server.p12`/`other.p12`/`client.p12` và hai PKCS12 truststores `trust-good.p12`/`trust-other.p12`.
- `SSLContext` + KeyManagerFactory/TrustManagerFactory; mTLS server đòi client identity.
- Timeouts, try-with-resources và shutdown executor/server sau mỗi scenario.

Các negative tests **không yêu cầu exact exception message** vì thông điệp TLS tùy JSSE provider/JDK. Chúng xác minh không có HTTPS response/hợp lệ khi trust, hostname hoặc protocol sai. Positive tests xác minh HTTP 200, body UTF-8, TLS session, cipher suite, server principal. Cả hai phía kiểm chứng mTLS bằng request và body chứa verified client principal.

### 8.2. Toàn bộ mã nguồn `TlsTrustHostnameDemo.java`

```java
import com.sun.net.httpserver.Headers;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpsConfigurator;
import com.sun.net.httpserver.HttpsExchange;
import com.sun.net.httpserver.HttpsParameters;
import com.sun.net.httpserver.HttpsServer;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.URL;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.security.cert.Certificate;
import java.security.cert.X509Certificate;
import java.time.Duration;
import java.util.List;
import java.util.Arrays;
import java.util.Collection;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import javax.net.ssl.HttpsURLConnection;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLPeerUnverifiedException;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.TrustManagerFactory;

public final class TlsTrustHostnameDemo {
    private static final String BODY = "HTTPS verified 🌏";

    private static KeyStore load(String path, char[] password) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(Path.of(path))) {
            store.load(in, password);
        }
        return store;
    }

    private static KeyManagerFactory keyManagers(KeyStore store,
                                                  char[] password)
            throws Exception {
        KeyManagerFactory factory = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        factory.init(store, password);
        return factory;
    }

    private static TrustManagerFactory trustManagers(KeyStore store)
            throws Exception {
        TrustManagerFactory factory = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        factory.init(store);
        return factory;
    }

    private static SSLContext serverContext(KeyStore serverKeys, char[] password,
                                             KeyStore trustedClients)
            throws Exception {
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(keyManagers(serverKeys, password).getKeyManagers(),
                trustedClients == null ? null
                        : trustManagers(trustedClients).getTrustManagers(),
                new SecureRandom());
        return context;
    }

    private static SSLContext clientContext(KeyStore serverTrust,
                                             KeyStore clientIdentity,
                                             char[] password)
            throws Exception {
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(clientIdentity == null ? null :
                        keyManagers(clientIdentity, password).getKeyManagers(),
                trustManagers(serverTrust).getTrustManagers(),
                new SecureRandom());
        return context;
    }

    private static final class Fixture implements AutoCloseable {
        final HttpsServer server;
        final ExecutorService workers = Executors.newFixedThreadPool(4);

        Fixture(SSLContext tls, boolean needClientCertificate,
                String[] protocols) throws IOException {
            server = HttpsServer.create(new InetSocketAddress(
                    InetAddress.getByName("127.0.0.1"), 0), 0);
            server.setHttpsConfigurator(new HttpsConfigurator(tls) {
                @Override
                public void configure(HttpsParameters params) {
                    SSLParameters policy =
                            getSSLContext().getDefaultSSLParameters();
                    policy.setProtocols(protocols);
                    policy.setNeedClientAuth(needClientCertificate);
                    params.setSSLParameters(policy);
                }
            });
            server.createContext("/probe", exchange -> {
                try (exchange) {
                    if (!exchange.getRequestMethod().equals("GET")) {
                        exchange.getResponseHeaders().set("Allow", "GET");
                        byte[] bytes = "Method Not Allowed".getBytes(
                                StandardCharsets.UTF_8);
                        exchange.sendResponseHeaders(405, bytes.length);
                        try (OutputStream out = exchange.getResponseBody()) {
                            out.write(bytes);
                        }
                        return;
                    }
                    HttpsExchange tlsRequest = (HttpsExchange) exchange;
                    String principal;
                    try {
                        principal = tlsRequest.getSSLSession()
                                .getPeerPrincipal().getName();
                    } catch (SSLPeerUnverifiedException ignored) {
                        principal = "none";
                    }
                    String answer = "body=" + BODY + "\n"
                            + "tls=" + tlsRequest.getSSLSession().getProtocol()
                            + "\nclient=" + principal + "\n";
                    byte[] bytes = answer.getBytes(StandardCharsets.UTF_8);
                    Headers response = exchange.getResponseHeaders();
                    response.set("Content-Type", "text/plain; charset=UTF-8");
                    exchange.sendResponseHeaders(200, bytes.length);
                    try (OutputStream out = exchange.getResponseBody()) {
                        out.write(bytes);
                    }
                }
            });
            server.setExecutor(workers);
            server.start();
        }

        int port() {
            return server.getAddress().getPort();
        }

        @Override
        public void close() {
            server.stop(0);
            workers.shutdownNow();
        }
    }

    private static HttpClient client(SSLContext tls, boolean tls13Only) {
        HttpClient.Builder builder = HttpClient.newBuilder()
                .sslContext(tls)
                .connectTimeout(Duration.ofSeconds(3))
                .version(HttpClient.Version.HTTP_1_1);
        if (tls13Only) {
            SSLParameters policy = tls.getDefaultSSLParameters();
            policy.setProtocols(new String[]{"TLSv1.3"});
            builder.sslParameters(policy);
        }
        return builder.build();
    }

    private static HttpRequest get(int port) {
        return HttpRequest.newBuilder(URI.create(
                "https://127.0.0.1:" + port + "/probe"))
                .timeout(Duration.ofSeconds(6)).GET().build();
    }

    private static HttpResponse<String> send(HttpClient client, int port)
            throws Exception {
        return client.send(get(port), HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));
    }

    private static boolean sendFails(HttpClient client, int port) {
        try {
            send(client, port);
            return false;
        } catch (IOException expected) {
            return true;
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new AssertionError(interrupted);
        } catch (Exception unexpected) {
            throw new AssertionError(unexpected);
        }
    }

    private static boolean httpsUrlWorks(SSLContext tls, int port)
            throws IOException {
        HttpsURLConnection conn = (HttpsURLConnection)
                new URL("https://127.0.0.1:" + port + "/probe")
                        .openConnection();
        conn.setSSLSocketFactory(tls.getSocketFactory());
        conn.setConnectTimeout(3000);
        conn.setReadTimeout(6000);
        try {
            if (conn.getResponseCode() != 200) return false;
            try (InputStream in = conn.getInputStream()) {
                return new String(in.readAllBytes(), StandardCharsets.UTF_8)
                        .contains("body=" + BODY);
            }
        } finally {
            conn.disconnect();
        }
    }

    private static String rawSocketProtocol(SSLContext tls, int port)
            throws IOException {
        try (SSLSocket client = (SSLSocket) tls.getSocketFactory()
                .createSocket("127.0.0.1", port)) {
            client.setSoTimeout(5000);
            SSLParameters policy = client.getSSLParameters();
            policy.setEndpointIdentificationAlgorithm("HTTPS");
            client.setSSLParameters(policy);
            client.startHandshake();
            return client.getSession().getProtocol();
        }
    }

    private static boolean rawSocketFails(SSLContext tls, int port) {
        try {
            rawSocketProtocol(tls, port);
            return false;
        } catch (IOException expected) {
            return true;
        }
    }

    private static boolean hasIpSan(X509Certificate cert)
            throws Exception {
        Collection<List<?>> names = cert.getSubjectAlternativeNames();
        if (names == null) return false;
        for (List<?> name : names) {
            if (Integer.valueOf(7).equals(name.get(0))
                    && "127.0.0.1".equals(name.get(1))) {
                return true;
            }
        }
        return false;
    }

    private static void check(String name, boolean result) {
        if (!result) throw new AssertionError(name);
        System.out.println(name + "=true");
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 6) {
            throw new IllegalArgumentException(
                    "server.p12 other.p12 client.p12 trust-good.p12 "
                            + "trust-other.p12 server.pem");
        }
        String secret = System.getenv("TLS_DEMO_PASSWORD");
        if (secret == null || secret.isBlank()) {
            throw new IllegalStateException("Set TLS_DEMO_PASSWORD for demo");
        }
        char[] password = secret.toCharArray();
        try {
            KeyStore serverKeys = load(args[0], password);
            KeyStore otherKeys = load(args[1], password);
            KeyStore clientKeys = load(args[2], password);
            KeyStore trustGood = load(args[3], password);
            KeyStore trustOther = load(args[4], password);
            Certificate serverCert = serverKeys.getCertificate("server");
            Certificate otherCert = otherKeys.getCertificate("other");
            Certificate clientCert = clientKeys.getCertificate("client");
            check("serverPrivateKeyPresent",
                    serverKeys.isKeyEntry("server"));
            check("otherPrivateKeyPresent", otherKeys.isKeyEntry("other"));
            check("clientPrivateKeyPresent", clientKeys.isKeyEntry("client"));
            check("trustGoodContainsCertOnly",
                    trustGood.isCertificateEntry("server")
                    && !trustGood.isKeyEntry("server"));
            check("trustOtherContainsCertOnly",
                    trustOther.isCertificateEntry("other")
                    && !trustOther.isKeyEntry("other"));
            check("trustedServerCertMatches",
                    serverCert.equals(trustGood.getCertificate("server")));
            check("unrelatedCertDiffers", !serverCert.equals(otherCert));
            check("serverIpSanPresent",
                    hasIpSan((X509Certificate) serverCert));
            check("otherIpSanMissing",
                    !hasIpSan((X509Certificate) otherCert));
            ((X509Certificate) serverCert).checkValidity();
            check("serverCertCurrentlyValid", true);
            check("serverPemExported",
                    Files.readString(Path.of(args[5]),
                            StandardCharsets.US_ASCII)
                            .contains("BEGIN CERTIFICATE"));

            SSLContext trusted = clientContext(trustGood, null, password);
            SSLContext unrelated = clientContext(trustOther, null, password);
            SSLContext withIdentity = clientContext(trustGood, clientKeys, password);
            SSLContext plainServer = serverContext(serverKeys, password, null);
            SSLContext wrongNameServer = serverContext(otherKeys, password, null);
            SSLContext mtlsServer = serverContext(serverKeys, password, clientKeys);

            try (Fixture server = new Fixture(plainServer, false,
                    new String[]{"TLSv1.3", "TLSv1.2"})) {
                check("serverLoopbackOnly",
                        server.server.getAddress().getAddress().isLoopbackAddress());
                check("serverPortEphemeral", server.port() > 0);
                check("httpsConfiguratorInstalled",
                        server.server.getHttpsConfigurator() != null);
                HttpResponse<String> ok = send(client(trusted, false), server.port());
                check("trustedClientHttp200", ok.statusCode() == 200);
                check("trustedBodyVisible",
                        ok.body().contains("body=" + BODY));
                check("serverPeerClientNone",
                        ok.body().contains("client=none\n"));
                check("responseContentType",
                        ok.headers().firstValue("Content-Type").orElse("")
                            .equalsIgnoreCase("text/plain; charset=UTF-8"));
                check("clientSslSessionAvailable", ok.sslSession().isPresent());
                String proto = ok.sslSession().orElseThrow().getProtocol();
                check("negotiatedProtocolModern",
                        proto.equals("TLSv1.3") || proto.equals("TLSv1.2"));
                check("serverPeerCertSubject",
                        ok.sslSession().orElseThrow().getPeerPrincipal()
                                .getName().contains("CN=localhost"));
                check("cipherSuiteNotEmpty", !ok.sslSession()
                        .orElseThrow().getCipherSuite().isBlank());
                check("httpsUrlConnectionWorks",
                        httpsUrlWorks(trusted, server.port()));
                String rawProto = rawSocketProtocol(trusted, server.port());
                check("rawSocketEndpointVerified",
                        rawProto.equals("TLSv1.3") || rawProto.equals("TLSv1.2"));
                check("defaultTrustRejectsSelfSigned",
                        sendFails(HttpClient.newHttpClient(), server.port()));
                check("unrelatedTrustRejectsServer",
                        sendFails(client(unrelated, false), server.port()));
            }

            try (Fixture server = new Fixture(wrongNameServer, false,
                    new String[]{"TLSv1.3", "TLSv1.2"})) {
                check("wrongNameServerCertTrustedButMismatch",
                        otherCert.equals(trustOther.getCertificate("other")));
                check("httpClientRejectsWrongIpSan",
                        sendFails(client(unrelated, false), server.port()));
                check("rawSocketRejectsWrongIpSan",
                        rawSocketFails(unrelated, server.port()));
            }

            try (Fixture server = new Fixture(mtlsServer, true,
                    new String[]{"TLSv1.3", "TLSv1.2"})) {
                check("mutualTlsRejectsNoClientIdentity",
                        sendFails(client(trusted, false), server.port()));
                HttpResponse<String> mtls =
                        send(client(withIdentity, false), server.port());
                check("mutualTlsHttp200", mtls.statusCode() == 200);
                check("mutualTlsPeerPrincipal",
                        mtls.body().contains("CN=demo-client"));
                check("mutualTlsPayloadCorrect",
                        mtls.body().contains("body=" + BODY));
            }

            try (Fixture server = new Fixture(plainServer, false,
                    new String[]{"TLSv1.2"})) {
                HttpResponse<String> v12 =
                        send(client(trusted, false), server.port());
                check("tls12OnlyServerSuccess", v12.statusCode() == 200);
                check("tls12Negotiated",
                        v12.sslSession().orElseThrow()
                                .getProtocol().equals("TLSv1.2"));
                check("tls13OnlyClientRejected",
                        sendFails(client(trusted, true), server.port()));
            }
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
```

### 8.3. Biên dịch và chạy

Cần tạo các fixtures bằng `keytool` ở mục 3 trước. Khi `TLS_DEMO_PASSWORD` đúng với mật khẩu các keystores và các files nằm trong cùng thư mục test:

```bash
javac --release 17 TlsTrustHostnameDemo.java
java TlsTrustHostnameDemo server.p12 other.p12 client.p12 trust-good.p12 trust-other.p12 server.pem
```

Không cần framework, không có kết nối Internet; runtime phải có `jdk.httpserver` và `java.net.http`. Với named modules, khai báo `requires jdk.httpserver;` và `requires java.net.http;`. App tự dừng server/executor sau test. Các files certificates/class tạm của lượt QA được dọn trong random directory dưới TEMP; không sửa repository.

### 8.4. Stdout thực tế trên Windows OpenJDK 24

```text
serverPrivateKeyPresent=true
otherPrivateKeyPresent=true
clientPrivateKeyPresent=true
trustGoodContainsCertOnly=true
trustOtherContainsCertOnly=true
trustedServerCertMatches=true
unrelatedCertDiffers=true
serverIpSanPresent=true
otherIpSanMissing=true
serverCertCurrentlyValid=true
serverPemExported=true
serverLoopbackOnly=true
serverPortEphemeral=true
httpsConfiguratorInstalled=true
trustedClientHttp200=true
trustedBodyVisible=true
serverPeerClientNone=true
responseContentType=true
clientSslSessionAvailable=true
negotiatedProtocolModern=true
serverPeerCertSubject=true
cipherSuiteNotEmpty=true
httpsUrlConnectionWorks=true
rawSocketEndpointVerified=true
defaultTrustRejectsSelfSigned=true
unrelatedTrustRejectsServer=true
wrongNameServerCertTrustedButMismatch=true
httpClientRejectsWrongIpSan=true
rawSocketRejectsWrongIpSan=true
mutualTlsRejectsNoClientIdentity=true
mutualTlsHttp200=true
mutualTlsPeerPrincipal=true
mutualTlsPayloadCorrect=true
tls12OnlyServerSuccess=true
tls12Negotiated=true
tls13OnlyClientRejected=true
```

**36/36 PASS**. Mỗi dòng `name=true` chỉ in khi điều kiện đúng; `check` ném `AssertionError` khi sai. Đây là kết quả từ các HTTPS sockets thực bằng Java 17-compatible source trên OpenJDK 24, không phải mock hoặc ví dụ stdout suy đoán. Các negative cases xác minh **kết nối thất bại**; không hardcode exact SSL exception message (phụ thuộc provider/JDK).

### 8.5. Ý nghĩa kết quả

| Nhóm | Assertion đặc trưng | Kết luận |
| --- | --- | --- |
| PKCS12 | `serverPrivateKeyPresent`, `trustGoodContainsCertOnly` | Identity có key, truststore chỉ có cert |
| Trust anchors | `trustedServerCertMatches`, `unrelatedCertDiffers` | Tập tin đúng/sai khác nhau |
| SAN | `serverIpSanPresent`, `otherIpSanMissing` | Phân biệt server cert SAN có/không có IP |
| PEM | `serverPemExported` | keytool xuất public certificate |
| HTTPS session | `trustedClientHttp200`, `clientSslSessionAvailable` | TLS và HTTP 200 thành công |
| Negotiation | `negotiatedProtocolModern`, `cipherSuiteNotEmpty` | TLS1.2/TLS1.3 và cipher đã thương lượng |
| Java client alternatives | `httpsUrlConnectionWorks`, `rawSocketEndpointVerified` | HttpsURLConnection và SSLSocket chấp nhận đúng trust+SAN |
| Trust negative | `defaultTrustRejectsSelfSigned`, `unrelatedTrustRejectsServer` | Default/unrelated trust không tin server |
| Hostname negative | `wrongNameServerCertTrustedButMismatch`, `httpClientRejectsWrongIpSan`, `rawSocketRejectsWrongIpSan` | **Trust đúng certificate vẫn fail vì SAN sai** |
| mTLS negative | `mutualTlsRejectsNoClientIdentity` | Server NEED cert và client thiếu key bị từ chối |
| mTLS positive | `mutualTlsHttp200`, `mutualTlsPeerPrincipal` | Server tin client cert, lấy principal và trả body |
| Protocol mismatch | `tls12Negotiated`, `tls13OnlyClientRejected` | Server TLS1.2-only và client TLS1.3-only không chung protocol |

**Phạm vi kiểm thử:** 36 tests xác minh fixture OpenJDK 24, không đánh giá public CA, CRL/OCSP, certificate rotation, proxy, TLS termination public, browser policy, OpenSSL executable, HTTP body quotas hay một production security audit.

## 9. Troubleshooting theo lỗi thực tế

### 9.1. `PKIX path building failed` trong Java nhưng curl truy cập được

Đầu tiên kiểm tra curl TLS backend: trên Windows Schannel có thể dùng native Windows roots, trong khi Java dùng JDK truststore hoặc custom SSLContext. Đọc JVM startup options và code xây client, xác minh CA/certificate chain được cấp phép rồi import **vào truststore riêng của app**. Không chỉnh global JDK cacerts nếu chỉ một ứng dụng cần trust và không dùng X509TrustManager trust-all.

### 9.2. Java báo “No subject alternative names matching”

Đã trust chain không đủ. Kiểm tra URL host là IP hay DNS, xem SAN bằng `keytool -printcert -v`, và xét SNI nếu virtual host có nhiều certificates. Trường hợp `https://127.0.0.1` cần IP SAN cho `127.0.0.1`; certificate chỉ có DNS SAN `localhost` không được giả định match IP. Sửa SAN/certificate hoặc URL đích đúng, không disable HostnameVerifier.

### 9.3. `s_client` hiển thị cert nhưng Java không trust

Lệnh OpenSSL có sử dụng `-verify_return_error` và `-verify_hostname/-verify_ip` không? Nếu chỉ có `-servername` thì đó là SNI. Java SSLContext còn có TrustManagers riêng, không dùng OpenSSL `-CAfile`. Test cả hai theo tool-specific truststore và policy.

### 9.4. mTLS báo handshake failure

Server có `setNeedClientAuth(true)` và TrustManager tin client CA/cert không? Client có `KeyManagerFactory` từ đúng keypair `client.p12` không? Certificate có EKU clientAuth và thời hạn đúng không? Nếu TLS terminate ở gateway, xác định bên nào thực sự xác minh client certificate; đừng tin header forwarded identity của client trực tiếp.

### 9.5. Server TLS1.2-only, client TLS1.3-only

Không có protocol chung nên fail **dù trust+SAN đúng**. Kiểm tra enabled protocols, suites, `jdk.tls.disabledAlgorithms` và provider policy. Dùng profile TLS1.3/TLS1.2 được hỗ trợ; không bật SSLv3 hoặc TLS1.0/1.1 chỉ để kết nối được.

### 9.6. HTTP 401/403 sau TLS thành công

Đây là lớp HTTP/application authentication/authorization. Certificate/trust/hostname có thể đã ổn. Không dùng import CA hoặc đổi TLS cipher như cách sửa một lỗi phân quyền nghiệp vụ.

## 10. JSSE debug đúng mức

Khi cần quan sát handshake và trust decisions trong JVM test:

```text
-Djavax.net.debug=ssl,handshake,trustmanager
```

Đây là **một JVM startup argument**, không phải shell command độc lập. Có thể thêm `keymanager` nếu debug client certificate selection. Các chế độ `all`/`packet`/`plaintext` có thể tạo logs rất nhạy cảm; không bật trên production traffic một cách vô kiểm soát. JSSE debug format thay đổi theo JDK, không viết business logic parse exact log messages.

Luôn ghi:
- Runtime/JDK version.
- Endpoint URL hostname/IP, port, SNI và proxy.
- Cert subject/issuer/fingerprint/SAN đã sanitize.
- Which truststore/SSLContext/provider/TLS backend.
- Negotiated protocol/cipher hoặc loại handshake failure.
- HTTP status nếu handshake đã hoàn thành.

Không in private keys, passwords, full Authorization headers hoặc request bodies.

## 11. Sai lầm phổ biến và cách phòng tránh

| Sai lầm | Hậu quả | Thực hành đúng |
| --- | --- | --- |
| Tưởng `keytool -printcert` là cert trusted | Chỉ in certificate | Kiểm tra truststore client thực |
| Import server private key sang client | Lộ private key | Chỉ import public cert/CA |
| `-noprompt` với cert không rõ nguồn | Tin attacker cert | Kiểm tra SHA-256 fingerprint/issuer trước |
| Import test cert vào cacerts global | Ảnh hưởng nhiều ứng dụng | Truststore riêng |
| Java truststore được coi là curl truststore | Backend khác | `curl -V` và trust policy riêng |
| Curl OK được coi là Java OK | TLS implementation khác | Test Java client thực |
| `curl -k` để “fix” | Mất certificate verification | Sửa issuer/SAN đúng |
| OpenSSL in CONNECTED = trusted | `s_client` có thể tiếp tục sau error | `-verify_return_error` |
| Chỉ dùng `-servername` | SNI không kiểm tra tên cert | `-verify_hostname/-verify_ip` |
| Dùng URL IP nhưng cert chỉ có DNS SAN | Hostname mismatch | Cấp IP SAN hoặc URL DNS đúng |
| Tắt HostnameVerifier của HttpsURLConnection | MITM risk | Giữ default verification |
| Raw SSLSocket không bật endpoint check | Trust cert sai tên | `setEndpointIdentificationAlgorithm("HTTPS")` |
| Dùng trust-all X509TrustManager | Tin mọi cert giả | TrustManagerFactory từ store được kiểm soát |
| Chỉ sửa JVM `trustStore` khi code có custom context | Không tác dụng | Kiểm tra builder.sslContext/context thực |
| Hardcode SSL exception string | JDK/provider khác | Test pass/fail + cause |
| Handshake trên một phía là đủ cho mTLS | TLS alerts có thể đến sau | Xác minh HTTP response và peer principal |
| mTLS certificate = authorization | Chưa map permission | App RBAC/ABAC riêng |
| Đổi file PKCS12 tưởng context tự reload | Key/trust manager đã init | Rotation/reload strategy |
| TLS tests trên runtime khác production | Trust roots/provider khác | CI cùng JDK/OS/policy |
| Lấy HTTP 403 làm TLS failure | Sai tầng | Kiểm tra authZ |
| Dùng TLS protocol yếu để debug | Bảo mật suy giảm | TLS1.2/1.3 và cập nhật clients |

## 12. Checklist chạy test TLS theo công cụ

1. Biết **đúng tool và TLS backend**: Java JDK/provider, curl Schannel/OpenSSL, OpenSSL version hay browser policy.
2. Có URL/host/IP/port/proxy/SNI cụ thể; kiểm tra TCP listener.
3. Biết certificate **thực** được server trình, chain/intermediates/issuer.
4. Kiểm tra validity, EKU, key constraints, SHA-256 fingerprint và SAN.
5. Kiểm tra trust anchors của **client thật**, không chỉ file server hoặc một tool khác.
6. Nếu URL dùng IP, cần IP SAN; nếu URL DNS, cần DNS SAN.
7. Không tắt certificate trust hoặc hostname verification.
8. Với mTLS, client có private key/cert và server TrustManager phù hợp.
9. Kiểm tra TLS protocols/ciphers có giao nhau và policy không disable.
10. Xác nhận negotiated TLS session và gửi request HTTP thực khi đó là mục tiêu.
11. Có negative tests: unknown CA, wrong truststore, wrong SAN, missing client cert và protocol mismatch.
12. Không đưa credentials/private keys vào logs, shell history hoặc CI artifacts.
13. Sau JDK/CA/provider/OS update, chạy lại matrix, không chỉ test happy path.
14. Nếu TLS terminate ở proxy, xác định trust mỗi network hop.
15. Có chính sách certificate rotation/revocation/expiry và authorization riêng.

## 13. Bài tập tự luyện

**Bài 1 — Đọc truststore:** Dùng `keytool -list -v` cho `trust-good.p12` và `server.p12`; giải thích sự khác nhau giữa `trustedCertEntry` và `PrivateKeyEntry`.

**Bài 2 — So SAN:** Kiểm tra `server.pem` và `other.pem`. Vì sao IP URL 127.0.0.1 có thể hoạt động với server cert nhưng không với other cert?

**Bài 3 — Trust negative:** Đổi HttpClient sang `trust-other` khi server dùng server.p12. Thử nghiệm fail; sau đó dùng đúng trust-good.

**Bài 4 — Hostname negative:** Server dùng other.p12, client trust đúng other cert nhưng URL IP 127.0.0.1. Xác nhận vẫn FAIL; không tắt hostname verification.

**Bài 5 — HttpsURLConnection:** Sử dụng custom `SSLContext` cho HttpsURLConnection, giữ hostname verifier mặc định. So với HttpClient.

**Bài 6 — Raw SSLSocket:** Bật `setEndpointIdentificationAlgorithm("HTTPS")`; nếu thiếu bước này, nguy cơ trust server sai tên là gì?

**Bài 7 — Curl:** Dùng `curl -V`, xác định Schannel hay OpenSSL backend. Chạy `--cacert` với server test có cert phù hợp và không dùng `-k`.

**Bài 8 — --resolve:** Dùng `--resolve localhost:8443:127.0.0.1`, giữ URL host localhost. Khi nào kết quả bị ảnh hưởng bởi SNI?

**Bài 9 — OpenSSL:** Nếu có executable, chạy `s_client -verify_return_error -verify_ip` và một negative case hostname sai. Không kết luận chỉ từ CONNECTED.

**Bài 10 — mTLS:** Thử client có `client.p12` và client không có identity với server NEED cert; phân biệt failure TLS với HTTP 403.

**Bài 11 — Debug:** Dùng `-Djavax.net.debug=ssl,handshake,trustmanager` trong môi trường test không có secrets thật, sau đó tắt debug.

**Bài 12 — Regression:** Đổi JDK provider/version và chạy lại suite; không yêu cầu cipher suite cố định nếu production policy không áp.

## 14. Câu hỏi ôn tập

**1. Handshake TCP thành công đã có TLS session chưa?** Chưa.

**2. Trust certificate có nghĩa hostname đúng không?** Không. Trust và SAN check độc lập.

**3. Java HttpClient lấy trust material từ đâu?** SSLContext được client cấu hình hoặc default JSSE trust.

**4. JDK truststore luôn bằng curl truststore?** Không.

**5. KeyManagerFactory khác TrustManagerFactory thế nào?** Identity/private key so với peer trust.

**6. `keytool -exportcert -rfc` có xuất private key không?** Không, chỉ public certificate.

**7. `keytool -printcert` có xác minh HTTP endpoint không?** Không, chỉ in nội dung certificate.

**8. Cert `CN=localhost` có đủ cho URL IP 127.0.0.1 không?** Không; cần IP SAN phù hợp.

**9. Raw SSLSocket có tự kiểm tra HTTPS hostname?** Không được giả định; bật endpoint identification HTTPS.

**10. HttpsURLConnection có cần trust-all cho self-signed test không?** Không; custom TrustManager tin đúng cert và SAN đúng.

**11. `curl --resolve` có tắt TLS name check không?** Không; nó đổi network target, URL hostname vẫn được dùng.

**12. Vì sao không dùng `curl -k`?** Nó vô hiệu hóa certificate verification, khiến test mất tính an toàn.

**13. `openssl -servername` có kiểm tra SAN chưa?** Chưa; cần `-verify_hostname` hoặc `-verify_ip`.

**14. `openssl s_client` cần gì để dừng khi verify error?** `-verify_return_error`.

**15. `-CAfile` của OpenSSL nhận private-key PKCS12 không?** Không; dùng PEM trusted certificates/CA data.

**16. `SSLSession.getProtocol()` trả HTTP protocol?** Không, TLS protocol.

**17. Client mTLS cần gì?** Private key/cert identity và trust anchors cho server.

**18. Server mTLS cần gì?** Server identity, trust client CA/cert và NEED policy.

**19. TLS handshake thất bại có HTTP 401 không?** Thường không; HTTP handler chưa xử lý request.

**20. 36/36 tests có bảo đảm production-ready?** Không. Còn CA/expiry/revocation/rotation, load, proxy và authZ.

## Tài liệu chính thức còn hiệu lực

- [Oracle Java SE 26 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/26/security/java-secure-socket-extension-jsse-reference-guide.html): TLS handshake, trust managers, endpoint verification, debug properties.
- [Oracle Java SE 26 — keytool](https://docs.oracle.com/en/java/javase/26/docs/specs/man/keytool.html): certificate, PKCS12 import/export/list/inspect.
- [Oracle Java SE 26 — SSLContext](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLContext.html): init key/trust managers.
- [Oracle Java SE 26 — SSLParameters](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLParameters.html): endpoint identification, protocols/client auth.
- [Oracle Java SE 26 — SSLSocket](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLSocket.html): startHandshake/SSLSession.
- [Oracle Java SE 26 — HttpsURLConnection](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/HttpsURLConnection.html): HTTPS connection verification.
- [Oracle Java SE 26 — KeyStore](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/KeyStore.html): PKCS12, PrivateKeyEntry, trusted certificate entries.
- [Oracle Java SE 26 — KeyManagerFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html): private key identity.
- [Oracle Java SE 26 — TrustManagerFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html): truststore/peer verification.
- [Oracle Java SE 26 — HttpClient](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html): SSLContext integration.
- [Oracle Java SE 26 — HttpResponse](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpResponse.html): sslSession().
- [Oracle Java SE 26 — HttpsConfigurator](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsConfigurator.html): TLS parameters cho HttpsServer.
- [OpenSSL 3.5 — openssl-s_client](https://docs.openssl.org/3.5/man1/openssl-s_client/): verify_return_error, verify_hostname, verify_ip, CAfile, SNI.
- [curl — SSL Certificate Verification](https://curl.se/docs/sslcerts.html): native/file CA stores, hostname validation.
- [curl — Command-line Manual](https://curl.se/docs/manpage.html): --cacert, --resolve, --insecure, --noproxy.
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): TLS handshake/authentication.

**Kết luận:** Khi HTTPS lỗi, không hỏi chung “SSL có chạy không?” mà phải hỏi **client nào, TLS backend nào, truststore nào, SAN/hostname nào, và handshake/HTTP đã tới bước nào?**. Dùng `keytool` để xem/quản lý cert, `HttpClient`/`HttpsURLConnection`/`SSLSocket` để kiểm chứng Java thực, curl `--cacert`/`--resolve` và OpenSSL `-CAfile -verify_return_error -verify_hostname/-verify_ip` cho môi trường tương ứng. Một chứng chỉ được tin vẫn bị từ chối nếu hostname không khớp; `mTLS` còn cần client keypair và server trust. Không dùng trust-all hay bỏ hostname check để làm bài test xanh. Bộ Java 17+ đã kiểm thử **36/36 assertions PASS** trên OpenJDK 24.
