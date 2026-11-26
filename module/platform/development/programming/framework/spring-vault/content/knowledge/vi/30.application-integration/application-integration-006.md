# Tích hợp thư viện bên ngoài cần khóa API hoặc chứng thư

## 1. Vì sao tích hợp SDK bên ngoài cần Spring Vault?

Ứng dụng Spring Boot thường gọi các dịch vụ thanh toán, email, lưu trữ, định danh hoặc API nội bộ qua HTTP client/SDK. Những thư viện đó có thể cần **API key**, access token, hoặc cặp **client certificate + private key** để xác thực qua mutual TLS (mTLS). Lưu các credential này trong source code, file cấu hình đóng gói vào JAR hay container image làm tăng nguy cơ rò rỉ và khiến rotation phải triển khai lại toàn bộ ứng dụng.

Trong module **SPRING_VAULT**, `VaultTemplate`/`VaultOperations` giúp Java truy cập HashiCorp Vault sau khi workload xác thực bằng Kubernetes auth, AppRole hoặc cơ chế khác và nhận quyền qua ACL policy. KV secrets engine có thể cất API key do bên thứ ba cấp; PKI secrets engine có thể cấp chứng thư client khi bên nhận tin CA của tổ chức. Token/lease, Transit encryption, wrapping, giám sát và kiểm thử tích hợp đều ảnh hưởng đến vận hành credential.

Một thiết kế thực tế phải trả lời bốn câu hỏi: **credential lấy từ đâu**, **ai được đọc hoặc cấp**, **thư viện bên ngoài nhận credential như thế nào**, và **khi credential đổi thì client đang chạy có sử dụng giá trị mới không**.

Sau bài này, bạn có thể:

- Chọn KV v2, PKI hoặc cơ chế lấy token của vendor đúng theo giao thức xác thực.
- Đọc API key từ Vault bằng Spring Vault rồi gắn key vào WebClient hoặc SDK.
- Tạo `SSLContext` để HTTP client trình bày client certificate trong mTLS.
- Phân biệt keystore/truststore và certificate do Vault ký với certificate mà vendor chấp nhận.
- Thiết kế rotation/refresh, phân quyền, xử lý lỗi và integration test.

Ví dụ sử dụng `api.vendor.example` và `client.orders.example.test` làm tên miền minh họa. Tên header và giao thức xác thực thực tế phải theo tài liệu của vendor.

## 2. Chọn nguồn credential phù hợp

| Loại credential | Nguồn dữ liệu | Bên nhận cần gì? | Cách quản lý vòng đời |
| --- | --- | --- | --- |
| API key tĩnh do vendor cấp | Vault KV v2 | Chuỗi API key để đặt vào header hoặc SDK config. | Đổi key ở vendor, ghi version mới vào KV, reload client. |
| OAuth access token ngắn hạn | Token endpoint/SDK của vendor, có thể dùng credential bootstrap lưu trong Vault | Access token và thời điểm hết hạn. | Refresh theo giao thức vendor; không coi KV là token provider tự động. |
| Credential động của hệ thống hỗ trợ Vault | Secrets engine tương ứng, ví dụ Database/cloud credentials | Credential và lease metadata. | Theo dõi TTL, renew/revoke và cập nhật connection/client. |
| Client certificate do CA tổ chức cấp | Vault PKI `pki_int/issue/vendor-client` hoặc ký CSR | X.509 certificate, chain, private key hoặc key handle. | Cấp mới trước khi hết hạn, cập nhật TLS client. |
| Client certificate vendor cấp | Keystore/HSM hoặc kho secrets có kiểm soát | Keypair/chứng thư do vendor chấp nhận. | Theo quy trình và CA của vendor; có thể lưu PEM/PKCS#12 trong KV nếu chính sách cho phép. |
| CA certificate để tin server bên ngoài | Truststore từ kênh xác thực và phân phối CA đáng tin | Root/intermediate CA để xác minh TLS server. | Theo dõi thay đổi CA và hostname, không vô hiệu hóa TLS validation. |

**Điều kiện then chốt:** Vault PKI không khiến một vendor bất kỳ tự tin chứng thư mà Vault ký. Nếu vendor yêu cầu chứng thư do CA của họ hoặc CA public đã đăng ký cấp, bạn phải dùng certificate chain họ chấp nhận. Chỉ chọn PKI cấp chứng thư bằng Vault khi quan hệ tin cậy với CA của Vault đã được hai bên thiết lập.

Credential **đăng nhập Vault** cũng khác credential **gọi vendor**. Token nhận từ workload authentication dành cho Vault, không dùng thay API key vendor trừ khi vendor thực sự hỗ trợ giao thức đó.

