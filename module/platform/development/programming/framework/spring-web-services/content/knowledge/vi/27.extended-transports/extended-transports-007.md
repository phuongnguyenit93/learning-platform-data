# Tổng quan transport email, XMPP và nhu cầu tích hợp chuyên biệt

## 1. Vì sao SOAP cần transport ngoài HTTP?

Trong module **SPRING_WEB_SERVICES**, dịch vụ SOAP được phát triển theo hướng **contract-first**: XSD định nghĩa cấu trúc dữ liệu, WSDL mô tả operation và binding, JAXB/OXM ánh xạ XML, còn Spring-WS điều phối thông điệp tới @Endpoint. Tuy nhiên, không phải đối tác nào cũng có thể gọi một HTTP endpoint trực tiếp. Một tổ chức có thể chỉ cho phép trao đổi qua mailbox email; một hệ thống nội bộ có thể đã có mạng XMPP và định danh JID để gửi thông điệp giữa các actor.

Spring-WS tách **SOAP message** khỏi **transport**. Cùng một WebServiceMessage có thể được gửi qua nhiều sender, được receiver chuyển tới MessageDispatcher, rồi xử lý bởi endpoint mapping, interceptor và @Endpoint. Vì vậy, XSD/WSDL và business endpoint có thể giữ ổn định khi thay đổi kênh truyền tải, miễn payload/Envelope và quy ước tích hợp tương thích.

Ở Spring-WS **4.1.4**, các transport đang được tài liệu và API công bố gồm:

- **Email:** MailMessageSender phía client, MailMessageReceiver phía server. Request được gửi qua SMTP; response được lấy qua POP3 hoặc IMAP.
- **XMPP:** XmppMessageSender phía client, XmppMessageReceiver phía server. Triển khai dựa trên thư viện Smack và địa chỉ JID.
- **Các thành phần dùng chung:** WebServiceMessageFactory, WebServiceTemplate, MessageDispatcher, endpoint mappings, EndpointInterceptor và JAXB/OXM.

Đây là các transport thực sự trong Spring-WS, không phải chỉ ví dụ cũ. Tuy nhiên, chúng không phải HTTP với tên khác: cách nhận phản hồi, timeout, routing, bảo mật, độ tin cậy và vận hành đều khác.

### Mục tiêu học tập

Sau bài thuộc chương **Truyền tải mở rộng**, bạn có thể:

1. Phân biệt SOAP message, SOAP binding và transport.
2. Mô tả vai trò WebServiceMessageSender, WebServiceMessageReceiver, MessageDispatcher và WebServiceMessageFactory.
3. Hiểu luồng email SOAP qua SMTP, POP3/IMAP, MailMessageSender, MailMessageReceiver và MonitoringStrategy.
4. Hiểu luồng XMPP SOAP qua XmppMessageSender, XmppMessageReceiver, Smack và JID.
5. Chọn polling, IMAP IDLE, receive timeout, correlation và reply routing phù hợp.
6. Phân biệt Spring-WS transports với channel adapters của Spring Integration.
7. Thiết kế bảo mật transport/message, allowlist destination, giới hạn payload và xử lý lỗi.
8. Lập kế hoạch kiểm thử và vận hành cho các tích hợp email/XMPP.

**Nguyên tắc trung tâm:** XSD/WSDL mô tả dữ liệu và ý nghĩa operation. Transport quyết định message được chuyển đi và phản hồi đến theo cách nào. Đổi transport không tự giải quyết retry, duplicate, identity, authorization hoặc transaction.

## 2. Mô hình chung: message không đồng nhất với đường truyền

### 2.1. Các lớp cần phân biệt

| Lớp | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| Business contract | Định nghĩa request, response, Fault và quy tắc dữ liệu. | XSD SubmitInvoiceRequest, WSDL SubmitInvoice. |
| SOAP message | Envelope, Header, Body, Fault và MIME parts nếu có. | SOAP 1.1 Envelope chứa XML payload. |
| Message factory | Tạo/đọc WebServiceMessage từ representation của transport. | SaajSoapMessageFactory. |
| Spring-WS dispatcher | Mapping message tới endpoint, gọi interceptor và adapter. | MessageDispatcher, PayloadRootAnnotationMethodEndpointMapping. |
| Transport | Gửi/nhận message qua kênh bên ngoài. | HTTP, email, XMPP, JMS. |
| Application service | Thực hiện nghiệp vụ và quản lý trạng thái. | Kiểm tra hóa đơn, cấp receipt, cập nhật trạng thái. |

~~~mermaid
flowchart TD
    A["XSD + WSDL contract"] --> B["JAXB / XML payload"]
    B --> C["SOAP WebServiceMessage"]
    C --> D{"Transport sender"}
    D --> E["HTTP / HTTPS"]
    D --> F["Email: SMTP"]
    D --> G["XMPP: Smack / JID"]
    E --> H["Transport-specific receiver"]
    F --> H
    G --> H
    H --> I["WebServiceMessageFactory"]
    I --> J["MessageDispatcher"]
    J --> K["Endpoint mapping / interceptors"]
    K --> L["@Endpoint"]
    L --> M["Business service"]
    M --> N["SOAP response / Fault"]
~~~

Sơ đồ là mô hình khái niệm. Với email, server thường có receiver độc lập theo dõi mailbox; với XMPP, receiver đăng ký xử lý message trên một XMPP connection. Không phải mọi transport đều đi qua MessageDispatcherServlet hoặc HTTP servlet.

### 2.2. WebServiceTemplate chọn sender bằng URI

Phía client, WebServiceTemplate marshal/unmarshal object và chọn WebServiceMessageSender phù hợp với URI đích. Có thể đặt defaultUri trên template hoặc truyền URI lúc gọi. Template cũng cho phép cấu hình một hay nhiều message senders.

~~~java
Object response = webServiceTemplate.marshalSendAndReceive(
    "https://partner.example.com/ws",
    request);
~~~

hoặc dùng defaultUri đã cấu hình:

~~~java
Object response =
    webServiceTemplate.marshalSendAndReceive(request);
~~~

Scheme của URI là tín hiệu để sender hỗ trợ transport tương ứng. Sender còn có thể kiểm tra destination bằng DestinationPolicy. Không ghép URI nhận từ người dùng vào lời gọi mà không xác thực/allowlist.

### 2.3. Endpoint nên độc lập SMTP và XMPP

Một endpoint tốt xử lý ý nghĩa XML nghiệp vụ, không tự mở mailbox hoặc đăng nhập XMPP server.

~~~java
@Endpoint
public class InvoiceEndpoint {
    private static final String NS =
        "https://example.com/invoices/v1";

    private final InvoiceApplicationService service;

    public InvoiceEndpoint(InvoiceApplicationService service) {
        this.service = service;
    }

    @PayloadRoot(namespace = NS, localPart = "SubmitInvoiceRequest")
    @ResponsePayload
    public SubmitInvoiceResponse submit(
            @RequestPayload SubmitInvoiceRequest request) {
        return service.submit(request);
    }
}
~~~

Các lớp request/response được sinh từ XSD; service là thành phần ứng dụng. Endpoint có thể xử lý cùng QName và payload khi receiver chuyển message tương thích tới dispatcher.

**Giới hạn:** cùng XSD/WSDL không có nghĩa hành vi transport giống nhau. HTTP thường trả response trên cùng exchange; email trả thư riêng; XMPP gửi stanza reply. Timeout, reply address, lỗi delivery và retry semantics vẫn khác nhau.

## 3. So sánh HTTP, email và XMPP

