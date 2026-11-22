# HttpMessageConverter, kiểu generic và ParameterizedTypeReference trong HTTP client đồng bộ

## 1. Học gì qua bài này?

Trong ứng dụng Spring, một lệnh HTTP không chỉ gửi/nhận bytes. Spring cần biết **kiểu dữ liệu Java đích** và **media type của HTTP body** để chọn bộ chuyển đổi từ JSON, text, byte array, XML hoặc form thành Java object. Khi API trả `List<Book>` hay `ApiEnvelope<List<Book>>`, kiểu `Class<List>` không đủ mô tả phần tử bên trong do **Java type erasure**. Vì thế, Spring cung cấp **`ParameterizedTypeReference<T>`** để giữ metadata kiểu generic tại runtime cho các APIs HTTP tương thích.

Chủ đề này nằm trong nhóm **HTTP client đồng bộ**. Trọng tâm là:

- **`RestClient`** (Spring Framework 6.1+, API fluent synchronous; lựa chọn hiện đại trong Spring 6.2/Boot 3.5).
- **`RestTemplate`** (API synchronous lâu đời, vẫn dùng nhiều trong dự án).
- **`HttpMessageConverter`**, **`GenericHttpMessageConverter`** và **`MappingJackson2HttpMessageConverter`** cho Java ↔ HTTP body.
- Khác biệt giữa `Class<T>`, `Type`, `ParameterizedTypeReference<T>`, `ResolvableType` và Jackson `TypeReference` (không phải cùng class).
- Request `Content-Type` so với `Accept`, response `Content-Type`, lỗi status, lỗi converter, DTO mapping và nested generics.
- Ví dụ **Java 17+, Spring Framework 6.2, Spring Boot 3.5** có thể kiểm thử độc lập bằng **`MockRestServiceServer`**, không gọi Internet thật.

**Kết quả kỳ vọng:** đọc JSON `[{"id":1,"title":"Spring"}]` thành **`List<Book>`** đúng kiểu; đọc `ApiEnvelope<List<Book>>` vẫn giữ kiểu `Book`; biết chẩn đoán lỗi `LinkedHashMap cannot be cast to Book`, sai media type và lỗi body serialization.

### 1.1. Phạm vi chính xác

`RestClient` và `RestTemplate` là **blocking/synchronous HTTP clients**. Converter ở đây thường đọc/ghi qua `InputStream`/`OutputStream`. **`WebClient`** là reactive client dùng `HttpMessageReader`/`HttpMessageWriter` và codecs; nó cũng có overload `ParameterizedTypeReference` nhưng **không sử dụng chính `HttpMessageConverter` synchronous theo cùng pipeline**. Đừng trộn hai cơ chế khi cấu hình.

Bài dùng ví dụ JSON vì phổ biến; `HttpMessageConverter` không đồng nghĩa “Jackson converter duy nhất”. Một request có thể đi qua String, byte array, form, XML hoặc converter tùy biến.

## 2. Cơ chế HTTP Message Conversion end-to-end

~~~text
Java request object / HttpEntity
          |
          | RestClient.body(obj) hoặc RestTemplate.exchange(...)
          v
Request headers: Content-Type / Accept
          |
          v
HttpMessageConverter.canWrite(targetType, mediaType)
          |
          v
HttpMessageConverter.write(...) -> HTTP bytes
          |
          v
Remote HTTP server
          |
          v
Status + headers + HTTP response body
          |
          v
Requested response Java type (Class<T> / Type via ParameterizedTypeReference)
          |
          v
Converter.canRead(targetType, response Content-Type)
          |
          v
Converter.read(...) -> Java value
~~~

Trong request/response đồng bộ, thread gọi phương thức `retrieve().body(...)` hoặc `exchange(...)` thường **chờ hoàn thành I/O/đọc body**. Có thể đặt thread pool, timeouts, connection pooling và concurrency budgets; không nên gọi blocking REST client trên WebFlux event-loop thread.

**Đường gửi và đường nhận độc lập:**
- **Request write**: object Java → bytes. Spring chọn converter theo **kiểu request body**, `Content-Type`, danh sách converters.
- **Response read**: bytes → object Java. Spring cần **kiểu đích** và **response `Content-Type`** để chọn converter.
- HTTP status (2xx/4xx/5xx) được giải quyết bởi client/error handler trước hoặc bên cạnh body conversion tùy API/nhánh gọi.

### 2.1. RestClient không gửi request chỉ vì gọi retrieve()

Trong Spring 6.2:

~~~java
RestClient.ResponseSpec spec = client.get()
        .uri("/books")
        .retrieve();

// Terminal operation mới thực sự đọc phản hồi:
List<Book> books = spec.body(BOOK_LIST);
~~~

Đây là snippet minh họa: `client`, `Book`, `BOOK_LIST` phải được khai báo. Spring docs nêu `retrieve()` tự nó chưa tạo side effect; phương thức terminal `body(...)`, `toEntity(...)`, `toBodilessEntity()` mới thực thi request. Không giả định response được gọi ngay sau `retrieve()`.

Với RestTemplate, lời gọi như `getForObject` hoặc `exchange` thực thi trong chính phương thức đó.

## 3. HttpMessageConverter là gì?

`org.springframework.http.converter.HttpMessageConverter<T>` là interface Spring để đọc/ghi HTTP body:

~~~java
boolean canRead(Class<?> clazz, MediaType mediaType);
boolean canWrite(Class<?> clazz, MediaType mediaType);
List<MediaType> getSupportedMediaTypes();
T read(Class<? extends T> clazz, HttpInputMessage inputMessage);
void write(T t, MediaType contentType, HttpOutputMessage outputMessage);
~~~

Đây là **chữ ký đã giản lược** nhằm minh họa, không phải source nguyên vẹn của interface trong mọi version (nullable annotations, overloads và declared exceptions được lược bỏ).

Các converter thường gặp:

| Converter | Đầu vào/đầu ra | Media type tiêu biểu | Điểm cần nhớ |
| --- | --- | --- | --- |
| `StringHttpMessageConverter` | `String` ↔ text | `text/plain`, `text/*` | Không parse JSON thành DTO dù chuỗi chứa JSON |
| `ByteArrayHttpMessageConverter` | `byte[]` ↔ bytes | `*/*`, thường ghi octet-stream | Dùng cho binary nhỏ đã có giới hạn |
| `ResourceHttpMessageConverter` | `Resource` ↔ stream/file response | Tùy resource/media type | Không coi đây là parser JSON |
| `FormHttpMessageConverter` | Form URL-encoded, ghi multipart | `application/x-www-form-urlencoded`, multipart | Multipart có nhiều parts, cần phân biệt map và file |
| `MappingJackson2HttpMessageConverter` | DTO/collection ↔ JSON | `application/json`, `application/*+json` | Dựa Jackson ObjectMapper và Type metadata |
| `MarshallingHttpMessageConverter` | XML thông qua marshaller | `application/xml`/`text/xml` | Tùy dependencies/config |
| Custom converter | Binary/protobuf/vendor media | Ví dụ `application/x-my-format` | Phải chỉ rõ canRead/canWrite và ordering |

**Không có một danh sách cố định bất biến** cho mọi ứng dụng: classpath, Spring Boot auto-configuration, client builder và custom registration quyết định converter thực tế. Cấu hình Spring MVC server-side và RestClient/RestTemplate client-side có thể khác nhau.

### 3.1. Vì sao GenericHttpMessageConverter quan trọng?

