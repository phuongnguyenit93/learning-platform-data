# Yêu cầu bảo mật bắt buộc, header bị thiếu và tránh đường đi bỏ qua xác minh

> **Chương:** WS-Security  
> **Module:** SPRING_WEB_SERVICES — Phát triển dịch vụ SOAP theo hướng **contract-first** với Spring Web Services: thiết kế XSD/WSDL, JAXB/OXM, endpoint và SOAP client; xử lý SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích trong tích hợp doanh nghiệp.

## 1. Mục tiêu: “không có Security Header” phải là một quyết định bảo mật

Giả sử một SOAP service nhận lệnh `SubmitPaymentRequest`. Tổ chức quy định caller phải gửi **WS-Security Timestamp** hợp lệ và **chữ ký số** được xác minh bằng certificate của đối tác, trong đó chữ ký bắt buộc phải bao phủ SOAP Body. Nếu request không có `wsse:Security`, hành vi an toàn mặc định là **từ chối trước khi gọi nghiệp vụ**; không tự chuyển sang “chế độ không bảo mật” chỉ vì header vắng.

Lỗi thiết kế nguy hiểm không nhất thiết là kiểm tra chữ ký sai. Đôi khi hệ thống chỉ **kiểm tra khi header tồn tại**, nhưng nếu không có header thì tiếp tục xử lý:

~~~java
// PHẢN VÍ DỤ: security là tùy chọn ngoài ý muốn.
if (soapSecurityHeaderExists(request)) {
    verifySignature(request);
}
processPayment(request);
~~~

Đây là **security bypass**: attacker chỉ cần bỏ `wsse:Security` để tránh bước xác minh. Một biến thể khác là endpoint mapping chưa gắn security interceptor, hoặc exception từ validation bị nuốt rồi endpoint vẫn chạy.

Sau bài học, bạn cần biết cách:

- Định nghĩa **bảo mật bắt buộc theo operation và message direction**, không chỉ “bật WS-Security đâu đó”.
- Phân biệt header **không có**, header **rỗng**, header **có nhưng gửi sai actor/role**, và header **có nhưng chưa được xác minh**.
- Hiểu `mustUnderstand` của SOAP **không tự thay thế** yêu cầu signature, token hay timestamp.
- Cấu hình WSS4J/Spring-WS để **không bỏ qua** request thiếu security actions bắt buộc.
- Đảm bảo endpoint không thực thi khi **không đủ chữ ký, signed coverage, certificate trust, timestamp hoặc replay controls** theo hợp đồng.
- Kiểm tra các đường đi khác nhau: SOAP 1.1/1.2, endpoint mappings, SOAP Fault, các callback trước/sau interceptor, client và gateway.
- Thiết kế test chứng minh **input không đáp ứng policy không thể gây side effect nghiệp vụ**.
- Ghi log kết quả kiểm tra mà không tiết lộ token, certificate key material hoặc SOAP Body nhạy cảm.

**Nguyên tắc cốt lõi:** Có `wsse:Security` không đồng nghĩa nó hợp lệ; không có `wsse:Security` không đồng nghĩa đó là request công khai. Quyết định xử lý phải xuất phát từ **security policy do server kiểm soát**, sau đó được thực thi theo hướng **fail closed**.

## 2. Threat model: các đường “đi vòng” xác minh phổ biến

Bảo vệ SOAP enterprise thường phải chịu cả input không đáng tin và sự sai khác cấu hình giữa các endpoints hoặc HTTP routes.

~~~mermaid
flowchart TD
    Client["SOAP caller"]
    G["HTTP / TLS / gateway"]
    P["SOAP parser / message factory"]
    M["EndpointMapping"]
    S["WS-Security validation"]
    V["Contract + authorization"]
    E["Endpoint"]
    B["Business side effects"]
    Client --> G --> P --> M --> S
    S -->|Xác minh đúng policy| V --> E --> B
    S -->|Thiếu/sai action hoặc cover| F["Reject / Fault / denial"]
    P -. "Lỗi parse trước dispatch" .-> F
    M -. "Endpoint không được bảo vệ?" .-> R["Bypass risk"]
    R -. "Phải ngăn bằng coverage kiểm thử" .-> F
~~~

Đây là sơ đồ **trách nhiệm và điểm chặn**, không phải sơ đồ thực thi nội bộ cố định của mọi Spring-WS release. SOAP parser, endpoint mapping, WSS4J và interceptor ordering có thể thay đổi theo cấu hình; security kiểm soát bắt buộc phải bảo đảm **không có đường đến nghiệp vụ** khi policy chưa thỏa.

### 2.1. Các kiểu bypass cần phân biệt

| Kiểu sai sót | Điều attacker hoặc lỗi cấu hình khai thác | Hậu quả |
|---|---|---|
| Header optional vô ý | Nếu thiếu `wsse:Security` thì bỏ qua verify | Request unsigned vẫn được xử lý |
| Action không đầy đủ | Chỉ kiểm Timestamp, quên Signature | Body có thể bị sửa mà không phát hiện |
| Signature coverage thiếu | Có chữ ký hợp lệ trên một Header không quan trọng | SOAP Body quan trọng không được bảo vệ |
| Sai actor/role | Security Header hướng tới một SOAP node khác | Server dùng/đếm nhầm header không dành cho nó |
| Duplicate/ambiguous elements | Hai Body hoặc element cùng ID, XPath lấy sai node | Signature wrapping / signed-node confusion |
| Security interceptor thiếu ở mapping | Một endpoint mới hoặc alias URL không được gắn bảo vệ | Cùng operation có đường công khai |
| Exception swallowed | Verify ném lỗi nhưng catch-and-continue | Side effect xảy ra sau thất bại |
| Mixed protected/public operations | Dựa vào URI chung hoặc SOAPAction chưa đáng tin để chọn chế độ | Sensitive operation bị route dưới policy yếu |
| UsernameToken kiểm tra yếu | Chỉ kiểm “có token”, không xác thực giá trị/replay | Giả mạo danh tính |
| Trust validation sai | Tin mọi certificate hoặc không kiểm signer identity | Chữ ký hợp lệ từ key không được cấp quyền |
| Fault path khác normal path | Error handler gửi/echo dữ liệu khi chưa xác minh | Rò PII, token và business state |
| Client bỏ verify response | Chỉ ký outgoing request, không verify incoming response | Chấp nhận response giả/mới bị sửa |

### 2.2. Hai loại “bỏ qua” đặc biệt

**Bỏ qua do không có header:** nếu middleware chỉ gọi verifier khi tìm thấy `wsse:Security`, một request thiếu header có thể được xử lý. Đây là lỗi **enforcement**.

**Bỏ qua do chữ ký không phủ dữ liệu sử dụng:** verifier có thể trả “signature cryptographically valid” vì một phần tử được ký hợp lệ, nhưng business code lại dùng Body khác/chưa ký. Đây là lỗi **coverage/binding giữa security và business data**.

Hai loại này cần bộ kiểm thử khác nhau. Một test chỉ đưa chữ ký giả và chờ exception **không** chứng minh service từ chối request hoàn toàn không có `wsse:Security`.

## 3. Cấu trúc SOAP Security Header và trạng thái phải phân biệt

WS-Security thường đặt thông tin security trong SOAP Header theo namespace:

~~~text
http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd
~~~

Timestamp và các attribute `wsu:Id` thường dùng namespace:

~~~text
http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd
~~~

SOAP 1.1 và SOAP 1.2 có namespace/semantics Header khác nhau, nên không nên xem mọi Envelope XML là tương đương chỉ vì cùng local name.

### 3.1. Mảnh SOAP Header có security elements

~~~xml
<soapenv:Header
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
    xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
  <wsse:Security soapenv:mustUnderstand="1">
    <wsu:Timestamp wsu:Id="ts-1">
      <wsu:Created>2026-11-27T02:00:00Z</wsu:Created>
      <wsu:Expires>2026-11-27T02:05:00Z</wsu:Expires>
    </wsu:Timestamp>
    <ds:Signature>
      <!-- SignedInfo, References, SignatureValue, KeyInfo thật -->
    </ds:Signature>
  </wsse:Security>
</soapenv:Header>
~~~

**Đây là mảnh XML minh họa, không phải chữ ký hợp lệ.** Các giá trị thời gian là fixture lịch sử, không dùng làm timestamp mới cho request thực. Một signature đúng phải do thư viện WS-Security/XML Signature tạo, dùng khóa/certificate và references theo policy. Không sao chép mảnh XML rồi tự chèn `SignatureValue` cho production.

### 3.2. Sáu trạng thái không được gom thành “có Security Header”

| Trạng thái | Ví dụ | Hệ thống yêu cầu Timestamp + Signature nên làm gì? |
|---|---|---|
| **Không có** `wsse:Security` | Envelope chỉ có Body | **Reject** |
| **Rỗng** | `<wsse:Security/>` | **Reject** vì thiếu actions |
| **Chỉ Timestamp** | Có Timestamp, không Signature | **Reject** vì thiếu Signature |
| **Có Signature nhưng verify fail** | Digest/key/algorithm không hợp lệ | **Reject** |
| **Signature verify pass nhưng Body chưa được ký** | Chỉ ký Header phụ | **Reject** theo coverage policy |
| **Đủ action, coverage, trust, freshness và authorization** | Signature bảo vệ đúng Body/Headers, signer được phép | Tiếp tục nghiệp vụ |

Một SOAP Header có thể chứa nhiều security blocks hướng đến các roles/nodes khác nhau theo quy tắc SOAP/WS-Security. Vì vậy không được đếm một `wsse:Security` bất kỳ ở bất kỳ vị trí nào như bằng chứng receiver này đã được bảo vệ.

### 3.3. SOAP Body và global element từ XSD

Ví dụ SOAP Body contract-first:

~~~xml
<soapenv:Body
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1"
    xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
    wsu:Id="body-1">
  <ord:SubmitOrderRequest>
    <ord:orderId>ORD-1001</ord:orderId>
    <ord:amount>100.00</ord:amount>
  </ord:SubmitOrderRequest>
</soapenv:Body>
~~~

Nếu policy yêu cầu **SOAP Body được ký**, verifier cần chứng minh đúng Body được code nghiệp vụ sử dụng nằm trong signed references; sự tồn tại của `wsu:Id="body-1"` không có nghĩa element đó đã ký. Không tự tin ID do XML mang tới cho đến khi security library xác minh references/ID uniqueness và policy áp dụng đúng.

## 4. Định nghĩa “bắt buộc” bằng policy matrix, không bằng if rải rác

Trước khi cấu hình interceptor, hãy lập **ma trận kiểm soát theo operation** và hướng message.

| Operation | Request authentication | Request integrity | Freshness/replay | Response security | Side effect |
|---|---|---|---|---|---|
| `GetOrder` | Certificate/UsernameToken theo policy | Sign Body và required Headers | Timestamp, replay nếu yêu cầu | Sign response nếu contract yêu cầu | Chỉ đọc có phân quyền |
| `SubmitOrder` | Verified signer theo partner | Sign Body + WS-A headers được yêu cầu | Timestamp + replay check | Sign response/receipt | Tạo đơn |
| `CancelOrder` | Verified principal | Sign Body + order ID | Timestamp + replay check | Signed confirmation/Fault theo policy | Hủy đơn |
| `DownloadDocument` | Verified identity + authorization | Sign request | Freshness | Sign/encrypt/MTOM protection khi policy yêu cầu | Trả tài liệu nhạy cảm |
| `HealthCheck` trên public route riêng | Theo thiết kế riêng | Có thể không áp dụng SOAP WS-Security | Theo route | Không lộ nghiệp vụ | Không dùng chung sensitive endpoint |

Đây là **ma trận minh họa**, không phải security profile mặc định được Spring-WS tự áp dụng. Một hệ thống có thể yêu cầu mTLS, UsernameToken, X.509 signature, encryption hoặc token khác nhau; chuẩn cuối cùng phải được hai bên thỏa thuận qua WSDL/WS-SecurityPolicy và tài liệu vận hành.

### 4.1. Những thuộc tính policy cần chốt

- **Cơ chế authentication:** UsernameToken, X.509 certificate signature, SAML token, Kerberos hoặc profile cụ thể. Không coi chúng tương đương.
- **Actions bắt buộc:** Timestamp, Signature, Encryption, UsernameToken và thứ tự/tương tác theo policy.
- **Parts bắt buộc được ký:** SOAP Body; một số SOAP Headers, `wsa:To`, `wsa:Action`, `wsa:ReplyTo`, `wsa:MessageID` khi cần.
- **Parts bắt buộc được mã hóa:** thông tin cá nhân, financial content, attachments hoặc trường theo policy.
- **Trust:** certificate path, signer identity mapping, key usage, pinning/PKI policy nếu có.
- **Freshness/replay:** đồng hồ, TTL, nonce, created/expires, cache kiểm tra trùng và scope đa node.
- **SOAP version:** 1.1/1.2, actor/role, mustUnderstand, fault semantics.
- **Response/Fault protection:** server cũng phải ký/mã hóa response nếu contract quy định; client cũng phải verify.
- **Authorization:** authenticated principal/tenant có quyền với operation và resource ID hay không.

### 4.2. Phân biệt yêu cầu về Header và thực tế xác minh

Câu “Header phải có `wsse:Security`” là **yêu cầu hình thức tối thiểu**. Câu “Signature action bắt buộc và signature phải bảo vệ Body được dùng trong nghiệp vụ” là **yêu cầu thực thi mạnh hơn**.

Một sơ đồ ra quyết định đúng hướng:

~~~mermaid
flowchart TD
    A["SOAP request đến"] --> B["Policy cho operation + direction"]
    B --> C{"Required security actions hiện diện?"}
    C -->|Không| R["Reject trước side effect"]
    C -->|Có| D{"Cryptographic / token validation pass?"}
    D -->|Không| R
    D -->|Có| E{"Signed/encrypted parts đúng policy?"}
    E -->|Không| R
    E -->|Có| F{"Timestamp / replay / trust pass?"}
    F -->|Không| R
    F -->|Có| G{"Principal authorized với resource?"}
    G -->|Không| R
    G -->|Có| H["Endpoint business"]
~~~

Không phải mọi bước có cùng thứ tự kỹ thuật với mọi policy: một số SOAP stacks cần decrypt trước khi kiểm tra phần được ký, số khác xử lý signature trước encryption. Hãy để **WSS4J/security stack** vận hành theo profile đã phê duyệt; sơ đồ dùng để minh họa **điều kiện phải được thỏa tất cả**, không phải hướng dẫn tự viết một signature engine.

## 5. mustUnderstand, actor/role và tính bắt buộc của Security Header

### 5.1. mustUnderstand không phải signature validation

Trong SOAP 1.1:

~~~xml
<wsse:Security
    xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    soapenv:mustUnderstand="1">
  <!-- Security token/signature thực -->
</wsse:Security>
~~~

Trong SOAP 1.2, thuộc tính thuộc **namespace Envelope SOAP 1.2**, với giá trị boolean theo SOAP 1.2:

~~~xml
<wsse:Security
    xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
    xmlns:env="http://www.w3.org/2003/05/soap-envelope"
    env:mustUnderstand="true">
  <!-- Security token/signature thực -->
</wsse:Security>
~~~

**mustUnderstand** liên quan nghĩa vụ **SOAP node nhận đúng role** phải hiểu/xử lý header được nhắm tới hoặc phát Fault `MustUnderstand` theo SOAP processing model. Nó **không** nói rằng token đã được kiểm tra, signature hợp lệ, signer được trust, Body được ký hay timestamp còn hiệu lực.

Một sender có thể đặt `mustUnderstand="1"` lên một header rỗng; receiver vẫn phải **từ chối theo security policy** khi hành động bắt buộc thiếu. Ngược lại, **thiếu header hoàn toàn** không thể được phát hiện chỉ nhờ `mustUnderstand` vì không có header nào để buộc xử lý.

### 5.2. actor/role quyết định header dành cho node nào

SOAP 1.1 dùng thuộc tính `actor`; SOAP 1.2 dùng `role`. Một header có thể được định hướng tới một intermediary thay vì ultimate receiver.

Ví dụ SOAP 1.2:

~~~xml
<wsse:Security
    xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
    xmlns:env="http://www.w3.org/2003/05/soap-envelope"
    env:role="http://www.w3.org/2003/05/soap-envelope/role/next"
    env:mustUnderstand="true">
  <!-- Chỉ là cấu trúc minh họa -->
</wsse:Security>
~~~

Không dùng sự có mặt của một header hướng tới một node khác làm bằng chứng **ultimate receiver** đã đáp ứng security. Nếu ứng dụng chạy sau một ESB/gateway, cần có hợp đồng rõ ràng:

- Gateway xác minh phần nào?
- Backend có tự xác minh lại end-to-end message signature không?
- Nếu gateway chuyển thông tin identity đã xác thực, cơ chế bảo vệ hop-to-hop và chống giả mạo headers là gì?
- Ai chịu trách nhiệm từ chối request thiếu actions?
- Có thể request đi vòng gateway vào backend trực tiếp không?

Không tự suy luận `role="next"` hay `role="ultimateReceiver"` có thể thay cho phân quyền của nghiệp vụ. Mỗi SOAP node phải tuân thủ SOAP processing model theo role được cấu hình.

### 5.3. Đừng tạo ngoại lệ ngầm khi không có header

Một code path dễ mắc lỗi:

~~~java
// PHẢN VÍ DỤ: API trả null khi không có security header.
SoapHeaderElement security = findSecurityHeader(soap);
if (security != null) {
    securityVerifier.verify(security);
}
// Không có Security => tiếp tục xử lý, sai với protected operation.
return invokeEndpoint();
~~~

Đúng hướng:

~~~text
if protected operation:
    require security enforcement for this operation
    validate required security actions
    validate signature coverage and trust
    validate timestamp/replay policy
    validate business authorization
    only then invoke endpoint
else:
    apply explicitly documented public-operation policy
~~~

Đây là sơ đồ **chính sách**; không nên tự triển khai signature verification bằng Java tùy ý. Hãy để WSS4J bảo đảm xác minh mật mã, rồi kiểm tra policy coverage/authorization bằng các thành phần đã được kiểm chứng.

## 6. Cấu hình Spring-WS/WSS4J để yêu cầu security actions

### 6.1. Wss4jSecurityInterceptor đảm nhiệm những gì?

Spring-WS tích hợp Apache WSS4J qua security interceptor (ví dụ `org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor` ở các phiên bản hỗ trợ). Interceptor này có thể thực thi các actions như:

- `Timestamp`
- `Signature`
- `UsernameToken`
- `Encrypt` (tên action/cơ chế tùy profile WSS4J)
- Các hành động/token khác theo phiên bản và WS-SecurityPolicy.

**Cần xác minh chính xác API/tên action của Spring-WS/WSS4J version trong dự án**, vì các thế hệ package và thuộc tính có thể khác nhau. Bài này dùng WSS4J theo mô hình phổ biến, không thay việc khóa phiên bản thư viện và kiểm thử hành vi thật.

### 6.2. Cấu hình yêu cầu Timestamp và Signature cho inbound request

Ví dụ Bean trong ứng dụng đã có `@EnableWs`:

~~~java
package com.example.orders.security;

import org.apache.wss4j.common.crypto.Crypto;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

import java.util.List;

@Configuration
@EnableWs
public class SoapSecurityConfiguration implements WsConfigurer {

    private final Crypto partnerVerificationCrypto;