| Tiêu chí | HTTP/HTTPS | Email transport | XMPP transport |
| --- | --- | --- | --- |
| Địa chỉ | URL/URI dịch vụ. | Mailbox qua mailto URI. | JID qua xmpp URI. |
| Kênh chính | Request/response trên kết nối HTTP. | SMTP gửi; POP3/IMAP nhận. | Kết nối XMPP, message stanza qua Smack. |
| Client | HTTP message sender. | MailMessageSender. | XmppMessageSender. |
| Server | HTTP receiver/Servlet. | MailMessageReceiver theo dõi mailbox. | XmppMessageReceiver dùng connection. |
| Response | Thường trong cùng HTTP exchange. | Email riêng được gửi về mailbox. | Message XMPP khác, cần correlation. |
| Nhịp nhận | Khi HTTP request tới. | Polling hoặc IMAP IDLE. | Theo sự kiện message trên connection. |
| Độ trễ | Thường thấp và tương tác ngay. | Có thể cao, phụ thuộc queue/polling/mail server. | Thường gần thời gian thực, phụ thuộc kết nối/server. |
| Presence | Không phải chức năng lõi. | Không có presence như mạng actor. | Hỗ trợ presence. |
| Rủi ro | TLS/proxy/rate limits/HTTP retries. | Spam, mailbox quota, MIME parsing, duplicate/late mail. | JID routing, connection state, stanza limits, domain policy. |

**Không chọn transport theo sở thích công nghệ.** Hãy bắt đầu từ khả năng của đối tác, độ trễ chấp nhận được, mô hình response, mức tải, payload size, security boundary và chi phí vận hành.

## 4. Email transport trong Spring-WS

### 4.1. Luồng xử lý email SOAP

Email transport dùng ba thành phần:

- **SMTP:** gửi request hoặc response.
- **POP3 hoặc IMAP:** truy xuất mailbox chứa request/response.
- **Mailbox:** nơi lưu message, thường là folder như INBOX.

Server-side MailMessageReceiver theo dõi folder POP3/IMAP, chuyển email thành WebServiceMessage, đưa vào MessageDispatcher, sau đó gửi response qua SMTP.

Client-side MailMessageSender tạo email từ WebServiceMessage, gửi SMTP rồi chờ email phản hồi ở POP3/IMAP. Vì vậy client có thể bị block trong giai đoạn đợi response.

~~~mermaid
sequenceDiagram
    participant C as SOAP client
    participant SMTP as SMTP server
    participant MB as Server mailbox
    participant R as MailMessageReceiver
    participant D as MessageDispatcher
    participant E as @Endpoint
    participant MBR as Client reply mailbox
    C->>SMTP: Gửi email chứa SOAP request
    SMTP->>MB: Phân phối vào mailbox server
    R->>MB: Poll hoặc IMAP IDLE
    MB-->>R: Email mới
    R->>D: Chuyển WebServiceMessage
    D->>E: Dispatch theo SOAP payload
    E-->>D: SOAP response hoặc Fault
    D->>SMTP: Gửi response qua SMTP
    SMTP->>MBR: Phân phối mail phản hồi
    C->>MBR: Poll POP3/IMAP và nhận response
~~~

Sơ đồ minh họa một luồng request/response. Thư có thể đến trễ, trùng, bị lọc spam, nằm trong folder khác hoặc bị mail server từ chối. Email delivery không đồng nghĩa business operation đã được xử lý thành công.

### 4.2. MailMessageReceiver và MonitoringStrategy

MailMessageReceiver là server-side component chạy độc lập, cần:

1. WebServiceMessageFactory để dựng SOAP message;
2. MessageDispatcher để chuyển request tới endpoint;
3. storeUri để truy cập mailbox nhận request, thường là POP3/IMAP;
4. transportUri để gửi response, thường là SMTP;
5. MonitoringStrategy để phát hiện thư mới.

| Strategy | Cách hoạt động | Khi phù hợp |
| --- | --- | --- |
| PollingMonitoringStrategy | Poll folder theo chu kỳ. | IMAP server không hỗ trợ IDLE hoặc muốn cơ chế đơn giản. |
| Pop3PollingMonitoringStrategy | Strategy dành cho POP3. | Mailbox POP3; không dùng PollingMonitoringStrategy chung cho POP3. |
| ImapIdleMonitoringStrategy | Dựa trên IMAP IDLE để được thông báo khi mailbox thay đổi. | IMAP server hỗ trợ IDLE và cần giảm polling định kỳ. |

Spring-WS cho phép thay đổi pollingInterval và deleteMessages. Javadoc Spring-WS 4.1.4 nêu polling interval mặc định của PollingMonitoringStrategy là 60 giây; hãy cấu hình rõ interval theo yêu cầu triển khai thay vì phụ thuộc mặc định. Các monitoring strategies mặc định xóa email đã xử lý; có thể thay đổi deleteMessages nếu cần policy lưu trữ riêng.

**Cần phân biệt:** xóa mail sau khi handler chạy không phải transaction chung với database nghiệp vụ. Nếu process chết sau khi lưu hóa đơn nhưng trước khi hoàn tất xử lý mailbox, message có thể được gửi lại hoặc trạng thái mailbox không phản ánh business commit. Phải có idempotency/dedup ở tầng nghiệp vụ.

### 4.3. Ví dụ cấu hình server-side email transport

~~~xml
<beans>
    <bean id="messageFactory"
          class="org.springframework.ws.soap.saaj.SaajSoapMessageFactory"/>
    <bean id="mailReceiver"
          class="org.springframework.ws.transport.mail.MailMessageReceiver">
        <property name="messageFactory" ref="messageFactory"/>
        <property name="from" value="soap-server@example.com"/>
        <property name="storeUri" value="MAIL_STORE_URI_FROM_SECRET_CONFIG"/>
        <property name="transportUri" value="SMTP_TRANSPORT_URI_FROM_SECRET_CONFIG"/>
        <property name="messageReceiver" ref="messageDispatcher"/>
        <property name="monitoringStrategy">
            <bean class="org.springframework.ws.transport.mail.monitor.PollingMonitoringStrategy">
                <property name="pollingInterval" value="30000"/>
                <property name="deleteMessages" value="true"/>
            </bean>
        </property>
    </bean>
    <bean id="messageDispatcher"
          class="org.springframework.ws.soap.server.SoapMessageDispatcher"/>
</beans>
~~~

Đây là **khung cấu hình minh họa**, giả định dependency Jakarta Mail và các bean endpoint mapping được cấu hình phù hợp. messageDispatcher trong dự án thực phải được nối với endpoint mappings và exception resolvers; ví dụ không phải một ứng dụng hoàn chỉnh.

Các URI mail phải đến từ secret/configuration system có kiểm soát. Không ghi username/password thật của mailbox vào XML trong Git hoặc log.

### 4.4. URI và cấu hình MailMessageSender

Client MailMessageSender dùng URI đích dạng:

~~~text
mailto:partner@example.com
mailto:partner@example.com?subject=SOAP%20Request
~~~

Các URI chỉ định mailbox nhận request; sender cần thêm:

- transportUri: mail transport dùng để gửi (thường SMTP);
- storeUri: mail store dùng để nhận response (POP3/IMAP);
- from: địa chỉ gửi được quản trị;
- receive timeout: thời gian client chờ thư phản hồi;
- subject/metadata theo convention đã thống nhất với đối tác.

Ví dụ client:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.transport.mail.MailMessageSender;
import org.springframework.ws.soap.saaj.SaajSoapMessageFactory;

@Configuration
public class EmailSoapClientConfiguration {
    @Bean
    public MailMessageSender mailMessageSender(Environment env) {
        MailMessageSender sender = new MailMessageSender();
        sender.setFrom("soap-client@example.com");
        sender.setTransportUri(
            env.getRequiredProperty("soap.mail.transport-uri"));
        sender.setStoreUri(
            env.getRequiredProperty("soap.mail.store-uri"));
        sender.setReceiveSleepTime(120_000);
        return sender;
    }

    @Bean
    public WebServiceTemplate emailSoapTemplate(
            SaajSoapMessageFactory messageFactory,
            Jaxb2Marshaller marshaller,
            MailMessageSender mailMessageSender) {
        WebServiceTemplate template =
            new WebServiceTemplate(messageFactory);
        template.setMarshaller(marshaller);
        template.setUnmarshaller(marshaller);
        template.setMessageSender(mailMessageSender);
        template.setDefaultUri(
            "mailto:partner@example.com?subject=SOAP%20Request");
        return template;
    }
}
~~~

