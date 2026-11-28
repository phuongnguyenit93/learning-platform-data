# Kích thước payload, JAXB, DOM và mức sử dụng bộ nhớ

> **Chương:** Hiệu năng và vận hành  
> **Module:** SPRING_WEB_SERVICES — phát triển dịch vụ SOAP theo hướng contract-first với Spring Web Services, thiết kế XSD/WSDL, ánh xạ JAXB và xây dựng endpoint cùng SOAP client; xử lý SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích để tích hợp hệ thống doanh nghiệp ổn định.

## 1. Vì sao kích thước XML trên mạng không phản ánh heap cần dùng?

Một SOAP message có thể chỉ chiếm vài megabyte khi truyền qua HTTP nhưng tiêu thụ bộ nhớ lớn hơn đáng kể trong JVM. Khi nhận message, ứng dụng có thể đồng thời giữ byte buffer từ transport, ký tự XML sau decode, cấu trúc SOAP message, cây DOM, JAXB object graph, các chuỗi/collection trong business layer và bản sao được tạo khi chuyển đổi dữ liệu.

Vì vậy, câu hỏi vận hành không chỉ là “request có bao nhiêu KB?” mà còn là:

- HTTP body có bao nhiêu bytes sau và trước giải nén?
- XML có bao nhiêu characters và bao nhiêu elements/attributes?
- Có bao nhiêu binary bytes được nhúng Base64 hoặc gửi qua MIME attachment?
- Parser/builders có tạo DOM tree hay đọc streaming?
- JAXB tạo bao nhiêu Java objects và giữ chúng sống bao lâu?
- Có bước nào copy toàn bộ payload hoặc serialize lại response không?
- Bao nhiêu requests lớn có thể chạy đồng thời?

Trong SOAP enterprise, một payload lớn có thể làm tăng allocation rate, garbage collection, latency và nguy cơ OutOfMemoryError. Nếu nhiều request lớn cùng đến, vấn đề thường xuất hiện ở concurrency chứ không chỉ ở kích thước của một message.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt wire size, compressed size, decoded XML size, binary size và heap footprint.
2. Giải thích chi phí bộ nhớ của SOAP Envelope, Base64, DOM và JAXB object graph.
3. Chọn DOM, SAX hoặc StAX theo cách xử lý dữ liệu.
4. Nhận biết khi nào JAXB tạo object graph phù hợp và khi nào cần streaming.
5. Giảm memory amplification bằng MTOM/attachments và xử lý dữ liệu theo luồng.
6. Đặt giới hạn kích thước, độ sâu, số elements và concurrency an toàn.
7. Đo heap, allocation, GC và latency bằng workload có thể tái lập.
8. Tối ưu Spring-WS mà không làm suy yếu XSD validation, XML security hoặc contract.

**Nguyên tắc:** Đo memory theo toàn bộ pipeline và concurrency. Không lấy Content-Length làm đại diện cho heap usage.

## 2. Các loại kích thước cần phân biệt

| Đại lượng | Ý nghĩa | Dùng để kiểm soát |
|---|---|---|
| Wire bytes | Bytes truyền qua HTTP/TLS, có thể đã nén | Bandwidth, request limit ở ingress |
| Compressed bytes | Kích thước body sau compression | Network quota, decompression ratio |
| Decompressed bytes | Bytes sau gzip/deflate | Chống decompression bomb |
| XML characters | Số ký tự XML sau decode | Parser input và text limits |
| XML structural size | Elements, attributes, depth, namespaces | CPU/heap parser |
| Attachment bytes | Binary parts trong MIME/MTOM | Disk/memory/stream limits |
| Java heap footprint | Objects/buffers/string/arrays đang sống | GC và heap capacity |
| Retained heap | Objects còn reachable sau xử lý | Leak và long-lived caches |

Ví dụ, một HTTP body gzip 1 MB có thể giải nén thành XML 40 MB. XML lại có thể chứa Base64 binary; khi decode, binary tạo một byte array khác. JAXB mapping sau đó có thể giữ các String hoặc collection khác. Những số này mô tả các tầng khác nhau, không được cộng/trừ tùy tiện vì có thể có sharing/copy tùy implementation.

### 2.1. Ghi nhận metric đúng thời điểm