## 3. Luồng tích hợp từ Vault đến thư viện

~~~mermaid
flowchart LR
 A["Java workload identity"] --> B["Vault auth/session"]
 B --> C["VaultOperations"]
 C --> D["KV v2 API key"]
 C --> E["PKI client certificate"]
 D --> F["Credential provider/cache"]
 E --> G["KeyStore + SSLContext"]
 F --> H["HTTP client / Vendor SDK"]
 G --> H
 H --> I["Third-party API"]
 J["Rotation coordinator"] --> C
 J --> F
 J --> G
~~~

Các vai trò có thể gói trong ít class nhưng phải tách trách nhiệm:

1. **Vault credential source** chỉ đọc secret hoặc xin certificate trên mount/role được phân quyền.
2. **Provider/cache** giữ credential hiện tại trong bộ nhớ và quy định tuổi cache, trạng thái sẵn sàng.
3. **SDK adapter/HTTP client** đưa key vào đúng request hoặc dùng SSL context cho TLS.
4. **Rotation coordinator** chuyển credential mới vào adapter, xác minh kết nối rồi ngừng dùng bản cũ.
5. **Monitoring** ghi tình trạng, phiên bản và thời hạn, không ghi plaintext key/private key.

Nhiều SDK giữ bản sao API key hoặc `SSLContext` từ lúc khởi tạo. Vì vậy **đọc được secret mới từ Vault chưa đồng nghĩa SDK đang sử dụng secret mới**. Quy trình thay credential phải kiểm chứng điều đó.

## 4. Kịch bản A: API key trong KV v2

Giả định đội vận hành đã bật KV version 2 ở mount `secret/` và lưu secret theo path logic `integrations/vendor-a`:

~~~json
{
  "api_key": "<TEST_OR_PLACEHOLDER_ONLY>",
  "account": "orders-staging"
}
~~~

Đây là schema minh họa; không đưa key thật vào tài liệu, Git hoặc lệnh shell ghi lịch sử. API HTTP cho KV v2 đọc qua `GET /v1/secret/data/integrations/vendor-a`, nhưng Spring Vault `VaultKeyValueOperations` nhận đường dẫn tương đối `integrations/vendor-a` và tự thêm prefix KV v2.

### 4.1. Policy tối thiểu và quyền của workload

Token của dịch vụ cần quyền đọc đúng một secret:

~~~hcl
# orders-vendor-a.hcl — policy cấp bởi đội vận hành
path "secret/data/integrations/vendor-a" {
  capabilities = ["read"]
}
~~~

Với KV v2, đường dẫn ACL phải bao gồm `data/`. Không cấp quyền `list` toàn mount, ghi/xóa API key, hoặc đọc key của nhiều vendor nếu không thực sự cần. Role quản trị cập nhật key dùng token và policy riêng. Workload đăng nhập Vault bằng auth method được tổ chức cấp quyền, không nhúng root token vào code.

**KV v2 có version dữ liệu nhưng không tự thay key tại vendor.** Khi cập nhật giá trị ở Vault, mọi SDK đã tạo từ key cũ vẫn phải có cơ chế refresh. KV key tĩnh không mặc nhiên có dynamic lease để Spring Vault tự renew như database credentials.

### 4.2. Đọc và cache key bằng Spring Vault

Ví dụ Java dưới đây dùng Spring Vault và Spring Scheduling, có bean `VaultOperations` đã được cấu hình Vault URL/TLS/workload authentication. Đặt rõ backend `KV_2` để tránh nhầm version mount.

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.beans.factory.InitializingBean;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Component
public final class VendorApiKeyProvider implements InitializingBean {

    private static final Duration MAX_CACHE_AGE = Duration.ofMinutes(10);

    private final VaultKeyValueOperations kv;
    private final AtomicReference<Snapshot> current = new AtomicReference<>();

    private record Snapshot(String key, Instant loadedAt) {}

    public VendorApiKeyProvider(VaultOperations vaultOperations) {
        this.kv = vaultOperations.opsForKeyValue(
                "secret", KeyValueBackend.KV_2);
    }

    @Override
    public void afterPropertiesSet() {
        reload(); // Fail fast nếu key cần thiết không có lúc startup.
    }

    // Cần bật @EnableScheduling trên ứng dụng Spring.
    @Scheduled(fixedDelayString =
            "${app.vendor.key-refresh-ms:300000}")
    public void reload() {
        VaultResponse response = kv.get("integrations/vendor-a");
        Map<String, Object> data =
                response == null ? null : response.getData();

        if (data == null
                || !(data.get("api_key") instanceof String key)
                || key.isBlank()) {
            throw new IllegalStateException(
                    "API key không tồn tại hoặc schema KV không hợp lệ");
        }

        current.set(new Snapshot(key, Instant.now()));
    }

