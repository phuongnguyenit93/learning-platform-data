# Kiểm tra lỗi ủy quyền, TLS và mất kết nối khi dùng Spring Vault

## 1. Mục tiêu kiểm thử

Ứng dụng Java truy cập **HashiCorp Vault** qua **Spring Vault** và **VaultTemplate/VaultOperations** thường phụ thuộc vào Vault ngay từ lúc khởi động hoặc trong lúc xử lý request. Việc đọc KV secrets, lấy dynamic credentials, gọi Transit encryption hoặc xin chứng thư PKI chỉ đáng tin cậy khi ứng dụng **phân biệt được lỗi bảo mật với lỗi kết nối**.

Một request thất bại có thể do:

- **Ủy quyền (authorization):** token hợp lệ nhưng không có quyền **read** trên path cụ thể; Vault từ chối.
- **Xác thực (authentication):** token thiếu, hết hạn, bị thu hồi hoặc workload đăng nhập sai role.
- **TLS:** chứng thư máy chủ không được tin cậy, hostname không khớp SAN, chứng thư hết hạn hoặc mTLS không đáp ứng yêu cầu.
- **Kết nối:** DNS không phân giải được, không thể mở TCP socket, kết nối bị reset hoặc Vault không phản hồi kịp thời.
- **Trạng thái dịch vụ:** Vault sealed, standby, đang bảo trì, bị giới hạn tải hoặc xảy ra lỗi 5xx.

Bài **Kiểm thử** này tập trung vào **“Kiểm tra lỗi ủy quyền, TLS và mất kết nối”**, với mục tiêu:

1. Xây dựng các test tái hiện **403 permission denied** bằng một token thiếu quyền thật, không phải chỉ mock một exception.
2. Xác minh client **từ chối chứng thư TLS không tin cậy** hoặc **hostname không trùng SAN**; không làm test chạy bằng cách tắt kiểm tra TLS.
3. Tạo lỗi **connection refused**, **read timeout** và **connection reset** một cách cô lập, có giới hạn thời gian.
4. Kiểm tra cách Spring Vault truyền lỗi lên tầng Java và cách ứng dụng quyết định **retry/fail-fast**.
5. Phân biệt **unit test**, **HTTP adapter test** và **integration test với Vault thật**.
6. Giữ token, private key, nội dung secret và dữ liệu audit khỏi log/test report.

Ví dụ dùng dịch vụ **orders-api** đọc KV v2 tại **kv-test/data/app/config**, xác thực bằng workload token chỉ có quyền được giao.

## 2. Bản đồ lỗi: test phải phát hiện đúng nguyên nhân

~~~mermaid
flowchart TD
    A["orders-api gọi VaultTemplate.read"] --> B{"Kết nối TCP/TLS thành công?"}
    B -->|"Không"| C{"Lỗi ở lớp nào?"}
    C --> D["DNS / connect refused / timeout / reset"]
    C --> E["TLS trust / SAN / mTLS"]
    B -->|"Có"| F{"Vault trả HTTP response?"}
    F -->|"403"| G["Kiểm tra token, ACL, path, namespace"]
    F -->|"404"| H["Kiểm tra KV path/version, secret không tồn tại"]
    F -->|"5xx"| I["Vault health, sealed, overload, server error"]
    F -->|"2xx"| J["Đọc response và kiểm tra dữ liệu mong đợi"]
    D --> K["Xử lý kết nối, timeout, retry có giới hạn"]
    E --> L["Sửa CA/hostname/chứng thư; không bỏ qua TLS"]
    G --> M["Dừng; không tự nâng quyền"]
~~~

Một test tốt không chỉ kiểm tra “có ném exception hay không”, vì **HTTP 403**, **TLSHandshakeException** và **ConnectException** đều có thể xuất hiện dưới một wrapper exception của client. Nếu chỉ viết **assertThrows(Exception.class)** thì test có thể “thành công” ngay cả khi kết nối Vault chưa từng được thiết lập.

| Nhóm lỗi | Dấu hiệu thường thấy | Điều cần xác minh | Retry? |
| --- | --- | --- | --- |
| Vault từ chối ACL | **HTTP 403**, thông báo permission denied | Token đang dùng, effective policy, KV v2 path, namespace | Không retry cùng token |
| Token không hợp lệ | **401 hoặc 403**, tùy endpoint và tình huống | Workload auth, token TTL, revoke, session | Chỉ tái xác thực theo quy trình |
| Secret không tồn tại | **404** hoặc **VaultOperations.read(...)** trả null | Path, mount, version KV, dữ liệu đã ghi | Không retry mù |
| TLS CA không tin cậy | **SSLHandshakeException/PKIX** | Truststore, issuer chain | Không |
| TLS hostname sai | Chứng thư không khớp DNS/IP trong SAN | Hostname kết nối, DNS SAN hoặc IP SAN | Không |
| mTLS thiếu chứng thư client | Handshake bị máy chủ từ chối | Keystore client, certificate/key, server policy | Không |
| Connection refused | **ConnectException** | Host/port/listener, network route | Chỉ retry giới hạn nếu tạm thời |
| Read timeout | **SocketTimeoutException/HttpTimeoutException** | Server/proxy không trả response trong budget | Có điều kiện |
| Connection reset | **SocketException** hoặc lỗi I/O | Proxy, network, server đóng socket | Có điều kiện theo operation |
| Vault sealed/standby | Health API với status đặc biệt | Trạng thái Vault/HA routing | Tùy tình huống, không retry vô hạn |

