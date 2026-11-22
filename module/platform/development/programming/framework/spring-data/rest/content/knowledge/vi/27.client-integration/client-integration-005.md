# Tạo mới qua Location và quản lý URI của tài nguyên trong Spring Data REST

Khi client tạo một tài nguyên mới qua Spring Data REST, request thường được gửi bằng HTTP POST tới collection resource. Server tạo entity, lưu vào repository và trả response cho biết tài nguyên mới đã được tạo. Header **Location** cung cấp URI của tài nguyên mới để client có thể tiếp tục đọc, cập nhật hoặc xóa đúng item resource.

Client nên lấy URI từ header Location hoặc self link trong representation HAL mà server trả về. Không nên tự ghép URI từ ID hoặc giả định cấu trúc URL của repository, vì base path, path mapping, identifier mapping và cấu hình export có thể thay đổi.

## 1. Luồng tạo tài nguyên bằng POST

Giả sử Spring Data REST công bố repository Person:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Client gửi POST tới collection resource:

~~~http
POST /people
Content-Type: application/json
Accept: application/hal+json

{
  "firstName": "An",
  "lastName": "Nguyen",
  "email": "an@example.com"
}
~~~

Spring Data REST bind JSON vào entity, lưu qua repository và trả response cho client. Khi tạo thành công, response thường sử dụng status **201 Created** cùng header Location trỏ tới item resource mới.

Ví dụ:

~~~http
HTTP/1.1 201 Created
Location: http://localhost:8080/people/42
Content-Type: application/hal+json
~~~

URI trong Location là địa chỉ client có thể dùng để truy cập tài nguyên vừa tạo. Giá trị /people/42 chỉ là ví dụ; ID và đường dẫn thực tế do ứng dụng cùng Spring Data REST quyết định.

## 2. Location là URI của tài nguyên mới

Header Location có ý nghĩa đặc biệt trong response tạo tài nguyên. Với status 201 Created, nó xác định tài nguyên chính được tạo bởi request.

Ví dụ:

~~~http
Location: https://api.example.com/people/42
~~~

Client có thể lưu URI này làm định danh của tài nguyên vừa tạo và dùng nó cho các request tiếp theo:

~~~http
GET /people/42
Accept: application/hal+json
~~~

~~~http
PATCH /people/42
Content-Type: application/json

{
  "lastName": "Tran"
}
~~~

~~~http
DELETE /people/42
~~~

Trong ứng dụng thực tế, client nên dùng nguyên URI nhận được từ Location hoặc resolve URI tương đối theo request URI. Không nên chỉ lấy số 42 rồi nối với một base URL tự đoán.

### Location có thể là URI tương đối

HTTP cho phép Location chứa URI-reference. Nếu giá trị không phải absolute URI, client cần resolve nó dựa trên URI của request theo quy tắc URI resolution.

Ví dụ request được gửi tới:

~~~text
https://api.example.com/v1/people
~~~

và response có:

~~~http
Location: /v1/people/42
~~~

Client resolve Location thành:

~~~text
https://api.example.com/v1/people/42
~~~

Dùng URI builder hoặc thư viện HTTP có hỗ trợ URI resolution để xử lý đúng scheme, host, port, context path và dấu gạch chéo.

## 3. Đọc Location trong Java client

Với Spring RestClient, client có thể nhận response entity và đọc header:

~~~java
RestClient restClient = RestClient.create();

ResponseEntity<Void> response = restClient.post()
    .uri("https://api.example.com/people")
    .contentType(MediaType.APPLICATION_JSON)
    .body(personRequest)
    .retrieve()
    .toBodilessEntity();

URI location = response.getHeaders().getLocation();

if (location == null) {
    throw new IllegalStateException(
        "Create response did not contain a Location header"
    );
}
~~~

Nếu cần response body, dùng kiểu body phù hợp với representation server trả về:

~~~java
ResponseEntity<PersonRepresentation> response =
    restClient.post()
        .uri("https://api.example.com/people")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaTypes.HAL_JSON)
        .body(personRequest)
        .retrieve()
        .toEntity(PersonRepresentation.class);

URI location = response.getHeaders().getLocation();
~~~

Kiểu Java nhận body phải phù hợp với HAL representation và cấu hình Jackson/HATEOAS của client. Nếu chỉ cần URI để tiếp tục làm việc, có thể đọc Location mà không cần deserialize toàn bộ body.

Với WebClient, Location có thể được đọc từ response headers:

~~~java
Mono<URI> createdLocation = webClient.post()
    .uri("/people")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(personRequest)
    .exchangeToMono(response -> {
        if (response.statusCode().is2xxSuccessful()) {
            URI location = response.headers()
                .asHttpHeaders()
                .getLocation();

            if (location == null) {
                return Mono.error(
                    new IllegalStateException("Missing Location header")
                );
            }

            return Mono.just(location);
        }

        return response.createException()
            .flatMap(Mono::error);
    });
~~~

Đoạn code minh họa việc đọc header; trong ứng dụng cần xử lý status code cụ thể theo hợp đồng API và không coi mọi response 2xx là tài nguyên đã được tạo.

## 4. Dùng Location để đọc tài nguyên vừa tạo

Sau khi nhận Location, client có thể GET URI đó để lấy representation mới nhất:

~~~java
PersonRepresentation created =
    restClient.get()
        .uri(location)
        .accept(MediaTypes.HAL_JSON)
        .retrieve()
        .body(PersonRepresentation.class);
~~~

Cách này hữu ích khi:

- Response POST không trả body.
- Client cần representation đầy đủ sau khi server áp dụng default value hoặc logic nghiệp vụ.
- Server tạo ID, timestamp hoặc thuộc tính dẫn xuất.
- Client muốn lấy các association link và metadata do Spring Data REST công bố.

Không cần giả định body POST luôn có đủ dữ liệu để xây dựng client state. Location cho biết địa chỉ item resource; GET tiếp theo cho phép client đọc representation theo hợp đồng hiện tại.

## 5. Location và self link trong HAL

Spring Data REST thường trả representation theo HAL. Trong response, _links.self.href cũng chỉ tới item resource.

Ví dụ:

~~~http
HTTP/1.1 201 Created
Location: http://localhost:8080/people/42
Content-Type: application/hal+json
~~~

~~~json
{
  "firstName": "An",
  "lastName": "Nguyen",
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/42"
    },
    "person": {
      "href": "http://localhost:8080/people/42"
    }
  }
}
~~~

Client có thể sử dụng self link trong body hoặc Location trong header để định vị item resource. Nếu cả hai cùng xuất hiện, chúng thường trỏ tới cùng tài nguyên chính; hãy dùng URI mà server công bố thay vì tự dựng một URI khác.

HAL link còn có thể chứa các relation như address, orders hoặc profile. Những link đó cho phép client điều hướng đến association hoặc metadata liên quan sau khi đã tạo entity.

### Location và self link có vai trò gần nhau nhưng nằm ở hai nơi khác nhau

| Thành phần | Vị trí | Vai trò |
|---|---|---|
| Location | HTTP response header | URI của tài nguyên được tạo bởi request |
| _links.self.href | HAL response body | URI để truy cập resource hiện tại |
| _links.<rel>.href | HAL response body | URI của tài nguyên hoặc chức năng liên quan |

Client có thể dùng Location để lưu URI ngay cả khi không deserialize HAL. Nếu cần điều hướng theo hypermedia, đọc self link và các relation trong body.

## 6. Phân biệt Location với Content-Location

Hai header có tên gần nhau nhưng ý nghĩa khác nhau:

- **Location** trong response 201 xác định tài nguyên được tạo.
- **Content-Location** xác định URI của representation được gửi trong message body, theo semantics HTTP tương ứng.

Ví dụ response tạo tài nguyên:

~~~http
HTTP/1.1 201 Created
Location: https://api.example.com/people/42
Content-Type: application/hal+json
~~~

Location là header client cần dùng để định vị tài nguyên mới.

Không nên lấy Content-Location thay cho Location chỉ vì response có body. Hãy dựa trên semantics HTTP và hợp đồng API mà server công bố.

Location cũng có thể xuất hiện trong response redirect 3xx với vai trò URI đích của redirect. Client cần xét status code để hiểu ý nghĩa header trong từng trường hợp.

## 7. Body của response tạo tài nguyên

Spring Data REST có thể được cấu hình để trả hoặc không trả representation body sau POST. Cấu hình RepositoryRestConfiguration có các tùy chọn liên quan đến việc trả body khi create và update.

Vì vậy, client không nên phụ thuộc vào giả định rằng POST luôn có body HAL hoặc luôn chỉ có header Location. Hãy xác định cấu hình API và xử lý cả hai trường hợp:

- Có Location và có body: client có thể dùng body ngay hoặc GET lại URI.
- Có Location nhưng body rỗng: client GET URI để lấy representation.
- Body có self link: client có thể dùng link đó làm URI của resource.
- Thiếu cả Location và self link: response không cung cấp đủ thông tin để client xác định URI mới theo quy trình thông thường; cần xử lý theo hợp đồng API hoặc báo lỗi.

