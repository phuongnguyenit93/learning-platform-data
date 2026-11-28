# validationActions, securementActions và thứ tự thực hiện hành động

## 1. Vì sao thứ tự hành động WS-Security quan trọng?

Trong module **SPRING_WEB_SERVICES**, ta xây dựng dịch vụ SOAP theo hướng contract-first: XSD/WSDL xác định hợp đồng XML và binding; JAXB/OXM chuyển đổi Java–XML; Spring Web Services xây dựng `@Endpoint`, `WebServiceTemplate`, SOAP Fault và interceptor. Khi tích hợp doanh nghiệp, thông điệp còn cần xác thực, toàn vẹn, bảo mật nội dung, giới hạn thời gian hiệu lực và khả năng tương tác giữa các hệ thống.

WS-Security bổ sung các thành phần bảo vệ vào **SOAP Header** và có thể biến đổi các phần trong SOAP Body. Trong Spring-WS, `Wss4jSecurityInterceptor` dựa trên Apache WSS4J giúp hai chiều:

- **Securement**: tạo token, timestamp, chữ ký hoặc mã hóa cho thông điệp **đang gửi đi**.
- **Validation**: đọc, kiểm tra và giải mã các thành phần bảo mật của thông điệp **nhận vào**.

Hai thuộc tính quyết định tập action ở ví dụ cấu hình là:

~~~java
interceptor.setSecurementActions("Timestamp Signature");
interceptor.setValidationActions("Timestamp Signature");
~~~

Chuỗi gồm **tên action cách nhau bằng khoảng trắng**. Không phải tên các Java methods mà ta tùy ý đặt; mỗi token phải được WSS4J/Spring-WS version sử dụng nhận diện.

**Điểm cốt lõi của bài:** thứ tự trong các chuỗi này có ý nghĩa. Spring-WS/WSS4J có thể đối chiếu những security actions thật sự tìm thấy trong thông điệp nhận với `validationActions`; không phải chỉ kiểm tra “có đủ các token ở đâu đó” theo tập hợp bất kỳ. Thứ tự còn ảnh hưởng tới việc một phần XML được **ký trước khi mã hóa** hay **mã hóa trước khi ký**, các phần nào thật sự được bảo vệ, và khả năng đối tác giải mã/kiểm chứng.

Tuy nhiên, không được đơn giản hóa thành quy tắc “cứ đảo ngược thứ tự validationActions so với securementActions”. Việc giải mã/kiểm chữ ký có các phụ thuộc kỹ thuật riêng, còn `validationActions` là **danh sách action inbound được mong đợi** theo kết quả và chính sách của interceptor/version. Hãy kiểm tra SOAP security header và test interoperability thực tế, nhất là khi kết hợp `Signature` với `Encrypt`.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích `securementActions` và `validationActions` theo **hướng message**, không theo vai trò business client/server cố định.
2. Nhận diện `UsernameToken`, `Timestamp`, `Signature`, `Encrypt`, `NoSecurity` và các action có giới hạn theo phiên bản.
3. Mô tả quá trình một WS-Security interceptor bảo vệ request/response và xác thực request/response.
4. Giải thích vì sao thứ tự action có thể làm thông điệp bị từ chối dù vẫn chứa đủ security elements.
5. Phân biệt thứ tự **security actions trong một interceptor** với thứ tự **nhiều ClientInterceptor/EndpointInterceptor**.
6. Biết các thành phần cần thiết để dùng chữ ký và mã hóa: private key, public certificate, crypto, password callback, certificate trust và policy.
7. Chọn giữa ký rồi mã hóa và mã hóa rồi ký theo hợp đồng bảo mật cụ thể.
8. Viết kiểm thử dương/âm cho action order, signature parts, certificate, timestamp, replay và SOAP Fault.
9. Đánh giá các khác biệt phiên bản Spring-WS/WSS4J, nhất là tên action encryption và API package.

## 2. Hai chiều thông điệp: outbound và inbound

Một SOAP service có thể vừa nhận request vừa gửi response. Còn một SOAP client thì làm ngược lại:

~~~mermaid
sequenceDiagram
    participant C as Spring-WS SOAP client
    participant S as Spring-WS SOAP server
    Note over C: Secure request outbound
    C->>S: HTTPS SOAP request + wsse:Security
    Note over S: Validate request inbound
    Note over S: Secure response outbound
    S-->>C: HTTPS SOAP response + wsse:Security
    Note over C: Validate response inbound
~~~

Tương ứng:

| Vai trò | Request | Response |
|---|---|---|
| **SOAP client** | `securementActions` áp dụng khi **gửi request** | `validationActions` áp dụng khi **nhận response** |
| **SOAP server** | `validationActions` áp dụng khi **nhận request** | `securementActions` áp dụng khi **gửi response** |

Đây là cách hiểu dễ nhớ nhất. **Securement không đồng nghĩa “phía server”; validation không đồng nghĩa “phía client”.** Cả hai bên đều có thể dùng cả hai, tùy bên nào đang gửi/nhận message.

### 2.1. Một chiều có thể có security policy khác chiều kia

Ví dụ một tích hợp:

~~~text
Client -> Server:
    Timestamp + UsernameToken + Signature

Server -> Client:
    Timestamp + Signature
~~~

Server cần:

~~~text
validationActions = "Timestamp UsernameToken Signature"
securementActions = "Timestamp Signature"
~~~

Client tương ứng cần:

~~~text
securementActions = "Timestamp UsernameToken Signature"
validationActions = "Timestamp Signature"
~~~

Đây là **bảng ý tưởng về action expectations**. Trong triển khai thật, chuỗi phải phù hợp thứ tự security processing do WSS4J phát sinh và đối tác công bố; đồng thời mỗi phía cần các cấu hình khóa/callback/parts tương ứng. Đặt đúng hai chuỗi chưa đủ để hoàn thành một policy ký số hoạt động.

### 2.2. Response có thể không cần cùng thuật toán với request

Một server có thể yêu cầu request đã ký nhưng cho phép response chỉ qua TLS; hoặc yêu cầu response cũng được ký, mã hóa, đính kèm timestamp. Điều đó phụ thuộc WSDL/WS-Policy và thỏa thuận của đối tác, **không được tự động suy từ việc request đã ký**.

Không bỏ validation response chỉ vì client tự tin rằng “HTTPS đã bảo vệ đường truyền” nếu hợp đồng yêu cầu WS-Security message-level signature.

## 3. Wss4jSecurityInterceptor là loại interceptor nào?

`Wss4jSecurityInterceptor` là thành phần Spring-WS xử lý WS-Security dựa trên WSS4J. Nó nằm trong chuỗi SOAP message processing và có thể được gắn phía:

- **Server**: thông qua cấu hình endpoint interceptors của Spring-WS.
- **Client**: thông qua `WebServiceTemplate#setInterceptors(...)`.

Trong các dòng Spring-WS 4.x sử dụng WSS4J 2 integration, package thường gặp là:

~~~java
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;
~~~

Một số tài liệu cũ dùng package `org.springframework.ws.soap.security.wss4j` hoặc cấu hình tương ứng với WSS4J 1.x/phiên bản Spring-WS cũ. **Không trộn import/package/API giữa các major versions** mà chưa kiểm tra artifact thực tế.

### 3.1. XML Spring bean và Java Config cùng diễn đạt một ý

Java Config tối giản minh họa hai thuộc tính:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

@Configuration
public class SoapSecurityConfiguration {

    @Bean
    public Wss4jSecurityInterceptor wsSecurity() {
        Wss4jSecurityInterceptor interceptor =
            new Wss4jSecurityInterceptor();

        interceptor.setValidationActions("Timestamp");
        interceptor.setSecurementActions("Timestamp");

        return interceptor;
    }
}
~~~

Cấu hình này chỉ đưa timestamp vào outbound message và yêu cầu timestamp inbound. Nó **không cung cấp authentication, signature hay encryption**; không được coi là WS-Security policy đầy đủ cho dữ liệu nhạy cảm.

Dạng XML bean tương ứng:

~~~xml
<bean id="wsSecurity"
      class="org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor">

    <property name="validationActions" value="Timestamp"/>
    <property name="securementActions" value="Timestamp"/>
</bean>
~~~

Khi chạy client/server, cần còn đăng ký bean này vào **đúng interceptor chain** và khai báo các thư viện/versions hỗ trợ.

### 3.2. Hai cấu hình không tự tạo bảo mật nếu không được gắn vào chain

Bean Spring được tạo thành công **không đồng nghĩa** interceptor được Spring-WS thực thi. Một service có thể có `@Bean Wss4jSecurityInterceptor` nhưng chưa register vào endpoint interceptors; một client có thể tạo bean nhưng `WebServiceTemplate` dùng một mảng interceptors khác.

Cần test request thực gửi có `wsse:Security` hoặc request không hợp policy bị từ chối. Đừng dựa vào việc application context khởi động thành công.

## 4. WS-Security Header là gì?

