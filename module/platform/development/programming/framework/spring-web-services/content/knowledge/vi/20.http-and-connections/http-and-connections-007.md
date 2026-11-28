# HTTPS, xác minh chứng chỉ và xác minh tên máy chủ

> **Chương:** HTTP và kết nối  
> **Module:** SPRING_WEB_SERVICES — phát triển dịch vụ SOAP contract-first bằng Spring Web Services (Spring-WS), thiết kế XSD/WSDL, ánh xạ JAXB, endpoint và SOAP client; vận hành SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích trong tích hợp doanh nghiệp.

## 1. Mục tiêu: kết nối HTTPS đúng, không chỉ “hết lỗi SSL”

Một SOAP client gọi `https://...` cần chứng minh **đang trao đổi với đúng máy chủ đáng tin cậy** trước khi gửi thông tin nghiệp vụ. Gặp lỗi `PKIX path building failed` hoặc `No subject alternative DNS name matching`, cách sửa đúng không phải bỏ qua SSL, bật chế độ “trust all” hoặc tắt hostname verification.

Ba câu hỏi độc lập:

1. **Kết nối có được bảo vệ bằng TLS không?** Hai phía thương lượng phiên bản TLS, cipher suite và khóa phiên phù hợp.
2. **Chứng chỉ máy chủ có đáng tin không?** Java kiểm tra đường dẫn chứng chỉ (certificate path) đến trust anchor, tính hợp lệ và các ràng buộc theo cơ chế PKIX/JSSE được cấu hình.
3. **Chứng chỉ có thuộc về đúng máy chủ mà client muốn gọi không?** Hostname verification so tên DNS/IP của URL với danh tính trong chứng chỉ, chủ yếu qua `subjectAltName` (SAN).

Một certificate chain hợp lệ **không đủ** nếu nó được cấp cho tên máy khác. Và một hostname khớp **không đủ** nếu chuỗi chứng chỉ không được trust.

Sau bài học, bạn có thể:

- Phân biệt `HTTPS`, `TLS handshake`, `PKIX trust validation` và `hostname verification`.
- Đọc đúng `DNS SAN`, `IP SAN`, `SNI`, certificate chain và truststore.
- Cấu hình Spring-WS `WebServiceTemplate` với HTTP sender dùng TLS và JVM truststore.
- Biết khi nào cần truststore riêng, khi nào cần client certificate cho **mTLS**.
- Phân tích lỗi TLS theo tầng mà không vô hiệu hóa bảo mật.
- Kiểm tra kết nối bằng `keytool`, OpenSSL, `curl` và integration test; phân biệt test SOAP mock với test HTTPS thật.
- Giải thích ranh giới HTTPS so với WS-Security, SOAP Fault, certificate rotation và proxy.

## 2. SOAP qua HTTPS nằm trong chuỗi xử lý nào?

Một request contract-first có thể đi qua:

~~~mermaid
flowchart TD
  A["OrderService: Java request DTO"] --> B["JAXB / OXM marshal"]
  B --> C["SOAP Envelope, Body, Header"]
  C --> D["WebServiceTemplate / ClientInterceptor"]
  D --> E["HTTP MessageSender"]
  E --> F["TLS handshake và kiểm tra peer"]
  F --> G["HTTPS qua proxy/load balancer"]
  G --> H["SOAP server"]
  H --> I["SOAP response / Fault"]
  I --> G
  G --> E
  E --> J["Unmarshal, fault handling"]
~~~

Sơ đồ này là hình ảnh khái quát. Thực tế TLS có thể **kết thúc tại reverse proxy/gateway**, và proxy mở một kết nối TLS khác tới backend hoặc chuyển tiếp nội bộ theo thiết kế. Mỗi chặng phải được đánh giá riêng.

### 2.1. Các tầng không nên nhầm

| Tầng | Câu hỏi kiểm chứng | Không thay thế cho |
|---|---|---|
| DNS/TCP | Client đang kết nối tới IP/port nào? | Trust của chứng chỉ |
| TLS/HTTPS | Phiên bảo mật, server authentication, hostname verification | SOAP payload validation |
| HTTP | URL path, Content-Type, SOAPAction, credentials, status code | Xác minh chữ ký WS-Security |
| SOAP | Envelope, Header, Body, SOAP 1.1/1.2 | Kết nối TCP/TLS |
| XSD/WSDL | QName, data types, operations, binding và `soap:address` | Truststore |
| JAXB/OXM | Chuyển Java object ↔ XML | Certificate validation |
| WS-Security | Chữ ký, mã hóa, timestamp/token trên message theo policy | Xác minh TLS peer |
| Business authorization | Principal có quyền gọi operation/truy cập tài nguyên không? | Tên DNS trong SAN |

**Hệ quả chẩn đoán:** nếu TLS handshake thất bại, request thường **chưa tới endpoint SOAP để sinh SOAP Fault**. Chỉnh `@PayloadRoot`, JAXB package hoặc SOAPAction sẽ không chữa lỗi TLS.

## 3. Certificate chain: vì sao “có HTTPS” chưa đủ?

Chứng chỉ X.509 của máy chủ thường chứa public key, thời hạn hiệu lực, issuer, subject, SAN, key usage, extended key usage và chữ ký của CA cấp chứng chỉ. Server thường gửi **leaf certificate** cùng các **intermediate CA certificates** cần thiết; trust anchor (thường root CA) được client tin cậy qua truststore hoặc chính sách trust riêng.

Ví dụ:

~~~text
Client truststore (đã tin cậy)
└── Trusted Root CA
    └── Intermediate CA
        └── Server leaf certificate
            ├── Subject Alternative Name: DNS:soap.partner.example
            ├── Public key
            ├── Validity: notBefore - notAfter
            └── Extended Key Usage: TLS Web Server Authentication
~~~

Ở TLS handshake, Java cần xác minh một **đường dẫn chứng chỉ hợp lệ** tới trust anchor với những ràng buộc của thuật toán/trust policy; nó không chỉ “nhìn thấy một certificate là được”.

### 3.1. Truststore chứa gì?

**Truststore** lưu các certificate/trust anchors mà phía client được phép dùng để xác minh peer. Với Java JSSE, nó thường là JKS hoặc PKCS#12. Nó **không** phải file private key của SOAP server, và không nên bị coi như nơi lưu tất cả certificates gặp trên Internet.

Một truststore chứa public certificate chưa mặc nhiên chứng minh certificate đó đáng tin: phải xác minh nguồn gốc, fingerprint hoặc quy trình phát hành qua kênh độc lập.

### 3.2. Các kiểm tra path validation điển hình

- Certificate chain có đường dẫn tới CA/trust anchor phù hợp.
- Chữ ký trong chain được xác minh và thuật toán/độ dài khóa được phép.
- Chứng chỉ còn hiệu lực theo thời gian kiểm tra (`notBefore`/`notAfter`).
- CA certificates có ràng buộc Basic Constraints/Key Usage phù hợp.
- Leaf certificate phù hợp mục đích TLS server authentication theo chính sách triển khai.
- Các name constraints/policy constraints được áp dụng khi liên quan.
- Revocation (CRL/OCSP) **chỉ được kiểm tra đầy đủ nếu trust policy/runtime được cấu hình tương ứng**; không tự kết luận Java mặc định luôn tra OCSP hoặc luôn soft-fail/hard-fail như mong muốn.

**Hai câu hỏi cuối cùng vẫn khác nhau:** chain có hợp lệ với trust anchor không, và **certificate đó có đúng cho hostname đích không**?

### 3.3. Thiếu intermediate khác với không tin root

Nếu đối tác không gửi intermediate cần thiết, client có thể báo lỗi PKIX dù root CA đã có trong truststore. Tùy JVM/OS/config, một số stack có cơ chế tìm intermediate, nhưng **không dựa vào việc tự tải AIA qua Internet** như chiến lược vận hành.

Giải pháp: yêu cầu đối tác cấu hình server gửi chain đúng; chỉ bổ sung CA/trust anchor vào client khi đã xác minh nguồn và có chính sách tin cậy. Không “import bừa” leaf certificate gặp lỗi để che nguyên nhân.

## 4. Hostname verification: xác minh danh tính trong URL

Giả sử URL SOAP được cấu hình:

~~~text
https://soap.partner.example/services/orders
~~~

Java HTTP client phải so **host `soap.partner.example`** của URL với danh tính DNS được chứng chỉ máy chủ khai báo. Thông thường dùng `subjectAltName`:

~~~text
X509v3 Subject Alternative Name:
    DNS:soap.partner.example
    DNS:api.partner.example
~~~

Một certificate khác chỉ có:

~~~text
DNS:old.partner.example
~~~

có thể có chain hợp lệ, nhưng **không hợp lệ cho `soap.partner.example`**.

### 4.1. SAN và Common Name

