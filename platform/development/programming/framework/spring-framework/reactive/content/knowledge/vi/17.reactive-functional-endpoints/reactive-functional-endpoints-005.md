# Tạo phản hồi bằng bodyValue, body và build

**Ngữ cảnh:** Spring Framework Reactive → **Endpoint hàm (WebFlux.fn)**.

Trong WebFlux.fn, một handler nhận `ServerRequest` và trả `Mono<ServerResponse>`. `ServerResponse` mô tả response HTTP: status, headers và body. Khi tạo response, ba cách thường gặp là:

- `bodyValue(value)` — ghi **một giá trị Java cụ thể** làm body.
- `body(publisher, elementType)` — ghi body từ **Publisher** như `Mono<T>` hoặc `Flux<T>`; framework subscribe và chuyển các phần tử thành HTTP content.
- `build()` hoặc `build(voidPublisher)` — tạo response **không có body**; overload thứ hai đợi một publisher hoàn tất trước khi response được commit.

Điểm dễ nhầm nhất là `build()` có hai ý nghĩa khác nhau tùy builder: `RouterFunctions.route().build()` tạo một router, còn `ServerResponse.ok().build()` tạo một HTTP response không có body. Trong bài này, `build` chủ yếu nói về `ServerResponse`.

## 1. WebFlux.fn tạo response theo mô hình nào?

WebFlux.fn là mô hình lập trình functional của Spring WebFlux. Thay vì khai báo route bằng annotation trên controller, ứng dụng kết hợp `RouterFunction` để định tuyến với `HandlerFunction` để xử lý request.

Một `HandlerFunction<ServerResponse>` nhận `ServerRequest` và trả `Mono<ServerResponse>`:

```java
HandlerFunction<ServerResponse> hello =
        request -> ServerResponse.ok().bodyValue("Hello World");
```

`Mono<ServerResponse>` là kết quả bất đồng bộ của handler. Nó cho phép việc đọc body, truy vấn dữ liệu hoặc ghi dữ liệu hoàn tất trước khi response được tạo. Bản thân `ServerResponse` là mô tả response; server adapter và response result handler của WebFlux chịu trách nhiệm ghi nó ra kết nối HTTP.

Một router tối giản:

```java
@Bean
RouterFunction<ServerResponse> routes(PeopleHandler handler) {
    return RouterFunctions.route()
            .GET("/people/{id}", handler::getOne)
            .GET("/people", handler::list)
            .POST("/people", handler::create)
            .DELETE("/people/{id}", handler::delete)
            .build();
}
```

Đây là snippet cần class `PeopleHandler` và Spring WebFlux configuration. `RouterFunctions.route().build()` kết thúc việc khai báo route và trả `RouterFunction<ServerResponse>`. Các method handler được tham chiếu sẽ trả `Mono<ServerResponse>`.

Khi request khớp route, `HandlerFunction` được gọi. `ServerResponseResultHandler` xử lý kết quả và gọi `writeTo` để ghi response. Do đó, handler nên **trả publisher**, không tự gọi `subscribe()` hoặc `block()` để ép response chạy.

## 2. ServerResponse và BodyBuilder

`ServerResponse` là abstraction đại diện cho HTTP response ở phía server. Các factory method thường dùng:

| Factory | Status | Mục đích |
|---|---:|---|
| `ServerResponse.ok()` | 200 | Trả dữ liệu thành công |
| `ServerResponse.created(uri)` | 201 | Tạo resource mới, kèm header `Location` |
| `ServerResponse.accepted()` | 202 | Đã chấp nhận xử lý, thường dùng cho workflow bất đồng bộ |
| `ServerResponse.noContent()` | 204 | Thành công nhưng không có body |
| `ServerResponse.badRequest()` | 400 | Request không hợp lệ |
| `ServerResponse.notFound()` | 404 | Không tìm thấy resource |
| `ServerResponse.status(code)` | Tùy chọn | Status tùy chỉnh |

Các factory trả về builder thích hợp. Ví dụ:

```java
Mono<ServerResponse> response =
        ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(person);
```

Các method như `contentType`, `header`, `headers`, `contentLength` và `hint` cấu hình metadata/serialization. Sau đó `bodyValue`, `body` hoặc `build` tạo `Mono<ServerResponse>`.

Ví dụ thêm header:

```java
return ServerResponse.ok()
        .header("X-Request-Source", "catalog")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(person);
```

`ServerResponse` có contract bất biến sau khi được tạo; builder là nơi cấu hình response trước khi xây dựng. Không nên giữ một builder mutable dùng chung giữa nhiều request. Tạo response builder mới cho mỗi lần xử lý request.

## 3. bodyValue(value): trả một giá trị cụ thể

`bodyValue` dùng khi ứng dụng đã có **một object Java cụ thể** và muốn dùng object đó làm response body.

```java
Person person = new Person(7, "An");

return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(person);
```

Framework chọn `HttpMessageWriter` và codec phù hợp với kiểu dữ liệu cùng `Content-Type`. Nếu JSON codec được cấu hình, object `Person` được serialize thành JSON.

