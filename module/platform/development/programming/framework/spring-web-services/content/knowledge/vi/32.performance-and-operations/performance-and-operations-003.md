# Streaming, payload caching và các thao tác làm tiêu thụ luồng dữ liệu

Trong Spring Web Services, một SOAP payload có thể được truy cập qua `Source`, `Result`, DOM, StAX hoặc JAXB object. Các API này có thể xử lý cùng XML nhưng **cách đọc payload quyết định message có thể được đọc lại hay không, dữ liệu có bị materialize vào bộ nhớ hay không và endpoint có thể tiếp tục xử lý sau interceptor hay không**.

Bài học thuộc chương **Hiệu năng và vận hành** của module `SPRING_WEB_SERVICES`. Module phát triển SOAP theo hướng contract-first với XSD/WSDL, JAXB, endpoint và SOAP client; đồng thời xử lý SOAP Fault, interceptor, XML security, WS-Security, TLS/chứng chỉ và kiểm thử tương thích. Tối ưu streaming phải giữ nguyên contract, thứ tự kiểm tra bảo mật và hành vi endpoint/client.

**Ba khái niệm cần tách biệt:**

- **Streaming API:** consumer đọc nội dung dần qua stream/cursor thay vì cần cây DOM hoặc byte array hoàn chỉnh.
- **Payload caching:** message implementation giữ payload đã đọc/materialize để lần truy cập sau có thể đọc lại.
- **End-to-end streaming:** từ HTTP transport đến message factory, interceptor, endpoint, business sink và response đều không buộc giữ toàn payload trong RAM. Một tầng materialize là đủ làm mất mục tiêu end-to-end.

Ví dụ hướng tới Java 17+, Spring-WS 4.1.x, Spring Framework 6.x và Apache Axiom khi dùng `AxiomSoapMessageFactory`. Các API/cấu hình cần đối chiếu với version thực tế. Không có SPECIAL_NOTE bổ sung cho bài này.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `Source`, `Result`, DOM, SAX, StAX và JAXB trong đường xử lý SOAP.
2. Giải thích payload có thể là one-shot hay repeatable và vì sao lần đọc đầu consume stream.
3. Hiểu khác biệt SAAJ/Axiom, đặc biệt `payloadCaching`, attachment caching và cache threshold.
4. Nhận ra thao tác làm consume payload: XPath, logging, validation, transform, JAXB unmarshal, interceptor và endpoint mapper.
5. Thiết kế pipeline đọc payload một lần, đồng thời giữ security/validation invariants.
6. Chọn khi nào cần cache/re-read và khi nào có thể dùng streaming.
7. Dùng `WebServiceTemplate` callback/extractor và repeatable resource ở client đúng vòng đời.
8. Đo heap, allocation, latency, GC, temp disk và backpressure thay vì suy luận từ tên API.
9. Kiểm thử read-once, payload lớn, lỗi giữa stream, concurrent load và tương thích SOAP.

## 1. Payload đi qua những tầng nào?

~~~mermaid
flowchart LR
    A["HTTP socket / TLS"] --> B["Message sender / servlet"]
    B --> C["SOAP message factory"]
    C --> D["SOAP Envelope + Header + Payload"]
    D --> E["Endpoint interceptors"]
    E --> F["Endpoint mapping / adapter"]
    F --> G["JAXB / Source / DOM / StAX"]
    G --> H["Application service"]
    H --> I["Response marshalling"]
    I --> J["SOAP serialization"]
    J --> K["HTTP response"]
~~~

Mỗi tầng có thể giữ buffer HTTP, parse Header/Body, materialize DOM/OM tree, đọc hết Source trong logging/validation/XPath, chuyển JAXB thành object graph hoặc sao chép sang `byte[]`/`String`/`ByteArrayOutputStream`. Vì vậy **không thể nhìn endpoint signature `Source` rồi kết luận toàn đường đi streaming**.

### 1.1. Hai loại chi phí

| Loại | Ví dụ | Tác động |
| --- | --- | --- |
| Memory | DOM nodes, Axiom OM tree, JAXB graph, byte[], log string | Heap peak, allocation, GC |
| I/O và CPU | XML parsing, canonicalization, validation, copy, disk cache | Latency, throughput, thread occupancy |
| Re-read | Cache payload hoặc serialize rồi parse lại | Thêm CPU/copy, cho phép nhiều consumer đọc |
| Backpressure | Slow client/backend giữ stream mở | Giữ request thread, socket, buffer hoặc temp file |

Với payload kích thước `P` và `C` requests đồng thời, nếu mỗi request materialize payload một lần thì chỉ riêng payload memory thô có thể xấp xỉ `C × P`; DOM/JAXB representation và copies làm thực tế cao hơn. Đây là estimate capacity, **không phải công thức dự đoán heap chính xác**.

### 1.2. Streaming không chỉ là buffer nhỏ

Streaming đúng nghĩa cần giới hạn số bytes thực tế, XML size/depth, concurrent requests, timeout, attachment count/bytes, temp storage và thời gian consumer giữ stream. Một stream đọc từng 8 KiB vẫn có thể gây DoS nếu có hàng nghìn streams đồng thời hoặc không giới hạn tổng bytes.

## 2. Source, Result và các mô hình đọc XML

`Source` và `Result` là abstraction JAXP; chúng không ấn định một chiến lược memory duy nhất. Implementation cụ thể quyết định dữ liệu nằm ở đâu và có thể đọc lại không.

| Kiểu | Vai trò | Đặc điểm |
| --- | --- | --- |
| `StreamSource` | Nguồn XML từ InputStream/Reader/system ID | Stream thường one-shot; system ID có thể kích hoạt resolver nếu không khóa external access |
| `SAXSource` | XML qua SAX XMLReader/InputSource | Event-driven nếu handler không giữ cả tree |
| `StAXSource` | Nguồn từ XMLStreamReader/XMLEventReader | Cursor/event stream tiến về trước; thường không rewind |
| `DOMSource` | Nguồn từ DOM Node | Payload đã materialize thành cây trong memory |
| `StreamResult` | Ghi XML vào stream/writer | Có thể ghi tăng dần; đích vẫn có thể là buffer |
| `DOMResult` | Ghi XML vào DOM | Tạo cây trong memory |
| `SAXResult` | Ghi XML thành events | Consumer có thể xử lý tuần tự |
| JAXB object | Object mapping | XML đã parse thành object graph; không còn raw payload stream |

