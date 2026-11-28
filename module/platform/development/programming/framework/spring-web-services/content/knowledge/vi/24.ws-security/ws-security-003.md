# Wss4jSecurityInterceptor và tích hợp Apache WSS4J

Một SOAP endpoint xây dựng đúng hợp đồng **XSD/WSDL** vẫn chưa an toàn chỉ vì chạy qua HTTPS. Trong tích hợp doanh nghiệp, request có thể đi qua gateway, ESB, hàng đợi hoặc nhiều SOAP intermediaries. Dịch vụ đôi khi cần biết **ai đã ký thông điệp, phần nào của SOAP Body/Header thực sự được ký, nội dung nào đã được mã hóa, timestamp còn hiệu lực không và một thông điệp đã được dùng lại hay chưa**. Những yêu cầu ở tầng **SOAP message** được giải quyết bằng **WS-Security**.

Trong **Spring Web Services (Spring-WS)**, `Wss4jSecurityInterceptor` tích hợp thư viện **Apache WSS4J** để bảo vệ thông điệp SOAP đi ra và kiểm tra thông điệp SOAP đi vào. Đó là một interceptor phục vụ cả **Spring-WS endpoint** lẫn **SOAP client**. Việc cấu hình đúng không chỉ dừng ở `securementActions="Signature"` hoặc `validationActions="UsernameToken"`; cần phối hợp keystore/truststore, callback handler, thuật toán, chính sách vùng dữ liệu được ký, replay protection, thứ tự xử lý và kiểm thử tương thích.

Bài thuộc chương **WS-Security** của module **SPRING_WEB_SERVICES**, nơi chúng ta phát triển dịch vụ SOAP theo hướng **contract-first** với XSD/WSDL, ánh xạ JAXB, xây dựng endpoint và SOAP client, xử lý SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích. Bài tập trung vào **kiến trúc, cấu hình và cách tích hợp `Wss4jSecurityInterceptor` với Apache WSS4J**, đồng thời đặt ra ranh giới rõ giữa bảo mật SOAP, TLS/mTLS, schema validation và phân quyền nghiệp vụ.

## 1. Bốn câu hỏi trước khi cấu hình WS-Security

Mọi chính sách bảo vệ SOAP nên trả lời:

1. **Xác thực:** Ai là chủ thể gửi thông điệp? Danh tính đến từ `UsernameToken`, chứng chỉ X.509/chữ ký, SAML hoặc cơ chế đáng tin khác?
2. **Toàn vẹn:** Chính xác phần tử XML nào phải được ký? SOAP Body, Timestamp, `wsa:Action`, `wsa:To`, identifier tenant hay attachment?
3. **Bí mật:** Phần dữ liệu nào phải được mã hóa, ai giữ private key giải mã và thuật toán nào hai phía hỗ trợ?
4. **Chống phát lại:** Timestamp, nonce, message ID, replay cache và idempotency của nghiệp vụ được áp dụng ở đâu?

Một SOAP request có thể mang `wsse:Security` nhưng **vẫn phải bị từ chối** nếu password sai, chữ ký không đáng tin, signed parts không đủ, timestamp hết hạn hoặc token đã được dùng lại. Ngược lại, một SOAP request có Body hợp XSD **không tự là thông điệp đã được xác thực**.

| Cơ chế | Tầng | Đảm bảo chính | Không tự đảm bảo |
| --- | --- | --- | --- |
| TLS/HTTPS | Transport | Bảo mật kênh truyền, xác thực server khi kiểm tra certificate đúng | SOAP message được ký xuyên các intermediaries |
| mTLS | Transport | Chứng chỉ client trong TLS handshake | SOAP Body/Header được ký, caller được quyền nghiệp vụ |
| `UsernameToken` | SOAP Header | Chứng minh shared secret theo WS-Security profile/chính sách | Quyền truy cập tài nguyên, mã hóa Body |
| XML Digital Signature | SOAP/XML | Toàn vẹn và danh tính signer **trên những nodes được ký** | Những node khác hoặc MIME parts không nằm trong signature |
| XML Encryption | SOAP/XML | Bí mật cho những parts đã mã hóa | Sender authorization, replay protection |
| `wsu:Timestamp` + replay cache | WS-Security processing | Hạn chế message cũ/trùng theo policy | Exactly-once execution hay idempotency nghiệp vụ |
| XSD/JAXB validation | Application contract | Kiểu và cấu trúc XML phù hợp hợp đồng | Chữ ký/token hợp lệ |
| Authorization | Domain/application | Principal có quyền với operation/resource | Tính đúng đắn của chữ ký nếu chưa xác minh |

**Nguyên tắc:** một security check chỉ có giá trị cho **dữ liệu thực sự được service tiêu thụ**, không chỉ vì SOAP Header chứa một chuỗi có vẻ hợp lệ.

## 2. WS-Security Header trong một SOAP message

Ví dụ **SOAP 1.1** minh họa vị trí của UsernameToken và Timestamp. Các giá trị mật khẩu/digest dưới đây là **placeholder không hợp lệ**, không dùng để gửi request thật:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
    xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
    xmlns:ord="urn:example:orders:v1">
  <soapenv:Header>
    <wsse:Security soapenv:mustUnderstand="1">
      <wsu:Timestamp wsu:Id="TS-1">
        <wsu:Created>2026-11-27T02:00:00Z</wsu:Created>
        <wsu:Expires>2026-11-27T02:05:00Z</wsu:Expires>
      </wsu:Timestamp>
      <wsse:UsernameToken wsu:Id="UT-1">
        <wsse:Username>partner-a</wsse:Username>
        <wsse:Password
            Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">PLACEHOLDER</wsse:Password>
        <wsse:Nonce>PLACEHOLDER</wsse:Nonce>
        <wsu:Created>2026-11-27T02:00:00Z</wsu:Created>
      </wsse:UsernameToken>
    </wsse:Security>
  </soapenv:Header>
  <soapenv:Body>
    <ord:GetOrderRequest>
      <ord:orderId>ORD-1024</ord:orderId>
    </ord:GetOrderRequest>
  </soapenv:Body>
</soapenv:Envelope>
~~~

**Chú ý:**

- `wsse:Security` nằm trong **SOAP Header**; phần dữ liệu nghiệp vụ vẫn nằm trong **SOAP Body**.
- `wsu:Timestamp` và `wsse:UsernameToken` là hai đối tượng với semantics riêng; thời điểm `Created` trong UsernameToken không tự thay thế mọi ràng buộc của Timestamp.
- `mustUnderstand` là quy tắc SOAP processing, **không phải bằng chứng authentication**.
- Khi dùng chữ ký X.509, Header còn có thể chứa `ds:Signature`, `wsse:BinarySecurityToken` và các references. Khi mã hóa, có thể thấy `xenc:EncryptedData`/`EncryptedKey` theo profile.
- Tiền tố XML có thể khác (`wsse` thành `sec`), nhưng **namespace URI và QName** phải đúng.

Ví dụ request ở trên không thể qua validation chỉ vì có cấu trúc XML đúng: digest/nonce là placeholder, timestamp có thể đã hết hạn và token chưa được chứng minh. Đây chính là điều `Wss4jSecurityInterceptor` phải kiểm tra ở runtime.

## 3. Kiến trúc tích hợp Spring-WS với Apache WSS4J

~~~mermaid
flowchart TD
    A["SOAP client<br/>WebServiceTemplate"] --> C["ClientInterceptor<br/>Wss4jSecurityInterceptor"]
    C --> D["SAAJ SOAP message<br/>outbound security"]
    D --> T["HTTP sender / TLS / mTLS"]
    T --> G["Gateway / intermediary"]
    G --> P["MessageDispatcherServlet<br/>XML parsing"]
    P --> M["EndpointMapping / interceptor chain"]
    M --> I["EndpointInterceptor<br/>Wss4jSecurityInterceptor"]
    I --> V{"WSS4J validation OK?"}
    V -->|Không| F["Security SOAP Fault / từ chối"]
    V -->|Có| X["XSD / JAXB / authorization"]
    X --> E["@Endpoint và domain service"]
    E --> R["SOAP response / Fault"]
    R --> O["WSS4J securement outbound"]
    O --> T2["HTTP response"]
~~~

Sơ đồ mô tả **quan hệ trách nhiệm**, không cam kết mọi callback vật lý chạy theo một tuyến giống nhau. SOAP/XML parser phải đọc được Header trước khi WSS4J xử lý. Endpoint mapping có thể diễn ra trước endpoint-bound interceptors; vì vậy phải bảo vệ cả parser, transport, routing và những request không map được endpoint.

`Wss4jSecurityInterceptor` thuộc package:

~~~java
org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor
~~~

Đây là tích hợp với **Apache WSS4J 2.x**, và class này triển khai cả `EndpointInterceptor` và `ClientInterceptor`. Với Spring-WS 4.x, các API Javax/Jakarta liên quan XML cần được giữ đồng bộ với Spring Framework/JAXB/SAAJ runtime đang dùng. **Đừng lấy class ở package `wss4j` của một dự án Spring-WS rất cũ rồi đổi tên ngẫu nhiên**; kiểm tra dependency và JavaDoc đúng phiên bản.

### 3.1. WSS4J làm gì bên dưới?

Apache WSS4J cung cấp các thành phần xử lý WS-Security:

| Nhóm Apache WSS4J | Vai trò |
| --- | --- |
| `WSSecurityEngine` | Xử lý/kiểm tra WS-Security trên SOAP DOM |
| WS-Security actions | Xây UsernameToken, Timestamp, Signature, Encryption hoặc kiểm tra tương ứng |
| `Crypto` | Làm việc với chứng chỉ, trust material, private keys |
| `CallbackHandler` | Cung cấp/tra cứu secret, password hoặc xử lý callback theo policy |
| `WSPasswordCallback` | Callback password cho UsernameToken, signing, decryption tùy ngữ cảnh |
| `ReplayCache` | Phát hiện nonce/timestamp/signature replay theo cấu hình |
| `WSSConfig`/processor/validator | Chính sách/thuật toán và cách xử lý security tokens |

Spring-WS giữ vai trò **đăng ký và điều phối interceptor**; WSS4J thực hiện nhiều thao tác mật mã/chuẩn WS-Security. Tích hợp còn cần tầng **xác định principal và authorization** của ứng dụng: một chữ ký hợp lệ chưa chắc có quyền `CancelOrder`.

### 3.2. Inbound khác outbound

| Vai trò interceptor | SOAP đi vào | SOAP đi ra |
| --- | --- | --- |
| **Ở SOAP server** | `validationActions`: kiểm tra **request** | `securementActions`: bảo vệ **response** |
| **Ở SOAP client** | `validationActions`: kiểm tra **response** | `securementActions`: bảo vệ **request** |