    public String currentKey() {
        Snapshot state = current.get();
        if (state == null
                || state.loadedAt().isBefore(
                        Instant.now().minus(MAX_CACHE_AGE))) {
            throw new IllegalStateException(
                    "API key chưa sẵn sàng hoặc cache đã quá hạn");
        }
        return state.key();
    }
}
~~~

Code trên cố ý không in key ra log. Spring Vault `kv.get` là lời gọi **blocking**, thực hiện ở initialization/scheduler; `currentKey()` chỉ đọc bộ nhớ để dùng ở luồng xử lý request. Giá trị 5 phút và 10 phút chỉ là chính sách cache ví dụ, không phải TTL của key vendor. Nếu Vault lỗi khi refresh, bản cũ có thể vẫn được dùng trong khoảng thời gian cho phép, sau đó bị từ chối để tránh cache bí mật cũ vô hạn.

Để bật scheduling, đặt `@EnableScheduling` ở cấu hình Spring. `InitializingBean.afterPropertiesSet` sẽ làm startup thất bại nếu key không đọc được; lựa chọn đó phù hợp với ứng dụng không thể phục vụ mà thiếu credential. Nếu hệ thống cần khởi động khi Vault gián đoạn, thay bằng readiness gate và cơ chế retry/circuit breaker rõ ràng, không âm thầm chạy với key rỗng.

## 5. Đưa API key vào WebClient hoặc SDK ngoài

### 5.1. Gắn header cho từng request

Giả định vendor yêu cầu header `X-API-Key`. Ví dụ Spring WebFlux `WebClient`:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public final class VendorProfileClient {

    private final WebClient client;
    private final VendorApiKeyProvider keyProvider;

    public VendorProfileClient(
            WebClient.Builder builder,
            VendorApiKeyProvider keyProvider) {
        this.client = builder
                .baseUrl("https://api.vendor.example")
                .build();
        this.keyProvider = keyProvider;
    }

    public Mono<String> fetchProfile() {
        return client.get()
                .uri("/v1/profile")
                .headers(headers ->
                        headers.set("X-API-Key", keyProvider.currentKey()))
                .retrieve()
                .bodyToMono(String.class);
    }
}
~~~

Header được đặt theo request; sau khi provider chuyển sang key B, request mới có thể nhận B. Không gọi Vault blocking trong event loop của WebFlux, và không in request header vào logs/traces. Với vendor dùng `Authorization: Bearer ...` hoặc cơ chế HMAC, thay logic theo hợp đồng thực tế của SDK, không mặc định tên header trên.

**Giới hạn điểm đến:** base URL của vendor phải được kiểm soát; không đưa credential vào yêu cầu có absolute URL tùy ý hoặc redirect sang domain không được phép. Một số client chuyển tiếp header khi redirect; phải kiểm chứng hành vi, chặn redirect không đáng tin và bật TLS hostname verification.

### 5.2. SDK nhận key qua constructor

Một số SDK nhận credential khi tạo object, không đọc lại key trong các lần gọi sau. Mã giả:

~~~text
keyB = credentialProvider.currentKey()
candidate = VendorSdkBuilder.apiKey(keyB).build()
candidate.safeValidationCall()
activeClientReference.set(candidate)
retireOldClientAfterInFlightRequests()
~~~

`VendorSdkBuilder` chỉ là tên giả, không phải lớp của một thư viện có thật. Adapter sản xuất phải dùng API mà vendor SDK thực sự cung cấp. Với SDK hỗ trợ credential callback/interceptor, có thể đọc snapshot mới tại thời điểm request. Với SDK bất biến, phải tạo client mới, kiểm chứng trước và chuyển tham chiếu một cách nguyên tử; không giả định sửa `@ConfigurationProperties` sẽ tự thay credential trong object đã được tạo.

### 5.3. Cách xử lý phản hồi lỗi

- Vault `403` khi đọc KV: kiểm tra role/token/namespace và policy `secret/data/...` trước khi nghĩ API key vendor bị sai.
- Vendor `401` hoặc `403`: key/token đã bị thu hồi, scope/tenant/IP allowlist sai; có thể refresh key một lần theo rate limit, rồi báo lỗi nếu vẫn không hợp lệ.
- Vendor `429`: quota/rate limit; backoff theo hướng dẫn vendor, không rotate key bừa bãi.
- Vendor `5xx`/timeout: retry có giới hạn và idempotency phù hợp; request tạo thanh toán có thể đã hoàn thành phía vendor dù client timeout.

