# Client interceptor và bảo mật

## Mục tiêu

Sau bài học này, bạn có thể:

- Xác định vị trí của client interceptor trong luồng gọi SOAP từ Spring Integration.
- Phân biệt interceptor của Spring Web Services với interceptor HTTP và interceptor của MessageChannel.
- Cấu hình interceptor để bổ sung header, ghi nhận thông tin vận hành và áp dụng WS-Security.
- Chọn đúng lớp bảo vệ cho SOAP header, HTTP transport và kết nối TLS.
- Xử lý SOAP Fault, lỗi xác thực và lỗi kết nối mà không làm lộ thông tin nhạy cảm.

Trong module **SPRING_INTEGRATION_ADAPTERS**, outbound adapter và gateway đưa message từ hệ thống nội bộ sang hệ thống ngoài. Với Web Services, phần lớn ví dụ là SOAP: payload được marshal thành XML, gửi qua HTTP hoặc HTTPS, sau đó response được unmarshal thành object. Client interceptor cho phép áp dụng các hành vi dùng chung quanh lần gọi SOAP mà không đưa logic bảo mật và quan sát vào từng flow nghiệp vụ.

Module còn bao gồm adapter file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu. Mỗi connector có cơ chế xác thực, bảo vệ transport và quản lý kết nối riêng. **ClientInterceptor** trong bài này dành cho SOAP client của Spring Web Services; không áp dụng nó cho mọi adapter chỉ vì các adapter đều trao đổi message với hệ thống ngoài.

## 1. Interceptor nằm ở đâu trong luồng tích hợp?

Một luồng outbound SOAP thường có các bước sau:

1. Message đi vào request channel của Spring Integration.
2. Outbound gateway lấy payload và chuyển thành SOAP request bằng marshaller.
3. WebServiceTemplate chạy chuỗi ClientInterceptor.
4. WebServiceMessageSender gửi SOAP envelope qua HTTP hoặc HTTPS.
5. Response hoặc SOAP Fault được nhận về; interceptor xử lý kết quả.
6. Gateway chuyển response thành payload và phát ra reply channel. Lỗi được chuyển thành exception để flow xử lý.

Sơ đồ dưới đây thể hiện vị trí của interceptor:

~~~mermaid
sequenceDiagram
    participant Flow as Spring Integration flow
    participant Gateway as Web Services outbound gateway
    participant Template as WebServiceTemplate
    participant Interceptor as ClientInterceptor chain
    participant Sender as WebServiceMessageSender
    participant Partner as SOAP service

    Flow->>Gateway: Message request
    Gateway->>Template: SOAP payload
    Template->>Interceptor: handleRequest
    Template->>Sender: Gửi SOAP request
    Sender->>Partner: HTTPS / SOAP
    Partner-->>Sender: SOAP response hoặc Fault
    Sender-->>Template: WebServiceMessage
    alt Response thành công
        Template->>Interceptor: handleResponse
    else SOAP Fault
        Template->>Interceptor: handleFault
    end
    Template->>Interceptor: afterCompletion
    Template-->>Gateway: Kết quả hoặc exception
    Gateway-->>Flow: Reply hoặc error flow
~~~

Interceptor thuộc client SOAP của Spring Web Services. Nó không thay thế MessageChannel, không quyết định định tuyến message giữa các channel và cũng không phải nơi triển khai quy tắc nghiệp vụ của ứng dụng.

## 2. Vòng đời của ClientInterceptor

Spring Web Services định nghĩa contract **org.springframework.ws.client.support.interceptor.ClientInterceptor**. Một interceptor có thể triển khai bốn callback:

| Callback | Thời điểm | Mục đích phù hợp |
|---|---|---|
| handleRequest | Trước khi gửi request | Thêm SOAP header, kiểm tra điều kiện gọi, ghi nhận metadata |
| handleResponse | Khi nhận response thành công | Kiểm tra hoặc ghi nhận response |
| handleFault | Khi nhận SOAP Fault | Ghi nhận fault và bổ sung thông tin chẩn đoán |
| afterCompletion | Khi lần gọi hoàn tất | Dọn tài nguyên hoặc ghi nhận kết quả cuối cùng |

Các callback request chạy theo thứ tự interceptor được đăng ký. Callback response, fault và afterCompletion chạy theo thứ tự ngược lại. Điều này cho phép các interceptor lồng nhau theo cách tương tự một chuỗi xử lý.

Hai lưu ý quan trọng:

- Giá trị trả về **false** từ handleRequest dừng quá trình xử lý tiếp theo và ngăn request được gửi. Chỉ dùng cách này khi chủ đích là từ chối hoặc short-circuit lời gọi.
- Không bắt rồi nuốt exception bảo mật. Nếu xác minh chữ ký, chứng thư hoặc token thất bại, lời gọi cần thất bại để flow phía trên có thể xử lý đúng.

Interceptor thường được đăng ký dưới dạng Spring bean dùng chung. Vì nhiều message có thể gọi đồng thời, không lưu trạng thái riêng của một request vào field có thể thay đổi trong interceptor singleton. Nếu cần đo thời gian hoặc tương quan request, hãy dùng cơ chế context an toàn cho từng lần gọi và bảo đảm dữ liệu được dọn ở afterCompletion.

### Ví dụ: interceptor ghi nhận vòng đời lời gọi

Ví dụ sau ghi nhận loại kết quả và exception, không đọc hoặc ghi toàn bộ SOAP envelope:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ws.client.WebServiceClientException;
import org.springframework.ws.client.support.interceptor.ClientInterceptor;
import org.springframework.ws.context.MessageContext;

public final class SoapAuditInterceptor implements ClientInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(SoapAuditInterceptor.class);

    @Override
    public boolean handleRequest(MessageContext messageContext)
            throws WebServiceClientException {
        log.debug("Preparing outbound SOAP request");
        return true;
    }

    @Override
    public boolean handleResponse(MessageContext messageContext)
            throws WebServiceClientException {
        log.debug("Received outbound SOAP response");
        return true;
    }

    @Override
    public boolean handleFault(MessageContext messageContext)
            throws WebServiceClientException {
        log.warn("Received SOAP Fault from partner");
        return true;
    }

    @Override
    public void afterCompletion(
            MessageContext messageContext, Exception exception)
            throws WebServiceClientException {
        if (exception != null) {
            log.warn("SOAP invocation failed: {}",
                    exception.getClass().getSimpleName());
        }
    }
}
~~~

Trong môi trường thực tế, log nên có correlation ID, tên đối tác, operation, thời gian xử lý và loại lỗi. Hãy lấy correlation ID từ context được thiết kế để truyền qua flow; đừng tạo một field mutable trong interceptor để giữ ID giữa các request. Không ghi password, access token, UsernameToken, private key, nội dung SOAP có dữ liệu cá nhân hoặc dữ liệu thanh toán.

### Ví dụ: thêm SOAP header

Khi hợp đồng của đối tác yêu cầu một header ứng dụng, interceptor có thể thêm header vào SOAP message:

~~~java
import java.util.UUID;
import javax.xml.namespace.QName;
import org.springframework.ws.client.WebServiceClientException;
import org.springframework.ws.client.support.interceptor.ClientInterceptor;
import org.springframework.ws.context.MessageContext;
import org.springframework.ws.soap.SoapMessage;

public final class PartnerHeaderInterceptor implements ClientInterceptor {

    private static final QName REQUEST_ID =
            new QName("urn:example:integration", "RequestId", "int");

    @Override
    public boolean handleRequest(MessageContext messageContext)
            throws WebServiceClientException {
        if (messageContext.getRequest() instanceof SoapMessage) {
            SoapMessage soapMessage = (SoapMessage) messageContext.getRequest();
            soapMessage.getSoapHeader()
                    .addHeaderElement(REQUEST_ID)
                    .setText(UUID.randomUUID().toString());
        }
        return true;
    }

    @Override
    public boolean handleResponse(MessageContext messageContext)
            throws WebServiceClientException {
        return true;
    }

    @Override
    public boolean handleFault(MessageContext messageContext)
            throws WebServiceClientException {
        return true;
    }

    @Override
    public void afterCompletion(
            MessageContext messageContext, Exception exception) {
        // Không giữ dữ liệu request trong instance interceptor.
    }
}
~~~

Tên header, namespace, kiểu dữ liệu và quy tắc tạo giá trị phải theo hợp đồng của đối tác. Một header tự đặt không tự động trở thành cơ chế xác thực. Nếu đối tác yêu cầu header phải được ký số, cần cấu hình WS-Security để bảo vệ header đó theo đúng chính sách.

## 3. Phân biệt các lớp bảo mật

Một lời gọi SOAP có thể đi qua nhiều lớp bảo vệ. Chọn đúng lớp dựa trên nơi thông tin được truyền và yêu cầu trong hợp đồng tích hợp.