    public SoapSecurityConfiguration(
            @Qualifier("partnerVerificationCrypto") Crypto crypto) {
        this.partnerVerificationCrypto = crypto;
    }

    @Bean
    public Wss4jSecurityInterceptor requestSecurity() {
        Wss4jSecurityInterceptor interceptor =
                new Wss4jSecurityInterceptor();

        // Bắt buộc validation khi nhận SOAP request.
        interceptor.setValidateRequest(true);
        interceptor.setValidationActions("Timestamp Signature");
        interceptor.setValidationSignatureCrypto(
                partnerVerificationCrypto);

        // Quan trọng với policy bắt buộc: thiếu Security header
        // không được là lý do skip validation.
        interceptor.setSkipValidationIfNoHeader(false);

        return interceptor;
    }

    @Override
    public void addInterceptors(List<EndpointInterceptor> interceptors) {
        interceptors.add(requestSecurity());
    }

}
~~~

**Giới hạn quan trọng của ví dụ:** đây là **khung cấu hình** diễn giải API và chính sách, không phải ứng dụng Spring Boot độc lập. Phải cung cấp bean WSS4J `Crypto` với qualifier `partnerVerificationCrypto`, được cấu hình từ truststore/certificate policy của tổ chức. Nếu bean bắt buộc không tồn tại, Spring dependency injection phải **không cho ứng dụng khởi động**; tuyệt đối không fallback sang trust-all. Mẫu gọi bean method trong `addInterceptors` giả định `@Configuration` đang dùng proxyBeanMethods mặc định; nếu tắt proxy, cần tiêm đúng bean thay vì tự tạo interceptor mới.

Điều phải chốt trong môi trường thực:

1. `validationActions` yêu cầu các hành động cần thiết, nhưng **phải kiểm chứng bằng negative tests** rằng request không header, rỗng, thiếu một action đều bị từ chối.
2. `skipValidationIfNoHeader=false` là một biểu hiện quan trọng của **fail closed** nếu API/property có trong version đang dùng. Kiểm tra getter/setter và behavior của phiên bản thực, không mặc định một config giống nhau trên tất cả releases.
3. `validateRequest=true` bảo đảm ý định áp dụng inbound validation; phải kiểm tra interceptor thật sự nằm trong **chain của endpoint mapping cần bảo vệ**.
4. `Crypto` dùng để xác minh chữ ký/trust **phải** được cấu hình chính xác theo PKI, danh tính signer và certificate lifecycle; không dùng trust-all.
5. Thành công của `Timestamp Signature` **chưa tự chứng minh** SOAP Body và required Headers được ký đúng policy; coverage checks cần test riêng.
6. Nếu dự án có nhiều loại endpoints, không để public-operation policy trôi sang sensitive operation chỉ vì cùng URL/mapping.

Ví dụ cấu hình thực tế có thể dùng constructor injection vào một `@Configuration` object để tránh gọi method bean thủ công. Cần bảo đảm không đăng ký duplicate interceptors hoặc nhầm bean khi có nhiều `WsConfigurer`.

### 6.3. Vì sao không nên chỉ dùng WS-Security Header presence interceptor?

Phản ví dụ:

~~~java
public boolean handleRequest(MessageContext ctx, Object endpoint) {
    if (hasSecurityHeader(ctx)) {
        return true;
    }
    return false;
}
~~~

Đây mới là **kiểm tra hiện diện**, không phải xác minh mật mã hoặc policy. Nó không xác nhận:

- `UsernameToken` có password/nonce đúng không.
- `Timestamp` có hết hạn hay bị replay không.
- `ds:Signature` có chữ ký hợp lệ không.
- Signer certificate có trong trust policy và được cấp quyền không.
- Signature có ký **SOAP Body mà endpoint dùng** không.
- Header có đúng role/actor hay không.

Nếu cần một gate bắt buộc riêng, hãy xây nó trên **kết quả đã được WSS4J xác minh** và policy/authorization nội bộ, không trên việc tìm chuỗi `<wsse:Security>`.

### 6.4. Interceptor chỉ có hiệu lực trên đường dispatch nó tham gia

`WsConfigurer#addInterceptors(...)` là một cách đăng ký interceptors vào cấu hình Spring-WS, nhưng cần kiểm tra **tất cả EndpointMappings thực đang hoạt động** trong ứng dụng. Có thể có:

- `@PayloadRoot` mapping mặc định và mapping tự viết.
- SOAPAction hoặc WS-Addressing endpoint mappings.
- Một servlet riêng, URL alias hoặc service khác trong cùng application.
- Fault/error routes được xử lý trước dispatch.
- Endpoint đăng ký thêm sau khi khởi tạo cấu hình.
- Một SOAP request đến từ broker/JMS hoặc một ingress khác nếu ứng dụng hỗ trợ.

**Không** chỉ test một operation “happy path”. Hãy lập inventory operation → transport → servlet/message receiver → endpoint mapping → security interceptor chain, rồi test mọi entrypoint có thể gọi business method nhạy cảm.

## 7. Signature verification khác yêu cầu “Body phải được ký”

### 7.1. Signature hợp lệ chưa đủ nếu ký sai phần

Giả sử SOAP request có `wsse:Security` và một `ds:Signature` hợp lệ, nhưng reference chỉ tới:

~~~xml
<ord:ClientNote
    xmlns:ord="urn:example:orders:v1"
    Id="note-1">hello</ord:ClientNote>
~~~

Trong khi request Body chứa:

~~~xml
<ord:SubmitOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:orderId>ORD-1001</ord:orderId>
  <ord:amount>100.00</ord:amount>
</ord:SubmitOrderRequest>
~~~

Nếu policy của operation yêu cầu Body được ký mà verifier chỉ xác nhận **có một chữ ký hợp lệ nào đó**, thì phần dữ liệu ảnh hưởng đến nghiệp vụ có thể vẫn **chưa được bảo vệ**.

Cần chứng minh:

- References của chữ ký bao phủ **đúng SOAP Body** (hoặc các elements được policy định nghĩa).
- Các required Headers như `wsa:Action`/`To`/`ReplyTo` có signed coverage nếu policy yêu cầu.
- Reference URI/`wsu:Id` được resolve duy nhất, không bị nhầm vì duplicate IDs.
- Không có XML Signature Wrapping: phần business handler đọc phải chính là phần đã được verify.
- Signature algorithm/key/trust phù hợp policy.
- Không có interceptor sửa signed elements sau verify trước khi nghiệp vụ sử dụng.

### 7.2. Ví dụ khác biệt giữa giá trị XML và dữ liệu được ký

~~~xml
<ord:amount xmlns:ord="urn:example:orders:v1">100.00</ord:amount>
~~~

và:

~~~xml
<ord:amount xmlns:ord="urn:example:orders:v1">100</ord:amount>
~~~

có thể biểu diễn cùng giá trị `xs:decimal` nhưng **khác nội dung XML** để tính digest theo canonicalization/transforms của XML Signature. JAXB re-marshalling hoặc interceptor “chuẩn hóa giá” sau khi ký có thể làm signature fail.

Ngược lại, không phải mọi thay đổi whitespace/prefix ngoài signed references đều làm digest thay đổi. Phải kiểm tra **transforms và signed reference set**, không dùng quy tắc “XML text khác nhau nghĩa là signature luôn sai”.

### 7.3. Dấu hiệu Signature Wrapping cần test

Một message có thể có:

- Một element đã ký nhưng không nằm trong SOAP Body mà business handler dùng.
- Hai elements có local name gần giống nhau hoặc ở namespaces khác.
- Một `wsu:Id` bị trùng/được parser xử lý không nhất quán.
- Một SOAP Body được ký nhưng code chọn phần tử khác bằng XPath `local-name()`.
- Security Header có chữ ký thuộc một role khác với receiver.

**Không tự viết XML Signature verifier bằng XPath thô.** Dùng WSS4J, xác minh required signed parts với đúng policy và thêm negative tests cho wrapping/duplicate ID. Nếu thư viện xác minh chữ ký thành công nhưng business sử dụng DOM node khác, cần sửa **ràng buộc security-to-business**, không chỉ thêm một check “Header tồn tại”.

## 8. UsernameToken, Timestamp, nonce và chống replay

### 8.1. UsernameToken không đồng nghĩa đã đăng nhập

Một SOAP Header có thể chứa:

~~~xml
<wsse:UsernameToken
    xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
    xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
    wsu:Id="ut-1">
  <wsse:Username>partner-a</wsse:Username>
  <wsse:Password>not-a-real-secret</wsse:Password>
</wsse:UsernameToken>
~~~

**Đây là một mảnh XML giả để minh họa cấu trúc, không đủ để authentication.** Một UsernameToken production còn chịu ràng buộc của token profile và security policy (PasswordText/PasswordDigest, nonce, created, timestamp, transport, trust, replay protection).

Các lỗi phổ biến:

1. Chỉ đọc `Username` rồi gán principal.
2. Token không có password nhưng vẫn được chấp nhận ở operation yêu cầu password.
3. PasswordDigest được coi như encryption; thực tế digest không thay thế TLS hoặc message encryption.
4. Không kiểm tra nonce/created/replay.
5. Cho phép bypass khi UsernameToken hoàn toàn vắng.
6. Dùng credential validator làm “allow all” cho môi trường debug rồi quên gỡ.
7. Cho phép identity `partner-a` trong SOAP Body thay thế identity đã xác thực của token.

**Đúng hướng:** WSS4J/token validator và callback handler phải kiểm tra credential theo policy; principal và roles phải được xây từ **kết quả authentication đã verify**, không từ tên người dùng do XML tự khai.

### 8.2. Timestamp là dữ liệu cần verify, không chỉ là hai thẻ XML

~~~xml
<wsu:Timestamp
    xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">
  <wsu:Created>2026-11-27T02:00:00Z</wsu:Created>
  <wsu:Expires>2026-11-27T02:05:00Z</wsu:Expires>
</wsu:Timestamp>
~~~