Đối với server, nên ghi:
- Compressed và decompressed request bytes nếu ingress hỗ trợ đo.
- Processing time theo phase.
- Payload type/operation đã phân loại, không gắn toàn bộ XML vào metric labels.
- Số attachments và bytes.
- Kết quả validation/parse.
- Concurrent in-flight requests.

Heap usage đo ở JVM/process, không phải từ một request đơn lẻ. Muốn quy đổi request size thành memory cost cần benchmark/profile theo payload shape và concurrency thực tế.

## 3. SOAP Envelope và cấu trúc XML tạo overhead

SOAP message gồm Envelope, Header tùy chọn và Body. Business payload chỉ là một phần của document. Header có thể chứa WS-Security, WS-Addressing, correlation metadata hoặc custom headers; mỗi phần thêm elements, attributes, namespaces và có thể thêm cryptographic material.

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wsse="...">
  <soap:Header>
    <!-- Security, addressing, correlation metadata -->
  </soap:Header>
  <soap:Body>
    <ord:SubmitOrderRequest xmlns:ord="urn:example:orders:v1">
      <ord:orderId>ORD-1001</ord:orderId>
      <ord:quantity>2</ord:quantity>
    </ord:SubmitOrderRequest>
  </soap:Body>
</soap:Envelope>
~~~

Một payload nhỏ có thể tạo nhiều objects nếu có nhiều nested elements. Ngược lại, một text node rất lớn có thể tạo một String/char array lớn dù số elements ít. Vì vậy cần kiểm cả kích thước text và cấu trúc.

## 4. Base64 làm tăng kích thước dữ liệu

Khi binary được nhúng trực tiếp vào XML bằng Base64, kích thước text tăng khoảng một phần ba so với binary gốc, chưa tính whitespace và XML markup. Công thức xấp xỉ:

[
L_{base64}=4\times\lceil N/3\rceil
]

Trong đó N là số binary bytes và L là số Base64 characters.

Ví dụ, một file 15 MiB khi Base64 hóa có khoảng 20 MiB ký tự trước khi tính Envelope/markup. Nếu XML parser tạo String/char representation và JAXB tạo byte[] sau decode, ứng dụng có thể đồng thời giữ nhiều representation của cùng dữ liệu.

### 4.1. Khi Base64 vẫn phù hợp

Base64 trong XML có thể chấp nhận được khi:
- Binary nhỏ và có giới hạn rõ.
- Payload cần đơn giản hóa cho consumer.
- Interoperability với client không hỗ trợ MTOM là yêu cầu.
- Không cần streaming attachment độc lập.

Không chọn Base64 cho file lớn chỉ vì mapping JAXB tiện. Đo cả peak heap và concurrency trước khi quyết định.

## 5. MTOM và MIME attachments giảm XML expansion

MTOM cho phép SOAP message tham chiếu binary data qua xop:Include và truyền bytes trong MIME attachment thay vì nhúng toàn bộ Base64 text trong XML. Đây có thể giảm XML text expansion và cho phép transport xử lý attachment riêng.

~~~xml
<ord:Document>
  <ord:fileName>invoice.pdf</ord:fileName>
  <ord:content>
    <xop:Include
        href="cid:attachment-001"
        xmlns:xop="http://www.w3.org/2004/08/xop/include"/>
  </ord:content>
</ord:Document>
~~~

MIME package chứa root SOAP part và attachment part có Content-ID tương ứng.

### 5.1. MTOM không tự động bảo đảm streaming

MTOM giảm Base64 expansion nhưng implementation vẫn có thể buffer attachment trong memory hoặc spool ra disk. Cần kiểm tra:
- SOAP message factory và attachment support đang dùng.
- Marshaller mapping cho binary content.
- HTTP sender/receiver buffering.
- Attachment threshold và disk-spooling behavior nếu có.
- Stream lifecycle và cleanup khi client/server ném exception.
- Signature/encryption policy đối với attachment.
- Consumer thật có hỗ trợ MTOM hay không.

### 5.2. Kiểm tra tính toàn vẹn của attachment

Không chỉ assert attachment tồn tại. Test bytes/length/checksum ở hai phía, Content-ID/reference, filename metadata và xử lý khi stream bị truncate. Với file nhạy cảm, đảm bảo authorization trước khi ghi ra disk hoặc chuyển tiếp đến downstream.

## 6. DOM: tiện lợi nhưng tốn bộ nhớ