Với TLS hiện đại, hãy cấp certificates chứa **SAN đúng**. Không dựa vào Common Name (CN) như phương thức chuẩn thay thế SAN; hành vi fallback CN khác nhau giữa các client/platform và có thể bị loại bỏ.

Ví dụ:

| URL client gọi | SAN trong cert | Kết luận danh tính |
|---|---|---|
| `https://soap.partner.example/ws` | `DNS:soap.partner.example` | Khớp tên |
| `https://soap.partner.example/ws` | `DNS:api.partner.example` | Không khớp |
| `https://127.0.0.1:8443/ws` | `DNS:localhost` | Không khớp IP |
| `https://127.0.0.1:8443/ws` | `IP:127.0.0.1` | Khớp nếu chứng chỉ cũng được trust |
| `https://api.partner.example/ws` | `DNS:*.partner.example` | Có thể khớp theo quy tắc wildcard của verifier |
| `https://partner.example/ws` | `DNS:*.partner.example` | Không phải một subdomain đơn cấp của wildcard |
| `https://a.b.partner.example/ws` | `DNS:*.partner.example` | Thường không khớp vì thêm cấp subdomain |

Bảng giả định trust chain/thời hạn/thuật toán đều tốt và tập trung riêng vào **hostname matching**. Wildcard và IDN/IP literal có những quy tắc chi tiết riêng theo client/TLS implementation; hãy xác minh với runtime thực, không coi wildcard khớp mọi cấp tên.

### 4.2. Hostname là host của URL, không phải path

Với URL `https://soap.partner.example:8443/orders/v1`:

- Tên cần kiểm tra: `soap.partner.example`.
- Cổng `8443` không phải một phần của tên trong SAN.
- Path `/orders/v1` không được so với certificate.
- HTTP `Host` header hoặc SOAP Header không nên được dùng để “đánh lừa” hostname verification nếu URL kết nối tới một host khác.

Nếu team muốn gọi **IP trực tiếp** trong URL, certificate cần có `IP SAN` đúng; cách tốt hơn thường là dùng hostname được cấp certificate hợp lệ và để DNS resolve IP tương ứng.

### 4.3. SNI khác hostname verification

**Server Name Indication (SNI)** là extension TLS cho phép client báo tên server mong muốn trong quá trình handshake, để server/proxy có thể chọn certificate phù hợp khi phục vụ nhiều host.

**Hostname verification** là kiểm tra danh tính certificate đã nhận so với host yêu cầu. Hai cơ chế liên quan nhưng **không giống nhau**:

- SNI sai/vắng có thể khiến gateway trả certificate của virtual host mặc định.
- Hostname verifier sẽ từ chối nếu certificate đó không đúng cho host.
- Sửa `SNI` có thể giúp server chọn đúng certificate, nhưng **không được tắt hostname verification**.
- Gọi bằng IP có thể ảnh hưởng việc gửi SNI, tùy JSSE implementation.

### 4.4. Kết thúc TLS tại reverse proxy

Đường thật có thể là:

~~~text
SOAP client
  └─ HTTPS → api.partner.example (gateway TLS certificate)
                 └─ HTTPS → orders-backend.internal
                    (certificate backend khác)
~~~

Client phía bạn xác minh **certificate của gateway cho `api.partner.example`**. Gateway có trách nhiệm xác minh certificate backend nếu kết nối gateway → backend dùng HTTPS. Một certificate backend hợp lệ cho `orders-backend.internal` **không đủ** cho client ngoài truy cập `api.partner.example`.

Đồng thời cần kiểm tra WSDL `soap:address` công bố URL **có thể truy cập từ bên ngoài**, không để `http://localhost`/internal hostname lộ ra cho client.

## 5. Quy trình handshake và vị trí lỗi trong SOAP

Một mô hình đơn giản:

~~~mermaid
sequenceDiagram
    participant C as Spring-WS SOAP client
    participant T as JSSE/HTTP sender
    participant S as Partner HTTPS endpoint
    C->>T: POST https://soap.partner.example/ws
    T->>S: TLS ClientHello (SNI)
    S-->>T: Certificate chain + TLS handshake data
    T->>T: PKIX chain/trust checks
    T->>T: Hostname verification
    alt TLS xác thực thành công
        T->>S: HTTP POST + SOAP Envelope
        S-->>T: HTTP response + SOAP message/Fault
        T-->>C: Response / fault handling
    else Xác minh thất bại
        T-->>C: TLS/SSL exception
    end
~~~

TLS 1.3 và TLS 1.2 có handshake chi tiết khác nhau; sơ đồ chỉ nhấn mạnh **client không được gửi SOAP data cho peer chưa được xác minh theo policy**. HTTP proxy `CONNECT`, mTLS và session resumption có thể thêm bước riêng.

Một vài dấu hiệu:

- `javax.net.ssl.SSLHandshakeException` với nguyên nhân `PKIX path building failed`: thường ở **chain/trust validation**.
- `No subject alternative DNS name matching ...` hoặc `No name matching ...`: ở **hostname verification**.
- `CertificateExpiredException`: kiểm tra thời hạn.
- `handshake_failure` hoặc `protocol_version`: có thể do TLS/cipher/client cert/algorithm mismatch, không phải lúc nào cũng chứng minh “cert sai”.
- `WebServiceIOException` trong Spring-WS có thể bọc một số exception từ HTTP/TLS transport; phải đọc **root cause** để tìm đúng tầng.

**Không sửa SOAPAction, JAXB, XSD hay endpoint mapping để chữa lỗi trước khi HTTP/SOAP được gửi.**

## 6. Java JSSE và truststore mặc định

Spring-WS không tự xây một bộ xác minh TLS độc lập cho từng SOAP operation. Khi dùng HTTP sender dựa trên JDK `HttpsURLConnection`, cơ chế trust/hostname verification mặc định của **JSSE** được áp dụng theo cấu hình JVM và HTTP stack.

### 6.1. Trường hợp public CA được Java tin cậy

Một SOAP endpoint dùng HTTPS với certificate hợp lệ từ CA đã nằm trong truststore thích hợp của JVM thường **không cần** tạo custom trust manager. Ví dụ client Spring-WS:

~~~java
package com.example.orders.client;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.transport.http.HttpUrlConnectionMessageSender;

@Configuration
public class PartnerSoapClientConfig {

    @Bean
    public Jaxb2Marshaller ordersMarshaller() {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
        marshaller.setContextPath("com.example.orders.contract");
        return marshaller;
    }

    @Bean
    public WebServiceTemplate ordersWebServiceTemplate(
            Jaxb2Marshaller ordersMarshaller) {
        WebServiceTemplate template = new WebServiceTemplate();
        template.setMarshaller(ordersMarshaller);
        template.setUnmarshaller(ordersMarshaller);

        template.setDefaultUri(
            "https://soap.partner.example/services/orders");

        // Ví dụ dùng HTTP sender dựa trên URLConnection của JDK.
        template.setMessageSender(new HttpUrlConnectionMessageSender());
        return template;
    }
}
~~~

Giả định package `com.example.orders.contract` chứa JAXB model được sinh từ XSD, có JAXB API/runtime đúng phiên bản Spring-WS. Việc cấu hình trên **không** sinh chứng chỉ, không tạo WSDL, không bật WS-Security và chưa thiết lập timeout/HTTP authentication.

Trong lựa chọn sender này, hãy giữ **default TLS server trust validation và hostname verification** của JDK. Nếu ứng dụng chuyển sang Apache HttpClient, JDK HttpClient hoặc sender khác, phải xem cấu hình TLS **của chính sender đó**; không tự kết luận mọi HTTP library đều dùng hoàn toàn cùng default SSLContext và hostname verifier.

### 6.2. Gọi SOAP contract-first

Ví dụ Java client (các class JAXB tùy schema thực):

~~~java
GetOrderRequest request = new GetOrderRequest();
request.setOrderId("ORD-1001");

GetOrderResponse response = (GetOrderResponse)
        ordersWebServiceTemplate.marshalSendAndReceive(
            request,
            new SoapActionCallback(
                "urn:example:orders:v1/GetOrder"));

String status = response.getStatus();
~~~

Cần import `org.springframework.ws.soap.client.core.SoapActionCallback` và tiêm bean `ordersWebServiceTemplate`. Mẫu giả định XJC tạo `GetOrderRequest` có root JAXB phù hợp; một schema khác có thể yêu cầu `JAXBElement` từ `ObjectFactory`. SOAPAction phải lấy từ **WSDL binding thực tế**.

Những điều **độc lập**:

- Java HTTP sender mở HTTPS và xác minh peer.
- `SoapActionCallback` đặt SOAPAction trên outgoing SOAP message.
- JAXB marshal Body đúng QName/structure XSD.
- SOAP server xác nhận request SOAP, policy WS-Security và nghiệp vụ.