Khi policy yêu cầu Timestamp, cần kiểm tra:

- Timestamp **thực có** và được WSS4J xử lý thành công.
- `Created` không quá cũ hoặc quá xa tương lai theo clock-skew policy.
- `Expires` chưa quá hạn, và TTL hợp lệ.
- Timestamp nằm trong phạm vi **chữ ký** nếu security policy yêu cầu integrity của thời gian.
- Cơ chế replay cache/nonce/MessageID được triển khai với TTL và scope phù hợp, nhất là nhiều node.
- Đồng hồ các hệ thống dùng NTP và có alert lệch giờ.

**Timestamp được verify ≠ đã có replay protection hoàn chỉnh.** Một request cũ còn trong cửa sổ hợp lệ có thể bị phát lại nếu không có deduplication cache, nonce hoặc idempotency protection theo hợp đồng.

### 8.3. Các thao tác có side effect cần chống replay mạnh hơn

Lệnh `SubmitPayment` hoặc `CancelOrder` cần kiểm tra cả **security replay** lẫn **business idempotency**:

| Kiểm soát | Ngăn loại lỗi nào? | Có đủ một mình không? |
|---|---|---|
| Signed Timestamp | Giới hạn độ tươi và bảo vệ thời gian | Không nếu replay trong TTL |
| UsernameToken nonce | Giúp phát hiện lặp token khi được cache/verify | Không thay nghiệp vụ idempotency |
| `wsa:MessageID` | Tương quan request, phát hiện duplicate nếu lưu | Không tự là bằng chứng authentication |
| Idempotency key do hai bên thống nhất | Chống tạo side effect hai lần | Không thay signature/authorization |
| WS-Security signature | Bảo vệ integrity và signer identity theo policy | Không tự cấm replay nguyên message |

Không đưa request tới business service chỉ vì Timestamp parse được hoặc MessageID có vẻ ngẫu nhiên. Cần chính sách cache và authorization rõ ràng, đồng thời cân nhắc race conditions ở hệ thống phân tán.

## 9. Encryption, signed parts và MTOM: tránh kiểm tra sai tầng

### 9.1. Encryption không đồng nghĩa tất cả thông tin được bảo vệ

Một operation có thể yêu cầu:

- SOAP Body có chữ ký để phát hiện sửa đổi và ràng buộc identity.
- SOAP Body hoặc một số elements được mã hóa theo WS-SecurityPolicy.
- Timestamp được ký; các SOAP Headers nhạy cảm được ký hoặc mã hóa.
- Binary attachments được bảo vệ theo profile đã thống nhất.

Nếu message chỉ có `EncryptedData` nhưng **thiếu Signature** mà policy yêu cầu, không được chấp nhận. Ngược lại, chữ ký hợp lệ không tự chứng minh confidentiality khi ứng dụng cần encryption ở mức message.

### 9.2. Thứ tự sign/encrypt phải theo policy

~~~mermaid
flowchart TD
    A["JAXB/XML Body và Headers"] --> B["WS-Security outbound policy"]
    B --> C["Signature / Encryption theo profile"]
    C --> D["SOAP qua HTTPS"]
    D --> E["WSS4J inbound policy"]
    E --> F["Verified/decrypted message parts"]
    F --> G["Authorization + business"]
~~~

Một số WS-SecurityPolicy yêu cầu sign-before-encrypt; một số khác có yêu cầu khác. Không tự hardcode “decrypt luôn trước verify” hoặc “verify luôn trước decrypt” cho mọi môi trường. Cần kiểm tra action processing order, reference IDs và profile của đối tác.

**Điểm quan trọng:** `wsse:Security` chứa Encryption nhưng **thiếu Signature** vẫn phải bị từ chối nếu Signature bắt buộc. Một action không tự thay thế action khác vì parser đã giải mã được SOAP Body.

### 9.3. XML Signature Wrapping sau decryption

Phần dữ liệu JAXB/DOM endpoint sử dụng phải **chính là phần có integrity được xác minh**. Sau decryption, không chọn nhầm element không được ký bằng XPath rộng hoặc so local name mà bỏ namespace. Nếu WSS4J xác minh một `Reference URI` nhưng endpoint dùng Body khác, policy chưa được thực thi đúng.

### 9.4. MTOM/attachments cần kiểm tra riêng

Một field `xs:base64Binary` có thể truyền inline Base64 hoặc bằng MTOM/XOP trong MIME parts. Nếu policy yêu cầu integrity của attachment:

- Chữ ký phải bảo vệ content theo **profile WS-Security/MTOM** phù hợp, không chỉ placeholder `xop:Include`.
- Content-ID, MIME parts và signed references phải nhất quán.
- Test checksum bytes sau giải mã và test signature riêng (checksum không thay authentication).
- Không đọc hết attachments vào `ByteArrayOutputStream` chỉ để kiểm tra/logging.
- Giới hạn số MIME parts, decoded bytes, disk spooling, request timeouts và concurrency.
- Không để đường nhận multipart bỏ qua security interceptor của SOAP requests khác.

**Bật MTOM không tự tạo attachment signing.** Hai cơ chế khác nhau; phải cấu hình profile và kiểm thử end-to-end.

## 10. Không để endpoint mapping, interceptor order hoặc lỗi sớm bỏ qua xác minh

### 10.1. Một security policy phải bao phủ mọi entrypoint

Cùng một operation có thể được gửi qua:

~~~text
/soap/orders
/ws/orders
/legacy/soap
/gateway/partner-a/orders
~~~

Những URL này là ví dụ. Nếu chỉ `/soap/orders` đi qua `MessageDispatcherServlet` gắn WSS4J interceptor, còn `/legacy/soap` gọi cùng service logic nhưng không có gate, policy có **lỗ hổng triển khai** dù tuyến chính đúng.

| Lớp | Câu hỏi |
|---|---|
| Gateway/load balancer | Có route nào đến SOAP backend nhưng bỏ qua kiểm tra không? |
| Servlet mapping | Những URL nào vào `MessageDispatcherServlet`? |
| Alternate ingress | JMS, batch, REST/internal adapter có gọi business trực tiếp không? |
| EndpointMapping | PayloadRoot, SOAPAction, WS-Addressing, custom mapping nào active? |
| Interceptor chain | WSS4J interceptor có trong chain của mọi protected operation không? |
| Method dispatch | Endpoint nào có side effects? |
| Security context | Principal có từ kết quả verify hay từ input caller? |
| Business authorization | Có kiểm tra operation/resource cho mọi đường vào service không? |

Một kiểm soát **security-at-boundary** bảo vệ SOAP; **authorization trong business/service layer** bổ sung defense-in-depth cho những API khác. Không thay gate SOAP bằng check nghiệp vụ yếu hơn.

### 10.2. Interceptor order và side effects

`EndpointInterceptor` có callbacks `handleRequest`, `handleResponse`, `handleFault` và `afterCompletion`, với thứ tự và semantics phụ thuộc phiên bản/config.

Cần xác minh:

- Interceptor nào có thể đọc raw/decrypted SOAP trước security verification?
- Interceptor nào có thể ghi DB, publish event hoặc tạo side effect trước khi verify?
- Khi WSS4J từ chối request, endpoint và các interceptors phía sau có chạy không?
- Nếu một interceptor trước đó trả false hoặc ném exception, có đường fallback nào gọi service không?
- Response signing có chạy với normal response và SOAP Fault theo contract không?
- Khi lỗi xảy ra trước mapping, có error handler nào rò dữ liệu không?

**Không coi thứ tự code trong `addInterceptors` là chứng cứ duy nhất.** Dùng integration tests để quan sát hành vi thật.

### 10.3. Header absent cần test theo mọi cách định tuyến

Với một protected `SubmitOrderRequest`, gửi cùng SOAP Body nhưng thay đổi:

1. Route HTTP, URL alias và reverse-proxy path được phép.
2. SOAPAction đúng, thiếu và sai.
3. `wsa:Action` đúng, sai và thiếu theo policy.
4. SOAP 1.1/1.2 nếu cả hai được hỗ trợ.
5. `wsse:Security` hoàn toàn vắng.
6. `wsse:Security` rỗng hoặc chỉ có một action.
7. `wsse:Security` gửi sai actor/role.
8. Signature hợp lệ nhưng không bảo vệ Body bắt buộc.

**Kết quả yêu cầu:** không có business side effect nếu message không đáp ứng security policy. Nếu không map được endpoint, từ chối ở tầng routing/protocol và không “fallback” sang business.

### 10.4. Lỗi trước interceptor vẫn phải an toàn

XML không well-formed, SOAP version sai hoặc HTTP Body vượt quota có thể bị chặn tại proxy/message factory **trước WSS4J**. Điều này không phải bypass nếu business chưa chạy; nhưng vẫn phải bảo đảm:

- Parser không tải external entities/DTD.
- Error response không echo raw XML, token hoặc secret.
- Không có business side effect.
- Không tự gửi SOAP Fault tới `wsa:FaultTo` chưa được authorize.
- Không dùng URI, exception text hoặc Header chưa xác thực làm log/metric labels không giới hạn.

### 10.5. Không xác thực bằng các header tự khai

Không suy identity từ `X-Partner-Id` chưa được gateway xác thực, SOAP `<PartnerId>`, `MessageID`, `ReplyTo`, `UsernameToken` chưa verify hoặc `ds:KeyInfo` chưa kiểm trust. TLS thành công cũng không tương đương mTLS client authentication và business authorization.

Nếu gateway terminate mTLS, backend chỉ nên nhận principal thông qua kết nối/headers được bảo vệ, và phải chặn direct backend bypass. Một certificate hợp lệ không tự cấp quyền `CancelOrder` cho mọi tenant.

## 11. SOAP Fault và error handling vẫn phải giữ fail-closed semantics

### 11.1. Request không đạt policy nên nhận lỗi gì?