DOM biểu diễn XML thành cây objects có thể truy cập ngẫu nhiên. Mỗi element, attribute, text node, namespace và quan hệ cha-con có object/metadata overhead. Một payload XML text liên tục có thể trở thành nhiều objects trong heap.

DOM phù hợp khi:
- Message nhỏ/vừa, cần truy cập nhiều vị trí theo thứ tự tùy ý.
- Cần sửa nhiều node trước serialize.
- API/framework bắt buộc Source/DOM representation.
- Dữ liệu được giới hạn rõ và có heap budget.

DOM ít phù hợp cho payload rất lớn chỉ cần đọc tuần tự, nhất là khi nhiều request đồng thời. Tránh tạo thêm DOM document thứ hai sau khi message factory đã xây representation tương tự.

## 7. SAX: xử lý theo sự kiện

SAX parser phát các events như startElement, characters và endElement khi duyệt tài liệu. Ứng dụng có thể xử lý từng record, chỉ giữ state cần thiết và loại bỏ phần đã xử lý.

~~~java
public final class OrderLineHandler
        extends org.xml.sax.helpers.DefaultHandler {

    private boolean inLine;
    private final List<OrderLine> lines = new ArrayList<>();

    @Override
    public void startElement(
            String uri, String localName, String qName,
            org.xml.sax.Attributes attributes) {
        if ("line".equals(localName)) {
            inLine = true;
        }
    }

    @Override
    public void endElement(
            String uri, String localName, String qName) {
        if ("line".equals(localName)) {
            inLine = false;
        }
    }

    @Override
    public void characters(char[] ch, int start, int length) {
        if (inLine) {
            // Tích lũy hoặc xử lý text theo schema thực tế.
        }
    }
}
~~~

Đây là skeleton minh họa. Trong SAX, một text node có thể được chia thành nhiều callbacks; không giả định một lần characters() nhận toàn bộ nội dung. Handler cần state machine cho nested elements, namespaces, escaping và boundaries.

SAX phù hợp dữ liệu lớn xử lý tuần tự, nhưng khó truy cập ngẫu nhiên và code handler có thể phức tạp. Nếu cần JAXB-generated DTO đầy đủ, SAX thuần không tự chuyển message thành toàn bộ object graph.

## 8. StAX: pull parsing và kiểm soát luồng đọc

StAX cung cấp pull API: ứng dụng chủ động đọc events từ XMLStreamReader. Nó hữu ích khi cần duyệt tuần tự nhưng muốn kiểm soát flow rõ hơn SAX.

~~~java
XMLInputFactory factory = XMLInputFactory.newFactory();

// Cấu hình chống external entities theo provider và policy.
factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
factory.setProperty(
        "javax.xml.stream.isSupportingExternalEntities", false);

try (InputStream input = requestBodyStream) {
    XMLStreamReader reader =
            factory.createXMLStreamReader(input);

    try {
        while (reader.hasNext()) {
            int event = reader.next();

            if (event == XMLStreamConstants.START_ELEMENT) {
                String localName = reader.getLocalName();
                // Xử lý element hiện tại, chỉ giữ state cần thiết.
            }
        }
    } finally {
        reader.close();
    }
}
~~~

Đây là ví dụ JAXP/StAX minh họa. Phải kiểm tra property names, defaults và behavior trên XML provider cụ thể; không coi một property unsupported là đã được bảo vệ. Stream được đóng theo ownership contract của API, tránh đóng input stream do container quản lý nếu application không sở hữu nó.

StAX không tự biến Spring-WS endpoint thành streaming. Nếu một tầng trước đó đã buffer toàn HTTP body hoặc build DOM/SOAPMessage, lợi ích heap của parser pull có thể bị giới hạn.

## 9. JAXB: object graph thuận tiện và chi phí allocation

JAXB chuyển XML thành Java object graph. Điều này giúp business code làm việc với DTO có kiểu dữ liệu rõ thay vì tự duyệt XML, nhưng mỗi field/element có thể tạo object, String, collection hoặc wrapper.

~~~java
SubmitOrderRequest request =
        (SubmitOrderRequest) marshaller.unmarshal(source);

for (OrderLine line : request.getLines()) {
    process(line);
}
~~~

Nếu request chứa hàng trăm nghìn lines, JAXB có thể tạo collection và object cho toàn bộ lines trước khi business code bắt đầu xử lý. Ngay cả khi xử lý từng line trong vòng lặp, graph vẫn còn reachable từ request cho đến khi reference được thả.