Đây là ví dụ Spring-WS 4.1.x với Jakarta Mail. Package MailMessageSender vẫn nằm trong org.springframework.ws.transport.mail. Giá trị 120_000 chỉ minh họa; client cần cấu hình timeout theo polling interval, độ trễ mail server và SLA. Javadoc yêu cầu receive sleep time không nhỏ hơn polling interval của receiver trong request/response conversation.

Một số trường hợp nên truyền URI lúc gọi thay cho defaultUri, nhất là khi một client gửi nhiều đối tác. Không ghép địa chỉ email tùy ý vào URI mà không xác thực/allowlist.

### 4.5. Email request/response không tương đương một HTTP round trip

MailMessageSender có thể đợi response mail, nhưng điều đó không biến SMTP thành transport đồng bộ có latency thấp. Client đang thực hiện một request/response API ở tầng Java trong khi bên dưới là quá trình lưu trữ, chuyển phát và truy xuất mail riêng biệt.

Các hệ quả:

- Timeout dài không chứng minh server đã thất bại; email request có thể còn trong queue.
- Retry có thể tạo hai email và hai lần thực hiện nghiệp vụ.
- Subject không đủ làm correlation key duy nhất.
- Một mailbox có thể nhận email từ nguồn ngoài danh sách đối tác.
- Server có thể nhận email đã bị sửa, forward hoặc chuyển qua gateway khác.
- SMTP accepted không đồng nghĩa người nhận đã nhận hoặc xử lý; cần receipt/acknowledgement ở tầng ứng dụng nếu quan trọng.

Nếu use case cần xử lý chậm, nên thiết kế **acknowledgement + correlation ID + operation status** thay vì giữ thread chờ mail vô thời hạn.

### 4.6. Out-of-band reply và an toàn destination

Với WS-Addressing ReplyTo/FaultTo, server có thể phải gửi response tới địa chỉ ngoài luồng request. Với mail sender, Spring-WS kiểm tra mailbox có hợp lệ và mặc định từ chối một số local-only mailbox host. Có thể gắn DestinationPolicy nếu cần allowlist domain hoặc quy tắc nghiêm ngặt hơn.

Đây là một ranh giới an ninh quan trọng: **không cho requester tùy ý điều khiển server gửi SOAP Fault tới mailbox nội bộ hay địa chỉ ngoài tenant**. Cần:

- Allowlist domain/email recipient theo đối tác đã xác thực;
- Kiểm tra mailbox syntax, header injection, recipient count và độ dài;
- Không tin ReplyTo chỉ vì nó có QName hợp lệ;
- Chặn địa chỉ localhost/internal-only và destination không được phép;
- Ghi audit destination ở mức metadata đã chuẩn hóa;
- Giới hạn SMTP relay, outbound rate và kích thước attachment.

Nếu không cần out-of-band reply, nên giữ response trong convention mailbox đã định trước.

## 5. XMPP transport trong Spring-WS

### 5.1. XMPP là mạng messaging có định danh, không phải email realtime

**XMPP (Extensible Messaging and Presence Protocol)**, trước đây thường được gọi là Jabber, là giao thức nhắn tin dựa trên XML. Trong hệ thống XMPP, các actor có địa chỉ **Jabber ID/JID**, có thể gửi message trực tiếp và phát trạng thái presence.

Spring-WS sử dụng thư viện **Smack** để tích hợp XMPP. Hai thành phần chính:

- XmppMessageSender: triển khai WebServiceMessageSender, dùng cho WebServiceTemplate;
- XmppMessageReceiver: nhận XMPP message trên server và chuyển tới MessageDispatcher.

Spring-WS 4.1.4 vẫn công bố các sender/receiver này trong package org.springframework.ws.transport.xmpp; đây là support transport cụ thể của Spring-WS.

### 5.2. JID và xmpp URI

JID thường có cấu trúc:

~~~text
localpart@domainpart/resource
~~~

Ví dụ:

~~~text
invoice-bot@example.org/soap-gateway
~~~

xmpp URI dùng destination JID:

~~~text
xmpp:invoice-bot@example.org
~~~

Resource có thể mô tả một kết nối/client cụ thể. Khi thiết kế routing, phải thống nhất destination JID, account đăng nhập, domain của XMPP service và cách xử lý message reply.

Không dùng JID như một chuỗi email. JID có quy tắc chuẩn hóa/định danh riêng; domain của JID còn liên hệ với service domain của connection.

### 5.3. Luồng XMPP SOAP

~~~mermaid
sequenceDiagram
    participant C as SOAP client
    participant S as Smack XMPPConnection
    participant X as XMPP server
    participant R as XmppMessageReceiver
    participant D as MessageDispatcher
    participant E as @Endpoint
    C->>S: Tạo SOAP WebServiceMessage
    S->>X: Gửi XMPP message tới JID server
    X->>R: Message stanza đến receiver
    R->>D: Chuyển thành WebServiceMessage
    D->>E: Dispatch theo payload QName
    E-->>D: SOAP response / Fault
    D-->>R: Response message
    R->>X: Gửi reply stanza
    X-->>S: Reply đến client
~~~

Sơ đồ mô tả request-response thông thường. XMPP còn có presence, stanza extensions và khả năng nhiều actor tương tác; tuy nhiên XmppMessageSender vẫn thực hiện một WebServiceConnection có receive call. Không nên suy rằng marshalSendAndReceive qua XMPP đồng nghĩa ứng dụng đã được thiết kế thành workflow bất đồng bộ hoàn chỉnh.

### 5.4. XMPP connection và receiver

Server-side XmppMessageReceiver cần:

- XMPPConnection/XMPPTCPConnection đã kết nối và xác thực;
- WebServiceMessageFactory;
- MessageReceiver, thường là MessageDispatcher.

Cấu hình XML minh họa:

~~~xml
<beans>
    <bean id="messageFactory"
          class="org.springframework.ws.soap.saaj.SaajSoapMessageFactory"/>
    <bean id="xmppConnection"
          class="org.springframework.ws.transport.xmpp.support.XmppConnectionFactoryBean">
        <property name="host" value="XMPP_HOST_FROM_SECRET_CONFIG"/>
        <property name="username" value="XMPP_USERNAME_FROM_SECRET_CONFIG"/>
        <property name="password" value="XMPP_PASSWORD_FROM_SECRET_CONFIG"/>
    </bean>
    <bean id="xmppReceiver"
          class="org.springframework.ws.transport.xmpp.XmppMessageReceiver">
        <property name="messageFactory" ref="messageFactory"/>
        <property name="connection" ref="xmppConnection"/>
        <property name="messageReceiver" ref="messageDispatcher"/>
    </bean>
    <bean id="messageDispatcher"
          class="org.springframework.ws.soap.server.SoapMessageDispatcher">
        <!-- Cấu hình endpointMappings và exceptionResolvers trong ứng dụng thực. -->
    </bean>
</beans>
~~~

Đây là cấu hình khung. Dependency Smack và các thành phần transport phải tương thích Spring-WS version đang dùng; thông tin đăng nhập lấy từ secret store. Production còn cần quản lý lifecycle/reconnect, TLS, certificate verification, giới hạn stanza và chính sách account/domain.

### 5.5. Client-side XmppMessageSender

Client XmppMessageSender yêu cầu XMPPConnection và URI dạng xmpp:<JID>. Nó tạo XMPP message từ WebServiceMessage, gửi đi rồi chờ phản hồi.

~~~java
import org.jivesoftware.smack.XMPPConnection;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.transport.xmpp.XmppMessageSender;

@Configuration
public class XmppSoapClientConfiguration {
    @Bean
    public XmppMessageSender xmppMessageSender(
            XMPPConnection connection) {
        XmppMessageSender sender = new XmppMessageSender();
        sender.setConnection(connection);
        sender.setMessageEncoding("UTF-8");
        sender.setReceiveTimeout(30_000);
        return sender;
    }

