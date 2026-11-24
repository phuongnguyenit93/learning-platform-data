# HTTPS và cấu hình client trong môi trường kiểm thử

## Mục tiêu bài học

**Spring Cloud Contract** mô tả hành vi HTTP hoặc thông điệp bằng **Groovy DSL** và **YAML DSL**, sinh kiểm thử phía producer và đóng gói HTTP stubs để consumer dùng qua **Stub Runner**. Khi consumer kết nối qua **HTTPS**, kiểm tra response từ WireMock chỉ là một phần: client còn phải thiết lập **TLS**, xác minh chứng chỉ của server và kiểm tra hostname.

Chủ đề này thuộc chương **WireMock**. Ta sẽ tách rõ **hành vi HTTP được hợp đồng hóa** với **cấu hình bảo mật của kết nối**, để không nhầm việc một stub trả HTTP 200 với việc TLS đã được kiểm tra đúng.

Sau bài học, bạn có thể:

- Khởi tạo WireMock với HTTPS listener và xác định đúng port.
- Phân biệt **server keystore**, **client truststore**, **SAN** và hostname verification.
- Cấu hình Java HTTP client sử dụng test truststore mà không tắt xác thực TLS.
- Định hướng cấu hình HTTPS cho RestTemplate, RestClient, WebClient và Feign.
- Giải thích sự khác nhau giữa **WireMockServer tự chạy** và **WireMock bên trong Stub Runner**.
- Viết kiểm thử dương/âm, xử lý mTLS, hostname container, CI và các lỗi kết nối.

## 1. TLS diễn ra trước HTTP matcher

Một lời gọi:

~~~text
https://localhost:8443/api/orders/ORD-1001
~~~

phải hoàn tất quá trình TLS handshake trước khi HTTP request đến WireMock matcher.

~~~mermaid
sequenceDiagram
    participant C as Consumer HTTP client
    participant S as WireMock TLS listener
    participant W as WireMock matcher
    C->>S: TLS ClientHello
    S-->>C: Server certificate
    C->>C: Xác minh chain + trust + hostname
    alt TLS hợp lệ
        C->>W: GET /api/orders/ORD-1001
        W->>W: So khớp method/path/header
        W-->>C: HTTP 200 + JSON
    else TLS không hợp lệ
        C--xS: Hủy handshake
    end
~~~

Ví dụ hợp đồng HTTP Spring Cloud Contract:

~~~yaml
description: "Lấy đơn hàng đã thanh toán"
name: get_paid_order
request:
  method: GET
  url: /api/orders/ORD-1001
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: ORD-1001
    status: PAID
~~~

Hợp đồng mô tả **HTTP method, path, header, status và body**. Nó không tự tạo HTTPS certificate và không tự yêu cầu Stub Runner mở HTTPS listener. Cùng một mapping có thể dùng trên HTTP hoặc HTTPS nếu server được cấu hình phù hợp.

| Phần kiểm thử | Ví dụ | Bằng chứng cần có |
| --- | --- | --- |
| TLS identity | Chứng chỉ được tin cậy, SAN khớp hostname | HTTPS client integration test |
| Kết nối HTTPS | Đúng host, port, protocol | Client thực sự handshake thành công |
| HTTP contract | GET đúng path trả 200, JSON như hợp đồng | Producer contract tests và WireMock stub tests |
| Consumer behavior | Checkout xử lý `PAID` đúng | Consumer integration assertions |
| Cấu hình production | TLS tại ingress, renew, cipher policy | Test triển khai và kiểm tra bảo mật riêng |

**HTTP contract test PASS không tự chứng minh HTTPS được cấu hình đúng.** Ngược lại, TLS handshake thành công cũng không chứng minh URL hoặc JSON response tương thích.

## 2. Chạy WireMock bằng HTTPS

WireMock Java API hỗ trợ HTTPS port. Với test tự quản lý `WireMockServer`, dùng port động để tránh va chạm khi chạy song song.

~~~java
import com.github.tomakehurst.wiremock.WireMockServer;

import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;
import static com.github.tomakehurst.wiremock.client.WireMock.*;