Ví dụ body có thể được client nhận như sau:

```json
{
  "id": 7,
  "name": "An"
}
```

Đây là JSON representation minh họa; nội dung thực tế phụ thuộc field, Jackson configuration, serializer và các annotation của DTO.

### 3.1. bodyValue phù hợp với trường hợp nào?

- Một DTO đã được lấy từ cache hoặc đã có sẵn trong bộ nhớ.
- Một kết quả tính toán đồng bộ.
- Một object domain đã được chuyển sang response DTO.
- Một collection hữu hạn, nhỏ và có giới hạn rõ ràng khi muốn trả nó như một JSON array.

Ví dụ trả danh sách đã có:

```java
List<PersonDto> people = List.of(
        new PersonDto(1, "An"),
        new PersonDto(2, "Binh")
);

return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(people);
```

Ở đây `List<PersonDto>` là một giá trị đã được tạo. `bodyValue` không biến list thành một stream reactive. Nếu list lớn, việc gom toàn bộ dữ liệu trước khi trả response có thể tiêu tốn bộ nhớ đáng kể.

### 3.2. bodyValue không phải cách đưa Mono hoặc Flux vào response

Đây là lỗi thường gặp:

```java
Mono<Person> person = repository.findById(id);

// Sai: bodyValue nhận một object, không phải Publisher để stream.
return ServerResponse.ok()
        .bodyValue(person);
```

Trong Spring WebFlux, `bodyValue` từ chối `Publisher` hoặc producer mà `ReactiveAdapterRegistry` nhận diện được; trường hợp này có thể ném `IllegalArgumentException`.

Hãy dùng `body` khi giá trị thực tế là một publisher:

```java
Mono<Person> person = repository.findById(id);

return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(person, Person.class);
```

Nếu repository trả empty, `body` không tự chuyển response thành 404. Handler cần quyết định rõ trường hợp không tìm thấy bằng `switchIfEmpty`.

## 4. body(publisher, elementType): trả dữ liệu reactive

`body` dùng khi body đến từ một nguồn bất đồng bộ, chẳng hạn:

- `Mono<Person>`: tối đa một object.
- `Flux<Person>`: nhiều object được phát theo thời gian.
- Một `Publisher<T>` khác tương thích với Reactive Streams.
- Một producer khác có thể được Spring `ReactiveAdapterRegistry` chuyển thành Publisher thông qua overload phù hợp.

Ví dụ một `Mono`:

```java
Mono<Person> person = repository.findById(id);

return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(person, Person.class);
```

Ví dụ một `Flux`:

```java
Flux<Person> people = repository.findAll();

return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(people, Person.class);
```

Khác biệt quan trọng: `body` không yêu cầu handler gom toàn bộ stream thành list trước. Writer tiêu thụ publisher và serialize phần tử theo khả năng của codec/transport. Đây là lựa chọn tự nhiên cho response có dữ liệu reactive.

### 4.1. Ý nghĩa của elementType

Overload phổ biến:

```java
.body(publisher, Person.class)
```

Tham số thứ hai là **kiểu của từng phần tử được publisher phát**, không phải kiểu của toàn bộ publisher. Với `Flux<Person>`, element type là `Person.class`.

Nếu mỗi item là một kiểu generic, có thể dùng `ParameterizedTypeReference` để giữ thông tin generic:

```java
Flux<Map<String, Object>> rows = repository.findRows();

return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(rows,
                new ParameterizedTypeReference<Map<String, Object>>() {});
```

Đây là snippet cần import `ParameterizedTypeReference` và các kiểu tương ứng. Type reference mô tả **một phần tử Map**, vì publisher phát nhiều Map. Không truyền `ParameterizedTypeReference<List<Map<...>>>` trừ khi mỗi phần tử thực sự là một list.

### 4.2. body có thể nhận Mono hoặc Flux

Cả hai đều là Publisher:

```java
Mono<Person> one = repository.findById(7);

Mono<ServerResponse> oneResponse =
        ServerResponse.ok().body(one, Person.class);

Flux<Person> many = repository.findAll();

Mono<ServerResponse> manyResponse =
        ServerResponse.ok().body(many, Person.class);
```

Trong ví dụ thứ nhất, publisher phát tối đa một person. Trong ví dụ thứ hai, publisher có thể phát nhiều person. Cùng một API `body` hỗ trợ cả hai; kiểu nguồn và contract của endpoint quyết định ngữ nghĩa.

Nếu `Mono<Person>` là empty, response body không có person. Nếu yêu cầu API là trả 404 khi không có resource, hãy xử lý empty trước khi tạo response:

```java
return repository.findById(id)
        .flatMap(person ->
                ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(person))
        .switchIfEmpty(ServerResponse.notFound().build());
```

### 4.3. body không tự chọn status dựa trên dữ liệu

`body` chỉ cấu hình response body. Nó không tự suy ra:

- Empty có nghĩa 404.
- Có dữ liệu có nghĩa 200.
- Lỗi repository có nghĩa 404.
- Một publisher phát nhiều item có nghĩa 206 Partial Content.

Status là quyết định của handler và API contract. Hãy đặt status rõ bằng `ok()`, `created()`, `notFound()` hoặc `status(...)`.

## 5. body(BodyInserter): kiểm soát cách ghi body

`BodyInserter` là abstraction mô tả cách chèn nội dung vào response. Overload:

```java
.body(BodyInserter<?, ? super ServerHttpResponse> inserter)
```

cho phép sử dụng một inserter có sẵn hoặc custom inserter. Với các trường hợp thông thường, `bodyValue` và `body(publisher, type)` là API ngắn gọn hơn.

Ví dụ dùng `BodyInserters.fromValue`:

```java
return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(BodyInserters.fromValue(person));
```

Đây là cách diễn đạt tương đương về ý nghĩa với `bodyValue(person)`. Nó hữu ích khi cần kết hợp với API `BodyInserters` hoặc khi một phương thức khác đã tạo sẵn BodyInserter.

Với publisher:

```java
return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(BodyInserters.fromPublisher(people, Person.class));
```

Đây là cách tạo inserter từ publisher, có ý nghĩa tương đương với `body(people, Person.class)` trong trường hợp này.

### 5.1. Khi nào cần BodyInserter tùy chỉnh?

Có thể cần khi:

- Một abstraction dùng chung đã cung cấp `BodyInserter`.
- Cần ghép một cách ghi body đặc thù với response builder.
- Cần tích hợp một chiến lược ghi nội dung đã có.
- Muốn tái sử dụng một hàm tạo body inserter giữa nhiều handler.

Không nên tạo custom inserter chỉ để thay một lời gọi `bodyValue` đơn giản. Custom writer phải tôn trọng lifecycle, cancellation, backpressure và ownership của buffer.

### 5.2. Hints cho codec

`BodyBuilder.hint(key, value)` và `hints(...)` truyền gợi ý cho codec hỗ trợ. Ví dụ Jackson JSON View:

```java
return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .hint(Jackson2CodecSupport.JSON_VIEW_HINT, PublicView.class)
        .bodyValue(person);
```

Đây là snippet yêu cầu Jackson codec và view class phù hợp. Hint chỉ có tác dụng nếu codec đang dùng hiểu key đó; nó không phải một bộ lọc bảo mật tổng quát. Không dựa vào JSON View để thay thế authorization hoặc thiết kế response DTO.

## 6. build(): tạo response không có body

`build()` tạo `ServerResponse` mà không ghi response body.

Ví dụ:

```java
return ServerResponse.noContent().build();
```

Kết quả là response 204 No Content, không có body.

Một response 201 Created với header Location:

```java
URI location = URI.create("/people/7");

return ServerResponse.created(location).build();
```

`created(location)` đặt status 201 và header `Location`. `build()` kết thúc response không có body.

Các ví dụ khác:

```java
return ServerResponse.notFound().build();

return ServerResponse.badRequest().build();

return ServerResponse.accepted().build();
```

Không nên gắn body JSON vào status 204. Theo HTTP semantics, 204 biểu thị không có content trong response; nếu client cần một object kết quả, dùng status phù hợp như 200 hoặc 201 cùng body.

### 6.1. build() không đợi một tác vụ nghiệp vụ khác

Giả sử:

```java
Mono<Void> save = repository.save(person);

return ServerResponse.ok().build();
```

Đoạn này **không sử dụng publisher save**. Nếu handler không ghép `save` vào response pipeline ở nơi khác, việc lưu không được thực thi bởi đoạn code trên. `build()` chỉ tạo response không body.

Không được hiểu `build()` là “đợi mọi thao tác trước đó trong biến local”. Reactive publisher chỉ được chạy khi được subscribe và được nối vào chuỗi thực thi.

## 7. build(Publisher<Void>): response không body nhưng đợi công việc hoàn tất

Overload `build(Publisher<Void>)` cũng tạo response không có body, nhưng response được commit khi publisher truyền vào **hoàn tất**.

Đây là khác biệt cốt lõi:

```java
Mono<Void> save = repository.save(person);

return ServerResponse.ok().build(save);
```

Nếu `save` hoàn tất thành công, `build(save)` tạo response. Nếu `save` phát lỗi, lỗi đi theo publisher kết quả và response bình thường không được commit bởi đường thành công này.

Spring mô tả overload này là build response không có body và chỉ commit response khi publisher được cung cấp hoàn tất. Nó phù hợp với tác vụ có kiểu `Mono<Void>` như save/delete/audit mà client không cần nhận một object response.

### 7.1. Luồng tín hiệu

```text
Handler tạo Mono<Void> save
          │
          ▼
ServerResponse.ok().build(save)
          │
          ▼
Framework subscribe vào Mono<ServerResponse>
          │
          ▼
Publisher save được thực thi
     ┌────┴──────────┐
     │               │
 onComplete        onError
     │               │
     ▼               ▼
Tạo/commit       Truyền lỗi tới
response không   error handling
có body          của WebFlux
```

