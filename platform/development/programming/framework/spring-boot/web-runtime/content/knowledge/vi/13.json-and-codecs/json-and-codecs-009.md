# Định dạng JSON, văn bản, nhị phân và XML khi có bộ chuyển đổi phù hợp

## Mục tiêu bài học và phạm vi

Sau bài học này, bạn có thể:

1. Giải thích vì sao cùng một HTTP endpoint có thể nhận hoặc trả **JSON**, **văn bản thuần**, **dữ liệu nhị phân** và **XML**, nhưng không phải mọi định dạng đều tự động khả dụng.
2. Phân biệt **Content-Type** với **Accept**, hiểu cơ chế lựa chọn representation và tình huống trả HTTP 400, 406, 415.
3. Chọn đúng kiểu Java như record/DTO, String, byte[], Resource, InputStreamResource, Mono<T> hoặc Flux<T> tương ứng với nội dung HTTP.
4. Phân biệt **HttpMessageConverter** của Spring MVC và **HttpMessageReader/HttpMessageWriter/Encoder/Decoder** của WebFlux.
5. Biết thư viện nào thường cung cấp JSON/XML, những giới hạn của String/binary converters và cách kiểm tra danh sách converter/codec đang có trong runtime.
6. Viết một ứng dụng **Spring Boot 3.3.x, Java 17+** chạy được, nhận và trả JSON/XML, text/plain, application/octet-stream với headers đúng.
7. Biết triển khai tương đương trên WebFlux, bao gồm điều kiện classpath của XML codec và sự khác biệt reactive body.
8. Kiểm thử bằng curl, MockMvc, WebTestClient, và phát hiện các lỗi sai media type, sai serialization, charset, kích thước payload hoặc bảo mật XML.

**Ngữ cảnh:** JSON và codec trong Spring Boot web-runtime. Bài sử dụng API của **Spring Boot 3.3.x / Spring Framework 6.1.x / Java 17+**. Tên API ở Spring Framework 7 hoặc Spring Boot 4 có thể khác; không thay package/class trong ví dụ 3.3 theo tài liệu phiên bản mới hơn.

**Nguyên tắc trọng tâm:** Header chỉ mô tả kiểu nội dung; việc chuyển object thành bytes (và ngược lại) cần **converter/codec phù hợp với cả kiểu Java lẫn media type**. Đặt Accept: application/xml không tự cài XML serialization, cũng như đặt Content-Type: application/json không biến tùy ý một String thành JSON hợp lệ.

## 1. HTTP body có thể mang nhiều loại biểu diễn

Một HTTP message gồm method/status, URL, headers và body. Body là bytes; việc giải thích chúng phụ thuộc media type.

Ví dụ các response có cùng ý nghĩa nghiệp vụ "sản phẩm id=7, tên=pen":

### JSON

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":7,"name":"pen"}
~~~

### Plain text

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=UTF-8

7,pen
~~~

### XML

~~~http
HTTP/1.1 200 OK
Content-Type: application/xml

<product><id>7</id><name>pen</name></product>
~~~

### Binary

~~~http
HTTP/1.1 200 OK
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="product.bin"

...bytes không nhất thiết là text...
~~~

Các ví dụ là **biểu diễn khác nhau**, không phải một phép đổi định dạng chung không cần code. JSON/XML có cấu trúc, text thuần có thể là bất cứ quy ước nào do API định nghĩa, binary là bytes do ứng dụng tạo. Converter không tự quyết định business schema hoặc tạo nội dung PDF/ZIP/image từ DTO.

**Quan trọng:** Content-Type là metadata; byte thực tế phải đúng định dạng đã công bố. Nếu body là JSON nhưng gắn application/xml, XML parser sẽ lỗi. Nếu body là text tùy ý nhưng gắn application/json, JSON client có thể parse thất bại.

## 2. Media type/MIME type là gì?

Một media type HTTP có dạng:

~~~text
type/subtype; parameter=value
~~~

Ví dụ:

~~~text
application/json
application/problem+json
application/xml
text/xml
text/plain; charset=UTF-8
application/octet-stream
image/png
application/pdf
application/x-ndjson
text/event-stream
~~~

Phân loại thường gặp:

| Media type | Nội dung điển hình | Bộ xử lý Java có thể phù hợp |
|---|---|---|
| application/json | JSON object/array | Jackson ObjectMapper và JSON converter/codec |
| application/*+json | JSON theo kiểu vendor hoặc Problem Details | JSON converter/codec có supported media types phù hợp |
| text/plain | Văn bản thuần | String converter/encoder/decoder |
| application/octet-stream | Byte không cần khai báo cấu trúc cao hơn | byte[]/DataBuffer/Resource |
| application/xml, text/xml | XML document | Jackson XML, JAXB hoặc XML reader/writer đã cấu hình |
| application/*+xml | Kiểu XML theo vendor | Tùy supported media types của XML converter |
| application/pdf | File PDF thật | Byte[]/Resource writer nhưng phải có bytes PDF hợp lệ |
| image/png | Ảnh PNG thật | Byte[]/Resource writer, bytes phải là PNG |
| application/x-ndjson | JSON object riêng trên từng dòng | Streaming JSON codec phù hợp |
| text/event-stream | Server-Sent Events | SSE writer/encoder khi WebFlux hoặc MVC tương ứng hỗ trợ |

**application/octet-stream** không có nghĩa rằng file không có kiểu dữ liệu. Nó biểu diễn payload nhị phân tổng quát khi API không cung cấp media type chuyên biệt. Nếu biết là PNG hoặc PDF thì nên khai báo image/png hoặc application/pdf phù hợp với nội dung thật, kèm header disposition nếu cần tải xuống.

### Đuôi file không phải Content-Type

URL /report.pdf và header Content-Type: application/json có thể cùng tồn tại về mặt HTTP; server vẫn gửi JSON bytes nếu ứng dụng tạo JSON. Client có thể bị nhầm hoặc chặn nội dung. Hãy để định dạng, tên file và headers thống nhất, đặc biệt khi client dùng trình duyệt hoặc download manager.

### Charset không tự biến byte thành text hợp lệ

text/plain; charset=UTF-8 cho biết byte cần được giải mã theo UTF-8. Nếu server ghi bytes theo một bảng mã khác nhưng gắn UTF-8, chữ tiếng Việt có thể hỏng. JSON trao đổi qua mạng hiện đại thường dùng UTF-8; với XML, cần quan tâm cả Content-Type charset và XML declaration nếu có.

## 3. Hai chiều chuyển đổi: đọc request và ghi response

Trước khi gọi controller, Spring phải đưa request body vào kiểu Java mong muốn. Sau khi controller trả kết quả, Spring phải viết response body.

~~~text
CLIENT
  |
  |  HTTP request
  |  Content-Type: application/json
  |  Body: {"name":"pen"}
  v
Spring HTTP infrastructure
  |
  +-- Chọn converter/reader cho (Java target type, request media type)
  |      -> decode/deserialize bytes thành ProductInput
  |
  v
Controller + Service
  |
  |  Java value ProductView
  v
Spring HTTP infrastructure
  |
  +-- Dựa trên Accept, produces, supported media types và Java return type
  |      -> chọn representation/converter/writer
  |      -> serialize ProductView ra JSON/XML/...
  |
  v
HTTP response có Content-Type và bytes tương ứng
~~~

Bốn sự thật cần nhớ:

1. **Đọc** phụ thuộc vào **request Content-Type** và **kiểu tham số Java**.
2. **Ghi** phụ thuộc vào **request Accept**, **produces**, **kiểu trả về Java** và **writer có mặt**.
3. **Content-Type của response** phải mô tả bytes thực tế server trả.
4. Cả routing conditions (consumes/produces) lẫn converter/codec đều có thể làm request không được chấp nhận.

Không có một thao tác toString() chung đủ để chuyển mọi object thành JSON, XML, PDF hoặc binary với ý nghĩa đúng.

## 4. Content-Type và Accept khác nhau

| Header | Bên gửi | Ý nghĩa |
|---|---|---|
| Request Content-Type | Client | Định dạng **request body đang gửi** |
| Request Accept | Client | Định dạng response client **có thể nhận** |
| Response Content-Type | Server | Định dạng **response body thực tế** |
| Response Content-Disposition | Server | Cách gợi ý hiển thị/tải nội dung và tên file |
| Response Vary | Server | Header request nào có thể ảnh hưởng representation để cache phân biệt |

Ví dụ client gửi XML nhưng muốn JSON:

~~~http
POST /api/convert HTTP/1.1
Content-Type: application/xml
Accept: application/json

<product><id>7</id><name>pen</name></product>
~~~

Đây là yêu cầu hợp lệ **nếu** endpoint chấp nhận XML input và có thể trả JSON output. Input Content-Type và output Accept **không bắt buộc giống nhau**.

### Độ ưu tiên của Accept

~~~http
Accept: application/json, application/xml;q=0.5
~~~

Client ưu tiên JSON hơn XML. Spring xét khả năng của handler và writer; khi cả hai định dạng được hỗ trợ, JSON có thể được chọn dựa trên quy tắc content negotiation và mức ưu tiên.

Nếu Accept là */*, client nói có thể nhận nhiều định dạng, chứ không chỉ định một định dạng duy nhất. Nếu endpoint hỗ trợ JSON và XML, đừng hứa một kết quả cụ thể cho mọi client thiếu Accept; hãy đặt Accept rõ ràng khi kiểm thử.