WireMockServer stub = new WireMockServer(
    wireMockConfig().dynamicPort().dynamicHttpsPort()
);

stub.start();
try {
    stub.stubFor(get(urlEqualTo("/api/orders/ORD-1001"))
        .willReturn(aResponse()
            .withStatus(200)
            .withHeader("Content-Type", "application/json")
            .withBody("{\"id\":\"ORD-1001\",\"status\":\"PAID\"}")));

    String httpsBaseUrl =
        "https://localhost:" + stub.httpsPort();

    // Dùng một HTTP client có TLS truststore phù hợp
    // để gọi httpsBaseUrl.
} finally {
    stub.stop();
}
~~~

Đây là **WireMock Java DSL**, khác với Spring Cloud Contract Groovy DSL. API cụ thể cần phù hợp với phiên bản WireMock mà dự án đang sử dụng.

### Port HTTP và port HTTPS là hai giá trị khác nhau

| Giá trị | Ý nghĩa |
| --- | --- |
| `stub.port()` | HTTP port (nếu listener HTTP được bật) |
| `stub.httpsPort()` | HTTPS port |
| `http://localhost:<httpPort>` | Kết nối HTTP, không có TLS |
| `https://localhost:<httpsPort>` | Kết nối HTTPS có TLS handshake |

Đoạn trên bật **cả HTTP lẫn HTTPS** với hai cổng động. Bật HTTPS không có nghĩa HTTP tự động bị tắt. Nếu yêu cầu chỉ phục vụ HTTPS, cần kiểm tra tùy chọn vô hiệu hóa HTTP của đúng phiên bản và xác minh trong test.

**Đừng dùng `stub.port()` rồi chỉ đổi chuỗi `http` thành `https`.** Một kết nối TLS gửi vào cổng HTTP có thể bị từ chối trước khi HTTP matcher chạy.

## 3. Certificate, keystore, truststore và SAN

Khi WireMock làm HTTPS server, nó cần **private key** và **certificate**. Client phải tin certificate hoặc CA phù hợp, và hostname trong URL phải được phép bởi certificate.

| Thành phần | Thuộc về | Nội dung/chức năng |
| --- | --- | --- |
| **Server keystore** | WireMock | Private key và certificate chain của server |
| **Client truststore** | Consumer test | CA/certificate được phép dùng để tin server |
| **Subject Alternative Name (SAN)** | Server certificate | DNS hostname hoặc IP address hợp lệ |
| **Client keystore** | Consumer (khi dùng mTLS) | Private key và certificate của client |
| **Server truststore** | WireMock (khi dùng mTLS) | CA/certificate dùng để tin client |

Ví dụ test gọi `https://localhost` thì certificate nên có `DNS:localhost`. Nếu test gọi `https://127.0.0.1` thì certificate cần có `IP:127.0.0.1`. Một certificate có `CN=localhost` nhưng không có SAN phù hợp **không nên được coi là đủ** cho hostname verification hiện đại.

Trong một số cách cấu hình, WireMock có thể sử dụng chứng chỉ thử nghiệm mặc định. Không nên giả định chứng chỉ đó được JVM tin cậy hoặc có SAN khớp URL của test. Hãy kiểm tra certificate thực tế và thiết lập trust material cụ thể.

### Self-signed certificate có dùng được không?

**Có**, nếu client test cố ý tin certificate thử nghiệm đó và vẫn kiểm tra hostname. Một certificate self-signed không tự động được tin; client cần truststore chứa certificate hoặc trust anchor tương ứng.

Cách làm nên theo thứ tự:

1. Tạo certificate riêng cho môi trường test với SAN đúng.
2. Đặt private key và certificate vào server keystore.
3. Xuất public certificate/CA, đưa vào client truststore.
4. Cấu hình **HTTP client dùng trong test** tin truststore này.
5. Kiểm tra hostname verification được bật.
6. Thử thêm một certificate hoặc hostname sai để bảo đảm kết nối bị từ chối.

## 4. Tạo test keystore và truststore bằng keytool

