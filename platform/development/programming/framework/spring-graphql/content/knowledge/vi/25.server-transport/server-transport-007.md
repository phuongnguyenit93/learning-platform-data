# GraphQL response content type

GraphQL over HTTP dùng HTTP headers để mô tả định dạng request và response. `Content-Type` của request cho server biết body được gửi theo định dạng nào; `Accept` cho server biết client có thể nhận định dạng response nào. Hai header này có vai trò khác nhau và không nên dùng thay thế cho nhau.

Với HTTP request thông thường trong Spring for GraphQL, client gửi GraphQL request envelope dưới dạng JSON, thường dùng `Content-Type: application/json`. Ở chiều trả về, media type chuyên biệt `application/graphql-response+json` mô tả một GraphQL response JSON; `application/json` vẫn được dùng rộng rãi để tương thích với client và server cũ. Chọn media type đúng giúp client phân biệt một GraphQL response với JSON thông thường và xử lý status code nhất quán hơn.

Sau bài này, bạn có thể:

- Phân biệt request `Content-Type`, response `Content-Type` và request `Accept`.
- Hiểu `application/json` và `application/graphql-response+json`.
- Gửi GraphQL query/mutation qua HTTP với headers phù hợp.
- Hiểu quan hệ giữa media type và HTTP status code.
- Nhận biết các lỗi 406, 415 và lỗi GraphQL trong response body.
- Kiểm tra content negotiation trong Spring for GraphQL.
- Phân biệt HTTP response media type với WebSocket, SSE và incremental delivery.

## 1. Content-Type và Accept có vai trò khác nhau

HTTP có hai header quan trọng khi trao đổi nội dung:

| Header | Hướng truyền | Ý nghĩa |
| --- | --- | --- |
| Request `Content-Type` | Client → Server | Định dạng của request body |
| Request `Accept` | Client → Server | Các định dạng response client chấp nhận |
| Response `Content-Type` | Server → Client | Định dạng thực tế của response body |

Ví dụ client gửi GraphQL request JSON và ưu tiên GraphQL response media type:

```http
POST /graphql HTTP/1.1
Content-Type: application/json
Accept: application/graphql-response+json, application/json;q=0.9

{
  "query": "query Book($id: ID!) { book(id: $id) { id title } }",
  "operationName": "Book",
  "variables": {
    "id": "book-42"
  }
}
```

Server đọc request body theo `Content-Type: application/json`, sau đó chọn một response representation phù hợp với `Accept`. Nếu chọn media type chuyên biệt, response có thể là:

```http
HTTP/1.1 200 OK
Content-Type: application/graphql-response+json; charset=UTF-8

{
  "data": {
    "book": {
      "id": "book-42",
      "title": "Spring GraphQL in Practice"
    }
  }
}
```

`Accept` không mô tả định dạng body request. Ngược lại, `Content-Type` request không nói server phải trả về định dạng nào. Nếu client chỉ gửi `Content-Type` mà không gửi `Accept`, server sẽ dùng quy tắc mặc định của adapter/framework.

## 2. GraphQL request envelope là JSON

Một GraphQL HTTP request thường gửi một JSON object với các thuộc tính:

```json
{
  "query": "query Books { books { id title } }",
  "operationName": "Books",
  "variables": {},
  "extensions": {}
}
```

- `query`: GraphQL document dạng chuỗi.
- `operationName`: tên operation cần thực thi nếu document có nhiều operation; có thể bỏ qua nếu chỉ có một operation.
- `variables`: map biến đầu vào của operation.
- `extensions`: metadata mở rộng theo thỏa thuận giữa client và server.

Đây là JSON envelope, vì vậy request body thông thường dùng `Content-Type: application/json`. Không đặt `Content-Type: application/graphql-response+json` cho request envelope chỉ vì server trả response bằng media type đó; tên media type này dành cho GraphQL response.