**Chú ý:** trong Vault, mã HTTP health có ý nghĩa riêng: ví dụ mặc định **429** cho standby, **501** cho uninitialized và **503** cho sealed. Không xem mọi **429** là rate limit hoặc mọi **503** là lỗi có thể khắc phục bằng retry.

## 3. Chọn đúng tầng kiểm thử

| Tầng | Công cụ gợi ý | Chứng minh được gì? | Không chứng minh được gì? |
| --- | --- | --- | --- |
| Unit test | JUnit 5, Mockito | Quy tắc phân loại exception, số lượt retry, mapping lỗi | ACL hoặc TLS thật của Vault |
| HTTP adapter test | MockWebServer, WireMock, local HTTP server | 403/5xx giả lập, timeout, response chậm, I/O failure | Danh tính/token được Vault thật ủy quyền |
| TLS integration test | Vault HTTPS lab, CA test, truststore riêng | Trust chain, SAN, client certificate | Quyền truy cập KV nếu không có token hợp lệ |
| Vault integration test | Vault dev/test instance hoặc Testcontainers | Policy thật, token thật, KV v2 GET, phản hồi 403 | Mạng production hoặc hệ thống CA production |
| Fault-injection test | Toxiproxy, proxy test, container network | Reset/timeout/gián đoạn có thể tái hiện | Mọi dạng outage trong production |
| Staging smoke test | Vault staging với identity staging | Đường kết nối, ACL và TLS gần thực tế | Không thay thế test lỗi chủ động ở lab |

**Không chủ động seal Vault hoặc tắt auth method ở môi trường chung** để kiểm tra lỗi. Dùng Vault lab riêng và proxy/fault injection có khả năng khôi phục tự động.

### Tách loại kiểm thử theo độ an toàn

- **Read-only:** test GET KV và các trạng thái lỗi; không thay đổi secret thật.
- **Setup trong lab:** quản trị viên tạo mount test, fake secret, policy và token TTL ngắn; chạy trên Vault test.
- **Fault injection:** chỉ tác động tới đường kết nối của client test, không phá toàn cluster.
- **Cleanup:** thu hồi token test, xóa dữ liệu/mount nếu lab được tạo riêng và chắc chắn không chứa dữ liệu của nhóm khác.

Mọi test phải xác định **environment** trước khi chạy. Nếu không có biến cấu hình Vault test, nên **skip có lý do** hoặc fail cấu hình; không tự động trỏ sang địa chỉ Vault production.

## 4. Chuẩn bị Vault lab và hai token có quyền khác nhau

Ví dụ lệnh dành cho **Vault CLI trong Bash**. Yêu cầu một Vault test đã initialized/unsealed và một operator được cấp quyền tạo mount/policy/token test.

### 4.1 Tạo KV v2 và secret giả

~~~bash
# Chỉ chạy trên Vault lab riêng; không chạy lại nếu mount đã tồn tại.
vault secrets enable -path=kv-test -version=2 kv

vault kv put -mount=kv-test app/config \
  mode="integration-test" \
  feature="enabled"

vault kv get -mount=kv-test app/config
~~~

