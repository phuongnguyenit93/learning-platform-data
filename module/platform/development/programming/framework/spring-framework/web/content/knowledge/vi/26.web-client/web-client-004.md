# WebClient: đọc JSON, kiểu generic, dữ liệu theo luồng và multipart

## 1. Mục tiêu và mô hình tư duy

**WebClient** là HTTP client trong Spring WebFlux. Nó tạo yêu cầu HTTP, gửi và nhận dữ liệu qua các codec, sau đó trả về **Mono<T>** (0–1 giá trị) hoặc **Flux<T>** (0–n giá trị). WebClient dùng được cả trong ứng dụng Spring MVC lẫn WebFlux; việc gọi WebClient không tự biến toàn bộ ứng dụng thành reactive.

Bài này tập trung vào **phần thân (body)** của HTTP request/response:
- Đọc JSON của một đối tượng và danh sách đối tượng.
- Giữ đúng kiểu generic, kể cả cấu trúc lồng nhau như API envelope chứa một page.
- Đọc dữ liệu liên tục qua NDJSON hoặc Server-Sent Events (SSE).
- Gửi biểu mẫu multipart gồm trường văn bản, JSON và tệp; khi máy chủ trả multipart, đọc các part tương ứng.
- Nhận biết ranh giới giữa dữ liệu dạng dòng, dữ liệu cần gom toàn bộ vào bộ nhớ và vòng đời tài nguyên.

Các đoạn mã dựa trên **Java 17+, Spring Framework 6.x / Spring Boot 3.x và Project Reactor**. Những đường dẫn HTTP bắt đầu bằng /api trong bài là **hợp đồng API minh họa**: chúng chỉ thực sự hoạt động nếu hệ thống đích triển khai các endpoint cùng Content-Type và cấu trúc body đã mô tả.

### Chọn cách đọc theo hợp đồng phản hồi

| Response Content-Type và dạng body | Mục tiêu | Cách đọc thông dụng |
| --- | --- | --- |
| application/json, một object | Lấy DTO | retrieve().bodyToMono(User.class) |
| application/json, một mảng | Lấy List<User> | bodyToMono(ParameterizedTypeReference<List<User>>) |
| application/json, object bọc generic | Lấy ApiEnvelope<Page<User>> | bodyToMono(ParameterizedTypeReference<...>) |
| application/x-ndjson, mỗi dòng một JSON | Nhận nhiều phần tử theo thời gian | retrieve().bodyToFlux(User.class) |
| text/event-stream | Nhận SSE và metadata event | bodyToFlux(ParameterizedTypeReference<ServerSentEvent<User>>) |
| multipart/form-data, **request** | Gửi text, JSON và file | MultipartBodyBuilder + BodyInserters |
| multipart/mixed, **response** | Đọc tên/headers/content của từng part | Reader cho MultiValueMap<String, Part> |

**Accept** diễn đạt kiểu phản hồi client mong muốn; **Content-Type** mô tả kiểu body đang gửi. Đừng nhầm hai header. WebClient chọn codec dựa trên **kiểu Java đích** và **media type thực tế**.

## 2. Chuẩn bị dependencies và WebClient

Trong dự án Spring Boot có quản lý phiên bản dependency, thêm starter sau vào **pom.xml**:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

Starter cung cấp WebClient, Reactor và HTTP client mặc định phù hợp; Spring Boot thường tự cấu hình các codec Jackson khi Jackson có trên classpath. Nếu không dùng Spring Boot, phải tự quản lý các dependency Spring WebFlux, Reactor, HTTP connector và JSON codec tương ứng.

Tạo một client với địa chỉ gốc và giới hạn giải mã có chủ đích:

~~~java
WebClient client = WebClient.builder()
    .baseUrl("http://localhost:8080")
    .codecs(config -> config.defaultCodecs()
        .maxInMemorySize(2 * 1024 * 1024))
    .build();
~~~