| Lớp | Cơ chế thường gặp | Bảo vệ điều gì? |
|---|---|---|
| SOAP message | WS-Security UsernameToken, Timestamp, Signature, Encryption | Danh tính, tính toàn vẹn và/hoặc tính bí mật ở cấp message |
| HTTP transport | HTTP Basic, Bearer token, API key trong header HTTP | Quyền truy cập ở lớp HTTP |
| TLS | HTTPS, truststore, client certificate (mTLS) | Kênh truyền, xác thực máy chủ và có thể xác thực client |
| Spring Integration message | MessageChannel, header và channel security | Quyền gửi/nhận message trong ứng dụng |

Các cơ chế này không thay thế lẫn nhau:

- HTTPS mã hóa đường truyền giữa hai đầu TLS, nhưng không tự tạo chữ ký XML có thể được xác minh sau khi message đi qua gateway trung gian.
- WS-Security bảo vệ SOAP message theo chính sách đã chọn, nhưng không thay thế việc xác minh chứng thư máy chủ khi kết nối HTTPS.
- HTTP Bearer token nằm trong HTTP Authorization header; WS-Security UsernameToken nằm trong SOAP header. Gửi một loại không có nghĩa là đã đáp ứng loại còn lại.
- Channel interceptor của Spring Integration hoạt động trên message nội bộ. Nó không thay thế ClientInterceptor của Spring Web Services.

Đừng nhầm **org.springframework.http.client.ClientHttpRequestInterceptor** với **org.springframework.ws.client.support.interceptor.ClientInterceptor**. Loại thứ nhất thuộc HTTP client của Spring, thường dùng với RestTemplate; loại thứ hai làm việc với SOAP MessageContext và được đăng ký trên WebServiceTemplate. Chọn interface theo client thực sự gửi request.

Đối chiếu hợp đồng của đối tác để biết họ yêu cầu cơ chế nào, header nào phải được ký, thành phần nào phải mã hóa, thời hạn timestamp và chứng thư nào được tin cậy.

## 4. Cấu hình WebServiceTemplate và interceptor

**WebServiceTemplate** là client trung tâm của Spring Web Services. Interceptor phải được gắn vào đúng template mà outbound gateway hoặc thành phần gọi SOAP thực sự sử dụng. Nếu ứng dụng cấu hình một template nhưng gateway tự tạo và dùng template khác, interceptor sẽ không chạy.

Ví dụ cấu hình một template dành riêng cho đối tác:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.client.support.interceptor.ClientInterceptor;
import org.springframework.ws.transport.WebServiceMessageSender;

@Configuration
public class PartnerSoapClientConfiguration {

    @Bean
    WebServiceTemplate partnerWebServiceTemplate(
            Jaxb2Marshaller partnerMarshaller,
            @Qualifier("partnerMessageSender")
            WebServiceMessageSender messageSender,
            @Qualifier("partnerHeaderInterceptor")
            ClientInterceptor headerInterceptor,
            @Qualifier("partnerWsSecurityInterceptor")
            ClientInterceptor securityInterceptor) {

        WebServiceTemplate template = new WebServiceTemplate();
        template.setDefaultUri("https://partner.example.com/soap");
        template.setMarshaller(partnerMarshaller);
        template.setUnmarshaller(partnerMarshaller);
        template.setMessageSenders(messageSender);
        template.setInterceptors(new ClientInterceptor[] {
                headerInterceptor,
                securityInterceptor
        });
        return template;
    }
}
~~~

Ví dụ giả định đã có bean **Jaxb2Marshaller**, **partnerMessageSender**, **partnerHeaderInterceptor** và **partnerWsSecurityInterceptor**. Jaxb2Marshaller được dùng cho cả marshal request lẫn unmarshal response. Thay endpoint và các bean theo cấu hình thực tế của ứng dụng.

Trong flow Spring Integration, outbound gateway phải sử dụng template đã cấu hình này. Nếu dùng XML namespace hoặc Java DSL, cách truyền template phụ thuộc phiên bản Spring Integration đang chạy; hãy kiểm tra cấu hình gateway của phiên bản dự án và xác nhận gateway đang tham chiếu đúng bean. Với lời gọi trực tiếp để minh họa, một Service Activator có thể gọi cùng template:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;
import org.springframework.ws.client.core.WebServiceTemplate;

@Component
public class PartnerSoapOperation {

    private final WebServiceTemplate partnerWebServiceTemplate;