Một request thiếu `wsse:Security` khi policy yêu cầu phải bị **từ chối**. Việc ánh xạ thành SOAP Fault hoặc HTTP error phụ thuộc SOAP 1.1/1.2, Spring-WS exception resolver, WSS4J và contract.

Ví dụ SOAP 1.1 Fault tối giản:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <soapenv:Fault>
      <faultcode>soapenv:Client</faultcode>
      <faultstring>Security requirements not satisfied</faultstring>
    </soapenv:Fault>
  </soapenv:Body>
</soapenv:Envelope>
~~~

**Đây là ví dụ lỗi chung, không phải Fault bắt buộc cho mọi WS-Security profile.** SOAP 1.2 dùng `Code`/`Reason` khác; WSS4J có thể trả security-specific codes/subcodes. Không hardcode Fault template nếu profile tương tác yêu cầu mã khác.

Bất kể format nào:

- Không gọi endpoint business.
- Không chuyển request sang anonymous fallback.
- Không thực thi nghiệp vụ rồi trả Fault để “debug”.
- Không tiết lộ nội dung signature, password, truststore, private key hoặc stack trace.
- Không dùng `wsa:FaultTo` chưa được authorize để gửi thông tin lỗi.
- Không mô tả quá chi tiết nguyên nhân password/certificate fail cho caller, tạo oracle thử khóa.

### 11.2. Đừng nuốt security exceptions rồi trả response nghiệp vụ

~~~java
// PHẢN VÍ DỤ: verification failure bị biến thành guest mode.
try {
    verifyInboundSecurity(message);
} catch (Exception ex) {
    log.warn("Verification failed, continuing as guest");
}
return orderService.submit(request);
~~~

Với protected operation, security failure **phải dừng** trước side effect. Khi WSS4J/credential service/truststore không khả dụng, fail closed theo policy vận hành, không “cho qua để giữ uptime”.

Cũng không nên:

~~~java
if (validationFailed) {
    return defaultOrderResponse(); // Sai với protected operation.
}
~~~

Đó có thể biến lỗi bảo mật thành response thành công giả hoặc làm lộ existence của đơn hàng.

### 11.3. Fault có phải được ký không?

Nếu WS-SecurityPolicy yêu cầu sign/encrypt response, cần phân biệt **normal response, modeled business Fault và security/protocol Fault**:

| Loại response | Cần kiểm tra |
|---|---|
| Normal SOAP response | Required signed/encrypted parts, signer trust, timestamp |
| Modeled business Fault | Security protection theo contract và data classification |
| Fault do verify inbound signature fail | Có thể phát sinh trước khi biết caller identity/key; theo security fault profile |
| Parser/transport error | Có thể chưa tạo được SOAP message để ký |
| HTTP/TLS handshake failure | Không có SOAP Fault hợp lệ nếu chưa hoàn thành transport |

Không áp dụng mù “mọi Fault đều có chữ ký” nếu lỗi xảy ra trước khi tạo security context/recipient key. Đồng thời không dùng security Fault exception làm lý do gửi plaintext business detail.

### 11.4. Ghi nhận lỗi mà không tiết lộ dữ liệu

Một log vận hành an toàn:

~~~text
service=orders
operation=SUBMIT_ORDER
security_result=DENIED
reason_code=REQUIRED_ACTION_MISSING
phase=INBOUND_SECURITY
~~~

Không log raw SOAP Header/Body, UsernameToken/password digest, `SignatureValue`, private key, attachment hoặc toàn bộ certificate chain. `reason_code` do server định nghĩa trong allowlist, không phải giá trị tùy ý lấy từ exception/user input.

## 12. SOAP client cũng phải bắt buộc xác minh response

`WebServiceTemplate` có thể ký outgoing request, nhưng điều đó **không tự xác minh** incoming response. Nếu contract yêu cầu server-signed response, client phải kiểm tra signature và coverage trước khi dùng JAXB object trong nghiệp vụ.

### 12.1. Outbound securement khác inbound validation

| Trên client | Vai trò | Rủi ro nếu thiếu |
|---|---|---|
| Securement | Ký/mã hóa SOAP request | Server từ chối hoặc message mất integrity/confidentiality |
| Response validation | Xác minh response signature, Timestamp, trusted server signer | Chấp nhận dữ liệu giả/bị sửa |
| TLS peer authentication | Xác minh CA/hostname HTTPS server | Kết nối nhầm peer/MITM |
| Correlation/authorization | Response thuộc đúng request/tenant | Đưa nhầm dữ liệu vào nghiệp vụ |
| Fault policy | Phân loại security/business Fault an toàn | Rò hoặc tin Fault không đáng tin |

### 12.2. Ví dụ hướng cấu hình client

~~~java
// Đoạn minh họa: dùng trong cấu hình có sẵn WSS4J,
// Crypto cho signing, key alias/password và trusted response.
// Chưa đủ để chạy độc lập khi thiếu những bean này.

Wss4jSecurityInterceptor clientSecurity =
        new Wss4jSecurityInterceptor();

clientSecurity.setSecurementActions("Timestamp Signature");
clientSecurity.setValidateResponse(true);
clientSecurity.setValidationActions("Timestamp Signature");
clientSecurity.setValidationSignatureCrypto(
        trustedPartnerResponseCrypto);
clientSecurity.setSkipValidationIfNoHeader(false);

webServiceTemplate.setInterceptors(
        new ClientInterceptor[] { clientSecurity });
~~~

`trustedPartnerResponseCrypto` và `webServiceTemplate` là biến cấu hình của dự án. Cần thêm `securementSignatureCrypto`, alias/key password hoặc callback handler theo version thực. Đoạn code **không tạo signature hợp lệ chỉ nhờ setSecurementActions**.

Cần test normal response, unsigned response và modeled Fault khi yêu cầu response security. Đừng mặc định `setValidateResponse(true)` bảo đảm mọi đường SOAP Fault được kiểm tra theo một cách: kiểm tra callbacks/behavior của stack thực.

### 12.3. WebServiceMessageCallback không phải WS-Security engine

`WebServiceMessageCallback`/`SoapActionCallback` có thể thêm SOAPAction, WS-Addressing và business headers **trước khi gửi**. Nhưng không nên tự tạo `wsse:Security` bằng nối XML.

Nếu request cần ký một header:

1. Tạo header đúng QName/namespace và contract.
2. Đảm bảo nó tồn tại trước signing.
3. Dùng WSS4J thực thi signing/encryption.
4. Test references bao phủ Header và Body như policy yêu cầu.
5. Không cho interceptor khác mutate signed elements sau ký.
6. Với MTOM, kiểm tra signed attachment profile và bytes trên HTTP MIME package thật.

### 12.4. SOAP Fault từ server cũng có thể không đáng tin

Client cần phân biệt:

- SOAP Fault do **server đã xác thực** trả về theo policy.
- HTTP error/redirect/proxy response không phải SOAP Fault.
- SOAP Fault có sender-supplied detail và signature không hợp lệ.
- TLS error khiến không có SOAP response.

Không tự “parse Fault trước rồi tin detail” nếu contract yêu cầu signed Fault. Nhưng cũng không giả định security Fault phát sinh trước khi server có thể ký phải đi theo cùng đường validation như business Fault — hãy kiểm thử profile cụ thể và dùng error mapping không lộ dữ liệu.

## 13. Thêm policy assertion sau cryptographic verification

Với operation nhạy cảm, bạn có thể cần kiểm tra **những điều kiện nghiệp vụ/security policy** ngoài việc WSS4J xử lý thành công các actions. Nhưng lớp này **không được tự xác minh signature** bằng cách tìm thẻ XML; nó chỉ nhận **kết quả đã được security stack tin cậy xác minh**.

### 13.1. Mô hình dữ liệu kết quả đã xác minh

~~~java
package com.example.orders.security;

public record VerifiedSoapSecurity(
        boolean requiredSecurityHeaderProcessed,
        boolean requiredTimestampValidated,
        boolean signatureCryptographicallyValid,
        boolean exactBusinessBodyCovered,
        boolean requiredHeadersCovered,
        boolean signerTrustedForPartner,
        boolean replayCheckPassed,
        String authenticatedPrincipal) {
}
~~~

**Cực kỳ quan trọng:** `VerifiedSoapSecurity` không phải một JAXB request DTO, không được deserialize từ SOAP Header/Body, không nhận booleans từ client và không lấy trực tiếp từ field `<IsVerified>true</IsVerified>`. Chỉ **adapter nội bộ tin cậy** sau khi WSS4J kiểm tra token, signature references, certificate trust, coverage và replay mới được tạo record này. Các booleans ở đây mang tính **mô tả điều kiện**, không phải công thức tự động chứng minh WSS4J đã xác minh tất cả chúng.

### 13.2. Fail-closed assertion cho operation bắt buộc

~~~java
package com.example.orders.security;

public final class RequiredSoapSecurityPolicy {

    public void requireForSubmitOrder(
            VerifiedSoapSecurity evidence) {

        if (evidence == null
                || !evidence.requiredSecurityHeaderProcessed()
                || !evidence.requiredTimestampValidated()
                || !evidence.signatureCryptographicallyValid()
                || !evidence.exactBusinessBodyCovered()
                || !evidence.requiredHeadersCovered()
                || !evidence.signerTrustedForPartner()
                || !evidence.replayCheckPassed()
                || evidence.authenticatedPrincipal() == null
                || evidence.authenticatedPrincipal().isBlank()) {

            throw new SecurityException(
                    "Required SOAP security not satisfied");
        }
    }
}
~~~

Ví dụ mang mục đích **làm rõ điều kiện bất biến**: nếu một điều kiện không thỏa, không thể gọi business method. Trong ứng dụng thực, WSS4J/interceptor là lớp kiểm tra mật mã bắt buộc, policy enforcement nhận một đối tượng evidence **không thể bị client giả mạo**, và authorization sau đó kiểm tra principal được phép thực hiện `SubmitOrder` cho order/tenant cụ thể.