Ví dụ server yêu cầu request có Timestamp và chữ ký, nhưng response chỉ cần Timestamp và chữ ký của **server**. Hai phía phải cấu hình **cặp inbound/outbound đối xứng theo hợp đồng**, không lấy nguyên một bean dùng cả client/server khi trust material, aliases và chính sách khác nhau.

## 4. SecurementActions và ValidationActions

Hai thuộc tính quan trọng nhất:

~~~java
interceptor.setSecurementActions("Timestamp Signature");
interceptor.setValidationActions("Timestamp Signature");
~~~

Các action là **chuỗi phân tách bằng dấu cách**. Đây không phải tên Java annotation hay XPath. Danh sách WSS4J mà Spring-WS 4.1.4 công bố:

| Action | Outbound `securementActions` | Inbound `validationActions` |
| --- | --- | --- |
| `UsernameToken` | Tạo username/password token | Kiểm tra UsernameToken |
| `UsernameTokenSignature` | Tạo UsernameToken và chữ ký theo secret-key profile | Không dùng như một validation action cùng tên |
| `Timestamp` | Thêm `wsu:Timestamp` | Kiểm tra timestamp |
| `Signature` | Ký message/parts theo cấu hình | Xác minh XML Signature |
| `Encrypt` | Mã hóa message/parts theo cấu hình | Giải mã message |
| `NoSecurity` | Không tạo bảo vệ SOAP | Không yêu cầu WS-Security action |

**Thứ tự các actions có ý nghĩa:** WSS4J kiểm tra thứ tự security actions ở inbound theo cấu hình validation và cơ chế strict action checking. `"Timestamp Signature Encrypt"` không đồng nghĩa tùy ý với `"Encrypt Signature Timestamp"`. Thiết kế thứ tự theo **policy và thực tế XML trên dây**, đặc biệt khi kết hợp sign/encrypt; phải kiểm thử bằng đối tác độc lập.

### 4.1. Không lấy danh sách action làm một chính sách đầy đủ

`validationActions="Signature"` xác minh **có thao tác Signature hợp lệ**; bản thân chuỗi action không xác định:

- SOAP Body nào và Header nào **bắt buộc** được ký.
- Certificate chain thuộc danh tính đối tác nào, trust anchor nào được phép.
- UsernameToken nào gắn với principal hay tenant đang gọi.
- Chữ ký có bao phủ **đúng node được endpoint/JAXB tiêu thụ** không.
- Callback `ReplyTo/FaultTo` có nằm trong vùng bảo vệ cần thiết không.

Vì vậy các ràng buộc **signed-parts coverage, X.509 trust, authorization và message invariants** phải được xác định rõ, kiểm tra bằng cấu hình/validator phù hợp và negative tests. Đừng coi “pass `Signature`” là đủ cho mọi yêu cầu.

## 5. Dependency và đồng bộ phiên bản

Đoạn Maven dependencies minh họa trong dự án đã có Spring Boot/Spring dependency management tương thích:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.ws</groupId>
        <artifactId>spring-ws-core</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.ws</groupId>
        <artifactId>spring-ws-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.ws</groupId>
        <artifactId>spring-ws-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Đây **không phải POM hoàn chỉnh**; Spring-WS/WSS4J/SAAJ/JAXB dependencies và các phụ thuộc tùy chọn như SAML/OpenSAML cần được giải quyết theo dependency management đã chọn. Không pin version WSS4J và HttpClient một cách độc lập với Spring-WS rồi kỳ vọng các API tương thích.

Một số lỗi do sai dependency graph:

- `NoClassDefFoundError` cho `org.apache.wss4j.*`.
- Lẫn `org.apache.ws.security.*` (WSS4J cũ) với `org.apache.wss4j.*` (WSS4J 2.x).
- Lẫn `javax.xml.soap`/`javax.xml.bind` và `jakarta.xml.soap`/`jakarta.xml.bind`.
- Thiếu SAAJ implementation hoặc security provider/algorithm được policy yêu cầu.
- Một thư viện XML security, OpenSAML hay cryptography provider không tương thích classpath.

Trong quy trình nâng cấp, kiểm tra BOM và release notes của **đúng cặp Spring-WS / WSS4J**, chạy lại signature/encryption interoperability tests. **Không thay XML parser/security libraries chỉ để né một Fault mà chưa hiểu nguyên nhân**.

## 6. Đăng ký Wss4jSecurityInterceptor ở SOAP server

Ví dụ một server chỉ yêu cầu **UsernameToken + Timestamp** ở inbound. `CallbackHandler` dưới đây là thành phần riêng để lấy mật khẩu theo danh tính đối tác (xem phần 8):

~~~java
import javax.security.auth.callback.CallbackHandler;
import org.apache.wss4j.common.cache.ReplayCache;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

@Configuration
public class InboundSoapSecurityConfiguration {

    @Bean
    public Wss4jSecurityInterceptor inboundWsSecurity(
            CallbackHandler partnerSecretCallbacks,
            ReplayCache wsSecurityReplayCache) {

        Wss4jSecurityInterceptor interceptor =
                new Wss4jSecurityInterceptor();
        interceptor.setValidationActions("UsernameToken Timestamp");
        interceptor.setValidationCallbackHandler(partnerSecretCallbacks);
        interceptor.setTimestampStrict(true);
        interceptor.setValidationTimeToLive(300);
        interceptor.setFutureTimeToLive(60);
        interceptor.setValidationReplayCache(wsSecurityReplayCache);
        interceptor.setStrictActionChecking(true);
        interceptor.setBspCompliant(true);
        return interceptor;
    }
}
~~~

**Giả định của ví dụ:** `partnerSecretCallbacks` và `wsSecurityReplayCache` là các beans đã được triển khai và quản lý riêng, có semantics phù hợp WSS4J; không phải Spring tự sinh hai bean này trong mọi dự án. `ReplayCache` thường nên được lựa chọn theo nhu cầu **một instance hay nhiều server nodes**; `setValidationReplayCache` kiểm soát detection cho các nhóm replay mà WSS4J hỗ trợ.

### 6.1. Gắn interceptor vào EndpointInterceptor chain

~~~java
import java.util.List;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

@Configuration
@EnableWs
public class SoapEndpointConfiguration implements WsConfigurer {
    private final Wss4jSecurityInterceptor inboundWsSecurity;

    public SoapEndpointConfiguration(
            Wss4jSecurityInterceptor inboundWsSecurity) {
        this.inboundWsSecurity = inboundWsSecurity;
    }

    @Override
    public void addInterceptors(
            List<EndpointInterceptor> interceptors) {
        interceptors.add(inboundWsSecurity);
    }
}
~~~

Ở một Spring-WS application context, `WsConfigurer.addInterceptors(...)` thêm interceptor vào chuỗi của các endpoint mappings được framework cấu hình. **Không tạo hai interceptor chains không được kiểm soát** vì thêm một cấu hình trùng lặp; phải xác minh bean/mapping thực tế, thứ tự và phạm vi áp dụng.

### 6.2. Giới hạn của endpoint-bound security

EndpointInterceptor được liên kết với **đường có endpoint mapping phù hợp**. Một lỗi XML parser, SOAP version, HTTP gateway hoặc request chưa chọn được endpoint có thể xảy ra **trước** interceptor. Vì vậy:

- Cứng hóa SOAP/XML parser và giới hạn request size/depth từ ingress.
- Kiểm tra TLS, mTLS, HTTP auth tại đúng tầng khi được yêu cầu.
- Không để endpoint nhạy cảm **lọt khỏi interceptor chain** vì mapping/config khác.
- Không dùng `@PayloadRoot`/`@Action` để thay authentication; đó chỉ là routing.
- Kiểm thử cả request **không có endpoint match** và yêu cầu có đúng SOAP Header.

## 7. Dùng Wss4jSecurityInterceptor ở SOAP client

Một Spring-WS client có thể phát `UsernameToken` và `Timestamp` trước khi gửi request:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

@Configuration
public class OutboundSoapSecurityConfiguration {
    @Bean
    public Wss4jSecurityInterceptor outboundWsSecurity(
            @Value("${partner.soap.username}") String username,
            @Value("${partner.soap.password}") String password) {

        Wss4jSecurityInterceptor interceptor =
                new Wss4jSecurityInterceptor();
        interceptor.setSecurementActions("UsernameToken Timestamp");
        interceptor.setSecurementUsername(username);
        interceptor.setSecurementPassword(password);
        interceptor.setSecurementPasswordType("PasswordDigest");
        interceptor.setSecurementUsernameTokenNonce(true);
        interceptor.setSecurementUsernameTokenCreated(true);
        interceptor.setSecurementTimeToLive(300);
        return interceptor;
    }
}
~~~

**Quan trọng:** password chỉ được inject từ **secret management**; không lưu mật khẩu thực trong Git, config công khai hoặc log. `PasswordDigest` chỉ là kiểu biểu diễn UsernameToken; **không thay thế TLS** và cũng không chứng minh Body được ký. Một hệ thống production có thể cần **Signature/Encrypt** thay vì, hoặc ngoài, UsernameToken tùy đối tác.

Gắn client interceptor vào `WebServiceTemplate`:

~~~java
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.client.support.interceptor.ClientInterceptor;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

WebServiceTemplate template = configuredWebServiceTemplate;
Wss4jSecurityInterceptor security = outboundWsSecurity;
template.setInterceptors(new ClientInterceptor[] {security});
~~~

Hai biến `configuredWebServiceTemplate` và `outboundWsSecurity` tượng trưng cho các beans đã tạo, không phải code chạy độc lập. `WebServiceTemplate` phải được cấu hình `SaajSoapMessageFactory`, OXM/JAXB, HTTP message sender, URI và TLS/mTLS phù hợp. **Chỉ phát request security không tự kiểm tra response security**: nếu đối tác ký hoặc mã hóa SOAP response, client phải cấu hình **`validationActions` và Crypto thích hợp** để xác minh.

### 7.1. Đừng dùng một interceptor singleton với nhiều partner policy khác nhau

~~~text
Partner A: UsernameToken + Timestamp, shared secret A
Partner B: X.509 Signature + Encrypt, private key B, trust B
Partner C: SOAP 1.2, Signature và WS-Addressing signed headers
~~~

Ba policies này thường cần **ba cấu hình riêng**. Không liên tục gọi `setSecurementUsername(...)` hoặc `setValidationSignatureCrypto(...)` trên cùng một interceptor trước từng request đồng thời: đó là cấu hình **có thể gây race condition và rò identity**. Tạo named template/interceptor beans riêng theo đối tác, cố định cấu hình sau khởi tạo.

## 8. UsernameToken, callback handler và nguồn danh tính