Interface base `HttpMessageConverter` nhận **`Class`**, ví dụ `Book.class` hoặc `List.class`. `Class<List>` không thể biểu diễn kiểu đầy đủ `List<Book>` vì kiểu generic bị erase ở runtime.

`GenericHttpMessageConverter<T>` mở rộng interface này để làm việc với Java reflection **`Type`**:

~~~java
boolean canRead(Type type, Class<?> contextClass, MediaType mediaType);
T read(Type type, Class<?> contextClass, HttpInputMessage inputMessage);
boolean canWrite(Type type, Class<?> clazz, MediaType mediaType);
~~~

Đây cũng là chữ ký giản lược. Nếu converter hỗ trợ generic, nó có thể nhìn thấy `List<Book>`, `Map<String, List<Book>>` hay `ApiEnvelope<List<Book>>` thay vì chỉ thấy raw `List`.

**Nhưng:** `ParameterizedTypeReference` chỉ **mang thông tin type**; nó không tự parse JSON. Cần một converter thực sự hiểu media type và generic shape, thường là Jackson JSON converter trên classpath. Nếu response là `text/html` hoặc service trả HTML error page thì một type reference đúng vẫn không thể biến HTML thành `Book`.

## 4. Content-Type, Accept và response type: ba khái niệm khác nhau

| Header/API | Nằm ở đâu | Ý nghĩa |
| --- | --- | --- |
| Request `Content-Type: application/json` | Request từ client | Bytes gửi lên đang có định dạng JSON |
| Request `Accept: application/json` | Request từ client | Client muốn nhận response kiểu JSON |
| Response `Content-Type: application/json` | Response từ server | Bytes phản hồi thực tế là JSON |
| `body(Book.class)` | Java client code | Mong parse body thành Book |
| `body(new ParameterizedTypeReference<List<Book>>() {})` | Java client code | Mong parse body thành List có phần tử Book |

**Ví dụ POST:**

~~~java
Book result = client.post()
        .uri("/books")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .body(new Book(3L, "Reactive"))
        .retrieve()
        .body(Book.class);
~~~

Đây là snippet có `client` đã cấu hình. Converter **ghi JSON** từ Book cho request, server xử lý, converter **đọc JSON** từ response trở lại Book. `Accept` không tự đặt request body `Content-Type`, và `Content-Type` của request không thể ép remote server phải trả JSON.

Khi server trả JSON nhưng khai `Content-Type: text/plain`, việc chọn converter có thể khác; đừng sửa vấn đề bằng cách ép `List.class` hay bỏ validation. Hãy sửa HTTP contract ở upstream hoặc cấu hình converter custom có chủ đích, với test đầy đủ.

## 5. Vấn đề Java type erasure và List.class

Giả sử upstream trả:

~~~json
[
  {"id": 1, "title": "Spring"},
  {"id": 2, "title": "Jackson"}
]
~~~

Bạn muốn `List<Book>` nhưng viết:

~~~java
List<?> books = client.get()
        .uri("/books")
        .retrieve()
        .body(List.class);
~~~

Jackson chỉ nhận raw `List`; các phần tử JSON object thông thường thành `LinkedHashMap`, không phải `Book`. Nếu ép:

~~~java
@SuppressWarnings("unchecked")
List<Book> wrong = (List<Book>) (List<?>) books;
Book first = wrong.get(0);  // Có thể ClassCastException
~~~

Bộ biên dịch không bảo đảm phần tử thật là Book khi generic type bị erase, nên lỗi thường chỉ xuất hiện lúc lấy/ép phần tử.

### 5.1. Vì sao không có `List<Book>.class`?

Trong Java, class literal chỉ viết được `Book.class`, `List.class`, không thể `List<Book>.class`:

~~~java
Class<Book> one = Book.class;
Class<List> many = List.class;
// Class<List<Book>> typed = List<Book>.class; // Java syntax invalid
~~~

Không phải Spring bỏ quên overload: Java không có class literal cho một **parameterized type**. Muốn giữ parameter `Book` phải truyền Java `Type` hoặc một object có thể giữ Type.

### 5.2. Trường hợp object không generic

Nếu phản hồi duy nhất là:

~~~json
{"id":1,"title":"Spring"}
~~~

thì `Book.class` là đủ:

~~~java
Book book = client.get()
        .uri("/books/1")
        .retrieve()
        .body(Book.class);
~~~

Không bắt buộc dùng `ParameterizedTypeReference<Book>` cho DTO không generic. Dùng type reference chỉ khi cần biểu diễn `List<Book>`, `Page<Book>`, `Map<String, Book>`, nested envelopes hoặc type variable đã được resolve.

## 6. ParameterizedTypeReference<T>: ghi lại Type đầy đủ

`org.springframework.core.ParameterizedTypeReference<T>` dùng dạng **anonymous subclass** để nhận thông tin generic từ superclass signature:

~~~java
ParameterizedTypeReference<List<Book>> type =
        new ParameterizedTypeReference<List<Book>>() {};
~~~

**Hai dấu ngoặc nhọn `{}` ở cuối là quan trọng**: bạn đang tạo một anonymous subclass mà superclass mang type parameter `List<Book>`; Spring dùng reflection để nắm bắt kiểu đích.

Sau đó RestClient:

~~~java
List<Book> books = client.get()
        .uri("/books")
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .body(type);
~~~

Hoặc lấy status, headers và body:

~~~java
ResponseEntity<List<Book>> response = client.get()
        .uri("/books")
        .retrieve()
        .toEntity(type);

HttpStatusCode status = response.getStatusCode();
List<Book> list = response.getBody();
~~~

`ResponseEntity.getBody()` có thể trả **null** khi body không tồn tại hoặc contract cho phép, nên đừng dereference `response.getBody().size()` nếu không có null policy. `retrieve().body(type)` cũng có thể trả null trong một số trường hợp 204/empty body.

### 6.1. Nested generic

Một API dùng envelope:

~~~json
{
  "data": [
    {"id":1,"title":"Spring"},
    {"id":2,"title":"Jackson"}
  ],
  "traceId": "rid-42"
}
~~~

Với DTO:

~~~java
public record ApiEnvelope<T>(T data, String traceId) {}
~~~

Type phải giữ được **cả hai lớp generic**:

~~~java
ParameterizedTypeReference<ApiEnvelope<List<Book>>> type =
        new ParameterizedTypeReference<ApiEnvelope<List<Book>>>() {};

ApiEnvelope<List<Book>> envelope = client.get()
        .uri("/books/envelope")
        .retrieve()
        .body(type);
~~~

Nếu chỉ truyền `ApiEnvelope.class`, Jackson có thể giải mã `data` thành raw `List<LinkedHashMap>`, làm mất tầng `Book`.

### 6.2. Generic không chỉ là List

Ví dụ:

~~~java
ParameterizedTypeReference<Map<String, List<Book>>> mapType =
        new ParameterizedTypeReference<Map<String, List<Book>>>() {};

ParameterizedTypeReference<List<ApiEnvelope<Book>>> listEnvelopeType =
        new ParameterizedTypeReference<List<ApiEnvelope<Book>>>() {};
~~~

Lưu ý `Map<String, List<Book>>` cần JSON object có property names ứng với String keys, còn `List<ApiEnvelope<Book>>` cần JSON array mà mỗi phần tử có cấu trúc ApiEnvelope. **Metadata type đúng không bù cho JSON shape sai**.

