# Thời hạn kết nối, đọc phản hồi và ngân sách thời gian toàn lời gọi

## 1. Tại sao timeout là một phần của thiết kế SOAP client?

Trong module **SPRING_WEB_SERVICES**, hệ thống được xây dựng theo hướng **contract-first**: XSD/WSDL định nghĩa thông điệp và giao diện, Spring Web Services (Spring-WS) cung cấp endpoint và SOAP client, JAXB/OXM thực hiện ánh xạ Java–XML, còn SOAP Fault, interceptor, XML security, WS-Security và chứng chỉ giúp tích hợp hệ thống doanh nghiệp an toàn.

Dù SOAP payload tuân thủ XSD và Java code gọi `marshalSendAndReceive` chính xác, một lời gọi vẫn có thể **treo quá lâu** vì mạng không kết nối được, máy chủ nhận nhưng không phản hồi, connection pool cạn, handshake TLS chậm, hoặc client tự retry nhiều lần.

Một cấu hình kiểu:

~~~java
sender.setConnectionTimeout(Duration.ofSeconds(3));
sender.setReadTimeout(Duration.ofSeconds(5));
~~~

**không tự có nghĩa** toàn bộ lời gọi SOAP sẽ hoàn thành trong 8 giây. Có thể tồn tại nhiều bước khác chưa được giới hạn, hoặc các timeout được áp dụng lại cho mỗi kết nối, mỗi lần đọc, mỗi attempt.

Vì vậy cần phân biệt ba quyết định:

1. **Thời hạn kết nối**: client sẵn sàng chờ để thiết lập kết nối mạng trong bao lâu?
2. **Thời hạn đọc phản hồi**: khi đã kết nối, client chịu chờ dữ liệu phản hồi trong bao lâu?
3. **Ngân sách thời gian toàn lời gọi**: từ lúc ứng dụng bắt đầu operation đến lúc nhận kết quả hoặc lỗi cuối cùng, bao nhiêu thời gian được phép tiêu thụ?

Bài thuộc chương **HTTP và kết nối** và tập trung vào chủ đề **Thời hạn kết nối, đọc phản hồi và ngân sách thời gian toàn lời gọi** của một SOAP client Spring-WS.

### Sau bài học, bạn có thể

- Phân biệt connect timeout, pool acquisition timeout, response/read timeout và overall deadline.
- Mô hình hóa các pha DNS → pool → TCP → TLS → upload → server → download → JAXB.
- Cấu hình message sender của `WebServiceTemplate` mà không nhầm sang JAXB/SOAPAction.
- Hiểu tại sao các timeout riêng lẻ không tạo ra giới hạn tổng một cách tự động.
- Thiết kế deadline xuyên suốt retry và các dịch vụ phía sau.
- Tránh retry không an toàn với SOAP operations có side effect.
- Kiểm thử timeout, SOAP Fault, response chậm, lỗi TLS và sự cố connection pool.
- Chọn chỉ số vận hành cho dịch vụ SOAP doanh nghiệp.

## 2. Một lời gọi marshalSendAndReceive thực sự trải qua những bước nào?

Ví dụ ứng dụng gọi dịch vụ đối tác:

~~~java
GetOrderResponseType response =
    partnerOrderClient.getOrder("ORD-2048");
~~~

Bên trong adapter, Spring-WS có thể thực hiện:

~~~java
Object result = template.marshalSendAndReceive(
    "https://partner.example.test/ws/orders",
    requestRoot,
    new SoapActionCallback(
        "urn:example:orders:action:GetOrder"
    )
);
~~~

Các bước có thể bao gồm:

~~~mermaid
flowchart TD
    A["Bắt đầu operation"] --> B["Tạo JAXB request và SOAP Envelope"]
    B --> C["SOAP callback / ClientInterceptor"]
    C --> D["Chờ lấy kết nối từ pool (nếu dùng pool)"]
    D --> E["DNS / route / proxy"]
    E --> F["TCP connect"]
    F --> G["TLS handshake / xác minh chứng chỉ"]
    G --> H["Gửi HTTP headers và SOAP body"]
    H --> I["Server xử lý / truy vấn / gọi downstream"]
    I --> J["Chờ headers và đọc SOAP response"]
    J --> K["SOAP Fault / WS-Security verification"]
    K --> L["JAXB unmarshal / domain mapping"]
    L --> M["Hoàn thành operation"]
~~~

Trong thực tế, việc tạo request/response stream, TLS và callback có thể xen kẽ hoặc lười thực thi (lazy) tùy HTTP client/message factory. Sơ đồ chỉ mô tả **những khoản thời gian cần tính vào ngân sách**, không khẳng định mọi thư viện triển khai cùng một thứ tự cứng nhắc.

### 2.1. Đừng giới hạn chỉ đoạn HTTP

Nếu đo từ lúc đặt `HttpClient.execute(...)` đến lúc nhận headers, bạn có thể bỏ sót:

- JAXB marshal request.
- Tạo SOAP Header và tính chữ ký WS-Security.
- Chờ thread/queue hoặc connection từ pool.
- Đọc toàn bộ XML response.
- Kiểm tra chữ ký/mã hóa và unmarshalling.
- Chuyển response thành domain object.
- Backoff và những attempts trước đó.

Đối với caller, tất cả đều là thời gian của **một lời gọi nghiệp vụ**.

### 2.2. Timeout và deadline không phải một khái niệm

- **Timeout tương đối**: cho phép một pha kéo dài không quá một khoảng nào đó, ví dụ connect timeout 2 giây.
- **Deadline tuyệt đối**: thời điểm muộn nhất mà operation phải kết thúc, ví dụ còn 1,4 giây trước khi hết budget.
- **Budget**: tổng khoảng thời gian được cấp cho operation, dùng để tạo deadline khi bắt đầu.

Có thể tính deadline theo đồng hồ monotonic:

~~~text
deadline = startMonotonic + operationBudget

remaining = max(0, deadline - nowMonotonic)
~~~

Không nên dùng `System.currentTimeMillis()` để đo khoảng thời gian vì wall-clock có thể nhảy khi NTP đồng bộ hoặc quản trị viên đổi giờ; ưu tiên `System.nanoTime()` cho thời gian trôi qua trong cùng một process.

## 3. Bốn kiểu timeout phổ biến trong HTTP client

| Loại | Tiếng Anh thường gặp | Giới hạn gì? | Điều nó không tự giới hạn |
|---|---|---|---|
| **Connect timeout** | Connection timeout | Thời gian chờ thiết lập TCP socket/kết nối đến đích hoặc proxy theo implementation | Tổng lời gọi; DNS/TLS không phải luôn được bao phủ đầy đủ |
| **Connection acquisition timeout** | Pool lease / connection request timeout | Thời gian đợi lấy một connection từ pool | Thời gian connect hoặc server xử lý |
| **Read/socket timeout** | Read/Socket timeout | Thời gian chờ thao tác đọc nhận dữ liệu, tùy client là khoảng im lặng giữa các lần đọc | Tổng tải một response nếu dữ liệu vẫn đến từng phần |
| **Response timeout** | Response timeout | Thời hạn chờ phản hồi được HTTP client quy định | Có thể không bao trùm toàn bộ parse/JAXB và retry |
| **Overall deadline** | Total call budget | Mốc thời gian cho cả operation mà ứng dụng muốn bảo đảm | Chỉ trở thành giới hạn cứng nếu transport/cancellation thực thi được |

Tên API **không hoàn toàn thống nhất giữa các thư viện**. Ví dụ, `readTimeout` của `HttpURLConnection`, `responseTimeout` của Apache HttpClient 5 và timeouts của một HTTP async client có thể khác nhau về thời điểm bắt đầu, việc reset bộ đếm và xử lý kết nối reused.

### 3.1. Connect timeout

Connect timeout hữu ích khi host không thể nhận kết nối hoặc đường mạng không hoàn tất bắt tay TCP kịp thời.

Ví dụ:

~~~text
Connect timeout = 2 s
TCP connection chưa thiết lập sau khoảng thời gian được áp dụng
    -> client ném lỗi kết nối/timeout
~~~

**Không suy ra DNS luôn nằm trong 2 giây.** Java DNS resolver hoặc hệ điều hành có thể có hành vi riêng, và các thư viện HTTP khác nhau có thể xử lý resolution, multiple addresses, proxy và retries khác nhau.

Connect timeout cũng không chứng minh TLS handshake sẽ kết thúc đúng trong 2 giây. Cần biết thư viện nào áp dụng timeout cho handshake, bao gồm các bước certificate verification và network round-trips.

### 3.2. Read timeout

Read timeout thường bảo vệ một bước đọc socket khi phía bên kia không gửi thêm dữ liệu trong khoảng nhất định.

Ví dụ với read timeout 4 giây:

~~~text
Server gửi response headers
   -> 3,5 giây sau gửi một đoạn dữ liệu
   -> 3,5 giây sau gửi đoạn tiếp theo
   -> ...
~~~

Từng lần đọc có thể chưa chạm timeout dù toàn bộ body mất nhiều chục giây. Vì vậy **read timeout không tương đương total response timeout**.

Một số HTTP clients có response timeout với phạm vi khác; phải đọc semantics của đúng API đang dùng và kiểm thử phản hồi nhỏ giọt (trickle response) trước khi coi nó là bảo đảm thời gian tổng.

### 3.3. Connection request timeout của pool

Nếu SOAP client dùng connection pool có tối đa 20 kết nối đến đối tác mà đã có 20 requests giữ hết số đó, request thứ 21 có thể chờ **lấy connection**, ngay cả khi network của đối tác vẫn khỏe.

Một timeout cho pool acquisition giúp tránh việc caller chờ vô hạn khi pool cạn. Đừng nhầm lỗi pool exhaustion với lỗi đối tác không chấp nhận TCP connect.