### 9.1. JAXB phù hợp khi

- Payload có kích thước bounded.
- Business logic cần toàn bộ request để validate transaction.
- DTO rõ ràng tăng an toàn kiểu và maintainability.
- Collection size được giới hạn.
- Heap budget và concurrent load đã được đo.

### 9.2. Khi nào cần cách tiếp cận khác?

Xem streaming hoặc paging khi:
- XML chứa rất nhiều repeating elements độc lập.
- Business xử lý từng record không cần giữ toàn bộ request.
- Peak memory tỷ lệ gần tuyến tính với số records và gây GC pressure.
- Payload vượt giới hạn thực tế của consumer/partner.
- Có thể thiết kế contract theo batch/chunk hoặc attachment stream.

Không chuyển sang SAX/StAX chỉ vì “streaming nhanh hơn”. Cần đo bottleneck; nhiều workload nhỏ/vừa sẽ đơn giản và đủ nhanh với JAXB.

## 10. Streaming end-to-end: điểm nghẽn có thể nằm trước parser

Một pipeline có thể gồm:

~~~text
HTTP socket
  → HTTP server/container buffer
  → compression/decompression
  → SOAP MessageFactory
  → SOAP Header/Body representation
  → validation/interceptors
  → JAXB unmarshal
  → business mapper
  → database/downstream
~~~

Nếu HTTP layer đọc toàn body vào memory, message factory dựng DOM hoặc security interceptor cần toàn bộ signed parts, việc dùng StAX ở business layer không loại bỏ các buffers phía trước.

Hãy kiểm từng stage:
1. Transport có stream hay buffer toàn body?
2. MessageFactory có materialize DOM/attachments không?
3. XSD validation cần đọc lại payload hay buffer?
4. WS-Security phải canonicalize/signature-check những phần nào?
5. JAXB tạo toàn DTO hay có một streaming binding path?
6. Business layer giữ bao nhiêu records cùng lúc?
7. Logging/tracing có copy payload thành String không?

Không tuyên bố hệ thống “streaming” chỉ vì một method nhận InputStream. Streaming là thuộc tính của toàn pipeline và vòng đời dữ liệu.

## 11. Spring-WS message factory và OXM lựa chọn

Spring-WS có các message factory và transport abstractions khác nhau. SAAJ thường làm việc với SOAPMessage representation; các implementation như Axiom có cách materialize/lazy/streaming khác nhau tùy version và cấu hình. Không mặc định chuyển message factory sẽ làm heap giảm một tỷ lệ nhất định.

Khi chọn:
- Kiểm compatibility với SOAP version, WS-Security, attachments và interceptors.
- Đọc behavior của Spring-WS version và underlying implementation.
- Test actual payload sizes và concurrency.
- Kiểm memory khi validation/security enabled, không chỉ benchmark parser trần.
- So sánh correctness và interoperability trước/sau.

Jaxb2Marshaller cũng có chi phí context/model initialization. Tái sử dụng configured marshaller/context khi thread-safety contract của version cho phép; không tạo JAXBContext/Jaxb2Marshaller mới cho mỗi request nếu startup/metadata setup đáng kể. Tránh cache không giới hạn các schema contexts theo user input.

## 12. Đo memory: heap, allocation, GC và retained objects

Không đo bằng một lần gọi System.gc() hay nhìn một ảnh heap usage trong Task Manager. Cần quan sát cả allocation rate, retained heap, GC pauses, CPU và throughput.

### 12.1. Các nguồn evidence

- Java Flight Recorder (JFR): allocation samples, object allocation, GC pauses, thread activity.
- Java Mission Control hoặc profiler tương thích: heap/object analysis.
- Heap dump: retained objects, dominator tree và reference paths.
- GC logs: allocation pressure, young/old collections, pause time.
- Micrometer/application metrics: request sizes, latency, in-flight count, error rate.
- Load test tool: throughput và p95/p99 latency theo payload profile.

### 12.2. Câu hỏi khi đọc heap dump

- Có nhiều byte[]/char[] lớn đang sống không?
- Có String chứa toàn bộ SOAP XML hoặc Base64 không?
- DOM Node/Text objects chiếm tỷ lệ nào?
- JAXB DTO collections giữ quá nhiều elements?
- Attachment buffers/temporary buffers bị retain?
- Request/response objects còn được giữ trong async queue hoặc logs?
- Có cache theo message/user không giới hạn?
- Một object lớn được reference bởi singleton, retry queue hay ThreadLocal?