    @Bean
    public WebServiceTemplate xmppSoapTemplate(
            org.springframework.ws.soap.saaj.SaajSoapMessageFactory factory,
            org.springframework.oxm.jaxb.Jaxb2Marshaller marshaller,
            XmppMessageSender sender) {
        WebServiceTemplate template = new WebServiceTemplate(factory);
        template.setMarshaller(marshaller);
        template.setUnmarshaller(marshaller);
        template.setMessageSender(sender);
        template.setDefaultUri("xmpp:invoice-bot@example.org");
        return template;
    }
}
~~~

Đoạn code minh họa giả định bean XMPPConnection đã được tạo, đăng nhập và lifecycle được quản lý. receiveTimeout ở đây là ví dụ 30 giây; API XmppMessageSender có mặc định -1, có nghĩa receive blocking không có timeout. **Không giữ mặc định đó trong request thread cần giới hạn SLA** nếu không có kiểm soát khác.

### 5.6. Domain của JID và DestinationPolicy

Khi dùng sender cho destination do peer cung cấp (ví dụ WS-Addressing ReplyTo), Spring-WS kiểm tra JID domain có khớp service domain của connection đã cấu hình hay không. Có thể thêm DestinationPolicy để:

- Chỉ cho phép các domain/tenant nằm trong allowlist;
- Kiểm tra JID format và resource;
- Ngăn routing sang account hoặc domain nội bộ ngoài ý muốn;
- Áp chính sách routing riêng với destination nhận từ message đối tác.

Mặc định checks khác nhau theo WebServiceMessageSender.UriSource: URI do application cấu hình và URI từ remote message không có cùng trust level. Không biến JID từ SOAP Header thành destination outbound mà không validate.

### 5.7. Presence không phải SOAP acknowledgement

XMPP hỗ trợ presence để cho biết account/resource có thể online, unavailable hoặc trạng thái khác. Nhưng:

- Presence không chứng minh một SOAP operation đã được xử lý;
- Message stanza đã gửi không chứng minh endpoint nghiệp vụ đã commit;
- Reply message cần correlation/định danh riêng;
- Account có thể online nhưng service handler bị lỗi;
- Một kết nối XMPP có thể reconnect trong khi request đang chờ response.

Vì vậy cần SOAP/application acknowledgement, receipt ID, operation status và dedup theo business contract. Không dùng presence để suy ra trạng thái xử lý hóa đơn.

## 6. Email và XMPP trong kiến trúc tích hợp doanh nghiệp

### 6.1. Lựa chọn theo nhu cầu

| Nhu cầu | Email phù hợp khi | XMPP phù hợp khi |
| --- | --- | --- |
| Đối tác chỉ có hộp thư tích hợp | Có mailbox vận hành, chính sách mail và thời gian xử lý chậm. | Không phù hợp nếu đối tác không có XMPP infrastructure. |
| Nhận message đến theo sự kiện | IMAP IDLE khả dụng; polling không đáp ứng độ trễ. | XMPP connection ổn định, nhận stanza gần thời gian thực. |
| Batch và chứng từ | Có thể gửi email kèm message/attachment theo policy. | Có thể gửi metadata; file transfer/extension cần tiêu chuẩn và triển khai rõ. |
| Trạng thái actor | Không có presence như mạng realtime. | Presence là khả năng tự nhiên của XMPP. |
| Vận hành | Quản lý mailbox, quota, retention, spam, SMTP/IMAP credentials. | Quản lý XMPP server, JID, connection/reconnect, stanza policy. |
| Response | Thư phản hồi độc lập, có delay. | XMPP message reply, cần correlation. |

### 6.2. Email hay XMPP không phải message broker thay thế trong mọi trường hợp

Nếu yêu cầu gồm persistence/replay có bảo đảm, consumer groups, dead-letter queues, delivery guarantees, transaction integration và throughput lớn, cần đánh giá messaging transports chuyên dụng như JMS hoặc broker khác. Email và XMPP có thể phù hợp với hệ sinh thái đối tác cụ thể, nhưng không được mặc định có cùng delivery semantics với JMS/broker.

**Spring-WS transport** là cách đưa WebServiceMessage vào/ra SOAP dispatcher. **Spring Integration** lại cung cấp channel adapters, message channels, routers, transformers và flow orchestration. Spring Integration có các adapter riêng cho Mail và XMPP; chúng là abstraction khác với MailMessageSender/XmppMessageSender của Spring-WS.

~~~mermaid
flowchart LR
    A["Email/XMPP inbound adapter"] --> B["Spring Integration channel"]
    B --> C["Normalize metadata"]
    C --> D["Validate identity and payload"]
    D --> E["Business service"]
    E --> F["Build SOAP response/receipt"]
    F --> G["Email/XMPP outbound adapter"]
~~~

Nếu dùng Spring Integration, message có thể được chuyển qua nhiều channel/queue; nên có error channel và persistence/correlation rõ ràng. Đây không còn là chỉ một WebServiceTemplate request-response call.

### 6.3. Khi nào nên giữ HTTP làm transport chính?

HTTP/HTTPS thường là lựa chọn hợp lý khi:

- Client cần request/response trực tiếp và SLA thời gian thấp;
- Đối tác có thể gọi endpoint URL qua TLS;
- Cần gateway, observability, rate limits, OAuth2/mTLS và API management;
- Có yêu cầu tải file lớn hoặc MTOM theo hạ tầng đã kiểm thử;
- WSDL/public endpoint cần được công bố ổn định.

Email/XMPP là lựa chọn mở rộng khi một ràng buộc tích hợp cụ thể khiến HTTP không phù hợp, hoặc khi hệ thống đã có mạng/infra tương ứng.

## 7. Contract-first qua email/XMPP: dữ liệu nào phải có?

### 7.1. XSD/WSDL vẫn mô tả SOAP Body, không mô tả mọi thuộc tính transport

XSD có thể mô tả requestId, correlationId, partnerId/tenant, documentId, business timestamp, receipt/status và typed Faults. Nhưng XSD/WSDL SOAP binding không tự định nghĩa đầy đủ:

- SMTP From, To, IMAP folder, mail retention;
- email Message-ID, threading hoặc subject conventions;
- XMPP connection account, JID, resource, stanza routing và presence;
- receive timeout, polling interval hoặc reconnect behavior;
- duplicate delivery, quarantine và mailbox cleanup.

Đây là các **transport/integration configuration** và **operational contracts** cần được thống nhất riêng.

### 7.2. Correlation ID và idempotency

Một request email có thể tới mailbox hai lần; client có thể timeout rồi gửi lại. XMPP sender có thể không nhận response dù server đã xử lý. Với operation có side effect, ứng dụng cần:

1. requestId hoặc idempotency key duy nhất theo partner;
2. uniqueness constraint lưu bền vững ở database;
3. Trạng thái RECEIVED, PROCESSING, SUCCEEDED, REJECTED;
4. Receipt ID và operation status để client tra cứu;
5. Cơ chế duplicate trả cùng kết quả hoặc quy tắc từ chối rõ;
6. Retention/dedup window đã thỏa thuận;
7. Correlation ID xuyên logs/metrics mà không chứa secret.

**Không dùng email subject hoặc JID thread đơn độc làm idempotency key** nếu không có bảo đảm uniqueness và persistence theo contract.

### 7.3. Chuyển thành workflow bất đồng bộ

~~~mermaid
sequenceDiagram
    participant P as Partner
    participant T as Email/XMPP transport
    participant S as Spring-WS endpoint
    participant DB as Business database
    P->>T: SubmitRequest(requestId)
    T->>S: Deliver SOAP request
    S->>DB: Register requestId (unique)
    S->>DB: Persist operation as RECEIVED
    S-->>T: SOAP acknowledgement / receipt
    T-->>P: Deliver acknowledgement
    Note over S,DB: Process asynchronously
    S->>DB: Update result SUCCEEDED / REJECTED
    P->>T: GetStatus(receiptId)
    T->>S: SOAP status request
    S->>DB: Read durable result
    S-->>T: SOAP status response
    T-->>P: Deliver status