Nếu host của certificate sai, sửa SOAPAction không có tác dụng. Nếu TLS tốt nhưng request sai XSD, thay truststore không có tác dụng.

### 6.3. JVM dùng truststore nào?

JSSE có cơ chế lựa chọn truststore từ các system properties và cấu hình runtime, thường liên quan `javax.net.ssl.trustStore` và các keystore `jssecacerts`/`cacerts`. Thứ tự/tính khả dụng cụ thể phụ thuộc JDK distribution, phiên bản, security provider và chính sách ứng dụng.

Bạn có thể xác định **runtime Java thật** (khác với JDK được dùng biên dịch) và kiểm tra cấu hình startup. Không đoán rằng truststore của hệ điều hành luôn được Java dùng, hoặc rằng JVM trong container có cùng CA list với laptop.

Một cấu hình cấp **process** có thể dùng:

~~~text
-Djavax.net.ssl.trustStore=/opt/app/security/partners-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

`javax.net.ssl.trustStorePassword` thường cần được cung cấp khi triển khai truststore có mật khẩu, nhưng **không ghi mật khẩu trong tài liệu, source, command history hay log**. Dùng secret-management/deployment mechanism phù hợp, giới hạn quyền đọc file và tránh để secret lộ qua process arguments nếu nền tảng hiển thị command line.

**Cảnh báo:** chỉ định một truststore tùy biến có thể **thay thế** tập trust anchors mặc định của JSSE cho process, không đơn thuần “cộng thêm một CA”. Nếu file mới chỉ chứa CA của đối tác A, các kết nối HTTPS khác trong cùng JVM có thể không còn trust những public CAs trước đây. Hãy thiết kế policy/tập anchors có chủ đích hoặc dùng SSLContext riêng theo đối tác.

### 6.4. Không thay truststore trong lúc request chạy

Thay `System.setProperty("javax.net.ssl.trustStore", ...)` sau khi SSLContext/connection pool đã khởi tạo có thể không làm thay đổi các TLS connections đang dùng hoặc default context đã được cache. Không viết logic đổi global truststore theo từng request trong ứng dụng đa luồng: request A và B có thể bị ảnh hưởng chéo.

Nếu cần trust policy khác nhau theo đối tác:

- Tạo **HTTP message sender hoặc HTTP client riêng** được cấu hình SSLContext cho từng đối tác.
- Gắn đúng sender vào từng `WebServiceTemplate`.
- Giữ hostname verification bật và certificate policy riêng.
- Kiểm tra pool connection reuse, rotation/reload và đóng tài nguyên.
- Không sửa global `HttpsURLConnection.setDefaultSSLSocketFactory(...)` hay `setDefaultHostnameVerifier(...)` trong ứng dụng đa client nếu không có kiểm soát phạm vi.

## 7. Tạo truststore từ CA đã xác minh

Một đối tác nội bộ có thể dùng private CA chưa có trong JVM default truststore. Giải pháp đúng là **import CA/trust anchor đã được xác minh và phê duyệt**, không bỏ qua kiểm tra TLS.

### 7.1. Lấy và kiểm chứng chứng chỉ ngoài băng

Đối tác nên cung cấp root/intermediate CA qua kênh chính thức và **SHA-256 fingerprint** qua một kênh tin cậy độc lập. Trước khi import, kiểm tra nội dung:

~~~bash
keytool -printcert -file partner-root-ca.pem -v
~~~

Hoặc với OpenSSL:

~~~bash
openssl x509 -in partner-root-ca.pem -noout -subject -issuer -dates -fingerprint -sha256
~~~

Cần xác minh với đơn vị quản trị CA rằng certificate đúng issuer/subject, fingerprint và mục đích. Lệnh in fingerprint **chỉ giúp đối chiếu**; một fingerprint tải từ cùng website không tin cậy với certificate không tạo được trust mới.

### 7.2. Import trust anchor vào PKCS#12

Ví dụ để hệ thống nhắc nhập mật khẩu thay vì ghi trên command line:

~~~bash
keytool -importcert \
  -alias partner-approved-root \
  -file partner-root-ca.pem \
  -keystore partner-truststore.p12 \
  -storetype PKCS12
~~~

Kiểm tra lại:

~~~bash
keytool -list -v \
  -keystore partner-truststore.p12 \
  -storetype PKCS12
~~~

`keytool` có thể nhắc xác nhận import và mật khẩu. Chỉ xác nhận sau khi đã kiểm tra fingerprint/policy. Nếu certificate đối tác là leaf tự ký trong môi trường test, có thể tin cậy nó như anchor ở **phạm vi test hẹp**, nhưng production nên có chính sách CA/rotation rõ ràng.

Không import **mọi leaf certificate** mà máy chủ đưa ra để “fix PKIX”. Cách làm này dễ biến truststore thành danh sách ngoại lệ không được review, gây khó khăn lúc rotation và có thể tin nhầm peer.

### 7.3. Root vs intermediate vs leaf

| Đối tượng | Công dụng | Lưu ý |
|---|---|---|
| Root CA trust anchor | Điểm kết thúc đường dẫn trust | Phải được tổ chức phê duyệt, bảo vệ integrity |
| Intermediate CA | Liên kết giữa leaf và root; thường server phải gửi | Thiếu intermediate gây path building fail |
| Leaf server certificate | Danh tính service HTTPS, chứa SAN | Thường được rotate ngắn hạn |
| Certificate pinning | Giới hạn peer/key cụ thể hơn trust CA thường | Có chi phí rotation/failover; không triển khai ngẫu hứng |
| Client certificate (mTLS) | Chứng minh danh tính **client** trước server | Nằm với private key ở keystore phía client |

**Không dùng cùng một từ “certificate” cho tất cả vai trò.** Một lỗi `PKIX` cần kiểm tra path/trust; lỗi hostname mismatch cần sửa certificate SAN/URL; mTLS yêu cầu key material phía client, là một chuyện khác.

## 8. SSLContext riêng: truststore không làm mất hostname verification

Khi phải xây TLS context riêng cho một đối tác, API chuẩn JSSE có thể nạp `KeyStore` và `TrustManagerFactory` rồi tạo `SSLContext`.

### 8.1. Tạo SSLContext từ truststore tin cậy

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.GeneralSecurityException;
import java.security.KeyStore;
import java.security.SecureRandom;

import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public final class PartnerTlsContexts {
    private PartnerTlsContexts() {}

    public static SSLContext createServerTrustContext(
            Path trustStorePath, char[] storePassword)
            throws IOException, GeneralSecurityException {

        KeyStore trustStore = KeyStore.getInstance("PKCS12");

        try (InputStream in = Files.newInputStream(trustStorePath)) {
            trustStore.load(in, storePassword);
        }

        TrustManagerFactory trustManagers =
                TrustManagerFactory.getInstance(
                    TrustManagerFactory.getDefaultAlgorithm());
        trustManagers.init(trustStore);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(
                null,
                trustManagers.getTrustManagers(),
                new SecureRandom());

        return context;
    }
}
~~~

Code trên tạo SSLContext dùng các trust anchors trong file PKCS#12. `storePassword` được nhận qua `char[]`, nhưng caller cần lấy secret từ nguồn bảo mật, làm sạch `char[]` khi không còn dùng và quản lý quyền đọc truststore file. Không truyền password dưới dạng string literal trong source code.

**Ranh giới cực kỳ quan trọng:** `SSLContext` và `TrustManagerFactory` giải quyết **trust/path validation**. Chúng **không tự chứng minh HTTP sender sẽ thực hiện hostname verification đúng**. Khi gắn context vào HTTP client/message sender, bạn vẫn phải giữ endpoint identity checking của sender.

Đoạn code chỉ tạo context; nó **chưa kết nối** `SSLContext` với `HttpUrlConnectionMessageSender`. Cách inject SSLContext, SSL socket factory và hostname verifier là **API tùy implementation/version**. Không được suy đoán `new HttpUrlConnectionMessageSender(sslContext)` tồn tại. Với Apache HttpClient-based sender, dùng chính builder TLS của HttpClient version đang chạy, cấu hình cả trust strategy lẫn hostname verifier.

### 8.2. Kiểm tra hostname khi tự dùng raw SSLSocket

Đối với một `SSLSocket` cấp thấp, hostname verification **không được giả định tự bật**. Java cho phép cấu hình:

~~~java
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocket;

// sslContext là context đã tạo từ trust anchors được phê duyệt.
String hostname = "soap.partner.example";

try (SSLSocket socket = (SSLSocket)
        sslContext.getSocketFactory().createSocket(hostname, 443)) {

    SSLParameters params = socket.getSSLParameters();
    params.setEndpointIdentificationAlgorithm("HTTPS");
    socket.setSSLParameters(params);

    socket.startHandshake();
    // Chỉ tiếp tục trao đổi protocol sau khi handshake hợp lệ.
}
~~~