### 3.4. Overall deadline

Overall deadline là yêu cầu phía **ứng dụng**: operation phải báo kết quả/thất bại trong khoảng thời gian đã thống nhất, tính luôn việc thử lại và mọi bước trung gian.

Để thực thi đúng, hệ thống cần truyền **thời gian còn lại** xuống từng bước/attempt và có khả năng **cancel hoặc abort** lời gọi HTTP đang chờ. Chỉ có một biến deadline trong Java mà không kết nối nó với transport vẫn chưa bảo đảm request đang bị block sẽ dừng đúng lúc.

## 4. Ví dụ cho thấy connectTimeout + readTimeout không phải tổng thời gian

Giả sử:

~~~text
connectTimeout = 2 s
readTimeout = 4 s
poolLeaseTimeout = 1 s
~~~

Có thể xảy ra:

1. Chờ pool 0,8 giây.
2. Resolve DNS, TCP connect, TLS handshake mất thêm thời gian.
3. SOAP request được marshal, ký và upload.
4. Server xử lý 3,9 giây trước khi gửi byte đầu.
5. Server gửi body thành nhiều đoạn, mỗi đoạn cách nhau 3 giây.
6. Client xác minh chữ ký và unmarshal response.
7. Logic nghiệp vụ tiếp tục thực hiện mapping.

Không có gì đảm bảo tổng ≤ 2 + 4 = 6 giây. Một lời gọi có nhiều attempts còn cộng thêm backoff.

### 4.1. Ví dụ timeline đơn giản

~~~text
0 ms      250     700     1200     1600      4100      6000     6400
|---------|-------|--------|--------|----------|---------|---------|
 marshal    pool    connect  TLS      server      body      JAXB
            wait                         work       receive

  Tổng operation = 6.400 ms
~~~

Nếu yêu cầu nghiệp vụ có **budget 5.000 ms**, lời gọi trên đã vượt mức dù từng timeout HTTP có thể chưa báo lỗi.

### 4.2. Nhiều IP hoặc redirect có thể làm tổng tăng

Tùy HTTP client:

- Một hostname có thể phân giải ra nhiều địa chỉ IP; thử từng địa chỉ có thể áp dụng connect timeout riêng.
- Proxy có thể cần bước tunnel `CONNECT` và TLS.
- HTTP redirect có thể thêm round-trip hoặc bị chặn vì SOAP operation thường không nên tự động chuyển sang URL không đáng tin.
- Library có thể retry kết nối ở lớp transport nếu được bật.
- Pool có thể trả connection cũ đã hết hiệu lực và phải tạo connection mới.

Cần kiểm tra **hành vi thực tế** của message sender và HTTP client được cấu hình; không cộng timeouts như một phép tính bảo đảm.

## 5. Các tầng timeout trong SOAP service-to-service

Một yêu cầu của người dùng có thể đi qua nhiều ứng dụng:

~~~mermaid
flowchart LR
    A["HTTP API / UI\nbudget 5s"] --> B["Order service\nSOAP client"]
    B --> C["Partner SOAP\nservice"]
    C --> D["Database / queue"]
~~~

Từng tầng đặt timeout 5 giây **không có nghĩa** toàn bộ giao dịch nằm trong 5 giây. Nếu API đầu chờ 5 giây để gọi service thứ hai, service thứ hai lại chờ 5 giây cho service thứ ba, thời gian thực tế có thể lớn hơn cả ngân sách ban đầu khi có retries và xử lý khác.

### 5.1. Truyền remaining budget, không cấp lại budget mới

Ví dụ caller có budget 5 giây:

~~~text
Bắt đầu tại T0:      5.000 ms
Trước khi gọi SOAP:  4.300 ms còn lại
Sau connect/TLS:     3.800 ms còn lại
Sau response:          700 ms còn lại
Mapping + return:      300 ms còn lại
~~~

Khi gọi xuống partner, tầng client cần dùng **4.300 ms còn lại** làm trần thay vì tạo deadline 5 giây mới.

Nếu hệ thống có hai SOAP calls nối tiếp, mỗi call phải tiêu thụ từ **một ngân sách chung**, không có quyền riêng rẽ dùng toàn bộ 5 giây.

### 5.2. Truyền deadline qua SOAP Header có cần không?

Có thể có một header vận hành:

~~~xml
<com:DeadlineUtc
    xmlns:com="urn:example:common:v1">
    2026-11-27T10:00:05Z
</com:DeadlineUtc>
~~~

Nhưng chỉ dùng khi hai bên đã **thống nhất giao thức header và clock-skew policy**. SOAP Header tự thêm có thể bị từ chối bởi `mustUnderstand`, WSDL policy hoặc WS-Security.

Khi truyền deadline xuyên máy, cần xét:

- Wall-clock của hai máy có thể lệch; dùng timeout/remaining budget và quy tắc trừ độ trễ truyền hoặc có đồng bộ thời gian được đảm bảo.
- Deadline là dữ liệu mang tính gợi ý nếu remote không hỗ trợ cancellation.
- Header có thể cần chữ ký khi security policy yêu cầu.
- Không gửi deadline khách hàng tự cung cấp mà chưa xác thực vì có thể cho phép giữ tài nguyên quá lâu.

Trong một process, đo thời gian bằng monotonic clock. Qua network, truyền một **contract metadata** được kiểm soát, không coi `System.nanoTime()` giữa hai máy là có thể so sánh trực tiếp.

## 6. Đặt budget theo SLA/SLO chứ không theo cảm tính

Giả sử một API của doanh nghiệp có mục tiêu đáp ứng trong **4 giây** từ lúc nhận HTTP request. API có middleware, validation, domain mapping và một lời gọi SOAP đến đối tác.

Một bản phân bổ ví dụ:

| Pha | Dự phòng dự kiến |
|---|---:|
| API authentication/validation | 250 ms |
| Chuẩn bị domain + JAXB + WS-Security | 350 ms |
| SOAP call và network/server | 2.800 ms |
| Xử lý response + trả HTTP | 300 ms |
| Biên an toàn | 300 ms |
| **Tổng** | **4.000 ms** |

Các con số chỉ minh họa, không phải thông số tối ưu cho mọi hệ thống. Chúng phải dựa vào latency p95/p99, network, kích thước SOAP payload, cryptography, tình trạng pool và load test thực tế.

### 6.1. Giá trị nào nên nhỏ hơn giá trị nào?

Thường thiết kế:

~~~text
connection acquisition timeout
      <= attempt time budget

connect timeout
      <= attempt time budget

response/read timeout
      <= attempt time budget

attempt budget + retry backoff + parse/other work
      <= remaining overall budget
~~~

Đây là **bất đẳng thức định hướng thiết kế**. Vì từng loại timeout có phạm vi riêng, không thể suy ra tổng deadline được bảo đảm chỉ bằng việc đặt chúng ≤ attempt budget; vẫn cần cơ chế kiểm soát toàn operation.

### 6.2. Tạo timeouts theo failure modes

- Đối tác down hoặc IP blackhole → connect timeout cần đủ ngắn để giải phóng tài nguyên.
- Đối tác chậm thực sự → response timeout bảo vệ caller.
- Pool cạn do load tăng → pool lease timeout giúp fast-fail.
- DNS hoặc TLS chậm → HTTP client/deadline cần quan sát đúng pha.
- Response rất lớn hoặc truyền chậm → overall budget và giới hạn size quan trọng.
- Retry/backoff → phải nằm trong ngân sách, không làm caller chờ nhiều lần một cách vô hạn.

## 7. WebServiceTemplate nằm ở đâu trong cấu hình timeout?

`WebServiceTemplate` chịu trách nhiệm điều phối SOAP send/receive nhưng không trực tiếp cung cấp một API duy nhất để bảo đảm **overall deadline** trên mọi loại transport.

Timeout kết nối/đọc và cấu hình pool chủ yếu nằm ở **`WebServiceMessageSender` và HTTP client bên dưới**, không nằm trong `Jaxb2Marshaller` hay `SoapActionCallback`.

~~~text
PartnerOrderClient
  |
  +-- WebServiceTemplate
  |     +-- Jaxb2Marshaller
  |     +-- ClientInterceptor[]
  |     +-- SOAP message factory
  |     +-- WebServiceMessageSender
  |             +-- HttpURLConnection / Apache HttpClient
  |                      +-- connect/read/lease timeouts
  |
  +-- Application deadline / retry / circuit breaker
~~~

Nếu chỉ gọi:

~~~java
template.setDefaultUri("https://partner.example.test/ws");
~~~

thì bạn mới cấu hình **địa chỉ**, chưa chọn cụ thể timeout, TLS, proxy hay connection pooling policy.

### 7.1. Connection timeout không phải JAXB timeout

Đây là lỗi cấu hình thường gặp:

~~~java
Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
// Không có ý nghĩa: "Đặt timeout mạng trên marshaller".
~~~

Marshaller xử lý Java object ↔ XML; nó không chịu trách nhiệm kết nối TCP. Ngược lại, một SOAP client có HTTP timeout hợp lý vẫn có thể mất nhiều thời gian khi marshal XML rất lớn hoặc ký SOAP Body.

### 7.2. Message sender phải khớp HTTP stack

Spring-WS có các sender cho những HTTP implementations khác nhau. Ví dụ:

- `HttpUrlConnectionMessageSender` sử dụng JDK `HttpURLConnection`.
- `HttpComponentsMessageSender` dành cho các dòng dùng Apache HttpClient 4 ở phiên bản tương thích.
- `HttpComponents5MessageSender` dành cho Apache HttpClient 5 ở dòng Spring-WS hỗ trợ.