### GET thường không cần Request Content-Type

~~~bash
curl -i -H 'Accept: application/json' http://localhost:8080/api/products/7
~~~

Header Accept yêu cầu JSON response. Không cần thêm Content-Type: application/json cho một GET **không có body** chỉ để yêu cầu response JSON. Ngược lại, khi gửi POST JSON body, Content-Type của request là thông tin quan trọng.

## 5. Spring MVC dùng HttpMessageConverter

Spring MVC trên Servlet stack sử dụng:

~~~java
org.springframework.http.converter.HttpMessageConverter<T>
~~~

Interface và các implementation đọc/ghi HTTP body qua abstractions HttpInputMessage/HttpOutputMessage, gắn với Servlet request/response.

Một vài triển khai tiêu biểu của Spring Framework 6:

| Converter | Java type tiêu biểu | Media type / nhiệm vụ |
|---|---|---|
| MappingJackson2HttpMessageConverter | JavaBean, DTO, record, Map/List | JSON qua Jackson ObjectMapper |
| StringHttpMessageConverter | String | Text và các supported media types của converter |
| ByteArrayHttpMessageConverter | byte[] | Raw bytes; mặc định có thể ghi application/octet-stream |
| ResourceHttpMessageConverter | Resource | Đọc/ghi tài nguyên và stream file |
| MappingJackson2XmlHttpMessageConverter | DTO/JavaBean | XML qua Jackson XmlMapper khi extension có mặt |
| Jaxb2RootElementHttpMessageConverter | JAXB-annotated bean | XML khi các thành phần JAXB phù hợp có mặt |
| SourceHttpMessageConverter | javax.xml.transform.Source | Đọc/ghi XML Source |
| FormHttpMessageConverter | MultiValueMap và form parts | application/x-www-form-urlencoded và form/multipart support |

Đây là danh sách **ví dụ**, không cam kết tất cả converters luôn có trong mọi ứng dụng. Spring Boot auto-configuration nhìn dependency và config. Với starter-web thường có Jackson JSON; XML cần Jackson XML extension hoặc JAXB hỗ trợ như tài liệu Boot 3.3 mô tả.

### Những câu hỏi khi chọn converter

- Kiểu Java: String, byte[], Resource hay Product?
- Media type: application/json, text/plain, application/xml?
- Đọc hay ghi?
- Converter có đăng ký không?
- Converter có canRead/canWrite cho kiểu và media type đó không?
- Có converter nào khác được đặt trước với phạm vi hỗ trợ quá rộng không?

Converter chỉ giải quyết **representation**. Nó không thực hiện authentication, business validation, database access hoặc xây dựng file PDF thật từ một object bất kỳ.

## 6. Spring WebFlux dùng reader, writer và codec

WebFlux dùng các hợp đồng:

~~~java
org.springframework.http.codec.HttpMessageReader<T>
org.springframework.http.codec.HttpMessageWriter<T>
org.springframework.core.codec.Decoder<T>
org.springframework.core.codec.Encoder<T>
~~~

Dữ liệu request body thường đi qua Publisher<DataBuffer>; decoder chuyển bytes thành object, encoder chuyển object thành DataBuffer; HTTP reader/writer tích hợp codec với media type và headers.

~~~text
HTTP request Flux<DataBuffer>
       |
       v
HttpMessageReader
       |
       v
Decoder (Jackson JSON / String / JAXB XML / ...)
       |
       v
Mono<Product> hoặc Flux<Product>
       |
       v
WebFlux controller + service
       |
       v
HttpMessageWriter
       |
       v
Encoder (Jackson JSON / String / binary / JAXB XML / ...)
       |
       v
HTTP response Publisher<DataBuffer>
~~~

**Không sử dụng HttpMessageConverter MVC để cấu hình WebFlux server**. Ngược lại, WebFlux codecs không tự thay thế MVC message converters.

### JSON trong WebFlux

Thông thường sử dụng Jackson2JsonDecoder/Jackson2JsonEncoder kết hợp HttpMessageReader/Writer khi Jackson có trên classpath. Controller có thể nhận @RequestBody Mono<Product> và trả Mono<Product>.

### XML trong WebFlux

Spring Framework 6.1 có **Jaxb2XmlDecoder/Jaxb2XmlEncoder** trong package org.springframework.http.codec.xml. Chúng áp dụng cho các kiểu JAXB phù hợp khi có thư viện JAXB cần thiết, với registration thích hợp. Không giả định thêm **jackson-dataformat-xml** vào WebFlux sẽ tự biến các JAXB codecs thành MappingJackson2XmlHttpMessageConverter; lớp sau thuộc **MVC**.

Điểm cần kiểm tra là **decoder/encoder XML thực sự đã được WebFlux registry đăng ký** và DTO được hỗ trợ. Nếu không, bổ sung JAXB dependency/codecs theo yêu cầu ứng dụng.

### Backpressure và aggregation

Một JSON document đơn lẻ có thể cần aggregate bytes trong bộ nhớ khi decode; NDJSON cho phép xử lý từng object theo format streaming. WebFlux có backpressure nhưng không loại bỏ mọi buffering. Giới hạn spring.codec.max-in-memory-size cần được đánh giá độc lập với file upload và proxy size limits.

## 7. JSON: object, array, String và kiểu Java

JSON là một tập hợp giá trị có cú pháp chuẩn: object, array, string, number, boolean, null.

~~~json
{
  "id": 7,
  "name": "pen",
  "inStock": true,
  "tags": ["stationery", "office"],
  "price": 12.5
}
~~~

Java có thể biểu diễn cấu trúc này bằng DTO hoặc record:

~~~java
public record ProductDto(
        long id,
        String name,
        boolean inStock,
        java.util.List<String> tags,
        java.math.BigDecimal price) {}
~~~

Đây là khai báo record minh họa để đặt trong project Java 17+. Jackson có thể serialize các accessor của record theo kiểu dữ liệu tương ứng, miễn module/cấu hình runtime hỗ trợ.

### JSON text không giống Java String

Ví dụ response body:

~~~text
hello
~~~

không phải JSON string literal hợp lệ vì JSON string cần dấu nháy:

~~~json
"hello"
~~~

Nếu controller trả String và gắn produces=application/json, **StringHttpMessageConverter có thể ghi raw String**, không nhất thiết Jackson sẽ thêm dấu nháy. Vì vậy để trả JSON object hoặc array, nên dùng DTO, record, Map có kiểu rõ ràng và để JSON converter/codec serialize.

### Không tự ghép JSON bằng nối chuỗi

Phản ví dụ:

~~~java
String json = "{\"name\":\"" + name + "\"}";
~~~

Nếu name chứa dấu nháy, backslash hoặc ký tự đặc biệt, JSON có thể hỏng. Nếu chứa input không tin cậy, còn có nguy cơ thao túng nội dung response. Dùng ObjectMapper/DTO để escape và xây dựng representation đúng.

### Các kiểu dữ liệu cần quyết định rõ

- **Number:** JSON number không phân biệt long/double/BigDecimal; client và server cần thống nhất phạm vi số nguyên, độ chính xác và đơn vị.
- **Date/time:** tránh tự đoán format, timezone; dùng java.time và cấu hình Jackson phù hợp.
- **null/missing:** một property vắng mặt không hoàn toàn giống property có giá trị null.
- **unknown fields:** có thể được bỏ qua hoặc gây lỗi tùy mapper/deserialization policy.
- **Enum:** có thể được biểu diễn bằng tên hoặc custom string, cần xem version API.
- **Nested object/circular graph:** tránh serialize trực tiếp ORM entities có lazy-loading, cycle hoặc bí mật.

### JSON lỗi có thể trả 400

~~~http
POST /api/products HTTP/1.1
Content-Type: application/json