Đây là **ví dụ JSSE cấp thấp**, không phải SOAP client hoàn chỉnh. Với sender dựa trên `HttpsURLConnection`, hostname verification thông thường đã được HTTP client cung cấp; **không** tự thay bằng `HostnameVerifier` chấp nhận mọi tên. Khi có SNI/virtual hosting, đảm bảo kết nối được tạo với đúng hostname thay vì IP hoặc tên giả.

### 8.3. Sự khác biệt giữa default trust và partner-specific trust

Nếu tách SSLContext riêng cho đối tác, hệ thống cần xác định:

1. Các CA nào được trust **chỉ** cho đối tác này?
2. Có cần giữ public roots mặc định ngoài private CA không?
3. Các HTTP redirects, DNS aliases hoặc failover hosts nào được phép?
4. Mỗi host mới có SAN phù hợp không?
5. Khi certificate/CA rotate, context hoặc pooled connections có được reload đúng không?
6. Có bị trộn secret/certificate của hai đối tác trong cùng một message sender không?

Không kết hợp trust managers bằng chiến lược “nếu bất kỳ trust manager nào nhận là được” mà không review chính sách; thay đổi như vậy mở rộng tập peer được tin cậy.

## 9. Mutual TLS (mTLS): client cũng trình chứng chỉ

Ở HTTPS thông thường, client xác minh **server**. Với **mTLS**, server còn yêu cầu client chứng minh danh tính bằng **client certificate và private key** trong handshake.

~~~mermaid
flowchart LR
  A["SOAP client"] -->|"Server certificate + hostname verification"| B["HTTPS server"]
  B -->|"Yêu cầu client certificate"| A
  A -->|"Client certificate + proof of private key"| B
  B -->|"Server validates client chain/policy"| C["SOAP endpoint"]
~~~

### 9.1. Keystore và truststore khác nhiệm vụ

| Ở client Spring-WS | Chứa gì | Mục đích |
|---|---|---|
| **Truststore** | Approved CA/trust anchors để xác minh server | Client kiểm tra server HTTPS |
| **Keystore** | Client private key và certificate chain | Client trình danh tính khi server yêu cầu mTLS |
| **WSS4J signing keystore** | Khóa/chứng chỉ dùng ký SOAP message | WS-Security message signature, có thể khác mTLS key |
| **TLS session** | Keys thương lượng trong handshake | Mã hóa traffic, không phải nơi lưu key ứng dụng |

`javax.net.ssl.keyStore` và `javax.net.ssl.trustStore` không phải hai tên tương đương. Cần phân biệt passwords, vị trí file, loại keystore và rotation.

Ví dụ cấu hình **process-wide** về mặt ý tưởng:

~~~text
-Djavax.net.ssl.keyStore=/opt/app/security/client-identity.p12
-Djavax.net.ssl.keyStoreType=PKCS12

-Djavax.net.ssl.trustStore=/opt/app/security/partner-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

Các password cần được nạp qua secret-management của deployment; tránh hiện trong source, log, command history hoặc process list. Trong môi trường nhiều đối tác, ưu tiên client-specific TLS settings thay vì dùng một identity cho mọi outbound connection.

### 9.2. Tạo SSLContext dùng cả client key và trust anchors

~~~java
import java.security.KeyStore;
import java.security.SecureRandom;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

// Đã nạp clientIdentity và approvedServerTrust vào KeyStore
// từ các nguồn được quản lý an toàn.
KeyManagerFactory kmf =
        KeyManagerFactory.getInstance(
            KeyManagerFactory.getDefaultAlgorithm());
kmf.init(clientIdentity, clientKeyPassword);

TrustManagerFactory tmf =
        TrustManagerFactory.getInstance(
            TrustManagerFactory.getDefaultAlgorithm());
tmf.init(approvedServerTrust);

SSLContext mTlsContext = SSLContext.getInstance("TLS");
mTlsContext.init(
        kmf.getKeyManagers(),
        tmf.getTrustManagers(),
        new SecureRandom());
~~~

Đây là **mảnh mã**: `clientIdentity`, `approvedServerTrust` và `clientKeyPassword` phải được khởi tạo bởi cấu hình an toàn trong ứng dụng. Để thực sự áp dụng mTLS, HTTP sender phải sử dụng `mTlsContext` và **giữ hostname verification bật**. Phía server cũng cần trust client certificate chain và cấu hình client-auth phù hợp. Không chỉ thêm keystore vào project mà kỳ vọng server tự yêu cầu chứng chỉ.

### 9.3. mTLS không tự cấp quyền nghiệp vụ

mTLS chứng minh bên client sở hữu khóa riêng tương ứng certificate được server chấp nhận. Nó **không tự quyết định** request đó được phép sửa đơn hàng nào; phải có cơ chế mapping identity → principal/role và authorization. Đồng thời, nếu WSDL/WS-SecurityPolicy yêu cầu chữ ký SOAP, mTLS **không thay thế** chữ ký ở mức message.

## 10. Những cấu hình “sửa nhanh SSL” tuyệt đối nên tránh

### 10.1. Trust-all TrustManager

~~~java
// PHẢN VÍ DỤ — KHÔNG SỬ DỤNG:
X509TrustManager insecure = new X509TrustManager() {
    public void checkClientTrusted(
            X509Certificate[] chain, String authType) {}
    public void checkServerTrusted(
            X509Certificate[] chain, String authType) {}
    public X509Certificate[] getAcceptedIssuers() {
        return new X509Certificate[0];
    }
};
~~~

Đây là anti-pattern: `checkServerTrusted` không xác minh chain; bất kỳ máy chủ nào có thể được coi là hợp lệ, tạo điều kiện cho machine-in-the-middle. Mục đích minh họa lỗi, không phải code triển khai; không cấu hình vào `SSLContext`.

### 10.2. HostnameVerifier luôn true

~~~java
// PHẢN VÍ DỤ — KHÔNG SỬ DỤNG:
HostnameVerifier insecureVerifier =
        (hostname, session) -> true;
~~~

Dù trust chain hợp lệ, certificate của một server khác có thể bị chấp nhận cho URL mà client định gọi. Điều này phá bước gắn **chứng chỉ với đúng host**.

### 10.3. Tắt verify trong công cụ chẩn đoán

Các tùy chọn như `curl -k` hoặc `--insecure` bỏ qua certificate verification nên **không dùng làm bằng chứng kết nối production an toàn**. Nếu test một endpoint dùng private CA, hãy cung cấp CA đúng bằng `--cacert` hoặc truststore phù hợp; nếu certificate thiếu SAN, sửa certificate hoặc URL, không tắt verifier.

### 10.4. Bỏ qua TLS vì “chúng ta còn WS-Security”

WS-Security có thể ký/mã hóa một số parts theo policy nhưng không mặc nhiên che tất cả HTTP metadata, URLs, chứng chỉ, các headers không mã hóa hay attachments. TLS và WS-Security có phạm vi khác nhau; hệ thống enterprise thường yêu cầu cả hai. Không dùng chữ ký SOAP như lý do bỏ HTTPS/hostname verification.

## 11. Bộ công cụ chẩn đoán chứng chỉ và HTTPS

Không cần tự sửa ứng dụng ngay khi gặp `SSLHandshakeException`. Trước hết thu thập những bằng chứng có thể tái lập trong **môi trường được phép**, không đưa certificate/key secrets vào log công khai.

### 11.1. Xem certificate do server thực sự gửi

OpenSSL có thể truy vấn endpoint và yêu cầu đúng SNI:

~~~bash
openssl s_client \
  -connect soap.partner.example:443 \
  -servername soap.partner.example \
  -showcerts
~~~

Lệnh giúp quan sát chain đã trình ra, issuer, subject và một số thông tin TLS. Tuy nhiên, **chỉ có `-showcerts` không đủ để xác nhận trust và hostname**. Kiểm tra đầy đủ hơn với một CA bundle tin cậy:

~~~bash
openssl s_client \
  -connect soap.partner.example:443 \
  -servername soap.partner.example \
  -verify_hostname soap.partner.example \
  -verify_return_error \
  -CAfile partner-approved-ca.pem
~~~

`partner-approved-ca.pem` phải là CA/trust bundle **đã xác minh nguồn**, không phải file tùy ý tải từ chính server đang kiểm tra. Kiểm tra output verify code và lỗi thực tế. Việc OpenSSL chấp nhận certificate **không chứng minh Java sẽ chấp nhận**, vì OpenSSL và JVM có thể có tập CAs, thuật toán và policy khác nhau.

Nếu endpoint dùng mTLS, lệnh OpenSSL có thể cần thêm **client certificate/key test** do đối tác cấp. Không thử private key production bằng lệnh ghi vào terminal history hoặc trong môi trường không được kiểm soát.