**Đường dẫn API GET thực** của KV v2 là **kv-test/data/app/config**, khác với logical path **app/config** ở Vault CLI. Sai tiền tố **data/** có thể gây lỗi path chứ không phải lỗi ACL.

### 4.2 Tạo policy cho phép và policy cố tình không cho phép

Ví dụ file HCL dành cho lab:

~~~hcl
# testing-allow.hcl
path "kv-test/data/app/config" {
  capabilities = ["read"]
}
~~~

~~~hcl
# testing-denied.hcl
path "kv-test/data/app/other" {
  capabilities = ["read"]
}
~~~

Policy **testing-denied** không cấp **read** cho secret **app/config**. Sự khác biệt này cho phép kiểm thử một request 403 với **token hợp lệ nhưng thiếu quyền**, thay vì cố dùng token sai định dạng.

~~~bash
vault policy write testing-allow testing-allow.hcl
vault policy write testing-denied testing-denied.hcl

# Trong lab, lưu token vào kho bí mật của môi trường test,
# không in hay commit token vào repository.
TEST_VAULT_ALLOWED_TOKEN=$(
  vault token create -policy=testing-allow -ttl=20m \
    -format=json | jq -r '.auth.client_token'
)

TEST_VAULT_DENIED_TOKEN=$(
  vault token create -policy=testing-denied -ttl=20m \
    -format=json | jq -r '.auth.client_token'
)
~~~

Hai token được cấp thông qua operator có quyền phù hợp. Chúng có thể còn policy **default**; cần bảo đảm không có policy bổ sung cấp quyền đọc secret đang test.

**Không dùng root token làm test subject của case bị từ chối.** Root token có quyền rộng, khiến test không còn phản ánh hành vi phân quyền thông thường.

### 4.3 Preflight bằng Vault CLI

~~~bash
# Thực hiện trong shell của test runner có các token trên.
VAULT_TOKEN="$TEST_VAULT_ALLOWED_TOKEN" \
  vault token capabilities kv-test/data/app/config

VAULT_TOKEN="$TEST_VAULT_DENIED_TOKEN" \
  vault token capabilities kv-test/data/app/config
~~~

Kỳ vọng: token thứ nhất có **read**, token thứ hai có **deny**. Chỉ chạy integration test sau khi Vault test sẵn sàng, mount và secret có thật.

Đối với cluster dùng namespace, phải cung cấp namespace test đồng nhất cho CLI và Java. **Token đúng nhưng namespace sai** có thể cho lỗi tương tự thiếu quyền.

## 5. Kiểm thử ủy quyền thực với VaultTemplate

Ví dụ JUnit 5 dưới đây không phụ thuộc Spring Boot auto-configuration. Nó dùng **VaultEndpoint**, **TokenAuthentication** và **VaultTemplate** được Spring Vault cung cấp.

**Biến môi trường cần có:** **TEST_VAULT_ADDR**, **TEST_VAULT_ALLOWED_TOKEN**, **TEST_VAULT_DENIED_TOKEN**; các token được inject từ secret store của CI/test runner. Không đặt token vào annotation hoặc source code.

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.net.URI;

import org.junit.jupiter.api.Test;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.VaultResponse;

class VaultAuthorizationIT {

    private static final String KV_PATH = "kv-test/data/app/config";

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Thiếu biến test: " + name);
        }
        return value;
    }

    private static VaultOperations client(String token) {
        URI uri = URI.create(requiredEnv("TEST_VAULT_ADDR"));
        return new VaultTemplate(
                VaultEndpoint.from(uri),
                new TokenAuthentication(token));
    }

    @Test
    void validReadTokenCanReadExistingKvSecret() {
        VaultOperations allowed = client(
                requiredEnv("TEST_VAULT_ALLOWED_TOKEN"));

        VaultResponse response = allowed.read(KV_PATH);
        assertThat(response).isNotNull();
        assertThat(response.getData()).isNotNull();
    }

    @Test
    void validTokenWithoutReadPermissionIsRejected() {
        VaultOperations denied = client(
                requiredEnv("TEST_VAULT_DENIED_TOKEN"));

        assertThatThrownBy(() -> denied.read(KV_PATH))
                .as("Token thiếu ACL phải bị Vault từ chối")
                .isInstanceOf(RuntimeException.class);
    }
}
~~~

Đoạn test đầu tiên xác nhận **đường kết nối, mount và secret đang hoạt động**. Đoạn test thứ hai xác nhận client Java nhận lỗi; tuy nhiên **RuntimeException** riêng lẻ **chưa đủ chứng minh đây là 403**. Bước tiếp theo kiểm tra mã HTTP của request cùng danh tính, để tránh false positive do timeout hoặc TLS.

### 5.1 Xác minh HTTP status là 403

Trong test Vault test thuần HTTP hoặc HTTPS đã được trust, có thể dùng **JDK HttpClient** để đọc trực tiếp status của endpoint:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.Test;

class VaultAuthorizationStatusIT {

    @Test
    void deniedWorkloadGetsHttp403() throws Exception {
        String address = System.getenv("TEST_VAULT_ADDR");
        String token = System.getenv("TEST_VAULT_DENIED_TOKEN");

        if (address == null || token == null) {
            throw new IllegalStateException("Thiếu môi trường Vault test");
        }

        URI target = URI.create(
                address.replaceAll("/+$", "")
                        + "/v1/kv-test/data/app/config");

        HttpRequest request = HttpRequest.newBuilder(target)
                .timeout(Duration.ofSeconds(3))
                .header("X-Vault-Token", token)
                .GET()
                .build();

        HttpClient http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .build();

        HttpResponse<Void> response = http.send(
                request, HttpResponse.BodyHandlers.discarding());

        assertThat(response.statusCode()).isEqualTo(403);
    }
}
~~~

Nếu dùng namespace Enterprise, thêm **X-Vault-Namespace** với namespace test khi cần. JDK HttpClient trong ví dụ dùng truststore mặc định; với Vault test dùng CA nội bộ, phải cấu hình truststore của client trước khi chạy. **Không dùng một HTTP client bỏ qua xác minh TLS để lấy status 403**, vì kết quả đó sẽ che giấu lỗi bảo mật cần kiểm tra.

### 5.2 Tách case token sai và case thiếu quyền

**Token hợp lệ thiếu ACL** là case cần kết luận **403 do phân quyền**. **Token hết hạn/bị revoke** là case khác, thường báo permission denied nhưng cách trả status có thể tùy endpoint/config/version. Test các trường hợp này riêng:

| Case | Fixture | Điều cần khẳng định |
| --- | --- | --- |
| Được phép | Token có read + secret tồn tại | Đọc được |
| Bị từ chối ACL | Token hợp lệ chỉ đọc path khác | **403**, không lộ secret |
| Token bị revoke | Token test đã được revoke | Không đọc được; phân loại auth/token lifecycle |
| Secret không tồn tại | Token hợp lệ có quyền trên đúng path được yêu cầu | Trả null/404 theo API, không nhầm với ACL |
| Sai namespace | Token/role thuộc namespace khác | Từ chối; kiểm tra cấu hình namespace |

Dùng một token thiếu quyền để chứng minh lỗi ACL, không dùng một chuỗi token giả vì khi đó test chủ yếu kiểm tra authentication.

## 6. Kiểm thử TLS: từ chối CA không tin cậy

TLS có hai bước liên quan nhưng khác nhau: xác minh **chuỗi chứng thư CA** và xác minh **hostname/IP trong SAN**. Một client có thể tin CA nhưng vẫn phải từ chối chứng thư có SAN không phù hợp với địa chỉ kết nối.

### 6.1 Chuẩn bị fixture HTTPS độc lập

Tạo **Vault test có TLS bật** và chứng thư máy chủ được ký bởi **CA thử nghiệm** không có trong truststore mặc định của JVM đang chạy test. Ví dụ:

~~~text
Test URL:     https://localhost:18200
Server cert:  SAN = DNS:localhost
Issuer:       Lab-CA (không nằm trong client truststore)
Expected:     TLS handshake fails before HTTP/ACL evaluation
~~~

CA thử nghiệm có thể được quản lý bằng openssl, một PKI fixture hoặc Vault PKI trong lab. Không cần lấy chứng thư từ hệ thống thật để tái hiện lỗi trust.

**Không đặt** các cấu hình như **VAULT_SKIP_VERIFY=true**, hostname verifier luôn true hoặc trust-all X509TrustManager để “sửa” ca kiểm thử. Làm như vậy sẽ vô hiệu hóa thuộc tính bảo mật mà test cần xác nhận.

### 6.2 JUnit test: CA không tin cậy

Đây là kiểm thử **lớp TLS trong JDK** dùng cùng endpoint mà Spring Vault có thể truy cập. Nó giúp phân biệt TLS failure với HTTP 403; khi áp dụng cho VaultTemplate, kiểm tra thêm wrapper exception thực tế của phiên bản Spring Vault.

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.catchThrowable;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import javax.net.ssl.SSLHandshakeException;

import org.junit.jupiter.api.Test;

class VaultTlsTrustIT {

    @Test
    void untrustedServerCertificateFailsBeforeHttp() {
        String url = System.getenv("TEST_VAULT_UNTRUSTED_TLS_URL");

        if (url == null || url.isBlank()) {
            throw new IllegalStateException("Thiếu TLS fixture URL");
        }

        HttpClient http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .build();

        HttpRequest request = HttpRequest.newBuilder(URI.create(url))
                .timeout(Duration.ofSeconds(3))
                .GET()
                .build();

        Throwable failure = catchThrowable(() ->
                http.send(request, HttpResponse.BodyHandlers.discarding()));

        assertThat(failure).isNotNull();
        assertThat(hasCause(failure, SSLHandshakeException.class)).isTrue();
    }

    static boolean hasCause(Throwable error, Class<?> expected) {
        for (Throwable current = error;
             current != null;
             current = current.getCause()) {
            if (expected.isInstance(current)) {
                return true;
            }
        }
        return false;
    }
}
~~~

Test này giả định **CA fixture cố tình không được tin cậy**. Nếu môi trường CI đã cài CA đó vào truststore toàn máy, test không còn đo đúng tình huống; cần tạo một test truststore riêng biệt, cô lập với cấu hình thật.

### 6.3 Kiểm tra hostname và SAN

Để kiểm tra riêng hostname verification, cần **tin cậy CA thử nghiệm** nhưng dùng tên kết nối không có trong SAN:

~~~text
Server cert SAN: DNS:vault.lab.internal
Client URL:      https://127.0.0.1:18200
Client trust:    đã trust Lab-CA
Expected:        hostname/IP verification thất bại
~~~

Chứng thư chỉ có **DNS:vault.lab.internal** không chứng minh server có danh tính **127.0.0.1**; trường hợp client kết nối bằng IP cần **IP SAN** tương ứng. Đừng coi việc Subject CN chứa tên gần giống là đủ để xác minh hostname.

Kiểm tra ba trường hợp đối chứng:

1. **CA đúng + hostname đúng**: TLS bắt tay thành công, sau đó mới xét status HTTP và ACL.
2. **CA sai + hostname đúng**: handshake thất bại vì chain không tin cậy.
3. **CA đúng + hostname sai**: handshake/hostname verification thất bại vì SAN không khớp.

Với mTLS, bổ sung ca **client certificate hợp lệ**, **không có client certificate** và **client certificate không được server tin cậy**. Lỗi mTLS thường xảy ra trước khi request đến endpoint Vault; không suy ra nó là lỗi ACL **403**.

## 7. Kiểm thử mất kết nối: connection refused

Khi client kết nối tới một port không có listener, hệ điều hành có thể trả **connection refused**. Đây là lỗi mạng, khác với HTTP 403 hoặc 404.

Ví dụ JUnit tạo một port tạm thời rồi đóng listener trước khi thử gọi VaultTemplate:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.catchThrowable;

import java.net.ConnectException;
import java.net.InetAddress;
import java.net.ServerSocket;

import org.junit.jupiter.api.Test;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;

class VaultConnectionRefusedIT {

    @Test
    void unreachableTcpEndpointFailsWithoutHttpResponse()
            throws Exception {

        int port;
        try (ServerSocket reservation = new ServerSocket(
                0, 1, InetAddress.getByName("127.0.0.1"))) {
            port = reservation.getLocalPort();
        }

        String url = "http://127.0.0.1:" + port;

        VaultTemplate vault = new VaultTemplate(
                VaultEndpoint.from(url),
                new TokenAuthentication("non-secret-test-token"));

        Throwable failure = catchThrowable(
                () -> vault.read("kv-test/data/app/config"));

        assertThat(failure).isNotNull();
        assertThat(hasCause(failure, ConnectException.class)).isTrue();
    }

    private static boolean hasCause(Throwable error, Class<?> expected) {
        for (Throwable current = error;
             current != null;
             current = current.getCause()) {
            if (expected.isInstance(current)) {
                return true;
            }
        }
        return false;
    }
}
~~~

Test này **không cần Vault thật**, vì lỗi xảy ra trước khi Vault có thể nhận request. Port được hệ điều hành cấp rồi đóng có một race condition nhỏ: tiến trình khác có thể chiếm port trước request. Trong CI cần test ổn định tuyệt đối, ưu tiên proxy/network fixture quản lý listener và trạng thái ngắt kết nối có kiểm soát.

**Không kết luận “Vault trả 503” từ connection refused.** Connection refused không có HTTP response. Việc phân loại đúng giúp quan sát lỗi mạng khác với Vault server error.

## 8. Kiểm thử read timeout bằng local HTTP fixture

Timeout khác connection refused. Với read timeout, TCP connection **đã được thiết lập**, request có thể đã tới server nhưng client **không nhận phản hồi trong thời hạn**.

JUnit 5 có thể dùng **JDK HttpServer** làm một server giả cố tình không trả response trong lúc client chờ. Đoạn mã dưới đây không cần Vault thật và không ghi thêm file trong repository.

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.time.Duration;
import java.util.concurrent.CountDownLatch;

import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;

class HttpReadTimeoutTest {

    @Test
    void timesOutWhenServerAcceptsButDoesNotRespond()
            throws Exception {

        CountDownLatch release = new CountDownLatch(1);
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0),
                0);

        server.createContext("/v1/kv-test/data/app/config", exchange -> {
            try {
                release.await(); // Cố tình chặn response, chỉ trong test.
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            } finally {
                exchange.close();
            }
        });

        server.start();
        try {
            URI target = URI.create(
                    "http://127.0.0.1:" + server.getAddress().getPort()
                            + "/v1/kv-test/data/app/config");

            HttpClient http = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(1))
                    .build();

            HttpRequest request = HttpRequest.newBuilder(target)
                    .timeout(Duration.ofMillis(250))
                    .GET()
                    .build();

            assertThrows(HttpTimeoutException.class, () ->
                    http.send(
                            request,
                            HttpResponse.BodyHandlers.discarding()));
        } finally {
            release.countDown();
            server.stop(0);
        }
    }
}
~~~

**Giải thích:** server đã nhận kết nối nhưng chưa trả HTTP headers; JDK client hết request timeout và ném **HttpTimeoutException**. Với Spring Vault, HTTP client có thể bọc **SocketTimeoutException/HttpTimeoutException** trong exception khác; vì thế test Spring Vault riêng phải kiểm tra **cause chain** và timeout configuration của HTTP adapter tương ứng.

Đoạn test dùng module **jdk.httpserver** thuộc JDK. Nếu build/test runtime không bật module này theo mặc định, cần cấu hình module trong test JVM hoặc dùng MockWebServer/WireMock.

### Connect timeout và read timeout không giống nhau

| Timeout | Xảy ra ở bước | Dấu hiệu |
| --- | --- | --- |
| **Connect timeout** | Không thiết lập được TCP connection trong thời hạn | ConnectTimeoutException hoặc lỗi I/O tương đương |
| **TLS handshake timeout** | TCP đã kết nối nhưng quá trình TLS chưa hoàn thành | Exception từ TLS hoặc network client |
| **Read/request timeout** | Gửi request nhưng không nhận response đúng hạn | SocketTimeoutException/HttpTimeoutException |
| **Overall deadline** | Tổng thời gian gồm queue, retry, kết nối và xử lý | Do tầng nghiệp vụ/caller quản lý |

Ví dụ Spring Cloud Vault có cấu hình connect/read timeout tùy phiên bản; cần kiểm tra tài liệu bản đang dùng và xác minh bằng test thay vì để giá trị mặc định vô hạn. Một **retry policy** với ba lần gọi và timeout riêng mỗi lần có thể khiến deadline người dùng bị vượt quá nếu không tính tổng.

## 9. Connection reset: trường hợp khó của idempotency

**Connection reset** có thể xảy ra sau khi Vault đã **nhận và xử lý** request nhưng response chưa tới client. Lúc này client chỉ thấy socket bị đóng bất thường, không biết thao tác có hoàn thành hay chưa.

Ví dụ mô phỏng trong môi trường có proxy:

~~~text
orders-api → test proxy → Vault
             |
             +-- test proxy chủ động reset kết nối
                 sau khi chuyển request đến Vault
~~~

Đối với **KV v2 GET một giá trị**, việc retry có thể hợp lý nếu đã xác nhận operation là đọc thuần túy, có maxAttempts, timeout và backoff. Nhưng với **database/creds/role**, lời gọi đọc có thể cấp một dynamic credential mới. Với **PKI issue**, Vault có thể đã phát hành chứng thư trước khi client bị reset. Với **unwrap**, wrapping token có thể đã bị tiêu thụ.

| Operation | Retry sau reset? |
| --- | --- |
| KV v2 GET giá trị | Có điều kiện, giới hạn số lần và deadline |
| Đọc metadata không gây side effect | Có điều kiện |
| Cấp database credential | Không retry mù vì có thể phát hành lease mới |
| PKI issue | Không retry mù vì có thể cấp chứng thư khác |
| Token creation | Không retry mù vì có thể sinh token mới |
| Response wrapping unwrap | Không retry mù vì token chỉ dùng một lần |
| Lease renew/revoke | Chính sách riêng theo semantics, audit và idempotency |

**Tuyệt đối không viết test “mất kết nối thì retry mọi VaultOperations.read”**. Tên phương thức **read** không bảo đảm endpoint không có tác dụng phụ.

Toxiproxy hoặc HTTP/TCP proxy test có thể mô phỏng **reset, latency, packet cut, server unavailable**. Dùng địa chỉ proxy từ **test client** và khôi phục trạng thái proxy trong cleanup, không thay đổi route production.

## 10. Phân loại lỗi trong Java mà không nuốt nguyên nhân

Ứng dụng cần một bước phân loại tập trung thay vì catch mọi exception rồi trả “Vault unavailable”. Logic nên ưu tiên lỗi TLS và HTTP rõ ràng, sau đó mới xét lỗi mạng trong cause chain.

Ví dụ thuật toán minh họa:

~~~java
public enum VaultFailureKind {
    FORBIDDEN,
    NOT_FOUND,
    AUTHENTICATION,
    TLS,
    CONNECTIVITY,
    SERVER_UNAVAILABLE,
    OTHER
}
~~~

Quy tắc ứng dụng nên xác định:

- Nếu nhận **403 từ Vault**, kiểm tra token, policy, namespace và path. Không chuyển sang token quản trị.
- Nếu TLS certificate validation thất bại, **fail closed**; không tự động trust-all hoặc chuyển sang HTTP.
- Nếu kết nối tạm thời thất bại trên **KV GET**, có thể retry theo chính sách có giới hạn.
- Nếu secret không tồn tại, phân biệt null/404 với 403 và không tạo giá trị mặc định chứa credential giả.
- Nếu request tạo tài nguyên hoặc sử dụng token một lần, không retry khi kết quả còn mơ hồ.
- Khi exception bị wrapper, giữ **cause chain** để phân loại; không log raw response chứa secret.

Một helper đơn giản để kiểm tra cause chain trong test:

~~~java
public static boolean hasCause(
        Throwable failure, Class<? extends Throwable> type) {

    for (Throwable current = failure;
         current != null;
         current = current.getCause()) {

        if (type.isInstance(current)) {
            return true;
        }
    }
    return false;
}
~~~

Với Spring Vault phiên bản khác nhau, exception HTTP có thể được bọc khác nhau. Không parse thông báo lỗi bằng cách tìm chuỗi **"403"** rồi coi là hợp đồng ổn định duy nhất. Với phiên bản Spring Vault có exception chứa HTTP status cụ thể, dùng status đó; khi cần chứng minh ACL ở integration test, kiểm tra trực tiếp HTTP status trên cùng fixture.

### Giới hạn retry và backoff

Ví dụ chính sách **chỉ cho KV GET**:

~~~text
maxAttempts = 3       # Tổng: 1 lần gọi đầu + tối đa 2 retry
connectTimeout = 1s
readTimeout = 2s
backoff = 150ms, 300ms (có jitter)
overallDeadline = theo ngân sách của request nghiệp vụ

403/TLS failure/404: dừng ngay
connect reset/timeout/5xx tạm thời: có thể retry có giới hạn
~~~

Không đặt retry ở nhiều tầng vô tình nhân thành **3 × 3 × 3 = 27 request**. Cần có giới hạn concurrency và circuit breaker khi Vault thực sự không khả dụng.

## 11. Kiểm thử hệ thống khôi phục như thế nào?

Phát hiện exception đúng mới là một phần. Hành vi sau lỗi còn phải phù hợp với loại secret và tầm quan trọng của workload.

### Startup phụ thuộc KV configuration

Nếu secret là bắt buộc để ứng dụng hoạt động, sau khi hết attempts có thể **fail startup** và để orchestration xử lý restart/readiness theo chính sách. Không âm thầm dùng cấu hình không an toàn hoặc token mặc định.

### Request trực tuyến dùng Transit

Nếu Vault mất kết nối khi ứng dụng cần mã hóa, nên trả lỗi có kiểm soát hoặc đưa công việc vào queue an toàn theo thiết kế; không ghi plaintext thay vì ciphertext chỉ để giữ HTTP 200.

### Dynamic credential và lease

Nếu lấy database credential thất bại sau timeout, không chắc Vault chưa cấp lease. Cần quan sát audit/lease lifecycle và chính sách cấp lại riêng. Đừng kéo dài một credential đã hết hạn bằng cách làm mới cache.

### TLS

Nếu lỗi trust hoặc SAN, ứng dụng **không được hạ cấp từ HTTPS xuống HTTP**, không tắt hostname verification và không tự thêm mọi CA vào truststore. Cập nhật đúng CA bundle, certificate hoặc địa chỉ kết nối qua quy trình cấu hình tin cậy.

### Token/ACL

Nếu workload token thiếu quyền, cần sửa **Vault policy và auth role** qua đường vận hành được phê duyệt. Test nên xác nhận ứng dụng **không tự nâng quyền**, không lấy root token và không retry 403 vô tận.

## 12. Ma trận kiểm thử hoàn chỉnh

| ID | Fixture | Hành động | Kết quả cần khẳng định |
| --- | --- | --- | --- |
| AUTH-01 | Token có read, secret tồn tại | KV v2 GET | Thành công, đúng giá trị demo |
| AUTH-02 | Token hợp lệ không có read | KV v2 GET | HTTP 403, không trả secret |
| AUTH-03 | Token đã revoke/expired | KV v2 GET | Bị từ chối; lỗi auth/tokens được phân loại |
| AUTH-04 | Secret path thiếu, token có quyền trên path | KV v2 GET | Null/404, không nhầm với 403 |
| AUTH-05 | Namespace sai | KV v2 GET | Bị từ chối hoặc path không có; kiểm tra namespace |
| TLS-01 | CA được trust, hostname đúng | HTTPS tới Vault | TLS OK, tiếp tục kiểm tra HTTP |
| TLS-02 | CA không được trust | HTTPS tới Vault | SSLHandshakeException, không có HTTP response |
| TLS-03 | CA được trust, SAN không khớp host | HTTPS tới Vault | Hostname verification thất bại |
| TLS-04 | Server yêu cầu mTLS, không có client cert | HTTPS tới Vault | Handshake bị từ chối |
| TLS-05 | Chứng thư server hết hạn | HTTPS tới Vault | Certificate validation thất bại |
| NET-01 | Port không có listener | VaultTemplate.read | Connection refused, không có status HTTP |
| NET-02 | TCP đã nhận, không có response | GET qua slow fixture | Read/request timeout đúng budget |
| NET-03 | Proxy reset sau khi chuyển request | GET qua proxy | Lỗi I/O và retry theo semantics |
| NET-04 | DNS không tồn tại | Kết nối tới hostname test | UnknownHost và phân loại config/network |
| NET-05 | Vault tạm thời 503 | KV GET | Retry giới hạn khi phù hợp; không vô hạn |
| NET-06 | Proxy khôi phục sau lỗi đầu tiên | KV GET | Khôi phục trong budget, đếm đúng attempts |
| SAFE-01 | Bất kỳ lỗi nào | Kiểm tra log/trace | Không có token, private key, plaintext secret |
| SAFE-02 | Lỗi 403 | Theo dõi retry/ACL | Không retry cùng token, không fallback quyền cao |
| SAFE-03 | TLS không hợp lệ | Kiểm tra cấu hình client | Không trust-all hoặc bỏ qua hostname |

### Tránh test giả thành công

Một bài test lỗi cần có **đối chứng thành công**:

- Trước khi thử 403, dùng token có quyền để xác nhận server/secret đang hoạt động.
- Trước khi thử CA sai, dùng client tin đúng CA để xác nhận server có thể bắt tay TLS.
- Trước khi thử hostname sai, đảm bảo CA đã được trust và server thực sự phục vụ chứng thư dự kiến.
- Trước khi thử timeout, xác minh server giả đã lắng nghe và client đã kết nối.
- Trước khi thử connection reset, xác minh proxy đã chuyển request đúng endpoint.

Nếu không có đối chứng, lỗi port sai có thể bị báo nhầm thành lỗi permission; lỗi trust có thể bị báo nhầm thành lỗi server không phản hồi.

## 13. Quan sát và bằng chứng kiểm thử

Các metric và thông tin log gợi ý:

| Thông tin | Ý nghĩa |
| --- | --- |
| **operation** | KV read, Transit encrypt, PKI issue; tránh log path nhạy cảm |
| **outcome** | success, forbidden, tls_error, connect_error, timeout, server_error |
| **http_status** | Chỉ có khi thực sự nhận HTTP response |
| **duration** | Thời gian từng attempt và tổng thời gian logic |
| **attempt_count** | Số lần gọi thực tế, tối đa theo chính sách |
| **client_identity** | Tên workload/role logic, không phải token |
| **correlation_id** | Liên kết request, trace và sự kiện Vault audit |
| **tls_peer_identity** | Hostname được cấu hình, không ghi private key |
| **health_state** | initialized, sealed, standby theo nguồn health phù hợp |

Ví dụ log không nhạy cảm:

~~~text
service=orders-api operation=kv-read result=forbidden status=403 attempts=1
service=orders-api operation=kv-read result=tls_error attempts=1
service=orders-api operation=kv-read result=connect_timeout attempts=3
~~~

Không đưa **X-Vault-Token**, SecretID, private key, response JSON chứa secret hoặc nội dung exception có giá trị nhạy cảm vào log. Khi debug TLS, có thể quan sát thông tin certificate chain/test CA đã được phép, nhưng tuyệt đối không phát tán key material của CA hay workload.

Kiểm tra audit log ở Vault test để đối chiếu request **đã tới Vault** hay chưa. Với handshake thất bại hoặc connection refused, request HTTP có thể chưa đi đến tầng Vault xử lý ACL, nên việc không thấy audit record là phù hợp. Ngược lại, request 403 do ACL thường đã qua kết nối TLS và vào lớp authorization.

## 14. Checklist vận hành kiểm thử trong CI

1. Dùng **Vault test riêng**, không chạy fault injection trên cluster production/shared staging.
2. Thiết lập **KV v2**, fake secret, policy read và policy denied; cấp token TTL ngắn qua cơ chế bảo vệ của CI.
3. Chạy **success control** trước mỗi ca lỗi; phân biệt 403 thực với TLS/timeout.
4. Dùng **TLS CA test riêng** để tạo trust failure, hostname mismatch, expired certificate và mTLS failure.
5. Dùng **local server hoặc proxy** để tái hiện connection refused, read timeout và reset mà không tác động Vault thật.
6. Cấu hình connect/read timeout và overall deadline; xác nhận số lượt retry hữu hạn.
7. Kiểm tra **cause chain**, HTTP status cụ thể khi có response và kết quả nghiệp vụ; không chỉ assert mọi exception.
8. Giới hạn test ở các operation an toàn; không retry mù PKI issue, dynamic credential issuance hay unwrap.
9. Kiểm tra log và metric không làm lộ bí mật; dọn token/fixture sau test.
10. Ghi rõ phiên bản Java, Spring Vault, Vault và cấu hình TLS để tái lập lỗi.

**Điểm cốt lõi:** khi kiểm thử **Spring Vault**, cần xác định request **bị Vault từ chối vì quyền**, **không qua được TLS** hay **không thể liên lạc với Vault**. Ba trường hợp có biểu hiện exception gần nhau nhưng hướng xử lý khác nhau. Test được thiết kế theo tầng, có đối chứng thành công và kiểm tra kết quả cụ thể sẽ giúp ứng dụng Java phục hồi đúng cách mà không làm suy yếu xác thực, ACL hoặc TLS.

## Tài liệu tham khảo chính thức

- [Spring Vault — VaultTemplate API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultTemplate.html).
- [Spring Vault — VaultEndpoint API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/client/VaultEndpoint.html).
- [Spring Vault — Authentication](https://docs.spring.io/spring-vault/reference/vault/authentication.html).
- [HashiCorp Vault — ACL Policies](https://developer.hashicorp.com/vault/docs/concepts/policies).
- [HashiCorp Vault — KV Secrets Engine HTTP API](https://developer.hashicorp.com/vault/api-docs/secret/kv/kv-v2).
- [HashiCorp Vault — Health API](https://developer.hashicorp.com/vault/api-docs/system/health).
- [Java — HttpClient API](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html).
- [JUnit 5 — User Guide](https://junit.org/junit5/docs/current/user-guide/).