    public PartnerSoapOperation(
            @Qualifier("partnerWebServiceTemplate")
            WebServiceTemplate partnerWebServiceTemplate) {
        this.partnerWebServiceTemplate = partnerWebServiceTemplate;
    }

    @ServiceActivator(inputChannel = "partnerSoapRequests")
    public Object invoke(Object request) {
        return partnerWebServiceTemplate.marshalSendAndReceive(request);
    }
}
~~~

Đoạn Service Activator trên chỉ minh họa việc gọi template từ một endpoint của Spring Integration. Khi dùng Web Services outbound gateway, giữ gateway làm adapter chuyên dụng và cấu hình gateway để dùng template có interceptor. Tránh tạo template mới trong từng lần xử lý message vì sẽ làm mất cấu hình dùng chung, tăng chi phí khởi tạo và khiến hành vi khó kiểm soát.

Nếu ứng dụng có nhiều đối tác, nên tạo template, message sender và bộ interceptor riêng cho từng hợp đồng. Không dùng chung một chính sách bảo mật nếu các đối tác có yêu cầu UsernameToken, chữ ký, chứng thư hoặc timeout khác nhau.

## 5. Bảo vệ SOAP message bằng WS-Security

WS-Security định nghĩa cách mang thông tin bảo mật trong SOAP header. Các cơ chế thường gặp gồm:

- **UsernameToken**: gửi danh tính client; có thể dùng password text hoặc password digest tùy chính sách đối tác.
- **Timestamp**: giới hạn thời gian hiệu lực của message, hỗ trợ phát hiện message cũ hoặc phát lại.
- **Signature**: ký các phần SOAP được chỉ định để bên nhận xác minh nguồn gốc và tính toàn vẹn.
- **Encryption**: mã hóa các phần SOAP được chỉ định để chỉ bên có khóa phù hợp đọc được.

Trong Spring Web Services, **Wss4jSecurityInterceptor** cung cấp tích hợp WS-Security dựa trên Apache WSS4J. Ví dụ sau cấu hình UsernameToken dạng digest và timestamp cho request đi:

~~~java
import org.apache.wss4j.dom.WSConstants;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

@Bean
Wss4jSecurityInterceptor partnerWsSecurityInterceptor(
        @Value("${partner.soap.username}") String username,
        @Value("${partner.soap.password}") String password) {

    Wss4jSecurityInterceptor interceptor =
            new Wss4jSecurityInterceptor();

    interceptor.setSecurementActions("Timestamp UsernameToken");
    interceptor.setSecurementUsername(username);
    interceptor.setSecurementPassword(password);
    interceptor.setSecurementPasswordType(WSConstants.PW_DIGEST);
    interceptor.setSecurementTimeToLive(300);

    return interceptor;
}
~~~

Các thuộc tính securement mô tả bảo mật áp dụng cho message gửi đi. Password digest không phải là cơ chế thay thế HTTPS; vẫn phải bảo vệ đường truyền và quản lý bí mật an toàn. Giá trị username, password và thời hạn phải khớp chính sách của đối tác. Không đưa credential thật vào source code hoặc file cấu hình được commit; lấy chúng từ secret manager hoặc cấu hình môi trường có kiểm soát.

Nếu đối tác ký response, client cần xác minh chữ ký bằng trust material đã được phê duyệt. Nếu hợp đồng yêu cầu mã hóa request, cần cấu hình chứng thư công khai của đối tác và chọn đúng phần SOAP cần mã hóa. Cấu hình ký và mã hóa thường cần Crypto/keystore, alias khóa, mật khẩu khóa, certificate chain và danh sách phần tử được bảo vệ. Các giá trị đó phải được quản lý theo môi trường và vòng đời chứng thư.

Một số nguyên tắc khi cấu hình WS-Security:

1. Thống nhất rõ action và thứ tự action với đối tác. Tên action như Timestamp, UsernameToken, Signature và Encrypt phải khớp chính sách hai phía.
2. Xác định rõ phần nào của SOAP Body và SOAP Header phải được ký hoặc mã hóa. Chỉ ký Body có thể chưa đủ nếu đối tác yêu cầu bảo vệ các header định tuyến hoặc định danh.
3. Xác minh chữ ký response bằng truststore và certificate đúng. Không chấp nhận chứng thư chỉ vì nó được gửi kèm message.
4. Đồng bộ đồng hồ giữa các hệ thống. Timestamp có thể bị từ chối khi clock skew vượt ngưỡng cho phép.
5. Dùng nonce, timestamp và cơ chế chống replay theo khả năng của stack và yêu cầu đối tác.
6. Kiểm thử cả trường hợp credential sai, timestamp hết hạn, chữ ký không hợp lệ và response không đáp ứng chính sách.