Một số hệ thống cũ hoặc extension có thể hỗ trợ gửi raw GraphQL document bằng media type riêng, nhưng đó không phải dạng JSON envelope phổ biến của Spring for GraphQL. Hãy dùng đúng định dạng mà HTTP handler của ứng dụng hỗ trợ.

## 3. application/json và application/graphql-response+json

Hai media type thường gặp ở response HTTP:

| Media type | Ý nghĩa | Tình huống |
| --- | --- | --- |
| `application/json` | JSON tổng quát | Tương thích với nhiều client/server hiện có |
| `application/graphql-response+json` | JSON có cấu trúc GraphQL response | Media type chuyên biệt được GraphQL over HTTP khuyến nghị |

`application/graphql-response+json` vẫn chứa JSON body với các trường như `data`, `errors` và có thể có `extensions`. Điểm khác biệt là media type nói rõ body tuân theo hình dạng GraphQL response, giúp client hiểu đây là kết quả của một GraphQL operation thay vì một JSON document tùy ý.

Media type này có hậu tố `+json`, nên client có thể nhận biết cú pháp JSON theo quy ước structured syntax suffix. Tuy nhiên, client vẫn nên kiểm tra media type đầy đủ thay vì chỉ đoán từ nội dung body.

`application/json` vẫn quan trọng vì nhiều client, proxy và server cũ chỉ hỗ trợ media type này. Trong giai đoạn chuyển đổi, client thường gửi cả hai giá trị trong `Accept`, ưu tiên `application/graphql-response+json` bằng quality value cao hơn.

## 4. Response media type không thay đổi theo việc có lỗi hay không

Media type mô tả định dạng response, không mô tả operation thành công hay thất bại. Một GraphQL response có thể là:

- Chỉ có `data` khi mọi field thành công.
- Có cả `data` và `errors` khi một phần field thất bại.
- Chỉ có `errors` khi request không hợp lệ trước execution.
- Có `data: null` cùng `errors` khi execution error lan lên root do non-null propagation.

Các trường hợp trên vẫn là GraphQL response. Nếu server đã chọn `application/graphql-response+json`, response media type không cần đổi chỉ vì mảng `errors` xuất hiện.

Ví dụ partial data:

```http
HTTP/1.1 200 OK
Content-Type: application/graphql-response+json

{
  "data": {
    "book": {
      "id": "book-42",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Author service is unavailable",
      "path": ["book", "author"],
      "extensions": {
        "code": "UPSTREAM_UNAVAILABLE"
      }
    }
  ]
}
```

Client cần đọc GraphQL envelope, không chỉ dựa vào tên media type hoặc status code để kết luận mọi field thành công.

## 5. Accept negotiation cho GraphQL response

Client có thể khai báo nhiều response media type theo thứ tự ưu tiên:

```http
Accept: application/graphql-response+json, application/json;q=0.9
```

Quality value `q` cho biết mức ưu tiên tương đối; giá trị mặc định là `1`. Trong ví dụ, client ưu tiên `application/graphql-response+json` nhưng vẫn chấp nhận `application/json` nếu server chưa hỗ trợ media type mới.

Server cần chọn một representation được cả hai phía hỗ trợ. Nếu client không chấp nhận bất kỳ media type response nào mà server có thể tạo, HTTP content negotiation có thể kết thúc bằng `406 Not Acceptable`.

Khi hỗ trợ nhiều response media type, server nên trả đúng `Content-Type` đã chọn và có thể cần `Vary: Accept` để cache/proxy phân biệt response theo header Accept. Không được luôn ghi cứng `application/graphql-response+json` trong response filter nếu handler thực tế đã serialize theo representation khác hoặc không hỗ trợ semantics tương ứng.

## 6. HTTP status code và GraphQL response

HTTP status code mô tả kết quả ở tầng HTTP; GraphQL `data` và `errors` mô tả kết quả ở tầng GraphQL. Hai tầng liên quan nhưng không đồng nhất.

Với media type chuyên biệt `application/graphql-response+json`, GraphQL over HTTP cho phép phân biệt rõ hơn lỗi request trước execution với execution result. Quy tắc cụ thể cần được áp dụng theo phiên bản đặc tả và implementation, nhưng định hướng là:

- Request không thể được thực thi do lỗi cú pháp, validation hoặc variable coercion có thể được biểu diễn bằng HTTP 4xx.
- Khi GraphQL execution đã tạo execution result, kể cả response có partial data và `errors`, response thường dùng HTTP 2xx.
- Lỗi HTTP hoặc server xảy ra trước khi tạo được GraphQL response có thể dùng status 4xx/5xx tương ứng.

Với media type legacy `application/json`, nhiều client cũ mong đợi đọc GraphQL envelope kể cả khi status không phải 2xx. Vì lý do tương thích, implementation có thể duy trì quy tắc status 200 cho GraphQL response hợp lệ và để client đọc `errors` trong body. Hãy kiểm tra hành vi của Spring for GraphQL version và HTTP adapter đang sử dụng thay vì tự giả định status mapping.

Ví dụ minh họa hai tầng:

| Tình huống | Tầng HTTP | Tầng GraphQL |
| --- | --- | --- |
| Request body không phải JSON hợp lệ | Có thể là 400 | Chưa có GraphQL response |
| `Accept` không có representation phù hợp | 406 | Chưa thực thi operation |
| Query gọi field không tồn tại | Status phụ thuộc response media type/implementation | Request error trong `errors` |
| Resolver lỗi ở field nullable | Thường 2xx khi có execution result | Có thể có `data` và `errors` |
| Lỗi server trước khi tạo response | 5xx | Có thể không có GraphQL envelope |

Không dùng HTTP 200 như bằng chứng duy nhất rằng nghiệp vụ thành công; cũng không dùng HTTP 4xx để thay thế việc đọc `errors` và `extensions.code`.

## 7. Phân biệt 400, 406 và 415

Một số status thường gặp khi cấu hình endpoint:

| Status | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `400 Bad Request` | Request không hợp lệ ở HTTP hoặc GraphQL request parsing/coercion theo mapping của server | JSON body sai cú pháp hoặc request envelope thiếu trường bắt buộc |
| `406 Not Acceptable` | Server không thể tạo response representation mà client yêu cầu | `Accept: application/xml` trong khi endpoint chỉ trả JSON |
| `415 Unsupported Media Type` | Server không hỗ trợ định dạng request body được gửi | Gửi body JSON nhưng khai báo `Content-Type: text/plain` |

Các status chính xác có thể phụ thuộc HTTP adapter, framework version và giai đoạn lỗi. Ví dụ, một query GraphQL sai validation có thể được trả thành GraphQL request error chứ không phải lỗi HTTP parser. Hãy xác định endpoint nhận request đến đâu trước khi phân loại.

## 8. Gửi request bằng curl

Ví dụ gửi query bằng JSON envelope và ưu tiên response media type chuyên biệt:

```bash
curl -i https://localhost:8080/graphql \
  -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/graphql-response+json, application/json;q=0.9' \
  --data '{"query":"query { books { id title } }"}'
```

Đọc cả status line lẫn `Content-Type` trong response headers. Đừng chỉ xem JSON body vì cùng một body có thể được trả với media type hoặc status khác nhau.

Nếu muốn kiểm tra fallback legacy:

```bash
curl -i https://localhost:8080/graphql \
  -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"query":"query { books { id title } }"}'
```

So sánh response headers để xác nhận server chọn media type theo `Accept`. Nếu cả hai request luôn trả cùng một media type, đó có thể là hành vi hiện tại của adapter; cần đối chiếu với phiên bản Spring for GraphQL đang dùng.

## 9. GET và POST trong GraphQL over HTTP

GraphQL over HTTP thường hỗ trợ POST với JSON request envelope. GET có thể dùng query parameters như `query`, `operationName`, `variables` và `extensions` đã được encode theo URL.

Ví dụ GET:

```http
GET /graphql?query=%7Bbooks%7Bid%20title%7D%7D HTTP/1.1
Accept: application/graphql-response+json, application/json;q=0.9
```