### 2.1. StreamSource không bảo đảm stream repeatable

~~~java
InputStream input = obtainRequestStream();
Source source = new StreamSource(input);

// Consumer đầu tiên có thể đọc đến EOF.
transformer.transform(source, new StreamResult(output));

// Không được giả định source có thể transform lần hai.
~~~

`InputStream` thông thường chỉ tiến về trước; `mark/reset` không phải lúc nào cũng hỗ trợ và không nên là contract ngầm. Nếu cần hai consumer, quyết định rõ có cache/copy vào storage hay tổ chức một lần đọc để fan-out an toàn.

### 2.2. DOMSource tiện dụng nhưng tốn memory

DOM hữu ích khi cần random access, XPath nhiều lần, sửa nodes hoặc signature processing cần tree. Nhưng toàn bộ nodes/attributes/text có object overhead. Với payload lớn hoặc nhiều requests đồng thời, DOM có thể tốn nhiều lần XML bytes trên wire. Dùng khi cần capability của tree và payload có bound hợp lý; đo với XML shape gần production.

### 2.3. StAX/SAX phù hợp xử lý tuần tự

StAX cursor có thể đọc event từng bước. SAX handler có thể xử lý start/text/end events. Hai cách giảm nhu cầu xây toàn cây XML, nhưng handler vẫn có thể tự tích lũy toàn dữ liệu vào list/String/byte array. Streaming parser cần namespace-aware logic, state machine và limits; không parse XML bằng tìm tag substring.

## 3. One-shot, repeatable và thao tác tiêu thụ payload

### 3.1. Các thao tác có thể consume payload

- `Transformer.transform(source, result)`.
- JAXB `Unmarshaller.unmarshal(source)`.
- XPath evaluation trên Source không cache.
- Schema validator đọc stream đầu vào.
- Logging interceptor serialize payload thành String/bytes.
- Custom interceptor dùng `getPayloadSource()` rồi đọc tới EOF.
- Endpoint adapter chuyển payload thành JAXB object.

Không phải mọi lần gọi method đều consume nếu chỉ quan sát Header/metadata; nhưng **không suy đoán từ tên method**. Kiểm implementation/version cụ thể.

### 3.2. Bảng phân loại

| Thao tác | Có thể đọc hết body? | Hệ quả |
| --- | --- | --- |
| Đọc SOAP Header | Thường không cần consume payload | Có thể an toàn với body stream |
| Đọc attachment metadata | Không nhất thiết đọc attachment bytes | Phụ thuộc provider |
| Payload logging | Thường đọc/serialize payload | Có nguy cơ consume hoặc materialize |
| XPath trên payload | Parse phần XML liên quan | Có thể đọc hết và cache tree |
| XSD validation | Đọc XML để validate | Có thể tiêu thụ Source |
| JAXB unmarshalling | Đọc document tạo object | Source one-shot đã consume |
| Transform Source → DOMResult | Đọc source, tạo DOM | Materialize toàn payload |
| Transform Source → StreamResult | Đọc source, ghi đích | Có thể stream nếu transformer không buffer |
| Endpoint nhận JAXB object | XML parse trước khi gọi method | Business method không còn raw stream |
| Endpoint nhận Source | Có thể nhận source consumptive | Phụ thuộc adapter/message factory |

Nếu payload cần đi qua validator, audit logger và JAXB unmarshaller, ba consumer độc lập có thể không đọc được cùng one-shot Source. Chỉ gọi `getPayloadSource()` nhiều lần không đủ chứng minh mỗi lần có stream mới.

### 3.3. Ba chiến lược khi cần nhiều consumer

1. **Một pipeline consumer:** kết hợp validation/inspection/transform vào một pass nếu thứ tự và security semantics cho phép.
2. **Cache có giới hạn:** materialize payload vào memory/disk để consumer đọc lại; đặt hard size limit.
3. **Staging bền vững:** copy với bounded buffer vào file/object storage riêng, sau đó mở stream mới cho consumer; quản lý ownership/cleanup.

Không cache mọi request vô hạn chỉ để tránh lỗi stream đã đóng. Cũng không bỏ validation/signature checks chỉ để đạt streaming. Bảo mật và contract validation vẫn là điều kiện trước business processing.


## 4. SAAJ và Axiom: payload caching hoạt động ở đâu?

Spring-WS dùng `WebServiceMessageFactory` để tạo SOAP message từ transport. Hai implementation thường gặp là `SaajSoapMessageFactory` và `AxiomSoapMessageFactory`. Chọn factory ảnh hưởng cách XML được parse, giữ và đọc lại.

### 4.1. SAAJ: message tree và DOM-oriented processing

SAAJ dựa trên SOAP with Attachments API for Java. Trong cách dùng phổ biến, SOAP Envelope/Header/Body được biểu diễn qua SAAJ message model dựa trên tree; payload access thông qua DOM/SOAP APIs. Đây là lựa chọn tương thích rộng và phù hợp nhiều interceptor/handler truyền thống.

- Việc dùng `Source` từ SAAJ message không đồng nghĩa transport-to-endpoint zero-copy.
- Khi cần inspect/sửa SOAP nodes, SAAJ thường dễ tích hợp.
- Với payload lớn, đo memory peak và allocation của message factory, logging, JAXB và serialization.
- Không có setter `payloadCaching` tương đương Axiom trên `SaajSoapMessageFactory`; đừng copy cấu hình Axiom sang SAAJ.

### 4.2. Axiom: mô hình XML có thể hỗ trợ deferred building