### 6.3. Không capture type variable chưa resolve như một kiểu cụ thể

Anti-pattern trong utility generic:

~~~java
public <T> T fetch(String path) {
    ParameterizedTypeReference<T> type =
            new ParameterizedTypeReference<T>() {};
    return client.get().uri(path).retrieve().body(type);
}
~~~

Đây là method minh họa nằm trong một class có `RestClient client`. `T` là **type variable** bị erase, nên anonymous subclass ở đây không thể biết caller muốn `List<Book>` hay `ApiEnvelope<Book>` thực sự. Không nên tin rằng `T` sẽ tự được suy ra đầy đủ tại runtime.

Cách đúng là caller cung cấp **type token đã resolve**:

~~~java
public <T> T fetch(String path, ParameterizedTypeReference<T> type) {
    return client.get().uri(path).retrieve().body(type);
}
~~~

Khi gọi:

~~~java
List<Book> books = fetch(
        "/books", new ParameterizedTypeReference<List<Book>>() {});
~~~

Hoặc nếu cần runtime composition, sử dụng `ParameterizedTypeReference.forType(Type)` với Java reflection Type được xây chính xác. Không tự tạo `List<T>` trên type variable chưa được resolve.

### 6.4. `Type` và `ParameterizedTypeReference.forType`

Khi một thư viện đã tạo `java.lang.reflect.Type` từ method generic thật, bạn có thể bridge:

~~~java
Type type = SomeApi.class
        .getDeclaredMethod("listBooks")
        .getGenericReturnType();

ParameterizedTypeReference<?> ref =
        ParameterizedTypeReference.forType(type);
~~~

Đây là **snippet minh họa**; `SomeApi` phải có method phù hợp và phải xử lý `NoSuchMethodException`. Nếu `listBooks` trả `List<Book>` thật, reflection Type chứa type đó. Nếu method trả type variable `T` mà chưa được resolve trong context, `forType` không thể tự đoán Book.

Spring còn có `ResolvableType` để phân tích generic type hierarchies và kết hợp Type metadata. Nó không phải JSON decoder.

## 7. RestClient: lời gọi typed response

`RestClient` được thêm từ Spring Framework 6.1, vì vậy ví dụ áp dụng trực tiếp với **Spring Framework 6.2 / Spring Boot 3.5**; không giả định tương thích Spring Boot 3.0 (Spring Framework 6.0).

Tạo client:

~~~java
RestClient client = RestClient.builder()
        .baseUrl("https://api.example.com")
        .defaultHeader("X-App", "demo")
        .build();
~~~

`api.example.com` là hostname ví dụ, không có service thật. `RestClient` sau khi build có thể tái sử dụng giữa threads; không tạo một client mới cho mỗi request nếu cần connection pooling/consistent configuration.

**Gọi GET với generic:**

~~~java
ParameterizedTypeReference<List<Book>> type =
        new ParameterizedTypeReference<>() {};

List<Book> books = client.get()
        .uri("/books")
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .body(type);
~~~

**Lấy response entity:**

~~~java
ResponseEntity<List<Book>> entity = client.get()
        .uri("/books")
        .retrieve()
        .toEntity(type);
~~~

**Gọi POST body DTO:**

~~~java
Book created = client.post()
        .uri("/books")
        .contentType(MediaType.APPLICATION_JSON)
        .body(new Book(3L, "REST"))
        .retrieve()
        .body(Book.class);
~~~

**Nếu endpoint không trả body:**

~~~java
ResponseEntity<Void> response = client.delete()
        .uri("/books/{id}", 3)
        .retrieve()
        .toBodilessEntity();
~~~

Đừng gọi `body(Void.class)` rồi giả định sẽ nhận một `Void` instance. `toBodilessEntity()` rõ nghĩa hơn nếu chỉ cần status/headers.

### 7.1. RestClient retrieve() và exchange() không giống nhau

- `retrieve()` dùng các thao tác terminal để giải mã theo converter, kèm status handlers phù hợp. Theo mặc định, các status 4xx/5xx có thể dẫn tới `RestClientResponseException` trước khi business xử lý body thành DTO thành công.
- `exchange((request, response) -> ...)` cung cấp mức thao tác thấp hơn với HTTP response và streams, phù hợp xử lý response custom/streaming/advanced. Khi dùng low-level exchange callback, **default status handlers của retrieve không tự áp dụng theo cùng cách**; caller phải chủ động kiểm tra status/error/cleanup.
- Chỉ `retrieve()` chưa gửi request; `body(...)`, `toEntity(...)`, `toBodilessEntity()` là terminal.

Ví dụ chặn lỗi domain theo status khi dùng retrieve:

~~~java
Book book = client.get().uri("/books/{id}", 99)
        .retrieve()
        .onStatus(status -> status.value() == 404,
                (request, response) -> {
                    throw new IllegalArgumentException("Book not found");
                })
        .body(Book.class);
~~~

Đoạn minh họa dùng client sẵn có. Trong production nên dùng exception/domain policy có HTTP status, request ID và retry rules rõ ràng; không nuốt status 500 rồi chuyển sang empty Book.

## 8. RestTemplate: sử dụng exchange với ParameterizedTypeReference

Dự án cũ thường viết:

~~~java
RestTemplate template = new RestTemplate();
Book book = template.getForObject(
        "https://api.example.com/books/1", Book.class);
~~~

Với generic, `getForObject(url, List.class)` **không mang `Book`**, nên dùng `exchange`:

~~~java
ParameterizedTypeReference<List<Book>> type =
        new ParameterizedTypeReference<>() {};

ResponseEntity<List<Book>> response = template.exchange(
        "https://api.example.com/books",
        HttpMethod.GET,
        null,
        type
);

List<Book> books = response.getBody();
~~~

`RestTemplate.exchange(..., HttpMethod, HttpEntity<?>, ParameterizedTypeReference<T>)` giữ `List<Book>` khi converter hỗ trợ generic. Không có overload `getForObject(url, ParameterizedTypeReference)` giống hệt; chọn đúng API.

Nếu cần request header:

~~~java
HttpHeaders headers = new HttpHeaders();
headers.setAccept(List.of(MediaType.APPLICATION_JSON));
HttpEntity<Void> request = new HttpEntity<>(headers);

ResponseEntity<List<Book>> response = template.exchange(
        "https://api.example.com/books",
        HttpMethod.GET,
        request,
        type
);
~~~

Nếu có request body generic, có thể dùng `RequestEntity` hoặc `HttpEntity<T>`, các overload phù hợp; xem **cả hướng serialize** (request) và deserialize (response).

### 8.1. RestTemplate không “sai”, RestClient không tự “nhanh hơn”

Cả hai là synchronous HTTP clients; RestClient là API fluent mới hơn, RestTemplate có ecosystem rộng và code chạy ổn định. Việc đổi syntax từ RestTemplate sang RestClient **không tự loại bỏ blocking I/O**. Hãy đo latency, request factory, connection pool, retry policy và network trước khi tuyên bố cải thiện hiệu năng.

Dùng `WebClient` khi thật sự cần reactive composition, nhưng không block result trên Reactor event loop. `ParameterizedTypeReference` cũng xuất hiện trong `WebClient.bodyToMono(type)`/`bodyToFlux(type)` nhưng implementation conversion khác.

## 9. RestClient và RestTemplate chọn converter bằng cách nào?