`UsernameToken` mang username cùng thông tin chứng minh mật khẩu theo profile. Với `PasswordText`, mật khẩu có thể xuất hiện trực tiếp trong SOAP Header nếu không được bảo vệ bằng cơ chế khác; với `PasswordDigest`, client tạo digest từ **nonce/created/password** theo profile, nhưng vẫn cần bảo vệ transport, chống replay và lưu trữ secret an toàn.

### 8.1. Callback để tra shared secret

Một `CallbackHandler` của Java có thể đáp ứng callback WSS4J:

~~~java
import java.io.IOException;
import javax.security.auth.callback.Callback;
import javax.security.auth.callback.CallbackHandler;
import javax.security.auth.callback.UnsupportedCallbackException;
import org.apache.wss4j.common.ext.WSPasswordCallback;

public final class PartnerSecretCallbackHandler
        implements CallbackHandler {

    private final PartnerSecretStore secretStore;

    public PartnerSecretCallbackHandler(PartnerSecretStore secretStore) {
        this.secretStore = secretStore;
    }

    @Override
    public void handle(Callback[] callbacks)
            throws IOException, UnsupportedCallbackException {

        for (Callback callback : callbacks) {
            if (!(callback instanceof WSPasswordCallback passwordCallback)) {
                throw new UnsupportedCallbackException(callback);
            }

            String identity = passwordCallback.getIdentifier();
            String secret = secretStore.getActiveSecret(identity);
            if (secret == null) {
                // Không phân biệt "không có user" và "mật khẩu sai"
                // trên phản hồi công khai.
                throw new IOException("Không thể xác minh SOAP credential");
            }
            passwordCallback.setPassword(secret);
        }
    }
}
~~~

Đoạn code dùng Java 16+ cho pattern matching `instanceof`. `PartnerSecretStore` là abstraction **do ứng dụng định nghĩa**, tra secret theo danh tính đã cho phép; còn `WSPasswordCallback` là kiểu của WSS4J. Đây là **minh họa luồng callback**, không phải thiết kế secret store production hoàn chỉnh:

- Có thể cần phân biệt `WSPasswordCallback` usage (UsernameToken, private key signing/decryption) và **tách callbacks theo mục đích**, tránh dùng cùng một secret cho mọi chức năng.
- PasswordDigest cần phía xác minh có khả năng tính/kiểm digest theo profile; một hash một chiều của mật khẩu trong DB **không tự tương đương** shared secret mà WSS4J mong đợi.
- Phải giới hạn user/tenant được chấp nhận, áp rotation và giới hạn abuse/replay.
- Không log `getPassword()`, nonce, raw UsernameToken hoặc bất kỳ secret nào.
- Đối với người dùng nội bộ, kiểm tra khả năng tích hợp `SpringSecurityPasswordValidationCallbackHandler` và Spring Security principal/authentication context.

### 8.2. SimplePasswordValidationCallbackHandler dùng trong phòng thử nghiệm

Spring-WS cung cấp `SimplePasswordValidationCallbackHandler` để kiểm tra UsernameToken với một `Properties` in-memory. Ví dụ **chỉ dành cho unit/integration test**:

~~~java
import java.util.Properties;
import org.springframework.ws.soap.security.wss4j2.callback.SimplePasswordValidationCallbackHandler;

SimplePasswordValidationCallbackHandler handler =
        new SimplePasswordValidationCallbackHandler();
Properties fixtureUsers = new Properties();
fixtureUsers.setProperty("test-client", "test-secret-only");
handler.setUsers(fixtureUsers);
~~~

Không mang một bảng plaintext secrets kiểu này vào production. Nó hữu ích để chứng minh request thiếu UsernameToken hoặc dùng sai password sẽ bị từ chối, nhưng **không giải quyết account lifecycle, MFA, tenants, revocation, phishing hay rate limits**.

### 8.3. Spring Security và quyền nghiệp vụ

`SpringSecurityPasswordValidationCallbackHandler` có thể dùng `UserDetailsService` để xác thực UsernameToken và tích hợp `SecurityContextHolder` trong request lifecycle tương thích. **Điều này chưa tự cấp quyền đọc/hủy mọi đơn hàng**:

~~~text
UsernameToken được kiểm tra
          ↓
Principal đáng tin được xác định
          ↓
Authorization: principal này có quyền gọi GetOrder?
          ↓
Authorization: principal này có quyền xem orderId?
          ↓
XSD/JAXB/business validation và thực hiện nghiệp vụ
~~~

Chỉ lấy `wsse:Username` từ XML rồi gắn làm principal không qua xác minh là lỗi nghiêm trọng. Khi dùng message-level X.509, danh tính có thể đến từ certificate/signature, không phải từ UsernameToken; cần có cơ chế mapping identity rõ ràng theo policy.

## 9. Timestamp, replay cache và idempotency

`Timestamp` giúp phát hiện message quá cũ hoặc có `Created` ở tương lai không hợp lệ. Trên Spring-WS 4.1, những setter đáng chú ý:

~~~java
interceptor.setValidationActions("Timestamp");
interceptor.setTimestampStrict(true);
interceptor.setValidationTimeToLive(300); // giây
interceptor.setFutureTimeToLive(60);       // giây
interceptor.setValidationReplayCache(wsSecurityReplayCache);
~~~

**Các giá trị minh họa**, không phải SLA mặc định cho mọi đối tác. Nếu policy yêu cầu 60 giây và hệ thống lệch giờ 70 giây, tăng time-to-live tùy tiện có thể làm rộng cửa sổ replay; trước hết cần đồng bộ đồng hồ và xác định clock skew được phép.

### 9.1. Vì sao timestamp hợp lệ vẫn cần replay cache?

Giả sử attacker thu được một SOAP request đã ký hợp lệ với `Timestamp` còn hiệu lực 5 phút. Nếu server chỉ kiểm chữ ký và thời gian, request có thể được phát lại nhiều lần **trong 5 phút đó**. Replay cache lưu những nhận diện cần thiết (nonce hoặc định danh của signed/timestamp message theo cơ chế WSS4J) để nhận biết request trùng.

`setValidationReplayCache(ReplayCache)` của Spring-WS/WSS4J kết nối replay detection cho UsernameToken nonce và những loại timestamp/signature hoặc SAML one-time-use được hỗ trợ. Spring-WS có `SpringReplayCache` dựa trên Spring Cache abstraction.

**Trong cụm nhiều pods/nodes**, cache cục bộ một node có thể không nhìn thấy nonce đã được dùng trên node khác. Nếu hệ thống cần chống replay xuyên cluster, thiết kế một backend/cache dùng chung, TTL/quota/eviction và failure policy phù hợp; hãy kiểm thử phát lại trên **hai nodes khác nhau**.

### 9.2. WS-Security replay không phải business idempotency

Hai khái niệm khác nhau:

| Bảo vệ | Chống điều gì? | Khóa/tính chất |
| --- | --- | --- |
| **WS-Security replay detection** | Dùng lại thông điệp/nonce/chữ ký trong cửa sổ security | Nonce/timestamp/signature theo policy |
| **Business idempotency** | Tạo hai đơn/chi tiền hai lần từ cùng một ý định | Business request ID gắn với caller và fingerprint |

Khi retry một operation `PlaceOrder` vì timeout, client có thể cần tạo **WS-Security Timestamp/Nonce/Signature mới hợp lệ** nhưng **giữ nguyên idempotency key của nghiệp vụ**. Đừng tắt replay protection để “sửa” tình huống retry bị từ chối.

## 10. Crypto, keystore, truststore và vòng đời chứng chỉ

Để **ký/giải mã**, cần material gắn với private key của phía thực hiện. Để **xác minh chữ ký/mã hóa tới đối tác**, cần certificate/public key của phía còn lại theo một trust policy cụ thể.

| Hoạt động | Material chính | Cách dùng trong interceptor |
| --- | --- | --- |
| Client **ký request** | Private key + certificate client | `securementSignatureCrypto`, signing alias |
| Server **xác minh request** | Public cert/trust anchors của client | `validationSignatureCrypto` |
| Client **mã hóa request cho server** | Public cert server | `securementEncryptionCrypto`, recipient alias |
| Server **giải mã request** | Private key server | `validationDecryptionCrypto` và password callback khi cần |
| Server **ký response** | Private key server | `securementSignatureCrypto`, signing alias |
| Client **xác minh response** | Server public cert/trust anchors | `validationSignatureCrypto` |

**Đây là trust/identity theo SOAP message**, không được đánh đồng với truststore/keystore trong HTTP TLS/mTLS. Một ứng dụng có thể dùng cùng hoặc khác certificate tùy thiết kế, nhưng vòng đời và mục đích sử dụng phải được phê duyệt.

### 10.1. CryptoFactoryBean

Spring-WS có `org.springframework.ws.soap.security.wss4j2.support.CryptoFactoryBean` để tạo `org.apache.wss4j.common.crypto.Crypto`.

Ví dụ chỉ ra cách Spring tạo Crypto từ keystore/truststore được cấp qua cấu hình:

~~~java
import java.io.IOException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.Resource;
import org.springframework.ws.soap.security.wss4j2.support.CryptoFactoryBean;

@Bean
public CryptoFactoryBean partnerTrustCrypto(
        @Value("${ws.security.partner-trust-location}") Resource location,
        @Value("${ws.security.partner-trust-password}") String password)
        throws IOException {

    CryptoFactoryBean factory = new CryptoFactoryBean();
    factory.setKeyStoreLocation(location);
    factory.setKeyStorePassword(password);
    return factory;
}
~~~

Bean này **sản xuất một WSS4J `Crypto`**, dùng để xác minh signer trust theo policy. Đây là ví dụ wiring, không chứa file keystore cụ thể; `ws.security.*` phải đến từ cấu hình an toàn. Nếu muốn dùng PKCS#12/JKS hoặc provider tùy chỉnh, phải định nghĩa type/provider và kiểm tra tương thích với runtime.

**Không đưa private key, truststore passwords, key aliases nhạy cảm hoặc certificate signing secrets vào repository.** Tốt nhất là tách trust material và private signing/decryption material theo quyền vận hành; sử dụng secret manager, HSM/KMS nếu policy yêu cầu, và có kế hoạch certificate rotation.

### 10.2. Ví dụ server xác minh chữ ký X.509

~~~java
import org.apache.wss4j.common.cache.ReplayCache;
import org.apache.wss4j.common.crypto.Crypto;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

