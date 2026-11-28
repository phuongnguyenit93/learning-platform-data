# Xác thực HTTP, proxy và cấu hình thông tin truy cập

## 1. Bài toán của một SOAP client đi qua mạng doanh nghiệp

Một SOAP client dùng **Spring Web Services (Spring-WS)** có thể gửi XML hoàn toàn đúng XSD/WSDL nhưng vẫn không kết nối được dịch vụ. Nguyên nhân thường nằm **ngoài SOAP Body**: máy chủ yêu cầu HTTP Basic/Bearer authentication, lưu lượng phải qua proxy của doanh nghiệp, proxy lại yêu cầu tài khoản khác, hoặc HTTPS/mTLS không tin cậy chứng chỉ.

Ví dụ ứng dụng quản lý vận đơn gọi SOAP service của một đối tác qua một HTTP proxy:

- Endpoint dịch vụ: `https://soap.example.invalid/ws/shipments`.
- Proxy trung gian: `proxy.example.invalid:3128`.
- Tài khoản HTTP của **dịch vụ đích**: `service-user` và secret riêng.
- Tài khoản của **proxy**: `proxy-user` và secret khác.
- Nếu có mTLS, ứng dụng còn cần client certificate/private key riêng.
- Nếu có WS-Security, SOAP Header có thể còn chứa token hoặc chữ ký XML.

Đây là **nhiều ranh giới xác thực khác nhau**. Chỉ cấu hình JAXB marshaller hoặc `SoapActionCallback` không giải quyết được HTTP 401, HTTP 407, proxy tunneling, certificate trust hay timeout.

Bài nằm trong chương **HTTP và kết nối** của module **SPRING_WEB_SERVICES**. Bối cảnh của module là phát triển dịch vụ SOAP **contract-first**, thiết kế XSD/WSDL, JAXB/OXM, endpoint/client, SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích trong tích hợp doanh nghiệp.

### Mục tiêu

Sau bài học, bạn có thể:

1. Phân biệt HTTP origin authentication, proxy authentication, HTTPS/TLS, mTLS và WS-Security.
2. Chọn `WebServiceMessageSender` phù hợp cho HTTP authentication/proxy trong Spring-WS.
3. Cấu hình Apache HttpClient 5 với **credential scopes riêng** cho origin và proxy.
4. Cấu hình Java `HttpClient`, `ProxySelector` và `Authenticator` với phạm vi trách nhiệm rõ.
5. Quản lý endpoint URI, account, password/token, proxy, trust/key material qua cấu hình an toàn.
6. Chẩn đoán HTTP 401, 403, 407, TLS failure, timeout, redirect và SOAP Fault mà không trộn chúng.
7. Hiểu connection pooling, timeout, credential rotation, idempotency và giới hạn retry.
8. Kiểm thử đường truyền thực qua proxy, TLS/mTLS, SOAP client và hệ thống đối tác.

## 2. Bốn lớp xác thực phải phân biệt

| Lớp | Chứng minh điều gì? | Nơi truyền thông tin | Điểm từ chối điển hình |
| --- | --- | --- | --- |
| **Origin HTTP authentication** | HTTP caller được origin/gateway chấp nhận | HTTP `Authorization`, challenge `WWW-Authenticate` | HTTP 401 hoặc 403 |
| **HTTP proxy authentication** | HTTP client được phép sử dụng proxy | HTTP `Proxy-Authorization`, challenge `Proxy-Authenticate` | HTTP 407 |
| **TLS/mTLS** | Kênh được bảo vệ; chứng chỉ máy chủ và đôi khi máy khách được kiểm tra | TLS handshake, không nằm trong SOAP Envelope | Handshake/hostname/trust failure |
| **SOAP WS-Security** | SOAP message/token/chữ ký/timestamp đạt policy | `soap:Header/wsse:Security` | SOAP security Fault hoặc từ chối theo stack |

Còn **application authorization** trả lời câu hỏi khác: sau khi đã xác thực caller, họ có được truy cập `shipmentId` hoặc `accountId` cụ thể không? Server phải kiểm quyền theo policy, không coi việc client đi qua proxy hoặc được mTLS xác thực là có quyền với mọi dữ liệu.

### 2.1. HTTP header và SOAP header không giống nhau

```http
POST /ws/shipments HTTP/1.1
Host: soap.example.invalid
Authorization: Basic <redacted>
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:example:shipment:v1/GetShipmentStatus"
```

Trong SOAP Envelope có thể còn:

```xml
<soapenv:Header
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">
  <wsse:Security>
    <!-- Token, signature, timestamp theo policy đã thỏa thuận -->
  </wsse:Security>
</soapenv:Header>
```

`Authorization` và `Proxy-Authorization` thuộc HTTP transport; `wsse:Security` thuộc SOAP message. Spring-WS `@SoapHeader` phía server không tự đọc HTTP `Authorization`; `WebServiceTemplate` không tự lấy SOAP UsernameToken thay cho HTTP Basic.

> Các chuỗi trong ví dụ là ký hiệu minh họa; **không** đưa mật khẩu/token thật vào source code, log hoặc tài liệu.

## 3. Luồng HTTP/SOAP khi sử dụng một proxy có xác thực

```mermaid
sequenceDiagram
    participant C as Spring-WS client
    participant P as HTTP proxy
    participant S as SOAP service
    C->>P: CONNECT soap.example.invalid:443
    P-->>C: 407 Proxy Authentication Required (nếu cần)
    C->>P: CONNECT + Proxy-Authorization
    P-->>C: 200 Connection Established
    C->>S: TLS handshake qua tunnel
    S-->>C: Server certificate (+ mTLS challenge nếu có)
    C->>S: POST SOAP + Authorization (bên trong TLS)
    S-->>C: HTTP response + SOAP Body/Fault
```

Sơ đồ minh họa proxy hỗ trợ **HTTP CONNECT tunnel** tới HTTPS origin. Không phải mọi proxy có cùng trình tự: có thể preemptive auth, authentication schemes khác, TLS-intercepting proxy, HTTP/2 hoặc chính sách gateway riêng. Kiểm thử proxy đang dùng là bắt buộc.

Điểm quan trọng:

- **Proxy account** dùng ở chặng kết nối proxy.
- **Service account** dùng khi gọi dịch vụ đích.
- Với CONNECT tunnel bảo vệ đúng bằng TLS đến origin, nội dung HTTP `Authorization` của origin nằm trong kết nối TLS bên trong tunnel.
- Nếu doanh nghiệp sử dụng proxy giải mã/kiểm TLS, mô hình trust và điểm nhìn thấy dữ liệu thay đổi; cần đánh giá chính sách bảo mật và certificate chain.
- Không gửi một credential provider phạm vi toàn cục cho bất kỳ máy chủ nào client được điều hướng tới.

### 3.1. Không nhúng password vào endpoint URL

Tránh:

```text
https://service-user:real-password@soap.example.invalid/ws
http://proxy-user:real-password@proxy.example.invalid:3128
```

Thông tin userinfo trên URI có thể lọt vào cấu hình, trace, exception hoặc log, không được mọi HTTP client hỗ trợ nhất quán và làm việc rotate secret khó khăn. Hãy tách endpoint/host/port và secret trong cấu hình có quyền truy cập hạn chế.

## 4. WebServiceTemplate không trực tiếp sở hữu HTTP credential policy

`WebServiceTemplate` là API client trung tâm của Spring-WS:

```java
Object response =
    webServiceTemplate.marshalSendAndReceive(
        request,
        new SoapActionCallback(
            "urn:example:shipment:v1/GetShipmentStatus"));
```

Trong đó:

- `Marshaller/Unmarshaller` chuyển JAXB objects sang/về XML.
- `SoapActionCallback` đặt action theo SOAP binding.
- **`WebServiceMessageSender`** quản lý kết nối transport, ví dụ HTTP.
- HTTP implementation bên dưới quyết định Basic/other HTTP auth, proxy routing, pool, TLS và timeout.
- Spring-WS client interceptors có thể xử lý SOAP message/WS-Security, khác với proxy/HTTP authentication.

`WebServiceTemplate` cho phép thiết lập một sender:

```java
template.setMessageSender(messageSender);
template.setDefaultUri(
    "https://soap.example.invalid/ws/shipments");
```

Hoặc thiết lập nhiều senders khi có nhiều transport URI schemes; sender được chọn theo khả năng hỗ trợ URI. **Không** nên dựa vào mặc định khi có proxy/auth phức tạp: cấu hình tường minh và kiểm thử kết nối.

### 4.1. Các lựa chọn HTTP message sender

