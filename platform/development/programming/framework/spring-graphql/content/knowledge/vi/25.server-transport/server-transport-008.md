# application/graphql-response+json

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích ý nghĩa của media type `application/graphql-response+json`.
- Phân biệt media type của request với media type của response.
- Dùng header `Accept` để yêu cầu GraphQL response theo định dạng chuyên biệt.
- Hiểu khác biệt giữa `application/graphql-response+json` và `application/json` legacy.
- Phân biệt GraphQL request error, execution error và HTTP transport error.
- Đọc HTTP status code cùng GraphQL response body một cách chính xác.
- Hiểu cách Spring for GraphQL hỗ trợ media type này và những điểm cần kiểm tra theo phiên bản.
- Kiểm thử content negotiation, response body và HTTP status bằng `WebTestClient` và `HttpGraphQlTester`.

## 1. Vì sao cần application/graphql-response+json?

GraphQL định nghĩa cấu trúc request và response, nhưng bản thân GraphQL không bắt buộc phải dùng HTTP. Khi triển khai qua HTTP, server cần một media type để client nhận biết nội dung response là kết quả GraphQL.

Trước đây, nhiều GraphQL server dùng `application/json` cho response. JSON này có thể chứa GraphQL result, nhưng client không thể chỉ dựa vào media type để phân biệt nó với một JSON error do proxy, API gateway hoặc middleware tạo ra.

Ví dụ, client gửi một GraphQL query nhưng gateway trả về JSON:

~~~json
{
  "error": "upstream unavailable"
}
~~~

Nếu cả GraphQL response và lỗi từ hạ tầng đều dùng `application/json`, client cần thêm logic để đoán nội dung nhận được có phải GraphQL response hay không.

Media type `application/graphql-response+json` giải quyết vấn đề nhận diện này. Khi response có:

~~~http
Content-Type: application/graphql-response+json
~~~

client biết body được khai báo là GraphQL-over-HTTP response và có thể xử lý theo cấu trúc GraphQL, kể cả khi HTTP status không thuộc nhóm 2xx.

Media type này là JSON response chuyên biệt cho GraphQL. Nó không tạo ra một cấu trúc body hoàn toàn mới; điểm quan trọng là ý nghĩa của response media type và cách kết hợp nó với HTTP status code.

## 2. Đây là media type của response, không phải request

Cần phân biệt rõ hai header:

- `Content-Type` mô tả định dạng body client gửi lên.
- `Accept` mô tả định dạng response client muốn nhận.

Với HTTP GraphQL JSON thông thường, request vẫn dùng:

~~~http
Content-Type: application/json
~~~

Còn client yêu cầu response chuyên biệt bằng:

~~~http
Accept: application/graphql-response+json
~~~

Ví dụ một request đầy đủ:

~~~http
POST /graphql HTTP/1.1
Content-Type: application/json
Accept: application/graphql-response+json

{
  "query": "query BookById($id: ID!) { book(id: $id) { id title } }",
  "operationName": "BookById",
  "variables": {
    "id": "b-01"
  }
}
~~~

Không gửi `Content-Type: application/graphql-response+json` chỉ vì muốn nhận response có media type đó. Theo GraphQL-over-HTTP, `application/graphql-response+json` là media type của JSON response; request body JSON tiêu chuẩn vẫn được gửi bằng `application/json`.

## 3. Yêu cầu response bằng Accept

Client cho server biết các response media type được chấp nhận thông qua header `Accept`.

Để ưu tiên media type mới và vẫn tương thích với server/client legacy, có thể gửi:

~~~http
Accept: application/graphql-response+json, application/json;q=0.9
~~~

Ý nghĩa:

- `application/graphql-response+json` có độ ưu tiên mặc định cao nhất.
- `application/json;q=0.9` là lựa chọn tương thích có độ ưu tiên thấp hơn.
- Server chọn media type phù hợp theo content negotiation và khả năng hỗ trợ.

Nếu client chỉ chấp nhận media type mới:

~~~http
Accept: application/graphql-response+json
~~~