Một SOAP message có thể mang SOAP Header:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
    xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
    xmlns:ord="urn:example:orders:v1">

    <soap:Header>
        <wsse:Security soap:mustUnderstand="1">

            <wsu:Timestamp wsu:Id="TS-1">
                <wsu:Created>2026-11-27T02:30:00Z</wsu:Created>
                <wsu:Expires>2026-11-27T02:35:00Z</wsu:Expires>
            </wsu:Timestamp>

            <!-- UsernameToken, Signature hoặc EncryptedKey
                 tùy theo action policy và implementation. -->

        </wsse:Security>
    </soap:Header>

    <soap:Body>
        <ord:GetOrderRequest>
            <ord:orderId>ORD-2048</ord:orderId>
        </ord:GetOrderRequest>
    </soap:Body>
</soap:Envelope>
~~~

Đây là **XML minh họa về cấu trúc**, chưa có chữ ký, khóa hoặc mã hóa hợp lệ. Vì timestamp sử dụng ngày giờ cụ thể, không dùng chính fixture này như timestamp còn hiệu lực ở mọi thời điểm; các tests thật phải tạo thời gian dựa trên test clock và chính sách TTL.

### 4.1. QName của Security Header khác QName nghiệp vụ

Một SOAP message có ít nhất ba nhóm namespace:

- SOAP Envelope/Body.
- `wsse:Security` và `wsu:Timestamp`/ID.
- Business payload `ord:GetOrderRequest` theo XSD.

WS-Security không làm thay đổi mục tiêu contract-first: payload vẫn phải đúng XSD/WSDL, còn Header phải đúng WS-Security profile và security policy.

### 4.2. Không đọc vị trí XML node là đủ để suy action sequence

Thứ tự xuất hiện của các XML nodes trong `wsse:Security` có thể cung cấp dấu hiệu, nhưng chữ ký tham chiếu qua `ds:Reference`, nội dung có thể được mã hóa, và WSS4J có thể xử lý nhiều action results. Không kết luận trình tự mã hóa/ký chỉ dựa vào việc text string `<ds:Signature>` nằm trước hay sau `<xenc:EncryptedKey>` trong một log.

Hãy dùng WSS4J validation results, policy và **negative interoperability tests** để xác nhận action order.

## 5. Bảng action cơ bản

Từ góc nhìn một message, các action thường gặp là:

| Token | Securement outbound | Validation inbound | Điều cần chú ý |
|---|---|---|---|
| `UsernameToken` | Tạo UsernameToken | Kiểm tra UsernameToken | Cần callback/credential policy, TLS và replay guard |
| `Timestamp` | Tạo Created/Expires metadata | Kiểm tra thời gian hợp lệ | Clock skew, TTL, replay không chỉ timestamp |
| `Signature` | Tạo XML Signature | Kiểm tra chữ ký và trust | Private key vs public certificate, signed parts |
| `Encrypt` | Mã hóa XML parts | Giải mã XML parts | Recipient cert vs private decrypt key, algorithms |
| `UsernameTokenSignature` | Tạo UsernameToken và signature theo profile | Tùy version/policy, không suy tương đương `UsernameToken + Signature` | Kiểm tra WSS4J/profile cụ thể |
| `NoSecurity` | Không làm bảo vệ theo token này | Không kiểm tra action tương ứng | Không dùng làm cách bỏ bảo mật production |

**Chú ý phiên bản:** tài liệu Spring-WS 4.x vẫn mô tả `Encrypt` trong `Wss4jSecurityInterceptor`. Ở Apache WSS4J từ 2.3 có action name `Encryption` thay cho tên `Encrypt` trước đây trong một số configuration constants. Đây là khác biệt API/configuration **cần xác minh theo phiên bản thực tế**, không tự thay toàn bộ chuỗi `Encrypt` trong một Spring-WS app chỉ vì tài liệu WSS4J mới dùng `Encryption`.

### 5.1. Securement là hành động tạo, validation là hành động tiêu thụ

Khi bảo vệ outbound:

~~~text
Timestamp -> thêm thời gian
Signature -> ký những XML parts đã chọn
Encrypt   -> mã hóa những XML parts đã chọn
~~~

Khi inbound:

~~~text
Timestamp -> xác minh thời hạn
Signature -> kiểm chứng chữ ký
Encrypt   -> giải mã với private key phù hợp
~~~

Đây là **mô tả mục tiêu action**, không phải khẳng định thứ tự các operations nội bộ khi cùng một message vừa được ký vừa mã hóa. Việc WSS4J xử lý decryption/verification có thể phụ thuộc layout thực tế và loại ký–mã hóa.

### 5.2. Action names không đủ mô tả chính sách

`securementActions="Signature"` không tự nói:

- Chữ ký bao phủ Body, Timestamp hay business header nào.
- Sử dụng key alias/chứng chỉ gì.
- Signature algorithm/digest algorithm/canonicalization profile nào.
- Certificate chain có được partner trust không.
- Có yêu cầu xác minh `wsu:Id` và chống wrapping không.

Tương tự, `validationActions="Signature"` không có nghĩa người gửi được phép ký bằng **bất kỳ** chứng chỉ hợp lệ về mặt toán học; vẫn cần trust/authorization policy.

## 6. securementActions: bảo vệ thông điệp gửi đi

Cú pháp đơn giản:

~~~java
interceptor.setSecurementActions(
    "Timestamp Signature"
);
~~~

Ý định: outbound message có Timestamp và Signature theo cấu hình. Nếu yêu cầu cả mã hóa:

~~~java
interceptor.setSecurementActions(
    "Timestamp Signature Encrypt"
);
~~~

Nhưng khi kết hợp actions, **đừng lấy thứ tự này làm một mẫu cố định cho mọi đối tác**. WSDL/WS-Policy có thể yêu cầu protection order khác, ví dụ ký trước khi mã hóa hay ngược lại. Tập signed/encrypted parts và key identifiers cũng có thể khác.

### 6.1. Securement không thay bảo mật đường truyền

WS-Security cung cấp message-level integrity/confidentiality cho phần XML được ký/mã hóa. HTTPS/TLS lại bảo vệ kênh truyền giữa các network hops theo mô hình TLS. Nhiều hệ thống doanh nghiệp yêu cầu **cả hai**.

Một UsernameToken có password dạng digest không làm TLS trở nên không cần thiết. Certificate/public key trong SOAP Security Header cũng không tự thay thế certificate trust của HTTPS.

### 6.2. Nếu không có securementActions thì sao?

Không nên suy rằng một SOAP message outgoing sẽ được ký/mã hóa chỉ vì interceptor bean đã được đăng ký hoặc có `validationActions`. Nếu outgoing policy yêu cầu Signature mà không có outbound securement configuration tương ứng, thông điệp có thể thiếu chữ ký.

Ở chiều server, điều này đặc biệt dễ bị bỏ sót: xác minh request inbound thành công **không tự tạo chữ ký cho response outbound**.

### 6.3. Action order có thể ảnh hưởng signed data

Nếu Timestamp cần được bảo vệ khỏi sửa đổi, thêm Timestamp trước khi tạo Signature và **đưa đúng Timestamp element vào signature parts** là một hướng thiết kế thường gặp. Chỉ đưa `Timestamp` và `Signature` vào cùng chuỗi **không tự đảm bảo** Timestamp đã được ký.

Nếu encryption áp vào SOAP Body, quyết định ký cái gì (plaintext body, encrypted XML, wrapper hay các headers) phụ thuộc policy và trình tự được chọn.

## 7. validationActions: điều kiện đối với thông điệp nhận vào

Một cấu hình:

~~~java
interceptor.setValidationActions(
    "Timestamp Signature"
);
~~~

diễn tả **action profile inbound được mong đợi**. WSS4J kiểm tra message security, bao gồm yêu cầu về action matches/order theo cơ chế interceptor.

Quan trọng:

1. `validationActions` không phải lời nhắn “tự ký dữ liệu giúp tôi”; nó dùng cho message **đã nhận**.
2. Nó không chỉ đếm sự xuất hiện của `ds:Signature` trong SOAP text; cần xác minh chữ ký mật mã, signed references và trust policy.
3. Nếu action order thực tế khác điều interceptor mong đợi, message có thể bị từ chối.
4. Nếu một action cần key/callback mà chưa cấu hình, validation có thể thất bại dù XML syntactically hợp lệ.
5. Chữ ký hợp lệ và certificate được trust vẫn chưa chứng minh người gửi **được phép thực hiện operation**; cần authorization.

### 7.1. Tại sao không cứ khai báo NoSecurity?

Một cấu hình nhận bất cứ SOAP Body nào mà không xác minh signature/time có thể làm mất toàn bộ ý nghĩa WS-Security requirement của đối tác. `NoSecurity` chỉ phù hợp trong một profile thật sự không yêu cầu message security, ví dụ thử nghiệm tối thiểu đã tách môi trường. Không đặt `NoSecurity` để “làm cho test xanh” khi production policy yêu cầu ký/mã hóa.

### 7.2. Validation order không phải một whitelist unordered

Giả sử partner gửi token theo một order khác so với `validationActions`. Interceptor có thể từ chối dù tất cả token names đều xuất hiện, vì **order có ý nghĩa trong WSS4J policy enforcement**. Cần đồng bộ với partner tại **security action level**, không chỉ tại WSDL payload QName.

Tuy nhiên, khi phân tích mixed `Signature`/`Encrypt`, điều cần đối chiếu là **inbound action results** và cấu hình của đúng WSS4J version. Không viết một thuật toán thủ công đơn giản là đảo chuỗi securement rồi xem đó là quy tắc tiêu chuẩn.