Chỉ bật validation cho các action mà đối tác cam kết gửi trong response. Nếu client yêu cầu chữ ký nhưng đối tác không ký response, cấu hình validation không phù hợp sẽ khiến mọi response bị từ chối. Ngược lại, nếu hợp đồng yêu cầu response phải được ký mà client không xác minh, ứng dụng có thể chấp nhận message đã bị sửa đổi.

## 6. Bảo vệ HTTP transport và TLS

SOAP thường được truyền qua HTTP(S), vì vậy bảo mật message và bảo mật transport cần được cấu hình riêng.

**HTTPS/TLS** cần xác minh certificate chain và hostname của máy chủ. Truststore phải chứa CA hoặc chứng thư được tổ chức tin cậy; khi dùng mutual TLS, client cần keystore chứa private key và certificate phù hợp. Không tắt hostname verification, không dùng trust-all TrustManager và không bỏ qua lỗi handshake để làm cho tích hợp chạy được.

**HTTP Basic, Bearer token hoặc API key** thuộc lớp HTTP. Cấu hình chúng tại HTTP message sender hoặc cơ chế transport tương ứng với phiên bản Spring-WS và HTTP client đang dùng. Đừng nhầm HTTP Authorization header với SOAP header. Với token ngắn hạn, cần có cơ chế lấy mới, xử lý hết hạn và tránh log token. Nếu đối tác dùng OAuth2, xác định rõ nơi lấy token, audience/scope, thời hạn và cách refresh; không mặc định rằng WS-Security tự thực hiện OAuth2.

Message sender cũng là nơi cần xem xét:

- Connection timeout và read/response timeout.
- Connection pooling và giới hạn số kết nối khi có tải đồng thời.
- TLS protocol và cipher suite theo chuẩn của tổ chức.
- Truststore, keystore và lịch thay certificate.
- Proxy, DNS và cấu hình mạng của môi trường triển khai.

Tên class và cách cấu hình HTTP client có thể khác giữa các phiên bản Spring Web Services và thư viện HTTP được chọn. Hãy dùng message sender tương thích với phiên bản trong dự án, rồi kiểm thử TLS thực tế ở môi trường tích hợp. Không sao chép cấu hình SSL từ một phiên bản khác mà chưa kiểm tra API và dependency.

## 7. Lỗi bảo mật và xử lý trong Spring Integration

Có thể chia lỗi thành ba nhóm để chọn cách xử lý:

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Lỗi xác thực hoặc chính sách | HTTP 401/403, UsernameToken sai, chữ ký không hợp lệ | Dừng lời gọi, cảnh báo cấu hình hoặc credential, không retry mù |
| Lỗi SOAP nghiệp vụ | SOAP Fault, mã lỗi nghiệp vụ, request không hợp lệ | Đọc fault code/detail theo hợp đồng, ánh xạ sang lỗi nghiệp vụ |
| Lỗi transport tạm thời | Timeout, DNS tạm lỗi, connection reset, HTTP 5xx | Có thể retry có giới hạn nếu operation an toàn để retry |

SOAP Fault là response SOAP có cấu trúc lỗi. Interceptor nhận fault qua **handleFault**; lỗi transport hoặc lỗi xảy ra trong quá trình gọi có thể đi qua exception và được quan sát ở **afterCompletion**. Không coi mọi lỗi đều là SOAP Fault.

Trong Spring Integration, exception từ outbound endpoint có thể được chuyển đến error channel theo cấu hình flow. Khi thêm retry advice, cần phân loại exception và đặt giới hạn số lần thử, khoảng nghỉ và tổng thời gian. Chỉ retry lỗi tạm thời. Một timeout không chứng minh rằng đối tác chưa xử lý request: server có thể đã thực hiện nghiệp vụ nhưng response bị mất. Với thao tác tạo giao dịch hoặc cập nhật dữ liệu, hãy dùng idempotency key hoặc cơ chế tra cứu trạng thái theo hợp đồng trước khi gửi lại.

Không trả thông tin nội bộ như stack trace, đường dẫn keystore, token hoặc chi tiết chứng thư cho hệ thống gọi. Có thể ghi correlation ID và mã lỗi đã chuẩn hóa vào error flow để đội vận hành tra cứu log bảo mật.

## 8. Kiểm thử interceptor và chính sách bảo mật