### 11.2. Xem certificate từ file

~~~bash
keytool -printcert -v -file server-cert.pem
~~~

Với OpenSSL:

~~~bash
openssl x509 \
  -in server-cert.pem \
  -noout -subject -issuer -dates -ext subjectAltName
~~~

Lưu ý:

- `Subject` hoặc `CN` không thay thế SAN.
- `Issuer` chỉ là tên nhà cấp; phải xác minh **đường dẫn chữ ký** đến trust anchor.
- `Not Before`/`Not After` phụ thuộc thời gian và đồng hồ hệ thống.
- Một certificate xuất hiện trong output chưa chứng minh private key tương ứng thuộc về endpoint đúng; TLS handshake xác nhận quyền sở hữu khóa theo protocol.

### 11.3. Dùng curl với CA được phê duyệt

~~~bash
curl -v \
  --cacert partner-approved-ca.pem \
  https://soap.partner.example/services/orders.wsdl
~~~

Lệnh này giúp xem HTTPS và WSDL URL với một trust source chỉ định. `curl` có thể dùng OpenSSL, Schannel hoặc TLS backend khác tùy máy; một lần GET WSDL thành công chưa chứng minh JVM trong production dùng cùng truststore/policy.

Khi cần kết nối tới **một IP định trước** trong test DNS mà vẫn kiểm tra hostname và SNI theo URL:

~~~bash
curl -v \
  --cacert partner-approved-ca.pem \
  --resolve soap.partner.example:443:203.0.113.10 \
  https://soap.partner.example/services/orders.wsdl
~~~

`203.0.113.10` thuộc dải IP dành cho tài liệu minh họa, không phải server thực. `--resolve` hữu ích ở môi trường test vì URL vẫn chứa `soap.partner.example` — danh tính certificate vẫn được kiểm tra theo hostname đó. Nó **khác** với đổi URL thành `https://203.0.113.10` rồi tắt hostname verifier.

### 11.4. Bật debug JSSE đúng lúc

Với JVM có hỗ trợ, các thuộc tính sau giúp xem handshake và xây chứng chỉ:

~~~text
-Djavax.net.debug=ssl,handshake
-Djava.security.debug=certpath
~~~

Bật **tạm thời trong môi trường được kiểm soát**, có chính sách lưu/xóa log và redaction phù hợp. Debug TLS có thể ghi nhiều certificate details và metadata kết nối; tránh bật đại trà trong production, nhất là với tải lớn.

Khi đọc log:

1. Xác nhận hostname/port thực tế và SNI.
2. Xem certificate chain server đã trình.
3. Tìm trust anchor, lỗi build path hoặc algorithm constraints.
4. Tìm hostname/SAN mismatch.
5. Nếu mTLS, xác minh server có yêu cầu client cert và Java có chọn identity phù hợp.
6. Đối chiếu thời gian hệ thống, proxy và truststore của **JVM đang chạy**, không chỉ laptop.

Đừng chia sẻ raw logs chứa đường dẫn key material, certificate nội bộ, token hoặc thông tin nhạy cảm mà chưa loại bỏ dữ liệu không cần thiết.

## 12. Bảng chẩn đoán lỗi HTTPS cho SOAP client

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý an toàn |
|---|---|---|
| `PKIX path building failed` / `unable to find valid certification path` | Root không được trust, thiếu intermediate, truststore không đúng, path constraints | Kiểm tra chain/SNI; xác minh và bổ sung CA phù hợp, sửa server gửi intermediates |
| `No subject alternative DNS name matching...` | URL hostname không nằm trong DNS SAN | Sửa URL hoặc certificate SAN; không tắt hostname verification |
| `No subject alternative names present` | Certificate không có SAN phù hợp | Cấp/reissue cert có SAN đúng |
| `No subject alternative IP address matching...` | Dùng IP URL nhưng certificate không có IP SAN | Dùng DNS URL có DNS SAN hoặc cấp IP SAN nếu bắt buộc |
| `CertificateExpiredException` | Leaf hoặc certificate trong path đã hết hạn | Gia hạn/rotate chain phù hợp, cập nhật trust/monitoring |
| `CertificateNotYetValidException` | Cert chưa có hiệu lực hoặc đồng hồ sai | Kiểm tra clock/NTP và certificate validity |
| `Algorithm constraints check failed` | Key size/signature algorithm bị policy cấm | Cấp cert/key theo chính sách hiện hành; không tắt constraints |
| TLS `protocol_version` | Peer và client không thống nhất TLS version | Kiểm tra TLS support, nâng stack/cấu hình cả hai phía theo policy |
| `handshake_failure` | Có thể do cipher/protocol, mTLS/client cert, SNI hoặc policy khác | Xem TLS debug và server logs; không kết luận theo một chữ “handshake” |
| `bad_certificate` / `certificate_required` | Server từ chối hoặc yêu cầu client cert | Kiểm tra mTLS keystore, alias, chain, key usage và server trust |
| `HTTP 401/403` sau TLS | Kết nối HTTPS đã qua; auth HTTP/business bị từ chối | Kiểm tra credentials, authorization/WS-Security; đừng sửa truststore vô cớ |
| `HTTP 404` cho WSDL/SOAP URL | Path/servlet/proxy sai, không còn là lỗi chain | So WSDL address, gateway route và context path |
| SOAP Fault sau POST | SOAP/XSD/WS-Security/business error | Phân tích SOAP Fault và contract, không suy ra TLS lỗi |
| `SSLPeerUnverifiedException` | Peer identity chưa được xác thực trong TLS session hoặc hostname check fail | Xem chính sách peer/auth, root cause |
| Chạy laptop, fail trong container | JDK CA bundle/truststore, clock, DNS/SNI hoặc proxy khác | Kiểm tra chính container/JVM, không lấy kết luận từ máy dev |
| Chỉ fail sau cert rotation | Leaf/chain/SAN/CA thay, pool/cache hoặc pinning cũ | So cert mới, trust anchors, reload contexts/pools có kiểm soát |

Một số message có thể khác nhau theo Java version, JSSE provider và HTTP sender. `WebServiceTemplate` có thể bọc lỗi transport thành Spring-WS exception; luôn nhìn vào **root cause chain**.

### 12.1. Quy trình điều tra theo thứ tự

~~~mermaid
flowchart TD
  A["SOAP call thất bại"] --> B{"Đã hoàn thành TLS handshake?"}
  B -->|"Chưa"| C{"PKIX/path validation?"}
  C -->|"Có"| D["Kiểm tra root/intermediate/truststore/time"]
  C -->|"Không"| E{"Hostname / SAN mismatch?"}
  E -->|"Có"| F["Sửa DNS URL hoặc certificate SAN"]
  E -->|"Không"| G["SNI, TLS version/ciphers, mTLS, proxy"]
  B -->|"Rồi"| H{"HTTP response?"}
  H -->|"401/403/404"| I["HTTP authentication, path, gateway"]
  H -->|"SOAP Fault"| J["SOAPAction, QName, XSD, WS-Security"]
  H -->|"SOAP response"| K["JAXB/XSD/unmarshal, business result"]
~~~

Quy trình này giúp tránh “sửa ngược tầng”: thay XML namespace khi certificate sai hoặc thêm CA mới khi service trả SOAP Fault hợp lệ.

## 13. Bài lab: chứng chỉ test đúng SAN và hostname mismatch

Một lab có giá trị phải chứng minh **hai kết quả**: cùng một server/certificate được chấp nhận với hostname đúng và bị từ chối với hostname không khớp, **dù truststore tin cậy certificate đó**.

### 13.1. Tạo certificate tự ký chỉ để test

Dùng `keytool` tạo keystore chứa private key/certificate cho server HTTPS cục bộ:

~~~bash
keytool -genkeypair \
  -alias local-soap-server \
  -keyalg RSA \
  -keysize 2048 \
  -validity 14 \
  -dname "CN=localhost" \
  -ext "SAN=dns:localhost" \
  -keystore local-soap-server.p12 \
  -storetype PKCS12
~~~

Lệnh này tạo một **certificate test ngắn hạn**, chỉ có DNS SAN `localhost` (không có IP SAN `127.0.0.1`). `keytool` sẽ yêu cầu mật khẩu phù hợp; không dùng mật khẩu production trong lab.

Xuất public cert để test client tin cậy nó:

~~~bash
keytool -exportcert \
  -alias local-soap-server \
  -keystore local-soap-server.p12 \
  -storetype PKCS12 \
  -rfc \
  -file local-soap-server.pem
~~~

Import vào truststore test:

~~~bash
keytool -importcert \
  -alias local-soap-server-test \
  -file local-soap-server.pem \
  -keystore local-client-trust.p12 \
  -storetype PKCS12
~~~

Kết quả chỉ phù hợp **môi trường thử nghiệm**. Tin cậy leaf tự ký như anchor cho lab không phải cách tự động phù hợp với quản lý certificates production.