public Wss4jSecurityInterceptor serverSignatureValidation(
        Crypto partnerTrustCrypto,
        ReplayCache replayCache) {

    Wss4jSecurityInterceptor interceptor =
            new Wss4jSecurityInterceptor();
    interceptor.setValidationActions("Timestamp Signature");
    interceptor.setValidationSignatureCrypto(partnerTrustCrypto);
    interceptor.setValidationReplayCache(replayCache);
    interceptor.setTimestampStrict(true);
    interceptor.setValidationTimeToLive(300);
    interceptor.setFutureTimeToLive(60);
    interceptor.setBspCompliant(true);
    interceptor.setStrictActionChecking(true);
    return interceptor;
}
~~~

Đoạn code minh họa cấu hình method, **không phải @Bean production hoàn chỉnh**: phải đăng ký interceptor đúng chain như phần 6 và xây `Crypto`/`ReplayCache` từ policy tin cậy. Nếu signer truststore chứa nhiều đối tác, cần ràng buộc **certificate signer ↔ partner/tenant/operation**: signature hợp lệ với một trusted cert bất kỳ chưa đủ để kết luận signer được gọi mọi operation.

### 10.3. Chữ ký outbound

Với alias private key đã cấp cho bên ký:

~~~java
import org.apache.wss4j.common.crypto.Crypto;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

public Wss4jSecurityInterceptor clientSignatureSecurement(
        Crypto clientSigningCrypto,
        String signingAlias,
        String privateKeyPassword) {

    Wss4jSecurityInterceptor interceptor =
            new Wss4jSecurityInterceptor();
    interceptor.setSecurementActions("Timestamp Signature");
    interceptor.setSecurementSignatureCrypto(clientSigningCrypto);
    interceptor.setSecurementSignatureUser(signingAlias);
    interceptor.setSecurementPassword(privateKeyPassword);
    interceptor.setSecurementSignatureKeyIdentifier("DirectReference");
    interceptor.setSecurementTimeToLive(300);
    return interceptor;
}
~~~

`DirectReference` dùng để tham chiếu certificate token theo profile tương ứng; một số đối tác dùng `IssuerSerial`. Hai phía phải thỏa thuận key identifier, trust chain, signature/digest algorithms và signed parts. `setSecurementPassword` ở ví dụ là **private-key credential**, không nhất thiết là UsernameToken password. Với cấu hình kết hợp nhiều actions/identities, cần thiết kế secrets và aliases riêng tránh nhập nhằng.

### 10.4. Certificate trust và revocation

Khi verify chữ ký, phải xem **certificate chain**, issuer/subject constraints, effective key usage, validity, chain trust và ràng buộc danh tính theo chính sách. Spring-WS 4.1 có `setValidationSubjectDnConstraints(...)` và `setEnableRevocation(...)` cho cấu hình liên quan; điều kiện CRL/OCSP và khả năng hoạt động offline phụ thuộc PKI/provider được triển khai.

Không giả định `signature cryptographically valid` đồng nghĩa cert chưa bị thu hồi hoặc signer đang được phép. Cần kiểm tra những yêu cầu này một cách cụ thể và có negative tests cho revoked/expired/wrong signer.

## 11. XML Encryption: outbound Encrypt, inbound Encrypt

Trong tên action Spring-WS, **`Encrypt`** có nghĩa khác nhau tùy chiều:

- Với `securementActions`: **mã hóa** XML elements/content đi ra.
- Với `validationActions`: **giải mã** những parts đi vào và kiểm tra cấu trúc bảo mật tương ứng.

Ví dụ client mã hóa request cho server bằng **public cert của server**:

~~~java
import org.apache.wss4j.common.crypto.Crypto;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

public Wss4jSecurityInterceptor clientEncryption(
        Crypto recipientPublicCrypto,
        String recipientCertificateAlias) {

    Wss4jSecurityInterceptor interceptor =
            new Wss4jSecurityInterceptor();
    interceptor.setSecurementActions("Encrypt");
    interceptor.setSecurementEncryptionCrypto(recipientPublicCrypto);
    interceptor.setSecurementEncryptionUser(recipientCertificateAlias);
    interceptor.setSecurementEncryptionKeyTransportAlgorithm(
            "http://www.w3.org/2001/04/xmlenc#rsa-oaep-mgf1p");
    return interceptor;
}
~~~

**Đây là ví dụ chọn key transport RSA-OAEP theo profile/khả năng liên thông**, chưa quy định mọi algorithms, encryption parts hoặc SOAP binding. Để dùng thật, chọn một bộ thuật toán được hai phía hỗ trợ và thỏa chuẩn/policy (ví dụ AES mạnh cho nội dung), xác định element/content encryption, certificate recipient và negative tests.

Ở server nhận thông điệp mã hóa:

~~~java
import javax.security.auth.callback.CallbackHandler;
import org.apache.wss4j.common.crypto.Crypto;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

public Wss4jSecurityInterceptor serverDecryption(
        Crypto serverPrivateCrypto,
        CallbackHandler privateKeyPasswords) {

    Wss4jSecurityInterceptor interceptor =
            new Wss4jSecurityInterceptor();
    interceptor.setValidationActions("Encrypt");
    interceptor.setValidationDecryptionCrypto(serverPrivateCrypto);
    interceptor.setValidationCallbackHandler(privateKeyPasswords);
    return interceptor;
}
~~~

`validationDecryptionCrypto` cần private key phù hợp với recipient của message; callback cung cấp credential giải mã khi provider yêu cầu. **Không dùng truststore chỉ chứa public cert để giả làm private decryption keystore**.

### 11.1. Không bật lại thuật toán cũ chỉ để vượt lỗi

Spring-WS 4.1/WSS4J mặc định **không cho phép RSA PKCS#1 v1.5 XML Encryption key transport** qua `setAllowRSA15KeyTransportAlgorithm(false)`. Đối với đối tác mới, ưu tiên RSA-OAEP hoặc phương án được PKI/security policy phê duyệt. Nếu bên cũ chỉ hỗ trợ RSA 1.5, đó là một **ngoại lệ tương thích có rủi ro**, không phải cấu hình mặc định nên sao chép.

Tương tự, tránh dùng thuật toán chữ ký/digest yếu, bỏ kiểm tra certificate trust hoặc tắt `bspCompliant`. Bất kỳ ngoại lệ nào cũng cần đánh giá rủi ro, thời hạn chuyển đổi và tests âm chứng minh không chấp nhận những thông điệp ngoài policy.

## 12. Signed parts: điều kiện an toàn quan trọng hơn “có chữ ký”

Giả sử request SOAP chứa:

~~~xml
<soapenv:Body wsu:Id="body-1"
              xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
              xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">
    <ord:TransferFundsRequest xmlns:ord="urn:example:payments:v1">
        <!-- Dữ liệu được business service sử dụng -->
    </ord:TransferFundsRequest>
</soapenv:Body>
~~~

WSS4J có thể xác minh `ds:Signature` hợp lệ, nhưng an toàn nghiệp vụ chỉ đạt khi signature **bao phủ đúng Body node mà endpoint/JAXB thực sự tiêu thụ** và những SOAP Headers liên quan đến quyền/định tuyến.

### 12.1. Outbound: securementSignatureParts

Spring-WS hỗ trợ cấu hình `setSecurementSignatureParts(String)`. Mặc định, WSS4J ký **SOAP Body**; nếu hợp đồng yêu cầu ký cả Timestamp hoặc WS-Addressing Header, phải khai báo chính xác signed parts và kiểm chứng message trên dây.

Ví dụ **chỉ ký SOAP 1.1 Body** một cách tường minh:

~~~java
interceptor.setSecurementSignatureParts(
        "{}{http://schemas.xmlsoap.org/soap/envelope/}Body");
~~~

Chuỗi signed-part của WSS4J gồm các phần tử phân tách bằng dấu chấm phẩy; cú pháp có dạng `{}{namespace}localName` trong ví dụ API này. Đối với SOAP 1.2, **namespace Body phải đổi** thành `http://www.w3.org/2003/05/soap-envelope`. Không copy hardcode SOAP 1.1 namespace cho một SOAP 1.2 client.

Với Header mang `wsa:Action`, namespace của Header là `http://www.w3.org/2005/08/addressing`. Nếu policy yêu cầu ký Action, phải đưa **đúng Header node** vào signed parts. Việc chỉ thêm `ActionCallback` sau khi chữ ký đã tạo có thể làm message bị lệch policy; cần kiểm thử interceptor/callback ordering trên Spring-WS version thực tế.

### 12.2. Inbound: validation Signature chưa tự chứng minh coverage

`setValidationActions("Signature")` kích hoạt WSS4J xử lý chữ ký và kiểm tra kết quả. Nhưng một check về **sự tồn tại hoặc tính hợp lệ của một signature** không thay thế yêu cầu **coverage**.

Một bộ kiểm tra an toàn cần xác nhận:

1. **Signer:** certificate/identity nào được dùng, có nằm trong trust policy/allowed partner set không?
2. **Signed Body:** đúng SOAP Body đang được handler tiêu thụ được ký hay không?
3. **Signed Headers:** những Header quyết định operation, destination, principal, tenant hoặc routing đã được ký/bảo vệ tương ứng chưa?
4. **Reference resolution:** `ds:Reference URI` chỉ tới đúng phần tử duy nhất, không trùng IDs hoặc tham chiếu tới một node khác.
5. **Transforms/algorithms:** thuật toán và XML canonicalization nằm trong danh sách policy cho phép.
6. **Replay:** timestamp/nonce/signature identity đã được kiểm tra theo replay policy chưa?
7. **Authorization:** signer được phép thực hiện **operation và tác động tài nguyên** hay không?

### 12.3. XML Signature Wrapping (XSW)

Một cuộc tấn công XSW có thể giữ lại một node **đã được ký** nhưng chèn hoặc di chuyển một node **chưa được ký** sao cho SOAP framework tiêu thụ node khác. Security engine báo signature hợp lệ, nhưng nghiệp vụ đọc dữ liệu attacker thay đổi.

~~~mermaid
flowchart TD
    A["SOAP message có ds:Signature"] --> B["WSS4J verify chữ ký"]
    B --> C{"Signer và signature hợp lệ?"}
    C -->|Không| X["Từ chối"]
    C -->|Có| D{"Signature bao phủ đúng Body/Header đang dùng?"}
    D -->|Không| Y["Từ chối: coverage/XSW risk"]
    D -->|Có| E{"Principal được phép gọi operation?"}
    E -->|Không| Z["Từ chối: authorization"]
    E -->|Có| F["XSD/JAXB + business validation<br/>sau đó mới có side effect"]
~~~

**Không tự “chữa” XSW bằng cách tìm `ds:Signature` theo XPath rồi tin message.** Dùng WSS4J được cập nhật, XML parser an toàn, cơ chế ID resolution/coverage thích hợp, chính sách signature rõ ràng và negative tests sửa **node không được ký**. Nếu service có XML transformations trước/sau verification, phải bảo đảm đối tượng được verify là đối tượng được consume.