**Không trộn API của HttpClient 4 và 5.** Các lớp `RequestConfig`, `Timeout`, `ConnectionConfig`, connection manager và setter signatures đã thay đổi. Chọn ví dụ phù hợp version dependency của dự án; không sao chép cấu hình mà chưa đối chiếu javadocs/build runtime.

## 8. Cấu hình đơn giản với HttpUrlConnectionMessageSender

Đối với SOAP client không yêu cầu pool phức tạp, `HttpUrlConnectionMessageSender` là lựa chọn đơn giản.

Một cấu hình **theo API sử dụng `Duration` ở các dòng Spring-WS hỗ trợ**:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.transport.http.HttpUrlConnectionMessageSender;

@Configuration
public class OrdersHttpSenderConfiguration {

    @Bean
    public HttpUrlConnectionMessageSender ordersHttpSender() {

        HttpUrlConnectionMessageSender sender =
            new HttpUrlConnectionMessageSender();

        sender.setConnectionTimeout(
            Duration.ofSeconds(2)
        );

        sender.setReadTimeout(
            Duration.ofSeconds(4)
        );

        return sender;
    }
}
~~~

**Lưu ý tương thích phiên bản:** Một số dòng Spring-WS cũ có setters nhận `int` theo mili giây thay vì `Duration`; một số dòng mới đổi/deprecate phương thức cũ. Cần đối chiếu chữ ký API của đúng Spring-WS artifact trước khi copy snippet.

Gắn sender vào template:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.transport.http.HttpUrlConnectionMessageSender;

@Configuration
public class OrdersClientConfiguration {

    @Bean(name = "ordersTemplate")
    public WebServiceTemplate ordersTemplate(
            @Qualifier("ordersMarshaller")
            Jaxb2Marshaller marshaller,
            HttpUrlConnectionMessageSender ordersHttpSender) {

        WebServiceTemplate template =
            new WebServiceTemplate();

        template.setMarshaller(marshaller);
        template.setUnmarshaller(marshaller);
        template.setDefaultUri(
            "https://partner.example.test/ws"
        );
        template.setMessageSender(ordersHttpSender);

        return template;
    }
}
~~~

Ở đây `ordersMarshaller` giả định là bean `Jaxb2Marshaller` được khởi tạo từ XSD/JAXB package đúng contract. Nếu có nhiều sender/marshaller beans cùng type, dùng `@Qualifier` để gắn đúng client.

### 8.1. Hai timeout này bảo vệ gì?

- `setConnectionTimeout`: giới hạn thời gian dành cho việc kết nối theo semantics của JDK connection implementation.
- `setReadTimeout`: giới hạn blocking read theo semantics của `URLConnection`.
- Không cái nào trực tiếp cấp **deadline tổng** cho cả lời gọi `marshalSendAndReceive`.

Ngoài ra, `HttpURLConnection` không cung cấp pooling/lease APIs giống Apache pooled HTTP client; nếu bạn cần kiểm soát số lượng kết nối, pool pressure hoặc connection reuse nâng cao, nên đánh giá HTTP sender dựa trên HttpClient và connection manager phù hợp.

### 8.2. Chọn 0 hoặc âm làm timeout có rủi ro

Một số HTTP API xem timeout bằng **0** là vô hạn; API khác từ chối giá trị âm hoặc diễn giải khác. Không dùng `0` với suy nghĩ “không chờ”. Hãy xác định chính sách và kiểm tra giá trị cấu hình tại startup.

### 8.3. TLS handshake có thể chưa nằm trọn trong connect timeout

`HttpURLConnection`/HTTPS có các pha DNS, TCP, proxy tunnel và TLS negotiation khác nhau. Phạm vi `connectTimeout`/`readTimeout` đối với handshake phụ thuộc implementation. Nếu yêu cầu chặn cứng trong thời hạn nhất định, phải kết hợp với cơ chế tổng và transport cancellation có kiểm thử thực tế.

## 9. Apache HttpClient và connection pool trong tích hợp tải cao

Khi client có lưu lượng nhiều, connection pooling giúp tái sử dụng TCP/TLS connections và giảm chi phí handshake. Nhưng pool tạo thêm một hàng đợi cần được giới hạn.

Một kiến trúc:

~~~text
Business thread
    |
    v
WebServiceTemplate
    |
    v
HttpComponents5MessageSender (nếu dùng HttpClient 5)
    |
    v
Pooling connection manager
    |-- max connections toàn client
    |-- max connections mỗi route
    |-- lease wait / connection request timeout
    |-- connect timeout
    |-- response timeout
    |-- idle/expired connection eviction
    |
    v
Remote SOAP endpoint
~~~

Các tham số pool có tác động khác nhau:

| Tham số | Rủi ro khi quá nhỏ | Rủi ro khi quá lớn |
|---|---|---|
| Max total connections | Queue/lease timeout, throughput thấp | Nhiều sockets/TLS sessions/FDs |
| Max per route | Một partner thành bottleneck | Flood remote partner khi load tăng |
| Lease timeout | Fail-fast có thể nhiều khi burst | Threads chờ pool quá lâu |
| Keep-alive/idle TTL | Phải handshake lại nhiều lần | Dùng connection stale nếu eviction/validation kém |
| Connect timeout | False timeout khi network biến động | Giữ thread/socket lâu khi host down |
| Response timeout | Fail trước khi partner hoàn tất | Caller treo lâu khi server chậm |

Không tăng pool size vô hạn để “chữa” lease timeout. Cần xem vì sao connections bị giữ lâu: server chậm, response body chưa đóng, quá nhiều calls đồng thời, retry storm, hoặc không giới hạn tải ở tầng caller.

### 9.1. Một ví dụ cấu hình HttpClient 5

Trong stack **Spring-WS có `HttpComponents5MessageSender` và Apache HttpClient 5**, có thể xây client với pool và timeouts ở lớp Apache:

~~~java
import org.apache.hc.client5.http.classic.HttpClient;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.core5.util.Timeout;

import org.springframework.ws.transport.http.HttpComponents5MessageSender;

RequestConfig requests = RequestConfig.custom()
    .setConnectionRequestTimeout(Timeout.ofSeconds(1))
    .setResponseTimeout(Timeout.ofSeconds(4))
    .build();

ConnectionConfig connections = ConnectionConfig.custom()
    .setConnectTimeout(Timeout.ofSeconds(2))
    .build();

PoolingHttpClientConnectionManager manager =
    PoolingHttpClientConnectionManagerBuilder.create()
        .setDefaultConnectionConfig(connections)
        .setMaxConnTotal(100)
        .setMaxConnPerRoute(20)
        .build();

CloseableHttpClient httpClient = HttpClients.custom()
    .setConnectionManager(manager)
    .setDefaultRequestConfig(requests)
    .disableAutomaticRetries()
    .build();

HttpComponents5MessageSender sender =
    new HttpComponents5MessageSender(httpClient);

// Gắn sender vào WebServiceTemplate qua setMessageSender(...).
~~~

Đây là **mẫu định hướng triển khai cho những phiên bản tương thích**, không phải một file Java độc lập hoàn chỉnh. Cần kiểm tra package imports, constructor, API HTTP sender của phiên bản Spring-WS đang dùng, TLS/proxy policy, và quản lý lifecycle đóng `CloseableHttpClient` cùng pool đúng lúc ứng dụng shutdown.

Có thể khác biệt theo phiên bản Apache HttpClient 5 minor: một số timeout hoặc connection manager builder APIs được thay đổi/deprecate. Không trộn `HttpComponentsMessageSender` (HttpClient 4) và `HttpComponents5MessageSender` (HttpClient 5).

### 9.2. Vì sao nên vô hiệu hóa retry ngầm của HTTP client khi cần kiểm soát ngân sách?

Một số HTTP stacks có logic retry ở tầng transport. Với SOAP POST có side effect, một retry không được application biết có thể gây request trùng hoặc tiêu thụ budget không dự tính.

Ví dụ dùng `disableAutomaticRetries()` để **đưa quyết định retry lên tầng có hiểu nghiệp vụ**. Quy tắc retry chính xác vẫn tùy version/client configuration, nhưng nguyên tắc là phải biết mỗi operation được gửi bao nhiêu lần.

### 9.3. Chưa có tổng deadline khi chỉ cấu hình HttpClient

Dù có lease=1s, connect=2s, response=4s, một lời gọi vẫn có thể mất hơn 4s vì chờ pool, parse SOAP, ký/verify XML và retry. Cần thêm budget orchestration và khả năng cancellation phù hợp.

## 10. Read timeout và response timeout: trường hợp server trả nhỏ giọt

Giả sử `GetReport` SOAP operation tạo response lớn. Server gửi phần đầu rồi mỗi 2 giây mới gửi thêm một phần:

~~~text
T=0s   Kết nối thành công
T=1s   Nhận response headers
T=3s   Nhận XML fragment A
T=5s   Nhận XML fragment B
T=7s   Nhận XML fragment C
T=9s   Nhận XML fragment D
T=11s  SOAP Body hoàn tất
~~~

Nếu read timeout đo **khoảng không hoạt động giữa hai lần đọc** và được đặt 3 giây, từng lần chờ có thể chưa vượt timeout; tổng response vẫn mất 11 giây.

### 10.1. Điều gì làm việc này nguy hiểm với SOAP?

JAXB thường chỉ có thể cung cấp đối tượng response cuối cùng khi XML đã được đọc và phân tích đủ. Với SOAP message lớn có WS-Security, client còn phải xác minh chữ ký hoặc giải mã trước khi tin cậy dữ liệu.

Do đó, một connection vẫn “có dữ liệu” không có nghĩa lời gọi đang tiến tới kết thúc trong ngân sách.

### 10.2. Những cách bảo vệ