Một lớp `SecurityException` thuần Java ở đây chỉ phục vụ mẫu; Spring-WS SOAP Fault mapping cho exception này phải được thiết kế theo contract, không trả raw stack trace cho client.

### 13.3. Không để “unknown” biến thành “true”

Nếu provider/interceptor không cho biết một cách đáng tin rằng Body đã được ký đúng references, **không** làm:

~~~java
// PHẢN VÍ DỤ:
boolean bodySigned =
        coverageResult == null ? true : coverageResult.bodySigned();
~~~

Đúng hướng: khi bằng chứng thiếu hoặc không xác định, **không xử lý protected operation**. Tương tự, nếu signer identity chưa được liên kết với partner trust policy, không suy ra quyền chỉ từ việc signature mathematically valid.

### 13.4. Unit tests của policy assertion

~~~java
package com.example.orders.security;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class RequiredSoapSecurityPolicyTest {

    private final RequiredSoapSecurityPolicy policy =
            new RequiredSoapSecurityPolicy();

    private VerifiedSoapSecurity validEvidence() {
        return new VerifiedSoapSecurity(
                true, true, true, true,
                true, true, true, "partner-a");
    }

    @Test
    void acceptsEvidenceWithEveryMandatoryCondition() {
        assertDoesNotThrow(
                () -> policy.requireForSubmitOrder(validEvidence()));
    }

    @Test
    void rejectsCompletelyMissingEvidence() {
        assertThrows(SecurityException.class,
                () -> policy.requireForSubmitOrder(null));
    }

    @Test
    void rejectsHeaderNotProcessed() {
        var invalid = new VerifiedSoapSecurity(
                false, true, true, true,
                true, true, true, "partner-a");
        assertThrows(SecurityException.class,
                () -> policy.requireForSubmitOrder(invalid));
    }

    @Test
    void rejectsSignatureThatDoesNotCoverBusinessBody() {
        var invalid = new VerifiedSoapSecurity(
                true, true, true, false,
                true, true, true, "partner-a");
        assertThrows(SecurityException.class,
                () -> policy.requireForSubmitOrder(invalid));
    }

    @Test
    void rejectsMissingReplayValidation() {
        var invalid = new VerifiedSoapSecurity(
                true, true, true, true,
                true, true, false, "partner-a");
        assertThrows(SecurityException.class,
                () -> policy.requireForSubmitOrder(invalid));
    }
}
~~~

**Giới hạn:** đây chỉ là unit test của **policy assertion sau verify**, không test WSS4J, không test cryptography và không chứng minh security evidence được tạo từ đúng SOAP nodes. Integration tests ở mục tiếp theo là bắt buộc để tránh nhầm một test boolean thành test an ninh thực.

## 14. Test thiếu header và các trường hợp tấn công đường đi vòng

Một bộ kiểm thử phải chứng minh **hai điều cùng lúc**:

1. Request không thỏa security policy bị từ chối.
2. Business logic có side effects **không chạy**.

Nếu chỉ assert có SOAP Fault nhưng business service đã ghi database trước đó, hệ thống vẫn nguy hiểm.

### 14.1. Ma trận negative tests tối thiểu

| Trường hợp | Đầu vào | Mong đợi |
|---|---|---|
| Header vắng hoàn toàn | SOAP Body hợp lệ, không có `wsse:Security` | Reject; business calls = 0 |
| Header rỗng | `<wsse:Security/>` | Reject; business calls = 0 |
| Chỉ Timestamp | Có thời gian, không Signature | Reject; business calls = 0 |
| Chỉ Signature | Thiếu Timestamp bắt buộc | Reject |
| Signature giả | `SignatureValue` không hợp lệ | Reject |
| Signature từ key không được trust | Chữ ký mathematically valid, certificate không thuộc trust policy | Reject |
| Signature đúng nhưng ký sai element | Header phụ được ký, Body chưa ký | Reject theo coverage |
| Duplicate `wsu:Id` / signed-node confusion | Signed part khác Body được sử dụng | Reject hoặc parser/security library ngăn |
| Security header sai SOAP actor/role | Header không hướng tới receiver | Không tính là protected; Reject |
| Header namespace spoofing | Local name “Security” nhưng sai namespace | Không tính là WS-Security; Reject |
| Timestamp hết hạn | Created/Expires ngoài policy | Reject |
| Timestamp quá xa tương lai | Created không nằm trong clock-skew | Reject |
| Replay nguyên SOAP message | Cùng signature/nonce/request ID phát lại | Reject/deduplicate theo policy |
| UsernameToken thiếu password/nonce khi bắt buộc | Token không đạt profile | Reject |
| SOAP Body bị sửa sau khi ký | Digest mismatch | Reject |
| Header có `mustUnderstand` nhưng thiếu actions | “Hiểu” header không đủ | Reject |
| Action order/profile không tương thích | WS-SecurityPolicy yêu cầu khác | Reject |
| SOAP version sai | SOAP 1.2 tới binding chỉ hỗ trợ 1.1 | Protocol rejection; business calls = 0 |
| URL alias chưa bảo vệ | Protected operation qua ingress khác | Cũng phải reject |
| Fault/error exception branch | Có lỗi xảy ra trước hoặc trong verify | Không fallback sang business |
| Chỉ có mTLS, thiếu WS-Security | Chứng chỉ client được trust | Reject nếu policy yêu cầu message signature |

**Không tạo test ký số bằng cách đặt một thẻ `ds:Signature` rỗng rồi coi “Signature present” là valid signature.** Phải tạo signed SOAP messages **thật** bằng certificate/key test và security stack tương thích để kiểm tra meaningful negative cases.

### 14.2. SOAP request không có Security Header

Đây là fixture SOAP 1.1 hợp lệ ở mức Envelope/Body, **cố ý thiếu WS-Security**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
  <soapenv:Header/>
  <soapenv:Body>
    <ord:SubmitOrderRequest>
      <ord:orderId>ORD-1001</ord:orderId>
      <ord:amount>100.00</ord:amount>
    </ord:SubmitOrderRequest>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Expected outcome khi `SubmitOrder` được bảo vệ:

~~~text
SOAP parser: may parse successfully
Endpoint mapping: may identify SubmitOrder
WS-Security policy: DENIED (required header/actions absent)
Business service: NOT INVOKED
Database/payment/event side effects: NONE
SOAP Fault / HTTP denial: follows contract, no secrets
~~~

**Đừng sửa SOAP Body thành XML sai schema để tạo negative security test**; khi đó request có thể bị từ chối do parser/XSD trước khi chạm security gate và test **không chứng minh** missing-header enforcement. Một test tốt giữ Body hợp lệ, chỉ thay trạng thái security.

### 14.3. Test bằng MockWebServiceClient

Spring-WS test support có `MockWebServiceClient` để kiểm tra endpoint dispatch trong application context. Phác thảo với operation đã có JAXB/endpoint thật:

~~~java
@SpringBootTest
class MissingSecurityHeaderIntegrationTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    OrderServiceSpy orderServiceSpy; // Test helper do dự án tạo.

    @Test
    void missingSecurityHeaderNeverInvokesBusiness() {
        MockWebServiceClient client =
                MockWebServiceClient.createClient(context);

        Source body = new StringSource("""
            <ord:SubmitOrderRequest
                xmlns:ord="urn:example:orders:v1">
              <ord:orderId>ORD-1001</ord:orderId>
              <ord:amount>100.00</ord:amount>
            </ord:SubmitOrderRequest>
            """);

        client.sendRequest(withPayload(body))
              .andExpect(messageContext -> {
                  var response = messageContext.getResponse();
                  assertNotNull(response);
                  assertInstanceOf(SoapMessage.class, response);
                  assertTrue(((SoapMessage) response)
                           .getSoapBody().hasFault());
              });

        assertEquals(0, orderServiceSpy.submitCalls());
    }
}
~~~

Đây là **mẫu integration test** cần imports JUnit, Spring Test, `spring-ws-test` và static import `RequestCreators.withPayload`; `OrderServiceSpy` là helper instrumented business service của dự án, không phải class Spring có sẵn. Cần xác nhận `ResponseMatcher` callback API trên version đang dùng; nếu parser trả lỗi **trước khi tạo response SOAP**, test có thể phải assert exception/HTTP error thay vì `hasFault()`, nhưng **business calls = 0** vẫn là điều kiện bắt buộc.

Không dùng một mock endpoint bỏ qua Spring security configuration để thay thế test này. Và `MockWebServiceClient` không kiểm tra HTTPS/mTLS/HTTP gateway; cần thêm test HTTP thật.

### 14.4. Test signature coverage trên message thật

Tạo ba fixtures bằng tool WSS4J/stack đối tác trong môi trường test:

1. **Hợp lệ:** Timestamp + Signature ký đúng SOAP Body và các required headers.
2. **Chữ ký hợp lệ nhưng sai coverage:** dùng key được trust ký một optional Header, không ký Body.
3. **Body tampered:** ký request đúng, sau đó đổi `orderId` hoặc `amount` trong Body được ký.

Service phải chỉ cho trường hợp (1) tới nghiệp vụ. Trường hợp (2) là kiểm thử cực kỳ quan trọng vì có thể bắt lỗi “chỉ require signature action, không kiểm required signed parts”. Trường hợp (3) xác minh integrity thực.

Dùng certificate/key **test**, không dùng private keys production trong fixtures. Không xem “signature cryptographically valid” là đồng nghĩa “signer được phép thao tác mọi resource”.

### 14.5. Test qua HTTPS và các mappings thật

Ngoài mock tests, chạy integration test với `MessageDispatcherServlet`, HTTP sender và full Spring application context:

- Gửi SOAP tới URL thực, không phải chỉ gọi endpoint method trực tiếp.
- Kiểm tra response/Fault và **không có side effect** với no-header request.
- Gửi qua các public/gateway/legacy paths được cho phép; xác nhận không có unprotected alias.
- Kiểm tra HTTPS certificate chain/hostname/mTLS theo policy.
- Chứng minh SOAP Body/WS-Security version đúng contract.
- Thử request không well-formed, oversized payload/MTOM để chặn trước business.
- Thử SOAP 1.1 và 1.2 nếu hai versions được hỗ trợ.
- Kiểm tra client cũng verify signed normal response và Fault theo profile.

**Một phép thử pass trên một URL không chứng minh mọi URL/EndpointMapping đã được bao phủ.**

## 15. Quan sát vận hành mà không làm suy yếu bảo mật

### 15.1. Logging đúng mức

Các trường metadata có thể hữu ích:

~~~text
service=orders
operation=SUBMIT_ORDER
security_state=REJECTED
reason_code=SIGNATURE_REQUIRED
soap_version=1.1
business_invoked=false
~~~

Không log raw `wsse:Security`, UsernameToken password/digest, `SignatureValue`, private key, full SOAP Body, MTOM binary, decrypted content hoặc certificate details vượt nhu cầu. Một phần exception string có thể chứa XML caller-supplied; không dùng nguyên như metric label.

### 15.2. Metrics cần có để phát hiện bypass

| Metric/kết quả | Điều đo |
|---|---|
| `soap_security_missing_header_total` | Requests tới protected routes thiếu header |
| `soap_security_validation_failed_total` | Lỗi signature/token/timestamp theo reason code giới hạn |
| `soap_security_coverage_denied_total` | Signature có nhưng không phủ required parts |
| `soap_security_replay_denied_total` | Replay/duplicate bị từ chối theo policy |
| `soap_business_invoked_without_security_total` | **Bắt buộc luôn bằng 0** cho protected operations |
| `soap_security_unknown_route_total` | Các SOAP requests không map đúng operation/security config |
| `soap_security_config_error_total` | Lỗi Crypto, truststore, provider/interceptor wiring |

Metric names là ví dụ thiết kế, không phải metric Spring-WS tự phát hành. Cardinality phải thấp: operation code, outcome, policy version; tránh labels là SOAPAction tùy ý, user ID, URL Callback hoặc raw faultstring.

### 15.3. Startup và deployment gates

- Không khởi động protected service nếu thiếu WSS4J interceptor hoặc verification Crypto bắt buộc.
- Không fallback sang permissive trust manager khi keystore/truststore load lỗi.
- Không tự tắt validation trong môi trường production vì đối tác tạm ngừng ký.
- Không để feature flags cấp quyền anonymous cho operation có side effect mà không có change review.
- Có alert cho tăng đột biến số request thiếu Security Header và tỷ lệ security faults.
- Có inventory các endpoint mappings và kiểm thử request không ký qua mọi entrypoint.
- Khi rotate signer certificates, kiểm thử trust overlap có kiểm soát, không “allow all” trong cutover.

### 15.4. Cách kiểm tra một incident

Khi log xuất hiện nhiều request thiếu `wsse:Security`:

1. Xác nhận request thực sự tới protected operation và parser không bị bypass.
2. Kiểm tra request bị từ chối **trước business side effect**.
3. Đối chiếu policy version, mapping, interceptor wiring và gateway path.
4. Kiểm tra client upstream có mất signing interceptor vì config/feature flag hay không.
5. Thu thập **metadata đã được loại bí mật**, không lưu payload/chữ ký thô đại trà.
6. Từ chối mở “bypass tạm thời” nếu không có phương án bảo mật thay thế được phê duyệt và kiểm thử.
7. Sau sửa lỗi, chạy lại no-header, signature-missing, unsigned-Body và tampered-message tests.

## 16. Case study: endpoint mới bỏ qua security header bắt buộc

### 16.1. Bối cảnh

Một hệ thống đơn hàng doanh nghiệp công bố hai SOAP operations:

- `GetOrder`: lấy đơn đã được cấp quyền.
- `CancelOrder`: hủy đơn, có side effect và bắt buộc Timestamp + Signature bảo vệ SOAP Body.

Ứng dụng đã có WSS4J trên endpoint mapping chính và một test signed request thành công. Một đội khác bổ sung URL `/soap/legacy-orders` để hỗ trợ client cũ, nhưng quên đăng ký security interceptor tại mapping mới.

Sau khi deploy:

- Request signed qua `/soap/orders` vẫn thành công.
- Request thiếu `wsse:Security` qua `/soap/legacy-orders` vẫn vào `CancelOrderEndpoint`.
- Business service thực hiện hủy đơn.
- Log HTTP chỉ cho thấy response bình thường; không có counter security-denied trên route legacy.

**Root cause không phải thuật toán RSA/HMAC yếu.** Đó là **coverage gap**: security verifier không chạy trên đường yêu cầu bắt buộc.

### 16.2. Những giả định sai

| Giả định | Vì sao sai |
|---|---|
| “WSS4J đã có một bean trong Spring context” | Bean tồn tại không chứng minh được gắn với mọi mapping |
| “Client chính luôn ký SOAP” | Caller độc hại hoặc client lỗi có thể gửi no-header |
| “SOAPAction đúng nên request an toàn” | Action là routing metadata, không phải signature |
| “`mustUnderstand` buộc server xử lý security” | Nếu header vắng, không có gì để must-understand |
| “Bên ngoài đã có mTLS” | mTLS không tự yêu cầu WS-Security Body signature |
| “Chỉ legacy client được gọi URL đó” | Nếu gateway route/direct access không enforce, attacker vẫn có thể thử |
| “Có business authorization nên đủ” | Authorization không thay integrity/replay protections mà operation bắt buộc |

### 16.3. Cách khoanh vùng

1. **Dừng tác động:** chặn hoặc hạn chế legacy route cho tới khi security policy được gắn đúng; không tắt WSS4J tuyến chính.
2. **Inventory:** liệt kê tất cả URL/mappings đến cùng business service và bean/chain tương ứng.
3. **Evidence:** gửi no-header request với SOAP Body hợp lệ tới từng route; xác nhận business call counter.
4. **Thử coverage:** không chỉ thêm “header exists”, mà test missing Timestamp, missing Signature, wrong signer và unsigned Body.
5. **So policy:** cùng operation phải có cùng required actions/coverage qua các public entrypoints, trừ ngoại lệ đã được phê duyệt và tách service rõ.
6. **Fix cấu hình:** đăng ký WSS4J đúng scope, fail closed nếu trust Crypto thiếu hoặc verification lỗi.
7. **Defense-in-depth:** business service kiểm tra principal/authorization và không sử dụng client-declared identity chưa verify.
8. **Regression:** chạy qua gateway/proxy, SOAP 1.1/1.2 và các endpoint mappings thật.
9. **Incident response:** đối chiếu audit/side effects, xác định request đã được xử lý mà thiếu security theo quy trình tổ chức.

### 16.4. Hành vi sau sửa cần đạt

~~~mermaid
flowchart TD
    A["SOAP request tới bất kỳ route CancelOrder nào"] --> P["Đúng protected operation policy"]
    P --> H{"Security header/actions required có và valid?"}
    H -->|Không| R["Reject, no side effect"]
    H -->|Có| C{"Signature covers exact Body, trusted signer?"}
    C -->|Không| R
    C -->|Có| T{"Timestamp, replay, authorization pass?"}
    T -->|Không| R
    T -->|Có| B["Cancel order exactly under business policy"]
~~~

Kết quả nghiệm thu phải có cả **positive test** (signed request đúng vẫn hoạt động) và **negative tests** (no-header/unsigned Body/expired Timestamp/cross-tenant request không thể hủy đơn).

### 16.5. Khi nào được tạo ngoại lệ bảo mật?

Trong một số hệ thống, có public health endpoint hoặc legacy route chuyển tiếp qua gateway đã xác thực. Ngoại lệ chỉ có thể chấp nhận khi:

- Được định nghĩa thành **một security profile riêng, explicit**.
- Được tách khỏi operation nhạy cảm và không có business side effect ngoài phạm vi được phép.
- Trust boundary/certificates/proxy headers được kiểm soát và không có đường vòng.
- Có owner, expiry/migration plan và audit.
- Có negative tests chứng minh không thể dùng ngoại lệ để gọi protected operations.

Không viết `if (legacyClient) skipValidation()` dựa vào một SOAP Header hoặc User-Agent do caller gửi.

## 17. Bài tập thực hành kèm đáp án

### Bài 1 — Security Header hoàn toàn vắng

Một endpoint `CancelOrder` yêu cầu Timestamp và chữ ký. Request không chứa `wsse:Security` nhưng SOAP Body hợp lệ. Có thể để WSS4J bỏ qua rồi cho business service xử lý không?

**Đáp án:** Không. Thiếu header đồng nghĩa thiếu actions bắt buộc. Cấu hình phải fail closed và test business call counter bằng 0. Kiểm tra cả `skipValidationIfNoHeader` và actual interceptor coverage theo phiên bản.

### Bài 2 — Header rỗng nhưng mustUnderstand=1

SOAP Header có `<wsse:Security soapenv:mustUnderstand="1"/>`. Đã đáp ứng policy chưa?

**Đáp án:** Chưa. `mustUnderstand` buộc SOAP node xử lý header theo SOAP processing model, không tạo Timestamp, Signature, trust hay signed coverage. Header rỗng phải bị từ chối khi policy yêu cầu actions.

### Bài 3 — Signature hợp lệ ký header phụ

Request ký hợp lệ phần tử `ClientNote` nhưng không ký SOAP Body, trong khi operation cần chữ ký Body. WSS4J có thể thấy signature cryptographically valid. Service có nên chấp nhận không?

**Đáp án:** Không. Cần enforce **required signed parts**, đúng Body mà endpoint sử dụng, và chống signed-node confusion. Có signature action không đủ.