Khi thay đổi cấu hình return body, hãy kiểm tra client hiện có vì chúng có thể phụ thuộc vào status, header hoặc body của response POST.

## 8. CORS và quyền đọc Location trong trình duyệt

Một ứng dụng chạy trong browser có thể gửi POST tới API ở origin khác. Browser áp dụng CORS và không cho JavaScript đọc mọi response header theo mặc định.

Để JavaScript đọc được Location, server có thể cần expose header:

~~~http
Access-Control-Expose-Headers: Location
~~~

Ví dụ cấu hình Spring MVC/Spring Security cần cho phép origin và expose header theo policy của ứng dụng. Chỉ thêm Access-Control-Expose-Headers không thay thế Access-Control-Allow-Origin, preflight handling hoặc authorization.

Nếu browser nhận response 201 nhưng response.headers.get("Location") trả về null, hãy kiểm tra CORS expose header trong response thực tế trước khi kết luận server không gửi Location.

Ví dụ JavaScript:

~~~javascript
const response = await fetch("https://api.example.com/people", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Accept": "application/hal+json"
  },
  body: JSON.stringify({
    firstName: "An",
    lastName: "Nguyen"
  })
});

const location = response.headers.get("Location");

if (!response.ok) {
  throw new Error("Create request failed");
}

if (!location) {
  throw new Error("Location header is not available");
}

const createdResponse = await fetch(location, {
  headers: { "Accept": "application/hal+json" }
});
~~~

Đoạn code giả định server đã cấu hình CORS cho origin của client và expose Location. Client production cũng cần xử lý credential, lỗi mạng, redirect và status code cụ thể.

## 9. Quản lý URI sau khi tạo

Sau khi tạo thành công, client nên lưu URI do server cung cấp cùng dữ liệu client-side tương ứng.

Một số nguyên tắc hữu ích:

- Lưu URI như một định danh tài nguyên, không chỉ lưu ID nếu API có thể dùng URI tùy chỉnh.
- Dùng URI nhận từ Location hoặc self link cho request tiếp theo.
- Không nối base URL và ID bằng chuỗi nếu server đã cung cấp link.
- Khi chuyển môi trường hoặc đổi base path, để client khám phá link mới từ response.
- Không giả định URI sẽ không đổi nếu API có hỗ trợ redirect hoặc URI migration.
- Kiểm tra scheme và host trước khi client tin cậy một URI từ server ngoài phạm vi tin cậy của ứng dụng.

Với ứng dụng nhiều tenant hoặc nhiều API host, URI có thể mang thông tin định tuyến. Lưu URI giúp client không cần tự tái tạo quy tắc routing.

## 10. Retry POST và tránh tạo trùng

POST tạo tài nguyên thường không idempotent. Nếu client gửi POST nhưng timeout trước khi nhận response, client không biết chắc server đã tạo entity hay chưa.

Không nên tự động gửi lại POST một cách mù quáng. Có thể xảy ra trường hợp request đầu đã tạo tài nguyên, nhưng response bị mất; request thứ hai tạo thêm bản ghi khác.

Một số cách xử lý:

- Nếu nhận được response, dùng Location để xác định resource đã tạo.
- Nếu timeout, kiểm tra trạng thái bằng một business key hoặc request correlation identifier nếu API hỗ trợ.
- Với nghiệp vụ cần retry an toàn, thiết kế idempotency key và lưu kết quả xử lý ở server.
- Đặt unique constraint cho business key nếu domain yêu cầu không tạo trùng.
- Thiết kế client retry theo hợp đồng API thay vì suy luận từ status code hoặc network exception.

Location giúp quản lý URI sau khi nhận response thành công; nó không tự giải quyết tình huống response bị mất trước khi client đọc được header.

## 11. Tạo tài nguyên qua custom controller

Nếu ứng dụng dùng custom controller thay cho repository endpoint tiêu chuẩn, controller cần chủ động trả status và Location đúng semantics.

Ví dụ:

~~~java
@PostMapping("/people")
public ResponseEntity<Person> create(@RequestBody PersonRequest request) {
    Person saved = personService.create(request);

    URI location = ServletUriComponentsBuilder
        .fromCurrentRequest()
        .path("/{id}")
        .buildAndExpand(saved.getId())
        .toUri();

    return ResponseEntity.created(location).body(saved);
}
~~~

ResponseEntity.created(location) tạo response 201 Created và thiết lập Location. URI được xây dựng dựa trên request hiện tại và ID entity đã lưu.