## 8. Thứ tự có nhiều lớp khác nhau

Trong một SOAP integration có ít nhất **bốn thứ tự** cần phân biệt:

| Thứ tự | Nơi cấu hình | Tác động |
|---|---|---|
| **Action order outbound** | `securementActions` | Security operations tạo message |
| **Expected action order inbound** | `validationActions` | Điều kiện WSS4J dùng để chấp nhận message |
| **Interceptor chain order** | `WebServiceTemplate.setInterceptors` hoặc server interceptor registry | Khi nào headers, logging, validation, security được chạy |
| **XML element order** | XSD `xs:sequence` hoặc WS-Security layout | Cấu trúc XML hợp đồng/bảo mật |

Không nhầm các câu:

- “Ký sau khi thêm Header” = interceptor chain order.
- “Ký trước mã hóa” = securement action/protection order.
- “Timestamp trước Signature trong expected list” = validation action order.
- “GetOrderRequest/OrderId xuất hiện theo sequence” = business XSD order.

Một hệ thống có thể đúng ba thứ tự nhưng sai thứ tư.

### 8.1. Ví dụ tên khác nhau nhưng không được tráo

~~~text
WSDL operation: GetOrder
Request payload QName: {urn:example:orders:v1}GetOrderRequest
WS-Addressing Action: urn:example:orders:action:GetOrder
WS-Security action: Signature
SOAP 1.1 SOAPAction: urn:example:orders:action:GetOrder
~~~

WS-Addressing `Action` và WSS4J action `Signature` **hoàn toàn khác nhau**. Một bên mô tả operation/message routing, bên kia mô tả bảo mật. Không lấy `setSecurementActions("GetOrder")` hoặc dùng `SoapActionCallback("Signature")`.

## 9. Spring-WS server: validate request, secure response

Một server thông thường:

~~~mermaid
flowchart TD
    A["HTTP SOAP request"] --> B["SOAP message factory"]
    B --> C["Wss4jSecurityInterceptor: validateRequest"]
    C --> D{"Inbound WS-Security hợp lệ?"}
    D -->|"Không"| X["SOAP security Fault / reject"]
    D -->|"Có"| E["XSD validation + endpoint dispatch"]
    E --> F["Business @Endpoint"]
    F --> G["SOAP response"]
    G --> H["Wss4jSecurityInterceptor: secureResponse"]
    H --> I["HTTP SOAP response"]
~~~

Luồng trên mô tả trách nhiệm logic. Thứ tự dispatch/XSD/security cụ thể phụ thuộc framework configuration và interceptor chain; cần bảo đảm không xử lý business side effects trước khi security validation thành công.

### 9.1. Cấu hình server theo policy bất đối xứng

Ví dụ server **yêu cầu inbound request có Timestamp và Signature** nhưng outbound response chỉ cần Timestamp và Signature theo security contract:

~~~java
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

Wss4jSecurityInterceptor serverSecurity =
    new Wss4jSecurityInterceptor();

serverSecurity.setValidationActions(
    "Timestamp Signature"
);

serverSecurity.setSecurementActions(
    "Timestamp Signature"
);

// Còn PHẢI cấu hình:
// - validationSignatureCrypto: trust công khai của client,
// - securementSignatureCrypto: private signing key của server,
// - key alias/password callback,
// - signature parts/algorithms,
// - timestamp TTL/clock skew,
// - WS-Security policy và SOAP endpoints.
~~~

Snippet chỉ thể hiện logic action property, **không đủ để ký số thật sự**. Nếu inbound request có UsernameToken bổ sung, server có thể cần:

~~~java
serverSecurity.setValidationActions(
    "UsernameToken Timestamp Signature"
);
~~~

và callback handler xác minh UsernameToken phù hợp.

### 9.2. Đăng ký server interceptor tại đúng nơi

Trong ứng dụng Spring-WS dùng `WsConfigurerAdapter` hoặc `WsConfigurer` theo phiên bản hỗ trợ, ví dụ:

~~~java
import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;

@Configuration
@EnableWs
public class SoapEndpointInterceptorsConfig
        implements WsConfigurer {

    private final Wss4jSecurityInterceptor security;

    public SoapEndpointInterceptorsConfig(
            Wss4jSecurityInterceptor security) {
        this.security = security;
    }

    @Override
    public void addInterceptors(
            List<EndpointInterceptor> interceptors) {
        interceptors.add(security);
    }
}
~~~

Cấu hình này minh họa **cách đăng ký**, không thay các beans XSD/WSDL, `MessageDispatcherServlet`, crypto hoặc SOAP Fault policy. Nếu dự án dùng Spring XML, đăng ký interceptor trong cấu hình Spring-WS server tương ứng.

## 10. Spring-WS client: secure request, validate response

Một `WebServiceTemplate` có thể sử dụng cùng loại `Wss4jSecurityInterceptor` như một client interceptor.

~~~java
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.client.support.interceptor.ClientInterceptor;

Wss4jSecurityInterceptor clientSecurity =
    new Wss4jSecurityInterceptor();

clientSecurity.setSecurementActions(
    "Timestamp Signature"
);

clientSecurity.setValidationActions(
    "Timestamp Signature"
);

WebServiceTemplate template = new WebServiceTemplate();

template.setInterceptors(new ClientInterceptor[] {
    clientSecurity
});

// Còn cần JAXB marshaller/unmarshaller,
// SOAP factory, HTTP sender, TLS và crypto configuration.
~~~

Ở **outbound request**, interceptor tạo Timestamp/Signature. Khi **inbound response** về, nó kiểm tra Timestamp/Signature theo policy.

### 10.1. Tránh dùng nhầm keys ở hai chiều

- Khi client **ký request**: dùng private signing key của client.
- Khi client **xác minh response**: dùng public certificate/trust material của server.
- Khi server **xác minh request**: dùng public certificate/trust material của client.
- Khi server **ký response**: dùng private signing key của server.

Không cấu hình một keystore chứa private key của đối tác vào phía client chỉ để “validation hoạt động”; trong thiết kế đúng, mỗi bên chỉ giữ private key của chính mình.

### 10.2. Nếu client chỉ gửi request một chiều

Một operation không có business response vẫn cần quyết định liệu HTTP acknowledgment/transport và SOAP Fault có phải chịu WS-Security validation hay không. Không mặc định `validationActions` sẽ chạy nếu không có SOAP response message, và không coi HTTP 202 là một SOAP success response đã xác thực.

### 10.3. SOAP Fault có thể theo đường xử lý khác

Một server có thể trả SOAP Fault khi inbound signature sai. Client phải xử lý fault/message-level errors theo cơ chế Spring-WS, nhưng không được giả định mọi security failure đều có một response SOAP Fault đã được **ký bằng cùng bộ actions như normal response**. Hành vi phụ thuộc policy, thời điểm lỗi và khả năng tạo Fault. Thiết kế exception handling cần phân biệt SOAP Fault, WS-Security validation exception và HTTP/TLS/transport errors.

## 11. UsernameToken và authentication

`UsernameToken` mang thông tin xác thực trong `wsse:Security`. Token có thể sử dụng các dạng password được profile hỗ trợ, kèm nonce và thời điểm tạo.

~~~xml
<wsse:UsernameToken
    xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
    xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
    wsu:Id="UT-example">
    <wsse:Username>partner-client</wsse:Username>
    <!-- Password/Nonce/Created được thêm theo profile thực tế. -->
</wsse:UsernameToken>
~~~

XML trên là minh họa về element, **không phải credential hợp lệ**.

### 11.1. Action gửi và nhận

Bên gửi:

~~~java
security.setSecurementActions("UsernameToken");
security.setSecurementUsername("partner-client");

// Cần securementPassword hoặc CallbackHandler,
// PasswordType và nonce/created theo WSS4J version.
~~~

Bên nhận:

~~~java
security.setValidationActions("UsernameToken");

// Cần validationCallbackHandler/validator liên kết
// với nguồn credential tin cậy và chính sách replay.
~~~

Không coi việc có thẻ `UsernameToken` là đã xác thực: phải xác minh credential, thời điểm, nonce, nguồn identity và quyền thực hiện SOAP operation.

### 11.2. PasswordDigest không thay TLS

`PasswordDigest` không đồng nghĩa mã hóa SOAP Body, và không loại bỏ sự cần thiết của HTTPS/TLS. Nonce và Created chỉ hữu ích chống phát lại khi phía nhận có kiểm tra cửa sổ thời gian và replay cache phù hợp. Một token còn hạn không có nghĩa nó chưa từng được sử dụng.

### 11.3. UsernameTokenSignature không phải tổ hợp phổ quát

`UsernameTokenSignature` là action/profile riêng trong những WSS4J versions hỗ trợ. Nó không đương nhiên tương đương `UsernameToken Signature` với chữ ký X.509. Khi dùng profile này, cần xác nhận key derivation, kiểu signature, sự hỗ trợ của Spring-WS adapter và bên đối tác.

## 12. Timestamp, TTL và replay

`Timestamp` thường chứa các phần tử `wsu:Created` và `wsu:Expires`:

~~~xml
<wsu:Timestamp
    xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
    wsu:Id="TS-example">
    <wsu:Created>2026-11-27T02:30:00Z</wsu:Created>
    <wsu:Expires>2026-11-27T02:35:00Z</wsu:Expires>
