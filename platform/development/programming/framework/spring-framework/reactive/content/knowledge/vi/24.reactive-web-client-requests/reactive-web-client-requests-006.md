# Gửi Publisher bằng body và giữ đúng kiểu phần tử trong Spring WebClient

## 1. Vì sao WebClient có body(Publisher, elementType)?

Spring WebClient là HTTP client reactive. Khi gửi request, ứng dụng thường không có sẵn toàn bộ body dưới dạng một object hoàn chỉnh. Dữ liệu có thể đến từ một `Mono<T>`, `Flux<T>`, một nguồn file, một service khác hoặc một pipeline xử lý bất đồng bộ.

WebClient cho phép truyền trực tiếp một publisher vào request body:

~~~java
Flux<Person> people = loadPeople();

Mono<Void> result = webClient.post()
    .uri("/people/import")
    .contentType(MediaType.APPLICATION_JSON)
    .body(people, Person.class)
    .retrieve()
    .bodyToMono(Void.class);
~~~

Ở đây:

- `people` là nguồn dữ liệu bất đồng bộ.
- Mỗi phần tử phát ra từ publisher có kiểu `Person`.
- `Person.class` cho WebClient biết kiểu của **từng phần tử** cần encode.
- Codec phù hợp chuyển từng giá trị Java thành bytes của HTTP request body.
- WebClient quản lý subscription và việc ghi request; ứng dụng compose publisher trả về thay vì tự gọi `subscribe()`.

Điểm cần hiểu chính xác là `body(publisher, elementType)` không khai báo kiểu của publisher bên ngoài. Nó khai báo kiểu của **giá trị mà publisher phát ra**. Với `Flux<Person>`, element type là `Person`; với `Mono<List<Person>>`, element type là `List<Person>`.

## 2. Các overload body() thường dùng

`WebClient.RequestBodySpec` cung cấp nhiều overload để truyền publisher hoặc một producer có thể chuyển thành publisher:

| API | Đầu vào | Ý nghĩa |
| --- | --- | --- |
| `body(Publisher<T>, Class<T>)` | Publisher và class của phần tử | Gửi publisher, khai báo element type bằng Class |
| `body(Publisher<T>, ParameterizedTypeReference<T>)` | Publisher và generic type reference | Gửi publisher khi kiểu phần tử có generic type |
| `body(Object producer, Class<?> elementClass)` | Publisher hoặc producer được ReactiveAdapterRegistry hỗ trợ | Dùng khi nguồn chưa có kiểu Publisher trực tiếp |
| `body(Object producer, ParameterizedTypeReference<?> elementTypeRef)` | Producer adaptable và generic element type | Giữ generic type cho producer adaptable |
| `body(BodyInserter)` | BodyInserter | Kiểm soát cách ghi body bằng inserter |
| `bodyValue(Object)` | Một giá trị body cụ thể | Gửi một object/value đã có sẵn |

Hai overload được dùng nhiều nhất trong Java là:

~~~java
.body(personMono, Person.class)
~~~

và:

~~~java
.body(personFlux, Person.class)
~~~

Chúng cùng khai báo element type là `Person`; khác biệt nằm ở publisher phát tối đa một phần tử hay nhiều phần tử.

### body(Publisher, Class)

~~~java
Mono<Person> onePerson = findPerson();
Flux<Person> manyPeople = findPeople();

webClient.post()
    .uri("/people/one")
    .contentType(MediaType.APPLICATION_JSON)
    .body(onePerson, Person.class)
    .retrieve()
    .bodyToMono(Void.class);

webClient.post()
    .uri("/people/batch")
    .contentType(MediaType.APPLICATION_JSON)
    .body(manyPeople, Person.class)
    .retrieve()
    .bodyToMono(Void.class);
~~~

`Class<T>` đủ khi element type là một class cụ thể như `Person`, `Order`, `String` hoặc `byte[]`.

### body(Publisher, ParameterizedTypeReference)

Khi mỗi phần tử là một kiểu generic, `Class<T>` không thể biểu diễn đầy đủ type argument do Java type erasure. Dùng `ParameterizedTypeReference<T>`:

~~~java
Flux<ApiEnvelope<Person>> events = loadEvents();

webClient.post()
    .uri("/events")
    .contentType(MediaType.APPLICATION_NDJSON)
    .body(
        events,
        new ParameterizedTypeReference<ApiEnvelope<Person>>() {}
    )
    .retrieve()
    .bodyToMono(Void.class);
~~~

Anonymous subclass của `ParameterizedTypeReference` giữ lại thông tin generic type lúc runtime. WebClient có thể cung cấp type đầy đủ cho codec, ví dụ `ApiEnvelope<Person>`, thay vì chỉ biết raw class `ApiEnvelope`.

## 3. T là kiểu của mỗi phần tử, không phải kiểu publisher

Đây là điểm dễ nhầm khi đọc generic signature:

~~~java
<T, P extends Publisher<T>>
RequestHeadersSpec<?> body(
    P publisher,
    Class<T> elementClass
);
~~~

Trong signature trên:

- `P` là kiểu publisher, ví dụ `Mono<Person>` hoặc `Flux<Person>`.
- `T` là kiểu phần tử được phát ra, ví dụ `Person`.
- `elementClass` mô tả `T`, không mô tả `P`.

Ví dụ:

| Publisher | Kiểu phần tử T | Cách gọi |
| --- | --- | --- |
| `Mono<Person>` | `Person` | `body(mono, Person.class)` |
| `Flux<Person>` | `Person` | `body(flux, Person.class)` |
| `Mono<List<Person>>` | `List<Person>` | `body(mono, new ParameterizedTypeReference<List<Person>>() {})` |
| `Flux<ApiEnvelope<Person>>` | `ApiEnvelope<Person>` | `body(flux, new ParameterizedTypeReference<ApiEnvelope<Person>>() {})` |
| `Flux<Map<String, Person>>` | `Map<String, Person>` | `body(flux, new ParameterizedTypeReference<Map<String, Person>>() {})` |

Ví dụ với `Mono<List<Person>>`:

~~~java
Mono<List<Person>> peopleMono = loadPeopleAsList();

webClient.post()
    .uri("/people/list")
    .contentType(MediaType.APPLICATION_JSON)
    .body(
        peopleMono,
        new ParameterizedTypeReference<List<Person>>() {}
    )
    .retrieve()
    .bodyToMono(Void.class);
~~~

Publisher phát ra **một giá trị** có kiểu `List<Person>`. Type reference phải mô tả `List<Person>`, không phải `Mono<List<Person>>`.

Tương tự, với `Flux<ApiEnvelope<Person>>`, mỗi lần `onNext` phát một envelope. Type reference mô tả `ApiEnvelope<Person>`, không phải `Flux<ApiEnvelope<Person>>`.

## 4. Giữ generic type khi Java type erasure xuất hiện

Java generic type bị xóa phần lớn thông tin type argument khi runtime. Ví dụ, `List<Person>` và `List<Order>` đều có raw class là `List.class`.

Nếu chỉ truyền:

~~~java
.body(envelopes, ApiEnvelope.class)
~~~

codec chỉ nhận được raw type `ApiEnvelope`. Khi cần serialize/deserialize đúng generic structure, dùng:

~~~java
.body(
    envelopes,
    new ParameterizedTypeReference<ApiEnvelope<Person>>() {}
)
~~~

Ví dụ định nghĩa:

~~~java
public record ApiEnvelope<T>(
    String eventType,
    T data
) {}

public record Person(
    String name,
    int age
) {}
~~~

Publisher:

~~~java
Flux<ApiEnvelope<Person>> events = Flux.just(
    new ApiEnvelope<>("created", new Person("An", 30)),
    new ApiEnvelope<>("updated", new Person("Binh", 28))
);
~~~

Gửi request:

~~~java
Mono<Void> sent = webClient.post()
    .uri("/person-events")
    .contentType(MediaType.APPLICATION_NDJSON)
    .body(
        events,
        new ParameterizedTypeReference<ApiEnvelope<Person>>() {}
    )
    .retrieve()
    .bodyToMono(Void.class);
~~~

Type reference cho codec biết mỗi event có cấu trúc `ApiEnvelope<Person>`. Nếu bỏ type argument hoặc dùng raw type, codec có thể chỉ thấy một map/object tổng quát hoặc không có đủ thông tin để xử lý kiểu lồng nhau như mong muốn.

### Một publisher phát ra List khác với một publisher phát ra từng Person

Hai trường hợp sau có body semantics khác nhau:

~~~java
Flux<Person> people = Flux.just(
    new Person("An", 30),
    new Person("Binh", 28)
);

Flux<List<Person>> batches = Flux.just(
    List.of(new Person("An", 30)),
    List.of(new Person("Binh", 28))
);
~~~

- `Flux<Person>`: mỗi phần tử là một Person.
- `Flux<List<Person>>`: mỗi phần tử là một danh sách Person.

Nếu serialize multi-value publisher thành JSON array, trường hợp thứ nhất có dạng array Person; trường hợp thứ hai có dạng array của các array. Hãy chọn element type theo đúng dữ liệu mà mỗi `onNext` phát ra.

## 5. Phân biệt body() với bodyValue()

Hai API có mục đích khác nhau.

### body() nhận publisher

Dùng khi body được tạo bất đồng bộ:

~~~java
Flux<Person> people = findPeople();

webClient.post()
    .uri("/people")
    .contentType(MediaType.APPLICATION_JSON)
    .body(people, Person.class)
    .retrieve()
    .bodyToMono(Void.class);
~~~

WebClient subscribe vào publisher trong quá trình ghi request body. Ứng dụng không cần và không nên tự subscribe để gửi request.

### bodyValue() nhận một giá trị đã có

Dùng khi đã có object hoặc collection:

~~~java
Person person = new Person("An", 30);

webClient.post()
    .uri("/people")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(person)
    .retrieve()
    .bodyToMono(Void.class);
~~~

Với một collection cụ thể có generic type, Spring Framework 6.2 có overload:

~~~java
List<Person> people = List.of(
    new Person("An", 30),
    new Person("Binh", 28)
);

webClient.post()
    .uri("/people/list")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(
        people,
        new ParameterizedTypeReference<List<Person>>() {}
    )
    .retrieve()
    .bodyToMono(Void.class);
~~~

Type reference ở overload `bodyValue(value, typeRef)` mô tả **toàn bộ giá trị body**, vì không có publisher element ở đây.

### Không dùng bodyValue() để truyền Publisher

Đoạn sau là sai:

~~~java
Flux<Person> people = findPeople();

webClient.post()
    .uri("/people")
    .bodyValue(people);
~~~

`bodyValue` yêu cầu một value body cụ thể. Nếu đối tượng là `Publisher` hoặc producer được `ReactiveAdapterRegistry` nhận diện, Spring ném `IllegalArgumentException` và hướng dẫn dùng `body(...)` hoặc BodyInserter tương ứng.

Cách đúng:

~~~java
webClient.post()
    .uri("/people")
    .body(people, Person.class);
~~~

Quy tắc ghi nhớ:

- Có một object/list đã có: `bodyValue(value)`.
- Có `Mono<T>` hoặc `Flux<T>`: `body(publisher, elementType)`.
- Có generic type: dùng `ParameterizedTypeReference`.
- Cần tùy chỉnh cách ghi body: dùng `BodyInserter`.

## 6. body() và BodyInserters

`body(...)` là shortcut tiện lợi trên WebClient. Bên dưới, nó sử dụng `BodyInserter` để ghi body vào request.

Có thể tạo inserter tường minh:

~~~java
Flux<Person> people = findPeople();

Mono<Void> result = webClient.post()
    .uri("/people")
    .contentType(MediaType.APPLICATION_JSON)
    .body(BodyInserters.fromPublisher(people, Person.class))
    .retrieve()
    .bodyToMono(Void.class);
~~~

Các factory thường gặp:

| Factory | Dùng cho |
| --- | --- |
| `BodyInserters.fromPublisher(publisher, Class)` | Publisher có element type là class cụ thể |
| `BodyInserters.fromPublisher(publisher, ParameterizedTypeReference)` | Publisher có generic element type |
| `BodyInserters.fromProducer(producer, Class)` | Producer được ReactiveAdapterRegistry chuyển thành Publisher |
| `BodyInserters.fromProducer(producer, ParameterizedTypeReference)` | Producer adaptable có generic element type |
| `BodyInserters.fromValue(value)` | Một giá trị body cụ thể |
| `BodyInserters.fromResource(resource)` | Gửi Resource, ví dụ file |

Ví dụ generic inserter:

~~~java
Flux<ApiEnvelope<Person>> events = loadEvents();

Mono<Void> result = webClient.post()
    .uri("/person-events")
    .contentType(MediaType.APPLICATION_NDJSON)
    .body(BodyInserters.fromPublisher(
        events,
        new ParameterizedTypeReference<ApiEnvelope<Person>>() {}
    ))
    .retrieve()
    .bodyToMono(Void.class);
~~~

Trong hầu hết trường hợp, `body(publisher, elementType)` ngắn gọn hơn. Dùng BodyInserter khi muốn tái sử dụng logic ghi body hoặc kết hợp với API nhận BodyInserter.

Không dùng `BodyInserters.fromValue(publisher)` để thay thế `fromPublisher`; value inserter cũng dành cho một value cụ thể.

## 7. Content-Type quyết định cách publisher được encode

Element type trả lời câu hỏi **mỗi giá trị Java có kiểu gì**. Header `Content-Type` trả lời câu hỏi **body được gửi theo định dạng nào**. Hai yếu tố này phối hợp để Spring chọn `HttpMessageWriter`/encoder phù hợp.

Ví dụ:

~~~java
.body(people, Person.class)
~~~

chưa nói rõ body phải là JSON array, NDJSON hay định dạng khác. Cần chọn media type theo hợp đồng endpoint:

~~~java
.contentType(MediaType.APPLICATION_JSON)
~~~

hoặc:

~~~java
.contentType(MediaType.APPLICATION_NDJSON)
~~~

Header `Accept` lại mô tả định dạng response client mong muốn, không phải định dạng request body:

~~~java
.accept(MediaType.APPLICATION_JSON)
~~~

Một request có thể gửi NDJSON nhưng nhận JSON response:

~~~java
webClient.post()
    .uri("/people/import")
    .contentType(MediaType.APPLICATION_NDJSON)
    .accept(MediaType.APPLICATION_JSON)
    .body(people, Person.class)
    .retrieve()
    .bodyToMono(ImportSummary.class);
~~~

## 8. Flux<Person> với application/json và application/x-ndjson

Đây là khác biệt quan trọng khi gửi publisher nhiều phần tử.

### application/json

Với Jackson encoder mặc định của Spring WebFlux, một multi-value publisher có media type `application/json` được gom bằng `Flux.collectToList()`, sau đó serialize thành JSON array.

Ví dụ:

~~~java
Flux<Person> people = Flux.just(
    new Person("An", 30),
    new Person("Binh", 28)
);

webClient.post()
    .uri("/people")
    .contentType(MediaType.APPLICATION_JSON)
    .body(people, Person.class);
~~~

Body có hình dạng:

~~~json
[
  {"name":"An","age":30},
  {"name":"Binh","age":28}
]
~~~

Đây là một JSON document dạng array. Encoder mặc định chờ publisher hoàn tất để có collection cần serialize. Nó phù hợp cho batch hữu hạn; không phù hợp cho stream không bao giờ hoàn tất nếu client/server cần một JSON array hoàn chỉnh.

### application/x-ndjson

Với streaming media type như `application/x-ndjson`, Jackson encoder encode, ghi và flush từng giá trị riêng lẻ theo định dạng JSON line-delimited.

~~~java
webClient.post()
    .uri("/people/stream")
    .contentType(MediaType.APPLICATION_NDJSON)
    .body(people, Person.class);
~~~

Body có hình dạng:

~~~text
{"name":"An","age":30}
{"name":"Binh","age":28}
~~~

Mỗi dòng là một JSON document độc lập. Server có thể decode từng record khi dữ liệu đến, không cần đợi toàn bộ publisher hoàn tất.

### So sánh

| Tiêu chí | application/json | application/x-ndjson |
| --- | --- | --- |
| Cấu trúc body | Một JSON document, thường là array | Nhiều JSON document, mỗi record một dòng |
| Multi-value Flux mặc định | Gom thành List rồi serialize | Encode, write và flush từng phần tử |
| Client parse | Parser JSON document/array | Parser theo từng dòng |
| Phù hợp | Batch hữu hạn | Streaming records |
| Publisher vô hạn | Không phù hợp với array cần đóng | Có thể tiếp tục phát record |
| Kết thúc body | Kết thúc JSON document | Kết thúc HTTP stream |

Lưu ý: flush ở encoder không bảo đảm mọi proxy hoặc client hiển thị dữ liệu ngay lập tức. Nếu cần streaming end-to-end, cần kiểm tra cả server transport, proxy và client.

## 9. Mono, Flux, empty publisher và nguồn dữ liệu

### Mono<T>: gửi tối đa một phần tử

~~~java
Mono<Person> person = personService.findById("42");

Mono<Void> sent = webClient.put()
    .uri("/people/42")
    .contentType(MediaType.APPLICATION_JSON)
    .body(person, Person.class)
    .retrieve()
    .bodyToMono(Void.class);
~~~

Nếu publisher hoàn tất rỗng, không có object nào được phát. Điều đó khác với gửi một JSON object có các field rỗng hoặc gửi JSON `null`. Hợp đồng endpoint cần quy định rõ request body có được phép vắng mặt hay không.

### Flux<T>: gửi nhiều phần tử

~~~java
Flux<Person> people = personService.findAll();

Mono<Void> sent = webClient.post()
    .uri("/people/import")
    .contentType(MediaType.APPLICATION_NDJSON)
    .body(people, Person.class)
    .retrieve()
    .bodyToMono(Void.class);
~~~

### Nguồn Iterable hoặc collection

Nếu collection đã có sẵn:

~~~java
List<Person> list = loadList();

Mono<Void> sent = webClient.post()
    .uri("/people")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(
        list,
        new ParameterizedTypeReference<List<Person>>() {}
    )
    .retrieve()
    .bodyToMono(Void.class);
~~~

Nếu muốn phát từng item từ collection:

~~~java
Flux<Person> publisher = Flux.fromIterable(list);

Mono<Void> sent = webClient.post()
    .uri("/people/stream")
    .contentType(MediaType.APPLICATION_NDJSON)
    .body(publisher, Person.class)
    .retrieve()
    .bodyToMono(Void.class);
~~~

Hai cách có cùng dữ liệu nguồn nhưng hợp đồng body khác nhau: một body value là collection JSON, còn một publisher nhiều item được encode theo streaming media type.

## 10. Producer không phải Publisher trực tiếp

Overload:

~~~java
body(Object producer, Class<?> elementClass)
~~~

cho phép nhận một producer mà `ReactiveAdapterRegistry` có thể chuyển thành Publisher. Các reactive type hoặc coroutine type được adapter hỗ trợ có thể dùng qua overload này.

Trong Java với Reactor, `Mono` và `Flux` đã là Publisher, nên dùng overload:

~~~java
.body(publisher, Element.class)
~~~

Nếu tích hợp một reactive library khác hoặc một kiểu producer như Kotlin `Deferred`, hãy kiểm tra nó có adapter phù hợp trong `ReactiveAdapterRegistry` hay không. Không phải mọi object có method `subscribe` hoặc `get` đều tự động được WebClient hiểu là request body publisher.

Nếu producer có generic element type, truyền `ParameterizedTypeReference` tương ứng để codec nhận đúng kiểu phần tử.

## 11. BodyInserter cho form và multipart

WebClient còn hỗ trợ các loại request body có cấu trúc riêng.

### Form URL-encoded