### 13.2. Chạy một HTTPS test server

Cần một HTTPS server cục bộ thực sự sử dụng `local-soap-server.p12` tại cổng `8443`. Nếu đó là một ứng dụng Spring Boot test, có thể cấu hình dạng:

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: file:/path/to/local-soap-server.p12
    key-store-type: PKCS12
    key-store-password: ${TEST_TLS_KEYSTORE_PASSWORD}
~~~

Đoạn YAML là **mẫu lab**, không tạo ứng dụng server trong bài này. Cần cung cấp biến môi trường `TEST_TLS_KEYSTORE_PASSWORD` qua cơ chế test secret an toàn và chỉnh path thực. Nếu ứng dụng SOAP được map ở `/ws/*`, URL test có thể là `https://localhost:8443/ws`.

Một server không cần xử lý SOAP nghiệp vụ mới kiểm tra được TLS, nhưng để kiểm tra **cả SOAP**, phải có `MessageDispatcherServlet` và endpoint/WSDL tương ứng.

### 13.3. Hai phép thử bắt buộc

**Trường hợp đúng hostname:**

~~~text
https://localhost:8443/ws
~~~

Nếu client tin certificate test, chain/time/policy phù hợp, hostname verification sẽ thấy `DNS:localhost` và có thể chấp nhận.

**Trường hợp sai hostname:**

~~~text
https://127.0.0.1:8443/ws
~~~

Certificate chỉ chứa `DNS:localhost`, không chứa `IP:127.0.0.1`. Một client có hostname verification đúng phải **từ chối** kết nối IP này, dù truststore đã tin certificate.

Nếu cả hai đường đều thành công trong lab với cùng certificate, cần kiểm tra liệu bạn đã vô tình tắt hostname verification hoặc dùng client library có configuration không an toàn hay không. Đối với TLS policy thực, vẫn phải xét certificate chain và hostname theo sender, không chỉ kết quả một HTTP status.

### 13.4. Test bằng curl

~~~bash
curl -v \
  --cacert local-soap-server.pem \
  https://localhost:8443/ws
~~~

Và:

~~~bash
curl -v \
  --cacert local-soap-server.pem \
  https://127.0.0.1:8443/ws
~~~

Cả hai đều có thể trả HTTP 404/405 sau TLS nếu server không phục vụ GET `/ws`; điều quan trọng của lab là **phân biệt TLS verification success với HTTP application status**. Lệnh thứ hai phải fail ở certificate name matching khi curl có TLS verification bật. Sau đó chạy lại bằng chính Java HTTP sender của Spring-WS để so hành vi JSSE.

### 13.5. Test mock chưa đủ

`MockWebServiceServer` rất hữu ích để kiểm tra SOAP Body, SOAPAction, header và response của `WebServiceTemplate`. Tuy nhiên, nó thường **không mở TCP/TLS connection thật**; một test mock thành công không chứng minh truststore, certificate chain, hostname verification, proxy hoặc mTLS đúng.

Hãy có **ít nhất một integration test qua HTTPS thật** với test server/CA và các ca âm tính (wrong CA, wrong host, expired certificate khi thiết kế fixture), bên cạnh test SOAP payload thông thường.

## 14. Proxy, DNS, redirect, timeout và certificate rotation

### 14.1. Proxy HTTP CONNECT và TLS interception

Một SOAP client doanh nghiệp có thể đi qua corporate proxy:

~~~text
Spring-WS client → HTTP CONNECT proxy → TLS với partner host
~~~

Khi proxy chỉ tunnel, TLS peer identity vẫn phải khớp hostname URL đích. Nếu proxy thực hiện **TLS interception** và cấp lại certificate bằng CA nội bộ, client sẽ thấy một chain khác. Việc thêm corporate CA vào truststore là một **quyết định security/policy cần được phê duyệt**, không phải bước khắc phục tự động.

Đặc biệt với WS-Security, proxy/gateway có thể quan sát HTTP metadata nhưng **không được sửa các signed SOAP parts** nếu không có cơ chế trusted transformation/resigning hợp lệ.

### 14.2. DNS, SNI và nhiều IP backend

DNS có thể trả nhiều địa chỉ cho một hostname. Dù kết nối tới IP A hay B, TLS certificate của endpoint mà client nhận vẫn cần hợp lệ cho `soap.partner.example`. SNI có thể quyết định certificate phù hợp ở load balancer.

Nếu chỉ một backend bị hostname mismatch, hãy thử kết nối qua từng IP với **cùng hostname URL/SNI** bằng kỹ thuật `curl --resolve` trong môi trường test. Không tự thay URL thành IP rồi tắt verify để bỏ qua lỗi failover.

### 14.3. Redirects: đừng để mất trust boundary

WSDL URL có thể redirect; SOAP POST cũng có thể nhận redirect, nhưng xử lý follow redirect với POST/body/credentials tùy HTTP client. Quy tắc an toàn:

- Cho phép redirects chỉ khi business protocol và sender đã hỗ trợ rõ.
- Không tự follow từ `https://` xuống `http://` với request nhạy cảm.
- Kiểm tra hostname/certificate **cho mỗi HTTPS destination mới**.
- Không chuyển Basic auth, bearer token hoặc mTLS identity sang host khác khi chưa được phép.
- Không tải WSDL/XSD từ URL do untrusted SOAP input chỉ định (SSRF).
- Capture actual redirected URL trong test, không chỉ nhìn URL ban đầu.

### 14.4. Timeout xảy ra ở tầng nào?

| Loại timeout | Ý nghĩa |
|---|---|
| TCP connect timeout | Không thiết lập được kết nối mạng trong giới hạn |
| TLS handshake timeout | Handshake/certificate exchange không hoàn tất kịp thời, tùy sender có riêng setting hay nằm trong connect/read timeout |
| HTTP read/socket timeout | Đợi bytes response quá lâu |
| SOAP/application timeout | Business operation hoặc hệ thống phía đối tác chậm |
| Connection pool timeout | Không lấy được connection từ pool trong giới hạn |

Cấu hình API timeout cụ thể phụ thuộc `HttpUrlConnectionMessageSender`, HttpComponents sender và phiên bản Spring-WS/HTTP client. Không tự giả định chỉ đặt một “read timeout” là giới hạn **toàn bộ** request từ bắt đầu tới kết thúc. Sau timeout, đối tác có thể đã xử lý nghiệp vụ; retry cần xét idempotency.

### 14.5. Rotation và certificate expiration

Certificate server có thể được gia hạn/đổi CA trước khi hết hạn. Quy trình vận hành cần:

1. Theo dõi expiry của certificate **thực đang phục vụ** trên mọi gateway/backend.
2. Xác nhận SAN và chain của certificate mới.
3. Nếu đổi root/intermediate CA, chuẩn bị truststore update/overlap window có kiểm soát.
4. Nếu pin leaf/public key, lập kế hoạch rotation cụ thể — pinning sai dễ gây outage.
5. Reload/recreate client SSLContexts hoặc connection pools khi cần theo implementation.
6. Kiểm tra failover regions/URLs và client JVM/container images mới.
7. Thử cả mTLS client identity rotation và SOAP WS-Security signing certificate nếu các khóa khác nhau.
8. Tài liệu hóa rollback và alert khi còn ít ngày đến expiry.

Không chờ certificate hết hạn mới import CA mới. Nhưng cũng không giữ mãi các trust anchors đã thu hồi hoặc không còn được phép tin cậy.

## 15. Kiểm thử HTTPS bằng Java và Spring-WS

### 15.1. Test TLS handshake với HttpsURLConnection

Dùng Java để xác minh **chính JSSE** trong ứng dụng, thay vì chỉ dựa vào kết quả OpenSSL trên máy khác. Ví dụ helper dưới đây dùng một `SSLContext` đã được cấu hình với **trust anchors của lab** rồi giữ **hostname verifier mặc định** của `HttpsURLConnection`:

~~~java
import java.io.IOException;
import java.net.URL;
import javax.net.ssl.HttpsURLConnection;
import javax.net.ssl.SSLContext;

public final class TlsProbe {

    private TlsProbe() {}

    public static String verifyConnection(
            String httpsUrl, SSLContext sslContext)
            throws IOException {

        HttpsURLConnection connection =
                (HttpsURLConnection) new URL(httpsUrl)
                        .openConnection();

        connection.setSSLSocketFactory(
                sslContext.getSocketFactory());
        // KHÔNG đặt HostnameVerifier = (host, session) -> true.

        connection.setConnectTimeout(3000);
        connection.setReadTimeout(3000);

        try {
            connection.connect(); // Kích hoạt kết nối/handshake TLS.
            return connection.getCipherSuite();
        } finally {
            connection.disconnect();
        }
    }
}
~~~