GET chỉ phù hợp với query operation. Mutation không được gửi qua GET vì GET có semantics an toàn và có thể bị cache, prefetch hoặc thực thi lại bởi thành phần trung gian. Dùng POST cho mutation.

Với GET, không có request body nên `Content-Type` thường không cần thiết; `Accept` vẫn mô tả response client muốn nhận. Với POST JSON, cần `Content-Type: application/json` và có thể thêm `Accept` để chọn response representation.

## 10. Spring for GraphQL và HTTP content negotiation

Spring for GraphQL cung cấp HTTP transport thông qua `GraphQlHttpHandler` cùng adapter cho Spring MVC hoặc WebFlux. Spring Boot có thể tự cấu hình endpoint theo starter và property của ứng dụng. Request được chuyển thành `WebGraphQlRequest`, sau đó đi qua interceptor và GraphQL execution service.

Khi làm việc với content type, cần kiểm tra ba điểm trong đúng phiên bản ứng dụng:

1. HTTP adapter chấp nhận request `Content-Type` nào.
2. Adapter/framework có hỗ trợ thương lượng `Accept` giữa `application/graphql-response+json` và `application/json` hay không.
3. Response thực tế được ghi với `Content-Type` và status code nào cho request error, execution result và transport error.

Không nên tự đặt header response bằng filter mà không điều chỉnh content negotiation và status mapping. Header phải phản ánh đúng representation đã serialize. Nếu adapter hiện chỉ hỗ trợ `application/json`, hãy giữ hợp đồng đó cho tới khi nâng cấp hoặc cấu hình một implementation hỗ trợ media type GraphQL response đầy đủ.

Property `spring.graphql.path` có thể thay đổi endpoint path, nhưng không tự quyết định mọi media type mà adapter hỗ trợ. Content negotiation còn phụ thuộc HTTP handler, message converter/codec và phiên bản Spring for GraphQL/Spring Framework.

## 11. Ví dụ kiểm thử HTTP bằng WebTestClient

Với WebFlux hoặc test client dựa trên WebTestClient, có thể kiểm tra request headers và response headers trực tiếp:

```java
webTestClient.post()
        .uri("/graphql")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(
                MediaType.parseMediaType("application/graphql-response+json"),
                MediaType.APPLICATION_JSON)
        .bodyValue(Map.of(
                "query", "query { books { id title } }"))
        .exchange()
        .expectStatus().is2xxSuccessful()
        .expectHeader().contentTypeCompatibleWith(
                MediaType.parseMediaType("application/graphql-response+json"));
```

Test này giả định endpoint và adapter của dự án đã hỗ trợ `application/graphql-response+json`. Nếu ứng dụng hiện chỉ trả `application/json`, assertion cần phản ánh đúng contract đã cấu hình; không sửa test để ép một header mà server không thực sự hỗ trợ.

Ngoài media type, nên kiểm tra body envelope:

```java
.expectBody()
.jsonPath("$.data.books").exists();
```

Đối với request lỗi, kiểm tra cả status code và response body theo media type đã thương lượng. Đặc biệt, hãy xác nhận client không bỏ body GraphQL error chỉ vì HTTP status không phải 2xx.

## 12. Kiểm thử fallback và lỗi content negotiation

Nên có các test riêng:

1. Client gửi `Accept: application/graphql-response+json` và server trả media type đó nếu được hỗ trợ.
2. Client gửi `Accept: application/json` và server trả JSON legacy.
3. Client gửi cả hai media type với quality value và server chọn representation ưu tiên phù hợp.
4. Client gửi `Accept` không được hỗ trợ và server trả 406 theo cấu hình.
5. Client gửi request body JSON với `Content-Type: application/json` và server parse được envelope.
6. Client gửi media type request không được hỗ trợ và server trả 415 theo adapter.
7. Query validation error trả đúng GraphQL error envelope và status mapping.
8. Execution error có partial data vẫn được client đọc đúng.
9. Header response khớp representation thực tế, bao gồm charset nếu được khai báo.
10. Proxy/gateway không thay đổi hoặc loại bỏ media type và status ngoài ý muốn.