Không retry vô hạn request không idempotent để “thử key mới”; phân loại hệ thống phát sinh lỗi trước rồi mới chọn chính sách khôi phục.

## 6. Kịch bản B: thư viện dùng chứng thư client mTLS

mTLS yêu cầu client có **client certificate + private key** và tin cậy server certificate của vendor. Hai mối quan hệ tin cậy độc lập:

| Vật liệu TLS | Công dụng | Nguồn quản lý |
| --- | --- | --- |
| Client leaf certificate | Trình bày danh tính Java client với vendor. | Vault PKI hoặc chứng thư vendor cho phép. |
| Client private key | Chứng minh quyền sở hữu certificate. | KeyStore/HSM/agent ứng dụng bảo vệ. |
| Client CA chain | Vendor xây chuỗi tin cậy tới CA họ chấp nhận. | Từ issuer/PKI và phân phối theo giao thức. |
| Vendor server CA / trust anchors | Java kiểm tra certificate + hostname của TLS server. | Truststore xác minh độc lập, không ghép tùy tiện với client key. |

Nếu vendor chỉ chấp nhận CA của chính họ, một certificate do Vault tự ký không dùng được dù code Java đã tạo `SSLContext` thành công. Chỉ sử dụng PKI của Vault để cấp client certificate khi vendor tin CA hoặc issuer tương ứng. Nếu vendor cấp keypair riêng, lưu bảo vệ keypair/keystore và nạp theo hướng dẫn vendor; Vault PKI không thay thế issuer đó.

### 6.1. Phân quyền PKI cho client certificate

Giả định Vault PKI mount `pki_int/` và role `vendor-client` cấp certificate với tên `client.orders.example.test`, thời hạn 6 giờ, Extended Key Usage cho client authentication. Role phải được quản trị cấu hình giới hạn DNS/SAN, TTL, thuật toán và loại key phù hợp.

Policy runtime:

~~~hcl
path "pki_int/issue/vendor-client" {
  capabilities = ["update"]
}
~~~

`update` chỉ cho phép gọi endpoint issue của role này, không cho sửa role, CA, issuer hay cấp certificate cho mọi miền. Nếu workload tự tạo private key trong HSM rồi gửi CSR, quy trình dùng `pki_int/sign/vendor-client` và policy của endpoint sign.

### 6.2. Cấp CertificateBundle bằng Spring Vault

~~~java
import java.time.Duration;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultPkiOperations;
import org.springframework.vault.support.CertificateBundle;
import org.springframework.vault.support.VaultCertificateRequest;

@Service
public final class VendorCertificateSource {

    private final VaultPkiOperations pki;

    public VendorCertificateSource(VaultOperations vaultOperations) {
        this.pki = vaultOperations.opsForPki("pki_int");
    }

    public CertificateBundle issueCertificate() {
        VaultCertificateRequest request =
                VaultCertificateRequest.builder()
                        .commonName("client.orders.example.test")
                        .ttl(Duration.ofHours(6))
                        .build();

        return pki.issueCertificate("vendor-client", request)
                .getRequiredData();
    }
}
~~~

`opsForPki("pki_int")` chọn **mount path**; `issueCertificate("vendor-client", request)` chọn **PKI role**. Vault trả về certificate, chain và private key mới khi dùng `issue`. Bundle là dữ liệu cực kỳ nhạy cảm: không serialize vào HTTP response, không ghi log và hạn chế vòng đời trong bộ nhớ/file.

Nếu cần private key không rời khỏi HSM/workload, ứng dụng tạo keypair và CSR cục bộ, gửi qua `signCertificateRequest`; Vault trả certificate đã ký nhưng không trả private key của leaf. Role và ACL vẫn giới hạn danh tính được phép ký.

### 6.3. Chuyển CertificateBundle sang SSLContext

Nhiều HTTP client/SDK hỗ trợ Java `SSLContext` hoặc nhận keystore/truststore. Ví dụ này nhận `vendorTrustStore` đã được cấp từ **CA tin cậy của server vendor** qua kênh an toàn:

~~~java
import java.security.GeneralSecurityException;
import java.security.KeyStore;
import java.security.SecureRandom;

import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

import org.springframework.vault.support.CertificateBundle;

public final class VendorSslContextFactory {

    private VendorSslContextFactory() {}