| Sender | Nền HTTP | Phù hợp khi | Điểm cần lưu ý |
| --- | --- | --- | --- |
| `HttpUrlConnectionMessageSender` | `HttpURLConnection` của JDK | Kịch bản HTTP cơ bản, ít tùy chỉnh | Không có các tiện ích authentication/pooling nâng cao như Apache client |
| `JdkHttpClientMessageSender` | Java `HttpClient`, có từ Spring-WS 4.0 | Muốn JDK client với `ProxySelector`/`Authenticator` và cấu hình JDK | Một số scheme/proxy tunnel behavior phụ thuộc JDK/system properties |
| `HttpComponents5MessageSender` | Apache HttpClient 5 | HTTP auth, pooling, timeout bằng setter thuận tiện | Cần dependency Apache 5; đừng nhầm class Apache 4 |
| `SimpleHttpComponents5MessageSender` | Apache HttpClient 5 custom/factory | Cần proxy/auth scopes, redirect policy, nhiều customizations | Từ Spring-WS 4.1; nên dùng factory/default SOAP-header handling phù hợp |
| `HttpComponentsMessageSender` | Apache HttpClient 4 (legacy) | Chỉ khi project cũ đang dùng API này | `org.apache.http.*` khác hoàn toàn `org.apache.hc.*` |

Spring-WS 4.1 giới thiệu `SimpleHttpComponents5MessageSender` cho trường hợp cung cấp Apache HttpClient 5 đã cấu hình; constructor/`setHttpClient` của `HttpComponents5MessageSender` bị đánh dấu deprecated ở 4.1.0. **Không trộn ví dụ HttpClient 4, 5 hoặc JDK trong một cấu hình.**

## 5. Nguồn cấu hình: URL, origin, proxy và secrets

Nên định nghĩa các khái niệm riêng:

| Thuộc tính | Ví dụ/ý nghĩa | Mức nhạy cảm |
| --- | --- | --- |
| Endpoint URI | `https://soap.example.invalid/ws/shipments` | Thường là cấu hình, đôi khi nội bộ |
| Origin hostname/port | `soap.example.invalid:443` | Dùng cho routing và credential scope |
| Origin auth type | Basic, Bearer, mTLS, WS-Security profile | Metadata policy |
| Origin username | `service-user` | Hạn chế log |
| Origin password/token | Secret manager hoặc runtime injection | **Secret** |
| Proxy enabled/host/port | `proxy.example.invalid:3128` | Hạ tầng |
| Proxy username | `proxy-user` | Hạn chế log |
| Proxy password | Secret riêng | **Secret** |
| Truststore/CA | CA tin cậy máy chủ/proxy | Bảo vệ integrity |
| Client keystore/private key | Dùng cho mTLS | **Rất nhạy cảm** |
| Timeout, pool size | Theo SLA/môi trường | Cấu hình vận hành |
| Bypass proxy destinations | Hostname/route allowlist | Chính sách mạng |

### 5.1. Cấu hình tách secret (chỉ là schema ví dụ)

```yaml
partner:
  soap:
    endpoint-uri: https://soap.example.invalid/ws/shipments
    origin-host: soap.example.invalid
    origin-port: 443
    proxy:
      enabled: true
      host: proxy.example.invalid
      port: 3128
    connection-timeout: 5s
    read-timeout: 20s
    max-connections: 40
```

YAML trên **không chứa username/password/token**. Những giá trị nhạy cảm nên đến từ secret manager, vault, workload identity, biến môi trường được quản trị đúng hoặc cơ chế runtime injection có kiểm soát. Không commit một file `application-prod.yml` chứa mật khẩu thật.

### 5.2. Cấu hình không phải bằng chứng xác thực thành công

Dù `endpoint-uri`, `proxy.host` và `secretRef` có mặt, vẫn cần xác minh:

1. Secret có hiện hành và thuộc môi trường đúng không?
2. Tài khoản có quyền truy cập endpoint/WSDL operation không?
3. Proxy có cho CONNECT tới cổng 443 của origin không?
4. Client trust CA nào, hostname có khớp cert không?
5. Origin HTTP auth có trùng với WS-Security không?
6. Có redirect sang host khác có thể làm lộ Authorization không?

Nếu câu trả lời phụ thuộc policy của đối tác, phải làm rõ bằng tài liệu tích hợp và integration test chứ không tự suy.

## 6. HTTP Basic Authentication: cơ chế và giới hạn

HTTP Basic dùng giá trị `Authorization: Basic <base64(username:password)>`. **Base64 là encoding, không phải encryption**; Basic phải dùng qua HTTPS với certificate validation đúng.

Một trao đổi challenge minh họa:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="shipment-service"
```

Client được cấu hình credential hợp lệ có thể phản hồi theo cơ chế HTTP authentication của client library. Việc client gửi Authorization ngay request đầu (preemptive) hay sau challenge tùy policy/implementation.

### 6.1. Phân biệt 401 và 403

- **401 Unauthorized**: HTTP request thiếu hoặc không được chấp nhận bởi authentication scheme; response thường có `WWW-Authenticate`.
- **403 Forbidden**: server nhận request nhưng từ chối cấp quyền thực hiện. Có thể đến từ gateway, policy, origin hoặc authorization.
- Không suy ra từ 401/403 rằng SOAP payload đã vào endpoint hoặc rằng một business transaction chắc chắn chưa diễn ra.

Đừng đưa nguyên giá trị `Authorization` vào các công cụ logging để “debug 401”.

### 6.2. Basic không tự mô tả SOAP user

Một server có thể yêu cầu Basic ở gateway và WS-Security UsernameToken/chữ ký trong SOAP Header. Hai ràng buộc này không thay thế nhau; cần đáp ứng **cả hai** nếu security policy quy định như vậy.

## 7. Cấu hình Basic đơn giản với HttpComponents5MessageSender

Với Spring-WS 4.0.5+/4.1 và Apache HttpClient 5, sender có API `setCredentials(...)` và `setAuthScope(...)`:

```java
import java.time.Duration;

import org.apache.hc.client5.http.auth.AuthScope;
import org.apache.hc.client5.http.auth.UsernamePasswordCredentials;
import org.apache.hc.core5.http.HttpHost;
import org.springframework.ws.transport.http.HttpComponents5MessageSender;

public final class OriginHttpSenderFactory {

    public static HttpComponents5MessageSender basicSender(
            String originHost,
            int originPort,
            String username,
            char[] password) {

        HttpHost origin =
                new HttpHost("https", originHost, originPort);

        HttpComponents5MessageSender sender =
                new HttpComponents5MessageSender();

        sender.setAuthScope(new AuthScope(origin));
        sender.setCredentials(
            new UsernamePasswordCredentials(username, password));

        sender.setConnectionTimeout(Duration.ofSeconds(5));
        sender.setReadTimeout(Duration.ofSeconds(20));
        sender.setMaxTotalConnections(40);

        return sender;
    }
}
```

**Giới hạn của ví dụ:** chỉ cấu hình **origin Basic credentials**; chưa có proxy, mTLS hoặc token refresh. Nếu credentials provider chọn scheme tự động, việc dùng username/password không buộc dịch vụ chỉ được trao đổi bằng Basic; scheme thực tế đến từ server challenge và HTTP client configuration. Test đúng scheme/policy.

Không dùng phạm vi credentials mặc định quá rộng khi caller có thể truy cập nhiều origins. `new AuthScope(origin)` giới hạn scope theo host/scheme/port, giúp tránh dùng lại service password cho proxy hoặc một host không liên quan.

### 7.1. Sự khác biệt Apache HttpClient 4 và 5

| Thành phần | Apache HttpClient 4 | Apache HttpClient 5 |
| --- | --- | --- |
| Packages | `org.apache.http.*` | `org.apache.hc.client5.*`, `org.apache.hc.core5.*` |
| Sender Spring-WS | `HttpComponentsMessageSender` | `HttpComponents5MessageSender` |
| Username/password credentials | API khác, thường password string | `UsernamePasswordCredentials(username, char[])` |
| Timeout setters | Thường `int` milliseconds | `Duration` trong API Spring-WS 4.1 |
| Preconfigured client (4.1) | API cũ | Ưu tiên `SimpleHttpComponents5MessageSender` |

Một bài hướng dẫn tìm trên mạng dùng `org.apache.http.auth.UsernamePasswordCredentials` sẽ không thể copy thẳng vào `HttpComponents5MessageSender`. Kiểm project dependency thực trước khi chọn ví dụ.

## 8. Cấu hình proxy và credentials riêng cho origin/proxy

Khi phải qua proxy có xác thực, **một bộ credential duy nhất không đủ**. Ta cần hai `AuthScope`:

- Service credentials được gắn với `https://soap.example.invalid:443`.
- Proxy credentials được gắn với `http://proxy.example.invalid:3128`.