- Có **total deadline** bao trùm toàn bộ operation.
- Giới hạn kích thước SOAP body, độ sâu XML và số phần tử.
- Chọn HTTP client hỗ trợ khả năng hủy request khi deadline hết.
- Có stream-level limits/response body caps khi phù hợp.
- Tránh giữ nguyên tất cả response body vào bộ nhớ chỉ để logging.
- Đo time-to-first-byte và total response body time riêng nếu có công cụ.
- Với dữ liệu rất lớn, cân nhắc streaming/StAX hoặc thiết kế API phân trang/thao tác bất đồng bộ thay vì SOAP response khổng lồ.

### 10.3. Time-to-first-byte không thay tổng response time

Một số metrics đo lúc nhận headers hoặc byte đầu; điều đó không đại diện thời gian JAXB unmarshal xong. Nếu business SLA kết thúc khi Java method trả response, metric phải bắt đầu từ operation entry và dừng sau mapping/validation.

## 11. Thiết kế DeadlineBudget bằng monotonic clock

Một component đơn giản có thể theo dõi thời gian còn lại từ khi operation bắt đầu:

~~~java
import java.time.Duration;

public final class DeadlineBudget {

    private final long startedNanos;
    private final long budgetNanos;

    private DeadlineBudget(Duration allowed) {
        if (allowed == null
                || allowed.isZero()
                || allowed.isNegative()) {
            throw new IllegalArgumentException(
                "Ngân sách phải lớn hơn 0"
            );
        }

        this.startedNanos = System.nanoTime();
        this.budgetNanos = allowed.toNanos();
    }

    public static DeadlineBudget start(Duration allowed) {
        return new DeadlineBudget(allowed);
    }

    public Duration remaining() {
        long elapsed = System.nanoTime() - startedNanos;
        long left = budgetNanos - Math.max(0L, elapsed);

        return Duration.ofNanos(Math.max(0L, left));
    }

    public boolean expired() {
        return remaining().isZero();
    }

    public void requireRemaining() {
        if (expired()) {
            throw new CallDeadlineExceededException(
                "Đã hết ngân sách thời gian SOAP"
            );
        }
    }
}
~~~

`CallDeadlineExceededException` là exception ứng dụng tự định nghĩa. Ví dụ này chủ ý dùng `System.nanoTime()` để đo **thời gian trôi qua**, không dùng wall-clock. `Duration.toNanos()` có thể overflow nếu truyền ngân sách cực lớn; trong ứng dụng nên giới hạn cấu hình maximum được chấp nhận, ví dụ vài giây hoặc chục giây theo policy.

### 11.1. Những gì helper này giải quyết

- Không cấp lại budget mỗi khi bắt đầu retry.
- Biết lúc nào operation đã hết thời gian.
- Cho phép các bước tiếp theo nhận thời gian còn lại.
- Phân biệt timeout do **budget của caller** với timeout **đọc/kết nối của transport** khi log và metric.

### 11.2. Những gì helper này chưa giải quyết

Nó **không tự ngắt** một `WebServiceTemplate.marshalSendAndReceive(...)` đang block trong socket read hoặc TLS handshake. Nếu chỉ kiểm tra trước khi gọi, operation vẫn có thể vượt deadline.

Ví dụ không đủ:

~~~java
DeadlineBudget budget =
    DeadlineBudget.start(Duration.ofSeconds(3));

budget.requireRemaining();

Object response = template.marshalSendAndReceive(request);

// Có thể trở về sau 10 giây dù budget là 3 giây.
~~~

Để có một **hard deadline** đáng tin cậy cần chọn HTTP transport/client API hỗ trợ request cancellation và cấu hình timeouts có thể ràng buộc với remaining budget. Phải kiểm thử với một server cố tình giữ kết nối, không chỉ dựa trên tính toán thời gian trong code.

### 11.3. Đặt deadline ở đâu?

Với một operation nghiệp vụ:

~~~text
OrderApplicationService.lookup(...)
    |
    +-- Tạo DeadlineBudget một lần
    |
    +-- Validation, SOAP request marshal, WS-Security
    |
    +-- Attempt 1
    |      +-- pool wait, connect, request, response, unmarshal
    |
    +-- Nếu retry được và còn budget
    |      +-- Backoff có giới hạn
    |      +-- Attempt 2 dùng budget còn lại
    |
    +-- Return hoặc DeadlineExceeded
~~~

Nếu tầng API phía trên đã có deadline, client adapter **nhận deadline hiện có** thay vì tự cấp thêm. Điều này đặc biệt quan trọng với chuỗi nhiều dịch vụ downstream.

## 12. Deadline mềm, deadline cứng và việc hủy request

Cần phân biệt ba mức thực thi:

| Mức | Cơ chế | Bảo đảm |
|---|---|---|
| **Theo dõi** | Đo elapsed, cảnh báo vượt SLO | Không ngăn lời gọi kéo dài |
| **Soft deadline** | Trả lỗi cho caller khi hết budget | Caller thôi chờ, nhưng network task có thể vẫn chạy |
| **Enforced/hard deadline** | Timeout/cancellation của transport và xử lý có kiểm soát | Có khả năng dừng thao tác ở ranh giới đã thiết kế; phải kiểm chứng |

Không nên gọi một cơ chế là “hard timeout” chỉ vì code dùng `Future.get(timeout)`.

### 12.1. Vì sao Future.get không đủ?

Ví dụ:

~~~java
Future<Object> pending = executor.submit(
    () -> template.marshalSendAndReceive(request)
);

Object result = pending.get(
    3,
    java.util.concurrent.TimeUnit.SECONDS
);
~~~

`pending.get(3s)` chỉ giới hạn thời gian **thread đang đợi Future**. Khi nó ném `TimeoutException`, task ở thread khác có thể vẫn đang chờ socket hoặc xử lý JAXB.

Ngay cả:

~~~java
pending.cancel(true);
~~~

cũng chỉ gửi yêu cầu interrupt. Không có bảo đảm mọi HTTP stack hoặc XML parser đang block sẽ dừng ngay lập tức. Thread có thể vẫn giữ connection, làm pool cạn và khiến các requests kế tiếp cũng chậm.

Nếu dùng Future để tạo soft deadline, phải có **cơ chế đóng/abort connection** tương thích, giới hạn số task chạy dở, kiểm soát thread pool và test khả năng giải phóng tài nguyên.

### 12.2. CompletableFuture.orTimeout cũng không tự đóng socket

Một mẫu thường gặp:

~~~java
CompletableFuture.supplyAsync(
    () -> template.marshalSendAndReceive(request),
    executor
).orTimeout(3, TimeUnit.SECONDS);
~~~

Nó có thể hoàn tất future bằng lỗi timeout, nhưng **không mặc định hủy I/O** trong task đang chạy. Điều này chỉ giới hạn cách người gọi quan sát completion, không phải khả năng giải phóng connection và thread.

### 12.3. Khi cần giới hạn cứng hơn

Một thiết kế có thể sử dụng:

1. HTTP client hỗ trợ per-request deadlines/response timeout và cancellation.
2. Không chia sẻ cấu hình timeout mutable bị thay đổi giữa concurrent calls.
3. Cơ chế abort request khi deadline hết, nếu API transport cho phép.
4. Connection pool và caller concurrency giới hạn.
5. Giới hạn payload/parse complexity.
6. Recovery/cleanup và monitoring những thao tác đã quá hạn.
7. Integration test xác minh cả thời gian trả lỗi **và** thời gian giải phóng connection.

Với API đồng bộ `WebServiceTemplate`, khả năng áp dụng một deadline thật sự xuyên mọi pha phụ thuộc HTTP sender đã chọn. Nếu yêu cầu chặt chẽ hơn, có thể cần một transport wrapper chuyên dụng hoặc một client stack hỗ trợ end-to-end cancellation rõ ràng, thay vì giả định property của template sẽ làm việc đó.

## 13. Phân bổ thời gian theo mỗi attempt

Giả sử toàn operation có budget 4 giây và chính sách cho phép tối đa hai attempts với operation **read-only** `GetOrder`.

Một kế hoạch minh họa:

~~~text
Tổng budget: 4.000 ms

Attempt 1:
  pool wait tối đa 200 ms
  connect tối đa 400 ms
  response/read tối đa 1.600 ms

Nếu lỗi có thể retry:
  backoff 150 ms

Attempt 2:
  dùng remaining budget thực tế
  không được cấp lại 4.000 ms
  còn chừa thời gian cho JAXB và return
~~~

Không được cộng cơ học các con số rồi khẳng định hoàn thành đúng hạn; đó là **các trần cho từng pha**, và có bước DNS/TLS/serialization nằm ngoài phạm vi một vài timeout.

### 13.1. Thuật toán retry theo remaining time

Pseudocode có ý nghĩa:

~~~java
DeadlineBudget budget =
    DeadlineBudget.start(Duration.ofSeconds(4));

for (int attempt = 1; attempt <= 2; attempt++) {
    budget.requireRemaining();

    Duration remaining = budget.remaining();

    // Chọn một attemptBudget <= remaining, có khoảng
    // dự phòng cho mapping, cleanup và phản hồi caller.
    Duration attemptBudget = chooseAttemptBudget(remaining);

    try {
        // Gửi SOAP qua transport có cấu hình/khả năng cancel
        // thực sự ràng buộc với attemptBudget.
        return executeSoapAttempt(attemptBudget);

    } catch (TransientPartnerException transientFailure) {
        if (attempt == 2
                || !isRetrySafeOperation()
                || budget.expired()) {
            throw transientFailure;
        }

        Duration delay = chooseBackoff(attempt);
        if (delay.compareTo(budget.remaining()) >= 0) {
            throw new CallDeadlineExceededException(
                "Không còn budget để retry"
            );
        }

        sleepWithinBudget(delay);
    }
}