Nếu publisher là `Mono.empty()`, nó hoàn tất ngay khi được subscribe; do đó response có thể được tạo ngay sau completion đó. Nếu publisher là `Mono.never()`, response sẽ chờ vô hạn nếu không có timeout hoặc cancellation. Nếu publisher lỗi, handler trả lỗi reactive thay vì coi thao tác là thành công.

### 7.2. Dùng build(Publisher<Void>) cho create/delete

Ví dụ một thao tác xóa:

```java
Mono<Void> deletion = repository.deleteById(id);

return ServerResponse.noContent().build(deletion);
```

Response 204 chỉ được tạo sau khi publisher delete hoàn tất. Tuy nhiên, nếu repository coi “không có ID” là hoàn tất bình thường, đoạn này vẫn trả 204. Nếu API cần 404 khi không có resource, repository phải cung cấp kết quả đủ thông tin để phân biệt và handler phải ánh xạ rõ.

Ví dụ một thao tác ghi audit trước khi trả response:

```java
Mono<Void> audit = auditService.recordAccess(userId);

return ServerResponse.ok().build(audit);
```

Response không có body được tạo sau khi audit publisher complete. Nếu audit là bắt buộc đối với yêu cầu, lỗi audit sẽ làm workflow lỗi. Nếu audit chỉ best-effort, hãy định nghĩa policy riêng thay vì vô tình bỏ lỗi.

### 7.3. build(Publisher<Void>) không gửi publisher đó thành body

Đây là lỗi phân biệt API:

```java
// Không phải cách stream danh sách Person:
return ServerResponse.ok().build(repository.findAll());
```

`build(Publisher<Void>)` yêu cầu publisher biểu diễn **completion**, không phải các item response. `Flux<Person>` không phải `Publisher<Void>` phù hợp.

Muốn ghi danh sách Person, dùng:

```java
return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(repository.findAll(), Person.class);
```

`body` dùng các phần tử để tạo response content; `build` chỉ dùng completion publisher để quyết định lúc commit response rỗng.

## 8. So sánh ba cách tạo response

| Cách | Đầu vào | Có body? | Đợi publisher? | Ví dụ |
|---|---|---:|---:|---|
| `bodyValue(value)` | Object cụ thể | Có | Không có publisher body để đợi | `Person` |
| `body(publisher, type)` | Publisher phát dữ liệu | Có, theo item phát ra | Có, writer tiêu thụ publisher | `Flux<Person>` |
| `build()` | Không cần publisher | Không | Không đợi tác vụ khác | `204 No Content` |
| `build(voidPublisher)` | Publisher chỉ biểu thị completion | Không | Có, chờ complete | `Mono<Void>` |

Ví dụ cùng một dữ liệu:

```java
Person person = new Person(7, "An");

// Object đã có:
Mono<ServerResponse> a =
        ServerResponse.ok().bodyValue(person);

// Publisher chỉ có một item:
Mono<Person> personMono = Mono.just(person);
Mono<ServerResponse> b =
        ServerResponse.ok().body(personMono, Person.class);

// Không body, không đợi tác vụ:
Mono<ServerResponse> c =
        ServerResponse.noContent().build();

// Không body, chờ thao tác save:
Mono<Void> save = repository.save(person);
Mono<ServerResponse> d =
        ServerResponse.noContent().build(save);
```

Lựa chọn đúng dựa trên **kiểu đầu vào và ý nghĩa response**, không dựa vào việc tên method ngắn hay dài.

## 9. Ví dụ thực tế: handler cho resource Person

Một handler class có thể nhóm các chức năng đọc, liệt kê, tạo và xóa:

```java
import java.net.URI;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import static org.springframework.web.reactive.function.server.ServerResponse.*;

public class PeopleHandler {

    private final PeopleRepository repository;

    public PeopleHandler(PeopleRepository repository) {
        this.repository = repository;
    }

    public Mono<ServerResponse> getOne(ServerRequest request) {
        int id = Integer.parseInt(request.pathVariable("id"));

        return repository.findById(id)
                .flatMap(person -> ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(person))
                .switchIfEmpty(notFound().build());
    }

    public Mono<ServerResponse> list(ServerRequest request) {
        Flux<Person> people = repository.findAll();

        return ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(people, Person.class);
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        Mono<Person> saved = request.bodyToMono(Person.class)
                .flatMap(repository::save);

        return saved.flatMap(person -> created(
                        URI.create("/people/" + person.id()))
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(person));
    }

    public Mono<ServerResponse> delete(ServerRequest request) {
        int id = Integer.parseInt(request.pathVariable("id"));

        return noContent().build(repository.deleteById(id));
    }
}
```

Đây là handler hoàn chỉnh về cấu trúc nhưng phụ thuộc vào `Person`, `PeopleRepository` và implementation repository của ứng dụng. Giả định:

- `findById` trả `Mono<Person>`, empty nếu không tìm thấy.
- `findAll` trả `Flux<Person>`.
- `save` trả `Mono<Person>` đã lưu và có ID.
- `deleteById` trả `Mono<Void>` hoàn tất khi thao tác xóa hoàn tất.

Phân tích từng method:

**getOne:** `bodyValue` dùng khi `findById` đã phát một Person cụ thể. Nếu empty, `switchIfEmpty` chọn response 404 không body. Lỗi repository vẫn đi qua error signal; nó không tự biến thành 404.

**list:** `body` nhận `Flux<Person>`. Handler không cần `collectList()`; response writer tiêu thụ publisher và serialize từng phần tử theo codec. Client có thể nhận một JSON array; cách ghi và flush phụ thuộc media type, writer và transport.

**create:** request body được decode thành `Person`, repository lưu và phát lại person đã lưu. Sau đó handler tạo response 201 cùng Location và body JSON. `bodyValue` được gọi khi object saved đã có.

**delete:** `build(Publisher<Void>)` đảm bảo response không body được tạo sau completion của thao tác delete. Nếu repository phát lỗi, response đi theo đường error.

### Một cách create khác: chỉ trả status và Location

Nếu API không cần trả object đã tạo, có thể dùng `build()` sau khi đã có kết quả save:

```java
public Mono<ServerResponse> createWithoutBody(ServerRequest request) {
    return request.bodyToMono(Person.class)
            .flatMap(repository::save)
            .flatMap(saved -> created(
                    URI.create("/people/" + saved.id()))
                    .build());
}
```

Ở đây `build()` nằm **bên trong flatMap sau khi save đã phát saved**. Vì vậy handler vẫn đợi save; việc đợi đến từ chuỗi `flatMap`. Đây khác với `build()` được gọi độc lập trước khi nối publisher save.

## 10. bodyValue, body và build trong RouterFunction

Một router có thể kết hợp nhiều loại response:

```java
@Bean
RouterFunction<ServerResponse> peopleRoutes(PeopleHandler handler) {
    return RouterFunctions.route()
            .GET("/people/{id}", handler::getOne)
            .GET("/people", handler::list)
            .POST("/people", handler::create)
            .DELETE("/people/{id}", handler::delete)
            .build();
}
```

Hãy phân biệt hai lời gọi `build`:

- `RouterFunctions.route().build()` — tạo `RouterFunction` từ route definitions.
- `ServerResponse.noContent().build()` — tạo `Mono<ServerResponse>` không có body.
- `ServerResponse.ok().build(publisher)` — tạo response rỗng sau completion publisher.

Ba lời gọi cùng tên nhưng khác builder, kiểu trả về và mục đích. Khi đọc code, luôn xem đối tượng đứng trước dấu chấm để xác định đang build router hay HTTP response.

## 11. Status, headers và body phải nhất quán

Body method không tự quyết định status. Handler nên chọn status theo API contract.

| Tình huống | Response thường dùng | Body |
|---|---|---|
| Đọc thành công một resource | 200 OK + `bodyValue` | Resource |
| Đọc danh sách từ repository | 200 OK + `body` | `Flux<T>` |
| Tạo mới và trả resource | 201 Created + Location + `bodyValue` | Resource mới |
| Tạo mới nhưng không cần nội dung | 201 Created + Location + `build()` | Không |
| Xóa thành công | 204 No Content + `build(voidPublisher)` | Không |
| Chấp nhận job chạy nền | 202 Accepted + `bodyValue` hoặc `build()` | Có thể là job ID |
| Không tìm thấy | 404 Not Found + `build()` | Không |
| Request không hợp lệ | 400 Bad Request hoặc 422 theo contract | Có thể có error DTO |

Ví dụ tạo response có header cache:

```java
return ServerResponse.ok()
        .cacheControl(CacheControl.maxAge(Duration.ofMinutes(5)))
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(person);
```

Ví dụ thêm ETag hoặc Location cần tính toán đúng theo resource. Không đặt Content-Length thủ công cho stream nếu chưa biết chính xác số byte sẽ ghi; encoder có thể tạo dữ liệu theo thời gian.

### 11.1. 202 Accepted không có nghĩa công việc đã hoàn tất

Một API nhận job xử lý nền thường trả 202 khi job đã được chấp nhận để xử lý, chứ không nhất thiết chờ xử lý xong.

Nếu ứng dụng enqueue một job bền vững và có job ID:

```java
return ServerResponse.accepted()
        .location(URI.create("/jobs/" + job.id()))
        .bodyValue(new JobAccepted(job.id()));
```

Nếu dùng `build(jobProcessingPublisher)`, handler lại chờ publisher đó hoàn tất trước khi response được commit. Đây có thể là semantics khác với “đã chấp nhận, xử lý sau”. Hãy phân biệt việc **enqueue đã thành công** với việc **toàn bộ job đã xử lý xong**.

## 12. Xử lý empty và error đúng cách