server cần trả media type đó nếu hỗ trợ. Nếu không có response media type nào được client chấp nhận, server có thể từ chối content negotiation bằng `406 Not Acceptable` theo quy tắc GraphQL-over-HTTP.

Nếu client không gửi `Accept`, server có thể chọn media type mặc định theo triển khai. Để hành vi giữa các môi trường rõ ràng, client nên gửi `Accept` một cách tường minh.

## 4. Cấu trúc GraphQL response vẫn là JSON

Response với `application/graphql-response+json` vẫn sử dụng cấu trúc GraphQL result quen thuộc.

Khi operation thực thi thành công:

~~~http
HTTP/1.1 200 OK
Content-Type: application/graphql-response+json; charset=utf-8
~~~

~~~json
{
  "data": {
    "book": {
      "id": "b-01",
      "title": "GraphQL in Practice"
    }
  }
}
~~~

Khi một field thực thi lỗi nhưng GraphQL vẫn tạo được kết quả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/graphql-response+json; charset=utf-8
~~~

~~~json
{
  "data": {
    "book": null
  },
  "errors": [
    {
      "message": "Book was not found",
      "path": ["book"],
      "extensions": {
        "code": "BOOK_NOT_FOUND"
      }
    }
  ]
}
~~~

Khi GraphQL không thể bắt đầu execution do document không hợp lệ, response có thể chỉ có errors và không có key `data`:

~~~http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/graphql-response+json; charset=utf-8
~~~

~~~json
{
  "errors": [
    {
      "message": "Cannot query field 'unknownField' on type 'Query'."
    }
  ]
}
~~~

Cấu trúc body giúp client phân biệt request error với execution result. HTTP status bổ sung thông tin ở tầng transport và observability.

## 5. Khác biệt giữa request error và execution error

Để hiểu media type này, cần phân biệt hai nhóm lỗi theo GraphQL execution.

### Request error

Request error ngăn GraphQL thực thi operation. Ví dụ:

- GraphQL document không parse được.
- Field không tồn tại trong schema.
- Argument không đúng kiểu.
- Variable không thể coercion theo khai báo.
- Không xác định được operation cần thực thi.

Trong trường hợp này, GraphQL response error result không có key `data`. Với `application/graphql-response+json`, GraphQL-over-HTTP specification hướng dẫn dùng HTTP status 4xx hoặc 5xx phù hợp với nguyên nhân.

Ví dụ:

| Nguyên nhân | HTTP status thường dùng theo spec |
|---|---:|
| JSON request body sai cú pháp | 400 |
| GraphQL document parse thất bại | 400 |
| GraphQL validation thất bại | 422 |
| Variable coercion thất bại | 422 |
| Operation không xác định được | 422 |
| Request dùng Content-Type không hỗ trợ | 415 |
| Accept không có media type phù hợp | 406 |
| Client chưa xác thực | 401 |
| Client không có quyền gọi endpoint | 403 |

Đây là hướng dẫn của GraphQL-over-HTTP specification; ứng dụng cần kiểm tra hành vi thực tế của server và phiên bản framework.

### Execution error

Execution error phát sinh sau khi operation đã qua parse, validation và bắt đầu thực thi. Ví dụ:

- Resolver không tìm thấy dữ liệu.
- Database hoặc service downstream gặp lỗi.
- Một field bị từ chối bởi authorization.
- Custom scalar không serialize được giá trị trả về.

GraphQL có thể trả một phần dữ liệu cùng errors:

~~~json
{
  "data": {
    "book": {
      "id": "b-01",
      "title": "GraphQL in Practice",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Author is not available",
      "path": ["book", "author"]
    }
  ]
}
~~~

Đây vẫn là một GraphQL execution result. Client nên đọc `data` và `errors`, không xem mọi response có errors là request thất bại hoàn toàn.

## 6. Media type mới thay đổi cách dùng HTTP status code

Lợi ích quan trọng của `application/graphql-response+json` là server có thể dùng HTTP status code có ý nghĩa hơn.

Theo GraphQL-over-HTTP September 2026 Edition:

| GraphQL result | Hướng dẫn status code |
|---|---|
| Có `data` khác null, không có errors | SHOULD trả 200 |
| Có `data` khác null và có errors | MUST trả 2xx |
| Có cả key `data` (kể cả null) và `errors` | SHOULD trả 294 Partial Success |
| Không có key `data` vì request error | Appropriate 4xx hoặc 5xx |
| Không thể tạo GraphQL-over-HTTP response hợp lệ | Appropriate 4xx hoặc 5xx; không dùng media type GraphQL response |

`294 Partial Success` là status code được bản specification này khuyến nghị cho trường hợp GraphQL có cả data và errors. Đây là mã tùy chỉnh được nêu trong specification, chưa phải status code HTTP tiêu chuẩn được đăng ký phổ biến. Hạ tầng proxy, gateway, monitoring và client cần được kiểm tra trước khi dựa vào mã này.

Điều quan trọng đối với client là: khi nhận `application/graphql-response+json`, hãy xử lý body như một GraphQL response hợp lệ bất kể status code. Status code hữu ích cho logging, metrics, gateway và quan sát vận hành; body mới cho biết chi tiết GraphQL result.

## 7. So sánh với application/json legacy

`application/json` vẫn được nhiều hệ thống hỗ trợ vì lý do tương thích. Tuy nhiên, hành vi HTTP status truyền thống có thể khác media type mới.

| Tiêu chí | `application/json` legacy | `application/graphql-response+json` |
|---|---|---|
| Mục đích | JSON response kiểu cũ | Media type chuyên biệt cho GraphQL response |
| Nhận diện GraphQL response | Không rõ chỉ từ media type | Rõ ràng qua Content-Type |
| Parse/validation error | Nhiều server cũ trả 200 | Có thể dùng 4xx |
| Execution error | Thường 200 cùng errors | Có thể dùng status theo GraphQL-over-HTTP |
| Tương thích proxy/monitoring | Khó phân biệt GraphQL error với intermediary error | Dễ nhận diện GraphQL response hơn |
| Khuyến nghị | Dùng khi cần client legacy | Ưu tiên cho client mới |

Không nên kết luận rằng mọi server dùng `application/json` đều có hành vi giống hệt nhau. Bảng này mô tả khác biệt mục tiêu và hành vi tương thích thường gặp; status code cuối cùng phụ thuộc triển khai.

## 8. Spring for GraphQL hỗ trợ media type này

Spring for GraphQL hỗ trợ `application/graphql-response+json` trong HTTP transport. Theo tài liệu Server Transports hiện hành:

- HTTP request body mặc định dùng `application/json`.
- Client có thể yêu cầu `application/graphql-response+json` qua `Accept`.
- Nếu client không thể hiện preference, Spring chọn media type mới làm response content type.
- Client vẫn có thể yêu cầu `application/json` để nhận legacy HTTP behavior.
- Khi dùng media type mới, lỗi parse hoặc validation của GraphQL document được trả với HTTP 4xx.
- Với `application/json` legacy, các lỗi parse/validation này vẫn trả HTTP 200.
- Sau khi GraphQL request đã validate thành công, tài liệu Spring mô tả HTTP status là 200, kể cả khi execution có errors; errors nằm trong phần `errors` của response.

Điểm cuối cần được chú ý khi so sánh với GraphQL-over-HTTP September 2026 Edition. Bản specification mới khuyến nghị status 294 cho response có cả `data` và `errors`, trong khi tài liệu Spring for GraphQL 2.1.0 hiện hành mô tả status 200 cho mọi execution result sau validation. Vì vậy, không nên giả định Spring tự động trả 294 chỉ vì client yêu cầu media type mới.

Nếu cần tuân thủ chính xác status mapping của một phiên bản GraphQL-over-HTTP cụ thể, hãy kiểm tra phiên bản Spring for GraphQL đang dùng, kiểm thử endpoint và xem có cần tùy chỉnh HTTP handler hay không. Không thay đổi status code một cách tùy tiện nếu client, proxy hoặc API gateway chưa được kiểm tra tương thích.

## 9. Gửi request tới Spring endpoint bằng curl

Ví dụ yêu cầu response media type mới:

~~~bash
curl -i http://localhost:8080/graphql \
  -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/graphql-response+json" \
  -d '{
    "query": "query BookById($id: ID!) { book(id: $id) { id title } }",
    "operationName": "BookById",
    "variables": {
      "id": "b-01"
    }
  }'
~~~

Các điểm cần kiểm tra trong response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/graphql-response+json
~~~

- Status code được trả theo hành vi của phiên bản Spring đang chạy.
- `Content-Type` phải tương thích với media type client yêu cầu.
- Body phải có cấu trúc GraphQL result.
- Nếu có errors, kiểm tra thêm `path` và `extensions`.

Để kiểm tra legacy behavior:

~~~bash
curl -i http://localhost:8080/graphql \
  -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "query": "{ unknownField }"
  }'
~~~

Với Spring for GraphQL theo tài liệu hiện hành, lỗi parse/validation trong trường hợp legacy `application/json` vẫn được trả với status 200. Điều này là một trong những lý do client mới nên ưu tiên media type chuyên biệt.

## 10. Content negotiation khi client hỗ trợ cả hai media type

Một client có thể cần tương thích với server cũ trong khi vẫn ưu tiên response media type mới.

Ví dụ:

~~~http
Accept: application/graphql-response+json, application/json;q=0.9
~~~

Các trường hợp cần kiểm thử:

| Accept | Mục tiêu |
|---|---|
| `application/graphql-response+json` | Chỉ chấp nhận response media type mới |
| `application/json` | Yêu cầu legacy behavior |
| `application/graphql-response+json, application/json;q=0.9` | Ưu tiên mới, fallback legacy |
| `application/xml` | Không có media type GraphQL JSON được chấp nhận |

Khi client và server không thống nhất media type, content negotiation có thể thất bại. Với GraphQL-over-HTTP, `406 Not Acceptable` là status phù hợp khi server không thể đáp ứng Accept header theo chính sách triển khai.

Nếu client dùng fallback, cần kiểm tra response `Content-Type` thực tế thay vì giả định server luôn chọn media type đầu tiên.

## 11. Client cần xử lý response như thế nào?

Với media type mới, client không nên dừng xử lý chỉ vì `response.ok` là false. Một GraphQL request error có thể được biểu diễn bằng HTTP 4xx cùng body GraphQL hợp lệ.

Một chiến lược xử lý tổng quát:

1. Đọc HTTP status và `Content-Type`.
2. Nếu `Content-Type` là `application/graphql-response+json`, parse body theo GraphQL response format kể cả khi status là 4xx.
3. Kiểm tra key `data` để biết operation có tạo execution result hay không.
4. Kiểm tra `errors` để xử lý lỗi request hoặc lỗi từng field.
5. Dùng `path` để xác định field gây lỗi.
6. Dùng mã trong `extensions` nếu server công bố error code ổn định.
7. Nếu response không có media type GraphQL, xử lý như HTTP/intermediary error và không giả định body là GraphQL result.

Ví dụ JavaScript ở client:

~~~javascript
const response = await fetch("/graphql", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Accept": "application/graphql-response+json, application/json;q=0.9"
  },
  body: JSON.stringify({
    query: "query { book(id: \"b-01\") { id title } }"
  })
});

const contentType = response.headers.get("Content-Type") ?? "";

if (contentType.includes("application/graphql-response+json")) {
  const result = await response.json();

  if (result.errors?.length) {
    console.error("GraphQL errors:", result.errors);
  }

  if (result.data !== undefined) {
    renderBook(result.data);
  }
} else {
  const body = await response.text();
  throw new Error(
    `HTTP ${response.status}: ${body}`
  );
}
~~~

Đây là ví dụ minh họa luồng xử lý. Trong ứng dụng thật, cần xử lý cả trường hợp body rỗng, JSON không hợp lệ, network error và media type có tham số như `charset=utf-8`. Nên parse media type thay vì chỉ so sánh chuỗi một cách cứng nhắc.

## 12. Kiểm thử media type với WebTestClient

`HttpGraphQlTester` hữu ích để kiểm tra nội dung GraphQL response. Khi cần xác minh chính xác HTTP status và header, có thể dùng `WebTestClient` trực tiếp.

Ví dụ kiểm thử thành công:

~~~java
@Test
void shouldReturnGraphQlResponseJson() {
    webTestClient.post()
            .uri("/graphql")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.parseMediaType(
                    "application/graphql-response+json"))
            .bodyValue(Map.of(
                    "query", """
                            { book(id: "b-01") { id title } }
                            """))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                    MediaType.parseMediaType(
                            "application/graphql-response+json"))
            .expectBody()
            .jsonPath("$.data.book.id").isEqualTo("b-01");
}
~~~

Ví dụ kiểm thử validation error theo hành vi media type mới:

~~~java
@Test
void shouldUseClientErrorForInvalidDocument() {
    webTestClient.post()
            .uri("/graphql")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.parseMediaType(
                    "application/graphql-response+json"))
            .bodyValue(Map.of(
                    "query", "{ unknownField }"))
            .exchange()
            .expectStatus().is4xxClientError()
            .expectHeader().contentTypeCompatibleWith(
                    MediaType.parseMediaType(
                            "application/graphql-response+json"))
            .expectBody()
            .jsonPath("$.errors").isArray();
}
~~~

Hai test trên xác nhận các đặc điểm Spring mô tả trong tài liệu hiện hành: response media type mới được chọn qua Accept và parse/validation error có thể dùng HTTP 4xx.

Có thể tạo `HttpGraphQlTester` với Accept header:

~~~java
HttpGraphQlTester tester =
        HttpGraphQlTester.builder(webTestClient)
                .headers(headers -> headers.setAccept(List.of(
                        MediaType.parseMediaType(
                                "application/graphql-response+json"),
                        MediaType.APPLICATION_JSON)))
                .build();
~~~

Dùng tester để kiểm tra GraphQL body:

~~~java
tester.document("""
        query {
          book(id: "b-01") {
            id
            title
          }
        }
        """)
        .execute()
        .path("book.id")
        .entity(String.class)
        .isEqualTo("b-01");
~~~

Nếu cần kiểm tra status 294 theo GraphQL-over-HTTP September 2026 Edition, hãy viết test riêng cho execution result có cả `data` và `errors`. Không dùng giả định đó cho Spring nếu phiên bản hiện tại vẫn theo mô tả status 200 sau validation.

## 13. Ảnh hưởng tới proxy, gateway và observability

Media type mới không chỉ dành cho client. Nó còn giúp các thành phần hạ tầng nhận diện response GraphQL.

Một số lợi ích:

- Access log có thể phân biệt GraphQL response với JSON error thông thường.
- API gateway có thể phân loại request error và execution result dựa trên status.
- Monitoring có thể thống kê validation failure, partial response và lỗi server.
- Client có thể parse GraphQL error response ngay cả khi HTTP status là 4xx.
- Hệ thống hỗ trợ nhiều phiên bản client có thể dùng content negotiation để chuyển đổi dần.

Tuy nhiên, proxy hoặc gateway có thể thay đổi status, body hoặc Content-Type. Cần cấu hình để:

- Không thay GraphQL response bằng HTML error page ngoài ý muốn.
- Giữ nguyên `application/graphql-response+json` khi chuyển tiếp response hợp lệ.
- Không chuyển mọi HTTP 4xx thành 200.
- Không retry mutation chỉ vì response là 4xx/5xx nếu không biết operation đã được thực thi hay chưa.
- Theo dõi các status code tùy chỉnh như 294 nếu ứng dụng chọn sử dụng.

Nếu response có media type GraphQL nhưng body bị proxy sửa thành một JSON khác, client có thể tin nhầm payload. Vì vậy, cần kiểm thử end-to-end qua gateway/proxy thực tế, không chỉ gọi trực tiếp application server.

## 14. Bảo mật và dữ liệu lỗi

Media type không tự cung cấp authentication hoặc authorization. Nó chỉ xác định loại response và hỗ trợ semantics HTTP.

Khi trả GraphQL errors:

- Không gửi stack trace hoặc SQL query ra client.
- Không đưa access token, session ID hoặc thông tin bí mật vào `extensions`.
- Chỉ công bố error code và field path mà client cần.
- Kiểm soát log variables vì chúng có thể chứa dữ liệu cá nhân.
- Đảm bảo proxy và cache không chia sẻ response cá nhân giữa các user.
- Không xem `application/graphql-response+json` là bằng chứng request đã được xác thực.