**maxInMemorySize** là giới hạn bộ đệm của một số thao tác giải mã (ví dụ khi gom một giá trị JSON lớn); đây không phải giới hạn tổng kích thước mọi tệp tải lên hay dung lượng toàn stream. Trước khi tăng giới hạn, cần xác định vì sao response bị gom vào RAM.

WebClient thường được đăng ký thành bean dùng lại:

~~~java
@Configuration
class HttpClientConfig {
    @Bean
    WebClient externalClient(WebClient.Builder builder) {
        return builder.baseUrl("https://api.example.org").build();
    }
}
~~~

Hai import ở ví dụ bean là **org.springframework.context.annotation.Bean** và **org.springframework.context.annotation.Configuration**. URL example.org là địa chỉ minh họa, cần đổi theo hệ thống thật. Không tạo mới client cho từng bản ghi hay từng sự kiện.

## 3. Đọc JSON: một đối tượng, metadata HTTP và danh sách

Giả sử máy chủ có:

~~~http
GET /api/users/7
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json

{"id":7,"name":"An"}
~~~

DTO Java 17:

~~~java
public record User(long id, String name) {}
~~~

Đọc JSON thành một đối tượng:

~~~java
Mono<User> user = client.get()
    .uri("/api/users/{id}", 7)
    .accept(MediaType.APPLICATION_JSON)
    .retrieve()
    .bodyToMono(User.class);
~~~

**bodyToMono(User.class)** giải mã body theo cấu trúc DTO. **Mono<User>** chưa có giá trị ngay tại lúc khai báo; yêu cầu HTTP sẽ được thực thi khi có subscription. Với phản hồi không có body, Mono có thể hoàn thành rỗng; một JSON object và một JSON array không thể tùy tiện dùng chung cùng kiểu đích.

Nếu cần mã trạng thái và headers:

~~~java
Mono<ResponseEntity<User>> result = client.get()
    .uri("/api/users/{id}", 7)
    .retrieve()
    .toEntity(User.class);
~~~

Phải lấy status từ **ResponseEntity**, không cố đưa status thành field của User. Với các trường JSON đặt tên khác field Java, dùng cấu hình Jackson hoặc annotation **@JsonProperty** thích hợp. Nếu response là JSON động, có thể giải mã thành **JsonNode** để duyệt mà chưa cần DTO cố định, nhưng nên ưu tiên DTO khi có hợp đồng rõ ràng.

### JSON array và hai cách biểu diễn

Ví dụ body:

~~~json
[
  {"id":7,"name":"An"},
  {"id":8,"name":"Bình"}
]
~~~

Nếu muốn một collection hoàn chỉnh: dùng tham chiếu generic ở mục 4. Nếu muốn xử lý từng phần tử có khả năng được decoder phát ra trong quá trình đọc, có thể dùng:

~~~java
Flux<User> userFlux = client.get()
    .uri("/api/users")
    .accept(MediaType.APPLICATION_JSON)
    .retrieve()
    .bodyToFlux(User.class);

Mono<List<User>> allUsers = userFlux.collectList();
~~~

**collectList()** gom toàn bộ phần tử trước khi phát kết quả và có chi phí bộ nhớ tương ứng. Việc **bodyToFlux** phát một mảng JSON theo phần tử không tự chứng minh server đang truyền realtime: mạng, JSON framing và cách server flush response đều ảnh hưởng thời điểm nhận.

## 4. Đọc JSON generic đúng kiểu

Trong Java, **List.class** chỉ giữ được kiểu thô; nó không biểu diễn **List<User>**. Vì type erasure, làm như sau dễ gây ra các phần tử được giải mã thành Map thay vì User:

~~~java
// Sai kiểu đích khi muốn List<User>: mất thông tin User.
Mono<List> raw = client.get()
    .uri("/api/users")
    .retrieve()
    .bodyToMono(List.class);
~~~