throw new IllegalStateException("Không có kết quả");
~~~

Đây là **pseudocode kiến trúc**, các helper `chooseAttemptBudget`, `executeSoapAttempt`, `chooseBackoff`, `sleepWithinBudget`, `isRetrySafeOperation` và exception types là phần ứng dụng cần triển khai. Không copy nguyên khối như một class biên dịch độc lập.

Trọng tâm không nằm ở vòng `for` mà ở lời cam kết: **executeSoapAttempt phải áp được budget xuống transport/cancellation**; nếu không, điều kiện `budget.expired()` chỉ được kiểm tra sau khi thao tác đã block quá lâu.

### 13.2. Backoff và jitter cũng tiêu thụ budget

Nếu retry sau 300 ms rồi 900 ms, tổng 1,2 giây nằm trong budget. Không áp một chính sách retry cố định 5 attempts với backoff dài hơn deadline rồi mong caller vẫn trả đúng SLA.

Jitter giúp tránh nhiều clients đồng loạt retry sau một outage, nhưng vẫn phải giữ tổng thời gian không vượt remaining budget. Thông thường tính:

~~~text
delayApplied = min(delayWithJitter, remaining - reserveForWork)
~~~

Nếu không còn đủ thời gian cho một attempt có khả năng thành công, nên fast-fail thay vì tạo thêm lưu lượng vô ích.

### 13.3. Retry budget và time budget là hai trần khác nhau

- `maxAttempts = 2` bảo vệ số lần gửi.
- `overallBudget = 4s` bảo vệ thời gian.
- `maxConcurrent = 100` bảo vệ số lời gọi đồng thời.
- `rateLimit` bảo vệ tốc độ phát sinh request.

Phải có chính sách phối hợp cả bốn. Chỉ đặt timeout thấp nhưng cho retry vô hạn vẫn gây retry storm.

## 14. Idempotency quyết định có được retry SOAP hay không

Một SOAP operation như `GetOrder` thường là truy vấn, có thể retry khi lỗi transport tạm thời nếu đối tác cho phép và request không có side effect. Nhưng `CreateOrder`, `SubmitPayment` hoặc `CancelOrder` có thể đã xử lý thành công dù client hết thời gian chờ response.

### 14.1. Ví dụ timeout không chứng minh server chưa làm việc

~~~text
Client                   Server
  |---- CreateOrder ------>|
  |                        | Ghi DB thành công
  |<--- response ...        | (mạng lỗi giữa chừng)
  | timeout                |
  |---- CreateOrder ------>| (retry)
  |                        | Có thể tạo đơn thứ hai
~~~

Nếu operation không idempotent, retry có thể tạo duplicate. Cần xác định chiến lược:

- Idempotency key hoặc request ID được server hiểu và lưu kết quả theo chính sách.
- SOAP contract công bố semantics của thao tác lặp.
- Nếu không có idempotency, chỉ retry những lỗi có thể chứng minh chưa gửi request, hoặc thực hiện reconciliation thay vì gửi lại.
- Kết quả “không rõ đã thực hiện hay chưa” phải có error state và quy trình điều tra rõ ràng.

### 14.2. Không retry mọi SOAP Fault

SOAP 1.1 Fault `Client` hoặc SOAP 1.2 `Sender` thường gợi ý lỗi request, credential, schema hoặc policy; retry nguyên thông điệp thường không khắc phục được.

SOAP 1.1 `Server` hoặc SOAP 1.2 `Receiver` có thể là sự cố tạm thời nhưng không tự chứng minh retry an toàn. Phải xét Fault Detail, WSDL error contract, tác động nghiệp vụ và idempotency.

### 14.3. Kiểm soát HTTP-level retries

Một HTTP client có thể tự retry lỗi kết nối tùy config. Nếu application cũng có retry, số attempts trên dây có thể lớn hơn mong đợi.

Với SOAP POST có side effect, nên thiết kế một nơi duy nhất quyết định retry. Nếu chọn để tầng HTTP auto retry, phải chứng minh nó chỉ thực hiện trong các tình huống an toàn và được tính vào budget/metric.

## 15. Deadline xuyên nhiều lời gọi và fan-out

Một request API có thể gọi song song hai SOAP services:

~~~mermaid
flowchart LR
    A["API request: budget 3s"] --> B["Orders SOAP"]
    A --> C["Billing SOAP"]
    B --> D["Join / response"]
    C --> D
~~~

Nếu hai calls chạy **song song**, tổng thời gian không nhất thiết bằng tổng hai response times; nhưng join vẫn phải tôn trọng budget tổng. Nếu một call chậm, cần biết có thể trả partial result hay phải hủy toàn bộ và rollback/reconcile.

Nếu calls chạy **tuần tự**, call thứ hai chỉ có thời gian còn lại sau call thứ nhất. Không cấp hai lần 3s.

### 15.1. Cộng thêm chi phí xử lý của API

Trước khi gửi SOAP, caller có thể tiêu thụ 600 ms cho authentication, DB lookup và JAXB mapper. Nếu deadline tổng là 3s, SOAP call chỉ còn 2,4s **trừ reserve** cho xử lý response và trả HTTP.

Ví dụ:

~~~text
SLA API:                3.000 ms
Auth + validation:        350 ms
Domain lookup:            250 ms
Reserve response write:   250 ms
SOAP khả dụng còn:      2.150 ms
~~~

Đây chỉ là ví dụ phân bổ. Thời gian còn lại thực tế phải đo bằng đồng hồ monotonic tại thời điểm bắt đầu SOAP, không suy ra từ các hằng số dự kiến.

### 15.2. Deadline trong distributed tracing

Traces nên có:

- Parent span cho operation API.
- Child span cho SOAP client attempt.
- Attribute operation, partner alias và attempt number.
- Duration và error kind (connect/lease/read/deadline/Fault).
- Correlation ID có vòng đời rõ.

Không dùng `orderId`, UUID mỗi request hoặc địa chỉ riêng làm metric labels có cardinality cao. Dữ liệu tracing phải theo chính sách bảo mật và masking.

## 16. SOAP Fault không giống timeout

Khi remote server có khả năng trả SOAP Fault hợp lệ, đó là **phản hồi ở tầng SOAP**, không phải lời gọi “không có phản hồi”.

Ví dụ SOAP 1.1 Fault:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
    <soap:Body>
        <soap:Fault>
            <faultcode>soap:Server</faultcode>
            <faultstring>Backend temporarily unavailable</faultstring>
        </soap:Fault>
    </soap:Body>
</soap:Envelope>
~~~

`WebServiceTemplate` có thể gọi `ClientInterceptor.handleFault` và `FaultMessageResolver` để xử lý Fault. Nếu network không kết nối được, không có SOAP Envelope để xử lý và `handleFault` có thể không chạy.

### 16.1. Ma trận phân loại

| Kết quả | Có SOAP message hợp lệ? | Có thể liên quan timeout? | Xử lý |
|---|---|---|---|
| Response bình thường | Có | Có thể chậm nhưng hoàn tất | JAXB/domain response |
| SOAP Fault | Có | Có thể do server quá tải, nhưng không phải client socket timeout | Fault resolver, policy |
| Connect timeout | Không cần có | Có | Transport exception |
| Pool lease timeout | Chưa gửi đến server | Có | Local saturation/backpressure |
| Read timeout | Có thể mới nhận một phần | Có | Transport/parse exception |
| Overall deadline exceeded | Tùy thời điểm | Có | Caller budget/cancellation |
| TLS handshake failure | Không có SOAP body đáng tin | Không nhất thiết là timeout | TLS/certificate error |
| JAXB unmarshal failure | Thường đã có SOAP payload | Không nhất thiết | Contract mismatch |

### 16.2. Hai loại lỗi timeout khác nhau về trách nhiệm

**Connect timeout** có thể do network, DNS/proxy routing hoặc remote host không phản hồi kết nối.

**Read timeout** có thể do remote server xử lý quá lâu, reverse proxy buffering, mất gói hoặc response truyền chậm. Nó không chứng minh lỗi nằm hoàn toàn ở server.

**Deadline exceeded** có thể do caller dành quá ít budget, overload ở client pool hoặc nhiều attempts, dù server từng attempt phản hồi trong thời gian hợp lý.

Do đó, khi log `timeout` cần thêm stage và attempt, không chỉ in chung “SOAP timeout”.

## 17. Tác động của TLS, chứng chỉ và WS-Security lên ngân sách

SOAP enterprise thường sử dụng HTTPS và có thể dùng mutual TLS, XML Signature, Timestamp hoặc mã hóa một phần thông điệp.

### 17.1. TLS handshake

Một kết nối mới có thể trải qua:

1. DNS/route/proxy tunnel.
2. TCP connect.
3. TLS handshake.
4. Xác minh certificate chain và hostname.
5. Có thể gửi client certificate để xác thực mTLS.
6. Bắt đầu gửi HTTP SOAP request.

Các bước này có thể tốn thời gian; trong một số HTTP stacks TLS handshake được giới hạn bởi những timeout khác nhau hoặc không được bao trùm trọn bởi connect timeout. Không giả định `connectTimeout=2s` đồng nghĩa **đã TLS-ready trong 2s**.

### 17.2. Reuse connection giúp giảm handshake nhưng không giải quyết mọi vấn đề

Pooling có thể tái sử dụng TCP/TLS connection cho nhiều SOAP requests; điều đó giảm latency trung bình. Tuy nhiên:

- Idle connection có thể bị load balancer đóng.
- Certificate rotation/truststore thay đổi cần quản trị pool.
- Connection pool có thể cạn khi remote server chậm.
- Hệ thống có nhiều routes có thể cần max-per-route phù hợp.
- Timeouts với reused connection khác một kết nối mới không có TCP connect.