Một `MultiValueMap<String, String>` có thể được gửi như form data:

~~~java
MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
form.add("name", "An");
form.add("role", "developer");

Mono<Void> result = webClient.post()
    .uri("/form")
    .bodyValue(form)
    .retrieve()
    .bodyToMono(Void.class);
~~~

Hoặc dùng:

~~~java
.body(BodyInserters.fromFormData("name", "An")
    .with("role", "developer"))
~~~

### Multipart

Với multipart thông thường, dùng `MultipartBodyBuilder` để tạo các part có kiểu dữ liệu khác nhau:

~~~java
MultipartBodyBuilder builder = new MultipartBodyBuilder();
builder.part("description", "Quarterly report");
builder.part("metadata", new Person("An", 30));
builder.part("file", new FileSystemResource("report.pdf"));

Mono<Void> result = webClient.post()
    .uri("/uploads")
    .body(BodyInserters.fromMultipartData(builder.build()))
    .retrieve()
    .bodyToMono(Void.class);
~~~

Nếu cần stream multipart tuần tự bằng `PartEvent`, có thể truyền `Flux<PartEvent>` với element type `PartEvent.class`. Chọn cách multipart map hay PartEvent theo yêu cầu upload; không gom file lớn vào collection nếu mục tiêu là truyền tuần tự.

## 12. Request publisher chỉ được tiêu thụ theo lifecycle của request

WebClient không gửi body ngay tại dòng gọi `body(...)`. Nó xây dựng request specification; khi exchange được subscribe, WebClient mới ghi request body và subscribe publisher nguồn.

Một chuỗi điển hình:

~~~text
Tạo Mono/Flux nguồn
       |
       v
webClient.post().body(publisher, elementType)
       |
       v
retrieve() / exchangeToMono()
       |
       v
Caller subscribe hoặc framework compose publisher
       |
       v
WebClient subscribe body publisher
       |
       v
Codec encode từng giá trị thành bytes
       |
       v
HTTP client transport ghi request
       |
       v
Nhận response
~~~

Không tự gọi `subscribe()` trên publisher body:

~~~java
// Không nên:
people.subscribe(person -> log.info("{}", person));

return webClient.post()
    .uri("/people")
    .body(people, Person.class)
    .retrieve()
    .bodyToMono(Void.class);
~~~

Đoạn trên có thể subscribe cùng một nguồn hai lần. Với cold publisher, nguồn có thể chạy hai lần; với hot hoặc one-shot publisher, request có thể mất dữ liệu hoặc không còn replay được.

Nếu cần logging, quan sát trong cùng pipeline:

~~~java
Flux<Person> observed = people
    .doOnNext(person -> log.debug("Sending person name={}", person.name()));
~~~

Không log dữ liệu nhạy cảm hoặc toàn bộ body trong production nếu không có lý do và chính sách bảo vệ phù hợp.

## 13. Cold publisher, hot publisher và retry

Nhiều publisher Reactor là cold: mỗi subscription bắt đầu lại quá trình tạo dữ liệu. Ví dụ `Flux.fromIterable(list)` thường có thể được subscribe lại.

Một số nguồn là hot hoặc one-shot:

- Event stream từ message broker.
- Input request body đang được đọc.
- Một stream file hoặc network response chỉ có thể tiêu thụ một lần.
- Publisher được tạo từ callback/event source không replay.

Điều này quan trọng khi dùng retry:

~~~java
webClient.post()
    .uri("/people")
    .body(people, Person.class)
    .retrieve()
    .bodyToMono(Receipt.class)
    .retry(2);
~~~

`retry(2)` có thể subscribe lại publisher request và thực hiện lại HTTP exchange. Nếu body publisher không replay được, lần retry có thể thiếu dữ liệu hoặc thất bại. Nếu server đã xử lý request trước khi connection lỗi, retry còn có thể gửi lặp thao tác nghiệp vụ.

Để retry an toàn:

1. Xác định publisher có thể replay hay không.
2. Dùng nguồn cold có thể tạo lại body khi cần.
3. Thiết kế idempotency key cho thao tác có side effect.
4. Không retry lỗi validation hoặc lỗi 4xx không thể khắc phục.
5. Giới hạn số lần retry, dùng backoff và timeout phù hợp.
6. Với body one-shot, cân nhắc tạo publisher mới cho mỗi attempt hoặc không retry tự động.

## 14. Backpressure, cancellation và lỗi khi ghi request

### Backpressure

Publisher body được tiêu thụ theo Reactive Streams. Demand từ HTTP writer/transport được truyền qua pipeline để điều tiết dữ liệu.

Backpressure không đồng nghĩa toàn bộ request được gửi trong một lần, cũng không có nghĩa mỗi phần tử tương ứng với một packet. Nó giúp điều tiết việc sản xuất/tiêu thụ dữ liệu giữa các tầng.

Tránh:

- `collectList()` với stream lớn không cần aggregation.
- Buffer không giới hạn khi nguồn nhanh hơn network.
- Chuyển toàn bộ publisher thành `byte[]` nếu muốn streaming.
- Tạo concurrency không giới hạn cho công việc trước khi encode.