Apache Axiom cung cấp object model hỗ trợ lazy/deferred building và streaming-oriented access. Spring-WS tích hợp qua `AxiomSoapMessageFactory`. Axiom có thể giữ payload chưa build toàn bộ cho tới khi consumer yêu cầu; nhưng khi một thao tác đòi random access/serialization/re-read, model có thể phải build/caching phần tương ứng.

Axiom hữu ích khi đường xử lý được thiết kế streaming. Nó **không tự động** làm mọi endpoint/interceptor streaming. XPath, JAXB unmarshal, DOM conversion hoặc payload logger vẫn có thể buộc đọc/build payload.

### 4.3. payloadCaching là cache của SOAP payload

`AxiomSoapMessageFactory.setPayloadCaching(boolean)` điều khiển việc cache payload để hỗ trợ nhiều lần truy cập. Khi bật, Axiom có thể giữ/build payload để các thao tác sau truy cập lại. Khi tắt, payload access thiên về streaming/forward-only; consumer đầu tiên có thể làm payload không còn sẵn cho consumer tiếp theo.

Ví dụ cấu hình Java:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.soap.axiom.AxiomSoapMessageFactory;

@Configuration(proxyBeanMethods = false)
class AxiomMessageConfig {

    @Bean
    AxiomSoapMessageFactory soapMessageFactory() {
        AxiomSoapMessageFactory factory =
            new AxiomSoapMessageFactory();

        // false: chọn one-pass payload access.
        // Chỉ dùng nếu interceptors/endpoints không cần đọc lại.
        factory.setPayloadCaching(false);
        return factory;
    }
}
~~~

Đây là config minh họa. Dependency Axiom phải tương thích Spring-WS/Spring Framework của dự án và message factory bean thật sự phải được dùng bởi SOAP servlet/client. Nếu Boot auto-configuration hoặc config khác tạo factory riêng, sửa bean không đúng nơi có thể không thay đổi runtime behavior.

### 4.4. Khi nào bật và khi nào tắt?

| Tình huống | Hướng chọn |
| --- | --- |
| Nhiều interceptors cùng đọc payload | Caching có thể cần thiết |
| Endpoint mapping/validation/XPath phụ thuộc re-read | Giữ cache hoặc redesign pipeline có chủ ý |
| Một endpoint consumer duy nhất đọc body tuần tự | Có thể cân nhắc cache off |
| Payload lớn, throughput cao, one-pass processing | Axiom payloadCaching off có thể giảm buffering |
| Logging interceptor đọc body trước endpoint | Cache hoặc bỏ payload logging; không tắt cache mù |
| Signature/validation cần nhiều bước | Kiểm WSS4J/parser behavior trước; không bỏ security để stream |
| Code cần DOM/random access | Cache/tree model phù hợp hơn |
| Client retry/re-read cùng request | Dùng repeatable source hoặc build lại message; cache server-side không làm InputStream nguồn thành repeatable |

Không có default universal. Bắt đầu từ behavior đúng và contract/security, sau đó benchmark profile đại diện. Đừng tắt payload cache chỉ vì heap thấp hơn trong test không có validator/logging thực tế.

### 4.5. payloadCaching khác attachmentCaching và threshold

`AxiomSoapMessageFactory` có những thiết lập riêng cho payload và MIME attachments:

| Setting | Điều chỉnh | Không có nghĩa |
| --- | --- | --- |
| `payloadCaching` | Cache/read strategy cho SOAP XML payload | Không giới hạn kích thước payload |
| `attachmentCaching` | Cache attachment content theo cơ chế Axiom | Không phải file scan/security |
| `attachmentCacheThreshold` | Ngưỡng bộ nhớ trước khi attachment cache spill sang disk theo implementation | Không phải hard upload size limit |
| `attachmentCacheDir` | Thư mục dùng cho attachment cache/spill khi cấu hình hỗ trợ | Không phải durable document store |

Không nhầm threshold với giới hạn file. Attachment 200 MiB vẫn có thể được chấp nhận nếu không có hard limit ở transport/application, kể cả threshold chỉ 64 KiB. Phải đếm decoded bytes thực và áp limit tổng/single-part độc lập.

### 4.6. Tắt payload caching có thể làm interceptor sau thất bại

Giả sử chain:

~~~text
1. LoggingInterceptor đọc payload thành String
2. PayloadValidatingInterceptor validate payload
3. Endpoint adapter unmarshal JAXB
~~~

Nếu message factory/payload access là forward-only và logging interceptor đã consume body, bước validation hoặc JAXB có thể nhận payload rỗng/EOF. Với một số message factory/pipeline, provider có thể cache/copy theo cách khác; vì vậy hãy **tái hiện với đúng factory, order và version**, không xem pseudocode này là behavior universal.

Khi cấu hình `payloadCaching=false`, audit từng component:

- Có gọi `getPayloadSource()` hoặc transform payload không?
- Có đọc Source hơn một lần không?
- Endpoint mapping dựa vào payload root có phải đọc trước interceptor không?
- Validation interceptor và WSS4J có cần replay/canonicalization?
- Logging có serialize body rồi vẫn mong endpoint đọc lại?
- Response interceptor/client extractor có cùng vấn đề ở chiều outbound không?

Nếu có consumer thứ hai, cần cache, redesign thành một pass, hoặc copy vào bounded replayable representation.

## 5. Các thao tác thường vô tình phá streaming

### 5.1. Logging toàn bộ SOAP payload

Ví dụ anti-pattern:

~~~java
Source source = message.getPayloadSource();
String xml = transformToString(source);
log.info("SOAP request: {}", xml);
~~~

Việc biến payload thành String phải đọc/serialize payload và tạo thêm bản sao trong heap. Nó cũng có thể để lộ PII, access tokens, UsernameToken, dữ liệu thanh toán hoặc tài liệu. Không bật body logging ở production như cách chẩn đoán mặc định.