~~~

Đây là **mô hình ứng dụng gợi ý**, không phải behavior mặc định của MailMessageReceiver hoặc XmppMessageReceiver. Muốn xử lý bất đồng bộ thật, application phải có persistent state, scheduler/worker/queue và operation status contract.

## 8. Bảo mật transport và message

### 8.1. Email không phải kênh tin cậy mặc định

SMTP/IMAP/POP3 có thể được cấu hình TLS, nhưng điều đó không bảo đảm mọi hop email được mã hóa hoặc thư không bị forward/log/archive ở nơi khác.

Cần TLS cho SMTP submission, IMAP/POP3 và certificate verification; credential riêng cho service account; quyền mailbox tối thiểu; mailbox allowlist; giới hạn sender/recipient, số thư, message size và MIME parts; kiểm tra MIME Content-Type, attachment và malware; quarantine mail không hợp lệ; retention/deletion/backup policy; không ghi raw email body/SOAP Security Header vào logs công khai.

TLS ở chặng SMTP không tự tạo end-to-end SOAP confidentiality/integrity. Với dữ liệu nhạy cảm, xem xét WS-Security Signature/Encryption hoặc cơ chế mã hóa đầu cuối đã thỏa thuận.

### 8.2. XMPP security và trust

Một triển khai XMPP cần TLS/STARTTLS và xác minh certificate/domain của server; credentials riêng cho account/service; kiểm soát ai được gửi stanza vào JID; quản trị roster/subscription/presence; giới hạn stanza/body/extension size, message rate và connection count; validate sender JID/domain/tenant; quản lý reconnect, health checks và alert.

**XMPP account đã xác thực không tự chứng minh sender của từng SOAP business request có quyền.** Service phải ánh xạ sender JID sang principal/partner identity đáng tin và kiểm tra authorization theo operation/tài nguyên.

### 8.3. WS-Security dùng được ở nhiều transport

WS-Security nằm trong SOAP Header, nên có thể được giữ khi SOAP message gửi qua email hoặc XMPP, miễn message factory/receiver và client/server xử lý đúng. Cơ chế có thể gồm UsernameToken, Timestamp, XML Signature, XML Encryption và attachment protection.

Không được mặc định security behavior của HTTP tự áp dụng cho SMTP/XMPP. Interceptor Spring-WS có thể validate SOAP message, còn TLS/account authentication của email/XMPP là tầng khác. Cần kiểm tra cùng một policy qua từng transport, bao gồm Faults và reply routing.

### 8.4. Destination policy và SSRF

Khi SOAP Header có WS-Addressing ReplyTo/FaultTo, server có thể mở kết nối outbound tới destination mà requester cung cấp. Đây là nguy cơ SSRF/routing abuse nếu không kiểm tra:

- Email: chỉ chấp nhận mailbox/domain được phép; từ chối local-only destination và header injection.
- XMPP: kiểm tra JID/domain; domain cần khớp service domain của connection hoặc allowlist.
- HTTP out-of-band reply: kiểm tra URL, DNS, IP private/loopback/link-local và redirects.
- Không chấp nhận destination từ request chưa xác thực.
- Đặt quota response outbound, timeout và audit.

Spring-WS có DestinationPolicy để bổ sung allowlist và rules cho sender. Mặc định checks hữu ích nhưng **không thay thế allowlist theo tổ chức** hoặc đánh giá DNS/rebinding theo threat model.

## 9. Attachments và giới hạn payload

### 9.1. SOAP MIME attachments qua email

Email là MIME message nên có thể chứa MIME parts. Nhưng việc transport dùng MIME không có nghĩa mọi MIME part tự động trở thành SOAP attachment theo đúng contract:

- Root SOAP content phải được tạo/nhận bằng message factory phù hợp;
- Content-ID, Content-Type, multipart boundary và encoding phải hợp lệ;
- XSD/JAXB/MTOM hoặc SwA policy phải được client/server hỗ trợ đồng nhất;
- Mail gateway có thể quét, biến đổi, giới hạn hoặc chặn file;
- Kích thước email phải tính cả MIME headers, base64 expansion, body và attachment.

Không dùng email như file-transfer không giới hạn. Nên có maxMessageBytes, maxAttachmentBytes, số part tối đa, allowlist file type, malware scan và storage staging.

### 9.2. XMPP payload không nên chứa tệp rất lớn tùy tiện

XMPP message stanza chủ yếu là XML message content. Có thể dùng XMPP extensions (XEP) cho file transfer, nhưng client và server phải cùng hỗ trợ extension tương ứng. Không tự nhúng binary lớn dạng Base64 vào stanza và giả định Smack/XMPP server chịu được XML size, memory pressure, packet limits, timeout và security scanning.

Với tệp lớn, có thể dùng file/object storage endpoint có token/URL bảo vệ rồi gửi metadata/checksum qua SOAP/XMPP; đây là kiến trúc bổ sung phải được thỏa thuận, không phải chức năng mặc định của XmppMessageSender.

### 9.3. MTOM là cơ chế SOAP

MTOM/XOP tối ưu binary data trong SOAP message; nó không thay SMTP/IMAP/XMPP transport. Khi dùng MTOM, message factory cần hỗ trợ MIME packaging, JAXB marshaller cần cấu hình MTOM nếu cần, đối tác phải hiểu XOP/MTOM và gateway/transport không được làm hỏng package. Kiểm thử file bytes/checksum qua đúng transport, không chỉ kiểm tra SOAP Body marshal thành công.

## 10. SOAP Fault và lỗi transport

### 10.1. Không phải mọi lỗi đều có SOAP Fault

| Tình huống | Tầng lỗi | Kết quả client có thể thấy |
| --- | --- | --- |
| Mailbox/password sai | SMTP/POP3/IMAP auth | Mail transport exception hoặc không truy cập được mailbox. |
| SMTP relay từ chối recipient | SMTP | Lỗi gửi trước khi server SOAP xử lý request. |
| Thư vào spam/quarantine | Mail server/gateway | Client không nhận response, request có thể đã được gửi. |
| Mailbox đầy/quota | Mail store/SMTP | Delivery failure hoặc thư bị trì hoãn. |
| Mail polling chậm | Monitoring strategy | Response đến muộn hoặc client timeout. |
| XMPP account không đăng nhập | Smack/XMPP connection | Connection/authentication error. |
| JID không hợp lệ/domain mismatch | Destination validation | Destination reject hoặc transport error. |
| XMPP connection mất | Network/server | Send/receive exception, response có thể đã bị mất. |
| SOAP XML không hợp lệ | Message factory/parser | SOAP parsing/protocol error nếu có thể tạo Fault. |
| QName không map được endpoint | MessageDispatcher | Endpoint mapping exception/protocol error. |
| UsernameToken/Signature sai | WS-Security interceptor | SOAP Security Fault nếu SOAP message được xử lý đủ. |
| Lỗi validation/business | Endpoint/application | SOAP Fault theo exception resolver/contract. |

**Timeout không chứng minh operation chưa chạy.** Email request có thể tới server nhưng response chưa về. XMPP server có thể đã xử lý rồi connection bị reset trước khi client nhận reply.

### 10.2. Idempotency trước retry

~~~text
requestId = partnerId + operationId (unique)
payloadHash = hash(canonical business payload)

Nếu requestId mới:
    register and execute
Nếu requestId đã tồn tại + payloadHash giống:
    return previously stored receipt/result
Nếu requestId đã tồn tại + payloadHash khác:
    reject as idempotency conflict
~~~

Đây là logic ứng dụng minh họa. Trong triển khai thực cần unique constraint/transaction, retention và trạng thái durable. Không đặt idempotency chỉ ở một in-memory map hoặc transport thread.

### 10.3. Fault contract độc lập transport