### 12.3. Instrumentation an toàn

Ghi số liệu tổng hợp theo operation/version; tránh đưa full SOAP body vào metric labels/logs. Không tạo tag chứa orderId, partner ID không giới hạn hoặc payload snippets vì gây high cardinality và lộ dữ liệu. Dùng correlation ID có kiểm soát cho trace, và redaction trước khi lưu captures.

## 13. Benchmark công bằng và có thể tái lập

So DOM, JAXB, SAX hoặc StAX chỉ có ý nghĩa khi workload và môi trường giống nhau.

Cố định:
- JDK/vendor/version và heap settings.
- Spring-WS/JAXB/XML provider versions.
- Schema, message factory và interceptors.
- Payload fixtures: nhỏ, trung bình, lớn; shallow/deep; text-heavy; many-elements; binary.
- Số concurrent requests và warm-up.
- Validation/security bật hay tắt.
- Response behavior và downstream latency.

Đo:
- Throughput (requests/second).
- p50/p95/p99 latency.
- Allocation bytes/request.
- Peak/retained heap.
- GC count/pause time.
- CPU utilization.
- Error/rejection rate.

Không so benchmark StAX parser trần với end-to-end JAXB+WS-Security pipeline rồi kết luận StAX làm ứng dụng nhanh hơn. So đúng cùng công việc/cùng checks. Dùng nhiều runs và report variance.

## 14. Kiểm soát payload size và complexity ở ingress

Giới hạn ở HTTP ingress/container/gateway thường phải áp dụng trước khi parser tạo nhiều objects. Đặt các controls phù hợp:
- Maximum compressed request bytes.
- Maximum decompressed bytes.
- Maximum XML document bytes/chars.
- Maximum element depth.
- Maximum attributes per element.
- Maximum text node size nếu provider hỗ trợ.
- Maximum number of elements/records.
- Maximum attachments và tổng attachment bytes.
- Decompression ratio hoặc CPU budget nếu có compression.
- Per-request timeout và concurrent in-flight limit.

Tên cấu hình cụ thể phụ thuộc servlet container, message factory, XML parser, proxy và Spring-WS version. Đừng chỉ thêm validation ở endpoint vì lúc đó phần lớn parse/allocation có thể đã xảy ra.

### 14.1. Reject sớm và rõ ràng

Payload vượt limit cần bị từ chối với error mapping đã định nghĩa, không trả stack trace hoặc heap details. Log kích thước/phase/reason code, không log toàn message. Có giới hạn cho cả request và response generation; response lớn cũng có thể làm server heap cạn.

### 14.2. Không nới limit chỉ để chữa lỗi tích hợp

Nếu đối tác gửi file quá lớn, cân nhắc MTOM, chunking theo nghiệp vụ, pagination, asynchronous document exchange hoặc object storage reference có authorization. Nới payload limit làm tăng exposure cho mọi requests cùng endpoint.

## 15. Concurrency nhân peak memory

Một request 30 MB heap footprint có thể không đáng lo ở concurrency 1 nhưng trở thành áp lực lớn khi 40 requests cùng parse. Số request in-flight, buffering ở tầng transport, response overlap và GC pause tạo hiệu ứng cộng dồn.

Ước tính sơ bộ:

[
M_{inflight}approx C	imes M_{request,peak}
]

Trong đó C là số request đồng thời và M_request,peak đo từ profile. Đây chỉ là budget heuristic; không phải heap sizing formula chính xác vì allocations có lifetime khác nhau, buffers có thể được chia sẻ, và JVM cần headroom cho baseline/application/GC.

Điều chỉnh:
- Giới hạn concurrency cho operations payload nặng.
- Dùng bounded executor/queue, tránh queue vô hạn giữ toàn request.
- Áp dụng admission control/load shedding.
- Tách workload lớn khỏi endpoint latency-sensitive.
- Giám sát heap occupancy và GC pauses.
- Đảm bảo backpressure/queue limits ở downstream.

Không tăng heap không giới hạn để che memory amplification; điều đó có thể kéo dài GC pauses và làm sự cố nghiêm trọng hơn.

## 16. Logging và tracing cũng có thể nhân đôi payload

Các logging interceptors đôi khi đọc/copy SOAP Body thành String để log. Nếu request lớn và nhiều concurrent calls, logging có thể giữ thêm byte[], char[] và String trong heap. Log cả Base64 attachment có thể phình dung lượng và lộ dữ liệu.