Một publisher body có thể:

- Phát một hoặc nhiều item.
- Hoàn tất mà không phát item.
- Phát lỗi trước khi có item.
- Phát một phần dữ liệu rồi mới lỗi.

### 12.1. Empty không tự đồng nghĩa Not Found

`Mono.empty()` là hoàn tất thành công không có item. Chỉ khi contract của endpoint xác định “không có item” nghĩa là resource không tồn tại, mới chuyển thành 404.

```java
return repository.findById(id)
        .flatMap(person -> ServerResponse.ok().bodyValue(person))
        .switchIfEmpty(ServerResponse.notFound().build());
```

### 12.2. Error không được biến thành empty một cách tùy tiện

`onErrorResume(error -> Mono.empty())` có thể che giấu database outage như thể resource không tồn tại. Phân biệt lỗi nghiệp vụ, lỗi codec, lỗi persistence và trạng thái empty.

Nếu cần chuyển lỗi domain thành status cụ thể, dùng exception mapping hoặc error handler tập trung. `bodyValue`, `body` và `build` không thay thế cơ chế xử lý lỗi.

### 12.3. Publisher body lỗi sau khi response đã bắt đầu ghi

Với response streaming, writer có thể đã gửi status và headers trước khi publisher body lỗi. Server thường không thể quay lại đổi status đã commit hoặc thay một phần stream bằng một error JSON hoàn chỉnh.

Nếu endpoint streaming cần biểu đạt lỗi giữa luồng, thiết kế protocol-level error event, sequence ID hoặc cơ chế resume. Đừng giả định `body(Flux<T>, T.class)` biến mọi lỗi muộn thành response 500 hoàn chỉnh.

## 13. Streaming, backpressure và memory

`body(Flux<T>, Class<T>)` là lựa chọn tự nhiên khi response được tạo dần. Tuy nhiên, việc dùng `Flux` không tự bảo đảm mọi tầng đều streaming hoàn hảo.

Các điểm cần lưu ý:

- Đừng `collectList()` một nguồn vô hạn hoặc rất lớn chỉ để gọi `bodyValue`.
- Dùng `Flux<T>` nếu có thể encode và gửi từng phần tử theo media type phù hợp.
- Xác định rõ JSON array, NDJSON hoặc SSE theo contract của client.
- Giới hạn concurrency ở upstream; không tạo vô hạn inner calls.
- Đo buffer, direct memory, response latency và slow clients.
- Khi client disconnect, cancellation có thể truyền tới publisher; side effect ngoài hệ thống không tự rollback.
- Nếu stream phải replay, dùng event store/broker và sequence thay vì mong `body` tự lưu lịch sử.

Ví dụ NDJSON:

```java
return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_NDJSON)
        .body(repository.streamEvents(), EventDto.class);
```

Ví dụ SSE:

```java
return ServerResponse.ok()
        .contentType(MediaType.TEXT_EVENT_STREAM)
        .body(eventService.stream(), ServerSentEvent.class);
```

Đây là snippets; kiểu SSE có thể là `ServerSentEvent<EventDto>` và cần element type tương ứng. Media type phải phù hợp với cách client đọc. `body` chỉ nối publisher với response writer; nó không tự tạo framing SSE nếu dữ liệu nguồn không được biểu diễn đúng kiểu.

## 14. Không tự subscribe hoặc block để tạo response

Không làm như sau:

```java
public Mono<ServerResponse> wrong(ServerRequest request) {
    repository.save(request.bodyToMono(Person.class))
            .subscribe();

    return ServerResponse.ok().build();
}
```

Đoạn này tạo subscription riêng và response có thể hoàn tất trước khi save. Lỗi save không tự đi vào handler response; client disconnect không nhất thiết hủy công việc con.

Hãy nối publisher:

```java
public Mono<ServerResponse> correct(ServerRequest request) {
    return request.bodyToMono(Person.class)
            .flatMap(repository::save)
            .flatMap(saved -> ServerResponse.created(
                    URI.create("/people/" + saved.id()))
                    .bodyValue(saved));
}
```

Tương tự, không dùng `block()` trong handler WebFlux để lấy object đồng bộ rồi mới build response. Điều đó chặn thread reactive và phá mô hình non-blocking. Dùng `flatMap`, `map`, `then` và trả `Mono<ServerResponse>`.

## 15. Chương trình Java 17+ chạy độc lập: phân biệt bodyValue, body và build

Ví dụ sau sử dụng Maven và Spring WebFlux. Chương trình tạo các đối tượng `ServerResponse` để minh họa cách builder chọn body và cách `build(Publisher<Void>)` đợi completion. Nó **không dựng HTTP server và không serialize body ra socket**; phần ghi HTTP thực tế do WebFlux server adapter và response writer đảm nhiệm.

Cấu trúc:

```text
server-response-builder-demo/
├── pom.xml
└── src/main/java/demo/ServerResponseBuilderDemo.java
```

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>server-response-builder-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-webflux</artifactId>
            <version>6.2.16</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp `src/main/java/demo/ServerResponseBuilderDemo.java`:

```java
package demo;

import java.net.URI;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.ServerResponse;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class ServerResponseBuilderDemo {

    record Person(int id, String name) { }

    public static void main(String[] args) {
        Person person = new Person(7, "An");

        ServerResponse valueResponse = ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(person)
                .block();

        System.out.println("bodyValue status="
                + valueResponse.statusCode().value());

        ServerResponse publisherResponse = ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(Flux.just(
                        person,
                        new Person(8, "Binh")),
                        Person.class)
                .block();

        System.out.println("body publisher status="
                + publisherResponse.statusCode().value());

        ServerResponse emptyResponse = ServerResponse.noContent()
                .build()
                .block();

        System.out.println("build status="
                + emptyResponse.statusCode().value());

        AtomicInteger completedWork = new AtomicInteger();

        Mono<Void> save = Mono.fromRunnable(() -> {
            completedWork.incrementAndGet();
            System.out.println("save publisher completed");
        });

        ServerResponse afterSave = ServerResponse
                .created(URI.create("/people/7"))
                .build(save)
                .block();

        System.out.println("build(publisher) status="
                + afterSave.statusCode().value()
                + ", completedWork=" + completedWork.get());
    }
}
```

Chạy từ thư mục chứa `pom.xml` với JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ServerResponseBuilderDemo
```

**Standard output dự kiến** (không tính thông báo Maven):

```text
bodyValue status=200
body publisher status=200
build status=204
save publisher completed
build(publisher) status=201, completedWork=1
```

Giải thích:

1. `bodyValue(person)` tạo response 200 có body value là một Person.
2. `body(Flux.just(...), Person.class)` tạo response 200 có body đến từ publisher phát hai Person.
3. `noContent().build()` tạo response 204 không body.
4. `created(uri).build(save)` subscribe vào publisher completion. Callback tăng counter và in dòng save complete trước khi `block()` nhận response 201.
5. `block()` chỉ xuất hiện trong `main` của chương trình minh họa để chờ kết quả. Không đưa `block()` vào WebFlux handler hoặc event-loop.

Ví dụ chứng minh builder API và thời điểm completion publisher. Nó không kiểm tra JSON bytes trên mạng, không dựng HTTP headers thực tế hoặc thay thế integration test với WebTestClient.

## 16. Kiểm thử handler và response

Nên kiểm tra cả response metadata lẫn publisher lifecycle.

### 16.1. StepVerifier cho handler

Với một handler trả `Mono<ServerResponse>`:

```java
StepVerifier.create(handler.getOne(request))
        .assertNext(response ->
                assertEquals(200, response.statusCode().value()))
        .verifyComplete();
```

Đây là snippet cần JUnit, Reactor Test, request fixture và imports. Kiểm tra status chưa đủ để chứng minh body được serialize đúng; cần test HTTP boundary cho writer/codec.

### 16.2. WebTestClient kiểm tra HTTP thật

`WebTestClient` có thể bind tới router function hoặc server thật để kiểm tra status, headers và body:

```java
webTestClient.get()
        .uri("/people/7")
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.id").isEqualTo(7)
        .jsonPath("$.name").isEqualTo("An");