## 13. Kết hợp Signature và Encrypt đúng thứ tự

Hai mô hình thường được nhắc đến:

| Mô hình | Ý nghĩa khái quát | Rủi ro/điều kiện |
| --- | --- | --- |
| **Sign then encrypt** | Ký dữ liệu, sau đó mã hóa những phần cần bảo mật | Receiver giải mã trước khi verify theo profile; kiểm tra đối tượng ký |
| **Encrypt then sign** | Mã hóa nội dung, rồi ký phần biểu diễn được thỏa thuận | Signature có thể bao phủ ciphertext; policy phải quy định cách verify |

**Không có một chuỗi action đúng cho mọi đối tác.** Chuẩn/profile và SOAP stack xác định tổ hợp nào tương thích; thứ tự trong `securementActions` và `validationActions` phải phù hợp với thứ tự tạo/xử lý security elements. Các ví dụ `"Timestamp Signature Encrypt"` và `"Encrypt Signature Timestamp"` **không tương đương**, và đổi thứ tự tùy tiện có thể khiến WSS4J từ chối request.

### 13.1. Cấu hình hoàn chỉnh phải khai báo nhiều mảnh

~~~text
Outbound policy:
  Timestamp
  Signature: signing identity + Crypto + signed Body/Headers + algorithms
  Encrypt: recipient public key + selected XML parts + algorithms

Inbound policy:
  Validation action ordering
  Trusted signer Crypto + certificate constraints
  Decryption Crypto + private-key callback
  Timestamp validity + ReplayCache
  Signature/ID/coverage checks + BSP
  Principal mapping + authorization
~~~

Đây là **checklist cấu hình**, không phải code có thể copy thành production mà bỏ các bước. Khi chỉ cấu hình `setSecurementActions("Signature Encrypt")` nhưng không chỉ định signer/private key/recipient certificate, ứng dụng có thể không khởi tạo hoặc thất bại khi gửi.

### 13.2. SignatureConfirmation

Với một số profile, bên gửi muốn kiểm chứng rằng phía nhận xác nhận đã xử lý signature của request trong response. Spring-WS hỗ trợ `setEnableSignatureConfirmation(true)`.

Chức năng này gắn với **cặp request–response**, cần cả inbound validation và outbound securement/response processing như tài liệu chính thức mô tả. **Không bật chỉ vì thấy tên có chữ “confirmation”**: hãy kiểm tra SOAP exchange pattern, WS-Addressing callbacks và khả năng hỗ trợ của hai phía. Một response có `SignatureConfirmation` không thay business acknowledgment hay transaction commit.

### 13.3. BSP và thuật toán

Spring-WS/WSS4J có:

~~~java
interceptor.setBspCompliant(true);
interceptor.setAllowRSA15KeyTransportAlgorithm(false);
interceptor.setStrictActionChecking(true);
~~~

Đây là các lựa chọn thực thi policy ở mức WSS4J; một số là mặc định trong Spring-WS 4.1, nhưng **không nên chỉ dựa vào default khi yêu cầu compliance**. BSP giúp loại các dạng thông điệp không phù hợp WS-I Basic Security Profile; không thay chứng chỉ trust/authorization. Lựa chọn thuật toán cần được review với chính sách bảo mật doanh nghiệp và khả năng tích hợp.

## 14. SOAP Fault và lỗi bảo mật trong interceptor

Lỗi bảo mật không phải lỗi validation dữ liệu nghiệp vụ thông thường. Spring-WS/WSS4J có thể ném:

| Nhóm | Exception | Bối cảnh |
| --- | --- | --- |
| **Inbound validation** | `WsSecurityValidationException` | UsernameToken sai, signature invalid, timestamp không hợp lệ, decrypt failed |
| **Outbound securement** | `WsSecuritySecurementException` | Không tìm được private key, Crypto/algorithm config sai, không ký/mã hóa được |
| **Business/domain** | Exception của service | Order không tồn tại, caller không có quyền, DB lỗi |
| **HTTP/TLS transport** | I/O hoặc TLS exception | Chưa lập được kết nối, proxy error, mTLS handshake |
| **XML parser/contract** | Parsing/JAXB/schema exception | XML sai, request không hợp XSD |

Theo Spring-WS Reference 4.1, security exceptions có đường xử lý **riêng của interceptor**, không nhất thiết đi qua `SoapFaultMappingExceptionResolver` của endpoint. Mặc định, `handleValidationException` tạo **SOAP 1.1 Client** hoặc **SOAP 1.2 Sender** Fault. `handleSecurementException` thường log lỗi và dừng xử lý message.

### 14.1. Response SOAP Fault minh họa

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
    <soapenv:Body>
        <soapenv:Fault>
            <faultcode>soapenv:Client</faultcode>
            <faultstring>Thông điệp không đáp ứng chính sách bảo mật</faultstring>
        </soapenv:Fault>
    </soapenv:Body>
</soapenv:Envelope>
~~~

Đây là **mẫu hình thức**, không phải cam kết text Fault mặc định của Spring-WS. Không để message công khai tiết lộ rằng “alias signing-key-prod không tồn tại”, “truststore chứa CA X” hay “user tenant B tồn tại nhưng mật khẩu sai”.

### 14.2. Nhánh lỗi có thể không tạo được SOAP Fault

Một số lỗi xảy ra **trước SOAP processing**:

- TLS handshake/mTLS client certificate không hợp lệ.
- HTTP reverse proxy từ chối request size hoặc trả 502/504.
- XML parser không thể đọc Envelope hoặc request bị chặn trước dispatcher.
- Server chết/timeout trước khi ghi phản hồi.

Những lỗi này có thể trả HTTP error, reset kết nối hoặc timeout **không chứa SOAP Fault**. Client không nên catch mọi `WebServiceIOException` rồi ép đọc `SoapFault`.

### 14.3. Không để security Fault kích hoạt callback nguy hiểm

Nếu request có WS-Addressing `FaultTo` non-anonymous, server có thể được yêu cầu gửi Fault tới URI do caller cung cấp. **Không gửi bảo mật failure tới URI chưa tin cậy** trước khi xác minh danh tính/đích. Khi sử dụng out-of-band replies, cần ordering phù hợp giữa WSS4J và WS-Addressing interceptor, kèm callback destination allowlist.

## 15. WS-Addressing, SOAP Headers và thứ tự interceptor

WS-Addressing có `wsa:Action`, `To`, `MessageID`, `ReplyTo`, `FaultTo`. WSS4J có `wsse:Security`. Nếu action/target được quyết định bởi một Header chưa xác minh, an toàn phụ thuộc **cách bảo vệ và xử lý** Header đó.

~~~mermaid
flowchart TD
    A["SOAP Header có wsa:Action/To/ReplyTo"] --> B["SOAP parser + route discovery"]
    B --> C["WSS4J verify signature/credential"]
    C --> D{"Header quan trọng được ký/bảo vệ?"}
    D -->|Không| E["Từ chối hoặc không tin Header"]
    D -->|Có| F["Authorization + destination policy"]
    F --> G["@Action endpoint / response callback"]
~~~

Sơ đồ là **mô hình tin cậy**, không phải bảo đảm vật lý rằng endpoint mapping diễn ra sau signature validation. Một số mapping có thể cần đọc Action trước để chọn endpoint. Vì vậy, **phải ngăn side effects và outbound callbacks cho đến khi WSS4J đã xác minh security theo policy**.

### 15.1. Những Header nào thường nên được bảo vệ?

| Header | Vì sao cần xem xét? |
| --- | --- |
| `wsu:Timestamp` | Không cho attacker sửa thời hạn còn hiệu lực |
| `wsa:Action` | Tránh thay operation intent |
| `wsa:To` | Tránh thay logical destination/tenant routing |
| `wsa:ReplyTo`, `FaultTo` | Tránh sửa callback destination, SSRF/data exfiltration |
| Custom `TenantId`, `CorrelationId` | Chỉ xem là dữ liệu đáng tin nếu được bảo vệ/ràng buộc phù hợp |
| SOAP Body | Dữ liệu nghiệp vụ chính phải được bảo vệ theo chính sách |

Một `CorrelationId` tự do, dù được log, **không phải chứng cứ authentication**. Nếu nó ảnh hưởng phân quyền hoặc xử lý idempotency, phải ràng buộc với principal/body theo policy.

### 15.2. Thứ tự đăng ký interceptors

Khi sử dụng `WsConfigurer.addInterceptors(...)`, các interceptors có thể chạy qua `handleRequest`, `handleResponse`, `handleFault` và `afterCompletion` theo lifecycle Spring-WS. Cần hiểu:

- Security outbound **phải bảo vệ phiên bản cuối** của SOAP Body/Header được gửi.
- Thêm/sửa Header đã nằm trong signature sau khi ký có thể làm signature invalid.
- Input validation, payload logging hoặc domain interceptor không được **tin dữ liệu chưa được xác minh**.
- Spring-WS xử lý WS-Addressing out-of-band có yêu cầu đặc biệt: **security interceptor trước addressing interceptor** để không gửi Fault tới attacker-chosen `FaultTo`.
- Khi một interceptor trả `false` hoặc ném lỗi, các callback còn lại/response behavior phụ thuộc lifecycle; kiểm thử **cả thành công và lỗi**.

Đừng thay interceptor order chỉ vì muốn response có một Header tiện log; kiểm tra lại security coverage và fault path.

## 16. XSD/JAXB, XML parser, MTOM và WS-Security

Trong module contract-first, XSD/JAXB và WSS4J cùng nhìn SOAP message nhưng **khác trách nhiệm**:

~~~text
TLS/HTTP request bounds
  ↓
Safe XML/SOAP parsing + attachment bounds
  ↓
WS-Security validation/decryption/signature coverage
  ↓
XSD validation + JAXB unmarshal
  ↓
Authentication identity + authorization
  ↓
Business rules / transaction / idempotency
  ↓
JAXB marshal response / schema checks
  ↓
WS-Security securement outbound + transport
~~~

Đây là **thứ tự điều kiện an toàn logic**, không phải API call order cố định. Một số parser/endpoint mapping callbacks có thể xảy ra sớm hơn; XML parsing tối thiểu buộc phải xảy ra trước khi xác minh signature. Điều bất biến là **không có tác dụng phụ nghiệp vụ trước khi các security checks cần thiết đạt**.

### 16.1. XML security độc lập với WSS4J

WSS4J không phải lý do để cho phép XML External Entities (XXE), DTD ngoài hoặc schema import tùy ý từ Internet trong parser. Cần:

- Cấu hình parser/transformer/JAXB chống XXE/SSRF và XML entity expansion.
- Giới hạn SOAP message size, depth, nodes, headers, attachments và timeout.
- Dùng schema catalog/import resolution đáng tin cậy.
- Kiểm soát XML canonicalization, ID attributes và signature references.
- Không tin payload bị giải mã trước khi hoàn tất verify/authorization theo policy.

### 16.2. MTOM attachment signature/encryption

Nếu SOAP message sử dụng **MTOM/XOP**, dữ liệu binary có thể nằm trong MIME parts ngoài phần XML root. **Ký SOAP Body không mặc nhiên có nghĩa mọi attachment được bảo vệ**: điều này phụ thuộc cơ chế signature/XOP transform và security profile của hai phía.

Spring-WS 4.1 cung cấp:

~~~java
interceptor.setAttachmentCallbackHandler(attachmentCallbacks);
~~~

`setAttachmentCallbackHandler(CallbackHandler)` hỗ trợ WSS4J xử lý ký/mã hóa attachments theo khả năng stack. `attachmentCallbacks` phải hiện thực callback semantics phù hợp với MIME/attachment processing và được đăng ký **cùng SOAP message factory hỗ trợ attachments**. Không phải cứ có method setter là mọi MTOM attachment tự được ký.

Để xác minh, test một **file nhị phân có checksum cố định**, rồi sửa một byte trong MIME part. Nếu hợp đồng yêu cầu attachment signed/encrypted, server/client **phải từ chối** phiên bản bị sửa. Đồng thời test trường hợp Body signature hợp lệ nhưng attachment không được bảo vệ để phát hiện lỗ hổng coverage.

### 16.3. Không xem Base64 decoding là signature verification

JAXB có thể chuyển `xs:base64Binary` thành `byte[]` hoặc `DataHandler`; việc chuyển đổi thành công chỉ chứng minh XML/MIME parse được. Một hash SHA-256 do **client tự khai báo** cũng có thể bị sửa cùng file nếu không được bảo vệ bằng chữ ký/chính sách đáng tin. Hash giúp kiểm tra tính nguyên vẹn end-to-end trong test; **không thay thế chữ ký xác thực nguồn**.

## 17. Kiến trúc xác thực và phân quyền theo đối tác

Ví dụ dịch vụ `GetOrder` và `CancelOrder` cùng đi qua `/soap/orders`. Partner A được xem dữ liệu của tenant A; Partner B được hủy đơn của tenant B. Sau WS-Security validation:

~~~text
X509 signer fingerprint / UsernameToken principal
          ↓
VerifiedPartnerIdentity { partnerId, tenantId, capabilities }
          ↓
Check SOAP Action + Body QName policy
          ↓
Check operation permission
          ↓
Check resource ownership of orderId
          ↓
Domain operation
~~~

**Không map identity bằng một Header do caller tự khai báo** nếu Header đó không được bảo vệ. Certificate subject DN hoặc alias cũng cần được ánh xạ theo **trust policy và allowlist**, chứ không phải `substring("CN=")` rồi mặc định tin.

| Tình huống | Kiểm tra bắt buộc |
| --- | --- |
| Partner có cert hợp lệ nhưng đã bị ngừng hợp đồng | Revocation/allowlist và trạng thái account |
| Partner A cố gọi CancelOrder của B | Authorization theo principal + resource/tenant |
| SOAP Body ký đúng nhưng `wsa:Action` bị sửa | Action/Body/Signature coverage |
| UsernameToken đúng nhưng không có role | Authentication thành công, authorization thất bại |
| Đơn hàng của tenant khác được hỏi qua GetOrder | Không để lộ existence hoặc nội dung |
| Request timeout sau khi đã ghi dữ liệu | Business idempotency và reconciliation |

Authorization nên trả mã lỗi/Fault đã chuẩn hóa, không tiết lộ điều kiện nội bộ như “tenant B tồn tại” cho caller không có quyền.

## 18. Chiến lược kiểm thử tích hợp WSS4J

Chỉ unit test:

~~~java
endpoint.getOrder(request);
~~~

**không kiểm tra được WS-Security**: lời gọi trực tiếp không đi qua SOAP Header, WSS4J interceptor, HTTP sender, certificate trust hay Fault processing. Cần kiểm thử theo từng lớp.

| Lớp test | Công cụ | Điều chứng minh |
| --- | --- | --- |
| **Key material và Crypto** | Test keystore/certificate fixture | Alias tồn tại, private/public keys đúng, trust chain và expiry theo policy |
| **WSS4J processing** | Spring test context, interceptor thực | UsernameToken, Timestamp, Signature, Encrypt được tạo/verify theo config |
| **Server SOAP** | `MockWebServiceClient` | Inbound request đi qua endpoint mappings/interceptor và tạo success/Fault |
| **Client SOAP** | `MockWebServiceServer` | `WebServiceTemplate` tạo WS-Security Header, xử lý inbound response/Fault |
| **HTTP(S) integration** | Embedded HTTPS test endpoint/proxy | TLS/mTLS và SOAP security cùng hoạt động, không nhầm tầng |
| **Cross-platform** | Java, .NET/WCF, ESB/SOAP stack đối tác | Interoperability ở SOAP version, key identifiers, algorithms, canonicalization |
| **Load/security negative** | Test harness có kiểm soát | Replay, clock skew, XSW, throughput, file/attachment and signature limits |

### 18.1. Server test: request không có WS-Security Header

Giả sử Spring test context đã đăng ký `@Endpoint` có payload root `{urn:example:orders:v1}GetOrderRequest` và cấu hình **inbound security yêu cầu UsernameToken/Timestamp**:

~~~java
import static org.springframework.ws.test.server.RequestCreators.withPayload;
import static org.springframework.ws.test.server.ResponseMatchers.clientOrSenderFault;

import org.springframework.xml.transform.StringSource;
import org.springframework.ws.test.server.MockWebServiceClient;

String xml = """
    <ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
        <ord:orderId>ORD-1024</ord:orderId>
    </ord:GetOrderRequest>
    """;

MockWebServiceClient client =
        MockWebServiceClient.createClient(applicationContext);

client.sendRequest(withPayload(new StringSource(xml)))
        .andExpect(clientOrSenderFault());
~~~

Đây là **ví dụ test rút gọn**: `applicationContext` phải được khởi tạo trong test, endpoint mapping phải thực sự chọn handler và security interceptor phải nằm trong chain. Nếu request không map được endpoint, kết quả có thể không đi qua WSS4J như ý định test. Hãy assert thêm **domain service chưa được gọi và không có transaction/side effect**. Khi test dựa vào Fault matcher, xác nhận tên API với phiên bản `spring-ws-test` của dự án.

**Điểm thiết yếu:** `withPayload(...)` **chỉ tạo SOAP Body**, không tạo UsernameToken hay Signature. Nó phù hợp test âm “thiếu security header”, nhưng **không phải positive test WS-Security**.

### 18.2. Positive server test dùng một SOAP client ký thật

Để kiểm chứng signature trust và cryptography:

1. Tạo **test CA**, signer certificate và keystore fixture; không dùng production private keys.
2. Cấu hình `WebServiceTemplate` hoặc WSS4J client interceptor ký một request đúng `GetOrderRequest`.
3. Gửi qua test server đã bật `Wss4jSecurityInterceptor` với truststore chứa đúng certificate/trust anchor.
4. Assert request được chấp nhận, endpoint gọi đúng **một lần**, response đúng XSD.
5. Capture SOAP request ở môi trường thử nghiệm và kiểm chứng `ds:Signature` bao phủ Body/Header theo policy.
6. Đổi public cert/truststore sang không đáng tin: request phải bị từ chối, domain không chạy.

Không dùng một fixture `<wsse:Security/>` rỗng rồi gọi đó là “request có chữ ký”. Chữ ký thực phụ thuộc private key, canonicalization, digest, references và certificate.

### 18.3. Test client-side với MockWebServiceServer

`MockWebServiceServer` kiểm thử `WebServiceTemplate` phía **client**:

- Outbound `ClientInterceptor` có tạo `wsu:Timestamp`, `wsse:UsernameToken` hoặc `ds:Signature` không?
- Body JAXB có đúng QName và nội dung sau securement không?
- Khi server trả SOAP Fault, client phân loại đúng mà không coi Fault là success DTO?
- Khi server trả response đã ký, client có thực sự xác minh signature trước khi sử dụng dữ liệu không?

**Giới hạn:** một response được stub chỉ bằng `withPayload(...)` thường không mang chữ ký/WS-Security Header đầy đủ; nếu client cấu hình yêu cầu response signed, test đó có thể **thất bại đúng chính sách**. Để test inbound signature, cần tạo response SOAP đã ký thật bằng test WSS4J responder hoặc fixture được xây với keystore test, thay vì tắt validation cho test vượt qua.

### 18.4. Kiểm thử phiên bản SOAP 1.1/1.2

| Thuộc tính | SOAP 1.1 | SOAP 1.2 |
| --- | --- | --- |
| Envelope | `http://schemas.xmlsoap.org/soap/envelope/` | `http://www.w3.org/2003/05/soap-envelope` |
| MustUnderstand | `soapenv:mustUnderstand="1"` | SOAP 1.2 xử lý thuộc tính theo SOAP 1.2 |
| Fault nhóm client | `Client` | `Sender` |
| Fault structure | `faultcode/faultstring` | `Code/Reason` |
| WS-Security | `wsse:Security` với policy đã thỏa thuận | `wsse:Security` với policy đã thỏa thuận |

Không chỉ thay `Content-Type` mà giữ SOAP 1.1 Envelope khi chuyển sang SOAP 1.2. Signature/encryption parts phải dùng đúng **QName namespace của Body** theo phiên bản.

## 19. Ma trận negative tests WS-Security

Một bài test bảo mật mạnh phải chứng minh **không chấp nhận điều xấu**. Ma trận dưới đây áp dụng cho partner integration có UsernameToken, Timestamp và X.509 Signature; bỏ những mục không thuộc policy đã công bố.