Các lệnh sau là **ví dụ dành cho shell kiểu POSIX**. Trên PowerShell, dùng một dòng mỗi lệnh hoặc cú pháp xuống dòng thích hợp. Không cần chạy chúng trong quá trình đọc bài.

~~~bash
# 1. Server keypair/certificate chỉ dành cho test.
keytool -genkeypair -alias wiremock-local \
  -keyalg RSA -keysize 2048 -validity 30 \
  -storetype JKS -keystore wiremock-server.jks \
  -storepass test-only -keypass test-only \
  -dname "CN=localhost" \
  -ext "SAN=dns:localhost,ip:127.0.0.1"

# 2. Chỉ xuất public certificate, không xuất private key.
keytool -exportcert -rfc -alias wiremock-local \
  -keystore wiremock-server.jks -storepass test-only \
  -file wiremock-local.crt

# 3. Client truststore tin certificate thử nghiệm.
keytool -importcert -noprompt -alias wiremock-local \
  -file wiremock-local.crt -storetype PKCS12 \
  -keystore wiremock-client-trust.p12 \
  -storepass trust-test-only
~~~

`test-only` và `trust-test-only` chỉ là mật khẩu **minh họa**, không dành cho production. Server JKS chứa private key phải được bảo vệ; không sao chép private key production vào fixture hoặc repository. Với chính sách nghiêm ngặt, có thể tạo bộ chứng chỉ test trong CI, giới hạn thời gian sống và dọn sau khi chạy.

Trong các phiên bản WireMock hỗ trợ, cấu hình keystore có thể thực hiện như sau:

~~~java
WireMockServer stub = new WireMockServer(
    wireMockConfig()
        .dynamicPort()
        .dynamicHttpsPort()
        .keystorePath("src/test/resources/tls/wiremock-server.jks")
        .keystorePassword("test-only")
);
~~~

Đường dẫn phải trỏ đúng JKS đã tạo. Tùy phiên bản, các tùy chọn cho loại keystore, private key password và TLS listener có thể khác; cần xem log startup và API thực tế của WireMock. **Không sửa lỗi certificate bằng cách tắt hostname verification.**

## 5. Dùng SSLContext cho Java 11+ HttpClient

Một chiến lược rõ ràng là dùng `SSLContext` được cấu hình **riêng cho HTTP client của test**, tránh sửa truststore toàn JVM và làm ảnh hưởng các test khác.

~~~java
import java.io.InputStream;
import java.net.http.HttpClient;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public final class TestHttpsClientFactory {

    public static HttpClient create(Path truststoreFile,
                                    char[] password) throws Exception {
        KeyStore trustStore = KeyStore.getInstance("PKCS12");

        try (InputStream input =
                 Files.newInputStream(truststoreFile)) {
            trustStore.load(input, password);
        }

        TrustManagerFactory trustManagers =
            TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm()
            );
        trustManagers.init(trustStore);

        SSLContext tlsContext = SSLContext.getInstance("TLS");
        tlsContext.init(
            null,
            trustManagers.getTrustManagers(),
            new SecureRandom()
        );

        return HttpClient.newBuilder()
            .sslContext(tlsContext)
            .build();
    }
}
~~~

Ví dụ gửi HTTP request qua HTTPS tới WireMock:

~~~java
import java.net.URI;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Path;

var client = TestHttpsClientFactory.create(
    Path.of("src/test/resources/tls/wiremock-client-trust.p12"),
    "trust-test-only".toCharArray()
);

var request = HttpRequest.newBuilder()
    .uri(URI.create("https://localhost:" + stub.httpsPort()
        + "/api/orders/ORD-1001"))
    .header("Accept", "application/json")
    .GET()
    .build();

HttpResponse<String> response = client.send(
    request, HttpResponse.BodyHandlers.ofString()
);

if (response.statusCode() != 200 ||
    !response.body().contains("\"PAID\"")) {
    throw new AssertionError("Response HTTPS không đúng kịch bản");
}
~~~