Spring-WS 4.1 hỗ trợ `HttpComponents5ClientFactory.withDefaults()` và `SimpleHttpComponents5MessageSender`. Factory giúp quản lý custom Apache client và cấu hình mặc định cần thiết cho SOAP POST.

### 8.1. Ví dụ Apache HttpClient 5 qua authenticated proxy

```java
import java.time.Duration;

import org.apache.hc.client5.http.auth.AuthScope;
import org.apache.hc.client5.http.auth.UsernamePasswordCredentials;
import org.apache.hc.client5.http.impl.auth.BasicCredentialsProvider;
import org.apache.hc.core5.http.HttpHost;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.transport.http.HttpComponents5ClientFactory;
import org.springframework.ws.transport.http.SimpleHttpComponents5MessageSender;

public final class ProxiedSoapClientFactory {

    public static WebServiceTemplate create(
            PartnerAccessSecrets secrets) {

        HttpHost origin =
                new HttpHost("https", "soap.example.invalid", 443);
        HttpHost proxy =
                new HttpHost("http", "proxy.example.invalid", 3128);

        BasicCredentialsProvider provider =
                new BasicCredentialsProvider();

        provider.setCredentials(
            new AuthScope(origin),
            new UsernamePasswordCredentials(
                secrets.originUsername(),
                secrets.originPassword()));

        provider.setCredentials(
            new AuthScope(proxy),
            new UsernamePasswordCredentials(
                secrets.proxyUsername(),
                secrets.proxyPassword()));

        HttpComponents5ClientFactory factory =
                HttpComponents5ClientFactory.withDefaults();

        factory.setConnectionTimeout(Duration.ofSeconds(5));
        factory.setReadTimeout(Duration.ofSeconds(20));
        factory.setMaxTotalConnections(40);

        factory.addClientBuilderCustomizer(builder -> {
            builder.setProxy(proxy);
            builder.setDefaultCredentialsProvider(provider);
            builder.disableRedirectHandling();
        });

        SimpleHttpComponents5MessageSender sender =
                new SimpleHttpComponents5MessageSender(factory);

        WebServiceTemplate template = new WebServiceTemplate();
        template.setDefaultUri(
                "https://soap.example.invalid/ws/shipments");
        template.setMessageSender(sender);
        return template;
    }
}
```

`PartnerAccessSecrets` là interface/adapter **do ứng dụng định nghĩa**, ví dụ cung cấp `originUsername()`, `originPassword()`, `proxyUsername()`, `proxyPassword()` từ một secret provider; các password methods trả `char[]`. Đây là code hướng dẫn cho HTTP transport; khi gọi `marshalSendAndReceive` còn cần JAXB marshaller/unmarshaller và SOAPAction callback.

**Các điều kiện phải xác minh:**

1. `origin` thực sự khớp host/port/scheme của endpoint URI. Nếu URI thay đổi theo môi trường, tạo scope từ cấu hình tương ứng, không giữ literal `soap.example.invalid` của bài học.
2. `proxy` thực sự là proxy được phép theo chính sách mạng.
3. Username/password của origin và proxy **không dùng chung** chỉ để “dễ vận hành”.
4. Mọi secret được nạp từ nguồn quản trị; không log `provider` hoặc `secrets`.
5. HTTPS và truststore có hiệu lực; Basic không được gửi qua đường plaintext tới origin.
6. Test thực tế một request qua proxy, vì HTTP auth handshake/CONNECT phụ thuộc HTTP client và proxy triển khai.
7. `builder.disableRedirectHandling()` minh họa chính sách **không tự theo redirect** đối với SOAP POST để tránh sai endpoint và credential leakage. Nếu contract bắt buộc redirect, phải có allowlist/method semantics và test riêng.

### 8.2. Vì sao dùng `withDefaults()`?

Spring-WS cung cấp `HttpComponents5ClientFactory.withDefaults()` với interceptor xử lý một số HTTP transport headers do SOAP message tạo, ví dụ xử lý `Content-Length`/`Transfer-Encoding` để Apache client tính đúng entity headers.

Khi tự dựng Apache `HttpClient` bằng tay rồi đưa vào `SimpleHttpComponents5MessageSender`, bạn cần hiểu ai chịu trách nhiệm với những headers này. Không tự đặt hoặc giữ hai giá trị `Content-Length` mâu thuẫn; test SOAP POST thật với body có kích thước khác nhau.

### 8.3. Bảo mật của proxy authentication

Proxy credentials chỉ được gửi tới **proxy được chỉ định** và theo authentication scheme mà proxy yêu cầu. Đừng gắn `Proxy-Authorization` tĩnh cho mọi HTTP request, và đừng cho credential provider có scope `ANY` nếu có thể giới hạn theo proxy host/port.

Với proxy qua HTTP, một số metadata của CONNECT và auth exchange có thể không được bảo vệ bởi TLS ở chặng client–proxy; nếu dùng Basic cho proxy, cần đánh giá chính sách đường truyền nội bộ hoặc sử dụng HTTPS proxy nếu stack và hạ tầng hỗ trợ. Việc origin dùng HTTPS **không tự bảo vệ password gửi tới proxy** trước khi tunnel được thiết lập.

## 9. Bật hoặc tắt proxy theo môi trường

Không phải môi trường nào cũng có proxy:

- Laptop dev có thể gọi trực tiếp sandbox.
- CI có proxy outbound bắt buộc.
- Production trong private network có egress gateway nhưng không cho direct internet.
- Một số hosts nội bộ phải đi trực tiếp (bypass/no-proxy).
- Khu vực disaster recovery có proxy hoặc host khác.

Đừng trộn mọi nhánh vào một biến `http.proxyHost` toàn cục nếu ứng dụng đồng thời gọi nhiều dịch vụ khác nhau với policy khác nhau.

### 9.1. Tách factory theo route

```text
PartnerEndpointPolicy
  ├─ endpoint-uri
  ├─ allowed-origin-hosts
  ├─ origin-auth-policy
  ├─ proxy-required?
  │    ├─ proxy-host
  │    └─ proxy-auth-policy
  ├─ tls-policy
  ├─ timeout-policy
  └─ redirect-policy
       |
       v
WebServiceMessageSender per destination/policy
       |
       v
WebServiceTemplate per partner integration
```

Với nhiều đối tác, có thể tạo mỗi template/sender theo một security/route profile rõ ràng. **Không** cập nhật `setCredentials(...)` hoặc `setDefaultUri(...)` trên một shared template đang xử lý request đồng thời để thay đổi tài khoản theo từng tenant; cách đó dễ race hoặc gửi sai secrets.

### 9.2. Bypass proxy phải có test

Một `NO_PROXY` hoặc system property có thể được một HTTP stack tôn trọng nhưng stack khác bỏ qua. Nếu dùng Apache client đã `setProxy(proxy)` rõ, các biến môi trường của hệ điều hành không nhất thiết override cấu hình ấy.

Hãy có test quan sát thực tế request đi qua proxy hay trực tiếp. Cấu hình bypass thiếu kiểm soát có thể làm phá egress policy hoặc cho phép truy cập host ngoài allowlist.

## 10. JdkHttpClientMessageSender và ProxySelector

Nếu dự án chọn JDK `HttpClient`, Spring-WS 4.x có `JdkHttpClientMessageSender`. Java API cho phép cấu hình proxy và authenticator.

Ví dụ **proxy route** cơ bản:

```java
import java.net.InetSocketAddress;
import java.net.ProxySelector;
import java.net.http.HttpClient;
import java.time.Duration;

import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.transport.http.JdkHttpClientMessageSender;

public final class JdkSoapTransportFactory {

    public static WebServiceTemplate createViaProxy() {
        HttpClient client = HttpClient.newBuilder()
            .proxy(ProxySelector.of(
                new InetSocketAddress(
                    "proxy.example.invalid", 3128)))
            .connectTimeout(Duration.ofSeconds(5))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

        JdkHttpClientMessageSender sender =
                new JdkHttpClientMessageSender(client);
        sender.setRequestTimeout(Duration.ofSeconds(20));

        WebServiceTemplate template = new WebServiceTemplate();
        template.setMessageSender(sender);
        template.setDefaultUri(
                "https://soap.example.invalid/ws/shipments");
        return template;
    }
}
```