WSDL/XSD có thể mô tả typed SOAP Fault và business error codes. Cùng một lỗi nghiệp vụ nên có **ý nghĩa Fault ổn định** dù message đi qua HTTP, email hoặc XMPP. Nhưng HTTP thường trả Fault qua response của kết nối; email gửi mail phản hồi; XMPP gửi stanza/message response. Nếu transport thất bại trước khi SOAP Fault được tạo hoặc phân phối, client chỉ thấy transport error. Không đưa mật khẩu mail/XMPP, stack trace hay nội dung tài liệu nhạy cảm vào Fault detail.

## 11. Khác nhau giữa Spring-WS và Spring Integration

### 11.1. Spring-WS transport

Trong Spring-WS:

- WebServiceMessageSender gửi SOAP WebServiceMessage;
- WebServiceMessageReceiver hoặc receiver chuyên biệt đưa SOAP message vào dispatcher;
- WebServiceTemplate cung cấp client API request/response;
- MessageDispatcher định tuyến SOAP message tới endpoint;
- EndpointInterceptor và WS-Security xử lý SOAP-level concerns.

Đây là lựa chọn khi mục tiêu chính là **gọi hoặc cung cấp SOAP service qua transport được Spring-WS hỗ trợ**.

### 11.2. Spring Integration adapters

Spring Integration cũng có Mail inbound/outbound channel adapters, XMPP inbound/outbound channel adapters, message channels, routers, filters, transformers, service activators và error channels. Đây là lựa chọn khi mục tiêu là xây **integration flow** giữa nhiều hệ thống/protocols. Cần kiểm tra artifact/version Spring Integration riêng; không suy các adapter này nằm trong spring-ws-core.

~~~mermaid
flowchart LR
    A["Email/XMPP inbound adapter"] --> B["Spring Integration channel"]
    B --> C["Normalize metadata"]
    C --> D["Validate identity and payload"]
    D --> E["Business service"]
    E --> F["Build SOAP response/receipt"]
    F --> G["Email/XMPP outbound adapter"]
~~~

Nếu dùng Spring Integration, message có thể đi qua nhiều channel/queue; cần error channel và persistence/correlation rõ. Đây không còn là chỉ một WebServiceTemplate request-response call.

### 11.3. Khi nào nên giữ HTTP làm transport chính?

HTTP/HTTPS thường hợp lý khi client cần request/response trực tiếp và SLA thấp; đối tác có thể gọi endpoint URL qua TLS; cần gateway, observability, rate limits, OAuth2/mTLS và API management; cần MTOM qua hạ tầng đã kiểm thử; hoặc WSDL/public endpoint cần công bố ổn định.

Email/XMPP là lựa chọn mở rộng khi một ràng buộc tích hợp cụ thể khiến HTTP không phù hợp, hoặc khi hệ thống đã có mạng/infra tương ứng.

## 12. Các API Spring-WS liên quan

| Transport | API | Trách nhiệm |
| --- | --- | --- |
| Email | org.springframework.ws.transport.mail.MailMessageSender | Gửi request email, đợi response từ POP3/IMAP. |
| Email | org.springframework.ws.transport.mail.MailMessageReceiver | Nhận mail request, dispatch và gửi response. |
| Email | org.springframework.ws.transport.mail.monitor.PollingMonitoringStrategy | Poll IMAP folder. |
| Email | org.springframework.ws.transport.mail.monitor.Pop3PollingMonitoringStrategy | Poll POP3 folder. |
| Email | org.springframework.ws.transport.mail.monitor.ImapIdleMonitoringStrategy | Nhận thông báo IMAP IDLE nếu server hỗ trợ. |
| XMPP | org.springframework.ws.transport.xmpp.XmppMessageSender | Gửi message và nhận response. |
| XMPP | org.springframework.ws.transport.xmpp.XmppMessageReceiver | Nhận XMPP message và dispatch. |
| XMPP | org.springframework.ws.transport.xmpp.support.XmppConnectionFactoryBean | Tạo connection từ cấu hình. |

Spring-WS 4.x dùng Jakarta generation cho mail APIs; class Spring-WS vẫn mang package org.springframework.ws. Dependency mail provider và Smack cần tương thích đúng BOM/version. Không trộn ví dụ cũ dùng javax.mail hoặc Smack API generation khác vào project Jakarta mà không kiểm tra.

Email/XMPP sender/receiver vẫn cần WebServiceMessageFactory để tạo và đọc SOAP message. Factory chịu trách nhiệm SOAP representation; sender/receiver chịu trách nhiệm transport.

WebServiceTemplate có thể dùng nhiều sender, nhưng nên cân nhắc tách template theo transport nếu mỗi transport có credential, timeout, DestinationPolicy, observability, retry policy và message size limit khác nhau.

## 13. Kiểm thử và vận hành

### 13.1. Test layers

| Kiểu test | Kiểm tra |
| --- | --- |
| XSD/JAXB unit | Payload marshal/unmarshal, QName, constraints. |
| MockWebServiceServer | Client WebServiceTemplate, callback, SOAP message/response logic. |
| MockWebServiceClient | Dispatcher, endpoint mapping, interceptor và SOAP Fault. |
| Email integration test | SMTP/IMAP hoặc POP3 sandbox, folder, polling/IDLE, response mailbox. |
| XMPP integration test | Smack connection, JID, stanza delivery, reply, reconnect và domain policy. |
| End-to-end | Hệ thống test mail/XMPP server với client partner fixture. |
| Failure/load tests | Duplicate/late delivery, mailbox quota, offline XMPP, timeout, concurrency và recovery. |

Mock SOAP tests không kiểm tra SMTP/IMAP/XMPP routing. Ngược lại, test SMTP acceptance không chứng minh SOAP Body đúng XSD hoặc WS-Security được validate.

### 13.2. Ma trận lỗi

| Ca thử | Email | XMPP |
| --- | --- | --- |
| Credential sai | SMTP/IMAP authentication failure. | XMPP authentication failure. |
| Destination không hợp lệ | Mailbox syntax/domain allowlist. | JID parsing/service-domain policy. |
| Message bị gửi trùng | Cùng request ID hai email. | Cùng request ID trong message/stanza. |
| Response đến trễ | IMAP mail đến sau receive timeout. | Stanza reply tới sau receive timeout. |
| Server restart | Mail còn trong mailbox được phát hiện lại theo strategy. | Connection reconnect và recovery theo server semantics. |
| Response bị mất | Mail gửi thành công nhưng client không lấy được. | Server gửi reply nhưng client mất connection. |
| Payload quá lớn | Mail size/attachment quotas. | Stanza/server packet limits. |
| WS-Security sai | SOAP Fault hoặc processing error trong mail message. | SOAP Fault hoặc processing error trong XMPP message. |
| Destination reply độc hại | ReplyTo mailbox nội bộ/không allowlist. | JID domain ngoài service domain. |
| Duplicate business effect | Idempotency theo request ID. | Idempotency theo request ID. |

### 13.3. Metrics và logs

~~~text
soap_transport_requests_total{transport, operation, outcome}
soap_transport_failures_total{transport, failure_category}
soap_transport_receive_wait_seconds{transport}
soap_mailbox_messages_pending
soap_mail_poll_duration_seconds
soap_xmpp_connection_state
soap_xmpp_reconnect_total
soap_business_duplicate_requests_total{operation}
soap_transport_payload_bytes{transport, direction}
~~~

Đây là metric đề xuất. Tránh đưa email address, JID đầy đủ, username, Message-ID, requestId hoặc payload field tùy ý làm label vì dễ gây cardinality cao và rò dữ liệu. Logs nên có correlation ID, transport type, operation QName, outcome và error category; không log passwords, WS-Security token, raw SOAP Envelope hoặc attachment.

### 13.4. Runbook tối thiểu

**Email:** kiểm tra SMTP relay/auth/TLS; kiểm tra mailbox URI/folder và IMAP/POP3 login; kiểm tra MonitoringStrategy, polling interval/IMAP IDLE và deleteMessages; đối chiếu Message-ID/correlation ID, thư pending/quarantine và duplicate; kiểm tra receive timeout; xác minh receiver còn chạy và mailbox response đúng.