Để có consumer assertions vững, nên parse JSON và kiểm tra `$.id`, `$.status` thay vì `contains`. Ví dụ chỉ nhấn mạnh cấu hình client TLS.

**Truststore này chỉ định những certificate được tin cậy; không phải “trust all”.** Cần bảo đảm hostname verification được giữ hoạt động và có kiểm tra âm tính trong môi trường HTTP client thực.

## 6. Không dùng trust-all hay bỏ qua hostname verification

Trên Internet thường có ví dụ dùng `TrustManager` chấp nhận tất cả certificate hoặc cấu hình “relaxed HTTPS validation” để test qua self-signed certificate.

Cách đó khiến bài kiểm thử HTTPS mất ý nghĩa:

- Chấp nhận certificate giả, hết hạn hoặc ngoài trust policy.
- Che khuất trường hợp hostname không khớp SAN.
- Không xác minh truststore của consumer đã được cấu hình đúng.
- Dễ bị sao chép sang staging/production.
- Có thể khiến CI xanh ngay cả khi kết nối TLS thực tế sẽ thất bại.

**Cách đúng:** sử dụng một CA hoặc certificate test xác định, đưa vào truststore của đúng HTTP client, giữ hostname verification và thêm test thất bại khi trust/hostname sai.

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Đúng test certificate + `localhost` có trong SAN | TLS thành công |
| Truststore không tin certificate/CA của server | TLS handshake thất bại |
| URL host không có trong SAN | Hostname verification từ chối |
| Client HTTPS nối vào cổng HTTP | Lỗi protocol/TLS trước HTTP matching |
| TLS đúng nhưng URL path sai | HTTP request không match stub |
| Trust-all vô tình được bật | Test âm tính có thể lộ lỗi vì vẫn kết nối được |

Không cần bật một hệ thống PKI production đầy đủ để kiểm thử WireMock. Nhưng phải **giữ nguyên nguyên tắc xác minh danh tính**.

## 7. RestTemplate, RestClient, WebClient và Feign

Không có một property Spring Cloud Contract chung tự cấu hình TLS cho mọi HTTP client. Cần xác định **HTTP transport** mà consumer đang thực sự dùng.

| HTTP client | Nơi cần cung cấp TLS trust material |
| --- | --- |
| Java `HttpClient` | `SSLContext` của instance |
| `RestTemplate` | `ClientHttpRequestFactory` / HTTP transport thực |
| Spring `RestClient` | Request factory hoặc client builder |
| Spring `WebClient` | `ClientHttpConnector` / Reactor Netty SSL context |
| OpenFeign | HTTP client implementation/transport do Feign sử dụng |
| Client có discovery | Thêm scheme, URI, secure flag và port của `ServiceInstance` |

Chỉ thay một cấu hình:
 
~~~yaml
orders:
  base-url: "https://localhost:8443"
~~~

**chưa đủ** nếu client chưa tin certificate. Ngược lại, việc thiết lập truststore cho Java `HttpClient` không tự thay đổi cấu hình của WebClient hoặc Feign nếu chúng dùng transport khác.

### WebClient / Reactor Netty

Với Spring WebFlux, có thể sử dụng một test CA/certificate PEM khi tạo `SslContext` cho Reactor Netty:

~~~java
import io.netty.handler.ssl.SslContext;
import io.netty.handler.ssl.SslContextBuilder;
import java.io.File;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

File certFile = new File(
    "src/test/resources/tls/wiremock-local.crt"
);

SslContext testSsl = SslContextBuilder.forClient()
    .trustManager(certFile)
    .build();

HttpClient nettyClient = HttpClient.create()
    .secure(spec -> spec.sslContext(testSsl));

WebClient client = WebClient.builder()
    .clientConnector(new ReactorClientHttpConnector(nettyClient))
    .baseUrl("https://localhost:" + stub.httpsPort())
    .build();
~~~

Đây là khung cấu hình client; cần có dependencies, lifecycle và xử lý lỗi phù hợp dự án. Với phiên bản Reactor Netty đang dùng, **xác minh hostname verification thực sự được bật khi dùng SSL context tùy chỉnh**; một số cách tạo SSL handler cần bật nó một cách tường minh. Chỉ dùng `trustManager(certFile)` không chứng minh hostname đã được kiểm tra.