| Nhóm | Cách làm sai request | Kỳ vọng |
| --- | --- | --- |
| **Header thiếu** | Không có `wsse:Security` | Bị từ chối trước nghiệp vụ |
| **Username sai** | Username không trong allowlist | Từ chối, không tiết lộ user tồn tại |
| **Password sai** | PasswordText/Digest không hợp lệ | Từ chối, không gọi domain |
| **PasswordType sai** | Đổi Text ↔ Digest trái policy | Từ chối hoặc xử lý đúng policy, không hạ cấp |
| **Nonce trùng** | Gửi lại cùng UsernameToken nonce | Replay detection từ chối |
| **Timestamp hết hạn** | `Expires` ở quá khứ | Từ chối theo policy |
| **Timestamp tương lai** | `Created` vượt clock skew cho phép | Từ chối |
| **Replay xuyên node** | Gửi cùng signed message tới hai server pods | Không được xử lý lại nếu replay policy yêu cầu |
| **Signer không tin cậy** | Cert từ CA hoặc partner khác | Từ chối theo trust/identity binding |
| **Cert hết hạn** | NotAfter đã qua | Từ chối theo PKI policy |
| **Cert bị thu hồi** | Revoked cert theo chính sách | Từ chối nếu revocation required |
| **Chữ ký hỏng** | Đổi một ký tự trong signed Body | Signature invalid, không side effect |
| **Header không được ký** | Sửa `wsa:Action` hoặc `TenantId` nằm ngoài coverage | Từ chối nếu Header ảnh hưởng quyết định bảo mật |
| **XML Signature Wrapping** | Chèn Body khác, giữ node cũ đã ký | Không dùng unsigned Body |
| **ID trùng** | Hai nodes có cùng `wsu:Id` | Parser/verify từ chối ambiguous references |
| **Digest yếu** | Thay algorithm URI không được phép | Từ chối |
| **Wrong action order** | Thay thứ tự các WSS4J actions so với policy | Bị strict validation từ chối |
| **BSP violation** | Tạo token không phù hợp BSP | Bị từ chối khi BSP enforcement bật |
| **RSA 1.5 inbound** | Dùng key transport bị cấm | Từ chối, không bật ngoại lệ tùy tiện |
| **Decryption wrong key** | EncryptedKey dùng recipient không khớp | Không giải mã/không chạy nghiệp vụ |
| **Attachment sửa bytes** | Sửa một byte MIME part đã được policy bảo vệ | Chữ ký/attachment validation từ chối |
| **SOAP version sai** | Envelope 1.2 tới stack chỉ hỗ trợ 1.1 | VersionMismatch/HTTP error thích hợp |
| **Header có secret bị log** | Bật payload tracing trong môi trường test | Test/đánh giá redaction không lộ credentials |
| **Không có authz** | Signer đúng nhưng gọi operation ngoài quyền | Bị authorization từ chối |
| **Security Fault + FaultTo nội bộ** | Đặt `FaultTo=http://127.0.0.1/...` | Không kết nối outbound tới URI không tin cậy |

**Đừng chấp nhận test chỉ vì HTTP status là 500.** Phải xác minh domain service **không được gọi**, không có đơn/tài khoản bị thay đổi, không có callback SSRF, và server không rò chi tiết trust/password. HTTP status/Fault cụ thể phải đối chiếu SOAP version và đường xử lý lỗi.

### 19.1. Negative test quan trọng nhất: chữ ký hợp lệ nhưng không đủ

Thiết kế một test có **chữ ký mật mã hợp lệ trên một node** nhưng **SOAP Body được tiêu thụ chứa nội dung không được ký**, hoặc Action/To đã bị sửa sau khi ký. Mục tiêu không phải vô hiệu hóa WSS4J; mục tiêu là chứng minh application/framework **không tin dữ liệu ngoài signed coverage**.

Tùy SOAP stack, việc tạo fixture XSW đòi công cụ bảo mật chuyên dụng; sử dụng môi trường kiểm thử cô lập và dữ liệu giả. Không bao giờ dùng production private key hoặc gửi malformed signed requests đến hệ thống bên ngoài khi chưa được phép.

## 20. Interoperability: Spring-WS với .NET/WCF, ESB và SOAP stacks khác

WS-Security là chuẩn nhưng các công cụ khác nhau có thể sử dụng **profiles, thuật toán, key identifiers và vị trí Header** khác nhau.

| Khía cạnh | Bên gửi và nhận phải thống nhất |
| --- | --- |
| SOAP version | 1.1 hay 1.2, Envelope/Content-Type/Fault behavior |
| WS-Security version | Token profiles và namespaces đúng hợp đồng |
| UsernameToken | PasswordText/Digest, Nonce, Created, timestamp/replay policy |
| X.509 key reference | `IssuerSerial`, `DirectReference`, `BinarySecurityToken` profile |
| Signature | Signed Body/Headers, canonicalization, SignatureMethod, DigestMethod |
| Encryption | Content/Element scope, AES mode, RSA-OAEP/key transport |
| Certificate trust | CA chain, partner identity mapping, expiration/revocation |
| Timestamp | TTL, clock skew, time synchronization |
| WS-Addressing | `Action/To/ReplyTo/FaultTo`, signature coverage |
| MTOM | Signature/encryption of SOAP and MIME attachments, XOP transforms |
| SOAP Fault | Correct security failure classification, no leaked internals |

### 20.1. Một bộ fixture liên thông cần có

~~~text
1. Unsecured request    → phải bị từ chối nếu security required
2. Valid signed request → phải được chấp nhận
3. Wrong signer request → phải bị từ chối
4. Expired timestamp    → phải bị từ chối
5. Exact replay         → phải bị từ chối theo policy
6. Signed request + bad Header outside coverage
                       → bị từ chối nếu Header ảnh hưởng bảo mật
7. Secured response     → client verify/decrypt được
8. Security SOAP Fault  → client xử lý được, không lộ secret
9. Large/MTOM message   → coverage theo attachment policy
10. SOAP 1.2 equivalent → đúng Envelope/Fault/version policy
~~~

Đặc biệt với .NET/WCF, đôi khi một SOAP stack yêu cầu **timestamp được ký**, X.509 token ở `BinarySecurityToken` hoặc những canonicalization options khác; không tự suy những yêu cầu này chỉ từ XSD Body. **Hãy lấy WSDL/WS-Policy và một gói request được cả hai phía xác nhận** làm chuẩn kiểm thử.

### 20.2. Lấy bằng chứng nhưng không lộ secrets

Trong phòng thử nghiệm, có thể lưu:

- WSDL/XSD/WS-Policy version.
- Tên algorithms/alg URIs, key identifier type và **public** certificate fingerprint.
- Danh sách QName của signed/encrypted parts.
- Fault codes, loại lỗi validation, timestamp/replay outcome.
- Correlation ID đã lọc, latency và kích thước payload.

**Không lưu** private keys, key passwords, UsernameToken plaintext/digest, raw Authorization headers, full signed request có PII hoặc dữ liệu khách hàng thực vào ticket, dashboard hay repository.

## 21. Quan sát, vận hành và tối ưu hiệu năng

WS-Security có thể tiêu tốn CPU/RAM vì canonicalization, XML parsing, cryptography, attachments và certificate chain validation. **Thêm `Signature`/`Encrypt` không miễn phí**; với tải lớn, cần đo chứ không giả định throughput của SOAP client/server giống khi chưa bật security.

### 21.1. Metrics nên thu

| Metric | Mục đích |
| --- | --- |
| `soap.security.validation.count` theo outcome | Tỷ lệ accepted/rejected theo partner |
| `soap.security.validation.latency` | Tốn thời gian verify/decrypt bao nhiêu |
| `soap.security.securement.latency` | Tốn thời gian sign/encrypt outbound |
| `soap.security.replay.rejected` | Số replay attempts bị từ chối |
| `soap.security.timestamp.rejected` | Lỗi expired/future timestamps |
| Certificate expiry remaining days | Chủ động rotation |
| Cache hit/eviction/size | Replay detection có đủ bộ nhớ/TTL không |
| SOAP request/response bytes | Giới hạn size, tải và attachment overhead |
| SOAP Fault codes | Phân loại lỗi protocol/security/business |
| Failed authentication by partner | Detect abuse, nhưng tránh high-cardinality raw usernames |

Đây là **tên metric gợi ý do ứng dụng tự định nghĩa**, không phải metrics mặc định mà WSS4J nhất định tự xuất. Không dùng raw UsernameToken username/nonce hoặc certificate subject text làm metric labels không kiểm soát, vì vừa nhạy cảm vừa gây cardinality cao.

### 21.2. Nguyên tắc logging

- Log **loại lỗi**, operation, SOAP version, partner ID đã xác minh (nếu có) và correlation ID đã lọc.
- Redact `wsse:Security`, mật khẩu, nonce, token, private key/cert secrets; đặc biệt thận trọng với `SoapEnvelopeLoggingInterceptor` hoặc HTTP wire logs.
- Không log decrypted sensitive Body mặc định ở production.
- Phân biệt validation error, securement error, transport error và business Fault.
- Với lỗi certificate, log nội bộ thông tin tối thiểu đã lọc; phản hồi client bằng Fault trung tính.
- Quản lý retention/audit access theo quy định bảo vệ dữ liệu của tổ chức.

### 21.3. Certificate/key rotation

Một quy trình rotation nên:

1. Công bố fingerprint và public certificate mới theo kênh tin cậy.
2. Cho truststore server/client nhận **đúng hai certificate trong cửa sổ chuyển đổi** nếu policy cho phép.
3. Đổi alias/private key signing trong configuration theo lịch.
4. Kiểm thử success và failure với old/new signer.
5. Xóa trust cũ sau khi hết thời gian chuyển đổi, xác minh revocation/expiry.
6. Theo dõi các connection TLS và SOAP signature; key rotation ở WS-Security **không tự đổi TLS cert**.

Không tự chuyển tất cả đối tác về “trust all certs” khi gặp lỗi rotation. Nếu dùng HSM/KMS, cần thiết kế cách WSS4J `Crypto`/provider sử dụng key mà không xuất private key ra file không kiểm soát.

## 22. Chẩn đoán lỗi Wss4jSecurityInterceptor