Với custom endpoint nằm trong Spring Data REST, cần xem xét dùng @RepositoryRestController và các assembler/representation phù hợp để response tuân theo hypermedia contract của API. Nếu controller trả DTO hoặc representation riêng, hãy định nghĩa rõ URI và các link mà client được phép sử dụng.

Không xây dựng Location từ ID trước khi entity được lưu nếu ID được database sinh. Hãy tạo entity, lưu thành công, sau đó lấy identifier và tạo URI.

## 12. Xử lý lỗi và response không như mong đợi

Client nên phân biệt các tình huống:

- **201 Created:** tài nguyên mới đã được tạo; đọc Location nếu có.
- **200 OK hoặc 204 No Content:** không phải response tạo resource tiêu chuẩn 201; kiểm tra hợp đồng custom API.
- **400 Bad Request:** body hoặc dữ liệu đầu vào không hợp lệ.
- **401/403:** client chưa xác thực hoặc không có quyền tạo.
- **409 Conflict:** có thể xảy ra khi business key hoặc constraint bị xung đột.
- **415 Unsupported Media Type:** Content-Type không được endpoint hỗ trợ.
- **5xx hoặc timeout:** kết quả có thể chưa rõ nếu server đã xử lý nhưng response không tới client.

Không coi mọi status 2xx là có Location. Kiểm tra status code và header theo đúng thao tác, đồng thời xử lý trường hợp response body rỗng.

## 13. Kiểm thử Location và URI lifecycle

Nên kiểm thử qua HTTP integration test để xác nhận server trả URI đúng và client có thể sử dụng URI đó.

Các trường hợp cần kiểm tra:

1. POST dữ liệu hợp lệ tới collection resource.
2. Xác nhận status là 201 Created theo hợp đồng API.
3. Xác nhận response có Location trỏ tới item resource mới.
4. Nếu body có HAL, xác nhận _links.self.href phù hợp với Location.
5. GET URI từ Location và xác nhận entity vừa tạo có thể được đọc.
6. Kiểm tra response khi cấu hình không trả body.
7. Kiểm tra base path, context path, reverse proxy và URI tương đối nếu ứng dụng có cấu hình đó.
8. Kiểm tra CORS để browser client đọc được Location.
9. Kiểm tra trường hợp thiếu Location hoặc body không có self link.
10. Kiểm tra timeout và retry để tránh tạo trùng tài nguyên.
11. Kiểm tra custom controller trả ResponseEntity.created(location) tạo header đúng.
12. Kiểm tra client không tự ghép URI từ ID khi server đã công bố URI chính thức.

## 14. Quy trình triển khai

1. Xác định collection resource mà client dùng để POST.
2. Gửi request với Content-Type và Accept phù hợp.
3. Kiểm tra status code tạo tài nguyên theo hợp đồng API.
4. Đọc header Location và lưu URI mới.
5. Nếu body có HAL, đọc self link và các relation cần thiết.
6. Nếu body rỗng hoặc client cần dữ liệu mới nhất, GET URI từ Location.
7. Nếu client chạy trong browser, cấu hình CORS expose Location.
8. Xây dựng retry/idempotency policy cho trường hợp timeout.
9. Kiểm thử status, Location, self link và request GET tiếp theo.

## 15. Những điểm cần ghi nhớ

- POST tới collection resource là cách thông dụng để tạo entity qua Spring Data REST.
- Response tạo thành công thường dùng 201 Created và header Location trỏ tới item resource mới.
- Client nên dùng Location hoặc HAL self link thay vì tự ghép URL từ ID.
- Location có thể là URI tương đối và cần được resolve theo URI của request.
- Content-Location và Location có semantics khác nhau.
- Response body sau POST phụ thuộc cấu hình; client cần hỗ trợ trường hợp body rỗng.
- Browser client cần server expose Location qua CORS để JavaScript đọc được header.
- POST thường không idempotent; timeout và retry có thể tạo bản ghi trùng nếu API không có idempotency mechanism.
- Custom controller có thể dùng ResponseEntity.created(location) để trả 201 và Location.
- Kiểm thử cả header, HAL self link và khả năng GET lại tài nguyên bằng URI nhận được.

## Nguồn tham khảo

- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — RepositoryRestConfiguration API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/config/RepositoryRestConfiguration.html)
- [Spring Framework — ResponseEntity API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ResponseEntity.html)
- [HTTP Semantics — RFC 9110, 201 Created and Location](https://www.rfc-editor.org/rfc/rfc9110.html)
- [MDN — Access-Control-Expose-Headers](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Access-Control-Expose-Headers)