Đây là **ví dụ proxy không yêu cầu credentials**; không tự suy ra Basic/Bearer từ JDK `HttpClient`. Điểm cần hiểu là `HttpClient` quyết định proxy selector, redirect, TLS session và các API auth mà JDK hỗ trợ; Spring-WS đặt SOAP message lên transport đó.

### 10.1. Khi proxy cần authentication

Có thể cấu hình `HttpClient.Builder.authenticator(Authenticator)`. Một Authenticator có thể phân biệt:

- `RequestorType.PROXY`: xác thực proxy.
- `RequestorType.SERVER`: xác thực origin.

Khi viết custom authenticator, kiểm **requestor type, host, port và scheme**, tránh trả origin password cho một proxy hoặc một máy chủ không được chấp thuận. Không dùng một `PasswordAuthentication` mặc định cho mọi request host.

**Cảnh báo quan trọng:** JDK HTTP client và `HttpURLConnection` có những hạn chế/chính sách khác nhau đối với Basic proxy authentication cho HTTPS CONNECT; ví dụ JDK có thể chặn Basic tunneling bởi default-disabled auth schemes. Không chỉnh các system properties bảo vệ này một cách mù quáng chỉ để “qua được proxy”; nếu corporate proxy yêu cầu scheme đặc biệt, hãy chọn sender/client đáp ứng policy và kiểm thử.

### 10.2. Chọn JDK hay Apache?

- Chọn JDK khi policy proxy/auth tương thích các tính năng JDK và không cần Apache-specific customization.
- Chọn Apache HttpClient 5 khi cần scope rõ cho nhiều credentials, advanced proxy handling, pool, route customization và quan sát chi tiết.
- Không kết luận Apache “bảo mật hơn” chỉ từ tên thư viện: cấu hình TLS, credentials, redirects và certificate trust quyết định độ an toàn.

## 11. HTTP 401 và 407: cùng chữ “authentication” nhưng hai nơi khác nhau

### 11.1. 401: origin/gateway yêu cầu xác thực

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="shipment-service"
```

Hướng kiểm:

1. Có gọi đúng endpoint URI, host, scheme và port không?
2. Có dùng đúng service account và auth mechanism không?
3. Credential scope có match origin được gọi không?
4. Server cần Basic, Digest, Bearer, mTLS hay WS-Security?
5. Có gateway đứng trước origin trả 401 thay cho SOAP endpoint không?
6. Credential có hết hạn/đã bị rotate không?
7. Client/proxy có follow redirect đến host khác làm thay auth context không?

### 11.2. 407: proxy yêu cầu xác thực

```http
HTTP/1.1 407 Proxy Authentication Required
Proxy-Authenticate: Basic realm="corporate-egress"
```

Hướng kiểm:

1. Client có thực sự đi qua proxy đó không?
2. Proxy hostname/port có đúng theo môi trường không?
3. `BasicCredentialsProvider` có scope theo proxy, **không** origin không?
4. Proxy auth scheme có được HTTP stack hỗ trợ không?
5. Có cần VPN, domain, Kerberos/NTLM hoặc allowlist riêng không?
6. Proxy có cho CONNECT đến đích và cổng 443 không?
7. HTTPS tunnel có được thiết lập sau khi proxy auth thành công không?

### 11.3. 403 không phải mặc định là SOAP Fault

HTTP 403 có thể đến từ proxy, WAF, API gateway, origin hoặc security middleware. Nó không chứng minh `@Endpoint` đã chạy. Ngược lại, application authorization denial có thể được biểu diễn trong một SOAP Fault **nếu request đã đi đến SOAP stack** và policy cho phép.

Không gán tất cả 401/403/407 thành `SoapFaultClientException`; cần phân loại theo transport và đọc response content nếu có.

## 12. Bearer token: khi nào khác HTTP Basic?

Một số SOAP endpoints dùng OAuth 2.0 access token hoặc token có thời hạn trong HTTP:

```http
Authorization: Bearer <redacted-access-token>
```

Đây là **HTTP bearer authentication**, khác với `wsse:Security` trong SOAP Header. Bearer token thường có hạn sử dụng; client adapter phải tính đến refresh, caching, scope/audience và token rotation.

### 12.1. Không đưa token vào SOAPAction hoặc Body

Không dùng:

```xml
<sh:GetShipmentStatusRequest>
  <sh:accessToken>...</sh:accessToken>
</sh:GetShipmentStatusRequest>
```

trừ khi contract **thực sự** thiết kế một field như vậy (và được đánh giá bảo mật). Token được gửi trong HTTP Authorization **không** tự trở thành `@SoapHeader` hoặc JAXB field.

### 12.2. Cấu hình Bearer đúng tầng

Có thể sử dụng HTTP client request interceptor/hook hỗ trợ thêm `Authorization` **cho origin đã cho phép** ngay trước khi gửi; token supplier lấy token hiện hành từ một provider thread-safe. Với Apache HttpClient 5, builder có request interceptors, nhưng cần kiểm target route khi có proxy/redirect. Không dùng một interceptor toàn cục gắn Bearer vào mọi request bất kể destination.

Các điều kiện an toàn:

- Chỉ gửi token tới HTTPS hosts trong allowlist.
- Không log token, không đưa vào query parameter hoặc exception.
- Refresh dựa trên expiry, dùng đồng bộ hợp lý khi nhiều threads cùng refresh.
- Không retry vô hạn khi nhận 401; chỉ refresh một cách có giới hạn theo policy.
- Không đưa token sang proxy bằng `Proxy-Authorization` nếu đó là origin token.
- Kiểm audience/scope đối tác yêu cầu, không hoán đổi token giữa môi trường production và sandbox.

### 12.3. Preemptive authentication

Basic/Digest có thể dựa vào challenge; một số gateway yêu cầu auth ngay request đầu. Preemptive Basic gửi header không đợi 401 và phải được cấu hình giới hạn theo origin; có nguy cơ lộ credential nếu đi nhầm host. Với SOAP POST có side effect, một cơ chế HTTP auth challenge có thể dẫn đến HTTP client gửi lại request; quy trình idempotency và xử lý side effect vẫn phải được thiết kế.

Không dùng `Authorization` thủ công trên toàn bộ `WebServiceTemplate` làm workaround cho mọi scheme khi HTTP client có cơ chế auth riêng và scoped credentials.

## 13. HTTP Digest, NTLM, Kerberos và proxy doanh nghiệp

Không phải mọi môi trường chỉ dùng Basic:

| Cơ chế | Khi gặp | Điều cần kiểm tra |
| --- | --- | --- |
| Digest | Một số SOAP services cũ | Server challenge, nonce/realm, hỗ trợ thực tế của HTTP client |
| NTLM | Môi trường doanh nghiệp cũ | Domain/workstation và version client, chính sách bảo mật |
| Kerberos/SPNEGO/Negotiate | Doanh nghiệp tích hợp SSO | Ticket, service principal, DNS/time sync, client configuration |
| Bearer/OAuth 2.0 | API gateway hiện đại trước SOAP | Access token source, expiry, scopes/audience |
| mTLS | Xác thực workload/máy khách | Client certificate/private key, trust, rotation |
| WS-Security | SOAP policy yêu cầu ký/mã hóa/token | WSS4J, X.509 XML Signature, timestamp/replay |

Một `UsernamePasswordCredentials` **không tự bật NTLM/Kerberos**. Cấu hình auth scheme cụ thể phụ thuộc Apache/JDK client, challenge và phiên bản thư viện. Với NTLM legacy, Spring-WS có những ví dụ custom Apache HttpClient; cần kiểm tra hỗ trợ security và yêu cầu migration thay vì sao chép mã không tương thích.

Không dùng Digest như lý do để bỏ TLS hoặc hostname verification. Với SOAP có dữ liệu nhạy cảm, bảo vệ kênh và payload theo policy vẫn cần độc lập với HTTP scheme.

## 14. HTTPS, truststore và mutual TLS

HTTP authentication xử lý danh tính ở tầng HTTP. **TLS** bảo vệ kênh và xác thực server certificate; **mTLS** bổ sung client certificate để server xác thực client khi TLS handshake.

### 14.1. Phân biệt truststore và keystore

- **Truststore**: danh sách CA/certificate client tin để kiểm chứng server/proxy TLS endpoint (tùy topology).
- **Keystore**: client certificate/private key dùng để chứng minh danh tính của client cho server trong mTLS.
- **HTTP username/password**: secret khác, gửi qua HTTP auth, không phải nội dung trong keystore.
- **WS-Security signing key**: có thể liên quan PKI nhưng được dùng để ký **SOAP XML**, không tự đồng nhất với TLS client key.

### 14.2. Mẫu tạo SSLContext của JDK

```java
import java.security.KeyStore;
import java.security.SecureRandom;