```

Đây là snippet cần WebTestClient đã bind với ứng dụng/RouterFunction và dữ liệu test tương ứng.

### 16.3. Test build(Publisher<Void>) đợi completion

Có thể dùng một publisher có thể kiểm soát để chứng minh response chưa xuất hiện trước completion. Ví dụ unit-level với `MonoProcessor`/`Sinks.One` cần quản lý subscription và test synchronization; không dùng `Thread.sleep` để đoán thời điểm. Trong integration test, kiểm tra thao tác ghi chưa hoàn tất thì response chưa được commit.

Ngoài ra, test các trường hợp:

- Repository phát empty.
- Repository phát lỗi trước khi tạo response.
- Body publisher phát một phần rồi lỗi.
- Client hủy khi body đang stream.
- Response dùng đúng status, Content-Type và Location.
- Body có đúng schema JSON hoặc framing NDJSON/SSE.
- Không có tác vụ nào bị subscribe tách rời.

## 17. Những lỗi thường gặp

1. **Dùng `bodyValue(mono)`.** `bodyValue` nhận object cụ thể; dùng `body(mono, Type.class)` cho publisher.
2. **Dùng `build()` để mong chờ save.** `build()` không nhận publisher; nối thao tác qua `flatMap` hoặc dùng `build(Mono<Void>)`.
3. **Dùng `build(fluxOfPeople)` để trả danh sách.** Overload này biểu thị completion và không có body; dùng `body(flux, Person.class)`.
4. **Dùng `bodyValue` cho stream vô hạn.** Nó không phải streaming API; dùng `body(Flux, type)`.
5. **Quên Content-Type.** Writer có thể không chọn representation mà client mong muốn; đặt content type theo API contract khi cần.
6. **Cho rằng body empty tự trả 404.** Empty là tín hiệu complete không item; handler phải dùng `switchIfEmpty` nếu empty có nghĩa không tìm thấy.
7. **Cho rằng body publisher error luôn tạo HTTP 500 hoàn chỉnh.** Nếu response đã commit, status không thể thay ngược; lỗi stream có thể làm response kết thúc bất thường.
8. **Gọi subscribe bên trong handler.** Tạo subscription riêng và tách lỗi/hủy khỏi response.
9. **Gọi block trong handler.** Chặn thread reactive; hãy compose publisher.
10. **Dùng build(Publisher<Void>) với publisher phát giá trị.** Hãy chuyển thành `Mono<Void>` nếu chỉ cần completion hoặc dùng `body` nếu muốn gửi item.
11. **Trả 202 sau khi đợi toàn bộ job hoàn tất.** Kiểm tra semantics; 202 thường biểu thị đã chấp nhận chứ không nhất thiết đã xử lý xong.
12. **Trả 204 kèm body JSON.** 204 không có content; chọn status khác nếu cần body.
13. **Dùng bodyValue(List lớn) cho dữ liệu không giới hạn.** Collection đã aggregate có thể tiêu tốn nhiều bộ nhớ; cân nhắc Flux và streaming format.
14. **Không khai báo element type đúng.** `body(publisher, Person.class)` mô tả từng phần tử, không phải kiểu toàn bộ publisher.
15. **Nhầm RouterFunctions.Builder.build với ServerResponse.build.** Xác định builder receiver và kiểu trả về trước khi kết luận.
16. **Coi BodyInserter là nơi thực hiện business logic.** Inserter chịu trách nhiệm ghi representation; nghiệp vụ nên nằm trong service/publisher trước khi response được tạo.
17. **Dùng JSON View làm cơ chế authorization.** Hint codec chỉ điều chỉnh serialization; vẫn phải kiểm tra quyền và DTO.
18. **Quên xử lý lỗi save khi dùng build(save).** Lỗi phải được đưa vào error handling; không nuốt hoặc log rồi trả thành công.
19. **Đặt Location sai hoặc thiếu sau create.** Location phải trỏ tới resource theo contract; không tự ghép URI từ input chưa được validate.
20. **Coi response object đã build là body đã gửi xong.** Server còn phải ghi response qua writer/adapter; lỗi I/O có thể xảy ra trong giai đoạn đó.

## 18. Checklist chọn API

Trước khi viết một handler, hãy trả lời:

- Body đã là một object cụ thể chưa? Nếu có, `bodyValue` thường phù hợp.
- Body là `Mono<T>` hoặc `Flux<T>`? Dùng `body(publisher, elementType)`.
- Mỗi phần tử là kiểu generic? Dùng `ParameterizedTypeReference`.
- Có cần custom body insertion? Cân nhắc `BodyInserter`.
- Response không có body và không chờ tác vụ khác? Dùng `build()`.
- Response không có body nhưng phải chờ thao tác hoàn tất? Dùng `build(Publisher<Void>)`.
- Có cần trả 404 khi repository empty? Xử lý `switchIfEmpty` trước khi tạo response.
- Status và headers có phù hợp HTTP contract? Chọn rõ 200/201/202/204 và Location.
- Body có streaming không? Chọn media type và publisher phù hợp, tránh aggregate vô hạn.
- Có lỗi hoặc cancellation? Giữ mọi tác vụ thuộc cùng publisher chain và quản lý resource đúng lifecycle.
- Có kiểm thử body serialization? Dùng WebTestClient, không chỉ assert `ServerResponse.statusCode`.
- Có nhầm router builder với response builder? Xác nhận kiểu đối tượng trước `build()`.

**Ghi nhớ:** `bodyValue` dành cho object đã có; `body` dành cho publisher phát nội dung; `build()` tạo response không body; `build(Publisher<Void>)` tạo response không body sau khi publisher completion hoàn tất. Cả bốn lựa chọn đều trả về publisher để WebFlux quản lý. Chọn đúng theo **dữ liệu đầu vào, body có cần gửi hay không, và thời điểm response được phép commit**.

## Tài liệu tham khảo

- Spring Framework — [Functional Endpoints (WebFlux.fn): HandlerFunction và ServerResponse](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html).
- Spring Framework — [ServerResponse.BodyBuilder Javadoc: bodyValue, body, hints](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/reactive/function/server/ServerResponse.BodyBuilder.html).
- Spring Framework — [ServerResponse.HeadersBuilder Javadoc: build(), build(Publisher<Void>)](https://docs.spring.io/spring-framework/docs/5.3.20/javadoc-api/org/springframework/web/reactive/function/server/ServerResponse.HeadersBuilder.html).
- Spring Framework — [BodyInserters API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/BodyInserters.html).
- Spring Framework — [WebFlux.fn running a server and response handling](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html).
- Project Reactor — [Mono and Flux reference](https://projectreactor.io/docs/core/release/reference/).
- Project Reactor — [Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html).