| Triệu chứng | Nghi ngờ chính | Cách xác minh |
| --- | --- | --- |
| Không thấy `wsse:Security` | Interceptor chưa gắn vào template/endpoint hoặc `securementActions` rỗng | Runtime bean, interceptor chain, SOAP message |
| `No endpoint found` | SOAP routing xảy ra trước endpoint interceptor | QName, SOAPAction/WS-A, mappings |
| `InvalidSecurity` | Token không hợp profile, signature/decryption hỏng | Fault + WSS4J logs đã lọc, test fixture |
| UsernameToken sai dù username đúng | PasswordType/Digest/nonce/callback secret lệch | CallbackHandler, token profile, clock |
| Request replay bị từ chối khi retry | Reuse nonce/timestamp/signed message | Retry policy, replay cache, business idempotency |
| Replay được chấp nhận trên pod khác | Cache chỉ cục bộ một node | Cross-node replay test, distributed cache |
| Signature verification failed | Wrong truststore, cert, signed bytes hoặc canonicalization | Crypto, cert chain, SOAP namespace, XML transforms |
| Signature valid nhưng tenant sai | Không bind signer identity với tenant/operation | Authorization + coverage policy |
| `KeyStoreException` / wrong alias | Keystore type/password/alias sai | CryptoFactoryBean config, local test keys |
| Private key unavailable | Chỉ có public trust cert, thiếu signer/decrypter key | Phân biệt signing/decryption key material |
| Decryption failed | Recipient alias/key transport/algorithm sai | Envelope encrypted parts, private key mapping |
| Wrong action order | `validationActions` khác thứ tự actual WS-Security | Đối chiếu WSS4J action processing order |
| SOAP 1.1 chạy nhưng 1.2 lỗi | Body namespace/Content-Type và signature parts hardcode 1.1 | SOAP factory, QName signed parts |
| WS-Addressing Header bị sửa sau ký | Callback/interceptor order sai hoặc proxy rewrite | Signature references, Action/To, proxy |
| SOAP Fault không qua resolver | Security exception được xử lý ở interceptor | `handleValidationException` và Fault branch |
| HTTP 502 không có SOAP Fault | Proxy/transport lỗi trước SOAP processing | HTTP/TLS/gateway logs |
| UsernameToken hợp lệ nhưng domain bị từ chối | Authorization thất bại | Principal/roles/tenant/resource policy |
| Test pass nhưng .NET/WCF fail | Canonicalization, key identifier hoặc WS-Policy khác | So wire XML và policy; test cả hai chiều |
| File MTOM được nhận nhưng signature không phủ bytes | Attachment-specific coverage chưa cấu hình | Tamper binary MIME part, WSS4J callback profile |
| Heap tăng mạnh khi ký file lớn | DOM/canonicalization/buffering/attachments | Heap profiler, concurrency, streaming limits |
| Lỗi do thiếu thư viện | WSS4J/SAAJ/XML-Security version lệch | Dependency management đúng bản Spring-WS |

### Lưu đồ tìm nguyên nhân theo tầng

~~~mermaid
flowchart TD
    A["SOAP call thất bại"] --> B{"TLS/HTTP và XML parse OK?"}
    B -->|Không| C["Truststore/mTLS/proxy/XML hardening"]
    B -->|Có| D{"Endpoint có security interceptor?"}
    D -->|Không| E["WsConfigurer/mapping/template config"]
    D -->|Có| F{"Token, timestamp, replay OK?"}
    F -->|Không| G["UsernameToken/callback/TTL/cache"]
    F -->|Có| H{"Signature/decryption và trust OK?"}
    H -->|Không| I["Crypto, alias, algorithms, signed parts"]
    H -->|Có| J{"Signed data là data ứng dụng dùng?"}
    J -->|Không| K["Reject: XSW, header/body coverage"]
    J -->|Có| L{"Principal được phép?"}
    L -->|Không| M["Authorization fault"]
    L -->|Có| N["XSD/JAXB + domain → secured response"]
~~~

Đây là **quy trình chẩn đoán**, không phải thứ tự callback bảo mật thực tế trong mọi runtime. Điều quan trọng là không để một đường xử lý lỗi hoặc mapping khác **bỏ qua security policy**.

## 23. Bài tập tự đánh giá

### Bài 1 — Thiết lập UsernameToken/Timestamp

Tạo `Wss4jSecurityInterceptor` phía client với `securementActions="UsernameToken Timestamp"`, nonce/created và password từ secret test. Phía server dùng `validationActions` tương ứng cùng callback handler. Test đúng secret, sai secret, thiếu Header và timestamp hết hạn.

### Bài 2 — Chuyển sang signature X.509

Dùng keystore test có private key/certificate và truststore chứa trusted certificate. Cấu hình client ký SOAP Body, server xác minh. Đổi Body một ký tự; test phải bị từ chối và `OrderService` không chạy.

### Bài 3 — Xác nhận signed parts

Thêm Header `wsa:Action` và `TenantId` có ảnh hưởng authorization. Thiết kế policy ký Body cùng những Headers cần thiết; thử sửa từng Header sau khi ký. Giải thích vì sao `validationActions="Signature"` đơn lẻ chưa đủ.

### Bài 4 — Replay cache trong cluster

Đặt hai instances server nhận cùng request có UsernameToken nonce/signature. Kiểm tra cache riêng từng node có thể chấp nhận lại request; thiết kế shared `ReplayCache` thích hợp, áp TTL/quota và test retry không làm trùng nghiệp vụ.

### Bài 5 — Ký và mã hóa hai chiều

Thiết kế Partner A ký request bằng private key A, mã hóa cho server bằng public cert S; server giải mã bằng private key S và xác minh chữ ký bằng trust A. Server ký response bằng private key S, client xác minh bằng trust S. Vẽ vị trí bốn Crypto/certificate sets.

### Bài 6 — SOAP Fault và privacy

Cho request thiếu UsernameToken, sai signer trust, Timestamp hết hạn, và DB unavailable. Dự đoán lỗi xảy ra ở interceptor hay domain; thiết kế Fault không tiết lộ key aliases/SQL, đồng thời giữ audit nội bộ đủ cho xử lý sự cố.

### Bài 7 — WS-Addressing FaultTo và SSRF

Một client không hợp lệ gửi `FaultTo=http://127.0.0.1:8080/admin`. Thiết kế cơ chế không phát callback trước khi WSS4J validation, đồng thời kiểm callback destination bằng allowlist, DNS, redirect và outbound TLS policy.

### Bài 8 — MTOM attachment integrity

Gửi file qua MTOM với chính sách yêu cầu bảo vệ binary attachment. Sửa một byte trong MIME part sau khi ký; test nhận phải phát hiện và từ chối, không chỉ dựa vào XML Body signature hợp lệ.

### Bài 9 — Tương thích .NET/ESB

Lấy một request được đối tác ký hợp lệ và các thông số WS-Policy. Tạo client Spring-WS tái hiện SOAP version, Timestamp, key identifier, signature/digest algorithms, signed parts và `wsa:Action`. Test response signed/Fault và lỗi signature sau reverse proxy.

### Bài 10 — Security hardening review

Đọc một cấu hình đang có `setBspCompliant(false)`, `setAllowRSA15KeyTransportAlgorithm(true)`, không có replay cache và log raw SOAP Body. Liệt kê từng rủi ro, ưu tiên biện pháp sửa và thiết kế negative tests kiểm chứng không có regression.

## 24. Checklist trước khi triển khai production

| Nhóm | Điều kiện đạt |
| --- | --- |
| **Hợp đồng** | XSD/WSDL/SOAP version và WS-Policy/tổ hợp security actions được công bố rõ |
| **Dependencies** | spring-ws-security, Apache WSS4J/SAAJ/JAXB runtime tương thích |
| **Interceptor** | Đúng `@Endpoint` mappings và `WebServiceTemplate` có interceptor ở mọi đường cần bảo vệ |
| **Inbound** | ValidationActions đúng actions/thứ tự, strict checking và BSP phù hợp |
| **Outbound** | SecurementActions đúng; alias/secret/Crypto/parts/algorithms cấu hình đầy đủ |
| **UsernameToken** | PasswordText/Digest, nonce/created, callback secrets, principal identity theo policy |
| **Timestamp** | Clock sync, TTL, future skew, expired rejection và replay detection |
| **Replay cluster** | Cache có TTL/quota, khả năng chống replay giữa nhiều nodes |
| **Signature** | Trust cert/signer identity, coverage đúng Body/Header, chống XSW/duplicate IDs |
| **Encryption** | Key transport và AES/recipient cert hợp policy; private key decryption bảo vệ |
| **Certificate lifecycle** | Trust anchors, rotation, expiry/revocation/identity binding được kiểm toán |
| **Authorization** | Principal đã xác minh → scope/tenant/operation/resource checks |
| **Transport** | TLS/mTLS, hostname verification, HTTP timeouts và proxy rules độc lập với WS-Security |
| **XML/attachments** | Parser hardening, quotas, XSD/JAXB validation, MTOM parts được bảo vệ khi bắt buộc |
| **WS-Addressing** | Action/To/ReplyTo/FaultTo coverage, callback allowlist, security trước out-of-band |
| **SOAP Fault** | Security faults không lộ internals; client phân biệt Fault với TLS/HTTP errors |
| **Testing** | Positive/negative signed requests, tamper, replay, bad cert, XSW, SOAP 1.1/1.2, interop |
| **Observability** | Metrics và redacted logs, cảnh báo certificate expiry và security rejection |
| **Reliability** | Retry/idempotency tách biệt replay; không tự tạo giao dịch trùng |

## 25. Tài liệu chuẩn để đối chiếu API và bảo mật

Những ví dụ bài học dùng API Java/Spring-WS phổ biến ở **Spring-WS 4.1.x**, nhưng các setter, phiên bản WSS4J, chính sách thuật toán và extension points có thể thay đổi. Trước khi triển khai, đối chiếu tài liệu chính thức:

- [Spring Web Services 4.1.4 — Wss4jSecurityInterceptor JavaDoc](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/soap/security/wss4j2/Wss4jSecurityInterceptor.html): validation/securement actions, Crypto, callback, signed parts, replay cache, BSP và attachment callback.
- [Spring Web Services 4.1.4 — Reference: Securing Your Web Services](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/): UsernameToken, certificate trust, Timestamp, Signature, Encryption và security faults.
- [Spring-WS — WsConfigurer](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/config/annotation/WsConfigurer.html): đăng ký endpoint interceptors.
- [Apache WSS4J](https://ws.apache.org/wss4j/): WS-Security engine, Crypto, configuration, DOM/StAX processing và token profiles.
- [OASIS Web Services Security](https://docs.oasis-open.org/wss/): WS-Security SOAP Message Security và token profiles.
- [W3C XML Signature](https://www.w3.org/TR/xmldsig-core1/) và [XML Encryption](https://www.w3.org/TR/xmlenc-core1/): signed references/canonicalization và encrypted parts.
- [OWASP XML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_Security_Cheat_Sheet.html): parser hardening/XXE và các nguyên tắc xử lý XML từ nguồn không tin cậy.

**Kết luận:** `Wss4jSecurityInterceptor` là cầu nối giữa chuỗi xử lý SOAP của **SPRING_WEB_SERVICES** và **Apache WSS4J**. Nó giúp **tạo** WS-Security protection ở outbound và **xác minh/giải mã** ở inbound bằng `securementActions`/`validationActions`, UsernameToken callbacks, `Crypto`, Timestamp và ReplayCache. Nhưng **một chữ ký hợp lệ không tự là authorization**, và **một Header `wsse:Security` không tự chứng minh Body/Headers đã được bảo vệ đầy đủ**. Muốn tích hợp doanh nghiệp ổn định, hãy xác định policy theo đối tác, kiểm tra signed-parts coverage và signer identity, bảo vệ parser/TLS/MTOM, chống replay xuyên cluster, quản lý keys/certificates và kiểm thử cả request/response lẫn SOAP Fault trên wire thực tế.