{"id": 7, "name":
~~~

Body không phải JSON hợp lệ, nên decoder/converter có thể từ chối bằng lỗi đọc body, thông thường HTTP 400. Không hiểu nhầm đó là "route không tồn tại".

## 8. Văn bản thuần: text/plain và charset

Một endpoint văn bản thường có Java type String:

~~~java
@GetMapping(
    path = "/greeting",
    produces = MediaType.TEXT_PLAIN_VALUE
)
String greeting() {
    return "Xin chào";
}
~~~

Đây là method đặt trong @RestController. Khi client Accept: text/plain, Spring chọn writer phù hợp để ghi bytes text. Cần hiểu encoding và Content-Type của response, nhất là khi có tiếng Việt.

### Text plain không phải JSON string

Body:

~~~text
Xin chào
~~~

là text/plain. Nếu API muốn JSON string, body phải là:

~~~json
"Xin chào"
~~~

Hai representation có body khác nhau và client parse khác nhau. Đừng trả raw text nhưng khai báo application/json chỉ để "API trông giống JSON".

### UTF-8 và Content-Type

Ví dụ:

~~~http
Content-Type: text/plain; charset=UTF-8
~~~

Nếu tạo bytes thủ công:

~~~java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
~~~

Khi nhận bytes raw text:

~~~java
String text = new String(bytes, StandardCharsets.UTF_8);
~~~

Đây là snippets minh họa, cần import java.nio.charset.StandardCharsets. Cần thống nhất charset giữa client và server để không làm hỏng ký tự có dấu.

**Không dùng platform default charset** cho binary/text protocol khi cần output ổn định giữa Windows, Linux và container. Với Spring MVC 3.3, Boot cung cấp default String converter encoding UTF-8 theo tài liệu; cấu hình tùy chỉnh hoặc proxy vẫn có thể thay kết quả nên test response thực tế.

### Tại sao nên dùng String khi dữ liệu thực sự là text?

String phù hợp cho plain text nhỏ, health marker hoặc file cấu hình dạng text có contract rõ. Nếu nội dung lớn, cân nhắc streaming Resource hoặc cơ chế stream. Nếu là dữ liệu có trường/chú giải cấu trúc, JSON DTO có thể dễ mở rộng và kiểm tra hơn.

## 9. Binary: byte[], Resource và Content-Disposition

Binary là bytes có thể chứa giá trị 0x00 hoặc 0xFF; không phải chuỗi ký tự UTF-8. Tuyệt đối không chuyển tùy tiện qua new String(bytes) rồi lại getBytes() nếu cần **giữ nguyên mọi byte**.

Ví dụ payload ba byte:

~~~text
41 00 FF
~~~

Đây là hex notation cho bytes 0x41, 0x00, 0xFF. Byte đầu là chữ A theo ASCII, hai byte còn lại không phải một chuỗi văn bản thông thường.

### byte[] cho payload nhỏ

~~~java
@GetMapping(
    path = "/download",
    produces = MediaType.APPLICATION_OCTET_STREAM_VALUE
)
byte[] download() {
    return new byte[] {0x41, 0x00, (byte) 0xFF};
}
~~~

Đây là snippet đặt trong @RestController. ByteArrayHttpMessageConverter của MVC hoặc binary codec của WebFlux có thể ghi bytes nguyên dạng. Trả byte[] nhỏ rất tiện, nhưng trả một mảng 1 GB sẽ tạo áp lực bộ nhớ lớn.

### Resource cho nội dung lớn hoặc file

Trong MVC, ResourceHttpMessageConverter hỗ trợ org.springframework.core.io.Resource. Ví dụ trả một file **đã tồn tại, đường dẫn do ứng dụng kiểm soát**:

~~~java
@GetMapping("/download/report")
ResponseEntity<Resource> report() {
    Resource file = new FileSystemResource(
            Path.of("/var/app/reports/report.pdf"));
    return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_PDF)
            .header(
                HttpHeaders.CONTENT_DISPOSITION,
                ContentDisposition.attachment()
                    .filename("report.pdf").build().toString()
            )
            .body(file);
}
~~~

Đây là đoạn minh họa trong MVC controller, cần imports cho Resource, FileSystemResource, Path và các HTTP types, và giả sử file có thật, có quyền đọc. Không ghép đường dẫn từ tên file do client gửi khi chưa chuẩn hóa/kiểm soát, tránh path traversal.

**Điểm quan trọng:** Content-Type application/pdf nói rằng payload là PDF; **Resource converter không tự tạo PDF** từ dữ liệu JSON. File phải chứa bytes PDF hợp lệ.

### Content-Disposition

~~~http
Content-Disposition: attachment; filename="report.pdf"
~~~

Header gợi ý browser tải file xuống với tên tương ứng; nó không bảo đảm client sẽ tuân theo, không bảo vệ dữ liệu và không phải cơ chế authorization. Với Unicode filename, dùng builder của Spring để encode/quote phù hợp thay vì tự nối header chứa input chưa được kiểm tra.

### Content-Length, Range, caching

Các thư viện hoặc resource handlers có thể hỗ trợ Content-Length, Last-Modified, ETag, Range tùy kiểu Resource và handler. Đừng mặc định trả ResponseEntity<byte[]> sẽ tự có streaming hoặc Range support. Với download lớn, xem cấu trúc Resource/ResourceRegion hoặc streaming endpoint phù hợp với phiên bản framework.

### Byte[] có thể biểu diễn PNG, ZIP, PDF mà không có converter chuyên biệt

Một writer raw binary có thể gửi bytes PNG/PDF/ZIP với media type phù hợp, **nếu ứng dụng đã tạo đúng bytes**. Việc writer không hiểu cấu trúc PDF không phải lỗi: nhiệm vụ của nó là chép bytes và headers; trách nhiệm tạo file đúng định dạng nằm ở tầng xử lý tương ứng.

## 10. XML: chỉ khi converter/codec và thư viện phù hợp đã sẵn sàng

XML là một định dạng đánh dấu có element, attribute, namespace, escaping và các quy tắc well-formed riêng.

~~~xml
<product>
    <id>7</id>
    <name>pen</name>
</product>
~~~

Một POJO Java có thể được ánh xạ XML bằng nhiều cơ chế:

- **Jackson XML:** module com.fasterxml.jackson.dataformat:jackson-dataformat-xml, dùng XmlMapper. Spring MVC có MappingJackson2XmlHttpMessageConverter.
- **JAXB:** dùng Jakarta XML Binding API và runtime implementation. Spring MVC có Jaxb2RootElementHttpMessageConverter khi phù hợp; WebFlux có Jaxb2XmlEncoder/Jaxb2XmlDecoder khi codec registry và JAXB khả dụng.
- **Custom XML:** dùng Marshaller/Unmarshaller, Source/XML streams hoặc writer riêng cho API contract đặc biệt.

### Chỉ thêm produces=application/xml chưa đủ

~~~java
@GetMapping(produces = MediaType.APPLICATION_XML_VALUE)
Product product() {
    return new Product(...);
}
~~~

Đây là snippet minh họa. Nếu không có converter/codec nào có thể ghi Product dưới XML, endpoint **không tự hoạt động** chỉ nhờ annotation. Có thể phát sinh lỗi negotiation hoặc lỗi ghi tùy thời điểm và mapping, không nên hứa một status duy nhất cho mọi cấu hình.

### Jackson XML trong Spring MVC và Java 17+

Gradle dependency khi dùng Spring Boot 3.3 dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'com.fasterxml.jackson.dataformat:jackson-dataformat-xml'
}
~~~

Maven cần dependency tương ứng. Boot quản lý version khi BOM/plugin đã được cấu hình. Package annotation của Jackson XML:

~~~java
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlRootElement;
~~~

Ví dụ JavaBean:

~~~java
@JacksonXmlRootElement(localName = "product")
public class Product {
    private long id;
    private String name;

    public Product() {}