Khuyến nghị:
- Log operation, duration, status, message ID và payload byte counts.
- Bật full payload logging chỉ trong sandbox có redaction/size cap/short retention.
- Không log credentials, tokens, signatures, personal data hoặc file contents.
- Đặt giới hạn cho log event; truncation phải được đánh dấu rõ.
- Không dùng payload/XML làm metric labels.
- Tracing nên propagation correlation metadata, không copy toàn Body.

## 17. Cấu trúc xử lý large payload

Nếu business semantics cho phép xử lý từng record, tránh tạo list khổng lồ:

~~~java
for (OrderLine line : request.getLines()) {
    repository.save(map(line));
}
~~~

Đoạn trên vẫn không streaming nếu request JAXB đã chứa toàn bộ List. Để xử lý thật sự theo luồng, contract/transport/parser cần cung cấp record từng phần; business layer xử lý và release references theo batch.

Thiết kế các lựa chọn:
- Chia request thành batches có maximum records/bytes.
- Dùng asynchronous job nhận metadata và attachment.
- Chuyển file lớn qua MTOM hoặc object storage có token/access control ngắn hạn.
- Dùng pagination cho response danh sách lớn.
- Có checkpoint/idempotency khi xử lý từng batch.
- Xác định partial failure semantics và retry boundaries.

Không đổi contract sang streaming nếu client/server không thống nhất framing, ordering, fault và resume semantics.

## 18. Case study: tăng memory sau khi bật audit logging

### 18.1. Hiện tượng

Một SOAP endpoint nhận chứng từ XML với binary scan được Base64. Trước đây throughput bình thường, sau khi bật request logging, p99 latency tăng, young GC chạy thường xuyên và heap dump có nhiều char[] lớn cùng String giữ SOAP Body.

### 18.2. Phân tích

- HTTP body được buffer khi nhận.
- MessageFactory tạo SOAP message representation.
- JAXB tạo DTO và byte[] sau Base64 decode.
- Logging interceptor serialize/copy payload thành một String lớn.
- Log appender async queue giữ String lâu hơn request.
- Concurrent requests tạo nhiều representation cùng lúc.

### 18.3. Cách khắc phục

1. Dùng metrics về bytes và operation thay full-body logging.
2. Đặt giới hạn log event và bỏ qua attachments.
3. Dùng MTOM cho binary lớn nếu consumer support.
4. Kiểm tra HTTP/message factory buffering.
5. Giới hạn concurrent requests/file size.
6. Profile lại với logging bật vì đó là production path thực.
7. Giữ regression load test cho p95/p99, allocation/request và GC.

### 18.4. Tiêu chí nghiệm thu

- Payload hợp lệ vẫn parse/validate đúng.
- Rejected oversized request không tạo side effect.
- Heap/allocation và p99 trở lại budget đã đặt ở cùng load profile.
- Logging không giữ toàn SOAP Body hoặc attachment.
- Attachment bytes/checksum không đổi.
- Security/validation/interoperability tests vẫn pass.

## 19. Bài tập tự luyện

**Bài 1 — Wire size:** HTTP body 2 MB có thể dùng hơn 2 MB heap?

**Đáp án:** Có. Decode, parser structures, DOM, JAXB objects, copies và business representations có thể làm heap footprint lớn hơn wire size.

**Bài 2 — Compression:** Compressed body nhỏ chứng minh payload an toàn về memory?

**Đáp án:** Không. Phải giới hạn decompressed bytes/ratio và XML structural complexity.

**Bài 3 — Base64:** Binary 12 MiB nhúng Base64 tạo khoảng bao nhiêu characters?

**Đáp án:** Xấp xỉ 16 MiB Base64 characters, chưa tính XML markup/whitespace.

**Bài 4 — DOM:** Vì sao DOM tốn memory hơn đọc streaming?

**Đáp án:** DOM giữ node objects, attributes, text, namespace và parent/child relationships cho toàn document; streaming chỉ cần giữ state/buffer hiện tại nếu pipeline không buffer trước đó.

**Bài 5 — JAXB:** Vòng lặp xử lý từng item sau unmarshal có đảm bảo streaming?

**Đáp án:** Không. JAXB có thể đã tạo toàn bộ object graph/list trước khi vòng lặp chạy.