import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public final class ClientTlsContexts {

    public static SSLContext create(
            KeyStore clientIdentity,
            char[] keyPassword,
            KeyStore trustedCAs) throws Exception {

        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(clientIdentity, keyPassword);

        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(trustedCAs);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(
                kmf.getKeyManagers(),
                tmf.getTrustManagers(),
                new SecureRandom());

        return context;
    }
}
```

`clientIdentity` và `trustedCAs` là `KeyStore` đã được tải **từ nguồn đáng tin và được bảo vệ**; code này chỉ tạo `SSLContext`, chưa cấu hình vào HTTP sender. Với JDK `HttpClient.Builder.sslContext(context)` có thể gắn vào client ở mục 10. Với Apache HttpClient 5, cần cấu hình TLS strategy/connection manager của đúng phiên bản.

### 14.3. Không “trust all” để chạy được

Các anti-pattern nguy hiểm:

- `TrustManager` luôn chấp nhận mọi certificate.
- Tắt hostname verification.
- Bỏ kiểm chain hoặc tin certificate tự ký bất kỳ.
- Gắn private key/certificate vào Git repository.
- Đưa key password qua query parameter hoặc log.
- Dùng cùng một identity certificate cho mọi đối tác/tenant không được policy cho phép.

Nếu kết nối HTTPS thất bại do certificate, phải sửa trust chain, hostname/SAN, certificate rotation hoặc policy môi trường. Không tắt bảo vệ chỉ vì SOAP XML hợp lệ.

## 15. Proxy CONNECT và certificate trong môi trường có TLS inspection

Một HTTPS request qua HTTP proxy thường đi theo `CONNECT`. Có ba trường hợp đáng chú ý:

1. **Transparent CONNECT tunnel**: client thiết lập TLS với origin và kiểm origin certificate.
2. **TLS-inspecting proxy** được doanh nghiệp cho phép: proxy kết thúc một TLS session và tạo session khác tới origin; client thấy chain do proxy cung cấp, cần chính sách trust riêng.
3. **Proxy không hỗ trợ CONNECT/đích bị chặn**: có thể nhận 403/407/502 ở chặng proxy mà không có SOAP Fault.

Nếu cần WS-Security XML signature, việc proxy sửa SOAP message sau khi ký có thể làm verification thất bại. Đừng giả định TLS inspection luôn giữ nguyên byte-level SOAP representation.

**Chứng chỉ không được tin** không đồng nghĩa **sai SOAP Fault**. Handshake có thể chưa đi đến application. Dùng logging TLS an toàn và proxy/server audit khi chẩn đoán.

## 16. Timeout: connect, pool lease, read và request không giống nhau

| Timeout | Ý nghĩa | Triệu chứng khi cấu hình quá thấp |
| --- | --- | --- |
| DNS/route (không phải luôn có một setter riêng) | Tìm địa chỉ, chọn route và kết nối mạng | Chờ lâu hoặc lỗi host |
| **Connection timeout** | Thời gian thiết lập TCP/route/connection theo client | Không kết nối được hoặc proxy chậm |
| **Pool acquisition/lease timeout** | Chờ một connection có sẵn trong pool | Tải cao gây timeout dù server khỏe |
| **Read/response timeout** | Chờ dữ liệu/response sau khi gửi theo HTTP client | Server xử lý lâu hoặc mạng chậm |
| **Overall request deadline** | Giới hạn toàn bộ lời gọi theo policy | Cần phối hợp nhiều timeouts và cancellation |

`HttpComponents5MessageSender` có `setConnectionTimeout(Duration)` và `setReadTimeout(Duration)`. `JdkHttpClientMessageSender` có `setConnectionTimeout(Duration)` và `setRequestTimeout(Duration)`; ý nghĩa không nhất thiết trùng hoàn toàn. Khi dùng Apache client custom, pool lease/connection request timeout có thể cần cấu hình trong underlying HttpClient/request config.

### 16.1. Ví dụ timeout profile

```text
Connect timeout = 5s
Read/response timeout = 20s
Business operation SLA = 12s
Retry policy = 0 hoặc có giới hạn theo operation
```

Các con số là **minh họa**, không phải chuẩn chung. Nếu SLA nghiệp vụ 12 giây nhưng client chờ read timeout 20 giây rồi còn retry 3 lần, tổng thời gian có thể vượt SLA. Hãy tính deadline end-to-end bao gồm DNS, proxy CONNECT, TLS handshake, SOAP serialization, server processing và retry/backoff.

### 16.2. Read timeout không kết luận server chưa xử lý

Nếu `CreateShipment` đã ghi database rồi response bị mất, client nhận read timeout. Đây là trạng thái **unknown outcome**, phải tra cứu theo request ID hoặc retry cùng idempotency key theo hợp đồng. Không phát sinh request ID mới cho mỗi lần retry POST.

## 17. Connection pooling, keep-alive và lifecycle

Apache HttpClient 5 có connection pooling; `HttpComponents5MessageSender` cung cấp `setMaxTotalConnections(int)` và các cấu hình pool khác. Nhưng pool không mặc nhiên giúp hiệu năng nếu bạn đặt quá nhỏ, không release connection hoặc server/proxy thường đóng idle connections.

Các chỉ số nên theo dõi:

- Active / idle / pending connections.
- Pool exhaustion và thời gian chờ lease.
- TCP resets khi tái sử dụng kết nối đã bị proxy/server đóng.
- TLS handshake frequency, timeouts và reconnects.
- Latency p50/p95/p99 riêng theo origin, proxy và operation.
- HTTP status 401/403/407/429/5xx (không log Authorization).
- Số lần retry và lỗi SOAP Fault/transport.

### 17.1. Lifecycle của HTTP client

Tạo và chia sẻ sender/template theo policy cho nhiều requests thường tốt hơn tạo một HTTP client mới mỗi SOAP call. Nhưng tài nguyên pool/threads phải được đóng khi application shutdown; hãy dùng cơ chế bean lifecycle/`DisposableBean` phù hợp của sender/client.

Không đóng shared `CloseableHttpClient` ngay sau một request rồi tiếp tục dùng `WebServiceTemplate`. Ngược lại, không để client/pool không được quản lý lifecycle khi redeploy.

### 17.2. Concurrent use không đồng nghĩa được đổi cấu hình tùy ý

Một `WebServiceTemplate`/HTTP client cấu hình cố định có thể phục vụ nhiều request, nhưng **mutate sender.credentials hoặc template.defaultUri trong lúc chạy** không phải cách an toàn để đổi tenant. Nên tách beans per partner/credential profile hoặc dùng token provider per request có scope được kiểm chứng và thread-safe.

## 18. Credential rotation và quản trị secret

Một hệ thống doanh nghiệp có thể phải rotate:

- Basic password của service account.
- Proxy password hoặc account.
- Bearer access/refresh tokens.
- mTLS client certificate/private key.
- CA/truststore khi đối tác thay chain.
- WS-Security signing certificate/alias.

### 18.1. Quy trình rotation

1. Đối tác/corporate IT công bố cửa sổ thay đổi và policy hỗ trợ song song credential cũ/mới.
2. Secret manager phát hành version mới, có access control/audit.
3. Ứng dụng cập nhật sender/credential provider đúng cách hoặc recreate client pool nếu bắt buộc.
4. Chạy readiness/smoke test với endpoint phù hợp mà không phát sinh giao dịch ngoài ý muốn.
5. Theo dõi HTTP 401/407, TLS failures, WS-Security Fault và error rate.
6. Thu hồi secret cũ, xác minh không còn clients sử dụng.
7. Giữ rollback có kiểm soát trong thời gian chuyển tiếp; không lưu plaintext password ở logs/artifacts.

### 18.2. Một lần đổi secret không bảo đảm mọi connection thay ngay

Nếu underlying client dùng credential cache, keep-alive hoặc session reuse, việc secret manager trả secret mới **không chắc** tự cập nhật tất cả connection pools/senders đã khởi tạo. Cần hiểu client lifecycle và rotate bằng cách cập nhật provider an toàn hoặc tạo client mới rồi dừng client cũ có kiểm soát.

Với Bearer token, provider nên tránh “thundering herd” khi hàng trăm requests cùng thấy token hết hạn; dùng đồng bộ refresh/expiry skew và không retry vô hạn.

### 18.3. Đừng đặt cả origin và proxy password trong một biến

`SOAP_PASSWORD` và `PROXY_PASSWORD` là hai mục đích khác nhau. Việc dùng chung một secret tăng blast radius khi bị lộ và khiến audit/revocation khó hơn.

## 19. Redirects, DNS và phòng tránh rò rỉ credentials

SOAP POST thường được gửi đến một endpoint cụ thể đã công bố trong WSDL. Nếu HTTP client tự động follow HTTP 301/302/307/308 tới một host khác, các nguy cơ gồm:

- Đổi method/body không tương thích với SOAP operation.
- Gửi Authorization hoặc Bearer token tới host không mong đợi.
- Đi qua proxy/bypass route khác.
- Đổi hostname làm TLS certificate check thất bại.
- Trùng side effects nếu request bị gửi lại.

**Khuyến nghị:** không tự follow cross-origin redirect đối với SOAP POST trừ khi contract/gateway policy định nghĩa và có allowlist + tests. Ví dụ Apache builder ở mục 8 đã minh họa `disableRedirectHandling()`.

### 19.1. DNS cũng thuộc trust boundary

Nếu service URI có thể do input người dùng quyết định, code có thể bị biến thành SSRF client gọi intranet hoặc metadata endpoint. Hãy giới hạn destinations bằng cấu hình do người quản trị kiểm soát, allowlist scheme/host/port, và kiểm routing thực (DNS rebinding/proxy behavior) theo threat model.

`WebServiceTemplate.sendAndReceive(uri, ...)` không nên nhận URL tùy ý từ SOAP payload hoặc HTTP request mà không có validation và destination policy.

## 20. SOAP Fault không phải lỗi HTTP authentication

Một SOAP 1.1 Fault trả về có dạng:

```xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <soapenv:Fault>
      <faultcode>soapenv:Client</faultcode>
      <faultstring>Invalid shipment request</faultstring>
    </soapenv:Fault>
  </soapenv:Body>