    public long getId() { return id; }
    public void setId(long id) { this.id = id; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
}
~~~

Đây là POJO minh họa, cần đặt trong file/class có tên và imports hợp lệ; ví dụ hoàn chỉnh ở phần sau sẽ dùng nested public static class để runnable.

Với Jackson XML converter được đăng ký, DTO có thể được đọc/ghi dưới XML. Khi đổi sang XML, **hình thức root element và property elements** có thể cần annotation; đừng đoán XML root name luôn là tên class hoặc luôn giống JSON field names.

### XML không tương đương 1:1 với JSON

JSON array:

~~~json
{"tags":["java","spring"]}
~~~

XML có thể dùng nhiều thẻ lặp, wrapper element hoặc attributes:

~~~xml
<product>
    <tags>
        <tag>java</tag>
        <tag>spring</tag>
    </tags>
</product>
~~~

Cách ánh xạ cụ thể phụ thuộc DTO, Jackson XML/JAXB annotations và mapper configuration. Namespace, XML attributes, CDATA, mixed content hoặc schema validation đều cần quan tâm riêng; không thể bảo đảm mọi JSON document có bản XML tương đương không mất thông tin.

### XML bảo mật

XML có bề mặt tấn công như external entity resolution/XXE, XML bomb, dữ liệu lồng sâu và tài liệu rất lớn. Với input XML không tin cậy:

- Dùng thư viện parser/converter đã được cập nhật và cấu hình bảo vệ an toàn.
- Vô hiệu hóa DTD/external entity access khi không có nhu cầu hợp lệ.
- Đặt giới hạn kích thước request, độ sâu, entity expansion và tài nguyên được sử dụng.
- Không log XML chứa bí mật hay cấu hình parser cho phép đọc file nội bộ.
- Kiểm tra chính sách security của parser cụ thể và test payload bị từ chối; đừng giả định mọi XML decoder mặc định có chính sách giống nhau.

**Không** dùng tính năng XML nếu API không cần; nhiều ứng dụng có thể chỉ cung cấp JSON để giảm số contract và bề mặt cần bảo trì.

## 11. consumes và produces: khai báo contract của endpoint

Trong controller:

~~~java
@PostMapping(
    path = "/api/products",
    consumes = {
        MediaType.APPLICATION_JSON_VALUE,
        MediaType.APPLICATION_XML_VALUE
    },
    produces = {
        MediaType.APPLICATION_JSON_VALUE,
        MediaType.APPLICATION_XML_VALUE
    }
)
~~~

Ý nghĩa:

- POST body **có thể** là JSON hoặc XML.
- Client **có thể** yêu cầu JSON hoặc XML response.
- Spring phải có reader/converter thích hợp **cho input type** và writer thích hợp **cho output type**.
- consumes/produces là các điều kiện routing/content negotiation, không tự cài codec.

Một request JSON tới endpoint có thể nhận XML response:

~~~http
POST /api/products HTTP/1.1
Content-Type: application/json
Accept: application/xml

{"id":7,"name":"pen"}
~~~

Server hoàn toàn có thể deserialize JSON vào Product rồi serialize Product thành XML. Khi muốn biến đổi dữ liệu nghiệp vụ, controller/service quyết định transformation; converter chỉ lo wire representation.

### Một handler hỗ trợ nhiều media types

Nếu cùng business logic, thường dễ duy trì một method:

~~~java
@GetMapping(
    path = "/api/products/{id}",
    produces = {
        MediaType.APPLICATION_JSON_VALUE,
        MediaType.APPLICATION_XML_VALUE
    }
)
Product get(@PathVariable long id) {
    return new Product(...);
}
~~~

Thay vì tạo hai method có cùng path/method chỉ khác produces rồi phải đồng bộ business logic. Nếu XML/JSON có schema khác nhau đáng kể, hãy thiết kế DTO hoặc method chuyên biệt có chủ đích.

### Đừng đoán response khi Accept mơ hồ

Một endpoint quảng bá JSON và XML nhưng client gửi Accept: */* có nhiều lựa chọn có thể chấp nhận. Việc converter nào được ưu tiên có thể phụ thuộc thứ tự registry, media type và cấu hình. Client cần representation cụ thể nên gửi **Accept chính xác**; automated tests cũng vậy.

## 12. Ví dụ Spring Boot MVC chạy được: JSON, text, binary và XML

Đây là project **Spring MVC riêng**, dùng Java 17+ và Spring Boot 3.3.x. Dự án có embedded Tomcat từ starter-web và Jackson XML từ dependency bổ sung.

### 12.1. Dependencies

Trong build.gradle của project đã có Spring Boot Gradle plugin, repositories và Java toolchain:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'com.fasterxml.jackson.dataformat:jackson-dataformat-xml'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đây là **phần dependencies**, không phải toàn bộ build.gradle. Nếu dùng Maven, thêm các dependency tương ứng theo Spring Boot BOM. Không cần tự khai báo một version bất kỳ cho jackson-dataformat-xml khi Boot dependency management đã quản lý đúng.

### 12.2. Java source file hoàn chỉnh

Tạo **src/main/java/com/example/formats/FormatsApplication.java**:

~~~java
package com.example.formats;

import java.util.Locale;
import java.util.Map;

import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlRootElement;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class FormatsApplication {

    public static void main(String[] args) {
        SpringApplication.run(FormatsApplication.class, args);
    }

    @JacksonXmlRootElement(localName = "product")
    public static class Product {

        private long id;
        private String name;

        public Product() {}

        public Product(long id, String name) {
            this.id = id;
            this.name = name;
        }

        public long getId() {
            return id;
        }

        public void setId(long id) {
            this.id = id;
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }
    }

    @RestController
    @RequestMapping("/api")
    public static class FormatsController {

        @GetMapping(
                path = "/products/{id}",
                produces = {
                    MediaType.APPLICATION_JSON_VALUE,
                    MediaType.APPLICATION_XML_VALUE
                }
        )
        public Product find(@PathVariable long id) {
            return new Product(id, "item-" + id);
        }

        @PostMapping(
                path = "/products/echo",
                consumes = {
                    MediaType.APPLICATION_JSON_VALUE,
                    MediaType.APPLICATION_XML_VALUE
                },
                produces = {
                    MediaType.APPLICATION_JSON_VALUE,
                    MediaType.APPLICATION_XML_VALUE
                }
        )
        public Product echo(@RequestBody Product product) {
            return product;
        }

        @GetMapping(
                path = "/text",
                produces = MediaType.TEXT_PLAIN_VALUE
        )
        public String text() {
            return "Xin chào";
        }

        @PostMapping(
                path = "/text/upper",
                consumes = MediaType.TEXT_PLAIN_VALUE,
                produces = MediaType.TEXT_PLAIN_VALUE
        )
        public String upper(@RequestBody String text) {
            return text.toUpperCase(Locale.ROOT);
        }

        @GetMapping(
                path = "/bytes",
                produces = MediaType.APPLICATION_OCTET_STREAM_VALUE
        )
        public ResponseEntity<byte[]> bytes() {
            byte[] data = new byte[] {
                0x41, 0x00, (byte) 0xFF
            };

            return ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_OCTET_STREAM)
                    .header(
                            HttpHeaders.CONTENT_DISPOSITION,
                            ContentDisposition.attachment()
                                    .filename("sample.bin")
                                    .build().toString()
                    )
                    .body(data);
        }

        @PostMapping(
                path = "/bytes/count",
                consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE,
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        public Map<String, Integer> count(@RequestBody byte[] data) {
            return Map.of("size", data.length);
        }
    }
}
~~~

**Đây là một Java file hoàn chỉnh** trong project Spring Boot đã khai báo dependencies. Không dùng lệnh javac trần nếu không cung cấp Spring, Servlet và Jackson trên classpath. Nested public static Product có zero-argument constructor cùng getters/setters để Jackson JSON và Jackson XML có thể đọc/ghi; @JacksonXmlRootElement quyết định XML root element.

### 12.3. Cấu hình và khởi động

Tạo **src/main/resources/application.yml**:

~~~yaml
server:
  port: 8080
~~~

Từ root project Gradle:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Đợi embedded server khởi động. Nếu port 8080 đang bận, đổi server.port và thay URL trong các lệnh thử.

### 12.4. JSON response

~~~bash
curl -i http://localhost:8080/api/products/7 \
  -H 'Accept: application/json'
~~~

Response điển hình:

~~~http
HTTP/1.1 200
Content-Type: application/json

{"id":7,"name":"item-7"}
~~~

Header có thể có tham số; thứ tự key, whitespace, content length do runtime quyết định. Ý nghĩa body là id=7 và name=item-7.

### 12.5. XML response từ cùng endpoint

~~~bash
curl -i http://localhost:8080/api/products/7 \
  -H 'Accept: application/xml'
~~~

Một body XML có ý nghĩa tương đương:

~~~xml
<product>
    <id>7</id>
    <name>item-7</name>
</product>
~~~

Jackson XML có thể bỏ whitespace xuống dòng hoặc bổ sung XML declaration tùy cấu hình; vì vậy **không so sánh raw XML string byte-for-byte** như một hợp đồng mặc định. Test nên kiểm tra XML well-formed, root element và nội dung field cần thiết.

### 12.6. JSON request, XML response

~~~bash
curl -i -X POST http://localhost:8080/api/products/echo \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/xml' \
  --data '{"id":8,"name":"pen"}'
~~~

Request JSON được deserialize thành Product, sau đó Product được serialize ra XML. Mục đích bài thực hành là chứng minh **Content-Type input và Accept output độc lập**.

### 12.7. XML request, JSON response

~~~bash
curl -i -X POST http://localhost:8080/api/products/echo \
  -H 'Content-Type: application/xml' \
  -H 'Accept: application/json' \
  --data '<product><id>8</id><name>pen</name></product>'
~~~

Body response JSON có ý nghĩa:

~~~json
{"id":8,"name":"pen"}
~~~

Nếu POST này thất bại trong một dự án khác, kiểm tra XML converter đã được đăng ký, POJO có constructor/getters/setters/annotations tương thích, request Content-Type, parser và exception log. Không sửa bằng cách gắn nhãn JSON vào XML bytes.

### 12.8. Text/plain

~~~bash
curl -i http://localhost:8080/api/text \
  -H 'Accept: text/plain'
~~~

Body được tạo bởi code là:

~~~text
Xin chào
~~~

Gửi text body:

~~~bash
curl -i -X POST http://localhost:8080/api/text/upper \
  -H 'Content-Type: text/plain; charset=UTF-8' \
  -H 'Accept: text/plain' \
  --data-binary 'hello'
~~~

Body chính xác cho ASCII:

~~~text
HELLO
~~~

Chọn chuỗi ASCII trong test này để so sánh byte/text đơn giản; với chữ có dấu hãy kiểm tra UTF-8 và Unicode normalization theo môi trường.

### 12.9. Binary response

~~~bash
curl -i http://localhost:8080/api/bytes \
  -H 'Accept: application/octet-stream'
~~~

Response mang ba byte 0x41 0x00 0xFF, không phải ba ký tự hiển thị an toàn. Nên lưu ra file:

~~~bash
curl -sS http://localhost:8080/api/bytes -o sample.bin
~~~

Trên Linux/macOS có thể xem hex:

~~~bash
od -An -tx1 sample.bin
~~~

Giá trị hex mong đợi:

~~~text
41 00 ff
~~~

Dấu cách và định dạng dòng của lệnh od có thể khác; ba byte là kết quả cần đối chiếu. Không mở một file nhị phân tùy ý dưới dạng UTF-8 để xem nó có đúng không.

### 12.10. Binary request, JSON response

Tạo file input.bin có ba byte 0x41, 0x00, 0xFF; hoặc gửi file sample.bin vừa tải:

~~~bash
curl -i -X POST http://localhost:8080/api/bytes/count \
  -H 'Content-Type: application/octet-stream' \
  -H 'Accept: application/json' \
  --data-binary '@sample.bin'
~~~

Response body:

~~~json
{"size":3}
~~~

Điều này chứng minh ByteArrayHttpMessageConverter đọc raw bytes cho tham số byte[], trong khi Jackson JSON converter ghi kết quả Map thành JSON.

### 12.11. PowerShell: tránh lỗi escape

Trên Windows, gọi curl.exe để tránh alias curl trong Windows PowerShell:

~~~powershell
curl.exe -i -H "Accept: application/json" "http://localhost:8080/api/products/7"
curl.exe -i -H "Accept: application/xml" "http://localhost:8080/api/products/7"
curl.exe -sS "http://localhost:8080/api/bytes" -o sample.bin
curl.exe -i -X POST "http://localhost:8080/api/bytes/count" -H "Content-Type: application/octet-stream" -H "Accept: application/json" --data-binary "@sample.bin"
~~~

Khi gửi JSON/XML nhiều dấu nháy, cách ổn định là ghi body ra file UTF-8 và dùng --data-binary "@payload.json" hoặc "@payload.xml"; tránh phụ thuộc sự khác nhau giữa escaping của PowerShell 5.1 và PowerShell 7.

## 13. Kiểm thử ví dụ MVC bằng MockMvc

Tạo **src/test/java/com/example/formats/FormatsApplicationTests.java**:

~~~java
package com.example.formats;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FormatsApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void producesJsonWhenClientAcceptsJson() throws Exception {
        mvc.perform(get("/api/products/9")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.id").value(9))
            .andExpect(jsonPath("$.name").value("item-9"));
    }

    @Test
    void producesXmlWhenClientAcceptsXml() throws Exception {
        mvc.perform(get("/api/products/9")
                    .accept(MediaType.APPLICATION_XML))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_XML))
            .andExpect(content().string(
                    containsString("<name>item-9</name>")));
    }

    @Test
    void canReadXmlAndReturnJson() throws Exception {
        mvc.perform(post("/api/products/echo")
                    .contentType(MediaType.APPLICATION_XML)
                    .accept(MediaType.APPLICATION_JSON)
                    .content(
                        "<product><id>8</id><name>pen</name></product>"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(8))
            .andExpect(jsonPath("$.name").value("pen"));
    }

    @Test
    void returnsPlainText() throws Exception {
        mvc.perform(post("/api/text/upper")
                    .contentType(MediaType.TEXT_PLAIN)
                    .accept(MediaType.TEXT_PLAIN)
                    .content("hello"))
            .andExpect(status().isOk())
            .andExpect(content().string("HELLO"));
    }

    @Test
    void returnsExactBinaryBytes() throws Exception {
        mvc.perform(get("/api/bytes")
                    .accept(MediaType.APPLICATION_OCTET_STREAM))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_OCTET_STREAM))
            .andExpect(content().bytes(
                    new byte[]{0x41, 0x00, (byte) 0xFF}));
    }

    @Test
    void rejectsUnsupportedRequestContentType() throws Exception {
        mvc.perform(post("/api/products/echo")
                    .contentType(MediaType.TEXT_PLAIN)
                    .content("hello"))
            .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void rejectsUnacceptableResponseType() throws Exception {
        mvc.perform(get("/api/products/9")
                    .accept(MediaType.APPLICATION_PDF))
            .andExpect(status().isNotAcceptable());
    }

    @Test
    void rejectsMalformedJson() throws Exception {
        mvc.perform(post("/api/products/echo")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("{bad-json"))
            .andExpect(status().isBadRequest());
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Các test kiểm tra lựa chọn JSON/XML, chuyển XML input thành JSON output, text, binary đúng từng byte, lỗi input media type (415), output media type (406) và JSON malformed (400).

**Lưu ý:** Test XML kiểm tra một field trong XML, không buộc raw response giống một chuỗi có indentation/cấu trúc khoảng trắng cố định. Nếu DTO/XML mapping thay đổi, bổ sung XML parser assertion cho namespace/root/schema thay vì dựa vào vị trí các dấu cách.

MockMvc kiểm tra Servlet MVC pipeline mà không cần mở TCP socket thật. Nó không thay thế integration test khi deployment có reverse proxy, TLS hoặc body size limit của container.

## 14. Cấu hình converter trong Spring Boot MVC

Spring Boot 3.3 tự đăng ký converters dựa trên classpath. Với starter-web, JSON thường sẵn có. Thêm Jackson XML extension có thể khiến XML converter tương ứng xuất hiện khi Boot auto-configuration phù hợp.

### Cách quan sát registry thật sự

Có thể tiêm RequestMappingHandlerAdapter trong MVC application và in danh sách:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerAdapter;

@Configuration(proxyBeanMethods = false)
class ConverterDiagnostics {

    @Bean
    ApplicationRunner showConverters(
            RequestMappingHandlerAdapter adapter) {
        return args -> adapter.getMessageConverters().forEach(
                c -> System.out.println(
                        c.getClass().getSimpleName() + " " +
                        c.getSupportedMediaTypes()
                )
        );
    }
}
~~~

Đây là một **class cấu hình bổ sung** trong project MVC. Nó hữu ích để xem converters thực tế; không chạy riêng bằng javac. Không mặc định thứ tự output giống nhau trong mọi version/classpath.

### Thêm converter mới khi nào?

Nếu định dạng lạ có contract rõ, có thể viết HttpMessageConverter phù hợp hoặc bean converter bổ sung. Với text/plain, JSON, byte[] và Resource, thường **không cần** viết custom converter. Với XML, ưu tiên thư viện XML chuẩn đã tích hợp hơn là tự ghép XML bằng String.

### Thay đổi ObjectMapper

Nếu chỉ muốn đổi tên field, date format, inclusion, deserializer hoặc serializer JSON, nên chỉnh Jackson ObjectMapper/Boot Jackson customizer thay vì thay cả message converter.

Ví dụ property:

~~~yaml
spring:
  jackson:
    serialization:
      indent-output: true
~~~

Nó có thể bật pretty-print cho Jackson JSON. Không làm binary bytes đổi hay tự động thêm XML writer nếu thiếu dependency.

### WebMvcConfigurer

~~~java
@Configuration(proxyBeanMethods = false)
class ConverterConfig implements WebMvcConfigurer {

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters) {
        // Chỉ thay đổi khi đã xác định converter cần tinh chỉnh.
    }
}
~~~

Đây là snippet cấu hình; imports cần các Spring types tương ứng. extendMessageConverters cho phép tinh chỉnh danh sách đã được đăng ký. **Không dùng @EnableWebMvc chỉ để thêm XML**, vì điều đó có thể vô hiệu hóa các tiện ích auto-configuration MVC của Boot.

## 15. Ví dụ tương đương trong Spring WebFlux

Phần này dùng **project riêng**, không ghép starter-webflux vào project MVC và mặc định nó chuyển sang reactive. Spring Boot có cả starter-web và starter-webflux thường chọn MVC mặc định.

### Dependencies

Trong build.gradle của project WebFlux đã có plugin/repository:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'jakarta.xml.bind:jakarta.xml.bind-api'
    implementation 'org.glassfish.jaxb:jaxb-runtime'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Ở đây XML đi qua **JAXB** trong WebFlux 6.1, không phải MappingJackson2XmlHttpMessageConverter của MVC. Spring WebFlux có Jaxb2XmlDecoder/Jaxb2XmlEncoder khi classpath/configuration phù hợp. Nếu runtime không đăng ký XML codec, cần kiểm tra registry và cấu hình explicit theo nhu cầu; không mặc định mọi phụ thuộc XML đều được auto-detect như nhau.

### Java source file cho WebFlux

Tạo **src/main/java/com/example/reactiveformats/ReactiveFormatsApplication.java**:

~~~java
package com.example.reactiveformats;

import java.util.Locale;

import jakarta.xml.bind.annotation.XmlAccessType;
import jakarta.xml.bind.annotation.XmlAccessorType;
import jakarta.xml.bind.annotation.XmlRootElement;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class ReactiveFormatsApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                ReactiveFormatsApplication.class, args);
    }

    @XmlRootElement(name = "product")
    @XmlAccessorType(XmlAccessType.FIELD)
    public static class Product {

        private long id;
        private String name;

        public Product() {}

        public Product(long id, String name) {
            this.id = id;
            this.name = name;
        }

        public long getId() {
            return id;
        }

        public void setId(long id) {
            this.id = id;
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }
    }

    @RestController
    public static class Controller {

        @GetMapping(
                path = "/api/products/{id}",
                produces = {
                    MediaType.APPLICATION_JSON_VALUE,
                    MediaType.APPLICATION_XML_VALUE
                }
        )
        public Mono<Product> get(@PathVariable long id) {
            return Mono.just(new Product(id, "item-" + id));
        }

        @PostMapping(
                path = "/api/products/echo",
                consumes = {
                    MediaType.APPLICATION_JSON_VALUE,
                    MediaType.APPLICATION_XML_VALUE
                },
                produces = {
                    MediaType.APPLICATION_JSON_VALUE,
                    MediaType.APPLICATION_XML_VALUE
                }
        )
        public Mono<Product> echo(
                @RequestBody Mono<Product> input) {
            return input;
        }

        @PostMapping(
                path = "/api/text/upper",
                consumes = MediaType.TEXT_PLAIN_VALUE,
                produces = MediaType.TEXT_PLAIN_VALUE
        )
        public Mono<String> upper(
                @RequestBody Mono<String> input) {
            return input.map(
                    s -> s.toUpperCase(Locale.ROOT));
        }

        @GetMapping(
                path = "/api/bytes",
                produces = MediaType.APPLICATION_OCTET_STREAM_VALUE
        )
        public Mono<byte[]> bytes() {
            return Mono.just(
                    new byte[]{0x41, 0x00, (byte) 0xFF});
        }
    }
}
~~~

Code trên là một file hoàn chỉnh trong project WebFlux có dependencies tương ứng. Các JAXB annotations khai báo root và field mapping để JAXB XML codec hiểu DTO. Jackson JSON có thể serialize/deserialize qua getters/setters. Không có Servlet HttpMessageConverter trong code này.

Nếu ứng dụng không nhận XML dù đã có JAXB dependencies, một cách mở rộng **có chủ đích** là đăng ký Jaxb2XmlDecoder/Encoder trong ServerCodecConfigurer:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.DecoderHttpMessageReader;
import org.springframework.http.codec.EncoderHttpMessageWriter;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.http.codec.xml.Jaxb2XmlDecoder;
import org.springframework.http.codec.xml.Jaxb2XmlEncoder;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
class AdditionalXmlCodecs implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.customCodecs().register(
                new DecoderHttpMessageReader<>(
                        new Jaxb2XmlDecoder()));
        configurer.customCodecs().register(
                new EncoderHttpMessageWriter<>(
                        new Jaxb2XmlEncoder()));
    }
}
~~~

Đây là một **class bổ sung tùy chọn**, chỉ dùng sau khi xác minh registry chưa có codec XML phù hợp và DTO thực sự hỗ trợ JAXB. Nếu default codecs đã có XML, không đăng ký bản sao vô ích. Tránh tắt registerDefaults(false) vì có thể làm mất cả JSON, text và binary codecs.

### Cấu hình buffer cho WebFlux

~~~yaml
spring:
  codec:
    max-in-memory-size: 512KB
~~~

Property Boot 3.3 giúp giới hạn buffering ở các codecs khi cần aggregate dữ liệu. Nó không phải giới hạn kích thước toàn bộ file upload hay mọi response. Với JSON/XML document lớn, cần cân nhắc quota, streaming và request size limits. Khi dùng WebClient tự tạo bằng builder riêng, xác minh cấu hình codec tương ứng thay vì cho rằng server property luôn áp dụng.

### Kiểm tra WebFlux bằng curl

~~~bash
curl -i -H 'Accept: application/json' \
  http://localhost:8080/api/products/7

curl -i -H 'Accept: application/xml' \
  http://localhost:8080/api/products/7

curl -i -X POST \
  -H 'Content-Type: text/plain' \
  -H 'Accept: text/plain' \
  --data-binary 'hello' \
  http://localhost:8080/api/text/upper
~~~

JSON và XML cần codec tương ứng; text endpoint trả HELLO. Với XML, nếu ứng dụng không nhận representation thì phải xem lỗi cụ thể và XML codec registry, không tự đổi media type để che lỗi.

## 16. Kiểm thử WebFlux bằng WebTestClient

Tạo **src/test/java/com/example/reactiveformats/ReactiveFormatsApplicationTests.java**:

~~~java
package com.example.reactiveformats;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class ReactiveFormatsApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void writesJson() {
        client.get()
                .uri("/api/products/7")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(7)
                .jsonPath("$.name").isEqualTo("item-7");
    }

    @Test
    void writesXmlWhenJaxbCodecIsAvailable() {
        client.get()
                .uri("/api/products/7")
                .accept(MediaType.APPLICATION_XML)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_XML);
    }

    @Test
    void readsTextAndReturnsUppercase() {
        client.post()
                .uri("/api/text/upper")
                .contentType(MediaType.TEXT_PLAIN)
                .accept(MediaType.TEXT_PLAIN)
                .bodyValue("hello")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("HELLO");
    }

    @Test
    void rejectsUnacceptableMediaType() {
        client.get()
                .uri("/api/products/7")
                .accept(MediaType.APPLICATION_PDF)
                .exchange()
                .expectStatus().isNotAcceptable();
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

WebTestClient kiểm tra HTTP-level behavior của WebFlux. Test XML xác nhận header/status khi JAXB codec thực sự sẵn sàng; trong môi trường khác, có thể cần custom codec và bảo đảm JAXB runtime. Bổ sung XML parser validation nếu API có XML schema/namespace bắt buộc.

**Không** tự gọi .block() trong WebFlux controller để lấy XML/JSON object từ Mono, và không tự subscribe() để ghi response. Runtime quản lý subscription/cancellation, codecs làm việc với publisher.

## 17. Form, multipart và raw binary: phân biệt nội dung ở nhiều tầng

Một request multipart/form-data có thể chứa file PNG, JSON metadata và text part trong cùng một body:

~~~http
POST /upload HTTP/1.1
Content-Type: multipart/form-data; boundary=...

--...
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"name":"demo"}
--...
Content-Disposition: form-data; name="file"; filename="image.png"
Content-Type: image/png

...PNG bytes...
--...--
~~~

Đây là sơ đồ minh họa multipart với boundary rút gọn, không phải payload gửi trực tiếp hợp lệ vì boundary/footer đã viết bằng dấu ba chấm.

**Request top-level Content-Type là multipart/form-data**; từng part có thể có Content-Type riêng như application/json hoặc image/png. Vì thế:

- MVC có MultipartFile, Part, @RequestPart, MultipartResolver/Servlet multipart support.
- WebFlux có FilePart, Part, PartEvent hoặc getMultipartData theo nhu cầu.
- @RequestPart với một JSON metadata part có thể dùng message converter/reader cho **part body** khi định dạng đúng.
- Không dùng @RequestBody byte[] đọc mọi multipart rồi coi toàn bộ bytes là file PNG.
- Gọi raw body và tự parse boundary thường là việc không cần thiết và dễ sai.

Dạng application/x-www-form-urlencoded cũng không phải JSON; với MVC thông thường dùng @RequestParam/@ModelAttribute, với WebFlux có getFormData và body readers thích hợp.

## 18. Khi nào cần streaming thay vì chuyển cả body thành mảng?

Dùng byte[] phù hợp payload nhỏ. Với file/download lớn hoặc server-sent events, tránh gom toàn bộ nội dung vào memory.

### MVC streaming

Spring MVC có StreamingResponseBody, Resource và resource handlers. Khi dùng StreamingResponseBody, ứng dụng chủ động ghi byte vào OutputStream, không phải Jackson serialization DTO.

Snippet minh họa:

~~~java
@GetMapping(
    path = "/stream",
    produces = MediaType.APPLICATION_OCTET_STREAM_VALUE
)
StreamingResponseBody stream() {
    return output -> {
        output.write(new byte[]{0x41, 0x42, 0x43});
    };
}
~~~

Đây là method trong @RestController với import StreamingResponseBody, không phải chương trình standalone. Đối với lượng dữ liệu lớn, cần xử lý I/O, flush, exception/cancellation và resource ownership. Không assume streaming làm mọi tác vụ chạy không dùng heap.

### WebFlux streaming

WebFlux có thể viết Flux<DataBuffer>, Resource, Flux<DTO> theo media type. Với NDJSON:

~~~java
@GetMapping(
    path = "/events",
    produces = MediaType.APPLICATION_NDJSON_VALUE
)
Flux<EventDto> events() {
    return Flux.just(
        new EventDto(1, "started"),
        new EventDto(2, "finished")
    );
}
~~~

Đây là snippet với record EventDto và imports thích hợp. NDJSON là nhiều JSON object theo dòng, **không phải một JSON array**. Streaming có thể bị buffer bởi proxy/client; cần test bằng curl -N hoặc reactive client có bodyToFlux.

### Binary streaming và DataBuffer ownership

Trong WebFlux, pooled DataBuffer có thể cần release đúng contract khi ứng dụng chủ động giữ/bỏ buffer. Nếu chỉ trả DTO/byte[] nhỏ qua codec chuẩn, hãy để framework quản lý. Đừng tự subscribe raw body rồi đồng thời chuyển cùng body vào @RequestBody; stream không tự replay.

## 19. Mã lỗi HTTP thường gặp theo định dạng

| Tình huống | Phản hồi điển hình | Điểm kiểm tra |
|---|---|---|
| JSON request sai cú pháp | 400 Bad Request | JSON parser, DTO, Content-Type |
| XML request sai cú pháp | 400 Bad Request | XML parser, DTO mapping, Content-Type |
| @RequestBody required nhưng body trống | 400 Bad Request | Required/body binding |
| Gửi text/plain tới endpoint chỉ consumes JSON/XML | 415 Unsupported Media Type | Request Content-Type |
| Client chỉ Accept PDF trong khi endpoint chỉ produces JSON/XML | 406 Not Acceptable | Accept, produces, available writers |
| Controller không có path phù hợp | 404 Not Found | Handler mapping, path |
| HTTP method không được hỗ trợ | 405 Method Not Allowed | GET/POST/PUT,... |
| Serializer thất bại khi ghi object | Có thể 500 hoặc stream lỗi | Converter/writer, object graph |
| Body vượt giới hạn | Status phụ thuộc layer/config | Proxy/server/codec limits |
| Dữ liệu ảnh trả với bytes khác PNG | Client parse thất bại dù HTTP 200 | Payload thật và Content-Type |

**Không cam kết một status chung cho mọi trường hợp thiếu XML converter.** Khi handler matches consumes/produces nhưng không có converter có thể đọc/ghi DTO, lỗi có thể khác theo bước chọn handler, framework và exception handling. Hãy xem application logs và test đúng phiên bản.

### Đừng nhầm 406 với 415

- **415:** client đang gửi một request body mà server không chấp nhận/không đọc được theo media type.
- **406:** client yêu cầu response representation mà server không thể cung cấp.

Ví dụ Accept: application/xml nhưng request Content-Type: application/json không phải lý do gây 415. Chỉ khi input JSON không được chấp nhận mới cần điều chỉnh Content-Type/consumes.

## 20. Phân biệt converter, encoder, parser và schema validator

Những khái niệm dễ bị gộp chung:

| Khái niệm | Vai trò |
|---|---|
| HttpMessageConverter (MVC) | Tích hợp đọc/ghi HTTP body và content type |
| HttpMessageReader/Writer (WebFlux) | Tích hợp HTTP body với reactive codec |
| Jackson ObjectMapper | Serialize/deserialize JSON |
| Jackson XmlMapper | Serialize/deserialize XML theo Jackson |
| JAXB Marshaller/Unmarshaller | Ánh xạ Java objects và XML theo JAXB |
| String decoder/encoder | Chuyển byte và char theo charset |
| Byte[]/Resource converter | Đọc/ghi bytes và tài nguyên |
| JSON Schema/XML Schema validator | Kiểm tra cấu trúc theo schema do ứng dụng yêu cầu |
| Bean Validation | Kiểm tra constraint ở Java DTO, ví dụ @NotBlank |
| ConversionService | Chuyển giữa các Java types trong binding, không phải HTTP body decoder |

**Một XML document well-formed chưa chắc thỏa XML Schema**, và một JSON object parse được chưa chắc vượt qua Bean Validation hoặc business rules.

Ví dụ DTO:

~~~java
public record CreateProduct(
    @NotBlank String name,
    @Min(1) int quantity
) {}
~~~

Đây là record Java 17+ minh họa, cần jakarta.validation constraints và spring-boot-starter-validation. Sau khi converter/codec tạo DTO, Spring Validation có thể kiểm tra nếu tham số được khai báo @Valid. Validation không làm parser tự hiểu sai cấu trúc thành dữ liệu đúng.

## 21. Dữ liệu hóa response và phiên bản API

Một API hỗ trợ nhiều format cần quyết định có **cùng schema semantic** hay không. Ví dụ một record Java có price BigDecimal, date/time và tags:

~~~json
{
  "id": 3,
  "price": "19.95",
  "effectiveAt": "2026-01-01T00:00:00Z",
  "tags": ["new", "sale"]
}
~~~

Đây là một contract giả định do ứng dụng thiết kế, không phải cách Jackson mặc định bắt buộc serialize BigDecimal thành String; nếu muốn chuỗi tiền tệ, cần DTO field String hoặc custom serializer.

XML representation có thể cần root element, namespace và wrapper cho tags. Khi client giữ một schema lâu dài, thay đổi field naming, kiểu number hoặc array structure là thay đổi contract ngay cả khi endpoint vẫn trả 200.

### Cẩn thận với Accept và versioning

~~~http
Accept: application/vnd.example.product.v1+json
~~~

Đây là ví dụ custom vendor media type. Converter JSON có thể hỗ trợ application/*+json, nhưng handler produces phải cho phép representation tương ứng và API phải duy trì version contract. Đừng coi việc thêm +json là tự tạo version mới từ dữ liệu.

### Vary: Accept với cache

Nếu cùng URL có thể trả JSON và XML theo Accept, cache/proxy cần phân biệt representation, thường liên quan:

~~~http
Vary: Accept
~~~

Không assume header này luôn được framework tự thêm trong mọi path, cấu hình proxy hoặc cache. Kiểm tra thực tế và cấu hình policy phù hợp để tránh client yêu cầu XML nhưng nhận JSON được cache dưới cùng URL.

## 22. Lưu ý về JSON/XML parsing và bảo mật

### Không deserialize các loại Java tùy ý từ input

Nếu mapper được bật polymorphic default typing quá rộng cho data không tin cậy, có nguy cơ chấp nhận loại object không mong muốn. Hãy dùng DTO đích rõ ràng và cấu hình mapper an toàn. Không đưa thẳng persistence entity/password hash/token vào response.

### Giới hạn size, depth, concurrent requests

Một JSON array lớn hoặc XML rất sâu có thể tiêu tốn CPU/memory. Giới hạn cần ở nhiều lớp:

- Reverse proxy hoặc ingress.
- Servlet container/Reactor Netty HTTP runtime.
- Codec/request body aggregation.
- Multipart settings.
- Business-level count, pagination, rate limit và timeouts.

Không tăng max-in-memory-size lên hàng trăm MB chỉ để hết lỗi mà không đánh giá số request đồng thời và memory budget.

### XML entity expansion / external resources

Không để parser tải external DTD, external entities hoặc truy cập filesystem/network khi input đến từ client, trừ khi có yêu cầu đặc biệt được kiểm soát. Kiểm tra cấu hình và test XXE/DoS cụ thể cho parser implementation đang dùng.

### Content-Type sniffing

Browser có thể diễn giải một số nội dung khác cách server gắn header nếu thiếu chính sách bảo vệ. Đối với binary download hoặc nội dung không đáng tin, cân nhắc:

~~~http
X-Content-Type-Options: nosniff
~~~

Header này là một phần của security hardening, không thay xác thực/authorization, không sửa bytes sai định dạng.

### Binary file từ user upload

Nếu cho phép upload ảnh/PDF/ZIP, không tin hoàn toàn filename, extension hoặc Content-Type do client khai báo. Có thể cần kiểm tra magic bytes, parser an toàn, size limit, antivirus, storage isolation, access-control và download Content-Disposition. Không lưu trực tiếp file dưới tên/path do client gửi.

## 23. Debug thực tế: xác định converter/codec nào tham gia

Khi response không đúng:

1. **Xác nhận web stack:** MVC hay WebFlux? Có cả starter-web và starter-webflux không?
2. **Xem incoming headers:** Content-Type request và Accept response preference có thực sự tới server không?
3. **Xem controller annotations:** consumes/produces, path và HTTP method.
4. **Xem Java types:** @RequestBody Product hay String/byte[]? Controller trả DTO, String, Resource, Mono/Flux?
5. **Xem classpath:** Jackson JSON có không? Với XML có jackson-dataformat-xml hoặc JAXB API/runtime phù hợp không?
6. **Xem converter/codec registry:** type/media support, thứ tự và customizations.
7. **Xem exception:** HttpMessageNotReadableException, HttpMessageNotWritableException, UnsupportedMediaType, NotAcceptable, DataBufferLimitException, XML parse error.
8. **Test với curl:** dùng -i cho headers, -H Accept phù hợp, --data-binary cho raw bodies, -o khi tải binary.
9. **Kiểm tra bytes thực:** JSON parser/XML parser/hex viewer, không chỉ nhìn file extension.
10. **Kiểm tra proxy/cache/security:** forwarded headers, cache Vary, CORS, content sniffing và payload limits.

### Log converter trong MVC

~~~java
@Configuration(proxyBeanMethods = false)
class DiagnosticsConfig {

    @Bean
    ApplicationRunner listConverters(
            RequestMappingHandlerAdapter adapter) {
        return args -> adapter.getMessageConverters().forEach(
                converter -> System.out.println(
                    converter.getClass().getName())
        );
    }
}
~~~

Đây là snippet configuration, cần imports trong project MVC. Nó quan sát danh sách runtime của MVC adapter, không phải WebFlux codecs.

### Log codec trong WebFlux

Spring Boot có ServerCodecConfigurer và CodecCustomizer. Một configurer do bạn tự tạo không nhất thiết đã được áp dụng customizers của Boot, nên đừng dùng ServerCodecConfigurer.create() độc lập rồi tuyên bố đó là runtime registry. Debug WebFluxConfigurer/CodecCustomizer thực tế hoặc inspect bean đã cấu hình để xác định decoder/encoder sẵn có.

Log ở DEBUG/TRACE có thể tiết lộ headers/body, nhất là khi dùng spring.codec.log-request-details; chỉ bật theo chính sách bảo vệ dữ liệu.

## 24. Những lỗi phổ biến và hướng sửa

### Lỗi 1: Client yêu cầu XML nhưng không có XML dependency

Dấu hiệu: API JSON hoạt động, XML request/response không chạy. Kiểm tra Spring MVC có MappingJackson2XmlHttpMessageConverter hoặc JAXB converter phù hợp; WebFlux có JAXB XML codec đã đăng ký chưa. Thêm dependency/config cần thiết và test; không đổi header XML thành JSON để che vấn đề.

### Lỗi 2: Controller trả String chứa JSON và đặt application/json

Dấu hiệu: client parse lỗi JSON, đặc biệt khi String không có dấu nháy hoặc dấu escape đúng. Trả DTO/Map và để Jackson serialize. Nếu đó là text thực sự, trả text/plain.

### Lỗi 3: Byte[] bị chuyển thành String trước khi gửi

Dấu hiệu: file nhị phân bị hỏng, bytes 0xFF trở thành replacement characters hoặc thay đổi length. Trả byte[]/Resource không qua charset transformation.

### Lỗi 4: XML nested collections khác JSON

Dấu hiệu: XML có wrapper tags lạ hoặc parse thiếu item. Định nghĩa XML mapping annotation/schema phù hợp, test nested array, attributes và namespace. Không giả định map XML=JSON 1:1.

### Lỗi 5: Dữ liệu Unicode hỏng

Dấu hiệu: dấu tiếng Việt bị sai trong text hoặc XML. Kiểm tra Content-Type, charset, actual bytes, XML encoding declaration, shell encoding và proxy. Sử dụng UTF-8 nhất quán.

### Lỗi 6: Dùng @RequestBody Product cho raw octet-stream

Dấu hiệu: converter không có khả năng đọc Product từ application/octet-stream. Nếu payload thật là raw bytes thì nhận byte[]/Resource, sau đó business parser riêng; không gắn application/json cho raw bytes.

### Lỗi 7: GET không gửi Accept nhưng server trả định dạng không như mong đợi

Dấu hiệu: cùng endpoint đôi khi JSON, đôi khi XML giữa các client. Khi cần kiểu cụ thể, client gửi Accept rõ; server có thể quy định default representation bằng cấu hình/mapping có chủ đích.

### Lỗi 8: Đọc multipart như JSON body

Dấu hiệu: lỗi 415 hoặc JSON parser đọc boundary. Dùng @RequestPart/MultipartFile/FilePart theo stack, tách metadata JSON part khỏi file part.

### Lỗi 9: Custom converter chấp nhận mọi media type

Dấu hiệu: JSON/XML/text bị serialize sai sau khi thêm converter custom. Giới hạn canRead/canWrite/supports vào type và media type thực sự cần, giữ converters mặc định và thêm regression tests.

### Lỗi 10: XML parse resource bị lạm dụng

Dấu hiệu: XML entity/DTD gây network access, file reads hoặc CPU/memory spike. Cấu hình parser an toàn, chặn external entities và đặt quotas.

## 25. Bài tập và câu hỏi tự kiểm tra

**Câu 1.** Request body là XML, Accept là application/json. Có thể trả JSON không?

**Đáp án:** Có, nếu endpoint chấp nhận XML input, có reader để decode XML thành Java object và có writer JSON phù hợp để encode response.

**Câu 2.** Tại sao đổi produces=application/xml chưa chắc làm DTO được trả XML?

**Đáp án:** Vì còn cần converter/codec hỗ trợ kiểu Java và XML. Annotation không cài đặt thư viện serializer.

**Câu 3.** Spring MVC và WebFlux có chung HttpMessageConverter không?

**Đáp án:** Không. MVC dùng HttpMessageConverter; WebFlux dùng HttpMessageReader/Writer và Encoder/Decoder, tích hợp Reactive Streams.

**Câu 4.** Một response có Content-Type: application/pdf nhưng body là JSON string. Client có chắc mở được PDF không?

**Đáp án:** Không. Header không tạo PDF. Server phải cung cấp bytes PDF thật.

**Câu 5.** Muốn trả file ZIP 100 MB, có nên tạo byte[] lớn trong controller không?

**Đáp án:** Thường nên dùng Resource/streaming và kiểm soát I/O, memory, timeouts. byte[] giữ toàn bộ file trong heap nếu tải cả vào memory.

**Câu 6.** Tại sao StringHttpMessageConverter có thể gây nhầm khi trả String và produces=application/json?

**Đáp án:** Vì converter String có thể ghi raw text không bọc JSON string literal. Trả DTO hoặc record là cách rõ ràng cho JSON object/array.

**Câu 7.** Vì sao HTTP 415 khác HTTP 406?

**Đáp án:** 415 liên quan media type của request body không được chấp nhận; 406 liên quan response representation client yêu cầu nhưng server không cung cấp được.

**Câu 8.** XML parse thành công đã đủ để đảm bảo dữ liệu đúng nghiệp vụ chưa?

**Đáp án:** Chưa. Còn XML schema/Bean Validation, authentication/authorization và các quy tắc nghiệp vụ riêng.

**Câu 9.** Với WebFlux, thêm jackson-dataformat-xml có đảm bảo auto có JAXB XML codec không?

**Đáp án:** Không. Jackson XML extension của MVC và JAXB codecs của WebFlux là hai cơ chế khác nhau. Phải kiểm tra dependencies, DTO annotations và WebFlux codec registry thực tế.

**Câu 10.** Tại sao XML/JSON cùng URL có thể cần Vary: Accept trong HTTP cache?

**Đáp án:** Vì representation thay đổi theo Accept; nếu cache dùng một bản cho mọi Accept, client có thể nhận sai định dạng.

**Câu 11.** Khi upload file PNG bằng multipart, Content-Type top-level là gì?

**Đáp án:** Thường là multipart/form-data; phần file có thể có Content-Type image/png. Cần multipart parsing, không coi toàn bộ body là PNG bytes.

**Câu 12.** Khi đọc byte[] nhận 0x41 0x00 0xFF, có nên convert String để so sánh output không?

**Đáp án:** Không. Dùng length, checksum hoặc so sánh byte array/hex; chuyển sang String có thể làm hỏng bytes không hợp lệ với charset.

## 26. Checklist trước khi triển khai

- [ ] Xác định HTTP body đang dùng JSON, text, binary hay XML thật.
- [ ] Khai báo consumes/produces phù hợp contract, phân biệt Content-Type và Accept.
- [ ] Kiểm tra kiểu Java: DTO/record, String, byte[], Resource hoặc Mono/Flux.
- [ ] Với MVC, có HttpMessageConverter tương ứng; với WebFlux, có reader/writer/codec tương ứng.
- [ ] XML chỉ được bật khi có module/implementation và cấu hình an toàn phù hợp.
- [ ] JSON serialize bằng ObjectMapper/DTO, không tự nối chuỗi.
- [ ] Văn bản dùng encoding rõ ràng, nhất quán UTF-8 khi phù hợp.
- [ ] Binary được giữ nguyên từng byte, dùng media type chuyên biệt nếu biết file format.
- [ ] Download có Content-Disposition phù hợp và quyền truy cập được kiểm tra.
- [ ] File lớn có streaming/Resource và giới hạn memory/timeouts.
- [ ] Có test JSON/XML/text/binary, 400/406/415, XML malformed và bytes chính xác.
- [ ] Đã kiểm tra cache Vary, proxy, CORS và content sniffing khi có nhiều representations.
- [ ] Đã kiểm tra XML parser bảo vệ trước XXE/DTD/external entities và payload DoS.
- [ ] Không lộ entity/password/token qua JSON/XML serialization.
- [ ] Không tự cài @EnableWebMvc hoặc @EnableWebFlux chỉ để thêm một converter.
- [ ] Quan sát danh sách converter/codec thật trong runtime, không phỏng đoán từ annotation.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Servlet Web Applications / HttpMessageConverters](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
- [Spring Boot 3.3 — Reactive Web Applications / HTTP Codecs](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html)
- [Spring Framework 6 — HTTP Message Conversion (MVC)](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/message-converters.html)
- [Spring Framework 6.1 — MappingJackson2XmlHttpMessageConverter Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/converter/xml/MappingJackson2XmlHttpMessageConverter.html)
- [Spring Framework 6.1 — HTTP XML codecs (Jaxb2XmlDecoder/Encoder)](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/codec/xml/package-summary.html)
- [Spring Framework — WebFlux Codecs Configuration](https://docs.spring.io/spring-framework/reference/web/webflux/config.html)
- [Spring Framework — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html)
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