**Bài 6 — StAX:** Dùng XMLStreamReader có đảm bảo Spring-WS không buffer message?

**Đáp án:** Không. MessageFactory, transport, validation và interceptors có thể đã buffer/materialize trước parser.

**Bài 7 — MTOM:** Dùng MTOM chắc chắn không còn attachment buffering?

**Đáp án:** Không. Phụ thuộc message factory, sender, marshaller và threshold/spooling configuration; phải profile.

**Bài 8 — Concurrency:** Vì sao cùng payload size có thể gây OOM khi tải tăng?

**Đáp án:** Nhiều requests giữ đồng thời buffers/DOM/JAXB objects; peak memory tăng theo in-flight work và lifetime.

**Bài 9 — Logging:** Chỉ log SOAP body có thể làm heap tăng?

**Đáp án:** Có. String/char[] copies và async logging queues có thể retain payload lớn.

**Bài 10 — Benchmark:** So parser StAX trần với end-to-end JAXB+WS-Security có công bằng?

**Đáp án:** Không. Cần cùng workload, validation/security, warmup, JDK, payload và concurrency.

**Bài 11 — Giới hạn:** Nên chỉ limit XML bytes ở endpoint method?

**Đáp án:** Không. Parser/transport có thể đã cấp phát trước khi endpoint được gọi; đặt ingress/message limits sớm.

**Bài 12 — Heap:** Có thể nới Xmx vô hạn để xử lý large SOAP payload?

**Đáp án:** Không. Cần budget theo concurrency, bounded queues, payload limits và profiling; heap lớn không loại bỏ memory amplification.

## 20. Checklist hiệu năng và vận hành

### Payload measurements
- [ ] Phân biệt wire/compressed/decompressed/XML/attachment bytes.
- [ ] Đo elements, depth, attributes và repeated-item count.
- [ ] Có payload profiles nhỏ/vừa/lớn và worst-case hợp lệ.
- [ ] Ước tính memory theo concurrent in-flight requests từ profiler.

### Parser và binding
- [ ] Xác định MessageFactory thực tế và buffering behavior.
- [ ] Xác định JAXB object graph/collection sizes.
- [ ] DOM chỉ dùng khi cần random access và payload bounded.
- [ ] SAX/StAX chỉ chọn khi pipeline thực sự streaming end-to-end.
- [ ] Không tạo parser/marshaller/context mới không cần thiết mỗi request.
- [ ] Kiểm tra thread-safety/lifecycle của validator và marshaller theo version.

### Binary/attachments
- [ ] Đánh giá Base64 expansion.
- [ ] Dùng MTOM khi binary lớn và consumers hỗ trợ.
- [ ] Test attachment byte integrity/checksum.
- [ ] Kiểm memory/disk spooling và cleanup khi exception.
- [ ] Signature/encryption policy bao phủ attachments khi cần.

### Resource limits
- [ ] Giới hạn compressed và decompressed HTTP body.
- [ ] Giới hạn XML bytes/depth/elements/text và attachment bytes.
- [ ] Có timeout, concurrency limit và bounded queues.
- [ ] Reject oversized/decompression-heavy payload trước business processing.
- [ ] Có load shedding/admission control cho workload lớn.
- [ ] Không nới limits chỉ để bỏ qua contract design kém.

### Profiling và observability
- [ ] JFR/GC logs/heap dump cho payload profiles.
- [ ] Đo allocation/request, retained heap, throughput, p95/p99 và GC pauses.
- [ ] Benchmark với cùng JDK/dependency/security/schema settings.
- [ ] Logging không copy toàn SOAP Body/attachments trong production.
- [ ] Metrics không dùng payload hoặc IDs vô hạn làm tags.
- [ ] Có regression load test và memory budget trong CI/performance environment.

**Ghi nhớ:** Kích thước payload trên HTTP chỉ là một đầu vào của bài toán bộ nhớ. SOAP parsing có thể tạo DOM, JAXB tạo object graph, Base64 phình binary thành text, logging và concurrency tiếp tục giữ thêm buffers/copies. Hãy đo toàn pipeline, giới hạn payload và complexity ở ingress, dùng MTOM cho binary lớn khi phù hợp, và chỉ chuyển sang SAX/StAX khi các tầng transport/message factory/validation thực sự hỗ trợ streaming. Mọi tối ưu phải giữ nguyên XSD validation, XML security, WS-Security và contract semantics.