</wsu:Timestamp>
~~~

Timestamp dùng ngày giờ minh họa, không phải fixture luôn còn hiệu lực. Tạo timestamp động bằng test clock trong kiểm thử.

| Cấu hình | Vai trò |
|---|---|
| `securementActions="Timestamp"` | Bên gửi tạo Timestamp |
| `validationActions="Timestamp"` | Bên nhận yêu cầu và kiểm tra Timestamp |
| Timestamp TTL/strictness | Khoảng thời gian được chấp nhận |
| Clock skew | Cho phép độ lệch đồng hồ có giới hạn |
| Signature covering Timestamp | Ngăn sửa đổi Timestamp đã được ký |
| Replay cache | Phát hiện phát lại trong cửa sổ thời gian |

Một số Spring-WS/WSS4J releases có `timestampStrict`, `timeToLive`, `validationTimeToLive` và `timestampPrecisionInMilliseconds`. Không sao chép tên property hoặc default value qua major versions mà chưa kiểm tra API của artifact hiện tại.

### 12.1. Timestamp không phải HTTP timeout

Thời hạn WS-Security Timestamp là thuộc tính của **message** so với đồng hồ thời gian thực. HTTP connect/read timeout hay overall deadline đo thời gian chờ của **caller**. Một SOAP request có Timestamp hợp lệ vẫn có thể bị timeout khi gửi/nhận.

### 12.2. Timestamp không tự chống mọi replay

Một request đã ký, Timestamp chưa hết hạn vẫn có thể bị phát lại trong cửa sổ cho phép nếu không có kiểm soát nonce/message ID/replay. Với các operation có side effect như tạo đơn hoặc thanh toán, phải có thêm **business idempotency key** và cơ chế reconciliation.

### 12.3. Có Timestamp + Signature vẫn cần cấu hình signature parts

Nếu chữ ký chỉ bao phủ SOAP Body, Timestamp không tự nhiên được ký vì nằm trong cùng `wsse:Security`. Kiểm tra `securementSignatureParts` và các `ds:Reference` thực tế. Khi Timestamp ảnh hưởng quyết định an ninh, policy thường yêu cầu bảo vệ tính toàn vẹn của nó.

## 13. Signature: ký, xác minh và signed parts

XML Digital Signature cho phép bên gửi ký những XML nodes đã chọn bằng **private signing key**. Bên nhận xác minh với **public certificate** và áp dụng certificate trust/authorization.

~~~mermaid
sequenceDiagram
    participant C as SOAP client
    participant S as SOAP server
    C->>C: Marshal Body, tạo Timestamp
    C->>C: Ký các parts theo policy
    C->>S: SOAP request + ds:Signature
    S->>S: Kiểm tra signed references
    S->>S: Verify chữ ký + cert trust
    S->>S: Kiểm tra Timestamp và quyền
    S-->>C: Response bảo vệ theo policy chiều về
~~~

### 13.1. Cấu hình ký outbound

~~~java
security.setSecurementActions(
    "Timestamp Signature"
);

security.setSecurementUsername(
    "client-signing-key-alias"
);

// Cần Crypto chứa private key của client,
// mật khẩu key từ secret store và key identifier.
// security.setSecurementSignatureCrypto(ownSigningCrypto);
~~~

`setSecurementActions("Signature")` một mình không đủ để ký thật nếu thiếu Crypto/private key/alias/callback password.

### 13.2. Cấu hình xác minh inbound

~~~java
security.setValidationActions(
    "Timestamp Signature"
);

// Cần Crypto chứa public certificates/trust
// của partner và chính sách signer identity.
// security.setValidationSignatureCrypto(partnerTrustCrypto);
~~~

Một chữ ký toán học hợp lệ với certificate không được trust vẫn phải bị từ chối. Ngược lại, một certificate nằm trong truststore không tự cấp quyền gọi mọi operation. Authorization phải được kiểm tra theo identity đã xác minh.

### 13.3. Signature parts kiểm soát vùng được bảo vệ

Các phần quan trọng có thể gồm SOAP Body, `wsu:Timestamp`, `wsa:To`/`wsa:Action`/`wsa:ReplyTo`, cùng business Headers ảnh hưởng đến logic.

Một giá trị minh họa cho SOAP 1.1 Body:

~~~java
security.setSecurementSignatureParts(
    "{}{http://schemas.xmlsoap.org/soap/envelope/}Body"
);
~~~

Dạng phần tử ký trong Spring-WS/WSS4J thường dùng cú pháp `{}{namespace}localName` và ngăn cách các targets bằng `;`. Ví dụ thêm Timestamp, CorrelationId:

~~~text
{}{http://schemas.xmlsoap.org/soap/envelope/}Body;
{}{http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd}Timestamp;
{}{urn:example:common:v1}CorrelationId
~~~

Khi đưa vào property thực tế, nối thành **một chuỗi** và kiểm tra namespace, prefix-independent QName, signature references và partner profile. SOAP 1.2 dùng Body namespace khác SOAP 1.1.

### 13.4. XML Signature Wrapping không được giải quyết chỉ bằng action name

Nếu receiver xác minh một node đã ký nhưng business code lại xử lý node khác cùng local name, có thể có nguy cơ XML Signature Wrapping. Vì vậy:

- Xác minh những XML nodes thực sự được ký.
- Kiểm tra unique IDs, references và các parts bắt buộc.
- Enforce SOAP Envelope/Body/Header structure và XSD QName.
- Dùng WSS4J provider cập nhật và không bỏ validation trong domain pipeline.

`validationActions="Signature"` không đủ nếu code phía sau tin dữ liệu khác với phần đã được xác minh.

## 14. Encrypt: mã hóa outbound và giải mã inbound

XML Encryption dùng để che nội dung của các XML parts được chọn. Nó không phải transport TLS, dù cả hai bảo vệ tính bí mật ở các phạm vi khác nhau.

### 14.1. Phân biệt key direction

| Tác vụ | Bên gửi dùng | Bên nhận dùng |
|---|---|---|
| Ký | Private signing key của sender | Public signing cert của sender + trust |
| Mã hóa | Public encryption cert của recipient | Private decryption key của recipient |

Không chia sẻ private keys giữa các bên chỉ để giải quyết lỗi security action. Một ứng dụng nên giữ private keys của chính mình, cùng trust material đã được phê duyệt cho đối tác.

### 14.2. Securement Encrypt

~~~java
security.setSecurementActions("Encrypt");

// Thường cần public recipient certificate:
// security.setSecurementEncryptionUser("partner-key-alias");
// security.setSecurementEncryptionCrypto(recipientPublicCrypto);
~~~

### 14.3. Validation Encrypt

~~~java
security.setValidationActions("Encrypt");

// Thường cần private decryption key của phía nhận:
// security.setValidationDecryptionCrypto(ownPrivateCrypto);
// và callback mở khóa nếu cần.
~~~

Ở chiều **inbound**, action `Encrypt` biểu thị kiểm tra/giải mã một message đã được mã hóa, **không có nghĩa bên nhận sẽ mã hóa thêm**.

### 14.4. Content và Element encryption

`securementEncryptionParts` cho phép chọn chế độ XML Encryption, ví dụ:

~~~text
{Content}{urn:example:orders:v1}GetOrderResponse
{Element}{urn:example:orders:v1}SensitiveDetails
~~~

- `Content` mã hóa nội dung trong element.
- `Element` mã hóa toàn element.
- Cú pháp, QName và default parts phải đối chiếu WSS4J/Spring-WS version.

Không coi mã hóa SOAP Body là mã hóa toàn bộ SOAP Headers, security tokens hoặc attachments. Các phần cần bảo vệ phải được nêu rõ trong policy.

### 14.5. Cẩn trọng khi đổi tên Encrypt/Encryption

Apache WSS4J 2.3 trở lên có action `Encryption`, thay cho tên `Encrypt` của các releases trước đó ở một số configuration constants. Tài liệu Spring-WS 4.1.x của interceptor vẫn dùng `Encrypt`. Không tự động đổi mọi cấu hình từ `Encrypt` sang `Encryption`: xác minh chính xác Spring-WS adapter và WSS4J action parser đang chạy bằng test.

## 15. Sign-before-encrypt và encrypt-before-sign

Với message vừa có `Signature` vừa có `Encrypt`, thứ tự bảo vệ là một lựa chọn bảo mật.

### 15.1. Ký rồi mã hóa

~~~text
Plaintext SOAP parts
    -> tạo XML Signature trên các parts lựa chọn
    -> mã hóa những XML parts theo policy
    -> gửi SOAP message
~~~

Tùy profile, chữ ký hoặc các targets có thể nằm trong phần mã hóa. Receiver có thể cần giải mã để tìm nội dung/References liên quan, rồi mới hoàn tất signature verification.

### 15.2. Mã hóa rồi ký

~~~text
Plaintext SOAP parts
    -> mã hóa các XML parts
    -> ký ciphertext hoặc elements liên quan
    -> gửi SOAP message
~~~

Chữ ký bảo vệ representation sau mã hóa tùy signature targets. Không suy rằng hai profiles bảo vệ cùng dữ liệu, hoặc mọi receiver đều hỗ trợ cả hai.

### 15.3. Những câu hỏi phải trả lời từ contract/policy

- Bên đối tác yêu cầu `SignBeforeEncrypt` hay `EncryptBeforeSign`?
- Body/Headers nào cần ký? Header nào cần mã hóa?
- Ký plaintext hay encrypted representation?
- Dùng key identifiers, token references và algorithms nào?
- WS-I BSP/WS-Policy định nghĩa layout ra sao?
- Kết quả WSS4J inbound action order có khớp `validationActions` không?

**Không có thứ tự chung đúng cho mọi đối tác.** Một ví dụ `securementActions="Timestamp Signature Encrypt"` không được coi là tiêu chuẩn cho mọi SOAP service.

### 15.4. Không đảo validationActions máy móc

Sai lầm:

~~~text
Outbound securement: "Timestamp Signature Encrypt"
Inbound validation:  "Encrypt Signature Timestamp" // Đảo chuỗi
~~~

`validationActions` là danh sách **expected inbound security actions**, và Spring-WS kiểm tra tính phù hợp của action order theo WSS4J results. Crypto processing có các phụ thuộc riêng. Không thể suy inbound property bằng cách `reverse()` chuỗi outbound một cách phổ quát.

Cách đúng: dùng sender thật tạo message, receiver thật kiểm chứng theo một policy đã thống nhất, xem WSS4J diagnostics **đã loại bỏ dữ liệu nhạy cảm**, rồi dùng positive/negative tests xác nhận cả tổ hợp order, signed parts và algorithms.

## 16. Phân biệt action order với interceptor chain order

Một HTTP SOAP request có thể đi qua nhiều interceptors:

~~~text
WebServiceTemplate request:
  Observation
    -> BusinessHeader / Correlation
      -> Wss4jSecurityInterceptor
        -> HTTPS sender

SOAP response:
  HTTPS sender
    -> Wss4jSecurityInterceptor
      -> BusinessHeader / Correlation
        -> Observation
~~~

Sơ đồ là thứ tự logic phổ biến; đường Fault/exception và `afterCompletion` có thể đi theo nhánh khác khi callback chặn xử lý hoặc ném exception. Phải kiểm chứng trên Spring-WS version thực tế.

**Hai cấu hình độc lập:**

1. Đăng ký `Wss4jSecurityInterceptor` sau interceptor tạo SOAP Header giúp header hiện diện trước khi ký.
2. `securementSignatureParts` phải **chỉ rõ QName header đó** mới bảo đảm nó được ký theo yêu cầu.

Đăng ký đúng thứ tự **không** đồng nghĩa mọi headers trước đó tự động trở thành signed parts.

### 16.1. Một business Header cần integrity

Ví dụ:

~~~xml
<com:CorrelationId
    xmlns:com="urn:example:common:v1">
    REQ-2048
</com:CorrelationId>
~~~

Nếu đối tác yêu cầu Header này được ký, hãy xác nhận message tạo ra có `ds:Reference` bao phủ đúng Header QName và có `wsu:Id` theo cơ chế ký cần thiết. Tránh dựa vào việc header xuất hiện trong cùng SOAP Envelope với `ds:Signature`.

### 16.2. WS-Addressing Callback/Action cũng phải chạy đúng thời điểm

`ActionCallback` có thể thêm `wsa:Action`, `wsa:To`, `wsa:ReplyTo` trên outbound request. Nếu WS-Security policy bắt buộc ký các addressing headers, chúng phải tồn tại khi WSS4J thực hiện Signature.

Đừng nhầm `wsa:Action` (operation routing URI) với WSS4J `Signature` action. Khi thay đổi thứ tự callback/interceptor hoặc framework, chạy interoperability test để đảm bảo đúng parts được bảo vệ.

### 16.3. Tránh log hoặc mutate SOAP XML sau khi ký

Một interceptor quan sát có thể làm hỏng signature nếu nó ghi lại Body/Headers đã được ký, đổi IDs, namespace declarations hoặc canonicalization semantics. Ưu tiên metrics/log đã giảm dữ liệu: operation, partner alias, action profile, security result, duration và fault category.

Không log nguyên UsernameToken, BinarySecurityToken, EncryptedKey, plaintext trước mã hóa, private keys hay Fault Detail nhạy cảm.

## 17. Quản lý Crypto, key alias và trust material

Các action `Signature` và `Encrypt` cần keystore/truststore và callback xử lý password/key material.

| Nhiệm vụ | Vật liệu cần thiết |
|---|---|
| Ký outbound | Private signing key của bên gửi và key alias |
| Xác minh inbound | Public signing certificate/trust của bên gửi |
| Mã hóa outbound | Public encryption certificate của bên nhận |
| Giải mã inbound | Private decryption key của bên nhận |
| UsernameToken outbound | Identity/credential từ secret provider |
| UsernameToken inbound | Credential validator/identity store/replay policy |

### 17.1. Spring-WS Crypto properties ở mức ý tưởng

~~~java
// PSEUDOCODE: đối tượng Crypto/CallbackHandler được
// tạo và quản lý theo Spring-WS/WSS4J version.
//
// security.setSecurementSignatureCrypto(ownSigningCrypto);
// security.setValidationSignatureCrypto(trustedPartnerCrypto);
//
// security.setSecurementEncryptionCrypto(partnerPublicCrypto);
// security.setValidationDecryptionCrypto(ownPrivateDecryptCrypto);
//
// security.setSecurementCallbackHandler(privateKeyPasswordHandler);
// security.setValidationCallbackHandler(tokenOrKeyPasswordHandler);
~~~

Các property names trên tương ứng những chức năng được Spring-WS/WSS4J tích hợp trong các phiên bản nhất định; kiểm tra exact API và package của dependency trước khi áp dụng.

### 17.2. Khóa ký không nhất thiết là khóa TLS

Một đối tác có thể dùng certificate TLS/mTLS khác với certificate ký SOAP message. TLS handshake xác minh peer trên kênh HTTP, còn `validationSignatureCrypto` xác minh message-level Signature. Không trỏ tất cả cấu hình vào cùng một keystore chỉ vì tên “certificate” giống nhau.

### 17.3. Certificate có trust không đồng nghĩa có quyền

Ngoài xác minh đường dẫn chứng chỉ/expiry và thuật toán, hệ thống cần map signer identity sang partner account, tenant và các SOAP operations được phép. Một Signature hợp lệ của đối tác A không được cấp quyền sửa dữ liệu của đối tác B.

### 17.4. Rotation và tuổi thọ key

Thiết kế cần tính đến:

- Hai bộ certificate có thể cùng tồn tại trong giai đoạn chuyển đổi.
- Certificate expiry/rotation schedule được giám sát.
- Tránh đổi key alias giữa các concurrent SOAP calls.
- Trust thay đổi phải được kiểm chứng trên cold/warm connections và message-level signature.
- Keystore/password không xuất hiện trong config repository hoặc lỗi SOAP Fault.

## 18. Ví dụ XML bean server hoàn chỉnh ở mức cấu trúc

Một server nhận request có `Timestamp Signature`, rồi trả response cũng có `Timestamp Signature`:

~~~xml
<!-- Fragment, phải khai báo Crypto và callback beans thực tế. -->
<bean id="ordersWsSecurity"
      class="org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor">

    <property name="validationActions"
              value="Timestamp Signature"/>

    <property name="securementActions"
              value="Timestamp Signature"/>

    <property name="validationSignatureCrypto"
              ref="trustedClientSignerCrypto"/>

    <property name="securementSignatureCrypto"
              ref="serverOwnSigningCrypto"/>

    <property name="securementUsername"
              value="server-signing-key-alias"/>

    <property name="securementCallbackHandler"
              ref="serverSigningPasswordHandler"/>
</bean>
~~~

**Đây không phải bean configuration có thể chạy độc lập:** phải tạo Crypto từ trusted keystore/truststore, password callback, SOAP message factory, Spring-WS endpoint interceptor registry, và cấu hình thuật toán/parts theo policy. Không đặt private key password dạng literal trong file XML.

### 18.1. Cấu hình hai chiều bất đối xứng

Ví dụ contract:

~~~text
Incoming request:
  UsernameToken Timestamp Signature

Outgoing response:
  Timestamp Encrypt
~~~

Server cần các thành phần riêng:

- Inbound validation callback xác thực UsernameToken.
- Inbound signature trust của client.
- Outbound recipient public cert để mã hóa response.
- Clock skew/TTL và replay controls.
- Quy tắc Fault response nếu inbound authentication hoặc signature không hợp lệ.

Không dùng chung một tập action bất kể request/response chỉ để giảm cấu hình.

### 18.2. Nhiều partner nên có profile riêng

Một application vừa host SOAP endpoint vừa call đối tác có thể cần:

~~~text
ordersServerSecurity
paymentPartnerClientSecurity
inventoryPartnerClientSecurity
~~~

Mỗi profile có version, required actions, keystore/truststore, signed/encrypted parts và fault policy khác nhau. Không sửa `setSecurementActions(...)` trên một singleton interceptor trong lúc nhiều threads dùng; điều đó là thay mutable global configuration.

## 19. WS-I BSP, key transport và thuật toán

WS-Security interoperability còn phụ thuộc các quy tắc profile như WS-I Basic Security Profile (BSP). Một Spring-WS/WSS4J version mới có thể mặc định từ chối cấu trúc message cũ trước đây được chấp nhận.

### 19.1. BSP enforcement

Trong Spring-WS 4.1.x, `setBspCompliant(boolean)` được tài liệu mô tả để kiểm soát WS-I BSP validation; mặc định là `true`. Chỉ cân nhắc tắt khi đối tác có một lý do tương thích đã được phê duyệt, threat model và exception policy rõ ràng.

Không tắt BSP hoặc signature validation chỉ để “giải quyết” một sai lệch thứ tự action.

### 19.2. RSA PKCS#1 v1.5 và RSA-OAEP

Với inbound XML Encryption, Spring-WS 4.1.x có `setAllowRSA15KeyTransportAlgorithm(boolean)`; tài liệu mô tả mặc định `false` để tránh chấp nhận RSA PKCS#1 v1.5 key transport trừ khi bắt buộc tương thích. Outbound nên ưu tiên RSA-OAEP trong profile phù hợp với đối tác và security baseline.

Không tuyên bố một thuật toán luôn an toàn trong mọi bối cảnh: cần xét key size, digest, canonicalization, XML Encryption version, threat model và khả năng hỗ trợ của partner.

### 19.3. Kiểm tra signature và encryption algorithms độc lập

`validationActions="Signature Encrypt"` không khẳng định SHA-256, RSA-OAEP hoặc AES-GCM tự được chọn. Các thuật toán thực tế được quyết định bởi policy, XML Security Header và cấu hình library. Negative tests cần kiểm tra algorithm downgrade, unexpected key identifiers và unsupported cipher suites theo baseline của tổ chức.

## 20. SOAP 1.1/1.2, Fault và phiên bản contract

Chữ ký đối với SOAP Body phụ thuộc **namespace của SOAP Envelope**:

| SOAP version | Body QName namespace |
|---|---|
| SOAP 1.1 | `http://schemas.xmlsoap.org/soap/envelope/` |
| SOAP 1.2 | `http://www.w3.org/2003/05/soap-envelope` |

Nếu `securementSignatureParts` trỏ Body SOAP 1.1 nhưng message factory tạo SOAP 1.2, phần được ký có thể không khớp. Đừng coi lỗi này là lỗi certificate ngay.

### 20.1. SOAP Fault khác security validation failure

Một message có Fault hợp lệ theo SOAP protocol có thể đi qua `FaultMessageResolver` và `ClientInterceptor.handleFault`. Nhưng lỗi WS-Security có thể phát sinh **trước khi** business endpoint xử lý, khi signature bị từ chối hoặc không giải mã được.

Trong Spring-WS, các nhóm exceptions `WsSecurityValidationException` và `WsSecuritySecurementException` diễn đạt lỗi validation và securement. Framework có đường xử lý security exceptions riêng; không giả định mọi exception sẽ được map thành cùng một business Fault, hoặc mọi Fault đều mang chữ ký response thông thường.

### 20.2. Đừng tiết lộ lý do kiểm chứng nội bộ cho client

Nếu certificate private key/callback/algorithm bị lỗi, không trả raw stack trace, keystore file path, alias hoặc nội dung UsernameToken cho remote caller. Có thể trả SOAP security Fault/HTTP error theo binding với fault code đã chuẩn hóa, correlation ID và thông điệp an toàn.

### 20.3. WS-Security không thay XSD/authorization

- **XSD validation**: kiểm tra payload QName, types, facets và occurrence.
- **WS-Security**: xác minh token/chữ ký/mã hóa theo policy.
- **TLS**: bảo vệ kênh truyền.
- **Authorization**: quyết định danh tính được thực hiện operation nào.
- **Anti-XXE**: giới hạn XML parsers/external entity resolution.

Một message có Signature hợp lệ vẫn có thể sai `xs:pattern` hoặc chứa business value không được phép. Một message đúng XSD không được miễn WS-Security.

## 21. Đọc Security Header để tìm lỗi thứ tự

Khi WSS4J từ chối message, thực hiện phân tích có thứ tự:

1. Xác nhận SOAP version và content type.
2. Xác nhận server/client đã đăng ký interceptor vào **đúng chain**.
3. Kiểm tra inbound `wsse:Security` thuộc actor/role được xử lý.
4. Kiểm tra action tokens trong `validationActions` và WSS4J adapter version.
5. So action results nhận được với expected order; phân biệt order mismatch và missing action.
6. Kiểm tra timestamp window, nonce và replay.
7. Xác minh signing public certificate trust và allowed identity.
8. Kiểm tra signed references có bao phủ đúng XML elements.
9. Nếu có encryption, kiểm tra recipient key, key transport và encryption parts.
10. Kiểm tra WSDL/WS-Policy và hướng request/response.
11. Nếu cần điều tra, dùng SOAP sample trong **môi trường test có bảo mật**, đã bỏ secrets.
12. Tạo negative regression test mô phỏng đúng sự cố trước khi sửa cấu hình.

Không bắt đầu bằng cách tắt validation hoặc đặt `NoSecurity`. Việc đó chỉ làm mất tín hiệu lỗi, có thể phá contract bảo mật và gây rủi ro trên production.

### 21.1. Phân biệt lỗi order với lỗi certificate

| Triệu chứng | Khả năng | Kiểm tra |
|---|---|---|
| Mismatch expected action sequence | Order khác hoặc action thiếu/thừa | `validationActions`, outbound actions, processor result |
| Signature verification failure | Body/Header thay đổi, canonicalization, khóa sai | `ds:Reference`, cert, signature algorithm |
| Certificate trust failure | Cert lạ/hết hạn/chain không trust | Truststore, partner rotation |
| Decryption failure | Không có private decrypt key đúng | Alias, Crypto, key transport |
| Timestamp validation failure | Hết hạn/clock skew/future time | UTC, TTL, skew, test clock |
| UsernameToken failure | Password/nonce/callback sai | Credential store, replay policy |
| Missing wsse:Security | Không có securement hoặc Header role sai | Sender/interceptor registration |
| SOAPAction mismatch | SOAP binding khác WS-Security | WSDL, HTTP/SOAP headers |
| XML Parser failure | Malformed XML/XXE blocking | XML factory, XML security policy |

## 22. Một cấu hình tối thiểu an toàn cho bài thực hành

Với mục tiêu **học action direction và order**, hãy dùng môi trường test cô lập, tạo certificate/keystore thử nghiệm không chứa secrets thật và bắt đầu bằng một policy dễ kiểm:

~~~text
Request:
  Timestamp + Signature
  Body và Timestamp thuộc signed parts

Response:
  Timestamp + Signature
  Body và Timestamp thuộc signed parts

Transport:
  HTTPS test endpoint
  Certificate/trust policy test riêng
~~~

Phát triển theo lộ trình:

1. Chạy SOAP Body không WS-Security trong local test riêng để xác nhận XSD/WSDL/QName.
2. Bật `Timestamp` và test request/response clock.
3. Bật `Signature` với test key pairs.
4. Assert certificate trust và signed references.
5. Cố ý bỏ Signature để xác nhận receiver reject.
6. Cố ý sửa nội dung đã ký để xác nhận receiver reject.
7. Cố ý đổi action order để xác nhận enforcement.
8. Bổ sung `Encrypt` chỉ khi cả hai bên đã có decryption/encryption keys và policy.
9. Lặp lại tests với SOAP Fault, expired timestamp và response validation.
10. Chạy interoperability với SOAP stack khác, không chỉ hai phía cùng dùng Spring-WS.

**Không dùng test keystore/password ở staging/production.** Sự tiện lợi của một sample cùng key pair hai phía có thể che giấu việc đang dùng sai key direction.

## 23. Kiểm thử bảo mật bằng MockWebServiceClient và MockWebServiceServer

Spring-WS cung cấp hai công cụ testing phục vụ **hai ranh giới khác nhau**:

| Công cụ | Mục tiêu |
|---|---|
| `MockWebServiceClient` | SOAP **server** endpoint và endpoint interceptor |
| `MockWebServiceServer` | SOAP **client** `WebServiceTemplate` và client interceptor |

`MockWebServiceClient` có thể giúp kiểm tra server từ chối request sai security và không chạy domain service. `MockWebServiceServer` giúp kiểm tra outbound request từ SOAP client và phản ứng với mock SOAP response/Fault.

**Cần hiểu giới hạn:** Kiểm tra một XML fixture chứa `<wsse:Security>` chưa chứng minh chữ ký mật mã hợp lệ. Test WS-Security cần message được ký bằng key fixture thực, receiver thật xác minh chữ ký/certificate policy, rồi mới assert.

### 23.1. Test server inbound validation

Bộ test nên có:

~~~text
Input:
  SOAP Envelope
  + Timestamp
  + Signature thật bằng test private key
  + Body và Timestamp nằm trong signed references

Expected:
  WSS4J validation PASS
  Endpoint nhận đúng GetOrderRequest QName
  Business method chỉ chạy khi security thành công
~~~

Các ca âm:

- Thiếu Signature.
- Thiếu Timestamp khi expected.
- Timestamp expired.
- Signature trên Body khác với Body được xử lý.
- Chữ ký hợp lệ nhưng certificate không nằm trong trust policy.
- Token có action order khác expectation.
- Wrong SOAP Body namespace/signed part.
- Header role/actor khác yêu cầu.

Không chỉ assert HTTP status 500: phải xác định nguyên nhân và đảm bảo business operation chưa chạy khi security validation thất bại.

### 23.2. Test client outbound securement

Một test client có thể:

1. Tạo `WebServiceTemplate` với JAXB, message factory và WSS4J ClientInterceptor.
2. Gửi `GetOrderRequest` qua `MockWebServiceServer`.
3. Dùng matcher kiểm tra SOAP Body QName, sự hiện diện của Timestamp và Signature.
4. **Quan trọng:** Dùng WSS4J verifier và trusted test certificate để xác minh chữ ký và signed references, không chỉ tìm XML tag.
5. Trả mock SOAP response đã ký bằng server test private key.
6. Assert client validation thành công và unmarshal `GetOrderResponse` đúng.
7. Trả response bị sửa sau ký; assert client từ chối.
8. Trả response có certificate lạ; assert client từ chối.

### 23.3. Test order bằng hai cấu hình phát sinh message khác nhau

Mô hình:

~~~text
Test sender A:
    securementActions = "Timestamp Signature"

Test receiver:
    validationActions = "Timestamp Signature"

Expected:
    PASS nếu khóa/parts/clock/policy hợp lệ
~~~

Đổi thứ tự ở sender hoặc receiver trong một test riêng có thể tạo mismatch. Kỳ vọng thực tế phụ thuộc cách WSS4J version ghi nhận action results và các rules cụ thể. Test phải kiểm tra exception/result đúng, không suy đoán rằng XML node order tự quyết định tất cả.

### 23.4. Test encrypt/sign kết hợp

Với partner yêu cầu vừa Signature vừa Encryption, cần hai nhóm tests:

- **Positive**: profile order, targets, algorithms và key identifiers đúng → receiver giải mã, kiểm chữ ký và xử lý business.
- **Negative**: đảo protection order, đổi encrypted parts, sửa signed references, dùng wrong recipient cert, thay thuật toán không được phép → receiver từ chối theo policy.

Khi test thất bại, phân loại rõ `action order`, `signature verification`, `decryption` và `policy mismatch`; không gộp mọi lỗi thành “cannot unmarshal SOAP response”.

## 24. Ma trận kiểm thử theo hướng request/response

| Ca | Client request | Server validation | Server response | Client validation | Kỳ vọng |
|---|---|---|---|---|---|
| A1 | Timestamp + Signature đúng | Cùng profile | Timestamp + Signature đúng | Cùng profile | Thành công |
| A2 | Chỉ Timestamp | Yêu cầu Timestamp + Signature | Không bắt buộc phát response business | — | Server từ chối |
| A3 | Timestamp + Signature sai cert | Có Signature nhưng trust fail | Security fault/error | Policy riêng | Server từ chối |
| A4 | Timestamp + Signature đúng | PASS | Response thiếu Signature | Yêu cầu Signature | Client từ chối |
| A5 | Timestamp + Signature đúng | PASS | Signature đúng nhưng Body bị sửa | Yêu cầu Signature | Client từ chối |
| A6 | Timestamp hết hạn | Validate TTL | — | — | Server từ chối |
| A7 | UsernameToken password sai | Validate token | — | — | Server từ chối |
| A8 | Action result order khác | Expect strict order | — | — | Server từ chối khi policy thực thi |
| A9 | Encrypt bằng sai recipient cert | Không có đúng decrypt key | — | — | Decryption failure |
| A10 | Signed Body nhưng thiếu signed Timestamp khi required | Parts policy chặt | — | — | Không chấp nhận |
| A11 | SOAP 1.2 message nhưng Body signature parts chọn SOAP 1.1 | Ký sai/missing target | — | — | Security/contract mismatch |
| A12 | Message có wsse:Security nhưng không có các actions bắt buộc | Expected list khác | — | — | Không đạt action validation |
| A13 | Request SOAP Fault path | Security có thể fail trước endpoint | Fault không nhất thiết protected như normal response | Chế độ riêng | Không báo success giả |
| A14 | Đúng WS-Security nhưng payload sai XSD | PASS | Validation fault | Theo policy | Domain không nhận input sai |

**Mọi dòng chỉ là ý tưởng kiểm thử**, không phải khẳng định WSS4J phát cùng exception name/code cho mọi release. Với các flows có Fault, phải xét security của chính Fault và thời điểm lỗi xảy ra.

## 25. Một ví dụ kiểm thử action direction bằng unit assertions

Ta có thể kiểm tra **cấu hình định hướng** ở cấp unit bằng một builder nhỏ thay vì đặt các chuỗi rải rác:

~~~java
public final class OrdersSecurityActions {

    public static final String REQUEST_OUTBOUND =
        "Timestamp Signature";

    public static final String REQUEST_INBOUND =
        "Timestamp Signature";

    public static final String RESPONSE_OUTBOUND =
        "Timestamp Signature";

    public static final String RESPONSE_INBOUND =
        "Timestamp Signature";

    private OrdersSecurityActions() {}
}
~~~

Trong một test policy riêng:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class SecurityActionContractTest {

    @Test
    void requestAndResponseProfilesAreExplicit() {
        assertEquals(
            OrdersSecurityActions.REQUEST_OUTBOUND,
            OrdersSecurityActions.REQUEST_INBOUND
        );

        assertEquals(
            OrdersSecurityActions.RESPONSE_OUTBOUND,
            OrdersSecurityActions.RESPONSE_INBOUND
        );
    }
}
~~~

Test này chỉ chứng minh **hai chuỗi cấu hình đã được đồng bộ như mong muốn**; nó không xác minh cryptography, action order thực tế hoặc SOAP Header. Do đó, **không được coi là security conformance test**. Muốn chứng minh an toàn, phải tạo message thật và verify bằng một implementation thực tế, tốt nhất có peer stack độc lập.

### 25.1. Không hard-code cùng profile cho mọi bên

Một số service có request profile `UsernameToken Timestamp Signature` nhưng response profile `Timestamp Encrypt`. Khi đó bốn hằng trong class trên phải khác nhau theo hợp đồng, và test phải diễn tả **mapping request-outbound ↔ request-inbound** cùng **response-outbound ↔ response-inbound**.

### 25.2. Đừng dùng mock validator “luôn pass”

Một fake verifier trả true cho mọi `ds:Signature` có thể giúp test business flow nhưng không được dùng để chứng minh SOAP security. Phải có ít nhất một test thực sự dùng WSS4J with known test keys và kiểm chứng negative cases.

## 26. Interoperability với đối tác khác Java

Một SOAP stack của .NET/WCF, ESB hoặc nền tảng khác có thể dùng cùng WSDL/XSD nhưng khác:

- Layout của `wsse:Security`.
- Key identifier: issuer serial/direct reference.
- Certificate chain và trust requirements.
- Signature algorithm, canonicalization, digest.
- EncryptedData Content/Element mode.
- Protection order ký trước mã hóa hoặc ngược lại.
- WS-Security Timestamp/Nonce policy.
- SOAP 1.1/1.2 và header actor/role.
- Signed parts của WS-Addressing.
- WS-I BSP enforcement.
- SOAP Fault representation và signature của response.

Không dùng việc **hai phía cùng dùng một phiên bản WSS4J và một bộ JAXB classes** làm bằng chứng duy nhất cho interoperability. Một peer độc lập hoặc bộ test fixtures được chuẩn hóa sẽ phát hiện các giả định chung sai.

### 26.1. Thay đổi bảo mật có thể là breaking change dù XSD không đổi

Các thay đổi như:

- Thêm `Signature` vào `validationActions`.
- Đổi action order.
- Đưa thêm Header vào signed parts.
- Thay `Encrypt` encryption target.
- Loại certificate của partner khỏi trust.
- Bật strict Timestamp.
- Thay SOAP binding/header role.

có thể khiến clients cũ bị từ chối, dù `GetOrderRequest` XML hợp XSD không đổi. Cần quản lý WS-Security policy/version song song với contract WSDL/XSD.

### 26.2. Chuyển version action token Encrypt/Encryption

Trong quá trình nâng cấp Spring-WS/WSS4J, hãy:

1. Xác nhận artifacts/dependency versions và action constants.
2. Ghi lại security profile được đối tác công bố.
3. Kiểm tra tên action parser nhận diện ở adapter.
4. Test outbound SOAP message trên wire.
5. Test inbound validation với fixtures của version cũ và mới.
6. Test khi cấu hình action không được nhận diện có **fail startup/validation** đúng policy.
7. Chỉ phát hành sau khi partner conformance test pass.

Không đổi tên action mù quáng trên production rồi chờ SOAP Fault để biết có lỗi hay không.

## 27. Lỗi thường gặp và hướng chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
|---|---|---|
| Không có `wsse:Security` outbound | Interceptor chưa đăng ký/`securementActions` rỗng | Client/server chain, template wiring |
| Inbound missing action | Request thiếu Signature/Timestamp | Expected `validationActions` |
| Inbound action order mismatch | Sequence khác theo WSS4J results | Partner securement, expected action order |
| Chữ ký sai sau khi thêm logging | Interceptor mutate Body/Headers | Thứ tự interceptor, signed references |
| Chữ ký đúng nhưng receiver từ chối | Trust/allowed signer identity không phù hợp | Certificates, Crypto, authorization |
| Timestamp expired | Clocks/TTL/strictness | Clock sync, Created/Expires |
| Replay được chấp nhận | Thiếu nonce/message ID cache | Replay protection và idempotency |
| Cannot decrypt | Wrong recipient cert/private decrypt key | EncryptionUser, decryption Crypto, key ID |
| Message pass nhưng Header không được ký | Default Signature chỉ cover Body | `securementSignatureParts` |
| SOAP 1.2 fail còn SOAP 1.1 pass | Body namespace/actor khác | Message factory, signature parts |
| UsernameToken bị reject | PasswordType/credentials/callback sai | Credential store, nonce policy |
| Fault response không verify được | Fault đi nhánh policy khác | Fault handling, expected response actions |
| Chỉ lỗi sau nâng cấp | WSS4J action names/BSP/algorithm rules đổi | Version matrix, regression tests |
| Bật NoSecurity thì “hết lỗi” | Đã tắt validation bắt buộc | Khôi phục policy; chẩn đoán nguyên nhân gốc |
| Test chỉ xem XML tags vẫn pass với signature giả | Thiếu crypto validation thật | WSS4J verifier và negative tests |

### 27.1. Debug có thứ tự

Khi nhận thông báo “The security processing failed”:

1. Xem lỗi ở **securement outbound** hay **validation inbound**.
2. Xác định request hay response đang lỗi.
3. Kiểm tra đúng Spring-WS/WSS4J version và action names.
4. Xác nhận action order expectation khớp security results của sender.
5. Kiểm tra cert trust/key alias và private-key password callback.
6. Kiểm tra SOAP version, namespaces và signed/encrypted parts.
7. Kiểm tra Timestamp TTL/skew, replay và UsernameToken.
8. Kiểm tra một bước interceptor nào thay đổi XML sau ký không.
9. Tái hiện bằng fixtures và key test trên môi trường tách biệt.
10. Không tắt các checks để “đi đường vòng” qua security.

## 28. Bài thực hành: GetOrder có UsernameToken, Timestamp, Signature và Encrypt

Một bên **Order Client A** gọi **Order Server B** thông qua WSDL SOAP 1.1, XSD namespace `urn:example:orders:v1`.

Contract yêu cầu:

~~~text
Request A -> B:
    UsernameToken Timestamp Signature
    Signed: Body, Timestamp, wsa:Action
    Authentication: account A + signed identity
    TLS: HTTPS

Response B -> A:
    Timestamp Signature Encrypt
    Signed/encrypted targets và protection order
    phải được thống nhất bằng WS-Security policy
~~~

### Các nhiệm vụ

1. Ghi rõ request/response action lists ở **cả hai phía**.
2. Giải thích vì sao server dùng `validationActions` cho request nhưng `securementActions` cho response.
3. Giải thích vì sao client dùng `securementActions` cho request nhưng `validationActions` cho response.
4. Tạo JAXB binding/XSD GetOrderRequest/GetOrderResponse với QName đúng.
5. Cấu hình SOAP 1.1 message factory và `WebServiceTemplate`.
6. Cấu hình WSS4J action names, UsernameToken callback và Timestamp policy.
7. Tạo **hai cặp test key** riêng: client signing/decryption, server signing/decryption theo policy thực.
8. Đăng ký server interceptor ở đúng endpoint registry và client interceptor ở đúng template.
9. Tạo WS-Addressing Action/To trước bước ký nếu policy yêu cầu ký headers.
10. Cấu hình `securementSignatureParts` chứa Body, Timestamp và Action QName theo SOAP/WS-A versions.
11. Cấu hình partner public encryption certificate và own private decryption key.
12. Thử profile sign-before-encrypt và test partner chỉ chấp nhận protection order được công bố.
13. Kiểm tra inbound `validationActions` khớp action results thật, không đảo chuỗi máy móc.
14. Test positive request/response có signed parts và trust đúng.
15. Test thiếu UsernameToken, Timestamp hoặc Signature.
16. Test sửa Body hoặc Action sau khi ký.
17. Test certificate lạ/hết hạn, Timestamp expired, nonce replay.
18. Test decryption bằng wrong private key.
19. Test SOAP 1.2/1.1 binding mismatch và Payload XSD invalid.
20. Test SOAP Fault không bị diễn giải nhầm thành normal JAXB response.
21. Ghi metrics theo phase/outcome, không log raw SOAP secrets.
22. Viết tài liệu support matrix Spring-WS × WSS4J × partner policy.

**Tiêu chí đạt:** Client/server có action profiles rõ ràng từng chiều, đúng signature/encryption parts, validation thật sự từ chối message bị sửa hoặc không trust, Fault được xử lý an toàn và có regression tests trước mỗi nâng cấp.

## 29. Checklist trước khi đưa WS-Security actions vào production

- [ ] Phân biệt `securementActions` (outbound) và `validationActions` (inbound).
- [ ] Request và response có profile riêng, không mặc định đồng nhất.
- [ ] Hành động được viết đúng token và đúng thứ tự theo WSS4J/policy.
- [ ] Không tự động đảo ngược validation action list so với securement list.
- [ ] Có tests xác nhận action order và action result enforcement.
- [ ] Interceptor đã đăng ký đúng template/endpoint chain.
- [ ] SOAP Header nghiệp vụ được tạo **trước** khi ký nếu phải ký.
- [ ] Signed parts gồm Body, Timestamp, WS-A Header cần bảo vệ theo policy.
- [ ] Encrypted parts chọn đúng Element/Content và QName.
- [ ] Ký trước/mã hóa trước phù hợp profile đối tác.
- [ ] Securement dùng own private signing key và recipient public encryption cert.
- [ ] Validation dùng sender public trust và own private decryption key.
- [ ] UsernameToken password/callback được quản lý qua secret store, không hard-code.
- [ ] Timestamp TTL, clock skew, nonce/replay cache và idempotency được kiểm soát.
- [ ] Certificate rotation, trust chain và authorization đã được kiểm chứng.
- [ ] Không tắt BSP hoặc cho phép RSA15 key transport nếu chưa có exception policy.
- [ ] SOAP 1.1/1.2 Body namespace và Header role/actor chính xác.
- [ ] SOAP Fault/security exception không tiết lộ key/password/stack trace.
- [ ] XSD validation, XML parser hardening và TLS không bị bỏ qua.
- [ ] Không log raw SOAP Envelope/UsernameToken/EncryptedKey/decrypted data.
- [ ] Có crypto-enabled positive và negative integration tests.
- [ ] Có test interoperability với đối tác/stack độc lập khi khả thi.
- [ ] Có monitoring lỗi Signature, Timestamp, Trust, Decrypt và action order.
- [ ] Có kế hoạch rollback và tương thích khi đổi WSS4J/Spring-WS version.

## 30. Tổng kết và câu hỏi tự kiểm tra

- **`securementActions`** mô tả các actions bảo vệ message gửi đi.
- **`validationActions`** mô tả security actions cần nhận diện và kiểm chứng ở message nhận vào, có enforcement thứ tự theo WSS4J.
- **Client:** secure request, validate response. **Server:** validate request, secure response.
- **Order có nhiều lớp:** action list, interceptor chain, XML element order, và sign/encrypt protection order; không đồng nhất chúng.
- **Token name không đủ:** đúng key, cert trust, signed/encrypted parts, thuật toán, timestamp/replay và policy mới quyết định tính an toàn.
- **`Encrypt` vs `Encryption`** cần kiểm chứng theo đúng Spring-WS/WSS4J version.
- **BSP, TLS, XSD và XML parser hardening** bổ sung chứ không thay thế WS-Security.
- **SOAP Fault và transport errors** khác WS-Security validation/securement failure.
- **Kiểm thử thật phải dùng crypto keys mẫu và message verifier**, không chỉ assert sự xuất hiện của vài XML nodes.

**Câu hỏi tự kiểm tra:** Client A gửi `Timestamp Signature Encrypt`, nhưng server B đặt `validationActions="Encrypt Signature Timestamp"` vì cho rằng bước validation phải đảo ngược thứ tự securement. Một request bị từ chối, trong khi engineer nhìn SOAP Header vẫn thấy đủ Timestamp, Signature và EncryptedKey. Hãy chỉ ra vì sao không thể kết luận lỗi nằm ở thiếu token, cách kiểm tra inbound action results/order và signed/encrypted parts, key/trust/algorithm, và thiết kế ít nhất năm negative tests chứng minh rằng server chỉ chấp nhận đúng security profile của hợp đồng.

## 31. Tài liệu tham khảo để đối chiếu theo phiên bản

- Spring Web Services Reference, phần WSS4J security interceptor và các thuộc tính `validationActions`/`securementActions`: https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/
- Spring Web Services API cho `Wss4jSecurityInterceptor` của dòng 4.0.x: https://docs.spring.io/spring-ws/docs/4.0.15/api/org/springframework/ws/soap/security/wss4j2/Wss4jSecurityInterceptor.html
- Apache WSS4J, action names và configuration constants: https://ws.apache.org/wss4j/config.html
- Apache WSS4J, hướng dẫn cơ chế xử lý actions: https://ws.apache.org/wss4j/using.html

Khi dự án đang dùng các phiên bản khác, hãy ưu tiên **Javadocs và release notes đúng dependency đã pin**; tài liệu cũ có thể sử dụng tên action, property hoặc package khác. Không thay đổi production security policy chỉ bằng suy luận từ ví dụ của một phiên bản khác.