Nếu dự án dùng `MockMvc`, viết các kiểm tra tương đương qua MockMvc. Nếu dùng `HttpGraphQlTester`, nhớ rằng tester tập trung vào GraphQL interaction; khi cần xác nhận HTTP headers/status, dùng tester hoặc web test client ở tầng transport.

## 13. Subscription và content type của transport

Không phải mọi kết quả GraphQL đều được truyền bằng một HTTP JSON response thông thường.

| Kiểu trao đổi | Transport/media type hoặc protocol thường gặp |
| --- | --- |
| Query/mutation qua HTTP | JSON request/response; response có thể là `application/graphql-response+json` hoặc `application/json` |
| Subscription qua WebSocket | WebSocket subprotocol, thường là `graphql-transport-ws`; không dùng response `Content-Type` HTTP JSON cho từng event |
| Subscription qua Server-Sent Events | `text/event-stream` |
| Incremental delivery | Có thể dùng `multipart/mixed` nếu server, client và phiên bản implementation hỗ trợ |

WebSocket handshake vẫn bắt đầu bằng HTTP, nhưng sau khi upgrade, các GraphQL message được truyền theo subprotocol của WebSocket. SSE dùng một HTTP response stream có content type riêng. Vì vậy, không áp dụng máy móc `application/graphql-response+json` cho mọi event subscription.

`multipart/mixed` cũng không nên bật chỉ bằng cách đổi header. Server phải thực sự phát đúng multipart boundary và format payload mà client hiểu. Hãy kiểm tra hỗ trợ của Spring for GraphQL version, GraphQL Java và transport adapter trước khi sử dụng incremental delivery.

## 14. Charset và JSON encoding

JSON qua HTTP hiện đại thường được mã hóa UTF-8. Response header có thể xuất hiện dưới dạng:

```http
Content-Type: application/graphql-response+json; charset=UTF-8
```

Client không nên giả định response là UTF-16 hoặc dùng encoding theo hệ điều hành. Server cần serialize JSON nhất quán và giữ đúng ký tự Unicode, ví dụ tiếng Việt có dấu.

Không tự nối `charset` vào header nếu message converter/codec đã quản lý encoding. Cần tránh trường hợp header nói UTF-8 nhưng body thực tế được mã hóa theo charset khác.

## 15. Caching, proxy và Vary: Accept

HTTP cache và reverse proxy có thể lưu response dựa trên URL, method và một số request headers. Nếu cùng một endpoint trả hai representation tùy theo `Accept`, cache cần biết response phụ thuộc header đó.

Header:

```http
Vary: Accept
```

cho cache biết representation có thể thay đổi theo `Accept`. Nếu thiếu `Vary: Accept`, một proxy cấu hình không phù hợp có thể trả representation `application/json` cho client chỉ chấp nhận `application/graphql-response+json`, hoặc ngược lại.

GraphQL POST thường không được cache như GET theo mặc định. Nếu cho phép cache query GET, hãy cân nhắc variables trong URL, authorization, tenant, cookies và cache key. Không cache response chứa dữ liệu riêng tư ở shared cache nếu không có chính sách phân vùng phù hợp.

## 16. CORS và browser client

Browser client có thể gửi `Accept` và `Content-Type` qua CORS. `Content-Type: application/json` thường khiến request cross-origin cần preflight vì đây không phải safelisted content type trong nhiều trường hợp. Server cần cho phép origin, method và header phù hợp.

Nếu client gửi thêm header authorization hoặc header tùy chỉnh, cấu hình CORS cần cho phép các header đó. Response `Content-Type` sẽ được browser expose mặc định như response header cơ bản; nếu client cần đọc header không được expose theo mặc định, cấu hình `Access-Control-Expose-Headers` tương ứng.

Không dùng CORS thay cho authentication hoặc authorization. CORS là chính sách browser kiểm soát việc JavaScript ở origin khác đọc response; nó không ngăn mọi client HTTP trực tiếp gọi endpoint.