### Cancellation

Nếu caller hủy subscription hoặc timeout xảy ra, WebClient có thể cancel việc ghi body và nguồn publisher. Nguồn file, socket hoặc listener cần có cleanup đúng lifecycle.

### Error signal

Nếu publisher phát `onError` trong khi ghi request, request body có thể kết thúc bất thường và server nhận được body chưa hoàn chỉnh. Lỗi này khác với lỗi HTTP status do server trả về.

Không nuốt lỗi nguồn bằng `onErrorComplete()` nếu server cần biết request đã bị cắt. Hãy chuyển lỗi hoặc ánh xạ nó theo hợp đồng nghiệp vụ.

## 15. Phân biệt lỗi ghi request với lỗi response

WebClient có hai giai đoạn:

1. Gửi request: encode body và ghi bytes.
2. Nhận response: đọc status, headers và body.

Ví dụ:

~~~java
Mono<ImportReceipt> result = webClient.post()
    .uri("/people/import")
    .contentType(MediaType.APPLICATION_NDJSON)
    .body(people, Person.class)
    .retrieve()
    .bodyToMono(ImportReceipt.class);
~~~

- Lỗi encode hoặc lỗi publisher body xảy ra ở giai đoạn gửi.
- Server trả HTTP 400/500 là response status.
- Lỗi decode response xảy ra khi đọc body response.

Mặc định, `retrieve()` chuyển response 4xx/5xx thành `WebClientResponseException`. Có thể tùy chỉnh:

~~~java
Mono<ImportReceipt> result = webClient.post()
    .uri("/people/import")
    .contentType(MediaType.APPLICATION_NDJSON)
    .body(people, Person.class)
    .retrieve()
    .onStatus(
        status -> status.is4xxClientError(),
        response -> response.createException()
    )
    .bodyToMono(ImportReceipt.class);
~~~

Nếu cần tự quyết định theo từng status và chủ động consume response, dùng `exchangeToMono()`. Dù dùng cách nào, hãy đọc/giải phóng response body đúng lifecycle để tránh giữ connection hoặc buffer.

## 16. Đọc response là chiều ngược lại với gửi body

Không nhầm:

- `body(publisher, elementType)`: gửi request body.
- `bodyToMono(type)`: đọc response body thành một giá trị.
- `bodyToFlux(type)`: đọc response body thành nhiều giá trị.

Ví dụ đọc response JSON array:

~~~java
Flux<Person> responsePeople = webClient.get()
    .uri("/people")
    .retrieve()
    .bodyToFlux(Person.class);
~~~

Ví dụ đọc response object generic:

~~~java
Mono<ApiEnvelope<Person>> response = webClient.get()
    .uri("/person/42")
    .retrieve()
    .bodyToMono(
        new ParameterizedTypeReference<ApiEnvelope<Person>>() {}
    );
~~~

Type reference cũng quan trọng ở chiều response vì Java type erasure vẫn tồn tại. Nếu response là `ApiEnvelope<Person>`, không nên chỉ truyền raw `ApiEnvelope.class` khi cần giữ kiểu của data bên trong.

## 17. Ví dụ hoàn chỉnh Java 17+ với Spring Boot WebFlux

Ví dụ dưới đây minh họa việc gửi một publisher qua WebClient và giữ đúng kiểu phần tử:

- Client nhận `Flux<Person>` dạng NDJSON ở endpoint `/api/people/forward`.
- WebClient chuyển tiếp cùng publisher tới `/api/internal/people`.
- Request downstream dùng `body(people, Person.class)`.
- Server đích nhận `Flux<Person>` và đếm số phần tử.
- Response là một JSON object `BatchReceipt`.

Cấu trúc dự án:

~~~text
webclient-publisher-body/
├── pom.xml
└── src/
    ├── main/java/com/example/webclientbody/
    │   ├── WebClientBodyApplication.java
    │   ├── WebClientConfig.java
    │   └── PeopleController.java
    └── test/java/com/example/webclientbody/
        └── PeopleControllerTest.java
~~~

File `pom.xml` (Spring Boot 3.5.0, Java 17+):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>webclient-publisher-body</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File `src/main/java/com/example/webclientbody/WebClientBodyApplication.java`:

~~~java
package com.example.webclientbody;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebClientBodyApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebClientBodyApplication.class, args);
    }
}
~~~

File `src/main/java/com/example/webclientbody/WebClientConfig.java`:

~~~java
package com.example.webclientbody;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class WebClientConfig {

    @Bean
    WebClient downstreamClient(WebClient.Builder builder) {
        return builder.baseUrl("http://localhost:8080").build();
    }
}
~~~

File `src/main/java/com/example/webclientbody/PeopleController.java`:

~~~java
package com.example.webclientbody;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class PeopleController {

    public record Person(String name, int age) {}

    public record BatchReceipt(long accepted) {}

    private final WebClient downstreamClient;

    public PeopleController(WebClient downstreamClient) {
        this.downstreamClient = downstreamClient;
    }

    // Downstream endpoint: nhận từng Person từ NDJSON.
    @PostMapping(
        path = "/internal/people",
        consumes = MediaType.APPLICATION_NDJSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<BatchReceipt> receive(
            @RequestBody Flux<Person> people) {

        return people.count()
            .map(BatchReceipt::new);
    }

    // Gateway endpoint: nhận publisher rồi gửi tiếp bằng WebClient.body().
    @PostMapping(
        path = "/people/forward",
        consumes = MediaType.APPLICATION_NDJSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<BatchReceipt> forward(
            @RequestBody Flux<Person> people) {

        return downstreamClient.post()
            .uri("/api/internal/people")
            .contentType(MediaType.APPLICATION_NDJSON)
            .accept(MediaType.APPLICATION_JSON)
            .body(people, Person.class)
            .retrieve()
            .bodyToMono(BatchReceipt.class);
    }
}
~~~

Chạy trong thư mục `webclient-publisher-body` với JDK 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

Tạo file `people.ndjson` với nội dung UTF-8:

~~~text
{"name":"An","age":30}
{"name":"Binh","age":28}
~~~

Gửi request bằng cURL:

~~~bash
curl.exe -i -X POST http://localhost:8080/api/people/forward ^
  -H "Content-Type: application/x-ndjson" ^
  -H "Accept: application/json" ^
  --data-binary "@people.ndjson"
~~~

Response dự kiến:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
~~~

Body:

~~~json
{"accepted":2}
~~~

Luồng dữ liệu:

~~~text
people.ndjson
    |
    v
POST /api/people/forward
    |
    v
@RequestBody Flux<Person>
    |
    v
WebClient.body(people, Person.class)
    |
    v
POST /api/internal/people
    |
    v
@RequestBody Flux<Person>
    |
    v
count()
    |
    v
{"accepted":2}
~~~

Đây là demo relay trong cùng ứng dụng để minh họa publisher được truyền qua WebClient. Trong production, downstream thường là service khác; hãy cấu hình base URL, authentication, timeout, connection pool và retry policy phù hợp. Không để endpoint nội bộ không được bảo vệ truy cập công khai chỉ vì demo dùng cùng server.

## 18. Kiểm thử kiểu phần tử bằng WebTestClient

Test dưới đây gửi một publisher typed tới endpoint nhận NDJSON. Dependency `spring-boot-starter-test` đã được khai báo trong pom.

File `src/test/java/com/example/webclientbody/PeopleControllerTest.java`:

~~~java
package com.example.webclientbody;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Flux;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class PeopleControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void sendsTypedPublisherAsNdjson() {
        Flux<PeopleController.Person> people = Flux.just(
            new PeopleController.Person("An", 30),
            new PeopleController.Person("Binh", 28)
        );

        client.post()
            .uri("/api/internal/people")
            .contentType(MediaType.APPLICATION_NDJSON)
            .body(people, PeopleController.Person.class)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .json("{\"accepted\":2}");
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Test xác nhận WebTestClient có thể encode publisher theo element type được khai báo và endpoint decode hai record thành `Flux<Person>`. Đây là test request body ở HTTP integration level; ví dụ relay ở mục trước minh họa WebClient thực hiện cùng thao tác outbound.

## 19. Những lỗi thường gặp

1. **Dùng `bodyValue(flux)`:** sai API. Publisher phải dùng `body(publisher, elementType)`.
2. **Truyền `Flux.class` làm element type:** sai khái niệm. Element type là kiểu mỗi phần tử phát ra, ví dụ `Person.class`.
3. **Dùng raw class cho generic element:** mất thông tin type argument. Dùng `ParameterizedTypeReference`.
4. **Tạo type reference cho cả publisher:** với `Flux<ApiEnvelope<Person>>`, type reference là `ApiEnvelope<Person>`, không phải `Flux<ApiEnvelope<Person>>`.
5. **Nhầm type reference của bodyValue và body:** `bodyValue(value, typeRef)` mô tả toàn bộ value; `body(publisher, typeRef)` mô tả từng publisher element.
6. **Dùng `bodyValue` cho `Mono<List<Person>>`:** đây vẫn là publisher. Dùng `body(mono, new ParameterizedTypeReference<List<Person>>() {})`.
7. **Dùng `body(publisher, List.class)` khi cần `List<Person>`:** raw List không giữ generic Person. Dùng type reference.
8. **Không đặt Content-Type:** codec có thể không chọn được writer phù hợp hoặc server hiểu sai định dạng. Đặt Content-Type theo hợp đồng endpoint.
9. **Nhầm Accept với Content-Type:** Accept mô tả response mong muốn; Content-Type mô tả request body.
10. **Cho rằng Flux + application/json luôn streaming từng item:** Jackson encoder mặc định gom multi-value Flux thành List rồi serialize JSON array.
11. **Dùng application/json cho Flux vô hạn:** encoder mặc định cần publisher hoàn tất để tạo array. Chọn NDJSON hoặc giao thức streaming phù hợp.
12. **Dùng NDJSON nhưng gửi JSON array:** server mong mỗi dòng là một JSON document độc lập. Định dạng hai bên phải thống nhất.
13. **Tự subscribe publisher trước khi gửi:** có thể tiêu thụ nguồn hai lần hoặc làm mất dữ liệu hot/one-shot.
14. **Retry publisher one-shot:** retry có thể không replay được body và có thể gửi lặp thao tác đã thành công ở server.
15. **Không xử lý lỗi nguồn:** publisher phát error giữa request có thể làm body bị cắt; không đổi lỗi đó thành thành công.
16. **Không phân biệt lỗi request với lỗi response:** encode/write failure khác HTTP 4xx/5xx và khác response decode failure.
17. **Set Content-Length cho stream không biết trước kích thước:** header có thể sai. Để transport quản lý framing nếu không biết độ dài.
18. **Dùng collectList không cần thiết:** làm tăng bộ nhớ và trì hoãn encode đối với nguồn lớn.
19. **Không kiểm soát cancellation:** timeout hoặc caller cancel có thể dừng việc gửi body; nguồn có tài nguyên cần cleanup.
20. **Không test generic element type:** code có thể compile nhưng codec serialize thành raw map hoặc cấu trúc sai. Test cả request Content-Type và JSON thực tế.

## 20. Checklist trước khi gửi Publisher

- Nguồn body là một value, `Mono<T>`, `Flux<T>` hay producer adaptable?
- Nếu là publisher, element type chính xác là gì?
- Có cần `Class<T>` hay generic `ParameterizedTypeReference<T>`?
- Đã dùng `body()` thay cho `bodyValue()` khi nguồn là Publisher chưa?
- Nếu body là một List đã có sẵn, có nên gửi bằng `bodyValue(list, typeRef)`?
- Content-Type có khớp với định dạng body không?
- Accept có mô tả đúng định dạng response mong muốn không?
- JSON array hay NDJSON mới phù hợp với hợp đồng client/server?
- Publisher có cold/replayable không nếu có retry?
- Có tránh subscribe/block thủ công không?
- Có xử lý timeout, cancellation và lỗi encode/write không?
- Có kiểm tra response status và decode response body đúng kiểu không?
- Có test với generic type lồng nhau nếu endpoint dùng DTO generic không?

## 21. Câu hỏi tự kiểm tra

**1.** `body(Publisher<T>, Class<T>)` dùng Class để mô tả điều gì? Kiểu của từng phần tử do publisher phát ra.

**2.** Với `Flux<Person>`, element type là gì? `Person.class`.

**3.** Với `Mono<List<Person>>`, element type là gì? `List<Person>`, nên dùng `ParameterizedTypeReference<List<Person>>`.

**4.** Vì sao cần `ParameterizedTypeReference`? Để giữ generic type argument mà Java type erasure không thể biểu diễn bằng raw Class.

**5.** `bodyValue()` có nhận Publisher không? Không; nó ném `IllegalArgumentException` với Publisher/producer được ReactiveAdapterRegistry nhận diện.

**6.** Khác biệt type reference giữa `body` và `bodyValue` là gì? body mô tả kiểu mỗi phần tử publisher; bodyValue mô tả kiểu của giá trị body cụ thể.

**7.** `Flux<Person>` + `application/json` mặc định được encode thế nào? Jackson encoder gom thành List rồi serialize JSON array.

**8.** Muốn gửi record JSON từng dòng nên dùng media type nào? `application/x-ndjson`.

**9.** Có cần gọi `subscribe()` trên publisher body không? Không. WebClient quản lý subscription khi request được thực thi.

**10.** Retry có luôn an toàn với body publisher không? Không. Nguồn có thể one-shot/hot và request có thể đã được server xử lý trước khi lỗi kết nối.

**11.** Content-Type và Accept khác nhau thế nào? Content-Type mô tả request body; Accept mô tả response media type client mong muốn.

**12.** `bodyToFlux(Person.class)` có phải API gửi request body không? Không. Đó là API đọc response body thành Flux.

**Ghi nhớ:** `body(publisher, elementType)` gửi một nguồn reactive và khai báo **kiểu của từng phần tử**. Dùng `Class<T>` cho class cụ thể; dùng `ParameterizedTypeReference<T>` khi element có generic type. `bodyValue(value)` dành cho một giá trị cụ thể và không nhận Publisher. Chọn Content-Type đúng: JSON array cho batch hữu hạn, NDJSON cho record stream; để WebClient quản lý subscription, backpressure, cancellation và xử lý response theo lifecycle.

**Tài liệu chính thức:**
- [Spring Framework 6.2 — WebClient Request Body](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-body.html)
- [WebClient.RequestBodySpec Javadoc — body and bodyValue](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/function/client/WebClient.RequestBodySpec.html)
- [BodyInserters Javadoc — fromPublisher and fromValue](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/function/BodyInserters.html)
- [Spring Framework 6.2 — Reactive Core and Jackson Encoder](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [ParameterizedTypeReference Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/ParameterizedTypeReference.html)
- [Spring Framework 6.2 — WebClient Response Body](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-retrieve.html).