Hãy giữ thông tin kiểu bằng **ParameterizedTypeReference<T>**:

~~~java
ParameterizedTypeReference<List<User>> listType =
    new ParameterizedTypeReference<List<User>>() {};

Mono<List<User>> users = client.get()
    .uri("/api/users")
    .accept(MediaType.APPLICATION_JSON)
    .retrieve()
    .bodyToMono(listType);
~~~

Dạng anonymous subclass lưu lại thông tin generic để codec Jackson biết mỗi phần tử phải thành User. Dùng một kiểu **List<User>** ở bên trái không đủ nếu tham số đưa cho bodyToMono chỉ là **List.class**.

### Generic lồng nhau: API envelope và trang dữ liệu

Giả sử API trả về:

~~~json
{
  "status": "ok",
  "data": {
    "content": [
      {"id":7,"name":"An"},
      {"id":8,"name":"Bình"}
    ],
    "totalElements": 2
  }
}
~~~

Định nghĩa các record:

~~~java
public record Page<T>(List<T> content, long totalElements) {}
public record ApiEnvelope<T>(String status, T data) {}
~~~

Giải mã đầy đủ cấu trúc:

~~~java
ParameterizedTypeReference<ApiEnvelope<Page<User>>> type =
    new ParameterizedTypeReference<ApiEnvelope<Page<User>>>() {};

Mono<ApiEnvelope<Page<User>>> page = client.get()
    .uri("/api/users/page")
    .retrieve()
    .bodyToMono(type);
~~~

Kết quả của **data().content()** là **List<User>**, không phải danh sách Map. **ParameterizedTypeReference** còn dùng được với **bodyToFlux** nếu mỗi phần tử của luồng cũng là một kiểu generic (chẳng hạn **Event<User>**).

**Phân biệt hai trường hợp:** một HTTP response có JSON array nên đọc thành List<User> hoặc Flux<User>; một response có object bao **data.content** phải đọc bằng cấu trúc envelope tương ứng. **bodyToFlux(User.class)** không tự bóc trường data.content của envelope.

## 5. Dữ liệu theo luồng: NDJSON và SSE

**Streaming** nghĩa là xử lý dần các sự kiện/phần tử khi chúng đến thay vì chờ toàn bộ response hoàn tất. Có hai định dạng phổ biến:

1. **NDJSON** (application/x-ndjson): mỗi dòng chứa một giá trị JSON độc lập. Dòng mới kết thúc một bản ghi.
2. **SSE** (text/event-stream): mỗi event được đóng khung bằng các dòng **data:**, có thể thêm **id:**, **event:** và **retry:**. Hai định dạng không tương đương.

### 5.1 Đọc NDJSON

Body minh họa, được server trả với **Content-Type: application/x-ndjson**:

~~~text
{"id":7,"name":"An"}
{"id":8,"name":"Bình"}
{"id":9,"name":"Chi"}
~~~

Client:

~~~java
Flux<User> liveUsers = client.get()
    .uri("/api/users/live")
    .accept(MediaType.APPLICATION_NDJSON)
    .retrieve()
    .bodyToFlux(User.class);

Mono<Void> firstThree = liveUsers
    .take(3)
    .doOnNext(user -> System.out.println(user.name()))
    .then();
~~~

**take(3)** chủ động ngừng sau ba phần tử và hủy subscription phía client. Đây là kỹ thuật hữu ích với luồng kéo dài; khi nguồn kết thúc sớm, có thể nhận ít hơn ba phần tử. **then()** chỉ báo hoàn tất/lỗi, không giữ lại danh sách. Trong ví dụ này chưa chạy HTTP cho đến khi một bên subscribe hoặc block ở ranh giới không-reactive.

Để xem các bản ghi trên terminal khi server đã triển khai endpoint:

~~~bash
curl -N -H "Accept: application/x-ndjson" http://localhost:8080/api/users/live
~~~