    public static SSLContext create(
            CertificateBundle clientCertificate,
            char[] keyPassword,
            KeyStore vendorTrustStore) throws GeneralSecurityException {

        KeyStore keyStore =
                clientCertificate.createKeyStore("vendor-client", keyPassword);

        KeyManagerFactory keyManagers = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        keyManagers.init(keyStore, keyPassword);

        TrustManagerFactory trustManagers = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        trustManagers.init(vendorTrustStore);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(keyManagers.getKeyManagers(),
                trustManagers.getTrustManagers(), new SecureRandom());

        return context;
    }
}
~~~

`KeyManagerFactory` chọn private key và client certificate khi server yêu cầu mTLS. `TrustManagerFactory` xác minh server certificate theo truststore. Không đưa certificate client vào truststore như một giải pháp bỏ qua CA của server. Không dùng `trustAll` hoặc tắt hostname verification để vượt qua lỗi handshake.

Nếu server vendor có public certificate chain chuẩn và ứng dụng dùng default JVM truststore được kiểm soát, có thể chọn default trust material thay vì tạo truststore riêng. Nhưng việc chỉ nạp một vendor CA tùy ý khi chưa xác minh cũng không an toàn.

Sử dụng với Java 11+ `HttpClient`:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import javax.net.ssl.SSLContext;

SSLContext tls = VendorSslContextFactory.create(
        certificateBundle, keyPassword, vendorTrustStore);

HttpClient client = HttpClient.newBuilder()
        .sslContext(tls)
        .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.vendor.example/v1/status"))
        .GET()
        .build();

HttpResponse<String> response =
        client.send(request, HttpResponse.BodyHandlers.ofString());
~~~

Đây là ví dụ Java HTTP client chuẩn. Nếu thư viện bên ngoài dùng Reactor Netty, OkHttp, Apache HttpClient hoặc custom TLS transport, phải ánh xạ `SSLContext`/key material vào **đúng client instance**. Tạo `SSLContext` trong JVM chưa làm tất cả SDK tự sử dụng nó.

### 6.4. Spring Boot SSL bundles như một phương án tích hợp

Spring Boot hỗ trợ `SslBundle` cho JKS/PEM, giúp cấu hình key/trust material mà code SDK có thể nhận. Ví dụ nếu Vault Agent/sidecar ghi PEM vào filesystem hạn chế quyền:

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        vendor-client:
          keystore:
            certificate: "file:/run/secrets/vendor-client-chain.pem"
            private-key: "file:/run/secrets/vendor-client-key.pem"
          truststore:
            certificate: "file:/run/secrets/vendor-server-ca.pem"
~~~

Ở Java, bean `SslBundles` cung cấp bundle:

~~~java
import javax.net.ssl.SSLContext;
import org.springframework.boot.ssl.SslBundle;
import org.springframework.boot.ssl.SslBundles;

// sslBundles được Spring inject vào service thích hợp.
SslBundle bundle = sslBundles.getBundle("vendor-client");
SSLContext sslContext = bundle.createSslContext();
~~~

**Lưu ý về reload:** Một số Spring Boot version hỗ trợ `spring.ssl.bundle.pem.<name>.reload-on-update=true` khi thành phần sử dụng bundle có khả năng reload. Những phiên bản/transport cụ thể như web server Tomcat/Netty có hỗ trợ riêng; SDK tự tạo client từ `SSLContext` thường không tự đọc lại PEM chỉ vì file mới xuất hiện. Phải kiểm chứng khả năng reload của chính thành phần tiêu thụ hoặc xây lại client.

Không đưa private key vào Git/JAR/container image. Nếu ghi file, cần ownership, filesystem permission, thay cặp file certificate/key an toàn, kiểm tra tránh ghi dở giữa chừng và cleanup.

## 7. Rotation API key: phối hợp hai hệ thống

Vault KV có thể lưu version mới nhưng **quyền hoạt động của API key thuộc vendor**. Luồng luân phiên khi vendor hỗ trợ hai key đồng thời:

~~~mermaid
sequenceDiagram
    participant Admin as Rotation job
    participant Vendor as Vendor API
    participant Vault as Vault KV v2
    participant App as Java adapter
    Admin->>Vendor: Tạo key B với đúng scope
    Vendor-->>Admin: Key B
    Admin->>Vault: Ghi KV version mới chứa key B
    App->>Vault: Refresh KV key B
    App->>Vendor: Test call an toàn bằng B
    Vendor-->>App: Thành công
    Admin->>Vendor: Revoke key A sau khi cutover
    App->>App: Ngừng dùng SDK instance/secret A
~~~

Không log key B trong CI/artifact hoặc command line. Nếu vendor chỉ cho một key active, lập maintenance/cutover theo quy trình vendor thay vì tự áp dụng overlap. Với nhiều replica, đo xem từng replica đã chuyển sang B chưa rồi mới thu hồi A. Sử dụng metadata về version/modified time của KV để theo dõi tiến độ **không bao gồm giá trị key**.