Kiểm thử cần xác nhận cả hành vi đúng lẫn hành vi từ chối:

- Request có đúng SOAP header, namespace và giá trị theo hợp đồng.
- UsernameToken và Timestamp được tạo đúng action và định dạng.
- Response hợp lệ được chấp nhận; response thiếu hoặc sai chữ ký bị từ chối nếu chính sách yêu cầu chữ ký.
- SOAP Fault được chuyển đến nhánh lỗi phù hợp.
- HTTP 401/403 không bị retry như lỗi mạng tạm thời.
- Timeout được giới hạn theo cấu hình và không làm treo toàn bộ flow.
- Log không chứa password, token hoặc nội dung SOAP nhạy cảm.

Spring-WS cung cấp **MockWebServiceServer** để kiểm thử request/response của WebServiceTemplate mà không cần gọi đối tác thật. Có thể dùng request matcher để xác minh SOAP payload và header, rồi trả về response hoặc SOAP Fault giả lập. Kiểm thử TLS, mutual TLS, certificate rotation và tương thích WS-Security vẫn cần môi trường tích hợp có chứng thư và chính sách gần với môi trường triển khai.

Một bài kiểm thử bảo mật hữu ích nên có ít nhất một ca thành công và các ca âm tính: credential sai, timestamp cũ, certificate không được tin cậy, chữ ký sai và HTTP authorization bị từ chối. Ghi rõ chính sách nào đang được kiểm tra để khi hợp đồng đối tác thay đổi, nhóm có thể cập nhật test có chủ đích.

## 9. Sự cố thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra |
|---|---|
| Interceptor không được gọi | Outbound gateway đang dùng WebServiceTemplate khác; interceptor chưa được đăng ký vào template thực tế |
| Request có SOAP header nhưng đối tác không nhận | Sai namespace, tên phần tử, SOAP version hoặc header không đúng hợp đồng |
| Đối tác trả HTTP 401/403 | Sai cơ chế hoặc credential ở lớp HTTP; kiểm tra Authorization header và quyền của client |
| WS-Security từ chối UsernameToken | Sai password type, username, password, nonce hoặc quy tắc timestamp |
| Signature validation failed | Sai truststore/certificate, alias, phần tử được ký, thứ tự action hoặc cấu hình canonicalization |
| TLS handshake failed | Certificate chain không được tin cậy, hostname không khớp, certificate hết hạn hoặc TLS policy không tương thích |
| Chỉ lỗi khi chạy đồng thời | Interceptor đang giữ trạng thái mutable dùng chung hoặc token/context không an toàn theo luồng |
| Retry tạo dữ liệu trùng | Operation không idempotent và chưa có idempotency key hoặc cơ chế đối soát |

Khi điều tra, kiểm tra theo thứ tự: endpoint và transport, HTTP status, SOAP Fault, WS-Security policy, sau đó mới đến payload nghiệp vụ. Dùng correlation ID để nối log của Integration flow với log của SOAP client và hệ thống đối tác.

## 10. Checklist trước khi đưa adapter vào vận hành

- [ ] Outbound gateway sử dụng đúng WebServiceTemplate đã cấu hình interceptor.
- [ ] Interceptor thread-safe và không giữ dữ liệu của request trước.
- [ ] SOAP header đúng namespace và đúng hợp đồng.
- [ ] WS-Security action, phần tử ký/mã hóa và validation khớp chính sách đối tác.
- [ ] HTTPS xác minh certificate chain và hostname; mTLS được cấu hình nếu cần.
- [ ] HTTP credential và WS-Security credential được quản lý riêng, lấy từ nguồn bí mật phù hợp.
- [ ] Timeout, connection pool và giới hạn retry phù hợp với SLA.
- [ ] Error flow phân biệt lỗi bảo mật, SOAP Fault và lỗi transport.
- [ ] Có idempotency hoặc đối soát cho operation có tác dụng phụ.
- [ ] Log có correlation ID nhưng không làm lộ token, password, private key hay SOAP payload nhạy cảm.
- [ ] Có kiểm thử âm tính cho credential, timestamp, chữ ký, certificate và quyền HTTP.

Một client SOAP an toàn cần đồng thời tuân thủ hợp đồng message, chính sách WS-Security, bảo vệ transport và cách xử lý lỗi của Spring Integration. Khi các lớp này được cấu hình trên đúng WebServiceTemplate mà gateway sử dụng, các flow nghiệp vụ có thể tái sử dụng chính sách bảo mật nhất quán và xử lý lỗi có kiểm soát.