Với response JSON `application/json` và đích `ApiEnvelope<List<Book>>`, client duyệt cấu hình converters để chọn converter có thể đọc kiểu/media type cần thiết. Converter Jackson generic có thể dùng Type đầy đủ để tạo `ApiEnvelope`, `List` và `Book`. Nếu không có Jackson dependency hoặc converter bị xóa khỏi list, parse có thể thất bại dù TypeReference đúng.

Ngược lại, nếu response có `text/plain` và bạn gọi `body(String.class)`, String converter có thể xử lý, không cần Jackson.

### 9.1. Cách kiểm tra converter thực có sẵn

~~~java
RestTemplate template = new RestTemplate();
template.getMessageConverters()
        .forEach(c ->
            System.out.println(c.getClass().getSimpleName()));
~~~

Đây là snippet chạy được trong class Java với imports phù hợp và Spring Web dependencies. Danh sách in ra tùy classpath Spring version; **không gán một stdout cố định**. Khi RestClient được cấu hình thông qua builder, có thể cấu hình list converters bằng callback:

~~~java
RestClient configured = RestClient.builder()
        .messageConverters(converters -> {
            // Quan sát/thay đổi list có chủ đích.
            converters.forEach(c ->
                    System.out.println(c.getClass().getName()));
        })
        .build();
~~~

**Không xóa các converter mặc định mù quáng.** Nếu bạn gọi `converters.clear()` rồi chỉ đăng ký `StringHttpMessageConverter`, kết quả JSON DTO sẽ không được đọc/ghi như trước.

### 9.2. Thứ tự converter và media type

Một custom converter quá rộng (ví dụ `canRead(..., */*)` cho Object) được thêm trước Jackson có thể chặn Jackson và khiến body bị parse sai. Đăng ký media type chính xác, chỉ các classes converter biết xử lý, kiểm thử serialize + deserialize, status + headers. Tránh override `supportedMediaTypes` của Jackson thành `*/*` để “sửa lỗi” upstream gửi sai Content-Type, vì dễ vô tình đọc HTML/error page như JSON và làm giảm khả năng chẩn đoán.

### 9.3. Boot auto-configuration

Spring Boot 3.x có thể cung cấp cấu hình builder, ObjectMapper và customizers theo starters. Nếu dùng **`RestClient.builder()` trực tiếp**, bạn có thể **bỏ qua một số customization** của Boot mà bean `RestClient.Builder` được Boot cấu hình sẵn.

Trong Boot 3.5, pattern:

~~~java
@Configuration
class ClientConfiguration {

    @Bean
    CatalogClient catalogClient(RestClient.Builder builder) {
        RestClient rest = builder
                .baseUrl("https://api.example.com")
                .build();
        return new CatalogClient(rest);
    }
}
~~~

Đây là class minh họa, `CatalogClient` sẽ được định nghĩa ở phần thực hành; URL ví dụ cần thay bằng endpoint tin cậy/cấu hình ở production. Nếu có nhiều RestClient, dùng builder clone/configuration một cách có kiểm soát, không mutate shared builder sau build trong luồng xử lý đồng thời.

## 10. Jackson ObjectMapper và ParameterizedTypeReference: khác nhau thế nào?

**Hai giải pháp khác API layer:**

| Khái niệm | Đơn vị | Mục đích |
| --- | --- | --- |
| `Class<Book>` | Java reflection | Một concrete class |
| `Type`/`ParameterizedType` | Java reflection | Mô tả `List<Book>`, nested generics |
| `ParameterizedTypeReference<T>` | Spring Core | Giữ `Type` qua APIs Spring generic |
| `ResolvableType` | Spring Core | Phân giải/phân tích generics |
| `TypeReference<T>` | Jackson | Giữ generic metadata cho `ObjectMapper.readValue` |
| `JavaType` | Jackson | Mô hình kiểu của Jackson cho deserialization |
| `HttpMessageConverter` | Spring Web | Biến HTTP bytes ↔ Java object |
| `ObjectMapper` | Jackson | JSON ↔ Java object |

Nếu bạn chỉ có JSON string/byte array và tự dùng Jackson:

~~~java
ObjectMapper mapper = new ObjectMapper();

List<Book> books = mapper.readValue(
        json,
        new com.fasterxml.jackson.core.type.TypeReference<List<Book>>() {});
~~~

Đây là snippet với `String json` đã có; khác namespace và use case với Spring `ParameterizedTypeReference`. Khi dùng RestClient/RestTemplate, thông thường **không cần tự `ObjectMapper.readValue`**: để converter xử lý content-type, headers và TypeToken.

Nếu phải chuyển qua JavaType:

~~~java
JavaType type = mapper.getTypeFactory()
        .constructCollectionType(List.class, Book.class);

List<Book> books = mapper.readValue(json, type);
~~~

Đây là ví dụ Jackson thuần ngoài request client abstraction. Trong hệ thống lớn, giữ một `ObjectMapper` đã cấu hình nhất quán cho Java time, naming, modules, date format và polymorphic type restrictions; không tạo Mapper mới cho từng request nếu không cần.

## 11. Thực hành chạy được: Java 17 + Spring Boot 3.5

Bài tập tập trung **synchronous HTTP client**, không cần khởi động REST server thật. `MockRestServiceServer` sẽ đáp ứng những requests được `RestClient` và `RestTemplate` gửi qua mock `ClientHttpRequestFactory`. Nhờ đó có thể test converter/type reference chính xác, không phụ thuộc mạng, token, hostname hay external API.

Dùng **Spring Boot 3.5.x / Spring Framework 6.2.x** và Java 17+, package `com.example.demo`.

### 11.1. Dependencies

Tạo Maven project qua Spring Initializr (Spring Boot 3.5.x, Java 17), chọn:
- Spring Web (để có Spring Web, RestClient/RestTemplate, Jackson JSON).
- Spring Boot Starter Test (JUnit Jupiter, Spring Test/MockRestServiceServer).

Trong file `pom.xml` do Spring Initializr sinh sẵn, phần dependencies có dạng:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Đây là **một phần** của `pom.xml`, không phải file Maven độc lập. Spring Initializr chịu trách nhiệm parent, Java version, Maven plugins và version management. `spring-boot-starter-web` trong demo bao gồm khả năng chạy Servlet HTTP server nếu cần, nhưng test ở đây dùng **mock outgoing HTTP client**, không cần server lắng nghe socket.

Cấu trúc:

~~~text
src/main/java/com/example/demo/
    DemoApplication.java
    Book.java
    ApiEnvelope.java
    CatalogClient.java
src/test/java/com/example/demo/
    CatalogClientTest.java
    RestTemplateGenericTest.java
~~~

### 11.2. DemoApplication.java

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Ứng dụng Boot này có thể khởi động bằng `./mvnw spring-boot:run`. Tuy nhiên, **các unit/integration-style client tests không cần chạy DemoApplication**; tạo RestClient và MockRestServiceServer trực tiếp để chỉ kiểm thử bài toán converter.

### 11.3. Book.java

~~~java
package com.example.demo;

public record Book(long id, String title) {}
~~~

Jackson 2.x tích hợp trong Spring Boot 3.5 xử lý Java records chuẩn theo constructors/components, khi JSON keys khớp `id` và `title`.

### 11.4. ApiEnvelope.java

~~~java
package com.example.demo;

public record ApiEnvelope<T>(T data, String traceId) {}
~~~

`T` có thể là `Book`, `List<Book>` hoặc kiểu khác. JSON field `traceId` minh họa metadata response, **không** phải phần của Java generic mechanism.