Điểm quan trọng:

- `setSSLSocketFactory(...)` giới hạn SSLContext cho **connection này**, không gọi `SSLContext.setDefault(...)` toàn JVM.
- `HttpsURLConnection` bình thường thực hiện hostname verification, miễn ứng dụng không bị cấu hình override không an toàn ở nơi khác.
- Chỉ lấy cipher suite sau handshake **không chứng minh SOAP payload hợp lệ**, nhưng kết nối TLS được thiết lập với peer qua chính JSSE.
- Đây là probe dành cho integration test. Trong SOAP client thực, hãy cấu hình **message sender** sử dụng SSLContext theo API của sender.
- Việc tạo URL từ input chưa tin cậy là một rủi ro SSRF; trong production, endpoint URL phải lấy từ allowlist/cấu hình đã duyệt.

### 15.2. Ma trận kiểm thử danh tính

Khi lab ở mục 13 đang phục vụ HTTPS từ cert `DNS:localhost`, ta muốn kiểm tra:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLException;
import org.junit.jupiter.api.Test;

class SoapTlsIdentityTest {

    // testTrustContext() dùng local-client-trust.p12 của lab.
    // Cần được triển khai trong test fixtures và KHÔNG chứa
    // password literal trong repository.
    private final SSLContext tls = testTrustContext();

    @Test
    void matchingDnsNameIsAccepted() {
        assertDoesNotThrow(() ->
            TlsProbe.verifyConnection(
                "https://localhost:8443/ws", tls));
    }

    @Test
    void ipWithoutIpSanIsRejected() {
        assertThrows(SSLException.class, () ->
            TlsProbe.verifyConnection(
                "https://127.0.0.1:8443/ws", tls));
    }
}
~~~

**Điều kiện test:** HTTPS server đang chạy, certificate đã được tin cậy qua `testTrustContext()`, không có hostname verifier bị tắt, port và DNS đúng. `testTrustContext()` là helper giả định; có thể dùng `PartnerTlsContexts.createServerTrustContext(...)` ở mục 8 với truststore test. Không chạy test này nếu chưa dựng HTTPS fixture thực.

Một `SSLException` ở test âm tính phải được **điều tra nguyên nhân**: kết nối bị từ chối vì wrong SAN là mục tiêu của test, không phải do hết hạn cert, thiếu trust anchor hoặc server chưa chạy. Chỉ dùng `assertThrows` là chưa đủ để kết luận đúng hostname verifier; bổ sung kiểm tra root cause/log của môi trường test.

### 15.3. Test SOAP sau khi TLS thành công

Với server có `MessageDispatcherServlet` và endpoint Spring-WS:

~~~java
Object response = webServiceTemplate.marshalSendAndReceive(
    "https://localhost:8443/ws",
    requestRoot,
    new SoapActionCallback("urn:example:orders:v1/GetOrder"));
~~~

Test thành công cần xác nhận thêm:

- WSDL/`soap:address`, SOAPAction và payload QName đúng.
- XSD/JAXB marshal và unmarshal đúng.
- SOAP version và HTTP Content-Type theo binding.
- Không có redirect xuống HTTP hoặc sang host chưa được phê duyệt.
- Nếu mTLS/WS-Security được yêu cầu, certificate client và SOAP signature thực sự được xác minh.
- Request sai XSD hoặc sai security token được từ chối bằng lỗi phù hợp.

Trước khi gọi SOAP phải gắn một **HTTP sender được cấu hình với test SSLContext**. Đoạn gọi trên riêng lẻ không tự tạo hoặc cài `SSLContext`.

### 15.4. Mock SOAP không thay thế test HTTPS

| Loại test | Chứng minh được | Không tự chứng minh |
|---|---|---|
| `MockWebServiceServer` | SOAP Body, Action, Header, marshalling, response mock | DNS, TCP, CA trust, SAN, TLS/mTLS thật |
| XSD/JAXB unit tests | Schema, QName, kiểu dữ liệu | HTTPS identity |
| `TlsProbe` qua local HTTPS | JSSE trust/hostname validation với test certificate | SOAP request/response contract |
| Spring-WS integration test qua HTTPS | TLS + servlet + SOAP request/response | Tất cả policy của đối tác production |
| Test với endpoint đối tác sandbox | Cấu hình thực, WSDL/WS-Security interoperability | Toàn bộ các trường hợp sản xuất nếu dữ liệu/region/cert khác |

Một test plan tốt có **cả test dương tính lẫn âm tính**. Nếu test chỉ chứng minh “kết nối thành công”, việc một ai đó thay `HostnameVerifier` thành luôn true có thể không bị phát hiện.

## 16. Case study: sự cố sau khi đối tác đổi chứng chỉ

### 16.1. Bối cảnh

Ứng dụng Spring Boot dùng `WebServiceTemplate` gọi:

~~~text
https://api.partner.example/soap/orders
~~~

Đối tác đổi gateway và certificate. Sau thay đổi, khoảng một nửa request bị `SSLHandshakeException`, nhưng một số requests vẫn thành công. Người vận hành nhận đề xuất tạm thời “tắt certificate validation cho ổn định”.

Hãy **không** làm vậy. Bắt đầu từ evidence theo từng đích:

1. Kiểm tra DNS trả những IP nào, và endpoint nào đang lỗi.
2. Với mỗi IP, giữ nguyên host `api.partner.example` và SNI bằng công cụ test như `curl --resolve` hoặc OpenSSL kết nối có `-servername`.
3. So certificate chain, SAN, expiry và trust anchor của từng gateway.
4. Kiểm tra gateway/backend có cùng TLS policy, có intermediate thiếu hoặc certificate của virtual host mặc định không.
5. Đối chiếu Java runtime truststore và client connection pool: process có đang giữ context/cert trust cũ không?
6. Thử negative test bằng một hostname khác để bảo đảm verifier vẫn hoạt động.

### 16.2. Ví dụ một nguyên nhân gốc

Gateway A trả certificate:

~~~text
SAN: DNS:api.partner.example
Chain: leaf -> intermediate-v2 -> approved-root
~~~

Gateway B lại trả:

~~~text
SAN: DNS:internal-gw.partner.example
Chain: leaf -> intermediate-v2 -> approved-root
~~~

Cả hai có thể có chain hợp lệ; **gateway B vẫn sai hostname** cho URL public. Thêm intermediate/root vào truststore **không sửa được SAN sai**. Cách khắc phục là đối tác cấu hình gateway B dùng certificate hợp lệ cho `api.partner.example` hoặc sửa routing/SNI đúng theo contract.

Một trường hợp khác: cả hai SAN đúng nhưng B không gửi intermediate. Lúc đó phải sửa certificate chain configuration, không thay hostname verifier.

### 16.3. Kết quả cần bàn giao

- Root cause: cụ thể là chain, hostname, SNI, mTLS hay TLS policy; không chỉ ghi “SSL error”.
- Evidence: host/SNI/IP, subject/issuer/SAN và verification result; **không thu thập private keys**.
- Biện pháp sửa đúng tầng: gateway certificate, intermediate chain, approved truststore hoặc client config.
- Regression tests: successful SOAP call, wrong-host rejection, wrong-CA rejection, expired cert test khi có fixture, WS-Security signature nếu dùng.
- Monitoring: certificate expiry, tỷ lệ TLS handshake failure và lỗi theo region/gateway.
- Rollback/rotation plan: hỗ trợ certificate chain cũ/mới có kiểm soát mà không dùng trust-all.

Nếu một bên đề nghị đổi URL thành `https://10.x.x.x` rồi tắt hostname verification, yêu cầu họ cung cấp **tên DNS và certificate hợp lệ** hoặc giải pháp mTLS/proxy được phê duyệt. Không đánh đổi identity checking để che lỗi hạ tầng.

## 17. Bài tập thực hành và đáp án

### Bài 1 — Trust chain tốt nhưng SAN sai

Client gọi `https://orders.partner.example/ws`. Server trả chứng chỉ được ký bởi CA mà client trust, SAN chỉ có `DNS:billing.partner.example`. Có được phép kết nối không?

**Đáp án:** Không. PKIX trust chain thành công không có nghĩa certificate đúng cho hostname `orders.partner.example`. Phải sửa SAN/certificate hoặc URL hợp đồng, không tắt hostname verifier.

### Bài 2 — Gọi IP thay DNS

Client đang gọi `https://soap.partner.example/ws` và hoạt động. Đội vận hành thay URL thành `https://198.51.100.20/ws` để “tránh DNS lỗi”. Certificate chỉ chứa `DNS:soap.partner.example`. Vì sao thất bại?

**Đáp án:** URL mới dùng IP literal; verifier cần IP SAN phù hợp. Đừng disable validation; khôi phục DNS URL, sửa DNS hoặc triển khai certificate IP SAN theo chính sách. `198.51.100.20` là IP minh họa dành cho tài liệu, không phải đích thật.