Trong test hãy có cả **cold connection** và **warm pooled connection**.

### 17.3. WS-Security là chi phí xử lý thông điệp

Với WS-Security, các bước có thể gồm:

~~~text
Marshal SOAP payload
   -> thêm Timestamp, Security Header
   -> ký Body/Headers
   -> (nếu yêu cầu) mã hóa
   -> gửi HTTPS
   -> nhận response
   -> xác minh chữ ký và chứng chỉ
   -> giải mã
   -> JAXB unmarshal
~~~

Những bước cryptography/XML canonicalization có thể tiêu tốn CPU đáng kể trên payload lớn, không được bảo vệ bởi socket read timeout. Vì vậy **overall latency metric** cần bao gồm chúng.

### 17.4. Không tắt certificate validation để giảm thời gian

Nếu TLS handshake hoặc certificate verification chậm/lỗi, không khắc phục bằng cách tin cậy mọi certificate hoặc tắt hostname verification. Cần kiểm tra truststore, certificate chain, DNS, proxy và chính sách mTLS đúng cách. Thay đổi security để đạt SLA có thể tạo rủi ro nghiêm trọng hơn timeout.

## 18. Connection pool, concurrency và backpressure

Một SOAP client sync giữ một worker thread trong suốt thời gian gọi network. Nếu 500 threads cùng gọi đối tác, mỗi call chờ 5s, hệ thống có thể tích lũy hàng nghìn requests chỉ trong thời gian ngắn nếu không giới hạn đầu vào.

### 18.1. Little's Law như công cụ suy nghĩ

Với hệ thống ổn định, quan hệ gần đúng:

~~~text
Concurrency ~= throughput x mean latency
~~~

Ví dụ một đối tác xử lý 100 requests/s và latency trung bình 0,5s, số calls đang chờ trung bình có thể khoảng 50. Nếu latency tăng lên 3s nhưng traffic không giảm, số calls đồng thời có thể tăng lên khoảng 300.

Đây là quan hệ thống kê ở trạng thái ổn định, **không phải công thức bảo đảm peak pool size**. Pool sizing cần xét burst traffic, tail latency p99, số routes và khả năng chịu tải của partner.

### 18.2. Cần giới hạn callers trước pool

Các biện pháp:

- Semaphore/bulkhead giới hạn số SOAP calls đồng thời.
- Queue có kích thước và thời hạn chờ xác định.
- Pool lease timeout để tránh chờ vô hạn.
- Circuit breaker khi đối tác liên tục lỗi.
- Rate limit theo partner quotas.
- Load shedding/fast-fail khi thiếu budget.
- Retry budget riêng để tránh retry storm.

Nếu pool lease timeout liên tục tăng, không tăng vô hạn maxConnections. Hãy kiểm tra có request giữ connection lâu, response body không được tiêu thụ/đóng, TLS/network chậm hoặc quá nhiều retries đồng thời không.

### 18.3. Timeout là cơ chế giải phóng tài nguyên, không chỉ trải nghiệm người dùng

Một lời gọi hết deadline nhưng HTTP task vẫn sống có thể tiếp tục giữ:

- Thread.
- Socket/connection pool lease.
- Memory buffers chứa SOAP body.
- JAXB/WS-Security objects.
- Tracing/logging contexts.

Vì thế cần đo **thời gian thu hồi tài nguyên** sau timeout, không chỉ đo caller đã nhận exception sau bao lâu.

## 19. Thiết kế retry khi budget còn rất ít

Giả sử budget tổng còn 200 ms sau attempt đầu. Policy cho retry thứ hai cần pool wait 100 ms, connect 300 ms, read 900 ms. Lúc này **không nên retry** chỉ để “đủ số lần thử” vì phần thời gian còn lại rất khó cho một attempt hữu ích.

Một chính sách gợi ý:

~~~text
if remaining <= reserveForReturn:
    fail DEADLINE_EXCEEDED

if remaining < minimumUsefulAttempt:
    fail DEADLINE_EXCEEDED

if operation is not retry-safe:
    fail with original classified error

if retry quota exhausted:
    fail with original classified error

else:
    backoff <= remaining - minimumUsefulAttempt
    attemptTimeout <= remaining - reserveForReturn
    execute attempt with real cancellation/transport limits
~~~

Các ngưỡng `minimumUsefulAttempt` hoặc `reserveForReturn` cần được đo theo môi trường thực; không dùng một con số cố định cho mọi SOAP service.

### 19.1. Không reset deadline ở recursive retry

Sai:

~~~java
Object call() {
    try {
        return template.marshalSendAndReceive(request);
    } catch (Exception ex) {
        // Gọi lại call() có thể reset timeout vô hạn.
        return call();
    }
}
~~~

Không chỉ có nguy cơ stack overflow, nó còn làm mất kiểm soát số attempts và không phân biệt Fault với lỗi mạng. Thực thi retry bằng loop/circuit breaker có giới hạn và deadline của operation gốc.

### 19.2. Hedging và speculative retry có thể nhân đôi side effects

Gửi cùng SOAP request đến hai connections song song để lấy response nhanh nhất (hedging) có thể hữu ích cho read-only idempotent operations nhưng nguy hiểm cho những operation tạo/thay đổi dữ liệu. Nếu đối tác không hỗ trợ idempotency và cancellation, hedging có thể tạo hai thao tác thật.

Không sử dụng kỹ thuật này cho thanh toán/đặt hàng chỉ để giảm p99 mà chưa chứng minh tính an toàn nghiệp vụ.

## 20. Kiểm thử timeout phải sử dụng HTTP thật ở lớp transport

`MockWebServiceServer` của Spring-WS rất hữu ích để kiểm tra SOAP payload, SOAPAction, JAXB response và SOAP Fault. Tuy nhiên, nó **thay thế HTTP transport**. Vì vậy nó không chứng minh:

- TCP connection timeout.
- DNS/proxy/TLS handshake latency.
- Read timeout khi server giữ socket mở.
- Connection pool lease timeout.
- Connection cancellation và thu hồi tài nguyên.
- Tính đúng của total deadline sau nhiều retries.

Đây là khác biệt quan trọng giữa **contract test** và **transport resilience test**.

### 20.1. Ma trận test theo failure mode

| Test | Cách mô phỏng | Xác nhận |
|---|---|---|
| T1 | SOAP response hợp lệ và nhanh | Unmarshal đúng, dưới budget |
| T2 | Server chấp nhận TCP nhưng không gửi headers | Read/response timeout đúng |
| T3 | Server gửi headers rồi dừng body | Blocking read timeout đúng |
| T4 | Server gửi body nhỏ giọt mỗi lần dưới read timeout | Overall deadline vẫn được xử lý |
| T5 | HTTP connection bị từ chối ngay | Fast-fail connection error, không gọi Fault handler |
| T6 | Network blackhole có kiểm soát | Connect timeout theo transport thực tế |
| T7 | Pool có một connection, hai calls đồng thời | Pool lease timeout/backpressure |
| T8 | TLS certificate không trust | TLS handshake failure, không tự bypass security |
| T9 | SOAP Fault hợp lệ trong HTTP error response | Fault resolver phân loại SOAP Fault |
| T10 | HTTP 503 trả HTML, không có SOAP Envelope | Transport/parse error, không nhận như SOAP Fault |
| T11 | JAXB unmarshalling rất chậm với payload lớn | Tổng operation latency tính cả parse |
| T12 | Retry 2 attempts và backoff | Tổng không reset budget, số attempts được kiểm tra |
| T13 | Caller deadline hết khi socket đang block | Caller fail đúng hạn và resource được thu hồi |
| T14 | Cùng endpoint khi reuse keep-alive connection | Không giả định connect timeout chạy ở mọi call |
| T15 | SOAP message có WS-Security | Thời gian ký/verify tính vào tổng |

Để thử blackhole/network hoặc TLS failure, cần môi trường test được phép và có thể tái tạo (network simulator, Toxiproxy, WireMock/MockWebServer tùy chức năng, hoặc dedicated test gateway). Không dùng địa chỉ IP công cộng bất kỳ để cố “làm timeout”, vì kết quả phụ thuộc network thật và khó tái hiện.

### 20.2. Test read timeout bằng HTTP server cục bộ

Một skeleton JUnit dùng JDK HTTP server để mô phỏng server giữ response:

~~~java
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import com.sun.net.httpserver.HttpServer;

import org.junit.jupiter.api.Test;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.transport.http.HttpUrlConnectionMessageSender;

class SoapHttpTimeoutTest {