### RestTemplate và RestClient

Các client này thường dùng `ClientHttpRequestFactory`. HTTPS truststore cần được cung cấp cho **HTTP library nằm sau request factory**, ví dụ Apache HttpClient, JDK transport hoặc thư viện khác.

API khác nhau giữa Apache HttpClient 4 và 5, và giữa các bản Spring Boot. Hãy lấy đúng version trong dự án để cấu hình; đừng copy một “SSL socket factory” từ dependency khác mà không kiểm tra.

### Feign và service discovery

Với `@FeignClient(name = "orders-api")`, client có thể dùng Spring Cloud LoadBalancer để chọn server. Ngoài TLS truststore, cần xác minh:

1. Service ID `orders-api` trỏ tới stub instance phù hợp.
2. Instance có **HTTPS scheme/HTTPS port** và metadata an toàn nếu client cần.
3. Feign thực sự dùng transport đã cấu hình certificate trust.
4. Không fallback âm thầm sang dịch vụ staging/production.

Nếu Feign được cấu hình **URL tĩnh**, test có thể bỏ qua service discovery. Điều đó có thể hữu ích cho HTTPS test riêng, nhưng không nên tuyên bố đã kiểm chứng discovery trong trường hợp đó.

## 8. Cổng động, CI và hostname trong container

Với `dynamicHttpsPort()`, WireMock sử dụng HTTPS port do hệ điều hành cấp. Không hardcode `8443` trong consumer test; lấy port từ WireMock và truyền vào cấu hình client.

~~~text
WireMockServer.start()
    |
    +--> WireMockServer.httpsPort()
    |
    +--> https://localhost:<httpsPort>
    |
    +--> HTTP client được cấu hình truststore
    |
    +--> Consumer assertions
    |
    +--> WireMockServer.stop()
~~~

Trong Spring Boot integration tests, có thể đăng ký URL động qua `@DynamicPropertySource`, miễn là server đã khởi động trước khi Spring đọc property:

~~~java
// Phác thảo: "stub" là WireMockServer đã khởi động
// và được quản lý lifecycle trong test class.
@DynamicPropertySource
static void register(DynamicPropertyRegistry registry) {
    registry.add("orders.base-url",
        () -> "https://localhost:" + stub.httpsPort());
}
~~~

**Chú ý container:** `localhost` trong một container consumer không phải container WireMock. Nếu URL thật là `https://wiremock:8443` thì certificate cần có `DNS:wiremock` trong SAN. Không tắt hostname verification để chạy được trong Docker; sửa certificate và DNS/network test cho phù hợp.

Một cách làm có thể tái lập là chọn host test có thể phân giải, tạo certificate với SAN chứa host đó, để CI cung cấp đúng đường dẫn truststore và dùng port động khi chạy chung host.

## 9. WireMockServer riêng khác với WireMock trong Stub Runner

Trong Spring Cloud Contract, các HTTP stubs thường được đóng gói theo tọa độ artifact, rồi **Stub Runner** tạo stub server. Tuy nhiên:

| Cách chạy | Người quản lý server | Vấn đề TLS |
| --- | --- | --- |
| `new WireMockServer(...)` trong JUnit | Test code | Có thể tự bật HTTPS listener, chọn keystore và port |
| WireMock JUnit extension | Extension | Cấu hình TLS qua options tương ứng |
| Spring Cloud Contract **Stub Runner** | Stub Runner | TLS phụ thuộc hỗ trợ và cấu hình của version Stub Runner/WireMock |
| WireMock sau một TLS proxy test | Proxy + test infrastructure | TLS được kiểm tra ở kết nối consumer–proxy, upstream có thể là HTTP |

Ví dụ Stub Runner ID:

~~~java
@AutoConfigureStubRunner(
    ids = "com.example.orders:order-service:1.4.2:stubs:8090",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
~~~

ID ở đây chỉ **stub artifact và port theo cú pháp Stub Runner**. Nó **không tự bảo đảm** server trên 8090 dùng HTTPS.

Không nên tự đoán property `spring.cloud.contract.stubrunner.https.enabled` hoặc tương tự nếu chưa kiểm tra phiên bản plugin đang dùng có hỗ trợ hay không. Đổi `http://localhost:8090` thành `https://localhost:8090` trong cấu hình consumer **không biến HTTP listener thành HTTPS**.

### Khi phiên bản Stub Runner không hỗ trợ cách bật HTTPS cần thiết

Có thể tách thành các phép thử:

1. **Producer contract tests** chứng minh producer đáp ứng các HTTP method/status/body đã mô tả.
2. **Consumer tests qua Stub Runner HTTP** kiểm tra logic consumer với đúng stub artifact.
3. **Consumer HTTPS test qua WireMockServer riêng** kiểm tra cấu hình TLS của HTTP client, sử dụng kịch bản HTTP tương ứng.
4. Nếu cần, **integration tests ở môi trường test thật** xác minh cấu hình ingress/proxy/mTLS.

Dùng một **TLS reverse proxy** trước WireMock HTTP cũng có thể là lựa chọn test, nhưng cần ghi rõ: handshake HTTPS kiểm tra proxy, **không chứng minh WireMock upstream dùng HTTPS**.

## 10. mTLS: xác minh cả hai chiều

HTTPS thông thường là server authentication: client tin certificate của server. Với **mutual TLS (mTLS)**, server còn yêu cầu client trình certificate.

~~~mermaid
flowchart LR
    A["Consumer"] -->|"Xác minh server cert + hostname"| B["WireMock HTTPS"]
    B -->|"Nếu mTLS: xác minh client cert"| A
    C["Client truststore"] --> A
    D["Server keystore"] --> B
    E["Client keystore (mTLS)"] --> A
    F["Server truststore (mTLS)"] --> B
~~~

Để có bằng chứng mTLS:

- WireMock server được cấu hình **bắt buộc** client authentication.
- Server truststore chứa CA/certificate dùng xác minh client.
- Client có private key và certificate test phù hợp.
- Client vẫn xác minh server certificate và hostname.
- Test **thiếu client cert**, cert sai hoặc chưa được tin cậy phải thất bại.

Với JDK `SSLContext`, mTLS thường cần thêm `KeyManagerFactory` từ client keystore để truyền key managers vào `init(...)`:

~~~java
// Phác thảo cho mTLS, không phải mã hoàn chỉnh:
// KeyManagerFactory kmf = ...; // từ client keystore test
// TrustManagerFactory tmf = ...; // tin server certificate
// tlsContext.init(kmf.getKeyManagers(),
//                 tmf.getTrustManagers(), new SecureRandom());
~~~

Một bài HTTPS test một chiều PASS **không chứng minh** mTLS đã được bật. Cấu hình bắt buộc client certificate của WireMock phải được xác minh với API của phiên bản đó.

## 11. Gỡ lỗi theo tầng

| Triệu chứng | Nơi kiểm tra trước | Nguyên nhân thường gặp |
| --- | --- | --- |
| `PKIX path building failed` | Truststore/chain | Client không tin certificate/CA |
| `No subject alternative names` | Certificate SAN | Host trong URL không khớp danh tính |
| `SSLHandshakeException` | TLS config | Trust, TLS version, cipher hoặc client auth |
| `NotSslRecordException`, `wrong version number` | Protocol/port | Gửi HTTPS tới cổng HTTP |
| `Connection refused` | Network/lifecycle | WireMock chưa chạy, sai port hoặc bind address |
| TLS thành công, HTTP 404 | WireMock mappings | Sai method, path, query, header hoặc body |
| Test gọi server staging | Discovery/base URL | Không dùng stub instance đúng |
| Local PASS, Docker CI FAIL | Hostname/DNS/SAN | `localhost` và hostname container khác nhau |
| Chỉ PASS với relaxed SSL | Bảo mật client | Đã tắt certificate/hostname verification |
| CI PASS với stub cũ | Artifact version | Chưa dùng stub được sinh từ producer build mới |

Quy trình chẩn đoán:

~~~mermaid
flowchart TD
    A["Consumer HTTPS test"] --> B{"WireMock có HTTPS listener?"}
    B -->|Không| X["Cấu hình server TLS"]
    B -->|Có| C{"Host + HTTPS port đúng?"}
    C -->|Không| Y["Sửa URL / discovery"]
    C -->|Có| D{"Certificate được tin cậy, SAN đúng?"}
    D -->|Không| Z["Sửa certificate/truststore"]
    D -->|Có| E{"TLS handshake thành công?"}
    E -->|Không| U["Kiểm tra TLS policy/mTLS"]
    E -->|Có| F{"Request match stub?"}
    F -->|Không| V["Kiểm tra method/path/headers/body"]
    F -->|Có| G["Assert consumer behavior"]
~~~

Nếu TLS handshake thất bại, request thường **chưa tới HTTP matcher**, nên có thể không có request entry trong WireMock serve events. Khi đó sửa regex hoặc body matcher thường không giải quyết nguyên nhân.

## 12. CI cần chứng minh điều gì?

Một pipeline có thể tách HTTP compatibility và HTTPS client behavior thành các cổng kiểm tra khác nhau:

~~~mermaid
flowchart TD
    A["Contract Groovy/YAML đã review"] --> B["Sinh producer contract tests"]
    B --> C{"Producer tests PASS và không bị skip?"}
    C -->|Không| X["BLOCK"]
    C -->|Có| D["Sinh/publish stub artifact đúng version"]
    D --> E["Consumer test qua Stub Runner"]
    E --> F{"Consumer assertions PASS?"}
    F -->|Không| X
    F -->|Có| G["HTTPS WireMock client integration test"]
    G --> H{"TLS trust/SAN và HTTP assertions PASS?"}
    H -->|Không| X
    H -->|Có| I["Lưu bằng chứng và xét rollout"]
~~~

Trong báo cáo có thể ghi nhận:

~~~yaml
# Ví dụ evidence do dự án tự thiết kế.
producer_revision: "order-service@abc123"
contracts_revision: "contracts@def456"
stub_artifact: "com.example.orders:order-service:1.4.2:stubs"
consumer_revision: "checkout-service@cde789"
wiremock_https_enabled: true
test_hostname: localhost
test_certificate_san:
  - "DNS:localhost"
test_truststore: "wiremock-client-trust.p12"
hostname_verification_checked: true
producer_contract_tests: PASS
consumer_stub_tests: PASS
https_client_integration_tests: PASS
~~~

Không đặt password/private key vào evidence. Một giá trị như `hostname_verification_checked: true` chỉ đáng tin nếu có **test âm tính** hoặc cơ chế xác minh thực tế. Kết quả còn phải được gắn với đúng producer build, stub artifact version, consumer commit và test configuration.

**Cần nêu phạm vi:** HTTPS với WireMock chứng minh kết nối tới test endpoint đã cấu hình, không tự chứng minh TLS/certificate của ingress production được quản lý đúng, hoặc mọi consumer đều tương thích.

## 13. Bài tập thực hành

### Bài tập A — Chọn port đúng

WireMock chạy HTTP trên `10876` và HTTPS trên `11443`. Consumer gọi `https://localhost:10876/api/orders/ORD-1001` rồi gặp lỗi TLS.

**Yêu cầu:** sửa URL, giải thích vì sao `stub.port()` không thể thay `stub.httpsPort()` và bổ sung assertion JSON.

**Gợi ý:** dùng `https://localhost:11443`, truststore test phù hợp, kiểm tra status 200 và `status: PAID`.

### Bài tập B — Certificate SAN sai

Server có certificate SAN `DNS:localhost`; consumer container gọi `https://wiremock:8443`.

**Yêu cầu:** giải thích vì sao truststore đúng vẫn thất bại và đề xuất sửa an toàn.

**Gợi ý:** tạo cert test có `DNS:wiremock` hoặc điều chỉnh hostname/URL đúng với SAN. Không tắt hostname verification.

### Bài tập C — TLS thành công nhưng 404

HTTPS handshake thành công. Stub chỉ định nghĩa `GET /api/orders/ORD-1001`, nhưng consumer gửi `GET /api/orders/ORD-9999`.

**Yêu cầu:** xác định lỗi nằm ở tầng nào và nơi cần điều tra.

**Gợi ý:** HTTP WireMock mapping, không phải TLS; kiểm tra request journal và method/path/header/body.

### Bài tập D — Truststore và server keystore

Một thành viên commit một bản sao private key production vào repository test và cho mọi client dùng nó để kết nối HTTPS.

**Yêu cầu:** nêu các rủi ro và đề xuất giải pháp.

**Gợi ý:** dùng test keypair riêng, chỉ phân phối public CA/cert cho client, bảo vệ private key và cấp quyền phù hợp.

### Bài tập E — Stub Runner chỉ mở HTTP

Consumer cần HTTPS. Stub Runner phiên bản đang dùng chạy một HTTP stub server bình thường.

**Yêu cầu:** đề xuất cách xác minh HTTP contract và HTTPS client mà không tuyên bố sai rằng Stub Runner đã mở TLS.

**Gợi ý:** chạy Stub Runner cho HTTP compatibility, WireMockServer HTTPS riêng cho TLS client; hoặc kiểm tra và dùng cách bật HTTPS được phiên bản Stub Runner hỗ trợ.

### Bài tập F — Kiểm tra TLS âm tính

HTTPS test PASS sau khi bật relaxed SSL, nhưng khi dùng truststore hẹp thì FAIL.

**Yêu cầu:** có đủ bằng chứng để phát hành cấu hình HTTPS này không? Nêu các bước tiếp theo.

**Gợi ý:** chưa. Cần cấu hình server cert/SAN và client truststore hợp lệ, bật hostname verification, chạy thử cả certificate/hostname đúng và sai.

## 14. Checklist trước khi kết luận bài kiểm thử HTTPS

- [ ] Đã phân biệt mục tiêu kiểm thử TLS với HTTP contract.
- [ ] WireMock có **HTTPS listener** thực, không chỉ có mappings.
- [ ] Client dùng đúng `httpsPort()`, không nhầm `port()`.
- [ ] Certificate server là **test certificate** và không dùng private key production.
- [ ] Hostname/IP của URL khớp SAN của certificate.
- [ ] Client tin CA/certificate test qua truststore có phạm vi hẹp.
- [ ] Hostname verification được bật và có kiểm tra âm tính.
- [ ] Không dùng trust-all hoặc relaxed HTTPS validation để tạo bằng chứng TLS.
- [ ] RestTemplate/RestClient/WebClient/Feign thực tế dùng HTTP transport có TLS config đúng.
- [ ] Với discovery/load balancer, scheme và port của instance tương thích HTTPS.
- [ ] Với mTLS, server bắt buộc xác minh client certificate và có test âm tính.
- [ ] Port động, hostname và network container được quản lý có thể tái lập.
- [ ] Đã phân biệt lỗi handshake với lỗi mapping/HTTP 404.
- [ ] Stub Runner được kiểm tra **có hỗ trợ HTTPS theo cấu hình đó hay không**; không tự đoán property.
- [ ] Generated producer contract tests thực sự chạy PASS.
- [ ] Consumer tests dùng đúng stub artifact/version và assert logic ứng dụng.
- [ ] CI ghi phạm vi bằng chứng, không lộ private key hoặc secret.
- [ ] Những đặc điểm TLS tại production ingress được kiểm tra riêng khi cần.

**Ghi nhớ:** WireMock HTTPS là **cấu hình server TLS và client trust/hostname verification**, còn Spring Cloud Contract chủ yếu bảo vệ **hành vi HTTP đã thỏa thuận**. Muốn có bằng chứng tương thích đáng tin, cần xác minh cả generated producer tests, stub/consumer behavior và đường kết nối HTTPS của client; không đánh đồng chúng hoặc tắt TLS validation chỉ để làm CI xanh.