Tùy proxy/server, Content-Type đúng vẫn chưa đủ cho trải nghiệm realtime nếu tầng gửi dữ liệu giữ buffer lâu không flush.

### 5.2 Đọc SSE với payload JSON

Ví dụ raw response:

~~~text
id: 101
event: user
data: {"id":7,"name":"An"}

id: 102
event: user
data: {"id":8,"name":"Bình"}

~~~

Đọc kèm metadata:

~~~java
ParameterizedTypeReference<ServerSentEvent<User>> eventType =
    new ParameterizedTypeReference<ServerSentEvent<User>>() {};

Flux<ServerSentEvent<User>> events = client.get()
    .uri("/api/users/events")
    .accept(MediaType.TEXT_EVENT_STREAM)
    .retrieve()
    .bodyToFlux(eventType);

Flux<User> payloads = events
    .filter(event -> event.data() != null)
    .map(ServerSentEvent::data);
~~~

Nếu không cần id/event/retry, hệ thống có thể đọc từng DTO trực tiếp khi codec và payload SSE phù hợp; dùng **ServerSentEvent<User>** để không mất thông tin protocol. Đừng ép stream SSE vào **Mono<List<User>>** nếu kết nối được thiết kế không kết thúc.

Kiểm tra trực tiếp:

~~~bash
curl -N -H "Accept: text/event-stream" http://localhost:8080/api/users/events
~~~

### 5.3 Vòng đời, backpressure và lỗi ở stream

- Một **Flux** là mô tả pipeline; subscription kích hoạt network I/O. Ở controller reactive, nên **return Flux/Mono** cho framework quản lý, tránh gọi **subscribe()** tùy tiện rồi đánh mất quản lý lỗi và hủy luồng.
- **Backpressure** giúp điều tiết nhu cầu phần tử trong Reactive Streams, nhưng không bảo đảm mọi API, proxy hay HTTP peer đều áp dụng cùng tốc độ phát. Tránh downstream chậm vô hạn và các toán tử gom dữ liệu không giới hạn.
- **timeout(Duration.ofSeconds(30))** có thể dùng khi thật sự yêu cầu dữ liệu xuất hiện trong thời hạn đó, nhưng với stream nhiều khoảng nghỉ, timeout có thể coi một khoảng nghỉ hợp lệ là lỗi. Phân biệt timeout kết nối, response và timeout giữa các phần tử.
- **take(n)**, hủy subscription và chính sách retry có thể ngắt hoặc tái kết nối stream; tự xác định cách tránh xử lý trùng event khi reconnect, ví dụ dùng id SSE.
- Không gọi **collectList()** trên stream vô hạn. Không giả định response **application/json** chứa một mảng khổng lồ tự nhiên sẽ được flush theo từng phần tử.

## 6. Multipart request: gửi trường text + JSON + file

Multipart không phải một JSON object lớn. Một body **multipart/form-data** được chia thành các **part**, mỗi part có tên, headers riêng (có thể có filename/Content-Type) và dữ liệu tương ứng. Tình huống điển hình: upload file cùng metadata có cấu trúc.

Hợp đồng ví dụ:
- **POST /api/uploads**
- Part **description**: một chuỗi.
- Part **metadata**: JSON của **UploadMetadata**.
- Part **file**: binary file.
- Response thành công: **application/json**, ví dụ **{"id":"f-123"}**.

Mã gửi multipart:

~~~java
public record UploadMetadata(String source, String category) {}
public record UploadReceipt(String id) {}

Path path = Path.of("./avatar.png");

MultipartBodyBuilder parts = new MultipartBodyBuilder();
parts.part("description", "Ảnh đại diện");
parts.part("metadata", new UploadMetadata("mobile", "avatar"),
           MediaType.APPLICATION_JSON);
parts.part("file", new FileSystemResource(path), MediaType.IMAGE_PNG);