Thay bằng structured metadata không nhạy cảm: operation QName, message size, elapsed time, correlation ID và fault category. Nếu buộc sample payload, dùng allowlist, masking, size cap, retention/access control và bật có thời hạn.

### 5.2. XPath và DOM conversion

XPath evaluation thường cần navigator trên XML model. Tùy implementation, nó có thể build payload tree hoặc parse hết source. Chạy nhiều XPath queries độc lập có thể tạo repeated work nếu payload không cache.

Nếu chỉ cần vài field cho routing/metrics, cân nhắc một pass parser hoặc đọc SOAP Header metadata đã định nghĩa, nhưng không tự parse raw XML bằng string matching. Không dùng XPath/logging đọc nội dung chứa security token trước khi trust/authorization policy cho phép.

### 5.3. XSD validation và JAXB unmarshal

Validation và unmarshal đều phải đọc XML. Nếu cả hai chạy liên tiếp trên one-shot source, phải bảo đảm framework/provider quản lý caching/replay hoặc thiết kế pipeline rõ ràng. Không xóa `PayloadValidatingInterceptor` chỉ để giải quyết EOF; schema validation có thể là contract requirement.

Một pattern hợp lý:
- Dùng message factory/pipeline có cache khi validation và JAXB là hai consumer riêng.
- Hoặc dùng một pipeline parse có validation tích hợp, chỉ khi framework và contract hỗ trợ rõ.
- Hoặc staged payload có byte limit rồi mở stream riêng cho validator và unmarshaller.

### 5.4. Interceptor order làm thay đổi semantics

Spring-WS endpoint interceptors có thể chạy ở các pha request/response. Nếu interceptor đọc body, nó có thể ảnh hưởng interceptor sau. Nếu interceptor sửa payload, endpoint có thể nhìn content khác content đã được log/validate. Hãy thống nhất order và bất biến:

| Pha | Hoạt động | Quy tắc |
| --- | --- | --- |
| Request đầu vào | Authentication/security checks | Không log secrets; verify trước business processing |
| Request validation | XSD/contract checks | Payload consumer sau vẫn phải hoạt động |
| Observability | Metadata/metrics | Ưu tiên Header/metadata thay toàn Body |
| Endpoint | JAXB/Source mapping | Chỉ xử lý payload đã qua required checks |
| Response | Mapping/validation/signature | Không consume response trước bước serialize/transport |

Đây là thứ tự khái niệm; order cụ thể phụ thuộc interceptor chain và endpoint mapping thực tế. WS-Security có yêu cầu parse, decrypt và verify parts; không đẩy logging trước security để lộ plaintext hoặc bỏ verification.


## 6. Streaming trong SOAP client với WebServiceTemplate

`WebServiceTemplate` có overloads cho `Source`/`Result` và callback/extractor. Những API này cho phép application kiểm soát nguồn/đích XML tốt hơn so với luôn marshal toàn bộ request thành JAXB object; nhưng **message factory, transport sender và transformer vẫn quyết định có buffer/copy hay không**.

### 6.1. Gửi Source và ghi response vào stream

Ví dụ minh họa client đọc request từ file và ghi response sang file staging:

~~~java
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import javax.xml.transform.stream.StreamResult;
import javax.xml.transform.stream.StreamSource;
import org.springframework.ws.client.core.WebServiceTemplate;

public void exchangeXml(
        WebServiceTemplate template,
        Path requestXml,
        Path responseStaging) throws Exception {

    try (InputStream requestIn = Files.newInputStream(requestXml);
         OutputStream responseOut =
             Files.newOutputStream(responseStaging)) {

        var request = new StreamSource(requestIn);
        var response = new StreamResult(responseOut);

        boolean received = template.sendSourceAndReceiveToResult(
            "https://partner.example.test/soap/orders",
            request,
            null,
            response);

        if (!received) {
            throw new IllegalStateException(
                "SOAP response was not received");
        }
    }
}
~~~

Ví dụ sử dụng overload nhận URI, request Source, callback và Result; kiểm tra signature overload theo Spring-WS version mà dự án compile. `responseStaging` phải là file private với permission, quota, cleanup và xử lý partial output khi request lỗi. Không ghi trực tiếp vào path do caller cung cấp.

Đây **không phải bảo đảm zero-copy**: framework có thể transform Source vào message payload, message factory có thể build/cache, HTTP sender có thể buffer và response Result không phản ánh transport buffering. Ví dụ chỉ tránh ép application tạo JAXB graph hoặc byte array đầy đủ.

### 6.2. Callback và extractor

- `WebServiceMessageCallback` được dùng để chỉnh message outgoing, ví dụ SOAP Action hoặc custom header.
- `WebServiceMessageExtractor<T>` xử lý response message và trả về một giá trị application.
- Nếu extractor lấy `getPayloadSource()` rồi transform sang `StreamResult`, nó vẫn phải quản lý one-shot Source và output lifecycle.
- Không giữ `WebServiceMessage`, `Source`, `InputStream` hoặc `Result` sau callback/extractor nếu implementation chỉ đảm bảo lifetime trong exchange.

Ví dụ khái niệm extractor:

~~~java
WebServiceMessageExtractor<Path> extractor = message -> {
    Path staged = createPrivateStagingFile();

    try (OutputStream out = Files.newOutputStream(staged)) {
        transformer.transform(
            message.getPayloadSource(),
            new StreamResult(out));
    }

    return staged;
};

Path responseFile = template.sendSourceAndReceive(
    endpointUri,
    requestSource,
    requestCallback,
    extractor);
~~~

`createPrivateStagingFile`, `transformer`, `endpointUri`, `requestSource` và `requestCallback` là dependencies/application code giả định. Bản thực cần cleanup staged file khi transform lỗi, quota và validation trước khi chuyển file sang kho bền vững. Extractor không nên trả `InputStream` đã bị đóng bởi try-with-resources.

### 6.3. Repeatable request source khi retry

Một request Source dựa trên `InputStream` thường chỉ đọc được một lần. Nếu HTTP sender hoặc application cần replay:

- Mở lại file input cho mỗi lần gửi; file source phải tồn tại đến khi exchange hoàn tất.
- Với payload sinh động, tạo lại Source từ dữ liệu bền vững hoặc factory có thể mở stream mới.
- Với body nhỏ, bounded byte array có thể phù hợp nếu hard size limit rõ.
- Không dùng `InputStreamResource`/`StreamSource` đã consume làm retry source.
- Chỉ retry operation idempotent hoặc có business idempotency key; transport timeout không chứng minh server chưa commit.

**Repeatable input** là khả năng tạo stream mới từ cùng dữ liệu, không phải gọi `reset()` trên mọi stream.

### 6.4. Client JAXB vs Source

| Cách gọi | Ưu điểm | Chi phí/cần lưu ý |
| --- | --- | --- |
| `marshalSendAndReceive(JAXB object)` | Dễ dùng, type-safe, mapping contract rõ | XML/object graph và serialization |
| `sendSourceAndReceive...` | Chủ động source/result và xử lý XML tuần tự | Quản lý stream, validation, lỗi và one-shot lifecycle |
| `WebServiceMessageExtractor` | Kiểm soát đọc response | Extractor có thể consume payload; không giữ message sau exchange |

Không chuyển mọi SOAP client sang raw Source chỉ vì payload lớn. JAXB phù hợp request/response nghiệp vụ có cấu trúc và giới hạn hợp lý. Streaming XML phù hợp khi payload lớn, opaque hoặc chuyển tiếp đến sink mà không cần toàn object graph.


## 7. Streaming ở server và vòng đời endpoint

### 7.1. Endpoint nhận JAXB object

~~~java
@PayloadRoot(
    namespace = "urn:example:documents:v1",
    localPart = "ImportDocumentRequest")
@ResponsePayload
public ImportDocumentResponse importDocument(
        @RequestPayload ImportDocumentRequest request) {

    // Framework đã unmarshall XML thành object trước khi gọi method.
    return service.importDocument(map(request));
}
~~~

Cách này rõ contract và thuận tiện validation/business mapping. Nhưng nếu request có dữ liệu lớn trong `byte[]`, `List`, nested JAXB objects hoặc text field khổng lồ, object graph có thể chiếm heap đáng kể. `@RequestPayload` không tự nói dữ liệu được stream vào service.

### 7.2. Endpoint nhận Source cần one-pass contract

Với payload opaque hoặc cần xử lý XML tuần tự, một endpoint có thể nhận `Source`/kiểu source phù hợp với endpoint adapter:

~~~java
@PayloadRoot(
    namespace = "urn:example:documents:v1",
    localPart = "ImportDocumentRequest")
@ResponsePayload
public Source importDocument(@RequestPayload Source payload) {
    // Ví dụ: chuyển qua parser/transformer đã giới hạn resource.
    // Không đọc payload ở interceptor trước đó nếu factory one-pass.
    return responseSourceFor(service.process(payload));
}
~~~

Đây là **skeleton**, không phải bảo đảm mọi endpoint adapter/factory combination hỗ trợ Source theo cùng cách. Kiểm mapping, argument resolver, message factory và Spring-WS version. `Source` vẫn có thể là DOMSource hoặc source đã được build/cache; inspect runtime type/profile trước khi kết luận streaming.

### 7.3. Không chuyển stream ra khỏi request nếu chưa staging

Không trả `InputStream` lấy từ request payload để background job đọc sau khi endpoint return. Message context, HTTP request hoặc Axiom builder có thể đã đóng/consume. Nếu processing bất đồng bộ:

1. Copy bounded stream vào private staging/durable object storage trong request lifetime.
2. Tính size/hash và ghi metadata/job state nhất quán.
3. Chỉ enqueue job sau khi staging được lưu bền vững.
4. Worker mở **stream mới** từ staging.
5. Cleanup theo ownership/TTL và reconciliation sau crash.

Không giữ `Source`/`InputStream` của message context trong queue.

### 7.4. Response streaming cũng cần kiểm soát

Response lớn có thể bị materialize ở JAXB marshalling, response interceptor, `DOMResult` hoặc HTTP layer. Cân nhắc Source/streaming message support khi framework/provider cho phép, nhưng giữ SOAP envelope, namespace, fault handling và security profile đúng. Nếu response được ký bằng WS-Security, signature engine có thể cần canonicalize/reference các parts và tăng buffering/CPU; **không giả định ký XML và zero-copy luôn tương thích**.

## 8. Backpressure, cancellation và timeout

Streaming giảm memory khi consumer đọc/ghi dần, nhưng có thể giữ resource lâu hơn. Server thread có thể bị giữ trong thời gian client upload chậm hoặc storage backend chậm.

| Điều khiển | Mục tiêu |
| --- | --- |
| Max request/response bytes | Giới hạn tổng payload |
| Read/connection timeout | Ngăn stream treo vô hạn |
| Request concurrency/bulkhead | Giới hạn số stream đồng thời |
| Bounded queue | Không tích lũy job vô hạn |
| Storage write timeout/quota | Xử lý disk/object store chậm hoặc đầy |
| Client disconnect/cancellation | Đóng stream và dừng xử lý khi an toàn |
| Retry/idempotency | Không nhân đôi side effects khi outcome chưa rõ |

Một upload thread block chờ slow storage vẫn giữ socket, buffers và request context. Đo **throughput theo payload size và concurrency**, không chỉ requests/second với SOAP message nhỏ.


## 9. Attachment streaming và MIME cache

SOAP có thể mang binary data qua SwA hoặc MTOM/XOP. XML payload và MIME attachment có caching/lifecycle riêng.

### 9.1. Đọc attachment mà không tạo byte array

Với Spring-WS MIME API, `Attachment.getInputStream()` cho phép đọc bytes qua stream:

~~~java
Attachment attachment = requireAttachment(message, contentId);