### Bài 4 — Signed Body nhưng unsigned WS-Addressing ReplyTo

Request Body đã ký, nhưng `wsa:ReplyTo` do caller khai báo chưa ký và trỏ đến endpoint lạ. Server có thể gửi business response đến đó không?

**Đáp án:** Không nếu chưa authorize. Nếu policy yêu cầu signed WS-A headers, request còn thiếu integrity protection cho ReplyTo. Dù header đã ký, destination vẫn cần allowlist theo trusted partner/tenant/operation và egress controls.

### Bài 5 — Timeout không phải replay proof

Timestamp còn hợp lệ trong 5 phút, attacker gửi lại cùng một message trong phút thứ nhất. Việc kiểm `Expires` có tự chặn replay không?

**Đáp án:** Không. Cần replay protection/nonce/MessageID theo policy và business idempotency để tránh side effects lặp.

### Bài 6 — mTLS thay chữ ký SOAP?

Gateway đã xác minh certificate client. Endpoint có thể bỏ Signature action mà contract bắt buộc không?

**Đáp án:** Không. mTLS bảo vệ hop và client authentication theo trust policy; WS-Security signature bảo vệ message parts theo chính sách. Muốn đổi profile phải có thay đổi hợp đồng/chấp thuận, không tạo fallback ngầm.

### Bài 7 — Interceptor bị thiếu ở một mapping

Cùng `SubmitOrderRequest` được nhận qua `/soap/orders` và `/legacy/orders`. WSS4J chỉ gắn tuyến đầu. Test nào quan trọng nhất?

**Đáp án:** Gửi Body **hợp lệ nhưng không có Security Header** qua **cả hai routes** và assert bị từ chối, business service không chạy. Thêm tests valid signed/tampered/unsigned Body cho từng route.

### Bài 8 — UsernameToken có tên người dùng

Một header `UsernameToken` chứa `Username=partner-a` nhưng không có password/nonce mà policy yêu cầu. Có thể tạo principal `partner-a` chỉ từ tên không?

**Đáp án:** Không. Chỉ cấp principal sau khi WSS4J/token validator xác thực credential và các replay requirements; dữ liệu do sender khai báo không tự đáng tin.

### Bài 9 — Header sai role

Một `wsse:Security` được nhắm tới intermediary role, còn ultimate receiver cần security header của chính nó. Đếm header kia như một dấu hiệu protected có an toàn không?

**Đáp án:** Không. Phải tuân thủ actor/role semantics và policy của node nhận; header không dành cho nó không thay required security actions của nó.

### Bài 10 — SOAP Fault trước verify

Request không well-formed hoặc thiếu required security tạo lỗi sớm; service cố gửi detailed Fault tới `wsa:FaultTo` chưa được xác thực. Có vấn đề gì?

**Đáp án:** Có nguy cơ lộ dữ liệu/SSRF. Không dùng FaultTo chưa authorize làm outbound destination; xử lý lỗi tại tầng phù hợp và chỉ trả thông tin đã được phép công bố.

### Bài 11 — Client ký request nhưng không kiểm response

`WebServiceTemplate` gắn WSS4J securement cho outgoing message, nhưng không validate incoming signed response. Có đáp ứng “response bắt buộc được ký” không?

**Đáp án:** Chưa. Phải cấu hình inbound response validation và signed coverage theo policy, test unsigned/tampered response bị từ chối trước khi business dùng dữ liệu.

### Bài 12 — Test boolean policy có đủ?

Một unit test tạo `VerifiedSoapSecurity(true, true, ...)` rồi assert policy pass. Có chứng minh SOAP request thật an toàn không?

**Đáp án:** Không. Phải test rằng **WSS4J thực** tạo evidence sau cryptographic/reference/trust validation và không có đường nào client tự tạo booleans; thêm HTTP/SOAP integration tests.

### Bài 13 — Header thiếu khi provider lỗi

Do keystore/trust configuration lỗi, security interceptor không khởi tạo. Có thể tạm bỏ nó khỏi chain để SOAP service vẫn chạy không?

**Đáp án:** Không với protected operations. Phải fail startup/disable protected route cho đến khi trust policy hoạt động; không chuyển sang insecure fallback.

### Bài 14 — SOAP 1.2 và mustUnderstand

Một test chỉ kiểm `soapenv:mustUnderstand="1"` của SOAP 1.1. Khi thêm SOAP 1.2, có thể dùng y hệt Envelope namespace không?

**Đáp án:** Không. SOAP 1.2 có Envelope namespace/processing model và giá trị boolean riêng. Test phải dùng message factory đúng version và kiểm action policy/role semantics trên wire thực.

## 18. Checklist triển khai security bắt buộc, không bypass

### 18.1. Định nghĩa policy

- [ ] Mỗi operation xác định rõ có bắt buộc `wsse:Security` hay không.
- [ ] Có danh sách **required actions** (Timestamp, Signature, UsernameToken, Encryption...) theo contract.
- [ ] Quy định **signed parts** chính xác: SOAP Body và required SOAP Headers.
- [ ] Quy định encrypted parts/attachments theo WS-SecurityPolicy.
- [ ] Trust/certificate/principal mapping và key rotation được quản lý.
- [ ] Có timestamp freshness, nonce/replay và idempotency cho operations có side effects.
- [ ] Phân biệt request, normal response, modeled Fault và security/protocol Fault policies.
- [ ] Xác thực principal và authorization resource tách khỏi XSD validation.

### 18.2. Spring-WS/WSS4J enforcement

- [ ] Security interceptor được tạo thành công với Crypto/trust material hợp lệ.
- [ ] `validateRequest` bật cho protected requests.
- [ ] Không skip validation khi Security Header vắng nếu operation yêu cầu.
- [ ] Không chấp nhận Security Header rỗng hoặc thiếu required action.
- [ ] Không dùng `mustUnderstand` thay signature/token validation.
- [ ] Có policy cho SOAP actor/role và WS-A Headers nếu dùng intermediaries.
- [ ] Kiểm tra exact signed SOAP Body/Headers, ID uniqueness và signature wrapping.
- [ ] Không nuốt WSS4J exceptions hoặc fallback sang anonymous guest mode.
- [ ] Interceptor được gắn vào **mọi protected EndpointMapping** và ingress.
- [ ] Không để aliases/legacy routes/JMS adapters bypass business authorization.
- [ ] Không tạo business side effect trước khi verify/security policy pass.
- [ ] Không đặt raw XML logging interceptor trước security rồi ghi dữ liệu nhạy cảm.

### 18.3. SOAP client và transport

- [ ] Outgoing client securement đúng WSDL/WS-SecurityPolicy.
- [ ] Client inbound response validation được bật và test với unsigned/tampered responses.
- [ ] SOAPAction/WS-Addressing headers được tạo đúng trước signing khi required.
- [ ] HTTPS certificate chain/hostname verification và mTLS (nếu cần) được kiểm tra.
- [ ] TLS/mTLS không được coi là thay thế chữ ký WS-Security bắt buộc.
- [ ] MTOM/attachment integrity, MIME size limits và memory/streaming được test.
- [ ] Credentials, certificate/private keys và signed payload không được log.
- [ ] SOAP Fault mapping không trả raw exception và không gửi tới `FaultTo` chưa được authorize.

### 18.4. Kiểm thử âm tính

- [ ] No-header request với Body hợp lệ → reject, **business calls = 0**.
- [ ] Empty header và chỉ Timestamp/Signature → reject khi thiếu required action.
- [ ] Invalid signature, wrong signer, expired Timestamp và replay → reject.
- [ ] Signature hợp lệ nhưng chưa ký Body/required Headers → reject.
- [ ] Duplicate IDs, XML Signature Wrapping và namespace spoofing → reject.
- [ ] Security Header sai actor/role → không coi là đạt policy của receiver.
- [ ] SOAP 1.1/1.2 và routing theo PayloadRoot/SOAPAction/WS-A Action đều được test.
- [ ] Mọi HTTP URL aliases/ingress paths được kiểm tra.
- [ ] Lỗi parser/message factory không vào business và không external egress.
- [ ] SOAP Fault/exception paths không lộ PII, token hay KeyInfo.
- [ ] Response và Fault có security theo profile; client kiểm tra đúng.
- [ ] Test bằng **signature/certificates thật của môi trường test**, không chỉ header giả.
- [ ] Sau nâng JDK/Spring-WS/WSS4J, test lại interceptor wiring và defaults.

### 18.5. Vận hành và phát hành

- [ ] CI có regression gate cho missing-header và unsigned-Body tests.
- [ ] Startup fail closed nếu WSS4J/Crypto/security policy không sẵn sàng.
- [ ] Monitoring theo reason codes có cardinality thấp, không chứa raw XML.
- [ ] Alerts khi các security failures tăng bất thường hoặc route không có policy.
- [ ] Có chứng cứ từ test rằng protected business operation **không thể chạy khi thiếu xác minh**.
- [ ] Có kế hoạch migration/rotation keys và profile thay đổi được phê duyệt.
- [ ] Dữ liệu nội bộ và audit logs được phân quyền, retention và redaction phù hợp.
- [ ] Không nhầm hoàn thành bước viết nội dung với chứng nhận production security readiness.

**Ghi nhớ:** yêu cầu WS-Security bắt buộc là một **invariant của toàn bộ đường xử lý SOAP**, không phải điều kiện `if(header != null)`. Với Spring Web Services, dùng WSS4J để xác minh token/chữ ký, cấu hình không bỏ qua khi header thiếu, kiểm tra signed coverage và certificate trust, áp dụng timestamp/replay/authorization, rồi chứng minh bằng **negative tests trên mọi endpoint mapping** rằng không có request chưa đạt policy nào thực thi nghiệp vụ. SOAP Header, mustUnderstand, TLS và XSD đều có vai trò riêng; không thành phần nào tự thay thế enforcement WS-Security end-to-end.