Mono<UploadReceipt> uploaded = client.post()
    .uri("/api/uploads")
    .contentType(MediaType.MULTIPART_FORM_DATA)
    .body(BodyInserters.fromMultipartData(parts.build()))
    .retrieve()
    .bodyToMono(UploadReceipt.class);
~~~

Giải thích:
- **MultipartBodyBuilder** tạo một **MultiValueMap<String, HttpEntity<?>>** có thông tin part và headers. Không tự ghép boundary hay chuỗi multipart bằng tay; framework gán boundary và mã hóa body.
- **FileSystemResource** cho codec đọc file và lấy filename. Truyền **Path**/đường dẫn như một chuỗi thông thường sẽ chỉ gửi văn bản, không gửi bytes của file.
- Metadata có **Content-Type: application/json** riêng; **Content-Type: multipart/form-data** là header của request tổng thể.
- Server có thể trả một **JSON response** cho upload multipart; khi đó **bodyToMono(UploadReceipt.class)** là đúng. Không nhầm kiểu request với kiểu response.
- File phải tồn tại và client cần quyền đọc file. Nếu server kỳ vọng tên part khác, Spring không tự đổi tên part cho đúng.

Bản cực ngắn khi chỉ gửi text và một Resource:

~~~java
Mono<String> answer = client.post()
    .uri("/api/uploads/simple")
    .body(BodyInserters.fromMultipartData("description", "Tài liệu")
        .with("file", new FileSystemResource(Path.of("./document.pdf"))))
    .retrieve()
    .bodyToMono(String.class);
~~~

Với file rất lớn hoặc part có nguồn reactive, **MultipartBodyBuilder.asyncPart(...)** cho phép đưa **Publisher** cùng kiểu phần tử vào part. Khi cần thực sự truyền multipart tuần tự, Spring còn hỗ trợ **FormPartEvent** và **FilePartEvent**. Chỉ dùng kỹ thuật nâng cao đó khi hiểu việc cấp và giải phóng **DataBuffer**; không biến toàn bộ file thành **byte[]** lớn chỉ để tiện gửi.

### Góc nhìn server để đối chiếu hợp đồng

Ví dụ controller WebFlux nhận đúng các part trên:

~~~java
@PostMapping(path = "/api/uploads",
             consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<UploadReceipt> upload(
        @RequestPart("metadata") Mono<UploadMetadata> metadata,
        @RequestPart("file") FilePart file) {
    return metadata.flatMap(info ->
        file.transferTo(Path.of("./uploads", file.filename()))
            .thenReturn(new UploadReceipt("f-123")));
}
~~~

Đây chỉ là ví dụ minh họa cách ghép API client–server; ứng dụng thực phải **kiểm tra tên tệp và đường dẫn đích**, tạo thư mục, xử lý lỗi file trùng và không dùng trực tiếp tên người dùng cung cấp để ghép đường dẫn lưu trữ. Trường **description** trong request có thể được server nhận thêm bằng **@RequestPart("description") String description** nếu cần.

## 7. Khi *response* là multipart: đọc từng part

Khác với mục 6, có API trả **Content-Type: multipart/mixed** (hoặc multipart/form-data) cho một response gồm nhiều part. Đọc body kiểu **List<User>** hay **byte[]** không giúp nhận metadata và ranh giới giữa các part. Một hướng xử lý là giải mã thành **MultiValueMap<String, Part>** qua **MultipartHttpMessageReader**. Với WebClient cần kiểm tra client codec đã có reader này chưa; có thể đăng ký reader tường minh như sau:

~~~java
WebClient multipartClient = client.mutate()
    .codecs(config -> config.customCodecs()
        .register(new MultipartHttpMessageReader(
            new DefaultPartHttpMessageReader())))
    .build();

ParameterizedTypeReference<MultiValueMap<String, Part>> multipartType =
    new ParameterizedTypeReference<MultiValueMap<String, Part>>() {};

Mono<MultiValueMap<String, Part>> response = multipartClient.get()
    .uri("/api/bundle")
    .accept(MediaType.MULTIPART_MIXED)
    .retrieve()
    .bodyToMono(multipartType);
~~~

Giả sử response có file part mang tên **file**:

~~~java
Mono<Void> saved = response.flatMap(map -> {
    Part part = map.getFirst("file");
    if (part instanceof FilePart filePart) {
        return filePart.transferTo(Path.of("./downloaded.bin"));
    }
    return Mono.error(new IllegalStateException(
        "Response không chứa file part tên 'file'"));
});
~~~

**FormFieldPart** cung cấp giá trị văn bản của form field; **FilePart** có **filename()**, **headers()** và **transferTo(Path)**. Trường hợp một tên có nhiều part, dùng **get(name)** để lấy danh sách, thay vì **getFirst(name)**. **FilePart** chứa nội dung có vòng đời tài nguyên; phải đọc, chuyển tiếp hoặc ghi file đúng cách, không giữ tham chiếu Part rồi bỏ dở luồng. Cấu hình reader ở đây giúp trình bày rõ codec cần dùng, vì mặc định các codec client giữa phiên bản/cấu hình có thể khác nhau.

Đối với phản hồi multipart rất lớn cần xử lý từng khối theo stream, có thể chọn **PartEventHttpMessageReader** / **PartEvent** phù hợp và xử lý các **DataBuffer** có kiểm soát; đọc map toàn bộ part không phải giải pháp mặc định tốt cho mọi khối lượng dữ liệu. Khác với **multipart/form-data**, **application/x-www-form-urlencoded** chỉ là cặp khóa–giá trị đơn giản, không phải file part.

## 8. Một lớp client hoàn chỉnh, nhất quán về kiểu

Mã sau tổng hợp các trường hợp chính vào một lớp. File **ReadingWithWebClient.java** thuộc package **demo**. Nó **biên dịch với dependency WebFlux được cấu hình như mục 2**; khi gọi các phương thức, hệ thống HTTP phía server phải hiện thực đúng những endpoint ví dụ. Vì kết quả phụ thuộc dữ liệu từ server nên không có stdout cố định để khẳng định trước.

~~~java
package demo;

import java.nio.file.Path;
import java.util.List;

import org.springframework.core.ParameterizedTypeReference;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.http.codec.multipart.DefaultPartHttpMessageReader;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.http.codec.multipart.MultipartHttpMessageReader;
import org.springframework.http.codec.multipart.Part;
import org.springframework.util.MultiValueMap;
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class ReadingWithWebClient {
    public record User(long id, String name) {}
    public record Page<T>(List<T> content, long totalElements) {}
    public record ApiEnvelope<T>(String status, T data) {}
    public record UploadMetadata(String source, String category) {}
    public record UploadReceipt(String id) {}

    private final WebClient client;

    public ReadingWithWebClient(String baseUrl) {
        this.client = WebClient.builder()
            .baseUrl(baseUrl)
            .build();
    }

    public Mono<User> readUser(long id) {
        return client.get()
            .uri("/api/users/{id}", id)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .bodyToMono(User.class);
    }

    public Mono<List<User>> readUserList() {
        ParameterizedTypeReference<List<User>> type =
            new ParameterizedTypeReference<List<User>>() {};
        return client.get()
            .uri("/api/users")
            .retrieve()
            .bodyToMono(type);
    }

    public Mono<ApiEnvelope<Page<User>>> readPage() {
        ParameterizedTypeReference<ApiEnvelope<Page<User>>> type =
            new ParameterizedTypeReference<ApiEnvelope<Page<User>>>() {};
        return client.get()
            .uri("/api/users/page")
            .retrieve()
            .bodyToMono(type);
    }

    public Flux<User> readNdjson() {
        return client.get()
            .uri("/api/users/live")
            .accept(MediaType.APPLICATION_NDJSON)
            .retrieve()
            .bodyToFlux(User.class);
    }

    public Flux<ServerSentEvent<User>> readSse() {
        ParameterizedTypeReference<ServerSentEvent<User>> type =
            new ParameterizedTypeReference<ServerSentEvent<User>>() {};
        return client.get()
            .uri("/api/users/events")
            .accept(MediaType.TEXT_EVENT_STREAM)
            .retrieve()
            .bodyToFlux(type);
    }

    public Mono<UploadReceipt> upload(Path sourceFile) {
        MultipartBodyBuilder parts = new MultipartBodyBuilder();
        parts.part("description", "Ảnh đại diện");
        parts.part("metadata",
            new UploadMetadata("mobile", "avatar"),
            MediaType.APPLICATION_JSON);
        parts.part("file", new FileSystemResource(sourceFile));

        return client.post()
            .uri("/api/uploads")
            .contentType(MediaType.MULTIPART_FORM_DATA)
            .body(BodyInserters.fromMultipartData(parts.build()))
            .retrieve()
            .bodyToMono(UploadReceipt.class);
    }

    public Mono<Void> downloadMultipartFile(Path destination) {
        WebClient readerClient = client.mutate()
            .codecs(config -> config.customCodecs()
                .register(new MultipartHttpMessageReader(
                    new DefaultPartHttpMessageReader())))
            .build();

        ParameterizedTypeReference<MultiValueMap<String, Part>> type =
            new ParameterizedTypeReference<MultiValueMap<String, Part>>() {};

        return readerClient.get()
            .uri("/api/bundle")
            .accept(MediaType.MULTIPART_MIXED)
            .retrieve()
            .bodyToMono(type)
            .flatMap(parts -> {
                Part part = parts.getFirst("file");
                if (part instanceof FilePart filePart) {
                    return filePart.transferTo(destination);
                }
                return Mono.error(new IllegalStateException(
                    "Thiếu file part trong response"));
            });
    }
}
~~~

**Cách sử dụng:** tạo **new ReadingWithWebClient("http://localhost:8080")**, rồi ở một thành phần reactive trả trực tiếp **readUser(7)** hoặc **readNdjson()** cho caller. Ở một điểm vào dòng lệnh hoặc test không chạy trên event-loop có thể dùng **readUser(7).block()**, nhưng không nên dùng **block()** trong handler WebFlux/reactive pipeline. Không gọi **subscribe()** rồi lập tức trả HTTP 200 cho một upload quan trọng: như vậy caller không biết upload đã hoàn tất hay lỗi.

### Theo dõi lỗi HTTP có ngữ cảnh

**retrieve()** mặc định chuyển HTTP 4xx/5xx thành **WebClientResponseException**; với nghiệp vụ cần thông báo riêng có thể đặt **onStatus** trước bodyToMono:

~~~java
Mono<User> user = client.get()
    .uri("/api/users/{id}", 7)
    .retrieve()
    .onStatus(
        status -> status.value() == 404,
        response -> Mono.just(
            new IllegalArgumentException("Không tìm thấy user 7")))
    .bodyToMono(User.class);
~~~

Khi dùng **exchangeToMono/Flux** để tự chọn cách đọc dựa trên status, phải xử lý response body ngay trong callback phù hợp; đừng để body chưa đọc rồi cố giải mã sau callback. Đặt timeout/retry theo tính chất nghiệp vụ; retry upload POST không có idempotency key có thể tạo bản ghi trùng.

## 9. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Nhận LinkedHashMap thay vì User trong danh sách | Dùng List.class, mất generic | Dùng ParameterizedTypeReference<List<User>> |
| Decode báo mismatch hoặc không lấy được phần tử | JSON root object/array khác DTO | Xem body và schema thực; DTO phải khớp JSON |
| Dữ liệu NDJSON không hiện dần | Server/proxy không flush hoặc response không phải NDJSON | Kiểm tra Content-Type, framing, curl -N và hành vi flush |
| SSE không đọc được bằng JSON codec thường | Nhầm text/event-stream với application/json | Dùng accept(TEXT_EVENT_STREAM) và ServerSentEvent<T> |
| Tăng RAM khi stream chạy lâu | collectList/cache/buffer không giới hạn | Xử lý mỗi phần tử, giới hạn/hủy rõ ràng |
| Multipart chỉ gửi đường dẫn tệp | Đưa String path thay cho file Resource | Dùng FileSystemResource hoặc dữ liệu file được encode đúng |
| HTTP 415 / 400 khi upload | Content-Type sai hoặc tên part khác hợp đồng | So request headers, boundary, part names, per-part media type |
| Cannot decode multipart response | Client chưa có multipart reader thích hợp | Đăng ký MultipartHttpMessageReader và kiểm tra kiểu Part |
| DataBufferLimitException | Decoder phải gom một giá trị quá giới hạn | Kiểm tra payload, streaming strategy và giới hạn codec |
| RuntimeException sau khi block() | 4xx/5xx, timeout hoặc lỗi giải mã | Bắt đúng loại lỗi; đọc status + body an toàn khi cần |
| Treo tài nguyên/kết nối khi xử lý part | Bỏ qua nội dung part hoặc hủy sai vòng đời | Consume/transfer/release các part và DataBuffer đúng API |

Không log tràn lan toàn bộ JSON chứa dữ liệu cá nhân hoặc binary multipart. Đối với file tải về, dùng đường dẫn đã kiểm soát và kiểm tra kích thước, định dạng, tên file theo yêu cầu ứng dụng.

## 10. Kiểm tra kiến thức qua tình huống

1. **GET /users** trả **application/json** với một mảng 100 user: muốn List<User> đầy đủ → **bodyToMono(ParameterizedTypeReference<List<User>>)**; nếu muốn xử lý từng phần tử, cân nhắc **bodyToFlux(User.class)**.
2. **GET /users/page** trả object **{"data":{"content":[...]}}**: phải có DTO envelope/page đúng schema; **bodyToFlux(User.class)** không tự đi vào field content.
3. **GET /users/live** gửi từng JSON object trên từng dòng: dùng **application/x-ndjson + bodyToFlux(User.class)**, kiểm tra server flush và tránh collectList vô hạn.
4. **GET /events** trả **text/event-stream** có event id và JSON data: dùng **ServerSentEvent<User>** để có cả metadata.
5. **POST /uploads** đòi part **file** và part **metadata** dạng JSON: dùng MultipartBodyBuilder; response thành công là JSON thì đọc **UploadReceipt**, không đọc như multipart chỉ vì request là multipart.
6. **GET /bundle** trả **multipart/mixed** gồm text và file: client cần multipart reader phù hợp; đọc **Part**, chuyển nội dung file bằng API dành cho FilePart hoặc dữ liệu reactive tương ứng.

### Checklist khi tự triển khai

- Xác nhận status, Content-Type và schema body của **response thực tế** trước khi chọn kiểu Java.
- Với generic, truyền **ParameterizedTypeReference** đến tận lời gọi bodyToMono/bodyToFlux.
- Với streaming, xác định định dạng NDJSON/SSE, ranh giới bản ghi, flush, hủy, timeout và backpressure.
- Với multipart, phân biệt chiều **gửi request** và **đọc response**; kiểm tra tên part, filename, headers, quản lý file/DataBuffer.
- Đưa Mono/Flux vào chuỗi xử lý cuối cùng và quản lý lỗi; chỉ block tại ranh giới đồng bộ có kiểm soát.

## Tài liệu tham khảo

- [Spring Framework – WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [Spring Framework – WebClient retrieve() và giải mã response](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html)
- [Spring Framework – WebClient request body và multipart](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-body.html)
- [Spring Framework – Reactive Core, codecs và multipart](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [Spring Framework – WebClient exchangeToMono/Flux](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html)