try (InputStream in = attachment.getInputStream()) {
    copyWithLimitAndDigest(
        in,
        privateStagingPath,
        maxAttachmentBytes);
}
~~~

`requireAttachment`, `copyWithLimitAndDigest`, `privateStagingPath` và `maxAttachmentBytes` là application helpers giả định. `copyWithLimitAndDigest` cần bounded buffer, đếm actual bytes, abort khi vượt giới hạn, tính hash trong cùng pass và cleanup partial file khi lỗi.

Không dùng `attachment.getSize()` như hard limit: metadata size có thể chưa biết hoặc khác số decoded bytes thực tế. Đọc stream có kiểm soát mới xác nhận được kích thước thực.

### 9.2. Attachment cache khác payload cache

- `payloadCaching` liên quan SOAP XML Body.
- `attachmentCaching` và threshold điều khiển cache/spill attachment theo Axiom implementation.
- Attachment cache directory phải private, quota/inode monitored và cleanup theo lifecycle/provider.
- Threshold chỉ là memory-to-disk policy; hard upload size, tổng request size và file scan vẫn do application/gateway enforce.

Không giả định attachment stream mở lại nhiều lần khi cache tắt. Nếu cần retry, scanner và persistence đọc độc lập, stage file/object bền vững hoặc dùng nguồn repeatable do ứng dụng quản lý.

### 9.3. MTOM không tự động có nghĩa zero-copy

MTOM/XOP tránh biểu diễn binary dưới dạng Base64 text inline trong XML, giảm expansion trên wire và có thể cải thiện memory/CPU. Tuy nhiên serializer, SAAJ/Axiom, MIME parser, `DataHandler`, HTTP sender và attachment handler vẫn có thể buffer/copy bytes. Phải đo heap/disk với đúng provider, threshold và attachment size.

## 10. Cấu hình vận hành theo profile

| Profile | Đặc điểm | Định hướng |
| --- | --- | --- |
| Small business messages | XML nhỏ, JAXB, nhiều validation/interceptors | Caching/re-read thường đơn giản hơn |
| Large XML document | Body lớn, tuần tự, ít random access | Axiom one-pass nếu pipeline hỗ trợ |
| Binary attachment | XML metadata nhỏ, file lớn | Attachment cache/spill + hard size quota + private staging |
| WS-Security heavy | Signature/encryption, multiple references | Ưu tiên security đúng, benchmark tree/cache behavior |
| Pass-through gateway | Ít business mapping, chuyển tiếp payload | Streaming Source/Result nếu transport/message factory hỗ trợ |
| Audit/debug mode | Cần quan sát nội dung | Metadata-first; sampling có kiểm soát, không bật toàn Body mặc định |

Một cấu hình `payloadCaching=false` không thể áp cho toàn ứng dụng nếu có operation vẫn cần XPath/JAXB re-read. Tách message factory/endpoint profile nếu servlet topology cho phép; không đổi mutable config theo từng request trên singleton.


## 11. Đo hiệu năng và theo dõi tài nguyên

### 11.1. Metrics theo payload size và concurrency

Theo dõi ít nhất:

| Metric | Vì sao cần |
| --- | --- |
| Request/response bytes histogram | Phân phối payload thực tế |
| In-flight SOAP requests | Concurrency thực |
| Heap used/committed và allocation rate | Peak memory và churn |
| GC pause/time | Tác động latency |
| Process RSS/container memory | Native buffers và memory ngoài heap |
| Request/response duration histogram | p50/p95/p99 theo size class |
| XML parse/validation duration | Chi phí parser và XSD |
| Bytes copied và copy duration | Phát hiện nhiều materialization |
| Temp disk bytes/inodes | Axiom attachment cache/staging |
| Open file descriptors | Stream/resource leaks |
| Fault count theo lớp | Validation, parse, timeout, transport, business |
| Executor/connection pool saturation | Backpressure và queue buildup |

Metric labels phải cardinality thấp: operation, schema version, payload size bucket, result class. Không dùng raw requestId, customerId, filename, token hoặc XML content làm labels.

### 11.2. Benchmark phải mô phỏng đường đi thật

Benchmark chỉ gọi transformer `StreamSource → StreamResult` không phản ánh Spring-WS end-to-end. Cần bao gồm:

1. HTTP transport và SOAP message factory thực tế.
2. Đúng SAAJ hoặc Axiom implementation và payloadCaching profile.
3. Interceptor chain gồm security, validation và observability giống production.
4. Endpoint mapping/JAXB hoặc Source processing.
5. SOAP response marshalling và HTTP serialization.
6. Payload size distribution và request concurrency gần production.
7. Cold/warm key caches, TLS, WS-Security và attachment profile nếu được dùng.

So sánh profile cache on/off, payload nhỏ/vừa/lớn, 1/10/peak concurrency. Đo heap/RSS/GC/latency/throughput và temp I/O, không chỉ benchmark một request.

### 11.3. Công thức sizing sơ bộ

~~~text
C = concurrent requests
P = average in-memory payload representation bytes per request
B = per-request stream buffer
T = temporary attachment spill/staging bytes
H = other heap (JAXB, XML nodes, application objects, runtime)

Approximate heap pressure ≈ C × (P + B) + H
Approximate temp pressure ≈ concurrent staged/spilled bytes + retained files
~~~

Đây là model định hướng. `P` phụ thuộc tree/object overhead, encoding và duplicate copies; `H` thay đổi theo load. Dùng load test và heap profile để lấy hệ số thực, chừa headroom cho GC, burst và rolling deploy.

### 11.4. Dấu hiệu nhận biết streaming bị phá

- Heap tăng gần tuyến tính với payload size × concurrency.
- Allocation profile xuất hiện nhiều `byte[]`, `char[]`, DOM nodes hoặc JAXB objects.
- p99 tăng mạnh khi bật SOAP body logging hoặc XPath interceptor.
- Tắt cache làm xuất hiện empty payload/EOF ở interceptor sau.
- Temp directory, inode hoặc open file descriptors tăng sau mỗi batch.
- Throughput giảm khi scanner/object store chậm và in-flight requests tích tụ.
- Payload nhỏ ổn nhưng OOM khi vài requests lớn chạy cùng lúc.