### 11.5. CatalogClient.java — RestClient dùng type token đúng

~~~java
package com.example.demo;

import java.util.List;

import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.RestClient;

public final class CatalogClient {

    private static final ParameterizedTypeReference<List<Book>>
            BOOK_LIST = new ParameterizedTypeReference<>() {};

    private static final ParameterizedTypeReference<
            ApiEnvelope<List<Book>>> ENVELOPE =
            new ParameterizedTypeReference<>() {};

    private final RestClient client;

    public CatalogClient(RestClient client) {
        this.client = client;
    }

    public Book findOne(long id) {
        return client.get()
                .uri("/books/{id}", id)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .body(Book.class);
    }

    public List<Book> findAll() {
        return client.get()
                .uri("/books")
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .body(BOOK_LIST);
    }

    public ResponseEntity<List<Book>> findAllWithMetadata() {
        return client.get()
                .uri("/books")
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .toEntity(BOOK_LIST);
    }

    public ApiEnvelope<List<Book>> findEnvelope() {
        return client.get()
                .uri("/books/envelope")
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .body(ENVELOPE);
    }

    public Book create(Book book) {
        return client.post()
                .uri("/books")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .body(book)
                .retrieve()
                .body(Book.class);
    }
}
~~~

Điểm chính:

1. `BOOK_LIST` và `ENVELOPE` là type references **tĩnh, immutable, có type đã resolve**. Tái sử dụng mà không phải tạo anonymous subclass ở mỗi HTTP call.
2. `findOne` dùng `Book.class` vì không có generic.
3. `findAll` dùng `List<Book>` và `findEnvelope` dùng nested `ApiEnvelope<List<Book>>`, tránh `LinkedHashMap`.
4. `findAllWithMetadata` giữ HTTP status/headers trong ResponseEntity; vẫn có thể trả body null theo contract.
5. `create` phải set request `Content-Type` để converter serialize Book sang JSON; `Accept` chỉ mô tả response mong đợi.
6. Caller phải xác định policy khi null body, 404/500, timeout, retries và malformed JSON. Demo không tự retry vì GET/POST có idempotency khác nhau.
7. **RestClient là blocking**, không gọi từ event loop WebFlux nếu không offload.
8. Không có external URL trong class; baseUrl được gắn trong test, nên test deterministic.

### 11.6. CatalogClientTest.java — MockRestServiceServer kiểm thử đúng kiểu