**XMPP:** kiểm tra server availability, TLS/certificate và authentication; kiểm tra connection lifecycle, service domain, account/JID/resource; kiểm tra XmppMessageReceiver active và sender có connection; kiểm tra JID destination/reply policy, stanza delivery và response timeout; kiểm tra reconnect/offline behavior; đối chiếu request ID và business dedup.

## 14. Case study: đối tác gửi hóa đơn qua mailbox, hệ thống nội bộ dùng XMPP

### 14.1. Bối cảnh

Đối tác kế toán không thể gọi endpoint HTTP trực tiếp do chính sách mạng. Họ chỉ được phép gửi email đến mailbox tích hợp. Trong nội bộ, hệ thống xử lý hóa đơn phát thông báo qua XMPP đến các actor dịch vụ khác.

~~~text
Partner mail client
    → SMTP email chứa SOAP SubmitInvoiceRequest
    → MailMessageReceiver / IMAP mailbox
    → Spring-WS MessageDispatcher / InvoiceEndpoint
    → InvoiceApplicationService + database
    → Publish internal event to XMPP
    → XmppMessageSender / destination JID
    → Downstream actor
~~~

### 14.2. Các quyết định

1. XSD định nghĩa SubmitInvoiceRequest với requestId, partnerId, invoice data và attachment policy.
2. WSDL định nghĩa operation và typed Faults; transport email conventions được ghi riêng.
3. Mail receiver poll mailbox hoặc dùng IMAP IDLE nếu môi trường hỗ trợ.
4. Request phải đi qua allowlist sender/domain và WS-Security/authentication policy; email From không phải bằng chứng danh tính duy nhất.
5. Endpoint ghi request ID vào database với unique constraint trước khi thực hiện side effect.
6. Application phát event qua outbox sau khi commit business transaction.
7. XMPP consumer nhận event và dedup theo event ID; không tin presence thay acknowledgement.
8. Client đối tác dùng receipt/status operation để kiểm tra kết quả nếu email response đến trễ.

### 14.3. Lỗi và recovery

| Sự cố | Hành vi cần có |
| --- | --- |
| Đối tác gửi cùng email hai lần | Cùng request ID chỉ tạo một invoice. |
| Mail được nhận nhưng process chết trước database commit | Message được phục hồi/re-delivery theo mailbox strategy; không có kết quả nửa vời. |
| Database commit thành công nhưng email response gửi lỗi | Retry response/tra cứu receipt, không tạo invoice lần nữa. |
| XMPP server offline sau business commit | Outbox giữ event pending, retry chuyển phát. |
| Downstream XMPP consumer nhận trùng | Consumer dedup event ID. |
| Email có attachment độc hại/oversize | Quarantine/reject trước khi ghi vào vùng business storage. |
| Fault response bị gửi tới mailbox không được phép | DestinationPolicy/allowlist từ chối routing. |

**Bài học:** transport delivery, business commit và downstream event delivery là ba trạng thái riêng. Phải kết nối chúng bằng transaction/outbox, idempotency, receipt và monitoring; không giả định một lần gửi email hoặc XMPP stanza tạo thành giao dịch phân tán nguyên tử.

## 15. Những ngộ nhận phổ biến

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Spring-WS chỉ hỗ trợ HTTP.” | Spring-WS 4.1.4 còn có email, XMPP và JMS transports trong support module. |
| “Email/XMPP bắt buộc viết lại @Endpoint.” | Endpoint có thể giữ nguyên nếu receiver chuyển message tương thích tới dispatcher. |
| “Email transport chỉ gửi mail, không nhận response.” | MailMessageSender có thể chờ POP3/IMAP response; server có MailMessageReceiver. |
| “SMTP gửi thành công nghĩa SOAP operation hoàn tất.” | SMTP acceptance chỉ là transport delivery step. |
| “Mailbox polling mặc định chính xác một phút ở mọi version.” | Phải đối chiếu version/strategy và cấu hình rõ interval. |
| “IMAP IDLE và polling là cùng một cơ chế.” | Polling kiểm tra định kỳ; IMAP IDLE là cơ chế server thông báo thay đổi mailbox. |
| “POP3 có thể dùng mọi IMAP polling strategy.” | Spring-WS có Pop3PollingMonitoringStrategy riêng. |
| “XMPP chỉ là email realtime.” | XMPP có connection, JID, stanza, roster/presence và extension protocol riêng. |
| “JID tương đương email address.” | JID là định danh XMPP với local/domain/resource semantics. |
| “Presence online nghĩa server SOAP xử lý được request.” | Presence không phải business acknowledgement. |
| “XMPP sender không có timeout.” | XmppMessageSender có setReceiveTimeout; mặc định -1 là blocking không timeout. |
| “Cùng có MIME nên email và MTOM là một.” | MIME email và SOAP MTOM/XOP là hai lớp/cấu trúc khác nhau. |
| “Spring Integration XMPP adapter chính là Spring-WS XmppMessageSender.” | Một bên là channel adapter, bên kia là SOAP WebServiceMessageSender. |
| “Retry transport là an toàn cho mọi operation.” | Cần idempotency/receipt khi request có side effect. |
| “WS-Addressing ReplyTo luôn đáng tin.” | Phải validate destination và allowlist; có nguy cơ SSRF/routing abuse. |
| “Không có HTTP nên không cần WS-Security/TLS.” | Email/XMPP transport có security riêng và SOAP message có thể cần WS-Security. |
| “Một SOAP Fault luôn đến được client.” | SMTP/IMAP/XMPP có thể lỗi trước/sau khi Fault được tạo hoặc gửi. |

## 16. Checklist chọn và triển khai extended transport

### Contract và use case

- [ ] Đã xác định lý do cần email/XMPP thay HTTP/HTTPS.
- [ ] XSD/WSDL giữ business payload, operation và Fault ổn định.
- [ ] Đã định nghĩa request ID, correlation, receipt, status và idempotency.
- [ ] Đã thống nhất response mode, timeout, retry và SLA với đối tác.
- [ ] Đã ghi riêng transport conventions: mailbox/JID, subject, folder, destination và metadata.

### Email

- [ ] SMTP, POP3/IMAP host, TLS, certificates và credentials được quản trị an toàn.
- [ ] MailMessageSender có transportUri, storeUri, from và receive timeout đúng.
- [ ] MailMessageReceiver có messageFactory, dispatcher, store/transport URI và monitoring strategy.
- [ ] POP3 dùng strategy phù hợp; IMAP polling/IDLE được đánh giá theo server support.
- [ ] Polling interval, deleteMessages, mailbox retention và duplicate handling được cấu hình rõ.
- [ ] Domain/mailbox allowlist, spam/quarantine, header injection và outbound SMTP quota được quản lý.
- [ ] Giới hạn message/attachment size, MIME parts và malware scan đã được kiểm thử.

### XMPP

- [ ] Smack/XMPP dependencies tương thích version.
- [ ] Connection được tạo, authenticate, TLS/certificate verification và lifecycle/reconnect được quản lý.
- [ ] XmppMessageSender có connection và receive timeout hữu hạn khi cần.
- [ ] XmppMessageReceiver có connection, message factory và dispatcher.
- [ ] JID/domain/resource policy rõ, DestinationPolicy có allowlist cho remote destination.
- [ ] Presence không được dùng thay acknowledgement/business status.
- [ ] Stanza size, rate limits, connection count, offline behavior và server limits được kiểm thử.

### Security, reliability và operations

- [ ] TLS và identity của transport server được xác minh.
- [ ] WS-Security/Signature/Encryption áp dụng theo threat model và được test trên đúng transport.
- [ ] ReplyTo/FaultTo không thể hướng outbound message tới địa chỉ/domain không được phép.
- [ ] Business dedup/idempotency, transaction/outbox và recovery không phụ thuộc một transport thread.
- [ ] Có tests cho duplicate, late reply, timeout, mailbox/XMPP server outage, reconnect và restart.
- [ ] Metrics/logs có correlation nhưng không chứa passwords, token, raw SOAP payload hay attachment.
- [ ] Có runbook/mailbox monitoring/XMPP connection alerts và kế hoạch xoay credential.

