# Mô phỏng kết nối chậm, lỗi giữa chừng và giới hạn kích thước

Một SOAP integration test cần kiểm tra điều gì xảy ra khi mạng và đối tác không hoạt động theo kịch bản lý tưởng. Partner có thể nhận request nhưng trả response rất chậm; response có thể đến từng chunk rồi dừng giữa chừng; server có thể reset kết nối khi client đang đọc; request hoặc response có thể vượt giới hạn dung lượng; hoặc proxy từ chối body trước khi Spring-WS nhìn thấy SOAP Envelope.

Bài này thuộc chương **Kiểm thử tích hợp** của module **SPRING_WEB_SERVICES**, tập trung mô phỏng **kết nối chậm, lỗi giữa chừng và giới hạn kích thước**. Ta sử dụng WebServiceTemplate làm SOAP client, HTTP mock server như WireMock để tạo network behavior, và embedded Spring-WS server để kiểm các giới hạn ở phía nhận. Bài học kết hợp contract-first XSD/WSDL, JAXB marshalling/unmarshalling, SOAP Fault, HTTP transport, WS-Security và MTOM attachments.

Một MockWebServiceServer của Spring-WS client rất hữu ích để tạo SOAP payload/Fault in-process, nhưng nó không mở HTTP socket. Muốn kiểm read timeout, partial response, connection reset, chunked transfer, TLS hoặc byte limits thực tế, dùng mock HTTP server và chính HTTP message sender mà ứng dụng dùng ở production. WireMock hỗ trợ fixed delays, random delays, chunked dribble và malformed/reset responses. [WireMock: Simulating Faults](https://wiremock.org/docs/simulating-faults/)

## 1. Mục tiêu học tập

1. Phân biệt connection timeout, read timeout, response delay và slow-dribble response.
2. Dựng mock HTTP endpoint để giả lập partner SOAP chậm.
3. Mô phỏng response bị cắt cụt, malformed chunk và connection reset.
4. Kiểm SOAP client xử lý timeout/IO failure mà không tạo business success giả.
5. Đo và kiểm request/response bytes theo giới hạn đã định.
6. Kiểm request body lớn, SOAP XML lớn và MTOM attachments.
7. Phân biệt giới hạn ở client, proxy, servlet container, message factory và application.
8. Kiểm retry/idempotency khi response bị mất sau khi partner đã xử lý request.
9. Dùng test HTTP thật cho transport behavior và mock message tests cho contract behavior.
10. Xây ma trận fault-injection có thể chạy lặp lại, không phụ thuộc timing ngẫu nhiên.

## 2. Bản đồ tầng lỗi trong SOAP integration

~~~mermaid
flowchart TD
    A["SOAP client"] --> B["WebServiceTemplate"]
    B --> C["HTTP message sender"]
    C --> D["TCP/TLS"]
    D --> E["Proxy / gateway"]
    E --> F["Remote servlet container"]
    F --> G["MessageDispatcherServlet"]
    G --> H["SOAP / MIME parser"]
    H --> I["Endpoint + application"]
    I --> J["SOAP response"]
    J --> H
    H --> F
    F --> E
    E --> D
    D --> C
    C --> B
    B --> A
~~~

| Tầng | Ví dụ failure | Công cụ/kiểm thử |
|---|---|---|
| Client configuration | Connect/read timeout sai | HTTP mock + config test |
| HTTP sender | Pool exhausted, acquisition timeout | HTTP mock/load test |
| TCP/TLS | Refused/reset/certificate failure | Local HTTP/HTTPS server |
| Proxy/gateway | 413/502/503/504/idle timeout | Proxy integration |
| Servlet container | Request-size/connector timeout | Embedded server test |
| SOAP/MIME parser | Malformed XML/MIME | SOAP/MIME test |
| Application | Slow operation, Fault sau xử lý | Endpoint test |
| Client mapping | Exception bị map sai | Client façade test |

HTTP error có thể xảy ra trước SOAP parsing và không có SOAP Envelope. SOAP Fault là message-level response hợp lệ, cần phân biệt với transport failure.

## 3. Timeout có nhiều ý nghĩa

| Timeout | Bắt đầu tính từ | Điều nó giới hạn |
|---|---|---|
| DNS/name resolution | Khi resolve host | Tìm địa chỉ |
| Connect timeout | Khi mở TCP | Thiết lập kết nối |
| TLS handshake timeout | Khi thương lượng TLS | Secure channel |
| Pool acquisition timeout | Khi mượn connection | Chờ connection rảnh |
| Write timeout | Khi ghi request | Gửi bytes |
| Read/response timeout | Khi chờ/đọc response | Chờ dữ liệu |
| Proxy upstream timeout | Proxy đợi backend | Gateway chờ upstream |
| Overall operation deadline | Toàn bộ call | Tổng thời gian cho phép |

Partner có thể accept TCP nhanh nhưng không trả byte nào lâu; đó là read timeout, không phải connect timeout. Partner khác trả byte đầu nhanh rồi gửi từng phần rất chậm; tùy HTTP client, read timeout có thể đo idle-read gap thay vì tổng thời gian. Cần mô phỏng cả hai.

## 4. Cấu hình timeout cho WebServiceTemplate

WebServiceTemplate ủy thác HTTP I/O cho WebServiceMessageSender. Cách đặt timeout phụ thuộc sender và HTTP client implementation. Không giả định một setter chung của template điều khiển mọi timeout.

Với Spring Boot version có WebServiceTemplateBuilder và HttpClientSettings, có thể cấu hình connect/read timeout bằng builder:

~~~java
import java.time.Duration;

import org.springframework.boot.http.client.HttpClientSettings;
import org.springframework.boot.webservices.client.WebServiceMessageSenderFactory;
import org.springframework.boot.webservices.client.WebServiceTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.client.core.WebServiceTemplate;

@Configuration(proxyBeanMethods = false)
public class PartnerSoapClientConfiguration {

    @Bean
    WebServiceTemplate partnerWebServiceTemplate(
            WebServiceTemplateBuilder builder) {

        HttpClientSettings settings = HttpClientSettings.defaults()
            .withConnectTimeout(Duration.ofSeconds(2))
            .withReadTimeout(Duration.ofSeconds(4));

        builder.httpMessageSenderFactory(
            WebServiceMessageSenderFactory.http(settings)
        );
        return builder.build();
    }
}
~~~

Package/builder methods phụ thuộc Spring Boot version. Nếu project không có builder API trên, cấu hình sender implementation trực tiếp theo version đang dùng. Kiểm BOM/Javadoc của HTTP sender thật. Spring Boot Web Services reference mô tả builder và việc tùy chỉnh connect/read timeouts: https://docs.spring.io/spring-boot/reference/io/webservices.html

### 4.1. Deadline budget

~~~text
Connect timeout:       2 s
Read timeout:          4 s
Overall partner call:  6 s
Caller request budget: 8 s
Proxy upstream budget: 9 s
~~~

Giá trị chỉ là ví dụ. Tổng budget cần xét pool acquisition, DNS/TLS, retry và serialize response. Hai lần retry với read timeout 4 giây có thể vượt caller budget nếu không quản lý deadline tổng.

### 4.2. Read timeout không phải overall deadline

Một số HTTP clients định nghĩa read timeout là thời gian chờ lần đọc hoặc khoảng không có dữ liệu. Response liên tục gửi chunk nhỏ có thể không kích hoạt idle timeout dù tổng thời gian lâu. Nếu cần giới hạn tổng call, dùng deadline/cancellation policy riêng và kiểm semantics của HTTP client.

## 5. Dựng HTTP fault server bằng WireMock

WireMock chạy như HTTP server thật, nên SOAP client dùng sender production vẫn gửi request qua socket. Có thể khởi chạy WireMock embedded trong JUnit, Testcontainers hoặc test service riêng.

~~~java
import com.github.tomakehurst.wiremock.WireMockServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;

class PartnerTransportTest {
    private WireMockServer wireMock;

    @BeforeEach
    void startServer() {
        wireMock = new WireMockServer(0);
        wireMock.start();
    }

    @AfterEach
    void stopServer() {
        wireMock.stop();
    }

    String partnerUrl() {
        return wireMock.baseUrl() + "/soap/payments";
    }
}
~~~

Port 0 yêu cầu server chọn port trống; test lấy URL thực qua baseUrl(). Test chạy song song cần server/stub state độc lập. Không dùng fixed port dễ va chạm tiến trình khác.

### 5.1. Đưa URL mock vào client configuration

Không thay endpoint production bằng sửa source code. Dùng test property hoặc constructor/configuration override để đưa partner URL sang WireMock. Kiểm request journal để chắc request đến đúng path và HTTP method. Test nên fail fast nếu URI vẫn trỏ tới partner production.

## 6. Mô phỏng partner chậm trước khi trả response

WireMock withFixedDelay(milliseconds) khiến server đợi trước khi gửi response. Đây là cách kiểm read timeout khi peer accept request nhưng response bắt đầu muộn.

~~~java
wireMock.stubFor(post(urlPathEqualTo("/soap/payments"))
    .willReturn(aResponse()
        .withStatus(200)
        .withHeader("Content-Type", "text/xml; charset=utf-8")
        .withBody(validSoapResponse)
        .withFixedDelay(1500)));
~~~

Nếu client read timeout là 300 ms, test mong đợi transport/read timeout. Nếu timeout là 3 giây, response có thể về bình thường. Không dùng Thread.sleep() trong test để đợi request; cấu hình delay ngay ở mock server.

### 6.1. Test hai phía ngưỡng timeout

| Test | WireMock delay | Client read timeout | Kỳ vọng |
|---|---:|---:|---|
| Dưới ngưỡng | 100 ms | 1.000 ms | Nhận response |
| Trên ngưỡng | 1.500 ms | 300 ms | Read timeout |
| Sát ngưỡng | 800 ms | 800 ms | Tránh; dễ phụ thuộc scheduler |
| Timeout tăng | 1.500 ms | 3.000 ms | Nhận response |

Không test sát đúng ranh giới millisecond; CI runner và scheduler làm timing thay đổi. Dùng khoảng cách đủ rộng để test ổn định.

## 7. Mô phỏng response nhỏ giọt theo chunk

Một response có thể bắt đầu đúng hạn nhưng truyền body từng phần rất chậm. WireMock withChunkedDribbleDelay(numberOfChunks, totalDuration) chia body thành nhiều chunks trong khoảng thời gian quy định.

~~~java
wireMock.stubFor(post(urlPathEqualTo("/soap/payments"))
    .willReturn(aResponse()
        .withStatus(200)
        .withHeader("Content-Type", "text/xml; charset=utf-8")
        .withBody(validSoapResponse)
        .withChunkedDribbleDelay(8, 2400)));
~~~

Tám chunks trong 2,4 giây cho phép quan sát read timeout semantics của HTTP sender. Đừng giả định toàn bộ 2,4 giây tính như một lần read timeout. Nếu client reset idle timer mỗi khi bytes đến, response có thể hoàn tất. Nếu application có overall deadline, deadline vẫn phải được enforce riêng.

### 7.1. Assert điều gì?

Đo elapsed duration trong khoảng rộng, kiểm response không được trả thành công sớm và capture exception/cause nếu timeout. Không assert millisecond chính xác. Với low-level socket semantics, dùng HTTP mock server phù hợp và test đúng sender đang dùng ở production.

## 8. Mô phỏng response bị lỗi giữa chừng

Lỗi giữa chừng khác server trả HTTP 500: peer có thể gửi status/header hợp lệ, gửi một phần XML rồi đóng socket. Client có thể nhận truncated response hoặc I/O exception khi parse.

WireMock hỗ trợ các fault modes như malformed response chunk, random data then close, empty response và connection reset:

~~~java
import static com.github.tomakehurst.wiremock.client.Fault.MALFORMED_RESPONSE_CHUNK;

wireMock.stubFor(post(urlPathEqualTo("/soap/payments"))
    .willReturn(aResponse().withFault(MALFORMED_RESPONSE_CHUNK)));
~~~

Hoặc:

~~~java
import static com.github.tomakehurst.wiremock.client.Fault.RANDOM_DATA_THEN_CLOSE;

wireMock.stubFor(post(urlPathEqualTo("/soap/payments"))
    .willReturn(aResponse().withFault(RANDOM_DATA_THEN_CLOSE)));
~~~

Fault modes phụ thuộc OS/network stack. Tài liệu WireMock ghi nhận CONNECTION_RESET_BY_PEER có thể hoạt động khác trên Windows; không dùng nó làm test duy nhất. Ưu tiên malformed/truncated response portable và đánh dấu reset test theo platform.

### 8.1. Assert điều gì?

- Client không trả success object với fields mặc định.
- Lỗi được phân loại là transport/protocol response failure phù hợp.
- Không retry không giới hạn.
- HTTP connection và response stream được giải phóng.
- Correlation ID/operation metadata có trong diagnostic logs.
- Không log SOAP payload nhạy cảm hoặc WS-Security Header.

Exception cụ thể khác nhau giữa URLConnection, Apache HttpClient và JDK HttpClient. Assert exception category/cause semantics thay vì hard-code implementation exception khi project chưa cam kết sender đó.

## 9. Phân biệt HTTP error response với truncated response

| Kịch bản | HTTP headers | Body | Kết quả client thường gặp |
|---|---|---|---|
| SOAP Sender Fault | Có thể HTTP 500 | SOAP Fault đầy đủ | SoapFaultClientException |
| Gateway 502 | HTTP 502 | HTML/JSON | HTTP/transport error |
| Empty response | Có thể status 200 | Rỗng | Empty/malformed response |
| Truncated SOAP | Status/header hợp lệ | XML chưa đóng | I/O/XML parse error |
| Reset trước headers | Không có response | Không có | Connection exception |
| Read timeout | Chưa có response hoàn chỉnh | Có thể một phần | Read timeout/I/O error |

Không ánh xạ tất cả vào PaymentRejected. SOAP Sender Fault biểu thị remote endpoint trả message-level Fault; connection reset có thể khiến outcome chưa biết.

## 10. Giả lập lỗi khi request đang được gửi

Một số lỗi xảy ra trong giai đoạn client upload body: server đọc một phần request rồi đóng connection, hoặc proxy từ chối sau khi đọc header/body limit. Điều này quan trọng với SOAP/MTOM lớn vì marshalling có thể đã tạo body dài.

Các kịch bản cần có:

1. Server accept connection rồi đóng trước khi đọc body.
2. Server đọc một phần body rồi đóng.
3. Server đọc hết request nhưng đóng trước response.
4. Server trả HTTP 413 khi body vượt ngưỡng.
5. Proxy timeout khi upload chậm.
6. Client write timeout hoặc connection reset khi stream request.

WireMock fault simulation chủ yếu hữu ích cho HTTP stub behavior. Để kiểm chính xác partial request consumption, viết local socket/HTTP test server hoặc dùng fault proxy có thể điều khiển inbound stream. Malformed response chunk không mô phỏng mọi dạng client upload failure.

### 10.1. Phân biệt upload chưa hết và server đã commit

Nếu peer ngắt sau khi đọc đủ request, nó có thể đã xử lý/commit nghiệp vụ trước khi response bị mất. Client không thể kết luận transaction chưa chạy chỉ dựa IOException. Dùng idempotency key/requestId và status reconciliation.

## 11. Giới hạn kích thước có nhiều lớp

Một SOAP message có thể bị giới hạn ở nhiều thành phần:

~~~mermaid
flowchart LR
    A["Client body generation"] --> B["Client sender/stream"]
    B --> C["Proxy request limit"]
    C --> D["HTTP connector limit"]
    D --> E["SOAP/MIME parser limit"]
    E --> F["Application quota"]
~~~

| Vị trí | Dữ liệu đo | Mục đích |
|---|---|---|
| Client marshalling | XML bytes tạo ra | Tránh tạo request quá lớn |
| Client attachment source | Raw file/stream bytes | Quota trước upload |
| Proxy/gateway | HTTP body bytes | Chặn oversized request ở edge |
| Servlet connector | Request bytes/buffering | Bảo vệ server resources |
| SOAP/MIME parser | Envelope + MIME part sizes | Giới hạn XML/MIME processing |
| Application | Document/business size | Business quota |
| Client response reader | Response bytes | Chặn partner response quá lớn |
| Temp storage | Attachment/temp file bytes | Tránh disk exhaustion |

Giới hạn tại proxy có thể trả HTTP 413 trước khi SOAP Dispatcher chạy. Giới hạn trong application có thể trả SOAP Sender/Client Fault nếu Envelope đã parse đủ. Cần xác định layer chịu trách nhiệm và response mong đợi.

## 12. Kiểm request body size phía client

Khi client marshal object thành SOAP XML hoặc gửi MTOM, đo kích thước bytes thực tế, không phải số ký tự Java String. UTF-8 có thể dùng nhiều bytes cho một ký tự; MIME boundary, headers và SOAP Envelope cũng làm tổng body lớn hơn payload text.

Với mock HTTP server, kiểm recorded request body. Pseudocode:

~~~java
// Pseudocode: RecordedRequest thuộc mock server cụ thể,
// không phải Spring-WS API chung.
RecordedRequest recorded = mockServer.takeRequest();
byte[] requestBytes = recorded.getBody().readByteArray();

assertTrue(requestBytes.length <= configuredMaxRequestBytes);
~~~

Đối chiếu byte length với limit và xác minh Content-Length/chunked behavior. Nếu body streamed, không buffer vô hạn chỉ để đo; dùng bounded counting stream hoặc server-side byte counter.

### 12.1. Kiểm oversized request bị từ chối

Một server nhận SOAP request nên có acceptance boundary rõ: kích thước tối đa và status/Fault khi vượt ngưỡng. Test gửi:

- Body nhỏ hơn limit: endpoint được gọi.
- Body đúng limit: behavior theo quy định inclusive/exclusive.
- Body lớn hơn limit 1 byte: bị reject.
- Chunked body không khai Content-Length: vẫn enforce actual bytes.
- Multipart MTOM có attachment vượt per-part limit.
- Tổng attachments vượt total quota.

Đừng chỉ kiểm Content-Length header; client có thể dùng chunked transfer hoặc header không đáng tin.

## 13. Kiểm request limit trên embedded Spring-WS server

Để kiểm giới hạn thật, chạy Spring Boot embedded server ở random port và gửi HTTP SOAP POST lớn. Không dùng MockWebServiceClient cho test này vì nó bỏ qua socket/connector.

Test fixture phải biết giới hạn đặt ở đâu: reverse proxy, server connector, filter, multipart resolver, SOAP message factory hay application. Một assertion đúng có thể là HTTP 413 từ connector/proxy; nếu application parse được Envelope thì có thể trả SOAP Fault theo contract. Đừng giả định mọi layer đều trả cùng response.

### 13.1. Đếm side effect

Ngoài status, dùng spy/counter hoặc repository fixture để xác nhận oversized request không vào business service và không ghi dữ liệu. Nếu connector/proxy chặn trước servlet, endpoint invocation count phải bằng zero. Nếu application từ chối sau parse, transaction không được commit.

### 13.2. Chunked body

Gửi chunked request không có Content-Length tường minh để xác minh byte-limit thực tế. Một implementation chỉ check Content-Length có thể bị bypass. Dùng HTTP client hỗ trợ streaming/chunked và server thật; mock transport không chứng minh framing behavior.

## 14. Giới hạn SOAP XML và parser resources

HTTP body size không phải giới hạn duy nhất. Một XML nhỏ theo bytes có thể lồng rất sâu hoặc có nhiều elements/attributes; do đó cần giới hạn depth/node count/parser complexity theo XML stack và threat model.

Kiểm:

- Max Envelope size.
- Max element depth.
- Max attributes/nodes/text length.
- DTD/external entities disabled.
- XSD import/include catalog allowlist.
- Processing time và parser memory.
- SOAP Header count/size.
- Không parse cùng body nhiều lần không cần thiết.

Một Envelope dưới HTTP body limit vẫn có thể gây memory/CPU pressure nếu cấu trúc XML cực đoan. Test XML depth/node limits riêng với security/contract validation.

## 15. MTOM: giới hạn part và tổng attachment

MTOM truyền binary qua multipart/related, SOAP Body tham chiếu binary bằng xop:Include và Content-ID. Các giới hạn cần phân biệt:

- SOAP Envelope bytes.
- Số MIME parts.
- Kích thước từng part.
- Tổng kích thước attachments.
- MIME header/Content-ID length.
- Temp disk bytes và thời gian giữ file.
- Số uploads đồng thời.

Kiểm Content-ID thiếu/trùng, XOP reference không tìm thấy part, attachment vượt per-part limit và nhiều parts vượt tổng quota. Nếu WS-Security ký attachments, xác minh đúng profile/bytes; không chỉ assert Body có XOP element.

### 15.1. Không biến large attachment thành byte[] mặc định

Buffer toàn bộ binary vào heap có thể tăng allocation/GC và gây OOM dưới concurrency. Nếu contract/workload cần file lớn, dùng streaming hoặc bounded temporary storage và kiểm cleanup sau success, Fault, timeout, disconnect và shutdown.

## 16. Giới hạn response body phía client

Partner có thể trả response XML/MTOM quá lớn dù request nhỏ. SOAP client cần policy giới hạn response bytes/attachment total. Nhiều HTTP sender không có một property chung bao phủ toàn bytes sau khi nhận; kiểm khả năng của HTTP client, bounded stream wrapper hoặc custom message sender/receiver.

Test response dưới limit thành công, response vượt limit bị từ chối trước khi JAXB unmarshalling tạo graph quá lớn. Với MTOM, tính cả MIME parts chứ không chỉ SOAP Body. Nếu HTTP client buffer toàn response trước khi ứng dụng thấy message, giới hạn phải đặt đủ sớm ở transport layer.

## 17. Fault injection với WireMock

Một test có thể đổi stub behavior để mô phỏng HTTP error:

~~~java
wireMock.stubFor(post(urlPathEqualTo("/soap/payments"))
    .willReturn(aResponse()
        .withStatus(504)
        .withHeader("Content-Type", "text/plain")
        .withBody("upstream timeout")));
~~~

Slow response:

~~~java
wireMock.stubFor(post(urlPathEqualTo("/soap/payments"))
    .willReturn(aResponse()
        .withStatus(200)
        .withHeader("Content-Type", "text/xml")
        .withBody(validSoapResponse)
        .withFixedDelay(1800)));
~~~

Partial/corrupt response:

~~~java
wireMock.stubFor(post(urlPathEqualTo("/soap/payments"))
    .willReturn(aResponse()
        .withFault(Fault.MALFORMED_RESPONSE_CHUNK)));
~~~

Đây là các scenario riêng. Không đăng ký stub chồng chéo mà không reset state. Dùng scenario names hoặc reset mappings giữa tests, kiểm request journal để biết call đã tới mock server chưa.

## 18. Test cùng HTTP sender production

Một fault test chỉ có giá trị nếu dùng cùng loại HTTP sender, pool configuration, TLS settings và timeout policy như production. Nếu test dùng URLConnection nhưng production dùng Apache HttpClient/JDK HttpClient, exception, timeout semantics, pooling và connection reuse có thể khác.

Tạo template qua cùng configuration factory/bean, chỉ override URI sang mock host. Không mock WebServiceMessageSender nếu mục tiêu là transport fault. Mock message layer và real HTTP layer là hai cấp test khác nhau.

## 19. Retry, circuit breaker và idempotency

Slow/partial response có thể khiến outcome không rõ. Nếu client gửi payment, partner commit thành công rồi response bị reset, retry lần hai có thể double charge nếu server không idempotent.

| Failure | Retry? | Điều kiện |
|---|---|---|
| Connect refused trước khi gửi | Có thể | Retry budget, partner availability |
| Read timeout sau khi gửi | Không retry mù | Idempotency key và reconcile |
| Truncated response | Không retry mù | Unknown outcome |
| HTTP 429/503 | Có thể | Retry-After/backoff/idempotency |
| SOAP Sender/Client Fault | Thường không | Request cần sửa |
| SOAP Receiver Fault | Tùy | Fault code và partner policy |
| TLS certificate invalid | Không retry liên tục | Sửa trust/config |
| Request/response quá lớn | Không retry nguyên trạng | Thay payload/contract |

Circuit breaker giúp ngừng gửi khi partner fail liên tục; nó không thay timeout hoặc idempotency. Retry cần tổng deadline, exponential backoff, jitter, max attempts và phân loại lỗi.

## 20. Logging và đo đạc fault tests

~~~text
partner=payments-partner
operation=SubmitPayment
scenario=partial-response
connectTimeoutMs=500
readTimeoutMs=800
requestBytes=20480
responseBytesRead=1024
elapsedMs=812
outcome=TRANSPORT_FAILURE
correlationId=test-corr-001
~~~

Không log raw SOAP Envelope, UsernameToken, PasswordText, WS-Security signatures/private keys, payment details hoặc attachment bytes. Trong test, payload fixtures synthetic và logs có thể kiểm nội dung redacted.

Metrics nên có timeout counts theo connect/read/pool, reset/truncated response count, 413 count, request/response bytes, MTOM part counts, upload duration, active connections và client pool saturation.

## 21. Determinism: làm fault test ổn định trên CI

- Fixed delay có khoảng cách rộng so với timeout assertion.
- Tránh test đúng bằng timeout boundary.
- Dùng port tự chọn và teardown server trong finally/AfterEach.
- Không dùng Thread.sleep để đồng bộ test.
- Dùng bounded test-level timeout lớn hơn client timeout.
- Reset stub mappings/request journal giữa scenario.
- Phân loại OS-sensitive reset tests.
- Dùng isolated fixture nếu test chạy song song.
- Lặp test để phát hiện resource leakage.

WireMock ghi nhận CONNECTION_RESET_BY_PEER có thể hoạt động khác trên Windows; ưu tiên malformed chunk portable và tách reset test theo platform. https://wiremock.org/docs/simulating-faults/

## 22. Bộ kiểm thử tích hợp trên embedded server

Một test server thật cần kiểm:

1. HTTP request dưới size limit đi tới SOAP endpoint.
2. Request vượt limit bị reject trước business side effect.
3. Chunked body vượt limit vẫn bị chặn theo actual bytes.
4. Malformed XML không tới business operation.
5. MTOM attachment vượt per-part/aggregate limit bị từ chối.
6. Slow upload được giới hạn theo policy phù hợp.
7. Proxy 413/504 được phân loại là transport error, không parse thành SOAP Fault.
8. SOAP Fault hợp lệ vẫn được parse khi Envelope đúng.
9. Connection disconnect không để lại partial database transaction.
10. Temp attachment files được cleanup ở success/failure.
11. Health/readiness/shutdown không làm request treo vô hạn.

Dùng random-port embedded server và HTTP thật. Nếu production đi qua ingress, ít nhất một test environment cần chạy qua proxy/config gần production; embedded-only test không chứng minh edge policies.

## 23. Test matrix: slow network, midstream failure và size limits

| ID | Fault scenario | Layer | Expected result |
|---|---|---|---|
| N01 | Delay dưới read timeout | HTTP client | Success |
| N02 | Delay trên read timeout | HTTP client | Read timeout |
| N03 | Response dribble từng chunk | HTTP client | Theo read/overall deadline |
| N04 | HTTP 504 | Gateway/client | Communication error |
| N05 | Empty HTTP response | HTTP/message parser | Empty/truncated error |
| N06 | Malformed response chunk | TCP/HTTP | I/O/protocol error |
| N07 | Reset trước response headers | TCP | Connection error |
| N08 | Close sau một phần XML | HTTP/XML | Truncated response, no success |
| N09 | Server nhận request nhưng không trả lời | Application/HTTP | Timeout, unknown outcome |
| N10 | Client write chậm bị server đóng | Upload/network | Write/connection error |
| S01 | Request dưới max bytes | Server/proxy | Accept |
| S02 | Request đúng ngưỡng | Size policy | Policy-defined boundary |
| S03 | Request vượt max một byte | Server/proxy | Reject |
| S04 | Chunked request vượt max | Connector/application | Reject theo actual bytes |
| S05 | SOAP XML vượt Envelope limit | Parser | Reject trước business |
| S06 | XML depth/node vượt limit | Parser | Reject an toàn |
| S07 | MIME part vượt per-part max | MIME layer | Reject |
| S08 | Tổng MTOM parts vượt quota | MIME/application | Reject |
| S09 | Body nhỏ, attachment lớn | MIME layer | Reject |
| S10 | Partner response vượt max bytes | Client transport | Abort/fail safely |
| S11 | MTOM response vượt aggregate limit | Client MIME | Reject |
| R01 | Partner commit rồi response reset | Business/retry | Unknown outcome, reconcile |
| R02 | Retry cùng requestId | Idempotency | Không duplicate |
| R03 | Retry vượt deadline budget | Resilience | Stop retry |
| R04 | Repeated delay/failure | Circuit breaker | Open/half-open theo policy |
| C01 | Partial upload rồi disconnect | Server/application | Không commit partial document |
| C02 | Temp file còn sau failure | Storage | Cleanup/recovery |
| C03 | Request size rejected | Endpoint | Business invocation count = 0 |
| C04 | SOAP Fault body hợp lệ | SOAP client | Map SoapFaultClientException |
| C05 | HTTP error body là HTML | SOAP client | Không coi là SOAP Fault |

## 24. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
|---|---|---|
| Delay test không timeout | Sender read timeout khác config test | Inspect effective sender/client |
| Test thành connect timeout | Mock server chưa start hoặc connect budget thấp | Assert server started/port |
| Dribble response vẫn success | Read timeout là idle-read timeout | Kiểm overall deadline |
| Reset test treo Windows | OS socket reset behavior | Dùng malformed chunk portable |
| Exception khác dự kiến | HTTP sender khác nhau | Inspect cause chain |
| Request-size test không trả 413 | Limit ở layer khác/app trả Fault | Xác định enforcement layer |
| Chunked request bypass limit | Chỉ check Content-Length | Đếm actual bytes |
| MTOM upload OOM | Buffering/byte[]/raw logging | Streaming/storage quotas |
| Response quá lớn vào JAXB | Limit đặt quá muộn | Enforce trước unmarshal |
| Retry tạo duplicate | Outcome unknown, thiếu idempotency | requestId/reconcile |
| SOAP Fault thành transport error | Proxy rewrite hoặc Content-Type | Kiểm Envelope/headers |
| HTTP 500 HTML bị map thành Fault | Mapper quá rộng | Kiểm body và Fault resolver |
| Temp files leak | Cleanup chỉ ở happy path | Test Fault/reset/shutdown |
| Test flaky | Timing sát threshold/shared port | Margin/dynamic port/lifecycle |

## 25. Bài thực hành: mô phỏng partner thanh toán không ổn định

**Bối cảnh:** Spring-WS client gửi SubmitPayment qua HTTPS tới partner. Request gồm requestId, account, amount và có thể attachment. Client dùng WebServiceTemplate với connect/read timeouts. Partner đôi lúc trả response chậm, đôi lúc commit xong rồi connection reset. Gateway giới hạn 2 MiB cho HTTP request; mỗi attachment tối đa 1 MiB.

### Nhiệm vụ

1. Cấu hình WebServiceTemplate theo HTTP sender production.
2. Đặt connect/read timeout và tổng deadline.
3. Dựng WireMock local server trên dynamic port.
4. Test delay 100 ms trả response thành công.
5. Test delay dài hơn read timeout và assert communication timeout.
6. Test chunked dribble để xác định read-timeout semantics.
7. Test malformed response chunk và partial SOAP XML.
8. Test empty response, HTTP 504 và HTML error response.
9. Test request body dưới 2 MiB, đúng ngưỡng và vượt ngưỡng.
10. Test chunked transfer vượt limit không có Content-Length.
11. Test MTOM một attachment dưới 1 MiB, đúng ngưỡng và quá ngưỡng.
12. Test tổng nhiều attachments vượt quota nếu contract có nhiều parts.
13. Test SOAP XML depth/node limit.
14. Dùng embedded server thật xác minh request lớn không vào business service.
15. Dùng partner simulator mô phỏng commit rồi reset response.
16. Retry với requestId cũ và xác nhận không có payment duplicate.
17. Xác minh timeout/partial response không tạo default success object.
18. Kiểm temp files/streams cleanup ở mọi failure branch.
19. Đảm bảo logs không chứa credentials/token/payment payload.
20. Chạy suite trên CI và đánh dấu reset-by-peer test theo platform nếu cần.

### Câu hỏi tự kiểm tra

1. Connect timeout khác read timeout thế nào?
2. Tại sao response dribble có thể không kích hoạt idle read timeout?
3. Fixed delay phù hợp test trường hợp nào?
4. Chunked dribble kiểm behavior nào?
5. Malformed response chunk khác HTTP 500 SOAP Fault thế nào?
6. Vì sao MockWebServiceServer không chứng minh socket reset?
7. Request size nên đo bằng ký tự hay bytes?
8. Vì sao không chỉ tin Content-Length?
9. Proxy trả 413 có cần SOAP Envelope không?
10. SOAP parser limit khác HTTP body limit ra sao?
11. MTOM có per-part và aggregate limits nào?
12. Vì sao response limit cần đặt trước unmarshalling?
13. Timeout sau SubmitPayment có chứng minh partner chưa commit?
14. Retry idempotent nên giữ hay đổi requestId?
15. Vì sao test tránh đúng timeout boundary?
16. Reset test có thể khác trên Windows vì sao?
17. SOAP Fault khác transport failure ra sao?
18. Khi nào cần test qua ingress thay vì embedded server?
19. Làm sao chứng minh oversized request không có business side effect?
20. Vì sao không buffer attachment lớn vào heap mặc định?

### Đáp án tham khảo

| Câu | Đáp án |
|---|---|
| 1 | Connect giới hạn mở kết nối; read giới hạn chờ/đọc response theo semantics sender. |
| 2 | Bytes đến liên tục có thể reset idle timer dù tổng response kéo dài. |
| 3 | Server accept request nhưng trì hoãn byte response đầu tiên. |
| 4 | Response body gửi từng chunk theo thời lượng. |
| 5 | SOAP Fault là Envelope hợp lệ; malformed chunk không tạo message hoàn chỉnh. |
| 6 | MockWebServiceServer dispatch in-process, không có TCP socket. |
| 7 | Bytes thực tế của encoding/stream. |
| 8 | Chunked transfer/header giả có thể không phản ánh bytes thực. |
| 9 | Không; proxy có thể chặn trước SOAP parsing. |
| 10 | HTTP limit chặn tổng body; XML limit chặn cấu trúc/complexity. |
| 11 | Part count, per-part size, total size, headers và temp storage. |
| 12 | Tránh JAXB/DOM materialize dữ liệu quá lớn vào memory. |
| 13 | Không; partner có thể commit rồi mất response. |
| 14 | Giữ cùng key cho cùng business operation. |
| 15 | Scheduler/CI timing làm outcome flaky ở ranh giới. |
| 16 | Socket reset/linger behavior của OS khác nhau. |
| 17 | Fault là SOAP message; transport failure là lỗi truyền/nhận. |
| 18 | Khi kiểm routing, forwarded headers, edge limits, proxy timeout/TLS. |
| 19 | Assert endpoint invocation count bằng zero và DB không commit. |
| 20 | Tránh heap pressure, GC pauses và OOM dưới concurrency. |

## 26. Checklist trước production

- [ ] Connect, pool-acquisition, read/write và overall deadline được phân biệt.
- [ ] HTTP sender test là sender đang dùng ở production.
- [ ] Fixed delay test dưới/trên ngưỡng có margin ổn định.
- [ ] Chunked dribble test xác minh timeout semantics.
- [ ] Partial/truncated/malformed response xử lý an toàn.
- [ ] HTTP 413/502/503/504 không bị coi nhầm là SOAP Fault.
- [ ] Request max bytes enforce với Content-Length và chunked stream.
- [ ] Response max bytes enforce trước JAXB unmarshalling.
- [ ] XML Envelope size/depth/node limits phù hợp threat model.
- [ ] MIME per-part/aggregate/count/header limits được cấu hình.
- [ ] MTOM streaming/temp storage có quota và cleanup.
- [ ] Oversized/malformed request không tạo business side effects.
- [ ] Transport failure sau gửi request được xem là unknown outcome khi cần.
- [ ] Retry có max attempts, backoff/jitter, deadline và idempotency key.
- [ ] Circuit breaker không che lỗi contract permanent.
- [ ] Mock HTTP server dùng cùng HTTP sender configuration production.
- [ ] Embedded server và ingress/proxy có integration tests riêng.
- [ ] Reset-by-peer test xét khác biệt Windows/Unix.
- [ ] Logs/metrics chỉ chứa metadata an toàn, không raw SOAP/token/attachment.
- [ ] Fault suite deterministic, dynamic port và teardown ổn định.
- [ ] Temp files/connections/streams đóng trong cả success/failure.
- [ ] Partner/contract versions có fixture interoperability.

## 27. Tổng kết

Kiểm thử tích hợp SOAP cần chủ động tạo điều kiện mạng và payload xấu mà partner thật khó tái hiện đúng lúc. **Fixed delay** mô phỏng response bắt đầu muộn; **chunked dribble** mô phỏng dữ liệu đến từng phần; **malformed/truncated/reset faults** mô phỏng response hỏng hoặc kết nối dừng giữa chừng. Những thử nghiệm này cần dùng HTTP mock server và cùng loại HTTP message sender như production để quan sát đúng timeout, exception và connection lifecycle.

Giới hạn dung lượng phải được thực thi ở nhiều lớp: client request generation, proxy, servlet connector, SOAP/MIME parser, application quota và client response reader. Đo bytes thực, không chỉ ký tự hoặc Content-Length; kiểm chunked transfer, SOAP XML complexity và MTOM per-part/aggregate limits. HTTP 413 ở proxy có thể xảy ra trước SOAP Envelope, còn response Fault hợp lệ cần map theo SOAP contract.

Cuối cùng, lỗi sau khi gửi request có thể để lại **unknown outcome**. Đừng retry mù payment/document submission chỉ vì response bị timeout/reset. Giữ idempotency key, reconcile trạng thái và kiểm không có partial side effects. Kết hợp WireMock fault injection, embedded-server size tests, proxy tests và observability metadata-only giúp dịch vụ Spring Web Services chịu latency, disconnect và dữ liệu lớn mà vẫn bảo vệ tính đúng đắn nghiệp vụ.

## Tài liệu tham khảo

- [Spring Boot — Web Services: WebServiceTemplateBuilder and HTTP client timeouts](https://docs.spring.io/spring-boot/reference/io/webservices.html)
- [Spring Web Services — Reference Documentation](https://docs.spring.io/spring-ws/docs/current/reference/html/)
- [WireMock — Simulating Faults](https://wiremock.org/docs/simulating-faults/)
- [Spring Framework — Testing Client Applications and mock web servers](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html)