~~~java
package com.example.demo;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class CatalogClientTest {

    MockRestServiceServer server;
    CatalogClient catalog;

    @BeforeEach
    void setup() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("https://catalog.test");

        server = MockRestServiceServer.bindTo(builder).build();
        catalog = new CatalogClient(builder.build());
    }

    @Test
    void singleDtoUsesClass() {
        server.expect(requestTo("https://catalog.test/books/1"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        """
                        {"id":1,"title":"Spring"}
                        """,
                        MediaType.APPLICATION_JSON));

        Book book = catalog.findOne(1);
        assertNotNull(book);
        assertEquals(1, book.id());
        assertEquals("Spring", book.title());
        server.verify();
    }

    @Test
    void genericListKeepsBookElementType() {
        server.expect(requestTo("https://catalog.test/books"))
                .andRespond(withSuccess(
                        """
                        [{"id":1,"title":"Spring"},
                         {"id":2,"title":"Jackson"}]
                        """,
                        MediaType.APPLICATION_JSON));

        List<Book> books = catalog.findAll();

        assertNotNull(books);
        assertEquals(2, books.size());
        assertEquals(Book.class, books.get(0).getClass());
        assertEquals("Jackson", books.get(1).title());
        server.verify();
    }

    @Test
    void nestedGenericEnvelopeKeepsBookType() {
        server.expect(
                requestTo("https://catalog.test/books/envelope"))
                .andRespond(withSuccess(
                        """
                        {"data":[{"id":7,"title":"Generic"}],
                         "traceId":"rid-42"}
                        """,
                        MediaType.APPLICATION_JSON));

        ApiEnvelope<List<Book>> envelope = catalog.findEnvelope();

        assertNotNull(envelope);
        assertEquals("rid-42", envelope.traceId());
        assertEquals(Book.class, envelope.data().get(0).getClass());
        assertEquals("Generic", envelope.data().get(0).title());
        server.verify();
    }

    @Test
    void responseEntityHasStatusAndTypedBody() {
        server.expect(requestTo("https://catalog.test/books"))
                .andRespond(withSuccess(
                        """
                        [{"id":1,"title":"Spring"}]
                        """,
                        MediaType.APPLICATION_JSON));

        ResponseEntity<List<Book>> response =
                catalog.findAllWithMetadata();

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals(Book.class,
                response.getBody().get(0).getClass());
        server.verify();
    }

    @Test
    void postSerializesRequestAndDeserializesResponse() {
        server.expect(requestTo("https://catalog.test/books"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(content().contentType(
                        MediaType.APPLICATION_JSON))
                .andExpect(content().json(
                        """
                        {"id":3,"title":"REST"}
                        """))
                .andRespond(withSuccess(
                        """
                        {"id":3,"title":"REST"}
                        """,
                        MediaType.APPLICATION_JSON));

        Book created = catalog.create(new Book(3, "REST"));

        assertEquals("REST", created.title());
        assertEquals(3, created.id());
        server.verify();
    }

    @Test
    void http404IsNotAnEmptyBook() {
        server.expect(requestTo("https://catalog.test/books/99"))
                .andRespond(withStatus(HttpStatus.NOT_FOUND)
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(
                            """
                            {"message":"not found"}
                            """));

        assertThrows(RestClientResponseException.class,
                () -> catalog.findOne(99));
        server.verify();
    }
}
~~~

**Vì sao test này chứng minh đúng bài?**

- Không gọi `https://catalog.test` qua DNS: `MockRestServiceServer.bindTo(builder)` **gắn mock request factory trước khi `builder.build()`**. Nếu build RestClient trước rồi mới bind, test có thể không sử dụng factory vừa cấu hình.
- Test list kiểm tra **runtime class của phần tử** bằng `Book.class`, không chỉ size hoặc string.
- Test nested generic kiểm tra Book nằm **bên trong** `ApiEnvelope<List<Book>>`.
- Test POST kiểm tra cả **outgoing request `Content-Type` + JSON** và incoming JSON DTO.
- Test HTTP 404 xác minh lỗi status không bị nuốt thành “Book rỗng”.
- `server.verify()` yêu cầu các expected mock HTTP requests được thực hiện.
- JUnit test không phải benchmark performance hay end-to-end API integration thật; nó kiểm tra client conversion code/URI/status bằng mock.
- Các import thừa (nếu IDE báo warning) có thể dọn bằng formatter; với Java compiler bình thường chúng không ngăn biên dịch.

### 11.7. RestTemplateGenericTest.java — tương đương API cũ

~~~java
package com.example.demo;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class RestTemplateGenericTest {

    @Test
    void exchangeWithParameterizedTypeReference() {
        RestTemplate template = new RestTemplate();
        MockRestServiceServer server =
                MockRestServiceServer.bindTo(template).build();

        server.expect(requestTo("https://catalog.test/books"))
                .andRespond(withSuccess(
                        """
                        [{"id":1,"title":"Spring"}]
                        """,
                        MediaType.APPLICATION_JSON));

        ParameterizedTypeReference<List<Book>> type =
                new ParameterizedTypeReference<>() {};

        ResponseEntity<List<Book>> result = template.exchange(
                "https://catalog.test/books",
                HttpMethod.GET,
                null,
                type);

        assertNotNull(result.getBody());
        assertEquals(Book.class,
                result.getBody().get(0).getClass());
        server.verify();
    }
}
~~~

Test cho thấy cả hai synchronous HTTP clients **đều** hỗ trợ đọc generic types khi dùng đúng API và converter.

### 11.8. Chạy kiểm thử

Trong project Maven:

~~~bash
./mvnw test
~~~

Trên Windows PowerShell:

~~~powershell
.\mvnw.cmd test
~~~

Nếu thiếu Maven Wrapper nhưng Maven đã cài: `mvn test`.

Kết quả **mong đợi nếu dependencies/config đã khớp và tests chạy thành công**: 7 tests pass (6 `CatalogClientTest`, 1 `RestTemplateGenericTest`), không có network call bên ngoài. Nếu bạn thêm test class khác hoặc thay version/dependencies thì tổng test count có thể khác. Đừng bịa rằng những tests này đã chạy nếu chưa thực sự chạy trên một project.

Có thể khởi động Boot app:

~~~bash
./mvnw spring-boot:run
~~~

App chỉ là skeleton Spring Boot, **không expose endpoint `/books`** và không thực hiện HTTP requests tự động. Các tests dùng mock server mới cung cấp responses để bảo đảm bài tập độc lập.

## 12. Chẩn đoán lỗi generic sai bằng một test nhỏ

Để thấy `List.class` làm mất kiểu:

~~~java
Object raw = new ObjectMapper().readValue(
        """
        [{"id":1,"title":"Spring"}]
        """,
        List.class);

List<?> list = (List<?>) raw;

System.out.println(list.get(0).getClass().getName());
~~~

Nếu Jackson 2.x mặc định và JSON là array các object như trên, stdout sẽ là:

~~~text
java.util.LinkedHashMap
~~~

Snippet Java cần import `ObjectMapper` và `List`; có thể chạy bằng một method trong project chứa Jackson. Đây là **một thử nghiệm local Jackson**, không cần HTTP, vì lỗi bắt nguồn từ raw generic type chứ không phải từ network.

Dùng đúng type token:

~~~java
List<Book> typed = new ObjectMapper().readValue(
        """
        [{"id":1,"title":"Spring"}]
        """,
        new com.fasterxml.jackson.core.type.TypeReference<List<Book>>() {});
System.out.println(typed.get(0).getClass().getName());
~~~

Kết quả dự kiến:

~~~text
com.example.demo.Book
~~~

Đối với RestClient/RestTemplate, dùng **Spring ParameterizedTypeReference** thay vì Jackson TypeReference, để client chuyển đầy đủ `java.lang.reflect.Type` tới `HttpMessageConverter`.

## 13. Request body có generic: lúc nào cần type token?

Khi **response** là `List<Book>`, type token là điểm mấu chốt để deserializer tạo đúng object elements. Với **request**, generic payload cũng có thể quan trọng khi converter quyết định serialization dựa trên generic type hoặc các type annotations.

Ví dụ request body list:

~~~java
List<Book> books = List.of(
        new Book(1, "Spring"),
        new Book(2, "Jackson"));

ResponseEntity<Void> response = client.post()
        .uri("/books/import")
        .contentType(MediaType.APPLICATION_JSON)
        .body(books)
        .retrieve()
        .toBodilessEntity();
~~~

Jackson thường có thể serialize List<Book> đúng dựa vào các **runtime values** của phần tử. Nhưng với container generic phức tạp, polymorphism, empty collection, type-dependent custom serializers hoặc generic envelope, có thể cần chỉ rõ generic type thay vì dựa vào raw runtime class.

Spring RestClient còn có overload `body(Object, ParameterizedTypeReference)` trên request body ở Spring 6.2. Cấu trúc minh họa:

~~~java
ParameterizedTypeReference<List<Book>> type =
        new ParameterizedTypeReference<>() {};

client.post()
        .uri("/books/import")
        .contentType(MediaType.APPLICATION_JSON)
        .body(books, type)
        .retrieve()
        .toBodilessEntity();
~~~

Đoạn cần `RestClient client` đã cấu hình. Type token không đảm bảo remote API chấp nhận JSON đó; vẫn cần schema/validation/status tests.

## 14. MediaType và lỗi converter hay gặp

### 14.1. Server trả Content-Type sai

Server trả:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html

<html>upstream error</html>
~~~

Caller lại:

~~~java
Book book = client.get().uri("/books/1")
        .retrieve().body(Book.class);
~~~

Sẽ không tự có một Book hợp lệ. Spring có thể báo không tìm được converter phù hợp hoặc lỗi decoding khác theo pipeline/version. Hãy log **status, content type, request ID, endpoint** một cách an toàn và sửa upstream contract.

### 14.2. Raw List → LinkedHashMap

Dấu hiệu:

~~~text
java.lang.ClassCastException:
java.util.LinkedHashMap cannot be cast to com.example.demo.Book
~~~

Giải pháp: dùng `ParameterizedTypeReference<List<Book>>` trong `RestTemplate.exchange` hoặc `RestClient.retrieve().body(type)`. Đừng ép unchecked cast hoặc dùng vòng lặp cast trực tiếp Map sang Book.

### 14.3. JSON không khớp DTO

~~~json
{"identifier":1,"name":"Spring"}
~~~

Nhưng DTO cần:

~~~java
public record Book(long id, String title) {}
~~~

Cần map đúng schema, dùng `@JsonProperty` khi cần hoặc cập nhật DTO. Type reference không tự rename fields. Nếu kiểu số vượt range, JSON sai, field bắt buộc thiếu hoặc enum lạ, ObjectMapper/validation vẫn có thể thất bại hay đặt defaults tùy cấu hình.

### 14.4. Không có Jackson trên classpath

Nếu project chỉ có spring-web nhưng không có JSON converter/Jackson, `body(Book.class)` cho JSON có thể không được hỗ trợ theo cách bạn kỳ vọng. Với Spring Boot MVC starter, Jackson thường đi kèm; nếu dùng dependencies thủ công, cần bổ sung và đăng ký converter.

### 14.5. Generic TypeReference sai tầng

Một response `ApiEnvelope<List<Book>>` không thể đọc đúng bằng:

~~~java
new ParameterizedTypeReference<List<Book>>() {}
~~~

vì root JSON là object có `data`, không phải array. Dùng TypeReference **khớp root schema**. Tương tự, `ApiEnvelope<Book>` khác `ApiEnvelope<List<Book>>` ở field data.

### 14.6. 204 No Content

Một response status **204** không có body. `body(Book.class)` không thể “tự tạo Book rỗng”; phải xử lý null/ResponseEntity hoặc dùng `toBodilessEntity()` cho endpoint có contract trả body rỗng.

### 14.7. Error responses không nhất thiết đi qua success DTO converter

Nếu upstream trả status 400 kèm problem JSON, mặc định `retrieve()` có thể ném `RestClientResponseException`. Đừng nghĩ `body(Book.class)` parse được Book từ error body. Cần `onStatus`, `RestClientResponseException`, hoặc API error deserialization phù hợp.

### 14.8. 415 và 406 không phải lúc nào cũng do client-side parser

- **415 Unsupported Media Type** thường xảy ra server không chấp nhận `Content-Type` request/body.
- **406 Not Acceptable** thường xảy ra server không thể sản xuất representation phù hợp với request `Accept`.
- **Client-side converter/decoding error** xảy ra khi client không thể đọc body theo media type/target type, ngay cả status 200.

Phân biệt lỗi ở **bên nào**. Không chữa 415 bằng tăng timeout hoặc chữa 406 bằng đổi `List<Book>` thành `List.class`.

## 15. Cấu hình custom HttpMessageConverter: khi nào nên và không nên?

Nếu API dùng binary/proprietary media type, bạn có thể triển khai converter mới. Nhưng đa số JSON APIs nên dùng Jackson converter sẵn có và tùy chỉnh `ObjectMapper` hợp lý.

Pseudo-pattern minh họa:

~~~java
RestClient custom = RestClient.builder()
        .messageConverters(list -> {
            list.add(0, myConverter);
        })
        .build();
~~~

`myConverter` là instance thật đã implement `HttpMessageConverter<T>`, và phải có media-type class matching chính xác. Không nên đưa custom converter `canRead(Object.class, */*)` trước Jackson.

Nếu muốn custom generic converter, cân nhắc `GenericHttpMessageConverter<T>` hoặc base class phù hợp; xử lý `Type` cùng Jackson/Gson library thay vì **không parse generic element type**.

### 15.1. Cấu hình JSON theo ObjectMapper

Ví dụ minh họa với Jackson:

~~~java
ObjectMapper mapper = new ObjectMapper()
        .findAndRegisterModules();

MappingJackson2HttpMessageConverter converter =
        new MappingJackson2HttpMessageConverter(mapper);
~~~

Đây là snippet trong code có Jackson dependencies/imports. Tạo `ObjectMapper` mới tùy tiện có thể **mất config của Boot**: Java time settings, naming strategies, property inclusion, unknown fields policies, custom serializers, security restrictions. Khi ở Spring Boot, ưu tiên dùng `ObjectMapper` bean đã được Boot customize hoặc `Jackson2ObjectMapperBuilder`/customizer thích hợp.

Nếu dùng `@JsonTypeInfo`/polymorphic deserialization, cần kiểm soát trusted subtypes và tránh cấu hình Jackson default typing rộng cho dữ liệu không tin cậy. `ParameterizedTypeReference` không là cơ chế bảo mật polymorphism.

### 15.2. Không tùy tiện sửa converters của tất cả clients

Mỗi RestClient/RestTemplate có cấu hình message converters riêng; thay converter list ở một nơi không mặc định thay toàn bộ clients khác. Spring MVC server dùng converters qua request mapping adapter. Spring WebFlux dùng codec infrastructure khác. Cần thống nhất client/server content negotiation policy, nhưng đừng suy ngược mọi instance dùng cùng list.

## 16. HTTP client đồng bộ và vận hành production

Dù converter/type reference đúng, client vẫn có thể thất bại vì:
- Timeouts mạng/remote service;
- Pool hết kết nối, DNS/TLS/connect delays;
- Payload quá lớn cần parse thành collection khổng lồ;
- 429/503/retry storm;
- Error body chứa PII/credentials nếu log bừa;
- SSRF nếu nhận URL upstream từ user không validate;
- Rate limiting/circuit breaker không được đặt;
- Unbounded threads gọi blocking I/O;
- Mismatch Jackson/schema version giữa client và server.

### 16.1. Đặt connect/read timeout phù hợp

Ví dụ với request factory của Spring:

~~~java
SimpleClientHttpRequestFactory factory =
        new SimpleClientHttpRequestFactory();
factory.setConnectTimeout(3_000); // milliseconds
factory.setReadTimeout(5_000);

RestClient client = RestClient.builder()
        .requestFactory(factory)
        .baseUrl("https://api.example.com")
        .build();
~~~

Đây là cấu hình minh họa chạy được với Spring Web, không chứng minh `SimpleClientHttpRequestFactory` là lựa chọn hiệu năng tốt nhất cho mọi workload. Với production high concurrency, lựa chọn Apache HttpComponents/JDK client với connection pooling theo hạ tầng phù hợp, đo pending acquires, max connections, connection TTL và TLS costs.

**Tách biệt:**
- Connect timeout giới hạn thời gian tạo connection;
- Read timeout giới hạn chờ đọc dữ liệu theo semantics của HTTP client factory;
- Business deadline giới hạn toàn bộ operation, có thể cần ở tầng gọi ngoài;
- Retry nên bounded, có backoff và chỉ khi an toàn/idempotent.

### 16.2. Không parse một response vô hạn thành List

`body(new ParameterizedTypeReference<List<Book>>() {})` là lựa chọn tốt khi endpoint trả **một JSON array hữu hạn, có size limit hợp lý**. Nhưng nếu API trả millions of items, đây vẫn là một collection materialization trong memory. `ParameterizedTypeReference` **không** phải streaming parser.

Với các dữ liệu lớn:
- Pagination ở upstream: endpoint trả Page/limit/next cursor hữu hạn.
- NDJSON/chunked streaming: cân nhắc `RestClient.exchange` + bounded streaming parser hoặc reactive `WebClient.bodyToFlux` khi kiến trúc phù hợp.
- Files: dùng `Resource`/streaming output, không `body(byte[].class)` cho file nhiều GiB.
- Đặt max response bytes/timeouts và bảo vệ trước các JSON objects cực lớn.

### 16.3. Observability

Thu thập metrics theo endpoint:
- Status 2xx/4xx/5xx, retry count và timeout reasons.
- p50/p95/p99 HTTP latency, queue wait, upstream network time.
- Payload size, JSON decoding time/allocations.
- Connection pool active/idle/pending.
- Thread count và blocking worker saturation.
- Serialization/deserialization failures theo media type/schema version.
- Trace/correlation ID, nhưng không log body, tokens hoặc user data nhạy cảm.

Đừng coi lỗi converter chỉ là “body null”; để metric/error policy phản ánh nguyên nhân cụ thể.

## 17. Bảng quyết định nhanh

| Đầu vào HTTP | Đích Java | Cách nên dùng |
| --- | --- | --- |
| `{"id":1,"title":"Spring"}` | `Book` | `body(Book.class)` |
| `[{"id":1,...}]` | `List<Book>` | `body(new ParameterizedTypeReference<List<Book>>() {})` |
| `{"data":[...],"traceId":"..."}` | `ApiEnvelope<List<Book>>` | `body(new ParameterizedTypeReference<ApiEnvelope<List<Book>>>() {})` |
| `{"items":{"a":[...]}}` | `Map<String, List<Book>>` | `ParameterizedTypeReference<Map<String,List<Book>>>` nếu JSON shape thực khớp |
| `hello` với `text/plain` | `String` | `body(String.class)` |
| Bytes nhị phân nhỏ | `byte[]` | `body(byte[].class)` + hard size limit |
| Không có body / HTTP 204 | Không cần DTO | `toBodilessEntity()` |
| HTTP status + headers + typed body | `ResponseEntity<List<Book>>` | `toEntity(ParameterizedTypeReference<List<Book>>)` |
| RestTemplate GET generic | `ResponseEntity<List<Book>>` | `exchange(..., type)` |
| Response streaming/huge payload | Stream/chunks/pagination | Không `collectList` toàn bộ; chọn API có bounded memory |

## 18. Những nhầm lẫn cần tránh

1. **Nhầm `HttpMessageConverter` là Jackson ObjectMapper.** Converter quản lý HTTP media type, đọc/ghi body; Jackson chỉ là một implementation cho JSON.
2. **Nhầm `Accept` với `Content-Type`.** Accept mô tả mong muốn response, Content-Type mô tả bytes thực của request/response.
3. **Dùng `List.class` rồi cast sang `List<Book>`.** Không giải quyết Java erasure; sẽ có `LinkedHashMap` cho object JSON.
4. **Dùng `new ParameterizedTypeReference<T>() {}` trong generic method rồi kỳ vọng biết caller type.** T chưa được resolve, phải truyền type token từ caller.
5. **Dùng `ApiEnvelope.class` cho `ApiEnvelope<List<Book>>`.** Mất generic type của trường data.
6. **Đọc response JSON bằng converter khi response Content-Type là `text/html`.** Phải sửa contract hoặc handling.
7. **Tự `ObjectMapper.readValue` sau khi RestClient đã decode.** Tránh parse hai lần không cần thiết.
8. **Đặt custom converter hỗ trợ mọi media type trước converter mặc định.** Có thể cướp request/response của converter đúng.
9. **Nhầm `RestClient` là reactive.** Nó synchronous; `WebClient` mới là non-blocking reactive.
10. **Tăng connection threads vô hạn để xử lý chậm.** Cần timeouts, bounded pools và upstream capacities.
11. **Tưởng ParameterizedTypeReference giới hạn JSON array size.** Nó chỉ giữ kiểu, không giới hạn số phần tử hoặc memory.
12. **Không test 204, 404, malformed JSON, wrong media type.** Happy-path generic test là cần nhưng chưa đủ production.
13. **Tự đoán Boot 3.0 có RestClient.** RestClient xuất hiện Spring Framework 6.1; dùng Boot 3.2+ hoặc xác minh dependency version.
14. **Copy converter config WebFlux qua RestClient.** Reactive codec và synchronous converter là hai abstraction riêng.
15. **Gửi URL tùy ý cho RestClient từ user.** Có thể dẫn tới SSRF; kiểm soát domain/scheme, redirects và trusted endpoints.
16. **Ghi raw error body vào log.** Upstream có thể trả PII/secrets; log metadata an toàn thay vì toàn payload.

## 19. Câu hỏi ôn tập

**1. Tại sao `getForObject(..., List.class)` thường trả `List<LinkedHashMap>`?**

Vì `List.class` không có type parameter `Book`. Jackson giải JSON object thành Map khi không có element target class rõ ràng.

**2. `ParameterizedTypeReference` có tự parse JSON không?**

Không. Nó lưu Java `Type`; một `HttpMessageConverter` hỗ trợ target type/media type (thường Jackson) mới parse bytes.

**3. `GenericHttpMessageConverter` thêm điều gì?**

Nó có overload làm việc với `Type` ngoài `Class`, cho phép xét generic element/field types.

**4. Khi nào `Book.class` đã đủ?**

Khi response là một concrete `Book` object không generic, và JSON schema tương ứng.

**5. REST client mới Spring 6.2 lấy `List<Book>` thế nào?**

`restClient.get().uri(...).retrieve().body(new ParameterizedTypeReference<List<Book>>() {})`.

**6. RestTemplate dùng cách tương ứng nào?**

`restTemplate.exchange(url, HttpMethod.GET, null, new ParameterizedTypeReference<List<Book>>() {})`.

**7. Sự khác nhau giữa Jackson TypeReference và Spring ParameterizedTypeReference?**

Cả hai lưu type metadata cho generic nhưng thuộc API layer/library khác. Jackson TypeReference dùng với ObjectMapper, Spring ParameterizedTypeReference dùng với Spring client APIs.

**8. Có thể dùng một Method `<T> T fetch()` chứa `new ParameterizedTypeReference<T>() {}` để suy ra T từ nơi gọi?**

Không đáng tin. T là unresolved type variable trong method; caller cần truyền Class/ParameterizedTypeReference hoặc Type đã resolve.

**9. Vì sao `body(List.class)` trả kết quả nhưng `Book b = list.get(0)` có thể ném lỗi?**

Kiểu generic lúc compile bị erase, trong List thực là `LinkedHashMap`, không phải Book.

**10. `Accept: application/json` có bắt buộc server trả JSON không?**

Nó chỉ là negotiation preference. Server có thể trả lỗi/response khác; client phải kiểm tra HTTP status và actual `Content-Type`.

**11. `RestClient.retrieve()` có tự gọi network ngay không?**

Theo Spring 6.2 reference, `retrieve()` một mình chưa thực thi request; phải gọi terminal `body(...)`, `toEntity(...)`, hoặc `toBodilessEntity()`.

**12. Vì sao type token không thay paging/size limits?**

Nó mô tả kiểu đích, còn số lượng bytes/items vẫn có thể cực lớn. Cần pagination/streaming/caps độc lập.

## 20. Checklist trước khi đưa vào production

1. Xác định rõ HTTP client đang là **RestClient**, **RestTemplate** hay WebClient; cấu hình đúng converter/codec stack.
2. Kiểm tra Spring version: RestClient từ 6.1, trong ví dụ là Framework 6.2/Boot 3.5.
3. Thiết kế DTO/records khớp JSON schema, field names, nullability, date/time và unknown-fields policy.
4. Với response generic/nested, luôn chuyển type token đã resolve `ParameterizedTypeReference<T>` ở đúng tầng API.
5. Đảm bảo Jackson hoặc converter tương ứng có trong classpath và danh sách client converters.
6. Đặt `Accept` và `Content-Type` theo đúng request/response contract, không ép media type `*/*` để che lỗi.
7. Kiểm tra status, headers, null/204 và 4xx/5xx; định nghĩa exception mapping/retry/idempotency rõ.
8. Cấu hình connect/read/overall timeouts và connection pool/concurrency budgets.
9. Không nhận URL tùy ý hoặc redirects nguy hiểm gây SSRF, dùng allowlist outbound hosts.
10. Đặt max response bytes/number of elements, pagination hoặc bounded streaming cho payload lớn.
11. Không serialize secrets hoặc log request/response bodies nhạy cảm; có tracing/observability và redact.
12. Dùng `MockRestServiceServer` kiểm thử converters, generic element runtime class, nested DTO, POST JSON, status errors và malformed media type.
13. Kiểm thử integration với upstream thực khi cần verify proxy, TLS, network timeout và content negotiation.
14. Đừng coi chuyển RestTemplate → RestClient là một thay đổi từ blocking sang non-blocking; đo yêu cầu cụ thể.

## 21. Nguồn tham khảo

- [Spring Framework 6.2 — REST Clients (RestClient, RestTemplate, ParameterizedTypeReference)](https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html)
- [Spring Framework 6.2 — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/message-converters.html)
- [Spring Framework 6.2 — RestClient Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/client/RestClient.html)
- [Spring Framework 6.2 — RestTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/client/RestTemplate.html)
- [Spring Framework 6.2 — GenericHttpMessageConverter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/converter/GenericHttpMessageConverter.html)
- [Spring Framework 6.2 — HttpMessageConverter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/converter/HttpMessageConverter.html)
- [Spring Framework 6.2 — ParameterizedTypeReference Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/ParameterizedTypeReference.html)
- [Spring Framework 6.2 — MockRestServiceServer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/web/client/MockRestServiceServer.html)
- [Spring Boot 3.5 — REST clients auto configuration](https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html)
- [Oracle Java — Type Erasure](https://docs.oracle.com/javase/tutorial/java/generics/erasure.html)