</soapenv:Envelope>
```

Đây là **SOAP protocol/application error**. HTTP 401 hoặc 407 có thể chỉ mang HTML/text hoặc empty body từ gateway/proxy. TLS handshake failure thậm chí không có HTTP response. Không cố parse chúng như SOAP Fault.

### 20.1. Client exception taxonomy

| Nhận được | Phân loại | Hướng xử lý |
| --- | --- | --- |
| SOAP Fault `Client/Sender` | SOAP contract/business/security tùy detail | Đọc Fault code/reason/detail theo WSDL |
| SOAP Fault `Server/Receiver` | SOAP xử lý lỗi phía server | Xem retry policy và idempotency |
| HTTP 401 | Origin/gateway authentication | Kiểm service credentials, challenge/realm, scope |
| HTTP 403 | Origin/gateway/proxy policy | Kiểm authorization, allowlist và nguồn trả lỗi |
| HTTP 407 | Proxy authentication | Kiểm proxy credentials và route |
| TLS handshake error | Transport/certificate | Kiểm truststore, hostname, mTLS |
| Connect/read timeout | Transport/unknown outcome | Backoff, status query/idempotency cho command |
| HTTP 429/503 | Rate limit/availability | Retry có giới hạn theo SLA/policy; không mặc định safe |

Spring-WS `WebServiceTemplate` có Fault resolver cho SOAP messages và transport exceptions cho lỗi HTTP/I/O; exception cụ thể phụ thuộc sender. Đừng viết một `catch (Exception e) { return null; }` khiến mọi lỗi trở thành “không có dữ liệu”.

## 21. Phân biệt xác thực client SOAP và authorization server

Client gửi HTTP credentials chỉ chứng minh một khía cạnh identity ở gateway. Server có thể vẫn cần:

- Schema validation với XSD.
- Routing theo payload QName và SOAPAction/binding policy.
- WS-Security signature/timestamp/token verification.
- Authorization trên `accountId`/`shipmentId` của caller.
- Business policy và state transitions.
- Idempotency, transaction và SOAP Fault mapping.

Trong môi trường nhiều tenants, **không lấy accountId trong SOAP Body hoặc custom Header TenantCode làm danh tính đã xác thực**. HTTP authentication provider, TLS certificate identity hoặc WS-Security principal phải được ánh xạ vào security context đáng tin theo policy, rồi authorization quyết định quyền cụ thể.

## 22. Logging và quan sát không làm lộ bí mật

Log minh họa:

```text
partner=shipment-provider
operation=GetShipmentStatus
route=via-proxy
httpStatus=407
errorCategory=PROXY_AUTH
correlationId=CORR-1042
durationMs=153
```

Những thứ **không được log mặc định**:

- `Authorization`, `Proxy-Authorization`, bearer/refresh tokens.
- Basic password và HTTP challenge credential data.
- Full SOAP Header chứa WS-Security UsernameToken hoặc signature.
- Private key, keystore passwords, secret-manager values.
- Full SOAP Body chứa thông tin khách hàng.
- Credential provider `toString()` hoặc debug dump của HTTP request.

### 22.1. Metrics cần phân biệt lỗi

Các metrics ví dụ:

```text
soap_client_requests_total{partner="shipment",operation="GetStatus"}
soap_http_responses_total{origin="shipment",status="401"}
soap_proxy_auth_failures_total{proxy="corp-egress"}
soap_tls_handshake_failures_total{partner="shipment"}
soap_faults_total{partner="shipment",faultCode="Client"}
soap_client_timeouts_total{partner="shipment",stage="read"}
soap_connection_pool_pending{partner="shipment"}
```

Đây là **tên metric thiết kế**, không phải metric mặc định của Spring-WS. Không gắn password, request ID hay high-cardinality shipment ID vào metric labels.

Để điều tra 401/407, có thể bật HTTP wire logs trong môi trường kiểm soát thời gian ngắn **chỉ sau khi bảo đảm secrets/headers/body nhạy cảm được redaction**. Tắt lại và xóa bản ghi theo chính sách lưu trữ.

## 23. Kiểm thử: mock SOAP chưa đủ để chứng minh HTTP auth

Spring-WS có `MockWebServiceServer` để kiểm tra payload, SOAPAction và SOAP response trong `WebServiceTemplate`. Nhưng mock này **không tạo một HTTP CONNECT proxy thực**, không xác thực mTLS và không bảo đảm Apache/JDK credential challenges thực tế.

### 23.1. Ma trận test theo tầng

| Test | Tool/cách làm | Bằng chứng cần có |
| --- | --- | --- |
| SOAP XML/WSDL | `MockWebServiceServer`, XML-aware matcher | Body đúng QName và SOAPAction |
| Basic origin 401→authenticated | Embedded HTTP server/gateway sandbox | Credential scope đúng, nhận SOAP response |
| Origin wrong credentials | Embedded origin | 401 được phân loại, không gọi business endpoint |
| Proxy 407→authenticated | Local authenticated proxy test fixture | Proxy credential dùng đúng; không lộ origin password |
| Proxy bypass | Route-observing test proxy | Bypass host thật sự đi direct theo policy |
| HTTPS CONNECT | Local/provisioned proxy + TLS origin | Tunnel và TLS hostname/chain chính xác |
| mTLS handshake | TLS test server yêu cầu client certificate | Cấp cert hợp lệ thành công, cert sai bị chặn |
| WS-Security signature | SOAP integration test | Chữ ký/timestamp/token đúng policy |
| HTTP 403 gateway | Gateway fixture | Không cố parse HTML response thành SOAP Fault |
| HTTP 307 redirect | Test redirect đến host khác | Không gửi origin creds sang host không tin |
| Timeout sau commit | Controlled server + DB fixture | Client không tạo duplicate khi retry |
| Token rotation | Fake token issuer/secret provider | Làm mới token đúng thời điểm, không spam/đổi sai audience |
| Connection pooling | Load test có đo pool | Không starvation/leak, giới hạn concurrency |
| .NET/ESB interoperability | Client/partner sandbox thực | HTTP auth, WSDL, SOAPAction, Fault, security tương thích |

### 23.2. Thử có proxy và không proxy

Khi chạy bài thực hành, dựng một **proxy giả lập được phép trong môi trường test**; không cần sử dụng proxy doanh nghiệp thật hoặc yêu cầu cung cấp credentials production.

Các ca cần thử:

1. Proxy host/port đúng, credential đúng, origin credential đúng: SOAP response hợp lệ.
2. Proxy credential sai, origin credential đúng: 407, chưa nhận SOAP response.
3. Proxy đúng, origin credential sai: 401 từ origin/gateway.
4. Proxy từ chối CONNECT: lỗi transport, kiểm status/source.
5. Endpoint URI host khác scope credentials: client không tự dùng origin password sai host.
6. HTTP redirect sang host ngoài allowlist: không gửi credentials, báo lỗi rõ.
7. TLS certificate không trust: handshake fail, không tắt certificate validation.
8. HTTP 200 có SOAP Fault hoặc SOAP response state `REJECTED`: phân loại ở tầng SOAP/nghiệp vụ, không coi là authentication issue.

### 23.3. Test cấu hình chứ không chỉ test method

Một unit test tạo `WebServiceTemplate` đúng object nhưng chưa gửi request **không chứng minh**:

- `BasicCredentialsProvider` chọn đúng scope khi có challenge.
- Proxy thực nhận `Proxy-Authorization` chứ không phải origin.
- HTTP client không gửi Bearer tới redirect host.
- mTLS certificate đúng alias được dùng.
- HTTP 401/407 được phân loại đúng exceptions.

Cần một test harness có thể quan sát HTTP headers **đã được làm sạch trước khi lưu** hoặc kiểm bằng assertions không in secret. So sánh mọi giá trị nhạy cảm chỉ trong bộ nhớ test và xóa fixtures theo quy định.

## 24. Những tình huống chẩn đoán thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| HTTP 401 dù username/password đúng | Scope không match host, wrong realm/auth scheme, password rotate | Kiểm challenge và origin scope |
| HTTP 407 | Proxy credential không đúng hoặc chưa được cấu hình | Kiểm CONNECT, `Proxy-Authenticate` và proxy scope |
| HTTPS qua proxy nhưng báo 403 | Proxy chặn CONNECT/destination policy | Kiểm allowlist origin/port và proxy audit |
| SSLHandshakeException | CA chain, SAN/hostname, key/cert mTLS, TLS policy | Kiểm certificate chain và trust/key config |
| SocketTimeoutException | Server chậm, proxy, read timeout | Đo kết nối/TLS/response stages |
| Pool timeout dù server khỏe | Pool hết connection hoặc leak | Metrics active/leased/pending |
| SOAP `MustUnderstand` Fault | Header bắt buộc không được xử lý | Kiểm SOAP header/policy, không sửa HTTP password |
| SOAP `Client/Sender` Fault | XML/QName/XSD hoặc SOAP input sai | Kiểm WSDL/XSD/Fault detail |
| `Proxy-Authorization` bị origin nhìn thấy | Header gắn sai tầng/route | Bỏ manual header injection, dùng HTTP proxy auth API |
| Token xuất hiện trong log | HTTP wire debug hoặc exception dump | Redact, revoke/rotate nếu bị lộ |
| Hoạt động direct nhưng fail qua proxy | CONNECT, proxy auth, TLS inspection, header policy | Test riêng từng chặng |
| Chỉ fail sau thời gian idle | Stale pooled connection, proxy keep-alive | Connection eviction/TTL và retry phù hợp |
| Chỉ fail trên CI | Proxy env/NO_PROXY, truststore, DNS, secret injection | So sánh effective config không lộ secrets |

### 24.1. Khi nào cần liên hệ đối tác hoặc bộ phận hạ tầng?

Nếu đã xác minh cấu hình và test nhưng vẫn có 401/407/TLS issues, cần bằng chứng an toàn:

- Timestamp và correlation ID.
- Endpoint hostname/port, proxy hostname/port, route.
- HTTP status và các authentication scheme names đã quan sát.
- Certificate issuer, subject/SAN, validity dates và fingerprint công khai theo policy.
- Tên error category, không phải password/token.
- Environment, Spring-WS/HTTP client version và test case tái hiện.

Không gửi raw Authorization headers, private key hoặc token để “nhờ kiểm giúp”.

## 25. Lựa chọn thiết kế theo mức độ phức tạp

```mermaid
flowchart TD
    A[SOAP client cần HTTP] --> B{Có auth/proxy/pooling phức tạp?}
    B -->|Không| C[Sender cơ bản hoặc JDK]
    B -->|Có| D{Cần custom Apache routing + scopes?}
    D -->|Không| E[JdkHttpClientMessageSender nếu policy hỗ trợ]
    D -->|Có| F[HttpComponents5ClientFactory + SimpleHttpComponents5MessageSender]
    C --> G[HTTPS + contract tests]
    E --> G
    F --> G
    G --> H[Auth 401/407, TLS, Fault và timeout integration tests]
    H --> I[Metrics, rotation, retry/idempotency]