SDK bất biến cần khởi tạo client mới, validate kết nối rồi chuyển atomically. Các request đang chạy trên client cũ phải được xử lý theo timeout/draining đã xác định; không đóng connection trước khi tác vụ giao dịch quan trọng hoàn tất.

**Cache và sự cố Vault:** Khi refresh thất bại nhưng key cũ còn được vendor cho phép, chính sách có thể giữ cache tạm thời đến max age. Nếu credential bị thu hồi vì lộ, chính sách cần vô hiệu hóa sớm hơn; cache age không phải giấy phép sử dụng key đã bị revoke.

## 8. Rotation certificate mTLS

Chứng thư X.509 có `NotBefore` và `NotAfter`. Renew Vault token hay lease **không sửa ngày hết hạn của certificate đã phát hành**.

Quy trình:

1. Theo dõi `NotAfter` và serial của certificate **đang được SDK dùng**, không chỉ certificate đã cấp ở Vault.
2. Cấp hoặc ký certificate mới đủ sớm trước hạn; kiểm tra SAN, EKU `clientAuth`, issuer và chain vendor tin cậy.
3. Tạo keystore/SSLContext mới hoặc ghi bộ PEM mới bằng cơ chế an toàn.
4. Thử mTLS handshake với endpoint sandbox/health thích hợp, xác minh server thật sự nhận client certificate mới.
5. Chuyển traffic sang client mới hoặc reload TLS component đã chứng minh có hỗ trợ.
6. Ngừng dùng client cũ, thu hồi serial cũ nếu yêu cầu; kiểm tra CRL/OCSP và cache của vendor.
7. Theo dõi lỗi handshake, certificate expiration và trạng thái tất cả replicas.

Nếu thay certificate trước nhưng private key vẫn là bản cũ không tương ứng, TLS sẽ thất bại. Giữ keypair và certificate chain nhất quán; thay thế như một đơn vị. Khi issuer CA được xoay, phải bảo đảm vendor đã cài trust chain mới trước cutover.

## 9. Spring Cloud Vault và các SDK có config tĩnh

Có hai cách lấy credential:

| Hướng | Cách hoạt động | Tác động khi rotation |
| --- | --- | --- |
| Spring Cloud Vault đưa secrets vào environment/property | `@ConfigurationProperties` hoặc SDK builder đọc giá trị lúc startup. | Cần kiểm tra cơ chế refresh/rebind; object SDK cũ thường phải tái tạo. |
| Spring Vault đọc runtime qua `VaultOperations` | Credential provider cache/refresh, adapter đọc snapshot hoặc rebuild SDK. | Có thể chuyển key mà không restart nếu code và SDK hỗ trợ. |
| Vault Agent/CSI ghi file credential | SDK đọc PEM/keystore hoặc secret file. | Cần file rotation an toàn và xác nhận thành phần có file watching/reload. |

Không mặc định mỗi lần KV thay version sẽ tự cập nhật bean Spring đã được khởi tạo. Tương tự, không cho rằng file mới xuất hiện thì SSLContext đã được tạo trước đó cũng đổi. Xác định trước cơ chế cung cấp và nạp lại credential phù hợp lifecycle của SDK.

Với workload đã có identity mạnh như Kubernetes auth hoặc workload identity, để Spring Vault trực tiếp truy cập Vault thường tránh nhu cầu đưa Vault token tĩnh vào ứng dụng. Một bên cấp credential có thể dùng response wrapping để bàn giao AppRole SecretID cho workload khi cần; wrapped token cũng là bearer credential, phải được bảo vệ và unwrap một lần.

## 10. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cần xác minh |
| --- | --- | --- |
| Vault `403 permission denied` ở KV | Token workload thiếu `read` tại `secret/data/integrations/vendor-a` hoặc namespace sai. | Policy/auth role và path KV v2 thật. |
| Vault `404` hoặc secret trả null | Mount sai, KV v1/v2 nhầm, secret chưa có hoặc key đã xóa. | Mount/version, path logic, secret metadata. |
| Vault timeout hoặc TLS handshake fail | Vault endpoint/network, CA, token/session lỗi. | TLS tới Vault, auth, timeout, renew và logs an toàn. |
| Vendor HTTP `401/403` | API key sai/revoked, scope/tenant/IP allowlist sai. | Phiên bản key đang được gửi và vendor authentication. |
| Vendor HTTP `429` | Quota/rate limit. | Retry-after, backoff và rate limiter; không thay key liên tục. |
| Java `PKIX path building failed` | Truststore client không có server CA đúng hoặc chain bị thiếu. | TLS server chain và truststore đang dùng bởi SDK. |
| TLS `bad_certificate`/`certificate_required` | Client không gửi certificate, vendor không tin CA, EKU/chain sai. | Keystore, SSLContext, issuer vendor tin, SAN/EKU. |
| Hostname verification fail | URL/SNI không khớp SAN của server vendor. | URL, DNS, SAN; không tắt hostname validation. |
| Vault đã cấp certificate mới nhưng client gửi bản cũ | SDK giữ SSLContext/connection pool cũ, reload không hoạt động. | Serial client certificate trên handshake mới. |
| Một số replica vẫn lỗi sau rotation | Cache chưa refresh/SDK chưa rebuild, key A revoke quá sớm. | Version credential theo replica và trạng thái client cũ. |