### Bài 3 — JVM truststore riêng làm lỗi dịch vụ khác

Sau khi đặt `-Djavax.net.ssl.trustStore=partners.p12`, SOAP client tới đối tác A hoạt động, nhưng REST client tới public service B đột nhiên `PKIX` fail.

**Đáp án:** Custom truststore có thể thay thế tập trust anchors mặc định cho process. Cần thiết kế tập roots đúng hoặc client-specific SSLContext/HTTP sender, không dùng trust-all và không thay global property theo request.

### Bài 4 — Root tin cậy nhưng server thiếu intermediate

Trong truststore có root CA, leaf của server được cấp bởi intermediate CA nhưng server không gửi intermediate. Tại sao có thể path building fail?

**Đáp án:** Client không có đủ chain components để nối leaf tới root. Yêu cầu server gửi intermediate đúng hoặc dùng resolver/cert path policy phù hợp; không giả định mọi JVM tự tải intermediates qua Internet.

### Bài 5 — mTLS khác WS-Security

Đối tác yêu cầu mTLS và chữ ký SOAP Body. Bạn cấu hình client certificate thành công, SOAP POST được chấp nhận ở TLS, nhưng SOAP Fault báo thiếu signature. Có mâu thuẫn không?

**Đáp án:** Không. mTLS chứng minh danh tính client ở kết nối, còn WS-Security ký thông điệp. Cần cấu hình cả hai theo policy và kiểm tra key/cert identities phù hợp.

### Bài 6 — WSDL qua HTTPS nhưng SOAP endpoint qua HTTP

Client tải WSDL thành công từ `https://partner.example/ws/orders.wsdl`. Trong `soap:address` lại là `http://internal.example/ws`. Có thể kết luận kết nối SOAP được HTTPS bảo vệ không?

**Đáp án:** Không. URL tải **WSDL** và URL đích **SOAP POST** có thể khác nhau. Phải xác minh URL thực mà `WebServiceTemplate` dùng và chỉnh cấu hình contract/proxy để dùng HTTPS đúng policy.

### Bài 7 — Curl pass, Java fail

`curl --cacert partner-ca.pem` tải WSDL thành công, nhưng Java SOAP client báo PKIX. Phải làm gì?

**Đáp án:** Xác minh Java runtime/truststore thực, CA chain, SNI/hostname và TLS debug. Curl có thể dùng CA/backend/policy khác JSSE. Không coi kết quả curl là bằng chứng Java cấu hình đúng.

### Bài 8 — Tắt hostname verifier ở môi trường test

Một test chỉ xác nhận `https://localhost:8443` trả HTTP 200. Developer thêm hostname verifier luôn true để test pass. Vì sao test kém an toàn?

**Đáp án:** Test không có trường hợp sai hostname, nên không phát hiện việc bỏ identity checking. Tạo cert test có `DNS:localhost`, trust đúng và assert `https://127.0.0.1:8443` thất bại nếu không có IP SAN.

### Bài 9 — TLS handshake fail có phải SOAP Fault?

Ứng dụng nhận `SSLHandshakeException` trước khi server xác nhận certificate. Có nên sửa `SoapFaultMappingExceptionResolver` ở server không?

**Đáp án:** Không. TLS handshake failure nằm ở tầng vận chuyển/chứng chỉ, trước SOAP endpoint/Fault resolver. Xử lý TLS config hoặc server certificate; fault resolver không thể trả SOAP Fault cho request chưa thiết lập được HTTPS đúng.

### Bài 10 — Certificate rotation và truststore

Đối tác thông báo chuyển từ CA A sang CA B trong hai tuần. Client hiện chỉ trust CA A. Bạn có thể chuẩn bị thế nào?

**Đáp án:** Xác minh CA B ngoài băng, kiểm tra SAN/chain/policy, cập nhật truststore hoặc SSLContext riêng có kiểm soát, dự tính overlap window và reload connection pools, test cả chain mới/cũ trước khi cutover, rồi loại trust anchor cũ theo quy trình phê duyệt.

### Bài 11 — Client log SSL debug

Để chẩn đoán lỗi, developer bật TLS debug trên production rồi gửi nguyên log cho đối tác. Có cần xem xét gì?

**Đáp án:** Logs có thể chứa certificate chain, endpoints, thuật toán và các metadata nội bộ. Cần lấy mẫu có kiểm soát, loại dữ liệu nhạy cảm, hạn chế thời gian bật, bảo vệ quyền truy cập và chỉ chia sẻ phần đủ chẩn đoán.

### Bài 12 — Revocation

Một công ty yêu cầu từ chối chứng chỉ đã bị thu hồi. Có thể khẳng định Java mặc định luôn hard-fail khi OCSP server không truy cập được không?

**Đáp án:** Không. Phải thiết kế và kiểm thử revocation policy (CRL/OCSP, cache, soft-/hard-fail, stapling khi có) theo JDK/provider, yêu cầu an ninh và khả năng mạng của môi trường thực.

## 18. Checklist triển khai HTTPS cho SOAP client Spring-WS

### Trust và hostname verification

- [ ] URL SOAP dùng HTTPS theo policy; không gửi nội dung nhạy cảm qua HTTP.
- [ ] Xác minh đúng **runtime JVM** và HTTP message sender đang dùng.
- [ ] Server certificate chain dẫn tới trust anchor được phê duyệt.
- [ ] Server gửi intermediate CA certificates phù hợp.
- [ ] Certificate chưa hết hạn, chưa bắt đầu sai thời điểm và thỏa algorithm/key-usage policy.
- [ ] DNS SAN/IP SAN khớp **host của URL thực**; không chỉ kiểm tra CN.
- [ ] Không dùng TrustManager bỏ qua `checkServerTrusted`.
- [ ] Không dùng `HostnameVerifier` luôn true hoặc tắt endpoint identity checking.
- [ ] Nếu dùng custom SSLContext, sender vẫn thực hiện hostname verification.
- [ ] SNI/virtual-host certificate đúng trên mọi gateway/IP.
- [ ] Revocation policy được quy định và test, không suy đoán JVM default.
- [ ] Không import bừa certificates chỉ để làm biến mất lỗi PKIX.

### Keystore, mTLS, transport và vận hành

- [ ] Phân biệt truststore (trust server) và keystore (client private key).
- [ ] mTLS certificate/key/chain được quản lý qua secret manager, file permissions đúng.
- [ ] TLS signing identity và WS-Security message signing identity được phân biệt.
- [ ] Truststore/keystore passwords không có trong source/log/CLI công khai.
- [ ] Client theo từng đối tác có cấu hình trust/identity riêng khi cần.
- [ ] HTTP sender timeout, proxy, pool và TLS configuration theo đúng phiên bản dependency.
- [ ] Redirect được kiểm soát; không tự chuyển HTTPS → HTTP hoặc lộ credentials qua host mới.
- [ ] Certificate rotation, expiry alerts và reload/rollback có chủ sở hữu rõ.
- [ ] Kết nối proxy → backend cũng có TLS policy đúng nếu được yêu cầu.
- [ ] WSDL `soap:address` và tất cả URL imports/XSD được kiểm tra từ phía client.
- [ ] Không log SOAP Body, token, private key, TLS secrets hay certificates nội bộ không cần thiết.

### Kiểm thử

- [ ] Java TLS integration test chứng minh đúng host được chấp nhận.
- [ ] Java TLS negative test chứng minh wrong-host/wrong-CA bị từ chối.
- [ ] Test expired cert/intermediate missing/mTLS rejection khi phù hợp.
- [ ] Test SOAP Body, SOAPAction, JAXB và XSD riêng với `MockWebServiceServer`.
- [ ] Test SOAP request/response qua HTTPS **thật**, không chỉ mock.
- [ ] Test WS-Security signed/tampered messages và authorization nếu policy yêu cầu.
- [ ] Test failover gateways, container runtime và cert rotation.
- [ ] Test timeout/retry/idempotency và phân biệt TLS exception với SOAP Fault.
- [ ] Security debug/logging được giới hạn và xóa theo chính sách.

**Ghi nhớ:** Một SOAP client an toàn không chỉ cần URL bắt đầu bằng `https://`. Nó phải **xác minh đường dẫn chứng chỉ và trust anchor**, **kiểm tra SAN khớp hostname đích**, đồng thời bảo vệ cấu hình TLS/mTLS trong HTTP sender. Với Spring Web Services, HTTPS là an ninh **kênh truyền**; SOAP/XSD/JAXB bảo đảm hợp đồng dữ liệu; WS-Security bổ sung an ninh **thông điệp** theo policy. Sự tương thích doanh nghiệp chỉ được chứng minh khi cả kiểm thử TLS âm tính, SOAP integration và certificate rotation đều được thực hiện có kiểm soát.