## 17. Những lỗi thường gặp

- **Nhầm `Accept` với request `Content-Type`:** một header mô tả response mong muốn, header kia mô tả request body.
- **Gửi `application/graphql-response+json` cho JSON request envelope:** media type này mô tả GraphQL response.
- **Chỉ gửi `Accept: application/json` rồi mong server tự dùng media type chuyên biệt:** server chọn theo negotiation và khả năng hỗ trợ thực tế.
- **Luôn ghi cứng response Content-Type:** header có thể không khớp representation đã serialize.
- **Cho rằng có `errors` thì response phải là 4xx:** execution result có partial data vẫn thường là response 2xx.
- **Dựa vào HTTP 200 để kết luận nghiệp vụ thành công:** cần đọc `data`, `errors` và `extensions`.
- **Dùng GET cho mutation:** GET có thể bị cache hoặc prefetch và không phù hợp với operation thay đổi trạng thái.
- **Nhầm HTTP JSON response với WebSocket/SSE subscription:** từng transport có protocol và content type riêng.
- **Đổi header sang multipart/mixed nhưng body không phải multipart:** media type phải khớp định dạng thực tế.
- **Bỏ qua `Vary: Accept`:** cache/proxy có thể phục vụ sai representation.
- **Không kiểm thử qua HTTP adapter thật:** `GraphQlTester` ở execution layer không xác nhận đầy đủ HTTP headers và status.
- **Coi CORS là cơ chế bảo mật API:** vẫn cần Spring Security và authorization ở server.

## 18. Quy trình thiết kế GraphQL response content type

Khi cấu hình HTTP transport cho Spring for GraphQL, hãy thực hiện:

1. Chọn JSON request envelope và xác nhận request `Content-Type` được adapter hỗ trợ.
2. Xác định response media type server hỗ trợ: `application/graphql-response+json`, `application/json` hoặc cả hai.
3. Cấu hình client gửi `Accept` theo thứ tự ưu tiên và fallback phù hợp.
4. Bảo đảm response `Content-Type` phản ánh đúng JSON representation đã serialize.
5. Xác định status mapping cho request error, execution result và lỗi HTTP theo media type/implementation.
6. Trả 406 khi không có representation được chấp nhận và 415 khi request media type không được hỗ trợ, theo adapter contract.
7. Kiểm thử query thành công, partial data, request error và invalid content negotiation qua HTTP.
8. Kiểm tra `Vary: Accept`, proxy, cache và CORS nếu endpoint được gọi từ browser.
9. Xử lý WebSocket, SSE và multipart incremental như các transport/representation riêng.
10. Ghi rõ media type, status code và fallback behavior trong API documentation.

`Content-Type` và `Accept` là phần của hợp đồng HTTP giữa client và GraphQL server. Request JSON envelope thường dùng `application/json`; response có thể dùng media type chuyên biệt `application/graphql-response+json` hoặc media type legacy `application/json` tùy khả năng và chính sách tương thích. Trong Spring for GraphQL, hãy xác nhận hành vi của HTTP adapter và phiên bản framework bằng integration test, bảo đảm header khớp body và status mapping. Khi phân biệt rõ HTTP transport với GraphQL execution và subscription transport, client có thể xử lý response, lỗi và partial data một cách nhất quán.

## Tài liệu tham khảo

- [GraphQL over HTTP Specification](https://graphql.github.io/graphql-over-http/draft/)
- [Spring for GraphQL — HTTP Transport](https://docs.spring.io/spring-graphql/reference/transports.html#transports.http)
- [Spring for GraphQL — GraphQlHttpHandler API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/server/GraphQlHttpHandler.html)
- [Spring Boot — Spring for GraphQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [MDN — Content-Type](https://developer.mozilla.org/docs/Web/HTTP/Headers/Content-Type)
- [MDN — Accept](https://developer.mozilla.org/docs/Web/HTTP/Headers/Accept)