    @Test
    void timesOutWhenServerWaitsBeforeHeaders() throws Exception {

        HttpServer server = HttpServer.create(
            new InetSocketAddress("127.0.0.1", 0),
            0
        );

        server.createContext("/soap", exchange -> {
            try {
                // Server nhận request rồi cố tình không trả
                // response headers trong một khoảng.
                Thread.sleep(1200);

                byte[] response = """
                    <soap:Envelope xmlns:soap=
                        "http://schemas.xmlsoap.org/soap/envelope/">
                      <soap:Body/>
                    </soap:Envelope>
                    """.getBytes(StandardCharsets.UTF_8);

                exchange.getResponseHeaders().set(
                    "Content-Type",
                    "text/xml; charset=utf-8"
                );

                exchange.sendResponseHeaders(
                    200,
                    response.length
                );

                try (var body = exchange.getResponseBody()) {
                    body.write(response);
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            } catch (java.io.IOException connectionClosed) {
                // Client có thể đã timeout và đóng connection.
            } finally {
                exchange.close();
            }
        });

        server.start();

        try {
            HttpUrlConnectionMessageSender sender =
                new HttpUrlConnectionMessageSender();

            sender.setConnectionTimeout(
                Duration.ofMillis(500)
            );

            sender.setReadTimeout(
                Duration.ofMillis(200)
            );

            WebServiceTemplate template =
                new WebServiceTemplate();

            template.setMessageSender(sender);

            // Dùng một SOAP XML request hợp lệ trong fixture
            // và gọi sendSourceAndReceiveToResult(...) ở đây.
            // Assert exception phù hợp Spring-WS version,
            // đồng thời đo elapsed time và kiểm tra cleanup.

        } finally {
            server.stop(0);
        }
    }
}
~~~

Đây là **test skeleton** chỉ mô tả phần setup server/sender. Để test chạy và có assertion thực sự, cần gắn một SOAP request fixture, gọi template, kiểm tra exception, dọn request body và dùng bộ test framework thích hợp. Trong một số JVM/module configuration, `com.sun.net.httpserver.HttpServer` cần module `jdk.httpserver`. API setters `Duration` phụ thuộc Spring-WS version tương thích; với phiên bản khác phải điều chỉnh.

Mục đích của skeleton là làm rõ rằng **`MockWebServiceServer` không kiểm tra socket timeout**; transport tests cần thật sự đi qua HTTP.

### 20.3. Đo elapsed bằng monotonic clock

Trong integration test:

~~~java
long started = System.nanoTime();

try {
    // Gửi SOAP operation qua HTTP local test server.
} finally {
    long elapsedNanos = System.nanoTime() - started;
    Duration elapsed = Duration.ofNanos(elapsedNanos);

    // Ghi/assert elapsed với một độ dung sai
    // đủ cho CI, tránh test cực kỳ mong manh.
}
~~~

Đừng assert chính xác “200 ms phải kết thúc ở 200 ms” trên một máy CI dùng chung. Scheduler, JVM warm-up, GC và tải hệ thống có thể gây jitter. Nhưng cũng không để độ dung sai rộng đến mức test không còn phát hiện được cấu hình timeout bị vô hiệu hóa.

### 20.4. Kiểm tra cả việc tài nguyên được trả lại

Sau khi một request timeout, hãy thử gửi request thứ hai vào **cùng pool**. Nếu pool size là 1 và request đầu vẫn giữ connection dù caller đã ngừng chờ, request thứ hai có thể lease timeout. Đây là phép thử thực tế để phát hiện soft deadline không giải phóng network work.

## 21. Test connection pool lease timeout

Với Apache pooled HTTP client, có thể tạo tình huống có kiểm soát:

~~~text
Pool maxPerRoute = 1
Pool lease timeout = 200 ms

Thread A:
  gọi SOAP, remote giữ response 2 giây
  -> connection đang được A sử dụng

Thread B:
  bắt đầu sau A
  -> chờ pool connection
  -> không có connection sau 200 ms
  -> lease timeout
~~~

**Không kết luận server không thể kết nối** khi xảy ra lease timeout. Đây là sự cố resource contention trong chính client, mặc dù server có thể nhận requests bình thường.

Một bộ test tốt nên ghi rõ:

- Số connections tối đa của pool.
- Số requests cạnh tranh.
- Thời gian giữ connection của request A.
- Trần thời gian chờ lease của B.
- Loại exception/metric `pool_acquisition_timeout`.
- Connection được trả lại pool sau khi A hoàn tất hoặc bị hủy.

### 21.1. Test pooled connection đã bị đóng từ phía server

Load balancer thường đóng connections idle theo timeout riêng. Client giữ một connection trong pool có thể lấy ra connection stale:

~~~text
T0: Client gọi thành công, pool giữ keep-alive socket.
T1: Load balancer đóng socket idle.
T2: Client lấy connection cũ để gửi SOAP.
T3: Có thể gặp lỗi socket/reuse và cần connection mới.
~~~

Cần kiểm tra eviction/validation policy của HTTP connection manager, cơ chế retry có an toàn không và số attempts thực tế. Đừng chỉ tăng read timeout; lỗi stale connection không nhất thiết được giải quyết bằng cách chờ lâu hơn.

### 21.2. Đo pool metrics

Khi thư viện/monitoring cho phép, nên quan sát:

~~~text
pool.leased
pool.available
pool.pending
pool.max
connection.acquire.duration
connection.acquire.timeout.count
~~~

Tên metric thực tế phụ thuộc instrumentation stack. Dùng những tín hiệu đó để phân biệt partner chậm với việc client tự bão hòa.

## 22. Phân loại exception Spring-WS tại ranh giới client

`WebServiceTemplate` có thể ném các ngoại lệ khác nhau tùy nguồn lỗi:

- `WebServiceIOException`: lỗi I/O/transport trong một số đường đi.
- `WebServiceTransportException`: vấn đề HTTP transport/status theo Spring-WS.
- `SoapFaultClientException`: SOAP Fault được resolver xử lý theo cấu hình.
- `XmlMappingException`: JAXB/OXM không marshal/unmarshal được.
- Các exception khác do JAXB, TLS, XML parser hoặc custom client stack.

Các lớp exception và nguyên nhân lồng nhau có thể khác giữa Spring-WS versions. Vì vậy **không dùng tên exception chung làm nguồn duy nhất để biết timeout xảy ra ở đâu**.

### 22.1. Tạo mã phân loại ứng dụng

Ví dụ phân loại ở client adapter:

~~~java
public enum PartnerCallFailure {
    POOL_ACQUISITION_TIMEOUT,
    CONNECT_TIMEOUT,
    READ_TIMEOUT,
    DEADLINE_EXCEEDED,
    SOAP_FAULT,
    TRANSPORT_ERROR,
    TLS_SECURITY_ERROR,
    JAXB_CONTRACT_ERROR,
    UNKNOWN
}
~~~

Có thể dựa vào:

- Exception type từ HTTP client hoặc root cause.
- Phase được instrumentation ghi nhận.
- Việc đã nhận SOAP Fault hợp lệ hay chưa.
- Deadline budget còn lại tại thời điểm lỗi.
- Kết quả kiểm tra contract/QName.

Nếu cause chain không đủ để phân biệt một cách chắc chắn, ghi `TRANSPORT_ERROR` hoặc `UNKNOWN` thay vì suy diễn. Không “đoán” lỗi từ message string tùy thuộc locale/version.

### 22.2. Giữ nguyên nguyên nhân gốc

Một adapter có thể bọc lỗi:

~~~java
catch (WebServiceIOException io) {
    throw new PartnerUnavailableException(
        "Không thể hoàn tất SOAP call",
        io
    );
}
~~~

`PartnerUnavailableException` là exception của ứng dụng. Luôn giữ `cause` để có thể điều tra nội bộ an toàn. Không trả raw stack trace/certificate details cho caller bên ngoài.

### 22.3. Không retry mọi WebServiceIOException

Một timeout network không luôn chứng minh request chưa được server xử lý. Với operations ghi dữ liệu, cần xem idempotency và trạng thái chưa xác định. Với GET-like SOAP query, retry có thể an toàn hơn nhưng vẫn phải trong deadline và partner quota.

## 23. Observability: đo gì để biết timeout đang xảy ra?

Chỉ có một metric `soap_call_duration` là chưa đủ để tìm nguyên nhân.

Một dashboard hữu ích có thể theo dõi:

| Metric | Ý nghĩa |
|---|---|
| Operation end-to-end latency p50/p95/p99 | SLA/SLO thật của caller |
| HTTP attempt latency | Mỗi lần gọi network |
| Connect duration/timeouts | Vấn đề TCP/route/host |
| Pool acquire duration/timeouts | Local saturation |
| Time to first response byte | Server/proxy có gửi gì chưa |
| Response body download duration | Body lớn/trickle |
| JAXB marshal/unmarshal duration | XML mapping CPU/size |
| WS-Security sign/verify duration | Chi phí crypto/security |
| Retry attempts/backoff | Lượng thời gian/số requests bổ sung |
| Deadline exceeded count | Caller budget bị vượt |
| SOAP Fault by code | Lỗi tầng SOAP, tách transport |
| TLS handshake/certificate errors | Trust/protocol issues |
| Active threads/pool leased/pending | Resource pressure |

Không phải HTTP sender nào cũng cho tất cả metrics; có thể cần custom instrumentation hoặc OpenTelemetry/HTTP client monitoring tương ứng.

### 23.1. Ghi nhận một logical call và nhiều attempts

Ví dụ:

~~~text
logical_call_id: 7f0d...
operation: GetOrder
logical_budget_ms: 3500

attempt=1, duration=900ms, error=READ_TIMEOUT
backoff=100ms
attempt=2, duration=800ms, outcome=SOAP_RESPONSE

logical_elapsed=2050ms
logical_outcome=SUCCESS
~~~

Tổng logical elapsed gồm request marshaling, attempts, backoff và response handling nên không nhất thiết bằng tổng attempt durations. Thiết kế metric để không báo mỗi retry là một business call mới.

### 23.2. Metric labels tránh cardinality cao

Dùng các nhãn ổn định:

~~~text
partner=order-provider
operation=GetOrder
outcome=deadline_exceeded
transport=http
soap_version=1.1
~~~

Không dùng orderId, userId, request UUID, raw certificate fingerprint hoặc nguyên URL chứa query secrets làm nhãn metric. Những dữ liệu này có thể gây cardinality cực lớn và rò rỉ thông tin.

### 23.3. Logging timeout phải nói rõ pha

Ví dụ log có cấu trúc:

~~~text
partner=order-provider
operation=GetOrder
phase=pool_acquire
attempt=2
elapsed_ms=850
remaining_budget_ms=1750
outcome=timeout
~~~

Ghi thêm correlation ID được quản lý theo chính sách khi cần, nhưng không log nguyên SOAP request/response hoặc credentials. Với WS-Security, chữ ký, token và certificate materials phải được bảo vệ.

## 24. Kế hoạch triển khai và kiểm thử ở production-like staging

Đừng bật các timeout cực ngắn chỉ dựa trên local test, vì môi trường staging/production có DNS, TLS, proxy và latency khác.

Một kế hoạch triển khai:

1. **Đọc hợp đồng**: WSDL SOAP 1.1/1.2, endpoint URI, message size, WS-Security, operations có side effect.
2. **Chọn HTTP sender**: JDK connection hay Apache pooled client phù hợp traffic và dependency.
3. **Đặt timeout tường minh**: lease, connect, read/response; không dựa vào default.
4. **Đặt overall budget**: theo SLA/SLO của application và thời gian còn lại từ upstream.
5. **Thiết kế cancellation**: biết client có thể abort I/O và thu hồi connections khi deadline hết hay không.
6. **Đặt retry policy**: số lần, backoff, lỗi được retry, idempotency và quota.
7. **Thiết lập concurrency limits**: pool max, bulkhead/semaphore và rate limit.
8. **Chạy failure injection**: server treo headers, body nhỏ giọt, pool cạn, TLS fail, SOAP Fault.
9. **Test SOAP contract**: JAXB, XML namespace, XSD, SOAPAction, WSDL binding và generated client độc lập.
10. **Load test**: p95/p99, throughput, memory, GC, active threads, pool pressure.
11. **Rollout có giám sát**: bật cho một tỷ lệ traffic hoặc một nhóm đối tác/operation nếu kiến trúc cho phép.
12. **Chuẩn bị rollback**: nếu timeout quá ngắn gây false timeout hoặc retry storm.

### 24.1. Môi trường phát triển nhanh có thể che lỗi

Một SOAP server cùng máy với client có round-trip vài mili giây và không cần TLS thật. Điều đó không đo được latency xuyên vùng mạng, proxy, HSM signing, certificate validation, cold connection hoặc đối tác bị quá tải.

Nên dùng latency injection và production-like certificates/proxy cấu hình an toàn trong staging để phát hiện timeout ngân sách không thực tế.

### 24.2. Không dùng timeout để che lỗi contract

Nếu `marshalSendAndReceive` liên tục báo JAXB unexpected element, tăng read timeout không giải quyết được. Nếu server trả SOAP Fault do SOAPAction sai, tăng connect timeout cũng vô ích. Phân loại lỗi đúng trước khi thay timeout.

## 25. Bài thực hành: thiết kế budget cho GetOrder và SubmitPayment

Giả sử hệ thống có hai operations:

| Operation | Ngữ nghĩa | Mục tiêu thời gian |
|---|---|---|
| `GetOrder` | Truy vấn trạng thái đơn hàng | 3 giây |
| `SubmitPayment` | Có thể tạo side effect | 5 giây |

Bộ phận tích hợp dùng SOAP client Spring-WS, JAXB `ObjectFactory`/`JAXBElement`, `WebServiceTemplate` và HTTPS. Đối tác có giới hạn 30 concurrent calls và yêu cầu SOAP 1.1 với WS-Security Timestamp + Signature.

### 25.1. Các nhiệm vụ

1. Tạo XSD/WSDL tối thiểu cho request/response hai operations, ghi rõ QName.
2. Cấu hình `Jaxb2Marshaller` và SOAP message factory đúng binding.
3. Chọn HTTP sender JDK hay Apache pooled client và giải thích lý do.
4. Đặt pool max-per-route không vượt chính sách đối tác, có bulkhead/rate limit khi cần.
5. Chọn lease, connect, read/response timeouts tường minh.
6. Tạo `DeadlineBudget` một lần tại entry point của mỗi operation.
7. Viết diagram/timeline gồm JAXB, pool, TCP, TLS, WS-Security, remote server và response parse.
8. Cho `GetOrder` retry tối đa hai attempts nếu lỗi được phân loại retryable, luôn dùng remaining budget.
9. Xác định `SubmitPayment` chỉ được retry khi có cơ chế idempotency và policy đối tác rõ.
10. Test normal SOAP response qua `MockWebServiceServer`.
11. Test SOAP Fault riêng, không nhầm với network timeout.
12. Test read timeout bằng HTTP server cố tình không trả headers.
13. Test trickle response để chứng minh read timeout không bảo đảm tổng deadline.
14. Test connection pool max=1 với hai calls cạnh tranh.
15. Test TLS trust failure không làm client tắt certificate validation.
16. Test caller hết deadline và kiểm tra resource được thu hồi.
17. Test retry không làm vượt tổng attempts, tổng budget và partner quota.
18. Đo end-to-end p95/p99 với WS-Security và connection reuse.
19. Viết dashboard có outcome tags tách lease/connect/read/deadline/SOAP Fault.
20. Mô tả rollback nếu sau deploy lỗi deadline tăng đột biến.

**Tiêu chí đạt:** Không có timeout vô hạn ngoài chủ đích; tổng budget được theo dõi và ràng buộc bằng transport cancellation phù hợp; không retry operation có side effect một cách mù quáng; có kiểm thử giao thức, lỗi mạng, pool và SOAP Fault; không làm suy yếu TLS/WS-Security.

### 25.2. Hai tình huống suy luận

**Tình huống A:** Connect timeout 1 giây, read timeout 3 giây, server trả một fragment XML mỗi 2 giây và tổng body mất 20 giây. Vì sao client có thể không timeout ở lần đọc nào nhưng người dùng vẫn đợi 20 giây? Cần thêm cơ chế nào?

**Tình huống B:** Client gọi `SubmitPayment`, timeout sau 4 giây và không biết server đã xử lý thanh toán hay chưa. Có được retry ngay không? Thiết kế cần bổ sung những dữ liệu/hợp đồng gì để retry an toàn?

## 26. Checklist trước khi đưa timeout vào production

- [ ] Có overall budget/SLO cho từng SOAP operation và upstream caller.
- [ ] Phân biệt connect timeout, read/response timeout và pool lease timeout.
- [ ] Không cộng connect+read như một tổng deadline bảo đảm.
- [ ] Có xử lý DNS, proxy, TLS, upload, download và JAXB trong timeline.
- [ ] `WebServiceTemplate` được gắn đúng `WebServiceMessageSender`.
- [ ] Dùng đúng API timeout theo Spring-WS/HttpClient version, không trộn HttpClient 4/5.
- [ ] Không đặt timeout 0/vô hạn ngoài chủ đích và chính sách.
- [ ] Có connection pool sizing, per-route limit và backpressure.
- [ ] Budget được tạo một lần, mỗi retry dùng remaining budget.
- [ ] Retry có max attempts, backoff, timeout budget và idempotency policy.
- [ ] HTTP client có khả năng cancel/abort và test thu hồi tài nguyên khi quá hạn.
- [ ] Không coi `Future.get(timeout)` hoặc `orTimeout` là bảo đảm tự đóng socket.
- [ ] SOAP Fault được phân loại khác HTTP/transport/JAXB errors.
- [ ] Không retry mọi SOAP Fault hoặc payment operation.
- [ ] TLS certificate validation và WS-Security vẫn được bảo vệ.
- [ ] Có test server treo headers, body nhỏ giọt và pool exhaustion.
- [ ] Có test cancellation, retry storm và concurrency.
- [ ] Có JAXB/XSD/WSDL/SOAPAction compatibility tests riêng.
- [ ] Quan sát latency end-to-end p50/p95/p99, attempt times và error phase.
- [ ] Không log raw SOAP payload, tokens, passwords hoặc secrets.
- [ ] Có load test production-like và rollout/rollback plan.

## 27. Ghi nhớ

- **Connect timeout** giới hạn giai đoạn kết nối theo HTTP stack; nó không đồng nghĩa DNS/TLS và toàn lời gọi luôn hoàn tất trong thời gian đó.
- **Read/response timeout** giới hạn một phần hoạt động nhận phản hồi; tùy implementation, body nhỏ giọt vẫn có thể kéo dài tổng thời gian.
- **Pool acquisition timeout** giới hạn thời gian đợi một connection từ connection pool; nó phát hiện tình trạng bão hòa ở phía client.
- **Overall deadline** là ngân sách chung cho JAXB, SOAP interceptor, pool, network, TLS, server, response processing và retry.
- **Các timeout riêng lẻ không tự tạo hard deadline.** Muốn ràng buộc tổng phải có cơ chế chuyển remaining budget xuống transport và hủy I/O khi hết hạn.
- **Retry không tự động an toàn:** SOAP operation có side effect cần idempotency/reconciliation và budget rõ ràng.
- **SOAP Fault khác transport timeout**: chỉ khi nhận một SOAP Fault hợp lệ mới có thể đi qua luồng Fault resolver.
- **Test transport phải đi qua HTTP thật hoặc network simulator**; `MockWebServiceServer` hữu ích cho SOAP contract nhưng không thay test socket timeout.
- **Security và reliability phải đi cùng nhau:** không tắt TLS/certificate validation hoặc bỏ WS-Security để tránh lỗi timeout.

**Câu hỏi tự kiểm tra:** Một SOAP client dùng `WebServiceTemplate` và `HttpUrlConnectionMessageSender` với connect timeout 2 giây, read timeout 4 giây. Caller có SLO tổng 5 giây nhưng một server trả response từng đoạn cách nhau 3 giây khiến `marshalSendAndReceive` mất 18 giây. Hãy giải thích vì sao hai timeout chưa bảo đảm SLO, phân biệt read timeout và overall deadline, đề xuất cách áp dụng remaining budget/cancellation, và nêu ba kiểm thử để chứng minh giải pháp không để lại socket hoặc thread bị giữ lâu sau khi caller hết thời gian.