Tránh log credential khi phân tích exception. Với API thanh toán hoặc thao tác có side effect, retry theo idempotency token và tài liệu vendor; request timeout không chứng minh vendor chưa xử lý giao dịch.

## 11. Bảo mật và quan sát

Các nguyên tắc vận hành:

- Xác thực Vault bằng workload identity, cấp policy theo secret path/PKI role; không dùng root token ở runtime.
- Tách quyền đọc API key với quyền ghi KV, tách quyền issue certificate với quyền quản trị PKI issuer/role.
- Bảo vệ kết nối TLS tới **cả Vault và vendor**, kiểm tra hostname, CA và redirect; không dùng `trustAll`.
- Không đưa API key vào URL, logs, APM traces, actuator/config dump, test artifact, stdout hoặc container image.
- Không ghi certificate bundle chứa private key, Vault token, wrapped SecretID, PKCS#12 password hoặc PEM private key vào exception/log.
- Theo dõi tỷ lệ thành công khi fetch credential, cache age, số lần rotation, vendor 401/403/429, TLS errors và thời gian tới `NotAfter`.
- Giữ cấu hình tương ứng giữa staging/production: Vault mount, KV version, PKI role, vendor truststore và SDK version.

Một secret lấy ra từ Vault có thể còn tồn tại trong memory của Java dưới dạng `String` hoặc object SDK. JVM không đảm bảo xóa nhanh đối với `String` bất biến; hạn chế tạo bản sao, debug dump, reflection-based logging và vòng đời giữ secret. Dùng key handle trong HSM khi yêu cầu bảo vệ private key cao hơn.

## 12. Kiểm thử tích hợp có ý nghĩa

Unit test với mock `VaultOperations` chứng minh logic mapping, nhưng **không xác minh ACL Vault, KV version, SSL handshake hay SDK thật sự dùng credential mới**.

### 12.1. API key test

1. Khởi tạo Vault test với KV v2, key A và token workload chỉ có quyền read path được giao.
2. Xác minh `kv.get("integrations/vendor-a")` có dữ liệu, sai mount/key nhận lỗi kiểm soát và token không có policy bị từ chối.
3. Dùng MockWebServer/WireMock hoặc sandbox vendor kiểm tra header `X-API-Key`, hostname/path và TLS server verification; không log giá trị header thật.
4. Cập nhật key B trong Vault, kích hoạt refresh, xác minh request mới dùng B; kiểm tra SDK tĩnh được rebuild khi cần.
5. Giả lập vendor 401/403/429 và timeout; đảm bảo retry có giới hạn và không lặp giao dịch không idempotent.
6. Cố redirect request sang origin khác trong sandbox, xác minh key không bị forward ngoài allowlist.
7. Thử Vault tạm không khả dụng và cache quá hạn, xác nhận readiness/fail-closed theo thiết kế.

### 12.2. Client certificate mTLS test

1. Dùng CA/issuer test và PKI role dành cho client TLS, policy issue của token workload.
2. Cấp certificate bằng Spring Vault; xác minh SAN, `clientAuth` EKU, chain, private key tương ứng và thời hạn.
3. Tạo SSLContext, kết nối một TLS test server yêu cầu certificate ký bởi CA được cho phép; kiểm tra handshake thành công.
4. Thay truststore bằng CA không đúng hoặc dùng server hostname không trùng SAN; kết nối phải bị từ chối.
5. Cấp certificate mới và thay client/SSLContext; kiểm tra certificate serial ở handshake mới đã thay đổi.
6. Thu hồi quyền issue và thử request mới; xác nhận lỗi 403 xử lý an toàn, không lộ private key.
7. Kiểm tra file permission, log/trace và cleanup của toàn bộ key material trong môi trường thử nghiệm.