```

Đừng chọn một message sender chỉ vì nó có “timeout” và bỏ qua nhu cầu tách proxy password/origin password. Ngược lại, đừng tự dựng proxy/connection manager cực kỳ phức tạp khi một `JdkHttpClientMessageSender` đơn giản đã đáp ứng chính sách và được test đủ.

## 26. Các anti-pattern cần tránh

### 26.1. Coi `@SoapHeader` là nơi gửi HTTP Basic

Sai tầng: `@SoapHeader` xử lý SOAP Header, còn `Authorization` thuộc HTTP transport.

**Sửa:** cấu hình HTTP client/message sender.

### 26.2. Dùng một credential có scope toàn cầu

Service password có thể bị gửi cho proxy hoặc origin khác nếu auth caching/redirect/routing không kiểm soát.

**Sửa:** scope theo scheme/host/port, tách proxy/origin và tắt redirect không được phê duyệt.

### 26.3. Giấu password trong URI

URI/log có thể làm lộ secret; còn phải đối mặt với parsing, encoding và không tương thích client.

**Sửa:** secret manager + credentials provider.

### 26.4. Tắt TLS verification để vượt lỗi certificate

Có thể chấp nhận server giả và lộ HTTP Basic/Bearer hoặc SOAP payload.

**Sửa:** sửa truststore, keystore, hostname và certificate rotation.

### 26.5. Coi 407 là lỗi SOAP nghiệp vụ

Request có thể chưa tới origin, không có SOAP Envelope phản hồi.

**Sửa:** chẩn đoán proxy authentication ở transport layer.

### 26.6. Bật auto-retry POST không có idempotency

Có thể tạo shipment/thanh toán trùng khi response bị mất sau commit.

**Sửa:** idempotency key, status query, retry policy theo operation.

### 26.7. Thay đổi credentials trên shared template theo từng tenant

Requests song song có thể dùng sai account hoặc gửi thông tin truy cập của tenant này tới origin của tenant khác.

**Sửa:** tách sender/template theo credential profile hoặc dùng request-scoped auth context có kiểm chứng an toàn.

### 26.8. Bật wire logging chứa Authorization/Proxy-Authorization

Credential xuất hiện trong log aggregator, ticket hoặc artifact CI.

**Sửa:** redaction, giới hạn quyền truy cập và thời gian bật debug.

### 26.9. Nghĩ rằng dùng HTTPS đồng nghĩa có mTLS

HTTPS bình thường xác thực server certificate. mTLS chỉ xảy ra khi server yêu cầu và client gửi certificate hợp lệ theo TLS handshake.

**Sửa:** test TLS server yêu cầu client certificate, kiểm key alias và trust chain.

### 26.10. Cấu hình SOAP Security rồi bỏ HTTP authentication

Một đối tác có thể yêu cầu cả Basic ở gateway và chữ ký WS-Security trong SOAP message.

**Sửa:** đọc đầy đủ WSDL/policy, cấu hình từng tầng và test từng lỗi.

## 27. Quy trình triển khai đề xuất

1. **Đọc hợp đồng tích hợp**: WSDL/XSD, SOAP 1.1/1.2 binding, SOAPAction, endpoint URI và security policy.
2. **Khảo sát đường truyền**: direct hay proxy, CONNECT, hostname/port allowlist, TLS inspection, DNS/routing.
3. **Xác định auth cho từng tầng**: origin Basic/Bearer/NTLM/Kerberos, proxy auth, TLS/mTLS và WS-Security.
4. **Phân quyền bí mật**: origin credentials, proxy credentials, private keys và truststore được tách và quản lý qua secret provider.
5. **Chọn message sender**: JDK hoặc Apache HttpClient 5 theo khả năng và version Spring-WS.
6. **Cấu hình scopes**: chỉ định origin và proxy rõ, kiểm redirect và bypass.
7. **Cấu hình TLS**: xác minh hostname, server chain, client certificate và rotation policy.
8. **Cấu hình timeouts/pool**: tính theo SLA và khả năng xử lý của origin/proxy.
9. **Cấu hình WebServiceTemplate**: default URI, sender, JAXB/OXM, SOAPAction, client interceptors.
10. **Viết contract tests**: request/response QName, Fault, WSDL/XSD và XML security.
11. **Viết HTTP integration tests**: 401/403/407, CONNECT, proxy bypass, TLS/mTLS, redirect và token rotation.
12. **Thiết kế lỗi/retry**: phân biệt transport, SOAP Fault, business rejection và unknown outcome; idempotency cho commands.
13. **Triển khai/quan sát**: metrics theo partner/proxy, alerts, logs an toàn và playbook sự cố.
14. **Kiểm thử tương thích với đối tác thật**: Java/JAXB, .NET/ESB, security schemes và certificate renewal.

## 28. Bài tập thực hành

### Bài tập 1 — Xác định tầng authentication

Cho một SOAP request có HTTP Basic, mTLS certificate và WS-Security signature. Phân loại các giá trị nằm ở HTTP, TLS hay SOAP. Giải thích tại sao vượt qua một tầng không thay thế authorization trên `shipmentId`.

### Bài tập 2 — Chạy Basic với scoped credentials

Dùng `HttpComponents5MessageSender` gửi request đến HTTPS test origin có Basic challenge. Cấu hình `new AuthScope(origin)` và `UsernamePasswordCredentials`. Thử đúng/sai mật khẩu, đúng/sai origin host, xác minh client không gửi service password sang host khác.

### Bài tập 3 — Thêm authenticated proxy

Dựng local HTTP CONNECT proxy test có Basic authentication. Dùng `HttpComponents5ClientFactory.withDefaults()` và hai `AuthScope` như mục 8. Thử các trường hợp proxy credential sai và origin credential sai, chứng minh một trường hợp tạo 407, trường hợp kia tạo 401.

### Bài tập 4 — JdkHttpClientMessageSender và ProxySelector

Cấu hình JDK `HttpClient` đi qua proxy không cần auth, với `ProxySelector`, connection timeout và disable redirects. Sau đó thêm test proxy yêu cầu authentication; quan sát hạn chế JDK tunnel auth scheme và đánh giá có nên chuyển sang Apache HttpClient 5 không.

### Bài tập 5 — mTLS và certificate rotation

Dựng HTTPS test server yêu cầu client certificate. Tạo truststore và keystore riêng cho test, dùng `SSLContext` trong `JdkHttpClientMessageSender`. Thử cert đúng, hết hạn và chain không được trust; không tắt hostname verification.

### Bài tập 6 — Bearer token và redirects

Thiết kế token provider có expiry/refresh. Gắn token vào HTTP Authorization cho đúng origin, từ chối redirect sang host khác, và thử nhiều threads cùng gặp token hết hạn. Không ghi token vào logs hoặc metrics.

### Bài tập 7 — Retry sau timeout

Dựng operation `CreateShipment(requestId)` với server commit xong rồi đóng kết nối trước response. Client thấy timeout nhưng không tạo request ID mới; truy vấn theo idempotency key hoặc retry đúng policy để không tạo shipment trùng.

### Bài tập 8 — Vận hành

Viết runbook cho HTTP 401, 407, TLS handshake failure, SOAP `MustUnderstand` Fault và read timeout. Mỗi loại cần xác định owner (đối tác/proxy/PKI/dev), dữ liệu chẩn đoán an toàn và hành động phục hồi.

## 29. Checklist trước khi phát hành

- [ ] Endpoint URI, WSDL/XSD, SOAPAction và SOAP version được lấy từ contract đã công bố.
- [ ] Có sơ đồ đường đi direct/proxy/CONNECT/mTLS theo môi trường.
- [ ] Origin authentication và proxy authentication dùng **hai bộ credentials riêng**.
- [ ] Credential scopes giới hạn đúng scheme/host/port; không dùng `ANY` vô ý.
- [ ] Không có password/token trong URI, source code, plain configuration hoặc log.
- [ ] Chỉ gửi Basic/Bearer tới HTTPS origin được tin; không tắt TLS hostname verification.
- [ ] Nếu proxy auth dùng Basic, đã đánh giá bảo vệ đường truyền tới proxy.
- [ ] Sender phù hợp version Spring-WS/JDK/Apache HttpClient, không trộn Apache 4/5.
- [ ] `HttpComponents5ClientFactory.withDefaults()` hoặc tương đương xử lý SOAP/HTTP headers nhất quán.
- [ ] Proxy routing/bypass và HTTP redirect policy được kiểm thử end-to-end.
- [ ] TLS truststore/keystore, mTLS client certificate và certificate rotation được quản lý rõ.
- [ ] WS-Security signature/token/timestamp được xử lý ở SOAP security stack, không nhầm HTTP Basic.
- [ ] Connection/read/pool acquisition timeouts và SLA được cân bằng.
- [ ] HTTP 401, 403, 407, TLS errors, SOAP Fault và business rejection được phân loại riêng.
- [ ] Retry không tạo tác dụng phụ trùng; commands có idempotency/status query.
- [ ] Credentials và token được rotate mà không mutating shared sender thiếu đồng bộ.
- [ ] Không ghi Authorization/Proxy-Authorization/WS-Security token vào wire logs.
- [ ] Có integration tests với authenticated origin và authenticated proxy thật hoặc harness.
- [ ] Có test TLS/mTLS, certificate chain, redirects, proxy denial và connection pool.
- [ ] Có test Java/JAXB và client stack đối tác nếu hợp đồng yêu cầu.
- [ ] Có metrics, alerts, runbook và owner của proxy/secrets/certificate.

## 30. Tài liệu đối chiếu

- [Spring Web Services 4.1 — Reference, Using Spring-WS on the Client](https://docs.spring.io/spring-ws/docs/4.1.4-SNAPSHOT/reference/html/): `WebServiceTemplate`, message senders và cấu hình client.
- [Spring-WS 4.1 — HttpComponents5MessageSender API](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/transport/http/HttpComponents5MessageSender.html): `setCredentials`, `setAuthScope`, timeout và pool.
- [Spring-WS 4.1 — HttpComponents5ClientFactory API](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/transport/http/HttpComponents5ClientFactory.html): `withDefaults`, custom builder, credentials và HTTP client configuration.
- [Spring-WS 4.1 — SimpleHttpComponents5MessageSender API](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/transport/http/SimpleHttpComponents5MessageSender.html): nhận preconfigured Apache HttpClient 5 hoặc client factory.
- [Spring-WS 4.1 — JdkHttpClientMessageSender API](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/transport/http/JdkHttpClientMessageSender.html): Java `HttpClient`, connect/request timeout.
- [Apache HttpClient 5 — AuthScope API](https://hc.apache.org/httpcomponents-client-5.6.x/current/httpclient5/apidocs/org/apache/hc/client5/http/auth/AuthScope.html): giới hạn thông tin xác thực theo host/scheme/port.
- [IETF RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): `Authorization`, `Proxy-Authorization`, status 401/403/407 và authentication challenges.
- [IETF RFC 7617 — Basic HTTP Authentication](https://www.rfc-editor.org/rfc/rfc7617): định dạng Basic và giới hạn bảo mật.
- [IETF RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer token trong HTTP.
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): lưu trữ, kiểm soát quyền và rotation secrets.

Hãy đối chiếu **phiên bản chính xác** của Spring-WS, Spring Framework, JDK, Apache HttpClient và cấu hình proxy đang chạy. Các ví dụ dùng Java 17+ và Spring-WS 4.1-style APIs để minh họa; chúng không có nghĩa mọi môi trường đều hỗ trợ giống nhau hoặc không cần kiểm thử security policy thực.

## 31. Tổng kết

**Xác thực HTTP và proxy của Spring-WS client thuộc tầng transport, không thuộc JAXB hay SOAP Body.** `WebServiceTemplate` gửi SOAP message qua một `WebServiceMessageSender`; chính HTTP client bên dưới chịu trách nhiệm với `Authorization`, `Proxy-Authorization`, routing, CONNECT, timeout, TLS/mTLS và connection pooling.

Để tích hợp doanh nghiệp ổn định, cần **tách credentials của origin và proxy, giới hạn phạm vi sử dụng theo host/port/scheme, quản lý secrets an toàn, giữ TLS verification và kiểm thử đường truyền thực**. HTTP 401/407 không phải SOAP Fault; TLS handshake error có thể xảy ra trước SOAP; timeout không chứng minh nghiệp vụ chưa commit. Khi hợp đồng còn yêu cầu WS-Security, chữ ký/timestamp/certificate ở SOAP Header phải được xử lý riêng và kiểm thử cùng XSD/WSDL, client JAXB và security policy.

Một cấu hình tốt không chỉ “gọi được SOAP service” mà còn **không gửi nhầm bí mật, không bỏ qua proxy policy, phân loại lỗi đúng, quay vòng credential được và không tạo giao dịch trùng khi retry**.