## 12. Lỗi thường gặp và cách xử lý

| Anti-pattern | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| Gọi `readAllBytes()` trên request | Buffer toàn payload | Bounded streaming/staging |
| Convert toàn payload thành String để log | Duplicate heap, rò PII/secret | Metadata-first, redaction |
| Tắt payloadCaching mà giữ nhiều body consumers | Consumer sau nhận EOF/empty payload | Cache hoặc thiết kế one-pass |
| Coi payloadCaching là upload size limit | Không giới hạn bytes | Hard limit độc lập |
| Coi attachmentCacheThreshold là file-size limit | Threshold chỉ điều khiển cache/spill | Count decoded bytes thực |
| Dùng SAAJ rồi kỳ vọng zero-copy | Tree-oriented message model | Đo memory hoặc thử Axiom |
| Dùng Axiom rồi mặc định zero-copy | XPath/JAXB/DOM vẫn materialize | Profile cả interceptor và endpoint |
| JAXB `byte[]` cho file rất lớn | Object chứa toàn binary | DataHandler/attachment stream + staging |
| Giữ Source/Stream sau endpoint return | Message context có thể đã đóng | Copy sang durable storage |
| Retry bằng stream đã consume | Request body rỗng/lỗi | Open stream mới từ repeatable source |
| Dùng DOMResult cho payload lớn | Full tree in memory | StreamResult nếu downstream chấp nhận |
| Bỏ XSD/WS-Security để tối ưu | Hạ contract/security | Pipeline an toàn, benchmark đúng |
| Log SOAP plaintext trước security verify | Có thể lộ dữ liệu chưa trust | Metadata/redaction và đúng security order |
| Không giới hạn concurrency | Nhiều stream giữ buffers/socket | Bulkhead/backpressure |
| Dọn temp dir chung sau mỗi request | Xóa file request khác | Ownership per request + TTL reaper |

## 13. Quy trình kiểm thử streaming và payload caching

### 13.1. Ma trận test

| Test | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Payload cache on, nhiều consumers | Logging/validation/JAXB chain | Mỗi consumer nhận payload đúng |
| Payload cache off, một consumer | Axiom + one-pass endpoint | Đọc tuần tự thành công |
| Payload cache off, hai consumers | Validator rồi logger/mapper | Chứng minh EOF hoặc redesign/cache |
| Payload lớn | Tăng size theo bậc | Heap/RSS trong budget |
| Concurrent uploads | Tăng đồng thời tới peak | Backpressure, không OOM |
| Client disconnect giữa stream | Ngắt upload/download | Stream/file cleanup |
| Disk full khi spill | Temp quota nhỏ | Lỗi có kiểm soát, cleanup partial |
| SOAP Body logging | On/off so sánh | Đo duplicate allocation và latency |
| JAXB vs Source | Cùng payload | So memory, latency, behavior |
| MTOM attachment | Tăng binary size | Cache/staging đúng quota |
| WS-Security enabled | Signature/encryption thật | Đo CPU/memory, giữ verification |
| Interceptor order | Hoán đổi logger/validator có kiểm soát | Phát hiện consumer bị consume |
| Retry outbound | Repeatable file source | Payload resend giống nhau |
| Message factory đổi | SAAJ vs Axiom | So compatibility và resource |

### 13.2. Kiểm tra payload one-shot một cách rõ ràng

Tạo test Source/stream có thể phát hiện lần đọc thứ hai, thay vì dựa vào InputStream tình cờ hỗ trợ mark/reset. Ví dụ helper:

~~~java
final class ReadOnceInputStream extends FilterInputStream {
    private boolean opened;

    ReadOnceInputStream(InputStream delegate) {
        super(delegate);
    }

    @Override
    public int read(byte[] bytes, int offset, int length)
            throws IOException {
        return super.read(bytes, offset, length);
    }

    void assertConsumed() {
        // Trong test, theo dõi EOF/close ở wrapper riêng.
    }
}
~~~

Đây chỉ là khung minh họa; test hoàn chỉnh nên wrapper tracking EOF/close và throw nếu provider cố mở underlying source lần nữa sau khi consume. Test hai consumers theo order production và assert payload thứ hai vẫn đúng **nếu** caching bật, hoặc pipeline chỉ có một consumer khi cache tắt.

### 13.3. Đo heap và allocation

- Warm up JVM, serializer, JAXB context, TLS và crypto provider trước phép đo.
- Chạy nhiều vòng với payload cố định và concurrency tăng dần.
- Ghi heap histogram/JFR allocation, GC pauses và RSS/container memory.
- Chụp bytes thực đọc/ghi, temp file count/size và duration.
- So profile `payloadCaching=true/false` trên cùng message factory và chain.
- Lặp lại với body logging, XSD validation, XPath và WS-Security từng bật/tắt theo ma trận.
- Đặt acceptance thresholds trước benchmark; không chọn profile chỉ dựa trên một run thuận lợi.

## 14. Checklist trước production

1. **Message factory:** runtime thật đang dùng SAAJ hay Axiom? Có kiểm bean/message factory mà servlet/client thực sự sử dụng?
2. **Payload cache:** payloadCaching có phù hợp với số lượng consumers và thứ tự interceptor?
3. **One-shot:** Có interceptor/logger/validator nào đọc payload trước endpoint? Ai là consumer đầu tiên?
4. **Attachments:** attachment caching/threshold/temp directory đã tách khỏi hard upload limit, quota và malware scan?
5. **Bounds:** request bytes, XML depth/size, attachment count, concurrency, timeouts đều có giới hạn?
6. **JAXB:** Có trường byte[]/String/List hoặc object graph lớn làm materialize toàn dữ liệu?
7. **Client source:** retry có mở stream mới từ repeatable source? File nguồn có tồn tại tới khi send hoàn tất?
8. **Async:** Không giữ Source/InputStream của message context sau request; staged object đã durable trước enqueue?
9. **Security:** Không bỏ WS-Security, signature coverage hoặc XSD validation để tối ưu?
10. **Observability:** Không log toàn SOAP body/credentials; metrics cardinality thấp và đo size/latency/heap?
11. **Backpressure:** Có bulkhead, bounded queue, disk quota và behavior khi client disconnect?
12. **Benchmark:** Có test SAAJ/Axiom, cache on/off, payload size distribution, attachments, security và peak concurrency?
13. **Recovery:** Partial files, temp cache và stream cleanup có xử lý exception/process restart?
14. **Compatibility:** SOAP 1.1/1.2, WSDL, QName, JAXB và đối tác Java/.NET vẫn tương thích?