Server vẫn cần Spring Security, authorization ở field/service và chính sách bảo vệ dữ liệu như bình thường.

## 15. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Response vẫn là `application/json` | Client gửi Accept legacy hoặc server chọn fallback | Kiểm tra Accept và response Content-Type |
| Gửi media type mới trong Content-Type request bị lỗi | Nhầm media type response với request | Dùng request Content-Type `application/json` |
| Client coi 422 là network error | Client chỉ parse body khi status 2xx | Parse GraphQL response khi Content-Type phù hợp |
| Parse/validation error vẫn là HTTP 200 | Client yêu cầu legacy `application/json` | Ưu tiên `application/graphql-response+json` |
| Execution error vẫn là HTTP 200 trên Spring | Hành vi được Spring docs hiện hành mô tả sau validation | Đọc `errors` trong body và kiểm tra version |
| Client không nhận được response media type mong muốn | Accept header hoặc q-value không phù hợp | Kiểm tra content negotiation |
| Gateway trả HTML thay GraphQL JSON | Middleware thay response khi gặp 4xx/5xx | Cấu hình gateway giữ GraphQL response |
| Status 294 bị xử lý bất thường | Hạ tầng chưa nhận diện status tùy chỉnh | Kiểm tra client, proxy, cache và metrics |
| Không có GraphQL body | Lỗi xảy ra trước khi tạo response hợp lệ hoặc middleware chặn request | Kiểm tra HTTP status và Content-Type thực tế |

## 16. Checklist triển khai

Trước khi dùng `application/graphql-response+json` trong môi trường thực tế:

- [ ] Request POST vẫn dùng `Content-Type: application/json`.
- [ ] Client gửi `Accept: application/graphql-response+json`.
- [ ] Có fallback `application/json` nếu cần hỗ trợ server legacy.
- [ ] Client kiểm tra response Content-Type trước khi parse body.
- [ ] Client có thể parse GraphQL response kể cả khi HTTP status là 4xx.
- [ ] Client đọc cả `data` và `errors`.
- [ ] Server trả status theo hành vi đã xác minh của phiên bản framework.
- [ ] Đã phân biệt request error và execution error trong logging/metrics.
- [ ] Proxy/gateway không thay đổi GraphQL response ngoài ý muốn.
- [ ] Cache không làm lộ response phụ thuộc user hoặc tenant.
- [ ] Đã kiểm thử response thành công, validation error và execution error.
- [ ] Nếu dùng status 294, toàn bộ hạ tầng đã được kiểm tra tương thích.

## Kết luận

`application/graphql-response+json` là media type JSON chuyên biệt cho GraphQL response. Client yêu cầu nó qua header `Accept`, còn request body JSON tiêu chuẩn vẫn dùng `Content-Type: application/json`. Media type này giúp client, proxy và hệ thống quan sát nhận diện GraphQL response rõ ràng, đồng thời hỗ trợ cách dùng HTTP status code có ý nghĩa hơn so với legacy `application/json`.

Với Spring for GraphQL, HTTP transport hiện hỗ trợ media type này. Tuy nhiên, cần phân biệt hành vi được tài liệu Spring mô tả với hướng dẫn mới của GraphQL-over-HTTP September 2026 Edition, đặc biệt là status code cho partial response. Hãy kiểm thử trên đúng phiên bản triển khai, xử lý body theo Content-Type và đọc cả `data` lẫn `errors` để client hoạt động ổn định.

## Tài liệu tham khảo

- [Spring for GraphQL — Server Transports, HTTP](https://docs.spring.io/spring-graphql/reference/transports.html)
- [GraphQL over HTTP — September 2026 Edition](https://http-spec.graphql.org/September2026/)
- [GraphQL — Serving over HTTP](https://graphql.org/learn/serving-over-http/)
- [GraphQL — Announcing the GraphQL over HTTP Specification](https://graphql.org/blog/2026-11-12-announcing-the-graphql-over-http-spec/)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