Để test TTL/rotation, ưu tiên mock `Clock` cho logic cache và dùng certificate thay thế thay vì ngủ hàng giờ. Bài lab không được dùng token quản trị production, tài khoản vendor production hoặc CA đang phục vụ hệ thống thật.

## 13. Bài thực hành tổng hợp

Ứng dụng `orders-service` cần gọi hai vendor:

- **Vendor A:** yêu cầu API key header, hỗ trợ hai key active trong thời gian xoay vòng.
- **Vendor B:** yêu cầu client certificate mTLS do CA của tổ chức ký, được vendor B tin cậy.

Thiết kế policy tối thiểu cho workload:

~~~hcl
path "secret/data/integrations/vendor-a" {
  capabilities = ["read"]
}

path "pki_int/issue/vendor-client" {
  capabilities = ["update"]
}
~~~

Đầu tiên, ứng dụng đọc key A từ KV v2 rồi tạo HTTP request có header đúng. Đồng thời, ứng dụng dùng `VaultPkiOperations` xin chứng thư cho role `vendor-client`, tạo `KeyStore`/`SSLContext` và đưa vào client dùng cho vendor B. Khi đội vận hành thêm key B vào Vault, credential provider refresh rồi request mới sử dụng B; chỉ khi mọi replica hoạt động với B mới thu hồi A tại vendor. Đối với mTLS, phát hành chứng thư mới trước hạn, áp dụng vào TLS client và kiểm tra serial thực tế của kết nối mới.

Checklist nghiệm thu:

| Yêu cầu | Bằng chứng |
| --- | --- |
| ACL tối thiểu | Workload chỉ `read` đúng KV key và `update` đúng PKI issue role. |
| Header đúng | Mock vendor nhận header từ key hiện đang active. |
| Không rò credential | Không thấy key/token/private key trong log, trace, artifact, actuator. |
| TLS hai chiều | Java tin server CA/hostname; vendor tin client certificate chain. |
| Rotation API key | Request mới dùng B, SDK/replica cũ được xử lý trước khi revoke A. |
| Rotation mTLS | Kết nối mới trình bày certificate serial mới đã được vendor chấp nhận. |
| Sự cố có kiểm soát | Vault timeout/cache quá hạn, vendor 401/429 và TLS lỗi được phân loại. |
| Thực hành an toàn | Chỉ dùng Vault test, CA test, vendor sandbox và dữ liệu giả. |

## 14. Câu hỏi tự đánh giá

1. Vì sao Vault KV thay secret version nhưng SDK đã khởi tạo có thể vẫn gửi API key cũ?
2. Với KV v2 mount `secret/`, ACL path phải chứa thành phần nào, còn `kv.get` nhận path gì?
3. Vì sao không nên gọi Spring Vault blocking từ WebFlux event loop ở mỗi HTTP request?
4. Vault token và vendor API key phục vụ hai hệ thống xác thực khác nhau ra sao?
5. Khi vendor không tin CA của Vault, có thể dùng certificate do Vault PKI issue để mTLS với vendor không?
6. `KeyStore` khác `TrustStore` thế nào, và ai xác minh private key/certificate của bên nào?
7. Vì sao tạo `SSLContext` mới không đồng nghĩa SDK đã chuyển sang dùng nó?
8. Khi vendor trả 429, rotate API key có giải quyết đúng vấn đề không?
9. Hãy mô tả trình tự xoay key khi vendor cho phép A/B cùng hoạt động, rồi khi vendor chỉ cho một key.
10. Những kiểm chứng nào cần có để khẳng định một certificate mới đã được TLS client thật sự trình bày?

## Tài liệu tham khảo

- [Spring Vault — Secrets engines và KV operations](https://docs.spring.io/spring-vault/reference/vault/vault-secret-engines.html)
- [Spring Vault — VaultOperations Java API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultOperations.html)
- [Spring Vault — VaultKeyValueOperations Java API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultKeyValueOperations.html)
- [Spring Vault — VaultPkiOperations Java API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultPkiOperations.html)
- [Spring Vault — CertificateBundle Java API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/support/CertificateBundle.html)
- [Spring Cloud Vault — Reference](https://docs.spring.io/spring-cloud-vault/reference/)
- [Spring Boot — SSL bundles và reload](https://docs.spring.io/spring-boot/reference/features/ssl.html)
- [HashiCorp Vault — KV v2 secrets engine](https://developer.hashicorp.com/vault/docs/secrets/kv/kv-v2)
- [HashiCorp Vault — PKI secrets engine](https://developer.hashicorp.com/vault/docs/secrets/pki)
- [HashiCorp Vault — ACL policies](https://developer.hashicorp.com/vault/docs/concepts/policies)