## 15. Bài tập tự kiểm tra

**Bài 1.** Phân biệt streaming API, payload caching và end-to-end streaming. Vì sao dùng `Source` chưa đủ chứng minh zero-copy?

**Bài 2.** Một interceptor đọc `getPayloadSource()` trước JAXB unmarshaller. Điều gì có thể xảy ra khi Axiom payload caching tắt?

**Bài 3.** Vì sao SAAJ tree-oriented thường cần nhiều memory hơn với payload XML lớn so với một pipeline StAX tuần tự?

**Bài 4.** Phân biệt `payloadCaching`, `attachmentCaching` và `attachmentCacheThreshold`. Cái nào là hard upload size limit?

**Bài 5.** Client dùng `StreamSource` từ một `InputStream`, request timeout và application retry cùng Source. Vì sao lần gửi thứ hai có thể rỗng?

**Bài 6.** Một PayloadValidatingInterceptor và JAXB adapter cùng cần body. Hãy đề xuất ba cách tổ chức pipeline không đọc mất payload.

**Bài 7.** Vì sao body logging có thể vừa làm giảm throughput vừa làm lộ dữ liệu nhạy cảm?

**Bài 8.** Một endpoint trả Source cho background worker sau khi method return. Rủi ro lifetime nào xảy ra? Thiết kế staging ra sao?

**Bài 9.** MTOM giảm Base64 expansion nhưng vì sao vẫn có thể buffer toàn attachment?

**Bài 10.** Thiết kế benchmark so SAAJ và Axiom với payload 1 MiB, 10 MiB, 100 MiB và concurrency khác nhau. Cần đo những gì?

**Bài 11.** Khi nào nên bật payloadCaching để hỗ trợ XPath/validation/logging? Vì sao vẫn cần hard limits?

**Bài 12.** Một attachment cache spill ra disk sau 64 KiB. Điều đó có nghĩa file tối đa 64 KiB không? Giải thích.

**Bài 13.** Nếu WS-Security signature processing cần canonicalize XML, vì sao không nên tắt signature để đạt mục tiêu streaming?

**Bài 14.** Làm sao test phát hiện interceptor thứ nhất đã consume one-shot stream và interceptor thứ hai nhận EOF?

**Bài 15.** Một client upload chậm giữ request thread 5 phút. Ngoài buffer size, cần kiểm soát concurrency, timeout, backpressure và cancellation thế nào?

### Gợi ý trả lời cốt lõi

- **1–2:** Source mô tả abstraction, không mô tả repeatability; one-shot consumer có thể làm consumer sau nhận EOF khi không cache.
- **3–4:** DOM/OM tree có object overhead; payload cache là XML, attachment cache là MIME part; threshold là spill policy, không phải hard limit.
- **5–6:** Stream thường không rewind; dùng re-open source, bounded cache/staging hoặc one-pass pipeline.
- **7–8:** Logging tạo String/copy và phơi PII; message context có lifetime request, async phải staging durable.
- **9–10:** MIME/parser/provider có thể buffer; đo heap, RSS, GC, I/O, latency, throughput, concurrency và temp disk.
- **11–12:** Cache giúp re-read nhưng cần size limits; threshold chỉ quyết định memory/disk cache.
- **13–15:** Giữ security invariant; test read-once bằng wrapper; giới hạn active streams và xử lý client/backend chậm.

## Tài liệu tham khảo

- [Spring Web Services Reference 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/) — message factories, SAAJ/Axiom, streaming payload, client và attachments.
- [Spring-WS API — AxiomSoapMessageFactory](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/soap/axiom/AxiomSoapMessageFactory.html) — payloadCaching, attachment caching, threshold và cache directory.
- [Spring-WS API — WebServiceTemplate](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/client/core/WebServiceTemplate.html) — Source/Result, callback, extractor và send/receive overloads.
- [Spring-WS API — Attachment](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/mime/Attachment.html) — attachment stream, DataHandler và size metadata.
- [Apache Axiom](https://ws.apache.org/axiom/) — deferred building, OM model và streaming-oriented XML processing.
- [Jakarta XML Binding](https://jakarta.ee/specifications/xml-binding/) — JAXB marshalling/unmarshalling.
- [Oracle — JAXP Streaming API for XML](https://www.oracle.com/java/technologies/jaxp-streaming-api.html) — pull parsing và cursor-based XML processing.
- [W3C — SOAP Message Transmission Optimization Mechanism](https://www.w3.org/TR/soap12-mtom/) — MTOM/XOP và binary optimization.

**Ghi nhớ:** streaming là thuộc tính của **toàn pipeline**, không phải tên kiểu Source. Trước khi tắt Axiom payloadCaching, hãy liệt kê tất cả consumer có thể đọc body (endpoint mapping, interceptor, validator, logger, JAXB, security) và xác định ai đọc trước. Phân biệt payload cache với attachment cache/threshold, dùng repeatable sources cho retry, staging có giới hạn cho xử lý bất đồng bộ, và benchmark bằng đúng message factory/interceptor/transport ở production. Không đánh đổi validation, WS-Security hoặc giới hạn tài nguyên để có một con số throughput đẹp trong test đơn giản.