## 17. Câu hỏi tự kiểm tra

1. Vì sao Spring-WS tách WebServiceMessageFactory, MessageDispatcher và WebServiceMessageSender?
2. Những lớp nào của SOAP contract có thể được tái sử dụng khi đổi HTTP sang email/XMPP?
3. MailMessageSender sử dụng SMTP và POP3/IMAP theo vai trò nào?
4. MailMessageReceiver biến email thành WebServiceMessage và dispatch ra sao?
5. Khác biệt giữa PollingMonitoringStrategy và ImapIdleMonitoringStrategy là gì?
6. Vì sao POP3 có strategy polling riêng?
7. Ý nghĩa của deleteMessages và rủi ro khi xóa thư không đồng bộ business transaction là gì?
8. Tại sao receiveSleepTime của client mail cần tương thích với polling interval server?
9. mailto URI khác storeUri và transportUri thế nào?
10. Vì sao SMTP accepted không có nghĩa endpoint đã xử lý nghiệp vụ?
11. JID gồm những thành phần nào và vì sao không đồng nhất với email address?
12. Vai trò của XmppMessageSender và XmppMessageReceiver khác nhau thế nào?
13. Vì sao XmppMessageSender mặc định không có receive timeout hữu hạn có thể gây giữ thread?
14. Điều kiện domain của JID khi dùng out-of-band XMPP replies là gì?
15. Presence khác application acknowledgement ở điểm nào?
16. Vì sao sender và receiver có thể dùng cùng MessageDispatcher nhưng transport security vẫn khác?
17. Spring Integration XMPP channel adapter khác Spring-WS XMPP message sender thế nào?
18. Tại sao email attachment không tự động đồng nghĩa với SOAP MTOM/XOP?
19. Làm thế nào tránh SSRF/routing abuse qua WS-Addressing ReplyTo/FaultTo?
20. Vì sao timeout email/XMPP không chứng minh server chưa commit nghiệp vụ?
21. Cần idempotency và receipt như thế nào để retry an toàn?
22. Khi nào nên dùng HTTP/JMS/broker thay email hoặc XMPP?

## 18. Bài tập thực hành

**Bối cảnh:** Một đối tác gửi lệnh xuất hóa đơn qua email SOAP. Hệ thống nội bộ cần phát thông báo trạng thái qua XMPP. Cả hai transport sử dụng cùng business XSD/WSDL và phải phục hồi khi server offline hoặc message bị gửi trùng.

### Phần A — Hợp đồng

1. Thiết kế XSD cho SubmitInvoiceRequest gồm requestId, partnerId, invoice data và SubmitInvoiceResponse gồm receiptId, status.
2. Công bố WSDL operation và các business Fault; xác định message correlation metadata.
3. Xác định mailbox request/response, XMPP JID, timeout, retry window và destination allowlist.

### Phần B — Email transport

4. Cấu hình SaajSoapMessageFactory, MailMessageSender và WebServiceTemplate.
5. Cấu hình server MailMessageReceiver với IMAP mailbox, SMTP response và PollingMonitoringStrategy.
6. Thử đổi sang ImapIdleMonitoringStrategy nếu server hỗ trợ, đo độ trễ và tài nguyên.
7. Gửi email chứa SOAP request, kiểm tra response mail và đối chiếu requestId.
8. Thử duplicate email, delayed response, mailbox quota, sai credential, MIME malformed và attachment quá lớn.

### Phần C — XMPP transport

9. Tạo Smack connection bằng XmppConnectionFactoryBean, bảo đảm TLS và credentials từ secret store.
10. Cấu hình XmppMessageReceiver với message factory/dispatcher.
11. Cấu hình client XmppMessageSender với JID destination và timeout hữu hạn.
12. Kiểm tra request/response, JID domain mismatch, XMPP server offline, reconnect và reply tới destination ngoài allowlist.
13. Chứng minh presence online không thay thế receipt/business acknowledgement.

### Phần D — Reliability, security và quan sát

14. Dùng database unique constraint để dedup theo partner + requestId.
15. Dùng outbox để phát trạng thái hóa đơn qua XMPP sau khi invoice transaction commit.
16. Test WS-Security invalid token, bad signature, timestamp/replay, TLS certificate failure.
17. Test Fault khi lỗi schema/business và phân biệt với transport errors.
18. Ghi metrics cho mailbox pending/poll latency, XMPP reconnect, transport receive timeout, business duplicate và operation outcomes.
19. Viết runbook khi SMTP fail, IMAP folder không hoạt động, XMPP connection mất hoặc response đến muộn.

**Tiêu chí đạt:** cùng contract SOAP hoạt động qua email và XMPP; endpoint không phụ thuộc transport; response có thể đến trễ nhưng request không gây side effect trùng; reply destination an toàn; dữ liệu/credentials được bảo vệ; monitoring phân biệt transport delivery với business completion.

## 19. Tài liệu tham khảo chính thức

- [Spring Web Services Reference 4.1.4 — Transports](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/): email transport, XMPP transport, out-of-band replies và WebServiceTemplate.
- [MailMessageSender API 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/transport/mail/MailMessageSender.html): mailto URI, SMTP/POP3/IMAP, receive sleep time.
- [MailMessageReceiver API 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/transport/mail/MailMessageReceiver.html): receiver lifecycle, Jakarta Mail session, monitoring strategy và transport/store URI.
- [PollingMonitoringStrategy API 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/transport/mail/monitor/PollingMonitoringStrategy.html): polling interval và behavior.
- [XmppMessageSender API 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/transport/xmpp/XmppMessageSender.html): XMPP connection, JID URI, encoding và receive timeout.
- [XmppMessageReceiver API 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/transport/xmpp/XmppMessageReceiver.html): server-side receiver và lifecycle.
- [Spring Integration XMPP Support](https://docs.spring.io/spring-integration/reference/xmpp.html): inbound/outbound channel adapters, presence, message headers và XMPP extensions.
- [Spring Integration Mail Support](https://docs.spring.io/spring-integration/reference/mail.html): mail inbound/outbound channel adapters và message-driven integration flows.

Các API Spring-WS trên là tham chiếu cho **release 4.1.4**; project dùng version khác cần đọc đúng Javadoc, dependency management, Jakarta Mail/Smack generation và test trên runtime thật.

## 20. Tổng kết

**Email và XMPP là các transport mở rộng có triển khai trực tiếp trong Spring Web Services.** Email dùng MailMessageSender/MailMessageReceiver với SMTP và POP3/IMAP; XMPP dùng XmppMessageSender/XmppMessageReceiver dựa trên Smack và địa chỉ JID. Hai transport cùng có thể đưa SOAP WebServiceMessage tới MessageDispatcher và xử lý endpoint contract-first, nhưng khác nhau về địa chỉ, kết nối, receive behavior, reply routing, timeout và vận hành.

Trong tích hợp doanh nghiệp, hãy giữ **XSD/WSDL và business endpoint ổn định**, đồng thời xác định rõ transport conventions, request correlation, receipt, idempotency, security, destination allowlist, attachment limits, error handling và recovery. Email delivery, XMPP stanza delivery và business transaction commit là những trạng thái riêng; không thể coi chúng là một giao dịch nguyên tử.

**Ghi nhớ:** chọn email khi hệ sinh thái mailbox và quy trình trao đổi chậm phù hợp; chọn XMPP khi tổ chức đã có hạ tầng actor/JID và cần message/presence; chọn HTTP/JMS hoặc broker khi semantics của chúng phù hợp hơn. Transport chỉ là đường chuyển message. Một SOAP integration đáng tin cậy vẫn cần hợp đồng ổn định, xác thực đúng, kiểm thử tương thích và cơ chế phục hồi ở tầng nghiệp vụ.
